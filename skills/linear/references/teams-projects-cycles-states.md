# Teams / Projects / Cycles / Workflow States / Labels

> 字段来自官方 GraphQL SDL，行为性描述（默认值、报错与否）未用真实 Key 验证，标 `⚠ 文档原文，未实测`。

## 目录
1. [核心原则：按 ID 查，不按名字查](#核心原则按-id-查不按名字查)
2. [Team](#team)
3. [Project 与 ProjectMilestone](#project-与-projectmilestone)
4. [Cycle（不能通过 API 创建）](#cycle不能通过-api-创建)
5. [WorkflowState（团队私有，状态 ID 不能跨团队）](#workflowstate团队私有状态-id-不能跨团队)
6. [IssueLabel（可以是团队私有，也可以是工作区级）](#issuelabel可以是团队私有也可以是工作区级)

## 核心原则：按 ID 查，不按名字查

Team / Project / Cycle / WorkflowState / IssueLabel / Webhook 的单个查询和所有 mutation 的 `*Id` 参数，**清一色只接受 UUID，不接受名字或 key**：

```graphql
team(id: String!): Team!
project(id: String!): Project!
cycle(id: String!): Cycle!
workflowState(id: String!): WorkflowState!
issueLabel(id: String!): IssueLabel!
```

如果只知道团队 key（如 `"ENG"`）、项目名、标签名，**必须先用带 `filter` 的列表 query 查出 ID**，这是写 Linear 自动化最常见的第一步，几乎每个"给我建一个 xxx 相关的 issue"任务都要先做这一步：

```graphql
# 按团队 key 查 ID
query { teams(filter: { key: { eq: "ENG" } }) { nodes { id key name } } }

# 按项目名查 ID（模糊匹配用 contains）
query { projects(filter: { name: { contains: "Checkout" } }) { nodes { id name } } }

# 按标签名查 ID（注意标签可能同名但分属不同团队，见下）
query { issueLabels(filter: { name: { eq: "Bug" } }) { nodes { id name team { id key } } } }
```

## Team

**核心查询**：`team(id)` / `teams(after, before, filter: TeamFilter, first, includeArchived, last, orderBy)`

```graphql
query Teams {
  teams { nodes { id key name } }
}

query TeamDetail($id: String!) {
  team(id: $id) {
    id key name
    states { nodes { id name type position } }
    labels { nodes { id name } }
    cycles(first: 5, orderBy: updatedAt) { nodes { id number startsAt endsAt } }
    activeCycle { id number }
  }
}
```

**关键 mutation**：`teamCreate(input: TeamCreateInput!)`、`teamUpdate(id, input: TeamUpdateInput!)`、`teamDelete(id)`。`TeamCreateInput.name` 是唯一必填字段；`key` 不传会根据 `name` 自动生成（比如 "Engineering" → `ENG`）；`cyclesEnabled`/`cycleDuration`/`cycleStartDay`/`cycleCooldownTime` 这些字段控制该团队 Cycle 的**自动生成**规则（见下节，Cycle 本身不能手动创建，只能通过这些团队设置驱动）。

**注意事项**：
- `Team.key` 就是 issue identifier 的前缀（如 `ENG-123` 里的 `ENG`），创建后可以改（`teamUpdate` 里传新 `key`），但已存在的 issue identifier 不会重新编号。
- `issues(includeSubTeams: Boolean = false)` 这个字段参数默认 `false`——查团队 issue 列表时子团队的 issue **默认不包含在内**，需要显式传 `true`。`projects(includeSubTeams: Boolean = false)` 同理。
- `private: Boolean` 已标记 `@deprecated`，改用 `visibility: TeamVisibility!` 字段判断团队可见性。

## Project 与 ProjectMilestone

**核心查询**：`project(id)` / `projects(after, before, filter: ProjectFilter, first, includeArchived, last, orderBy, sort)`

```graphql
query ProjectDetail($id: String!) {
  project(id: $id) {
    id name description
    state status { id name type }
    lead { id name }
    teams { nodes { id key } }
    issues(first: 20) { nodes { id identifier title } }
    projectMilestones { nodes { id name targetDate sortOrder } }
  }
}
```

**关键参数**（`ProjectCreateInput`）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | `String!` | 是 | 唯一强制字段 |
| `teamIds` | `[String!]!` | **是**（数组本身必填，但可以是空数组，⚠ 未实测确认空数组的真实行为） | 项目可以跨多个团队共享，注意这里是复数 `teamIds` 数组，不是单个 `teamId`——和 `IssueCreateInput`/`WorkflowStateCreateInput` 的单数 `teamId` 不一致，混淆是常见笔误来源 |
| `leadId` | `String` | 否 | 项目负责人 UUID |
| `statusId` | `String` | 否 | 项目状态（`ProjectStatus`，工作区级配置，不是 `WorkflowState`，两者是完全不同的类型，不要混用） |
| `startDate` / `targetDate` | `TimelessDate` | 否 | `"YYYY-MM-DD"` |
| `labelIds` | `[String!]` | 否 | `ProjectLabel`，和 issue 用的 `IssueLabel` 是不同的类型体系，两套标签互不通用 |

```graphql
mutation ProjectCreate($input: ProjectCreateInput!) {
  projectCreate(input: $input) { success project { id name } }
}
```

```json
{ "input": { "name": "Q3 Checkout Revamp", "teamIds": ["9cfb482a-81e3-4154-b5b9-2c805e70a02d"] } }
```

`projectUpdate(id, input: ProjectUpdateInput!)`、`projectDelete(id)`（软删除，替代已废弃的 `projectArchive`）、`projectUnarchive(id)`。

**ProjectMilestone**（项目里的阶段性节点，不是独立的顶级资源，总挂在某个 Project 下）：`projectMilestoneCreate(input: ProjectMilestoneCreateInput!)` 需要 `projectId` + `name`，`projectMilestoneUpdate`/`projectMilestoneDelete`/`projectMilestoneMove`（调整顺序）。issue 通过 `IssueCreateInput.projectMilestoneId` 关联到具体里程碑。

**注意事项**：
- `Project.status`（`ProjectStatus!`，工作区级共享的项目状态定义，如 Planned/In Progress/Completed）和 `Project.state`（`ProjectStatusType` 枚举字符串，粗粒度分类）是两个不同粒度的字段，别和 issue 的 `WorkflowState` 弄混——三层命名（`Project.status` / `Project.state` / `Issue.state`）容易读错。
- `ProjectUpdateInput` 有 `trashed: Boolean`，效果类似软删除的另一条路径，和 `projectDelete` 有功能重叠，选一个统一用即可。

## Cycle（不能通过 API 创建）

**⚠ 最容易踩的坑**：`cycleCreate` mutation 在 schema 里标了 `@deprecated(reason: "Cycle creation is not supported.")`——**没有可用的"创建 Cycle" API**。Cycle 由 Linear 根据 `Team` 上的 `cyclesEnabled` / `cycleDuration`（周数）/ `cycleStartDay`（星期几开始）/ `cycleCooldownTime` 等设置**自动滚动生成**，唯一能程序化影响 Cycle 的方式是：

1. 通过 `teamUpdate` 修改上述团队级 Cycle 设置（间接影响未来自动生成的 Cycle）；
2. 对已存在的 Cycle 用 `cycleUpdate(id, input: CycleUpdateInput!)` 改名字/日期/描述；
3. `cycleArchive(id)` 归档；
4. `cycleShiftAll(id, input)` 整体平移某团队从该 Cycle 起的所有未来 Cycle 日期；
5. `cycleStartUpcomingCycleToday(teamId)` 让下一个即将到来的 Cycle 提前从今天开始。

**核心查询**：`cycle(id: String!)` / `cycles(filter: CycleFilter, ...)`，或从 `team(id) { cycles {...}, activeCycle {...} }` 挂载查询。

```graphql
query ActiveCycle($teamId: String!) {
  team(id: $teamId) {
    activeCycle { id number startsAt endsAt progress }
  }
}
```

**注意事项**：`Cycle.team: Team!` 是非空单值——**Cycle 严格属于一个团队，`cycleId` 不能跨团队复用**，和 WorkflowState 的团队私有性质完全一致（见下节）。`isActive`/`isFuture`/`isNext`/`isPast`/`isPrevious` 这几个布尔字段可以直接查，不需要自己用日期比较 `startsAt`/`endsAt` 来判断当前 Cycle 处于什么阶段。

## WorkflowState（团队私有，状态 ID 不能跨团队）

**⚠ 最重要的跨团队自动化陷阱**：`WorkflowState` 类型有非空的 `team: Team!` 字段——**每个团队维护自己独立的一套工作流状态**，即使两个团队都有一个名叫 "In Progress" 的状态，它们的 `id` 完全不同、不可互换。把 A 团队的 state ID 传给 B 团队的 issue 做 `stateId`，⚠ 文档未明确报错还是静默失败，**必须先查目标 issue 所属团队自己的状态列表再传 ID**：

```graphql
query TeamStates($teamId: String!) {
  team(id: $teamId) {
    states(filter: { type: { eq: "started" } }) {
      nodes { id name type position }
    }
  }
}
```

（这正是官方 `agent-best-practices.md` 里推荐 Agent 接手 issue 时"把状态挪到 started 分类第一个状态"的标准写法——按 `type` 过滤 + 按 `position` 排序取最小值，不要硬编码状态名字符串比如 `"In Progress"` 去匹配，不同团队/不同语言工作区这个名字可能不一样。）

**核心查询**：`workflowState(id)` / `workflowStates(filter: WorkflowStateFilter, ...)`

**关键字段**：`type: String!` 状态分类，取值 `"triage" | "backlog" | "unstarted" | "started" | "completed" | "canceled" | "duplicate"`（7 种），`position: Float!` 决定同分类下的显示顺序（数字越小越靠前）。

**关键 mutation**（`WorkflowStateCreateInput`）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | `String!` | 是 | |
| `color` | `String!` | 是 | 十六进制色值 |
| `teamId` | `String!` | 是 | 新状态归属的团队，**创建后不可转移到别的团队** |
| `type` | `String!` | 是 | 必须是上面 7 种取值之一 |
| `position` | `Float` | 否 | 不传则追加到该分类末尾（⚠ 未实测确认排序默认行为） |

```graphql
mutation { workflowStateCreate(input: { name: "Blocked", color: "#eb5757", teamId: "9cfb482a-...", type: "started" }) { success workflowState { id } } }
```

`workflowStateUpdate(id, input: WorkflowStateUpdateInput!)`、`workflowStateArchive(id)`。**`teamId` 不在 `WorkflowStateUpdateInput` 里**（更新时不能换团队），要跨团队复用一个状态定义唯一的办法是在目标团队重新创建一份同名同色的状态。

## IssueLabel（可以是团队私有，也可以是工作区级）

和 WorkflowState/Cycle 不同，**Label 的团队归属是可选的**：`IssueLabel.team: Team`（可空）。`team` 为 `null` 表示这是**工作区级标签**，任意团队的 issue 都能用；`team` 非空则是该团队私有标签。这个"跨团队通用性"上的行为和 WorkflowState/Cycle 正好相反，容易套错经验。

**核心查询**：`issueLabel(id)` / `issueLabels(filter: IssueLabelFilter, ...)`，或 `team(id) { labels {...} }` / `organization { labels {...} }`（工作区级）。

```graphql
query FindLabel { issueLabels(filter: { name: { eq: "Bug" } }) { nodes { id name team { id key } } } }
```

**关键参数**（`IssueLabelCreateInput`）：`name: String!` 必填，`teamId` **不传即创建为工作区级标签**，传了则创建为该团队私有标签；`isGroup: Boolean` 标记这是一个"标签组"（父标签），`parentId` 让新标签归属到某个已有标签组下（`IssueLabel` 支持一层父子层级）。

```graphql
mutation { issueLabelCreate(input: { name: "P0", color: "#ff0000" }) { success issueLabel { id name } } }
```

`issueLabelUpdate(id, input)`、`issueLabelDelete(id)`（硬删，返回 `DeletePayload!`）、`issueLabelRetire(id)`/`issueLabelRestore(id)`（软删/恢复，返回 `IssueLabelPayload!`）——**retire/restore 和 delete 是两条不同的路径**，delete 没有恢复入口，需要"可撤销的删除"场景应该用 retire。

**注意事项**：创建同名标签在同一团队下是否报重复 ⚠ 文档未说明；跨团队或团队标签与工作区标签之间允许重名（因为它们是完全独立的记录，`id` 不同）。给 issue 挂标签时（`labelIds`/`issueAddLabel`），团队私有标签和工作区标签的 UUID 可以在同一个数组里混用。
