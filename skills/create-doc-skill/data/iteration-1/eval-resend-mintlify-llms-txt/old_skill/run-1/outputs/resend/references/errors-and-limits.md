# Errors, limits and quotas

> Source: resend.com/docs/api-reference/{introduction,errors,rate-limit,pagination} + resend-openapi v1.5.1, read 2026-09-03. NOT yet verified against the live API — see verification-plan.md.

Read this when: a call returns a non-2xx status, you are designing retry/queue logic, or you need to know a size/count limit before building a payload.

## Error envelope

```json
{ "name": "validation_error", "statusCode": 422, "message": "The pagination limit must be a number between 1 and 100. ..." }
```

The Node SDK surfaces the same thing as `error` in `{ data, error }` (`error.name`, `error.message`). It does **not** throw for API errors.

## HTTP status → meaning

| Status | Meaning per docs | Typical `name` |
|---|---|---|
| 200 / 201 / 202 | OK / created / accepted (async, e.g. `POST /events/send`) | — |
| 400 | Bad parameters | `validation_error`, `invalid_idempotency_key` |
| 401 | API key missing, or key restricted to sending only | `missing_api_key`, `restricted_api_key` |
| 403 | Key invalid/inactive/suspended, domain not verified, test-sender restriction, over contact quota, missing OAuth scope, **or missing `User-Agent` (error code 1010, not a JSON error)** | `restricted_api_key`, `suspended_api_key`, `validation_error`, `invalid_permission`, `email_above_quota` |
| 404 | Endpoint or resource not found | `not_found` |
| 405 | Wrong method | `method_not_allowed` |
| 409 | Idempotency conflicts, resource locked | `invalid_idempotent_request`, `concurrent_idempotent_requests`, `resource_locked` |
| 422 | Semantic validation (missing field, bad UUID, bad attachment, `@example.com` recipient, pagination out of range) | `missing_required_field`, `missing_required_parameter`, `invalid_parameter`, `invalid_attachment`, `validation_error` |
| 429 | Rate limit **or** daily/monthly quota | `rate_limit_exceeded`, `daily_quota_exceeded`, `monthly_quota_exceeded` |
| 500 / 503 | Resend-side | `application_error`, `service_unavailable` |

Note the docs' intro table says 401 = "key missing", 403 = "key invalid" — but `restricted_api_key` appears under **both** 401 and 403 with different messages. Branch on `name` + `message`, not on status alone.

## Full error-name table (from docs/api-reference/errors)

| `name` | Status | Message (abridged) | What to do |
|---|---|---|---|
| `invalid_idempotency_key` | 400 | key must be 1–256 chars | fix key |
| `validation_error` | 400 | field-level problem, details in message | read message |
| `missing_api_key` | 401 | no Authorization header | add `Authorization: Bearer …` |
| `restricted_api_key` | 401 | key is sending-only | use a `full_access` key for non-send endpoints |
| `email_above_quota` | 403 | can't retrieve content, received while over quota | upgrade plan |
| `invalid_permission` | 403 | OAuth token lacks scopes | request proper scopes |
| `restricted_api_key` | 403 | key not active | create a new key |
| `suspended_api_key` | 403 | key suspended | contact support |
| `validation_error` | 403 | "You can only send testing emails to your own email address" | verify a domain, change `from` |
| `validation_error` | 403 | "The X domain is not verified" | `from` domain must be verified |
| `validation_error` | 403 | "domain has been registered already" | claim the domain / check team |
| `validation_error` | 403 | "You have reached your contacts quota" (broadcast send) | upgrade marketing plan |
| `not_found` | 404 | endpoint does not exist | check URL |
| `method_not_allowed` | 405 | | check method |
| `concurrent_idempotent_requests` | 409 | same key in progress | retry later |
| `invalid_idempotent_request` | 409 | same key, different body within 24 h | new key or same body |
| `resource_locked` | 409 | another update in flight | retry after short delay |
| `invalid_attachment` | 422 | attachment needs `content` or `path` | fix attachment |
| `invalid_parameter` | 422 | e.g. not a valid UUID | fix value |
| `missing_required_field` | 422 | body missing fields (listed in message) | add fields |
| `missing_required_parameter` | 422 | query/path params missing | add params |
| `daily_quota_exceeded` | 429 | free-plan daily quota | wait 24 h / upgrade |
| `monthly_quota_exceeded` | 429 | monthly quota | upgrade |
| `rate_limit_exceeded` | 429 | too many req/s | back off, queue |
| `application_error` | 500 | unexpected | retry later; status page |
| `service_unavailable` | 503 | | retry later |

