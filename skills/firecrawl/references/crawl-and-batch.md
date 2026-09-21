# Crawl 与 Batch Scrape：多页抓取

本文覆盖 Firecrawl v2 的两种"多页"抓取方式：`crawl`（从一个起始 URL 递归发现并抓取整个站点）与
`batch/scrape`（对一份固定 URL 列表并发抓取）。两者都是**异步任务**：`POST` 请求立即返回一个
任务 id，页面内容要靠后续轮询或 webhook 才能拿到。单页同步抓取见 `scrape.md`，`scrapeOptions`/
`formats` 的字段在本文直接复用，不重复展开每个格式的细节。

Base URL：`https://api.firecrawl.dev/v2`。认证：`Authorization: Bearer <FIRECRAWL_API_KEY>`
（环境变量 `FIRECRAWL_API_KEY`，示例代码中不要硬编码 key）。

## ⚠ 本文最重要的一件事：这两个 POST 端点不会直接返回页面内容

`POST /v2/crawl` 和 `POST /v2/batch/scrape` 的响应里**没有 `data` 字段**，只有任务 id 和一个
状态查询 URL。这与单页 `POST /v2/scrape` 的同步返回模式完全不同——按"scrape 的经验"去猜，几乎
必然会以为响应里已经有内容。实际流程是：

1. 发起任务 → 拿到 `id`；
2. 轮询 `GET /v2/crawl/{id}`（或 `GET /v2/batch/scrape/{id}`）直到 `status` 到达终止状态；
3. 页面内容嵌在**这个轮询响应本身**的 `data` 数组里，没有独立的"结果"端点；
4. 单次响应超过 10MB 或任务未完成时会带一个 `next` URL（`?skip=N` 分页游标），继续请求 `next`
   才能拿到剩余数据；
5. 或者完全不轮询，改用 `webhook` 参数让 Firecrawl 主动推送（见"获取通知，不用轮询"一节）。

**已用真实 API 验证（2026-09-21）**：

```
POST /v2/crawl {"url":"https://skillify.carbonleft.com","limit":2}
→ {"success":true,"id":"01a0bf91-...","url":"https://api.firecrawl.dev/v2/crawl/01a0bf91-..."}
```

无任何页面内容，只有 `success`/`id`/`url`。约 3 秒后轮询：

```
GET /v2/crawl/01a0bf91-...
→ {"success":true,"status":"scraping","completed":2,"total":2,"creditsUsed":2,
   "expiresAt":"...","next":"https://api.firecrawl.dev/v2/crawl/01a0bf91-...?skip=2",
   "data":[{...已抓取页面...}]}
```

内容出现在 `data` 里，`next` 带上 `?skip=2` 分页游标。`completed`/`total`/`creditsUsed` 计数
机制已实测确认生效；本次只观察到中间态 `status:"scraping"`，`completed`/`failed`/`cancelled`
等终止态字面值来自文档转录，未在本次验证中触发观察到。

## 目录

