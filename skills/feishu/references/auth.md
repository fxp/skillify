# 鉴权与三种 access token

来源：`open.feishu.cn/document`「API 调用指南」「认证及授权」「服务端 SDK」（抓取于 2026-09-11）。
**除标注「无凭证探测（2026-09-11）」的条目外，所有报错码与行为描述均为文档原文，未实测。**

## 目录

1. [三种凭证怎么选](#1-三种凭证怎么选)
2. [自建应用获取 tenant_access_token（最常用）](#2-自建应用获取-tenant_access_token)
3. [自建应用获取 app_access_token](#3-自建应用获取-app_access_token)
4. [商店应用：app_ticket → app_access_token → tenant_access_token](#4-商店应用的三步换取)
5. [user_access_token：OAuth 授权码流程（v3 端点）](#5-user_access_tokenoauth-授权码流程)
6. [刷新 user_access_token](#6-刷新-user_access_token)
7. [用 user_access_token 获取登录用户信息](#7-获取登录用户信息)
8. [调用 API 时怎么带凭证、凭证错了会看到什么](#8-调用-api-时怎么带凭证)
9. [飞书与 Lark 国际版域名](#9-飞书与-lark-国际版域名)
10. [官方 Python SDK 的 token 管理](#10-官方-python-sdk)
11. [容易写错的地方](#11-容易写错的地方)

---

## 1. 三种凭证怎么选

| 凭证 | 值的形态 | 代表谁 | 怎么拿 | 有效期 | 典型用途 |
|---|---|---|---|---|---|
| `tenant_access_token` | `t-` 开头 | 应用身份（某个租户下） | 自建：`app_id` + `app_secret`；商店：`app_access_token` + `tenant_key` | 最长 2 小时 | 机器人发消息、以应用身份读通讯录、审批、飞书人事 |
| `app_access_token` | `a-` 或 `t-` 开头 | 应用身份短期令牌 | 自建：`app_id` + `app_secret`；商店：再加 `app_ticket` | 最长 2 小时 | 基本只用于**商店应用**换 tenant_access_token |
| `user_access_token` | v2/v3 令牌端点返回 `eyJ...`（JWT 形态，1–2 KB）；历史接口返回 `u-` 开头 | 某个登录用户 | OAuth 2.0 授权码流程 | 以响应 `expires_in` 为准（示例 7200 秒） | 以用户身份创建多维表格（所有者是该用户）、搜索用户、搜索部门 |

文档给的选择规则：

- **先看目标 API 文档「请求头 → Authorization」一栏**写了支持哪几种 token，不支持的 token 会直接报错。
  本 skill 覆盖的接口里：
  - 只支持 `tenant_access_token`：创建审批实例、审批任务操作、飞书人事（企业版）大部分接口、标准版花名册、事件出口 IP。
  - 只支持 `user_access_token`：搜索用户 `GET /open-apis/search/v1/user`、搜索部门 `POST /open-apis/contact/v3/departments/search`、获取登录用户信息 `GET /open-apis/authen/v1/user_info`。
  - 两者都支持：通讯录读写、发消息、多维表格。
- 不操作用户个人资源时用 tenant_access_token；要操作"用户自己的"资源（在用户云空间建文档）用 user_access_token。
- 用 tenant_access_token 读通讯录，数据范围由**应用的通讯录权限范围**（开发者后台「权限管理 → 数据权限」）决定；
  用 user_access_token 读，范围由**该用户的组织架构可见范围**决定，不受应用通讯录范围影响（见 [contacts.md](contacts.md)）。
- 文档说开放平台"正在逐步统一 app_access_token 和 tenant_access_token"，新代码按 tenant_access_token 写即可。

---

## 2. 自建应用获取 tenant_access_token

**Endpoint**: `POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal`
**用途**: 企业自建应用用 App ID / App Secret 换应用身份凭证。不需要任何 API 权限。商店应用不能用这个接口（见第 4 节）。

**关键参数**（请求体，`Content-Type: application/json; charset=utf-8`）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `app_id` | string | 是 | — | 开发者后台「凭证与基础信息」，形如 `cli_xxx` |
| `app_secret` | string | 是 | — | 同上 |

**示例请求**

```bash
curl -s -X POST 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal' \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d "{\"app_id\":\"$FEISHU_APP_ID\",\"app_secret\":\"$FEISHU_APP_SECRET\"}"
```

```python
import os, time, requests

BASE = os.environ.get("FEISHU_BASE", "https://open.feishu.cn")   # Lark 国际版改成 https://open.larksuite.com
_cache = {"token": None, "expire_at": 0.0}

def tenant_access_token() -> str:
    # 文档：剩余有效期 >= 30 分钟时再调用会返回同一个 token；< 30 分钟才会发新的
    if _cache["token"] and time.time() < _cache["expire_at"] - 30 * 60:
        return _cache["token"]
    r = requests.post(f"{BASE}/open-apis/auth/v3/tenant_access_token/internal",
                      json={"app_id": os.environ["FEISHU_APP_ID"],
                            "app_secret": os.environ["FEISHU_APP_SECRET"]},
                      timeout=10)
    body = r.json()
    if body.get("code") != 0:              # 失败时 HTTP 仍是 200，只能看 code
        raise RuntimeError(f"get tenant_access_token failed: {body}")
    _cache["token"] = body["tenant_access_token"]
    _cache["expire_at"] = time.time() + body["expire"]
    return _cache["token"]
```

**示例响应**（文档原文）

```json
{
    "code": 0,
    "msg": "ok",
    "tenant_access_token": "t-caecc734c2e3328a62489fe0648c4b98779515d3",
    "expire": 7200
}
```

**注意事项**

- **字段在顶层，不在 `data` 里**；名字是 `tenant_access_token` 和 `expire`（秒），不是 `access_token` / `expires_in`。
- 有效期最长 2 小时。剩余 <30 分钟时再调用会拿到**新 token**，此时新旧两个 token 同时有效；剩余 ≥30 分钟时返回原 token。
  所以"每次请求前都去换一次"不会报错，但毫无必要；按 `expire` 缓存，在最后 30 分钟内刷新即可。
- 无凭证探测（2026-09-11）：`app_id=test` → **HTTP 200** + `{"code":10003,"data":{},"msg":"invalid param"}`。
  换 token 失败**不会**给 4xx，`raise_for_status()` 抓不到，必须判 `code`。
- 无凭证探测（2026-09-11）：路径带尾斜杠 `/internal/`（文档「调用 API」页的示例就是这么写的）同样返回 10003，路径可达。
- 无凭证探测（2026-09-11）：用 `GET` 调用返回 HTTP 404 纯文本 `404 page not found`（见 [errors-and-limits.md](errors-and-limits.md)）。
- App Secret 错误、应用停用分别对应哪个错误码 ⚠ 文档未说明（通用错误码表有 `10003 invalid parameter`、`10014 app unauthorized`、`10015 wrong app secret`，未说明各自触发条件）。
- IP 白名单对获取 access_token 的接口不生效（文档原文）。

---

## 3. 自建应用获取 app_access_token

**Endpoint**: `POST https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal`
**用途**: 自建应用获取 app_access_token；响应里**顺带返回 tenant_access_token**。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `app_id` | string | 是 | 同上 |
| `app_secret` | string | 是 | 同上 |

```bash
curl -s -X POST 'https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal' \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d "{\"app_id\":\"$FEISHU_APP_ID\",\"app_secret\":\"$FEISHU_APP_SECRET\"}"
```

示例响应（文档原文）：

```json
{"app_access_token": "t-g1044ghJRUIJJ5ZPPZMOHKWZISL33E4QSS3abcef", "code": 0, "expire": 7200,
 "msg": "ok", "tenant_access_token": "t-g1044ghJRUIJJ5ZPPZMOHKWZISL33E4QSS3abcef"}
```

注意：有效期规则同 tenant_access_token（<30 分钟重取得新值）。无凭证探测（2026-09-11）：伪造 `app_id` → HTTP 200 + `code:10003`。

---

## 4. 商店应用的三步换取

商店应用（应用商店上架、多租户安装）不能直接用 App Secret 换 tenant_access_token，要走三步：

1. **收 app_ticket**：为应用配置事件订阅地址后，开放平台**每 1 小时**推送一次 `app_ticket` 事件，应用自己保存最新值。
   推送可能延迟，可主动触发重推：

   **Endpoint**: `POST https://open.feishu.cn/open-apis/auth/v3/app_ticket/resend`，body `{"app_id": "...", "app_secret": "..."}`。
   通用错误码表：`10016 app resend fail`——自建应用调用会失败（文档原文）。app_ticket 事件体结构本 skill 未抓取，⚠ 以文档「app_ticket 事件」页为准。

2. **换 app_access_token**：

   **Endpoint**: `POST https://open.feishu.cn/open-apis/auth/v3/app_access_token`

   | 参数 | 类型 | 必填 | 说明 |
   |---|---|---|---|
   | `app_id` | string | 是 | |
   | `app_secret` | string | 是 | |
   | `app_ticket` | string | 是 | 第 1 步收到的最新值 |

   响应顶层 `code`、`msg`、`app_access_token`、`expire`。

3. **按租户换 tenant_access_token**：

   **Endpoint**: `POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token`

   | 参数 | 类型 | 必填 | 说明 |
   |---|---|---|---|
   | `app_access_token` | string | 是 | 第 2 步结果 |
   | `tenant_key` | string | 是 | 租户标识。来源：企业开通应用时推送的「首次启用应用」事件；或用户登录网页 / 小程序时身份信息里带的 `tenant_key` |

   示例响应（文档原文）：`{"code":0,"msg":"success","tenant_access_token":"t-caecc...","expire":7140}`。
   每个安装了应用的租户各有一个 tenant_access_token，缓存要按 `tenant_key` 分开。

---

## 5. user_access_token：OAuth 授权码流程

**先注意端点版本。** `llms.txt` 索引里「获取 user_access_token」指向的页面现在是 **v2（已标为历史版本，不推荐）**：
`POST https://open.feishu.cn/open-apis/authen/v2/oauth/token`。当前推荐的是 **v3**：`POST https://accounts.feishu.cn/oauth/v3/token`
（注意域名是 `accounts.feishu.cn`，路径没有 `/open-apis`）。文档说除端点外，请求参数和响应结构与 v2 一致；
v3 修正了 PKCE：授权阶段没传 `code_challenge` 但换 token 时传了 `code_verifier`，v2 不拒绝，v3 会拒绝。

### 5.1 第一步：把用户重定向到授权页

**Endpoint**: `GET https://accounts.feishu.cn/open-apis/authen/v1/authorize`（这是浏览器页面，不是服务端调用）

| 查询参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `client_id` | string | 是 | 应用 App ID |
| `response_type` | string | 是 | 固定 `code` |
| `redirect_uri` | string | 是 | URL 编码；**必须先在开发者后台「开发配置 → 安全设置 → 重定向 URL」登记**，否则不过安全校验 |
| `scope` | string | 否 | 空格分隔、区分大小写；一次最多 200 个；要拿 `refresh_token` 必须包含 `offline_access`；拼了应用没开通的权限，用户授权时报 20027 |
| `state` | string | 否 | 回调原样带回，用来防 CSRF，务必校验 |
| `code_challenge` | string | 否 | PKCE |
| `code_challenge_method` | string | 否 | `S256`（推荐）或 `plain`（默认值） |
| `prompt` | string | 否 | `consent`：强制显示授权页 |

用户同意后浏览器跳到 `redirect_uri?code=...&state=...`；拒绝则是 `?error=access_denied&state=...`。
`code` **有效期 5 分钟、只能用一次**，字符集 `[A-Za-z0-9-_]`，文档建议至少预留 64 字符。
在飞书客户端内打开网页应用时可免确认直接跳转（文档原文）。`redirect_uri` 含 `#` 时，fragment 会被拼到 `?code=...` 之后，解析时注意。

授权是**累积**的：最新生成的 user_access_token 包含用户历史上授予过的所有权限。

### 5.2 第二步：用 code 换 token

**Endpoint**: `POST https://accounts.feishu.cn/oauth/v3/token`
**用途**: 授权码换 `user_access_token`（和可选的 `refresh_token`）。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `grant_type` | string | 是 | — | 固定 `authorization_code` |
| `client_id` | string | 是 | — | App ID |
| `client_secret` | string | 否* | — | 开放平台创建的应用都是 Confidential Client，**必须填**；只有官方 MCP 应用这类 Public Client 可不填但必须走 PKCE |
| `code` | string | 是 | — | 第一步拿到的授权码 |
| `redirect_uri` | string | 否 | — | 若第一步传了，这里要一致，否则 20071 |
| `code_verifier` | string | 否 | — | PKCE 时必填；43–128 字符 |
| `scope` | string | 否 | 全部已授权 | 只能**缩减**，必须是已授权范围的子集（否则 20068），不能重复（20067） |

请求头 `Content-Type`：推荐 `application/x-www-form-urlencoded`，文档说也兼容 `application/json`。
不要同时用 HTTP Basic 认证和 `client_secret`，否则 20070。

**示例请求**

```bash
curl -s -X POST 'https://accounts.feishu.cn/oauth/v3/token' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=authorization_code' \
  --data-urlencode "client_id=$FEISHU_APP_ID" \
  --data-urlencode "client_secret=$FEISHU_APP_SECRET" \
  --data-urlencode "code=$AUTH_CODE" \
  --data-urlencode "redirect_uri=https://example.com/api/oauth/callback"
```

```python
import os, requests

def exchange_code(code: str, redirect_uri: str) -> dict:
    r = requests.post("https://accounts.feishu.cn/oauth/v3/token", data={
        "grant_type": "authorization_code",
        "client_id": os.environ["FEISHU_APP_ID"],
        "client_secret": os.environ["FEISHU_APP_SECRET"],
        "code": code,
        "redirect_uri": redirect_uri,
    }, timeout=10)
    body = r.json()
    if body.get("code") != 0:          # 失败时 HTTP 400，body 带 error / error_description / code
        raise RuntimeError(f"{body.get('code')} {body.get('error')}: {body.get('error_description')}")
    return body   # access_token / expires_in / refresh_token / refresh_token_expires_in / token_type / scope
```

**示例响应**（文档原文）

```json
{
    "code": 0,
    "access_token": "eyJhbGciOiJFUzI1NiIs**********X6wrZHYKDxJkWwhdkrYg",
    "expires_in": 7200,
    "refresh_token": "eyJhbGciOiJFUzI1NiIs**********XXOYOZz1mfgIYHwM8ZJA",
    "refresh_token_expires_in": 604800,
    "scope": "auth:user.id:read offline_access task:task:read user_profile",
    "token_type": "Bearer"
}
```

失败响应（文档原文）：`{"code": 20050, "error": "server_error", "error_description": "An unexpected server error occurred..."}`

**注意事项**

- 响应字段叫 **`access_token`**（不是 `user_access_token`），也**没有 `data` 包裹**；这和 tenant_access_token 接口的字段名又不同。
- `expires_in`、`refresh_token_expires_in` 是**非固定值**，文档明确要求按响应值计算过期时间，不要硬编码 7200。
- `refresh_token` 只有用户授予了 `offline_access` 才返回。
- token 长度通常 1–2 KB 且会随 scope 增多变长，文档建议存储预留 4 KB（`VARCHAR(255)` 会截断）。
- 实际生效权限以响应 `scope` 为准，服务端可能裁剪。
- 用户不在应用可用范围内会报 20010。
- 无凭证探测（2026-09-11）：v3 端点用表单和 JSON 两种编码，伪造 code 时都返回 **HTTP 400** +
  `{"error":"invalid_grant","error_description":"The authorization code is not found. Please note that an authorization code can only be used once.","code":20003}`；
  v2 端点 `open.feishu.cn/open-apis/authen/v2/oauth/token` 仍在响应，返回相同结构。
- ⚠ 文档自相矛盾：「获取授权码」页说使用 PKCE 时"可以暂时搭配 v2 换取 Token，后续将尽快支持最新的 Token 端点"；
  而 v2 页的迁移说明称新增 v3 正是为了修正 PKCE 校验，并说"已启用且正确使用 PKCE 时可直接迁移到 v3"。用 PKCE 时哪个端点可用，拿到凭证后需实测。

**授权阶段 / 换 token 阶段的常见错误码**（文档原文，未实测）

| code | HTTP | 含义 |
|---|---|---|
| 20001 / 20063 | 400 | 缺必填参数 / 请求体格式不对 |
| 20002 | 400 | `client_id` 与 `client_secret` 不匹配 |
| 20003 / 20065 | 400 | 授权码不存在 / 已被用过（只能用一次） |
| 20004 | 400 | 授权码过期（>5 分钟） |
| 20010 | 400 | 用户没有应用的使用权限（不在可用范围） |
| 20024 | 400 | 授权码 / refresh_token 属于另一个应用 |
| 20027 | — | 授权页：scope 里有应用未开通的权限 |
| 20049 | 400 | PKCE 校验失败 |
| 20050 / 20072 | 500 / 503 | 服务端错误 / 暂不可用，可重试 |
| 20067 / 20068 | 400 | scope 重复 / 超出已授权范围 |
| 20070 | 400 | 同时用了 Basic Auth 和 client_secret |
| 20071 | 400 | `redirect_uri` 与授权时不一致 |

---

## 6. 刷新 user_access_token

**Endpoint**: `POST https://accounts.feishu.cn/oauth/v3/token`（与换 token 同一个端点，`grant_type` 不同）
**用途**: 用 `refresh_token` 换新的 `user_access_token` 和**新的** `refresh_token`。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `grant_type` | string | 是 | 固定 `refresh_token` |
| `client_id` | string | 是 | App ID |
| `client_secret` | string | 是 | App Secret |
| `refresh_token` | string | 是 | 上一次换到 / 刷到的 refresh_token |
| `scope` | string | 否 | 只能缩减 |

```python
def refresh(refresh_token: str) -> dict:
    r = requests.post("https://accounts.feishu.cn/oauth/v3/token", data={
        "grant_type": "refresh_token",
        "client_id": os.environ["FEISHU_APP_ID"],
        "client_secret": os.environ["FEISHU_APP_SECRET"],
        "refresh_token": refresh_token,
    }, timeout=10)
    body = r.json()
    if body.get("code") != 0:
        raise RuntimeError(body)
    # 必须立刻把新的 refresh_token 持久化——旧的已经作废
    return body
```

**注意事项**（文档原文，未实测）

- 前置条件两个：开发者后台开通 `offline_access` 权限且授权链接的 `scope` 带上它；「安全设置」里打开"刷新 user_access_token"开关（看不到开关说明默认开启；改完要发版）。没开开关报 20074。
- **`refresh_token` 只能用一次**。刷新成功后原 refresh_token 立即失效（再用报 20064 / 20073），原 user_access_token 在到期前仍可用。
  多实例并发刷新同一个 refresh_token，只有一个会成功——刷新要加锁。
- 用户授权满 **365 天**后必须让用户重新授权，继续刷新报 20037。
- v3 端点接受 v2、v3 下发的 refresh_token；v2 刷新端点只接受 v2 下发的（20026 说明）。
- 其他错误码：20024（refresh_token 属于别的应用）、20026（refresh_token 无效）、20037（已过期）。

---

## 7. 获取登录用户信息

**Endpoint**: `GET https://open.feishu.cn/open-apis/authen/v1/user_info`
**用途**: 用 user_access_token 取当前登录用户的身份，常用于"飞书登录"。只接受 user_access_token。

```bash
curl -s 'https://open.feishu.cn/open-apis/authen/v1/user_info' -H "Authorization: Bearer $USER_ACCESS_TOKEN"
```

返回 `data` 下的关键字段：`name`、`open_id`、`union_id`、`user_id`（需 `contact:user.employee_id:readonly` 字段权限）、
`email`、`mobile`、`tenant_key`。文档提醒：`email`、`mobile` 是管理员导入的联系方式，**未经用户本人实时验证**，
不要直接当业务系统的登录凭证。用户身份识别用 `open_id` / `union_id`。

---

## 8. 调用 API 时怎么带凭证

- 请求头：`Authorization: Bearer <access_token>`（文档："该值需要增加 `Bearer<空格>` 前缀"）。JSON 接口加 `Content-Type: application/json; charset=utf-8`。
- **不要在前端使用任何 access_token**，一律服务端调用（文档原文）。
- 无凭证探测（2026-09-11）看到的鉴权失败形态：

| 情况 | HTTP | code | msg |
|---|---|---|---|
| 不带 Authorization | 400 | `99991661` | `Missing access token for authorization...` |
| **只写 token 不写 `Bearer `** | 400 | `99991661` | 同上——服务端当成没带，不会提示缺前缀 |
| 伪造的 `t-` token | 400 | `99991663` | `Invalid access token for authorization...` |
| 伪造的 `eyJ` 形态 token | 400 | `99991668` | `Invalid access token...`（被识别为 user token） |

- 其余与 token 有关的通用错误码（文档原文）：`99991663` 也可能是"当前接口不支持 tenant_access_token"；
  `99991677` user token 过期；`99991672` 应用没申请该 API 权限（返回里有缺失的 scope）；
  `99991679` 用户没授予该权限——按返回的 `permission_violations` 重新发起授权并拼上缺的 scope；
  `99991671` "token 格式错误，must start with t-/u-"。
- ⚠ 文档自相矛盾：99991671 的描述要求 token 以 `t-`/`u-` 开头，但新版令牌端点下发的 user_access_token 是 `eyJ...`。
  探测中 `eyJ` 形态被当作 user token 校验（99991668），说明 99991671 的描述已过时。

---

## 9. 飞书与 Lark 国际版域名

| | 飞书（中国） | Lark（国际版） |
|---|---|---|
| OpenAPI 基址 | `https://open.feishu.cn` | `https://open.larksuite.com`（SDK 文档列出） |
| OAuth 授权页 / 令牌 | `https://accounts.feishu.cn/...` | ⚠ 文档未说明 |

- 无凭证探测（2026-09-11）：`POST https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal` 伪造参数返回与飞书域名完全相同的
  `{"code":10003,"data":{},"msg":"invalid param"}`，路径结构一致。
- 基址写成可配置项（环境变量），不要硬编码 `open.feishu.cn`。飞书租户的应用能否调 Lark 域名、反之亦然，⚠ 文档未说明。
- 文档站里还大量出现 `open.larkoffice.com` 的链接（开发者后台、事件结构页），它与上面两个域名的关系 ⚠ 文档未说明；API 调用以 `open.feishu.cn` 为准。

---

## 10. 官方 Python SDK

```bash
pip install lark-oapi -U     # Python >= 3.7
```

```python
import os
import lark_oapi as lark
from lark_oapi.api.contact.v3 import *

client = lark.Client.builder() \
    .app_id(os.environ["FEISHU_APP_ID"]) \
    .app_secret(os.environ["FEISHU_APP_SECRET"]) \
    .domain(lark.FEISHU_DOMAIN) \
    .log_level(lark.LogLevel.INFO) \
    .build()                       # 自建应用：SDK 自动获取、缓存 tenant_access_token

req = BatchGetIdUserRequest.builder() \
    .user_id_type("open_id") \
    .request_body(BatchGetIdUserRequestBody.builder().emails(["someone@example.com"]).build()) \
    .build()
resp = client.contact.v3.user.batch_get_id(req)
if not resp.success():
    raise RuntimeError(f"{resp.code} {resp.msg} log_id={resp.get_log_id()}")
print(lark.JSON.marshal(resp.data, indent=2))
```

- 方法定位规则：`client.<业务域>.<版本>.<资源>.<方法>`，对应 URL `/open-apis/<业务域>/<版本>/<资源>/...`。
- 以用户身份调用：Client 加 `.enable_set_token(True)`，每次请求传
  `lark.RequestOption.builder().user_access_token(token).build()` 作为第二个参数。
- 商店应用：`.app_type(lark.AppType.ISV)`，并在 RequestOption 里设置 `tenant_key`。
  ⚠ 文档自相矛盾：SDK 配置表里 `app_ticket` 这一项的描述写的是"需要在该参数内传入应用的 app_access_token"。
- `domain`：默认飞书；文档写"Lark：`https://open.larksuite.com`"，但 SDK 里对应常量名 ⚠ 文档未说明，可直接传 URL 字符串（未核实）。
- `timeout` 不传默认**永不超时**（文档原文），生产代码务必 `.timeout(秒)`。

---

## 11. 容易写错的地方

1. tenant_access_token 响应在顶层、字段名 `expire`；OAuth 响应字段名 `access_token` / `expires_in`——三个接口三套命名，别用一个解析函数套。
2. 换 token 失败 HTTP 200（tenant/app token）或 HTTP 400（OAuth），**两种都要判 `code`**。
3. `Authorization` 必须带 `Bearer `；少了只会看到 99991661"没带 token"，很难联想到是前缀问题。
4. user_access_token 流程用 v3 端点 `accounts.feishu.cn/oauth/v3/token`，别照索引里的 v2 页抄 `open.feishu.cn/open-apis/authen/v2/oauth/token`。
5. refresh_token 一次性，刷新后立刻持久化新值；并发刷新要加锁；365 天后必须重新授权。
6. 商店应用没有 `/internal` 接口可用，要 app_ticket → app_access_token → 按 tenant_key 换 tenant_access_token。
7. 选错 token 类型报 99991663 / 99991668，先回头看接口文档 Authorization 一栏支持哪种。
