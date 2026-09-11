# 鉴权与连接：第三方系统登录授权签名、会话登录、SDK 初始化

> 来源：官方 Python SDK `kingdee.cdp.webapi.sdk` 8.2.0（PyPI，Homepage `https://open.kingdee.com`，import 名 `k3cloud_webapi_sdk`）源码；
> `https://open.kingdee.com/k3cloud/open/ApiCenterReportDetail.aspx`（SDK 介绍，更新时间 2020-11-05）；
> 各表单操作说明中的「登录（ValidateUser）」（API 版本 7.5.1800.6）。抓取于 2026-09-11。
> **签名算法是按 SDK 源码逐行转写的，未用真实凭证验证；网关行为来自无凭证探测（2026-09-11）。**

## 目录

1. 先弄清你连的是哪台服务器
2. 两种鉴权方式怎么选
3. 第三方系统登录授权：拿到哪些参数
4. 用官方 Python SDK（推荐）
5. 不用 SDK：签名算法逐步拆解
6. `kd_sign.py`：给 curl / 其他语言用的签名辅助脚本
7. 会话登录 ValidateUser（旧方式）
8. 数据中心列表 GetDataCenterList
9. 无凭证探测结果
10. 常见错误对照

---

## 1. 先弄清你连的是哪台服务器

- 金蝶云星空 WebAPI **跑在客户自己的星空站点上**（私有部署或金蝶公有云租户），地址形如 `http(s)://<客户域名>/k3cloud/`。
  **没有一个所有客户共用的 `api.kingdee.com` 业务地址**——`open.kingdee.com` 是开放平台（文档 / 授权），不是 API 服务器。
- 所有接口的 URL 都是：`POST {ServerUrl}/{ServiceName}.common.kdsvc`，body 为 JSON，`Content-Type: application/json`。
  SDK：ServerUrl 以 `/` 结尾就直接拼，否则补一个 `/`。
- SDK 8.2.0 源码注释：「取消默认旧网关，要求必须输入url by Ann 2025-01-15」。旧版 SDK 的默认地址
  `https://api.kingdee.com/galaxyapi/` 被注释掉了；8.2.0 里 `server_url` 为空直接抛 `RuntimeError('ServerUrl is required')`。
  **别从老博客里抄 galaxyapi 地址当默认值。**
- 前置条件（SDK 介绍页原文）：星空产品必须升级到 **PT136657【7.3.1310.2】及以上**，并且配置新版「第三方系统登录授权」，SDK 才能用。

## 2. 两种鉴权方式怎么选

| | 第三方系统登录授权（签名） | 会话登录（ValidateUser + Cookie） |
| --- | --- | --- |
| 凭证 | 账套 ID + 集成用户名 + AppID + AppSecret | 账套 ID + 用户名 + **密码** |
| 每个请求 | 都带一组签名头（见第 5 节），不需要先"登录" | 先调登录接口拿会话 Cookie，后续请求带 Cookie |
| 官方态度 | SDK 介绍页与所有代码示例都用这个；示例注释「此处不再使用参数形式传入用户名及密码等敏感信息，改为在登录配置文件中设置」 | 文档页的操作列表里 **ValidateUser 被前端代码刻意隐藏**（`if (OperaNumber == "ValidateUser") //屏蔽登录操作按钮`） |
| 用于 | 新对接一律用它 | 维护老代码 / 老版本服务器 |

**结论：新代码用第三方授权签名；最省事的是直接用官方 SDK，不要自己手搓签名。**

## 3. 第三方系统登录授权：拿到哪些参数

操作流程（SDK 介绍页原文要点）：
1. 以管理员 `Administrator` 登录金蝶云星空，进入「系统管理 → 第三方系统登录授权」。
2. 点「新增」，新增一个第三方系统登录授权信息（页面上的「获取应用ID」会跳到 open.kingdee.com 生成）。
3. 点「生成测试链接」验证授权是否成功。
4. 把生成的应用 ID、应用名称、应用密钥、集成用户名称填进项目配置。

