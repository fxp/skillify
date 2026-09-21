# airtable skill 验证计划（待真实 API Key）

现状：文档版，抓取于 2026-09-21。依据 `https://airtable.com/developers/web/llms.txt` 索引下的全部 API reference Markdown 导出页 + 从 API reference 页面渲染后的 HTML 中提取出的完整内嵌 OpenAPI 3.1.0 规范（该规范没有独立公开的 `/openapi.json` 路径，只能从页面自带的 hydration JSON 里摘出）+ `support.airtable.com` 的公式函数参考页，**没有做过任何真实 API 调用**，也没有跑 with/without skill 对照实验。

## 测试原则

- Key 只走环境变量 `AIRTABLE_TOKEN`（个人访问令牌，`pat` 前缀），不写入任何文件；验证完成后全仓库 `grep -rn "<token 前 12 位>"` 一遍确认无残留。
- 建一个专用的测试 base（几个字段覆盖主要类型：单行文本、数字、单选、多选、日期、附件、formula、rollup、链接记录），只在这个 base 上做写操作，避免碰到真实项目数据。
- 每条结论改回对应 reference 时按固定格式写"已用真实 API 验证（日期）：传 X 返回 `{...}`"，文档本身的缺口/错误同时升到 `SKILL.md` 的"跨领域的通用规则"。
- 测试 token 的 scope 建议一次性勾满 `data.records:read/write`、`schema.bases:read/write`，只授权给这一个测试 base，避免误碰真实数据。
- 每次调用记录到 `airtable-workspace/verification-log.md`：日期、endpoint、请求要点、原始响应/报错片段。

## P0 —— SKILL.md"先确认的事" + 本 skill 标为最高优先级的文档缺口（低成本、优先测）

| # | 结论/假设 | 怎么测 | 预期成本 | 判定 |
|---|---|---|---|---|
| 1 | **批量写请求的记录数上限**（Create/Update/Delete records）——官方文档正文和内嵌 OpenAPI 规范都没有直接写出数字，只有 `pyairtable` 源码硬编码 10 | 对同一张测试表分别发送 10 条、11 条、15 条的批量 Create records 请求 | 建 10~15 条测试记录，几乎零成本 | 确认 11 条是否真的报错、报错的具体 `type`/`message`；如果不报错，确认实际生效的上限是多少 |
| 2 | `filterByFormula` 传入非法/不构成合法公式语法的字符串（比如误传了序列化后的 JSON 字典字符串）时的真实行为 | 用 `filterByFormula='{"Status": {"$eq": "Active"}}'`（当成普通字符串传入）发一次 List records | 0（只读） | 确认是报错（哪个错误码/文案）、返回全部记录、还是返回空结果——这是 SKILL.md 头号陷阱条目的关键判据 |
| 3 | 计算字段（formula/rollup/count/autoNumber 等）在 Create/Update records 请求体里出现时的精确报错 | 对带 formula 字段的测试表，PATCH 一条记录，`fields` 里包含该 formula 字段名 | 0 | 记录精确的状态码、`error.type`、`error.message` 原文，替换 write-records.md 里"⚠ 未实测确认"的推测 |
| 4 | 附件字段写入的精确形状：`[{"url": "..."}]` 是否就够、`filename` 要不要一起传、传了官方读格式里的只读字段（如 `id`）会不会报错 | 分别用 `[{"url": <公网图片URL>}]`、`[{"url": ..., "filename": "x.jpg"}]` 两种 body 更新同一个附件字段 | 0（只是异步抓取一张小图） | 确认两种写法是否都成功；查最终读回的 `fields` 里 filename 从哪来（自动从 URL 推断还是必须显式传） |
| 5 | Base URL 和鉴权头精确格式 | 用 `Authorization: Bearer $AIRTABLE_TOKEN` 打一次 `GET /v0/meta/whoami` | 0 | 确认 200 且返回 `id`；同时用一个故意错的 token 确认 401 响应体格式 |

## P1 —— evals.json 的 5 个陷阱场景对应的裁决项（中等优先级）

