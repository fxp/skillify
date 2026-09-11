# 鉴权与请求签名

> 来源：open.qiyuesuo.com「API协议」「接口列表」「新手指南 / 接入流程」「常见问题」各页（抓取于 2026-09-11），
> 下载中心 SDK 版本表（`/api/sdklist`），GitHub `qiyuesuo/jssdk-server`、`qiyuesuo/sdk-python-sample` 源码。
> **未用真实凭证验证。** 凡是"会返回 / 会报错"的描述，除标注「无凭证探测（2026-09-11）」的以外，均为文档原文，未实测。

## 目录

1. [环境与域名](#1-环境与域名)
2. [开通与凭证](#2-开通与凭证)
3. [四个鉴权请求头与签名](#3-四个鉴权请求头与签名)
4. [Python 请求封装（其余 reference 都复用它）](#4-python-请求封装其余-reference-都复用它)
5. [curl 版](#5-curl-版)
6. [官方 SDK](#6-官方-sdk)
7. [HmacSha256 鉴权（SDK 已支持，文档站未说明）](#7-hmacsha256-鉴权sdk-已支持文档站未说明)
8. [公共响应结构与成功判定](#8-公共响应结构与成功判定)
9. [查询当前应用信息](#9-查询当前应用信息)
10. [子公司与 tenantName](#10-子公司与-tenantname)
11. [注意事项与 ⚠](#11-注意事项与-)

---

## 1. 环境与域名

| 用途 | 测试（沙箱） | 正式 |
| --- | --- | --- |
| **OpenAPI Base URL**（代码里用这个） | `https://openapi.qiyuesuo.cn` | `https://openapi.qiyuesuo.com` |
| 契约锁云平台（配置业务分类、文件模板、印章、回调） | `https://cloud.qiyuesuo.cn` | `https://cloud.qiyuesuo.com` |
| 开放平台控制台（申请接入、查看 AppToken / AppSecret） | `https://open.qiyuesuo.cn` | `https://open.qiyuesuo.com` |

- 完整 URL = Base URL + 接口路径，例如 `https://openapi.qiyuesuo.cn/v2/contract/draft`。路径有 `/v2/...`、`/v3/...`，也有不带版本的（`/company/platforminfo`、`/companyauth/pcpage`、`/chain/evidence/...`），**照接口列表逐个写，不要统一加前缀**。
- 两套环境**数据隔离**；沙箱里签的合同不具备法律效力；不要在沙箱做压力测试（文档原文）。
- 部分 PHP / 小程序示例写的是 `https://openapi.qiyuesuo.me`，文档没解释这个域名。
  无凭证探测（2026-09-11）：它在线，返回与另外两个环境同格式的网关错误（见 `qiyuesuo-workspace/probe-log.md` P8）。代码里不要用它。
- ⚠ 文档未说明：**私有化（私有云）部署**的 Base URL 与差异。文档站只在证书 FAQ 和 APP SDK 页提到"私有云"，错误码汇总也写明是"公有云开放平台"。私有化项目的地址、接口版本以部署方提供的为准，不要套用上表。
- 无凭证探测（2026-09-11）：测试、正式两个 Base URL 都在线，鉴权失败返回 JSON（§8）。

## 2. 开通与凭证

流程（文档原文）：开放平台注册账号 → 填写接入申请 → 开启沙箱（系统自动在测试环境创建企业、生成接入令牌和印章）→ 正式上线前完成**企业认证** → 在云平台「集成管理」申请业务系统，客服审核通过后查看**接入令牌（AppToken）与密钥（AppSecret）**（查看时需手机号校验）。

- 业务系统详情里可以**开启 / 关闭 IP 校验、配置 IP 白名单**（文档原文；开启后非白名单来源会被拒，具体报错文档未说明 ⚠）。
- 测试环境企业认证也要做，"至少保证企业名称要真实"（FAQ 原文）。
- 测试环境账户余额为 0 时无法发起合同，要联系客服充值（FAQ 原文）。
- **没有换 token 接口**：AppToken 是静态值，直接放进请求头，不存在"先调接口拿 access_token、过期再刷新"这一步。
- 开放平台**控制台**里维护的旧版文件模板 / 印章与**云平台**维护的是两套隔离的数据，新版接口只认云平台的（FAQ 原文）。

## 3. 四个鉴权请求头与签名

所有接口的请求头必须带（API协议页原文）：

| 请求头 | 值 |
| --- | --- |
| `x-qys-open-accesstoken` | AppToken |
| `x-qys-open-timestamp` | Unix 时间戳，**毫秒** |
| `x-qys-open-nonce` | 请求唯一标识，一般用 UUID；**10 分钟内只能用一次**（防重放） |
| `x-qys-open-signature` | `MD5(AppToken + AppSecret + timestamp + nonce)` 的 32 位 hex |

签名算法逐步：

1. 每个请求现取毫秒时间戳 `ts`（字符串）和新的 `nonce`。
2. 按 **AppToken、AppSecret、ts、nonce** 的顺序**直接拼接**，中间没有分隔符。
3. 对拼接串做 MD5，输出 hex。文档示例 `4e77af6b465c4080e25ecd012eaf2916` 与官方 jssdk-python-server（`hashlib.md5(s.encode('utf-8')).hexdigest()`）都是**小写**。

和别家习惯不同的地方：

- **签名不覆盖 URL、query、body**。不要照 HMAC 类平台的习惯去拼"方法 + 路径 + 排序参数 + body 摘要"。
- 没有 `Authorization` 头、没有 `Bearer` 前缀，header 名是全小写的 `x-qys-open-*`。
- AppSecret 只参与签名，不出现在任何请求头里。
- 文档示例（API协议页）：

```
GET /v2/seal/list?selectOffset=0&selectLimit=2 HTTP/1.1
Host: openapi.qiyuesuo.cn
x-qys-open-timestamp: 1565753984643
x-qys-open-signature: 4e77af6b465c4080e25ecd012eaf2916
x-qys-open-accesstoken: DWjfxmA12a
x-qys-open-nonce: 254775d7-3c7c-4e9d-9880-1d4c5fb3dbd0
```

- ⚠ 文档自相矛盾：API协议页说四个头"必须"，但几乎所有接口页的 Http 示例只写了 `timestamp`、`signature`、`accesstoken` 三个，没有 `nonce`。**按四个头发**；缺 nonce 会不会被拒，无凭证探测测不出来（P6：伪造 token 时先报 INVALID TOKEN）。
- ⚠ 文档未说明：时间戳允许的偏差窗口。服务器要做 NTP 校时。
- GitHub `qiyuesuo/jssdk-server` 的 C# 版 `CryptUtils.Md5` 用 GBK 编码、`ToString("X")` 拼 hex（单字节不补零）。自己实现时用标准 32 位小写 hex，不要照抄那一行。

## 4. Python 请求封装（其余 reference 都复用它）

凭证只从环境变量读。`QYS_BASE_URL` 默认指向测试环境。

```python
# qys_client.py —— 契约锁 OpenAPI 最小封装（requests）
import hashlib
import os
import time
import uuid

import requests

QYS_BASE_URL = os.environ.get("QYS_BASE_URL", "https://openapi.qiyuesuo.cn")  # 正式：https://openapi.qiyuesuo.com
QYS_APP_TOKEN = os.environ["QYS_APP_TOKEN"]
QYS_APP_SECRET = os.environ["QYS_APP_SECRET"]


class QysError(Exception):
    def __init__(self, http_status, code, response_code, message, body):
        super().__init__(f"HTTP {http_status} code={code} responseCode={response_code} {message}")
        self.http_status, self.code, self.response_code, self.message, self.body = (
            http_status, code, response_code, message, body)


def qys_headers() -> dict:
    ts = str(int(time.time() * 1000))
    nonce = str(uuid.uuid4())
    sign = hashlib.md5((QYS_APP_TOKEN + QYS_APP_SECRET + ts + nonce).encode("utf-8")).hexdigest()
    return {
        "x-qys-open-accesstoken": QYS_APP_TOKEN,
        "x-qys-open-timestamp": ts,
        "x-qys-open-nonce": nonce,
        "x-qys-open-signature": sign,
    }


def qys_call(method: str, path: str, *, params=None, json_body=None, data=None, files=None,
             raw: bool = False, timeout: int = 60):
    """JSON 接口返回 result；raw=True 时对文件流接口（下载 PDF / ZIP / 印章图片）返回 bytes。"""
    resp = requests.request(method, QYS_BASE_URL.rstrip("/") + path, headers=qys_headers(),
                            params=params, json=json_body, data=data, files=files, timeout=timeout)
    ctype = resp.headers.get("Content-Type", "")
    if raw and "application/json" not in ctype:
        resp.raise_for_status()
        return resp.content
    try:
        body = resp.json()
    except ValueError:
        resp.raise_for_status()
        raise
    code, rc = body.get("code"), body.get("responseCode")
    # 文档里成功判定两种写法都有：code == 0 / responseCode == "00000000"（见 §8）
    if code == 0 or rc == "00000000":
        return body.get("result")
    raise QysError(resp.status_code, code, rc, body.get("message"), body)
```

用法：

```python
from qys_client import qys_call

seals = qys_call("GET", "/v2/seal/list", params={"selectOffset": 0, "selectLimit": 20})
detail = qys_call("GET", "/v2/contract/detail", params={"contractId": "2591540368898105360"})
draft = qys_call("POST", "/v2/contract/draft", json_body={...})           # JSON 接口
doc = qys_call("POST", "/v2/document/addbyfile",                          # multipart 接口
               data={"contractId": draft["id"], "title": "劳动合同", "fileSuffix": "pdf"},
               files={"file": ("劳动合同.pdf", open("劳动合同.pdf", "rb"), "application/pdf")})
pdf_bytes = qys_call("GET", "/v2/document/download", params={"documentId": doc["documentId"]}, raw=True)
```

- 每次调用都重新生成 timestamp + nonce + signature；**不要缓存签名头复用**（nonce 10 分钟内只能用一次）。
- `requests` 的 `params=` 会自动 URL 编码 query（文档要求"请求的URL需要URL编码"，中文公司名、分类名尤其要编码）。
- 发 JSON 用 `json=`（会带 `Content-Type: application/json`）；multipart 接口用 `data=` + `files=`，不要手动写 `Content-Type`。

## 5. curl 版

```bash
export QYS_BASE_URL=https://openapi.qiyuesuo.cn     # 正式环境换成 https://openapi.qiyuesuo.com
# QYS_APP_TOKEN / QYS_APP_SECRET 从环境变量读
TS=$(python3 -c 'import time;print(int(time.time()*1000))')
NONCE=$(python3 -c 'import uuid;print(uuid.uuid4())')
SIG=$(python3 -c "import hashlib,sys;print(hashlib.md5(sys.argv[1].encode()).hexdigest())" \
      "${QYS_APP_TOKEN}${QYS_APP_SECRET}${TS}${NONCE}")

curl -sS "$QYS_BASE_URL/v2/seal/list?selectOffset=0&selectLimit=10" \
  -H "x-qys-open-accesstoken: $QYS_APP_TOKEN" \
  -H "x-qys-open-timestamp: $TS" \
  -H "x-qys-open-nonce: $NONCE" \
  -H "x-qys-open-signature: $SIG"
```

每条 curl 前都要重新生成 `TS / NONCE / SIG`。

## 6. 官方 SDK

- 提供 Java、.NET（C#）、Python、PHP、Go 五种 SDK，从下载中心 `https://open.qiyuesuo.com/download` 获取，**不是 pip / npm / Maven Central 上的公开包**（GitHub sample README 原文："前往契约锁开放平台下载 Python SDK 及依赖包，并添加到项目中"）。
- 下载中心 SDK 版本表（`GET https://open.qiyuesuo.com/api/sdklist?type=JAVA|Python|PHP|csharp|GO`，2026-09-11 读取）最新版：Java 4.0.2、Python 3.4.0、PHP 3.6.8、C# 3.4.0、Go 3.1.5。
- Python SDK 用法（GitHub `qiyuesuo/sdk-python-sample` 与文档示例）：

```python
from httpClient.SdkClient import *
from request.ContractDraftRequest import *
from bean.Contract import *
import json

sdkClient = SdkClient("https://openapi.qiyuesuo.cn", app_token, app_secret)
resp = sdkClient.request(ContractDraftRequest(contract))   # 返回 JSON 字符串
mapper = json.loads(resp)
```

- SDK 的 `Request` 类名与接口一一对应（`ContractDraftRequest`、`DocumentAddByFileRequest`、`ContractSendRequest`、`ContractSignCompanyRequest`、`ContractPageRequest`…），各 reference 的示例都给出底层 endpoint，用 SDK 时照名字找对应类。
- SDK 示例里判断成功有的写 `mapper['code'] != 0`，有的写 `mapper['responseCode'] != '00000000'`（见 §8）。
- 本 skill 的示例用 §4 的 `requests` 封装，不依赖 SDK 包。

## 7. HmacSha256 鉴权（SDK 已支持，文档站未说明）

- 下载中心 changelog：Java 4.0.0、Python 3.3.9、PHP 3.6.7、Go 3.1.4（均 2026-01-23）、C# 3.3.9（2026-03-05）写着"支持HmacSha256鉴权"。
- ⚠ 文档未说明：文档站「API协议」页只描述了 MD5 签名，没有任何页面给出 HmacSha256 的请求头名、待签名串、密钥或如何切换。
- 结论：**自己手写请求时用 §3 的 MD5 规则**；需要 HmacSha256 时只能用新版 SDK 或向契约锁确认，不要自行猜测 header 名和拼接方式。

## 8. 公共响应结构与成功判定

文档说法（⚠ 文档自相矛盾）：

| 页面写法 | 成功值 | 出现在 |
| --- | --- | --- |
| `responseCode`（String）+ `message` + `result` | `"00000000"` | 创建合同草稿、发起合同、签署公章、签署页面、合同详情等新版页面 |
| `code`（Integer）+ `message` + `result` | `0` | 签署合同汇总页、认证、模板列表、多文件添加等页面；「接口响应码说明」全局码 `0 [SUCCESS]` |

无凭证探测（2026-09-11，两次一致）：错误响应**同时**带两个字段，且 HTTP 状态码等于 `code`：

```
HTTP/2 442
content-type: application/json;charset=UTF-8

{"message":"INVALID TOKEN","code":442,"responseCode":"11990442"}
```

<!-- Gap: 文档各接口页的"返回参数"只列 responseCode(String) 或只列 code(Integer) 之一，也没提 HTTP 状态码；无凭证探测（2026-09-11，复跑一致）显示错误响应同时带 code 与 responseCode，且 HTTP 状态码 = code（441/442）。 -->

写代码时：

- **先解析 JSON，再看 HTTP 状态**。鉴权失败是 HTTP 441 / 442 这种非标准状态码（`raise_for_status()` 会当 4xx 抛出，但你拿不到 body 里的 `message`）。
- 成功判定写成 `code == 0 or responseCode == "00000000"`（§4 的封装就是这样），两种字段都兼容。成功响应是否同时带两个字段，⚠ 未实测。
- 下载类接口（`/v2/document/download`、`/v2/contract/download`、`/v2/seal/image`）成功时返回文件流，不是 JSON；失败时的格式 ⚠ 文档未说明，按 Content-Type 分支处理。
- 响应码有 4 位（`1101`）和 8 位（`11011101`）两套写法，见 [errors-and-limits.md](errors-and-limits.md)。

## 9. 查询当前应用信息

### 查询开放平台应用信息
**Endpoint**: `GET /company/token/get`
**用途**: 查当前 AppToken 对应应用的名称、回调地址、回调是否加密、回调解密密钥。无请求参数。

**示例响应（result 字段，文档原文）**

| 字段 | 说明 |
| --- | --- |
| `appName` | 应用名称 |
| `accessToken` | 应用的 AppToken |
| `callbackUrl` | 回调地址 |
| `encrypt` | 回调是否加密 |
| `callbackSecretKey` | 加密回调信息的 SecretKey |
| `encryptType` | 加密算法（`AES_ECB` / `AES_CBC`） |

```python
app = qys_call("GET", "/company/token/get")
print(app["callbackUrl"], app["encrypt"], app.get("encryptType"))
```

修改回调配置用 `POST /company/token/update/callback`，见 [callbacks.md](callbacks.md)。

### 对接方信息
**Endpoint**: `GET /company/platforminfo`
**用途**: 取对接方（平台方）公司信息：`status`（`UNREGISTERED` / `AUTH_SUCCESS`）、`id`、`name`、`registerNo`。适合作为"凭证是否可用"的第一个只读调用。

## 10. 子公司与 tenantName

- 一个 AppToken 可以代表集团内多个公司：在云平台把已认证的子公司加入"下级法人单位管理"，调用时带**子公司全名** `tenantName`（FAQ 原文）。
- 几乎所有合同接口都有 `tenantName`：以子公司身份创建的合同，**用 `bizId` 定位时必须同时带 `tenantName`**，否则找不到合同主体；用 `contractId` 定位时不需要。
- 不传 `tenantName` 默认为对接方（平台方）主公司。

## 11. 注意事项与 ⚠

- 先在测试环境（`openapi.qiyuesuo.cn`）联调，上线切 `openapi.qiyuesuo.com`，两套环境的 AppToken / AppSecret、业务分类 ID、模板 ID、印章 ID 都不通用（数据隔离）。
- AppSecret 只放服务端；JS-SDK / 小程序场景由服务端申请临时令牌或转发请求（官方 `jssdk-server` 就是这种转发服务）。
- ⚠ 文档自相矛盾：四个请求头 vs 示例三个头（§3）；`code` vs `responseCode`（§8）。
- ⚠ 文档未说明：时间戳偏差窗口；IP 白名单拒绝时的错误码；HmacSha256 规则；私有化部署地址；接口 QPS 限制。