| 配置项（SDK conf.ini / kdwebapi.properties，参数名不区分大小写） | 含义 | 本 skill 示例用的环境变量 |
| --- | --- | --- |
| `X-KDApi-AcctID` | 账套 ID（**即数据中心 ID**，不是账套名称） | `KD_ACCT_ID` |
| `X-KDApi-UserName` | 授权的集成用户 | `KD_USERNAME` |
| `X-KDApi-AppID` | 应用 ID，形如 `<clientId>_<32位字符>`（SDK 按 `_` 拆两段） | `KD_APP_ID` |
| `X-KDApi-AppSec` | 应用密钥 | `KD_APP_SECRET` |
| `X-KDApi-ServerUrl` | 星空站点地址（Java 配置示例有此项，Python conf.ini 示例没有，但 8.2.0 必填） | `KD_SERVER_URL` |
| `X-KDApi-LCID` | 账套语系，默认 **2052** | `KD_LCID` |
| `X-KDApi-OrgNum` | 组织编码，「启用多组织时配置对应的组织编码才有效」，默认 0 | `KD_ORG_NUM` |
| `X-KDApi-Proxy` | 代理（仅 Python 配置示例有） | — |
| `x-kdapi-secpwd` | 可选，覆盖 AppSecret 解码用的种子（见第 5 节），SDK 源码里有，文档未提 ⚠ | `KD_SECPWD` |
| `x-kdapi-connecttimeout` / `x-kdapi-requesttimeout` | 超时秒数，默认 120（SDK 源码） | — |

- 这些 `X-KDApi-*` 是**配置文件里的键名**，不是 HTTP 请求头！真正发出去的请求头是第 5 节那一套 `X-Api-*` / `X-Kd-*`。
  直接把 `X-KDApi-AppID: ...` 当 header 发出去是常见误写。
- AppID 的第二段在签名中会被「解码」后当 HMAC 密钥用，AppSecret 另外用于第二个签名——两个密钥用途不同。

## 4. 用官方 Python SDK（推荐）

```bash
pip install kingdee.cdp.webapi.sdk      # PyPI 包名；import 名是 k3cloud_webapi_sdk
```

PyPI 描述里写的安装命令是 `pip install k3cloud_webapi_sdk`，SDK 介绍页写的是 `pip install <本地 whl 路径>`（资料包里的 whl）。
PyPI 上的项目名是 `kingdee.cdp.webapi.sdk`（当前 8.2.0）⚠ 三处说法不一，以能装上的为准，import 名都是 `k3cloud_webapi_sdk`。

```python
import json, os
from k3cloud_webapi_sdk.main import K3CloudApiSdk

sdk = K3CloudApiSdk(os.environ["KD_SERVER_URL"], timeout=120)   # 构造函数必须给 ServerUrl
sdk.InitConfig(
    acct_id=os.environ["KD_ACCT_ID"],
    user_name=os.environ["KD_USERNAME"],
    app_id=os.environ["KD_APP_ID"],
    app_secret=os.environ["KD_APP_SECRET"],
    server_url=os.environ["KD_SERVER_URL"],   # 这里也要给，空串会抛 ServerUrl is required
    lcid=int(os.environ.get("KD_LCID", 2052)),
    org_num=int(os.environ.get("KD_ORG_NUM", 0)),
)
rows = json.loads(sdk.ExecuteBillQuery({"FormId": "BD_MATERIAL", "FieldKeys": "FNumber,FName", "Limit": 10}))
```

也可以用配置文件：`sdk = K3CloudApiSdk(server_url); sdk.Init(config_path="conf.ini", config_node="config")`，
conf.ini 里是 `[config]` 节 + 上表的 `X-KDApi-*` 键。

**SDK 行为要点（源码）**
- 所有方法返回的是**响应文本字符串**，自己 `json.loads`。
- 缺账套 ID / 用户 / 应用 ID / 应用密钥时，`IsValid()` 只 `print('SDK初始化失败，缺少必填授权项：...')`，不抛异常；
  之后调用任何接口，`Execute()` **返回**（不是抛出）一个 `RuntimeError('拒绝请求，请先正确初始化!')` 对象——
  你的 `json.loads(...)` 会报 `TypeError`，看起来和鉴权无关。初始化后先检查 `sdk.initialize is True`。
- 响应 HTTP 状态是 200 或 206 时，SDK 读取 `kdservice-sessionid` Cookie 并保存全部 Set-Cookie，后续请求自动带上；其他状态码直接抛 `RuntimeError(响应文本)`。
- 响应文本以 `response_error:` 开头时抛 `RuntimeError`（详见 [`errors-and-responses.md`](errors-and-responses.md)）。
- `verify=False`：SDK 关闭了 HTTPS 证书校验并屏蔽了警告。生产环境要校验证书就不能直接用 SDK 的 `PostJson`。
- SDK 请求头里的 User-Agent 是 `Kingdee/Python WebApi SDK 7.3 (...)`，与包版本号 8.2.0 不一致，无需在意。