| # | 陷阱 | 怎么测 | 预期成本 | 判定 |
|---|---|---|---|---|
| 6 | 链接记录字段传入目标表的显示文本（而非 record ID）时，`typecast: true` 是否会自动匹配/新建链接记录（eval #2 相关、SKILL.md 规则 6） | 对一个 `multipleRecordLinks` 字段，`typecast: true` 场景下传一个不存在的 record ID 字符串，以及传目标表 primary field 的显示文本字符串 | 低成本，几条测试记录 | 确认两种情况各自的行为：报错、忽略、还是新建/匹配了链接记录 |
| 7 | 429 限流触发后的精确响应头/体，以及是否真的需要固定等 30 秒（而非更短时间即可恢复） | 短时间内对同一个测试 base 连续发起超过 5 req/s 的只读请求，触发 429 后每隔几秒重试一次记录何时恢复 200 | 略高（要故意刷请求量），但纯读请求成本仍为 0 | 记录 429 响应体、`Retry-After`（如果有）、真实需要等待的秒数是否接近 30 |
| 8 | upsert 的节流策略是否真的与标准限流不同（write-records.md 引用的官方保留声明） | 对同一测试 base，分别用普通 batch update 和 `performUpsert` 各自做限流触发测试，对比恢复所需时间 | 低成本 | 确认两者是否有可观察的差异；如无差异，更新措辞为"未观察到差异" |
| 9 | 单选/多选字段传入不存在选项且不开 `typecast` 时的精确报错 `type`/`message` | PATCH 一条记录的 singleSelect 字段，传一个不存在的选项名，不带 `typecast` | 0 | 记录精确错误响应，替换 SKILL.md/write-records.md 里"文档原文，未实测"的转录 |
| 10 | uploadAttachment 端点（`content.airtable.com`）超过 5MB 文件时的精确报错 | 用一个 6MB 左右的文件走 uploadAttachment 端点 | 0（失败请求不产生存储成本） | 确认报错状态码/文案，验证"5MB 硬上限"这条结论 |

## P2 —— 影响准确性但优先级略低的项

| # | 结论 | 怎么测 | 预期成本 | 判定 |
|---|---|---|---|---|
| 11 | Get record 的"表名对不上但会退化成整 base 搜索"这条容错行为 | 用正确的 base、错误的 table（但 record 确实在这个 base 的另一张表里）请求 Get record | 0 | 确认是否依然 200 返回该记录 |
| 12 | `cellFormat=string` 在不传 `timeZone`/`userLocale` 时的精确报错 | List records 只传 `cellFormat=string`，不传另外两个参数 | 0 | 确认报错文案/状态码 |
| 13 | List records 分页游标 `LIST_RECORDS_ITERATOR_NOT_AVAILABLE` 的实际触发条件（客户端翻页多慢会触发） | 开始翻页后人为 sleep 较长时间（几分钟）再继续用旧 offset 翻下一页 | 0，只是耗时 | 记录大概多久后游标失效，更新 read-and-filter-records.md 的措辞 |
| 14 | `externalSyncSource` 字段是否真的完全只读 | 若测试账号能创建 synced table，尝试写这个字段；否则跳过 | 视账号权限而定，可能跳过 | 确认或补充"未验证，需要企业/同步功能权限"的说明 |
| 15 | OAuth 完整授权流程（本计划其它项都基于 PAT，OAuth 未覆盖） | 用官方 `Airtable/oauth-example` 仓库走一次完整授权 + 换 token + 刷新 | 需要额外注册 OAuth 集成，成本较高 | 视时间/优先级决定是否做，做的话补全 auth-and-scopes.md 的 OAuth 章节实测标注 |

## P3 —— 低优先级/需要企业权限或额外条件，暂不强求

| # | 项目 | 备注 |
|---|---|---|
| 16 | 企业专属 scope（SCIM、审计日志、change events、eDiscovery、HyperDB） | 本 skill 明确不覆盖，不在验证范围 |
| 17 | Webhooks API 全流程（创建、payload 拉取、过期刷新） | 本 skill 明确不覆盖，需要时应作为独立 skill/reference 补充 |
| 18 | Billing plan 差异（Free 的月度调用总量限制的精确阈值） | 需要 Free 计划账号长期观察用量，暂不强求 |
| 19 | Sync CSV 专用端点 | 本 skill 明确不覆盖 |

## 完成后

- 每条结论改回对应 reference 文件，写「已用真实 API 验证（日期）：传 X 返回 `{...}`」；文档本身的缺口/错误同时升到 `SKILL.md`"跨领域的通用规则"一节，尤其是 P0 #1（批量上限）和 #2（filterByFormula 误用的真实后果）——这两条是本次调研里价值最高的发现，务必优先坐实。
- `SKILL.md`"⚠ 验证状态"从"文档版，未验证"改成分区写清"已验证 / 仍是文档转录"，参照本工作区其它 skill（如 `firecrawl`、`autodl`）的写法。
- 跑 `evals/evals.json` 的 5 个场景做 with/without skill 对照（子 Agent 各写一版代码，用本计划里验证过的真实报错去判两版代码能不能在生产环境跑通），写 `airtable-workspace/comparison-report.md`（Markdown，按本工作区 `CLAUDE.md` 的约定，不生成 HTML/Artifact）。
- 全仓库 `grep` token 前 12 位，确认没有残留；删除测试中创建的所有记录、字段、表（如果新建了测试 base，测试结束后一并删除或清空）。
