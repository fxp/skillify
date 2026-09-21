---
name: linear
description: 接入 Linear 项目管理平台的 GraphQL API（developers.linear.app / api.linear.app/graphql）使用手册——涵盖鉴权（个人 API Key vs OAuth2 vs OAuth Actor Authorization vs Client Credentials）、Issue/Team/Project/Cycle/WorkflowState/IssueLabel/Comment 核心数据模型的查询与增删改、cursor 分页、过滤器、Webhook、官方 TypeScript SDK（@linear/sdk）、Linear for Agents（Agent Session/Activity/Signals，供 AI Agent 以工作区成员身份运作）与官方远程 MCP Server（mcp.linear.app）。当用户提到"Linear""linear.app""developers.linear.app""api.linear.app""@linear/sdk""LinearClient""issueCreate""Linear webhook""Linear MCP""Linear agent"，或要写代码通过 API 管理 Linear 的 issue/项目/团队时，应主动使用本技能——不要凭记忆编造字段名、假设存在 REST 端点，或照搬其他项目管理平台（Jira、Asana、GitHub Issues）的接口习惯。
---

# Linear GraphQL API 接入指南

Linear 是一个纯 GraphQL API 的项目管理平台：唯一 endpoint `https://api.linear.app/graphql`，**没有平行的 REST API**。本 skill 覆盖核心资源（Issue/Team/Project/Cycle/WorkflowState/IssueLabel/Comment）的查询与增删改、鉴权、分页/过滤、Webhook、官方 TypeScript SDK，以及 Linear 专门为 AI Agent 设计的 Agent Session/Activity 体系和官方远程 MCP Server。**本页只做路由与跨领域规则，字段表和代码示例在 `references/`。**

## ⚠ 验证状态

**文档版，抓取于 2026-09-21，未用真实 API Key 或 OAuth App 调用验证。** 内容来源：

- `https://linear.app/developers/*` 全部 26 篇开发者文档页（`developers.linear.app` 已 301 重定向到 `linear.app/developers`，用 `.md` 后缀抓取纯 Markdown 源）
- `https://linear.app/docs/mcp`（官方 MCP Server 文档）
- 官方 GraphQL SDL 规范 `https://raw.githubusercontent.com/linear/linear/master/packages/sdk/src/schema.graphql`（52,378 行，随 `@linear/sdk` 发布，**字段名/类型/是否必填这类结构性事实直接来自这份规范，精度高于人写教程**）
- `@linear/sdk` 源码 `error.ts`（SDK 错误类型映射）

**除了直接引自 SDL 的字段类型/必填标记外，几乎所有"会报错""默认返回 xxx""行为是……"这类描述都是文档原文转录，未实测**，每处已在正文标注 `⚠ 文档原文，未实测`（全部 reference 文件共 42 处）。拿到真实 API Key 后按 `linear-workspace/verification-plan.md` 补测，with-skill / without-skill 对照实验待验证完成后进行。

**Linear for Agents 相关 API（`references/agents-and-mcp.md`）官方自己标注为 Developer Preview / Technology Preview，比其余部分更不稳定**，字段和行为随时可能变，写生产代码前建议额外核对官方最新页面。

## 用之前先确认 4 件事

1. **只有一个 endpoint，没有 REST API**：`https://api.linear.app/graphql`（POST，JSON body）。如果训练直觉是先找 REST 路径表，这里不适用——所有"接口"都是这个 endpoint 上的一个具体 GraphQL query/mutation 名字，见导航表。
2. **两种鉴权方式，`Authorization` header 格式不同，不能混用**：个人 API Key 是 `Authorization: <API_KEY>`（**没有 `Bearer` 前缀**）；OAuth2 access token 是 `Authorization: Bearer <ACCESS_TOKEN>`（有前缀）。Linear 官方 MCP Server（`mcp.linear.app`）反过来——不管传 API Key 还是 OAuth token，统一都要加 `Bearer`。三个入口三套规则，照搬会 401。详见 `references/auth-and-endpoint.md`。
3. **Team/Project/Cycle/WorkflowState/IssueLabel 只能按 ID 查、按 ID 传，不接受名字**：`team(id: String!)` 这类查询和所有 mutation 的 `*Id` 输入字段都是如此，只知道团队 key（如 `"ENG"`）或标签名时要先用 `filter: { key/name: { eq: "..." } }` 查出 UUID。
4. **WorkflowState 和 Cycle 的 ID 是团队私有的，不能跨团队复用**（`WorkflowState.team: Team!`、`Cycle.team: Team!` 都是非空单值）；**IssueLabel 相反，可以是工作区级也可以是团队私有**（`IssueLabel.team: Team` 可空，`null` 即工作区级、任意团队可用）。这是最常见的跨团队自动化 bug 来源，详见 `references/teams-projects-cycles-states.md`。

## 30 秒跑通第一个请求

```bash
curl -X POST https://api.linear.app/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: $LINEAR_API_KEY" \
  --data '{"query": "{ viewer { id name email } }"}'
```

