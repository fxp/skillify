# tavily skill 验证计划（待真实 API Key）

现状：文档版，抓取于 2026-09-21，只做了对官方 OpenAPI 规范 + `llms-full.txt` 全站文档的交叉阅读，**没有发起过一次真实 API 调用**（没有 Key）。
以下按优先级列出拿到 Key 后要测的结论，对应 `tavily/SKILL.md`「跨领域通用规则」和各 reference 文件里的 `⚠` 标记。

测试原则：Key 只走环境变量 `TAVILY_API_KEY`，测完立即从 shell 历史/临时文件里清理；免费账号有 1,000 credits/月，P0/P1 全部是低成本只读调用，
优先用最短 query、`max_results` 尽量小、Extract/Crawl/Map 限制 `limit`，把消耗控制在个位数 credit；每条测试记录到 `verification-log.md`
（日期、endpoint、请求要点、原始响应片段、花费 credit），写回对应 reference 文件时按 `已用真实 API 验证（日期）：...` 格式标注证据。

## P0 —— SKILL.md 开头几件事 + 零成本/低成本只读，错了全盘皆错

| # | 结论 | 怎么测 | 判定 |
|---|---|---|---|
| 1 | `search_depth` 默认 `basic`，不传该参数直接生效 | `POST /search`，不传 `search_depth` | 观察 `content` 是否为分块格式（`[...]` 分隔） |
| 2 | ⚠ 文档矛盾：`max_results` 默认值到底是 10（OpenAPI/SDK）还是 5（Best Practices 页/CLI） | `POST /search`，不传 `max_results`，数 `results` 长度 | 更新 `search.md` §1，写清真实默认值 |
| 3 | `basic` 深度 2026-07 起返回多条分块（不是单条摘要） | 同上，检查 `results[].content` 里是否有 `[...]` 分隔符 | 确认/推翻 changelog 声称的行为 |
| 4 | `auto_parameters=true` 可能把 `search_depth` 静默升级为 `advanced`，多花 1 credit | `POST /search`，`auto_parameters: true` + `include_usage: true`，不传 `search_depth`，对比同一 query 显式传 `search_depth: basic` 的 `usage` | 对比两次 `usage.search_usage`/花费是否不同；响应里能否看到实际生效的 `search_depth`（`auto_parameters` 字段） |
| 5 | `include_raw_content` 不传时 `raw_content` 为 `null`/不返回 | `POST /search`，不传 `include_raw_content` | 检查响应里是否存在 `raw_content` 字段及其值 |
| 6 | Extract 对一个明显失效的 URL（如 `https://example.invalid/404-not-a-real-page`）返回 HTTP 200 + 空 `results` + 非空 `failed_results` | `POST /extract`，`urls` 全部传无效域名 | 确认状态码与两个数组 |
| 7 | Extract 对全部 URL 都格式非法（如空字符串）返回 400 | `POST /extract`，`urls: [""]` | 确认状态码和 `detail.failed_results` |
| 8 | `POST /research`（非流式）成功创建任务返回 201 | 提交一个 `model: mini` 的最简研究任务 | 检查状态码，记录 `request_id` |
| 9 | `GET /research/{id}` 在 pending/in_progress 时返回 202，完成后返回 200 | 紧接上一步轮询 2–3 次 | 记录每次轮询的状态码和 `status` 字段 |
| 10 | `include_domains_mode` 不设 `include_domains` 时返回 400 | `POST /search`，只传 `include_domains_mode: "restrict"` | 确认状态码和 `detail.error` |
| 11 | `filter_by_language` 不设 `language` 时返回 400 | 同上模式，只传 `filter_by_language: true` | 确认状态码 |
| 12 | Keyless header + 有效 Bearer key 同时传，以 Bearer 为准 | `POST /search`，同时带 `X-Tavily-Access-Mode: keyless` 和 `Authorization: Bearer` | 对比响应里能否看出走了哪条限流（如额度是否从账号扣） |

## P1 —— ⚠ 文档自相矛盾的裁决 + 中等成本

