# 鉴权与 GraphQL Endpoint

> 全部内容整理自官方文档（抓取于 2026-09-21）与 GraphQL SDL 规范，**未用真实 API Key 或 OAuth App 调用验证**。凡是行为描述（"会报错"、"返回 xxx"）而非纯字段定义的地方，均为 `⚠ 文档原文，未实测`。

## 目录
1. [GraphQL 是唯一入口，没有 REST API](#graphql-是唯一入口没有-rest-api)
2. [两种鉴权方式，header 格式不同](#两种鉴权方式header-格式不同)
3. [OAuth 2.0 完整流程](#oauth-20-完整流程)
4. [OAuth Actor Authorization（actor=app）](#oauth-actor-authorizationactorapp)
5. [Client Credentials Token（服务端到服务端）](#client-credentials-token服务端到服务端)
6. [OAuth App Manifest（程序化创建 App）](#oauth-app-manifest程序化创建-app)
7. [文件存储鉴权](#文件存储鉴权)

## GraphQL 是唯一入口，没有 REST API

**Endpoint**: `POST https://api.linear.app/graphql`

**用途**: Linear 的公开 API 是纯 GraphQL，和 Linear 内部客户端用的是同一个 endpoint、同一份 schema。没有平行的 REST API——除了 OAuth 的 token/revoke 端点（表单编码，见下）和文件上传的预签名 URL（普通 HTTPS PUT），业务数据的增删改查全部走这一个 GraphQL endpoint。**如果你的直觉是"先找 REST 端点列表"，这里没有，所有"endpoint"实际上是这份 endpoint 上的一个具体 query/mutation 名字。**

支持 introspection，可以用任意 GraphQL 客户端（Apollo Studio 的公开 workspace 也能直接探索：`https://studio.apollographql.com/public/Linear-API/variant/current/home`）内省整个 schema。

**请求格式**（两种鉴权方式共用同一个请求体格式）：

```bash
curl -X POST https://api.linear.app/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: $LINEAR_API_KEY" \
  --data '{"query": "{ viewer { id name email } }"}'
```

**示例响应**：

```json
{ "data": { "viewer": { "id": "...", "name": "...", "email": "..." } } }
```

## 两种鉴权方式，header 格式不同

Linear 支持两种鉴权方式，**请求头写法不一样，混用会导致 401**：

| 方式 | Header | 前缀 |
|---|---|---|
| 个人 API Key | `Authorization: <API_KEY>` | **没有 `Bearer` 前缀**，裸 key 直接放在 header 值里 |
| OAuth2 access token | `Authorization: Bearer <ACCESS_TOKEN>` | 有 `Bearer` 前缀，标准写法 |

个人 API Key 在 [Security & access 设置页](https://linear.app/settings/account/security) 生成，适合个人脚本、内部工具；面向他人分发的应用应使用 OAuth2。

**⚠ 容易犯的错**：大多数 API（包括 Linear 自己的 MCP 服务器，见 `agents-and-mcp.md`）个人 Key 也习惯性加 `Bearer` 前缀，但 Linear 的 GraphQL API 个人 Key **明确不加**。反过来把 OAuth token 漏加 `Bearer` 也会失败。两种 key 类型不能凭"经验"统一处理，要按上表精确匹配。

```bash
# 个人 API Key（无 Bearer）
curl https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  --data '{"query": "{ viewer { id } }"}'

# OAuth access token（有 Bearer）
curl https://api.linear.app/graphql \
  -H "Authorization: Bearer $LINEAR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"query": "{ viewer { id } }"}'
```

## OAuth 2.0 完整流程

### 1. 创建 OAuth2 应用

在 [Create OAuth2 Application](https://linear.app/settings/api/applications/new) 页面创建，配置 redirect callback URL。官方建议专门建一个工作区来管理 OAuth App（每个 admin 用户都能访问它的配置）。

### 2. 跳转授权

```http
GET https://linear.app/oauth/authorize
  ?client_id=<CLIENT_ID>
  &redirect_uri=<REDIRECT_URI>
  &response_type=code
  &scope=read,write
  &state=<CSRF_RANDOM>
```

**关键参数**

| 参数 | 必填 | 说明 |
|---|---|---|
| `client_id` | 是 | 创建 App 时分配 |
| `redirect_uri` | 是 | 必须与 App 配置一致 |
| `response_type=code` | 是 | 固定值 |
| `scope` | 是 | 逗号分隔，见下表；`read` 默认永远带上 |
| `state` | 建议 | 防 CSRF，回调时原样带回，必须校验一致 |
| `prompt=consent` | 否 | 每次都强制显示同意页（即便已授权过），用于让用户连接多个工作区 |
| `actor` | 否 | `user`（默认，以安装者身份创建资源）/ `app`（以应用自身身份创建，见下方 Actor Authorization） |
| `code_challenge` / `code_challenge_method` | PKCE 时必填 | `plain` 或 `S256` |

**Scope 列表**

| Scope | 说明 |
|---|---|
| `read` | 默认，永远存在 |
| `write` | 写权限；只需要评论/建 issue 时用更窄的 scope |
| `issues:create` | 仅允许创建 issue 及其附件 |
| `comments:create` | 仅允许创建评论 |
| `timeSchedule:write` | 创建/修改时间排班 |
| `admin` | 管理级完整权限，非必要不要申请 |
| `app:assignable` | agent 专属：允许被指派为 delegate（见 `agents-and-mcp.md`） |
| `app:mentionable` | agent 专属：允许被 @提及 |
| `customer:read` / `customer:write` | 访问 Customer 相关实体 |
| `initiative:read` / `initiative:write` | 访问 Initiative 相关实体 |

### 3. 换取 access token

```http
POST https://api.linear.app/oauth/token
Content-Type: application/x-www-form-urlencoded

code=<AUTH_CODE>&redirect_uri=<REDIRECT_URI>&client_id=<CLIENT_ID>&client_secret=<CLIENT_SECRET>&grant_type=authorization_code
```

**注意事项**：必须是 `application/x-www-form-urlencoded`，不是 JSON body（和 GraphQL 主端点的 JSON body 不一样，容易搞混）。PKCE 流程下 `client_secret` 可选但要传 `code_verifier`。

**示例响应**：

```json
{
  "access_token": "00a21d8b0c4e2375...",
  "token_type": "Bearer",
  "expires_in": 86399,
  "scope": "read write",
  "refresh_token": "sz0c8ffy95zj2ff6..."
}
```

`access_token` 有效期 24 小时（`expires_in` 秒数，~24h），过期需用 `refresh_token` 刷新。2023-12-01 前创建的 OAuth App，`scope` 字段返回的是字符串数组而不是空格分隔字符串，做兼容解析时要注意。2026-04-01 起全部 OAuth2 App 已迁移到新 refresh token 体系。

### 4. 刷新 access token

```http
POST https://api.linear.app/oauth/token
Content-Type: application/x-www-form-urlencoded

refresh_token=<REFRESH_TOKEN>&grant_type=refresh_token&client_id=<CLIENT_ID>&client_secret=<CLIENT_SECRET>
```

鉴权二选一：`client_id`/`client_secret` 作为表单参数，或 `Authorization: Basic <base64(client_id:client_secret)>`。PKCE 生成的 token 刷新时只需传 `client_id`。

**⚠ 有用的容错细节**：刷新请求有 **30 分钟宽限期**——如果用一个有效 refresh token 发起刷新请求但因网络问题没收到新 token，30 分钟内可以用同一个旧 refresh token 重放原请求再拿一次,不会因为"重复使用"被拒绝。

### 5. 撤销 token

```http
POST https://api.linear.app/oauth/revoke
```

body 传 `token`（要撤销的 token 值）+ 可选 `token_type_hint`(`access_token`/`refresh_token`)。响应码：`200` 撤销成功、`400` 无法撤销（比如已经被撤销过）、`401` token 本身鉴权失败。旧版兼容方式（`Authorization` header 或 `access_token`/`refresh_token` 表单字段）仍支持，但新集成建议统一用 `token` 字段，不要混用新旧字段。

### 6. 轮换 client secret / webhook signing secret

App 设置页 **Settings → API → Rotate secret**，client secret 和 webhook 签名密钥分开轮换。轮换 client secret 会立即让所有基于它签发的 client credentials token 失效，但**不会**撤销已经发出去的用户 access/refresh token（它们在下次刷新时才会用上新 secret）。轮换 webhook 签名密钥立即生效，要同步更新自己这边验签用的密钥。

## OAuth Actor Authorization（actor=app）

默认所有鉴权方式（个人 Key、标准 OAuth）的"操作者"都是授权的那个用户——用这个 token 创建的 issue、评论显示为该用户所为。

给 `/oauth/authorize` 加 `actor=app` 参数后，行为变成：用户只是"安装应用到工作区"，之后用这个 access token 做的操作（建 issue、评论、改状态）显示为**应用自身**，不是安装者。这是给 agent、service account 用的模式,**安装需要 admin 权限**(因为是工作区级授权)。

`actor=app` 取代了旧版 `actor=application` 参数——`actor=application` 已废弃但仍兼容,如果现有集成在用可以继续用,新集成一律用 `actor=app`。二者核心区别:`actor=application` 允许同一个 token 在不同场景下时而代表用户、时而代表应用(双重身份);`actor=app` 的 token 从授权开始就固定是应用身份,不会切换。如果现有代码依赖 `actor=application` 的双重身份特性做迁移,需要让用户走两次授权(一次拿个人 token,一次拿 app token)。

**自定义显示名 / 头像**（仅 `actor=app` 场景常用）：在 `issueCreate` / `commentCreate` 的 input 里传 `createAsUser` + `displayIconUrl`，渲染成 "User (via Application)" 格式，方便在没有 Linear 账号的第三方系统里标注真实操作者：

```graphql
mutation IssueCreate {
  issueCreate(
    input: {
      title: "New exception"
      teamId: "9cfb482a-81e3-4154-b5b9-2c805e70a02d"
      createAsUser: "Mark"
      displayIconUrl: "http://path.to/image.png"
    }
  ) {
    success
    issue { id title }
  }
}
```

## Client Credentials Token（服务端到服务端）

给 CI、定时任务这类不方便走用户交互授权流程的场景。**先在 OAuth App 设置里手动打开 client credentials 开关**，才能使用这个 grant type。

```http
POST https://api.linear.app/oauth/token

grant_type=client_credentials&scope=read,write&client_id=<CLIENT_ID>&client_secret=<CLIENT_SECRET>
```

（鉴权同样可以用 `Authorization: Basic <base64(client_id:client_secret)>` 代替表单里的 `client_id`/`client_secret`。）

**注意事项**：
- 生成的 token 是 `app` actor token（等价于走了 `actor=app`），覆盖工作区**全部公开团队**，有效期固定 **30 天**，**没有 refresh token**——收到 401 就要重新请求一个新 token，官方建议"每次运行开始时现拿一个，只在这次运行内用，不要手动复制持久化成长期 Key"。
- 同一 scope 下最多可有 **1000 个并行 active token**；如果用不同 scope 再请求一次，**会撤销所有旧的 app actor token**，换成携带新 scope 的这一个——多个 token 并行只在 scope 完全相同时才可能。
- 如果先用别的 grant type（比如标准授权码流程 + `actor=app`）拿到过一个 app token，就不能再叠加多个并行 app token——要多个并行 token 必须全部走 client_credentials 生成。
- App 的 client secret 被轮换后，该 App 名下所有 client credentials token 会失效。
- 团队访问范围可以在 App 详情页随时调整，即便 token 已经生成。

未开启 client credentials 的 App 调用会收到：

```json
{ "error": "Error", "error_description": "Client does not support the client_credentials grant type" }
```

## OAuth App Manifest（程序化创建 App）

允许用 URL 查询参数或 JSON manifest（`$schema: https://linear.app/.well-known/oauth-app-manifest.schema.json`, `schemaVersion: "1.0.0"`）预填 [Create OAuth2 Application](https://linear.app/settings/api/applications/new) 页面，适合托管平台生成"一键安装"链接，或开源项目分享预配置。两种格式等价，同时提供时 JSON manifest 优先。

**核心字段**（URL 参数用点号路径，如 `oauth.client_name`；JSON 用嵌套对象）：

| 字段 | 必填 | 限制 |
|---|---|---|
| `distribution` | 否，默认 `private` | `private` / `public` |
| `developer.name` | 是 | 2–80 字符 |
| `oauth.client_name` | 是 | 2–80 字符，**不能包含 `Linear` 字样，不能包含 `http://`/`https://`** |
| `oauth.client_uri` | 是 | 绝对 URL |
| `oauth.redirect_uris` | 是 | 1–32 个，可重复传参表示数组，值需唯一 |
| `oauth.grant_types` | 否，默认 `authorization_code` | `authorization_code`（必含） / `client_credentials` |
| `webhook.url` | webhook 块存在时必填 | 必须 `https://`，host 不能是 loopback/私网地址/`linear.app` |
| `webhook.resourceTypes` | webhook 块存在时必填 | 见 `webhooks.md` 的 resourceTypes 表 |

URL 参数示例（省略号处为真实值，参数间用 `&` 连接）：

```
https://linear.app/settings/api/applications/new?distribution=public&oauth.client_name=Acme+Agent&oauth.client_uri=https%3A%2F%2Facme.dev&oauth.redirect_uris=https%3A%2F%2Facme.dev%2Fcallback&oauth.grant_types=authorization_code&oauth.grant_types=client_credentials&webhook.enabled=true&webhook.url=https%3A%2F%2Facme.dev%2Fwebhook&webhook.resourceTypes=Issue&webhook.resourceTypes=Comment
```

JSON manifest 通过单个 `manifest` 查询参数（URL-encoded JSON）传递，也可以本地存成文件用 `$schema` 做编辑器/CI 校验。**未识别的查询参数会被静默忽略**，拼错参数名不会报错，只是不会生效。

## 文件存储鉴权

上传到 Linear 的文件（图片、附件）存放在私有云存储 `https://uploads.linear.app`，**需要鉴权才能访问**，即便在 API 响应里拿到的 URL 也不能直接公开分享/嵌入。

```bash
curl https://uploads.linear.app/<workspace-id>/<file-id> \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

（这里的裸 URL 直接访问同样接受和 GraphQL API 相同的鉴权 header 格式——个人 Key 无 Bearer、OAuth token 有 Bearer,与上文一致。）

可选在 GraphQL 请求上传 `public-file-urls-expire-in: <seconds>` header,让响应里所有文件 URL 都带上限时签名,允许不鉴权临时访问(用于短期分享):

```ts
const client = new LinearClient({
  apiKey: process.env.LINEAR_API_KEY,
  headers: { "public-file-urls-expire-in": "60" }
});
```

如果要在 Linear 之外长期展示这些图片,官方建议下载后自托管,不要依赖 Linear 的私有存储直连。文件上传本身的 mutation（`fileUpload`）见 `references/issues-and-comments.md` 附录或官方 [How to upload a file](https://linear.app/developers/how-to-upload-a-file-to-linear) 指南；核心流程是 `fileUpload` mutation 拿预签名 URL → 服务端 `PUT` 文件内容（**不能在浏览器端直接 PUT，会被 Linear 的 CSP 拦截**，必须代理到自己的服务端）。
