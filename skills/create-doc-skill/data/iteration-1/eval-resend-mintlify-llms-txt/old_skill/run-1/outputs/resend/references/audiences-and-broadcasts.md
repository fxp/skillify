# Templates, contacts, segments, topics, broadcasts, events

> Source: resend.com/docs + resend-openapi v1.5.1, read 2026-09-03. NOT yet verified against the live API — see verification-plan.md.

Read this when you need reusable email **templates** with variables, or anything on the marketing side: **contacts**, **segments** (formerly audiences), **topics** (subscription preferences), **broadcasts** (newsletters/campaigns), or custom **events** that trigger automations. For plain transactional sends see `sending.md`.

Contents: 1 Templates · 2 Contacts · 3 Segments · 4 Topics · 5 Broadcasts · 6 Events & automations · 7 Mental model

JSON field names below are the raw API (snake_case); the Node SDK uses camelCase equivalents (`fallbackValue`, `segmentId`, `scheduledAt`, `firstName`, `contactId`). Every SDK call resolves `{ data, error }`.

---

## 1. Templates

### Create a template
**Endpoint**: `POST /templates`  (SDK: `resend.templates.create()`)
**Purpose**: Store a reusable HTML body with `{{{VARIABLES}}}` so sends only pass variable values.
**Key parameters**

| Param (JSON) | SDK name | Type | Required | Notes |
|---|---|---|---|---|
| `name` | `name` | string | yes | display name |
| `html` | `html` | string | yes | use triple mustache `{{{VAR}}}` for variables |
| `alias` | `alias` | string | no | human id usable instead of the UUID in `template.id` and `/templates/{id}` |
| `from`, `subject`, `reply_to[]` | `from`, `subject`, `replyTo` | string / string[] | no | defaults; the send payload overrides them |
| `text` | `text` | string | no | plain-text version |
| `variables[]` | `variables` | array | no | `{ key, type, fallback_value }` — `type` ∈ `string \| number \| boolean \| object \| list`; SDK `fallbackValue` |

```ts
const { data, error } = await resend.templates.create({
  name: 'order-confirmation',
  alias: 'order-confirmation',
  from: 'Acme Store <store@mail.acme.dev>',
  subject: 'Thanks for your order!',
  html: '<p>Item: {{{PRODUCT}}}</p><p>Total: {{{PRICE}}}</p>',
  variables: [
    { key: 'PRODUCT', type: 'string', fallbackValue: 'item' },
    { key: 'PRICE', type: 'number', fallbackValue: 20 },
  ],
});
// data: { id, object: 'template' }
```
```bash
curl -X POST https://api.resend.com/templates -H "Authorization: Bearer $RESEND_API_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"order-confirmation","html":"<p>{{{PRODUCT}}}</p>","variables":[{"key":"PRODUCT","type":"string","fallback_value":"item"}]}'
```
**Gotchas**
- A new template is a **draft**. It must be **published** before `emails.send({ template })` will accept it.
- Variable keys: letters/digits/`_`, ≤50 chars; reserved: `FIRST_NAME`, `LAST_NAME`, `EMAIL`, `UNSUBSCRIBE_URL`.
- No fallback + no value at send time ⇒ send fails with a validation error (the email is not sent).
- The docs show `await resend.templates.create({...}).publish()` chained — `⚠ VERIFY:` `create()` returns a promise of `{ data, error }`, so chaining is unlikely to type-check; use two calls (below).

### Publish / get / list / update / delete / duplicate
| Action | Endpoint | SDK | Notes |
|---|---|---|---|
| Publish | `POST /templates/{id}/publish` | `resend.templates.publish(idOrAlias)` | `{id}` accepts UUID **or alias** |
| Get | `GET /templates/{id}` | `resend.templates.get(idOrAlias)` | returns html/text/variables/status |
| List | `GET /templates` | `resend.templates.list({ limit, after, before })` | **always paginated** (`has_more`) |
| Update | `PATCH /templates/{id}` | `resend.templates.update(id, {...})` | same body fields as create; re-publish after editing (`⚠ VERIFY` whether an update unpublishes) |
| Delete | `DELETE /templates/{id}` | `resend.templates.remove(id)` | |
| Duplicate | `POST /templates/{id}/duplicate` | `resend.templates.duplicate(id)` | new draft copy |

```ts
const created = await resend.templates.create({ /* … */ });
if (created.error) throw new Error(created.error.message);
const published = await resend.templates.publish(created.data!.id);
```

