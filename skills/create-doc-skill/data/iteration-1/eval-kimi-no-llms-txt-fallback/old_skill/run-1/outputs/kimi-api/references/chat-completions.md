# Chat Completions（`POST /v1/chat/completions`）及相关指南

> 状态：文档草稿，基于 2026-09-03 抓取的 platform.moonshot.cn/docs 官方文档 + /docs/openapi.json 撰写，**尚未用真实 API 调用验证**。

本文覆盖：请求参数与各模型差异、思考模型 / `reasoning_content` / Preserved Thinking、`reasoning_effort`、多轮对话、流式输出、JSON Mode / Structured Output、Partial Mode、Context Caching、`max_completion_tokens`、logprobs / prediction / safety_identifier、请求签名 header。工具调用见 `tools.md`，图片/视频输入见 `vision-and-files.md`。

## 平台共性

- Base URL：`https://api.moonshot.cn/v1`；鉴权 `Authorization: Bearer $MOONSHOT_API_KEY`。
- OpenAPI 用 `model` 做 discriminator，把请求体拆成三套 schema：`kimi-k3`（`KimiK3ChatRequest`）、`kimi-k2.7-code` / `kimi-k2.7-code-highspeed`（`KimiK27CodeChatRequest`，同一模型、参数完全一致，高速版约 180 Tokens/s）、`kimi-k2.6`（`KimiK26ChatRequest`）。三套 schema 的公共字段一致，差异只在思考控制字段。
- Kimi K3 需在开放平台完成充值（最低 10 元）后才能调用，新用户 15 元代金券不可用于 K3；累计充值决定账户等级与限速。
- 错误响应统一为 `{"error": {"message", "type", "code"}}`；HTTP 400 / 401 / 500 同结构。

来源: docs/api/chat, docs/guide/kimi-k3-quickstart

### 创建聊天补全

**Endpoint**: `POST /v1/chat/completions`

**用途**: 向 Kimi 模型发送 `messages` 列表并获取一条回复；同一接口承载流式输出、思考模式、JSON/Structured Output、Partial Mode 与工具调用。API 无状态，多轮对话需自行回传历史。

**关键参数**（公共部分；模型专属字段见下一节）

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `model` | string | 是 | — | `kimi-k3` / `kimi-k2.7-code` / `kimi-k2.7-code-highspeed` / `kimi-k2.6` |
| `messages` | array | 是 | — | `role` ∈ system / user / assistant / tool；`content` 为 string 或多模态对象数组，schema 标注 `content` 必填且"不得为空"。可选 `name`、`partial`（仅最后一条 assistant） |
| `max_completion_tokens` | integer | 否 | 因模型而异；K3 为 131072 | 期望输出的 Token 上限（不含输入）。K3 最大 1048576。达到上限时 `finish_reason="length"`；输入 + 该值超出上下文窗口返回 `invalid_request_error` |
| `max_tokens` | integer | 否 | — | **已弃用**，schema 标 DEPRECATED，请改用 `max_completion_tokens`（指南页仍大量使用 `max_tokens`，见疑点） |
| `stream` | boolean | 否 | false | SSE 流式输出 |
| `stream_options.include_usage` | boolean | 否 | false | 在 `data: [DONE]` 前追加一个 `choices=[]`、带总 `usage` 的 chunk |
| `response_format` | object | 否 | `{"type":"text"}` | `text` / `json_object` / `json_schema`（后者需 `json_schema.name` + `json_schema.schema`，`strict` 默认 true） |
| `stop` | string \| string[] | 否 | null | 停用词，完全匹配即停，命中的词不输出；**最多 5 个**，每个 ≤ 32 字节 |
| `logprobs` / `top_logprobs` | boolean / integer | 否 | false / — | 返回输出 Token 对数概率；`top_logprobs` 取值 0–20 且必须同时 `logprobs=true` |
| `prediction` | object | 否 | — | Predicted Output：`{"type":"content","content": string \| [{"type":"text",...}]}` |
| `prompt_cache_key` | string | 否 | null | 提升缓存命中率的会话/任务 id；Kimi Code Plan 下"为必填" |
| `safety_identifier` | string | 否 | — | 稳定的终端用户标识（建议对用户名/邮箱做哈希） |
| `tools` / `tool_choice` | — | 否 | — | 见 `tools.md` |

