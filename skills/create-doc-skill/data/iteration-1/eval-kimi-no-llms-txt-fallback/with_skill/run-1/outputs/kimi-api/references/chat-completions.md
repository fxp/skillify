> 内容整理自 platform.kimi.com/docs（抓取于 2026-09-03），**尚未用真实 API 调用验证**；实际报错优先信任 API。

# Kimi API — `POST /v1/chat/completions` 全用法参考

Base URL `https://api.moonshot.cn/v1`；鉴权 `Authorization: Bearer $MOONSHOT_API_KEY`；请求体 `Content-Type: application/json`。
Python 示例统一用 `openai` SDK：`OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")`。
Kimi 专有的**请求顶层**参数（`thinking`、`prompt_cache_key`）在 SDK 里**必须走 `extra_body`**；专有的**消息级**字段（`partial`、`reasoning_content`、`video_url`）写在 `messages` 的 dict 里即可原样透传。

## 目录

1. [我想发一条消息拿到回复（基本请求 / 响应）](#1-基本请求--响应)
2. [我想做多轮对话并控制上下文长度](#2-多轮对话与上下文长度控制)
3. [我想边生成边显示（流式输出 SSE）](#3-流式输出sse)
4. [我想拿到结构化 JSON（JSON Mode vs Structured Output）](#4-json-mode--structured-outputresponse_format)
5. [我想固定回复开头 / 续写被截断的输出（Partial Mode）](#5-partial-mode)
6. [我想降低重复长上下文的成本（Context Caching）](#6-context-caching)
7. [我想让模型看图 / 看视频（视觉输入）](#7-视觉输入图片--视频)
8. [我想在断线时自动恢复（自动重连）](#8-自动断线重连)
9. [附录：参数速查、SDK 传参、错误](#9-附录)

## 1. 基本请求 / 响应

### 发送一条消息并获取回复

**Endpoint**: `POST /v1/chat/completions`  
**用途**: 无状态的一次性补全：把 `messages` 发给模型，拿回一条 `assistant` 消息。后面所有功能（流式、JSON、Partial、视觉、缓存）都是在这个请求体上加字段，不换 endpoint。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | — | `kimi-k3` / `kimi-k2.7-code` / `kimi-k2.7-code-highspeed` / `kimi-k2.6`。OpenAPI 按 `model` 做 discriminator，各模型接受的专有参数不同（见附录） |
| `messages` | array | 是 | — | 每条 `{"role","content"}`；`role` ∈ `system` / `user` / `assistant` / `tool`；`content` 为 string 或多模态 object 数组，**不得为空** |
| `messages[].name` | string | 否 | null | 发送者名称；在 Partial Mode 里有特殊语义（§5） |
| `max_completion_tokens` | integer | 否 | 因模型而异（K3 默认 131072，上限 1048576） | 只算输出长度。输入 + 该值超出上下文窗口 → 400 `invalid_request_error` |
| `max_tokens` | integer | 否 | — | OpenAPI 标记**已弃用**，改用 `max_completion_tokens`；但所有 guide 示例仍在用 `max_tokens`（⚠ 文档自相矛盾，两者目前应都可用，实测为准） |
| `stop` | string \| string[] | 否 | null | 最多 5 个，每个 ≤ 32 字节；匹配到的词本身不输出 |
| `reasoning_effort` | string | 否 | `max` | **仅 `kimi-k3`**：`low` / `high` / `max`。K3 始终思考且 Preserved Thinking 常开 |
| `thinking` | object | 否 | k2.6 `{"type":"enabled"}`；k2.7-code `{"type":"enabled","keep":"all"}` | **仅 K2.x**：`type` ∈ `enabled` / `disabled`（k2.7-code 只接受 `enabled`）；`keep` ∈ `"all"` / `null`。SDK 走 `extra_body` |
| `prompt_cache_key` | string | 否 | null | 会话/任务级缓存键（§6） |
| `safety_identifier` | string | 否 | — | 终端用户稳定标识（建议哈希后传） |
| `logprobs` / `top_logprobs` | boolean / integer 0-20 | 否 | false / — | `top_logprobs` 必须配合 `logprobs: true` |

`temperature`、`top_p`、`n`：⚠ 文档未说明 —— OpenAPI 摘要里**没有**这三个字段；vision 页只说"各模型取值约束不同，建议不要手动设置"；streaming 页说当前模型 `n` 固定为 1，>1 返回 400 `invalid n: only 1 is allowed for this model`。

**示例请求**

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k3",
    "messages": [
      {"role": "system", "content": "你是 Kimi，由 Moonshot AI 提供的人工智能助手。"},
      {"role": "user", "content": "你好，我叫李雷，1+1等于多少？"}
    ],
    "reasoning_effort": "low",
    "max_completion_tokens": 4096
  }'
```

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[
        {"role": "system", "content": "你是 Kimi，由 Moonshot AI 提供的人工智能助手。"},
        {"role": "user", "content": "你好，我叫李雷，1+1等于多少？"},
    ],
    reasoning_effort="low",            # SDK 原生有这个参数名，可直接传
    max_completion_tokens=4096,
    # extra_body={"thinking": {"type": "disabled"}},   # 换 kimi-k2.6 时，专有参数走 extra_body
)
msg = completion.choices[0].message
print(msg.content, getattr(msg, "reasoning_content", None))   # reasoning_content 仅思考模型有；SDK 类型未声明，用 getattr
```

**示例响应**

```json
{
  "id": "cmpl-04ea926191a14749b7f2c7a48a68abc6", "object": "chat.completion", "created": 1698999496, "model": "kimi-k3",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "你好，李雷！1+1等于2。", "reasoning_content": "用户问的是基础数学问题，直接相加即可。"},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 19, "completion_tokens": 21, "total_tokens": 40, "cached_tokens": 10}
}
```

`finish_reason` ∈ `stop` / `length` / `tool_calls`；`message.content` 可为 `null`（如纯工具调用）。

**注意事项**

- `reasoning_content` 是 Kimi 扩展字段，OpenAI SDK 类型里没有；Python 用 `getattr`，Node 直接读属性。
- `max_completion_tokens` 会先被思考消耗：K3 默认思考，值太小可能截断在思考阶段 —— `content` 为空且 `finish_reason="length"`。
- `logprobs` 返回位置：OpenAPI 描述写"响应 message 的 logprobs 字段"，但响应 schema 未定义该字段 —— ⚠ 文档未说明（OpenAI 在 `choices[].logprobs`），实测为准。
- 可选请求头 `X-Msh-Request-Nonce`（UUID v4）：携带后响应头返回 `Msh-Request-Timestamp` / `Msh-Request-Signature` 供事后校验；值不合法时请求照常执行但不返回签名头。已下线模型（`moonshot-v1-*`、`kimi-k2.5`、`kimi-k2-*`、`kimi-latest`、`kimi-thinking-preview`）返回 404；中国站 `api.moonshot.cn` 与国际站 `platform.kimi.ai` 的 key 完全隔离，混用 401。

## 2. 多轮对话与上下文长度控制

### 让模型"记住"之前聊过的内容

**Endpoint**: `POST /v1/chat/completions`（无会话 API）  
**用途**: API 完全无状态，没有 conversation id；"记忆" = 你把历史 `user` / `assistant`（含 `tool`）消息按时间顺序拼进 `messages` 再发。与 §6 配合可显著降低重复前缀成本。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `messages` | array | 是 | — | 顺序：system → 历史 user/assistant 交替 → 最新 user |
| `messages[].reasoning_content` | string | 否 | — | 思考模型的历史 assistant 消息应**原样带回**该字段（Preserved Thinking）。K3、k2.7-code 常开；k2.6 需 `thinking.keep="all"` 才会用到，默认 `null` 时服务端忽略 |
| `thinking.keep` | `"all"` \| null | 否 | k2.6: null；k2.7-code: `"all"`（固定） | 只影响**历史轮次**的 `reasoning_content` 是否进上下文，不影响当前轮是否思考 |

**示例请求**

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k3",
    "messages": [
      {"role": "system", "content": "你是 Kimi。"},
      {"role": "user", "content": "你好，我今年 27 岁。"},
      {"role": "assistant", "content": "你好！很高兴认识你。", "reasoning_content": "用户自我介绍，礼貌回应即可。"},
      {"role": "user", "content": "你知道我今年几岁吗？"}]
  }'
```

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

system_messages = [{"role": "system", "content": "你是 Kimi，由 Moonshot AI 提供的人工智能助手。"}]
history: list = []            # 只存 user/assistant；system 单独存，截断时才不会被截掉

def make_messages(user_input: str, n: int = 20) -> list:
    global history
    history.append({"role": "user", "content": user_input})
    if len(history) > n:      # 只保留最新 n 条，粗略控制上下文长度
        history = history[-n:]
    return system_messages + history

def chat(user_input: str) -> str:
    completion = client.chat.completions.create(model="kimi-k3", messages=make_messages(user_input))
    msg = completion.choices[0].message
    history.append(msg)       # 直接 append SDK 的 message 对象：会带上 reasoning_content（Preserved Thinking 需要）
    return msg.content

print(chat("你好，我今年 27 岁。"))
print(chat("你知道我今年几岁吗？"))   # 期望：27 岁
```

**示例响应**：与 §1 相同；第二轮起 `usage.cached_tokens` 通常 > 0（前缀命中缓存，见 §6）。

**注意事项**

- 截断历史时**必须保留 system 消息**：官方做法是 system 单独一个列表、每次拼在最前。API 页的多轮示例只 append `{"role":"assistant","content": reply.content}`，guide 页 append 整个 message 对象（含 `reasoning_content`）；思考模型下用后者，否则"模型可能丢失推理上下文"（API 页 Warning）。
- 更精细的做法（文档只提方向未给实现）：按 token 数截断（`POST /v1/tokenizers/estimate-token-count` 估算）、对丢弃的旧消息做摘要后插回、多用户各自维护 `messages`、持久化、并发加锁。
- Kimi 允许 system 出现在任意位置：长对话角色漂移时可在中间**再插一条 system 消息**强化设定（§5）；K3 还可在任意位置插入 `{"role":"system","tools":[...]}`（无 `content`）动态加载工具，只影响其后的对话。

## 3. 流式输出（SSE）

### 边生成边返回，并在最后拿到 usage

**Endpoint**: `POST /v1/chat/completions`，请求体 `"stream": true`；响应 `Content-Type: text/event-stream`  
**用途**: 降低首 token 等待。与非流式的区别：`choices[].message` 变成 `choices[].delta`，每个 chunk 只带增量；`usage` 只在最后的 chunk 出现。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `stream` | boolean | 否 | false | 开启 SSE |
| `stream_options.include_usage` | boolean | 否 | false | 为 true 时在 `data: [DONE]` 前追加一个 `choices: []`、顶层 `usage` 为对象的统计 chunk；其它 chunk 的 `usage` 为 `null`。流中断则收不到 |

**示例请求**

```bash
curl -N https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k3",
    "messages": [{"role": "user", "content": "请解释什么是递归。"}],
    "stream": true,
    "stream_options": {"include_usage": true}
  }'
```

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")
stream = client.chat.completions.create(
    model="kimi-k3",
    messages=[{"role": "user", "content": "请解释什么是递归。"}],
    stream=True,
    stream_options={"include_usage": True},
)

usage, finish_reason, reasoning, content = None, None, "", ""

for chunk in stream:
    # usage：优先顶层；官方示例还兼容 choices[0].usage（见下方“文档自相矛盾”）
    chunk_usage = chunk.usage or (getattr(chunk.choices[0], "usage", None) if chunk.choices else None)
    if chunk_usage:
        usage = chunk_usage
    if not chunk.choices:                        # 最终统计 chunk 的 choices 为空，别写 chunk.choices[0]
        continue
    choice = chunk.choices[0]
    delta = choice.delta
    if choice.finish_reason:
        finish_reason = choice.finish_reason
    frag = getattr(delta, "reasoning_content", None)   # 思考片段先于 content 到达；SDK 类型未声明
    if frag:
        reasoning += frag
    if delta.content:
        content += delta.content
        print(delta.content, end="", flush=True)
    # delta.tool_calls：同一调用的片段共享 index；id/type/function.name 只在首片段出现；
    # function.arguments 是 JSON 字符串片段，按 index 追加拼接，流结束后再 json.loads

print("\nfinish_reason:", finish_reason, "usage:", usage)
```

**示例响应**（SSE 原文：每个事件 `data: ` + JSON + `\n\n`）

```text
data: {"id":"cmpl-xxx","object":"chat.completion.chunk","created":1698999575,"model":"kimi-k3","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"cmpl-xxx","object":"chat.completion.chunk","created":1698999575,"model":"kimi-k3","choices":[{"index":0,"delta":{"content":"你好"},"finish_reason":null}]}

...

data: {"id":"cmpl-xxx","object":"chat.completion.chunk","created":1698999575,"model":"kimi-k3","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":19,"completion_tokens":13,"total_tokens":32,"cached_tokens":12}}

data: {"id":"cmpl-xxx","object":"chat.completion.chunk","created":1698999575,"model":"kimi-k3","choices":[],"usage":{"prompt_tokens":19,"completion_tokens":13,"total_tokens":32}}

data: [DONE]
```

**注意事项**

- **以 `data: [DONE]` 作为唯一"传输完成"信号**；收到 `finish_reason=stop` 但没收到 `[DONE]` 仍视为不完整。`role` 只在第一个 chunk 的 `delta` 出现一次。
- `usage` 出现位置 —— ⚠ 文档自相矛盾：API 页示例把 `usage` 放在 `finish_reason="stop"` 那个 chunk 的**顶层**（且未开 `include_usage`）；streaming guide 示例是 finish chunk 里的 `choices[0].usage` + 之后一个 `choices: []` 的独立统计 chunk（顶层 `usage`）；OpenAPI 的 `ChoiceDelta` 也定义了 `usage`。官方代码同时读顶层 `chunk.usage` 和 `choices[0].usage`，照抄这个防御写法。
- `cached_tokens`：OpenAPI 顶层 chunk `usage` 有，`ChoiceDelta.usage` 没有 —— ⚠ 文档未说明流式下该字段在哪一层可靠出现。
- 自己解析 SSE：按行读、只处理 `data: ` 前缀、`[DONE]` 退出；不要假设每个 chunk 都有 `choices[0]`。提前终止：`break` / 关闭连接即可，无取消 API。
- 流被打断拿不到 usage：把已收到的 content 存下来，事后用 `POST /v1/tokenizers/estimate-token-count`（body `{"model","messages"}`，读 `data.total_tokens`）估算。
- `tool_calls` 片段的 `type` 与声明一致（`function` 或 `builtin_function`）；`finish_reason="tool_calls"` 后把 assistant 消息（含 `tool_calls` 与折叠后的 `reasoning_content`）和 `role="tool"` 结果追加进 `messages` 再调一次。

## 4. JSON Mode / Structured Output（`response_format`）

### 用 `response_format` 拿到可解析的 JSON

**Endpoint**: `POST /v1/chat/completions`  
**用途**: 同一个参数、两种模式。`json_object`（JSON Mode）只保证"一个合法 JSON Object"，字段名/类型不保证、可能多字段，字段必须在 prompt 里描述（最好给示例），适合原型；`json_schema`（Structured Output）按 schema 严格约束字段名/类型/嵌套（`strict: true` 时 token 级约束解码，`additionalProperties: false` 可禁止额外字段），prompt 只需描述业务任务，适合生产 / 对接下游。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `response_format.type` | string | 否 | `text` | `text` / `json_object` / `json_schema` |
| `response_format.json_schema.name` | string | type=json_schema 时必填 | — | 标识名，用于日志/调试 |
| `response_format.json_schema.schema` | object | type=json_schema 时必填 | — | JSON Schema，需符合 **MFJS（Moonshot Flavored JSON Schema）**；不是 object 时 400 `invalid_request_error` |
| `response_format.json_schema.strict` | boolean | 否 | OpenAPI: `true`；guide: 建议显式设 `true` | `true`：约束解码；`false`：只保证合法 JSON Object |

**示例请求**

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k3",
    "messages": [
      {"role": "system", "content": "你是一个新闻摘要助手。"},
      {"role": "user", "content": "请总结以下新闻：今日，人工智能技术领域迎来重大突破..."}
    ],
    "response_format": {
      "type": "json_schema",
      "json_schema": {
        "name": "news_summary", "strict": true,
        "schema": {
          "type": "object",
          "properties": {"title": {"type": "string"}, "author": {"type": ["string", "null"]},
                         "keywords": {"type": "array", "items": {"type": "string"}}},
          "required": ["title", "author", "keywords"], "additionalProperties": false
        }
      }
    }
  }'
```

```python
import os, json
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

# 1) JSON Mode：字段靠 prompt 描述
completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[
        {"role": "system", "content": '请用 JSON 输出，格式：{"text": "文字信息", "image": "图片地址", "url": "链接地址"}'},
        {"role": "user", "content": "你好，我叫李雷，1+1等于多少？"},
    ],
    response_format={"type": "json_object"},
)
if completion.choices[0].finish_reason == "length":
    raise RuntimeError("JSON 被截断，增大 max_completion_tokens")
data = json.loads(completion.choices[0].message.content)   # 只解析 content，不要解析整个响应对象

# 2) Structured Output：字段靠 schema
schema = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "新闻标题"},
        "author": {"type": ["string", "null"], "description": "缺失时给 null"},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "author", "keywords"],
    "additionalProperties": False,
}
completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[{"role": "system", "content": "你是一个新闻摘要助手。"},
              {"role": "user", "content": "请总结以下新闻：今日，人工智能技术领域迎来重大突破..."}],
    response_format={"type": "json_schema", "json_schema": {"name": "news_summary", "strict": True, "schema": schema}},
)
result = json.loads(completion.choices[0].message.content)
```

**示例响应**：`choices[0].message.content` 为序列化字符串，如 `"{\"title\": \"人工智能技术取得重大突破\", \"author\": \"科技日报\", \"keywords\": [\"人工智能\", \"深度学习\"]}"`；思考模型同时有 `reasoning_content`。

**注意事项**

- 两种模式都只生成 JSON **Object**，不要引导它输出 JSON Array 或标量；`json_object` 不在 prompt 里说明字段 → 输出结构不可预期。
- `strict` 默认值 —— ⚠ 文档自相矛盾：OpenAPI 写 `default: true`，guide 说"省略时 k2.6 更易输出 schema 外字段、建议显式设 true"。**始终显式写 `strict: true`** 就没有歧义。
- 模型差异：`kimi-k2.7-code` 最稳（嵌套/数组/`anyOf`/`oneOf`/`$ref`/`additionalProperties: true` 都可）；`kimi-k3` 稳定支持嵌套、数组、`anyOf`；`kimi-k2.6` 复杂 schema 不稳（`$ref` 可能回 Markdown 代码块、`oneOf` 可能被忽略），业务层需剥掉 ```` ```json ```` 包裹并二次校验。
- `required` 字段必现；信息缺失想让模型给 `null` 而不是编造，用联合类型 `"type": ["integer", "null"]`（k2.6 仍可能返回空字符串）。schema 含 MFJS 不支持的特性时 API 也常返回 200 且**不会**有 `warning` 字段；静态自检用 `walle` CLI：`go install github.com/moonshotai/walle/cmd/walle@latest && walle -schema '<schema json>' -level strict`。
- 设置/更换 `response_format` **不会破坏前缀缓存**。截断（`finish_reason="length"`）时增大 `max_tokens`、简化嵌套或缩短输入。
- **不要把 `json_object` 与 Partial Mode 混用**（API 页 Warning）；想引导 JSON 开头，二选一：用 `json_schema`，或不设 response_format、只用 `partial: true` 预填 `{`。`json_schema` + partial：k2.7-code 简单 schema 通常正常，复杂 schema 可能破坏约束；k2.6 不建议混用。

## 5. Partial Mode

### 让模型从指定前缀继续写（固定开头 / 续写截断 / 角色扮演）

**Endpoint**: `POST /v1/chat/completions`  
**用途**: 在 `messages` **末尾**放一条 `role="assistant"` 且 `partial: true` 的消息，模型强制以其 `content` 开头往下生成（Prefill）。区别于 §4：Partial 约束"开头文本"而非结构；区别于 OpenAI：OpenAI 无该字段，末尾 assistant 消息会被当成普通历史。

**关键参数**（都写在**消息**上，不是请求顶层）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `messages[-1].role` + `partial` | string + boolean | 是 | partial 默认 false | 最后一条消息 `role="assistant"` 且 `partial: true` |
| `messages[-1].content` | string | 是 | — | 前缀；可为空字符串 `""`（配合 `name`） |
| `messages[-1].name` | string | 否 | null | 角色名，作为输出前缀的一部分，强化角色口吻 |
| `messages[-1].reasoning_content` | string | 否 | — | 思考模型**续写截断输出**时，把上一轮返回的 `reasoning_content` 一并带回 |

**示例请求**

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k3",
    "messages": [
      {"role": "user", "content": "用 Python 实现快速排序。"},
      {"role": "assistant", "content": "```python\n", "partial": true}
    ]
  }'
```

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

# 1) 固定开头
prefix = "尊敬的用户您好，"
completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[{"role": "user", "content": "你好？"},
              {"role": "assistant", "content": prefix, "partial": True}],   # dict 原样透传，SDK 不校验多余字段
)
print(prefix + completion.choices[0].message.content)   # 响应不含前缀，要自己拼回去

# 2) 续写被截断的输出（思考模型要把 reasoning_content 带回）
q = [{"role": "user", "content": "请背诵完整的出师表。"}]
first = client.chat.completions.create(model="kimi-k3", messages=q, max_tokens=1200)
if first.choices[0].finish_reason == "length":
    m = first.choices[0].message
    second = client.chat.completions.create(
        model="kimi-k3",
        messages=q + [{"role": "assistant", "content": m.content, "partial": True,
                       "reasoning_content": getattr(m, "reasoning_content", None)}],
        max_tokens=86400,
    )
    print(m.content + second.choices[0].message.content)

# 3) 角色扮演：末尾放 {"role": "assistant", "name": "凯尔希", "content": "", "partial": True}，用 name 固定身份、content 留空
```

**示例响应**：与 §1 相同；`message.content` **只含续写部分**，不含你喂的前缀。

**注意事项**

- 最终文本 = 前缀 + `content`，要自己拼。续写截断内容时第一次请求的 `max_tokens` 要够大，保证截断落在正文而非思考阶段；截断在思考阶段时 `content` 为空，续写会从头生成。
- 思考模式下续写必须带回 `reasoning_content`；不带会怎样 ⚠ 文档未说明（示例注释只写"思考模式需要 reasoning_content"）。
- `partial` 放在非末尾消息上的行为 ⚠ 文档未说明（OpenAPI 只说"在最后一条 assistant 消息中设置为 true"）。与 `response_format` 的兼容性见 §4。
- 长对话保持人设：详细角色描述 + 语气/背景细节 + 对话中途**重新插入 system 消息** + 末尾 `partial` + `name`。

## 6. Context Caching

### 重复的长前缀自动降本

**Endpoint**: `POST /v1/chat/completions`（无独立缓存 API，无需创建 / 引用 / 删除缓存）  
**用途**: 全自动前缀缓存：服务端检测到与上一请求重复的初始上下文（system prompt、知识文档、工具定义……）就复用。与 RAG 的区别：不需要 embedding/召回，命中率取决于前缀是否稳定；适合固定文档问答、Copilot、瞬时高流量、规则复杂的 Agent。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `messages` 顺序 | — | — | — | 把固定大段内容放在**数组最前面（可在 system 消息之前）**，用户问题和回复追加其后 |
| `prompt_cache_key` | string | 否 | null | 会话/任务 id，用于把相似请求路由到同一缓存；Coding Agent 退出恢复会话时应保持不变；Kimi Code Plan 下**必填**。SDK 走 `extra_body` |

**示例请求**

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k3",
    "prompt_cache_key": "session-8f3c2a",
    "messages": [
      {"role": "system", "content": "<这里是几千 token 的固定知识文档……>"},
      {"role": "system", "content": "你是产品文档问答助手。"},
      {"role": "user", "content": "退款政策是什么？"}]
  }'
```

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")
KNOWLEDGE = open("product_docs.md", encoding="utf-8").read()   # 固定长文档，放最前面

def ask(question: str, session_id: str) -> str:
    completion = client.chat.completions.create(
        model="kimi-k3",
        messages=[{"role": "system", "content": KNOWLEDGE},
                  {"role": "system", "content": "你是产品文档问答助手。"},
                  {"role": "user", "content": question}],
        extra_body={"prompt_cache_key": session_id},   # Kimi 专有顶层参数 → extra_body
    )
    u = completion.usage
    print("prompt:", u.prompt_tokens, "cached:", getattr(u, "cached_tokens", None))
    return completion.choices[0].message.content

ask("退款政策是什么？", "session-8f3c2a")
ask("保修多久？", "session-8f3c2a")     # 第二次 cached_tokens 预期 > 0
```

**示例响应**

```json
"usage": {"prompt_tokens": 19, "completion_tokens": 21, "total_tokens": 40, "cached_tokens": 10}
```

**注意事项**

- 命中门槛：**前一个请求的 prompt tokens > 256** 时，新请求才能命中前缀缓存；前一个请求 < 256 则不会被缓存（原文"被丢弃"）。恰好 256 ⚠ 文档未说明。
- `usage.cached_tokens` 来自 OpenAPI 与 API 页示例；caching guide 正文完全没提该字段或任何 usage 字段（⚠ 文档未说明 cached_tokens 是否即"命中缓存的 prompt token 数"，按字段描述推断是）。
- 缓存 TTL、上限、跨 key / 跨模型是否共享：⚠ 文档未说明（只说"生命周期由系统自动管理"）；`prompt_cache_key` 只出现在 OpenAPI，caching guide 说"无需添加额外参数"—— 不冲突（可选优化），但效果 ⚠ 文档未说明。
- 改 `response_format` 不破坏前缀缓存；改前缀内容（system prompt、工具定义）会。计费见 `/docs/pricing/chat#计费逻辑`，材料未含具体价格。

## 7. 视觉输入（图片 / 视频）

### 让模型理解图片或视频

**Endpoint**: `POST /v1/chat/completions`；`messages[].content` 用 **object 数组**  
**用途**: `kimi-k3` / `kimi-k2.6` / `kimi-k2.7-code` / `kimi-k2.7-code-highspeed` 都支持图片和视频。与 OpenAI 的差别：**不支持 http(s) 图片 URL**，只支持 base64 data URL 和 `ms://<file_id>`；多了 `video_url` part 类型。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `content[].type` | string | 是 | — | `text` / `image_url` / `video_url` |
| `content[].image_url` | object \| string | type=image_url 时必填 | — | `{"url": "..."}` 或直接字符串；`url` 取值：`data:image/<fmt>;base64,...` 或 `ms://<file_id>` |
| `content[].video_url` | object \| string | type=video_url 时必填 | — | 同上：`data:video/mp4;base64,...` 或 `ms://<file_id>` |
| 文件上传 | — | — | — | 先 `client.files.create(file=Path(...), purpose="image" 或 "video")`，再用 `ms://{file.id}` 引用（上传接口详见 files 文档） |

**示例请求**

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k3",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQ..."}},
        {"type": "image_url", "image_url": "data:image/png;base64,iVBORw0..."},
        {"type": "text", "text": "比较这两张图的差异。"}
      ]
    }]
  }'
