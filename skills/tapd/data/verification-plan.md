# TAPD skill 验证计划（拿到真实凭证后执行）

前提：一个 **专用测试项目**（`TAPD_WORKSPACE_ID`）。文档里没有删除需求 / 缺陷 / 任务本身的接口，写操作会在项目里留下数据，不要在生产项目里测。
凭证只放环境变量：`TAPD_API_USER` / `TAPD_API_PASSWORD`；开放应用另需 `TAPD_CLIENT_ID` / `TAPD_CLIENT_SECRET`。验证完 `grep -rn` 仓库确认没有泄漏。
每条结论验证后回写对应 reference：「已用真实凭证验证（日期）：…」+ 响应片段；与文档不符的加 `<!-- Gap: … -->` 并升到 SKILL.md。

## P0：鉴权与响应形状（只读，零成本）
| # | 要验证的结论 | 调用 | 判定 |
|---|---|---|---|
| 1 | Basic API 账号可用；testauth 响应是否真的回显口令 | `GET /quickstart/testauth` | `status==1`；看 `data` 字段（**不要把输出贴进任何文件**） |
| 2 | 带真实凭证时拼错路径是否仍返回 Hello world | `GET /storys?workspace_id=$WS`、`GET /stories/not_a_real_action?workspace_id=$WS` | 记录 HTTP 与 body |
| 3 | `X-RateLimit-Limit` 带凭证时的值与窗口 | 连续 5 次 `GET /stories/count` 看头 | 记录 Limit / Remaining 变化 |
| 4 | client_credentials 换 token；过期 / 伪造 token 的状态码（422 还是 401） | `POST /tokens/request_token` → `GET /bugs/count` 带 token；再带改坏一位的 token | 记录状态行与 info |
| 5 | token 放 query `access_token=` 是否可用 | `GET /workspaces/get_workitems_long_id_by_short_ids?...&access_token=` | 是否 200 |
| 6 | 应用 Basic（client_id:client_secret）与 Bearer 权限是否一致 | 同一接口两种方式 | 对比 |

## P1：查询语法与分页（只读）
| # | 结论 | 调用 | 判定 |
|---|---|---|---|
| 7 | 时间查询 `modified=>…`、`~` 区间、到秒精度 | `GET /bugs?workspace_id=&modified=>2026-09-01 00:00:00` | 结果都在范围内 |
| 8 | `limit=500` 时实际返回条数（截断到 200 还是报错） | `GET /stories?limit=500` | 记录 |
| 9 | `page*limit>20000` 的错误码 / 文案 | `GET /stories?limit=200&page=101` | 记录 |
| 10 | `cursor` 在 `/stories`、`/bugs`、`/tasks`、`/timesheets` 是否都支持；是否包含边界记录；与 `order=id asc` 组合 | 各取两页比 id | 记录 |
| 11 | 用错字段名（`/bugs?name=xxx`）是报错还是被静默忽略 | 对比 `/bugs/count?name=xxx` 与 `/bugs/count` | 数量相同即静默忽略（高价值） |
| 12 | `name` 默认模糊、`EQ<…>` 精确 | `/iterations?name=W3` vs `name=EQ<2026-W38>` | |
| 13 | 时间字段时区 | 创建一条后比对 `created` 与本地时间 | |
| 14 | `children_id` 查空传半角 `|` 还是全角 `丨` | 两种各查一次 | |

## P2：写操作（测试项目内，留痕）
| # | 结论 | 调用 | 判定 |
|---|---|---|---|
| 15 | 创建需求能否直接带 `status`；未知字段是否报错 | `POST /stories` | |
| 16 | JSON body 不带 Content-Type 时的行为 | `POST /stories` 发 JSON 不带头 | 报错还是字段丢失（静默失效最危险） |
| 17 | 需求 `priority_label=High` 写入与 `priority` 回读 | `POST /stories` | |
| 18 | 缺陷流转缺必填附加字段时的报错 | `POST /bugs status=resolved` 不带 resolution | 记录 info |
| 19 | 人员字段写 `zhangsan` 与 `zhangsan;` 是否等价；多处理人分隔符 | `POST /tasks owner=…` | |
| 20 | 工时唯一约束的报错；`timespent` 单位 | 同 entity/date/owner 连建两条 | 记录 info |
| 21 | `delete_timesheets` 部分失败时外层 status | 删一个存在 + 一个不存在的 cost_id | 外层 status 与 `data.data.failed` |
| 22 | `update_iteration` 不带 `id` 的行为（新建？报错？） | `POST /iterations` 带 current_user 不带 id | |
| 23 | `tcases/batch_save` 不带 JSON Content-Type 是否可用 | 照文档 curl 示例 | |
| 24 | `tcase_instance/execute` 不传 `last_executor`；批量 tcase_id 传法 | | |
| 25 | `/story_changes` limit=200 时的行为（文档写最大 100） | | |

清理：测试产生的工时用 `delete_timesheets` 删除；需求 / 缺陷 / 任务无删除 API，在 UI 里手动删除或整体归档测试项目。

## P3：Webhook（需要可公网访问的接收端）
| # | 结论 | 做法 |
|---|---|---|
| 26 | 实际报文格式（form / json）、`id` / `event_id` 类型、是否有签名头 | 配置事件订阅，改一个缺陷状态，记录完整请求头与 body |
| 27 | 状态变更事件名：`bug::status_change` 还是 `bug::update` + change_fields | 同上 |
| 28 | 失败重试次数、超时、间隔 | 接收端先返回 500 观察重投 |
| 29 | 任务状态变更事件名；前后置绑定事件名 | |
| 30 | 「事件映射」页的正确地址 | 在开发者后台事件订阅界面找事件清单 |

## 需要资料包 / 内网才能确认的点（本次按规矩未下载）
- Python SDK `tapd-python-sdk` 只在 `mirrors.tencent.com` 私有源，方法签名、重试行为未核实。
- Node SDK `@opentapd/tapd-node-sdk@1.68.0`（公共 npm 存在）的方法名与参数校验未核实；`@tencent/tapd-node-sdk` 公共 npm 不存在。
- 文档中 `tapd.woa.com` / `o.tapd.woa.com` 内网地址对应的外网地址（OAuth 跳转模式）。
