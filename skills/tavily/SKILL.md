---
name: tavily
description: 接入 Tavily（tavily.com / docs.tavily.com，专为 AI Agent / RAG 设计的搜索与内容 API）的 API 使用手册——涵盖 Search（实时网页搜索、search_depth 档位、话题 / 时间 / 域名 / 语言过滤）、Extract（按 URL 批量抽取干净正文，与 Firecrawl 的 scrape 概念上重叠）、Crawl 与 Map（站内图状发现与批量抽取，对标 Firecrawl 的 crawl/map）、Research（多步骤深度研究并生成带引用的报告，含流式输出）、Feedback / Usage / Logs / Enterprise Key 管理，以及 Python / JavaScript SDK、Tavily CLI、MCP、keyless 免密访问、x402 按次付费。当用户提到"Tavily""tavily-python""@tavily/core""tavily-mcp""tavily-cli""tvly""api.tavily.com"，或要写代码做 AI Agent 的实时联网搜索 / 网页抽取 / 整站爬取 / 深度研究时，应主动使用本技能，不要凭记忆编造参数名或默认值，也不要直接套用 Firecrawl、Serper、Bing Search、Google PSE 等其他搜索 / 抓取平台的接口习惯。
---

# Tavily 接入指南

Tavily 是专为 AI Agent 和 RAG 场景设计的搜索与内容 API：`/search` 做实时网页搜索、`/extract` 从已知 URL 批量抽正文、
`/crawl` + `/map` 做站内图状发现与批量抽取、`/research` 做多步骤深度研究并产出带引用的报告。
**本页只做分流与规则，字段表、curl/Python 示例在 `references/`。**

## ⚠ 验证状态

**文档版，抓取于 2026-09-21，未用真实 API Key 调用验证。** 本 skill 完全基于：

- 官方 OpenAPI 3.0.3 规范 `https://docs.tavily.com/documentation/api-reference/openapi.json`（全流程最权威材料，字段表、`required`、`minimum`/`maximum`、响应 schema 均来自这里）；
- `https://docs.tavily.com/llms-full.txt`（全站文档拼接，含 Best Practices、Changelog、SDK Reference、CLI、MCP、keyless、x402 等叙述性文档）。

**除标注"来自 OpenAPI 规范"的字段表外，所有报错文案、响应示例、行为描述都是文档原文，未实测**，请在文件里搜索 `⚠ 文档原文，未实测`。
本文档站更新非常活跃（截至抓取时的 changelog 最新条目在 2026-08：`include_domains_mode`、`language`/`filter_by_language`、`safe_search` 全面开放、
`search_depth=basic` 改为返回分块内容——均晚于多数模型的训练截止时间），**不要凭训练记忆写 Tavily 代码，字段名和默认值以这份 skill 或最新 OpenAPI 规范为准**。
拿到真实 Key 后按 `tavily-workspace/verification-plan.md` 补测，对照实验（with skill vs without skill）待真实调用到位后进行。

## 用之前先确认 3 件事

1. **Base URL 固定为** `https://api.tavily.com`（文档站 `docs.tavily.com`、控制台 `app.tavily.com`、MCP `mcp.tavily.com`、x402 `x402.tavily.com` 都是不同域名，不要混用）。
2. **鉴权精确格式**：`Authorization: Bearer tvly-YOUR_API_KEY`。**例外**：`POST /org-usage` 必须用组织 **owner 本人**的个人账号 key（`ownerBearerAuth`），传一个团队 / 企业级 key 会被拒绝——这是全平台唯一一个鉴权范围不同的 endpoint，见 `references/errors-and-limits.md`。
3. **最容易选错的字段**：`search_depth`（`basic`/`fast`/`advanced`/`ultra-fast`，费用和返回内容类型都不同）和 `extract_depth` / crawl 的 `extract_depth`（`basic`/`advanced`，同样影响费用），详见下方「跨领域通用规则」和 `references/search.md`。

## 30 秒跑通第一个请求

不需要 API Key（keyless，限流更严格，正式使用请换成真实 Key）：

```bash
curl -X POST https://api.tavily.com/search \
  -H "Content-Type: application/json" \
  -H "X-Tavily-Access-Mode: keyless" \
  -d '{"query": "Who is Leo Messi?", "max_results": 3}'
```

有 Key 时把 keyless header 换成 `Authorization: Bearer tvly-YOUR_API_KEY` 即可，响应 schema 完全一致。

## 我要做什么 → 读哪一份

