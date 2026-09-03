# Resend skill · 真实 API 验证计划

状态：**尚未执行**（本轮没有 API key）。拿到 key 后按下面顺序跑，每项验证完立刻把结论回写到对应 reference（格式：`**已用真实 API 验证（YYYY-MM）**：做了什么 → 原始响应片段`），文档本身错了的条目升到 SKILL.md "跨领域通用规则"。

## 前置
- 环境变量 `RESEND_API_KEY`（full_access）；**只作为环境变量传给命令，不写进任何文件**。跑完 `grep -rn "re_" <skill-dir>` 确认无泄漏。
- 一个已验证域名最好有（否则只能测 `onboarding@resend.dev` → 自己邮箱的路径，且第 2 组大部分测不了）。
- 收件地址全部用 `delivered@` / `bounced@` / `complained@` / `suppressed@resend.dev`，避免伤害域名信誉。
- 免费计划有日配额（100 封/天，⚠ 数字待在 Settings→Usage 核对），全计划预计消耗 < 40 封。
- 测试创建的 webhook / template / contact / segment / api key 用完全部删除；在 `verification-log.md` 记日期、endpoint、请求要点、结果、花费。

## 优先级 P0：全盘皆错型（只读、零成本先跑）

| # | 要验证的结论 | 怎么测 | 判定 |
|---|---|---|---|
| 0.1 | 鉴权 `Authorization: Bearer` + `User-Agent` 缺一不可 | `GET /domains` 三次：正常；去掉 `User-Agent`；`Authorization` 不带 `Bearer` 前缀 | 期望：200 / 403(1010，看是否为 Cloudflare HTML 而非 JSON) / 401 `missing_api_key`。记下缺 UA 时响应体到底长什么样 |
| 0.2 | 错误体结构 `{statusCode, name, message}` | `GET /emails/not-a-uuid` | 期望 422 `invalid_parameter`；确认字段名 |
| 0.3 | `validation_error` 是 400 还是 422（⚠ errors 页 vs pagination 页矛盾） | `GET /contacts?limit=500`；`GET /contacts?after=x&before=y` | 记录各自 statusCode |
| 0.4 | 分页：`has_more` / cursor 语义；老接口不传 limit 返回全部 | `GET /api-keys`（无 limit） vs `GET /emails`（无 limit） | 老接口无 `has_more`？新接口默认 20？ |
| 0.5 | `sending_access` key 调其他接口是 401 还是 403 `restricted_api_key` | 创建一个 sending key，用它 `GET /domains` | 记录 status + name |

## 优先级 P1：发送核心（每项 1–3 封）

| # | 要验证的结论 | 怎么测 | 判定 |
|---|---|---|---|
| 1.1 | **Node SDK 里 `idempotencyKey` 的位置**（⚠ 文档自相矛盾：第一个参数 vs 第二个 options 参数） | 同一 key 连发两次，分别用两种写法；再看第二次是否返回同一个 `id` | 哪种写法真正生效（返回相同 id 且只发一封）；另一种是被静默忽略还是报错 |
| 1.2 | 幂等冲突：同 key 不同 body → 409 `invalid_idempotent_request`；key 长度 257 → 400 `invalid_idempotency_key` | 直接 fetch 带 `Idempotency-Key` header | 记录原始响应 |
| 1.3 | **SDK 传 snake_case（`reply_to`、`scheduled_at`）是静默忽略还是报错** | `resend.emails.send({..., reply_to: 'x'} as any)`，然后 `GET /emails/{id}` 看 `reply_to` 字段 | 静默失效最危险，必须写进 SKILL.md 规则 2 |
| 1.4 | `POST /emails` 成功状态码是 200 还是 201（⚠ OpenAPI vs 页面） | curl `-i` | 记录 |
| 1.5 | 省略 `html`/`text`/`template` 全部三者是否报错；同时给 `html` 和 `template` 是否报错 | 两次请求 | 期望 422 `missing_required_field` / 互斥错误；记录 message |
| 1.6 | `text` 省略时是否自动从 `html` 生成（Node 页说会） | 发一封只有 html 的，`GET /emails/{id}` 看 `text` | — |
| 1.7 | `to` 第 51 个地址；`tags.name` 含空格/中文 | 各一次 | 期望 422，记录 message |
| 1.8 | `scheduled_at` 自然语言（"in 1 hour"）在 REST 上是否也接受；上限是否 30 天 | REST 发 `"scheduled_at":"in 1 hour"`、`"+31 days"` | 记录；随后 `POST /emails/{id}/cancel` 清理 |
| 1.9 | `PATCH /emails/{id}` / `cancel` 对已发送（非 scheduled）邮件返回什么 | 对 1.6 的邮件调 cancel | 记录 status/name |

