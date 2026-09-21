# Sentry skill 验证计划

写这份计划的时候手上没有真实 Sentry 账号 / API auth token / DSN。`/Users/chopinfeng/Workspace/Skillify/sentry/` 下的全部内容来自 `docs.sentry.io` 官方文档（抓取于 2026-09-21）和 `github.com/getsentry/sentry-api-schema` 的 `openapi-derefed.json`（同日抓取），**没有做任何真实调用**。这份文件按优先级列出拿到 key 之后要测什么、怎么测、预期成本、怎么判定——对应 `create-doc-skill` 第 3 步。

## 需要准备什么

- 一个 Sentry 组织（免费版即可）+ 至少一个已经在接收真实错误的项目（没有真实错误可以用下面 P0 里的方式手动触发几条）。
- 三种 token 各建一个：Organization Token、Internal Integration Token（自定义 scope）、Personal Token——用来验证 `auth-and-tokens.md` 里的权限差异断言。
- 一个测试用的项目 DSN（用于验证 ingestion vs Web API 的凭证隔离断言）。
- 如果要测 EU 区域相关断言，需要一个数据区域选了 EU 的组织（多数人手头的免费测试账号大概率是 US 区域，这条如果没有 EU 组织就只能标注"未验证"跳过，不要硬凑）。

## P0（最低成本、必须测——决定 skill 骨干断言是否成立）

| # | 要测的结论 | 用哪个 endpoint | 怎么判定 | 预期成本 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `GET /api/0/organizations/` 能列出组织，响应含 `links.regionUrl` | `GET /api/0/organizations/` | 检查响应字段名是否和 SKILL.md/organizations-and-projects.md 里写的一致 | 免费，1 次只读请求 |
| 2 | 不传 `query` 时 issue 列表隐式应用 `is:unresolved` | `GET /api/0/organizations/{org}/issues/` 分别传 `query=` 空串 和 完全不传 `query` | 对比两次返回的 issue 集合是否不同（不传应该只有未解决的，传空串应该含全部状态） | 免费 |
| 3 | `event_id` 支持字面量 `latest`/`oldest`/`recommended` | `GET /api/0/organizations/{org}/issues/{issue_id}/events/latest/` | 能不能成功拿到一条 event，和列表接口里手动取最新一条比对是否是同一条 | 免费 |
| 4 | `entries` 字段的真实结构（堆栈跟踪具体在哪一层） | 同上 latest event 详情 | 把完整响应存下来，找到 `type: "exception"` 或类似的条目，记录真实路径写回 `events.md` | 免费 |
| 5 | DSN 打 Web API 会被拒绝（验证"DSN 只写不读"） | 用 `Authorization: DSN {dsn}` 调 `GET /api/0/organizations/{org}/issues/` | 应该报 401/403，记录具体报错 body | 免费 |
| 6 | Auth token 塞进 SDK `dsn=` 参数会怎样 | Python `sentry_sdk.init(dsn="Bearer的那个token字符串")` 之后 `capture_message` | 观察 SDK 是否报错/静默丢弃/Sentry 后台是否收到，记录哪种情况 | 免费（不产生真实计费事件太多） |

## P1（低成本，覆盖主要 CRUD 行为）