**示例请求**

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kimi-k3",
    "messages": [
      {"role": "system", "content": "你是 Kimi。"},
      {"role": "user", "content": "用一句话介绍 Kimi K3。"}
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
        {"role": "system", "content": "你是 Kimi。"},
        {"role": "user", "content": "用一句话介绍 Kimi K3。"},
    ],
    reasoning_effort="low",          # K3 专属；K2.x 用 extra_body={"thinking": {...}}
    max_completion_tokens=4096,
)
message = completion.choices[0].message
if hasattr(message, "reasoning_content"):   # SDK 类型未声明该字段
    print("[思考]", getattr(message, "reasoning_content"))
print(message.content)
```

**示例响应**（非流式，关键字段）

```json
{
  "id": "cmpl-...", "object": "chat.completion", "created": 1698999496, "model": "kimi-k3",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "...", "reasoning_content": "..."},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 19, "completion_tokens": 21, "total_tokens": 40, "cached_tokens": 10}
}
```

`finish_reason` ∈ `stop` / `length` / `tool_calls`；`reasoning_content` 仅思考模式开启时返回；`usage.cached_tokens` 为命中缓存的 Token 数（顶层 `usage` 内，不是 OpenAI 的 `prompt_tokens_details.cached_tokens`）。

**注意事项**

- 采样参数不可调：OpenAPI schema 里**根本没有** `temperature` / `top_p` / `n` / `presence_penalty` / `frequency_penalty` 字段。K3 快速开始"重要限制"原话：`temperature=1.0`、`top_p=0.95`、`n=1`、`presence_penalty=0`、`frequency_penalty=0` 为固定值，**建议不要显式传入**（未说传入会报错）。K2.7-code / K2.6 快速开始"参数变动说明"则明确：这些字段"若指定其他值，将会报错"，且 K2.6 非思考模式 temperature 固定 0.6（思考模式 1.0）。流式输出页另注明：三个模型 `n>1` 均返回 400 `invalid n: only 1 is allowed for this model`。
- `stop` 上限 5 个（OpenAI 为 4 个），每个 ≤ 32 字节。
- 多轮对话 / 工具调用时把 API 返回的**完整 assistant message 原样回传**，不要只留 `content`（K3 与 K2.7-code 强制要求）。
- `reasoning_content` 的 Token 同样受输出上限约束并计费：`reasoning_content` + `content` 的 Token 数 ≤ `max_tokens`。

来源: docs/api/chat, docs/guide/kimi-k3-quickstart, docs/guide/kimi-k2-7-code-quickstart, docs/guide/kimi-k2-6-quickstart, docs/guide/utilize-the-streaming-output-feature-of-kimi-api

## 各模型参数差异（思考控制与默认值）

| 字段 | `kimi-k3` | `kimi-k2.7-code`（含 highspeed） | `kimi-k2.6` |
| --- | --- | --- | --- |
| `reasoning_effort`（顶层） | `low` / `high` / `max`，默认 `max` | 不支持 | 不支持 |
| `thinking.type` | 不支持（"无需也不应传入"） | 仅 `enabled`，传 `disabled` 报错 | `enabled`（默认）/ `disabled` |
| `thinking.keep` | — | 不传 / `null` / `"all"` 均按 `"all"` 处理，其他值报错 | `null`（默认，不保留历史思考）/ `"all"` |
| `thinking` 默认值 | — | `{"type":"enabled","keep":"all"}` | `{"type":"enabled"}` |
| 思考能否关闭 | 不能（"目前关不了"，可用 `reasoning_effort=low` 缩短） | 不能 | 能 |
| Preserved Thinking | 始终开启 | 始终开启 | 需显式 `keep: "all"` |
| 上下文 / 输出上限 | 1M；`max_completion_tokens` 默认 131072，最大 1048576 | 256K；快速开始称 `max_tokens` 默认 32768 | 256K；快速开始称 `max_tokens` 默认 32768 |
| 固定 temperature | 1.0（建议不传） | 1.0（传其他值报错） | 思考 1.0 / 非思考 0.6（传其他值报错） |

`thinking` 对象 `additionalProperties: false`，`type` 必填。从 K2.x 迁移到 K3：删掉 `thinking`，按需加顶层 `reasoning_effort`。

来源: docs/api/chat, docs/guide/use-thinking-models, docs/guide/use-reasoning-effort, docs/guide/kimi-k3-quickstart, docs/guide/kimi-k2-7-code-quickstart, docs/guide/kimi-k2-6-quickstart

## 思考模型、reasoning_content 与 Preserved Thinking

要点：

- 思考模型先输出推理过程（`reasoning_content`），再输出最终答案（`content`）；两者同级，都在 `choices[0].message` 内。
- openai SDK 的 `ChatCompletionMessage` / `ChoiceDelta` 类型**未声明** `reasoning_content`，官方建议用 `hasattr(obj, "reasoning_content")` 判断、`getattr` 读取；直接走 HTTP 则和 `content` 同级读取即可。
- 流式输出中 `reasoning_content` 一定先于 `content` / `tool_calls` 出现，可用"是否出现 content"判断思考结束。
- Preserved Thinking = 把**历史轮次** assistant 消息的 `reasoning_content` 一并回传。`thinking.keep` 只影响历史轮次是否被服务端采用，不改变当前轮是否思考（由 `thinking.type` 控制）。K2.6 默认 `keep: null` 时服务端会忽略历史 `reasoning_content`（上下文更短、更省钱）；`"all"` 则保留并计费。
- 单轮任务内的多步工具调用循环，无论模型都应保留全部 `reasoning_content` 回传；不回传不报错但会影响连贯性。思考模型做工具循环时官方建议 `max_tokens >= 16000` 并开启流式。
- 回传格式：assistant 消息里直接带 `"reasoning_content": "<上一轮返回值>"`，与 `content` 并列。

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

messages = [
    {"role": "system", "content": "你是 Kimi。"},
    {"role": "user", "content": "第一个问题..."},
    {"role": "assistant",
     "reasoning_content": "<上一轮 API 返回的 reasoning_content>",
     "content": "<上一轮 API 返回的最终回答>"},
    {"role": "user", "content": "请基于之前的分析继续推导下一步。"},
]
response = client.chat.completions.create(
    model="kimi-k2.6",
    messages=messages,
    extra_body={"thinking": {"type": "enabled", "keep": "all"}},  # thinking 不是 SDK 原生参数
)
# 关闭 K2.6 思考：extra_body={"thinking": {"type": "disabled"}}
# K2.7-code：不要传 thinking；K3：不要传 thinking，用 reasoning_effort
```

