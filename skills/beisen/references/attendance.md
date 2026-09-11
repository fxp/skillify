# 假勤：休假、假期余额、考勤记录、打卡（读取与推送）

来源：open.italent.cn 文档中心 › 新版接口 v3.0 › 假勤管理（休假 / 假期余额 / 考勤记录 / 打卡）；PaaS平台 › 开放平台 ›
「根据请求ID查询业务异步接口的任务处理状态」；社区文档「常见对接问题（假勤管理）」「常见对接案例（假勤管理）」（pageId 158367766、124882444）。
抓取于 2026-09-11。**未用真实凭证验证**；报错与行为均为「文档原文，未实测」。

路径前缀 `https://openapi.italent.cn/AttendanceOpen/api/v1/`，全部 `POST` + JSON，`Authorization: Bearer <access_token>`。

## 目录

1. 和组织员工接口不一样的地方（先看）
2. 休假：按开始日期取 / 按审批通过时间取
3. 假期余额
4. 考勤记录（日结果）
5. 打卡：读取
6. 推送：打卡数据、休假数据（异步）
7. 其他假勤接口（只列入口）

---

## 1. 和组织员工接口不一样的地方

| | 组织员工 v5 | 假勤 |
|---|---|---|
| 分页 | `scrollId` 滚动，10 秒过期 | **游标**：请求传 `queryCursor`，响应返回 `data.sortCursor` + `data.isLastPage` + `data.total` |
| 每页上限 | capacity ≤300 | **`pageSize` 默认 100，最高 100** |
| 时间格式 | `2021-01-01T00:00:00` | 响应多为 `"2020-09-29 18:00:00"`（空格分隔）；请求示例既有 `"2020-11-11"` 也有 `"2020-11-11 11:10:20"` |
| 人员 ID | UserID | `staffId` / `userId` / `userID`（不同接口字段名不同；两者区别 ⚠ 文档未说明，FAQ 有专门条目但答案未抓取） |
| 外壳 | `code` 字符串 | 查询类 `{"code":"200","data":{…}}`；**推送类 `{"Code":200,"Message":null}`（首字母大写）** |
| 同步 / 异步 | 同步 | 查询同步；**推送多为异步**，返回 200 ≠ 数据入库 |

⚠ 文档自相矛盾（游标字段名）：多个接口的 `queryCursor` 说明写「使用上一次查询返回的 QueryCursor」，但响应字段表和示例里只有 `sortCursor`。**把响应的 `data.sortCursor` 作为下一次的 `queryCursor`**。

通用翻页（Python）：

```python
def cursor_all(client, path, args, list_key):
    """假勤游标翻页。list_key: 'vacationList' / 'vacationRemainList' / 'items' / 'swipingCardDetails'"""
    out, cursor = [], None
    while True:
        body = client.post(path, {**args, "queryCursor": cursor, "pageSize": 100})
        data = body.get("data") or {}
        out.extend(data.get(list_key) or [])
        cursor = data.get("sortCursor")
        if data.get("isLastPage") or not cursor or not data.get(list_key):
            return out
```

## 2. 休假

### 获取休假数据（按休假开始日期）
**Endpoint**: `POST /AttendanceOpen/api/v1/Vacation/GetListByDate`
**用途**: 取「休假开始日期」为某一天的休假单。限流 40/秒、1500/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `day` | date | 是 | 休假开始日期，如 `"2020-11-11"` —— **一次一天** |
| `queryCursor` | string | 否 | 首次 null |
| `pageSize` | int | 否 | 默认 100，最高 100 |

关键响应字段 `data.vacationList[]`：`vacationId`、`staffId`、`staffEmail`、`attendanceOrg`、`vacationType`、`vacationStartDateTime`、`vacationStopDateTime`、
`vacationDuration`（**分钟**）、`dayValueOfDuration`（**天**）、`vacationDurationIncludeUnit`（如 `"0.5天"`）、`documentType`、`approveStatus`、`applicant`、`reason`。

⚠ 文档自相矛盾：字段表说 `vacationType` 是休假项目 GUID、`documentType` / `approveStatus` 是编码（如 `"1"`），响应示例却是
`"vacationType":"病假"`、`"documentType":"请假"`、`"approveStatus":"通过"`（中文文本）；示例里 `vacationDuration: 270` 配 `dayValueOfDuration: 0.5`、
起止时间只差 1 小时，也对不上。**解析时两种形态都兼容**，拿到凭证后按 verification-plan 核实。

