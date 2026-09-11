# 通讯录：部门、人员、用户组、角色

> 来源：https://developer.fxiaoke.com/openapi_v2/ 的 common/address/*（成员、用户组、角色）、object/OrganizationAndPersonnel/*（部门对象、人员对象）、
> FAQ「人员对象查不到数据」（抓取于 2026-09-11），旧版 wiki 通讯录接口（artiId=1079 / 1089 / 1090 / 1093 / 1116 / 1122）。
> **本文件全部为文档原文，未实测。** 请求头、thirdTraceId、`FxkClient` 见 `auth.md`。

## 目录
1. 三套入口怎么选
2. 部门下成员：`/cgi/user/list`、`/cgi/user/simpleList`
3. 部门列表与部门对象 DepartmentObj
4. 人员对象 PersonnelObj（按手机号 / 姓名 / 状态查员工）
5. 旧版文档里的人员接口（新版未收录）
6. 用户组
7. 角色
8. 人员对象查不到 / 查不全
9. 本文件的 ⚠

---

## 1. 三套入口怎么选

纷享的「通讯录」能力分散在三处，参数风格各不相同：

| 我要做什么 | 用哪套 | Endpoint | 参数风格 |
| --- | --- | --- | --- |
| 拉某部门（或全公司）的员工清单 | 成员接口 | `/cgi/user/list`（详细）、`/cgi/user/simpleList`（简略） | **参数平铺在 body 顶层**，没有 `data` 包裹 |
| 按条件查部门 / 员工、增改部门 / 员工 | 对象接口 | `/cgi/crm/v2/data/query|get|create|update`，apiName `DepartmentObj` / `PersonnelObj` | 标准对象接口，条件在 `data.search_query_info` |
| 用户组、角色 | special 接口 | `/cgi/crm/v2/special/*`、`/cgi/crm/v2/bi/lwt/query` | 参数在 `data` 里 |

员工 ID 有两种形态：CRM 员工 ID（如 `1000`，新版传参默认）和 openUserId（`FSUID_…`，旧版传参）。见 `auth.md` 第 3、9 节。

## 2. 部门下成员

### 2.1 获取部门下成员信息（详细）

**Endpoint**: `POST /cgi/user/list?thirdTraceId={uuid4}`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| includeNull | Boolean | 否 | 默认 false |
| departmentId | Int | 是 | 部门 ID（**顶层，不在 data 里**） |
| fetchChild | Boolean | 是 | true 同时取所有子部门员工；false / 不传只取当前部门 |
| showDepartmentIdsDetail | Boolean | 是 | true 时返回主属部门 `mainDepartmentId` 与附属部门 `attachingDepartmentIds` |

```bash
curl -sS -X POST "https://$FXK_HOST/cgi/user/list?thirdTraceId=$(uuidgen | tr A-Z a-z)" \
  -H "authorization: Bearer $FXK_TOKEN" -H "x-fs-ea: $FXK_EA" -H "x-fs-userid: $FXK_USER_ID" \
  -H 'Content-Type: application/json' \
  -d '{"departmentId": 999999, "fetchChild": true, "showDepartmentIdsDetail": true}'
```

```python
users = fxk.post("/cgi/user/list", {"departmentId": 999999, "fetchChild": True,
                                    "showDepartmentIdsDetail": True})["userList"]
active = [u for u in users if not u.get("isStop")]
```

**示例响应**（节选）

```json
{
  "userList": [
    {
      "openUserId": "1000", "account": "111", "name": "小明", "nickName": "小明", "isStop": false,
      "email": "xiaoming@qq.com", "mobile": "15611110000", "gender": "M", "position": "销管",
      "departmentIds": [111111, 1001], "employeeNumber": "111", "hireDate": "2023-03-16",
      "createTime": 1758789217451, "leaderId": "1000"
    }
  ],
  "traceId": "E-O.827xxxxxx", "errorCode": 0, "errorMessage": "success", "errorDescription": "成功"
}
```

- 列表在顶层 `userList`，不在 `data` 里。
- `isStop: true` 表示停用（离职）。
- 新版示例里 `openUserId` 的值是 `"1000"`（员工 ID 形态），旧版 wiki 是 `FSUID_…`——取决于传参方式 / convertUserId（⚠ 文档未明说）。

### 2.2 获取部门下成员简略信息

**Endpoint**: `POST /cgi/user/simpleList?thirdTraceId={uuid4}`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| departmentId | Int | 是 | 非负整数；**`999999` 代表全公司** |
| fetchChild | Boolean | 否 | 默认 false |

返回 `userList[]`：`openUserId`、`name`、`nickName`。只要 ID ↔ 姓名映射时用它。

- ⚠ 文档自相矛盾：2.2 明确 `999999` 是全公司，2.1 没有这句；旧版部门对象返回里根部门 `parent_id` 也是 `999999`（「全公司」），但旧版 wiki 另一处又写「根部门ID为0」。

