# 飞书 skill 验证计划（留给有凭证的人）

现状：文档版，抓取于 2026-09-11，只做了 20 次无凭证探测（见 `probe-log.md`）。本计划列出拿到凭证后要测的结论，
按优先级排序。**所需条件**：一个测试租户 + 一个企业自建应用（App ID / App Secret），开启机器人能力，
申请下表涉及的 API 权限并发布；一个测试群（含一个自定义机器人，开签名校验）；一个测试多维表格（把应用加为协作者）；
审批管理后台建一个只有「单行文本 + 日期 + 单选」控件的测试审批定义；飞书人事（企业版）如租户未开通则 P3 整组跳过并在 SKILL.md 注明。
所有调用均为免费 OpenAPI；飞书人事写接口会产生真实人员记录，**只在测试租户做并立即撤销入职**。

凭证只走环境变量（`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_BOT_WEBHOOK`、`FEISHU_BOT_SECRET`），测完全仓库
`grep -rn "<secret 前 8 位>"`；测试产生的群消息、多维表格记录、审批实例、待入职人员全部清理。

每条结论验证后按 create-doc-skill 格式写回 reference：`已用真实 API 验证（YYYY-MM）：做了什么 → 原始响应片段`；
与文档不符的加 `<!-- Gap: … -->` 并升到 SKILL.md。

## P0：先打通 SKILL.md「当前事实」

| # | 结论 | 怎么测 | 判定 |
|---|---|---|---|
| 0.1 | `tenant_access_token/internal` 成功返回顶层 `tenant_access_token` + `expire` | 真实 app_id/app_secret 调一次 | 字段名、层级、`expire ≤ 7200` |
| 0.2 | 剩余 ≥30 分钟时重取返回同一 token，<30 分钟返回新 token 且旧的仍可用 | 连续两次调用比对；再在最后 30 分钟内各调一次 | 与文档一致 / 不一致 |
| 0.3 | App Secret 错误时的 HTTP 状态与 code（10003？10014？10015？） | 故意改错 secret 一次 | 记录原文 |
| 0.4 | 缺 `Bearer ` 前缀 → 99991661（无凭证已证实），真 token 不带前缀是否一样 | 真 token 去掉前缀调 `GET /contact/v3/scopes` | |
| 0.5 | `user_id_type` 默认 `open_id` | `GET /contact/v3/users/find_by_department?department_id=0` 不带 user_id_type，看 items 的 ID 形态 | 返回 `ou_` 即成立 |
| 0.6 | 用 user_id 但不带 `user_id_type=user_id` 的真实报错 | `GET /contact/v3/users/<某 user_id>` | 记录 code——这是 SKILL.md 规则 5 的证据 |
| 0.7 | Lark 域名能否用飞书租户凭证换 token | 飞书凭证调 `open.larksuite.com/.../tenant_access_token/internal` | 记录结果，写入 auth.md 第 9 节 |

## P1：文档 ⚠ 与"直觉会写错"的点

