# Map & Search — URL 发现与网络搜索

覆盖两个「不用爬全站也能拿到 URL / 内容」的端点：

- `POST /v2/map` — 给一个 URL，快速列出这个站点上的链接，**不抓正文**。
- `POST /v2/search` — 搜网络（web / images / news），可选顺带抓每条结果的正文。

Base URL：`https://api.firecrawl.dev/v2`。认证统一用
`Authorization: Bearer $FIRECRAWL_API_KEY`（从环境变量读取，不要硬编码进代码或示例里）。

两者都不是 `/crawl`：`/crawl` 是递归遍历一个已知站点、把每个页面都抓下来的异步任务（见
`references/crawl.md`）；`/map` 只列 URL 不抓正文，`/search` 是面向整个互联网的搜索引擎查询，
不是针对某一个已知站点的遍历。三者经常被一个 Agent 搞混，尤其是"map 一个网站"和"crawl 一个网站"
听起来几乎是同一件事。

## 先读这两条：已验证的反直觉行为

在写任何调用代码之前，务必先知道这两点——都是这次会话里对生产环境的真实调用验证过的，不是从文档
转录的：

### 1. `map` 给一个具体页面 URL，不会返回整站——即使文档标题写的是"map a website"

已用真实 API 验证（2026-09-21）：对 `https://skillify.carbonleft.com`（一个具体路径/子域名，不是
"给个域名根路径"意义上的整站入口）调用 `/v2/map`，返回：

```json
{
  "success": true,
  "id": "...",
  "links": [
    { "url": "https://skillify.carbonleft.com", "title": "skillify-runtime" }
  ],
  "warning": "Only 1 result(s) found. For broader coverage, try mapping the base domain: carbonleft.com"
}
```

只有 1 个链接。`success` 依然是 `true`——这不是一次失败的请求，`warning` 字段才是真正带着
可执行信息的地方："如果你想要更全的覆盖，去 map 根域名 `carbonleft.com`，而不是这个子域名/路径"。
一个只读过"map 一个网站，拿到网站上所有的 URL"这句宣传语的 Agent，几乎必然会假设不管传进去的是
根域名还是某个深层路径，返回的都是"整个网站"的链接——这是错的。**要拿到全站链接，把 `url` 设成
根域名（如 `https://example.com`），而不是网站里的某个具体页面。**

### 2. `search` 默认会抓每条结果的正文，不只是标题/摘要——比大多数"search API"重得多

已用真实 API 验证（2026-09-21）：`{"query":"firecrawl web scraping api","limit":2}`（没有传
`scrapeOptions`）→ 每条结果的 `description` 字段里出现的是完整的、像 markdown 一样带段落/代码块的
抓取内容，不是一两句话的摘要。这与 OpenAPI schema 里 `scrapeOptions.formats` 的默认值
`['markdown']` 一致——也就是说 `scrapeOptions` 本身默认就是 `{}`，但它的 `formats` 子字段默认值
已经是 `['markdown']`，所以哪怕请求体完全不带 `scrapeOptions`，search 也会去抓正文。

⚠ 文档与实测有一处对不上号，如实记录：`features_search.md` 的 Basic Usage 示例展示的响应只有
`title` / `description` / `url` / `position`，看起来像"默认不抓正文的轻量摘要"；同一份文档又说
"Search results include query-relevant Highlights by default"（`highlights` 参数默认 `true`），
即默认返回的 `description` 本身就可能是从正文里挑出来的、和查询相关的高亮片段，而不是引擎原生
snippet。真实调用观察到的"`description` 里是大段类 markdown 内容"，究竟是 `scrapeOptions.formats`
默认抓取的结果，还是 `highlights` 默认生效的结果，OpenAPI 摘要和该文档页都没有把两者的因果关系
讲清楚——⚠ 文档未说明。对使用者来说结论是一样的：**不要假设 `/search` 默认返回的是轻量摘要**，
不管哪个参数导致的，它默认比"搜索"这个词暗示的要重、要贵。想要传统意义上的"标题+短摘要"，把
`highlights` 设为 `false`（拿 provider 原始 snippet），并按下面"注意事项"里说的方式控制
`scrapeOptions.formats` 来避免整页抓取——但**关闭抓取的具体写法本次没有实测过**，见下方标注。

---

## 发现一个网站上有哪些页面（Map）

### URL 映射

**Endpoint**: `POST /v2/map`

