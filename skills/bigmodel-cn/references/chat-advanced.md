# 对话补全（Chat Completions）

对话补全是智谱开放平台的核心能力域，覆盖文本对话、多模态（图片/视频/文件）理解、工具调用（Function Calling / 联网搜索 / 知识库检索 / MCP）、流式输出、深度思考（Reasoning）、结构化输出与上下文缓存。所有请求均以 `https://open.bigmodel.cn/api/` 为 Base URL，鉴权方式为 HTTP Bearer Token：

```
Authorization: Bearer <API_KEY>
```

API Key 在 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取。模型代码、各模型上下文窗口/`max_tokens` 上限等详见 `models.md`。

---

> 本文是 [`chat.md`](chat.md) 的进阶部分：异步对话、函数调用、结构化输出、深度思考、上下文缓存。
> 只在需要完整参数表或示例代码时打开，并且**只读你需要的那一节**（用 Read 的 offset/limit）。

## 二、对话补全（异步）

某些场景（批处理、长任务、不需要实时交互）适合用异步接口：提交请求后立即拿到 `task_id`，由客户端轮询结果接口获取最终响应，避免长时间占用一个 HTTP 连接。

### 提交异步任务

**Endpoint**: `POST /paas/v4/async/chat/completions`

**用途**: 请求体与同步接口的"普通对话模型请求"基本一致（`model`/`messages`/`thinking`/`reasoning_effort`/`do_sample`/`temperature`/`top_p`/`max_tokens`/`tools`/`tool_choice`/`stop`/`response_format`/`request_id`/`user_id`），但**不支持 `stream`**——异步接口本身就是"提交后轮询"的模式，无 SSE 流。

**关键参数**：同第一节"关键参数"表，去掉 `stream` 与 `tool_stream`。

**示例请求**：

```bash
curl --location 'https://open.bigmodel.cn/api/paas/v4/async/chat/completions' \
--header 'Authorization: Bearer YOUR_API_KEY' \
--header 'Content-Type: application/json' \
--data '{
    "model": "glm-5.3",
    "messages": [{"role": "user", "content": "写一篇 2000 字的行业分析报告"}]
}'
```

```python
import requests

resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/async/chat/completions",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "写一篇 2000 字的行业分析报告"}],
    },
)
task = resp.json()
task_id = task["id"]
print("task_id:", task_id, "status:", task["task_status"])
```

**示例响应**：

```json
{
  "model": "glm-5.3",
  "id": "任务ID，查询时使用",
  "request_id": "...",
  "task_status": "PROCESSING"
}
```

`task_status` 取值：`PROCESSING`（处理中）、`SUCCESS`（成功）、`FAIL`（失败）。提交接口只返回状态壳，真正的 `choices`/`usage` 内容必须通过下方查询接口获取。

### 查询异步结果

> **⚠️ 已用真实 API 验证（2026-09-07）：异步端点会静默替换模型，同步端点不会。** 同一个 `model` 值，两个端点的行为不一致——
> 实测对照（看响应体回显的 `model` 字段，以及轮询结果里的 `model`）：
>
> | 请求的 model | `POST /chat/completions` 回显 | `POST /async/chat/completions` 回显 | 异步结果回显 |
> | :--- | :--- | :--- | :--- |
> | `glm-4.6` | `glm-4.6` | **`glm-4.7`** | `GLM-4.7` |
> | `glm-4.7` | `glm-4.7` | **`glm-4.7-ali`** | `glm-4.7-ali` |
> | `glm-4.5-air` | `glm-4.5-air` | `glm-4.5-air` | `GLM-4.5-Air` |
> | `glm-5.3` | `glm-5.3` | `glm-5.3` | `GLM-5.3` |
>
> 注意 `glm-4.7-ali` 这个名字**在官方文档里完全不存在**，只能从响应里看到。含义：**异步任务不能假设"我传什么就跑什么"**——
> 需要结果可复现、或有审计/计费对账要求时，必须读回响应里的 `model` 字段做核对，不要相信请求体。
> 受影响的是较旧的型号（`glm-4.6`/`glm-4.7`）；`glm-4.5-air`、`glm-5.3` 实测原样透传。这份对照随平台更新会变，重要场景请自行复测。

