# 鉴权与网关：数据中心域名 → access_token → 业务接口

> 来源：open.yonyoucloud.com 文档中心「开放平台接入文档」（抓取于 2026-09-11）+ 官方 gitee 示例仓库
> `yycloudopen/corp-demo`、`yycloudopen/isv-demo` 的 README（网页直接浏览，未下载任何包）。
> 所有返回示例与报错说明均为**文档原文，未实测**；标「无凭证探测（2026-09-11）」的是用伪造参数打出来的真实返回，
> 命令见 `yonyou-workspace/probe-log.md`。

## 目录

1. 调用链总览
2. 第一步：查租户所在数据中心的网关域名
3. 第二步（企业自建应用）：获取 access_token
4. 第二步（ISV / 生态应用）：获取 access_token
5. 第三步：调用业务接口
6. 官方 SDK
7. 无凭证探测结果
8. 本文件的 ⚠ 汇总

---

## 1. 调用链总览

YonBIP 公有云是多数据中心部署，**每个数据中心有独立的一套开放平台**。文档原文：
「开发者调用开放平台接口，就需要先获取到租户所在数据中心的核心网关域名和 auth 域名，其中 auth 域名用于调用
【获取 access_token】接口，核心网关域名用于调用业务接口。」

```
tenantId ──► GET {数据中心查询}/open-auth/dataCenter/getGatewayAddress?tenantId=…
              └─► data.tokenUrl   （auth 域名，如 https://yonbip.diwork.com/iuap-api-auth）
              └─► data.gatewayUrl （核心网关，如 https://yonbip.diwork.com/iuap-api-gateway）
appKey/appSecret ──► GET {tokenUrl}/open-auth/selfAppAuth/base/v1/getAccessToken?appKey&timestamp&signature
              └─► data.access_token（2 小时）
业务调用 ──► {gatewayUrl}/yonbip/<业务路径>?access_token=…
```

凭证从哪来：租户管理员在工作台「数字化建模 → 系统管理 → 我的应用」建自建应用（或「云平台 → 连接集成服务 →
API 管理 → API 调用」新增授权 key），再在「开放平台 → API 授权」里勾选**末级 API 分类**，此时生成 `appKey` /
`appSecret`。**没授权的 API 分类调用会报 `310037 API未被授权`**（文档原文，未实测）。

环境变量约定（本 skill 所有示例都用）：`YONBIP_TENANT_ID`、`YONBIP_APP_KEY`、`YONBIP_APP_SECRET`，
以及缓存下来的 `YONBIP_TOKEN_URL`、`YONBIP_GATEWAY_URL`。

---

## 2. 第一步：查租户所在数据中心的网关域名

**Endpoint**: `GET https://apigateway.yonyoucloud.com/open-auth/dataCenter/getGatewayAddress?tenantId=<租户ID>`
**用途**: 用租户 ID 换出该租户所在数据中心的 `tokenUrl` 和 `gatewayUrl`。不需要 token。

> 域名来源：文档页只写占位符 `${apiauth}/open-auth/dataCenter/getGatewayAddress`；
> 具体主机 `https://apigateway.yonyoucloud.com` 取自官方 corp-demo / isv-demo README
> （「适配之后需要通过租户来获取（https://apigateway.yonyoucloud.com/open-auth/dataCenter/getGatewayAddress?tenantId=*****）」）。
> 无凭证探测（2026-09-11）：该主机该路径在线，伪造 `tenantId=test` 返回 JSON（见 §7 P1）。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| tenantId | string | 是 | 租户 ID。自建应用在工作台可查看；ISV 应用从应用 URL 中获取（文档「常用字段说明」） |

**示例请求**

```bash
curl -sS "https://apigateway.yonyoucloud.com/open-auth/dataCenter/getGatewayAddress?tenantId=$YONBIP_TENANT_ID"
```

