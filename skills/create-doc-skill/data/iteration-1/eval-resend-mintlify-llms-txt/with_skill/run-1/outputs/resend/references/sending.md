# Resend · 发送邮件（单发、批量、定时、附件、管理已发邮件）

> **⚠ 验证状态：本文件全部内容为 OpenAPI 规范（resend/resend-openapi v1.5.1）与 https://resend.com/docs 页面的转录（抓取于 2026-09），尚未用真实 API key 调用验证。实际报错以 API 为准；未验证细节以 ⚠ 标出。**

来源：OpenAPI `Emails` tag（10 个 endpoint）；文档页 `api-reference/emails/*`、`dashboard/emails/*`、`send-with-nodejs`、`ai-onboarding`、`knowledge-base/what-email-addresses-to-use-for-testing`、`what-attachment-types-are-not-supported`、`what-sending-feature-to-use`。

## 目录
1. 选型：单发 / 批量 / 定时 / Broadcasts
2. 正文的四种写法：html / text / react / template
3. 我想发一封邮件 —— `POST /emails`
4. 我想一次发多封 —— `POST /emails/batch`
5. 我想定时发 —— `scheduled_at`
6. 我想带附件 / 内嵌图片 —— `attachments`
7. 我想打标签 / 加自定义 header —— `tags`、`headers`
8. 我想防止重试重复发送 —— `Idempotency-Key`
9. 我想查已发邮件 —— `GET /emails/{id}`、`GET /emails`
10. 我想改期 / 取消定时邮件 —— `PATCH /emails/{id}`、`POST /emails/{id}/cancel`
11. 我想把邮件分享给别人看 —— `POST /emails/{id}/share`
12. 我想读回已发邮件的附件 —— `GET /emails/{id}/attachments[/{attachment_id}]`
13. 我想看发送统计 —— `GET /emails/metrics`
14. 测试地址与 `last_event` 状态表

**命名差异（全文适用）**：REST body 是 snake_case（`reply_to`、`scheduled_at`、`content_id`、`content_type`），Node SDK 是 camelCase（`replyTo`、`scheduledAt`、`contentId`、`contentType`）。下面参数表按 REST 字段名写，SDK 示例用 camelCase。裸 HTTP 请求必须带 `Authorization: Bearer $RESEND_API_KEY` 和 `User-Agent`（缺 User-Agent 返回 403 / 错误码 1010）。

## 1. 选型：单发 / 批量 / 定时 / Broadcasts

| 需求 | 用什么 | 依据 |
|---|---|---|
| 一封事务邮件（密码重置、订单确认） | `POST /emails` | 默认路径 |
| 2–100 封**内容各不相同**的事务邮件，一次请求发完 | `POST /emails/batch` | 减少请求数（默认限速 10 req/s/team） |
| 同一封邮件发给很多人（营销、newsletter） | Broadcasts（另见 broadcasts 参考），**不要**用 batch 循环 | `dashboard/emails/batch-sending`："For marketing campaigns use Broadcasts"；营销邮件必须可退订 |
| 带附件或内嵌图片 | 只能 `POST /emails` | batch 不支持 `attachments` |
| 定时发送 | `POST /emails` 带 `scheduled_at`；batch 每个元素也可带（⚠ 见第 4 节矛盾） | `dashboard/emails/schedule-email` |
| 多个收件人看同一封（`to` 数组） | `POST /emails`，`to` 最多 50 个 | OpenAPI：Max 50 |

## 2. 正文的四种写法：html / text / react / template

| 写法 | REST 字段 | 说明 |
|---|---|---|
| HTML | `html` | 最常用。 |
| 纯文本 | `text` | **省略时 Resend 会从 `html` 自动生成纯文本版**；传空字符串 `""` 可关闭自动生成（`api-reference/emails/send-email`）。 |
| React 组件 | `react`（仅 Node SDK） | 用 React Email 组件渲染。官方要求**以函数调用形式传入** `WelcomeEmail({ name: 'John' })`，不要写 JSX `<WelcomeEmail name="John" />`（`send-with-nodejs` 官方 AI 指令）。REST 没有这个字段。 |
| 托管模板 | `template: { id, variables }` | `id` 是**已发布**模板的 id 或 alias；`variables` 的 key 只能是 ASCII 字母、数字、下划线，≤50 字符，保留名 `FIRST_NAME`、`LAST_NAME`、`EMAIL`、`UNSUBSCRIBE_URL` 不可用；value 是 string（≤2000 字符）或 number（≤2^53−1）。模板里用到的变量必须全部提供，否则 validation error。 |