| 我要做什么 | 读 | 核心 endpoint |
| :--- | :--- | :--- |
| 实时网页搜索、按话题 / 时间 / 域名 / 语言 / 国家过滤、拿 AI 生成的简短答案 | [`search.md`](references/search.md) | `POST /search` |
| 从已知 URL（一个或最多 20 个）批量抽取干净正文，判断和 Firecrawl `/scrape` 的选型边界 | [`extract-and-content.md`](references/extract-and-content.md) | `POST /extract` |
| 从一个起始 URL 出发整站爬取并抽正文，或只要 URL 清单不要正文 | [`extract-and-content.md`](references/extract-and-content.md) | `POST /crawl`、`POST /map` |
| 多步骤深度研究、生成带引用的报告或结构化 JSON、流式接收研究过程 | [`research.md`](references/research.md) | `POST /research`、`GET /research/{request_id}` |
| Python / JavaScript SDK 怎么装怎么用、Tavily CLI、MCP Server（含 keyless MCP）、x402 按次付费 | [`sdks-and-access.md`](references/sdks-and-access.md) | 无独立 REST endpoint（SDK 是对上面几个 endpoint 的封装） |
| 速率限制、Credits 计费明细、HTTP 错误码、账号用量查询、按请求查日志、企业版批量发 Key、意见反馈 | [`errors-and-limits.md`](references/errors-and-limits.md) | `GET /usage`、`POST /logs`、`POST /org-usage`、`POST /feedback`、`/documentation/enterprise/*` |

本 skill 覆盖 Tavily 的核心 REST API（`api.tavily.com` 下的 10 个 endpoint）与官方 Python/JS SDK、CLI、MCP。
**不覆盖**：具体框架集成教程（LangChain / CrewAI / Dify / n8n 等，文档在 `docs.tavily.com/documentation/integrations/*`，用法是把这里的 endpoint 包一层框架自带的 Tool 类，字段不变）、
Tavily Hybrid RAG（MongoDB 专用的本地 + 网络混合检索封装，仅 Python SDK 提供，见 `sdk/python/reference#tavily-hybrid-rag`，与核心 REST API 关系不大）、
官方 Agent Skills 仓库 `github.com/tavily-ai/skills`（那是 Tavily 自己发布的、通过 CLI 安装的一组 slash-command skill，和本 skill 是两回事，见 `sdks-and-access.md` 第 5 节的辨析）。

## 跨领域的通用规则（写代码前必读）

以下每条后面标的"⚠ 假设，待验证"是本 skill 基于文档提出的**未经真实调用证实的推测**，优先级见 `tavily-workspace/verification-plan.md`；
标"⚠ 文档自相矛盾"的是抓取时就发现的、文档内部或 OpenAPI 与叙述文档之间互相冲突的地方，孰是孰非同样待真实调用裁决。

1. **`search_depth` 同时决定延迟、返回内容形态和费用，四档不是线性关系。** `basic`/`fast`/`ultra-fast` 各 1 credit，`advanced` 2 credits（OpenAPI `search.md` 的
   `description` 字段明确给出）。`ultra-fast` 返回的是整页 NLP 摘要（"Content"），其余三档都返回可配置条数的相关性分块（"Chunks"，由 `chunks_per_source` 控制）。
   **2026-07 起 `basic` 也改成返回分块**（changelog），训练数据更旧的模型很可能还记得"`basic` 返回单条摘要"的旧行为，写代码或做选型建议时不要用这个旧印象。
2. **`auto_parameters=true` 可能悄悄把你升级到 `advanced`（2 credits），文档只在最佳实践页提了一句。** 官方原话："Note: `search_depth` may be automatically
   set to advanced when it's likely to improve results. This uses 2 API credits per request. To avoid the extra cost, you can explicitly set `search_depth` to `basic`."
   如果调用方只关心成本可预测性，`auto_parameters` 和显式 `search_depth` 二选一，不要两个都不设生怕"智能"帮你省钱。⚠ 假设，待验证：实测调用时这一升级是否会在
   响应里留下任何显式信号（`include_usage=true` 时 `usage` 字段能否看出实际用了几个 credit）。
3. **`content` 和 `raw_content` 不是"精简版"和"完整版"的关系，是两个默认行为完全不同的字段。** `results[].content` 一直都在，是（分块后的）摘要；
   `results[].raw_content` **默认不返回**，必须显式传 `include_raw_content: true`（或 `"markdown"`/`"text"`）才会出现，返回的是清洗后的完整页面内容。
   `extract`/`crawl` 的响应里则反过来：正文字段就叫 `raw_content` 且默认返回（因为 extract/crawl 本身的目的就是拿正文）。**跨 endpoint 套用字段名语义会出错**。
4. **Extract / Crawl 对失败 URL 从不收费，但 HTTP 200 不代表全部成功，必须检查 `failed_results`。** OpenAPI 对 `/extract` 200 响应的官方描述原文：
   "HTTP 200 can have an empty results array when all valid URLs fail during extraction; output order is not guaranteed." 只按状态码判断成功 / 失败会漏掉部分失败的情况。
