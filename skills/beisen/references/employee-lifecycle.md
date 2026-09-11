# 入职 / 转正 / 调动 / 离职：员工生命周期写接口

来源：open.italent.cn 文档中心 › 新版接口 v3.0 › 组织员工 › 员工与任职、外部ID映射（抓取于 2026-09-11）。
**未用真实凭证验证**；报错与行为均为「文档原文，未实测」。这些都是**写接口**，会真实改变租户里的员工数据，
先在沙箱或测试租户跑通（沙箱域名见 `auth-and-conventions.md` 第 1 节，⚠ 文档未正式说明）。

路径前缀 `https://openapi.italent.cn/TenantBaseExternal/api/v5/`，全部 `POST` + JSON（删除类为 `DELETE`），
响应外壳 `{"code":"200","message":…,"data":…}`，`code` 是**字符串**，业务错误为 `"417"`。

## 目录

1. 状态机：哪个接口能对哪种状态的人用
2. 所有写接口共通的规则
3. 新建待入职 `Employee/CreateForEntry`
4. 待入职 → 入职 `Employee/Entry`；取消入职 `Employee/CancelEntry`
5. 直接新建在职 / 外部人员 / 实习生 `Employee/Create`
6. 试用期转正 `Employee/ProbationPositive`
7. 调动 `Employee/Transfer`
8. 离职 `Employee/Dimission` / 离职申请 `Employee/DimissionApproval`
9. 外部 ID 映射 `SourceIdMapping/UpdateOriginalIdByTargetId`
10. 其他生命周期接口（只列入口）

---

## 1. 状态机

```
                CreateForEntry                Entry
  (不存在) ─────────────────────▶ 待入职 ───────────────▶ 试用 / 正式 ── ProbationPositive ──▶ 正式
     │                              │  CancelEntry / DelayEntry / DeleteForEntry
     │ Create（直接建在职/外部/实习生）                                 │
     └──────────────────────────────────────────────▶ 在职 ──── Transfer（调动）
                                                                       └── Dimission / DimissionApproval ──▶ 离职
```

| 接口 | 只能用于 | 明确不支持（文档原文） |
|---|---|---|
| `CreateForEntry` | 首次新建待入职 | — |
| `Create` | 首次新建在职员工、外部人员、实习生 | 「不适用场景：新建待入职员工」 |
| `Entry` | 待入职状态员工 | 「员工非待入职状态，或不存在无法使用该接口」；「接口无法支持电子签署业务，若需电子签署，则必须在页面处理」 |
| `CancelEntry` | 待入职状态员工 | 同上 |
| `ProbationPositive` | 试用期内部员工 | 「外部人员、已离职人员、实习生、非试用期员工不支持试用期转正」；「不支持转正申请，请在页面进行操作」 |
| `Transfer` | 已入职的正式员工或实习生 | 「不支持调动申请，请在页面进行操作」；「外部人员、已离职人员不支持调动」 |
| `Dimission` | 已入职的正式员工或实习生 | 「不支持离职申请，请在页面进行操作」；「不支持离职外部人员、已离职人员」 |
| `DimissionApproval` | 同上，**发起离职申请**（走审批） | 「外部人员、已离职人员不支持发起离职申请」 |

⚠ 文档自相矛盾：`Dimission` 写「不支持离职申请，请在页面进行操作」，但同目录下就有 `DimissionApproval`（发起离职申请）和 `ApprovalDimissionStart`（发起离职审批），
调动也有 `ApprovalTransferStart`。理解为：`Dimission` / `Transfer` 是**直接生效、不走审批**；要走审批用带 Approval 的接口。

状态不对时的典型报错（文档原文）：`{"code":"417","message":"该人员当前状态不能办理当前业务"}`（Entry）、
`{"code":"417","message":"非试用员工不支持试用期转正操作"}`、`{"code":"417","message":"外部人员不支持离职操作"}`。

## 2. 共通规则（文档原文，多处重复出现）

1. **UserId 与 OriginalId 有且仅有一个**：「人员UserId标识（OId）或外部ID标识（OriginalId，第三方系统唯一标识ID（非北森系统））必须有且仅有一个有值」。
2. **外部 ID 引用**：新建时传 `originalId`，「系统中会自动创建一个外部ID和内部ID字段映射关系，供后续更新、删除等操作使用」；
   之后引用部门、经理等可用 `XXXOriginalId`（如 `oIdDepartmentOriginalId`、`pOIdEmpAdminOriginalId`、`oIdOrganizationOriginalId`），
   「前提是系统中已通过新增操作关联该外部ID，否则报错」。
