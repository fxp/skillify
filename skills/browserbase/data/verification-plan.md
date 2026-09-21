# Browserbase skill 验证计划

状态：**尚未开始**。本 skill 目前完全基于 https://docs.browserbase.com 与 https://docs.stagehand.dev 的文档转录（抓取于 2026-09-21），没有用真实 Browserbase API Key 调用过任何一个 endpoint，也没有跑过 Stagehand 的任何一行代码。本文件按优先级列出拿到 Key 后要验证的结论、用哪个 endpoint/操作、预期成本、怎么判定通过。

## 0. 账号与预算前提

- 免费版额度：1 浏览器小时/月、（⚠ 有矛盾，见下）1-3 并发、15 分钟单会话上限、0 GB 代理流量、CAPTCHA/Verified 均不可用。免费版基本够跑完第 1-3 优先级的只读探测；proxies/Verified 相关测试需要 Developer 及以上付费方案（$20/mo 起）。
- **在开始前，先读一遍本文件第 6 节「会话清理风险」**，每一步测试后立即检查 Sessions 列表页确认没有残留的 RUNNING 会话。

## 优先级 1：先确认鉴权与最基础的读写路径（最便宜，5 分钟内可做完）

| # | 要验证的结论 | 怎么测 | 预期成本 | 判定 |
| :-- | :-- | :-- | :-- | :-- |
| 1.1 | 鉴权 header 精确写法：`x-bb-api-key`，无 Bearer 前缀 | `curl -H "x-bb-api-key: $KEY" https://api.browserbase.com/v1/sessions` | 免费（只读列表） | 200 且返回会话列表 JSON；再故意传错 key，确认返回的状态码/错误体（目前完全没有文档证据，是 errors-and-limits.md 里明确写"未知"的一块） |
| 1.2 | `POST /v1/sessions` 空 body 创建会话成功，返回字段和 OpenAPI summary 一致（`id`/`connectUrl`/`seleniumRemoteUrl`/`status`/`expiresAt`/`keepAlive`/`region`/`proxyBytes`/`signingKey`） | `curl -X POST .../v1/sessions -d '{}'` | 约 1 分钟计费（1 分钟最低消费） | 响应字段名/类型和 sessions-rest.md 表一致；立刻 `REQUEST_RELEASE` 释放 |
| 1.3 | `POST /v1/sessions/{id}` 只接受 `status: REQUEST_RELEASE`（SKILL.md 通用规则第 7 条提到的文档矛盾） | 对同一个会话尝试 PATCH 其他字段（比如 `userMetadata`），看是被拒绝还是被静默忽略还是真的支持 | 同上 | 如果确实只支持 `status`，把 llms.txt 摘要里"或更新其他可变字段"这句标记为确认过时的错误文案；如果真支持其他字段，反过来更新 sessions-rest.md |
| 1.4 | Node SDK `@browserbasehq/sdk` 和 Python SDK `browserbase` 各跑一遍 30 秒示例代码（SKILL.md 里的那段） | `npm install @browserbasehq/sdk` + 跑示例 | 约 1-2 分钟计费 | 连接成功、`page.goto` 成功、能拿到 session 录像链接 |

## 优先级 2：SKILL.md 通用规则里标了 ⚠ 的具体行为（决定skill 可信度的核心）