| # | reference | 结论 / ⚠ | 怎么测 | 判定 |
|---|---|---|---|---|
| 1.1 | messaging-bots | 自定义机器人签名：`HMAC(key=ts\nsecret, msg=空)`；毫秒时间戳是否被拒 | 正确签名发 1 条；毫秒 ts 发 1 条 | 期望 0 / 19021 |
| 1.2 | messaging-bots | webhook `content` 传字符串（应用机器人写法）时的报错 | 1 次 | 期望 9499，记录原文 |
| 1.3 | messaging-bots | 应用机器人 `content` 传对象（webhook 写法）时的报错 | `POST /im/v1/messages` 1 次 | 期望 230001 或类似 |
| 1.4 | messaging-bots | `uuid` 1 小时去重：同 uuid 发两次的第二次响应 | 2 次 | 是否返回原 message_id / 报错 |
| 1.5 | messaging-bots | 接收消息事件重复推送时 `event_id` 是否不同而 `message_id` 相同（⚠ 去重键矛盾） | 让服务端故意超时 1 次触发重推 | 比较两次推送的 event_id |
| 1.6 | events-callbacks | Webhook 验签公式、解密（key=SHA256(EncryptKey)，IV=前 16 字节） | 用 events-callbacks.md 第 10 节接收器保存地址 + 收一条消息 | challenge 通过、验签通过 |
| 1.7 | events-callbacks | 签名时间戳容忍窗口（⚠ 未说明） | 无法主动构造，记录真实请求头时间戳与服务器时间差 | 仅记录 |
| 1.8 | auth | PKCE：授权阶段带 `code_challenge`，分别用 v3 和 v2 端点换 token（⚠ 矛盾） | 浏览器走一次授权 ×2 | 哪个端点成功 |
| 1.9 | auth | v3 令牌端点 JSON 与表单两种编码成功路径是否一致 | 各 1 次 | |
| 1.10 | auth | refresh_token 一次性：同一 refresh_token 刷两次 | 2 次 | 第二次 20064 / 20073 |
| 1.11 | bitable | 关联字段写入：数组 vs `{"link_record_ids": [...]}`（⚠ 两页写法不同） | 各写 1 条 | 哪种成功、另一种报什么 |
| 1.12 | bitable | 文本字段写入字符串、读出对象列表 | 写 1 条再 search | 结构对照 |
| 1.13 | bitable | 单选写入不存在的选项是否静默新建 | 1 次 | 查字段 property |
| 1.14 | bitable | 日期筛选 `ExactDate` 是否按天生效 | 构造同日不同时刻两条记录 | |
| 1.15 | bitable | 未加协作者时 tenant token 访问的报错（HTTP 403 / 400？code？） | 新建一个未授权表格 search 1 次 | 记录原文 |
| 1.16 | bitable | batch_get 的 `user_id_type` 默认值、`record_ids` 上限（⚠ 未说明） | 不传 user_id_type；传 101 个 ID | |
| 1.17 | bitable | 记录数上限 20,000 与"无额外限制"（⚠ 矛盾） | 仅在有大表时核对，**不要为此造 2 万条** | 可跳过并注明 |
| 1.18 | approval | 必填控件漏传是否真的不报错（FAQ 原文） | 创建实例时省略必填控件 1 次 | |
| 1.19 | approval | 日期控件传毫秒时间戳（而非 RFC3339）的报错 | 1 次 | 期望 1390001 |
| 1.20 | approval | 单选传选项文字（而非 value）的报错 | 1 次 | |
| 1.21 | approval | 上传文件 `www.feishu.cn/approval/openapi/v2/file/upload` 响应字段（⚠ 未抓全） | 传 1 个小附件 | 记录响应 |
| 1.22 | approval | 转交接口的目标人字段名（⚠ 未抓取） | 读文档页后调 1 次 | |
| 1.23 | approval | 未调 subscribe 时是否收不到实例事件；调后收到 v1.0 结构 | 创建 1 个实例前后各看一次 | |
| 1.24 | approval | `REVERTED` 事件 `operate_time` 为 int64 | 通过后撤销 1 次 | |
| 1.25 | approval | 批量取实例 ID 时间窗 >10 小时的行为 | 1 次 | 报错 / 截断 |

## P2：分页、频控、错误形态

| # | 结论 | 怎么测 |
|---|---|---|
| 2.1 | 通讯录 `page_size=51` 的报错（文档 40009 / 40011） | 1 次 |
| 2.2 | 多维表格 search `page_size=501` 的报错 | 1 次 |
| 2.3 | 限流响应是 429 还是 400、`x-ogw-ratelimit-*` 头是否存在 | **不做压测**；只在正常调用中留意，偶遇时记录 |
| 2.4 | 业务错误的 HTTP 状态（多维表格 1254xxx 文档标 200） | 故意传错 field_name 1 次 |
| 2.5 | 带真 token 请求不存在路径是否仍是纯文本 404（Gap 复核） | 1 次 |

## P3：飞书人事（企业版，需租户已开通）

| # | 结论 | 怎么测 |
|---|---|---|
| 3.1 | 只有 API 权限、没有「员工资源」数据权限时 search 的表现（⚠ 未说明） | 1 次 |
| 3.2 | `fields` 为空时只返回 `employment_id` | 1 次 |
| 3.3 | `GET /corehr/v1/job_datas` 默认 `user_id_type=people_corehr_id`、`page_size` 为字符串且必填、上限（⚠） | 3 次以内 |
| 3.4 | 创建待入职 → 2 秒内 query 查不到 → 完成入职 → `corehr.job_data.employed_v1` 事件 → search 5 分钟后可见 | 1 条测试人员，**完成后立即撤销 / 删除** |

## P4：对照实验（第 4 步）

凭证到位且 P0–P1 写回后，用 `feishu/evals/evals.json` 的 3 个场景跑 with / without skill 对照，
报告写 `feishu-workspace/comparison-report.md`（Markdown，按 CLAUDE.md 约定），打分依据真实调用结果。