**用途**: 给一个 URL，快速返回这个站点上能发现的链接列表（不抓正文，不返回页面内容）。适合：
先列出一个站点有哪些页面、再决定抓哪些；只需要知道某个主题相关的页面在哪里（配合 `search`
子参数）；不需要整站内容只需要 URL 清单。它比 `/crawl` 快得多，但也粗糙得多——`/crawl` 通过
递归跟踪站内链接来发现页面并逐个抓取，有完整的执行/错误记录；`/map` 主要靠站点的 sitemap，
辅以搜索引擎结果和历史抓取缓存来"快速拼出一份链接清单"，可能漏掉 sitemap 里没有的页面。需要
"更彻底、更新鲜"的发现结果时用 `/crawl`；只需要某一个具体页面自身包含的链接时，用
`/scrape` 的 `links` format（见 `references/scrape.md`），不要为此单独调用 `/map`。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `url` | string(uri) | 是 | — | 起始 URL。已用真实 API 验证：传一个具体路径/子域名只会返回该路径下找到的链接，不是整站；想要全站结果，传根域名。 |
| `search` | string | 否 | — | 按相关性搜索/过滤站内 URL 的关键词，例如 `"docs"` 只返回与该词相关的 URL，按相关性从高到低排序。 |
| `sitemap` | string，枚举 `skip` / `include` / `only` | 否 | `include` | 控制 sitemap 在发现 URL 中的作用：`skip` 完全不用 sitemap；`only` 只返回 sitemap 里出现过的 URL；默认 `include` 是 sitemap 和其它发现方式（缓存的抓取记录、SERP 结果）一起用。 |
| `includeSubdomains` | boolean | 否 | `true` | 是否把子域名下的链接也算进去。 |
| `ignoreQueryParameters` | boolean | 否 | `true` | 是否排除带 query string 的 URL（同一页面的不同参数变体默认会被去重掉）。 |
| `ignoreCache` | boolean | 否 | `false` | sitemap 数据默认最长缓存 7 天；设为 `true` 绕过缓存拿最新数据。 |
| `limit` | integer | 否 | `5000` | 最多返回多少条链接。 |
| `timeout` | integer | 否 | 无默认（不设超时） | 毫秒。 |
| `location.country` / `location.languages` | string / array\<string\> | 否 | country 默认 `'US'` | 模拟地理位置对应的代理、语言、时区，语义同 `/scrape` 的 `location`。 |

此外还有企业版才用得到的 `threatProtection`（URL 威胁扫描覆盖组织策略，需要团队开通 Threat
Protection，否则请求会被 403 拒绝）和 `auditMetadata.username`（SIEM 审计日志用的用户归属字段）
两个对象参数，普通调用不需要传，这里不展开。

**示例请求**

```bash
# 最常见用法：map 根域名，拿全站链接
curl -X POST "https://api.firecrawl.dev/v2/map" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://firecrawl.dev"
  }'

# 带 search 子参数：只要和 "docs" 相关的 URL，按相关性排序
curl -X POST "https://api.firecrawl.dev/v2/map" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://firecrawl.dev",
    "search": "docs",
    "limit": 50
  }'
```

```python
import os
import requests

FIRECRAWL_API_KEY = os.environ["FIRECRAWL_API_KEY"]

resp = requests.post(
    "https://api.firecrawl.dev/v2/map",
    headers={
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    },
    json={
        "url": "https://firecrawl.dev",   # 想要全站结果就传根域名，不要传具体页面路径
        "sitemap": "include",
        "limit": 100,
    },
    timeout=60,
)
resp.raise_for_status()
data = resp.json()
for link in data["links"]:
    print(link["url"], link.get("title"))
if data.get("warning"):
    print("WARNING:", data["warning"])   # 覆盖不足等可操作信号会出现在这里，success 依旧是 true
```

**示例响应**

已用真实 API 验证（2026-09-21）——对一个具体子域名路径调用的真实响应（见上文"反直觉行为 1"）：

```json
{
  "success": true,
  "id": "...",
  "links": [
    { "url": "https://skillify.carbonleft.com", "title": "skillify-runtime" }
  ],
  "warning": "Only 1 result(s) found. For broader coverage, try mapping the base domain: carbonleft.com"
}
```

文档转录，未实测（对根域名 map 成功、覆盖较广时的典型响应形状，来自 `features_map.md`）：

