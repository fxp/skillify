# Resend skill — real-API verification plan

Status: **not executed** (no `RESEND_API_KEY` at draft time, 2026-09-03). Run this before treating the skill as verified. Estimated cost: free tier is enough (all sends go to `*@resend.dev` test addresses; ~20 emails total).

## Setup

1. Create a **full_access** API key in the Resend dashboard and export it only in the shell: `export RESEND_API_KEY=…` (never write it to a file in the repo).
2. Optional but strongly recommended: verify a throwaway subdomain (e.g. `test.<yourdomain>`) so domain-related checks (V9–V11, V14) are meaningful. Without it, all sends must use `from: onboarding@resend.dev` and `to:` = the account owner's address, which limits the test-address checks.
3. Use `uv run --with httpx python …` or a scratch Node project with `npm i resend` — do not install globally.
4. After the run: `grep -r "re_[A-Za-z0-9]\{20,\}" <skill dir>` must return nothing before committing.

Each item below says what to call, what the docs claim, and which reference file/line to update with `(verified 2026-MM, <observed>)` or to correct.

## A. Blocking contradictions found while reading the docs (`⚠ VERIFY` markers)

| # | Check | Docs claim(s) | How to test | Update |
|---|---|---|---|---|
| V1 | Idempotency key placement in Node SDK | `dashboard/emails/idempotency-keys`: 2nd arg `{ idempotencyKey }`. `send-with-nodejs` AI-prompt block: `idempotencyKey` **inside** the payload. | Send twice with the same key using each form; the correct form returns the **same** `id` twice and only one email in the dashboard. Also check the SDK's TypeScript types. | `SKILL.md` cross-cutting rules; `sending.md` § Idempotency |
| V2 | `scheduled_at` natural language | Docs: `"in 1 min"`, `"tomorrow at 9am"` accepted. OpenAPI: ISO 8601 only. | `POST /emails` with `scheduled_at: "in 2 min"` and with ISO; confirm 200 + `last_event: scheduled`; then `PATCH` with natural language. | `sending.md` § Scheduling |
| V3 | `resend.webhooks.verify()` signature & header access | Example reads `req.headers['svix-id']` on a `NextRequest` (which has `.get()`); return value described as parsed payload. | Create a webhook via API, trigger `email.sent`, capture headers+raw body, call `verify()` with `headers.get(...)` values; confirm it returns the parsed object and throws on a tampered body. | `webhooks-and-receiving.md` § Verify |
| V4 | Webhook retry schedule | `webhooks/introduction` FAQ: 5 s, 5 m, 30 m, 2 h, 5 h, 10 h. `webhooks/retries-and-replays`: Immediately, 5 s, 5 m, 30 m, 2 h, 5 h, 10 h, 10 h. | Point a webhook at an endpoint returning 500; read attempts from `GET /webhooks/{id}/events/{event_id}/attempts` over ~1 h (first four steps) and note timestamps. | `webhooks-and-receiving.md` § Retries; `errors-and-limits.md` table |
| V5 | Chained `resend.templates.create({...}).publish()` | Shown on `dashboard/templates/create-template`. | Check the SDK return type; if `create()` returns a Promise of `{data,error}`, chaining is impossible — replace with a two-call example. | `audiences-and-broadcasts.md` § Templates |
| V6 | React `react:` param — function call vs JSX | `send-with-nodejs`: pass `WelcomeEmail({ name })` (not JSX). `template-emails-with-react-email`: `react: <Email url=… />`. | Send both forms from a `.tsx` file; both should work if `react` accepts `ReactNode`; record which the types accept. | `sending.md` § React |
| V7 | `restricted_api_key` status code | Listed under both 401 and 403 with different messages. | Create a `sending_access` key and call `GET /domains`; record status + body. | `errors-and-limits.md` |
| V8 | Missing `User-Agent` behaviour | Docs: 403, error code 1010, non-API error page. | Python `httpx` with `headers={"User-Agent": ""}` (or raw socket) to `GET /domains`; record exact status/body. Also confirm a `fetch()` from Node 20 (which sends `undici` UA) succeeds. | `SKILL.md`, `sending.md` raw-fetch example |

## B. "Required" and "response-field" claims to confirm

