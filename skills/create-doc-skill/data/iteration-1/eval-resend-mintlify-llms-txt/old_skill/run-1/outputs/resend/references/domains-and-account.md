# Domains, API keys, suppressions, logs

> Source: resend.com/docs + resend-openapi v1.5.1, read 2026-09-03. NOT yet verified against the live API — see verification-plan.md.

Read this when: onboarding a new sending/receiving domain (DNS records, verification, regions, tracking), programmatically issuing/rotating API keys, managing the suppression list, or debugging 4xx responses via request logs. Multi-tenant SaaS setups (each tenant sends from its own domain) live here too.

Contents: 1 Domains · 2 API keys · 3 Suppressions · 4 Logs · 5 OAuth (pointer)

---

## 1. Domains

### Create a domain
**Endpoint**: `POST /domains`  (SDK: `resend.domains.create()`)
**Purpose**: Register a domain/subdomain and receive the DNS records the owner must add.

| Param (JSON) | SDK name | Type | Required | Notes |
|---|---|---|---|---|
| `name` | `name` | string | yes | prefer a **subdomain** (`notifications.acme.dev`), each subdomain verified separately |
| `region` | `region` | enum | no | `us-east-1` (default) \| `eu-west-1` \| `sa-east-1` \| `ap-northeast-1` — pick closest to recipients; fixed after creation (`⚠ VERIFY`) |
| `custom_return_path` | `customReturnPath` | string | no | Return-Path subdomain, default `send` → `send.<domain>` |
| `open_tracking`, `click_tracking` | `openTracking`, `clickTracking` | boolean | no | |
| `tls` | `tls` | enum | no | `opportunistic` (default) \| `enforced` (mail not sent if TLS fails) |
| `capabilities` | `capabilities` | `{ sending: 'enabled'\|'disabled', receiving: 'enabled'\|'disabled' }` | no | at least one enabled; receiving adds an MX record |
| `tracking_subdomain` | `trackingSubdomain` | string | no | custom CNAME host for open/click tracking |

```ts
import { Resend } from 'resend';
const resend = new Resend(process.env.RESEND_API_KEY);

const { data, error } = await resend.domains.create({ name: 'notifications.acme.dev', region: 'eu-west-1' });
if (error) throw new Error(`${error.name}: ${error.message}`);

console.log(`Domain ${data.id} status=${data.status}`);
for (const r of data.records) {
  // r.record: 'SPF' | 'DKIM' | 'Receiving' | 'Tracking' | 'TrackingCAA'
  // r.type:   'MX' | 'TXT' | 'CNAME' | 'CAA'
  console.log([r.record, r.type, r.name, r.value, r.priority ?? '', r.ttl, r.status].join('\t'));
}
```
```bash
curl -X POST https://api.resend.com/domains -H "Authorization: Bearer $RESEND_API_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"notifications.acme.dev","region":"eu-west-1"}'
```
**Response (201)**: `id, name, created_at, status, region, capabilities, records[], open_tracking, click_tracking, tracking_subdomain`.
`status` ∈ `not_started | pending | verified | failed | partially_verified | partially_failed`; each record has its own `status` (`pending | verified | failed | temporary_failure | not_started`).

**Gotchas**
- The domain is unusable in `from` until `status === 'verified'` — sends return 403 `validation_error` "domain is not verified".
- DNS values must match **exactly**; when a CNAME is shown, do **not** proxy it (Cloudflare orange cloud breaks verification).
- Verification typically completes in <15 min, DNS can take up to 72 h; there is a "Restart verification" button / `POST /domains/{id}/verify`.
- A domain already used by another Resend team ⇒ 403 "domain has been registered already" → use the **claim** flow (`POST /domains/claim`, `GET /domains/{id}/claim`, `POST /domains/{id}/claim/verify`).
- The account's Resend-managed `<id>.resend.app` address can receive mail without any DNS work.

### Verify / get / list / update / delete
| Action | Endpoint | SDK | Notes |
|---|---|---|---|
| Trigger verification | `POST /domains/{id}/verify` | `resend.domains.verify(id)` | checks DKIM, SPF and tracking CNAME; returns `{ object, id }` — poll `get()` for status |
| Get | `GET /domains/{id}` | `resend.domains.get(id)` | same shape as create incl. `records[]` |
| List | `GET /domains` | `resend.domains.list()` | paginated only if `limit` passed |
| Update | `PATCH /domains/{id}` | `resend.domains.update({ id, ... })` | `open_tracking`, `click_tracking`, `tls`, `capabilities`, `tracking_subdomain` (`⚠ VERIFY` SDK arg shape) |
| Delete | `DELETE /domains/{id}` | `resend.domains.remove(id)` | |

