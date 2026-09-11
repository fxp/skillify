# 回调通知：支付成功与退款结果的验签、解密、应答

> 来源：`pay.weixin.qq.com/doc/v3/merchant/` 下 4012791861（支付成功回调）、4013071196（退款结果通知）、4012071382（解密回调报文）、
> 4012075420（回调通知注意事项）、4013053249（签名探测流量）、4013053283（回调缺签名头）、4013053274（Tag mismatch）、
> 4012075249（回调与查单实现指引）、4012154180（公钥切换期的回调兼容），抓取于 2026-09-11。
>
> **验证状态**：没有收到过真实回调。报文结构、重试节奏、IP 段都是文档原文，未实测。
> 解密代码的参数约定（nonce 和 associated_data 按 UTF-8 原串传，密文先 base64 解码）用本地加密再解密的往返测试验证过（2026-09-11，离线），
> 但没有拿真实密文验证过。验签函数 `verify_wechatpay_signature` 在 `auth-signing.md` §3。

## 目录
1. [两种回调一览](#1-两种回调一览)
2. [回调报文结构](#2-回调报文结构)
3. [处理流程：8 步](#3-处理流程8-步)
4. [解密 AEAD_AES_256_GCM](#4-解密-aead_aes_256_gcm)
5. [完整示例（Flask）](#5-完整示例flask)
6. [应答与重试机制](#6-应答与重试机制)
7. [支付成功回调：解密后的字段](#7-支付成功回调解密后的字段)
8. [退款结果回调：解密后的字段](#8-退款结果回调解密后的字段)
9. [notify_url 与网络要求](#9-notify_url-与网络要求)
10. [收不到回调 / 验签失败的排查](#10-收不到回调--验签失败的排查)
11. [本文件 ⚠ 汇总](#11-本文件--汇总)

---

## 1. 两种回调一览

| 回调 | 什么时候发 | 发到哪 | `event_type` | `resource.original_type` |
|---|---|---|---|---|
| 支付成功 | 用户**支付成功**后（五种产品都一样）。**支付失败不会发回调** | 下单时传的 `notify_url` | `TRANSACTION.SUCCESS` | `transaction` |
| 退款结果 | 退款单状态变成成功、关闭或异常时 | 申请退款时传的 `notify_url`；没传就发到商户平台配置的地址（**那样收到的是 v2 XML 格式**，见 `refunds.md` §7） | `REFUND.SUCCESS` / `REFUND.ABNORMAL` / `REFUND.CLOSED` | `refund` |

两种回调都是 `POST` + JSON body，业务数据都加密放在 `resource` 里，验签、解密、应答的规则完全一样。

## 2. 回调报文结构

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string(36) | 通知 ID，每条通知唯一，可以用来去重 |
| `create_time` | string(32) | 通知创建时间，RFC3339 格式 |
| `event_type` | string(32) | 见 §1 |
| `resource_type` | string(32) | 固定是 `encrypt-resource` |
| `summary` | string | 摘要，例如「支付成功」「退款成功」 |
| `resource.algorithm` | string(32) | 目前只有 `AEAD_AES_256_GCM` |
| `resource.ciphertext` | string | base64 编码的密文 |
| `resource.associated_data` | string | 附加数据，**可能为空** |
| `resource.nonce` | string | 解密用的随机串，和签名用的随机串无关 |
| `resource.original_type` | string | `transaction` / `refund` |

```json
{"id": "EV-2018022511223320873", "create_time": "2015-05-20T13:29:35+08:00",
 "resource_type": "encrypt-resource", "event_type": "TRANSACTION.SUCCESS", "summary": "支付成功",
 "resource": {"original_type": "transaction", "algorithm": "AEAD_AES_256_GCM",
              "ciphertext": "…", "associated_data": "", "nonce": "…"}}
```

回调请求带着 4 个签名头：`Wechatpay-Serial`（验签用的平台证书序列号或微信支付公钥 ID）、`Wechatpay-Signature`、`Wechatpay-Timestamp`、`Wechatpay-Nonce`。

## 3. 处理流程：8 步

| # | 做什么 | 为什么（文档依据） |
|---|---|---|
| 1 | **取原始 body 字节**，先不要让框架解析 JSON | 验签用的是原始报文，任何重新序列化都会导致验签失败（4013053249） |
| 2 | 取 4 个 `Wechatpay-*` 头 | 头不齐，多半是代理或 CDN 把它们过滤掉了（4013053283） |
| 3 | 时间戳和本机相差 >5 分钟就拒绝 | 防重放（4013053420）。微信支付重发时会重新生成时间戳和签名 |
| 4 | 按 `Wechatpay-Serial` 选公钥：`PUB_KEY_ID_…` 用微信支付公钥，否则用对应的平台证书 | 4012791861。从平台证书切到公钥的灰度期间，**两种签名的回调都会收到**（4013038816） |
| 5 | 验签：`时间戳\n随机串\n原始body\n`，SHA256withRSA | 验签失败就回 4xx/5xx，微信支付会带着正确签名重发 |
| 6 | 用 APIv3 密钥解密 `resource` | §4 |
| 7 | **幂等**地更新业务状态：同一个订单只处理一次，已经处理过就直接回成功 | 「同样的通知可能会多次发送给商户系统」（4012075420） |
| 8 | **5 秒内**回 `200` 或 `204`，不带 body。耗时的业务逻辑放到异步任务里做 | 5 秒没回就算失败，会触发重试（4012791861） |

- 签名探测：微信支付会在极少数回调里故意给错误签名，签名值以 `WECHATPAY/SIGNTEST/` 开头。
  **不能特殊放行**，要照常验签，验不过就回 4xx/5xx（4013053249）。直接回 200 或者跳过验签的实现，会被这类流量暴露出来。
- 以下是本 skill 的建议，文档没有明确要求：解密后核对 `mchid`（和 `appid`）确实是你自己的；核对 `amount.total` 和本地订单金额一致，再标记订单为已支付。

## 4. 解密 AEAD_AES_256_GCM

- 密钥：**APIv3 密钥**，32 个字符，直接取它的 UTF-8 字节。不要做 hex 或 base64 解码，也**不能用 APIv2 密钥**。
- nonce：`resource.nonce` 原串的 UTF-8 字节。
- AAD：`resource.associated_data` 原串的 UTF-8 字节，可能是空串。下载平台证书时这个值固定是 `"certificate"`。
- 密文：`resource.ciphertext` 先 base64 解码。解码后末尾 16 字节是认证 tag，Python 的 `AESGCM.decrypt` 直接传整段就行。
- 文档 Java 提示：取 JSON 里的值时只要引号**里面**的内容。例如 `"nonce":"123"` 要取 `123`，不是带引号的 `"123"`。

```python
# notifications_helpers.py
import base64, json
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def decrypt_resource(resource: dict, apiv3_key: str, parse_json: bool = True):
    """回调 resource 和 /v3/certificates 的 encrypt_certificate 都用这个函数解密。"""
    if resource.get("algorithm") != "AEAD_AES_256_GCM":
        raise ValueError(f"unsupported algorithm: {resource.get('algorithm')}")
    key = apiv3_key.encode("utf-8")
    if len(key) != 32:
        raise ValueError("APIv3 key must be 32 bytes")
    plaintext = AESGCM(key).decrypt(
        resource["nonce"].encode("utf-8"),
        base64.b64decode(resource["ciphertext"]),
        (resource.get("associated_data") or "").encode("utf-8"),
    )  # 密钥、nonce、AAD 任何一个不对，都会抛出 cryptography.exceptions.InvalidTag
    text = plaintext.decode("utf-8")
    return json.loads(text) if parse_json else text
```

解密报 Tag mismatch / `InvalidTag` 的三个原因（4013053274，文档原文）：用错了 APIv3 密钥（例如用了别的商户号的密钥，或者用了 APIv2 的 key）；
密文不对（注意报文里的密文是 base64 编码过的）；解密时漏传了 associated_data。

Java 如果报 `InvalidKeyException: Illegal key size`，是老版本 JDK 限制了 AES-256，要升级到 8u162 以上（4013053271）。

## 5. 完整示例（Flask）

```python
import json, os
from flask import Flask, request

from wechatpay_v3 import verify_wechatpay_signature      # auth-signing.md §3
from notifications_helpers import decrypt_resource         # §4

app = Flask(__name__)
APIV3_KEY = os.environ["WECHATPAY_APIV3_KEY"]

@app.post("/wechatpay/notify")            # 不要给这个路由加登录校验（4012075420）
def wechatpay_notify():
    raw = request.get_data()              # 原始字节
    try:
        verify_wechatpay_signature(request.headers, raw)
    except ValueError as e:
        return {"code": "FAIL", "message": str(e)}, 401      # 4xx/5xx 都可以，微信支付会重发
    event = json.loads(raw)
    try:
        data = decrypt_resource(event["resource"], APIV3_KEY)
    except Exception:
        return {"code": "FAIL", "message": "decrypt failed"}, 500
    if event["event_type"] == "TRANSACTION.SUCCESS":
        enqueue("payment_success", notify_id=event["id"], data=data)   # 放进队列，异步幂等处理
    elif event["event_type"].startswith("REFUND."):
        enqueue("refund_result", notify_id=event["id"], data=data)
    return "", 204                         # 200 或 204，都不需要 body


def handle_payment_success(data: dict) -> None:   # 队列消费者
    order = load_order(data["out_trade_no"])
    if order.status == "PAID":                     # 已经处理过：直接返回，保证幂等
        return
    if data["trade_state"] != "SUCCESS" or data["amount"]["total"] != order.total_fen:
        alert("callback mismatch", data)           # 本 skill 的建议，文档没要求
        return
    order.mark_paid(transaction_id=data["transaction_id"], paid_at=data["success_time"])
```

FastAPI 写法一样：用 `body = await request.body()` 拿原始字节，`request.headers` 查头的时候不区分大小写。

## 6. 应答与重试机制

| 情况 | 商户应答 | 微信支付的行为（文档原文） |
|---|---|---|
| 验签通过、已经收下 | HTTP `200` 或 `204`，**不需要 body** | 不再发这条通知。万一又收到重复通知，继续回 200，做好重入 |
| 验签失败或处理失败 | HTTP `4XX` 或 `5XX`，body 是 `{"code": "FAIL", "message": "失败原因"}` | 按下面的节奏重发 |
| 5 秒内没有应答 | —— | 算失败，同样重发 |

重发间隔：**15s / 15s / 30s / 3m / 10m / 20m / 30m / 30m / 30m / 60m / 3h / 3h / 3h / 6h / 6h**，最多 15 次。支付回调和退款回调都是这个节奏。

- 这里的应答规则是 v3 的：HTTP 状态码加可选的 JSON。v2 回调是 XML 格式、应答方式也不一样，两套代码不能混用（本 skill 不覆盖 v2）。
- 「商户系统不能仅依赖回调通知获取结果，需结合查询接口使用」。重试 15 次都失败、或者回调一直不来，就靠查单兜底，见 `orders.md` §5。
- 回调没法在线上测试：文档说「微信支付未提供线上测试回调接口」，只能在生产环境用真实支付来测（FAQ 4012791869）。

## 7. 支付成功回调：解密后的字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `appid` / `mchid` / `out_trade_no` | string | 下单时传的值 |
| `transaction_id` | string(32) | 微信支付订单号 |
| `trade_type` | string(16) | `JSAPI` / `NATIVE` / `APP` / `MWEB` / `MICROPAY` / `FACEPAY` |
| `trade_state` | string(32) | 支付成功回调里是 `SUCCESS` |
| `trade_state_desc` | string(256) | 状态描述 |
| `bank_type` | string(32) | 例如 `CMC`、`ICBC_DEBIT`、`OTHERS` |
| `attach` | string(128) | 下单时传了才有 |
| `success_time` | string(64) | 支付完成时间，RFC3339 格式 |
| `payer.openid` | string(128) | 付款用户 |
| `amount.total` / `amount.payer_total` | int | **分**。`payer_total` = 总金额 − 代金券金额 |
| `amount.currency` / `amount.payer_currency` | string | `CNY` |
| `scene_info.device_id` | string | 下单时传了才有 |
| `promotion_detail[]` | array | 用了代金券才有 |

```json
{"transaction_id": "1217752501201407033233368018", "mchid": "1230000109", "appid": "wxd678efh567hg6787",
 "out_trade_no": "1217752501201407033233368018", "trade_type": "APP", "trade_state": "SUCCESS",
 "trade_state_desc": "支付成功", "bank_type": "CMC", "attach": "自定义数据",
 "success_time": "2018-06-08T10:34:56+08:00", "payer": {"openid": "oUpF8uMuAJO_M2pxb1Q9zNjWeS6o"},
 "amount": {"total": 100, "payer_total": 100, "currency": "CNY", "payer_currency": "CNY"}}
```

## 8. 退款结果回调：解密后的字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `mchid` / `out_trade_no` / `transaction_id` | string | —— |
| `out_refund_no` / `refund_id` | string | 商户退款单号 / 微信支付退款单号 |
| `refund_status` | string(32) | `SUCCESS` / `CLOSED` / `PROCESSING` / `ABNORMAL` |
| `success_time` | string(64) | 退款成功时才有 |
| `user_received_account` | string(64) | 退款入账账户描述，例如「招商银行信用卡」 |
| `amount.total` / `refund` / `payer_total` / `payer_refund` | int | **分** |

**字段名注意**：退款回调里状态字段叫 **`refund_status`**，而申请退款、查询退款接口的应答里叫 **`status`**。两边复用同一段解析代码会取不到值。
回调里也**没有** `channel` 和 `funds_account` 这些字段，需要的话去调查询退款接口。

```json
{"mchid": "1900000100", "transaction_id": "1008450740201411110005820873", "out_trade_no": "20150806125346",
 "refund_id": "50200207182018070300011301001", "out_refund_no": "7752501201407033233368018",
 "refund_status": "SUCCESS", "success_time": "2018-06-08T10:34:56+08:00",
 "user_received_account": "招商银行信用卡",
 "amount": {"total": 999, "refund": 999, "payer_total": 999, "payer_refund": 999}}
```

## 9. notify_url 与网络要求

`notify_url` 的填写规则（4012075420，文档原文）：
- 必须以 `https://` 开头，写完整路径。只写域名不行，写 `http://`、`./PayNotify.aspx`、IP 地址、`localhost` 或内网地址都不行。
- **不能带参数**（`?order=…` 这种不行）。要区分订单，就从解密后的 `out_trade_no` 里取。
- 域名要能解析，国内服务器需要 ICP 备案。
- 回调处理代码**不能做登录态校验**。

如果防火墙对入站 IP 有限制，需要放行下面这些网段（文档原文，抓取于 2026-09-11，以文档最新版本为准）：

| 用途 | IP |
|---|---|
| 支付回调 | 上海电信 `101.226.103.0/25`、上海联通 `140.207.54.0/25`、上海 CAP `121.51.58.128/25`、深圳电信 `183.3.234.0/25`、深圳联通 `58.251.80.0/25`、深圳 CAP `121.51.30.128/25`、香港 `203.205.219.128/25`、广州腾讯云 `81.71.199.64`、`81.71.198.25`、`81.71.199.59` |
| 退款结果通知、分账动账通知（新增） | `175.24.214.208`、`175.24.211.24`、`175.24.213.135`、`109.244.180.23`、`114.132.203.119`、`43.139.43.69` |
| 风险订单通知（新增） | `43.140.107.97`、`43.140.107.217`、`43.140.107.141` |

WAF 或 CC 防护可能会把回调请求当成恶意请求拦掉，需要加白名单。

## 10. 收不到回调 / 验签失败的排查

| 现象 | 可能原因（文档原文归纳） |
|---|---|
| 一条回调都收不到 | **商户没设置 APIv3 密钥**（这种情况下微信支付不会发回调）；下单没传 `notify_url`；地址不是 https、是内网地址或者拼错；防火墙 / 安全组 / WAF 拦截；DNS 解析失败 |
| 退款回调收不到 | 申请退款时没传 `notify_url`，商户平台也没配置 |
| 收到的退款回调是 XML | 见 §1 和 `refunds.md` §7 |
| 回调里没有 `Wechatpay-*` 头 | 反向代理 / CDN 过滤了这些扩展头；改代理配置或者直连（4013053283） |
| 验签偶尔失败 | 签名以 `WECHATPAY/SIGNTEST/` 开头的是探测流量，失败是**正确**结果；或者在公钥切换灰度期间只支持了一种公钥 |
| 验签总是失败 | 用解析后重新序列化的 body 验签；验签串少了最后的 `\n`；`Wechatpay-Serial` 对应的公钥没配 |
| 回调验签报 `Last unit does not have enough valid bits` | 文档 FAQ（4012791869）里有这个问题，一般是签名串被截断或者 base64 解码出错 ⚠ 本 skill 没有抄录 FAQ 原答案 |
| 解密 `InvalidTag` / Tag mismatch | §4 列的三个原因 |

## 11. 本文件 ⚠ 汇总

- ⚠ 文档说法不一：选公钥的方式。支付回调页（4012791861）说「看 `Wechatpay-Serial` 是不是 `PUB_KEY_ID_` 开头来区分」；
  切换指引的 PHP 部分（4012154180）说「不应差别对待此字段值的构成」，要按序列号去映射。上面的代码用「serial → 公钥」映射表按原值查，两种说法都兼容。
- ⚠ 文档未说明：支付回调和退款回调里 `resource.associated_data` 的实际取值。示例是空串，代码按原值传入即可。
- ⚠ 文档自相矛盾：验签失败时的应答。正文说「需返回应答报文」，但应答参数表里 `code` / `message` 两个字段都标的是选填。按正文写，回 `{"code":"FAIL","message":"…"}`。
- ⚠ 文档未说明：`Last unit does not have enough valid bits` 的原因。本 skill 没有抄录 FAQ 的原始答案，§10 的解释是推断。