来源: docs/guide/use-thinking-models, docs/api/chat, docs/guide/kimi-k2-6-quickstart

## reasoning_effort（仅 K3）

- 请求顶层字符串字段，取值 `"low"` / `"high"` / `"max"`，默认 `"max"`；**没有 `"medium"`**（与 OpenAI 的 minimal/low/medium/high 不同）。
- K3 始终思考且 Preserved Thinking 始终开启，`reasoning_effort` 只调强度，不能关闭思考；觉得思考太长就设 `low`。
- Python SDK 可直接传 `reasoning_effort="max"`（官方示例如此）。多轮 / 工具调用必须回传完整 assistant message（含 `reasoning_content` 和 `tool_calls`）。

```python
completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[{"role": "user", "content": "请推导数列 1, 4, 9, 25, 64, ... 的通项公式"}],
    reasoning_effort="high",
)
```

来源: docs/guide/use-reasoning-effort, docs/guide/kimi-k3-quickstart

## 多轮对话管理

- API 无状态：每次请求都要把 system + 历史 user/assistant（以及 tool 消息）按时间顺序整体发送。
- 官方示例直接把返回的 `completion.choices[0].message` 对象 append 回 `messages`（K2.7-code 示例用 `message.model_dump()`），以保证 `reasoning_content` / `tool_calls` 不丢。
- 控制长度：官方示例策略是"system 消息单独保存、每次只带最近 N（默认 20）条历史"；截断时务必把 system 消息放回最前面。生产环境还需考虑多用户隔离、持久化、并发锁、对丢弃消息做摘要等。
- 与缓存配合：把固定的大段上下文放在 `messages` 最前面，后续追加用户问题与回复，前缀不变即可自动命中缓存（见下文）。