### 根据审批通过时间获取休假数据
**Endpoint**: `POST /AttendanceOpen/api/v1/Vacation/GetVacationInfoByApprovalTime`
**用途**: 增量拉「某天审批完成」的休假单（适合每日同步到薪酬 / 三方考勤）。限流 50/秒、1500/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `approveStartDate` | date-time | 是 | 审批开始日期时间 |
| `approveStopDate` | date-time | 是 | 审批结束日期时间 |
| `approveStatus` | int | 否 | 不传 = 所有审批状态（「注：不返回审批中的数据」） |
| `queryCursor` / `pageSize` | | 否 | 同上 |

⚠ 文档自相矛盾（三处）：
1. 警告「单次只能查询一天的数据，即开始日期需要等于结束日期」，请求示例却是 `"approveStartDate":"2020-10-10","approveStopDate":"2020-10-14"`。**按警告一天一查**。
2. `approveStatus` 说明写「1 通过 1 审批中 2 不通过 3 作废 4 已驳回 5 草稿 6」，示例注释写「通过1，审批中2，不通过3，作废4，已驳回5，草稿6」，schema 是字符串枚举
   `NotKnow, ApprovePass, ApproveProcess, ApproveReject, ApproveAborted, ApproveRebut, ApproveRevoke, ApproveError`。只取已通过的：**传 1**（两处说法都认为 1=通过）。
   异常原文：`{"code":"417","data":[],"message":"ApproveStatus参数格式不正确,请参考接口文档修改后重试！"}`。
3. 提示说「不返回审批中的数据」，参数却能传「审批中」。

响应 `data.vacationList[]` 字段很多（157 行字段表），常用：`vacationId`、`userID`、`oIdVacationType`、`vacationItemName`、`vacationItemCode`（如 `"CasualLeave"`）、
`documentType`（int，请假 / 销假）、`approveStatus`（int）、`isCancel`（`"1"` 是 `"0"` 否，有无销假）、`vacationDuration`（分钟，**销假单为负数**，示例 `-420`）、
`vacationStartDateTime`、`vacationStopDateTime`、`halfDayStartOption` / `halfDayStopOption`、`approveCompleteDateTime`。

社区 FAQ（问题标题原文，答案在子页面未抓取）：「【获取休假数据】和【根据审批通过时间获取休假数据】接口，有何差别？」
「页面导入了休假数据，但是通过接口拿不到数据？」「接口返回的开始时间、结束时间都是0点？」——遇到这些现象先去 FAQ 查。

## 3. 假期余额

### 获取假期余额数据
**Endpoint**: `POST /AttendanceOpen/api/v1/VacationRemain/GetVacationRemainList`
限流 50/秒、1500/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `vacationItemCode` | string | 是 | 休假项目编码，如 `"AdjustLeave"` |
| `year` | int | 否 | 年份 |
| `queryCursor` / `pageSize` | | 否 | 每页最多 100 |

⚠ 文档自相矛盾：`vacationItemCode` 标必填，请求示例 `{"year":2021,"pageSize":1}` 却没传。**传上**。

响应 `data.vacationRemainList[]`：`userId`、`userName`、`userEmail`、`year`（string）、`vacationTypeName`、`currentYearLimit`（本年额度）、`currentYearRemain`（本年余额）、
`lastYearSurplusLimit` / `lastYearSurplusRemain`（结余）、`currentYearTotalRemain`（本年总余额）、`currentYearTotalLimit`、`transferStatus`（如 `"未结转"`）、
`currentYearEffectiveDate`、`lastYearSurplusEffectiveDate`。余额单位（天 / 小时）⚠ 文档未说明，取决于休假项目设置。

按人查：`VacationRemain/GetListByUserId`；离职余额：`VacationRemain/GetDimissionBalance`；旧接口 `VacationRemain/GetList` 标「不推荐」。

## 4. 考勤记录（每人每天的考勤结果）

### 获取考勤数据-新
**Endpoint**: `POST /AttendanceOpen/api/v1/AttendanceStatistics/GetAttendanceStatisticsList`
限流 **25/秒、750/分钟**。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `startDate` / `stopDate` | date | 是 | 「单次只能查询一天的数据，即开始日期需要等于结束日期」 |
| `queryCursor` / `pageSize` | | 否 | |

