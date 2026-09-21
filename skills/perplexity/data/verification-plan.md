# perplexity skill 验证计划（待真实 API Key）

现状：文档版，抓取于 2026-09-21（`https://docs.perplexity.ai`，`llms.txt` + `llms-full.txt` 全站 197 篇 + OpenAPI 规范 `openapi.json`/`openapi-gateway-chat.json`/`openapi-auth.json`），依据文档 Markdown 源页 + 规范整理，**没有做过任何真实 API 调用**，也没有跑 with/without skill 对照实验。

测试原则：Key 只走环境变量，不写入任何文件；每条结论改回对应 reference 时按固定格式写"已用真实 API 验证（日期）：传 X 返回 `{...}`"；测试产生的 sandbox 会话、Agent response（`store: true` 的）用完即可不必强制清理（Perplexity 没有文档提及的"删除 response"接口，⚠ 待确认是否存在），但要避免反复触发 `sandbox` 工具（$0.03/会话，容易滚雪球）；每次调用记录到 `verification-log.md`（日期、endpoint、请求要点、原始响应片段、花费）。

## P0 —— SKILL.md"先确认的 4 件事" + 本 skill 标为最高优先级的假设（低成本，优先测）

| # | 结论/假设 | 怎么测 | 预期成本 | 判定 |
|---|---|---|---|---|
| 1 | `Authorization: Bearer <key>` 能调通 `POST /v1/sonar` | 最小请求（`model: "sonar"` + 单条 user message） | ~$0.005 | 200 + `choices[0].message.content` |
| 2 | Agent API 裸 `model` + 无 `tools` 确实不联网、不产生引用 | 用同一个问题分别调（a）`model` 无 tools、（b）`model` + `tools: [{"type":"web_search"}]`，对比 `output` 是否出现 `search_results` 条目 | ~$0.01 | (a) 无 search_results 条目；(b) 有——这是 SKILL.md 第一条跨领域规则，必须先验证掉 |
| 3 | Agent API 引用标记 `[1][2]` 是否真的"取决于提示词"，不加提示要求时是否完全不出现 | 复用 #2 的 (b) 请求但不在 prompt 里要求引用格式，检查 `output_text` 里有无方括号标记 | 复用 #2 | 记录实际是否出现标记；若默认就有标记，SKILL.md 第 2 条通用规则要改措辞 |
| 4 | Sonar 流式响应的 `search_results`/`citations` 确实只在最后一个/几个 chunk 出现 | `stream: true` 调一次 Sonar，逐 chunk 打印是否含非空 `search_results` | ~$0.005 | 记录 `search_results` 首次非空出现在第几个 chunk（应该是最后） |
| 5 | Agent API 流式（typed SSE events）是否也有类似"元数据延迟到达"的行为，事件类型全集是什么 | `stream: true` 调一次 Agent API（preset 或带 web_search 工具），记录所有出现过的 `event.type` | ~$0.01 | 补全 `agent-api.md`"流式响应"一节里标注为"⚠ 文档未说明全集"的事件类型清单 |

## P1 —— evals.json 5 个陷阱场景对应的裁决项

| # | 陷阱 | 怎么测 | 预期成本 | 判定 |
|---|---|---|---|---|
| 6 | eval #3：Anthropic 模型缺 `max_output_tokens` 真的 400 | 调一次 `model: "anthropic/claude-haiku-4-5"`（最便宜的 Anthropic 模型）不传 `max_output_tokens` | ~$0（应该 400，未消耗 token；若非 400 需确认是否计费） | 记录原始错误体，和文档转录的错误文案逐字对比 |
| 7 | eval #4：`search_recency_filter` + 精确日期过滤器同时传的真实行为 | 调 Search API，同时传 `search_recency_filter: "week"` 和 `search_after_date_filter`/`search_before_date_filter` | ~$0.005（1 次请求） | 确认是 400、还是忽略其中一个（哪个）、还是两者都生效取交集——这类"参数组合的实际语义"文档没写，是本 skill 目前标注最多的空白之一 |
| 8 | eval #5：`sonar-reasoning`（无 Pro）作为 model 传入的真实报错 | 调 `POST /v1/sonar`，`model: "sonar-reasoning"` | ~$0（应报错） | 确认是模型不存在的 400/404，记录精确错误码和文案 |
| 9 | `sonar-deep-research` 的实际计费明细（引用 token/搜索查询/推理 token 是否真的分别出现在 `usage`） | 用一个需要多步搜索的问题调一次 `sonar-deep-research`（预算一次即可，成本较高） | 参考文档定价预估 ~$0.05–0.2（视搜索轮次而定，需设置合理的最大预算防止失控） | 核对 `usage.citation_tokens`/`usage.num_search_queries`/`usage.reasoning_tokens`/`usage.cost.*` 是否都非 null 且和账单一致 |

