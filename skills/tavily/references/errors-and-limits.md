# 鉴权、速率限制、计费、错误码、账号与企业版管理

> ⚠ 文档版参考：字段表来自官方 OpenAPI 规范（`/usage`、`/logs`、`/org-usage`、`/feedback`），限流/计费/企业版三块来自叙述性文档，
> 抓取于 2026-09-21，**未用真实 API Key 验证**。

目录：[1. 鉴权](#1-鉴权) · [2. 速率限制](#2-速率限制) · [3. Credits 计费总表](#3-credits-计费总表)
· [4. HTTP 错误码](#4-http-错误码) · [5. Usage / Logs](#5-usage--logs) · [6. Feedback](#6-feedback)
· [7. Org-Usage 与企业版 Key 管理](#7-org-usage-与企业版-key-管理仅-enterprise-套餐) · [8. API Key 安全实践](#8-api-key-安全实践)

## 1. 鉴权

| 方式 | 适用 endpoint | 格式 |
| :--- | :--- | :--- |
| `bearerAuth`（普通 Key） | `/search`、`/extract`、`/crawl`、`/map`、`/research`、`GET /research/{id}`、`/feedback`、`/usage`、`/logs` | `Authorization: Bearer tvly-YOUR_API_KEY` |
| `ownerBearerAuth`（组织 owner 个人 Key） | `/org-usage` | 同上 header 格式，但 key 必须来自组织 **owner 本人的个人账号**，不能是组织/企业级 key |
| Keyless（无 Key） | 仅 `/search`、`/extract` | header `X-Tavily-Access-Mode: keyless`，与 `Authorization` 同时出现时以 `Authorization` 为准 |

控制台 `app.tavily.com` 区分「Development」和「Production」两种 Key，对应不同的速率限制档位（见 §2）；生产 Key 需要账号有有效付费方案或开启 PAYGO。

## 2. 速率限制

| Endpoint 分组 | Development | Production |
| :--- | :--- | :--- |
| 默认（`/search`、`/extract`） | 100 RPM | 1,000 RPM |
| `/crawl`（创建） | 100 RPM | **100 RPM（不随生产 key 升档）** |
| `/map`（创建） | ⚠ 文档未明确列出独立限流条目，未知是否共享 Crawl 的固定 100 RPM 还是走默认档；待验证 | 同左 |
| `/research`（**创建任务**，`POST /research`） | 20 RPM | **20 RPM（不随生产 key 升档）** |
| `GET /research/{id}`（轮询状态） | 走默认档 100 RPM | 走默认档 1,000 RPM |
| `/usage` | 10 次 / 10 分钟 | 10 次 / 10 分钟（同样不升档） |

超限返回 `429 Too Many Requests`，若响应带 `Retry-After` header，按其秒数等待后重试；错误文案本身会因限流规则不同而变化，**判断是否限流用状态码 + header，
不要匹配错误信息文本**（官方原文明确提示这一点）。Keyless 访问走独立、更严格的限流规则，具体数值文档未给出。

## 3. Credits 计费总表

| Endpoint | 计费单位 | Basic/默认 | Advanced/加强 |
| :--- | :--- | :--- | :--- |
| Search | 每次请求 | `basic`/`fast`/`ultra-fast` = 1 credit | `advanced` = 2 credits |
| Extract | 每 5 次**成功**抽取 | `basic` = 1 credit / 5 次 | `advanced` = 2 credits / 5 次 |
| Map | 每 10 个**成功**发现的页面 | 常规 = 1 credit / 10 页 | 带 `instructions` = 2 credits / 10 页 |
| Crawl | Mapping 部分 + Extraction 部分**相加** | 见下方示例 | 见下方示例 |
| Research | 每请求区间（不是固定值） | `model=mini`：4–110 credits | `model=pro`：15–250 credits |
| Feedback | 不计费 | — | — |

**Crawl 计费示例**（官方原文）：爬 10 页、`extract_depth=basic` → mapping 1 credit（10 页÷10）+ extraction 2 credits（10 次成功÷5）= **3 credits**；
同样 10 页、`extract_depth=advanced` → mapping 1 + extraction 4 = **5 credits**。若同时传了 `instructions`，mapping 部分的费率也翻倍，
两个乘数（`instructions` 影响 mapping、`extract_depth` 影响 extraction）互相独立、可以同时叠加，不要按单一乘数线性估算。

失败的 URL/页面**从不计费**（Extract/Map/Crawl 官方原文均强调这一点），只按成功数计费。

套餐价格（截至抓取时）：Free 1,000 credits/月；Project $30/4,000 credits；Bootstrap $100/15,000；Startup $220/38,000；Growth $500/100,000；
PAYGO $0.008/credit；Enterprise 定制。生产 Key 需要账号有效付费方案或开启 PAYGO，否则拿不到生产档速率限制（Rate Limits 页 Tip 原文）。

## 4. HTTP 错误码

所有 endpoint 共用同一套错误响应形态：`{"detail": {"error": "..."}}`（422 是数组形态，见下）。

| 状态码 | 含义 | 适用范围 |
| :--- | :--- | :--- |
| 400 | 请求参数不合法（如某个组合参数依赖的前提字段没设） | 全部 POST endpoint |
| 401 | Key 缺失或错误 | 全部 |
| 403 | Crawl/Map：起始 URL 不被支持；Logs：免费账号调用；org-usage：传了非 owner 个人 key | 各自专属 |
| 404 | 研究任务 `request_id` 不存在；org-usage：组织不存在或无权限 | `GET /research/{id}`、`/org-usage` |
| 413 | 请求体超过 256 KB | 仅 `/feedback` |
| 422 | 请求体 schema 校验失败，`detail` 是数组，每项含 `loc`/`msg`/`type`/`input`/`ctx` | 全部（FastAPI 风格校验错误） |
| 429 | 超速率限制，看 `Retry-After` header | 全部 |
| 432 | Key 或 Plan 额度超限 | 全部业务 endpoint |
| 433 | PAYGO 额度超限 | 全部业务 endpoint |
| 500 | 服务端错误 | 全部 |
| 504 | 查询超时 | `/logs`、`/org-usage` |

**⚠ 文档原文，未实测**：以上全部来自 OpenAPI 规范的 `responses` 描述文字，没有一条真实调用验证过。432/433 是 Tavily 自定义的非标准状态码
（不是 IANA 注册状态码），写错误处理代码时不要假设客户端库/HTTP 框架会自动识别成"客户端错误"分类，需要显式按数字判断。

## 5. Usage / Logs

**`GET /usage`** — 查当前 Key 和账号的用量。可选 header `X-Project-ID` 按项目筛选。限流 10 次/10 分钟（全平台最严格）。

```bash
curl https://api.tavily.com/usage -H "Authorization: Bearer $TAVILY_API_KEY"
```

响应给出 `key.usage`/`key.limit`（当前 Key 本计费周期用量/上限，`limit` 为 `null` 表示不限）以及按 endpoint 拆分的 `key.search_usage`/`extract_usage`/
`crawl_usage`/`map_usage`/`research_usage`；`account.*` 是整个账号套餐维度的对应字段，另有 `account.current_plan`/`paygo_usage`/`paygo_limit`。

**`POST /logs`** — 查最近的逐请求调用日志（**仅付费方案可用，免费账号 403**）。

| 参数 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `limit` | int | `10` | 最多返回条数，最新的在前 |
| `start_date` / `end_date` | date | — | `YYYY-MM-DD` |
| `endpoints` | array\<string\> | 全部 | `search`/`extract`/`map`/`crawl`/`research` |
| `project_id` | string | — | 只看某个项目 |
| `filter_by_api_key` | bool | `false` | true 时只看发起本次调用的这个 Key 自己的日志，false 时看账号/组织下所有 Key 的日志 |

**日志不含请求/响应的原始内容**（官方 Info 原文强调 "never include the input or output of a request"），只有 `endpoint`/`depth`/`response_time`/
`credits`/`api_key`（掩码到后 4 位）/`request_id`/`timestamp`，做审计或调试具体请求内容时用不上这个接口，只能定位到 `request_id` 再联系支持。

## 6. Feedback

**Endpoint**: `POST /feedback`
**用途**: 对某次 search 请求（`request_id`）或某个 session（`session_id`）提交效果反馈，帮助 Tavily 改进排序质量。**不消耗 credits**。

⚠ **Beta 状态**：官方原话"submit feedback on a best-effort basis — send it asynchronously, treat a failure as non-fatal, and never block your agent
on the response"。不要把 Feedback 调用放在关键路径上，失败了也不影响主流程。

```bash
curl -X POST https://api.tavily.com/feedback \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TAVILY_API_KEY" \
  -d '{"request_id": "123e4567-e89b-12d3-a456-426614174111", "agent_score": 0.9, "used_urls": ["https://example.com"]}'
```

`request_id` 和 `session_id` 至少传一个（都不传返回 400）；可选 `agent_score`/`human_score`/`extra_scores[]`/`comment`/`response_delivered`/
`used_ids`/`used_urls`/`used_citations`/`urls_scores[]`（逐条结果打分，用 `id` 或 `url` 定位）。若账号/组织开启了 Zero Data Retention，这里提交的
自由文本和 URL 内容不会被存储。

## 7. Org-Usage 与企业版 Key 管理（仅 Enterprise 套餐）

以下四个 endpoint 面向 Enterprise 客户，且**不在核心 OpenAPI 规范文件里**（`openapi.json` 只包含 `/org-usage`，`/generate-keys`、`/deactivate-keys`、
`/key-info` 只有叙述性文档页，没有机器可读 schema）——这三个的请求/响应体精确字段⚠ 文档未说明，比其余 endpoint 的可信度更低，接入前建议先找 Tavily 要一份
Enterprise 专属的接口文档或直接找支持确认。

| Endpoint | 用途 | 鉴权 |
| :--- | :--- | :--- |
| `POST /org-usage` | 查组织下所有 Key 的用量、PAYGO 花费（USD）、请求数，按日期/项目/深度筛选 | `ownerBearerAuth`（owner 个人 key） |
| `POST /generate-keys` | 批量生成自定义配置的 API Key | Enterprise 权限（未说明具体是哪种 key） |
| `POST /deactivate-keys` | 按 `request_id`（批量，撤销某次生成请求生成的全部 key）或按 `Authorization` header 里的具体 key（单个）撤销 | 同上 |
| `GET /key-info` | 查某个 Key 的信息，要查的 Key 放在 `Authorization` header 里 | 同上 |

`org-usage` 的关键约束（SKILL.md 通用规则第 8 条已提示）：用 `organization_name`（区分大小写，精确匹配）定位组织，鉴权必须是这个组织 **owner 的个人账号**
Key，传团队/企业 Key 会收到 403 "Please authenticate with the organization owner's personal API key, not an organization API key."；`organization_name`
缺失返回 422。

```bash
curl -X POST https://api.tavily.com/org-usage \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_PERSONAL_TAVILY_API_KEY" \
  -d '{"organization_name": "Acme Corp", "start_date": "2026-08-01", "end_date": "2026-08-31"}'
```

响应给出 `totals`（组织整体用量/PAYGO 花费/请求数，含按 endpoint 拆分的 `totals.by_type.*`）和 `keys[]`（逐 Key 明细，Key 本身掩码到后 5 位）。

## 8. API Key 安全实践

- **泄漏处理**（如误提交进公开仓库、截图里带出、客户端代码硬编码）：立即在控制台撤销该 Key → 生成新 Key → 替换所有环境变量/密钥管理系统里的旧值 →
  如果泄漏前有异常用量，联系 `support@tavily.com`。
- **定期轮换**（官方建议约 90 天一次）：先生成新 Key 并部署到应用（新旧同时有效）→ 验证新 Key 工作正常 → 确认无误后再撤销旧 Key，避免轮换过程中的停机。
- **永远不要把 Key 硬编码进源码**，用环境变量或密钥管理服务；本 skill 全部示例统一用 `TAVILY_API_KEY` 这个环境变量名。