⚠ 文档自相矛盾：请求示例 `"startDate":"2020-08-01","stopDate":"2020-08-10"`（10 天）。按警告一天一查。

响应 `data.items[]`：`userId`、`cardNumber`、`swipingCardDate`、`status`（1 正常、2 异常）、`attendanceMethod`（2 正常考勤、3 不考勤、4 暂停考勤、5 打一次卡）、
`missingTime`（缺勤时长）、`times[]`（卡点：`actualTime` 实打卡、`patchCardTime` 补签点、`type`；未打卡时是 `"0001-01-01 00:00:00"`，**不是 null**）、`createdTime`、`modifiedTime`。
异常原文：`{"code":"417","message":"stopDate参数格式不正确,请参考接口文档修改后重试！"}`。

## 5. 打卡：读取

### 根据打卡日期获取对应打卡数据
**Endpoint**: `POST /AttendanceOpen/api/v1/SwipingCardData/GetSwipingCardsByDateV2`
限流 20/秒、1200/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `punchCardDate` | date | 是 | 打卡日期 `"2020-11-11"` |
| `userIds` | int[] | 否 | 按员工筛选，最多 1000 人；不传 = 全部 |
| `customSortingRule` | object | 否 | `{"CreatedTime": 1}`，1 升序 2 降序 |
| `queryCursor` / `pageSize` | | 否 | |

响应 `data.swipingCardDetails[]`：`staffId`、`userEmail`、`cardNumber`、`punchCardDate`、`swipingCardDateTime`（日期 + 时间）、`punchCardTime`（`0001-01-01 16:09:00`，只有时间部分有意义）、
`dataSource`（来源编码）、`locationDetail`、`locationTitle`、`signinResult`、`facilityIdentify`、`wifiName`、`lat` 等。

## 6. 推送（异步）

### 接收打卡数据
**Endpoint**: `POST /AttendanceOpen/api/v1/SwipingCardData/PostAsync`
**用途**: 三方考勤机 / 门禁把打卡推给北森。限流 50/秒、1500/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `DataSourceType` | int | 是 | 「接口导入 = 14，不支持其他来源」 |
| `PrimaryKeyType` | int | 否 | `0` 考勤卡号、`1` 北森 UserId |
| `Items` | array | 是 | **单次 ≤1000 条** |
| `Items[].PrimaryKey` | string | schema 未标必填（⚠ 文档未说明） | 按 PrimaryKeyType 填卡号或 UserId；不传就无法对应到人，照示例传 |
| `Items[].CardDateTime` | datetime | schema 未标必填（⚠ 文档未说明） | `"2020-07-23 09:34:00"`；照示例传 |
| `Items[].PunchCardState` | string | 否 | 打卡状态枚举（选项表未抓取；FAQ 有「PunchCardState 数据格式错误」一条） |
| `Items[].LocationTitle` / `LocationDetail` / `TimeZone` / `Data` / `SigninResult` | string | 否 | 有自定义字段时地点详情放 `Properties` 的 `location_detail` |
| `Items[].Properties` | object | 否 | 自定义字段 |
| `ErrorEmail` | string | — | 「已废弃」 |

**字段名首字母大写**（`Items`、`PrimaryKey`），与其他接口的 camelCase 不同；大小写是否敏感 ⚠ 文档未说明，照文档写。

```python
r = client.s.post("https://openapi.italent.cn/AttendanceOpen/api/v1/SwipingCardData/PostAsync",
                  headers={"Authorization": f"Bearer {token}"}, timeout=30,
                  json={"DataSourceType": 14, "PrimaryKeyType": 1,
                        "Items": [{"PrimaryKey": "115000335", "CardDateTime": "2026-09-11 09:02:00",
                                   "LocationTitle": "北京办公室"}]})
body = r.json()                                  # {"Code": 200, "Message": null}
request_id = r.headers.get("X-PAAS-Request-ID")   # 查处理结果用，见 auth-and-conventions.md 第 7 节
```

提示原文（重要）：「异步执行，支持反复推送……（仅接收近一年内的数据）。数据未入库不会有提示 接口返回成功仅代表通过了接口必填信息、自定义字段校验等基础校验，
不代表数据可以进入系统，常见接口返回成功但数据未入库原因有：已存在相同相同分钟打卡、考勤卡号未维护或不同员工考勤卡号相同……」。
→ **返回 `Code: 200` 之后必须用 `X-PAAS-Request-ID` 查异步状态**；同一分钟的重复打卡会被丢弃；按卡号推送前确认卡号已维护且不重复。

