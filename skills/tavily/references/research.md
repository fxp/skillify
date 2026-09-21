# Research — 多步骤深度研究与带引用的报告

> ⚠ 文档版参考：字段表来自官方 OpenAPI 规范，流式协议与最佳实践来自叙述性文档，抓取于 2026-09-21，**未用真实 API Key 验证**。

目录：[1. 这是 Tavily 的"Q&A/深度研究"能力](#1-这是-tavily-的-qa深度研究能力) · [2. 创建任务](#2-创建研究任务) · [3. 查询状态](#3-查询任务状态)
· [4. 流式输出](#4-流式输出-sse) · [5. 计费](#5-计费动态区间不是固定单价) · [6. 注意事项](#6-注意事项)

## 1. 这是 Tavily 的"Q&A/深度研究"能力

Tavily 没有一个单独叫"Q&A"或"Answer"的 endpoint；对"给我一个问题的答案"这类需求，有两条路：

- **轻量级**：`POST /search` 传 `include_answer: true`（或 `"advanced"`），在搜索结果之外附带一段 LLM 生成的简短答案，见 `search.md`。
- **重量级、需要综合多个来源并生成结构化/带引用报告**：`POST /research`，本文件描述的能力——会执行多次搜索、分析来源、生成详细研究报告，
  是异步任务模型（创建任务 → 轮询或流式获取结果），不是搜索那种一次请求一次响应的同步调用。

## 2. 创建研究任务

**Endpoint**: `POST /research`
**用途**: 提交一个研究任务，Tavily 的研究 Agent 会自主执行多次搜索、分析来源，生成综合报告（或按 `output_schema` 生成结构化 JSON）。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `input` | string | 是 | — | 研究任务/问题描述 |
| `model` | enum | 否 | `auto` | `mini`（窄且明确的问题，高效）/`pro`（跨多子话题的复杂课题，全面）/`auto`（不确定复杂度时） |
| `stream` | bool | 否 | `false` | true 时返回 SSE 流，见 §4 |
| `output_schema` | object | 否 | — | JSON Schema，需含 `properties`，可选 `required`；提供后报告按该结构输出，而不是自由文本 |
| `citation_format` | enum | 否 | `numbered` | `numbered`/`mla`/`apa`/`chicago` |
| `include_domains` | array\<string\> | 否 | `[]` | **软偏好**，最多 20 个；即使设置了，其他域名的来源仍可能出现在报告里 |
| `exclude_domains` | array\<string\> | 否 | `[]` | **硬屏蔽**，最多 20 个；屏蔽主域名连子域名一起屏蔽（下行匹配），屏蔽子域名不影响主域名本身 |
| `output_length` | enum | 否 | `standard` | `short`/`standard`/`long`；官方强调这是"目标区间不是硬上限"，具体问题需要时长度可能超出区间 |
| `files` | array\<object\> | 否 | — | 附带文件作为额外信息源（连同网络搜索一起被引用），最多 5 个，仅 `.txt`/`.md`/`.json`，单文件 ≤8 万词，全部文件合计 ≤8 万词，base64 编码 |

**示例请求**

```bash
curl -X POST https://api.tavily.com/research \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TAVILY_API_KEY" \
  -d '{
    "input": "Analyze the competitive landscape for AI coding assistants in the SMB market in 2026",
    "model": "pro",
    "citation_format": "numbered"
  }'
```

```python
import os
from tavily import TavilyClient

client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
task = client.research(
    input="Analyze the competitive landscape for AI coding assistants in the SMB market in 2026",
    model="pro",
)
print(task["request_id"], task["status"])  # 提交成功不代表任务已完成，见 §3
```

**示例响应（201，文档给出的字段形态，未实测）**

```json
{
  "request_id": "123e4567-e89b-12d3-a456-426614174111",
  "created_at": "2025-01-15T10:30:00Z",
  "status": "pending",
  "input": "What are the latest developments in AI?",
  "model": "mini",
  "response_time": 1.23
}
```

⚠ **提交成功的 HTTP 状态码是 201，不是 200**（当 `stream: false` 时）。用 `response.status_code == 200` 判断"提交成功"会误判成失败。

## 3. 查询任务状态

**Endpoint**: `GET /research/{request_id}`
**用途**: 轮询获取研究任务的状态和结果。

**关键参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `request_id` | path | string | 是 | 创建任务时返回的 ID |
| `include_usage` | query | bool | 否 | 附带 credit 消耗明细 |

**状态码和 status 字段的组合，是这个 endpoint 最容易踩坑的地方**：

| HTTP 状态码 | `status` 字段值 | 含义 |
| :--- | :--- | :--- |
| **202** | `pending` / `in_progress` | 任务还没跑完，需要继续轮询 |
| **200** | `completed` | 任务成功，`content`（报告正文，字符串或 `output_schema` 指定的结构化对象）和 `sources[]` 都有值 |
| **200** | `failed` | 任务失败（依然是 200！），`content`/`sources` 不存在，只有 `request_id`/`status`/`response_time`/可选 `usage` |
| 401 | — | key 缺失或错误 |
| 404 | — | `request_id` 不存在 |
| 500 | — | 服务端错误 |

**只有 200 代表"任务已经跑完"，但 200 本身不代表"任务成功"，必须再看 `status` 是 `completed` 还是 `failed`。** 只按状态码判断会把还在跑的任务（202）
误当成错误，或者把跑完但失败的任务（200 + `status: failed`）误当成成功。

**示例请求**

```bash
curl -X GET "https://api.tavily.com/research/123e4567-e89b-12d3-a456-426614174111" \
  -H "Authorization: Bearer $TAVILY_API_KEY"
```

```python
import time

while True:
    result = client.get_research(task["request_id"])  # 方法名以实测/SDK Reference 为准，OpenAPI 只定义了 GET /research/{id}
    if result["status"] in ("completed", "failed"):
        break
    time.sleep(10)

if result["status"] == "completed":
    print(result["content"])
    print(result["sources"])
else:
    print("research task failed", result.get("request_id"))
```

## 4. 流式输出（SSE）

设 `stream: true` 时，`POST /research` 直接以 `text/event-stream` 返回，不再是先拿 `request_id` 再轮询的模式。事件结构**兼容 OpenAI Chat Completions
的 chunk 格式**（`object: "chat.completion.chunk"`、`choices[0].delta`），但 `delta` 里塞的是 Tavily 自己的字段，不是标准 OpenAI 字段：

| 事件类型 | 出现位置 | 关键字段 |
| :--- | :--- | :--- |
| Tool Call | `delta.tool_calls.type == "tool_call"` | `name`（`Planning`/`WebSearch`/`ResearchSubtopic`[仅 pro]/`Generating`）、`id`、`arguments`、`queries`[仅 WebSearch] |
| Tool Response | `delta.tool_calls.type == "tool_response"` | 同上 + `sources[]`（该工具调用发现的来源） |
| Content | `delta.content` | 字符串（自由文本报告分片）或对象（`output_schema` 场景下的结构化分片） |
| Sources | `delta.sources[]` | 内容流完之后，给出本次研究用到的全部来源 |
| Done | `event: done`（无 JSON body） | 流结束标志 |
| Error | `object: "error"` | `error` 字段给出错误信息 |

典型顺序：`Planning` tool_call/response → `WebSearch` tool_call/response（可能多轮）→（`pro` 模式下还有 `ResearchSubtopic` 循环）→
`Generating` tool_call/response → 若干 Content 事件 → Sources 事件 → Done。

```python
from tavily import TavilyClient

client = TavilyClient(api_key="tvly-YOUR_API_KEY")
stream = client.research(input="Research the latest developments in AI", model="pro", stream=True)
for chunk in stream:
    print(chunk.decode("utf-8"))
```

流式和轮询是互斥的两条路径，不要对同一个 `stream: true` 的请求既解析 SSE 又去调 `GET /research/{id}` 轮询——流式请求根本不会预先给你一个可轮询的 `request_id`
（响应体本身就是流，不是先返回 201 + `request_id`）。

## 5. 计费：动态区间，不是固定单价

和 Search/Extract/Crawl「每次调用 = 固定 credit 数」不同，Research 按**每请求的最小 / 最大 credit 边界**动态计费：

| | `model=pro` | `model=mini` |
| :--- | :--- | :--- |
| 每请求最低 | 15 credits | 4 credits |
| 每请求最高 | 250 credits | 110 credits |

具体落在区间哪个位置取决于任务实际执行的搜索轮次和 Subtopic 展开程度，**下单前无法精确预知这次会花多少 credit**，只能知道上下界。
预算敏感的场景应该：(a) 优先用 `mini` 而不是默认 `auto`（`auto` 可能升级到 `pro` 的区间），(b) 用 `include_usage=true` 在拿到结果后核对真实花费，
(c) 不要假设"一次 research 调用"和"一次 search 调用"是同一数量级的成本，区间下限（`mini` 4 credits）也已经是 basic search 的 4 倍。

## 6. 注意事项

- **速率限制独立且更严格**：任务创建（`POST /research`）无论开发还是生产 key 都固定 20 RPM；轮询 `GET /research/{id}` 走默认限速（开发 100 / 生产 1000 RPM），
  不要把轮询频率和任务创建频率搞混——高频轮询不会撞到 20 RPM 那条线，高频创建新任务会。
- **`files` 参数只接受纯文本类文件**（`.txt`/`.md`/`.json`），不支持 PDF/Word 等需要额外解析的格式；传超过限制（5 个文件、单文件 8 万词、合计 8 万词）的行为
  文档未说明是报错还是截断，⚠ 文档未说明，待验证。
- `output_schema` 至少要有一个 `properties` 里的 key 出现在 `required` 里（OpenAPI 描述原文），空 `required` 数组是否报错未说明。
- **HTTP 错误码**：400/401/429/432/433/500 与 Search 共用同一套语义（见 `errors-and-limits.md`），`GET` 额外有 404（`request_id` 不存在）。
