# 候选人、申请与简历（ATS）

> 来源：ATS 文档「候选人API」「招聘官网API」「人才库API」<https://www.mokahr.com/docs/api/>（抓取于 2026-09-11）。
> **文档版，未用真实凭证调用验证。** 报错 / 行为描述除标「无凭证探测（2026-09-11）」外均为「文档原文，未实测」。
> 鉴权见 `auth.md`：`Authorization: Basic base64("<API_KEY>:")`。下文 `ats_call()` 即 `auth.md` 第 8 节的最小客户端。

## 目录

1. [先搞清 ID：候选人 vs 申请](#1-先搞清-id候选人-vs-申请)
2. [增量同步申请（最常用）](#2-增量同步申请最常用)
3. [按申请 ID 批量取详情](#3-按申请-id-批量取详情)
4. [按条件分页查申请](#4-按条件分页查申请)
5. [按邮箱 / 手机 / 证件号查申请](#5-按邮箱--手机--证件号查申请)
6. [把候选人放进 Moka：官网申请 vs 上传简历](#6-把候选人放进-moka官网申请-vs-上传简历)
7. [移动阶段](#7-移动阶段)
8. [归档（淘汰）到人才库](#8-归档淘汰到人才库)
9. [附件与简历文件](#9-附件与简历文件)
10. [其他候选人接口速查](#10-其他候选人接口速查)
11. [⚠ 汇总](#11--汇总)

---

## 1. 先搞清 ID：候选人 vs 申请

- **候选人（candidateId）**是人；**申请（applicationId）**是"这个人投了这个职位"。同一候选人可有多份申请。
- 移动阶段、面试、Offer、入职、附件、归档**全部按 `applicationId`** 操作；只有标签、推荐职位等少数接口按 `candidateId`。
- 申请所在位置 = **招聘流程（pipelineId）+ 阶段（stageId）**。阶段类型 `stageType`（文档原文）：
  `100` 初筛型、`101` offer 型、`102` 待入职、`200` 筛选型、`201` 面试型、`202` 测试型、`205` 无类型、`206` 试工类型。
- 归档类型 `archiveReasons.type`：`1` 被候选人拒绝、`2` 被我们拒绝、`3` 录用、`4` 系统原因、`5` 离职；
  `archiveReasonType` 为 `REJECTED_BY_CANDIDATES` / `REJECTED_BY_US` / `HIRED` / `SYSTEM` / `CHECKOUT`。
- 招聘模式 `hireMode`：`1` 社招、`2` 校招。

## 2. 增量同步申请（最常用）

### 获取候选人申请列表（游标拉取）
**Endpoint**: `GET https://api.mokahr.com/api-platform/v1/data/applications`
**用途**：按"更新时间"增量拉申请的**精简列表**（只有 ID、渠道、阶段名等），详情再用第 3 节批量取。

**关键参数（query）**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `fromTime` | string | 否 | — | 数据开始时间。**只在第一次请求时带** |
| `next` | string | 否 | — | 上一页响应里的 `next`。与 `fromTime` **二选一**；响应里没有 `next` 表示拉完了 |
| `limit` | string | 否 | 100 | 每页条数 |

**示例请求**

```bash
curl -s "https://api.mokahr.com/api-platform/v1/data/applications?fromTime=2026-09-01&limit=100" -u "$MOKA_API_KEY:"
```

```python
def iter_applications(from_time: str, limit: int = 100):
    params = {"fromTime": from_time, "limit": limit}
    while True:
        body = ats_call("GET", "/v1/data/applications", params=params)
        yield from body.get("data", [])
        nxt = body.get("next")
        if not nxt:                       # 没有 next 字段 = 没有更多数据
            return
        params = {"next": nxt, "limit": limit}   # 之后只带 next，不再带 fromTime
```

**示例响应**（文档原文）

```json
{"data": [{"id": 1, "sourceName": "拉勾", "headhunterCompany": "好猎头", "stageName": "沟通Offer", "jobId": "123", "updatedAt": "2017-01-01 10:00:00"}],
 "next": "8465195468"}
```

**注意事项**

- 响应**没有 `code` / `success` 字段**，成功判定就是 HTTP 200 + 有 `data`。
- `fromTime` 的格式：⚠ 文档未说明（招聘需求同类接口示例写 `fromTime=2018-1-1`）。先用 `yyyy-MM-dd`。
- `next` 能否跨进程持久化、隔天继续用：⚠ 文档未说明。稳妥做法是每次跑完记下本批最大 `updatedAt`，下次作为 `fromTime`，并按 `id` 去重。
- 无凭证探测（2026-09-11，#A11）：伪造 Key 调本接口 → HTTP 500 `{"code":-1,"success":false,"msg":"无法识别的认证信息"}`（路径存在）。

## 3. 按申请 ID 批量取详情

### 根据申请 Id 批量获取候选人信息
**Endpoint**: `POST https://api.mokahr.com/api-platform/v3/data/getApplictaions`
**用途**：拿第 2 节的 ID 换完整信息：候选人基础信息、联系方式、证件、教育 / 工作经历、职位、流程与阶段、归档原因、渠道、锁定、入职信息。

<!-- 路径拼写：Applictaions（不是 Applications）是文档原样，也是真实路径，见下方探测 -->

**关键参数（JSON body）**

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `applicationIds` | array[integer] | 是 | **最多 20 个** |

**示例请求**

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/v3/data/getApplictaions" \
  -u "$MOKA_API_KEY:" -H "Content-Type: application/json" -d '{"applicationIds":[411348665]}'
```

```python
def get_applications(ids: list[int]) -> list[dict]:
    out = []
    for i in range(0, len(ids), 20):                       # 每批 ≤ 20
        body = ats_call("POST", "/v3/data/getApplictaions", json={"applicationIds": ids[i:i + 20]})
        if body.get("code") != 200:
            raise RuntimeError(body)
        out += body["data"]["applicationList"]
    return out
```

**示例响应（精简）**

```json
{"code": 200, "msg": "success",
 "data": {"applicationList": [{"applicationId": 411348665, "appliedAt": 1744702215000,
   "candidateBaseInfo": {"candidateId": 1, "name": "…", "gender": 1, "contactInfo": {"email": "…", "phone": "…"}},
   "job": {"jobId": "…", "jobTitle": "…"}, "pipeline": {"pipelineId": 1, "name": "…"},
   "stage": {"stageId": 1, "name": "…", "stageType": 201}, "archived": false,
   "sourceInfo": {"sourceId": 1, "sourceName": "…", "sourceType": 2}, "checkinInfo": {"probation": 3, "headcountId": 5}}]}}
```

**注意事项**

- **路径拼写是 `getApplictaions`**（字母顺序 `…ict-a-ions`），不要"修正"成 `getApplications`。
  无凭证探测（2026-09-11，#B1 / #B2，各两次）：伪造 Key 调 `…/v3/data/getApplictaions` → HTTP 500 `系统中不存在该apiKey`（路由存在）；
  调拼写正确的 `…/v3/data/getApplications` → **HTTP 404** `{"message":"您访问的页面不存在"}`。
- 成功码是 `code == 200`（不是 0）。时间字段都是**毫秒时间戳**（`appliedAt`、`updatedAt`…）。
- 枚举全是数字：`gender` 1 男 2 女；`academicDegree` 1 其他 … 6 本科、7 硕士、8 MBA、9 博士；`certificateType` 1 身份证 … 5 护照；`sourceInfo.sourceType` 1 主动搜索 / 2 主动投递 / 3 内部推荐 / 4 猎头推荐。
- `candidateInfo.portraitUrl` 有过期时间（文档原文「默认一天」）。

## 4. 按条件分页查申请

### 根据条件查询申请信息（分页）
**Endpoint**: `POST https://api.mokahr.com/api-platform/v3/applications/list_by_condition`
**用途**：按职位 / 流程 / 阶段 / 归档状态 / 时间窗筛申请，返回结构同第 3 节（字段略少）。

**关键参数（JSON body）**

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `applicationIds` / `candidateIds` | array[integer] | 否 | 各最多 20 |
| `jobId` | string | 否 | 职位 ID |
| `pipelineIds` / `stageIds` | array[integer] | 否 | 流程 / 阶段 |
| `hireMode` | integer | 否 | 1 社招 / 2 校招，其他值视为没传 |
| `archived` | boolean | 否 | 是否已归档 |
| `updateAtStartTime` / `updateAtEndTime` | long | 否 | 更新时间窗（毫秒），**最大 3 个月** |
| `applicationCreateStartTime` / `…EndTime` | long | 否 | 申请首次入库时间窗，最大 3 个月 |
| `applicationAppliedAtStartTime` / `…EndTime` | long | 否 | 系统展示的申请日期窗，最大 3 个月 |
| `headhunterId` / `headhunterContractId` / `sourceId` | long | 否 | 传任一个即**取消 3 个月窗口限制**，只返回该猎头 / 合同 / 来源下的申请 |
| `limit` | integer | 否 | 默认 20，**最大 20** |
| `next` | string | 否 | 翻页时**只传这一个**（文档原文「分页参数, 只传这一个就可以」） |

**示例请求**

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/v3/applications/list_by_condition" \
  -u "$MOKA_API_KEY:" -H "Content-Type: application/json" \
  -d '{"pipelineIds":[17,87],"applicationCreateStartTime":1722233308000,"applicationCreateEndTime":1724911708000}'
```

```python
def list_by_condition(cond: dict):
    body = ats_call("POST", "/v3/applications/list_by_condition", json=cond)
    while True:
        if body.get("code") != 200:
            raise RuntimeError(body)
        yield from body["data"].get("applicationList", [])
        nxt = body["data"].get("next")
        if not nxt:
            return
        body = ats_call("POST", "/v3/applications/list_by_condition", json={"next": nxt})
```

**注意事项**

- 时间窗超过 3 个月的处理方式（报错还是截断）：⚠ 文档未说明。拉历史数据时按 ≤ 3 个月切片。
- 无凭证探测（#B5）：路径存在（伪造 Key → HTTP 500 `系统中不存在该apiKey`）。

## 5. 按邮箱 / 手机 / 证件号查申请

**Endpoint**: `POST https://api.mokahr.com/api-platform/v3/applications/list_by_contact_or_id`
**用途**：查重 / 回溯："这个人以前投过吗"。**最多返回 100 条**。

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `emailList` | array[string] | 否 | 最多 20 |
| `phoneList` | array[string] | 否 | 最多 20 |
| `citizenIdList` | array[string] | 否 | 最多 20 |

三者不能全空。响应结构同第 4 节，成功码 `code == 200`。

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/v3/applications/list_by_contact_or_id" \
  -u "$MOKA_API_KEY:" -H "Content-Type: application/json" -d '{"phoneList":["13800000000"]}'
```

## 6. 把候选人放进 Moka：官网申请 vs 上传简历

| 场景 | 用哪个 | 要点 |
| :--- | :--- | :--- |
| 自研招聘官网 / 小程序，候选人自己填表投递某职位 | `POST /v1/jobs/{orgId}/{jobId}/apply` | 结构化字段 + 可选简历文件；必填项取决于系统里的申请表设置 |
| 内部系统 / 渠道拿到一份简历文件，让 Moka 解析入库，可不指定职位 | `POST /v3/candidate/uploadResume` | multipart；`operateEmail`（HR 及以上）、`resume`、`sourceId` 必填 |
| 零代码嵌入官网申请页 | iframe `https://app.mokahr.com/apply/{orgId}/{siteId}#/job/{jobId}/apply?pure=1` | 见 `jobs.md` 第 6 节 |

### 6.1 申请一个职位
**Endpoint**: `POST https://api.mokahr.com/api-platform/v1/jobs/{orgId}/{jobId}/apply`
**用途**：代候选人投递到指定职位。支持 `application/json` 和 `multipart/form-data`；**要传简历或附件文件就必须用 multipart**，multipart 上传的简历会经过简历解析。

**关键参数**

| 位置 | 参数 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| path | `orgId` | 是 | 租户 ID |
| path | `jobId` | 是 | 职位 ID |
| query | `isRecommendation` | 否 | `1` = 内推申请（此时 `recommendCode` 与 body `recommender` 二选一，都填优先 `recommender`） |
| query | `isCheckProtect` | 否 | `1` 且内推时校验保护期 |
| query | `siteId` / `websiteSourceId` | 否 | 指定官网渠道 / 来源效果 |
| query | `acquisitionMode` | 否 | `0` 未知 / `2` 后台导入 / `5` 人才推荐 / `8` 主动推荐 / `9` 主动申请 |
| query | `ownerEmail` | 否 | 候选人所有者邮箱 |
| body | `basicInfo` | 是 | `{name, age, gender(男/女), email, phone, lastCompany, lastSpeciality, academicDegree, political}`，至少一个属性 |
| body | `educationInfo[]` / `experienceInfo[]` / `projectInfo[]` / `practiceInfo[]` / `languageInfo[]` | 否 | 日期如 `2014-01` |
| body | `jobIntention` | 否 | `{aimSalary, forwardLocation}`，`aimSalary` 单位千（K） |
| body | `customFields[]` | 否 | `{id, value, index}`；模块是数组时 `index` 必填且与下标一致 |
| body | `recommender` | 否 | `{name, email, phone, employeeId}` |
| multipart | 以上各块 | — | **每块是 JSON 字符串**；另有 `resume`（文件）、`attachments`（文件，最多 10 个） |

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/v1/jobs/$MOKA_ORG_ID/$JOB_ID/apply" \
  -u "$MOKA_API_KEY:" \
  -F 'basicInfo={"name":"张三","phone":"13800000000","email":"zhangsan@example.com"}' \
  -F 'resume=@./zhangsan.pdf'
```

```python
import json
files = {"resume": ("zhangsan.pdf", open("zhangsan.pdf", "rb"), "application/pdf")}
data = {"basicInfo": json.dumps({"name": "张三", "phone": "13800000000"}, ensure_ascii=False)}
r = ats.post(f"{ATS}/v1/jobs/{org_id}/{job_id}/apply", data=data, files=files, timeout=60)
app = r.json()        # 文档：返回新申请信息，含 id（申请 id）、candidateId、stageId
```

- 响应直接是申请对象（`id`、`candidateId`、`stageId`…），**没有 `code` 包装**；失败时的格式：⚠ 文档未说明。
- 文档原文：「该模块字段是否必填取决于系统内字段属性设置」——同一请求在不同租户可能因必填项不同而失败。

### 6.2 上传简历（支持无职位上传）
**Endpoint**: `POST https://api.mokahr.com/api-platform/v3/candidate/uploadResume`（`multipart/form-data`）

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `operateEmail` | string | 是 | 操作人邮箱，角色须为 HR 及以上 |
| `resume` | file | 是 | 简历附件 |
| `sourceId` | Long | 是 | 渠道 ID |
| `jobId` | string | 否 | 不传即"无职位上传" |
| `websiteSourceName` | Long | 否 | 门户名称（社招 / 校招门户才填）。⚠ 类型写 Long、名称是"门户名称"，文档自相矛盾 |
| `internalReferralEmail` | string | 否 | `sourceId` 为内推门户时必填 |
| `ambassadorEmail` | string | 否 | `sourceId` 为校园大使时必填 |
| `isBreakJobPermission` | Boolean | 否 | `true` = 不校验操作人对该职位的权限 |

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/v3/candidate/uploadResume" -u "$MOKA_API_KEY:" \
  -F 'resume=@./resume.pdf' -F "operateEmail=$HR_EMAIL" -F 'sourceId=1' -F "jobId=$JOB_ID"
```

响应（文档原文）：`{"code":0,"msg":"success","success":true,"data":{"application":{"candidateId":2,"id":1,"jobId":"1","pipelineId":1,"sourceId":1,"stageId":1}}}`

- **成功码是 `code == 0`**，与同为 v3 的查询接口（`code == 200`）不同。
- ⚠ 文档自相矛盾：示例里有 `senondSourceId`（疑似二级渠道），参数表没有。
- 无凭证探测（#B8）：路径存在（伪造 Key、不带文件 → HTTP 500 鉴权错误，而非参数错误）。

## 7. 移动阶段

### 将申请移动到所在职位下的任一阶段
**Endpoint**: `PUT https://api.mokahr.com/api-platform/v1/applications/move_application_stage?applicationId={applicationId}&stageId={stageId}`
**用途**：把申请挪到**同一职位流程内**的任意阶段。

| 参数 | 位置 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `applicationId` | **query** | 是 | 申请 ID |
| `stageId` | **query** | 是 | 目标阶段 ID，用 `GET /v1/data/job_stages?jobId=` 查 |

```bash
curl -s -X PUT "https://api.mokahr.com/api-platform/v1/applications/move_application_stage?applicationId=96&stageId=4" -u "$MOKA_API_KEY:"
```

```python
stages = ats_call("GET", "/v1/data/job_stages", params={"jobId": job_id})   # 返回裸数组 [{"id":1,"name":"初筛"}, …]
target = next(s["id"] for s in stages if s["name"] == "面试")
res = ats_call("PUT", "/v1/applications/move_application_stage",
               params={"applicationId": app_id, "stageId": target})           # 参数在 query，不是 body
assert res.get("code") == 0, res                                              # 0 成功，1 失败
```

- **参数在 query string，方法是 PUT，无 body**——按 REST 习惯写成 JSON body 不会被读取（⚠ 未实测会返回什么）。
- 文档示例用 `http://`，照抄会明文发送凭据且不会被重定向（探测 #A7）。用 `https://`。
- `GET /v1/data/job_stages` 返回**裸数组**，不是 `{data: …}`。无凭证探测（#B10）：路径存在。
- 不在同一职位流程的阶段能否移动：⚠ 文档未说明（接口名写"所在职位下的任一阶段"）。
- 另有 `GET /v2/stage/getStagesList`、`GET /v2/pipelines/getPipelinesList` 可查全部阶段 / 流程。

## 8. 归档（淘汰）到人才库

### 归档申请（可选发拒信）
**Endpoint**: `POST https://api.mokahr.com/api-platform/v1/archiveApplicationToTalentPool`

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `applicationIds` | array[integer] | 是 | 申请 IDs |
| `hireMode` | integer | 是 | 1 社招 / 2 校招 |
| `operatorEmail` | string | 是 | 操作人邮箱 |
| `talentPoolIds` | array[integer] | 是 | 目标人才库（`GET /v1/talentPool/list?hireMode=1` 查） |
| `reasonId` | integer | 否 | 归档原因 ID（`GET /v1/archiveReasons` 查，拒绝类型） |
| `detail` | string | 否 | 归档原因说明 |
| `needRefuse` | boolean | 否 | `true` 时按租户设置发拒信 |
| `businessUnitId` | number | 否 | BU id |

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/v1/archiveApplicationToTalentPool" -u "$MOKA_API_KEY:" \
  -H "Content-Type: application/json" \
  -d '{"applicationIds":[411250317],"talentPoolIds":[200003160],"reasonId":2455,"hireMode":2,"operatorEmail":"hr@example.com","needRefuse":false}'
```

响应：`{"code":0,"msg":"成功"}`（0 成功 / 1 失败）。**会不会给候选人发拒信由 `needRefuse` 决定**，默认不传即不按设置发——批量淘汰前确认用户意图。

## 9. 附件与简历文件

### 按申请 Id 获取候选人附件
**Endpoint**: `POST https://api.mokahr.com/api-platform/v3/attachments/get`，body `{"applicationId": 5567833}`（单个）

返回（`code == 200`）：`resumeUrl`（原始简历）、`standardResumeUrl`（标准简历 PDF）、`attachments4App[]`（申请附件）、`attachments4Ca[]`（候选人附件），
每个附件 `{id, name, size, createdAt, url, type, customFieldId, customFieldName, applyFormId}`；
`type` 如 `ORIGINAL_RESUME`、`CANDIDATE_UPLOAD_ATTACHMENT`、`HR_UPLOAD_ATTACHMENT`、`OFFER_ACCEPT`、`ID_CARD_FRONT`、`ID_CARD_BACK` 等。

- 下载链接是带 `Expires` / `Signature` 的 OSS 签名 URL，**会过期**：要落盘就立刻下载，不要只存 URL。
- 纯文本简历内容：`POST /api-platform/application/resumeContent/get`（根据申请 id 获取简历解析文本，字段见文档）。

## 10. 其他候选人接口速查

以下只列路径与用途（均出自文档），字段表见文档对应小节：

| 用途 | Endpoint |
| :--- | :--- |
| 查候选人的全部申请及状态 | `POST /api-platform/candidate/v1/getApplicationStates` |
| 按流程取符合条件的申请 | `POST /api-platform/candidate/v1/application/list_by_pipeline` |
| 拉黑 / 移出黑名单 | `POST /api-platform/v1/blackCandidate` · `POST /api-platform/v1/talentPool/blackList/remove` |
| 标签：查租户标签 / 加 / 删 / 按申请取 | `POST /api-platform/candidate/v3/query/tags` · `…/v3/add/tags` · `…/v3/remove/tags` · `POST /api-platform/candidate/getLabels` |
| 写候选人操作记录 | `POST /api-platform/candidate/v1/create_activities` |
| 候选人 / 申请自定义字段 | `GET /api-platform/v1/candidates/custom_fields` · `POST /api-platform/v3/applications/setCustomFields/byApplicationId` |
| 查人才库 / 库内候选人 / 移动复制 | `GET /api-platform/v1/talentPool/list` · `GET /api-platform/v1/talentPool/candidates` · `POST /api-platform/v1/reserveOtherTalentPool` |
| 人才库数据导入 | `POST /api-platform/v2/syncCandidates` |
| 查候选人锁状态 | `POST /api-platform/pipeline/v3/queryLockedApplications` |

注意这些路径前缀并不统一（`/api-platform/v1/…`、`/api-platform/candidate/v3/…`、`/api-platform/pipeline/v3/…`），**逐个照文档完整 URL 写**，不要自行拼成 `/v1/…`。

## 11. ⚠ 汇总

- ⚠ 文档未说明：`/v1/data/applications` 的 `fromTime` 格式、`next` 能否跨次持久化。
- ⚠ 文档未说明：`list_by_condition` 时间窗超过 3 个月时的行为。
- ⚠ 文档未说明：官网申请接口失败时的响应格式。
- ⚠ 文档自相矛盾：`uploadResume` 的 `websiteSourceName` 类型；示例中的 `senondSourceId` 不在参数表。
- ⚠ 文档未说明：`move_application_stage` 能否跨职位流程；把参数放 body 时的行为。
- 成功码不统一：`/v1/data/*` 无 code；v3 查询 `code == 200`；`uploadResume`、移动阶段、归档 `code == 0`。