```python
messages = [{"role": "system", "content": "你是 Kimi。"}]

def chat(user_input: str) -> str:
    messages.append({"role": "user", "content": user_input})
    completion = client.chat.completions.create(model="kimi-k3", messages=messages)
    assistant_message = completion.choices[0].message
    messages.append(assistant_message)      # 整个对象回传，保留 reasoning_content
    return assistant_message.content
```

来源: docs/guide/engage-in-multi-turn-conversations-using-kimi-api, docs/api/chat

## 流式输出（SSE）

- `stream: true` 后响应 `Content-Type: text/event-stream`；每个事件为 `data: <JSON>\n\n`，结尾 `data: [DONE]`。**只能以 `[DONE]` 判断结束**，收到 `finish_reason=stop` 但没等到 `[DONE]` 仍视为不完整。
- chunk 结构同 completion，但 `message` 换成 `delta`；`delta.role` 仅首个 chunk 出现；`delta` 中可能出现 `content`、`reasoning_content`（先于 content）、`tool_calls`（片段按 `index` 拼接，`arguments` 必须追加不能覆盖）。
- `stream_options: {"include_usage": true}`：在 `[DONE]` 前多发一个 `choices: []`、顶层 `usage` 为总用量的 chunk；schema 称其他 chunk 的 `usage` 为 `null`。不要假设每个 chunk 都有 `choices[0]`。流被打断时可能拿不到该 chunk，官方建议保存已收内容后用 `/v1/tokenizers/estimate-token-count` 补算。
- 提前终止：直接 `break` / 关闭连接即可。

```python
stream = client.chat.completions.create(
    model="kimi-k3",
    messages=[{"role": "user", "content": "解释为什么天空是蓝色的。"}],
    stream=True,
    stream_options={"include_usage": True},
)
usage = None
for chunk in stream:
    if chunk.usage:                     # 最后的统计 chunk，choices 为空
        usage = chunk.usage
    if not chunk.choices:
        continue
    delta = chunk.choices[0].delta
    reasoning = getattr(delta, "reasoning_content", None)
    if reasoning:
        print(reasoning, end="", flush=True)
    if delta.content:
        print(delta.content, end="", flush=True)
print("\ntotal_tokens:", usage.total_tokens if usage else "unknown")
```

不用 SDK 时：`httpx.stream("POST", ...)` 逐行读，跳过非 `data: ` 行，payload 为 `[DONE]` 时退出，其余 `json.loads`。

来源: docs/guide/utilize-the-streaming-output-feature-of-kimi-api, docs/api/chat

## JSON Mode 与 Structured Output（`response_format`）

| 模式 | `type` | 保证 | 适用 |
| --- | --- | --- | --- |
| 文本 | `text`（默认） | 无约束 | 普通对话 |
| JSON Mode | `json_object` | 合法 JSON **Object**（不保证字段） | 简单/字段灵活场景 |
| Structured Output | `json_schema` | 按 schema 约束（token 级约束解码） | 生产、下游强类型对接 |

- `json_object`：**必须**在 system/user prompt 里写清字段名、类型，最好给示例；只会生成 JSON Object，不要引导输出数组；解析 `message.content`（不要解析整个响应，思考模型还有 `reasoning_content`）。
- `json_schema`：`json_schema.name`、`json_schema.schema` 必填；`strict` 默认 true，官方建议显式写 `true`。`strict=true` 时 schema 需符合 **MFJS（Moonshot Flavored JSON Schema）**，可用 `walle` CLI 静态自检：`go install github.com/moonshotai/walle/cmd/walle@latest && walle -schema '<schema>' -level strict`。`strict=false` 时只保证合法 JSON Object。
- 模型差异（官方原话）：K3 稳定支持（嵌套、数组、`anyOf`）；K2.7-code 最稳（含 `oneOf` / `$ref` / `additionalProperties: true`）；K2.6 复杂 schema 偶有不稳定（`$ref` 可能返回 Markdown 代码块、`oneOf` 被忽略、`partial=true` 时输出 schema 外字段），建议简单 schema + 业务层二次校验。
- 缺失信息用可空联合类型 `"type": ["integer", "null"]` 表达，避免模型编造；`required` 字段必现；`additionalProperties: false` 禁止额外字段。
- 截断：`finish_reason="length"` 说明 JSON 没写完，增大输出上限 / 简化 schema。schema 本身非法（如 `schema` 不是 object）返回 400 `invalid_request_error`。
- 设置 `response_format` **不会破坏前缀缓存**。
- 不要把 `json_object` 与 Partial Mode 混用（api/chat 明确警告）；`json_schema` + `partial` 在 K2.7-code 简单 schema 下通常可用，K2.6 不建议。

