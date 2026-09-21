# SDK / CLI / MCP / x402 — 怎么接进你的运行环境

> ⚠ 文档版参考：内容来自官方 SDK Reference、CLI 文档、MCP 文档、keyless/x402 页，抓取于 2026-09-21，**未用真实 API Key 验证**。

目录：[1. Python SDK](#1-python-sdk) · [2. JavaScript SDK](#2-javascript-sdk) · [3. Tavily CLI](#3-tavily-cli)
· [4. MCP Server](#4-mcp-server) · [5. 和官方 Agent Skills 的关系](#5-和官方-agent-skills-tavily-aiskills-的关系)
· [6. Keyless 免密访问](#6-keyless-免密访问) · [7. x402 按次付费](#7-x402-按次付费) · [8. Session / Project 追踪](#8-session--project-追踪)

## 1. Python SDK

包名 `tavily-python`（PyPI），`pip install tavily-python`。GitHub：`tavily-ai/tavily-python`。

```python
from tavily import TavilyClient, AsyncTavilyClient

# 同步
client = TavilyClient("tvly-YOUR_API_KEY")
# 异步
aclient = AsyncTavilyClient("tvly-YOUR_API_KEY")
```

客户端方法基本和 REST endpoint 一一对应：`search()`、`extract()`、`crawl()`、`map()`、`research()`。**⚠ 文档自相矛盾**：SDK Reference 正文明确说"通过 `map`
函数访问"，但同一份文档里至少有一处代码示例写的是 `tavily_client.mapping(...)`——以正文和参数表为准，方法名按 `map` 写，`mapping` 疑似文档残留，
实测前先 `dir(TavilyClient)` 确认。

支持的额外客户端级参数：
- `project_id`（或环境变量 `TAVILY_PROJECT`）——附加到该客户端发出的所有请求，用于 `/logs`、控制台按项目筛选用量。
- `session_id` / `human_id`——附加 `X-Session-Id`/`X-Human-Id` header，也可以在每次方法调用时单独覆盖（`client.search(..., session_id=..., human_id=...)`）。
- `proxies`（或环境变量 `TAVILY_HTTP_PROXY`/`TAVILY_HTTPS_PROXY`）——`{"http": "...", "https": "..."}`。

`tavily-python` 还打包了一个 `TavilyHybridClient`（MongoDB 专用的本地库 + 网络搜索混合检索封装，依赖 Cohere 做 embedding/rerank，需要 `pip install cohere`
和 `CO_API_KEY`）。这是一个独立的、偏小众的能力，不是核心 REST API 的一部分，用到时单独查 SDK Reference 的 "Tavily Hybrid RAG" 一节，本 skill 不展开。

## 2. JavaScript SDK

包名 `@tavily/core`（npm），`npm i @tavily/core`。GitHub：`tavily-ai/tavily-js`。

```javascript
const { tavily } = require("@tavily/core");
const client = tavily({ apiKey: "tvly-YOUR_API_KEY" });

const response = await client.search("Who is Leo Messi?");
const extracted = await client.extract("https://en.wikipedia.org/wiki/Lionel_Messi");
const crawled = await client.crawl("https://docs.tavily.com", { instructions: "Find all pages on the Python SDK" });
```

参数命名和 REST/Python 基本一致（snake_case 字段名原样透传，不是 camelCase——例如 `search_depth` 而不是 `searchDepth`；⚠ 文档未逐一验证是否所有字段
都保持 snake_case，Best Practices 页的异步批量示例里出现过 `searchDepth: "advanced"` 这种 camelCase 写法，⚠ 文档自相矛盾，两种写法哪个真实生效待验证）。

## 3. Tavily CLI

包名 `tavily-cli`（PyPI，也可 `uv tool install tavily-cli`），命令名 `tvly`。官方安装脚本：

```bash
curl -fsSL https://cli.tavily.com/install.sh | bash
# 或
pip install tavily-cli
```

鉴权三选一：`tvly login --api-key tvly-YOUR_API_KEY`（存到 `~/.tavily/config.json`）、`tvly login`（浏览器 OAuth，存到 `~/.mcp-auth/`）、
环境变量 `TAVILY_API_KEY`（优先级最高）。

```bash
tvly search "latest AI news" --topic news --time-range week
tvly extract https://example.com/article --query "key findings" --chunks-per-source 3
tvly crawl https://docs.example.com --max-depth 2 --select-paths "/docs/.*"
tvly map https://example.com --max-depth 2
tvly research "compare React vs Svelte" --model pro --citation-format apa -o report.md
```

**CLI 的 `--max-results` 默认值写的是 `5`**，和 OpenAPI/Python SDK Reference 的 `10` 不一致，见 `search.md` §1 的三方矛盾。
**CLI 的 `--chunks-per-source`（search 子命令）选项说明写"requires `fast` or `advanced` depth"**，没提 `basic`；但 2026-07 changelog 明确说
`chunks_per_source` 现在对 `basic` 也生效——CLI 这行说明疑似落后于后端改动，⚠ 文档自相矛盾，见 SKILL.md 通用规则第 12 条。

每条命令加 `--json` 输出机器可读结果（人类可读的进度信息走 stderr，`--json` 时 stdout 只有干净 JSON），方便接脚本/`jq`。

## 4. MCP Server

- **远程 MCP**（推荐，免本地安装）：`https://mcp.tavily.com/mcp/?tavilyApiKey=<your-api-key>`（Streamable HTTP），也支持 OAuth（URL 里不带 key，首次连接时走浏览器授权）。
- **本地 MCP**：npm 包 `@tavily/mcp` / GitHub `tavily-ai/tavily-mcp`，Node.js ≥ v20。

```bash
# Claude Code
claude mcp add tavily-remote-mcp --transport http https://mcp.tavily.com/mcp/
```

**⚠ 文档不一致：MCP 暴露的工具集合，两处文档给出的清单不一样。** MCP 专属文档页（`documentation/mcp`）的 "Features" 只提到两个工具：
`tavily-search`、`tavily-extract`；而 Claude 集成页（`documentation/integrations/claude`）列出的 "Tavily tools available" 表有六个：
`tavily_search`、`tavily_extract`、`tavily_crawl`、`tavily_map`、`tavily_research`、`tavily_skill`（注意连字符 `-` vs 下划线 `_` 命名也不统一）。
⚠ 假设，待验证：实测连接远程 MCP 后 `tools/list` 返回的真实工具清单和命名，不要在文档没验证前假设某个工具一定存在。

MCP 支持通过 `DEFAULT_PARAMETERS` header 传一个 JSON 对象设置所有请求的默认参数（如 `{"search_depth": "advanced", "max_results": 10}`）。
`X-Session-Id` 由 MCP session 自动生成并复用于该 session 内的所有工具调用；`X-Human-Id` 需要客户端主动通过 header 或 `humanId` query 参数提供才会转发。

## 5. 和官方 Agent Skills（`tavily-ai/skills`）的关系

Tavily 自己在 GitHub 发布了一组通过 CLI 安装的 skill（`npx skills add tavily-ai/skills --all`），包含 `tavily-search`/`tavily-extract`/`tavily-crawl`/
`tavily-map`/`tavily-research`/`tavily-best-practices` 六个 slash-command 风格 skill，安装后靠 Tavily CLI（`tvly`）在后台执行，面向"编码 Agent 在本地
会话里临时用一下 Tavily"的场景。**本 skill（`Skillify/tavily`）是不同的东西**：这里教的是直接调用 REST API / SDK 写业务代码，适合要把 Tavily 集成进
生产应用、后端服务、自建 Agent 运行时的场景，不依赖用户本地是否装了 `tvly` CLI。两者不冲突，可以同时存在；如果 Agent 已经装了官方 CLI skill，
优先用它做交互式的临时查询，写正式代码集成时按本 skill 的参数表来。

## 6. Keyless 免密访问

Header `X-Tavily-Access-Mode: keyless`，**仅 `/search`、`/extract` 支持**，`/crawl`、`/map`、`/research` 必须用真实 Key。
响应 schema 和有 Key 时完全一致（官方强调"Keyless responses are identical to keyed responses"），免费但限流更严格，具体限流数值文档未给出
（⚠ 文档未说明，只说"rate-limited"）。同时传 keyless header 和有效 `Authorization: Bearer` 时以后者为准，用真实账号的限流和额度。

远程 MCP 也支持 keyless：

```bash
claude mcp add tavily-remote-mcp --transport http https://mcp.tavily.com/mcp/ \
  --header "X-Tavily-Access-Mode: keyless"
```

## 7. x402 按次付费

给不持有传统 API Key、但持有加密钱包的自主 Agent 用的支付通道：`https://x402.tavily.com/search`，走 x402 v2 协议，Base 主网 USDC 结算，
**固定只支持 `search_depth=advanced` 一档**，定价 $0.01/次（USDC 原子单位 `10000` = $0.01，6 位小数精度）。流程：Agent 发请求 → 收到 402 +
`PAYMENT-REQUIRED` header（base64 JSON，含 `accepts[0].amount`/`payTo` 等 EIP-3009 转账授权信息）→ Agent 签名 USDC 转账授权 → 带
`PAYMENT-SIGNATURE` header 重试 → 200 + 搜索结果 + `PAYMENT-RESPONSE` header（结算回执）。上游调用失败会自动退款到发起转账的钱包（走
`nonce` 关联原始支付），**退款到发起签名的钱包地址**，用交易所/托管钱包支付的话退款会进那个钱包，生产场景建议用自托管钱包。这是一条和
`Authorization: Bearer` 完全独立的鉴权/计费通道，不要和常规 API Key 调用混在一套客户端代码里。

## 8. Session / Project 追踪

三个可选 header，REST/SDK/CLI/MCP 都支持（字段名统一）：

| Header | 用途 | 谁生成 |
| :--- | :--- | :--- |
| `X-Project-ID` | 按项目筛选 `/logs` 和控制台用量 | 调用方设置（或 SDK `project_id`/环境变量 `TAVILY_PROJECT`） |
| `X-Session-Id` | 把同一个 Agent 任务里的多次调用（search→extract→search）关联成一个会话 | 调用方设置；MCP session 会自动生成并复用 |
| `X-Human-Id` | 标识 Agent 背后的终端用户，帮助 Tavily 理解多步骤交互、改进结果质量 | 调用方设置；**服务端会先哈希再存储**，MCP 不会自己生成，只透传客户端提供的值 |

多步骤 Agent 工作流（比如"先搜索、再从筛选出的几个结果里 extract、再补充搜索"）建议全程复用同一个 `session_id`，便于 Tavily 侧做效果分析，
也方便自己在 `/logs` 里按会话排查问题。
