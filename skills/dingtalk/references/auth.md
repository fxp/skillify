# 鉴权与 access token（新旧两套 API）

来源：open.dingtalk.com/document 下「获取企业内部应用的access_token / accessToken」「获取应用的 Access Token」
「获取用户token」「获取登录用户的访问凭证」「通过免登码获取用户信息」「获取第三方应用授权企业的accessToken」
「获取第三方企业应用的suiteAccessToken」「服务商获取第三方应用授权企业的access_token」「第三方访问接口的签名计算方法」
「新旧版规范服务端API区别」「基础概念」（抓取于 2026-09-11）。
**除标「无凭证探测」的条目外，行为描述均为文档原文，未实测。**

## 目录

1. [先分清两套服务端 API](#1-先分清两套服务端-api)
2. [企业内部应用：拿应用 token](#2-企业内部应用拿应用-token)
3. [统一版 token 接口（内部 + 第三方）](#3-统一版-token-接口内部--第三方)
4. [用户身份：OAuth 登录 → 用户 token](#4-用户身份oauth-登录--用户-token)
5. [免登：前端 authCode → 后端 userid](#5-免登前端-authcode--后端-userid)
6. [第三方企业应用（ISV）的 token](#6-第三方企业应用isv的-token)
7. [ID 体系：别把 userid / unionid / corpId 混用](#7-id-体系别把-userid--unionid--corpid-混用)
8. [官方 SDK](#8-官方-sdk)
9. [⚠ 本文件的未说明 / 矛盾之处](#9--本文件的未说明--矛盾之处)

---

## 1. 先分清两套服务端 API

钉钉同时维护两套服务端 API，产品能力不完全重叠（文档原文："新版服务端API未包含全部的服务端API的产品能力"），
旧版"不再开放新能力"但"接口不会下线"。**一个项目里两套并用是常态**（例如工作通知、考勤、大部分通讯录只有旧版；
机器人、互动卡片、审批新接口在新版）。

| | 旧版 | 新版 |
| --- | --- | --- |
| Host | `https://oapi.dingtalk.com` | `https://api.dingtalk.com` |
| 路径形态 | `/gettoken`、`/topapi/...`、`/attendance/...`、`/robot/send` | `/v1.0/<产品>/...` |
| token 放哪 | **query 参数 `?access_token=`** | **header `x-acs-dingtalk-access-token`** |
| 字段风格 | snake_case（`userid_list`、`agent_id`） | camelCase（`userIds`、`robotCode`） |
| 成功判定 | HTTP 200 且 `errcode == 0` | HTTP 2xx，body 里没有 `errcode` |
| SDK | 旧版 SDK（`import dingtalk.api`） | `alibabacloud_dingtalk`（见第 8 节） |

文档原文："新旧两个版本的 SDK 不可混用。"

**无凭证探测（2026-09-11）——token 放错位置的真实表现**（详见 `errors-and-limits.md`）：

| 请求 | 返回 |
| --- | --- |
| 新版 `GET /v1.0/contact/users/test`，header `x-acs-dingtalk-access-token: test` | HTTP 400 `{"code":"InvalidAuthentication","message":"不合法的access_token"}` |
| 同一接口改用 `?access_token=test` | HTTP 400 `{"code":"AuthenticationFailed.MissingParameter","message":"缺少参数：x-acs-dingtalk-access-token"}` |
| 同一接口改用 `Authorization: Bearer test` | 同上，`缺少参数：x-acs-dingtalk-access-token` |
| 旧版 `POST /topapi/v2/user/get?access_token=test` | HTTP 200 `{"errcode":88,"sub_code":"40014","sub_msg":"不合法的access_token"}` |
| 旧版同一接口只放 header `x-acs-dingtalk-access-token` | HTTP 200 `{"errcode":88,"sub_code":"40000","sub_msg":"access_token is blank"}` |
| 旧版同一接口把 `access_token=test` 放进表单 body（照文档 curl） | HTTP 200 `errcode 88 / sub_code 40014`（说明 POST 表单 body 里的 token 也会被读取） |

结论：**新版只认那个 header，不认 Bearer、不认 query；旧版只认 access_token 参数，不认 header。**

---

## 2. 企业内部应用：拿应用 token

### 获取企业内部应用的 accessToken（新版，推荐）

**Endpoint**: `POST https://api.dingtalk.com/v1.0/oauth2/accessToken`
**用途**: 用应用的 Client ID / Client Secret（即旧称 AppKey / AppSecret）换应用级 token，调新版接口放 header，调旧版接口放 query。

**关键参数**（JSON body）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| appKey | String | 是 | 企业内部应用的 Client ID |
| appSecret | String | 是 | 企业内部应用的 Client Secret |

**示例请求**

```bash
curl -X POST https://api.dingtalk.com/v1.0/oauth2/accessToken \
  -H 'Content-Type: application/json' \
  -d "{\"appKey\":\"$DINGTALK_APP_KEY\",\"appSecret\":\"$DINGTALK_APP_SECRET\"}"
```

```python
import os, time, requests

_cache: dict = {}

def get_app_token() -> str:
    """企业内部应用 token，按应用缓存，提前 5 分钟刷新。"""
    key = os.environ["DINGTALK_APP_KEY"]
    hit = _cache.get(key)
    if hit and hit["exp"] - 300 > time.time():
        return hit["token"]
    r = requests.post(
        "https://api.dingtalk.com/v1.0/oauth2/accessToken",
        json={"appKey": key, "appSecret": os.environ["DINGTALK_APP_SECRET"]},
        timeout=10,
    )
    if r.status_code != 200:            # 新版失败走 HTTP 4xx/5xx + {"code","message","requestid"}
        raise RuntimeError(f"gettoken failed {r.status_code}: {r.text}")
    data = r.json()
    _cache[key] = {"token": data["accessToken"], "exp": time.time() + data["expireIn"]}
    return data["accessToken"]
```

**示例响应**

```json
{"accessToken": "fw8ef8we8f76e6f7s8dxxxx", "expireIn": 7200}
```

**注意事项**

- 有效期 7200 秒；有效期内重复获取返回同一个值并自动续期（文档原文）。文档要求自行缓存、按应用区分存储、不要频繁调用，否则被限流。
- 文档列的错误：`400 invalidClientIdOrSecret`。**无凭证探测（2026-09-11）**：伪造 `appKey=test` 返回
  HTTP 400 `{"requestid":"...","code":"invalidClientIdOrSecret","message":"无效的clientId或者clientSecret"}`，与文档一致。
- 响应字段是 `accessToken` / `expireIn`（camelCase），和旧版 `access_token` / `expires_in` 不同，别用同一个解析函数。

### 获取企业内部应用的 access_token（旧版）

**Endpoint**: `GET https://oapi.dingtalk.com/gettoken?appkey=...&appsecret=...`
**用途**: 旧版等价接口。文档标注"已完成升级，后续将维持现有功能且不再新增能力"，未接入的建议用新版。

**关键参数**（query）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| appkey | String | 是 | Client ID |
| appsecret | String | 是 | Client Secret |

**示例请求**

```bash
curl "https://oapi.dingtalk.com/gettoken?appkey=$DINGTALK_APP_KEY&appsecret=$DINGTALK_APP_SECRET"
```

```python
r = requests.get("https://oapi.dingtalk.com/gettoken",
                 params={"appkey": os.environ["DINGTALK_APP_KEY"],
                         "appsecret": os.environ["DINGTALK_APP_SECRET"]}, timeout=10)
data = r.json()
if data.get("errcode") != 0:            # 旧版失败也是 HTTP 200
    raise RuntimeError(data)
token = data["access_token"]            # 7200 秒
```

**示例响应**

```json
{"errcode": 0, "access_token": "96fc7a7axxx", "errmsg": "ok", "expires_in": 7200}
```

**注意事项**

<!-- Gap: 文档 curl 示例用 -X GET 加 -d 表单 body 传 appkey/appsecret（还多传了 access_token），实测 body 不被读取，返回 40035 缺少参数 -->
- **文档的 curl 示例是错的。** 示例写 `curl -X GET ... -d 'appkey=appkey' -d 'appsecret=appsecret'`（还额外传了一个 `access_token`）。
  **无凭证探测（2026-09-11）**：照抄该写法返回 `{"errcode":40035,"errmsg":"缺少参数 corpid or appkey"}`；
  改用 query string 则进入凭证校验，返回 `{"errcode":40096,"errmsg":"不合法的appKey或appSecret"}`。**一律用 query string。**
- `40096` 不在「全局错误码」表里（表里只有 `40089 不合法的corpId或corpSecret`）⚠ 文档未说明。
- 文档的 Python 示例是旧版 SDK 的 Python 2 写法（`except Exception,e:`），Python 3 直接语法错误 ⚠。

---

## 3. 统一版 token 接口（内部 + 第三方）

### 获取应用的 Access Token

**Endpoint**: `POST https://api.dingtalk.com/v1.0/oauth2/{corpId}/token`
**用途**: 文档称"企业内部应用和第三方企业应用两种场景统一为一个接口"。与第 2 节的区别：路径里要带组织 corpId，字段是 OAuth 风格 snake_case。

**关键参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| corpId | path | String | 是 | 应用运行在哪个组织就填哪个：内部应用填本企业 corpId；三方应用填授权企业 corpId |
| client_id | body | String | 是 | 应用 Client ID |
| client_secret | body | String | 是 | 应用 Client Secret |
| grant_type | body | String | 是 | 固定 `client_credentials` |

```bash
curl -X POST "https://api.dingtalk.com/v1.0/oauth2/$DINGTALK_CORP_ID/token" \
  -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$DINGTALK_APP_KEY\",\"client_secret\":\"$DINGTALK_APP_SECRET\",\"grant_type\":\"client_credentials\"}"
```

**示例响应**：`{"access_token": "2bf******9be361a5084f1e2b8", "expires_in": 7200}` —— 注意这里又是 snake_case。

**注意事项**

- 文档列的错误：`400 invalid.client`、`400 unsupported.grant.type`、`401 unauthorized.client`、`500 server.error`（文档原文，未实测）。
- **无凭证探测（2026-09-11）**：用伪造 corpId `dingtest` + 伪造 client_id 调用，返回 HTTP 500
  `{"code":"unknownError","message":"未知错误"}`，而不是文档的 `400 invalid.client`。corpId 不合法时报错不具诊断性 ⚠，
  排障时先确认 corpId（开发者后台首页可见）。

---

## 4. 用户身份：OAuth 登录 → 用户 token

用于"以登录用户身份"调用接口（例如 `GET /v1.0/contact/users/me`）。应用 token 调这类接口不行。

### 第一步：拼授权页 URL

```
https://login.dingtalk.com/oauth2/auth?redirect_uri=<urlencode 后的回调地址>
  &response_type=code&client_id=<AppKey 或 SuiteKey>&scope=openid&state=<随机串>&prompt=consent
```

| 参数 | 必填 | 说明（文档原文摘要） |
| --- | --- | --- |
| redirect_uri | 是 | 须与开发者后台「安全设置」登记的重定向 URL 一致；值要 urlencode |
| response_type | 是 | 固定 `code` |
| client_id | 是 | 内部应用 AppKey；三方企业应用 SuiteKey |
| scope | 是 | 只支持 `openid` 或 `openid corpid`（空格分隔，需 url 编码） |
| prompt | 是 | `consent` 进入授权确认页 |
| state | 否 | 原样带回 |

**授权成功后回跳的参数名是 `authCode`，不是 OAuth 惯例的 `code`**：
`https://www.aaaaa.com/a/b?authCode=xxxx&state=dddd`；失败时 `?error=yyyyyy&state=dddd`（文档原文）。

### 第二步：获取用户 token

**Endpoint**: `POST https://api.dingtalk.com/v1.0/oauth2/userAccessToken`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| clientId | String | 是 | 内部应用 AppKey / 三方企业应用 SuiteKey / 三方个人应用 AppId |
| clientSecret | String | 是 | 对应的 Secret |
| grantType | String | 是 | `authorization_code`（配 `code`）或 `refresh_token`（配 `refreshToken`） |
| code | String | 否 | 上一步拿到的 authCode |
| refreshToken | String | 否 | 上次返回的 refreshToken，有效期 30 天 |

```python
def user_token_from_code(auth_code: str) -> dict:
    r = requests.post("https://api.dingtalk.com/v1.0/oauth2/userAccessToken", json={
        "clientId": os.environ["DINGTALK_APP_KEY"],
        "clientSecret": os.environ["DINGTALK_APP_SECRET"],
        "code": auth_code,
        "grantType": "authorization_code",
    }, timeout=10)
    r.raise_for_status()
    return r.json()   # {"accessToken","refreshToken","expireIn":7200,"corpId"}

def whoami(user_token: str) -> dict:
    r = requests.get("https://api.dingtalk.com/v1.0/contact/users/me",
                     headers={"x-acs-dingtalk-access-token": user_token}, timeout=10)
    r.raise_for_status()
    return r.json()   # nick / unionId / openId / mobile(需权限) / email / stateCode
```

**注意事项**

- `GET /v1.0/contact/users/{unionId}` 要的是**用户 token**（文档原文："需要先获取个人用户的accessToken"），`unionId` 传 `me` 取当前授权人。
  返回的是 **unionId，不含 userid**；要 userid 需再用应用 token 调 `topapi/user/getbyunionid`（见 `contacts.md`）。
- 请求体字段是 camelCase（`grantType`），和第 3 节的 `grant_type` 不同。

---

## 5. 免登：前端 authCode → 后端 userid

H5 微应用 / 小程序在钉钉客户端内打开时，前端用 JSAPI `requestAuthCode`（微应用）或 `getAuthCode`（小程序）拿免登码，
后端用**应用 token**换 userid。

### 通过免登码获取用户信息

**Endpoint**: `POST https://oapi.dingtalk.com/topapi/v2/user/getuserinfo?access_token=<应用token>`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| code | String | 是 | 免登授权码，**5 分钟内有效且只能用一次** |

```python
r = requests.post("https://oapi.dingtalk.com/topapi/v2/user/getuserinfo",
                  params={"access_token": get_app_token()}, json={"code": code}, timeout=10)
d = r.json()
if d["errcode"] != 0:
    raise RuntimeError(d)
userid, unionid = d["result"]["userid"], d["result"]["unionid"]
```

**示例响应**

```json
{"errcode": 0, "errmsg": "ok",
 "result": {"userid": "userid123", "unionid": "gliiW0piiii02zBUjUxxxx", "associated_unionid": "N2o5U3axxxx",
            "device_id": "12drtfxxxxx", "sys": true, "sys_level": 1, "name": "张xx"}}
```

`sys_level`：1 主管理员、2 子管理员、100 老板、0 其他（文档原文）。
旧接口 `GET /user/getuserinfo` 文档标"不推荐"。免登码无效时全局错误码为 `40078 不存在的临时授权码`（文档原文，未实测）。

---

## 6. 第三方企业应用（ISV）的 token

ISV 场景比内部应用多一个 **suite_ticket**：钉钉约每 5 小时向应用回调推送一次（文档原文），必须持久化、不要设失效缓存，
新 ticket 会使旧的失效；没回 success 会连续重推，超过 100 次停止（见 `events.md`）。

| 目的 | Endpoint | body |
| --- | --- | --- |
| 应用自身的 suiteAccessToken | `POST https://api.dingtalk.com/v1.0/oauth2/suiteAccessToken` | `suiteKey`、`suiteSecret`、`suiteTicket` |
| 授权企业的 accessToken（新版） | `POST https://api.dingtalk.com/v1.0/oauth2/corpAccessToken` | `suiteKey`、`suiteSecret`、`authCorpId`、`suiteTicket` |
| 授权企业的 access_token（旧版） | `POST https://oapi.dingtalk.com/service/get_corp_token` | 见下方签名 |

<!-- Gap: 「获取第三方应用授权企业的accessToken」参数表写 HTTP URL 为 https://api.dingtalk.com/oauth2/corpAccessToken（无 /v1.0），无凭证探测返回 HTTP 200 + errcode 404「请求的URI地址不存在」；请求示例里的 /v1.0/oauth2/corpAccessToken 才存在 -->
**corpAccessToken 的文档 URL 写错了。** 参数表写 `https://api.dingtalk.com/oauth2/corpAccessToken`，请求示例写 `POST /v1.0/oauth2/corpAccessToken`。
**无凭证探测（2026-09-11）**：无 `/v1.0` 的路径返回 `{"errcode":404,"errmsg":"请求的URI地址不存在"}`；
带 `/v1.0` 的路径返回 HTTP 400 `{"code":"invalidSuiteKey","message":"suitekey不合法"}`（路径存在、进入参数校验）。**用 `/v1.0/oauth2/corpAccessToken`。**

其他注意：
- 该接口参数表只列了 `suiteKey/suiteSecret/authCorpId`，请求示例里却还有 `suiteTicket` 和一个 `x-acs-dingtalk-access-token` header ⚠ 文档自相矛盾。
  错误码表里有 `invalidSuiteTicket`，推测 suiteTicket 是需要的，未验证。
- 三方授权企业 token：文档称"有效期内重复获取会返回新的"（和内部应用"返回相同值"不同）。
- 旧版 `service/get_corp_token` 走 HTTP 时必须签名：
  `signature = urlencode(Base64(HmacSHA256(key=suiteSecret, msg=timestamp + "\n" + suiteTicket)))`，
  `timestamp` 为毫秒；`accessKey`、`timestamp`、`suiteTicket`、`signature` 放 query，`auth_corpid` 放 body（文档 curl 示例原文如此）。
  URL 编码要把 `+` 编成 `%20`、`*` 编成 `%2A`（文档原文）。定制应用的 suiteTicket "可随意填写"。

```python
import base64, hashlib, hmac, time, urllib.parse
def isv_signature(suite_secret: str, suite_ticket: str) -> tuple[str, str]:
    ts = str(int(time.time() * 1000))
    raw = hmac.new(suite_secret.encode(), f"{ts}\n{suite_ticket}".encode(), hashlib.sha256).digest()
    return ts, urllib.parse.quote(base64.b64encode(raw).decode(), safe="")
```

---

## 7. ID 体系：别把 userid / unionid / corpId 混用

| ID | 含义（文档原文摘要） | 常见出处 | 谁要它 |
| --- | --- | --- | --- |
| corpId | 企业组织唯一标识 | 开发者后台首页；以 `ding` 开头 | 统一 token 接口路径、ISV `authCorpId` |
| userid（也叫 userId / staffId） | 企业内员工唯一标识，不可更改 | 通讯录接口、免登 | 工作通知、审批、考勤、机器人单聊 `userIds` |
| unionid（unionId） | 同一开放平台账号（开发者企业账号）下所有应用相同；**不同开发者账号下不同** | `topapi/v2/user/get` 返回、用户 token 接口 | `/v1.0/contact/users/{unionId}`、卡片 `userIdType=2` |
| AgentId | 企业内部应用的能力标识 | 开发者后台应用详情 | 工作通知 `agent_id`、审批 `microappAgentId` |
| robotCode | 机器人编码 | 机器人配置页 / 收消息回调 | 企业机器人发消息 |
| openConversationId | 群会话 ID（`cid` 开头） | 建群返回、JSAPI chooseChat、机器人收消息的 `conversationId` | 机器人群消息、互动卡片 |
| processCode | 审批模板唯一码（`PROC-` 开头） | 审批模板编辑页 URL | 审批相关接口 |

- 机器人收到的消息里 `senderId`、`chatbotUserId`、`msgId` 是**加密 ID**，不是 userid；userid 在 `senderStaffId`，
  且"机器人发布上线后生效，否则不会返回"（文档原文）。
- 错误码里的 `staffId` 就是 userid（如 `invalidParameter.userId.empty 缺少staffId`）。
- 新版部分接口可用 unionId 代替 userId，但要看具体接口是否有 `userIdType` 之类的开关，不要默认互换。

---

## 8. 官方 SDK

新版服务端 SDK（文档「服务端SDK下载」原文）：Python `pip install alibabacloud_dingtalk`（Python 3），
Java Maven `dingtalk`、Go `github.com/alibabacloud-go/dingtalk/`、Node `@alicloud/dingtalk`、PHP `alibabacloud/dingtalk`、
C# `AlibabaCloud.SDK.Dingtalk`。旧版 SDK 固定 2.0.0。**新旧 SDK 不可混用。**

新版 Python SDK 取 token（文档示例原样精简）：

```python
from alibabacloud_dingtalk.oauth2_1_0.client import Client as OAuthClient
from alibabacloud_dingtalk.oauth2_1_0 import models as oauth_models
from alibabacloud_tea_openapi import models as open_api_models

config = open_api_models.Config()
config.protocol = "https"
config.region_id = "central"
client = OAuthClient(config)
resp = client.get_access_token(oauth_models.GetAccessTokenRequest(
    app_key=os.environ["DINGTALK_APP_KEY"], app_secret=os.environ["DINGTALK_APP_SECRET"]))
```

新版 SDK 调业务接口时 token 通过 `XxxHeaders().x_acs_dingtalk_access_token` 传入（各接口文档示例一致）。
SDK 返回对象如何取字段（如 `resp.body.access_token`）文档未说明 ⚠，本 skill 示例统一用 `requests` 直调 HTTP。

---

## 9. ⚠ 本文件的未说明 / 矛盾之处

- 同一应用的新版 accessToken 能否直接当旧版 access_token 用（反之亦然）：⚠ 文档未说明，无凭证无法验证。稳妥做法是各自按文档接口获取。
- 旧版 gettoken 伪造凭证返回 `40096`，全局错误码表未收录 ⚠ 文档未说明。
- 统一版 `/v1.0/oauth2/{corpId}/token` 对非法 corpId 返回 500 unknownError，与文档错误码表不符 ⚠（非法 corpId 情形文档未说明）。
- corpAccessToken 参数表缺 `suiteTicket`、示例多一个 header ⚠ 文档自相矛盾。
- 「基础概念」页的快速上手写 `GET https://oapi.dingtalk.com/topapi/v2/user/get?...&userid=...`，而该接口文档写 `HTTP Method POST` ⚠ 文档自相矛盾（本 skill 按 POST 写）。
