# Agent API：统一的多提供商网页问答 + 工具入口

⚠ 本文件全部内容整理自官方文档与 OpenAPI 规范，未用真实 Key 调用验证。所有请求/响应示例标 `⚠ 文档原文，未实测`。

Agent API 是官方现在推荐的默认入口：一个 endpoint 访问 OpenAI/Anthropic/Google/xAI/Z.AI/Moonshot AI/NVIDIA 的模型，以及 Perplexity 自己的 `sonar` 模型；内置 `web_search`、`fetch_url`、`sandbox`（代码执行）、`people_search`、`finance_search`、MCP 远程服务器、自定义函数等工具；用 Open Responses 标准的请求/响应形状（`input` 进、`output` 数组出），不是 Sonar 的 `messages`/`choices`。

## 目录
- [Endpoint 与鉴权](#endpoint-与鉴权)
- [两种起步方式：preset vs 显式 model](#两种起步方式)
- [Web Search 工具](#web-search-工具)
- [其他内置工具（点名，不展开）](#其他内置工具)
- [流式响应](#流式响应)
- [结构化输出](#结构化输出)
- [后台运行（长任务）](#后台运行)
- [模型选择的族特有限制](#模型选择的族特有限制)
- [与 Sonar Chat Completions 的参数映射](#与-sonar-chat-completions-的参数映射)

## Endpoint 与鉴权

**Endpoint**: `POST https://api.perplexity.ai/v1/agent`
OpenAI Responses SDK 兼容别名：`POST https://api.perplexity.ai/v1/responses`（把 OpenAI SDK 的 `base_url` 设为 `https://api.perplexity.ai/v1`，`client.responses.create()` 会自动打到这条路径，行为等同 `/v1/agent`）。

其余端点：
- `GET /v1/agent/{id}` — 取回一个已创建的 response（快照）。**只有创建时 `store` 省略或为 `true` 的 response 能取回**；`store: false` 的会返回 404。
- `GET /v1/agent/{id}/files` / `GET /v1/agent/{id}/files/{file_id}/content` — 列出/下载 sandbox 工具产出的文件（`share_file` 工具投递的），按账号隔离。
- `POST /v1/agent/{id}/cancel` — 请求取消一个仍在运行的 response（异步生效，`200` 只表示"已收到取消请求"，需轮询确认终态）；取消一个已终结的 response 返回 `400`。
- `GET /v1/models` — 列出 Agent API 可用模型 id（OpenAI List Models 格式）。

**鉴权**: `Authorization: Bearer $PERPLEXITY_API_KEY`

**请求体唯一必填字段是 `input`**（string，用户的问题/任务描述）。`model`、`preset`、`profile` 都是可选的——不传任何一个的行为⚠ 文档未说明（可能有服务端默认 preset，未确认）。

## 两种起步方式

### 方式一：显式 `model`（裸模型，默认不联网）

```python
response = client.responses.create(
    model="openai/gpt-5.6-sol",
    input="Explain the difference between supervised and unsupervised learning."
)
print(response.output_text)
```

这条路径**不带任何工具**（响应里 `tools: []`），是纯 LLM 补全，没有搜索、没有引用。想要联网必须自己加 `tools`：

```python
response = client.responses.create(
    model="openai/gpt-5.6-sol",
    input="What were the binding obligations of Executive Order 14110?",
    tools=[
        {
            "type": "web_search",
            "search_context_size": "medium",
            "filters": {
                "search_domain_filter": [".gov"],
                "search_recency_filter": "month"
            },
            "user_location": {"country": "US"}
        }
    ],
)
```

### 方式二：`preset`（推荐起步方式，自带工具 + 引用规则）

```python
response = client.responses.create(
    preset="low",
    input="Summarize the core findings of the 'Attention Is All You Need' paper.",
)
```

Presets 是官方维护的"模型 + 系统提示词 + 工具 + 参数"打包，调用时用名字引用，官方后续优化会自动生效（除非你冻结成显式配置）。

| Preset | 适合 | 备注 |
|---|---|---|
| `fast` | 单一事实查询、定义、快速摘要 | 模型 `openai/gpt-5.6-luna`，`max_steps: 1`，`reasoning_effort: minimal`，`service_tier: priority`，工具仅 `web_search` |
| `low` | 日常研究问题、轻量多步查询 | 文档示例里解析出的模型是 `openai/gpt-5.1`，工具含 `web_search`+`fetch_url` |
| `medium` | 多跳浏览、跨多来源聚合 | — |
| `high` | 专家级推理、详尽信源覆盖 | 深度研究场景 |
| `xhigh` | 开放式 agentic 任务（跑代码、长工具链、边聚合边构建结果） | 带代码沙箱，最强也最贵 |
| `wide-research` | 批量构建有信源支撑的条目集合 | 见文档 `agent-api/wide-research.md`，本 skill 未展开 |

**⚠ 只有 `fast` preset 的完整配置本次抓取到了逐字段细节**（见文档"Current preset values"手风琴列表）；`low`/`medium`/`high`/`xhigh` 的具体模型/参数只从示例响应片段里反推了部分（如 `low` preset 的示例响应显示实际调用了 `openai/gpt-5.1`），不保证是当前生效的完整配置——preset 背后的模型会随官方优化迭代，**永远以 `response.model` 字段的真实返回值为准，不要硬编码 preset↔model 的映射去做自己的成本估算**，需要精确成本控制时用"冻结配置"（复制 preset 当前的具体字段值到你自己的请求，省略 `preset` 参数）。

**Sonar 模型 ↔ Agent API preset 的推荐迁移映射**（官方内部基准，文档原文，未注明数值来源方法论）：

| 原 Sonar 模型 | 建议改用的 preset | 说明 |
|---|---|---|
| `sonar` | `fast` | 单一事实/定义类查询 |
| `sonar-pro` | `low` | 日常研究问题 |
| `sonar-reasoning-pro` | `medium` | 多跳浏览与聚合 |
| `sonar-deep-research` | `high`（或追求最强用 `xhigh`） | 专家级/详尽研究，文档称通常单价还低于 `sonar-deep-research` |

## Web Search 工具

```json
{"type": "web_search", "search_context_size": "medium", "filters": {...}, "user_location": {...}, "max_results": 10, "max_tokens": 4000, "max_tokens_per_page": 1000}
```

| 参数 | 类型 | 说明 |
|---|---|---|
| `type` | string | 必须是 `"web_search"` |
| `search_context_size` | string | `low`/`medium`/`high`，控制检索 token 预算档位 |
| `filters` | object | 域名/时间/语言过滤，字段名与 Sonar 相同但挂在这里而非请求体顶层，见 `references/search-controls.md` |
| `user_location` | object | 挂在 tool 对象上，与 `filters` 平级（不在 `filters` 里面）——注意这和 Search API/Sonar 把它归进搜索选项的位置不完全一样，写代码前对照 `search-controls.md` 的挂载位置表 |
| `max_results` | integer | 1-50，单次调用收集结果数上限 |
| `max_tokens` / `max_tokens_per_page` | integer | 搜索上下文的 token 预算控制 |

**响应形状**：`web_search` 触发时，`output` 数组里会插入一个 `type: "search_results"` 的条目（在最终 `message` 条目之前），包含 `queries`（模型实际发出的检索词）和 `results`（`id`/`url`/`title`/`snippet`/`date`/`last_updated`/`source`）。`usage.tool_calls_details.search_web.invocation` 记录调用次数。

**⚠ 引用不是自动加标记的**：文档原文提示——是否在正文插入 `[1][2]` 这种方括号标记"取决于提示词"，需要显式要求（例如附加"Cite your sources inline using bracketed markers like `[1][2]`"）。**无论有没有标记，`search_results[].id`/`url` 才是权威来源**，不要用正文里有没有方括号来判断这次回答是否有据可查。

**定价**：`web_search` 按调用次数计费，$2.5 / 1000 次调用（= $0.0025/次），与模型 token 费用分开计。

**限流**：跟随 Agent API 请求本身的限流档位（见 `references/errors-limits-pricing.md`），没有独立的 `web_search` 限流。

## 其他内置工具

以下工具本 skill 只点名存在和一句话用途，字段表未展开（超出"网页问答/检索"核心场景，需要时读对应文档页）：

- **`fetch_url`**（`docs/agent-api/tools/fetch-url-content.md`）：抓取指定 URL 的内容，$0.0005/次调用。
- **`sandbox`**（`docs/agent-api/tools/sandbox.md`）：隔离容器里跑代码，按容器会话计费（$0.03/会话，一个会话覆盖 20 分钟活跃使用窗口，不是运行时长上限）；从沙箱内部发起的 SDK 检索按 $0.0025/次（与 `web_search` 同价）另计。
- **`people_search`**（`docs/agent-api/tools/people-search.md`）：查找专业人士/员工，$5/1000 次调用。
- **`finance_search`**（`docs/agent-api/tools/finance-search.md`）：结构化财务/市场数据，$5/1000 次调用。
- **MCP**（`docs/agent-api/tools/mcp.md`）：连接远程 MCP server 作为工具。
- **Connectors**（`docs/agent-api/tools/connectors.md`）：在 Project 里配置好的服务连接（Slack/GitHub/Datadog 等托管连接器）或自带 MCP server，按 connector ID 引用。
- **Custom Functions**（`docs/agent-api/tools/custom-functions.md`）：自定义函数，模型请求调用后你在本地执行并把结果回传。

## 流式响应

```python
stream = client.responses.create(
    preset="fast",
    input="Explain what a model card is.",
    stream=True
)
for event in stream:
    if event.type == "response.output_text.delta":
        print(event.delta, end="")
    elif event.type == "response.completed":
        print(event.response.usage)
```

流式协议是**类型化 SSE 事件**（`response.output_text.delta`、`response.completed` 等，具体事件类型清单本次抓取未完整列出，⚠ 文档未说明全集），不是 Sonar 那种"每个 chunk 都是一个完整 choices 对象、自己判断 delta 是否为空"的形态。迁移指南原文说 Agent API 流式"always emits typed SSE events with reasoning and tool activity as separate events, closest to Sonar's `concise` mode; there is no `full`-mode inline-metadata format"——如果你依赖 Sonar `stream_mode: "full"` 把元数据内联在同一个 chunk 里的行为，Agent API 没有对应模式。

## 结构化输出

```json
{
  "response_format": {
    "type": "json_schema",
    "json_schema": {"name": "your_schema_name", "schema": {...}}
  }
}
```

**`json_schema.name` 是必填字段**（1-64 个字母数字字符），这点和 Sonar Chat Completions 不同（Sonar 里 `name` 可选，默认 `"schema"`，见 `references/grounded-answers.md`）。`schema.required` 数组里列出的字段才是真正必填；没列进 `required` 的声明字段即使存在于 schema 里，输出中也可能是 `null`。行为在流式/非流式、`/v1/agent`/`/v1/responses` 两条路径下一致（文档原文明确说明）。首次用新 schema 同样有 10-30 秒首 token 延迟，机制与 Sonar 相同。

结构化输出**不限定于 Perplexity 自家模型**（迁移指南原文："structured outputs are not restricted to specific Perplexity models on the Agent API"）——第三方模型也能用，具体支持程度按各模型自身能力,⚠ 文档未说明是否所有列出的 Agent API 模型都 100% 支持。

## 后台运行

长任务（深度研究、重度 sandbox 工作）不要占着流式连接，改用后台模式：

```python
response = client.responses.create(
    model="openai/gpt-5.6-sol",
    input="Produce a competitive landscape report for the EV charging market.",
    tools=[{"type": "web_search"}, {"type": "sandbox"}],
    background=True,
)
while response.status in ("queued", "in_progress"):
    time.sleep(2)
    response = client.responses.retrieve(response.id)
```

后台任务是持久化的，客户端断连也会继续跑完；可以先用 `stream: true` 实时看，断线后用 `GET /v1/agent/{id}?stream=true&starting_after=N` 从序号 `N` 之后重连（只在"重连窗口"内有效，过期后 `400`，只能退回普通 `GET /v1/agent/{id}` 拿最终快照）。

Sonar 的异步 Chat Completion（`POST /v1/async/sonar`）在 Agent API 里对应的就是这个 `background: true` 模式，不是另一个独立 endpoint。

## 模型选择的族特有限制

- **Anthropic 模型（`anthropic/*`）必须传 `max_output_tokens`**，否则 `400`：`validation failed: max_output_tokens is required when using Anthropic models`。这是 `max_output_tokens` 这个通用字段在 Anthropic 模型上被强制要求，不代表其他模型也强制。
- **GPT-5/o1/o3 家族模型（含 `openai/gpt-5.6-sol` 等）静默忽略 `temperature`/`top_p`**：不报错，只是不影响生成结果。即使某个模型支持采样控制参数，把 `temperature` 设为 `0` 也不保证跨请求确定性输出（文档原文明确提醒）。
- **`service_tier`**：省略、或设为 `auto`/`default` 用默认处理；`flex`（0.5× token 单价，低优先级尽力而为）；`priority`（2× token 单价，高优先级，`fast` 是它的别名）。如果选中的模型（或 fallback 链里的每一个模型）不支持所选 tier，请求**不会报错**，服务端静默回退到默认处理并忽略 `service_tier`——响应里的 `service_tier` 字段反映实际生效的档位，不能假设它等于你传的值。
- **模型 fallback**：可以传 `models`（数组）而非单个 `model` 做故障转移链，见 `docs/agent-api/model-fallback.md`（本 skill 未展开字段表）。

## 与 Sonar Chat Completions 的参数映射

摘自官方迁移指南（`docs/agent-api/migrate-from-sonar/how-to.md`），照搬 Sonar 请求体到 Agent API 前先查这张表：

**直接对应（改名/挪位置）**：

| Sonar 参数 | Agent API 对应 |
|---|---|
| `search_domain_filter`、`search_recency_filter`、`search_*_date_filter`、`last_updated_*_filter` | 同名字段，挪进 `web_search` 工具的 `filters` |
| `web_search_options.search_context_size` | `web_search` 工具上的 `search_context_size`（不在 `filters` 里） |
| `web_search_options.user_location` | `web_search` 工具上的 `user_location`（不在 `filters` 里） |
| `num_search_results` | `web_search` 工具上的 `max_results` |
| `reasoning_effort` | `reasoning.effort` |
| `max_tokens` | 改名为 `max_output_tokens` |

**没有直接字段，要改用工具/模式**：

| Sonar 参数 | Agent API 变通方案 |
|---|---|
| `enable_search_classifier` | 提供 `web_search` 工具，让模型自己判断要不要搜索 |
| `disable_search` | 不传 `web_search` 工具即可；**但带 `preset` 的请求里 `tools: []` 不会清空 preset 自带的工具**，目前没有公开方式关掉 preset 内置工具，`max_tool_calls: 0` 是文档给出的强制变通（禁用所有工具调用） |
| `search_mode` | `web`（隐式默认）；`academic` 无直接等价，用 `web_search` + 域名过滤 + 提示词模拟；`sec` 用 `finance_search` 或按 SEC 来源过滤的 `web_search` |
| `search_type`（Pro Search） | 无直接等价：`"fast"` ≈ `fast` preset，`"pro"` ≈ `low` preset；或者对显式 `model` 设 `max_steps` 限制多步搜索轮数；没有 `"auto"` 分类器等价物 |
| `return_related_questions` | 用提示词要求模型在结尾给几个追问问题，可选配合结构化输出 |

**直接没有等价物，属于要砍掉重写的功能**：

- `search_language_filter` — 没有 Agent API 等价物。
- `stream_mode` — Agent API 流式固定是类型化事件（见"流式响应"一节），没有 `full` 内联模式。
- 图片结果全家桶（`return_images`、`num_images`、`image_domain_filter`、`image_format_filter`、`web_search_options.image_results_enhanced_relevance`）— 不支持，Agent API 不返回 `images`。
- 视频结果全家桶（`return_videos`、`num_videos`、`media_response`）— 不支持，Agent API 不返回 `videos`。

需要以上任一能力时，只能继续用 Sonar Chat Completions（`references/grounded-answers.md`），不要假设 Agent API 有等价参数只是名字不同。
