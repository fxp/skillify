# linear skill 验证计划（待真实 API Key）

现状：文档版，抓取于 2026-09-21。产出方式是深度阅读官方文档全部 26 篇 `developers.linear.app` 页面 + 官方 MCP Server 文档 + 官方 GraphQL SDL 规范精读（52,378 行，逐类型提取 Issue/Team/Project/Cycle/WorkflowState/IssueLabel/Comment/Webhook/Mutation/Query 的精确字段定义），**没有发起过一次真实 API 调用**（没有 Key，也没有 OAuth App）。以下按优先级列出拿到 Key 后要测的结论，对应 `linear/SKILL.md`「跨领域通用规则」和各 reference 文件里的 `⚠` 标记（全部 reference 文件共 42 处）。

测试原则：Key 只走环境变量 `LINEAR_API_KEY`，测完立即从 shell 历史/临时文件清理；免费/试用工作区通常无需承担云资源费用（Linear 本身不是按调用计费的 SaaS），但**要在一个专门建的测试工作区或沙箱团队里跑写操作**，不要在真实生产工作区里创建/删除测试 issue、team、webhook；每条测试记录到 `verification-log.md`（日期、endpoint、请求要点、真实响应片段），写回对应 reference 文件时按「已用真实 API 验证（日期）：传 X 返回 `{...}`」格式标注证据，文档本身确认写错的地方要升级到 SKILL.md 的跨领域规则最前面。

## P0 —— SKILL.md 开头几件事 + 零成本只读，错了全盘皆错

| # | 结论 | 怎么测 | 判定 |
|---|---|---|---|
| 1 | 个人 API Key 走 `Authorization: <KEY>`（无 Bearer），传 `Bearer <KEY>` 会 401 | `POST /graphql`，`{query: "{ viewer { id } }"}`，先用无 Bearer 试通，再故意加 Bearer 前缀试一次 | 对比两次的 HTTP 状态码和响应体 |
| 2 | OAuth access token 走 `Authorization: Bearer <TOKEN>` | 走一次完整 OAuth 授权码流程拿 token，同样请求 `viewer` | 确认 200 + 正确返回 `viewer` |
| 3 | `issue(id: "ENG-123")` human-readable identifier 和 UUID 都能查到同一条记录 | 先用 UUID 查一次记录 `identifier`，再用该 `identifier` 字符串重新查一次 | 两次返回同一个 `id` |
| 4 | `team(id: "ENG")`（传 key 而不是 UUID）会失败 | 直接传团队 key 字符串当 `id` 参数 | 记录报错信息/是否返回 `null`/是否报 GraphQL 类型错误 |
| 5 | 默认分页 50 条，不传 `first` 静默截断 | 一个有 >50 issue 的团队跑 `team(id) { issues { nodes { id } } }` 不传分页参数 | 数返回条数是否恰好 50，`pageInfo.hasNextPage` 是否为 `true` |
| 6 | `orderBy: updatedAt` 真的按更新时间倒序 | 改一个旧 issue 的标题，紧接着查 `issues(orderBy: updatedAt, first: 5)` | 确认该 issue 出现在结果最前面 |
| 7 | 不传 `includeArchived` 时归档资源不出现在列表里 | 归档一个 issue，不传 `includeArchived` 查询该团队 issues 列表 | 确认该 issue 不在结果里；再传 `includeArchived: true` 确认能看到 |

## P1 —— 跨团队 ID 陷阱（本 skill 的核心卖点，优先测）

| # | ⚠ | 怎么测 | 判定 |
|---|---|---|---|
| 8 | 把团队 A 的 WorkflowState id 传给团队 B 的 issue 做 `stateId`：报错还是静默接受/失败 | 建两个测试团队 A/B，查 A 的一个 `started` 分类状态 id，用它对 B 团队下的一个 issue 调 `issueUpdate(stateId: ...)` | 记录返回的 `success`/`errors`，若成功需进一步确认 issue 实际状态是什么 |
| 9 | 把团队 A 的 Cycle id 传给团队 B 的 issue 做 `cycleId`：同上 | 同上模式，换成 `cycleId` | 同上 |
| 10 | `cycleCreate` 调用后的真实行为（deprecated 但字段仍在 schema 里） | 直接调用 `cycleCreate(input: {...})` | 记录是报错、返回 `success: false`，还是意外真的创建成功 |
| 11 | 工作区级 IssueLabel（`teamId` 不传）能被任意团队的 issue 使用 | 创建一个不传 `teamId` 的 Label，尝试挂到两个不同团队的 issue 上 | 确认两边都能成功挂上 |
| 12 | 团队私有 Label 挂到别的团队 issue 上：报错还是允许 | 创建一个带 `teamId: A` 的 Label，尝试挂到团队 B 的 issue 上 | 记录结果 |

## P2 —— 错误形状与限流（中高成本/需要触发边界条件）

