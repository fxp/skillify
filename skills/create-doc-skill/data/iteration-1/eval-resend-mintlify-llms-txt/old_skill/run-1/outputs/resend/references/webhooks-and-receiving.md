# Resend — Webhooks and Receiving (Inbound) Email

> Source: resend.com/docs + resend-openapi v1.5.1, read 2026-09-03. NOT yet verified against the live API — see verification-plan.md.

## When to read this file

Read this when you need to (a) register or manage webhook endpoints via the API, (b) write a handler that verifies
Resend's Svix-style signature and reacts to `email.*` / `domain.*` / `contact.*` / `suppression.*` events, (c) understand
retry / ordering / duplicate semantics before persisting events, or (d) receive inbound email (`email.received`) and fetch
its body and attachments. Sending is in the emails reference. Examples: TypeScript + official Node SDK; raw HTTP inline.

Contents: 1. Webhook CRUD · 2. Delivered-event inspection · 3. Event types and payload envelope ·
4. Signature verification (Next.js + Express) · 5. Delivery semantics · 6. Receiving (inbound) email

## 1. Webhook CRUD

### Create a webhook
**Endpoint**: `POST /webhooks`  (SDK: `resend.webhooks.create()`)
**Purpose**: Register an HTTPS endpoint and the event types it should receive. The response is the ONLY place
the `signing_secret` is guaranteed to appear on creation (it is also returned by get/list).
**Key parameters**

| Param (JSON) | SDK name | Type | Required | Notes |
|---|---|---|---|---|
| `endpoint` | `endpoint` | string | yes | Public HTTPS URL. Use ngrok / VS Code port-forwarding for local dev. |
| `events` | `events` | string[] | yes | Any subset of the event types in section 3. |

