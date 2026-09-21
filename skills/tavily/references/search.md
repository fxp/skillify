# Search — 实时网页搜索

> ⚠ 文档版参考：内容来自官方 OpenAPI 规范（字段表权威来源）+ Best Practices for Search + Changelog（叙述性说明），
> 抓取于 2026-09-21，**未用真实 API Key 验证**。报错原文、响应示例均标注来源。

目录：[1. 默认值的文档矛盾](#1-max_results-默认值的文档矛盾) · [2. search_depth](#2-search_depth关键参数决定费用和内容形态)
· [3. 关键参数表](#3-关键参数表来自-openapi-规范) · [4. 过滤参数详解](#4-过滤参数详解) · [5. 示例请求](#5-示例请求)
· [6. 示例响应](#6-示例响应文档给出的字段形态未实测) · [7. 注意事项](#7-注意事项)

## 1. `max_results` 默认值的文档矛盾

⚠ 文档自相矛盾，三处说法不一致，**拿到 Key 后第一件事就测这个**（不传 `max_results` 直接调用，数一下 `results` 长度）：

| 来源 | 默认值 |
| :--- | :--- |
| OpenAPI 规范 `search.md` 参数说明 | `10` |
| Python SDK Reference 参数表 | `10` |
| 官方 Best Practices for Search 页正文 | "Limits results returned (default: `5`)" |
| Tavily CLI `--max-results` 选项表 | `5` |

**保守写法：永远显式传 `max_results`，不要依赖默认值**，这样无论哪个是真的都不影响行为。`max_results` 合法范围 `0`–`20`（OpenAPI `minimum`/`maximum`，这一条没有矛盾）。

## 2. `search_depth`：关键参数，决定费用和内容形态

| 档位 | 费用（API Credit / 次请求） | 返回内容形态 | 延迟 | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| `ultra-fast` | 1 | **Content**（整页 NLP 摘要，一条） | 最低 | 时间敏感场景；`safe_search` 不支持（⚠ 文档未说明是报错还是忽略） |
| `fast` | 1 | **Chunks**（重排序分块，条数由 `chunks_per_source` 控制） | 低 | 想要分块格式又要低延迟 |
| `basic`（默认） | 1 | **Chunks**（2026-07 起，此前是单条摘要——见下方 changelog 提示） | 中 | 通用场景的默认选择 |
| `advanced` | 2 | **Chunks**，覆盖面和相关性最高 | 较高 | 冷门话题、最新发布内容、多面向问题 |

> **Changelog 提示（2026-07）**：`search_depth=basic` 此前只返回单条页面摘要，现在和 `fast`/`advanced` 一样返回可配置条数的重排序分块，
> `results[].content` 里多条分块用 `[...]` 分隔符拼接。**训练数据较旧的模型很可能还记得"`basic` = 单条摘要"的旧行为，不要照旧印象写解析代码**
> （比如假设 `content` 一定是一段连续摘要而不做 `[...]` 切分）。

`chunks_per_source`：每个来源最多返回的分块数（每块 ≤500 字符），**Search 场景上限是 3**（`advanced`/`basic`/`fast` 都可用，`ultra-fast` 不适用，
因为它返回的是整页摘要不是分块），默认 3。注意 Extract/Crawl 的同名参数上限是 5，不要混用同一套心智模型。

`auto_parameters`：开启后 Tavily 按 query 内容自动配置参数（含可能把 `search_depth` 升到 `advanced`，见 SKILL.md 通用规则第 2 条）；
`include_answer`、`include_raw_content`、`max_results` 这三个必须手动设置，`auto_parameters` 不会帮你决定（因为它们直接影响响应体积）。

## 3. 关键参数表（来自 OpenAPI 规范）

**Endpoint**: `POST /search`
**用途**: 对给定 query 执行一次实时网页搜索，返回按相关性排序的结果列表，可选附带 AI 生成的简短答案、图片、原始页面内容。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `query` | string | 是 | — | 搜索查询。官方建议 <1500 字符，复杂/多主题查询拆成多个独立请求（见 §7） |
| `search_depth` | enum | 否 | `basic`（⚠ 见 §1 同类矛盾，默认值本身没有争议，是 `max_results` 有争议） | `advanced`/`basic`/`fast`/`ultra-fast`，见 §2 |
| `chunks_per_source` | int | 否 | `3` | 1–3；仅 `advanced`/`basic`/`fast` 深度生效 |
| `max_results` | int | 否 | ⚠ 见 §1 | 0–20 |
| `topic` | enum | 否 | `general` | `general`/`news`/`finance`；`news` 常用于实时时事，会自动开启 `include_published_date` |
| `time_range` | enum | 否 | — | `day`/`week`/`month`/`year`（或简写 `d`/`w`/`m`/`y`）。**默认不会剔除无发布日期的结果**，除非同时传 `filter_by_published_date: true` |
| `start_date` / `end_date` | string | 否 | — | `YYYY-MM-DD`，按发布 / 最后更新日期过滤；同样默认不剔除无日期结果 |
| `include_published_date` | bool | 否 | `false` | `topic=news` 时自动开启；beta 阶段 |
| `filter_by_published_date` | bool | 否 | `false` | true 时才会真正剔除时间窗外及无日期的结果，同时自动开启 `include_published_date` |
| `include_answer` | bool\|string | 否 | `false` | `true`/`"basic"` 快答案；`"advanced"` 更详细的答案 |
| `include_raw_content` | bool\|string | 否 | `false` | `true`/`"markdown"` 返回 markdown 正文；`"text"` 返回纯文本（可能更慢） |
| `include_images` | bool | 否 | `false` | 顶层 `images[]` + 每条结果自带 `images[]` |
| `include_image_descriptions` | bool | 否 | `false` | 需要 `include_images=true` 才有意义 |
| `include_favicon` | bool | 否 | `false` | 每条结果的 favicon URL |
| `include_domains` | array\<string\> | 否 | `[]` | 最多 300 个域名 |
| `exclude_domains` | array\<string\> | 否 | `[]` | 最多 150 个域名 |
| `include_domains_mode` | enum | 否 | — | `restrict`（硬过滤，只保留列表内域名）/`prefer`（软偏好，列表外域名仍可能出现）。**必须先设 `include_domains`，否则 400** |
| `country` | enum（~150 个国家名） | 否 | — | 仅 `topic=general` 时生效 |
| `language` | string | 否 | — | ISO 639-1 代码或英文语言名；默认只是排序加权，不严格过滤 |
| `filter_by_language` | bool | 否 | `false` | true 时严格剔除不匹配语言的结果。**必须先设 `language`，否则 400** |
| `auto_parameters` | bool | 否 | `false` | 见 §2 通用规则第 2 条 |
| `exact_match` | bool | 否 | `false` | query 里用引号包住短语，仅返回包含该原文短语的结果，绕过同义词/语义变体 |
| `safe_search` | bool | 否 | `false` | 过滤成人/不安全内容；**`fast`/`ultra-fast` 深度不支持**（⚠ 文档未说明报错还是忽略，2026-08 起面向所有套餐开放） |
| `include_usage` | bool | 否 | `false` | 响应里附带本次调用的 credit 消耗明细 |

## 4. 过滤参数详解

**时间过滤三件套不是互斥的**：`time_range`（相对时间窗）、`start_date`/`end_date`（绝对时间窗）、`filter_by_published_date`（是否严格执行）。
只传前两者中的一个而不传 `filter_by_published_date`，效果是"软优先"而不是硬过滤——没有可探测发布日期的结果依然会留在结果里。
想要"日期窗口内 + 保留无日期结果"，只传 `include_published_date: true` 配合时间窗，不要设 `filter_by_published_date`。

**域名过滤两种模式**：`include_domains_mode: "restrict"`（默认心智模型里"include just means include"的硬过滤）
vs `"prefer"`（软优先，列表外域名仍可能进入结果，适合"优先权威来源但不想空手而归"的场景，如财经/新闻查询）。
`exclude_domains` 永远是硬过滤，不受 `include_domains_mode` 影响；子域名匹配规则：列主域名会连子域名一起过滤，列子域名只精确匹配该子域名
（2026-08 changelog 明确的匹配规则，之前版本文档未必写清楚，判断"父域名是否连带子域名"时以这条为准）。

## 5. 示例请求

```bash
curl -X POST https://api.tavily.com/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TAVILY_API_KEY" \
  -d '{
    "query": "latest developments in AI regulation",
    "search_depth": "advanced",
    "topic": "news",
    "time_range": "week",
    "max_results": 5,
    "chunks_per_source": 3,
    "include_answer": "basic"
  }'
```

```python
import os
from tavily import TavilyClient

client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

response = client.search(
    query="latest developments in AI regulation",
    search_depth="advanced",
    topic="news",
    time_range="week",
    max_results=5,          # 显式传，不依赖有争议的默认值（见 §1）
    chunks_per_source=3,
    include_answer="basic",
)
print(response["results"])
```

## 6. 示例响应（文档给出的字段形态，未实测）

```json
{
  "query": "latest developments in AI regulation",
  "answer": "A short LLM-generated answer, only present when include_answer was requested.",
  "images": [],
  "results": [
    {
      "id": "a3f9c2-00",
      "title": "Example Article Title",
      "url": "https://example.com/article",
      "content": "<chunk 1 text> [...] <chunk 2 text> [...] <chunk 3 text>",
      "score": 0.81,
      "raw_content": null,
      "published_date": null,
      "favicon": "https://example.com/favicon.ico"
    }
  ],
  "response_time": 1.23,
  "request_id": "123e4567-e89b-12d3-a456-426614174111"
}
```

字段说明要点：`content` 在开启分块的深度下是多个分块用 `[...]` 拼接，不是单一连续段落；`raw_content` 默认为 `null`，只有 `include_raw_content` 为真时才有值；
`answer`/`images`（除非 `include_images`）/`auto_parameters` 字段仅在对应请求参数开启时才出现在响应里，不要假设它们总是存在（哪怕值是 `null`）。

## 7. 注意事项

- **query 建议 <1500 字符，复杂/多主题问题拆成多个独立请求**，而不是塞进一个长 query 里让 Tavily 自己拆分（官方原话："Think of it as a query for an agent
  performing web search, not long-form prompts."）。
- **HTTP 错误码**：400（参数不合法，如设了 `include_domains_mode` 却没设 `include_domains`）、401（key 缺失或错误）、429（超限流，看 `Retry-After` 头）、
  432（Key/Plan 额度超限）、433（PAYGO 额度超限）、422（请求体 schema 校验失败，`detail[]` 数组逐条给出 `loc`/`msg`）、500。以上均为文档原文，未实测（⚠ 文档原文，未实测）。
- **异步批量搜索**：用 `AsyncTavilyClient` + `asyncio.gather`，官方建议用信号量控制并发（`concurrency ≈ (RPM / 60) × 平均延迟秒数`），
  每个请求都要单独捕获异常并打标（`ok`/`error`），不要让一个 429 拖垮整批；示例见官方 Best Practices for Search 页的 `search_one`/`batch_search` 模式。
- **跨调用去重**：多个搜索的结果按 URL（去掉 query string 和结尾斜杠）合并，`content` 里的分块按 `[...]` 拆开后再去重拼接，避免同一页面的内容重复占用上下文。
- **多步骤 Agent 工作流要传 `session_id`（可选 `human_id`）**，同一任务的多次调用（先 search 再 extract 再追加 search）共用一个 `session_id`，
  便于 Tavily 侧做归因分析；用 MCP 时 `X-Session-Id` 由 MCP server 自动生成，不需要手动设置。
- **keyless 访问**（无需注册/免费）：header `X-Tavily-Access-Mode: keyless`，响应 schema 和有 key 时完全一致，限流更严格；同时传 keyless header
  和有效 `Authorization: Bearer` 时以后者为准。仅 `/search`、`/extract` 支持 keyless，`/crawl`、`/map`、`/research` 必须要 key。
