把这份 skill 装进你的 Agent，让它接 Sentry 时不再把 DSN 和 Web API 的 auth token 这两种完全不同的凭证搞混，也不会漏掉「不传 `query` 时默认只查未解决 issue」这种容易让搜索结果悄悄少一半的默认行为。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill sentry --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill sentry --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/sentry/sentry.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「先分清楚：ingestion 还是 Web API？」「用之前先确认这 3 件事」三节；
2. `references/` 下有 8 个 `.md`，其中 `ingestion-vs-api.md` 讲的是 DSN 上报（ingestion）和 auth token 查询（Web API）这两套完全独立的 API 表面该怎么选；
3. 在 `SKILL.md` 里能搜到「links.regionUrl」字样，是判断该用 `us.sentry.io` 还是 `de.sentry.io` 的官方推荐做法。

## 这份 skill 覆盖什么

Sentry（`docs.sentry.io`，错误追踪/应用监控平台）的两类开发者任务：给应用装 SDK 让它自己上报错误（ingestion，用 DSN），以及用 Web API（`sentry.io/api/0/...`，Bearer auth token）读取/管理组织、项目、issue、event、release、alert 等已有数据。覆盖鉴权（三种 auth token 怎么选）、issue 查询 DSL、事件与堆栈跟踪、release 与 deploy、alert 与 webhook、分页限流；Crons 定时任务监控不在覆盖范围内。

内容不是文档搬运，重点是两个真实发现的反直觉点：一是 **ingestion 和 Web API 是完全独立的两套 API 表面、两种不能互换的凭证**——DSN 天生只写不读（官方原话："they do not allow read access to any information"），SDK 的 `dsn=` 参数不能填 auth token，反过来 auth token 也不是 SDK 初始化参数，这是本 skill 要防的头号混淆错误；二是 **Issue 搜索不传 `query` 参数时默认应用 `is:unresolved` 过滤**，很容易被误解成「不传条件=查全部」，实际上已解决/已忽略的 issue 会被悄悄排除在外，而且 issue 搜索本身是 `key:value` 的 DSL，不支持 `OR`/`AND` 布尔操作符（那是 Explore/Dashboards/Monitors 才有的语法）。另外 SKILL.md 还提醒 Base URL 必须带区域前缀（`us.sentry.io` / `de.sentry.io`），最稳做法是查一次组织信息的 `links.regionUrl` 字段而不是自己猜。

## 版本

文档版，抓取于 2026-09-21，未用真实凭证验证。实际调用时报错与 skill 不一致，
**以 API 的真实报错为准**，并去 `docs.sentry.io` 核实最新情况。
