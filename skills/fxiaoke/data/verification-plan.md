# fxiaoke skill 验证计划（待真实凭证）

现状：文档版，抓取于 2026-09-11，只做了无凭证探测（`probe-log.md`）。以下按优先级列出拿到凭证后要测的结论。
测试原则：凭证只走环境变量；创建类测试用明显的测试数据（名称带 `skill-verify-`），测完立即作废 + 删除；记录到 `verification-log.md`（日期、endpoint、请求要点、原始响应片段）。

需要的账号条件：企业已购买 OpenAPI 配额；自建应用已开启开发模式；测试机 IP 在白名单；一个 CRM 管理员员工 ID；一个普通员工 ID；一个测试用 `__c` 自定义对象。

## P0 —— SKILL.md「当前事实」，错了全盘皆错（只读，零成本）

| # | 结论 | 怎么测 | 判定 |
|---|---|---|---|
| 1 | 客户端凭证 `POST /oauth2.0/token` + `grantType=app_secret` 返回 `accessToken`、`ea`、`expiresIn` | 真实调用一次 | 记录 `expiresIn` 的真实值与语义（剩余秒数？）；`openUserId` 字段实际是什么 |
| 2 | header `authorization: Bearer` + `x-fs-ea` + `x-fs-userid`（员工 ID `1000` 形态）能调通 | `POST /cgi/crm/v2/object/list` | errorCode 0 |
| 3 | 缺 `thirdTraceId` 是否被拒 | 同 2，去掉 URL 参数 | 被拒则记录错误码；不拒则在 auth.md 改为「文档要求但实测不强制」 |
| 4 | 缺 `x-fs-userid` 的报错 | 同 2，去掉该 header | 记录错误码 / 文案 |
| 5 | 0–6600 秒内重复换 token 返回同一个 | 间隔 1 分钟调两次 | accessToken 相同 |
| 6 | 旧版 body 传参（`corpAccessToken`/`corpId`/`currentOpenUserId`）仍可用 | `/cgi/corpAccessToken/get/V2` + 旧版 body 调 object/list | errorCode 0 |

## P1 —— 文档自相矛盾（⚠）的裁决（只读优先）

| # | ⚠ | 怎么测 | 判定 |
|---|---|---|---|
| 7 | 列表响应是 `data.dataList` 还是单条 map | `data/query` AccountObj limit=5 | 更新 query-and-paging.md 第 7 节 |
| 8 | 总数参数 `returnTotalNum` / `find_explicit_total_num` / `need_return_count_num` 哪个生效 | 同一查询分别传三种，看 `total` | 保留生效的，其余标「无效」 |
| 9 | `limit=101` 的报错；`offset` 非 limit 整数倍的报错；`offset=10100` 是否回 10013 | 三次 query | 记录原文 |
| 10 | `_id GT` 深翻页可用 | 按 query-and-paging.md 第 9 节跑两页 | 第二页首条 `_id` > 第一页末条 |
| 11 | operator `HASANYOF` 与 `CONTAINS` 哪个可用；`N` 是否能查出空值 | 多选字段各试一次 | 更新 operator 表 |
| 12 | describe 的 `includeDetail` 放顶层还是 data 里 | 两种各调一次 SalesOrderObj 之类有从对象的对象 | 看是否返回从对象 |
| 13 | `__c` 对象发到 `/cgi/crm/v2/data/query`（预置路径）的报错；预置对象发到 custom 路径的报错 | 各一次 | 把报错写进 custom-objects.md 第 2 节 |
| 14 | 错误码表：appSecret 错、appId 错、permanentCode 错分别回什么 | 3 次换 token（仍用伪造值即可） | 补全 errors-and-limits.md 第 2 节 |

## P2 —— 写入类（创建测试数据，测完清理）

| # | 结论 | 怎么测 | 判定 |
|---|---|---|---|
| 15 | 预置对象 create：`dataObjectApiName` 放 `object_data` 内；`object_describe_api_name` 是否必填 | 创建一条 LeadsObj（带 / 不带该字段各一次） | 返回 `dataId` |
| 16 | 默认触发审批流 / 工作流 | 在有审批流的对象上不传开关创建 | 观察是否进审批 |
| 17 | 字段值类型：金额传数字而非字符串、日期传秒而非毫秒、单选传 label 会怎样（报错还是**静默存错**） | 各一次 | 静默失效的升到 SKILL.md 规则 |
| 18 | 自定义对象 create 的返回里新数据 id 在哪 | 创建一条 `__c` 数据 | 更新 custom-objects.md 第 3 节 |
| 19 | update 未传字段是否被清空 | 改一个字段后 get 对比 | 更新 crm-preset-objects.md 第 4 节 |
| 20 | 未作废直接 delete 的报错；invalid 传列表的报错 | 各一次 | 记录原文 |
| 21 | changeOwner `ownerId` 用 `["1005"]` 还是 `"[1005]"` | 两种各一次 | 保留可用写法 |
| 22 | 公海客户不 choose 直接 changeOwner 的报错；choose 后领取人是谁 | 需要一个公海 + 测试客户 | 记录报错与领取人 |
| 23 | `/cgi/message/send` 的 `toUser` 在新版传参下填员工 ID 还是 FSUID | 给测试员工发一条文本 | 收到即可 |
| 24 | 文件上传两步走 + 附件字段写 npath | 传 1 KB 文本文件到测试 `__c` 对象的附件字段 | 详情里能看到附件 |

## P3 —— 通讯录与限流（只读）

| # | 结论 | 怎么测 |
|---|---|---|
| 25 | `/cgi/user/list` 参数平铺顶层可用；`departmentId=999999` 是全公司 | 调一次 |
| 26 | 管理员身份查 PersonnelObj 是否为空（人员对象权限） | 调一次，对照 `/cgi/user/list` |
| 27 | 旧版 `/cgi/user/getByMobile`、`/cgi/user/get/batchByUpdTime` 是否仍可用、是否认新版 header | 各一次 |
| 28 | `/cgi/crm/v2/bi/lwt/query` 是否真是「按角色查用户」 | 用 roleGetRoleList 拿到的 roleCode 调一次 |
| 29 | 单接口 100 次 / 20 秒超限时的错误码（14001 还是 30004） | **不做压测**；如企业允许，只在测试企业里对 object/list 连发 110 次 |

## 完成后

- 每条结论改回对应 reference，写「已用真实凭证验证（日期）：… 返回 …」；文档错误加 `<!-- Gap: … -->` 并升到 SKILL.md 规则层。
- SKILL.md「⚠ 验证状态」改为「已验证 / 未验证」分区。
- 跑 evals/evals.json 的 with / without skill 对照，写 `comparison-report.md`（Markdown）。
- 全仓库 `grep` 凭证前 8 位，确认没有泄漏；测试数据已作废 + 删除。
