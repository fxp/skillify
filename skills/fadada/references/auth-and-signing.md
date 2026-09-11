# 鉴权与请求签名

> 来源：dev.fadada.com FASC OpenAPI 5.1「开发前必读 / 接口请求说明」「API文档 / 服务访问凭证」「附录 / 基本概念」，抓取于 2026-09-11；
> 官方 Python SDK 源码（gitee.com/fadada-cloud/fasc-openapi-python-sdk，分支 `v5.1`，`fasc_api/utils/hashs.py`、`https.py`、`client.py`）。
> **未用真实凭证验证。** 凡是"会返回 / 会报错"的描述，除标注「无凭证探测（2026-09-11）」的以外，均为文档原文，未实测。

## 目录

1. [环境与域名](#1-环境与域名)
2. [一次调用的四个步骤](#2-一次调用的四个步骤)
3. [公共请求参数](#3-公共请求参数)
4. [签名算法（逐步）](#4-签名算法逐步)
5. [获取服务访问凭证](#5-获取服务访问凭证)
6. [Python 请求封装（其余 reference 都复用它）](#6-python-请求封装其余-reference-都复用它)
7. [curl / shell 版签名与调用](#7-curl--shell-版签名与调用)
8. [官方 Python SDK](#8-官方-python-sdk)
9. [公共响应结构](#9-公共响应结构)
10. [无凭证探测结果](#10-无凭证探测结果)
11. [注意事项与 ⚠](#11-注意事项与-)

---

## 1. 环境与域名

| 环境 | Base URL | 法大大 API 服务端公网 IP（你方防火墙放行用） |
| --- | --- | --- |
| 生产 | `https://api.fadada.com/api/v5` | 42.192.31.171 |
| 测试（UAT） | `https://uat-api.fadada.com/api/v5` | 81.69.152.83 |

- 完整 URL = Base URL + 接口地址，例如 `https://uat-api.fadada.com/api/v5/service/get-access-token`。
  文档表格里写的是带尾斜杠的 `.../api/v5/`，拼接时注意不要出现 `//`（⚠ 双斜杠是否被接受，文档未说明）。
- 通过接口拿到的文件下载地址也在 `fadada.com` 下，文档建议对二级域名 `fadada.com` 整体加白，不细分三级域名。
- 你方服务器出口 IP 可能也要在法大大登记：错误码 `100016 IP地址不在白名单`，解决方案是"官网应用管理中配置IP白名单"（文档原文，未实测）。
- 回调请求的来源 IP 是另一套，见 [callbacks.md](callbacks.md)。
- AppId / AppSecret：企业管理员在法大大 SaaS 企业管理后台「应用 - 集成应用」创建应用后查看。
  ⚠ 文档未说明测试环境与生产环境是否共用同一对 AppId/AppSecret——按两套环境分别配置、分别存放。
- 无凭证探测（2026-09-11）：两个 Base URL 都在线，用伪造 AppId 调换 token 接口都返回 `HTTP 200` + JSON（详见 §10）。

## 2. 一次调用的四个步骤

获取服务访问凭证 accessToken → 生成接口参数签名 → 调用业务接口 → 接收响应（文档原文）。

| 项 | 规定（文档原文） |
| --- | --- |
| 协议 | 必须 HTTPS |
| 方法 | 无特殊说明**一律 POST** |
| Content-Type | 只支持 `application/x-www-form-urlencoded` |
| 参数位置 | 公共参数除 `bizContent` 外**全部走请求头**；业务参数全部塞进表单字段 `bizContent`，值是 JSON 字符串 |
| 编码 | UTF-8 |
| 时间 | 所有请求、回调、重定向里的时间都是**毫秒** Unix 时间戳 |

也就是说：业务参数**不是** JSON body，而是 `bizContent=<URL 编码后的 JSON 字符串>` 这一个表单字段。
接口文档里"请求参数"表格列的字段，除非特别说明，都是 `bizContent` 里面的字段。

## 3. 公共请求参数

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `X-FASC-App-Id` | header | 是 | 应用 AppId |
| `X-FASC-Sign-Type` | header | 是 | 固定 `HMAC-SHA256` |
| `X-FASC-Sign` | header | 是 | 签名值（小写 hex，算法见 §4）|
| `X-FASC-Timestamp` | header | 是 | 毫秒时间戳字符串；与平台时间正负相差不能超过 5 分钟（300000 ms），防重放 |
| `X-FASC-Nonce` | header | 是 | 随机串，最长 32 字符，**10 分钟内不能重复** |
| `X-FASC-AccessToken` | header | 业务接口必填 | 换 token 接口不传 |
| `X-FASC-Grant-Type` | header | 仅换 token 接口 | 固定 `client_credential` |
| `X-FASC-Api-SubVersion` | header | 是 | 子版本号，本 skill 固定 `5.1`；"若指定子版本号下不存在接口，系统将会报错返回" |
| `bizContent` | body（表单） | 业务接口必填 | 业务参数 JSON 字符串 |

响应头 `X-FASC-Request-Id`：每次调用唯一的请求 ID，文档建议打进日志，找法大大技术支持排查时提供。

## 4. 签名算法（逐步）

1. **收集参数**：本次请求要发送的所有 `X-FASC-*` 公共请求头（**不含** `X-FASC-Sign` 自己），加上 `bizContent`（业务接口）。
   值为空的参数不参与签名（文档原文："不包括值为空的字段"）——最简单的做法是根本不发送空值的头。
2. **排序**：按参数名 ASCII 升序。大写的 `X-FASC-*` 排在小写的 `bizContent` 前面。
3. **拼接**：`key=value` 用 `&` 连接，得到待签名字符串。**值用原文，不做百分号编码**（官方 Python SDK：`'%s=%s&' % (k, v)`）。
4. `signText = sha256_hex(待签名字符串)`，小写 hex。
5. `signingKey = HMAC_SHA256(key = AppSecret, msg = X-FASC-Timestamp)`，取**原始 32 字节**。
6. `X-FASC-Sign = HMAC_SHA256(key = signingKey, msg = signText).hex()`，小写。

业务接口的待签名字符串长这样（键顺序固定）：

```
X-FASC-AccessToken=<token>&X-FASC-Api-SubVersion=5.1&X-FASC-App-Id=<appId>&X-FASC-Nonce=<nonce>&X-FASC-Sign-Type=HMAC-SHA256&X-FASC-Timestamp=<ts>&bizContent=<json>
```

换 token 接口（没有 AccessToken、多一个 Grant-Type、没有 bizContent）：

```
X-FASC-Api-SubVersion=5.1&X-FASC-App-Id=<appId>&X-FASC-Grant-Type=client_credential&X-FASC-Nonce=<nonce>&X-FASC-Sign-Type=HMAC-SHA256&X-FASC-Timestamp=<ts>
```

**本地自洽性测试向量**（用与官方 SDK 相同的算法在本地计算，**不是平台返回的**，只能用来确认你的实现和 SDK 一致）：

```
AppSecret      = dummysecret
X-FASC-Timestamp = 1757570000000
待签名字符串     = X-FASC-AccessToken=tok&X-FASC-Api-SubVersion=5.1&X-FASC-App-Id=00000000&X-FASC-Nonce=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&X-FASC-Sign-Type=HMAC-SHA256&X-FASC-Timestamp=1757570000000&bizContent={"signTaskId":"1"}
X-FASC-Sign    = 45a459b6af348e6ff2b3e5727823c54f4e5f4e23eea22e916d8da6befefe25bf
```

> ⚠ 文档自相矛盾：正文第 3 步写"使用应用的 AppSecret 对上述待签名字符串进行签名"，读起来像是 `HMAC(AppSecret, 待签名字符串)` 一步完成；
> 但同页的 `FddCryptUtil.sign()` 伪代码和官方 Python SDK 都是上面的**两步派生**（先用时间戳派生临时密钥，再对 sha256 摘要做 HMAC）。按伪代码 / SDK 实现。

> ⚠ 文档写"采用 urlencoded 格式组织参数"，指的是 `key=value&key=value` 的形状；官方 Python SDK 拼接时**不做**百分号编码。
> 注意这只影响**待签名字符串**；HTTP body 本身仍然要按 form-urlencoded 编码发送（requests 的 `data=` / curl 的 `--data-urlencode` 会处理）。

**签名的 `bizContent` 必须和实际发出去的是同一个字符串**：先把 JSON 序列化成字符串，用这个字符串签名，再把这个字符串原样放进表单。
不要签名时用一种序列化、发送时让 HTTP 库再序列化一次。

## 5. 获取服务访问凭证

**Endpoint**: `POST /service/get-access-token`

**用途**: 用 AppId/AppSecret 换 accessToken，调用其他所有业务接口的第一步。

**关键参数**（全部走请求头，无 bizContent）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `X-FASC-App-Id` | string | 是 | AppId |
| `X-FASC-Sign-Type` | string | 是 | `HMAC-SHA256` |
| `X-FASC-Sign` | string | 是 | 签名值 |
| `X-FASC-Timestamp` | string | 是 | 毫秒时间戳 |
| `X-FASC-Nonce` | string | 是 | 随机串 ≤32 |
| `X-FASC-Grant-Type` | string | 是 | 固定 `client_credential` |
| `X-FASC-Api-SubVersion` | string | 是 | `5.1` |

**示例请求**：Python 见 §6 `TokenCache.get()`，curl 见 §7 `fasc_token`。

**示例响应**（字段名来自文档字段表；数值为示意）

```json
{
  "code": "100000",
  "msg": "请求成功",
  "data": {
    "accessToken": "…",
    "expiresIn": "7200"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `data.accessToken` | string | 服务访问凭证。文档要求预留 512 字符存储空间 |
| `data.expiresIn` | string | 过期时间，单位秒，"从发送请求开始的多长时间内有效" |

**注意事项**（文档原文，未实测）

- 有效期默认 7200 秒。**有效期内重复获取会返回同一个 accessToken 并续期**；过期后获取才返回新的。
- 有效期内每调用一次任何 FASC 接口，token 有效期自动延长 2 小时。2 小时内没有调用的话，建议每 2 小时内调一次换 token 接口续期。
- "不能过度频繁调用接口，否则可能会受到拦截"——**缓存 token，不要每个请求都换一次**。
- 每个应用的 token 相互独立，缓存要按 AppId 区分。
- token 失效时业务接口返回 `100002 访问凭证失效`；无凭证探测（2026-09-11）：伪造 token 调业务接口得到 `HTTP 401` + `{"code":"100002","msg":"访问凭证失效"}`。

## 6. Python 请求封装（其余 reference 都复用它）

依赖 `requests`。环境变量：`FASC_APP_ID`、`FASC_APP_SECRET`、`FASC_BASE_URL`（默认 UAT）。
**按文档与官方 SDK 算法编写，未用真实凭证调通。**

```python
"""fasc_client.py —— FASC OpenAPI 5.1 最小调用封装"""
import hashlib
import hmac
import json
import os
import threading
import time
import uuid
from typing import Optional

import requests

BASE_URL = os.environ.get("FASC_BASE_URL", "https://uat-api.fadada.com/api/v5")
APP_ID = os.environ["FASC_APP_ID"]
APP_SECRET = os.environ["FASC_APP_SECRET"]
SUB_VERSION = "5.1"


class FascError(Exception):
    def __init__(self, code, msg, http_status=None, request_id=None):
        super().__init__(f"[{code}] {msg} (http={http_status}, X-FASC-Request-Id={request_id})")
        self.code, self.msg, self.http_status, self.request_id = code, msg, http_status, request_id


def fasc_sign(params: dict, timestamp: str, app_secret: str) -> str:
    """两步派生签名：key=HMAC(AppSecret, ts)；sign=HMAC(key, sha256hex(排序拼接串))"""
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] not in (None, ""))
    signing_key = hmac.new(app_secret.encode("utf-8"), timestamp.encode("utf-8"), hashlib.sha256).digest()
    sign_text = hashlib.sha256(to_sign.encode("utf-8")).hexdigest()
    return hmac.new(signing_key, sign_text.encode("utf-8"), hashlib.sha256).hexdigest()


def _signed_headers(biz_content: Optional[str], access_token: Optional[str]) -> dict:
    ts = str(int(time.time() * 1000))
    headers = {
        "X-FASC-App-Id": APP_ID,
        "X-FASC-Sign-Type": "HMAC-SHA256",
        "X-FASC-Timestamp": ts,
        "X-FASC-Nonce": uuid.uuid4().hex,          # 32 位，10 分钟内不能重复
        "X-FASC-Api-SubVersion": SUB_VERSION,
    }
    if access_token:
        headers["X-FASC-AccessToken"] = access_token
    else:
        headers["X-FASC-Grant-Type"] = "client_credential"
    params = dict(headers)
    if biz_content is not None:
        params["bizContent"] = biz_content
    headers["X-FASC-Sign"] = fasc_sign(params, ts, APP_SECRET)
    return headers


def _parse(resp: requests.Response) -> dict:
    rid = resp.headers.get("X-FASC-Request-Id")
    try:
        body = resp.json()                         # 401 等非 200 也带 JSON body，先解析再判断
    except ValueError:
        raise FascError("NON_JSON", resp.text[:200], resp.status_code, rid)
    if body.get("code") != "100000":               # code 是字符串
        raise FascError(body.get("code"), body.get("msg"), resp.status_code, rid)
    return body


class TokenCache:
    """accessToken 7200 秒；每次调用任何接口自动续期 2 小时（文档原文）。一个 AppId 一个实例。"""

    def __init__(self):
        self._token, self._expire_at, self._lock = None, 0.0, threading.Lock()

    def get(self, force_refresh: bool = False) -> str:
        with self._lock:
            if force_refresh or not self._token or time.time() > self._expire_at - 300:
                resp = requests.post(f"{BASE_URL}/service/get-access-token",
                                     headers=_signed_headers(None, None), timeout=10)
                data = _parse(resp)["data"]
                self._token = data["accessToken"]
                self._expire_at = time.time() + int(data.get("expiresIn") or 7200)
            return self._token

    def touch(self):
        self._expire_at = max(self._expire_at, time.time() + 7200)


TOKENS = TokenCache()


def fasc_call(path: str, biz: dict, timeout: int = 15) -> Optional[dict]:
    """调业务接口，返回 data（可能为 None）；code != "100000" 抛 FascError；100002 自动换 token 重试一次。"""
    biz = {k: v for k, v in biz.items() if v is not None}      # 顶层去掉 None
    biz_str = json.dumps(biz, ensure_ascii=False, separators=(",", ":"))
    for attempt in (0, 1):
        token = TOKENS.get(force_refresh=(attempt == 1))
        resp = requests.post(f"{BASE_URL}{path}",
                             headers=_signed_headers(biz_str, token),
                             data={"bizContent": biz_str},     # 签名用的就是这个字符串
                             timeout=timeout)
        try:
            body = _parse(resp)
        except FascError as e:
            if e.code == "100002" and attempt == 0:
                continue
            raise
        TOKENS.touch()
        return body.get("data")
```

用法：

```python
from fasc_client import fasc_call, FascError

try:
    data = fasc_call("/sign-task/start", {"signTaskId": "1656657193146145802"})
except FascError as e:
    print(e.code, e.msg, e.request_id)
```

## 7. curl / shell 版签名与调用

依赖 `openssl`、`xxd`、`python3`（只用来取毫秒时间戳；macOS 的 `date` 没有 `%N`）。

```bash
# 需要：export FASC_APP_ID=… FASC_APP_SECRET=… FASC_BASE_URL=https://uat-api.fadada.com/api/v5
fasc_sign() {   # $1=timestamp  $2=待签名字符串
  local key
  key=$(printf '%s' "$1" | openssl dgst -sha256 -mac HMAC -macopt "key:$FASC_APP_SECRET" -binary | xxd -p -c 256)
  printf '%s' "$2" | openssl dgst -sha256 -hex | awk '{printf "%s", $NF}' \
    | openssl dgst -sha256 -mac HMAC -macopt "hexkey:$key" -hex | awk '{print $NF}'
}
fasc_ts()    { python3 -c 'import time;print(int(time.time()*1000))'; }
fasc_nonce() { uuidgen | tr -d '-' | tr 'A-Z' 'a-z'; }

# 1) 换 token
fasc_token() {
  local ts nonce str
  ts=$(fasc_ts); nonce=$(fasc_nonce)
  str="X-FASC-Api-SubVersion=5.1&X-FASC-App-Id=$FASC_APP_ID&X-FASC-Grant-Type=client_credential&X-FASC-Nonce=$nonce&X-FASC-Sign-Type=HMAC-SHA256&X-FASC-Timestamp=$ts"
  curl -sS -X POST "$FASC_BASE_URL/service/get-access-token" \
    -H "X-FASC-App-Id: $FASC_APP_ID" -H 'X-FASC-Sign-Type: HMAC-SHA256' \
    -H "X-FASC-Timestamp: $ts" -H "X-FASC-Nonce: $nonce" \
    -H 'X-FASC-Grant-Type: client_credential' -H 'X-FASC-Api-SubVersion: 5.1' \
    -H "X-FASC-Sign: $(fasc_sign "$ts" "$str")" \
    -H 'Content-Type: application/x-www-form-urlencoded'
}
# export FASC_TOKEN=$(fasc_token | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["accessToken"])')

# 2) 业务接口：$1=路径  $2=bizContent（紧凑 JSON；签名和发送是同一个字符串）
fasc_call() {
  local ts nonce str
  ts=$(fasc_ts); nonce=$(fasc_nonce)
  str="X-FASC-AccessToken=$FASC_TOKEN&X-FASC-Api-SubVersion=5.1&X-FASC-App-Id=$FASC_APP_ID&X-FASC-Nonce=$nonce&X-FASC-Sign-Type=HMAC-SHA256&X-FASC-Timestamp=$ts&bizContent=$2"
  curl -sS -X POST "$FASC_BASE_URL$1" \
    -H "X-FASC-App-Id: $FASC_APP_ID" -H 'X-FASC-Sign-Type: HMAC-SHA256' \
    -H "X-FASC-Timestamp: $ts" -H "X-FASC-Nonce: $nonce" -H 'X-FASC-Api-SubVersion: 5.1' \
    -H "X-FASC-AccessToken: $FASC_TOKEN" -H "X-FASC-Sign: $(fasc_sign "$ts" "$str")" \
    --data-urlencode "bizContent=$2"
}
# 例：fasc_call /sign-task/start '{"signTaskId":"1656657193146145802"}'
```

其余 reference 里的 curl 示例都用这里的 `fasc_call`。`--data-urlencode` 会自动带 `Content-Type: application/x-www-form-urlencoded`。

## 8. 官方 Python SDK

- 官方提供 Java / Python / Go / PHP / C# / .NET Framework / Node.js SDK，仓库在 `gitee.com/fadada-cloud/fasc-openapi-<语言>-sdk`（链接来自开发者站前端代码）。
- Python SDK 的 README：要求 Python 3.8+；安装方式是拿到源码后 `python setup.py install`，再 `pip install -r requirements.txt`。
  ⚠ 是否发布到 PyPI、包名是什么，文档未说明——不要凭印象写 `pip install fadada`。
- v5.1 与 v5.0 是两个子版本，SDK 在 gitee 上是两个分支（`v5.1` / `v5.0`），不要混用。

README 里的用法：

```python
from fasc_api.client.client import ApiClient
from fasc_api.client.service_client import ServiceClient
from fasc_api.exception.exceptions import ClientException, ServerException

api_client = ApiClient('appId', 'appSecret', request_url='https://uat-api.fadada.com/api/v5', log=True, timeout=10)
try:
    result = ServiceClient.get_access_token(api_client)
    api_client.set_access_token(result['data']['accessToken'])   # 后续调用前设置
except ClientException as e:   # 客户端初始化 / 网络异常
    print(e)
except ServerException as e:   # code != "100000" 的业务异常
    print(e)
```

从 SDK 源码能看出来的几点（源码观察，未运行）：

- `request_url` 直接和 `/service/get-access-token` 这类路径拼接，所以要传到 `/api/v5` 为止、不带尾斜杠。
- 签名、表单提交方式与 §4 完全一致：`requests.post(url, data={"bizContent": json.dumps(data)}, headers=…)`。
- `ApiClient` 把 `app_id`、`app_secret`、`request_url` 存成**类属性**，同一进程里创建第二个 `ApiClient` 会覆盖第一个——一个进程只对接一个应用时才适合直接用。
- 业务模块：`UserClient`、`CorpClient`、`OrgClient`、`SealClient`、`DocClient`、`TemplateClient`、`SignTaskClient`、`EUIClient` 等；接口路径常量在 `fasc_api/utils/url_params.py`。
- SDK 的"查询签署任务详情"路径常量是 `/sign-task/app/get-detail`——文档里这是**旧版（不推荐）**详情接口，新版是 `/sign-task/get-detail`，见 [sign-tasks.md](sign-tasks.md) §15。

## 9. 公共响应结构

| 字段 | 位置 | 类型 | 说明 |
| --- | --- | --- | --- |
| `X-FASC-Request-Id` | header | string | 请求 ID，建议打日志 |
| `code` | body | string | 返回码，**`"100000"` 才是成功** |
| `msg` | body | string | 描述 |
| `data` | body | object | 业务数据，可能为 `null` |

```json
{"code": "100000", "msg": "请求成功", "data": {"url": "https://z.fadada.com/DI72FT7i89"}}
{"code": "100002", "msg": "访问凭证失效", "data": null}
```

<!-- Gap: 文档的公共响应只列 code/msg/data；无凭证探测（2026-09-11）的每个错误响应都多一个布尔字段 success（值为 false），文档未提。 -->
无凭证探测（2026-09-11）：实际错误响应形如 `{"msg":"…","code":"100001","data":null,"success":false}`，**多一个文档没写的 `success` 字段**。
写强类型解析时不要假设只有三个字段；判成功仍以 `code == "100000"` 为准（`success` 在成功响应里是否存在、取值如何，⚠ 未验证）。

## 10. 无凭证探测结果

全部使用伪造 AppId `test`、伪造签名 / 伪造 token，不含任何真实凭证。完整记录在 `fadada-workspace/probe-log.md`。

| # | 请求 | HTTP | 响应 | 说明 |
| --- | --- | --- | --- | --- |
| P1 | UAT `POST /service/get-access-token`，全套伪造 header | 200 | `{"msg":"未获取有效的平台信息","code":"100001",…}` | AppId 无效走 100001，不是 401 |
| P2 | 生产 同上 | 200 | 同 P1 | 生产域名在线，行为一致 |
| P3 | UAT `POST /sign-task/create`，不带任何 X-FASC 头 | 200 | `{"msg":"X-FASC-App-Id 不能为空","code":"100012",…}` | 缺头是 100012，不是错误码表里的 100010 |
| P4 | UAT 换 token 改用 GET | 200 | 同 P1 | 方法校验不先于 AppId 校验（不能据此说 GET 可用） |
| P5 | UAT 不存在的路径 + 伪造 token | 401 | `{"msg":"访问凭证失效","code":"100002",…}` | token 校验先于路由：token 无效时拼错路径看不出来 |
| P6 | UAT `/sign-task/get-detail` + 伪造 token | 401 | 同 P5 | — |
| P7 | UAT `/sign-task/app/get-detail` + 伪造 token | 401 | 同 P5 | 新版 / 旧版两个详情路径都返回 100002，无凭证无法确认两者现状 |
| P8 | UAT 换 token，时间戳设为 10 分钟前 | 200 | `{"msg":"请求已过期","code":"100001",…}` | 时间戳校验先于 AppId 校验；100001 覆盖多种原因 |

结论：

- 鉴权类错误**不一定**是非 200：AppId 无效、时间戳过期是 `HTTP 200 + 100001`，token 无效是 `HTTP 401 + 100002`。先解析 body 再判断。
- `100001` 在错误码表里是"不可预知异常，请稍后重试"，但探测里它也用于"AppId 无效""请求已过期"，这两种重试没用——**遇到 100001 要看 msg**（见 [errors-and-limits.md](errors-and-limits.md)）。

## 11. 注意事项与 ⚠

- **每次请求都生成新的 Timestamp 和 Nonce**；服务器要做 NTP 校时，时间偏差超过 5 分钟会被拒（探测到的 msg 是"请求已过期"）。
- **`X-FASC-Api-SubVersion` 必须带**，本 skill 全部按 `5.1` 写。
- 业务 JSON 里的布尔值按 JSON 布尔传（`true`/`false`）。文档部分请求示例把布尔写成字符串 `"true"`，与字段表的 `boolean` 类型不一致，⚠ 字符串是否被接受未验证。
- 文档 Java 示例的注释写"bizContent参数中的json字符串，不包括空的字段"——建议构造 bizContent 时去掉 `null` / 空串字段。⚠ 带空字段是否影响签名或校验，文档未说明。
- 一律 POST。文档说"如果无特殊说明，总是使用 POST"；本 skill 覆盖的接口全部是 POST。
- 响应头里的 `X-FASC-Request-Id` 一定要记日志。
- 本 skill 覆盖的接口之外，FASC 还有组织管理、印章、计费、审批、合同起草 / 归档、工具能力等模块，签名与请求格式完全相同。
