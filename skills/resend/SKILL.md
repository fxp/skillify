---
name: resend
description: "接入 Resend（resend.com/docs，域名 api.resend.com）的交易邮件发送 API 使用手册——涵盖 Bearer token 鉴权、POST /emails（from/to/subject/html/text、附件、抄送/密送、定时发送）、POST /emails/batch（每次最多 100 封）、域名验证（SPF/DKIM/DMARC——未验证域名直接硬失败，没有静默降级）、React Email/HTML 模板、webhook 的送达/退信/投诉通知（svix 签名，需显式订阅事件）、以及速率限制/配额（每团队 10 req/s，免费层额度很低）。SDK：Node 用 `resend`（npm）、Python 用 `resend`（pip）。当用户提到 Resend、resend.com、api.resend.com、`RESEND_API_KEY`、`resend` 包，或要写代码发交易邮件时应主动使用本技能——不要凭记忆或套用其他邮件 API（SendGrid、SES、Postmark）的经验编字段名或失败模式，Resend 的细节不同，而且更新很快。"
---

# Resend —— 面向 AI Agent 的交易邮件 API

Resend 是一套围绕一个核心动作构建的交易邮件 API —— `POST /emails` —— 再加上域名验证、批量发送、模板、webhook，以及一层**本 skill 不覆盖**的营销功能（Broadcasts/Contacts/Automations，见下文"本 skill 不覆盖"）。这一页负责导航和陈述跨领域的通用规则；字段级细节和代码示例都在 `references/` 里。

## ⚠ 验证状态 —— 先读这个

**本 skill 里的任何内容都没有用真实 Resend API key 验证过。** 它只完成了 `create-doc-skill` 方法论的第 1—2 步（抓取真实的当前文档、做结构化整理）——第 3 步（真实 API 验证）和第 4 步（有/无 skill 对照实验）都被明确跳过了，因为撰写时（2026-09-21）没有可用的 API key。

- 下面的每一条事实性陈述——每个字段名、状态码、错误字符串、限额、默认值——都是 `⚠ 文档原文，未实测`：取自 Resend 的在线文档（`resend.com/docs`）以及官方 OpenAPI 规范（`resend.com/openapi.json`，规范版本 1.5.0），抓取于 2026-09-21。没有一条被真实 HTTP 响应确认过。
- 这里的任何代码示例都没有真正跑过。把每一个"预期响应"当作文档引用，而不是实测结果。
- `evals/evals.json` 里的场景是根据文档推演出来的、看起来合理的"坑"（有几条直接来自文档里记录的失败模式——比如 Resend 文档自己给出的、未验证域名返回的 403 错误原文），并没有在真实账号上验证过。
- 一旦拿到真实的 `RESEND_API_KEY`，在把本 skill 用于生产之前，先过一遍 `../resend-workspace/verification-plan.md`，并按照 `create-doc-skill/references/verify.md` 的做法，把每一处 `⚠` 标记原地更新为验证日期和证据。

## 用之前先确认 7 件事

