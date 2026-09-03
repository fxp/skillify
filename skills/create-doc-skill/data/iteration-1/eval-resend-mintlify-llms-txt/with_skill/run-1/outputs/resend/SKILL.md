---
name: resend
description: 接入 Resend（resend.com，开发者邮件 API；npm 包 `resend`，REST base https://api.resend.com）的使用手册——涵盖发送/批量/定时邮件与附件、幂等重试、域名与 API key、Webhooks 签名验证与收件（inbound）、联系人/分段/主题/退订/Broadcasts、模板/自动化/自定义事件、错误码与限额。当用户提到 "Resend""resend.com""resend.dev""import { Resend }""RESEND_API_KEY""用 Resend 发邮件/收邮件/webhook"，或要求写调用上述任意能力的代码时，务必先读本技能，不要凭记忆或套 SendGrid/Mailgun/SES 的参数习惯。不适用于：SMTP 通用配置、React Email 组件排版本身（那是 react-email 技能）。
---

# Resend 接入指南

Resend 是面向开发者的邮件 API：单发/批量/定时发送、收件（inbound）、Webhooks、域名与 DKIM 管理，以及营销侧的联系人 / 分段 / Broadcasts / 模板 / 自动化。本技能的目标是让你**第一次就写对**调用代码，示例全部为 TypeScript（官方 SDK `resend` 优先，附 `fetch` 裸 HTTP 版）。

## ⚠ 验证状态（先读）

**本技能全部内容尚未用真实 API key 调用验证。** 内容来源：
- OpenAPI 规范 `resend/resend-openapi` `resend.json` v1.5.1（108 个 endpoint，`https://raw.githubusercontent.com/resend/resend-openapi/main/resend.json`）——字段名、必填、枚举以它为准；
- 文档站 https://resend.com/docs（`llms-full.txt`，抓取于 2026-09）——限制数字、行为说明、SDK 写法。

规范与页面互相矛盾、或页面没写清的地方在各 reference 里以 `⚠` 标出；真实调用的待验证清单见同级的 `verification-plan.md`。**实际报错以 API 为准**——拿到 key 后先按验证计划跑一遍再信任本文件中的"限制数字"。

## 用之前先确认 3 件事

1. **Base URL 固定 `https://api.resend.com`**，无版本前缀（`POST /emails`，不是 `/v1/emails`）。只支持 HTTPS。
2. **鉴权 header 精确写法：`Authorization: Bearer <RESEND_API_KEY>`**（来源：OpenAPI `securitySchemes.bearerAuth = {type: http, scheme: bearer}`，全局生效；key 以 `re_` 开头）。**第二个必需 header：`User-Agent`**——文档明确缺它会被 403（错误码 1010）拒绝，SDK/curl 自带，用 `fetch` 必须手动加。
3. **最容易选错的字段：`from` 的域名。** 未验证域名只能用 `onboarding@resend.dev` 发给你自己账号的邮箱，发给别人返回 403 `validation_error`。生产必须先在 /domains 验证域名，`from` 用该域名（推荐子域名如 `notifications.example.com`）。API key 分 `full_access` / `sending_access` 两种，后者调发信以外接口报 `restricted_api_key`。

## 30 秒跑通第一个请求

```bash
curl -X POST https://api.resend.com/emails \
  -H "Authorization: Bearer $RESEND_API_KEY" \
  -H "User-Agent: my-app/1.0" \
  -H "Content-Type: application/json" \
  -d '{"from":"Acme <onboarding@resend.dev>","to":["delivered@resend.dev"],"subject":"hello","html":"<p>it works</p>"}'
# 成功: {"id":"<uuid>"}
```

```ts
import { Resend } from 'resend';                       // 包名就是 resend，不是 @resend/node
const resend = new Resend(process.env.RESEND_API_KEY);

const { data, error } = await resend.emails.send({
  from: 'Acme <onboarding@resend.dev>',                // 测试用；生产换成已验证域名
  to: ['delivered@resend.dev'],                        // 官方测试收件地址，不会伤害信誉
  subject: 'hello',
  html: '<p>it works</p>',
});
if (error) { console.error(error.name, error.message); return; }  // SDK 不抛异常，返回 { data, error }
console.log(data.id);
```

测试收件地址：`delivered@` / `bounced@` / `complained@` / `suppressed@resend.dev`，分别模拟对应事件。

## 能力域导航

| 我想做什么 | 读这个文件 | 核心 endpoint |
|---|---|---|
| 发一封 / 批量发 / 定时发邮件，带附件、内嵌图片、tags、自定义 header，用模板或 React 组件，重试不重复发 | `references/sending.md` | `POST /emails`、`POST /emails/batch`、`GET /emails/{id}`、`PATCH /emails/{id}`、`POST /emails/{id}/cancel`、`GET /emails/metrics` |
| 添加/验证域名、拿 DNS 记录、开关打开/点击追踪、创建/限定 API key、多租户 | `references/domains-and-api-keys.md` | `POST /domains`、`POST /domains/{id}/verify`、`PATCH /domains/{id}`、`POST /api-keys` |
| 接收 Webhook（送达/退信/投诉/打开/点击…）并验证签名；接收 inbound 邮件并读正文附件 | `references/webhooks-and-receiving.md` | `POST /webhooks`、`GET /webhooks/{id}/events`、`GET /emails/receiving/{id}`、`GET /emails/receiving/{id}/attachments/{aid}` |
| 管理联系人 / 属性 / 分段 / 主题订阅 / 退订与抑制列表，发 Broadcast（newsletter） | `references/audiences-and-broadcasts.md` | `POST /contacts`、`POST /segments`、`POST /topics`、`POST /suppressions`、`POST /broadcasts`、`POST /broadcasts/{id}/send` |
| 建模板并用 `template.id + variables` 发送；自动化流程；自定义事件触发；查请求日志 | `references/templates-automations-events.md` | `POST /templates`、`POST /templates/{id}/publish`、`POST /automations`、`POST /events/send`、`GET /logs` |
| 错误码含义、429/配额、分页、重试策略、裸 HTTP 封装 | `references/errors-and-limits.md` | — |

