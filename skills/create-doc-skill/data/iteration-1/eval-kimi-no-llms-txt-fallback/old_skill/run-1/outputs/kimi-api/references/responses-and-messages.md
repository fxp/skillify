# Responses API 与 Anthropic 兼容 Messages API

> 状态：文档草稿，基于 2026-09-03 抓取的 platform.moonshot.cn/docs 官方文档 + /docs/openapi.json 撰写，**尚未用真实 API 调用验证**。

## 三个入口怎么选

| | Chat Completions | Responses | Messages（Anthropic 兼容） |
|---|---|---|---|
| Endpoint | `POST /v1/chat/completions` | `POST /v1/responses` | `POST /anthropic/v1/messages` |
| base_url | `https://api.moonshot.cn/v1` | `https://api.moonshot.cn/v1` | `https://api.moonshot.cn/anthropic` |
| SDK | `openai` `chat.completions.create` | `openai` `responses.create` | `anthropic` `messages.create`、Claude Code |
| 支持模型 | k3 / k2.7-code(-highspeed) / k2.6 | **仅 `kimi-k3`** | **仅 `kimi-k3`**（OpenAPI 枚举） |
| 推理强度 | `reasoning_effort` (K3) / `thinking` (K2.x) | `reasoning.effort` | `output_config.effort` |
| 结构化输出 | `response_format` | `text.format` (`json_schema`) | `output_config.format` (`json_schema`) |
| 工具 | `tools[].function` | `tools[]` function / **namespace** | `tools[]` (`input_schema`) |
| tool_choice | auto/none/required(K3) | **只有 `auto`** | `{type: auto/any/none}` |
| 状态保存 | 无状态 | 无状态（`store`/`previous_response_id`/`conversation` 固定 false/null） | 无状态 |
| Batch / Files | 支持 | 不支持（Batch 只认 chat/completions） | 不支持 |
| 用谁 | 默认；要 K2.x、Batch、流式最成熟 | 已有 Responses 代码、想要 namespace 工具 | 已有 Anthropic SDK / Claude Code 代码 |

结论：新项目默认走 Chat Completions（见 `chat-completions.md`）。另外两个入口是"迁移免改代码"用的。

---

## 1. Responses API

**Endpoint**: `POST /v1/responses`
**用途**: OpenAI Responses 兼容；输入文本/图片，输出文本/JSON，或调用函数工具。`stream: true` 时 SSE。

### 关键参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | — | 当前只支持 `kimi-k3` |
| `input` | string \| array | 是 | — | 字符串 = 一条 user 消息；数组 = 带 `type` 的 item 列表（见下） |
| `instructions` | string | 否 | — | 顶层系统指令 |
| `stream` | bool | 否 | false | SSE 事件流 |
| `max_output_tokens` | int | 否 | 131072 | 最大 1048576（只算输出） |
| `reasoning.effort` | `low`/`high`/`max` | 否 | `max` | 推理强度 |
| `text.format` | object | 否 | — | `{"type":"json_schema","name":"output","schema":{...},"strict":true}` |
| `tools` | array | 否 | — | `{"type":"function","name","description","parameters","strict"}` 或 `{"type":"namespace","name","description","tools":[...]}` |
| `tool_choice` | string | 否 | `auto` | **枚举只有 `auto`** |
| `prompt_cache_key` | string | 否 | — | 同一会话固定，提升缓存命中 |
| `safety_identifier` | string | 否 | — | 终端用户哈希 ID |

`input` 数组 item 类型：
| type | 说明 |
|---|---|
| `message`（可省略 type） | `role`: `user`/`assistant`/`developer`（developer 按系统指令处理）；`content` 字符串或 content part 数组 |
| `reasoning` | 回放上一轮推理：`content: [{"type":"reasoning_text","text"}]`（优先）或 `summary: [{"type":"summary_text","text"}]` |
| `function_call` | 回放模型的调用：`call_id`、`name`、`arguments`(JSON 字符串)、可选 `namespace` |
| `function_call_output` | 工具结果：`call_id` 与上面配对，`output` 字符串或数组 |
| `additional_tools` | 对话中途追加工具：`role: developer`，`tools: [...]`，从该位置起生效 |

### 示例

```python
import os
from openai import OpenAI
client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

resp = client.responses.create(
    model="kimi-k3",
    instructions="你是 Kimi，一个由 Moonshot AI 提供的人工智能助手。",
    input="用一句话解释什么是上下文缓存。",
)
print(resp.output_text)          # SDK 便捷属性；原始结构见下
```
```bash
curl https://api.moonshot.cn/v1/responses \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"kimi-k3","instructions":"你是 Kimi。","input":"用一句话解释什么是上下文缓存。"}'
```

