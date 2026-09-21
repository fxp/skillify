---
name: slack
description: 接入 Slack API（api.slack.com / docs.slack.dev）为 AI agent 收发消息、读取频道历史、处理实时事件（Events API / Socket Mode）、响应 slash command 和交互组件（按钮、模态框）。涵盖 OAuth 授权与细粒度 scope 模型、chat.postMessage、Block Kit 富文本、conversations.history/list、mrkdwn 格式、限流分级（Tier 1-4）。当用户提到 "Slack API""slack_sdk""@slack/web-api""@slack/bolt""Bolt for Python/JavaScript""Slack bot""Slack 机器人""Slack 消息""Slack webhook""Slack OAuth scope""Slack Socket Mode""Slack slash command"，或要求写代码让 agent 给 Slack 发消息、读 Slack 频道历史、监听 Slack 事件、处理 Slack 按钮点击时，应主动使用本技能，不要凭记忆编造 scope 名称、endpoint 参数或误用其他 IM 平台（企业微信、飞书、钉钉）的接口习惯。
---

# Slack API 接入指南

Slack 是团队协作 IM 平台。面向开发者的能力入口是 **Web API**（超过 200 个 `https://slack.com/api/METHOD` RPC 风格方法）+ **Events API / Socket Mode**（接收实时事件）+ **Block Kit**（富文本/交互式 UI）+ **Bolt 框架**（JS/Python/Java，封装了上述全部内容并自动处理鉴权、重试、限流）。本 skill 面向"agent 要收发消息、读频道、处理事件与交互"这一常见场景。

内容整理自 `https://docs.slack.dev`（Slack 官方开发者文档站，2025 年从 `api.slack.com` 迁移过来；`api.slack.com` 现在主要承载应用管理控制台 `https://api.slack.com/apps` 和 Block Kit Builder 等工具页面，文档正文已转发到 `docs.slack.dev`），抓取于 2026-09。

## ⚠ 验证状态

**本 skill 尚未使用真实 Slack App / bot token 验证。** 所有结论来自官方文档原文转录，未经真实业务调用核实。全文所有具体行为断言（错误码、限流数字、字段是否默认返回等）都标注了 `⚠ 文档原文，未实测`。

**已做的极小一部分验证**：2026-09-21 做了 4 次**无凭证探测**（不需要 token，对 `https://slack.com/api/chat.postMessage`、`conversations.list`、一个不存在的方法名、`api.test` 分别发请求），证实了"错误信号在响应体的 `ok`/`error` 字段、HTTP 状态码始终是 200"这条核心断言（见 [references/errors-and-limits.md](references/errors-and-limits.md) 的验证记录）。除此之外**没有其他任何断言被真实调用验证过**——scope 模型、mrkdwn 渲染、限流数字、Events API/Socket Mode 行为、交互组件/slash command 的时序要求全部是文档转录。

拿到测试 workspace 的 App 和 bot token 后，请按 `../slack-workspace/verification-plan.md` 的清单逐条验证并把结果写回对应 reference 文件（格式："已用真实 API 验证（日期）：... 报错/响应原文"）。在验证完成前，把本 skill 的输出当作"高质量文档摘要"而不是"实测过的行为契约"。

## 用之前先确认 3 件事

1. **Base URL 固定为** `https://slack.com/api/<method>`（例如 `https://slack.com/api/chat.postMessage`）。不是 REST 风格，是 RPC 风格：每个方法一个固定路径，参数决定行为，HTTP method 因方法而异（读方法多为 GET，写方法多为 POST）。⚠ 文档原文，未实测
2. **鉴权精确格式**：`Authorization: Bearer xoxb-...`（bot token）或 `xoxp-...`（user token）。也可以把 token 作为 POST body 的 `token` 参数传（`application/x-www-form-urlencoded` 时），但**绝不能**放在 query string 里，`application/json` 请求也**只能**走 header。⚠ 文档原文，未实测
3. **最容易选错的字段：token 类型 + scope，而不是"有没有 token"**。Slack 的鉴权是细粒度 scope 模型——token 完全合法、完全有效，调用仍会因为**这个 token 没有这一条具体 scope** 而失败（`missing_scope`），这是新手最常踩的坑，见下方"跨领域通用规则"第一条。

## 30 秒跑通第一个请求

发一条消息到某个 channel（bot 必须已被邀请加入该 channel，否则报 `not_in_channel`）：

```bash
curl -X POST https://slack.com/api/chat.postMessage \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-type: application/json" \
  --data '{"channel":"C0123456789","text":"Hello from an agent"}'
```

