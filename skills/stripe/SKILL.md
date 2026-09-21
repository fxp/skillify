---
name: stripe
description: 接入 Stripe API（api.stripe.com，docs.stripe.com/api）的开发者手册——涵盖鉴权与 test/live 模式隔离、PaymentIntents 支付流程与 Checkout Sessions 的选型、Customers 与已保存的 PaymentMethod、Subscriptions/Billing、webhook 事件与 Stripe-Signature 签名校验、幂等重试（Idempotency-Key）、错误码与限流。当用户提到 "Stripe""stripe.com""api.stripe.com""stripe-python""stripe-node""@stripe/stripe-js""PaymentIntent""Checkout Session""webhook 签名校验""集成 Stripe 支付/订阅"，或要求写代码调用上述任意能力时，应主动使用本技能，不要凭记忆编造参数名或字段结构，也不要把训练数据里旧版 Charges API 的写法当成当前推荐方案。本技能仅用于生成/审查集成代码，不用于授权任何 Agent 自主转移真实资金——涉及真实金钱操作前必须由人确认，且任何验证只能用 Stripe 测试模式（test mode）密钥和测试卡号进行，绝不能用 live 密钥。
---

# Stripe API 接入指南

Stripe 是主流的在线支付与账单基础设施，REST API 以 `https://api.stripe.com` 为 base URL，围绕 PaymentIntent（支付）、Customer（客户）、PaymentMethod（支付方式）、Subscription/Invoice（订阅与账单）等资源展开。本 skill 聚焦「Agent/开发者集成支付」最核心的一条主线：鉴权 → 发起并确认一笔支付 → 保存客户与支付方式 → （可选）订阅计费 → 用 webhook 可靠地知道结果，并贯穿两条几乎所有 payment API 特有、通用开发直觉容易漏掉的规则：**幂等重试** 和 **webhook 签名校验**。

Connect（多方平台分账）、Tax、Issuing、Terminal、Capital、Crypto、Climate、Identity、Financial Connections、Radar 高级规则等专项能力不在本 skill 覆盖范围内，文档见 docs.stripe.com 对应目录。

## ⚠ 验证状态

**本 skill 目前没有真实 Stripe API Key，第 3、4 步（真实调用验证、对照实验）尚未执行。** 全部内容来自 2026-09-21 抓取的 docs.stripe.com 官方文档（Markdown 导出 + `stripe/openapi` 仓库的 OpenAPI 规范），**没有任何一条结论经过真实 API 调用验证**。字段名、必填/可选、报错文案、状态码全部是「文档原文转录」，可能存在文档本身的错漏、过时内容，或者 Markdown 导出丢失的表格/示例。每个 reference 文件顶部和具体报错/行为描述处都重复标注了 `⚠ 文档原文，未实测`。

**有 key 之后的验证计划见 `stripe-workspace/verification-plan.md`**，按优先级列出了要用真实测试模式调用核实的结论清单。验证完成前，任何基于本 skill 生成的代码在合入生产前都应该先在 Stripe 测试模式里跑通。

### ⚠⚠ 真实资金安全边界（务必遵守）