### 响应结构

```json
{"id": "resp_xxx", "object": "response", "created_at": 1720000000, "completed_at": 1720000005,
 "status": "completed",            // in_progress | completed | incomplete | failed
 "model": "kimi-k3",
 "output": [                        // 顺序：reasoning → message → function_call
   {"type": "reasoning", "id": "...", "summary": [{"type": "summary_text", "text": "..."}], "encrypted_content": null, "status": "completed"},
   {"type": "message", "id": "...", "role": "assistant", "status": "completed",
    "content": [{"type": "output_text", "text": "...", "annotations": []}]},
   {"type": "function_call", "id": "...", "call_id": "call_xxx", "name": "get_weather", "arguments": "{\"city\":\"北京\"}", "status": "completed"}
 ],
 "usage": {"input_tokens": 0, "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
           "output_tokens": 0, "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 0},
 "incomplete_details": null,       // {"reason": "max_output_tokens" | "content_filter"} when status=incomplete
 "error": null,                    // {"code","message"} when status=failed
 "store": false, "background": false, "previous_response_id": null, "conversation": null}
```

### 工具调用回合（Responses 风格）

```python
tools = [{"type": "function", "name": "get_weather", "description": "查天气",
          "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}]

r1 = client.responses.create(model="kimi-k3", input="北京天气如何？", tools=tools)
history = [{"role": "user", "content": "北京天气如何？"}]
history += [item.model_dump(exclude_none=True) for item in r1.output]      # 原样回放 reasoning + function_call
for item in r1.output:
    if item.type == "function_call":
        history.append({"type": "function_call_output", "call_id": item.call_id,
                        "output": '{"weather": "晴", "temperature_c": 24}'})
r2 = client.responses.create(model="kimi-k3", input=history, tools=tools)
print(r2.output_text)
```
把上一轮 `output` 里的 `reasoning` 和 `function_call` item 原样放回 `input`——这是 K3 Preserved Thinking 的要求（与 Chat Completions 里"原样回传完整 assistant message"同理）。

### 流式事件

`stream: true` 时每帧 `event: <type>` + `data: <json>`，`sequence_number` 从 0 单调递增。事件类型（OpenAPI 枚举）：`response.created`、`response.in_progress`、`response.output_item.added/done`、`response.content_part.added/done`、`response.output_text.delta/done`、`response.reasoning_summary_text.delta/done`（推理增量）、`response.function_call_arguments.delta/done`、`response.completed` / `response.incomplete` / `response.failed`（末尾事件带完整 response 快照）。

```python
with client.responses.stream(model="kimi-k3", input="写一首四行诗") as s:
    for ev in s:
        if ev.type == "response.output_text.delta":
            print(ev.delta, end="", flush=True)
    final = s.get_final_response()
```

来源: docs/api/responses, schema/responses

---

## 2. Messages API（Anthropic 兼容）

**Endpoint**: `POST /anthropic/v1/messages`（base_url `https://api.moonshot.cn/anthropic`）
**用途**: 已用 Anthropic SDK / Claude Code 的项目零改代码接入 Kimi。

### 关键参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | — | `kimi-k3`（OpenAPI 枚举唯一值；Claude Code 教程里用别名 `kimi-k3[1m]`） |
| `messages` | array | 是 | — | `role` 只有 `user`/`assistant`；系统提示放顶层 `system`。最后一条是 assistant → 从其内容后续写（Partial Mode） |
| `max_tokens` | int | **是** | — | Anthropic 风格必填；到上限 `stop_reason=max_tokens` |
| `system` | string \| text 块数组 | 否 | — | 系统提示 |
| `stream` | bool | 否 | false | SSE |
| `stop_sequences` | array | 否 | — | ≤5 个，每个 ≤32 字节 |
| `tools` | array | 否 | — | `{"name","description","input_schema"}`（`type: custom` 可省）；`input_schema` 顶层必须 `object`，遵循 MFJS |
| `tool_choice` | object | 否 | `{type: auto}` | `auto` / `any` / `none` |
| `metadata.user_id` | string | 否 | — | 稳定终端用户 ID（哈希后） |
| `output_config.effort` | `low`/`high`/`max` | 否 | `max` | 推理强度；中途切换会破坏前缀缓存 |
| `output_config.format` | object | 否 | — | `{"type":"json_schema","schema":{...}}` 结构化输出 |

