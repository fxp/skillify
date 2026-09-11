# 员工信息与任职记录：全量 / 增量拉取、按 ID 查、ID 反查、字段翻译

来源：open.italent.cn 文档中心 › 新版接口 v3.0 › 组织员工 › 员工与任职；PaaS平台 › 数据服务 › 根据查询条件获取数据源；
社区文档「常见对接问题(组织员工)」「重要升级通知」（users.italent.cn pageId=109710166、250249832）。抓取于 2026-09-11。
**未用真实凭证验证**；报错与行为均为「文档原文，未实测」。鉴权、响应外壳、ID 类型见 `auth-and-conventions.md`；
时间窗滚动的通用规则与 `scroll_all()` 见 `organization-and-positions.md` 第 2 节。

路径前缀 `/TenantBaseExternal/api/v5/Employee/`，全部 `POST` + JSON。

## 目录

1. 数据模型：员工信息 + 任职记录
2. 该用哪个接口
3. 人员状态 / 雇佣关系 / 任职类型 / 审批状态：数字怎么传
4. 时间窗拉取员工（单条任职）`GetByTimeWindow`
5. 多条任职 `GetListByTimeWindow`、按组织拉 `GetEmployeeOfOrganization`
6. 按 UserID 查员工信息 / 任职记录
7. 用邮箱 / 工号 / 手机号反查 UserID
8. 字段值翻译：数据源接口（替代已下线的 enableTranslate）
9. 容易误判的字段语义

---

## 1. 数据模型

一个员工 = 一条**员工信息**（EmployeeInformation，`employeeInfo`：姓名、邮箱、证件、手机……，主键 UserID）
+ 若干条**任职记录**（EmploymentRecord，`recordInfo`：部门、职位、职务、工号、入职日期、直线经理、人员状态……）。
任职记录有时间轴（`startDate` / `stopDate`）和类型（主职、兼职……）。所以「员工在哪个部门」取决于你要**哪一条**任职记录：

- `isGetLatestRecord: true`（默认）→ **最新主职**：生效日期最大的那条（可能是未来生效的调动）；
- `isGetLatestRecord: false` → **当前生效主职**：「生效日期小于今天，失效日期大于今天的记录」。

做「当前组织架构 / 通讯录」通常要**当前生效**，默认值却是**最新**——这是最容易踩的一点。

## 2. 该用哪个接口

| 我要 | 接口 | 每批 / 每次上限 |
|---|---|---|
| 全量或增量同步员工 + 一条主职任职 | `Employee/GetByTimeWindow` | capacity ≤300，时间窗 ≤90 天 |
| 同上，但要员工的**多条**任职记录（兼职、历史） | `Employee/GetListByTimeWindow` | 同上 |
| 不限制当前 / 最新生效的多条任职 | `Employee/GetMoreListByTimeWindow`（本 skill 未整理字段） | |
| 某个组织（可含子组织）下的员工 | `Employee/GetEmployeeOfOrganization` | 同上（滚动） |
| 已知 UserID 取员工信息 | `Employee/GetBasicInfoByIds` | ≤300 个 |
| 已知 UserID 取任职记录 | `Employee/GetServiceInfoByIds` | ≤300 个 |
| 邮箱 → UserID | `Employee/GetUserIDByEmail` | 1 个 |
| 工号 → UserID | `Employee/GetUserIDsByJobNumbers` | **≤30 个** |
| 手机号 → UserID | `Employee/GetUserIDsByMobilesV5` | **≤30 个** |
| 某人的直线下级 | `Employee/GetJuniorById`（本 skill 未整理字段） | |
| 审批中的任职数据 | `Employee/GetListByBussinessType`（拼写如此；未整理字段） | |

**时间窗接口只返回审批生效（及可选审批通过）的数据**：「时间窗接口不可获取审批中的数据」（GetByTimeWindow 参考文档标题原文）。

## 3. 状态枚举：数字怎么传

⚠ 文档自相矛盾：这些字段的 schema 是**字符串枚举**（如 `EmployeeStatus: ["None","ForEntry","OnProbation",…]`），
而字段说明和全部请求示例用**数字**（`"empStatus":[1,2,3,7]`）。**按示例传数字**。下表的数字来自字段说明原文；
「schema 枚举名」一列按 schema 顺序对照，二者在说明给出的每个例子上都一致（对照是推断，⚠ 未实测）。

