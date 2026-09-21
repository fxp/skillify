---
name: firecrawl
description: 接入 Firecrawl（docs.firecrawl.dev，域名 api.firecrawl.dev）的网页抓取/爬取/搜索 API 使用手册——涵盖单页抓取（含 markdown/HTML/JSON 结构化抽取/截图/问答等 17 种输出格式）、批量抓取、整站递归爬取（crawl）、URL 发现（map）、网页搜索（search）、结构化数据抽取的三种方案怎么选、鉴权、错误码、限流与 credits 计费。当用户提到"Firecrawl""firecrawl.dev""api.firecrawl.dev""firecrawl-py""@mendable/firecrawl-js""FirecrawlApp""网页抓取 API""爬虫 API""把网页转成 markdown""抓某个网站所有链接/页面""网页转结构化 JSON"，或要写代码调用上述任意能力时，应主动使用本技能，不要凭记忆编造字段名、误用其他抓取平台的接口习惯，尤其不要在结构化抽取时漏传 schema、或调用已经废弃的 /extract 端点却不知道它废弃了。
---

# Firecrawl 接入指南

Firecrawl（docs.firecrawl.dev）是面向 AI Agent 的网页数据 API："把网页变成干净的数据"——单页抓取、整站爬取、URL 发现、网页搜索、结构化抽取，统一走 `api.firecrawl.dev`。本 skill 覆盖当前文档站主推的 **v2** API 里最常用的 6 类核心能力，目标是第一次调用就跑通，不踩已知的两个"静默失败/悄悄废弃"的坑。

## ⚠ 验证状态

内容整理自 https://docs.firecrawl.dev（v2 文档，抓取于 2026-09-21）+ 官方 OpenAPI 规范（`v2-openapi.json`）。**用一把真实 key 对核心端点做了实测**：`/scrape`（成功、401、403 无 key、400 无效 URL、JSON 格式的静默失败）、`/map`、`/search`、`/crawl`（提交 + 轮询状态）、`/extract`（发现已废弃）——细节和原始响应见各 reference 文件里标了"已用真实 API 验证（2026-09-21）"的地方，以及 `firecrawl-workspace/verification-log.md`。**未验证**：`/agent`、`/interact`（浏览器沙箱交互）、`/monitor`（定时监控）、`/parse`（文档解析 PDF/Word 等）、`actions`（scrape 内的浏览器交互序列）、webhook 的实际投递与签名校验——这些要么标了"文档原文，未实测"，要么直接列在"本 skill 不覆盖"里。

## 用之前先确认 3 件事

1. **Base URL 固定为 `https://api.firecrawl.dev/v2`。** 文档站还留着 v1（`https://api.firecrawl.dev/v1`），实测目前仍然能响应，但当前文档只讲 v2，v2 独有 batch/scrape、map、7 种以上 v1 没有的输出格式——不要因为 v1 没报废就选它，本 skill 全篇按 v2 写（见 `references/errors-and-limits.md`）。
2. **鉴权**：`Authorization: Bearer <FIRECRAWL_API_KEY>`，key 形如 `fc-...`。不带 key 是 **403**，带错 key 是 **401**——两种不同状态码，处理逻辑不要合并。
3. **结构化数据抽取选错路最容易踩坑**：想从页面拿 JSON，直接用 `POST /scrape` 的 `formats: [{"type":"json","schema":{...}}]`，**必须带 `schema`**——传裸字符串 `"json"`（不带 schema）会返回 `success:true` 但 `data.json` 是 `null`，只有一个容易被忽略的 `data.warning` 字段说抽取失败了，而且照样扣 5 credits。独立的 `POST /extract` 端点已经**被官方在运行时标记为废弃**（`warnings` 字段明说"用 /scrape 代替"），但文档页面自己又说该迁移到 `/agent`——两个说法互相矛盾，本 skill 一律建议走 `/scrape` 的 JSON 格式。完整细节见 `references/structured-extraction.md`。

## 30 秒跑通第一个请求

```bash
curl https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```
```python
import os, requests
r = requests.post(
    "https://api.firecrawl.dev/v2/scrape",
    headers={"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"},
    json={"url": "https://example.com"},
)
print(r.json()["data"]["markdown"])
```
成功返回 `{"success": true, "data": {"markdown": "...", "metadata": {...}}}`，1 credit（已实测）。

## 能力域导航

| 我想做什么 | 读 | 核心 endpoint |
| :--- | :--- | :--- |
| 抓一个已知 URL 的干净内容（markdown/HTML/截图/问答/媒体提取…） | [`scrape.md`](references/scrape.md) | `POST /scrape` |
| 从一个已知 URL 里拿结构化 JSON——该用哪个方案、别踩废弃端点的坑 | [`structured-extraction.md`](references/structured-extraction.md) | `POST /scrape`（JSON 格式，推荐）、`POST /extract`（已废弃但能用） |
| 抓一批已知 URL，或从一个种子 URL 开始递归爬全站 | [`crawl-and-batch.md`](references/crawl-and-batch.md) | `POST /batch/scrape`、`POST /crawl` + `GET /crawl/{id}` |
| 先看一个站有哪些 URL（不抓内容），或者搜网页/图片/新闻 | [`map-and-search.md`](references/map-and-search.md) | `POST /map`、`POST /search` |
| 查报错原因、判断要不要重试、查限流和 credits 消耗 | [`errors-and-limits.md`](references/errors-and-limits.md) | 错误码表、`GET /team/credit-usage`、`GET /team/queue-status` |