| # | ⚠ | 怎么测 | 判定 |
|---|---|---|---|
| 13 | `chunks_per_source` 在 `search_depth=basic` 下是否真的生效（changelog 说生效，CLI 文档暗示只对 fast/advanced 生效） | `POST /search`，`search_depth: basic`，`chunks_per_source: 1` vs `chunks_per_source: 3` | 对比 `results[].content` 长度/分块数是否随参数变化 |
| 14 | Search 场景 `chunks_per_source` 传 4 或 5（超过文档声称的上限 3）：报错还是静默截断到 3 | `POST /search`，`chunks_per_source: 5` | 记录状态码/实际返回分块数 |
| 15 | Extract/Crawl 场景 `chunks_per_source` 上限是否真的是 5（而不是和 Search 一样的 3） | `POST /extract`，带 `query` + `chunks_per_source: 5` | 记录实际返回分块数 |
| 16 | Crawl 组合计费公式（mapping + extraction 独立叠加）是否与文档示例一致 | `POST /crawl`，`limit: 10`，`extract_depth: basic`，`include_usage: true` | 对比 `usage` 里的 credit 消耗和文档给出的「10 页 basic = 3 credit」示例 |
| 17 | `instructions`/`extract_depth` 同时传时 Crawl 费用是否按两个乘数同时叠加（4 credit/10 页 mapping + 4 credit/10 页 extraction = 8？还是别的组合） | `POST /crawl`，同时传 `instructions` + `extract_depth: advanced`，`limit: 10` | 记录真实 `usage`，写回 `extract-and-content.md` §4 的 ⚠ 假设条目 |
| 18 | Python SDK 的 Map 方法名到底是 `map` 还是 `mapping`（正文和某处代码示例矛盾） | `python -c "from tavily import TavilyClient; print([m for m in dir(TavilyClient) if 'map' in m.lower()])"` | 安装 `tavily-python` 后直接检查，不需要网络调用 |
| 19 | JS SDK 参数是否真的接受 camelCase（如 `searchDepth`）还是只认 snake_case（`search_depth`） | `@tavily/core` 的 `client.search(query, { searchDepth: "advanced" })` vs `{ search_depth: "advanced" }` | 对比两种写法哪个真的改变了返回结果（如分块数/延迟） |
| 20 | `safe_search: true` 配合 `search_depth: "fast"` 或 `"ultra-fast"`：报错还是静默忽略 | `POST /search`，`search_depth: fast`，`safe_search: true` | 记录状态码；若不报错，检查响应里有无字段暗示该参数被忽略 |
| 21 | `include_usage` 在未达到最低计费门槛前是否真的显示为 0（Extract 未到 5 次成功、Map 未到 10 页成功） | `POST /extract`，`urls` 只传 1 个，`include_usage: true` | 检查 `usage` 字段的值 |
| 22 | Research 流式（`stream: true`）事件结构是否和文档给出的示例一致（`chat.completion.chunk` 包装、`tool_calls`/`sources`/`done` 事件） | `POST /research`，`model: mini`，`stream: true`，跑一个最简单的问题 | 记录真实 SSE 事件序列，更新 `research.md` §4 |

## P2 —— 需要付费方案 / 企业版权限，可能账号条件不满足则跳过并显式标注

| # | 结论 | 怎么测 | 判定 |
|---|---|---|---|
| 23 | `POST /logs`：免费账号返回 403，付费账号能拿到日志 | `POST /logs`，`limit: 5` | 记录真实状态码；若测试账号是免费档，直接记录「验证受限于账号档位」 |
| 24 | `POST /org-usage`：传团队/普通 Key 返回 403，必须 owner 个人 Key | `POST /org-usage`，`organization_name` 用测试组织真实名称 | 记录状态码和错误文案；无企业版权限时在 SKILL.md 标「未验证，账号非 Enterprise」 |
| 25 | `GET /usage` 响应字段（`key.*`/`account.*`）与 OpenAPI 描述一致 | `GET /usage` | 对比真实字段名和 `errors-and-limits.md` §5 的表 |
| 26 | `POST /feedback` 最小请求（只传 `session_id`）能否成功、`feedback_id` 格式 | `POST /feedback`，`session_id: "test-<uuid>"` | 记录响应，确认不计费（对比调用前后 `/usage`） |
| 27 | `/generate-keys`、`/deactivate-keys`、`/key-info` 三个企业版 endpoint 的真实请求体（OpenAPI 规范里没有这三个的 schema，纯靠叙述文档编的示例未必对） | 需要 Enterprise 权限，大概率无法测；如账号有权限，先用 `GET /key-info` 只读探测请求体形态 | 更新 `errors-and-limits.md` §7，标注真实字段名 |

## P3 —— MCP / CLI（需要额外安装，独立于 REST API 测试）

| # | 结论 | 怎么测 |
|---|---|---|
| 28 | 远程 MCP `tools/list` 真实返回的工具名（`tavily-search`/`tavily_search` 等命名、是否含 crawl/map/research/skill） | `claude mcp add tavily-remote-mcp --transport http https://mcp.tavily.com/mcp/`，连接后列出工具 |
| 29 | Keyless 远程 MCP（带 `X-Tavily-Access-Mode: keyless` header）是否真的免注册可用 | 同上，加 header，不配置任何 Key |
| 30 | CLI `tvly search` 的真实默认 `max_results`（呼应 P0 #2，交叉验证 REST 和 CLI 是否给出同一个数字） | `tvly search "test" --json \| jq '.results \| length'` |
| 31 | CLI `--chunks-per-source` 在 `--depth basic` 下是否真的生效（呼应 P1 #13） | `tvly search "test" --depth basic --chunks-per-source 2 --json` |

## 完成后

- 每条结论改回对应 reference 文件，写「已用真实 API 验证（日期）：传 X 返回 `{...}`」格式，附真实响应片段。
- ⚠ 文档自相矛盾的条目裁决后从「假设，待验证」改成「已验证：文档 A 对 / 文档 B 错」或「两处都不对，真实行为是 …」。
- 文档本身确认写错的地方（如果验证坐实），从 reference 深处升级到 `SKILL.md` 的「跨领域的通用规则」一节最前面，因为那一层永远加载。
- SKILL.md 顶部「⚠ 验证状态」按「已验证（日期、花费）/ 未验证」分区重写，不再是现在这种整体"文档版"的笼统说法。
- 验证完成后，按 `create-doc-skill` 方法论第 4 步补跑 with-skill / without-skill 对照实验，写 `tavily-workspace/comparison-report.md`（Markdown，参考本工作区 `CLAUDE.md` 的报告约定）。