```

```python
import os, base64
from pathlib import Path
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

def to_data_url(path: str) -> str:
    ext = os.path.splitext(path)[1].lstrip(".")          # png / jpeg / webp ...
    return f"data:image/{ext};base64," + base64.b64encode(Path(path).read_bytes()).decode("utf-8")

# 1) 多图 base64
completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[{"role": "user", "content": [                   # content 必须是数组，不能是序列化后的字符串
        {"type": "image_url", "image_url": {"url": to_data_url("a.png")}},
        {"type": "image_url", "image_url": {"url": to_data_url("b.png")}},
        {"type": "text", "text": "比较这两张图的差异。"},
    ]}],
)

# 2) 大视频：先上传拿 file id，再用 ms:// 引用
video = client.files.create(file=Path("video.mp4"), purpose="video")
completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[{"role": "user", "content": [
        {"type": "video_url", "video_url": {"url": f"ms://{video.id}"}},   # SDK 类型未声明 video_url，dict 透传
        {"type": "text", "text": "请描述这个视频。"},
    ]}],
)
```

**示例响应**：与 §1 相同结构；`usage.prompt_tokens` 含按分辨率/关键帧动态计算的图片/视频 token。

**注意事项**

- `content` 必须是 JSON **数组**；把数组 `json.dumps` 成字符串塞进 `content` 是非标准格式，不保证被当作视觉输入。**http(s) 图片 URL 不支持**（vision 页明确"URL 格式的图片：不支持"）；API 页说的"直接传入 URL 字符串"指 data URL / `ms://` 的字符串简写。
- 图片 MIME：jpeg / png / gif / webp / bmp / heic / heif；**SVG 被拒绝**（base64 或上传都不行），要理解 SVG 就把 XML 源码当文本发。GIF/WebP 动图可能按视频解码、按视频计 token。视频 MIME：mp4 / mpeg / mov / avi / x-flv / mpg / webm / wmv / 3gpp。
- 推荐图片 ≤ 4096×2160、视频 ≤ 1080p，更高只增耗时不增效果；token 可用 `/v1/tokenizers/estimate-token-count` 预估。
- 图片数量无限制，但**请求体 ≤ 100M**；大视频必须走文件上传；多次复用的图/视频也建议上传。
- 视觉可与多轮、流式、工具调用、JSON Mode、Partial Mode 组合。
- 上传 `purpose` 取值：材料里只出现 `"image"`（SVG 一节）与 `"video"`，完整枚举 ⚠ 文档未说明（在 files 文档）。

