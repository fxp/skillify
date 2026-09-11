# 当面付：付款码支付（商家扫用户）与订单码支付（用户扫商家）

> 内容整理自 opendocs.alipay.com：open/00f7nr（产品介绍）、00f7ns（付款码支付快速接入）、00f7nv（接入注意事项）、
> 02ekfp（alipay.trade.pay）、05osux / 05osuz（订单码支付产品介绍 / 快速接入）、05osv9（alipay.trade.precreate）、
> 02ekfr（alipay.trade.cancel）、00ip3n（当面付沙箱），以及官方 v3 描述文件 openapi.yaml（2026-08-26 版）。
> 抓取于 2026-09-11。**未用真实凭证验证**；本文所有返回码、错误码、行为描述均为「文档原文，未实测」，另有标注的除外。

## 目录

1. [两种扫码方向，选错接口就全错](#1-两种扫码方向选错接口就全错)
2. [付款码支付 alipay.trade.pay](#2-付款码支付-alipaytradepay)
3. [付款码支付的结果判定：10000 不等于付款成功](#3-付款码支付的结果判定10000-不等于付款成功)
4. [订单码支付 alipay.trade.precreate](#4-订单码支付-alipaytradeprecreate)
5. [轮询 + 撤销：线下收银的闭环](#5-轮询--撤销线下收银的闭环)
6. [撤销 alipay.trade.cancel](#6-撤销-alipaytradecancel)
7. [当面付专属注意事项](#7-当面付专属注意事项)

---

## 1. 两种扫码方向，选错接口就全错

| 场景 | 谁扫谁 | 接口（旧版 method） | v3 路径 | `product_code` |
|---|---|---|---|---|
| 付款码支付（条码支付） | 收银员用扫码枪扫**用户手机上的付款码** | `alipay.trade.pay` | `POST /v3/alipay/trade/pay` | `FACE_TO_FACE_PAYMENT`（默认）；签约「当面付快捷版」传 `OFFLINE_PAYMENT` |
| 刷脸付 | 刷脸设备 | `alipay.trade.pay`，`scene=security_code`，`auth_code` 为 `fp` 开头 35 位 | 同上 | 同上 |
| 订单码支付（扫码支付） | **用户用支付宝扫商家生成的二维码** | `alipay.trade.precreate` | `POST /v3/alipay/trade/precreate` | `QR_CODE_OFFLINE`（05osv9 业务参数表：「订单码支付传：QR_CODE_OFFLINE」，必选） |

- 当面付产品公告：「不再支持小程序」，小程序请用 JSAPI 支付（本 skill 不覆盖）。
- 费率（00f7nr 原文）：单笔 0.6%；新签约商家 T+1 结算；交易后 12 个月内可退款，服务费随退款退回。
- ⚠ 文档自相矛盾：v3 openapi.yaml 的 `/v3/alipay/trade/precreate` 描述写的是「收银员通过收银台或商户后台调用……生成二维码」，而旧版 05osv9 是「订单码支付」产品下的同名接口、`product_code=QR_CODE_OFFLINE`；当面付产品（00f7nr）自己的 API 列表里没有 precreate。**先确认商户签的是「当面付」还是「订单码支付」，`product_code` 以签约为准。**

---

## 2. 付款码支付 alipay.trade.pay

**Endpoint**: 旧版 `POST https://openapi.alipay.com/gateway.do?method=alipay.trade.pay`；v3 `POST /v3/alipay/trade/pay`
**用途**: 拿扫码枪读到的用户付款码直接扣款。同步返回结果，但结果可能是「等待用户付款」（需轮询）。

**关键参数**（业务参数，旧版放 `biz_content`，v3 直接是 body）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `out_trade_no` | string(64) | 是 | — | 商户订单号，字母 / 数字 / 下划线，商户端不重复 |
| `total_amount` | price(11) | 是 | — | **单位：元**，两位小数，`[0.01, 100000000]`。示例值 `"88.88"`（字符串） |
| `subject` | string(256) | 是 | — | 订单标题，**不能含 `/`、`=`、`&` 等特殊字符** |
| `auth_code` | string(64) | 是 | — | 用户付款码：25~30 开头、16~24 位数字（以实际读到的长度为准）；刷脸为 `fp` 开头 35 位 |
| `scene` | string(32) | 是 | `bar_code` | `bar_code` 条码支付 / `security_code` 刷脸支付。⚠ 文档自相矛盾：参数表标「必选」，描述又写「默认值为 bar_code」 |
| `product_code` | string(64) | 否 | `FACE_TO_FACE_PAYMENT` | 当面付快捷版传 `OFFLINE_PAYMENT` |
| `seller_id` | string(28) | 否 | 签约账号 | 指定收款账号；优先级：门店绑定收款账户 > `seller_id` > 签约账号 |
| `store_id` | string(32) | 否 | — | 商户门店编号（注意事项页要求**所有支付都传**，且不能含中文） |
| `terminal_id` | string(32) | 否 | — | 机具终端编号（机具接入要求传） |
| `operator_id` | string(28) | 否 | — | 操作员编号 |
| `goods_detail` | GoodsDetail[] | 否 | — | 商品明细：`goods_id`、`goods_name`、`quantity`、`price`（元）必填；参与单品活动必须传 |
| `extend_params.sys_service_provider_id` | string(64) | 否 | — | 服务商返佣用，填服务商 PID |
| `business_params.mc_create_trade_ip` | string(128) | 否 | — | 用户端外网 IP |
| `query_options` | string[] | 否 | — | 定制额外返回：`fund_bill_list`、`voucher_detail_list`、`enterprise_pay_info`、`hyb_amount`、`discount_goods_detail`、`discount_amount`、`mdiscount_amount` |
| `timeout_express` | string | 否 | 3h | v3 描述文件：「当面付场景默认值为3h，如需指定，推荐设置5m及以上」；取值 `1m`～`15d`，不接受小数（`1.5h` 写 `90m`） |

⚠ 文档未说明：v3 openapi.yaml 对 `/v3/alipay/trade/pay` **没有标注任何必填字段**，上表「必填」取自旧版 API 页（open/02ekfp）。

**示例请求（Python，官方旧版 SDK）**

```python
from alipay.aop.api.domain.AlipayTradePayModel import AlipayTradePayModel
from alipay.aop.api.request.AlipayTradePayRequest import AlipayTradePayRequest
from alipay.aop.api.response.AlipayTradePayResponse import AlipayTradePayResponse
# client 初始化见 signing-and-protocols.md 第 3 节

m = AlipayTradePayModel()
m.out_trade_no = "20150320010101001"
m.total_amount = "88.88"          # 元，字符串，两位小数——不要传 8888（分）
m.subject = "Iphone6 16G"
m.auth_code = "28763443825664394" # 扫码枪读到的付款码
m.scene = "bar_code"
m.store_id = "NJ_001"
m.terminal_id = "NJ_T_001"
raw = client.execute(AlipayTradePayRequest(biz_model=m))
resp = AlipayTradePayResponse(); resp.parse_response_content(raw)
```

⚠ 文档未说明：Python SDK 是否提供 `AlipayTradePayModel` 等类——Python 文档页（common/02np8q）只演示了 `AlipayTradeCreateModel`；Java SDK 有 `AlipayTradePayModel`（open/02ekfp）。类名按 Java 规则推断，未核对 Python 包内容。

**示例请求（v3，curl 结构示意）**

```bash
# Authorization 的计算见 signing-and-protocols.md 第 6 节
curl -X POST 'https://openapi.alipay.com/v3/alipay/trade/pay' \
  -H 'Content-Type: application/json' -H 'Accept: application/json' \
  -H "Authorization: ALIPAY-SHA256withRSA app_id=${ALIPAY_APP_ID},timestamp=${TS_MS},nonce=${NONCE},expired_seconds=120,sign=${SIGN}" \
  --data '{"out_trade_no":"20150320010101001","total_amount":"88.88","subject":"Iphone6 16G","auth_code":"28763443825664394","scene":"bar_code"}'
```

**示例响应（旧版，业务字段，open/02ekfp）**

```json
{"alipay_trade_pay_response":{
  "code":"10000","msg":"Success",
  "trade_no":"2013112011001004330000121536","out_trade_no":"6823789339978248",
  "buyer_logon_id":"159****5620","total_amount":"120.88","receipt_amount":"88.88",
  "gmt_payment":"2014-11-27 15:45:57",
  "fund_bill_list":[{"fund_channel":"ALIPAYACCOUNT","amount":"10"}]},
 "sign":"..."}
```

响应里标「必选」的业务字段：`out_trade_no`、`total_amount`、`receipt_amount`、`gmt_payment`、`fund_bill_list`；`trade_no`、`buyer_logon_id`、`buyer_pay_amount`、`invoice_amount`、`point_amount` 为可选。
⚠ 文档未说明：示例响应中的具体数值为本文按字段表组织的示意，字段名以字段表为准。

---

## 3. 付款码支付的结果判定：10000 不等于付款成功

来源：open/00f7ns（文档原文，未实测）。

| `code` | 含义 | 该怎么做 |
|---|---|---|
| `10000` | **只表示请求成功**。「若存在扣款异常可能发生回滚导致扣款失败，必须根据查询接口或者异步通知返回的交易状态进行判断」 | 以 `alipay.trade.query` 的 `trade_status` / 异步通知为准 |
| `10003` | 等待用户付款（余额不足、超额需输密码等） | 等 5 秒后开始轮询 `alipay.trade.query`（见第 5 节） |
| `20000` | 未知异常（系统异常 / 网络超时） | 调查询确认结果，不要直接判失败 |
| `40001`–`40006` | 支付失败 | 检查参数；`40004` 可展示 `display_message` 给用户 |

**付款码支付的交易状态**（查询接口 / 通知的 `trade_status`）：`WAIT_BUYER_PAY`、`TRADE_SUCCESS`、`TRADE_CLOSED`、`TRADE_FINISHED`，含义见 [trade-query-refund-close.md](trade-query-refund-close.md)。

- 金额：沙箱中「单笔 2000 元以上需用户输入支付密码」；正式环境「单笔 1000 元以上会唤起支付收银台输入密码」（00ip3n）——这就是 `10003` 的典型来源。
- 付款码支付**也会发异步通知**（前提是传了 `notify_url`），默认只在 `TRADE_SUCCESS` 触发。线下收银通常以轮询为主、通知为辅。

---

## 4. 订单码支付 alipay.trade.precreate

**Endpoint**: 旧版 `method=alipay.trade.precreate`；v3 `POST /v3/alipay/trade/precreate`
**用途**: 生成一个订单二维码串 `qr_code`，商户自己把它渲染成二维码，用户用支付宝「扫一扫」付款。**此时交易还没有被用户看到；用户扫码后才进入支付。**

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `out_trade_no` | string(64) | 是 | 商户订单号 |
| `total_amount` | price(12) | 是 | 元，两位小数，`[0.01, 100000000]` |
| `subject` | string(256) | 是 | 不能含 `/ = &` |
| `product_code` | string(64) | 是 | 订单码支付传 `QR_CODE_OFFLINE` |
| `seller_id` | string(32) | 否 | 指定收款账号 |
| `body` | string(128) | 否 | 附加信息，异步通知、对账单原样返回 |
| `goods_detail` | GoodsDetail[] | 否 | 商品明细 |
| `discountable_amount` | price(11) | 否 | 可打折金额；同时传可打折 / 不可打折 / 总额时须满足「总额 = 可打折 + 不可打折」；设成 0 会导致无法享受折扣 |
| `store_id` / `operator_id` / `terminal_id` | string | 否 | 门店 / 操作员 / 终端 |
| `merchant_order_no` | string(32) | 否 | 商户原始订单号 |
| `timeout_express` / `time_expire` | string | 否 | 订单超时；两者都传以 `time_expire` 为准 |
| `notify_url`（公共参数 / v3 body 字段） | string(256) | 否 | 扫码支付**没有同步跳转**，支付结果只能靠异步通知 + 轮询 |

**示例请求（Python，自行签名版，函数见 signing-and-protocols.md 第 4 节）**

```python
res = call_v2("alipay.trade.precreate", {
    "out_trade_no": "20150320010101001",
    "total_amount": "88.88",
    "subject": "Iphone6 16G",
    "product_code": "QR_CODE_OFFLINE",
    "store_id": "NJ_001",
}, notify_url="https://api.example.com/alipay/notify")
if res["code"] == "10000":
    qr = res["qr_code"]          # 例：https://qr.alipay.com/bavh4wjlxf12tper3a —— 自己生成二维码图片
```

**示例响应（旧版，open/05osv9 字段表）**

```json
{"alipay_trade_precreate_response":{"code":"10000","msg":"Success",
  "out_trade_no":"6823789339978248","qr_code":"https://qr.alipay.com/bavh4wjlxf12tper3a"},
 "sign":"..."}
```

**注意事项**（05osuz、05osvb，文档原文，未实测）

- `qr_code` **有效期 2 小时**，从接口返回开始计时。
- 同一个订单号不能重复申请二维码（`ACQ.APPLY_PC_MERCHANT_CODE_ERROR`：「同样的订单号不能重复多次申请二维码」）。⚠ 文档未说明二维码能否被多次扫描——常见问题页摘要说「不可重复扫码」，未抓到正文细节。
- 交易成功后部分退款，状态仍为 `TRADE_SUCCESS`；全部退完变 `TRADE_CLOSED`；未退完且超过可退期变 `TRADE_FINISHED`。
- 预创建接口**不创建支付宝侧交易**之前，查询可能返回交易不存在（⚠ 文档未说明用户扫码前 `alipay.trade.query` 的确切返回——请把 `ACQ.TRADE_NOT_EXIST` 当作「用户还没扫」处理，而非失败）。

---

## 5. 轮询 + 撤销：线下收银的闭环

两份文档给了不同的轮询参数（都是文档原文，未实测）：

| 来源 | 起始 | 间隔 | 总时长 | 超时后 |
|---|---|---|---|---|
| 付款码快速接入 00f7ns / 订单码快速接入 05osuz | 等 5 秒 | 5 秒 | ⚠ 未给数值 | 最后一次仍 `WAIT_BUYER_PAY` → **立即** `alipay.trade.cancel` |
| 接入注意事项 00f7nv（「资金安全」一节） | — | 3 秒 | 30 秒 | 同上 |
| 接入注意事项 00f7nv（「推荐架构」一节） | — | 3–6 秒 | 60 秒左右 | 收银员手动停止时也必须撤销 |
| 订单码快速接入 05osuz 时序图 | — | 3–5 秒 | — | — |

⚠ 文档自相矛盾：同一份「接入注意事项」内出现 30 秒 / 60 秒两种总时长。取 3 秒间隔、30–60 秒总时长都在文档允许范围内。

闭环规则（00f7nv 原文要点）：

- 「每一笔交易一定要闭环：即支付成功或撤销交易，不能有交易一直停留在等待用户付款的状态。」
- 「撤销一定要紧接着最后一次查询，不能有时间间隔。」
- 「让用户再次支付前，必须通过查询确认当前订单的状态。」没拿到结果不要直接换单号再扣一次——可能造成用户重复付款（「用户资损单边账」）。
- 同一业务订单更换 `out_trade_no` 重新下单前，先查旧单：`TRADE_SUCCESS` 则不要再付；`WAIT_BUYER_PAY` 则先 `alipay.trade.close` 再下新单（00f7nu 原文）。
- 系统异常（`code=20000`、`sub_code=isp.unknow-error` 或 `ACQ.SYSTEM_ERROR`）时结果未知，按具体 API 的异常处理策略重试或查询。

```python
import time
def settle_barcode_payment(out_trade_no: str, pay_res: dict, total_seconds=30, interval=3) -> str:
    code = pay_res["code"]
    if code in ("10000", "10003", "20000"):          # 10000 也要以查询为准
        deadline = time.time() + total_seconds
        while time.time() < deadline:
            q = call_v2("alipay.trade.query", {"out_trade_no": out_trade_no})
            if q["code"] == "10000":
                st = q["trade_status"]
                if st in ("TRADE_SUCCESS", "TRADE_FINISHED"):
                    return "PAID"
                if st == "TRADE_CLOSED":
                    return "CLOSED"
            time.sleep(interval)
        c = call_v2("alipay.trade.cancel", {"out_trade_no": out_trade_no})   # 紧接最后一次查询
        return "CANCELLED" if c["code"] == "10000" else "UNKNOWN_NEED_MANUAL"
    return "FAILED"                                    # 40001–40006
```

---

## 6. 撤销 alipay.trade.cancel

**Endpoint**: 旧版 `method=alipay.trade.cancel`；v3 `POST /v3/alipay/trade/cancel`
**用途**: 支付结果**未知**（超时、系统异常、轮询超时）时撤销：用户没付 → 关闭交易；用户已付 → 原路退款。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `out_trade_no` | string[1,64] | 二选一 | 原支付请求的商户订单号 |
| `trade_no` | string[1,64] | 二选一 | 支付宝交易号 |

响应关键字段：`action`——`close`（交易未支付，已关闭，无退款）/ `refund`（交易已支付，已退款）/ 未返回（未查到交易或调用失败）；`retry_flag`（是否需要重试）；`gmt_refund_pay`、`refund_settlement_id`（仅银行间联场景）。

**撤销 vs 退款 vs 关闭**（00f7nv「区分撤销与退款接口」，文档原文）

| 接口 | 什么时候用 |
|---|---|
| `alipay.trade.cancel` 撤销 | **只**在「支付系统超时或支付结果未知」时用 |
| `alipay.trade.refund` 退款 | 正常的退款业务**全部**走退款接口 |
| `alipay.trade.close` 关闭 | 明确未付款的交易，不想再让用户付 |

业务错误码（v3 openapi.yaml 枚举）：`ACQ.TRADE_HAS_FINISHED`、`ACQ.TRADE_CANCEL_TIME_OUT`、`ACQ.CANCEL_NOT_ALLOWED`、`ACQ.SELLER_BALANCE_NOT_ENOUGH`、`ACQ.REASON_TRADE_BEEN_FREEZEN`、`ACQ.REASON_TRADE_REFUND_FEE_ERR`、`ACQ.SYSTEM_ERROR`、`ACQ.INVALID_PARAMETER`。
⚠ 文档自相矛盾：同一枚举里既有 `ACQ.SYSTEM_ERROR` 也有拼错的 `AQC.SYSTEM_ERROR`。

---

## 7. 当面付专属注意事项

来源：open/00f7nv、00ip3n（文档原文，未实测）。

- **部分退款每次换 `out_request_no`**：同一 `out_request_no` 会幂等返回上一次结果，导致后续部分退款「失败」。
- 监控 `INVALID_PARAMETER`：一旦出现立即停止调用并排查，避免大量无效请求。
- 外部订单号重复会导致交易失败；「对新建的订单进行跳号处理」。
- 付款码支付成功率建议保持 95% 以上。
- `goods_detail` 的单品金额与订单金额要一致，否则实收与应收不匹配。
- 推荐「商家 / 服务商后台转发」架构（门店终端 → 商户服务端 → 支付宝），而不是门店终端直连公网。
- 沙箱：只支持余额支付；条码付的 `auth_code` 要从**沙箱钱包**获取；扫码付要用沙箱钱包扫一扫；不支持优惠核销、花呗分期；`timeout_express` 不可超过当前时间 15 小时（正式默认 3h）；退款金额必须等于支付金额、每笔只能退一次。详见 [sandbox.md](sandbox.md)。