- [爬取一整个网站](#爬取一整个网站从一个-url-开始)：`POST /v2/crawl`、`GET/DELETE /v2/crawl/{id}`
- [查看 crawl 失败页面](#查看-crawl-失败了哪些页面)：`GET /v2/crawl/{id}/errors`
- [抓取固定 URL 列表](#抓取一份已知的固定-url-列表)：`POST /v2/batch/scrape`、`GET/DELETE /v2/batch/scrape/{id}`
- [查看 batch 失败 URL](#查看-batch-scrape-失败了哪些-url)：`GET /v2/batch/scrape/{id}/errors`
- [预览 crawl 参数](#在真正跑-crawl-之前预览它会抓到什么)：`POST /v2/crawl/params-preview`
- [查看在跑任务](#查看当前有哪些-crawl-在跑)：`GET /v2/crawl/active`
- [webhook：不轮询也能拿到通知](#获取通知不用轮询webhook)
- [Credits 与已验证事实小结](#credits-与已验证事实小结)

---

## 爬取一整个网站，从一个 URL 开始

### 发起 crawl

**Endpoint**: `POST /v2/crawl`
**用途**：从一个起始 URL 出发，递归发现并抓取整个站点（或其中一部分）下的所有可达页面，每个
页面走一次完整的 scrape 流程。与 `batch/scrape` 的区别：crawl 只需一个种子 URL，页面列表由
sitemap + 链接发现自动生成；batch/scrape 要求自己提供完整 URL 列表，不做任何发现。这是异步
任务，本端点立即返回任务 id，不返回页面内容（见上方"最重要的一件事"）。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `url` | string(uri) | 是 | 无 | 起始 URL |
| `limit` | integer | 否 | `10000` | 最多抓取页数；开始前会检查剩余 credits 能否覆盖 `limit`，不够则 402 |
| `maxDiscoveryDepth` | integer | 否 | 无 | 链接发现跳数上限（非 URL `/` 段数）；根站点和 sitemap 命中页深度为 0，到达上限的页面仍会被抓，但不再跟踪其上的链接 |
| `includePaths` / `excludePaths` | string[] | 否 | 无 | URL **路径名**正则白/黑名单（Rust/RE2，不支持环视和反向引用）；起始 URL 也要匹配 `includePaths`，否则可能返回 0 页 |
| `regexOnFullURL` | boolean | 否 | `false` | 为 `true` 时上面两个正则匹配完整 URL（含 query string），而非仅路径名 |
| `sitemap` | string | 否 | `"include"` | `include`（sitemap+链接发现）/ `skip`（只走 HTML 链接）/ `only`（只用 sitemap+起始 URL） |
| `crawlEntireDomain` | boolean | 否 | `false` | `false` 只抓子路径；`true` 允许跟踪同级/父级路径 |
| `allowSubdomains` | boolean | 否 | `false` | 是否跟踪子域名链接 |
| `allowExternalLinks` | boolean | 否 | `false` | 是否跟踪站外链接（只跟一跳）；指向外部站点首页的链接会被跳过，记入 errors，错误码 `EXTERNAL_LINK` |
| `ignoreQueryParameters` | boolean | 否 | `false` | 不因 query string 不同而重复抓同一路径 |
| `ignoreRobotsTxt` / `robotsUserAgent` | boolean / string | 否 | `false` / 无 | 忽略 robots.txt / 自定义 robots.txt 判定 UA；**均为企业版专属** |
| `delay` | number | 否 | 无 | 每次 scrape 间隔秒数；设置后并发强制为 1 |
| `maxConcurrency` | integer | 否 | 团队并发上限 | 本次 crawl 的最大并发 scrape 数 |
| `scrapeOptions` | object | 否 | 无 | 应用到每个被抓页面的 scrape 参数，`formats` 用法与 `scrape.md` 完全相同 |
| `webhook` | object | 否 | 无 | webhook 配置，见文末小节 |
| `prompt` | string | 否 | 无 | 自然语言生成以上参数；显式设置的参数覆盖生成值 |
| `zeroDataRetention` | boolean | 否 | `false` | 零数据保留，需联系 help@firecrawl.dev |

**示例请求**

```bash
curl -s -X POST "https://api.firecrawl.dev/v2/crawl" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://docs.firecrawl.dev",
    "limit": 100,
    "includePaths": ["blog/.*"],
    "scrapeOptions": { "formats": ["markdown"], "onlyMainContent": true }
  }'
```

```python
import os, requests

resp = requests.post(
    "https://api.firecrawl.dev/v2/crawl",
    headers={"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"},
    json={
        "url": "https://docs.firecrawl.dev",
        "limit": 100,
        "includePaths": ["blog/.*"],
        "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
    },
)
job_id = resp.json()["id"]  # 之后用来轮询
```

**示例响应**

已用真实 API 验证（2026-09-21），`{"url":"https://skillify.carbonleft.com","limit":2}`：

```json
{"success": true, "id": "01a0bf91-...", "url": "https://api.firecrawl.dev/v2/crawl/01a0bf91-..."}
```

**注意事项**

- 最容易踩的坑：响应里**没有 `data`**，拿不到页面内容，必须轮询或用 webhook。
- 默认只抓"子路径"，不跟踪同级/父级路径，例如爬 `website.com/blogs/` 不会返回
  `website.com/other-parent/blog-1`；要覆盖更广用 `crawlEntireDomain`。
- `includePaths`/`excludePaths` 匹配的是路径名，不含 query parameters（除非
  `regexOnFullURL: true`）；正则不支持环视/反向引用，编译失败直接 400。多关键词建议拆成多条短
  pattern。单字段最多 1000 条、每条 2000 字符，两字段合计最多 1000 条、100,000 字符。
- credit 消耗：每页 1 credit；JSON 格式每页 +4 credits；PDF 解析每页 1 credit（文档转录数值；
  本次验证的 2 页纯 markdown crawl 消耗 2 credits，与文档一致）。
- **结果不保证确定**：页面并发抓取，链接发现顺序受网络时序影响，同配置多次运行结果可能不同，
  `maxDiscoveryDepth` 越大越明显。要更可复现：`maxConcurrency: 1`（或设 `delay`，同样强制并发
  为 1），或用 `sitemap: "only"`。
- `completed == total` 不代表全部成功——`total` 只统计 `completed` 加上进行中/排队/积压的页面，
  **失败页面不计入**，所以终态时两者总相等，无法据此判断有无失败；失败只能查
  `GET /crawl/{id}/errors`。

### 轮询 crawl 状态 / 取结果

**Endpoint**: `GET /v2/crawl/{id}`
**用途**：查询 crawl 任务进度，并在同一响应里直接拿到已抓到的页面内容——没有独立的"结果"
端点。本身是只读操作，不消耗新的 crawl。

**关键参数**：`id`（path，string(uuid)，必填）——crawl 任务 id。

响应体关键字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | 当前状态；端点级 schema 只写了 `scraping`/`completed`/`failed`（⚠ 文档自相矛盾，见下） |
| `total` | integer | `completed` 加进行中/排队/积压的页面数；**失败页面不计入** |
| `completed` | integer | 已成功抓取页数 |
| `creditsUsed` | integer | 已消耗 credits |
| `expiresAt` / `createdAt` / `completedAt` / `duration` | string / string / string / number | 过期时间（完成后 24 小时内可取）/ 开始时间 / 结束时间（仅终止态有）/ 已耗时秒数 |
| `next` | string | 下一页 10MB 数据的 URL；只要 `status` 非 `completed`，或响应超 10MB，就会出现 |
| `data` | array\<object\> | 已抓页面，字段与单页 scrape 响应一致（`markdown`/`html`/`links`/`metadata` 等，取决于 `scrapeOptions.formats`） |

**示例请求**

```bash
curl -s -X GET "https://api.firecrawl.dev/v2/crawl/01a0bf91-..." \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY"
```

```python
import os, requests, time

headers = {"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"}
url = f"https://api.firecrawl.dev/v2/crawl/{job_id}"
r = requests.get(url, headers=headers).json()
while r["status"] not in ("completed", "failed", "cancelled"):
    time.sleep(3)
    r = requests.get(url, headers=headers).json()

pages = r["data"]
while r.get("next"):
    r = requests.get(r["next"], headers=headers).json()
    pages += r["data"]
```

**示例响应**

已用真实 API 验证（2026-09-21），发起 2 页 crawl 约 3 秒后轮询：

```json
{
  "success": true, "status": "scraping", "completed": 2, "total": 2, "creditsUsed": 2,
  "expiresAt": "...", "next": "https://api.firecrawl.dev/v2/crawl/01a0bf91-...?skip=2",
  "data": [{ "...": "已抓取页面，字段与单页 scrape 响应一致" }]
}
```

**注意事项**

- ⚠ 文档自相矛盾：`GET /crawl/{id}` 自身响应 schema 只列 `scraping`/`completed`/`failed`，但
  同一份规范里 `DELETE /crawl/{id}` 的成功响应把 `status` 固定为 `cancelled`，且
  `features_crawl.md` 文档页正文明确写"One of `scraping`, `completed`, `failed`, or
  `cancelled`"——任务取消后再查状态会出现端点自身 schema 没列出的值。
- `next` **不是纯粹的"还有更多数据"信号**：只要 `status` 非 `completed` 就会出现，一个终止态
  的 `failed`/`cancelled` crawl 也可能一直带着 `next`。**不要**用"`next` 是否存在"作轮询退出
  条件——应以 `status` 到达终止态为退出条件，再看 `next` 是否存在且上一页 `data` 非空来决定是否
  继续翻页。
- `data` 里是 Firecrawl **自己成功抓到**的页面，哪怕目标站点返回 404，只要 Firecrawl 拿到了
  响应体就算成功，HTTP 状态码在 `data[].metadata.statusCode`；真正的"抓取失败"（网络错误、超时、
  robots.txt 拦截）不在 `data` 里，要查 `errors` 端点。
- 结果完成后 24 小时内可通过 API 取，过期后只能去 activity logs。

### 取消 crawl

**Endpoint**: `DELETE /v2/crawl/{id}`
**用途**：取消一个仍在进行中的 crawl 任务，是有副作用的写操作。

**关键参数**：`id`（path，string(uuid)，必填）。

```bash
curl -s -X DELETE "https://api.firecrawl.dev/v2/crawl/01a0bf91-..." \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY"
```

**示例响应**：文档/规范转录，未实测：成功 `{"status": "cancelled"}`；未找到任务 404 `{"error": "..."}`。

**注意事项**

- 未找到任务是 404，不是 200 里带错误字段。
- 取消后再查状态，`status` 应变为 `cancelled`（见上一节枚举矛盾）；已抓到的页面预期仍保留在
  `data` 里，但本次会话未实测确认，⚠ 文档未说明。

## 查看 crawl 失败了哪些页面

**Endpoint**: `GET /v2/crawl/{id}/errors`
**用途**：`GET /v2/crawl/{id}` 的 `data` 只含成功页面；这个端点列出 Firecrawl **自己**没抓成功
的页面（网络错误、超时、robots.txt 拦截），是判断 crawl 是否"真的抓全了"的唯一途径——
`completed == total` 说明不了有无失败（见上文）。

**关键参数**：`id`（path，string(uuid)，必填）。

响应体：`errors`（数组，每条含 `id`/`url`/`error`/`timestamp`）、`robotsBlocked`（被 robots.txt
拦截的 URL 数组）。

**示例请求**

```bash
curl -s -X GET "https://api.firecrawl.dev/v2/crawl/01a0bf91-.../errors" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY"
```

**示例响应**

文档/规范转录，未实测：

```json
{
  "errors": [{ "id": "...", "url": "https://example.com/broken", "error": "timeout", "timestamp": "2026-09-21T00:00:00.000Z" }],
  "robotsBlocked": ["https://example.com/private"]
}
```

**注意事项**

- 站外首页链接被跳过时也记录在 `errors` 里，错误码 `EXTERNAL_LINK`；但文档页自己说这个错误码
  "目前会出现在 error 对象上，但还不是已发布 schema 的一部分"——⚠ 文档原文自称与自己的 schema
  不同步。
- 这份列表**不保证完整**：文档明确说"部分内部失败类型目前会在响应构建前被过滤掉"，只能当作
  "已报告的失败"，不能当作"没报告就没失败"的证明。
- 目标站点返回 404/500 等 HTTP 错误码不算这里的 error——那种页面在 `data` 里，状态码在
  `metadata.statusCode`。

## 抓取一份已知的固定 URL 列表

### 发起 batch scrape

**Endpoint**: `POST /v2/batch/scrape`
**用途**：对一份**自己提供的**明确 URL 列表做并发抓取，不做任何链接发现——这是它与 `crawl`
最根本的区别。和单页 `scrape` 相比，batch/scrape 一次提交多个 URL，且同样是异步任务（立即返回
任务 id，不返回内容，与 crawl 完全一致）。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `urls` | array\<string(uri)\> | 是 | 无 | 要抓取的 URL 列表 |
| `ignoreInvalidURLs` | boolean | 否 | `true` | 列表含非法 URL 时默认忽略，用其余 URL 建任务，非法 URL 进 `invalidURLs`；`false` 时非法 URL 会让整个请求失败 |
| `maxConcurrency` | integer | 否 | 团队并发上限 | 本次 batch 最大并发 scrape 数 |
| `formats` | array | 否 | `['markdown']` | 与单页 scrape 完全相同，见 `scrape.md`；结构化抽取须用 `{"type":"json","schema":{...}}` 对象形式，裸字符串 `"json"` 会静默失败（见 `scrape.md` 的已验证陷阱） |
| `onlyMainContent` / `onlyCleanContent` | boolean | 否 | `true` / `false` | 只留正文 / Beta，LLM 二次清洗残留样板内容 |
| `maxAge` / `minAge` | integer | 否 | `172800000`（2天）/ 无 | 缓存有效期（毫秒）/ 只读缓存不新抓，无匹配返回 404 `SCRAPE_NO_CACHED_DATA` |
| `webhook` | object | 否 | 无 | 事件为 `batch_scrape.started`/`.page`/`.completed`/`.failed` |
| `proxy` | string | 否 | `auto` | `basic` / `enhanced` / `auto` |
| `zeroDataRetention` | boolean | 否 | `false` | 零数据保留，需联系 help@firecrawl.dev |

（`actions`/`parsers`/`redactPII`/`location` 等每页 scrape 选项与单页 scrape 完全一致，字段见
`scrape.md`，不重复展开。）

**示例请求**

```bash
curl -s -X POST "https://api.firecrawl.dev/v2/batch/scrape" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://firecrawl.dev", "https://docs.firecrawl.dev"], "formats": ["markdown"]}'
```

```python
import os, requests

resp = requests.post(
    "https://api.firecrawl.dev/v2/batch/scrape",
    headers={"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"},
    json={"urls": ["https://firecrawl.dev", "https://docs.firecrawl.dev"], "formats": ["markdown"]},
)
job_id = resp.json()["id"]
```

**示例响应**

文档/规范转录，未实测（本次会话未对 `/v2/batch/scrape` 发真实请求；OpenAPI 与文档页两处描述
一致，但未用真实 key 验证）：

```json
{"success": true, "id": "123-456-789", "url": "https://api.firecrawl.dev/v2/batch/scrape/123-456-789", "invalidURLs": []}
```

**注意事项**

- 和 crawl 一样，这里也**没有页面内容**，只有任务 id——不要以为传了多个 URL 就同步拿回结果。
- `invalidURLs` 只在 `ignoreInvalidURLs`（默认 `true`）生效时出现；显式设 `false` 时该字段
  "undefined"（按 OpenAPI 原文），非法 URL 会直接让整个请求失败而不是被跳过。
- credit 消耗：文档页例子里 36 个 URL 全成功消耗 36 credits，即默认纯 markdown 模式下
  1 credit/URL，与 crawl 一致；JSON 结构化抽取等格式的额外加价按 scrape 侧规则（单页 scrape 实测
  JSON 格式是 5 credits，见 `scrape.md`），batch/scrape 侧的叠加数值本次未单独验证，⚠ 文档未说明。

### 轮询 batch scrape 状态 / 取结果

**Endpoint**: `GET /v2/batch/scrape/{id}`
**用途**：与 `GET /v2/crawl/{id}` 结构完全对称——内容同样嵌在响应的 `data` 里，分页方式也是
同一套 `next` + `?skip=N`。

**关键参数**：`id`（path，string(uuid)，必填）。

响应体字段与 `GET /v2/crawl/{id}` 一致：`status`（`scraping`/`completed`/`failed`，同样有 ⚠
文档自相矛盾，见下）、`total`、`completed`、`creditsUsed`、`expiresAt`/`createdAt`/
`completedAt`/`duration`、`next`、`data`（每项字段同单页 scrape 响应）。

**示例请求**

```bash
curl -s -X GET "https://api.firecrawl.dev/v2/batch/scrape/123-456-789" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY"
```

```python
import os, requests, time

headers = {"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"}
url = f"https://api.firecrawl.dev/v2/batch/scrape/{job_id}"
r = requests.get(url, headers=headers).json()
while r["status"] not in ("completed", "failed", "cancelled"):
    time.sleep(3)
    r = requests.get(url, headers=headers).json()
pages = r["data"]
```

**示例响应**

文档/规范转录，未实测：

```json
{
  "status": "completed", "total": 36, "completed": 36, "creditsUsed": 36,
  "expiresAt": "2024-00-00T00:00:00.000Z",
  "next": "https://api.firecrawl.dev/v2/batch/scrape/123-456-789?skip=26",
  "data": [{ "markdown": "...", "metadata": { "title": "...", "sourceURL": "...", "statusCode": 200 } }]
}
```

**注意事项**

- ⚠ 文档自相矛盾：与 crawl 同款问题——端点自身 schema 只写 `scraping`/`completed`/`failed`，
  但 `DELETE /batch/scrape/{id}` 的成功响应把 `status` 设为 `cancelled`。
- 文档页给出的"completed"示例里 `next` 依然出现（`?skip=26`），呼应 crawl 一节的提醒：即使
  `status: "completed"` 也不保证没有 `next`，翻页循环应以 `data` 是否为空判断，不能只看
  `status`。
- 结果同样 24 小时内可用 API 取，过期后转 activity logs。

### 取消 batch scrape

**Endpoint**: `DELETE /v2/batch/scrape/{id}`
**用途**：取消进行中的 batch scrape 任务，与 crawl 取消端点结构完全对称。

**关键参数**：`id`（path，string(uuid)，必填）。

```bash
curl -s -X DELETE "https://api.firecrawl.dev/v2/batch/scrape/123-456-789" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY"
```

**示例响应**：文档/规范转录，未实测：成功 `{"status": "cancelled"}`；未找到任务 404。

**注意事项**：与 crawl 取消端点行为一致——未找到任务是 404，不是带错误字段的 200。

## 查看 batch scrape 失败了哪些 URL

**Endpoint**: `GET /v2/batch/scrape/{id}/errors`
**用途**：与 `GET /v2/crawl/{id}/errors` 结构完全一致，列出 Firecrawl 自己没抓成功的 URL 和
robots.txt 拦截的 URL。

**关键参数**：`id`（path，string(uuid)，必填）。响应体：`errors`（数组，`id`/`url`/`error`/
`timestamp`）、`robotsBlocked`（数组）——字段与 crawl 的 errors 端点完全一致。

```bash
curl -s -X GET "https://api.firecrawl.dev/v2/batch/scrape/123-456-789/errors" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY"
```

**示例响应**：文档/规范转录，未实测：`{"errors": [], "robotsBlocked": []}`。

**注意事项**：与 crawl 侧一样，不保证完整枚举——`errors` 会漏掉部分被内部过滤掉的失败类型
（⚠ 文档未说明具体过滤了哪些类型）。

## 在真正跑 crawl 之前，预览它会抓到什么

**Endpoint**: `POST /v2/crawl/params-preview`
**用途**：把一句自然语言 prompt（例如"抓这个站点 /blog 下的所有文章，跳过 /blog/archive"）
连同起始 URL 发过去，Firecrawl 用 LLM 翻译成一组结构化 crawl 参数**返回给你**，但**不会**真的
发起 crawl——它是"把 prompt 编译成参数草稿"，不是"试跑一遍看命中哪些 URL"。想直接用自然语言
发起 crawl，可把同一个 `prompt` 字段直接传给 `POST /v2/crawl` 本身（该端点也接受 `prompt`，
生成的参数可被显式参数覆盖）。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `url` | string(uri) | 是 | 要爬取的 URL |
| `prompt` | string | 是 | 描述想爬什么的自然语言 |

响应体（`data` 内）：`url`、`includePaths`/`excludePaths`、`maxDepth`（⚠ 见下）、
`maxDiscoveryDepth`、`crawlEntireDomain`/`allowExternalLinks`/`allowSubdomains`、`sitemap`
（枚举只列 `skip`/`include`，⚠ 见下）、`ignoreQueryParameters`/`ignoreRobotsTxt`/
`robotsUserAgent`、`deduplicateSimilarURLs`（⚠ 见下）、`delay`（⚠ 见下）、`limit`。

**示例请求**

```bash
curl -s -X POST "https://api.firecrawl.dev/v2/crawl/params-preview" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://docs.firecrawl.dev", "prompt": "只抓 /blog 下的文章，跳过 /blog/archive"}'
```

```python
import os, requests

r = requests.post(
    "https://api.firecrawl.dev/v2/crawl/params-preview",
    headers={"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"},
    json={"url": "https://docs.firecrawl.dev", "prompt": "只抓 /blog 下的文章，跳过 /blog/archive"},
).json()
print(r["data"])
```

**示例响应**

文档/规范转录，未实测：

```json
{
  "success": true,
  "data": {
    "url": "https://docs.firecrawl.dev",
    "includePaths": ["blog/.*"], "excludePaths": ["blog/archive/.*"],
    "maxDepth": 3, "maxDiscoveryDepth": 3,
    "crawlEntireDomain": false, "allowExternalLinks": false, "allowSubdomains": false,
    "sitemap": "include", "ignoreQueryParameters": false, "limit": 100
  }
}
```

**注意事项**

- ⚠ 文档自相矛盾（字段命名）：`POST /v2/crawl` 请求体只接受 `maxDiscoveryDepth`，没有单独的
  `maxDepth`；但 `params-preview` 响应同时列出 `maxDepth` 和 `maxDiscoveryDepth`。不清楚
  `maxDepth` 是别名、是 `/crawl` 尚未公开支持的参数，还是遗留旧字段名——⚠ 文档未说明，把
  `params-preview` 输出原样喂给 `/crawl` 前应先确认 `maxDepth` 会不会被接受或静默忽略。
- ⚠ 文档自相矛盾（枚举不一致）：`params-preview` 响应里 `sitemap` 的枚举只写 `skip`/
  `include`，但 `POST /v2/crawl` 的 `sitemap` 明确有三个值 `skip`/`include`/`only`。preview
  是否会生成 `"only"`——⚠ 文档未说明。
- ⚠ 文档未说明：`deduplicateSimilarURLs` 只出现在 `params-preview` 响应里，`POST /v2/crawl`
  请求体没有同名参数——不清楚是 preview 独有的软性建议，还是 `/crawl` 其实支持但未写进公开
  schema。
- ⚠ 文档未说明（单位不一致）：`params-preview` 响应里 `delay` 的描述是"毫秒"，但
  `POST /v2/crawl` 请求体自己的 `delay` 描述是"秒"——同名字段、同批端点，单位描述不一致，不确定
  是笔误还是两端点确实不同单位；直接复用 preview 的 `delay` 值前应先核实。
- 以上几处均未实测，稳妥做法是把 `params-preview` 输出当"草稿"人工核对后再拼进真正的
  `POST /v2/crawl` 请求体，不要把整个 `data` 对象原样透传。

## 查看当前有哪些 crawl 在跑

**Endpoint**: `GET /v2/crawl/active`
**用途**：列出当前团队所有仍在进行中的 crawl 任务（不含 batch/scrape——没有对应的
`GET /v2/batch/scrape/active`）。适合发起新 crawl 前检查是否已有类似任务在跑，避免重复消耗
credits，或用于监控面板。

**关键参数**：无请求参数。

**响应体**：`success`（boolean，必填）、`crawls`（数组，每项含 `id`/`teamId`/`url`/`options`，
`options` 是该 crawl 发起时用的完整爬虫参数，含 `scrapeOptions`）。

**示例请求**

```bash
curl -s -X GET "https://api.firecrawl.dev/v2/crawl/active" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY"
```

```python
import os, requests

r = requests.get(
    "https://api.firecrawl.dev/v2/crawl/active",
    headers={"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"},
).json()
for c in r["crawls"]:
    print(c["id"], c["url"])
```

**示例响应**

文档/规范转录，未实测：

```json
{
  "success": true,
  "crawls": [{ "id": "01a0bf91-...", "teamId": "team_...", "url": "https://docs.firecrawl.dev",
               "options": { "scrapeOptions": { "formats": [{ "type": "markdown" }] } } }]
}
```

**注意事项**

- 只返回"active"任务；已完成/失败/取消的任务不出现，要查历史要么记住自己发起时的 id 去
  `GET /crawl/{id}`，要么去 activity logs。
- ⚠ 文档未说明：分页方式未知——团队同时有大量 crawl 在跑时 `crawls` 是否有上限或游标分页，
  OpenAPI 摘要和文档页均未提及。

## 获取通知，不用轮询：webhook

`crawl` 和 `batch/scrape` 都支持在请求体里加 `webhook` 对象，作为轮询的替代方案——任务开始、
每抓完一页、任务结束时 Firecrawl 会主动 POST 到指定 URL。

```json
{"webhook": {"url": "https://your-domain.com/webhook", "headers": {"X-Custom": "..."},
             "metadata": {"any_key": "any_value"}, "events": ["started", "page", "completed"]}}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `url` | string | 是 | 接收 webhook 的 HTTPS 端点 |
| `headers` | object | 否 | 随请求带上的自定义 header |
| `metadata` | object | 否 | 原样附加到每次 webhook payload |
| `events` | array\<string\> | 否 | 只订阅指定事件；默认全订阅 |

- crawl 事件：`crawl.started` / `crawl.page`（每抓完一页触发，`data` 是那页内容+metadata）/
  `crawl.completed` / `crawl.failed`；batch/scrape 对应 `batch_scrape.started`/`.page`/
  `.completed`/`.failed`。
- payload 结构统一：`{"success":bool,"type":"crawl.page","id":"<任务id>","data":[...],"metadata":{...}}`；
  失败事件另有 `error` 字段。
- 端点必须 **10 秒内**返回 2xx，否则算失败；自动重试 3 次（1 分钟 / 5 分钟 / 15 分钟后各一次），
  全部失败后放弃，不再重试。
- 每个请求带 `X-Firecrawl-Signature` 头（`sha256=...`，HMAC-SHA256），务必先用账户 Advanced 设置
  里的 webhook secret 做 timing-safe 签名校验，再处理 payload。
- 以上全部来自 `webhooks/overview.md` 与 `webhooks/events.md` 转录，本次会话未搭建真实接收端点
  触发和验证投递、签名或重试行为，⚠ 文档原文，未实测。

## Credits 与已验证事实小结

已用真实 API 验证（2026-09-21）：

- 账号计划 1000 credits/周期，本轮验证后剩余约 511（`GET /v2/team/credit-usage` →
  `{"success":true,"data":{"remainingCredits":N,"planCredits":N,...}}`）。
- `limit:2` 的 crawl 实际消耗 2 credits（1 credit/页），与文档一致。
- `POST /v2/crawl` 初始响应确认不含页面数据，只有 `success`/`id`/`url`；`GET /v2/crawl/{id}`
  轮询响应确认内容在 `data` 里、`next` 带 `?skip=N` 分页游标——这是本文开头的核心结论，也是本次
  验证中信度最高的部分。

未实测、依据文档/OpenAPI 转录（各小节内已标 "文档/规范转录，未实测" 或 "⚠ 文档原文，未实测"）：

- `batch/scrape` 全部四个端点（发起/查状态/取消/查错误）——本次会话未对 `/v2/batch/scrape*`
  发过真实请求，字段来自 OpenAPI `Scraping.md` 摘要与 `features_batch-scrape.md` 文档页，两者
  互相印证但未被真实调用验证。
- `crawl` 的 `DELETE`、`/errors`、`/params-preview`、`/active` 四个端点——同样未发真实请求，
  只做字段级转录。
- `status` 到达终止态（`completed`/`failed`/`cancelled`）时的真实响应形状——本次验证的 crawl
  轮询只观察到了中间态 `status:"scraping"`，没有等它跑完看终止态响应。
- webhook 投递本身（签名头、重试时序）——没有搭建真实接收端点触发和验证。