## 3. 部门列表与部门对象 DepartmentObj

部门列表**没有单独的 list 接口**，用对象查询（旧版 wiki 1079：「与预设对象一致」）：

**Endpoint**: `POST /cgi/crm/v2/data/query?thirdTraceId={uuid4}`，`dataObjectApiName: "DepartmentObj"`

```json
{
  "data": {
    "dataObjectApiName": "DepartmentObj",
    "search_query_info": {
      "limit": 100, "offset": 0, "filters": [],
      "orders": [{"fieldName": "_id", "isAsc": true}],
      "fieldProjection": ["_id", "name", "parent_id", "parent_id__r", "status"]
    }
  }
}
```

旧版 wiki 1079 给出的返回字段：

| 字段 | 说明 |
| --- | --- |
| `_id` | 部门 ID |
| `name` | 部门名称 |
| `parent_id` | 父部门 ID（列表形式，如 `["999999"]`）；`parent_id__r` 里有 `deptName`、`deptId`、`status` |
| `status` | 0 启用 / 1 停用 / 2 删除——**非启用状态会导致部门下人员无法登录** |

- 部门创建 / 修改 / 详情 / 删除走 `data/create|update|get|delete`，`dataObjectApiName: "DepartmentObj"`，结构同 `crm-preset-objects.md`。
- ⚠ 文档未说明：新版部门对象的字段清单（新版页只有通用示例），用 `object/describe` 查 `DepartmentObj`。

## 4. 人员对象 PersonnelObj

**Endpoint**: `POST /cgi/crm/v2/data/query?thirdTraceId={uuid4}`，`dataObjectApiName: "PersonnelObj"`

旧版 wiki 1090 列出的常用过滤字段：

| field_name | 含义 |
| --- | --- |
| `phone` | 手机号 |
| `full_name` | 姓名 |
| `status` | 员工状态：0 启用 / 1 停用 |
| `create_time` | 创建时间（毫秒时间戳） |
| `user_id` | 员工 openUserId（旧版 wiki 1089「根据 openUserId 查询员工」） |

按手机号查员工：

```python
def find_employee_by_mobile(fxk, mobile: str):
    body = {"data": {"dataObjectApiName": "PersonnelObj", "search_query_info": {
        "limit": 10, "offset": 0,
        "filters": [{"field_name": "phone", "operator": "EQ", "field_values": [mobile]},
                    {"field_name": "status", "operator": "EQ", "field_values": ["0"]}],
        "orders": []}}}
    data = fxk.post("/cgi/crm/v2/data/query", body)["data"]
    return data.get("dataList", [data]) if isinstance(data, dict) else data
```

- 人员对象的创建 / 修改 / 详情 / 改负责人同样走 `data/create|update|get|changeOwner`（新版文档有对应页面，结构与客户一致）。
- **人员对象有单独的查询权限控制**，经常「查不到 / 查不全」，见第 8 节。
- ⚠ 文档未说明：新版人员对象的字段清单；用 describe 查 `PersonnelObj` 确认 `phone`、`full_name`、`user_id` 在你们企业里的实际 apiName。

## 5. 旧版文档里的人员接口（新版未收录）

以下接口只出现在旧版 wiki（旧版传参：body 带 `corpAccessToken` + `corpId`），新版文档没有对应页面，⚠ 是否仍然可用、是否支持新版 header 未知：

| 接口 | Endpoint（旧版 wiki） | 关键参数 |
| --- | --- | --- |
| 手机号查员工 | `POST /cgi/user/getByMobile` | `mobile`；返回 `empList[]`（`openUserId`、`name`、`mainDepartmentIds`、`departmentIds`、`status` 等） |
| 按修改时间增量查员工 | `POST /cgi/user/get/batchByUpdTime` | `startTime` / `endTime`（毫秒，可空）、`pageSize`（默认 20，**最大 1000**）、`pageNumber`（默认 1，页码从 1 开始）、`showDepartmentIdsDetail` |

`batchByUpdTime` 返回 `pageNumber`、`pageCount`、`totalCount`、`lastChangedTime`、`employees[]`（`openUserId`、`name`、`isStop`、`mobile`、`departmentIds`、`mainDepartmentId`……）。
注意它用**页码**分页，和对象查询的 offset 分页不同。新代码优先用第 4 节的 PersonnelObj 查询（`last_modified_time GT …` 做增量）。

## 6. 用户组

