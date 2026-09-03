# 对话补全（Chat Completions）

对话补全是智谱开放平台的核心能力域，覆盖文本对话、多模态（图片/视频/文件）理解、工具调用（Function Calling / 联网搜索 / 知识库检索 / MCP）、流式输出、深度思考（Reasoning）、结构化输出与上下文缓存。所有请求均以 `https://open.bigmodel.cn/api/` 为 Base URL，鉴权方式为 HTTP Bearer Token：

```
Authorization: Bearer <API_KEY>
```

API Key 在 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取。模型代码、各模型上下文窗口/`max_tokens` 上限等详见 `models.md`。

---

## 一、对话补全（同步）

### 对话补全

**Endpoint**: `POST /paas/v4/chat/completions`

**用途**: 与指定模型进行一次对话，模型基于 `messages` 一次性（`stream=false`）或流式（`stream=true`）返回响应。支持纯文本模型、视觉模型（GLM-5.3-Flash、GLM-5V-Turbo、GLM-4.6V 等）、音频模型（GLM-4-Voice）、角色扮演/心理咨询模型（CharGLM-4、Emohaa）四类请求体，本节聚焦最常用的纯文本 / 视觉对话模型。

#### messages 消息结构

| 角色 | 说明 |
| :-- | :-- |
| `system` | 系统消息，设定模型行为与角色，`content` 为字符串 |
| `user` | 用户消息。纯文本模型 `content` 为字符串；视觉模型 `content` 可为字符串，也可为多模态数组（见下） |
| `assistant` | 模型回复，可包含 `content`、`reasoning_content`（历史思维链，见"深度思考"一节）、`tool_calls` |
| `tool` | 工具调用结果，必须携带 `tool_call_id` 指回对应的 `tool_calls[].id` |

`messages` 不能只包含 `system` 或 `assistant` 消息，至少要有一条 `user` 消息。

**多模态 `content` 数组**（视觉模型 user 消息，四选一或组合）：

| type | 对应字段 | 说明 |
| :-- | :-- | :-- |
| `text` | `text`（字符串） | 文本片段 |
| `image_url` | `image_url.url` | 图片 URL 或 Base64；单图 ≤5M，像素 ≤6000×6000，支持 jpg/png/jpeg。GLM-5.3-Flash/GLM-5V-Turbo/GLM-4.6V/GLM-4.5V 最多 50 张；GLM-4V-Plus-0111 最多 5 张；GLM-4V-Flash 仅 1 张且不支持 Base64 |
| `video_url` | `video_url.url` | 视频 URL，mp4/mkv/mov。GLM-5.3-Flash/GLM-5V-Turbo/GLM-4.6V/GLM-4.5V 限 200M 内；GLM-4V-Plus 限 20M 内且时长 ≤30s。GLM-4V-Plus-0111 要求 `video_url` 必须是 `content` 数组第一项 |
| `file` | `file.file_id` / `file.file_url` / `file.file_data` / `file.filename` | 文件输入，三选一（`file_id` 来自文件上传接口、`file_url` 为直链、`file_data` 为 `data:<MIME>;base64,<DATA>`）。单文件 ≤50M，最多 50 个；`file` 为新类型，兼容历史 `file_url` type（不建议再用旧类型名）。**用 `file_id` 时，上传文件必须传 `purpose=user_data`**（见下方重要提示），此时实际支持的格式只有 `pptx/ppt/docx/doc/xlsx/xls/pdf`，不含 txt/jsonl |

音频模型（`glm-4-voice`）另有 `input_audio` 类型（`data` 为 Base64，`format` 为 `wav`/`mp3`，音频最长 10 分钟，1 秒音频折算 12.5 Token），不属于本节视觉模型范围，用法类似。