### Sending with a template
See `sending.md` § Templates. Shape: `emails.send({ from, to, subject?, template: { id: 'order-confirmation', variables: { PRODUCT: 'Laptop', PRICE: 499 } } })` — no `html`/`text`/`react` alongside `template`.

---

## 2. Contacts

### Create a contact
**Endpoint**: `POST /contacts`  (SDK: `resend.contacts.create()`)
**Purpose**: Add a marketing recipient; optionally place it in segments and set topic subscriptions.

| Param (JSON) | SDK name | Type | Required | Notes |
|---|---|---|---|---|
| `email` | `email` | string | yes | |
| `first_name`, `last_name` | `firstName`, `lastName` | string | no | available in broadcasts as `{{{contact.first_name}}}` |
| `unsubscribed` | `unsubscribed` | boolean | no | **global** opt-out; `true` blocks all broadcasts regardless of topics |
| `properties` | `properties` | object | no | custom properties — keys must exist (see Contact properties) |
| `segments[]` | `segments` | string[] | no | segment IDs |
| `topics[]` | `topics` | `{ id, subscription: 'opt_in' \| 'opt_out' }[]` | no | |
| `audience_id` | `audienceId` | string | no | **legacy** (Audiences → Segments migration); omit in new code |

```ts
const { data, error } = await resend.contacts.create({
  email: 'delivered@resend.dev',
  firstName: 'Ada',
  unsubscribed: false,
  segments: ['<segment-id>'],
  topics: [{ id: '<topic-id>', subscription: 'opt_in' }],
});
// data: { object: 'contact', id }
```

### Get / update / delete / list
| Action | Endpoint | SDK | Notes |
|---|---|---|---|
| Get | `GET /contacts/{id}` | `resend.contacts.get(idOrEmail)` | `{id}` accepts contact ID **or email address** |
| Update | `PATCH /contacts/{id}` | `resend.contacts.update({ id \| email, ... })` | body: `email`, `first_name`, `last_name`, `unsubscribed`, `properties` (`⚠ VERIFY` exact SDK arg shape) |
| Delete | `DELETE /contacts/{id}` | `resend.contacts.remove(idOrEmail)` | |
| List | `GET /contacts?segment_id=&limit=&after=&before=` | `resend.contacts.list({ segmentId, limit, after })` | paginated only when `limit` given; list items: `id, email, first_name, last_name, created_at, unsubscribed` |
| Segments of a contact | `GET /contacts/{contact_id}/segments`, `POST/DELETE /contacts/{contact_id}/segments/{segment_id}` | `resend.contacts.segments.*` (`⚠ VERIFY` SDK namespace) | |
| Topics of a contact | `GET /contacts/{contact_id}/topics`, `PATCH /contacts/{contact_id}/topics` | | PATCH body: `topics[{ id, subscription }]` |
| Bulk import | `POST /contacts/imports`, `GET /contacts/imports[/{id}]` | | async job; CSV imports do **not** emit `contact.created` webhooks |

### Contact properties
`POST/GET/PATCH/DELETE /contact-properties[/{id}]` define custom keys (name + type) that `properties` on a contact may use. Create the property first, then set it on contacts.

**Gotchas**
- `unsubscribed: true` is stronger than any topic opt-in.
- Contacts beyond your plan's **contact quota** can still be created, but broadcast sends return 403 `validation_error` "reached your contacts quota".

---

## 3. Segments

**Endpoints**: `POST /segments` (body `name` required, optional `filter` object, legacy `audience_id`), `GET /segments` (paginated when `limit`), `GET/PATCH/DELETE /segments/{id}`, `GET /segments/{id}/contacts`, `GET /segments/{id}/metrics`. SDK: `resend.segments.*`.

```ts
const { data } = await resend.segments.create({ name: 'newsletter-subscribers' });
// data: { id, object: 'segment' }
```
**Gotchas**
- "Audiences" in older docs/SDK versions = Segments now; `audience_id` fields are kept for backward compatibility. Prefer `segment_id`.
- A broadcast targets exactly one segment (`segment_id` required).

---

## 4. Topics

**Endpoints**: `POST /topics` (`name`, `description?`, `default_subscription: 'opt_in' | 'opt_out'`, `visibility: 'public' | 'private'` — `⚠ VERIFY` exact field names against the OpenAPI block for `/topics`), `GET /topics` (**always paginated**), `GET/PATCH/DELETE /topics/{id}`. SDK: `resend.topics.*`.

