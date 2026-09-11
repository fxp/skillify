# 鉴权与请求签名（SaaS API V3）

> 内容整理自 e签宝开放平台《e签宝公有云API调用说明》《请求签名鉴权方式说明》《如何计算Body体的Content-MD5值》
> 《OAuthToken鉴权方式说明》《基于HmacSM3算法的签名鉴权方式说明》《SaaS API接口报错401排查流程》
> 《沙箱模拟环境使用说明》《正式生产环境使用说明》《公有云API域名列表》（`open.esign.cn/doc/opendoc/dev-guide3/*`、`helper/*`，抓取于 2026-09-11）。
> **未用真实凭证调用验证**。§11 的结论来自无凭证探测（伪造 appId，2026-09-11，复跑两次一致）；其余报错与行为为「文档原文，未实测」。
> §5 的签名函数用本地测试向量校验过（不联网，脚本 `esign-workspace/sign_check.py`），但**签名结果从未被 e签宝网关接受过**。

## 目录

1. [环境、域名与应用准备](#1-环境域名与应用准备)
2. [两种鉴权方式：用请求签名，别用 OAuthToken](#2-两种鉴权方式用请求签名别用-oauthtoken)
3. [公共请求头](#3-公共请求头)
4. [待签名字符串与 Content-MD5](#4-待签名字符串与-content-md5)
5. [Python 封装：esign_request()](#5-python-封装esign_request)
6. [curl + openssl 手算签名](#6-curl--openssl-手算签名)
7. [让自定义 Header 参与签名](#7-让自定义-header-参与签名)
8. [HmacSM3（国密）变体](#8-hmacsm3国密变体)
9. [OAuthToken 方式（仅作了解）](#9-oauthtoken-方式仅作了解)
10. [响应结构与成功判断](#10-响应结构与成功判断)
11. [无凭证探测结果](#11-无凭证探测结果)
12. [⚠ 本文件的未说明 / 矛盾之处](#12--本文件的未说明--矛盾之处)

---

## 1. 环境、域名与应用准备

| 环境 | API 域名 | 文件上传下载（OSS） | 回调来源 IP |
| --- | --- | --- | --- |
| 正式生产 | `https://openapi.esign.cn` | `oss.esign.cn`（加密模式 `upload.esign.cn`） | 118.31.35.8 |
| 沙箱模拟 | `https://smlopenapi.esign.cn` | `esignoss.esign.cn`（加密模式 `upload-pre.esign.cn`） | 47.96.79.204 |

- 沙箱只用于联调，签的合同**无法律效力**；沙箱数据不能迁到正式，上线要在正式环境重新创建应用、模板等。
- **两套环境的 AppId / AppSecret 不通用**。沙箱应用在正式开放平台 `open.esign.cn` 控制台的【沙箱服务】里创建。
  401 排查页原文：正式环境 appId 一般 `5111` 开头，沙箱一般 `7438` 或 `4438` 开头——拿到 appId 先对一下前缀和域名。
- 调用前必须在应用的【安全配置】里添加**调用方公网出口 IP 白名单**；**2026-07-31 起不再允许配置 `*`**，只能填具体 IP。
  白名单不匹配返回 `403 IP白名单不匹配`（错误码页原文）。
- 签署 / 认证完成后要跳回自家页面的，还要在控制台配置**重定向域名白名单**，否则用户会看到“您即将访问的页面可能有安全风险”。
- 全部走 HTTPS + TLS1.2，UTF-8，JSON。正式环境禁止压测和渗透测试；沙箱压测需先报备。上线前 2–3 天向 e签宝报备。

---

## 2. 两种鉴权方式：用请求签名，别用 OAuthToken

| | 请求签名（Signature）| OAuthToken |
| --- | --- | --- |
| 官方态度 | **优先推荐** | 不推荐 |
| 做法 | 每个请求用 AppSecret 对待签名串做 HmacSHA256 | 先 `GET /v1/oauth2/access_token` 换 token，放 `X-Tsign-Open-Token` |
| 坑 | 待签名串拼接规则严格 | token 120 分钟；**再次获取会让旧 token 在 5 分钟后失效**，多台服务器各自换 token 会互相踢掉 |
| 模式开关 | 请求头 `X-Tsign-Open-Auth-Mode: Signature` | 不传 Auth-Mode 即默认 token 模式 |

**`X-Tsign-Open-Auth-Mode: Signature` 漏传时，网关按 OAuthToken 模式处理，返回 `TOKEN_CANT_BE_NULL`**（无凭证探测证实，见 §11 P9）。
看到这个报错先查 Auth-Mode 头，别去换 token。

---

## 3. 公共请求头

| 头 | 必填 | 值 |
| --- | --- | --- |
| `X-Tsign-Open-App-Id` | 是 | 应用 ID |
| `X-Tsign-Open-Auth-Mode` | 是 | 固定 `Signature` |
| `X-Tsign-Open-Ca-Signature` | 是 | 请求签名值（Base64） |
| `X-Tsign-Open-Ca-Timestamp` | 是 | 当前 Unix 时间戳，**毫秒**；15 分钟有效，建议每次取当前时间 |
| `Accept` | 是 | 建议 `*/*`（部分 HTTP 库不设 Accept 时会自动补 `*/*`，显式设置最稳） |
| `Content-Type` | 是 | 建议 `application/json; charset=UTF-8`；GET/DELETE 无 body 时可为空串或不传 |
| `Content-MD5` | 否（有 body 时应传） | body 的 Content-MD5；GET/DELETE 无 body 时为空串或不传 |
| `X-Tsign-Open-Ca-Signature-Headers` | 否 | 自选 Header 参与签名时才用，见 §7 |

**头里的值与待签名串里的值必须逐字一致**（尤其 `Accept`、`Content-Type`、`Content-MD5`）。`Content-Type` 里写了 `; charset=UTF-8`，签名串里也要写。

---

## 4. 待签名字符串与 Content-MD5

### 4.1 待签名字符串（StringToSign）

七个字段按顺序用 `\n` 连接：

```
HTTPMethod\n
Accept\n
Content-MD5\n
Content-Type\n
Date\n
Headers\n          ← 只有 Headers 非空时才出现这一行（连同它后面的 \n）
PathAndParameters
```

| 字段 | 规则 |
| --- | --- |
| HTTPMethod | 全大写：`GET`、`POST`、`PUT`、`DELETE` |
| Accept | 请求头 Accept 的值，通常 `*/*` |
| Content-MD5 | 请求头 Content-MD5 的值；无 body 时空串（**空串也要保留它后面的 `\n`**） |
| Content-Type | 请求头 Content-Type 的值；可为空串 |
| Date | 请求头 Date 的值（RFC822）；通常不传，**空串但保留 `\n`** |
| Headers | 自选参与签名的 Header，见 §7；为空时**这一行和它的 `\n` 都不要** |
| PathAndParameters | 不含 `https://host`；有 query 时 `Path?k1=v1&k2=v2`，**key 按 ASCII 升序**；值为空只写 key（不写 `=`）；同名多值取第一个；**值不做 URL 编码**（实际请求 URL 里中文要编码，签名串里不编码） |

大小写敏感。文档给的“拼接后示例”（`POST /v3/sign-flow/create-by-file`，无 Date、无 Headers）：

```
POST
*/*
uxydqKBMBy6x1siClKEQ6Q==
application/json; charset=UTF-8

/v3/sign-flow/create-by-file
```

注意 `application/json; charset=UTF-8` 后面有一个空行——那是空的 Date。

### 4.2 签名值

```
X-Tsign-Open-Ca-Signature = Base64( HmacSHA256( key = AppSecret(UTF-8), msg = StringToSign(UTF-8) ) )
```

输出是 **Base64**（不是 hex）。回调验签用的是 hex，别混（见 [callbacks.md](callbacks.md)）。

### 4.3 Content-MD5

```
Content-MD5 = Base64( MD5( body 的 UTF-8 原始字节 ) )     ← MD5 的 16 字节二进制，不是 32 位 hex 字符串
```

- 算 MD5 用的字节必须和真正发出去的 body **一模一样**：先序列化一次，MD5 与发送共用同一个 bytes。
  用 `requests.post(json=...)` 会自己再序列化一遍，空格 / 键序 / 中文转义可能不同，导致 `INVALID_SIGNATURE`。
- 文件上传时 body 里的 `contentMd5` 是**文件**的 Content-MD5，同一算法、不同数据（见 [files-and-templates.md §2](files-and-templates.md)）。
- 本地向量：`Content-MD5("{}") = mZFLkyvTelC5g8XnyQrpOw==`；`Content-MD5('{"name":"张某人","age":18}') = jsmDBtOHeXhiozlzXsFtlg==`。

---

## 5. Python 封装：esign_request()

后面所有 reference 的示例都调用这里的 `esign_request()`。凭证只从环境变量读。

```python
from __future__ import annotations
import base64, hashlib, hmac, json, os, time, urllib.parse
import requests

ESIGN_HOST = os.environ.get("ESIGN_HOST", "https://smlopenapi.esign.cn")   # 正式：https://openapi.esign.cn
ESIGN_APP_ID = os.environ["ESIGN_APP_ID"]
ESIGN_APP_SECRET = os.environ["ESIGN_APP_SECRET"]


class ESignError(Exception):
    def __init__(self, http_status, code, message, payload):
        super().__init__(f"HTTP {http_status} code={code} message={message}")
        self.http_status, self.code, self.message, self.payload = http_status, code, message, payload


def content_md5(data: bytes) -> str:
    return base64.b64encode(hashlib.md5(data).digest()).decode()


def _norm_query(query: dict | None) -> dict:
    out = {}
    for k, v in (query or {}).items():
        if isinstance(v, (list, tuple)):
            v = v[0] if v else None                      # 同名多值：签名只取第一个
        if v is None:
            continue                                     # 不发送的参数也不参与签名
        out[k] = ("true" if v else "false") if isinstance(v, bool) else str(v)
    return out


def path_and_params(path: str, query: dict | None = None) -> str:
    if not query:
        return path
    parts = [k if query[k] == "" else f"{k}={query[k]}" for k in sorted(query)]   # 值不编码
    return path + "?" + "&".join(parts)


def string_to_sign(method, accept, md5, ctype, date, headers_str, pap) -> str:
    s = f"{method.upper()}\n{accept}\n{md5}\n{ctype}\n{date}\n"
    return s + (f"{headers_str}\n{pap}" if headers_str else pap)


def sign(sts: str, secret: str) -> str:
    return base64.b64encode(hmac.new(secret.encode("utf-8"), sts.encode("utf-8"), hashlib.sha256).digest()).decode()


def esign_request(method: str, path: str, body: dict | None = None, query: dict | None = None, timeout: int = 30) -> dict:
    method = method.upper()
    accept, ctype = "*/*", "application/json; charset=UTF-8"
    q = _norm_query(query)
    raw, md5 = b"", ""
    if body is not None:
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")   # 只序列化这一次
        md5 = content_md5(raw)
    sts = string_to_sign(method, accept, md5, ctype, "", "", path_and_params(path, q))
    headers = {
        "X-Tsign-Open-App-Id": ESIGN_APP_ID,
        "X-Tsign-Open-Auth-Mode": "Signature",
        "X-Tsign-Open-Ca-Timestamp": str(int(time.time() * 1000)),
        "X-Tsign-Open-Ca-Signature": sign(sts, ESIGN_APP_SECRET),
        "Accept": accept,
        "Content-Type": ctype,
        "Content-MD5": md5,
    }
    url = ESIGN_HOST + path
    if q:
        url += "?" + urllib.parse.urlencode(sorted(q.items()))   # URL 里要编码；签名串里不编码
    resp = requests.request(method, url, data=raw if body is not None else None, headers=headers, timeout=timeout)
    try:
        payload = resp.json()                 # 网关 401 也是 JSON，先解析再判断
    except ValueError:
        raise ESignError(resp.status_code, None, resp.text[:200], None)
    if payload.get("code") != 0:              # 业务成功只有 code == 0（int）
        raise ESignError(resp.status_code, payload.get("code"), payload.get("message"), payload)
    return payload


if __name__ == "__main__":
    print(esign_request("GET", "/v3/organizations/identity-info", query={"orgName": "某某科技有限公司"}))
```

要点：
- `json.dumps(..., separators=(",", ":"), ensure_ascii=False)` 的结果既用来算 MD5 也原样发送；不要改用 `requests(json=...)`。
- GET / DELETE 无 body 时 `Content-MD5` 为空串，但 `Content-Type` 仍发送并进签名串（与文档 Java 示例 `testGet` 一致）。
- 带 query 的 DELETE（如 `DELETE /v3/sign-flow/{id}/signers/sign-fields?signFieldIds=a,b`）同样把 query 放进 PathAndParameters：
  `esign_request("DELETE", f"/v3/sign-flow/{fid}/signers/sign-fields", query={"signFieldIds": "a,b"})`。
- 布尔 query 值要转成小写 `true/false`（Python 的 `str(True)` 是 `True`）。

**本地测试向量**（AppSecret 用假值 `dummysecret`，只验证拼接与编码，不代表网关会接受）：

| 输入 | 结果 |
| --- | --- |
| §4.1 文档示例串，secret=`dummysecret` | `6dYuzEqXUobDAEL97Ja5pvH3QWHpn4R5iJSWEvIsCo8=` |
| `GET\n*/*\n\napplication/json; charset=UTF-8\n\n/v3/sign-flow/abc123/detail`，secret=`dummysecret` | `xG4jw3vs+xusJ0x3XkIJBwxpTHHzEHqdMGOJ45Ry8Fk=` |
| `path_and_params("/v3/organizations/identity-info", {"orgName":"某某科技有限公司","orgIDCardType":""})` | `/v3/organizations/identity-info?orgIDCardType&orgName=某某科技有限公司` |

官方有《鉴权签名计算》在线工具 `https://open.esign.cn/tools/signature` 可对照（本 skill 未使用该工具）。
官方提供 Java / PHP / .NET / Python 的对接示例 DEMO（zip 下载，本 skill 未下载、未参考）；Go 无官方 DEMO。

---

## 6. curl + openssl 手算签名

```bash
export ESIGN_HOST=https://smlopenapi.esign.cn     # 正式换成 https://openapi.esign.cn
BODY='{"docTemplateName":"劳动合同模板","fileId":"<fileId>"}'
PATH_Q='/v3/doc-templates/doc-template-create-url'
BODY_MD5=$(printf '%s' "$BODY" | openssl dgst -md5 -binary | base64)
STS=$(printf 'POST\n*/*\n%s\napplication/json; charset=UTF-8\n\n%s' "$BODY_MD5" "$PATH_Q")
SIG=$(printf '%s' "$STS" | openssl dgst -sha256 -hmac "$ESIGN_APP_SECRET" -binary | base64)
TS=$(python3 -c 'import time;print(int(time.time()*1000))')

curl -sS -X POST "$ESIGN_HOST$PATH_Q" \
  -H "X-Tsign-Open-App-Id: $ESIGN_APP_ID" -H 'X-Tsign-Open-Auth-Mode: Signature' \
  -H "X-Tsign-Open-Ca-Timestamp: $TS" -H "X-Tsign-Open-Ca-Signature: $SIG" \
  -H 'Accept: */*' -H 'Content-Type: application/json; charset=UTF-8' -H "Content-MD5: $BODY_MD5" \
  --data-raw "$BODY"
```

GET 无 body：`STS=$(printf 'GET\n*/*\n\napplication/json; charset=UTF-8\n\n%s' "/v3/sign-flow/$FLOW_ID/detail")`，不带 `--data`，`Content-MD5` 头可省略。

---

## 7. 让自定义 Header 参与签名

一般不需要。需要时（文档原文）：
- 选中的 Header 按 key ASCII 升序，逐个写 `Key:Value\n`；值为空写 `Key:\n`；
- 这些 key 用英文逗号连起来放进请求头 `X-Tsign-Open-Ca-Signature-Headers`；
- 不参与 Header 签名的：`X-Tsign-Open-Ca-Signature`、`X-Tsign-Open-Ca-Signature-Headers`、`Accept`、`Content-MD5`、`Content-Type`、`Date`；
- Headers 段放在 Date 行之后、PathAndParameters 之前，并以 `\n` 与 PathAndParameters 分隔。

⚠ 文档写法是 “`HeaderKey1 + ":" + HeaderValue1 + "\n" + HeaderKey2 + ...`”，最后一个 Header 之后是否已含 `\n`、
与“Headers 非空时再追加 `\n`”是否会产生两个换行，文档未说清；按 Java 示例（`append(Headers).append("\n").append(url)`），Headers 串末尾**不应**再带 `\n`。

---

## 8. HmacSM3（国密）变体

与 HmacSHA256 版的差别（文档原文）：
- 加请求头 `X-Tsign-Content-Hash-Algorithm: SM3`、`X-Tsign-Open-Ca-Signature-Algorithm: HmacSM3`；
- `Content-MD5` 换成 `X-Tsign-Content-Hash`（body 的 SM3 摘要），待签名串第三行相应变为 Content-Hash；
- 签名改用 HmacSM3，其余头与拼接规则不变。Python 标准库没有 SM3，需要第三方国密库（本 skill 不展开）。

---

## 9. OAuthToken 方式（仅作了解）

| Endpoint | 参数（query） | 说明 |
| --- | --- | --- |
| `GET /v1/oauth2/access_token` | `appId`、`secret`、`grantType=client_credentials` | 无需请求头；返回 `data.token`、`data.expiresIn`（**毫秒时间戳字符串**，是截止时刻不是秒数）、`data.refreshToken` |
| `GET /v1/oauth2/refresh_token` | `appId`、`refreshToken`、`grantType=refresh_token` | 刷新 |

业务请求头：`X-Tsign-Open-App-Id`、`X-Tsign-Open-Token`、`Content-Type: application/json; charset=UTF-8`。
token 120 分钟有效，建议提前 5 分钟刷新；**任何一次重新获取都会让上一个 token 只剩 5 分钟**，分布式部署必须集中换取、共享同一个 token。
这个接口把 `secret` 放在 URL query 里，容易进访问日志——这也是更推荐请求签名的原因之一。

---

## 10. 响应结构与成功判断

| 场景 | HTTP | Body |
| --- | --- | --- |
| 业务成功 | 200 | `{"code": 0, "message": "成功", "data": {...}}` |
| 业务失败 | ⚠ 文档未说明 HTTP 状态 | `{"code": 1435002, "message": "参数错误: …", "data": null}` 之类 |
| 网关鉴权失败 | **401**（探测证实） | `{"success": false, "code": 401, "message": "无效的应用"}`（**没有 data 字段，多一个 success 字段**） |
| IP 白名单 | 403（错误码页原文） | `IP白名单不匹配` |
| 换 token 失败 | **200**（探测证实） | `{"code": 72000032, "message": "应用停用或应用不存在", "data": null}` |
| PUT 文件流到 OSS | 200 / 400 / 403 / 405 | 成功 `{"errCode":0,"msg":"成功"}`；失败是 OSS 的错误（见 [files-and-templates.md §3](files-and-templates.md)） |

规则：
- **一律先解析 JSON，再按 `code == 0`（int）判断**；不要只看 HTTP 状态，也不要按 `message` 文案判断（文档明确说 message 会调整）。
- 响应里可能新增字段，反序列化要容忍未知字段（文档专门有一页讲 JSON 反序列化容错）。
- 401 的 `message` 细分见 [errors-and-limits.md §2](errors-and-limits.md)。

---

## 11. 无凭证探测结果

2026-09-11，伪造 `appId=test` + 伪造签名，每条复跑两次结果一致。完整命令见 `esign-workspace/probe-log.md`。

| # | 请求 | 结果 |
| --- | --- | --- |
| P1 | 沙箱 `POST /v3/files/file-upload-url`，完整签名头，伪造 appId | HTTP 401，`{"success":false,"code":401,"message":"无效的应用"}` |
| P2 | 同上，正式域名 | HTTP 401，同一 body（正式域名在线） |
| P3 | 沙箱，不带任何 `X-Tsign-Open-*` 头 | HTTP 401，`TOKEN_CANT_BE_NULL` |
| P4 | 沙箱 `GET /v3/sign-flow/test/detail`，伪造 appId | HTTP 401，`无效的应用` |
| P5 | 时间戳设为 20 分钟前 | 仍是 `无效的应用`：应用校验先于时间戳校验，15 分钟窗口无法无凭证验证 |
| P6 | 不存在的路径 `/v3/not-exist-xyz` | HTTP 401，`无效的应用`：先鉴权后路由，401 时无法判断路径对错 |
| P7 | `GET /v1/oauth2/access_token?appId=test&secret=test&grantType=client_credentials` | **HTTP 200**，`{"code":72000032,"message":"应用停用或应用不存在","data":null}` |
| P8 | 伪造 `X-Tsign-Open-Token` | HTTP 401，`无效的应用` |
| P9 | 只带 `X-Tsign-Open-App-Id`，漏 Auth-Mode / 签名 / 时间戳 | HTTP 401，`TOKEN_CANT_BE_NULL`（与 401 排查页“未指定 Auth-Mode 默认 token 模式”一致） |

---

## 12. ⚠ 本文件的未说明 / 矛盾之处

| 位置 | 问题 |
| --- | --- |
| §3 | `Content-MD5` 标为“否”（非必填），但 POST 带 body 时省略它能否通过签名校验 ⚠ 文档未说明；稳妥做法是有 body 就传 |
| §4.1 | Content-Type 在签名串里是否允许与头里大小写 / 空格不同 ⚠ 文档只说“大小写敏感”，按逐字一致处理 |
| §7 | 自选 Headers 段末尾换行的写法，正文与示例代码表述不完全一致 |
| §10 | 业务失败（非 0 code）时的 HTTP 状态码 ⚠ 文档未说明 |
| §10 | 公共响应格式表只有 `code/message/data`，而网关 401 响应是 `success/code/message`（401 排查页有写，探测证实） |
| §11 P7 | 换 token 返回的 `72000032` 未出现在抓到的任何错误码页 |