## 5. 不用 SDK：签名算法逐步拆解

以下完全按 SDK 8.2.0 `WebApiClient.BuildHeader()` 转写。输入：完整请求 URL、AcctID、UserName、AppID、AppSecret、LCID、OrgNum。

**第 1 步：待签路径**
取 URL 里域名之后的路径（SDK：从第 10 个字符之后找第一个 `/`），做 UTF-8 URL 编码，**再把 `/` 也替换成 `%2F`**：

```
/k3cloud/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc
→ %2Fk3cloud%2FKingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc
```

**第 2 步：时间戳与 nonce**：都取当前**秒级** Unix 时间戳字符串（SDK 里 nonce 和 timestamp 是同一个值）。

**第 3 步：拆 AppID**：`AppID.split('_')` 恰好两段时，`client_id = 第1段`，`client_sec = DecodeAppSecret(第2段)`；否则两者都是空串。

**第 4 步：DecodeAppSecret(s)**
- `len(s) != 32` → 返回空串。
- `raw = base64_decode(s)`（24 字节）。
- 密钥流：默认种子四段 `0054s397` `p6234378` `o09pn7q3` `r5qropr7`（配置了 `x-kdapi-secpwd` 时取它的前 32 位按 8 位一段），拼接后做 **ROT13**，
  默认得到 `0054f397c6234378b09ca7d3e5debce7`（SDK 中间插入的随机数字在取子串时被丢弃，不影响结果）。
- `raw` 与密钥流逐字节异或 → 再 base64 编码 → 得到 `client_sec`。

**第 5 步：X-Api-Signature**
```
api_sign = "POST\n" + 编码后的路径 + "\n\nx-api-nonce:" + nonce + "\nx-api-timestamp:" + timestamp + "\n"
X-Api-Signature = base64( hex( HMAC_SHA256(key=client_sec, msg=api_sign) ) )
```
注意三点：**路径和 nonce 之间是两个换行**（空的 query 行）；nonce 在前、timestamp 在后；
**HMAC 结果先转成小写十六进制字符串，再对这个字符串做 base64**——不是直接 base64 原始 32 字节摘要。

**第 6 步：X-Kd-Appdata 与 X-Kd-Signature**
```
app_data       = AcctID + "," + UserName + "," + LCID + "," + OrgNum
X-Kd-Appdata   = base64(app_data 的 UTF-8 字节)
X-Kd-Signature = base64( hex( HMAC_SHA256(key=AppSecret, msg=AppID + app_data) ) )
```

**完整请求头**

| Header（名字大小写照 SDK 源码） | 值 |
| --- | --- |
| `X-Api-ClientID` | client_id |
| `X-Api-Auth-Version` | `2.0` |
| `x-api-timestamp` | timestamp |
| `x-api-nonce` | nonce |
| `x-api-signheaders` | `x-api-timestamp,x-api-nonce` |
| `X-Api-Signature` | 第 5 步 |
| `X-Kd-Appkey` | 完整 AppID |
| `X-Kd-Appdata` | 第 6 步 |
| `X-Kd-Signature` | 第 6 步 |
| `Content-Type` | `application/json` |
| `kdservice-sessionid` / `Cookie` | 上一次响应返回过会话 Cookie 才带（SDK 自动维护，首个请求没有） |

- 签名里写死了 `POST`，所有接口都只用 POST。
- 时间戳过期会被拒（见第 9 节探测：13 分钟前的时间戳被网关判「过期」），服务器时钟要准。

## 6. `kd_sign.py`：签名辅助脚本

按第 5 节转写，**未用真实凭证验证**。读环境变量，打印 `Header: value` 每行一个，供 curl 或其他语言参考：

