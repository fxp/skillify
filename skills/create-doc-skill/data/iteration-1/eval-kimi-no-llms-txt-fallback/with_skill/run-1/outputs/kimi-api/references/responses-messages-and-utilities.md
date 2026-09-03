> 内容整理自 platform.kimi.com/docs（抓取于 2026-09-03），**尚未用真实 API 调用验证**；实际报错优先信任 API。

# Kimi API：Responses / Messages 协议与工具类接口

## 目录

1. [三种推理协议怎么选](#1-三种推理协议怎么选)
2. [通用约定：鉴权、Base URL、请求签名 Header](#2-通用约定)
3. [OpenAI Responses 兼容：`POST /v1/responses`](#3-openai-responses-兼容)
4. [Anthropic Messages 兼容：`POST /anthropic/v1/messages`](#4-anthropic-messages-兼容)
5. [工具类接口](#5-工具类接口)：5.1 列出模型 `GET /v1/models` · 5.2 估算 Token `POST /v1/tokenizers/estimate-token-count` · 5.3 查询余额 `GET /v1/users/me/balance` · 5.4 校验请求签名 `POST /v1/signatures/verify`（含完整流程）

---

## 1. 三种推理协议怎么选

| | OpenAI Chat Completions | OpenAI Responses | Anthropic Messages |
|---|---|---|---|
| Endpoint | `POST /v1/chat/completions` | `POST /v1/responses` | `POST /anthropic/v1/messages` |
| SDK `base_url` | `https://api.moonshot.cn/v1` | `https://api.moonshot.cn/v1` | `https://api.moonshot.cn/anthropic` |
| SDK / 工具 | `openai`（Python/Node）、LangChain、Dify、Coze 等 | `openai`（Python/Node） | `anthropic`（Python/Node）、Claude Code |
| 可用模型 | `kimi-k3`、`kimi-k2.7-code`、`kimi-k2.7-code-highspeed`、`kimi-k2.6`（见 auth 与 models 文档） | 规范写明"本接口当前支持 `kimi-k3`" | 规范 `model` 枚举只有 `kimi-k3` |
| 系统提示 | `messages[]` 中 `role: system` | 顶层 `instructions`，或 `input[]` 中 `role: developer` | 顶层 `system`（字符串或 text 块数组）；`messages[].role` 只能是 user / assistant |
| 推理强度 | `reasoning_effort`（kimi-k3）/ `thinking`（kimi-k2.6，需 `extra_body`） | `reasoning.effort`：low / high / max | `output_config.effort`：low / high / max |
| 结构化输出 | 见 chat-completions 参考 | `text.format` = `{type: json_schema, schema}` | `output_config.format` = `{type: json_schema, schema}` |
| 多轮状态 | 客户端自己拼 messages | **无服务端状态**：`store`/`background` 固定 false，`previous_response_id`/`conversation` 固定 null，历史必须放回 `input[]` | 客户端自己拼 messages，thinking 块需带 `signature` 原样回传 |
| Kimi 专有扩展 | `thinking`、`partial`（写在 assistant 消息上） | `namespace` 工具、`additional_tools` 中途追加工具、`prompt_cache_key`、`safety_identifier` | `output_config`、`usage.output_tokens_details.thinking_tokens`、图片 `ms://<file_id>` 引用 |
| 明确不支持 / 未列出 | 见 chat-completions 参考 | `tool_choice` 只有 `auto`；`input_image` 不支持公网 http(s) URL；`encrypted_content` 固定 null；请求体未列出 `temperature`/`top_p`/`metadata`/`parallel_tool_calls` | 图片不支持公网 URL（仅 base64 或 `ms://`）；`tool_choice` 无强制指定某个工具的 `tool` 类型；请求体未列出 `temperature`/`top_p`/`top_k`/`thinking`/`cache_control` |
| 适用场景 | 存量 OpenAI 生态代码、第三方框架、需要全部 4 个模型 | 新写的 OpenAI Responses 风格代码、需要 namespace/动态工具 | 存量 Anthropic SDK 代码、Claude Code 等 Anthropic 生态工具 |

**选型口诀**：老代码用哪家 SDK 就走哪条协议，只改 `base_url` 和 key；新项目要用 `kimi-k2.7-code`/`kimi-k2.6` 时只能走 Chat Completions（Responses/Messages 规范里只列了 `kimi-k3`）。

---

## 2. 通用约定

- **鉴权**：所有接口唯一 header `Authorization: Bearer $MOONSHOT_API_KEY`；JSON 请求加 `Content-Type: application/json`。Key 在 https://platform.kimi.com/console/api-keys 创建，代码里只用环境变量 `MOONSHOT_API_KEY` 读取。
- **域名**：服务地址 `https://api.moonshot.cn`；国际站 `platform.kimi.ai` 的 key 与中国站完全隔离，混用 401；余额也互不相通。
- **请求签名 Header（三个推理接口共用）**：请求头带 `X-Msh-Request-Nonce: <随机串，推荐 UUID v4>` 即开启签名，响应头返回 `Msh-Request-Timestamp`（Unix 毫秒）与 `Msh-Request-Signature`（`reqsigv1_` 前缀）。流式与非流式都返回。只允许一个非空 header 值；值不合法时请求照常执行但不返回签名头。校验流程见 5.4。

---

## 3. OpenAI Responses 兼容

### 创建模型响应（Responses）

**Endpoint**: `POST /v1/responses`（SDK `base_url="https://api.moonshot.cn/v1"`，`client.responses.create`）

**用途**: 用 OpenAI Responses 协议调用 Kimi：`input` 传文本/图片/历史 item，返回 `output` item 数组（reasoning → message → function_call）。与 `/v1/chat/completions` 的核心区别：输入是带 `type` 的 item 列表而非 messages，系统提示走 `instructions`，推理配置走 `reasoning.effort`，支持 namespace 工具与中途追加工具；但**没有服务端会话状态**。

**关键参数**（请求体）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | — | 规范："本接口当前支持 `kimi-k3`" |
| `input` | string \| array | 是 | — | 字符串 = 一条 user 消息；数组 = 按顺序的 item（见下表），可含历史对话、工具调用、工具结果 |
| `instructions` | string | 否 | — | 顶层系统指令，作为最靠前的指令生效 |
| `stream` | boolean | 否 | `false` | `true` 时以 SSE 事件流返回 |
| `max_output_tokens` | integer | 否 | `131072`（kimi-k3） | 最大可设 `1048576`。是**期望输出长度**，不是输入+输出总长。达到上限时 `status=incomplete`，`incomplete_details.reason=max_output_tokens` |
| `reasoning.effort` | string | 否 | `max` | 枚举 `low` / `high` / `max`。档位越高延迟与推理 Token 越多 |
| `text.format` | object | 否 | — | 结构化输出。`type`（必填，枚举仅 `json_schema`）、`schema`（必填，JSON Schema）、`name`（缺省 `output`）、`strict`（boolean） |
| `tools[]` | array | 否 | — | 工具定义，按 `type` 区分：`function` 或 `namespace`（见下） |
| `tool_choice` | string | 否 | — | 枚举**只有 `auto`**（模型自行决定） |
| `prompt_cache_key` | string | 否 | — | 上下文缓存标识，同一会话用同一取值可提升缓存命中率 |
| `safety_identifier` | string | 否 | — | 用户稳定标识（建议哈希后的用户名/邮箱），用于违规检测 |

`input[]` item 类型（省略 `type` 时按 `message` 处理）：

| `type` | 必填字段 | 说明 |
|---|---|---|
| `message` | `role`（`user` / `assistant` / `developer`）、`content`（string 或 content part 数组） | `developer` 按系统指令处理。可选 `status: completed` |
| `reasoning` | — | 回放上一轮推理。`summary[]{type: summary_text, text}` 或 `content[]{type: reasoning_text, text}`，**`content` 优先于 `summary`**；可选 `id`、`status` |
| `function_call` | `call_id`、`name`、`arguments`（JSON 字符串） | 回放模型发起的调用；可选 `id`、`namespace`、`status` |
| `function_call_output` | `call_id`、`output`（string 或 content part 数组） | 工具执行结果，`call_id` 与 `function_call` 配对 |
| `additional_tools` | `role: developer`、`tools[]` | **Kimi 扩展**：对话中途追加工具，作用范围从该 item 位置开始 |

content part 类型（`message.content[]` / `function_call_output.output[]`）：

| `type` | 字段 | 说明 |
|---|---|---|
| `input_text` | `text` | 输入文本 |
| `input_image` | `image_url`、`detail`（`auto` / `low` / `high` / `original`） | `image_url` 必须是 data URL（`data:image/png;base64,...`），**不支持公网 http(s) URL** |
| `output_text` | `text` | 回放 assistant 历史文本时使用 |

`tools[]` 定义：

| `type` | 必填字段 | 说明 |
|---|---|---|
| `function` | `name`（正则 `^[a-zA-Z_][a-zA-Z0-9-_]{0,127}$`） | 可选 `description`、`parameters`（JSON Schema）、`strict` |
| `namespace` | `name`、`description`、`tools[]`（function 工具数组） | **Kimi 扩展**：把一组 function 收纳到同一命名空间；模型调用时输出 item 带 `namespace` 字段 |

**示例请求**

```bash
curl https://api.moonshot.cn/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k3",
    "instructions": "你是 Kimi，一个由 Moonshot AI 提供的人工智能助手。",
    "input": "用一句话解释什么是上下文缓存。",
    "reasoning": {"effort": "low"},
    "max_output_tokens": 4096
  }'
```
```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.cn/v1",
)

# 1) 基本调用
resp = client.responses.create(
    model="kimi-k3",
    instructions="你是 Kimi，一个由 Moonshot AI 提供的人工智能助手。",
    input="用一句话解释什么是上下文缓存。",
    reasoning={"effort": "low"},
)
print(resp.output_text)
# 2) 函数工具 + 多轮回放（无服务端状态：把上一轮 output 原样拼回 input）
tools = [{
    "type": "function",
    "name": "get_weather",
    "description": "查询城市天气",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
}]
history = [{"role": "user", "content": "北京今天天气怎么样？"}]
r1 = client.responses.create(model="kimi-k3", input=history, tools=tools)
history += [item.model_dump(exclude_none=True) for item in r1.output]  # reasoning / function_call 一起回放
for item in r1.output:
    if item.type == "function_call":
        history.append({
            "type": "function_call_output",
            "call_id": item.call_id,
            "output": '{"city": "北京", "weather": "晴", "temp_c": 26}',
        })
r2 = client.responses.create(model="kimi-k3", input=history, tools=tools)
print(r2.output_text)
# 3) 流式
with_stream = client.responses.create(model="kimi-k3", input="写一首四行小诗", stream=True)
for event in with_stream:
    if event.type == "response.output_text.delta":
        print(getattr(event, "delta", ""), end="", flush=True)  # delta 字段名按 OpenAI 惯例，规范未逐事件列出
```

**示例响应**（非流式，关键字段）

```json
{
  "id": "resp_68f0c1c2d3e4f5a6b7c8d9e0",
  "object": "response",
  "created_at": 1786338000,
  "completed_at": 1786338003,
  "status": "completed",
  "model": "kimi-k3",
  "output": [
    {"type": "reasoning", "id": "rs_...", "summary": [{"type": "summary_text", "text": "..."}], "encrypted_content": null, "status": "completed"},
    {"type": "message", "id": "msg_...", "role": "assistant", "status": "completed",
     "content": [{"type": "output_text", "text": "上下文缓存是……", "annotations": []}]},
    {"type": "function_call", "id": "fc_...", "call_id": "...", "name": "get_weather", "namespace": "...", "arguments": "{\"city\":\"北京\"}", "status": "completed"}
  ],
  "usage": {
    "input_tokens": 120,
    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 120},
    "output_tokens": 80,
    "output_tokens_details": {"reasoning_tokens": 30},
    "total_tokens": 200
  },
  "incomplete_details": null, "error": null,
  "store": false, "background": false, "previous_response_id": null, "conversation": null
}
```

- `status` 枚举：`in_progress` / `completed` / `incomplete` / `failed`；`incomplete_details.reason` 枚举：`max_output_tokens` / `content_filter`；`failed` 时看 `error.code` / `error.message`。
- `usage.input_tokens` **含**命中缓存部分（与 Messages 协议相反，见 4）。

**流式事件**（`stream: true`，SSE 帧 `event: <type>` + `data: <json>`，每个事件必有 `type` 与从 0 单调递增的 `sequence_number`）：

`response.created` → `response.in_progress` → `response.output_item.added` → `response.content_part.added` → `response.reasoning_summary_part.added` / `response.reasoning_summary_text.delta` / `response.reasoning_summary_text.done` / `response.reasoning_summary_part.done` → `response.output_text.delta` / `response.output_text.done` → `response.function_call_arguments.delta` / `response.function_call_arguments.done` → `response.content_part.done` → `response.output_item.done` → `response.completed` | `response.incomplete` | `response.failed` | `error`

**注意事项**

- **无服务端状态**：响应中 `store`/`background` 固定 `false`，`previous_response_id`/`conversation` 固定 `null`。多轮必须把上一轮 `output` 的 reasoning/message/function_call item 拼回 `input[]`；不要传 `previous_response_id`。
- 输出的 reasoning item 只有 `summary[]`（`summary_text`），`encrypted_content` 固定 `null`；回放时 `reasoning` 的 `content`（`reasoning_text`）优先于 `summary`，直接原样回传 output item 即可。
- `tool_choice` 枚举只有 `auto`；传 `required`/`none`/指定函数对象会怎样 `⚠ 文档未说明`。
- 工具类型只有 `function` 与 `namespace`，没有任何 OpenAI 内置工具（web_search、file_search、code_interpreter 等）。
- `text.format` 只有 `json_schema`，且 `schema` 必填；`{"type": "text"}` / `json_object` 是否被接受 `⚠ 文档未说明`。
- 请求体规范未列出 `temperature`、`top_p`、`metadata`、`parallel_tool_calls`、`service_tier`（响应体里 `temperature`/`top_p`/`metadata`/`service_tier` 为可空字段，`parallel_tool_calls` 为 boolean）；请求中传这些参数是否生效或报错 `⚠ 文档未说明`。
- `input[].role` 枚举为 `user`/`assistant`/`developer`，没有 `system`；`role: system` 是否被接受 `⚠ 文档未说明`，系统提示请用 `instructions` 或 `developer`。
- 流式各事件除 `type`/`sequence_number` 外的载荷字段（如 `delta`、`item`、`response`）`⚠ 文档未说明`，上面示例按 OpenAI 惯例读取 `delta`。
- 429 含义是"请求过于频繁**或额度不足**"，先查 5.3 余额再重试。

---

## 4. Anthropic Messages 兼容

### 创建消息（Messages）

**Endpoint**: `POST /anthropic/v1/messages`（完整 URL `https://api.moonshot.cn/anthropic/v1/messages`；SDK `base_url="https://api.moonshot.cn/anthropic"`，SDK 自动补 `/v1/messages`）

**用途**: 用 Anthropic Messages 协议调用 Kimi，支持流式、工具调用、图片输入、思考（thinking 块）与结构化输出。面向已有 Anthropic SDK / Claude Code 的项目：只改 base URL 与 key。与 Responses 的区别：消息结构是 Anthropic 的 content block 体系，`max_tokens` **必填**，推理配置走 `output_config`。

**关键参数**（请求体）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | `kimi-k3`（规范写了 default，但仍标为必填） | 枚举只有 `kimi-k3` |
| `messages[]` | array | 是 | — | `role` 枚举 `user` / `assistant`；`content` 为字符串或内容块数组。**最后一条为 assistant 时从其内容之后继续生成（Partial Mode）** |
| `max_tokens` | integer | **是** | — | 最小 1。达到上限未结束时 `stop_reason=max_tokens` |
| `system` | string \| array | 否 | — | 系统提示，字符串或 `[{type: text, text}]` 数组 |
| `stream` | boolean | 否 | `false` | SSE 流式 |
| `stop_sequences` | array<string> | 否 | — | 最多 5 个，每个不超过 32 字节；完全匹配时停止，匹配词本身不输出 |
| `tools[]` | array | 否 | — | `name`（必填，正则 `^[a-zA-Z_][a-zA-Z0-9-_]{0,127}$`）、`input_schema`（必填，顶层 `type` 必须为 `object`，需符合 MFJS 规范）、`description`、`type`（枚举仅 `custom`，可省略） |
| `tool_choice` | object | 否 | `{type: auto}` | `type` 枚举 `auto`（模型自行决定）/ `any`（强制调用任意工具）/ `none`（不调用） |
| `metadata.user_id` | string | 否 | — | 终端用户/会话稳定 ID，提升缓存命中与滥用检测；建议哈希值；Coding Agent 建议传 session id 并保持不变 |
| `output_config.effort` | string | 否 | `max` | 枚举 `low` / `high` / `max`。**切换档位会破坏前缀缓存命中**，建议会话开始前定好 |
| `output_config.format` | object | 否 | — | 结构化输出：`type`（必填，枚举仅 `json_schema`）、`schema`（必填，JSON Schema） |

`messages[].content[]` 内容块：

| `type` | 必填字段 | 出现位置 | 说明 |
|---|---|---|---|
| `text` | `text` | user / assistant | 文本 |
| `image` | `source` | user（含 tool_result 内） | `source.type` 枚举 `base64` / `url`。`base64` 时需 `media_type`（`image/jpeg` / `image/png` / `image/gif` / `image/webp`）+ `data`；`url` 时 `url` 必须是 `ms://<file_id>`（先经 `/v1/files` 上传） |
| `thinking` | `thinking` | assistant | 多轮时把响应中的 thinking 块（含 `signature`）**原样放回** |
| `tool_use` | `id`、`name`、`input` | assistant | 模型发起的工具调用 |
| `tool_result` | `tool_use_id`、`content`（string 或 text/image 块数组） | user | 工具执行结果 |

**示例请求**

```bash
curl https://api.moonshot.cn/anthropic/v1/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k3",
    "max_tokens": 1024,
    "system": "你是 Kimi，一个由 Moonshot AI 提供的人工智能助手。",
    "messages": [{"role": "user", "content": "用一句话解释什么是上下文缓存。"}],
    "output_config": {"effort": "low"}
  }'
```
```python
import os
from anthropic import Anthropic

client = Anthropic(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.cn/anthropic",
)

# 1) 基本调用（max_tokens 必填；Kimi 扩展参数 output_config 走 extra_body）
msg = client.messages.create(
    model="kimi-k3",
    max_tokens=1024,
    system="你是 Kimi，一个由 Moonshot AI 提供的人工智能助手。",
    messages=[{"role": "user", "content": "用一句话解释什么是上下文缓存。"}],
    extra_body={"output_config": {"effort": "low"}},
)
for block in msg.content:          # 顺序：thinking → text → tool_use
    if block.type == "text":
        print(block.text)
# 2) 工具调用 + 多轮（thinking 块含 signature 原样回传）
tools = [{
    "name": "get_weather",
    "description": "查询城市天气",
    "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
}]
messages = [{"role": "user", "content": "北京今天天气怎么样？"}]
r1 = client.messages.create(model="kimi-k3", max_tokens=1024, tools=tools, messages=messages)
if r1.stop_reason == "tool_use":
    messages.append({"role": "assistant",
                     "content": [b.model_dump(exclude_none=True) for b in r1.content]})
    results = [{"type": "tool_result", "tool_use_id": b.id,
                "content": '{"city": "北京", "weather": "晴", "temp_c": 26}'}
               for b in r1.content if b.type == "tool_use"]
    messages.append({"role": "user", "content": results})
    r2 = client.messages.create(model="kimi-k3", max_tokens=1024, tools=tools, messages=messages)
    print(next(b.text for b in r2.content if b.type == "text"))
# 3) 流式：按规范列出的事件类型处理
stream = client.messages.create(
    model="kimi-k3", max_tokens=1024, stream=True,
    messages=[{"role": "user", "content": "写一首四行小诗"}],
)
for event in stream:
    if event.type == "content_block_delta":
        d = event.delta               # d.type: text_delta / thinking_delta / signature_delta / input_json_delta
        if d.type == "text_delta":
            print(d.text, end="", flush=True)
        elif d.type == "input_json_delta":
            pass                      # d.partial_json 需拼接后再 json.loads
    elif event.type == "message_delta":
        print("\nstop_reason =", event.delta.stop_reason)
```

**示例响应**（非流式，关键字段）

```json
{
  "id": "...",
  "type": "message",
  "role": "assistant",
  "model": "kimi-k3",
  "content": [
    {"type": "thinking", "thinking": "...", "signature": "..."},
    {"type": "text", "text": "上下文缓存是……"},
    {"type": "tool_use", "id": "...", "name": "get_weather", "input": {"city": "北京"}}
  ],
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 100,
    "output_tokens": 80,
    "cache_read_input_tokens": 0,
    "cache_creation_input_tokens": 100,
    "output_tokens_details": {"thinking_tokens": 30}
  }
}
```

- `stop_reason` 枚举：`end_turn`（自然结束，**含命中 `stop_sequences`**）/ `max_tokens` / `tool_use` / `refusal`（触发内容安全审查）/ `null`。
- `usage.input_tokens` **不含**命中缓存部分；命中/写入分别看 `cache_read_input_tokens` / `cache_creation_input_tokens`；`output_tokens` 含推理 Token，其中推理部分在 `output_tokens_details.thinking_tokens`（Kimi 扩展字段）。

**流式事件**：SSE 帧 `event` 与 `data.type` 一致，顺序 `message_start` → (`content_block_start` → `content_block_delta`… → `content_block_stop`)… → `message_delta` → `message_stop`。`content_block_delta.delta.type` 枚举 `text_delta`（`text`）/ `thinking_delta`（`thinking`）/ `signature_delta`（`signature`）/ `input_json_delta`（`partial_json`）。`message_start.message` 是完整 `MessagesResponse` 结构；`message_delta` 带 `delta.stop_reason`、`delta.stop_sequence` 与 `usage`。

**错误体**：400 / 500 为 Anthropic 格式 `{"type": "error", "error": {"type": "...", "message": "..."}, "request_id": "..."}`；反馈问题请附 `request_id`。

**注意事项**

- `max_tokens` 必填（Anthropic 原生也必填，但从 OpenAI 迁来的人常漏）；`messages[].role` 只有 `user`/`assistant`，系统提示必须走顶层 `system`。
- **命中 `stop_sequences` 时 `stop_reason` 是 `end_turn` 而不是原生 Anthropic 的 `stop_sequence`**；`stop_sequence` 字段仍会给出匹配到的词。枚举里也没有 `pause_turn`。
- `tool_choice.type` 只有 `auto`/`any`/`none`，**没有原生的 `{type: tool, name}`**（强制调用指定工具）；也未列出 `disable_parallel_tool_use`。传了会怎样 `⚠ 文档未说明`。
- 推理控制用 Kimi 的 `output_config.effort`，规范未列出原生 `thinking: {type: enabled, budget_tokens}`；传原生 `thinking` 参数是否被接受/忽略 `⚠ 文档未说明`。`effort` 没有"关闭"档，thinking 块是否总会返回 `⚠ 文档未说明`。
- 多轮必须把 thinking 块连同 `signature` 原样放回 assistant 消息（用 SDK 对象时 `model_dump(exclude_none=True)` 即可）；`signature` 在响应里是可选字段。
- 图片：`source.type=url` 的 `url` 只接受 `ms://<file_id>`，**不接受公网 https 图片 URL**（原生 Anthropic 接受）。
- 规范未列出 `temperature`、`top_p`、`top_k`、`cache_control`（`cache_creation_input_tokens` 表明缓存是自动的）；这些参数传入后是否生效 `⚠ 文档未说明`。
- `tools[].input_schema` 需符合 MFJS（Moonshot Flavored JSON Schema）规范，且顶层 `type` 必须为 `object`；复杂 schema 报 400 时先对照 MFJS 文档。
- 流式事件里未列出原生 Anthropic 的 `ping` 与 `error` 事件；流中出错如何表达 `⚠ 文档未说明`。
- 401 的响应体在规范中引用的是 OpenAI 风格 `{"error": {"message", "type", "code"}}`，与 400/500 的 Anthropic 格式不同；这会不会影响 anthropic SDK 的异常解析 `⚠ 文档未说明`（规范原文如此，两处都列出以备核对）。
- `model` 字段规范同时写了 `required` 与 `default: kimi-k3` `⚠ 文档自相矛盾`（必填字段不该有默认值）；保险起见总是显式传 `model`。
- **Claude Code 接入**：文档只有一句"已经在使用 Anthropic SDK、Claude Code 等工具的开发者，只需把 base URL 指向 `https://api.moonshot.cn/anthropic`"；具体的环境变量名 / 配置项 / 模型名映射 `⚠ 文档未说明`（不在本次输入材料内），按 Claude Code 自身文档配置 base URL 与 key 即可。

---

## 5. 工具类接口

### 5.1 列出模型

**Endpoint**: `GET /v1/models`（SDK `client.models.list()`，openai SDK）

**用途**: 列出当前可用的所有模型及其能力（上下文长度、是否支持图片/视频/深度思考）。和 `/v1/responses`/`/anthropic/v1/messages` 的区别：只读元数据，不产生推理费用。

**关键参数**：无（无 query / path 参数）。

**示例请求**

```bash
curl https://api.moonshot.cn/v1/models \
  -H "Authorization: Bearer $MOONSHOT_API_KEY"
```
```python
import os, requests

r = requests.get(
    "https://api.moonshot.cn/v1/models",
    headers={"Authorization": f"Bearer {os.environ['MOONSHOT_API_KEY']}"},
)
for m in r.json()["data"]:
    print(m["id"], m.get("context_length"), m.get("supports_image_in"),
          m.get("supports_video_in"), m.get("supports_reasoning"))
# openai SDK 的 client.models.list() 也能用，但 Kimi 扩展字段不在 SDK 的 Model 类型声明里
```

**示例响应**

```json
{
  "object": "list",
  "data": [
    {
      "id": "kimi-k3",
      "object": "model",
      "created": 1786338000,
      "owned_by": "...",
      "context_length": 1048576,
      "supports_image_in": true,
      "supports_video_in": true,
      "supports_reasoning": true
    }
  ]
}
```

**注意事项**

- `object`、`owned_by` 的具体取值 `⚠ 文档未说明`（上面示例值仅为占位）。
- 已下线模型（`moonshot-v1-*`、`kimi-k2.5`、`kimi-k2-*`、`kimi-latest`、`kimi-thinking-preview`）调用返回 404；上线前用本接口核对模型 ID。

### 5.2 估算 Token 数量

**Endpoint**: `POST /v1/tokenizers/estimate-token-count`（openai SDK 无对应方法，用 `requests`）

**用途**: 发送请求前估算一组 messages 在指定模型下的 Token 数。输入结构与 Chat Completions 基本一致（支持多模态 content）。与 `/v1/models` 的区别：这是按内容计算的实时估算，不是模型元数据。

**关键参数**（请求体）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | `kimi-k3` | 枚举 `kimi-k3` / `kimi-k2.7-code` / `kimi-k2.7-code-highspeed` / `kimi-k2.6` |
| `messages[]` | array | 是 | — | `role` 枚举 `system` / `user` / `assistant` / `tool`；`content` 不得为空，为字符串或 `text` / `image_url` / `video_url` 块数组 |
| `messages[].content[].image_url` / `video_url` | object \| string | — | — | `{url: "..."}` 或直接字符串；文档示例用 data URL |
| `messages[].name` / `messages[].partial` | string / boolean | 否 | null / `false` | 发送者名称；`partial: true` 放在最后一条 assistant 消息上启用 Partial Mode |

**示例请求**

```bash
curl https://api.moonshot.cn/v1/tokenizers/estimate-token-count \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k3",
    "messages": [
      {"role": "system", "content": "你是 Kimi，由 Moonshot AI 提供的人工智能助手。"},
      {"role": "user", "content": "你好，我叫李雷，1+1等于多少？"}
    ]
  }'
```
```python
import os, requests

api_key = os.environ["MOONSHOT_API_KEY"]
payload = {
    "model": "kimi-k3",
    "messages": [
        {"role": "system", "content": "你是 Kimi，由 Moonshot AI 提供的人工智能助手。"},
        # 多模态：content 也可以是 [{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}, {"type": "text", "text": "..."}]
        {"role": "user", "content": "你好，我叫李雷，1+1等于多少？"},
    ],
}
r = requests.post(
    "https://api.moonshot.cn/v1/tokenizers/estimate-token-count",
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    json=payload,
)
body = r.json()
if "error" not in body:
    print(body["data"]["total_tokens"])
```

**示例响应**

```json
{"data": {"total_tokens": 80}}
```

**注意事项**

- 结果在 `data.total_tokens`（外面套了一层 `data`）；文档原话"当没有 `error` 字段，可以取 `data.total_tokens`"，先判 `error` 再取值。图片走 `image_url` 块（data URL），视频走 `video_url` 块。
- 请求体没有 `tools` 字段，工具定义占用的 Token 无法用本接口估算 `⚠ 文档未说明`。
- 只接受 Chat Completions 风格的 messages；Responses 的 `input[]` item 和 Messages 的 content block 需自行转换后再估算，直接传是否会拒绝或误算 `⚠ 文档未说明`。名字是"估算"，与真实 `usage` 是否严格一致 `⚠ 文档未说明`。

### 5.3 查询余额

**Endpoint**: `GET /v1/users/me/balance`（用 `requests`）

**用途**: 查询当前 API Key 所属账户的可用余额、代金券余额、现金余额。收到 429"额度不足"或准备上线前用。

**关键参数**：无。

**示例请求**

```bash
curl https://api.moonshot.cn/v1/users/me/balance \
  -H "Authorization: Bearer $MOONSHOT_API_KEY"
```
```python
import os, requests

r = requests.get(
    "https://api.moonshot.cn/v1/users/me/balance",
    headers={"Authorization": f"Bearer {os.environ['MOONSHOT_API_KEY']}"},
)
body = r.json()
if body["code"] == 0:
    d = body["data"]
    print(d["available_balance"], d["voucher_balance"], d["cash_balance"])
```

**示例响应**

```json
{
  "code": 0,
  "data": {
    "available_balance": 49.5,
    "voucher_balance": 10.0,
    "cash_balance": 39.5
  },
  "scode": "...",
  "status": true
}
```

**注意事项**

- 响应壳是 `code`（0 表示成功）/ `data` / `scode`（状态码，取值 `⚠ 文档未说明`）/ `status`（boolean），不是 OpenAI 风格；成功判据用 `code == 0`。
- 三个余额单位都是人民币元。`available_balance` = 现金 + 代金券，**≤ 0 时无法调用推理 API**；`voucher_balance` 不可为负；`cash_balance` 可为负表示欠费，此时 `available_balance` 等于 `voucher_balance`。

### 5.4 校验请求签名

**Endpoint**: `POST /v1/signatures/verify`（用 `requests`）

**用途**: 校验 Chat Completions / Responses / Messages 响应头里的请求签名，证明"Kimi API 在某个时间点以指定 `model` 接受了这个请求"——用于向用户/第三方证明背后是 Kimi 官方 API、核验代理层没有偷换模型、事后审计与争议举证。与其它工具接口的区别：它不查询状态，只做一次纯校验，且需要先在推理请求上开启签名。

**完整流程**

1. 客户端生成随机 nonce（推荐 UUID v4），在推理请求头加 `X-Msh-Request-Nonce: <nonce>`（三个推理接口都支持，流式/非流式都行）。
2. 响应头返回 `Msh-Request-Timestamp`（Kimi 接受请求时的 Unix **毫秒**时间戳，int64）与 `Msh-Request-Signature`（`reqsigv1_` 前缀的不透明 token，由 Kimi 基于 nonce、timestamp、请求体 `model` 签发）。
3. 任意持有 (nonce, timestamp, model, signature) 四元组的一方，把它们 POST 到本接口；四者与签发时完全一致 → `{"valid": true}`，否则 `{"valid": false}`。

**关键参数**（请求体，全部必填）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `nonce` | string | 是 | — | 调用时通过 `X-Msh-Request-Nonce` 发送的 nonce，需与原值完全一致（minLength 1） |
| `timestamp` | integer(int64) | 是 | — | 响应头 `Msh-Request-Timestamp` 的 Unix 毫秒时间戳（minimum 1）。注意是**整数**不是字符串 |
| `model` | string | 是 | — | 调用时请求体中的 `model`，需完全一致 |
| `signature` | string | 是 | — | 响应头 `Msh-Request-Signature` 的签名 token |

**示例请求**

```bash
NONCE="$(uuidgen)"
MODEL="kimi-k3"

# 1. 带 nonce 调用推理接口，把响应头存到文件（此处用 Responses，Chat/Messages 同理）
curl -sS -D response.headers -o response.json \
  https://api.moonshot.cn/v1/responses \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -H "Content-Type: application/json" \
  -H "X-Msh-Request-Nonce: $NONCE" \
  -d "{\"model\": \"$MODEL\", \"input\": \"你好\"}"

TIMESTAMP="$(awk -F': ' 'tolower($1)=="msh-request-timestamp" {gsub("\\r", "", $2); print $2}' response.headers)"
SIGNATURE="$(awk -F': ' 'tolower($1)=="msh-request-signature" {gsub("\\r", "", $2); print $2}' response.headers)"

# 2. 校验
curl -sS https://api.moonshot.cn/v1/signatures/verify \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"nonce\": \"$NONCE\", \"timestamp\": $TIMESTAMP, \"model\": \"$MODEL\", \"signature\": \"$SIGNATURE\"}"
```
```python
import os, uuid, requests
from openai import OpenAI

api_key = os.environ["MOONSHOT_API_KEY"]
nonce = str(uuid.uuid4())
model = "kimi-k3"

# 方式 A：Responses 协议，用 with_raw_response 读响应头
oa = OpenAI(api_key=api_key, base_url="https://api.moonshot.cn/v1")
raw = oa.responses.with_raw_response.create(
    model=model, input="你好",
    extra_headers={"X-Msh-Request-Nonce": nonce},
)
timestamp = int(raw.headers["Msh-Request-Timestamp"])
signature = raw.headers["Msh-Request-Signature"]
# 方式 B：Messages 协议同理——Anthropic(base_url="https://api.moonshot.cn/anthropic")
#   .messages.with_raw_response.create(..., extra_headers={"X-Msh-Request-Nonce": nonce})

verify = requests.post(
    "https://api.moonshot.cn/v1/signatures/verify",
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    json={"nonce": nonce, "timestamp": timestamp, "model": model, "signature": signature},
)
print(verify.json())  # {"valid": true}
```

**示例响应**

```json
{"valid": true}
```

响应头 `Cache-Control: no-store`（固定，校验结果不应被缓存）。

**注意事项**

- **签名只证明"Kimi API 在该时间点接受了这个 nonce 和 model"**，不证明请求最终成功、不证明响应内容完整、也不绑定请求/响应正文。
- **服务端不记录 nonce**：重放同一组四元组仍返回 `valid: true`。防重放、有效时间窗口（比如只接受 `timestamp` 在 N 分钟内的签名）要由调用方自己实现。
- 签名算法不公开（token 是不透明的 `reqsigv1_...`），**无法离线校验**，只能调本接口；本接口有 429 限流，不要每个请求都同步校验。
- `X-Msh-Request-Nonce` 只允许一个非空值；值不合法时推理请求照常成功但**不返回**两个签名头——读 header 前先判存在，不要假设一定有。
- `timestamp` 必须按整数传（curl 里不要加引号）；`model` 必须和推理请求体一字不差。经代理/网关调用时，网关必须透传 `X-Msh-Request-Nonce` 请求头和两个 `Msh-Request-*` 响应头，否则拿不到签名——这恰恰是本接口要检测的场景。
- 签名与 API Key 的关系（能否用另一个 Key 校验别人的签名）`⚠ 文档未说明`；文档说"持有四元组的任何一方都可以验证"，但接口本身仍要求 Bearer 鉴权。
