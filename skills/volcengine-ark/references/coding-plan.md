# 火山方舟 Coding Plan（个人版为主，企业版差异单独一节）

本文覆盖：Coding Plan 是什么、与 Agent Plan / 标准 API 的边界、两条 Base URL、Model Name 全表（上下文 / 最大输出 / 默认思考）、`ark-code-latest` 与控制台切换、额度与刷新规则、"不可用于 API 调用"的官方口径、专属权益（Embedding、ArkClaw）、Ark CLI 用法、开发排错相关 FAQ、影响开发者的公告、企业版差异。各 AI 工具的逐步配置**不在本文**，见 `references/tools-setup.md`。

标注约定：**（文档原文，未实测）** = 行为描述来自官方文档，本 skill 未实际调用验证；`⚠` = 文档未说明 / 自相矛盾，是后续真实验证的优先项。

**验证状态（2026-09-04）**：以下所有"Plan 入口共性结论"（Key 隔离、`auto` 不能直填、`developer` role 400、`glm-5.3` 思考控制、`kimi` 的 `max_tokens`、`service_tier` 报错、Embeddings 形态等）是在 **Agent Plan `/api/plan/v3` 实测**得出的，标为 **已用真实 API 验证（2026-09-04，Agent Plan Medium）**。**Coding Plan `/api/coding/v3` 因当前账号未订阅（Pro 已售罄）未直接验证**——两套 Plan 入口由同一网关提供、报错文案里甚至互相串（Agent Plan 入口的 `service_tier` 报错说的是 "coding plan"），预期行为一致，但本文对 Coding Plan 入口的描述仍按**文档转录**对待，遇到不一致以 Coding Plan 入口实际返回为准。

## 目录

