# Resend · 域名与 API key

> **⚠ 验证状态：本文件全部内容为 OpenAPI 规范（resend/resend-openapi v1.5.1）与 https://resend.com/docs 页面的转录（抓取于 2026-09），尚未用真实 API key 调用验证。实际报错以 API 为准；未验证细节以 ⚠ 标出。**

## 目录

1. [全局约定（简）](#全局约定简)
2. [域名](#域名)
   - [我想添加域名并拿到 DNS 记录 — `POST /domains`](#我想添加域名并拿到-dns-记录)
   - [我想触发验证并知道结果 — `POST /domains/{id}/verify` + 轮询 `GET`](#我想触发验证并知道结果)
   - [我想查看域名 — `GET /domains`、`GET /domains/{id}`](#我想查看域名)
   - [我想改 tracking / TLS / 收发能力 — `PATCH /domains/{id}`](#我想改-tracking--tls--收发能力)
   - [域名已被另一个团队占用 — claim 三步流程](#域名已被另一个团队占用claim-流程)
   - [我想删除域名 / 换 region](#我想删除域名--换-region)
   - [域名相关 403 速查](#域名相关-403-速查)
3. [API key](#api-key)
   - [我想创建一个 key（含限定域名）— `POST /api-keys`](#我想创建一个-key)
   - [列出 / 重命名 / 删除](#列出--重命名--删除)
   - [401 / 403 对照：sending_access 越权到底报什么](#401--403-对照)
   - [多租户（SaaS 替租户发信）建议](#多租户建议)
4. [疑点核实结论汇总](#疑点核实结论汇总)

## 全局约定（简）

- Base URL `https://api.resend.com`，header `Authorization: Bearer <RESEND_API_KEY>`。
- 裸 `fetch` 必须带 `User-Agent`，否则请求在到达 API 之前就被拒：403、错误码 1010 `Access denied`（SDK 与 curl 自动带）。
- SDK：`import { Resend } from 'resend'; const resend = new Resend(process.env.RESEND_API_KEY);`，所有方法返回 `{ data, error }`，不抛异常。
- REST body 是 snake_case（`open_tracking`、`custom_return_path`），Node SDK 参数是 camelCase（`openTracking`、`customReturnPath`）。下文参数表一律写 REST 字段名。
- 域名和 key 都属于 **team**：团队所有成员都能增删改查域名；一个域名同一时间只能在一个团队里处于活跃状态。团队能加的域名数由套餐决定，付费 transactional 套餐可加购 domains add-on（+100 个域名，$20/月）。

## 域名

推荐用子域名（`notifications.example.com`）而不是根域名发信，每个子域名都要单独创建并验证；同一根域名可以有多个子域名，例如 newsletter 开 tracking、事务邮件不开。

### 我想添加域名并拿到 DNS 记录

**Endpoint**: `POST /domains`
**用途**: 在当前团队创建域名，响应里直接带上需要去 DNS 商添加的全部记录。它不会触发验证——记录加好后要另调 verify。

**关键参数**（REST 字段名；Node SDK 用 camelCase）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `name` | string | 是 | — | 域名或子域名，如 `notifications.example.com` |
| `region` | string | 否 | `us-east-1` | 发信出口区域，枚举 `us-east-1` \| `eu-west-1` \| `sa-east-1` \| `ap-northeast-1`。只决定邮件从哪发出，账号数据一律存美国。创建后**不能改**，只能删了重建 |
| `custom_return_path` | string | 否 | `send` | Return-Path 子域名（用于 SPF、DMARC 对齐、退信）。≤63 字符，字母开头、字母或数字结尾，只含字母数字连字符。别用 `testing` 这类会暴露给收件人的词 |
| `tls` | string | 否 | `opportunistic` | `opportunistic`（尝试 TLS，失败则明文发）\| `enforced`（对方不支持 TLS 就不发） |
| `open_tracking` / `click_tracking` | boolean | 否 | 关闭 | 只有在 `tracking_subdomain` 配置**且验证通过**后才真正生效 |
| `tracking_subdomain` | string | 否 | — | 点击/打开跟踪用的子域名前缀，如 `links` → 生成 `links.example.com` 的 CNAME。一旦设置只能改不能删 |
| `capabilities.sending` / `capabilities.receiving` | string | 否 | ⚠ 文档未说明 | `enabled` \| `disabled`，至少一个 enabled。示例响应里默认是 sending enabled、receiving disabled |

**示例**（SDK）：

```ts
import { Resend } from 'resend';
const resend = new Resend(process.env.RESEND_API_KEY);

const { data, error } = await resend.domains.create({
  name: 'notifications.example.com',
  region: 'eu-west-1',
  customReturnPath: 'outbound',
  tls: 'enforced',
});
if (error) throw new Error(`${error.name}: ${error.message}`);
// data.records 就是要加到 DNS 的记录
```

**示例**（`fetch`，底层 `POST /domains`）：

```ts
const res = await fetch('https://api.resend.com/domains', {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
    'Content-Type': 'application/json',
    'User-Agent': 'my-app/1.0',
  },
  body: JSON.stringify({ name: 'notifications.example.com', region: 'eu-west-1' }),
});
const domain = await res.json(); // 201
```

**示例响应**（201，关键字段）：

```json
{
  "id": "…", "name": "notifications.example.com", "status": "not_started",
  "region": "eu-west-1", "open_tracking": false, "click_tracking": false,
  "capabilities": { "sending": "enabled", "receiving": "disabled" },
  "records": [
    { "record": "SPF",  "type": "MX",    "name": "send", "value": "feedback-smtp.eu-west-1.amazonses.com", "priority": 10, "ttl": "Auto", "status": "not_started" },
    { "record": "SPF",  "type": "TXT",   "name": "send", "value": "\"v=spf1 include:amazonses.com ~all\"", "ttl": "Auto", "status": "not_started" },
    { "record": "DKIM", "type": "CNAME", "name": "<selector>._domainkey", "value": "<selector>.dkim.amazonses.com.", "ttl": "Auto", "status": "not_started" }
  ]
}
```

`records[].record` 枚举：`SPF` | `DKIM` | `Receiving`（收信 MX）| `Tracking`（跟踪 CNAME）| `TrackingCAA`（域名已有 CAA 记录时额外要加的 CAA）。`records[].type` 枚举：`MX` | `TXT` | `CNAME` | `CAA`。`records[].status` 枚举：`not_started` | `pending` | `verified` | `failed` | `temporary_failure`。

**注意事项**：
- 记录集合随创建时间变化：老域名 SPF 是 TXT+MX、DKIM 是 TXT 或 3 条 CNAME；2026-08 之后创建的域名 SPF 可能改成 CNAME，且可能是两条（Return-Path 子域名 + `r` 前缀的兄弟，如 `outbound` 与 `routbound`），两条都要加。**永远以响应里的 `records` 为准**，不要按经验手写。
- Cloudflare 上 CNAME 必须是灰云（DNS only），橙云代理会让验证永远不完成。
- 域名已被别的团队验证过时，这个接口返回 403 `validation_error`「The example.com domain has been registered already」→ 走下面的 claim 流程。
- ⚠ 文档自相矛盾：`custom_return_path` 的 dashboard 页写"creating or updating a domain via the API"都能设，但 OpenAPI 与 update-domain 页面的 PATCH body 都**没有**这个字段。按规范只能在创建时设。

### 我想触发验证并知道结果

**Endpoint**: `POST /domains/{domain_id}/verify`
**用途**: DNS 记录加好后触发验证。**异步**：响应只回 `{ object: "domain", id }`，不含结果；域名状态会被临时置为 `pending`（不管之前是什么），随后随验证进度变化并触发 `domain.updated` webhook。结果要靠轮询 `GET /domains/{id}` 或订阅 webhook 拿。

```ts
const { error } = await resend.domains.verify(domainId); // POST /domains/{id}/verify

// 轮询直到离开 pending（多租户页建议改用 webhook 监听 domain.verified 事件）
async function waitVerified(id: string, everyMs = 30_000) {
  for (;;) {
    const { data } = await resend.domains.get(id); // GET /domains/{id}
    if (data && data.status !== 'pending' && data.status !== 'not_started') return data;
    await new Promise((r) => setTimeout(r, everyMs));
  }
}
```

**域名 `status` 枚举**（OpenAPI 列出 6 个；dashboard 文档另有第 7 个）：

| status | 含义 |
|---|---|
| `not_started` | 已创建，还没触发过验证 |
| `pending` | 正在验证 |
| `verified` | 可发信 |
| `partially_verified` | 收/发只有一项通过；或两条发信 CNAME 只通过一条（能发，但没有备用发信服务器） |
| `partially_failed` | 域名已验证，但收/发其中一项未通过 |
| `failed` | 72 小时内没检测到记录 |
| `temporary_failure` | ⚠ 文档自相矛盾：manage-domains 页把它列为域名状态（已验证域名周期复查时记录丢失，72 小时内找回则回 `verified`，否则转 `failed`），但 OpenAPI 的域名 `status` 枚举没有它，只在 `records[].status` 里出现 |

**注意事项**：
- 通常记录加好 15 分钟内验证完成，DNS 传播最长 72 小时；超过 72 小时可重新调 verify（dashboard 的 "Restart verification"）。
- 常见失败原因：MX 值被 DNS 商自动拼上你的域名（值末尾加 `.`）；MX 指向的 region 与域名 region 不一致（"region-mismatch"）；多条 MX 指向不同 region（"multiple-regions"）；DKIM 值多了引号/被截断；CNAME 与同名子域名上已有的 A/TXT/MX 冲突（换一个 `custom_return_path`）。
- 验证 tracking 子域名也用这个接口（它会一并检查 DKIM、SPF 和 tracking CNAME）。

### 我想查看域名

**Endpoint**: `GET /domains`（列表）、`GET /domains/{domain_id}`（单个）
**用途**: 列表项**不含** `records` 和 `tracking_subdomain`，要拿 DNS 记录必须查单个。列表接口支持 cursor 分页参数 `limit` / `after` / `before`；不传 `limit` 时按 auth.md 的说法返回全部。

```ts
const { data: list } = await resend.domains.list();          // { object:"list", has_more, data:[{ id, name, status, created_at, region, open_tracking, click_tracking, capabilities }] }
const { data: one } = await resend.domains.get(domainId);    // 多出 tracking_subdomain、records[]，object:"domain"
```

### 我想改 tracking / TLS / 收发能力

**Endpoint**: `PATCH /domains/{domain_id}`
**用途**: 域名创建后唯一的配置修改口。改不了 `name`、`region`、`custom_return_path`（要换只能删了重建）。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `open_tracking` / `click_tracking` | boolean | 否 | — | 需 `tracking_subdomain` 已配置且验证通过才生效 |
| `tracking_subdomain` | string | 否 | — | 改子域名后要重新加 CNAME 并 verify，验证通过前继续用旧值；旧记录别删（已发邮件里的链接还在用） |
| `tls` | string | 否 | `opportunistic` | `opportunistic` \| `enforced`（PATCH 的 OpenAPI 没写 enum 数组，仅描述里写了这两个值） |
| `capabilities.sending` / `capabilities.receiving` | string | 否 | 保持原值 | `enabled` \| `disabled`，可只传一个，至少保留一个 enabled |

```ts
const { data, error } = await resend.domains.update({
  id: domainId,              // Node SDK 把 id 放在同一个对象里，不是第一个位置参数
  openTracking: false,
  clickTracking: true,
  trackingSubdomain: 'links',
  tls: 'enforced',
});
// 响应只有 { object: "domain", id }，改完要 GET 才能看到新的 Tracking 记录
```

**注意事项**：tracking 默认关闭，官方建议只对 Broadcasts 开 open tracking，事务邮件别开，以免被收件方判为营销邮件。自定义 tracking 子域名需要 Resend 签发 TLS 证书，受地区限制的域名不支持。

### 域名已被另一个团队占用（claim 流程）

**场景**: `POST /domains` 报「domain has been registered already」。先确认不是自己登错团队/同事已加过——如果你控制那个团队，直接在那边删掉再在这边创建即可（团队间"转移"没有专门接口，就是删+建）。只有**无法访问占用团队**时才走 claim。

**与普通 create+verify 的区别**: claim 用一条 TXT 记录证明你控制该域名，Resend 通过安全检查后把域名从原团队释放、以**全新域名（新 DKIM 密钥）**转入你的团队。原团队的 DNS 记录不能复用，claim 完成后还要走一遍正常的"加 DKIM 记录 → verify"。

| 步骤 | Endpoint | SDK | 说明 |
|---|---|---|---|
| 1 发起 | `POST /domains/claim` | `resend.domains.claims.create({ name })` | body 同创建域名（`name` 必填，可带 `region`、`custom_return_path`、`open_tracking`、`click_tracking`、`tracking_subdomain`；⚠ 与 create 不同，规范里**没有** `tls` 和 `capabilities`）。响应 201 是 `domain_claim`；若已有一个完全相同的 pending claim，返回 200 并原样返回那个 claim |
| 2 加 TXT | — | — | 把响应 `record`（`type` 恒为 `TXT`，`name` 是被 claim 的域名本身，`value` 形如 `resend-domain-verification=…`）加到 DNS |
| 3 验证 | `POST /domains/{domain_id}/claim/verify` | `resend.domains.claims.verify(domainId)` | 异步；`domain_id` 用 claim 响应里的 **占位域名 id**（`domain_id` 字段），不是 claim 自己的 `id` |
| 4 轮询 | `GET /domains/{domain_id}/claim` | `resend.domains.claims.get(domainId)` | 直到 `status` 为 `completed` |
| 5 收尾 | `GET /domains/{domain_id}` → 加新 DKIM → `POST /domains/{domain_id}/verify` | 同上文 | 完成后才能收发 |

```ts
const { data: claim } = await resend.domains.claims.create({ name: 'example.com' }); // POST /domains/claim
// claim.record => { type:"TXT", name:"example.com", value:"resend-domain-verification=…", ttl:"Auto" }
// …用户加完 TXT 后：
await resend.domains.claims.verify(claim!.domain_id!); // POST /domains/{domain_id}/claim/verify
const { data: latest } = await resend.domains.claims.get(claim!.domain_id!); // GET /domains/{domain_id}/claim
```

**claim `status` 枚举**: `pending`（等 DNS 验证）| `verified`（TXT 通过，转移进行中）| `completed`（已归你的团队）| `blocked`（安全检查拦下，看 `blocked_reason`：`grace_period` | `recent_owner_activity` | `pending_scheduled_emails`）| `expired`（claim 过期，dashboard 文档说窗口 7 天，`expires_at` 示例也是 +7 天）| `superseded`（被更新的 claim 取代）| `canceled` | `failed`（看 `failure_reason`）。

**取消 claim**: 没有专门接口，`DELETE /domains/{domain_id}` 删掉占位域名即可。

### 我想删除域名 / 换 region

**Endpoint**: `DELETE /domains/{domain_id}`（SDK `resend.domains.remove(id)`），响应 `{ object: "domain", id, deleted: true }`。

**注意事项**：
- 域名配置过 tracking 子域名的话，删除会连带撤掉 Resend 托管的跟踪代理，**已发出邮件里的所有跟踪链接立刻失效**。要保链接，先自建代理指向 Resend 的 tracking DNS 记录再删。
- 换 region 没有接口：删 → 用新 region 重建 → 按新响应改 DNS（MX 值里带 region）。中间会有发信中断，且同一域名同时只能存在一个，要跨 region 容灾请用不同子域名（`us.example.com` / `eu.example.com`）。
- 删掉再在别的团队重建，等于"转移"；DNS 传播期间发信会中断。

### 域名相关 403 速查

| 错误 | 触发 | 处理 |
|---|---|---|
| 403 code `1010` `Access denied` | 裸 HTTP 缺 `User-Agent`，请求根本没到 API | 加 `User-Agent` header |
| 403 `validation_error`「You can only send testing emails to your own email address」 | `from` 用 `onboarding@resend.dev` 却发给非本人账号邮箱 | 验证自己的域名 |
| 403 `validation_error`「The domain.com domain is not verified」 | `from` 的域名与已验证域名不完全一致（验证的是 `sending.domain.com` 却用 `domain.com`，或状态不是 verified） | 改 `from` 精确匹配，或加并验证那个域名 |
| 403 `validation_error`「The example.com domain has been registered already」 | `POST /domains` 撞上别的团队已验证的域名 | 上文 claim |

## API key

### 我想创建一个 key

**Endpoint**: `POST /api-keys`
**用途**: 程序化签发 key，典型用途是给每个租户/服务发一把只能发信、只能用某个域名的 key。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `name` | string | 是 | — | 最多 50 字符（页面说明；OpenAPI 未写上限） |
| `permission` | string | 否 | ⚠ 文档未说明 | `full_access`（增删改查任何资源）\| `sending_access`（只能发邮件）。拼写就是这两个下划线值，dashboard 显示为 "Full access" / "Sending access" |
| `domain_id` | string | 否 | — | 把 key 限定为只能从这一个域名发信。**只在 `permission` 为 `sending_access` 时有效**；配 `full_access` 时文档说 "only used when sending_access"，即被忽略（⚠ 是忽略还是报错，文档未说明） |

**示例**（SDK）：

```ts
const { data, error } = await resend.apiKeys.create({
  name: 'Tenant: acme.example.com',
  permission: 'sending_access',
  domain_id: domainId, // ⚠ 官方 multi-tenant 页的 Node 示例就是 snake_case 的 domain_id；SDK 是否也接受 domainId，文档未说明
});
// data.token 只在这一次响应里出现，立刻存进你的密钥库
```

**示例**（`fetch`，底层 `POST /api-keys`）：

```ts
const res = await fetch('https://api.resend.com/api-keys', {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${process.env.RESEND_API_KEY}`, // 必须是 full_access 的 key
    'Content-Type': 'application/json',
    'User-Agent': 'my-app/1.0',
  },
  body: JSON.stringify({ name: 'Tenant: acme.example.com', permission: 'sending_access', domain_id: domainId }),
});
const { id, token } = await res.json(); // 201
```

**示例响应**（201）：`{ "id": "<api_key_id>", "object": "api_key", "token": "<以 re_ 开头的密钥>" }`。字段名是 **`token`**（不是 `key`/`secret`）；⚠ OpenAPI 响应表只列了 `id` 和 `token`，页面示例多一个 `object: "api_key"`。

**注意事项**：
- `token` **只在创建响应里返回一次**，之后 `GET /api-keys` 和 dashboard 都看不到明文，无法找回，只能删了重发。
- key 不会自动过期，直到你删除为止；文档建议至少 90 天轮换一次，30 天没用过的 key dashboard 会标出来。
- 轮换顺序：新建同权限同域名的 key → 部署到所有环境 → 在 Logs 里按 key 过滤确认有请求 → 再删旧 key。两把 key 可同时有效。

### 列出 / 重命名 / 删除

| 操作 | Endpoint | SDK | 响应 | 备注 |
|---|---|---|---|---|
| 列出 | `GET /api-keys` | `resend.apiKeys.list()` | `{ object:"list", has_more, data:[{ id, name, created_at, last_used_at }] }` | 列表项**没有** `permission`、`domain_id`、`token`（⚠ 想知道一把 key 的权限只能去 dashboard，文档未说明 API 途径）。支持 `limit`/`after`/`before` |
| 重命名 | `PATCH /api-keys/{api_key_id}` | `resend.apiKeys.update(id, { name })`（id 是第一个位置参数，和 `domains.update` 不同） | `{ object:"api_key", id }` | **只能改 `name`**；`permission` 和 `domain_id` 只能在 dashboard 改 |
| 删除 | `DELETE /api-keys/{api_key_id}` | `resend.apiKeys.remove(id)` | `{ object:"api_key", id, deleted:true }` | 立即生效；先确认新 key 已上线 |

### 401 / 403 对照

errors 页把 `restricted_api_key` 同时列在 401 和 403 下，但**消息不同，是两种情况**，并不矛盾：

| HTTP | `name` | message | 含义 |
|---|---|---|---|
| 401 | `missing_api_key` | Missing API key in the authorization header | 没带 `Authorization: Bearer` |
| 401 | `restricted_api_key` | This API key is restricted to only send emails | **`sending_access` 的 key 调了发信以外的接口**（域名、key、contacts…）→ 换 `full_access` key |
| 403 | `restricted_api_key` | API key is not active | key 本身已失效（被删/停用），去 dashboard 检查或重建 |
| 403 | `suspended_api_key` | This API key is suspended | 被 Resend 停用，联系支持 |
| 403 | `invalid_permission` | Access token is missing required scopes | 面向 access token 的 scope 错误（⚠ 与 API key permission 的关系文档未说明） |

结论（疑点 6）：`sending_access` 越权是 **401 `restricted_api_key`**，auth.md 与 errors 页一致；403 那条是"key 不活跃"。⚠ 未实测。另外 ⚠ 文档未说明：`domain_id` 限定的 key 用别的域名当 `from` 发信时返回什么（推测是 403 `validation_error` "domain is not verified" 一类，未证实）。

### 多租户建议

官方 KB 给出两条路，没有"唯一正确答案"：

- **方案 A 单账号**：每个租户域名用 `POST /domains` 加进你的团队 → verify（异步，用 `domain.verified` webhook 而不是轮询）→ `POST /api-keys` 发 `sending_access` + `domain_id` 的 key 给该租户用。全程 API 可自动化；代价是所有租户共享发信信誉（一个租户乱发会拖累甚至导致整个账号被停）、dashboard 没有按租户的统计、总量大了要申请提高速率限制（默认 10 req/s/team 是全团队所有 key 共享）、每个租户域名都占团队域名配额。webhook 路由靠发信时打 `tags`（如 `tenant_id`）。
- **方案 B BYOK**：租户自己注册 Resend、验证域名、把 key 交给你，你按租户 `new Resend(tenantKey)`。信誉、配额、webhook 全隔离，但团队创建**没有 API**，租户必须手动开户。
- A→B 或 B→A 迁移时，域名必须先从原账号删除再在新账号验证，DNS 传播期间会断发。

## 疑点核实结论汇总

1. **`region` 枚举与默认值**：OpenAPI 明确 4 个值 `us-east-1` | `eu-west-1` | `sa-east-1` | `ap-northeast-1`，默认 `us-east-1`；Markdown 页只列枚举不写默认（不矛盾）。`custom_return_path` 默认 `send`，两边一致。⚠ 未实测。
2. **`permission` 拼写**：`full_access` / `sending_access`（OpenAPI enum 与页面一致）。`domain_id` 只对 `sending_access` 有效。token 字段名 `token`，只在创建响应返回一次（create-an-api-key 页与 multi-tenant 页明说）。⚠ `permission` 缺省时取哪个值文档未说明。
3. **verify 同步/异步**：异步。响应只有 `{object, id}`；域名被临时置 `pending`，之后通过 `domain.updated` webhook 或轮询 GET 看结果。域名 status 枚举见上表；`temporary_failure` 是否是域名级状态，OpenAPI 与 dashboard 文档 ⚠ 自相矛盾。
4. **claim 流程解决什么**：域名已被你无法访问的另一个团队验证占用时，用 TXT 证明所有权把它"抢"过来；与普通 create 的区别是多一轮 TXT 验证 + 安全检查，且完成后是带新 DKIM 的全新域名，仍要再走一次加记录+verify。若你能访问原团队，直接删+建即可。
5. **PATCH 取值**：`open_tracking` / `click_tracking` 为 boolean；`tls` 为 `opportunistic` | `enforced`，默认 `opportunistic`（PATCH 处 OpenAPI 只在描述里写枚举，未给 enum 数组）。⚠ PATCH 是否接受 `custom_return_path`，页面与规范矛盾。
6. **sending_access 越权**：401 `restricted_api_key`（见对照表）。⚠ 未实测。
