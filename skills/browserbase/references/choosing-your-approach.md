# 该用哪一层：REST+Playwright / Stagehand / Browserbase Agents / Search / Fetch

> ⚠ 本文件整理自 https://docs.browserbase.com（抓取于 2026-09-21），**未使用真实 API Key 验证**。所有行为描述都是文档转录，不是实测结论。

Browserbase 现在自称 "the Browser Agent Platform"，一个 API Key 下挂了五种能力：**Browsers**（原始会话）、**Agents**（托管自主 agent）、**Stagehand**（嵌入你代码里的自然语言库）、**Search**、**Fetch**、以及 **Model Gateway**。这些能力互相重叠，选错一层不会报错，只会导致要么贵得离谱、要么脆得离谱。本文件就是帮你在写代码前先做选型。

## 目录

- [三层浏览器自动化：REST 会话 / Stagehand / Browserbase Agents](#三层浏览器自动化reston-会话--stagehand--browserbase-agents)
- [先问：要不要浏览器？Search → Fetch → Browsers](#先问要不要浏览器search--fetch--browsers)
- [组合模式](#组合模式)
- [反直觉的地方](#反直觉的地方)

## 三层浏览器自动化：REST 会话 / Stagehand / Browserbase Agents

这是本 skill 覆盖范围里最核心的选型问题。官方博客把它定义为 **risk vs scale（风险 vs 规模）的权衡轴**（⚠ 文档原文引用自 use-cases/agents.md 链接的博客标题，正文内容未展开抓取，以下表格是文档站正文给出的三档）：

| 你在谱系哪个位置 | 长什么样 | 用什么 | 参考文件 |
| :--- | :--- | :--- | :--- |
| 脚本掌控整个流程，AI 只处理单个步骤 | 确定性代码 + 自愈式的 `act`/`extract` 调用 | Stagehand | [`stagehand.md`](stagehand.md) |
| 脚本把"难的那几步"甩给 agent | 脚本做骨架，遇到需要推理的步骤调用一次 agent | Stagehand + Agents 混用 | [`stagehand.md`](stagehand.md) + 本节下方 Agents 部分 |
| Agent 掌控整个循环，你只要结果 | 给一句自然语言目标，全自动跑完 | Browserbase Agents | 本节下方 |

**判断原则**（⚠ 文档原文）：一次点错的代价如果是钱或审计失败，就该用确定性脚本（REST + Playwright/Puppeteer/Selenium，见 [`sessions-rest.md`](sessions-rest.md)）；如果你根本没法提前穷举站点/布局/流程，脚本化就是打不赢的仗，该用 agent。

### 1. 原始 REST 会话 + 你自己的自动化库（Playwright / Puppeteer / Selenium）

**什么时候用**：你能提前写死选择器和流程；需要最低延迟、最低单次调用成本、完全可预测的执行路径；或者你已经有一套 Playwright/Selenium 测试/爬虫代码，只是想换成 Browserbase 的云端浏览器而不改自动化逻辑。

**代价**：站点改版、弹窗、验证码之外的动态变化都会直接断你的选择器；没有"自愈"能力。

详见 [`sessions-rest.md`](sessions-rest.md)。

### 2. Stagehand：自然语言驱动，但循环还是你自己写

**什么时候用**：你想要确定性的整体控制流（明确知道下一步该干什么），但每一步的具体选择器/操作交给模型去找，这样页面小改版不会直接断你的脚本。Stagehand 的 `act`/`observe`/`extract` 是**单步原语**，不是自主循环——你的代码仍然决定"先做 A 再做 B 再做 C"。

**代价**：每个 `act()`/`extract()`/`observe()` 调用都可能触发一次 LLM 推理（除非命中 server-side cache 或你把 `observe()` 的结果直接回放进 `act()`），比纯脚本慢、比脚本贵；仍然需要你写控制流代码。

详见 [`stagehand.md`](stagehand.md)。

### 3. Browserbase Agents：完全托管的自主 agent

**什么时候用**：你连"下一步该干什么"都不想自己写——只想给一句自然语言目标（`task`）和一个可选的 `resultSchema`，让 Browserbase 在服务端跑完整个循环（模型调用、工具使用、浏览器会话、Search、文件、shell，都在 Browserbase 基础设施里），你只负责轮询结果。适合"站点会持续改版""要横向覆盖成百上千个站点，不想为每个站点维护一份脚本"这类场景（⚠ 文档原文示例：用一个可复用 Agent 替代维护 N 份脆弱脚本）。

**关键概念**（⚠ 文档原文，见 platform/agents/overview.md）：

| 概念 | 含义 |
| :--- | :--- |
| Agent | 可复用的自主 agent 定义：`name` + 可选 `systemPrompt` + 可选 `resultSchema` |
| Run | 一次具体的自然语言任务执行 |
| Messages | 一次 run 的完整执行记录（做了什么，按时间顺序） |
| Session | 支撑这次 run 的 Browserbase 浏览器会话，可用 Live View / Replay 观察 |

**创建并触发一次 run**（Node.js，⚠ 文档原文）：

```typescript
import Browserbase from "@browserbasehq/sdk";

const bb = new Browserbase({ apiKey: process.env.BROWSERBASE_API_KEY! });

const { agentId, runId } = await bb.agents.runs.create({
  task: "Go to Hacker News and return the top 3 stories with their titles and URLs",
});
```

不传 `agentId` 时是一次性、未配置的 run；传入一个预先创建的 `agentId`（带 `systemPrompt`/`resultSchema`）则复用该 Agent 的行为定义。

**Run 生命周期**（终态需要轮询到达）：`PENDING` → `RUNNING` → 终态之一 `COMPLETED` / `FAILED` / `STOPPED` / `TIMED_OUT`。REST 端点：`POST /v1/agents/runs` 创建，`GET /v1/agents/runs/{runId}` 轮询，`GET /v1/agents/runs/{runId}/messages` 看执行记录，`POST /v1/agents/runs/{runId}/stop` 中止。管理 Agent 定义本身：`POST/GET/PATCH/DELETE /v1/agents/{agentId}`。

**内置能力**（⚠ 文档原文）：浏览器自动化（内部用 Stagehand 做 navigate/click/type/wait/observe/extract）、Search、文件读写、shell 命令、Agent Identity（proxies/CAPTCHA/verified 走 `browserSettings` 原样传入）、可观测性（live session、recording、replay、messages）。

**⚠ 与 ZDR/BYOS 的冲突**：Agents 目前不在 Zero Data Retention 和 Bring Your Own Storage 的覆盖范围内（文档原文警告，需要这两项合规能力的话要联系 Browserbase）。

**⚠ 计费是独立的一条线**：Agents 有自己的月度调用额度和超额费率（见 [`lifecycle-recording-cost.md`](lifecycle-recording-cost.md) 的计费一节），和 Sessions 的浏览器分钟计费是两回事——一次 Agent run 同时消耗 Agents 额度 **和** 它背后那个浏览器会话的分钟数。

**不要用 Agents 的场景**（⚠ 文档原文表格）：需要在自己代码里做确定性控制 → 用原始会话；要把自定义浏览器逻辑部署成可调用端点 → 用 Functions（本 skill 不覆盖，见下方"本 skill 不覆盖"）；只需要便宜的只读侦察 → 用 Search 或 Fetch。

## 先问：要不要浏览器？Search → Fetch → Browsers

在决定"REST / Stagehand / Agents 选哪个"之前，先问一个更前置的问题：**这个任务到底需不需要一个真实浏览器？** 官方文档反复强调这条递进关系（⚠ 文档原文，多个页面重复出现）：

```
Search（找信息在哪）→ Fetch（便宜地把内容抓下来）→ Browsers（需要交互/登录/JS 渲染时才用）
```

### Search（`POST /v1/search`）—— 你还不知道信息在哪的时候

不需要浏览器，返回搜索结果列表（`title`/`url`/`author`/`publishedDate`/`image`/`favicon`）。`query`（1-200 字符，必填）+ `numResults`（1-25，默认 10）。⚠ 文档原文：限流 **120 请求/分钟/项目**，超限返回 429。错误码：400（query 为空或 numResults 越界）、403（项目未开通 Search）、429、503、500。

**什么时候用**：做 recon、找候选 URL、给 RAG 管线找源，然后再决定要不要为某个结果开一个真实会话。

### Fetch（`POST /v1/fetch`）—— 知道 URL、只是想要干净内容，不需要交互

不渲染 JavaScript，轻量抓取一个已知 URL。三种输出格式：`raw`（原始响应体，最便宜）、`markdown`、`json`（需要同时传 `schema`，这是 "Fetch Extract"，比普通 Fetch 贵，计费在 pricing 表里单独一档）。

**关键限制**（⚠ 文档原文，是明确的报错，不是静默失败）：
- 响应体超过 **5MB** → `502` `{"error":"Bad Gateway","message":"...exceeded the maximum allowed size of 5MB. Use a browser session..."}`
- 目标页面 **60 秒**未响应 → `504` Gateway Timeout
- **不执行 JavaScript**——JS 渲染的动态内容拿不到，官方建议这种情况直接改用真实会话，不是加大超时能解决的
- **不能把 PDF 转成 markdown/json**——PDF 场景一律要用真实会话
- `schema` 只在 `format: "json"` 时合法，传给 `raw`/`markdown` 会被拒绝
- 代理：Fetch 只支持 Browserbase 托管代理的单一配置（`proxies: true` 或带 `geolocation` 的对象），**不支持自定义代理和按域名分流规则**——这点和真实会话的 proxies 能力不对等，是容易踩的坑

**什么时候用**：批量抓取已知 URL 列表、把"驱动一次 UI 找到底层请求，之后就用 Fetch 重放"这种监控/轮询场景做便宜化（先用真实会话观察 Network 面板找到那个真正返回数据的请求，然后后续改用 Fetch 直接打那个请求，不再需要浏览器）。

### Browsers —— 需要交互、登录态、JS 渲染，或高准确率优先于速度时

这才是本 skill 主体覆盖的三层（REST/Stagehand/Agents）。触发条件（⚠ 文档原文）：页面需要交互、数据在登录墙或 JS 渲染之后、需要比速度更高的准确率。

## 组合模式

官方文档给出的典型组合（⚠ 文档原文，来自 use-cases/agents.md）：

- **深度研究**：Search 发现相关页面 → Fetch 做便宜的初筛/摘要 → 对需要交互或结构化抽取的页面才开 Agent/真实会话。既控制 token 和延迟，又能覆盖需要真实浏览器才能到达的部分。
- **周期性拉取同一份数据**（比如价格监控）：先用一次真实会话观察 Network 面板找到返回数据的底层请求，之后的周期性拉取改用 Fetch 重放，不用每次都跑一遍完整 UI。
- **横向覆盖成百上千个站点**：一个带 `systemPrompt`/`resultSchema` 的可复用 Agent，替代为每个站点单独维护一份脚本；用 Functions 部署以降低延迟（本 skill 不覆盖 Functions）。

## 反直觉的地方

- **"Browsers"不是唯一入口。** 很容易把 Browserbase 直接等同于"远程浏览器 API"，但官方现在把 Search/Fetch 当作同等重要的入口——很多任务用不到浏览器，直接开会话是浪费钱且慢。
- **Stagehand 不是"自动帮你规划所有步骤"。** `act`/`extract`/`observe` 都是单步原语，控制流（先做什么再做什么、要不要重试）仍然是你的代码要写的；真正"给个目标就全自动跑完"的是 Browserbase Agents，是完全不同的产品，别把两者的能力预期搞反。
- **Fetch 的代理能力比真实会话弱得多。** 如果你的抓取脚本依赖多代理按域名分流（`domainPattern` 规则）或自定义代理认证，那些能力只在真实会话的 `proxies` 里有，Fetch 只有单一托管代理配置，迁移过去会静默变成一种能力子集，不会报错提示你"这个功能在 Fetch 里不存在"。
- **一次 Agent run 同时吃两份账单。** Agents 调用次数额度、以及它背后那个浏览器会话消耗的分钟数，是两条独立的计费线，不要只按"Agent 调用次数"估算成本。

## 本 skill 不覆盖

- **Functions**（`platform/runtime/overview` — 把浏览器自动化部署成可调用的 serverless 端点，零基础设施管理）：本 skill 只覆盖"直接建会话/用 Stagehand/用 Agents"这几种交互式路径，没有抓取 Functions 部署/构建相关页面的细节。
- **Model Gateway 的完整模型列表与定价**：本 skill 只在 [`stagehand.md`](stagehand.md) 里提到 Model Gateway 作为 Browserbase 会话下的模型自动选择机制，没有整理它支持的具体模型清单。
- **Webhooks 的完整签名校验实现**：仅在 [`lifecycle-recording-cost.md`](lifecycle-recording-cost.md) 里简要提及存在这个功能，未展开覆盖注册/验签/重试细节。
- **各家第三方集成**（1Password、AgentKit、n8n、LangChain、CrewAI、Mastra、Vercel AI SDK、Temporal、Trigger.dev 等 20+ 个 `/integrations/*` 页面）：这些是"把 Browserbase/Stagehand 接进某个特定框架"的教程，和"Browserbase 本身的 API 长什么样"是两回事，不在本 skill 范围内。

内容整理自 https://docs.browserbase.com（抓取于 2026-09-21），未使用真实 API Key 验证，实际调用报错优先信任真实 API。