> **已用真实 API 调用验证（2026-09）：`file` 类型的 `file_id` 只认 `purpose=user_data` 上传的文件**。用 `POST /paas/v4/files` 上传文件时，`purpose` 传 `agent`、`code-interpreter` 或其他值（这些同样能接受 pdf/txt 等格式、上传本身不会报错）拿到的 `file_id`，放进 `chat/completions` 的 `file` 类型引用时会返回 `{"error":{"code":"1210","message":"文件解析失败，请检查文件可访问性和格式"}}`——上传成功不代表这个 file_id 能被 chat 接口读取。只有 `purpose=user_data` 上传的文件才能被 `file` 类型正常解析（实测用一份 PDF 验证：`user_data` 直接成功提取出文件里的合同编号；同一份文件用 `agent`/`code-interpreter` 上传后引用则 100% 报错）。而 `user_data` 这个 purpose 本身只接受 `pptx/ppt/docx/doc/xlsx/xls/pdf`（已用真实调用验证 `.txt` 会在上传阶段就被拒绝：`"文件格式暂不支持，仅支持: pptx/ppt/docx/doc/xlsx/xls/pdf"`）——也就是说，想让 chat/completions 直接读一个 `.txt` 或 `.jsonl` 文件，`file` 类型这条路完全走不通（无论传哪个 purpose），需要改用 `file_data`（Base64 内联）或 `file_url`（直链），或者改走 `references/files-batch.md` 里的文档解析服务。

#### 关键参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| :-- | :-- | :-- | :-- | :-- |
| `model` | string | 是 | - | 模型代码，如 `glm-5.3`、`glm-5.3-flash`（视觉） |
| `messages` | array | 是 | - | 见上表 |
| `stream` | boolean | 否 | `false` | 是否 SSE 流式输出，见第三节 |
| `thinking` | object | 否 | `{"type":"enabled"}` | 深度思考开关，仅 GLM-4.5 及以上支持，见第六节 |
| `reasoning_effort` | string | 否 | `max` | 推理强度，仅 GLM-5.2 及以上支持，见第六节 |
| `tools` | array | 否 | - | `function`/`retrieval`/`web_search`/`mcp` 四类工具，最多 128 个，见第四节 |
| `tool_choice` | string | 否 | `auto` | 仅支持 `auto` |
| `tool_stream` | boolean | 否 | `false` | 工具调用参数是否流式返回，仅 GLM-5.3/5.2/5.1/5/5-Turbo/4.7/4.6 支持，见第三节 |
| `response_format` | object | 否 | `{"type":"text"}` | `text` 或 `json_object`，仅纯文本模型支持，见第五节 |
| `do_sample` | boolean | 否 | `true` | 是否采样；`false` 时忽略 `temperature`/`top_p`，走贪心解码 |
| `temperature` | number | 否 | 视模型而定 | `[0.0, 1.0]`，两位小数 |
| `top_p` | number | 否 | 视模型而定 | `[0.01, 1.0]`，两位小数 |
| `max_tokens` | integer | 否 | 视模型而定 | 输出 token 上限，最大 131072（视模型），建议不小于 1024 |
| `stop` | array\<string\> | 否 | - | 最多 4 个停止词 |
| `request_id` | string | 否 | 自动生成 | 6-64 字符，建议用 UUID |
| `user_id` | string | 否 | - | 终端用户标识，6-128 字符，不建议包含敏感信息 |

各参数详细取值范围/各模型默认值见第八节速查表；`tools`/`response_format`/`thinking`/`reasoning_effort` 的完整语义见第四、五、六节。视觉模型请求体的 `tools` 仅支持 `function` 类型，且仅 GLM-5.3-Flash、GLM-4.6V、AutoGLM-Phone 支持；`tool_choice` 仅 GLM-4.6V 支持。

#### 示例请求（纯文本）

```bash
curl --location 'https://open.bigmodel.cn/api/paas/v4/chat/completions' \
--header 'Authorization: Bearer YOUR_API_KEY' \
--header 'Content-Type: application/json' \
--data '{
    "model": "glm-5.3",
    "messages": [
        {"role": "system", "content": "你是一个乐于助人的助手。"},
        {"role": "user", "content": "用一句话介绍一下你自己。"}
    ]
}'
```

```python
import requests

url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json",
}
payload = {
    "model": "glm-5.3",
    "messages": [
        {"role": "system", "content": "你是一个乐于助人的助手。"},
        {"role": "user", "content": "用一句话介绍一下你自己。"},
    ],
}

resp = requests.post(url, headers=headers, json=payload, timeout=60)
resp.raise_for_status()
data = resp.json()
print(data["choices"][0]["message"]["content"])
print("usage:", data["usage"])
```

#### 示例请求（多模态：图片 + 文本）

```python
import requests

payload = {
    "model": "glm-5.3-flash",
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "描述一下这张图片里有什么。"},
                {"type": "image_url", "image_url": {"url": "https://example.com/cat.jpg"}},
            ],
        }
    ],
}
resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json=payload,
)
print(resp.json()["choices"][0]["message"]["content"])
```