| # | Check | How |
|---|---|---|
| V9 | `POST /emails` truly requires `subject` (OpenAPI: required) and at least one of `html`/`text`/`react`/`template` (docs, not in OpenAPI `required`) | Omit each in turn; expect 422 `missing_required_field` / `validation_error`; record the message text. |
| V10 | `text: ""` opts out of auto-generated plain text | Send with `html` + `text: ""`, then `GET /emails/{id}` and check `text`. |
| V11 | `to` max 50 — per field or combined with cc/bcc? | Send with 51 in `to` (expect 422); then 30 to + 30 cc (does it pass?). Use `delivered+N@resend.dev` labels. |
| V12 | Batch: attachments rejected (not silently dropped); whole batch fails on one invalid item; `data[]` index-aligned | `POST /emails/batch` with one attachment → expect 4xx. Batch of 3 with the 2nd invalid → expect no ids at all. Batch of 3 valid → ids order matches. |
| V13 | `GET /emails` shape: `has_more`, `last_event` enum values, whether `html`/`text` are included in list items (OpenAPI says yes — surprising for a list) | Call with `limit=2`; diff the JSON against `sending.md` response table. |
| V14 | `POST /domains` response contains `records[]` with `priority` on MX and `TrackingCAA`; `status` initial value (`pending` vs `not_started`) | Create `test-verify.<domain>`, print records, delete afterwards. |
| V15 | `POST /webhooks` returns `signing_secret` in the create response (OpenAPI yes) and whether `GET /webhooks/{id}` also returns it (docs say yes) | Create, get, list; then delete. |
| V16 | Received-email webhook carries no body; `GET /emails/receiving/{id}` returns `html`, `text`, `headers`; attachments endpoint returns `download_url` that expires | Requires receiving enabled on a domain or the `<id>.resend.app` address; send an email with an attachment to it. |
| V17 | Rate-limit headers present on every response (`ratelimit-limit`, `ratelimit-remaining`, `ratelimit-reset`) and `retry-after` on 429; quota headers `x-resend-daily-quota` | Fire 15 `GET /domains` in <1 s with `httpx`; capture headers of the first 200 and the first 429. |
| V18 | Pagination: `limit` omitted on `GET /contacts` returns **all**; `GET /emails` always paginates (default 20); `after`+`before` together → 422 `validation_error` | Three calls; record statuses and `has_more`. |
| V19 | Test addresses: `bounced@resend.dev` produces `email.bounced` webhook; `+label` works; `suppressed@resend.dev` rejects labels; `user@example.com` → 422 | Send four emails, watch dashboard/webhook. Requires a verified domain (`onboarding@resend.dev` can only send to the owner's address). |
| V20 | Template variable rules: reserved names rejected on create; missing variable without fallback → validation error on send; alias accepted in `template.id` and in `/templates/{id}/publish` | Create template with `FIRST_NAME` var (expect error), then a valid one with alias; publish by alias; send with and without the variable. Delete afterwards. |
| V21 | Contacts: `PATCH /contacts/{email}` works with an email address as the path id; `audience_id` optional (legacy) | Create contact, update by email, delete. |
| V22 | Broadcast `send: true` + `scheduled_at`; `POST /broadcasts/{id}/send` rejects dashboard-created broadcasts | Only if a segment with test contacts exists; otherwise skip and leave the marker. |
| V23 | SDK exposes response headers? | Inspect `resend` package source/types for `headers` on the result; if absent, keep the "use fetch for retry-after" note. |

## C. Cleanup checklist after the run

- Delete: test domain(s), test webhook(s), test template(s), test contact(s)/segment(s), any sending-only API key created for V7.
- Cancel any scheduled email left from V2.
- `grep` the skill directory and shell history file for key material.

## D. Recording format

In the reference file, replace the `⚠ VERIFY:` line with:

```
✅ Verified 2026-MM-DD against api.resend.com (SDK resend@x.y.z): <one-line observed behaviour>. Evidence: <status code + first 120 chars of response body>.
```

Keep the original docs claim in the same bullet if it turned out to be wrong, tagged `DOC-DISCREPANCY:` so future readers know the docs cannot be trusted on that point.

## E. Comparison-eval linkage

`resend/evals/evals.json` scenarios 1–8 are graded from the generated code. Items V1 (scenario 2), V2/V9 (scenario 3), V3 (scenario 4), V5/V20 (scenario 5), V14 (scenario 6), V18 (scenario 7) and V16 (scenario 8) determine whether the "skill-recommended" answer is actually the *correct* one — re-grade those scenarios after the verification run using the observed responses as ground truth, per the methodology's rule "score by real API behaviour, not by how the code reads".
