/**
 * ark-client.test.js — 不打真实 API 的单元测试（node --test）
 * 用注入的 fetchImpl 模拟方舟 SSE 响应，验证：
 *   - 请求 URL / 头 / body（thinking.disabled、stream、include_usage、Bearer Key）
 *   - SSE 解析：跨包切断的行、CRLF、usage 收尾 chunk（choices 为空）、[DONE]
 *   - 错误 body 解析与 hint、Request id 提取
 *   - 429 限流重试、401 不重试、流中途报错不重试
 *   - role 校验（developer 拒绝）
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  streamChatCompletion,
  chatStream,
  sseDataLines,
  formatUsage,
  ArkApiError,
  DEFAULT_BASE_URL,
  DEFAULT_MODEL,
} from "./ark-client.js";

const API_KEY = "test-key-not-real";

/** 把若干字符串按给定切片边界组成 ReadableStream<Uint8Array> */
function streamFromPieces(pieces) {
  const enc = new TextEncoder();
  let i = 0;
  return new ReadableStream({
    pull(controller) {
      if (i < pieces.length) controller.enqueue(enc.encode(pieces[i++]));
      else controller.close();
    },
  });
}

/** 模拟方舟 doubao-seed-2.0-lite 关闭思考 + include_usage 的完整 SSE 文本 */
function arkSSE({ model = "doubao-seed-2-0-lite-260428", text = ["您好", "，", "很高兴为您服务。"] } = {}) {
  const base = { created: 1788487468, id: "0217abc", model, service_tier: "default", object: "chat.completion.chunk", usage: null };
  const lines = [];
  text.forEach((t, idx) => {
    lines.push(`data: ${JSON.stringify({ ...base, choices: [{ delta: { content: t, role: "assistant" }, index: 0 }] })}\n\n`);
    if (idx === text.length - 1) {
      lines.push(`data: ${JSON.stringify({ ...base, choices: [{ delta: { content: "", role: "assistant" }, finish_reason: "stop", index: 0 }] })}\n\n`);
    }
  });
  lines.push(
    `data: ${JSON.stringify({
      ...base,
      choices: [],
      usage: {
        prompt_tokens: 42,
        completion_tokens: 12,
        total_tokens: 54,
        prompt_tokens_details: { cached_tokens: 0 },
        completion_tokens_details: { reasoning_tokens: 0 },
      },
    })}\n\n`,
  );
  lines.push("data: [DONE]\n\n");
  return lines.join("");
}

function sseResponse(sseText, { pieces, status = 200 } = {}) {
  const body = streamFromPieces(pieces ?? [sseText]);
  return new Response(body, { status, headers: { "Content-Type": "text/event-stream" } });
}

function jsonErrorResponse(status, error, headers = {}) {
  return new Response(JSON.stringify({ error }), { status, headers: { "Content-Type": "application/json", ...headers } });
}

test("sseDataLines: 跨包切断、CRLF、注释行、无 trailing newline", async () => {
  const pieces = ["data: {\"a\"", ":1}\r\n\r\n: comment\nevent: x\ndata: {\"b\":2}\n\ndata: [DO", "NE]"];
  const got = [];
  for await (const p of sseDataLines(streamFromPieces(pieces))) got.push(p);
  assert.deepEqual(got, ['{"a":1}', '{"b":2}', "[DONE]"]);
});

