# 错误处理与限流

> ⚠ 本文件全篇未经真实 API 调用验证，所有行为断言标注为"文档原文，未实测"。

- [响应体里的 ok/error，不是 HTTP 状态码](#ok-error)
- [限流分级：Tier 1-4 + Special](#rate-tiers)
- [如何正确退避（Retry-After）](#backoff)
- [conversations.history/replies 的 2025-05-29 新规](#history-rate-change)
- [常见错误码速查](#common-errors)

## 响应体里的 ok/error，不是 HTTP 状态码 {#ok-error}

⚠ 文档原文，未实测。Slack Web API 的所有响应都是 JSON，**HTTP 状态码几乎总是 200，无论调用成功还是业务失败**（真正的非 200 只出现在限流 429 和少数网关层错误）。判断成败必须看响应体：

```json
// 成功
{"ok": true, "channel": "C123", "ts": "1503435956.000247"}

// 失败——HTTP 状态码依然是 200
{"ok": false, "error": "channel_not_found"}

// 成功但带警告——ok 仍是 true
{"ok": true, "warning": "something_problematic", "stuff": "..."}
```

**已用真实 API 验证（无凭证探测，2026-09-21）**：对 `https://slack.com/api/chat.postMessage` 不带任何 token 发 POST，`https://slack.com/api/conversations.list` 带一个伪造的 `Authorization: Bearer xoxb-fake-token-123` 发 GET，`https://slack.com/api/not.a.real.method` 发一个根本不存在的方法名，三次调用的 HTTP 状态码**全部是 200**，响应体分别是：

```
{"ok":false,"error":"not_authed"}
{"ok":false,"error":"invalid_auth"}
{"ok":false,"error":"unknown_method","req_method":"not.a.real.method"}
```

`api.test`（无需鉴权的探活端点）不带任何参数调用则返回 `{"ok":true,"args":{}}`，HTTP 200。这确认了"错误信号在响应体的 `ok`/`error` 字段，不在 HTTP 状态码"这条核心断言在无鉴权场景下成立；需要真实 token 才能验证需要鉴权的方法（如 `missing_scope`、`not_in_channel`、429 限流）在同样"HTTP 200 + `ok:false`"模式下的具体错误码，见 `../../slack-workspace/verification-plan.md`。

代码里的正确模式：

```python
resp = client.chat_postMessage(channel=channel_id, text=text)
if not resp["ok"]:
    raise RuntimeError(f"Slack API error: {resp['error']}")
```

用官方 SDK（`slack_sdk`/`@slack/web-api`）时，非 `ok` 响应会被自动包装成异常抛出（`SlackApiError`），不需要手动检查 `ok` 字段；直接拼 HTTP 请求时必须自己检查。

## 限流分级：Tier 1-4 + Special {#rate-tiers}

⚠ 文档原文，未实测。每个 Web API 方法被指派一个限流档位，档位信息写在该方法文档页的 "Facts" 区块（"Rate Limits" 一行）。限流窗口口径是 **"每个方法 × 每个 workspace × 每个 app"**——不同方法互不影响，也不因为一个 workspace 被限流就影响其他 workspace。

| Tier | 大致限额 | 典型方法 |
|---|---|---|
| Tier 1 | 1+ 次/分钟 | 极少数低频管理类方法 |
| Tier 2 | 20+ 次/分钟 | `conversations.list` 等 |
| Tier 3 | 50+ 次/分钟 | `conversations.history`（内部自用/Marketplace app）、`conversations.replies` |
| Tier 4 | 100+ 次/分钟 | 高频只读方法 |
| Special | 各方法各自定义 | `chat.postMessage`（约 1 条/秒/频道 + workspace 总量上限）|

Slack **不公开精确的突发（burst）容量**，官方建议按"平均每秒不超过 1 次调用"设计节奏，短暂超过没关系，持续超过才会真正触发限流。

**翻页方法不带 `cursor`/`limit` 时限流更严格**——例如想一次性拉全量 `users.list` 又不分页，会比正常分页调用更容易被限流。

## 如何正确退避（Retry-After） {#backoff}

⚠ 文档原文，未实测。真正被限流时才会收到非 200 状态码：

```
HTTP/1.1 429 Too Many Requests
Retry-After: 30
```

**必须精确读取 `Retry-After` 头（单位：秒）并等待这么久之后再重试同一个方法**——不要自己发明指数退避的秒数，Slack 已经告诉你确切等多久。伪代码：

```python
import time
resp = client_raw_http_call(...)
if resp.status_code == 429:
    wait = int(resp.headers.get("Retry-After", "1"))
    time.sleep(wait)
    resp = client_raw_http_call(...)  # 重试同一个方法
```

用 `slack_sdk`/`@slack/web-api` 官方 SDK 时，很多场景下重试逻辑已经内置（尤其 Bolt 框架），可以不用手写这段，但**自建 HTTP 调用或用极简的第三方封装时必须自己处理**。

## conversations.history/replies 的 2025-05-29 新规 {#history-rate-change}

⚠ 文档原文，未实测，这是一条时效性较强的规则，验证时优先核实是否仍然生效：

- **谁受影响**：2025-05-29 之后新创建、且**未上架 Slack Marketplace 的商业分发 app**，以及这类既有 app 的**新安装**。
- **变化内容**：`conversations.history` 和 `conversations.replies` 的限流从 Tier 3 降到 **Tier 1（约 1 次/分钟）**，且 `limit` 参数的默认值和上限都降到 **15 条**。
- **谁不受影响**：内部客户自建 app（internal customer-built apps）保持 Tier 3、`limit` 上限 1000；已批准上架 Marketplace 的 app 不受影响；2025-05-29 之前就已存在的安装（老安装）也不受影响。
- **agent 场景的含义**：如果这个 Slack app 是给某个组织内部自己用的（不对外商业分发），大概率**不受此规则影响**，仍然是 Tier 3。如果是要打包卖给其他 workspace 的商业化产品，且没有走 Marketplace 上架流程，读频道历史会明显受限——这时候应该考虑走 Slack Marketplace 审核，或者转而依赖 Events API 被动接收消息而不是主动轮询 `conversations.history`。

## 常见错误码速查 {#common-errors}

⚠ 文档原文，未实测；以下按"多个方法通用"的错误码整理，具体到某个方法可能有专属错误码，见各方法文档的 Errors 表。

| 错误码 | 含义 | 常见原因 |
|---|---|---|
| `missing_scope` | token 没有这个方法要求的 scope | 忘了申请对应 scope，或用户没授予某个可选 scope |
| `not_authed` | 请求根本没带 token | header/body 都没传 token |
| `invalid_auth` | token 格式非法或被拒绝 | token 抄错、多余空格、来自被禁止的 IP |
| `token_expired` / `token_revoked` | token 已失效 | 被用户/管理员吊销，或 app 被卸载 |
| `channel_not_found` | `channel` 参数无效 | ID 打错、用了已废弃的频道名而不是 ID |
| `not_in_channel` | bot 不是该频道成员 | 需要先被邀请/调用 `conversations.join`（仅限 public） |
| `no_permission` | token 权限不够做这个操作 | 常见于试图操作 bot 未加入的频道 |
| `ratelimited` | 被限流 | 看 `Retry-After` 头 |
| `is_archived` | 目标频道已归档 | 归档频道不能发消息 |
| `restricted_action*` 系列 | 工作区管理策略禁止该操作 | 只读频道、线程被锁定等，管理员侧设置 |
| `invalid_blocks` / `invalid_blocks_format` | `blocks` JSON 不合法或不符合 Block Kit 语法 | 手写 JSON 时字段拼错、结构不对 |
| `trigger_expired` / `trigger_exchanged` | `trigger_id` 过期或已被用过 | 见 [interactivity.md](interactivity.md) |

**`missing_scope` 排障顺序建议**：先看该方法文档 Facts 区块要求哪个 scope → 看最近一次 API 响应的 `x-oauth-scopes` 头，确认当前 token 实际持有哪些 scope → 如果确实缺失，需要引导用户重新走一遍 OAuth 授权（追加新 scope，不能"补丁式"单独加）。
