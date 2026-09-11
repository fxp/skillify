# 鉴权与 access_token（自用型 / 工具型）+ API 调用格式

内容整理自 https://doc.youzanyun.com/ （抓取于 2026-09-11）。**未用真实凭证验证。**
报错与行为描述未标注来源的，都是「文档原文，未实测」；标「无凭证探测（2026-09-11）」的见 `youzan-workspace/probe-log.md`。

## 目录
1. 先判断应用类型
2. 自用型：`authorize_type=silent` 换 token / 刷新
3. 工具型：code 回调 → `authorization_code` 换 token → `refresh_token` 刷新
4. 调业务 API 的统一格式（URL、版本号、token 位置、Content-Type）
5. token 缓存与刷新：可直接用的 Python 实现
6. 多店铺、IP 白名单、能力包
7. 有容器应用与“免鉴权”SDK
8. 获取 token 的错误码
9. ⚠ 本文件的文档矛盾 / 未说明

---

## 1. 先判断应用类型

有赞云应用有两个维度（基本概念页）：

| 维度 | 取值 | 对鉴权的影响 |
|---|---|---|
| 用途 | **自用型**（商家自研，不上架）/ **工具型**（服务商开发，上架应用市场，商家订购） | **决定换 token 的方式**（见下） |
| 部署 | **有容器**（跑在有赞云）/ **无容器**（跑在自己服务器） | 换 token 方式**一致**；无容器支持 IP 白名单、有容器不支持；有容器有开发 / 生产两组 client_id，无容器只有一组 |

- 自用型：用 `client_id + client_secret + 店铺 kdt_id` 直接换（`silent`），不需要商家每次授权。
- 工具型：只能用商家订购后有赞推送给你的 **授权 code** 换（`authorization_code`），再用 `refresh_token` 续期。
- 用错方式 → `1105 不支持的应用类型`（文档原文，未实测）。
- 接扩展点必须用有容器应用；只做 API + 消息打通用无容器即可。

## 2. 自用型：silent 换 token / 刷新

**Endpoint**: `POST https://open.youzanyun.com/auth/token`
**用途**: 自用型应用（有容器 / 无容器一致）获取某个店铺的 access_token；同一接口传 `refresh: true` 即刷新。

**关键参数**（JSON body，`Content-Type: application/json`）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| client_id | String | 是 | 应用 ID（控制台“应用概况”查看） |
| client_secret | String | 是 | 应用 secret |
| authorize_type | String | 是 | 固定 `"silent"` |
| grant_id | String | 是 | 授权店铺 id，即 **kdt_id**（支付商户对接传 mchId） |
| refresh | Boolean | 是 | 默认 false；true 表示生成新 token |

**示例请求**
```bash
curl -X POST 'https://open.youzanyun.com/auth/token' \
  -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$YOUZAN_CLIENT_ID\",\"client_secret\":\"$YOUZAN_CLIENT_SECRET\",\"authorize_type\":\"silent\",\"grant_id\":\"$YOUZAN_KDT_ID\",\"refresh\":false}"
```
```python
import os, requests
r = requests.post("https://open.youzanyun.com/auth/token", json={
    "client_id": os.environ["YOUZAN_CLIENT_ID"],
    "client_secret": os.environ["YOUZAN_CLIENT_SECRET"],
    "authorize_type": "silent",
    "grant_id": os.environ["YOUZAN_KDT_ID"],
    "refresh": False,          # 布尔值，不要写成字符串 "false"
}, timeout=10)
body = r.json()
assert body.get("success") and body.get("code") == 200, body
token = body["data"]["access_token"]
```

**示例响应**（文档原文）
```json
{"success": true, "code": 200,
 "data": {"expires": 1583720718116, "scope": "beauty_appointment beauty_cashier ...",
          "access_token": "774ae7b675f8db2aa65d38bf5de710b", "authority_id": "42583152"},
 "message": null}
```

**注意事项**
- `expires` 是**过期时刻的毫秒时间戳**（文档：“时间戳（单位：毫秒；过期时间：7天）”），不是“剩余秒数”。按 OAuth 习惯写 `time.time() + expires` 会得到一个几万年后的时间。
- `authority_id` 就是 kdt_id。
- 自用型响应里有没有 `refresh_token`：49259 页的字段表和示例有，IO94 / 3031 页没有 → ⚠ 文档自相矛盾。自用型刷新本来就不用 refresh_token，别依赖它。
- 文档的 curl 示例把 `refresh` 写成字符串 `"false"`，参数表写 Boolean → ⚠ 文档未说明字符串是否被接受，统一传布尔。
- `refresh` 的语义（F4cU / 3031 页原文）：
  - 旧 token 有效期内 + `refresh=false` → 返回旧 token，**不续期**；
  - 旧 token 已过期 + 任意 → 生成新 token；
  - 旧 token 有效期内 + `refresh=true` → 生成新 token。旧 token **还能用 1 小时**（F4cU、3031、FAQ 5172、错误码 4202 行）还是**立即失效**（49259、49275）→ ⚠ 文档自相矛盾。写代码时按“立即失效”处理最安全：刷新后立刻切换到新 token，不要并发地让旧 token 继续跑。
