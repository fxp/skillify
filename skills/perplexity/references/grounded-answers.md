# 用 Sonar Chat Completions 拿带引用的网页问答

⚠ 本文件全部内容整理自官方文档与 OpenAPI 规范，未用真实 Key 调用验证。所有请求/响应示例标 `⚠ 文档原文，未实测`。

**官方现状**：Sonar Chat Completions（`POST /v1/sonar`）仍然完全可用，字段没有变化，是从 Perplexity 早期 API 延续下来的形态——`messages` 数组进、OpenAI 风格 `choices` 出，额外带 `citations`/`search_results` 字段。但文档站每个 `docs/sonar/*` 页面顶部都渲染一个 `<SonarDeprecationNotice />` 组件（Markdown 导出剥掉了组件内容，只留下占位标签，具体文案未知，⚠ 文档未说明），官方入口页也不再把它列进"Available APIs"卡片组（只列 Router/Agent/Search/Embeddings 四个）。**新项目建议先看 `references/agent-api.md`**；本文件适合"已有 OpenAI 兼容集成，想尽快拿引用"或"明确不需要多提供商模型/工具"的场景。

## 目录
- [Endpoint 与鉴权](#endpoint-与鉴权)
- [非流式请求](#非流式请求)
- [流式请求](#流式请求)
- [响应结构](#响应结构)
- [结构化输出](#结构化输出)
- [媒体附件（图片/文件/PDF/视频输入，图片/视频结果输出）](#媒体附件)
- [异步 Chat Completion](#异步-chat-completion)
- [OpenAI SDK 兼容](#openai-sdk-兼容)

## Endpoint 与鉴权

**Endpoint**: `POST https://api.perplexity.ai/v1/sonar`
等价路径（OpenAI 兼容）：`POST https://api.perplexity.ai/chat/completions`——两者文档原文说"both paths accepted by Perplexity for compatibility"，⚠ 文档未说明两者在行为上是否有任何差异，未实测。

**鉴权**: `Authorization: Bearer $PERPLEXITY_API_KEY`

## 非流式请求

```python
from perplexity import Perplexity

client = Perplexity()

completion = client.chat.completions.create(
    model="sonar-pro",
    messages=[
        {"role": "user", "content": "What is quantum computing?"}
    ]
)

print(completion.choices[0].message.content)
```

```bash
curl https://api.perplexity.ai/v1/sonar \
  -H "Authorization: Bearer $PERPLEXITY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sonar-pro",
    "messages": [
      {"role": "user", "content": "What is quantum computing?"}
    ]
  }' | jq
```

**关键请求字段**（来自 OpenAPI `components.schemas` for `POST /v1/sonar`）：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | - | 枚举：`sonar`、`sonar-pro`、`sonar-deep-research`、`sonar-reasoning-pro`。**没有** `sonar-reasoning`（非 Pro）。 |
| `messages` | array | 是 | - | `role` 枚举 `system`/`user`/`assistant`/`tool`；`content` 可以是纯字符串，也可以是数组形式支持文本+图片+文件+PDF+视频混合内容（见媒体附件一节）。 |
| `stream` | boolean | 否 | `false` | 见流式请求一节。 |
| `max_tokens` | integer | 否 | - | 最大补全 token 数。 |
| `temperature` | number | 否 | - | 0-2。 |
| `top_p` | number | 否 | - | nucleus sampling。 |
| `response_format` | object | 否 | 纯文本 | `{"type": "json_schema", "json_schema": {"schema": {...}}}`，见结构化输出一节。 |
| `web_search_options.search_context_size` | string | 否 | `"low"` | `low`/`medium`/`high`，见 `references/search-controls.md`。 |
| `web_search_options.search_type` | string | 否 | - | `fast`/`pro`/`auto`（Pro Search，仅 Sonar Pro）。 |
| `web_search_options.user_location` | object | 否 | - | 地理位置个性化，见 `references/search-controls.md`。 |
| `web_search_options.image_results_enhanced_relevance` | boolean | 否 | `false` | 对图片结果做增强相关性过滤。 |
| `search_mode` | string | 否 | `"web"` | `web`/`academic`/`sec`。 |
| `return_images` | boolean | 否 | - | 见媒体附件一节。 |
| `return_related_questions` | boolean | 否 | - | 返回建议的追问问题。 |
| `enable_search_classifier` | boolean | 否 | - | 让分类器判断是否需要搜索。 |
| `disable_search` | boolean | 否 | - | 完全禁用搜索，模型只用训练知识回答。 |
| `search_domain_filter` / `search_language_filter` / `search_recency_filter` / `search_after_date_filter` / `search_before_date_filter` / `last_updated_after_filter` / `last_updated_before_filter` | 见 `references/search-controls.md` | 否 | - | 挂在请求体顶层，不像 Agent API 那样包在 tool 对象里。 |
| `image_format_filter` / `image_domain_filter` | array\<string\> | 否 | - | 只影响 `return_images` 的图片结果，见媒体附件。 |
| `stream_mode` | string | 否 | `"full"` | `full`（默认，推理事件被压缩、元数据内联）/`concise`（推理事件单独发）。仅影响流式响应格式。 |
| `reasoning_effort` | string | 否 | - | 控制推理强度，主要对 `sonar-deep-research` 有意义。 |
| `language_preference` | string | 否 | - | ISO 639-1，偏好的回答语言。 |

⚠ 文档未说明：`response_format` 还支持一个规范里列出但文档正文未展开的 `type: "regex"` 分支（`agent-api/migrate-from-sonar/how-to.md` 提到"Sonar's `response_format.type: "regex"` has no Agent API equivalent"，侧面证实存在但本文件没抓到它的字段表）。

## 流式请求

设置 `stream: true`：

```python
stream = client.chat.completions.create(
    model="sonar-pro",
    messages=[{"role": "user", "content": "What are the most widely used open-source LLMs?"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

**⚠ 关键行为**（文档原文，`sonar/features.md`）：流式响应包含三类信息——(1) 逐步到达的内容分片；(2) **搜索结果（在最后一个/几个 chunk 里才出现，不是逐步到达）**；(3) usage 统计和其他元数据。想在 UI 里"边生成边显示来源"的实现思路在这里不成立，引用列表要等流结束才完整。

## 响应结构

```json
{
  "id": "a1b2c3d4-...",
  "model": "sonar-pro",
  "created": 1234567890,
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "..."},
      "delta": {"role": "assistant", "content": ""},
      "finish_reason": "stop"
    }
  ],
  "citations": ["https://example.com/a", "https://example.com/b"],
  "search_results": [
    {
      "title": "...", "url": "https://example.com/a",
      "date": "2026-05-01", "last_updated": "2026-05-10",
      "snippet": "...", "source": "web"
    }
  ],
  "usage": {
    "prompt_tokens": 14, "completion_tokens": 287, "total_tokens": 301,
    "search_context_size": "low",
    "citation_tokens": null, "num_search_queries": null, "reasoning_tokens": null,
    "cost": {
      "input_tokens_cost": 0.00008, "output_tokens_cost": 0.00423,
      "request_cost": 0.006, "citation_tokens_cost": null,
      "reasoning_tokens_cost": null, "search_queries_cost": null,
      "total_cost": 0.01031
    }
  }
}
```

⚠ 修正记录：OpenAPI 摘要脚本按 tag 展开 `/v1/sonar` 的 200 响应 schema 时，输出里**遗漏了 `citations`、`search_results`、`images`、`related_questions` 四个顶层字段**（该脚本对深层复用的 `$ref` 有展开不全的已知问题）。用原始 `openapi.json` 里 `CompletionResponse` schema 的 `properties` 列表交叉核对后补全，字段确实存在于规范里：`citations: string[] | null`、`search_results: ApiPublicSearchResult[] | null`、`images: ImageResult[] | null`（仅 `return_images: true` 时非空）、`related_questions: string[] | null`（仅 `return_related_questions: true` 时非空）。写代码解析响应时不要漏读这几个字段；如果你自己也用这套 OpenAPI 摘要脚本处理其他大 schema，建议再拿原始 JSON 抽查一遍 `properties` 键名是否被摘要完整覆盖。

`usage.cost` 的各项子字段只在对应功能被触发时才非 `null`（例如非 `sonar-deep-research` 模型的 `citation_tokens_cost`/`reasoning_tokens_cost`/`search_queries_cost` 恒为 `null`，只有 `input_tokens_cost`/`output_tokens_cost`/`request_cost`/`total_cost` 总是有值）。

## 结构化输出

支持 JSON Schema 结构化输出：

```python
from pydantic import BaseModel
from typing import Optional, List

class FinancialMetrics(BaseModel):
    company: str
    quarter: str
    revenue: float
    key_highlights: Optional[List[str]] = None

completion = client.chat.completions.create(
    model="sonar-pro",
    messages=[{"role": "user", "content": "Summarize Apple's most recent 10-K."}],
    response_format={
        "type": "json_schema",
        "json_schema": {"schema": FinancialMetrics.model_json_schema()}
    }
)
metrics = FinancialMetrics.model_validate_json(completion.choices[0].message.content)
```

**关键点**：
- `json_schema.name` 是**可选**的，默认值 `"schema"`（和 Agent API 不同，见 `references/agent-api.md`）。
- `json_schema.strict` 默认 `true`。
- 第一次用某个新 schema 请求可能有 10-30 秒的首 token 延迟（服务端准备 schema），后续复用同一 schema 的请求没有这个延迟（文档原文）。
- ⚠ 文档原文警告：**不要在 schema 里定义一个"来源链接"字段指望模型填对**——"Requesting links as part of a JSON response may not always work reliably. Use the links returned in the `citations` or `search_results` fields from the API response instead."

## 媒体附件

**发送图片/文件/PDF/视频**（作为 `messages[].content` 数组的一部分，与文本混合）：支持 base64 编码或 HTTPS URL 两种方式，`content` 数组里每个 item 的 `type` 分别是 `text`/`image_url`/`file_url`（可带 `file_name`）/`pdf_url`/`video_url`。⚠ 文档未说明：具体大小限制、支持的 MIME 类型清单本次抓取未展开到字段级别，需要时读 `docs/sonar/media.md` 原文或等真实调用探测。

**接收图片结果**：请求里设 `return_images: true`，响应 `images` 数组才非空；可配合 `image_domain_filter`（限定图片来源域名）、`image_format_filter`（限定 `png`/`jpg` 等格式）、`web_search_options.image_results_enhanced_relevance`（增强相关性过滤）。

**接收视频结果**：⚠ 文档未说明具体请求参数名，只在文档目录里出现"Receiving Videos"小节，本次抓取未展开完整字段表。

**⚠ 重要**：以上所有图片/视频相关字段（`return_images`、`image_domain_filter`、`image_format_filter`、`return_videos` 等）**在 Agent API 里都没有对应物**——Agent API 文档原文明确写"not supported; the Agent API returns no `images`" / "no `videos`"。如果要做需要图片/视频检索结果的功能，只能用 Sonar Chat Completions，不能迁移到 Agent API。

## 异步 Chat Completion

`POST /v1/async/sonar` 提交异步请求，`GET /v1/async/sonar/{api_request}` 轮询结果，`GET /v1/async/sonar` 列出账号下所有异步请求。⚠ 文档原文：这三个 endpoint 页面同样挂了 `<SonarDeprecationNotice />`；Agent API 的对应能力是 `background: true` + 轮询 `GET /v1/agent/{id}`（见 `references/agent-api.md` 的后台运行小节），迁移指南建议新代码直接用后者。

## OpenAI SDK 兼容

把 OpenAI SDK 的 `base_url` 指向 Perplexity 即可，无需改动调用代码：

```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ.get("PERPLEXITY_API_KEY"),
    base_url="https://api.perplexity.ai"
)
resp = client.chat.completions.create(
    model="sonar-pro",
    messages=[{"role": "user", "content": "..."}]
)
```

| OpenAI SDK 调用 | Perplexity endpoint | 说明 |
|---|---|---|
| `client.chat.completions.create()` | `POST /v1/sonar`（别名 `POST /chat/completions`） | 两条路径等价 |
| `client.async_.chat.completions.create()`（Perplexity 原生 SDK 概念，非标准 OpenAI SDK） | `POST /v1/async/sonar`（别名 `POST /async/chat/completions`） | 两条路径等价 |

响应完全匹配 OpenAI 格式，额外带 `search_results`（`title`/`url`/`date`）和 `citations`（URL 数组）两个 Perplexity 专属字段——标准 OpenAI 客户端类型定义不认识这两个字段，用动态解析或 Perplexity 官方 SDK 类型能拿到；纯 OpenAI SDK 场景下这两个字段仍会出现在原始 JSON 里，只是 SDK 的类型提示不会为它们提供自动补全。