## 8. 自动断线重连

### 请求失败时重试；流式中断时接着写

**Endpoint**: `POST /v1/chat/completions`（无服务端重连 / 续传 API，全靠客户端）  
**用途**: 并发限制、网络抖动导致的偶发失败通常很短暂；官方方案 = 客户端循环重试。对流式请求，可把已收到的 `content` 作为 Partial Mode 前缀在新请求里续写，避免从头重新生成。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| （客户端）重试次数 / 间隔 | — | — | 官方示例 100 次 / 固定 1s | 官方示例未做指数退避 |
| `partial` + `reasoning_content` | — | — | — | 流式续写时复用 §5 写法 |

**示例请求**

```bash
# curl 自带重试（对 5xx / 连接错误）
curl --retry 5 --retry-delay 1 --retry-all-errors https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{"model":"kimi-k3","messages":[{"role":"user","content":"讲一个童话故事。"}]}'
```

```python
import os, time
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

# 官方示例 = 非流式 create() 包在 for i in range(100): try/except Exception: time.sleep(1) 里。
# 下面是流式 + Partial 续写（按 auto-reconnect 页的描述 + §5 规则组合，非官方逐字示例）：
def stream_with_resume(messages, max_attempts: int = 5) -> str:
    got, reasoning = "", ""
    for _ in range(max_attempts):
        req = list(messages)
        if got:   # 断线后把已收到的内容作为前缀续写
            req.append({"role": "assistant", "content": got, "partial": True,
                        **({"reasoning_content": reasoning} if reasoning else {})})   # 思考模型才带
        try:
            for chunk in client.chat.completions.create(model="kimi-k3", messages=req, stream=True):
                if not chunk.choices: continue
                d = chunk.choices[0].delta
                reasoning += getattr(d, "reasoning_content", None) or ""
                got += d.content or ""
            return got                     # 正常走到 [DONE]
        except Exception as e:
            print("stream interrupted:", e); time.sleep(1)
    return got
```