## P2 —— 影响成本估算但优先级略低的项

| # | 结论 | 怎么测 | 预期成本 | 判定 |
|---|---|---|---|---|
| 10 | Search API 计费单位（1 请求）与限流单位（每 query 1 单位）分离，多查询请求账单确认 | 发一次带 5 个 query 的多查询请求，检查控制台账单增量 | ~$0.005（按文档 1 计费单位算） | 确认账单只增加 1 个计费单位，不是 5 个 |
| 11 | Search API `search_context_size` 默认值确实是 `"high"`（与 Sonar/Agent API 的 `"low"` 不同） | 调一次 Search API 不传 `search_context_size`，对比传 `"low"` 和不传的响应内容长度/token 消耗差异 | ~$0.01（2 次请求） | 若不传时内容量明显更大，佐证默认是 high |
| 12 | Embeddings 向量确实未归一化，需要余弦相似度而非内积 | 对两段已知语义相近/不相关的文本调 `pplx-embed-v1-0.6b`，手算内积 vs 余弦相似度排序是否一致 | ~$0（$0.004/1M token 级别，几乎免费） | 确认两种度量方式排序是否有实际差异（若向量本身接近归一化，差异可能很小，需要多组样本） |
| 13 | Agent API `service_tier` 不支持时静默降级（不报错） | 对一个不支持 `flex`/`priority` 的模型传 `service_tier: "priority"` | ~$0.005 | 确认请求成功且响应 `service_tier` 字段反映实际生效档位（应为默认值而非请求值） |
| 14 | preset 带 `tools: []` 是否真的不清空内置工具 | 用 `preset: "low"` + `tools: []` 调一次，检查响应里 `tools` 字段和 `output` 有无 search_results | ~$0.01 | 确认工具是否依然被调用；若确实无法关闭，佐证 SKILL.md 第 8 条规则；同时测 `max_tool_calls: 0` 变通是否真的完全禁用工具调用 |

## P3 —— 低优先级/需要额外条件，暂不强求

| # | 项目 | 备注 |
|---|---|---|
| 15 | Sandbox 工具（$0.03/会话）完整生命周期 | 涉及持续计费的容器会话，先用最小任务测通再决定是否深入 |
| 16 | Wide Research / Skills（server-side skill 上传）/ Connectors（托管连接器） | 超出本 skill"网页问答/检索"核心场景，暂不纳入本轮验证 |
| 17 | Contextualized Embeddings 完整字段表 | 本 skill 未展开具体请求体形状，需要文档分块检索场景时再补 |
| 18 | Analytics API（组织级用量查询） | 需要 org admin 权限生成的专属 analytics key，测试账号可能没有 |
| 19 | Router API 的模型目录与故障转移细节 | 与"网页问答/检索"关系较弱，本 skill 目前只提了一句用途 |
| 20 | Perplexity Search SDK（"Search as Code"）、CLI（`pplx`）、官方 MCP Server | 都是文档站一级导航项但超出本 skill 范围，暂不展开 |

## 完成后

- 每条结论改回对应 reference 文件，写「已用真实 API 验证（日期）：传 X 返回 `{...}`」；文档本身的错误同时升到 `SKILL.md`"跨领域的通用规则"一节。
- `SKILL.md`"⚠ 验证状态"从"文档版，未验证"改成分区写清"已验证 / 仍是文档转录"，参照 `firecrawl`/`fxiaoke` 等既有 skill 的写法。
- 跑 `evals/evals.json` 的 5 个场景做 with/without skill 对照（子 Agent 各写一版代码，用本计划里验证过的真实报错去判两版代码能不能在生产环境跑通），写 `perplexity-workspace/comparison-report.md`（Markdown，按本工作区 `CLAUDE.md` 的约定，不生成 HTML/Artifact）。
- 全仓库 `grep` Key 前 8 位，确认没有残留。