## 优先级 P2：批量（⚠ 文档自相矛盾，最高价值）

| # | 要验证的结论 | 怎么测 | 判定 |
|---|---|---|---|
| 2.1 | **batch 元素带 `attachments` 是报错、静默丢弃、还是实际能发**（OpenAPI 有该字段，ai-onboarding 说不支持） | 2 封的 batch，其中一封带 1KB 文本附件 | `GET /emails/{id}/attachments` 看附件是否存在 |
| 2.2 | batch 元素带 `scheduled_at` 同上 | 同上 | `GET /emails/{id}` 看 `scheduled_at` |
| 2.3 | 原子性：第 2 封缺 `subject` 时第 1 封是否也不发 | 2 封 batch | 期望整批 422；确认第 1 封没有 id |
| 2.4 | 101 封 → 报错类型 | 构造 101 封（都发 delivered@resend.dev；若配额紧张跳过并标注） | 记录 |
| 2.5 | batch 的 `Idempotency-Key` 生效 | 同 key 两次 | 第二次返回相同 id 列表 |

## 优先级 P3：域名 / key（只读为主，创建后即删）

| # | 要验证的结论 | 怎么测 | 判定 |
|---|---|---|---|
| 3.1 | `POST /domains` 响应 `records[]` 字段名（record/name/type/value/ttl/priority/status？）与 `region` 枚举/默认值 | 创建 `test-<rand>.example.com` 后 `DELETE` | 记录完整响应 |
| 3.2 | `POST /domains/{id}/verify` 返回什么；`status` 枚举实际取值 | verify 一个 DNS 未配置的域名，再 `GET` | 期望 `pending`/`failed`…记录 |
| 3.3 | `POST /api-keys` 响应字段（`token` 只在创建时返回？）；`permission` 拼写；`domain_id` 配 `full_access` 是否报错 | 创建后 `GET /api-keys` 看是否再有 token；删除 | 记录 |
| 3.4 | 未验证域名的 `from` → 403 message 原文 | 用 `nobody@unverified-example.com` 发 | 记录 |

## 优先级 P4：Webhook（需要一个公网 URL，可用 Resend CLI 的本地 webhook 或 requestbin）

| # | 要验证的结论 | 怎么测 | 判定 |
|---|---|---|---|
| 4.1 | `POST /webhooks` 的 `events[]` 拼写（`email.bounced` 等）；不合法值报错 | 创建含一个错拼事件的 webhook | 期望 422，记录合法列表（若 message 列出） |
| 4.2 | 签名 header 名（`svix-*` 还是 `resend-*`）与 secret 格式；`svix` 包 `Webhook.verify` 通过 | 发一封到 `bounced@resend.dev`，捕获请求 | 用 raw body 验证通过；用 JSON.stringify(parsed) 验证失败 |
| 4.3 | `email.bounced` payload：`data.to` 是数组？`data.bounce` 子对象字段 | 同上 | 记录完整 payload |
| 4.4 | `GET /webhooks/{id}/events` 与 `/attempts` 响应结构 | 只读 | 记录 |

## 优先级 P5：营销对象模型（免费计划可能受限，能测多少测多少）

| # | 要验证的结论 | 怎么测 | 判定 |
|---|---|---|---|
| 5.1 | Audiences 是否仍可用 / 是否 deprecated；`POST /contacts` 是否还需要 audience_id | 直接 `POST /contacts {email}` | 记录 |
| 5.2 | `GET /contacts/{id}` 传 email 代替 uuid 是否可行 | 一次 | 记录 |
| 5.3 | `POST /broadcasts` 最小必填集（segment_id? audience_id?）；创建后不 send 是否 draft | 创建后 `DELETE` | 记录 |
| 5.4 | `POST /templates` 未 publish 时用于 `POST /emails` 是否报错；variables 缺失是 fallback 还是报错 | 创建→发送→publish→发送→删除 | 记录 |
| 5.5 | `POST /events/send` body 结构与 identifier 语义 | 一次 | 记录 |

