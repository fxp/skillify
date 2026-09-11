# ATS 组织架构与用户同步（把 eHR / 人事系统的部门和账号同步进招聘系统）

> 来源：ATS 文档「组织架构API」「用户API」「职责API」<https://www.mokahr.com/docs/api/>（抓取于 2026-09-11）。
> **文档版，未用真实凭证调用验证。** 报错 / 行为描述除标「无凭证探测（2026-09-11）」外均为「文档原文，未实测」。
> 鉴权见 `auth.md`；`ats_call()` 为 `auth.md` 第 8 节的最小客户端。
> 这里说的是**招聘系统（ATS）里的**部门与用户（HR、面试官、用人经理的登录账号）；员工人事档案在 People，见 `people-hr.md`。

## 目录

1. [为什么先同步、主键是什么](#1-为什么先同步主键是什么)
2. [同一个 URL，三种语义](#2-同一个-url三种语义)
3. [读全量部门](#3-读全量部门)
4. [全量同步部门（PUT，危险）](#4-全量同步部门put危险)
5. [增量新增部门](#5-增量新增部门)
6. [更新部门](#6-更新部门)
7. [删除 / 合并部门](#7-删除--合并部门)
8. [同步用户账号](#8-同步用户账号)
9. [读取用户（V3）](#9-读取用户v3)
10. [其他用户与职责接口](#10-其他用户与职责接口)
11. [⚠ 汇总](#11--汇总)

---

## 1. 为什么先同步、主键是什么

- 职位、招聘需求、用户、Offer 都用 `departmentCode` 指向部门；**部门不先同步，后面的 `departmentCode` 都无处可指**。
- 部门主键是 **`departmentCode`（你方系统的部门 ID）**；Moka 自己的 ID 是 `departmentId`。根部门的 `parentCode` 传字符串 `"0"`。
- 用户主键由每条数据的 `uniqueType` 决定：`email` / `number`（工号）/ `phone`。
- ATS 文档提供了一份《Moka ATS 标准交付集成开发方案》（石墨文档链接，未抓取），标准做法见该文档。

## 2. 同一个 URL，三种语义

| 方法 + 路径 | 语义 | 没出现在请求里的部门 |
| :--- | :--- | :--- |
| `PUT /api-platform/v2/departments` | **全量同步**：新增 + 更新 + 标记删除 | **被标记为已删除** |
| `POST /api-platform/v2/departments` | 更新指定部门 | 不受影响 |
| `POST /api-platform/v2/departments/sync/incremental` | 增量新增 | 不受影响 |
| `DELETE /api-platform/v1/departments` | 删除标记 / 合并删除 | — |
| `GET /api-platform/v1/departments` | 读全量 | — |

文档原文（新增组织架构一节）：「组织架构增量同步必须使用POST请求，如果使用PUT请求，为全量同步，请求中未提供的部门，部门将标记为已删除」。
**只想加一个部门时用了 PUT，会把其余所有部门标记删除。**

四个写接口都可能返回「当前有未处理完的组织架构更新，请稍后再试」——组织架构写入要**串行**，收到这条就等一会儿再重试。

## 3. 读全量部门

**Endpoint**: `GET https://api.mokahr.com/api-platform/v1/departments`（无参数）

```bash
curl -s "https://api.mokahr.com/api-platform/v1/departments" -u "$MOKA_API_KEY:"
```

返回 `{"success": true, "departments": [ … ]}`，每项：`name`、`departmentId`（Moka ID）、`departmentCode`（你方 ID）、`parentCode`（null 为一级）、`parentId`、
`deletedByApi`（`1` = 被标记删除）、`type`（`1` 普通 / `2` 门店）、`localizedNames[]{locale, propValue}`。失败 `{"success": false, "errorMessage": "…"}`。

无凭证探测（2026-09-11，#A2）：伪造 Key → HTTP 500 `{"code":-1,"success":false,"msg":"无法识别的认证信息"}`。

## 4. 全量同步部门（PUT，危险）

**Endpoint**: `PUT https://api.mokahr.com/api-platform/v2/departments`

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `departments[]` | array | 是 | 部门数据（**必须是完整清单**） |
| `departments[].name` | string | 是 | 部门名称 |
| `departments[].departmentCode` | string | 是 | 你方部门 ID |
| `departments[].parentCode` | string | 是 | 上级部门 code，一级部门传 `"0"` |
| `departments[].type` | number | 否 | `1` 普通（默认）/ `2` 门店 |
| `departments[].sequence` | number | 否 | 0–10000，可两位小数；空则排最后 |
| `departments[].localizedNames[]` | array | 否 | `{locale: "en-US", propValue: "…"}`；只能传已开通语言，`name` 默认作 zh-CN |
| `operatorEmail` | string | 否 | 系统内操作人邮箱（记日志） |

文档原文的同步规则：系统没有、请求有 → 新增；都有 → 更新（已标删除的恢复正常）；**系统有、请求没有 → 标记已删除，需要手动进 Moka 把它合并到其他部门才能真正删除**。

```python
def full_sync_departments(depts: list[dict]):
    """depts 必须是 eHR 的完整部门树；少传一个就会被标删除。"""
    assert depts, "拒绝用空列表做全量同步"
    res = ats_call("PUT", "/v2/departments", json={"departments": depts})
    if res.get("code") not in (0, 200):
        raise RuntimeError(res)
    return res.get("data", {}).get("result")   # {"new": n, "delete": n, "update": n}
```

- 返回示例 `{"code":0,"msg":"success","data":{"result":{"new":0,"delete":0,"update":0}}}`；失败示例 `{"code":-1,"msg":"false"}`。
  ⚠ 文档自相矛盾：返回字段表写「`200`: 成功」，示例是 `0`——按 `code in (0, 200)` 判。
- **先看 `result.delete`**：非预期的删除数说明清单不完整，应立刻告警。
- 文档里 OAuth2 的 Bearer 调用示例正是这个接口（见 `auth.md` 第 4 节）。
- 可能的错误信息（文档原文）：部门 ID 重复、部门重复（同父同名）、父级部门未找到、部门的父级部门不能直接（间接）为自身。

## 5. 增量新增部门

**Endpoint**: `POST https://api.mokahr.com/api-platform/v2/departments/sync/incremental`

body 与第 4 节相同（`departments[]` 的 `name`、`departmentCode`、`parentCode` 必填），**只新增**。

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/v2/departments/sync/incremental" -u "$MOKA_API_KEY:" \
  -H "Content-Type: application/json" \
  -d '{"departments":[{"departmentCode":"RD-01","name":"研发一部","parentCode":"RD"}]}'
```

- 返回示例 `{"code":0,"msg":"success"}`；字段表同样写 200 成功（⚠ 同上）。
- 可能的错误（文档原文）：「部门名称: XXX, 编号XXX的部门编号重复」（请求内重复，或与已同步部门重复）、父级部门未找到、同父下名称已存在。
- 父部门必须已存在或在同一请求里：按层级从上到下排序后提交。
- 无凭证探测（2026-09-11，#B4）：路径存在（伪造 Key → HTTP 500 鉴权错误）。

## 6. 更新部门

**Endpoint**: `POST https://api.mokahr.com/api-platform/v2/departments`

- 以 `departmentCode` 为主键更新；**要改 `departmentCode` 本身时，传 `departmentId`（Moka ID）**，此时以 `departmentId` 为主键（文档原文）。
- 字段同第 4 节，另有 `departments[].departmentId`。返回 `{"code":0,"msg":"success"}`。

## 7. 删除 / 合并部门

**Endpoint**: `DELETE https://api.mokahr.com/api-platform/v1/departments`（**DELETE 带 JSON body**）

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `departments[].department_code` | string | 是 | 要删的部门（注意这里是**下划线** `department_code`） |
| `departments[].target_department_code` | string | 否 | 传了 = 把数据合并到目标部门并删除原部门；不传 = 只标记"已删除"，仍需在系统内手动删 |
| `email` | string | 是 | 已在 Moka 注册的操作人邮箱 |

```python
res = ats_call("DELETE", "/v1/departments",
               json={"departments": [{"department_code": "RD-OLD", "target_department_code": "RD-01"}],
                     "email": "hr@example.com"})
if not res.get("success"):
    raise RuntimeError(res.get("errorMessage"))
```

返回：成功 `{"code":0,"msg":"成功","success":true,"errorMessage":"","data":{}}`；失败示例 `{"code":625011,"msg":"department_code(…)在系统中已存在","success":false,…}`。
部分 HTTP 客户端 / 代理会丢弃 DELETE 的 body——用 `requests` 的 `json=` 没问题，自研网关要确认会转发。

## 8. 同步用户账号

**Endpoint**: `POST https://api.mokahr.com/api-platform/v2/users/syncInfo`（**每次最多 100 条**）

| 参数（`usersInfo[]` 每项） | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `uniqueType` | string | 是 | `email` / `number` / `phone`：这次用哪个字段判断是不是同一个账号 |
| `email` / `number` / `phone` | string | 与 `uniqueType` 对应的那个必填 | — |
| `name` / `nickname` | string | 否 | 姓名 / 花名 |
| `roleId` | int | **首次创建必填** | 自定义角色 ID（`GET /v1/users/roles?type=all` 查） |
| `departmentCode` | array | 是 | 部门 code 列表。**传空数组 `[]` 被视为"所有部门"**（文档原文） |
| `deactivated` | int | 是 | `0` 不禁用 / `1` 禁用。**首次创建时传 1，用户不会被创建** |
| `superiorEmail` | string | 否 | 上级邮箱；**传空字符串会清空汇报关系**，配合 `updateSuperiorEmail` 控制 |
| `updateDepartment` | boolean | 否 | **不传默认 `true`**：会用本次 `departmentCode` 覆盖部门 |
| `updateSuperiorEmail` | boolean | 否 | 是否更新上级 |
| `autoActivated` | int | 否 | `1` 自动激活，默认 0 |
| `thirdPartyId` | string | 否 | 单点登录用；没有传 `""` |
| `locale` / `timezone` | string | 否 | `zh-CN` / `en-US`；时区如 `Asia/Shanghai` |
| `costCenterCode` | string | 否 | 仅成本中心开关开启且角色为 HR（role ≥ 30）及以上时生效 |

```python
def sync_users(users: list[dict]):
    for i in range(0, len(users), 100):                     # 每批 ≤ 100
        res = ats_call("POST", "/v2/users/syncInfo", json={"usersInfo": users[i:i + 100]})
        for err in res.get("data", {}).get("errorList", []):   # 部分失败不影响整体 code
            print("同步失败:", err["data"].get("email") or err["data"].get("number"), err["msg"])

sync_users([{"uniqueType": "email", "email": "li@example.com", "name": "李四", "roleId": 60,
             "departmentCode": ["RD-01"], "deactivated": 0, "updateDepartment": True}])
```

返回：`{"code":200,"msg":"success","data":{"successCount":1,"errorList":[]}}`；失败项在 `errorList[]{data, msg, code}`（文档示例 `"参数错误: roleId"`）。
文档的失败示例外层 `code:-1` 但 `msg` 仍是 `"success"`——**以 `successCount` / `errorList` 为准**。

## 9. 读取用户（V3）

**Endpoint**: `POST https://api.mokahr.com/open-api/ats/v3/users/list`（**前缀是 `/open-api/ats/v3`，不是 `/api-platform`**）

| 参数 | 说明 |
| :--- | :--- |
| `userId` / `roleId` / `email` / `phone` / `number` | 精确筛选 |
| `deactivated` | 0 可用 / 1 禁用 |
| `departmentIdType` + `departmentId` | `DEPARTMENT_ID`（默认，Moka ID）或 `DEPARTMENT_CODE`（你方 code） |
| `limit` | 默认 100，最大 500 |
| `order` | `DESC`（默认，按创建时间新到旧）/ `ASC`——**只有 ASC 时返回 `nextUserId`**，可做增量 |
| `nextUserId` | 翻页游标 |

返回 `{"code":0,"msg":"成功","data":{"userList":[…],"nextUserId":…}}`；`userList[]` 含 `userId`、`name`、`email`、`phone`、`number`、`roleId`、
`role`（0 内推人、5 前台、10 面试官、20 用人经理、25 高级用人经理、30 HR、40 管理员、50 超管）、`deactivated`、`pending`（待激活）、
`departmentsInfo.belongTo` / `inCharge`（所属 / 负责部门）、`superiorEmail`。

- ⚠ 文档自相矛盾：字段表写「非 200 代表失败」，示例 `code: 0`。
- 无凭证探测（2026-09-11，#A10）：伪造 Key → **HTTP 401** `{"code":-1,"msg":"无法识别的认证信息","subCode":"Unauthorized"}`，与 `/api-platform` 下的 HTTP 500 不同，是另一套网关。
- 旧版 `POST /api-platform/v1/users/list`（获取人事信息）仍在文档中；新代码用 V3。

## 10. 其他用户与职责接口

| 用途 | Endpoint |
| :--- | :--- |
| 查询角色 | `GET /api-platform/v1/users/roles?type=all`（`all` / `custom` / `builtin`），返回 `{"success":true,"data":[{"id","name","role","description"}]}` |
| 登出用户 | `POST /api-platform/v1/users/logout` |
| 工作交接 | `POST /api-platform/users/v2/handover` |
| 用户组 | `POST /api-platform/v1/userGroup/add` · `…/queryUserGroupList` · `…/addMember` · `…/deleteMember` · `…/listByGroupIds`；更新用 `/api-platform/v1/user_group/update`（注意下划线） |
| 职责同步 / 部门绑定职责成员 / 查询 | `POST /api-platform/v1/positions/syncInfo` · `POST /api-platform/v1/position/departmentUser` · `POST /api-platform/v1/dept_position_user/search` |
| 门店同步 | `PUT /api-platform/v1/stores` · `POST /api-platform/v1/get_stores` |

## 11. ⚠ 汇总

- ⚠ 文档自相矛盾：部门全量 / 增量 / 更新接口的成功码（示例 0，字段表 200）；V3 用户列表同样。
- ⚠ 文档自相矛盾：用户同步失败示例外层 `code:-1` 而 `msg:"success"`。
- 删除接口字段是 `department_code`（下划线），其余接口是 `departmentCode`（驼峰）。