- 一个店铺只能授权给一个自用型应用；一个自用型应用默认只能授权一个店铺，两个及以上要在控制台提交申请、审核通过后再由商家后台确认（8702）。
- 必须 `application/json`。无凭证探测（2026-09-11，单次）：同样参数用 form 编码提交，返回
  `{"success":false,"code":1000,"data":null,"message":"Content type 'application/x-www-form-urlencoded;charset=UTF-8' not supported,Please use 'application/json;charset=UTF-8'"}`。
  注意错误码表把 1000 描述为“client_secret 不正确”，所以**不能只凭 1000 判断是 secret 错了**，要看 message。

## 3. 工具型：code 回调 → authorization_code → refresh_token

### 3.1 拿到授权 code
- 只有工具型需要 code。商家在应用市场订购后，有赞向控制台“应用概况”里配置的**回调地址**推送 3 条消息：应用订购、应用授权、授权 code，**无先后顺序**。
- 回调要求：**GET 请求、GBK 编码**；回调地址**不能带自定义参数**（`https://a.com/notify?id=1` 错，`https://a.com/notify` 对）。
- code 通知形如 `https://你的回调地址?code=xxxx`；订购 / 授权消息形如 `?message=...`，`message` 先 urldecode，再用 **client_secret 做 AES 解密**（3173 页，官方解密 demo 是 zip 包，本 skill 未下载，算法细节 ⚠ 文档未在正文说明）。
- code **2 分钟有效、只能换一次**（FAQ 3906、3907）。过期或重复使用 → `1005 非法授权码`。
- code 本身看不出是哪家店：换 token 后用响应里的 `authority_id`（= kdt_id）关联（FAQ 3909）。
- 同一商家收到多个 code 不一定异常（控制台也能手动点“获取 code”触发）。
- 开发期：控制台“应用上架 → 授权管理”或测试店铺页点“获取 code”，会立即推送到回调地址。
- 需要自定义参数时（仅限已订购的店铺）：引导商家打开 `https://diy.youzanyun.com/oauth/authorize?client_id=...&state=...`，确认后回调 URL 带 `code` 与 `state`（FAQ 33403）。

最小回调接收（Flask）：
```python
from flask import Flask, request
app = Flask(__name__)

@app.get("/youzan/callback")          # 有赞以 GET 推送，参数 GBK 编码
def youzan_callback():
    code = request.args.get("code")
    if code:
        save_pending_code(code)       # 2 分钟内必须换掉，建议直接同步换
        exchange_code(code)           # 见 3.2
    elif request.args.get("message"):
        handle_subscribe_message(request.args["message"])  # urldecode + AES(client_secret) 解密
    return "success"
```
⚠ 文档未说明回调需要返回什么内容；上例返回 `success` 只是保守写法。GBK 编码下 Flask 默认按 UTF-8 解析 query，code 是纯 ASCII 不受影响，含中文的字段需要自己按 GBK 解码原始 query。

### 3.2 用 code 换 token

**Endpoint**: `POST https://open.youzanyun.com/auth/token`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| client_id | String | 是 | 应用 ID |
| client_secret | String | 是 | 应用 secret |
| authorize_type | String | 是 | 固定 `"authorization_code"` |
| code | String | 是 | 订购授权后推送的 code |

```bash
curl -X POST 'https://open.youzanyun.com/auth/token' -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$YOUZAN_CLIENT_ID\",\"client_secret\":\"$YOUZAN_CLIENT_SECRET\",\"authorize_type\":\"authorization_code\",\"code\":\"$CODE\"}"
```
响应 `data` 多一个 `refresh_token`（28 天）。Node SDK 示例还传了 `redirect_uri`，参数表里没有 → ⚠ 文档未说明。

### 3.3 用 refresh_token 刷新

参数表里没有列出，只在示例里出现（49281、FxLS 页）：
```json
{"client_id": "...", "client_secret": "...", "authorize_type": "refresh_token", "refresh_token": "..."}
```
- 刷新后得到新的 access_token（7 天）和新的 refresh_token（28 天）。
- 旧凭证何时失效：49281 说上一个 refresh_token 立即失效；3982 说旧 access_token 和 refresh_token 同时失效；5172 说旧 access_token 还能用 1 小时 → ⚠ 文档自相矛盾。**无论如何都要原子地保存新的 refresh_token**，否则下一次刷新会拿着失效的 refresh_token。
- 商家订购到期 → 授权关系失效，token 刷不出来（`1004 授权关系已过期`），只能等商家续订后重新推送 code。

