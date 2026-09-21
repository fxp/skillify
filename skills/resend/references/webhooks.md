# Webhook（送达 / 退信 / 投诉事件）

> ⚠ 本文件的全部内容都是 `⚠ 文档原文，未实测`——整理自 `resend.com/docs`（抓取于 2026-09-21），未经真实 API 调用确认。见 SKILL.md 里的验证状态说明。

## 这份文件要防的坑

**退信和投诉的 webhook 事件是"选配"的，不是自动的。** 一个发了邮件、指望"反正会有别的办法知道退信/投诉"的 agent 是错的——除非你显式创建一个 webhook 并在它的 `events` 数组里列出想要的事件类型，否则不会有任何东西主动推给你的应用。这一点关系到送达率：一个从来没接这条线的集成，除了 Resend 在平台层面自动做的那部分之外（见下文——确实有一些自动保护,只是没有 webhook 你看不见它在起作用），完全没有应用层信号去停止往一个持续失败的地址发信。

**不依赖 webhook、始终自动生效的部分**：Resend 自己维护一份抑制名单，对任何硬退信或投诉过的地址,**自动跳过之后的发送**,全平台生效,零配置。完整机制见 `domain-verification.md` 的抑制名单一节。Webhook 的作用是让*你的应用*知道发生了某个事件（同步自己的数据库、提醒人工、从自己在别处维护的独立邮件列表里移除这个地址)——它不是让 Resend 停止往坏地址重发的那个机制,那个是自动的。

## 管理 webhook — API

**Endpoint**：`POST https://api.resend.com/webhooks`

| 字段 | 类型 | 是否必填 |
|---|---|---|
| `endpoint` | string | **是**——你公网可达的 HTTPS URL。 |
| `events` | array of strings | **是**——你必须显式列出每一个想要的事件类型（完整列表见下文）。没有"订阅全部"这个默认选项，也不会因为你为比如 `email.sent` 创建了一个 webhook，就隐含地把退信/投诉也包含进去。 |

**响应 201** 包含 `signing_secret`——保存好它；验证收到的 payload 时要用（见下文）。`GET`/列表调用也会返回它，默认情况下不会在其他任何地方再明文显示一次。⚠ 文档未说明 之后能不能在不轮换的情况下重新显示它。

其他端点：`GET /webhooks`（列表）、`GET /webhooks/{id}`（单个，包含 `signing_secret`）、`PATCH /webhooks/{id}`（更新 `endpoint`/`events`/`status`——`status` 是 `enabled`\|`disabled`）、`DELETE /webhooks/{id}`。

