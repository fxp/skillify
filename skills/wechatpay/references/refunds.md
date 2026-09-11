# 退款：申请、查询、异常退款

> 来源：`pay.weixin.qq.com/doc/v3/merchant/` 下 4013071036（申请退款）、4013071041（查询单笔退款）、4013071193（发起异常退款）、
> 4013071031（开发指引与状态流转）、4014959631（退款最佳实践）、4013071200（FAQ），抓取于 2026-09-11。
> 五种支付产品的退款接口是同一组。退款结果回调见 `notifications.md`。
>
> **验证状态**：没有用真实凭证调用过。错误码、频率限制、行为描述都是文档原文，未实测。
> 无凭证探测（2026-09-11）：不带 Authorization 调 `POST /v3/refund/domestic/refunds`，返回
> `401 {"code":"SIGN_ERROR","message":"Http头Authorization值格式错误，请参考《微信支付商户REST API签名规则》"}`，说明 path 存在。

## 目录
1. [退款单状态机](#1-退款单状态机)
2. [申请退款](#2-申请退款)
3. [查询单笔退款](#3-查询单笔退款)
4. [重试与幂等：唯一安全的写法](#4-重试与幂等唯一安全的写法)
5. [发起异常退款](#5-发起异常退款)
6. [错误码](#6-错误码)
7. [FAQ 里的坑](#7-faq-里的坑)

---

## 1. 退款单状态机

```
申请退款受理成功
      │
      ▼
 PROCESSING ──退款成功──────────────────────────▶ SUCCESS（终态）
      │ ├──受理超过 7 天且商户账户资金不足────────▶ CLOSED（终态，退款失败）
      │ └──原路退回失败（卡作废/冻结）且零钱也已注销──▶ ABNORMAL
      │                                               │
      └──────────────────────────────────  发起异常退款 / 商户平台手动处理成功 ──▶ SUCCESS
```

- 「申请退款」接口返回 200，**只代表退款单被受理了**，不代表钱已经退了。结果以退款回调或查询退款为准（4013071036）。
- 原路退回失败时，微信支付会**先尝试退到用户零钱**。只有零钱也注销了，才会进入 `ABNORMAL`（4013071031）。
- `CLOSED` 就是退款失败。如果还要退，**换一个新的 `out_refund_no`** 重新申请（FAQ）。
- 到账时间：零钱支付的订单一般 5 分钟内到账；银行卡支付的一般 1–3 个工作日（4013071041）。

## 2. 申请退款

**Endpoint**: `POST /v3/refund/domestic/refunds`
**用途**：对支付成功的订单做全额或部分退款，原路退回。

**关键限制（文档原文）**
- 只能退**支付成功后 365 天内**的订单。超期会返回 `TRADE_OVERDUE`（FAQ）。
- 一笔订单最多做 **50 次**部分退款。多次部分退款要**换新的商户退款单号，并且间隔 1 分钟**。
- 申请失败后重试时，**必须用原来的商户退款单号**，否则可能重复退款。
- 频率限制：同一商户号，调用成功的请求 150 QPS，调用失败（报错）的请求 **6 QPS**。
- 只有查单确认订单是 `SUCCESS` 才能发起退款（4014959631）。未付款的订单退款会报 `RESOURCE_NOT_EXISTS`。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `transaction_id` | string(32) | 二选一 | 微信支付订单号 |
| `out_trade_no` | string(32) | 二选一 | 商户订单号。和 `transaction_id` **必须传一个** |
| `out_refund_no` | string(64) | 是 | 商户退款单号，只能是数字、大小写字母和 `_-|*@`。**同一个退款单号请求多次，只会退一笔** |
| `reason` | string(80) | 否 | 退款原因，会显示在给用户的退款消息里。退款金额 ≤1 元且是部分退款时不显示 |
| `notify_url` | string(256) | 否 | 退款结果回调地址。传了就优先用它，商户平台上配的退款回调地址不再生效。**建议总是传**，原因见 §7 |
| `funds_account` | string | 否 | `AVAILABLE`（只适用于旧资金流商户）/ `UNSETTLED`（只适用于出行预付押金退款） |
| `amount.refund` | integer | 是 | 退款金额，**分**，不能超过原订单支付金额 |
| `amount.total` | integer | 是 | **原订单金额**，分。退款请求里这一项也必须传 |
| `amount.currency` | string(16) | 是 | 固定 `CNY`（下单时这一项是选填，**退款时是必填**） |
| `amount.from[]` | array | 否 | 指定从哪些账户出资（`account`: `AVAILABLE` / `UNAVAILABLE`，`amount`），分账订单才用 |
| `goods_detail[]` | array | 否 | 按商品退款时才传：`merchant_goods_id`、`unit_price`、`refund_amount`、`refund_quantity`… |

**示例请求**

```bash
curl -X POST https://api.mch.weixin.qq.com/v3/refund/domestic/refunds \
  -H 'Authorization: WECHATPAY2-SHA256-RSA2048 mchid="1230000109",...' \
  -H 'Accept: application/json' -H 'Content-Type: application/json' -A 'my-shop-backend/1.0' \
  -d '{"out_trade_no":"1217752501201407033233368018","out_refund_no":"R1217752501201407033233368018","reason":"商品已售完","notify_url":"https://shop.example.com/wechatpay/refund-notify","amount":{"refund":3000,"total":10000,"currency":"CNY"}}'
```

```python
from wechatpay_v3 import request

def apply_refund(out_trade_no: str, out_refund_no: str, refund_fen: int, total_fen: int, reason: str | None = None) -> dict:
    payload = {
        "out_trade_no": out_trade_no,
        "out_refund_no": out_refund_no,                          # 调用前先落库，重试一律复用它
        "notify_url": "https://shop.example.com/wechatpay/refund-notify",
        "amount": {"refund": refund_fen, "total": total_fen, "currency": "CNY"},
    }
    if reason:
        payload["reason"] = reason
    return request("POST", "/v3/refund/domestic/refunds", payload=payload)
```

**应答字段（节选）**

| 字段 | 说明 |
|---|---|
| `refund_id` | 微信支付退款单号。**发起异常退款时要用它** |
| `out_refund_no` / `transaction_id` / `out_trade_no` | —— |
| `channel` | `ORIGINAL`（原路退回）/ `BALANCE`（退回余额）/ `OTHER_BALANCE`（原账户异常，退到其他余额账户）/ `OTHER_BANKCARD`（原卡异常，退到其他银行卡） |
| `user_received_account` | 退款入账账户的描述，例如「招商银行信用卡」「支付用户零钱」 |
| `status` | `SUCCESS` / `CLOSED` / `PROCESSING` / `ABNORMAL` |
| `success_time` | status 为 SUCCESS 时才返回 |
| `create_time` | 退款受理时间 |
| `funds_account` | `UNSETTLED` / `AVAILABLE` / `UNAVAILABLE` / `OPERATION` / `BASIC` / `ECNY_BASIC` |
| `amount.refund` / `total` / `payer_total` / `payer_refund` / `settlement_refund` / `settlement_total` / `discount_refund` / `refund_fee` | 全部是**分**。`payer_refund` 是用户实际收到的现金；用了代金券时它会小于 `refund` |
| `promotion_detail[]` | 代金券退款明细 |

**示例响应（节选）**

```json
{"refund_id": "50000000382019052709732678859", "out_refund_no": "1217752501201407033233368018",
 "transaction_id": "1217752501201407033233368018", "out_trade_no": "1217752501201407033233368018",
 "channel": "ORIGINAL", "user_received_account": "招商银行信用卡", "status": "SUCCESS",
 "create_time": "2020-12-01T16:18:12+08:00", "funds_account": "UNSETTLED",
 "amount": {"total": 100, "refund": 100, "payer_total": 90, "payer_refund": 90, "currency": "CNY"}}
```

**手续费**（FAQ 4013071200）：退款时手续费按比例退还。例如 100 元订单、费率 0.6%，退 50 元：从商户账户扣 49.7 元，微信退还 0.3 元手续费，用户一共收到 50 元。

## 3. 查询单笔退款

**Endpoint**: `GET /v3/refund/domestic/refunds/{out_refund_no}`
**用途**：确认退款单是否受理、现在是什么状态。**没有时间限制**，任何退款单都能查（FAQ）。

**关键参数**：只有 path 参数 `out_refund_no`（string(64)，必填）。文档没有列 `mchid` query 参数，这一点和查单接口不同。

```python
def query_refund(out_refund_no: str) -> dict:
    return request("GET", f"/v3/refund/domestic/refunds/{out_refund_no}")
```

应答字段和申请退款的应答一样。

**文档建议的轮询节奏**：每隔 1 分钟查一次；超过 5 分钟还是 `PROCESSING`，就逐步拉长间隔（5 分钟、10 分钟、20 分钟、30 分钟…）。
查询频率限制是同一商户号 300 QPS，遇到 `FREQUENCY_LIMITED` 就隔 1 分钟再查。

## 4. 重试与幂等：唯一安全的写法

文档最佳实践（4014959631）：申请退款的应答**只要不是 200 OK**（包括超时、429、500），**先查退款单，再决定下一步**：

```python
import requests
from wechatpay_v3 import WechatPayError

def refund_safely(out_trade_no, out_refund_no, refund_fen, total_fen):
    try:
        return apply_refund(out_trade_no, out_refund_no, refund_fen, total_fen)
    except (WechatPayError, requests.RequestException) as e:
        if isinstance(e, WechatPayError) and e.code in ("NOT_ENOUGH", "USER_ACCOUNT_ABNORMAL", "INVALID_REQUEST"):
            raise                                  # 明确失败：NOT_ENOUGH 充值后可以原单原参数重试；另外两个要人工处理
    try:
        return query_refund(out_refund_no)         # 查得到（只要不是 CLOSED）就说明已经受理了，按 status 继续处理
    except WechatPayError as e:
        if e.code == "RESOURCE_NOT_EXISTS":        # 没受理：用原单原参数重试，这样做是幂等的
            return apply_refund(out_trade_no, out_refund_no, refund_fen, total_fen)
        raise
```

- **绝对不要**因为超时就换一个新的 `out_refund_no` 重试。换单号就是新的一笔退款，可能退两次钱。
- `429 FREQUENCY_LIMITED` 的官方说明是「该笔退款为受理中，请调用查单接口确认或降低频率原单重试，重试请勿更换单号」。
  HTTP 状态码页（4012081717）也说：退款场景下的 429「并非明确的未受理」，要先查询。
- 应用程序**不能靠 message 做自动化分支**（最佳实践原文：「错误描述可能因业务调整而发生变更」）。

## 5. 发起异常退款

**Endpoint**: `POST /v3/refund/domestic/refunds/{refund_id}/apply-abnormal-refund`
**用途**：退款单状态是 `ABNORMAL` 时，把钱退到用户的其他银行卡，或者退到商户自己的银行账户（再由商户线下退给用户）。也可以在商户平台 → 交易中心手动处理。

**关键参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `refund_id` | path | string(32) | 是 | **微信支付退款单号**（不是 `out_refund_no`） |
| `out_refund_no` | body | string(64) | 是 | 商户退款单号 |
| `type` | body | string | 是 | `USER_BANK_CARD`（退到用户银行卡）/ `MERCHANT_BANK_CARD`（退到交易商户的银行账户） |
| `bank_type` | body | string(16) | 退到用户时必填 | 银行类型，只支持指定的 15 家银行的借记卡（招行、交行、农行、建行、工行、中行、平安、浦发、中信、光大、民生、兴业、广发、邮储、宁波银行） |
| `bank_account` | body | string(1024) | 退到用户时必填 | 银行卡号，**必须先用微信支付公钥（或平台证书）加密**，见 `auth-signing.md` §7 |
| `real_name` | body | string(1024) | 退到用户时必填 | 收款用户姓名，**同样要加密** |

- 带了加密字段的请求，**必须加上 `Wechatpay-Serial` 请求头**，值是加密用的公钥 ID 或平台证书序列号。
- 频率限制 150 QPS（文档原文）。
- 应答结构和申请退款的应答一样；异常退款成功后，`channel` 会是 `OTHER_BANKCARD`。
- 这个接口的业务错误码本 skill 没有抄录，见文档页 4013071193。

## 6. 错误码

申请退款（4013071036，文档原文，未实测）：

| HTTP | code | 含义 | 处理 |
|---|---|---|---|
| 400 | `INVALID_REQUEST` | 格式没问题，但不符合业务规则，退款申请失败 | 看 message，例如「您的请求参数与订单信息不一致」→ 核对订单号、商户号 |
| 401 | `SIGN_ERROR` | 签名错误 | `auth-signing.md` §9 |
| 403 | `NOT_ENOUGH` | 商户账户余额不足，退款申请失败 | 充值后**原单原参数**重试 |
| 403 | `USER_ACCOUNT_ABNORMAL` | 用户账号异常（例如已注销），退款申请失败 | 商户自行线下处理 |
| 404 | `MCH_NOT_EXISTS` | 商户号不存在 | 注意：下单接口里这个码是 400，这里是 404 |
| 404 | `RESOURCE_NOT_EXISTS` | 订单号不存在，或者订单还没付款 | 核对订单 |
| 429 | `FREQUENCY_LIMITED` | 频率限制，**这笔退款可能正在受理中** | 先查退款单，再原单重试，**不要换单号** |
| 500 | `SYSTEM_ERROR` | 系统超时 | **不要换**商户退款单号，用相同参数再调一次 |

查询单笔退款：`401 SIGN_ERROR`、`404 MCH_NOT_EXISTS`、`404 RESOURCE_NOT_EXISTS`（退款单不存在）、`500 SYSTEM_ERROR`。

FAQ 里还提到下面几个（HTTP 状态码没写，⚠ 文档未说明）：`TRADE_OVERDUE`（超过一年）、`REFUND_FEE_MISMATCH`（订单金额或退款金额和之前的请求不一致）、
「当前使用此业务的用户较多，请稍后再试」（系统繁忙）。

## 7. FAQ 里的坑

- **会收到 XML 格式的退款回调**（FAQ）：两种情况下，微信支付会发 **v2 的 XML 格式**退款通知：一是退款是用 v2 接口发起的；
  二是**调用 v3 申请退款时没传 `notify_url`，而商户平台「交易中心 → 退款管理 → 退款配置」里配了回调地址**。
  另外，在商户平台上手动操作的退款，回调也是 v2 XML 格式。所以 v3 退款**总是显式传 `notify_url`**，
  回调处理代码也要能识别并记录「不是 JSON」的请求，而不是直接崩掉。
- 如果接口里没传 `notify_url`，商户平台上也没配，**就不会有退款回调**（4012075420）。
- ⚠ 文档自相矛盾：退款 FAQ 里有两条用的是 v2 的字段名：「缺少参数refund_fee」，以及「total_fee或refund_fee（金额参数单位为分，不能加小数点）填写错误」。
  v3 申请退款的 body 里**没有**这两个字段，对应的是 `amount.total` / `amount.refund`。写代码时不要照 FAQ 用 `refund_fee`。
- 支付和退款不能用不同的商户号：订单付款成功后就和下单时的商户号绑定了。
- 支付和退款**可以**分别用 v2 和 v3 接口，但文档「不建议跨版本使用」（FAQ 4012791869）。
- 申请退款接口**不支持**「附加数据」（attach）参数（FAQ）。
- 退款和分账互相独立，不需要先完结分账才能退款（FAQ）。
- 超过一年的订单无法退款：直连商户可以改用「商家转账」，或者线下退给用户（FAQ）。
