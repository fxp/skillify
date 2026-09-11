---
name: moka
description: 接入 Moka（摩卡，MokaHR，mokahr.com）开放 API 的使用手册，覆盖两套互不通用的接口：Moka 招聘 ATS OpenAPI（api.mokahr.com/api-platform，API Key 走 HTTP Basic 或 OAuth2 accessToken）与 Moka People 人事 OpenAPI（api.mokahr.com/api-platform/hcm/oapi，Basic 加 entCode、apiCode、nonce、timestamp 与 MD5withRSA 签名）。内容包括组织架构与用户同步、职位与招聘需求 HC、候选人与申请的增量拉取、上传简历、移动阶段、面试与 Offer、入职标记、People 的部门、员工任职数据、新增与离职员工、待入职、ATS 与 People 的 Webhook 验签与重试、错误码、限流与分页。当用户提到 Moka、摩卡、MokaHR、Moka People、Moka 招聘、mokahr.com、api.mokahr.com、entCode、apiCode、pushCandidate、导入EHR 推送，或要写代码把招聘系统或人事系统与 eHR、OA、BI、自研官网对接时，应主动使用本技能，不要凭记忆编造接口路径、签名算法或成功码，也不要套用北森、飞书人事、钉钉等其他 HR SaaS 的接口习惯。
---
# Moka 接入指南（ATS 招聘 + People 人事）

Moka 开放平台（open.mokahr.com）有两套独立的 OpenAPI：**ATS**（招聘：职位、候选人、面试、Offer）与 **People**（人事：组织、员工、待入职）。
两套的 Base URL、鉴权、响应结构、推送机制都不同。**本页只做分流与规则，字段表和示例在 references/。**

## ⚠ 验证状态

文档版：内容整理自 <https://www.mokahr.com/docs/api/>（ATS，27 个一级章节 / 210 个二级小节）与
<https://people.mokahr.com/docs/api/view/v1.html>（People，15 个一级章节 / 191 个二级小节），抓取于 2026-09-11，**未用真实凭证调用验证**。
另做了 50 次无凭证探测（伪造 Key / 签名，确认鉴权失败格式、路由是否存在、域名），并本地复算了 webhook HMAC、AES 示例与 People RSA 签名。
报错描述凡未标「无凭证探测」的，都是「文档原文，未实测」。拿到凭证后按 `moka-workspace/verification-plan.md` 补测；对照实验待真实凭证到位后进行。

## 当前事实

| 项 | 值 |
| :--- | :--- |
| ATS Base URL | `https://api.mokahr.com/api-platform/v1`（部分接口在 `/v2`、`/v3`、`/api-platform/<模块>/…`、`/open-api/ats/v3/…`，照文档完整 URL 写）；国际版 `hire-r1-api.mokahr.com` |
| ATS 鉴权 | `Authorization: Basic base64("<API_KEY>:")`（Key 作用户名、密码空，curl `-u "$KEY:"`）；或 `POST /v1/auth/oauth2/getToken` 换 2 小时 `accessToken` 后 `Bearer` |
| People Base URL | `https://api.mokahr.com/api-platform/hcm/oapi` |
| People 鉴权 | Basic `apiKey:` **加** query `entCode`、`apiCode`、`nonce`、`timestamp`（毫秒）、`sign`（部分接口还有 `userName`）；`sign` = 除 sign 外的 query 按 key 字典序拼 `k=v&…` 后 MD5withRSA、Base64、URL 编码 |
| 鉴权失败（无凭证探测，复跑一致） | ATS：**HTTP 500** `{"code":-1,"success":false,"msg":"无法识别的认证信息"}`；OAuth2 失败 **HTTP 200** + `code:110020`；People：**HTTP 403** `{"success":false,"msg":"无法识别的认证信息"}` |
| 最容易选错 | 用哪套 API、哪个 People `apiCode`（每个接口一个，按数据源生成）；ATS 各接口成功码不同（`success` / `code:0` / `code:200` / 无信封） |
| 推送 | ATS：POST JSON，`?sign=` = HMAC-SHA256(signing key, 原始 body) 十六进制；People：多为 GET，只带 ID，`pwd` 校验，1 秒内回 `{"code":"200"}` |

## 照通用经验写容易错的地方（来自文档，未实测）