**Gotchas**
- `default_subscription` **cannot be changed** after creation.
- `topic_id` on `POST /emails` (transactional) and on broadcasts scopes delivery: contact opted-out ⇒ email not sent and marked `failed`; non-contact recipient ⇒ sent only if the topic default is opt-in. Each `to/cc/bcc` address is evaluated separately.
- Recipients see topics on the unsubscribe page (`{{{RESEND_UNSUBSCRIBE_URL}}}` in broadcast HTML); `private` topics are only visible to contacts already opted in.

---

## 5. Broadcasts

### Create a broadcast
**Endpoint**: `POST /broadcasts`  (SDK: `resend.broadcasts.create()`)
**Purpose**: Compose a campaign to a segment; keep as draft, send now, or schedule.

| Param (JSON) | SDK name | Type | Required | Notes |
|---|---|---|---|---|
| `segment_id` | `segmentId` | string | yes | (`audience_id` legacy alias) |
| `from` | `from` | string | yes | verified domain |
| `subject` | `subject` | string | yes | |
| `html` / `text` | | string | no | supports `{{{contact.first_name\|there}}}` fallback syntax and `{{{RESEND_UNSUBSCRIBE_URL}}}` |
| `name`, `preview_text`, `reply_to[]`, `topic_id` | `name`, `previewText`, `replyTo`, `topicId` | | no | |
| `send` | `send` | boolean | no | `true` = send/schedule immediately; default `false` = draft |
| `scheduled_at` | `scheduledAt` | string | no | **only valid when `send: true`**; ISO 8601 or natural language ("in 1 hour") |

```ts
const { data, error } = await resend.broadcasts.create({
  segmentId: '<segment-id>',
  from: 'Acme <news@mail.acme.dev>',
  subject: 'September update',
  html: 'Hi {{{contact.first_name|there}}}, … <a href="{{{RESEND_UNSUBSCRIBE_URL}}}">Unsubscribe</a>',
  send: true,
  scheduledAt: 'in 1 hour',
});
// data: { id, object: 'broadcast' }
```

### Send / cancel / manage
| Action | Endpoint | SDK | Notes |
|---|---|---|---|
| Send or schedule an existing draft | `POST /broadcasts/{id}/send` body `{ scheduled_at? }` | `resend.broadcasts.send(id, { scheduledAt })` | **only API-created broadcasts**; dashboard-editor broadcasts cannot be sent via API |
| Cancel queued/scheduled | `POST /broadcasts/{id}/cancel` | `resend.broadcasts.cancel(id)` | |
| Get / list / update / delete | `GET /broadcasts/{id}`, `GET /broadcasts` (paginated when `limit`), `PATCH`, `DELETE` | `resend.broadcasts.*` | |
| Recipients by event | `GET /broadcasts/{id}/recipients?event=` | | e.g. who opened/clicked (`⚠ VERIFY` query param name) |
| Clicked links | `GET /broadcasts/{id}/clicked-links` | | |

**Gotchas**
- Broadcasts are the marketing path; for many *different* transactional emails use `POST /emails/batch` instead (see `sending.md`).
- Gmail/Yahoo bulk-sender rules: include the unsubscribe URL; Resend adds `List-Unsubscribe` for broadcasts automatically (`⚠ VERIFY`).
- Over contact quota ⇒ 403 on send, not on create.

---

## 6. Events & automations (brief)

**Send a custom event**: `POST /events/send` → 202
```ts
await resend.events.send({ event: 'order_placed', email: 'delivered@resend.dev', payload: { orderId: 'A-1' } });
// exactly ONE of `email` or `contactId` must be given
```
Events are declared with `POST /events` (name + schema) and can trigger **automations** (`/automations`, `/automations/{id}/runs`, `/duplicate`, `/stop`) — multi-step sequences (send email, delay, wait-for-event, add-to-segment, condition). Automations are mostly built in the dashboard; the API covers CRUD, duplicate, stop and run inspection. Consult resend.com/docs/dashboard/automations/* before writing automation code.

---

## 7. Mental model (for engineers coming from other providers)

- **SendGrid "dynamic templates" / Postmark "templates"** → Resend Templates: draft → publish → `template: { id | alias, variables }`. Variables are triple-mustache `{{{X}}}` (no HTML escaping), not `{{x}}`.
- **Mailchimp lists / SES contact lists** → Segments (not "Audiences" any more) + Topics for per-category preferences; a contact's global `unsubscribed` beats everything.
- **Campaigns** → Broadcasts; `send: false` = draft, `send: true` (+ `scheduled_at`) = go. Only API-created broadcasts are API-sendable.
- Contact **quota** is enforced at broadcast send time, not at contact creation.