| # | 要测的结论 | 用哪个 endpoint | 怎么判定 | 预期成本 |
| :--- | :--- | :--- | :--- | :--- |
| 7 | `PUT .../issues/{issue_id}/` 单个 resolve/assign 按文档字段能跑通 | `PUT /api/0/organizations/{org}/issues/{issue_id}/`，body `{"status":"resolved"}`、再 `{"assignedTo":"<email>"}` | 状态确实变化，响应字段和文档一致 | 免费 |
| 8 | 批量 `PUT .../issues/`（不传 `id`，只按 `query` 过滤）确实隐式"更新全部匹配" | 先造 2-3 个测试 issue，批量 PUT `query=is:unresolved&project=<test-project>` | 全部匹配的 issue 状态都变了，且没传 `id` 时不报错 | 免费（如果测试项目本来就没什么真实用户在看） |
| 9 | 批量操作里传入越权/不存在的 ID 是否真的"静默跳过、不整体报错" | 批量 PUT `id=<真实ID>&id=999999999`（后者不存在） | 检查响应状态码和真实 ID 那条是否生效 | 免费 |
| 10 | Client Key（DSN）列表/创建 endpoint 字段是否和文档一致 | `GET`/`POST /api/0/projects/{org}/{project}/keys/` | 对比 `dsn.public` 等字段名 | 免费 |
| 11 | `PUT` 更新项目时，`project:read`-only token 是否真的被限制在文档列出的白名单字段内 | 用只有 `project:read` scope 的 token 调 `PUT /api/0/projects/{org}/{project}/`，分别改白名单内/外的字段 | 白名单外字段应该被拒绝或忽略，记录具体行为 | 免费 |
| 12 | 创建 release 遇到已存在 `version` 时是否真的返回 `208` | 两次 `POST .../releases/` 同一个 `version` | 检查第二次的状态码和响应体 | 免费 |
| 13 | Region 相关：US 组织用裸 `sentry.io` 是否真的能work，EU 组织不用 `de.sentry.io` 会怎样 | 分别请求 | 记录具体行为（如果没有 EU 测试账号，这条标注"账号条件不满足，未验证"） | 免费；需要 EU 账号才能测后半部分 |

## P2（有一定成本或需要额外前置条件）

| # | 要测的结论 | 用哪个 endpoint | 怎么判定 | 预期成本 |
| :--- | :--- | :--- | :--- | :--- |
| 14 | Service Hook 注册后真的会收到 `event.alert`/`event.created` 推送 | `POST /api/0/projects/{org}/{project}/hooks/`（URL 指向一个临时的 webhook.site 之类的接收端） | 触发一条测试错误，观察是否收到 POST | 免费，但要求项目开通 `servicehooks` feature（可能需要付费计划或联系支持） |
| 15 | Integration Platform Webhook 的签名校验代码能不能真的验证通过 | 建一个 Internal Integration，配置 webhook URL 指向本地隧道 | 触发一个 issue 事件，用文档给的 HMAC-SHA256 代码验证签名 | 免费，需要搭一个临时接收服务（ngrok 之类） |
| 16 | Detector + Workflow 完整建一条"错误数超过阈值 → Slack 通知"的告警链路 | `POST .../detectors/` + `POST .../workflows/` | 人为制造超过阈值的错误量，观察是否触发通知 | 有一定操作成本（要接 Slack integration），且 `conditionResult` 优先级数值映射的矛盾点需要在这里确认 |
| 17 | `GET /api/0/seer/models/` 是否真的不需要鉴权 | 不带 `Authorization` header 直接调 | 检查是否成功 | 免费 |
| 18 | Seer autofix 完整流程（`POST .../autofix/` 触发 → 轮询 `GET` 状态） | 需要账号开通 Seer、且项目接了源码仓库 | 记录真实响应结构，替换掉 `issues.md` 里的猜测部分 | 可能需要额外权限/计费层级，成本未知，优先级放最后 |

## 验证完成后要做的事

1. 每验证一条，按 `create-doc-skill/references/verify.md` 的格式把对应 reference 文件里的 `⚠ 文档原文，未实测` 改成 `已用真实 API 验证（日期）：<做了什么> → <报错原文/响应片段>`。
2. 发现文档本身错了的地方，除了改对应 reference，同步升级到 `SKILL.md` 的"跨领域的通用规则"一节。
3. 全部验证跑完后，把 `SKILL.md` 顶部的"⚠ 验证状态"banner 更新成"哪些已验证、哪些仍是文档转录"的准确说法（照抄 AutoDL 案例的写法：分模块列清楚，不要笼统写"已验证"）。
4. 按 `create-doc-skill` 第 4 步，用 `evals/evals.json` 里的 5 个场景跑 with-skill / without-skill 对照实验，产出 `comparison-report.md`（Markdown 格式，按仓库约定不做 HTML/Artifact）。
5. 全仓库 `grep` 一遍确认没有真实 token/DSN 残留（验证过程中产生的临时 key 用完立即在 Sentry 后台吊销）。