1. **招聘和人事是两套 API，不能混写。** People 每个请求都要 RSA 签名，且每个能力要在「对外接口设置」单独建接口拿 `apiCode`；同一个 `POST /v1/batch/data` 返回员工任职、异动还是 IM 员工数据，由 apiCode 对应的数据源决定。
2. **ATS 没有统一的成功判定。** 有的回 `{"success":true}`，有的 `code:0`，V3 查询 `code:200`，增量接口只有 `{data,next}`；鉴权失败是 HTTP 500（无凭证探测）——把 5xx 当临时故障重试会对错误 Key 无限重试。
3. **分页至少五种。** `fromTime` 起步再只带 `next`（`/v1/data/*`）、body 里的 `next`（V3，每页 ≤ 20，时间窗 ≤ 3 个月）、`limit`+`offset`、People `pageNum`+`pageSize ≤ 200`、`nextCursor`+`hasMore`；面试列表一次 ≤ 31 天。
4. **参数位置与拼写反直觉。** 移动阶段、回写 Offer 接受 / 拒绝是 `PUT` + query 参数；申请批量详情路径是文档拼写 `getApplictaions`（无凭证探测：`getApplications` 返回 404）；`getJobs` 的 `hireMode` 是 `"social"/"campus"`，别处是 `1/2`。
5. **`PUT /v2/departments` 是全量同步：没传的部门会被标记删除。** 新增用 `POST /v2/departments/sync/incremental`，更新用 `POST /v2/departments`；用户同步 `departmentCode: []` 表示"所有部门"，`updateDepartment` 默认 `true`。
6. **Webhook 验签对原始 body 字节做。** 本地复算：文档示例只在紧凑 JSON 下对得上，Python `json.dumps` 默认带空格就对不上；文档 AES 解密示例编码写反（本地执行报 `ERR_OSSL_BAD_DECRYPT`）。People 推送只给 ID、按 `requestUniqueKey` 去重，重试 15s/5m/1h/6h。
7. **写入不会"顺便"做你以为的事。** `sendOffer` 的短信 / 邮件 / 微信通知默认全关；People 员工写接口外层 `code:0` 也可能逐条失败（看 `data.data[].success`）；People 写入日期是毫秒时间戳，读出却是 `yyyy-MM-dd`。

## 我要做什么 → 读哪一份

| 我要做什么 | 读 | 核心 endpoint |
| :--- | :--- | :--- |
| 选对 API 与域名、ATS Basic / OAuth2、People 签名、看懂鉴权失败 | [`auth.md`](references/auth.md) | `POST /v1/auth/oauth2/getToken` · People `sign`（MD5withRSA） |
| 把 eHR 的部门与账号同步进招聘系统 | [`ats-org-users.md`](references/ats-org-users.md) | `PUT /v2/departments` · `POST /v2/departments/sync/incremental` · `POST /v2/users/syncInfo` · `POST /open-api/ats/v3/users/list` |
| 职位的查询 / 创建 / 更新 / 发布，招聘官网，招聘需求 HC | [`jobs.md`](references/jobs.md) | `POST /v1/jobs/getJobs` · `POST /v1/jobs` · `GET /v1/jobs/{orgId}` · `POST /v1/headcount` |
| 候选人与申请：增量拉取、批量详情、上传简历、移动阶段、归档、附件 | [`candidates.md`](references/candidates.md) | `GET /v1/data/applications` · `POST /v3/data/getApplictaions` · `POST /v3/candidate/uploadResume` · `PUT /v1/applications/move_application_stage` |
| 创建面试、Offer 创建 / 审批 / 发送 / 回写、标记入职 | [`interviews-offers.md`](references/interviews-offers.md) | `POST /v1/interview/create` · `POST /v1/create-offer` · `POST /v1/sendOffer` · `PUT /v1/applications/{applicationId}/hired` |
| People：部门、员工任职数据、新增 / 更新 / 离职员工、待入职、职位职务 | [`people-hr.md`](references/people-hr.md) | `POST /v1/batch/data` · `POST /v1/org/department/batchData` · `POST /v2/core/rosters/addEmployees` · `POST /v1/basic/ob/employee/batchCreate` |
| 接收 ATS 与 People 的推送：验签、解密、回复、重试、幂等 | [`webhooks.md`](references/webhooks.md) | ATS `POST 回调?sign=` · People `GET/POST 回调?apiCode&pwd` |
| 错误码、限流、分页方式、时间格式、空值 | [`errors-and-limits.md`](references/errors-and-limits.md) | ATS 错误码表 · People 全局错误码（含 HTTP 600 限流） |