## 4. 调业务 API 的统一格式

文档（API 调用页）：所有 API 用 HTTPS、POST、JSON、UTF-8。

```
POST https://open.youzanyun.com/api/{api_name}/{api_version}?access_token={token}
Content-Type: application/json

{业务参数 JSON}
```

- API 靠**名称 + 版本号**定位，例如 `youzan.trade.get` + `4.0.2` → `/api/youzan.trade.get/4.0.2`。文档里写成 `youzan.trade.get.4.0.2` 的，最后三段是版本号，拼 URL 时要拆开。
- 同一个 API 名有多个版本，字段可能不同；**以你调用的那个版本的文档为准**，不要混用。
- 无凭证探测（2026-09-11，×2）：
  - 缺版本号 `/api/youzan.item.detail.get?access_token=...` → `{"gw_err_resp":{"err_msg":"非法请求地址","err_code":4001}}`
  - 名称或版本不存在（`youzan.trade.get/9.9.9`）→ `4005 非法的API`，**先于 token 校验**
  - token 放 `Authorization: Bearer ...` 头、URL 不带 → `4201 非法的请求凭证`（等同没传）
  - token 放 JSON body → `4201`
  - URL 不带 token → `4201`；URL 带伪造 token → `4203`，`err_msg` 为 “Token 不存在”
  - `Content-Type: text/plain` → `4007 非法的请求姿势，httpMethod:POST, contentType:text/plain`
  - `http://` → `301` 跳转到 `https://`
  - 以上错误的 HTTP 状态码都是 200。
- 文档 4007 行说 GET / POST 都支持，POST 支持 `application/json`、`application/x-www-form-urlencoded`、`multipart/form-data`。无凭证探测（单次）：GET + query 参数能走到鉴权层（返回 4203）。业务参数一律建议 POST JSON。
- 免鉴权接口路径格式是 `/api/auth_exempt/{api_name}/{api_version}`（错误码 4001 行原文）。
- 老开放平台 `https://open.youzan.com/` 的 token / SDK 和有赞云不通用（FAQ 3899、4811）。

```python
API_BASE = "https://open.youzanyun.com/api"

def call_api(api: str, version: str, params: dict, token: str) -> dict:
    r = requests.post(f"{API_BASE}/{api}/{version}",
                      params={"access_token": token},      # 只能放 query
                      json=params, timeout=10)             # 文档：接口 5 秒超时
    r.raise_for_status()
    body = r.json()
    if "gw_err_resp" in body:                              # 网关层错误（无凭证探测证实的结构）
        err = body["gw_err_resp"]
        raise YouzanError(err.get("err_code"), err.get("err_msg"), err.get("trace_id"))
    if body.get("success") is False or body.get("code") not in (200, None):
        raise YouzanError(body.get("code"), body.get("message"), body.get("trace_id"))
    return body.get("data")
```
更完整的错误分类与重试见 `errors-and-limits.md`。

## 5. token 缓存与刷新（Python）

规则（文档原文）：7 天有效；必须缓存，频繁获取会被限流；多店铺授权同一应用时各店 token 独立，**缓存键要带 kdt_id**；token 维度是「应用 + 店铺」，同一店铺授权给有容器和无容器两个应用，得到的是两个互不冲突的 token（FAQ 3905）。

```python
import json, os, time, threading, requests
AUTH_URL = "https://open.youzanyun.com/auth/token"
_lock = threading.Lock()
_cache: dict[str, dict] = {}          # 生产环境换成 Redis / DB，键 = f"{client_id}:{kdt_id}"

def _request_token(payload: dict) -> dict:
    r = requests.post(AUTH_URL, json=payload, timeout=10)
    r.raise_for_status()
    body = r.json()
    if not body.get("success") or body.get("code") != 200:
        raise RuntimeError(f"auth/token {body.get('code')}: {body.get('message')}")
    return body["data"]

def get_self_token(kdt_id: str, force_refresh: bool = False) -> str:
    """自用型：按店铺缓存；离过期不足 1 天时主动 refresh。"""
    key = f"{os.environ['YOUZAN_CLIENT_ID']}:{kdt_id}"
    with _lock:
        item = _cache.get(key)
        now_ms = int(time.time() * 1000)
        if item and not force_refresh and item["expires"] - now_ms > 24 * 3600 * 1000:
            return item["access_token"]
        data = _request_token({
            "client_id": os.environ["YOUZAN_CLIENT_ID"],
            "client_secret": os.environ["YOUZAN_CLIENT_SECRET"],
            "authorize_type": "silent",
            "grant_id": str(kdt_id),
            "refresh": bool(item) and (force_refresh or item["expires"] - now_ms <= 24 * 3600 * 1000),
        })
        _cache[key] = {"access_token": data["access_token"], "expires": int(data["expires"])}
        return data["access_token"]
```
- 调业务 API 收到 `4202 请求凭证过期` / `4203` / `4201` 时：强制刷新一次再重试一次；仍失败就停止并告警（很可能是授权被解除或订购到期），不要死循环刷新。
- 工具型把 `refresh_token` 一起存；刷新成功后**先写库再返回**。

