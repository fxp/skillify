# APIv3 签名、验签、证书与敏感字段加密

> 来源：`pay.weixin.qq.com/doc/v3/merchant/` 下 4012365342（总述）、4012365334 / 4012365336 / 4012365337（Path / Body / Query 签名）、
> 4013053249 / 4013053420（验签）、4012551764（下载平台证书）、4013053257（敏感字段加密）、4024350132（证书密钥概览）、
> 4012154180（平台证书切换公钥）、4012365344–4012365348 / 4012072670（签名报错），抓取于 2026-09-11。
>
> **验证状态**：没有用真实凭证调用过。凡是没标「无凭证探测」的报错文本，都是文档原文，未实测。
> 签名算法用文档公开的**测试私钥**离线复算过（见 §8），离线复算不等于和线上接口实测一致。

## 目录
1. [开发前要拿到的 7 样东西](#1-开发前要拿到的-7-样东西)
2. [请求签名：Authorization 头](#2-请求签名authorization-头)
3. [Python 实现（requests + cryptography）](#3-python-实现requests--cryptography)
4. [curl + openssl 手工签名](#4-curl--openssl-手工签名)
5. [应答验签](#5-应答验签)
6. [微信支付公钥 vs 平台证书；下载平台证书](#6-微信支付公钥-vs-平台证书下载平台证书)
7. [敏感字段加密](#7-敏感字段加密)
8. [离线自检：用文档测试向量复算](#8-离线自检用文档测试向量复算)
9. [签名类报错对照](#9-签名类报错对照)
10. [本文件 ⚠ 汇总](#10-本文件--汇总)

---

## 1. 开发前要拿到的 7 样东西

| 材料 | 用在哪 | 从哪来（文档 4013070756 / 4024350132） | 本 skill 示例用的环境变量 |
|---|---|---|---|
| `mchid` 商户号 | Authorization 头、几乎所有请求体或 query | 商户平台 → 账户中心 → 商户信息 | `WECHATPAY_MCHID` |
| `appid` | 下单、调起支付签名；必须已和 mchid 绑定 | 公众平台（公众号 / 小程序）或开放平台（移动应用） | `WECHATPAY_APPID` |
| 商户 API 证书私钥 `apiclient_key.pem` | 请求签名、调起支付签名 | 商户平台 → API 安全 → 申请商户 API 证书；**只能下载一次**，丢了只能重新申请 | `WECHATPAY_PRIVATE_KEY_PATH` |
| 商户 API 证书序列号 | Authorization 里的 `serial_no` | 商户平台查看，或 `openssl x509 -in apiclient_cert.pem -noout -serial` | `WECHATPAY_MCH_SERIAL_NO` |
| 微信支付公钥 `pub_key.pem` + 公钥 ID（`PUB_KEY_ID_…`） | 验应答 / 回调签名、加密敏感字段 | 商户平台 → API 安全 → 微信支付公钥（**推荐**，不过期） | `WECHATPAY_PUBLIC_KEY_PATH` / `WECHATPAY_PUBLIC_KEY_ID` |
| 或：平台证书 `wechatpay_*.pem` + 证书序列号 | 同上（二选一；5 年有效，需要平滑更换） | `GET /v3/certificates` 或官方证书下载工具 | —— |
| APIv3 密钥（32 个字符） | 解密回调 `resource`、解密平台证书 | 商户平台 → API 安全 → 设置 APIv3 密钥；**设置后不可查看** | `WECHATPAY_APIV3_KEY` |

> 文档原文（4024350132）：V2 和 V3 是两套独立体系。V2 用「APIv2 密钥 + 商户 API 证书」，V3 用「APIv3 密钥 + 商户 API 证书 + 平台证书/微信支付公钥」。
> 接口 URL 带 `v3` 的是 V3 接口，其余都是 V2。**APIv2 密钥不能拿来解密 v3 回调**：拿 v2 的 key 解密会得到 Tag mismatch（4013053274）。

## 2. 请求签名：Authorization 头

**适用范围**：本 skill 里的所有 `https://api.mch.weixin.qq.com/v3/...` 请求，包括拿 `download_url` 下载账单。

### 2.1 签名串：5 行，每行都以 `\n` 结尾（最后一行也要）

```
HTTP请求方法\n
URL\n
请求时间戳\n
请求随机串\n
请求报文主体\n
```

| 行 | 规则（文档原文归纳） | 容易错在哪 |
|---|---|---|
| 方法 | 大写：`GET` / `POST` | 小写 `post` 会导致验签失败（4012365347） |
| URL | **去掉域名**，保留 path，有 query 就带上 `?` 和查询串 | 写成 `https://api.mch…/v3/…` 或多一个 `/`（`//v3/…`）都会错（4012365347） |
| 时间戳 | 秒级 Unix 时间 | 与服务器相差 >5 分钟 → 401（文档 4012072670；**无凭证探测 P7 证实**） |
| 随机串 | 任意随机字符串；文档示例 32 位十六进制 | 必须和 Authorization 里的 `nonce_str` 相同 |
| 报文主体 | 请求 body **原样**；GET、或没有 body 时是空串，这一行只剩一个 `\n` | 签名时的 body 必须和实际发出的字节完全一致：签的是单行 JSON，发的也得是单行 |

四类请求第 2 行具体写法：

| 请求带什么参数 | 第 2 行（URL）写什么 | 文档示例 |
|---|---|---|
| 只有 Body | path | `/v3/pay/transactions/jsapi` |
| Path 参数 | 把 `{…}` 换成实际值 | `/v3/refund/domestic/refunds/1217752501201407033233368018` |
| Query 参数 | path + `?` + 查询串，和实际请求的 URL **逐字符一致**（值要先 URL encode） | `/v3/marketing/partnerships?limit=5&offset=10&authorized_data=%7B…%7D&…` |
| 下载账单 | `download_url` 的 path + query | `/v3/billdownload/file?token=xxx` |

> 查单 `GET /v3/pay/transactions/out-trade-no/{out_trade_no}?mchid=…` 同时有 path 参数和 query：签名串里的 URL 要带上 `?mchid=…`。
> 这是最常见的「POST 能签对、GET 就 401」的原因。

### 2.2 Authorization 头

```
Authorization: WECHATPAY2-SHA256-RSA2048 mchid="1900007291",nonce_str="593BEC0C930BF1AFEB40B4A08C8FB242",signature="<base64>",timestamp="1554208460",serial_no="408B07E79B8269FEC3D5D3E6AB8ED163A6A380DB"
```

- 认证类型固定为 `WECHATPAY2-SHA256-RSA2048`，后面跟**一个空格**，然后是 5 个 `key="value"`，用英文逗号分隔，**不加空格、必须双引号**，顺序随意（4012365344）。
- `signature` = 用**商户 API 证书私钥**对签名串做 SHA256withRSA（PKCS#1 v1.5 填充），结果 base64，**不换行**。
- `serial_no` 是**商户 API 证书**的序列号。它和响应头里的 `Wechatpay-Serial`（微信支付公钥 ID / 平台证书序列号）不是一个东西。
- 其他平台常见的 `Bearer <token>` 在这里不可用。无凭证探测（2026-09-11）：`Authorization: Bearer fake-token` 返回
  `401 {"code":"SIGN_ERROR","message":"签名信息错误，验签失败"}`。

### 2.3 其他必须的请求头

| Header | 值 | 依据 |
|---|---|---|
| `Accept` | `application/json` | 文档原文（4012081709）。无凭证探测：`Accept: */*` 也能通过这项检查 |
| `Content-Type` | `application/json`（有 body 时） | 文档原文；图片上传接口除外 |
| `User-Agent` | 任意非空值，建议写「系统名/版本」 | 文档说「很可能会拒绝」没有 UA 的请求。**无凭证探测（2026-09-11）：在 `/v3/certificates`、`/v3/refund/*` 上去掉 UA 直接 `400 {"code":"INVALID_REQUEST","message":"Http头缺少Accept或User-Agent"}`**，而且这项检查在签名校验之前；交易类 `/v3/pay/transactions/*` 去掉 UA 仍返回 401 `SIGN_ERROR`（2026-09-11 复测），UA 检查不是每个接口都有，一律带上。 |
| `Wechatpay-Serial` | 微信支付公钥 ID（`PUB_KEY_ID_…`） | 用公钥模式时在请求里带上，微信支付才会用「微信支付公钥」对应的私钥签应答。切换期间不带这个头，应答就用平台证书签（4012154180）。**请求里有敏感字段加密时必须带**，值是加密用的公钥 ID 或平台证书序列号（4013053257） |
| `Accept-Language` | `en` / `zh-CN` / `zh-HK` / `zh-TW` | 可选，控制错误描述的语言，默认 zh-CN |

## 3. Python 实现（requests + cryptography）

官方服务端 SDK 只有 **Java（wechatpay-java）、PHP（wechatpay/wechatpay）、Go（wechatpay-go）** 三种（4012076498），**没有官方 Python SDK**。
下面这个最小客户端按文档算法写成，其他 reference 的 Python 示例都 `from wechatpay_v3 import ...` 它。
其中 `rsa_sign` 已经用文档测试私钥复算过 5 个签名示例里的 4 个（§8）。

```python
# wechatpay_v3.py —— 需要 Python 3.10+，pip install requests cryptography
import base64, binascii, json, os, secrets, time
from urllib.parse import urlencode, urlsplit

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

BASE_URL = "https://api.mch.weixin.qq.com"            # 备域名 https://api2.mch.weixin.qq.com
MCHID = os.environ["WECHATPAY_MCHID"]
MCH_SERIAL_NO = os.environ["WECHATPAY_MCH_SERIAL_NO"]  # 商户 API 证书序列号
with open(os.environ["WECHATPAY_PRIVATE_KEY_PATH"], "rb") as f:          # apiclient_key.pem（PKCS#8）
    MCH_PRIVATE_KEY = serialization.load_pem_private_key(f.read(), password=None)

WECHATPAY_PUBLIC_KEY_ID = os.environ["WECHATPAY_PUBLIC_KEY_ID"]           # PUB_KEY_ID_…
with open(os.environ["WECHATPAY_PUBLIC_KEY_PATH"], "rb") as f:
    # 验签公钥表：Wechatpay-Serial -> 公钥。平台证书模式就放「证书序列号 -> 证书公钥」，可以同时放多把
    VERIFY_KEYS = {WECHATPAY_PUBLIC_KEY_ID: serialization.load_pem_public_key(f.read())}

SESSION = requests.Session()


class WechatPayError(Exception):
    def __init__(self, status, code=None, message=None, detail=None, request_id=None):
        super().__init__(f"HTTP {status} {code}: {message}")
        self.status, self.code, self.message = status, code, message
        self.detail, self.request_id = detail, request_id


def rsa_sign(message: str) -> str:
    """SHA256withRSA(PKCS#1 v1.5) + base64。请求签名、调起支付签名都用它。"""
    sig = MCH_PRIVATE_KEY.sign(message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode("ascii")


def build_authorization(method: str, url_path_and_query: str, body: str) -> str:
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16).upper()
    message = f"{method}\n{url_path_and_query}\n{timestamp}\n{nonce}\n{body}\n"
    return ("WECHATPAY2-SHA256-RSA2048 "
            f'mchid="{MCHID}",nonce_str="{nonce}",signature="{rsa_sign(message)}",'
            f'timestamp="{timestamp}",serial_no="{MCH_SERIAL_NO}"')


def verify_wechatpay_signature(headers, body: bytes, max_skew: int = 300) -> None:
    """应答和回调都用这个函数验签。body 必须是收到的原始字节，不能 json.loads 之后再 dumps 回去。"""
    ts, nonce = headers.get("Wechatpay-Timestamp"), headers.get("Wechatpay-Nonce")
    signature, serial = headers.get("Wechatpay-Signature"), headers.get("Wechatpay-Serial")
    if not (ts and nonce and signature and serial):
        raise ValueError("missing Wechatpay-* signature headers")
    if abs(time.time() - int(ts)) > max_skew:                 # 文档建议最多允许 5 分钟偏差，防重放
        raise ValueError("Wechatpay-Timestamp skew > 5 min")
    key = VERIFY_KEYS.get(serial)
    if key is None:                                           # 平台证书模式：先刷新证书再重试
        raise ValueError(f"unknown Wechatpay-Serial {serial}")
    message = ts.encode() + b"\n" + nonce.encode() + b"\n" + body + b"\n"
    try:
        key.verify(base64.b64decode(signature), message, padding.PKCS1v15(), hashes.SHA256())
    except (InvalidSignature, binascii.Error, ValueError) as e:
        # 以 WECHATPAY/SIGNTEST/ 开头的签名是微信支付故意下发的探测流量，也必须在这里判为失败
        raise ValueError("WeChat Pay signature verification failed") from e


def request(method: str, path: str, query: dict | None = None, payload: dict | None = None):
    url = BASE_URL + path + ("?" + urlencode(query) if query else "")
    body = "" if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    headers = {"Accept": "application/json", "User-Agent": "my-shop-backend/1.0",
               "Wechatpay-Serial": WECHATPAY_PUBLIC_KEY_ID}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    # 先 prepare 再签名：用 requests 最终发出去的 URL 签名，避免它对 path 再编码一次导致签名串和实际 URL 不一致
    req = requests.Request(method, url, headers=headers,
                           data=body.encode("utf-8") if payload is not None else None).prepare()
    parts = urlsplit(req.url)
    req.headers["Authorization"] = build_authorization(
        method, parts.path + ("?" + parts.query if parts.query else ""), body)
    resp = SESSION.send(req, timeout=10)
    if resp.status_code >= 400:
        # 无凭证探测（2026-09-11）：4xx 应答不带 Wechatpay-* 签名头；404/405 的 body 是空的
        try:
            err = resp.json()
        except ValueError:
            err = {}
        raise WechatPayError(resp.status_code, err.get("code"), err.get("message"),
                             err.get("detail"), resp.headers.get("Request-ID"))
    verify_wechatpay_signature(resp.headers, resp.content)    # 2xx 必须验签，204 就用空 body 验
    return resp.json() if resp.content else None
```

为什么要先 `prepare()` 再签名：`out_trade_no` 允许包含 `|`，而 `requests` 准备请求时会把 path 里的 `|` 编码成 `%7C`。
本地用 `PreparedRequest` 验证过（2026-09-11，离线）：`…/out-trade-no/A|B*C_1-2` 会变成 `…/out-trade-no/A%7CB*C_1-2`。
所以如果拿原始字符串去签名，签名串里的 URL 就和实际发出去的 URL 不一致。

**不要**用 `requests.post(url, json=payload)`：`json=` 会按 requests 自己的方式再序列化一遍（默认分隔符是 `", "` / `": "`），
发出去的字节就和签名时 `json.dumps(..., separators=(",", ":"))` 得到的字符串不一样了。文档对应的要求是「你计算签名时 body 是怎么样的，
你发起请求时 body 就应该是怎么样的」（4012365336）。

## 4. curl + openssl 手工签名

用来排查问题。拿到的签名值应该能和你代码算出来的对上（时间戳和随机串取相同值时）。

```bash
# GET 带 query：第 5 行是空串，所以 printf 的格式串以 \n\n 结尾
URL_PATH="/v3/pay/transactions/out-trade-no/ORDER20260911001?mchid=${WECHATPAY_MCHID}"
TS=$(date +%s); NONCE=$(openssl rand -hex 16 | tr 'a-f' 'A-F')
SIG=$(printf 'GET\n%s\n%s\n%s\n\n' "$URL_PATH" "$TS" "$NONCE" \
      | openssl dgst -sha256 -sign "$WECHATPAY_PRIVATE_KEY_PATH" | openssl base64 -A)
curl -sS -D - "https://api.mch.weixin.qq.com${URL_PATH}" \
  -A 'my-shop-backend/1.0' -H 'Accept: application/json' \
  -H "Wechatpay-Serial: ${WECHATPAY_PUBLIC_KEY_ID}" \
  -H "Authorization: WECHATPAY2-SHA256-RSA2048 mchid=\"${WECHATPAY_MCHID}\",nonce_str=\"${NONCE}\",signature=\"${SIG}\",timestamp=\"${TS}\",serial_no=\"${WECHATPAY_MCH_SERIAL_NO}\""

# POST：body 先存成变量，签名和 -d 用同一个变量，确保字节一致
BODY='{"mchid":"'"${WECHATPAY_MCHID}"'"}'
SIG=$(printf 'POST\n%s\n%s\n%s\n%s\n' "/v3/pay/transactions/out-trade-no/ORDER20260911001/close" "$TS" "$NONCE" "$BODY" \
      | openssl dgst -sha256 -sign "$WECHATPAY_PRIVATE_KEY_PATH" | openssl base64 -A)
```

## 5. 应答验签

**什么时候验**：每个 2xx 应答都要验；回调通知也要验（见 `notifications.md`）。

**验签串：3 行**，每行以 `\n` 结尾（4013053249 / 4013053420）：

```
应答时间戳\n        ← Wechatpay-Timestamp
应答随机串\n        ← Wechatpay-Nonce
应答报文主体\n      ← 原始 body；204 没有 body 时这一行只剩一个 \n
```

然后用 `Wechatpay-Serial` 对应的公钥，对「验签串 + base64 解码后的 `Wechatpay-Signature`」做 SHA256withRSA 验证。

| 步骤 | 做法 | 来源 |
|---|---|---|
| 1. 选公钥 | `Wechatpay-Serial` 以 `PUB_KEY_ID_` 开头 → 微信支付公钥；否则是平台证书序列号 → 找对应证书。更稳妥的写法：维护一张「serial → 公钥」映射表，按原值查 | 4012791861、4012154180 |
| 2. 防重放 | `Wechatpay-Timestamp` 和本机时间相差 >5 分钟就拒绝；本机要做 NTP 时间同步 | 4013053420 |
| 3. 原始 body | 用原始报文验签，框架不能改动 body（先解析再序列化会改掉空格和字段顺序） | 4013053249 |
| 4. 验签失败 | 应答：丢弃，可以重试（微信支付不会对重试请求再发探测签名）；回调：回 4xx/5xx，等微信支付重发 | 4013053249 |
| 5. 签名探测 | 微信支付会在极少数应答或回调里故意给错误签名，签名值以 `WECHATPAY/SIGNTEST/` 开头。**不要特殊放行**，照常验签，验不过就按失败处理 | 4013053249 |
| 6. 文件下载 | 下载账单这类文件下载接口的应答**不带签名头**，跳过验签，改为比对 `hash_value` | 4013053249、4013071238 |
| 7. 代理剥头 | 部分代理 / CDN 会过滤 `Wechatpay-*` 扩展头，导致拿不到签名，需要调整代理配置 | 4013053283 |

<!-- Gap: 平台证书验签页（4013053420）写「所有应答，微信支付都会使用平台证书私钥签名（文件下载接口和首次下载平台证书除外）」；无凭证探测（2026-09-11）P1–P7、P10–P12 的 401/400 应答全部不带任何 Wechatpay-* 头 -->
**无凭证探测（2026-09-11）**：鉴权失败的 401、缺 UA 的 400 都**不带** `Wechatpay-Signature` / `Wechatpay-Serial` / `Wechatpay-Timestamp` / `Wechatpay-Nonce`。
所以验签代码要**先判断 HTTP 状态码**。如果对 4xx 也强制验签，会抛出「缺签名头」，把真正的错误码（`SIGN_ERROR` / `PARAM_ERROR`…）盖掉。
2xx 应答是否一定带签名头，没有凭证无法验证，按文档理解是会带的。

## 6. 微信支付公钥 vs 平台证书；下载平台证书

| | 微信支付公钥（推荐） | 平台证书 |
|---|---|---|
| 有效期 | 不过期 | 5 年，到期前必须换，系统要支持新旧证书平滑更换 |
| 获取 | 商户平台 → API 安全 → 微信支付公钥，下载 `pub_key.pem`，页面上能看到公钥 ID | `GET /v3/certificates`（响应里的证书是用 APIv3 密钥加密的），或官方证书下载工具 |
| `Wechatpay-Serial` 的样子 | `PUB_KEY_ID_` + 数字串 | 40 位十六进制证书序列号 |
| 数量 | 每个商户号 1 个 | 通常 1 个，换证书期间新旧 2 个 |
| 请求头 | 请求里带 `Wechatpay-Serial: <公钥ID>`，应答才会用公钥签名 | 不需要 |

- 同一个商户号只选一种用（4024350132）。从平台证书切换到公钥时有灰度期（4012154180）：
  回调按 0.1% → 1% → 5% → 10% → 20% → 50% → 100% 的比例，用 7 天逐步切到公钥签名，**灰度期间回调两种签名都会收到**，验签代码要同时支持两种。
  应答用哪种签名，取决于你的请求有没有带 `Wechatpay-Serial: PUB_KEY_ID_…`。
- 文档 FAQ（4013038816）：申请了公钥之后默认**不会**开启切换，要到商户平台点「开启公钥切换」，应答才会改用公钥签名。
- PHP SDK 页（4012076511）提到：用证书下载工具时如果返回 `{"code": "RESOURCE_NOT_EXISTS","message": "无可用的平台证书，请在商户平台-API安全申请使用微信支付公钥。"}`，
  说明这个商户号**只能用微信支付公钥**（文档原文，未实测）。

### 下载平台证书

**Endpoint**: `GET /v3/certificates`
**用途**：拿到当前可用的平台证书列表（加密的 PEM）。只有平台证书模式才需要。
频率限制：单个商户号 1000 次/秒（文档原文）。文档要求**定期调用，间隔小于 12 小时**，不要把平台证书硬编码在代码里。

**关键参数**：没有 query 和 path 参数，只需要 Authorization 和 `Accept`。

**示例请求**

```bash
curl -X GET https://api.mch.weixin.qq.com/v3/certificates \
  -H 'Authorization: WECHATPAY2-SHA256-RSA2048 mchid="1900000001",...' -H 'Accept: application/json' -A 'my-shop-backend/1.0'
```

```python
import os
from wechatpay_v3 import request
from notifications_helpers import decrypt_resource   # 实现见 notifications.md §4，算法和解密回调完全相同
certs = request("GET", "/v3/certificates")["data"]
for c in certs:
    pem = decrypt_resource(c["encrypt_certificate"], os.environ["WECHATPAY_APIV3_KEY"], parse_json=False)
    # 用证书里的公钥验签；以 serial_no 为键放进 VERIFY_KEYS
```

**示例响应（文档原文，节选）**

```json
{"data": [{"serial_no": "5157F09EFDC096DE15EBE81A47057A7232F1B8E1",
           "effective_time ": "2018-06-08T10:34:56+08:00", "expire_time ": "2018-12-08T10:34:56+08:00",
           "encrypt_certificate": {"algorithm": "AEAD_AES_256_GCM", "nonce": "61f9c719728a",
                                   "associated_data": "certificate", "ciphertext": "sRvt… "}}]}
```

**注意事项**
- `encrypt_certificate.associated_data` 固定是 `"certificate"`，解密时要作为 AAD 传进去。
- 加密敏感字段时用**启用时间最晚**的那张证书（文档原文）。
- ⚠ 文档自相矛盾：参数表把 `effective_time` / `expire_time` 标成 `integer`，说明里却写「时间格式为 RFC3339」，示例又是字符串，
  而且示例的键名带了尾随空格（`"effective_time "`）。解析时字段类型要宽松处理，键名以实际返回为准。
- 首次获取平台证书是先有鸡还是先有蛋的问题：第一次下载时手里还没有证书，没法验这次应答的签名。文档的做法是先用官方工具下载，
  再「通过证书信任链验证平台证书」（4012069411）。

## 7. 敏感字段加密

**什么时候用**：请求参数里有姓名、银行卡号这类敏感信息时。本 skill 范围内只有「发起异常退款」的 `bank_account` / `real_name` 需要（见 `refunds.md`）。

- 算法：RSA 公钥加密，填充方案 **RSAES-OAEP**，结果 base64（4013053257）。
- 公钥：微信支付公钥（推荐），或平台证书公钥。
- 请求**必须带** `Wechatpay-Serial` 头，值是加密所用的公钥 ID 或平台证书序列号。
  漏带时的报错（文档原文，未实测）：「HTTP header缺少微信支付平台证书序列号(Wechatpay-Serial)」；
  带错时的报错：`{"code":"PARAM_ERROR","message":"平台证书序列号Wechatpay-Serial错误"}`（4013053279）。
- 文档 Java 示例的报错提示写着「加密原串的长度不能超过214字节」。

```python
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
import base64

def encrypt_sensitive(plaintext: str, wechatpay_public_key) -> str:
    # 与文档 Java 示例一致：RSA/ECB/OAEPWithSHA-1AndMGF1Padding
    ct = wechatpay_public_key.encrypt(
        plaintext.encode("utf-8"),
        padding.OAEP(mgf=padding.MGF1(hashes.SHA1()), algorithm=hashes.SHA1(), label=None))
    return base64.b64encode(ct).decode("ascii")
```

- ⚠ 文档自相矛盾：加密指引（4013053257）和官方 Go 工具库（4015119334 的 `EncryptOAEPWithPublicKey` 用 `sha1.New()`）都用 **OAEP + SHA-1**；
  而 FAQ「平台私钥解密失败」（4016913151）写「推荐使用SHA-256作为哈希算法」。上面的代码按指引和官方工具库写（SHA-1）。
  如果真的报「平台私钥解密失败」，这里是要优先实测的地方。
- 反方向：微信支付下行的敏感字段，用**商户 API 证书公钥**加密，商户用 `apiclient_key.pem` 解密（4012153196 流程图）。

## 8. 离线自检：用文档测试向量复算

文档公开了一对**测试用**商户 API 私钥（商户号 1900007291，序列号 `408B07E79B8269FEC3D5D3E6AB8ED163A6A380DB`），
以及几个算好的签名值。我们在 2026-09-11 用 §3 的 `rsa_sign`（Python `cryptography`）离线复算，结果如下：

| 文档示例 | 结果 |
|---|---|
| Body 签名（4012365336，JSAPI 下单，签名值以 `jnks4dlr…` 开头） | ✅ 一致 |
| Path 签名（4012365334，查询单笔退款） | ✅ 一致 |
| JSAPI 调起支付 `paySign`（4012365339） | ✅ 与「得出的签名值」代码块一致 |
| APP 调起支付 `sign`（4012365340） | ✅ 一致 |
| Query 签名（4012365337，委托营销查询合作伙伴） | ❌ 不一致。按原样、先解码 query、去掉 query 三种写法都复算不出 |
| 应答验签（签名值以 `mfI1CP…` 开头） | 平台证书页（4013053420）给的公钥 ✅；**微信支付公钥页（4013053249）给的公钥 ❌** |

- ⚠ 文档自相矛盾：Query 签名示例（4012365337）给出的签名值，用同页的测试私钥和同页的签名串复算不出来。
  这个示例不能拿来当自测基准。Path / Body 示例可以当基准（它们已经复算通过）。
- ⚠ 文档自相矛盾：微信支付公钥验签示例（4013053249）沿用了平台证书页的签名值，但换了一把公钥，照着做只会得到 `Verification Failure`。
  用这两页做自测时，以平台证书页的数据为准。
- 同一套调起支付示例里，JS 示例的 `paySign` 和 iOS 示例的 `sign` 末尾都多了一个 `%`（shell 打印时没有换行留下的痕迹），见 `payments.md`。

## 9. 签名类报错对照

HTTP 状态码全部是 401，`code` 全部是 `SIGN_ERROR`，**只能靠 message 区分原因**（4012072670，文档原文，未实测；标注「探测」的行除外）：

| message（节选） | 原因 | 处理 |
|---|---|---|
| `Http头Authorization值格式错误，请参考《微信支付商户REST API签名规则》` | 缺 Authorization，或者格式不对（换行、单引号、中文符号、多了空格） | 核对 §2.2。**无凭证探测（2026-09-11）：不带 Authorization 调 `/v3/certificates`、`/v3/refund/domestic/refunds`、`/v3/bill/tradebill` 都返回这一句** |
| `签名信息错误，验签失败` | —— | **无凭证探测（2026-09-11）**：不带 Authorization 或者用 `Bearer` 调 `/v3/pay/transactions/*`，返回的是这一句，不是上面那句 |
| `签名错误` | 格式对但签名值不对 | **无凭证探测（2026-09-11）**：Authorization 格式正确、签名是伪造的，返回这一句。排查：私钥用错（拿了 `apiclient_cert.pem` 或平台证书）、签名串 5 行不对、body 被重新序列化、query 没进签名串 |
| `Http头Authorization中的timestamp与发起请求的时间不得超过5分钟` | 本机时钟不准，或者照抄了示例里的时间戳 | NTP 同步。**无凭证探测（2026-09-11）：用文档示例的时间戳 `1554208460` 请求，返回的正是这一句，而且它比签名校验先执行** |
| `HTTP头Authorization认证类型不正确` | 认证类型不是 `WECHATPAY2-SHA256-RSA2048` | —— |
| `商户证书序列号有误。请使用签名私钥匹配的证书序列号` | `serial_no` 和私钥不匹配 | `openssl x509 -in apiclient_cert.pem -noout -serial` 核对；证书的 CN 就是商户号 |
| `商户证书已过期` / `商户证书已作废` / `已更换证书，请使用新证书` | 证书状态不对 | 重新申请或换成新证书 |
| `商户未设置APIv3密钥。` / `商户未申请过证书。` | 商户平台没配置好 | 由超级管理员去商户平台配置 |
| `http header中的mchid与post payload中的mchid不匹配`（400 `PARAM_ERROR`，4012791869 FAQ） | Authorization 里的 mchid 和 body 里的 mchid 不一样 | 两处用同一个值 |

## 10. 本文件 ⚠ 汇总

- §6 下载平台证书：`effective_time` / `expire_time` 的类型和示例互相矛盾，示例键名带尾随空格。
- §7 敏感字段加密：OAEP 的哈希算法，指引和工具库用 SHA-1，FAQ 推荐 SHA-256。
- §8 Query 签名示例复算不出；微信支付公钥验签示例的公钥和签名对不上。
- §5 `<!-- Gap -->`：文档说「所有应答都会签名」，实际探测到 4xx 应答没有签名头。
