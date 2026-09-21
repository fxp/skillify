# Linear for Agents（Agent Session / Activity）与官方 MCP Server

> 来源：`https://linear.app/developers/agents`、`agent-interaction`、`agent-best-practices`、`agent-signals`、`https://linear.app/docs/mcp`（抓取于 2026-09-21）。**这整块 API 官方标注为 Developer Preview / Technology Preview，功能和字段随时可能变**，比本 skill 其余部分更不稳定，写代码前建议先核对最新官方页面。行为性描述未实测，标 `⚠ 文档原文，未实测`。

## ⚠ Developer Preview 提醒

> Linear for Agents APIs are currently in active development and available as a **Developer Preview**. Functionality and Agent APIs may change before general availability.

`agentSession.plan`（Agent Plans）额外标注为 **Technology Preview**（比 Developer Preview 更早期）。如果你在构建长期维护的生产 Agent 集成，预期这部分字段和行为在未来可能有破坏性变更，不要把它当作和 Issue/Team 一样稳定的核心 API。

## 目录
1. [这是给"作为 Linear 工作区成员运作的 Agent"设计的，不是普通只读集成](#这是给作为-linear-工作区成员运作的-agent-设计的不是普通只读集成)
2. [接入：actor=app + 专属 scope](#接入actorapp--专属-scope)
3. [Agent Session 生命周期](#agent-session-生命周期)
4. [Agent Activity：五种类型](#agent-activity五种类型)
5. [Signals（人机双向元数据）](#signals人机双向元数据)
6. [Agent Plans](#agent-plans)
7. [其余 Agent 专属 Webhook](#其余-agent-专属-webhook)
8. [官方远程 MCP Server](#官方远程-mcp-server)

## 这是给"作为 Linear 工作区成员运作的 Agent"设计的，不是普通只读集成

Linear 区分两种第三方接入形态：

- **普通 Integration**：主要读数据，或代表某个具体人类成员执行写操作——用标准 OAuth（`actor=user`，见 `auth-and-endpoint.md`）即可。
- **Agent**：希望在 Linear 里表现为一个**独立的工作区成员**（有自己的身份、可以被 @提及、可以被指派、有自己的头像和状态）——需要 `actor=app` + Agent Session/Activity 体系（本文件的内容）。

判断依据（官方原话）：只读或行为应归属到具体人类身上，用 Integration；希望应用作为独立身份出现并主导行动，用 Agent。装进工作区的 Agent **不计入付费席位**，开发本身不收费；要分发给其他工作区，需要提交到 [Linear 集成目录](https://linear.app/docs/integration-directory#submit-your-integration)。官方提供了一个基于 TypeScript SDK + Cloudflare 的参考实现：[Weather Bot](https://github.com/linear/weather-bot)。

## 接入：actor=app + 专属 scope

Agent 鉴权建立在标准 OAuth2 之上（见 `auth-and-endpoint.md`），额外要求：

1. `/oauth/authorize` 加 `actor=app` 参数——工作区级安装，**需要 admin 权限完成安装**。
2. 按需申请 agent 专属 scope：`app:assignable`（允许被指派为 delegate）、`app:mentionable`（允许被 @提及）。**这两个 scope 默认不会自动获得**，不申请就无法被提及/指派，Agent 也就收不到会话。
3. `actor=app` 模式下**不能同时申请 `admin` scope**（互斥）。
4. Application 设置页里，**Webhooks → 勾选 "Agent session events"** 分类，才能收到下面描述的 `AgentSessionEvent` webhook。

**重要行为**：一旦订阅了 `AgentSessionEvent` webhook 分类，**该工作区所有用户立刻会看到 Agent Session 相关 UI**——即使你只是想先订阅调试，也会对真实用户产生界面变化,这不是一个"静默开发模式"。

App 在每个工作区里的 ID 各不相同,用装机后拿到的 access token 查一次 `viewer { id }` 拿到的就是"该应用在这个工作区的用户 ID",建议和 access token 一起存起来,后续识别"这是我自己的 App 账号"要用这个 ID 而不是假设它在所有工作区一致。

`Issue.delegate` 与 `Issue.assignee` 是两个不同字段——**指派给 Agent 的 issue 设置的是 `delegate`,不是 `assignee`**,这样可以保持人类作为 issue 的最终归属人(assignee),Agent 只是被委托执行。写查询/过滤条件时区分好这两个字段,`assignee` 查询条件不会匹配到"被委托给 Agent"的 issue。

## Agent Session 生命周期

**`AgentSession`** 追踪一次 Agent 任务的完整生命周期。当 Agent 被 @提及，或被指派（delegate）一个 issue 时，**Linear 自动创建**一个 `AgentSession`——不需要 Agent 自己调用创建它（除非是下面提到的"主动创建"场景）。

**6 种会话状态**（Linear 根据最后一次收到的 Activity 自动推导，**不需要手动管理状态**）：`pending`、`active`、`error`、`awaitingInput`、`complete`、`stale`。

**首次响应的硬性时限**：

- 收到 `created` 类型的 `AgentSessionEvent` webhook 后，**必须在 10 秒内**发出一个 `thought` 类型的 Activity（哪怕只是"收到了，正在处理"），否则该会话会被标记为**无响应（unresponsive）**。
- 首次响应之后,续发的 Activity 有 **30 分钟**的宽限期,超时会话进入 `stale` 状态——但这个状态**可恢复**,只要再发一条 Activity 就能激活。
- Webhook 接收端本身必须在 **5 秒**内返回响应（这是 HTTP 层的超时,和上面 10 秒的"业务层首个 Activity"是两个不同的计时器,不要混淆）。

**外部 URL**（把用户导向你自己的仪表盘）：用 `agentSessionUpdate` 的 `externalUrls`（对象数组，每个含 `label`+`url`，`url` 需数组内唯一；`addedExternalUrls`/`removedExternalUrls` 做增量更新而不是整体替换）设置后，Linear 会渲染一个"Open"按钮跳转出去，**设置 externalUrls 同样能防止会话被标记为无响应**（等价于发了一次 Activity）。旧字段 `externalLink` 已废弃但仍可用。

**主动创建会话**（没有被提及/指派，但 Agent 主动想在某个 issue/comment 下发起会话）：`agentSessionCreateOnIssue` / `agentSessionCreateOnComment` mutation。

**Session Webhook 的两种 action**：

| `action` | 说明 |
|---|---|
| `created` | 新会话创建（提及或指派触发）。应该开始新一轮 Agent 循环，用 `promptContext` 字段（预格式化好的上下文字符串，包含 issue 详情、评论历史、guidance）或结构化字段（`agentSession.issue`/`agentSession.comment`/`previousComments`/`guidance`）构造 prompt |
| `prompted` | 用户在已有会话里发了新消息（`agentActivity.body` 字段），追加进对话历史继续处理 |

`guidance` 指工作区/父团队/团队层级配置的指引（比如偏好的代码仓库、任务约束），随 `created` payload 一起带来。

## Agent Activity：五种类型

Agent 通过持续发出 `AgentActivity` 向用户汇报进度，**服务端会校验 shape，格式不对直接拒绝**：

```graphql
mutation AgentActivityCreate($input: AgentActivityCreateInput!) {
  agentActivityCreate(input: $input) {
    success
    agentActivity { id }
  }
}
```

```json
{ "input": { "agentSessionId": "...", "content": { "type": "thought", "body": "..." } } }
```

| 类型 | 用途 | 关键字段 |
|---|---|---|
| `thought` | 内部思考/说明 | `body`（Markdown） |
| `elicitation` | 向用户请求澄清/确认 | `body`；常配合 `signal: auth`/`select`（见下） |
| `action` | 描述一次工具调用，可分两阶段发（先不带 `result` 表示"开始"，完成后再发一次带 `result`） | `action`（动词短语）、`parameter`、`result`（可选，Markdown） |
| `response` | 工作完成/最终结果 | `body` |
| `error` | 报告失败 | `body` |

**`prompt` 类型是用户产生的，Agent 不能自己生成**——收到 `prompted` webhook 对应的正是一条 `prompt` 类型 Activity,是用户后续追问/回应 elicitation 时产生的,不要在自己代码里构造一条 `type: prompt` 的 Activity 发出去(会被拒绝)。

**⚠ 读会话历史不要依赖 Comment**：Comment 可编辑，读取时不保证是发送时的原始内容；要重建"当时到底发生了什么"必须遍历 `agentSession.activities`（时间冻结的快照），不是读 `issue.comments`：

```graphql
query AgentSession($agentSessionId: String!) {
  agentSession(id: $agentSessionId) {
    activities {
      edges {
        node {
          updatedAt
          content {
            ... on AgentActivityThoughtContent { body }
            ... on AgentActivityActionContent { action parameter result }
            ... on AgentActivityElicitationContent { body }
            ... on AgentActivityResponseContent { body }
            ... on AgentActivityErrorContent { body }
            ... on AgentActivityPromptContent { body }
          }
        }
      }
    }
  }
}
```

**Ephemeral Activity**：`thought`/`action` 类型可以额外标记 `ephemeral: true`，表示"临时展示状态"，UI 上会在下一条 Activity 到达时自动被替换掉（适合展示"正在搜索…"这类过渡态,不需要永久留痕）。`elicitation`/`response`/`error` 不支持标记为 ephemeral。

**仓库建议查询**：`issueRepositorySuggestions(issueId, agentSessionId, candidateRepositories)`——给一份"Agent 已有权限的候选仓库列表"，Linear 用 LLM 结合 issue 内容/会话上下文/内部信号（关联 issue、近期 PR）返回带置信度的排序建议，比自己写仓库匹配启发式更准；不确定时可以把候选仓库缩小成一份"select"型 elicitation 抛给用户确认（见下节 Signals）。

## Signals（人机双向元数据）

Signal 是挂在 Activity 上的额外元数据,指导接收方(人或 Agent)如何解读/处理这条 Activity。

**人 → Agent**（只出现在 `prompt` 类型 Activity 上）：

- **`stop`**：用户点击"Send stop request"后自动生成。Agent 收到后**必须立即停止一切后续动作**（代码修改、API 调用），并最终发出一条 `response` 或 `error` 类型 Activity 确认已停止、告知当前状态。

**Agent → 人**（Agent 发 Activity 时在 `signal` 字段附加，配合 `signalMetadata`）：

- **`auth`**（只用于 `elicitation`）：告诉用户需要先完成账号关联才能继续。Linear 渲染一个临时的"Link account"UI（新 Activity 到达后自动消失）。`signalMetadata`: `{ url, userId?（限定只对特定用户展示）, providerName?（标注是哪个服务的鉴权） }`。完成关联后 Agent 应发一条 `thought` 恢复工作。
- **`select`**（只用于 `elicitation`）：给用户一组选项（确认、目标选择如"选哪个 GitHub 仓库"等场景）。`signalMetadata.options`: `[{ label?, value }]`。**用户不是必须选选项**——自由文本回复同样会被记为普通 `prompt` Activity 并使该 elicitation 失效，所以处理 `prompted` webhook 时 Agent 必须能用 LLM 理解自由文本回复，不能假设回复内容一定是 `options` 里的某个 `value`。

```json
{
  "agentSessionId": "...",
  "content": { "type": "elicitation", "body": "Which package in the monorepo are you referring to?" },
  "signal": "select",
  "signalMetadata": { "options": [{ "label": "frontend", "value": "src/packages/frontend" }, { "label": "backend", "value": "src/packages/backend" }] }
}
```

## Agent Plans

> ⚠ Technology Preview，比整体 Developer Preview 状态更早期。

会话级别的任务清单，随执行过程演进。`agentSession.plan` 是一个数组，每项 `{ content: string, status: "pending" | "inProgress" | "completed" | "canceled" }`。

**⚠ 关键约束：更新 plan 必须整体替换，不能只改其中一项的状态**——每次调用都要把完整的 plan 数组重新传一遍:

```graphql
mutation AgentSessionUpdate($agentSessionId: String!, $data: AgentSessionUpdateInput!) {
  agentSessionUpdate(id: $agentSessionId, input: $data) { success }
}
```

```json
{ "data": { "plan": [
  { "content": "Update @linear/sdk to v61.0.0 and run npm install", "status": "inProgress" },
  { "content": "Implement agent plan mutations", "status": "pending" }
] } }
```

## 其余 Agent 专属 Webhook

除了 `AgentSessionEvent`，Agent 场景还有两类 webhook（同样在 App 的 Webhook 配置分类里勾选启用，在 `webhookCreate`/App Manifest 的 `resourceTypes` 里也能订阅同名类型）：

**Inbox Notifications**（`AppUserNotification`）——当有事情直接牵涉到 Agent 自己的用户身份时触发（被取消指派、有人对 Agent 的评论做表情回应等）：

```json
{ "type": "AppUserNotification", "action": "issueAssignedToYou", "createdAt": "...", "organizationId": "...", "oauthClientId": "...", "appUserId": "...", "notification": { } }
```

`action` 常见取值：`issueMention`、`issueEmojiReaction`、`issueCommentMention`、`issueCommentReaction`、`issueAssignedToYou`、`issueUnassignedFromYou`、`issueNewComment`、`issueStatusChanged`。

**Permission Change**（`PermissionChange`）——Agent 的团队访问权限被工作区 admin 改动时触发：

```json
{ "type": "PermissionChange", "action": "teamAccessChanged", "canAccessAllPublicTeams": false, "addedTeamIds": [], "removedTeamIds": ["..."], "webhookTimestamp": 0, "webhookId": "..." }
```

App 被撤权时额外单独收到一条：

```json
{ "type": "OAuthApp", "action": "revoked", "organizationId": "...", "oauthClientId": "...", "webhookTimestamp": 0, "webhookId": "..." }
```

## 官方远程 MCP Server

**⚠ 任务要求特别核对的部分**：Linear 官方发布并托管了一个远程 MCP Server，遵循 [MCP 规范](https://modelcontextprotocol.io/specification/2025-03-26)（2025-03-26 版本），**不需要自己实现 MCP server**——这是接 Linear 到任意支持 MCP 的 Agent/客户端（Claude、Cursor、VS Code、Windsurf、Zed 等）最省事的路径，前提是宿主允许接第三方远程 MCP。

**端点与传输**：

| 地址 | 用途 |
|---|---|
| `https://mcp.linear.app/mcp` | 主端点，**读写**权限，Streamable HTTP 传输 |
| `https://mcp.linear.app/mcp/readonly` | 只暴露只读工具的独立端点 |
| `https://mcp.linear.app/sse` | **已废弃**的 SSE 传输 fallback，只给不支持 Streamable HTTP 的老客户端用（如 WSL 环境部分客户端） |

**鉴权方式（二选一）**：

1. **交互式 OAuth 2.1 + 动态客户端注册**——大部分客户端（Claude、Cursor 等）走这条路，用户在浏览器里走一次标准授权流程。
2. **直接传 Bearer token**——`Authorization: Bearer <token>` header，**这里无论传的是 OAuth access token 还是个人 API Key，统一都要加 `Bearer` 前缀**。这一点和直连 `api.linear.app/graphql` 时"个人 API Key 不加 Bearer"的规则**不一致**（见 `auth-and-endpoint.md`），从直连 API 迁移到走 MCP Server 时容易漏加。

**只读访问的两种方式**：连 `/mcp/readonly` 端点；或连标准 `/mcp` 端点但只申请 `read` OAuth scope（该 token 天然无法触达写操作）；或者更简单——生成一个**只勾选 Read 权限的个人 API Key**，直接当 Bearer token 传给标准 `/mcp` 端点。

**能力**：官方原文"has tools available for finding, creating, and updating objects in Linear like issues, projects, and comments — with more functionality on the way"——工具集仍在扩展，具体工具列表建议连接后用 MCP 客户端自己的 `tools/list` 查（本 skill 未罗列具体工具名，⚠ 没有实测连接确认当前工具清单）。

**多工作区**：MCP Server 按 OAuth 会话鉴权，**一个已认证的会话不会因为"重新连接"就自动切换工作区**——每个工作区需要独立的鉴权上下文。用支持独立配置目录的客户端（如 `mcp-remote` 的 `MCP_REMOTE_CONFIG_DIR` 环境变量）给每个工作区分别指定不同目录，分别走一次登录。

**FAQ 里的运维要点**：
- 连接报内部服务器错误：先 `rm -rf ~/.mcp-auth` 清掉本地缓存的鉴权信息重连；也检查 Node.js 版本是否过旧。
- 连接偶尔掉线：客户端侧断开重连即可，不影响 Linear 侧的数据/鉴权状态。

**Claude Code 接入示例**：

```bash
claude mcp add --transport http linear-server https://mcp.linear.app/mcp
```

之后在会话里跑一次 `/mcp` 走认证流程。
