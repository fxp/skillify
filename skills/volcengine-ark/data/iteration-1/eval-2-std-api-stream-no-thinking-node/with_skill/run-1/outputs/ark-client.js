/**
 * ark-client.js — 火山方舟（Volcengine Ark）标准后付费入口的最小流式客户端
 *
 * 只依赖 Node.js ≥ 18 内置的 fetch / ReadableStream / AbortController，零第三方依赖。
 *
 * 设计要点（均来自方舟 Chat Completions 文档与 skill 中的实测结论）：
 *  - 入口：https://ark.cn-beijing.volces.com/api/v3（标准后付费）。/api/plan/v3、/api/coding/v3 是套餐入口，
 *    Key 与 model 格式都不同，本客户端默认不走那两个。
 *  - 鉴权：Authorization: Bearer <方舟 API Key>。
 *  - model：标准入口填带日期的 Model ID（doubao-seed-2-0-lite-260428）或推理接入点 ep-xxx。
 *  - 关闭深度思考：顶层字段 thinking: { type: "disabled" }（方舟私有字段，不在 OpenAI 规范里）。
 *  - 流式：stream: true + stream_options: { include_usage: true }；usage 在 `data: [DONE]` 之前
 *    以一个 choices 为空数组的 chunk 下发，中间 chunk 的 usage 一律为 null。
 *  - role 只接受 system / user / assistant / tool，不接受 OpenAI 新版的 developer。
 *  - 重试：只在拿到响应头之前（网络错误、429 限流、500）指数退避重试；一旦开始收流就不再重试，
 *    因为服务端已生成的 token 会计费。
 */

import { randomUUID } from "node:crypto";

export const DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3";
export const DEFAULT_MODEL = "doubao-seed-2-0-lite-260428";

const ALLOWED_ROLES = new Set(["system", "user", "assistant", "tool"]);

/** 429 / 500 里可以安全重试的错误码（限流请求不计费）。见 errors-and-limits.md §7 */
const RETRYABLE_CODES = new Set([
  "RateLimitExceeded.EndpointRPMExceeded",
  "RateLimitExceeded.EndpointTPMExceeded",
  "ModelAccountRpmRateLimitExceeded",
  "ModelAccountTpmRateLimitExceeded",
  "APIAccountRpmRateLimitExceeded",
  "AccountRateLimitExceeded",
  "ServerOverloaded",
  "RequestBurstTooFast",
  "InflightBatchsizeExceeded",
  "InternalServiceError",
]);

/** 明确不可重试的 429 子类（配额 / 自设限额，重试只会继续失败） */
const NON_RETRYABLE_429 = new Set(["QuotaExceeded", "SetLimitExceeded"]);

/** 常见错误码 → 给人看的排查提示 */
const ERROR_HINTS = {
  AuthenticationError:
    "API Key 缺失或无效。确认 ARK_API_KEY 是「方舟 API Key」（控制台 → API Key 管理），而不是 Agent Plan 专属 Key；检查首尾空格。",
  InvalidAccountStatus: "账号状态异常，请联系火山引擎。",
  AccountOverdueError: "账号欠费（余额 < 0），请到费用中心充值。",
  "OperationDenied.ServiceOverdue": "账单已逾期，请充值。",
  "OperationDenied.ServiceNotOpen":
    "模型未开通。标准后付费入口需要先在控制台「开通管理」开通该模型（或开启自动开通）。",
  ModelNotOpen:
    "账号未开通该模型。到控制台「开通管理」开通 doubao-seed-2.0-lite 后重试。",
  "InvalidEndpointOrModel.NotFound":
    "模型或接入点不存在 / 无权访问。标准入口 /api/v3 要填带日期的 Model ID（如 doubao-seed-2-0-lite-260428）或 ep-xxx；小写 Model Name（doubao-seed-2.0-lite）是套餐入口的写法。",
  "InvalidEndpointOrModel.ModelIDAccessDisabled":
    "当前账号策略不允许用 Model ID 直调，请在控制台创建推理接入点并把 ARK_MODEL 设为 ep-xxx。",
  AccessDenied: "无权访问：检查 API Key 的模型 / 接入点 / IP 白名单限制。",
  InvalidParameter: "请求参数非法：对照 message 里的字段名检查（常见：role 用了 developer、max_tokens 与 max_completion_tokens 同时传）。",
  MissingParameter: "缺少必要参数。",
  SensitiveContentDetected: "输入内容触发内容审核，请更换提问。",
  QuotaExceeded: "额度耗尽（免费试用额度或自设限额）。开通模型进入后付费，或到控制台调整。",
  SetLimitExceeded: "达到你在「开通管理 → 推理限额」里自设的限额，服务已暂停。",
  InternalServiceError: "方舟内部错误，已自动重试仍失败；带 Request id 提工单。",
};

