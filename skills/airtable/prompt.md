把这份 skill 装进你的 Agent，让它写 Airtable 接入代码时不再把 `filterByFormula` 当成 MongoDB/Pinecone 那种 `{field: {$gt: value}}` 操作符对象来写——Airtable 会把它当字符串处理，**不报错，只会静默返回不符合预期的结果**。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill airtable --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill airtable --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/airtable/airtable.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认 3 件事」和「能力域导航」三节；
2. `references/` 下有 5 个 `.md`，其中 `read-and-filter-records.md` 讲的是 `filterByFormula`（Airtable 自有公式语言）的语法；
3. 在 `SKILL.md` 里能搜到「MAX_RECORDS_PER_REQUEST」字样——这是官方 `pyairtable` 客户端源码里硬编码的批量写请求上限（10 条/请求），因为官方 Web API 文档正文和内嵌 OpenAPI 规范都没有直接写出这个数字。

## 这份 skill 覆盖什么

Airtable Web API（`airtable.com/developers/web/api`）以 base（数据库/工作区）为顶层单位，base 内有 table，table 内是 record（行）与 field（列）。覆盖：鉴权（个人访问令牌取代了 2024-02-01 停用的旧版 API key，以及 OAuth）与细粒度 scope、记录读取与分页（offset/pageSize/view）、`filterByFormula` 过滤、记录的创建/更新/删除（单条与批量、upsert、typecast）、字段类型与只读计算字段、附件字段的专用上传流程、Metadata API、错误码与限流（5 请求/秒/base，50 请求/秒/用户）。

重点是两个真实发现的陷阱：**`filterByFormula` 是 Airtable 自己的公式语言，语法接近 Excel，不是 SQL 也不是 MongoDB 风格的操作符对象**——如果 Agent 刚写过 MongoDB/Pinecone 之类的过滤器代码，很容易照搬 `{"age": {"$gt": 18}}` 这种结构传给 `filterByFormula`，Airtable 不会报错，只会静默返回全部记录或空结果，这是本 skill 认定的头号陷阱，正确写法是一个求值为布尔的公式字符串，如 `AND({Status} = "Active", {Age} > 18)`；**批量写请求的记录数上限，官方文档正文和内嵌 OpenAPI 规范里都没有直接写出具体数字**——这是本次调研中最值得记录的"文档与现实的落差"，官方维护的 Python 客户端 `pyairtable` 源码里硬编码 `MAX_RECORDS_PER_REQUEST = 10` 并据此自动分批，写批量代码时应默认按 10 条/请求分批,但这不等于真实调用已验证。此外计算字段（formula/rollup/lookup/count 等）只读，不能通过写记录接口设置。

内容不是文档搬运：skill 明确标出了官方文档的两处缺口（批量上限数字缺失、附件字段写入形状未给精确字段表），并交叉核对了官方 Markdown 文档与从页面内嵌 JSON 提取的完整 OpenAPI 3.1.0 规范（该规范未在任何独立路径公开）。全篇未用真实 API Key 调用验证过任何一条结论，也没有做 with/without skill 的对照实验，报错文案、状态码、限流数字全部标 ⚠ 文档原文，未实测。

## 版本

文档版，抓取于 2026-09-21，未用真实凭证验证。**实际调用时报错与 skill 不一致，以 API 的真实报错为准**，并去 `airtable.com/developers/web/api` 核实最新情况；批量写请求上限、附件字段写入的精确形状是验证计划里优先级最高的两项。
