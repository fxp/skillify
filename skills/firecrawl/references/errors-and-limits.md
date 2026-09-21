# 鉴权、错误码、限流与计费

目录：[鉴权](#鉴权) · [v1 vs v2](#v1-vs-v2不要用-v1) · [错误响应形状](#错误响应形状) · [错误码表](#错误码表文档原文) · [重试策略](#重试策略文档原文) · [限流](#限流) · [计费与 credits](#计费与-credits)

## 鉴权

**已用真实 API 验证（2026-09-20/21）**：`Authorization: Bearer <FIRECRAWL_API_KEY>`，key 格式 `fc-...`。示例代码统一从环境变量 `FIRECRAWL_API_KEY` 读取，绝不硬编码。

- 不带 `Authorization` header → **HTTP 403**（不是 401！）：
  ```json
  {"success":false,"error":"Unfortunately, your IP address looks suspicious, so Firecrawl can't be used without an API key from here. Sign up for a free API key at https://firecrawl.dev for 1000 credits and higher rate limits for free. (If you're an agent, you can also use https://firecrawl.dev/auth.md)"}
  ```
  完全没带 key 和带了一把**错误的** key 是两种不同的 HTTP 状态码，不要用同一段 catch 逻辑处理。
- 带一把错误/伪造的 key → **HTTP 401**：`{"success":false,"error":"Unauthorized: Invalid token"}`

## v1 vs v2：不要用 v1

**已用真实 API 验证（2026-09-21）**：`https://api.firecrawl.dev/v1/scrape` 目前仍然能正常响应，返回的基础字段（`success`/`data.markdown`/`data.metadata`）和 v2 形状一致。但官方当前文档站（`docs.firecrawl.dev`）主入口只讲 v2，v2 独有大量 v1 没有的能力（`batch/scrape`、`map`、结构化 `formats` 数组里的 `question`/`highlights`/`audio`/`video`/`changeTracking` 等）。本 skill 全篇按 **v2**（`https://api.firecrawl.dev/v2`）写。不要因为 v1 现在还能跑就假设两者行为、字段完全一致——本 skill 没有逐条对比过 v1/v2 的差异，只确认了"v1 没报废、基础调用能通"这一点，其余差异 `⚠ 文档未说明`。

## 错误响应形状

**已用真实 API 验证**（400/401/403 三种，见上方与 scrape.md）。非 2xx 响应统一是：
```json
{"success": false, "error": "人类可读的错误信息", "details": "可选，部分错误才有的结构化字段"}
```
判断成功与否统一看 `success` 字段，不要只看 HTTP 状态码是不是 2xx——**但反过来也不能只看 `success`**：`/v2/scrape` 的 JSON 抽取失败时 `success` 仍然是 `true`，失败信号在 `data.json === null` + 一个容易被忽略的 `data.warning` 字段里（`⚠` 最容易被漏掉的一条，见 `references/scrape.md`"JSON 格式"一节）。`success: true` 不等于"拿到了你要的东西"，还要看具体端点自己的完成信号。

## 错误码表（文档原文，https://docs.firecrawl.dev/api-reference/errors ，抓取于 2026-09-21，未逐条实测）

| HTTP | `error`（典型文案） | 原因 | 处理 | 可重试 |
| :--- | :--- | :--- | :--- | :--- |
| 400 | `Bad Request` / 具体校验信息 | 请求体没通过 schema 校验 | 看 `details` 里点名的字段 | 否 |
| 400 | `Invalid URL` | `url` 缺失/格式错/协议不支持 | 传绝对路径的 `http(s)://` URL | 否 |
| 401 | `Unauthorized: Invalid token` | key 缺失/格式错/已吊销 | 换一把有效 key | 否 |
| 402 | `Payment Required: Insufficient credits` | 套餐 credits 用完且没开随用随付 | 升级套餐或开通随用随付 | 否 |
| 403 | `Forbidden` | key 没有这个端点/功能的权限 | 换一把有权限的 key 或升级套餐 | 否 |
| 403 | `SCRAPE_PROMPT_INJECTION_DETECTED` | 开了 `checkPromptInjection: true`，页面内容被判定含 prompt injection，抽取被中止 | 人工核查页面内容；确认是误判可以去掉这个开关重试 | 否 |
| 404 | `Not Found` | job ID / 资源 / 路径不存在 | 核对 ID 和 URL | 否 |
| 408 | `Request Timeout` | 页面加载超过 `timeout` | 调大 `timeout`，简化 `actions`，或用 `fastMode` | 是，退避重试 |
| 409 | `Conflict` | 资源状态不允许这个操作（比如已经被删了） | 重新拉一次状态再决定 | 否 |
| 413 | `Payload Too Large` | 请求体超过大小上限 | 精简 schema，或减少一次 batch 里的 URL 数 | 否 |
| 422 | `Unprocessable Entity` / 抽取 schema 错误 | schema 不是合法 JSON Schema，或模型抽不出符合 schema 的结果 | 校验 schema，放宽 required，或换 `model` | 视情况 |
| 429 | `Rate limit exceeded` | 超过套餐的每分钟请求数上限 | 按 `Retry-After`（秒）退避重试 | 是，退避重试 |
| 429 | `Concurrency limit reached` | 并发浏览器数达到套餐上限 | 等在飞任务结束，降并发，或升级套餐 | 是，退避重试 |
| 500 | `Internal Server Error` | 服务端未处理的失败 | 指数退避重试；持续失败带 request ID 联系支持 | 是，退避重试 |
| 502/503 | `Bad Gateway` / `Service Unavailable` | 上游代理/worker 异常，服务暂时不可用 | 退避重试 | 是，退避重试 |
| 504 | `Gateway Timeout` | 请求超过网关超时（常见于长 crawl 走同步接口） | 改用异步 crawl/batch 接口轮询，而不是等一个长请求 | 是，退避重试 |

429 响应通常带 `Retry-After` header（秒数）——至少等这么久再重试。

## 重试策略（文档原文，未逐条实测）

把上表的"可重试"列当权威依据，不要自己从 HTTP 状态码猜。退避重试要点：`{408, 429, 500, 502, 503, 504}` 可重试，指数退避 + 抖动，429 时优先遵守 `Retry-After`。crawl/batch scrape 这类异步任务本身有 48 小时排队超时（见下方限流一节），轮询状态接口本身不计入 credits 消耗。

## 限流

**并发浏览器数**（决定能同时跑多少个抓取任务，超出的排队，排队超过 48 小时会超时）：Free 2、Hobby 5、Standard 25、Growth 50、Scale/Enterprise 100+。查当前可用量：`GET /v2/team/queue-status`。

**按端点的每分钟请求数上限**（文档原文表格，节选 Free/Hobby/Standard 三档，完整表见 https://docs.firecrawl.dev/rate-limits ）：

| 套餐 | /scrape | /map | /crawl | /search |
| :--- | :--- | :--- | :--- | :--- |
| Free | 10 | 10 | 2 | 10 |
| Hobby | 100 | 100 | 20 | 100 |
| Standard | 500 | 500 | 100 | 500 |

`/batch/scrape` 的限流和 `/crawl` 共享同一份配额，不是单独算的。同一个 team 下所有 API key 共享同一份限流计数器，不是按 key 各算各的。

**无 key 访问（keyless）**：官方托管的 MCP keyless 入口只开放 Search / Scrape / Parse（REST/SDK/CLI 额外开放 Interact），按 IP 每天限请求数和 credits 数两条线，先触发哪条都是 429。`crawl`/`extract`/`map`/`batch scrape` 等一律不支持无 key 调用。本 skill 假设你已经有一把真实 key，不覆盖 keyless 模式的细节。

## 计费与 credits

**已用真实 API 验证（2026-09-21）**，同时和文档表格（https://docs.firecrawl.dev/billing ，抓取于 2026-09-21）互相印证一致：

| 操作 | 官方文档标价 | 本次实测 | 是否一致 |
| :--- | :--- | :--- | :--- |
| 普通 markdown 抓取一页 | 1 credit/页 | 1 credit（`data.metadata.creditsUsed`） | ✅ 一致 |
| JSON 格式抽取一页（`formats` 里带 `{type:"json",...}`） | 1（基础）+4（JSON）=5 credits/页 | 5 credits，**JSON 抽取失败（见 scrape.md 的静默失败坑）时同样收 5 credits** | ✅ 一致，且确认失败也扣费 |
| map 一次调用 | 1 credit/次 | 未在响应里单独确认 credits 字段，但调用本身成功 | 文档转录 |
| search（10 条结果内） | 2 credits/10 条 | 未逐一核对计费，2 条结果的调用能正常拿到内容 | 文档转录 |
| `/v2/extract`（已废弃端点，1 URL、1 个字段） | 文档没有单独给 `/extract` 的计价行（它已经不推荐使用） | **21 credits** | ⚠ 明显比等效的 `/scrape` JSON 格式（5 credits）贵约 4 倍——这是弃用 `/extract`、改用 `/scrape` JSON 格式的另一条理由，不只是"少一个端点" |

**计费判定的关键规则（文档原文）**：决定扣不扣费的是"Firecrawl 有没有返回一份 document"，不是目标网站有没有返回 2xx。目标站返回 403/404，只要 Firecrawl 把这个响应原样抓回来了，照样按 1 credit/页 计费；完全没抓到任何东西（目标站不响应、渲染全部失败）才不计费。**`checkPromptInjection` 中止抽取时按 5 credits 计费**（不是不计），因为页面已经抓下来过一遍才判定出注入。

**crawl 的预检查**：传显式 `limit` 时，Firecrawl 只按这个数量做一次准入检查（通不过会尝试按余额下调 limit 再检查一次，还不行才 402），不会预扣整个 limit 对应的 credits；不传 `limit` 时默认上限是 10000 页，但开始时的检查只按 1 credit 走，不会因为余额不够 10000 页就直接拒绝——**页面是边跑边计费的，不是提交任务时一次性扣完**。batch scrape/crawl 的 credits 到账可能比任务提交晚几分钟到几小时，轮询状态接口本身不耗 credits。

跨端点通用：以上这些"额外加 credits"的修饰符（JSON 格式 +4、`question`/`highlights`/`audio`/`video` 各 +4、PII 脱敏 +4、Zero Data Retention +1 等）可以叠加，且**同样的修饰符在 crawl 和 search 里也适用**——因为它们内部对每一页都是走的 scrape。查实时余额：`GET /v2/team/credit-usage` → `{"success":true,"data":{"remainingCredits":N,"planCredits":N,"billingPeriodStart":"...","billingPeriodEnd":"..."}}`（已实测，字段名和这里一致）。