3. **3 秒防重**（Transfer、Dimission、DimissionApproval、ProbationPositive）：「为防止并发请求导致重复数据，请求参数相同时，3秒内仅能请求一次，否则进行错误提示」。
   → **重试前至少等 3 秒**，否则你的重试会被当成重复请求报错。
4. **编制校验**（Transfer、ProbationPositive）：「该接口内部包含组织编制超编校验逻辑」——超编会被拒。
5. **自定义字段** `customProperties: {"字段编码": 值}`（区分大小写，「自动忽略非自定义字段和不存在的字段」——**写错字段名不报错，值丢失**）；
   标准多语言等可选字段放 `optionalSysProperties`，如 `{"Name_fr":"…"}`。
6. **清空字段** `emptyFields: ["Desc","Note"]`：「字段未传值或者null表示不更新该字段，如需清空，请添加对应字段名称……该列表优先级高，若同一个字段既赋值又清空，则优先清空」。
7. **时间格式**：「时间类型的参数，如果携带时分秒，请注意格式为 2022-02-09T04:30:30」。
8. 引用型字段的取值：部门 / 机构 `oIdDepartment`、`oIdOrganization` 是 int OId；`oIdJobPost`、`oIdJobSequence` 「必须为空或数字」（传字符串数字）；
   `oIdJobPosition`、`oIdJobLevel`、`oidJobGrade` 「必须为空或GUID」；人员来源 / 用工形式 / 人员类别是 GUID（各自实体的业务数据）。

⚠ 文档自相矛盾（字段大小写）：schema 字段名是 `pOIdEmpAdmin` / `pOIdEmpReserve2`，多个请求示例写成 `poIdEmpAdmin` / `poIdEmpReserve2`。
JSON 反序列化是否大小写不敏感 ⚠ 文档未说明——按 schema 写 `pOIdEmpAdmin`，拿到凭证后验证。

## 3. 新建待入职

### 新建待入职员工
**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/CreateForEntry`
**用途**: 首次创建一个待入职员工（员工信息 + 任职记录 + 可选合同）。限流 50/秒、1500/分钟。

提示原文：「必填项：姓名、电子邮件、部门、入职日期、雇佣关系、试用期」。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `employeeInformation` | object | 是 | 员工信息 |
| `employeeInformation.name` | string | 是 | 姓名 |
| `employeeInformation.email` | string | 是 | 电子邮件（租户内唯一，重复会 417） |
| `employeeInformation.originalId` | string | 否 | 第三方系统主键，建立映射 |
| `employeeInformation.iDType` / `iDNumber` | string | 否 | 证件类型（选项表未抓取）/ 证件号 —— **重聘判定默认按证件号** |
| `employeeInformation.mobilePhone`、`gender`、`birthday`、`inviteForActivation`… | | 否 | 共 90+ 字段，见文档 |
| `employmentRecord` | object | 是（按提示） | 任职记录 |
| `employmentRecord.oIdDepartment` | int | 是（按提示） | 部门 OId（或 `oIdDepartmentOriginalId`） |
| `employmentRecord.entryDate` | date-time | 是（按提示） | 入职日期 |
| `employmentRecord.employType` | int | 是（按提示） | 雇佣关系（0 内部员工、2 实习生，见 `employees.md` 第 3 节） |
| `employmentRecord.probation` | int | 是（按提示） | 试用期（月），0 = 无试用期 |
| `employmentRecord.jobNumber` | string | 否 | 工号 |
| `employmentRecord.oIdOrganization`、`pOIdEmpAdmin`、`oIdJobPost`、`oIdJobPosition`… | | 否 | |
| `employmentContract` | object | 否 | 合同（`firstPartyCode`、`contractType`、`effectiveDate`…） |

⚠ 文档未说明：提示里的 6 个必填项在 schema 里只有 `employeeInformation`、`name`、`email` 标了 required，其余字段的 required 标记缺失，以提示为准。

```bash
curl -sS -X POST 'https://openapi.italent.cn/TenantBaseExternal/api/v5/Employee/CreateForEntry' \
  -H "Authorization: Bearer ${BEISEN_TOKEN}" -H 'Content-Type: application/json' \
  -d '{"employeeInformation":{"name":"张三","email":"zhangsan@example.com","originalId":"HR-000123"},
       "employmentRecord":{"oIdDepartment":4744879,"entryDate":"2026-10-01T00:00:00","employType":0,"probation":3,"jobNumber":"E000123"}}'
