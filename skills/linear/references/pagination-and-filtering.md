# 分页与过滤

> 来源：`https://linear.app/developers/pagination`、`https://linear.app/developers/filtering`（抓取于 2026-09-21）+ GraphQL SDL 里 `PageInfo`/`*Connection`/`PaginationOrderBy` 的精确定义。这一份基本是纯 schema 事实，行为部分（默认排序、默认页大小）来自文档原文，未实测复核。

## 目录
1. [Relay 风格 cursor 分页——精确 shape](#relay-风格-cursor-分页精确-shape)
2. [nodes 简写 vs edges 完整写法](#nodes-简写-vs-edges-完整写法)
3. [排序（orderBy）](#排序orderby)
4. [归档资源默认隐藏](#归档资源默认隐藏)
5. [过滤（Filter）比较器](#过滤filter比较器)
6. [逻辑运算符 and / or](#逻辑运算符-and--or)
7. [按关联关系过滤](#按关联关系过滤)
8. [相对时间过滤](#相对时间过滤)

## Relay 风格 cursor 分页——精确 shape

Linear 所有返回列表的字段都是 `XxxConnection`，统一实现 [Relay Connection spec](https://relay.dev/graphql/connections.htm)。**精确字段名**（来自 SDL，不要凭记忆拼写，`hasNextPage`/`hasPreviousPage` 不要漏掉 `has` 前缀，也不要错写成 `hasMore`）：

```graphql
type PageInfo {
  endCursor: String
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
}

type IssueConnection {   # 以 Issue 为例，其余实体的 XxxConnection 形状完全一样
  edges: [IssueEdge!]!
  nodes: [Issue!]!
  pageInfo: PageInfo!
}

type IssueEdge {
  node: Issue!
  cursor: String!
}
```

所有分页字段共同的参数签名（`after`/`before`/`first`/`last` 四个是**每一个** connection 字段都有的，不止顶层 `issues`）：

```graphql
issues(
  after: String        # 向前翻页游标，传上一页 pageInfo.endCursor
  before: String        # 向后翻页游标，传上一页 pageInfo.startCursor
  first: Int             # 向前分页数量，默认 50
  last: Int              # 向后分页数量，默认 50
  includeArchived: Boolean  # 默认 false，见下
  orderBy: PaginationOrderBy  # createdAt（默认）| updatedAt
  filter: IssueFilter
): IssueConnection!
```

**往后翻页**：

```graphql
query Issues($after: String) {
  issues(first: 10, after: $after) {
    edges { node { id title } cursor }
    pageInfo { hasNextPage endCursor }
  }
}
```

把上一次响应的 `pageInfo.endCursor` 作为下一次请求的 `after` 变量，循环直到 `pageInfo.hasNextPage == false`。

**注意事项**：
- **默认页大小是 50**，不传 `first`/`last` 的查询会静默截断到前 50 条,不会报错也不会提示还有更多数据(除非你检查 `pageInfo.hasNextPage`)。批量导出、统计类脚本容易因为漏查 `hasNextPage` 而拿到不完整的数据却毫无察觉。
- `first`/`last` 不要同时传（Relay 规范下二者语义互斥，一个是向前分页一个是向后分页），⚠ 文档未明确同时传会报错还是其中一个被忽略。
- 复杂度计费与分页数量直接挂钩：`first`/`last` 越大，单次请求复杂度分数越高（详见 `errors-and-rate-limits.md`），显式传一个够用的小值既能控成本又能让复杂度计算器知道你的真实需求。

## nodes 简写 vs edges 完整写法

不需要 `cursor` 值（比如不做分页，只想要前 N 条）时可以跳过 `edges`，直接用 `nodes` 拿到扁平数组（写法上类似 GitHub GraphQL API 的习惯）：

```graphql
query Teams {
  teams { nodes { id name } }
}
```

两种写法返回的是同一份底层数据，`nodes` 只是省略了每条记录的 `cursor` 字段，`pageInfo` 仍然存在,要继续翻页仍然要读 `pageInfo.endCursor`/`hasNextPage`（`cursor` 字段本身用不到时才适合用 `nodes` 简写；需要精确定位某一条记录对应哪个游标时用 `edges`）。

## 排序（orderBy）

```graphql
enum PaginationOrderBy { createdAt updatedAt }
```

**只有这两个取值**，默认 `createdAt`。想要"最近变更优先"（例如轮询增量更新、避免重复拉取旧数据）要显式传 `orderBy: updatedAt`：

```graphql
query RecentlyUpdated {
  issues(orderBy: updatedAt) {
    nodes { id identifier title updatedAt }
  }
}
```

官方明确建议：需要增量同步数据时按 `updatedAt` 排序 + 记录上次同步的时间戳去过滤，而不是要轮询导出全量数据再在客户端过滤（见 `references/webhooks.md` 和 `errors-and-rate-limits.md` 关于"避免轮询"的建议——Linear 更推荐用 webhook 替代高频轮询）。

`issues` 顶层查询还有一个 `sort: [IssueSortInput!]`参数（`projects` 也有对应的 `sort: [ProjectSortInput!]`），SDL 里标注为 `[INTERNAL]`，⚠ 不确定公开 API 客户端能否稳定依赖，不建议在生产代码里使用，用标准的 `orderBy` 就够。

## 归档资源默认隐藏

所有分页查询默认 **不返回已归档的资源**（`archivedAt` 非空的记录），要显式传 `includeArchived: true` 才能看到：

```graphql
query { issues(includeArchived: true) { nodes { id title archivedAt } } }
```

## 过滤（Filter）比较器

绝大多数可分页字段都能传 `filter: XxxFilter`，`XxxFilter` 是按目标类型逐字段生成的输入类型，每个字段对应一个"比较器"输入类型（如 `NullableStringComparator`/`DateComparator`/`NumberComparator`）。

**通用比较器**（字符串 / 数值 / 日期字段都有）：

| 比较器 | 说明 |
|---|---|
| `eq` | 等于 |
| `neq` | 不等于 |
| `in` | 在给定集合中 |
| `nin` | 不在给定集合中 |

**数值 / 日期字段额外支持**：

| 比较器 | 说明 |
|---|---|
| `lt` / `lte` | 小于 / 小于等于 |
| `gt` / `gte` | 大于 / 大于等于 |

**字符串字段额外支持**：

| 比较器 | 说明 |
|---|---|
| `eqIgnoreCase` / `neqIgnoreCase` | 忽略大小写的等于/不等于 |
| `startsWith` / `notStartsWith` | 前缀匹配 |
| `endsWith` / `notEndsWith` | 后缀匹配 |
| `contains` / `notContains` | 包含 |
| `containsIgnoreCase` / `notContainsIgnoreCase` | 忽略大小写包含 |

**可空字段额外支持 `null: Boolean`**（判断字段是否有值）：

```graphql
query { issues(filter: { description: { null: true } }) { nodes { id title } } }
```

**⚠ 容易漏掉的默认值坑**：`priority: { lte: 2 }` 这类数值过滤会把 `priority == 0`（"无优先级"，不是"最高优先级"）也一并算作 `<= 2` 返回,因为 0 在数值上确实小于等于 2。想要"只看设了优先级且是高优先级"的 issue,要显式加 `neq: 0`。这是文档明确给出的例子,不是隐藏行为,但很容易被忽略。

## 逻辑运算符 and / or

**同一个 filter 对象里的多个字段默认按 `and` 合并**（全部满足才匹配）：

```graphql
query { issues(filter: { priority: { eq: 1 }, dueDate: { lte: "2021" } }) { nodes { id title } } }
```

要用 `or` 逻辑，显式用 `or: [XxxFilter!]` 数组：

```graphql
query { issues(filter: { or: [{ priority: { eq: 4 } }, { priority: { eq: 0 } }], dueDate: { lte: "2021" } }) { nodes { id title } } }
```

（这个例子里 `or` 分支和顶层的 `dueDate` 条件之间仍然是 `and` 关系——`or` 只管它自己数组里的条件互相是"或"，不会把整个 filter 对象变成"或"。）

## 按关联关系过滤

可以按关联对象的字段过滤，语法是把关联字段名当 key，值是对应类型的 Filter：

```graphql
# 按 assignee 邮箱过滤
query { issues(filter: { assignee: { email: { eq: "john@linear.app" } } }) { nodes { id title } } }

# 一对多/多对多关系：默认语义是"至少一个匹配"（any）
query { issues(filter: { labels: { name: { eq: "Bug" } } }) { nodes { id title } } }

# 要求"全部匹配"用 every
query { issues(filter: { labels: { every: { name: { eq: "Bug" } } } }) { nodes { id title } } }
```

**注意事项**：`labels: { name: { eq: "Bug" } }`（不加 `every`）返回的是"至少有一个标签叫 Bug"的 issue，**即使该 issue 还挂了其他标签也会被匹配**；`every` 版本则要求该 issue 的**所有**标签都叫 "Bug"（实际上只对单标签 issue 有意义，多标签 issue 几乎不可能满足）。两者语义差异很大，选错会导致过滤结果偏差很大却没有报错提示。

也可以嵌套跨层过滤，比如"项目负责人叫 John 的项目下、带 Bug/Defect 标签的 issue"：

```graphql
query {
  projects(filter: { lead: { name: { startsWith: "John" } } }) {
    nodes {
      issues(filter: { labels: { name: { in: ["Bug", "Defect"] } } }) {
        nodes { id title }
      }
    }
  }
}
```

## 相对时间过滤

所有日期字段的比较值除了 ISO 日期字符串，还支持 **ISO 8601 Duration**（相对当前时间），常用于"写一次、每次跑结果都准确"的过滤条件而不用每次手算日期：

```graphql
# 两周内到期的 issue（每次运行都以"当前时间"为基准，不需要改代码里的日期字面量）
query { issues(filter: { dueDate: { lt: "P2W" } }) { nodes { id title } } }

# 过去两周内完成的 issue（负号表示"过去"）
query { viewer { createdIssues(filter: { completedAt: { gt: "-P2W" } }) { nodes { id title } } } }
```

正数 Duration（如 `"P2W"`）表示"未来"方向，负号前缀（如 `"-P2W"`）表示"过去"方向,写定时任务/看板脚本时用这个而不是每次现算 `new Date()` 再格式化成绝对日期传参,能省掉一类时区换算 bug。