**Endpoint**: `GET /paas/v4/async-result/{id}`

**用途**: 用提交异步任务返回的 `id` 轮询获取最终结果（对话补全与视频生成共用此接口）。

**关键参数**：

| 参数名 | 类型 | 必填 | 说明 |
| :-- | :-- | :-- | :-- |
| `id` | string（path） | 是 | 提交任务时返回的任务 ID |

**示例请求 / 轮询写法**：

```bash
curl --location 'https://open.bigmodel.cn/api/paas/v4/async-result/{task_id}' \
--header 'Authorization: Bearer YOUR_API_KEY'
```

```python
import time
import requests

def poll_async_result(task_id: str, api_key: str, interval=2, timeout=120):
    url = f"https://open.bigmodel.cn/api/paas/v4/async-result/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    waited = 0
    while waited < timeout:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        result = r.json()
        status = result.get("task_status")
        if status == "SUCCESS":
            return result
        if status == "FAIL":
            raise RuntimeError(f"async task failed: {result}")
        time.sleep(interval)
        waited += interval
    raise TimeoutError("polling timed out")

result = poll_async_result(task_id, "YOUR_API_KEY")
print(result["choices"][0]["message"]["content"])
```

**示例响应（成功，关键字段）**：

```json
{
  "id": "...",
  "request_id": "...",
  "created": 1735000000,
  "model": "glm-5.3",
  "choices": [
    {"index": 0, "message": {"role": "assistant", "content": "……"}, "finish_reason": "stop"}
  ],
  "usage": {"prompt_tokens": 20, "completion_tokens": 800, "total_tokens": 820}
}
```

处理中时响应仅包含 `model`/`task_status`/`request_id` 等壳字段，没有 `choices`。

**注意事项**：

- 异步接口不支持 `stream`；如果需要"边生成边看"的体验，请用同步接口 + `stream=true`。
- 轮询建议加指数退避或固定间隔（如 2-5 秒），并设置总超时，避免死循环。
- 该查询接口同时服务对话补全和视频生成任务，响应体是 `oneOf` 结构（对话补全结果 / 视频结果 / 图片结果三选一），用 `task_status` 与是否存在 `choices`/`video_result`/`image_result` 字段区分任务类型。

---

## 四、工具调用（Function Calling）

### 支持的工具类型

`tools` 数组中每一项都是 `{"type": "...", "<type>": {...}}` 的形式，`type` 支持四种：

| type | 内层字段 | 说明 |
| :-- | :-- | :-- |
| `function` | `function.name`、`function.description`、`function.parameters`（JSON Schema 对象） | 自定义函数调用，`name` 需匹配 `^[a-zA-Z0-9_-]+$`，长度 ≤64；`description`、`parameters` 均必填 |
| `retrieval` | `retrieval.knowledge_id`（必填）、`retrieval.prompt_template` | 知识库检索，`knowledge_id` 从平台知识库功能创建获取；`prompt_template` 可自定义，需包含 `{{ knowledge }}` 与 `{{ question }}` 占位符 |
| `web_search` | `web_search.enable`、`search_engine`（`search_std`/`search_pro`/`search_pro_sogou`/`search_pro_quark`）、`search_query`、`search_intent`、`count`（1-50）、`search_domain_filter`、`search_recency_filter`、`content_size`、`result_sequence`、`search_result`、`require_search`、`search_prompt` | 联网搜索工具。**必须显式传 `web_search.search_result: true`**，响应体顶层才会带 `web_search` 引用来源数组（`icon`/`title`/`link`/`media`/`publish_date`/`content`/`refer`；注意 `link` 是否为空取决于 `search_engine`，见 `references/tools.md`）——已用真实 API 验证：不传这个字段（默认 `false`）时搜索依然会正常执行、结果依然会被用于生成回答，但响应体里完全没有 `web_search` 这个顶层字段，代码里如果读 `response.get("web_search")` 期望拿到引用列表，默认情况下永远是 `None`，不会报错，只是"想展示信息来源"这个需求会静默失效 |
| `mcp` | `mcp.server_label`（必填）、`mcp.server_url`、`mcp.transport_type`（`sse`/`streamable-http`，默认 `streamable-http`）、`mcp.allowed_tools`、`mcp.headers` | 调用外部 MCP Server 上的工具；若连接智谱官方 MCP Server，`server_label` 填 MCP Code 即可，无需 `server_url` |

