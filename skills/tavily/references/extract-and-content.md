# Extract / Crawl / Map — 已知 URL 抽正文、整站发现与批量抽取

> ⚠ 文档版参考：字段表来自官方 OpenAPI 规范，行为说明来自 Best Practices for Crawl/Extract，抓取于 2026-09-21，**未用真实 API Key 验证**。

目录：[1. 三个 endpoint 怎么选](#1-三个-endpoint-怎么选) · [2. 和 Firecrawl 的选型边界](#2-和-firecrawl-的选型边界)
· [3. Extract](#3-extract) · [4. Crawl](#4-crawl) · [5. Map](#5-map) · [6. 注意事项](#6-注意事项)

## 1. 三个 endpoint 怎么选

| 我已经有… | 我想要… | 用哪个 |
| :--- | :--- | :--- |
| 一个或几个（≤20）已知 URL | 每个 URL 的干净正文 | **Extract** |
| 一个起始 URL，不知道站点结构 | 站内所有 URL 清单，**不需要正文** | **Map** |
| 一个起始 URL，不知道站点结构 | 站内多个页面的正文，一次拿到 | **Crawl**（内部 = Map 发现 + Extract 抽取，两段费用叠加，见 §4） |
| 不知道该看哪些网页 | 先找到相关网页再决定 | 先用 **Search**（见 `search.md`），拿到 URL 后再 Extract |

官方原话（Best Practices for Crawl）：Map 更快（只拿 URL），Crawl 更慢但拿完整正文；用 Map 先摸清站点结构、验证路径规则是否符合预期，
再把摸清楚的 `select_paths`/`select_domains` 配置喂给 Crawl，比直接对整站跑一次昂贵的 Crawl 更省成本。

## 2. 和 Firecrawl 的选型边界

如果同一个工作区里还装了 Firecrawl 的 skill，注意概念上的对应关系，**不要把两家的参数名和响应字段混用**：

| 概念 | Tavily | Firecrawl |
| :--- | :--- | :--- |
| 单个已知 URL 抽正文 | `POST /extract`（同时支持批量，一次最多 20 个 URL） | `/scrape`（单 URL；批量抽取有专门的 batch scrape） |
| 整站爬取抽正文 | `POST /crawl`（图状遍历，`instructions` 做语义过滤） | `/crawl`（异步任务，需要轮询 job） |
| 只要 URL 清单 | `POST /map` | `/map` |
| 输出格式 | 默认 markdown，可选纯文本；**没有** 17 种输出格式那么丰富，没有截图、没有结构化 JSON 抽取 schema | 支持 markdown/HTML/JSON 结构化抽取/截图/问答等多种输出格式 |
| 抽取深度控制 | `extract_depth: basic`/`advanced`（advanced 拿表格、嵌入内容，费用翻倍） | 有独立的 stealth/proxy 等反爬策略参数 |
| 计费模型 | 按**成功**抽取的 URL 数量分档收费（失败不收费），Crawl 额外叠加 Map 部分的费用 | 按 credit，具体档位见 Firecrawl 自己的定价页 |

一句话结论：两家做的事高度重叠（都是"给 Agent 提供干净网页内容"），**Tavily 的差异化优势在 Search 和 Research**（Firecrawl 没有对标 `/research` 的深度研究报告能力），
**Firecrawl 的差异化优势在输出格式的丰富度和结构化抽取 schema**（Tavily 的 Extract 没有类似 Firecrawl `json` 格式那种"给 schema 直接产出结构化字段"的能力，
只有 `query` 参数做分块重排序，不做字段级结构化抽取）。同时需要两者的项目里，不要假设同名参数（比如两边都有 `extract_depth`/类似深度概念）语义完全一致。

## 3. Extract

**Endpoint**: `POST /extract`
**用途**: 从一个或多个（最多 20 个）已知 URL 批量抽取干净正文。成功的 URL 进 `results`，失败的进 `failed_results`，两个数组即使在 HTTP 200 时也都要检查。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `urls` | string \| array\<string\> | 是 | — | 1 个字符串或 1–20 个 URL 的数组；超过 20 个/空列表/全部校验失败会返回 400 |
| `query` | string | 否 | — | 提供后按相关性对抽取出的分块重排序 |
| `chunks_per_source` | int | 否 | `3` | 1–5；**仅当 `query` 已设置时生效**（不同于 Search 场景，这里上限是 5 不是 3） |
| `extract_depth` | enum | 否 | `basic` | `basic`/`advanced`；advanced 拿表格、嵌入内容，成功率更高但更慢更贵 |
| `format` | enum | 否 | `markdown` | `markdown`/`text`；text 可能增加延迟 |
| `include_images` | bool | 否 | `false` | 响应里附带页面内抽出的图片 URL 列表 |
| `include_favicon` | bool | 否 | `false` | 每条结果附带 favicon URL |
| `timeout` | float | 否 | `basic` 10s / `advanced` 30s | 1.0–60.0 秒，单个 URL 的抽取超时 |
| `include_usage` | bool | 否 | `false` | 附带 credit 消耗；**成功抽取数未达到 5 次前该值可能显示为 0**（官方 NOTE，因为按每 5 次成功计费一次） |

**示例请求**

```bash
curl -X POST https://api.tavily.com/extract \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TAVILY_API_KEY" \
  -d '{
    "urls": ["https://en.wikipedia.org/wiki/Artificial_intelligence", "https://en.wikipedia.org/wiki/Machine_learning"],
    "extract_depth": "advanced"
  }'
```

```python
import os
from tavily import TavilyClient

client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
response = client.extract(
    urls=[
        "https://en.wikipedia.org/wiki/Artificial_intelligence",
        "https://en.wikipedia.org/wiki/Machine_learning",
    ],
    extract_depth="advanced",
)
for r in response["results"]:
    print(r["url"], len(r["raw_content"]))
for f in response["failed_results"]:
    print("FAILED", f["url"], f["error"])
```

**示例响应**（文档给出的字段形态，未实测）

```json
{
  "results": [
    { "url": "https://en.wikipedia.org/wiki/Artificial_intelligence", "raw_content": "...", "images": [], "favicon": "https://en.wikipedia.org/favicon.ico" }
  ],
  "failed_results": [],
  "response_time": 1.23,
  "request_id": "123e4567-e89b-12d3-a456-426614174111"
}
```

**注意事项**

- **失败的 URL 不收费**，收费只按成功抽取的 URL 数量（每 5 个成功 1 credit basic / 2 credit advanced）。
- **HTTP 200 不代表全部成功**：官方原话 "HTTP 200 can have an empty results array when all valid URLs fail during extraction"。只有当"全部 URL 都没通过格式校验"时才会返回 400
  （`detail.failed_results` 描述每个失败原因）；只要有 URL 格式合法，哪怕实际抓取全失败，也是 200 + 空 `results` + 非空 `failed_results`。
- `results[]` **顺序不保证和入参 `urls[]` 顺序一致**（官方原文强调），按 `url` 字段匹配，不要按下标对齐。
- `chunks_per_source` 只在传了 `query` 时生效——不传 `query` 就传 `chunks_per_source` 不会报错，但不会产生效果（⚠ 文档只说"仅当 query 提供时可用"，
  没说不满足条件时是报错还是静默忽略，按"静默失效"处理最安全）。

## 4. Crawl

**Endpoint**: `POST /crawl`
**用途**: 从一个起始 URL 开始做图状站内遍历，边发现边抽正文。费用 = Map 部分 + Extract 部分两段独立计费（见 §6）。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `url` | string | 是 | — | 起始 URL |
| `instructions` | string | 否 | — | 自然语言指令做语义过滤（如"只找 Python SDK 相关文档页"）；**传了之后 mapping 部分费用从 1 credit/10 页 变成 2 credit/10 页** |
| `chunks_per_source` | int | 否 | `3` | 1–5；仅当 `instructions` 已设置时生效 |
| `max_depth` | int | 否 | `1` | 从起始 URL 算起的最大层级深度；**每加一层，耗时指数级增长**（官方原话），建议从 1 开始逐步增加 |
| `max_breadth` | int | 否 | `20` | 每一层最多跟随的链接数 |
| `limit` | int | 否 | `50` | 总页数硬上限，爬到这个数直接停 |
| `select_paths` / `exclude_paths` | array\<string\> | 否 | — | 正则匹配路径（如 `/docs/.*`） |
| `select_domains` / `exclude_domains` | array\<string\> | 否 | — | 正则匹配域名/子域名 |
| `allow_external` | bool | 否 | `true` | 是否把外部域名的链接也纳入最终结果列表 |
| `extract_depth` | enum | 否 | `basic` | `basic`/`advanced`，同 Extract，独立影响 extraction 部分费用 |
| `format` | enum | 否 | `markdown` | `markdown`/`text` |
| `include_images` | bool | 否 | `false` | — |
| `include_favicon` | bool | 否 | `false` | — |
| `timeout` | float | 否 | `150` | 10–150 秒 |
| `include_usage` | bool | 否 | `false` | 未达到 `/extract`+`/map` 最低计费门槛前可能显示 0 |

**示例请求**

```bash
curl -X POST https://api.tavily.com/crawl \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TAVILY_API_KEY" \
  -d '{
    "url": "docs.tavily.com",
    "max_depth": 2,
    "instructions": "Find all pages about the Python SDK",
    "select_paths": ["/sdk/.*"]
  }'
```

```python
import os
from tavily import TavilyClient

client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
response = client.crawl(
    "docs.tavily.com",
    max_depth=2,
    instructions="Find all pages about the Python SDK",
    select_paths=["/sdk/.*"],
)
print(response["base_url"], len(response["results"]))
```

**示例响应**（文档给出的字段形态，未实测）

```json
{
  "base_url": "docs.tavily.com",
  "results": [
    { "url": "https://docs.tavily.com/sdk/python/quick-start", "raw_content": "...", "favicon": "https://docs.tavily.com/favicon.ico" }
  ],
  "response_time": 9.07,
  "request_id": "123e4567-e89b-12d3-a456-426614174111"
}
```

**注意事项**

- **费用 = Mapping 费用 + Extraction 费用两段独立计费**。官方举例：10 页 basic 抽取 = 1 credit（mapping，10 页 ÷ 10）+ 2 credit（extraction，10 次成功 ÷ 5 × 1）= 3 credit；
  10 页 advanced 抽取 = 1 + 4 = 5 credit。`instructions` 只影响 mapping 那一半的费率，`extract_depth` 只影响 extraction 那一半，两个开关同时开启费用会叠加，不要线性外推。
  ⚠ 假设，待验证：文档没有给出「同时传 `instructions` 又传 `extract_depth=advanced`」的完整费用样例，实测建议先跑一个小规模（`limit` 设低）验证公式。
- **速率限制不随开发/生产 key 升档**：开发和生产 key 都是 100 RPM（不同于 Search/Extract 从 100→1000 RPM），见 `errors-and-limits.md`。
- **HTTP 403** 专属于 Crawl/Map：`Forbidden - URL is not supported`（比如起始 URL 本身不允许被爬取），Extract/Search 没有这个状态码。
- **常见误用**（Best Practices for Crawl 原文列出）：`max_depth` 设到 4 以上（耗时指数增长）；不传 `instructions` 对整站漫爬（浪费资源、上下文爆炸）；
  不设 `limit`（失控爬取，意外超支）；不检查失败结果。
- 建议先用 Map 摸清站点结构、验证路径正则是否命中预期 URL，再把验证过的 `select_paths` 喂给 Crawl。

## 5. Map

**Endpoint**: `POST /map`
**用途**: 从一个起始 URL 出发发现站内所有 URL（像图一样遍历），**不抽正文**，只要 URL 清单，速度比 Crawl 快。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `url` | string | 是 | — | 起始 URL |
| `instructions` | string | 否 | — | 自然语言指令；传了后费用从 1 credit/10 页 变成 2 credit/10 页 |
| `max_depth` / `max_breadth` / `limit` | int | 否 | `1` / `20` / `50` | 语义同 Crawl |
| `select_paths` / `exclude_paths` / `select_domains` / `exclude_domains` | array\<string\> | 否 | — | 正则匹配 |
| `allow_external` | bool | 否 | `true` | — |
| `timeout` | float | 否 | `150` | 10–150 秒 |
| `include_usage` | bool | 否 | `false` | 未达到最低计费门槛（10 次成功页）前可能显示 0 |

**示例请求**

```bash
curl -X POST https://api.tavily.com/map \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TAVILY_API_KEY" \
  -d '{"url": "docs.tavily.com", "select_paths": ["/api-reference/.*"], "max_depth": 2}'
```

```python
import os
from tavily import TavilyClient

client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
response = client.map("docs.tavily.com", select_paths=["/api-reference/.*"], max_depth=2)
print(response["results"])
```

**示例响应**（文档给出的字段形态，未实测）

```json
{
  "base_url": "docs.tavily.com",
  "results": ["https://docs.tavily.com/api-reference/introduction", "https://docs.tavily.com/api-reference/endpoint/search"],
  "response_time": 8.43,
  "request_id": "123e4567-e89b-12d3-a456-426614174111"
}
```

**注意事项**

- Map 没有 `extract_depth`/`format`/`include_images`/`include_favicon` 这些和正文相关的参数（它根本不抽正文），照抄 Crawl 的参数列表会传出无效字段。
- 官方 Python SDK Reference 里 Map 相关的一处示例代码调用了 `tavily_client.mapping(...)`，但同页正文明确说"通过 `map` 函数访问"——**以 SDK Reference 正文和参数表为准，
  方法名是 `map`**，`mapping` 疑似历史遗留或文档渲染残留的写法，⚠ 文档自相矛盾，实测导入 `tavily` 包后用 `dir(TavilyClient)` 确认一次更保险。
- 和 Crawl 一样走 `POST /crawl` 同级的速率限制家族（⚠ 文档未明确说 Map 是否共享 Crawl 的 100 RPM 固定限速还是走默认限速，`rate-limits` 页只单独列了 Crawl 一项，
  待验证，见 `verification-plan.md`）。

## 6. 注意事项

- Extract/Crawl/Map 三者都是 `bearerAuth`（普通 API Key），不像 `org-usage` 需要特殊的 owner key。
- 三者都不支持 keyless 访问（只有 Search、Extract 的**部分场景**——不对，实际上 keyless 页面明确写的是"仅 `/search`、`/extract` 支持 keyless"，Crawl/Map/Research 都需要正式 Key）。
- 三者的 `include_usage=true` 都有"未达到最低计费门槛时可能显示 0"的提示，不要把 0 误判为"这次调用免费"，等累计到位后usage 数字会补上来（⚠ 文档原文，未实测，实测建议连续调用几次观察 usage 变化）。