| # | ⚠ | 怎么测 | 判定 |
|---|---|---|---|
| 13 | 校验错误（如非法枚举值）返回 200 + `errors` 而不是非 200 | `issueCreate` 传一个明显非法的字段值（如格式错误的 `dueDate`） | 记录 HTTP 状态码和 `errors[0]` 内容 |
| 14 | 限流错误的精确字段名：`extensions.code`（大写 `RATELIMITED`）还是 `extensions.type`（小写 `ratelimited`），还是两者都有 | 短时间内连续发大量请求触发限流（注意别在生产工作区/共享 Key 上做，可能影响同账号下其他集成） | 记录真实响应体的完整 `extensions` 对象 |
| 15 | 限流响应 HTTP 状态码确实是 400 而不是 429 | 同上 | 记录状态码 |
| 16 | 查询复杂度计算公式（0.1/property、1/object、connection × 分页数）是否与文档示例的复杂度数字吻合 | 跑文档给的两个示例查询（`user(id:"me"){name}` 和 `user(id:"me"){createdIssues{nodes{id title createdAt}}}`），读响应头 `X-Complexity` | 对比是否为文档所说的 2 和 66 |
| 17 | 单次查询超过复杂度 10,000 点是否直接拒绝 | 构造一个深层嵌套、大 `first` 的查询 | 记录状态码和错误信息 |
| 18 | API Key 和 OAuth App 的限流响应头数值是否与文档一致（2500/5000 请求，3M/2M 复杂度） | 分别用 API Key 和一个 OAuth App token 发请求，读 `X-RateLimit-*` 响应头 | 记录真实数值 |

## P3 —— Webhook（需要公网可达的接收端）

| # | 结论 | 怎么测 |
|---|---|---|
| 19 | `webhookCreate` 需要 admin 权限，非 admin Key 调用会怎样报错 | 用非 admin 权限的账号 Key 尝试创建 webhook |
| 20 | 签名验证代码（HMAC-SHA256，raw body）能否用真实 webhook 密钥验证通过一次真实投递 | 部署一个临时公网可达的 webhook consumer（如 `requestbin.com` 或临时 Cloudflare Worker），创建一个 issue 触发投递，核对 `Linear-Signature` 计算结果 |
| 21 | 投递失败重试的真实时间间隔（1 分钟/1 小时/6 小时）是否准确 | 让 webhook consumer 故意返回非 200，记录后续重试的真实时间戳 |
| 22 | 5 秒响应超时判定是否准确 | consumer 故意 sleep 6 秒再响应，看是否被判定为失败并重试 |

## P4 —— Agent API（Developer Preview，需要 OAuth App + actor=app，成本和复杂度最高）

| # | 结论 | 怎么测 |
|---|---|---|
| 23 | `actor=app` + `app:assignable`/`app:mentionable` scope 申请后，@提及/指派 该 App 确实会自动创建 `AgentSession` | 完整走一遍 OAuth App 创建 + 安装 + 在测试工作区 @提及该 App |
| 24 | 10 秒内未响应 `created` webhook 是否真的会被标记 unresponsive，以及 UI 上具体表现 | 故意让 webhook 处理端延迟 15 秒才发第一条 `thought` Activity |
| 25 | `agentActivityCreate` 对 5 种 content type 的 shape 校验有多严格（缺字段/多字段会怎样） | 分别用五种类型各发一次合法 payload，再各发一次故意缺字段的 payload |
| 26 | Agent Plan 必须整体替换（不能单项更新状态）这条限制的真实报错形式 | 尝试只传 plan 数组里的一项做"部分更新" |
| 27 | 指派给 App 的 issue，`delegate` 字段确实被设置而 `assignee` 不变/为空 | 把一个 issue 指派给已安装的 Agent App，查询该 issue 的 `delegate`/`assignee` |

## P5 —— MCP Server（独立于 GraphQL API 的验证路径）

| # | 结论 | 怎么测 |
|---|---|---|
| 28 | MCP Server 用个人 API Key 走 `Authorization: Bearer <API_KEY>`（注意这里有 Bearer，和直连 GraphQL API 不同） | `claude mcp add --transport http linear-mcp https://mcp.linear.app/mcp` 或直接用 `curl` 发一个 MCP `initialize` 请求带 Bearer header |
| 29 | `/mcp/readonly` 端点确实只暴露只读工具 | 连接后列出 `tools/list`，对比是否包含任何写操作工具 |
| 30 | 当前工具清单的真实工具名（官方文档未列出具体名字） | 连接后 `tools/list`，记录完整工具名和参数 schema |

## 完成后

- 每条结论改回对应 reference 文件，写「已用真实 API 验证（日期）：传 X 返回 `{...}`」格式，附真实响应片段。
- 22（错误字段名 code vs type 不一致）验证后，`errors-and-rate-limits.md` 和 `sdk-and-clients.md` 里的对应 ⚠ 条目要同步裁决更新。
- P1（跨团队 ID）如果验证坐实"静默失败/静默接受错误状态"这类高危行为，要把结论升级到 SKILL.md 跨领域规则最前面并加粗强调，这是本 skill 目前最重要但未经验证的核心卖点。
- SKILL.md 顶部「⚠ 验证状态」按「已验证（日期）/ 未验证」重写，不再是现在这种整体"文档版"的笼统说法。
- 验证完成后，按 `create-doc-skill` 方法论第 4 步补跑 with-skill / without-skill 对照实验，用 `evals/evals.json` 里的 5 个场景，写 `linear-workspace/comparison-report.md`（Markdown，参考本工作区 `CLAUDE.md` 的报告约定：表格 + Task/Why 段落，不生成 HTML/Artifact）。