视频与文件输入的用法一致，只需把 `content` 数组中的项换成 `{"type": "video_url", "video_url": {"url": "..."}}` 或 `{"type": "file", "file": {"file_url": "..."}}`（也可用 `file_id`/`file_data`）。

#### 示例响应（非流式，关键字段）

```json
{
  "id": "...",
  "request_id": "...",
  "created": 1735000000,
  "model": "glm-5.3",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "……模型回复……",
        "reasoning_content": "……思维链（仅开启 thinking 的模型返回）……",
        "tool_calls": null
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 20,
    "completion_tokens": 120,
    "total_tokens": 140,
    "prompt_tokens_details": {"cached_tokens": 0}
  },
  "web_search": [],
  "content_filter": []
}
```

`finish_reason` 取值：`stop`（正常结束/命中 stop 词）、`tool_calls`（命中函数调用）、`length`（达到 `max_tokens`）、`sensitive`（触发内容安全拦截，需业务判断是否撤回）、`network_error`（模型推理异常）、`model_context_window_exceeded`（超出上下文窗口）。

#### 注意事项

- `content` 在使用 `tool_calls` 时可能为 `null`；判断是否为函数调用应看 `finish_reason == "tool_calls"` 或 `message.tool_calls` 是否非空，而不是 `content` 是否为空。
- 视觉模型（GLM-4.5V 系列）的 `content` 中可能带有 `<think></think>` 思考标签与 `<|begin_of_box|>...<|end_of_box|>` 文本边界标签，解析时需要额外处理。
- `reasoning_content` 只在开启 `thinking` 且模型系列支持时返回（GLM-4.5 系列、GLM-4.1V-Thinking 系列等）。
- `response_format` 仅纯文本对话模型支持，视觉/音频/角色扮演模型请求体中没有该字段。
- `temperature` 与 `top_p` 建议二选一调整，不要同时改动。

---

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

## 三、流式输出（SSE）

### 基本 SSE 协议

将 `stream` 设为 `true` 后，响应的 `Content-Type` 变为 `text/event-stream`，服务端按 Server-Sent Events 格式持续推送多个 `data: {...}` 事件，每个事件是一个 JSON chunk，字段结构与非流式响应的 `choices[].message` 类似，但用 `delta` 承载增量内容：

```
data: {"id":"1","created":1677652288,"model":"glm-5.2","choices":[{"index":0,"delta":{"content":"春"},"finish_reason":null}]}

data: {"id":"1","created":1677652288,"model":"glm-5.2","choices":[{"index":0,"delta":{"content":"天"},"finish_reason":null}]}

...

data: {"id":"1","created":1677652288,"model":"glm-5.2","choices":[{"index":0,"finish_reason":"stop","delta":{"role":"assistant","content":""}}],"usage":{"prompt_tokens":8,"completion_tokens":262,"total_tokens":270}}

data: [DONE]
```

- 每个 chunk 的 `choices[0].delta` 可能包含 `content`（增量文本）、`reasoning_content`（增量思维链）、`tool_calls`（增量工具调用，见下）、`audio`（`glm-4-voice` 增量音频）。
- `finish_reason` 与 `usage` 只出现在最后一个有效 chunk 中。
- 流以字面量 `data: [DONE]` 结束，客户端应以此为终止信号，不要尝试对它做 JSON 解析。

**用标准库 requests 消费 SSE**（不依赖 SDK）：

```python
import json
import requests

url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
headers = {"Authorization": "Bearer YOUR_API_KEY", "Content-Type": "application/json"}
payload = {
    "model": "glm-5.2",
    "messages": [{"role": "user", "content": "写一首关于春天的诗"}],
    "stream": True,
}

full_content = ""
with requests.post(url, headers=headers, json=payload, stream=True, timeout=120) as resp:
    resp.raise_for_status()
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        data_str = line[len("data:"):].strip()
        if data_str == "[DONE]":
            break
        chunk = json.loads(data_str)
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta", {})
        if delta.get("content"):
            full_content += delta["content"]
            print(delta["content"], end="", flush=True)
        if choices[0].get("finish_reason"):
            usage = chunk.get("usage")
            print(f"\n\nfinish_reason={choices[0]['finish_reason']}, usage={usage}")

print("\n完整内容:\n", full_content)
```

