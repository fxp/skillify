# Webhooks 与签名校验

> ⚠ 本文件全部内容转录自 docs.stripe.com（抓取于 2026-09-21），未经真实 API 调用验证——签名算法本身是标准 HMAC-SHA256，逻辑上可自行推导验证，但没有拿真实 Stripe 请求跑过。

## ⚠⚠ 先读这一段：不验证签名是安全漏洞，不是"最佳实践没做到"

**你的 webhook 端点是一个公网可访问的 HTTPS URL，任何人都能对它发 POST 请求**。如果处理逻辑收到一个 `{"type": "payment_intent.succeeded", ...}` 就直接信任并执行"发货"、"开通服务"、"标记订单已付款"这类动作，而不先验证这个请求真的来自 Stripe，那么**任何知道你端点 URL 的人都可以伪造事件、免费拿到你的商品或服务**。这不是代码质量问题，是可以直接导致资金损失的安全漏洞，本 skill 把它放在和金额单位错误同等优先级的位置反复强调。

验证方式：检查请求携带的 `Stripe-Signature` header，配合该 webhook 端点专属的签名密钥（`whsec_...`，注意这不是 API Key，见 [auth-and-modes.md](auth-and-modes.md#webhook-签名密钥不是-api-key)）。

## 目录

- [设置一个 webhook 端点](#设置一个-webhook-端点)
- [用官方库验证签名（推荐）](#用官方库验证签名推荐)
- [手写验证算法（不用官方库时）](#手写验证算法不用官方库时)
- [最容易踩的坑：框架把原始请求体改写了](#最容易踩的坑框架把原始请求体改写了)
- [常见事件类型](#常见事件类型)
- [可靠性最佳实践](#可靠性最佳实践)
- [本地测试](#本地测试)

## 设置一个 webhook 端点

1. 你的服务暴露一个公网可访问的 HTTPS `POST` 端点。
2. 在 Dashboard **Webhooks** 页（或用 `/v2/core/event_destinations` API）注册这个端点 URL,选择要订阅的事件类型。
3. 注册成功后 Dashboard 会显示一个 `whsec_...` 开头的签名密钥，**只显示一次，点 Reveal secret 才能看到**，要立刻保存到你的 secrets 管理里。
4. 同一个端点如果同时收 test 模式和 live 模式的事件，**两种模式的签名密钥不同**，要分别保存。

本地开发没有公网 URL 时，用 `stripe listen --forward-to localhost:4242/webhook`（Stripe CLI）转发事件，CLI 会打印一个临时的 `whsec_...` 给本地验证用。

## 用官方库验证签名（推荐）

所有官方 SDK 都提供构造/验证事件的方法，只需要三个输入：**原始请求体字符串**、`Stripe-Signature` header 的值、这个端点的 `whsec_` 密钥。

```python
import stripe

endpoint_secret = os.environ["STRIPE_WEBHOOK_SECRET"]  # whsec_...

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.data  # 必须是原始 bytes/str，不能是已经被框架 parse 过的对象
    sig_header = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        return "", 400  # payload 不是合法 JSON
    except stripe.SignatureVerificationError:
        return "", 400  # 签名不匹配，拒绝处理，不要执行任何业务逻辑

    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        # 处理逻辑
    return "", 200
```

```javascript
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
const endpointSecret = process.env.STRIPE_WEBHOOK_SECRET; // whsec_...

app.post('/webhook', express.raw({type: 'application/json'}), (req, res) => {
  let event;
  try {
    event = stripe.webhooks.constructEvent(req.body, req.headers['stripe-signature'], endpointSecret);
  } catch (err) {
    return res.status(400).send(`Webhook signature verification failed: ${err.message}`);
  }
  if (event.type === 'payment_intent.succeeded') {
    // 处理逻辑
  }
  res.json({received: true});
});
```

验证失败（`SignatureVerificationError` / 抛异常）时**必须返回 4xx 并且不执行任何业务逻辑**——这不是"记录一下警告继续处理"的场景。

## 手写验证算法（不用官方库时）

`Stripe-Signature` header 格式：

```
t=1492774577,v1=5257a869e7ecebeda32affa62cdca3fa51cad7e77a0e56ff536d0ce8e108d8bd,v0=6ffbb59b2300aae63f272406069a9788598b792a944a07aba816edb039989a39
```

- `t=` 是 Unix 时间戳
- `v1=` 是当前有效的签名 scheme（HMAC-SHA256）
- `v0=` 是给旧客户端兼容用的假签名，**必须忽略**，只验证 `v1`（忽略非 `v1` scheme 是防降级攻击的要求，不是可选项）

验证步骤：
1. 按 `,` 分割 header，再按 `=` 分割每一段拿到 `t` 和（一个或多个）`v1` 值。
2. 拼接 `signed_payload = f"{t}.{raw_request_body}"`（时间戳 + 英文句号 + 原始请求体字符串，注意是**原始**字节，不是重新 `json.dumps` 序列化后的版本）。
3. 用该端点的 `whsec_` 密钥作为 HMAC key，对 `signed_payload` 算 HMAC-SHA256，得到期望签名。
4. 用**常量时间比较**（防时序攻击）把期望签名和 header 里的 `v1` 值比对，只要有一个匹配就算验证通过。
5. **同时检查时间戳新鲜度**：拿 `t` 和当前时间比较，超出容忍窗口（官方库默认 5 分钟）就拒绝，防止重放攻击。⚠ 文档原文明确警告：**不要把容忍度设成 0**，那样等于完全关掉了重放检查。

## 最容易踩的坑：框架把原始请求体改写了

签名验证依赖的是 Stripe 发出时的**原始字节**,很多 Web 框架的默认中间件会在你的路由函数拿到 body 之前就做了 JSON 解析、重新序列化、改变空白符/键顺序——任何改动都会让签名对不上,报 `No signatures found matching the expected signature for payload`。

- **Express + `express.json()`**：如果 `express.json()` 中间件注册在 webhook 路由之前，它会提前把 body 解析成对象,等到达 webhook handler 时原始字符串已经丢了。**webhook 路由要在 `express.json()` 之前注册，或者只对 webhook 路由用 `express.raw({type: 'application/json'})`**。
- **Next.js**（App Router / Pages Router）：默认的 body parsing 同样会干扰,需要关闭自动 body parsing 后手动读取原始 buffer,具体做法参考官方 stripe-node 仓库里的示例。
- **AWS API Gateway + Lambda**：需要配置 Body Mapping Template 显式透传 `rawBody` 字段,直接用 `event.body` 可能已经被网关处理过。

排查这类错误的第一步永远是：打印实际收到的 `sig_header` 和 body 字符串，确认 header 格式确实是 `t=...,v1=...` 这种形式，再确认 body 没有被任何中间件动过。

## 常见事件类型

支付相关：

| 事件 | 说明 |
|---|---|
| `payment_intent.created` | PaymentIntent 创建 |
| `payment_intent.succeeded` | 支付成功 |
| `payment_intent.payment_failed` | 支付尝试失败 |
| `payment_intent.requires_action` | 需要客户完成额外认证（3DS 等） |
| `payment_intent.canceled` | 已取消 |
| `charge.succeeded` / `charge.failed` / `charge.refunded` | 具体扣款记录层面的事件 |
| `charge.dispute.created` | 客户发起拒付 |

Checkout：

| 事件 | 说明 |
|---|---|
| `checkout.session.completed` | 客户完成 Checkout（一次性支付或订阅首期） |
| `checkout.session.async_payment_succeeded` / `.async_payment_failed` | 部分支付方式（如银行转账）结果是异步到达的 |
| `checkout.session.expired` | 会话超时未完成 |

订阅/账单相关：见 [subscriptions-and-billing.md](subscriptions-and-billing.md#该监听哪些-webhook-事件)。

完整事件类型清单见 [官方文档](https://docs.stripe.com/api/events/types.md)（截至抓取时有几百种，本文件只列高频用到的）。

## 可靠性最佳实践

- **只订阅集成实际需要的事件类型**，不要订阅全部事件——文档原文明确说这会给你的服务端造成不必要的处理压力。
- **处理重复投递**：Stripe 可能对同一事件投递多次，用 `event.id` 做幂等去重（记录已处理过的 event id）。少数情况下同一个业务动作会生成两个不同的 Event 对象，这种情况下用 `data.object` 里业务对象自己的 ID 加 `event.type` 组合去重。
- **快速返回 2xx**，复杂的业务逻辑（发邮件、写第三方系统）放到异步队列里处理，不要在 webhook handler 里同步跑完再返回，避免超时导致 Stripe 判定投递失败而重试,造成额外的重复处理压力。
- **自动重试**：live 模式下失败会在最多 3 天内按指数退避重试；sandbox 模式下重试几次、间隔几小时。端点被禁用/删除后停止重试。
- **签名验证 + IP 白名单双重防护**：Stripe 固定从一组已知 IP 发送 webhook（列表见 [docs.stripe.com/ips.md](https://docs.stripe.com/ips.md)），可以配置防火墙只接受这些 IP 的请求,但**这只是纵深防御的一层，不能替代签名校验**——两者都要做。
- **CSRF 豁免**：Rails/Django 这类框架默认对所有 POST 做 CSRF token 校验，webhook 路由要单独豁免,否则会先被框架自己的 CSRF 中间件拦下来（和 Stripe 无关的另一个坑）。
- **定期轮换签名密钥**：Dashboard 里可以 roll secret，轮换期间新旧密钥同时有效最多 24 小时,给你时间平滑切换代码里的密钥。

## 本地测试

```bash
stripe listen --forward-to localhost:4242/webhook
# 另开一个终端：
stripe trigger payment_intent.succeeded
```

`stripe trigger <event_type>` 会真实创建一套触发该事件的最小对象组合并转发到本地端点,比手写假 payload 更贴近真实事件结构。