export class ArkApiError extends Error {
  /**
   * @param {object} p
   * @param {number} p.status HTTP 状态码（流中错误为 200）
   * @param {string} [p.code] error.code
   * @param {string} [p.type] error.type（可能为空串）
   * @param {string} [p.param] error.param（可能为空串）
   * @param {string} [p.message]
   * @param {string} [p.requestId]
   * @param {boolean} [p.midStream] 是否在收流过程中出错（此时不应重试）
   * @param {string} [p.rawBody]
   */
  constructor({ status, code, type, param, message, requestId, midStream = false, rawBody }) {
    super(message || `HTTP ${status}${code ? ` ${code}` : ""}`);
    this.name = "ArkApiError";
    this.status = status;
    this.code = code || "";
    this.type = type || "";
    this.param = param || "";
    this.requestId = requestId || "";
    this.midStream = midStream;
    this.rawBody = rawBody;
  }

  /** 是否值得重试（仅在未开始收流时有意义） */
  get retryable() {
    if (this.midStream) return false;
    if (this.code && RETRYABLE_CODES.has(this.code)) return true;
    if (this.status === 429) {
      // 未知 429 子码：除明确的配额类外默认可重试
      return !NON_RETRYABLE_429.has(this.code.split(".")[0]);
    }
    return this.status >= 500;
  }

  /** 人类可读的排查提示 */
  get hint() {
    return ERROR_HINTS[this.code] || ERROR_HINTS[this.code.split(".")[0]] || "";
  }

  /**
   * 从非 2xx Response 构造。方舟错误 body 固定为 {"error":{"code","message","param","type"}}，
   * 但路径不存在时可能返回空 body，所以要先判空再解析。
   */
  static async fromResponse(response) {
    let rawBody = "";
    try {
      rawBody = await response.text();
    } catch {
      /* ignore */
    }
    let err = {};
    if (rawBody.trim()) {
      try {
        err = JSON.parse(rawBody)?.error ?? {};
      } catch {
        err = { message: rawBody.slice(0, 500) };
      }
    }
    const requestId =
      /Request id:\s*([A-Za-z0-9-]+)/i.exec(err.message || "")?.[1] ||
      response.headers?.get?.("x-request-id") ||
      "";
    return new ArkApiError({
      status: response.status,
      code: err.code,
      type: err.type,
      param: err.param,
      message: err.message || `HTTP ${response.status} ${response.statusText || ""}`.trim(),
      requestId,
      rawBody,
    });
  }
}

export class ArkTimeoutError extends Error {
  constructor(phase, ms) {
    super(`${phase} 超时（${ms} ms）`);
    this.name = "ArkTimeoutError";
    this.phase = phase;
    this.timeoutMs = ms;
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 指数退避 + 抖动；如果服务端给了 Retry-After 则优先用它 */
function backoffMs(attempt, retryAfterHeader) {
  const ra = Number(retryAfterHeader);
  if (Number.isFinite(ra) && ra > 0) return Math.min(ra * 1000, 60_000);
  const base = 1000 * 2 ** attempt; // 1s, 2s, 4s...
  return Math.min(base + Math.random() * 500, 30_000);
}

/**
 * 把 SSE 字节流解析成一条条 `data:` 负载字符串。
 *
 * 方舟 / OpenAI 兼容服务器每个 `data:` 行就是一个完整的 JSON（或 `[DONE]`），
 * 所以这里按「一行 data = 一个事件」派发，而不是按 SSE 规范把多行 data 用 \n 拼接——
 * 后者在服务器不发空行分隔时会把两个 JSON 粘在一起。
 * 正确处理：跨 TCP 包被切断的行、CRLF、`:` 开头的注释行、event:/id:/retry: 行。
 *
 * @param {ReadableStream<Uint8Array>} body
 * @param {{ onActivity?: () => void }} [opts]
 */
export async function* sseDataLines(body, { onActivity } = {}) {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";

  const handleLine = (rawLine) => {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (!line || line.startsWith(":")) return undefined;
    if (!line.startsWith("data:")) return undefined; // event:/id:/retry: 忽略
    let payload = line.slice(5);
    if (payload.startsWith(" ")) payload = payload.slice(1);
    return payload;
  };

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      onActivity?.();
      buf += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) !== -1) {
        const line = buf.slice(0, nl);
        buf = buf.slice(nl + 1);
        const payload = handleLine(line);
        if (payload !== undefined) yield payload;
      }
    }
    buf += decoder.decode();
    if (buf) {
      const payload = handleLine(buf);
      if (payload !== undefined) yield payload;
    }
  } finally {
    // 消费者提前 break / 抛错时释放连接，避免 socket 数据积压
    try {
      await reader.cancel();
    } catch {
      /* ignore */
    }
  }
}