test("streamChatCompletion: 请求形态正确，事件序列正确，usage 在收尾 chunk", async () => {
  let captured;
  const fetchImpl = async (url, init) => {
    captured = { url, init };
    // 故意把 SSE 文本切成奇怪的边界（含多字节汉字中间）
    const full = arkSSE();
    const bytes = new TextEncoder().encode(full);
    const cut1 = 37;
    const cut2 = Math.floor(bytes.length / 2);
    const dec = (u8) => u8; // 直接 enqueue 字节
    const body = new ReadableStream({
      start(c) {
        c.enqueue(dec(bytes.slice(0, cut1)));
        c.enqueue(dec(bytes.slice(cut1, cut2)));
        c.enqueue(dec(bytes.slice(cut2)));
        c.close();
      },
    });
    return new Response(body, { status: 200 });
  };

  const events = [];
  for await (const ev of streamChatCompletion({
    apiKey: API_KEY,
    messages: [
      { role: "system", content: "你是客服" },
      { role: "user", content: "你好" },
    ],
    fetchImpl,
    maxTokens: 512,
  })) {
    events.push(ev);
  }

  assert.equal(captured.url, `${DEFAULT_BASE_URL}/chat/completions`);
  assert.equal(captured.init.method, "POST");
  assert.equal(captured.init.headers.Authorization, `Bearer ${API_KEY}`);
  assert.equal(captured.init.headers["Content-Type"], "application/json");
  assert.ok(captured.init.headers["X-Client-Request-Id"]);
  const body = JSON.parse(captured.init.body);
  assert.equal(body.model, DEFAULT_MODEL);
  assert.equal(body.stream, true);
  assert.deepEqual(body.stream_options, { include_usage: true });
  assert.deepEqual(body.thinking, { type: "disabled" });
  assert.equal(body.max_tokens, 512);
  assert.equal(body.max_completion_tokens, undefined);
  assert.equal(body.messages.length, 2);

  const types = events.map((e) => e.type);
  assert.deepEqual(types, ["start", "meta", "content", "content", "content", "finish", "usage"]);
  assert.equal(events.find((e) => e.type === "meta").model, "doubao-seed-2-0-lite-260428");
  assert.equal(events.filter((e) => e.type === "content").map((e) => e.text).join(""), "您好，很高兴为您服务。");
  assert.equal(events.find((e) => e.type === "finish").finishReason, "stop");
  assert.equal(events.find((e) => e.type === "usage").usage.total_tokens, 54);
});

test("chatStream: 汇总结果 + formatUsage 输出", async () => {
  const fetchImpl = async () => sseResponse(arkSSE());
  const chunks = [];
  const r = await chatStream(
    { apiKey: API_KEY, messages: [{ role: "user", content: "hi" }], fetchImpl },
    { onContent: (t) => chunks.push(t) },
  );
  assert.equal(r.content, "您好，很高兴为您服务。");
  assert.equal(chunks.join(""), r.content);
  assert.equal(r.reasoning, "");
  assert.equal(r.finishReason, "stop");
  assert.equal(r.model, "doubao-seed-2-0-lite-260428");
  const text = formatUsage(r.usage, { model: r.model });
  assert.match(text, /prompt_tokens\s*: 42/);
  assert.match(text, /completion_tokens: 12/);
  assert.match(text, /total_tokens\s*: 54/);
  assert.match(text, /reasoning_tokens: 0/);
  assert.doesNotMatch(text, /⚠/);
});

test("formatUsage: reasoning_tokens > 0 时给出思考未关闭的警告；usage 缺失时提示", () => {
  const warn = formatUsage({ prompt_tokens: 1, completion_tokens: 110, total_tokens: 111, completion_tokens_details: { reasoning_tokens: 109 } });
  assert.match(warn, /⚠ reasoning_tokens > 0/);
  assert.match(formatUsage(null), /未收到 usage/);
});

test("thinking: null 时不发该字段；max_tokens 与 max_completion_tokens 互斥", async () => {
  let body;
  const fetchImpl = async (_u, init) => {
    body = JSON.parse(init.body);
    return sseResponse(arkSSE());
  };
  await chatStream({ apiKey: API_KEY, messages: [{ role: "user", content: "hi" }], fetchImpl, thinking: null, maxCompletionTokens: 300 });
  assert.equal("thinking" in body, false);
  assert.equal(body.max_completion_tokens, 300);

  const gen = streamChatCompletion({ apiKey: API_KEY, messages: [{ role: "user", content: "hi" }], fetchImpl, maxTokens: 1, maxCompletionTokens: 2 });
  await assert.rejects(() => gen.next(), /不能同时设置/);
});