Undocumented-but-observed cases to expect (mark as `⚠ VERIFY` until tested): 403 with a non-JSON/Cloudflare-style body and code `1010` when `User-Agent` is missing; 422 when sending to `@example.com`/`@test.com`.

## Rate limits

- **10 requests/second per team** across all API keys (can be raised by support). Applies to every endpoint, including `GET`s used for pagination.
- Response headers (IETF draft-06 names, lowercase): `ratelimit-limit`, `ratelimit-remaining`, `ratelimit-reset` (seconds), `retry-after` (seconds, on 429).
- Quota headers: `x-resend-daily-quota` (free plan only), `x-resend-monthly-quota` — *used* amounts.
- Sent **and received** emails count toward daily/monthly quotas.
- Contact quota: you can exceed it when adding contacts, but broadcast sends fail with 403 until you upgrade.

Retry policy that fits these rules (TypeScript sketch):

```ts
async function withBackoff<T>(fn: () => Promise<{ data: T | null; error: { name: string; message: string } | null }>, attempts = 5) {
  for (let i = 0; i < attempts; i++) {
    const res = await fn();
    if (!res.error) return res;
    const retryable = ['rate_limit_exceeded', 'concurrent_idempotent_requests', 'resource_locked', 'application_error', 'service_unavailable'];
    if (!retryable.includes(res.error.name)) return res;      // quota errors are NOT retryable within the window
    await new Promise(r => setTimeout(r, Math.min(30_000, 500 * 2 ** i)));
  }
  throw new Error('Resend: retries exhausted');
}
// Use an Idempotency-Key on every send you might retry, so a retried POST /emails cannot double-send.
```

The SDK does not expose response headers in `{ data, error }` (`⚠ VERIFY` — if you need `retry-after`, call the REST API with `fetch` and read `res.headers`).

## Size / count limits (collected from all pages)

| Thing | Limit |
|---|---|
| Recipients in `to` | 50 (docs also apply "max 50" to cc/bcc arrays — `⚠ VERIFY` whether the cap is per field or combined) |
| Email size incl. attachments (after base64) | 40 MB |
| Batch size | 100 emails per `POST /emails/batch`; attachments not supported in batch |
| Tags per email | 75; `name`/`value` ASCII letters, digits, `_`, `-`; ≤256 chars each |
| Template variable key | ≤50 chars; letters/digits/`_`; reserved: `FIRST_NAME`, `LAST_NAME`, `EMAIL`, `UNSUBSCRIBE_URL` |
| Template variable value | string ≤2,000 chars; number ≤ 2^53−1 |
| Attachment `content_id` | <128 chars |
| Idempotency key | 1–256 chars; remembered 24 h; only on `POST /emails` and `POST /emails/batch` |
| Scheduling horizon | up to 30 days ahead; not available over SMTP |
| Pagination `limit` | 1–100, default 20; `after` xor `before` |
| Suppression batch | 100 per add/remove call |
| Webhook retry schedule | ~5 s → 5 min → 30 min → 2 h → 5 h → 10 h (+10 h) with auto-disable on persistent failure (`⚠ VERIFY` exact schedule; two pages differ) |
| Unsupported attachment types | see docs/knowledge-base/what-attachment-types-are-not-supported (executables, scripts etc.) |

## Pagination contract

```
GET /contacts?limit=50               → { object: "list", has_more: true, data: [...] }
GET /contacts?limit=50&after=<lastId>
GET /contacts?limit=50&before=<firstId>
```
Cursor = the `id` of an object; the cursor object itself is excluded from the page. Endpoints that *always* paginate: `GET /emails`, `GET /templates`, `GET /topics`. Endpoints that paginate *only if* `limit` is passed (otherwise return all): domains, api-keys, broadcasts, segments, contacts, received emails, received-email attachments. Pagination validation failures come back as `validation_error` with status 422 (the pagination page's example) — despite the intro table listing 400 for bad parameters.

## Versioning

None today; Resend says calendar-based version headers will come later. Don't send an `Api-Version`-style header.