```python
import os, requests
r = requests.get("https://apigateway.yonyoucloud.com/open-auth/dataCenter/getGatewayAddress",
                 params={"tenantId": os.environ["YONBIP_TENANT_ID"]}, timeout=10)
body = r.json()
if body.get("code") != "00000":
    raise RuntimeError(f"查网关失败: {body}")
token_url, gateway_url = body["data"]["tokenUrl"], body["data"]["gatewayUrl"]
```

**示例响应**（文档原文，未实测）

```json
{
  "code": "00000",
  "message": "成功！",
  "data": {
    "gatewayUrl": "https://yonbip.diwork.com/iuap-api-gateway",
    "tokenUrl": "https://yonbip.diwork.com/iuap-api-auth"
  }
}
```

**注意事项**

- 成功码是字符串 `"00000"`，不是 `200`。
- 返回的两个域名**已经带了路径前缀**（`/iuap-api-auth`、`/iuap-api-gateway`），后面直接拼 `/open-auth/…` 或 `/yonbip/…`。
- 结果按租户稳定，可以缓存；⚠ 文档未说明多久会变、要不要定期刷新。
- 无凭证探测（2026-09-11）：伪造 tenantId 时返回 HTTP 200 +
  `{"code":"500","message":"根据租户id获取网关地址出现异常"}`——错误码同样是字符串，且不是文档里任何一张码表。
- 老博客里的 `https://api.diwork.com` 是 README 所说「多数据中心适配之前」的 tokenUrl，新代码不要写死。

---

## 3. 第二步（企业自建应用）：获取 access_token

**Endpoint**: `GET {tokenUrl}/open-auth/selfAppAuth/base/v1/getAccessToken`
**用途**: 用 appKey + 签名换接口令牌，有效期 2 小时。

> 路径沿革（文档原文）：2023-07-21 起「自建应用获取 token，路径从 `/iuap-api-auth/open-auth/selfAppAuth/getAccessToken`
> 改为 `/iuap-api-auth/open-auth/selfAppAuth/base/v1/getAccessToken`」，参数不变。`tokenUrl` 已含 `/iuap-api-auth`，
> 所以拼接时只加 `/open-auth/selfAppAuth/base/v1/getAccessToken`。

**关键参数**（全部走 query string）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| appKey | string | 是 | 应用 appKey |
| timestamp | number(long) | 是 | Unix **毫秒**时间戳（文档原文「unix timestamp, 毫秒时间戳」） |
| signature | string | 是 | 签名，见下 |

### 3.1 签名算法（逐步）

文档原文：`URLEncode( Base64( HmacSHA256( parameterMap ) ) )`，「parameterMap 按照参数名称排序，参数名称与参数值依次拼接
(signature 字段除外)」，「Hmac 的 key 为自建应用的 appSecret」。

1. 取除 `signature` 外的全部参数：`appKey`、`timestamp`。
2. 按参数名升序排序（`appKey` < `timestamp`）。
3. 依次拼接「名 + 值」，中间**没有** `=`、`&` 或任何分隔符：
   `appKey41832a3d2df94989b500da6a22268747timestamp1568098531823`（文档原文示例）。
4. 以 `appSecret` 为 key 做 HmacSHA256，得到 32 字节二进制摘要（**不是** hex 字符串）。
5. 对二进制摘要做标准 Base64（含 `+ / =`）。
6. 对 Base64 结果做**一次** URL 编码后放进 query。文档里的例子 `signature=5emnxzmPp%2FCFvb2hcddwtMVgfKUARq9DGQZOjxqe%2Fp8%3D`
   可见 `/`→`%2F`、`=`→`%3D`。

**示例请求**

```bash
TS=$(python3 -c 'import time; print(int(time.time()*1000))')
SIG=$(printf 'appKey%stimestamp%s' "$YONBIP_APP_KEY" "$TS" \
      | openssl dgst -sha256 -hmac "$YONBIP_APP_SECRET" -binary | base64 \
      | python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read().strip(), safe=""))')
curl -sS "$YONBIP_TOKEN_URL/open-auth/selfAppAuth/base/v1/getAccessToken?appKey=$YONBIP_APP_KEY&timestamp=$TS&signature=$SIG"
```

