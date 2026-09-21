# 错误处理与限流

目录：[错误响应结构](#错误响应结构) · [常见 HTTP 状态码](#常见-http-状态码) · [限流：burst + daily 两套独立限制](#限流burst--daily-两套独立限制) · [⚠ 文档自相矛盾的一个数字](#-文档自相矛盾的一个数字) · [限流响应头](#限流响应头) · [429 响应体](#429-响应体) · [重试策略](#重试策略)

全部内容 ⚠ 文档原文，未实测（整理自 `docs/api-reference/error-handling`、`docs/developer-tooling/platform/usage-guidelines`、`docs/apps/legacy-apps/private-apps/overview`，抓取于 2026-09-21）。

## 错误响应结构

多数 HubSpot 错误是人类可读的 JSON，而不是固定错误码枚举：

```json
{
  "status": "error",
  "message": "Property values were not valid: [...]",
  "errors": [
    { "message": "discount was not a valid number", "code": "INVALID_INTEGER", "context": { "propertyName": ["discount"] } }
  ],
  "category": "VALIDATION_ERROR",
  "correlationId": "a43683b0-5717-4ceb-80b4-104d02915d8c"
}
```

**⚠ 官方文档明确警告：以上字段全部要当作可选来解析**——不同 API 返回的字段集合不完全一致，写错误解析代码时不要假设 `category`/`errors`/`correlationId` 一定存在，要做好缺字段的容错，否则解析器本身可能先崩溃。

排查问题时优先带上 `correlationId` 去 HubSpot 支持/开发者社区求助，这是官方用来定位具体请求的标识。

## 常见 HTTP 状态码

| 状态码 | 含义 |
|---|---|
| `200` | 默认成功状态（HubSpot 大多数端点约定，除非该端点文档另有说明） |
| `207 Multi-Status` | 批量创建启用了 `objectWriteTraceId` 时，部分成功部分失败会返回这个而不是 200（见 `references/batch.md`） |
| `400 Bad Request` | 请求格式或字段值有问题，响应体会带 `message` 说明具体原因 |
| `401 Unauthorized` | 鉴权无效（token 错误、过期、格式不对） |
| `403 Forbidden` | 鉴权本身有效但 scope 不够，响应 `errors[].context.requiredGranularScopes` 会列出满足任一个即可的 scope |
| `414` | 请求 URI 过长；或合并两条记录时报这个错，说明目标记录累计合并次数已超 250 次上限（`Cannot have more than 250 identities on a profile`） |
| `423 Locked` | 短时间内对同一批记录并发写太猛，触发乐观锁；等 **≥2 秒**再重试 |
| `429 Too many requests` | 触碰限流（见下） |
| `477 Migration in Progress` | 账号正在做数据中心迁移，响应带 `Retry-After` 头（单位秒，可能长达 24 小时） |
| `502` / `504` | HubSpot 处理超限/超时，暂停几秒后重试 |
| `503` | HubSpot 临时不可用，暂停几秒后重试 |
| `521` / `522` / `523` / `524` | HubSpot 侧服务器/连接问题（含 524 "100 秒内无响应"），暂停后重试；521/522 建议联系官方支持 |
| `525` / `526` | SSL 证书/握手问题，需联系官方支持，重试无意义 |

## 限流：burst + daily 两套独立限制

HubSpot 对每个账号/应用同时施加**两套**限制，任一个先触发都会拒绝后续请求：

- **Burst（每 10 秒滚动窗口）**：短时间内并发请求数上限。
- **Daily（按账号本地时区午夜重置）**：一天总请求数上限。

具体数字取决于你用的是哪种鉴权/分发方式：

| 应用类型 | Product Tier | 每 10 秒 | 每日 |
|---|---|---|---|
| 私有分发（legacy private app 或 2025.2/2026.03 平台上 `distribution: private` 的应用，Service Key 同档） | Free / Starter（任意 Hub） | 100 / app | 250,000 / 账号 |
| 同上 | Professional（任意 Hub） | 190 / app | 625,000 / 账号 |
| 同上 | Enterprise（任意 Hub） | 190 / app | 1,000,000 / 账号 |
| 同上 + 购买 API Limit Increase（最多加购 2 份） | 任意 Tier | **200 或 250**（见下方矛盾说明） / app | 每加购一份 +1,000,000 / 账号（此上限本身**不会**因为多加购继续叠加） |
| 公开分发 OAuth 应用（应用市场上架，legacy public app 或新平台 marketplace 分发） | 不分 Tier，每个**安装该应用的账号**各自计 | 110 / 每个安装账号（**Search API 除外**） | 不适用 daily 限制的说法，文档未给出对应的每日数字 |

**Burst 是按"每个私有应用/Service Key"各自独立计算，Daily 是整个账号所有私有应用共享同一个额度**——这两者的计算粒度不同，容易假设成"两个都是账号级别"或"两个都是应用级别"。

## ⚠ 文档自相矛盾的一个数字

购买 **API Limit Increase** 加购项后，私有分发应用的 burst 上限具体是多少，**两处当前有效的官方文档给出了不同答案**：

- `docs/apps/legacy-apps/private-apps/overview`（私有应用总览页，限流表在"Private app limits"一节）：**200 / private app**。
- `docs/developer-tooling/platform/usage-guidelines`（限流总纲页，表格在"Privately distributed app limits"一节）：**250 / app**。

两个页面都是 2026-09-21 当次抓取时的当前版本，找不到任何"其中一个已过期/待更新"的标注。没有真实账号无法确认哪个数字是对的（也可能两者分别对应不同的历史加购层级，文档没写清楚）。**代码里做限流预算/节流时不要硬编码这两个数字中的任意一个**，而是读实际响应的 `X-HubSpot-RateLimit-Max` 头做动态节流（见下）。

## 限流响应头

| Header | 含义 |
|---|---|
| `X-HubSpot-RateLimit-Daily` | 当日总配额（**OAuth 应用的响应里不会带这个头**） |
| `X-HubSpot-RateLimit-Daily-Remaining` | 当日剩余（同上，OAuth 应用没有） |
| `X-HubSpot-RateLimit-Max` | 当前 burst 窗口允许的最大请求数 |
| `X-HubSpot-RateLimit-Remaining` | 当前 burst 窗口剩余请求数 |
| `X-HubSpot-RateLimit-Interval-Milliseconds` | burst 窗口长度（毫秒），当前是 `10000`（10 秒） |

⚠ `X-HubSpot-RateLimit-Secondly` / `X-HubSpot-RateLimit-Secondly-Remaining` 两个头文档写"仍会返回、数值仍准确，但对应的限制已经不再生效"——不要照这两个头做节流逻辑，它们是历史遗留。**Search API 的响应完全不带以上任何限流头**，节流预算只能靠客户端自己按文档给出的"5 请求/秒"静态数字算（见 `references/search.md`），没有实时剩余配额可读。

## 429 响应体

```json
{
  "status": "error",
  "message": "You have reached your daily limit.",
  "errorType": "RATE_LIMIT",
  "correlationId": "c033cdaa-2c40-4a64-ae48-b4cec88dad24",
  "policyName": "DAILY",
  "requestId": "3d3e35b7-0dae-4b9f-a6e3-9c230cbcf8dd"
}
```

`policyName` 是 `DAILY` 或（burst 场景对应的另一个值，⚠ 文档原文只举了 `DAILY` 的例子，burst 场景对应的具体字符串未在抓取的材料里明确给出，可能是 `TEN_SECONDLY_ROLLING`——文档正文提到过这个术语但没有作为 `policyName` 取值直接展示，未实测）——建议按 `message` 里的关键词（"daily"/"second"）兜底判断，不要假设 `policyName` 只有一种取值。

**429 错误率不应超过当日总请求量的 5%**，如果打算上架应用市场，超过这个比例会导致认证审核不通过。

## 重试策略

- 触发 **daily** 限制没有别的办法，只能等第二天账号所在时区午夜重置，或者升级订阅/购买加购。
- 触发 **burst（10 秒滚动窗口）** 限制应该做客户端节流（按 `X-HubSpot-RateLimit-Max`/`Remaining` 动态调整发送速率），而不是简单粗暴地捕获 429 之后 sleep 固定时间再重试。
- **批量端点 + 客户端缓存设置类数据**是官方给出的降低总请求量的首选手段，而不是单纯地加大 sleep 间隔（见 `references/batch.md`"大批量同步的节流建议"）。
- Webhook 场景（你的服务作为接收方）：HubSpot 对失败的通知最多重试 **10 次**，分散在 24 小时内；workflow 触发的 webhook 收到 `4xx` **不会**自动重试，唯一例外是 `429`（会遵守 `Retry-After` 头，单位是**毫秒**，注意不是秒）。
- Custom code workflow action 里如果自己调用 HubSpot API 遇到 429/5xx（用 `axios` 或 `@hubspot/api-client`），HubSpot 会在最长 **3 天**内自动重试该 action，首次重试延迟约 1 分钟，之后按递增间隔重试，最大间隔 8 小时。
