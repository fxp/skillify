# 鉴权、错误码、限流与计费

> ⚠ 本文件全部内容整理自官方文档（`/docs/get-started/quickstart`、`/docs/admin/error-codes`、`/docs/admin/billing`、`/docs/admin/pricing`、`/docs/sdks/quickstart`、`/docs/integrations/payments/x402/quickstart`）与 OpenAPI 规范的 `securitySchemes`，**未经真实 API 调用验证**。

目录：[鉴权](#鉴权) · [SDK](#sdk) · [错误响应结构](#错误响应结构) · [HTTP 状态码](#http-状态码) · [常见错误 tag](#常见错误-tag) · [Contents 的 URL 级失败](#contents-的-url-级失败) · [限流](#限流) · [Agent 并发限制](#agent-并发限制) · [定价速查](#定价速查) · [免 Key 按次付费（x402 / MPP）](#免-key-按次付费x402--mpp) · [API Key 管理](#api-key-管理)

## 鉴权

OpenAPI 规范 `components.securitySchemes` 同时定义了两种方式，**描述文字完全相同**：

```yaml
apiKey:
  type: apiKey
  in: header
  name: x-api-key
  description: "Pass your Exa API key in the x-api-key header. You can also authenticate with Authorization: Bearer <key>."
bearer:
  type: http
  scheme: bearer
  description: "Pass your Exa API key in the x-api-key header. You can also authenticate with Authorization: Bearer <key>."
```

即规范本身也认为两者等价。但**文档站里能找到的每一处示例代码**（覆盖 search/contents/answer/agent/batch 全部端点，curl、Python、JS 三种语言）无一例外用：

```
Authorization: Bearer $EXA_API_KEY
```

没有任何一处示例用 `x-api-key: $EXA_API_KEY`。⚠ 未实测两者是否完全等价、能否同时传、冲突时谁生效——建议新代码照抄文档示例只用 `Authorization: Bearer`，除非有官方支持明确说需要 `x-api-key`。

x402 免密支付文档明确了一条相关行为（⚠ 文档原文，未实测）："x402 and API key access are independent. If your request includes an `x-api-key` or `Authorization: Bearer` header, the normal API key billing flow is used and x402 is bypassed entirely."——即只要带了任意一种鉴权头，就会走正常计费而不是 x402 逐次链上支付，说明两个 header 至少在"是否触发计费鉴权"这一判断上是等价的。

Key 从 https://dashboard.exa.ai/api-keys 创建；每个 Key 可以单独设置比团队更低的限流/预算上限（团队整体限流仍然计入该 Key 的流量）。

## SDK

官方维护两个 SDK：

| 语言 | 包名 | 安装 | 要求 |
|---|---|---|---|
| Python | `exa-py` | `pip install exa-py` / `uv add exa-py` | Python 3.9+ |
| JavaScript/TypeScript | `exa-js` | `npm install exa-js` / `pnpm add exa-js` | — |

两个 SDK 默认都从环境变量 `EXA_API_KEY` 读取密钥；也可以显式传入：`Exa(api_key="...")`（Python）/ `new Exa("...")`（JS）。Python 另有 `AsyncExa` 异步客户端。源码仓库：`github.com/exa-labs/exa-py`、`github.com/exa-labs/exa-js`。

## 错误响应结构

绝大多数端点（`/search`、`/contents`、`/answer`、`/monitors`）返回**扁平**结构：

```json
{
  "requestId": "67207943fab9832d162b5317f4cca830",
  "error": "Invalid request body | Validation error: Invalid value for type",
  "tag": "INVALID_REQUEST_BODY"
}
```

⚠ **Agent API（`/agent/runs/*`）例外，是嵌套结构**（见 `references/agent.md`"错误结构"节）：

```json
{ "error": { "type": "INVALID_REQUEST", "code": "INVALID_OUTPUT_SCHEMA", "message": "..." } }
```

文档原文建议：先按 HTTP 状态码分支，`tag`/`error.code` 的取值集合是开放式的（"open-ended"，随时可能新增），未识别的 tag 当成该状态码的通用错误处理，不要因为遇到陌生 tag 就判定解析失败。联系支持时带上 `requestId`。

## HTTP 状态码

| 状态码 | 含义 | 处理建议 |
|---|---|---|
| 400 | 请求体/参数/头或参数组合不合法 | 按返回的 `error` 文案修正 |
| 401 | Key 缺失或无效 | 检查鉴权头和 Key 本身 |
| 402 | 信用额度耗尽或预算超限 | 去 dashboard 充值，或找团队管理员调预算 |
| 403 | Key 无权访问该功能，或被策略拦截 | 检查返回文案和当前套餐的功能开放范围 |
| 404 | 路由或资源不存在 | 检查 endpoint 路径和资源 ID |
| 409 | 与现有状态冲突（如 Webset 的 `externalId` 已存在） | 取已有资源，或换一个标识符 |
| 422 | Websets preview 的 query 无法被拆解成合法的实体+条件 | 改写 preview query |
| 429 | Key/团队/网络触发限流或并发上限 | 有 `Retry-After` 就按它等，否则指数退避 |
| 500 | 服务端未预期错误 | 稍后重试，持续出现再联系支持 |
| 503 | Exa 暂时过载（`SERVICE_OVERLOADED`）或不可用；**请求未被处理，不计费** | 指数退避重试；文档特别强调"降低请求速率没用，是过载和你的速率无关，重试才有用" |
| 504 | 请求超过处理时限 | 重试或缩小请求范围 |

## 常见错误 tag

**账号/计费/权限**

| tag | HTTP | 说明 |
|---|---|---|
| `INVALID_API_KEY` | 401 | Key 缺失/为空/无效 |
| `NO_MORE_CREDITS` | 402 | 账户余额耗尽 |
| `API_KEY_BUDGET_EXCEEDED` | 402 | 该 Key 自己设置的预算上限超了 |
| `TEAM_BUDGET_EXCEEDED` | 402 | 团队当期预算超了 |
| `FEATURE_DISABLED` | 403 | 该 endpoint/搜索模式/选项不在当前套餐开放范围 |
| `PROHIBITED_CONTENT` / `CONTENT_FILTER_ERROR` | 403 | 内容安全策略拦截 |
| `RATE_LIMIT_EXCEEDED` | 429 | 超出自己的限流 |
| `SERVICE_OVERLOADED` | 503 | Exa 侧过载，请求还没处理就被丢弃 |

**请求校验**

| tag | HTTP | 说明 |
|---|---|---|
| `INVALID_REQUEST_BODY` | 400 | JSON body 没通过 schema 校验 |
| `INVALID_REQUEST` | 400 | 选项之间冲突，或用了 Beta 功能但没带对应的 `Exa-Beta` 头 |
| `INVALID_NUM_RESULTS` | 400 | 请求 `highlights` 时 `numResults` 必须 ≤ 100 |
| `NUM_RESULTS_EXCEEDED` | 400 | 请求的结果数超过当前套餐上限 |
| `INVALID_JSON_SCHEMA` | 400 | 提供的 `outputSchema` 本身不合法 |
| `SUBPAGES_LIMIT_EXCEEDED` | 400 | `/contents` 单次请求最多 100 个 subpages |

**x402 / MPP 支付协议专属**（仅免 Key 按次付费场景）

| tag | HTTP | 说明 |
|---|---|---|
| `X402_PAYMENT_REQUIRED` | 402 | 需要支付 |
| `X402_INVALID_SIGNATURE` | 400 | x402 支付签名无效 |
| `X402_VERIFICATION_FAILED` | 402 | x402 支付无法验证 |
| `MPP_VERIFICATION_FAILED` | 402 | MPP 支付无法验证 |
| `X402_TOO_MANY_UNPAID` | 429 | 待支付的 x402 请求过多 |
| `X402_WALLET_RATE_LIMITED` | 429 | x402 钱包触发限流 |
| `X402_INTERNAL_ERROR` | 500 | Exa 侧无法生成 x402 支付要求 |

## Contents 的 URL 级失败

**只有 `/contents`（含带 `snapshotAsOf` 的历史请求）才有 `statuses` 字段**，`/search` 没有。单个 URL 失败不影响整体请求（仍是 200），失败原因体现在 `statuses[].error`，具体 tag 见 `references/contents-and-find-similar.md`。

## 限流

按 QPS（每秒查询数）计，**按团队整体计**（团队下所有 Key 共用），可以给单个 Key 设更低的上限但不会突破团队总量：

| Endpoint | 默认限流 |
|---|---|
| `/search`、`/answer`、`/chat/completions` | 10 QPS |
| `/search` 且 `type` 为 `deep-lite`/`deep`/`deep-reasoning` | 5 QPS |
| `/contents` | 100 QPS |
| `/agent/runs`、`/responses` | 5 QPS，且并发 50 个进行中的 run |
| `/websets/*` | 20 QPS |

超限返回 429，有 `Retry-After` 头就按它等待，否则指数退避。

**30 天内充值满 $1,000 会自动把限流提到 25 QPS，持续 90 天**（按购买金额算，不是消费金额；再次达标会重置这 90 天窗口）。企业版限流自定义。

## Agent 并发限制

Agent 有两个独立的控制维度（文档原文强调"两者分开"）：

- **并发**：同时最多 50 个进行中的 run，与 QPS 无关，QPS 提升不会连带提升这个上限；超过时 429 + `CONCURRENCY_LIMIT_REACHED`。
- **起新 run 的速率**：`POST /agent/runs` 吃团队 QPS 额度，**每次起 run 算 2 次请求**——默认 10 QPS 的账号每秒最多起 5 个 run，25 QPS 能起 12 个。
- **轮询不吃 QPS**：`GET` 查状态/事件/列表都不计入 QPS，也不会阻塞新 run 的调度，可以放心高频轮询。

## 定价速查

⚠ 文档原文，未实测，且价格随时可能调整，正式使用前应查 https://docs.exa.ai/admin/pricing 最新版本。

| 端点/能力 | 基础价（含 10 条结果/次） | 超出部分 |
|---|---|---|
| `/search`（`instant`/`fast`/`auto`） | $7 / 1k 次 | 每条超出 10 的结果 $1/1k 条；AI 摘要 $1/1k 页 |
| `/search`（`deep-lite`/`deep`） | $12 / 1k 次 | 同上 |
| `/search`（`deep-reasoning`） | $15 / 1k 次 | 同上 |
| `/answer` | $5 / 1k 次 | 不区分结果数 |
| `/contents` | $1 / 1k 页，**按内容类型分别计**（text/highlights/summary 各算一次） | AI 摘要额外 $1/1k 页 |
| `/monitors` | $15 / 1k 次 | 同 `/search` |
| Agent 固定 effort | `minimal` $0.012 / `low` $0.025 / `medium` $0.10 / `high` $0.50 / `xhigh` $1.00（每次） | — |
| Agent `auto`/`max`（计量） | ACU $0.10/单位 + 检索 $0.005/次 | 默认封顶 $5 / $20，`budget.maxCostDollars` 可调（$1–$100） |
| Agent 联系人富化 | 邮箱 $0.02/个，电话 $0.07/个 | 独立于其他 Agent 费用项 |

新账号有 $20 免费额度（约 2,800 次基础搜索），Free Tier 每月再补 $10。团队额度耗尽或 Key 预算超限统一返回 402。

## 免 Key 按次付费（x402 / MPP）

`/search` 和 `/contents` 支持不带 Key、按次用加密货币付费：**x402**（USDC，Base 或 Solana 链）、**MPP/Tempo**（USDC.e）。未带鉴权头且未带支付头的请求会收到 402 + `PAYMENT-REQUIRED` 响应头（base64 编码，含定价和支持的支付网络），客户端签名支付后带 `PAYMENT-SIGNATURE` 头重试。**只要请求带了 `x-api-key` 或 `Authorization: Bearer`，就会走正常计费流程，x402 完全不触发**——两条路径互斥、由是否携带鉴权头决定，不需要显式开关。仅 `/search`、`/contents` 两个端点支持，其余端点不支持免 Key 付费。⚠ 本 skill 未展开 x402/MPP 的完整签名流程，需要时读 `/docs/integrations/payments/x402/quickstart`。

## API Key 管理

团队管理相关操作走独立的 team-management API（`GET/POST/PATCH/DELETE /v0/... `团队与 Key 相关路由，规范文件 `team-management-spec.yaml`，本 skill 未展开字段细节）：创建 Key（可选命名、可选限流配置）、列出 Key、查单个 Key 详情、查 Key 的用量与账单分析、改名/改限流、删除 Key、查团队信息（`GET /v0/teams/me`，含并发用量与上限）。需要时读 `/docs/reference/team-management/*`。