**Example (TypeScript)**
```ts
import { Resend } from 'resend';
const resend = new Resend(process.env.RESEND_API_KEY);

const { data, error } = await resend.webhooks.create({
  endpoint: 'https://example.com/api/resend-webhook',
  events: ['email.delivered', 'email.bounced', 'email.complained', 'email.received'],
});
if (error) throw new Error(error.message);
// Persist data.signing_secret as RESEND_WEBHOOK_SECRET — it is what verify() needs.
console.log(data.id, data.signing_secret);
```
**Example (curl)**
```bash
curl -X POST https://api.resend.com/webhooks \
  -H "Authorization: Bearer $RESEND_API_KEY" -H 'Content-Type: application/json' -H 'User-Agent: my-app/1.0' \
  -d '{"endpoint":"https://example.com/api/resend-webhook","events":["email.delivered","email.bounced"]}'
```
**Response**: `{ object: "webhook", id, signing_secret }` (201). Secret is prefixed `whsec_`.
**Gotchas**: many endpoints per account, each with its own secret (unlike SendGrid's single Event Webhook); `events` must be
a non-empty array (no "all events" flag); a `sending_access` key gets 401 `restricted_api_key` here — use `full_access`.

### Get / list / update / delete
**Endpoints**: `GET /webhooks/{webhook_id}` (`resend.webhooks.get(id)`), `GET /webhooks` (`resend.webhooks.list()`),
`PATCH /webhooks/{webhook_id}` (`resend.webhooks.update(id, {...})`), `DELETE /webhooks/{webhook_id}` (`resend.webhooks.remove(id)`).
**Purpose**: Inspect, rotate endpoint URLs, change subscriptions, re-enable an auto-disabled endpoint, or remove.
PATCH body (all optional, same names in SDK): `endpoint`; `events` (replaces the whole list, not a merge);
`status: 'enabled' | 'disabled'` (set `enabled` to revive an endpoint Resend auto-disabled after persistent failures).
**Example (TypeScript)**
```ts
const { data: hooks } = await resend.webhooks.list({ limit: 50 });        // { object:'list', has_more, data:[{id,endpoint,events,status,created_at}] }
const { data: one }   = await resend.webhooks.get(hookId);                // same fields + signing_secret
await resend.webhooks.update(hookId, { events: ['email.bounced'], status: 'enabled' });
await resend.webhooks.remove(hookId);                                     // { object:'webhook', id, deleted:true }
```
**Gotchas**: list is cursor-paginated (`limit`, `after` XOR `before`, read `has_more`); list items omit `signing_secret`;
`events` is typed `array|null` in the OpenAPI spec — guard against `null`.

## 2. Inspecting events delivered to a webhook

### List events, get one event, list delivery attempts
**Endpoints**: `GET /webhooks/{webhook_id}/events` (`resend.webhooks.events.list({ webhookId })`),
`GET /webhooks/{webhook_id}/events/{event_id}` (`resend.webhooks.events.get({ webhookId, eventId })`),
`GET /webhooks/{webhook_id}/events/{event_id}/attempts` (`resend.webhooks.events.attempts.list({ webhookId, eventId })`).
**Purpose**: Debug "did Resend call me?" without the dashboard — delivery `status`, the exact `payload` sent, and the
HTTP status / body your endpoint returned per attempt. Query: `limit` (1–100, default 20), `after` cursor —
**`before` is NOT supported** on these two lists.
**Example (TypeScript)**
```ts
const { data: ev } = await resend.webhooks.events.get({ webhookId, eventId: 'msg_...' });
// ev: { object:'webhook_event', id, type, created_at, status:'pending'|'attempting'|'success'|'failed', next_attempt_at|null, payload }
const { data: at } = await resend.webhooks.events.attempts.list({ webhookId, eventId: ev.id });
for (const a of at.data) console.log(a.http_status_code, a.response, a.sent_at);   // most recent first
```
**Gotchas**: event ids are Svix message ids (`msg_…`) — identical to the `svix-id` header your handler sees, so use them to
correlate; `next_attempt_at` is `null` once `success`/`failed`; replay is dashboard-only (no API endpoint in the spec).

## 3. Event types and payload envelope

| Group | Types |
|---|---|
| Email | `email.sent`, `email.delivered`, `email.delivery_delayed`, `email.complained`, `email.bounced`, `email.opened`, `email.clicked`, `email.failed`, `email.received`, `email.scheduled`, `email.suppressed` |
| Domain | `domain.created`, `domain.updated`, `domain.deleted` |
| Contact | `contact.created`, `contact.updated`, `contact.deleted` (NOT fired for CSV imports) |
| Suppression | `suppression.added`, `suppression.removed` |

Common envelope for `email.*` events:
```ts
type ResendEmailEvent = {
  type: string; created_at: string;            // created_at (ISO 8601) is what you sort by
  data: {
    email_id: string;                          // == id returned by emails.send
    message_id: string;                        // RFC Message-ID '<...@...>'
    created_at: string; from: string; to: string[]; subject: string;
    tags?: Record<string, string>;             // OBJECT keyed by tag name — NOT the [{name,value}] array you send
    broadcast_id?: string; template_id?: string;
    bounce?: { type: 'Permanent'|'Temporary'; subType: string; message: string; diagnosticCodes?: string[] }; // email.bounced
    click?:  { ipAddress: string; link: string; timestamp: string; userAgent: string };                        // email.clicked
  };
};
```
**Gotchas**
- `tags` arrives as `{ category: "welcome" }`, while `emails.send` takes `tags: [{ name, value }]` — do not reuse your send type.
- `bounce.subType === 'Suppressed'` = Resend refused to send because the address is on your suppression list.
- `email.received` has a different `data` shape (section 6): bare-address `from`, plus `cc`, `bcc`, `received_for`, `attachments[]` metadata.
- `email.opened`/`email.clicked` fire only with tracking enabled AND a verified tracking subdomain; Gmail rarely emits `complained`.

## 4. Signature verification

Every delivery carries three headers: `svix-id`, `svix-timestamp`, `svix-signature`. Verification MUST use the
raw request body string — parsing to JSON and re-stringifying breaks the signature. The secret is the webhook's
`signing_secret` (`whsec_…`), not your API key.

### SDK: `resend.webhooks.verify()`
**Endpoint**: local, no HTTP call  (SDK: `resend.webhooks.verify({ payload, headers: { id, timestamp, signature }, webhookSecret })`)
**Purpose**: Throws if the signature/timestamp is invalid; returns the parsed event object on success.

⚠ VERIFY: the docs example reads `req.headers['svix-id']` on a `NextRequest`; on a Fetch `Headers` object that is
`undefined` — use `req.headers.get('svix-id')` (as below). The docs also call `verify()` without `await`; `await` it anyway.

**Example (TypeScript — Next.js App Router, `app/api/resend-webhook/route.ts`)**
```ts
import { NextRequest, NextResponse } from 'next/server';
import { Resend } from 'resend';
const resend = new Resend(process.env.RESEND_API_KEY);

export async function POST(req: NextRequest) {
  const payload = await req.text();                       // RAW body — never req.json() first
  let event: any;
  try {
    event = await resend.webhooks.verify({
      payload,
      headers: {
        id: req.headers.get('svix-id') ?? '',
        timestamp: req.headers.get('svix-timestamp') ?? '',
        signature: req.headers.get('svix-signature') ?? '',
      },
      webhookSecret: process.env.RESEND_WEBHOOK_SECRET!,
    });
  } catch {
    return new NextResponse('Invalid signature', { status: 400 });
  }

  // At-least-once delivery → dedupe on svix-id before side effects:
  // if (await alreadyProcessed(req.headers.get('svix-id')!)) return NextResponse.json({ ok: true });
  if (event.type === 'email.bounced' && event.data.bounce?.type === 'Permanent') { /* drop event.data.to[] */ }
  if (event.type === 'email.received') { /* enqueue event.data.email_id; fetch body later (section 6) */ }
  return NextResponse.json({ ok: true });                 // 2xx quickly; do heavy work async
}
```

**Example (TypeScript — Express / plain Node with the `svix` package)**
```ts
import express from 'express';
import { Webhook } from 'svix';                           // npm install svix

const app = express();
const wh = new Webhook(process.env.RESEND_WEBHOOK_SECRET!);

// express.raw keeps the body a Buffer; express.json() on this route would break verification.
app.post('/api/resend-webhook', express.raw({ type: 'application/json' }), (req, res) => {
  let event: any;
  try {
    event = wh.verify(req.body.toString('utf8'), {
      'svix-id': req.header('svix-id')!, 'svix-timestamp': req.header('svix-timestamp')!, 'svix-signature': req.header('svix-signature')!,
    });
  } catch { return res.status(400).send('Invalid signature'); }
  res.status(200).json({ ok: true });                     // ack first …
  void handleEvent(event, req.header('svix-id')!);        // … then process (dedupe on svix-id inside)
});
```
**Gotchas**: frameworks that auto-parse JSON (Next.js Pages API `bodyParser`, Express `json()`, NestJS) must have body
parsing disabled for this route or every verification fails; `svix` also rejects stale timestamps (replay protection) —
keep clocks in sync; `svix-signature` can hold several space-separated `v1,<sig>` values during secret rotation.

## 5. Delivery semantics (design your handler around these)

- **Respond 2xx fast.** Anything else (or a timeout) counts as failure and triggers retries. Queue heavy work.
- **At-least-once.** Duplicates happen (e.g. your 200 was lost). Store processed `svix-id` values and skip repeats.
- **Order NOT guaranteed.** `email.opened` can arrive before `email.delivered`. Sort by `created_at`; never drive a state machine off arrival order.
- **Retry schedule** — ⚠ VERIFY, the docs disagree with themselves: *Managing Webhooks* FAQ says 5s → 5m → 30m → 2h → 5h → 10h
  (6 retries); *Retries and Replays* says Immediately → 5s → 5m → 30m → 2h → 5h → 10h → 10h (8 attempts). Each interval starts
  after the previous failure; either way retries span roughly a day.
- **Auto-disable.** Persistent failure → email notice → endpoint disabled (second notice). Re-enable in the dashboard or via
  `PATCH /webhooks/{id}` `status: 'enabled'`. Disabled/removed endpoints get no attempts.
- **Replays** (dashboard only): `failed` AND `succeeded` events can be replayed (backfill, reprocess, test a new endpoint) — your
  dedupe must tolerate deliberate re-sends.
- **Source IPs** for allowlisting: `44.228.126.217`, `50.112.21.217`, `52.24.126.164`, `54.148.139.208`, `2600:1f24:64:8000::/52`.
- **Local dev:** `resend webhooks listen` (CLI) registers a temporary webhook and streams events to your terminal.

## 6. Receiving (inbound) email

Prerequisites: use the account's Resend-managed `<id>.resend.app` subdomain (Emails → Receiving tab; any username works, no
DNS) or enable `capabilities.receiving` on a verified domain and add the returned `Receiving` **MX** record — on a dedicated
subdomain if the domain already has MX records, since mail only reaches the lowest-priority MX. Then subscribe a webhook to
`email.received`. **That webhook carries metadata ONLY** (`email_id`, `from`, `to`, `cc`, `bcc`, `received_for`, `subject`,
`message_id`, `attachments[{id, filename, content_type, content_disposition, content_id}]`); body, headers and attachment
bytes must be fetched with the endpoints below (by design, so large attachments survive serverless body-size limits).

