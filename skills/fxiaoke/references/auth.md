# 鉴权、公共参数与所在云域名

> 来源：https://developer.fxiaoke.com/openapi_v2/ 的「快速开始」「客户端凭证模式」「授权码模式」「刷新 accessToken」「应用免登」
> 「公共参数填写」「旧版传参方式说明」「所在云域名」页（抓取于 2026-09-11），以及旧版 wiki
> （https://open.fxiaoke.com/open/openindex/wiki.html ，artiId=17 / 19 / 169）。
> **除标「无凭证探测（2026-09-11）」的条目外，本文件里的报错与行为都是文档原文，未实测。**

## 目录
1. 开始前：拿到 appId / appSecret / permanentCode
2. Base URL：按企业所在云选域名
3. 两代传参方式：新版 header vs 旧版 body
4. 客户端凭证模式换 accessToken（服务端对接首选）
5. 旧版：换 corpAccessToken
6. 授权码模式（用户参与）与刷新 token
7. 应用免登：用 code 换 openUserId
8. thirdTraceId
9. x-fs-userid / currentOpenUserId 填谁
10. 可直接复用的 Python 客户端
11. 本文件的 ⚠

---

## 1. 开始前：拿到 appId / appSecret / permanentCode

新版文档只描述了「企业自建应用」这一种接入身份：

1. 登录纷享销客网页版 → 管理后台 → 应用列表 → 右上角「新建企业自建应用」。
   APP 端跳转地址 / WEB 端跳转地址至少填一个，没有就填 `https://www.fxiaoke.com`。
2. **开启开发模式**（不开无法使用 OpenAPI）：
   - 登录授权发起页域名：不含 `http://` / `https://` 前缀，授权码模式用它校验请求来源；没有就填 `www.fxiaoke.com`；
   - 允许访问的**白名单 IP**；
   - 服务号：用于企信发消息，没有可不填。
3. 确定后得到三件套：

| 参数 | 说明 | 示例形态 | 建议环境变量 |
| --- | --- | --- | --- |
| appId | 企业应用 ID | `FSAID_xxxxx` | `FXK_APP_ID` |
| appSecret | 企业应用凭证密钥 | — | `FXK_APP_SECRET` |
| permanentCode | 永久授权码 | — | `FXK_PERMANENT_CODE` |

4. 「CRM 接口查询权限设置」：默认全部接口可用，文档建议自行收窄访问区间。

凭证只放环境变量，不要写进代码或日志。

## 2. Base URL：按企业所在云选域名

接口地址里的 `${填入所在云的域名}` 要换成**企业所在云**的 OpenAPI 域名（「所在云域名」页）：

| 云 | OpenAPI 域名 |
| --- | --- |
| 纷享云（默认） | `open.fxiaoke.com` |
| 华为云 | `open-hwcloud.fxiaoke.com` |
| 阿里云 | `open-ale.fxiaoke.com` |
| 香港华为 | `open-ksc.sharecrm.com` |
| 法兰克福 | `open-hws.fxiaoke.com` |
| 北美云 | `open-na.sharecrm.com` |

规律：其他云 = `open-${当前云登录域名}`。不确定企业在哪个云时，先问用户登录纷享网页版用的是哪个域名。

- ⚠ 文档自相矛盾：旧版 wiki（artiId=169）把 `open-hws.fxiaoke.com` 标为「海外AWS」、`open-ale.fxiaoke.com` 标为「钉钉云」，
  与新版「法兰克福」「阿里云」的标签不同。域名本身一致，以企业实际登录域名为准。
- 无凭证探测（2026-09-11）：`open-hwcloud.fxiaoke.com/oauth2.0/token` 可达，伪造凭证返回与纷享云相同的 `errorCode 10006`。

<!-- Gap: 「公共参数填写」页的示例 URL 写的是 https://www.fxiaoke.com/cgi/crm/v2/data/get?thirdTraceId=… ；无凭证探测（2026-09-11）该地址返回 HTTP 302 → https://www.fxiaoke.com/messageform/website/html/home.html 的 HTML 页面，不是 OpenAPI 网关。OpenAPI 必须打 open.fxiaoke.com 或所在云的 open-* 域名。 -->
**不要用 `www.fxiaoke.com` 当 API 域名**——文档示例里出现过，但它不是 API 网关（见上方 Gap 注释）。

