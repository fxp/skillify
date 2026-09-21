把这份 skill 装进你的 Agent，让它写 Notion API 接入代码时不再凭训练记忆里"只有 database 和 page"的旧模型编代码——2025-09-03 版本之后 database 和 data source 是两个不同的对象，`database_id` 和 `data_source_id` 不能互换，也不会漏掉"必须先在 Notion UI 里把页面共享给集成"这个最容易踩的坑。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill notion --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill notion --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/notion/notion.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认 3 件事」和「能力域导航」三节；
2. `references/` 下有 6 个 `.md`，其中 `databases-and-data-sources.md` 讲的是 database 与 data source 双层模型（2025-09-03 起的架构变更）；
3. 在 `SKILL.md` 里能搜到「404」字样，确认的是"集成未被共享到页面时返回 404 而不是权限错误"这条坑，而不是笼统的权限报错说明。

## 这份 skill 覆盖什么

Notion API（`developers.notion.com`，域名 `api.notion.com`）让集成读写 Notion 工作区里的页面、数据库/数据源、区块、评论、用户和文件。覆盖 7 块：鉴权（internal connection / personal access token / public OAuth connection）与共享机制、database/data source 双层模型与查询过滤排序、页面与区块(block)内容树的读写、富文本(rich text)对象格式、Search、版本化的 `Notion-Version` 请求头与错误/限流、官方 SDK。

重点是两个真实发现的陷阱：**"token 有效"和"集成能看到这个页面/数据库"是两回事，而且失败模式是 404 不是 403**——internal connection 和 public connection 必须先在 Notion UI 里对每个顶层页面/数据库手动"Add connections"（子页面会继承父页面的共享，PAT 例外直接继承创建者权限），没共享时 API 返回该资源"不存在"（404），极容易被误诊为"ID 抄错了"而不是共享没做；**2025-09-03 起 database 和 data source 是两个不同对象，`database_id` 和 `data_source_id` 不能互换**——一个 database 下可以挂多个 data source，几乎所有"读写数据库行"的操作现在都要用 `data_source_id`，正确流程是先 `GET /v1/databases/{database_id}` 拿到 `data_sources[]` 列表，再用其中的 `data_source_id` 去查询/创建页面/建关系，凭旧模型写代码会直接报错或查到空结果。

内容不是文档搬运：skill 明确标出了这次数据源模型的架构变更时间点，并把"页面内容是区块树，但 API 也提供了 markdown 便捷层，两者语义不同"这类容易混淆的边界写清楚（整体写入用 markdown 更快，局部/增量编辑仍要用区块级 API）；富文本从不是纯字符串而是带 `annotations` 的对象数组这条也单独标出。全篇未用真实 Key 验证，所有具体报错文案、字段行为标注为 ⚠ 文档原文，未实测。

## 版本

文档版，抓取于 2026-09-21，未用真实凭证验证。**实际调用时报错与 skill 不一致，以 API 的真实报错为准**，并去 `developers.notion.com` 核实最新情况。
