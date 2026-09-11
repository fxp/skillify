# 错误码、HTTP 状态码与重试决策

> 来源：`pay.weixin.qq.com/doc/v3/merchant/` 下 4012081709（基本规则）、4012081717（HTTP 状态码）、4012072670（401 原因）、
> 各 API 页的错误码表、4014959631（退款最佳实践）、FAQ（4012791869 / 4013071200 / 4013071254），抓取于 2026-09-11；
> 另有 `wechatpay-workspace/probe-log.md` 的 13 次无凭证探测。
>
> **验证状态**：标了「无凭证探测（2026-09-11）」的行是真实返回；其余都是**文档原文，未实测**。

## 目录
1. [错误响应长什么样](#1-错误响应长什么样)
2. [HTTP 状态码](#2-http-状态码)
3. [无凭证探测到的真实错误响应](#3-无凭证探测到的真实错误响应)
4. [业务错误码总表](#4-业务错误码总表)
5. [能不能重试：决策表](#5-能不能重试决策表)
6. [频率限制汇总](#6-频率限制汇总)
7. [前端（调起支付）错误](#7-前端调起支付错误)
8. [v2 和 v3 的错误模型不同](#8-v2-和-v3-的错误模型不同)
9. [本文件 ⚠ 汇总](#9-本文件--汇总)

---

## 1. 错误响应长什么样

v3 用 **HTTP 状态码**表示结果，失败时 body 是 JSON（4012081709）：

```json
{"code": "PARAM_ERROR", "message": "参数错误",
 "detail": {"field": "/amount/currency", "value": "XYZ", "issue": "Currency code is invalid", "location": "body"}}
```

| 字段 | 说明 |
|---|---|
| `code` | 错误码，分为公共错误码和业务错误码。**写分支逻辑只能用它** |
| `message` | 错误描述。**同一个 code 可能对应多个不同的 message**，message 也可能随业务调整而改变，只能写进日志 |
| `detail` | 只有 `PARAM_ERROR` / `INVALID_REQUEST` 才返回。`field` 在 body 里时是 JSON Pointer（例如 `/amount/currency`），在 URL / query 里时是参数名；`location` 取值为 `body` / `url` / `query` |

成功的约定：有 body 返回 200，没有 body 返回 204（例如关单），已受理待处理返回 202。

公共错误码：`PARAM_ERROR`（参数错误）、`INVALID_REQUEST`（HTTP 请求不符合 APIv3 规则）、`SIGN_ERROR`（验证不通过）、`SYSTEM_ERROR`（系统异常）。

每个请求都有唯一标识，放在应答头 `Request-ID` 里，找微信支付技术支持时要提供（4012081709）。

<!-- Gap: 基本规则（4012081709）写「请求的唯一标识包含在应答的HTTP头Request-ID中」；无凭证探测（2026-09-11）P2/P3/P4/P7 调 /v3/pay/transactions/* 得到的 401 应答里没有 Request-ID 头（/v3/certificates、/v3/refund、/v3/bill 的 401 里有） -->
**无凭证探测（2026-09-11）**：`/v3/pay/transactions/*` 鉴权失败的 401 应答里**没有 `Request-ID` 头**；`/v3/certificates`、`/v3/refund/domestic/refunds`、`/v3/bill/tradebill` 的 401 里有。
所以日志代码要允许 Request-ID 为空，不能因为取不到这个头就抛异常。

## 2. HTTP 状态码

| 状态码 | 含义 | 文档给的一般处理 | 典型 code |
|---|---|---|---|
| 200 / 204 | 成功 / 成功但没有 body | —— | —— |
| 202 | 已受理，还没处理完 | **用原参数再请求一遍** | —— |
| 400 | 协议或参数不合法 | 按 `detail` 修正 | `PARAM_ERROR`、`INVALID_REQUEST` |
| 401 | 签名验证失败 | 检查签名参数和算法 | `SIGN_ERROR` |
| 403 | 没有权限，或者业务规则不允许 | 开通权限 / 按 message 处理 | `NO_AUTH`、`OUT_TRADE_NO_USED`、`NOT_ENOUGH`… |
| 404 | 资源不存在 | 检查 ID 或 URL | `ORDER_NOT_EXIST`、`RESOURCE_NOT_EXISTS` |
| 405 | 请求方法不对 | 检查方法 | —— |
| 429 | 超过频率限制 | 降频后重试。**退款场景不代表「未受理」，要先查询确认** | 见 ⚠ |
| 500 | 系统错误 | 按接口的错误指引重试 | `SYSTEM_ERROR` |
| 502 / 503 | 服务下线 / 过载保护 | 稍后重试 | `SERVICE_UNAVAILABLE` |

## 3. 无凭证探测到的真实错误响应

全部是 2026-09-11 用伪造商户号 `1900000000` 或者不带凭证请求得到的（完整记录见 `wechatpay-workspace/probe-log.md`）：

| 请求 | HTTP | 响应 body | 说明 |
|---|---|---|---|
| 不带 Authorization，调 `/v3/certificates`、`/v3/refund/domestic/refunds`、`/v3/bill/tradebill`，主域名和 `api2` 备域名都一样 | 401 | `{"code":"SIGN_ERROR","message":"Http头Authorization值格式错误，请参考《微信支付商户REST API签名规则》"}` | 缺 Authorization 返回的是 401，不是 400 |
| 不带 Authorization，或者用 `Bearer`，调 `/v3/pay/transactions/*` | 401 | `{"code":"SIGN_ERROR","message":"签名信息错误，验签失败"}` | 同样是缺头，交易类接口返回的 message 不一样 |
| Authorization 格式正确，签名是伪造的 | 401 | `{"code":"SIGN_ERROR","message":"签名错误"}` | —— |
| Authorization 里的 timestamp 是 2019 年的 | 401 | `{"code":"SIGN_ERROR","message":"Http头Authorization中的timestamp与发起请求的时间不得超过5分钟"}` | 时间窗口检查在签名校验之前 |
| 去掉 User-Agent（`/v3/certificates`、`/v3/refund/*`） | **400** | `{"code":"INVALID_REQUEST","message":"Http头缺少Accept或User-Agent"}` | 这些接口 UA 检查在鉴权之前；交易类 `/v3/pay/transactions/*` 去掉 UA 仍是 401 `SIGN_ERROR`（2026-09-11 复测） |
| `GET /v3/pay/transactions/native`（这个接口要用 POST） | 405 | 空 body | —— |
| 不存在的 path | 404 | 空 body | 可以和「path 存在、但鉴权失败」的 401 区分开 |
| 以上所有 4xx | —— | 应答头里**没有**任何 `Wechatpay-*` 签名头 | 所以 4xx 不能验签，见 `auth-signing.md` §5 |

结论：同一个 `401 SIGN_ERROR` 至少有 4 种 message。**错误处理只按 `code` 分支**，message 原样写日志就好。

## 4. 业务错误码总表

同一个 code 在不同接口里 HTTP 状态可能不一样（例如 `MCH_NOT_EXISTS`：下单 / 查单是 400，退款是 404），所以**不要硬编码「code → HTTP 状态」的映射**。

| code | HTTP | 出现在 | 含义 | 处理 |
|---|---|---|---|---|
| `PARAM_ERROR` | 400 | 全部 | 参数错误 | 看 `detail.field` 修，不要重试 |
| `INVALID_REQUEST` | 400 | 全部 | 不符合 v3 规则或业务规则（例如退款时「您的请求参数与订单信息不一致」） | 看 message 修；证书、退款接口缺 UA 也是这个码（探测） |
| `APPID_MCHID_NOT_MATCH` | 400 | 下单 | appid 和 mchid 没有绑定 | 去商户平台绑定 |
| `MCH_NOT_EXISTS` | 400 / 404 | 下单、查单、关单 / 退款 | 商户号不存在 | 核对 mchid |
| `ORDER_CLOSED` | 400 | Native 下单 | 订单已关闭 | 换新的 out_trade_no 重新下单 |
| `NO_STATEMENT_EXIST` | 400 | 申请账单 | 那天没有账单 | 正常结果，不要重试 |
| `STATEMENT_CREATING` | 400 | 申请账单 | 账单还在生成 | 10 点后再试；之后每半小时试一次 |
| `SIGN_ERROR` | 401 | 全部 | 签名 / 证书问题 | 修代码，见 `auth-signing.md` §9 |
| `NO_AUTH` | 403 | 下单；下载账单 | 产品权限没开 / 下载账单的商户和申请账单的商户不一致 | 开通权限 / 统一商户号 |
| `OUT_TRADE_NO_USED` | 403 | 下单 | 商户订单号重复（同一个单号换了参数或换了下单接口） | 用原来的参数重试，或者换新单号 |
| `RULE_LIMIT` | 403 | H5 下单、查单、关单 | 业务规则限制 | 看 message |
| `TRADE_ERROR` | 403 | 查单、关单 | 因为业务原因交易失败 | 看 message |
| `NOT_ENOUGH` | 403 | 申请退款 | 商户余额不足 | 充值后**原单原参数**重试 |
| `USER_ACCOUNT_ABNORMAL` | 403 | 申请退款 | 用户账号异常（已注销） | 线下退款 |
| `ORDER_NOT_EXIST` | 404 | 查单 | 订单不存在 | 核对单号 / 下单是否成功 |
| `RESOURCE_NOT_EXISTS` | 404 | 申请退款、查询退款 | 订单不存在或没付款 / 退款单不存在 | 申请退款前先查单；查退款返回 404 说明「没受理」，可以原单重试 |
| `FREQUENCY_LIMITED` | 429 | 全部 | 频率超限 | 降频；退款先查询 |
| `SYSTEM_ERROR` | 500 | 全部 | 系统错误 / 超时 | **相同参数**重试（下单用同一个 out_trade_no，退款用同一个 out_refund_no） |
| `SERVICE_UNAVAILABLE` | 502 / 503 | 全部 | 服务不可用 | 稍后重试，可以切换到备域名 |
| `TRADE_OVERDUE` | ⚠ 未说明 | 申请退款（FAQ） | 订单已经超过一年 | 不能再退，改走商家转账或线下退款 |
| `REFUND_FEE_MISMATCH` | ⚠ 未说明 | 申请退款（FAQ） | 订单金额或退款金额和之前的请求不一致 | 核对 amount；同一个 out_refund_no 的参数不能变 |

平台证书下载工具如果返回 `RESOURCE_NOT_EXISTS`「无可用的平台证书，请在商户平台-API安全申请使用微信支付公钥。」，说明这个商户号只能用微信支付公钥（4012076511）。

## 5. 能不能重试：决策表

```python
from wechatpay_v3 import WechatPayError

def classify(e: WechatPayError) -> str:
    if e.status in (500, 502, 503) or e.code in ("SYSTEM_ERROR", "SERVICE_UNAVAILABLE"):
        return "retry_same_params"          # 相同参数、相同单号重试，可以切到 api2 备域名
    if e.status == 429 or e.code == "FREQUENCY_LIMITED":
        return "backoff_then_query"         # 先降频；如果是资金类操作（退款），先查询再决定
    if e.code == "STATEMENT_CREATING":
        return "retry_later"                # 半小时后再试
    if e.status == 401:
        return "fix_signing"                # 代码或证书有问题，重试没用
    return "do_not_retry"                   # 400 / 403 / 404：参数、权限、业务问题
```

| 场景 | 应该做的 | 不应该做的 |
|---|---|---|
| 下单超时，或者 500 | 用**同一个 out_trade_no、完全相同的参数**再调一次下单 | 换新单号（会产生两笔待支付订单，用户可能付两次） |
| 退款超时，或者 429 / 500 | 先 `GET /v3/refund/domestic/refunds/{out_refund_no}`；返回 404 `RESOURCE_NOT_EXISTS` 再原单重试 | 换新的 out_refund_no |
| 查单或关单是 500 | 直接重试（查单、关单是幂等的，关单支持重入） | —— |
| 202 | 用原参数再请求一遍 | 当成失败处理 |
| 网络层超时（没有收到 HTTP 响应） | 当作「结果未知」，按上面对应的场景处理 | 当作失败 |

## 6. 频率限制汇总

| 接口 | 限制（文档原文） |
|---|---|
| 申请退款 | 同一商户号：调用成功的请求 150 QPS，**调用失败的请求 6 QPS**；一个月以前的订单报「频率限制，1个月之前的订单请降低申请频率再重试」时，调整退款时间后用原参数重试 |
| 查询单笔退款 | 同一商户号 300 QPS |
| 发起异常退款 | 150 QPS |
| 下载平台证书 | 单个商户号 1000 次/秒 |
| 申请资金账单 | 商户号维度 3 QPS |
| 下单 / 查单 / 关单 / 申请交易账单 | ⚠ 文档未说明具体数值 |

## 7. 前端（调起支付）错误

| 端 | 返回值 | 含义 |
|---|---|---|
| JSAPI | `get_brand_wcpay_request:ok` / `:cancel` / `:fail` | 成功（**还要查单确认**）/ 用户取消 / 失败 |
| 小程序 | `requestPayment:ok` / `requestPayment:fail cancel` / `requestPayment:fail <详情>` | 同上；`errno: 102, jsapi has no permission` 表示公众平台限制了这个小程序的支付权限 |
| APP | `errCode` = `0` / `-1` / `-2` | 成功 / 错误（签名错误、AppID 没注册或不匹配…）/ 用户取消 |

常见前端报错（FAQ 原文节选）：
- 「当前页面的URL未注册」：没配 JSAPI 支付授权目录。
- 「支付验证签名失败」：prepay_id 格式不对（APP 不带 `prepay_id=` 前缀，JSAPI 和小程序带），或者下单和调起支付用的不是同一份商户证书。
- 「下单账号与支付账号不一致」：下单时的 openid 不是当前在付款的用户。
- H5「商家参数格式有误」「支付请求已失效」「请在微信外打开订单」：h5_url 被改动过 / 超过 5 分钟 / 在微信内置浏览器里打开了 H5 支付。

## 8. v2 和 v3 的错误模型不同

**无凭证探测（2026-09-11）**：用伪造商户号 POST v2 接口 `https://api.mch.weixin.qq.com/pay/orderquery`，返回：

```
HTTP/1.1 200 OK
Content-Type: text/plain

<xml><return_code><![CDATA[FAIL]]></return_code>
<return_msg><![CDATA[签名错误]]></return_msg>
</xml>
```

| | v2（本 skill 不覆盖） | v3 |
|---|---|---|
| URL | `/pay/*`、`/secapi/*`… | `/v3/*` |
| 报文 | XML | JSON |
| 失败时 | **HTTP 200**，body 里 `return_code=FAIL` | HTTP 4xx / 5xx，body 里有 `code` |
| 签名 | APIv2 密钥 MD5 / HMAC-SHA256 | 商户 API 证书私钥 RSA |

同一个商户号可以同时用 v2 和 v3（FAQ 4016179629）。但同一个流程里不要一半用 v2 一半用 v3：
错误处理、回调格式（退款回调可能变成 XML，见 `refunds.md` §7）、金额字段名（`total_fee` 和 `amount.total`）都对不上。

## 9. 本文件 ⚠ 汇总

- ⚠ 文档自相矛盾：429 对应的错误码，HTTP 状态码页（4012081717）写的是 `RATELIMIT_EXCEEDED`，而各 API 页的错误码表写的都是 `FREQUENCY_LIMITED`。
  代码对 429 **按状态码处理**，两个 code 都要兼容。
- ⚠ 文档未说明：下单、查单、关单、申请交易账单的具体频率上限。
- ⚠ 文档未说明：FAQ 里出现的 `TRADE_OVERDUE`、`REFUND_FEE_MISMATCH` 对应的 HTTP 状态码。
- `<!-- Gap -->`（§1）：文档说应答头里有 `Request-ID`，实际交易类接口的 401 应答里没有。
