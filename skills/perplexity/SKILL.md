---
name: perplexity
description: 接入 Perplexity API（docs.perplexity.ai / api.perplexity.ai）的使用手册（文档版，未经真实调用验证）——涵盖新的统一 Agent API（多提供商模型 + 内置 web_search/fetch_url/sandbox/people_search/finance_search 工具 + presets）、独立的 Search API（POST /search 原始检索结果）、正在被 Agent API 取代的 Sonar Chat Completions（sonar/sonar-pro/sonar-reasoning-pro/sonar-deep-research，OpenAI 兼容）、Router API（第三方开源模型网关）、Embeddings API、搜索控制（domain/recency/date/language/location 过滤）、流式与结构化输出、错误码/限流/计费。当用户提到 "Perplexity API" "Perplexity Sonar" "pplx-api" "api.perplexity.ai" "PERPLEXITY_API_KEY" "sonar-pro" "sonar-deep-research" "Perplexity Agent API"，或要写代码调用 Perplexity 做带引用的网页问答/检索时，应主动使用本技能——Perplexity 的 API 面在训练数据截止后发生了结构性变化（新增了和 Sonar 平行的 Agent API/Search API/Router API，Sonar Chat Completions 正被标注为过时），不要只凭训练记忆写成"POST /chat/completions + sonar-pro"就完事，也不要误用其他搜索/RAG API（Tavily、Exa、Firecrawl）的参数习惯。
---

# Perplexity 接入指南

Perplexity 提供**四个独立的核心 API**：**Router**（第三方开源模型的 OpenAI 兼容网关）、**Agent API**（多提供商模型 + 内置网页搜索/URL 抓取/代码沙箱等工具 + presets，官方现在的默认推荐入口）、**Search**（只拿排名网页结果，不经过 LLM）、**Embeddings**（文本向量化）。此外还有一套**仍可用但被官方标注为过时（deprecated）** 的 **Sonar Chat Completions API**（`sonar`/`sonar-pro`/`sonar-reasoning-pro`/`sonar-deep-research`，OpenAI 兼容 `messages`/`choices` 结构）——这是大多数人训练记忆里"Perplexity API"的样子，但官方文档站的每一个 Sonar 页面顶部都挂着一条迁移提示，建议新集成改用 Agent API。本 skill 五个入口都覆盖，按开发者意图分文件。

## ⚠ 验证状态

**文档版：内容整理自 `https://docs.perplexity.ai/llms.txt` + `llms-full.txt`（全站 197 篇 Markdown 源页）+ 官方 OpenAPI 规范 `openapi.json`（`info.version: 1.0.0`，含 Sonar/Search/Embeddings/Agent/Skills/Analytics）+ `openapi-gateway-chat.json`（Router）+ `openapi-auth.json`，抓取于 2026-09-21，尚未用真实 API Key 调用验证。**

- 字段名、类型、必填、枚举值、默认值：来自官方 OpenAPI 规范的 `components.schemas`，是当前流程里最权威的原始材料；但规范本身也可能滞后于线上真实行为，且 OpenAPI 摘要脚本在个别大 schema 上有展开不全的情况（例如 `/v1/sonar` 的响应曾遗漏 `citations`/`search_results`/`images`/`related_questions` 四个顶层字段，本 skill 已用原始 JSON 交叉核对补全，但类似遗漏不能保证已全部排查干净）。
- 请求/响应示例：来自文档站代码块，全部标 `⚠ 文档原文，未实测`。
- 报错文案、错误码、限流数字、定价数字：来自 `/docs/admin/rate-limits-usage-tiers`、`/docs/getting-started/pricing`、`/docs/sdk/error-handling` 页面转录，同样未实测，标 `⚠ 文档原文，未实测`。
- 本 skill **没有做任何真实 API 调用**，也没有做 with/without skill 的对照实验。`evals/evals.json` 里的期望输出是"文档说应该这样"的假设，不是已验证结论。
- 拿到真实 Key 后按优先级验证的清单见 `perplexity-workspace/verification-plan.md`。

## 用之前先确认 4 件事