`tools` 最多 128 个函数；`tool_choice` 目前默认且仅支持字符串 `"auto"`（不支持强制指定某个函数）。视觉模型的 `tools` 只支持 `function` 类型，且仅 GLM-5.3-Flash / GLM-4.6V / AutoGLM-Phone 支持。

> **已用真实 API 调用验证（2026-09）**：OpenAPI 规范把 `web_search.search_engine` 标记为必填字段，但实测对 `chat/completions` 里的 `web_search` 工具类型省略该字段**并不会报错**——平台会静默套用一个默认搜索引擎，联网检索依然生效。这与下方 `references/tools.md` 里**独立的** `POST /paas/v4/web_search` 端点不同：那个端点已实测确认省略 `search_engine` 会直接返回 `{"error":{"code":"1214","message":"search_engine:The search_engine cannot both be empty."}}`。也就是说同一个字段名，在两个不同入口的必填程度并不一致（规范文档本身也存在类似的不一致）。**实践建议**：无论走哪个入口，都显式传 `search_engine`，不要依赖未文档化的默认值。**但不要随手填 `search_pro`**——实测 `search_pro` 与 `search_std` 返回的来源 `link` 恒为空字符串，只有 `search_pro_bing` / `search_pro_jina` / `search_pro_quark` / `search_pro_sogou` 才带真实链接；需要展示可点击来源时必须选后面这几个，详见 `references/tools.md` 里的对照表。

响应中的 `tool_calls[].type` 目前只会是 `function` 或 `mcp`（`web_search`/`retrieval` 是平台侧直接执行并把结果注入 `web_search` 字段或正文，不会作为 `tool_calls` 让你二次执行）。

### 完整的 Function Calling 多轮循环

工具调用是"模型只给参数、应用自己执行"的模式：模型返回 `tool_calls` → 你的代码解析并调用真实函数 → 把结果用 `role:"tool"` 消息（携带对应的 `tool_call_id`）加回 `messages` → 再次请求模型拿到最终回答。以下是标准库 `requests` 版的完整示例：

```python
import json
import requests

API_KEY = "YOUR_API_KEY"
URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

def get_weather(city: str) -> dict:
    """真实业务里这里应调用天气 API"""
    return {"city": city, "temperature": "22°C", "condition": "晴天"}

TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "获取指定城市的当前天气信息",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市名称，如：北京"}},
            "required": ["city"],
        },
    },
}]

def chat(messages):
    resp = requests.post(URL, headers=HEADERS, json={
        "model": "glm-5.3",
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
    })
    resp.raise_for_status()
    return resp.json()

messages = [{"role": "user", "content": "北京今天天气怎么样？"}]

# 第一轮：模型可能返回 tool_calls
result = chat(messages)
message = result["choices"][0]["message"]
messages.append(message)  # 把 assistant 消息（含 tool_calls）原样加回历史

if message.get("tool_calls"):
    for tool_call in message["tool_calls"]:
        if tool_call["type"] == "function" and tool_call["function"]["name"] == "get_weather":
            args = json.loads(tool_call["function"]["arguments"])
            weather_result = get_weather(args["city"])
            messages.append({
                "role": "tool",
                "content": json.dumps(weather_result, ensure_ascii=False),
                "tool_call_id": tool_call["id"],
            })

    # 第二轮：把工具结果传回去，拿最终自然语言回答
    final_result = chat(messages)
    print(final_result["choices"][0]["message"]["content"])
else:
    print(message["content"])
```

**注意事项**：

- 必须把模型返回的 `assistant` 消息（原样，含 `tool_calls`）加入 `messages` 历史，再紧跟对应的 `tool` 消息，顺序不能乱，否则模型无法对齐 `tool_call_id`。
- 一次响应可能包含多个 `tool_calls`（并行调用多个函数），需要逐个执行并各自追加一条 `role:"tool"` 消息。
- `function.arguments` 是 JSON 格式字符串，调用前务必 `json.loads` 并做参数校验，不要直接信任模型输出去执行危险操作（数据库写入、shell 命令等）。
- 若开启了 `thinking` 且使用交错式思考（Interleaved Thinking）/保留式思考（Preserved Thinking），把 `assistant` 消息加回历史时还需要带上 `reasoning_content`，详见第六节。

