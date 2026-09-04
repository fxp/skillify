/**
 * Minimal, dependency-free client for the Volcengine Ark (火山方舟) standard
 * OpenAI-compatible Chat Completions API, with SSE streaming support.
 *
 * Only relies on Node.js >= 18 built-ins (global fetch, AbortController,
 * TextDecoder, Web Streams).
 */

export const DEFAULT_BASE_URL = 'https://ark.cn-beijing.volces.com/api/v3';

/** Error thrown for non-2xx HTTP responses from Ark. */
export class ArkApiError extends Error {
  /**
   * @param {string} message
   * @param {{status:number, code?:string, type?:string, requestId?:string, body?:unknown}} info
   */
  constructor(message, info) {
    super(message);
    this.name = 'ArkApiError';
    this.status = info.status;
    this.code = info.code;
    this.type = info.type;
    this.requestId = info.requestId;
    this.body = info.body;
  }
}

/**
 * Parse an SSE byte stream into JSON event payloads.
 * Handles: chunk boundaries splitting a line, CRLF, multi-line `data:` fields,
 * comment lines (`: keep-alive`), and the terminal `data: [DONE]` sentinel.
 *
 * @param {ReadableStream<Uint8Array>} body
 * @returns {AsyncGenerator<any>}
 */
export async function* parseSseJson(body) {
  const decoder = new TextDecoder('utf-8');
  const reader = body.getReader();
  let buffer = '';
  let dataLines = [];

  const flushEvent = () => {
    if (dataLines.length === 0) return undefined;
    const data = dataLines.join('\n');
    dataLines = [];
    return data;
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let newlineIdx;
      while ((newlineIdx = buffer.indexOf('\n')) !== -1) {
        let line = buffer.slice(0, newlineIdx);
        buffer = buffer.slice(newlineIdx + 1);
        if (line.endsWith('\r')) line = line.slice(0, -1);

        if (line === '') {
          const data = flushEvent();
          if (data === undefined) continue;
          if (data === '[DONE]') return;
          yield safeJsonParse(data);
          continue;
        }
        if (line.startsWith(':')) continue; // SSE comment / keep-alive
        if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).replace(/^ /, ''));
        }
        // `event:`, `id:`, `retry:` fields are ignored – Ark only uses `data:`.
      }
    }
    // Flush anything left without a trailing blank line.
    buffer += decoder.decode();
    if (buffer.trim().startsWith('data:')) {
      dataLines.push(buffer.trim().slice(5).replace(/^ /, ''));
    }
    const tail = flushEvent();
    if (tail !== undefined && tail !== '[DONE]') yield safeJsonParse(tail);
  } finally {
    reader.releaseLock();
  }
}

function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch (err) {
    throw new Error(`Malformed SSE JSON payload from Ark: ${text.slice(0, 200)}`);
  }
}

const RETRYABLE_STATUS = new Set([408, 409, 425, 429, 500, 502, 503, 504]);

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(t);
        reject(signal.reason ?? new Error('aborted'));
      },
      { once: true },
    );
  });
}

/**
 * Stream a chat completion from Ark.
 *
 * @param {object} opts
 * @param {string} opts.apiKey                Ark API key (Bearer token).
 * @param {string} opts.model                 Model ID (e.g. doubao-seed-2-0-lite-260215) or Endpoint ID (ep-xxx).
 * @param {Array<{role:string, content:string}>} opts.messages
 * @param {string} [opts.baseUrl]
 * @param {number} [opts.temperature]
 * @param {number} [opts.maxTokens]
 * @param {boolean} [opts.disableThinking=true]  Sends `thinking: {type:'disabled'}`.
 * @param {number} [opts.timeoutMs=60000]      Time budget for the whole request (connect + full stream).
 * @param {number} [opts.maxRetries=2]         Retries for transient failures *before* any bytes are received.
 * @param {AbortSignal} [opts.signal]
 * @returns {AsyncGenerator<{type:'delta', text:string} | {type:'reasoning', text:string} | {type:'finish', reason:string} | {type:'usage', usage:object} | {type:'meta', id:string, model:string, requestId?:string}>}
 */