也可以用 `httpx` 的 `client.stream("POST", url, ...)` 达到同样效果，处理方式一致（按行读取，过滤 `data:` 前缀，遇到 `[DONE]` 结束）。

### 工具调用的流式输出（tool_stream）

默认情况下（`tool_stream=false` 或不传），即使 `stream=true`，模型的工具调用参数（`function.arguments`）也会等积累完整后一次性放进某个 chunk 返回。设置 `tool_stream=true`（同时要求 `stream=true`）后，`arguments` 会随 chunk 逐步增量返回，从而更快开始渲染/减少调用延迟。仅 GLM-5.3、GLM-5.2、GLM-5.1、GLM-5、GLM-5-Turbo、GLM-4.7、GLM-4.6 系列支持此参数。

> `tool_stream` 只改变工具调用参数的**返回方式**，平台不会代为执行工具。收到完整参数后仍需应用自行解析执行、把结果通过 `role:"tool"` 消息回传，再次调用模型才能得到最终回答（完整闭环见第四节）。

流式 `delta.tool_calls` 的每一项带 `index`（同一个工具调用在多个 chunk 间用它来对齐拼接）、`id`、`type`、`function.name`、`function.arguments`（增量片段，需要按 `index` 累加拼接成完整 JSON 字符串）：

```python
import requests, json

payload = {
    "model": "glm-5.3",
    "messages": [{"role": "user", "content": "北京天气怎么样"}],
    "tools": [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定地点当前的天气情况",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    }],
    "stream": True,
    "tool_stream": True,
}

final_tool_calls = {}
with requests.post(
    "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json=payload, stream=True,
) as resp:
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        data_str = line[len("data:"):].strip()
        if data_str == "[DONE]":
            break
        chunk = json.loads(data_str)
        delta = chunk["choices"][0]["delta"]
        for tc in delta.get("tool_calls") or []:
            idx = tc["index"]
            if idx not in final_tool_calls:
                final_tool_calls[idx] = {"id": tc.get("id"), "function": {"name": "", "arguments": ""}}
            fn = tc.get("function") or {}
            if fn.get("name"):
                final_tool_calls[idx]["function"]["name"] = fn["name"]
            if fn.get("arguments"):
                final_tool_calls[idx]["function"]["arguments"] += fn["arguments"]

print(final_tool_calls)
```

**注意事项**：

- `tool_stream=true` 必须搭配 `stream=true`，否则无意义。
- 拼接 `arguments` 时一定要按 `index` 分组累加，不能假设一次工具调用只出现在一个 chunk 里。
- 只有 `arguments` 是逐步返回的碎片；`id`、`function.name` 通常在第一个相关 chunk 中给出。

---

## 四、工具调用（Function Calling）

### 支持的工具类型

`tools` 数组中每一项都是 `{"type": "...", "<type>": {...}}` 的形式，`type` 支持四种：

| type | 内层字段 | 说明 |
| :-- | :-- | :-- |
| `function` | `function.name`、`function.description`、`function.parameters`（JSON Schema 对象） | 自定义函数调用，`name` 需匹配 `^[a-zA-Z0-9_-]+$`，长度 ≤64；`description`、`parameters` 均必填 |
| `retrieval` | `retrieval.knowledge_id`（必填）、`retrieval.prompt_template` | 知识库检索，`knowledge_id` 从平台知识库功能创建获取；`prompt_template` 可自定义，需包含 `{{ knowledge }}` 与 `{{ question }}` 占位符 |
| `web_search` | `web_search.enable`、`search_engine`（`search_std`/`search_pro`/`search_pro_sogou`/`search_pro_quark`）、`search_query`、`search_intent`、`count`（1-50）、`search_domain_filter`、`search_recency_filter`、`content_size`、`result_sequence`、`search_result`、`require_search`、`search_prompt` | 联网搜索工具。**必须显式传 `web_search.search_result: true`**，响应体顶层才会带 `web_search` 引用来源数组（`icon`/`title`/`link`/`media`/`publish_date`/`content`/`refer`）——已用真实 API 验证：不传这个字段（默认 `false`）时搜索依然会正常执行、结果依然会被用于生成回答，但响应体里完全没有 `web_search` 这个顶层字段，代码里如果读 `response.get("web_search")` 期望拿到引用列表，默认情况下永远是 `None`，不会报错，只是"想展示信息来源"这个需求会静默失效 |
| `mcp` | `mcp.server_label`（必填）、`mcp.server_url`、`mcp.transport_type`（`sse`/`streamable-http`，默认 `streamable-http`）、`mcp.allowed_tools`、`mcp.headers` | 调用外部 MCP Server 上的工具；若连接智谱官方 MCP Server，`server_label` 填 MCP Code 即可，无需 `server_url` |

