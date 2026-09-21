---
name: exa
description: 接入 Exa（exa.ai / docs.exa.ai）AI 原生语义搜索 API 的使用手册（文档版，未经真实调用验证）——涵盖 Search 搜索（auto/fast/instant/deep-lite/deep/deep-reasoning 六种模式、highlights/text/summary 内容抽取、outputSchema 结构化输出、Snapshot 历史快照）、Contents 取网页正文、已废弃的 findSimilar、Answer 问答、Exa Agent 研究型异步代理（list building、enrichment、Exa Connect 数据源）、认证与限流计费。当用户提到 "Exa" "exa.ai" "docs.exa.ai" "exa-py" "exa-js" "@exa-labs" "EXA_API_KEY" "Exa Agent" "Exa Search" "Exa Contents" "findSimilar" "Websets"，或要写代码调用上述任意能力、把 Exa 接入 agent/RAG 管线时，应主动使用本技能，不要凭训练记忆编参数名——Exa 的 API 在训练数据截止后有实质性变化（尤其是 search 的 type 参数不再是 neural/keyword），也不要套用 Google/Bing/Tavily/SerpAPI 等其他搜索 API 的接口习惯。
---

# Exa 接入指南

Exa 是一个面向 AI Agent 的语义搜索 API：核心是 `/search`（自然语言查询网页并可选抽取正文）、`/contents`（已知 URL 取正文/摘要）、`/answer`（问答+引用）、Exa Agent（`/agent/runs`，异步研究型代理，做 list building / 实体核查 / 富化）。本页只做分流与跨领域规则，字段表和示例在 `references/`。

## ⚠ 验证状态

**文档版：内容整理自 https://docs.exa.ai （经 307 跳转落在 https://exa.ai/docs ，抓取于 2026-09-21）+ 官方 OpenAPI 规范 `exa-spec.json`（`info.version: 2.0.0`），尚未用真实 API Key 调用验证。**

- 字段名、类型、必填、枚举值、默认值：来自官方 OpenAPI 规范（`components.schemas`），是当前流程里最权威的原始材料，但规范本身也可能滞后于线上真实行为。
- 请求/响应示例：来自文档站代码块或 OpenAPI 规范里的 `example`，全部标 `⚠ 文档原文，未实测`。
- 报错文案、错误码列表、限流数字：来自 `/docs/admin/error-codes` 和 `/docs/admin/billing` 页面转录，同样未实测，标 `⚠ 文档原文，未实测`。
- 本 skill **没有做任何真实 API 调用**，也没有做 with/without skill 的对照实验。`evals/evals.json` 里的期望输出是"文档说应该这样"的假设，不是已验证结论。
- 拿到真实 Key 后按优先级验证的清单见 `exa-workspace/verification-plan.md`。

## 用之前先确认 3 件事

1. **Base URL**：`https://api.exa.ai`。Websets 相关端点（列表建设/富化/监控/导入/webhook）在 `/v0/websets/*` 之下，是一个更庞大的独立产品面（39 个 endpoint），本 skill **未覆盖**，需要时读 https://docs.exa.ai/websets/api 。
2. **鉴权**：官方 OpenAPI 的 `securitySchemes` 同时列了两种方式且描述完全相同——`x-api-key: <key>` 请求头，或 `Authorization: Bearer <key>`。**但文档站里能看到的每一份示例代码（curl / Python / JS，覆盖 search、contents、answer、agent、batch 全部端点）无一例外用的是 `Authorization: Bearer $EXA_API_KEY`**，没有一处示例用 `x-api-key`。两种头是否能同时传、冲突时谁生效，文档未说明，⚠ 未实测——建议照抄文档示例，只用 `Authorization: Bearer`。Key 从 https://dashboard.exa.ai/api-keys 获取；两个官方 SDK（`exa-py`、`exa-js`）默认从环境变量 `EXA_API_KEY` 读取，无需手动设置 header。
3. **最容易选错的字段：`/search` 的 `type`**。它**不再是** `neural` / `keyword`（这是 Exa 早期、训练语料里最常见的写法）。当前 OpenAPI 规范里 `type` 的合法枚举值是 `instant` / `fast` / `auto`（默认）/ `deep-lite` / `deep` / `deep-reasoning`，规范里完全没有 `neural`/`keyword` 这两个值。传旧值会报错还是被静默忽略（进而回退到默认 `auto`）未实测，是本 skill 优先级最高的验证项，见下方跨领域规则第 1 条。

## 30 秒跑通第一个请求

最便宜、最常用的组合：`query` + `contents.highlights`（约 $0.007/次，10 条结果内）。

