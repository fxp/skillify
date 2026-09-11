# 北森 skill 验证计划（拿到凭证后执行）

现状：文档版，抓取于 2026-09-11，**没有任何真实凭证调用**。下面按优先级列出要验证的结论、用哪个接口、预期成本、怎么判定。
全部来自 reference 里的 ⚠ 标记与「文档原文，未实测」条目。验证结果按 create-doc-skill 的 verify.md 写回：日期 + 做了什么 + 原始报错 / 响应片段。

前提：一个**测试租户**（或沙箱），租户 ID、app_id、AppSecret；连接器勾选下列接口；服务器出口 IP 已加入 OpenAPI 受信 IP。
凭证只走环境变量 `BEISEN_TENANT_ID` / `BEISEN_APP_ID` / `BEISEN_APP_SECRET`，结束后全仓库 grep secret 前 8 位。

## P0 鉴权（先打通，全是只读、零成本）

| # | 要验证 | 做法 | 判定 |
|---|---|---|---|
| 1 | 四字段表单换 token 成功；响应字段类型 | `POST /OAuth/Token` form：app_id、secret、tenant_id、grant_type=client_credentials | 记录 `expires_in` 的类型与数值：秒数（~8400000？）还是时间戳；`tenant_id`/`user_id` 是字符串还是数字 |
| 2 | 缺 `app_id` 能否换 token（Demo 没带） | 同上去掉 app_id | 成功 → 参数表错；失败 → 记录 error 值 |
| 3 | JSON body 是否被接受 | 同样字段用 `application/json` | 记录报错 |
| 4 | secret 错、grant_type 错的错误值 | 各一次 | 记录 `{"error": ...}` 全文，写进 errors-and-limits.md |
| 5 | 业务接口是否必须 `Bearer ` 前缀 | 任一只读接口，header 分别为 `Bearer <t>` 和 `<t>` | 无凭证时两者都是 401，需真实 token 区分 |
| 6 | token 实际有效期 | 换 token 后隔几个小时 / 一天调用 | 确定合理的本地缓存时长 |
| 7 | 连接器未勾选的接口返回什么 | 调一个未勾选接口 | 401？403？body？ |
| 8 | 沙箱域名 | 向实施顾问确认；文档只出现过 `openapi.italent-dev.cn` | 写进 auth-and-conventions.md 第 1 节 |

## P1 组织员工读取（只读）

| # | 要验证 | 接口 | 判定 |
|---|---|---|---|
| 9 | 枚举传数字 vs 传字符串名 | `Employee/GetByTimeWindow`：`empStatus:[1]` vs `["ForEntry"]`；`timeWindowQueryType:2` vs `"BusinessModifiedTime"` | 哪种被接受、是否静默忽略（**重点：静默失效**） |
| 10 | 数字 ↔ 含义完整表 | `/dataservice/api/DataSource/GetDataSource` 查 EmployeeStatus / EmployType / ServiceType / ApprovalStatus 的数据源（app / dsName 取值需先查社区参考页 pageId 95813878 等） | 补全 employees.md 第 3 节表格 |
| 11 | 90 天是硬限制 | 时间窗 91 天 | 417 `只支持查询90天范围内的数据，请分段查询` 则确认 |
| 12 | scrollId 10 秒过期 | 拿到第一批后 sleep 15 秒再续 | 空 data？报错？ |
| 13 | `timeWindowQueryType` 省略时的默认 | 不传 | 与 1 / 2 的结果对比 |
| 14 | `isGetLatestRecord` true / false 差异 | 找一个有未来生效调动的员工 | 两次 `oIdDepartment` 不同即确认 |
| 15 | 响应里 `employeeStatus` string、`employType` int 的混用 | 同上 | 确认类型 |
| 16 | `GetUserIDsByJobNumbers` 逐条 code | 一个存在、一个不存在的工号 | 不存在的条目 `userId` 是否为空（文档示例带了 userId） |
| 17 | 邮箱大写是否查不到 | `GetUserIDByEmail` 大写 / 小写各一次 | 大写返回 null 则确认「需小写」 |
| 18 | `GetBasicInfoByIds` 的 oIds 传字符串 | `["388551"]` vs `[388551]` | |
| 19 | `Organization/GetSubOrganizations` 根 OId = 900+租户ID | `oId=900<tenantId>` | 返回一级组织即确认 |
| 20 | `pOIdOrgReserve2 = -2` 含义 | 看真实数据 | |
| 21 | `columns` 不选的字段是否仍出现为 null | | |
| 22 | 公开错误码表的长码（`00908-…`）是否出现在响应里 | 触发一个编制相关错误 | 记录响应里 code / message 的真实形态 |

