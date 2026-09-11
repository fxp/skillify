---
name: beisen
description: 接入北森 iTalent 一体化 HR SaaS 开放平台（open.italent.cn，接口域名 openapi.italent.cn）OpenAPI 的使用手册——涵盖用 tenant_id、app_id、AppSecret 调 POST /OAuth/Token 换 access_token 与 Bearer 鉴权、连接器接口授权与受信 IP；组织单元、职位、职务的时间窗滚动拉取（scrollId）；员工信息与任职记录的全量 / 增量同步、UserID 与工号 / 邮箱 / 手机号反查、状态枚举与数据源翻译；入职、转正、调动、离职写接口与 originalId 外部 ID 映射；假勤（休假、假期余额、考勤记录、打卡读取与异步推送、X-PAAS-Request-ID 查任务状态）；招聘（申请、应聘者、流程阶段转移、职位、入职管理）；错误码与限流。当用户提到"北森""iTalent""Beisen""open.italent.cn""openapi.italent.cn""TenantBaseExternal""AttendanceOpen""RecruitV6""北森 OpenAPI""北森 token""北森员工同步"，或要写代码对接北森的组织员工、假勤、招聘数据时，应主动使用本技能，不要凭记忆编造接口路径和参数，也不要套用飞书、钉钉、企业微信或其他 HR 系统的接口习惯。
---
# 北森 iTalent OpenAPI 接入指南

北森 iTalent 的 OpenAPI：用租户 ID + AppSecret 换 token，按「连接器」授权调用组织员工、假勤、招聘等产品线的接口。
**本页只做分流与规则，字段表和示例在 references/。**

## ⚠ 验证状态

文档版：内容整理自 https://open.italent.cn/#/open-document （抓取于 2026-09-11），**未用真实凭证调用验证**。
抓取范围：新版 v3.0 接口文档 718 篇（组织员工 298、假勤管理 165、招聘管理系统 181、PaaS平台 74）、旧版 v2.0 178 篇、社区文档 10 篇、公开错误码表 276 条；
文档站本身是 SPA，内容取自它调用的匿名接口（`open.italent.cn/api/OpenDocument/Get` 等）和 `users.italent.cn/AnnoyDocument/*`。
无凭证探测 10 个请求 × 2 轮（伪造 tenant_id / token），两轮结果一致，命令见 `beisen-workspace/probe-log.md`。
**没抓到的**：文档里「查看可用选项」的枚举选项表（其背后接口匿名返回 404）；社区文档的子页面（FAQ 答案、对接方案详情、每日调用次数查询页）；
需登录的开放平台管理者后台（连接器、受信 IP、调用量）。拿到凭证后按 `beisen-workspace/verification-plan.md` 补测。对照实验待真实凭证到位后进行。

## 当前事实

| 项 | 值 |
| :--- | :--- |
| Base URL | `https://openapi.italent.cn`（文档站 `open.italent.cn`；**只用 https**） |
| 换 token | `POST /OAuth/Token`，**表单** `application/x-www-form-urlencoded`：`app_id`、`secret`、`tenant_id`、`grant_type=client_credentials`。无凭证探测：伪造 tenant_id → HTTP 400 `{"error":"invalid_tenantid"}` |
| 鉴权头 | `Authorization: Bearer <access_token>`；业务接口 `Content-Type: application/json` |
| token 有效期 | ⚠ 文档自相矛盾（表格：秒、8400000；Demo：字符串 `"1479202744"`）→ 保守缓存 + 401 时重取一次 |
| 用哪一代接口 | 新版 v3.0：`/TenantBaseExternal/api/v5/…`（组织员工）、`/AttendanceOpen/api/v1/…`（假勤）、`/RecruitV6/api/v1/…`（招聘） |
| 鉴权失败形态 | 无凭证探测：缺 Authorization → **400** `{"message":"Authorization header is empty"}`；无效 token → **401** `{"message":"un-authorized"}`，**不存在的路径也 401** |
| 最容易选错 | 员工「当前部门」要 `isGetLatestRecord:false`（默认 true 取的是最新、可能未来生效的任职）；各类 ID 类型不同（见下） |

## 照通用经验写容易错的地方（来自文档，未实测）

1. **换 token 是表单 POST 到 `/OAuth/Token`，不是 JSON，也不是 `/token`。** 四个字段按参数表都传（同页 Demo 缺 `app_id`，⚠ 矛盾）；
   文档模板里出现的 `https://openapi.italent.cn/token` 无凭证探测是 404。token 是租户级，`user_id`「此时无效」。
