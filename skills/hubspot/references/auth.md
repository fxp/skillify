# 鉴权：私有应用 access token / Service Key（beta）/ OAuth 应用

目录：[三种鉴权方式怎么选](#三种鉴权方式怎么选) · [私有应用 access token](#私有应用-access-token-legacy-private-app) · [Service Key（beta）](#service-key-beta) · [OAuth 应用](#oauth-应用) · [Scopes 模型](#scopes-模型) · [已弃用：hapikey](#已弃用的-hapikey)

全部内容 ⚠ 文档原文，未实测（整理自 `docs/apps/legacy-apps/private-apps/overview`、`docs/apps/developer-platform/build-apps/authentication/*`、`docs/developer-tooling/platform/usage-guidelines`，抓取于 2026-09-21）。

## 三种鉴权方式怎么选

HubSpot 当前所有 CRM API 请求都用同一个请求头：

```
Authorization: Bearer <token>
```

`<token>` 怎么拿，取决于你在做什么：

| 场景 | 用哪种 | 关键特征 |
|---|---|---|
| 给自己的账号写脚本 / 内部工具 / 单账号 Agent（本 skill 覆盖的主场景） | **私有应用 access token**（legacy private app）或 **Service Key（beta）** | 控制台手动创建，token 直接复制，静态、不过期（除非手动 rotate） |
| 要分发给其他人的多个 HubSpot 账号安装（应用市场上架，或管理一批已知客户账号） | **OAuth 应用** | 需要自建 OAuth 后端，处理 authorization code 换 token、refresh token 续期 |
| 只是想临时探一两个端点，不想建应用 | **Service Key（beta）**，创建流程最短 | 功能上等价于私有应用 token，UI 更轻量，但处于公开 beta，行为可能变 |

**训练记忆里最常见的错误假设：HubSpot 有一把全局"API Key"（`hapikey`），拼进每个请求的 query string 就能用。这个鉴权方式对 CRM 对象 API 早已不适用**，见文末[已弃用的 hapikey](#已弃用的-hapikey)。

## 私有应用 access token（legacy private app）

官方文档把这类应用称为 "Legacy private apps"（`docs/apps/legacy-apps/private-apps/overview`），但页面明确写"仍受 HubSpot 支持"（Legacy apps are still supported by HubSpot），只是拿不到构建在新版 developer platform（2025.2/2026.03/2026.09）上的最新功能（如 UI extensions、serverless functions）。对于"读写 CRM 数据"这个诉求，legacy private app 完全够用，也是目前 HubSpot 全站示例代码里最常见的鉴权方式。

**创建步骤**（控制台操作，无 API）：

1. HubSpot 账号 → **Development** → 左侧栏 **Legacy apps** → 右上角 **Create legacy app** → 选 **Private**。
2. 填名称、Logo、描述。
3. **Scopes** 标签页 → **Add new scope** → 勾选需要的 scope（见下方 [Scopes 模型](#scopes-模型)）。必须是 [super admin](https://knowledge.hubspot.com/user-management/hubspot-user-permissions-guide#super-admin) 才能创建/管理私有应用。
4. 可选：**Webhooks** 标签页配置事件订阅（私有应用支持 webhook，但订阅本身**不能通过 API 编辑**，只能在这个 UI 里改）。
5. **Create app**，弹窗展示 access token，**这是唯一能看到完整 token 的机会之一**（之后可在 Auth 标签页点 Show token 再看）。

**调用示例**：

```bash
curl --request GET \
  --header "Authorization: Bearer $HUBSPOT_ACCESS_TOKEN" \
  --url "https://api.hubapi.com/crm/v3/objects/contacts?limit=10&archived=false"
```

token 格式类似 `pat-na1-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`（`na1` 是数据中心标识，欧洲账号可能是 `eu1` 等）。⚠ 文档原文，未实测：具体前缀因账号数据中心而异，未逐一验证。

**限制与运维要点**：

- 每个 HubSpot 账号最多创建 **20 个**私有应用。
- 私有应用**不支持自定义 timeline events**（要用这个功能得建 public app）。
- **账号降级会导致 token 静默失去部分 scope 权限**（token 字符串不变，但请求会开始因为缺 scope 报错）——比如账号失去 HubDB 功能后，token 里配置过的 HubDB scope 自动失效。
- **创建 token 的用户被移除账号后，部分调用会开始报 `"result": "USER_DOES_NOT_HAVE_PERMISSIONS"`**，需要 rotate token 或把该用户加回账号解决。
- **Rotate token**：Auth 标签页 → Rotate → 选"立即撤销旧 token"或"7 天后过期旧 token"（给迁移窗口期）。官方建议每 6 个月 rotate 一次。
- **查 token 信息**（Hub ID、scopes、创建者）：`POST /oauth/v2/private-apps/get/access-token-info`，请求体 `{"tokenKey": "<token>"}`。
- **查每日用量**：`GET /account-info/v3/api-usage/daily/private-apps`。
- **调用日志**：应用详情页 Logs 标签页，只保留 30 天，且**不记录请求体/响应体**，需要更长审计需求要自己在客户端落日志。

## Service Key（beta）

新版 developer platform（2025.2 / 2026.03）配套的轻量替代方案，公开 beta，2026-09 抓取时仍在有效期内。功能上和私有应用 token 几乎等价：也是 `Authorization: Bearer <key>` + 按 scope 授权，控制台生成，不需要建"应用"这个概念。

**创建步骤**：账号 → **Development** → **Keys** → **Service keys** → **Create service key** → 起名字 → 勾 scopes → **Create**。

**调用示例**（文档给出的官方示例，⚠ 注意这个 beta 功能的示例代码用的仍是 `crm/v3/objects/contacts` 而不是新的 2026-09 路径）：

```bash
curl --request GET \
  --header "Authorization: Bearer pat-na1-*********-****-****-****-************" \
  --url "https://api.hubapi.com/crm/v3/objects/contacts?limit=10&archived=false"
```

**限制**：

- 只能创建 super admin 或有 "Developer tools access" 权限的用户才能管理。
- **只能用来发 REST API 请求**，不能用于 webhook 鉴权、UI extension 调用，或其他 developer platform 专属功能——那些场景仍需要建正式的 app 并用它的 static/OAuth token。
- 限流和"私有分发的应用"（版本 2025.2/2026.03）共用同一套额度（见 `references/errors-and-limits.md`）。
- Rotate / 删除流程和私有应用 token 类似（immediate 或 7 天延迟过期）。
- **这是 public beta**：功能仍在变化中，参与即代表同意 HubSpot 的 Beta Terms，正式发布前不建议依赖它做生产环境的唯一鉴权路径。

## OAuth 应用

只有要把集成分发到**多个不受控的 HubSpot 账号**（应用市场上架，或管理一批授权客户账号）时才需要。核心流程：

1. 在开发者账号里建一个 app，配置 `auth.type = oauth`，`distribution` 设为 `marketplace`（应用市场上架）或 `private`（自己指定最多 **10 个**账号白名单）。
2. 需要自建一个 OAuth 后端（HubSpot 提供 Node.js quickstart，可跑在 Docker 里）来处理 authorization code flow：把用户导向 `https://app.hubspot.com/oauth/authorize`，换回 authorization code，再用 `client_id` + `client_secret` 在 `https://api.hubapi.com/oauth/v1/token` 换 access token + refresh token。
3. access token 有 `expires_in`（短期），需要用 refresh token 主动刷新；**`401` 不是"该刷新 token 了"的可靠信号**，要按 `expires_in` 到期时间主动刷新，不要等到收到 401 才刷新。
4. 调用方式同样是 `Authorization: Bearer <access_token>`。

```bash
curl --request GET \
  --header "Authorization: Bearer 00000000-aaaa-xxx-yyyy-zzzzzzzzzzzz" \
  --url "https://api.hubapi.com/crm/objects/2026-03/contacts?limit=10&archived=false"
```

⚠ 文档原文，未实测：OAuth 应用请求**不会**返回 `X-HubSpot-RateLimit-Daily` / `X-HubSpot-RateLimit-Daily-Remaining` 响应头（文档在限流页面明确写了这个排除项），需要另外通过账号信息 API 查用量。

**Client credentials token**（不同于面向用户安装的 OAuth token）：目前文档里唯一提到用到它的场景是 webhooks journal API 的账号级配置，用 `grant_type=client_credentials` 换一个短期 token，代表"应用本身"而不是某个装了应用的用户。

## Scopes 模型

HubSpot 的 scope 命名遵循 `crm.objects.<object>.<read|write>` 这种模式，例如：

- `crm.objects.contacts.read` / `crm.objects.contacts.write`
- `crm.objects.companies.read` / `crm.objects.companies.write`
- `crm.objects.deals.read` / `crm.objects.deals.write`
- `crm.objects.custom.read` / `crm.objects.custom.write`（所有自定义对象共用，不分对象类型）
- `crm.schemas.<object>.read` / `crm.schemas.<object>.write`（管理 schema 本身，和读写记录的 scope 分开）

**敏感度分档**（仅 Enterprise 账号开通"敏感数据属性"功能时相关）：多数对象除了基础 read/write，还有两档更高权限：

- `crm.objects.<object>.sensitive.read.v2` / `.sensitive.write.v2`
- `crm.objects.<object>.highly_sensitive.read.v2` / `.highly_sensitive.write.v2`

⚠ 未实测：只有基础 read scope、没有 sensitive scope 时，`GET` 一条记录是否会连非敏感属性一起报 403，还是只是悄悄跳过敏感属性只返回非敏感的——从 `properties/guide` 的措辞（"默认只返回非敏感属性，需要显式传 `dataSensitivity=sensitive` 才返回敏感属性"）推断更可能是后者（静默过滤），但未验证。

**granular scopes 迁移**：官方文档提到"Update your app to use granular scopes (BETA)"，暗示存在更粗粒度的旧式 scope 和这套细粒度 scope 并存的过渡期，⚠ 文档未说明旧式粗粒度 scope 具体叫什么、新旧能否混用，需要时另查该迁移指南。

查看某个 endpoint 具体需要哪些 scope：每个 endpoint 的官方参考页顶部都有一个"Required Scopes"折叠框，列出该端点接受的**任意一个**满足即可的 scope 集合（不是全部都要）——例如创建联系人页面列出的是一长串 40+ 个 scope，任意一个匹配用户 token 已授权的 scope 都能过。

## 已弃用的 hapikey

训练语料里最常见的 HubSpot 鉴权写法——在每个请求 URL 拼 `?hapikey=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`——**已经不是 CRM 对象 API 的有效鉴权方式**，不要凭记忆这样写。

当前文档里唯一还提到 `hapikey` 的地方是"Developer API key"（开发者账号级别的 key，不是某个 HubSpot 账号的 key），只用于极少数开发者工具类端点（如自定义 conversations channel 注册），用法是 `?hapikey={YOUR_DEVELOPER_API_KEY}&appId={appId}` 这种 query 参数组合，跟"读写某个账号的 contacts/companies/deals"完全无关。**创建/读取/更新/搜索/批量操作 CRM 对象，一律用本文件前三节的 Bearer token 方式**，不要在这些端点上尝试 `hapikey`。