| # | 要验证的结论 | 怎么测 | 预期成本 | 判定 |
| :-- | :-- | :-- | :-- | :-- |
| 2.1 | **5 分钟连接超时**：创建会话后故意等 6 分钟再连接，确认真的失败 | 创建会话，`sleep 360`，再 `connectOverCDP` | 约 5-6 分钟计费（这一项比较贵，可以用最短的超时配置降低成本，或干脆跳过、只做文档转录标注） | 连接失败，记录具体报错信息原文 |
| 2.2 | **10 分钟 CDP 空闲断连**：连上后不发任何命令，等 11 分钟，确认连接被断 | 连接后 `sleep 660`，再尝试操作 | 约 11 分钟计费（较贵，可选：先用小规模验证心跳机制本身是否真的能防止断连，而不必真等到 10 分钟阈值） | 确认断连行为，以及心跳（`page.evaluate(() => undefined)` 每 5 分钟一次）是否真的能续命 |
| 2.3 | **`connectUrl` 是否单次性**：非 keepAlive 会话，断开连接后用同一个 `connectUrl` 重连，是否失败 | 建一个不带 `keepAlive` 的会话，连接→主动断开（不调用 REQUEST_RELEASE，只是断开 WS）→重新用同一 URL 连一次 | 约 1-2 分钟 | 这是 SKILL.md 里标了"待验证"最重要的一条，直接决定 sessions-rest.md 里那条规则是否需要改写 |
| 2.4 | **keepAlive 会话断开重连**：`keepAlive: true`，断开后用同一个 `connectUrl` 重连是否成功 | 建一个 `keepAlive: true` 的会话，连接→断开→重连 | 约 2-3 分钟（keepAlive 期间持续计费，测完立刻 REQUEST_RELEASE） | 重连应成功；顺便确认"不显式释放就一直计费"这条 |
| 2.5 | **`solveCaptchas` 默认值确实是 true**：不传这个字段创建会话，访问一个已知有 CAPTCHA 的测试页（文档里提到的 `https://www.google.com/recaptcha/api2/demo`），确认控制台真的打印了 `browserbase-solving-started` | 建默认会话，`page.goto` 到该 demo 页，监听 console 事件 | 约 1 分钟 + CAPTCHA 解决耗时（5-30秒） | 确认事件确实触发；同时验证设 `solveCaptchas: false` 后不触发 |
| 2.6 | **Free 计划并发数矛盾**（1 还是 3）：如果测试账号是 Free 计划，直接开 2-3 个并发会话看第几个被拒绝 | 并行 `POST /v1/sessions` 三次 | 约 3 分钟（如果都成功） | 确认真实并发上限，回填 SKILL.md 第 7 条的矛盾说明，不要留着两个数字都可能对 |

## 优先级 3：Stagehand v4 的核心行为（比 REST 层贵，因为要跑真实模型推理）

| # | 要验证的结论 | 怎么测 | 预期成本 | 判定 |
| :-- | :-- | :-- | :-- | :-- |
| 3.1 | v4 API 形状：`browserbase.launch()` → `Stagehand.create({ browser })` → `stagehand.act(...)` 真的能跑通（不是文档笔误） | 跑 quickstart 示例（云端模式，需要一个模型 provider key 或依赖 Model Gateway） | 1 次 `act`/`extract`/`observe` 调用的 LLM 推理费用 + 约 1 分钟浏览器时长 | 三个原语都成功返回，字段名（`data`/`metadata.actionId`/`metadata.cache.status`）和 stagehand.md 一致 |
| 3.2 | **Model Gateway 免模型 key**：Browserbase 云端会话下不传 `model` 参数，确认 Stagehand 真的能自动选模型并完成一次 `act()`，不报"缺少模型 key"的错 | 同上，但故意不传任何 `model`/`apiKey` 给 `act()` | 同上 | 确认 Model Gateway 计费走 Browserbase key，不需要单独的 OpenAI/Anthropic key |
| 3.3 | **本地浏览器必须显式传模型 key**：用 `localBrowser.launch()` 且不传 model，确认真的报错而不是静默用某个默认模型 | 本地跑一次 quickstart，故意不传 `model` | 0（本地不计 Browserbase 分钟数，只有模型 API 花费，这里故意不传所以应该直接报错、无花费） | 确认这是硬报错，报错信息记下来 |
| 3.4 | Stagehand v4 是否仍有 `agent()` 方法（SKILL.md 里标了 `⚠ 文档未说明`） | 查 `@browserbasehq/stagehand` 包的 TypeScript 类型定义/API 文档，或直接试调 `stagehand.agent` | 0（先查类型定义即可，不需要真的跑） | 确认 v4 是否保留 `agent()`，回填 stagehand.md |
| 3.5 | server-side cache 的 `cache.status` 真的从 `MISS` 变成 `HIT` | 同一个 `act()` 指令连续调用两次，`cache: true` | 1 次 LLM 推理费用（第二次应该不产生新的推理费用，验证省钱是否属实） | 第二次响应 `metadata.cache.status === "HIT"` 且明显更快 |