```python
import base64, hashlib, hmac, os, time, requests

def yonbip_sign(params: dict, secret: str) -> str:
    """返回原始 Base64 签名（尚未 URL 编码）。"""
    plain = "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(secret.encode("utf-8"), plain.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")

def get_self_app_token(token_url: str) -> dict:
    params = {"appKey": os.environ["YONBIP_APP_KEY"], "timestamp": str(int(time.time() * 1000))}
    params["signature"] = yonbip_sign(params, os.environ["YONBIP_APP_SECRET"])
    # requests 会对 params 做且只做一次 URL 编码（/→%2F, +→%2B, =→%3D），所以这里传原始 Base64
    r = requests.get(f"{token_url}/open-auth/selfAppAuth/base/v1/getAccessToken", params=params, timeout=10)
    body = r.json()
    if body.get("code") != "00000":
        raise RuntimeError(f"取 token 失败: {body}")
    return body["data"]          # {"access_token": "...", "expire": 7200}
```

**示例响应**（文档原文，未实测）

```json
{"code": "00000", "message": "成功！", "data": {"access_token": "b8743244c5b44b8fb1e52a55be7e2f", "expire": 7200}}
```

**注意事项**

- **URL 编码只做一次**。用 `requests` 的 `params=` 时传原始 Base64；自己拼 URL 时才 `quote(sig, safe="")`。
  先 `quote` 再交给 `params=` 会被编码两次（`%2F` 变 `%252F`）。⚠ 文档未说明服务端对二次编码 / 未编码的容忍度。
- Python 的 `urllib.parse.quote` 默认 `safe="/"`，**不会**编码 `/`，和文档示例（`%2F`）不一致——显式传 `safe=""`。
- ⚠ 文档自相矛盾：参数表写毫秒时间戳，官方 isv-demo README 里的 Python 示例用的是 `int(time.time())`（秒），
  而且那段示例漏了 `import hashlib`。按参数表用毫秒；⚠ 文档未说明时间戳容忍窗口。
- `data.expire` 单位是秒（7200）。**缓存 token，过期前刷新**，不要每次业务调用都重新签名取 token。
- 文档原文：「新版本获取的 token 会比较长，并且包含特殊字符，请在使用新 token 调用 openApi 时候对 token 进行 encode 编码」。
  见 §5。
- 文档原文：「改造后……请注意保持 header 中的 ContentType 是 application/json」「请使用 UTF-8」。GET 请求也带上无妨。
- Java 常见坑（文档原文）：IBM JDK 的 `sun.misc.BASE64Encoder` 与 `java.util.Base64` 不互通，改用
  `org.apache.commons.codec.binary.Base64` 或 `java.util.Base64`。

---

## 4. 第二步（ISV / 生态应用）：获取 access_token

**Endpoint**: `GET {tokenUrl}/open-auth/suiteApp/base/v1/getAccessToken`
**用途**: ISV 用 suiteKey 给**某个购买了应用的租户**换 token。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| suiteKey | string | 是 | 生态应用的 appKey |
| tenantId | string | 是 | 购买者租户的 tenantId |
| timestamp | string | 是 | 时间戳（⚠ 本页类型写 string、未写单位；自建应用页写毫秒 long） |
| signature | string | 是 | 同 §3.1，参与签名的是 `suiteKey`、`tenantId`、`timestamp`（按名排序），Hmac key 为 `suiteSecret` |

待签串形如 `suiteKey<值>tenantId<值>timestamp<值>`。

**注意事项**

- ⚠ 文档自相矛盾：ISV 的「获取接口令牌 access_token」页仍写旧路径 `/open-auth/suiteApp/getAccessToken`；
  自建应用页的「2023-07-21 地址调整说明」写生态应用已改为 `/open-auth/suiteApp/base/v1/getAccessToken`。优先用 base/v1。
