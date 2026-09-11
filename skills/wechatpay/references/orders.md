# 查单、关单与订单状态

> 来源：`pay.weixin.qq.com/doc/v3/merchant/` 下 4012791858（按微信支付订单号查单）、4012791859（按商户订单号查单）、4012791860（关单）、
> 4012791870（订单状态流转）、4012075249（支付回调和查单实现指引）、4012791869（FAQ），抓取于 2026-09-11。
> 五种支付产品的查单和关单接口是同一组（Native FAQ 4012791890）。
>
> **验证状态**：没有用真实凭证调用过。错误码和行为描述都是文档原文，未实测。
> 无凭证探测（2026-09-11）：`GET /v3/pay/transactions/out-trade-no/PROBE_FAKE_0001?mchid=1900000000` 在各种伪造鉴权下都返回 401 `SIGN_ERROR`，说明 path 存在。

## 1. 订单状态机

```
            用户支付成功                    申请退款成功（支付后 1 年内）
 NOTPAY ─────────────────▶ SUCCESS ─────────────────────────────▶ REFUND
   │
   ├── 商户调用关单接口（下单后 7 天内）──▶ CLOSED
   └── 超过 7 天没付，微信支付自动关单 ────▶ CLOSED
```

- 终态有三个：`SUCCESS`、`CLOSED`、`REFUND`（4012791870）。
- 用户付款失败（余额不足、风控、超过 `time_expire`…），状态**保持 `NOTPAY`**，不会变成失败态。
- `REVOKED` / `USERPAYING` / `PAYERROR` 只有付款码支付会返回，本 skill 覆盖的五种产品不会出现。
- 部分退款后查单，`trade_state` 是 `REFUND`（退款 FAQ）。所以「`trade_state == SUCCESS` 才算已付款」这种写法，会把已付款但部分退款的订单误判成未付款。

## 2. 按商户订单号查单（推荐）

**Endpoint**: `GET /v3/pay/transactions/out-trade-no/{out_trade_no}?mchid={mchid}`
**用途**：任何状态的订单都能查。**订单还没付款时只能用这个接口**（没付款就还没有 `transaction_id`）。

**关键参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `out_trade_no` | path | string(32) | 是 | 下单时传的商户订单号 |
| `mchid` | **query** | string(32) | 是 | 下单时传的商户号。**它在 query 里，签名串的 URL 要带上 `?mchid=…`** |

**示例请求**

```bash
curl -X GET 'https://api.mch.weixin.qq.com/v3/pay/transactions/out-trade-no/1217752501201407033233368018?mchid=1230000109' \
  -H 'Authorization: WECHATPAY2-SHA256-RSA2048 mchid="1230000109",...' -H 'Accept: application/json' -A 'my-shop-backend/1.0'
```

```python
from wechatpay_v3 import request, MCHID

def query_by_out_trade_no(out_trade_no: str) -> dict:
    return request("GET", f"/v3/pay/transactions/out-trade-no/{out_trade_no}", query={"mchid": MCHID})
```

**应答字段**（按商户订单号查单和按微信订单号查单一样）

| 字段 | 类型 | 说明 |
|---|---|---|
| `appid` / `mchid` / `out_trade_no` | string | 下单时传的值 |
| `transaction_id` | string(32) | 微信支付订单号。**按商户订单号查时是选填：未支付的订单没有这个字段** |
| `trade_type` | string(16) | `JSAPI`（公众号和小程序）/ `NATIVE` / `APP` / `MWEB`（H5）/ `MICROPAY` / `FACEPAY`。按商户订单号查时也是选填 |
| `trade_state` | string(32) | `SUCCESS` / `REFUND` / `NOTPAY` / `CLOSED`（外加付款码专用的三种状态） |
| `trade_state_desc` | string(256) | 状态描述 |
| `bank_type` | string(32) | 付款银行，例如 `ICBC_DEBIT`；零钱等非银行卡统一是 `OTHERS` |
| `attach` | string(128) | 下单时传了才会返回 |
| `success_time` | string(64) | 支付完成时间，RFC3339 格式，付款成功后才返回 |
| `payer.openid` | string(128) | 付款成功后返回 |
| `amount.total` | integer | 订单总金额，**分** |
| `amount.payer_total` | integer | 用户实际支付的金额（分）= 总金额 − 代金券金额 |
| `amount.currency` / `payer_currency` | string | `CNY` |
| `scene_info.device_id` | string | 下单时传了才返回 |
| `promotion_detail[]` | array | 用了代金券才返回：`coupon_id`、`amount`、`type`（`CASH` / `NOCASH`）、`scope`（`GLOBAL` / `SINGLE`）… |

**示例响应（节选）**

```json
{"appid": "wxd678efh567hg6787", "mchid": "1230000109", "out_trade_no": "1217752501201407033233368018",
 "transaction_id": "1217752501201407033233368018", "trade_type": "JSAPI", "trade_state": "SUCCESS",
 "trade_state_desc": "支付成功", "bank_type": "CMC", "success_time": "2018-06-08T10:34:56+08:00",
 "payer": {"openid": "oUpF8uMuAJO_M2pxb1Q9zNjWeS6o"},
 "amount": {"total": 100, "payer_total": 100, "currency": "CNY", "payer_currency": "CNY"}}
```

## 3. 按微信支付订单号查单

**Endpoint**: `GET /v3/pay/transactions/id/{transaction_id}?mchid={mchid}`
**用途**：只能查已付款的订单（这时才有 `transaction_id`）。应答结构和 §2 一样，`transaction_id` / `trade_type` 在这里是必返字段。

