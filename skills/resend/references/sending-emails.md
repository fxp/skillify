# 发送邮件

> ⚠ 本文件的全部内容都是 `⚠ 文档原文，未实测`——整理自 `resend.com/docs` 和 `resend.com/openapi.json`（抓取于 2026-09-21），未经真实 API 调用确认。见 SKILL.md 里的验证状态说明。

## 目录

- [发送一封邮件 — `POST /emails`](#发送一封邮件--post-emails)
- [附件](#附件)
- [定时发送](#定时发送)
- [自定义请求头](#自定义请求头)
- [幂等性 key](#幂等性-key)
- [测试地址](#测试地址)
- [查询 / 更新 / 取消已发送或已排期的邮件](#查询--更新--取消)
- [邮件状态生命周期](#邮件状态生命周期)

## 发送一封邮件 — `POST /emails`

**Endpoint**：`POST https://api.resend.com/emails`
**用途**：发送一封交易邮件。这是绝大多数集成唯一需要的端点。

**Auth**：`Authorization: Bearer re_xxxxxxxxx`（原生 HTTP 请求还需加 `User-Agent` 请求头——见 SKILL.md 第 3 条）。

**请求体**

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `from` | string | **是** | 发件地址。域名必须已验证（或用 `onboarding@resend.dev` 做测试——见下文）。友好名称格式：`"Acme <sender@yourdomain.com>"`。 |
| `to` | string \| string[] | **是** | 最多 **50** 个地址。 |
| `subject` | string | **是** | |
| `html` | string | html/text/react 三选一必填 | HTML 正文。 |
| `text` | string | | 纯文本正文。**省略时会从 `html` 自动生成**——想关掉这个自动生成，传一个显式的空字符串。 |
| `react` | React.ReactNode | | **仅 Node.js SDK 支持。** 其他语言的服务端 SDK 都没有这个字段；它也不是一个原生的 API 字段（是 SDK 在请求发出前把它在客户端渲染成 HTML）。见 `templates-and-react-email.md`。 |
| `bcc` | string \| string[] | | |
| `cc` | string \| string[] | | |
| `reply_to`（Node SDK 里叫 `replyTo`） | string \| string[] | | |
| `headers` | object | | 自定义请求头——见[自定义请求头](#自定义请求头)。 |
| `scheduled_at`（`scheduledAt`） | string | | 自然语言（`"in 1 hour"`）或 ISO 8601。最多提前 30 天。见[定时发送](#定时发送)。 |
| `attachments` | array | | 见[附件](#附件)。 |
| `tags` | array of `{name, value}` | | 用于过滤/统计的自定义元数据。name 和 value：仅限 ASCII 字母/数字/`_`/`-`，各自最长 256 字符。 |
| `template` | object `{id, variables}` | | 用一个已发布的 Resend Template 发送，替代 `html`/`text`/`react`。**和 `html`、`text`、`react` 互斥**——同时传会返回校验错误。见 `templates-and-react-email.md`。 |
| `topic_id` | string | | 把这次发送限定在某个订阅 Topic 下：如果收件人是一个已经退订了该 Topic 的联系人，邮件会被静默跳过（标记为 `failed`），即便请求本身返回成功；如果收件人不是已知联系人，只有当该 Topic 的默认订阅方式是 `opt-in` 时才会发送。`to`/`cc`/`bcc` 各自独立判定。这是营销层功能——本 skill 只标注该字段的存在，不做进一步覆盖。 |

**请求头**：`Idempotency-Key`（可选）——见[幂等性 key](#幂等性-key)。

**响应 200**

```json
{ "id": "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794" }
```

这就是成功响应体的*全部内容*——只有一个 id。需要完整详情时之后再用 `GET /emails/{id}` 单独查询。

**示例 — curl**

```bash
curl -X POST 'https://api.resend.com/emails' \
  -H "Authorization: Bearer $RESEND_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "from": "Acme <onboarding@resend.dev>",
    "to": ["delivered@resend.dev"],
    "cc": "cc-recipient@example.com",
    "bcc": ["bcc1@example.com", "bcc2@example.com"],
    "subject": "Your receipt",
    "html": "<p>Thanks for your payment.</p>"
  }'
```

**示例 — Python（报错时抛异常，见 SKILL.md 第 5 条）**

```python
import os, resend
from resend.exceptions import ResendError, ValidationError, RateLimitError

resend.api_key = os.environ["RESEND_API_KEY"]

params: resend.Emails.SendParams = {
    "from": "Acme <onboarding@resend.dev>",
    "to": ["delivered@resend.dev"],
    "cc": "cc-recipient@example.com",
    "bcc": ["bcc1@example.com", "bcc2@example.com"],
    "subject": "Your receipt",
    "html": "<p>Thanks for your payment.</p>",
}

try:
    email = resend.Emails.send(params)
    print(email)  # {'id': '...'}
except RateLimitError:
    ...  # back off and retry
except ValidationError as error:
    ...  # fix the request params — error carries .code/.message
except ResendError as error:
    ...  # catch-all
```

缺少必填字段（比如没传 `to`）时，SDK 本身会抛出一个普通的 `ValueError`，而不是 `ResendError`——如果想要一条统一的错误处理路径，两种都要 catch。⚠ 文档原文，未实测。

**示例 — Node.js（返回 `{data, error}`，API 错误不会抛异常——见 SKILL.md 第 5 条）**

```ts
import { Resend } from 'resend';

const resend = new Resend(process.env.RESEND_API_KEY);

const { data, error } = await resend.emails.send({
  from: 'Acme <onboarding@resend.dev>',
  to: ['delivered@resend.dev'],
  cc: 'cc-recipient@example.com',
  bcc: ['bcc1@example.com', 'bcc2@example.com'],
  subject: 'Your receipt',
  html: '<p>Thanks for your payment.</p>',
});

if (error) {
  console.error(error); // { message: string, name: string }
  return;
}
console.log(data); // { id: '...' }
```

Node SDK 的参数是**驼峰命名**（`replyTo`、`scheduledAt`）；Python/API/其他 SDK 是**下划线命名**（`reply_to`、`scheduled_at`）。混用命名习惯在大多数 JS 运行时里不会报校验错误，而是被静默当成一个不认识的多余字段直接忽略——把某个语言文档里的示例照搬到 Node 代码时，要仔细核对字段命名方式。⚠ 文档原文，未实测。

## 附件

**两种附件方式：**

1. **远程文件** —— `path`：一个 Resend 会在服务端抓取的 URL，配合 `filename`。
2. **本地文件** —— `content`：Base64 编码的文件内容（部分 SDK 也接受原始 buffer），配合 `filename`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `content` | string(binary)/buffer | 本地文件的 Base64 内容。和 `path` 互斥——二选一，不能同时传（都不传会返回 `422 invalid_attachment`）。 |
| `filename` | string | 显示文件名。 |
| `path` | string | 远程附件的抓取 URL。 |
| `content_type`（`contentType`） | string | 可选；不传时根据 `filename` 推断。 |
| `content_id`（`contentId`） | string | 用于[内联/嵌入图片](#通过-cid-实现内联图片)——任意字符串，须小于 128 个字符。 |

```json
{
  "attachments": [
    { "path": "https://resend.com/static/sample/invoice.pdf", "filename": "invoice.pdf" }
  ]
}
```

### 通过 CID 实现内联图片

在 HTML 正文里用 `cid:` URL 引用附件的 `content_id`，并在附件里设置同一个值：

```html
<img src="cid:logo-image" />
```

```json
{ "attachments": [{ "path": "...", "filename": "logo.png", "content_id": "logo-image" }] }
```

### 限制

- **整封邮件的大小（含所有附件，Base64 编码之后）必须 ≤ 40 MB。** 这是 Base64 膨胀*之后*的大小（大约比原始文件大 33%），不是原始文件大小——按这个来预算。
- **`POST /emails/batch` 不支持附件**——见 SKILL.md 跨领域规则第 2 条（这一点和 OpenAPI schema 矛盾，schema 里没有体现这个限制；在验证之前，以这条被两处独立文档页面重复过的文字说明为准）。
- **不是所有文件类型都能发送。** 以下扩展名在*发送*时会被拦截（收信不受限制）：`.adp .app .asp .bas .bat .cer .chm .cmd .com .cpl .crt .csh .der .exe .fxp .gadget .hlp .hta .inf .ins .isp .its .js .jse .ksh .lib .lnk .mad .maf .mag .mam .maq .mar .mas .mat .mau .mav .maw .mda .mdb .mde .mdt .mdw .mdz .msc .msh .msh1 .msh2 .mshxml .msh1xml .msh2xml .msi .msp .mst .ops .pcd .pif .plg .prf .prg .reg .scf .scr .sct .shb .shs .sys .ps1 .ps1xml .ps2 .ps2xml .psc1 .psc2 .tmp .url .vb .vbe .vbs .vps .vsmacros .vss .vst .vsw .vxd .ws .wsc .wsf .wsh .xnk`。发送这类文件（比如一个 `.exe` 或 `.js` 文件）大概率会失败——具体的失败模式（错误码、静默丢弃）文档没写；⚠ 文档未说明。如果确实需要发送被拦截的文件类型，打个 zip 包再发。

**事后查看/下载附件**：`GET /emails/{email_id}/attachments`（列表）和 `GET /emails/{email_id}/attachments/{attachment_id}`（单个）都会返回一个限时有效的签名 `download_url`，以及 `content_disposition`（`inline`/`attachment`）、`size`、`expires_at`。

## 定时发送

在 `POST /emails`（或 `POST /emails/batch` 里逐条设置）上设置 `scheduled_at`（`scheduledAt`）：

- **自然语言**：`"in 1 hour"`、`"tomorrow at 9am"`、`"Friday at 3pm ET"`。
- **ISO 8601**：`"2026-08-05T11:52:01.858Z"`。
- **最多提前 30 天。**
- **SMTP 发送不支持定时**——这个功能只有 API/SDK/CLI 支持。

```bash
curl -X POST 'https://api.resend.com/emails' \
  -H "Authorization: Bearer $RESEND_API_KEY" -H 'Content-Type: application/json' \
  -d '{"from":"Acme <onboarding@resend.dev>","to":["delivered@resend.dev"],"subject":"hello","html":"<p>hi</p>","scheduled_at":"in 1 min"}'
```

**改期**：`PATCH /emails/{email_id}`，传新的 `scheduled_at`。
**取消**：`POST /emails/{email_id}/cancel`。⚠ 一旦取消，一封邮件**无法再改期发送**——取消是终态，不是暂停。

**定时发送失败**（到了预定时间邮件却没发出去）会发生在：用来创建排期的那个 API key 在预定时刻到来之前被删除/过期/暂停了，或者账号被标记为需要人工审核。失败原因会显示在 dashboard 里那封失败邮件的详情上，据这份文档看不会在 `email.failed` webhook 事件之外自动推送给你——见 `webhooks.md`。⚠ 文档原文，未实测。

## 自定义请求头

`headers: { "X-Entity-Ref-ID": "..." }` —— 任意自定义邮件请求头，比如 `X-Entity-Ref-ID`（文档记录的用途：防止 Gmail 把不相关的邮件归并到同一个线程里）或 `List-Unsubscribe`（文档记录的用途：给收件人一个一键退订的合规入口）。Resend 已经自己设置好了送达所需的全部请求头；这个字段是增量添加，不是用来覆盖 Resend 自己设置的请求头的。至于尝试覆盖一个 Resend 托管的请求头（比如 `From`、`Message-ID`）会被拒绝、被忽略、还是被接受——⚠ 文档原文，未实测，文档未说明。

## 幂等性 key

只在 **`POST /emails` 和 `POST /emails/batch`** 上支持（更新/取消/其他端点不支持）。

- 直接作为 `Idempotency-Key` HTTP 请求头传递，或通过各 SDK 单独的 `options` 参数传递（**不是**请求体/params 对象里的字段——见上面的 Python 示例，它是 `send()` 的第二个位置参数）。
- SMTP：用 `Resend-Idempotency-Key` 邮件头代替。
- 长度 1—256 个字符，每个逻辑请求必须唯一。建议格式：`<event-type>/<entity-id>`，比如 `welcome-user/123456789`。
- **保留 24 小时。** Resend 会检查这个窗口内是否已经用过同一个 key；如果用过，会返回原来那次的响应，**不会重新发送邮件**——可以放心盲重试。

**复用同一个 key 时的响应：**

| 状态码 | Error type | 含义 |
|---|---|---|
| 400 | `invalid_idempotency_key` | key 的长度不在 1—256 个字符之间。 |
| 409 | `invalid_idempotent_request` | 同一个 key 之前用过，但这次请求体和之前**不一样**——这次调用会被拒绝，换个 key 或者让请求体和原来完全一致。 |
| 409 | `concurrent_idempotent_requests` | 另一个用同一个 key 的请求还在处理中——短暂等待后重试是安全的。 |

```bash
curl -X POST 'https://api.resend.com/emails' \
  -H "Authorization: Bearer $RESEND_API_KEY" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: welcome-user/123456789' \
  -d '{"from":"Acme <onboarding@resend.dev>","to":["delivered@resend.dev"],"subject":"hello","html":"<p>hi</p>"}'
```

## 测试地址

Resend 提供了一批 `resend.dev` 域名下的测试地址，用来在**不影响你真实域名信誉、也不用真实收件箱**的情况下模拟特定结果，每个地址都支持 `+label` 后缀（比如 `delivered+signup@resend.dev`）来区分场景/webhook payload：

| 地址 | 模拟的结果 |
|---|---|
| `delivered@resend.dev` | 成功送达。 |
| `bounced@resend.dev` | 硬退信——产生一个 SMTP `550 5.1.1`（"Unknown User"）响应。 |
| `complained@resend.dev` | 收件人标记为垃圾邮件。 |
| `suppressed@resend.dev` | 被抑制名单拦截（原因上报为此前的一次退信）。**不支持 `+label`。** |

⚠ 文档原文，未实测。测试邮件依然会计入账号的每日/每月发送配额。不要用瞎编的假地址或者本地假 SMTP 服务器来代替这些测试地址——文档明确指出这是错误的测试方式，因为这样要么什么用都没有，要么会给你自己的域名带来真实退信风险。

## 查询 / 更新 / 取消

| Endpoint | Method | 用途 |
|---|---|---|
| `GET /emails/{email_id}` | 读取 | 一封已发送/已排期邮件的完整详情。 |
| `GET /emails` | 列表 | 游标分页（`limit`/`after`/`before`）的团队发送邮件列表。 |
| `PATCH /emails/{email_id}` | 更新 | 目前文档里只写了 `scheduled_at` 可更新（改期）。 |
| `POST /emails/{email_id}/cancel` | 取消 | 取消一封**已排期、还未发出**的邮件。终态——取消之后无法再改期。 |

## 邮件状态生命周期

`last_event` 字段（以及 webhook 订阅可以监听的事件——见 `webhooks.md`）可能是以下任意一个：

`bounced` · `canceled` · `clicked` · `complained` · `delivered` · `delivery_delayed` · `failed` · `opened` · `queued`（仅 Broadcasts/Batch）· `scheduled` · `sent` · `suppressed`

⚠ 文档原文，未实测 —— 这些状态之间准确的状态迁移图（比如 `delivery_delayed` 之后能不能变成 `delivered`）文档没有记录；文档未说明。