```python
#!/usr/bin/env python3
"""kd_sign.py <ServiceName> —— 金蝶云星空 WebAPI 第三方授权签名头（转写自官方 Python SDK 8.2.0，未实测）"""
import base64, codecs, hashlib, hmac, os, sys, time
from urllib.parse import quote, urlparse

DEFAULT_SEED = "0054s397p6234378o09pn7q3r5qropr7"

def _b64hex_hmac(msg: str, key: str) -> str:
    hexdigest = hmac.new(key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()
    return base64.b64encode(hexdigest.encode("utf-8")).decode()

def decode_app_secret(part: str) -> str:
    if len(part) != 32:
        return ""
    raw = base64.b64decode(part)
    seed = (os.environ.get("KD_SECPWD") or DEFAULT_SEED)[:32]
    key = codecs.encode(seed, "rot13").encode("utf-8")
    return base64.b64encode(bytes(b ^ key[i] for i, b in enumerate(raw))).decode()

def build_headers(url, acct_id, username, app_id, app_secret, lcid=2052, org_num=0):
    path = quote(urlparse(url).path, encoding="utf-8").replace("/", "%2F")
    ts = str(int(time.time()))
    nonce = ts
    parts = app_id.split("_")
    client_id, client_sec = (parts[0], decode_app_secret(parts[1])) if len(parts) == 2 else ("", "")
    api_sign = f"POST\n{path}\n\nx-api-nonce:{nonce}\nx-api-timestamp:{ts}\n"
    app_data = f"{acct_id},{username},{lcid},{org_num}"
    return {
        "X-Api-ClientID": client_id,
        "X-Api-Auth-Version": "2.0",
        "x-api-timestamp": ts,
        "x-api-nonce": nonce,
        "x-api-signheaders": "x-api-timestamp,x-api-nonce",
        "X-Api-Signature": _b64hex_hmac(api_sign, client_sec),
        "X-Kd-Appkey": app_id,
        "X-Kd-Appdata": base64.b64encode(app_data.encode("utf-8")).decode(),
        "X-Kd-Signature": _b64hex_hmac(app_id + app_data, app_secret),
        "Content-Type": "application/json",
    }

if __name__ == "__main__":
    service = sys.argv[1]
    base = os.environ["KD_SERVER_URL"].rstrip("/")
    h = build_headers(f"{base}/{service}.common.kdsvc", os.environ["KD_ACCT_ID"], os.environ["KD_USERNAME"],
                      os.environ["KD_APP_ID"], os.environ["KD_APP_SECRET"],
                      int(os.environ.get("KD_LCID", 2052)), int(os.environ.get("KD_ORG_NUM", 0)))
    for k, v in h.items():
        print(f"{k}: {v}")
```

curl 用法（兼容 macOS 自带 bash 3.2，不用 `mapfile`）：

```bash
SVC=Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.View
HDRS=(); while IFS= read -r h; do HDRS+=(-H "$h"); done < <(python3 kd_sign.py "$SVC")
curl -sS -X POST "${KD_SERVER_URL%/}/$SVC.common.kdsvc" "${HDRS[@]}" \
  -d '{"formid":"BD_MATERIAL","data":{"Number":"WL0001"}}'
```

- 签名里的时间戳是**生成时刻**的，生成后尽快发出。
- 其他语言照第 5 节实现时，重点对齐：`%2F`、两个 `\n`、hex 再 base64、AppID 第二段先解码。

## 7. 会话登录 ValidateUser（旧方式）

**Endpoint**：`POST {ServerUrl}/Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc`
**用途**：用账号密码登录，拿会话 Cookie。文档页把这个操作隐藏了；新对接不推荐。

**参数（文档原文）**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `acctID` | 字符串 | 是 | 帐套 Id（数据中心 ID） |
| `username` | 字符串 | 是 | 用户名称 |
| `password` | 字符串 | 是 | 用户密码 |
| `lcid` | 整型 | 否 | 语言标识（2052 为简体中文，来自 SDK 配置说明「账套语系，默认2052」） |

- 文档的「JSON格式数据」一栏是**空的**，只给了 .NET 调用 `client.ValidateUser(acctID, username, password, lcid)`。
  HTTP body 是 `{"acctID":..,"username":..,"password":..,"lcid":2052}` 这样的对象还是按参数顺序的数组 ⚠ 文档未说明，需实测。
- 返回（文档原文模板）：`{"Message":"！","MessageCode":"","LoginResultType":0,"Context":null,"FormId":null}`，
  备注「ValidateUser 是验证用户信息是否合法」。**`LoginResultType` 的枚举值 ⚠ 文档未说明**（社区文章称 1 为成功，未在官方材料中核实）。
- 登录后的会话：SDK 处理响应时读取 Cookie `kdservice-sessionid`，之后既放进同名请求头也放进 Cookie。用 curl 就 `-c/-b` 维护 Cookie 文件。
- 其他登录接口 `AuthService.LoginByAppSecret` 等只见于社区文章，本次抓到的官方材料里没有参数说明 ⚠。
- 无凭证探测（2026-09-11）：对旧公网网关 `api.kingdee.com/galaxyapi` 调 ValidateUser 被网关直接拒绝（`4002 APP_ID is empty`），
  即该网关要求第三方授权头，不接受裸账号密码。

