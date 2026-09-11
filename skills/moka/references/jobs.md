# 职位与招聘需求（ATS）

> 来源：ATS 文档「职位API」「招聘需求 API」「招聘官网API」<https://www.mokahr.com/docs/api/>（抓取于 2026-09-11）。
> **文档版，未用真实凭证调用验证。** 报错 / 行为描述除标「无凭证探测（2026-09-11）」外均为「文档原文，未实测」。
> 鉴权见 `auth.md`；`ats_call()` 为 `auth.md` 第 8 节的最小客户端。

## 目录

1. [同一个概念的四种写法（先看）](#1-同一个概念的四种写法先看)
2. [查询职位](#2-查询职位)
3. [按 ID / mjCode 取职位详情（V3）](#3-按-id--mjcode-取职位详情v3)
4. [增量拉职位](#4-增量拉职位)
5. [创建职位](#5-创建职位)
6. [更新职位](#6-更新职位)
7. [发布 / 下架职位](#7-发布--下架职位)
8. [招聘官网接口（给自研官网用）](#8-招聘官网接口给自研官网用)
9. [流程、阶段与字典数据](#9-流程阶段与字典数据)
10. [招聘需求（Headcount）](#10-招聘需求headcount)
11. [⚠ 汇总](#11--汇总)

---

## 1. 同一个概念的四种写法（先看）

| 概念 | 写法 | 出现在 |
| :--- | :--- | :--- |
| 招聘模式 | query `currentHireMode=1/2` | 创建职位、创建招聘需求、流程列表 |
| 招聘模式 | body `hireMode: "social" / "campus"`（**字符串**） | `POST /v1/jobs/getJobs` |
| 招聘模式 | query `mode=social / campus` | 招聘官网 `GET /v1/jobs/{orgId}` |
| 招聘模式 | `hireMode: 1 / 2`（整数） | 职位 / 申请的返回值、V3 申请查询 |
| 职位性质 | `"全职" / "兼职" / "实习" / "其它"`（中文） | 创建 / 更新职位、职位返回值 |
| 职位性质 | `1 / 2 / 3 / 4`（数字） | `getJobs`、招聘官网的筛选参数 |
| 职位性质 | `fulltime / parttime / intern / other` | 招聘需求 |
| 薪资 | 数值 + `salaryUnit`（`0` k/月、`1` 元/月、`2` 元/周、`3` 元/天、`4` 元/小时、`5` 元/次） | 创建职位 / 招聘需求 |

- ⚠ 文档自相矛盾：`getJobs` 参数表写 `commitment` 是 number（1–4），同页示例传的是 `"全职"`。
- ⚠ 文档自相矛盾：招聘需求返回表写 `commitment` 可选值为中文，示例返回 `"fulltime"`。
- 招聘官网返回的 `minSalary` / `maxSalary` 文档原文单位是「千（K）」，V3 详情写「单位为k」；带 `salaryUnit` 时以 `salaryUnit` 为准。

## 2. 查询职位

**Endpoint**: `POST https://api.mokahr.com/api-platform/v1/jobs/getJobs`
**用途**：按部门 / 地点 / 状态 / 更新时间 / 自定义字段筛选系统里的职位。

| 参数（body） | 类型 | 必填 | 默认 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `hireMode` | string | 是 | — | `social` 社招 / `campus` 校招 |
| `limit` / `offset` | string | 否 | 30 / 0 | 分页 |
| `status` | string | 否 | — | `open` / `closed` / `pause` |
| `jobId` | string | 否 | — | 单个职位 |
| `departmentCodes` / `storeCodes` | array | 否 | — | 部门 / 门店编码 |
| `locationIds` / `zhinengId` / `siteId` | — | 否 | — | 地点 / 职能 / 官网 |
| `commitment` | number | 否 | — | 1 全职 2 兼职 3 实习 4 其它（⚠ 见第 1 节） |
| `updatedFromAt` / `updatedEndAt` | string | 否 | — | 按更新时间，如 `2020-06-01` |
| `customFields[]` | array | 否 | — | `{id, value}` |

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/v1/jobs/getJobs" -u "$MOKA_API_KEY:" \
  -H "Content-Type: application/json" -d '{"hireMode":"social","status":"open","limit":30,"offset":0}'
```

```python
def iter_open_jobs(hire_mode="social"):
    offset = 0
    while True:
        res = ats_call("POST", "/v1/jobs/getJobs",
                       json={"hireMode": hire_mode, "status": "open", "limit": 30, "offset": offset})
        jobs = res["data"]["jobs"]
        yield from jobs
        offset += len(jobs)
        if not jobs or offset >= res["data"]["total"]:
            return
```

返回（文档示例）：`{"code":0,"msg":"success","data":{"total":1,"jobs":[{"id","title","status","mjCode","commitment","department{id,code,name}","locations[]","pipelineId","customFields[]","updatedAt",…}]}}`

- `jobManager` / `jobHrAssistant` / `jobHiringManager` / `jobInterviewer` **默认不返回**，要 CSM 在后台打开「官网职位接口负责人同步开关」。
- 无凭证探测（2026-09-11，#B6）：路径存在（伪造 Key → HTTP 500 `系统中不存在该apiKey`）。

## 3. 按 ID / mjCode 取职位详情（V3）

**Endpoint**: `POST https://api.mokahr.com/api-platform/v3/job/getJobInfo`

| 参数 | 必填 | 说明 |
| :--- | :--- | :--- |
| `jobIds` | 与 `mjCodes` 至少一个 | 最多 20 个（文档推荐用 jobId，性能更好） |
| `mjCodes` | — | 最多 10 个；与 jobIds 同时存在以 jobId 为准 |
| `sence` / `scene` | 否 | 查询场景；不传只返回基本信息，要负责人 / 自定义字段等找 CSM |

返回 `{"code":0,"codeType":0,"data":[…]}`；时间字段为**毫秒时间戳**；含 `hcIds`、`jobRanks[]`、`locations[]`、`stores[]`、`pipelineId`、`customFields[]`（多选值在 `multiSelectValue`）、`jobFamily`（是否虚拟职位）等。

- ⚠ 文档自相矛盾：参数表字段名写 `sence`，示例请求写 `scene`；参数表把三个参数都标「是」必填，描述又说二选一 / 可不传。
- ⚠ 文档自相矛盾：返回表把 `code` 描述为「面试id」、`message` 为「面试开始时间」（从面试接口复制错），示例里也没有 `message` 字段。

## 4. 增量拉职位

**Endpoint**: `GET https://api.mokahr.com/api-platform/v1/data/jobs`
参数与游标规则同 `GET /v1/data/applications`：首次 `fromTime`，之后只带 `next`，响应无 `next` 即结束，`limit` 默认 100。
返回 `{"data":[{"id","title","status"}],"next":"…"}`——只有 3 个字段，详情用第 3 节补。

## 5. 创建职位

**Endpoint**: `POST https://api.mokahr.com/api-platform/v1/jobs?currentHireMode=1`
文档原文：「创建职位时间即为开始招聘时间」。

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `currentHireMode`（query） | integer | — | 1 社招 / 2 校招（表中未标必填，示例带） |
| `title` | string | 是 | 职位名称 |
| `commitment` | string | 是 | `全职` / `兼职` / `实习` / `其它` |
| `status` | string | 否 | `open` / `closed` / `pause` |
| `departmentCode` | string | 否 | 组织架构同步时用的部门 code（见 `ats-org-users.md`） |
| `number` | integer | 否 | 招聘人数 |
| `experience` | string | 否 | `不限`、`应届毕业生`、`1年以下`、`1-3年`、`3-5年`、`5-10年`、`10年以上` |
| `education` | string | 否 | `不限`、`高中以下`、`中专`、`大专`、`本科`、`硕士`、`博士` |
| `minSalary` / `maxSalary` / `salaryUnit` | integer | 否 | 见第 1 节 |
| `locationId` / `locationIds` | — | 否 | 同时存在优先 `locationIds` |
| `managerEmail` / `managerNumber` | string | 否 | 负责人；有 number 时忽略 email；`managerNumber=-1` 删除负责人 |
| `hrAssistantEmails` / `hiringManagerEmails` / `interviewerEmails` | array | 否 | 协助人 / 用人经理 / 面试官；对应 `…Numbers` 优先，传空数组 `[]` 清空 |
| `jobRankIds` / `zhinengId` / `jobPriorityId` / `pipelineId` | — | 否 | 职级 / 职能 / 优先级 / 招聘流程 |
| `headcountIds` | array | 否 | 关联招聘需求 |
| `customData` | object | 否 | key = 自定义字段 id；多选字段 value 为**选项 id 数组** |
| `siteIds` / `storeIds` | array | 否 | 官网 / 门店 |
| `isVirtual` / `jobIdsForVirtualJobList` | — | 否 | 虚拟职位及其关联的实体职位 |
| `confidential` | integer | 否 | 1 保密职位 |

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/v1/jobs?currentHireMode=1" -u "$MOKA_API_KEY:" \
  -H "Content-Type: application/json" \
  -d '{"title":"后端工程师","commitment":"全职","status":"open","departmentCode":"RD-01","managerEmail":"hr@example.com","minSalary":20,"maxSalary":40,"salaryUnit":0}'
```

```python
res = ats_call("POST", "/v1/jobs", params={"currentHireMode": 1},
               json={"title": "后端工程师", "commitment": "全职", "departmentCode": "RD-01"})
if not res.get("success"):
    raise RuntimeError(res)
job_id, mj_code = res["data"]["jobId"], res["data"]["mjCode"]   # jobId 是 UUID 字符串
```

返回：`{"success": true, "data": {"jobId": "d7556714-…", "mjCode": "MJ001789"}}`。`jobId` 是字符串 UUID，`mjCode` 是对外展示的职位编号。

## 6. 更新职位

**Endpoint**: `PUT https://api.mokahr.com/api-platform/v1/jobs/{jobId}`

- body 字段「和创建新职位的body参数一致」，另有本接口特有字段：`archive`（是否放入人才库）、`tempJobToJob`（0 保持 / 1 取消 / 2 重新关联）、`distributeJobId`、
  `displayOnOfficialSite` / `displayOnRecommendationSite`（文档写「默认: false」）、`departmentCode`（**传 `null` 会删除职位的部门**）、`storeIds`、`publishedAt`。
- ⚠ 文档未说明 HTTP 方法：「HTTP请求」一栏只有 URL 没有方法，示例用 `PUT`。
- ⚠ 文档未说明：更新时不传 `displayOnOfficialSite` / `displayOnRecommendationSite` 是"保持不变"还是按默认 `false` 从官网下架。
  **更新前先用第 3 节读出当前状态，更新时显式带上这两个值**，或者只用第 7 节的发布接口改展示状态。
- 返回 `{"success": true, "data": {"jobId": "…"}}`。

```python
ats_call("PUT", f"/v1/jobs/{job_id}", json={"title": "高级后端工程师", "commitment": "全职",
                                            "displayOnOfficialSite": True})   # 显式保持官网展示
```

## 7. 发布 / 下架职位

**Endpoint**: `POST https://api.mokahr.com/api-platform/jobs/v1/display_job_on_websites`（注意前缀是 `/api-platform/jobs/v1/`）

| 参数 | 必填 | 说明 |
| :--- | :--- | :--- |
| `jobId` | 是 | 职位 ID |
| `siteIds` | 是 | 要发布 / 下架的官网 ID |
| `displayOnOfficialSite` | 否 | **不传 = 状态不变**；`true` 发布；`false` 下架 |
| `displayOnRecommendationSite` + `recommendationSiteIds` | 否 | 内推官网 |
| `displayOnHeadhunterSite` + `headhunterIds` / `headhunterContractIds` | 否 | 猎头端 |

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/jobs/v1/display_job_on_websites" -u "$MOKA_API_KEY:" \
  -H "Content-Type: application/json" -d '{"jobId":"c9705c0d-…","siteIds":[364],"displayOnOfficialSite":true}'
```

返回：`{"code":0,"success":true,"data":{"operateOfficialSiteSuccess":…,"operateRecommendationSiteSuccess":…,"operateHeadhunterSiteSuccess":…}}`；
文档原文「参数没传和操作失败都是false」——所以 `false` 不一定是失败，只检查你实际传了的那一项。

- ⚠ 文档自相矛盾：返回表写 `data[]`（数组），示例是对象；示例把 `headhunterIds` 写成字符串 `"[200000063,…]"`，参数表是 array。

## 8. 招聘官网接口（给自研官网用）

### 获取官网职位列表
**Endpoint**: `GET https://api.mokahr.com/api-platform/v1/jobs/{orgId}?mode=social`

| 参数 | 必填 | 说明 |
| :--- | :--- | :--- |
| `orgId`（path） | 是 | 租户 ID |
| `mode` | 是 | `social` / `campus` |
| `keyword` / `limit`（默认 30）/ `offset` / `locationIds` / `zhinengId` / `siteId` / `commitment`（1–4）/ `updatedFromAt` / `updatedEndAt` / `departmentCodes` / `status` | 否 | 筛选与分页 |

```bash
curl -s "https://api.mokahr.com/api-platform/v1/jobs/$MOKA_ORG_ID?mode=social&limit=30&offset=0"
```

- 文档示例请求**不带任何鉴权**。无凭证探测（2026-09-11，#C1，复跑两次一致）：不带鉴权头调 `GET /api-platform/v1/jobs/<伪造 orgId>`，
  返回 **HTTP 403** `{"message":"招聘模式 必填","msg":"招聘模式 必填","code":3}`——是参数校验错误而不是鉴权错误，说明该接口至少在参数校验阶段不要求 API Key。
  不带 Key 能否真的拿到职位数据：未证实（需要真实 orgId）。前端直调前先与用户确认是否允许暴露。
- Q&A（文档原文）：已关闭职位若关闭时没勾选"取消在官网显示"，仍会出现在列表里（`closedAt` 有值）；删除的职位彻底消失。
- 其他官网接口：单个职位 `GET /v1/jobs/{orgId}/{jobId}`、按地点 / 职能分组 `GET /v1/jobs-groupedby-location/{orgId}` · `GET /v1/jobs-groupedby-zhineng/{orgId}`、
  官网列表 `GET /v1/website/list`、投递 `POST /v1/jobs/{orgId}/{jobId}/apply`（见 `candidates.md` 第 6 节）、申请状态 `GET /v1/applications/{applicationId}`。

### 零代码嵌入申请页（iframe）
在官网申请页 URL 后加 `pure=1` 得到纯净版申请表（文档原文）：

- PC：`https://app.mokahr.com/apply/{orgId}/{siteId}#/job/{jobId}/apply?pure=1`
- 移动：`https://app.mokahr.com/m/apply/{orgId}/{siteId}#/job/{jobId}/select?pure=1`
- 校招把路径里的 `apply` 换成 `campus_apply`；`siteId` 没开多官网可省略。

## 9. 流程、阶段与字典数据

| 用途 | Endpoint | 返回形态 |
| :--- | :--- | :--- |
| 招聘流程列表 | `GET /api-platform/v1/pipelines/list?currentHireMode=1`（`currentHireMode` 必填） | `{"rows":[{"id","name","disabled"}]}` |
| 职位下可移动的阶段 | `GET /api-platform/v1/data/job_stages?jobId=…` | 裸数组 `[{"id","name"}]` |
| 全部流程 / 阶段（V2） | `GET /api-platform/v2/pipelines/getPipelinesList` · `GET /api-platform/v2/stage/getStagesList` | 见文档 |
| 职位优先级 / 职级 | `GET /api-platform/v1/job_priority` · `GET /api-platform/v1/job_ranks`（职级另有 POST / PUT / DELETE） | 见文档 |
| 地点 / 职能 | `GET /api-platform/v1/locations` · `POST /api-platform/v1/zhineng/getZhineng` | 见文档 |
| 职位字段 / 自定义字段 | `GET /api-platform/v1/jobs-fields` · `POST /api-platform/v1/jobs-custom-fields` | 见文档 |
| JD 模板 | `POST /api-platform/v1/job/job_desc_template/list` | 见文档 |

## 10. 招聘需求（Headcount）

文档原文：「写入接口请求频率限制1分钟30次」。枚举：

| 字段 | 取值 |
| :--- | :--- |
| `status` | `draft` 草稿、`unstart` 未进行（默认）、`ongoing` 进行中、`complete` 已完成、`suspend` 已暂停、`canceled` 已取消、`timeout` 已超期 |
| `type` | `planned` 计划内（默认）、`unplanned` 计划外 |
| `commitment` | `fulltime`（默认）、`parttime`、`intern`、`other` |
| `hiremode` | `1` 社招、`2` 校招 |

### 新建招聘需求
**Endpoint**: `POST https://api.mokahr.com/api-platform/v1/headcount?currentHireMode=1`

| 参数 | 必填 | 说明 |
| :--- | :--- | :--- |
| `number` | 是 | 需求编号，**全局唯一且不可修改**——用你系统的主键 |
| `jobName` | 是 | 需求名称 |
| `needNumber` | 是 | 需求人数 |
| `departmentCode` | 否 | 组织架构同步时的 department_code |
| `type` / `commitment` / `status` | 否 | 见上表 |
| `ownerEmail` / `ownerEmployeeId` | 否 | 汇报对象 |
| `managerEmails` / `managerEmployeeIds` | 否 | 负责人（需有权限，如 HR、超管） |
| `sharedUserEmails` / `sharedUserEmployeeIds` | 否 | 共享人；负责人、共享人、创建人不能为同一人 |
| `creatorEmail` | 否 | 只在创建时可设 |
| `startDate` / `completeDate` | 否 | ISO8601 |
| `connectedJobIds` | 否 | 关联职位 |
| `education` | 否 | `不限`、`高中以下`、`中专`、`中技`、`大专`、`本科`、`硕士`、`博士` |
| `minSalary` / `maxSalary` / `salaryUnit` / `payPeriod`（12–24）/ `paymentMethod`（0 日结 1 周结 2 月结 3 完工结） | 否 | — |
| `customData` | 否 | key = 自定义字段 id；多选为选项 id 数组。文档原文：2024-11-18 前创建的社招字段 id 可用于校招，但「尽量使用真正模式的字段id」 |

```bash
curl -s -X POST "https://api.mokahr.com/api-platform/v1/headcount?currentHireMode=1" -u "$MOKA_API_KEY:" \
  -H "Content-Type: application/json" \
  -d '{"number":"HC-2026-0001","jobName":"后端工程师","needNumber":2,"departmentCode":"RD-01","startDate":"2026-09-15T00:00:00.000Z"}'
```

返回 `{"headcount": {"id": 1, "number": "…", "status": "unstart", "usedNumber": …, "remainNumber": …, …}}`（没有 `success` / `code` 包装）。

### 其他招聘需求接口

| 用途 | Endpoint | 说明 |
| :--- | :--- | :--- |
| 更新 / 删除 | `PUT /api-platform/v1/headcount/{hcId}` · `DELETE /api-platform/v1/headcount/{hcId}` | 计入 30 次/分钟 |
| 按状态列表 | `GET /api-platform/v1/headcounts?currentHireMode=1&status=ongoing&pageNumber=1` | **每页固定 20 条**，只能翻 `pageNumber` |
| 增量拉取 | `GET /api-platform/v1/data/headcounts?fromTime=2018-1-1&limit=100` | 游标同 `/v1/data/applications` |
| 单个详情 / 基本信息列表 / 数量 | `GET /v1/headcount/{hcId}` · `GET /v1/headcount/minimal_headcounts` · `GET /v1/headcount_status/count` | — |
| 核销情况 | `POST /api-platform/v1/headcounts/getHeadcountVerificationInfo` | — |

- 人数口径：`usedNumber`（已使用，入职后又离职会扣减）、`remainNumber = needNumber - usedNumber`、`currentEnrolledNumber`（在职）、`departureNumber`（离职）。
  文档原文建议用「在职人数」与系统招聘需求模块保持一致。
- ⚠ 文档自相矛盾：`/v1/data/headcounts` 参数表把 `fromTime`、`next` 都标为必填，说明又写"二者只带其一"——按二选一。
- 列表接口返回表里有 `startData`（应为 `startDate`，文档笔误）。

## 11. ⚠ 汇总

- ⚠ 文档自相矛盾：`getJobs` 的 `commitment` 类型；招聘需求 `commitment` 返回值；V3 职位详情 `sence`/`scene` 与返回表描述；发布接口 `data` 类型；`/v1/data/headcounts` 必填标注。
- ⚠ 文档未说明：更新职位的 HTTP 方法（示例 PUT）；更新时不传官网展示开关是否会下架职位。
- ⚠ 未证实：招聘官网职位列表不带 API Key 是否返回数据（探测只证实了不带 Key 时走到参数校验）。
