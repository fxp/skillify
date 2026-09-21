# Slack skill 验证计划

`slack/` skill 目前**完全没有用真实 Slack App / token 验证过**——第 1、2 步（抓取 + 撰写）已完成，第 3 步（真实调用验证）和第 4 步（对照实验）尚未进行。本文件是拿到测试 workspace 后的验证清单，按 create-doc-skill 第 3 步的优先级排序（低成本先测、四类最值得测的地方优先）。

## 需要准备

- 一个测试 Slack workspace（免费版即可覆盖大多数场景；部分权限相关行为可能需要付费/企业版才能测到边界）。
- 创建一个测试 App（`https://api.slack.com/apps` → Create New App），至少申请：`chat:write`、`chat:write.public`、`channels:read`、`channels:history`、`groups:read`、`groups:history`、`im:history`、`commands`、`connections:write`。
- Bot token（`xoxb-`）+ App-level token（`xapp-`，测 Socket Mode 用）。
- 至少一个 bot **已加入**的 public 频道 + 一个 bot **未加入**的 public 频道（专门用来测 `not_in_channel`）+ 一个 private 频道。
- 一个能收公网 HTTP 请求的 endpoint（测 Events API HTTP 模式 / slash command / 交互组件时需要，本地开发可以用 ngrok 类工具，或者只测 Socket Mode 跳过这部分）。

Key 只用环境变量传，不写入任何文件；验证结束后 `grep -rn` 全仓库确认没有残留。

## 已完成的验证（无需 token）

2026-09-21 做过 4 次**无凭证探测**（不需要真实 workspace/App，任何人都能重跑）：`chat.postMessage` 不带 token、`conversations.list` 带伪造 token、一个不存在的方法名、`api.test` 无鉴权探活——全部返回 **HTTP 200**，业务结果在响应体的 `ok`/`error` 字段里（`not_authed`/`invalid_auth`/`unknown_method`）。这条最基础的"错误信号在 body 不在状态码"的断言已经证实，记录见 `../slack/references/errors-and-limits.md`。下面 P0 的第 2 条已可视为完成，保留在清单里是为了在拿到真实 token 后补测"需要鉴权的方法"在同样模式下的具体错误码（`missing_scope`、`not_in_channel` 等）。

## 验证清单（按优先级）

### P0：SKILL.md 顶部"先确认的 3 件事" + 跨领域通用规则（错一个全盘皆错）

1. **鉴权格式**：确认 `Authorization: Bearer xoxb-...` 可用；确认 token 放 query string 会被拒绝（`auth-and-scopes.md` 声称"不能放 query string"）。
2. **`ok: false` + HTTP 200（需要鉴权的方法）**：已用无凭证探测证实了基础模式（见上），还需用真实 token 故意传一个错误的 `channel` 给 `chat.postMessage`，确认 `error` 字段具体取值（应为 `channel_not_found`）。
3. **`missing_scope`**：用一个只有 `channels:read`（没有 `chat:write`）的 token 调 `chat.postMessage`，确认报错码是 `missing_scope`，并记录 `x-oauth-scopes` 响应头实际内容。
4. **Bot token 读未加入频道历史**：对 bot **未加入**的 public 频道调 `conversations.history`，确认报 `not_in_channel`（`read-messages-and-channels.md` 的核心断言）。
5. **`chat:write.public` 的效果**：分别在有/没有这个 scope 时,对 bot 未加入的 public 频道调 `chat.postMessage`,对比行为差异。

### P1：mrkdwn 格式（send-messages.md 的核心断言）

6. 发一条 `text` 用标准 Markdown 语法（`**bold**`、`[link](url)`）的消息，确认它**不会**被解析成粗体/链接，原样显示星号和方括号。
7. 发一条用 mrkdwn 语法（`*bold*`、`<url|text>`）的消息，确认正确渲染。
8. 测试 `<#C0123|name>` 频道链接、`<@U0123>` 用户提及在 Block Kit `mrkdwn` 类型文本对象里的渲染效果。

### P1：限流与 Retry-After（errors-and-limits.md 的核心断言）

9. 短时间内对同一频道连续调用 `chat.postMessage` 制造突发，观察是否/何时触发 429，读取 `Retry-After` 头的实际取值范围。
10. **`conversations.history` 的 2025-05-29 新规**是本 skill 里最容易过期的一条结论——测试账号如果不是"未上架 Marketplace 的商业分发 app"，测不出这条规则本身，但至少要确认：当前测试 app 的 `conversations.history` 实际 `limit` 上限是多少（15 还是 1000），倒推自己属于哪一类。

### P2：Events API / Socket Mode

11. 配置一个测试 endpoint，走一遍 URL 验证握手，确认 `challenge` 字段回传的格式要求（纯文本 vs JSON 是否都真的可以）。
12. 用 Bolt（Python 或 JS）跑通 Socket Mode 最小示例，确认 `apps.connections.open` 返回的 WebSocket URL 可用、`hello` 消息结构。
13. 触发一次 `app_mention` 事件，比对实际 payload 结构和文档示例是否一致。

### P2：交互组件与 slash command

14. 创建一个测试 slash command，确认 3 秒 ACK 窗口的实际容错度（超时后用户看到的具体错误提示）。
15. 用一条带按钮的消息测试 `block_actions` payload，确认 `response_url` 的"5 次 / 30 分钟"额度是否准确，以及 `replace_original`/`delete_original`/线程回复组合的实际行为。
16. 测试 `trigger_id` 的 3 秒有效期和"只能用一次"的断言（`views.open` 成功一次后再用同一个 `trigger_id` 是否确实报 `trigger_exchanged`）。

### P3：分页与频道类型

17. `conversations.list` 混合 `im`/`mpim` 类型，确认"返回条数明显少于 limit"的现象是否真实存在。
18. Slack Connect 场景（如有条件）：确认 private 频道 ID 前缀从 `G` 变成 `C` 的说法。

## 验证结果写回位置

每条验证完成后，改写对应 reference 文件里的那条断言，格式固定为：

```
**已用真实 API 验证（YYYY-MM-DD）**：<做了什么> → <报错/响应原文片段>
```

发现文档本身写错的地方（比如某条断言和实测行为不一致），除了改 reference，还要同步升级到 `SKILL.md` 的"跨领域通用规则"一节，因为那一层是永远加载的。

## 第 4 步（对照实验）说明

本次未做对照实验。`evals/evals.json` 里的 5 个场景已经写好 prompt + expected_output + expectations，可以直接用来跑"有 skill / 无 skill"两版子 Agent 对照（见 create-doc-skill 第 4 步流程），不需要重新设计场景。建议验证完 P0/P1 清单后再跑对照实验，这样打分时能用真实报错去判定两版代码谁能在生产环境跑通，而不是"代码读起来像不像对"。