| 字段 | 数字（文档说明原文） | schema 枚举名（顺序） |
|---|---|---|
| `empStatus` 人员状态 | 「[1,2,3,7]（待入职、试用、正式、返聘）」；示例 `[1,2,3,4,5,6,8,12]` | None, ForEntry, OnProbation, InService, TransferredOut, TransferredIn, Retirement, Reemploy, Dimission, Die, StopReemploy, ForReemoloy, Informal |
| `employType` 雇佣关系 | 「[0,2]，表示内部员工、实习生」 | Inner, Other, Trainee |
| `serviceType` 任职类型 | 「[0]，表示主职」 | MainJob, ParttimeJob, Reemploy, Loan, Expatriate |
| `approvalStatuses` 审批状态 | 「2 审批通过(Success)、4 审批生效(Effective)，其他状态不可用」 | Draft, Approving, Success, Refused, Effective, Invalid, Rejected, Temporary |
| `timeWindowQueryType` | 「1修改时间、2业务修改时间」（**从 1 开始**） | ModifiedTime, BusinessModifiedTime |

注意 `timeWindowQueryType`、`extQueries[].queryType` 从 **1** 起编号，而人员状态等从 **0** 起——不能用「枚举下标」统一推。
完整选项表在文档的「查看可用选项」链接（`/#/datasource-options?fieldName=EmployeeStatus&metaName=TenantBase.EmploymentRecord`），
其背后接口匿名访问返回 404，**本 skill 没有抓到完整的数字 ↔ 含义表**（⚠ 文档未说明，拿到凭证后用数据源接口查，见第 8 节）。

**`empStatus` 与 `withDisabled` 的互补规则**（GetByTimeWindow 字段说明原文）：
1. `empStatus` 不为 null 且非空 → 用 `empStatus`；
2. `empStatus` 为 null 且 `withDisabled=false` → 查待入职、试用、正式、返聘；
3. `empStatus` 为 null 且 `withDisabled=true` → 查全部状态；
4. `empStatus` 为**空数组** → 查试用、正式、返聘（**不含待入职**）。

`null` 和 `[]` 结果不同。要离职员工：`withDisabled: true`（或显式列出离职状态码）。

## 4. 时间窗拉取员工（单条任职）

### 根据时间窗滚动查询变动的员工与单条任职信息
**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/GetByTimeWindow`
**用途**: 全量 / 增量同步员工信息 + 一条任职记录（「若存在多条，优先取未删除的主职」）。限流 50/秒、1500/分钟。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `startTime` / `stopTime` | date-time | 是 | — | ≤90 天（超出 417，见 organization 文件第 2 节） |
| `timeWindowQueryType` | int | 否 | ⚠ 文档未说明 | 1 修改时间 / 2 业务修改时间；**建议显式传** |
| `scrollId` | string | 否 | — | 首次 `""`，10 秒内续拉 |
| `capacity` | int | 否 | 100 | ≤300 |
| `empStatus` | int[] | 否 | null | 见第 3 节互补规则 |
| `employType` | int[] | 否 | 内部员工 | 说明原文「[0,2]，表示内部员工、实习生」；`1` 按 schema 顺序对应 `Other`，推断为外部人员（⚠ 推断，未实测） |
| `serviceType` | int[] | 否 | 主职 | |
| `approvalStatuses` | int[] | 否 | [4] 生效 | 只可 2、4 |
| `isGetLatestRecord` | bool | 否 | **true** | true 最新主职；false 当前生效主职 |
| `withDisabled` | bool | 否 | false | 是否包含离职 |
| `isGetOfferRecord` | bool | 否 | false | 是否带出 Offer 记录 |
| `isWithDeleted` | bool | 否 | false | |
| `columns` | string[] | 否 | null=全部 | 只决定查不查值，不改变响应结构 |
| `extQueries` / `sort` | | 否 | | 见 organization 文件第 2 节 |
| `enableTranslate` | bool | — | — | **已停用**（2026-03-13 起新客户禁止使用） |

```bash
curl -sS -X POST 'https://openapi.italent.cn/TenantBaseExternal/api/v5/Employee/GetByTimeWindow' \
  -H "Authorization: Bearer ${BEISEN_TOKEN}" -H 'Content-Type: application/json' \
  -d '{"timeWindowQueryType":2,"startTime":"2026-09-10T00:00:00","stopTime":"2026-09-11T00:00:00",
       "scrollId":"","capacity":300,"withDisabled":true,"isGetLatestRecord":false,
       "employType":[0,2],"columns":["Name","Email","JobNumber","OIdDepartment","EmployeeStatus","LastWorkDate"]}'