2. **查询接口也是 POST + JSON，而且没有 page/pageSize。** 组织员工用 `scrollId` 滚动：每批 ≤300、时间窗 ≤90 天（超出 417）、
   **两次调用间隔 >10 秒 scrollId 就失效**、以 `data` 为空结束（`isLastData` 已废弃）；假勤用 `queryCursor`←`data.sortCursor`、每页 ≤100；招聘用 `batchId`←`nextBatchId`。
3. **员工同步要显式选对任职记录和状态。** `isGetLatestRecord` 默认 true（最新主职）；`empStatus: null` 与 `[]` 含义不同，默认不含离职、只含内部员工；
   增量同步业务变化用 `timeWindowQueryType: 2`（业务修改时间），否则会收到大量系统刷新产生的变动。
4. **枚举按数字传，但编号起点不统一。** schema 写字符串枚举名，示例全用数字（⚠ 矛盾）；人员状态 / 雇佣关系从 0 起，`timeWindowQueryType`、`queryType` 从 1 起。
   `enableTranslate` 已停用（2026-03-13），字段翻译改调 `/dataservice/api/DataSource/GetDataSource`。
5. **ID 类型各不相同。** 员工 UserID 是 int；组织 OId 是 int，**根组织 = 900 + 租户ID**；职位 OId 是 GUID，职务 OId 是数字字符串；招聘全用 GUID。
   邮箱反查要小写；工号 / 手机号反查一次 ≤30 个且**逐条**看 `data[].code`；写接口 `userId` 与 `originalId` **有且仅有一个**；
   招聘入职接口里的 `originalId` 却是「录用部门 ID」。
6. **HTTP 200 不等于成功，外壳也不统一。** 组织员工 `code` 是字符串 `"417"`，招聘是整数 `400`，假勤推送是大写 `Code`；
   批量接口会部分失败（`failDatas` / 逐条 code）；**打卡、休假推送是异步的**，200 只是受理，要拿响应头 `X-PAAS-Request-ID` 调
   `GET /OpenPlatform/api/AsyncApiExecInfo/GetByRequestId` 看结果。
7. **限流按「租户 × 接口」计、多个连接器共享，另有每日总量。** 分钟额度常远小于秒额度 ×60（如 50/秒、1500/分钟）；日总量用尽当天所有接口 429；
   调动 / 离职 / 转正「相同参数 3 秒内仅能请求一次」；受信 IP 名单外调用返回 403。

## 我要做什么 → 读哪一份

| 我要做什么 | 读 | 核心 endpoint |
| :--- | :--- | :--- |
| 换 token、配请求头、认 ID、处理三套响应外壳、查异步任务状态 | [`auth-and-conventions.md`](references/auth-and-conventions.md) | `POST /OAuth/Token` · `GET /OpenPlatform/api/AsyncApiExecInfo/GetByRequestId` |
| 拉组织架构、下级组织、职位、职务等基础数据 | [`organization-and-positions.md`](references/organization-and-positions.md) | `POST /TenantBaseExternal/api/v5/Organization/GetByTimeWindow` · `…/Organization/GetSubOrganizations` · `…/Position/GetByTimeWindow` |
| 全量 / 增量同步员工与任职记录、用工号 / 邮箱 / 手机号反查 UserID、翻译字段值 | [`employees.md`](references/employees.md) | `POST /TenantBaseExternal/api/v5/Employee/GetByTimeWindow` · `…/Employee/GetUserIDsByJobNumbers` · `/dataservice/api/DataSource/GetDataSource` |
| 新建待入职、入职、转正、调动、离职，维护外部 ID 映射 | [`employee-lifecycle.md`](references/employee-lifecycle.md) | `POST /TenantBaseExternal/api/v5/Employee/CreateForEntry` · `…/Employee/Entry` · `…/Employee/Transfer` · `…/Employee/Dimission` |
| 读休假、假期余额、考勤记录、打卡，推送打卡 / 休假 | [`attendance.md`](references/attendance.md) | `POST /AttendanceOpen/api/v1/Vacation/GetVacationInfoByApprovalTime` · `…/SwipingCardData/PostAsync` · `…/AttendanceStatistics/GetAttendanceStatisticsList` |
| 增量拉申请、取应聘者与简历、推进流程阶段、拉职位、单招聘入职 | [`recruiting.md`](references/recruiting.md) | `POST /RecruitV6/api/v1/Apply/GetApplyListByModifiedTime` · `…/Apply/TransferPhase` · `…/RecruitOnBoarding/Entry` |
| 看懂 400 / 401 / 403 / 417 / 429、限流档位、重试策略 | [`errors-and-limits.md`](references/errors-and-limits.md) | 网关错误 · 业务 `code` · 公开错误码表 |

