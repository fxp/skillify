---
name: resend
description: Write correct code against the Resend email API (resend.com, api.resend.com, the `resend` npm package / Node SDK, Python `resend`, Go `resend-go`, etc.) on the first try — sending transactional email, batch sends, scheduling, attachments, templates, contacts/segments/topics/broadcasts, domains and DNS records, API keys, suppressions, webhooks (Svix-signed) and inbound email receiving. Use this skill whenever a task mentions Resend, `resend.emails.send`, `RESEND_API_KEY`, `onboarding@resend.dev`, a Resend webhook, or "send an email from my Node/Next.js/serverless app" where Resend is the chosen provider — even for a one-line send. It captures field names, required params, limits and doc contradictions that an engineer used to SendGrid/SES/Postmark/Mailgun will otherwise guess wrong (User-Agent requirement, camelCase vs snake_case, batch has no attachments, idempotency key placement, raw-body webhook verification).
---

# Resend API skill

> Source: resend.com/docs (llms.txt export) + github.com/resend/resend-openapi v1.5.1, read 2026-09-03.
> **Status: draft — NOT yet verified against the live API** (no API key was available). Every `⚠ VERIFY` marker in `references/` is a point where the docs contradict themselves, the OpenAPI spec, or general expectations. See `verification-plan.md` next to this skill before trusting those points in production.

## Where to look (read only the file you need)

| I want to… | Read | Endpoints / SDK |
|---|---|---|
| Send one email (html / text / React / template), attachments, tags, custom headers, scheduling, idempotent retries, cancel/reschedule, look up a sent email | `references/sending.md` | `POST /emails`, `GET/PATCH /emails/{id}`, `POST /emails/{id}/cancel` — `resend.emails.*` |
| Send up to 100 different emails in one call | `references/sending.md` § Batch | `POST /emails/batch` — `resend.batch.send()` |
| Reusable templates with `{{{VARIABLES}}}`, marketing contacts, segments, topics, broadcasts (newsletters), custom events | `references/audiences-and-broadcasts.md` | `/templates`, `/contacts`, `/segments`, `/topics`, `/broadcasts`, `/events` |
| Receive delivery/bounce/open/click events; verify webhook signatures; process inbound email | `references/webhooks-and-receiving.md` | `/webhooks/*`, `GET /emails/receiving/*` — `resend.webhooks.verify()`, `resend.emails.receiving.get()` |
| Add/verify a sending domain, print DNS records, manage API keys, suppression list, request logs | `references/domains-and-account.md` | `/domains`, `/api-keys`, `/suppressions`, `/logs` |
| Decode an error code, know the limits (rate, quota, size, recipients) | `references/errors-and-limits.md` | — |

## Cross-cutting rules (apply to every endpoint)

**Base URL & auth.** `https://api.resend.com` (HTTPS only, no versioning yet). Header `Authorization: Bearer <key>`. Keys look like `re_…`; read them from `process.env.RESEND_API_KEY`, never hard-code.

**Raw HTTP needs a `User-Agent` header.** Requests without one are rejected with HTTP 403 and error code `1010` *before* reaching the API, so the API key looks "invalid" even when it is fine. The SDKs and the CLI set it for you; `fetch()` in some runtimes does not. Prefer the SDK unless there is no SDK for the runtime.

**Node SDK shape (TypeScript).**
```ts
import { Resend } from 'resend';               // package name is exactly `resend`
const resend = new Resend(process.env.RESEND_API_KEY);

const { data, error } = await resend.emails.send({
  from: 'Acme <notifications@yourdomain.com>',  // verified domain in prod
  to: ['delivered@resend.dev'],
  subject: 'Hello',
  html: '<p>It works</p>',
});
if (error) { /* { name, message } — the SDK does NOT throw on API errors */ }
console.log(data?.id);
```
- SDK params are **camelCase** (`replyTo`, `scheduledAt`, `contentId`, `segmentId`, `fallbackValue`); the JSON API is **snake_case** (`reply_to`, `scheduled_at`, `content_id`). Mixing them silently drops the field.
- Per-request options (e.g. `{ idempotencyKey }`) go in the **second argument** of `send()` / `batch.send()`, not inside the payload (one quickstart page shows it inside the payload — `⚠ VERIFY`).
- Every call resolves `{ data, error }`; only wrap in `try/catch` for network failures.

**Sender rules.** `from` must be on a verified domain; until then only `onboarding@resend.dev` works and it can only deliver to the account owner's own address (403 `validation_error`). Use `Name <addr@domain>` for a display name. Recipients: `to`/`cc`/`bcc` each accept `string | string[]`, max 50 addresses in `to`.

**Testing without hurting reputation.** `delivered@resend.dev`, `bounced@resend.dev`, `complained@resend.dev`, `suppressed@resend.dev` simulate events; `+label` suffixes work (except on `suppressed@`). Sending to `@example.com` / `@test.com` returns 422.

**Limits to remember.** 10 requests/second per team (429 `rate_limit_exceeded`, honour `retry-after`); daily/monthly email quotas also return 429; 40 MB per email after base64; batch = 100 emails and **no attachments**; 75 tags per email; scheduling up to 30 days ahead; idempotency keys live 24 h, ≤256 chars.

**Pagination.** Cursor-based: query `limit` (1–100, default 20), `after` = id of last item, `before` = id of first item, never both; response `{ object: 'list', has_more, data }`. Older list endpoints return everything when `limit` is omitted; `GET /emails`, `/templates`, `/topics` always paginate.

**Webhooks.** Signed by Svix (`svix-id`, `svix-timestamp`, `svix-signature`); verify against the **raw body string**, not re-serialised JSON. Delivery is at-least-once and unordered — dedupe on `svix-id`, sort by `created_at`. Inbound `email.received` events carry metadata only; fetch the body via `GET /emails/receiving/{id}`.

**Sync vs async.** Sending is synchronous at the API level (you get an `id` immediately) but delivery is asynchronous — track `last_event` via `GET /emails/{id}` or webhooks. Broadcasts and contact imports are asynchronous jobs.

## When the docs disagree with themselves

The reference files mark each one `⚠ VERIFY`. The ones most likely to bite: idempotency-key placement in the Node SDK; `scheduled_at` natural-language support (docs say yes, OpenAPI says ISO 8601 only); the `resend.webhooks.verify()` header access pattern in the Next.js example; the two different webhook retry schedules; the chained `templates.create(...).publish()` snippet. Resolve them with a real key using `verification-plan.md` and then update the reference file with the date and the observed response.

## Other entry points worth knowing

- **CLI** (`npm install -g resend-cli` or `brew install resend/cli/resend`, then `resend login`): `resend emails send …`, `resend webhooks listen` for local webhook development, `resend templates …`.
- **MCP server**: `npx -y resend-mcp` with `RESEND_API_KEY` in the environment (or the hosted server) lets an agent list/read/send email directly; see resend.com/docs/mcp-server.
- **SMTP**: host `smtp.resend.com`, port 465, user `resend`, password = API key; scheduling is not supported over SMTP; idempotency via the `Resend-Idempotency-Key` header.
- **React Email**: `react:` param on `emails.send` (Node only); mutually exclusive with `html`/`text`/`template`.