`tools` 最多 128 个函数；`tool_choice` 目前默认且仅支持字符串 `"auto"`（不支持强制指定某个函数）。视觉模型的 `tools` 只支持 `function` 类型，且仅 GLM-5.3-Flash / GLM-4.6V / AutoGLM-Phone 支持。

> **已用真实 API 调用验证（2026-09）**：OpenAPI 规范把 `web_search.search_engine` 标记为必填字段，但实测对 `chat/completions` 里的 `web_search` 工具类型省略该字段**并不会报错**——平台会静默套用一个默认搜索引擎，联网检索依然生效。这与下方 `references/tools.md` 里**独立的** `POST /paas/v4/web_search` 端点不同：那个端点已实测确认省略 `search_engine` 会直接返回 `{"error":{"code":"1214","message":"search_engine:The search_engine cannot both be empty."}}`。也就是说同一个字段名，在两个不同入口的必填程度并不一致（规范文档本身也存在类似的不一致）。**实践建议**：无论走哪个入口，都显式传 `search_engine`（如 `search_pro`），不要依赖未文档化的默认值——省略在今天可用不代表未来仍然可用。

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
| `thinking.type` | string | 否 | `enabled` | `enabled`/`disabled`。**GLM-5.3、GLM-5.3-FLASH 不支持关闭**，传 `disabled` 会报错 |
| `thinking.clear_thinking` | boolean | 否 | `true` | 是否清除历史轮次的 `reasoning_content`，控制 Preserved Thinking，见下 |
| `reasoning_effort` | string | 否 | `max` | 推理强度，仅 GLM-5.2 及以上支持 |

**不同模型系列的思考行为差异**：

| 模型系列 | `thinking.type=enabled` 时的实际行为 |
| :-- | :-- |
| GLM-5.3、GLM-5.3-FLASH | 强制思考，无法关闭，思考强度由 `reasoning_effort` 控制 |
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

- 开启深度思考会增加响应时间与 Token 消耗，简单事实查询/翻译/分类等轻量任务建议关闭（GLM-5.3/5.3-FLASH 除外，无法关闭）。
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

## 八、核心参数速查

| 参数 | 类型 | 默认值 | 取值范围 | 说明 |
| :-- | :-- | :-- | :-- | :-- |
| `do_sample` | boolean | `true` | `true`/`false` | `false` 时走贪心解码，`temperature`/`top_p` 被忽略；需要确定性输出（代码生成、翻译）时建议设 `false` |
| `temperature` | number | 依模型而定（GLM-5.x/4.7/4.6 为 `1.0`，GLM-4.5 系列为 `0.6`，GLM-4 系列为 `0.75`） | `[0.0, 1.0]`，两位小数 | 越高越随机/有创造性，越低越确定；与 `top_p` 二选一调整 |
| `top_p` | number | 依模型而定（GLM-5.x/4.7/4.6/4.5 系列为 `0.95`，GLM-4 系列为 `0.9`） | `[0.01, 1.0]`，两位小数 | 核采样阈值；建议 0.8-0.95；与 `temperature` 二选一调整 |
| `max_tokens` | integer | 依模型而定 | `[1, 131072]`（视模型上限不同） | 只限制输出长度，不含输入；各模型具体默认值/上限见 `models.md` |
| `stream` | boolean | `false` | `true`/`false` | 是否 SSE 流式返回 |
| `thinking.type` | string | `enabled` | `enabled`/`disabled` | 仅 GLM-4.5 及以上支持；GLM-5.3/5.3-FLASH 不可关闭 |
| `reasoning_effort` | string | `max` | 见第六节档位表 | 仅 GLM-5.2 及以上支持，`thinking` 开启时生效 |

不同模型家族的 `temperature`/`top_p`/`max_tokens` 具体默认值与上限差异较大（例如视觉模型、音频模型、CharGLM/Emohaa 各不相同），本表仅给出纯文本旗舰模型的典型值，完整的分模型参数表见 `models.md`。
