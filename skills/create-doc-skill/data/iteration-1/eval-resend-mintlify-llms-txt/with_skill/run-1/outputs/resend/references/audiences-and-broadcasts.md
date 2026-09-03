# Resend · 营销侧对象模型：Contacts / Segments / Topics / Suppressions / Broadcasts

> **⚠ 验证状态：本文件全部内容为 OpenAPI 规范（resend/resend-openapi v1.5.1）与 https://resend.com/docs 页面的转录（抓取于 2026-09），尚未用真实 API key 调用验证。实际报错以 API 为准；未验证细节以 ⚠ 标出。**

来源页：`api-reference/{contacts,contact-properties,segments,topics,suppressions,broadcasts}/*`、`dashboard/audiences/*`、`dashboard/segments/*`、`dashboard/topics/introduction`、`dashboard/broadcasts/*`、`dashboard/emails/email-suppressions`、`dashboard/settings/unsubscribe-page`、`knowledge-base/{why-use-topics,how-do-i-cancel-a-broadcast,audience-hygiene,why-are-my-emails-landing-on-the-suppression-list,what-counts-as-email-consent}`。

## 目录
1. 对象模型一页图（先读）
2. Audiences 已废弃 → Segments（迁移要点）
3. 谁能拦住一封邮件：`unsubscribed` / Topic 订阅 / Suppression 三者关系
4. 我想管理联系人（Contacts CRUD、按 id 或 email 定位）
5. 我想批量导入联系人（Contact Imports，CSV multipart）
6. 我想给联系人加自定义字段（Contact Properties）
7. 我想分组（Segments）与增删组员
8. 我想让用户自己选收什么邮件（Topics 与订阅偏好）
9. 我想屏蔽地址（Suppressions 单条/批量）
10. 我想群发（Broadcasts：创建 / 发送 / 定时 / 取消 / 更新 / 删除 / 统计）
11. 通用约定与命名差异

## 1. 对象模型一页图

| 对象 | 是什么 | 谁看得见 | 主键 / 定位方式 |
|---|---|---|---|
| **Contact** | 全局实体，一个 email 一条；可属于 0..n 个 Segment，可对每个 Topic opt_in/opt_out | 内部 | uuid **或 email 地址**（路径里两者皆可） |
| **Contact Property** | 自定义字段定义（`key` + `type` + `fallback_value`），值挂在 Contact 的 `properties` 上 | 内部；可在 Broadcast 正文做合并变量 | uuid |
| **Segment** | 你自己的分组，Broadcast 的收件范围 | 内部（收件人永远看不到） | uuid |
| **Topic** | 用户侧偏好类别（Newsletter / Promotions…），出现在退订页 | **收件人可见**（public 全员可见；private 仅 opt_in 者可见） | uuid |
| **Suppression** | 团队级黑名单（bounce / complaint / manual），跨所有域名、跨事务与营销邮件 | 内部 | uuid **或 email 地址** |
| **Broadcast** | 一次群发：`segment_id` + `from` + `subject` + 正文（+ 可选 `topic_id`） | — | uuid |

官方一句话：**Segments 决定发给谁（sender intent），Topics 决定谁说过"别发这类给我"（recipient preference）。** 发 Broadcast 时先选 Segment，再打 Topic 标签，Segment 里 opt_out 了该 Topic 的人自动被排除。

## 2. Audiences 已废弃 → Segments

- OpenAPI v1.5.1 把 `GET/POST /audiences`、`GET/DELETE /audiences/{id}` 四个接口**全部标 `deprecated`**，描述原文："Use Segments instead. These endpoints still work, but will be removed in the future."。文档页面则直接说 "Audiences are now called Segments"，并给了迁移指南 `dashboard/segments/migrating-from-audiences-to-segments`。
- 旧模型：Contact 隶属于某个 Audience，同一 email 在两个 Audience 里是两个对象、算两份配额。新模型（Global Contacts）：Contact 独立于 Segment，一个 email 只算一个 Contact，可同时在多个 Segment。
- **contacts 接口不再需要 `audience_id`**：迁移页原文 "Contacts API endpoints that previously required an `audience_id` can now be used directly instead"。OpenAPI 与页面里都**没有** `/audiences/{id}/contacts` 这种路径，全部是顶层 `/contacts`、`/contacts/{id}`、`/contacts/{contact_id}/segments/{segment_id}`。
- ⚠ 文档自相矛盾（残留字段）：OpenAPI 的 `POST /contacts` body 仍列有可选 `audience_id`，`POST /segments` body 仍有可选 `audience_id`，`GET /segments` / `GET /segments/{id}` 响应仍有 `audience_id`；而对应文档页面完全不提这些字段，页面示例响应里也没有。按"新代码不要传、读响应时忽略"处理。
- Audiences 4 接口 vs Segments 5 接口的差异：Audiences 没有 PATCH；Segments 多了 `PATCH /segments/{id}`（改名）和列表分页参数（`limit/after/before`，响应带 `has_more`），Audiences 列表无分页。Segments 创建 body 除 `name` 外 OpenAPI 还列了 `filter`（object，"Filter conditions for the segment"）—— ⚠ 文档未说明 `filter` 的结构，页面未提及，不要依赖。
- Broadcast 对象同时带 `audience_id`（标 Deprecated）和 `segment_id`，两者值相同；写入时用 `segment_id`。