test("role 校验：developer 被本地拒绝，不会发请求", async () => {
  let called = false;
  const fetchImpl = async () => {
    called = true;
    return sseResponse(arkSSE());
  };
  const gen = streamChatCompletion({ apiKey: API_KEY, messages: [{ role: "developer", content: "x" }], fetchImpl });
  await assert.rejects(() => gen.next(), /developer/);
  assert.equal(called, false);
});

test("缺少 API Key 直接抛错", async () => {
  const saved = process.env.ARK_API_KEY;
  delete process.env.ARK_API_KEY;
  try {
    const gen = streamChatCompletion({ messages: [{ role: "user", content: "hi" }], fetchImpl: async () => sseResponse(arkSSE()) });
    await assert.rejects(() => gen.next(), /ARK_API_KEY/);
  } finally {
    if (saved !== undefined) process.env.ARK_API_KEY = saved;
  }
});

test("401 AuthenticationError：不重试，解析 code / Request id / hint", async () => {
  let calls = 0;
  const fetchImpl = async () =>
    (calls++, jsonErrorResponse(401, {
      code: "AuthenticationError",
      message: "The API key or AK/SK in the request is missing or invalid. Request id: 0217abcdef",
      param: "",
      type: "Unauthorized",
    }));
  const gen = streamChatCompletion({ apiKey: API_KEY, messages: [{ role: "user", content: "hi" }], fetchImpl, maxRetries: 2 });
  await assert.rejects(
    () => gen.next(),
    (err) => {
      assert.ok(err instanceof ArkApiError);
      assert.equal(err.status, 401);
      assert.equal(err.code, "AuthenticationError");
      assert.equal(err.requestId, "0217abcdef");
      assert.equal(err.retryable, false);
      assert.match(err.hint, /方舟 API Key/);
      return true;
    },
  );
  assert.equal(calls, 1);
});

test("404 ModelNotOpen 给出「开通管理」提示；空 body 404 不崩", async () => {
  const gen1 = streamChatCompletion({
    apiKey: API_KEY,
    messages: [{ role: "user", content: "hi" }],
    fetchImpl: async () => jsonErrorResponse(404, { code: "ModelNotOpen", message: "Your account has not activated the model. Request id: 1", param: "", type: "NotFound" }),
  });
  await assert.rejects(() => gen1.next(), (e) => e instanceof ArkApiError && /开通管理/.test(e.hint));

  const gen2 = streamChatCompletion({
    apiKey: API_KEY,
    messages: [{ role: "user", content: "hi" }],
    fetchImpl: async () => new Response("", { status: 404 }),
  });
  await assert.rejects(() => gen2.next(), (e) => e instanceof ArkApiError && e.status === 404 && e.code === "");
});

test("429 限流：退避后重试并成功（第 2 次拿到流）", async () => {
  let calls = 0;
  const fetchImpl = async () => {
    calls++;
    if (calls === 1) {
      return jsonErrorResponse(
        429,
        { code: "ModelAccountRpmRateLimitExceeded", message: "rate limited. Request id: r1", param: "", type: "TooManyRequests" },
        { "Retry-After": "0.01" },
      );
    }
    return sseResponse(arkSSE());
  };
  const r = await chatStream({ apiKey: API_KEY, messages: [{ role: "user", content: "hi" }], fetchImpl, maxRetries: 2 });
  assert.equal(calls, 2);
  assert.equal(r.content, "您好，很高兴为您服务。");
});

test("429 QuotaExceeded（额度耗尽）不重试", async () => {
  let calls = 0;
  const fetchImpl = async () =>
    (calls++, jsonErrorResponse(429, { code: "QuotaExceeded", message: "exhausted its free trial quota. Request id: q1", param: "", type: "TooManyRequests" }));
  const gen = streamChatCompletion({ apiKey: API_KEY, messages: [{ role: "user", content: "hi" }], fetchImpl, maxRetries: 2 });
  await assert.rejects(() => gen.next(), (e) => e instanceof ArkApiError && e.code === "QuotaExceeded" && e.retryable === false);
  assert.equal(calls, 1);
});

