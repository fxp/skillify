# 鉴权与 Token（Web API）

> ⚠ 全部内容来自 `docs.sentry.io/api/auth.md`、`docs.sentry.io/api/permissions.md`、`docs.sentry.io/account/auth-tokens.md` 转录，未经真实调用验证。

## 目录

- [请求头精确格式](#请求头精确格式)
- [三种 Auth Token 怎么选](#三种-auth-token-怎么选)
- [Scope（权限范围）对照表](#scope权限范围对照表)
- [OAuth2（第三方应用代表用户访问）](#oauth2第三方应用代表用户访问)
- [Device Authorization Flow（CLI/无浏览器场景）](#device-authorization-flowcli无浏览器场景)
- [DSN Authentication（极少数 endpoint）](#dsn-authentication极少数-endpoint)
- [遗留 API Key（不要用于新项目）](#遗留-api-key不要用于新项目)

## 请求头精确格式

```
Authorization: Bearer <token>
```

示例：

```bash
curl -H 'Authorization: Bearer 1a2b3c' \
  https://sentry.io/api/0/organizations/acme/projects/
```

没有奇怪前缀、没有自定义 header 名——就是标准 Bearer。**这一点和本目录下其他一些平台（如 AutoDL 裸 token 不带 `Bearer`）不一样，不要套别的平台的鉴权习惯。**

## 三种 Auth Token 怎么选

Sentry 有三种 token，权限模型和生命周期都不同，选错会导致"权限不够"或"权限过大"：

| 类型 | 绑定对象 | 权限范围 | 权限是否可自定义 | 典型场景 |
| :--- | :--- | :--- | :--- | :--- |
| **Organization Token** | 组织 | 固定的一组 CI 相关权限，**不可自定义** | 否 | CI/CD：上传 source map、创建 release，官方**首推**这个 |
| **Internal Integration Token** | 组织 | 组织内全部项目，权限可自定义（创建时选 scope，之后可编辑） | 可创建时选、之后编辑 | 需要 Organization Token 给不了的完整 API 访问权限时（如程序化建项目） |
| **Personal Token** | 用户 | 用户有权限访问的组织/项目子集，**创建后不能再编辑权限** | 可创建时选，不可编辑 | 代表某个用户操作（如"拉这个用户能看到的全部 issue"） |

选择建议（来自官方文档原话）：
- **默认首选 Organization Token**——CI 环境下如果这个 token 泄漏，攻击者能做的事有限，因为权限本身就窄。
- 需要 Organization Token 覆盖不到的能力（比如程序化创建项目）时，用 **Internal Integration**。
- 需要"以某个用户身份"操作、而不是"以组织身份"操作时，用 **Personal Token**；但注意如果创建者被移出组织，token 会失效，**不建议用于 CI**。

创建位置：
- Organization Token：`Settings > Developer Settings > Organization Tokens`。
- Internal Integration：先在 `Settings > Developer Settings` 创建一个 Internal Integration，安装后自动生成 token（见 `docs.sentry.io/integrations/integration-platform/internal-integration.md`）。
- Personal Token：账号菜单里的 `Personal Tokens` 页面。

⚠ 文档原文，未实测：Organization Token 创建后**只在创建时完整显示一次**，之后列表页只能看到末尾几位字符，丢了要重新建。

## Scope（权限范围）对照表

来自 `docs.sentry.io/api/permissions.md`：

| 资源域 | GET | PUT/POST | DELETE |
| :--- | :--- | :--- | :--- |
| Organizations | `org:read` | `org:write` | `org:admin` |
| Projects | `project:read` | `project:write` | `project:admin` |
| Teams | `team:read` | `team:write` | `team:admin` |
| Members | `member:read` | `member:write` | `member:admin` |
| Issues & Events | `event:read` | `event:write`（仅适用于**更新** issue） | `event:admin`（仅适用于**删除** issue） |
| Releases | `project:releases`（GET/PUT/POST/DELETE 统一用这一个 scope） | 同左 | 同左 |
| CI 专用 | — | `org:ci`（source map 上传、建 release、code mapping） | — |

**易错点**（文档明确写出的 Note）：
- **Events 本身是不可变的**，PUT/DELETE 权限只对 issue（聚合体）生效，不能单独删/改一次具体的 event。
- **`project:releases` scope 会同时授予 project 级和 org 级的 release endpoint 访问权**，不需要额外再加别的 scope；但如果用 `sentry-cli` 管理 release，还需要**额外加 `org:read`**（文档明确提醒的坑）。
- **Release 的写操作（create/update/delete/文件上传/deploy）要求 token 所属用户对该 release 关联的全部项目都有访问权**——如果组织关闭了 Open Membership，用户只能对自己所在 team 名下的项目做这些操作，即使 token 本身 scope 给够了也会因为用户的项目访问权限不够而被拒（⚠ 文档原文，未实测具体报错内容）。

## OAuth2（第三方应用代表用户访问）

面向"公开集成/第三方应用需要代表 Sentry 用户访问"的场景（对比：Internal Integration 是"我自己组织内部用"，OAuth2/Public Integration 是"给所有 Sentry 用户装"）。标准 Authorization Code Grant：

1. **发起授权**：把用户导向

   ```
   https://sentry.io/oauth/authorize/?client_id={CLIENT_ID}&response_type=code&scope={SCOPES}&redirect_uri={REDIRECT_URI}&code_challenge={CHALLENGE}&code_challenge_method=S256
   ```

   `scope` 是空格分隔的 permission 列表（同上表的 scope 名）。**强烈建议带 PKCE**（`code_challenge`/`code_challenge_method=S256`），防授权码截获攻击。

2. **换取 token**：

   ```bash
   curl -X POST https://sentry.io/oauth/token/ \
     -d client_id={CLIENT_ID} \
     -d client_secret={CLIENT_SECRET} \
     -d grant_type=authorization_code \
     -d code={AUTHORIZATION_CODE} \
     -d code_verifier={CODE_VERIFIER}
   ```

   响应含 `access_token`、`refresh_token`、`expires_in`（**access token 30 天过期**）、`scope`、`user`。

3. **刷新**：`grant_type=refresh_token` + `refresh_token=...`。

4. **组织范围限制**：OAuth token 只能访问用户在授权流程里选定的那一个组织，`GET /api/0/organizations/` 只会返回这一个组织，不是用户所在的全部组织（这一点和 Personal Token 不同，容易被误以为是 bug）。

5. **错误处理**：401 = token 过期/被吊销（刷新或重新授权）；403 = scope 不够（申请追加 scope 或优雅降级）。

⚠ 文档原文，未实测：以上响应结构、`expires_in` 具体秒数（文档样例 `2591999`，约等于 30 天）均未拿真实 OAuth app 验证过。

## Device Authorization Flow（CLI/无浏览器场景）

RFC 8628 设备授权流程，专给"没有浏览器/输入受限的设备"用（CLI 工具、CI/CD、Docker 容器、headless 环境）——这对"agent 在无头环境里需要用户一次性授权"的场景很贴合：

1. `POST https://sentry.io/oauth/device/code/`，body 带 `client_id`、可选 `scope`，拿到 `device_code`（轮询用）、`user_code`（给用户看的短码，格式 `XXXX-XXXX`，字符集刻意避开 0/O、1/I/L 避免混淆）、`verification_uri`、`expires_in`（默认 600 秒）、`interval`（默认 5 秒轮询间隔）。
2. 把 `user_code` 和 `verification_uri` 显示给用户，用户在**任意设备的浏览器**上打开链接、输入短码、批准。
3. 按 `interval` 轮询 `POST https://sentry.io/oauth/token/`（`grant_type=urn:ietf:params:oauth:grant-type:device_code`），未完成时收到 `{"error": "authorization_pending"}`，直到拿到 `access_token`/`refresh_token`。
4. 轮询过快会收到 `slow_down`（此时把 interval 再加 5 秒）；用户拒绝是 `access_denied`；超时是 `expired_token`（回到第 1 步重来）。

完整 Python 轮询实现示例见官方文档 `docs.sentry.io/api/auth.md#device-authorization-flow`（本 skill 不重复贴大段代码，逻辑就是上面 4 步 + 标准指数退避）。

⚠ 文档原文，未实测。

## DSN Authentication（极少数 endpoint）

个别 endpoint 允许直接用 DSN 做鉴权（不是 Bearer token），文档原话是"generally very limited"，具体哪个 endpoint 支持要看该 endpoint 自己的说明，**默认假设某个 endpoint 不支持 DSN 鉴权**，除非它明确写了支持：

```bash
curl -H 'Authorization: DSN {DSN}' \
  https://sentry.io/api/0/{organization_slug}/{project_slug}/user-reports/
```

这是 DSN 唯一能碰到 Web API 的地方（提交用户反馈），**不要用它去做常规的查询/管理操作**——上面 SKILL.md 强调的"DSN 只写不读"依然成立，这个 user-reports endpoint 是官方明确列出的例外，不代表 DSN 普遍能用在 Web API 上。

## 遗留 API Key（不要用于新项目）

HTTP Basic Auth，用户名是 key，**密码留空但冒号 `:` 必须写**：

```bash
curl -u {API_KEY}: https://sentry.io/api/0/organizations/{organization_slug}/projects/
```

官方原话：**"API keys are a legacy means of authenticating... disabled for new accounts. You should use authentication tokens wherever possible."** 只在维护老账号时才会遇到，新代码不要用这个。