本 skill 不覆盖：ATS 的招聘官网来源 / 宣讲会配置、门店、职责、内推奖励与内推账户、猎头、BI 报表、JD 模板、多语言与行政区划码表（均在 <https://www.mokahr.com/docs/api/> 对应章节）；
考试测评、背调、视频面试、叫号面试的服务商接入（<https://www.mokahr.com/docs/api/view/openPlatform.html>）；ATS 旧版接口（`view/v2.html`，官方不建议使用）；
People 的假勤、薪酬、绩效、审批表单、自定义分组、BI 报表（<https://people.mokahr.com/docs/api/view/v1.html> 对应章节）。

## House rules

- 凭证只走环境变量：`MOKA_API_KEY`、`MOKA_CLIENT_ID` / `MOKA_CLIENT_SECRET`、`MOKA_ORG_ID`、`MOKA_PEOPLE_API_KEY`、`MOKA_PEOPLE_ENT_CODE`、`MOKA_PEOPLE_PRIVATE_KEY`、`MOKA_PEOPLE_USER_NAME`、每个 People 接口的 apiCode。
- 一律 `https://`。文档部分示例写 `http://`；无凭证探测：http 不会被重定向，凭据会明文发出。
- ATS 路径照文档**完整 URL** 抄，前缀并不统一（`/v1/…`、`/candidate/v3/…`、`/pipeline/v3/…`、`/jobs/v1/…`、`/open-api/ats/v3/…`）；ATS 路由先于鉴权，拿伪造 Key 请求时 404 = 路径写错。
- 每个调用点按对应 reference 判成功；批量接口看逐条结果（`errorList`、`data[].code`、`data.data[].success`、`failedList`）。
- 需要 `orgId`、`operatorEmail` / `hrEmail`、`apiCode`、RSA 私钥而用户没给时，先问，不要编。
- 写组织架构前确认是全量还是增量；批量淘汰、发 Offer 前确认是否通知候选人（`needRefuse`、`notify*`）。
- People 限流按"每企业每分钟"算（常见 60 次 / 分钟，字段元数据 5 次 / 分钟，待入职写入 20 次 / 分钟），超限是 HTTP `600`。
- 签名 URL（简历、附件）会过期：收到就下载转存。

## 文档自相矛盾 / 未说明之处（⚠ 汇总）

- ATS Basic 的 JS 示例编码 `apiKey` 时没有冒号；哪些接口必须用 OAuth2 未说明；`clientID` 大小写敏感性未知 → `auth.md`
- People `nonce` 长度 ≤10 位 vs ≤8 位；RSA 密钥对来源未说明；ATS 与 People apiKey 是否同一个未说明 → `auth.md`
- 部门全量 / 增量 / 更新、V3 用户列表的成功码：示例 `0` vs 字段表 `200`；用户同步失败示例 `code:-1` 配 `msg:"success"` → `ats-org-users.md`、`errors-and-limits.md`
- `getJobs` 的 `commitment` 类型（数字 vs 示例中文）；V3 职位详情 `sence`/`scene`，返回表描述抄错；更新职位未写 HTTP 方法、不传官网展示开关是否下架未说明；`/v1/data/headcounts` 必填标注矛盾 → `jobs.md`
- `fromTime` 格式、`next` 能否跨次复用未说明；V3 时间窗超 3 个月的行为未说明；`uploadResume` 的 `websiteSourceName` 类型与示例 `senondSourceId` → `candidates.md`
- 创建面试返回字段描述张冠李戴、`startTime` 时区与 `signedInAt` 必填未解释；`sendOffer` 的 `hrEmail` 必填但示例没有；Offer `salaryNumber` 单位与类型 → `interviews-offers.md`
- People 待入职数据 `pageSize` ≤50 vs ≤200；`employee_type_id=4` 兼职 / 兼岗；新增员工必填字段未标 → `people-hr.md`
- ATS 推送重试、`triggeredAt` 单位、AES 密钥格式未说明；回复"2xx 即可" vs 面试推送要求 `code:0`；People 推送时限 1 秒 vs 3 秒；文档 AES 解密示例有误（本地执行证实）→ `webhooks.md`

## 文档与探测不符之处

reference 中用 `<!-- Gap: … -->` 标记，可 grep 定位（1 处）：People 文档写鉴权失败为 HTTP 401 / `100001`，无凭证探测（复跑一致）实际为 HTTP 403 且 body 无 `code` → `auth.md` 第 7 节。