/**
 * 校验 messages：role 只能是 system/user/assistant/tool；content 必须有。
 */
export function validateMessages(messages) {
  if (!Array.isArray(messages) || messages.length === 0) {
    throw new TypeError("messages 必须是非空数组");
  }
  messages.forEach((m, i) => {
    if (!m || typeof m !== "object") throw new TypeError(`messages[${i}] 不是对象`);
    if (!ALLOWED_ROLES.has(m.role)) {
      throw new TypeError(
        `messages[${i}].role = "${m.role}" 不被方舟支持，只能是 system / user / assistant / tool（OpenAI 的 developer 要改成 system）`,
      );
    }
    if (m.role !== "assistant" && (m.content === undefined || m.content === null || m.content === "")) {
      throw new TypeError(`messages[${i}].content 为空`);
    }
  });
}

/**
 * 流式调用 Chat Completions，按事件产出：
 *   { type: "start",     attempt, url }
 *   { type: "meta",      id, model, serviceTier }          // 首个 chunk 带的元信息；model 是实际服务的版本
 *   { type: "reasoning", text }                             // 思维链增量（关闭思考时不应出现）
 *   { type: "content",   text }                             // 回答增量
 *   { type: "tool_calls", toolCalls }                       // 本脚本不传 tools，正常不会出现
 *   { type: "finish",    finishReason }                     // stop / length / content_filter / tool_calls
 *   { type: "usage",     usage }                            // 末尾 usage chunk（choices 为空）
 *   { type: "warning",   message }
 *
 * @param {object} opts
 * @param {Array<{role: string, content: any}>} opts.messages
 * @param {string} [opts.apiKey]        默认 process.env.ARK_API_KEY
 * @param {string} [opts.baseURL]       默认 process.env.ARK_BASE_URL 或 DEFAULT_BASE_URL
 * @param {string} [opts.model]         默认 process.env.ARK_MODEL 或 DEFAULT_MODEL
 * @param {{type: "enabled"|"disabled"|"auto"}|null} [opts.thinking]  默认 { type: "disabled" }；传 null 则不发该字段
 * @param {number} [opts.maxTokens]     回答最大 token（关闭思考时用它即可）
 * @param {number} [opts.maxCompletionTokens]  回答 + 思维链上限；不能与 maxTokens 同传
 * @param {number} [opts.temperature]
 * @param {number} [opts.topP]
 * @param {object} [opts.extraBody]     其余想透传的字段
 * @param {Record<string,string>} [opts.headers]
 * @param {AbortSignal} [opts.signal]
 * @param {typeof fetch} [opts.fetchImpl]  便于测试注入
 * @param {number} [opts.maxRetries=2]
 * @param {number} [opts.connectTimeoutMs=30000]  从发请求到拿到响应头
 * @param {number} [opts.idleTimeoutMs=90000]     收流期间两个 chunk 之间的最大间隔
 * @param {string} [opts.clientRequestId]         X-Client-Request-Id，方便和方舟服务端日志对账
 * @param {(msg: string) => void} [opts.debug]
 */
