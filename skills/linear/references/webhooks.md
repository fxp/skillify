# Webhooks

> 来源：`https://linear.app/developers/webhooks`、`https://linear.app/developers/oauth-app-manifests`（resourceTypes 列表）、`https://linear.app/developers/sdk-webhooks`（抓取于 2026-09-21）。签名验证代码抄自官方文档示例，**未用真实 webhook 密钥实测验签**，标 `⚠ 文档原文，未实测`。Agent 专属的 `AgentSessionEvent` webhook 单独在 `references/agents-and-mcp.md` 讲，本文件只讲"数据变更"类通用 webhook。

## 目录
1. [创建 / 查询 / 删除 webhook](#创建--查询--删除-webhook)
2. [投递机制与重试策略](#投递机制与重试策略)
3. [Payload 形状](#payload-形状)
4. [验证签名（安全性）](#验证签名安全性)
5. [TypeScript SDK 的 LinearWebhookClient](#typescript-sdk-的-linearwebhookclient)

## 创建 / 查询 / 删除 webhook

**权限要求**：**只有工作区 admin，或带 `admin` scope 的 OAuth 应用，才能创建/读取 webhook**——普通成员权限的 API Key 大概率会在这一步失败（⚠ 文档只说了权限要求，未给出失败时的具体错误码，未实测）。

**关键参数**（`WebhookCreateInput`）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `url` | `String!` | 是 | 接收 POST 的 HTTPS 地址 |
| `resourceTypes` | `[String!]!` | 是 | 订阅的资源类型数组，见下方完整枚举 |
| `teamId` | `String` | 否 | 只订阅单个团队的事件 |
| `allPublicTeams` | `Boolean` | 否 | 订阅工作区全部公开团队的事件（和 `teamId` 二选一，⚠ 未实测确认同时传两者的优先级） |
| `enabled` | `Boolean` | 否，默认 `true` | |
| `secret` | `String` | 否 | 签名密钥，不传则由 Linear 生成 |
| `label` | `String` | 否 | 便于在设置页识别用途的标签 |

**支持订阅的资源类型**（"数据变更"webhook）：`Issue`、`IssueLabel`、`Comment`、`Reaction`（评论表情回应）、`Project`、`ProjectLabel`、`ProjectUpdate`、`Document`、`Initiative`、`InitiativeUpdate`、`Cycle`、`Customer`、`CustomerNeed`、`User`、`Attachment`。此外还有两类"便捷型"webhook 不属于标准数据变更事件：`IssueSLA`（SLA 相关事件）、`OAuthAuthorization`（OAuth App 被撤权时触发）。**Agent 场景专属的 `AgentSessionEvent`、`AppUserNotification`、`PermissionChange` 见 `agents-and-mcp.md`**，这三类同样在 `resourceTypes` 里订阅，但只有 OAuth App（尤其是 `actor=app` 模式的 agent）场景才有意义。

```graphql
mutation {
  webhookCreate(
    input: {
      url: "https://example.com/webhooks/linear-consumer"
      teamId: "72b2a2dc-6f4f-4423-9d34-24b5bd10634a"
      resourceTypes: ["Issue"]
    }
  ) {
    success
    webhook { id enabled }
  }
}
```

```json
{ "data": { "webhookCreate": { "success": true, "webhook": { "id": "790ce3f6-ea44-473d-bbd9-f3c73dc745a9", "enabled": true } } } }
```

查询与删除：

```graphql
query { webhooks { nodes { id url enabled team { id name } } } }
mutation { webhookDelete(id: "1087f03a-180a-4c31-b7dc-03dbe761ff59") { success } }
```

**注意事项**：webhook 属于 `Organization`（工作区），不是绑定到某个 App/用户，创建后可以通过 `webhooks` 顶层查询或 `team(id) { webhooks {...} }` 两条路径查到。OAuth App 也可以在 App 配置页预先声明 webhook 设置（`webhook.url`/`webhook.resourceTypes`），**每当一个新工作区安装该 App 时会自动为该工作区创建一个指向配置 URL 的 webhook**——这是 OAuth App 场景下批量管理 webhook 的推荐方式，不需要 App 自己在每次安装后再调 `webhookCreate`。

## 投递机制与重试策略

- Webhook 消费端必须是**公网可访问的 HTTPS 地址**（不能是 localhost）。
- 必须在收到 POST 后返回 **HTTP 200**表示已确认。
- 失败判定：服务不可达、**响应耗时超过 5 秒（5000ms）**、或返回非 200 状态码。
- 失败重试：**最多重试 3 次**，采用退避延迟——分别在 **1 分钟、1 小时、6 小时后**重试。
- 如果持续不响应，**该 webhook 可能被 Linear 自动禁用**，需要手动重新启用。

写消费端时的实践建议（官方给出）：收到请求后先快速返回 200，再异步处理业务逻辑,避免因为处理耗时超过 5 秒被判定为投递失败(尤其是签名验证之外还有耗时 I/O 的场景)。

## Payload 形状

**HTTP Headers**（每个 webhook 请求都带）：

```http
Accept-Charset: utf-8
Content-Type: application/json; charset=utf-8
Linear-Delivery: 234d1a4e-b617-4388-90fe-adc3633d6b72
Linear-Event: Issue
Linear-Signature: 766e1d90a96e2f5ecec342a99c5552999dd95d49250171b902d703fd674f5086
Linear-Timestamp: 1676056940508
User-Agent: Linear-Webhook
```

| Header | 说明 |
|---|---|
| `Linear-Delivery` | UUID v4，唯一标识这次投递（可用于去重/幂等） |
| `Linear-Event` | 触发事件的实体类型（`Issue`、`Comment` 等） |
| `Linear-Signature` | 请求体的 HMAC-SHA256 签名（hex 编码），见下节验证方法 |
| `Linear-Timestamp` | 发送时间的 UNIX 毫秒时间戳 |

**数据变更事件 body**（`action`/`type`/`actor`/`createdAt`/`data`/`url`/`updatedFrom`/`webhookTimestamp` 这几个字段所有数据变更事件通用）：

```json
{
  "action": "create",
  "actor": { "id": "b5ea5f1f-...", "type": "user", "name": "Linear Orbit", "email": "orbit@linear.app", "url": "..." },
  "data": { "id": "2174add1-...", "body": "...", "issueId": "...", "userId": "..." },
  "type": "Comment",
  "url": "https://linear.app/issue/LIN-1778/foo-bar#comment-...",
  "createdAt": "2020-01-23T12:53:18.084Z",
  "organizationId": "dc844923-...",
  "webhookTimestamp": 1676056940508,
  "webhookId": "000042e3-..."
}
```

| 字段 | 说明 |
|---|---|
| `action` | `create` / `update` / `remove` |
| `type` | 触发的实体类型 |
| `actor` | 触发者，可能是 `User`、OAuth client 或 `Integration`；如果触发者账号后来被删除，这里可能是 `null` |
| `data` | 该实体序列化后的完整值，形状与对应 GraphQL 类型一致 |
| `updatedFrom` | 仅 `update` 动作有：改动前各字段的旧值 |

`data` 字段的具体形状可以用 [Webhooks schema explorer](https://studio.apollographql.com/public/Linear-Webhooks/variant/current/schema/reference/objects)（Apollo Studio 公开 workspace）查，不需要凭猜测拼字段——webhook payload 的实体 schema 和常规 GraphQL query 返回的实体 schema **不完全是同一套类型定义**，有专门的 Webhooks schema。

## 验证签名（安全性）

**必须验证每个 webhook 请求确实来自 Linear**，两种手段叠加：

1. **HMAC-SHA256 签名验证**：用 webhook 的 `secret`（创建时可指定，或系统生成，webhook 详情页可查看/轮换）对**原始请求体字节**计算 HMAC-SHA256，hex 编码后与 `Linear-Signature` header 比较。**⚠ 必须用原始请求体（raw bytes），不能用解析后再重新 `JSON.stringify` 的字符串**——重新序列化可能因为字段顺序、空白符差异导致签名对不上，这是官方文档明确强调的坑，中间件（如 body-parser）如果在验签前就把 body 解析消费掉，会导致拿不到原始字节。
2. **时间戳校验**：解析后 body 里的 `webhookTimestamp` 字段（毫秒），建议校验其与本地当前时间相差在 1 分钟以内，防止重放攻击。

```ts
// 官方 Express 示例，⚠ 文档原文未实测
const crypto = require("node:crypto");

function verifySignature(headerSignatureString, rawBody, secret) {
  if (typeof headerSignatureString !== "string") return false;
  const headerSignature = Buffer.from(headerSignatureString, "hex");
  const computedSignature = crypto.createHmac("sha256", secret).update(rawBody).digest();
  return crypto.timingSafeEqual(computedSignature, headerSignature);
}

app.post("/webhook", express.json({
  verify: (req, _res, buf) => { req.rawBody = buf; }  // 关键：body-parser 验签阶段保留原始字节
}), (req, res) => {
  if (!verifySignature(req.get("linear-signature"), req.rawBody, LINEAR_WEBHOOK_SECRET)) {
    return res.sendStatus(401);
  }
  if (Math.abs(Date.now() - req.body.webhookTimestamp) > 60 * 1000) {
    return res.sendStatus(401);  // 拒绝超过 60 秒的请求，防重放
  }
  // ... 处理已验证的 webhook ...
  return res.sendStatus(200);
});
```

第二重手段：Linear 的出站 IP 地址在 [Security 文档](https://linear.app/docs/security#collapsible-fb465e337d77) 公开列出，可以额外做来源 IP 白名单校验。

## TypeScript SDK 的 LinearWebhookClient

`@linear/sdk/webhooks` 子包封装了签名验证 + 事件路由，比手写验签代码更省事：

```ts
import express from "express";
import { LinearWebhookClient } from "@linear/sdk/webhooks";

const webhookClient = new LinearWebhookClient("WEBHOOK_SECRET");
const handler = webhookClient.createHandler();

handler.on("Issue", (payload) => {
  console.log(payload.data.title);
});

app.post("/hooks/linear", handler);
```

**⚠ 关键前提**：和手写验签一样，**确保没有任何中间件（比如全局挂载的 body parser）在 `handler` 之前消费了原始请求体**——`LinearWebhookClient` 内部同样需要读取签名前的原始字节，被提前解析会导致签名验证失败。

手动验证场景（不想用内置 handler 路由，自己接管流程）也提供了独立的验证方法和常量：

```ts
import { LinearWebhookClient, LINEAR_WEBHOOK_SIGNATURE_HEADER, LINEAR_WEBHOOK_TS_FIELD } from '@linear/sdk/webhooks';

const webhookClient = new LinearWebhookClient("WEBHOOK_SECRET");

app.use("/hooks/linear", bodyParser.json({
  verify: (req, res, buf) => {
    webhookClient.verify(buf, req.headers[LINEAR_WEBHOOK_SIGNATURE_HEADER], JSON.parse(buf.toString())[LINEAR_WEBHOOK_TS_FIELD]);
  },
}), (req, res, next) => { next(); });
```