```python
import os
from slack_sdk import WebClient

client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
resp = client.chat_postMessage(channel="C0123456789", text="Hello from an agent")
print(resp["ts"], resp["channel"])
```

响应 `{"ok": true, ...}` 才算成功——**HTTP 状态码几乎总是 200，就算调用失败也是 200**，见下方"跨领域通用规则"第二条。⚠ 文档原文，未实测

## 能力域导航

| 我想做什么 | 参考文件 | 涉及的核心 endpoint / 概念 |
|---|---|---|
| 创建 App、搞清楚 bot token vs user token、申请对的 scope、验证 Slack 发来的请求签名 | [references/auth-and-scopes.md](references/auth-and-scopes.md) | OAuth v2 授权流程、`oauth.v2.access`、scope 列表、签名验证 |
| 发消息、格式化文本（mrkdwn）、用 Block Kit 做富文本/按钮、线程回复 | [references/send-messages.md](references/send-messages.md) | `chat.postMessage`、`chat.postEphemeral`、`chat.update`、`chat.scheduleMessage`、Block Kit |
| 读频道历史、列出频道、判断频道类型（public/private/im/mpim）、翻页 | [references/read-messages-and-channels.md](references/read-messages-and-channels.md) | `conversations.history`、`conversations.list`、`conversations.info`、`conversations.replies`、`conversations.join` |
| 实时收事件（有人发消息/加表情/加入频道）、选 HTTP 还是 Socket Mode | [references/realtime-events.md](references/realtime-events.md) | Events API、Socket Mode、URL 验证握手、`apps.connections.open` |
| 做 slash command、按钮点击、模态框（modal）这类"用户主动触发"的交互 | [references/interactivity.md](references/interactivity.md) | slash commands、`block_actions`、`response_url`、`trigger_id`、modals |
| 排查 429/限流、理解 Tier 1-4、退避策略、常见错误码含义 | [references/errors-and-limits.md](references/errors-and-limits.md) | Rate limit tiers、`Retry-After`、`missing_scope` 等错误码 |

Slack 还有 Slack CLI + Deno Slack SDK 构建的"next-gen platform apps"（工作流触发器、托管在 Slack 侧的函数），本 skill **不覆盖**这条路线——它面向的是"Slack 自己托管你的代码"的场景，和本 skill 假设的"agent 从自己的进程调用 Slack API"是两个不同的架构选择，文档在 `https://docs.slack.dev/tools/deno-slack-sdk.md`。同样不覆盖 SCIM、Audit Logs、Enterprise Grid 管理类 API。

## 跨领域的通用规则（写代码前必读）