## 3. 谁能拦住一封邮件：三层开关的关系

| 层 | 作用范围 | 谁设置 | 对 Broadcast | 对事务邮件 `POST /emails` |
|---|---|---|---|---|
| **Suppression**（bounce / complaint / manual） | 整个 team，所有域名和子域名 | Resend 自动（硬退信、投诉）或你手动 | 跳过，事件类型 `suppressed` | 跳过，邮件状态 `suppressed` |
| **Contact `unsubscribed: true`** | 该 Contact 的"全局订阅状态" | 用户点退订页"全部退订"，或你 PATCH | **不发任何 Broadcast**，即使他对某 Topic 是 opt_in | ⚠ 文档未说明。所有页面的措辞都是 "unsubscribed from all Broadcasts"；Topics 页另有一句 "will not receive emails from your account"，未区分事务邮件 |
| **Topic 订阅 opt_out** | 单个 Topic | 用户在退订页勾选，或你 PATCH `/contacts/{id}/topics` | 带 `topic_id` 的 Broadcast 排除 opt_out 者；不带 `topic_id` 的 Broadcast 不受 Topic 影响 | `POST /emails` 传 `topic_id` 时：收件人是 Contact 且 opt_out → 不发并标记 `failed`；不是 Contact → 仅当 Topic `default_subscription` 为 `opt_in` 才发；to/cc/bcc 逐个判定 |

关键结论（均为文档明示，优先级是"任一层为否即不发"，⚠ 文档未说明各层的判定先后顺序，但结果等价）：
- 退订页的行为取决于你有没有 Topic：**没有任何 Topic** 时，点退订链接 = 全局 `unsubscribed: true`；**有 Topic** 时展示偏好页，用户可只 opt_out 某些 public Topic，或"全部退订"。
- Broadcast **不带 `topic_id`** 而用户点了退订 → 直接全局退订（KB 页明确警告），所以官方建议每个 Broadcast 都打 Topic。
- 硬退信 / 投诉 → Resend **只自动加 Suppression，不会自动把 Contact 置为 unsubscribed**（audience-hygiene 页原文）。想同步 Contact 状态要自己接 `email.bounced` / `email.complained` webhook 后 PATCH。
- 从 Suppression 列表移除不保证可达；再次退信或投诉会自动重新加入并伤害信誉。
- Dashboard 的 Contact 状态：**Unsubscribed** = 全局退订；**Subscribed** = 至少订阅了一个 Topic。

## 4. 我想管理联系人（Contacts）

> 参数表用 REST 字段名（snake_case）；Node SDK 用 camelCase（`firstName`、`segmentId`）。

### 4.1 按 id 还是 email 定位
`GET / PATCH / DELETE /contacts/{id}`、`/contacts/{contact_id}/segments…`、`/contacts/{contact_id}/topics` 的路径参数在 OpenAPI 中都描述为 "The Contact ID or email address"，页面示例也同时给了 uuid 和 `steve.wozniak@gmail.com` 两种写法——**可以直接把 email 放进路径**。Node SDK 对应写法是 `{ id: '...' }` 或 `{ email: '...' }` 二选一（页面："Either `id` or `email` must be provided"）。用 fetch 时 email 里的 `@` 建议 `encodeURIComponent` 一下（文档示例是裸写的，⚠ 未说明是否必须编码）。

