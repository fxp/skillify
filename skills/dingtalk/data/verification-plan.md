# dingtalk skill 验证计划（拿到真实凭证后执行）

现状：文档版，2026-09-11 抓取，只做了无凭证探测（probe-log.md，P1–P14）。以下按优先级列出要用真实凭证确认的结论。
所需凭证：一个测试企业的**企业内部应用**（AppKey/AppSecret、AgentId，已开通通讯录读、工作通知、机器人发消息、审批读写、考勤读权限）、
一个测试群的自定义机器人 Webhook（开加签）、一个测试审批模板。凭证只走环境变量，结束后全仓 grep 前 8 位确认未泄漏。
成本：以下全部是免费接口；会产生的副作用只有给测试员工发消息 / 发起并撤销测试审批单，用完撤回 / 撤销。

## P0 —— 影响 SKILL.md 规则层的结论

| # | 结论 / ⚠ | 怎么测 | 判定 | 影响文件 |
| --- | --- | --- | --- | --- |
| 1 | topapi 接口接受 JSON body（文档 curl 全是表单） | `POST /topapi/v2/user/get?access_token=` 分别用 `json=` 和 `data=` 各调一次 | 两者都 errcode 0 → 保留 JSON 示例；JSON 报 40035 → 全部改表单 | contacts / messaging / attendance |
| 2 | 新版 accessToken 能否直接当旧版 access_token 用，反之 | 用 `/v1.0/oauth2/accessToken` 拿的 token 调 `topapi/v2/user/get`；用 `gettoken` 的 token 调 `GET /v1.0/contact/users/search` | 记录是否通用 | auth / SKILL 当前事实 |
| 3 | 旧版 token 过期时的返回是否也包在 88 里（`sub_code` 42001？） | 用一个 >2 小时前取的 token 调 topapi | 记录 errcode / sub_code | errors-and-limits |
| 4 | 工作通知静默丢弃：同内容同人一天第二条 errcode=0 但 `forbidden_user_id_list` 有人 | 对同一测试员工连发两条内容相同的 text 通知，再调 getsendresult | 第二条出现在 forbidden 列表 / forbidden_list code 143106 | messaging / SKILL #3 |
| 5 | HTTP 回调：URL 上实际参数名（`signature` 还是 `msg_signature`；`timestamp` 还是 `timeStamp`） | 后台配置 HTTP 推送指向可记录请求的地址，点"验证有效性" | 记录真实参数名，更新 events.md | events |
| 6 | HTTP 回调 ownerKey：后台配置的事件是否用 AppKey | 同上，分别用 AppKey / CorpId 解密 | 哪个不报 owner mismatch | events / SKILL #4 |

## P1 —— 文档自相矛盾，需要真实返回来裁决

| # | ⚠ | 怎么测 | 影响文件 |
| --- | --- | --- | --- |
| 7 | 审批 `deptId` 根部门填 -1 还是 1 | 不传 approvers 发起测试审批，分别 -1 / 1 | oa-approval |
| 8 | 撤销 `isSystem` 省略是否报错；发起后 15 秒内撤销的错误码 | 发起后立刻撤销一次，16 秒后省略 isSystem 再撤销 | oa-approval |
| 9 | `oToMessages/batchSend` 的 userIds 上限 20 还是 100 | 传 21 个 userid（可含无效 id） | messaging |
| 10 | `/attendance/list` 的 `limit=100` 是否被拒 | limit 分别 50 / 100 | attendance |
| 11 | `/attendance/listRecord` 只传日期（无时分秒）是否可用 | `checkDateFrom=2026-09-01` | attendance |
| 12 | `getsendprogress` 能否查 24 小时以前的 task | 用 >24h 的 task_id | messaging |
| 13 | `/topapi/v2/user/list` 的 `size` 上限；`listid` 大部门是否截断 | size=100 / 1000；在人数多的部门比对 | contacts |
| 14 | `/topapi/v2/user/get` 是否支持 GET（「基础概念」页写 GET） | GET 带 query userid | auth |
| 15 | 响应里 errcode / 布尔是否真是字符串（示例写 "0"、"true"） | 看任意 topapi 真实响应类型 | contacts |
| 16 | 自定义机器人 token 错误码：300005 vs 400101；加签错误的 errmsg | 伪造 sign 调一次真实 webhook | messaging |

## P2 —— 文档未说明、本次未转录

| # | 项 | 怎么测 |
| --- | --- | --- |
| 17 | `createAndDeliver` 响应结构；卡片 Stream 回调的请求 / 应答格式 | 用测试卡片模板投放到测试群并点按钮 |
| 18 | AI 卡片 `isFull=false` 对 markdown 变量的实际表现 | 流式推 3 帧 |
| 19 | Python `dingtalk-stream` 订阅通讯录 / 审批事件的 handler 写法 | 读 SDK 源码 + 实际订阅 `bpms_instance_change` |
| 20 | 审批事件 `type` 的全部取值（终止 / 删除） | 发起→撤销→删除测试审批，记录事件 |
| 21 | 通讯录事件在 Stream 通道下的 eventType 名称 | 测试企业里改一个员工信息 |
| 22 | corpAccessToken 是否必须 `suiteTicket`（参数表未列） | 需要第三方企业应用，可后置 |

## 执行规范

- 每条结论验证后改回对应 reference，写"已用真实凭证验证（日期）：…返回…"并附响应片段；和文档不符的加 `<!-- Gap: … -->`，
  并同步更新 SKILL.md「⚠ 汇总」与 `site.json`（gotchas / probed）。
- 记 `verification-log.md`：日期、endpoint、请求要点（去敏）、结果。
- 验证后跑一轮 evals（with / without skill 对照），报告写 `comparison-report.md`（Markdown）。