1. **Base URL**：`https://api.resend.com`。只支持 HTTPS —— API 不接受明文 HTTP。⚠ 文档原文，未实测。
2. **鉴权**：请求头 `Authorization: Bearer re_xxxxxxxxx`。key 必须以 `re_` 开头。在 `https://resend.com/api-keys` 获取。⚠ 文档原文，未实测。
3. **每一次直接的 HTTP 请求都必须带 `User-Agent` 请求头**（不只是鉴权相关）。官方 SDK 和 CLI 会自动带上这个头，但一个没带它的原生 `curl`/`requests` 调用会被拒绝，返回 `403`、错误码 `1010`——即使用的是完全有效的 API key 也一样。这是最常见的"我的 key 明明是对的为什么被 403"陷阱。⚠ 文档原文，未实测（文档：`/docs/knowledge-base/403-error-1010`）。
4. **包名**：Node.js —— `npm install resend`（导入 `{ Resend }`，**不是** `@resend/node` 或任何带作用域的名字）；Python —— `pip install resend`（`import resend`，异步客户端用 `pip install resend[async]`）。这两个是这两门语言**唯一**的官方第一方 SDK；Resend 还提供 PHP、Ruby、Go、Java、Rust、.NET，以及一个 Laravel 桥接包。⚠ 文档原文，未实测。
5. **Node 和 Python 两个 SDK 的错误处理方式是相反的——不要把两边的错误处理代码互相照搬。** Node 的 `resend.emails.send()` 对于 API 层面的错误**永远不会抛异常**；它会 resolve 成 `{ data, error }`，你得自己检查 `error`。Python 的 `resend.Emails.send()` 正好相反：任何 API 失败都会**抛出** `resend.exceptions.ResendError`（或其子类，比如 `RateLimitError`/`ValidationError`），成功时直接返回响应对象本身——没有 `{data, error}` 这种元组结构。用 `try/catch` 包住 Node 调用、指望能在 catch 块里抓到 API 错误的代码，会永远进不了 catch 块；检查 Python 返回值里有没有 `error` 键的代码，在第一次真实报错发生时就会因为 `AttributeError` 崩溃，因为异常早就沿着调用栈往上抛出去了，根本走不到那一行。⚠ 文档原文，未实测。
6. **从未验证的自定义域名发信会直接硬失败——不会静默降级成共享/测试域名。** Resend 自己的错误码参考文档记录了确切的响应：`403`，error type 为 `validation_error`，消息是 `` The `domain.com` domain is not verified. Please, add and verify your domain. ``（域名**已验证但不匹配**的情况另有一条措辞不同的 403）。没有静默降级到 Resend 自有地址这回事——对未验证域名发起的请求就是发不出去。见 `references/domain-verification.md`。⚠ 文档原文，未实测。
7. **测试域名 `onboarding@resend.dev` 只能发给你自己 Resend 账号绑定的邮箱地址。** 从 `resend.dev` 发给任何其他收件人都会返回 `403 validation_error`：`` You can only send testing emails to your own email address... ``。它不是一个通用的沙箱发件人。⚠ 文档原文，未实测。

## 30 秒跑通第一个请求

```bash
curl -X POST 'https://api.resend.com/emails' \
  -H "Authorization: Bearer $RESEND_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "from": "Acme <onboarding@resend.dev>",
    "to": ["delivered@resend.dev"],
    "subject": "hello world",
    "html": "<p>it works!</p>"
  }'
```

```python
import os, resend
from resend.exceptions import ResendError

resend.api_key = os.environ["RESEND_API_KEY"]

try:
    email = resend.Emails.send({
        "from": "Acme <onboarding@resend.dev>",
        "to": ["delivered@resend.dev"],
        "subject": "hello world",
        "html": "<p>it works!</p>",
    })
    print(email)  # {'id': '...'}
except ResendError as error:
    print(error)
```

预期返回 `{"id": "<uuid>"}`。`delivered@resend.dev` 是 Resend 提供的测试地址，永远模拟发送成功——可以反复调用而不损害你自己域名的信誉，而且它是未验证的测试发件人 `onboarding@resend.dev` 能发到的少数几个收件人之一（另一个是你账号自己的邮箱）。测试邮件依然会计入你账号的发送配额。⚠ 文档原文，未实测。

## 我要做什么 → 读哪一份

| 我想做什么 | 读 | 核心 endpoint |
|---|---|---|
| 发一封交易邮件——收件人、HTML/纯文本正文、附件、抄送/密送、自定义请求头、定时发送、幂等性 | `references/sending-emails.md` | `POST /emails`、`PATCH /emails/{id}`、`POST /emails/{id}/cancel`、`GET /emails/{id}` |
| 一次调用发出多达 100 封各不相同的邮件（收件人/内容各不同） | `references/batch-sending.md` | `POST /emails/batch` |
| 让一个自定义域名能发信——SPF/DKIM/DMARC 的 DNS 记录、验证状态、地区、跟踪 | `references/domain-verification.md` | `POST /domains`、`POST /domains/{id}/verify`、`GET /domains/{id}` |
| 构建邮件正文——纯 HTML/纯文本 vs Resend 托管 Templates vs React Email 组件 | `references/templates-and-react-email.md` | `POST /templates`、`POST /emails` 上的 `template` 字段 |
| 近实时获知送达、退信、投诉、打开/点击，或域名/联系人/抑制名单事件 | `references/webhooks.md` | `POST /webhooks`、`email.*` / `domain.*` / `suppression.*` 事件类型 |
| 处理错误响应、在触发限流/发送配额/附件限制之前先了解它们 | `references/errors-and-limits.md` | （跨领域内容：错误结构、`429` 行为、配额） |