### 创建联系人
**Endpoint**: `POST /contacts`
**用途**: 单条创建；同时可以放进若干 Segment、设置 Topic 偏好、写自定义属性。批量用第 5 节的 Import。
**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `email` | string | 是 | — | 全局唯一键 |
| `first_name` / `last_name` | string | 否 | — | |
| `unsubscribed` | boolean | 否 | ⚠ 未说明（示例传 `false`） | 全局订阅状态；`true` = 不收任何 Broadcast |
| `properties` | object | 否 | — | `{ "company_name": "Acme Corp" }` 扁平 map；**key 必须已用 Contact Properties 创建，且类型匹配，否则整个请求失败并返回错误**；key 区分大小写 |
| `segments` | array | 否 | — | ⚠ 文档自相矛盾：OpenAPI 为 `array<string>`（segment id 数组）；页面写 "Array of objects. Each object must contain the ID of the segment"，Import 接口示例用 `[{ "id": "…" }]`。两种都试，或创建后再调 `POST /contacts/{id}/segments/{segment_id}` 更稳 |
| `topics` | array<object> | 否 | — | `[{ "id": "<topic_id>", "subscription": "opt_in" \| "opt_out" }]` |
| `audience_id` | string | 否 | — | ⚠ 仅 OpenAPI 残留，页面无；不要传 |

**示例**
```ts
import { Resend } from 'resend';
const resend = new Resend(process.env.RESEND_API_KEY);

const { data, error } = await resend.contacts.create({
  email: 'steve.wozniak@example.com',
  firstName: 'Steve',
  lastName: 'Wozniak',
  unsubscribed: false,
  properties: { company_name: 'Acme Corp' },
  topics: [{ id: '<topic_id>', subscription: 'opt_in' }],
});
if (error) throw new Error(`${error.name}: ${error.message}`);
console.log(data?.id);
```
```ts
// 底层：POST /contacts
const res = await fetch('https://api.resend.com/contacts', {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
    'User-Agent': 'my-app/1.0',
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    email: 'steve.wozniak@example.com',
    first_name: 'Steve',
    properties: { company_name: 'Acme Corp' },
  }),
});
```
**示例响应**: `{ "object": "contact", "id": "<uuid>" }`
**注意事项**: 同一 email 重复创建的行为 ⚠ 文档未说明（Import 有 `on_conflict`，单条创建没有）。Automation 触发到不存在的地址时也会自动创建 Contact。

### 查询单个 / 列表
**Endpoint**: `GET /contacts/{id}`（id 或 email）、`GET /contacts?segment_id=&limit=&after=&before=`
**用途**: 单查返回完整对象含 `properties`；列表可按 `segment_id` 过滤（SDK：`resend.contacts.list({ segmentId })`）。文档页面另有 `GET /segments/{segment_id}/contacts` 列出某 Segment 的联系人，⚠ 该路径**不在 OpenAPI 里**，且其 SDK 示例实际调用的是 `contacts.list({ segmentId })`；优先用 `GET /contacts?segment_id=`。
**示例响应（单查）**
```json
{
  "object": "contact", "id": "<uuid>", "email": "steve.wozniak@example.com",
  "first_name": "Steve", "last_name": "Wozniak",
  "created_at": "2026-10-06 23:47:56.678+00", "unsubscribed": false,
  "properties": { "company_name": { "value": "Acme Corp", "type": "string" } }
}
```
⚠ 文档自相矛盾：`properties` 在**请求**里是扁平 `{key: value}`，页面**响应**示例是 `{key: {value, type}}`，而 OpenAPI 只说 "A map of custom property keys and values"。读响应时两种形状都要兼容。列表项**不含** `properties`。

### 更新 / 删除
**Endpoint**: `PATCH /contacts/{id}`、`DELETE /contacts/{id}`（id 或 email）
**关键参数（PATCH）**: `email`（⚠ OpenAPI 可改；dashboard 页说 email 不可编辑，文档自相矛盾）、`first_name`、`last_name`、`unsubscribed`、`properties`（同创建规则）。
**示例**
```ts
await resend.contacts.update({ email: 'steve.wozniak@example.com', unsubscribed: true });
await resend.contacts.remove({ id: '<contact_id>' });
```
**示例响应**: PATCH → `{ "object": "contact", "id": "<uuid>" }`；DELETE → OpenAPI `{ "object", "id", "deleted": true }`，⚠ 页面示例却是 `{ "object": "contact", "contact": "<uuid>", "deleted": true }`（字段名 `contact` 而非 `id`），文档自相矛盾，只依赖 `deleted`。