1. **先搞清楚要用哪个 API，不要默认套用训练记忆里的 Sonar Chat Completions**。官方现在把 **Agent API**（`POST /v1/agent`）定位为"多提供商、web-grounded 答案 + 内置引用"的默认入口；Sonar Chat Completions（`POST /v1/sonar`）仍然可用、字段没变，但文档明确标注为过时路径。新项目除非明确只要"OpenAI 兼容的 sonar-pro chat completion"，否则应优先考虑 Agent API。见下方导航表。
2. **Base URL 因 API 而异**，不是一个统一的 `/v1/xxx`：
   - Sonar Chat Completions：`https://api.perplexity.ai/v1/sonar`（OpenAI SDK 兼容路径 `https://api.perplexity.ai` + `/chat/completions` 也可，两者等价）
   - Agent API：`https://api.perplexity.ai/v1/agent`（OpenAI Responses SDK 兼容：`base_url="https://api.perplexity.ai/v1"` + `client.responses.create()`，实际打到 `/v1/responses`，是 `/v1/agent` 的别名）
   - Search API：`https://api.perplexity.ai/search`（注意**没有** `/v1` 前缀，和其他端点不一致）
   - Router API：`https://api.perplexity.ai/router/v1`（OpenAI Chat Completions 兼容）
   - Embeddings：`https://api.perplexity.ai/v1/embeddings`、`https://api.perplexity.ai/v1/contextualizedembeddings`
3. **鉴权统一是 `Authorization: Bearer $PERPLEXITY_API_KEY`**（HTTPBearer，规范里唯一列出的安全方案），所有 API 通用，Key 在 `https://console.perplexity.ai/project/keys` 生成，创建时必须先建 Project。⚠ 文档原文，未实测：Key 只在创建时完整显示一次。
4. **最容易选错的字段：Agent API 里"要不要联网搜索"不是自动的**。给 `POST /v1/agent` 传一个裸的 `model`（如 `openai/gpt-5.6-sol`）而不带 `tools`，得到的是**纯 LLM 回答，没有联网搜索，没有引用**——这和 Sonar Chat Completions"传 model 就自动带搜索"的行为完全不同。想要联网必须显式传 `tools: [{"type": "web_search"}]`，或者用 `preset`（presets 会自动带上 `web_search`/`fetch_url` 工具和引用格式要求的系统提示词）。见 `references/agent-api.md`。

## 30 秒跑通第一个请求

最简单、成本最低的路径是 Agent API 的 `fast` preset（内置 `web_search`，单步，reasoning_effort 最低）：

```bash
curl https://api.perplexity.ai/v1/agent \
  -H "Authorization: Bearer $PERPLEXITY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "preset": "fast",
    "input": "What is the current version of the Python programming language?"
  }' | jq
```

```python
from perplexity import Perplexity  # pip install perplexityai

client = Perplexity()  # 从环境变量 PERPLEXITY_API_KEY 读取
response = client.responses.create(
    preset="fast",
    input="What is the current version of the Python programming language?",
)
print(response.output_text)
```

⚠ 文档原文，未实测：响应形状（`output` 数组，含 `search_results` 条目和 `message` 条目）来自文档代码块，未真实调用确认。如果只想要"老式" OpenAI 兼容 chat completion + 引用数组，见 `references/grounded-answers.md` 的 Sonar 30 秒示例。

## 能力域导航

| 我想做什么 | 参考文件 | 涉及的核心 endpoint |
|---|---|---|
| 用 OpenAI 兼容的 `messages`/`choices` 结构拿一个带引用的网页问答（经典 Sonar 用法，仍可用但官方标注过时） | `references/grounded-answers.md` | `POST /v1/sonar`（= `POST /chat/completions`）、`POST /v1/async/sonar` |
| 用新的统一 Agent API 拿网页问答（多提供商模型可选、内置引用、可加代码沙箱/MCP/自定义函数等工具、支持 preset 一键配置） | `references/agent-api.md` | `POST /v1/agent`（= `POST /v1/responses`）、`GET /v1/agent/{id}`、presets |
| 只要原始检索结果（标题/URL/摘要），自己接自己的 LLM 或做数据管线，不要 Perplexity 帮我生成答案 | `references/search-api.md` | `POST /search` |
| 控制搜索范围：限定/排除域名、限定发布或更新时间、限定语言、按地理位置个性化、按人名找人 | `references/search-controls.md` | Sonar 的 `search_domain_filter` 等请求体字段 / Agent API `web_search` 工具的 `filters` / Search API 的同名请求体字段（三处字段名相同但挂载位置不同） |
| 在 Sonar/Search/Router/Agent 之间选模型，理解 `sonar`/`sonar-pro`/`sonar-reasoning-pro`/`sonar-deep-research` 与 Agent API 第三方模型/presets 的成本-深度权衡 | `references/models.md` | 无独立 endpoint，是选型指南 |
| 查错误码、限流档位、每个 API 的计价结构、Embeddings API 基本用法 | `references/errors-limits-pricing.md` | 全端点通用 + `POST /v1/embeddings`、`POST /v1/contextualizedembeddings` |