export async function* streamChatCompletion(opts) {
  const {
    messages,
    apiKey = process.env.ARK_API_KEY,
    baseURL = process.env.ARK_BASE_URL || DEFAULT_BASE_URL,
    model = process.env.ARK_MODEL || DEFAULT_MODEL,
    thinking = { type: "disabled" },
    maxTokens,
    maxCompletionTokens,
    temperature,
    topP,
    extraBody = {},
    headers = {},
    signal,
    fetchImpl = globalThis.fetch,
    maxRetries = 2,
    connectTimeoutMs = 30_000,
    idleTimeoutMs = 90_000,
    clientRequestId = randomUUID(),
    debug,
  } = opts;

  if (!apiKey || !apiKey.trim()) {
    throw new Error("缺少方舟 API Key：请设置环境变量 ARK_API_KEY（控制台 → API Key 管理）。");
  }
  if (typeof fetchImpl !== "function") {
    throw new Error("当前 Node 没有全局 fetch，请升级到 Node ≥ 18。");
  }
  if (maxTokens != null && maxCompletionTokens != null) {
    throw new TypeError("max_tokens 与 max_completion_tokens 不能同时设置（方舟会 400）。");
  }
  validateMessages(messages);

  const normalizedBase = baseURL.replace(/\/+$/, "");
  if (/\/api\/(plan|coding)(\/|$)/.test(normalizedBase)) {
    // 不是禁止，只是提醒：本脚本面向标准后付费；套餐入口 model 格式是小写 Model Name
    yield {
      type: "warning",
      message: `baseURL 指向套餐入口 ${normalizedBase}，model 需用小写 Model Name（如 doubao-seed-2.0-lite），且 Coding/Agent Plan 官方口径不允许用于普通 API 调用。`,
    };
  }
  const url = `${normalizedBase}/chat/completions`;

  const body = {
    model,
    messages,
    stream: true,
    stream_options: { include_usage: true },
    ...(thinking ? { thinking } : {}),
    ...(maxTokens != null ? { max_tokens: maxTokens } : {}),
    ...(maxCompletionTokens != null ? { max_completion_tokens: maxCompletionTokens } : {}),
    ...(temperature != null ? { temperature } : {}),
    ...(topP != null ? { top_p: topP } : {}),
    ...extraBody,
  };
  const bodyJson = JSON.stringify(body);
  debug?.(`POST ${url}\n${bodyJson}`);

  // ---------- 阶段 1：建连 + 拿响应头（可重试） ----------
  let response;
  let attempt = 0;
  const ac = new AbortController();
  const onExternalAbort = () => ac.abort(signal?.reason);
  if (signal) {
    if (signal.aborted) throw signal.reason ?? new Error("请求已被取消");
    signal.addEventListener("abort", onExternalAbort, { once: true });
  }

  try {
    for (;;) {
      let connectTimer;
      const connectTimeout = new ArkTimeoutError("建连 / 首包", connectTimeoutMs);
      try {
        connectTimer = setTimeout(() => ac.abort(connectTimeout), connectTimeoutMs);
        response = await fetchImpl(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
            Authorization: `Bearer ${apiKey.trim()}`,
            "X-Client-Request-Id": clientRequestId,
            ...headers,
          },
          body: bodyJson,
          signal: ac.signal,
        });
      } catch (err) {
        clearTimeout(connectTimer);
        if (signal?.aborted) throw signal.reason ?? err;
        const wrapped = ac.signal.aborted && ac.signal.reason === connectTimeout ? connectTimeout : err;
        if (attempt < maxRetries) {
          const wait = backoffMs(attempt, null);
          debug?.(`网络错误 ${wrapped?.message ?? wrapped}，${wait} ms 后重试（${attempt + 1}/${maxRetries}）`);
          await sleep(wait);
          attempt += 1;
          // 超时中止过的 controller 不能复用；换一个新的
          if (ac.signal.aborted) {
            return yield* streamChatCompletion({ ...opts, maxRetries: maxRetries - attempt, clientRequestId });
          }
          continue;
        }
        throw wrapped;
      }
      clearTimeout(connectTimer);

      if (response.ok) break;

      const apiErr = await ArkApiError.fromResponse(response);
      if (apiErr.retryable && attempt < maxRetries) {
        const wait = backoffMs(attempt, response.headers.get("retry-after"));
        debug?.(`HTTP ${apiErr.status} ${apiErr.code}，${wait} ms 后重试（${attempt + 1}/${maxRetries}）`);
        await sleep(wait);
        attempt += 1;
        continue;
      }
      throw apiErr;
    }

    yield { type: "start", attempt, url, clientRequestId };

    if (!response.body) {
      throw new ArkApiError({ status: response.status, message: "响应没有 body，无法读取流", midStream: true });
    }

    // ---------- 阶段 2：收流（不可重试，已生成 token 会计费） ----------
    const idleTimeout = new ArkTimeoutError("流式空闲", idleTimeoutMs);
    let idleTimer = setTimeout(() => ac.abort(idleTimeout), idleTimeoutMs);
    const resetIdle = () => {
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => ac.abort(idleTimeout), idleTimeoutMs);
    };

    let metaSent = false;
    let done = false;
    try {
      for await (const payload of sseDataLines(response.body, { onActivity: resetIdle })) {
        debug?.(`SSE ${payload}`);
        if (payload === "[DONE]") {
          done = true;
          break;
        }
        let chunk;
        try {
          chunk = JSON.parse(payload);
        } catch {
          yield { type: "warning", message: `无法解析的 SSE chunk：${payload.slice(0, 200)}` };
          continue;
        }
        if (chunk?.error) {
          const e = chunk.error;
          throw new ArkApiError({
            status: response.status,
            code: e.code,
            type: e.type,
            param: e.param,
            message: e.message,
            requestId: /Request id:\s*([A-Za-z0-9-]+)/i.exec(e.message || "")?.[1],
            midStream: true,
          });
        }
        if (!metaSent && chunk.model) {
          metaSent = true;
          yield { type: "meta", id: chunk.id, model: chunk.model, serviceTier: chunk.service_tier };
        }
        // usage 通常只在最后一个 choices 为空的 chunk 出现；个别第三方模型会提前给，统一以最后一次为准
        if (chunk.usage) yield { type: "usage", usage: chunk.usage };

        const choice = Array.isArray(chunk.choices) ? chunk.choices[0] : undefined;
        if (!choice) continue; // include_usage 的收尾 chunk 没有 choices
        const delta = choice.delta ?? {};
        if (delta.reasoning_content) yield { type: "reasoning", text: delta.reasoning_content };
        if (delta.content) yield { type: "content", text: delta.content };
        if (Array.isArray(delta.tool_calls) && delta.tool_calls.length) {
          yield { type: "tool_calls", toolCalls: delta.tool_calls };
        }
        if (choice.finish_reason) yield { type: "finish", finishReason: choice.finish_reason };
      }
    } catch (err) {
      if (signal?.aborted) throw signal.reason ?? err;
      if (ac.signal.aborted && ac.signal.reason === idleTimeout) throw idleTimeout;
      throw err;
    } finally {
      clearTimeout(idleTimer);
    }
    if (!done) yield { type: "warning", message: "流在收到 data: [DONE] 之前就结束了，内容可能不完整。" };
  } finally {
    signal?.removeEventListener("abort", onExternalAbort);
  }
}