**互斥**：给了 `template` 就不能再给 `html`、`text`、`react`，否则 API 返回 validation error。发模板时 payload 里的 `from`、`subject`、`reply_to` 优先于模板默认值；模板没设默认值的字段必须在 payload 里给。

⚠ 文档未说明：`html`/`text`/`react` 三者是否"至少要给一个"、以及都不给时的错误名。`send-with-nodejs` 的参数表把它们归为 "Content Parameters (at least one required)"，OpenAPI 里三者都不是 required。

## 3. 我想发一封邮件 —— `POST /emails`

**Endpoint**: `POST /emails`（Node SDK：`resend.emails.send(payload, options?)`）
**用途**: 发送一封事务邮件；支持多收件人、附件、定时、模板。与 batch 的区别：batch 是"多封不同邮件"，这里是"一封邮件（可多收件人）"。

**关键参数**（REST 字段名；Node SDK 用 camelCase）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `from` | string | 是 | — | 发件地址，可带显示名：`Acme <hello@yourdomain.com>`。域名必须已验证；`onboarding@resend.dev` 仅测试用。 |
| `to` | string \| string[] | 是 | — | 收件人，**最多 50 个**。 |
| `subject` | string | 是 | — | 主题。 |
| `cc` / `bcc` | string \| string[] | 否 | — | 抄送 / 密送。 |
| `reply_to` | string \| string[] | 否 | — | 回复地址（SDK：`replyTo`）。 |
| `html` / `text` / `react` / `template` | 见第 2 节 | 否 | — | 正文；`template` 与其他三者互斥。 |
| `headers` | object | 否 | — | 自定义邮件头，见第 7 节。 |
| `scheduled_at` | string | 否 | — | ISO 8601 或自然语言（`in 1 min`），见第 5 节。 |
| `attachments` | object[] | 否 | — | 见第 6 节。 |
| `tags` | `{name, value}[]` | 否 | — | 见第 7 节。 |
| `topic_id` | string | 否 | — | 把邮件限定到某个 topic：收件人是联系人且对该 topic **opt-in** → 发送；联系人且 **opt-out** → 不发，标记为 `failed`；不是联系人 → 仅当 topic 默认订阅为 `opt-in` 时发送。`to`/`cc`/`bcc` 每个地址**分别**判断。 |

请求头：`Idempotency-Key`（可选，见第 8 节）。

**示例（SDK）**

```ts
import { Resend } from 'resend';

const resend = new Resend(process.env.RESEND_API_KEY);

const { data, error } = await resend.emails.send({
  from: 'Acme <hello@yourdomain.com>',
  to: ['delivered@resend.dev'],
  replyTo: 'support@yourdomain.com',
  subject: 'Your receipt',
  html: '<p>Thanks for your order.</p>', // text 省略：Resend 会从 html 生成纯文本版
  tags: [{ name: 'category', value: 'receipt' }],
});

if (error) return console.error(error.name, error.message); // SDK 不抛异常，用 { data, error } 判错
console.log(data.id);
```

**示例（fetch，底层 `POST /emails`）**