```python
import json
completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[{"role": "user", "content": "小林今年 28 岁。提取姓名和年龄。"}],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "person",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "age": {"type": ["integer", "null"]}},
                "required": ["name", "age"],
                "additionalProperties": False,
            },
        },
    },
)
person = json.loads(completion.choices[0].message.content or "{}")
```

来源: docs/guide/use-json-mode-feature-of-kimi-api, docs/guide/response_format, docs/api/chat, docs/guide/kimi-k3-quickstart

## Partial Mode（前缀续写）

- 在 `messages` 末尾追加 `{"role": "assistant", "content": "<前缀>", "partial": true}`，模型强制以该前缀开头继续生成；**返回的 `content` 不含前缀**，需自行拼接。
- 用途：固定开头（如 JSON 的 `{`、代码块 "```python\n"）、角色扮演固定口吻（配合 `name` 字段，`name` 也算前缀的一部分，`content` 可为空串）、`finish_reason="length"` 后续写。
- 续写截断输出时，思考模型要把上一轮的 `reasoning_content` 一并放进这条 partial assistant 消息。注意输出上限会先被思考消耗：K3 若 `max_tokens` 太小，截断可能落在思考阶段——`content` 为空、`finish_reason=length`，续写会因前缀为空而从头生成，需把上限设够大。
- 长对话中可在中途再插一条 system 消息强化角色设定，再接 partial assistant 消息。

```python
prefix = "结论："
completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[
        {"role": "user", "content": "用一句话说明保持接口兼容的重要性。"},
        {"role": "assistant", "content": prefix, "partial": True},
    ],
)
print(prefix + (completion.choices[0].message.content or ""))
```

来源: docs/guide/use-partial-mode-feature-of-kimi-api, docs/api/chat, docs/guide/kimi-k3-quickstart

## Context Caching（自动前缀缓存）

- 对所有模型请求自动启用：无需创建缓存、无需 cache id、无需管理 TTL，也没有额外参数；系统检测到重复的初始上下文（system prompt、知识文档、工具定义）即自动复用。命中量体现在 `usage.cached_tokens`。
- 命中条件（原话）："当前一个请求的 prompt tokens 大于 256 时，新的请求才能命中前缀缓存；当前一个请求的 prompt tokens 小于 256 时，请求不会被缓存而是被丢弃。"
- 实践：把固定的大段上下文放在 `messages` 最前面（指南原文写"system 消息之前"），保持 system prompt、知识内容、工具定义稳定；后续只在尾部追加。
- `prompt_cache_key`（schema 字段）：用会话 id / task id 之类稳定字符串提升命中率，退出并恢复会话时保持不变；对 Kimi Code Plan 为必填；缓存指南页本身未提及此字段。
- 首 Token 延迟长文本场景平均可降至 5s 内；计费按"缓存命中 / 未命中"分别计价，见定价页。

```python
from pathlib import Path
knowledge = Path("knowledge-base.md").read_text(encoding="utf-8")
for question in ["总结关键结论。", "列出三个实施风险。"]:
    completion = client.chat.completions.create(
        model="kimi-k3",
        messages=[{"role": "system", "content": knowledge}, {"role": "user", "content": question}],
        extra_body={"prompt_cache_key": "session-42"},
    )
    print(completion.usage.cached_tokens, completion.choices[0].message.content)
```

来源: docs/guide/use-context-caching-feature-of-kimi-api, docs/guide/kimi-k3-quickstart, docs/api/chat

## 其他参数速查