### Retrieve a received email
**Endpoint**: `GET /emails/receiving/{email_id}`  (SDK: `resend.emails.receiving.get(id)`)
**Purpose**: Get `html`, `text`, `headers`, recipients and attachment metadata for one inbound message. Path `email_id` =
`event.data.email_id`. Optional query `html_format=data_uri|cid` (default `data_uri` inlines images as base64; `cid` keeps
`<img src="cid:…">` so you can map to `attachments[].content_id`) — docs only, absent from the OpenAPI summary; SDK
option name ⚠ VERIFY (`htmlFormat`?).
**Example (TypeScript)**
```ts
const { data: mail, error } = await resend.emails.receiving.get(event.data.email_id);
if (error) throw new Error(error.message);
console.log(mail.headers?.from);         // original From: with display name (webhook `from` is bare address)
console.log(mail.text ?? mail.html);     // either may be null
console.log(mail.raw?.download_url);     // signed URL for the full .eml incl. attachments; expires_at ~1h
// curl: GET "https://api.resend.com/emails/receiving/$EMAIL_ID?html_format=cid" -H "Authorization: Bearer $RESEND_API_KEY" -H 'User-Agent: x'
```
**Response**: `{ object:'email', id, from, to, cc, bcc, reply_to, received_for, subject, html, html_format, text, headers, message_id, created_at, raw:{download_url, expires_at}|null, attachments:[{id, filename, content_type, content_disposition, content_id, size}] }`.
**Gotchas**: `raw` and `html_format` are in the docs response but NOT the OpenAPI summary (⚠ VERIFY); 403 `email_above_quota`
means the message arrived while you were over quota and its content is unavailable — **received emails count 1:1 against
the same daily/monthly quota as sent mail** (free tier: 100/day, 3,000/month combined); attachment entries here carry NO
`download_url` — use the attachments endpoint.