## 3. 两代传参方式：新版 header vs 旧版 body

「公共参数填写」页明确说新旧版本传参方式不同。**同一个请求里只用一种**。

| 项 | 新版（文档主推） | 旧版 |
| --- | --- | --- |
| 换 token | `POST /oauth2.0/token`（`grantType=app_secret`） | `POST /cgi/corpAccessToken/get/V2` |
| token 放哪 | header `authorization: Bearer <accessToken>`（Bearer 后一个空格） | body 顶层 `corpAccessToken` |
| 企业标识 | header `x-fs-ea: <ea>`（客户端凭证响应里的 `ea`） | body 顶层 `corpId`（`FSCID_…`） |
| 操作人 | header `x-fs-userid: <CRM 员工ID>`，如 `1000` | body 顶层 `currentOpenUserId`（`FSUID_…`） |
| 员工 ID 形态 | 默认直接用 CRM 员工 ID；要用 FSUID 就在 body 顶层加 `"convertUserId": true` | openUserId（`FSUID_…`） |
| 文件参数 | 默认用 npath；要用 mediaId 就在 body 顶层加 `"convertMediaId": true` | mediaId |
| 业务参数 | body 的 `data` 里 | body 的 `data` 里 |

新版平台公共参数（位于 JSON 最外层）：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| convertUserId | boolean | 否 | 是否转换用户 ID。文档原句：「默认为 `true`，新版参时默认为 `false`」 |
| convertMediaId | boolean | 否 | 是否转换媒体 ID。文档原句同上 |

- ⚠ 文档表述含混：「默认为 true，新版参时默认为 false」——理解为旧版传参默认 true、新版 header 传参默认 false。新版代码里想用 `FSUID_…` 或 mediaId 时显式传 `true`，否则不要传。
- 无凭证探测（2026-09-11）：新版 header（伪造 Bearer）和旧版 body（伪造 corpAccessToken）两种写法网关**都认**，
  都返回 `{"errorMessage":"the cropId,cropAccessToken or authorization is error","errorCode":20016}`。
  完全不带鉴权时返回 `{"errorMessage":"corpAccessToken为必填项，不能为空","errorCode":20017}`。

## 4. 客户端凭证模式换 accessToken（服务端对接首选）

**Endpoint**: `POST https://{host}/oauth2.0/token?thirdTraceId={uuid4}`
**用途**: 服务端之间授权，无用户参与；拿到的 token 可配合**任意员工 ID**（`x-fs-userid`）访问接口。和授权码模式共用同一个 URL，靠 `grantType` 区分。

**关键参数**（JSON body）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| appId | String | 是 | — | 自建应用 appId |
| appSecret | String | 是 | — | 自建应用 appSecret |
| permanentCode | String | 是 | — | 永久授权码 |
| grantType | String | 是 | — | 固定 `app_secret` |

**示例请求**

```bash
export FXK_HOST=open.fxiaoke.com   # 按所在云改
TOKEN_JSON=$(curl -sS -X POST "https://$FXK_HOST/oauth2.0/token?thirdTraceId=$(uuidgen | tr A-Z a-z)" \
  -H 'Content-Type: application/json' \
  -d "{\"appId\":\"$FXK_APP_ID\",\"appSecret\":\"$FXK_APP_SECRET\",\"permanentCode\":\"$FXK_PERMANENT_CODE\",\"grantType\":\"app_secret\"}")
echo "$TOKEN_JSON" | jq '{errorCode, errorMessage, ea, expiresIn}'   # 不要把 accessToken 打进日志
export FXK_TOKEN=$(echo "$TOKEN_JSON" | jq -r .accessToken)
export FXK_EA=$(echo "$TOKEN_JSON" | jq -r .ea)
```

Python 见第 10 节的 `FxkClient._ensure_token`。

**示例响应**（文档原文，未实测）

```json
{
  "openUserId": "FSCID_xxxxxxx",
  "accessToken": "BCxxxxxDF2",
  "expiresIn": 7084,
  "appId": "FSAID_xxxxx",
  "ea": "fxxxx1",
  "errorCode": 0,
  "errorMessage": "success",
  "traceId": "E-O.fxxxxx6b"
}
```

