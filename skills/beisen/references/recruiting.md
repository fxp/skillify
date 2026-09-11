# 招聘：申请、应聘者、流程阶段、职位、入职管理

来源：open.italent.cn 文档中心 › 新版接口 v3.0 › 招聘管理系统（申请 / 应聘者 / 设置相关 / 职位 / 入职管理），
社区文档「常见对接案例（招聘管理系统）」（pageId 124029659；「常见对接问题」页 124029717 正文为空）。抓取于 2026-09-11。
**未用真实凭证验证**；报错与行为均为「文档原文，未实测」。鉴权见 `auth-and-conventions.md`。

路径前缀 `https://openapi.italent.cn/RecruitV6/api/v1/`。和组织员工不同：招聘有不少 **GET + query string** 接口（181 篇里 44 个 GET），
响应外壳 `{"data":…,"code":200,"message":"…"}` 里 **`code` 是整数**，参数错误是 `400`（不是 417）。

## 目录

1. 招聘的 ID 与对象关系
2. 增量拉申请：`Apply/GetApplyListByModifiedTime`
3. 按申请 ID 取阶段状态：`Apply/GetApplyListByApplyId`
4. 应聘者信息与简历：`Applicant/GetPersonProfileList`、`Applicant/GetResumeByApplyId`
5. 流程与阶段：`Setting/GetProcessConfigById` → `Apply/TransferPhase`
6. 职位：`Job/GetJobList`
7. 入职管理（单招聘）：`RecruitOnBoarding/GetStaffInfos`、`RecruitOnBoarding/Entry`
8. 其他招聘接口（只列入口）

---

## 1. ID 与对象

- **应聘者** Applicant：`applicantId`（GUID），另有 `candidateId`（`C` + 数字，如 `C00206396`）。
- **申请** Apply：一个应聘者投一个职位 = 一条申请，`applyId`（GUID）。流程阶段状态挂在申请上：`processId` / `processPhaseId` / `processStatusId`。
- **职位** Job：`jobId`（GUID），另有 int 型 `jobIntId`（文档：「推荐使用jobId作为标识字段」）和 `jobCode`。
- **入职管理**（单招聘租户，未开通组织员工时）：Offer `offerId`、待入职员工 `staffId`（GUID）。
- 老招聘迁移到新招聘的租户：`POST /RecruitV6Adapter/api/applicanthttp/getintids`（GUID → 旧 int ID）、`…/getguids`（反向），
  「迁移时勾选了“兼容使用老版OpenAPI”」才适用。
- 部门：招聘里的 `orgId` 是**北森部门 Id**（int，即组织单元 OId，见 `organization-and-positions.md`）。

## 2. 增量拉申请

### 根据申请更新时间获取申请信息
**Endpoint**: `POST /RecruitV6/api/v1/Apply/GetApplyListByModifiedTime`
**用途**: 「增量获取变化的申请，结合应聘者接口，将变化的信息存储在本地」。限流 20/秒、1000/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `startTime` | date-time | 是 | `"2021-08-31T21:00:00"` |
| `endTime` | date-time | 是 | **注意叫 `endTime`**（组织员工叫 `stopTime`） |
| `batchId` | string | 否 | 首次传空，之后传上次返回的 `nextBatchId` |

「每批次返回1000条数据；根据申请上的修改时间字段增量查询」。时间范围上限 ⚠ 文档未说明。

```python
def applies_changed(client, start, end):
    out, batch = [], ""
    while True:
        body = client.post("/RecruitV6/api/v1/Apply/GetApplyListByModifiedTime",
                           {"startTime": start, "endTime": end, "batchId": batch})
        data = body.get("data") or {}
        out.extend(data.get("items") or [])
        if data.get("isLastBatch") or not data.get("nextBatchId"):
            return out                      # items: [{applyId, applicantId, jobId}]
        batch = data["nextBatchId"]
```