```python
def query_by_transaction_id(transaction_id: str) -> dict:
    return request("GET", f"/v3/pay/transactions/id/{transaction_id}", query={"mchid": MCHID})
```

## 4. 关单

**Endpoint**: `POST /v3/pay/transactions/out-trade-no/{out_trade_no}/close`
**用途**：关闭**未支付**的订单，例如用户取消、超时未付。关单后的订单可以当作失败终态处理。

**关键参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `out_trade_no` | path | string(32) | 是 | 商户订单号 |
| `mchid` | **body** | string(32) | 是 | 注意：查单时 mchid 放在 query，**关单时 mchid 放在 JSON body** |

**示例请求**

```bash
curl -X POST https://api.mch.weixin.qq.com/v3/pay/transactions/out-trade-no/1217752501201407033233368018/close \
  -H 'Authorization: WECHATPAY2-SHA256-RSA2048 mchid="1230000109",...' \
  -H 'Accept: application/json' -H 'Content-Type: application/json' -A 'my-shop-backend/1.0' \
  -d '{"mchid":"1230000109"}'
```

```python
def close_order(out_trade_no: str) -> None:
    request("POST", f"/v3/pay/transactions/out-trade-no/{out_trade_no}/close", payload={"mchid": MCHID})
```

**示例响应**：`204 No Content`，没有 body。验签时第 3 行只剩一个 `\n`（`wechatpay_v3.request` 已经这样处理，见 `auth-signing.md` §5）。

**注意事项**
- 关单接口**支持重入**，可以重复调用（FAQ）。
- 用户付款失败**不需要**关单就能重新付：同一个订单还是 NOTPAY，可以继续付款。
- 过了 `time_expire` 之后，文档建议**先关单，再用新的 `out_trade_no` 重新下单**（下单页 `time_expire` 说明）。

## 5. 什么时候查单：文档给的兜底方案（4012075249）

回调可能因为网络问题丢失，所以商户系统「不能仅依赖回调通知」。

| 场景 | 做法 |
|---|---|
| 前端返回「成功」或「失败」 | 调**自己后端**的查单接口，由后端去查微信支付。查到 `SUCCESS` 就展示成功，否则提示用户「稍后在订单页核实，不要重复付款」 |
| 前端返回「取消」 | 保持未支付，不用查 |
| Native 二维码 | 前端轮询后端，示例是每 2 秒一次、共 60 秒 |
| 后端长时间没收到回调（方案一） | 从下单成功那一刻起，按 5 秒 / 30 秒 / 1 分钟 / 3 分钟 / 5 分钟 / 10 分钟 / 30 分钟 的间隔查单 |
| 后端长时间没收到回调（方案二） | 定时任务每 30 秒扫一遍「最近 10 分钟内创建、还没付款」的订单去查；同一订单查了 10 次还没付款，就调关单 |
| 用户对未付款订单再次付款 | **用原来的单号**，不要换新单号，避免重复支付 |
| T+1 对账 | 第二天 10 点之后下载前一天的交易账单逐笔核对，见 `bills.md` |

**判断支付成功的标准**（FAQ）：查单应答**验签通过**，并且 `trade_state` 是 `SUCCESS`。

```python
import time
from wechatpay_v3 import WechatPayError

def poll_until_final(out_trade_no: str, schedule=(5, 30, 60, 180, 300, 600, 1800)) -> str:
    for wait in schedule:
        time.sleep(wait)
        try:
            state = query_by_out_trade_no(out_trade_no)["trade_state"]
        except WechatPayError as e:
            if e.code == "ORDER_NOT_EXIST":
                return "NOT_EXIST"
            continue                                  # SYSTEM_ERROR / FREQUENCY_LIMITED：下一轮再查
        if state in ("SUCCESS", "REFUND", "CLOSED"):
            return state
    close_order(out_trade_no)                         # 仍是 NOTPAY：先关单，关单成功后再标记失败
    return "CLOSED"
```

- **NOTPAY 不能直接当作支付失败**（FAQ）。用户之后可能还会付款。要标记失败，先调关单，关单成功后再标记。
- 查单接口能查多久以前的订单：文档 FAQ 说「暂无时间限制」。

## 6. 错误码（文档原文，未实测）

| HTTP | code | 含义 | 处理 |
|---|---|---|---|
| 400 | `INVALID_REQUEST` / `PARAM_ERROR` | 请求无效 / 参数错误 | 看 `detail` |
| 400 | `MCH_NOT_EXISTS` | 商户号不存在 | 核对 mchid |
| 401 | `SIGN_ERROR` | 签名错误。GET 请求最常见的原因是签名串的 URL 漏了 `?mchid=…` | `auth-signing.md` §9 |
| 403 | `RULE_LIMIT` | 业务规则限制 | 看 message |
| 403 | `TRADE_ERROR` | 因为业务原因交易失败 | 看 message |
| 404 | `ORDER_NOT_EXIST` | 订单不存在（只有查单接口有这个码） | 检查单号，或者下单根本没成功 |
| 429 | `FREQUENCY_LIMITED` | 频率超限 | 降频 |
| 500 | `SYSTEM_ERROR` | 系统错误 | 用相同参数重试 |

FAQ 里的其他报错：「商户号和订单信息不匹配」→ 用 A 商户号去查 B 商户号的订单。订单支付成功后就和下单时的商户号绑定了，别的商户号不能操作它。

## 7. 本文件 ⚠

- ⚠ 文档未说明：查单和关单接口的具体频率上限。错误码表里有 `FREQUENCY_LIMITED`，但没给出数值。