1. [Coding Plan 是什么](#1-coding-plan-是什么)
2. [Coding Plan vs Agent Plan vs 标准 API](#2-coding-plan-vs-agent-plan-vs-标准-api)
3. [Base URL、Key、HTTP 头](#3-base-urlkeyhttp-头)
4. [支持的模型（Model Name 全表）](#4-支持的模型model-name-全表)
5. [模型配置的两种方式：Model Name vs ark-code-latest](#5-模型配置的两种方式model-name-vs-ark-code-latest)
6. [套餐、额度与刷新规则](#6-套餐额度与刷新规则)
7. [使用限制："不能用于 API 调用"](#7-使用限制不能用于-api-调用)
8. [连通性验证请求（Chat Completions / Embeddings）](#8-连通性验证请求chat-completions--embeddings)
9. [专属权益：Embedding 模型（OpenClaw / OpenViking）](#9-专属权益embedding-模型openclaw--openviking)
10. [专属权益：ArkClaw](#10-专属权益arkclaw)
11. [Ark CLI 在 Coding Plan 下的用法](#11-ark-cli-在-coding-plan-下的用法)
12. [工具 → 协议 → Base URL 速查](#12-工具--协议--base-url-速查)
13. [开发与排错 FAQ](#13-开发与排错-faq)
14. [影响开发者的公告：模型上线 / 下线 / 活动](#14-影响开发者的公告模型上线--下线--活动)
15. [企业版差异](#15-企业版差异)
16. [来源页面](#来源页面)

---

## 1. Coding Plan 是什么

方舟 Coding Plan 是火山方舟面向**个人开发者**的 AI 编程**订阅套餐**（包月），在 Claude Code、OpenCode、OpenClaw、TraeCode、Cline、Cursor、Roo Code、Kilo Code、Codex CLI、Hermes Agent 等 AI 编程工具里使用一组国产编程模型 + 一个 Embedding 模型，按套餐额度抵扣而不是按 token 后付费。

官方口径的四个卖点：支持主流模型（含 Embedding）；兼容主流 AI 编码工具且**套餐额度在所有工具间共享**；Lite / Pro 两档；多租户隔离、高峰不明显降速。

购买即开通：**不需要**在方舟控制台单独开通模型、也**不需要**创建推理接入点（`ep-xxx`），订阅成功后直接用 Model Name 调用。

控制台实读（2026-09-03，`console.volcengine.com/ark/region:cn-beijing/subscription/coding-plan`）：售卖页标题「Coding Plan 个人版 · 主流国产编程模型全覆盖，多生态兼容，模型工具不限，丝滑不降速」；Lite 9.9 元/月「立即订阅」；Pro 49.9 元/月**「已售罄」**；模型列表：Auto、Doubao-Seed-2.0-lite、Kimi-K2.7-Code、MiniMax-M3、Doubao-Seed-2.1-turbo、DeepSeek-V4-Flash、GLM-5.3、Doubao-Seed-Evolving、DeepSeek-V4-Pro、GLM-5.3-Flash（无 kimi-k3、无 doubao-seed-2.0-mini、无图片/视频/语音模型）。

## 2. Coding Plan vs Agent Plan vs 标准 API

三套入口**绝不能混用**：用错 Base URL 不会抵扣套餐额度，而是走后付费产生费用。

| 维度 | 标准 API（后付费） | **Coding Plan** | Agent Plan |
|---|---|---|---|
| OpenAI 协议 Base URL | `https://ark.cn-beijing.volces.com/api/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` | `https://ark.cn-beijing.volces.com/api/plan/v3` |
| Anthropic 协议 Base URL | ⚠ 文档未列出 | `https://ark.cn-beijing.volces.com/api/coding` | `https://ark.cn-beijing.volces.com/api/plan` |
| 用哪把 Key | 方舟 API Key | **同一把方舟 API Key**（文档写「API Key：获取 API Key」，链接到通用 API Key 管理页） | **Agent Plan 专属 API Key**（与方舟 API Key 不通用）。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Agent Plan Key 打 `/api/coding/v3/chat/completions` → **401** `{"error":{"code":"AuthenticationError","message":"The API key or AK/SK in the request is missing or invalid. ...","type":"Unauthorized"}}`（打 `/api/v3` 同样 401）——两把 Key 确实不互通，且错误是鉴权失败而非「套餐不支持」 |
| `model` 字段 | 带日期的 Model ID（如 `doubao-seed-2-1-pro-260628`）或 `ep-xxx` | 小写 Model Name（如 `kimi-k2.7-code`）或 `ark-code-latest` | 小写 Model Name、`ark-code-latest`（`auto` 不能直填，实测 404，见 §5） |
| 模型范围 | 全部已开通模型 | **只有语言模型 + 1 个向量化模型**（无图片/视频/语音） | 语言 + 向量化 + 图片/视频/语音 |
| 档位 | — | **Lite / Pro** 两档 | Small / Medium / Large / Max |
| 计量方式 | 按 token 后付费 | **按"请求次数"估算**的额度，分 5 小时 / 周 / 月三档限额 | AFP（Agent Fuel Point）精细抵扣，可开超额后付费 |
| 额度耗尽后 | — | 等下一周期恢复，**不会**扣其他资源包或余额 | 可选超额后付费 |
| 需要开通模型 / 建接入点 | 需要 | 不需要 | 不需要 |
| 是否允许非编程工具调用 | 允许 | **不允许**（可能被判滥用） | 文本/向量化模型不允许 |

官方在 Coding Plan 文档里多处引导：「方舟已推出 Agent Plan 套餐，新增支持全模态模型及专属 Harness，采用精细化 AFP 抵扣规则，用量清晰可查」——即 Coding Plan 的用量是**估算次数**、不可精细核对，Agent Plan 才有可查的 AFP 账。

## 3. Base URL、Key、HTTP 头

- 兼容 **Anthropic** 接口协议的工具（如 Claude Code）：`https://ark.cn-beijing.volces.com/api/coding`
- 兼容 **OpenAI** 接口协议的工具（如 Cline、Cursor、OpenCode、OpenClaw）：`https://ark.cn-beijing.volces.com/api/coding/v3`
- **请勿使用** `https://ark.cn-beijing.volces.com/api/v3`：文档原文「该 Base URL 不会消耗您的 Coding Plan 额度，而是会产生额外费用」。
- Key：方舟 API Key，控制台 `console.volcengine.com/ark/region:cn-beijing/apikey`。示例代码统一从环境变量 `ARK_API_KEY` 读取。
- HTTP 头（OpenAI 协议入口）：`Authorization: Bearer $ARK_API_KEY`、`Content-Type: application/json`。
- HTTP 头（Anthropic 协议入口）：文档只给了 Claude Code 的 `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` 形式。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Agent Plan 的 Anthropic 入口 `POST /api/plan/v1/messages` 对 `x-api-key: <Key>` 与 `Authorization: Bearer <Key>` **两种头都接受**（配 `anthropic-version: 2023-06-01`），Claude Code 的 `ANTHROPIC_AUTH_TOKEN`（Bearer）没问题；Coding Plan 入口 `/api/coding/v1/messages` 预期一致，⚠ 未直接实测。
- 区域：文档只出现 `cn-beijing`；「不同区域可选择的模型请以控制台为准」，其他区域 Base URL ⚠ 文档未说明。

## 4. 支持的模型（Model Name 全表）

Model Name 全小写；也可以直接复制开通管理页面里的模型名称（大小写混排形式同样被接受，文档原文）。以控制台实际展示为准。

| Model Name | 上下文窗口 | 最大输出 | 默认思考行为 | 多模态 | 备注 |
|---|---|---|---|---|---|
| `doubao-seed-evolving` | 1024k | 256k | ⚠ 文档未说明 | ⚠ 未说明 | 面向 Coding/Agent，周级持续升级，统一模型 ID；2026-08-21 上线 |
| `doubao-seed-2.1-turbo` | 256k | 64k | ⚠ 文档未说明 | 视觉理解 | 2026-07-23 上线；`doubao-seed-2.0-code` / `2.0-pro` 的官方迁移目标 |
| `doubao-seed-2.0-lite` | ⚠ 文档未说明 | ⚠ 文档未说明 | ⚠ 文档未说明 | 视觉理解 | 额度估算的基准模型（见 §6） |
| `minimax-m3` (`minimax-latest`) | 1024k | 128k | ⚠ 文档未说明 | 视觉理解 | 2026-06-08 上线 |
| `kimi-k2.7-code` (`kimi-latest`) | 256k | 32k（含思维链） | 支持思考模式，默认值 ⚠ 未说明 | 文本 / 图片 / 视频输入 | 2026-06-18 上线 |
| `glm-5.3` (`glm-latest`) | 1024k | 128k | **默认开启，不支持关闭**。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`thinking: {"type":"disabled"}` → **400** `{"error":{"code":"InvalidParameter","message":"thinking.type `disabled` is not supported by this model ...","type":"BadRequest"}}`；`reasoning_effort: "none"` → **400**「reasoning_effort `none` is not supported by this model」；但 `reasoning_effort: "low"` → 200 且 `reasoning_tokens: 0`、无 `reasoning_content`——**事实上等于关掉思考**，想省额度用这个 | ⚠ 未说明 | 抵扣系数高、额度消耗快，官方建议只用于重难点问题；2026-08-14 上线 |
| `glm-5.3-flash` | 1024k | 128k | ⚠ 文档未说明 | 原生多模态，支持图片输入 | 2026-08-28 上线；至 2026-09-11 抵扣系数 5 折 |
| `deepseek-v4-flash` | 1024k | 384k | **默认开启，支持手动关闭** | ⚠ 未说明 | 正式版 2026-08-04/07 全量 |
| `deepseek-v4-pro` (`deepseek-latest`) | 1024k | 384k | **默认开启，支持手动关闭** | ⚠ 未说明 | 抵扣系数高、额度消耗快，建议只用于重难点问题；正式版 2026-08-26 |
| `doubao-embedding-vision` | — | — | — | 多模态向量化 | 对应标准入口模型 `doubao-embedding-vision-251215`；见 §9 |
| `ark-code-latest` | 随控制台所选模型 | 随所选模型 | 随所选模型 | — | 不是模型，是"控制台切换"占位名，见 §5 |
| `Auto` | — | — | — | — | **只能在控制台选**，不能写进配置文件；见 §5。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`model: "auto"` → **404** `UnsupportedModel`，Coding Plan 文档说得对 |

补充说明（均为文档原文）：

- 1M 上下文：`doubao-seed-evolving`、`glm-5.3`、`glm-5.3-flash`、`deepseek-v4-flash`、`deepseek-v4-pro` 支持 1M 上下文窗口；在工具里开启 1M 的方法见 `references/tools-setup.md`（Claude Code / OpenCode / OpenClaw 各有配置）。
- 「在控制台可以查看模型在编码工具中默认的 thinking 行为，真实使用时可由编码工具通过指定参数修改思考行为」——所以上表 ⚠ 的默认思考值，以控制台为准。
- `*-latest` 别名：`glm-latest`→`glm-5.3`，`minimax-latest`→`minimax-m3`，`kimi-latest`→`kimi-k2.7-code`，`deepseek-latest`→`deepseek-v4-pro`（模型上线/下线公告）。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`model: "glm-latest"` → 200，响应 `"model":"glm-5.3"`，别名可直接写进请求。⚠ 其余三个别名仅见于公告，未实测。
- 与 Agent Plan 的差异：Coding Plan 列表里**没有** `kimi-k3`、图片/视频/语音模型。Auto 模式活动说明提到「支持路由到 kimi-k3，夜间 00:00-8:00 kimi-k3 的路由比例会大幅度提升」——即 kimi-k3 只能通过 Auto 被路由到，不能直接指定。

## 5. 模型配置的两种方式：Model Name vs ark-code-latest

| | 配置 Model Name（配置文件指定） | 配置 `ark-code-latest`（控制台管理） |
|---|---|---|
| 怎么填 | `model` / `ANTHROPIC_MODEL` 等填 §4 里的小写名 | 填 `ark-code-latest` |
| 切换模型 | 改配置文件；Claude Code 可 `claude --model <Model_Name>` 或对话中 `/model <Model_Name>`，**实时**生效 | 去开通管理页面（`console.volcengine.com/ark/region:cn-beijing/openManagement?LLM=%7B%7D&advancedActiveKey=subscribe`）选模型，**3-5 分钟**生效；Claude Code 里用 `/status` 确认 |
| 能否用 Auto | **不能**：文档原文「Model Name 不支持配置为 Auto，如需使用，请通过控制台切换该模式」。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`model: "auto"` → **404** `{"error":{"code":"UnsupportedModel","message":"The requested model does not support the agent plan feature. Please refer to the documentation at https://www.volcengine.com/docs/82379/2366394 to select a compatible model. ..."}}`（Agent Plan 控制台把 `auto` 列成 Model Name 是错的，本文档说得对） | **能**：控制台可选 Auto（默认选项），「效果 + 速度」双维度智能调度。实测选 Auto 时响应 `model` 字段为 `"auto"`，看不出实际路由到哪个模型 |
| 旧模型下线时 | 需手动改配置，否则失效（`glm-5.2` 下线例外：到期未迁移会自动路由到 `glm-5.3`） | 不用改配置；官方推荐方式 |
| 适用 | 需要在不同任务间快速换模型 | 一次配置、长期不动、想跟最新模型 |

官方推荐（模型下线公告「切换模型步骤」）：优先用 latest 配置——`ark-code-latest` 或 `glm-latest` / `minimax-latest` / `kimi-latest` / `deepseek-latest`，避免旧模型下线带来的影响。

Claude Code 官方建议的完整映射（快速开始）：`ANTHROPIC_MODEL`、`ANTHROPIC_DEFAULT_{HAIKU,SONNET,OPUS}_MODEL`、`CLAUDE_CODE_SUBAGENT_MODEL` 全部显式配置；Haiku 位设小模型、Subagent 与主模型一致；`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` 关掉遥测——文档原文：遥测请求「默认会走 `ANTHROPIC_BASE_URL` 并占用 Coding Plan 配额」。完整配置见 `references/tools-setup.md`。

## 6. 套餐、额度与刷新规则

### 档位与价格

| 档位 | 刊例价 | 2.5 折普惠活动价（2026-06-08 ~ 2026-11-08，首两个月） | 适用场景 |
|---|---|---|---|
| Lite | 40 元/月（120 元/季） | 9.9 元/月 | 中等强度开发任务，适合大多数开发者 |
| Pro | 200 元/月（600 元/季） | 49.9 元/月 | 复杂项目、高强度；用量 = Lite 的 5 倍 |

- 控制台 2026-09-03 实读：Pro **已售罄**。活动页写明「名额有限，先到先得」。
- 一个账号同一时间只有一个套餐生效；仅支持 Lite→Pro **升配**（补差价，有效期不变），不支持降配。
- 新客首购特惠（Lite 9.9 / Pro 49.9）已于 2026-03-17 暂停；现在的 9.9 / 49.9 来自 2.5 折普惠活动，第三个月起恢复原价。
- ⚠ 文档自相矛盾（退款）：FAQ 说「支持非七天无理由自助退订」（费用中心-退订管理，产品筛选「字节跳动大模型服务（豆包大模型）」）；新用户特惠活动页说「套餐购买后不支持退款」。以 FAQ（更新更晚）为准，但请以控制台实际入口为准。

### 额度（按请求次数估算）

官方预估基准：**Doubao Seed 2.0 Lite 模型 + Claude Code 未开启 Agent Team 模式**。

| 周期 | Lite | Pro |
|---|---|---|
| 每 5 小时 | 最多约 1,200 次请求 | 最多约 6,000 次 |
| 每周 | 最多约 9,000 次 | 最多约 45,000 次 |
| 每订阅月 | 最多约 18,000 次 | 最多约 90,000 次 |

文档反复强调这是估算：实际次数受「请求上下文长度、模型（抵扣系数）、项目复杂度、代码库规模、是否自动接受、是否开 thinking」影响；OpenClaw、Claude Code 开 Agent Team 会显著加速消耗。`glm-5.3`、`deepseek-v4-pro` 抵扣系数高。各模型的具体抵扣系数 ⚠ 文档未给出数值（只有活动页的相对折扣：Auto 系数 1；glm-5.3-flash 5 折等）。

### 刷新规则

- 5 小时限额：**以首次请求发生时间起算**，5 小时为周期定时刷新。
- 周限额：每周一 00:00:00 重置。
- 月限额：每订阅月第 1 日 00:00:00 重置。
- 耗尽后等待下一周期恢复，**不会**消耗其他资源包或账户余额（即不会静默转后付费）。
- 套餐有效期按自然月：01.04 买 1 个月 → 02.04 23:59；01.31 买 → 02.28 23:59。
- 用量在开通管理页面查看；也可用 Ark CLI 自然语言查询（§11）。

## 7. 使用限制："不能用于 API 调用"

官方口径（套餐概览 + FAQ，多处重复）：

> 套餐额度仅在 AI 编程工具中生效，不可用于 API 调用。在非 AI 编程工具中使用方舟 Coding Plan 权益对应的 Base URL 和 API Key 有可能被识别为滥用/违规，会导致订阅停用或账号封禁。

对开发者的含义：

- `/api/coding[/v3]` 在协议上就是 OpenAI / Anthropic 兼容的 HTTP 接口，技术上能用 SDK 直接调；但**官方明确不允许**把它当通用推理 API 接到自己的应用、脚本、批处理里。
- 需要在自己程序里调模型 → 用标准 API `/api/v3`（后付费）或 Agent Plan（Agent Plan 的图片/视频/语音模型允许 API 调用，文本/向量化同样不允许）。
- 团队使用：FAQ 说「Coding Plan 主要面向个人开发者，团队协作请使用方舟模型 API 按量付费」；但企业版（§15）已提供席位制团队方案——⚠ FAQ 该条与企业版文档并存，视为 FAQ 未更新。
- 判定标准（什么算"AI 编程工具"）⚠ 文档未说明；已列入支持列表的工具是安全边界。

## 8. 连通性验证请求（Chat Completions / Embeddings）

以下示例仅用于**验证 Key / Base URL / Model Name 是否配对正确**（例如工具报 404 时排查），不是把 Coding Plan 当 API 用的建议——见 §7。Coding Plan 文档本身**没有**给出任何直接 HTTP 调用示例和响应样例，以下请求体按 OpenAI 兼容协议书写。响应形态在 Agent Plan `/api/plan/v3` 实测为标准 OpenAI `chat.completion`（**已用真实 API 验证（2026-09-04，Agent Plan Medium）**），Coding Plan 入口预期一致但未直接实测。

### Chat Completions（OpenAI 协议）
**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/coding/v3/chat/completions`
**用途**: 用一条最小请求确认 Model Name 有效、Key 有 Coding Plan 权益。仅 Coding Plan 入口；标准入口对应 `/api/v3/chat/completions`（model 要填 Model ID / `ep-`），Agent Plan 入口对应 `/api/plan/v3/chat/completions`（Key 不同）。
**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | — | §4 小写 Model Name 或 `ark-code-latest`；**不能**填 `Auto`（实测 404）、`ep-`。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：带日期的 Model ID（`doubao-seed-2-0-lite-260428`）在 Plan 入口**会被接受但静默改版本**——响应 `model` 仍是 `doubao-seed-2-0-lite-260215`，与传 Name `doubao-seed-2.0-lite` 完全一样；老 Model ID `doubao-seed-1-8-251228` → 404 UnsupportedModel。别指望在 Plan 入口锁版本 |
| `messages[].role` | string | 是 | — | 仅支持 `system` / `assistant` / `user` / `tool`；**不支持 `developer`**。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`messages[0].role = "developer"` → **400** `{"error":{"code":"InvalidParameter","message":"The parameter `messages.role` specified in the request are not valid: invalid value: `developer`, supported values are: `system`, `assistant`, `user`, `tool`. ...","param":"","type":"BadRequest"}}`，见 §13 |
| `thinking` | object | 否 | 随模型（§4） | `{"type":"enabled"}` 开启深度思考，来自 FAQ 的工具配置。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`{"type":"disabled"}` 对 `doubao-seed-2.0-lite` 生效（默认开、`reasoning_tokens: 109` → 关后 0）；对 `glm-5.3` → **400**「thinking.type `disabled` is not supported by this model」 |
| `reasoning_effort` | string | 否 | ⚠ 文档未说明 | **已用真实 API 验证（2026-09-04，Agent Plan Medium）**（`glm-5.3`）：`"low"` → 200、`reasoning_tokens: 0`、无 `reasoning_content`（事实上关思考）；`"none"` → **400**「reasoning_effort `none` is not supported by this model」 |
| `max_tokens` / `max_completion_tokens` | int | 否 | — | **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：豆包（`doubao-seed-2.0-lite`）的 `max_tokens: 64` 不限制思维链（`completion_tokens: 110` = reasoning 109 + 回答 1）；`kimi-k3` 的 `max_tokens: 64` **把思维链算进去**，`finish_reason: "length"`、`content: ""` 回答被截空，去掉 `max_tokens` 改 `max_completion_tokens: 400` 后正常。用 kimi 系列请给足或改用 `max_completion_tokens` |
| `service_tier` | string | 否 | — | **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`"fast"` → **400** `{"error":{"code":"InvalidParameter","message":"The parameter `service_tier` specified in the request are not valid: fast service tier does not support coding plan. ...","param":"service_tier"}}`——Plan 入口不支持 fast tier，别传 |

**示例请求**

```bash
curl -sS https://ark.cn-beijing.volces.com/api/coding/v3/chat/completions \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"doubao-seed-2.0-lite","messages":[{"role":"user","content":"ping"}]}'
```

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["ARK_API_KEY"],                      # 普通方舟 API Key，不是 Agent Plan Key
    base_url="https://ark.cn-beijing.volces.com/api/coding/v3",
)
resp = client.chat.completions.create(
    model="doubao-seed-2.0-lite",                           # 小写 Model Name
    messages=[{"role": "user", "content": "ping"}],
)
print(resp.choices[0].message.content)
```

**示例响应**: 文档未提供。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**（Agent Plan 入口）：标准 OpenAI `chat.completion`——`choices[0].message.content`、思考模型另有 `choices[0].message.reasoning_content`、`usage.completion_tokens_details.reasoning_tokens`；注意 **`model` 字段返回的是带日期的 Model ID**（传 `doubao-seed-2.0-lite` 回 `"model":"doubao-seed-2-0-lite-260215"`；传 `ark-code-latest` 且控制台选 Auto 时回 `"model":"auto"`）。流式 `stream: true` + `stream_options.include_usage` 为标准 SSE，`delta.reasoning_content` 逐 token 下发，`usage` 在末尾 chunk 前均为 `null`。Coding Plan 入口预期一致。
**注意事项**
- 用 `/api/v3` 会成功返回但**走后付费**且要求 Model ID——这是最常见的"额度没扣、账单却涨"原因。
- Anthropic 协议对应路径为 `https://ark.cn-beijing.volces.com/api/coding/v1/messages`（Agent Plan 侧实测全路径 `/api/plan/v1/messages`）。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**（Agent Plan 入口）：`x-api-key` 与 `Authorization: Bearer` 两种头都接受；响应为标准 Anthropic Message，思维链是 `{"type":"thinking"}` block；`stream: true` 为标准 Anthropic SSE。**踩坑**：`model` 传 `claude-*`（如 `claude-sonnet-4-5`）不报错，被**静默路由到 `doubao-seed-2-1-turbo-260628`**——Coding Plan 入口是否同样映射未测，但 Claude Code 务必显式设 `ANTHROPIC_MODEL` 等全部模型变量（§5）。

### Embeddings（OpenAI 协议）
**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/coding/v3/embeddings`
**用途**: Coding Plan 唯一的向量化模型 `doubao-embedding-vision`，供工具做记忆检索；同样消耗套餐额度（按次数估算）。企业版同路径、换专属 Key。
**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | — | 固定 `doubao-embedding-vision`；文档建议固定同一版本、勿混用 |
| `input` | string / array | 是 | — | 文本。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`POST /embeddings` **只收字符串**（或字符串数组）；传 `[{"type":"text",...}]` 多模态对象数组 → **400**「The parameter `input[0]` ... expected a string, but got `map[text:a cat type:text]`」。图文向量化要走 `POST /embeddings/multimodal`（`input` 为对象数组，响应是 `data.embedding` **对象**而非 `data[0].embedding` 数组） |
| `dimensions` | int | 否 | **2048** | **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：不传时默认 **2048** 维（`/embeddings` 与 `/embeddings/multimodal` 一致；文档各处 2048 / 1024 / 3072 写法不一，以实测为准）；传 `dimensions: 1024` **生效**。OpenViking 配置里的 `"dimension": 1024` 即对应此参数 |

**示例请求**

```bash
curl -sS https://ark.cn-beijing.volces.com/api/coding/v3/embeddings \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"doubao-embedding-vision","input":"hello"}'
```

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["ARK_API_KEY"],
                base_url="https://ark.cn-beijing.volces.com/api/coding/v3")
emb = client.embeddings.create(model="doubao-embedding-vision", input="hello")
print(len(emb.data[0].embedding))
```

**示例响应**: 文档未提供。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**（Agent Plan 入口）：`{"object":"list","data":[{"object":"embedding","index":0,"embedding":[...]}],"model":"doubao-embedding-vision-251215","usage":{"prompt_tokens":20,"total_tokens":20}}`，`embedding` 默认 2048 维。
**注意事项**
- 方舟「兼容 OpenAI SDK」页说「向量化能力模型不支持 OpenAI API，请使用方舟 SDK」，而 Coding Plan 的 OpenClaw / OpenViking 配置又用 `provider: openai` + `/api/coding/v3` 调 `doubao-embedding-vision`。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Plan 入口的 OpenAI 形态 `POST /embeddings` **可用**（字符串输入），该文档说法在 Plan 入口不成立；OpenClaw `provider: openai` 这样配是对的。

## 9. 专属权益：Embedding 模型（OpenClaw / OpenViking）

核心配置：模型 `doubao-embedding-vision`（对应 `doubao-embedding-vision-251215`）；Base URL `https://ark.cn-beijing.volces.com/api/coding/v3`（OpenAI 协议）；Key = 方舟 API Key。**会消耗套餐额度**，按调用次数估算。

### OpenClaw（`~/.openclaw/openclaw.json`，或 `openclaw dashboard` → 配置 → All Settings → Raw）

在 `agents.defaults` 下增加 `memorySearch`（文档原文配置）：

```json
{
  "agents": {
    "defaults": {
      "memorySearch": {
        "provider": "openai",
        "model": "doubao-embedding-vision",
        "remote": {
          "baseUrl": "https://ark.cn-beijing.volces.com/api/coding/v3",
          "apiKey": "<ARK_API_KEY>"
        }
      }
    }
  }
}
```

Web UI 方式：Save → Update；终端方式：`openclaw gateway restart`。

### OpenViking（`~/.openviking/ov.conf`）

```json
{
  "embedding": {
    "dense": {
      "api_base" : "https://ark.cn-beijing.volces.com/api/coding/v3",
      "api_key"  : "<ARK_API_KEY>",
      "provider" : "volcengine",
      "dimension": 1024,
      "model"    : "doubao-embedding-vision"
    },
    "max_concurrent": 10
  }
}
```

注意 OpenClaw 用 `provider: "openai"`，OpenViking 用 `provider: "volcengine"`——这是两个工具各自的 provider 枚举，不是方舟侧的差异。

## 10. 专属权益：ArkClaw

ArkClaw = 火山引擎云端一键部署的 OpenClaw（一对一专属 ECS，7×24 在线），可直接使用已订阅的 Coding Plan。入口：方舟体验中心 → Agent → ArkClaw → 立即开始。

**权益现状（对新订阅者基本不可用）**：

- 2026-05-18 12:00 起「Coding Plan Pro 套餐赠送 ArkClaw」活动**已下线**；新购 Pro、Lite 升配 Pro 均不再赠送。
- 2026-03-24 起 Lite 新购用户不再赠送 7 日免费体验。
- 历史 Pro 用户（下线前已购且已在体验中心创建）：权益用到套餐到期；Pro 到期后 ArkClaw 被删除、数据保留 24 小时；续费延期则随套餐延长。
- 一个主账号只能开通一个 ArkClaw，子账号共享数据。
- 子账号创建需先由管理员授予 `iam:CreateRole`、`iam:GetRole`、`iam:AttachRolePolicy`、`iam:ListAttachedRolePolicies`。
- ⚠ 功能发布公告 2026-03-02 条目仍写「订阅方舟 Coding Plan 后，可免费解锁 ArkClaw」，与下线公告矛盾——以下线公告为准。

## 11. Ark CLI 在 Coding Plan 下的用法

Ark CLI（`@volcengine/ark-cli`，需 Node.js ≥ 16）是官方推荐的工具配置入口（ArkCLI Helper 取代了旧的 Ark Helper），同时覆盖 Coding Plan 的**交易 / 配置 / 用量**。

```bash
npm install -g @volcengine/ark-cli@latest
arkcli --version
arkcli auth login          # 首次：选 Project（可选「账号全部资源」）、选消费模式 Type = coding-plan
arkcli auth status
arkcli config reset        # 想重选登录配置时先执行，再 auth login
arkcli helper              # TUI：选 profile `coding-plan_cn-beijing_personal (Coding Plan)` → 默认 model → 要配置的 AI Agent（Claude Code / Codex / OpenCode / OpenClaw / Trae 等）
```

交易命令（不加 `--yes` 只返回订单预览与协议链接，建议先预览）：

```bash
arkcli plans buy   --plan coding-plan --type pro  --duration 1        # 预览；--type lite|pro，--duration 1-12 月，默认 1
arkcli plans buy   --plan coding-plan --type pro  --duration 1 --yes  # 真实下单
arkcli plans renew --plan coding-plan --duration 1 [--yes]
arkcli plans get                                                        # 查询账号下套餐状态
```

配置与用量目前文档只给了"通过 Agent 自然语言调用"的示例提示词（无对应子命令）：「Coding Plan Pro 支持哪些模型？」「我这个月 Coding Plan 还剩多少额度？」「我五小时额度还剩多少？」「我本周 doubao-seed-2.0-lite 用了多少额度？」——即在已用 arkcli 配好的 Agent 里直接问。对应的 `arkcli usage ...` 类子命令 ⚠ 文档未说明。

也可以把提示词「根据下面命令帮我安装 Ark CLI：https://lf3-static.bytednsdoc.com/obj/eden-cn/psjryh/ljhwZthlaukjlkulzlp/intro/volc.md」交给任意 AI Agent 自动完成安装登录。

## 12. 工具 → 协议 → Base URL 速查

详细的逐工具配置（含 1M 上下文、思考开关、遥测关闭）见 `references/tools-setup.md`。本表只回答"填哪条 Base URL"。

| 工具 | 协议 | Base URL | 依据 |
|---|---|---|---|
| Claude Code | Anthropic | `https://ark.cn-beijing.volces.com/api/coding` | 快速开始 |
| OpenClaw | OpenAI（`"api": "openai-completions"`） | `https://ark.cn-beijing.volces.com/api/coding/v3` | FAQ 配置样例 |
| OpenCode | OpenAI（`@ai-sdk/openai-compatible`） | `.../api/coding/v3` | FAQ 配置样例 |
| Cline / Cursor / Kilo Code / Roo Code | OpenAI 兼容 | `.../api/coding/v3` | FAQ「兼容 OpenAI API 工具」 |
| OpenViking（仅 Embedding） | OpenAI 兼容 | `.../api/coding/v3` | 记忆增强页 |
| Codex CLI / TraeCode / Hermes Agent / DeepSeek Harness / Pi / WorkBuddy / ZCode | ⚠ 本文输入页未说明 | 见 `references/tools-setup.md` | — |

## 13. 开发与排错 FAQ

以下来自官方 FAQ，默认 **（文档原文，未实测）**；标了「已用真实 API 验证」的条目是在 Agent Plan 入口实测过的报错原文。

**开启深度思考**
- Claude Code：`~/.claude/settings.json` 的 `env` 里加 `"CLAUDE_CODE_EXTRA_BODY": "{\"thinking\":{\"type\":\"enabled\"}}"`，重启 `claude`。
- OpenCode：`~/.config/opencode/opencode.json` 中该模型的 `options` 加 `{"thinking": {"type": "enabled"}}`；看不到思考内容时 `ctrl+p` 搜 `think` → `Show thinking`。
- OpenClaw：消息级 `/think:<level>` 或 `/t <level>`；会话级单独发一条 `/think:<level>`；全局 `openclaw config set agents.defaults.thinkingDefault high` 后 `openclaw gateway restart`。level 取值：`off / minimal / low / medium / high / xhigh`。
- 上述三种方式最终都落到请求体的 `thinking: {"type": "enabled"}`；`glm-5.3` 无法关闭，`deepseek-v4-*` 默认开可手动关（§4）。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：对 `glm-5.3` 传 `thinking.type: disabled` 会 **400**（工具里配了「关闭思考」再选 glm-5.3 会直接报错，不是静默忽略）；想让 glm-5.3 少想，传 `reasoning_effort: "low"`（实测 `reasoning_tokens: 0`）；`reasoning_effort: "none"` 也是 400。

**`HTTP 400 ... invalid value: developer, supported values are: system, assistant, user, tool.`**
- 原因：方舟 API 不支持 OpenAI 新版的 `developer` role。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：完整报错 `{"error":{"code":"InvalidParameter","message":"The parameter `messages.role` specified in the request are not valid: invalid value: `developer`, supported values are: `system`, `assistant`, `user`, `tool`. ...","param":"","type":"BadRequest"}}`，HTTP 400。
- OpenClaw 修法：在 **model 对象内**（不是 provider 级，否则报 `Unrecognized key: "compat"`）加 `"compat": { "supportsDeveloperRole": false }`，然后 `pkill -f openclaw && openclaw gateway restart`。FAQ 样例里 model 还带 `"reasoning": true`、`"contextWindow": 200000`、`"maxTokens": 8192`（这是工具侧声明，与 §4 真实窗口无关）。
- 其他工具若发 `developer` role，同理需改成 `system`。

**`run error: 404 The model or endpoint xxx does not exist or you do not have access to it`（OpenClaw）**
- 排查顺序：① `~/.openclaw/openclaw.json`（全局）与 `~/.openclaw/agents/main/agent/models.json`（单 Agent 本地配置，**优先级更高**）的 `baseUrl` 等是否一致；② 不一致就删掉 `models.json`；③ 按文档重配 `openclaw.json` 后 `openclaw gateway restart`。
- 通用排查（本文归纳，非文档原文）：Base URL 是否 `/api/coding/v3` 而非 `/api/v3`；`model` 是否小写 Model Name 而非 Model ID / `ep-`；该模型是否已下线（§14）；账号是否有生效中的 Coding Plan。

**OpenClaw 无法识别图片**
- 模型 `input` 要含 `"image"`（如 `kimi-k2.7-code` 配 `["text", "image"]`）；`agents.defaults.imageModel.primary` 显式指向 `volcengine-plan/kimi-k2.7-code`，并在 `agents.defaults.models` 里保留别名；重启 gateway。

**`gateway connect failed: Error: pairing required`（OpenClaw 安装）**
- `rm -rf ~/.openclaw/devices ~/.openclaw/identity && openclaw gateway install --force && openclaw gateway start`。

**额度被静默消耗**
- Claude Code 遥测走 `ANTHROPIC_BASE_URL` 占配额 → `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`（ArkCLI Helper 会自动加）。
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**（Agent Plan 入口）：Anthropic 入口对 `model: claude-*` **不报错而是静默路由到 `doubao-seed-2.1-turbo`**（高系数模型）。Claude Code 没把 `ANTHROPIC_MODEL` / `ANTHROPIC_DEFAULT_{HAIKU,SONNET,OPUS}_MODEL` / `CLAUDE_CODE_SUBAGENT_MODEL` 全配上时就会中招。Coding Plan 入口是否同样映射未测，按同样标准配全。

**kimi 模型回答为空 / `finish_reason: "length"`**
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**（`kimi-k3`）：kimi 的 `max_tokens` **包含思维链**，`max_tokens: 64` 时思维链就耗掉 61，`content: ""`。去掉 `max_tokens`、改 `max_completion_tokens`（或给足）后正常。豆包模型的 `max_tokens` 不限制思维链，没有这个问题。`kimi-k2.7-code` 文档写「最大输出 32k（含思维链）」，同一口径。

**`service_tier` 报 400**
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：传 `service_tier: "fast"` → `{"error":{"code":"InvalidParameter","message":"The parameter `service_tier` specified in the request are not valid: fast service tier does not support coding plan. ...","param":"service_tier"}}`——报错文案直接点名 coding plan（在 Agent Plan 入口也是这段文案）。Plan 入口不支持 fast tier，工具 / SDK 里如有 `service_tier` 默认值请去掉。

**Key 与 Base URL 不配对 → 401**
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Agent Plan 专属 Key 打 `/api/coding/v3` 或 `/api/v3` → **401** `AuthenticationError`「The API key or AK/SK in the request is missing or invalid.」。看到 401 先查 Key 类型和 Base URL 里 `coding` / `plan` 是否对得上，再查 Key 本身。

**旧 Ark Helper**
- 升级：`curl -fsSL https://lf3-static.bytednsdoc.com/obj/eden-cn/ylwslo-yrh/ljhwZthlaukjlkulzlp/install.sh | sh`；卸载：`npm uninstall -g @byted-aml/ark-helper`。已被 ArkCLI Helper 取代。

错误码总表见方舟文档 82379/1299023（本文未收录）。

## 14. 影响开发者的公告：模型上线 / 下线 / 活动

### 当前在线模型的上线时间

| 日期 | 事件 |
|---|---|
| 2026-08-28 | 新增 `glm-5.3-flash`；首两周抵扣系数 5 折（至 09-11 23:59:59） |
| 2026-08-26 | `deepseek-v4-pro` 正式版，支持 model name 及控制台选择 |
| 2026-08-21 | 新增 `doubao-seed-evolving` |
| 2026-08-14 | 新增 `glm-5.3` |
| 2026-08-04 / 08-07 | `deepseek-v4-flash` 正式版上线 / 全量，支持 model name 直接调用 |
| 2026-07-23 | 新增 `doubao-seed-2.1-turbo` |
| 2026-06-18 | 新增 `kimi-k2.7-code` |
| 2026-06-08 | 新增 `minimax-m3` |
| 2026-03-31 | 新增 Embedding `doubao-embedding-vision`；支持接入 OpenViking |
| 2026-03-06 | 新增 `doubao-seed-2.0-lite` |
| 2026-02-06 | 支持在配置文件用 Model Name 配置模型（此前只有控制台切换） |

### 下线节奏（配置里还写着这些名字的要改）

下线流程固定三步：启动&通知（同日起**新用户**——买了套餐但没用过该模型的——不能再用）→ 约两周后正式停服。

| 模型 | 停服时间 | 建议迁移 |
|---|---|---|
| `glm-5.2` | 2026-08-31 14:00 | `glm-5.3`（**到期未迁移会自动路由到 glm-5.3**，是唯一有自动路由的下线） |
| `kimi-k2.6`、`minimax-m2.7` | 2026-08-18 | `kimi-k2.7-code`、`minimax-m3` |
| `doubao-seed-2.0-code`、`doubao-seed-2.0-pro` | 2026-08-08 | `doubao-seed-2.1-turbo` |
| `doubao-seed-code` | 2026-08-05 | `doubao-seed-2.0-code`（本身也已下线，实际应迁 `doubao-seed-2.1-turbo`） |
| `glm-5.1`、`deepseek-v3.2` | 2026-06-30 | `glm-5.2`（已下线）→ `glm-5.3`；`deepseek-v4-pro` |
| `minimax-m2.5`、`kimi-k2.5`、`glm-4.7` | 2026-06-08 | — |
| `kimi-k2-thinking` | 2026-04-22 | — |

下线通知渠道：短信、站内信。规避方式：用 `ark-code-latest` 或 `*-latest`（§5）。

### 活动 / 售卖状态

- Pro 档控制台**已售罄**（2026-09-03 实读）；2.5 折普惠活动「名额有限」。
- Auto 模式 2026-06-10 18:00 ~ 2026-11-08 抵扣系数为 1（可路由到 kimi-k3，夜间比例提升）。
- `glm-5.3-flash` 至 2026-09-11 抵扣 5 折（配额相当于原用量 200%）。`deepseek-v4-pro`（4 折）、`kimi-k2.7-code`（2.5 折）、`glm-5.2` 的上线折扣已结束。
- 抵扣系数活动「不改变套餐内其他模型、Harness、套餐额度刷新规则与使用限制」。

## 15. 企业版差异

Coding Plan 企业版（Team）= 席位制的 Coding Plan，模型列表、Base URL、`ark-code-latest` / Auto 规则、额度刷新规则与个人版**完全一致**。差异集中在 Key、购买、权限：

| 维度 | 个人版 | 企业版 |
|---|---|---|
| Key | 方舟 API Key | **席位专属 API Key**——文档原文「Coding Plan 企业版专属 API Key 与火山方舟平台的 API Key 不同，请勿混用」。每席位一把，分配给用户后生成；席位过期即失效，重新生效后激活；席位解绑再绑定后 Key **会更新**（工具里要重配） |
| 档位 / 价格 | Lite 40 / Pro 200 元/月 | **Team Lite 120 元/月 / Team Pro 600 元/月**，每席位含 1 个对应个人版套餐的用量 |
| 起售 | 1 个账号 | **5 席位起售**；后续增购按需，但主账号席位总数 ≥ 5 |
| 购买时长 | 最多连续 6 个月（活动规则） | 单席位一次最多 12 个月，存量 + 新购 ≤ 24 个月 |
| 升降配 / 退订 | 支持升配；退订见 §6 ⚠ | **不支持升配或降配**；**不支持无理由退订**。想换档 = 解绑再绑到另一档席位（一个席位每订阅月只能换绑一次） |
| 席位绑定 | — | 一个席位一种套餐；一个子账号在一个 Project 下最多绑一个席位；席位从属项目，不同项目不互通 |
| 谁能买 | 完成实名认证 | 完成**企业认证**且有 `ArkFullAccess` 的管理员账号（主账号默认有） |
| 控制台 | 开通管理 → 订阅（`advancedActiveKey=subscribe`） | `console.volcengine.com/ark/region:cn-beijing/subscription/coding-plan-enterprise` 或开通管理 `advancedActiveKey=enterprise`：席位管理（单个/批量绑定、解绑、续费、自动续费）、增购席位、用量查看（所有席位）；席位用户看「我的 → 使用配置」切模型、查专属 Key、查 5 小时/周/月用量 |
| 配额管理 | — | 项目配置 → 配额管理 → CodingPlan：按项目分配席位额度；未配置则所有项目共享；调主账号总配额要联系销售 |
| 数据 | 参与数据授权（AI Coding 数据匿名化后用于模型优化，见特惠活动页「数据授权说明」） | 「不记录用户请求与模型返回数据」 |
| 使用限制口径 | 仅 AI 编程工具 | 「仅在 AI 编程或 AI 智能体等工具中生效」，其余同 |

**IAM 用户组（席位 + 权限必须同时配，否则子用户看不到也用不了）**：

| 用户组 | 成员 | 必选权限 |
|---|---|---|
| `CodingPlanTeam_Admin` | 管理席位的管理员 | `ArkFullAccess` |
| `CodingPlanTeam_User` | 只用本人席位 | `ArkPlanUserAccess` |

在企业账号下购买 / 续费**个人版**也需要加入管理员用户组。

**只让席位用户看到自己的专属 Key、看不到后付费 Key**（企业版 FAQ）：新建项目并在该项目下购买企业版（企业版 Key 不会出现在通用 API Key 列表）→ 该项目的 API Key 管理 → 安全设置 → 开启「限制成员权限」→ 用户 / 用户组授予 `ArkReadOnlyAccess` 并「限制到项目资源」→ 在该项目下分配席位。结果：席位用户不能创建/查看后付费 Key，但能查看自己的席位专属 Key。

⚠ 企业版快速开始正文写「`<ARK_API_KEY>`：替换为您自己的专属 API Key」，但链接指向通用 `apikey` 页面；核心配置区又强调专属 Key 与通用 Key 不同——以「席位专属 API Key（企业版页面获取）」为准。

企业版 Embedding：与 §9 完全相同的配置（同模型、同 `/api/coding/v3`），只是 `<ARK_API_KEY>` 换成席位专属 Key。企业版工具配置页与个人版是平行的一套（82379/2277823 Claude Code、2277824 OpenClaw、2277825 OpenCode 等），见 `references/tools-setup.md`。

---

## 来源页面

个人版
- 套餐概览 — https://www.volcengine.com/docs/82379/1925114 — 2026-08-31
- 快速开始 — https://www.volcengine.com/docs/82379/1928261 — 2026-08-28
- 常见问题 — https://www.volcengine.com/docs/82379/2165245 — 2026-08-24
- 记忆增强-Embedding模型 — https://www.volcengine.com/docs/82379/2279748 — 2026-04-14
- ArkClaw — https://www.volcengine.com/docs/82379/2229107 — 2026-08-06
- Ark CLI：Coding Plan 个人版使用指南 — https://www.volcengine.com/docs/82379/2656115 — 2026-08-21

活动及公告
- 功能发布公告 — https://www.volcengine.com/docs/82379/2222865 — 2026-08-28
- 模型上线公告 — https://www.volcengine.com/docs/82379/2578683 — 2026-08-28
- 模型下线公告 — https://www.volcengine.com/docs/82379/2578687 — 2026-08-24
- 新用户特惠活动 — https://www.volcengine.com/docs/82379/1928220 — 2026-07-22
- Agent/Coding Plan 指定模型抵扣系数限时折扣活动 — https://www.volcengine.com/docs/82379/2533566 — 2026-08-30
- Coding Plan Lite & Pro 套餐 2.5 折普惠活动 — https://www.volcengine.com/docs/82379/2525065 — 2026-07-27
- Coding Plan Pro 套餐赠送 ArkClaw 活动下线公告 — https://www.volcengine.com/docs/82379/2406398 — 2026-05-18

企业版
- 套餐概览 — https://www.volcengine.com/docs/82379/2276791 — 2026-08-31
- 快速开始 — https://www.volcengine.com/docs/82379/2277233 — 2026-08-31
- 控制台操作指南 — https://www.volcengine.com/docs/82379/2277820 — 2026-07-22
- 用户组与权限管理 — https://www.volcengine.com/docs/82379/2602658 — 2026-07-23
- 常见问题 — https://www.volcengine.com/docs/82379/2307902 — 2026-08-24
- 记忆增强-Embedding模型（企业版） — https://www.volcengine.com/docs/82379/2310403 — 2026-08-06

控制台实读
- Coding Plan 售卖页 — https://console.volcengine.com/ark/region:cn-beijing/subscription/coding-plan — 2026-09-03（当前账号未订阅；Pro 已售罄）

真实 API 验证（Agent Plan 入口，非 Coding Plan 入口）
- `volcengine-ark-workspace/verification-findings.md`、`verification-log.jsonl` — 2026-09-04（Agent Plan Medium 专属 Key；`/api/coding/v3` 仅验证了 Agent Plan Key 打过去返回 401）
