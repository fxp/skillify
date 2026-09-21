# Notion API 接入 skill — 验证计划

`/Users/chopinfeng/Workspace/Skillify/notion/` 目前的全部内容来自官方文档站（`developers.notion.com` 的 `llms.txt`/`llms-full.txt` + `openapi.json`，抓取于 2026-09-21，当时最新 API 版本 `2026-03-11`）与官方迁移指南，**没有用真实 API Key 做过一次调用**。本文件按优先级列出拿到 key 后要按顺序验证的结论，每条给出用哪个 endpoint、预期成本、怎么判定通过/失败。验证完成后，把结论按 `已用真实 API 验证（日期）：... 返回 {...}` 的格式写回对应 reference 文件，并在 `SKILL.md` 的"⚠ 验证状态"一节更新范围说明。

Key 只通过环境变量传入命令本身，不写进任何文件；测试产生的页面/数据库/区块用完清理（trash 即可，Notion API 不支持永久删除）。

## 前置条件

- 一个真实 Notion 工作区 + 一个 Personal access token（最省事的起点，不需要走 OAuth，也不需要额外做"共享"这一步就能拿到自己账号下的内容）。
- 至少准备一个测试用的 Notion 数据库，包含 `select`、`multi_select`、`relation`、`rich_text`、`title`、`checkbox`、`date` 几种属性类型，方便验证第 3、4 组。
- 如果条件允许，额外建一个 **internal connection**（用来验证"未共享 → 404"这条最关键的坑，PAT 场景验证不出这条）。

## P0：全篇最重要的一条坑——共享要求

**目标**：拿到 404 `object_not_found` 的真实报错原文，并确认共享后同一请求变成 200。

1. 用刚创建的 internal connection 的 token，直接 `GET /v1/users/me` 确认 token 本身有效。
2. 挑一个 **没有** 共享给该连接的测试页面，`GET /v1/pages/{page_id}`。预期：404，记录完整响应体（`code`/`message`/`status`）。
3. 在 Notion UI 里把该页面共享给这个连接（`••• → Add connections`）。
4. 重复第 2 步的请求。预期：200。
5. 用同一个 token 测试"共享父页面，子页面自动可访问"：建一个子页面，不单独共享它，直接 `GET` 子页面。预期：200（验证继承）。
6. 对照组：换成 **PAT**，对一个 PAT 创建者本人能在 Notion 里看到、但从未对任何连接做过"Add connections"的页面直接 `GET`。预期：200（验证 PAT 不需要共享这一步）。

判定：步骤 2 和步骤 6 的行为差异，以及步骤 2 的报错文案是否和 `references/auth-and-sharing.md` 里转录的文档示例一致，是本 skill 目前最大的未验证风险点。成本：0（纯读操作）。

## P0：database → data source 发现流程

**目标**：确认 `GET /v1/databases/{id}` 的真实响应形状，尤其是 `data_sources` 数组的确切字段。

1. 对测试数据库 `GET /v1/databases/{database_id}`，记录完整响应，核对是否确实只有 `data_sources: [{id, name}]`，不直接带 `properties`。
2. 用拿到的 `data_source_id` 调 `GET /v1/data_sources/{data_source_id}`，确认 `properties`（schema）、`parent`、`database_parent` 字段是否如文档描述。
3. 故意把 `database_id` 传给 `PATCH /v1/data_sources/{database_id}/query`（类型不匹配），记录报错是明确的 400/404 还是其它行为。
4. 故意把 `data_source_id` 传给 `GET /v1/databases/{data_source_id}`，同样记录报错。

成本：0（纯读操作，第 3、4 步预期报错，属于正常验证）。

## P1：属性值形状——select / multi_select / relation / rollup

**目标**：确认 `references/pages-and-blocks.md` 里的属性值形状表准确，尤其是"新选项自动加入 schema"和"relation 依赖对侧共享"这两条行为描述。

