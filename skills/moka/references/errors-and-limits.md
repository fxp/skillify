# 错误码、限流、分页与数据格式（ATS + People）

> 来源：ATS 文档「错误码」「时间字段格式说明」<https://www.mokahr.com/docs/api/>、People 文档「全局错误码」「API接口类型说明」<https://people.mokahr.com/docs/api/view/v1.html>（抓取于 2026-09-11）。
> **文档版，未用真实凭证调用验证。** 标「无凭证探测（2026-09-11）」的条目有可复跑命令（probe-log.md），其余为「文档原文，未实测」。

## 目录

1. [成功怎么判：响应结构一览](#1-成功怎么判响应结构一览)
2. [鉴权 / 路由失败（无凭证探测）](#2-鉴权--路由失败无凭证探测)
3. [ATS 错误码](#3-ats-错误码)
4. [People 全局错误码](#4-people-全局错误码)
5. [限流](#5-限流)
6. [分页方式对照](#6-分页方式对照)
7. [时间格式](#7-时间格式)
8. [空值](#8-空值)
9. [推荐的错误处理骨架（Python）](#9-推荐的错误处理骨架python)
10. [⚠ 汇总](#10--汇总)

---

## 1. 成功怎么判：响应结构一览

**ATS 没有统一信封**，同一个客户端里要按接口判。文档示例整理：

| 形态 | 成功条件 | 出现在 |
| :--- | :--- | :--- |
| `{"success": true, …}` / `{"success": false, "errorMessage": "…"}` | `success == true` | 创建职位、创建 / 发送 Offer、标记入职、`GET /v1/departments` |
| `{"code": 0, "msg": "…"}` | `code == 0` | 移动阶段、Offer 状态回写、归档、`uploadResume`、`/open-api/ats/v3/users/list`、OAuth2 getToken |
| `{"code": 0, "message": "…", "data": …}` | `code == 0`（字段名是 `message`） | 创建面试 |
| `{"code": 0, "codeType": 0, "data": […]}` | `code == 0` | V3 职位 / 面试详情 |
| `{"code": 200, "msg": "success", "data": …}` | `code == 200` | V3 申请查询、附件、`/v1/file/upload`、`/v2/users/syncInfo` |
| `{"data": […], "next": "…"}` | HTTP 200 | `/v1/data/applications`、`/v1/data/jobs`、`/v1/data/headcounts` |
| 裸数组 `[…]` / `{"rows": […]}` / `{"headcount": {…}}` | HTTP 200 | `/v1/data/job_stages` / `/v1/pipelines/list` / 创建招聘需求 |

- ⚠ 文档自相矛盾：组织架构全量同步 / 增量新增的示例是 `code: 0`，返回字段表写「`200`: 成功」；V3 人事信息示例 `code: 0`，字段表写「非 200 代表失败」。
  这类接口按 **`code in (0, 200)`** 判成功。
- **People**：读接口 `{"code":200,"msg":…,"data":{…}}`；员工写接口两层信封（外层 `code:0` → 内层 `data.code:200` → 逐条 `success`）；部门写接口外层 200 + 逐条 `data[].code`。见 `people-hr.md`。

## 2. 鉴权 / 路由失败（无凭证探测）

无凭证探测（2026-09-11），每条复跑两次一致：

| 情形 | HTTP | body |
| :--- | :--- | :--- |
| ATS `/api-platform/…` 无鉴权或伪造 Key（多数接口） | **500** | `{"code":-1,"success":false,"msg":"无法识别的认证信息"}` |
| ATS 部分接口伪造 Key（V3 查询、`getJobs`、`switchStatus`） | **500** | `{"code":-1,"success":false,"msg":"系统中不存在该apiKey"}` |
| ATS `/open-api/ats/v3/…` 伪造 Key | **401** | `{"code":-1,"msg":"无法识别的认证信息","subCode":"Unauthorized"}` |
| ATS 路径不存在 | **404** | `{"message":"您访问的页面不存在"}` |
| ATS OAuth2 伪造 clientID | **200** | `{"code":110020,"msg":"unauthorized_client","data":{}}` |
| ATS 招聘官网 `GET /v1/jobs/{orgId}` 不带任何鉴权、缺 `mode` | **403** | `{"message":"招聘模式 必填","msg":"招聘模式 必填","code":3}`（参数校验，而非鉴权错误） |
| People 一切未授权请求（含不存在路径） | **403** | `{"success":false,"msg":"无法识别的认证信息"}` |

要点：**ATS 鉴权失败是 HTTP 500**，别把 5xx 一律当"服务端抖动"重试；People 文档写鉴权失败是 401 / 100001，探测到的是 403 且无 `code`（详见 `auth.md` 第 7 节）。

## 3. ATS 错误码

文档「错误码」一节（`#-329`）是一张约 190 行的业务码表，按号段归类如下（文档原文，未实测；完整表见文档）：

| 号段 | 领域 | 常见条目 |
| :--- | :--- | :--- |
| `100001`–`100005` | 通用 | `100001` 需要登录才能进行该操作；`100002` 登录失效；`100003` 用户权限不够；`100004` 账户已过期；`100005` 参数异常（缺少必要参数） |
| `2010xx` | 叫号面试 | `201011` 找不到可用的面试申请；`201058` 候选人或申请不存在 |
| `2110xx` | 面试 / 面试评价表 | `211010` 与本面官已安排面试冲突；`211022` 最多可导出连续 7 天的面试；`211031` 面试官已填写反馈；`211034` 只有面试官才能填写面试反馈 |
| `2210xx` | 预约面试 | `221008` 预约面试已截止；`221017` 目标场次已满员 |
| `3001xx` / `3002xx` | 模板 / 字段 | `300204` 字段名称不可重复；`300208` 字段值不合法 |
| `3003xx` | Offer 审批 | `300310` Offer 审批进行中，不可修改；`300319` Offer 已审批；`300322` 此用户不是该 offer 审批人 |
| `3004xx` | 参数 / 角色 / 用户 | `300400` 参数错误 |
| `3005xx` | 申请 / 候选人 | `300501` 申请不存在；`300502` 申请已归档；`300506` 申请ID必传；`300507` 职位不存在；`300509` 当前申请所在阶段有误；`300515` 候选人不存在；`300518` 短信余量不足 |
| `3006xx` | Offer | `300600` Offer 不存在；`300608` Offer 已接受；`300612` 申请下已存在 Offer；`300617` Offer 审批未通过，不可发送；**`300618` 未开启外部系统创建 Offer**；`300620` 该创建人没有创建 offer 权限；`300621` 该用户没有发送 offer 权限 |
| `4000xx` | 猎头 / 内推渠道 | `400017` 候选人处于保护期；`400018` 职位已关闭 |
| `5001xx` / `5003xx` | 第三方（北森 / 牛客） | `500103` 未绑定北森服务；`500303` 未绑定牛客服务 |
| `7000xx` | 查重 | `700010` 候选人查重失败 |

另有**接口内专属码**，与上表不通用：

- 创建面试：`-1`、`100`–`106`、`400`（见 `interviews-offers.md` 第 2 节）。
- OAuth2：`110020 unauthorized_client`。
- 删除 / 合并部门示例：`625011`（department_code 已存在）。
- 各接口的中文 `errorMessage` 列表（如组织架构同步「当前有未处理完的组织架构更新，请稍后再试」），见各 reference。

**号段冲突**：通用表 `100001` 是"需要登录"，而创建面试接口的 `100` / `101` 是它自己的含义；`100002` 在 ATS 是"登录失效"，在 People 是"入参错误"。**错误码只在同一个接口 / 同一套 API 内有意义。**

## 4. People 全局错误码

文档原文：

| HTTP | 错误码 | 说明 | 排查 |
| :--- | :--- | :--- | :--- |
| 200 | `0` / `200` | 请求成功 | — |
| 400 | `100002` | 入参错误 | 检查参数 |
| 401 | `100001` | 没有进入系统权限 | 检查授权码（**探测到的是 403，见第 2 节**） |
| 403 | `100005` | 没有进入访问模块权限 | 检查是否有该模块权限 |
| 404 | `100000` | 请求地址错误 | — |
| 405 | `100000` | 接口请求方式错误 | — |
| 500 | `-1` | 系统错误 | 联系技术支持 |
| **600** | **`600`** | **请求频率过快，请稍后再试** | 降低调用频率 |

- **限流用的是非标准 HTTP 状态码 600**。按 `status_code == 429` 写的限流重试永远不会触发；按 `status >= 500` 重试又会把真正的系统错误一起重试。单独判 600。

## 5. 限流

**People（文档逐接口标注，均为"每企业"）**

| 接口 | 限额 |
| :--- | :--- |
| 读部门、读员工任职、职位 / 职务 / 职级列表、新增 / 更新 / 离职员工、部门写入 | 3 次/秒，60 次/分钟 |
| 字段元数据 `get_all_obj_fields`、枚举值 `get_enum_values` | 3 次/秒，**5 次/分钟** |
| 待入职批量新增 / 更新 / 取消 | **1 次/秒，20 次/分钟** |
| 获取编制信息 `/v1/org/hc/plan/query` | 1 次/秒，20 次/分钟 |
| 职位 / 职务写入 | 5 次/秒，60 次/分钟 |
| 合同写入、异动写入、成本中心 / 项目组 / 法人公司写入 | 2 次/秒，30 次/分钟 |
| 通用附件上传 | 50 次/秒，200 次/分钟 |
| 员工工作台待办查询 | 10 次/秒，300 次/分钟 |

每分钟额度才是真正的约束：60 次/分钟 ≈ 1 次/秒，按"3 次/秒"并发会在 20 秒内用完一分钟额度。批量同步用单线程 + ≥ 1 秒间隔。

**ATS**

- 文档原文：招聘需求（Headcount）**写入接口 1 分钟 30 次**。
- 其他 ATS 接口的限流：⚠ 文档未说明；超限时的返回格式：⚠ 文档未说明。
- 批量上限（文档原文，接口内）：同步人事信息每次 ≤ 100 条；V3 申请查询 ID ≤ 20、每页 ≤ 20；按联系方式查每类 ≤ 20、最多返回 100 条；V3 职位详情 `jobIds` ≤ 20、`mjCodes` ≤ 10；创建面试 `applicationIds` ≤ 200；Offer 附件 ≤ 5；官网申请附件 ≤ 10。

## 6. 分页方式对照

**同一平台至少五种分页方式**，不要写一个通用分页器套全部：

| 方式 | 接口 | 写法 |
| :--- | :--- | :--- |
| `fromTime` 起步 + `next` 游标（query） | ATS `GET /v1/data/applications`、`/v1/data/jobs`、`/v1/data/headcounts` | 首次只带 `fromTime`，之后只带 `next`；响应无 `next` 即结束；`limit` 默认 100 |
| `next` 游标（body） | ATS `POST /v3/applications/list_by_condition` | 翻页时 body 只放 `{"next": …}`；`limit` ≤ 20 |
| `limit` + `offset` | ATS `POST /v1/jobs/getJobs`、官网 `GET /v1/jobs/{orgId}` | `limit` 默认 30，`offset` 从 0 |
| `pageNumber`（每页固定 20） | ATS `GET /v1/headcounts` | 只能控制页码 |
| `nextUserId` 游标 | ATS `POST /open-api/ats/v3/users/list` | `order=ASC` 时返回 `nextUserId`，可做增量；`limit` ≤ 500 |
| 日期窗口 | ATS `GET /v1/interviews` | ≤ 31 天一窗 |
| `pageNum` + `pageSize` | People 大多数读接口 | `pageSize` ≤ 200（待入职数据 ≤ 50，⚠ 见 people-hr.md） |
| `nextCursor` + `hasMore` | People 兼岗、成本中心、法人公司 | 首次不传；`hasMore` 为 true 时传上次的 `nextCursor` |

## 7. 时间格式

ATS 文档原文列了四种：`yyyy`（毕业年份）、`yyyy-MM`（毕业时间）、`yyyy-MM-dd`（到岗日期）、`yyyy-MM-ddTHH:mm:ss.sssZ`（ISO8601，面试开始时间）；
并说明「由于历史原因，某些字段并没有严格按照以上规则设置格式……开发者最好做到能同时识别这几种格式」。实际还会遇到：

| 格式 | 出现在 |
| :--- | :--- |
| 毫秒时间戳 | ATS 所有 V3 接口；ATS 面试推送的 `startTime` / `endTime`；People 员工写入的日期字段；People 文档新增的第 5 种格式 |
| 秒时间戳（⚠ 仅示例） | ATS webhook `triggeredAt` 示例 `1505296287` |
| `yyyy-MM-dd HH:mm:ss`（无时区） | ATS 创建面试 `startTime` / `signedInAt`；`/v1/data/applications` 的 `updatedAt`；People 员工增量 `startDate` / `endDate` |
| `yyyy-MM-ddTHH:mm:ss`（无 Z） | People 部门 `effect_date` |

```python
from datetime import datetime, timedelta, timezone

CN = timezone(timedelta(hours=8))   # ⚠ 文档未说明无时区字符串的时区，这里假定北京时间

def parse_moka_time(v):
    """把 Moka 的各种时间表示转成带时区的 datetime。"""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        n = int(v)
        if n > 10**11:                      # 毫秒时间戳
            return datetime.fromtimestamp(n / 1000, tz=timezone.utc)
        if n > 10**8:                       # 秒时间戳
            return datetime.fromtimestamp(n, tz=timezone.utc)
        v = str(n)                          # 4 位年份，如毕业年份 2018
    s = v.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue
        return dt if dt.tzinfo else dt.replace(tzinfo=CN)
    raise ValueError(f"unknown Moka time format: {v!r}")
```

## 8. 空值

- ATS 文档原文：字段值为空返回 `null`，数组为空返回 `[]`；但「拉取面试列表」说明「字段若为空，则内容为空字符串」。
- People 文档原文：三种情况——**key 不出现**、`null`、`""`，都要兼容。用 `d.get(k) or None` 统一。

## 9. 推荐的错误处理骨架（Python）

```python
import time, requests

class MokaAuthError(Exception): ...
class MokaRateLimited(Exception): ...

def classify(resp: requests.Response) -> dict:
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:200]}
    msg = str(body.get("msg") or body.get("message") or "")
    if "认证信息" in msg or "不存在该apiKey" in msg:                # ATS 500 / 401、People 403 都是这类文案
        raise MokaAuthError(f"HTTP {resp.status_code}: {body}")      # 不要重试
    if resp.status_code == 600 or str(body.get("code")) == "600":
        raise MokaRateLimited(body)                                  # People 限流
    if resp.status_code == 404:
        raise RuntimeError(f"路径不存在（ATS 路由先于鉴权）：{resp.url}")
    return body

def with_backoff(fn, *a, tries=5, **kw):
    for i in range(tries):
        try:
            return fn(*a, **kw)
        except MokaRateLimited:
            time.sleep(min(60, 2 ** i))
    raise RuntimeError("rate limited too many times")
```

然后每个调用点按第 1 节判 `success` / `code`。

## 10. ⚠ 汇总

- ⚠ 文档自相矛盾：组织架构同步、V3 人事信息的成功码（示例 0 vs 字段表 200）。
- ⚠ 文档未说明：ATS 除招聘需求外的限流额度与超限返回格式。
- ⚠ 文档未说明：无时区时间字符串（如 `yyyy-MM-dd HH:mm:ss`）的时区。
- Gap（探测证实）：People 鉴权失败实际为 HTTP 403 无 `code`，文档写 401 / 100001（标记在 `auth.md`）。