1. **`missing_scope` 是最容易踩的坑：token 有效 ≠ 有权限。** Slack 从"整包 bot 权限"演进到了细粒度 scope 模型——每个 Web API 方法在文档 Facts 区块里明确列出它需要哪个 bot scope / user scope（例如 `chat.postMessage` 需要 `chat:write`，`conversations.history` 需要 `channels:history`/`groups:history`/`im:history`/`mpim:history` 之一，具体取决于频道类型）。App 创建时申请的 scope 集合是**只增不减**的——一次装机拿到的 token 只有当时申请到的那些 scope，想要新 scope 必须让用户重新走一遍 OAuth 授权（新 scope 会追加到已有 token 上，不是替换）。**调用前先看该方法文档的 Scopes 表，别假设"能读消息就能读所有消息"**。⚠ 文档原文，未实测
2. **`ok: false` 才是失败信号，不是 HTTP 状态码。** 几乎所有 Web API 响应的 HTTP 状态码都是 200，真正的成功/失败信号是响应体里的顶层布尔字段 `ok`。失败时会带一个机器可读的 `error` 字符串（如 `"error": "channel_not_found"`）；即使 `ok: true`，也可能带一个 `warning` 字段说明"调用成功但有点问题"。**永远先检查 `ok`，不要用 HTTP status 判断成败**——这和其他一些平台（响应体里包一个业务状态码而不是用 HTTP 状态码）是同一类坑。真正的 429（限流）才会返回非 200 状态码，见规则 5。⚠ 文档原文，未实测
3. **Bot token 能做的事天然比 user token 少，尤其是"读任意频道历史"。** Bot token（`xoxb-`）代表 app 自己的身份，只能访问**它作为成员加入的频道**；哪怕拿到了 `channels:history` scope，如果 bot 没被邀请进某个 public channel，调 `conversations.history` 照样报 `not_in_channel`（一个例外：user token 可以读取它未加入的 public channel 的历史）。User token（`xoxp-`）代表某个真人用户，权限等同于该用户在 Slack 客户端里能看到的一切。**"发消息到任意 public 频道"需要额外的 `chat:write.public` scope**，默认 bot 只能发到自己所在的频道。写代码前先想清楚：这个操作该用哪种 token,以及 bot 是否已经在目标频道里。⚠ 文档原文，未实测
4. **消息格式是 `mrkdwn`，不是标准 Markdown。** Slack 自己的一套语法，和常见 Markdown 规则不同:`*bold*`（单星号加粗，不是 `**bold**`）、`_italic_`、`~strike~`、链接写 `<https://url|显示文字>`（不是 `[text](url)`）、`<#C0123|channel-name>` 链接频道、`<@U0123>` @ 用户。默认所有 `chat.postMessage` 等方法的 `text`/blocks 里的 `mrkdwn` 类型文本对象都走这套语法；用标准 Markdown 语法（如 `**bold**`、`[link](url)`）大概率不会报错但也不会正确渲染成粗体/链接。详见 [references/send-messages.md](references/send-messages.md)。⚠ 文档原文，未实测
5. **限流是"每个方法各自独立"的，不是全局配额，必须精确遵守 `Retry-After`。** Slack 把 Web API 方法分成 Tier 1-4（越高越宽松）外加少数方法有专属的 special 限流规则（如 `chat.postMessage` 大约每频道每秒 1 条消息）。**限流窗口是"per method per workspace per app"**——一个方法被限流完全不影响调用其他方法，也不影响对其他 workspace 的调用。收到 HTTP 429 时响应头会带 `Retry-After: <秒数>`，必须精确等待这么久再重试同一方法，而不是自己猜一个退避时间。`conversations.history`/`conversations.replies` 对"非 Marketplace 商业分发的 app"从 2025-05-29 起被降到 Tier 1（每分钟 1 次、每次最多 15 条），内部自用 app 和已上架 Marketplace 的 app 不受影响——如果 agent 是给内部工作区用的自用 app，通常不受此限制。详见 [references/errors-and-limits.md](references/errors-and-limits.md)。⚠ 文档原文，未实测
6. **实时事件走 Events API（HTTP）或 Socket Mode（WebSocket）二选一，不是都要**。本地开发 / 在防火墙后 / 不想暴露公网 endpoint 时用 Socket Mode（无需公网 URL，靠 `apps.connections.open` 拿一次性 WebSocket URL，一个 app 最多 10 个并发连接）；生产环境、要上架 Slack Marketplace 则**必须**用 HTTP request URL（Socket Mode 的 app 不允许上架 Marketplace）。两者收到的 payload 结构基本一致，Bolt 框架对两种模式都有内置支持，只需要环境变量层面切换。详见 [references/realtime-events.md](references/realtime-events.md)。⚠ 文档原文，未实测
7. **官方 SDK 包名**：Python 是 `slack_sdk`（pip 包名 `slack_sdk`，`from slack_sdk import WebClient`），Node 是 `@slack/web-api`（`WebClient`）+ `@slack/bolt`（框架，内置 Web API/Events API/Socket Mode/OAuth）+ `@slack/socket-mode` + `@slack/webhook`。Python 侧的框架是 `slack_bolt`（`pip install slack_bolt`）。Java 是 Bolt for Java / `com.slack.api`。**优先用 Bolt**（`slack_bolt` / `@slack/bolt`）而不是裸 SDK——Bolt 自动处理 token 校验、重试、限流退避、签名验证，裸 SDK（`slack_sdk.web.WebClient` / `@slack/web-api`）需要自己实现这些。⚠ 文档原文，未实测

## 目录结构

```
slack/
├── SKILL.md
├── references/
│   ├── auth-and-scopes.md          # OAuth、bot/user token、scope 模型、请求签名验证
│   ├── send-messages.md            # chat.postMessage 等、Block Kit、mrkdwn、线程
│   ├── read-messages-and-channels.md  # conversations.* 读操作、频道类型、翻页
│   ├── realtime-events.md          # Events API、Socket Mode、事件订阅
│   ├── interactivity.md            # slash command、按钮/菜单交互、modal
│   └── errors-and-limits.md        # Tier 1-4、常见错误码、退避策略
└── evals/
    └── evals.json                  # 对照实验场景（草稿，尚未跑）
```

内容整理自 `https://docs.slack.dev`（抓取于 2026-09），实际调用报错优先信任 API 本身而不是本 skill。