```bash
# ⚠ body 形态未经文档确认
curl -sS -c kd.cookies -X POST "${KD_SERVER_URL%/}/Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc" \
  -H 'Content-Type: application/json' \
  -d "{\"acctID\":\"$KD_ACCT_ID\",\"username\":\"$KD_USERNAME\",\"password\":\"$KD_PASSWORD\",\"lcid\":2052}"
curl -sS -b kd.cookies -X POST "${KD_SERVER_URL%/}/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc" \
  -H 'Content-Type: application/json' -d '{"data":{"FormId":"BD_MATERIAL","FieldKeys":"FNumber,FName","Limit":10}}'
```

## 8. 数据中心列表 GetDataCenterList

SDK：`GetDataCenters()` → `Kingdee.BOS.ServiceFacade.ServicesStub.Account.AccountService.GetDataCenterList`，body 为 `{}`。
注意命名空间是 **`Kingdee.BOS.ServiceFacade.ServicesStub.Account`**，不是业务接口的 `Kingdee.BOS.WebApi.ServicesStub`。
返回结构 ⚠ 文档未说明。用途：确认 `X-KDApi-AcctID`（数据中心 ID）；也可以在星空「第三方系统登录授权 → 生成测试链接」里看到。

## 9. 无凭证探测结果（2026-09-11，目标：旧公网网关 `https://api.kingdee.com/galaxyapi/`）

客户私有部署服务器没有公开地址可测，只能探测这个已被 SDK 弃用的旧网关，**它的行为不代表客户服务器**。

| 请求 | HTTP | 响应 |
| --- | --- | --- |
| `GET /galaxyapi/` | 519 | `{"errcode":5001,"description":"API not found[GW]","description_cn":"请求的API不存在[网关]"}` |
| `POST …ExecuteBillQuery.common.kdsvc`，无鉴权头 | 519 | `{"errcode":4002,"description":"Unauthorized, APP_ID is empty[GW]","description_cn":"认证失败, 应用ID为空[网关]"}` |
| 同上，带 SDK 同形伪造头，时间戳为 13 分钟前 | 519 | `{"errcode":4006,"description":"Unauthorized, errDescEn: X-Api-TimeStamp is invalid: 1789120000[GW]","description_cn":"认证失败, errDescCn: X-Api-TimeStamp过期: 1789120000[网关]"}` |
| 同上，时间戳为当前秒 | 519 | `4002 APP_ID is empty`（响应头带 `X-Api-Requestid`） |
| `POST …AuthService.ValidateUser.common.kdsvc`，body 全是 `test` | 519 | `4002 APP_ID is empty` |

结论：`.common.kdsvc` 路径被网关识别；网关失败用**非标准 HTTP 519** + `errcode` JSON；秒级时间戳会被校验时效（窗口长度未测出）。
带 `X-Api-ClientID: test` 仍报「应用ID为空」，该网关从哪里读 APP_ID ⚠ 未查明——**不能据此认为 SDK 的头名写错了**。

## 10. 常见错误对照

| 现象 | 可能原因 | 依据 |
| --- | --- | --- |
| `RuntimeError: ServerUrl is required` | 8.2.0 起没有默认网关，构造函数 / InitConfig 没传 ServerUrl | SDK 源码 |
| 控制台打印「SDK初始化失败，缺少必填授权项：账套ID,用户…」，随后 `json.loads` 报 TypeError | 授权四项有空值；SDK 不抛异常而是返回异常对象 | SDK 源码 |
| HTTP 519 `errcode 4002 APP_ID is empty` | 请求打到了金蝶网关但没带（或网关未识别）第三方授权头 | 无凭证探测 |
| HTTP 519 `errcode 4006 X-Api-TimeStamp过期` | 本机时钟偏差 / 签名生成后隔太久才发 / 用了毫秒时间戳 ⚠（毫秒未测） | 无凭证探测 |
| 签名一直不对 | 对照第 5 节：`/` 没编码成 `%2F`、少了一个 `\n`、直接 base64 了原始摘要、把 AppSecret 当成 X-Api-Signature 的密钥 | SDK 源码 |
| 把 `X-KDApi-AppID` 当请求头发送 | 那是配置文件键名，不是 HTTP 头 | SDK 源码 + SDK 介绍页 |