- **`max_completion_tokens` vs `max_tokens`**：schema 只推荐前者；后者标 DEPRECATED。含义是"期望输出长度"而非输入+输出；输入 + 该值 > 上下文窗口即 400 `invalid_request_error`。K3 默认 131072、最大 1048576。指南页示例仍写 `max_tokens=1024*32` / `86400` / `65536`。
- **`logprobs` / `top_logprobs`**：schema 描述在 `message.logprobs` 返回；`top_logprobs` 0–20 且需 `logprobs=true`。响应 schema 中未列出 `logprobs` 结构。
- **`prediction`**：`{"type": "content", "content": "<预知的大段文本>"}`，用于"重新生成仅少量修改的文件"降低延迟；`content` 数组形式只支持 `type: text` 元素。文档未说明对 usage 的影响。
- **`safety_identifier`**：稳定的终端用户标识，用于识别违反使用政策的用户；建议哈希后传。
- **`X-Msh-Request-Nonce`**（请求 header，可选）：客户端生成随机 nonce（推荐 UUID v4）即开启请求签名，响应头返回 `Msh-Request-Timestamp`（Unix 毫秒）与 `Msh-Request-Signature`（`reqsigv1_` 前缀，基于 nonce、timestamp、`model` 签发）；nonce 不合法时请求照常执行但不返回签名头。校验用 `POST /v1/signatures/verify`，见 `utilities.md`。

来源: docs/api/chat

## 待验证疑点

