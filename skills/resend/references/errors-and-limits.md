# 错误与限制

> ⚠ 本文件的全部内容都是 `⚠ 文档原文，未实测`——整理自 `resend.com/docs`（抓取于 2026-09-21），未经真实 API 调用确认。见 SKILL.md 里的验证状态说明。

## 目录

- [错误响应结构](#错误响应结构)
- [HTTP 状态码含义](#http-状态码含义)
- [完整错误类型参考](#完整错误类型参考)
- [速率限制](#速率限制)
- [发送配额](#发送配额)
- [退信率和投诉率上限](#退信率和投诉率上限)
- [附件限制](#附件限制)
- [数据保留](#数据保留)

## 错误响应结构

Resend 用标准 HTTP 状态码，同时每个错误还会额外带一个 `type` 字符串，比单看状态码更具体（有几个错误 type 会在多个状态码下重复出现——比如 `restricted_api_key` 在 `401` 和 `403` 下分别对应不同的根因，`validation_error` 在 `400` 和 `403` 下都会出现；**如果需要区分这些情况，要基于 `type` 字符串来做判断，不能只看状态码**）。

## HTTP 状态码含义

| 状态码 | 含义 |
|---|---|
| `200` | 成功。 |
| `400` | 请求格式错误/参数不对。 |
| `401` | 请求里**没带** API key，或者这个 key 没有权限执行这个操作（一个仅有发送权限的 key 打到非发送端点会是 `restricted_api_key`）。 |
| `403` | API key **带了但被拒绝**——无效、被暂停、未激活，或者（同一个状态码,不同 `type`）一个关于域名验证/不匹配或 `resend.dev` 测试限制的 `validation_error`。**同时**，原生 HTTP 调用缺少 `User-Agent` 请求头时也是这个状态码（`error code 1010`)——这种情况很容易被误判成"我的 key 不对"，其实 key 本身没问题。 |
| `404` | 资源/端点不存在。 |
| `405` | 该路径不支持这个 Method（比如对一个只支持 `GET`/`POST` 的端点用了 `DELETE`）。 |
| `409` | 冲突——几乎总是和幂等性 key 有关（并发复用或者 payload 不一致的复用），或者是某个资源正在被并发更新。 |
| `422` | 请求体语义上不合法（比如一个附件既没传 `content` 也没传 `path`、一个无效的 UUID 参数、缺少必填字段）。 |
| `429` | 触发了速率限制**或**配额上限——看 `type` 才能分清是哪个（`rate_limit_exceeded` vs `daily_quota_exceeded` vs `monthly_quota_exceeded`）。 |
| `5xx` | Resend 自己的基础设施问题——去 `resend-status.com` 查一下。 |

## 完整错误类型参考

| `type` | 状态码 | 消息（文档原文） | 说明 |
|---|---|---|---|
| `invalid_idempotency_key` | 400 | Idempotency keys, if present, must have between 1 and 256 characters. | |
| `validation_error` | 400 | An error was found with one or more fields in the request. | 通用的字段校验失败；具体是哪个字段在消息体里有细节。 |
| `missing_api_key` | 401 | Missing API key in the authorization header. | |
| `restricted_api_key` | 401 | This API key is restricted to only send emails. | 一个只有 `sending_access` 权限的 key，打到了非发送端点。 |
| `email_above_quota` | 403 | You can't retrieve this email's content because it was above quota when received. | 特指读取*收到*的邮件内容这个场景,和发送无关。 |
| `invalid_permission` | 403 | Access token is missing required scopes. | OAuth token 场景，不是普通 API key。 |
| `restricted_api_key` | 403 | API key is not active | 和上面 401 的 `type` 字符串一样，状态码不同——要同时看 `type` 和状态码，不能只看 `type`。 |
| `suspended_api_key` | 403 | This API key is suspended | |
| `validation_error` | 403 | You can only send testing emails to your own email address... | `resend.dev` 发件人的限制——见 `domain-verification.md`。 |
| `validation_error` | 403 | The `domain.com` domain is not verified. Please, add and verify your domain. | 未验证域名这个核心陷阱——见 `domain-verification.md`。 |
| `validation_error` | 403 | The `example.com` domain has been registered already. | 这个确切的域名已经被另一个团队验证过了。 |
| `not_found` | 404 | The requested endpoint does not exist. | |
| `method_not_allowed` | 405 | Method is not allowed for the requested path. | |
| `concurrent_idempotent_requests` | 409 | There is another request in progress with the same idempotency key. | 短暂等待后重试是安全的。 |
| `invalid_idempotent_request` | 409 | This idempotency key has been used with this HTTP method and endpoint within the last 24 hours, but the request body was modified. | 用*同一个* key、传*不同*的请求体去重试，一定会遇到这个错误——换个 key，或者让请求体和原来完全一致。 |
| `resource_locked` | 409 | Another request is already updating this resource. | 短暂等待后重试。 |
| `invalid_attachment` | 422 | Attachment must have either a `content` or `path`. | |
| `invalid_parameter` | 422 | The `parameter` must be a valid UUID. | |
| `missing_required_field` | 422 | The request body is missing one or more required fields. | |
| `missing_required_parameter` | 422 | The request is missing one or more required parameters. | |
| `daily_quota_exceeded` | 429 | You have exceeded your daily email sending quota. | 仅免费层——见[发送配额](#发送配额)。 |
| `monthly_quota_exceeded` | 429 | You have exceeded your monthly email sending quota. | 所有套餐都适用。 |
| `rate_limit_exceeded` | 429 | Too many requests. Please limit the number of requests per second. | 见[速率限制](#速率限制)。 |
| `application_error` | 500 | An unexpected error occurred. | |
| `service_unavailable` | 503 | API is temporarily unavailable | |

另外还有一条值得关注但没列进上表的（来自 `domain-verification.md` 更深入的覆盖）：**域名/子域名不匹配**的那个 403（验证的是 `sending.example.com`，请求却用了 `example.com`）和未验证域名的场景共用同一个 `validation_error` type，但消息文案不一样——如果你的代码除了 `type` 之外还要分支判断，记得核对具体的消息文本。

## 速率限制

- **默认：每团队 10 请求/秒**（不是按 API key，也不是按域名算的）。账号上的每一个 API key 共享同一个池子。同一团队下两个服务分别以 6 req/s 和 4 req/s 发送，会一起撞上这个共享限额。
- **没有突发（burst）余量。** 同一个一秒窗口内的第 11 个请求就会得到 `429`，哪怕前十秒的请求量一直都远低于限额。
- **每个请求的响应头都会带**（IETF 草案标准的速率限制请求头）：`ratelimit-limit`、`ratelimit-remaining`、`ratelimit-reset`、`retry-after`。客户端限流应该依据这些,而不是靠猜。
- **应对高流量的方式**：批量发送（`POST /emails/batch`，最多 100 封,对限额只算**一次**请求)是文档给出的官方方案——不只是个便利功能。一个朴素的、对每封邮件都单独调用 `POST /emails` 的循环，在同样的实际发信量下，会比基于批量发送的方案更快撞上 `429`。
- 需要更高限额可以联系支持申请——不能自助开通。

## 发送配额

和速率限制是两回事——这个限的是总*发送量*，不是每秒请求数。

| 套餐 | 每日 | 每月 | 备注 |
|---|---|---|---|
| 免费 | **每天 100 封**，在 UTC 午夜重置（固定的日历日，不是滚动 24 小时) | 每月 3,000 封 | **发出和收到**的邮件都算；一次发送里的多个 `to`/`cc`/`bcc` 收件人各自单独计入配额（也就是说，一次带 10 个 `to` 地址的 `POST /emails` 调用会用掉 10 封的每日额度，不是 1 封）。 |
| Pro / Scale / Enterprise | 无每日上限 | 按套餐档位各不相同的每月上限 | 同样的发出+收到计数规则，同样的多收件人计数规则。 |

**超量**：付费套餐允许超出月度配额之后按量付费继续发送，但上限是**月度配额的 5 倍**——超过这个上限，发送会暂停,直到下一个计费周期（联系支持可以调整）。

**实际影响**：在免费层每天 100 封的上限下，"给 N=3 个收件人在一次 `to` 数组里发一封欢迎邮件"这种模式，会消耗掉 100 封里的 3 封，比一个朴素的 agent 可能预期的（"算 1 封已发送"）要快得多。一个没有按收件人计数的批量发送循环，光靠 10 req/s 这一个速率限制,就能在几秒钟内耗尽一个免费账号一整天的额度——通常先撞到的墙是速率限制,不是每日配额，但每日配额要到 UTC 午夜才重置，所以恢复时间不一样（速率限制退避是秒级的，配额重置可能要等上大半天）。

## 退信率和投诉率上限

账号整体的健康指标，和速率限制/配额是相互独立的：

- **退信率必须保持在 4% 以下。**
- **垃圾邮件投诉率必须保持在 0.08% 以下。**

超出任何一项，都可能导致**账号级别的临时发送暂停**，直到指标恢复——这是一个信誉保护机制，不是能在单次请求的错误处理里捕获的东西；通过 dashboard 的 Metrics 页面或者 webhook（`email.bounced`、`email.complained`）来监控，不是靠错误处理代码。考虑到 0.08% 的投诉阈值非常严格（大约每万封 8 封），而且 Gmail 完全不会通过 webhook 上报投诉（见 `webhooks.md`），对于这项特定的限制,dashboard 的 Metrics 页面——而不是单靠 webhook 统计出来的数字——才是唯一完整的信号来源。⚠ 文档原文，未实测。

## 附件限制

完整细节见 `sending-emails.md`；这里从"什么会失败、怎么失败"的角度做个汇总：

- 所有附件加起来，整封邮件 Base64 编码**之后**的大小 **≤ 40 MB**——不是编码前的原始文件大小。
- 有一份文档记录的、*发送*时会被拦截的文件扩展名列表（可执行文件、脚本、几种老旧的 Windows/Office 宏格式)——完整列表见 `sending-emails.md`。收信不受限制；只有发送受限。
- **批量端点完全不支持附件**（见 SKILL.md 第 2 条规则 / `batch-sending.md` 里关于这一点的规范与文档矛盾说明）。

## 数据保留

Resend 在 Free/Pro/Scale 套餐上,对邮件内容、元数据、投递事件和日志的保留期是 **30 天**；Enterprise 可以协商自定义保留期。如果需要 30 天以外的历史数据，文档给出的做法是自己在收到 webhook 事件时就存进自己的数据库——没有 API 能在数据过了保留期之后把它取回来。