## 优先级 4：Browserbase Agents（比 Stagehand 更贵，涉及完整自主循环，多步推理）

| # | 要验证的结论 | 怎么测 | 预期成本 | 判定 |
| :-- | :-- | :-- | :-- | :-- |
| 4.1 | `POST /v1/agents/runs` 创建 run，轮询到终态 | 用文档里的 Hacker News 示例任务跑一次 | 未知，Agents 是按次计费+背后浏览器分钟数两条线，具体多少钱建议先在 dashboard 上手动跑一次看账单再决定要不要用 API 再跑一次 | 确认 run 生命周期状态机（PENDING→RUNNING→COMPLETED 等）和轮询字段与文档一致 |
| 4.2 | Agents 的计费是否真的是"调用次数 + 浏览器分钟数"两条独立线 | 跑完 4.1 后去 usage/billing 页面核对 | 同上 | 确认账单明细里是否分别出现 Agents 额度消耗和 Sessions 分钟消耗 |

## 优先级 5：代理与网络限制（成本较高，涉及流量计费，且部分站点行为不稳定）

| # | 要验证的结论 | 怎么测 | 预期成本 | 判定 |
| :-- | :-- | :-- | :-- | :-- |
| 5.1 | `proxies: true` 走美国出口，1 MB 最低计费 | 建代理会话访问一个能回显 IP 的页面（如 httpbin.org/ip） | 约 1-2 MB 代理流量费用（需要 Developer 方案+） | 确认出口 IP 地区、确认账单里代理流量的计费粒度 |
| 5.2 | `allowedDomains` 只限制顶层导航，不拦 iframe/XHR（SKILL.md 里的推断） | 建一个 `allowedDomains` 限定单一域名的会话，导航到一个会加载跨域 iframe/XHR 的页面，观察是否真的没被拦 | 约 1 分钟 | 确认这条推断，不确认的话要改写措辞 |

## 6. 会话清理风险（每次测试后必做）

Browserbase 和很多云资源类平台一样，**"忘记关的会话会持续计费"**——尤其是本计划里 2.3/2.4 两步会故意创建 `keepAlive: true` 的会话或故意让连接超时/断开，这些会话不会自己在合理时间内停止计费（`keepAlive` 会一直跑到 6 小时上限）。每完成一批测试后：

1. 去 dashboard 的 Sessions 列表页（`https://www.browserbase.com/sessions`）确认没有 `RUNNING` 状态的残留会话。
2. 对任何还在跑的会话手动点击终止，或用 API `sessions.update(id, {status: "REQUEST_RELEASE"})` 批量清理。
3. 测试脚本本身也应该用 `try/finally` 保证异常退出时仍尝试释放（呼应 SKILL.md 通用规则第 1 条和 evals.json 场景 2）。
4. 涉及 Contexts 的测试（创建了新 Context）用完要么保留作为长期测试资产并记录 ID，要么显式 `DELETE /v1/contexts/{id}` 清理，不要在账号里留一堆孤立的测试 Context。
5. 测试完成后检查一次 `GET /v1/projects/{id}/usage`，把本轮测试的实际花费记进 `verification-log.md`（后续补充），供第 4 步"对照实验"参考真实成本量级。

## 完成后的下一步

1. 每验证一条，回到对应 reference 文件把 `⚠ 文档原文，未实测` 改写成带日期和证据的"已用真实 API 验证（日期）：..."。
2. 把本文件第 2 节里确认下来的矛盾结论（尤其是 2.3 connectUrl 单次性、2.6 免费版并发数）升级改写 SKILL.md 通用规则第 7 条。
3. 验证完成后，按 create-doc-skill 方法论第 4 步做 with-skill / without-skill 对照实验，场景直接复用 `evals/evals.json` 里已经写好的 5 个。