## 优先级 P6：子 Agent 撰写时发现的文档自相矛盾（各 1 次请求即可判定）

| # | 矛盾点（两份来源各说什么） | 怎么测 | 判定 |
|---|---|---|---|
| 6.1 | 域名 `status` 枚举：OpenAPI 6 个值，`dashboard/domains/manage-domains` 页多出 `temporary_failure` | 对 DNS 未配置域名 verify 后轮询 `GET /domains/{id}` 数次 | 记录出现过的全部 status 值 |
| 6.2 | `custom_return_path` 能否通过 `PATCH /domains/{id}` 修改：dashboard 页说可以，OpenAPI/update 页未列 | PATCH 一次 | 200 且生效 / 字段被忽略 / 4xx |
| 6.3 | 联系人 CSV 导入上限：OpenAPI 50MB vs 页面 200MB；`on_conflict` 默认值：OpenAPI `skip` vs 页面 `upsert` | 导入 2 行 CSV（其中 1 行已存在），**不传** `on_conflict`，看 `counts.updated/skipped` | 记录默认行为；大小上限可跳过并标注 |
| 6.4 | 模板 `variables[].type` 枚举：页面 `string|number` vs OpenAPI 加 `boolean|object|list` | `POST /templates` 建一个 `boolean` 变量 | 201 / 422 |
| 6.5 | 模板发送时缺变量且无 fallback：页面说整封拒绝并返回 validation error（`name` 未说明） | 用缺变量的 `template.variables` 调 `POST /emails` | 记录 statusCode / name / message |
| 6.6 | `POST /events/send` 用未注册联系人的 `email`：页面说会在 run 开始时自动创建联系人 | 发一个事件后 `GET /contacts/{email}` | 是否被创建 |
| 6.7 | Contact 全局 `unsubscribed: true` 是否也拦截 `POST /emails` 事务邮件（文档未说明） | 对一个 unsubscribed 的测试联系人地址（`delivered+unsub@resend.dev`）单发一封 | `last_event` 是 delivered 还是 suppressed/failed |
| 6.8 | Broadcast 合并变量：材料里只有 `{{{contact.first_name|fb}}}` 形式，大写 `{{{FIRST_NAME}}}` 不存在；自定义 property 占位符语法未说明 | 建一个 draft broadcast，`GET` 回来看 html 是否原样保存；如可发到测试地址则看渲染结果 | 记录被渲染 / 原样输出的写法 |
| 6.9 | `POST /broadcasts/{id}/send` 仅对 API 创建的 broadcast 有效（页面说法） | 对 dashboard 创建的 draft 调 send | 记录报错 |
| 6.10 | Webhook 重试计划：三处文档不一致（8 次含"立即" / 6 个间隔 / "最长 24 小时"） | 建一个指向永远 500 的 endpoint 的 webhook，发一封到 `delivered@resend.dev`，用 `GET /webhooks/{id}/events/{event_id}/attempts` 看时间戳 | 记录实际次数与间隔；测完删除 webhook |
| 6.11 | `GET /webhooks`（列表）响应是否含 `signing_secret`（文档自相矛盾） | 只读一次 | 记录 |
| 6.12 | `data.tags` 在 webhook payload 里是对象还是数组；`PATCH /webhooks` 的 `events` 是整组替换还是追加 | 发带 2 个 tag 的邮件看 payload；PATCH 只传 1 个事件后 GET | 记录 |

## 验证后要更新的地方
- 每个 reference 顶部的"⚠ 验证状态"段改为分区说明（哪些已验证、日期、花费）。
- SKILL.md "验证状态"一节；规则 2/4/5 根据 1.3、1.1、2.1–2.2 的结果改写。
- 把 ⚠ 项的结论写进 `evals/evals.json` 对应场景的 expectations，第 4 步的打分才有实测依据。
