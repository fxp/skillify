# Search：`POST /search`

> ⚠ 本文件全部内容整理自官方文档（https://docs.exa.ai/search/... ）与 OpenAPI 规范 `exa-spec.json`（`SearchRequest`/`SearchResponse` schema），**未经真实 API 调用验证**。字段名/类型/必填来自规范，行为描述（"会报错"、"会被忽略"）来自文档正文，一律视为 `⚠ 文档原文，未实测`。

目录：[基本用法](#基本用法) · [选搜索模式 type](#选搜索模式-type) · [内容选项 contents](#内容选项-contents-highlightstextsummary) · [过滤条件](#过滤条件) · [结构化输出 outputSchema](#结构化输出-outputschema) · [Deep Search 细节](#deep-search-细节) · [Exa Snapshot 历史快照](#exa-snapshot-历史快照) · [响应字段](#响应字段) · [注意事项汇总](#注意事项汇总)

## 基本用法

**Endpoint**: `POST https://api.exa.ai/search`
**用途**: 自然语言查询网页，返回排序后的结果列表，可选一并抽取每条结果的正文/高亮/摘要，或让 Exa 直接把结果综合成一句话答案/结构化 JSON。是本 skill 里最常用、最便宜的端点，`query` 是唯一必填字段。

**关键参数**（请求体顶层，`application/json`）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string | 是 | — | 自然语言查询，唯一必填字段 |
| `type` | enum | 否 | `auto` | `instant`/`fast`/`auto`/`deep-lite`/`deep`/`deep-reasoning`，见下表 |
| `numResults` | integer | 否 | 10 | 公开上限 100；不支持分页 |
| `contents` | object | 否 | 无（不返回正文） | 内容选项容器，见下节 |
| `includeDomains` / `excludeDomains` | array\<string\> | 否 | — | 最多 1200 项；支持完整域名、路径前缀（`example.com/docs`）、子域通配（`*.example.com`） |
| `startPublishedDate` / `endPublishedDate` | ISO 8601 date-time | 否 | — | 按发布日期过滤，注意不是 `maxAgeHours` |
| `startCrawlDate` / `endCrawlDate` | ISO 8601 date-time | 否 | — | **规范原文标注 "Deprecated and has no effect; ignored by the API"**——传了也不会生效，不会报错 |
| `category` | string | 否 | — | `company`/`publication`/`news`/`personal site`/`financial report`/`people` 等；`company`/`people` 类目返回结构化 `entities` 字段，但不支持 `startPublishedDate`/`endPublishedDate`/`excludeDomains`（传了 400） |
| `userLocation` | string | 否 | — | 两位 ISO 国家码，如 `US` |
| `compliance` | enum | 否 | — | 仅 `hipaa`，企业专属，要求只走缓存检索 |
| `outputSchema` | object | 否 | — | 触发结构化/文本综合，见下节 |
| `systemPrompt` | string | 否 | — | 指导综合行为的额外指令（信源偏好、去重等），**不是**用来指定输出结构 |
| `stream` | boolean | 否 | `false` | 仅在提供 `outputSchema` 时生效，走 SSE |
| `additionalQueries` | array\<string\> | 否 | — | 最多 10 条，**仅 deep 系列 type 生效**，为深度研究提供额外检索方向 |
| `moderation` | boolean | 否 | `false` | 开启内容审核过滤 |

**示例请求**

```bash
curl -s -X POST "https://api.exa.ai/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $EXA_API_KEY" \
  -d '{
    "query": "recent techniques for improving retrieval in RAG systems",
    "type": "auto",
    "contents": { "highlights": true }
  }'
```

```python
from exa_py import Exa  # pip install exa-py

exa = Exa()  # 读环境变量 EXA_API_KEY
result = exa.search(
    "recent techniques for improving retrieval in RAG systems",
    type="auto",
    contents={"highlights": True},
)
for r in result.results:
    print(r.title, r.url, r.highlights)
```

**示例响应**（⚠ 文档原文，未实测，字段来自 OpenAPI `example`）

```json
{
  "requestId": "b5947044c4b78efa9552a7c89b306d95",
  "results": [
    {
      "title": "A Comprehensive Overview of Large Language Models",
      "url": "https://arxiv.org/pdf/2307.06435.pdf",
      "publishedDate": "2023-11-16T01:36:32.547Z",
      "author": "Humza Naveed, ...",
      "id": "https://arxiv.org/abs/2307.06435",
      "image": "https://arxiv.org/pdf/2307.06435.pdf/page_1.png",
      "favicon": "https://arxiv.org/favicon.ico",
      "text": "Abstract Large Language Models (LLMs) have recently...",
      "highlights": ["Such requirements have limited their adoption..."],
      "summary": "This overview paper on Large Language Models..."
    }
  ],
  "resolvedSearchType": "neural",
  "costDollars": { "total": 0.007, "search": { "neural": 0.007 } }
}
```

注意：`results[].id` 在示例里就是结果的 URL 本身（不是一个不透明的内部 ID）。文档说它"Useful for the /contents endpoint"——即可以把 `/search` 结果的 `id` 直接塞进 `/contents` 的 `ids` 数组去二次取内容。

## 选搜索模式 type

**`type` 的合法值已经整体换代**（⚠ 来自 OpenAPI `enum`，不是训练语料里熟悉的 `neural`/`keyword`/`auto`）：

| `type` | 用在什么场景 | 延迟/深度 | 定价（含 10 条结果） |
|---|---|---|---|
| `instant` | 实时路径：自动补全、语音助手 | 最低延迟，检索深度换速度 | 与 `auto` 同档，$7/1k 次 |
| `fast` | 延迟敏感的用户可见搜索 | 降延迟，质量仍高 | $7/1k 次 |
| `auto`（默认） | 大多数场景的质量/速度平衡 | — | $7/1k 次 |
| `deep-lite` | 需要轻量研究+综合，且要求稳定约 4 秒延迟 | 比完整 deep 浅 | $12/1k 次 |
| `deep` | 需要多步检索、证据核验、结构化多条目输出 | 4–15 秒 | $12/1k 次 |
| `deep-reasoning` | 完整性和推理深度优先于延迟 | 12–40 秒 | $15/1k 次 |

`deep-lite`/`deep`/`deep-reasoning` 统称 "Deep Search"：不是简单换个参数值，检索过程本身变成"检索→核验证据→必要时补充检索→综合"的多轮循环，可用 `additionalQueries` 提供起始的检索方向变体。三种 deep 模式的默认限流是 5 QPS（其余 type 是 10 QPS，见 `errors-and-limits.md`）。

文档原文建议：比起 `deep-reasoning` 做长耗时研究/建列表/多跳富化，优先考虑 Exa Agent（见 `references/agent.md`）——Agent 有更多计算预算，且原生返回带引用的结构化结果。

## 内容选项 `contents.{highlights|text|summary}`

不传 `contents` 就没有正文，只有 `title`/`url`/`publishedDate`/`author`/`id`/`image`/`favicon` 等元数据。三种正文视图**建议三选一**（文档原文 "Pick one content view per request"；⚠ 未实测是否真的允许同时传多个，只是同时传会分别计费）：

| 视图 | 参数 | 说明 |
|---|---|---|
| Highlights | `contents.highlights: true` 或 `{query, verbosity, maxCharacters, dynamic}` | 摘录式片段，Exa 自己的抽取模型按相关性选段，官方推荐默认选项。不传子字段时不需要自己调字符预算 |
| Full text | `contents.text: true` 或 `{maxCharacters, includeHtmlTags, verbosity, includeSections, excludeSections}` | 完整正文（markdown 风格）；页面可能很大，建议配合 `maxCharacters`（上限 10000） |
| Summary | `contents.summary: {query, schema}` | 每条结果额外发起一次 LLM 调用生成摘要，成本更高（$1/1k pages）；`schema` 可传 JSON Schema 做结构化摘要 |

`contents.extras`：`links`（返回的站内链接数）、`imageLinks`、`richImageLinks`、`richLinks`、`codeBlocks`。

**Highlights 的 verbosity/dynamic 两个子选项是 Beta 功能**：`contents.highlights.verbosity`（`low`/`medium`/`high` 预设长度）和 `contents.highlights.dynamic`（跨结果集共享一个上下文预算，而不是逐条独立分配）都要求请求头 `Exa-Beta: dynamic-highlights-2026-08-28`，不带这个头传这两个字段会被拒绝（⚠ 文档原文，未实测拒绝的具体错误码）。

**内容新鲜度 `contents.maxAgeHours`**（不是发布时间过滤器，控制"抓取内容的缓存新鲜度"）：

| 取值 | 行为 |
|---|---|
| 省略 | 有缓存用缓存，没有则按需抓取 |
| 正整数 N | 缓存若新于 N 小时则用缓存，否则抓取；上限 720 |
| `0` | 总是抓新鲜页面（唯一能保证拿到最新渲染文本/HTML 标签的方式，`includeHtmlTags`、`verbosity`、`includeSections` 等选项要生效也建议配 `maxAgeHours: 0`） |
| `-1` | 只用缓存，绝不抓取现网页面 |

已废弃的 `contents.livecrawl`（字符串枚举 `always`/`preferred`/`fallback`/`never`）仍可能出现在旧代码/旧教程里，文档给了迁移表：

| 旧 `livecrawl` | 对应新写法 |
|---|---|
| `always` | `maxAgeHours: 0` |
| `never` | `maxAgeHours: -1` |
| `fallback` | 省略 `maxAgeHours` |
| `preferred` | 无直接等价，建议用较小的正整数，如 `maxAgeHours: 1` |

`contents.context`（顶层也有同名 `context` 字段）：**已废弃**，规范原文"Use highlights or text instead"，只是把正文拼成一个字符串返回，不建议再用。

## 过滤条件

- `includeDomains`/`excludeDomains`：接受完整域名（`example.com`）、路径前缀（`example.com/docs`）、子域通配（`*.example.com`），最多各 1200 项。文档原文建议把路径过滤写在这里，而不是在 `query` 里拼 `site:` 操作符（"Use this parameter for domain or path filtering instead of adding a `site:` operator to the query"）。
- `startPublishedDate`/`endPublishedDate`：只按 Exa 从页面 HTML 解析出的"估计发布日期"过滤，不保证每个页面都有可用值。
- `startCrawlDate`/`endCrawlDate`：⚠ **规范原文明确标注"Deprecated and has no effect; ignored by the API"**——历史上这俩参数曾用于按 Exa 爬取日期过滤，现在传了不会报错，但也完全不起作用，是最容易被旧代码继续传、却悄悄失效的一对参数。
- 过滤条件的原则（文档正文）：只在"不满足条件的结果完全不可用"时加硬过滤；只是偏好用自然语言写进 `query`，或在综合时写进 `systemPrompt`。

## 结构化输出 `outputSchema`

给 `outputSchema` 会在响应里加一个 `output` 对象，`results` 里仍然是原始排序结果。`output.content` 是生成的值，`output.grounding` 是逐字段的引用来源+置信度（`low`/`medium`/`high`），**不要**在自己的 schema 里再定义 citation/confidence 字段，Exa 会自动补。

两种 `outputSchema` 形态：

| `outputSchema.type` | 用途 | 结果字段 |
|---|---|---|
| `"text"` | 生成一段自由文本，`description` 控制格式/长度 | `output.content` 是字符串 |
| `"object"` | 生成符合 `properties`/`required` 的 JSON | `output.content` 是对象 |

⚠ 文档原文（未实测）：结构化 schema **最多支持 2 层嵌套、10 个属性**，超出会怎样未说明。`outputSchema` 对任意 `type`（包括非 deep 的 `auto`/`fast`/`instant`）都生效，会额外增加约 2 秒综合延迟；`stream: true` 只有配合 `outputSchema` 才有意义，否则接口仍返回普通 JSON。

```python
result = exa.search(
    "AI infrastructure companies that announced Series A or B funding in the past six months",
    output_schema={
        "type": "object",
        "properties": {
            "companies": {
                "type": "array",
                "maxItems": 10,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "round": {"type": "string"},
                        "amount": {"type": "string"},
                    },
                    "required": ["name", "round", "amount"],
                },
            }
        },
        "required": ["companies"],
    },
)
print(result.output.content if result.output else None)
```

## Deep Search 细节

`deep-lite`/`deep`/`deep-reasoning` 复用同一个 `POST /search`，只是 `type` 不同，处理流程多了"计划检索→检索并核验→必要时精修→选择并综合"四步（文档原文用 `<Steps>` 描述）。`numResults` 控制的是最终返回给你的结果条数，**不是**深度检索过程中内部会发起多少次检索。

- `additionalQueries`（最多 10 条）**只在 deep 系列 type 下生效**，用于提供你已知的、值得覆盖的不同角度/术语，不要用来堆砌同一个query 的近义改写。
- `systemPrompt` 管"怎么做研究、怎么呈现"（信源偏好、去重、新颖性约束），`query` 管"研究什么"，二者职责分开。
- 结构化输出建议优先用 deep 系列（文档原文："Deep modes are recommended by default when using outputSchema"），尤其是需要 3 个以上字段或多条目的场景；简单结构可以留在 `auto`/`fast`。

## Exa Snapshot 历史快照

`contents.snapshotAsOf`（`/search`）把内容锚定到某个历史时间点，只返回 Exa 在该时间点前已存有版本的页面：

```json
{
  "query": "latest stable Python release notes",
  "numResults": 3,
  "contents": { "snapshotAsOf": "2026-07-01T00:00:00Z", "highlights": true }
}
```

⚠ 文档原文，未实测的关键限制：

- 只支持 `auto`/`fast`/`instant` 三种 type，**不支持** `deep-lite`/`deep`/`deep-reasoning`，也不支持 `category` 参数。
- 快照请求**不能**同时传 `livecrawl`、`livecrawlTimeout`、`maxAgeHours`、`subpages`，混用会被拒绝并报 `INVALID_REQUEST`（因为历史请求只能用存量版本，不能触达现网）。
- 快照锚定的是"返回内容用哪个版本"，**不影响候选 URL 的排序检索**——Exa 仍然用当前检索信号找候选页，只是内容取历史版本，不是"完整还原当时的搜索结果排序"。
- 回溯窗口滚动 5 个月，按量计费套餐 10 QPS、每账号 100 次请求后需联系销售继续开通。

## 响应字段

**Response 200**（`oneOf`：无 `outputSchema` 时是 `SearchResultsResponse`，有 `outputSchema` 时是 `SearchSynthesisResponse`，后者额外多一个必填的 `output`）

| 字段 | 类型 | 说明 |
|---|---|---|
| `requestId` | string | 排障时优先带上这个 ID |
| `results[]` | array | 见下表 |
| `resolvedSearchType` | string | ⚠ **文档自相矛盾**：schema 描述写"Deprecated legacy field. Current production responses may return an empty string; clients should not branch on this value."，例值给的是 `""`；但 `POST /search` 参考页自己的响应示例又写着 `"resolvedSearchType": "neural"`。两处口径不一致，不要用它做分支逻辑 |
| `costDollars.total` / `.search.neural` / `.search.keyword` / `.summary` | number | 本次请求的估算成本拆分，不是账单记录 |
| `searchTime` | number | 服务端处理耗时（毫秒），可能不含综合阶段 |
| `output.content` / `output.grounding` | — | 仅 `outputSchema` 场景存在 |

`results[]` 每项：`title`（必填）、`url`（必填）、`publishedDate`、`author`、`id`（临时 ID，通常就是 URL）、`image`、`favicon`、`text`、`highlights[]`、`highlightScores[]`（余弦相似度）、`summary`、`subpages[]`（结构同 `results[]`）、`entities[]`（仅 `category: company`/`people`/`publication` 等实体类目返回，含 `id`/`type`/`version`/`properties`，公司实体有 `workforce`/`headquarters`/`financials`/`webTraffic`/`research` 等子字段，人物实体有 `firstName`/`lastName`/`workHistory`/`educationHistory` 等）。

## 注意事项汇总

- `/search` 把内容选项包在 `contents: {...}` 里；姊妹端点 `/contents` 把同名字段直接摊在请求体顶层——**不是同一套请求体结构**，照抄容易搞反，见 `references/contents-and-find-similar.md`。
- `numResults` 默认 10、公开上限 100，**不支持分页**；想要超过 100 条要联系销售。
- `category: "company"` 或 `"people"` 时，`startPublishedDate`/`endPublishedDate`/`excludeDomains` 会导致 400（文档原文明确列出这三个，不是"全部日期类参数"）。
- `moderation: true` 开启内容审核，会拦截什么类型的内容文档未细说，⚠ 文档未说明。
- 错误信封是扁平结构 `{"requestId", "error", "tag"}`（400/401/402/429/500/503 都一致），和 Agent API 的嵌套结构不同，见 `references/errors-and-limits.md`。
