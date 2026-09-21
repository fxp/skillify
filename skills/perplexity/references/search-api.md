# Search API：只要原始检索结果，不要 LLM 生成答案

⚠ 本文件全部内容整理自官方文档与 OpenAPI 规范，未用真实 Key 调用验证。

Search API 是四个核心 API 里唯一"不过 LLM"的一个：给一个或多个查询词，拿回排名网页结果（标题/URL/摘要/日期），不生成任何自然语言答案。适合自己接自己的 LLM、做数据管线/索引，或者只是想要比通用搜索引擎更贴近"AI 友好"排序的结果列表。

## Endpoint

**`POST https://api.perplexity.ai/search`** — 注意**没有** `/v1` 前缀，是文档站里唯一一个不带版本号的核心端点。

**鉴权**: `Authorization: Bearer $PERPLEXITY_API_KEY`

## 基本用法

```python
from perplexity import Perplexity

client = Perplexity()
search = client.search.create(
    query="SpaceX Starship architecture and orbital test milestones",
    max_results=5
)
for result in search.results:
    print(f"{result.title}: {result.url}")
```

```bash
curl -X POST 'https://api.perplexity.ai/search' \
  -H "Authorization: Bearer $PERPLEXITY_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query": "SpaceX Starship architecture", "max_results": 5}' | jq
```

## 请求字段（来自 OpenAPI `components.schemas` for `POST /search`）

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string \| array\<string\> | 是 | - | 单个查询或多查询数组（最多 5 个，见"多查询"一节） |
| `max_results` | integer | 否 | `10` | 网页搜索最多 20；`search_type: "people"` 时最多 50 |
| `search_type` | string | 否 | `"web"` | `web` / `people` |
| `search_context_size` | string | 否 | `"high"`（**注意默认值和 Sonar/Agent API 的 `"low"` 不同**） | `low`/`medium`/`high`，控制每页抽取内容量；与 `max_tokens`/`max_tokens_per_page` 互斥（省略其一） |
| `max_tokens` | integer | 否 | - | 所有结果页合计的最大内容 token 数 |
| `max_tokens_per_page` | integer | 否 | - | 单页最大抽取 token 数 |
| `country` | string | 否 | - | ISO 3166-1 alpha-2，粗粒度地区个性化（没有 Sonar/Agent API 那样完整的 `user_location` 对象） |
| `search_domain_filter` | array\<string\> | 否 | - | 见 `references/search-controls.md` |
| `search_language_filter` | array\<string\> | 否 | - | 见 `references/search-controls.md` |
| `search_recency_filter` / `search_after_date_filter` / `search_before_date_filter` / `last_updated_after_filter` / `last_updated_before_filter` | 见上 | 否 | - | 格式与互斥规则同 `references/search-controls.md` |

⚠ **`search_context_size` 默认值文档不一致**：Search API 的 OpenAPI 规范把默认值标为 `"high"`（本文件已确认），而 Sonar/Agent API 的默认值是 `"low"`。三套 API 共享同名字段但默认档位不同，照抄一边的"不传就是最便宜"假设放到 Search API 上会得到最贵的默认档位。

## 响应结构

```json
{
  "id": "...",
  "results": [
    {
      "title": "...", "url": "https://...",
      "snippet": "...", "date": "2026-02-20", "last_updated": "2026-02-21"
    }
  ],
  "server_time": null
}
```

⚠ 文档未说明：`date`/`last_updated` 的具体日期字符串格式（响应示例里出现过 `YYYY-MM-DD` 也出现过 `null`），`server_time` 字段的用途未展开说明。

## 多查询搜索

一次请求最多传 5 个查询（`query` 传数组），每个查询独立处理，结果一起返回：

```python
search = client.search.create(
    query=[
        "artificial intelligence trends 2024",
        "machine learning breakthroughs recent",
        "AI applications in healthcare"
    ],
    max_results=5
)
```

**⚠ 计费单位和限流单位不是一回事**（重要，见下方"计费与限流"）。

## 人物搜索

传 `search_type="people"` 把查询路由到人物搜索索引，其余参数（`max_results` 等）照常生效：

```python
response = client.search.create(
    query="Stripe VP of Engineering",
    search_type="people",
    max_results=10
)
```

用途：查具体某人的职业背景、按职位找某公司的员工、研究领导团队构成。**`max_results` 上限从网页搜索的 20 提升到 50**（仅 `search_type: "people"` 时生效）。

## 计费与限流（两套不同的计数方式）

- **计费**：按**成功请求数**收费，$5.00 / 1000 次请求，**与请求里塞了几个 query 无关**——一次带 5 个 query 的请求算 1 个计费单位。失败请求（校验错误、被限流、上游故障）不计费；返回空结果集的成功请求仍计费。
- **限流**：按**查询单位**计，`POST /search` 限速 50 query units/秒，突发容量 50 query units。**单查询请求消耗 1 个 query unit，多查询请求消耗"数组长度"个 query unit**——同样是那个带 5 个 query 的请求，计费上是 1 单位，限流上是 5 单位。按"我一分钟发几次请求"估算限流预算，在大量使用多查询请求时会显著低估真实消耗。

限流算法是漏桶（leaky bucket），限流阈值与账号的 usage tier 无关，所有账号统一（不像 Sonar/Agent API 那样按 tier 分级）。

## 与 Agent API `web_search` 工具的关系

两者都能搜网页，但用途不同：Search API 是"给我原始结果，我自己处理"；Agent API 的 `web_search` 是"模型自己决定搜什么、怎么用结果生成答案"，你拿到的是包在 `output` 数组里的 `search_results` 条目 + 最终生成的文字回答，不是独立可调用的检索原语。如果你的产品需要"先搜索、人工/规则筛选结果、再决定要不要喂给 LLM"这种控制粒度，用 Search API；如果直接要一个带来源的成品答案，用 Agent API 或 Sonar。

文档也提到可以把 Search API 注册成 Anthropic/OpenAI/Gemini 官方 SDK 里的一个 function/tool，让那些 SDK 的模型走标准 tool-use 循环调用 Perplexity 检索（`docs/search/agent-sdks/*`），本 skill 未展开这几篇的具体接线代码。

## Perplexity Search SDK（"Search as Code"）

文档另外提到一个独立的 **Search SDK**（`docs/search-sdk/overview.md`）："an agents-first Python SDK that brings Perplexity's Search as Code approach"，是比直接调 `POST /search`更高层的组合式检索原语库。⚠ 本 skill 未展开这部分内容，超出核心场景覆盖范围，需要时单独读该文档页。