```json
{
  "success": true,
  "links": [
    {
      "url": "https://docs.firecrawl.dev/features/scrape",
      "title": "Scrape | Firecrawl",
      "description": "Turn any url into clean data"
    },
    {
      "url": "https://www.firecrawl.dev/blog/5_easy_ways_to_access_glm_4_5",
      "title": "5 Easy Ways to Access GLM-4.5",
      "description": "Discover how to access GLM-4.5 models locally, ..."
    }
  ]
}
```

`title` / `description` 是否存在取决于目标网站本身有没有这些元数据，不保证每条都有——文档原文
明确写了"Title and description are not always present"。

**注意事项**

- ⚠ 已验证：`url` 传具体页面路径（含子域名）≠ 传根域名，前者只返回该路径下的链接。想要"整站
  URL"，必须传根域名。
- 文档原文：每次 `/map` 调用固定 **1 credit**，与 `limit` 无关——`limit=100000` 也只算 1 credit
  （未在本次会话中实测计费，来自 `features_map.md` 的 `<Info>` 说明）。
- `search` 子参数不是过滤开关，是排序依据：返回的仍可能是站内多数 URL，只是按相关性重新排序，
  不要假设它会把不相关的 URL 完全剔除干净。
- `sitemap: "only"` 会让结果强依赖目标站点 sitemap 是否完整；很多站点的 sitemap 本身就不全，
  这种情况下即使传根域名也可能覆盖不足，此时该看 `warning` 字段还是考虑改用 `/crawl`。
- `ignoreQueryParameters` 默认 `true`，如果目标站点用 query string 做实际路由（不是简单的
  tracking 参数），可能会把这些页面直接去重掉，需要显式设为 `false`。
- 不要为了拿"某一个页面上的链接"去调用 `/map`——那是 `/scrape` 的 `links` format 的工作，
  见 `references/scrape.md`。

---

## 搜索网络并可选读取结果全文（Search）

### 网络 / 图片 / 新闻搜索

**Endpoint**: `POST /v2/search`

**用途**: 对公开网络做一次搜索引擎查询，返回网页 / 图片 / 新闻结果，并且可以在同一次调用里顺带
抓取每条结果的正文（通过 `scrapeOptions`）。它和 `/map`、`/crawl` 的区别是：后两者都作用于一个
你已经知道的站点（给定 `url`），`/search` 作用于整个互联网，输入是一个查询词而不是 URL。当你
已经知道目标站点、只是想要它的页面列表时用 `/map`；当你不知道该去哪个网站找答案、需要先从网上
搜出候选页面时才用 `/search`。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string | 是 | — | 搜索词。 |
| `limit` | integer | 否 | `10` | 最多返回结果数；**同时指定多个 `sources` 时，`limit` 是"每种 source 各自"的上限**——`limit:5` + `sources:["web","news"]` 会返回最多 5 条 web、最多 5 条 news（合计最多 10 条），不是总数 5 条。 |
| `sources` | array\<object\> | 否 | `['web']` | 搜索哪些来源：`web`（标准网页结果）、`images`（图片搜索）、`news`（新闻）。可以同时传多个。 |
| `categories` | array\<object\> | 否 | `[]`（不按类别过滤） | 按类别过滤：`developer`（开发者文档/issue/PR/README，走 Developer Index）、`research`（学术/研究站点，2026-11-16 起语义会变，见下）、`pdf`（PDF 文件）。`developer` 不能和其它 category 混用。 |
| `includeDomains` / `excludeDomains` | array\<string(hostname)\> | 否 | — | 限定或排除特定域名，只传裸域名（不带协议/路径）；**两者互斥**，一次请求只能用其中一个。 |
| `tbs` | string | 否 | — | 时间过滤：`qdr:h/d/w/m/y`（过去 N 小时/天/周/月/年）、`cdr:1,cd_min:MM/DD/YYYY,cd_max:MM/DD/YYYY`（自定义日期范围）、`sbd:1`（按日期排序），可以组合，如 `sbd:1,qdr:w`。**只对 `web` 结果生效，不影响 `news` / `images`**。 |
| `location` / `country` | string | 否 | country 默认 `'US'` | 搜索结果的地理定位；两者最好一起传。 |
| `safe` | boolean | 否 | 不过滤 | 传 `true` 开启 SafeSearch，过滤露骨内容。 |
| `highlights` | boolean | 否 | `true` | 默认生成与查询相关的高亮片段填进结果；设为 `false` 改为拿 provider 原始的 description/snippet。 |
| `ignoreInvalidURLs` | boolean | 否 | `false` | 排除掉那些拿去调用其它 Firecrawl 端点会报错的 URL，便于直接把结果管道式传给 `/scrape` 等。 |
| `enterprise` | array\<string\> | 否 | — | Zero Data Retention 选项：`["zdr"]`（端到端 ZDR，10 credits/10 条结果）或 `["anon"]`（匿名化 ZDR，2 credits/10 条结果），仅企业版开通后可用。 |
| `scrapeOptions` | object | 否 | `{}`（其内部 `formats` 默认 `['markdown']`） | 是否/如何抓取每条结果的正文。`formats` 数组和 `/scrape` 用的是同一套 format 定义（`markdown` / `html` / `links` / `screenshot` / `json` 等）——完整字段表见 `references/scrape.md` 的 formats 表，这里不重复；同一份 `formats` 数组原样塞进 `scrapeOptions.formats` 即可。 |
| `timeout` | integer | 否 | `60000` | 毫秒。 |