本 skill 不覆盖：薪酬管理、目标 / 绩效、学习云、继任与发展、日程、森福利、AI 类应用（文档中心一级目录可见，未抓取）；
PaaS 平台的元数据、工作流、审批中心、电子签、通知、Ocean 报表；单点登录（开放应用连接）；旧版 v2.0 接口；事件订阅 / 回调推送（公开文档中未找到说明）。
这些都在 https://open.italent.cn/#/open-document 对应目录下。

## House rules

- 凭证只走环境变量：`BEISEN_TENANT_ID`、`BEISEN_APP_ID`、`BEISEN_APP_SECRET`；AppSecret 和 token 不下发前端。
- 所有调用走一个封装（`auth-and-conventions.md` 第 8 节）：https、Bearer、JSON；401 重取 token 只重试一次；`code`/`Code` 统一转字符串判断；
  日志记下响应头 `X-PAAS-Request-ID`、`EagleEye-TraceID`。
- 滚动 / 游标拉取：**先拉完再处理**，循环里不做慢操作；时间窗切成 ≤90 天。
- 写接口先在测试租户跑通；重试前先查询确认没有写成功，且间隔 >3 秒；批量接口检查 `failCount` / 逐条结果。
- 只接新版 v3.0；不要传 `enableTranslate`；标「不推荐」「已过期」的接口不要新接。
- 部署前确认服务器出口 IP 已加入 OpenAPI 受信 IP；换 token 与业务调用必须是同一环境（沙箱 / 生产）。
- 字段、枚举以文档中心为准；⚠ 处以真实报错为准，并回填 verification-plan。

## 文档自相矛盾 / 未说明之处（⚠ 汇总）

- token：参数表 `app_id` 必填 vs Demo 缺；`expires_in` 类型与数值矛盾；沙箱域名、其他错误值未说明 → `auth-and-conventions.md`
- 状态枚举：schema 字符串 vs 示例数字；数字 ↔ 含义完整表未抓到；`option` 说明数字 vs 示例 `"None"` → `employees.md`
- 时间窗「建议 90 天」vs 超出报 417；时区未说明；职位 / 职务 `isLastData` 未标废弃；`pOIdOrgReserve2 = -2` 含义未说明 → `organization-and-positions.md`
- `GetEmployeeOfOrganization` 标必填字段写着有默认值；`GetBasicInfoByIds` int vs 字符串示例；工号反查示例 417 条目带 userId；响应状态字段 int / string 混用 → `employees.md`
- `Dimission`「不支持离职申请」vs 有 `DimissionApproval`；`pOIdEmpAdmin` vs 示例 `poIdEmpAdmin`；转正 `positiveDate` vs `regularizationDate`；3 秒防重的报错文本未给 → `employee-lifecycle.md`
- 假勤：「一次一天」vs 多天示例（两处）；`vacationItemCode` 必填 vs 示例缺；`QueryCursor` vs `sortCursor`；`approveStatus` 编号两套说法；推送 `Code` 枚举名 vs 数字；GetListByDate 示例返回中文文本 → `attendance.md`
- 招聘：`GetApplyListByApplyId` 嵌套字段表 vs 扁平示例；`TransferPhase` 成功示例无 data；`GetStaffInfos`「北森用户Id」vs GUID；流程接口 404 不在错误码栏；batchId 过期时间未说明 → `recruiting.md`
- 错误码表长码（`00908-…`）与响应 `code` 的关系；429 响应体；每日总量数值 → `errors-and-limits.md`

## 文档与探测不符之处

reference 中用 `<!-- Gap: … -->` 标记（1 处，可 grep 定位）：「接口文档说明」模板写的请求地址 `https://openapi.italent.cn/token`，
无凭证探测两次均返回 404；真正的换 token 地址是 `POST /OAuth/Token` → `auth-and-conventions.md`。