**示例响应**：与 §1 / §3 相同。

**注意事项**

- auto-reconnect 页摘要写"为流式请求实现断线重连，并结合 Partial Mode 从中断处继续生成"，但正文代码只有**非流式的 try/except 重试** —— ⚠ 文档未说明流式续写的官方实现；`stream_with_resume` 是按 §5 规则组合的推断写法。
- 官方示例 `except Exception` 全部重试（含 400/401）；生产上应只重试网络错误和 5xx/429。流式中断时最终 `usage` 拿不到，见 §3 的估算方式。`openai` SDK 自带 `max_retries` / `timeout`（构造 `OpenAI(...)` 时传），属 SDK 行为，文档未提。

## 9. 附录

### 请求顶层参数速查（来自 OpenAPI）

| 参数 | 适用模型 | 备注 |
|---|---|---|
| `model`, `messages` | 全部 | 必填 |
| `max_completion_tokens`（`max_tokens` 已弃用） | 全部 | K3 默认 131072 / 上限 1048576 |
| `stop`, `stream`, `stream_options.include_usage` | 全部 | |
| `response_format` (`text` / `json_object` / `json_schema`) | 全部 | |
| `tools`, `tool_choice` (`auto` / `none` / `required` / `{"type":"function","function":{"name"}}`) | 全部 | `tools[].function.name` 需匹配 `^[a-zA-Z_][a-zA-Z0-9-_]{0,127}$`；`parameters` 需符合 MFJS；`function.strict` 默认 true |
| `logprobs`, `top_logprobs`, `prediction`, `prompt_cache_key`, `safety_identifier` | 全部 | |
| `reasoning_effort` (`low` / `high` / `max`) | 仅 `kimi-k3` | |
| `thinking.type` (`enabled` / `disabled`), `thinking.keep` (`"all"` / null) | 仅 K2.x | k2.7-code 只接受 `enabled` + `"all"`，传其它值报错 |
| `temperature`, `top_p`, `n`, `frequency_penalty`, `presence_penalty`, `seed` | — | ⚠ 文档未说明：OpenAPI 未列出；`n` 仅支持 1 |

消息级字段：`role`、`content`、`name`、`partial`、`reasoning_content`（响应 / 回传）、`tool_calls`（assistant）、`tool_call_id`（tool）；K3 另有 `{"role":"system","tools":[...]}` 动态工具消息。

### 错误响应

```json
{"error": {"message": "...", "type": "invalid_request_error", "code": "..."}}
```

| HTTP | `error.type` | 典型原因 |
|---|---|---|
| 400 | `invalid_request_error` | 输入 + `max_completion_tokens` 超上下文；`json_schema.schema` 不是 object；`n` > 1；k2.7-code 传 `thinking.type=disabled` |
| 401 | `invalid_authentication_error` / `incorrect_api_key_error` | key 无效、缺 `Bearer ` 前缀、中国站/国际站 key 混用 |
| 404 | — | 已下线模型 |
| 500 | — | 服务端错误，可重试 |

其它错误码（429 限流等）⚠ 文档未说明（本材料未含错误码总表）。