```bash
curl -s -X POST "https://api.exa.ai/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $EXA_API_KEY" \
  -d '{
    "query": "recent techniques for improving retrieval in RAG systems",
    "type": "auto",
    "contents": { "highlights": true }
  }'
```

```python
from exa_py import Exa  # pip install exa-py

exa = Exa()  # 从环境变量 EXA_API_KEY 读取
result = exa.search(
    "recent techniques for improving retrieval in RAG systems",
    type="auto",
    contents={"highlights": True},
)
for r in result.results:
    print(r.title, r.url, r.highlights)
```

⚠ 文档原文，未实测：以上响应结构与字段名来自 OpenAPI 规范 `example` 字段，未真实调用确认。

## 能力域导航

| 我想做什么 | 参考文件 | 涉及的核心 endpoint |
|---|---|---|
| 自然语言搜网页，拿排名结果+正文摘录，六种搜索模式（含 Deep Search 深度研究）、结构化输出、历史快照 | `references/search.md` | `POST /search` |
| 已经有 URL 列表，只想取正文/高亮/摘要/子页面；或者遇到旧教程里的"找相似链接"需求 | `references/contents-and-find-similar.md` | `POST /contents`、`POST /findSimilar`（已废弃） |
| 让 Exa 自己做检索+生成，直接拿一句话答案或带引用的摘要 | `references/answer.md` | `POST /answer`（也可通过 OpenAI 兼容的 `/chat/completions`，`model="exa"` 调用） |
| 长耗时的研究任务：建列表、富化联系方式、多跳核查、接第三方数据源（Fiber/Similarweb/Baselayer 等 Exa Connect） | `references/agent.md` | `POST /agent/runs` 及其轮询/SSE/取消/回放接口 |
| 鉴权格式、错误码、限流/并发、定价、SDK 安装 | `references/errors-and-limits.md` | 全端点通用 |

**本 skill 不覆盖**：Websets API（`/v0/websets/*`，列表建设+搜索+富化+监控+导入+webhook 的独立大产品面，39 个 endpoint，文档见 https://docs.exa.ai/websets/api ）；Monitors API（`POST /monitors`，定时跑 search 并推 webhook，见 https://docs.exa.ai/monitors/quickstart ）；Batch API（企业版功能，需联系销售开通，见 https://docs.exa.ai/batch/quickstart ）；x402/MPP 免 Key 按次付费通道；除 Python/JS 外的第三方框架集成（LangChain、LlamaIndex、CrewAI 等）。这几块在文档站里都是一级导航项，读者需要时应单独查文档，不要假设本 skill 的规则能直接套用。

## 跨领域的通用规则（写代码前必读）

以下每条都标了来源（OpenAPI 规范 / 文档正文），**全部未经真实调用验证**，是本 skill 认为最值得优先验证的"直觉陷阱"假设：

