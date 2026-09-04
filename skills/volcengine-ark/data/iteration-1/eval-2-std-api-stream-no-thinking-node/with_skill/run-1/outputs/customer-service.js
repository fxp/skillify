#!/usr/bin/env node
/**
 * customer-service.js — 用火山方舟标准 API 调豆包 Seed 2.0 lite 做客服问答
 *
 *   单问单答：  node customer-service.js "你们的退货政策是什么？"
 *   多轮对话：  node customer-service.js            （进入交互模式，/exit 退出，/reset 清空上下文，/usage 看累计用量）
 *   从管道读：  echo "怎么开发票" | node customer-service.js
 *
 * 环境变量（见 .env.example）：
 *   ARK_API_KEY        必填，方舟 API Key
 *   ARK_BASE_URL       默认 https://ark.cn-beijing.volces.com/api/v3
 *   ARK_MODEL          默认 doubao-seed-2-0-lite-260428（标准入口用带日期的 Model ID）
 *   ARK_MAX_TOKENS     默认 1024
 *   ARK_TEMPERATURE    不设则用模型默认
 *   CS_SYSTEM_PROMPT   覆盖内置客服 system prompt
 *   ARK_DEBUG=1        把请求体和每个 SSE chunk 打到 stderr
 *
 * 输出约定：模型回答走 stdout（方便管道），用量 / 提示 / 错误走 stderr。
 */

import { createInterface } from "node:readline";
import { stdin, stdout, stderr, exit, env, argv } from "node:process";
import {
  chatStream,
  formatUsage,
  ArkApiError,
  ArkTimeoutError,
  DEFAULT_BASE_URL,
  DEFAULT_MODEL,
} from "./ark-client.js";

const DEFAULT_SYSTEM_PROMPT = [
  "你是一名专业、耐心的在线客服助手。",
  "要求：",
  "1. 用简体中文回答，语气礼貌、简洁，先给结论再给必要说明；",
  "2. 只回答与产品、订单、售后、账户等客服相关的问题；无关问题礼貌说明并引导回客服范围；",
  "3. 不知道或需要查询内部系统的信息（如具体订单状态、个人账户数据）不要编造，告知用户你无法直接查询并说明可以怎么办；",
  "4. 涉及退款、赔付、政策条款等敏感承诺时，提示以官方最终解释为准，必要时建议转人工客服。",
].join("\n");

const config = {
  baseURL: env.ARK_BASE_URL || DEFAULT_BASE_URL,
  model: env.ARK_MODEL || DEFAULT_MODEL,
  maxTokens: env.ARK_MAX_TOKENS ? Number(env.ARK_MAX_TOKENS) : 1024,
  temperature: env.ARK_TEMPERATURE !== undefined && env.ARK_TEMPERATURE !== "" ? Number(env.ARK_TEMPERATURE) : undefined,
  systemPrompt: env.CS_SYSTEM_PROMPT || DEFAULT_SYSTEM_PROMPT,
  debug: env.ARK_DEBUG === "1" || env.ARK_DEBUG === "true",
};

if (Number.isNaN(config.maxTokens) || config.maxTokens <= 0) {
  stderr.write("ARK_MAX_TOKENS 必须是正整数\n");
  exit(2);
}
if (config.temperature !== undefined && (Number.isNaN(config.temperature) || config.temperature < 0 || config.temperature > 2)) {
  stderr.write("ARK_TEMPERATURE 必须在 [0, 2] 之间\n");
  exit(2);
}

/** 会话级累计用量 */
const totals = { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, reasoning_tokens: 0, cached_tokens: 0, turns: 0 };

function addTotals(usage) {
  if (!usage) return;
  totals.turns += 1;
  totals.prompt_tokens += usage.prompt_tokens ?? 0;
  totals.completion_tokens += usage.completion_tokens ?? 0;
  totals.total_tokens += usage.total_tokens ?? 0;
  totals.reasoning_tokens += usage.completion_tokens_details?.reasoning_tokens ?? 0;
  totals.cached_tokens += usage.prompt_tokens_details?.cached_tokens ?? 0;
}

function printTotals() {
  stderr.write(
    [
      "── 本次会话累计 ──",
      `轮次: ${totals.turns}`,
      `输入: ${totals.prompt_tokens}（缓存命中 ${totals.cached_tokens}）  输出: ${totals.completion_tokens}（思维链 ${totals.reasoning_tokens}）  合计: ${totals.total_tokens}`,
      "",
    ].join("\n"),
  );
}

function describeError(err) {
  if (err instanceof ArkApiError) {
    const parts = [`[方舟 API 错误] HTTP ${err.status}${err.code ? ` ${err.code}` : ""}${err.midStream ? "（流式中途）" : ""}`];
    if (err.message) parts.push(`message: ${err.message}`);
    if (err.param) parts.push(`param: ${err.param}`);
    if (err.requestId) parts.push(`Request id: ${err.requestId}（提工单时带上）`);
    if (err.hint) parts.push(`排查: ${err.hint}`);
    return parts.join("\n");
  }
  if (err instanceof ArkTimeoutError) {
    return `[超时] ${err.message}。可通过 idleTimeoutMs / connectTimeoutMs 调大；网络代理问题参考方舟 FAQ。`;
  }
  if (err?.name === "AbortError") return "[已取消] 请求被中断。";
  return `[错误] ${err?.stack || err?.message || String(err)}`;
}

/**
 * 跑一轮：把 history（不含 system）+ 新问题发给模型，流式打印回答，结束打印用量。
 * 返回 assistant 回复文本（供多轮追加到 history）；失败返回 null。
 */