**⚠ 文档自相矛盾 —— 官方 OpenAPI 规范（v1.5.0）只定义了 `/webhooks` 和 `/webhooks/{webhook_id}`。** 文字文档另外还记录了五个 webhook 管理端点，它们在 `openapi.json` 里**完全不存在**——这一点是直接读每个页面自己的示例 `curl` 命令确认的（这几个页面纯 Markdown 导出版本里，渲染出来的路径组件会被剥离掉——只抓 `` /docs/**.md `` 是看不到路径的，只有请求示例代码块里才有）：

| 用途 | Method + path（来自文档自己的 curl 示例） |
|---|---|
| 轮换签名密钥 | `POST /webhooks/{webhook_id}/signing-secret/rotate` |
| 列出投递到某个 webhook 的事件 | `GET /webhooks/{webhook_id}/events` |
| 获取某一个已投递的事件 | `GET /webhooks/{webhook_id}/events/{event_id}` |
| 重放一次投递尝试 | `POST /webhooks/{webhook_id}/events/{event_id}/replay` |
| 列出某个事件的所有投递尝试 | `GET /webhooks/{webhook_id}/events/{event_id}/attempts` |

把这五个当成真实存在、但**规范未确认**的端点——因为它们不在机器可读的 OpenAPI 规范里，不要在没检查你的代码生成器是否真的识别它们的情况下，针对它们构建依赖 spec 的工具链（自动生成的客户端、基于 schema 校验的请求）；照着上面的形状手写请求即可。

```bash
curl -X POST 'https://api.resend.com/webhooks' \
  -H "Authorization: Bearer $RESEND_API_KEY" -H 'Content-Type: application/json' \
  -d '{
    "endpoint": "https://yourapp.example.com/webhooks/resend",
    "events": ["email.bounced", "email.complained", "email.delivered", "suppression.added"]
  }'
```

## 完整事件类型列表

想收到下面任何一个事件，都必须在 `events` 里显式点名——不会因为订阅了别的事件就隐含包含。

**邮件相关事件**（对一个负责发信的 agent 最相关的几个）：

| 事件 | 触发时机 |
|---|---|
| `email.sent` | API 请求成功，Resend 将*尝试*投递。**这不代表已经送达**——它的意思是"已接受待发送"，相当于 HTTP 请求被接受，不代表邮件已经进入某个收件箱。 |
| `email.delivered` | Resend 的发送在收件人的邮件服务器上成功（被对方 MX 接受，不一定意味着落进主收件箱而不是垃圾邮件文件夹）。 |
| `email.delivery_delayed` | 临时性问题（收件箱已满、接收方服务器瞬时故障)——之后仍可能变成 `delivered`，不要当成终态。 |
| `email.bounced` | 收件人邮件服务器的**永久性**拒收——这是需要处理的"地址无效"信号。退信类型/子类型细节见下文。 |
| `email.complained` | 已送达，但收件人标记为垃圾邮件。**Gmail/Google Workspace 完全不会把这个事件上报给 Resend**——如果相当一部分收件人在用 Gmail，不要指望 `email.complained` 能提供完整的投诉覆盖。 |
| `email.suppressed` | 因为收件人已经在抑制名单上，这次发送被跳过——和 `bounced`（那是*把*地址加进名单的事件）是不同的事件。 |
| `email.opened` | 收件人打开了邮件（基于像素追踪——和任何打开追踪一样存在准确性上的局限，比如会被注重隐私的邮件客户端/代理拦截）。 |
| `email.clicked` | 收件人点击了邮件里的一个链接（需要发信域名开启点击追踪）。 |
| `email.scheduled` | 邮件被排期了（在排期设定的时刻触发，不是实际发送的时刻）。 |
| `email.failed` | 发送失败，原因不是邮件服务器退信——比如收件人格式无效、API key 问题、域名验证问题、超出配额等。 |
| `email.received` | 收到了一封**入站**邮件（需要域名配置了 Receiving 功能——本 skill 不覆盖这个功能）。 |

**其他分类**（不在本 skill 的核心范围内，但列出来是为了完整性，因为订阅机制是一样的）：`domain.created` / `domain.updated` / `domain.deleted`；`contact.created` / `contact.updated` / `contact.deleted`（注意：**批量 CSV 导入联系人不会触发 `contact.created` 事件**——如果你依赖这个事件来判断联系人何时落地，这是文档记录的一个已知缺口）；`suppression.added` / `suppression.removed`。

## 退信类型/子类型细节（针对 `email.bounced` payload）

| 类型 | 含义 | 子类型 |
|---|---|---|
| `Permanent`（"硬退信"） | 永远不会被送达。 | `General`、`NoEmail`（无法从退信消息本身提取出收件人地址）。 |
| `Transient`（"软退信"） | 之后可能会成功。 | `General`、`MailboxFull`、`MessageTooLarge`、`ContentRejected`、`AttachmentRejected`。 |
| `Undetermined` | 退信了，但接收方服务器的消息里没有足够细节可以分类。 | `Undetermined`。 |

依据抑制机制（`domain-verification.md`），只有 `Permanent` 类型的退信会自动触发加入抑制名单；`Transient` 退信值得记一笔日志，但单靠它本身不足以成为停止给这个地址发信的理由。

## Payload 结构

```json
{
  "type": "email.bounced",
  "created_at": "2026-11-22T23:41:12.126Z",
  "data": {
    "email_id": "56761188-7520-42d8-8898-ff6fc54ce618",
    "from": "Acme <onboarding@resend.dev>",
    "to": ["delivered@resend.dev"],
    "subject": "Sending this example",
    "bounce": { "type": "Permanent", "subType": "Suppressed", "message": "..." },
    "tags": { "category": "confirm_email" }
  }
}
```

每一个 webhook 请求还会带上 `svix-id`、`svix-timestamp`、`svix-signature` 这三个**请求头**（Resend 的 webhook 投递是基于 [Svix](https://docs.svix.com) 构建的，这是一个第三方 webhook 基础设施提供商——如果你以前对接过其他平台基于 Svix 的 webhook，认出这几个请求头名字会很有用，验证机制是一样的）。

## 签名验证 —— 信任一个 payload 之前先做这一步

从"你"的视角看，webhook 是 Resend 发来的未经鉴权的 HTTP POST——攻击者可以伪造一个 POST 打到你的端点、冒充一个退信/送达事件，除非你验证了签名。

**推荐方式 —— SDK 辅助方法**（用原始请求体和三个 `svix-*` 请求头）：

```ts
const result = resend.webhooks.verify({
  payload: rawBodyString, // must be the RAW, unparsed request body — re-stringifying parsed JSON breaks the signature check
  headers: {
    id: req.headers['svix-id'],
    timestamp: req.headers['svix-timestamp'],
    signature: req.headers['svix-signature'],
  },
  webhookSecret: process.env.RESEND_WEBHOOK_SECRET, // the signing_secret from webhook creation
});
```

**手动方式 —— 直接用 Svix 库**（`npm install svix`，或其他语言的 Svix 客户端）对任何基于 Svix 的 webhook 都是同样的用法，不是 Resend 专属的：

```ts
import { Webhook } from 'svix';
const wh = new Webhook(secret);
wh.verify(rawPayloadString, { 'svix-id': ..., 'svix-timestamp': ..., 'svix-signature': ... }); // throws on invalid signature
```

⚠ **用原始请求体，不要用解析后再重新序列化的版本。** 很多 Web 框架会在你的处理函数运行之前自动把请求体解析成 JSON；把解析出来的对象重新序列化之后再拿去验证，即使是一个真实有效的 payload 也会验证失败，因为签名是基于原始的确切字节计算出来的。

## 投递保证、顺序、重试

- **至少一次投递**——极少数情况下同一个事件可能被投递不止一次（比如你的服务器已经处理完了，但 ack 还没收到就发生网络超时)。用 `svix-id` 请求头去重（存下已处理过的 id，跳过重复的）。
- **不保证顺序。** 同一封邮件的 `email.opened` 可能先于 `email.delivered` 到达。如果你的逻辑依赖顺序，按 payload 里的 `created_at` 排序，不要假设到达顺序就反映了事件发生的顺序。
- **非 200 响应的重试计划**（指数退避）：立即 → 5 秒 → 5 分钟 → 30 分钟 → 2 小时 → 5 小时 → 10 小时 → 再 +10 小时。如果你的端点被移除/禁用，投递尝试会停止。
- **自动禁用 + 通知**：如果一个端点持续失败，Resend 会给你团队发邮件；如果还是不行，最终会**自动禁用**这个 webhook，并发第二封通知邮件。你需要在自己端点恢复健康之后手动去 dashboard 重新启用它——即使那个失败的端点后来开始正常返回 200 了，只要还标记着禁用，它不会自己悄悄恢复。
- **手动重放**：`failed` 和 `succeeded` 的事件都可以重放——从 dashboard 操作，或者调用 `POST /webhooks/{webhook_id}/events/{event_id}/replay`（见上面 spec 与文档的差异说明；这个端点有文档但不在 `openapi.json` 里)。适合在一次故障之后做数据回填，或者用更新过的处理逻辑重新处理一遍。
- **IP 白名单**（如果你的基础设施需要）：`44.228.126.217`、`50.112.21.217`、`52.24.126.164`、`54.148.139.208`、`2600:1f24:64:8000::/52`。

## 本地开发

Resend CLI 有一个 `webhooks listen` 命令，会启动一个本地服务器、注册一个临时 webhook，并把事件实时流式输出到你的终端——作为开发时搭 ngrok/端口转发隧道来暴露真实端点的替代方案。
