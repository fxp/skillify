# Resend · Webhooks 与收件（Receiving / Inbound）

> **⚠ 验证状态：本文件全部内容为 OpenAPI 规范（resend/resend-openapi v1.5.1）与 https://resend.com/docs 页面的转录（抓取于 2026-09），尚未用真实 API key 调用验证。实际报错以 API 为准；未验证细节以 ⚠ 标出。**

## 目录

1. [先选路线：Webhook 推送 vs 主动轮询](#1-先选路线webhook-推送-vs-主动轮询)
2. [我想订阅事件：Webhook CRUD](#2-我想订阅事件webhook-crud)
3. [事件类型完整枚举](#3-事件类型完整枚举)
4. [事件 payload 结构](#4-事件-payload-结构)
5. [我想验证签名](#5-我想验证签名)
6. [重试、去重、顺序、Replay](#6-重试去重顺序replay)
7. [我想排查某个 webhook 的投递：events / attempts 查询接口](#7-我想排查某个-webhook-的投递events--attempts-查询接口)
8. [我想收邮件：开启 Receiving](#8-我想收邮件开启-receiving)
9. [收件 webhook `email.received` 与读取正文/附件](#9-收件-webhook-emailreceived-与读取正文附件)
10. [我想回复 / 转发收到的邮件](#10-我想回复--转发收到的邮件)
11. [⚠ 汇总](#11--汇总)

通用约定见 `auth.md`：Base URL `https://api.resend.com`，`Authorization: Bearer <RESEND_API_KEY>`，裸 `fetch` 必须带 `User-Agent`（缺失 403 / 错误码 1010）；本文件接口需 `full_access` key（`sending_access` 返回 401 `restricted_api_key`）。REST 字段 snake_case，Node SDK camelCase。

## 1. 先选路线：Webhook 推送 vs 主动轮询

| 需求 | 用什么 | 说明 |
|---|---|---|
| 邮件状态变化实时通知（送达/退信/打开/点击…） | Webhook（`email.*` 事件） | 至少一次投递、乱序可能，需按 `svix-id` 去重 |
| 收到邮件时触发处理 | Webhook `email.received` + `GET /emails/receiving/{id}` | webhook 里**没有正文和附件内容**，只有元数据 |
| 无公网端点 / 批处理 | 轮询 `GET /emails/receiving`（列表）或 CLI `resend emails receiving` | 文档提到 CLI 可在终端流式显示新收件 |
| 补漏、离线回放 | Dashboard Replay + `GET /webhooks/{id}/events` | 目前 ⚠ 无 replay API，只有 Dashboard 按钮 |
| 长期留存事件 | 官方 Webhook Ingester（开源 Next.js 应用） | Resend 只保留 30 天邮件数据（how-to-store 页） |

出口 IP（需白名单时）：`44.228.126.217`、`50.112.21.217`、`52.24.126.164`、`54.148.139.208`、`2600:1f24:64:8000::/52`。本地调试用 ngrok 或 Resend CLI `webhooks listen`。

## 2. 我想订阅事件：Webhook CRUD

### 创建 Webhook（主力）

**Endpoint**: `POST /webhooks`
**用途**: 注册一个 HTTPS 端点并选择订阅的事件；**只有这个响应会返回 `signing_secret`，请立刻存起来**（get/list 也返回，但 Dashboard 里也能查看）。

**关键参数**（REST 字段名；Node SDK 用 camelCase，此处两个字段都是单词无差异）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `endpoint` | string | 是 | — | 公网可达的 HTTPS URL |
| `events` | string[] | 是 | — | 事件类型数组，取值见第 3 节；⚠ OpenAPI 未给枚举，文档示例里的取值形如 `"email.sent"`、`"email.received"` |

**示例**（SDK）：

```ts
import { Resend } from 'resend';
const resend = new Resend(process.env.RESEND_API_KEY);

const { data, error } = await resend.webhooks.create({
  endpoint: 'https://example.com/api/resend-webhook',
  events: ['email.sent', 'email.delivered', 'email.bounced', 'email.complained'],
});
// data.signing_secret 在此拿到后写入密钥管理
```

**示例**（fetch，底层 `POST /webhooks`）：

```ts
const res = await fetch('https://api.resend.com/webhooks', {
  method: 'POST',
  headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
             'Content-Type': 'application/json', 'User-Agent': 'my-app/1.0' },
  body: JSON.stringify({ endpoint: 'https://example.com/api/resend-webhook', events: ['email.received'] }),
});
const body = await res.json(); // 201: { object, id, signing_secret }
```

**示例响应**（201）：`{ "object": "webhook", "id": "<uuid>", "signing_secret": "whsec_…" }`

**注意事项**：
- `signing_secret` 以 `whsec_` 开头（docs 示例与 Ingester 环境变量说明一致）。不要把它写进代码，放 `RESEND_WEBHOOK_SECRET` 环境变量。
- 新建 webhook 的 `status` 文档未提及默认值；get 示例里为 `"enabled"` ⚠ 文档未说明默认值。

### 更新 Webhook

**Endpoint**: `PATCH /webhooks/{webhook_id}`
**用途**: 改 URL、改事件集合、启用/禁用（禁用后所有投递尝试也停止）。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `endpoint` | string | 否 | — | 新 URL |
| `events` | string[] | 否 | — | 整组替换（⚠ 文档未说明是否为增量合并，按示例看是整组传入） |
| `status` | string | 否 | — | 枚举 `enabled` / `disabled` |

SDK：`resend.webhooks.update(webhookId, { endpoint, events, status })`，响应 `{ object:'webhook', id }`。

### 查询 / 列表 / 删除

| 功能 | Endpoint | SDK | 响应要点 |
|---|---|---|---|
| 单个 | `GET /webhooks/{webhook_id}` | `resend.webhooks.get(id)` | `id, endpoint, events[], status, created_at, signing_secret` |
| 列表 | `GET /webhooks?limit&after\|before` | `resend.webhooks.list()` | `{ object:'list', has_more, data:[…] }`；OpenAPI 的 `data[]` **不含** `signing_secret`，但 verify 页说 list 也会返回 ⚠ 文档自相矛盾 |
| 删除 | `DELETE /webhooks/{webhook_id}` | `resend.webhooks.remove(id)` | `{ object:'webhook', id, deleted:true }` |

`created_at` 在 webhook 对象里的示例格式是 `"2026-08-22 15:28:00.000+00"`（非 ISO 8601 的 `T`/`Z` 形式），与事件里的 ISO 格式不同，解析时别写死格式 ⚠ 仅来自文档示例。

## 3. 事件类型完整枚举

`events` 数组的取值（docs event-types 页，共 19 个）：

| 分组 | 取值 | 触发时机 |
|---|---|---|
| Email | `email.sent` | API 请求成功，Resend 开始尝试投递 |
| | `email.delivered` | 已交付到收件方邮件服务器 |
| | `email.delivery_delayed` | 临时问题（收件箱满、对方服务器瞬时故障） |
| | `email.bounced` | 收件方**永久**拒收 |
| | `email.complained` | 已送达但被标记为垃圾邮件 |
| | `email.opened` | 打开（需开启 open tracking；文档提示 open rate 不一定准确） |
| | `email.clicked` | 点击链接（需开启 click tracking） |
| | `email.failed` | 发送失败（无效收件人、key 问题、域名未验证、配额等） |
| | `email.scheduled` | 使用 `scheduled_at` 定时发送时 |
| | `email.suppressed` | Resend 因抑制名单未发送 |
| | `email.received` | **收件**：Resend 收到一封发给你域名的邮件 |
| Domain | `domain.created` / `domain.updated` / `domain.deleted` | 域名增改删（含验证状态变化） |
| Contact | `contact.created` / `contact.updated` / `contact.deleted` | 联系人增改删；**CSV 批量导入不触发** `contact.created` |
| Suppression | `suppression.added` / `suppression.removed` | 抑制名单增删（自动：硬退信/投诉；手动：Dashboard/API） |

注意拼写：是 `email.delivery_delayed`（下划线），不是 `email.delayed`；退信是 `email.bounced` 不是 `email.bounce`。

## 4. 事件 payload 结构

所有事件的顶层结构固定：

```json
{ "type": "<事件类型>", "created_at": "<ISO 8601, 事件产生时间>", "data": { … } }
```

`data.created_at` 是**对象**（邮件/联系人/域名）的创建时间，与顶层 `created_at`（事件时间）不同；乱序排序时用顶层 `created_at`。

### `email.*` 的 `data` 公共字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `email_id` | string | 邮件 ID，可用于 `GET /emails/{id}` 或（收件）`GET /emails/receiving/{id}` |
| `message_id` | string | RFC `Message-ID` 头，形如 `<…@…>`，回复串线程时用 |
| `from` | string | 发送事件：与发送时一致，可含显示名 `Name <a@b.c>`；**`email.received` 里是裸地址**，显示名在 retrieve 接口的 `headers.from` |
| `to` | string[] | 受影响的收件人 |
| `subject` | string | 主题 |
| `created_at` | string | 邮件创建时间 |
| `broadcast_id` | string | 若来自 Broadcast |
| `template_id` | string | 若使用了模板 |
| `tags` | Record<string,string> | 发送时传的 tags，**是对象**（`{"category":"welcome"}`），不是 `[{name,value}]` 数组 ⚠ 与 `POST /emails` 请求体里 tags 的数组形式不同，仅按 webhook 文档示例记录 |

`data` 里**没有** `headers`、`html`、`text`（发送事件和收件事件都没有）。

### 各事件的附加子对象

| 事件 | 附加字段 | 子字段（注意是 camelCase） |
|---|---|---|
| `email.bounced` | `bounce` | `message`(string)、`type`（如 `Permanent` / `Temporary`）、`subType`（如 `Suppressed`、`MessageRejected`）、`diagnosticCodes`? ⚠ 文档参数表描述了"SMTP diagnostic responses 数组"但示例 JSON 未出现该字段，字段名未给出 |
| `email.clicked` | `click` | `ipAddress`、`link`、`timestamp`、`userAgent` |
| `email.failed` | `failed` | `reason`（如 `reached_daily_quota`） |
| `email.suppressed` | `suppressed` | `message`、`type`（示例 `OnAccountSuppressionList`） |
| `email.received` | `bcc[]`、`cc[]`、`received_for[]`、`attachments[]` | `attachments[]`: `id, filename, content_type, content_disposition, content_id`（**无 `size`、无内容**） |

### 非邮件事件的 `data`

- `contact.*`：`id, audience_id, segment_ids[], created_at, updated_at, email, first_name|null, last_name|null, unsubscribed`。
- `domain.*`：`id, name, status, created_at, region, capabilities{ sending, receiving }, records[]`。`status` 枚举 `verified | partially_verified | partially_failed | failed | pending | not_started`（发/收双能力域名可能出现 partially_*）；`capabilities.*` 为 `enabled | disabled`；`records[].record` 为 `SPF | DKIM | Receiving MX | Tracking`。
- `suppression.*`：`id, email, origin`（`bounce | complaint | manual`）、`source_id`（触发抑制的邮件 ID；`manual` 时为 `null`）、`created_at`。

## 5. 我想验证签名

Resend webhook 由 Svix 基础设施签名。要点：

| 项 | 值 |
|---|---|
| 请求头 | `svix-id`（投递唯一 ID，也用于去重）、`svix-timestamp`、`svix-signature`（形如 `v1,<base64>`） |
| Secret | webhook 的 `signing_secret`，`whsec_` 前缀；来源：`POST /webhooks` 响应、`GET /webhooks/{id}`、Dashboard webhook 详情页 |
| 库 | Node SDK 内置 `resend.webhooks.verify(...)`；或直接 `npm install svix` 用 `new Webhook(secret).verify(rawBody, headers)` |
| 输入 | **必须是原始请求体字符串**。任何框架先 `JSON.parse` 再 `JSON.stringify` 都会改变字节序列导致签名失败 |

⚠ 头名是 `svix-*`，**不是** `resend-signature` 之类；docs 中没有任何 `resend-*` 签名头。

### 用 SDK 验证（Next.js App Router）

```ts
import { NextRequest, NextResponse } from 'next/server';
import { Resend } from 'resend';
const resend = new Resend(process.env.RESEND_API_KEY);

export async function POST(req: NextRequest) {
  const payload = await req.text(); // 原始 body，不要 req.json()
  const id = req.headers.get('svix-id');
  const timestamp = req.headers.get('svix-timestamp');
  const signature = req.headers.get('svix-signature');
  if (!id || !timestamp || !signature) return new NextResponse('Missing headers', { status: 400 });

  let event;
  try {   // 校验失败抛错；成功返回已解析的 payload 对象
    event = resend.webhooks.verify({ payload, headers: { id, timestamp, signature },
                                     webhookSecret: process.env.RESEND_WEBHOOK_SECRET! });
  } catch { return new NextResponse('Invalid webhook', { status: 400 }); }
  if (event.type === 'email.bounced') { /* … */ }
  return NextResponse.json({ ok: true }); // 必须 200，否则会重试
}
```

⚠ 文档自相矛盾：verify 页与 forward KB 页的 `resend.webhooks.verify` 参数名是 `webhookSecret`，而 agent-email-inbox 页示例用的是 `secret`；且 verify 页示例用 `req.headers['svix-id']` 读取 NextRequest 头（在 App Router 里应为 `req.headers.get(...)`）。以 SDK 类型定义为准，本文采用 `webhookSecret` + `headers.get()`。

### 用 svix 库手动验证（Express 示例）

Express 默认 `express.json()` 会把 body 解析成对象，验证必须用 `express.raw()` 拿 Buffer：

```ts
import { Webhook } from 'svix';
app.post('/api/resend-webhook', express.raw({ type: 'application/json' }), (req, res) => {
  const wh = new Webhook(process.env.RESEND_WEBHOOK_SECRET!);
  try {
    const event = wh.verify(req.body.toString('utf8'), {   // 抛错即无效
      'svix-id': req.header('svix-id')!,
      'svix-timestamp': req.header('svix-timestamp')!,
      'svix-signature': req.header('svix-signature')!,
    }) as { type: string; data: any };
    res.sendStatus(200);
  } catch { res.status(400).send('Invalid signature'); }
});
```

svix 还会用 `svix-timestamp` 做时效检查以抵御重放攻击（verify 页只描述了重放风险，⚠ 容忍窗口大小文档未说明）。

## 6. 重试、去重、顺序、Replay

**成功判定**：端点返回 `HTTP 200`（introduction 页原文 "200 OK"；how-to-store 页说 "5xx 会重试"）⚠ 其他 2xx 是否算成功文档未明确，保险起见返回 200。

**重试计划** ⚠ 文档自相矛盾，三处说法不一：

| 来源 | 说法 |
|---|---|
| retries-and-replays 页 | 指数退避：立即、5s、5min、30min、2h、5h、10h、再 10h（共 8 次尝试） |
| introduction 页 FAQ | 5s、5min、30min、2h、5h、10h（6 个间隔） |
| how-to-store 页 FAQ | "自动重试最长 24 小时" |

每个间隔从上一次失败后起算。端点持续失败会先收到邮件通知，继续失败会被**自动禁用**并再次通知；恢复后在 Dashboard 或 `PATCH status: enabled` 重新启用。被删除/禁用的端点不再投递。

**投递语义**：at-least-once；可能重复（如你处理完但 ack 丢失）。去重用 `svix-id`（每次投递唯一）——存已处理的 `svix-id`，重复直接 200 返回。
**顺序**：不保证。`email.opened` 可能先于 `email.delivered` 到达，按顶层 `created_at` 排序。

**Replay**：Dashboard → Webhooks → 选端点 → 选事件 → "Replay"。`failed` 和 `succeeded` 都能重放，用于补数据、用新 handler 重处理、发到别的端点测试。⚠ OpenAPI v1.5.1 无 replay 接口，只能在 Dashboard 操作。

## 7. 我想排查某个 webhook 的投递：events / attempts 查询接口

三个只读接口，都以 `webhook_id` 为前缀；事件 ID 形如 `msg_…`，尝试 ID 形如 `atmpt_…`（非 UUID）。

| 功能 | Endpoint | SDK |
|---|---|---|
| 该 webhook 收到的事件列表（最新在前） | `GET /webhooks/{webhook_id}/events?limit&after` | `resend.webhooks.events.list({ webhookId })` |
| 单个事件（含完整 payload） | `GET /webhooks/{webhook_id}/events/{event_id}` | `resend.webhooks.events.get({ webhookId, eventId })` |
| 该事件的投递尝试列表 | `GET /webhooks/{webhook_id}/events/{event_id}/attempts?limit&after` | `resend.webhooks.events.attempts.list({ webhookId, eventId })` |

分页：`limit` 1–100 默认 20，**只支持 `after`，不支持 `before`**（与其他列表接口不同）。

事件对象字段：`id, type, created_at, status`（枚举 `pending | attempting | success | failed`）；单个事件另有 `next_attempt_at`（下次重试时间，成功或永久失败后为 `null`）和 `payload`（当初发给你的完整 JSON，可用于本地重放）。
尝试对象字段：`id, http_status_code, response`（你端点返回的 body 文本）、`sent_at`。

```ts
const { data: events } = await resend.webhooks.events.list({ webhookId });
for (const e of events?.data.filter((e) => e.status === 'failed') ?? []) {
  const { data: attempts } = await resend.webhooks.events.attempts.list({ webhookId, eventId: e.id });
  console.log(e.type, attempts?.data.map((a) => [a.http_status_code, a.response]));
}
```

## 8. 我想收邮件：开启 Receiving

两种收件地址：

| 方式 | 需要 DNS 吗 | 说明 |
|---|---|---|
| Resend 托管子域 `<id>.resend.app` | 不需要 | Dashboard → Emails → Receiving 标签 → "Receiving address" 查看；发到该子域**任意用户名**都会收到 |
| 自己的已验证域名 | **需要额外加一条 MX 记录** | Domains 页启用 receiving 开关，复制 MX（示例值形如 `inbound-smtp.<region>.amazonaws.com`，priority 10），加到 DNS 后点 "I've added the record" 等 MX 变为 verified |

关键点：
- 收件开在**域名层级**（domain 的 `capabilities.receiving`），一旦开启，该域名下**所有地址**的邮件都由 Resend 接收，按 webhook 的 `to` 字段自行路由。
- 已为发送验证过的域名不用重新验证，只验证 MX 这一条。
- 若根域已有 MX（正在用真实邮箱），**强烈建议用子域**（如 `inbound.example.com`）。邮件只投给优先级数值最低的 MX；Resend 的 MX 不是最低优先级就收不到，同优先级则结果不可预测。替代方案：在现有邮箱服务里设转发规则到 Resend 地址或直接转发到 MX 里的 SMTP 主机。
- `domain.updated` 事件的 `records[]` 会出现 `record: "Receiving MX"` 条目，可据此监控 MX 验证状态。

## 9. 收件 webhook `email.received` 与读取正文/附件

流程：邮件到达 → Resend 解析 → POST `email.received` 到你的端点（**只有元数据**）→ 你调 `GET /emails/receiving/{email_id}` 取正文/头 → 需要附件内容再调 attachments 接口拿签名下载 URL。官方解释：这样设计是为了在 serverless 请求体大小受限的环境也能处理大附件。

`email.received` payload 示例（见第 4 节字段表）：

```json
{ "type": "email.received", "created_at": "…",
  "data": { "email_id": "<uuid>", "created_at": "…", "message_id": "<…@…>",
            "from": "sender@example.com", "to": ["support@inbound.example.com"], "cc": [], "bcc": [],
            "received_for": ["forwarded@example.com"], "subject": "…",
            "attachments": [{ "id": "<uuid>", "filename": "a.png", "content_type": "image/png",
                              "content_disposition": "inline", "content_id": "img001" }] } }
```

⚠ reply-to-emails 页的 `email.received` 示例里 `from` 带显示名（`Acme <…>`），而 received 事件页明确说收件事件的 `from` 是裸地址，显示名在 `headers.from`；文档自相矛盾，以事件页为准并做两种情况兼容。

### 读取一封收到的邮件（主力）

**Endpoint**: `GET /emails/receiving/{email_id}`
**用途**: 取 `html` / `text` / `headers` / `raw` 下载地址与附件元数据。与 `GET /emails/{id}`（发送记录）不同路径，别混用。

| 查询参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `html_format` | `data_uri` \| `cid` | 否 | `data_uri` | 内联图片在 `html` 里的形式：默认转成 base64 `data:` URI；`cid` 保留 `<img src="cid:…">`，可按 `content_id` 对应 `attachments[]` 再下载。⚠ 此参数与响应里的 `html_format`、`raw` 字段只在 docs 页出现，OpenAPI v1.5.1 未收录 |

```ts
const { data: email, error } = await resend.emails.receiving.get(event.data.email_id);
if (error) throw new Error(error.message);
console.log(email.subject, email.html, email.text, email.headers?.from);
```

```ts
// 底层 GET /emails/receiving/{email_id}
const res = await fetch(`https://api.resend.com/emails/receiving/${emailId}?html_format=cid`, {
  headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}`, 'User-Agent': 'my-app/1.0' },
});
```

**示例响应**（关键字段）：

```json
{ "object": "email", "id": "<uuid>", "from": "sender@example.com", "to": ["…"], "subject": "…",
  "html": "…", "html_format": "data_uri", "text": null,
  "headers": { "from": "Acme <sender@example.com>", "return-path": "…", "mime-version": "1.0" },
  "cc": [], "bcc": [], "reply_to": [], "received_for": ["…"], "message_id": "<…>",
  "raw": { "download_url": "https://…?Signature=…", "expires_at": "…" },
  "attachments": [{ "id": "<uuid>", "filename": "…", "content_type": "…", "content_disposition": "inline",
                    "content_id": "img001", "size": 4096 }], "created_at": "…" }
```

**注意事项**：
- `html` / `text` 可能为 `null`（纯文本邮件没有 html，反之亦然）。
- `raw.download_url` 是签名的 CloudFront 地址，可下载原始 RFC 5322 文件（含全部附件），需要精确转发或用 `mailparser` 自己解析时用；`raw` 可能为 `null` ⚠ 何时为 null 文档未说明。
- 403 `email_above_quota`："You can't retrieve this email's content because it was above quota when received"——邮件在收到时已超出套餐配额，正文取不到，需升级套餐。⚠ 收件配额数值、单封收件大小上限文档未说明。
- `received_for[]`：来自 `Received` 头 `for` 子句，邮件是被别的邮箱转发进来时可据此知道原始收件人。

### 列出收到的邮件

**Endpoint**: `GET /emails/receiving?limit&after|before`（cursor 分页，`{object:'list', has_more, data[]}`）；SDK `resend.emails.receiving.list()`。列表项**不含** `html/text/headers`，含 `attachments[]` 元数据（含 `size`）。只返回收到的邮件，发送记录用 `GET /emails`。

### 附件：列出与下载

| 功能 | Endpoint | SDK |
|---|---|---|
| 列出附件（带下载 URL） | `GET /emails/receiving/{email_id}/attachments?limit&after\|before` | `resend.emails.receiving.attachments.list({ emailId })` |
| 单个附件 | `GET /emails/receiving/{email_id}/attachments/{attachment_id}` | `resend.emails.receiving.attachments.get({ emailId, id })` |

附件对象：`id, filename, content_type, content_id, content_disposition`（`inline | attachment`）、`size`（字节）、`download_url`（签名 URL）、`expires_at`。**`download_url` 有效期 1 小时**，过期后重新调接口取新 URL。下载 URL 本身不需要 Authorization 头。

```ts
const { data: list } = await resend.emails.receiving.attachments.list({ emailId: event.data.email_id });
for (const a of list?.data ?? []) {
  const r = await fetch(a.download_url);           // 签名 URL，无需 Authorization
  if (r.ok) { const buf = Buffer.from(await r.arrayBuffer()); /* 存储 / 解析 */ }
}
```

注意 `GET /emails/receiving/{id}` 响应里的 `attachments[]` **没有** `download_url`，要拿 URL 必须走 attachments 接口。

## 10. 我想回复 / 转发收到的邮件

### 同线程回复

邮件客户端按 `Message-ID` 串线程。回复时：`headers['In-Reply-To']` = 收件事件的 `data.message_id`，主题以 `Re:` 开头；多轮回复再把历史 `message_id` 用空格拼进 `References` 头。

```ts
const { data, error } = await resend.emails.send({
  from: 'Support <support@example.com>',   // 必须是已验证发送域
  to: [event.data.from],
  subject: `Re: ${event.data.subject}`,
  html: '<p>Thanks for your email!</p>',
  headers: { 'In-Reply-To': event.data.message_id,
             References: [...previousMessageIds, event.data.message_id].join(' ') },
});
```

REST 对应 `POST /emails`，body 里 `headers` 是对象 `{ "In-Reply-To": "<…>" }`。

### 转发

| 方式 | 说明 |
|---|---|
| Node SDK `resend.emails.receiving.forward({ emailId, to, from })` | 自动拉取正文与附件；默认 `passthrough: true` 原样转发；`passthrough: false` + 自定义 `text`/`html` 则以"forwarded message"页脚形式附上原邮件。⚠ 这是 SDK 辅助方法，OpenAPI v1.5.1 无对应 REST endpoint，其他语言/裸 HTTP 需手动转发 |
| 手动 | `GET /emails/receiving/{id}` 拿 `html/text`（或下载 `raw` 用 `mailparser` 解析，内联图片更可靠）→ 下载附件转 base64 → `POST /emails` 带 `attachments[]`（`filename, content, content_type, content_id`；`content_id` 需去掉尖括号） |

发送侧限制同普通发送：整封邮件（含 base64 后附件）≤ 40MB。

## 11. ⚠ 汇总

- §2 创建：`events` 取值 OpenAPI 无枚举；新建 webhook 默认 `status` 未说明。
- §2 列表：OpenAPI list 响应无 `signing_secret`，verify 页称 list 也返回——文档自相矛盾。
- §2 `created_at` 非 ISO 格式仅见于示例。
- §4 `tags` 在 webhook 里是对象、在发送请求里是数组；`bounce` 的 SMTP 诊断数组字段名未给出。
- §5 SDK verify 参数名 `webhookSecret` vs `secret`、`req.headers[...]` vs `.get()` 示例不一致；重放容忍窗口未说明。
- §6 重试计划三处不一致；非 200 的 2xx 是否算成功未说明；无 replay API。
- §9 `from` 是否带显示名两页矛盾；`html_format`/`raw` 未进 OpenAPI；`raw` 何时为 null、收件配额与大小上限未说明。
- §10 `forward` 只有 SDK，无 REST。
