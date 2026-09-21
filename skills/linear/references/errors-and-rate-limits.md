# 错误处理与限流

> 来源：`https://linear.app/developers/graphql`（Error handling 小节）、`https://linear.app/developers/rate-limiting`、`https://linear.app/developers/deprecations`（抓取于 2026-09-21）+ `@linear/sdk` 源码 `error.ts`。数值（限额、复杂度算法）来自文档原文，**未用真实调用触发限流验证准确性**，标 `⚠ 文档原文，未实测`。

## 目录
1. [错误响应的两种形状：200 部分成功 vs 400 限流](#错误响应的两种形状200-部分成功-vs-400-限流)
2. [GraphQL 标准错误 shape](#graphql-标准错误-shape)
3. [限流：三套独立配额，API Key 和 OAuth App 不一样](#限流三套独立配额api-key-和-oauth-app-不一样)
4. [查询复杂度计算](#查询复杂度计算)
5. [避免触发限流的实践](#避免触发限流的实践)
6. [API 没有版本号，用 @deprecated 指令](#api-没有版本号用-deprecated-指令)

## 错误响应的两种形状：200 部分成功 vs 400 限流

Linear 的 GraphQL API **不是所有错误都返回同一个 HTTP 状态码**，这是最容易被"GraphQL 错误一律 200"这类通用经验坑到的地方：

| 场景 | HTTP 状态码 | 说明 |
|---|---|---|
| 常规字段/校验错误（无效输入、权限不足、找不到资源等） | **200** | 遵循 GraphQL 标准："GraphQL queries can partially succeed with a 200 HTTP status, returning some data while including errors for failed fields."——**必须显式检查响应体里的 `errors` 数组，不能只看 HTTP 状态码判断成功** |
| 触发限流（超出请求数/复杂度配额） | **400** | `errors[].extensions.code == "RATELIMITED"`，见下节 |
| 服务端异常 | **5xx** | 文档只是笼统提到"监控 5xx"，未展开具体分类 |

也就是说，"检查 `errors` 数组"和"检查 HTTP 状态码"两件事都要做，缺一个都可能判断错：只看状态码会漏掉 200 里带的部分失败；只看 `errors` 数组不看状态码会把限流场景和普通字段错误混为一谈（限流场景应该做退避重试，普通输入错误不应该重试）。

## GraphQL 标准错误 shape

```json
{
  "errors": [
    {
      "message": "...",
      "path": ["issueCreate"],
      "extensions": { "code": "...", "...": "..." }
    }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `message` | 人类可读的错误描述 |
| `path` | 出错的 GraphQL 节点路径 |
| `extensions` | 附加上下文，可能包含错误码、校验细节等 |

**⚠ 待验证的字段名不一致**：官方 rate-limiting 文档给的限流错误示例用的是 `extensions.code: "RATELIMITED"`（大写、`code` 字段）；而 `@linear/sdk` 的 `error.ts` 源码里，SDK 是读取 `error.extensions?.type` 这个字段，映射到一份**小写字符串表**（如 `Ratelimited` 枚举 ↔ `"ratelimited"` 字符串，`InvalidInput` ↔ `"invalid input"` 等，完整映射见 `sdk-and-clients.md`）。这两处一个用 `code`/大写，一个用 `type`/小写——**没有真实调用确认这两个字段是否同时存在、还是文档示例与 SDK 实现分别对应两个不同版本/不同字段**，写裸 GraphQL 错误处理代码时建议 `extensions.code` 和 `extensions.type` 两个字段都做兼容检查，不要只读其中一个。

## 限流：三套独立配额，API Key 和 OAuth App 不一样

**请求数配额**（响应头 `X-RateLimit-Requests-Limit`/`X-RateLimit-Requests-Remaining`/`X-RateLimit-Requests-Reset`，reset 时间是 UTC 毫秒 epoch）：

| 认证方式 | 限额 | 归属维度 | 周期 |
|---|---|---|---|
| API Key | **2,500** | 用户（同一用户名下所有 API Key **共享同一份配额**，不是每个 Key 各算各的） | 1 小时 |
| OAuth App | **5,000** | 用户（或 App User，即 `actor=app` 场景） | 1 小时 |
| 未鉴权 | 600 | 来源 IP | 1 小时 |

**复杂度配额**（响应头 `X-Complexity`/`X-RateLimit-Complexity-Limit`/`X-RateLimit-Complexity-Remaining`/`X-RateLimit-Complexity-Reset`）：

| 认证方式 | 限额 | 归属维度 | 周期 |
|---|---|---|---|
| API Key | **3,000,000** | 用户 | 1 小时 |
| OAuth App | **2,000,000** | 用户（或 App User） | 1 小时 |
| 未鉴权 | 100,000 | 来源 IP | 1 小时 |

**⚠ 反直觉的地方**：OAuth App 的**请求数**配额（5,000）比 API Key（2,500）高一倍，但**复杂度**配额（2,000,000）反而比 API Key（3,000,000）低——"换成 OAuth 全面更宽松"是错误假设，两个维度一高一低，用小请求量但高复杂度查询（比如深层嵌套 connection）的场景下 OAuth App 反而更容易先撞上复杂度上限。

**单次查询硬上限**：无论哪种认证方式，**单个查询复杂度超过 10,000 点直接拒绝**，与配额周期无关。

**独立于全局限额的单端点限额**：部分 query/mutation 有自己更低的独立限额（响应头会额外带 `X-RateLimit-Endpoint-Requests-Limit`/`-Remaining`/`-Reset`/`-Name`），⚠ 文档未列出具体哪些端点、具体数值是多少,只说了"部分"存在,写批量脚本时对高频调用的具体 mutation/query 建议先看一次响应头有没有出现这组 endpoint 专属限额头,不要假设全局限额就是唯一约束。

**Actor Authorization 动态提额**：走 OAuth Actor Authorization（`actor=app`）的工作区级应用，限额会根据该工作区付费用户数动态提高（具体倍数关系文档未给出公式）。

**触发限流的响应**：

```json
{ "errors": [{ "message": "...", "extensions": { "code": "RATELIMITED" } }] }
```

HTTP 状态码 **400**（不是 429，也不是常规错误的 200，见上节）。

**需要更高限额**：可联系 Linear 支持按具体场景申请（文档未给出自动化申请渠道,是人工评估）。

## 查询复杂度计算

计算规则：**每个标量属性 0.1 点，每个 object 类型字段 1 点，connection 字段按其子字段总点数乘以分页参数值（不传则按默认 50 计算）**，最终结果向上取整。

**示例 1**：

```graphql
query WhoAmI { user(id: "me") { name } }
```

`user` 是 1 个 object（1 点）+ `name` 是 1 个 property（0.1 点）= 1.1，向上取整 = **复杂度 2**。

**示例 2**（未显式分页，按默认 50 计算）：

```graphql
query MyCreatedIssues { user(id: "me") { createdIssues { nodes { id title createdAt } } } }
```

`user` 1 点 + `createdIssues`（默认 50）× 3 个属性 × 0.1 = 15 点，合计 **66**。

**示例 3**（显式限制到 10 条）：

```graphql
query MyCreatedIssues { user(id: "me") { createdIssues(first: 10) { nodes { id title createdAt } } } }
```

同样的字段，`first: 10` 让复杂度降到 **14**——**显式传分页参数不仅控制返回条数，也直接决定复杂度评分**，不传等于让计算器按最大默认值（50）估算，深层嵌套 connection（比如 `issues { nodes { comments { nodes { ... } } } }` 这种两层分页嵌套）复杂度是乘积级增长，很容易在没意识到的情况下逼近单次查询上限。

## 避免触发限流的实践

官方给出的建议（都是"设计层面避免"，不是"报错后重试"）：

1. **别轮询**——需要感知数据变化，用 Webhook（见 `webhooks.md`），不要写定时轮询脚本反复拉全量数据。
2. **善用过滤**——用 `filter` 精确圈定需要的数据，而不是拉全量到客户端再筛（见 `pagination-and-filtering.md`）。
3. **需要拉全量时按 `updatedAt` 排序**——只追增量变化，不必每次全量翻页。
4. **用 SDK 时也要写自定义查询**——SDK 默认生成的字段集合可能比实际需要的更宽，字段多、深层关联多都会推高复杂度，针对具体需求手写精简 query。
5. **显式传分页参数**——即使默认值够用，显式传一个明确的小数字能让复杂度计算器按真实需求算分，而不是按 50 的默认上限。

## API 没有版本号，用 @deprecated 指令

Linear 的 GraphQL API **不像很多 REST API 那样有版本号**（没有 `v1`/`v2` 这种路径前缀），因为 GraphQL 本身持续演进的特性使得传统版本化意义不大。

- 破坏性变更前，Linear 官方会**主动联系已知使用该部分 API 的开发者**，给足迁移时间。
- 功能移除时，通常**保留一个不报错的空桩（no-op stub）**，避免已有查询/变更直接崩掉（例如本 skill 提到的 `cycleCreate`，虽然标了 `@deprecated`、reason 是"不再支持"，但字段本身仍在 schema 里，调用它会怎样 ⚠ 文档未说明、未实测——不代表它会正常创建 Cycle，只是不确定是报错还是静默返回失败）。
- schema 里用标准 `@deprecated(reason: "...")` 指令标注废弃字段/mutation，`reason` 通常直接给出替代方案（如 `boardOrder` 的 deprecated reason 是"请用 `sortOrder`"）。写代码/生成代码前，**过一遍 SDL 里目标字段是否带 `@deprecated`，reason 文本本身就是最权威的迁移指引**，比翻文档页更准确及时。
- API 层面的变更同样会记录进 [Linear Changelog](https://linear.app/changelog)，带 `[API]` 前缀标注。
