把这份 skill 装进你的 Agent，让它写 Slack API 接入代码时不再凭记忆猜 scope 名称，也不会把 HTTP 状态码当成成功/失败信号——Slack 几乎永远返回 200，真正的信号在响应体的 `ok` 字段里。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill slack --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill slack --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/slack/slack.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认 3 件事」和「能力域导航」三节；
2. `references/` 下有 6 个 `.md`，其中 `send-messages.md` 讲的是 `chat.postMessage`、Block Kit 富文本、mrkdwn 格式；
3. 在 `references/errors-and-limits.md` 里能搜到「无凭证探测」字样，附带真实的 curl/请求描述和 `{"ok":false,"error":"not_authed"}` 这类真实响应片段。

## 这份 skill 覆盖什么

Slack（团队协作 IM 平台，开发者文档在 `docs.slack.dev`——2025 年从 `api.slack.com` 迁移过来，后者现在只承载应用管理控制台 `api.slack.com/apps` 和 Block Kit Builder 等工具页面）的开发者接入面：超过 200 个 `https://slack.com/api/METHOD` RPC 风格方法组成的 Web API、Events API / Socket Mode 实时事件、Block Kit 富文本/交互式 UI、Bolt 框架。覆盖 6 块：OAuth 授权与细粒度 scope 模型、发消息（`chat.postMessage` 等）与 mrkdwn/Block Kit 格式、读频道历史与分页、实时事件该选 HTTP 还是 Socket Mode、slash command/按钮/模态框这类交互组件、Tier 1-4 限流分级与错误码。

重点是两个反直觉陷阱：**`missing_scope` 不等于"没 token"**——Slack 是细粒度 scope 模型，token 完全合法有效，调用仍会因为这个 token 没申请到这一条具体 scope 而失败（例如 `chat.postMessage` 需要 `chat:write`），而且一次装机拿到的 scope 集合只增不减，想要新权限必须让用户重新走一遍 OAuth 才能追加；**`ok: false` 才是失败信号，不是 HTTP 状态码**——几乎所有 Web API 响应的 HTTP 状态码都是 200，就算调用失败也是 200，真正的成败要看响应体顶层的 `ok` 布尔字段，很容易被"HTTP 4xx/5xx 才算错"的直觉带偏。此外 bot token 只能访问自己被邀请加入的频道，发消息到任意 public 频道还需要额外的 `chat:write.public` scope。

内容不是文档搬运：skill 里记录了 `docs.slack.dev` 相对 `api.slack.com` 的这次文档站迁移，避免 Agent 按训练记忆里的旧域名找文档；另外做过 4 次**无凭证探测**——不带真实 token 分别对 `chat.postMessage`（无 Authorization）、`conversations.list`（伪造 token）、一个不存在的方法名、`api.test`（无需鉴权的探活端点）发请求，确认了"HTTP 状态码全部是 200，错误信号在响应体的 `ok`/`error` 字段"这条核心断言在无鉴权场景下成立。除此之外 scope 模型、mrkdwn 渲染细节、限流具体数字、Events API/Socket Mode 行为、交互组件的时序要求全部仍是文档转录，标了 ⚠ 未实测，留给拿到真实 bot token 的人补测。

## 版本

文档版，抓取于 2026-09-21，未用真实凭证验证。另做过 4 次无凭证探测（不带真实 token 分别对 `chat.postMessage`、`conversations.list`、一个不存在的方法名、`api.test` 发请求），确认了"HTTP 状态码几乎总是 200，真正的成功/失败信号在响应体的 `ok` 字段"这条断言；除此之外的 scope 模型、mrkdwn 渲染、限流数字、Events API/Socket Mode 行为、交互组件时序要求仍未经真实调用验证。**实际调用时以 API 的真实报错为准**，并去 `docs.slack.dev` 核实最新情况。