```

```python
# 增量：上次同步时间 → 现在；按业务修改时间；含离职；取当前生效主职
rows = scroll_all(client, "/TenantBaseExternal/api/v5/Employee/GetByTimeWindow",
                  {"timeWindowQueryType": 2, "withDisabled": True, "isGetLatestRecord": False,
                   "employType": [0, 2]}, last_sync, now)
for r in rows:
    emp, rec = r["employeeInfo"], r.get("recordInfo") or {}
    upsert(user_id=emp["userID"], name=emp["name"], email=emp.get("email"),
           dept_oid=rec.get("oIdDepartment"), job_number=rec.get("jobNumber"),
           status=rec.get("employeeStatus"), last_work_date=rec.get("lastWorkDate"))
```

**示例响应**（文档原文，节选）

```json
{"scrollId": "DXF1ZXJ5QW5k…", "isLastData": true, "total": 1,
 "data": [{"originalId": null,
           "employeeInfo": {"userID": 101539902, "name": "test", "email": "****@beisen.com",
                            "businessModifiedTime": "2022-03-09T16:30:33", "objectId": "04866f9e-…",
                            "modifiedTime": "2022-03-09T16:30:33", "stdIsDeleted": false},
           "recordInfo": {"userID": 101539902, "oIdDepartment": 4745657, "startDate": "2022-03-09T00:00:00",
                          "stopDate": "9999-12-31T00:00:00", "jobNumber": null, "entryDate": "2022-03-09T00:00:00",
                          "employType": 2, "serviceType": 0, "approvalStatus": 4, "employeeStatus": "1",
                          "pOIdEmpAdmin": 101532496, "isCurrentRecord": true, "oIdOrganization": 900127666}}]}
```

**recordInfo 关键字段**（文档字段表）：`userID`、`oIdDepartment`（部门 OId，int）、`oIdOrganization`（机构 OId，int）、`jobNumber`（工号）、
`entryDate`、`lastWorkDate`、`regularizationDate`（转正日期）、`probation`（试用期月数）、`employType`（int）、`serviceType`（int）、
`serviceStatus`（int）、`approvalStatus`（int）、**`employeeStatus`（string，如 `"1"`）**、`oIdJobPost`（string）、`oIdJobPosition`（GUID）、
`oIdJobLevel`、`oidJobGrade`、`pOIdEmpAdmin`（直线经理 UserID）、`pOIdEmpReserve2`（虚线经理）、`isCurrentRecord`、`objectId`、
`businessModifiedTime`、`modifiedTime`、`stdIsDeleted`、`customProperties`（租户自定义字段）。

⚠ 文档未说明：同是状态，`employType` / `approvalStatus` 在响应里是 int，`employeeStatus` 是 string。比较时统一 `str()`。

**注意事项**（文档原文）
- 默认排序「先按照UserID升序，然后按照创建时间降序」。
- 「本接口需要有员工信息（EmployeeInformation）和任职记录（EmploymentRecord）的两者的对象权限，否则提示权限异常」——权限在连接器里配；
  参考文档标题里出现的报错原文 `access denied! no permission for object 'xxxx'`。
- 「自定义字段查询时……会指定过滤掉不存在的自定义字段，而非校验提示」——自定义字段名写错不报错，只是条件被忽略。
- 累计工龄 `workYearTotal`、累计司龄 `workYearCompanyTotal` 等「非实时数据，而是每天定时任务刷新」。
- 「开始结束时间参数，不传递时分秒，则时分秒默认为 00:00:00」。

## 5. 多条任职 / 按组织拉

### 根据时间窗滚动查询变动的员工与多条任职信息
**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/GetListByTimeWindow`
参数与 `GetByTimeWindow` 相同（`isGetOfferRecord` 在此接口无效：「只支持时间窗获取员工信息和单条任职记录接口」）。
响应 `data[]` 里任职记录是**数组**（响应字段表 186 行，比单条版多出任职集合），结构差异 ⚠ 本 skill 未逐字段整理，写解析代码前对照文档响应示例。

