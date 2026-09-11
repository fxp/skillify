# 法大大（FASC OpenAPI 5.1）skill 验证计划

skill 目前是**文档版**（抓取于 2026-09-11，只做了无凭证探测）。拿到 UAT 的 AppId / AppSecret 后，按下面的优先级补测，
每条结论写回对应 reference，格式：`**已用真实 API 验证（YYYY-MM-DD）**：做了什么 → 原始响应片段`。
Key 只走环境变量（`FASC_APP_ID`、`FASC_APP_SECRET`），测完全仓库 grep 一遍；测试创建的签署任务用完撤销 / 删除。

优先在 **UAT**（`https://uat-api.fadada.com/api/v5`）上测。⚠ UAT 是否消耗签署用量文档未说明（`211058 签署任务数可用量不足`），先确认。

## P0 —— 鉴权与签名（错了全盘皆错）

| # | 要验证的结论 | 怎么测 | 判定 | 影响文件 |
| --- | --- | --- | --- | --- |
| 1 | 两步派生签名算法正确 | 用 `fasc_client.py` 调 `/service/get-access-token` | 返回 `100000` + accessToken | auth-and-signing.md §4–§6 |
| 2 | 一步 HMAC（按文档正文字面理解）会失败 | 改成 `HMAC(AppSecret, 拼接串)` 再调 | 预期 `100003`；若也成功则文档正文没错，改 ⚠ | auth-and-signing.md §4 |
| 3 | 待签名串里的值**不**做百分号编码 | bizContent 含中文 / 空格 / `&`，分别用原文和编码后的值签名 | 只有原文通过 | auth-and-signing.md §4 |
| 4 | `expiresIn` 类型、有效期内重复换 token 返回同一 token | 连续换两次 | 比较 token 与 `expiresIn` | auth-and-signing.md §5 |
| 5 | 成功响应里 `success` 字段是否存在、取值 | 看换 token 成功响应 | 记录原文 | auth-and-signing.md §9 |
| 6 | 缺 `X-FASC-Api-SubVersion`、Nonce 重复、Nonce 超 32 位 | 各调一次 | 记录 code（关注 `100009` 的触发条件） | errors-and-limits.md §3 |
| 7 | 签名错误返回 `100003` 且 HTTP 状态 | 故意改错一位签名 | 记录 | errors-and-limits.md §3 |

## P1 —— 签署任务主流程

| # | 要验证的结论 | 怎么测 | 判定 | 影响文件 |
| --- | --- | --- | --- | --- |
| 8 | 新旧两个详情路径现状 | 同一个 signTaskId 分别调 `/sign-task/get-detail`、`/sign-task/app/get-detail` | 两者是否都可用、响应差异（旧版是否带参与方链接） | sign-tasks.md §15、auth-and-signing.md §8 |
| 9 | 文件流程：PUT 的 Content-Type 要求 | `get-upload-url` 后分别用 `application/octet-stream` 和 `application/pdf` PUT | 记录哪个 200 | files.md §5 |
| 10 | 文件名扩展名不一致 → `211157` | `/file/process` 传错扩展名 | 记录 code | files.md §7 |
| 11 | `autoStart` 默认 false | 不传 autoStart 创建，再查详情 | 状态 `task_created` | sign-tasks.md §4 |
| 12 | `autoStart=true` 缺签署方时的报错 | 只带 docs 不带 actors | 记录 code（预期 211146 / 211161） | sign-tasks.md §4 |
| 13 | 布尔传字符串 `"true"` 是否被接受 | `autoStart: "true"` | 成功 / 报错 / 静默忽略 | sign-tasks.md §4 |
| 14 | 发起方不在 actors 里时能否签 | 发起方未加入 actors，提交后查参与方 | 发起方无签署入口 | SKILL.md 规则 4 |
| 15 | `sendNotification` 默认值下签署方是否收到待签短信 | 用测试手机号作为 accountName，不传 notifyType | 是否收到短信 | sign-tasks.md §5 |
| 16 | 对 `task_created` 调 cancel → `211126`；delete 成功 | 依次调用 | 记录 | sign-tasks.md §14 |
| 17 | `/sign-task/actor/get-url` 在提交前调用的结果 | 未提交任务取链接 | 记录 | sign-tasks.md §11 |
| 18 | 个人参与方传 `certNoForMatch` 是否触发 `211132` | 非应用用户个人参与方带证件号创建 | 记录触发条件 | sign-tasks.md §5 |
| 19 | 下载：`downloadMode` 默认 preview 时服务端 GET 得到什么；单文档是否 zip | 完成一个任务后下载 | 记录 Content-Type | sign-tasks.md §17 |

## P1 —— 回调

| # | 要验证的结论 | 怎么测 | 判定 | 影响文件 |
| --- | --- | --- | --- | --- |
| 20 | 回调验签参数集合与算法 | 配置回调地址，完成一次签署，用 callbacks.md §5 验签 | 验签通过 | callbacks.md §4 |
| 21 | 重试是否复用原时间戳 / nonce | 故意返回 500，记录 3m、30m 两次重试的头 | 比较 Timestamp、Nonce | callbacks.md §4 |
| 22 | `sign-task-pending` 的 `signtaskId` 大小写、成员事件 `actorIInfo` 拼写 | 触发对应事件 | 记录字段名原文 | callbacks.md §7 |

## P2 —— 授权与模板

| # | 要验证的结论 | 怎么测 | 判定 | 影响文件 |
| --- | --- | --- | --- | --- |
| 23 | 授权重定向验签：空值是否参与签名 | 让测试用户完成一次个人授权，拿重定向 query 两种方式各算一次 | 哪种通过 | identity-authorization.md §7 |
| 24 | `/user/get` 未授权时的 `bindingStatus` / `identStatus` 取值 | 查一个未授权 clientUserId | 记录 | identity-authorization.md §8 |
| 25 | `redirectUrl` 编码次数 | 分别传编码一次 / 不编码 | 跳转是否正确 | identity-authorization.md §5 |
| 26 | 模板发起时省略 `actorType` / `permissions` 是否报错 | create-with-template 不传这两个字段 | 记录 | templates.md §7 |
| 27 | `fill-values` 响应键名是否带空格 | 调一次 | 记录原文 | templates.md §9 |

## P2 —— 错误码与限流

| # | 要验证的结论 | 怎么测 | 判定 | 影响文件 |
| --- | --- | --- | --- | --- |
| 28 | 缺 token 但其他头齐全时的 code | 不带 AccessToken 调业务接口 | 记录 | errors-and-limits.md §3 |
| 29 | 20 QPS 限流返回 `100004` 且 HTTP 403 | 仅在确认不影响账号时，对只读接口短时超频 | 记录（可跳过） | errors-and-limits.md §9 |

## 对照实验（第 4 步）

真实凭证到位、上述 P0/P1 验证完成后，用 `fadada/evals/evals.json` 的 3 个场景跑 with / without skill 对照，
打分依据第 3 步的真实调用结果，报告写 `fadada-workspace/comparison-report.md`（Markdown）。
