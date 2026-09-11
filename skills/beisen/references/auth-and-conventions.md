# 鉴权（换 token）与全局约定

来源：开放平台「接口文档说明 / Token 数据兑换流程」（open.italent.cn 文档中心左侧，内容硬编码在前端 bundle 中）、
社区文档「401/403 排查」（users.italent.cn pageId=80117962）、「受信 IP 白名单」（pageId=95813698）、
「429」（pageId=109711678）、PaaS平台 › 开放平台 › 「根据请求ID查询业务异步接口的任务处理状态」。抓取于 2026-09-11。
**未用真实凭证验证。**标「无凭证探测（2026-09-11）」的是用伪造参数打出来、复跑两次一致的结果（命令见 `beisen-workspace/probe-log.md`），
其余报错与行为均为「文档原文，未实测」。

## 目录

1. 凭证从哪来：连接器、AppSecret、受信 IP
2. 换 token：`POST /OAuth/Token`
3. 调业务接口：请求头与 URL
4. 北森的几种 ID（最容易传错）
5. 响应外壳：三套写法
6. 新版 v3.0 / 旧版 v2.0 / 「历史版本」三代接口怎么选
7. 异步接口：拿 `X-PAAS-Request-ID` 查处理结果
8. 一个可复用的 Python 客户端骨架

---

## 1. 凭证从哪来

- **AppSecret 找实施顾问申请**（文档原文：「向实施顾问申请密钥AppSecret，用于获取授权令牌AccesToken」）。租户没有自助注册开发者账号这一步。
- **凭证挂在「连接器」上**。401 排查文档原文：「连接器是否勾选了该接口，注意需要找获取Token的那个连接器（可根据key和secret确认）」。
  也就是说：token 能调哪些接口，取决于换 token 用的那对 key/secret 所属连接器勾选了哪些接口；字段级权限也在连接器里配
  （员工时间窗接口提示：「接口支持字段权限控制，在开放平台连接器中配置……本接口需要有员工信息（EmployeeInformation）和任职记录（EmploymentRecord）的两者的对象权限，否则提示权限异常」）。
- **受信 IP 白名单**（文档原文）：
  - 「自2022/8/19 23:59:59起，北森新开通的租户创建OpenAPI的连接器前需为企业配置OpenAPI调用受信IP白名单」；
  - 在开放平台「管理者后台 → OpenAPI调用受信IP」配置，需要「管理员(开放平台)」身份；保存后**立即生效**；
  - 企业首次维护受信 IP 即代表启用白名单，名单外服务器调用失败，错误码表（OpenPlatform `403`）：
    「当前企业已设置OpenAPI调用受信IP，当前调用端的IP不在受信IP范围内」。
  - 所以：部署到新机器 / 换出口 IP / 本地调试前，先确认 IP 在名单里。
- **沙箱**：401 排查文档提到「调用了沙箱环境的获取Token接口，去请求生产环境的业务接口」会 401，示例中出现过 `openapi.italent-dev.cn`。
  沙箱域名与开通方式 ⚠ 文档未说明（公开文档中未找到正式说明）。token 和业务接口必须来自同一环境。

## 2. 换 token

### 获取 access_token
**Endpoint**: `POST https://openapi.italent.cn/OAuth/Token`
**用途**: 用租户 ID + AppSecret 换业务接口用的 `access_token`。所有业务调用的第一步。

**Content-Type**: `application/x-www-form-urlencoded`（**表单，不是 JSON**）

**关键参数**（文档表格原文）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `app_id` | int | yes | italent appid |
| `secret` | string | yes | 申请应用时分配的 AppSecret |
| `tenant_id` | int | yes | 租户 id |
| `grant_type` | string | yes | 授权类型：1.authorization_code；**2.client_credentials（非特别说明授权类型使用本项）**；3.password；4.yufu；5.mobile_dynamic_code |