```ts
const res = await fetch('https://api.resend.com/emails', {
  method: 'POST',
  // User-Agent 缺失会 403（错误码 1010）
  headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}`, 'Content-Type': 'application/json', 'User-Agent': 'my-app/1.0' },
  body: JSON.stringify({
    from: 'Acme <hello@yourdomain.com>', to: ['delivered@resend.dev'], subject: 'Your receipt',
    reply_to: 'support@yourdomain.com', // REST 用 snake_case
    html: '<p>Thanks for your order.</p>',
  }),
});
const body = await res.json(); // 成功：{ id }；失败：{ statusCode, name, message }
```

**示例响应**：`{ "id": "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794" }`。Node SDK 包装为 `{ data: { id }, error: null }`；失败时 `{ data: null, error: { name, message } }`。

**注意事项**
- HTTP 状态码：OpenAPI 标的是 **200**；文档页示例只写 "Response" 未标状态码。⚠ 文档未说明是否实际返回 201，写代码时按 `res.ok` 判断而不是 `=== 200`。
- 未验证域名时，`from` 用 `onboarding@resend.dev` 只能发给自己账号的邮箱，否则 403 `validation_error`。
- 发给 `@example.com`、`@test.com` 这类地址会被拦截，返回 **422**（`knowledge-base/what-email-addresses-to-use-for-testing`）。测试请用第 14 节的 `resend.dev` 地址。
- 官方给 AI 的硬性指令（`send-with-nodejs`）：包名是 `resend`、类是 `Resend`；一定 `await`；用 `{ data, error }` 判错而不是 try/catch（只有网络层故障才 throw）；SDK 参数 camelCase；不要在生产代码用 `onboarding@resend.dev` 做 `from`。

## 4. 我想一次发多封 —— `POST /emails/batch`

**Endpoint**: `POST /emails/batch`（Node SDK：`resend.batch.send(payload[], options?)`）
**用途**: 一次请求最多 **100 封**互相独立的邮件（各自的 from/to/subject/正文）。不是"一封发给 100 人"（那是 `to` 数组，上限 50）。

**关键参数**：body 是**数组**，每个元素的字段与 `POST /emails` 相同（`from`、`to`、`subject` 必填；`to` 每封最多 50 个）。请求头 `Idempotency-Key` 可选，建议用代表整批的 key（如 `team-quota/123456789`）。

⚠ 文档自相矛盾（`attachments` / `scheduled_at` 在 batch 里能不能用）：
- OpenAPI schema：batch 数组元素含 `attachments` 和 `scheduled_at` 字段，与单发一致。
- `api-reference/emails/send-batch-emails` "Limitations"：**"The `attachments` field is not supported yet"**；同页参数表列出了 `scheduled_at`，没列 `attachments`。
- `dashboard/emails/batch-sending` "Limitations"：最多 100 封；`attachments` 不支持；每封独立处理；任一封校验失败则整个请求失败。
- `dashboard/emails/schedule-email` 专门有一节 "Schedule emails on the `POST /emails/batch` endpoint"，示例每个元素各自带 `scheduled_at: 'in 1 min'` / `'in 5 min'`，明确说**可以**。
- `ai-onboarding` 页：**"No attachments" 且 "No scheduling"**，让用户用单发。
- 结论：附件不支持是各页一致的；`scheduled_at` 是 OpenAPI + 两个功能页说支持、ai-onboarding 页说不支持，以实测为准。写代码时先按"支持"试，失败再拆成单发。

⚠ 文档自相矛盾（失败语义）：`dashboard/emails/batch-sending` 同时写了 "Each email in the batch is processed independently" 和 "The request will fail and return an error if any email in your payload is invalid"；`ai-onboarding` 页概括为 "Atomic — If one email fails validation, the entire batch fails"。合理解读：请求级校验是全有或全无，通过后各封投递互不影响；但文档没这样明说。

**示例（SDK）**

```ts
const { data, error } = await resend.batch.send([
  { from: 'Acme <hello@yourdomain.com>', to: ['delivered+order1@resend.dev'], subject: 'Order shipped',
    html: '<p>Your order has shipped.</p>', tags: [{ name: 'category', value: 'shipping' }] },
  { from: 'Acme <hello@yourdomain.com>', to: ['delivered+order2@resend.dev'], subject: 'Order confirmed',
    html: '<p>Your order is confirmed.</p>' },
]);
if (error) return console.error(error);
console.log(data.data.map((e) => e.id)); // ⚠ 见下方"响应嵌套"
```

**示例（fetch，底层 `POST /emails/batch`）**

```ts
const res = await fetch('https://api.resend.com/emails/batch', {
  method: 'POST',
  headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}`, 'Content-Type': 'application/json', 'User-Agent': 'my-app/1.0' },
  body: JSON.stringify([
    { from: 'Acme <hello@yourdomain.com>', to: ['a@example.org'], subject: 'A', html: '<p>A</p>' },
    { from: 'Acme <hello@yourdomain.com>', to: ['b@example.org'], subject: 'B', html: '<p>B</p>' },
  ]),
});
```

**示例响应**：`{ "data": [ { "id": "ae2014de-c168-4c61-8267-70d2662a1ce1" }, { "id": "faccb7a5-8a28-4e9a-ac64-8da1cc3bc1cb" } ] }` —— `data[i]` 与请求数组第 i 个元素一一对应（0-based）。

**注意事项**
- ⚠ 响应嵌套：REST 返回 `{ data: [ {id} ] }`；Node SDK 又包一层 `{ data, error }`。`ai-onboarding` 页的示例直接写 `data.map((e) => e.id)`（即 SDK 把内层 `data` 展开了），而按 REST 结构应是 `data.data`。哪一种取决于 SDK 版本，⚠ 文档未说明，实测后再定。
- 批量发出的邮件初始状态是 `queued`，之后再变为 `sent`/`delivered`。
- 批量里每封的 `to` 仍然最多 50 个。

## 5. 我想定时发 —— `scheduled_at`

不是独立 endpoint，是 `POST /emails`（和 batch 元素）上的一个字段。

| 参数 | 类型 | 说明 |
|---|---|---|
| `scheduled_at`（SDK `scheduledAt`） | string | ISO 8601（`2026-08-05T11:52:01.858Z`）或自然语言（`in 1 min`、`tomorrow at 9am`、`Friday at 3pm ET`）。**最多提前 30 天**。 |

```ts
const { data, error } = await resend.emails.send({
  from: 'Acme <hello@yourdomain.com>', to: ['delivered@resend.dev'],
  subject: 'Reminder', html: '<p>Your event starts in 24 hours.</p>',
  scheduledAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(), // 或 'in 1 hour'
});
```

**注意事项**
- 定时邮件的 `last_event` 是 `scheduled`；改期用第 10 节的 `PATCH`，取消用 `POST …/cancel`；**取消后不能再改期**。
- 定时邮件可能在到点时发送失败：API key 已被删除/停用、账号处于审核。失败原因在控制台邮件详情里看。
- SMTP 方式发的邮件不能定时。
- ⚠ 文档未说明：自然语言解析用哪个时区（示例里用了 `ET` 后缀，暗示需要显式写时区）；超过 30 天时的错误名。稳妥做法：自己算好 UTC 再传 ISO 字符串。

## 6. 我想带附件 / 内嵌图片 —— `attachments`

`attachments[]` 每个元素：

| 参数 | 类型 | 说明 |
|---|---|---|
| `content` | Base64 string（SDK 也接受 Buffer） | 本地文件内容。与 `path` 二选一。 |
| `path` | string（URL） | 远程文件，Resend 自己去下载，不用 Base64。 |
| `filename` | string | 附件显示名；未给 `content_type` 时用它推断 MIME。 |
| `content_type`（SDK `contentType`） | string | 可选 MIME 类型。 |
| `content_id`（SDK `contentId`） | string | 内嵌图片用：HTML 里写 `<img src="cid:logo-image">`，这里填 `logo-image`。**必须少于 128 字符**。 |

```ts
import fs from 'node:fs';

const invoice = fs.readFileSync('./invoice.pdf').toString('base64');

const { data, error } = await resend.emails.send({
  from: 'Acme <hello@yourdomain.com>', to: ['delivered@resend.dev'], subject: 'Receipt',
  html: '<p>Here is our <img src="cid:logo-image"/> logo and your invoice.</p>',
  attachments: [
    { content: invoice, filename: 'invoice.pdf' },                       // 本地
    { path: 'https://yourdomain.com/logo.png', filename: 'logo.png', contentId: 'logo-image' }, // 远程 + 内嵌
  ],
});
```

**注意事项**
- 整封邮件（含 Base64 后的附件）**不超过 40MB**。
- 不支持 batch endpoint（含内嵌图片）。
- 不允许发送的扩展名（`knowledge-base/what-attachment-types-are-not-supported`）：`.exe .bat .cmd .com .msi .js .jse .vbs .vbe .ps1 .reg .scr .lnk .url .tmp .hta .chm .cpl .pif .sys .app .adp .cer .crt .der .mdb .mde ...` 等可执行/脚本/证书类（完整表见该页，共 90 余项）。**接收**邮件不受此限制。
- 内嵌图片：建议同时给 `content_type` 或 `filename` 帮助客户端渲染；有些 webmail 会拒绝内嵌图片；控制台预览 HTML 时不显示附件和内嵌图片。
- ⚠ 文档未说明单封邮件的附件数量上限（只给了 40MB 总量）。

## 7. 我想打标签 / 加自定义 header —— `tags`、`headers`

**tags**：`[{ name, value }]`，每封最多 **75 个**；`name` 与 `value` 都只能含 ASCII 字母、数字、下划线、短横线，各 ≤256 字符（所以 `value: 'user@x.com'` 或含空格/中文的值会被拒）。tag 会原样出现在 webhook 事件里，用于回联业务对象（customer id、plan、邮件类别）。

**headers**：`{ 'Header-Name': 'value' }`。文档给出的两个典型用途：
- `X-Entity-Ref-ID`：给每封邮件不同值，**阻止 Gmail 把邮件串成同一会话**。
- `List-Unsubscribe: <https://example.com/unsubscribe>`：让邮件客户端显示一键退订。Resend 不为事务邮件管理退订列表，自己管。自 2024 年 2 月起 Gmail/Yahoo 要求批量发送者（>5000 封/天）同时加 `List-Unsubscribe-Post: List-Unsubscribe=One-Click` 并接受同 URL 的 POST（RFC 8058），POST 返回空 200/202，48 小时内停止发送。

```ts
await resend.emails.send({
  from: 'Acme <hello@yourdomain.com>', to: ['delivered@resend.dev'], subject: 'Weekly digest', html: '<p>...</p>',
  headers: {
    'X-Entity-Ref-ID': crypto.randomUUID(),
    'List-Unsubscribe': '<https://yourdomain.com/unsubscribe?u=123>',
    'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
  },
});
```

⚠ 文档未说明：哪些 header 名是保留的（如 `From`、`To`、`Message-ID`）会被忽略或报错。

## 8. 我想防止重试重复发送 —— `Idempotency-Key`

- 请求头 `Idempotency-Key`，仅 `POST /emails` 和 `POST /emails/batch` 支持；SMTP 用 `Resend-Idempotency-Key` 邮件头。
- 1–256 字符，每个请求唯一；推荐 `<event-type>/<entity-id>`，如 `welcome-user/123456789`；batch 用代表整批的 key。
- 24 小时内同 key + 同 body → 直接返回原响应，不再发送；同 key 不同 body → **409 `invalid_idempotent_request`**（换 key 或换 body 再试）；同 key 并发进行中 → **409 `concurrent_idempotent_requests`**（稍后重试即可）；key 长度非法 → 400 `invalid_idempotency_key`。

⚠ 文档自相矛盾（Node SDK 里 `idempotencyKey` 放哪）：
- `dashboard/emails/idempotency-keys` 与 `ai-onboarding`：放在**第二个 options 参数**里：

```ts
await resend.emails.send(
  { from: 'Acme <hello@yourdomain.com>', to: ['delivered@resend.dev'], subject: 'Welcome', html: '<p>Hi</p>' },
  { idempotencyKey: 'welcome-user/123456789' },
);
await resend.batch.send([/* ... */], { idempotencyKey: 'team-quota/123456789' });
```

- `send-with-nodejs`（及所有 `send-with-*` 框架页）：放在**第一个 payload 对象**里：

```ts
await resend.emails.send({
  from: 'Acme <hello@yourdomain.com>', to: ['delivered@resend.dev'], subject: 'Welcome', html: '<p>Hi</p>',
  idempotencyKey: 'welcome-user/123456789',
});
```

- `send-with-python` 页还写了一句 "Unlike Node's single-object `idempotencyKey` field, Python's `send()` takes idempotency as a second, separate argument"，即官方自己也把 Node 描述为"单对象字段"。
- 两种写法可能分属不同 SDK 版本；用哪种要看你安装的 `resend` 包的类型定义（TypeScript 编译会告诉你）。裸 HTTP 没有歧义：就是 `Idempotency-Key` 请求头。

## 9. 我想查已发邮件 —— `GET /emails/{id}`、`GET /emails`

### 查单封
**Endpoint**: `GET /emails/{email_id}`（SDK：`resend.emails.get(id)`）
**用途**: 取一封已发/已定时邮件的元数据、正文与当前状态 `last_event`。只覆盖**本 team 发出**的邮件；收到的邮件走 `receiving` 那组接口。

```ts
const { data, error } = await resend.emails.get('49a3999c-0ce1-4ea6-ab68-afcd6dc2e794');
// data.last_event === 'delivered' | 'bounced' | ...
```

**示例响应**（文档页）

```json
{
  "object": "email", "id": "4ef9a417-02e9-4d39-ad75-9611e0fcc33c",
  "message_id": "<111-222-333@email.example.com>",
  "to": ["delivered@resend.dev"], "from": "Acme <hello@yourdomain.com>",
  "created_at": "2026-04-03 22:13:42.674981+00", "subject": "Hello World",
  "html": "...", "text": null, "bcc": [], "cc": [], "reply_to": [],
  "last_event": "delivered", "scheduled_at": null,
  "tags": [{ "name": "category", "value": "confirm_email" }]
}
```

⚠ 文档自相矛盾：OpenAPI 的响应 schema **没有** `scheduled_at` 和 `tags` 字段，文档页示例响应有；`created_at` 是 `2026-04-03 22:13:42.674981+00` 这种 Postgres 风格而非 ISO 8601，解析时注意。

### 列表
**Endpoint**: `GET /emails`（SDK：`resend.emails.list()`）
**用途**: 分页列出本 team 发出的邮件。query：`limit`（1–100，默认 20）、`after` / `before`（游标 = 邮件 id，二选一）。响应 `{ object: "list", has_more, data: [...] }`，元素字段同上但**不含正文**（页面示例里没有 `html`/`text`；⚠ OpenAPI 的 list schema 里却列了 `html`/`text`，两边不一致）。列表示例里 `bcc`/`cc`/`reply_to` 为 `null`，单封查询里为 `[]`，处理时两种都要兼容。

```ts
let after: string | undefined;
do {
  const { data, error } = await resend.emails.list({ limit: 100, after });
  if (error) throw error;
  for (const email of data.data) console.log(email.id, email.last_event);
  after = data.has_more ? data.data.at(-1)?.id : undefined;
} while (after);
```

⚠ 文档未说明：`list()` 的 SDK 参数名是否就是 `{ limit, after, before }`（页面示例只有无参调用；Go 示例用 `After: 最后一条的 ID`）。

## 10. 我想改期 / 取消定时邮件 —— `PATCH /emails/{id}`、`POST /emails/{id}/cancel`

### 改期
**Endpoint**: `PATCH /emails/{email_id}`（SDK：`resend.emails.update({ id, scheduledAt })`）
**用途**: 修改一封**已定时、尚未发出**邮件的发送时间。文档标题就是 "Update a scheduled email"，body 只有一个字段 `scheduled_at`（ISO 8601；`schedule-email` 页示例也用了自然语言 `in 1 min`）。不能改收件人、主题或正文。

```ts
const { data, error } = await resend.emails.update({ id: '49a3999c-0ce1-4ea6-ab68-afcd6dc2e794', scheduledAt: new Date(Date.now() + 60_000).toISOString() });
```

**示例响应**（文档页）：`{ "object": "email", "id": "49a3999c-..." }`
⚠ 文档自相矛盾：OpenAPI 把 PATCH 的 200 响应 schema 写成只有 `scheduled_at` 一个字段（看起来是把请求体误放到了响应里），且没有列出请求体；以文档页为准。

### 取消
**Endpoint**: `POST /emails/{email_id}/cancel`（SDK：`resend.emails.cancel(id)`）
**用途**: 取消一封定时邮件；之后 `last_event` 变为 `canceled`。**取消后不能再改期或恢复**（要重新发一封）。

```ts
const { data, error } = await resend.emails.cancel('49a3999c-0ce1-4ea6-ab68-afcd6dc2e794');
```

**示例响应**（文档页）：`{ "object": "email", "id": "49a3999c-..." }`
⚠ 文档自相矛盾：OpenAPI 把 cancel 的响应 schema 写成完整邮件对象（含 `to`、`from`、`last_event` 等），文档页示例只有 `object` + `id`。

**注意事项**
- ⚠ 文档未说明：对一封**不是**定时的（已 `sent`/`delivered`）邮件调用 update 或 cancel 会返回什么错误；两个页面的标题和描述都只针对 "scheduled email"，应视为**只对 `last_event === 'scheduled'` 的邮件有效**。
- 没有"撤回已投递邮件"的接口。

## 11. 我想把邮件分享给别人看 —— `POST /emails/{id}/share`

**Endpoint**: `POST /emails/{email_id}/share`（SDK：`resend.emails.share(id, { expiresIn })`）
**用途**: 生成一个**无需登录**即可查看这封邮件（已发或已收）的公开链接，给团队外的人排查用。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `expires_in`（SDK `expiresIn`） | string | 否 | `48h` | 时长字符串，如 `10m`、`2 hours`、`1 day`；**不能超过 48 小时**。 |

```ts
const { data, error } = await resend.emails.share('49a3999c-0ce1-4ea6-ab68-afcd6dc2e794', { expiresIn: '2 hours' });
console.log(data.url); // https://resend.com/shared?token=...
```

**示例响应**：`{ "object": "email", "id": "49a3999c-...", "url": "https://resend.com/shared?token=..." }`

注意：任何拿到链接的人都能看邮件全文，别把含敏感内容的邮件分享出去。⚠ 文档未说明能否提前撤销链接。

## 12. 我想读回已发邮件的附件 —— `GET /emails/{id}/attachments[/{attachment_id}]`

**Endpoint**: `GET /emails/{email_id}/attachments`（SDK：`resend.emails.attachments.list({ emailId })`）；`GET /emails/{email_id}/attachments/{attachment_id}`（SDK：`resend.emails.attachments.get({ id, emailId })`）
**用途**: 列出/读取一封**已发送**邮件的附件元数据，拿到一个**带签名、会过期**的 `download_url`，再自己去下载内容。接口本身不返回文件字节。列表支持 `limit` / `after` / `before` 分页（游标是 attachment id）。

```ts
const { data, error } = await resend.emails.attachments.list({ emailId: '4ef9a417-02e9-4d39-ad75-9611e0fcc33c' });
for (const a of data.data) {
  const file = await fetch(a.download_url); // 注意 expires_at
  // ...
}
```

**示例响应**（单个附件；列表是 `{ object: "list", has_more, data: [ ... ] }`）

```json
{
  "object": "attachment", "id": "2a0c9ce0-3112-4728-976e-47ddcd16a318",
  "filename": "avatar.png", "size": 4096, "content_type": "image/png",
  "content_disposition": "inline", "content_id": "img001",
  "download_url": "https://outbound-cdn.resend.com/.../attachments/2a0c9ce0-...?...&signature=...",
  "expires_at": "2026-10-17T14:29:41.521Z"
}
```

`content_disposition` 枚举：`inline`（内嵌图片）/ `attachment`。⚠ 文档未说明 `download_url` 有效期长度（只给了 `expires_at`），以及已发邮件附件的保留期限。

## 13. 我想看发送统计 —— `GET /emails/metrics`

**Endpoint**: `GET /emails/metrics`（SDK：`resend.emails.metrics({ startDate, endDate, metrics, dimensions, granularity, timezone, domainId, emailId, broadcastId })`）
**用途**: 账号级发送指标聚合。全部参数可选；不传时返回**最近 7 天**（今天 + 前 6 天）所有指标的 `totals`，无 `data`。响应缓存最多 15 分钟；`start_date` 早于计划保留期会被截断到最早可用日期（指定 `broadcast_id` 时除外）。

| 参数 | 类型 | 说明 |
|---|---|---|
| `start_date` / `end_date` | ISO 8601 日期或时间 | `start_date` 默认 `end_date` 前 6 天；`end_date` 默认现在，未来值截断到当前。两者相等可查单日。 |
| `metrics` | string[] | 逗号分隔或重复参数。默认全部。 |
| `dimensions` | string[] | `period`、`domain`、`email`、`broadcast`，可组合；**`email` 与 `broadcast` 不能同时用**。不传则只有 `totals`。 |
| `granularity` / `timezone` | `hourly` \| `daily` \| `weekly` \| `monthly` / IANA 时区名 | 仅当 `dimensions` 含 `period` 时生效；桶数不能超过 10,000。 |
| `domain_id` / `email_id` / `broadcast_id` | uuid[]，各最多 100 | 过滤范围；`email_id` 不能与 `broadcast` 维度或 `broadcast_id` 同用，反之亦然。 |

可用指标：`received`、`sent`、`delivered`、`delivery_delayed`、`failed`、`suppressed`、`bounced`（= 下面三项之和）、`bounced_transient`、`bounced_permanent`、`bounced_undetermined`、`opened`、`unique_opened`、`clicked`、`unique_clicked`、`complained`、`unsubscribed`，以及比率 `delivery_rate`（delivered/sent）、`open_rate`（unique_opened/delivered）、`click_rate`（unique_clicked/delivered）、`bounce_rate`（bounced/sent）、`complaint_rate`、`unsubscribe_rate`。打开/点击指标需要域名开启 open/click tracking。

```ts
const { data, error } = await resend.emails.metrics({
  startDate: '2026-07-01', endDate: '2026-07-08',
  metrics: ['sent', 'delivered', 'bounce_rate'], dimensions: ['period', 'domain'], granularity: 'daily',
});
```

**示例响应**

```json
{
  "object": "metrics", "start_date": "2026-07-01T00:00:00.000Z", "end_date": "2026-07-08T00:00:00.000Z",
  "metrics": ["sent", "delivered", "open_rate"], "dimensions": ["period", "domain"], "granularity": "daily",
  "totals": { "sent": 1204, "delivered": 1180, "open_rate": 50.0 },
  "data": [ { "period": "2026-07-01", "domain_id": "d91cd9bd-...", "domain_name": "example.com", "sent": 172, "delivered": 169, "open_rate": 49.7 } ]
}
```

比率在示例里是 `50.0` / `49.7`，即**百分数**而不是 0–1 小数。`data[]` 行里有哪些标识字段取决于 `dimensions`（`period`、`domain_id`+`domain_name`、`email_id`、`broadcast_id`+`broadcast_name`）。

## 14. 测试地址与 `last_event` 状态表

**测试地址**（`resend.dev`，计入发送配额；不要用 `@example.com`/`@test.com`，会 422）：

| 地址 | 模拟事件 | 支持 `+label` |
|---|---|---|
| `delivered@resend.dev` | 投递成功 | 是（`delivered+signup@resend.dev`） |
| `bounced@resend.dev` | 硬退信，SMTP 550 5.1.1 | 是 |
| `complained@resend.dev` | 投递成功但被标记为垃圾邮件 | 是 |
| `suppressed@resend.dev` | 被抑制（原因显示为"曾退信"） | **否** |

`from` 未验证域名时可用 `onboarding@resend.dev`，但只能发到自己账号的邮箱。

**`last_event` 枚举**（OpenAPI 与 `dashboard/emails/manage-emails` 一致）：

| 值 | 含义 |
|---|---|
| `queued` / `scheduled` | Batch/Broadcast 创建的邮件已入队待处理 / 已定时未到点 |
| `sent` / `delivered` | 已发出到收件方服务器 / 收件方服务器已接受 |
| `delivery_delayed` | 临时问题（信箱满、对方服务器抖动），非最终状态 |
| `bounced` | 被拒收（Permanent / Transient / Undetermined 三类；硬退信地址会进 suppression list） |
| `complained` / `suppressed` | 已投递但被标记为垃圾邮件（Gmail 不回传此事件）/ 收件人在本 team 抑制列表里，未发送 |
| `failed` / `canceled` | 发送失败（含 `topic_id` opt-out）/ 定时邮件被取消 |
| `opened` / `clicked` | 打开 / 点击（需开启 tracking；打开率并不精确） |

抑制列表是 team 级、跨所有域名生效；来源 `bounce` / `complaint` / `manual`。从列表移除后若再次退信会自动重新抑制。