### 联系人 ↔ Segment 成员关系
**Endpoint**: `GET /contacts/{contact_id}/segments`、`POST /contacts/{contact_id}/segments/{segment_id}`、`DELETE /contacts/{contact_id}/segments/{segment_id}`
**用途**: 加/退组不用 PATCH 整个 Contact；POST/DELETE 无 body。SDK：`resend.contacts.segments.add({ contactId | email, segmentId })` / `.remove({ id | email, segmentId })` / `.list({ id | email })`（⚠ SDK 示例里 add 用 `contactId`、remove 用 `id`，以实际 SDK 类型为准）。
**示例响应**: OpenAPI：add → `{ object, contact_id, segment_id }`，remove → 同上加 `deleted`。⚠ 页面示例分别是 `{ "id": "<segment_id>" }` 和 `{ "object": "contact_segment", "id": "<contact_id>", "audienceId": "<segment_id>", "deleted": true }`（camelCase 且叫 audienceId），文档自相矛盾。

### 联系人的 Topic 偏好
**Endpoint**: `GET /contacts/{contact_id}/topics`、`PATCH /contacts/{contact_id}/topics`
**关键参数（PATCH）**: body `{ "topics": [{ "id": "<topic_id>", "subscription": "opt_in" | "opt_out" }] }`（OpenAPI，`topics` 必填）。⚠ 文档自相矛盾：页面 cURL 示例 `-d` 直接发**裸数组** `[{...}]`，SDK 示例发 `{ topics: [...] }`；按 OpenAPI 包在 `topics` 里。
**示例**
```ts
const { data } = await resend.contacts.topics.update({
  email: 'steve.wozniak@example.com',
  topics: [{ id: '<topic_id>', subscription: 'opt_out' }],
});
```
**示例响应**: GET → `{ object: "list", has_more, data: [{ id, name, description, subscription }] }`；PATCH → OpenAPI `{ object, contact_id, topics: [{ id, subscription }] }`，⚠ 页面示例是 `{ "object": "contact_topics", "id": "<topic_id>" }`，文档自相矛盾。
**注意事项**: 未显式设置的 Topic 按该 Topic 的 `default_subscription` 生效（Topic 创建后不可改）。

## 5. 我想批量导入联系人（Contact Imports）

### 创建导入任务
**Endpoint**: `POST /contacts/imports`（`multipart/form-data`，不是 JSON）
**用途**: 上传 **CSV 文件**异步导入；返回 import id，再轮询状态。Dashboard 也能导 CSV（AI 自动映射列名、能顺手创建新属性），API 版需要你自己给 `column_map`。
**关键参数（表单字段；object/array 字段必须是 JSON 字符串）**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `file` | file | 是 | — | CSV。上限 ⚠ 文档自相矛盾：OpenAPI "Maximum size is 50MB"，API 页面与 dashboard 页均写 200MB |
| `column_map` | JSON string | 否 | — | `{"email":"Email","first_name":"First Name","last_name":"Last Name","unsubscribed":"…","properties":{"plan":{"column":"Plan","type":"string"}}}`；属性 `type` 可 `string`/`number`/`boolean`，默认 `string`（⚠ Contact Property 定义本身只有 `string`/`number`，`boolean` 如何落地未说明） |
| `on_conflict` | `upsert` \| `skip` | 否 | ⚠ 文档自相矛盾：OpenAPI `skip`，页面 "Defaults to `upsert`"。**显式传** | 已存在的 email 是更新还是跳过 |
| `segments` | JSON string | 否 | — | `[{"id":"<segment_id>"}]`（页面示例形状） |
| `topics` | JSON string | 否 | — | `[{"id":"<topic_id>","subscription":"opt_in"}]` |

