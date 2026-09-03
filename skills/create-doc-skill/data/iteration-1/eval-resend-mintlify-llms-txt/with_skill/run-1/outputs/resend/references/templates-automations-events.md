# Resend · Templates / Automations / Events / Logs / OAuth grants

> **⚠ 验证状态：本文件全部内容为 OpenAPI 规范（resend/resend-openapi v1.5.1）与 https://resend.com/docs 页面的转录（抓取于 2026-09），尚未用真实 API key 调用验证。实际报错以 API 为准；未验证细节以 ⚠ 标出。**

鉴权与全局约定（Base URL、`Authorization: Bearer`、`User-Agent` 必带、`{ data, error }`、snake_case vs camelCase、cursor 分页）见 `auth.md`，本文不重复。

## 目录

1. [选型：三种"复用内容"方式怎么选](#选型)
2. [Templates：我想把邮件内容托管在 Resend](#templates)
   - 创建模板 · 用模板发送 · 发布/草稿/版本 · 更新 · 查询/列表 · 复制 · 删除
3. [Automations：我想让一个事件自动触发一串邮件](#automations)
   - 对象模型（steps / connections / config）· 创建 · 启停与更新 · 复制/删除 · Runs 排查
4. [Events：我想定义并触发自定义事件](#events)
5. [Logs：我想查某次 API 请求到底发了什么](#logs)
6. [OAuth grants（简述）](#oauth-grants)
7. [最易写错的三点](#最易写错的三点)

---

## 选型

| 需求 | 用什么 | 关键差别 |
|---|---|---|
| 同一封事务邮件反复发，内容想在 Dashboard 里维护 | **Template** + `POST /emails` 的 `template: { id, variables }` | 内容存在 Resend；发送时**不能**再传 `html`/`text`/`react`（否则 validation error）；只能引用**已 publish** 的版本 |
| 内容在代码里，每次发时渲染 | `POST /emails` 直接传 `html` / `react` | 见 emails 参考；与 Template 互斥 |
| 事件驱动的序列（欢迎系列、弃购提醒），带延迟/分支/等待 | **Automation**（trigger → steps）+ `POST /events/send` 触发 | send_email 步骤只能用 Template，不能内联 HTML；收件人是 Audience 里的 contact，不是任意地址 |

---

## Templates

### 创建模板
**Endpoint**: `POST /templates`
**用途**: 创建一个处于 `draft` 状态的模板；发送前必须 publish（见下）。

**关键参数**（REST 字段名；Node SDK 用 camelCase，如 `replyTo`、`fallbackValue`）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `name` | string | 是 | — | 模板名 |
| `html` | string | 是（OpenAPI） | — | 模板 HTML；变量写成 **三花括号** `{{{PRODUCT}}}`。⚠ 文档页未标必填，OpenAPI 标必填 |
| `alias` | string | 否 | — | 别名；之后所有 `/templates/{id}` 路径和发送时的 `template.id` 都可用 alias 代替 id |
| `from` | string | 否 | — | 默认发件人，`"Name <a@b.com>"`；发送时可覆盖 |
| `subject` | string | 否 | — | 默认主题；发送时可覆盖 |
| `reply_to` | string \| string[] | 否 | — | 默认 Reply-To。⚠ 文档页写 `string \| string[]`，OpenAPI 只写 `array<string>` |
| `text` | string | 否 | 由 HTML 生成 | 传空字符串 `""` 可关闭自动生成纯文本 |
| `react` | React.ReactNode | 否 | — | **仅 Node SDK**：直接传 React Email 组件，由 SDK 渲染成 HTML 再上传。⚠ 文档只标类型和"仅 Node.js SDK"，字段名按 emails 接口惯例推断为 `react`，未验证 |
| `variables[]` | object[] | 否 | — | 最多 **50** 个 |
| `variables[].key` | string | 是 | — | 建议大写（`PRODUCT_NAME`）。保留名不可用：`FIRST_NAME`、`LAST_NAME`、`EMAIL`、`RESEND_UNSUBSCRIBE_URL`、`contact`、`this` |
| `variables[].type` | enum | 是 | — | ⚠ **文档自相矛盾**：文档页/Dashboard 页只写 `'string' \| 'number'`；OpenAPI 枚举是 `string, number, boolean, object, list` |
| `variables[].fallback_value` | 与 type 同型 | 否 | — | 缺省值，必须与 `type` 同型。不给 fallback 则发送时必须传该变量 |

**示例**：

```ts
import { Resend } from 'resend';
const resend = new Resend(process.env.RESEND_API_KEY);

const { data, error } = await resend.templates.create({
  name: 'order-confirmation',
  alias: 'order-confirmation',
  from: 'Acme <store@example.com>',
  subject: 'Thanks for your order!',
  html: '<p>Name: {{{PRODUCT}}}</p><p>Total: {{{PRICE}}}</p>',
  variables: [
    { key: 'PRODUCT', type: 'string', fallbackValue: 'item' },
    { key: 'PRICE', type: 'number', fallbackValue: 25 },
  ],
});

// Node SDK 独有：创建并直接发布（文档原文写法）
await resend.templates.create({ /* 同上 */ }).publish();
```

```ts
// 底层：POST /templates
const res = await fetch('https://api.resend.com/templates', {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
    'Content-Type': 'application/json',
    'User-Agent': 'my-app/1.0',
  },
  body: JSON.stringify({
    name: 'order-confirmation',
    html: '<p>Name: {{{PRODUCT}}}</p><p>Total: {{{PRICE}}}</p>',
    variables: [
      { key: 'PRODUCT', type: 'string', fallback_value: 'item' },
      { key: 'PRICE', type: 'number', fallback_value: 25 },
    ],
  }),
});
```

**示例响应**（201）：`{ "id": "<template_id>", "object": "template" }`

**注意事项**
- 新建模板状态是 `draft`，**不能用于发送**；需 `POST /templates/{id}/publish` 或 Dashboard 发布。
- 变量写法是三花括号 `{{{KEY}}}`；文档没有出现双花括号写法。

### 用模板发送邮件
**Endpoint**: `POST /emails`（及 `POST /emails/batch` 的每个元素）
**用途**: 用 `template` 对象替代 `html`/`text`/`react`。完整发送参数见 emails 参考，这里只列模板相关。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `template.id` | string | 是（传了 `template` 时） | **已发布**模板的 id **或 alias** |
| `template.variables` | object | 否 | `{ KEY: value }` 键值对。key 只能含 ASCII 字母/数字/下划线，≤ **50** 字符；string 值 ≤ **2000** 字符，number 值 ≤ 2^53−1。⚠ 此处保留名列表是 `FIRST_NAME, LAST_NAME, EMAIL, UNSUBSCRIBE_URL`，与创建模板页的列表不一致（后者是 `RESEND_UNSUBSCRIBE_URL, contact, this`） |
| `from` / `subject` / `reply_to` | — | 视模板 | payload 里的值**优先于**模板默认值；模板没设默认值时 payload 必须提供 |

```ts
const { data, error } = await resend.emails.send({
  from: 'Acme <store@example.com>',
  to: ['delivered@resend.dev'],
  template: {
    id: 'order-confirmation',          // id 或 alias
    variables: { PRODUCT: 'Vintage Macintosh', PRICE: 499 },
  },
});
```

**注意事项**
- `template` 与 `html`/`text`/`react` 互斥，同时传返回 validation error。
- 变量缺失：有 `fallback_value` 用 fallback；没有则**整封邮件不发**，返回 validation error（文档未给出具体 error `name`，⚠ 文档未说明）。
- 引用未发布模板：文档只说"Only published templates can be used"，具体错误码 ⚠ 文档未说明。
- ⚠ Dashboard "Working with Variables" 页把发送时的 `variables` 描述为 "array of variable objects"，但所有代码示例和 OpenAPI 都是 object 键值对；按 object 写。

### 发布 / 草稿 / 版本
**Endpoint**: `POST /templates/{id}/publish`
**用途**: 把当前草稿变成"已发布版本"。发送永远用**最近一次发布**的版本。

```ts
const { data, error } = await resend.templates.publish('order-confirmation'); // id 或 alias
// → { object: 'template', id: '...' }
```

publish 前后差异：

| | 未 publish（draft） | 已 publish |
|---|---|---|
| `status` | `draft`，`published_at: null` | `published`，`published_at` 有值 |
| 能否发送 | 否 | 是 |
| 再次 PATCH 后 | 仍是 draft | 修改进入新草稿，**不影响**线上发送，`has_unpublished_versions: true`；需再 publish 才生效 |

- Dashboard 版本历史可回滚：回滚只是**基于旧版本创建新草稿**，不会自动改变已发布版本。

### 更新模板
**Endpoint**: `PATCH /templates/{id}`
**用途**: 部分更新；body 字段与创建完全相同，全部可选。更新只改草稿，见上表。

```ts
const { data, error } = await resend.templates.update('order-confirmation', {
  html: '<p>Total: {{{PRICE}}}</p><p>Name: {{{PRODUCT}}}</p>',
  variables: [{ key: 'PRICE', type: 'number', fallbackValue: 25 }],
});
// → { object: 'template', id: '...' }
```

⚠ 文档未说明：PATCH 时传 `variables` 是整体替换还是合并。

### 查询单个 / 列表
**Endpoint**: `GET /templates/{id}`（id 或 alias）、`GET /templates?limit&after&before`

```ts
const { data } = await resend.templates.get('order-confirmation');
const { data: list } = await resend.templates.list({ limit: 20, after: '<template_id>' });
```

单个响应关键字段：`object:"template"`, `id`, `current_version_id`, `name`, `alias`, `from`, `subject`, `reply_to`, `html`, `text`, `variables[]{id,key,type,fallback_value,created_at,updated_at}`, `status`(`draft|published`), `published_at`, `has_unpublished_versions`, `created_at`, `updated_at`。
列表响应：`{ object:"list", has_more, data:[{id,name,alias,status,published_at,created_at,updated_at}] }`，默认 20 条，**不含 html**。

### 复制 / 删除
- `POST /templates/{id}/duplicate` → `{ object:"template", id:"<新模板 id>" }`。SDK：`resend.templates.duplicate(id)`。⚠ 文档未说明副本是 draft 还是沿用原状态，以及 alias 如何处理。
- `DELETE /templates/{id}` → `{ object:"template", id, deleted:true }`。SDK：`resend.templates.remove(id)`。⚠ 文档未说明被 Automation `send_email` 步骤引用的模板能否删除。

---

## Automations

### 对象模型
一个 Automation = `name` + `status` + 有向图（`steps[]` 节点 + `connections[]` 边）。

**状态**：只有 `enabled` / `disabled` 两个值（OpenAPI 与文档一致）；创建默认 `disabled`。材料里**没有** `draft`/`active`/`paused` 之类状态。

**Step**（每个节点）：

| 字段 | 说明 |
|---|---|
| `key` | 图内唯一字符串，连接时引用 |
| `type` | `trigger` \| `send_email` \| `delay` \| `wait_for_event` \| `condition` \| `contact_update` \| `contact_delete` \| `add_to_segment` |
| `config` | 随 `type` 变化，见下表 |

| `type` | `config`（REST snake_case；Node SDK 示例用 `eventName`） | 备注 |
|---|---|---|
| `trigger` | `{ event_name }` | 必须**至少一个**；文档示例把它放 `steps[0]` |
| `send_email` | `{ template: { id, variables? }, from?, subject?, reply_to? }` | `id` 可为 alias；`variables` 值可以是静态字符串或引用对象 `{ "var": "event.<f>" }` / `{ "var": "contact.<f>" }` / `{ "var": "wait_events.<event_name>.<f>" }`；`from/subject/reply_to` 覆盖模板默认值；`reply_to` 这里是 **string** 而非数组 |
| `delay` | `{ duration }` | 自然语言时长 `"30 minutes"`、`"3 days"`，上限 **30 天** |
| `wait_for_event` | `{ event_name, timeout?, filter_rule? }` | `timeout` 上限 30 天；`filter_rule` 是与 condition 相同的 rule 对象 |
| `condition` | 规则树：`{ type:"rule", field, operator, value }` 或 `{ type:"and"\|"or", rules:[...] }` | `field` 必须带 `event.` 或 `contact.` 前缀；`operator` ∈ `eq, neq, gt, gte, lt, lte, contains, starts_with, ends_with, exists, is_empty`（后两个不需要 `value`）；`rules` 至少 1 项 |
| `contact_update` | `{ first_name?, last_name?, unsubscribed?, properties? }` | 每个值可为字面量或 `{ "var": "event.x" }` |
| `contact_delete` | `{}` | 必须传空对象 |
| `add_to_segment` | `{ segment_id }` | |

**Connection**（每条边）：`{ from: <key>, to: <key>, type? }`，`type` ∈ `default`（缺省）、`condition_met` / `condition_not_met`（仅 condition 出边）、`event_received` / `timeout`（仅 wait_for_event 出边）。

模板变量取值的三个命名空间：`event.*`（触发事件 payload）、`contact.*`（含 `contact.properties.<k>`）、`wait_events.<event_name>.*`（前面 wait_for_event 收到的 payload；同名多次则取最近一次）。模板里的变量 key 必须与 `variables` 的 key **完全一致**。

### 创建自动化
**Endpoint**: `POST /automations`
**用途**: 一次请求创建整张图。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `name` | string | 是 | — | |
| `status` | `enabled` \| `disabled` | 否 | `disabled` | 直接传 `enabled` 即创建即生效 |
| `steps` | Step[] | 是 | — | 至少含一个 `trigger` |
| `connections` | Connection[] | 是 | — | 必须与 `steps` 一起传。⚠ 文档未说明只有一个 trigger 且 `connections: []` 是否合法 |

```ts
const { data, error } = await resend.automations.create({
  name: 'Welcome series',
  status: 'disabled',
  steps: [
    { key: 'start', type: 'trigger', config: { eventName: 'user.created' } },
    { key: 'wait', type: 'delay', config: { duration: '1 hour' } },
    { key: 'check', type: 'condition',
      config: { type: 'rule', field: 'event.plan', operator: 'eq', value: 'pro' } },
    { key: 'pro_mail', type: 'send_email',
      config: { template: { id: 'welcome-pro', variables: { NAME: { var: 'event.firstName' } } } } },
    { key: 'free_mail', type: 'send_email',
      config: { template: { id: 'welcome-free' } } },
  ],
  connections: [
    { from: 'start', to: 'wait' },
    { from: 'wait', to: 'check' },
    { from: 'check', to: 'pro_mail', type: 'condition_met' },
    { from: 'check', to: 'free_mail', type: 'condition_not_met' },
  ],
});
```

```ts
// 底层：POST /automations（REST 用 event_name）
await fetch('https://api.resend.com/automations', {
  method: 'POST',
  headers: { /* Authorization + Content-Type + User-Agent，同上 */ },
  body: JSON.stringify({
    name: 'Welcome series',
    steps: [
      { key: 'start', type: 'trigger', config: { event_name: 'user.created' } },
      { key: 'welcome', type: 'send_email', config: { template: { id: 'welcome-pro' } } },
    ],
    connections: [{ from: 'start', to: 'welcome' }],
  }),
});
```

**示例响应**（201）：`{ "object": "automation", "id": "<automation_id>" }`

**注意事项**
- ⚠ 文档示例的 Node SDK 用 `config: { eventName }`（camelCase），cURL 用 `event_name`；其余 config 键（`reply_to`、`segment_id`、`filter_rule`、`first_name`）在文档里**只出现 snake_case 的 JSON 形式**，SDK 是否也会转换未验证。
- `send_email` 步骤引用的模板同样必须已发布。
- Resend **不会**自动给 `send_email` 步骤加退订链接；要在模板里放 `{{{RESEND_UNSUBSCRIBE_URL}}}`。联系人退订后，该 run 中剩余的 `send_email` 步骤被跳过，其他步骤照常执行。

### 启停与更新
**Endpoint**: `PATCH /automations/{automation_id}`、`POST /automations/{automation_id}/stop`

- PATCH body：`name` / `status` / `steps`+`connections`，至少给一项；`steps` 与 `connections` 必须成对。
- **enabled 状态下不能改图**：先 `status: 'disabled'`，或 duplicate 后改副本再切换。进行中的 run 会按启动时的版本跑完。
- `stop`：文档描述为 "Stop a running automation"，响应 `{ object:"automation", id, status:"disabled" }`——效果等于把状态置为 `disabled`（停止接收新触发）。⚠ 文档未说明 stop 是否会取消进行中的 run（intro 页说 in-flight runs 会跑完），也未说明 stop 后能否通过 `PATCH { status: 'enabled' }` 恢复——按状态模型推断可以，未验证。

```ts
await resend.automations.update('<automation_id>', { status: 'enabled' }); // 启用
await resend.automations.stop('<automation_id>');                           // 停止 → status: 'disabled'
```

### 复制 / 删除 / 查询
- `POST /automations/{id}/duplicate` → 201 `{ object:"automation", id:"<新 id>" }`。SDK `resend.automations.duplicate(id)`。⚠ 副本的 status 文档未说明。
- `DELETE /automations/{id}` → `{ object:"automation", id, deleted:true }`。SDK `resend.automations.remove(id)`。
- `GET /automations/{id}` → 含 `status`、`steps[]`、`connections[]`（返回的是 active version）。
- `GET /automations?status=enabled|disabled&limit&after&before` → 列表项只有 `id,name,status,created_at,updated_at`。
- 路径参数 `automation_id` 是 uuid；与 templates/events 不同，**没有 alias/name 形式**。

### Runs：排查某次触发跑到哪了
**Endpoint**: `GET /automations/{automation_id}/runs`、`GET /automations/{automation_id}/runs/{run_id}`

| 参数 | 说明 |
|---|---|
| `status`（query） | 逗号分隔：`running,completed,failed,cancelled`。Node SDK 传数组 `status: ['running','completed']` |
| `limit` / `after` / `before` | cursor 分页 |

```ts
const { data: runs } = await resend.automations.runs.list({
  automationId: '<automation_id>',
  status: ['failed'],
});
const { data: run } = await resend.automations.runs.get({
  automationId: '<automation_id>',
  runId: runs!.data[0].id,
});
// run.steps[]: { key, type, status, started_at, completed_at, output, error, created_at }
```

单个 run 响应：`{ object:"automation_run", id, status, started_at, completed_at, created_at, steps:[...] }`，`steps` 按图顺序排列，失败步骤看 `steps[].error`。

⚠ 文档自相矛盾：Dashboard Runs 页的状态表列了 5 个值（多一个 `skipped`），但同页解释 `skipped` 是**步骤**级别（退订/走了另一分支），OpenAPI 的 run `status` 枚举只有 4 个；`steps[].status` 在 OpenAPI 里没有枚举。

---

## Events

### 定义事件（可选但推荐）
**Endpoint**: `POST /events`
**用途**: 登记事件名和可选 payload schema。有 schema 时，`POST /events/send` 会校验并强制转换类型，不匹配返回 **422** 且事件不投递。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | 任意字符串（`user.created`、`welcome`）；点号只是惯例。**不能以 `resend:` 开头**（系统事件保留） |
| `schema` | object \| null | 否 | 扁平 `{ 字段: 类型 }`，类型 ∈ `string, number, boolean, date` |

```ts
const { data, error } = await resend.events.create({
  name: 'user.created',
  schema: { plan: 'string', trial: 'boolean' },
});
// 201 → { object: 'event', id: '<event_id>' }
```

其他 CRUD（`identifier` = 事件 **id(UUID) 或 name**，两者都可）：
- `GET /events/{identifier}` → `{ object:"event", id, name, schema, created_at, updated_at }`
- `GET /events?limit&after&before`
- `PATCH /events/{identifier}` body `{ schema }`（**必填**；传 `null` 清空）
- `DELETE /events/{identifier}` → `{ object:"event", id, deleted:true }`
- SDK：`resend.events.get('user.created')` / `.update('user.created', { schema })` / `.remove('user.created')` / `.list()`

⚠ 文档未说明：`POST /events/send` 是否要求事件已通过 `POST /events` 登记。Trigger 页说 Dashboard 里可以"选已有事件或直接输入新事件名"，暗示未登记的名字也能作为 trigger，但未明确说 send 未登记事件的行为。

### 触发事件
**Endpoint**: `POST /events/send`
**用途**: 向所有 **enabled** 且 trigger `event_name` 匹配的 Automation 投递一次事件（同名多个自动化会**全部**触发）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `event` | string | 是 | 事件名（不是事件 id） |
| `contact_id` | string(uuid) | 二选一 | Audience 里已有联系人的 id |
| `email` | string | 二选一 | 联系人邮箱；**不存在时会在 run 启动时自动创建联系人**。与 `contact_id` 恰好传一个 |
| `payload` | object | 否 | 自定义数据，后续步骤以 `event.<key>` 引用；有 schema 时校验并转换 |

```ts
const { data, error } = await resend.events.send({
  event: 'user.created',
  email: 'delivered@resend.dev',   // 或 contactId: '<contact_id>'
  payload: { plan: 'pro', firstName: 'Ada' },
});
// 202 → { object: 'event', event: 'user.created' }
```

底层 `POST /events/send`，REST body 与上面完全一致，只是 `contactId` 写成 `contact_id`。

**注意事项**
- 响应是 **202 Accepted**，且只回显事件名——**不返回 run id**；要追踪需再查 `GET /automations/{id}/runs`。
- 响应也不告诉你有没有自动化被触发；没有匹配的 enabled 自动化时大概率仍返回 202（⚠ 文档未说明）。
- ⚠ 文档未说明：`email` 自动建联系人时归入哪个 Audience，以及是否有幂等/去重。

---

## Logs

### 列出 / 查看 API 请求日志
**Endpoint**: `GET /logs`、`GET /logs/{log_id}`
**用途**: 排查"我刚才那次调用到底发了什么、API 回了什么"。这是 **API 请求日志**，不是邮件投递事件（那在 emails / webhooks）。

| 参数（query） | 说明 |
|---|---|
| `limit` / `after` / `before` | 仅 cursor 分页。⚠ API **没有**按状态码 / endpoint / 时间 / user-agent 过滤的参数；这些过滤只在 Dashboard 有。要找错误请求只能自己翻页筛 `response_status >= 400` |

```ts
const { data: logs } = await resend.logs.list();
// data[]: { id, created_at, endpoint, method, response_status, user_agent }

const { data: log } = await resend.logs.get(logs!.data[0].id);
// 追加: request_body, response_body（内容随原请求不同而不同）
```

列表项字段：`id`, `created_at`, `endpoint`（如 `/emails`、`/emails/<id>`）, `method`（`GET|POST|PUT|DELETE|PATCH|OPTIONS`）, `response_status`, `user_agent`。单条响应 `object:"log"`，多 `request_body` / `response_body`。

⚠ 文档未说明：日志保留时长、是否记录 4xx 之外被网关拒绝的请求（如缺 User-Agent 的 403）、`request_body` 是否脱敏。

---

## OAuth grants

团队通过 OAuth 授权给第三方客户端（如 Resend CLI）的记录。只有两个接口，用于审计和吊销：

- `GET /oauth/grants?limit&after&before` → `data[]{ id, client_id, scopes[], created_at, revoked_at, revoked_reason, client{ name, logo_uri } }`，**包含已吊销**的（活跃的 `revoked_at`/`revoked_reason` 为 `null`）。⚠ 文档示例响应多一个 `resource` 字段，OpenAPI 未定义。
- `DELETE /oauth/grants/{oauth_grant_id}` → `{ object:"oauth_grant", id, revoked_at, revoked_reason:"revoked_from_api" }`。吊销会使该 grant 下**所有** access/refresh token 失效；任何团队 API key 都能吊销；不存在或已吊销返回 **404**。

SDK：`resend.oauthGrants.list()` / `resend.oauthGrants.revoke(id)`。

---

## 最易写错的三点

1. **模板要先 publish 才能发**，且 PATCH 之后要**再 publish** 才生效——多数平台"保存即生效"，Resend 是 draft/published 双轨。
2. 触发自动化不是"给某个邮箱发邮件"，而是 `POST /events/send` 带 `event` + `contact_id`/`email`，回 202 且**不带 run id**；同名事件会触发**所有** enabled 自动化。
3. `template` 与 `html`/`text`/`react` **互斥**；变量语法是三花括号 `{{{KEY}}}`；发送时 `variables` 是 object 不是数组，缺变量且无 fallback 直接拒发。