`LINEAR_API_KEY` 在 [Security & access 设置页](https://linear.app/settings/account/security) 生成，个人 Key **不加 Bearer 前缀**（见上条 #2）。

## 我要做什么 → 读哪一份

| 我要做什么 | 读 | 涉及的核心 query/mutation |
|---|---|---|
| 搞清楚鉴权（个人 Key / OAuth2 授权码 / Actor Authorization / Client Credentials）、限额差异、文件存储鉴权 | [`references/auth-and-endpoint.md`](references/auth-and-endpoint.md) | `/oauth/authorize`、`/oauth/token`、`/oauth/revoke` |
| 查询/创建/更新/删除 Issue，加评论，上传文件，管理标签，Issue 间关系 | [`references/issues-and-comments.md`](references/issues-and-comments.md) | `issue(s)`、`issueCreate`、`issueUpdate`、`issueDelete`/`issueArchive`、`issueAddLabel`/`issueRemoveLabel`、`commentCreate`、`fileUpload` |
| Team/Project/Cycle/WorkflowState/IssueLabel 本身的查询与增删改，按名字反查 ID | [`references/teams-projects-cycles-states.md`](references/teams-projects-cycles-states.md) | `team(s)`、`project(s)`、`cycle(s)`、`workflowState(s)`、`issueLabel(s)`、对应的 `*Create`/`*Update` mutation |
| 拿精确的 cursor 分页 shape（`after`/`first`/`pageInfo.hasNextPage`）、过滤器比较器语法（`eq`/`contains`/相对时间等） | [`references/pagination-and-filtering.md`](references/pagination-and-filtering.md) | 所有 `XxxConnection` 字段通用 |
| 配置数据变更 Webhook、验证签名、处理投递失败重试 | [`references/webhooks.md`](references/webhooks.md) | `webhookCreate`/`webhookDelete`/`webhooks` |
| 构建"作为工作区成员运作"的 AI Agent（被 @提及/指派、Agent Session、Agent Activity、Signals），或接 Linear 官方远程 MCP Server | [`references/agents-and-mcp.md`](references/agents-and-mcp.md) | `agentSessionUpdate`、`agentActivityCreate`、`agentSessionCreateOnIssue/Comment`、`https://mcp.linear.app/mcp` |
| TypeScript SDK 怎么用、Python 怎么调（没有官方 SDK）、SDK 错误类型、1.x→2.x 迁移 | [`references/sdk-and-clients.md`](references/sdk-and-clients.md) | `@linear/sdk` 对上述所有 mutation/query 的封装 |
| 错误响应形状、限流数值（API Key vs OAuth App 不同）、查询复杂度算法、deprecation 机制 | [`references/errors-and-rate-limits.md`](references/errors-and-rate-limits.md) | 所有请求通用 |

**本 skill 不覆盖**：Customer Requests（`Customer`/`CustomerNeed`，见官方 [Managing Customers](https://linear.app/developers/managing-customers)）、Agent Interaction Guidelines 设计哲学页（`aig.md`，无 API 内容，纯交互规范）、`linear.new` 免 API 预填链接（无需鉴权的纯 URL 参数功能）、Initiative/Document/Release/Template 等未在任务范围内的资源类型——这些资源在 schema 里同样存在（同样的查询/mutation/分页/过滤模式），需要时可以直接套用本 skill 讲清楚的通用模式（ID-only 查找、Relay 分页、Filter 比较器）自行核对 SDL。

## 跨领域的通用规则（写代码前必读）

1. **GraphQL 是唯一入口，没有 REST API**——除了 OAuth 的 `/oauth/token`、`/oauth/revoke`（表单编码）和文件上传的预签名 `PUT` URL，业务数据增删改查全部走 `POST https://api.linear.app/graphql`。反射性去找 REST 端点列表会扑空。
2. **两种主要错误响应形状，都要处理，别只认一种**：常规字段/校验错误是 **HTTP 200** + 顶层 `errors` 数组（GraphQL 标准的"部分成功"，必须显式检查 `errors`，不能只看状态码）；**触发限流是 HTTP 400** + `errors[].extensions.code == "RATELIMITED"`——限流场景应该退避重试,普通输入错误不该重试,判断逻辑不能只看 `errors` 数组不看状态码。详见 `references/errors-and-rate-limits.md`。
3. **WorkflowState ID / Cycle ID 是团队私有的**——把 A 团队的状态 ID 传给 B 团队的 issue 做 `stateId` 是最常见的跨团队自动化 bug。改 issue 状态前先用 `team(id: <issue所属团队ID>) { states(filter: {...}) { nodes { id name type } } }` 查出**目标团队自己的**状态 ID，不要用另一个团队查到的 ID，也不要跨团队缓存复用。`IssueLabel` 恰好相反——可以是工作区级（`team: null`）也可以是团队私有，别用同一套假设套两类资源。
4. **按 ID 查是硬性要求，按名字/key 查不通**——`team`/`project`/`cycle`/`workflowState`/`issueLabel` 这些单值查询和所有 mutation 的 `*Id` 输入字段都只接受 UUID。只有名字/key 时，第一步永远是先用 `filter: { name/key: { eq: "..." } }` 的列表查询换出 ID，这一步不能省略，也不要假设 API 会做名字模糊匹配。
5. **鉴权 header 格式因入口而不同**：个人 API Key 直连 GraphQL 主端点 = 裸 key（无 `Bearer`）；OAuth token 直连 = `Bearer` 前缀；官方 MCP Server（`mcp.linear.app`）不管哪种 key 类型统一都要 `Bearer` 前缀。三选一，别凭一套习惯套所有入口。
6. **`issueDelete` 默认是软删除（trash），不是立即物理删除**——30 天宽限期内可恢复，只有管理员传 `permanentlyDelete: true` 才会跳过宽限期硬删。`issueArchive`（归档）和 `issueDelete`（trash）是两种不同语义，都不等于"永久清除"。
7. **`cycleCreate` 已废弃且不可用**（`@deprecated(reason: "Cycle creation is not supported.")`）——Cycle 只能通过 Team 的 `cyclesEnabled`/`cycleDuration`/`cycleStartDay` 等设置驱动自动生成，程序化只能改（`cycleUpdate`）、归档（`cycleArchive`）、整体平移（`cycleShiftAll`）或让下一个周期提前开始（`cycleStartUpcomingCycleToday`），**没有"创建一个新 Cycle"的可用 API**。
8. **限流限额因鉴权方式而不同，且请求数与复杂度两个维度不是同向变化**：API Key 请求数配额 2,500/小时低于 OAuth App 的 5,000/小时，但 API Key 的复杂度配额 3,000,000/小时反而**高于** OAuth App 的 2,000,000/小时——不能假设"换 OAuth 全面更宽松"。单次查询复杂度硬上限 10,000 点，与鉴权方式无关。详见 `references/errors-and-rate-limits.md`。
9. **分页统一是 Relay cursor 模型**：`after`/`before`/`first`/`last` + `pageInfo { hasNextPage hasPreviousPage startCursor endCursor }`，**默认页大小 50**，不传分页参数的查询会静默截断，不会报错也不提示，必须检查 `pageInfo.hasNextPage` 才能确认是否拿全了数据。`orderBy` 只有 `createdAt`（默认）/`updatedAt` 两个取值。详见 `references/pagination-and-filtering.md`。
10. **Linear for Agents 是 Developer Preview**，要让代码里的 Agent 以独立工作区成员身份运作（被 @提及、被指派、有自己的活动流），需要 `actor=app` OAuth 模式 + `app:assignable`/`app:mentionable` scope + 订阅 `AgentSessionEvent` webhook；被指派给 Agent 的 issue 设置的是 `delegate` 字段，**不是** `assignee`。首次响应有 **10 秒**硬性时限。详见 `references/agents-and-mcp.md`。
11. **Linear 有官方托管的远程 MCP Server**（`https://mcp.linear.app/mcp`，读写；`/mcp/readonly` 只读），遵循标准 MCP 规范，多数场景不需要自己实现 MCP server——但它的 Bearer 鉴权规则和直连 GraphQL API 不同（见规则 #5），且一个 OAuth 会话不会自动跨工作区切换。
12. **没有官方 Python SDK**，Python（或其他语言）调用统一手写 GraphQL 请求 POST 到主 endpoint，字段名和本 skill 给出的 GraphQL 示例完全一致；TypeScript 项目优先用官方 `@linear/sdk`（2.x 起 mutation 方法名是"动词在前"，如 `createIssue` 而不是 GraphQL 层的 `issueCreate`）。

## 目录结构

```
linear/
├── SKILL.md                          # 本文件：路由 + 跨领域通用规则
├── references/
│   ├── auth-and-endpoint.md          # 鉴权全流程（API Key/OAuth2/Actor Auth/Client Credentials）、endpoint、文件存储鉴权
│   ├── issues-and-comments.md        # Issue 查询/创建/更新/删除、评论、文件上传、标签增删、Issue 关系
│   ├── teams-projects-cycles-states.md  # Team/Project/Cycle/WorkflowState/IssueLabel 的查询与增删改
│   ├── pagination-and-filtering.md   # Relay cursor 分页精确 shape、过滤器比较器、相对时间
│   ├── webhooks.md                   # 数据变更 Webhook：创建、投递重试、payload 形状、签名验证
│   ├── agents-and-mcp.md             # Linear for Agents（Agent Session/Activity/Signals/Plans）+ 官方远程 MCP Server
│   ├── sdk-and-clients.md            # 官方 TypeScript SDK 用法、无官方 Python SDK 时怎么办、错误处理
│   └── errors-and-rate-limits.md     # 错误响应形状、限流数值、查询复杂度算法、deprecation 机制
└── evals/
    └── evals.json                    # 对照实验场景（打包时自动排除）
```

内容整理自 `https://linear.app/developers/*`（26 篇文档页）、`https://linear.app/docs/mcp`、官方 GraphQL SDL 规范（抓取于 2026-09-21）。**实际调用报错、返回字段、默认值一律优先信任 API 的真实响应**；本 skill 尚未做真实调用验证，验证优先级和方法见 `linear-workspace/verification-plan.md`。