| 动作 | Endpoint | body（都在 `data` 里） |
| --- | --- | --- |
| 获取用户组列表 | `POST /cgi/crm/v2/special/usergroupList` | `{}` |
| 添加用户组 | `POST /cgi/crm/v2/special/usergroupInsert` | `name`、`description`（都必填） |
| 获取用户组用户列表 | `POST /cgi/crm/v2/special/usergroupMemberList` | `groupId` |
| 向用户组添加用户（增量） | `POST /cgi/crm/v2/special/usergroupMemberInsert` | 见原文页 `common/address/user/group.html` |
| 修改用户组用户（覆盖） | `POST /cgi/crm/v2/special/usergroupMemberUpdate` | 见原文页 `common/address/user/update.html` |
| 删除用户组 | `POST /cgi/crm/v2/special/usergroupDelete` | 见原文页 `common/address/user/delete.html` |

```python
groups = fxk.post("/cgi/crm/v2/special/usergroupList", {"data": {}})["data"]
# [{"groupId": "1111111111", "groupName": "AAA负责人", "description": ""}, ...]
members = fxk.post("/cgi/crm/v2/special/usergroupMemberList",
                   {"data": {"groupId": groups[0]["groupId"]}})["data"]["employeeIds"]
```

- 注意返回形态不同：`usergroupList` 的 `data` 是**列表**；`usergroupMemberList` 的 `data` 是 map，成员在 `data.employeeIds`。
- 「增量」和「覆盖」是两个接口：覆盖接口会把用户组成员整体替换成你传的列表，同步时别用错。

## 7. 角色

| 动作 | Endpoint | body |
| --- | --- | --- |
| 获取角色列表 | `POST /cgi/crm/v2/special/roleGetRoleList` | `data.AuthContext.appId`（必填，示例 `"CRM"`） |
| 获取用户对应的角色 | `POST /cgi/crm/v2/special/getRolesByUsers` | 见原文页 `common/address/role/get.html` |
| 通过角色获取用户 | `POST /cgi/crm/v2/bi/lwt/query` | `data.roleCodes`（列表，必填）、`data.AuthContext`（可选） |
| 通过主角色获取用户 | `POST /cgi/crm/v2/bi/lwt/query` | 见原文页 `common/address/role/major.html` |
| 添加 / 修改 / 删除角色 | `/cgi/crm/v2/special/roleAdd`、`roleUpdate`、`roleDelete` | 见原文页 |
| 批量添加用户角色（增量） | `/cgi/crm/v2/special/batchAddUserRole` | 见原文页 |
| 批量设置用户角色（覆盖） | `/cgi/crm/v2/special/batchSetUserRoles` | 见原文页 |
| 删除指定角色的人员 | `/cgi/crm/v2/special/deleteByUserIds` | 见原文页 |

```json
{"data": {"AuthContext": {"appId": "CRM"}}}
```

角色列表返回 `data[]`：`roleCode`（如 `00000000000000001`）、`roleName`、`groupName`、`roleType`、`appId`、`description`、`delFlag`。

- ⚠ 文档自相矛盾：「通过角色获取用户」和「通过主角色获取用户」两个页面给的是**同一个路径** `/cgi/crm/v2/bi/lwt/query`；路径看起来也不像角色接口（像 BI 查询）。调用前核实。
- 「通过角色获取用户」的返回结构 ⚠ 文档未说明。
- 表中标「见原文页」的接口本 skill 没有逐字段整理，参数表在 https://developer.fxiaoke.com/openapi_v2/common/address/ 下对应页面。

## 8. 人员对象查不到 / 查不全

FAQ「人员对象查不到数据」+ 旧版 wiki 27（文档原文，未实测）：

- 人员对象有独立的查询权限控制，**CRM 管理员默认也没有全部人员数据权限**（管理员「除人员对象」外全都能看）。
- 方案一：找纷享客服在 CRM 产品灰度里申请「人员对象接口查询权限」。
- 方案二：后台「数据管理权限 → 数据共享」里给人员对象新建共享规则：规定哪些人员数据被共享、共享范围、谁能看。
  **如果共享给指定的某个人，接口的 `x-fs-userid`（旧版 `currentOpenUserId`）必须就是这个人**，否则仍查不到。
- 共享规则生效较慢：用该员工登录网页版，在人员列表里能看到数据，才说明规则已生效。
- 只是要员工名单时，第 2 节的 `/cgi/user/list` 不走人员对象权限（⚠ 文档未明说，是否受可见范围限制未证实）。

## 9. 本文件的 ⚠

- ⚠ 文档自相矛盾：全公司 / 根部门 ID 是 `999999` 还是 `0`（第 2.2 节）。
- ⚠ 文档未说明：`/cgi/user/list` 返回的 `openUserId` 取哪种形态；部门 / 人员对象的新版字段清单（第 2、3、4 节）。
- ⚠ 文档未说明：旧版 `getByMobile`、`batchByUpdTime` 是否仍可用、是否支持新版 header（第 5 节）。
- ⚠ 文档自相矛盾：两个角色查用户接口共用 `/cgi/crm/v2/bi/lwt/query`（第 7 节）。
- ⚠ 文档未说明：`/cgi/user/list` 是否受人员对象权限限制（第 8 节）。