| 字段 | 说明 |
| --- | --- |
| accessToken | 授权凭证，有效期两个小时 |
| ea | 企业账号 → 填到 header `x-fs-ea` |
| expiresIn | 过期时间（示例 7084，看起来是剩余秒数；⚠ 文档未说明单位与语义） |
| openUserId | 文档注释为「企业openCorpId」，示例值是 `FSCID_…`——⚠ 字段名与含义不符，别把它当员工 ID 用 |

**注意事项**（文档原文，未实测）
- **token 生命周期**：有效期 7200 秒；0–6600 秒内调用返回**相同**的 token；6600–7200 秒之间调用返回**新** token，此时新旧 token 都可用；7200 秒后旧 token 失效。
- **本接口每分钟 ≤10 次，且不能并发调用**。所以必须缓存（文档建议缓存 6600 秒），多线程 / 多进程共享一份 token，并在 6600–7200 秒之间重新获取。
- 业务接口报 `20016`（corpAccessToken 不存在或已过期）时重新换 token 再重试一次。
- 无凭证探测（2026-09-11）：伪造凭证、以及**完全不传 appSecret 字段**，都返回 HTTP 200 +
  `{"errorCode":10006,"errorMessage":"the parameter appSecret is missing or illegal","errorDescription":"缺少参数或参数不合法","error":"非法请求","error_description":"缺少参数或参数不合法"}`。
  错误码与文档码表不一致，详见 `errors-and-limits.md`。

## 5. 旧版：换 corpAccessToken

**Endpoint**: `POST https://{host}/cgi/corpAccessToken/get/V2?thirdTraceId={uuid4}`
**用途**: 旧版传参方式的 token。拿到的 `corpAccessToken` + `corpId` 要和 `currentOpenUserId` 一起放进每个业务请求的 body 顶层。新接入的代码优先用第 4 节。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| appId | String | 是 | 企业应用 ID |
| appSecret | String | 是 | 企业应用凭证密钥 |
| permanentCode | String | 是 | 永久授权码 |

```bash
curl -sS -X POST "https://$FXK_HOST/cgi/corpAccessToken/get/V2?thirdTraceId=$(uuidgen | tr A-Z a-z)" \
  -H 'Content-Type: application/json' \
  -d "{\"appId\":\"$FXK_APP_ID\",\"appSecret\":\"$FXK_APP_SECRET\",\"permanentCode\":\"$FXK_PERMANENT_CODE\"}"
```

响应（文档原文，未实测）：`errorCode`、`errorMessage`、`corpAccessToken`、`corpId`、`expiresIn`（0~7200 秒，续期规则同第 4 节）。

旧版业务请求体：

```json
{
  "corpAccessToken": "{corpAccessToken}",
  "corpId": "{corpId}",
  "currentOpenUserId": "{currentOpenUserId}",
  "data": {}
}
```

无凭证探测（2026-09-11）：该路径仍在服务，伪造凭证返回
`{"errorCode":10006,"errorMessage":"the parameter appSecret is missing or illegal","errorDescription":"缺少参数或参数不合法","traceId":"open-api-gateway-web/…"}`。

## 6. 授权码模式（用户参与）与刷新 token

适用于有后端的 Web 应用、需要知道「是哪个用户在操作」的场景。服务端批量同步数据用第 4 节即可。

### 6.1 获取 code

**Endpoint**: `GET https://{host}/oauth2.0/authorize?responseType=code&appId={APPID}&redirectUrl={REDIRECTURL}&state={STATE}&thirdTraceId={uuid4}`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| appId | String | 是 | 自建应用 appId |
| redirectUrl | String | 是 | 回调地址（见下方 ⚠） |
| responseType | String | 是 | 固定 `code` |
| state | String | 是 | 防 CSRF，回调时原样带回；随机生成，如 MD5(时间戳 + 当前帐号) |
| thirdTraceId | String | 是 | 本次请求标识 |

授权成功后浏览器被重定向到 `https://你的域名/xxx?code=xxxxxxx&state=77598SDASF`。服务器必须校验 `state` 与发起时一致，不一致就拒绝，不再去换 token。

- ⚠ 文档自相矛盾：参数表说 redirectUrl 的「域名需要与创建应用填写的 web 端跳转地址保持一致」，下方说明又说「域名需要与应用详情页中的**登录授权发起页域名**保持一致」。两个配置项不是一回事，配置时让两处域名相同最稳。
- 频繁获取用户身份时，文档建议：拿到用户身份后由你的应用生成代表用户身份的 cookie，下次先校验 cookie，避免每次都走 code。