export async function* streamChatCompletion(opts) {
  const {
    apiKey,
    model,
    messages,
    baseUrl = DEFAULT_BASE_URL,
    temperature,
    maxTokens,
    disableThinking = true,
    timeoutMs = 60_000,
    maxRetries = 2,
    signal,
  } = opts;

  if (!apiKey) throw new Error('apiKey is required');
  if (!model) throw new Error('model is required');
  if (!Array.isArray(messages) || messages.length === 0) throw new Error('messages must be a non-empty array');

  const url = `${baseUrl.replace(/\/+$/, '')}/chat/completions`;

  const payload = {
    model,
    messages,
    stream: true,
    // Ask Ark to append a final chunk carrying token usage (OpenAI-compatible).
    stream_options: { include_usage: true },
  };
  if (temperature !== undefined) payload.temperature = temperature;
  if (maxTokens !== undefined) payload.max_tokens = maxTokens;
  if (disableThinking) payload.thinking = { type: 'disabled' };

  const controller = new AbortController();
  const onOuterAbort = () => controller.abort(signal?.reason);
  signal?.addEventListener('abort', onOuterAbort, { once: true });
  const timer = setTimeout(() => controller.abort(new Error(`Ark request timed out after ${timeoutMs} ms`)), timeoutMs);

  try {
    let response;
    for (let attempt = 0; ; attempt++) {
      try {
        response = await fetch(url, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${apiKey}`,
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
          },
          body: JSON.stringify(payload),
          signal: controller.signal,
        });
      } catch (err) {
        if (controller.signal.aborted) throw controller.signal.reason ?? err;
        if (attempt < maxRetries) {
          await sleep(backoffMs(attempt), controller.signal);
          continue;
        }
        throw err;
      }

      if (response.ok) break;

      const requestId = response.headers.get('x-request-id') ?? response.headers.get('x-client-request-id') ?? undefined;
      const rawBody = await response.text().catch(() => '');
      let parsed;
      try {
        parsed = rawBody ? JSON.parse(rawBody) : undefined;
      } catch {
        parsed = undefined;
      }
      const apiErr = parsed?.error ?? {};
      const err = new ArkApiError(
        `Ark API ${response.status}${apiErr.code ? ` [${apiErr.code}]` : ''}: ${apiErr.message ?? (rawBody.slice(0, 300) || response.statusText)}`,
        { status: response.status, code: apiErr.code, type: apiErr.type, requestId, body: parsed ?? rawBody },
      );

      if (RETRYABLE_STATUS.has(response.status) && attempt < maxRetries) {
        const retryAfter = Number(response.headers.get('retry-after'));
        await sleep(Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter * 1000 : backoffMs(attempt), controller.signal);
        continue;
      }
      throw err;
    }

    if (!response.body) throw new Error('Ark response has no body');

    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.includes('text/event-stream')) {
      // Server ignored `stream: true` (or returned JSON error with 200). Surface it clearly.
      const text = await response.text();
      throw new Error(`Expected text/event-stream from Ark but got "${contentType}": ${text.slice(0, 300)}`);
    }

    let metaEmitted = false;
    let usageEmitted = false;

    for await (const chunk of parseSseJson(response.body)) {
      // Ark may put an error object inside the stream body.
      if (chunk?.error) {
        throw new ArkApiError(`Ark stream error${chunk.error.code ? ` [${chunk.error.code}]` : ''}: ${chunk.error.message ?? ''}`, {
          status: 200,
          code: chunk.error.code,
          type: chunk.error.type,
          body: chunk,
        });
      }

      if (!metaEmitted && chunk?.id) {
        metaEmitted = true;
        yield {
          type: 'meta',
          id: chunk.id,
          model: chunk.model,
          requestId: response.headers.get('x-request-id') ?? undefined,
        };
      }

      const choice = Array.isArray(chunk?.choices) ? chunk.choices[0] : undefined;
      if (choice) {
        const delta = choice.delta ?? {};
        // Ark-specific field: only present when thinking is enabled. We still
        // route it separately so it never leaks into the customer-facing answer.
        if (typeof delta.reasoning_content === 'string' && delta.reasoning_content.length > 0) {
          yield { type: 'reasoning', text: delta.reasoning_content };
        }
        if (typeof delta.content === 'string' && delta.content.length > 0) {
          yield { type: 'delta', text: delta.content };
        }
        if (choice.finish_reason) {
          yield { type: 'finish', reason: choice.finish_reason };
        }
      }

      // Usage arrives on the final chunk (choices: []) when include_usage is set.
      if (chunk?.usage && !usageEmitted) {
        usageEmitted = true;
        yield { type: 'usage', usage: chunk.usage };
      }
    }
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onOuterAbort);
  }
}

function backoffMs(attempt) {
  const base = 500 * 2 ** attempt;
  return base + Math.floor(Math.random() * 250);
}
