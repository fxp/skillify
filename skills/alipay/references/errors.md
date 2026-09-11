# 错误码与错误处理

> 内容整理自 opendocs.alipay.com：common/02km9f（旧版公共错误码）、open-v3/054fcv（v3 错误码）、open-v3/054oog（v3 错误处理）、
> common/02kdnf（签名排查）、open/00f7ns / 00f7nv（异常处理策略）、各 API 页「业务错误码」表，以及官方 v3 描述文件 openapi.yaml。
> 抓取于 2026-09-11。**未用真实凭证验证**；除标「无凭证探测（2026-09-11）」的条目外，所有错误码与处理建议均为「文档原文，未实测」。

## 目录

1. [两套协议的错误长得完全不一样](#1-两套协议的错误长得完全不一样)
2. [旧版网关：公共错误码（code / sub_code）](#2-旧版网关公共错误码code--sub_code)
3. [v3：HTTP 状态码 + code](#3-v3http-状态码--code)
4. [收单业务错误码（ACQ.*）速查](#4-收单业务错误码acq速查)
5. [「结果未知」怎么处理](#5-结果未知怎么处理)
6. [限流](#6-限流)
7. [通用处理代码](#7-通用处理代码)

---

## 1. 两套协议的错误长得完全不一样

**无凭证探测（2026-09-11）**，同一个伪造 `app_id=test` 的查询：

旧版 `POST https://openapi.alipay.com/gateway.do?method=alipay.trade.query…`

```
HTTP/1.1 200
content-type: text/html;charset=utf-8

{"alipay_trade_query_response":{"code":"40002","msg":"Invalid Arguments",
  "sub_code":"isv.invalid-app-id",
  "sub_msg":"无效的AppID参数，解决方案：https://open.alipay.com/api/errCheck?traceId=…&source=openapi"}}
```

v3 `POST https://openapi.alipay.com/v3/alipay/trade/query`

```
HTTP/2 400
content-type: application/json;charset=UTF-8
alipay-trace-id: 0b43c935…

{"code":"invalid-app-id","links":[{"link":"https://open.alipay.com/api/errCheck?traceId=…&source=openapi","desc":"解决方案"}],"message":"无效的AppID参数"}
```

| | 旧版 | v3 |
|---|---|---|
| HTTP 状态 | 一律 200（探测证实） | 4xx / 5xx（探测证实 400） |
| 位置 | `<method 点换下划线>_response` 对象内 | body 顶层 |
| 成功标志 | `code == "10000"` | HTTP 200 |
| 网关级错误 | `code` 为 20000/20001/40001–40006，`sub_code` 为 `isv.*` / `aop.*` / `isp.*` | `code` 为同名但**去掉 `isv.` / `aop.` 前缀**的 kebab-case（`invalid-app-id`） |
| 业务错误 | `code=40004` + `sub_code=ACQ.*` | `code=ACQ.*` |
| 描述 | `msg` + `sub_msg` | `message` |
| 解决方案链接 | 拼在 `sub_msg` 文本里（生产） | `links`：**数组** `[{link, desc}]` |
| 错误响应签名 | 无 `sign` 字段（探测） | 无 `alipay-signature` 头（探测） |

<!-- Gap: 官方 v3 描述文件 openapi.yaml 把错误响应的 links 声明为 string；无凭证探测（2026-09-11）实际返回 "links":[{"link":"…","desc":"解决方案"}] 数组 -->
**无凭证探测（2026-09-11）**：openapi.yaml 把错误体 `links` 声明为 `string`，实际是**对象数组**。按描述文件生成的强类型 SDK / 反序列化代码会在这里失败——解析时对 `links` 做宽松处理。

旧版的 Content-Type 声明是 `text/html` 但正文是 JSON（探测）；页面跳转类接口出错则是 **GBK 编码的 HTML 页面**（见 [web-and-app-pay.md](web-and-app-pay.md) 第 7 节）。

---

## 2. 旧版网关：公共错误码（code / sub_code）

来源：common/02km9f（文档原文，未实测）。

| code | msg | 常见 sub_code | 处理 |
|---|---|---|---|
| `10000` | 接口调用成功 | — | 看业务字段（**不等于支付 / 退款成功**） |
| `10003` | 等待用户付款（付款码支付） | — | 轮询查询（见 face-to-face.md） |
| `20000` | 服务不可用 | `isp.unknow-error`（业务系统）、`aop.unknow-error`（网关） | 稍后重试；交易类先查询确认 |
| `20001` | 授权权限不足 | `aop.invalid-auth-token`、`aop.auth-token-time-out`、`aop.invalid-app-auth-token`、`aop.invalid-app-auth-token-no-api`、`aop.app-auth-token-time-out`、`aop.no-product-reg-by-partner` | 刷新 / 重新获取授权令牌（服务商场景） |
| `40001` | 缺少必选参数 | `isv.missing-method`、`isv.missing-signature`、`isv.missing-signature-type`、`isv.missing-signature-key`、`isv.missing-app-id`、`isv.missing-timestamp`、`isv.missing-version`、`isv.decryption-error-missing-encrypt-type` | 补参数 |
| `40002` | 非法的参数 | `isv.invalid-parameter`、`isv.invalid-method`、`isv.invalid-format`、`isv.invalid-signature-type`、**`isv.invalid-signature`**、`isv.invalid-app-id`、`isv.invalid-timestamp`、`isv.invalid-charset`、`isv.illegal-json`、`isv.suspected-attack`、`isv.forbidden-api`、`app-cert-expired`、`not-online-app`、`invalid-openid`… | 见下 |
| `40003` | 条件异常 | `invalid-auth-relations`、**`isv.missing-signature-config`** | 控制台未上传公钥 / 证书 |
| `40004` | 业务处理失败 | 各接口 `ACQ.*`；另有 `unsupported-sdk-version` | 看第 4 节 |
| `40005` | 调用频次超限 | `isv.app-call-limited`、`isv.method-call-limited` | 降低并发 |
| `40006` | 权限不足 | `isv.insufficient-isv-permissions`、`isv.insufficient-user-permissions`、`isv.self-invoke-forbidden` | 产品未开通 / 未签约；应用未绑定商家 |

`40002` 里最常见的几个：

| sub_code | 含义 / 排查 |
|---|---|
| `isv.invalid-signature` | 公私钥不配对；**网关环境与 app_id、私钥不匹配（沙箱 vs 生产）**；中文未 urlencode；签名算法不对 |
| `isv.invalid-app-id` | app_id 不存在或应用未上线（沙箱：appId 不在沙箱控制台列表里） |
| `isv.invalid-timestamp` | 格式必须 `yyyy-MM-dd HH:mm:ss` |
| `isv.invalid-charset` | 只支持 GBK、UTF-8 |
| `isv.suspected-attack` | 参数值里出现了支付宝关键 key（`body`、`subject`、`service`、`out_trade_no`、`seller_id`、`total_fee` 等），换参数名 / 内容 |
| `not-online-app` | 应用未上线，去控制台上线 |
| `isv.missing-app-cert-sn` / `isv.missing-alipay-root-cert-sn` / `isv.app-cert-expired` | 证书模式缺 SN 或证书过期（02kdnf） |

⚠ 文档自相矛盾：`isv.invalid-signature-type` 说「目前只支持 RSA、RSA2、HMAC_SHA1」，签名页（057k53）说支持 RSA2 和 SM2、新应用只支持 RSA2。
**无凭证探测（2026-09-11）**：不带 `sign` 时返回的仍是 `isv.invalid-app-id`——网关先校验 app_id，再校验签名；排查签名问题前先确认 app_id 与网关环境匹配。

---

## 3. v3：HTTP 状态码 + code

来源：open-v3/054fcv、054oog（文档原文，未实测）。

| HTTP | 类别 | code 举例 |
|---|---|---|
| 200 | 成功 | — |
| 202 | 已接受未处理 | 「请使用原参数重复请求一遍」 |
| 204 | 成功无 body | — |
| 302 | 页面重定向接口成功（如手机网站支付） | — |
| 400 | 参数 / 协议非法；业务失败 | `invalid-parameter`、`invalid-app-id`、`invalid-signature`、`invalid-timestamp`、`missing-timestamp`、`invalid-content-type`、`invalid-http-method`、`illegal-json`、`not-online-app`、`app-cert-expired`、`missing-signature-config`、以及业务 `ACQ.*` |
| 401 | 授权 / 签名 | `invalid-auth-token`、`invalid-app-auth-token`、`insufficient-isv-permissions`、`self-invoke-forbidden`…（文档把「权限不足」也放在 401 下） |
| 403 | 无权限调用 | 产品未开通 |
| 404 | 资源不存在 | id 或 URL 错 |
| 429 | 频率超限 | `app-call-limited`、`method-call-limited` |
| 500 / 502 | 系统错误 | `unknow-error`；「商家需要重试」 |

⚠ 文档自相矛盾：
- 054q58 说「无签名或签名验证失败的请求……返回 401 Unauthorized」；054fcv 表格把 `missing-signature`、`invalid-signature` 放在 **400** 下。
- 054fcv 把 `unknow-error` 同时列在 400（业务异常）和 500（系统异常）下。

<!-- Gap: v3 签名规则页说无签名返回 401；无凭证探测（2026-09-11）不带 Authorization 头返回 HTTP 400 {"code":"missing-timestamp","message":"缺少时间戳参数"} -->
**无凭证探测（2026-09-11）**：不带 `Authorization` 头 → HTTP **400** `{"code":"missing-timestamp","message":"缺少时间戳参数"}`。所以「签名问题 = 401」的假设不成立；按 `code` 字段分支，而不是只按 HTTP 状态分支。

v3 描述文件（openapi.yaml）为每个接口列出了可能的公共 `code` 枚举（约 100 个，如 `invalid-app-state`、`illegal-timestamp`、`exceed-api-balance`），业务 `code` 是 `ACQ.*`。

---

## 4. 收单业务错误码（ACQ.*）速查

来源：各 API 页「业务错误码」（open/02ekfp、05osv9、02ekfq、02ekfs、02ekft、02o6e8、02ekfr），文档原文，未实测。

**所有接口通用**

| 错误码 | 含义 | 处理 |
|---|---|---|
| `ACQ.SYSTEM_ERROR` | 系统异常 | **结果未知**：支付 / 下单要立即查询；退款用**相同 `out_request_no` 与金额**重试；查询 / 关单重新发起 |
| `ACQ.INVALID_PARAMETER` | 参数无效 | 修正参数；监控，出现即停调排查（00f7nv） |
| `ACQ.ACCESS_FORBIDDEN` | 无权限使用接口 | 未签约 / 未开通产品 / 应用未绑定商家 |
| `ACQ.PARTNER_ERROR` | 应用 APP_ID 填写错误 | 确认 APP_ID 状态 |
| `ACQ.TRADE_NOT_EXIST` | 交易不存在 | 核对订单号；订单码 / 网站支付用户尚未进收银台时也可能如此（⚠ 文档未明说） |

**下单 / 支付（pay、precreate、create）**

| 错误码 | 处理 |
|---|---|
| `ACQ.TRADE_HAS_SUCCESS` | 交易已被支付：确认是否本买家的，是则视为成功，否则换订单号 |
| `ACQ.TRADE_HAS_CLOSE` | 交易已关闭：换订单号 |
| `ACQ.CONTEXT_INCONSISTENT` | 交易信息被篡改（同一订单号参数变了）：换订单号 |
| `ACQ.TOTAL_FEE_EXCEED` | 订单总金额超过限额 |
| `ACQ.BUYER_SELLER_EQUAL` | 买卖家不能相同 |
| `ACQ.EXIST_FORBIDDEN_WORD` | 订单信息含违禁词 |
| `ACQ.APPLY_PC_MERCHANT_CODE_ERROR` | 同一订单号不能重复申请二维码（precreate） |
| `ACQ.BEYOND_PAY_RESTRICTION` / `ACQ.BEYOND_PER_RECEIPT_*` / `ACQ.MERCHANT_PERM_RECEIPT_*` | 商户收款额度 / 限额 |
| `ACQ.MERCHANT_STATUS_NOT_NORMAL` | 商户超过三个月无交易需重新激活 |
| `ACQ.RISK_MERCHANT_IP_NOT_EXIST` | 未传用户 IP（`business_params.mc_create_trade_ip`） |
| `ACQ.NOW_TIME_AFTER_EXPIRE_TIME_ERROR` | 超时时间设置不对 |
| `ACQ.SUB_GOODS_SIZE_MAX_COUNT` | 子商品明细超过 150 条 |

**退款**：见 [trade-query-refund-close.md](trade-query-refund-close.md) 第 3 节（`ACQ.DISCORDANT_REPEAT_REQUEST`、`ACQ.REASON_TRADE_REFUND_FEE_ERR`、`ACQ.SELLER_BALANCE_NOT_ENOUGH`、`ACQ.TRADE_HAS_FINISHED` 等）。
**关闭**：`ACQ.TRADE_STATUS_ERROR` / `ACQ.REASON_TRADE_STATUS_INVALID`（非待支付不能关）。
**撤销**：`ACQ.TRADE_CANCEL_TIME_OUT`、`ACQ.CANCEL_NOT_ALLOWED`、`ACQ.TRADE_HAS_FINISHED`。
**账单**：`NO_BILL_DATA`、`BILL_NOT_EXIST`、`SYSTEM_RATE_LIMIT`、`USER_RATE_LIMIT`（不带 `ACQ.` 前缀）。

⚠ 文档自相矛盾：
- 退款查询错误码表同时有 `ACQ.TRADE_NOT_EXIST` 和不带前缀的 `TRADE_NOT_EXIST`。
- 撤销接口 v3 枚举同时有 `ACQ.SYSTEM_ERROR` 和 `AQC.SYSTEM_ERROR`。
- 账单接口枚举 `INVAILID_ARGUMENTS`（拼写如此）。
匹配错误码时用「包含」而不是精确相等更稳。

---

## 5. 「结果未知」怎么处理

来源：open/00f7nv（异常处理）、00f7ns（文档原文，未实测）。

「在调用支付宝接口时，可能会遇到网络超时或支付宝未知异常（接口返回 code=20000，sub_code=isp.unknow-error 或 aop.ACQ.SYSTEM_ERROR），此时业务处理结果是未知的」：

| 接口 | 结果未知时 |
|---|---|
| `alipay.trade.pay`（付款码） | 轮询 `alipay.trade.query`；轮询结束仍未知 → `alipay.trade.cancel` |
| `alipay.trade.precreate` / 网站 / APP 下单 | 查询；**不要换订单号直接重下**（可能重复付款） |
| `alipay.trade.refund` | 用**相同 `out_request_no`、相同金额**重试，或 10 秒后退款查询 |
| `alipay.trade.query` / `close` | 直接重试 |
| `alipay.trade.cancel` | 看 `retry_flag`；仍未知则人工处理 |

「对于每一笔交易或退款，一定要得到确切的结果。」

---

## 6. 限流

- 旧版：`40005` + `isv.app-call-limited`（应用维度）/ `isv.method-call-limited`（API 维度）；v3：HTTP 429 + 同名 code。处理：降低并发。
- 退款：同一笔交易两次退款至少间隔 3 秒；退款查询建议在退款后 10 秒以上。
- 账单下载：`SYSTEM_RATE_LIMIT` / `USER_RATE_LIMIT`。
- ⚠ 文档未说明：任何接口的具体 QPS 数值。

---

## 7. 通用处理代码

```python
UNKNOWN_SUBCODES = ("isp.unknow-error", "aop.unknow-error", "ACQ.SYSTEM_ERROR")

def classify_v2(resp: dict) -> str:
    """resp 为 xxx_response 对象（旧版网关）"""
    code, sub = resp.get("code"), resp.get("sub_code", "")
    if code == "10000":
        return "OK"                    # 仍需看业务字段：trade_status / fund_change / refund_status
    if code == "10003":
        return "WAIT_BUYER_PAY"
    if code == "20000" or any(s in sub for s in UNKNOWN_SUBCODES):
        return "UNKNOWN"               # 查询确认，不要当失败
    if code in ("40005",):
        return "RATE_LIMITED"
    if sub in ("isv.invalid-signature", "isv.missing-signature-config", "isv.invalid-app-id"):
        return "CONFIG_ERROR"          # 密钥 / 环境 / app_id，重试无用
    return "FAILED"

def classify_v3(r) -> str:
    """r 为 requests.Response（v3）"""
    if r.status_code in (200, 204):
        return "OK"
    body = r.json() if r.content else {}
    code = body.get("code", "")
    if r.status_code in (500, 502) or "SYSTEM_ERROR" in code or code == "unknow-error":
        return "UNKNOWN"
    if r.status_code == 429:
        return "RATE_LIMITED"
    if code in ("invalid-signature", "missing-signature-config", "invalid-app-id", "missing-timestamp"):
        return "CONFIG_ERROR"
    return "FAILED"
```
