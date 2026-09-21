# 选模型：Sonar 系列、Agent API 多提供商目录、presets

⚠ 本文件全部内容整理自官方文档与 OpenAPI 规范，未用真实 Key 调用验证。定价数字抓取于 2026-09-21，官方文档注明"pricing rates are updated monthly"，使用前建议对照 `/docs/getting-started/pricing` 原文确认未过期。

## Sonar 模型族（Sonar Chat Completions / 也可在 Agent API 里当作 `perplexity/sonar` 模型使用）

| 模型 | 上下文长度 | 定位 | Input（$/1M tok） | Output（$/1M tok） | 其他计费项 |
|---|---|---|---|---|---|
| `sonar` | 128K | 快速问答、单一事实查询 | $1 | $1 | 仅请求费（按 search context size 档位，$5/$8/$12 每 1000 请求） |
| `sonar-pro` | 200K | 进阶搜索，支持 Pro Search 多步工具调用 | $3 | $15 | 请求费 $6/$10/$14 每 1000 请求（`fast` 档）；Pro Search（`search_type: "pro"`）请求费涨到 $14/$18/$22 每 1000 请求，token 单价不变 |
| `sonar-reasoning-pro` | 128K | 复杂多步推理 | $2 | $8 | 请求费 $6/$10/$14 每 1000 请求 |
| `sonar-deep-research` | 128K | 详尽研究工作流，模型自主决定搜索轮次 | $2 | $8 | **额外三项**：引用 token $2/1M、搜索查询 $5/1K 次、推理 token $3/1M——见下方"成本陷阱"一节 |

⚠ **没有独立的 `sonar-reasoning`（非 Pro）模型**——OpenAPI 规范里 `POST /v1/sonar` 的 `model` 字段枚举值就是这四个（`sonar`、`sonar-pro`、`sonar-deep-research`、`sonar-reasoning-pro`），训练数据里可能存在的"sonar-reasoning"命名已经不是当前有效模型名。

**成本陷阱：`sonar-deep-research` 不是"更贵一点的 sonar-pro"，是完全不同的计费形状**。它是唯一会产生引用 token 费、搜索查询费、推理 token 费这三项额外计费的 Sonar 模型；搜索查询次数由模型自主决定（`reasoning_effort` 只能间接影响，不能精确控制），意味着同一个 prompt 两次调用的实际花费可能不同。做批量任务前该模型的成本估算不能用"单价 × 预期 token 数"简单外推，要留出查询次数波动的余量。

**Pro Search（仅 `sonar-pro`）**：通过 `web_search_options.search_type` 控制——`fast`（默认，标准行为）/ `pro`（多步工具调用，适合复杂查询，但按上表涨价）/ `auto`（模型自动判断复杂度分类）。⚠ 文档原文提示 Pro Search 要求 `stream: true`，具体是"强制要求"还是"仅推荐"未明确说明。

## Agent API 模型目录（多提供商，直接对接一手厂商定价，无加价）

Agent API 通过统一接口访问以下厂商模型，`pricing rates are updated monthly` 且"reflect direct first-party provider pricing with no markup"。以下摘录部分代表性型号，完整列表和最新价格见 `/docs/agent-api/models`：