响应（文档原文，节选）：`{"data":{"total":7,"nextBatchId":"DXF1ZXJ5…","isLastBatch":true,"items":[{"applyId":"e6af76f9-…","applicantId":"dcb9a1d7-…","jobId":"327663d2-…"}]},…}`。
**只返回三个 ID**，详情要再调第 3、4 节接口。异常原文：`{"data":null,"code":400,"message":"开始时间不能大于等于结束时间"}`。
batchId 的过期时间 ⚠ 文档未说明（组织员工 scrollId 是 10 秒，这里没写）。

## 3. 按申请 ID 取阶段状态

### 根据申请ID获取申请信息
**Endpoint**: `POST /RecruitV6/api/v1/Apply/GetApplyListByApplyId`
限流 20/秒、1000/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `applyIds` | GUID[] | 是 | 「最多允许查100个」 |
| `fieldNames` | string[] | 否 | 额外返回的申请字段，如 `["ProcessPhaseChangeDate","ProcessStatusChangeDate"]`；「不传则返回值FieldValues为空」 |

⚠ 文档自相矛盾：响应字段表是嵌套结构（`data[].applicantLite{applicantId,name,email,mobile,…}`、`jobLite{jobGuid,jobTitle,…}`、`processLite{id,code,…}`），
响应示例却是扁平的 `{"applyId","applicantId","jobId","processId","processPhaseId","processStatusId","fieldValues":{…}}`。
**解析时两种都兼容**（先取扁平字段，取不到再看 `*Lite`）。异常：`{"data":null,"code":400,"message":"一次最多允许查100个"}`。

## 4. 应聘者信息与简历

### 批量获取应聘者个人信息
**Endpoint**: `POST /RecruitV6/api/v1/Applicant/GetPersonProfileList`
限流 20/秒、1000/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `applicantIds` | GUID[] | 是 | 最多 100 个 |
| `fieldNames` | string[] | 否 | 「如果不传，则返回应聘者全部有值字段」 |

响应不是对象字段，而是**键值列表**：`data[] = {applicantId, fieldValues: [{name, value, text, downloadUrl}]}`。
`value` 是原始值（如 `"1"`），`text` 是翻译后文本（如 `"本科"`）；附件字段的 `downloadUrl`「有效期30天」，多文件用英文逗号分隔。

```python
def profile_dict(item):
    return {f["name"]: (f.get("text") or f.get("value")) for f in item.get("fieldValues") or []}
```

### 根据申请Id获取标准简历
**Endpoint**: `GET /RecruitV6/api/v1/Applicant/GetResumeByApplyId?applyId=…&tabs=…&isShortUrl=…`
**用途**: 「预入职或已入职应聘者，OA系统定时获取应聘者简历信息」。限流 50/秒、1500/分钟。

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `applyId` | query | 是 | 申请 Id |
| `tabs` | query | 否 | 申请详情页签 Id，逗号分隔，「不传默认为 1,2,3,4,5,7」 |
| `isShortUrl` | query | 否 | 免登录链接是否短链 |

响应 `data`：`applicantId`、`candidateId`、`elinkUrl`（免登录链接，「有效期为100天」）、`personProfile[]`、`additionalInfo[][]`（二维）……同样是 `{name,value,text,downloadUrl}` 列表。
警告原文：「对于integer类型的可枚举字段，value可能会返回-32767，表示系统在解析简历时无法识别出标准简历字段，此时会将简历原始值写入到Og开头的字段中」——
遇到 `-32767` 去读 `Og*` 字段，别当成真实枚举值。「依据申请职位所属流程的标准简历设置的字段进行返回，未配置的字段不返回」。

## 5. 流程与阶段转移

