# 鉴权与环境：ATS（招聘）与 People（人事）两套 API

> 来源：ATS <https://www.mokahr.com/docs/api/>、People <https://people.mokahr.com/docs/api/view/v1.html>（均抓取于 2026-09-11）。
> **文档版，未用真实凭证调用验证。** 报错 / 行为描述除标「无凭证探测（2026-09-11）」或「本地复算」外，均为「文档原文，未实测」。
> 探测编号（A1…、P1…、B1…、C1）对应 `moka-workspace/probe-log.md`，每条都有可直接复跑的完整命令。

## 目录

1. [先分清两套 API](#1-先分清两套-api)
2. [域名与环境](#2-域名与环境)
3. [ATS：HTTP Basic Auth（API Key）](#3-atshttp-basic-authapi-key)
4. [ATS：OAuth2 client_credentials（accessToken）](#4-atsoauth2-client_credentialsaccesstoken)
5. [ATS：orgId 与招聘模式这两个"隐形必填"](#5-atsorgid-与招聘模式这两个隐形必填)
6. [People：Basic Auth + query 签名（MD5withRSA）](#6-peoplebasic-auth--query-签名md5withrsa)
7. [鉴权失败时长什么样（无凭证探测）](#7-鉴权失败时长什么样无凭证探测)
8. [环境变量约定与最小客户端](#8-环境变量约定与最小客户端)
9. [⚠ 本文件的未说明 / 矛盾之处](#9--本文件的未说明--矛盾之处)

---

## 1. 先分清两套 API

Moka 开放平台首页（<https://open.mokahr.com/>）给出两张入口卡片：**ATS OpenAPI**（招聘，Moka Hire）与 **People OpenAPI**（人事，Moka People）。
两套文档、两种鉴权、两种响应结构，**不能套用对方的写法**。

| 项 | ATS（招聘） | People（人事） |
| :--- | :--- | :--- |
| 文档 | `www.mokahr.com/docs/api/` | `people.mokahr.com/docs/api/view/v1.html` |
| Base URL | `https://api.mokahr.com/api-platform/v1`（另有 `/api-platform/v2`、`/v3`、`/api-platform/<模块>/…`、`/open-api/ats/v3/…`，**以每个接口文档写的完整 URL 为准**） | `https://api.mokahr.com/api-platform/hcm/oapi`（其下再分 `/v1/…`、`/v2/…`） |
| 鉴权 | `Authorization: Basic base64("<API_KEY>:")`；或 OAuth2 换 `accessToken` 后 `Authorization: Bearer <accessToken>` | `Authorization: Basic base64("<apiKey>:")` **加** query 参数 `entCode`、`apiCode`、`nonce`、`timestamp`、`sign`（部分接口还要 `userName`） |
| 凭证从哪来 | 向 CSM（客户成功经理）索取 API Key；OAuth2 的 `clientID` / `clientSecret` 也找 CSM | `entCode`、apiKey 由 CSM 提供；`apiCode` 是 People 后台「设置 - 对外接口设置」里**每个接口单独生成**的接口编码 |
| 响应结构 | 各接口不统一（见 `errors-and-limits.md` 第 1 节） | 大多为 `{"code":200,"msg":"…","data":{…}}` |
| 主动推送 | 需 CSM 配置；POST JSON，HMAC-SHA256 签名放 URL `?sign=` | 在「对外接口设置」配置；多数是 **GET**，只带 ID，靠 `pwd` 校验 |

ATS 与 People 的 apiKey 是否同一个：⚠ 文档未说明。按两个独立凭证处理（两个环境变量）。

## 2. 域名与环境

| 环境 | 地址 | 来源 |
| :--- | :--- | :--- |
| 中国版正式 | `https://api.mokahr.com` | 两份文档 |
| 国际版正式 | `https://hire-r1-api.mokahr.com`（示例：`https://hire-r1-api.mokahr.com/api-platform/v1/data/moved_applications`） | ATS 文档「Open API 域名说明」 |
| ATS 测试环境 | `https://api-staging-3.mokahr.com/api-platform/v1` | ATS 文档「文档介绍」 |
| People 测试环境 | ⚠ 文档未说明 | — |

- 无凭证探测（2026-09-11，#A8 / #A9）：国际版域名与 ATS 测试域名对伪造 Key 的 `GET /api-platform/v1/archiveReasons` 都返回和正式域名相同的
  `HTTP 500 {"code":-1,"success":false,"msg":"无法识别的认证信息"}`，说明这两个域名在线、鉴权层行为一致。
- 国际版 People 域名：⚠ 文档未说明。
- **一律用 `https://`。** ATS 文档写「所有的请求都必须通过HTTPS发送」，但文档里 `move_application_stage`、`offer/status` 等示例写的是 `http://`，不要照抄。
  无凭证探测（2026-09-11，#A7）：`http://api.mokahr.com/api-platform/v1/job_priority` **不会 301 跳转**，直接返回鉴权错误——
  也就是说写成 http 不会被重定向"纠正"，凭据会以明文发出。

## 3. ATS：HTTP Basic Auth（API Key）

**用途**：调用 ATS 全部接口的默认方式。API Key 作为 Basic Auth 的 **username**，**password 留空**。

| 项 | 值 |
| :--- | :--- |
| Header | `Authorization: Basic <base64("<API_KEY>:")>`（注意末尾冒号） |
| curl | `-u "$MOKA_API_KEY:"`（文档原文：「由于password为空，username后面的冒号`:`是必要的」） |
| Python requests | `auth=(os.environ["MOKA_API_KEY"], "")` |
| 权限 | 文档原文：「API Key有访问所有API的权限」，重置找 CSM |

**示例请求**

```bash
curl -s "https://api.mokahr.com/api-platform/v1/archiveReasons" -u "$MOKA_API_KEY:"
```

```python
import os, requests

s = requests.Session()
s.auth = (os.environ["MOKA_API_KEY"], "")      # 等价于 Basic base64("KEY:")
r = s.get("https://api.mokahr.com/api-platform/v1/archiveReasons", timeout=15)
print(r.status_code, r.text[:200])
```

**注意事项**

- ⚠ 文档自相矛盾：正文要求 `base64("username:password")`（即 `KEY:`），但同页 JavaScript 示例写的是 `Buffer.from(apiKey).toString('base64')`，**没有冒号**。
  People 文档也明确「Basic Base64.encode(apiKey:) 冒号不可缺失」。按带冒号实现；不带冒号是否也能过，待真实 Key 验证（见 verification-plan）。
- 手工拼 header 时用 `base64.b64encode(f"{key}:".encode()).decode()`，别对 `key` 本身编码。

## 4. ATS：OAuth2 client_credentials（accessToken）

### 获取 accessToken
**Endpoint**: `POST https://api.mokahr.com/api-platform/v1/auth/oauth2/getToken`
**用途**：用 `clientID` + `clientSecret` 换 2 小时有效的 `accessToken`，之后以 `Authorization: Bearer <accessToken>` 调业务接口。
文档原文：「如果您需要和 Moka 开放平台对接获取隐私数据（如申请、职位信息等）……您需要取得授权」。

**关键参数（JSON body）**

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `clientID` | String | 是 | 应用唯一标识，找 CSM。**注意是大写 `ID`** |
| `clientSecret` | String | 是 | 应用密钥，找 CSM |
| `grantType` | String | 是 | 固定 `client_credentials`（字段名是驼峰 `grantType`，不是 OAuth 标准的 `grant_type`） |

**示例请求**

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/v1/auth/oauth2/getToken" \
  -H "Content-Type: application/json" \
  -d "{\"clientID\":\"$MOKA_CLIENT_ID\",\"clientSecret\":\"$MOKA_CLIENT_SECRET\",\"grantType\":\"client_credentials\"}"
```

```python
import os, time, requests

_token = {"value": None, "exp": 0.0}

def moka_access_token() -> str:
    """缓存 accessToken；剩余不足 30 分钟时再去换（此时文档说新旧 token 同时有效）。"""
    if _token["value"] and time.time() < _token["exp"] - 1800:
        return _token["value"]
    r = requests.post(
        "https://api.mokahr.com/api-platform/v1/auth/oauth2/getToken",
        json={"clientID": os.environ["MOKA_CLIENT_ID"],
              "clientSecret": os.environ["MOKA_CLIENT_SECRET"],
              "grantType": "client_credentials"},
        timeout=15,
    )
    body = r.json()
    if body.get("code") != 0:            # 失败时 HTTP 仍是 200，必须判 body.code
        raise RuntimeError(f"getToken failed: {body}")
    _token["value"] = body["data"]["accessToken"]
    _token["exp"] = time.time() + int(body["data"]["expiresIn"])   # 秒
    return _token["value"]

r = requests.put("https://api.mokahr.com/api-platform/v2/departments",
                 headers={"Authorization": f"Bearer {moka_access_token()}"},
                 json={"departments": []}, timeout=30)
```

**示例响应**（文档原文）

```json
{"code": 0, "msg": "成功", "data": {"accessToken": "a-685ca366-…", "expiresIn": 6824, "tokenType": "Bearer"}}
```

**注意事项**

- 有效期 2 小时。文档原文：剩余有效期 ≥ 30 分钟时再调用返回**老** token；< 30 分钟时返回**新** token，此时新老 token 都有效。
  所以不必抢在过期前一秒刷新，按上面「剩余 < 30 分钟再换」即可。
- 错误码（文档原文）：`110020 unauthorized_client`（clientID 或 clientSecret 无效）。
- 无凭证探测（2026-09-11，#A4）：伪造 `clientID=test` → **HTTP 200** + `{"code":110020,"msg":"unauthorized_client","data":{}}`。**失败不体现在 HTTP 状态码上**，必须判 `code`。
- 无凭证探测（#A5）：把字段写成小写 `clientId` 同样返回 110020，**无法据此判断字段名是否大小写敏感**——照文档用 `clientID`。
- 哪些接口必须用 OAuth2、哪些用 Basic 就行：⚠ 文档未说明。文档里唯一的 Bearer 示例是 `PUT /api-platform/v2/departments`；其余接口示例都用 `-u 'your_api_key:'`。
  无凭证探测（#A3）：伪造 Bearer 调 `GET /v1/locations` 返回与伪造 Basic 相同的鉴权错误，看不出 Bearer 在该接口是否被接受。
  没有 OAuth2 凭证时先用 API Key；拿到两种凭证后按 verification-plan P0 逐一对照。

## 5. ATS：orgId 与招聘模式这两个"隐形必填"

- **orgId**：租户标识（文档描述不一：「每个公司客户对应的唯一id」「MOKA租户orgId，由客户负责人提供」「租户ID」）。
  出现在路径里（招聘官网 `GET /v1/jobs/{orgId}`、`POST /v1/jobs/{orgId}/{jobId}/apply`）或 body 里（`POST /v1/interview/create`、`/v3/getInterviewInfos`、`/v3/getOfferInfos` 等）。
  API Key 本身已经确定了租户，但这些接口仍要显式传 `orgId`。没有 orgId 就先问用户 / CSM，不要编。
- **招聘模式**：大多数接口用 `currentHireMode` / `hireMode` 整数 `1`=社招、`2`=校招；**但 `POST /v1/jobs/getJobs` 的 `hireMode` 是字符串 `social` / `campus`**（见 `jobs.md`）。

## 6. People：Basic Auth + query 签名（MD5withRSA）

People 每个请求 = **Basic 头** + **query 里的一组签名参数** + JSON body。body 不参与签名。

### 6.1 每个请求都要带的 query 参数

| 参数 | 必填 | 说明（文档原文整理） |
| :--- | :--- | :--- |
| `entCode` | 是 | 租户唯一 ID，CSM 提供 |
| `apiCode` | 是 | People「设置 - 对外接口设置」里某个接口的**接口编码**。**每个能力要建一个接口、各有各的 apiCode**：例如读员工要数据源=【员工任职信息】的 apiCode，读部门要【批量-组织架构信息】，新增员工要【新增员工接口】 |
| `nonce` | 是 | 随机串，数字 + 字母；**5 分钟内不能重复**。长度：⚠ 文档自相矛盾——「API鉴权认证」一节写「不超过10位」，每个接口的参数表写「不超过8位」→ 取 ≤ 8 位 |
| `timestamp` | 是 | **毫秒**时间戳，与服务器时间相差不能超过 3 分钟 |
| `sign` | 是 | 见 6.2 |
| `userName` | 部分接口必填 | 租户下某员工的邮箱，**决定返回数据的权限范围**（文档推荐用超级管理员）。读员工任职、字段元数据等接口要；新增 / 更新 / 离职员工等写接口的参数表里没有它 |

Header：`Authorization: Basic base64("<apiKey>:")`，文档原文「冒号不可缺失」。

### 6.2 sign 生成规则

1. 取 query 里**除 `sign` 以外的全部参数**，按参数名**字典序**排序，拼成 `k1=v1&k2=v2…`（值不做 URL 编码）。
   文档示例：`apiCode=0001&entCode=1&nonce=999&timestamp=1565244098737` / 带 `userName` 时 `…&timestamp=1565244098737&userName=xiao@qq.com`
2. 对该字符串做 **MD5withRSA**（RSA PKCS#1 v1.5 + MD5）签名，结果 Base64。
3. 把 Base64 串放进 query 的 `sign`，**发送前必须 URL 编码**（含 `+`、`/`、`=`）。文档原文提醒：RestTemplate 会自动解码导致验签失败，建议用 okhttp / httpclient。

本地复算（2026-09-11，无网络）：用 People 文档 Java 示例 `RSATester` 里给出的测试密钥对，下方 `people_sign()` 对文档示例串
`apiCode=00001&entCode=1&nonce=9999999&timestamp=1565244098737&userName=361@qq.com` 的签名结果与 `openssl dgst -md5 -sign` **逐字节一致**，
并能用文档给的公钥验签通过（复算脚本见 probe-log.md「本地复算」）。**这只证明算法实现正确，不证明服务端接受**。

RSA 私钥由谁生成、公钥在哪里登记：⚠ 文档未说明（文档只放了一对测试密钥和"私钥签名、公钥验签"的示例）。拿不到私钥时找 CSM，别用文档里的测试私钥。

### 6.3 Python 最小实现

```python
import base64, os, secrets, string, time
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

PEOPLE_BASE = "https://api.mokahr.com/api-platform/hcm/oapi"

def load_private_key(key_text: str):
    key_text = key_text.strip()
    if key_text.startswith("-----BEGIN"):
        return serialization.load_pem_private_key(key_text.encode(), password=None)
    return serialization.load_der_private_key(base64.b64decode(key_text), password=None)  # 裸 Base64 的 PKCS#8

def people_sign(query: dict, private_key) -> str:
    plain = "&".join(f"{k}={query[k]}" for k in sorted(query) if k != "sign")
    sig = private_key.sign(plain.encode("utf-8"), padding.PKCS1v15(), hashes.MD5())  # MD5withRSA
    return base64.b64encode(sig).decode()

_PRIV = load_private_key(os.environ["MOKA_PEOPLE_PRIVATE_KEY"])

def people_post(path: str, body: dict, api_code: str, user_name: str | None = None) -> dict:
    query = {
        "entCode": os.environ["MOKA_PEOPLE_ENT_CODE"],
        "apiCode": api_code,                               # 每个接口各自的 apiCode
        "nonce": "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8)),
        "timestamp": str(int(time.time() * 1000)),          # 毫秒
    }
    if user_name:
        query["userName"] = user_name
    query["sign"] = people_sign(query, _PRIV)
    r = requests.post(PEOPLE_BASE + path, params=query,     # requests 会对 sign 做一次 URL 编码
                      auth=(os.environ["MOKA_PEOPLE_API_KEY"], ""),
                      json=body, timeout=30)
    data = r.json()
    if str(data.get("code")) not in ("200", "0"):
        raise RuntimeError(f"HTTP {r.status_code}: {data}")
    return data

# 例：读员工任职数据（数据源=员工任职信息 的 apiCode）
# people_post("/v1/batch/data", {"pageSize": 200, "pageNum": 1},
#             api_code=os.environ["MOKA_PEOPLE_APICODE_EMPLOYEE"],
#             user_name=os.environ["MOKA_PEOPLE_USER_NAME"])
```

对应的 curl（sign 需先用上面的函数算好，再 URL 编码）：

```bash
curl -s -X POST \
  "https://api.mokahr.com/api-platform/hcm/oapi/v1/batch/data?userName=$MOKA_PEOPLE_USER_NAME&entCode=$MOKA_PEOPLE_ENT_CODE&apiCode=$APICODE&nonce=ab12cd34&timestamp=$TS&sign=$SIGN_URLENCODED" \
  -u "$MOKA_PEOPLE_API_KEY:" -H "Content-Type: application/json" \
  -d '{"pageSize":200,"pageNum":1}'
```

**注意事项**

- 签名只覆盖 query；改了 query 里任何值（包括 `userName`）都要重算。
- 同一 `nonce` 5 分钟内复用会被判非法（文档原文），重试时要换 nonce、重算 sign。
- Java 示例用 `String.compareTo` 排序；参数名全是 ASCII，Python `sorted()` 结果相同。

## 7. 鉴权失败时长什么样（无凭证探测）

全部为无凭证探测（2026-09-11），每条复跑两次结果一致；完整命令见 probe-log.md。

| 场景 | 请求 | HTTP | 响应 body |
| :--- | :--- | :--- | :--- |
| ATS 不带任何鉴权 | `GET /api-platform/v1/archiveReasons`（#A1） | **500** | `{"code":-1,"success":false,"msg":"无法识别的认证信息"}` |
| ATS 伪造 Basic Key | `GET /api-platform/v1/departments`（#A2）等 | **500** | 同上 |
| ATS 伪造 Basic Key（部分 v3 / 公共接口） | `POST /api-platform/v3/applications/list_by_condition`（#B5）、`/v1/jobs/getJobs`（#B6）、`/v1/public/switchStatus`（#B3） | **500** | `{"code":-1,"success":false,"msg":"系统中不存在该apiKey"}` |
| ATS 伪造 Bearer | `GET /api-platform/v1/locations`（#A3） | **500** | `{"code":-1,"success":false,"msg":"无法识别的认证信息"}` |
| ATS `/open-api` 网关 | `POST /open-api/ats/v3/users/list`（#A10） | **401** | `{"code":-1,"msg":"无法识别的认证信息","subCode":"Unauthorized"}` |
| ATS 不存在的路径（带伪造 Key） | `GET /api-platform/v1/this_path_does_not_exist`（#A6） | **404** | `{"message":"您访问的页面不存在"}` |
| ATS OAuth2 伪造 clientID | `POST /api-platform/v1/auth/oauth2/getToken`（#A4） | **200** | `{"code":110020,"msg":"unauthorized_client","data":{}}` |
| People 不带鉴权 / 伪造 Key / 伪造签名 | `POST /hcm/oapi/v1/batch/data`（#P1、#P2）、`/v1/org/department/batchData`（#P3） | **403** | `{"success":false,"msg":"无法识别的认证信息"}` |
| People 不存在的路径 | `POST /hcm/oapi/v1/this_path_does_not_exist`（#P5） | **403** | 同上（People 先鉴权后路由） |

由此得到的写代码规则：

- **ATS 鉴权失败是 HTTP 500，不是 401**。重试逻辑若把 5xx 当"服务端临时故障"去重试，会对错误的 Key 无限重试——先判 body 的 `msg` / `code`。
- ATS 路由在鉴权之前：带伪造 Key 请求时，**404 表示路径写错，500 + 鉴权错误表示路径存在**。本 skill 用这个特性确认了若干文档路径（见各 reference 与 probe-log）。
- People 对一切未授权请求都回 403，无法用同样办法区分路径。
<!-- Gap: People 文档「全局错误码」写鉴权失败为 HTTP 401 / 错误码 100001「没有进入系统权限，请检查授权码是否准确」；无凭证探测（2026-09-11，#P1–#P3，各复跑两次）伪造 Key / 伪造签名实际返回 HTTP 403，body 为 {"success":false,"msg":"无法识别的认证信息"}，没有 code 字段。 -->
- People 文档把鉴权失败写成 HTTP 401 + `code: 100001`；**无凭证探测到的是 HTTP 403 且 body 没有 `code` 字段**。错误处理不要只写 `if body["code"] == 100001`。

## 8. 环境变量约定与最小客户端

| 变量 | 用于 |
| :--- | :--- |
| `MOKA_API_KEY` | ATS Basic Auth |
| `MOKA_CLIENT_ID` / `MOKA_CLIENT_SECRET` | ATS OAuth2 |
| `MOKA_ORG_ID` | ATS 需要 orgId 的接口 |
| `MOKA_BASE`（可选） | 国际版改成 `https://hire-r1-api.mokahr.com` |
| `MOKA_PEOPLE_API_KEY` | People Basic Auth |
| `MOKA_PEOPLE_ENT_CODE` | People `entCode` |
| `MOKA_PEOPLE_PRIVATE_KEY` | People 签名私钥（PEM 或裸 Base64 PKCS#8） |
| `MOKA_PEOPLE_USER_NAME` | People 读接口的 `userName` |
| `MOKA_PEOPLE_APICODE_<能力>` | 每个 People 接口各自的 apiCode |

ATS 最小客户端：

```python
import os, requests

ATS = os.environ.get("MOKA_BASE", "https://api.mokahr.com") + "/api-platform"
ats = requests.Session()
ats.auth = (os.environ["MOKA_API_KEY"], "")

def ats_call(method: str, path: str, **kw):
    """path 从 /v1/… /v2/… /v3/… 或 /candidate/… 开始，照文档完整 URL 去掉前缀 /api-platform。"""
    r = ats.request(method, ATS + path, timeout=30, **kw)
    try:
        body = r.json()
    except ValueError:
        r.raise_for_status(); raise
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {body}")   # 鉴权错误是 500，别当成可重试
    return body   # 各接口成功判定不同，由调用方按 reference 判 success / code
```

## 9. ⚠ 本文件的未说明 / 矛盾之处

- ⚠ 文档自相矛盾：ATS Basic Auth 的 JS 示例对 `apiKey` 编码时没有 `:`，正文和 People 文档都要求 `apiKey:`。
- ⚠ 文档未说明：ATS 哪些接口必须用 OAuth2 accessToken、哪些接受 API Key。
- ⚠ 文档未说明：ATS 与 People 的 apiKey 是否同一个；People 测试环境与国际版域名。
- ⚠ 文档自相矛盾：People `nonce` 长度（≤10 位 vs ≤8 位）。
- ⚠ 文档未说明：People RSA 密钥对由谁生成、公钥在哪登记。
- ⚠ 文档未说明：OAuth2 字段名 `clientID` 是否大小写敏感（探测 #A5 无法区分）。