内容块：`text`、`image`（`source.type` = `base64`(+`media_type` jpeg/png/gif/webp +`data`) 或 `url`(`ms://<file_id>`)）、`thinking`（`thinking` + `signature`，多轮时**原样放回** assistant 消息）、`tool_use`（assistant 侧：`id/name/input`）、`tool_result`（user 侧：`tool_use_id/content`）。

注意：**没有 Anthropic 的 `thinking: {type, budget_tokens}` 参数**——K3 始终思考，强度用 `output_config.effort`。

### 示例

```python
import os
from anthropic import Anthropic
client = Anthropic(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/anthropic")

msg = client.messages.create(
    model="kimi-k3",
    max_tokens=4096,
    system="你是 Kimi。",
    messages=[{"role": "user", "content": "用一句话介绍你自己"}],
)
for block in msg.content:            # 顺序：thinking → text → tool_use
    if block.type == "text":
        print(block.text)
print(msg.stop_reason, msg.usage)
```
```bash
curl https://api.moonshot.cn/anthropic/v1/messages \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"kimi-k3","max_tokens":1024,"messages":[{"role":"user","content":"你好"}]}'
```
（文档示例只用了 `Authorization: Bearer`；Anthropic SDK 自己会发 `x-api-key` / `anthropic-version` 头，是否被网关接受见疑点。）

### 响应结构

```json
{"id": "msg_xxx", "type": "message", "role": "assistant", "model": "kimi-k3",
 "content": [{"type": "thinking", "thinking": "...", "signature": "..."},
             {"type": "text", "text": "..."},
             {"type": "tool_use", "id": "toolu_xxx", "name": "get_weather", "input": {"city": "北京"}}],
 "stop_reason": "end_turn",         // end_turn | max_tokens | tool_use | refusal
 "stop_sequence": null,
 "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
           "cache_creation_input_tokens": 0, "output_tokens_details": {"thinking_tokens": 0}}}
```
`usage.input_tokens` **不含**缓存命中部分（与 Responses 的 `input_tokens` 含缓存相反）。

### 流式事件

顺序 `message_start` → (`content_block_start` → `content_block_delta`… → `content_block_stop`)… → `message_delta`(带 `stop_reason` + usage) → `message_stop`。`content_block_delta.delta.type` ∈ `text_delta` / `thinking_delta` / `signature_delta` / `input_json_delta`（`partial_json` 需拼接后 `json.loads`）。

```python
with client.messages.stream(model="kimi-k3", max_tokens=2048,
                            messages=[{"role": "user", "content": "写一首四行诗"}]) as s:
    for text in s.text_stream:
        print(text, end="", flush=True)
```

### 错误格式差异
Messages 入口的 400/500 返回 Anthropic 风格：`{"type": "error", "error": {"type", "message"}, "request_id"}`；401 仍是 OpenAI 风格 `{"error": {...}}`。

来源: docs/api/messages, docs/api/overview, schema/messages

---

## 待验证疑点

- Responses / Messages 的 `model` 枚举只有 `kimi-k3`：传 `kimi-k2.6` 是 404 还是 400，报错原文。
- Responses `tool_choice` 只有 `auto`：传 `required` / 指定函数对象时是报错还是静默当 auto。
- Responses 响应里 `temperature`/`top_p` 字段回显什么（请求不接受这两个参数，响应却有字段）；请求传 `temperature` 是否报错。
- Responses 流式事件的完整枚举（schema 中被截断），以及 `response.reasoning_summary_text.delta` 是否真的输出推理增量。
- OpenAI SDK `responses.create` 是否会因为 `namespace` 工具类型做客户端校验失败。
- Messages：Anthropic SDK 默认发 `x-api-key` 与 `anthropic-version` 头而非 `Authorization: Bearer`——网关是否两种都接受（docs/api/overview 的示例暗示 SDK 直接可用，需实测）。
- Messages：Anthropic SDK 会传 `thinking: {"type":"enabled","budget_tokens":N}` 的旧代码，网关是报错还是忽略。
- Messages：`max_tokens` 缺省时是否真的 400（schema 标必填）。
- Messages 图片 `media_type` 枚举只有 jpeg/png/gif/webp（比 Chat 的 7 种少），bmp/heic 是否被拒。
- Messages 的 `stop_reason: refusal` 触发条件；`request_id` 是否在成功响应头里也有。
- 两个入口的上下文缓存是否与 Chat Completions 共享前缀（同一 system prompt 跨入口能否命中）。