### 根据流程id获取流程及其包含阶段状态内容
**Endpoint**: `GET /RecruitV6/api/v1/Setting/GetProcessConfigById?processId=…`
返回 `data.processId`、`processCode`（如 `F001`）、`processName`、`scence`（社会招聘 / 校园招聘）、`phaseList[] = {phaseId, phaseCode, …, 状态列表}`。
阶段下状态列表的字段名 ⚠ 本 skill 未逐字段整理（见文档）。按编码取：`Setting/GetProcessConfigByCode`；列表：`Setting/GetProcessList`。
异常示例是 `{"data":null,"code":404,"message":"根据ID未查询到流程"}`——`404` 不在该接口的错误码栏（400/417/500）里（⚠ 文档自相矛盾）。

### 转移阶段状态
**Endpoint**: `POST /RecruitV6/api/v1/Apply/TransferPhase`
**用途**: 把一批申请推进到某流程阶段 / 状态（如三方系统完成面试后回写北森）。限流 50/秒、1500/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `applyIds` | GUID[] | 是 | 「一次最多允许转移100个」 |
| `phaseId` | GUID | 是 | 目标阶段（「可通过GetProcessConfigById接口获取到」） |
| `statusId` | GUID | 是 | 目标状态 |
| `processId` | GUID | 否 | 流程 Id |
| `reasonId` / `reasonIds` | GUID / GUID[] | 否 | 原因（单选 / 多选） |
| `isSkipApplyLock` | bool | 否 | true 不校验职位锁定，默认 false |
| `isSkipApplicantLock` | bool | 否 | true 不校验用户锁定，默认 false |

规则（文档原文）：「申请列表的当前流程和阶段必须一致」「要转移的流程和当前流程必须相同，不允许跨流程转移」「转移到淘汰状态，不会检查申请锁，其他情况会检查」。

**部分失败**：`code` 200 时也要看 `data`：`totalCount`、`transferCount`、`noTransferCount`，以及按原因分组的失败 applyId 列表
`applyDeleteApplyIds`、`applicantDeleteApplyIds`、`applicantBlackApplyIds`、`applicantLockedApplyIds`、`applyStatusChangedApplyIds`、
`applyOtherReasonRejectedApplyIds`、`applyByHunterOrRPOUnAcceptedIds`、`applyTransferRuleFailedApplyIds`。
文档成功示例只有 `{"code":200,"message":"转移状态成功"}`（没有 data），与字段表不一致（⚠ 文档自相矛盾），`data` 缺失时按全部成功处理前先确认。
异常原文：`{"code":400,"message":"要转移的流程和当前流程不一致，不允许转移"}`。
（该接口「场景」一栏写的是「客户自己搭建的内推或者内招平台，推荐成功后在招聘系统生成应聘者」，与接口功能不符，疑为文档笔误。）

## 6. 职位

### 根据条件获取职位列表
**Endpoint**: `POST /RecruitV6/api/v1/Job/GetJobList`
**用途**: 「批量获取一段时间内更新的职位信息」。限流 20/秒、1000/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `startTime` / `endTime` | date-time | 是 | 职位更新时间，「精度到秒级」 |
| `batchId` | string | 否 | 同第 2 节 |
| `status` / `kind` / `category` | int | 否 | 职位状态 / 工作性质 / 招聘类别（选项表未抓取） |
| `orgId` | int | 否 | 需求部门 Id |

每批 1000 条。`data.items[]`：`jobId`、`jobIntId`、`jobCode`、`jobTitle`、`headCount`（0 = 若干）、`orgId`、`isDeleted`（0 未删除、1 删除——**会返回已删除职位**）、
`modifiedDate`、`createDate`、`jobType`（职位类别 Id 数组）、`kind`、`category`、`locId`、`salaryType`、`minSalary` / `maxSalary`、`duty`、`require`。

## 7. 入职管理（单招聘租户）

招聘「常见对接案例」原文：单招聘（未开通北森组织员工）的客户，「应聘者在北森到达一定的招聘流程，三方系统拉取北森应聘者信息到三方系统完成入职，
后回写北森系统更新应聘信息（转移阶段状态/同步入职管理入职等）」。开通了组织员工的「招 Core 一体」租户，入职走 `employee-lifecycle.md`。