**本 skill 不覆盖**（在 OpenAPI 规范和 `resend.com/docs` 里都存在，但按本 skill 的任务范围不覆盖——如需请直接查文档）：**Broadcasts**（营销批量发送活动，`POST /broadcasts`）、**Contacts/Segments/Topics/Contact Properties**（Resend 的营销受众层）、**Automations/Events**（由自定义事件触发的工作流构建器）、**收信 / inbound**（`GET /emails/receiving`、转发、原线程回复）、**抑制名单管理 API**（`/suppressions/*`——抑制相关的 *webhook 事件* 因为关系到退信/投诉可送达性的坑，收录在 `references/webhooks.md` 里，但增删改查端点本身不覆盖）、**OAuth client 注册**，以及 **Logs**。以上这些都在同一个账号下、共享同一套 Bearer token 鉴权。

## 跨领域的通用规则（写代码前必读）

这些是最容易让一个凭通用邮件 API 直觉、或者套用其他厂商（SendGrid、SES、Mailgun、Postmark）习惯的开发者踩坑的地方。除非另有说明，全部是 `⚠ 文档原文，未实测`。

1. **未验证/不匹配的发信域名 = 硬 403，不是静默降级。** 见上面第 6 条。如果一个 agent 把这种情况当成"某种通用发送失败"盲目重试，会永远原样失败下去；正确的修复方式是做域名验证，不是重试逻辑。完整 DNS 配置见 `references/domain-verification.md`。
2. **OpenAPI 规范和文字文档在"批量发送能不能带附件"这件事上互相矛盾——以文字文档为准。** `POST /emails/batch` 的 OpenAPI schema 直接复用了单封发送 `POST /emails` 同一个 `SendEmailRequest` 对象，这个共享 schema 里包含 `attachments` 字段，规范本身没有标注任何批量场景下的限制。但**两个独立的文字文档页面**（`/docs/dashboard/emails/attachments` 和 `/docs/dashboard/emails/batch-sending`）都明确写着批量端点不支持附件（"We currently do not support sending attachments when using our batch endpoint"）。这是一处真实的"规范 vs 文档"自相矛盾——在验证之前，假定这条被重复了两次、更具体的文字限制是对的，不要依赖规范 schema 表面上的宽松。⚠ 文档自相矛盾 —— 已标记为优先验证项。
3. **退信/投诉的 webhook 通知是"选配"的；自动抑制发送不是。** 这是两套不同的机制，很容易混为一谈：
   - Resend 会在一次硬退信或一次垃圾邮件投诉之后，**自动**把该地址加进你团队的抑制名单（suppression list），并且**自动跳过**之后对这个地址（跨你所有域名）的发送——无论你有没有创建过任何 webhook，这个机制都会生效。一个从来没碰过 webhook 的 agent，也不会在平台层面持续往一个已经彻底失效的地址发信。
   - 但你的*应用*要想知道某一次具体的退信/投诉事件——从而把地址从你自己的邮件列表里移除、提醒人工、同步到你自己的数据库——只有当你**显式创建了一个 webhook 订阅**，并在它的 `events` 数组里列出 `email.bounced` / `email.complained`（通常还有 `suppression.added`）时才会发生。没有默认/自动的 webhook；`POST /webhooks` 要求你自己传入事件列表。而且不是所有服务商都会上报投诉——Gmail/Google Workspace 就明确不会把 `complained` 事件上报给 Resend，所以只靠 `email.complained` 来监控投诉，会完全漏掉 Gmail 收件人。
   见 `references/webhooks.md` 和 `references/domain-verification.md`（抑制名单一节）。