⚠ 文档自相矛盾：参数表把 `app_id` 标为必填，但同页 Demo 请求体只有
`tenant_id=204402&grant_type=client_credentials&secret=…`，没有 `app_id`。**按参数表四个字段都传**；拿到凭证后按 verification-plan 验证缺 `app_id` 时的行为。

**示例请求**

```bash
curl -sS -X POST 'https://openapi.italent.cn/OAuth/Token' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "app_id=${BEISEN_APP_ID}" \
  --data-urlencode "tenant_id=${BEISEN_TENANT_ID}" \
  --data-urlencode "secret=${BEISEN_APP_SECRET}" \
  --data-urlencode 'grant_type=client_credentials'
```

```python
import os, requests

resp = requests.post(
    "https://openapi.italent.cn/OAuth/Token",
    data={  # data= 发表单；不要用 json=
        "app_id": os.environ["BEISEN_APP_ID"],
        "tenant_id": os.environ["BEISEN_TENANT_ID"],
        "secret": os.environ["BEISEN_APP_SECRET"],
        "grant_type": "client_credentials",
    },
    timeout=15,
)
body = resp.json()
if resp.status_code != 200 or "access_token" not in body:
    raise RuntimeError(f"token failed: HTTP {resp.status_code} {body}")
token = body["access_token"]
```

**示例响应**（文档原文 Demo）

```json
{"access_token": "5N3w5J5_oTjVXQrIQ0Y1MfG-qQ9S6waDUtBGeqJ-DVBgNs41QqOCsQ",
 "expires_in": "1479202744", "tenant_id": "204402", "user_id": "0"}
```

| 字段 | 文档表格类型 | 说明（文档原文） |
|---|---|---|
| `access_token` | string | 租户授权的唯一票据 |
| `expires_in` | long | 授权有效时间，以秒为单位（8400000） |
| `tenant_id` | int | 授权租户 id |
| `user_id` | int | 授权用户 id（此时无效） |

⚠ 文档自相矛盾：表格说 `expires_in` 是 long、单位秒、值 8400000（约 97 天）；Demo 里却是**字符串** `"1479202744"`（量级像 Unix 时间戳），
`tenant_id`、`user_id` 在 Demo 里也是字符串。**写代码时**：数字字段一律 `int(...)` 兼容 string；不要把 `expires_in` 当成可信的精确 TTL，
用一个保守的本地缓存时长（自己定，文档没给推荐值），并且**收到 401 就强制重新换 token 再重试一次**。

**注意事项**

- **无凭证探测（2026-09-11）**：`tenant_id=0`、`app_id=0` 加伪造 secret → HTTP **400**，body `{"error":"invalid_tenantid"}`，
  响应头带 `X-RateLimit-Limit-second: 400`。token 接口的错误是 OAuth 风格的 `{"error": "..."}`，**不是**业务接口的 `{code, message}`。
- `invalid_tenantid` 以外的错误值（secret 错、app_id 错、grant_type 错）⚠ 文档未说明，需真实凭证验证。
- token 是**租户级**的（`user_id` 「此时无效」），不代表某个员工身份。
- 不要把 AppSecret / token 下发到前端。

<!-- Gap: 「接口文档说明」模板（open.italent.cn 文档中心）把示例请求地址写成 https://openapi.italent.cn/token；无凭证探测（2026-09-11，两次一致）GET 该地址返回 HTTP 404 HTML「The resource cannot be found.」。真正的换 token 地址是 POST https://openapi.italent.cn/OAuth/Token（伪造参数返回 400 {"error":"invalid_tenantid"}，说明路径存在）。 -->
> 文档模板里出现的 `https://openapi.italent.cn/token` 不是 token 接口（无凭证探测：404）。只用 `/OAuth/Token`。

## 3. 调业务接口

- 请求头（文档原文：「在请求报文头中新加Authorization，值为Bearer+空格+access_token」）：

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