### 查询待入职人员信息
**Endpoint**: `POST /RecruitV6/api/v1/RecruitOnBoarding/GetStaffInfos`
**请求体是裸 JSON 数组**，不是对象：

```json
["00884bc4-31f2-4d42-9b35-287e69867fa2", "00fdaf38-0102-4c45-9fa3-09b448ad4e03"]
```

「员工Id集合最大数量不能超过100」；「只会查找待入职的人员数据」。响应 `data[].staffInfos` 含 `id`、`name`、`email`、`infoCollectionStatus` 及大量证件 / 学历附件的
`*Path`（dfs 路径）和 `*DownLoadUrl`（「有效期30天」），另有家庭成员、教育、工作经历等子项（字段表 425 行）。
⚠ 文档自相矛盾：提示写「根据北森用户Id批量查询」，参数示例却是 GUID（入职管理的 staffId），异常原文 `"北森用户Id不能空"`。按示例传 staffId（GUID）。

### 入职
**Endpoint**: `POST /RecruitV6/api/v1/RecruitOnBoarding/Entry?offerId=…` 或 `?staffId=…`
**用途**: 「通过openapi入职人员，返回入职员工北森 userId」。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `offerId` / `staffId` | **query** | string | 至少一个 | |
| `originalId` | body | **int** | 是 | **「录用部门，必填。北森部门id」**——名字叫 originalId，含义是部门 OId，和组织员工里「外部ID」的 originalId 完全不是一回事 |
| `entryDate` | body | date | 否 | 「不填会取当前机器时间」 |
| `status` | body | int | 否 | 0 试用（默认）、1 正式 |
| `jobNumber`、`post`（岗位 GUID）、`probationDate`（月）、`pOIdEmpAdmin`、`pOIdEmpReserve`、`mobilePhone`、`mobileType`、`idNumber` | body | | 否 | |

响应 `{"data": 1001543834, "code": 200, "message": "…"}`，`data` 是新员工 UserID。成功时 `message` 可能带招聘需求人数管控提示（文档示例二），不要当错误。

## 8. 其他招聘接口（只列入口，本 skill 未整理字段）

| 领域 | 接口（`/RecruitV6/api/v1/…`） |
|---|---|
| 应聘者 | `Applicant/CreateOrUpdateApplicant`、`Applicant/GetApplicantIds`、`Applicant/GetApplicantIdsByDate`、`Applicant/GetResume`、`Applicant/GetOriginResumeFileUrl`、`Applicant/GetStandardResumeFileUrlByApplyId` |
| 申请 | `Apply/CreateApply`（投递）、`Apply/GetApplyListByDateAndStatus`、`Apply/GetApplysByPhaseStatusCode`、`Apply/UpdateApplyList`、`Apply/GetApplyElink` |
| 面试 | `Interview/ArrangeSingleInterview`、`Interview/GetInterviewsByDate`、`Interview/GetInterviewsByApplyId`、`Interview/GetEvaluationsByInterviewId`、`Interview/CancelInterview` |
| Offer / 入职管理 | `RecruitOnBoarding/GetOfferInfos`、`CreateOfferInfo`、`SendOffer`、`GetStaffIds`、`CancelEntry`、`SetDismission`、`CreatePost` / `GetPostDetails` |
| 招聘需求 | `Requirement/CreateRequirement`、`Requirement/GetRequirementWithCondition`、`Requirement/EntryHandle` |
| 职位广告 / 渠道 | `JobAd/*`、`Channel/GetChannelList` |
| 内推 / 人才库 / 黑名单 | `Recommend/*`、`TalentPool/*`、`RecruitmentBlackList/*` |
| 设置 | `Setting/GetProcessList`、`Setting/GetMsgTemplateList`、`Setting/GetDataSource`、`Setting/GetInterviewTypeList` |

字段表在 open.italent.cn 文档中心；本地渲染副本 `beisen-workspace/pages/open/招聘管理系统/`。