## 6. 多店铺、IP 白名单、能力包

- **多店铺**：同一认证主体的多个店铺可以共用一个自用型应用，每个店铺用自己的 kdt_id 换各自的 token（FAQ 5193）；主体不同要分别建应用。
- **IP 白名单**（无容器应用）：只能从 llms.txt 摘要拿到要点——仅支持 IPv4 / IPv6、不支持通配符、最多 64 条、2023-07-10 后创建的应用默认启用；正文页 `resource/doc/7555` 抓取时返回 500 壳页，⚠ 其余细节文档未能获取。
  未配置时的报错（FAQ 6241 示例，文档原文，未实测）：
  `{"gw_err_resp":{"trace_id":"...","err_msg":"源IP地址<redacted>非法调用有赞云，请完成IP地址确认后，前往应用中心控制台进行IP白名单配置","err_code":4007}}`
  注意它和“Content-Type 不对”共用 4007，要看 err_msg。另外配置时间要早于请求时间。
- **能力包**：每个 API / 消息属于某个能力包，文档页底部“如何获得此API权限”列出。没申请 → `4204 无权限访问`。工具型新增能力包只自动授予**新订购**的商家，老商家要在“授权管理”触发通知并由商家确认（4029、47374）。
- **计费**：大多数 API 文档标“是否计费：计费”，调用消耗月度额度；欠费会被限流或停用（见 `errors-and-limits.md`）。

## 7. 有容器应用与“免鉴权”SDK

- 有容器 Java 用注入的 `BifrostService.invoke(api对象, new Token(token), 结果类)`，**不要用 `DefaultYZClient`**，否则会 connect timed out（FAQ 3435、3427）。
- 有容器应用和云函数可以用“免鉴权 SDK”（Java `cloud-component-autoauth` 的 `AutoAuthYzService`、Node `youzanyun-sdk-nodejs` 的 `sdk.callApi({api, version, params, kdtId})`），平台托管 token；**无容器应用不支持**。
- 官方 Java / PHP / Node SDK 需先在控制台申请 API 权限后“打包下载”（资料包，本 skill 未下载，SDK 细节未核实）。无容器项目直接按第 4 节发 HTTP 即可。

## 8. 获取 token 的错误码（文档原文，未实测，除非另注）

| code | message | 场景 / 处理 |
|---|---|---|
| 1000 | 应用信息错误 | client_secret 不正确。无凭证探测（单次）：Content-Type 不是 JSON 也返回 1000，看 message 区分 |
| 1004 | 授权关系已过期 | 工具型订购到期或授权失效，控制台“授权管理”看授权时间 |
| 1005 | 非法授权码 | code 超过 2 分钟或已被使用 |
| 1103 | Client 不存在 | client_id 不对。无凭证探测（×2）：`client_id=test` → HTTP 200 + `{"success":false,"code":1103,"data":null,"message":"Client 不存在"}` |
| 1103 | 授权关系不存在 | grant_id 没传对 / 店铺没授权给该应用 |
| 1103 | 授权应用不匹配 | A 应用的 code 拿去用 B 应用的 client_id / secret 换 |
| 1105 | 不支持的应用类型 | 工具型用了 silent（或反之） |

同一个 1103 对应三种原因，**要看 message**，不要只按 code 分支。

## 9. ⚠ 本文件的文档矛盾 / 未说明

- 自用型 `refresh=true` 后旧 token “1 小时后失效” vs “立即失效” → ⚠ 文档自相矛盾（F4cU / 3031 / 5172 vs 49259 / 49275）
- 工具型刷新后旧 access_token 是否仍可用 1 小时 → ⚠ 文档自相矛盾（3982 vs 5172）
- 自用型响应是否含 `refresh_token` → ⚠ 文档自相矛盾（49259 vs IO94 / 3031）
- `refresh` 传字符串 `"false"` 是否被接受 → ⚠ 文档未说明（示例与参数表类型不一致）
- `authorize_type: "refresh_token"` 与 `refresh_token` 参数不在参数表中，只在示例里出现 → ⚠ 文档未说明
- Node SDK 示例的 `redirect_uri`；示例里 `refresh: fasle` 拼写错误 → ⚠ 文档未说明 / 示例有误
- 工具型回调应返回什么内容；订购消息 AES 解密的具体算法（在 zip demo 里） → ⚠ 文档未说明
- IP 白名单正文页不可得 → ⚠ 文档未说明（仅摘要）