### 6.2 用 code 换 token

**Endpoint**: `POST https://{host}/oauth2.0/token?thirdTraceId={uuid4}`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| appId | String | 是 | — |
| appSecret | String | 是 | — |
| redirectUrl | String | 是 | 回调地址 |
| code | String | 是 | 授权码 |
| grantType | String | 是 | 固定 `authorization_code` |

响应（文档原文，未实测）：`openUserId`（用户的 openUserId）、`accessToken`（两小时）、`corpId`、`refreshToken`（两个月）、`expiresIn`。

- ⚠ 文档自相矛盾：此处返回示例 `"expiresIn": 1580000000`（像时间戳），而刷新接口示例是 `7200`（秒）。
- 旧版 wiki（artiId=19）这一节的请求示例只有 `appAccessToken` + `code` 两个字段，和它自己的参数表对不上；以新版参数表为准。

### 6.3 刷新 accessToken

**Endpoint**: `POST https://{host}/oauth2.0/token?thirdTraceId={uuid4}`

```json
{
  "grantType": "refresh_token",
  "appId": "FSAID_xxxxx",
  "appSecret": "…",
  "refreshToken": "xxxxxx"
}
```

响应：`accessToken`、`refreshToken`、`expiresIn`（示例 7200）。refreshToken 有效期 2 个月，失效后要用户重新授权。

## 7. 应用免登：用 code 换 openUserId

**Endpoint**: `POST https://{host}/oauth2.0/getUserInfoByCode?thirdTraceId={uuid4}`
**用途**: 纷享里打开企业内部应用时免输入账号密码。先按 6.1 拿 code，再调本接口换当前用户。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| appId | String | 是 | 自建应用 AppId |
| appSecret | String | 是 | 自建应用 APPSecret |
| code | String | 是 | 上一步获取的 code |
| authType | Integer | 否 | 默认 0（OpenAPI）；填 1（微信小程序）时还会返回 sessionKey |

响应（文档原文，未实测）：`{"errorCode":0,"errorMessage":"success","data":"openUserId"}`——`data` 直接就是 openUserId 字符串。

「纷享免登」（客户系统单点登录进纷享，SAML2.0 / OAuth2）是后台配置流程，不是 API，本 skill 不覆盖。

## 8. thirdTraceId

- 文档要求**所有接口**都在 URL 后带 `thirdTraceId`，每次请求不同，按 **RFC 4122 UUID v4** 生成（Python `uuid.uuid4()`、Shell `uuidgen`）。
- 它在 URL query 里，不在 body、不在 header。
- 无凭证探测（2026-09-11）：伪造 token 且**不带** thirdTraceId 时，网关返回的仍是鉴权错误 20016，没有先报缺 thirdTraceId；
  带真实 token 时缺它会不会被拒 ⚠ 未能判定。照文档每次都带。

## 9. x-fs-userid / currentOpenUserId 填谁

- 新版 `x-fs-userid`：CRM → 搜「人员」→ 点人员的「系统名」→ 账号信息里的「员工ID」（如 `1000`）。
- 旧版 `currentOpenUserId`：openUserId（`FSUID_…`）。
- **它决定数据权限**。接口按这个人的角色和数据权限执行：查不到数据、报「无此操作的数据权限」「没有XXXX权限」，多数是这个人没权限。
  文档建议用 **CRM 管理员**的员工 ID（管理员默认有除人员对象外所有数据的权限）。人员对象（PersonnelObj）另需共享规则，见 `org-directory.md`。
- 客户端凭证模式「支持使用任意员工的id进行访问接口」，所以同一个 token 可以换不同 `x-fs-userid` 以不同身份操作。
- `currentOpenUserId` 在旧版每个业务请求里都是必填（参数表「必须：是」）；新版对应的 `x-fs-userid` 在「公共参数填写」里列为「必填参数」。

## 10. 可直接复用的 Python 客户端

其他 reference 里的 Python 示例都假设有这个 `FxkClient`（`requests` 实现，官方文档未提供 SDK）。

