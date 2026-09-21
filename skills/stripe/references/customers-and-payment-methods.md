# Customers 与已保存的 PaymentMethod

> ⚠ 本文件全部内容转录自 docs.stripe.com（抓取于 2026-09-21），未经真实 API 调用验证。

## 目录

- [Customer 对象](#customer-对象)
- [创建 Customer](#创建-customer)
- [PaymentMethod：创建与查询](#paymentmethod创建与查询)
- [把 PaymentMethod 关联到 Customer：三种方式怎么选](#把-paymentmethod-关联到-customer三种方式怎么选)
- [SetupIntent：只保存支付方式、不立即收款](#setupintent只保存支付方式不立即收款)

## Customer 对象

`Customer` 代表你业务里的一个客户，用来复用支付方式、追踪同一客户的多笔支付、在 Dashboard 里按客户聚合数据。不是每笔支付都必须关联 Customer——一次性访客支付可以不创建 Customer，但只要涉及"保存支付方式给以后用"（订阅、保存卡），就必须有 Customer。

**核心 endpoint**

| 操作 | Method + Path |
|---|---|
| 创建 | `POST /v1/customers` |
| 查询单个 | `GET /v1/customers/{id}` |
| 更新 | `POST /v1/customers/{id}` |
| 列表 | `GET /v1/customers` |
| 删除 | `DELETE /v1/customers/{id}` |

## 创建 Customer

**Endpoint**: `POST /v1/customers`

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 否 | 客户姓名/公司名，最长 256 字符 |
| `email` | string | 否 | 最长 512 字符，用于 Dashboard 搜索和展示，**不是登录鉴权用途** |
| `payment_method` | string | 否 | 创建时直接关联一个已存在的 PaymentMethod ID |
| `invoice_settings[default_payment_method]` | string | 否 | 指定这个客户的默认支付方式，订阅/发票收款时会优先用它 |
| `balance` | integer | 否 | 客户余额，**同样是最小货币单位的整数**，正数表示客户欠款增加、负数表示信用抵扣 |
| `tax_exempt` | enum | 否 | `none` / `exempt` / `reverse` |
| `metadata` | map | 否 | 自定义键值对 |

**示例请求**

```bash
curl https://api.stripe.com/v1/customers \
  -u "$STRIPE_TEST_SECRET_KEY:" \
  -d "name=Jenny Rosen" \
  --data-urlencode "email=jennyrosen@example.com"
```

```python
customer = client.v1.customers.create(params={
    "name": "Jenny Rosen",
    "email": "jennyrosen@example.com",
})
```

**示例响应**（关键字段，⚠ 文档原文）

```json
{
  "id": "cus_NffrFeUfNV2Hib",
  "object": "customer",
  "email": "jennyrosen@example.com",
  "name": "Jenny Rosen",
  "invoice_settings": {
    "default_payment_method": null
  },
  "livemode": false,
  "metadata": {}
}
```

**注意事项**

- `source` 参数（用 Token/Sources API 创建来源）是**遗留写法**，⚠ 文档原文明确说明——新集成应该用 PaymentMethod + `payment_method` 参数，不要用 `source`。
- Customer 的 `id`（`cus_...`）跟其他所有 Stripe 对象一样受 [test/live 模式隔离](auth-and-modes.md#test-模式-vs-live-模式两个完全隔离的世界) 约束。

## PaymentMethod：创建与查询

`PaymentMethod` 代表一种具体的支付方式（一张卡、一个银行账户……），可以独立创建、也可以在确认 PaymentIntent 时用 `payment_method_data` 现场生成。

**Endpoint**: `POST /v1/payment_methods`

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | enum | 是 | `card`、`us_bank_account`、`sepa_debit`……几十种，完整枚举见 API reference，和 PaymentIntent 的 `payment_method_types` 共享同一套枚举值 |
| `card` / `us_bank_account` / … | object | 视 `type` 而定 | 与 `type` 同名的字段，装该类型专属的详细信息（卡号、路由号等） |
| `billing_details` | object | 否 | 持卡人姓名、地址、邮箱、电话 |

⚠ 文档原文明确提示：**不建议直接调这个 endpoint 用裸卡号在服务端创建 PaymentMethod**，正常前端集成应该用 Stripe.js 在客户端完成（避免服务端经手卡信息、保持 PCI 合规），后端直接调用主要用于 `us_bank_account` 之类不涉及 PCI 范围的支付方式,或测试场景。

## 把 PaymentMethod 关联到 Customer：三种方式怎么选

这是一个容易被 API 表面相似度误导的地方——三个 endpoint 看起来都能达到"客户以后能用这张卡"的效果，但只有其中一部分是官方推荐路径：

| 方式 | Endpoint | 官方态度 |
|---|---|---|
| 直接 attach | `POST /v1/payment_methods/{id}/attach`（body 带 `customer=`） | ⚠ **文档原文明确不推荐**：不经过 SetupIntent/PaymentIntent 就直接 attach，不会做"为未来复用优化"的必要步骤（比如某些卡网络要求的额外校验），会导致以后用这张卡扣款时**拒付率和认证摩擦更高**。仅用于确实不需要那些优化的场景 |
| 通过 PaymentIntent 的 `setup_future_usage` | `POST /v1/payment_intents`（收一笔款的同时保存支付方式） | **推荐**：客户本来就要付一笔钱，同时想保存卡以后用，见 [accepting-payments.md](accepting-payments.md) |
| 通过 SetupIntent | `POST /v1/setup_intents` | **推荐**：客户当下不需要付款，只是要先保存支付方式（比如注册时预先绑卡、免费试用期不扣款），见下一节 |

设置某个 PaymentMethod 为订阅/发票的默认支付方式，用 `POST /v1/customers/{id}` 更新 `invoice_settings[default_payment_method]`。

## SetupIntent：只保存支付方式、不立即收款

**用途**：和 PaymentIntent 平行的另一个对象，专门用于"这次不收款，只是要把支付方式安全地保存下来，确保以后代扣时能用、认证摩擦最小"的场景（免费试用、延迟开始的订阅、企业客户预先登记付款方式）。

**核心 endpoint**

| 操作 | Method + Path |
|---|---|
| 创建 | `POST /v1/setup_intents` |
| 确认 | `POST /v1/setup_intents/{id}/confirm` |
| 查询 | `GET /v1/setup_intents/{id}` |

**关键参数**（create）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `customer` | string | 否 | 关联的 Customer，确认成功后 PaymentMethod 会 attach 到这个客户 |
| `payment_method_types` | array | 否 | 允许的支付方式类型，语义同 PaymentIntent |
| `usage` | enum | 否 | `on_session` / `off_session`，语义同 PaymentIntent 的 `setup_future_usage` |

流程和 PaymentIntent 平行：create → （客户端用 Stripe.js 收集支付方式）→ confirm → 如需要额外认证转 `requires_action` → 完成后 PaymentMethod 自动关联到指定 Customer，且已经过"为未来复用优化"的必要步骤（与上面提到的直接 `/attach` 的差异正是这里）。

**和 PaymentIntent 的 `setup_future_usage` 的取舍**：如果这次交互客户本来就要付一笔钱，用 PaymentIntent + `setup_future_usage` 一步到位；如果这次完全不收款，用 SetupIntent。两者都不要退回到直接调用 `/attach` 或使用 Sources API。
