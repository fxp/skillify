# 下单与前端调起支付：JSAPI / 小程序 / Native / H5 / APP

> 来源：`pay.weixin.qq.com/doc/v3/merchant/` 下 4012791856 / 4012791897（JSAPI 与小程序下单）、4012791877（Native 下单）、4012791834（H5 下单）、
> 4013070347（APP 下单）、4012791857 / 4012791898 / 4013070351 / 4012791835 / 4012791878（各种调起支付）、4012365339–4012365341（调起支付签名）、
> 4012791870 / 4012791831（开发指引）、4012791869 / 4012791890 / 4012791910（FAQ），抓取于 2026-09-11。
>
> **验证状态**：没有用真实凭证下过单。错误码和报错文本都是文档原文，未实测。调起支付签名算法用文档测试私钥离线复算通过。
> 签名和请求怎么发，见 `auth-signing.md`。Python 示例都依赖其中的 `wechatpay_v3.py`。

## 目录
1. [先选产品](#1-先选产品)
2. [下单公共参数](#2-下单公共参数)
3. [JSAPI / 小程序下单](#3-jsapi--小程序下单)
4. [Native 下单](#4-native-下单)
5. [H5 下单](#5-h5-下单)
6. [APP 下单](#6-app-下单)
7. [前端调起支付与调起签名](#7-前端调起支付与调起签名)
8. [下单错误码](#8-下单错误码)
9. [上线前要在商户平台 / 公众平台配好的东西](#9-上线前要在商户平台--公众平台配好的东西)
10. [本文件 ⚠ 汇总](#10-本文件--汇总)

---

## 1. 先选产品

| 用户在哪付款 | 产品 | 下单 Endpoint | 下单返回 | 前端怎么拉起 | appid 类型 |
|---|---|---|---|---|---|
| 微信内打开的网页（公众号 / 服务号） | JSAPI | `POST /v3/pay/transactions/jsapi` | `prepay_id`（2 小时有效） | `WeixinJSBridge.invoke('getBrandWCPayRequest', …)` | 公众号 / 服务号 |
| 微信小程序 | 小程序支付 | `POST /v3/pay/transactions/jsapi`（**和 JSAPI 共用同一个接口**） | `prepay_id` | `wx.requestPayment` | 小程序 |
| PC 网页、线下展示二维码 | Native | `POST /v3/pay/transactions/native` | `code_url`（2 小时有效） | 把 `code_url` 转成二维码 | 三种 appid 都可以 |
| 手机浏览器（**非**微信内置浏览器） | H5 | `POST /v3/pay/transactions/h5` | `h5_url`（**5 分钟**有效） | 页面跳转到 `h5_url` | 三种 appid 都可以 |
| 自家 APP | APP | `POST /v3/pay/transactions/app` | `prepay_id`（2 小时有效） | OpenSDK `sendReq(PayReq)` | 开放平台移动应用 |

- 五种产品只有「下单」和「调起支付」不一样。查单、关单、退款、账单、回调这些后续接口完全相同（Native FAQ 4012791890）。
- 本文件不覆盖：付款码支付（V2 接口）、刷脸支付、合单支付、服务商模式下单（`sub_mchid` 那一套，文档在 `/doc/v3/partner/`）。

## 2. 下单公共参数

以 JSAPI 为基准，其他产品的差异见各节。所有字段都放在 JSON body 里。

| 参数 | 类型 | 必填 | 说明（文档原文归纳） |
|---|---|---|---|
| `appid` | string(32) | 是 | 必须和 `mchid` 有绑定关系，否则报 `APPID_MCHID_NOT_MATCH` |
| `mchid` | string(32) | 是 | 必须和 Authorization 里的 mchid 相同 |
| `description` | string(127) | 是 | 商品描述，用户在微信账单里能看到 |
| `out_trade_no` | string(32) | 是 | 6–32 个字符，只能是数字、大小写字母和 `_-|*`，同一商户号下唯一 |
| `time_expire` | string(64) | 否 | 支付结束时间，RFC3339 格式，例如 `2015-05-20T13:29:35+08:00`。不传的话，超过 7 天未支付就不能再付。不能早于下单后 1 分钟（早了会被自动调到 1 分钟）。上限见下面的 ⚠ |
| `attach` | string(128) | 否 | 商户自定义数据，查单、回调、交易账单里会原样返回 |
| `notify_url` | string(255) | 是 | 支付成功回调地址。必须 `https://`、外网可访问、**不能带参数**（4012075420） |
| `goods_tag` | string(32) | 否 | 订单优惠标记（代金券用） |
| `support_fapiao` | boolean | 否 | 电子发票入口 |
| `amount.total` | integer | 是 | **单位是分，整数，必须大于 0**。1 元写 `100` |
| `amount.currency` | string(16) | 否 | 固定填 `CNY` |
| `payer.openid` | string(128) | JSAPI / 小程序必填 | 用户在**这个 appid** 下的 openid。Native / H5 / APP 没有 `payer` 字段 |
| `detail` | object | 否 | 商品详情，去掉空格换行后不超过 6144 字节。`detail.goods_detail[].unit_price` 的单位是分 |
| `scene_info.payer_client_ip` | string(45) | H5 必填，其他选填 | 用户终端 IP，支持 IPv4 / IPv6 |
| `scene_info.device_id` / `store_info` | —— | 否 | 门店和设备信息 |
| `settle_info.profit_sharing` | boolean | 否 | `true` 表示这笔要分账，支付成功后资金会被冻结（分账本 skill 不覆盖） |

- ⚠ 文档自相矛盾：`time_expire` 的上限，JSAPI / H5 / APP 下单页写「需在下单时间的 15 天以内，超过自动调整为第 15 天」，
  Native 下单页写「7 天以内，超过自动调整为第 7 天」。同时各开发指引又说「不传则默认 7 天」。稳妥做法：不要超过 7 天。
- 金额出错的报错（FAQ 4012791869，文档原文，未实测）：`amount.total` 传 0 会得到
  `{"code": "PARAM_ERROR","message": "输入源“/body/amount/total”映射到数值字段“总金额”规则校验失败，值低于最小值 1"}`。
- **重复下单**（FAQ）：同一个 `out_trade_no` 没付款前可以再调一次下单，但**所有参数必须和第一次完全一样**。
  换了参数、或者换成另一种下单接口，就会报商户订单号重复（API 页写的是 `403 OUT_TRADE_NO_USED`）。
  prepay_id 过期后（2 小时），用原来的下单参数再调一次下单接口就能拿到新的 prepay_id（4012791870）。
- ⚠ 文档自相矛盾：FAQ 说参数不一致时会报「201 商户订单号重复」，这个 `201` 是 v2 风格的错误码；v3 API 页写的是 HTTP 403 + `OUT_TRADE_NO_USED`。
- 前端的下单按钮要做防抖，避免重复支付（4012791870）。

## 3. JSAPI / 小程序下单

**Endpoint**: `POST /v3/pay/transactions/jsapi`
**用途**：微信内网页（JSAPI）和小程序共用，拿到 `prepay_id` 后交给前端拉起支付。小程序场景把 `appid` 换成小程序的 appid。

**关键参数**：§2 全部，外加必填的 `payer.openid`。openid 要和 appid 对应：同一个用户在公众号和小程序下的 openid 不一样，
混用会报「appid与openid不匹配」（FAQ）。

**示例请求**

```bash
curl -X POST https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi \
  -H 'Authorization: WECHATPAY2-SHA256-RSA2048 mchid="1230000109",...' \
  -H 'Accept: application/json' -H 'Content-Type: application/json' -A 'my-shop-backend/1.0' \
  -d '{"appid":"wxd678efh567hg6787","mchid":"1230000109","description":"Image形象店-深圳腾大-QQ公仔","out_trade_no":"1217752501201407033233368018","notify_url":"https://www.weixin.qq.com/wxpay/pay.php","amount":{"total":100,"currency":"CNY"},"payer":{"openid":"oUpF8uMuAJO_M2pxb1Q9zNjWeS6o"}}'
```

```python
import os
from wechatpay_v3 import request, MCHID

def jsapi_prepay(appid: str, out_trade_no: str, total_fen: int, openid: str, description: str) -> str:
    data = request("POST", "/v3/pay/transactions/jsapi", payload={
        "appid": appid, "mchid": MCHID, "description": description,
        "out_trade_no": out_trade_no,
        "notify_url": "https://shop.example.com/wechatpay/notify",   # https、不带参数
        "amount": {"total": total_fen, "currency": "CNY"},           # 分，int
        "payer": {"openid": openid},
    })
    return data["prepay_id"]
```

**示例响应**：`{"prepay_id": "wx201410272009395522657a690389285100"}`

## 4. Native 下单

**Endpoint**: `POST /v3/pay/transactions/native`
**用途**：拿到 `code_url`，转成二维码让用户用微信「扫一扫」付款。

**关键参数**：§2，**没有** `payer`。

```python
def native_prepay(appid: str, out_trade_no: str, total_fen: int, description: str) -> str:
    data = request("POST", "/v3/pay/transactions/native", payload={
        "appid": appid, "mchid": MCHID, "description": description, "out_trade_no": out_trade_no,
        "notify_url": "https://shop.example.com/wechatpay/notify",
        "amount": {"total": total_fen, "currency": "CNY"},
    })
    return data["code_url"]   # 例如 weixin://wxpay/bizpayurl/up?pr=NwY5Mz9&groupid=00
```

**注意事项**
- `code_url` 不是固定值，每次下单都不一样，直接按 URL 转成二维码就行，不要自己解析或拼接。有效期 2 小时。
- 文档原文：从相册识别、长按识别 Native 支付二维码都**不支持**（FAQ 4012791890），只能用「扫一扫」。
- Native 下单页的错误码表里有 `400 ORDER_CLOSED`（订单已关闭，需要重新下单）。
- 前端展示二维码后要**轮询自己后端的查单接口**，文档示例是每 2 秒一次、共 60 秒（4012075249）。

## 5. H5 下单

**Endpoint**: `POST /v3/pay/transactions/h5`
**用途**：用户在**手机浏览器**（不是微信内置浏览器）里付款。返回的 `h5_url` 会拉起微信客户端。

**和 §2 不同的地方**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `scene_info` | object | **是** | JSAPI 里是选填，这里必填 |
| `scene_info.payer_client_ip` | string(45) | 是 | **用户**的真实 IP，不是你服务器的 IP。获取方法见 4018677409 |
| `scene_info.h5_info.type` | string(32) | 是 | 场景类型：`Wap`、`iOS`、`Android` |
| `scene_info.h5_info.app_name` / `app_url` / `bundle_id` / `package_name` | string | 否 | 应用信息 |

```python
def h5_prepay(appid, out_trade_no, total_fen, description, user_ip) -> str:
    data = request("POST", "/v3/pay/transactions/h5", payload={
        "appid": appid, "mchid": MCHID, "description": description, "out_trade_no": out_trade_no,
        "notify_url": "https://shop.example.com/wechatpay/notify",
        "amount": {"total": total_fen, "currency": "CNY"},
        "scene_info": {"payer_client_ip": user_ip, "h5_info": {"type": "Wap"}},
    })
    return data["h5_url"]
```

**注意事项**
- `h5_url` 只有 **5 分钟**有效，**不能篡改、拆分或截断**。唯一允许的改动是在末尾拼上 `&redirect_url=<urlencode 后的地址>`，
  而且这个地址的域名必须是商户平台配置过的 H5 支付域名（4012791835）。
- 只有在配置过 H5 支付域名的网页里跳转 `h5_url` 才能拉起收银台。
- 用户从微信回到你的页面时，不代表已经付款成功。文档建议在回跳页放一个「确认支付情况 / 已完成支付」按钮，用户点击后去查单。
- H5 开发指引（4012791831）要求：下单接口要校验 `Origin` 和用户登录态，防止跨域盗用。

## 6. APP 下单

**Endpoint**: `POST /v3/pay/transactions/app`
**用途**：拿到 `prepay_id`，交给 APP 通过 OpenSDK 拉起支付。

**和 §2 不同的地方**：`appid` 必须是开放平台的**移动应用** appid；没有 `payer`。响应 `{"prepay_id": "…"}`，2 小时有效。

```python
def app_prepay(appid, out_trade_no, total_fen, description) -> str:
    return request("POST", "/v3/pay/transactions/app", payload={
        "appid": appid, "mchid": MCHID, "description": description, "out_trade_no": out_trade_no,
        "notify_url": "https://shop.example.com/wechatpay/notify",
        "amount": {"total": total_fen, "currency": "CNY"},
    })["prepay_id"]
```

## 7. 前端调起支付与调起签名

JSAPI、小程序、APP 三种调起都需要**后端**用商户 API 证书私钥再签一次名（和下单用的是同一份证书，4012365348）。
Native 和 H5 不需要调起签名。

### 7.1 调起签名串：4 行，每行以 `\n` 结尾

| 产品 | 第 1 行 | 第 2 行 | 第 3 行 | 第 4 行 |
|---|---|---|---|---|
| JSAPI | 公众号 appId | 时间戳（**秒**，字符串） | 随机串（≤32 位） | `prepay_id=wx2014…`（**带** `prepay_id=` 前缀） |
| 小程序 | 小程序 appId | 同上 | 同上 | `prepay_id=wx2014…`（带前缀） |
| APP | 移动应用 appId | 同上 | 同上 | `wx2014…`（**只放 prepay_id 本身，不带前缀**） |

算法：SHA256withRSA + base64，和请求签名一样（`rsa_sign`）。`signType` 字段**不参与签名**，但要传，值固定为 `RSA`。

```python
import secrets, time
from wechatpay_v3 import rsa_sign, MCHID

def jsapi_invoke_params(appid: str, prepay_id: str) -> dict:
    """JSAPI（WeixinJSBridge）和小程序（wx.requestPayment）共用。appid 必须和下单时传的一样。"""
    ts, nonce = str(int(time.time())), secrets.token_hex(16)
    package = f"prepay_id={prepay_id}"
    return {"appId": appid, "timeStamp": ts, "nonceStr": nonce, "package": package,
            "signType": "RSA", "paySign": rsa_sign(f"{appid}\n{ts}\n{nonce}\n{package}\n")}

def app_invoke_params(appid: str, prepay_id: str) -> dict:
    ts, nonce = str(int(time.time())), secrets.token_hex(16)
    return {"appId": appid, "partnerId": MCHID, "prepayId": prepay_id,
            "packageValue": "Sign=WXPay",          # 固定值；iOS 的字段名叫 package
            "nonceStr": nonce, "timeStamp": ts,
            "sign": rsa_sign(f"{appid}\n{ts}\n{nonce}\n{prepay_id}\n")}
```

### 7.2 各端怎么用

| 端 | 调用 | 参数 | 结果判断（**只能用来展示，不能作为支付成功的依据**） |
|---|---|---|---|
| JSAPI | `WeixinJSBridge.invoke('getBrandWCPayRequest', {appId, timeStamp, nonceStr, package, signType, paySign}, cb)` | 用 `jsapi_invoke_params` 的全部返回值 | `res.err_msg`：`get_brand_wcpay_request:ok` / `:cancel` / `:fail` |
| 小程序 | `wx.requestPayment({timeStamp, nonceStr, package, signType, paySign, success, fail})` | **不传 appId**（签名里仍然要用小程序 appId） | `requestPayment:ok` / `requestPayment:fail cancel` / `requestPayment:fail (detail)` |
| APP | `PayReq` + `api.sendReq(req)` | `app_invoke_params` 的返回值 | `onResp` 里的 `errCode`：`0` 成功 / `-1` 错误（签名错、AppID 没注册等）/ `-2` 取消 |
| H5 | `location.href = h5_url` | —— | 回到页面后查单 |
| Native | 展示二维码 | —— | 轮询查单 |

**文档反复强调**：前端回调（包括 `ok` / `errCode=0`）「并不保证它绝对可靠」。订单状态以**后端查单**和**支付成功回调**为准，见 `orders.md` 和 `notifications.md`。

**注意事项**
- 时间戳必须是**秒级**（10 位数字）。JS 里 `Date.now()` 是毫秒，要除以 1000 取整。
- 小程序的 `paySign` 必须用**实际调起支付的那个小程序的 appid** 来签，而且要和下单时传的 appid 一致，微信支付会校验两者是否一致（4012791898）。
- 交易类小程序要遵守《交易类小程序运营规范》并接入订单发货管理，否则可能被限制在正式环境调起支付（4012791898）。
- 常见前端报错（FAQ，文档原文）：JSAPI「当前页面的URL未注册」→ 没配 JSAPI 支付授权目录；「下单账号与支付账号不一致」→ 下单时的 openid 不是当前付款的用户；
  「调起支付报错：支付验证签名失败」→ prepay_id 格式不对（APP 不带前缀，JSAPI 和小程序带前缀），或者下单和调起用的不是同一份商户证书（4012365348）。
- ⚠ 文档示例瑕疵：JSAPI 调起签名页（4012365339）JS 示例里的 `paySign`，和 APP 调起签名页（4012365340）iOS 示例里的 `request.sign`，
  末尾都多了一个 `%`（shell 输出没有换行留下的痕迹）。我们用同页的测试私钥复算（2026-09-11，离线），正确值结尾是 `==`，不带 `%`。
  照抄示例里的值会导致签名错误。

## 8. 下单错误码

以下均为文档原文，未实测。HTTP 状态码以各 API 页为准。

| HTTP | code | 含义 | 处理 | 出现在 |
|---|---|---|---|---|
| 400 | `APPID_MCHID_NOT_MATCH` | appid 和 mchid 没有绑定 | 在商户平台绑定，或者换成已绑定的 appid | 全部 |
| 400 | `MCH_NOT_EXISTS` | 商户号不存在 | 核对 mchid | 全部 |
| 400 | `PARAM_ERROR` | 参数错误，`detail.field` 用 JSON Pointer 指出是哪个字段 | 按 `detail` 修 | 全部 |
| 400 | `INVALID_REQUEST` | 不符合 v3 规则，或者不符合业务规则 | 看 message | 全部 |
| 400 | `ORDER_CLOSED` | 订单已关闭 | 用新的 `out_trade_no` 重新下单 | Native |
| 401 | `SIGN_ERROR` | 签名错误 | 见 `auth-signing.md` §9 | 全部 |
| 403 | `NO_AUTH` | 这个产品的权限没开通 | 在商户平台 → 产品中心申请 | 全部 |
| 403 | `OUT_TRADE_NO_USED` | 商户订单号重复 | 同一个单号只能用相同的参数重试 | 全部 |
| 403 | `RULE_LIMIT` | 业务规则限制 | 看 message | H5 |
| 429 | `FREQUENCY_LIMITED` | 频率超限 | 降频 | 全部 |
| 500 | `SYSTEM_ERROR` | 系统错误 | **用相同参数**重试（同一个 out_trade_no） | 全部 |

## 9. 上线前要在商户平台 / 公众平台配好的东西

| 产品 | 必须配置 | 文档 |
|---|---|---|
| 全部 | appid 与 mchid 绑定；设置 APIv3 密钥（**没设置的话，微信支付不会发回调**，4012075420） | 4013287010、4012072195 |
| JSAPI | JSAPI 支付授权目录 | 4013287088 |
| H5 | H5 支付域名 | 4013287193 |
| 小程序 | 小程序已开通支付；交易类小程序接入发货管理 | 4012791898 |
| APP | 开放平台移动应用；iOS 配置 URL scheme / universal link | 4013070351 |

文档说明（4012073699）：APIv3 **没有沙箱环境**，也没有测试参数。FAQ 4016179629 说可以单独申请一个商户号专门给测试环境用。
回调也只能在生产环境用真实支付来测（FAQ 4012791869）。

## 10. 本文件 ⚠ 汇总

- §2 `time_expire` 的上限：Native 页写 7 天，其他页写 15 天。
- §2 订单号重复时的错误码：FAQ 写 `201`（v2 风格），API 页写 `403 OUT_TRADE_NO_USED`。
- §7 调起签名示例值末尾多了 `%`。
