# 实时事件：Events API（HTTP）vs Socket Mode

> ⚠ 本文件全篇未经真实 API 调用验证，所有行为断言标注为"文档原文，未实测"。

- [两种模式怎么选](#which-one)
- [HTTP 模式：Request URL](#http-mode)
- [Socket Mode](#socket-mode)
- [事件订阅与权限模型](#subscriptions)
- [常见事件类型](#common-events)

## 两种模式怎么选 {#which-one}

⚠ 文档原文，未实测。Slack 的 Events API 支持两种传输协议，接收到的事件 payload 结构基本一致，区别在"Slack 怎么把事件送到你手上"：

| 维度 | HTTP（Request URL） | Socket Mode（WebSocket） |
|---|---|---|
| 需要公网 endpoint | 是 | 否 |
| 能否上架 Slack Marketplace | 可以（**必须**用这个） | **不可以**——Socket Mode 的 app 目前不允许公开上架 |
| 推荐场景 | 生产环境、要分发给其他 workspace | 本地开发、在防火墙后运行、企业内部自用 app |
| 连接方式 | 每次事件一个短连接请求-响应 | 长连接，一个 app 最多 10 个并发连接 |
| 鉴权 | 靠请求签名验证（signing secret） | 靠 app-level token（`xapp-`），WebSocket 本身已预鉴权 |

官方建议：**能用 HTTP 就用 HTTP**（更少的活动部件、生产环境更可靠）；只有确实没法暴露公网 endpoint（企业防火墙、纯本地开发阶段）才用 Socket Mode。两者可以在 app 设置页随时切换，Bolt 框架对两者都有内置支持，只需要改初始化参数。

## HTTP 模式：Request URL {#http-mode}

⚠ 文档原文，未实测。

1. 在 App 设置页的 **Event Subscriptions** 打开开关，填入你的公网 HTTPS endpoint（Request URL）。
2. **首次保存时 Slack 会做一次性"URL 验证握手"**：POST 一个 `application/json` body 过来：
   ```json
   {"token": "...", "challenge": "3eZbrw1aBm2rZgRNFdxV2595E9CY3gmdALWMmHkvFXO7tYXAYM8P", "type": "url_verification"}
   ```
   你的 endpoint 必须原样把 `challenge` 值回传（HTTP 200 + 纯文本，或 `application/json` 里带 `{"challenge": "..."}` 都可以），才算验证通过。**这一步不需要签名验证**——`url_verification` 事件类型本身就是握手协议的一部分。
3. 之后所有真实事件都会 POST 到这个 URL，`Content-Type: application/json`，外层包一层 `event_callback` envelope：
   ```json
   {
     "type": "event_callback",
     "team_id": "T123ABC456",
     "api_app_id": "A123ABC456",
     "event": {"type": "app_mention", "user": "U123ABC456", "text": "...", "ts": "..."},
     "event_id": "Ev123ABC456",
     "event_time": 1234567890
   }
   ```
4. **收到真实事件后必须做签名验证**（见 [auth-and-scopes.md](auth-and-scopes.md) 的"验证 Slack 发来的请求签名"）——这一步和握手不同，是每次真实事件都要做的。
5. **必须在合理时间内（文档口径是几秒级）回 HTTP 200**，否则 Slack 会重试；把"耗时的业务逻辑"和"确认收到"解耦（先 200 再异步处理）是官方建议的模式。

## Socket Mode {#socket-mode}

⚠ 文档原文，未实测。设置分三步：

1. **创建/配置 app**，在 Socket Mode 设置页打开开关。
2. **生成 app-level token**（`xapp-` 前缀，需要 `connections:write` scope），在 Basic Information 页的 App-level tokens 区块生成。
3. 用这个 token 调 `apps.connections.open` 拿一次性 WebSocket URL：
   ```bash
   curl -X POST https://slack.com/api/apps.connections.open \
     -H "Authorization: Bearer $SLACK_APP_TOKEN"
   ```
   响应：`{"ok": true, "url": "wss://wss.slack.com/link/?ticket=..."}`

**用 Bolt 框架时这一切都自动处理**，只需要设置两个环境变量：

```python
# Python
import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

app = App(token=os.environ["SLACK_BOT_TOKEN"])
if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
```

```javascript
// Node
const { App } = require('@slack/bolt');
const app = new App({
  token: process.env.SLACK_BOT_TOKEN,
  appToken: process.env.SLACK_APP_TOKEN,
  socketMode: true,
});
(async () => { await app.start(); })();
```

**手写 WebSocket 客户端时要注意**：

- 连接建立后先收到一条 `{"type": "hello", ...}`。
- **每个事件都必须显式 ACK**（回传 `{"envelope_id": "<收到的envelope_id>"}`），否则 Slack 会判定未送达并重试——和 HTTP 模式不同，这里不需要验证签名（连接本身已鉴权），但**仍然需要主动确认收到**。
- 连接会定期刷新（数小时一次），收到 `{"type": "disconnect", "reason": "refresh_requested"}` 之类消息后要重新走一遍 `apps.connections.open` 建新连接；想做到不丢事件，建议维护多个并发连接（最多 10 个）做冗余。

## 事件订阅与权限模型 {#subscriptions}

⚠ 文档原文，未实测。

- 事件订阅复用 OAuth scope 体系：有 `files:read` scope 就可以选择订阅 `file_created`/`file_deleted` 等文件相关事件；bot 事件订阅只需要 bot 本身的 scope（一般是 `bot` 或具体 `*:read`），不需要额外申请。
- 你只会收到"授权用户能看到"的事件——例如只对私有频道有可见性的用户授权了你的 app，你也只能收到那些私有频道里的事件，不是整个 workspace 的所有私有频道。
- Workspace Events（跟随装机用户的授权范围）和 Bot Events（跟随 bot 自身身份）是分开配置的两个区块。

## 常见事件类型 {#common-events}

⚠ 文档原文，未实测；完整列表见 `https://docs.slack.dev/reference/events.md`。

| 事件 | 触发条件 | 需要的 scope |
|---|---|---|
| `app_mention` | 有人在 bot 所在频道 @ 了这个 app | `app_mentions:read` |
| `message.channels` / `message.groups` / `message.im` / `message.mpim` | 对应类型频道里有新消息 | 对应 `*:history` |
| `member_joined_channel` / `member_left_channel` | 成员加入/离开频道 | `channels:read` 等 |
| `app_rate_limited` | 该 workspace 的事件投递超过 30000 条/小时限额，本批事件被丢弃 | 无需订阅，自动收到 |
| `url_verification` | 配置 Request URL 时的一次性握手（不是真实业务事件） | 无 |

事件投递限额：**30,000 条/workspace/app/60 分钟**，超过会收到 `app_rate_limited` 通知型事件（说明限流开始时间），期间新事件会被丢弃而不是排队重试——高流量场景要考虑事件量预算。⚠ 文档原文，未实测
