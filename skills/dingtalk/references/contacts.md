# 通讯录：用户、部门、ID 转换

来源：open.dingtalk.com/document 下「查询用户详情」「获取部门用户userid列表」「获取部门列表」「获取部门用户详情」
「根据unionid获取用户userid」「根据手机号查询用户」「搜索用户userId」「获取用户通讯录个人信息」「查询离职记录列表」（抓取于 2026-09-11）。
**全部为文档原文，未实测。** 通讯录的主力接口是**旧版**（`oapi.dingtalk.com/topapi/...`，token 放 query）；
新版 `api.dingtalk.com/v1.0/contact/...` 只有少量接口。鉴权细节见 `auth.md`。

## 目录

1. [接口一览与选型](#1-接口一览与选型)
2. [查询用户详情](#2-查询用户详情)
3. [部门树与部门成员](#3-部门树与部门成员)
4. [ID 转换：unionid / 手机号 / 姓名 → userid](#4-id-转换unionid--手机号--姓名--userid)
5. [新版通讯录接口](#5-新版通讯录接口)
6. [遍历全员的正确写法](#6-遍历全员的正确写法)
7. [注意事项与 ⚠](#7-注意事项与-)

---

## 1. 接口一览与选型

| 我要 | 接口 | 版本 |
| --- | --- | --- |
| 按 userid 查一个人的详情 | `POST /topapi/v2/user/get` | 旧 |
| 列某部门的下一级子部门 | `POST /topapi/v2/department/listsub` | 旧 |
| 列某部门的 userid | `POST /topapi/user/listid` | 旧 |
| 分页列某部门成员详情 | `POST /topapi/v2/user/list` | 旧 |
| unionid → userid | `POST /topapi/user/getbyunionid` | 旧 |
| 手机号 → userid（仅企业内部应用） | `POST /topapi/v2/user/getbymobile` | 旧 |
| 按姓名 / 拼音搜 userid | `POST /v1.0/contact/users/search` | 新 |
| 以登录用户身份查自己 | `GET /v1.0/contact/users/me` | 新（用户 token） |
| 查离职记录 | `GET /v1.0/contact/empLeaveRecords` | 新 |

旧版公共约定：`https://oapi.dingtalk.com<path>?access_token=<应用token>`，成功判定 `errcode == 0`，数据在 `result` 里。
文档 curl 一律用表单（`application/x-www-form-urlencoded`）；本文件示例用 JSON body，⚠ topapi 对 JSON body 的支持未实测——
出问题时改成 `requests.post(url, params=..., data=body)`。

---

## 2. 查询用户详情

**Endpoint**: `POST https://oapi.dingtalk.com/topapi/v2/user/get?access_token=...`
**用途**: 按 userid 取员工详情（姓名、部门、unionid、主管、手机号等）。权限点 `qyapi_get_member`。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| userid | String | 是 | — | 员工 userId |
| language | String | 否 | zh_CN | `zh_CN` / `en_US` |

```bash
curl -X POST "https://oapi.dingtalk.com/topapi/v2/user/get?access_token=$TOKEN" \
  -H 'Content-Type: application/json' -d '{"userid":"zhangsan","language":"zh_CN"}'
```

```python
import requests

def oapi(path: str, token: str, body: dict) -> dict:
    r = requests.post(f"https://oapi.dingtalk.com{path}", params={"access_token": token}, json=body, timeout=10)
    d = r.json()
    if d.get("errcode") not in (0, "0"):     # 文档示例里 errcode 有时是字符串 "0"
        raise RuntimeError(f"{path}: {d}")
    return d

user = oapi("/topapi/v2/user/get", token, {"userid": "zhangsan"})["result"]
```

**响应关键字段**（`result` 下）

| 字段 | 说明 |
| --- | --- |
| userid / unionid / name / avatar | 基础信息；unionid 是"员工在当前开发者企业账号范围内的唯一标识" |
| mobile / state_code | 企业内部应用需开通「企业员工手机号信息」权限才返回；**第三方企业应用不返回**（需用统一授权套件） |
| email / work_place / remark / extension | 需「邮箱等个人信息」权限；且员工面板有值才返回；三方应用不返回 |
| manager_userid | 直属主管，有值才返回 |
| dept_id_list | 所属部门 ID 数组（一个人可在多个部门） |
| leader_in_dept / dept_order_list | 各部门内是否领导 / 排序 |
| role_list | 角色（id / name / group_name） |
| active / admin / boss / senior / real_authed / exclusive_account | 布尔标志 |
| hired_date | 入职时间，毫秒时间戳，有值才返回 |

**注意事项**

- 文档错误码：`33012 无效的userId`、`400002 无效的参数`、`-1 系统繁忙`（文档原文，未实测）。
- 响应**示例**里大量数值和布尔写成字符串（`"boss": "true"`、`"dept_id_list": "[2,3,4]"`），而字段表写 Boolean / Number[] ⚠ 文档自相矛盾。
  解析时按字段表类型写，同时容忍字符串。
- 企业账号（专属账号）用户用另一份文档「查询企业账号用户详情」，本 skill 未覆盖。

---

## 3. 部门树与部门成员

### 获取部门列表（下一级）

**Endpoint**: `POST https://oapi.dingtalk.com/topapi/v2/department/listsub?access_token=...`
**用途**: **只返回下一级**子部门的基础信息，"不支持获取当前部门下所有层级子部门"（文档原文）。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| dept_id | Number | 否 | ⚠ 文档未说明（示例传 1 / 100） | 父部门 ID，根部门为 1 |
| language | String | 否 | zh_CN | `zh_CN` / `en_US` |

响应 `result` 是数组：`dept_id`、`name`、`parent_id`、`create_dept_group`、`auto_add_user`。
错误码：`60003 未找到对应部门`（文档原文）。

### 获取部门用户 userid 列表

**Endpoint**: `POST https://oapi.dingtalk.com/topapi/user/listid?access_token=...`
**用途**: 取某部门（**不含子部门**）的 userid 列表。文档原文："本接口不受通讯录权限范围限制"。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| dept_id | Number | 是 | 部门 ID，根部门传 1 |

响应：`result.userid_list`（String[]）。文档未写分页参数，⚠ 大部门是否截断文档未说明。

### 获取部门用户详情（分页）

**Endpoint**: `POST https://oapi.dingtalk.com/topapi/v2/user/list?access_token=...`
**用途**: 分页取某部门成员详情，**子部门员工获取不到**。权限点 `qyapi_get_department_member`。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| dept_id | Number | 是 | — | 部门 ID，根部门传 1 |
| cursor | Number | 是 | — | 首次传 0，之后传返回的 `next_cursor` |
| size | Number | 是 | — | 分页大小，⚠ 上限文档未说明 |
| order_field | String | 否 | custom | `entry_asc` / `entry_desc` / `modify_asc` / `modify_desc` / `custom` |
| contain_access_limit | Boolean | 否 | — | 是否返回访问受限的员工 |
| language | String | 否 | zh_CN | |

```python
def list_dept_users(token: str, dept_id: int) -> list[dict]:
    out, cursor = [], 0
    while True:
        res = oapi("/topapi/v2/user/list", token, {"dept_id": dept_id, "cursor": cursor, "size": 100})["result"]
        out.extend(res.get("list", []))
        if not res.get("has_more"):          # 文档示例里 has_more 也可能是字符串 "true"
            return out
        cursor = res["next_cursor"]
```

⚠ `size=100` 是否被接受文档未说明（只写了"分页大小"），拿到凭证先验证。
错误码：`50004 部门不在权限范围内`、`40035 参数非法`、`60019 未能从部门中获取用户`（文档原文）。

---

## 4. ID 转换：unionid / 手机号 / 姓名 → userid

### 根据 unionid 获取用户 userid

**Endpoint**: `POST https://oapi.dingtalk.com/topapi/user/getbyunionid?access_token=...`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| unionid | String | 是 | 员工在当前开发者企业账号范围内的唯一标识 |

响应：`result.userid`、`result.contact_type`（0 企业内部员工 / 1 企业外部联系人）。错误码 `60121 未找到对应员工`。

**文档原文警告**："如果是通过**免登方式**获取的unionid，则不能使用免登获取的 token 调用该接口，需要使用下方的接口重新获取"——
即必须用 `auth.md` 第 2 节的**应用 token**，不能用用户 token。
unionid 的作用域："同一个企业员工，在不同的开发者企业账号下，unionid是不相同的"。

### 根据手机号查询用户

**Endpoint**: `POST https://oapi.dingtalk.com/topapi/v2/user/getbymobile?access_token=...`
**限制**: 仅"企业内部应用"；只能查**在职**员工（离职后查不到）；权限点 `qyapi_get_member_by_mobile`。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| mobile | String | 是 | 手机号 |

响应 `result.userid`。错误码：`40104 企业中无效的手机号`、`60121 未找到该用户`（文档原文）。

### 搜索用户 userId（新版）

**Endpoint**: `POST https://api.dingtalk.com/v1.0/contact/users/search`，header `x-acs-dingtalk-access-token`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| queryWord | String | 是 | 用户名称、拼音或英文名 |
| offset | Integer | 是 | 分页页码（⚠ 名为 offset 但文档写"分页页码"，示例传 0） |
| size | Integer | 是 | 分页大小，⚠ 上限文档未说明 |
| fullMatchField | Integer | 否 | 传 1 精确匹配姓名；不传为模糊匹配 |

```bash
curl -X POST https://api.dingtalk.com/v1.0/contact/users/search \
  -H "x-acs-dingtalk-access-token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"queryWord":"小红","offset":0,"size":10,"fullMatchField":1}'
```

响应：`{"hasMore": false, "totalCount": 2, "list": ["220141953"]}`——`list` 直接是 userid 字符串数组。

---

## 5. 新版通讯录接口

### 获取用户通讯录个人信息

**Endpoint**: `GET https://api.dingtalk.com/v1.0/contact/users/{unionId}`
**鉴权**: **用户 token**（`auth.md` 第 4 节），权限点 `Contact.User.Read`。`unionId` 传 `me` 查当前授权人。
响应：`nick`、`avatarUrl`、`mobile`（三方企业应用脱敏为 `155****3240`）、`openId`、`unionId`、`email`、`stateCode`。
错误：`404 invalidParameter.user.notFound`（文档原文）。

### 查询离职记录列表

**Endpoint**: `GET https://api.dingtalk.com/v1.0/contact/empLeaveRecords`，仅企业内部应用，权限点 `Contact.Common.Read`。

| 参数（query） | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| startTime | String | 是 | ISO 8601，如 `2020-07-10T00:00:00Z` |
| endTime | String | 否 | 不传时 startTime 距今 ≤365 天；传时跨度 ≤365 天 |
| nextToken | String | 否 | 首次传 `0`，之后传返回的 `nextToken` |
| maxResults | Integer | 是 | 每页最大 50 |

```python
def leave_records(token: str, start_iso: str) -> list[dict]:
    out, nxt = [], "0"
    while True:
        r = requests.get("https://api.dingtalk.com/v1.0/contact/empLeaveRecords",
                         headers={"x-acs-dingtalk-access-token": token},
                         params={"startTime": start_iso, "nextToken": nxt, "maxResults": 50}, timeout=10)
        r.raise_for_status()
        d = r.json()
        out.extend(d.get("records", []))
        nxt = d.get("nextToken")
        if not nxt:                      # ⚠ 结束条件（空串 / 缺失）文档未明确
            return out
```

记录字段：`userId`、`name`、`stateCode`、`mobile`、`leaveTime`（ISO 8601）、`leaveReason`
（`oapi` 接口删除 / `cancel` 注销 / `leave` 主动离职 / `unknown` / `delete` 管理员删除）。

---

## 6. 遍历全员的正确写法

文档原文："**目前暂不支持一次性获取企业下所有员工userid值**"，建议从根部门逐级调「获取部门列表」拿到全部部门 ID，
再对每个部门调「获取部门用户userid列表」。

```python
from collections import deque

def all_userids(token: str) -> set[str]:
    seen_depts, userids = set(), set()
    q = deque([1])                                    # 根部门 ID = 1
    while q:
        dept = q.popleft()
        if dept in seen_depts:
            continue
        seen_depts.add(dept)
        subs = oapi("/topapi/v2/department/listsub", token, {"dept_id": dept})["result"] or []
        q.extend(s["dept_id"] for s in subs)
        userids.update(oapi("/topapi/user/listid", token, {"dept_id": dept})["result"]["userid_list"])
    return userids                                    # 用 set 去重：一个人可属于多个部门（dept_id_list 是数组）
```

大企业跑这个会打出大量请求：注意 IP 维度限流（20 秒 10000 次，触发后封 5 分钟，见 `errors-and-limits.md`），
文档建议对组织架构"增加本地缓存机制"，并用通讯录变更事件（`events.md`）做增量同步，而不是定时全量拉。

---

## 7. 注意事项与 ⚠

- 其他通讯录接口速查（**参数未转录**，用前读原文）：
  `POST /topapi/v2/user/create`（创建用户）、`POST /topapi/v2/user/delete`（删除用户）、`POST /topapi/v2/department/listsubid`（子部门 ID 列表）、
  `POST /topapi/user/listsimple`（部门用户基础信息）、`POST /topapi/role/list`（角色列表）、`GET /auth/scopes`（通讯录权限范围）。
  旧旧版路径（`/user/get`、`/department/list`、`/user/getDeptMember` 等无 `topapi` 前缀的）文档已标为历史接口，新代码不要用。
- 三方企业应用拿不到 mobile / email / state_code 等字段，文档统一指向「钉钉统一授权套件」，本 skill 未覆盖。
- ⚠ `listsub` 的 `dept_id` 标为非必填，但不传时的行为文档未说明。
- ⚠ `listid`、`listsub` 是否有单次返回上限文档未说明。
- ⚠ 「查询用户详情」等响应示例把数值/布尔写成字符串，与字段表类型矛盾。