test("流中途返回 error 事件：抛 ArkApiError(midStream)，且不重试，已收内容保留", async () => {
  let calls = 0;
  const fetchImpl = async () => {
    calls++;
    const base = { id: "x", model: "doubao-seed-2-0-lite-260428", object: "chat.completion.chunk", usage: null };
    const sse =
      `data: ${JSON.stringify({ ...base, choices: [{ delta: { content: "部分", role: "assistant" }, index: 0 }] })}\n\n` +
      `data: ${JSON.stringify({ error: { code: "InternalServiceError", message: "boom. Request id: m1" } })}\n\n`;
    return sseResponse(sse);
  };
  const got = [];
  await assert.rejects(
    () =>
      chatStream({ apiKey: API_KEY, messages: [{ role: "user", content: "hi" }], fetchImpl, maxRetries: 2 }, { onContent: (t) => got.push(t) }),
    (e) => e instanceof ArkApiError && e.midStream === true && e.retryable === false && e.code === "InternalServiceError",
  );
  assert.equal(calls, 1);
  assert.deepEqual(got, ["部分"]);
});

test("没收到 [DONE] 就断流：产出 warning 而不是静默", async () => {
  const fetchImpl = async () => {
    const base = { id: "x", model: "doubao-seed-2-0-lite-260428", object: "chat.completion.chunk", usage: null };
    return sseResponse(`data: ${JSON.stringify({ ...base, choices: [{ delta: { content: "半截", role: "assistant" }, index: 0 }] })}\n\n`);
  };
  const r = await chatStream({ apiKey: API_KEY, messages: [{ role: "user", content: "hi" }], fetchImpl });
  assert.equal(r.content, "半截");
  assert.equal(r.usage, null);
  assert.ok(r.warnings.some((w) => /\[DONE\]/.test(w)));
});

test("空闲超时：chunk 之间停顿超过 idleTimeoutMs 抛 ArkTimeoutError", async () => {
  const fetchImpl = async (_u, init) => {
    const base = { id: "x", model: "doubao-seed-2-0-lite-260428", object: "chat.completion.chunk", usage: null };
    const enc = new TextEncoder();
    const body = new ReadableStream({
      start(c) {
        c.enqueue(enc.encode(`data: ${JSON.stringify({ ...base, choices: [{ delta: { content: "a", role: "assistant" }, index: 0 }] })}\n\n`));
        // 之后不再产出，等待外部 abort
        init.signal.addEventListener("abort", () => {
          try {
            c.error(init.signal.reason);
          } catch {
            /* already closed */
          }
        });
      },
    });
    return new Response(body, { status: 200 });
  };
  await assert.rejects(
    () => chatStream({ apiKey: API_KEY, messages: [{ role: "user", content: "hi" }], fetchImpl, idleTimeoutMs: 30 }),
    (e) => e.name === "ArkTimeoutError" && e.phase === "流式空闲",
  );
});

test("外部 AbortSignal 取消：抛出调用方的 reason", async () => {
  const ac = new AbortController();
  const fetchImpl = async (_u, init) => {
    const body = new ReadableStream({
      start(c) {
        init.signal.addEventListener("abort", () => c.error(init.signal.reason));
      },
    });
    return new Response(body, { status: 200 });
  };
  const p = chatStream({ apiKey: API_KEY, messages: [{ role: "user", content: "hi" }], fetchImpl, signal: ac.signal });
  setTimeout(() => ac.abort(new Error("user-cancel")), 10);
  await assert.rejects(p, /user-cancel/);
});

test("baseURL 指向套餐入口时给出 warning（但不阻止）", async () => {
  const r = await chatStream({
    apiKey: API_KEY,
    baseURL: "https://ark.cn-beijing.volces.com/api/plan/v3",
    model: "doubao-seed-2.0-lite",
    messages: [{ role: "user", content: "hi" }],
    fetchImpl: async () => sseResponse(arkSSE({ model: "doubao-seed-2-0-lite-260215" })),
  });
  assert.ok(r.warnings.some((w) => /套餐入口/.test(w)));
  assert.equal(r.model, "doubao-seed-2-0-lite-260215");
});