---

## 五、结构化输出（JSON 模式）

### JSON 输出

**Endpoint**: 复用 `POST /paas/v4/chat/completions`，通过 `response_format` 控制。

**用途**: 让模型直接返回可被 `json.loads` 解析的 JSON 文本，便于程序化处理，常用于信息抽取、分类打标、生成配置等场景。

**关键参数**：

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| :-- | :-- | :-- | :-- | :-- |
| `response_format.type` | string | 否 | `text` | `text`（普通文本）或 `json_object`（JSON 输出）；仅纯文本对话模型支持 |

**示例请求**：

```bash
curl --location 'https://open.bigmodel.cn/api/paas/v4/chat/completions' \
--header 'Authorization: Bearer YOUR_API_KEY' \
--header 'Content-Type: application/json' \
--data '{
    "model": "glm-5.2",
    "messages": [
        {"role": "system", "content": "你是情感分析专家，仅以 JSON 格式返回：{\"sentiment\":\"positive/negative/neutral\",\"confidence\":0.0,\"analysis\":\"...\"}"},
        {"role": "user", "content": "今天天气真好，心情很愉快！"}
    ],
    "response_format": {"type": "json_object"}
}'
```

```python
import json
import requests

payload = {
    "model": "glm-5.2",
    "messages": [
        {
            "role": "system",
            "content": (
                "你是情感分析专家。请严格按照以下 JSON 结构返回，不要输出多余文字：\n"
                '{"sentiment": "positive/negative/neutral", "confidence": 0.95, '
                '"emotions": ["joy"], "keywords": ["天气"], "analysis": "..."}'
            ),
        },
        {"role": "user", "content": "今天天气真好，心情很愉快！"},
    ],
    "response_format": {"type": "json_object"},
}
resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json=payload,
)
result = json.loads(resp.json()["choices"][0]["message"]["content"])
print(result["sentiment"], result["confidence"])
```

**示例响应**：`choices[0].message.content` 是一段可直接 `json.loads` 的字符串，例如 `{"sentiment":"positive","confidence":0.95,"emotions":["joy"],"keywords":["天气","心情"],"analysis":"..."}`。

**注意事项**：

- 平台没有类似"strict JSON Schema"的原生强约束模式（即没有 `response_format.type = "json_schema"`）；`response_format` 目前只有 `text`/`json_object` 两种取值。要让输出符合特定结构，必须在 `system`（或 `user`）消息里把目标 JSON 结构/字段说明写清楚，模型会尽量遵循，但不是数据库级别的强约束。
- 建议拿到结果后用 `jsonschema` 等库做二次校验（`json.loads` 解析失败或字段缺失时要有降级/重试逻辑），因为模型仍可能输出格式略有偏差的 JSON 或在极端情况下夹带解释性文字。
- `response_format` 仅对纯文本对话模型请求体生效，视觉/音频/角色扮演模型的请求体中没有该字段。
- JSON 模式会一定程度限制模型语言的自然度，建议只在需要程序化解析的场景使用。

---

## 六、深度思考（Thinking / Reasoning）

### 深度思考基础

深度思考通过启用思维链（Chain of Thought），让模型在正式回答前先进行多步分析，提升复杂任务（多步推理、方案设计、策略规划）的准确性与可解释性，代价是响应时间变长、消耗额外 Token。仅 GLM-4.5 及以上模型支持。

**关键参数**：

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| :-- | :-- | :-- | :-- | :-- |
| `thinking.type` | string | 否 | `enabled` | `enabled`/`disabled`。**GLM-5.3、GLM-5.3-FLASH 在标准端点 `…/api/paas/v4` 不支持关闭**，传 `disabled` 报 `1210`（已实测）；同一请求体打 Coding 端点 `…/api/coding/paas/v4` 却会被接受并真的关闭思考（`reasoning_tokens=0`，已实测），见 `references/coding-plan.md` |
| `thinking.clear_thinking` | boolean | 否 | `true` | 是否清除历史轮次的 `reasoning_content`，控制 Preserved Thinking，见下 |
| `reasoning_effort` | string | 否 | `max` | 推理强度，仅 GLM-5.2 及以上支持 |

