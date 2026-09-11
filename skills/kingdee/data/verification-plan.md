# kingdee 验证计划（拿到凭证后执行）

当前状态：文档版，未用真实凭证验证（2026-09-11）。本计划把 skill 里所有 ⚠ 转成可测项，按优先级排列。

## 需要的环境

- 一个**测试用**星空数据中心（不要在客户生产账套上跑写操作），补丁 ≥ PT136657【7.3.1310.2】。
- 第三方系统登录授权四项 + ServerUrl，走环境变量 `KD_SERVER_URL`、`KD_ACCT_ID`、`KD_USERNAME`、`KD_APP_ID`、`KD_APP_SECRET`。
- 成本：星空按许可收费，API 调用本身不计费；风险在于写入测试数据——每个写测试结束后 UnAudit + Delete 清理，记录到 `verification-log.md`。
- Key 卫生：结束后 `grep -rn "${KD_APP_ID:0:8}" ~/Workspace/Skillify/kingdee*` 确认无泄漏。

## P0 —— 鉴权（决定整份 skill 能不能用）

| # | 结论 | 怎么测 | 判定 |
| --- | --- | --- | --- |
| A1 | `kd_sign.py` 生成的 9 个头能通过鉴权 | 用 `kd_sign.py` + curl 调 `ExecuteBillQuery`（BD_MATERIAL, FieldKeys=FNumber, Limit=1），同时用官方 SDK 调一次对照 | 两者都返回二维数组；否则逐项比对 SDK `BuildHeader()` 输出 |
| A2 | 时间戳容忍窗口 | 把 `x-api-timestamp` 往回拨 1 / 5 / 15 分钟 | 记录被拒阈值与错误结构（客户服务器 vs 网关是否不同） |
| A3 | `ValidateUser` 的 body 形态与 `LoginResultType` 枚举 | 仅在允许账号密码的测试账套：对象 body；错误密码一次、正确一次 | 记录成功 / 失败的 LoginResultType 值；公有云租户是否直接拒绝 |
| A4 | `GetDataCenterList` 返回结构 | 签名调用 `Kingdee.BOS.ServiceFacade.ServicesStub.Account.AccountService.GetDataCenterList` | 记录字段 |
| A5 | SDK 未初始化时返回异常对象 | 故意留空 AppSecret 调 ExecuteBillQuery | 返回值类型为 RuntimeError 实例而非抛出 |

## P1 —— 查询

| # | 结论 | 怎么测 | 判定 |
| --- | --- | --- | --- |
| Q1 | `Limit` > 2000 的行为 | Limit=2500 查一个大表 | 报错 / 截断到 2000 / 正常返回 |
| Q2 | `StartRow` 从 0 还是 1 起 | StartRow=0 与 1 各查 Limit=2，按内码排序对比 | 重叠情况 |
| Q3 | `Limit` 默认值 | 不传 Limit | 返回行数 |
| Q4 | `FilterString` 语法 | `FNumber='x'`、`FModifyDate>='2026-01-01'`、`like`、`and/or` | 哪些可用；字符串转义 |
| Q5 | `OrderString` 语法 | `FNumber desc` | 是否生效 |
| Q6 | 基础资料字段直接查返回什么；`FMaterialId.FNumber` 点号语法是否支持 | 查 SAL_SaleOrder 的 FMaterialId 与 FMaterialId.FNumber | 返回内码 / 编码 / 报错 |
| Q7 | 查询失败时的返回结构 | FormId 写错、FieldKeys 写一个不存在的 key | 记录结构，更新 `kd_rows()` 判错逻辑 |
| Q8 | FormId 大小写敏感性 | `BD_MATERIAL` vs `BD_Material` | 是否等价（SDK 示例两种都有） |
| Q9 | View 的 `Result.Result` 是对象还是字符串 | View 一条物料 | 类型 |
| Q10 | `IsSuccess` 是布尔还是字符串 | 任意写操作成功 / 失败各一次 | 类型 |

