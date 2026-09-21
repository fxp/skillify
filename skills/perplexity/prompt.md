把这份 skill 装进你的 Agent，让它写调用 Perplexity API 的代码时不再凭训练记忆默认套用"POST /chat/completions + sonar-pro"，也不会漏传 `tools`/`preset` 导致 Agent API 悄悄不联网、没有引用。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill perplexity --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill perplexity --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/perplexity/perplexity.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认 4 件事」和「能力域导航」三节；
2. `references/` 下有 6 个 `.md`，其中 `agent-api.md` 讲的是 presets 与显式传 `model`/`tools` 的区别；
3. 在 `SKILL.md` 的"跨领域的通用规则"一节能搜到「Agent API 默认不联网、不引用」字样，并标注了 `⚠ 文档原文，未实测`。

## 这份 skill 覆盖什么

Perplexity（`docs.perplexity.ai`，域名 `api.perplexity.ai`）现在其实是**四个并行入口 + 一个过时入口**：Router（第三方开源模型的 OpenAI 兼容网关）、Agent API（官方现在的默认推荐入口，多提供商模型 + 内置 `web_search`/`fetch_url`/`sandbox` 等工具 + presets）、Search API（只拿排名网页结果，不经过 LLM）、Embeddings，以及仍可用但文档站每个页面顶部都挂着迁移提示的 Sonar Chat Completions（`sonar`/`sonar-pro`/`sonar-reasoning-pro`/`sonar-deep-research`，大多数人训练记忆里"Perplexity API"的样子）。

重点是两个反直觉陷阱：**Agent API 的联网搜索不是自动的**——给 `POST /v1/agent` 传裸 `model` 而不带 `tools`，拿到的是纯 LLM 回答，没有联网也没有引用，这和 Sonar Chat Completions"传 model 就自动带搜索"的行为完全相反，想联网必须显式传 `tools: [{"type": "web_search"}]` 或用会自动带上这些工具的 `preset`；以及 **Agent API 里 Anthropic 模型必须显式传 `max_output_tokens`，否则报 400**（文档原文："validation failed: max_output_tokens is required when using Anthropic models"），这是模型族特有的强制要求，OpenAI/Google/xAI 等其他模型不强制。此外 SKILL.md 还记录了 Search API 的 `POST /search` 路径下没有 `/v1` 前缀、日期过滤要用 `MM/DD/YYYY` 而不是 ISO 8601、以及 `sonar-deep-research` 有单独的引用/搜索查询/推理 token 三项额外计费，这些都是容易被合理直觉带偏的细节。

内容不是文档搬运：整理自 `docs.perplexity.ai` 的 `llms.txt`/`llms-full.txt`（全站 197 篇 Markdown 源页）加官方 OpenAPI 规范（`openapi.json`/`openapi-gateway-chat.json`/`openapi-auth.json`）交叉核对，字段名/类型/必填/枚举值以 OpenAPI 的 `components.schemas` 为准，请求示例、报错文案、限流与定价数字来自文档站转录，全部标注为 `⚠ 文档原文，未实测`。

## 版本

**文档版，抓取于 2026-09-21，未用真实凭证验证。** 全篇标注 `⚠ 文档原文，未实测`，没有做任何真实 API 调用，也没有做 with/without skill 的对照实验。实际调用时报错与 skill 不一致，**以 API 的真实报错为准**，并去 `docs.perplexity.ai` 核实最新情况。