## 跨领域的通用规则（写代码前必读）

1. **`success: true` 不等于"拿到了你要的东西"。** REST 层面的成功和业务层面的成功是两回事：JSON 抽取失败时 `success` 依然是 `true`，真实失败信号在 `data.json === null` + `data.warning` 里；`/extract` 已废弃时也是 `success: true`，废弃信号只在 `warnings` 数组里。检查响应不能只看 `success` 字段，具体到每个端点要看它自己的完成信号（见 `scrape.md` / `structured-extraction.md`）。
2. **`map`/`crawl`/`search` 都叫"网页发现/爬取"类接口，但语义完全不同，容易混用：** `map` 只列 URL、不抓内容，且只覆盖你给的那个具体路径（不会自动扩展到整个域名——实测过，`⚠` 见 `map-and-search.md`）；`crawl` 从一个种子 URL 出发递归发现并抓取，是**异步任务**，`POST /crawl` 只返回一个 job id，不返回任何页面内容，必须轮询 `GET /crawl/{id}` 拿结果；`search` 是搜索引擎查询，**默认会把每条结果也抓一遍内容**（不是只给标题摘要），比一般搜索 API 返回的数据量大得多、也更贵。
3. **`crawl` 和 `batch/scrape` 都是异步任务，模式一样：** 提交拿 job id → 轮询状态直到 terminal state（或配置 webhook 回调）→ 结果就在状态响应自己的 `data` 字段里，超出一页有 `next` 分页游标——不是"提交后立刻拿到内容"，也不是"另有一个单独的结果查询接口"。
4. **结构化抽取有三条路（`/scrape` JSON 格式、已废弃的 `/extract`、未覆盖的 `/agent`），选错的代价是要么白花 4 倍 credits，要么走一个随时可能被彻底下线的废弃端点。** 默认用 `/scrape` 的 JSON 格式；不知道目标 URL、需要自主发现的场景才轮到 `/agent`（本 skill 不覆盖，未实测）。
5. **Credits 计费按"Firecrawl 有没有返回一份 document"算，不按目标站返回的 HTTP 状态码算。** 目标站 403/404，只要 Firecrawl 把这个响应抓回来了照样计费；JSON 格式即使抽取失败（见第 1 条）也照样扣 5 credits（已实测）。`crawl`/`search`/带 JSON 格式的调用，credits 是叠加计费的，不是固定 1 credit。

## 本 skill 不覆盖

`/agent`（自主网页研究 agent，`/extract` 的官方推荐继任者之一，未验证，成本模型独立）、`/interact` 和 `/scrape/{jobId}/interact`（浏览器沙箱交互会话）、`/monitor`（定时监控/变更检测调度）、`/parse`（PDF/Word/Excel 等文档解析）、`/search/research/*` 与 `/search/developer`（垂直搜索索引）、`actions`（scrape 请求里的浏览器点击/滚动/等待交互序列，只在 `advanced-scraping-guide.md` 里读到过，没有真实调用验证）、webhook 的实际投递和签名校验（只读了文档，没有搭接收端验证）、team 用量与限额管理类接口（`/team/*` 除 `credit-usage`/`queue-status` 外）、Enterprise 专属功能（IP 限制、key 限制、威胁防护、SIEM 审计日志）。这些的入口都在 `docs.firecrawl.dev` 左侧导航，需要时按同样的方法论（先读 OpenAPI 摘要，再拿真实 key 验证）单独补。

## House rules

- Key 只走环境变量 `FIRECRAWL_API_KEY`，不要硬编码，不要打进日志。
- 判断请求是否真正成功，按端点各自的完成信号判断（见"通用规则"第 1 条），不要只看 `success` 或 HTTP 2xx。
- `crawl`/`batch scrape`/`extract` 都是异步任务，写代码前先决定轮询间隔还是配 webhook，不要假设第一次响应就有数据。
- 大规模调用前先查 `GET /team/credit-usage` 心里有数，JSON 格式、`question`/`highlights`/`audio`/`video` 等格式、PII 脱敏都是在基础 1 credit 上再加钱，crawl/search 内部按页/按条同样加钱。

## 目录结构

```
firecrawl/
├── SKILL.md
├── references/
│   ├── scrape.md                 # 单页抓取：markdown/HTML/截图/JSON/问答/媒体等 17 种格式
│   ├── structured-extraction.md  # 三种结构化抽取方案怎么选，/extract 废弃详情
│   ├── crawl-and-batch.md        # 批量抓取 + 整站递归爬取，异步任务模式
│   ├── map-and-search.md         # URL 发现 + 网页搜索
│   └── errors-and-limits.md      # 鉴权、错误码、限流、credits 计费
└── evals/
    └── evals.json                # 对照实验场景（打包时自动排除）
```

内容整理自 https://docs.firecrawl.dev（抓取于 2026-09-21），实际调用报错优先信任真实 API 返回，不信任文档转录。