1. `POST /v1/pages` 创建一页，同时写 `select`（用一个已存在选项的 `name`）、`multi_select`（一个已存在 + 一个**全新**的 `name`）、`relation`（关联另一个测试页面）三种属性。
2. `GET` 这个新页面，核对三种属性值的真实回读形状是否和文档表一致；确认那个全新的 `multi_select` 选项是否真的被自动加进了 schema（再 `GET` 一次 data source 确认）。
3. 用一个 **没有** 共享给该连接的页面 ID 去建 relation，确认响应是报错还是"relation 建立但之后读回是空/看不到目标页信息"（这条决定了 relation 属性读到空值时的排查方向）。
4. 建一个 `rollup` 属性（聚合某个 relation 的 `select` 值），`GET` 页面确认 rollup 的真实回读形状。

成本：新建 2-3 个测试页面，可控。

## P1：区块树读写 + markdown 便捷层

**目标**：验证区块追加/更新/删除的边界行为，以及 markdown 层和区块层的交互。

1. `POST /v1/pages` 用 `markdown` 字段创建一页（含标题+一段+一个列表），`GET /v1/blocks/{page_id}/children` 确认转换出的区块结构是否符合预期。
2. `PATCH /v1/blocks/{page_id}/children` 追加一个 `to_do` 区块，`position: {"type": "start"}`，确认真的插到最前面而不是末尾。
3. `PATCH /v1/blocks/{block_id}` 更新那个 `to_do` 的 `checked` 字段，确认"整字段替换、其它字段不受影响"的说法是否属实（同时传另一个没改过的字段看是否被清空）。
4. `DELETE /v1/blocks/{block_id}` 删掉一个区块，`GET` 确认 `in_trash: true`，且区块仍能通过 `GET /v1/blocks/{id}` 读到（软删除，非真删）。
5. 尝试一次超过 100 个子区块的 `children` 数组，确认是明确报错还是截断处理。
6. 验证 `archived` 字段：在 `2026-03-11` 版本下对 `PATCH /v1/pages/{id}` 传 `{"archived": true}`（而不是 `in_trash`），确认是报错、忽略还是仍然生效——这决定了"archived 别名已移除"这条结论是否准确。

成本：新建 1 页 + 若干区块操作，可控。

## P2：Search、错误处理、限流

1. `POST /v1/search` 不传 `query`，确认 `page_size` 默认值（核对 100 还是 10——`reference/intro.md` 和 `search-optimizations-and-limitations.md` 两处文档口径不一致，是本 skill 已标注的一处"文档自相矛盾"）。
2. `POST /v1/search`，`filter.value` 分别传 `"database"`（旧值）和 `"data_source"`（新值），对比行为差异（报错 / 忽略过滤条件 / 正常按新值工作）。
3. 故意省略 `Notion-Version` 头发一次请求，记录 `400 missing_version` 的真实报错文案。
4. 如果账号或工作区允许，故意触发一次 429（短时间内高频请求），记录 `Retry-After` 与 `additional_data` 的真实字段。**不建议**专门为了验证 Free 工作区 1000 区块上限而真的把测试工作区写满——这条如无现成的接近上限的工作区，标注为"未验证，按官方文档转录"即可，不必专门制造。

成本：Search 只读免费；429 测试要注意不要影响工作区里其它正在跑的连接。

## 验证记录格式

在对应 reference 文件里，把 `⚠ 文档原文，未实测` 替换为：

```
已用真实 API 验证（YYYY-MM-DD）：<做了什么> → <真实响应/报错片段>
```

如果发现文档本身是错的（不是本 skill 转录出错，而是官方文档描述与真实行为不符），除了改对应 reference，还要把这条发现升级写进 `SKILL.md` 的"跨领域通用规则"一节，并在这里追加一张"验证中修正的文档条目"表格记录下来。

## 尚未纳入范围、按需再补

以下能力域在抓取阶段已识别但本 skill 明确不覆盖，如果后续需要可以用同样的方法论（先读 `openapi-summary/` 对应 tag，再实测）单独补充：Comments（评论）、File uploads（含大文件分片上传）、Views（数据库视图管理）、Webhooks、Notion Agent APIs（Custom Agents / Sessions）、Agent Skills API、Meeting notes、Custom emojis、OAuth token 的 introspect/revoke/refresh 细节。