- 老流程还要 `suiteTicket`：开放平台向套件回调地址推送 `SUITE_TICKET` 事件（加密格式同事件推送，见 `events.md`），
  isv-demo README 的旧 token 示例带 `suiteTicket` 参数。Java SDK 注释：「如果是新的生态应用，suiteTicket 可以传入 null 值或者空字符串」。
  ⚠ 文档未说明新旧生态应用如何区分。
- 调用本接口前同样要先按**购买者租户**查 §2 的 tokenUrl。

---

## 5. 第三步：调用业务接口

**Endpoint 形态**: `{gatewayUrl}/yonbip/<业务路径>?access_token=<token>`
**用途**: 所有业务 OpenAPI。

文档原文（「业务接口调用开发」）：「调用用友开放平台接口时，需使用 HTTPS 协议、JSON 数据格式、UTF8 编码……
POST 请求请在 HTTP Header 中设置 Content-Type：application/json……要求访问接口的请求地址中必须携带访问令牌 access_token 参数」。

```bash
curl -sS -X POST "$YONBIP_GATEWAY_URL/yonbip/digitalModel/vendor/list?access_token=$(python3 -c 'import os,urllib.parse;print(urllib.parse.quote(os.environ["YONBIP_TOKEN"],safe=""))')" \
  -H 'Content-Type: application/json' \
  -d '{"pageIndex":1,"pageSize":10}'
```

```python
import requests

class YonBIP:
    def __init__(self, gateway_url: str, token_provider):
        self.gw, self.token = gateway_url.rstrip("/"), token_provider   # token_provider() 返回缓存中的有效 token

    def call(self, method: str, path: str, *, query=None, body=None) -> dict:
        q = dict(query or {}); q["access_token"] = self.token()        # 由 requests 负责编码
        r = requests.request(method, f"{self.gw}{path}", params=q, json=body, timeout=35)
        try:
            data = r.json()
        except ValueError:                                              # 见 errors-and-limits.md：有接口返回纯文本
            raise RuntimeError(f"HTTP {r.status_code} 非 JSON: {r.text[:200]}")
        if str(data.get("code")) != "200":
            raise RuntimeError(f"YonBIP 调用失败: {data}")
        return data
```

**注意事项**

- token 放 **URL query**，参数名 `access_token`；文档没有给任何 header 方式（⚠ 文档未说明 header 传 token 是否被接受）。
- GET 接口（如各种 `detail`）的业务参数也放 query：`?access_token=…&id=…`。
- 每个 API 的超时配置在 API 详情 JSON 的 `timeOut` 字段里（本 skill 覆盖的接口多为 30 秒，客户档案列表为 10 秒）。
- 业务接口的请求/返回结构、成功判定见各 reference 与 `errors-and-limits.md`。
- 2026-03-27 公告：YonBIP 公有云所有 OpenAPI 端点禁用 TLS 1.0/1.1，最低 TLS 1.2；JDK7 以下需升级。

---

## 6. 官方 SDK

文档「SDK 使用说明」提供三种 SDK，内置签名：

| 语言 | 获取方式（文档原文） | 入口 |
| --- | --- | --- |
| Java 8+ | 下载 jar 放 `lib/` 并 `<scope>system</scope>` 引用，或连用友 maven 库：`com.yonyou.iuap:yonbip-open-api-sdk:1.0.0-RELEASE` | `OpenServiceBuilder().setAppKey().setAppSecret().setEnv(域名)` + `InputParam().setUrl("/yonbip/…").setBody(map).setMethod("POST")`，`Invoke.getResult(...)`；生态应用 `Invoke.getEcoResult(builder, param, tenantId, suiteTicket)` |
| Go 1.17.7+ | `require gitee.com/yycloudopen/yonyou-openapi-sdk v1.0.0` | `openSdk.OptSelfRequest(...)`、`OptSuiteRequest(...)`；事件解密 `eventSdk.DecryptEventEncrypt(secret, holder)` |
| Python 3 | 「先到 yonbip 下载 whl 包」，`pip install xxxx.whl` | `from yonbip_open_api_sdk import request_opt, token_opt`：`request_opt.opt_self_app_request("post", data_url, header, json.dumps(data), params, token_info)`、`token_opt.opt_self_token(app_key, app_secret, host_url)`；事件 `from yonbip_open_event_sdk.event_opt import decrypt_event_encrypt` |