**示例**
```ts
import { readFile } from 'node:fs/promises';
const file = new Blob([await readFile('contacts.csv')], { type: 'text/csv' });
const { data, error } = await resend.contacts.imports.create({
  file,
  columnMap: { email: 'Email', firstName: 'First Name', properties: { plan: { column: 'Plan', type: 'string' } } },
  onConflict: 'upsert',
  segments: [{ id: '<segment_id>' }],
});
```
```ts
// 底层：POST /contacts/imports（multipart）——不要手动设 Content-Type，让 fetch 生成 boundary
const form = new FormData();
form.append('file', new Blob([csvBytes], { type: 'text/csv' }), 'contacts.csv');
form.append('column_map', JSON.stringify({ email: 'Email', first_name: 'First Name' }));
form.append('on_conflict', 'upsert');
form.append('segments', JSON.stringify([{ id: '<segment_id>' }]));
const res = await fetch('https://api.resend.com/contacts/imports', {
  method: 'POST',
  headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}`, 'User-Agent': 'my-app/1.0' },
  body: form,
});
```
**示例响应**: `{ "object": "contact_import", "id": "<uuid>" }`（201）

### 查询导入进度
**Endpoint**: `GET /contacts/imports/{id}`、`GET /contacts/imports?status=&limit=&after=&before=`
**用途**: `status` ∈ `queued | in_progress | completed | failed`；完成后 `counts: { total, created, updated, skipped, failed }`，`completed_at` 未完成时为 null。列表 `limit` 默认 10、1–100。
**示例**: `const { data } = await resend.contacts.imports.get('<import_id>');`
**注意事项**: 行数上限、单行失败原因、是否有 webhook 通知 ⚠ 文档未说明；只能轮询。

## 6. 我想给联系人加自定义字段（Contact Properties）

**Endpoint**: `POST /contact-properties`、`GET /contact-properties`、`GET /contact-properties/{id}`、`PATCH /contact-properties/{id}`、`DELETE /contact-properties/{id}`
**用途**: 先定义 schema，才能在 Contact 的 `properties` 里写值；值可在 Broadcast 正文中做合并变量。
**关键参数（POST）**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `key` | string | 是 | — | ≤50 字符，仅字母数字和下划线，区分大小写；**创建后不可改** |
| `type` | `string` \| `number` | 是 | — | **创建后不可改** |
| `fallback_value` | string \| number | 否 | — | Contact 没设值时的默认值，类型须与 `type` 一致；PATCH 只能改这一项 |

**示例**
```ts
const { data } = await resend.contactProperties.create({ key: 'company_name', type: 'string', fallbackValue: 'Acme Corp' });
await resend.contactProperties.update({ id: data!.id, fallbackValue: 'Example Company' });
```
**示例响应**: 创建 `{ "object": "contact_property", "id": "<uuid>" }`；单查 `{ object, id, key, type, fallback_value, created_at }`；列表带 `has_more`。
**注意事项**: 删除属性后已有 Contact 上的值如何处理 ⚠ 文档未说明。

## 7. 我想分组（Segments）

**Endpoint**: `POST /segments`、`GET /segments`、`GET /segments/{id}`、`PATCH /segments/{id}`、`DELETE /segments/{id}`
**用途**: Segment 只有一个 `name`（OpenAPI 另有 `filter` object，⚠ 结构未说明）。成员关系通过第 4 节的 `/contacts/{contact_id}/segments/{segment_id}` 维护，或创建/导入 Contact 时带 `segments`。
**关键参数**: `name`（POST 必填；PATCH 在 OpenAPI 里也是必填）。
**示例**
```ts
const { data } = await resend.segments.create({ name: 'Registered Users' });
await resend.segments.update('<segment_id>', { name: 'Active Users' });
await resend.segments.remove('<segment_id>');
```
**示例响应**: 创建 `{ "object": "segment", "id": "<uuid>", "name": "Registered Users" }`；列表 `{ object: "list", has_more, data: [{ id, name, created_at }] }`（OpenAPI 还有 `audience_id`，见第 2 节）。
**注意事项**:
- 删除 Segment 是否删除其中的 Contact ⚠ 文档未说明（新模型下 Contact 是全局的，推测仅解除关系，未验证）。
- `GET /segments/metrics`（`metrics=all_contacts|subscribers|unsubscribers`、`dimensions=segment`、`segment_id[]`）是**私有 beta**，响应形状可能变，缓存 15 分钟；⚠ 不在 OpenAPI 里。`subscribers` = `unsubscribed:false` 的 Contact 数。

## 8. 我想让用户自己选收什么邮件（Topics）

**Endpoint**: `POST /topics`、`GET /topics`、`GET /topics/{id}`、`PATCH /topics/{id}`、`DELETE /topics/{id}`
**用途**: 定义偏好类别；订阅状态挂在 Contact 上（第 4 节 `/contacts/{id}/topics`）。Broadcast 和 `POST /emails` 都能用 `topic_id` 打标签。
**关键参数（POST）**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `name` | string | 是 | — | ≤50 字符 |
| `default_subscription` | `opt_in` \| `opt_out` | 是 | — | 没有显式偏好的 Contact 默认状态；**创建后不可改**（PATCH 不接受）。`opt_in`：默认都收，除非明确退订（对既有 Contact 也生效）；`opt_out`：默认不收，除非明确订阅 |
| `description` | string | 否 | — | ≤200 字符，显示在退订页 |
| `visibility` | `public` \| `private` | 否 | `private` | `public` 退订页对所有 Contact 可见；`private` 只有 opt_in 的人看得到 |

**示例**
```ts
const { data } = await resend.topics.create({ name: 'Weekly Newsletter', defaultSubscription: 'opt_in', visibility: 'public' });
```
**示例响应**: `{ "object": "topic", "id": "<uuid>" }`；单查 `{ id, object, name, description, default_subscription, visibility, created_at }`。
**注意事项**:
- ⚠ 页面 `PATCH /topics/{id}` 的 cURL 示例传了 `default_subscription`，与"不可更改"的说明矛盾（OpenAPI 的 PATCH body 只有 `name/description/visibility`）；不要传。
- 官方建议 3–5 个 Topic；每个 Broadcast 都打 Topic，否则用户退订即全局退订。
- 删除 Topic 后引用它的 Broadcast / Contact 偏好如何处理 ⚠ 文档未说明。
- 退订页可在 Settings → Unsubscribe Page 定制标题、描述、logo、三种颜色；Pro 及以上可去掉 "Powered by Resend"。页面对 team 内所有域名共用。

## 9. 我想屏蔽地址（Suppressions）

**Endpoint**: `POST /suppressions`、`POST /suppressions/batch/add`、`POST /suppressions/batch/remove`、`GET /suppressions?origin=`、`GET /suppressions/{suppression}`、`DELETE /suppressions/{suppression}`
**用途**: 团队级黑名单，命中即跳过（事务 + Broadcast，所有域名）。`origin` ∈ `bounce`（硬退信自动）/ `complaint`（投诉自动）/ `manual`（你加的）。`{suppression}` 路径参数同样**接受 id 或 email**。
**关键参数**
| 接口 | 字段 | 说明 |
|---|---|---|
| `POST /suppressions` | `email`（必填） | 单条 |
| `POST /suppressions/batch/add` | `emails: string[]` | 1–100 个 |
| `POST /suppressions/batch/remove` | `emails: string[]` **或** `ids: string[]` | 二选一不可同传，1–100 个 |
| `GET /suppressions` | `origin`、`limit/after/before` | 分页 |

**示例**
```ts
await resend.suppressions.add({ email: 'bounced@example.com' });
await resend.suppressions.batch.add({ emails: ['a@example.com', 'b@example.com'] });
await resend.suppressions.batch.remove({ emails: ['a@example.com'] });
const { data } = await resend.suppressions.get('bounced@example.com');
```
```ts
// 底层：POST /suppressions/batch/add
await fetch('https://api.resend.com/suppressions/batch/add', {
  method: 'POST',
  headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}`, 'User-Agent': 'my-app/1.0', 'Content-Type': 'application/json' },
  body: JSON.stringify({ emails: ['a@example.com', 'b@example.com'] }),
});
```
**示例响应**: 单条 `{ "object": "suppression", "id": "<uuid>" }`；批量 `{ "data": [{ "object": "suppression", "id": "<uuid>" }] }`（remove 多一个 `deleted`），**批量响应没有顶层 `object`**；单查 `{ object, id, email, origin, source_id, created_at }`，`source_id` 指向触发退信/投诉的那封邮件 id，`manual` 时为 null。
**注意事项**:
- Gmail / Google Workspace 基本不回传 `complained` 事件，投诉型 suppression 会漏。
- 有 `suppression.added` / `suppression.removed` webhook，可用来同步到自己库。
- 批量 add 对已存在地址的行为、部分失败是否整体失败 ⚠ 文档未说明。

## 10. 我想群发（Broadcasts）

状态机（`status`）：`draft` →（send/schedule）→ `scheduled` → `queued`（发送中）→ `sent`；`scheduled` 取消 → 回到 `draft`；`queued` 取消 → `canceled`（终态，不能再发）。

### 创建
**Endpoint**: `POST /broadcasts`
**用途**: 创建草稿，或 `send: true` 立即发 / 定时发（免去第二次调用）。
**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `segment_id` | string | **是** | — | 收件范围。`audience_id` 已废弃，OpenAPI 仍接受但 "Use `segment_id` instead" |
| `from` | string | **是** | — | 须是已验证域名；带显示名 `Acme <news@updates.example.com>` |
| `subject` | string | **是** | — | |
| `html` / `text` | string | 否（OpenAPI） | — | 正文。`text` 不传时由 HTML 自动生成，传 `""` 可关闭生成。⚠ 文档未说明发送时是否要求至少有一个；页面示例都给了 `html`。Node SDK 另支持 `react` |
| `reply_to` | ⚠ OpenAPI `array<string>`；页面 `string \| string[]` | 否 | — | 保险起见传数组 |
| `preview_text` | string | 否 | — | 邮件客户端预览文字 |
| `name` | string | 否 | — | 内部名称，仅 dashboard 显示 |
| `topic_id` | string | 否 | — | 打 Topic 标签：排除 opt_out 者、退订页可按 Topic 退订。**强烈建议传** |
| `send` | boolean | 否 | `false` | `true` 则创建后立刻发送或（配合 `scheduled_at`）定时 |
| `scheduled_at` | string | 否 | — | **只能在 `send: true` 时用**。自然语言（`in 1 hour`）或 ISO 8601（`2026-08-05T11:52:01.858Z`） |

**正文合并变量与退订链接**（页面明示的写法，三重花括号）：
- `{{{contact.first_name|fallback}}}`、`{{{contact.last_name|fallback}}}`、`{{{contact.email}}}`；`|` 后是空值兜底文案。
- 自定义属性：页面只说 "You can include Contact Properties in the body"，⚠ 文档未给出自定义 key 的具体占位符写法（按上面模式推测是 `{{{contact.<key>}}}`，未验证）；属性未设值时用 `fallback_value`。
- ⚠ 材料里**没有** `{{{FIRST_NAME|there}}}` 这种大写写法，别从记忆里抄。
- 退订链接：`{{{RESEND_UNSUBSCRIBE_URL}}}`，每个收件人每个 Broadcast 唯一，指向退订/偏好页。API 创建的 Broadcast 不会自动加页脚，要**自己把它写进 html/text**。

**示例**
```ts
const { data, error } = await resend.broadcasts.create({
  segmentId: '<segment_id>',
  topicId: '<topic_id>',
  from: 'Acme <news@updates.example.com>',
  subject: 'What is new this week',
  replyTo: ['support@example.com'],
  html: '<p>Hi {{{contact.first_name|there}}}, …</p><p><a href="{{{RESEND_UNSUBSCRIBE_URL}}}">Unsubscribe</a></p>',
  send: true,
  scheduledAt: '2026-09-10T09:00:00.000Z',
});
```
```ts
// 底层：POST /broadcasts
const res = await fetch('https://api.resend.com/broadcasts', {
  method: 'POST',
  headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}`, 'User-Agent': 'my-app/1.0', 'Content-Type': 'application/json' },
  body: JSON.stringify({
    segment_id: '<segment_id>', topic_id: '<topic_id>',
    from: 'Acme <news@updates.example.com>', subject: 'What is new this week',
    html: '<p>Hi {{{contact.first_name|there}}}</p><a href="{{{RESEND_UNSUBSCRIBE_URL}}}">Unsubscribe</a>',
  }),
});
```
**示例响应**: `{ "object": "broadcast", "id": "<uuid>" }`（201）
**注意事项**: 没有 Segment 就发不了（可以先建草稿测试）。`from` 必须是验证过的域名。

### 发送 / 定时发送已有草稿
**Endpoint**: `POST /broadcasts/{id}/send`
**用途**: 把 `draft` 发出去或排期。**只能发 API 创建的 Broadcast**，dashboard 编辑器建的不能用此接口（页面 Note 原文）。
**关键参数**: `scheduled_at`（可选）。⚠ 文档自相矛盾：OpenAPI 说 "should be in ISO 8601 format"，页面说自然语言（`in 1 min`）或 ISO 8601 都行，示例用 `in 1 min`。用 ISO 8601 最稳。
**示例**
```ts
const { data } = await resend.broadcasts.send('<broadcast_id>', { scheduledAt: 'in 1 min' });
```
```ts
// 底层：POST /broadcasts/{id}/send
await fetch(`https://api.resend.com/broadcasts/${id}/send`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}`, 'User-Agent': 'my-app/1.0', 'Content-Type': 'application/json' },
  body: JSON.stringify({ scheduled_at: '2026-09-10T09:00:00.000Z' }),
});
```
**示例响应**: `{ "id": "<uuid>" }`——**没有 `object` 字段**，和其他接口不同。
**注意事项**: 定时的最远/最近时间范围、能否对 `scheduled` 状态重复调用改期 ⚠ 文档未说明（取消后回到 draft 再发是文档明示的路径）。

