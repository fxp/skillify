把这份 skill 装进你的 Agent，让它调用 Firecrawl 时不再凭记忆猜字段名，尤其不要在结构化抽取时漏传 `schema`、或调用已经废弃的 `/extract` 端点却不知道它废弃了。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill firecrawl --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill firecrawl --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/firecrawl/firecrawl.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认 3 件事」和「能力域导航」三节；
2. `references/` 下有 5 个 `.md`，其中 `structured-extraction.md` 讲的是 `/scrape` JSON 格式 vs 已废弃的 `/extract` 怎么选；
3. 在 `references/scrape.md` 里能搜到「已用真实 API 验证」字样，附带真实的响应片段（不是转录文档）。

## 这份 skill 覆盖什么

Firecrawl（`docs.firecrawl.dev`，域名 `api.firecrawl.dev` v2）的网页抓取/爬取/搜索 API：单页抓取（17 种输出格式）、
批量抓取、整站递归爬取（crawl）、URL 发现（map）、网页搜索（search）、结构化数据抽取该走哪条路、鉴权、错误码、限流与 credits 计费。

重点是两个**用真实 Key 验证过的静默失败陷阱**：`formats` 里传裸字符串 `"json"`（不带 `schema`）会返回 `success:true`
但 `data.json` 是 `null`，真正的失败信号藏在容易被忽略的 `data.warning` 字段里，而且照样扣 5 credits；独立的
`POST /extract` 端点已经被官方在运行时标记为废弃，但文档页面自己又建议迁移到另一个不同的端点（`/agent`），
两处权威来源互相矛盾——本 skill 一律建议走 `/scrape` 的 JSON 格式。另外两处反直觉默认行为：`map` 不会自动扩展到整站；
`search` 默认抓取每条结果的全文，不是只给标题摘要。

内容不是文档搬运：这是这批 skill 里唯一一个走完真实 API 验证 + with/without 对照实验全流程的——5 个场景里 3 个完胜，
2 个无 skill 版本凭合理工程直觉蒙对大方向但细节仍错，报告如实记录未夸大，见仓库 `data/comparison-report.md`。

## 版本

**已实测**，2026-09-21 用真实 Key 验证过核心端点（`/scrape`、`/map`、`/search`、`/crawl`、`/extract`）。
`/agent`、`/interact`、`/monitor`、`/parse` 等未覆盖，明确列在 SKILL.md 的「本 skill 不覆盖」一节。
