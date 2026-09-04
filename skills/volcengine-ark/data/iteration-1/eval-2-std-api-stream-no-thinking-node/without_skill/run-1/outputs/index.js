#!/usr/bin/env node
/**
 * 客服问答 CLI —— 火山方舟标准 API × 豆包 Seed 2.0 lite
 *
 * - 关闭深度思考 (thinking.type = "disabled")
 * - 流式输出 (SSE)，边收边打印
 * - 结束时打印 token 用量 (stream_options.include_usage)
 *
 * 用法:
 *   export ARK_API_KEY=xxxx
 *   node index.js                          # 交互式多轮客服对话
 *   node index.js --question "怎么申请退款"   # 单问单答后退出
 *   echo "怎么申请退款" | node index.js       # 从 stdin 读取一个问题
 *
 * 环境变量:
 *   ARK_API_KEY   (必填) 方舟 API Key
 *   ARK_MODEL     (可选) 模型 ID 或接入点 ID，默认 doubao-seed-2-0-lite-260215
 *   ARK_BASE_URL  (可选) 默认 https://ark.cn-beijing.volces.com/api/v3
 *   ARK_TIMEOUT_MS(可选) 单次请求总超时，默认 60000
 */

import { createInterface } from 'node:readline/promises';
import { stdin, stdout, stderr, exit } from 'node:process';
import { parseArgs } from 'node:util';
import { streamChatCompletion, ArkApiError, DEFAULT_BASE_URL } from './ark-client.js';

const DEFAULT_MODEL = 'doubao-seed-2-0-lite-260215';
const MAX_HISTORY_TURNS = 10; // user+assistant pairs kept in context

const SYSTEM_PROMPT = `你是「示例商城」的在线客服助手。要求：
1. 用简体中文、礼貌、简洁地回答，先给结论再给步骤。
2. 只回答与订单、物流、退换货、支付、账户、售后相关的问题；无关问题请礼貌说明并引导回业务范围。
3. 不确定或无法处理的事项（如涉及具体订单核实、赔付审批）不要编造，请告知会转接人工客服（工作时间 9:00-21:00）。
4. 不要索取或复述用户的完整银行卡号、密码、验证码等敏感信息。`;

function loadConfig() {
  const { values } = parseArgs({
    options: {
      question: { type: 'string', short: 'q' },
      model: { type: 'string', short: 'm' },
      'show-reasoning': { type: 'boolean', default: false },
      help: { type: 'boolean', short: 'h', default: false },
    },
    allowPositionals: false,
  });

  if (values.help) {
    stdout.write(
      [
        'Usage: node index.js [--question <text>] [--model <id>] [--show-reasoning]',
        '',
        'Env: ARK_API_KEY (required), ARK_MODEL, ARK_BASE_URL, ARK_TIMEOUT_MS',
        '',
      ].join('\n'),
    );
    exit(0);
  }

  const apiKey = process.env.ARK_API_KEY?.trim();
  if (!apiKey) {
    stderr.write('错误: 未设置 ARK_API_KEY 环境变量。请在火山方舟控制台 -> API Key 管理 中创建并导出：\n  export ARK_API_KEY=your_key\n');
    exit(2);
  }

  const timeoutMs = Number(process.env.ARK_TIMEOUT_MS ?? 60_000);
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    stderr.write('错误: ARK_TIMEOUT_MS 必须是正整数(毫秒)。\n');
    exit(2);
  }

  return {
    apiKey,
    model: values.model ?? process.env.ARK_MODEL ?? DEFAULT_MODEL,
    baseUrl: process.env.ARK_BASE_URL ?? DEFAULT_BASE_URL,
    timeoutMs,
    question: values.question,
    showReasoning: values['show-reasoning'],
  };
}

function formatUsage(usage) {
  const lines = [];
  const pt = usage.prompt_tokens ?? 0;
  const ct = usage.completion_tokens ?? 0;
  const tt = usage.total_tokens ?? pt + ct;
  lines.push(`  prompt_tokens     : ${pt}`);
  const cached = usage.prompt_tokens_details?.cached_tokens;
  if (cached !== undefined) lines.push(`    cached_tokens   : ${cached}`);
  lines.push(`  completion_tokens : ${ct}`);
  const reasoning = usage.completion_tokens_details?.reasoning_tokens;
  if (reasoning !== undefined) lines.push(`    reasoning_tokens: ${reasoning}`);
  lines.push(`  total_tokens      : ${tt}`);
  return lines.join('\n');
}

/**
 * Send one turn, stream the answer to stdout, return the full assistant text.
 * Prints usage + meta to stderr so stdout stays clean for piping.
 */
