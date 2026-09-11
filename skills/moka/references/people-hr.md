# Moka People 人事 API：组织、员工、待入职

> 来源：Moka People API 在线文档 <https://people.mokahr.com/docs/api/view/v1.html>（抓取于 2026-09-11）。
> **文档版，未用真实凭证调用验证。** 报错 / 行为描述除标「无凭证探测（2026-09-11）」外均为「文档原文，未实测」。
> 所有接口的鉴权与签名见 `auth.md` 第 6 节；下文 `people_post(path, body, api_code, user_name)` 即那里的实现。
> 下文路径均相对 `https://api.mokahr.com/api-platform/hcm/oapi`。

## 目录

1. [People 通用规则（先读）](#1-people-通用规则先读)
2. [读部门](#2-读部门)
3. [写部门](#3-写部门)
4. [读员工任职数据（含增量）](#4-读员工任职数据含增量)
5. [字段元数据与枚举值](#5-字段元数据与枚举值)
6. [新增 / 更新 / 离职员工](#6-新增--更新--离职员工)
7. [待入职员工](#7-待入职员工)
8. [职位、职务、职级](#8-职位职务职级)
9. [其他人事数据速查](#9-其他人事数据速查)
10. [本 skill 不覆盖的 People 模块](#10-本-skill-不覆盖的-people-模块)
11. [⚠ 汇总](#11--汇总)

---

## 1. People 通用规则（先读）

1. **一个能力一个 apiCode。** 在 People「设置 - 对外接口设置」为每个要用的接口建一条配置（选数据源），生成各自的 `apiCode`。
   例：读员工 → 数据源【员工任职信息】；读部门 → 【批量-组织架构信息】；新增部门 → 【新增组织部门接口】；新增员工 → 【新增员工接口】；待入职 → 【批量新增待入职员工】。
2. **同一个 URL，数据由 apiCode 决定。** `POST /v1/batch/data` 在文档里同时是「员工任职数据接口」「员工异动数据接口」「查询IM员工数据接口」的地址——
   返回哪种数据取决于你传的 apiCode 对应哪个数据源。**拿错 apiCode 会拿到另一种数据结构**，而不是报错（⚠ 未实测）。
3. **`userName` 决定数据范围。** 读员工类接口必须带 `userName`（某员工邮箱），按该人角色的数据权限过滤；文档推荐超级管理员。写接口大多不带。
4. **频率限制按接口、按企业计**（文档原文，每个接口单独标注），常见 `3次/秒/企业, 60次/分钟/企业`；字段元数据只有 **5 次/分钟**；待入职写入 **1 次/秒、20 次/分钟**。超限返回 HTTP `600` / 错误码 `600`（见 `errors-and-limits.md`）。
5. **响应信封**：读接口 `{"code":200,"msg":"操作成功","data":{"list":[…],"labelList":[…],"size":n,"total":n,"pageNum":…,"pageSize":…}}`；
   员工写接口是**两层信封**（外层 `code:0`，内层 `data.code:200`，再到逐条 `success`），见第 6 节。
6. **字段类型看 `labelList`**：每个字段的 `type`（1 字符串、2 日期、3 数字、4 是否、5 单选、6 地址、7 手机、9 证件、13 职务、14 职位、15 职级、16 工作地点、17 人员、21 公司…）。
   单选类（type 5/13/14/15/16/17/21）会**额外返回 `xxx_id`**；地址类返回 `xxx_province_code` / `_city_code` / `_county_code`；
   手机类额外返回区号，文档原文「会返回"xxx_county_code"或者"xxx_country_code"，请客户做好兼容」。
7. **空值三种形态**（文档原文）：字段缺失、`null`、`""`，都要兼容。
8. **读写日期格式不对称**：读出来多是 `"yyyy-MM-dd"` 字符串；**写入员工时日期字段是毫秒时间戳（Long）**；待入职写入的 `onBoardingDate` 类型写 `Date`（⚠ 具体格式未说明）。
9. **自定义字段**：读时 key 形如 `<分组>-DF_<随机串>`；写时放 `extend_fields`（员工）或 `extendFields`（待入职 / 部门），单选字段 key 以 `_id` 结尾。
10. 无凭证探测（2026-09-11，#P1–#P5）：不带鉴权 / 伪造 Key / 伪造签名 / 不存在的路径，一律 **HTTP 403** `{"success":false,"msg":"无法识别的认证信息"}`。

## 2. 读部门

### 组织部门数据接口
**Endpoint**: `POST /v1/org/department/batchData`（3 次/秒、60 次/分钟）
**apiCode 数据源**：【批量-组织架构信息】；**无 `userName`**

| 参数（body） | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `pageSize` | int | 是 | ≤ 200 |
| `pageNum` | int | 是 | 页码 |
| `nodeUidList` | Array&lt;Long&gt; | 否 | 部门 ID，≤ 200；与 `nodeCodeList` **二选一** |
| `nodeCodeList` | Array&lt;String&gt; | 否 | 部门编码，≤ 200 |
| `haveUsed` | int | 否 | `0` 停用 / `1` 启用 |

```python
def iter_departments(api_code: str):
    page = 1
    while True:
        res = people_post("/v1/org/department/batchData", {"pageSize": 200, "pageNum": page, "haveUsed": 1}, api_code)
        items = res["data"]["list"]
        yield from items
        if page * 200 >= res["data"]["total"] or not items:
            return
        page += 1
```

`data.list[]` 关键字段：`node_uid`（部门 ID）、`node_code`（部门编码）、`dept_sample_name`（部门名）、`dept_name`（全路径，如 `Moka/开发部/开发一组`）、
`effect_date`、`dept_type`、`superior_dept{id,name}`（根节点为 null）、`dept_level{id,name}`、`dept_hierarchy`、
`dept_director{dept_director_id,dept_director_name,dept_director_emp_no}`、`dept_hrbp{…}`、`tree_order`（越小越靠前）、`have_used`、自定义字段 `…-DF_…`。

## 3. 写部门

### 新增组织部门
**Endpoint**: `POST /v1/org/department/batchCreate`（3 次/秒、60 次/分钟），apiCode 数据源【新增组织部门接口】

| 参数（`data[]` 每项） | 必填 | 说明 |
| :--- | :--- | :--- |
| `nodeCode` | 是 | 部门编码 |
| `deptSampleName` | 是 | 部门名称 |
| `effectDate` | 是 | 生效日期（示例 `"2024-04-06"`） |
| `superiorDept.superiorDeptCode` / `superiorDept.superiorDeptId` | 是 | 上级部门编码 / ID（表中两者都标必填，⚠ 是否可只传其一未说明） |
| `deptType` / `deptHierarchy` | 否 | 部门类型 / 层级 |
| `deptDirector{deptDirectorId, deptDirectorEmpNo}` / `deptHrbp{deptHrbpId, deptHrbpEmpNo}` | 否 | 负责人 / HRBP |
| `treeOrder` | 否 | 同级排序 |
| `extendFields[]{fieldName, fieldValue, fieldEmployeeNo}` | 否 | 自定义字段 |

返回：`{"code":200,"msg":"操作成功","data":[{"nodeUid":124213423,"nodeCode":"yc00000022","code":200,"msg":"写入成功"},{"nodeUid":null,"nodeCode":"yc00000021","code":400,"msg":"写入失败:新增部门失败"}]}`
——**外层 200 不代表每条都成功**，逐条看 `data[].code`（200 成功 / 400 失败）。

- 文档示例 URL 是 `http://localhost:8007/oapi/v1/org/department/batchCreate`（内部地址），真实地址以「基本信息」一栏为准：`https://api.mokahr.com/api-platform/hcm/oapi/v1/org/department/batchCreate`。
- 修改：`POST /v1/org/department/batchUpdate`；启停：`POST /v1/org/department/batch/update/haveUsed`（均 3 次/秒、60 次/分钟，字段见文档）。
- 父部门要先存在：批量写时按层级从上到下排序后分批提交。

## 4. 读员工任职数据（含增量）

### 员工任职数据接口
**Endpoint**: `POST /v1/batch/data`（3 次/秒、60 次/分钟），apiCode 数据源【员工任职信息】，**`userName` 必填**

| 参数（body） | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `pageSize` | int | 是 | ≤ 200 |
| `pageNum` | int | 是 | 页码 |
| `uuidList` | Array&lt;Long&gt; | 否 | 员工 ID，≤ 2000 |
| `employeeNoList` / `officeEmailList` / `telephoneList` / `idNoList` | Array&lt;String&gt; | 否 | 工号 / 公司邮箱 / 手机 / 证件号，各 ≤ 2000 |
| `startDate` / `endDate` | String | 否 | **员工信息更新时间**范围，`yyyy-MM-dd HH:mm:ss`——用它做增量同步 |

```python
def iter_employees_updated(api_code: str, user_name: str, start: str, end: str):
    page = 1
    while True:
        res = people_post("/v1/batch/data",
                          {"pageSize": 200, "pageNum": page, "startDate": start, "endDate": end},
                          api_code, user_name=user_name)
        items = res["data"]["list"] or []
        yield from items
        if not items or page * 200 >= (res["data"].get("total") or 0):
            return
        page += 1

# 每小时增量：iter_employees_updated(code, "admin@corp.com", "2026-09-11 09:00:00", "2026-09-11 10:00:00")
```

`data.list[]` 关键字段（文档原文整理）：

| 字段 | 说明 |
| :--- | :--- |
| `uuid` | 员工在 People 的唯一 ID（= webhook 的 `employeeId`） |
| `employee_no` / `realname` / `nickname` | 工号 / 姓名 / 花名 |
| `department` + `department_id` | 部门名 + 部门 ID（= `node_uid`） |
| `report_leader` + `report_leader_id` | 直接上级 |
| `employee_type` + `employee_type_id` | 员工类型：1 正式、2 实习生、3 劳务派遣、4 兼职（⚠ id 表写"兼岗"、名称表写"兼职"，文档自相矛盾） |
| `employee_status` + `employee_status_id` | 1 在职、2 离职、3 试用、4 待入职 |
| `duty` / `position` / `duty_level`（各带 `_id`） | 职务 / 职位 / 职级 |
| `on_boarding_date` / `end_probation_date` / `leave_date` / `birthday` | `yyyy-MM-dd` 字符串 |
| `telephone` + `telephone_country_code` | 手机 + 区号（如 `+86`） |
| `office_email` / `personal_email` | 邮箱 |
| `id_no` + `id_type`（1 身份证、2 护照、3 港澳通行证、4 台湾通行证、5 外国人永久居留证） | 证件 |
| `attachment_*` / `id_card_back` | 附件数组 `{id,name,url}`，**url 24 小时过期** |

**注意事项**

- 文档原文：「员工数据不包含"待入职"的数据」——待入职用第 7 节。
- 同一数据的其他版本：`/v2/batch/data`（权限）、`/v3/batch/data`（含停用信息）、`/v4/batch/data`（含停用信息 / 权限），参数表同为 `pageSize ≤ 200` + `userName`；
  要拿**已离职 / 停用**信息时用 v3 / v4（字段差异见文档对应小节）。
- 员工异动数据也走 `/v1/batch/data`，但时间过滤是 `yyyy-MM-dd`，且 `startDate/endDate` 与 `ydStartDate/ydEndDate` 必须有一组、范围 ≤ 180 天、`uuidList ≤ 200`（文档原文）。

## 5. 字段元数据与枚举值

| 用途 | Endpoint | 频率 | 说明 |
| :--- | :--- | :--- | :--- |
| 系统对象与字段定义 | `POST /v1/personnel/v1/get_all_obj_fields` | 3 次/秒、**5 次/分钟** | body `{objIdList, objNameList, isHaveUsed}`，都不传返回全部；`userName` 必填 |
| 单选字段的枚举值 | `POST /v1/personnel/v1/get_enum_values` | 3 次/秒、**5 次/分钟** | 用上面返回的字段 `id`（attrId）查（字段见文档） |

- 每分钟只能调 5 次：**启动时拉一次缓存**，不要在每次写员工前调用。
- 写员工时的 `gender_id`、`employee_type_id`、`office_address_id` 等"选项 Id"都要从这里查，不能写中文名。

## 6. 新增 / 更新 / 离职员工

| 用途 | Endpoint | apiCode 数据源 |
| :--- | :--- | :--- |
| 新增员工 | `POST /v2/core/rosters/addEmployees` | 【新增员工接口】 |
| 更新员工 | `POST /v2/core/rosters/updateEmployees` | 更新员工接口（⚠ 数据源名称以文档该节为准） |
| 离职员工 | `POST /v2/core/rosters/leaveEmployees` | 【离职员工接口】 |
| 新增 / 更新（支持批量附件） | `POST /v3/core/rosters/addEmployees` · `/v3/core/rosters/updateEmployees` | — |

均为 3 次/秒、60 次/分钟，**无 `userName`**。body 统一 `{"data": [ {…员工…}, … ]}`。

**新增员工 `data[]` 常用字段**（文档原文整理；必填性文档未标注，⚠）

| 字段 | 类型 | 写法 |
| :--- | :--- | :--- |
| `employee_no` / `realname` / `nickname` | String | — |
| `gender_id` / `nationality_id` / `country_id` / `employee_type_id` / `months_of_probation_id` / `office_address_id` | 选项 Id | 从第 5 节查 |
| `birthday` / `begin_work_time` / `on_boarding_date` / `end_probation_date` / `company_start_date` | Long | **毫秒时间戳** |
| `telephone` / `contact_phone` | json | `{"country_code": "+86", "value": "13800000000"}` |
| `id_no` | json | `{"id_type_value": 2, "id_no": "…", "id_type_id": 2, "id_type_display": "护照"}` |
| `address` / `household_address` | json | `{"province": "120000", "city": "120000", "county": "120102", "value": "详细地址"}` |
| `department` | json | `{"department_id": "147716"}` 或 `{"department_no": "NO.215619"}`，都有时以 id 为准 |
| `report_leader` / `dashed_report_leader` / `mentor` | json | `{"report_leader_id": 75782241}` 或 `{"report_leader_no": "1915619"}` |
| `position_id` / `duty_id` | Long | 职位模式租户用 `position_id`，职务模式租户用 `duty_id` |
| `duty_level_id` / `manage_duty_level_id` | Long | 职级 / 管理职级 |
| `officeEmail` | String | ⚠ 这里是驼峰，读接口返回的是 `office_email` |
| `extend_fields` | json | 自定义字段；单选 key 以 `_id` 结尾 |

```python
emp = {
    "employee_no": "E2026001", "realname": "张三", "gender_id": "1",
    "telephone": {"country_code": "+86", "value": "13800000000"},
    "department": {"department_no": "RD-01"},
    "on_boarding_date": 1791417600000,            # 毫秒时间戳，不是 "2026-10-08"
    "employee_type_id": 1,
}
res = people_post("/v2/core/rosters/addEmployees", {"data": [emp]}, api_code=ADD_EMP_APICODE)
for row in res["data"]["data"]:                   # 外层 code:0 → 内层 code:200 → 逐条 success
    if not row["success"]:
        print("失败", row["employee_no"], row["errorMessage"])   # 如"工号已被其他人使用"
```

**响应（文档原文）**：成功与失败**外层都是** `{"code":0,"msg":"成功","data":{"code":200,"msg":"操作成功","data":[…]}}`，
区别只在 `data.data[].success` / `errorMessage`。只判外层会把失败当成功。

**离职员工** `data[]`：`employee_uid` / `employee_no`、`leave_date`（毫秒）、`leave_handover_date`、`event_type`（如「被动离职」）、`event_reason_id`（选项 Id）、`leave_detail_reason`、`leave_handle_remark`。
文档失败示例：`"员工已离职不能重复离职"`。

## 7. 待入职员工

### 批量添加待入职员工
**Endpoint**: `POST /v1/basic/ob/employee/batchCreate`（**1 次/秒、20 次/分钟**），apiCode 数据源【批量新增待入职员工】

| 字段（`data[]`，**驼峰命名**，每次 ≤ 100 条） | 必填 | 说明 |
| :--- | :--- | :--- |
| `realName` | 是 | 姓名 |
| `onBoardingPlan` | 是 | 入职计划 ID |
| `department` | 是 | `{departmentId}` 或 `{departmentNo}` 二选一 |
| `employeeTypeId` | 是 | 员工类型 ID |
| `onBoardingDate` | 是 | 入职时间（类型 Date，⚠ 格式未说明） |
| `telephoneCountryCode` + `telephone` | 是 | 区号 + 手机 |
| `personalEmail` | 是 | 个人邮箱 |
| `idNoIdType` + `idNo` | 是 | 证件类型 ID + 证件号 |
| `employeeNo` / `reportLeader{employeeId 或 employeeNo}` / `positionId` / `dutyId` / `dutyLevelId` / `officeAddressId` / `periodEndDate` / `monthsOfProbationId` | 否 | — |
| `extendFields[]` | 否 | `{fieldName, fieldValue, fieldEmployeeNo, fieldTelephoneCountryCode, …}` |

- **同一批里不能有重复的个人电话、证件号、个人邮箱**（文档原文），且要通过系统校验才能写入。
- 返回：`{"code":200,"data":{"successList":[{"index":0,"onBoardingUid":39223}],"failedList":[{"index":1,"errorList":["错误提示"]}]}}`——按**请求数组下标**对回。
- 注意命名风格：这里是 `realName` / `onBoardingDate`（驼峰），第 6 节员工接口是 `realname` / `on_boarding_date`（下划线）。
- 更新 / 取消：`POST /v1/basic/ob/employee/batchUpdate`、`POST /v1/basic/ob/employee/batchCancel`（同为 1 次/秒、20 次/分钟）。

### 待入职员工数据
**Endpoint**: `POST /v1/roster/onboarding`（3 次/秒、60 次/分钟）
- ⚠ 文档自相矛盾：同一节里两张表，一张写 `pageSize` 非必填、不超过 **50**，另一张写必填、不超过 **200**。按 ≤ 50 调。

## 8. 职位、职务、职级

租户要么是**职位模式**、要么是**职务模式**（文档多处用「仅职位模式租户有该字段」区分）：员工上只会有 `position_id` 或 `duty_id` 其一。

| 用途 | Endpoint | 分页 |
| :--- | :--- | :--- |
| 职位列表 | `POST /v2/core/org/getPositionPageList` | `pageNum` + `pageSize ≤ 200` |
| 职务列表 | `POST /v2/core/org/getDutyPageList` | `pageNum` + `pageSize ≤ 200` |
| 职级列表 | `POST /v2/core/org/getRankInfoList` | `pageSize ≤ 200` + `nextCursor`（⚠ 表里把 `nextCursor` 描述为「页码」且必填，与其他接口的游标含义不一致） |
| 新增 / 变更 / 启停职位 | `POST /v2/core/org/batchAddPosition` · `batchUpdatePosition` · `batchUpdatePositionStatus` | 5 次/秒、60 次/分钟 |
| 新增 / 变更 / 启停职务 | `POST /v2/core/org/batchAddDuty` · `batchUpdateDuty` · `batchUpdateDutyStatus` | 5 次/秒、60 次/分钟 |

## 9. 其他人事数据速查

| 数据 | 读 | 写 | 分页 |
| :--- | :--- | :--- | :--- |
| 合同 | `POST /v2/core/contract/getContractPageList` | `batchAddContract` · `batchUpdateContract` · `batchDeleteContract`（2 次/秒、30 次/分钟） | pageNum/pageSize |
| 异动 | `POST /v1/batch/data`（异动数据源的 apiCode） | `POST /v2/core/rosters/batchAddJobChange` · `batchUpdateJobChange` · `batchDeleteJobChange` | — |
| 兼岗 | `POST /v2/core/rosters/batch_get_concurrentPost` | — | `nextCursor` + `hasMore` |
| 成本中心 | `POST /v1/user/batch_get_cost_center` · `POST /v1/org/costCenterInfo` | `POST /v1/user/batch_set_cost_center` | `nextCursor` |
| 法人公司 | `POST /v1/org/get_legal_company` | `create_company` · `update_company` · `update_company_status` | `nextCursor`（首次不传，`hasMore` 为 true 时续传） |
| 个人履历 / 家庭成员 | `POST /v1/roster/personal/resume` · `POST /v1/roster/family/personnel` | `POST /v2/core/rosters/addResumeAndExtend` 等 | pageNum/pageSize ≤ 200 |
| 员工的招聘信息 | `POST /v1/recruitmentInfo/batchGetEmployeeRecruitmentInfo` | — | pageSize ≤ 200 |
| 通用附件上传 | — | `POST /v1/attachment/uploadAttachment`（50 次/秒、200 次/分钟） | — |

## 10. 本 skill 不覆盖的 People 模块

假勤（打卡、请假、加班、出差、排班、假期余额）、薪酬（薪资档案、核算、参保）、绩效、审批表单、自定义分组、BI 报表、IM 员工绑定——
接口都在同一份文档 <https://people.mokahr.com/docs/api/view/v1.html> 的「假勤接口API」「薪酬接口API」「绩效接口API」等章节，鉴权与签名同第 1 节。

## 11. ⚠ 汇总

- ⚠ 文档自相矛盾：`/v1/roster/onboarding` 的 `pageSize`（≤50 非必填 vs ≤200 必填）；`employee_type_id=4` 是"兼职"还是"兼岗"；`getRankInfoList` 的 `nextCursor` 描述为页码。
- ⚠ 文档未说明：新增员工各字段必填性；待入职 `onBoardingDate` 的具体格式；部门写入 `superiorDeptCode` / `superiorDeptId` 是否可只传其一。
- ⚠ 文档未说明：用错数据源的 apiCode 调 `/v1/batch/data` 会报错还是返回别的数据。
- 文档示例 URL `http://localhost:8007/oapi/…`（新增部门）是内部地址，不能用。