1. **本 skill 是「帮 Agent / 开发者写对集成代码」的文档参考，不是「授权 Agent 自主花钱」的许可。** 任何会创建真实收费、退款、订阅变更的代码，在连接 live 环境前必须有人明确确认。
2. **后续对本 skill 的任何真实调用验证，只能使用 Stripe 测试模式（sandbox）密钥**：`sk_test_...` / `rk_test_...`，配合 [Stripe 官方测试卡号](https://docs.stripe.com/testing.md)（如 `4242 4242 4242 4242`）。**绝不能使用 `sk_live_...` / `rk_live_...` 等 live 密钥做验证**，也不能在验证脚本里传入真实持卡人信息。
3. **给 Agent 用的 key 该怎么配（Stripe 官方推荐，未实测但是文档明确写的架构建议）**：用 [受限密钥（Restricted API Key，`rk_...`）](https://docs.stripe.com/keys/restricted-api-keys.md) 而不是无限制的 `sk_...`，创建时在 Dashboard 勾选「Authorizing agent access to your account」把它标记为 *agent-tagged key*。Stripe 会自动对这类 key 发起的敏感操作（默认覆盖创建退款、取消订阅；可自行加上创建 PaymentIntent、修改银行账户等）启用 [两方审批规则](https://docs.stripe.com/account/approvals.md)：Agent 发起的敏感请求会先返回 `approval_required`，由指定的人工审核者批准后才真正生效。这是把「Agent 集成 Stripe」和「Agent 能无监督转移真实资金」解耦的官方机制，本 skill 建议任何生产环境的 Agent 集成都采用这个架构，而不是把无限制的 `sk_live_` 直接交给 Agent。

## 用之前先确认 3 件事

1. **Base URL 固定为 `https://api.stripe.com/v1`**（部分较新资源如 event destinations、approval requests 挂在 `/v2` 下，且 `/v2` 请求需要额外带 `Stripe-Version` header，见 [references/webhooks.md](references/webhooks.md)）。
2. **鉴权精确格式**：把密钥作为 HTTP Basic Auth 的 **用户名**、密码留空 —— `curl -u sk_test_xxx:`（冒号不能少）；或者用 `Authorization: Bearer sk_test_xxx`（跨域请求场景用这个）。**没有 `X-Api-Key` 之类的自定义 header**，也不需要额外传 account ID（除非用 Connect）。详见 [references/auth-and-modes.md](references/auth-and-modes.md)。
3. **test 和 live 是两套完全隔离的数据世界，不是同一份数据的两种查看方式**：`sk_test_...` 创建的 `cus_...`、`pi_...`、`sub_...` 等对象 ID，换成 `sk_live_...` 去查询/操作会直接失败（反之亦然）；且这两种 ID 的字符串格式长得一模一样，光看 ID 本身分辨不出它是哪个模式创建的，必须靠「这个 ID 是哪个 key 返回的」来追踪。这是一个新手极易踩、且不会在代码审查里被发现的坑。详见 auth-and-modes.md。

## 30 秒跑通第一个请求

用测试模式密钥创建一个 PaymentIntent（不会产生真实费用，`sk_test_` 只能操作 sandbox 数据）：

```bash
curl https://api.stripe.com/v1/payment_intents \
  -u "$STRIPE_TEST_SECRET_KEY:" \
  -d amount=2000 \
  -d currency=usd \
  -d "automatic_payment_methods[enabled]=true"
```

`amount=2000` 是「2000 美分」也就是 $20.00 —— **金额永远是目标货币的最小单位的整数**，不是小数金额，这是全平台最容易踩的坑，见下方通用规则第 1 条。

## 能力域导航

| 我想做什么 | 参考文件 | 涉及的核心 endpoint |
|---|---|---|
| 搞清楚鉴权格式、test/live 隔离、Agent 该用什么 key | [references/auth-and-modes.md](references/auth-and-modes.md) | — |
| 接一笔支付（选 Checkout Sessions 还是 PaymentIntents、创建/确认/3DS） | [references/accepting-payments.md](references/accepting-payments.md) | `POST /v1/checkout/sessions`、`POST /v1/payment_intents`、`POST /v1/payment_intents/:id/confirm` |
| 创建/查询客户、保存并复用支付方式 | [references/customers-and-payment-methods.md](references/customers-and-payment-methods.md) | `POST /v1/customers`、`POST /v1/payment_methods`、`POST /v1/payment_methods/:id/attach`、`POST /v1/setup_intents` |
| 订阅制计费（创建订阅、处理首期扣款、账单事件） | [references/subscriptions-and-billing.md](references/subscriptions-and-billing.md) | `POST /v1/subscriptions`、`GET/POST /v1/subscriptions/:id`、`POST /v1/subscriptions/:id`（取消/更新） |
| 接收并**安全地**处理 Stripe 事件（webhook） | [references/webhooks.md](references/webhooks.md) | 你自己的 HTTPS 端点 + `Stripe-Signature` header 校验 |
| 给创建类请求加幂等键，安全地重试 | [references/idempotency-and-retries.md](references/idempotency-and-retries.md) | 所有 `POST` |
| 处理错误响应、卡拒付、限流 | [references/errors-and-limits.md](references/errors-and-limits.md) | — |

导航表覆盖了本 skill 的全部内容；不在表里的能力域（Connect、Tax、Issuing、Terminal 等）本 skill 不覆盖。

## 跨领域的通用规则（写代码前必读）

1. **金额是目标货币最小单位的整数，不是小数**。`amount=1099` 对 USD 是 $10.99，不是 $1099 也不是 $10.99 本身当整数传。少数货币是 **零小数货币**（zero-decimal，如 JPY、KRW），此时整数值本身就是金额，不用再乘 100（`amount=500` 就是 ¥500）；ISK/HUF/UGX/TWD 又是特例（对 payout 按零小数处理但 charge 仍按两位小数）。完整表见 [Stripe 货币文档](https://docs.stripe.com/currencies.md)。**这是全平台最经典的 100 倍错误来源**，任何生成金额的代码都要显式确认目标货币是否零小数。

2. **Stripe 当前推荐的「首选支付集成方式」已经发生过迁移，而且抓取时（2026-09）确认又变了一次，不是训练数据里可能记得的版本**：
   - 早期：Charges API（`POST /v1/charges`，直接传卡号）——**已废弃**，不要在新集成里使用。
   - 中期成为主流、也是多数训练语料里"现代"的答案：PaymentIntents API 直接建 + Stripe.js/Elements 手动确认。
   - **Stripe 当前（本次抓取的 llms.txt 与 `payments/payment-intents.md` 原文）的默认推荐是 Checkout Sessions API 配合 Payment Element**，官方原文（未实测，文档转录）：多数集成场景应优先用 Checkout Sessions，只有用户明确要求、或要用 Checkout Sessions 覆盖不到的「deferred PaymentIntent + Elements」这类自定义流程时，才直接手搭 PaymentIntents + Elements，因为后者代码量明显更大。
   - 本 skill 的 [accepting-payments.md](references/accepting-payments.md) 按用户需求范围详细覆盖的是 **PaymentIntents 这条底层 API 路径**（Agent/后端集成经常需要直接调这一层），但生成代码前要先确认：如果只是"接一个标准的收银台/订阅收款页"，现在的默认答案是 Checkout Sessions，不是手搭 PaymentIntents。
   - **Sources API、Tokens API 均已过时**，保存客户支付方式一律用 SetupIntent 或 PaymentMethod + PaymentIntent.setup_future_usage，不要用 Sources。

3. **webhook 端点收到的每一个 POST 请求，验证 `Stripe-Signature` header 之前都当成不可信输入**——不验证签名等于任何人都能伪造一个 `payment_intent.succeeded` 事件打到你的端点上，让你的系统误以为收到了钱、发货、开通服务。这不是"最佳实践建议"级别的问题，是能直接导致资金损失的安全漏洞，必须放在 SKILL 这一层反复强调。验证需要**原始未解析的请求体**，很多框架的默认中间件会在验证之前就把 body 解析/改写掉导致验证必然失败，这也是文档里点名的常见错误。详见 webhooks.md。

4. **所有创建类 `POST` 请求（尤其是创建 PaymentIntent/Subscription/Refund 这类和钱直接挂钩的）在重试时都要带同一个 `Idempotency-Key`**。网络超时时你不知道 Stripe 到底有没有处理这次请求，裸重试有真实的双重扣款风险；带上幂等键后，重试会安全地拿到第一次请求的结果而不是再执行一次。`GET`/`DELETE` 本身幂等，不需要也不应该带这个 header。详见 idempotency-and-retries.md。

5. **Restricted API Key（`rk_...`）优先于无限制的 Secret Key（`sk_...`）**，尤其是把 key 交给 Agent 使用的场景；Agent 用的 key 建议在创建时标记为 agent-tagged 以启用 Stripe 官方的两方审批机制。详见 auth-and-modes.md 与本文件上方的「真实资金安全边界」。

6. **官方 SDK**：Python 包名 `stripe`（`pip install stripe`），Node 包名 `stripe`（`npm install stripe`），此外还有 Ruby/PHP/Java/Go/.NET 的官方库。**不要在代码里写死具体版本号**——Stripe 自己的 Agent 集成指引原话（未实测，文档转录）是任何时候都应该先查 npm/PyPI 当前版本或直接用 `@latest` / 不锁版本安装，而不是用训练数据里记住的旧版本号。新版 SDK 推荐用 `StripeClient` 实例化方式（如 Python 的 `client = stripe.StripeClient(api_key)`）而不是设置全局 `stripe.api_key = ...`，Node 目前仍以 `const stripe = require('stripe')(key)` 工厂函数为主。

## 目录结构

```
stripe/
├── SKILL.md
├── references/
│   ├── auth-and-modes.md              鉴权、test/live 隔离、Agent key 与审批机制
│   ├── accepting-payments.md          Checkout Sessions vs PaymentIntents、创建/确认、3DS、金额
│   ├── customers-and-payment-methods.md  Customer、PaymentMethod、SetupIntent、保存卡
│   ├── subscriptions-and-billing.md   Subscription/Price/Invoice、首期扣款、账单事件
│   ├── webhooks.md                    事件类型、Stripe-Signature 签名校验（含手写算法）
│   ├── idempotency-and-retries.md     Idempotency-Key 精确语义、500/网络错误怎么重试
│   └── errors-and-limits.md           HTTP 状态码、error 对象字段、拒付码、限流
└── evals/
    └── evals.json                     5 个「有经验的开发者会凭直觉写错」的对照场景（未跑，见 stripe-workspace/verification-plan.md）
```

内容整理自 `docs.stripe.com`（llms.txt + API reference Markdown 导出）与 `github.com/stripe/openapi` 的 OpenAPI 规范，抓取于 **2026-09-21**。真实调用报错优先信任 API 本身，其次信任本 skill 标注了验证日期的条目；未标验证日期的一切内容都按「文档原文，可能过时或有误」对待。