### 取消
**Endpoint**: `POST /broadcasts/{id}/cancel`（无 body）
**前提**: 状态必须是 `scheduled` 或 `queued`。`scheduled` → `draft`（一封没发，可改后重排）；`queued` → `canceled`（已发出的不受影响、队列里剩余的不再发，**不能再发送**）。已 `sent` 的无法召回。
**示例**: `await resend.broadcasts.cancel('<broadcast_id>');` → `{ "object": "broadcast", "id": "<uuid>" }`
**注意事项**: 对 `draft` / `sent` 调用返回什么错误 ⚠ 文档未说明。

### 更新
**Endpoint**: `PATCH /broadcasts/{id}`
**用途**: 字段与创建相同（`segment_id, from, subject, reply_to, preview_text, html, text, name, topic_id`），**没有** `send` / `scheduled_at`。Dashboard 页说：`draft` 和 `scheduled` 可改内容；**已 `sent` 的只能改 `name`**。
**示例**: `await resend.broadcasts.update('<broadcast_id>', { html: '…' });` → `{ "object": "broadcast", "id": "<uuid>" }`

### 删除
**Endpoint**: `DELETE /broadcasts/{id}`
**前提**: ⚠ 文档自相矛盾：OpenAPI 摘要 "Remove an existing broadcast that is in the draft status"；页面说 `draft` **或 `scheduled`** 都可删，删 `scheduled` 等于同时取消排期。`sent` / `queued` 不可删。
**示例响应**: `{ "object": "broadcast", "id": "<uuid>", "deleted": true }`