async function askOnce(history, question, { signal } = {}) {
  const messages = [{ role: "system", content: config.systemPrompt }, ...history, { role: "user", content: question }];

  let printedAnything = false;
  let reasoningWarned = false;
  const t0 = Date.now();
  let tFirst = 0;

  try {
    const result = await chatStream(
      {
        messages,
        baseURL: config.baseURL,
        model: config.model,
        thinking: { type: "disabled" }, // 关闭深度思考
        maxTokens: config.maxTokens, // 思考已关，max_tokens 只限回答本身
        temperature: config.temperature,
        signal,
        debug: config.debug ? (m) => stderr.write(`[debug] ${m}\n`) : undefined,
      },
      {
        onContent: (text) => {
          if (!tFirst) tFirst = Date.now();
          printedAnything = true;
          stdout.write(text);
        },
        onReasoning: () => {
          // thinking.disabled 下不应该有思维链；万一出现，只提示一次，不把思维链混进回答里
          if (!reasoningWarned) {
            reasoningWarned = true;
            stderr.write("\n⚠ 收到 reasoning_content：模型没有关闭深度思考，请检查 thinking 参数 / 模型版本。\n");
          }
        },
        onWarning: (m) => stderr.write(`\n⚠ ${m}\n`),
      },
    );

    if (printedAnything) stdout.write("\n");
    if (!printedAnything && !result.content) {
      stderr.write(`\n（模型没有返回正文，finish_reason=${result.finishReason || "?"}）\n`);
    }
    if (result.finishReason === "length") {
      stderr.write(`⚠ 回答因 max_tokens=${config.maxTokens} 被截断，可调大 ARK_MAX_TOKENS。\n`);
    } else if (result.finishReason === "content_filter") {
      stderr.write("⚠ 回答被内容审核拦截（finish_reason=content_filter）。\n");
    }

    const elapsed = Date.now() - t0;
    const ttft = tFirst ? tFirst - t0 : null;
    stderr.write(`\n${formatUsage(result.usage, { model: result.model })}\n`);
    stderr.write(`耗时: ${elapsed} ms${ttft !== null ? `（首字 ${ttft} ms）` : ""}\n\n`);
    addTotals(result.usage);
    return result.content;
  } catch (err) {
    if (printedAnything) stdout.write("\n");
    stderr.write(`\n${describeError(err)}\n\n`);
    return null;
  }
}

async function readAllStdin() {
  const chunks = [];
  for await (const c of stdin) chunks.push(c);
  return Buffer.concat(chunks).toString("utf8").trim();
}

async function interactive() {
  stderr.write(
    [
      `火山方舟客服问答 · ${config.model} · ${config.baseURL}`,
      "输入问题回车发送；/reset 清空上下文，/usage 查看累计用量，/exit 退出（Ctrl+C 中断当前回答）。",
      "",
    ].join("\n"),
  );
  const rl = createInterface({ input: stdin, output: stderr, prompt: "你> " });
  let history = [];
  let current = null; // 正在进行的请求的 AbortController

  rl.on("SIGINT", () => {
    if (current) {
      current.abort(new DOMException("用户中断", "AbortError"));
      current = null;
    } else {
      rl.close();
    }
  });

  rl.prompt();
  for await (const line of rl) {
    const q = line.trim();
    if (!q) {
      rl.prompt();
      continue;
    }
    if (q === "/exit" || q === "/quit") break;
    if (q === "/reset") {
      history = [];
      stderr.write("（上下文已清空）\n");
      rl.prompt();
      continue;
    }
    if (q === "/usage") {
      printTotals();
      rl.prompt();
      continue;
    }

    rl.pause();
    current = new AbortController();
    stdout.write("客服> ");
    const answer = await askOnce(history, q, { signal: current.signal });
    current = null;
    if (answer) {
      // 多轮只回传 role + content；关闭思考时没有 reasoning_content 需要回传
      history.push({ role: "user", content: q }, { role: "assistant", content: answer });
    }
    rl.resume();
    rl.prompt();
  }
  rl.close();
  printTotals();
}

async function main() {
  if (!env.ARK_API_KEY || !env.ARK_API_KEY.trim()) {
    stderr.write(
      [
        "缺少 ARK_API_KEY。",
        "请在火山方舟控制台「API Key 管理」创建方舟 API Key，然后：",
        "  export ARK_API_KEY=xxxxxxxx",
        "注意：标准后付费入口需要先在「开通管理」开通 Doubao-Seed-2.0-lite。",
        "",
      ].join("\n"),
    );
    exit(2);
  }

  const args = argv.slice(2);
  if (args.includes("-h") || args.includes("--help")) {
    stderr.write(
      [
        "用法:",
        '  node customer-service.js "问题"        单问单答',
        "  node customer-service.js               交互式多轮",
        '  echo "问题" | node customer-service.js  从 stdin 读问题',
        "",
      ].join("\n"),
    );
    exit(0);
  }

  let question = args.join(" ").trim();
  if (!question && !stdin.isTTY) question = await readAllStdin();

  if (question) {
    const ac = new AbortController();
    process.on("SIGINT", () => ac.abort(new DOMException("用户中断", "AbortError")));
    const answer = await askOnce([], question, { signal: ac.signal });
    exit(answer === null ? 1 : 0);
  }

  await interactive();
}

main().catch((err) => {
  stderr.write(`${describeError(err)}\n`);
  exit(1);
});
