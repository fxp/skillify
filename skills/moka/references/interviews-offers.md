# 面试、Offer 与入职（ATS）

> 来源：ATS 文档「面试API」「Offer API」「入职API」「公共API」<https://www.mokahr.com/docs/api/>（抓取于 2026-09-11）。
> **文档版，未用真实凭证调用验证。** 报错 / 行为描述除标「无凭证探测（2026-09-11）」外均为「文档原文，未实测」。
> 鉴权见 `auth.md`；`ats_call()` 为 `auth.md` 第 8 节的最小客户端。

## 目录

1. [流程总览](#1-流程总览)
2. [创建面试](#2-创建面试)
3. [拉取面试列表（按日期）](#3-拉取面试列表按日期)
4. [按申请取面试（V3）](#4-按申请取面试v3)
5. [创建 Offer](#5-创建-offer)
6. [Offer 审批](#6-offer-审批)
7. [发送 Offer](#7-发送-offer)
8. [回写候选人接受 / 拒绝](#8-回写候选人接受--拒绝)
9. [读取 Offer 信息（V3）](#9-读取-offer-信息v3)
10. [标记入职 / 未入职 / 转正 / 离职](#10-标记入职--未入职--转正--离职)
11. [上传附件（给 Offer 用）](#11-上传附件给-offer-用)
12. [其他面试 / Offer 接口速查](#12-其他面试--offer-接口速查)
13. [⚠ 汇总](#13--汇总)

---

## 1. 流程总览

```
申请到面试型阶段(201) ─ 创建面试 ─ 面试反馈 ─ 移到 offer 型阶段(101)
   ─ 创建 Offer（需 CSM 开通）─ 审批 ─ 发送 Offer ─ 候选人接受/拒绝
   ─ 待入职(102) ─ 标记已入职 / 未入职 ─ 转正 / 离职
```

- 全程以 **`applicationId`** 为主键（见 `candidates.md` 第 1 节）。
- 面试、Offer 的**变化推送**用 ATS webhook（`createInterviewsInfo` 等、`pushCandidate`），见 `webhooks.md`。
- 这一组接口的响应格式五花八门：`{success, errorMessage}`、`{code:0, message}`、`{code:0, msg}`、`{code:0, codeType, data}`，逐个按下文判。

## 2. 创建面试

**Endpoint**: `POST https://api.mokahr.com/api-platform/v1/interview/create`

**关键参数（JSON body）**

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `stageId` | number | 是 | 面试所在阶段 ID（阶段信息列表接口获取） |
| `startTime` | string | 是 | **`yyyy-MM-dd HH:mm:ss`**（不是 ISO8601，⚠ 时区文档未说明） |
| `duration` | number | 是 | 分钟，**必须是 15 的倍数，且不超过 3 小时** |
| `typeCode` | number | 是 | `1` 现场面试、`2` 集体面试、`3` 电话面试 |
| `orgId` | string | 是 | 租户 orgId，"由客户负责人提供" |
| `interviewArrangerEmail` | string | 是 | 面试创建人 email |
| `locationId` | number | 是 | 面试地点 ID |
| `meetingRoomId` | number | 否 | 会议室 ID |
| `round` | number | 是 | 面试轮次。文档原文「需要提前给数据」，⚠ 取值来源未说明 |
| `signedInAt` | string | 是 | 候选人签到时间 `yyyy-MM-dd HH:mm:ss`。⚠ 创建时就必填签到时间，语义文档未解释 |
| `applicationIds` | array | 是 | 参与面试的申请 ID，1–200 个；**现场面试只能 1 个** |
| `interviewerEmails` | array | 是 | 面试官 email |

**示例请求**

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/v1/interview/create" -u "$MOKA_API_KEY:" \
  -H "Content-Type: application/json" \
  -d '{"stageId":1741,"startTime":"2026-09-15 14:00:00","duration":60,"typeCode":1,"orgId":"'"$MOKA_ORG_ID"'",
       "interviewArrangerEmail":"hr@example.com","locationId":1,"round":1,"signedInAt":"2026-09-15 13:50:00",
       "applicationIds":[425015406],"interviewerEmails":["interviewer@example.com"]}'
```

```python
payload = {
    "stageId": stage_id, "startTime": "2026-09-15 14:00:00", "duration": 60,   # 15 的倍数
    "typeCode": 1, "orgId": os.environ["MOKA_ORG_ID"], "interviewArrangerEmail": hr_email,
    "locationId": location_id, "round": 1, "signedInAt": "2026-09-15 13:50:00",
    "applicationIds": [app_id], "interviewerEmails": [interviewer_email],
}
res = ats_call("POST", "/v1/interview/create", json=payload)
if res.get("code") != 0:
    raise RuntimeError(f'{res.get("code")}: {res.get("message")}')   # 注意是 message 不是 msg
group_interview_id = res["data"]["groupInterviewId"]
```

**示例响应**（文档原文）：`{"code": 0, "message": "成功", "data": {"groupInterviewId": 1}}`

**本接口专属 code**（文档原文）

| code | 含义 |
| :--- | :--- |
| `-1` | 系统未知错误 |
| `100` | 负责人或者面试官 email 不准确 |
| `101` | 存在无权创建面试的职位 |
| `102` | 面试持续时长需要是 15 的倍数，且不能超过 3 小时 |
| `103` | 现场面试，仅支持一个候选人 |
| `104` | stageId 不合法 |
| `105` | applicationIds 不合法 |
| `106` | 未找到指定的面试，无法更新面试反馈 |
| `400` | 参数检查错误 |

**注意事项**

- ⚠ 文档自相矛盾：返回字段表把 `code` 描述成「面试id，md5字符串」、`message` 描述成「面试开始时间」、`data.groupInterviewId` 描述成「面试时长」——明显是从别的接口复制错了。以示例为准：`code` 数字、`message` 文本、`groupInterviewId` 为面试 ID。
- `typeCode` 只有 1–3；面试推送 / V3 查询里的 `interviewType` 有 1–5（多了 4 视频、5 叫号）。视频面试、叫号面试属于第三方服务商接入（`view/openPlatform.html`），本 skill 不覆盖。

## 3. 拉取面试列表（按日期）

**Endpoint**: `GET https://api.mokahr.com/api-platform/v1/interviews?startDate={startDate}&endDate={endDate}&hireMode={hireMode}`

| 参数 | 必填 | 说明 |
| :--- | :--- | :--- |
| `startDate` / `endDate` | 二选一对 | 面试日期，ISO8601 |
| `createStartDate` / `createEndDate` | 二选一对 | 面试创建日期，ISO8601 |
| `hireMode` | 否 | 1 社招 / 2 校招 |

文档原文：两对日期**必须有一对**；范围**不得超过 31 天**；「只能精确到天」（按年月日取值）；包含首尾两天。

```bash
curl -s "https://api.mokahr.com/api-platform/v1/interviews?startDate=2026-09-01T00:00:00.000Z&endDate=2026-09-30T00:00:00.000Z" -u "$MOKA_API_KEY:"
```

返回 `{"data": [...]}`，按开始时间升序；每项：`id`（md5 字符串）、`startTime`（ISO8601）、`type`（中文，如「现场面试」）、`duration`、`jobTitle`、`stageName`、`address`、`theme`、
`status`（中文：「未结束 / 已结束 / 已取消」）、`createdAt`、`hr{name,email,phone}`、`candidates[]{name,email,phone,status,jobTitle,applicationId,groupId}`、`interviewers[]`、`roomId`、`roomName`、`jobs[]{mjCode}`。

- **状态和类型是中文可读文本**，不是枚举——做判断时用第 4 节的 V3 接口（数字枚举）更稳。
- 空字段是空字符串 `""`（文档原文）。
- 拉一个月以上：按 ≤ 31 天切片。

## 4. 按申请取面试（V3）

**Endpoint**: `POST https://api.mokahr.com/api-platform/v3/getInterviewInfos`，body `{"applicationIds": [123456], "orgId": "…"}`（两者必填）

返回 `{"code":0,"codeType":0,"data":[…],"msg":…,"success":…}`，每项：

| 字段 | 说明 |
| :--- | :--- |
| `groupInterviewId` / `interviewId` / `groupId` | 面试 ID / 面试 ID / 面试组 ID |
| `status` | 1 未结束、2 已结束、3 已取消 |
| `candidateAttendStatus` | 1 未反馈、2 未到场、3 已拒绝、4 已接受、5 时间不合适 |
| `signInStatus` | 1 已签到、2 未签到 |
| `interviewType` | 1 现场、2 集体、3 电话、4 视频、5 叫号 |
| `startTime` / `createAt` | **毫秒时间戳** |
| `duration` / `roundId` / `roundName` / `stageId` / `locationId` / `meetingRoomId` / `applicationId` | — |

扩展信息（面试官、评价等）：`POST /api-platform/v3/getInterviewExtendInfos`（字段见文档）。

## 5. 创建 Offer

**Endpoint**: `POST https://api.mokahr.com/api-platform/v1/create-offer`
**前提**：文档原文「需要您的CSM开启该功能」；未开启时错误码表有 `300618 未开启外部系统创建Offer`。

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `applicationId` | integer | 是 | 申请 ID |
| `salaryNumber` | integer | 否 | 薪资数额 |
| `salaryType` | integer | 否 | `1` 时薪、`2` 日薪、`3` 月薪、`4` 年薪 |
| `checkinDate` | string | 否 | 入职时间（示例为 ISO8601 `2018-08-06T16:00:00.000Z`） |
| `locationId` | integer | 否 | 入职地点 |
| `contactUserName` / `contactPhone` / `contactEmail` | string | 否 | 联系人 |
| `customFields[]` | array | 否 | `{id 或 name, value}`（id 与 name 二选一） |
| `creatorEmail` / `creatorNumber` | string | 否 | 创建人邮箱 / 工号 |
| `toCandidateAttachment` / `toApproverAttachment` | array | 否 | 附件 key（第 11 节上传获得），各 ≤ 5 个 |
| `hcId` | integer | 否 | 关联招聘需求 |
| `jobRankId` / `departmentCode` | — | 否 | 职位级别 / 入职部门 |
| `isCreateOfferAttachment` / `templateId` | boolean / integer | 否 | 是否生成默认 offer 附件 / 附件模板 |

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/v1/create-offer" -u "$MOKA_API_KEY:" -H "Content-Type: application/json" \
  -d '{"applicationId":12,"salaryNumber":30000,"salaryType":3,"checkinDate":"2026-10-08T01:00:00.000Z","creatorEmail":"hr@example.com"}'
```

```python
res = ats_call("POST", "/v1/create-offer", json={"applicationId": app_id, "salaryNumber": 30000,
                                                 "salaryType": 3, "creatorEmail": hr_email})
if not res.get("success"):
    raise RuntimeError(res.get("errorMessage"))
```

- 响应 `{"success": true}` 或 `{"success": false, "errorMessage": "…"}`——**判 `success`，不是 `code`**。
- `salaryNumber` 的单位（元还是千元）：⚠ 文档未说明；在 V3 读取接口里它变成了**字符串**（示例 `"15"`）。写入前与用户确认口径。
- 无凭证探测（#B9）：路径存在（伪造 Key → HTTP 500 鉴权错误）。
- 修改 Offer 字段：`POST /api-platform/v1/offers/offerFields/update`（字段见文档）。

## 6. Offer 审批

### 获取某人的 Offer 审批列表
**Endpoint**: `GET https://api.mokahr.com/api-platform/v1/offerApprovals?email={email}&period={period}`

| 参数 | 必填 | 说明 |
| :--- | :--- | :--- |
| `email` | 是 | 审批人在 Moka 的 email |
| `period` | 是 | `pending` 待审批 / `past` 已审批 |

返回 `{"total": 1, "offerApprovals": [{"candidateName","jobTitle","departmentName","initiatedAt","url"}]}`——**列表里没有 applicationId 或 offerId**，只有审批 URL；适合做"待办提醒"，不适合做自动审批。

### 审批 Offer
**Endpoint**: `PUT https://api.mokahr.com/api-platform/v1/applications/offerApproval`（字段见文档「审批offer」）。

## 7. 发送 Offer

**Endpoint**: `POST https://api.mokahr.com/api-platform/v1/sendOffer`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `applicationId` | integer | 是 | — | 申请 ID |
| `hrEmail` | string | 是 | — | 操作 HR 邮箱 |
| `notifySms` | boolean | 否 | **否** | 是否短信通知候选人 |
| `notifyEmail` | boolean | 否 | **否** | 是否邮件通知候选人 |
| `notifyWechat` | boolean | 否 | **否** | 是否微信通知候选人 |
| `ccUserEmails` | array | 否 | — | 抄送人（受 `notifyEmail` 控制） |

```python
res = ats_call("POST", "/v1/sendOffer", json={"applicationId": app_id, "hrEmail": hr_email,
                                              "notifyEmail": True, "notifySms": True})
if not res.get("success"):
    raise RuntimeError(res.get("errorMessage"))
```

- **三个通知开关默认都是否**：只传 `applicationId` 的话，Offer 状态变成已发送，但候选人**收不到任何通知**。按用户意图显式打开。
- ⚠ 文档自相矛盾：参数表 `hrEmail` 必填，文档自己的示例请求里没有 `hrEmail`。按必填传。
- 审批未通过不能发（错误码 `300617 Offer审批未通过，不可发送`，文档原文）。

## 8. 回写候选人接受 / 拒绝

**Endpoint**: `PUT https://api.mokahr.com/api-platform/v1/offer/status?applicationId={applicationId}&accepted={accepted}&reasonId={reasonId}`
**用途**：候选人在你的系统里接受 / 拒绝了 Offer，把结果写回 Moka。

| 参数（**query**） | 必填 | 说明 |
| :--- | :--- | :--- |
| `applicationId` | 是 | 申请 ID |
| `accepted` | 是 | `1` 接受 / `0` 拒绝 |
| `reasonId` | 拒绝时必填 | 归档原因 ID（系统或自定义） |
| `talentPoolId` | 否 | 拒绝时放入的公开人才库，不填进公共人才库 |
| `fbTime` | 否 | 反馈时间（⚠ 格式文档未说明） |

```bash
curl -s -X PUT "https://api.mokahr.com/api-platform/v1/offer/status?applicationId=89&accepted=0&reasonId=1" -u "$MOKA_API_KEY:"
```

返回 `{"code": 0}` 为成功。参数全在 query、方法是 PUT；文档示例写 `http://`，请改 `https://`。

## 9. 读取 Offer 信息（V3）

**Endpoint**: `POST https://api.mokahr.com/api-platform/v3/getOfferInfos`，body `{"orgId": "…", "applicationIds": [111, 222]}`（两者必填）

返回 `{"code":0,"msg":"成功","success":true,"data":[…]}`，每项：`id`（offerId）、`salaryNumber`（**String**）、`salaryType`（1–4）、`checkinDate`（示例 `"2024-06-01"`）、
`sentAt` / `finishedAt` / `createdAt`（毫秒时间戳）、`status`（⚠ 取值文档未列全，示例 `pending`）、`applicationId`、`jobId`、`hcId`、`templateId`、`creatorId`、`contactName` 等。

扩展信息、导出（详情 + 发送记录 + 审批信息）：`POST /api-platform/v3/getOfferExtendInfos`、`POST /api-platform/v3/getOfferExportPdf`。

## 10. 标记入职 / 未入职 / 转正 / 离职

### 标记候选人已入职
**Endpoint**: `PUT https://api.mokahr.com/api-platform/v1/applications/{applicationId}/hired`

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `applicationId`（path） | integer | 是 | 申请 ID |
| `hiredAt` | string | 是 | 实际入职时间（示例 ISO8601） |
| `probation` | integer | 是 | 试用期月数 `0`–`6`，`0` = 无试用期 |
| `hcId` | integer | 否 | 招聘需求 ID。**不需要时整个字段别传**——文档原文「不允许传hcId=""或hcId=null」 |
| `isUseOfferHcid` | integer | 否 | 传 `1` 且不传 `hcId` 时，自动用该申请 Offer 关联的招聘需求 |
| `talentPoolIds` | array | 否 | 入职人才库；空则进"系统入职人才库" |

```python
body = {"hiredAt": "2026-10-08T01:00:00.000Z", "probation": 3, "isUseOfferHcid": 1}   # 不带 hcId 键
res = ats_call("PUT", f"/v1/applications/{app_id}/hired", json=body)
if not res.get("success"):
    raise RuntimeError(res.get("errorMessage"))    # 文档示例："hcId 参数错误"、"该申请已归档"
```

同组其他接口（均为 `PUT`，字段见文档「入职API」）：

| 用途 | Endpoint |
| :--- | :--- |
| 标记未入职 | `PUT /api-platform/v1/applications/{applicationId}/rejected` |
| 标记已入职转正 | `PUT /api-platform/v1/applications/{applicationId}/corrected` |
| 标记已离职 | `PUT /api-platform/v1/applications/{applicationId}/resign` |

入职成功后，该人进入人事系统的方式（People 的「批量添加待入职员工」或 People 自带的招聘集成）见 `people-hr.md`。

## 11. 上传附件（给 Offer 用）

**Endpoint**: `POST https://api.mokahr.com/api-platform/v1/file/upload`（`multipart/form-data`，字段 `upload_file`）

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/v1/file/upload" -u "$MOKA_API_KEY:" -F 'upload_file=@./offer.pdf'
```

返回 `{"data":{"key":"xxx"},"code":200,"msg":""}`——**成功码是 200**；把 `data.key` 放进创建 Offer 的 `toCandidateAttachment` / `toApproverAttachment`。
（文档示例命令漏了 `curl`，是笔误。）

## 12. 其他面试 / Offer 接口速查

| 用途 | Endpoint |
| :--- | :--- |
| 面试反馈数据 | `GET /api-platform/v1/data/interviewer_feedbacks` |
| 填写面试反馈 | `POST /api-platform/v1/interview/updateInterviewFeedback` |
| 单场面试信息 | `POST /api-platform/v1/interview/interview-information` |
| 面试官忙闲 | `POST /api-platform/v1/interview/busyTime` |
| 面试方案 | `POST /api-platform/v1/interview-plan/getInterviewPlanConfig` |
| Offer 附件模板 / 附件 | `POST /api-platform/v1/listOfferTemplateByOrgId` · `POST /api-platform/v1/offer/getOfferAttachment` |
| Offer 自定义字段 | `POST /api-platform/v2/offers/custom_fields` |
| 考试测评 / 背调信息 | `POST /api-platform/v3/getExamInfos` · `POST /api-platform/v3/getSurveyInfos` |

## 13. ⚠ 汇总

- ⚠ 文档自相矛盾：创建面试的返回字段描述张冠李戴；`sendOffer` 参数表 `hrEmail` 必填而示例没有。
- ⚠ 文档未说明：创建面试 `startTime` / `signedInAt` 的时区；`round` 取值来源；`signedInAt` 为何必填。
- ⚠ 文档未说明：Offer `salaryNumber` 单位；写入为 integer、读取为 String；`status` 取值全集；`fbTime` 格式。