## 跨领域通用规则（写代码前必读）

1. **三个 header 缺一不可（裸 HTTP）**：`Authorization: Bearer …`、`User-Agent`、`Content-Type: application/json`。"key 明明对却 403" 十有八九是缺 `User-Agent`。
2. **REST 用 snake_case，Node SDK 用 camelCase**：`reply_to`/`scheduled_at`/`content_type` ↔ `replyTo`/`scheduledAt`/`contentType`。用 SDK 时写 snake_case 会被静默忽略（⚠ 待验证是忽略还是报错），这是最隐蔽的坑。
3. **SDK 返回 `{ data, error }`，不 throw**。`try/catch` 抓不到业务错误；必须检查 `error`。裸 HTTP 的错误体是 `{ statusCode, name, message }`。
4. **重试发信必须带 `Idempotency-Key` header**（1–256 字符，24h 内有效，仅 `POST /emails` 与 `POST /emails/batch` 支持）。同 key 不同 body → 409 `invalid_idempotent_request`。SDK 里它是 `send()` 的**第二个参数** `{ idempotencyKey }`（⚠ 文档自相矛盾：Node 快速开始页把它写在第一个参数对象里，以 `sending.md` 的记录为准，验证计划第 1 项）。
5. **批量 `POST /emails/batch` 最多 100 封、每封 `to` 最多 50 个地址、不支持附件**（api-reference、batch-sending、ai-onboarding 三处一致）。`scheduled_at` 在 batch 元素里能否用是文档自相矛盾（OpenAPI、schedule-email、send-batch-emails 说可以，ai-onboarding 说不行）；失败语义也自相矛盾（"每封独立处理" vs "任一封失败整批失败"）——⚠ 验证计划 P2。需要附件就用单发；用了 batch 就对每封 id 做逐条核对。
6. **默认速率 10 req/s/team**（所有 key 共享），429 时按 `retry-after` 头退避；100 封用一次 batch 比并发 100 次单发省 99 次配额。
7. **`html`/`text`/`react` 与 `template` 互斥**；`react` 只在 Node SDK 存在，且要传函数调用 `Welcome({name})` 而不是 JSX。
8. **分页是 cursor 式**：`limit`(1–100，默认 20) + `after` **或** `before`（二选一），cursor 是对象 `id`，响应 `{object:"list", has_more, data}`。老 list 接口不传 `limit` 会一次返回全部。
9. **域名验证是 DNS 操作，Agent 做不完**：`POST /domains` 返回要加的 DNS 记录，人去 DNS 商加完再 `POST /domains/{id}/verify`；状态字段轮询见 `domains-and-api-keys.md`。
10. **Webhook 签名用 Svix 规范 header 验证，必须用 raw body**（框架自动 JSON parse 后签名必失败）；事件类型拼写以 `webhooks-and-receiving.md` 的枚举表为准（`email.bounced` 不是 `email.bounce`）。
11. **没有 API 版本头**（文档 FAQ 明说），不要自作主张加 `Resend-Version` 之类。
12. **收件（inbound）也计入发信配额**；免费计划有日配额（响应头 `x-resend-daily-quota`）。
13. **营销侧对象模型已变**：Audiences 已 deprecated（用 Segments），联系人是团队级的 `POST /contacts`（不是 `/audiences/{id}/contacts`）；newsletter 走 Broadcasts（创建 → `POST /broadcasts/{id}/send` 两步），正文合并变量是三花括号加 `contact.` 前缀（`{{{contact.first_name|there}}}`）与 `{{{RESEND_UNSUBSCRIBE_URL}}}`，大写 `{{{FIRST_NAME}}}` 写法在文档里不存在。
14. **两处文档自相矛盾、写代码时显式传参绕开**：CSV 导入 `POST /contacts/imports` 的 `on_conflict` 默认值 OpenAPI 说 `skip`、页面说 `upsert`——永远显式传；模板 `variables[].type` 页面只列 `string|number`、OpenAPI 多 `boolean|object|list`——先只用前两种。模板必须 `publish` 后才能用于发送，改完要再 publish。

## 目录结构

```
resend/
├── SKILL.md                              # 本文件：路由 + 通用规则
├── references/
│   ├── sending.md                        # 发送 / 批量 / 定时 / 附件 / 幂等 / 已发邮件管理
│   ├── domains-and-api-keys.md           # 域名、DNS、追踪开关、API key 权限
│   ├── webhooks-and-receiving.md         # Webhook 事件、签名验证、inbound 收件
│   ├── audiences-and-broadcasts.md       # 联系人 / 分段 / 主题 / 抑制 / Broadcasts
│   ├── templates-automations-events.md   # 模板 / 自动化 / 自定义事件 / 日志
│   └── errors-and-limits.md              # 错误码、限额、分页、重试
└── evals/evals.json                      # 对照评测场景（打包时排除）
```

内容整理自 https://resend.com/docs 与 resend/resend-openapi v1.5.1（抓取于 2026-09），**未经真实调用验证**；实际调用报错优先信任 API，并把发现回写到对应 reference（带日期与报错原文）。
