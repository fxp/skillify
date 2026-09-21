# 发送消息

> ⚠ 本文件全篇未经真实 API 调用验证，所有行为断言标注为"文档原文，未实测"。

- [chat.postMessage：发消息的主入口](#post-message)
- [mrkdwn：Slack 自己的格式语法，不是标准 Markdown](#mrkdwn)
- [Block Kit：富文本与交互式布局](#block-kit)
- [线程回复（thread_ts）](#threading)
- [临时消息（ephemeral）](#ephemeral)
- [更新 / 删除 / 定时消息](#update-delete-schedule)
- [其他发消息方式](#other-methods)

## chat.postMessage：发消息的主入口 {#post-message}

**Endpoint**: `POST https://slack.com/api/chat.postMessage`
**Scope**: bot `chat:write`；发到 bot 未加入的 public 频道额外需要 `chat:write.public`
**Rate limit**: Special tier——大约每频道每秒 1 条消息，外加整个 workspace 级别的总量限制（每分钟几百条量级），允许一定程度突发。⚠ 文档原文，未实测

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `channel` | string | 是 | 频道 ID（`C...`/`G...`）或用户 ID（`U...`，会开一个 1:1 DM）。**不支持**传频道名字符串（已废弃），必须先用 `conversations.list` 查到 ID |
| `text` | string | 否* | 纯文本正文；用 `blocks` 时会被当作通知栏的 fallback 文案。*不用 `blocks`/`attachments` 时事实上必填，否则报 `no_text` |
| `blocks` | array | 否 | Block Kit 布局数组，见下 |
| `thread_ts` | string | 否 | 目标是另一条消息的 `ts`，把本条发成该消息的线程回复 |
| `reply_broadcast` | boolean | 否 | 配合 `thread_ts`，是否让线程回复同时出现在频道主视图（默认 `false`） |
| `mrkdwn` | boolean | 否 | 默认 `true`，传 `false` 关闭 mrkdwn 解析（纯文本展示） |
| `unfurl_links` / `unfurl_media` | boolean | 否 | 是否自动展开链接预览 |
| `metadata` | object | 否 | `{event_type, event_payload}`，写业务元数据，workspace 内所有人都能读到，不要塞敏感信息 |

**示例请求**

```bash
curl -X POST https://slack.com/api/chat.postMessage \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-type: application/json" \
  --data '{
    "channel": "C0123456789",
    "text": "Deployment finished",
    "blocks": [
      {"type": "section", "text": {"type": "mrkdwn", "text": "*Deployment finished* :white_check_mark:"}}
    ]
  }'
```

```python
resp = client.chat_postMessage(
    channel="C0123456789",
    text="Deployment finished",
    blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "*Deployment finished* :white_check_mark:"}}],
)
```

**示例响应**

```json
{
  "ok": true,
  "channel": "C0123456789",
  "ts": "1503435956.000247",
  "message": {"text": "Deployment finished", "type": "message", "ts": "1503435956.000247"}
}
```

保存返回的 `ts`——这是这条消息在该频道内的唯一时间戳标识，后续更新/删除/线程回复都要用它。

**注意事项**

- **`no_in_channel`/`not_in_channel`**：bot 必须先被邀请进目标频道（或有 `chat:write.public` 权限）才能发消息，否则报错。
- **发到 DM**：`channel` 传用户 ID（`U...`）会自动开一个 1:1 对话；bot **不能**用本方法直接插话进两个真人之间已存在的 DM，除非该 app 的 slash command/shortcut 是在那个 DM 里被触发的。
- `text` 上限建议 4000 字符（超过 40000 会被服务端截断），更长内容应该用文件/snippet 上传而不是硬塞进一条消息。
- `parse` 参数控制自动解析：默认（或 `none`）会解析 mrkdwn 语法，设成 `full` 会忽略 mrkdwn 格式化。
- 响应中的 `message` 对象是 Slack 服务端**清洗后**的版本（链接会被规范化等），可能和你传入的不完全一致。

## mrkdwn：Slack 自己的格式语法，不是标准 Markdown {#mrkdwn}

⚠ 文档原文，未实测。**这是最容易踩的坑之一**：Slack 的 `mrkdwn` 受 Markdown 启发,但语法规则不同，直接套标准 Markdown 语法大概率不报错、但也不会按预期渲染。

| 效果 | mrkdwn 语法 | 常见 Markdown 语法（**Slack 不认**） |
|---|---|---|
| 加粗 | `*bold*`（单星号） | `**bold**` |
| 斜体 | `_italic_` | `*italic*` |
| 删除线 | `~strike~` | `~~strike~~` |
| 行内代码 | `` `code` `` | 相同 |
| 代码块 | ``` ```code``` ``` | 相同 |
| 链接 | `<https://x.com\|显示文字>` | `[显示文字](https://x.com)` |
| 换行 | 字面 `\n` | 相同 |
| 引用 | 行首 `>` | 相同 |
| 列表 | 无原生语法，只能手写 `- ` / `• ` + `\n` 模拟 | `- item` 会原样显示成文本 |
| 提及用户 | `<@U0123ABCD>` | 无 |
| 提及频道 | `<#C0123ABCD>` 或 `<#C0123ABCD\|频道名>` | 无 |
| 提及用户组 | `<!subteam^S0123ABCD>` | 无 |
| 特殊提及 | `<!here>` / `<!channel>` / `<!everyone>` | 无 |
| 日期格式化 | `<!date^unix时间戳^{date_short}\|兜底文案>` | 无 |

需要转义的字符：`&` → `&amp;`，`<` → `&lt;`，`>` → `&gt;`（因为这三个字符在 mrkdwn 里是控制字符）。

**在哪些地方生效**：`chat.postMessage` 等方法的顶层 `text` 参数默认按 mrkdwn 解析（除非传 `mrkdwn: false`）；Block Kit 的文本对象要显式设 `"type": "mrkdwn"`（否则默认 `plain_text`，不解析任何格式）。有些 block/element 只接受 `plain_text`（比如按钮文字），文档会在对应 block 页面标出来。

**自动解析 vs 手动转义**：默认不带 `link_names` 参数时，纯 URL 仍会被自动转成链接，但 `@用户名`/`#频道名` 这种文本不会被自动转成提及（Slack 已废弃"用户名"这个概念，必须用 ID）。想让第三方文本原样显示、不被误解析成提及/链接，Block Kit 文本对象里设 `verbatim: true`。

## Block Kit：富文本与交互式布局 {#block-kit}

⚠ 文档原文，未实测。Block Kit 是 JSON 定义的 UI 组件系统，用在消息、模态框（modal）、App Home 里。核心概念：

- **block**：布局单元，如 `section`（正文+可选配图/按钮）、`header`（大标题）、`divider`（分割线）、`context`（小字辅助信息）、`actions`（一排交互控件）、`image`。每个 block 有 `type` 字段决定结构。
- **element**：block 内部的交互控件，如 `button`、`select` 下拉菜单、`datepicker`、`checkboxes`。
- **composition object**：跨 block 复用的小对象，最常见是 text object：`{"type": "mrkdwn"|"plain_text", "text": "..."}`。

**最小可用示例**（一条带按钮的消息）：

```json
{
  "channel": "C0123456789",
  "text": "New request from Alice",
  "blocks": [
    {"type": "section", "text": {"type": "mrkdwn", "text": "*New request* from <@U0123456>"}},
    {
      "type": "actions",
      "elements": [
        {"type": "button", "text": {"type": "plain_text", "text": "Approve"}, "style": "primary", "action_id": "approve_request", "value": "req_42"},
        {"type": "button", "text": {"type": "plain_text", "text": "Reject"}, "style": "danger", "action_id": "reject_request", "value": "req_42"}
      ]
    }
  ]
}
```

点击按钮之后 Slack 怎么通知你的 app、怎么响应，属于"交互组件"范畴，见 [interactivity.md](interactivity.md)。

**注意事项**

- `blocks` 存在时，顶层 `text` 变成通知栏（推送通知/屏幕阅读器）用的 fallback 文案；**强烈建议保留 `text`**，否则屏幕阅读器用户可能读不到内容（Slack 会尝试从 blocks 里拼一个，但不保证覆盖全部信息）。
- 没有专门的 OAuth scope 是"用 Block Kit 才需要"的——用了 blocks 不会比纯文本消息多要权限。
- 用 [Block Kit Builder](https://api.slack.com/tools/block-kit-builder)（可视化工具，在 `api.slack.com` 而不是 `docs.slack.dev`）拖拽预览布局，生成 JSON 后再往代码里搬，比对着文档手写更不容易出错。
- 各个 block/element 的精确字段表（哪些字段必填、字符数上限、哪些是 `plain_text` only）分散在 `https://docs.slack.dev/reference/block-kit/blocks/*.md` 和 `.../block-elements/*.md` 几十个页面里，本 skill 未逐一展开，常用的 `section`/`actions`/`header`/`context`/`divider`/`button` 结构已覆盖大多数 agent 场景，遇到不熟悉的 block 类型建议直接查对应 reference 页或用 Block Kit Builder 试错。

## 线程回复（thread_ts） {#threading}

⚠ 文档原文，未实测。

- 给 `chat.postMessage` 传 `thread_ts`（父消息的 `ts` 值）即可把新消息发成该消息的线程回复。**永远用父消息的 `ts`**，不要用某条回复的 `ts`（否则行为未定义，文档建议"用父消息的"）。
- 默认线程回复只在线程内可见，频道主视图看不到；想让回复同时出现在主频道，加 `reply_broadcast: true`（谨慎使用，会通知更多人）。
- 判断一条消息是否已经是线程的一部分：读消息历史时看是否带 `thread_ts` 字段（等于自己的 `ts` 说明它是父消息且已有回复；不等于自己说明它是某条回复）。

## 临时消息（ephemeral） {#ephemeral}

**Endpoint**: `POST https://slack.com/api/chat.postEphemeral`
**Scope**: bot `chat:write`

只对指定的某一个用户可见（`user` 参数），其他频道成员看不到；不刷新页面/换设备就会消失，且**无法**通过任何 API 再次读取（不出现在 `conversations.history` 里）。适合"响应用户操作后的即时反馈"，不适合当作持久化记录。也无法用 `chat.update`/`chat.delete` 修改——只能在响应交互 payload 的 `response_url` 场景里间接更新/撤回，见 [interactivity.md](interactivity.md)。⚠ 文档原文，未实测

## 更新 / 删除 / 定时消息 {#update-delete-schedule}

⚠ 文档原文，未实测。

| 方法 | 用途 |
|---|---|
| `chat.update` | 用 `channel` + `ts` 改一条已发消息的文本/blocks |
| `chat.delete` | 用 `channel` + `ts` 撤回一条消息（对被"冒充身份"发的消息无效，见 `chat.postMessage` 的 `chat:write.customize` 场景） |
| `chat.scheduleMessage` | 定时发送，传 `post_at`（未来的 Unix 时间戳） |
| `chat.deleteScheduledMessage` | 取消一条还没发出的定时消息 |
| `chat.getPermalink` | 给一条消息生成可分享的永久链接 |

## 其他发消息方式 {#other-methods}

⚠ 文档原文，未实测。除了 `chat.postMessage`，还有几种发消息的路径，各有适用场景：

- **Incoming Webhooks**：装机时生成一个专属某频道的固定 URL，POST JSON 过去就能发消息，不需要处理 token——适合"只往一个固定频道推送通知，不需要读消息/交互"的简单场景。
- **`response_url`**（来自 slash command / 交互 payload）：临时 webhook，专门用来响应某次用户交互，见 [interactivity.md](interactivity.md)。
- Real Time Messaging API（RTM，遗留）：不支持 blocks/attachments，官方不推荐新项目使用。
