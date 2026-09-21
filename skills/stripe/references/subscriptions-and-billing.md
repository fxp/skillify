# Subscriptions 与 Billing 基础

> ⚠ 本文件全部内容转录自 docs.stripe.com（抓取于 2026-09-21），未经真实 API 调用验证。Billing 是 Stripe 里最复杂的能力域之一（试用期、按量计费、Schedule、税费联动……），本文件只覆盖"创建一个标准订阅、处理首期扣款、知道该监听哪些事件"这条主线，更复杂的用量计费/多阶段 Schedule 需求请查官方文档。

## 目录

- [核心对象关系](#核心对象关系)
- [创建订阅](#创建订阅)
- [首期扣款怎么处理：payment_behavior](#首期扣款怎么处理payment_behavior)
- [取消与更新](#取消与更新)
- [该监听哪些 webhook 事件](#该监听哪些-webhook-事件)
- [Subscriptions API 专属限流](#subscriptions-api-专属限流)

## 核心对象关系

```
Product（你卖的东西是什么，如"Gold Plan"）
  └─ Price（怎么收费：金额 + 币种 + 计费周期，一个 Product 可以有多个 Price）
       └─ Subscription（把一个 Customer 和一个或多个 Price 绑在一起，按周期生成 Invoice）
            └─ Invoice（每个计费周期生成一张，触发实际扣款）
```

创建订阅前必须先有：一个 `Customer`（建议已经关联好默认支付方式）、一个带 `recurring` 配置的 `Price`。

## 创建订阅

**Endpoint**: `POST /v1/subscriptions`

**前置条件**（⚠ 文档原文给出的典型准备步骤）：
1. 创建 PaymentMethod（或客户端用 Stripe.js 收集）
2. 创建 Customer 并关联该 PaymentMethod，设置为 `invoice_settings.default_payment_method`
3. 创建 Product
4. 创建 Price（挂在这个 Product 下，带 `recurring[interval]`）

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `customer` | string | 是 | — | 订阅的客户 |
| `items` | array | 是 | — | 最多 20 项，每项 `{price: "price_xxx", quantity: N}` |
| `collection_method` | enum | 否 | `charge_automatically` | `charge_automatically`（自动用默认支付方式扣款）/ `send_invoice`（邮件发票，客户手动付款，`days_until_due` 配合使用） |
| `payment_behavior` | enum | 否 | `allow_incomplete` | 决定首期发票扣款失败时怎么处理，见下一节，**这是最容易选错的参数** |
| `trial_period_days` / `trial_end` | integer / timestamp\|"now" | 否 | — | 试用期天数，或直接指定试用结束的具体时间戳 |
| `cancel_at_period_end` | boolean | 否 | `false` | 到当前周期结束时自动取消，而不是立刻取消 |
| `proration_behavior` | enum | 否 | `create_prorations` | 变更计费周期锚点时是否产生按比例调整的发票项，`none` 可以关掉 |

每个客户最多 500 个 active/scheduled 订阅（⚠ 文档原文限制，未实测）。

**示例请求**

```bash
curl https://api.stripe.com/v1/subscriptions \
  -u "$STRIPE_TEST_SECRET_KEY:" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d customer=cus_xxx \
  -d "items[0][price]=price_xxx"
```

**注意事项**

- 用 `send_invoice` 时不要传 `payment_behavior`（它只对 `charge_automatically` 有意义）。
- `price_data`（现场内联指定价格，不用先建 Price 对象）在部分场景可用，适合动态定价，但复杂计费模型建议还是先建 Price。

## 首期扣款怎么处理：payment_behavior

`collection_method=charge_automatically` 时，创建订阅的同一个请求里会**同步尝试完成第一张发票的扣款**。`payment_behavior` 决定扣款失败时订阅处于什么状态：

| 值 | 行为 | ⚠ 适用场景 |
|---|---|---|
| `allow_incomplete`（默认） | 扣款失败 → 订阅状态 `incomplete`；成功 → `active`。这是 2019-03-14 之后的默认行为，用来兼容 SCA/3DS 这类"扣款失败但不是不可恢复"的场景 | 需要处理 3DS 等交互式认证的标准场景 |
| `default_incomplete` | 首期发票需要付款时，**不会自动尝试扣款**，直接创建 `incomplete` 状态的订阅；必须由你显式检索该发票关联的 PaymentIntent 并调用 confirm 才能真正激活订阅 | **本 skill 推荐 Agent/后端集成默认用这个**——扣款这一步完全由你的代码显式触发和控制,不会有"创建订阅的 API 调用副作用里偷偷发生了一次扣款"这种容易被忽略的隐式行为 |
| `error_if_incomplete` | 扣款失败直接返回 HTTP 402，不创建订阅；**不支持**需要用户交互认证（如 3DS）的场景，因为它会直接报错而不是走 `requires_action` | 2019-03-14 前的旧默认值，遗留兼容用，新代码不建议选这个 |
| `pending_if_incomplete` | 仅用于**更新**已有订阅，不能用在创建 | — |

**陷阱**：如果代码里没有显式设置 `payment_behavior`，会落到默认的 `allow_incomplete`，也就是说 `POST /v1/subscriptions` 这一次调用可能已经在背后真实发起了一次扣款尝试——不是"创建了一个之后要手动触发付款的订阅对象"。写"先创建订阅草稿、确认后再扣款"这类流程时，必须显式传 `payment_behavior=default_incomplete`，不能依赖默认值。

## 取消与更新

| 操作 | Method + Path |
|---|---|
| 更新（改价格、加/减 item、改计费周期等） | `POST /v1/subscriptions/{id}` |
| 立刻取消 | `DELETE /v1/subscriptions/{id}` |
| 到周期末取消 | `POST /v1/subscriptions/{id}`，传 `cancel_at_period_end=true` |

⚠ 若给 Agent 配置了 [agent-tagged Restricted Key](auth-and-modes.md#给-agent-用的-key-restricted-key--审批机制)，"取消订阅"是 Stripe 官方默认就会加两方审批规则的敏感操作之一——这也是 Stripe 自己认为这类操作需要人工确认的信号。

## 该监听哪些 webhook 事件

订阅相关的大部分状态变化是异步的（首期扣款、周期续费、试用到期、支付失败重试……），**只靠 API 同步返回值感知不到后续变化，必须监听 webhook**（签名校验方式见 [webhooks.md](webhooks.md)）。高频事件：

| 事件 | 何时触发 | 建议动作 |
|---|---|---|
| `customer.subscription.created` | 订阅创建时；`status` 可能是 `incomplete` | 记录订阅 ID，视 `status` 决定是否已经可以开通服务 |
| `customer.subscription.updated` | 续费、加/减折扣、改价格等几乎所有订阅变更都会触发 | 按需要同步本地状态 |
| `customer.subscription.deleted` | 订阅彻底结束 | 撤销客户的服务/权限 |
| `customer.subscription.trial_will_end` | 试用期结束前 3 天（试用期本身短于 3 天则提前触发） | 提醒客户绑定/确认支付方式 |
| `invoice.paid` | 某期发票成功付款 | 确认 `subscription` 状态为 `active` 后再开通/续期服务，不要只看这个事件本身 |
| `invoice.payment_failed` | 某期发票扣款失败 | 通知客户、可结合 Stripe 的 Smart Retries 自动重试、或引导客户更新默认支付方式 |
| `invoice.payment_action_required` | 首期或续费需要客户完成交互式认证 | 引导客户完成认证，否则订阅会一直卡在 `incomplete`/收不到钱 |

⚠ 文档原文强调：**事件到达顺序不保证**（比如创建订阅可能先收到 `invoice.created` 也可能先收到 `customer.subscription.created`），不要写依赖事件先后顺序的逻辑；用事件的 `id` 去重，而不是用 `created` 时间戳判断顺序或去重（同一批事件可能共享同一秒时间戳）。

## Subscriptions API 专属限流

除全局限流外，Subscriptions API 有自己的专属限制（⚠ 文档原文，未实测）：

- 每个订阅每分钟最多 10 张新发票
- 每个订阅每天最多 20 张新发票
- 每个订阅每小时最多 200 次数量更新

批量脚本操作大量订阅时要注意这几条独立于全局 QPS 限制的资源级限流,详见 [errors-and-limits.md](errors-and-limits.md)。