5. **`/research` 的三个 HTTP 状态码不按常规 REST 习惯来，按状态码判断成功很容易踩坑。** `POST /research`（非流式）成功创建任务返回 **201**（不是 200）；
   `GET /research/{request_id}` 任务还在 `pending`/`in_progress` 时返回 **202**（不是 200）；只有任务 `completed` 或 `failed` 时才返回 **200**。
   写轮询逻辑时判断"完成"要看响应体里的 `status` 字段，不能只看状态码是不是 200。
6. **Crawl 的费用 = Map 部分 + Extract 部分两段独立计费，`instructions` 和 `extract_depth` 是两个互相独立的加倍开关。** 官方公式：
   `Crawl Cost = Mapping Cost + Extraction Cost`；不传 `instructions` 时 mapping 每 10 页 1 credit，传了变 2 credits／10 页；
   `extract_depth=basic` 时 extraction 每 5 次成功抽取 1 credit，`advanced` 变 2 credits／5 次。两个开关同时打开费用会叠加，不要只按其中一个估算。
7. **`chunks_per_source` 的取值上限因 endpoint 而不同：Search 是 1–3，Extract / Crawl 是 1–5。** 直接照抄 Search 的写法套到 Extract 上不会报错但拿不到第 4、5 块。
8. **`/org-usage` 要求组织 owner 的个人 key，不是任何一个组织成员的 key，也不是"企业版 key"。** 传错会收到 403
   "Please authenticate with the organization owner's personal API key, not an organization API key."，这是全平台唯一一个和其余 9 个 endpoint 鉴权范围不同的接口。
9. **`crawl` 和 `research`（任务创建）的速率限制不随开发 / 生产 key 升档，`search`/`extract`/`map` 才会从 100 RPM 跳到 1000 RPM。** `crawl` 开发和生产都固定 100 RPM，
   `research` 任务创建开发和生产都固定 20 RPM（轮询 `GET /research/{id}` 走默认限速）；从测试环境切到生产环境以为"限流自动放宽 10 倍"对这两个 endpoint 不成立。
10. **`safe_search` 在 `fast`/`ultra-fast` 深度下"不支持"，但文档没说是报错还是静默忽略。** ⚠ 文档未说明，这是"参数值和文档不一致时报错还是静默失效"这类最危险的坑，
    拿到 Key 后优先测（见 `verification-plan.md` P0）。
11. **文档自相矛盾：`max_results` 的默认值三处说法不一致。** OpenAPI 规范和 Python SDK Reference 都写默认 `10`；官方 Best Practices for Search 页原话是
    "Limits results returned (default: `5`)"；Tavily CLI 的 `--max-results` 选项表也写默认 `5`。⚠ 文档自相矛盾，实测以真实响应为准，见 `search.md` 第 1 节。
12. **文档自相矛盾：`chunks_per_source` 对 `basic` 深度是否生效，CLI 文档疑似落后于 2026-07 的改动。** Changelog 明确写"`chunks_per_source` now applies to
    `basic`"；但 CLI 命令参考里 `--chunks-per-source` 选项的说明仍写"requires `fast` or `advanced` depth"，只字未提 `basic`。⚠ 文档自相矛盾，CLI 文档可能没跟上后端改动。
13. **Feedback（`POST /feedback`）不消耗 credits，但是 Beta 状态，官方建议异步发送、失败不阻塞主流程。** 不要把它当成关键路径上的强依赖。
14. **Logs（`POST /logs`）和 org-usage 都要求付费方案（Paid Plan 或 PAYGO），免费账号调用返回 403。** 免费额度账号写这两个接口的代码前先跟用户确认账号档位。
15. **凭证只走环境变量**（示例统一用 `TAVILY_API_KEY`），不要硬编码；参考 `references/errors-and-limits.md` 的 API Key Management 一节（泄漏后立即撤销 + 轮换）。

## 目录结构

```
tavily/
├── SKILL.md                      # 本文件：路由 + 跨领域通用规则
├── references/
│   ├── search.md                 # POST /search 全部参数、过滤、auto_parameters、Best Practices
│   ├── extract-and-content.md    # POST /extract、/crawl、/map，含 Firecrawl 选型对照
│   ├── research.md               # POST /research、GET /research/{id}、流式 SSE
│   ├── sdks-and-access.md        # Python/JS SDK、CLI、MCP（含 keyless MCP）、x402、Session/Project 追踪
│   └── errors-and-limits.md      # 鉴权、速率限制、Credits 计费、HTTP 错误码、usage/logs/org-usage/feedback、企业版 Key 管理
└── evals/
    └── evals.json                # 第 4 步的对照场景（打包时自动排除）
```

内容整理自 `https://docs.tavily.com/documentation/api-reference/openapi.json`（OpenAPI 3.0.3）与
`https://docs.tavily.com/llms-full.txt`（抓取于 2026-09-21）。**实际调用报错、返回字段、默认值一律优先信任 API 的真实响应**，
文档（包括这份 skill）之间互相矛盾的地方已在上面逐条列出，裁决方法见 `tavily-workspace/verification-plan.md`。
