# SDK 与客户端选择

> 来源：`https://linear.app/developers/sdk`、`sdk-fetching-and-modifying-data`、`sdk-errors`、`advanced-usage`、`migrating-from-1-x-to-2-x`（抓取于 2026-09-21）。代码示例抄自官方文档，**未用真实 API Key 实测跑通**，标 `⚠ 文档原文，未实测`。

## 目录
1. [官方只有 TypeScript SDK，没有官方 Python SDK](#官方只有-typescript-sdk没有官方-python-sdk)
2. [安装与初始化](#安装与初始化)
3. [查询与获取数据](#查询与获取数据)
4. [Mutation 调用方式](#mutation-调用方式)
5. [SDK 内建分页助手](#sdk-内建分页助手)
6. [错误处理](#错误处理)
7. [进阶：Raw Client / 自定义 Client](#进阶raw-client--自定义-client)
8. [1.x → 2.x 迁移：mutation 命名方式变了](#1x--2x-迁移mutation-命名方式变了)

## 官方只有 TypeScript SDK，没有官方 Python SDK

Linear 官方只维护并发布 **`@linear/sdk`（TypeScript/JavaScript）** 一个客户端库，源码在 [github.com/linear/linear/tree/master/packages/sdk](https://github.com/linear/linear/tree/master/packages/sdk)，通过代码生成把整份 GraphQL schema（`schema.graphql`）转成强类型的 models 和 operations（生成文件 `_generated_sdk.ts`）。它同时可以在任意 JavaScript 运行环境使用（不限 TypeScript 项目）。

**没有官方发布的 Python SDK。** 用 Python（或其他没有官方 SDK 的语言）调 Linear API 时，标准做法是**手写 GraphQL 请求**——用 `requests`/`httpx` 直接 POST 到 `https://api.linear.app/graphql`（见 `auth-and-endpoint.md` 的 curl 示例，Python 版本把 `curl` 换成对等的 HTTP 库调用即可），或使用通用的 GraphQL 客户端库（如 `gql`）指向该 endpoint。⚠ 本 skill 未逐一核实第三方非官方 Python 包（PyPI 上可能存在社区维护的 `linear-*` 包）的可靠性/维护状态，不建议不加核实就依赖，官方文档也没有推荐任何第三方 Python 客户端。写 Python 代码时把 GraphQL query/mutation 字符串直接当作本 skill 各 reference 文件里给出的那些请求体传过去，字段名/结构和 TypeScript SDK 背后的 GraphQL 是完全一致的。

其他官方生态：`@linear/sdk/webhooks` 子包（TypeScript，签名验证辅助，见 `webhooks.md`）。Agent 的 GraphQL 部分同样没有官方 Python 封装,`agentActivityCreate` 等 mutation 需要 Python 时同样手写 GraphQL。

## 安装与初始化

```bash
npm install @linear/sdk
```

```ts
import { LinearClient } from "@linear/sdk";

// 个人 API Key
const client1 = new LinearClient({ apiKey: YOUR_PERSONAL_API_KEY });

// OAuth2 access token
const client2 = new LinearClient({ accessToken: YOUR_OAUTH_ACCESS_TOKEN });
```

**注意事项**：SDK 内部会根据你传的是 `apiKey` 还是 `accessToken` 自动拼出正确的 `Authorization` header（无 Bearer / 有 Bearer 的区别，见 `auth-and-endpoint.md`），**不需要自己手动拼 header**，这是用官方 SDK 相对手写 HTTP 请求的一个直接好处——省掉了两种鉴权方式 header 格式不一致这个最容易犯错的点。

## 查询与获取数据

无参数的单值模型直接是 Promise：

```ts
const me = await linearClient.viewer;
const org = await linearClient.organization;
```

Connection 类模型返回 `.nodes`：

```ts
const issues = await linearClient.issues();
const firstIssue = issues.nodes[0];
```

必填参数作为函数的第一个位置参数，可选参数作为最后一个对象参数：

```ts
const user = await linearClient.user("user-id");
const team = await linearClient.team("team-id");
const fiftyProjects = await linearClient.projects({ first: 50 });
const allComments = await linearClient.comments({ includeArchived: true });
```

模型上可以继续链式取关联模型（**只有当操作需要可选参数对象时才需要加括号**，纯属性访问不用）：

```ts
const me = await linearClient.viewer;
const myIssues = await me.assignedIssues();
const myFirstIssueComments = await myIssues.nodes[0].comments();
const commentAuthor = await myFirstIssueComments.nodes[0].user;  // 属性访问，不加括号
```

## Mutation 调用方式

三种等价写法：

```ts
// 1. 顶层方法 + input 对象
const team = (await linearClient.teams()).nodes[0];
await linearClient.createIssue({ teamId: team.id, title: "My Created Issue" });

// 2. 顶层方法 + 必填 id 位置参数 + input 对象
const me = await linearClient.viewer;
await linearClient.updateUser(me.id, { displayName: "Alice" });

// 3. 从模型实例上直接调用（省去重复传 id）
await me.update({ displayName: "Alice" });
```

Mutation 通常返回 `{ success, <entity> }` 形状的 Payload：

```ts
const commentPayload = await linearClient.createComment({ issueId: "some-issue-id" });
if (commentPayload.success) {
  return commentPayload.comment;
} else {
  throw new Error("Failed to create comment");
}
```

**⚠ 重要**：SDK 方法名是 `createIssue`/`updateUser`/`archiveProject` 这种"动词+模型名"顺序（2.x 命名规范，见下方迁移小节），**不是**直接照抄 GraphQL mutation 名字 `issueCreate`/`userUpdate`/`projectArchive`——这是初次用 SDK 时最容易犯的命名直觉错误：GraphQL 层是"模型名+动词"，SDK 层是反过来的"动词+模型名"。

## SDK 内建分页助手

Connection 结果自带 `fetchNext()`/`fetchPrevious()`，不需要手动把 `pageInfo.endCursor` 抄回下一次调用的参数里：

```ts
const issues = await linearClient.issues({ after: "some-issue-cursor", first: 10 });
const nextIssues = await issues.fetchNext();
const prevIssues = await issues.fetchPrevious();
```

也可以手动拼装（和裸 GraphQL 请求思路一致）：

```ts
const issues = await linearClient.issues();
const hasMoreIssues = issues.pageInfo.hasNextPage;
const moreIssues = await linearClient.issues({ after: issues.pageInfo.endCursor, first: 10 });
```

排序：

```ts
import { LinearDocument } from "@linear/sdk";
const issues = await linearClient.issues({ orderBy: LinearDocument.PaginationOrderBy.UpdatedAt });
```

（`PaginationOrderBy` 枚举值只有 `CreatedAt`/`UpdatedAt` 两种，对应 GraphQL 层的 `createdAt`/`updatedAt`，见 `pagination-and-filtering.md`。）

## 错误处理

```ts
import { InvalidInputLinearError, LinearError, LinearErrorType } from '@linear/sdk';

createTeam(input).catch(error => {
  if (error instanceof InvalidInputLinearError) {
    return new UserError(input, error);
  }
  throw error;
});
```

SDK 把原始 GraphQL 错误解析成带类型的 Error 子类（`InvalidInputLinearError`、`RatelimitedLinearError` 等，对应 `LinearErrorType` 枚举），可以用 `instanceof` 判断分支处理逻辑，而不用自己解析 `extensions.type`/`extensions.code` 字符串。`LinearError` 实例上还附带：

| 属性 | 说明 |
|---|---|
| `error.query` / `error.variables` | 导致失败的原始请求（query 字符串 + 变量） |
| `error.status` | HTTP 状态码 |
| `error.data` | 响应里可能附带的部分数据 |
| `error.errors` | 解析后的 `LinearGraphQLError[]`，每个含 `message`/`type`/`userError`/`path` |
| `error.raw` | 未加工的原始错误对象 |

`LinearErrorType` 完整枚举（来自 SDK 源码 `error.ts`）：`FeatureNotAccessible`、`InvalidInput`、`Ratelimited`、`NetworkError`、`AuthenticationError`、`Forbidden`、`BootstrapError`、`Unknown`、`InternalError`、`Other`、`UserError`、`GraphqlError`、`LockTimeout`、`UsageLimitExceeded`。裸 GraphQL 调用（不经 SDK）时这些类型对应的原始字符串、及其与 `rate-limiting.md` 文档给出的 `extensions.code: "RATELIMITED"` 大写写法之间的关系，见 `errors-and-rate-limits.md` 的 ⚠ 待验证条目。

## 进阶：Raw Client / 自定义 Client

不想用 SDK 生成的强类型方法，直接发原始 GraphQL：

```ts
const graphQLClient = linearClient.client;
const cycle = await graphQLClient.rawRequest(
  `query cycle($id: String!) { cycle(id: $id) { id name completedAt } }`,
  { id: "cycle-id" }
);
```

自定义 header（比如 `public-file-urls-expire-in`，见 `auth-and-endpoint.md`）：

```ts
const linearClient = new LinearClient({ apiKey, headers: { "my-header": "value" } });
// 或运行时动态设置
linearClient.client.setHeader("my-header", "value");
```

需要完全自定义底层请求逻辑（比如接入公司内部的 HTTP 客户端/中间件体系）时可以扩展 `LinearSdk`：

```ts
import { LinearError, LinearFetch, LinearRequest, LinearSdk, parseLinearError, UserConnection } from "@linear/sdk";

const customLinearRequest: LinearRequest = (document, variables) =>
  customGraphqlClient.request(document, variables).catch(error => { throw parseLinearError(error); });

class CustomLinearClient extends LinearSdk {
  constructor() { super(customLinearRequest); }
}
```

## 1.x → 2.x 迁移：mutation 命名方式变了

SDK 2.x 把 mutation 方法名从"模型名在前"改成了"动词在前"：

```ts
// 1.x
await linearClient.userUpdate(me.id, { displayName: "Alice" });

// 2.x（当前版本）
await linearClient.updateUser(me.id, { displayName: "Alice" });
```

**⚠ 如果读到的示例代码/训练记忆里是 `userUpdate`/`issueCreate` 这种写法，那是 1.x 或直接照抄 GraphQL mutation 名字的写法**，当前 `@linear/sdk` 2.x 的正确方法名是 `updateUser`/`createIssue`。GraphQL 层的 mutation 名字（`issueCreate`、`userUpdate` 等，本 skill 其余 reference 文件里给的都是这套）本身没有变,变的只是 SDK 包一层之后暴露给调用方的方法名。