### 查询与列表
**Endpoint**: `GET /broadcasts/{id}`、`GET /broadcasts?limit=&after=&before=`
**示例响应（单查）**
```json
{
  "object": "broadcast", "id": "<uuid>", "name": "Announcements",
  "audience_id": "<segment_id>", "segment_id": "<segment_id>",
  "from": "Acme <news@updates.example.com>", "subject": "hello world",
  "reply_to": null, "preview_text": "…", "html": "…", "text": "…",
  "status": "draft", "created_at": "…", "scheduled_at": null, "sent_at": null,
  "topic_id": "<topic_id>"
}
```
列表项不含 `from/subject/html/text`。

### 发送结果：收件人明细与点击链接
**Endpoint**: `GET /broadcasts/{id}/recipients?type=`、`GET /broadcasts/{id}/clicked-links`
**关键参数（recipients）**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | enum | **是** | `sent, delivered, opened, clicked, bounced, complained, unsubscribed, suppressed` 一次只能一种 |
| `email` | string | 否 | 子串过滤 |
| `bounce_type` | `permanent` \| `transient` \| `undetermined` | 否 | 仅 `type=bounced` 时可用 |
| `limit/after/before` | | 否 | 1–100，默认 20 |

**示例**
```ts
const { data } = await resend.broadcasts.recipients('<broadcast_id>', { type: 'clicked', limit: 100 });
const links = await resend.broadcasts.clickedLinks('<broadcast_id>', { limit: 20 });
```
**示例响应**: recipients `data[]` = `{ id, contact_id | null, email, count?, bounce_type?, clicked_links?: [{ url, clicks }] }`——`id` 是**分页游标，不是任何实体 id**，引用联系人用 `contact_id`（email 已不再对应 Contact 时为 null）；`count` 仅 opened/clicked 有。clicked-links `data[]` = `{ id(游标), url, clicks, unique_clicks }`，按总点击降序。
**注意事项**: 两个接口响应**缓存最多 15 分钟**。开信率受邮箱服务商影响可能不准。

