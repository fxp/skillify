# Slash Command 与交互组件（按钮 / 模态框）

> ⚠ 本文件全篇未经真实 API 调用验证，所有行为断言标注为"文档原文，未实测"。

- [Slash command](#slash-commands)
- [交互组件（按钮/菜单点击）](#interactive-components)
- [response_url：响应交互的临时 webhook](#response-url)
- [trigger_id 与模态框（modal）](#modals)
- [Socket Mode 下的交互 payload](#socket-mode-note)

## Slash command {#slash-commands}

⚠ 文档原文，未实测。用户在消息输入框里打 `/command 一些文字` 触发。设置需要 scope `commands`。

**配置**：App 设置页 → Slash Commands → Create New Command，填 Command 名字 + Request URL（同一个 app 的多个 command 可以共用一个 Request URL，靠 payload 里的 `command` 字段区分）。

**Slack 发来的 payload**（`Content-Type: application/x-www-form-urlencoded`）：

```
token=...&team_id=T0001&channel_id=C2147483705&channel_name=test&
user_id=U2147483697&command=/weather&text=94070&
response_url=https://hooks.slack.com/commands/.../...&
trigger_id=13345224609.738474920.8088930838d88f008e0
```

关键字段：`command`（触发的是哪个命令，一个 Request URL 服务多个命令时用它区分）、`text`（命令名之后的全部文字，原样透传，格式自己解析）、`response_url`（见下）、`trigger_id`（见下）、`user_id`/`channel_id`/`team_id`（上下文 ID，优先用 ID 不要用附带的可读名字段，名字可能变化）。

**响应要求**：

1. **必须在 3000 毫秒内回一个 HTTP 200**（哪怕是空响应），否则用户会看到 `operation_timeout` 错误。
2. HTTP 200 的 body 可以带内容——纯文本，或 `application/json` 的消息 payload（支持 blocks）。
3. **`response_type` 控制可见性**：默认 `ephemeral`（只有触发者能看到），传 `"response_type": "in_channel"` 会让响应和用户输入的原始命令一起公开显示在频道里。官方建议**显式声明** `response_type`，即便用默认值也写出来，避免歧义。
4. Slash command **不能在消息线程里触发**（split view/线程内没有这个入口），这是 Slack 客户端层面的限制，不是 API 限制。
5. Command 名字**没有命名空间**，多个 app 可能注册同名命令，Slack 会调用"最近安装的那个"——起名字要考虑唯一性。

## 交互组件（按钮/菜单点击） {#interactive-components}

⚠ 文档原文，未实测。用户点击消息里 Block Kit 的按钮/菜单/勾选框等触发。配置在 App 设置页 → Interactivity & Shortcuts → 打开开关 → 填 Request URL。

Payload 同样是 `application/x-www-form-urlencoded`，body 里有个 `payload` 参数，值是 JSON 字符串，需要自己 `JSON.parse`/`json.loads`。顶层 `type` 字段区分来源：

| `type` | 触发场景 |
|---|---|
| `block_actions` | 点击 Block Kit 里的按钮/select/checkbox 等 |
| `shortcut` / `message_actions` | 使用 global shortcut 或 message shortcut |
| `view_submission` | 提交了一个模态框 |
| `view_closed` | 取消/关闭了一个模态框（需要开启 `notify_on_close`） |

`block_actions` payload 示例关键字段：`actions[0].action_id`（你在 Block Kit 里定义的动作 ID，用来分发处理逻辑）、`actions[0].value`（你附带的业务数据，比如某个订单 ID）、`user`、`channel`、`message`（被点击按钮所在的原始消息）、`response_url`、`trigger_id`。

**响应要求同 slash command**：3 秒内 HTTP 200 ACK，之后可选地用 `response_url` 或 `trigger_id` 做后续动作。

## response_url：响应交互的临时 webhook {#response-url}

⚠ 文档原文，未实测。slash command / 交互 payload 里可能带一个 `response_url`（global shortcut **不会**带这个字段，因为它不发生在具体消息/频道上下文里）。这是一个一次性生成、指向特定交互的 webhook URL，特点：

- **5 次调用机会，30 分钟有效期**。超过这个额度/时限要改用正常的 `chat.postMessage` 等方法。
- POST 一个消息 payload（JSON）过去即可发消息，**绕过频道成员权限检查**（因为触发交互的这个动作本身已经证明了用户上下文有效）。
- 几种常见用法（都是往 `response_url` POST JSON）：
  - 普通响应：`{"text": "..."}`（默认 ephemeral）
  - 公开到频道：加 `"response_type": "in_channel"`
  - 更新原消息（比如点了按钮后把按钮消息替换成"已处理"）：`{"replace_original": "true", "text": "..."}`
  - 删除原消息：`{"delete_original": "true"}`（这是唯一允许出现在 body 里的字段）
  - 回线程：加 `"thread_ts": "<父消息ts>"`，**同时要显式设 `"replace_original": "false"`**，否则会覆盖掉你想回复的那条消息。
- Ephemeral 消息只能通过 `response_url` 更新/删除，普通消息也可以用 `chat.update`/`chat.delete` 代替。

## trigger_id 与模态框（modal） {#modals}

⚠ 文档原文，未实测。

- `trigger_id` 出现在交互 payload 里（slash command、按钮点击等），用来打开一个模态框（`views.open`）。
- **`trigger_id` 3 秒内失效，且只能用一次**（用过就废，第二次用会报 `trigger_exchanged`；过期用会报 `trigger_expired`）——拿到就立刻用，不要经过任何异步等待。
- 模态框提交（`view_submission`）或关闭（`view_closed`）事件也会 POST 到 Interactivity 的 Request URL，用 payload 的 `type` 字段区分。
- 模态框内部也可以配置生成一个新的 `response_url`（用于提交后异步响应），细节见 `https://docs.slack.dev/surfaces/modals.md`（本 skill 未展开这部分，多模态框/复杂表单场景建议直接查这个页面）。

## Socket Mode 下的交互 payload {#socket-mode-note}

⚠ 文档原文，未实测。开了 Socket Mode 之后，slash command / 交互组件 / Events API 的 payload **都**走 WebSocket 而不是各自的 Request URL，结构基本不变，只是外面多包一层：

```json
{"payload": {...原来HTTP模式下的payload...}, "envelope_id": "...", "type": "slash_commands", "accepts_response_payload": true}
```

响应方式也变了：不是 HTTP 200 + body，而是往 WebSocket 里发一条带 `envelope_id` 的 ACK（`accepts_response_payload: true` 时可以在 ACK 里带响应内容，等价于 HTTP 模式下 200 响应体里塞的东西）。用 Bolt 框架时这层差异被完全屏蔽，业务代码（`app.action(...)`, `app.command(...)` 等）不需要关心走的是 HTTP 还是 Socket Mode。