### 滚动查询指定组织下的员工与单条任职信息
**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/GetEmployeeOfOrganization`
**用途**: 取某组织（可含子组织）下的员工。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `orgOId` | int | 是 | 组织 OId |
| `includeSubOrg` | bool | 是 | 是否包括子组织（字段说明写「默认否」却标必填，⚠ 文档自相矛盾，**显式传**） |
| `queryDate` | date-time | 是 | 字段说明写「默认查询当前日期，null也表示当前日期」却标必填（⚠ 同上） |
| `scrollId` | string | 是 | 首次 `""` |
| `isWithDisable` | bool | 否 | 是否包含**停用组织** |
| `withDisabled` | bool | 否 | 是否包含**离职员工**（两个字段名只差一个 d，含义完全不同） |
| 其余 | | 否 | `empStatus`、`employType`、`serviceType`、`approvalStatuses`、`isGetLatestRecord`、`capacity`、`sort`、`extQueries`、`isWithDeleted`、`columns` |

注意：这个接口**没有 `startTime` / `stopTime`**，警告里却照抄了时间窗的「建议限定查询范围在90天」（⚠ 文档自相矛盾，可忽略）。
`empStatus` 在这里的规则：「传空数组默认查询正式在职、入职试用和退休返聘状态的员工」。
异常示例：`{"scrollId":null,"isLastData":false,"total":0,"data":null,"code":"417","message":"OrgOId不能为空且为正整数！"}`。

## 6. 按 UserID 查

### 根据员工UserID集合获取未删除的员工相关信息
**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/GetBasicInfoByIds`
限流 50/秒、1300/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `oIds` | int[] | 是 | **员工 UserID**，≤300 个（参数名叫 oIds，传的是 UserID） |
| `isWithDeleted` | bool | 否 | |
| `columns` | string[] | 否 | 「默认查询列：UserID、审批状态ApprovalStatus」 |

⚠ 文档自相矛盾：字段类型是 int 数组，提示却写「示例：["388551","388552"]」（字符串）。按 schema 传 int。
返回 `data[]` 是扁平的员工信息（`userID`、`name`、`email`、`mobilePhone`、`gender`（0 男 1 女）……），**不含任职**。
「若一个UserID有多条员工信息数据，优先取审批生效的，而后审批中的，最后其他状态的」；「不支持查询审批状态为不通过、作废、草稿、驳回状态的数据」。
缺参异常原文：`{"data":null,"code":"417","message":"Value cannot be null.\r\nParameter name: Argument name: Ids is null"}`。

### 根据员工UserID集合获取指定条件的任职记录相关信息
**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/GetServiceInfoByIds`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `oIds` | int[] | 是 | 员工 UserID，≤300 |
| `option` | int | 否 | 「0：条件查询-使用参数中的其他条件进行查询、1：直接获取最新主职任职记录，其他条件自动忽略、2：直接获取当前生效的主职任职记录，其他条件自动忽略」 |
| `empStatus` / `employType` / `serviceType` / `approvalStatus` | int[] | 否 | 注意这里是 **`approvalStatus`**（时间窗接口是 `approvalStatuses`）；默认：未删除、审批生效、主职 |
| `isWithDeleted` / `columns` | | 否 | |

⚠ 文档自相矛盾：`option` 说明写数字 0/1/2，请求示例却是 `"option": "None"`。按说明传数字。
要「当前在哪个部门」：`{"oIds": [...], "option": 2}`。

## 7. 邮箱 / 工号 / 手机号 → UserID

### 根据员工Email获取员工UserID
**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/GetUserIDByEmail`

```json
{"email": "zhangsan@beisen.com"}
```
响应（文档原文）：`{"data": "101485821", "code": "200", "message": null}` —— **`data` 是字符串形式的 UserID**，找不到时 `data` 为 null。
警告原文：「Email需小写」。调用前 `.strip().lower()`。「支持查询审批中、审批通过、审批生效的员工信息，如有多条，优先取审批生效的」。

