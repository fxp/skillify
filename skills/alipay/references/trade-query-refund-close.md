# 交易查询、退款、退款查询、关闭、对账单

> 内容整理自 opendocs.alipay.com：open/02ekfq（alipay.trade.query）、02ekfs（alipay.trade.refund）、
> 02ekft（alipay.trade.fastpay.refund.query）、02o6e8（alipay.trade.close）、02ekfu（alipay.data.dataservice.bill.downloadurl.query）、
> 00f7ns / 00dn7k / 00f7nh（各产品快速接入里的退款、对账说明）、00f7nv（注意事项），以及官方 v3 描述文件 openapi.yaml（2026-08-26）。
> 抓取于 2026-09-11。**未用真实凭证验证**；错误码与行为均为「文档原文，未实测」。
>
> 这组接口在当面付、订单码、电脑网站、手机网站、APP 支付下**是同一套**（每个产品页下各挂一份副本，内容一致）。
> 撤销 `alipay.trade.cancel` 只用于线下支付结果未知，见 [face-to-face.md](face-to-face.md)。

## 目录

1. [查询交易 alipay.trade.query](#1-查询交易-alipaytradequery)
2. [交易状态机](#2-交易状态机)
3. [退款 alipay.trade.refund](#3-退款-alipaytraderefund)
4. [退款成功怎么判断（最容易写错）](#4-退款成功怎么判断最容易写错)
5. [退款查询 alipay.trade.fastpay.refund.query](#5-退款查询-alipaytradefastpayrefundquery)
6. [关闭交易 alipay.trade.close](#6-关闭交易-alipaytradeclose)
7. [对账单下载地址 alipay.data.dataservice.bill.downloadurl.query](#7-对账单下载地址)
8. [v2 / v3 路径对照](#8-v2--v3-路径对照)

---

## 1. 查询交易 alipay.trade.query

**Endpoint**: 旧版 `method=alipay.trade.query`；v3 `POST /v3/alipay/trade/query`
**用途**: 主动查订单状态。**必须接**：没收到异步通知、支付返回未知（`10003`/`20000`）、撤销前确认、换单号重付前确认旧单。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `out_trade_no` | string(64) | 二选一 | 商户订单号 |
| `trade_no` | string(64) | 二选一 | 支付宝交易号；两个都传时**优先取 `trade_no`** |
| `query_options` | string[] | 否 | 额外返回：`trade_settle_info`、`fund_bill_list`、`voucher_detail_list`、`discount_goods_detail`、`mdiscount_amount`、`medical_insurance_info` |
| `org_pid` | string | 否 | 仅银行间联模式（v3 描述文件） |

**示例请求**

```python
res = call_v2("alipay.trade.query", {"out_trade_no": "20150320010101001"})   # call_v2 见 signing-and-protocols.md
# v3: r = call_v3("POST", "/v3/alipay/trade/query", {"out_trade_no": "20150320010101001"})
```

```bash
# v3 结构示意（Authorization 计算见 signing-and-protocols.md 第 6 节）
curl -X POST 'https://openapi.alipay.com/v3/alipay/trade/query' \
  -H 'Content-Type: application/json' -H "Authorization: ${ALIPAY_AUTH}" \
  --data '{"out_trade_no":"20150320010101001"}'
```

**示例响应（关键字段，open/02ekfq 字段表）**

| 字段 | 必选 | 说明 |
|---|---|---|
| `trade_no` / `out_trade_no` | 是 | 支付宝交易号 / 商户订单号 |
| `trade_status` | 是 | `WAIT_BUYER_PAY` / `TRADE_CLOSED` / `TRADE_SUCCESS` / `TRADE_FINISHED` |
| `total_amount` | 是 | 订单金额（元），等于下单时传入值 |
| `buyer_user_id` / `buyer_open_id` | 是 / 特殊可选 | 买家 ID；新商户建议用 `open_id` |
| `receipt_amount` | 特殊可选 | 商户实收（元） |
| `buyer_pay_amount` | 可选 | 买家实付（元），不含商户折扣 |
| `fund_bill_list` | 是 | 资金渠道明细 |
| `send_pay_date` | 特殊可选 | 打款给卖家的时间 |

⚠ 文档自相矛盾：v3 描述文件未标注任何必填 / 必返字段，上表「必选」取自旧版页面。

**注意事项**
- 查询接口 `code=10000` 只说明**查询成功**；支付是否成功看 `trade_status`。
- 订单码支付下单后用户还没扫码时，⚠ 文档未说明查询返回什么（很可能 `ACQ.TRADE_NOT_EXIST`，请当作「未付」而非失败）。
- 业务错误码：`ACQ.TRADE_NOT_EXIST`（查询的交易不存在）、`ACQ.INVALID_PARAMETER`、`ACQ.SYSTEM_ERROR`（重新发起）。

---

## 2. 交易状态机

来源：open/00f7nu、02ekfq、05osuz（文档原文，未实测）。

| `trade_status` | 含义 | 默认触发异步通知？ |
|---|---|---|
| `WAIT_BUYER_PAY` | 交易创建，等待买家付款 | 否 |
| `TRADE_SUCCESS` | 支付成功（**产品支持退款**时付款成功的状态） | **是** |
| `TRADE_FINISHED` | 交易结束，不可退款（产品不支持退款时付款成功；或支持退款但已超过可退期限） | 否 |
| `TRADE_CLOSED` | 未付款超时关闭，**或支付完成后全额退款** | 否 |

- 「只有交易通知状态为 `TRADE_SUCCESS` 或 `TRADE_FINISHED` 时，支付宝才会认定为买家付款成功。」——**判定「已付款」要把两个都算上**。
- 部分退款后状态仍是 `TRADE_SUCCESS`；全部退完变 `TRADE_CLOSED`。所以 `TRADE_CLOSED` **不一定是没付过钱**，要结合 `refund_fee` / 退款记录判断。
- 可退款期：当面付、电脑网站支付文档写「交易后 12 个月内」。

---

## 3. 退款 alipay.trade.refund

**Endpoint**: 旧版 `method=alipay.trade.refund`；v3 `POST /v3/alipay/trade/refund`
**用途**: 同步退款，原路退回。支持一笔交易多次部分退款。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `refund_amount` | price(16) | 是 | 本次退款金额（**元**，两位小数），不能大于订单金额；含营销金额 |
| `out_trade_no` / `trade_no` | string(64) | 二选一 | 同时传以 `trade_no` 为准 |
| `out_request_no` | string(64) | **部分退款时必填** | 退款请求号，交易内唯一。**重试同一笔退款时不能变**；发起新的一笔部分退款时**必须换** |
| `refund_reason` | string(256) | 否 | 退款原因，展示在账单 |
| `refund_goods_detail` | array | 否 | 退款商品明细（`goods_id`、`refund_amount` 必填） |
| `refund_royalty_parameters` | array | 否 | 退分账明细；当面付非直付通无需传 |
| `query_options` | string[] | 否 | 如 `refund_detail_item_list`（才会返回 `send_back_fee`） |

**规则**（open/02ekfs，文档原文，未实测）

1. 同一笔交易**两次退款至少间隔 3 秒**。
2. 累计退款金额不能超过交易总额（超了报 `ACQ.REASON_TRADE_REFUND_FEE_ERR` / `ACQ.REFUND_AMT_NOT_EQUAL_TOTAL`）。
3. 「若在此接口中传入【非当前接口文档中的参数】会造成【退款失败或重复退款】。」——别往 biz_content 里塞自定义字段。
4. 不可与其它退款产品混用，否则可能重复退款。
5. 涉及分账的交易，分账接收方要先在商家平台开启「分账回退授权」。
6. 超过签约设置的可退款期的交易无法退款（`ACQ.TRADE_HAS_FINISHED`，「即使重试也无法成功」）。

**示例请求**

```python
res = call_v2("alipay.trade.refund", {
    "out_trade_no": "20150320010101001",
    "refund_amount": "20.00",          # 元
    "out_request_no": "RF20240101001", # 部分退款必填；重试时保持不变
    "refund_reason": "正常退款",
})
if res["code"] == "10000" and res.get("fund_change") == "Y":
    ...  # 本次退款成功
elif res["code"] == "10000":
    ...  # fund_change=N 或缺失：去退款查询确认，不要直接判失败
elif res.get("sub_code") == "ACQ.SYSTEM_ERROR":
    ...  # 结果未知：用相同 out_request_no、相同金额重试，或先查
```

**示例响应（关键字段）**

| 字段 | 说明 |
|---|---|
| `trade_no` / `out_trade_no` / `buyer_logon_id` | 交易信息 |
| `refund_fee` | **该笔交易累计已退款成功的金额**（不是本次金额） |
| `fund_change` | 本次退款是否发生资金变化 `Y`/`N` |
| `send_back_fee` | 本次商户实际退回金额；需 `query_options` 传 `refund_detail_item_list` |
| `refund_detail_item_list` | 退款资金渠道，需 `query_options` 指定 |

**常见业务错误码**（open/02ekfs 节选）

| 错误码 | 处理 |
|---|---|
| `ACQ.SYSTEM_ERROR` | 结果未知，「请使用相同的参数再次重试调用，需要保证退款请求号不变」 |
| `ACQ.DISCORDANT_REPEAT_REQUEST` | 同一 `out_request_no` 已成功退过，但这次金额不同——每笔新退款换请求号 |
| `ACQ.REASON_TRADE_REFUND_FEE_ERR` / `ACQ.REFUND_AMT_NOT_EQUAL_TOTAL` | 累计退款超额；非全额退款时 `out_request_no` 必填 |
| `ACQ.SELLER_BALANCE_NOT_ENOUGH` | 商户余额不足，充值后重发 |
| `ACQ.TRADE_HAS_FINISHED` | 已过退款期限，线下处理 |
| `ACQ.TRADE_HAS_CLOSE` | 交易已关闭（未支付或已全额退款） |
| `ACQ.TRADE_NOT_ALLOW_REFUND` / `ACQ.NOT_ALLOW_PARTIAL_REFUND` | 状态或优惠券不允许（部分）退款 |
| `ACQ.TRADE_STATUS_ERROR` | 交易未付款 |
| `ACQ.REFUNDALLOC_UNAUTH_LIMIT` | 分账接收方未开启分账回退 |

另有异步退款受理接口 `POST /v3/alipay/trade/refund/apply`（返回 `refund_status`：`REFUND_PROCESSING` / `REFUND_SUCCESS` / `REFUND_FAIL`），⚠ 文档未说明它对普通当面付 / 网站支付是否开放，本 skill 不展开。

---

## 4. 退款成功怎么判断（最容易写错）

| 信号 | 说明（文档原文） |
|---|---|
| 退款接口 `code=10000` | **不代表退款成功** |
| 退款接口 `fund_change=Y` | 本次退款成功 |
| `fund_change=N` 或无此字段 | 「需通过退款查询接口进一步确认退款状态」 |
| 退款查询 `code=10000` | 只代表查询成功 |
| 退款查询 `refund_status=REFUND_SUCCESS` | 退款成功；**未返回该字段 = 退款请求未收到或失败** |

- 退款**默认不会触发 `trade_status_sync` 异步通知**（`TRADE_CLOSED` 通知默认关闭；见 [notify-and-verify.md](notify-and-verify.md)）。退款结果以同步返回或退款查询为准。
- 退款到银行卡的完成通知 `alipay.trade.refund.depositback.completed`：只在发起退款时传了 `deposit_back_info` 相关参数、且退款涉及银行卡时才触发，发到**应用网关**而不是 `notify_url`；沙箱不支持。

---

## 5. 退款查询 alipay.trade.fastpay.refund.query

**Endpoint**: 旧版 `method=alipay.trade.fastpay.refund.query`；v3 `POST /v3/alipay/trade/fastpay/refund/query`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `out_request_no` | string(64) | 是 | 退款时传的请求号；**退款时没传，则填原交易的 `out_trade_no`** |
| `out_trade_no` / `trade_no` | string(64) | 二选一 | 同时传以 `trade_no` 为准 |
| `query_options` | string[] | 否 | `refund_detail_item_list`、`gmt_refund_pay`、`deposit_back_info`、`refund_voucher_detail_list` |

**注意事项**（open/02ekft、00f7ns，文档原文，未实测）
- 与退款请求**间隔 10 秒以上**再查。
- `trade_no`、`out_trade_no`、`out_request_no` 必须和退款时一致；`out_request_no` 不一致时会「只会返回 10000，success，但是没有具体的退款信息」——**空结果不等于退款失败，可能是查错了号**。
- 未成功要重试退款时，**请求号和金额都保持一致**，防止重复退款。
- 响应：`refund_status`（`REFUND_SUCCESS`）、`refund_amount`（本次金额）、`total_amount`、`gmt_refund_pay`（需 query_options）、`deposit_back_info`（银行卡冲退：`dback_status` S/F/P）。

---

## 6. 关闭交易 alipay.trade.close

**Endpoint**: 旧版 `method=alipay.trade.close`；v3 `POST /v3/alipay/trade/close`
**用途**: 关闭**等待买家付款**的交易。关闭后该交易不可再支付。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `trade_no` / `out_trade_no` | string(64) | 二选一 | 同时传以 `trade_no` 为准 |
| `operator_id` | string(28) | 否 | 操作员 |
| `notify_url`（公共参数 / v3 body） | string | 否 | 关闭通知地址 |

- 业务错误码：`ACQ.TRADE_STATUS_ERROR`（「只有等待买家付款状态下才能发起交易关闭」）、`ACQ.REASON_TRADE_STATUS_INVALID` / `ACQ.REASON_ILLEGAL_STATUS`（非待支付状态）、`ACQ.TRADE_NOT_EXIST`、`ACQ.SYSTEM_ERROR`（重新发起）。
- ⚠ 文档未说明：对**从未被支付宝创建**的订单（如电脑网站支付用户没进收银台、订单码没被扫）调 close 的确切返回。一般通过 `timeout_express` / `time_expire` 让支付宝自动关单即可。
- 关闭不是退款：已付款的交易要用退款接口。

---

## 7. 对账单下载地址

**Endpoint**: 旧版 `method=alipay.data.dataservice.bill.downloadurl.query`；v3 `GET /v3/alipay/data/dataservice/bill/downloadurl/query?bill_type=…&bill_date=…`（**v3 这里是 GET + query string**，不是 POST JSON）

| 参数 | 必填 | 说明 |
|---|---|---|
| `bill_type` | 是 | `trade`（收单业务账单）、`signcustomer`（资金变动账务账单）、`merchant_act`（营销活动）、`trade_zft_merchant`（直付通二级商户）、`zft_acc`（直付通平台商） |
| `bill_date` | 是 | 日账单 `yyyy-MM-dd`、月账单 `yyyy-MM`；**不能下当日**，T+1，当日数据一般次日 9 点前生成；最早近 6 年 |
| `smid` | 否 | 仅 `bill_type=trade_zft_merchant` |
| `secure`（v3） | 否 | `true` 返回 https 链接，否则 http |

- 响应 `bill_download_url`：**30 秒内不下载就失效**，拿到立即服务端下载（CSV 压缩包）。v3 另有 `bill_file_code`（如 `EMPTY_DATA_WITH_BILL_FILE`）。
- 错误码（v3 枚举）：`NO_BILL_DATA`、`BILL_NOT_EXIST`、`BILL_DATE_BEFORE_REGISTRATION`、`TYPE_NOT_SUPPORTED`、`SYSTEM_RATE_LIMIT`、`USER_RATE_LIMIT`、`INVAILID_ARGUMENTS`（原文拼写如此）。
- 沙箱：只做模拟调用，下载的是模板，没有实际数据。

---

## 8. v2 / v3 路径对照

| 能力 | 旧版 `method` | v3 |
|---|---|---|
| 付款码支付 | `alipay.trade.pay` | `POST /v3/alipay/trade/pay` |
| 订单码预下单 | `alipay.trade.precreate` | `POST /v3/alipay/trade/precreate` |
| 统一收单创建（JSAPI 等） | `alipay.trade.create` | `POST /v3/alipay/trade/create` |
| 查询 | `alipay.trade.query` | `POST /v3/alipay/trade/query` |
| 退款 | `alipay.trade.refund` | `POST /v3/alipay/trade/refund` |
| 退款查询 | `alipay.trade.fastpay.refund.query` | `POST /v3/alipay/trade/fastpay/refund/query` |
| 关闭 | `alipay.trade.close` | `POST /v3/alipay/trade/close` |
| 撤销 | `alipay.trade.cancel` | `POST /v3/alipay/trade/cancel` |
| 账单下载地址 | `alipay.data.dataservice.bill.downloadurl.query` | `GET /v3/alipay/data/dataservice/bill/downloadurl/query` |
| 电脑网站 / 手机网站 / APP 下单 | `alipay.trade.page.pay` / `wap.pay` / `app.pay` | **无 v3 路径**（见 [web-and-app-pay.md](web-and-app-pay.md)） |

规律：v3 路径 = `/v3/` + 方法名把 `.` 换成 `/`；**HTTP 方法不能按「查询就用 GET」去猜**——`trade/query` 是 POST，`bill/downloadurl/query` 是 GET，以 openapi.yaml 为准。
v3 业务错误在 HTTP 4xx 的 body 里是 `{"code":"ACQ.TRADE_NOT_EXIST","message":"..."}`，旧版是 `code=40004` + `sub_code=ACQ.TRADE_NOT_EXIST`，见 [errors.md](errors.md)。