**不同模型系列的思考行为差异**：

| 模型系列 | `thinking.type=enabled` 时的实际行为 |
| :-- | :-- |
| GLM-5.3、GLM-5.3-FLASH | 标准端点强制思考、无法关闭（传 `disabled` 报 `1210`），思考强度由 `reasoning_effort` 控制；Coding 端点实测可关闭 |
| GLM-4.7、GLM-4.5V | 强制思考 |
| GLM-5.2、GLM-5.1、GLM-5、GLM-5-Turbo、GLM-5V-Turbo、GLM-4.6、GLM-4.6V、GLM-4.5 | 模型自动判断是否需要思考 |

**`reasoning_effort` 档位**：

| 取值 | 含义 | 适用模型 |
| :-- | :-- | :-- |
| `max`（默认） | 深度推理 | GLM-5.2 及以上通用 |
| `xhigh` | 增强推理，映射为 `max` | 仅 GLM-5.2 |
| `high` | 增强推理 | GLM-5.3/5.3-FLASH 与 GLM-5.2 均支持 |
| `medium` | 映射为 `high` | 仅 GLM-5.2 |
| `low` | 轻量思考 | GLM-5.3/5.3-FLASH 与 GLM-5.2 均支持 |
| `minimal` | 放弃思考，等价 `none` | 仅 GLM-5.2 |
| `none` | 放弃思考 | 仅 GLM-5.2 |

GLM-5.3 / GLM-5.3-FLASH 仅接受 `max`/`high`/`low` 三档，传其它值会报错；视觉模型（如 GLM-5.3-Flash 视觉请求体）同样仅支持 `max`/`high`/`low`。

> **已用真实 API 调用验证（2026-09）**：对同一个问题分别用 `reasoning_effort: "low"` 和 `"max"` 实测 glm-5.3，`low` 档返回的 `usage.completion_tokens_details.reasoning_tokens` 实测为 **0**（`max` 档同一问题约 800+），说明 `low` 在实际效果上接近"不思考"，不要按字面"轻量思考"理解成"思考但输出少"——如果代码逻辑依赖 `reasoning_content` 一定非空，`low` 档会拿到空值，需要做好判空处理。另外单独实测确认：给 `thinking.type` 传 `"disabled"` 在 glm-5.3 上会直接报错（业务错误码 `1210`，消息为"该模型始终思考，不支持关闭思考；请使用 low、high 或 max。"），不是被静默忽略。

**示例请求**：

```python
import requests

payload = {
    "model": "glm-5.3",
    "messages": [{"role": "user", "content": "详细解释量子计算的基本原理，并分析其在密码学领域的潜在影响"}],
    "thinking": {"type": "enabled"},
    "reasoning_effort": "max",
    "max_tokens": 4096,
}
resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json=payload,
)
msg = resp.json()["choices"][0]["message"]
print("思维链:", msg.get("reasoning_content"))
print("回答:", msg["content"])
```

**示例响应（关键字段）**：

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "……最终回答……",
      "reasoning_content": "让我从多个角度分析这个问题……"
    },
    "finish_reason": "stop"
  }],
  "usage": {"completion_tokens": 239, "prompt_tokens": 8, "total_tokens": 247}
}
```

### 思考模式：交错式思考 / 保留式思考 / 轮级思考

- **交错式思考（Interleaved Thinking）**：GLM-4.5 起默认支持，模型在多次工具调用之间、以及拿到工具结果之后可以继续思考，串联多步工具调用与推理。使用交错思考 + 工具时，必须显式保留 `reasoning_content` 并在把工具结果传回时一并带上。
- **保留式思考（Preserved Thinking）**：允许模型在上下文中保留此前 assistant 回合的 `reasoning_content`，提升推理连续性、模型表现与缓存命中率。在 Coding Plan 端点默认开启，在标准 API 端点默认关闭；标准 API 中通过 `thinking.clear_thinking: false` 开启。开启后必须把历史 `reasoning_content` **完整、未修改、按原顺序**传回，缺失/裁剪/改写/重排都会降低效果或直接失效。`clear_thinking` 只影响跨轮次的历史 thinking，不影响当前轮是否产生思考。
- **轮级思考（Turn-level Thinking）**：GLM-4.7 新增能力，同一会话内每一轮可独立开关思考——简单轮次关闭思考换取低时延，复杂轮次开启思考换取准确率，尤其适合 Agent/工具调用场景。

**开启 Preserved Thinking 的工具调用循环示例**（把 `reasoning_content` 带回历史）：

```python
import json
import requests

URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
HEADERS = {"Authorization": "Bearer YOUR_API_KEY"}
TOOLS = [{"type": "function", "function": {
    "name": "get_weather",
    "description": "获取天气信息",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
}}]

messages = [{"role": "user", "content": "北京天气怎么样？"}]

resp = requests.post(URL, headers=HEADERS, json={
    "model": "glm-5.1",
    "messages": messages,
    "tools": TOOLS,
    "thinking": {"type": "enabled", "clear_thinking": False},  # False 开启 Preserved Thinking
})
message = resp.json()["choices"][0]["message"]

# 关键：把 reasoning_content 原样带回历史，保持推理连贯
messages.append({
    "role": "assistant",
    "content": message.get("content"),
    "reasoning_content": message.get("reasoning_content"),
    "tool_calls": message.get("tool_calls"),
})
for tc in message.get("tool_calls") or []:
    messages.append({
        "role": "tool",
        "tool_call_id": tc["id"],
        "content": json.dumps({"weather": "Sunny", "temp": "25°C"}),
    })

resp2 = requests.post(URL, headers=HEADERS, json={
    "model": "glm-5.1",
    "messages": messages,
    "tools": TOOLS,
    "thinking": {"type": "enabled", "clear_thinking": False},
})
print(resp2.json()["choices"][0]["message"]["content"])
```

**注意事项**：

- 开启深度思考会增加响应时间与 Token 消耗，简单事实查询/翻译/分类等轻量任务建议关闭（GLM-5.3/5.3-FLASH 在标准端点无法关闭，用 `reasoning_effort: "low"` 替代）。
- Preserved Thinking 对 `reasoning_content` 的透传要求非常严格：必须完整、未改写、按原顺序，否则效果下降甚至失效，也会影响缓存命中率。
- 流式场景下 `reasoning_content` 通过 `delta.reasoning_content` 增量返回，需要自行拼接后再原样存回历史消息。

---

## 七、上下文缓存（Context Cache）

上下文缓存是**隐式、自动**的能力：无需任何额外参数，平台会自动识别请求中与此前请求重复或高度相似的内容（典型如固定的 `system` 提示词、长文档、多轮对话历史前缀），命中时直接复用之前的计算结果，从而降低 Token 成本并加快响应速度。支持所有主流模型，包括 GLM-5.2、GLM-5.1、GLM-5 系列等。

**如何触发**：让重复内容在请求间保持完全一致且位置相同即可，常见做法：

- 系统提示词固定不变（多轮对话中 `system` 消息内容逐字相同）。
- 把长文档整体放进 `system` 消息，多次针对同一文档提问。
- 维护完整的对话历史（`ConversationManager` 模式），让每次请求都在前一次的消息列表基础上追加，而不是重新拼装。

**如何观测命中情况**：响应 `usage.prompt_tokens_details.cached_tokens` 字段给出本次命中的缓存 Token 数：

```python
resp = requests.post(url, headers=headers, json=payload)
usage = resp.json()["usage"]
cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
print(f"缓存命中 {cached}/{usage['prompt_tokens']} tokens")
```

**计费影响**：仅适用于**标准 API 计费**（不包括资源包和 GLM Coding Plan 套餐）。新内容 Token 按标准价格计费，缓存命中 Token 按优惠价格计费（通常为标准价格的 50%），输出 Token 始终按标准价格计费。

**使用限制 / 注意事项**：

- 缓存基于内容相似度自动触发，完全相同的内容命中率最高；哪怕是空格、标点等轻微格式差异也可能导致不命中。
- 缓存有时效性，过期后会重新计算（不保证长期存在）。
- 首次请求需要建立缓存，可能略慢；后续复用请求才能体现出加速效果。
- 想提高命中率：系统提示词尽量模板化/稳定；长文档放进 `system` 消息而不是每次重新组织措辞；对话历史采用"追加式"管理，不要对历史消息做无谓的改写或重排。

---