```ts
// "verify" command: trigger, then poll status
await resend.domains.verify(domainId);
const { data: d } = await resend.domains.get(domainId);
console.log(d?.status, d?.records.map(r => `${r.record}:${r.status}`).join(' '));
```

### Multi-tenant SaaS
Each tenant domain is its own `POST /domains`; store the returned `id`, show the tenant the `records[]`, poll `status`. Use a `sending_access` API key scoped with `domain_id` per tenant if you hand keys to tenants (see below).

---

## 2. API keys

### Create an API key
**Endpoint**: `POST /api-keys`  (SDK: `resend.apiKeys.create()`)

| Param (JSON) | SDK name | Type | Required | Notes |
|---|---|---|---|---|
| `name` | `name` | string | yes | |
| `permission` | `permission` | enum | no | `full_access` \| `sending_access` |
| `domain_id` | `domainId` | string | no | restrict a **sending_access** key to one domain; ignored otherwise |

```ts
const { data } = await resend.apiKeys.create({ name: 'tenant-42-send', permission: 'sending_access', domainId: '<domain-id>' });
// data: { id, token }  ← token is returned ONLY here; store it (encrypted) immediately
```
**Gotchas**
- The `token` is shown once. Listing (`GET /api-keys` → `id, name, created_at`) never returns it.
- A `sending_access` key calling anything other than `POST /emails` / `/emails/batch` gets 401 `restricted_api_key` (also documented as 403 for an *inactive* key — `⚠ VERIFY`).
- Keys are team-wide for rate-limit purposes: 10 req/s applies across all keys of the team.
- Leaked key: delete it (`DELETE /api-keys/{id}`, SDK `resend.apiKeys.remove(id)`), create a new one, rotate env vars; check `GET /logs` for abuse. `PATCH /api-keys/{id}` only renames.
- Never commit keys; the skill's examples read `process.env.RESEND_API_KEY`.

---

## 3. Suppressions

The suppression list holds addresses Resend will **not** send to: added automatically after a hard bounce or spam complaint, or manually.

| Action | Endpoint | SDK (`⚠ VERIFY` names) | Notes |
|---|---|---|---|
| Add one | `POST /suppressions` body `{ email }` | `resend.suppressions.create({ email })` | 201 `{ object, id }` |
| Add many | `POST /suppressions/batch/add` | | ≤100 per call |
| Remove many | `POST /suppressions/batch/remove` | | ≤100 per call |
| Get / remove one | `GET/DELETE /suppressions/{suppression}` | | path accepts **id or email** |
| List | `GET /suppressions` | | |

**Gotchas**
- A send to a suppressed address is accepted by the API but ends with `last_event: suppressed` and an `email.suppressed` webhook — the API call itself does **not** fail.
- `suppressed@resend.dev` simulates this in tests (no `+label` support).
- Webhooks `suppression.added` / `suppression.removed` let you mirror the list in your DB.

---

## 4. Logs (API request logs)

**Endpoints**: `GET /logs` (paginated: `limit`, `after`, `before`), `GET /logs/{log_id}`.
Fields: `id, created_at, endpoint, method, response_status, user_agent`.

```ts
const { data } = await resend.logs.list({ limit: 20 });   // ⚠ VERIFY SDK method exists
data?.data.filter(l => l.response_status >= 400).forEach(l => console.log(l.created_at, l.method, l.endpoint, l.response_status, l.user_agent));
```
Use it to find 403/1010 (missing `User-Agent` — note `user_agent` may be `null` on those rows) and 429 bursts. Dashboard equivalent: resend.com/logs?status=429.

---

## 5. OAuth (pointer only)

`GET /oauth/grants`, `DELETE /oauth/grants/{id}`, plus `POST /oauth/register`, `/oauth/authorize`, `/oauth/token`, `/oauth/revoke` implement authorization-code + PKCE for third-party integrations that act on a Resend team. Access tokens lacking a scope get 403 `invalid_permission`. See resend.com/docs/guides/building-a-resend-oauth-client — not covered further here.