响应 `Code`（文档）：「200 成功 206 部分成功 401 无权限 417 失败」；schema 却是字符串枚举 `None, Succeed, PartSucceed, NoPermission, Failed`（⚠ 文档自相矛盾），示例是数字 `200`。
判断时 `str(body.get("Code")) in ("200", "Succeed")`，206 / PartSucceed 按部分失败处理。

### 接收休假数据
**Endpoint**: `POST /AttendanceOpen/api/v1/Vacation`
**用途**: 把三方系统审批完的休假单推给北森。限流 50/秒、1500/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `VacationRecords` | array | 是 | ≤1000 条 |
| `VacationRecords[].StaffName` | string | 是 | 员工姓名 |
| `VacationRecords[].StaffEmail` | string | 是 | 员工邮箱（FAQ 条目：「员工姓名与邮箱不符」会报错） |
| `VacationRecords[].StaffId` | int | 否 | |
| `VacationRecords[].VacationType` | string | 是 | 休假类别**名称**，如 `"病假"`、`"事假"` |
| `VacationRecords[].StartDateTime` / `StopDateTime` | string | 是 | `"2020-11-11 11:10:20"` |
| `HalfDayStartOption` / `HalfDayStopOption` | int | 否 | 半天假时填 |
| `Reason`、`Attachment`（dfs 路径）、`HandoverPerson`… | | 否 | |

```json
{"VacationRecords": [{"StaffName": "张三", "StaffEmail": "zhangsan@example.com", "VacationType": "事假",
                      "StartDateTime": "2026-09-14 09:00:00", "StopDateTime": "2026-09-14 18:00:00"}]}
```

同样**异步**：「首先调用此假勤业务异步接口，拿到响应头中的X-PAAS-Request-ID……再调用平台【根据请求ID查询业务异步接口的任务处理状态】接口……即可获得错误数据」。
`Type` 字段「可忽略，填写后无实际作用，以员工考勤方案中休假项目的属性为准」。
带审批流的同步推送另有 `Vacation/SyncAddWithApproval`、撤销 `Vacation/SyncRevorkWithApproval`（拼写如此）、`Vacation/Revoke`。

## 7. 其他假勤接口（只列入口，本 skill 未整理字段）

| 领域 | 接口（`/AttendanceOpen/api/v1/…`） |
|---|---|
| 出差 | `Business`（接收）、`Business/SyncAddWithApproval`、`Business/SyncChangeBusinessWithApproval`、`Business/Remove`、`Business/GetApprovalCompletedBusinessListByDate`、`Business/GetBusinessRecords` |
| 公出 | `Outward/Add`、`Outward/GetApprovalCompletedOutwardList`、`Outward/GetOutwardListByDate` |
| 加班 | `AttendanceOvertime`（推送）、`AttendanceOvertime/PostAsync`、`AttendanceOvertime/GetApprovalCompletedOverTimeListByDateTime`、`AttendanceOvertime/GetOverTimeListByDate` |
| 排班 / 班次 | `WorkShiftRecord/GetWorkShiftRecordListByMoth`（拼写如此）、`WorkShiftRecord/GetWorkShiftRecordByStaffIds`、`WorkShift/GetWorkShiftInfo`、`WorkShift/BatchGetWorkShiftByStaffIdDate` |
| 日报 / 月报 | `DailyReport/GetDailyReportListByDay`、`DailyReport/GetDailyReportListByModifiedTime`、`Monthly/GetMonthlyListByMonth`、`Monthly/GetMonthlyDetailsByMonth` |
| 考勤档案 | `AttendanceRecord/GetAttendanceRecords`、`AttendanceRecord/GetAttendanceRecordsByUserIdsAndDateTime` |
| 补签 | `AttendanceStatistics/GetFillCheckListByDate`、`AttendanceStatistics/GetApprovalCompletedFillCheckList` |
| 调休假 / 育儿假 | `ExchangeLeave/*`、`ParentLeave/*` |
| 组织日历 | `WorkCalendar/GetWorkCalendars` |

标「（不推荐）」的旧接口（`Vacation/GetList`、`VacationRemain/GetList`、`Business/GetList` 等）不要新接。
社区「常见对接案例（假勤管理）」建议出差对接「先看此文档，先行确认业务实施方案再决策接口方案」（同步在途申请 / 同步申请结果 / 异步三种方案）。
