# 鉴权与 Scope

> ⚠ 本文件全篇未经真实 API 调用验证，所有行为断言标注为"文档原文，未实测"。

- [Token 类型：bot / user / app-level / 其他](#token-types)
- [Scope 模型：为什么"有 token"不等于"有权限"](#scope-model)
- [OAuth v2 授权流程](#oauth-flow)
- [验证 Slack 发来的请求签名](#verifying-requests)
- [Token 存储与吊销](#token-lifecycle)

## Token 类型 {#token-types}

⚠ 文档原文，未实测。Slack 有多种 token，前缀不同、用途不同，**几乎所有面向 agent 的场景都用 bot token**：

| Token 类型 | 前缀 | 代表谁 | 典型用途 |
|---|---|---|---|
| **Bot token** | `xoxb-` | app 自己（不绑定具体人） | 绝大多数场景：发消息、读 bot 所在频道的历史、响应事件。装机用户离职也不影响 bot token 继续工作 |
| **User token** | `xoxp-` | 某个具体 Slack 用户 | 需要"以某个人的身份"操作时（如读取该用户能看到的所有 public 频道历史，包括 bot 未加入的频道）；权限等同于该用户本人在客户端里的权限 |
| **App-level token** | `xapp-` | app 本身，跨所有安装该 app 的组织 | 仅用于 Socket Mode 建立 WebSocket 连接（`apps.connections.open`）等"和具体 workspace 无关"的操作 |
| **Workflow token** | `xwfp-` | bot token 的一个子集，"即用即焚" | 15 分钟或一个 workflow 步骤完成后立刻失效；有"borrowed visibility"——可以临时借用触发该 workflow 的用户的频道可见性，无需 bot 本身加入频道 |
| Configuration token | 无固定前缀，在 App Manifest API 场景使用 | 具体用户+workspace | 仅用于创建/配置 app 本身（App Manifest API），不用于业务调用 |
| Legacy bot token | 旧式 | app | 只在维护老代码（如已废弃的 RTM API）时会遇到，新项目不要用 |

**新 App 默认走细粒度权限模型**（2019 年 12 月之后创建的 app 都是）。装机时请求哪些 scope，bot token 就只有那些 scope 对应的能力——不再有"一个 `bot` scope 包打天下"的旧模式。

## Scope 模型：为什么"有 token"不等于"有权限" {#scope-model}

⚠ 文档原文，未实测。这是整个鉴权体系里最容易被新手忽略、也是官方文档反复强调的一点：

- 每个 Web API 方法都在自己的文档页 "Facts" 区块里精确列出它需要的 **bot scope** 和 **user scope**（两者可能不同,例如 `chat.postMessage` 的 bot scope 和 user scope 都是 `chat:write`,但很多方法只对 bot 或只对 user 开放）。调用前一定要去对应方法的文档确认,不要凭经验猜。
- **Scope 只增不减**：第一次装机请求了 `channels:read`,第二次装机（同一个用户、同一个 workspace）又请求 `channels:write`,最终 token 会同时拥有两个 scope 的并集。**没有办法从已有 token 上移除某个 scope**,只能整个撤销重新授权。
- 每次 Web API 响应都会带一个 `x-oauth-scopes` 响应头，列出当前调用 token 实际拥有的全部 scope——调试 `missing_scope` 报错时先看这个 header 而不是去猜。
- 装机 URL 里，**bot scope 走 `scope=` 参数，user scope 走 `user_scope=` 参数**，两者不能混在一起传，且如果同时用了 Sign in with Slack (SIWS) 的 user scope 和非 SIWS 的 user scope 会直接报 `invalid_scope`。
- **Optional scopes**：App 可以把某些 scope 标记为可选（app settings 里取消勾选，或 manifest 里放进 `bot_optional`/`user_optional`），装机用户可以选择不授予。Agent 代码必须能优雅处理"这个可选 scope 没被授予"的情况（捕获对应的 `missing_scope` 错误,而不是假设一定成功）。

### 常见 scope 速查（面向 agent 的核心场景）

⚠ 文档原文，未实测；完整列表见 `https://docs.slack.dev/reference/scopes.md`。

| Scope | 授予的能力 |
|---|---|
| `chat:write` | 以 app 身份发消息（`chat.postMessage` 等） |
| `chat:write.public` | 发消息到 bot **未加入**的 public 频道（否则只能发到已加入的频道） |
| `chat:write.customize` | 发消息时自定义显示的 username/头像 |
| `channels:history` | 读 bot 已加入的 public 频道历史 |
| `groups:history` | 读 bot 已加入的 private 频道历史 |
| `im:history` | 读私信（DM）历史 |
| `mpim:history` | 读多人私信（group DM）历史 |
| `channels:read` / `groups:read` / `im:read` / `mpim:read` | 列出/查看对应类型频道的基本信息（`conversations.list`、`conversations.info`）——**不包含**消息内容,只是频道元数据 |
| `channels:join` | 主动加入 public 频道（`conversations.join`） |
| `commands` | 添加 slash command / shortcut |
| `connections:write` | 生成 WebSocket URL、连接 Socket Mode（`apps.connections.open`） |
| `users:read` | 查询工作区成员列表/信息 |
| `app_mentions:read` | 接收"有人 @ 了本 app"的事件 |

一个方法可能同时接受多个 `*:history` scope 之一（取决于目标频道类型），文档写法是"任一即可"，不是"全部都要"。

## OAuth v2 授权流程 {#oauth-flow}

⚠ 文档原文，未实测。Slack app 用标准 OAuth 2.0 三步流程安装到工作区：

1. **请求 scope**：把用户重定向到 `https://slack.com/oauth/v2/authorize?scope=<bot_scopes逗号分隔>&user_scope=<user_scopes逗号分隔>&client_id=<app的client_id>&redirect_uri=<你的回调地址>`。GovSlack 客户走 `https://slack-gov.com/oauth/v2/authorize`。
2. **等待用户同意**：什么都不用做，等 Slack 把用户重定向回 `redirect_uri`,并在 query string 里带上临时授权码 `code`（10 分钟内有效）和你之前传的 `state`（如果传了,要核对防伪造）。
3. **用授权码换 token**：调用 `oauth.v2.access`：

```bash
curl -F code=<从回调拿到的code> \
     -F client_id=<你的client_id> \
     -F client_secret=<你的client_secret> \
     https://slack.com/api/oauth.v2.access
```

成功响应形如（bot token 在顶层,user token 在 `authed_user` 里）：

```json
{
  "ok": true,
  "access_token": "xoxb-...",
  "token_type": "bot",
  "scope": "commands,incoming-webhook",
  "bot_user_id": "U0KRQLJ9H",
  "app_id": "A0KRD7HC3",
  "team": {"name": "Example Team", "id": "T9TK3CUKW"},
  "authed_user": {"id": "U1234", "scope": "chat:write", "access_token": "xoxp-1234", "token_type": "user"}
}
```

**还有一个专用于只拿 user token 的入口** `oauth.v2.user.access`，走 `https://slack.com/oauth/v2_user/authorize`——只需要 user token（不需要 bot token）、或要对接 MCP 客户端（如 Cursor、Claude Code）时用这条路径，遵循标准 OAuth 2.0 RFC。一般 agent 场景用 `oauth.v2.access` 就够了。

**Token 不会过期**（除非申请了 token rotation，见 `https://docs.slack.dev/authentication/using-token-rotation.md`）。需要吊销时调 `auth.revoke`。

## 验证 Slack 发来的请求签名 {#verifying-requests}

⚠ 文档原文，未实测。凡是 Slack 主动 POST 到你的 HTTP endpoint 的场景（Events API 的 HTTP 模式、slash command、交互组件 request URL）都必须验证签名，防止伪造请求：

1. 从 App 的 **Basic Information** 页拿 **Signing Secret**（环境变量 `SLACK_SIGNING_SECRET`，不要硬编码）。
2. 取请求头 `X-Slack-Request-Timestamp`,确认和本地时间相差不超过 5 分钟（防重放）。
3. 用原始请求体（**必须是反序列化之前的原始字节**，如 Flask 里用 `request.get_data()` 而不是先解析成 dict）拼出 basestring：`"v0:" + timestamp + ":" + raw_body`。
4. 用 signing secret 做 HMAC-SHA256，十六进制摘要前面加 `v0=` 前缀，得到期望签名。
5. 和请求头 `X-Slack-Signature`（**header 名大小写不敏感**）做**常量时间比较**（用 `hmac.compare_digest` 一类的函数，不要用 `==`）。

Socket Mode 下**不需要**做这一步——WebSocket 连接本身已经是预先鉴权的，只有走 HTTP 才需要验证签名。Bolt 框架（JS/Python/Java）内置了这套验证逻辑，只要设置 `SLACK_SIGNING_SECRET` 环境变量即可，不需要手写。

Events API 的 URL 验证握手（初次配置 request URL 时）用的是一次性 `challenge` 字段，不走签名验证，见 [realtime-events.md](realtime-events.md)。

## Token 存储与吊销 {#token-lifecycle}

⚠ 文档原文，未实测。

- **Token 只放环境变量**，绝不写进代码仓库或日志。
- Token 泄漏了：让用户 IP 白名单限制 + 调 `auth.revoke` 立即吊销。
- Bot token 被吊销后：bot 从工作区消失、其发出的 incoming webhook 失效；如果这个 app 在该工作区没有其他 user token 存活，看起来就像整个 app 被卸载了。