4. **速率限制是按团队算的，不是按 API key 或按域名算的**，超过之后也没有任何突发（burst）余量。默认 10 请求/秒，账号上的每一个 API key 共享这一个池子——同一团队下两个服务分别以 6 req/s 和 4 req/s 发送，在同一个窗口内会一起撞上 `429`，即便单看任何一个都没超过 10。一个跨多个 key/服务的朴素批量发送循环，如果你以为限流是按 key 算的，会比"10 req/s"这个数字暗示的更快撞上 `429`。批量发送（`POST /emails/batch`，每次最多 100 封）在这个限额里只算**一次**请求——这是官方文档给出的高流量缓解方案，不只是个便利功能。见 `references/errors-and-limits.md`。
5. **免费层的每日邮件配额很低，而且和速率限制是两回事**：每天 100 封，每月 3,000 封，**发出和收到**的邮件都算在里面，在 UTC 午夜重置（不是滚动的 24 小时窗口）。付费套餐取消了每日上限，但保留每月上限，另外还有一个硬性的超量上限——月度配额的 5 倍，超过之后暂停发送直到下一个计费周期。一个没有退避机制的批量发送循环，光靠 10 req/s 这一个速率限制，就能在不到 10 秒内把一个免费账号一整天的额度用光，远早于 429 限流本身成为真正的瓶颈。
6. **`template` 和 `html`/`text`/`react` 互斥。** 在同一个 `POST /emails` 请求体里同时传 `template.id` 和 `html`、`text` 或 `react` 中的任意一个，都会返回校验错误——每次发送只能选一种内容模式。见 `references/templates-and-react-email.md`。
7. **Node 和 Python 的错误处理方式是反的——见上面第 5 条。** 这是代码库混用多语言、或者 agent 把一个 SDK 的模式泛化套到另一个 SDK 上时，最容易引入的 bug。
8. **幂等性 key 是"选配"的，且按端点生效。** 只在 `POST /emails` 和 `POST /emails/batch` 上支持（更新/取消不支持），通过 `Idempotency-Key` HTTP 请求头传递（SDK 里是作为第二个 `options` 参数暴露的，不是请求体里的字段），保留 24 小时，长度 1—256 个字符。不带的话，重试一次失败的发送请求可能会导致重复发送。
9. **一个仅有 `sending_access` 权限的 API key 无法管理域名、webhook 或其他资源**——用受限 key 调用 `POST /emails`/`POST /emails/batch` 以外的任何接口都会返回 `401 restricted_api_key`。如果一个 API key 在创建时可以选配绑定到某一个特定域名，那么用其他域名发送也会失败，即便这个 key 本身是有效的。

## 目录结构

```
resend/
├── SKILL.md
├── references/
│   ├── sending-emails.md            # POST /emails：收件人、正文、附件、请求头、定时发送、幂等性、测试地址
│   ├── batch-sending.md             # POST /emails/batch：每次最多 100 封各不相同的邮件
│   ├── domain-verification.md       # SPF/DKIM/DMARC 的 DNS 配置、验证状态、地区、未验证域名的失败模式、抑制名单
│   ├── templates-and-react-email.md # Resend 托管 Templates API + React Email（简要——库本身的完整文档见 react.email）
│   ├── webhooks.md                  # 送达/退信/投诉/打开/点击事件类型、svix 签名验证、重试
│   └── errors-and-limits.md         # 错误结构、速率限制、配额、附件大小/类型限制、退信/投诉率上限
└── evals/
    └── evals.json                  # 有/无 skill 对照场景草稿（尚未跑过——见 ../resend-workspace/verification-plan.md）
```

内容整理自 `resend.com/docs`（通过其 `llms.txt`/`docs/llms.txt` 索引抓取于 2026-09-21，约 77 个独立页面）以及官方 OpenAPI 规范 `resend.com/openapi.json`（规范版本 1.5.0），并与 Resend 自己面向 AI agent 的内容（`/docs/send-with-nodejs`、`/docs/send-with-python`、`/docs/ai-onboarding`、`/docs/resend-skill`、`/docs/mcp-server`）做了交叉参照（仅作参照，未直接照抄；Resend 自己也发布了一套官方的 `resend/resend-skills` skill 仓库，以及一个托管的 MCP server：`https://mcp.resend.com/mcp`，两者都不在本 skill 的记录范围内）。**没有任何内容经过真实 API 调用验证。** 一旦拿到真实 key，以真实的 API/SDK 行为为准，覆盖这里写的任何内容，并按 `../resend-workspace/verification-plan.md` 更新 `⚠` 标记。