async function askOnce(cfg, messages, signal) {
  let answer = '';
  let usage;
  let meta;
  let finishReason;
  let printedReasoningHeader = false;
  const startedAt = Date.now();

  try {
    for await (const ev of streamChatCompletion({
      apiKey: cfg.apiKey,
      model: cfg.model,
      baseUrl: cfg.baseUrl,
      messages,
      temperature: 0.3,
      maxTokens: 1024,
      disableThinking: true,
      timeoutMs: cfg.timeoutMs,
      signal,
    })) {
      switch (ev.type) {
        case 'meta':
          meta = ev;
          break;
        case 'reasoning':
          // Should not appear with thinking disabled; never mix into the answer.
          if (cfg.showReasoning) {
            if (!printedReasoningHeader) {
              stderr.write('[reasoning] ');
              printedReasoningHeader = true;
            }
            stderr.write(ev.text);
          }
          break;
        case 'delta':
          answer += ev.text;
          stdout.write(ev.text);
          break;
        case 'finish':
          finishReason = ev.reason;
          break;
        case 'usage':
          usage = ev.usage;
          break;
        default:
          break;
      }
    }
  } finally {
    if (answer.length > 0 && !answer.endsWith('\n')) stdout.write('\n');
  }

  const elapsed = ((Date.now() - startedAt) / 1000).toFixed(2);

  if (finishReason && finishReason !== 'stop') {
    stderr.write(`\n[warn] finish_reason=${finishReason}${finishReason === 'length' ? '（回答可能被 max_tokens 截断）' : ''}\n`);
  }

  stderr.write('\n--- Token 用量 ---\n');
  if (usage) {
    stderr.write(formatUsage(usage) + '\n');
  } else {
    stderr.write('  (服务端未返回 usage；请确认 stream_options.include_usage 受支持，或检查网关是否吞掉了最后一个 chunk)\n');
  }
  stderr.write(`  model             : ${meta?.model ?? cfg.model}\n`);
  if (meta?.id) stderr.write(`  request id        : ${meta.id}\n`);
  stderr.write(`  elapsed           : ${elapsed}s\n\n`);

  return answer;
}

function trimHistory(messages) {
  // messages[0] is the system prompt; keep the most recent N user/assistant pairs.
  const system = messages[0];
  const rest = messages.slice(1);
  const keep = rest.slice(-MAX_HISTORY_TURNS * 2);
  return [system, ...keep];
}

async function readAllStdin() {
  const chunks = [];
  for await (const c of stdin) chunks.push(c);
  return Buffer.concat(chunks).toString('utf8').trim();
}

async function main() {
  const cfg = loadConfig();
  const ac = new AbortController();
  process.on('SIGINT', () => {
    ac.abort(new Error('interrupted'));
    stderr.write('\n已中断。\n');
    exit(130);
  });

  let messages = [{ role: 'system', content: SYSTEM_PROMPT }];

  // Mode 1: single question from --question or piped stdin.
  let single = cfg.question;
  if (!single && !stdin.isTTY) {
    single = await readAllStdin();
  }
  if (single) {
    if (!single.trim()) {
      stderr.write('错误: 问题为空。\n');
      exit(2);
    }
    messages.push({ role: 'user', content: single.trim() });
    await askOnce(cfg, messages, ac.signal);
    return;
  }

  // Mode 2: interactive multi-turn session.
  stderr.write(`客服助手已就绪 (model=${cfg.model})。输入问题回车发送，输入 /exit 退出，/reset 清空上下文。\n\n`);
  const rl = createInterface({ input: stdin, output: stderr });
  try {
    while (true) {
      const line = (await rl.question('你: ')).trim();
      if (!line) continue;
      if (line === '/exit' || line === '/quit') break;
      if (line === '/reset') {
        messages = [{ role: 'system', content: SYSTEM_PROMPT }];
        stderr.write('上下文已清空。\n');
        continue;
      }
      messages.push({ role: 'user', content: line });
      messages = trimHistory(messages);
      stderr.write('客服: ');
      const answer = await askOnce(cfg, messages, ac.signal);
      messages.push({ role: 'assistant', content: answer });
    }
  } finally {
    rl.close();
  }
}

main().catch((err) => {
  if (err instanceof ArkApiError) {
    stderr.write(`\n请求失败 (HTTP ${err.status}${err.code ? `, code=${err.code}` : ''}): ${err.message}\n`);
    if (err.requestId) stderr.write(`request id: ${err.requestId}\n`);
    if (err.status === 401) stderr.write('提示: 检查 ARK_API_KEY 是否正确、是否已过期。\n');
    if (err.status === 404 || err.code === 'ModelNotOpen' || err.code === 'InvalidEndpointOrModel') {
      stderr.write('提示: 确认模型已在方舟控制台「开通管理」中开通，且 ARK_MODEL 为正确的模型 ID (含版本后缀) 或接入点 ID (ep-...)。\n');
    }
    if (err.status === 429) stderr.write('提示: 触发限流 (RPM/TPM)，请稍后重试或提升配额。\n');
    exit(1);
  }
  stderr.write(`\n发生错误: ${err?.message ?? err}\n`);
  exit(1);
});
