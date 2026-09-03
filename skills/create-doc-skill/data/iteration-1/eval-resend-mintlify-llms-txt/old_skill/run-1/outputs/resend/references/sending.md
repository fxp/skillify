# Resend — Sending transactional email (Emails resource)

> Source: resend.com/docs + resend-openapi v1.5.1, read 2026-09-03. NOT yet verified against the live API — see verification-plan.md.

## When to read this file

Read this when you need to write TypeScript (or raw HTTP) that sends, schedules, batches, retrieves,
reschedules or cancels a transactional email with Resend, or that attaches files / inline images,
adds tags or custom headers, sends with a hosted template, or uses idempotency keys. It also lists
which recipient addresses are safe for tests. Broadcasts, Audiences/Contacts, Templates CRUD, Domains,
Webhooks and the full error-code table live in their own reference files.

Conventions: raw JSON API is `snake_case`; the Node SDK is `camelCase` (`replyTo`, `scheduledAt`, `contentId`,
`contentType`, `idempotencyKey`). Every SDK call resolves to `{ data, error }` and does NOT throw on API errors.

**Contents**: [Send](#send-an-email) · [Attachments / cid:](#attachments-and-inline-images) ·
[Tags & headers](#tags-and-custom-headers) · [Schedule / reschedule / cancel](#schedule-an-email) ·
[Idempotency](#idempotency-keys) · [Templates](#send-with-a-template) · [React Email](#react-email) ·
[Batch](#batch-send) · [Retrieve / list](#retrieve-a-sent-email) · [Sent attachments](#list-attachments-of-a-sent-email) ·
[Test addresses](#test-addresses) · [Raw fetch()](#raw-fetch-without-the-sdk)

### Send an email
**Endpoint**: `POST /emails`  (SDK: `resend.emails.send(payload, options?)`)
**Purpose**: Send one transactional email to up to 50 recipients. Returns the email `id` immediately; delivery is asynchronous (track via `last_event` or webhooks).
**Key parameters**

| Param (JSON) | SDK name | Type | Required | Notes |
|---|---|---|---|---|
| `from` | `from` | string | yes | `"Name <sender@yourdomain.com>"`. Domain must be verified (except the test sender, see below). |
| `to` | `to` | string \| string[] | yes | Max 50 addresses. |
| `subject` | `subject` | string | yes | Required unless a template supplies a default. |
| `cc`, `bcc`, `reply_to` | `cc`, `bcc`, `replyTo` | string \| string[] | no | Same shape as `to`. |
| `html` | `html` | string | no* | HTML body. |
| `text` | `text` | string | no* | Plain text. If omitted, auto-generated from `html`; pass `""` to opt out. |
| `react` | `react` | React.ReactNode | no* | Node SDK only. See [React Email](#react-email). |
| `template` | `template` | `{ id, variables? }` | no* | Mutually exclusive with `html`/`text`/`react`. See [Templates](#send-with-a-template). |
| `headers` | `headers` | object | no | Custom headers, e.g. `X-Entity-Ref-ID`, `List-Unsubscribe`. |
| `attachments` | `attachments` | array | no | See [Attachments](#attachments-and-inline-images). Not allowed in batch. |
| `tags` | `tags` | `{ name, value }[]` | no | See [Tags](#tags-and-custom-headers). |
| `scheduled_at` | `scheduledAt` | string | no | See [Scheduling](#schedule-an-email). |
| `topic_id` | `topicId` | string | no | Scope the email to a Topic (see Gotchas). |
| header `Idempotency-Key` | `options.idempotencyKey` | string | no | See [Idempotency keys](#idempotency-keys). |

\* At least one body source (`html`, `text`, `react`, or `template`) is needed.

**Example (TypeScript)**
```ts
import { Resend } from 'resend';

const resend = new Resend(process.env.RESEND_API_KEY);

const { data, error } = await resend.emails.send({
  from: 'Acme <noreply@yourdomain.com>',
  to: ['delivered@resend.dev'],
  replyTo: 'support@yourdomain.com',
  subject: 'Your receipt',
  html: '<p>Thanks for your order.</p>',
  // text omitted => generated from html. Use text: '' to send HTML only.
  headers: { 'X-Entity-Ref-ID': 'order-123' },
  tags: [{ name: 'category', value: 'receipt' }],
});

if (error) {
  console.error(error); // { name, message } — nothing is thrown
  return;
}
console.log(data); // { id: '49a3999c-...' }
```

**Example (curl)**
```bash
curl -X POST 'https://api.resend.com/emails' \
  -H "Authorization: Bearer $RESEND_API_KEY" -H 'Content-Type: application/json' \
  -d '{"from":"Acme <noreply@yourdomain.com>","to":["delivered@resend.dev"],"subject":"hello world","html":"<p>it works!</p>"}'
```

**Response**: `{ "id": "<email id>" }`. SDK: `{ data: { id }, error: null }` or `{ data: null, error: { name, message } }`.

**Gotchas**
- `to`/`cc`/`bcc`/`reply_to` accept a bare string OR an array; there is no `{ email, name }` object form (unlike SendGrid). Friendly names go inside the string: `"Name <a@b.com>"`. **50 recipients max.**
- `template` with any of `html`/`text`/`react` is a validation error. `html` + `text` together is fine.
- `text` is auto-derived from `html` unless you set `text: ""` — SES/Mailgun users often expect HTML-only by default.
- `topic_id`: each address in `to`/`cc`/`bcc` is checked separately. Contact opted-in → sent; contact opted-out → **not sent, marked `failed`**; not a contact → sent only if the topic's default subscription is `opt-in`. (`topicId` follows the camelCase convention; ⚠ VERIFY the exact SDK key — no Node example in the docs read.)
- Default rate limit **10 requests/second per team** → `429`; daily/monthly quota exhaustion is also `429`. `@example.com` / `@test.com` recipients → **422**.
- The SDK does not throw for API errors (`try/catch` only catches network failures). Raw HTTP without a `User-Agent` header → **403, error code 1010** before reaching the API.

### Attachments and inline images
**Endpoint**: `POST /emails` (same call, `attachments[]`)  (SDK: `resend.emails.send`)
**Purpose**: Attach files by Base64 content or by remote URL; optionally embed images inline via `cid:`.
**Key parameters** (each item of `attachments`)

| Param (JSON) | SDK name | Type | Required | Notes |
|---|---|---|---|---|
| `content` | `content` | Base64 string (SDK also takes `Buffer`) | one of content/path | OpenAPI types it `string, format=binary`; docs say `buffer \| string`. |
| `path` | `path` | string (URL) | one of content/path | Remote file fetched by Resend — no Base64 needed; better for large files. |
| `filename` | `filename` | string | recommended | Also used to derive `content_type`. |
| `content_type` | `contentType` | string | no | MIME type; derived from `filename` if omitted. |
| `content_id` | `contentId` | string | no | Inline images: reference as `<img src="cid:<content_id>">`. Arbitrary string, < 128 chars. |

**Example (TypeScript)**
```ts
import fs from 'node:fs';
const invoice = fs.readFileSync('./invoice.pdf').toString('base64');

const { data, error } = await resend.emails.send({
  from: 'Acme <billing@yourdomain.com>', to: 'delivered@resend.dev', subject: 'Invoice + logo',
  html: '<p>Here is our <img src="cid:logo-image"/> logo and your invoice.</p>',
  attachments: [
    { content: invoice, filename: 'invoice.pdf', contentType: 'application/pdf' },
    { path: 'https://yourdomain.com/static/logo.png', filename: 'logo.png', contentId: 'logo-image' },
  ],
});
```

**Response**: same as Send (`{ id }`).

**Gotchas**
- Whole email ≤ **40 MB including attachments after Base64 encoding**. Needs `content` OR `path`; neither → `422 "Attachment must have either a content or path"`.
- **Not supported on `POST /emails/batch`** (inline images included).
- Blocked on send (receiving is unrestricted): executables/scripts (`.exe .bat .cmd .com .js .jse .vbs .ps1 .msi .reg .scr .lnk .url .hta .chm .cpl .pif .sys .tmp .app` …) and Office macro/DB types (`.mdb .mde .adp` …). Full list: knowledge-base "What attachment types are not supported".
- Inline images: set `filename` or `content_type` so clients render them; some webmail clients reject them. Attachments do not show in the dashboard HTML preview.
- One docs sample sends `text: '<p>Thanks…</p>'` for a local attachment — a docs typo; use `html` for HTML.

### Tags and custom headers
**Endpoint**: `POST /emails` / `POST /emails/batch` (`tags[]`, `headers{}`)  (SDK: `resend.emails.send`)
**Purpose**: `tags` attach key/value metadata echoed back in webhook events and `GET /emails/{id}`; `headers` inject raw mail headers.
**Key parameters**

| Param (JSON) | SDK name | Type | Required | Notes |
|---|---|---|---|---|
| `tags[].name`, `tags[].value` | same | string | yes (per tag) | ASCII letters, digits, `_`, `-` only; ≤ 256 chars each. Max **75 tags** per email. |
| `headers` | `headers` | `Record<string,string>` | no | e.g. `X-Entity-Ref-ID` (prevents Gmail threading), `List-Unsubscribe`, `List-Unsubscribe-Post`. |

**Example (TypeScript)** — see the Send example above for `tags`; unsubscribe headers:
```ts
headers: {
  'List-Unsubscribe': '<https://yourdomain.com/unsubscribe?u=123>',
  'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
},
```

**Gotchas**
- Tag values are strings and cannot contain spaces, dots, `@` or unicode — `value: 'a@b.com'` is rejected; encode IDs instead.
- Resend does not manage unsubscribe lists for transactional mail. Bulk senders (>5,000/day to Gmail/Yahoo) must add `List-Unsubscribe` + `List-Unsubscribe-Post` (RFC 8058) and honour a `POST` to that URL within 48 h.

### Schedule an email
**Endpoint**: `POST /emails` (`scheduled_at`), `PATCH /emails/{email_id}` (reschedule), `POST /emails/{email_id}/cancel`  (SDK: `resend.emails.send`, `resend.emails.update({ id, scheduledAt })`, `resend.emails.cancel(id)`)
**Purpose**: Defer delivery up to **30 days** ahead; change or cancel the scheduled time later.

| Param (JSON) | SDK name | Type | Required | Notes |
|---|---|---|---|---|
| `scheduled_at` | `scheduledAt` | string | no | ISO 8601 (`2026-08-05T11:52:01.858Z`); docs also accept natural language (`"in 1 min"`, `"tomorrow at 9am"`, `"Friday at 3pm ET"`). |
| `email_id` (path) | `id` | string | yes (update/cancel) | The id returned by send. |

**Example (TypeScript)**
```ts
const oneHour = new Date(Date.now() + 60 * 60 * 1000).toISOString();

const { data } = await resend.emails.send({
  from: 'Acme <events@yourdomain.com>',
  to: 'delivered@resend.dev',
  subject: 'Reminder',
  html: '<p>Starts soon.</p>',
  scheduledAt: oneHour,            // or 'in 1 hour'
});

await resend.emails.update({ id: data!.id, scheduledAt: 'in 2 hours' }); // reschedule
await resend.emails.cancel(data!.id);                                     // cancel (irreversible)
```

**Response**: update/cancel → `{ "object": "email", "id": "<email id>" }`. (curl: `PATCH /emails/{id}` with `{"scheduled_at": "..."}`; `POST /emails/{id}/cancel` with no body.)

**Gotchas**
- ⚠ VERIFY: OpenAPI v1.5.1 describes `scheduled_at` as **ISO 8601 only**; the send/batch/schedule docs pages say natural language (`"in 1 min"`) is also accepted. Prefer ISO 8601 in production code.
- ⚠ VERIFY: the Update Email API page says the body is ISO 8601, while the Schedule guide reschedules with `"in 1 min"`; and the OpenAPI summary lists **no request body** for `PATCH /emails/{email_id}` (only a response with `scheduled_at`) although the docs clearly send `{ "scheduled_at": ... }`.
- Once cancelled an email **cannot be rescheduled**; `last_event` becomes `canceled`.
- Scheduled sends fail later if the API key is deleted/expired or the account goes under review. SMTP sends cannot be scheduled.

### Idempotency keys
**Endpoint**: header `Idempotency-Key` on `POST /emails` and `POST /emails/batch`  (SDK: second argument `{ idempotencyKey }`)
**Purpose**: Safe retries — same key + same payload within 24 h returns the original response without sending again.
**Key parameters**: header `Idempotency-Key` (SDK `options.idempotencyKey`), string, 1–256 chars, unique per request, kept **24 h**. Recommended pattern `<event-type>/<entity-id>`, e.g. `welcome-user/123`. SMTP: `Resend-Idempotency-Key` mail header.

**Example (TypeScript)**
```ts
const { data, error } = await resend.emails.send(
  { from: 'Acme <noreply@yourdomain.com>', to: 'delivered@resend.dev', subject: 'Welcome', html: '<p>Hi</p>' },
  { idempotencyKey: `welcome-user/${userId}` },
);
```

**Gotchas**
- ⚠ VERIFY: the Idempotency Keys page and the Send API page pass the key as the **second argument**; the Node quickstart's embedded AI prompt shows `idempotencyKey` **inside the payload object**. Contradictory — use the second-argument form and confirm.
- `400 invalid_idempotency_key` (bad length); `409 invalid_idempotent_request` (same key, different payload — retrying is useless unless you change key or payload); `409 concurrent_idempotent_requests` (a request with that key is still running — retry later).
- For batch the key covers the **whole batch** — pick a key that identifies the batch (`team-quota/123`), not one item.

### Send with a template
**Endpoint**: `POST /emails` / `POST /emails/batch` with `template`  (SDK: `resend.emails.send({ template: { id, variables } })`)
**Purpose**: Render a **published** hosted Template with variable values instead of sending `html`/`text`/`react`.

| Param (JSON) | SDK name | Type | Required | Notes |
|---|---|---|---|---|
| `template.id` | `template.id` | string | yes | Template id **or alias**. Must be published. |
| `template.variables` | `template.variables` | `Record<string, string \| number>` | if a used variable has no fallback | Key: ASCII letters/digits/`_`, ≤ 50 chars; reserved `FIRST_NAME`, `LAST_NAME`, `EMAIL`, `UNSUBSCRIBE_URL` (template page also reserves `contact`, `this`). Value: string ≤ 2,000 chars or number ≤ 2^53−1. |
| `from`, `subject`, `reply_to` | `from`, `subject`, `replyTo` | | if the template has no default | Payload values **override** template defaults. |

**Example (TypeScript)**
```ts
const { data, error } = await resend.emails.send({
  from: 'Acme <orders@yourdomain.com>',
  to: 'delivered@resend.dev',
  subject: 'Order confirmed',                 // overrides the template's default subject
  template: { id: 'order-confirmation', variables: { PRODUCT: 'Laptop', PRICE: 1299 } }, // id or alias
});
```

**Gotchas**
- A used variable with **no value and no fallback** → validation error, email not sent. Unpublished template → error.
- `template` + `html`/`text`/`react` → validation error.
- The template-variables guide calls `variables` an "array of variable objects", but every example and OpenAPI use a plain object `{ KEY: value }` — use the object. Up to 50 variables per template.

### React Email
**Endpoint**: `POST /emails` (`react`)  (SDK only: `resend.emails.send({ react })`)
**Purpose**: Let the Node SDK render a React Email component to HTML for you.

```ts
import { WelcomeEmail } from './emails/welcome';

const { data, error } = await resend.emails.send({
  from: 'Acme <hello@yourdomain.com>', to: 'delivered@resend.dev', subject: 'Welcome',
  react: WelcomeEmail({ name: 'John' }),
});
```

**Gotchas**
- `react` exists only in the Node SDK; it is not a JSON API field (raw API needs `html`).
- ⚠ VERIFY: the Node quickstart prompt insists on a **function call** `WelcomeEmail({ name })`, "not JSX"; the React Email knowledge-base, Hono and Cloudflare Workers guides pass **JSX** `react: <EmailTemplate firstName="John" />`. Both are a `ReactNode`; the call form works in plain `.ts` files.

### Batch send
**Endpoint**: `POST /emails/batch`  (SDK: `resend.batch.send(payloads[], options?)`)
**Purpose**: Send up to **100** independent emails (different recipients/content) in one request.
**Key parameters**: body is a JSON **array** of Send-email objects (same fields, incl. `template`, `tags`, `headers`, per-item `scheduled_at`). Header `Idempotency-Key` applies to the whole batch.

**Example (TypeScript)**
```ts
const { data, error } = await resend.batch.send(
  [
    { from: 'Acme <noreply@yourdomain.com>', to: 'delivered+a@resend.dev', subject: 'A', html: '<p>A</p>' },
    { from: 'Acme <noreply@yourdomain.com>', to: 'delivered+b@resend.dev', subject: 'B', html: '<p>B</p>', scheduledAt: 'in 5 min' },
  ],
  { idempotencyKey: `digest/${runId}` },
);
if (error) return console.error(error);
data!.data.forEach((item, i) => console.log(`email #${i} -> ${item.id}`));
```

**Response**: `{ "data": [ { "id": "..." }, ... ] }` — **index-aligned** with the request array (0-based).

**Gotchas**
- **No `attachments`** (nor inline images) in batch — not supported yet.
- All-or-nothing at validation: if any item is invalid the whole request fails and nothing is sent; there is no per-item error array (unlike SES `SendBulkTemplatedEmail`). Once accepted, each email is processed independently (initial `last_event` = `queued`).
- 100 emails per call; each item still obeys the 50-recipient limit.

### Retrieve a sent email
**Endpoint**: `GET /emails/{email_id}`  (SDK: `resend.emails.get(id)`)
**Purpose**: Fetch a sent email's metadata, bodies and current delivery status.
**Example (TypeScript)**: `const { data, error } = await resend.emails.get(emailId); data?.last_event // 'delivered'`

**Response**: `object: "email"`, `id`, `message_id`, `from`, `to[]`, `cc[]`, `bcc[]`, `reply_to[]`, `subject`, `html`, `text` (may be `null`), `created_at`, `last_event`, plus `scheduled_at` and `tags[]` in the docs sample (absent from the OpenAPI response schema — ⚠ VERIFY).
`last_event` enum: `bounced | canceled | clicked | complained | delivered | delivery_delayed | failed | opened | queued | scheduled | sent | suppressed`.

**Gotchas**: `sent` = handed to the receiving MTA, `delivered` = accepted by it — prefer webhooks over polling. SDK responses keep the JSON `snake_case` field names (`last_event`, `reply_to`).

### List sent emails
**Endpoint**: `GET /emails`  (SDK: `resend.emails.list({ limit?, after?, before? })`)
**Purpose**: Cursor-paginated list of emails **sent** by your team (received mail is `GET /emails/receiving`).
**Key parameters** (query, same names in SDK): `limit` integer, default 20, 1–100; `after` / `before` string cursor = an email `id`, mutually exclusive.

```ts
const { data } = await resend.emails.list({ limit: 50 });
const next = data?.has_more ? await resend.emails.list({ limit: 50, after: data.data.at(-1)!.id }) : null;
```

**Response**: `{ object: "list", has_more, data: [ { id, message_id, from, to[], subject, created_at, last_event, scheduled_at, cc, bcc, reply_to } ] }` — `cc/bcc/reply_to` may be `null`. Use `GET /emails/{id}` for bodies.

### List attachments of a sent email
**Endpoint**: `GET /emails/{email_id}/attachments`, `GET /emails/{email_id}/attachments/{attachment_id}`  (SDK: `resend.emails.attachments.list({ emailId, limit?, after?, before? })`, `resend.emails.attachments.get({ emailId, id })`)
**Purpose**: Enumerate attachments of an email you sent and get a **signed, expiring `download_url`**.

```ts
const { data } = await resend.emails.attachments.list({ emailId });
for (const a of data?.data ?? []) console.log(a.filename, a.content_type, a.size, a.download_url, a.expires_at);
const { data: one } = await resend.emails.attachments.get({ emailId, id: attachmentId });
```

**Response** (item): `id`, `filename` (nullable), `content_type`, `content_id`, `content_disposition` (`inline | attachment`, nullable), `size` (bytes), `download_url`, `expires_at`.

**Gotchas**: `download_url` is signed and expires at `expires_at` — fetch promptly, don't persist it. Paginated like other lists (`limit`, `after`/`before` cursors are attachment ids).

### Test addresses
- `delivered@resend.dev`, `bounced@resend.dev`, `complained@resend.dev`, `suppressed@resend.dev` simulate the corresponding events without hurting reputation. `+label` works on the first three (`delivered+user1@resend.dev`); **`suppressed@` has no label support**.
- `@example.com` / `@test.com` recipients → **422 Unprocessable Entity**.
- **Sender** `onboarding@resend.dev` (the `resend.dev` domain) is test-only: it can only deliver to the **email address of your own Resend account**; anything else → 403 "You can only send testing emails to your own email address". Verify a domain and use it in `from` for real recipients.

### Raw fetch() without the SDK
```ts
const res = await fetch('https://api.resend.com/emails', {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
    'Content-Type': 'application/json',
    'User-Agent': 'my-app/1.0',                 // REQUIRED: omitting it => 403, error code 1010
    'Idempotency-Key': `welcome-user/${userId}`, // optional
  },
  body: JSON.stringify({
    from: 'Acme <noreply@yourdomain.com>',
    to: ['delivered@resend.dev'],
    subject: 'Hello',
    html: '<p>Hello</p>',
    reply_to: 'support@yourdomain.com',          // snake_case on the wire
    scheduled_at: '2026-09-10T09:00:00.000Z',
  }),
});
const body = await res.json(); // 200 => { id }, else { statusCode, name, message }
```