**注意事项**

- SDK 示例的 `setEnv` / `host_url` 传的是「统一域名」（示例值 `https://bip-daily.yyuap.com`，明显是日常测试环境）。
  ⚠ 文档未说明 SDK 是否内部调用 §2 查数据中心，也未说明生产环境该传什么——拿到凭证后先验证（见 verification-plan）。
- Python whl 不在 PyPI，要从用友处下载；本 skill 未下载、未看过其源码。不能引第三方包时按 §3 自己实现签名即可，算法只有十几行。

---

## 7. 无凭证探测结果

以下每条都复跑两次、结果一致（完整命令见 `yonyou-workspace/probe-log.md`，均为伪造值，未用任何真实凭证）：

| # | 请求 | HTTP | 响应 |
| --- | --- | --- | --- |
| P1 | `GET apigateway.yonyoucloud.com/open-auth/dataCenter/getGatewayAddress?tenantId=test` | 200 | `{"code":"500","message":"根据租户id获取网关地址出现异常"}` |
| P2 | `GET api.diwork.com/open-auth/selfAppAuth/base/v1/getAccessToken?appKey=test&timestamp=<当前毫秒>&signature=<用 "test" 算的签名>` | 200 | `{"code":"10018","message":"应用不存在或appKey已停用"}` |
| P2 | 同上，旧路径 `…/selfAppAuth/getAccessToken` | 200 | 同上 `10018`——旧路径仍在线 |
| P2 | 同上，主机换成 `c2.yonyoucloud.com/iuap-api-auth`（base/v1） | 200 | 同上 `10018` |
| P3 | `POST c2.yonyoucloud.com/iuap-api-gateway/yonbip/digitalModel/vendor/list`，不带 access_token | 200 | `{"code":"310001","message":"access_token不能为空。"}` |
| P4 | 同上，`?access_token=test` | 200 | `{"code":"310036","message":"非法token"}` |
| P5 | `POST …/iuap-api-gateway/yonbip/skillify/not/exist?access_token=test` | **404** | `{"code":"310404","message":"网关上没有注册此API[/yonbip/skillify/not/exist]，请确认后重新调用"}` |

由此可见（只陈述观察到的）：

1. 鉴权失败不走 HTTP 4xx：token 缺失 / 非法都是 HTTP 200，错误在 body 的 `code`（**字符串**）里。
2. 网关先判路径再判 token：未注册路径即使带假 token 也返回 `310404` + HTTP 404。可以用假 token 无副作用地确认一个路径是否存在。
3. token 服务的错误码 `10018` 不在文档「返回码说明」任何一张表里（⚠ 文档未说明 token 接口的错误码表）。
4. `c2.yonyoucloud.com` 取自 API 文档详情 JSON 的 `address` 字段，是某个数据中心的网关；**你的租户未必在这里**，生产仍须走 §2。

---

## 8. 本文件的 ⚠ 汇总

- ⚠ 文档自相矛盾：timestamp 毫秒（参数表）vs 秒（isv-demo README 的 Python 示例）——§3
- ⚠ 文档自相矛盾：生态应用 token 路径，ISV 页写旧路径，自建页调整说明写 base/v1——§4
- ⚠ 文档自相矛盾：ISV 页 timestamp 类型 string，自建页 number long——§4
- ⚠ 文档未说明：数据中心结果缓存多久、时间戳容忍窗口、签名二次编码是否容忍、token 能否放 header——§2 §3 §5
- ⚠ 文档未说明：token 接口错误码表（探测到 `10018`）、查网关接口错误码（探测到 `"500"`）——§7
- ⚠ 文档未说明：SDK 的 env 生产取值、是否内置数据中心查询；新旧生态应用 suiteTicket 的区分——§4 §6
