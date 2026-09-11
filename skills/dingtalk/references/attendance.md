# 考勤：打卡结果、打卡详情、考勤组、假期与报表

来源：open.dingtalk.com/document 下「获取打卡结果」「获取打卡详情」「获取用户考勤组」「查询请假状态」「获取考勤报表列定义 / 列值」
「获取报表假期数据」「查询成员排班信息」「上传打卡记录」「计算请假时长」「获取部门用户签到记录」（抓取于 2026-09-11）。
**全部为文档原文，未实测。** 考勤接口**全部是旧版** `https://oapi.dingtalk.com`，token 放 query（见 `auth.md`），
成功判定 `errcode == 0`。考勤类审批（请假、加班、补卡、外出）的状态变化通过审批事件拿，见 `events.md`。

## 目录

1. [选型：打卡结果 vs 打卡详情 vs 报表](#1-选型打卡结果-vs-打卡详情-vs-报表)
2. [获取打卡结果](#2-获取打卡结果)
3. [获取打卡详情](#3-获取打卡详情)
4. [考勤组与排班](#4-考勤组与排班)
5. [请假与假期](#5-请假与假期)
6. [考勤报表](#6-考勤报表)
7. [签到与上传打卡](#7-签到与上传打卡)
8. [⚠ 未说明 / 矛盾之处](#8--未说明--矛盾之处)

---

## 1. 选型：打卡结果 vs 打卡详情 vs 报表

| 我要 | 接口 | 关键差异 |
| --- | --- | --- |
| 每个排班卡点的最终结果（正常 / 迟到 / 早退 / 缺卡） | `POST /attendance/list` | 每个卡点一条；**有排班没打卡也会返回卡点**（timeResult=NotSigned） |
| 所有原始打卡明细（含位置、Wi-Fi、无效打卡） | `POST /attendance/listRecord` | 打几次返回几次；**有排班没打卡返回空** |
| 出勤天数、迟到次数等统计口径 | `getattcolumns` + `getcolumnval` | 智能考勤报表的列值，不支持离职人员 |
| 某人某天是否在请假 | `POST /topapi/attendance/getleavestatus` | 按天返回请假时长 |

两个打卡接口的**参数名不同**：`/attendance/list` 用 `workDateFrom` / `workDateTo` / `userIdList`，
`/attendance/listRecord` 用 `checkDateFrom` / `checkDateTo` / `userIds`。复制粘贴时最容易错。

---

## 2. 获取打卡结果

**Endpoint**: `POST https://oapi.dingtalk.com/attendance/list?access_token=...`
**权限**: `qyapi_attendance_isv_query_result` / `qyapi_get_attendance_data`。不支持查询半年以前的数据。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| workDateFrom | String | 是 | `yyyy-MM-dd HH:mm:ss`；按**整天**生效（传 10:00 也返回当天 0–24 点） |
| workDateTo | String | 是 | 同上；与 From **相隔最多 7 天（含）** |
| userIdList | String[] | 是 | userid 列表，最多 50；"务必确保userId参数的正确性，否则本接口获取信息为空" |
| offset | Number | 是 | 首次 0，之后 offset + limit |
| limit | Number | 是 | 最大 50 |
| isI18n | Boolean | 否 | 海外平台 true，默认 false |

```python
import requests
from datetime import date, timedelta

def punch_results(token: str, userids: list[str], day_from: date, day_to: date) -> list[dict]:
    """day_to - day_from ≤ 7 天；userids ≤ 50，超出请自行分批。"""
    out, offset = [], 0
    while True:
        r = requests.post("https://oapi.dingtalk.com/attendance/list", params={"access_token": token}, json={
            "workDateFrom": f"{day_from} 00:00:00", "workDateTo": f"{day_to} 00:00:00",
            "userIdList": userids[:50], "offset": offset, "limit": 50}, timeout=10)
        d = r.json()
        if d.get("errcode") != 0:
            raise RuntimeError(d)
        out.extend(d.get("recordresult", []))
        if not d.get("hasMore"):
            return out
        offset += 50

# 查一个月：按 7 天切片
def punch_results_range(token, userids, start: date, end: date):
    rows, cur = [], start
    while cur <= end:
        stop = min(cur + timedelta(days=6), end)
        rows += punch_results(token, userids, cur, stop)
        cur = stop + timedelta(days=1)
    return rows
```

**响应字段**（`recordresult[]`）

| 字段 | 说明 |
| --- | --- |
| userId / workDate（毫秒）/ checkType | `OnDuty` 上班 / `OffDuty` 下班 |
| timeResult | `Normal` / `Early` 早退 / `Late` 迟到 / `SeriousLate` / `Absenteeism` 旷工迟到 / `NotSigned` 未打卡 |
| locationResult | `Normal` 范围内 / `Outside` 范围外 / `NotSigned` |
| baseCheckTime / userCheckTime | 基准时间 / 实际打卡时间（毫秒） |
| sourceType | `ATM` / `BEACON` / `DING_ATM` / `USER` / `BOSS` 老板改签 / `APPROVE` 审批系统 / `SYSTEM` / `AUTO_CHECK` |
| procInstId / approveId | 非空表示该卡点与请假、加班等审批有关 |
| groupId / planId / recordId / id | 考勤组、排班、打卡记录 ID |

分页标志是顶层 `hasMore`（驼峰），不是 `has_more`。考勤数据"同步可能会出现延迟"。

---

## 3. 获取打卡详情

**Endpoint**: `POST https://oapi.dingtalk.com/attendance/listRecord?access_token=...`
**用途**: 取全部原始打卡明细（含作弊、需二次确认等无效打卡），不支持 180 天之前。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| userIds | List | 是 | 最多 50 |
| checkDateFrom | String | 是 | `yyyy-MM-dd hh:mm:ss`；**按时刻生效**（传 10:00:00 拿不到 09:00 的打卡） |
| checkDateTo | String | 是 | 同上；与 From 相隔最多 7 天（含） |
| isI18n | Boolean | 否 | |

注意和打卡结果接口的区别：这里的时间是**精确时刻**，结果接口是**整天**。

**需要过滤无效打卡**（文档原文要求关注三个字段）：
- `isLegal`：`Y` 合法（timeResult 与 locationResult 都为 Normal）/ `N`；
- `invalidRecordType`：`Security` 安全原因 / `Other`；
- `invalidRecordMsg`：如"需要二次确认"。

其他字段：`userCheckTime`、`userAddress`（考勤机打卡时是考勤机名称）、`userLatitude/userLongitude`（ATM / DING_ATM 来源不返回）、
`userSsid`、`userMacAddr`、`deviceId`、`outsideRemark`、`planCheckTime`、`classId`、`photoUrl`（**SDK 不返回，需 HTTP 调用**）。
字段表把 `errcode`、`userCheckTime` 等标为 String，示例里却是数字 ⚠，解析要兼容。

---

## 4. 考勤组与排班

### 获取用户考勤组

**Endpoint**: `POST https://oapi.dingtalk.com/topapi/attendance/getusergroup?access_token=...`，body `{"userid": "..."}`。
一个员工在一个企业中只能属于一个考勤组。

响应 `result`：`group_id`、`name`、`type`（`FIXED` 固定排班 / `TURN` 轮班 / `NONE` 无班次）、
`classes[]`（`class_id`、`name`、`sections[].times[]` 含 `check_time`、`check_type`、`across` 跨天、`begin_min`/`end_min` 允许提前 / 延后分钟）。
`check_time` 形如 `"1970-01-01 09:30:00"`，只有时分秒有意义。
旧的 `group_key` 需用「groupKey转换为groupId」接口转换（未转录）。

### 查询成员排班信息

**Endpoint**: `POST https://oapi.dingtalk.com/topapi/attendance/schedule/listbyday?access_token=...`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| op_user_id | String | 是 | 操作人 userid |
| user_id | String | 是 | 被查人员 userid |
| date_time | Number | 是 | 毫秒时间戳 |

响应结构本次未转录 ⚠。批量版 `POST /topapi/attendance/schedule/listbyusers`（未转录）。

---

## 5. 请假与假期

### 查询请假状态

**Endpoint**: `POST https://oapi.dingtalk.com/topapi/attendance/getleavestatus?access_token=...`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| userid_list | String | 是 | **逗号分隔字符串**，最多 100 个 |
| start_time | Number | 是 | 毫秒时间戳；最多查 180 天 |
| end_time | Number | 是 | 毫秒时间戳 |
| offset | Number | 是 | 从 0 开始 |
| size | Number | 是 | 最大 20 |

```python
def leave_status(token: str, userids: list[str], start_ms: int, end_ms: int) -> list[dict]:
    out, offset = [], 0
    while True:
        d = requests.post("https://oapi.dingtalk.com/topapi/attendance/getleavestatus",
                          params={"access_token": token},
                          json={"userid_list": ",".join(userids[:100]), "start_time": start_ms,
                                "end_time": end_ms, "offset": offset, "size": 20}, timeout=10).json()
        if d.get("errcode") != 0:
            raise RuntimeError(d)
        res = d["result"]
        out.extend(res.get("leave_status", []))
        if not res.get("has_more"):          # 这里是 snake_case 的 has_more
            return out
        offset += 20
```

`leave_status[]`：`userid`、`start_time`、`end_time`、`duration_unit`（`percent_day` 天 / `percent_hour` 小时）、
**`duration_percent` = 时长 × 100**（请假 1 天 → 100；示例 650 + percent_hour = 6.5 小时）。直接当天数 / 小时数用会放大 100 倍。

### 获取报表假期数据

**Endpoint**: `POST https://oapi.dingtalk.com/topapi/attendance/getleavetimebynames?access_token=...`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| userid | String | 是 | |
| leave_names | String | 是 | 假期名称，逗号分隔，最大长度 20（如 `年假`） |
| from_date | Date | 是 | `yyyy-MM-dd HH:mm:ss`；不支持 225 天之前 |
| to_date | Date | 是 | 与 from_date 相差 31 天以内 |

### 其他

- 计算请假时长：`POST /topapi/attendance/getleaveapproveduration`，`userid`、`from_date`、`to_date`（`yyyy-MM-dd HH:mm:ss`），响应未转录 ⚠。
- 假期规则列表：`POST /topapi/attendance/vacation/type/list`；假期余额变更记录：`POST /topapi/attendance/vacation/record/list`（均未转录）。

---

## 6. 考勤报表

两步：先取列定义拿列 ID，再取列值。

1. `POST https://oapi.dingtalk.com/topapi/attendance/getattcolumns?access_token=...`（参数与响应未转录 ⚠，响应中含列 `id`）。
2. `POST https://oapi.dingtalk.com/topapi/attendance/getcolumnval?access_token=...`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| userid | String | 是 | 一次一个人 |
| column_id_list | String | 是 | 列 ID，逗号分隔，最多 20 个 |
| from_date | Date | 是 | `yyyy-MM-dd HH:mm:ss` |
| to_date | Date | 是 | 与 from_date 相差 31 天以内 |

响应：`result.column_vals[]`，每项 `column_vo.id` + `column_vals[{date, value}]`；某些列是固定值，只在 `fixed_value` 返回。
限制（文档原文）：**不支持获取离职人员**的考勤数据；"应出勤天数"只支持距今 **15 天内**，超过 15 天值为 0（不报错）。

---

## 7. 签到与上传打卡

### 获取部门用户签到记录

**Endpoint**: `GET https://oapi.dingtalk.com/checkin/record?access_token=...&department_id=1&start_time=...&end_time=...`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| department_id | String | 是 | 1 为根部门 |
| start_time / end_time | Number | 是 | 毫秒；间隔不超过 45 天 |
| offset / size | Number | 否 | size 最大 100 |
| order | String | 否 | `asc` / `desc` |

"签到"（外勤签到）与"打卡"是两套数据，不要混。多人签到记录另有 `POST /topapi/checkin/record/get`（未转录）。

### 上传打卡记录

**Endpoint**: `POST https://oapi.dingtalk.com/topapi/attendance/record/upload?access_token=...`
（用于把第三方考勤机的打卡写入钉钉）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| userid | String | 是 | |
| device_name | String | 是 | 考勤机名称，自定义 |
| device_id | String | 是 | 考勤机 ID，自定义 |
| user_check_time | Number | 是 | **毫秒**；须在 180 天以内 |
| photo_url | String | 否 | 公网可访问的图片地址 |

---

## 8. ⚠ 未说明 / 矛盾之处

- `/attendance/list`：`limit` 最大 50，文档 curl 示例却传 `limit=100` ⚠ 文档自相矛盾。
- `/attendance/listRecord`：参数叫 `checkDateFrom/checkDateTo`，说明里却写"workDateFrom和workDateTo参数相隔最多7天"；
  格式要求 `yyyy-MM-dd hh:mm:ss`，curl 示例传 `2018-01-01` ⚠ 文档自相矛盾。
- 时间窗：打卡结果"不支持半年以前"，打卡详情"不支持 180 天之前"，上传打卡"180 天以内"，假期数据"225 天"——各不相同，按各接口写。
- `getleavestatus` 响应示例多出字段表没有的 `leave_code`，且缺 `errmsg` ⚠ 文档未说明。
- `getattcolumns`、`listbyday`、`getleaveapproveduration` 的响应结构本次未转录 ⚠。
- 旧版接口文档 curl 用表单提交，本文件示例用 JSON body，⚠ 未实测（见 `messaging.md` 第 7 节同一说明）。
