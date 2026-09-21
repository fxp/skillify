把这份 skill 装进你的 Agent，让它写 Tavily 搜索/抽取接入代码时不再套用 Firecrawl/Serper/Bing 等其他搜索平台的字段习惯，也不会漏查 `/extract`、`/crawl` 响应里容易被忽略的 `failed_results`（HTTP 200 不代表全部成功）。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill tavily --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill tavily --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/tavily/tavily.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认 3 件事」和「我要做什么 → 读哪一份」三节；
2. `references/` 下有 5 个 `.md`，其中 `research.md` 讲的是 `POST /research` 的三个不按常规 REST 习惯来的 HTTP 状态码（201 创建、202 处理中、200 才是完成/失败）；
3. 在 `references/errors-and-limits.md` 里能搜到「⚠ 文档原文，未实测」字样（这是文档版，全篇未做真实调用）。

## 这份 skill 覆盖什么

Tavily（`tavily.com` / `docs.tavily.com`）是专为 AI Agent 和 RAG 场景设计的搜索与内容 API：`/search` 做实时网页搜索、`/extract` 从已知 URL 批量抽正文、`/crawl` + `/map` 做站内图状发现与批量抽取、`/research` 做多步骤深度研究并产出带引用的报告，外加 Python/JS SDK、CLI、MCP、keyless 免密访问、x402 按次付费。

重点是两个来自官方 OpenAPI 规范和文档正文的反直觉发现：**`content` 和 `raw_content` 不是"精简版"和"完整版"的关系，是两个默认行为完全不同的字段**——`/search` 的 `results[].content` 一直都在（分块摘要），但 `results[].raw_content`（清洗后的完整正文）**默认不返回**，必须显式传 `include_raw_content: true`；而 `/extract`、`/crawl` 的响应里正好反过来，正文字段就叫 `raw_content` 且默认返回，跨 endpoint 套用字段名语义会出错。**`/extract`、`/crawl` 的 HTTP 200 不代表全部成功**——OpenAPI 对 200 响应的官方描述原文是"HTTP 200 can have an empty results array when all valid URLs fail during extraction"，必须检查响应里的 `failed_results` 字段，不能只按状态码判断。此外文档站自身存在多处矛盾（比如 `max_results` 默认值，OpenAPI/SDK 说是 10，Best Practices 页面和 CLI 文档都说是 5），skill 里逐条标了出来，没有替读者替官方定论。

## 版本

文档版，抓取于 2026-09-21，未用真实凭证验证。实际调用时报错与 skill 不一致，
**以 API 的真实报错为准**，并去 `docs.tavily.com` 核实最新情况（这份文档站更新非常活跃，抓取时 changelog 最新条目就在 2026-08）。
