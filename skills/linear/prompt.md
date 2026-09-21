把这份 skill 装进你的 Agent，让它写调用 Linear API 的代码时不再去找不存在的 REST 端点，也不会把三种入口的鉴权 header 格式弄混而拿到 401。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill linear --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill linear --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/linear/linear.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认 4 件事」和「我要做什么 → 读哪一份」三节；
2. `references/` 下有 8 个 `.md`，其中 `agents-and-mcp.md` 讲的是 Linear for Agents（Agent Session/Activity）和官方远程 MCP Server；
3. 在 `SKILL.md` 里能搜到「个人 API Key 是 `Authorization: <API_KEY>`（没有 `Bearer` 前缀）」字样，并且能看到官方 MCP Server 反而统一要 `Bearer` 的对比说明。

## 这份 skill 覆盖什么

Linear（`developers.linear.app`，唯一 endpoint `https://api.linear.app/graphql`）是纯 GraphQL API 的项目管理平台，**没有平行的 REST API**。本 skill 覆盖核心资源（Issue/Team/Project/Cycle/WorkflowState/IssueLabel/Comment）的查询与增删改、鉴权（个人 API Key / OAuth2 / OAuth Actor Authorization / Client Credentials）、cursor 分页与过滤器、Webhook、官方 TypeScript SDK（`@linear/sdk`），以及 Linear 专门为 AI Agent 设计的 Agent Session/Activity/Signals 体系和官方远程 MCP Server（`mcp.linear.app`）。

重点是两个反直觉陷阱：**三个入口三套鉴权 header 规则，混用会 401**——个人 API Key 直连 GraphQL 主端点是裸 key（`Authorization: <API_KEY>`，没有 `Bearer` 前缀），OAuth2 access token 直连是 `Authorization: Bearer <ACCESS_TOKEN>`（有前缀），而官方 MCP Server（`mcp.linear.app`）不管传哪种 key 都统一要求 `Bearer` 前缀；以及**分页默认页大小是 50，不传分页参数的查询会静默截断、不报错也不提示**，必须显式检查 `pageInfo.hasNextPage` 才能确认是否拿全了数据。此外 SKILL.md 还记录了 Team/Project/Cycle/WorkflowState/IssueLabel 只能按 ID 查、按 ID 传（不接受名字，要先用 filter 查出 UUID）、WorkflowState 和 Cycle 的 ID 是团队私有不能跨团队复用（IssueLabel 相反，可以是工作区级）、`cycleCreate` 已被官方标记废弃不可用（Cycle 只能靠 Team 设置驱动自动生成）、以及限流配额里 API Key 的请求数配额低于 OAuth App 但复杂度配额反而更高，不能假设"换 OAuth 全面更宽松"。

内容不是文档搬运：整理自 `linear.app/developers/*` 全部 26 篇开发者文档页（已 301 重定向自旧域名 `developers.linear.app`）+ `linear.app/docs/mcp` + 官方 GraphQL SDL 规范 `schema.graphql`（52,378 行，随 `@linear/sdk` 发布）+ `@linear/sdk` 源码里的错误类型映射；字段名/类型/是否必填直接引自 SDL 规范，精度高于人写教程，其余"会报错""默认返回 xxx"这类行为描述是文档原文转录，全部标注 `⚠ 文档原文，未实测`（全部 reference 文件共 42 处）。Linear for Agents 相关内容官方自己标注为 Developer Preview，比其余部分更不稳定。

## 版本

**文档版，抓取于 2026-09-21，未用真实凭证验证。** 全篇标注 `⚠ 文档原文，未实测`，没有做任何真实 API 调用，也没有做 with/without skill 的对照实验。实际调用时报错与 skill 不一致，**以 API 的真实报错为准**，并去 `linear.app/developers` 核实最新情况。