1. **`type` 参数的可选值已经整体换代**（来自 OpenAPI `SearchRequest.type` 的 `enum`）：`instant` / `fast` / `auto`（默认）/ `deep-lite` / `deep` / `deep-reasoning`。没有 `neural`、`keyword`、`useAutoprompt` 这些 Exa 早期 API 的经典参数。如果凭记忆或旧博客文章写 `type: "neural"`，⚠ 未实测传入非法枚举值时是 400 报错还是静默回退到 `auto`——这是 P0 验证项。
2. **`/search` 和 `/contents` 接受同一套内容选项（`text`/`highlights`/`summary`/`maxAgeHours`…），但嵌套位置完全不同**（文档原文用 `<Warning>` 专门强调过这一点）：`/search` 把它们包在 `contents: {...}` 对象里（`"contents": {"highlights": true}`）；`/contents` 没有这层包装，这些字段直接铺在请求体顶层，和 `urls`/`ids` 平级（`"urls": [...], "highlights": true`）。照抄一个端点的请求体结构去拼另一个端点大概率是错的。
3. **默认不返回正文**：`/search` 不传 `contents` 参数、或 `/contents` 不传 `text`/`highlights`/`summary` 中任意一个，响应里就只有 `title`/`url`/`publishedDate` 等元数据字段，没有 `text` 字段。很多人假设"搜索 API 默认应该带正文"。
4. **`POST /findSimilar` 已废弃**（OpenAPI 规范把它标为 `deprecated: true`，`description` 原文写"Deprecated: prefer `/search` with a query describing the source"）。这是 Exa 早期最知名的端点之一（"找相似网页"），训练语料里大量出现，但当前文档已建议改用 `/search` 并把源页面特征写进自然语言 query。详见 `references/contents-and-find-similar.md`。
5. **Agent API（`/agent/runs`）的错误响应结构和 Search/Contents/Answer 完全不同**：后三者是扁平结构 `{"requestId": "...", "error": "...", "tag": "INVALID_REQUEST_BODY"}`；Agent API 是嵌套结构 `{"error": {"type": "INVALID_REQUEST", "code": "INVALID_OUTPUT_SCHEMA", "message": "..."}}`。给所有端点复用同一个错误解析函数会在 Agent API 上读错字段（比如去读顶层 `error` 当字符串用，实际上它是个 object）。
6. **`resolvedSearchType` 字段文档自相矛盾**（⚠ 文档自相矛盾，留给真实调用裁决）：OpenAPI 规范里字段描述写"Deprecated legacy field. Current production responses may return an empty string; clients should not branch on this value."，`example` 给的是空字符串 `""`；但同一份规范里 `POST /search` 响应的顶层 `example`（也就是 API reference 页面展示的"示例响应"）却写的是 `"resolvedSearchType": "neural"`。不要用这个字段做分支判断，也不要相信随手抄来的"示例响应"里它一定有值。
7. **`contents.maxAgeHours`（`/search`）/ `maxAgeHours`（`/contents`）不是"发布时间过滤器"，是"缓存新鲜度阈值"**，语义容易搞反：省略＝优先用缓存、缓存没有才抓取；`0`＝总是抓新鲜页面；`-1`＝只用缓存，绝不抓取；正整数 N＝缓存若新于 N 小时则用缓存，否则抓取。想按发布时间筛结果要用 `startPublishedDate`/`endPublishedDate`，和 `maxAgeHours` 是两回事。已废弃的 `livecrawl`（`always`/`preferred`/`fallback`/`never` 四态字符串）仍能在旧教程里见到，文档给了到 `maxAgeHours` 的映射表，见 `references/search.md`。
8. **`numResults` 默认 10，公开上限 100，且 `/search` 不支持分页**（文档原文："Search does not support pagination"）。想要比 100 更多结果要联系销售开企业版，不能翻页拿第二批。
9. **`highlights`/`text`/`summary` 建议三选一**：文档原文"Pick one content view per request"——三者可以同时传，但会分别计费、分别返回，不是互斥校验，只是文档层面的成本建议，⚠ 未实测是否真的没有互斥校验。
10. **Exa Agent 的"异步"指的是默认立即返回 run 对象（`status: "queued"`），不是等跑完再返回**：`POST /agent/runs` 默认直接给你一个带 `id`（`agent_run_` 前缀）的 run 对象，必须轮询 `GET /agent/runs/{id}` 或在创建请求上加 `Accept: text/event-stream` 消费 SSE 事件流，才能拿到 `output.text`/`output.structured`。以为它像 `/answer` 一样同步返回结果会拿到一个空/未完成的 run。
11. **`POST /agent/runs` 在限流上按 2 次请求计费**（文档原文：`each run start counts as two requests`），而 `GET` 轮询状态/事件/列表不计入 QPS。按"起一个 run = 1 次调用"估算并发预算会低估实际 QPS 消耗。
12. **`category: "company"` 或 `"people"`（`/search`、`/findSimilar` 共用）会让部分过滤参数直接 400**：文档原文列出不支持的参数是 `startPublishedDate`、`endPublishedDate`、`excludeDomains`；混用会报错而不是被忽略。
13. **鉴权头未定论**：见上方"用之前先确认"第 2 条，`x-api-key` 和 `Authorization: Bearer` 两种写法文档同时列出但示例代码只用后者，是否等价、能否混用未实测。

## 目录结构

```
exa/
├── SKILL.md
├── references/
│   ├── search.md                       # POST /search：六种 type、内容选项、outputSchema、Deep Search、Snapshot
│   ├── contents-and-find-similar.md    # POST /contents；已废弃的 POST /findSimilar
│   ├── answer.md                       # POST /answer；OpenAI 兼容 /chat/completions
│   ├── agent.md                        # POST /agent/runs 及配套的轮询/SSE/取消/回放/Connect 数据源
│   └── errors-and-limits.md            # 鉴权、错误码、限流并发、定价、SDK
└── evals/
    └── evals.json                      # 5 个"有经验的开发者会凭 Exa 旧版 API 或通用搜索 API 直觉写错"的场景（未验证，期望输出是假设）
```

内容整理自 https://docs.exa.ai （llms.txt 索引 + OpenAPI 规范 `exa-spec.json`，`info.version: 2.0.0`，抓取于 2026-09-21）。**这份文档的抓取日期晚于本模型的训练截止日期（2026-01），Exa API 在此期间发生过至少一次大改动（`type` 参数从 neural/keyword 换成 auto/fast/instant/deep-*），所以凭训练记忆写 Exa 代码本身就不可靠，务必读 reference 文件。** 实际调用报错优先信任 API 返回，其次信任本 skill 标了验证日期的结论，最后才是未标注来源的转录内容。