### 根据员工工号批量获取对应UserID
**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/GetUserIDsByJobNumbers`

```json
{"jobNumbers": ["ALlLXLJ01960", "ALlLXLJ00995"]}
```
- **一次 ≤30 个**（「一次操作不能超过30条数据」）。
- 响应是**逐条状态**：`data[] = {jobNumber, userId, code(int), msg}`，外层 `code` 仍是 `"200"`。
  必须逐条看 `data[i].code == 200`；文档响应示例里一条 `code: 417, msg: "所查工号无对应人员信息"` 的记录同时带着 `userId: 460098245`
  （⚠ 文档自相矛盾）——**code 不是 200 的条目不要用它的 userId**。
- 「由于工号同步到员工信息有延迟，不建议新增之后立刻通过工号查询」；不查已删除、不查不通过 / 作废 / 草稿 / 驳回。

### 根据员工手机号批量获取对应UserID
**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/GetUserIDsByMobilesV5`
`{"mobiles": ["133****5565"]}`，一次 ≤30 个，逐条 `data[] = {mobile, userId, code, msg}`，规则同工号。限流 40/秒、1300/分钟。

```python
def job_numbers_to_user_ids(client, job_numbers):
    out, missing = {}, []
    for i in range(0, len(job_numbers), 30):
        body = client.post("/TenantBaseExternal/api/v5/Employee/GetUserIDsByJobNumbers",
                           {"jobNumbers": job_numbers[i:i + 30]})
        for item in body.get("data") or []:
            if str(item.get("code")) == "200" and item.get("userId"):
                out[item["jobNumber"]] = item["userId"]
            else:
                missing.append((item.get("jobNumber"), item.get("msg")))
    return out, missing
```

## 8. 字段值翻译：数据源接口

`recordInfo.employeeStatus = "1"`、`place = "1108"`、`employmentSource = "d5c77d41-…"` 这类是**编码 / GUID**，文本要另外翻译。
旧做法 `enableTranslate: true` → `translateProperties`（如 `"EmployTypeText":"实习生"`）**已下线**（重要升级通知原文：
「请求参数：enableTranslate……停止支持，请勿继续传入；响应参数：translateProperties……不再返回数据源结果，默认返回null」，
正式限制时间 2026-03-13；新客户必须改用数据源接口）。

### 根据查询条件获取数据源
**Endpoint**: `POST https://openapi.italent.cn/dataservice/api/DataSource/GetDataSource`
**用途**: 批量取数据源（选项列表）的 value ↔ text。限流 30/秒、1000/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `app` | string | 是 | 应用编码，如 `Compensation` |
| `metaObjectName` | string | 是 | 实体编码，如 `TenantBase.EmployeeInformation` |
| `listFilter` | array | 是 | **≤10 个** |
| `listFilter[].dsName` | string | 是 | 数据源编码 |
| `listFilter[].fieldName` | string | 否 | 字段编码（查字段上绑定的自定义数据源时用） |
| `listFilter[].values` | string[] | 否 | 只翻译这些 value |
| `listFilter[].isShowInactive` | bool | 否 | 是否返回未启用项 |

响应 `data[] = {key, fieldName, application, metaObjectName, dataSourceResults: [{text, value, isActive, ...}]}`。
错误码（文档原文）：`000001` 参数缺失、`000002` 参数过长、`1000024` listFilter 数量过多（不能超过 10 个）、`401` Token 过期、`403` 联系平台授权。

⚠ 文档未说明：组织员工标准字段（EmployeeStatus、EmployType……）各自对应的 `app` / `dsName` 取值——文档指向的社区参考页
（pageId 95813878 / 95813839 / 95813842 / 103981374）未抓取。拿到凭证后先用它把第 3 节的数字表补全。

## 9. 容易误判的字段语义（文档原文）

- `lastWorkDate`：「最后工作日当天员工是在职员工，最后工作日的后一天员工人员状态为离职」。
- `ModifiedTime` vs `BusinessModifiedTime`：系统修改（如定时刷新工龄）会更新前者、不更新后者；增量同步业务变化用业务修改时间（`timeWindowQueryType: 2`），
  否则每天会收到大量“没有业务变化”的记录（参考文档标题原文：「为什么部分数据的修改时间是凌晨」）。
- `columns` 只控制查不查值：没选的字段仍出现在 JSON 里且为 null，不要把 null 当成“该员工没有这个值”。
- `originalId`：第三方系统主键，只有当初通过写接口带了 originalId 才有值。
- `employType` 默认只查内部员工（说明原文「默认查询内部员工」），实习生要显式放 `2`；外部人员推断为 `1`（⚠ 推断，未实测）。