| 提供商 | 代表模型（举例） | Input（$/1M） | Output（$/1M） | 备注 |
|---|---|---|---|---|
| Anthropic | `anthropic/claude-opus-5`、`claude-sonnet-5`、`claude-haiku-4-5` | 5.00 / 2.00 / 1.00 | 25.00 / 10.00 / 5.00 | **必须传 `max_output_tokens`，否则 400**（见 `references/agent-api.md`） |
| OpenAI | `openai/gpt-5.6-sol`（flagship）、`gpt-5.6-terra`、`gpt-5.6-luna`（最小/最快，`fast` preset 用的就是它） | 5.00–0.20（按尺寸分层，超 272K 上下文涨价） | 30.00–1.20 | 支持 `flex`/`priority` service tier |
| Google | `google/gemini-3.1-pro-preview`、`gemini-3.5-flash`、`gemini-3.5-flash-lite` | 2.00–0.25 | 12.00–1.50 | — |
| xAI | `xai/grok-4.6`、`grok-4.5`、`grok-4.20-*`（reasoning/non-reasoning/multi-agent 三个变体） | 1.25–2.00 | 2.50–6.00 | — |
| Z.AI | `perplexity/glm-5.3`、`glm-5.3-flash` | 1.40 / 0.15 | 4.40 / 0.50 | 注意模型 id 前缀是 `perplexity/` 不是 `zai/` |
| Moonshot AI | `perplexity/kimi-k3`、`kimi-k2.7-code` | 3.00 / 0.95 | 15.00 / 4.00 | Kimi K3 支持 `minimal`/`low`/`medium`/`high`/`xhigh`/`max` 六档 reasoning effort |
| NVIDIA | `perplexity/nemotron-3-ultra-550b-a55b` | 0.25 | 2.50 | 开放权重推理模型 |
| Perplexity | `perplexity/sonar` | 0.25 | 2.50 | **注意**：这个价格是 Agent API 里把 Sonar 当普通 model 用的 token 单价，和"Sonar Chat Completions 直接调 `sonar` 模型"的 $1/$1 定价不是同一回事——Agent API 场景下搜索是单独的 `web_search` 工具调用费（$2.5/1000 次），不含在这个 token 单价里；两条路径最终总花费不能直接对比单价高低，要按各自的完整计费公式各自估算 |

**Service tiers**（部分模型支持，非默认）：`flex`（0.5× token 单价，低优先级）；`priority`（2× 单价，高优先级，别名 `fast`）；省略或 `auto`/`default` 用标准处理。模型不支持所选 tier 时**静默降级**为默认处理，不报错。

## Presets：不想自己选模型时的默认路径

见 `references/agent-api.md` 的完整说明。速查表：

| Preset | 场景 |
|---|---|
| `fast` | 单一事实、定义、快速摘要 |
| `low` | 日常研究问题、轻量多步 |
| `medium` | 多跳浏览、跨源聚合 |
| `high` | 专家级推理、详尽信源覆盖 |
| `xhigh` | 开放式 agentic 任务（含代码沙箱） |
| `wide-research` | 批量构建有信源支撑的条目集合 |

Sonar → preset 的官方迁移映射：`sonar→fast`、`sonar-pro→low`、`sonar-reasoning-pro→medium`、`sonar-deep-research→high`（或更强用 `xhigh`）。

## 选型速查

- **只要 OpenAI 兼容、简单、便宜的网页问答，不关心用哪家模型**：Sonar `sonar` 或 Agent API `fast` preset。
- **要多家前沿模型可选（换模型对比效果、绑定某个厂商的特定能力）**：Agent API 显式 `model`，自己加 `web_search` 工具。
- **要"帮我把整个研究做完"（多轮搜索+推理+整合），不想自己编排**：Agent API 的 `medium`/`high`/`xhigh` preset，或 Sonar 的 `sonar-reasoning-pro`/`sonar-deep-research`——但后者成本结构更复杂（见上）。
- **要图片/视频检索结果**：只能用 Sonar Chat Completions，Agent API 不支持。
- **要精确控制搜索行为的每个细节（域名/语言/日期/结果数）又要 LLM 生成答案**：Sonar 或 Agent API 显式 `model` + `web_search` 工具（带完整 `filters`），不要用 preset（preset 的工具配置是固定的，自定义空间更小,虽然仍可通过传入同名字段覆盖 preset 默认值）。
- **只要检索结果，自己接自己的 LLM/管线**：Search API。

## 与 Router API 的关系（不展开）

Router API（`POST /router/v1/chat/completions` 等，OpenAI/Anthropic 兼容网关）提供 Perplexity 托管的**开放权重模型**（如 `perplexity/kimi-k3`）访问，主打"一个 endpoint 统一多个开源模型 + 自动路由和故障转移"，和 Agent API 的"多厂商一手模型 + 内置搜索/工具"是两条不同的产品线——Router 不内置网页搜索能力,是纯推理网关。本 skill 聚焦"网页问答/检索"场景，Router API 的完整模型目录和路由策略未展开,需要时读 `/docs/router/quickstart` 和 `/docs/router/models`。