/**
 * 便捷封装：把流消费完，返回汇总结果。回调用于实时打印。
 * @returns {Promise<{content: string, reasoning: string, usage: object|null, model: string, id: string, finishReason: string, warnings: string[]}>}
 */
export async function chatStream(opts, { onContent, onReasoning, onWarning } = {}) {
  let content = "";
  let reasoning = "";
  let usage = null;
  let model = "";
  let id = "";
  let finishReason = "";
  const warnings = [];
  for await (const ev of streamChatCompletion(opts)) {
    switch (ev.type) {
      case "content":
        content += ev.text;
        onContent?.(ev.text);
        break;
      case "reasoning":
        reasoning += ev.text;
        onReasoning?.(ev.text);
        break;
      case "usage":
        usage = ev.usage;
        break;
      case "meta":
        model = ev.model;
        id = ev.id;
        break;
      case "finish":
        finishReason = ev.finishReason;
        break;
      case "warning":
        warnings.push(ev.message);
        onWarning?.(ev.message);
        break;
      default:
        break;
    }
  }
  return { content, reasoning, usage, model, id, finishReason, warnings };
}

/** 把 usage 对象格式化成多行文本（缺失字段容错） */
export function formatUsage(usage, { model } = {}) {
  if (!usage) {
    return [
      "── Token 用量 ──",
      "（未收到 usage：确认请求带了 stream_options.include_usage=true，且流正常收到 [DONE]）",
    ].join("\n");
  }
  const cached = usage.prompt_tokens_details?.cached_tokens ?? 0;
  const reasoning = usage.completion_tokens_details?.reasoning_tokens ?? 0;
  const lines = [
    "── Token 用量 ──",
    ...(model ? [`实际服务模型      : ${model}`] : []),
    `输入 prompt_tokens  : ${usage.prompt_tokens ?? "?"}（缓存命中 cached_tokens: ${cached}）`,
    `输出 completion_tokens: ${usage.completion_tokens ?? "?"}（思维链 reasoning_tokens: ${reasoning}）`,
    `合计 total_tokens   : ${usage.total_tokens ?? "?"}`,
  ];
  if (reasoning > 0) {
    lines.push("⚠ reasoning_tokens > 0：深度思考没有被关闭，请检查请求里的 thinking.type 是否为 disabled。");
  }
  return lines.join("\n");
}