```python
import os, time, uuid, threading
import requests

HOST = os.environ.get("FXK_HOST", "open.fxiaoke.com")   # 按所在云改，不要用 www.fxiaoke.com
BASE = f"https://{HOST}"


class FxkError(RuntimeError):
    def __init__(self, resp: dict):
        self.code = resp.get("errorCode")
        self.resp = resp
        super().__init__(f"errorCode={self.code} msg={resp.get('errorMessage')} "
                         f"desc={resp.get('errorDescription')} traceId={resp.get('traceId')}")


class FxkClient:
    """客户端凭证模式 + 新版 header 传参。凭证只从环境变量读。"""

    def __init__(self, user_id: str | None = None):
        self.app_id = os.environ["FXK_APP_ID"]
        self.app_secret = os.environ["FXK_APP_SECRET"]
        self.permanent_code = os.environ["FXK_PERMANENT_CODE"]
        self.user_id = user_id or os.environ["FXK_USER_ID"]   # CRM 员工ID，如 "1000"，建议 CRM 管理员
        self._token = self._ea = None
        self._refresh_at = 0.0
        self._lock = threading.Lock()      # 换 token 接口不能并发、每分钟 ≤10 次

    def _ensure_token(self, force: bool = False) -> None:
        with self._lock:
            if not force and self._token and time.time() < self._refresh_at:
                return
            r = requests.post(f"{BASE}/oauth2.0/token",
                              params={"thirdTraceId": str(uuid.uuid4())},
                              json={"appId": self.app_id, "appSecret": self.app_secret,
                                    "permanentCode": self.permanent_code, "grantType": "app_secret"},
                              timeout=15)
            j = r.json()
            if j.get("errorCode") != 0:
                raise FxkError(j)
            self._token, self._ea = j["accessToken"], j["ea"]
            # 0–6600 秒内重复获取只会拿到同一个 token，所以最多缓存 6600 秒
            ttl = int(j.get("expiresIn") or 7200)
            self._refresh_at = time.time() + max(60, min(6600, ttl - 600))

    def post(self, path: str, body: dict) -> dict:
        self._ensure_token()
        for attempt in (0, 1):
            r = requests.post(f"{BASE}{path}",
                              params={"thirdTraceId": str(uuid.uuid4())},   # 每次新的 UUID v4
                              headers={"authorization": f"Bearer {self._token}",
                                       "x-fs-ea": self._ea,
                                       "x-fs-userid": self.user_id,
                                       "Content-Type": "application/json"},
                              json=body, timeout=30)
            try:
                j = r.json()                  # 业务错误也是 HTTP 200，只能看 errorCode
            except ValueError:
                raise RuntimeError(f"非 JSON 响应 HTTP {r.status_code}（域名是否写成了 www.fxiaoke.com？）")
            if j.get("errorCode") == 0:
                return j
            if j.get("errorCode") == 20016 and attempt == 0:   # token 失效 → 重新换一次
                self._ensure_token(force=True)
                continue
            raise FxkError(j)


# 用法
# fxk = FxkClient()
# acc = fxk.post("/cgi/crm/v2/data/get", {"data": {"dataObjectApiName": "AccountObj", "objectDataId": "…"}})
```

多进程 / 多实例部署时，把 token 放到 Redis 之类的共享缓存里，由一个进程负责刷新，否则容易触发「每分钟 ≤10 次、不能并发」的限制。

## 11. 本文件的 ⚠

- ⚠ 文档表述含混：`convertUserId` / `convertMediaId`「默认为 true，新版参时默认为 false」（第 3 节）。
- ⚠ 文档未说明：客户端凭证响应 `expiresIn` 的单位与语义（示例 7084）；`openUserId` 字段注释为企业 openCorpId（第 4 节）。
- ⚠ 文档自相矛盾：授权码模式 redirectUrl 要对齐「web 端跳转地址」还是「登录授权发起页域名」（第 6.1 节）。
- ⚠ 文档自相矛盾：授权码返回 `expiresIn: 1580000000` vs 刷新返回 `7200`（第 6.2 节）。
- ⚠ 文档自相矛盾：旧版 wiki 与新版对 `open-hws` / `open-ale` 的云标签不同（第 2 节）。
- ⚠ 未能判定：真实 token 下缺 `thirdTraceId` 是否被拒（第 8 节）。
- Gap（探测证实）：`www.fxiaoke.com` 不是 API 网关（第 2 节）。