- URL：`https://openapi.italent.cn` + 接口文档里的路径。文档的 `interface_url` 字段不带协议（如 `openapi.italent.cn/TenantBaseExternal/api/v5/Employee/GetByTimeWindow`），自己补 `https://`。
- 方法：新版接口绝大多数是 **POST + JSON body**，**包括查询类**。按抓到的文档统计：组织员工 v3.0 共 298 篇，POST 277、DELETE 13、PUT 6、GET 2
  （2 个 GET 都在「历史版本（不推荐）」里）；假勤 165 篇里 GET 3；招聘 181 篇里 GET 44。GET 接口（如异步任务状态、招聘的部分查询）参数走 query string。
- 401 排查文档原文：「接口不支持Path的可变参数，如 …/entry/save/{id} 改为 …/entry/save?id=」。新版接口没有 `{id}` 路径段；旧版 v2.0 大量 `/{tenantId}/` 路径（见第 6 节）。
- **无凭证探测（2026-09-11，复跑一致）**：
  - 不带 `Authorization` → HTTP **400** `{"message":"Authorization header is empty"}`；
  - 伪造 token（带不带 `Bearer ` 前缀一样）→ HTTP **401** `{"message":"un-authorized"}`；
  - 伪造 token 请求**不存在的路径**也是 401 —— 网关先鉴权后路由，**401 不能说明路径写对了**；
  - `http://` 没有被 301 跳转，网关直接回 401。文档写「所有的请求都为HTTPS协议」，照做只用 https。

## 4. 北森的几种 ID

| ID | 长什么样 | 在哪出现 | 注意 |
|---|---|---|---|
| **UserID** | int，如 `115515434` | 员工；任职记录的 `userID`；直线经理 `pOIdEmpAdmin`；组织负责人 `personInCharge` | 大多数员工接口的主键。批量接口参数名常叫 `oIds`，传的就是 UserID（文档提示「该处为员工UserID」） |
| **组织 OId** | int，如 `4745240` | 组织单元 `oId`；任职记录 `oIdDepartment`（部门）、`oIdOrganization`（机构） | **根组织 OId = 900 + 租户ID**（如 `900100000`）；「默认组织OId为0」 |
| **职位 OId** | **GUID 字符串** | 职位 `oId`；任职 `oIdJobPosition` | 与组织 OId 类型不同 |
| **职务 / 职务序列 OId** | **数字字符串**，如 `"63167"` | 职务 `oId`；任职 `oIdJobPost`、`oIdJobSequence` | 响应里是 string；写入时文档要求「必须为空或数字」 |
| **职级 / 职等 OId** | GUID 字符串 | `oIdJobLevel`、`oidJobGrade`（注意小写 `oid`） | |
| **objectId** | GUID | 每条员工信息 / 任职记录的实体主键 | 同一 UserID 可有多条任职记录，各有 objectId |
| **originalId（外部ID）** | 任意字符串 | 写接口可用它代替 UserID / OId | 新建时传入会建立「外部ID↔内部ID」映射；之后 `XXXOriginalId`（如 `oIdDepartmentOriginalId`、`pOIdEmpAdminOriginalId`）可直接引用。改映射用 `SourceIdMapping/UpdateOriginalIdByTargetId` |
| 邮箱 / 工号 / 手机号 | 字符串 | 反查 UserID 的三个接口 | 邮箱**需小写**；工号、手机号一次 ≤30 个（见 `employees.md`） |
| 招聘 GUID | GUID | `applicantId`、`applyId`、`jobId` | 招聘另有 int 型 `jobIntId`、`C+数字` 的 `candidateId`；文档建议用 GUID（见 `recruiting.md`） |
| 假勤 StaffId / UserId | int | 假勤接口 | 假勤常见问题专门有一条「接口返回中的UserId和StaffId分别是什么？」——答案在子页面，未抓取（⚠ 文档未说明） |