## P2 —— 写操作（测试账套，用完清理）

| # | 结论 | 怎么测 | 判定 |
| --- | --- | --- | --- |
| W1 | 物料最小必填集 | 只传 FCreateOrgId、FUseOrgId、FNumber、FName 调 Save | 成功，或记录要求补的字段 |
| W2 | SDK 示例的 `FUserOrgId` 拼写 | 用 `FUserOrgId` 保存 | 静默忽略 / 报错 / 生效 |
| W3 | `IsDeleteEntry` 默认 true 会删未传分录 | 建 3 行销售订单，Save 只带 1 行（不传 IsDeleteEntry） | 另 2 行是否被删；再测 false |
| W4 | Id=0 即新建、带内码即修改 | 同一 Model 分别带 0 与已有 FID | 行为 |
| W5 | 同编码重复新建 | 同 FNumber 两次 Save | 报重复 / 生成两条 |
| W6 | 布尔字符串与布尔值是否都认 | `"IsDeleteEntry": false` vs `"false"` | 等价与否 |
| W7 | 引用对象键名大小写 | `FBillTypeID` 用 `FNumber` 与 `FNUMBER` | 等价与否 |
| W8 | `Numbers` 数组 / `Ids` 字符串 | Submit 时 Ids 传数组 | 是否报错 |
| W9 | `ExcuteOperation` Forbid / Enable；opNumber 大小写 | `Forbid` vs `forbid` | 生效与否 |
| W10 | Push 默认规则与返回里的 `ConvertResponseStatus` | 采购订单下推采购入库（IsEnableDefaultRule=true） | 返回结构、下游单据状态 |
| W11 | Allocate 用内码 | 分配物料到第二组织 | 成功；目标组织是否需审核 |
| W12 | BatchSave 部分失败与 DIndex | 3 条中 1 条缺必填 | IsSuccess 整体值与 DIndex 对应关系 |
| W13 | BatchSaveQuery 异步轮询协议 | SDK `BatchSaveQuery` 50 条 | Status 流转 |

## P3 —— 凭证与财务

| # | 结论 | 怎么测 | 判定 |
| --- | --- | --- | --- |
| F1 | `FVOUCHERGROUPNO` / `FDocumentStatus` 留空能否保存 | 最小凭证 Save | 自动编号 / 报必填 |
| F2 | 借贷不平衡是否拒绝 | 借 100 贷 90 | 报错信息 |
| F3 | `FDETAILID__FFLEXn` 与核算维度映射 | 对挂客户维度的科目，View 一张现有凭证 | 记录映射 |
| F4 | 金额单位 | 保存 1200.00，界面核对 | 元 / 分 |
| F5 | 凭证有无过账 opNumber | ExcuteOperation 试 `Post`（预期失败） | 记录报错，确认「无过账接口」 |
| F6 | 应收单直接 Save 的最小必填集 | AR_receivable 最小 Model | 结果 |

## P4 —— 版本差异

- 用拿到的账号登录 `openapi.open.kingdee.com/ApiDoc`（新版 API 中心），核对 ExecuteBillQuery、Save 参数表是否比 2020 版（7.5.1800.6）有新增（如 BillQuery、分页字段），更新 reference。
- 下载官方资料包（`file.open.kingdee.com/WebAPI/金蝶云星空_新版WebAPI资料包.rar`，本次因需要下载许可未取）核对 .NET / Java SDK 的签名实现是否与 Python 一致。

## 验证后要改的地方

- 每条结论写回对应 reference，标「已用真实凭证验证（日期）」+ 响应片段；文档错误用 `<!-- Gap: … -->` 标注并升到 SKILL.md。
- 更新 SKILL.md「⚠ 验证状态」、site.json 的 `probed`、prompt.md 的版本一节。
- 跑 evals/evals.json 的对照实验，写 `comparison-report.md`（Markdown）。