**示例请求**

```bash
# 基本网页搜索
curl -s -X POST "https://api.firecrawl.dev/v2/search" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "firecrawl web scraping",
    "limit": 5
  }'

# 多 source + 类别过滤 + 域名限定 + 时间过滤
curl -X POST "https://api.firecrawl.dev/v2/search" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "vector database benchmark",
    "sources": ["web", "news"],
    "categories": ["research"],
    "includeDomains": ["arxiv.org"],
    "tbs": "qdr:m",
    "limit": 5
  }'

# 搜索 + 顺带抓每条结果的 markdown 正文和站内链接
curl -X POST "https://api.firecrawl.dev/v2/search" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "firecrawl web scraping",
    "limit": 3,
    "scrapeOptions": { "formats": ["markdown", "links"] }
  }'
```

```python
import os
import requests

FIRECRAWL_API_KEY = os.environ["FIRECRAWL_API_KEY"]

resp = requests.post(
    "https://api.firecrawl.dev/v2/search",
    headers={
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    },
    json={
        "query": "firecrawl web scraping",
        "limit": 5,
        "sources": ["web"],
        # 不想要每条结果都抓全文时显式控制 scrapeOptions.formats（见下方注意事项，
        # 具体"如何拿到最轻量结果"的写法本次未实测，先按 formats: [] 尝试并核对返回体）
        "scrapeOptions": {"formats": []},
    },
    timeout=60,
)
resp.raise_for_status()
data = resp.json()
for item in data["data"].get("web", []):
    print(item["url"], item.get("title"))
```

**示例响应**

已用真实 API 验证（2026-09-21）——`{"query":"firecrawl web scraping api","limit":2}`（未传
`scrapeOptions`）时，返回结构与文档一致（`data.web[]` 数组），但每条结果的 `description` 字段
里是大段类 markdown 内容，不是短摘要（见上文"反直觉行为 2"，具体字段级 JSON 未在验证记录里
逐字保存，行为以文字记录为准）。

文档转录，未逐字段实测（基本搜索、多 source 的响应形状，来自 `features_search.md`）：

```json
{
  "success": true,
  "data": {
    "web": [
      {
        "url": "https://www.firecrawl.dev/",
        "title": "Firecrawl - The Web Data API for AI",
        "description": "The web crawling, scraping, and search API for AI...",
        "position": 1
      }
    ],
    "images": [
      {
        "title": "Quickstart | Firecrawl",
        "imageUrl": "https://mintlify.s3.us-west-1.amazonaws.com/firecrawl/logo/logo.png",
        "imageWidth": 5814,
        "imageHeight": 1200,
        "url": "https://docs.firecrawl.dev/",
        "position": 1
      }
    ],
    "news": [
      {
        "title": "Y Combinator startup Firecrawl is ready to pay $1M to hire three AI agents as employees",
        "url": "https://techcrunch.com/...",
        "snippet": "It's now placed three new ads on YC's job board...",
        "date": "3 months ago",
        "position": 1
      }
    ]
  }
}
```

文档转录，未实测（带 `scrapeOptions` 抓取正文后的响应形状，来自同一文档页——注意这里正文出现在
`markdown` 字段，而不是上面真实验证里观察到的 `description` 字段，两者的关系文档没有讲清楚，
见上文"反直觉行为 2"里的 ⚠ 记录）：