```

```python
body = client.post("/TenantBaseExternal/api/v5/Employee/CreateForEntry", {
    "employeeInformation": {"name": "张三", "email": "zhangsan@example.com", "originalId": "HR-000123"},
    "employmentRecord": {"oIdDepartment": 4744879, "entryDate": "2026-10-01T00:00:00",
                         "employType": 0, "probation": 3, "jobNumber": "E000123"},
})
user_id = body["data"]["userId"]      # 另有 employeeInformationId / employmentRecordId（GUID）
```

响应（文档原文）：`{"data":{"employeeInformationId":"a363874a-…","employmentRecordId":"9d177c6b-…","userId":101501070},"code":"200","message":""}`。

**注意事项**
- 重聘 / 返聘：「根据【设置-入职-重聘/返聘判定规则】中设置规则判断是否重聘/返聘人员，默认根据证件号码判断，如果系统中存在证件号码相同人员则重聘入职该人员，
  若按设置中未开启匹配的规则匹配到系统中离职或退休人员，则提示人员重复」。
- 邮箱重复异常原文：`{"data":null,"code":"417","message":"电子邮箱与待入职的内部员工：…重复，请确认信息！"}`。
- 招聘系统里 Offer 转入职走的是招聘侧的「入职管理」接口（`/RecruitV6/api/v1/RecruitOnBoarding/*`，见 `recruiting.md`），单招聘未开通组织员工的租户用那一套。

## 4. 入职 / 取消入职

### 待入职员工入职
**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/Entry`
**用途**: 把待入职员工办理入职。限流 50/秒、1500/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `userId` | int | 二选一 | 「两个ID（UserId、OriginalId）必须有且仅有一个有值」 |
| `originalId` | string | 二选一 | |
| `employeeInformation` / `employmentRecord` / `employmentContract` | object | 否 | 「若未传递值，则直接使用新增待入职员工保存的已有值」 |

```json
{"originalId": "HR-000123"}
```
响应：`{"code":"200","message":null}`（没有 data）。

### 待入职员工取消入职
**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/CancelEntry`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `userIds` | int[] | 是 | ≤100 个 |
| `reasonForCancellation` | string | 否 | 取消原因（GUID，选项表未抓取） |

**批量接口会部分成功**（文档响应示例原文）：全部成功时 `{"data":null,"code":"200","message":"取消入职操作已完成，成功操作3个人员"}`；
部分失败时 `code` 仍是 `"200"`，失败明细在 `data.failDatas[] = {key, errorReason}`（如 `"该人员不是待入职人员"`、`"该人员不存在"`）。
**必须检查 `data.failCount`**。限流 50/秒、**500/分钟**。

## 5. 直接新建在职 / 外部人员 / 实习生

**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/Create`
字段与 `CreateForEntry` 基本相同（提示里的必填项也相同），响应同样返回 `userId`。限流 50/秒、1000/分钟。
批量版：`Employee/BatchCreateInService`（本 skill 未整理字段）。

## 6. 试用期转正

**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/ProbationPositive`
限流 30/秒、1000/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `userId` / `originalId` | | 二选一 | |
| `employmentRecord.regularizationDate` | date-time | 是 | 转正日期，≥1900-01-01 |
| `employmentRecord.probationResult` | string | 是 | 试用结果（选项编码，示例 `"26"`；选项表未抓取） |
| `employmentRecord.oIdDepartment`、`pOIdEmpAdmin`、`jobNumber`… | | 否 | 转正时可一并改的任职字段 |

⚠ 文档自相矛盾：提示写「必填项：转正日期（args.EmploymentRecord.positiveDate）」，字段表和示例里的字段名是 `regularizationDate`。按字段表写 `regularizationDate`。
「该操作不支持修改生效日期（ServiceInfoFields.StartDate）」。

## 7. 调动

### 直接调动已入职的正式员工或实习生
**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/Transfer`
限流 **30/秒、500/分钟**（比多数接口低）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `userId` / `originalId` | | 二选一 | |
| `employmentRecord` | object | 是 | |
| `employmentRecord.oIdDepartment` | int | 是 | 调动后部门 OId（或 `oIdDepartmentOriginalId`） |
| `employmentRecord.startDate` | date-time | 否 | 调动生效日期（示例中出现；是否必填 ⚠ 文档未说明） |
| `employmentRecord.pOIdEmpAdmin`、`oIdJobPost`、`oIdJobPosition`、`oIdJobLevel`、`place`… | | 否 | |

```python
client.post("/TenantBaseExternal/api/v5/Employee/Transfer", {
    "userId": 101501119,
    "employmentRecord": {"startDate": "2026-10-01T00:00:00", "oIdDepartment": 4744879, "pOIdEmpAdmin": 101178784},
})
```
异常原文：`{"code":"417","message":"指定的直线经理不存在"}`。调动产生一条新的任职记录（时间轴），读取时注意 `isGetLatestRecord`（见 `employees.md` 第 1 节）。

## 8. 离职

### 直接离职已入职的正式员工或实习生
**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/Dimission`
限流 40/秒、1300/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `userId` / `originalId` | | 二选一 | |
| `employmentRecord.lastWorkDate` | date-time | 是 | 最后工作日（「最后工作日当天员工是在职员工，最后工作日的后一天员工人员状态为离职」） |
| `employmentRecord.transitionTypeOID` | string | 否 | 异动类型（GUID） |
| `employmentRecord.addOrNotBlackList` | bool | 否 | 是否加入黑名单 |
| `employmentRecord.blackListAddReason` / `blackStaffDesc` / `remarks` | string | 否 | |

```json
{"userId": 101501119, "employmentRecord": {"lastWorkDate": "2026-09-30T00:00:00", "remarks": "个人原因"}}
```

### 对已入职的正式员工或实习生发起离职申请
**Endpoint**: `POST /TenantBaseExternal/api/v5/Employee/DimissionApproval`
同上结构；提示原文「最后工作日、预计最后工作日至少一个有值」（「预计最后工作日」的字段名 ⚠ 本 skill 未整理，见文档字段表）。

## 9. 外部 ID 映射

### 更新指定员工、组织的外部ID标识
**Endpoint**: `POST /TenantBaseExternal/api/v5/SourceIdMapping/UpdateOriginalIdByTargetId`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `targetId` | int | 是 | 组织 OId 或员工 UserID |
| `objectName` | string | 是 | 只支持 `Organization`、`EmployeeInformation` |
| `originalId` | string | 是 | 第三方系统主键 |

行为（文档原文）：「根据TargetId查找数据，匹配多条返回错误不更新，没有匹配到数据时新增一条映射关系」；
异常原文 `{"code":"417","message":"根据内部ID和对象匹配到多条数据"}`。存量员工（不是通过 API 建的）要用 originalId 调写接口，先用它补映射。

## 10. 其他生命周期接口（只列入口，本 skill 未整理字段）

| 接口 | 用途 |
|---|---|
| `Employee/UpdateEmployee` | 更新指定员工的员工信息与任职记录 |
| `Employee/BatchUpdateInService` | 批量更新在职员工 |
| `Employee/UpdateForEntry` | 编辑待入职 |
| `Employee/DelayEntry` | 待入职员工延期入职 |
| `Employee/EntryApprovalNew` | 待入职员工发起入职申请 |
| `Employee/PositiveForTrainee` / `PositiveForTraineeApproval` / `FinishTrainee` / `ForEntryForTrainee` | 实习生转正 / 转正申请 / 结束实习 / 实习生转正待入职 |
| `Employee/ApprovalTransferStart` / `ApprovalDimissionStart` / `ApprovalFinish` | 发起调动审批 / 发起离职审批 / 完成审批 |
| `Employee/StartDismissionHandoverProcess` | 发起离职交接流程 |
| `Employee/Retired` | 直接退休正式员工 |
| `DELETE Employee/DeleteForEntry`、`DELETE Employee/DeleteEmploymentRecord` | 删除待入职员工 / 删除指定任职记录 |
| `EmpSubset/*`、`Contract/*`、`ParttimeJob/*` | 员工子集（教育、家庭等）、合同协议、兼职 |

字段表在 open.italent.cn 文档中心；本地渲染副本 `beisen-workspace/pages/open/组织员工/员工与任职/`。
