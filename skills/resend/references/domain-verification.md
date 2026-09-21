# 域名验证（SPF / DKIM / DMARC）

> ⚠ 本文件的全部内容都是 `⚠ 文档原文，未实测`——整理自 `resend.com/docs` 和 `resend.com/openapi.json`（抓取于 2026-09-21），未经真实 API 调用确认。见 SKILL.md 里的验证状态说明。

## 目录

- [为什么这是一个真实的前置条件，而不是 API 细节](#为什么这是一个真实的前置条件而不是-api-细节)
- [跳过它会发生什么——具体的失败模式](#跳过它会发生什么具体的失败模式)
- [添加并验证一个域名 — API](#添加并验证一个域名--api)
- [Resend 生成的 DNS 记录](#resend-生成的-dns-记录)
- [域名和记录的状态值](#域名和记录的状态值)
- [DMARC（推荐，单独的一步）](#dmarc推荐单独的一步)
- [地区](#地区)
- [常见验证失败原因](#常见验证失败原因)
- [抑制名单 — 自动的退信/投诉保护](#抑制名单--自动的退信投诉保护)

## 为什么这是一个真实的前置条件,而不是 API 细节

Resend 是代表**你拥有并控制 DNS 的域名**发信的。"从我自己的域名发信"不是在 API 调用里填一个 `from` 地址那么简单——在这个域名的 DNS 上加上 Resend 生成的确切 TXT/MX/CNAME 记录之前，这个域名根本没法通过 Resend 发出任何东西。这是一个发信 API 本身之外的一次性配置步骤（在你的 DNS 提供商后台完成，不是在 `api.resend.com`），也是第一次集成尝试失败的头号常见原因。一个要"用 support@ourcompany.com 发邮件"的 agent，要么 (a) 先确认域名验证已经做完，要么 (b) 引导人工完成这一步——单靠 API 调用无法自动搞定，因为 agent 本身没有这个域名 DNS 提供商的访问权限。

## 跳过它会发生什么——具体的失败模式

这明确回答了"是直接拒绝还是静默降级"这个问题，依据是 Resend 自己的错误码参考文档（`/docs/api-reference/errors`）：

**从一个从来没添加/验证过的域名发信：**

```
HTTP 403, error type: validation_error
"The `domain.com` domain is not verified. Please, add and verify your domain."
```

**发信用的 `from` 域名字符串和你*已经*验证过的域名不完全匹配**（比如你验证的是 `sending.example.com`，但请求里用的是裸域名 `example.com`，或反过来）：

```
HTTP 403, error type: validation_error
(same error family — domain/subdomain mismatch; see /docs/knowledge-base/403-error-domain-mismatch)
```

**没有静默降级到 Resend 自有地址或共享地址这回事。** 请求就是会以一个 4xx 直接失败，邮件不会被发出——它不会悄悄换成 `onboarding@resend.dev` 或任何其他发件人。把"发送调用返回了错误"当成通用瞬时故障、值得盲目重试的代码，会一直原样重试下去，因为根本原因（域名未验证）不会随着重试次数变化。要把这个特定错误识别出来，作为一个配置问题上报，而不是当成一个投递问题。

**另外**，内置的、零配置就能用的测试域名 `onboarding@resend.dev` 有它自己的限制：它只能发给**你自己 Resend 账号绑定的邮箱地址**，别的都不行：

```
HTTP 403, error type: validation_error
"You can only send testing emails to your own email address (your-email@domain.com).
To send emails to other recipients, please verify a domain at resend.com/domains,
and change the `from` address to an email using this domain."
```

所以"我用 `resend.dev` 发给自己邮箱的快速测试成功了"这件事，完全说明不了真实收件人是否能收到邮件——那只有在域名验证完成之后才有可能。

## 添加并验证一个域名 — API

**Endpoint**：`POST https://api.resend.com/domains`

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `name` | string | **是** | 要验证的（子）域名，比如 `notifications.example.com`。Resend 官方文档**强烈建议用子域名**，而不是根域名——隔离发信信誉，也更能表明用途。 |
| `region` | enum | 否 | `us-east-1`（默认）\| `eu-west-1` \| `sa-east-1` \| `ap-northeast-1`。控制邮件从哪里*路由/发出*，不是账号数据存在哪（见[地区](#地区)）。 |
| `custom_return_path` | string | 否 | Return-Path/退信地址用的子域名。默认是 `send`（即 `send.yourdomain.tld`）。 |
| `open_tracking` / `click_tracking` | boolean | 否 | 开启打开/点击追踪像素和链接重写。 |
| `tls` | enum | 否 | `opportunistic`（默认，收件方不支持 TLS 时降级为未加密发送）\| `enforced`（协商不出 TLS 就**不发送**）。 |
| `capabilities.sending` / `capabilities.receiving` | enum `enabled`\|`disabled` | 否 | 至少要保留一个是开启的。 |

**响应 201** 返回域名对象，**包含需要添加的完整 DNS `records` 数组**（`record` 类型 SPF/DKIM/Receiving/Tracking、`name`、`type` MX/TXT/CNAME、`value`、`ttl`、MX 记录用的 `priority`，以及每条记录自己的 `status`）。

```bash
curl -X POST 'https://api.resend.com/domains' \
  -H "Authorization: Bearer $RESEND_API_KEY" -H 'Content-Type: application/json' \
  -d '{"name": "notifications.example.com", "region": "us-east-1"}'
```

在你的 DNS 提供商那边加好记录之后，触发验证：

**Endpoint**：`POST https://api.resend.com/domains/{domain_id}/verify` —— 触发针对 DKIM、SPF 和跟踪 CNAME（如果配置了的话）的 DNS 重新检查。验证本来就会自动/周期性进行；这个端点是强制立即重新检查一次（在修好一条 DNS 记录之后马上用，不用等下一轮自动检查）。

其他域名相关端点：`GET /domains`（列表）、`GET /domains/{id}`（单个，包含完整 `records` 数组 + 实时状态）、`PATCH /domains/{id}`（更新跟踪/TLS/capabilities）、`DELETE /domains/{id}`。

## Resend 生成的 DNS 记录

具体会出现哪些记录取决于**域名是什么时候添加的**（根据 Resend 自己的排障文档——这个规则在某个时间点变过，所以不要假设旧截图/旧教程和一个新创建的域名一致）：

- **较早创建的域名**：一条 `TXT` 记录和一条 `MX` 记录，两条一起才能让 SPF 验证通过（`send.yourdomain.tld`），另外还有一条单独的 `TXT` 记录用于 DKIM（`resend._domainkey.yourdomain.tld`）。
- **2026 年 8 月前后之后创建的域名**：用 `CNAME` 记录代替 TXT+MX 组合来做 SPF。如果显示了**两条** `CNAME` 记录，每一条各自独立验证——可能一条成功另一条不成功，这种情况下域名会显示 `partially_verified`：**依然能发送，但如果失败的那条是冗余记录，就没有备用发信服务器了**。
- 不管域名创建时间早晚，DKIM 以及任何收信/跟踪相关记录都是单独的条目。

⚠ 文档未说明 一个域名具体按哪种记录方案分配的确切判定标准——把这当成"以 `POST /domains` 响应里实际返回的记录为准"，而不是一个固定的假设。

## 域名和记录的状态值

**单条记录的 `status`**（OpenAPI 规范里记录的枚举）：`pending` · `verified` · `failed` · `temporary_failure` · `not_started`。

**域名整体的 `status`**（`Domain` 对象上这个字段本身）：OpenAPI 规范把它定义成一个裸的 `string` 类型，只给了一个*示例*值（`not_started`），**不是一个正式的枚举**——但文字文档里另外提到 `partially_verified` 是一个真实存在的域名级状态（上面的双 CNAME 场景），并暗示 `verified` 是最终的完全可用状态。⚠ 文档自相矛盾（或者至少是不完整）——规范里域名级状态的枚举，比文字文档描述的要少；把实际观察到的值当作：`not_started`、`pending`、`verified`、`partially_verified`、`failed`、`temporary_failure`，但在拿不同状态的真实账号验证之前，不要假设这份列表是穷尽的。

## DMARC（推荐，单独的一步）

DMARC **不是发信的必需条件**，但是 Resend 文档里推荐的验证完成之后的下一步，对送达率/防伪造有影响。需要 SPF 和/或 DKIM 已经通过（一旦你的域名在 Resend 里验证通过，这个条件会自动满足）。

在 `_dmarc.yourdomain.tld` 加一条 `TXT` 记录：

```
v=DMARC1; p=none; rua=mailto:dmarcreports@yourdomain.tld;
```

- `p`（策略）：`none`（只监控，从这里开始）→ `quarantine`（校验失败就打进垃圾邮件）→ `reject`（校验失败就拒收退回)。文档明确建议先从 `none` 开始，等确认这个域名所有合法发信来源的 DMARC 都能通过之后再收紧——收紧得太早，可能会静默拦截掉你自己其他也以这个域名发信的合法工具（工单系统、营销工具等）的邮件，你都不知道发生了什么。
- `rua`（汇总报告收件地址）可以是任意有效邮箱，包括在另一个域名下的邮箱。
- 一封邮件只需要**SPF 或 DKIM 二者之一**通过（不需要两个都通过）就算符合 DMARC；只有两个都失败才算 DMARC 失败。
- Resend 在 `/docs/dmarc-analyzer` 提供了一个免费的 DMARC 报告解析工具,用来读生成的 `.xml` 报告。

## 地区

创建域名时可以按域名各自选择四个发信地区之一：`us-east-1`（北弗吉尼亚，默认）· `eu-west-1`（爱尔兰）· `sa-east-1`（圣保罗）· `ap-northeast-1`（东京）。这控制的是邮件从**哪里发出**（影响到收件人的延迟），不是你账号/元数据存在哪里——根据 Resend 自己的数据驻留文档，**账号的所有数据（元数据、日志、API 记录）不管选哪个发信地区都统一存在美国**。如果有用户要求 EU 数据驻留、以为选 `eu-west-1` 就够了，这点很关键——除了 SMTP 发送这一跳本身之外，其他都不满足。

修改一个域名的地区：删除后重新添加（没有原地迁移地区这回事），然后重新指向 DNS。

## 常见验证失败原因

来自 Resend 自己的排障指南——适合一个替人工排查"这个域名为什么验证不过"的 agent 参考：

- **被代理的 CNAME 记录**（比如 Cloudflare 的橙色云代理）永远不会按普通 CNAME 解析——必须是仅 DNS/灰色云。
- **同一个子域名上，CNAME 不能和其他记录类型共存**——如果目标子域名已经有 `A`/`TXT`/`MX` 记录，要么删掉它，要么换一个不同的 Return-Path 子域名。
- **有些 DNS 提供商会自动在 MX 值后面追加你的域名**——比如变成 `feedback-smtp.eu-west-1.amazonses.com.example.com`，而不是 `feedback-smtp.eu-west-1.amazonses.com`。解决办法：在你 DNS 提供商那边给这条记录值末尾加一个点，标记它是一个不该被修改的完整限定名。
- **地区不匹配**：MX 记录指向的 AWS 地区和域名配置的 `region` 不一致——验证会报一个 `region-mismatch` 错误。
- **复制粘贴时 DKIM 值被截断/改动**（多了引号/空格，或者不小心把 SPF 信息加进了 DKIM 记录）。
- DNS 传播最长可能要 **72 小时**（通常快得多；往往 15 分钟内就能验证通过）。用"Restart verification"按钮（或 `POST /domains/{id}/verify`）强制重新检查，而不是干等。

## 抑制名单 — 自动的退信/投诉保护

**这在平台层面自动发生，和你有没有配置任何 webhook 无关。** 另见 SKILL.md 跨领域规则第 3 条和 `webhooks.md`。

- 以下三种情况会把一个地址加进你团队的抑制名单：一次**硬退信**（`bounce` 来源）、一次**垃圾邮件投诉**（`complaint` 来源）,或手动添加（`manual` 来源，通过 dashboard/API）。
- 一旦被抑制，Resend 会在之后每一次发送时**自动跳过**这个地址——跨你所有的域名和子域名，对交易邮件和 Broadcast 发送都生效,你这边不需要写任何代码。
- 把一个地址从抑制名单移除,**不保证**之后一定能送达；如果它再次退信/投诉，会被自动重新加入抑制名单。
- 不是所有服务商都会向 Resend 上报投诉——**Gmail/Google Workspace 明确不会发送 `complained` 事件**，所以基于垃圾邮件投诉的抑制机制，对 Gmail 收件人不会像对会上报投诉的服务商那样生效。
- `suppression.added`/`suppression.removed` 这两个 webhook 事件是为了**让你自己能看到**（同步你自己的邮件列表/数据库）——平台层面"跳过被抑制地址"这个行为本身不依赖它们，那是自动生效的。
- 所有账号还必须额外维持**退信率低于 4%**、**投诉率低于 0.08%**（见 `errors-and-limits.md`）——超出任何一项，都可能导致账号级别的发送暂停,直到指标恢复,这和逐地址的抑制机制是相互独立的两套东西。