```json
{
  "success": true,
  "data": [
    {
      "title": "Firecrawl - The Ultimate Web Scraping API",
      "description": "Firecrawl is a powerful web scraping API...",
      "url": "https://firecrawl.dev/",
      "markdown": "# Firecrawl\n\nThe Ultimate Web Scraping API\n\n...",
      "links": ["https://firecrawl.dev/pricing", "https://firecrawl.dev/docs"],
      "metadata": {
        "title": "Firecrawl - The Ultimate Web Scraping API",
        "sourceURL": "https://firecrawl.dev/",
        "statusCode": 200
      }
    }
  ]
}
```

OpenAPI 规范转录，未实测（响应 schema 里还定义了 `warning`、`id`、`creditsUsed` 三个顶层字段——
`warning` 用于返回搜索过程中出现的问题提示，`id` 是这次搜索任务的 id，可用于之后调用
`POST /v2/search/{jobId}/feedback` 提交反馈；`data.web[]` 每条结果还可以带 `html` / `rawHtml` /
`screenshot` / `audio` / `video` / `metadata` 等字段，取决于 `scrapeOptions.formats` 里请求了
什么，完整字段定义见 `references/scrape.md`）。

**注意事项**

- ⚠ 文档/规范转录，未实测：想要"更轻"的结果（不抓正文），OpenAPI schema 里确实有
  `scrapeOptions.formats` 这个字段可以设置——理论上传 `scrapeOptions: {"formats": []}` 或者干脆
  不请求任何内容型 format，就能避免整页抓取；但这条路径本次会话**没有实测过**，实际返回体是否
  真的变轻、`description`/`highlights` 是否仍然携带大段内容，都还没验证，不要当作已确认行为
  直接写进生产代码，先跑一次真实调用核对返回体。
- 成本模型（文档转录）：基础搜索本身 2 credits / 10 条结果，向上取整（1–10 条 = 2 credits，
  11–20 条 = 4 credits，以此类推）；开启 `scrapeOptions` 后，每条结果还要按标准抓取计费叠加——
  普通抓取 1 credit/页，PDF 解析 1 credit/页，JSON format 额外 +4 credits/页。想控成本：显式设
  `scrapeOptions.parsers: []`（不需要 PDF 解析时）、调低 `limit`、以及上面提到的"关闭内容型
  format"（未实测）。
- `includeDomains` 和 `excludeDomains` **互斥**，同一次请求只能传一个，两个都传会怎样文档没有
  明确说明（⚠ 文档未说明），不要同时传。
- `tbs` 只对 `sources: ["web"]` 的结果生效，对 `news` / `images` 无效——想按时间过滤新闻，
  文档建议改用 `web` source 配合 `site:` 操作符定向到新闻域名。
- `categories: ["research"]` 在 **2026-11-16 会发生破坏性变更**：目前是把 web 搜索限定在约 14
  个学术站点（arxiv.org、nature.com、pubmed 等），返回的还是 `data.web[]` 里的网页记录；变更后
  会改为搜索 Research Index，结果搬到 `data.research[]`，字段也变成论文记录
  （`paperId`/`title`/`abstract`/`score` 等）。在这之前，响应里会带一个 `warnings` 提示。如果
  只是想要"网页结果但限定在学术站点"，应该用 `includeDomains` 而不是 `categories: ["research"]`，
  避免这次变更影响到已有代码。
- `categories: ["developer"]` 不能和其它 category 混用；返回的结果仍在标准 `web` 分组里，每条
  会带一个 `category: "developer"` 字段做标记。
- 想要"先筛选/排序候选结果，再决定抓哪几条"时，用两步法：先不带 `scrapeOptions` 调 `/search`
  拿候选 URL 列表，筛完之后对选中的 URL 分别调用 `/scrape`（见 `references/scrape.md`），
  而不是一次性对所有搜索结果都开 `scrapeOptions`——尤其在 `limit` 较大时，一次性全量抓取会
  产生大量不必要的抓取费用。
- 如果对某次搜索结果的质量不满意或想反馈缺失内容，有独立的
  `POST /v2/search/{jobId}/feedback` 端点（`jobId` 就是本次响应里的 `id`），首次反馈有机会
  退还 1 credit；本文件不展开这个端点的完整参数，只标注其存在，用法见 API Reference。
- Zero Data Retention（`enterprise: ["zdr"]` / `["anon"]`）只覆盖 `/search` 本身；如果同时用
  `scrapeOptions` 抓正文，`enterprise` 参数会自动对抓取部分也生效 ZDR，不需要额外在
  `scrapeOptions` 里单独声明——这和 `/scrape` 自己的 `zeroDataRetention` 选项是两回事，别混淆
  （文档转录，未实测）。