## 11. 通用约定与命名差异

- 所有列表接口：`limit`（1–100，默认 20；imports 列表默认 10）、`after` / `before` 二选一、响应 `{ object: "list", has_more, data }`。⚠ `GET /contacts` 的 OpenAPI 响应表没列 `has_more`，页面示例有。
- REST body 与响应 snake_case（`first_name`, `segment_id`, `scheduled_at`, `fallback_value`, `default_subscription`, `on_conflict`）；Node SDK 参数 camelCase（`firstName`, `segmentId`, `scheduledAt`, `fallbackValue`, `defaultSubscription`, `onConflict`, `columnMap`），响应字段仍是 snake_case。
- SDK 方法名对照：`contacts.create/get/update/remove/list`、`contacts.imports.create/get/list`、`contacts.segments.add/remove/list`、`contacts.topics.list/update`、`contactProperties.*`、`segments.create/get/update/remove/list/metrics`、`topics.*`、`suppressions.add/get/remove/list` + `suppressions.batch.add/remove`、`broadcasts.create/get/update/remove/list/send/cancel/recipients/clickedLinks`。删除一律叫 `remove`。
- 需要 `full_access` key；`sending_access` key 调这些接口会 401 `restricted_api_key`。
- 相关 webhook：`contact.created/updated/deleted`、`suppression.added/removed`（其余见 webhooks reference）。
- 合规提醒（KB 页）：预勾选框、ToS 里夹带同意条款、"不退订即同意"都不算有效同意；投诉率/退信率持续偏高 Resend 可能暂停账号。营销邮件建议只发给 6 个月内有打开/点击的人。