### List received-email attachments / get one
**Endpoints**: `GET /emails/receiving/{email_id}/attachments` (`resend.emails.receiving.attachments.list({ emailId })`),
`GET /emails/receiving/{email_id}/attachments/{attachment_id}` (`resend.emails.receiving.attachments.get({ emailId, attachmentId })`).
**Purpose**: Obtain a temporary signed `download_url` per attachment. Paginated with `limit` / `after` / `before`.
**Example (TypeScript)**
```ts
const { data: list } = await resend.emails.receiving.attachments.list({ emailId: event.data.email_id });
for (const a of list.data) {
  if (new Date(a.expires_at) < new Date()) continue;     // re-list to get a fresh URL
  const res = await fetch(a.download_url);              // plain fetch — no Authorization header on the CDN URL
  if (!res.ok) continue;
  const bytes = Buffer.from(await res.arrayBuffer());   // a.filename may be null → pick your own name
}
```
**Response**: `{ object:'list', has_more, data:[{ id, filename|null, content_type, content_id, content_disposition:'inline'|'attachment'|null, size, download_url, expires_at }] }`.
**Gotchas**: `download_url` lives **1 hour** — persist bytes, not URLs, and re-list for a fresh one; inline images are already
embedded in `html` unless you requested `html_format=cid`.

### List received emails
**Endpoint**: `GET /emails/receiving`  (SDK: `resend.emails.receiving.list({ limit?, after?, before? })`)
**Purpose**: Poll or backfill inbound mail without webhooks (e.g. after an outage). Metadata + attachment metadata only;
cursor pagination on email id (`after` XOR `before`), read `has_more`.
**Example (TypeScript)**
```ts
const { data } = await resend.emails.receiving.list({ limit: 100 });
for (const m of data.data) { /* m.id, m.from, m.to, m.subject, m.created_at, m.attachments */ }
const next = data.has_more ? data.data.at(-1)?.id : undefined;   // pass as `after`
```
**Gotchas**: lists only *received* mail (sent mail is `GET /emails`); any username at the receiving domain is accepted, so
route on `to[]` / `received_for[]` yourself; reply in-thread by sending with `headers: { 'In-Reply-To': mail.message_id,
References: mail.message_id }` (see the emails reference).
