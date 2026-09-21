把这份 skill 装进你的 Agent，让它写 Exa 语义搜索接入代码时不再把 `/search` 的 `type` 参数写成早就换代的 `neural`/`keyword`，也不会把 `/search` 和 `/contents` 的内容选项（`highlights`/`text`/`summary`）嵌套位置搞混。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill exa --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill exa --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/exa/exa.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认 3 件事」和「能力域导航」三节；
2. `references/` 下有 5 个 `.md`，其中 `agent.md` 讲的是 `POST /agent/runs`（研究型异步代理）及其轮询/SSE/取消/回放接口；
3. 在 `references/search.md` 里能搜到「⚠ 文档原文，未实测」字样（这是文档版，全篇未做真实调用）。

## 这份 skill 覆盖什么

Exa（`exa.ai` / `docs.exa.ai`）是一个面向 AI Agent 的语义搜索 API：核心是 `/search`（自然语言查询网页并可选抽取正文，六种模式 auto/fast/instant/deep-lite/deep/deep-reasoning）、`/contents`（已知 URL 取正文/摘要）、`/answer`（问答+引用）、Exa Agent（`/agent/runs`，异步研究型代理，做 list building / 实体核查 / 富化）。

重点是两个来自官方 OpenAPI 规范（`exa-spec.json`）的反直觉发现：**`/search` 的 `type` 参数已经整体换代**——不再是训练语料里最常见的 `neural`/`keyword`，当前合法枚举值是 `instant`/`fast`/`auto`（默认）/`deep-lite`/`deep`/`deep-reasoning`，规范里完全没有旧值，传旧值是报错还是静默回退到 `auto` 未实测，是本 skill 优先级最高的验证项；**`/search` 和 `/contents` 接受同一套内容选项，但嵌套位置完全不同**（文档原文用 `<Warning>` 专门强调）——`/search` 把 `highlights`/`text`/`summary` 包在 `contents: {...}` 对象里，`/contents` 没有这层包装，这些字段直接铺在请求体顶层和 `urls`/`ids` 平级，照抄一个端点的请求体结构去拼另一个端点大概率是错的。另外 `POST /findSimilar` 已被官方标为废弃（`deprecated: true`），建议改用 `/search` + 自然语言描述源页面特征。

内容不是文档搬运：字段名、类型、默认值来自官方 OpenAPI 规范，鉴权格式（`Authorization: Bearer`）来自比对文档站全部示例代码得出的结论（规范里同时列了 `x-api-key` 但没有任何示例用它），`resolvedSearchType` 字段被标出文档自相矛盾之处（规范描述说是已废弃字段应为空字符串，但同一份规范给的示例响应里却有值），这些都留给拿到真实 Key 的人裁决。

## 版本

文档版，抓取于 2026-09-21，未用真实凭证验证。实际调用时报错与 skill 不一致，
**以 API 的真实报错为准**，并去 `docs.exa.ai` 核实最新情况（Exa API 在训练数据截止后已有实质性变化）。
