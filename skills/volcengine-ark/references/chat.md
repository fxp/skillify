# 火山方舟 Chat Completions（对话）API 全家桶

本文覆盖 `POST /api/v3/chat/completions` 的完整请求 / 响应字段，以及建立在它之上的流式输出、深度思考、结构化输出、Function Calling、续写模式、上下文缓存（含 Context API 与 `X-Prompt-Cache-Id`）和分词 API。多模态输入（图片 / 视频 / 文档 / 音频理解）、Files API、GUI Agent 见 `multimodal-input.md`，本文只保留字段占位。鉴权与 Base URL 见 `auth.md`。

> **验证范围说明**：文中标 **已用真实 API 验证（2026-09-04，Agent Plan Medium）** 的结论全部来自 **Agent Plan 入口 `/api/plan/v3`**（专属 Key）。标准入口 `/api/v3` 与 Coding Plan `/api/coding/v3` 没有 Key，**未实测**；写"标准入口预期相同"处均为推断。仍标 **（文档原文，未实测）** 的行为描述来自文档。

## 目录

1. [三套入口与本文 endpoint 可用性](#1-三套入口与本文-endpoint-可用性)
2. [我想发一次对话请求：Chat Completions](#2-我想发一次对话请求chat-completions)
   - 2.1 请求体字段表 · 2.2 `messages` 与 role · 2.3 响应对象 · 2.4 `usage`
3. [我想流式输出（SSE）](#3-我想流式输出sse)
4. [我想控制深度思考](#4-我想控制深度思考)
5. [我想让模型输出 JSON：结构化输出（beta）](#5-我想让模型输出-json结构化输出beta)
6. [我想让模型调用我的函数：Function Calling](#6-我想让模型调用我的函数function-calling)
7. [我想预填 assistant 让模型接着写：续写模式](#7-我想预填-assistant-让模型接着写续写模式)
8. [我想省输入 token：上下文缓存选型](#8-我想省输入-token上下文缓存选型)
   - 8.1 隐式缓存 + `X-Prompt-Cache-Id` · 8.2 Context API（创建缓存 + 缓存对话） · 8.3 Responses API 显式缓存（指引）
9. [我想数 token：分词 API](#9-我想数-token分词-api)
10. [提示词工程中与 API 相关的两条](#10-提示词工程中与-api-相关的两条)
11. [来源页面](#11-来源页面)

---

## 1. 三套入口与本文 endpoint 可用性

| endpoint | 标准 API `https://ark.cn-beijing.volces.com/api/v3` | Coding Plan `…/api/coding/v3` | Agent Plan `…/api/plan/v3` |
|---|---|---|---|
| `POST /chat/completions` | ✅ 文档主体 | ✅（auth.md：AI 编程工具通过 OpenAI 协议接入即走此路径） | ✅ **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：200，`model: doubao-seed-2.0-lite` → 响应 `"model":"doubao-seed-2-0-lite-260215"` |
| `POST /context/create`、`POST /context/chat/completions` | ✅ | ⚠ 文档未说明 | ❌ **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`POST /api/plan/v3/context/create` 返回 **404**（空 body）——Context API 在 Plan 入口不存在 |
| `POST /tokenization` | ✅ | ⚠ 文档未说明 | ❌ **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`POST /api/plan/v3/tokenization` 返回 **404**（空 body） |
| Header `X-Prompt-Cache-Id` | ✅（doubao-seed-2.0 及之后） | ⚠ 文档未说明 | ✅ **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：带 `X-Prompt-Cache-Id: skill-probe-1` 请求 200、不报错（单次 `cached_tokens: 0`，无法证明命中） |

同一轮实测里 `GET /api/plan/v3/models`、`GET /api/plan/v3/files` 也是 404：Plan 入口只暴露推理类 endpoint。

`model` 字段怎么填（来自 auth.md，所有小节通用）：

- 标准入口：带日期版本的 **Model ID**（如 `doubao-seed-2-1-pro-260628`）或推理接入点 **Endpoint ID**（`ep-xxxx`）。Access Key 签名鉴权时必须填 Endpoint ID。
- Coding / Agent Plan 入口：小写 **Model Name**（如 `doubao-seed-2.1-turbo`、`glm-5.3`、`deepseek-v4-pro`、`kimi-k2.7-code`），不要填带日期的 Model ID。Key：Coding Plan 用方舟 API Key（`ARK_API_KEY`），Agent Plan 用专属 Key（`ARK_AGENT_PLAN_API_KEY`）。
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Plan 入口 `model` 的真实解析（详见 `models.md` §1.1）：
  - Model Name `doubao-seed-2.0-lite` → 实际服务 `doubao-seed-2-0-lite-260215`（不是模型列表最新的 `260428`）；`doubao-seed-2.0-mini` → `doubao-seed-2-0-mini-260215`。
  - 填带日期 Model ID `doubao-seed-2-0-lite-260428` → **200 但响应 `model` 仍是 `doubao-seed-2-0-lite-260215`**：Plan 入口接受 Model ID 却**静默忽略版本号**，按 Name 路由。不要靠 Model ID 锁版本。
  - `model: "auto"` → **404** `{"error":{"code":"UnsupportedModel","message":"The requested model does not support the agent plan feature. Please refer to the documentation at https://www.volcengine.com/docs/82379/2366394 to select a compatible model. ..."}}`。要用智能调度只能填 `ark-code-latest`（实测 200，响应 `"model":"auto"`，控制台选的是 Auto）。
  - 套餐外模型（`doubao-seed-2.1-pro`）、老 Model ID（`doubao-seed-1-8-251228`）同样 404 UnsupportedModel（同一文案）。
- Plan 入口下本文各参数的可用性——**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`thinking`（第 4 节）、`reasoning_effort`（4.2）、`max_tokens` / `max_completion_tokens`（2.1）、`response_format: json_schema`（第 5 节）、`tools` + 强制 `tool_choice`（第 6 节）、`stream` + `stream_options.include_usage`（第 3 节）均生效；`service_tier: fast` 报 400（2.1）。`logprobs` / `logit_bias` / `stop` 未测。`glm-5.3` 默认开思考且 `thinking.disabled` 报 400（4.1）。

所有入口 HTTP 头相同：`Authorization: Bearer <key>`、`Content-Type: application/json`。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Agent Plan 专属 Key 打 `/api/v3` 或 `/api/coding/v3` 都是 **401** `{"error":{"code":"AuthenticationError","message":"The API key or AK/SK in the request is missing or invalid. ...","param":"","type":"Unauthorized"}}`——Key 与入口严格绑定，错的是鉴权而不是"套餐不支持"。

---

## 2. 我想发一次对话请求：Chat Completions

### Chat Completions

**Endpoint**: `POST /api/v3/chat/completions`（Plan 入口：`/api/coding/v3/chat/completions`、`/api/plan/v3/chat/completions`）

**用途**: 发送消息列表（文本，或含图片 / 视频 / 音频 / 文件的多模态内容），模型生成下一条 assistant 消息。同一个 endpoint 承载本文全部能力（流式、思考、JSON、工具、续写）；上下文缓存对话走 `/context/chat/completions`（第 8 节）。

#### 2.1 请求体字段表（文档 2026-08-28 版，逐字段核对）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | ✅ | — | Model ID 或 Endpoint ID（标准入口）；小写 Model Name（Plan 入口）。 |
| `messages` | object[] | ✅ | — | 消息列表，见 2.2。 |
| `stream` | boolean | | `false` | `true` 时按 SSE 逐块返回，以 `data: [DONE]` 结束。见第 3 节。 |
| `stream_options` | object | | `null` | 仅 `stream=true` 时有效。子字段 `include_usage`（boolean，默认 `false`：`[DONE]` 前追加一个 `choices=[]`、带完整 `usage` 的 chunk）、`chunk_include_usage`（boolean，默认 `false`：每个 chunk 的 `usage` 带截至该 chunk 的累计用量）。 |
| `thinking` | object | | 因模型而异 | `thinking.type`：`enabled`（强制先思考）/ `disabled`（直接回答）/ `auto`（模型自判，文档只列出 `doubao-seed-1-6-250615` 支持）。见第 4 节。 |
| `reasoning_effort` | string | | 因模型而异（`high` 或 `medium`） | 思考深度 7 档：`none` / `minimal` / `low` / `medium` / `high` / `xhigh` / `max`，各模型有映射规则，见第 4 节。 |
| `max_tokens` | integer | | `4096` | 文档：**回答**最大长度（不含思维链）。范围因模型而异。总输出还受 context window 限制。**已用真实 API 验证（2026-09-04，Agent Plan Medium）：各模型口径不一致，开思考一律用 `max_completion_tokens`。** 豆包 `doubao-seed-2.0-lite` + `max_tokens: 64` 且思考开 → `completion_tokens: 110`（`reasoning_tokens: 109` + 回答 1），与文档一致、不限制思维链；但 `kimi-k3` + `max_tokens: 64` → `finish_reason: "length"`、`content: ""`、`reasoning_tokens: 61`、`completion_tokens: 64`——**kimi-k3 把思维链算进 `max_tokens`**，回答被截空。去掉 `max_tokens`、改 `max_completion_tokens: 400` 后正常返回 `content: "2"`。 |
| `max_completion_tokens` | integer | | — | **回答 + 思维链**最大长度，范围 `[1, 65536]`。设置后 `max_tokens` 默认值失效；**不可与 `max_tokens` 同时设置**。支持模型见深度思考文档。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Plan 入口对 `kimi-k3` 生效（见上行）。 |
| `response_format` | object | | `{"type":"text"}` | `type`：`text` / `json_object` / `json_schema`。`json_schema` 子对象：`name`（必填）、`schema`（必填）、`description`、`strict`（默认 `false`）。beta。见第 5 节。 |
| `tools` | object[] | | `null` | 工具列表，每项 `{"type":"function","function":{"name","description","parameters","strict"}}`。见第 6 节。 |
| `tool_choice` | string / object | | 无工具时 `none`，有工具时 `auto` | `none` / `auto` / `required`，或 `{"type":"function","function":{"name":"..."}}` 强制指定。支持 `doubao-seed-1.6` 及之后系列。 |
| `parallel_tool_calls` | boolean | | `true` | `false` 时最多返回 1 个待调用工具（仅 `doubao-seed-1.6` 及之后模型支持 `false`；`true` 全模型通用）。 |
| `temperature` | number | | `1.0` | 范围 `[0, 2]`。`doubao-seed-2-0-pro-260215`、`doubao-seed-2-0-lite-260215` 固定为 `1`，传值被忽略。 |
| `top_p` | number | | `0.7` | 范围 `[0, 1]`。`doubao-seed-2-0-pro-260215`、`doubao-seed-2-0-lite-260215`、`doubao-seed-1-8-251228` 固定为 `0.95`，传值被忽略。建议只调 `temperature` 或 `top_p` 之一。 |
| `frequency_penalty` | number | | `0.0` | 范围 `[-2.0, 2.0]`。**`doubao-seed-1.8` 及后续系列不支持**。 |
| `presence_penalty` | number | | `0.0` | 范围 `[-2.0, 2.0]`。**`doubao-seed-1.8` 及后续系列不支持**。 |
| `stop` | string / string[] | | `null` | 最多 4 个停止词，命中即停且不输出该词。**深度思考模型不支持**。 |
| `logprobs` | boolean | | `false` | 返回每个输出 token 的对数概率。**深度思考模型不支持**。 |
| `top_logprobs` | integer | | `0` | 范围 `[0, 20]`，仅 `logprobs=true` 时可设。**深度思考模型不支持**。 |
| `logit_bias` | object | | `null` | `{"<token_id>": bias}`，bias 范围 `[-100, 100]`；token id 用分词 API 获取。**深度思考模型不支持**。 |
| `service_tier` | string | | `auto` | `auto`：优先用 TPM 保障包额度，无则降级常规；`fast`：优先用低延迟限流配额，无则降级常规；`default`：只用常规模式。均以 `model` 指定的接入点为单位。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Plan 入口传 `service_tier: "fast"` → **400** `{"error":{"code":"InvalidParameter","message":"The parameter `service_tier` specified in the request are not valid: fast service tier does not support coding plan. ...","param":"service_tier","type":"BadRequest"}}`（Agent Plan 入口报的却是 "coding plan" 文案）。Plan 入口不传时响应回 `"service_tier":"default"`。标准入口未测。 |
| `metadata` | — | | — | ⚠ 文档未说明（Chat API 参数表中没有该字段）。 |
| `prompt_cache_key` | — | | — | ⚠ 文档未说明（该字段只出现在 Responses API 事件文档中；Chat API 用 Header `X-Prompt-Cache-Id`，见 8.1）。 |
| `caching` / `store` / `expire_at` / `previous_response_id` | — | | — | 不属于 Chat API；是 Responses API 显式缓存字段（8.3）。Chat 路线的显式缓存用 `context_id`（8.2）。 |
| `n` / `seed` / `user` | — | | — | ⚠ 文档未说明（参数表中没有）。 |

常用请求头（非 body）：

| Header | 用途 |
|---|---|
| `X-Client-Request-Id` | 自定义请求 ID，用于把客户端与方舟服务端日志串起来（提供给售后定位问题）。Chat API、批量 Chat API 支持。OpenAI SDK 用 `extra_headers={"X-Client-Request-Id": "..."}` 传。 |
| `X-Prompt-Cache-Id` | 隐式缓存路由亲和键，见 8.1。 |

#### 2.2 `messages` 与 role

文档列出的 role 只有 4 个：`system`、`user`、`assistant`、`tool`。**不支持 `developer`**。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`messages[0].role = "developer"` → **400** `{"error":{"code":"InvalidParameter","message":"The parameter `messages.role` specified in the request are not valid: invalid value: `developer`, supported values are: `system`, `assistant`, `user`, `tool`. ...","param":"","type":"BadRequest"}}`（Plan 入口实测；与 FAQ 文档原文一致，标准入口预期相同但未测）。用 OpenAI 新版 SDK / 工具接入时把 developer 消息改成 `system`。

| role | `content` | 其他字段 | 说明 |
|---|---|---|---|
| `system` | string 或多模态 object[] | `name` | 指令、人设、背景。 |
| `user` | string 或多模态 object[] | `name` | 多模态 part 类型：`text`（`text`）、`image_url`（`image_url.url` / `file_id` / `detail` / `image_pixel_limit`）、`video_url`（`video_url.url` / `file_id` / `fps`）、`input_audio`（`input_audio.data` / `url` / `file_id` / `format`）、`file`（`file.file_data` / `file_url` / `file_id` / `filename`，仅 PDF）。细节见 `multimodal-input.md`。 |
| `assistant` | string | `name`、`reasoning_content`、`encrypted_content`、`tool_calls[]` | 历史模型消息或续写预填。`content` 与 `tool_calls` 至少填一个。`tool_calls[]` 每项：`id`（必填）、`type: "function"`（必填）、`function.name`（必填）、`function.arguments`（必填，JSON 字符串）。 |
| `tool` | string（必填） | `tool_call_id`（必填）、`name` | 工具执行结果，`tool_call_id` 必须对应上一条 assistant 的 `tool_calls[].id`。 |

`assistant.reasoning_content` / `encrypted_content` 回传规则见 4.4。

**示例请求**

curl（标准入口）：

```bash
curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seed-2-1-pro-260628",
    "messages": [
      {"role": "system", "content": "你是 AI 人工智能助手"},
      {"role": "user", "content": "常见的十字花科植物有哪些？"}
    ],
    "thinking": {"type": "disabled"},
    "max_tokens": 1024
  }'
```

Coding Plan 入口只改两处：URL 换成 `https://ark.cn-beijing.volces.com/api/coding/v3/chat/completions`，`model` 换成小写 Model Name（如 `"doubao-seed-2.1-turbo"`）；Agent Plan 再把 Key 换成 `$ARK_AGENT_PLAN_API_KEY`、路径换 `/api/plan/v3`。

Python（`openai` SDK；方舟专有字段走 `extra_body`，自定义头走 `extra_headers`）：

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["ARK_API_KEY"],
    base_url="https://ark.cn-beijing.volces.com/api/v3",  # Agent Plan: .../api/plan/v3 + ARK_AGENT_PLAN_API_KEY
    timeout=1800,  # 文档建议深度思考场景 1800s 以上
)
completion = client.chat.completions.create(
    model="doubao-seed-2-1-pro-260628",
    messages=[
        {"role": "system", "content": "你是 AI 人工智能助手"},
        {"role": "user", "content": "常见的十字花科植物有哪些？"},
    ],
    max_tokens=1024,
    extra_body={"thinking": {"type": "disabled"}},
    extra_headers={"X-Client-Request-Id": "my-trace-id-001"},
)
msg = completion.choices[0].message
if getattr(msg, "reasoning_content", None):
    print("[思维链]", msg.reasoning_content)
print(msg.content)
print(completion.usage)
```

官方 SDK `volcenginesdkarkruntime.Ark(base_url=..., api_key=...)` 的 `client.chat.completions.create(...)` 直接接受 `thinking=`、`extra_headers=` 参数，底层同一 endpoint。

#### 2.3 响应对象（非流式）

```json
{
  "id": "0217657...", "object": "chat.completion", "created": 1765713048,
  "model": "doubao-seed-2-1-pro-260628", "service_tier": "default",
  "service_status": {"model_fallback": {"fallback_triggered": false, "original_model": "doubao-seed-2-1-pro-260628"}},
  "choices": [{
    "index": 0, "finish_reason": "stop", "logprobs": null, "moderation_hit_type": null,
    "message": {"role": "assistant", "content": "……", "reasoning_content": "……",
                "encrypted_content": "djF+…", "tool_calls": null}
  }],
  "usage": { "…见 2.4" }
}
```

| 字段 | 说明 |
|---|---|
| `object` | 固定 `chat.completion`（流式 chunk 为 `chat.completion.chunk`）。 |
| `model` | 实际使用的模型名称和版本。 |
| `service_tier` | 实际推理模式：`scale`（TPM 保障包）/ `default`（常规）/ `fast`（低延迟）。注意请求端写 `auto`，响应端回 `scale`。 |
| `service_status.model_fallback` | `fallback_triggered`（是否触发模型降级）、`original_model`（降级前指定的模型）。 |
| `choices[].finish_reason` | `stop`（自然结束或命中 `stop`）/ `length`（触发 `max_tokens`、`max_completion_tokens` 或 context window）/ `content_filter`（内容审核拦截）/ `tool_calls`（模型要调工具）。 |
| `choices[].message.content` | 回答正文。 |
| `choices[].message.reasoning_content` | 思维链（或思考摘要）。支持：`doubao-seed-1.8` 及后续、`deepseek-v4-pro`、`deepseek-v4-flash`、`deepseek-v3.2`。 |
| `choices[].message.encrypted_content` | 加密压缩后的思考原文，`doubao-seed-2-0-lite-260428` 及后续版本返回；工具调用多轮时需回传（4.4）。 |
| `choices[].message.tool_calls[]` | `id`、`type: "function"`、`function.name`、`function.arguments`（JSON 字符串，可能不合法 / 含幻觉参数，调用前必须校验）。 |
| `choices[].logprobs.content[]` | `token`、`logprob`、`bytes`（UTF-8 整数列表）、`top_logprobs[]`（同结构）。 |
| `choices[].moderation_hit_type` | `severe_violation` / `violence`。仅视觉理解模型、且接入点护栏方案设为 Basic 时返回。 |

#### 2.4 `usage`

```json
"usage": {
  "prompt_tokens": 42, "completion_tokens": 846, "total_tokens": 888,
  "prompt_tokens_details": {"cached_tokens": 0, "audio_tokens": 0, "audio_cached_tokens": 0},
  "completion_tokens_details": {"reasoning_tokens": 408}
}
```

- `prompt_tokens_details.cached_tokens`：命中缓存的输入 token（含文本、音频等所有类型）。判断隐式缓存是否命中：`> 0` 命中，`= 0` 未命中。
- `completion_tokens_details.reasoning_tokens`：思维链 token。开启 thinking summary 的模型此处仍是**原始**思考内容的 token 数，计费按原始思考算。
- 计费公式（上下文缓存文档）：`(prompt_tokens - cached_tokens) × 输入单价 + cached_tokens × 缓存输入单价 + completion_tokens × 输出单价`。

**注意事项**

- `max_tokens` 与 `max_completion_tokens` 互斥；文档口径前者只限回答，后者限回答 + 思维链——**但实测 kimi-k3 的 `max_tokens` 含思维链**（2.1 表 `max_tokens` 行），开思考时统一用 `max_completion_tokens`。
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Plan 入口 `doubao-seed-2-0-lite-260215` 的非流式响应里没有 `service_status`、没有 `encrypted_content`（260215 是明文思维链模型，与 4.4 一致），`reasoning_content` 直接是原文。
- 深度思考模型不支持 `stop`、`logprobs`、`top_logprobs`、`logit_bias`；`doubao-seed-1.8` 及后续不支持 `frequency_penalty`、`presence_penalty`。
- 非流式 + 深度思考极易超时且超时后仍计费；文档建议 timeout ≥ 30 分钟或改用流式（第 3 节）。Go SDK 无论流式与否都要设 30 分钟以上。
- `service_tier` 里的 TPM 保障包 / 低延迟配额都是**推理接入点**（`ep-`）的属性；直接用 Model ID 调用时是否有效 ⚠ 文档未说明。
- 使用 TPM 保障包（`service_tier` 命中 `scale`）时不支持结构化输出。

---

## 3. 我想流式输出（SSE）

同一 endpoint，`"stream": true`。响应 `Content-Type` 为 SSE，每个 chunk 一行 `data: {json}`，`object` 为 `chat.completion.chunk`，结束标志是单独一行 `data: [DONE]`。

**返回格式**（文档示例，思考模型）：

```text
data: {"choices":[{"delta":{"content":"","reasoning_content":"用户","role":"assistant"},"index":0}],"created":1765713048,"id":"0217…","model":"doubao-seed-2-1-pro-260628","service_tier":"default","object":"chat.completion.chunk","usage":null}
data: {"choices":[{"delta":{"content":"你","role":"assistant"},"index":0}],"created":1765713048,"id":"0217…","model":"doubao-seed-2-1-pro-260628","service_tier":"default","object":"chat.completion.chunk","usage":null}
data: {"choices":[{"delta":{"content":"","role":"assistant"},"finish_reason":"stop","index":0}],"created":1765713048,"id":"0217…","model":"doubao-seed-2-1-pro-260628","service_tier":"default","object":"chat.completion.chunk","usage":null}
data: [DONE]
```

`choices[].delta` 字段：`role`（固定 `assistant`）、`content`、`reasoning_content`、`encrypted_content`、`tool_calls[]`（比非流式多一个 `index`，用于拼接，见 6.4）。`finish_reason` 只在最后一个内容 chunk 出现。

**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`/api/plan/v3` + `doubao-seed-2.0-lite` + `stream: true` + `stream_options: {"include_usage": true}` 返回的就是上述格式——标准 SSE，`delta.reasoning_content` 逐 token 下发（每 chunk 同时带 `"content":""`、`"role":"assistant"`），每个 chunk `"usage":null` 直到末尾的 usage chunk。实测首两个 chunk 原样：

```text
data: {"choices":[{"delta":{"content":"","reasoning_content":"\n","role":"assistant"},"index":0}],"created":1788487468,"id":"0217…","model":"doubao-seed-2-0-lite-260215","service_tier":"default","object":"chat.completion.chunk","usage":null}
data: {"choices":[{"delta":{"content":"","reasoning_content":"用户","role":"assistant"},"index":0}],"created":1788487468,"id":"0217…","model":"doubao-seed-2-0-lite-260215","service_tier":"default","object":"chat.completion.chunk","usage":null}
```

**`usage` 在流式下的默认行为**（文档原文）：

- `glm-5-2-260617`、`deepseek-v4-pro-ga-260813`、`deepseek-v4-flash-ga-260731`：默认在输出结束前返回 usage。
- 其他模型：默认 `usage: null`。要拿用量必须 `"stream_options": {"include_usage": true}`，则 `[DONE]` 前多一个 `choices: []` 的 chunk 携带完整 `usage`。`chunk_include_usage: true` 则每个 chunk 都带累计用量。

**思考 + 流式的顺序**：先流 `reasoning_content`，思考结束后（`doubao-seed-2-0-lite-260428` 及后续）单独一个 chunk 携带完整 `encrypted_content`（此时 `content`、`reasoning_content` 均为空），再流 `content`。

**示例请求**

```bash
curl -N https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seed-2-1-pro-260628",
    "messages": [{"role": "user", "content": "常见的十字花科植物有哪些？"}],
    "stream": true,
    "stream_options": {"include_usage": true}
  }'
```

```python
stream = client.chat.completions.create(
    model="doubao-seed-2-1-pro-260628",
    messages=[{"role": "user", "content": "常见的十字花科植物有哪些？"}],
    stream=True,
    stream_options={"include_usage": True},
)
with stream:  # 文档建议：异常/中断时自动关闭连接，避免 socket 数据积压卡住
    for chunk in stream:
        if not chunk.choices:            # 最后的 usage chunk，choices 为空
            print("\nusage:", chunk.usage); continue
        delta = chunk.choices[0].delta
        print(getattr(delta, "reasoning_content", None) or "", end="", flush=True)
        print(delta.content or "", end="", flush=True)
```

**注意事项**

- 消费 chunk 前先判断 `chunk.choices` 是否为空（`include_usage` 的收尾 chunk 没有 choices）。
- 长思考场景建议调大 TTFT（首 token）与 TPOT（逐 token）超时；思考摘要模型包间延迟可能较高。
- Go SDK 必须用 `CreateChatCompletionStream`，用非流式方法拿不到流。

---

## 4. 我想控制深度思考

### 4.1 `thinking.type`

| 值 | 行为 |
|---|---|
| `enabled` | 强制先思考再回答，输出 `reasoning_content`。 |
| `disabled` | 关闭思考，直接回答。 |
| `auto` | 模型自判是否思考。文档仅列出 `doubao-seed-1-6-250615` 支持。 |

**默认全部为 `enabled`**、支持 `enabled`/`disabled` 的模型（文档 2026-08-19 列表）：`doubao-seed-evolving`、`doubao-seed-2-1-pro-260628`、`doubao-seed-2-1-turbo-260628`、`doubao-seed-2-0-lite-260428`、`doubao-seed-2-0-mini-260428`、`doubao-seed-2-0-pro-260215`、`doubao-seed-2-0-lite-260215`、`doubao-seed-2-0-mini-260215`、`doubao-seed-2-0-code-preview-260215`、`doubao-seed-1-8-251228`、`glm-5-2-260617`、`glm-4-7-251222`、`doubao-seed-character-260628`、`doubao-seed-code-preview-251028`、`doubao-seed-1-6-vision-250815`、`doubao-seed-1-6-251015`、`doubao-seed-1-6-flash-250828`、`doubao-seed-1-6-flash-250615`、`deepseek-v4-pro-ga-260813`、`deepseek-v4-flash-ga-260731`、`deepseek-v4-pro-260425`、`deepseek-v4-flash-260425`。`doubao-seed-1-6-250615` 额外支持 `auto`。

文档矛盾点（上表说 `glm-5-2-260617` 支持 `disabled`，Coding Plan 文档说 `glm-5.3` 不支持关闭）——**已用真实 API 验证（2026-09-04，Agent Plan Medium）：`glm-5.3` 实测不可关。** `/api/plan/v3` + `model: glm-5.3` + `thinking: {"type":"disabled"}` → **400** `{"error":{"code":"InvalidParameter","message":"thinking.type `disabled` is not supported by this model ...","type":"BadRequest"}}`。`glm-5-2-260617`（标准入口）未测，可能确实是版本差异。绕法见 4.2：`reasoning_effort: "low"` 实测 `reasoning_tokens: 0`。

**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`doubao-seed-2.0-lite`（→ `260215`）默认**开**思考（不传 `thinking` 时 `reasoning_content` 存在、`reasoning_tokens: 109`）；传 `thinking: {"type":"disabled"}` 生效（`reasoning_tokens: 0`、无 `reasoning_content`）。`doubao-seed-2.0-mini`（→ `260215`）同样可关。

### 4.2 `reasoning_effort`（思考深度）

7 档：`none`、`minimal`、`low`、`medium`、`high`、`xhigh`、`max`。所有支持模型都接受全部 7 档，但会按下表映射：

| 模型 | 默认 | 映射规则 |
|---|---|---|
| `doubao-seed-evolving`、`doubao-seed-2-1-pro-260628`、`doubao-seed-2-1-turbo-260628` | `high` | `minimal` → 关闭思考；`none` → `minimal`；`xhigh`/`max` → `high` |
| `doubao-seed-2-0-lite-260428`、`-mini-260428`、`-pro-260215`、`-lite-260215`、`-mini-260215`、`-code-preview-260215`、`doubao-seed-1-8-251228`、`doubao-seed-1-6-251015`、`doubao-seed-character-260628` | `medium` | 同上 |
| `glm-5-2-260617` | `high` | `none`/`minimal` → 关闭思考；`low`/`medium` → `high`；`xhigh` → `max` |
| `deepseek-v4-pro-ga-260813`、`deepseek-v4-flash-ga-260731` | `high` | `none`/`minimal` → 关闭；`medium` → `low`；`xhigh` → `high` |
| `deepseek-v4-pro-260425`、`deepseek-v4-flash-260425` | `high` | `minimal` → 关闭；`none` → `minimal`；`low`/`medium` → `high`；`xhigh` → `max` |

- `reasoning_effort` 只作用于原始思考内容，不影响思考摘要长度。
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**，`glm-5.3`（Plan 入口，标准入口的 `glm-5-2-260617` 未测；上表 glm 行"所有支持模型都接受全部 7 档"对 glm-5.3 不成立）：
  - `reasoning_effort: "low"` → 200，`reasoning_tokens: 0`、无 `reasoning_content`，`content: "2"`——**事实上相当于关掉了思考**，是 glm-5.3 唯一实测可用的"关思考"手段。
  - `reasoning_effort: "none"` → **400** `{"error":{"code":"InvalidParameter","message":"reasoning_effort `none` is not supported by this model ...","type":"BadRequest"}}`。
  - `thinking: {"type":"disabled"}` → 400（见 4.1）。
- ⚠ 文档未说明 `thinking.type` 与 `reasoning_effort` 同时传时谁优先（Chat API 页只说"关系详见深度思考文档"，该文档未给出优先级）。

### 4.3 思维链在响应的位置 · 思考摘要

- 非流式：`choices[0].message.reasoning_content`；流式：`choices[0].delta.reasoning_content`。
- **thinking summary**：`doubao-seed-evolving`、`doubao-seed-2-1-pro-260628`、`doubao-seed-2-1-turbo-260628`、`doubao-seed-2-0-lite-260428` 默认开启，`reasoning_content` 返回的是**摘要**而非原文，同时返回 `encrypted_content`（加密原文）。⚠ 文档未说明能否关闭摘要。
- `usage.completion_tokens_details.reasoning_tokens` 与计费按原始思考 token 算。

### 4.4 多轮对话 / 工具调用时回传思考内容

| 场景 | 做法 |
|---|---|
| 普通多轮对话，模型版本 `251228` 之前 | 剔除历史 `reasoning_content`，只留 `role` + `content`。 |
| 普通多轮对话，`doubao-seed-1.8` 及后续 | 可保留历史 `reasoning_content`，模型自判是否使用。 |
| 工具调用多轮，思考摘要模型（4.3 列表） | 把上一轮 assistant 消息的 `encrypted_content`（和 `reasoning_content`）原样回传。`encrypted_content` 优先级更高，回传时 `reasoning_content` 被忽略；被篡改则报 `Invalid signature`（文档原文，未实测）。不回传不会报错，但 agent 场景推理效果下降。 |
| 工具调用多轮，原始思考模型（`doubao-seed-2-0-*-260215/260428`、`doubao-seed-1-8-251228`） | 回传 `reasoning_content`。 |

`doubao-seed-1.8` 之前的模型在工具调用时直接丢弃思维链；1.8 及后续可能把历史思维链纳入推理，输入 token 会增加（未输入模型的思维链不计费）。

**示例**（关思考 + 限思考长度）：

```bash
curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{"model": "doubao-seed-2-1-pro-260628",
       "messages": [{"role": "user", "content": "深度思考模型与非深度思考模型区别"}],
       "reasoning_effort": "low", "max_completion_tokens": 2000}'
```

```python
completion = client.chat.completions.create(
    model="doubao-seed-2-1-pro-260628",
    messages=[{"role": "user", "content": "深度思考模型与非深度思考模型区别"}],
    reasoning_effort="low", max_completion_tokens=2000,   # 均为 openai SDK 原生参数
    # extra_body={"thinking": {"type": "enabled"}},       # 或显式开关
)
```

**注意事项**

- 深度思考模型不支持 `stop` / `logprobs` / `top_logprobs` / `logit_bias`。
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**，Plan 入口三款模型的思考默认值与开关（标准入口未测）：
  | 模型（Plan Name → 实际版本） | 默认 | `thinking.disabled` | 备注 |
  |---|---|---|---|
  | `doubao-seed-2.0-lite` → `260215` | 开（`reasoning_tokens: 109`） | 生效（`reasoning_tokens: 0`） | `max_tokens: 64` 不限思维链，`completion_tokens: 110` |
  | `doubao-seed-2.0-mini` → `260215` | 开 | 生效 | — |
  | `glm-5.3` | 开 | **400** | `reasoning_effort: low` → 0 思维链；`none` → 400 |
  | `kimi-k3` | 开（`reasoning_tokens: 61`） | 未测 | `max_tokens` **含思维链**，64 上限下回答被截空 `finish_reason: length`；用 `max_completion_tokens` |
- 续写模式（第 7 节）只在部分思考模型上可用；其他思考模型以 assistant 结尾时 `thinking` 字段失效。
- 提示词建议：给目标与场景信息，少写"分步思考"之类的过程指令，少用 system、直接放 `user`。

---

## 5. 我想让模型输出 JSON：结构化输出（beta）

| | `json_schema` | `json_object` |
|---|---|---|
| 保证合法 JSON | ✅ | ✅ |
| 可定义结构 | ✅ | ❌ |
| 官方推荐 | ✅（`json_object` 的演进版） | ❌ |
| 严格模式 | `json_schema.strict: true`，不支持的关键字会显式报错 | 不涉及 |
| 提示词要求 | 直接描述任务即可，不必再要求"输出 JSON" | **输入中必须包含字符串 `json`** |

`response_format` 结构：

```json
"response_format": {
  "type": "json_schema",
  "json_schema": {
    "name": "math_reasoning",
    "description": "可选",
    "strict": true,
    "schema": { "type": "object", "properties": {...}, "required": [...], "additionalProperties": false }
  }
}
```

**方舟支持的 JSON Schema 关键字**：`type`（integer/number/string/boolean/null/array/object）、`$ref`（仅 `#` 开头本地引用）、`$defs`、`const`、`enum`、`anyOf`、`oneOf`（不严格保证 exactly one）、`allOf`（不严格保证 all）；array：`prefixItems`、`items`、`unevaluatedItems`；object：`properties`、`required`、`additionalProperties`、`unevaluatedProperties`。无格式约束语义的关键字被忽略；明确不支持的关键字报错。

**限制**（文档原文）：

- beta，可用性随负载波动，谨慎上生产。
- 使用 TPM 保障包时不支持；`doubao-seed-1.8` 之前版本通过模型单元部署时不支持。
- 不要与 `frequency_penalty`、`presence_penalty` 同用。
- 字段按 schema 定义顺序输出；`strict: false` 时只保证合法 JSON、尽量贴近 schema，不校验不报错。
- 显式缓存（Responses API）链路中一旦前序轮次开了 `caching`，不能用 `json_schema`，只能用 `json_object`。
- 支持模型见"模型列表 → 结构化输出能力(beta)"；示例用 `doubao-seed-1-6-251015`。

**示例请求**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Authorization: Bearer $ARK_API_KEY" -H "Content-Type: application/json" \
  -d '{
  "model": "doubao-seed-1-6-251015",
  "messages": [{"role": "system", "content": "你是一位数学辅导老师。"},
               {"role": "user", "content": "使用中文解题: 8x + 9 = 32 and x + y = 1"}],
  "response_format": {"type": "json_schema", "json_schema": {"name": "math_reasoning", "strict": true,
    "schema": {"type": "object",
      "properties": {
        "steps": {"type": "array", "items": {"type": "object",
          "properties": {"explanation": {"type": "string"}, "output": {"type": "string"}},
          "required": ["explanation", "output"], "additionalProperties": false}},
        "final_answer": {"type": "string"}},
      "required": ["steps", "final_answer"], "additionalProperties": false}}},
  "thinking": {"type": "disabled"}
}'
```

```python
from pydantic import BaseModel

class Step(BaseModel):
    explanation: str
    output: str

class MathResponse(BaseModel):
    steps: list[Step]
    final_answer: str

completion = client.beta.chat.completions.parse(   # openai SDK 自动把 pydantic 转成 strict json_schema
    model="doubao-seed-1-6-251015",
    messages=[
        {"role": "system", "content": "你是一位数学辅导老师。"},
        {"role": "user", "content": "使用中文解题: 8x + 9 = 32 and x + y = 1"},
    ],
    response_format=MathResponse,
    extra_body={"thinking": {"type": "disabled"}},
)
print(completion.choices[0].message.parsed.model_dump_json(indent=2))

# json_object 模式：提示词里必须出现 "json"
completion = client.chat.completions.create(
    model="doubao-seed-1-6-251015",
    messages=[{"role": "user", "content": "常见的十字花科植物有哪些？json输出"}],
    response_format={"type": "json_object"},
    extra_body={"thinking": {"type": "disabled"}},
)
```

**注意事项**

- Schema 设计建议（文档附 2）：英文字段名 + `description`；避免无意义嵌套和过度 `$ref`；数字 / 布尔不要用 string 代替；枚举用 `enum`；所有字段进 `required` 并加 `"additionalProperties": false`。
- 输出仍可能因长度截断（`finish_reason: length`）而不完整，需校验。
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`/api/plan/v3` + `doubao-seed-2.0-lite` + `response_format: {"type":"json_schema", ...}` → 200，`content: "{\"answer\": 2}"` 合法 JSON，`finish_reason: "stop"`——Plan 入口 `json_schema` 生效。标准入口预期相同但未测。

---

## 6. 我想让模型调用我的函数：Function Calling

### 6.1 工具定义（`tools[]`）

```json
{
  "type": "function",
  "function": {
    "name": "get_current_weather",
    "description": "获取指定地点的天气信息，支持摄氏度和华氏度两种单位",
    "parameters": {
      "type": "object",
      "properties": {
        "location": {"type": "string", "description": "地点的位置信息，例如北京、上海"},
        "unit": {"type": "string", "enum": ["摄氏度", "华氏度"], "description": "温度单位"}
      },
      "required": ["location"]
    }
  }
}
```

- `function.name`、`description`、`parameters` 文档均标必填（Chat API 参数表中 `description`、`parameters` 未标必选，附录规范标"是"）；`parameters` 必须是合法 JSON Schema、`type` 必须为 `object`，参数名英文且不重复，字段名大小写敏感，支持类型 string / number / integer / boolean / object / array。
- `function.strict: true`（Strict 模式）：模型严格按 schema 生成参数。前提：`properties` 内所有字段都在 `required` 中；建议 `"additionalProperties": false`；可选字段用 `"type": ["string", "null"]` 表达。文档建议始终开启。
- 保持 `properties` 内字段顺序稳定，顺序变化会影响模型输出（文档最佳实践）。

### 6.2 控制参数

| 参数 | 说明 |
|---|---|
| `tool_choice` | `none` / `auto`（有工具时默认）/ `required`（必须调 ≥1 个工具）/ `{"type":"function","function":{"name":"get_current_weather"}}`。支持 `doubao-seed-1.6` 及之后。 |
| `parallel_tool_calls` | 默认 `true`，一次响应可含多个 `tool_calls`；`false` 最多 1 个（仅 `doubao-seed-1.6` 及之后支持 `false`）。DeepSeek R1 不支持该字段、默认自动并行（文档 FAQ）。 |

### 6.3 多轮回传流程

严格遵循 `assistant(含 tool_calls) → tool(每个 tool_call_id 一条) → assistant` 的顺序，不能跳过 `tool` 消息直接发新的 assistant / user；缺失会因 prefill 机制触发重复调用或流程中断（文档原文）。触发工具调用时，模型先输出 `content` 再输出 `tool_calls`，当轮 `content` 不能依赖工具结果。

**第一轮请求 / 响应**（`finish_reason: "tool_calls"`）：

```bash
curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seed-2-1-pro-260628",
    "messages": [{"role": "user", "content": "北京和上海今天的天气如何？"}],
    "tools": [{"type": "function", "function": {"name": "get_current_weather",
      "description": "获取指定地点的天气信息",
      "parameters": {"type": "object",
        "properties": {"location": {"type": "string", "description": "地点，例如北京"}},
        "required": ["location"]}}}]
  }'
```

```json
{"choices": [{"finish_reason": "tool_calls", "index": 0,
  "message": {"role": "assistant", "content": "", "reasoning_content": "……", "encrypted_content": "djF+…",
    "tool_calls": [
      {"id": "call_wiezxeyae8jzxl3jx8nhfgb5", "type": "function",
       "function": {"name": "get_current_weather", "arguments": " {\"location\": \"北京\"}"}},
      {"id": "call_…2", "type": "function",
       "function": {"name": "get_current_weather", "arguments": " {\"location\": \"上海\"}"}}]}}]}
```

**第二轮请求**：把上面整条 assistant 消息（含 `tool_calls`、`reasoning_content`、`encrypted_content`）原样追加，再为每个 `tool_calls[].id` 追加一条 `tool` 消息，`tools` 定义继续带上：

```python
import json

tools = [...]  # 同上
messages = [{"role": "user", "content": "北京和上海今天的天气如何？"}]

def get_current_weather(location, unit="摄氏度"):
    return f"{location}今天天气晴朗，温度 25 {unit}。"

for _ in range(10):  # 文档建议加轮次上限，防死循环
    completion = client.chat.completions.create(
        model="doubao-seed-2-1-pro-260628", messages=messages, tools=tools,
    )
    choice = completion.choices[0]
    if choice.finish_reason != "tool_calls":
        print(choice.message.content)
        break
    messages.append(choice.message.model_dump(exclude_none=True))  # 保留 reasoning_content / encrypted_content
    for tc in choice.message.tool_calls:
        args = json.loads(tc.function.arguments)  # 不合法时可用 json_repair.loads 容错
        result = get_current_weather(**args) if tc.function.name == "get_current_weather" else f"未知函数 {tc.function.name}"
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
```

工具执行失败时同样以 `role: tool` 回填错误信息，模型会据此回复。

### 6.4 流式下拼接 `tool_calls`

流式时 `delta.tool_calls[]` 分片到达，每片带 `index`；`id` / `function.name` 出现在首片，`function.arguments` 逐片追加：

```python
final_tool_calls = {}
with stream:
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            print(delta.content, end="")
        for tc in delta.tool_calls or []:
            if tc.index not in final_tool_calls:
                final_tool_calls[tc.index] = tc
            else:
                final_tool_calls[tc.index].function.arguments += tc.function.arguments or ""
```

**注意事项**

- 函数调用场景关闭 thinking 可提速（文档推荐）；速度敏感可选 `doubao-seed-2-0-mini` 系列。
- `arguments` 是字符串且"模型并不总是生成有效 JSON、可能虚构参数"，调用前必须校验。
- 上下文缓存对话 API（8.2）**不支持 `tools`**。
- Plan 入口下 `tools` / `tool_choice`——**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`/api/plan/v3` + `doubao-seed-2.0-lite`，对无关问题"讲个笑话"传 `tool_choice: {"type":"function","function":{"name":"get_weather"}}` → 200，`finish_reason: "tool_calls"`，`tool_calls[0].function = {"name":"get_weather","arguments":"{\"city\": \"济南\"}"}`（`id` 形如 `call_cg5z3a…`）。**强制 `tool_choice` 在方舟真的强制生效**——模型会编造参数完成调用（与某些厂商忽略强制指定不同），所以只在确定要调时才用它。标准入口预期相同但未测。

---

## 7. 我想预填 assistant 让模型接着写：续写模式

**核心配置**：`messages` 最后一条 `role: "assistant"`，模型沿其格式 / 内容续写；响应 `content` **不含**预填部分，需自行拼接。

```python
PREFIX = "{"
completion = client.chat.completions.create(
    model="doubao-seed-2-1-pro-260628",
    messages=[
        {"role": "user", "content": "Use JSON to describe the name and function of the Doubao model"},
        {"role": "assistant", "content": PREFIX},
    ],
)
json_text = PREFIX + completion.choices[0].message.content
```

curl 同第 2 节，只是 `messages` 末尾多一条 `{"role": "assistant", "content": "="}`（文档示例：普通模式回"1+1等于2。"，续写模式只回"2"）。

三个典型场景：

1. **改善输出格式**：预填 `{` 跳过寒暄直接出 JSON（不保证 100% 合法，配 `json_repair`；有结构化输出需求优先用第 5 节）。
2. **突破 `max_tokens`**：`finish_reason == "length"` 时把已输出内容追加到最后一条 assistant 再请求，循环拼接；会多耗 token，务必设最大循环次数。
3. **角色扮演一致性**：预填 `"Wukong said:"` 之类锚定当前发言角色；换角色只改最后一条 assistant。

**支持模型**：无深度思考能力的文本模型全部支持；深度思考模型仅以下支持：`doubao-seed-evolving`、`doubao-seed-2-1-pro-260628`、`doubao-seed-2-1-turbo-260628`、`doubao-seed-2-0-lite-260428`、`doubao-seed-2-0-mini-260428`、`doubao-seed-2-0-pro-260215`、`doubao-seed-2-0-lite-260215`、`doubao-seed-2-0-mini-260215`、`doubao-seed-2-0-code-preview-260215`、`doubao-seed-1-8-251228`、`doubao-seed-character-260628`、`doubao-seed-code-preview-251028`、`doubao-seed-1-6-251015`。

**注意事项**

- 其他深度思考模型以 assistant 结尾时 `thinking` 字段失效、保持默认行为（文档原文，未实测）。
- 上下文缓存对话 API（8.2）不允许最后一条为 `assistant`，即不支持续写。

---

## 8. 我想省输入 token：上下文缓存选型

| | 隐式缓存 | 显式缓存 · Context API（Chat 路线） | 显式缓存 · Responses API |
|---|---|---|---|
| 开启方式 | 自动、**不可关闭**；可加 Header `X-Prompt-Cache-Id` 提升命中 | `POST /context/create` 拿 `context_id`，再 `POST /context/chat/completions` | `caching: {"type":"enabled"[, "prefix": true]}` + `previous_response_id` |
| 命中保证 | 不保证（容量、路由影响） | 确定性命中 | 确定性命中 |
| 最少 token | 默认 1024；`doubao-seed-2-1-turbo-260628`、`glm-5-2-260617`、`deepseek-v4-*` 为 2048 | ⚠ 文档未说明 | 前缀缓存 ≥ 256，Session 无限制 |
| 存储计费 | 不计费 | 计费（按小时） | 计费（按小时） |
| 支持 API | Chat / Responses / Batch | Context API 自身 | Responses API |
| 适用 | 多轮对话、工具调用等前缀持续增长场景 | 固定人设 / 前缀（`common_prefix`）或多轮会话（`session`） | 同左 |

⚠ 文档自相矛盾：上下文缓存指南（2026-09-01）的对比表把显式缓存"支持 API"只列为 Responses API，但 Context API 两页（2026-08-17 / 08-24）仍在线且完整描述 `/context/create` + `/context/chat/completions`。Context API 可能处于存量维护状态，新业务文档倾向 Responses API；两条路都写在下面。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`POST /api/plan/v3/context/create` → **404**（空 body），Context API 在 Plan 入口**不存在**；标准入口 `/api/v3/context/*` 是否仍可调未测。Plan 用户要显式缓存只能走 8.3 的 Responses API（`/api/plan/v3/responses` 实测可用，见 `responses.md`）。

显式缓存与隐式缓存互斥：请求使用显式缓存时隐式缓存不生效。

### 8.1 隐式缓存 + `X-Prompt-Cache-Id`

- 支持模型：`doubao-seed-code`、`doubao-seed-2.0` 及之后系列（在线推理）；批量推理支持模型全部开启。
- 命中判断：`usage.prompt_tokens_details.cached_tokens > 0`。
- 提升命中：稳定前缀放前（人设、长文本），变化内容放后（当轮问题、时间戳）；工具定义、顺序、`response_format` 保持一致。
- **`X-Prompt-Cache-Id`**（doubao-seed-2.0 及之后，Chat / Responses API）：同一 Endpoint + 模型 + 该值的请求优先路由到同一服务以提高前缀复用。尽力而为，不承诺固定实例。限制：同一取值 **≤ 15 请求/分钟**，超出回退常规路由；同一会话保持同一值，不同用户 / 并行会话用不同值；用不可读的内部 Session ID，不要放手机号、邮箱、凭证或 Prompt 原文。

```bash
curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ARK_API_KEY" \
  -H "X-Prompt-Cache-Id: sess_8f3a…" \
  -d '{"model": "doubao-seed-2-1-pro-260628", "messages": [{"role": "user", "content": "Hello"}]}'
```

Python：`client.chat.completions.create(..., extra_headers={"X-Prompt-Cache-Id": session_id})`，然后读 `completion.usage.prompt_tokens_details.cached_tokens` 判断命中。

**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`/api/plan/v3/chat/completions` 带 `X-Prompt-Cache-Id: skill-probe-1` → 200、不报错、响应正常（`cached_tokens: 0`——单次短请求无法证明命中，只证明 Plan 入口接受该头）。标准入口未测。

### 8.2 Context API（Chat 路线的显式缓存）

#### 创建上下文缓存

**Endpoint**: `POST /api/v3/context/create`（仅标准入口；**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`/api/plan/v3/context/create` 404，Plan 入口没有此接口）

**用途**: 把 system 人设 / 背景等要复用的消息预处理成缓存，返回 `context_id`；之后用缓存对话接口引用。与 8.1 的区别：确定性命中、可控 TTL，但收存储费。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | ✅ | — | **只能填 Endpoint ID（`ep-`）**，暂不支持 Model ID。 |
| `messages` | object[] | ✅ | — | 要缓存的消息：`system`（`role`、`content` string）、`user`（`role`、`content` string、`name`）、`assistant`（`role`、`content` / `tool_calls[]` 至少其一）。人设等放最前，两种模式下都常驻缓存直到过期。 |
| `mode` | string | | `session` | `session`：Session 缓存（每轮对话后把回复也写入缓存）；`common_prefix`：前缀缓存（只存初始信息，不更新）。 |
| `ttl` | integer | | `86400` | 过期秒数，范围 `[3600, 604800]`（1 小时到 7 天）。**每次调用 chat 都会重置计时**。 |
| `truncation_strategy` | object | | `null` | 仅 `mode=session` 可设；不设则按模型自动适配。两种互斥模式：`{"type":"last_history_tokens","last_history_tokens":4096}`（范围 `(0,32768)`，超限按最早缓存先清、不重算）或 `{"type":"rolling_tokens","rolling_tokens":true,"max_window_tokens":32768,"rolling_window_tokens":4096}`（接近上限时按 message 粒度 FIFO 裁剪并重算；`rolling_tokens=false` 时超限 `finish_reason=length`；需 0 < rolling_window_tokens < max_window_tokens < context window）。 |

**示例请求**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/context/create \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{"model": "ep-2025xxxx-xxxxx", "mode": "session", "ttl": 3600,
       "messages": [{"role": "system", "content": "你是一名文学分析助手，请根据下面内容分析《麦琪的礼物》。<小说全文>"}]}'
```

```python
import os, requests
BASE = "https://ark.cn-beijing.volces.com/api/v3"
HDR = {"Authorization": f"Bearer {os.environ['ARK_API_KEY']}", "Content-Type": "application/json"}

ctx = requests.post(f"{BASE}/context/create", headers=HDR, json={
    "model": "ep-2025xxxx-xxxxx", "mode": "session", "ttl": 3600,
    "messages": [{"role": "system", "content": "你是一名文学分析助手……<小说全文>"}],
}).json()
context_id = ctx["id"]
```

官方 SDK：`client.context.create(model=..., mode=..., messages=..., ttl=...)`，底层同一 endpoint。

**示例响应**

```json
{"id": "ctx-2025…", "model": "ep-2025xxxx-xxxxx", "mode": "session", "ttl": 3600,
 "truncation_strategy": {"type": "last_history_tokens", "last_history_tokens": 4096},
 "usage": {"prompt_tokens": 1200, "completion_tokens": 0, "total_tokens": 1200, "prompt_tokens_details": {"cached_tokens": 0}}}
```

#### 上下文缓存对话

**Endpoint**: `POST /api/v3/context/chat/completions`

**用途**: 带 `context_id` 的对话；`session` 模式只传最新一轮消息，历史由缓存维护。字段与 Chat API 大部分一致，**差异**如下：

| 参数 | 与 Chat API 的差异 |
|---|---|
| `context_id` | **新增，必填**。`/context/create` 返回的 `id`。 |
| `model` | 暂不支持 Model ID（文档表述为"您需要调用的模型的 ID…也可通过 Endpoint ID"，但页首提示"暂时不支持直接通过 Model ID 调用"→ ⚠ 文档自相矛盾，实测时先用 `ep-`）。 |
| `messages` | 最后一条不能是 `assistant`（不支持续写）；`session` 模式只传最新一轮。 |
| `tools` | **不支持**。 |
| `thinking` | **不支持**（页首提示）。 |
| `response_format` | 页首提示"不支持结构化输出参数"，但参数表又完整列出 `text` / `json_object` / `json_schema` → ⚠ 文档自相矛盾。 |
| `service_tier` | 只支持 `default`；缓存不支持 TPM 保障包，故不支持 `auto`。默认值仍标 `auto`（⚠ 文档自相矛盾）。 |
| `stream` / `stream_options.include_usage` / `max_tokens` / `stop` / `temperature` / `top_p` / `frequency_penalty` / `presence_penalty` / `logprobs` / `top_logprobs` / `logit_bias` | 同 Chat API（默认值一致：`max_tokens` 4096、`temperature` 1、`top_p` 0.7）。`stream_options` 无 `chunk_include_usage`。 |

**示例请求**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/context/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{"model": "ep-2025xxxx-xxxxx", "context_id": "ctx-2025…",
       "messages": [{"role": "user", "content": "用5个简短的要点总结核心情节。"}]}'
```

```python
resp = requests.post(f"{BASE}/context/chat/completions", headers=HDR, json={
    "model": "ep-2025xxxx-xxxxx",
    "context_id": context_id,
    "messages": [{"role": "user", "content": "用5个简短的要点总结核心情节。"}],
}).json()
print(resp["choices"][0]["message"]["content"])
print(resp["usage"]["prompt_tokens_details"]["cached_tokens"])   # 命中的缓存 token
```

官方 SDK：`client.context.completions.create(model=..., context_id=..., messages=...)`。

**示例响应**：结构同 2.3（`object: chat.completion`，`service_tier` 只会是 `scale` / `default`），`usage.prompt_tokens_details.cached_tokens` 为命中缓存量，`usage.completion_tokens_details.reasoning_tokens` 为思维链量。流式时 `usage` 默认 `null`，需 `stream_options.include_usage`。

**注意事项**

- 存储费从缓存创建起按自然小时计，不足 1 小时按 1 小时；`session` 模式每轮新增缓存内容都会累加存储量。
- `ttl` 每次 chat 调用都重置，长期不用的缓存到期自动删除；Context API 页未提供删除接口（⚠ 文档未说明能否主动删除）。
- 缓存内容：`doubao-seed-1.8` 之前模型缓存"输入 + 回答 − 思维链"；1.8 及之后只缓存输入。

### 8.3 Responses API 显式缓存（指引）

新业务文档推荐路线，字段在 `POST /api/v3/responses`：`caching: {"type":"enabled"}`（Session）或 `{"type":"enabled","prefix":true}`（前缀，首轮 ≥ 256 token 且不能 `stream`），`store` 默认 `true`，`expire_at` 最长 7 天，后续轮用 `previous_response_id`；`DELETE /api/v3/responses/{id}` 删缓存。限制：前序轮次开了 caching 就不能用 `json_schema`；`thinking` 赋值要与前一轮一致；`tools` 只能在首轮设置；设置了 `instructions` 的轮次不读不写缓存。详见 `responses.md`。

---

## 9. 我想数 token：分词 API

### 分词

**Endpoint**: `POST /api/v3/tokenization`（仅标准入口；**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`POST /api/plan/v3/tokenization` → 404，空 body）

**用途**: 对文本分词，返回 token ID 与偏移量；用于预估 `prompt_tokens`、拿 `logit_bias` 所需 token ID。仅文本，不支持多模态。与 `usage` 的区别：`usage` 是事后实际用量，分词 API 是事前估算。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | ✅ | — | Model ID 或 Endpoint ID（不同模型词表不同，用将要调用的那个模型）。 |
| `text` | string / string[] | ✅ | — | 一条或多条文本；多条传数组，结果按 `index` 对应。 |
| `user` | string | | — | 服务端接受但不使用，预留对齐其他接口。 |

**示例请求**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/tokenization \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{"model": "doubao-seed-2-1-pro-260628", "text": ["天空为什么这么蓝？", "花儿为什么这么香？"]}'
```

```python
resp = requests.post(f"{BASE}/tokenization", headers=HDR, json={
    "model": "doubao-seed-2-1-pro-260628",
    "text": ["天空为什么这么蓝？", "花儿为什么这么香？"],
}).json()
for item in resp["data"]:
    print(item["index"], item["total_tokens"], item["token_ids"][:5], item["offset_mapping"][:5])
```

官方 SDK：`client.tokenization.create(model=..., text=[...])`。openai SDK 无对应方法，用 `requests`。

**示例响应**

```json
{"id": "0217…", "object": "list", "created": 1765713048, "model": "doubao-seed-2-1-pro-260628",
 "data": [{"index": 0, "object": "tokenization", "total_tokens": 6,
           "token_ids": [1234, 5678, 9012, 3456, 7890, 111],
           "offset_mapping": [[0, 2], [2, 4], [4, 5], [5, 7], [7, 8], [8, 9]]}]}
```

`offset_mapping` 每项 `[start, end)` 为该 token 在原文中的字符区间（从 0 开始，右开）。

**注意事项**

- Plan 入口：**已用真实 API 验证（2026-09-04，Agent Plan Medium）**，`/api/plan/v3/tokenization` 404，Agent Plan 没有分词接口，只能用响应 `usage` 事后统计。`/api/coding/v3/tokenization` 是否存在 ⚠ 文档未说明（无 Coding Plan Key，未测；预期同样 404）。
- 控制台另有 Token 计算器；账号 / 项目 / 接入点维度用量在控制台"用量统计"查看。

---

## 10. 提示词工程中与 API 相关的两条

1. **role 用法**：`system` 放高优先级规则、身份、边界、工具使用规范，稍后每次调用都靠前传入；`user` 放需求；`tool` 只用于工具结果。方舟没有 `developer` role。深度思考模型反而建议少用 system、把信息直接放 `user`（深度思考文档）。
2. **前缀稳定即缓存友好**：稳定的规则 / 参考材料放消息列表前部，任务特定上下文放尾部——这既是提示词工程建议，也是隐式缓存命中的前提（第 8.1 节）。有思考模型时，提示词给"目标 + 场景 + 约束"，不要给分步过程；无思考模型则给精确步骤、格式和样例。

---

## 11. 来源页面

| 标题 | URL | 文档更新时间 |
|---|---|---|
| 对话(Chat) API | https://www.volcengine.com/docs/82379/1494384 | 2026-08-28 |
| 文本生成 | https://www.volcengine.com/docs/82379/1399009 | 2026-06-23 |
| 深度思考 | https://www.volcengine.com/docs/82379/1449737 | 2026-08-19 |
| 流式输出 | https://www.volcengine.com/docs/82379/2123275 | 2026-07-30 |
| 结构化输出(beta) | https://www.volcengine.com/docs/82379/1568221 | 2026-09-03 |
| Function Calling（函数调用） | https://www.volcengine.com/docs/82379/1262342 | 2026-08-05 |
| 续写模式 | https://www.volcengine.com/docs/82379/1359497 | 2026-07-30 |
| 分词 API | https://www.volcengine.com/docs/82379/1528728 | 2026-08-27 |
| 使用 Prompt Cache Key 提升缓存命中率 | https://www.volcengine.com/docs/82379/2615186 | 2026-08-04 |
| 创建上下文缓存 API | https://www.volcengine.com/docs/82379/1528789 | 2026-08-24 |
| 上下文缓存对话 API | https://www.volcengine.com/docs/82379/1529329 | 2026-08-17 |
| 上下文缓存 | https://www.volcengine.com/docs/82379/1398933 | 2026-09-01 |
| 提示词工程 | https://www.volcengine.com/docs/82379/1221660 | 2026-08-24 |
| 兼容 OpenAI SDK（`X-Client-Request-Id`、`extra_body`） | https://www.volcengine.com/docs/82379/1330626 | 2026-06-23 |
| 常见问题（developer role 报错） | https://www.volcengine.com/docs/82379/2165245 | 2026-08-24 |
| 真实 API 验证记录（Agent Plan Medium，`/api/plan/v3`） | `volcengine-ark-workspace/verification-findings.md` + `verification-log.jsonl`（同批产出） | 2026-09-04 |
