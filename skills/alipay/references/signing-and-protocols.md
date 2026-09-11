# 接入方式与签名：旧版 gateway.do 网关 vs 新版 v3

> 内容整理自 opendocs.alipay.com（common/057k53、02mse7、02kf5p、02kf5q、055cla、0i2kxr、02kdnf、02kdne，
> open-v3/054oog、054q58、054d0z、065bsc），抓取于 2026-09-11。**未用真实凭证验证。**
> 标「无凭证探测（2026-09-11）」的是用伪造 `app_id=test` 打出来的真实返回；其余报错、行为均为「文档原文，未实测」。

## 目录

1. [先选协议：两套并存，不能混用](#1-先选协议两套并存不能混用)
2. [密钥 / 证书：先搞清手里是哪几件](#2-密钥--证书先搞清手里是哪几件)
3. [用官方 SDK（推荐）](#3-用官方-sdk推荐)
4. [旧版网关：自行实现签名](#4-旧版网关自行实现签名)
5. [旧版网关：同步响应验签](#5-旧版网关同步响应验签)
6. [新版 v3：自行实现签名](#6-新版-v3自行实现签名)
7. [新版 v3：响应验签](#7-新版-v3响应验签)
8. [证书模式额外要带的东西](#8-证书模式额外要带的东西)
9. [接口内容加密（AES）只做了解](#9-接口内容加密aes只做了解)
10. [签名排查速查](#10-签名排查速查)

---

## 1. 先选协议：两套并存，不能混用

| | 旧版网关（文档称 OpenAPI 网关，常称 v2） | 新版 v3（OAS 3.0 / RESTful） |
|---|---|---|
| 请求地址 | `POST https://openapi.alipay.com/gateway.do`，接口名放 `method` 参数 | `POST https://openapi.alipay.com/v3/alipay/trade/query` 这种「每个接口一个路径」 |
| 沙箱 | `https://openapi-sandbox.dl.alipaydev.com/gateway.do` | `https://openapi-sandbox.dl.alipaydev.com` + 同样路径 |
| 业务参数 | 整个 JSON 串塞进一个表单字段 `biz_content` | 直接是 JSON body |
| 鉴权 | `sign` 参数（对排序后的全部参数签名） | `Authorization` 请求头（对「认证串 + 方法 + 路径 + body」签名） |
| 时间戳 | `timestamp=yyyy-MM-dd HH:mm:ss` 字符串 | authString 里 `timestamp=<Unix 毫秒>` |
| 出错 | **HTTP 200**，看 `<接口名>_response.code` | **HTTP 4xx/5xx**，body `{code, message, links}` |
| 签名算法 | `sign_type=RSA2`（SHA256WithRSA）；历史应用还可用 `RSA`（SHA1） | 只支持 `ALIPAY-SHA256withRSA`（及 SM2），**不支持 RSA(SHA1)** |
| 官方 SDK | Java / PHP / .NET / **Python** / Node.js（通用版） | Java / .NET / PHP / Node.js，**没有 Python** |
| 页面跳转 / 唤端（电脑网站、手机网站、APP 支付） | `alipay.trade.page.pay` / `wap.pay` / `app.pay` | **openapi.yaml 里没有对应 v3 路径**；v3 SDK 仍用 `pageExecute` / `sdkExecute` 并「传入 api 的方法名（method）」 |

**怎么选：**

- 用 Python：旧版网关 + `alipay-sdk-python`（官方只有这一个 Python SDK）。要 v3 就得自己实现第 6、7 节的签名。
- 用 Java / PHP / .NET / Node.js 新项目：服务端接口（当面付、查询、退款、关闭）可以用 v3 SDK；电脑网站 / 手机网站 / APP 支付的下单依旧走 `pageExecute` / `sdkExecute`。
- 一个项目里两套可以共存（同一 APPID、同一套密钥），**但同一个请求不能混**：往 `/v3/...` 路径发 `biz_content`、或往 `gateway.do` 发 `Authorization` 头，都不会被识别。⚠ 文档未说明「同一 APPID 可同时调 v2 与 v3」的明确条款，只是 v3 签名页的「接口加签方式」与 v2 共用同一个配置页。

> v3 文档（open-v3/054kaq）原话：v3「简化加验签逻辑，对 HTTP 报文整体进行签名」，「对于不符合支付宝 API v3 协议规范的请求将会被拒绝」。

**无凭证探测（2026-09-11）**：同一个伪造 `app_id=test` 的查询请求，
旧版返回 `HTTP 200` + `{"alipay_trade_query_response":{"code":"40002","msg":"Invalid Arguments","sub_code":"isv.invalid-app-id",...}}`；
v3 返回 `HTTP 400` + `{"code":"invalid-app-id","links":[{"link":"...","desc":"解决方案"}],"message":"无效的AppID参数"}`。错误处理代码两套必须分开写，详见 [errors.md](errors.md)。

---

## 2. 密钥 / 证书：先搞清手里是哪几件

| 加签方式 | 需要的文件 | 适用场景（文档原文） |
|---|---|---|
| 密钥（公钥模式） | 应用私钥、应用公钥、**支付宝公钥** | 除资金支出类场景外都可用 |
| 证书（公钥证书模式） | 应用私钥、应用公钥证书、支付宝公钥证书、支付宝根证书 | 红包、转账到支付宝账户**必须**用证书；其它场景二选一 |

必须知道的规则（common/02kf5p、02kdne、02kdnf，文档原文，未实测）：

- **一个 APPID 只能配置一种加签方式**。用证书模式的应用，不能再拿「公钥」去验签，反之亦然。
- **验签用「支付宝公钥」，不是你上传的「应用公钥」。** 两者都叫「公钥」，最常见的配置错误就是拿应用公钥去验支付宝的签名。
- 平台**不保存应用私钥**，丢了只能重新生成、重新上传。
- 私钥格式：**Java 用 PKCS8，其它语言用 PKCS1**；要求一行字符串（Python SDK 示例写「开发者私钥去头去尾去回车，单行字符串」）。
- RSA2 必须 ≥ 2048 位。新建应用只支持 RSA2。
- 从「公钥」切到「公钥证书」后 7 天内可回退；7 天后旧的公钥模式请求会被网关拦截。换新应用公钥证书后，老证书也只保留 7 天。
- 支付宝公钥证书约 5 年有效，会被重新签发（密钥内容不变，SN 变），平台提前 30 天生成新证书并通知。
- 沙箱和生产的 APPID、私钥、支付宝公钥**全部独立**，混用会得到 `isv.invalid-signature`。

---

## 3. 用官方 SDK（推荐）

SDK 自动完成请求签名和**同步响应**验签；**异步通知的验签 SDK 不会自动做**，要手动调验签方法（见 [notify-and-verify.md](notify-and-verify.md)）。

### Python（旧版网关，`alipay-sdk-python`）

来源：common/02np8q（文档原文）。PyPI 包名 `alipay-sdk-python`，模块路径 `alipay.aop.api`，文档写「适用于 Python 2.7 及以上」。

```python
import os
from alipay.aop.api.AlipayClientConfig import AlipayClientConfig
from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient
from alipay.aop.api.domain.AlipayTradeQueryModel import AlipayTradeQueryModel
from alipay.aop.api.request.AlipayTradeQueryRequest import AlipayTradeQueryRequest
from alipay.aop.api.response.AlipayTradeQueryResponse import AlipayTradeQueryResponse

cfg = AlipayClientConfig()
# 生产：https://openapi.alipay.com/gateway.do
# 沙箱：https://openapi-sandbox.dl.alipaydev.com/gateway.do
cfg.server_url = os.environ.get("ALIPAY_GATEWAY", "https://openapi.alipay.com/gateway.do")
cfg.app_id = os.environ["ALIPAY_APP_ID"]
cfg.app_private_key = os.environ["ALIPAY_APP_PRIVATE_KEY"]      # 单行、无 BEGIN/END
cfg.alipay_public_key = os.environ["ALIPAY_PUBLIC_KEY"]         # 支付宝公钥，不是应用公钥
client = DefaultAlipayClient(cfg)

model = AlipayTradeQueryModel()
model.out_trade_no = "20150320010101001"
request = AlipayTradeQueryRequest(biz_model=model)
raw = client.execute(request)                  # 返回的是 xxx_response 里的 JSON 字符串
resp = AlipayTradeQueryResponse()
resp.parse_response_content(raw)
if resp.is_success():
    print(resp.trade_status)
else:
    print(resp.code, resp.msg, resp.sub_code, resp.sub_msg)
```

<!-- Gap: 官方 Python SDK 文档（common/02np8q）所有示例的 server_url 都是旧沙箱 https://openapi.alipaydev.com/gateway.do；无凭证探测（2026-09-11）该域名 TLS 证书已过期（curl: (60) certificate has expired） -->
**无凭证探测（2026-09-11）**：Python SDK 文档四个示例全部把 `server_url` 写成 `https://openapi.alipaydev.com/gateway.do`（旧沙箱）。
该域名 TLS 握手返回 `certificate has expired`，照抄就连不上。沙箱请用 `https://openapi-sandbox.dl.alipaydev.com/gateway.do`（探测可达）。

⚠ 文档未说明：Python SDK 的证书模式配置字段、异步通知验签函数名——Python 文档页只给了公钥模式和 4 个调用示例。

### Java（旧版网关，密钥模式）

来源：common/02kf5q（文档原文）。

```java
AlipayConfig alipayConfig = new AlipayConfig();
alipayConfig.setServerUrl("https://openapi.alipay.com/gateway.do");
alipayConfig.setAppId(APPID);
alipayConfig.setPrivateKey(PRIVATE_KEY);          // PKCS8
alipayConfig.setFormat("json");
alipayConfig.setCharset("UTF-8");
alipayConfig.setAlipayPublicKey(ALIPAY_PUBLIC_KEY);
alipayConfig.setSignType("RSA2");
AlipayClient alipayClient = new DefaultAlipayClient(alipayConfig);
```

证书模式（common/097jyh 示例）：改为 `setAppCertPath` / `setAlipayPublicCertPath` / `setRootCertPath`，并用 `alipayClient.certificateExecute(request)` 而不是 `execute`。

### v3 SDK

| 语言 | 包 | 最低版本 |
|---|---|---|
| Java | Maven `com.alipay.sdk:alipay-sdk-java-v3` | 3.0.0.ALL |
| .NET | NuGet `AlipaySDKNet.OpenAPI` | 3.0.0 |
| PHP | Composer `alipaysdk/openapi` | 3.0.0 |
| Node.js | npm `alipay-sdk` | 4.0.0 |

类名规则（open-v3/065bsc 原文）：接口 `alipay.trade.pay` → 请求类 `AlipayTradePayModel`、响应类 `AlipayTradePayResponseModel`、异常 `AlipayTradePayDefaultResponse`、资源类 `AlipayTradeApi`、方法 `pay`。
v3 SDK「目前仅支持 RSA2 算法」；异步通知验签「依然提供 AlipaySignature 工具类……使用方式与 v2 版本一样」。

⚠ 文档自相矛盾：065bsc 正文说「目前已支持 Java、PHP、C# 三种编程语言」，同页表格列了四种（多一个 Node.js）；同页 OpenAPI Generator 一节又说「目前支付宝提供了 Java 版本的 SDK」。

---

## 4. 旧版网关：自行实现签名

来源：common/057k53、0i2kxr（文档原文，未实测）。

**公共请求参数**（所有 `gateway.do` 接口一致）

| 参数 | 必填 | 说明 |
|---|---|---|
| `app_id` | 是 | 应用 ID |
| `method` | 是 | 接口名，如 `alipay.trade.pay` |
| `format` | 否 | 仅支持 `JSON` |
| `charset` | 是 | `utf-8` / `gbk`（`isv.invalid-charset` 说明只支持 GBK、UTF-8） |
| `sign_type` | 是 | `RSA2`（推荐）/ `RSA` |
| `sign` | 是 | 签名串 |
| `timestamp` | 是 | `yyyy-MM-dd HH:mm:ss`，如 `2014-07-24 03:07:50` |
| `version` | 是 | 固定 `1.0` |
| `notify_url` | 否 | 异步通知地址（支付类接口在这里传，不是在控制台配） |
| `return_url` | 否 | 仅页面跳转类接口（page.pay / wap.pay） |
| `app_auth_token` | 否 | 服务商代调用时的应用授权令牌 |
| `biz_content` | 是 | 除公共参数外的所有业务参数，JSON 字符串 |
| `app_cert_sn` / `alipay_root_cert_sn` | 证书模式必填 | 见第 8 节 |

**签名步骤**

1. 取全部参数（公共 + `biz_content`），**去掉 `sign`**、值为空（空白 / null）的参数、文件二进制。**`sign_type` 保留参与签名**（与异步通知验签相反，别搞混）。
2. 按参数名 ASCII 升序排序，拼成 `k1=v1&k2=v2`（此时**不做 URL 编码**）。
3. 用应用私钥做 SHA256WithRSA，结果 Base64 → `sign`。
4. 各参数值做 URL 编码后发送：**`biz_content` 放 body，其余（尤其 `charset`）放 URL query**，`Content-Type: application/x-www-form-urlencoded`。

⚠ 文档自相矛盾：057k53 要求 `application/x-www-form-urlencoded`，但各 API 页（如 open/02ekfp）的 cURL 示例用 `-F 'biz_content=...'`（即 multipart/form-data）。以 SDK 行为为准，自行实现建议按 057k53。

```python
import base64, json, os, urllib.parse
from datetime import datetime, timezone, timedelta
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

GATEWAY = os.environ.get("ALIPAY_GATEWAY", "https://openapi.alipay.com/gateway.do")
APP_ID = os.environ["ALIPAY_APP_ID"]
PRIV = serialization.load_pem_private_key(
    open(os.environ["ALIPAY_APP_PRIVATE_KEY_PEM"], "rb").read(), password=None)

def sign_v2(params: dict) -> str:
    items = sorted((k, v) for k, v in params.items()
                   if k != "sign" and v is not None and str(v).strip() != "")
    content = "&".join(f"{k}={v}" for k, v in items)
    sig = PRIV.sign(content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()

def call_v2(method: str, biz: dict, notify_url: str | None = None) -> dict:
    common = {
        "app_id": APP_ID, "method": method, "format": "JSON", "charset": "utf-8",
        "sign_type": "RSA2", "version": "1.0",
        "timestamp": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
    }
    if notify_url:
        common["notify_url"] = notify_url
    biz_content = json.dumps(biz, ensure_ascii=False, separators=(",", ":"))
    common["sign"] = sign_v2({**common, "biz_content": biz_content})
    r = requests.post(GATEWAY + "?" + urllib.parse.urlencode(common),
                      data={"biz_content": biz_content},
                      headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
    body = r.json()                                   # 出错也是 HTTP 200
    key = method.replace(".", "_") + "_response"      # alipay.trade.query -> alipay_trade_query_response
    return body[key]

# 用法：res = call_v2("alipay.trade.query", {"out_trade_no": "20150320010101001"})
#       if res["code"] != "10000": 处理 res["sub_code"]
```

**无凭证探测（2026-09-11）**：旧网关错误响应 `Content-Type` 是 `text/html;charset=utf-8`，但正文是 JSON——用 `requests` 的 `r.json()` 没问题，别按 Content-Type 分支判断。

**页面跳转类接口（page.pay / wap.pay）**：签名规则相同，但**不由服务端发请求**，而是把签好的参数交给浏览器：

- POST：公共参数进 form `action` 的 query，`biz_content` 作为隐藏表单项（0i2kxr 原文）。
- GET：公共参数和 `biz_content` 全部进 query，按 RFC3986 编码，得到一个可以 302 的 URL。

---

## 5. 旧版网关：同步响应验签

来源：common/02mse7（文档原文，未实测）。SDK 会自动做；自己实现时：

1. 响应形如 `{"alipay_trade_precreate_response":{...},"sign":"..."}`（证书模式还多一个同级 `alipay_cert_sn`）。
2. 待验签内容 = **`xxx_response` 的原始 JSON 子串**，包含首尾花括号和双引号。**不能 `json.loads` 后再 `json.dumps`**——字段顺序、空格、`\/` 转义都会变，验签必挂。
3. 用支付宝公钥做 SHA256WithRSA 验证 Base64 解码后的 `sign`。
4. 文档提示：若内容里有 `http://` 的正斜杠，验签失败时把 `/` 转义成 `\/` 再试一次。

```python
import re
def extract_signed_part(raw_text: str, method: str) -> str:
    key = method.replace(".", "_") + "_response"
    start = raw_text.index('"%s"' % key) + len(key) + 2
    start = raw_text.index("{", start)
    depth, i = 0, start
    while True:                                   # 按括号深度截取原始子串（忽略字符串内花括号的简化实现）
        if raw_text[i] == "{": depth += 1
        elif raw_text[i] == "}":
            depth -= 1
            if depth == 0: return raw_text[start:i + 1]
        i += 1
```

**无凭证探测（2026-09-11）**：错误响应（`isv.invalid-app-id`）里**没有 `sign` 字段**——验签代码遇到无 `sign` 的错误响应不要抛异常，先看 `code`。

---

## 6. 新版 v3：自行实现签名

来源：open-v3/054oog（基本原则）、054q58（签名规则）、官方 Postman 脚本 `alipay-sdk-java-all/v3/script/postman_script.js`（由 065bsc 链接）。文档原文，未实测。

**请求基本规范**

- 全部 HTTPS；`Content-Type: application/json`、`Accept: application/json`（加密请求、文件上传除外）；只支持 UTF-8。
- 可选请求头 `alipay-request-id`：请求唯一标识，`a-zA-Z0-9-_`，≤ 32 位。响应头 `alipay-trace-id` 是支付宝侧的请求标识，排查问题时提供给技术支持。
- 服务商代调用：请求头 `alipay-app-auth-token: <token>`，且该值也参与签名。
- 部分代理不支持 PUT/PATCH/DELETE 时，用 POST + `X-HTTP-Method-Override`。

**步骤 1：authString**（`key=value`，英文逗号分隔，顺序无关，空值省略）

| 字段 | 必填 | 说明 |
|---|---|---|
| `app_id` | 是 | 应用 ID |
| `app_cert_sn` | 证书模式必填 | 应用公钥证书 SN |
| `timestamp` | 是 | **Unix 毫秒**；超过 10 分钟将被拒绝 |
| `nonce` | 是 | 每次唯一的随机串，重复可能被拒 |
| `expired_seconds` | ⚠ | 表格未列，但文档所有示例与官方 Postman 脚本都带 `expired_seconds=120` |

⚠ 文档自相矛盾：参数表把 `appAuthToken` 列为 authString 字段，但同页「待签名内容」把 appAuthToken 作为**单独一行**追加，并要求与请求头 `alipay-app-auth-token` 一致；官方 Postman 脚本也是单独一行、不放进 authString。按 Postman 脚本实现更稳。

**步骤 2：待签名内容**（每行以 `\n` 结尾，**最后一行也有 `\n`**）

```
${authString}\n
${httpMethod}\n
${httpRequestUrl}\n        ← 路径 + query，不含域名，如 /v3/alipay/trade/query
${httpRequestBody}\n       ← GET / 无 body 时为空字符串，但这一行的 \n 仍要保留
${appAuthToken}\n          ← 仅代调用时才有这一行
```

文档示例（054q58）：

```
app_id=201406060016xxxx,timestamp=1655869956477,nonce=eb4ade8f-8cfa-4ebf-a048-7eb52684ab32,expired_seconds=120
POST
/v3/alipay/marketing/activity/ordervoucher/create?auth_token=123
{"activity_name": "单品特价满10减1活动","publish_start_time": "2022-02-01 00:00:01"}
```

**步骤 3–4：签名并放进请求头**

```
Authorization: ALIPAY-SHA256withRSA ${authString},sign=${signature}
alipay-root-cert-sn: ${alipayRootCertSn}          ← 仅证书模式
```

算法标识与 authString 之间是**空格**，authString 与 `sign=` 之间是**逗号**。
body 需要 AES 加密时，**先加密再签名**（签的是密文）。

```python
import base64, json, os, time, uuid
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

HOST = os.environ.get("ALIPAY_V3_HOST", "https://openapi.alipay.com")   # 沙箱 https://openapi-sandbox.dl.alipaydev.com
APP_ID = os.environ["ALIPAY_APP_ID"]
PRIV = serialization.load_pem_private_key(open(os.environ["ALIPAY_APP_PRIVATE_KEY_PEM"], "rb").read(), None)

def call_v3(method: str, path: str, body: dict | None = None, app_auth_token: str | None = None):
    body_str = json.dumps(body, ensure_ascii=False, separators=(",", ":")) if body is not None else ""
    auth = f"app_id={APP_ID},timestamp={int(time.time() * 1000)},nonce={uuid.uuid4()},expired_seconds=120"
    content = f"{auth}\n{method}\n{path}\n{body_str}\n"
    if app_auth_token:
        content += f"{app_auth_token}\n"
    sig = base64.b64encode(PRIV.sign(content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())).decode()
    headers = {
        "Authorization": f"ALIPAY-SHA256withRSA {auth},sign={sig}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "alipay-request-id": uuid.uuid4().hex,          # 32 位
    }
    if app_auth_token:
        headers["alipay-app-auth-token"] = app_auth_token
    # 注意：发出去的 body 必须和签名用的 body_str 字节级一致，所以用 data= 而不是 json=
    r = requests.request(method, HOST + path, data=body_str.encode("utf-8") if body_str else None, headers=headers)
    return r

# r = call_v3("POST", "/v3/alipay/trade/query", {"out_trade_no": "20150320010101001"})
# if r.status_code != 200: err = r.json()  -> {"code": "...", "message": "...", "links": [...]}
```

<!-- Gap: v3 签名规则页（open-v3/054q58）说「无签名 或 签名验证失败的请求将被拒绝，并返回 401 Unauthorized」；无凭证探测（2026-09-11）不带 Authorization 头请求 /v3/alipay/trade/query 返回 HTTP 400 {"code":"missing-timestamp","message":"缺少时间戳参数"} -->
**无凭证探测（2026-09-11）**：不带 `Authorization` 头 → **HTTP 400** `{"code":"missing-timestamp","message":"缺少时间戳参数"}`，不是文档说的 401。
带伪造签名 + 伪造 `app_id` → HTTP 400 `invalid-app-id`（app_id 校验先于验签，所以真正的 401 签名错误路径没能探测到）。
错误处理不要只认 401 为「签名问题」。

---

## 7. 新版 v3：响应验签

来源：open-v3/054d0z（截图确认）、官方 Postman 脚本。文档原文，未实测。

响应头：`alipay-signature`（签名）、`alipay-timestamp`、`alipay-nonce`、`alipay-sn`（证书模式，支付宝证书 SN，与本地不一致要更新支付宝公钥证书）。

待验签内容：

```
${alipay-timestamp}\n
${alipay-nonce}\n
${httpResponseBody}\n
```

用与请求相同的算法 + 支付宝公钥验证 Base64 解码后的 `alipay-signature`。

```python
from cryptography.hazmat.primitives.serialization import load_pem_public_key
ALIPAY_PUB = load_pem_public_key(open(os.environ["ALIPAY_PUBLIC_KEY_PEM"], "rb").read())

def verify_v3_response(r: requests.Response) -> bool:
    sig = r.headers.get("alipay-signature")
    if not sig:
        return False
    content = f"{r.headers['alipay-timestamp']}\n{r.headers['alipay-nonce']}\n{r.text}\n"
    try:
        ALIPAY_PUB.verify(base64.b64decode(sig), content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception:
        return False
```

**无凭证探测（2026-09-11）**：400 错误响应里**没有 `alipay-signature` 头**（只有 `alipay-trace-id`）。⚠ 文档未说明错误响应是否签名——验签逻辑应只对 2xx 强制。

---

## 8. 证书模式额外要带的东西

| | 旧版网关 | v3 |
|---|---|---|
| 请求 | 公共参数加 `app_cert_sn`、`alipay_root_cert_sn`（不带则「网关会拒绝请求」） | authString 加 `app_cert_sn`；请求头加 `alipay-root-cert-sn` |
| 响应 | 与 `xxx_response`、`sign` 同级多一个 `alipay_cert_sn` | 响应头 `alipay-sn` |
| SDK 方法（Java 旧版） | `certificateExecute(request)`；异步通知 `AlipaySignature.rsaCertCheckV1(params, alipayPublicCertPath, "UTF-8", "RSA2")` | SDK 内部处理 |

SN 计算（common/057k53、open-v3/054q58 原文）：解析 X.509 证书，`签发者名称 + 序列号` 拼接后取 MD5 十六进制（不足 32 位前补 0）。
**根证书**是证书链：对链上每一张签名算法 OID 以 `1.2.840.113549.1.1`（RSA）开头的证书分别算 SN，再用 `_` 连接。
Java SDK 参考实现：`AlipaySignature.getCertSN`、`AntCertificationUtil.getRootCertSN`。

相关错误（common/02kdnf，文档原文，未实测）：`isv.missing-app-cert-sn`、`isv.missing-alipay-root-cert-sn`、`isv.invalid-alipay-root-cert-sn`、`isv.app-cert-expired`、`isv.app-cert-not-exist`、`isv.alipay-cert-not-exist`。

---

## 9. 接口内容加密（AES）只做了解

来源：common/02mse3（文档原文，未实测）。AES 用于对 `biz_content`（v3 为 body）加密防泄露，**不替代 RSA 签名**；算法 AES/CBC/PKCS5Padding。
在控制台配置后即时生效、不可删除。当面付 / 网站 / APP 支付的常规收款**不需要**开启。
旧版需在请求中带 `encrypt_type=AES`（相关错误 `isv.missing-encrypt-type`、`isv.invalid-encrypt-type`）。v3：先加密 body 再签名。
⚠ 文档未说明收单类接口是否强制要求加密——本 skill 默认不加密。

---

## 10. 签名排查速查

来源：common/02kdnf（文档原文，未实测）。

| 现象 | 原因 |
|---|---|
| `40002 isv.invalid-signature 无效签名` | 公私钥不是一对；网关环境（沙箱/生产）与 app_id、私钥不匹配；中文未 urlencode；字符集不一致 |
| `40003 isv.missing-signature-config` | 开放平台上还没上传应用公钥 / 证书 |
| Java 抛 `RSA 私钥格式不正确，请检查是否正确配置了 PKCS8 格式的私钥` | Java 需要 PKCS8；其它语言 PKCS1 |
| `NoSuchAlgorithmException: MD5 KeyFactory not available` | `sign_type` 设错 |
| `Signature length not correct: got 256 but was expecting 128` | `sign_type=RSA2` 却用了 RSA(1024) 的支付宝公钥（反之 got 128 expecting 256） |
| `sign check fail: check Sign and Data Fail` | 同步响应验签失败：支付宝公钥、环境或字符集不对 |
| `AlipaySignature.rsaCheckV1()` 返回 false | 异步通知验签失败，排查同上；生活号通知要用 V2（保留 `sign_type`） |

排查工具：支付宝开放平台密钥工具提供「签名」「同步验签」「异步验签」功能，可把自己算的 `sign` 与工具结果对比（签名工具「目前仅支持新版 OpenAPI 网关接口」，common/02khjm）。
