# 异步通知与验签（支付结果回调）

> 内容整理自 opendocs.alipay.com：open/00f7nu（当面付异步通知）、0c2c19（订单码）、00dn7l（电脑网站）、00f7nj（手机网站）、
> 00dn78（APP）、00iki4（APP 同步通知）、00dn7k / 00f7nh（快速接入中的 return_url 说明）、02ekfv（退款冲退通知），
> common/02mse7（自行实现验签）、02kf5q（SDK 验签）、02qibh（应用网关）、02kdnf（排查），open-v3/065bsc。
> 抓取于 2026-09-11。**未用真实凭证验证；也没有收到过真实通知**——本文所有行为描述均为「文档原文，未实测」。

## 目录

1. [三种「回调」别搞混](#1-三种回调别搞混)
2. [异步通知怎么来：格式与参数](#2-异步通知怎么来格式与参数)
3. [什么时候会通知（默认只有 TRADE_SUCCESS）](#3-什么时候会通知默认只有-trade_success)
4. [验签步骤（与请求签名规则不同）](#4-验签步骤与请求签名规则不同)
5. [验签后必须做的四项业务校验](#5-验签后必须做的四项业务校验)
6. [应答：必须回纯文本 success](#6-应答必须回纯文本-success)
7. [重试与幂等](#7-重试与幂等)
8. [完整 Python 处理器](#8-完整-python-处理器)
9. [同步返回：return_url 与 APP resultStatus 只能用来展示](#9-同步返回return_url-与-app-resultstatus-只能用来展示)
10. [v3 下的通知](#10-v3-下的通知)

---

## 1. 三种「回调」别搞混

| 名称 | 谁发给谁 | 用途 | 可信？ |
|---|---|---|---|
| **异步通知** `notify_url` | 支付宝服务器 → 商户服务器，POST | 支付结果 | **验签 + 业务校验后可信**，是最终依据之一 |
| 同步跳转 `return_url` | 用户浏览器 GET 回商户页面（电脑 / 手机网站支付） | 展示结果页 | **不可信**，只能作为结果页入口 |
| APP 同步结果 `resultStatus` | 支付宝 SDK → 商户 APP | 展示结果 | 不可信，以服务端为准 |
| 应用网关 | 支付宝 → 控制台配置的「应用网关」地址 | 生活号、转账到支付宝账户、红包、退款冲退完成等**非支付结果**消息 | — |

- **支付结果通知只发到下单时传的 `notify_url`**，不是控制台的「应用网关」（common/02qibh：「支付结果通知依据支付 API 中传入的 notify_url 通过 POST 请求发送，而非通用网关地址」）。**下单不传 `notify_url` 就收不到支付通知。**
- 支付结果「必须以异步通知或查询接口返回为准」，而且「需要商户同时接入支付结果异步通知与统一收单交易查询接口」——通知可能丢，查询是兜底。

---

## 2. 异步通知怎么来：格式与参数

- 方式：**HTTP POST，参数是表单（`application/x-www-form-urlencoded` 形式的 key=value）**，不是 JSON body。取值方式如 `$_POST['out_trade_no']`（00f7nu 原文）。
- `notify_url` 要求：公网可访问，URL 里不能有空格、HTML 标签等字符，**不能重定向**（重定向后支付宝收不到 `success`，会一直重发）。
- `charset` 以通知里的 `charset` 字段为准；文档 Java 示例附了 ISO-8859-1 → utf-8 的乱码修复注释。

**通知参数**（open/00f7nu，节选）

| 参数 | 必有 | 说明 |
|---|---|---|
| `notify_time` | 是 | `yyyy-MM-dd HH:mm:ss` |
| `notify_type` | 是 | `trade_status_sync` |
| `notify_id` | 是 | 通知校验 ID；**同一条通知重试时 `notify_id` 不变**，可用于去重 |
| `sign_type` / `sign` | 是 | 签名类型 / 签名 |
| `app_id` | 是 | 应用 ID |
| `auth_app_id` | 是 | 服务商代调用时为授权方 app_id |
| `trade_no` / `out_trade_no` | 是 | 支付宝交易号 / 商户订单号 |
| `trade_status` | 是 | 见第 3 节 |
| `total_amount` | 是 | 订单金额（**元**，两位小数） |
| `receipt_amount` | 是 | 商户实收（元） |
| `buyer_pay_amount` / `invoice_amount` / `point_amount` | 否 | 买家实付 / 可开票 / 集分宝 |
| `refund_fee` / `send_back_fee` | 否 | 退款通知中的总退款 / 实际退款 |
| `out_biz_no` | 否 | 退款通知里的退款流水号 |
| `buyer_id`（或 `buyer_open_id`）/ `buyer_logon_id` | 否 | 买家；新商户建议 openid |
| `seller_id` / `seller_email` | 否 | 卖家 |
| `subject` / `body` | 否 | 原样返回 |
| `gmt_create` / `gmt_payment` / `gmt_refund` / `gmt_close` | 否 | 时间 |
| `fund_bill_list` / `voucher_detail_list` | 否 | **JSON 字符串**（不是嵌套对象），需再 `json.loads` |
| `passback_params` | 否 | 下单时传的公用回传参数，**只在异步通知返回，同步不返回**（00f7nh） |

⚠ 文档自相矛盾：00f7nu 参数表对 `sign_type`、`sign` 写「如果开发者手动验签，不使用 SDK 验签，可以不传此参数」——这是通知参数、商户不需要「传」，属文档笔误；按「通知一定带 sign / sign_type」处理。

---

## 3. 什么时候会通知（默认只有 TRADE_SUCCESS）

| 触发条件 | 默认 |
|---|---|
| `TRADE_SUCCESS` 支付成功 | **触发** |
| `TRADE_FINISHED` 交易完结 | 不触发 |
| `WAIT_BUYER_PAY` 交易创建 | 不触发 |
| `TRADE_CLOSED` 交易关闭 | 不触发 |

来源：open/00f7nu「通知触发条件」表、各 API 页「触发通知类型」表（`tradeStatus.TRADE_SUCCESS` 默认开启 = 1，其余 = 0）。

- 所以：**超时关单、全额退款默认收不到通知**。退款结果靠退款接口同步返回 + 退款查询。
- 但同一篇文档第 5 节又写「只有交易通知状态为 `TRADE_SUCCESS` 或 `TRADE_FINISHED` 时……认定为买家付款成功」——处理代码要**同时认这两个状态**（产品不支持退款时付款成功就是 `TRADE_FINISHED`）。
- ⚠ 文档未说明：非默认的通知类型（TRADE_CLOSED 等）在哪里开启。

---

## 4. 验签步骤（与请求签名规则不同）

来源：common/02mse7、open/00f7nu（文档原文，未实测）。公钥模式和证书模式的**异步通知验签方式相同**。

1. 取通知的全部参数，**去掉 `sign` 和 `sign_type`**（注意：请求签名时 `sign_type` 是参与的，这里相反）。
   生活号通知例外：保留 `sign_type`（Java SDK 的 `verifyV2`）。收单支付通知用 V1 规则。
2. 对剩余参数值做 **URL decode**，按参数名字典序排序，拼成 `k=v&k=v`。
   注意：空值参数是否剔除 ⚠ 文档自相矛盾——验签页只说「除去 sign、sign_type 外凡是通知返回的参数皆是待验签的参数」，排查页（02kdnf）的解决方案里提到「未剔除空参数」会导致验签失败。按「剔除空值」实现。
3. `sign` 做 Base64 解码。
4. 用**支付宝公钥**（不是应用公钥）做 RSA 验签：`sign_type=RSA2` → SHA256WithRSA。

**SDK 方法**（文档原文）

| 语言 | 公钥模式 | 证书模式 |
|---|---|---|
| Java | `AlipaySignature.rsaCheckV1(params, ALIPAY_PUBLIC_KEY, CHARSET, sign_type)`（新名 `verifyV1`） | `AlipaySignature.rsaCertCheckV1(params, alipayPublicCertPath, "UTF-8", "RSA2")`（新名 `certVerifyV1`） |
| v3 Java / .NET / PHP SDK | 仍用 `AlipaySignature` 工具类，「使用方式与 v2 版本一样」 | 同左 |
| Python | ⚠ 文档未给出 Python SDK 的通知验签函数名 | ⚠ 同左 |

「SDK 已自动处理同步返回验签；针对异步通知，需手动调用验签方法」（common/02kf5q）——**用了 SDK 也要自己写验签这一步**。

---

## 5. 验签后必须做的四项业务校验

open/00f7nu 原文，任何一项不通过「表明本次通知是异常通知，务必忽略」：

1. `out_trade_no` 是商户系统中创建的订单号；
2. `total_amount` 等于该订单创建时的金额（**元**，按字符串 / Decimal 比较，别用 float）；
3. `seller_id`（或 `seller_email`）是这笔订单对应的收款方；
4. `app_id` 是商户自己的。

然后：按 `trade_status` 分别处理，并**过滤重复通知**（同一订单只推进一次状态）。

---

## 6. 应答：必须回纯文本 success

| 应答 | 支付宝行为 |
|---|---|
| `success` | 认为处理成功，**停止**重发 |
| `fail` 或其它任何内容 | 认为失败，按策略**重发** |

- 必须**恰好是 7 个字符 `success`**：不要返回 JSON、不要 `"success"` 带引号、不要 HTML 模板、不要换行包装、不要重定向。WAP 文档原文：「如果商家反馈给支付宝的字符不是 success 这 7 个字符，服务器会不断重发通知」。
- HTTP 状态码：「异步回调地址状态码 (HTTP 状态码) 为 200 时表示异步通知成功，返回码为 404 或 500 时则表示服务器内部错误」。
- 验签或业务校验失败：记日志并返回 `fail`（文档 Java 示例注释）。⚠ 文档未说明「已处理过的重复通知」应回什么——按幂等原则回 `success` 以停止重发。
- 退款冲退完成通知（02ekfv）应答同理（`success` / `fail`），⚠ 该页还有「是否区分大小写」一列，内容未能从抓取稿中完整读出。

---

## 7. 重试与幂等

| 来源 | 重试策略（文档原文） |
|---|---|
| 当面付 00f7nu / 订单码 0c2c19 | 未收到 `success` 时**立即重发 3 次**，仍不成功则间隔 **4m、10m、10m、1h、2h、6h、15h** |
| 电脑网站 00dn7l / 手机网站 00f7nj / APP 00dn78 | 间隔 **4m、10m、10m、1h、2h、6h、15h**（无「立即 3 次」） |
| 手机网站快速接入 00f7nh | 「会不断重发通知，直到超过 24 小时 22 分钟」 |
| 退款冲退通知 02ekfv | 25 小时内最多 8 次 |

⚠ 文档自相矛盾：各产品页对「是否先立即重发 3 次」说法不一。实现上无影响——都要求幂等处理、尽快回 `success`。

幂等要点：
- 同一条通知重试时 `notify_id` 不变；但**不同触发（如先 TRADE_SUCCESS 后 TRADE_FINISHED）是不同通知**。以「订单状态只前进不后退」做幂等最稳。
- 同一订单可能同时从「通知」和「主动查询」两条路拿到结果，两边都要走同一个幂等更新。

---

## 8. 完整 Python 处理器

按上面第 4–6 节的文档规则自行实现（官方 Python SDK 文档没有给出验签函数，故用 `cryptography`）。

```python
import base64, os
from decimal import Decimal
from urllib.parse import unquote_plus
from flask import Flask, request
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key

app = Flask(__name__)
ALIPAY_PUB = load_pem_public_key(open(os.environ["ALIPAY_PUBLIC_KEY_PEM"], "rb").read())  # 支付宝公钥
MY_APP_ID = os.environ["ALIPAY_APP_ID"]
MY_SELLER_ID = os.environ["ALIPAY_SELLER_ID"]          # 2088 开头的收款 PID

def verify_notify(params: dict) -> bool:
    sign = params.get("sign")
    if not sign:
        return False
    items = sorted((k, v) for k, v in params.items()
                   if k not in ("sign", "sign_type") and v not in (None, ""))
    content = "&".join(f"{k}={v}" for k, v in items)      # Flask 的 request.form 已完成 URL decode
    try:
        ALIPAY_PUB.verify(base64.b64decode(sign), content.encode(params.get("charset", "utf-8")),
                          padding.PKCS1v15(), hashes.SHA256())   # sign_type=RSA2
        return True
    except Exception:
        return False

@app.post("/alipay/notify")
def alipay_notify():
    params = request.form.to_dict()                      # 表单参数，不是 JSON
    if not verify_notify(params):
        return "fail", 200, {"Content-Type": "text/plain"}
    order = load_order(params["out_trade_no"])           # 你的订单存储
    if (order is None
            or Decimal(params["total_amount"]) != order.amount_yuan   # 元，Decimal 比较
            or params.get("seller_id") != MY_SELLER_ID
            or params.get("app_id") != MY_APP_ID):
        return "fail", 200, {"Content-Type": "text/plain"}
    if params["trade_status"] in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        mark_paid_idempotent(order, trade_no=params["trade_no"], notify_id=params["notify_id"])
    return "success", 200, {"Content-Type": "text/plain"}  # 恰好 7 个字符
```

---

## 9. 同步返回：return_url 与 APP resultStatus 只能用来展示

**电脑网站 / 手机网站 `return_url`**（00dn7k、00f7nh）
- 用户付款后浏览器 GET 跳回 `return_url`，URL 上带结果参数和 `sign`。「由于同步返回的不可靠性，支付结果必须以异步通知或查询接口返回为准，不能依赖同步跳转。」
- iOS 上唤起支付宝客户端付款后**不会自动跳回** `return_url`（00f7nh）。
- 用户中途退出手机网站支付，会跳到 `quit_url`。
- `passback_params` 不会出现在同步返回里。

**APP 支付同步结果**（00iki4）

| `resultStatus` | 含义 |
|---|---|
| `9000` | 订单支付成功 |
| `8000` | 正在处理中，结果未知（可能已成功），查订单 |
| `4000` | 订单支付失败 |
| `5000` | 重复请求 |
| `6001` | 用户中途取消 |
| `6002` | 网络连接出错 |
| `6004` | 支付结果未知（可能已成功），查订单 |

- `result` 字段是含 `alipay_trade_app_pay_response` 与 `sign` 的 JSON 字符串，可送回服务端验签；但文档同样建议「最终状态以服务端为准」——9000 也要等异步通知 / 查询。
- 商户 APP 可能在支付阶段被杀掉，拿不到同步结果；这时只能靠服务端。

---

## 10. v3 下的通知

- v3 文档（065bsc）：「v3 版本依然提供 AlipaySignature 工具类帮助开发者接入，使用方式与 v2 版本一样。」即支付结果通知**仍是表单 POST + 第 4 节的验签规则**，不是 v3 响应那套 `alipay-signature` 头。
- ⚠ 文档未说明：v3 下单（`POST /v3/alipay/trade/pay` 等）时 `notify_url` 放 body 字段（openapi.yaml 中 `close`、`create`、`refund/apply` 等请求体含 `notify_url` 字段），通知报文格式是否与 v2 完全一致。本 skill 按 v2 规则处理。