**本 skill 不覆盖**（文档里存在但超出"网页问答/检索"这个核心场景）：Router API 的完整第三方模型目录与故障转移细节（只在 `models.md` 里简要提一句用途）；Agent API 的 Sandbox 代码执行、MCP 远程服务器、Connectors、Custom Functions、Skills（server-side skill 上传）、Wide Research、Conversation state/多轮会话、Background Mode 的完整生命周期、Image Attachments——这些是 Agent API 更"agentic"的一面，本 skill 只在 `agent-api.md` 里点名存在和用途，不展开字段表，需要时读对应文档页；管理面 Analytics API（组织级用量查询）、API Key 管理的编程接口（`/generate_auth_token`、`/revoke_auth_token`）；Perplexity CLI（`pplx`）、官方 MCP Server、Perplexity Search SDK（"Search as Code"）。

## 跨领域的通用规则（写代码前必读）

以下每条都标了来源，**全部未经真实调用验证**，是本 skill 认为最值得优先验证的"直觉陷阱"假设：

1. **Agent API 默认不联网、不引用**（见上方"先确认 4 件事"第 4 条）。裸 `model` + 无 `tools` = 纯聊天模型。这是从"Sonar 系列模型天生自带搜索"心智迁移过来的开发者最容易踩的坑。
2. **Agent API 的行内引用标记 `[1][2]` 不是自动的**（文档原文，`web-search.md`）：即使加了 `web_search` 工具，模型是否在回答里插入方括号引用标记"取决于提示词"——presets 的系统提示词里硬编码了引用格式规则，但如果你自己拼 `model` + `tools` 而不写引用要求，很可能拿到一段引用了网页内容但没有任何 `[1]` 标记的纯文本。无论有没有标记，都应该以 `search_results[].id`/`url` 为可信来源，不要依赖正文里是否出现方括号。对比之下，Sonar Chat Completions 的引用格式规则是服务端固定注入的，不受你的 prompt 影响。
3. **流式响应里，搜索结果/引用只在最后一个（或几个）chunk 里出现**（文档原文，`sonar/features.md`："Search results and metadata are delivered in the final chunk(s) of a streaming response, not progressively"）。如果按"内容分片一样逐步到达"的假设去渲染引用列表，会长时间看到空列表。
4. **模型名对不上训练记忆**：当前 Sonar 系列只有 `sonar` / `sonar-pro` / `sonar-reasoning-pro` / `sonar-deep-research` 四个（来自 OpenAPI `enum`），**没有**单独的 `sonar-reasoning`（非 Pro 版本）。凭旧印象写 `sonar-reasoning` 大概率会拿到模型不存在的报错。
5. **`sonar-deep-research` 的计费结构和其他三个模型不一样**：它是唯一额外计"引用 token 费"（$2/1M）、"搜索查询费"（$5/1K 次查询）、"推理 token 费"（$3/1M）的 Sonar 模型，且搜索查询次数由模型自己决定，你无法精确控制，只能通过 `reasoning_effort` 间接影响。按"它只是更贵的 sonar-pro"估算成本会低估实际花费。
6. **结构化输出（`response_format.json_schema`）在两套 API 里同名字段的必填程度不同**：Sonar Chat Completions 的 `json_schema.name` 是可选的（默认值 `"schema"`）；Agent API 的 `json_schema.name` 是**必填**的（1-64 个字母数字字符）。照抄一边的请求体去另一边大概率漏字段。两边都提醒：**不要在 JSON schema 里定义一个"来源链接"字段指望模型可靠填对**——文档原文明确警告"Requesting links as part of a JSON response may not always work reliably"，链接一律从 `citations`/`search_results` 取。
7. **Agent API 里 Anthropic 模型必须显式传 `max_output_tokens`，否则 400**（文档原文：`validation failed: max_output_tokens is required when using Anthropic models`）。这是模型族特有的强制要求，不是 Agent API 的通用规则——OpenAI/Google/xAI 等其他模型不强制。
8. **`temperature`/`top_p` 对 GPT-5、o1、o3 系列模型在 Agent API 上是静默忽略的**（文档原文），不报错，只是不生效。这类"传了参数但服务端悄悄不执行"的行为在这套 API 里不止一处——`disable_search` 之于 Sonar 有效，但 Agent API 没有直接对应字段，且**给一个已经带 `preset` 的请求传 `tools: []` 并不会清空 preset 自带的工具**（文档原文：目前没有公开方法禁用 preset 自带工具，`max_tool_calls: 0` 是文档给出的"笨办法"变通）。
9. **日期过滤统一用 `MM/DD/YYYY` 字符串**（不是 ISO 8601 `YYYY-MM-DD`），Sonar、Search API、Agent API 的 `web_search` 工具三处一致。并且 `search_recency_filter`（相对时间窗，如 `"week"`）**不能和** `search_after_date_filter`/`search_before_date_filter`/`last_updated_*_filter`（精确日期）同时使用（文档原文，`search/filters/date-time-filters.md`）——想同时要"精确范围"和"相对窗口"是不支持的组合，混传的实际行为未文档说明，标 `⚠ 文档未说明`。
10. **域名过滤 allowlist/denylist 不能混用**：`search_domain_filter` 数组里的每一项要么全部不带 `-` 前缀（只搜这些域名），要么全部带 `-` 前缀（排除这些域名），最多 20 个条目。三处 API（Sonar 请求体顶层 / Agent API `web_search.filters` / Search API 请求体顶层）字段名相同，但挂载位置不同，详见 `references/search-controls.md`。
11. **Search API 的计费单位和限流单位不是同一回事**：一次请求最多传 5 条 `query`（数组），**计费按"1 次成功请求 = 1 个计费单位"**（$5/1000 次请求，与查询条数无关），但**限流按"每条 query = 1 个 rate-limit 单位"**计（50 query units/秒）。按请求数估算限流预算会低估实际消耗 5 倍（5 条查询的请求）。
12. **Embeddings 是未归一化向量**：`base64_int8` 编码必须用**余弦相似度**比较（不能用内积或欧氏距离），`base64_binary` 编码必须用**汉明距离**比较（文档原文警告）。套用"归一化向量随便用内积也一样"的通用直觉会得到错误的相似度排序。
13. **Search API 的 `POST /search` 路径下没有 `/v1` 前缀**，是本文档站里唯一一个不带版本前缀的核心端点，容易被复制粘贴其他端点时带错。

