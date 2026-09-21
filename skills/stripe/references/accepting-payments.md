# 接受一笔支付：Checkout Sessions vs PaymentIntents

> ⚠ 本文件全部内容转录自 docs.stripe.com（抓取于 2026-09-21），未经真实 API 调用验证。所有报错文案、状态流转描述均为文档原文转述,不是实测结果。

## 目录

- [先选型：Checkout Sessions 还是 PaymentIntents](#先选型checkout-sessions-还是-paymentintents)
- [PaymentIntent 的生命周期](#paymentintent-的生命周期)
- [创建 PaymentIntent](#创建-paymentintent)
- [确认 PaymentIntent](#确认-paymentintent)
- [Checkout Session（推荐的默认路径）](#checkout-session推荐的默认路径)
- [金额与货币：全平台最常见的 100 倍错误](#金额与货币全平台最常见的-100-倍错误)
- [测试卡号](#测试卡号)
- [幂等与重试](#幂等与重试)

## 先选型：Checkout Sessions 还是 PaymentIntents

**这条"该用哪个 API 作为首选支付集成方式"的推荐经历过不止一次迁移，本 skill 抓取时点（2026-09）确认的现状和大多数训练语料里"现代答案"已经不完全一样：**

| 阶段 | API | 现状 |
|---|---|---|
| 早期 | Charges API（`POST /v1/charges`，直接收卡号） | **已废弃**，不要用在新集成里，除非有特殊原因且没有其他办法 |
| 中期 / 多数人记忆中的"现代方案" | PaymentIntents API 直建 + Stripe.js/Elements 手动确认 | 仍然是官方支持、功能完整的正式 API，但**不再是官方默认首选** |
| **当前（2026-09 抓取确认）** | **Checkout Sessions API + Payment Element** | **官方当前默认推荐**，多数集成场景应该优先用这个 |

来自 `llms.txt`「Instructions for Large Language Model Agents」章节的原文态度（⚠ 文档原文，未实测，非逐字引用）：Stripe 把 Checkout Sessions API 当作支付的主力后端对象，明确说"不要推荐 Charges API"，而且**除非用户明确要求，否则不要用 Payment Intent API**，理由是代码量明显更大；`payments/payment-intents.md` 页面顶部也有近乎相同的措辞。唯一被文档点名"可以不用 Checkout Sessions"的场景，是需要「deferred Payment Intent + Elements」这种更定制化的流程（比如要在确认支付前先做自己的服务端校验逻辑）。

**这对本 skill 使用者的实际影响**：
- 如果任务是"给这个产品接一个标准的收银台/订阅收款页"，**先考虑 `POST /v1/checkout/sessions`**（Stripe 托管页面，或 `ui_mode: "elements"` 嵌入式），不要不假思索地直接手搭 PaymentIntent + Elements。
- 如果任务明确要求"完全自定义的支付表单/流程"、"我要在确认前拦截做自己的逻辑"、或者是本 skill 场景常见的"Agent/后端直接调 API、不需要 Stripe 托管的前端组件"，那么本文件下面详细讲的 **PaymentIntents 路径仍然是正确、受支持的选择**——这也是本 skill 按用户需求详细覆盖这条路径的原因。
- 无论选哪条路径，**都不要用 Charges API、Sources API、Tokens API**。保存客户支付方式一律走 SetupIntent 或 PaymentMethod + `setup_future_usage`，不要用 Sources。

## PaymentIntent 的生命周期

一个 PaymentIntent 代表一次购物车/一次结账会话的完整支付过程，典型状态流转：

```
requires_payment_method → requires_confirmation → requires_action（如需要 3DS）
  → processing → succeeded
                → requires_payment_method（失败，可重试新的支付方式）
                → canceled
```

构建集成分两步：**创建**（create）和**确认**（confirm）。也可以在 create 时传 `confirm=true` 一步做完（等价于用 confirm API 支持的全部参数）。

## 创建 PaymentIntent

**Endpoint**: `POST /v1/payment_intents`

**用途**：为一次支付建立一个跟踪对象，封装金额、货币、允许的支付方式等信息。官方建议尽早创建（比如客户一开始结账流程就创建），而不是等到最后一步。

**关键参数**（完整列表见 [官方文档](https://docs.stripe.com/api/payment_intents/create.md)，只列高频用到的）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `amount` | integer | 是 | — | 目标货币**最小单位**的整数金额，见下方"金额"一节。最低约 $0.50 美元等值，最多支持 8 位数字 |
| `currency` | enum | 是 | — | 三位小写 ISO 货币码，如 `usd` |
| `automatic_payment_methods[enabled]` | boolean | 否 | — | 设为 `true` 让 Stripe 根据 Dashboard 配置自动选可用支付方式，官方建议优先用这个而不是手动指定 `payment_method_types`（后者是旧写法，见下） |
| `payment_method_types` | array | 否 | — | 显式指定允许的支付方式类型（`card`、`us_bank_account`……几十种，完整枚举见 API reference）。⚠ 文档原文：官方建议改用 Dashboard 里的动态支付方式配置 + `automatic_payment_methods`，而不是在代码里手写这个列表，因为 Stripe 会根据客户所在地区/钱包/偏好自动挑更合适的方式 |
| `customer` | string | 否 | — | 关联的 Customer ID；配合 `setup_future_usage` 可以在支付完成后把支付方式自动 attach 到这个客户 |
| `payment_method` | string | 否 | — | 直接指定要用的 PaymentMethod ID |
| `capture_method` | enum | 否 | `automatic_async` | `automatic`（同步授权即扣款）/ `automatic_async`（默认，异步扣款，延迟更低，官方推荐优于 `automatic`）/ `manual`（先授权占用，之后单独调用 capture 扣款，不是所有支付方式都支持） |
| `confirm` | boolean | 否 | `false` | 设为 `true` 相当于创建后立刻确认，可以同时传 confirm API 的参数（如 `payment_method`、`return_url`） |
| `setup_future_usage` | enum | 否 | — | `on_session`（客户以后还会在结账流程里在场时复用）/ `off_session`（客户不在场时也要能复用，如订阅自动扣款）。设置后支付方式在确认完成、客户完成必需操作后会自动 attach 到 `customer` |
| `off_session` | boolean\|string | 否 | — | 传 `true` 表示这次支付客户当下不在场、无法完成交互式认证，用于"已保存支付方式后台代扣"场景 |
| `metadata` | map | 否 | — | 自定义键值对，会透传到关联的 Charge 上（后续更新 PaymentIntent 的 metadata 不会回溯更新已生成的 Charge） |

**示例请求**

```bash
curl https://api.stripe.com/v1/payment_intents \
  -u "$STRIPE_TEST_SECRET_KEY:" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d amount=1099 \
  -d currency=usd \
  -d "automatic_payment_methods[enabled]=true"
```

```python
import stripe

client = stripe.StripeClient(os.environ["STRIPE_TEST_SECRET_KEY"])
intent = client.v1.payment_intents.create(params={
    "amount": 1099,
    "currency": "usd",
    "automatic_payment_methods": {"enabled": True},
}, options={"idempotency_key": str(uuid.uuid4())})
```

```javascript
const stripe = require('stripe')(process.env.STRIPE_TEST_SECRET_KEY);

const intent = await stripe.paymentIntents.create(
  { amount: 1099, currency: 'usd', automatic_payment_methods: { enabled: true } },
  { idempotencyKey: crypto.randomUUID() }
);
```

**示例响应**（关键字段，⚠ 文档原文示例）

```json
{
  "id": "pi_3MtwBwLkdIwHu7ix28a3tqPa",
  "object": "payment_intent",
  "amount": 1099,
  "currency": "usd",
  "client_secret": "pi_3MtwBwLkdIwHu7ix28a3tqPa_secret_YrKJUKribcBjcG8HVhfZluoGH",
  "status": "requires_payment_method",
  "payment_method": null,
  "livemode": false
}
```

`client_secret` 是要传给前端（Stripe.js）完成确认用的，**不要记录日志、不要拼进 URL、只对当前客户暴露**，且必须在有 TLS 的页面上使用（⚠ 文档原文）。

**注意事项**

- 结账流程中断又恢复时，**复用同一个 PaymentIntent**（用之前存的 ID 检索），不要每次都新建——这样失败重试的历史状态才有意义。
- `payment_method` 省略且 `confirm=true` 时，会退回用 `customer.default_source`（是为了兼容老 Charges API 用户的迁移路径），**官方建议显式传 `payment_method`，不要依赖这个隐式回退**。
- 一个 PaymentIntent 可能关联多个 Charge 对象（多次尝试/重试各产生一个 Charge），要看具体某次支付结果需要检查对应 Charge 的 `outcome` 字段，不能只看 PaymentIntent 顶层状态。

## 确认 PaymentIntent

**Endpoint**: `POST /v1/payment_intents/{id}/confirm`

**用途**：表明客户确实要用某个支付方式付款，触发实际扣款尝试。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `payment_method` | string | 否（如果创建时已指定） | 要使用的 PaymentMethod ID |
| `return_url` | string | 视情况 | 客户完成 3DS 等跳转类认证后要跳回的地址，卡类和跳转类支付方式需要 |
| `off_session` | boolean\|string | 否 | 同 create，标记客户当下不在场 |
| `error_on_requires_action` | boolean | 否 | 设为 `true`：一旦需要额外认证就直接报错而不是走 `requires_action`，适合不打算处理交互式认证的简化集成 |

**示例请求**

```bash
curl https://api.stripe.com/v1/payment_intents/pi_xxx/confirm \
  -u "$STRIPE_TEST_SECRET_KEY:" \
  -d payment_method=pm_card_visa \
  --data-urlencode "return_url=https://example.com/return"
```

**关键行为**（⚠ 文档原文，未实测）：
- 如果支付方式需要额外认证（3D Secure 等），状态转到 `requires_action`，客户端要处理 `next_action` 字段指示的动作。
- 认证完成后回到 `requires_confirmation`，需要服务端**再显式调用一次 confirm** 才会真正发起扣款尝试——这一步容易被漏掉，误以为客户端认证通过=支付已完成。
- 确认次数有上限，超限后再调用会把 PaymentIntent 转成 `canceled`。
- 支付成功后转 `succeeded`（`capture_method=manual` 时是 `requires_capture`，需要再调用 capture）。

**支付完成之后**：官方建议服务端通过 **监听 webhook**（而不是只依赖客户端返回结果）来确认支付真的成功——客户端回调可能因为关闭页面、网络问题等根本没触发，webhook 是唯一可靠的"支付最终状态"来源。见 [webhooks.md](webhooks.md)。

## Checkout Session（推荐的默认路径）

**Endpoint**: `POST /v1/checkout/sessions`

如果不需要完全自定义的支付表单、只是要一个能收款/收订阅费的页面，这是当前官方推荐的默认入口，比手搭 PaymentIntents + Elements 代码量小很多。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `mode` | enum | 是 | `payment`（一次性）/ `subscription`（订阅，配合 recurring price）/ `setup`（只保存支付方式不收款） |
| `line_items` | array | 是（`payment`/`subscription` 模式） | 每项含 `price`（已创建的 Price ID）和 `quantity`，或用 `price_data` 现场指定金额 |
| `success_url` / `cancel_url` | string | 视集成方式而定 | 完成 / 取消后跳转地址 |
| `ui_mode` | enum | 否 | `hosted`（默认，Stripe 托管整页）/ `embedded`（嵌入页面）/ `elements`（配合 Payment Element 完全自控 UI 但仍由 Checkout Session 驱动确认） |

**示例请求**

```bash
curl https://api.stripe.com/v1/checkout/sessions \
  -u "$STRIPE_TEST_SECRET_KEY:" \
  --data-urlencode "success_url=https://example.com/success" \
  -d "line_items[0][price]=price_xxx" \
  -d "line_items[0][quantity]=1" \
  -d mode=payment
```

响应里的 `url` 字段是可以直接跳转过去的 Stripe 托管收银台地址（`ui_mode=hosted` 时）。Checkout Session 完成后会触发 `checkout.session.completed` webhook 事件，用它来做发货/开通逻辑，而不是只依赖前端跳回 `success_url`（客户可能关闭页面、篡改跳转）。

本 skill 不深入 Checkout Session 的全部配置项（税费、折扣、自定义字段等超出核心支付流程范围），需要时查 [Stripe Checkout Sessions API reference](https://docs.stripe.com/api/checkout/sessions/create.md)。

## 金额与货币：全平台最常见的 100 倍错误

**所有 API 请求里的 `amount` 都是目标货币最小单位的整数，不是小数金额。**

- 两位小数货币（USD、EUR 等多数货币）：`amount=1000` = $10.00，不是 $1000.00，也不能直接传 `amount=10.00`。
- **零小数货币**（zero-decimal，如 JPY、KRW 等）：不用再乘 100，整数本身就是金额。`amount=500` 对 JPY 就是 ¥500。完整零小数货币清单见 [Stripe 货币文档](https://docs.stripe.com/currencies.md#zero-decimal)，清单可能随时间变化，生成代码时不要硬编码清单本身，而是引用官方文档或用 SDK 里的当前定义。
- **特例货币**（ISK、HUF、UGX、TWD）：charge 仍按两位小数处理，但 payout（打款）按零小数处理且金额必须能被 100 整除——这四个货币在 charge 和 payout 两个场景下的取整规则不一致，容易漏。
- 最小金额限制：约合 $0.50 美元等值（具体换算按 charge 货币），超过限制会报错。最大支持 8 位数字（约 999,999.99 美元这个量级）。

**代码生成检查清单**：任何"把用户输入的价格转成 Stripe amount"的代码，都要先确认目标货币是否零小数，再决定要不要乘 100；不能对所有货币统一硬编码 `× 100`。

## 测试卡号

完整列表见 [Stripe 测试文档](https://docs.stripe.com/testing.md)，这里列最常用的一部分（⚠ 文档原文，未实测）：

| 用途 | 卡号 | PaymentMethod 简写 |
|---|---|---|
| 通用成功（Visa） | `4242 4242 4242 4242` | `pm_card_visa` |
| 通用拒付 | `4000000000000002` | `pm_card_visa_chargeDeclined` |
| 余额不足拒付 | `4000000000009995` | `pm_card_visa_chargeDeclinedInsufficientFunds` |
| CVC 错误拒付 | `4000000000000127` | `pm_card_chargeDeclinedIncorrectCvc` |
| 过期卡拒付 | `4000000000000069` | `pm_card_chargeDeclinedExpiredCard` |

有效期用任意未来日期、CVC 用任意 3 位数字（Amex 用 4 位）即可。**写测试代码时用 `payment_method=pm_card_visa` 这种 PaymentMethod 简写而不是裸卡号**——官方原文明确说不建议在服务端代码里直接传卡号，即便是在测试环境，因为这样写的代码上线后容易变成 PCI 不合规的写法（服务端不应该经手真实卡号）。

**绝不能在测试里使用真实卡号**，Stripe 服务协议禁止用真实卡信息在 live 模式测试。所有验证只用测试模式 key + 上表测试卡号进行。

## 幂等与重试

创建 PaymentIntent 这类会产生实际业务后果的 `POST` 请求，重试时必须带同一个 `Idempotency-Key`，避免网络超时后裸重试造成重复扣款。完整机制见 [idempotency-and-retries.md](idempotency-and-retries.md)。