写接口里「UserId 与 OriginalId **必须有且仅有一个有值**」（调动 / 离职 / 转正 / 入职等接口提示原文），两个都传或都不传都会被拒。

## 5. 响应外壳：三套写法

同一个开放平台，不同产品线的外壳不一样（从 896 篇文档的响应 schema 统计）：

| 产品线 | 外壳 | `code` 类型（文档） | 例子 |
|---|---|---|---|
| 组织员工 v3.0（`/TenantBaseExternal/api/v5/…`） | `{"code":"200","message":null,"data":…}`；时间窗接口再加 `scrollId`、`total`、`isLastData` | **字符串** `"200"` / `"417"` | `{"data":null,"code":"417","message":"只支持查询90天范围内的数据，请分段查询"}` |
| 招聘（`/RecruitV6/api/v1/…`） | `{"code":200,"message":"…","data":…}` | **整数** 200 / 400 / 417 / 500 | `{"data":null,"code":400,"message":"开始时间不能大于等于结束时间"}` |
| 假勤（`/AttendanceOpen/api/v1/…`） | 查询类多为 `{"code":"200","data":{…}}`；推送类是 **`{"Code":200,"Message":null}`（首字母大写）** | 混用 | 打卡 / 休假推送返回 `Code`、`Message` |
| 网关层（鉴权失败） | `{"message":"un-authorized"}` / `{"message":"Authorization header is empty"}` | 无 code，靠 HTTP 状态 | 无凭证探测（2026-09-11） |
| token 接口 | `{"error":"invalid_tenantid"}` | 无 code | 无凭证探测（2026-09-11） |

所以统一的判断写法是：**先看 HTTP 状态码，再兼容地读 `code`/`Code`，并把它转成字符串比较**：

```python
def biz_code(body: dict) -> str:
    c = body.get("code", body.get("Code"))
    return str(c) if c is not None else ""
```

还有两处「HTTP 200 + code 200 仍然可能部分失败」：批量接口的 `data.failDatas` / `data.failCount`（如取消入职），
按工号 / 手机号反查 UserID 的**逐条** `data[].code`（见 `employees.md`）。

## 6. 三代接口怎么选

| 代 | 路径特征 | 文档位置 | 建议 |
|---|---|---|---|
| 新版 v3.0 | `/TenantBaseExternal/api/v5/…`、`/AttendanceOpen/api/v1/…`、`/RecruitV6/api/v1/…` | 文档中心「新版接口 v3.0」 | **默认用这一代**，本 skill 全部基于它 |
| v3.0 树里的「历史版本（不推荐）」 | `/TenantBasePublicApiV2/v2/…`（含 PUT / DELETE 风格） | 组织员工 › 历史版本（不推荐） | 不要新接；很多标「【该接口已过期】」 |
| 旧版 v2.0 | `/tenantbase/v1/{tenantId}/…`、`/attendance/v1/{tenantId}/…`、`/userframework/v1/{tenantId}/…` | 文档中心「旧版接口 v2.0」（178 篇） | 不要新接；租户 ID 在 path 里 |

- **无凭证探测（2026-09-11，复跑一致）**：旧版 v2.0 路径 `/tenantbase/v1/0/employee/seviceinfo/email/search` 带伪造 token 返回
  HTTP **500**（状态行 `Falied to verify your credentials`，空 body），与新版路径的 401 不同。存量代码里看到 500 先检查是不是在用旧版路径。
- 2026-03-13 起组织员工数据获取类接口的 `enableTranslate` 参数停止支持、`translateProperties` 返回 null（社区文档「重要升级通知」原文，
  存量客户暂不受影响，新客户禁止使用）。翻译字段值改用数据源接口，见 `employees.md`。

## 7. 异步接口：拿 `X-PAAS-Request-ID` 查处理结果

