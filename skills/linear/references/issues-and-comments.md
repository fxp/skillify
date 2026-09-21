# Issues：查询 / 创建 / 更新 / 评论 / 附件

> 字段来自官方 GraphQL SDL（`schema.graphql`，随 `@linear/sdk` 发布），行为性描述未用真实 Key 调用验证，标 `⚠ 文档原文，未实测`。

## 目录
1. [查询单个 issue](#查询单个-issue)
2. [查询/过滤 issue 列表](#查询过滤-issue-列表)
3. [创建 issue（issueCreate）](#创建-issueissuecreate)
4. [批量创建（issueBatchCreate）](#批量创建issuebatchcreate)
5. [更新 issue（issueUpdate）](#更新-issueissueupdate)
6. [删除 / 归档 / 取消归档](#删除--归档--取消归档)
7. [标签（Label）增删](#标签label增删)
8. [评论（Comment）](#评论comment)
9. [上传文件并附到 issue](#上传文件并附到-issue)
10. [Issue 关系（阻塞/重复/相关）](#issue-关系阻塞重复相关)

## 查询单个 issue

**用途**：按 ID 拿单个 issue 的详情。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | `String!` | 是 | 接受 UUID，**也接受人类可读 identifier**（如 `"ENG-123"`），两种格式都能直接用，不需要先转换 |

**示例请求**

```graphql
query Issue {
  issue(id: "ENG-123") {
    id
    identifier
    title
    description
    priority
    priorityLabel
    state { id name type }
    team { id key name }
    assignee { id name }
    project { id name }
    cycle { id number }
    labels { nodes { id name } }
  }
}
```

```bash
curl https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" -H "Content-Type: application/json" \
  --data '{"query":"query($id:String!){issue(id:$id){id identifier title state{name}}}","variables":{"id":"ENG-123"}}'
```

**示例响应**

```json
{ "data": { "issue": { "id": "590a1127-...", "identifier": "ENG-123", "title": "...", "priority": 2, "priorityLabel": "High", "state": {"id":"...","name":"In Progress","type":"started"} } } }
```

**注意事项**：`priority` 是 `Float!`（0–4 的数值：0=无优先级，1=Urgent，2=High，3=Medium，4=Low），`priorityLabel` 是对应的文字标签，两个字段都能直接查，不需要自己维护映射表。

## 查询/过滤 issue 列表

**Endpoint**: `issues(after, before, first, last, filter: IssueFilter, includeArchived, orderBy, sort)` → `IssueConnection!`

分页与过滤的通用规则见 `references/pagination-and-filtering.md`，这里只给 issue 特有的例子。

```graphql
query MyOpenBugs {
  issues(
    filter: {
      assignee: { isMe: { eq: true } }
      labels: { name: { eq: "Bug" } }
      state: { type: { nin: ["completed", "canceled"] } }
    }
    first: 20
    orderBy: updatedAt
  ) {
    nodes { id identifier title state { name } priority }
    pageInfo { hasNextPage endCursor }
  }
}
```

也可以从 `team`/`user`/`project`/`cycle`/`workflowState` 等节点上直接挂载的 `issues(...)` 字段查（例如 `team(id:...) { issues(...) { nodes {...} } } }`），过滤参数形状与顶层 `issues` 完全一致（都是 `IssueFilter`）。

**⚠ 容易踩的坑**：过滤器默认不排除"未设置优先级"（`priority: 0`）的 issue。比如 `filter: { priority: { lte: 2 } }` 会把 `priority: 0`（无优先级）也算作 `<= 2` 一起返回，要显式加 `neq: 0` 才能排除。这是文档 `filtering.md` 明确给出的例子，不是隐藏行为。

## 创建 issue（issueCreate）

**用途**：新建一个 issue。**`teamId` 是唯一强制必填字段**，其余全部可选。

**关键参数**（`IssueCreateInput`，完整字段见 SDL；这里列常用的）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `teamId` | `String!` | **是** | 必须是 Team 的 UUID，不接受团队 key（如 `"ENG"`），需要先查 `teams(filter:{key:{eq:"ENG"}})` 拿 ID |
| `title` | `String` | 否 | 不传也能创建成功（⚠ 文档未明确必填与否，规范里未标 `!`，未实测确认省略后的默认标题行为） |
| `description` | `String` | 否 | Markdown，支持行内图片（自动上传，见下）、`+++` 折叠块、@mention 语法（见下方"Markdown 中的提及"） |
| `assigneeId` | `String` | 否 | 用户 UUID |
| `stateId` | `String` | 否 | **必须是该 issue 所属 `teamId` 名下的 WorkflowState UUID**，跨团队的 state ID 无法使用（见 `teams-projects-cycles-states.md` 的团队私有性说明）。不传时默认落到该团队 Backlog 分类的第一个状态；team 开了 Triage 功能则默认落到 Triage 状态 |
| `priority` | `Int` | 否 | 0–4 |
| `labelIds` | `[String!]` | 否 | Label UUID 数组，团队标签和工作区级标签（`team: null`）都可以混用 |
| `projectId` / `cycleId` / `parentId` | `String` | 否 | 同样只接受 UUID |
| `dueDate` | `TimelessDate` | 否 | `"YYYY-MM-DD"` 格式，不带时区 |
| `createAsUser` / `displayIconUrl` | `String` | 否 | 仅 `actor=app` OAuth 场景常用，见 `auth-and-endpoint.md` |

**示例请求**

```graphql
mutation IssueCreate {
  issueCreate(
    input: {
      title: "New exception"
      description: "More detailed error report in markdown"
      teamId: "9cfb482a-81e3-4154-b5b9-2c805e70a02d"
    }
  ) {
    success
    issue { id identifier title }
  }
}
```

**示例响应**

```json
{ "data": { "issueCreate": { "success": true, "issue": { "id": "...", "identifier": "ENG-124", "title": "New exception" } } } }
```

**注意事项**：
- 所有 mutation payload 的通用形状是 `{ success: Boolean!, <entity>: <Type>, lastSyncId: Float! }`——先检查 `success`，`entity` 字段在失败时可能为 `null`。
- **创建后前 3 分钟内对该 issue 属性的修改不会计入活动日志（activity log）**，即"创建过程的一部分"不算作后续变更，写自动化脚本统计"谁改了什么"时要注意这个窗口。
- Markdown 描述里的图片会被 Linear **自动下载并转存到私有云存储**（见 `auth-and-endpoint.md` 文件存储小节），不是简单地存一个外链。

## 批量创建（issueBatchCreate）

**用途**：一次请求创建多个 issue,减少往返次数。

**关键参数**：`input.issues: [IssueCreateInput!]!`——数组里每个元素和单个 `issueCreate` 的 `input` 结构完全一致(包括 `teamId` 仍是每个元素各自必填,不是共享一个)。

```graphql
mutation IssueBatchCreate($input: IssueBatchCreateInput!) {
  issueBatchCreate(input: $input) {
    success
    issues { id identifier title }
  }
}
```

```json
{ "input": { "issues": [
  { "teamId": "9cfb482a-...", "title": "Issue 1" },
  { "teamId": "9cfb482a-...", "title": "Issue 2" }
] } }
```

**注意事项**：返回的 `issues` 数组顺序 ⚠ 文档未说明是否与输入顺序一致，批量创建后如果需要精确对应关系，建议依赖 `title` 或自定义标记去匹配，不要假设下标对齐。这类批量接口通常仍计入常规请求复杂度限额（见 `errors-and-rate-limits.md`），批量并不等于免复杂度。

## 更新 issue（issueUpdate）

**用途**：更新已有 issue 的任意字段。

**关键参数**：mutation 顶层单独有 `id: String!`（同样接受 UUID 或 `"ENG-123"` 格式），`input: IssueUpdateInput!` 里放要改的字段，未出现在 input 里的字段不受影响。`labelIds` 是"整体替换"，如果只想增删部分标签用 `addedLabelIds`/`removedLabelIds`（`IssueUpdateInput` 独有，`IssueCreateInput` 没有）。

```graphql
mutation IssueUpdate {
  issueUpdate(
    id: "ENG-123"
    input: { stateId: "NEW-STATE-ID", addedLabelIds: ["label-uuid"] }
  ) {
    success
    issue { id title state { id name } }
  }
}
```

**注意事项**：
- `stateId` 必须属于该 issue 当前所在（或本次一起更新到的）团队；把另一个团队的 workflow state ID 传进来是最常见的跨团队自动化 bug 来源，务必先用 `team(id:...) { states { nodes { id name type } } }` 查出目标团队自己的状态 ID 列表再传。
- `trashed: true` / `trashed: false` 也在这个 input 里，等价于软删除/恢复，效果和 `issueDelete`/`issueUnarchive` 有重叠但走的是同一个 mutation，选哪个看你的代码里是否已经在用 `issueUpdate`。

## 删除 / 归档 / 取消归档

Linear 区分三种"移除"语义，**默认都不是立即物理删除**：

| Mutation | 语义 | 关键参数 |
|---|---|---|
| `issueDelete(id, permanentlyDelete)` → `IssueArchivePayload!` | **软删除（trash）**，30 天宽限期内可恢复；`permanentlyDelete: true` 跳过宽限期立即硬删，**仅管理员可用** | `id` |
| `issueArchive(id, trashed)` → `IssueArchivePayload!` | 归档（不等于删除，归档的 issue 仍可查询，默认从分页结果隐藏） | `id` |
| `issueUnarchive(id)` → `IssueArchivePayload!` | 取消归档 | `id` |

**注意事项**：`IssueArchivePayload.entity` 字段的文档说明是"归档/取消归档后的实体，如果实体已被（硬）删除则为 `null`"——写幂等的清理脚本时，`entity: null` 不代表调用失败，要看 `success` 字段。查询默认不返回已归档资源，要显式传 `includeArchived: true` 才能看到。

## 标签（Label）增删

单独加/删一个标签，不需要整体替换 `labelIds`：

```graphql
mutation { issueAddLabel(id: "ENG-123", labelId: "label-uuid") { success issue { id labels { nodes { name } } } } }
mutation { issueRemoveLabel(id: "ENG-123", labelId: "label-uuid") { success } }
```

创建/更新/归档 Label 本身（`issueLabelCreate`/`issueLabelUpdate`/`issueLabelRetire`）见 `references/teams-projects-cycles-states.md`。

## 评论（Comment）

**用途**：给 issue（或 Project / Document / Initiative，取决于传哪个 `*Id`）加评论。

**关键参数**（`CommentCreateInput`）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `body` | `String` | 否（⚠ 未标 `!`，未实测确认省略是否报错） | Markdown 正文 |
| `issueId` / `projectId` / `projectUpdateId` / `initiativeId` / `initiativeUpdateId` / `postId` | `String` | 四选一 | 评论挂载到哪个实体，只应传其中一个 |
| `parentId` | `String` | 否 | 回复某条已有评论，形成子线程 |
| `quotedText` | `String` | 否 | 行内评论时引用的原文片段 |
| `createOnSyncedSlackThread` | `Boolean` | 否 | 是否同步创建对应的 Slack 线程 |

```graphql
mutation CommentCreate($input: CommentCreateInput!) {
  commentCreate(input: $input) {
    success
    comment { id body issue { identifier } }
  }
}
```

```json
{ "input": { "issueId": "590a1127-f98b-49fc-ba74-2df8751c089e", "body": "Looking into this now." } }
```

其余评论 mutation：`commentUpdate(id, input: CommentUpdateInput!)`、`commentDelete(id)`、`commentResolve(id, resolvingCommentId?)`、`commentUnresolve(id)`——都返回 `CommentPayload!`（`{ success, comment, lastSyncId }`），`commentDelete` 返回 `DeletePayload!`（`{ success, entityId, lastSyncId }`，没有完整实体，只有被删 ID）。

**注意事项**：
- Agent 场景下**评论内容会被用户编辑，读取时不保证是最初发送的内容**；如果在构建 Agent 需要"冻结时间点"的对话快照，应该读 Agent Session 的 Activity 记录而不是 Comment 本身，见 `references/agents-and-mcp.md`。
- Markdown 正文里用纯 Linear URL（issue/用户 profile 链接）会被自动转换成 @mention 渲染，不需要特殊的 mention 语法。

## 上传文件并附到 issue

两种方式：

1. **行内 Markdown 图片自动上传**：在 `description`/`body` 里直接写 `![alt](https://example.com/image.png)` 或 base64 data URI，Linear 会自动下载/解码并转存。最简单，但只适合图片，不适合任意文件类型。
2. **`fileUpload` mutation 手动上传**：适合非图片文件，或需要控制存储元数据的场景。

**关键参数**（`fileUpload(contentType, filename, size, makePublic?, metaData?)` → `UploadPayload!`）

```graphql
mutation FileUpload($contentType: String!, $filename: String!, $size: Int!) {
  fileUpload(contentType: $contentType, filename: $filename, size: $size) {
    success
    uploadFile { uploadUrl assetUrl headers { key value } }
  }
}
```

拿到 `uploadFile.uploadUrl` 后，**必须在服务端**（不能在浏览器端，会被 Linear 的 CSP 拦截）发起 `PUT` 请求，把 `uploadFile.headers` 数组转成 `Headers` 对象一并带上：

```ts
const { uploadFile } = (await fileUpload(...)).data.fileUpload;
const headers = new Headers({ "Content-Type": contentType });
uploadFile.headers.forEach(({ key, value }) => headers.set(key, value));
await fetch(uploadFile.uploadUrl, { method: "PUT", headers, body: fileBuffer });
// 之后用 uploadFile.assetUrl 作为 issueCreate/commentCreate 的 description/body 里的图片链接
```

**注意事项**：`403 Forbidden` 常见原因是忘记把 `uploadFile.headers`（数组格式）转换成真正的 HTTP headers 附到 PUT 请求上；`CORS error` 常见原因是直接从浏览器发起了 PUT（必须经服务端代理）。上传后得到的 `assetUrl` 指向 Linear 私有存储，展示时同样需要鉴权（见 `auth-and-endpoint.md`）。

独立的 issue 附件（Attachment，用于关联外部系统链接、如 GitHub PR / 客服工单，语义上不同于"文件上传"）走 `attachmentCreate`/`attachmentUpdate` mutation 和 `attachment`/`attachmentsForURL` 查询，`attachmentCreate` 传入的 `url` 在同一个 `issueId` 下是幂等键——用同一个 URL 再次创建会更新已有附件而不是产生重复记录。附件详细的 `metadata` 富文本渲染规则参见官方 [Attachments](https://linear.app/developers/attachments) 页，此 skill 未展开覆盖（不在本次范围内）。

## Issue 关系（阻塞/重复/相关）

`issueRelationCreate`/`issueRelationUpdate`/`issueRelationDelete` 管理 issue 之间的 `blocks`/`duplicate`/`related` 等关系类型，`issue.relations` 字段可查询。⚠ 本 skill 未展开这部分字段表（不在任务给定范围内），需要时用 `schema.graphql` 里的 `IssueRelation`/`IssueRelationCreateInput` 自行核对，或参考 Apollo Studio 的 schema explorer。