1. **采样参数传入是否报错（K3）**：schema 无 `temperature`/`top_p`/`n`/`presence_penalty`/`frequency_penalty`；K3 快速开始只说"为固定值，建议不要显式传入"，K2.x 快速开始说"若指定其他值，将会报错"。需验证 K3 传 `temperature=0.3` 是报错还是被忽略，以及传等于固定值（1.0）是否被接受。来源: guide/kimi-k3-quickstart "重要限制"、guide/kimi-k2-7-code-quickstart "参数变动说明"。
2. **`n>1` 错误码**：流式输出页称三模型均 400 `invalid n: only 1 is allowed for this model`，与 K3 快速开始"建议不要显式传入"的措辞不一致，需实测 K3。
3. **`max_tokens` 是否仍被接受**：schema 标 DEPRECATED，但思考模型、Partial Mode、JSON Mode、K2.x 快速开始的示例全部仍用 `max_tokens`；需验证两者同时传的优先级、以及只传 `max_tokens` 是否有 warning。
4. **K2.x 输出上限默认值**：K2.7-code / K2.6 快速开始称 `max_tokens` 默认 32768；schema 只给 K3 默认 131072、其余"因模型而异"。需实测 K2.x 不传时的实际截断点。
5. **K3 `max_completion_tokens=1048576`**：schema 说最大 1048576 且"输入 + 该值超出上下文窗口返回 invalid_request_error"，1M 上下文下任何非空输入都会超出——需验证是否真报错还是服务端自动裁剪。
6. **流式 `usage` 位置不一致**：schema 同时在 `choices[].usage`（ChoiceDelta.usage）和顶层 `usage` 定义；流式指南 SSE 样例把 usage 放在带 `finish_reason` 的 chunk 的 `choices[0].usage` 里、再发一个 `choices=[]` 顶层 usage chunk；api/chat 样例则在 `finish_reason` chunk 顶层直接带 `usage`（含 `cached_tokens`）。需实测：不传 `include_usage` 时是否也有 usage、`cached_tokens` 在流式里出现在哪一层。
7. **流式 `delta.reasoning_content` 不在 schema 里**：`ChoiceDelta.delta` 只列 role/content/tool_calls；指南多处依赖 `delta.reasoning_content`。响应 schema 的 `message` 也没有 `logprobs` 字段。
8. **请求 `Message` schema 缺 assistant/tool 专属字段**：`Message` 只有 role/content/name/partial，没有 `reasoning_content`、`tool_calls`、`tool_call_id`，且 `content` 标为必填"不得为空"；但指南要求原样回传含 `reasoning_content` 的 assistant 消息，Partial Mode 示例 `content: ""`。需验证 assistant 消息 `content` 为空串 / null 时是否 400。
9. **SDK 对象回传能否保留 `reasoning_content`**：多轮指南直接 `messages.append(completion.choices[0].message)`（pydantic 对象），K2.7 示例用 `model_dump()`；openai SDK 序列化额外字段的行为文档未说明，需实测回传后服务端是否真的收到 `reasoning_content`。
10. **`reasoning_content` 的读取方式自相矛盾**：思考模型页说 SDK 类型不含该字段、只能 `hasattr/getattr`；Partial Mode 页示例却直接写 `completion.choices[0].message.reasoning_content`。需确认当前 openai SDK 版本下属性访问是否可用。
11. **K3 传 `thinking` / K2.x 传 `reasoning_effort` 的行为**：文档只说"不支持"/"无需也不应传入"，未说明是报错还是忽略。来源: guide/use-thinking-models 对照表。
12. **`reasoning_effort` 非法值**（如 `"medium"`）是否 400；SDK 类型提示不含 `"max"`（OpenAI 枚举），运行时能否直通需实测。
13. **K2.6 `thinking.keep: null` 时历史 `reasoning_content` 是否计费**：schema 说服务端"忽略"历史思考，未说明是否仍计入 `prompt_tokens`。
14. **`usage` 中思考 Token 归属**：思考页说 `reasoning_content` 计入输入/输出消耗，但响应 schema 没有 `completion_tokens_details.reasoning_tokens`；需确认是否合并在 `completion_tokens` 里。
15. **`cached_tokens` 字段位置**：Kimi 放在顶层 `usage.cached_tokens`，OpenAI 放在 `usage.prompt_tokens_details.cached_tokens`；依赖 OpenAI 字段路径的代码会读到 None。
16. **缓存 256 token 门槛原文歧义**："当前一个请求的 prompt tokens 大于 256"可读作"当**前一个**请求"或"当前**一个**请求"；恰好 256 时行为、以及"被丢弃"的确切含义需实测。来源: guide/use-context-caching-feature-of-kimi-api。
17. **缓存指南"放在 system 消息之前"**：多轮建议把固定上下文放在"messages 最前面（system 消息之前）"，与常规"system 在首位"冲突，需确认是笔误还是真的建议 user/system 顺序倒置。
18. **`prompt_cache_key` 的实际作用与 Kimi Code Plan 必填**：仅 schema 提及，缓存指南声称"无需额外参数"；需验证传与不传对 `cached_tokens` 的影响、以及非 Code Plan 账号传入是否有效。
19. **`strict=true` 不符合 MFJS 时的反馈**：schema 说"返回错误或 warning"，response_format 指南说 API 常返回 200 且"不会出现 warning 字段"。需实测非法 schema（如带 `$ref`）在三模型上的返回。
20. **`json_schema.strict` 默认值**：schema 默认 true；指南说"省略时 K2.6 更容易输出 schema 外字段"，暗示省略 ≠ true。需实测省略与显式 true 是否等价。
21. **Partial Mode 与 `json_object` 混用**：api/chat 警告"请勿混用"，但未说是报错还是仅结果不可控；K3 上 `json_schema` + `partial` 的兼容性文档未覆盖（只写了 K2.7-code / K2.6）。
22. **Partial Mode 返回是否含前缀**：指南说需手动拼接（即不含），但 `name` 作为"前缀的一部分"时 `content` 输出是否会重复角色名，需实测。
23. **`stop` 上限**：Kimi 5 个、每个 ≤32 字节（OpenAI 4 个、无字节限制）；超限返回什么错误未说明。
24. **`logprobs` 与思考模型**：是否对 `reasoning_content` 也返回 logprobs、返回结构（OpenAI 是 `choices[].logprobs.content[]`）文档未给出。
25. **`prediction` 的计费与拒绝 Token**：OpenAI 有 `accepted/rejected_prediction_tokens`，Kimi schema 无对应 usage 字段；预测内容是否收费需实测。
26. **`safety_identifier` 无任何行为说明**：触发何种响应（错误码/限流）未文档化。
27. **`X-Msh-Request-Nonce` 在流式响应下**：签名头是否随 SSE 响应头返回、以及 `Msh-Request-Signature` 是否覆盖 `stream=true` 请求，文档未说明。
28. **响应 `model` 字段**：api/chat 说会回显请求中的 model；对 `kimi-k2.7-code-highspeed` 回显的是 highspeed 还是基础名需实测。
29. **K3 访问门槛**：未充值账号调用 K3 的具体错误码/`type` 未文档化（只说"充值后解锁"）。