## 目录结构

```
perplexity/
├── SKILL.md
├── references/
│   ├── grounded-answers.md          # Sonar Chat Completions：请求/响应、流式、结构化输出、媒体附件、OpenAI 兼容
│   ├── agent-api.md                 # Agent API：presets vs 显式 model、web_search 等内置工具、流式、结构化输出、后台运行
│   ├── search-controls.md           # 域名/时间/语言/地理位置过滤，三套 API 的字段挂载位置对比
│   ├── search-api.md                # 独立 Search API：POST /search、多查询、人物搜索、计费/限流单位
│   ├── models.md                    # Sonar 模型族 + Agent API 模型目录 + Sonar→preset 映射表，成本-深度选型
│   └── errors-limits-pricing.md     # 各 API 定价明细、限流分级表、错误类型、Embeddings API 基本用法
└── evals/
    └── evals.json                   # 5 个"有经验的开发者会凭训练记忆或旧版 Perplexity API 写错"的场景（未验证，期望输出是假设）
```

内容整理自 `https://docs.perplexity.ai`（`llms.txt`/`llms-full.txt` 全站索引 + OpenAPI 规范，抓取于 2026-09-21）。**这份文档的抓取日期晚于本模型的训练截止日期（2026-01），Perplexity API 在此期间新增了 Agent API/Search API/Router API 并把 Sonar Chat Completions 标为过时路径，所以凭训练记忆写 Perplexity 代码本身就不可靠，务必读 reference 文件。** 实际调用报错优先信任 API 返回，其次信任本 skill 标了验证日期的结论，最后才是未标注来源的转录内容。