## P2 限流与网关

| # | 要验证 | 做法 | 判定 |
|---|---|---|---|
| 23 | 业务接口是否返回 `X-RateLimit-*` 响应头 | 任一调用看响应头 | 有则写进 errors-and-limits.md |
| 24 | 429 响应体 | **不要压测**；如自然遇到再记录 | |
| 25 | 每日调用总量数值 | 开放平台管理者后台「每日调用次数」 | 写进 errors-and-limits.md 第 5 节 |
| 26 | 受信 IP 403 响应体 | 从名单外 IP 调一次 | 记录 body |

## P3 假勤（先只读，推送用测试员工）

| # | 要验证 | 接口 | 判定 |
|---|---|---|---|
| 27 | 「只能查一天」是否硬限制 | `Vacation/GetVacationInfoByApprovalTime`、`AttendanceStatistics/GetAttendanceStatisticsList` 传多天 | 报错则按一天写死 |
| 28 | `approveStatus` 编号 | 传 1 / 2 对比结果 | 确定 1 = 通过 |
| 29 | `vacationItemCode` 是否必填 | `VacationRemain/GetVacationRemainList` 不传 | |
| 30 | 游标字段 | 翻第二页 | 确认用 `data.sortCursor` 作为下一次 `queryCursor` |
| 31 | `GetListByDate` 的 `vacationType` / `documentType` / `approveStatus` 是编码还是中文 | | |
| 32 | 打卡推送异步链路 | `SwipingCardData/PostAsync` 推 1 条测试打卡 → 读 `X-PAAS-Request-ID` → `AsyncApiExecInfo/GetByRequestId` | 记录 state 流转与 message 格式；推一条重复分钟的打卡看是否 PartialSuccess |
| 33 | 推送 `Code` 是数字还是枚举名 | 同上 | |
| 34 | 字段大小写是否敏感 | `Items` vs `items` | |

成本：打卡推送会在测试员工考勤里产生数据，测完用 `SwipingCardData/Remove`（删除从第三方系统同步的打卡记录）清理。

## P4 招聘（只读为主）

| # | 要验证 | 接口 | 判定 |
|---|---|---|---|
| 35 | `GetApplyListByApplyId` 响应是扁平还是嵌套 | 取 1 条申请 | 修正 recruiting.md 第 3 节 |
| 36 | `GetApplyListByModifiedTime` 时间范围上限、batchId 过期时间 | 大范围 + 间隔续拉 | |
| 37 | `GetStaffInfos` 传 staffId GUID 还是北森 UserID | 两种各一次 | |
| 38 | `RecruitOnBoarding/Entry` 的 body `originalId` 确为录用部门 OId | 测试 Offer | **写接口，只在测试租户** |
| 39 | `TransferPhase` 成功时是否返回 data 统计 | 测试申请 | |

## P5 生命周期写接口（只在测试租户）

| # | 要验证 | 接口 | 判定 |
|---|---|---|---|
| 40 | `pOIdEmpAdmin` vs `poIdEmpAdmin` 大小写 | `CreateForEntry` 各写一次 | 看经理是否写入 |
| 41 | `CreateForEntry` 实际必填项 | 逐个去掉提示里的 6 个必填项 | 记录 417 message |
| 42 | 3 秒防重的报错文本 | `Transfer` 同参数连发两次 | 记录 message |
| 43 | `ProbationPositive` 字段名 | `regularizationDate` vs `positiveDate` | |
| 44 | `DimissionApproval` 的「预计最后工作日」字段名 | 查字段表后调用 | |
| 45 | userId 与 originalId 同时传 | `Transfer` | 记录报错 |
| 46 | `customProperties` 字段名写错是否静默忽略 | `UpdateEmployee` | **静默失效要升到 SKILL.md** |

清理：测试员工用 `CancelEntry` / `DELETE DeleteForEntry` 删除待入职记录；已入职的测试员工办离职。

## 无需凭证、但本次没做的补抓

- 社区文档子页面（FAQ 答案、对接方案 Case1–9、「每日调用次数查询」「特殊符号被转码转译」等）：可用 `https://users.italent.cn/AnnoyDocument/GetHelpDocument?pageId=…` 匿名抓取，
  pageId 需从父页面的链接里解析（本次只抓了 10 篇顶层页面）。
- 文档中心其余 v3.0 应用（薪酬管理、绩效、目标、学习云等）的目录与接口文档：同一套匿名接口可抓。
- 不需要下载任何 SDK / 资料包；北森文档未提供官方 SDK 下载入口（本次未见）。
