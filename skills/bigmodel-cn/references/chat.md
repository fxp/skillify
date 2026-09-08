# 对话补全（Chat Completions）

对话补全是智谱开放平台的核心能力域，覆盖文本对话、多模态（图片/视频/文件）理解、工具调用（Function Calling / 联网搜索 / 知识库检索 / MCP）、流式输出、深度思考（Reasoning）、结构化输出与上下文缓存。所有请求均以 `https://open.bigmodel.cn/api/` 为 Base URL，鉴权方式为 HTTP Bearer Token：

```
Authorization: Bearer <API_KEY>
```

API Key 在 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取。模型代码、各模型上下文窗口/`max_tokens` 上限等详见 `models.md`。

---

> **本文只含最常用的三节**：同步对话、流式输出、核心参数速查。
> 异步对话、函数调用、JSON 模式、深度思考、上下文缓存见 [`chat-advanced.md`](chat-advanced.md)。
> 动手前请先看 `SKILL.md` 的「静默陷阱速查表」——那里已经列出本域全部实测踩坑点，多数情况不必再读本文。

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

## 八、核心参数速查

| 参数 | 类型 | 默认值 | 取值范围 | 说明 |
| :-- | :-- | :-- | :-- | :-- |
| `do_sample` | boolean | `true` | `true`/`false` | `false` 时走贪心解码，`temperature`/`top_p` 被忽略；需要确定性输出（代码生成、翻译）时建议设 `false` |
| `temperature` | number | 依模型而定（GLM-5.x/4.7/4.6 为 `1.0`，GLM-4.5 系列为 `0.6`，GLM-4 系列为 `0.75`） | `[0.0, 1.0]`，两位小数 | 越高越随机/有创造性，越低越确定；与 `top_p` 二选一调整 |
| `top_p` | number | 依模型而定（GLM-5.x/4.7/4.6/4.5 系列为 `0.95`，GLM-4 系列为 `0.9`） | `[0.01, 1.0]`，两位小数 | 核采样阈值；建议 0.8-0.95；与 `temperature` 二选一调整 |
| `max_tokens` | integer | 依模型而定 | `[1, 131072]`（视模型上限不同） | 只限制输出长度，不含输入；各模型具体默认值/上限见 `models.md` |
| `stream` | boolean | `false` | `true`/`false` | 是否 SSE 流式返回 |
| `thinking.type` | string | `enabled` | `enabled`/`disabled` | 仅 GLM-4.5 及以上支持；GLM-5.3/5.3-FLASH 在标准端点不可关闭（Coding 端点实测可以） |
| `reasoning_effort` | string | `max` | 见第六节档位表 | 仅 GLM-5.2 及以上支持，`thinking` 开启时生效 |

不同模型家族的 `temperature`/`top_p`/`max_tokens` 具体默认值与上限差异较大（例如视觉模型、音频模型、CharGLM/Emohaa 各不相同），本表仅给出纯文本旗舰模型的典型值，完整的分模型参数表见 `models.md`。