部分写接口（打卡推送 `SwipingCardData/PostAsync`、休假推送 `Vacation`、出差推送等）是**异步**的：返回 200 只代表通过了基础校验。
文档原文（接收休假数据）：「首先调用此假勤业务异步接口，拿到响应头中的X-PAAS-Request-ID……再调用平台【根据请求ID查询业务异步接口的任务处理状态】接口……即可获得错误数据。」

### 查询异步任务处理状态
**Endpoint**: `GET https://openapi.italent.cn/OpenPlatform/api/AsyncApiExecInfo/GetByRequestId`
**用途**: 用业务异步接口响应头里的 `X-PAAS-Request-ID` 查执行结果。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `requestId` | query | string | 是 | 业务接口响应头 `X-PAAS-Request-ID`（GUID） |

响应 `data.state` 枚举：`Running`（执行中）、`PartialSuccess`（部分成功）、`AllSuccess`（全部成功）、`Fail`（失败）、`Overtime`（超时）；
`PartialSuccess` / `Fail` 时读 `data.message`；`data.progress` 为预留字段。限流 50 次/秒/企业、1000 次/分钟/企业。

```python
import time
r = session.post(f"{BASE}/AttendanceOpen/api/v1/SwipingCardData/PostAsync", json=payload, headers=hdr, timeout=30)
req_id = r.headers.get("X-PAAS-Request-ID")      # 响应头，不在 body 里
for _ in range(30):
    s = session.get(f"{BASE}/OpenPlatform/api/AsyncApiExecInfo/GetByRequestId",
                    params={"requestId": req_id}, headers=hdr, timeout=15).json()
    state = (s.get("data") or {}).get("state")
    if state and state != "Running":
        break
    time.sleep(5)   # 文档：「轮询间隔不能过小，否则超出限频后无法继续轮询」；具体间隔文档未给
```

注意（文档原文）：「超时只是异步接口的轮询时间超过最大限制，不影响业务接口正常执行任务」——`Overtime` 不等于失败。
无凭证探测里每个响应都带 `X-PAAS-Request-ID` 头，但对**同步**接口用它查状态会返回什么 ⚠ 文档未说明。

## 8. Python 客户端骨架

```python
import os, time, requests

BASE = "https://openapi.italent.cn"

class Beisen:
    def __init__(self):
        self.s = requests.Session()
        self._token, self._exp = None, 0.0

    def _fetch_token(self):
        r = self.s.post(f"{BASE}/OAuth/Token", data={
            "app_id": os.environ["BEISEN_APP_ID"], "tenant_id": os.environ["BEISEN_TENANT_ID"],
            "secret": os.environ["BEISEN_APP_SECRET"], "grant_type": "client_credentials"}, timeout=15)
        body = r.json()
        if r.status_code != 200 or "access_token" not in body:
            raise RuntimeError(f"token: HTTP {r.status_code} {body}")
        self._token = body["access_token"]
        self._exp = time.time() + 3600   # 保守的本地缓存时长（自选）；expires_in 的含义文档自相矛盾

    def post(self, path, payload, retry=True):
        if not self._token or time.time() > self._exp:
            self._fetch_token()
        r = self.s.post(BASE + path, json=payload, timeout=30,
                        headers={"Authorization": f"Bearer {self._token}"})
        if r.status_code == 401 and retry:          # token 失效 / 连接器没勾接口 / 沙箱生产混用
            self._token = None
            return self.post(path, payload, retry=False)
        if r.status_code == 429:
            raise RuntimeError("429 限频：见 errors-and-limits.md")
        r.raise_for_status()
        body = r.json()
        code = str(body.get("code", body.get("Code", "")))
        if code not in ("200", ""):
            raise RuntimeError(f"{path}: code={code} message={body.get('message', body.get('Message'))}")
        return body
```

401 重取一次 token 后仍 401，就不是 token 过期：按 401/403 排查文档逐项查（域名、沙箱 / 生产、连接器是否勾选该接口、受信 IP、HTTP 方法）。
