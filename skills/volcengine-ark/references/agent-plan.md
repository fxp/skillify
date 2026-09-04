# 火山方舟 Agent Plan（个人版为主，企业版差异见末节）

本文覆盖：Agent Plan 是什么、与 Coding Plan / 标准后付费 API 的区别、专属 Base URL 与专属 API Key、四档套餐与各档支持的模型 / Harness、AFP 抵扣公式与全部系数、额度与刷新规则、超额后付费、`ark-code-latest` / `auto` 与 Model Name 两种配模型方式、在 Agent Plan 下用 API 调向量化 / 图片 / 视频 / 语音模型、Harness 一览、Ark CLI、常见问题、近期公告、企业版差异。各 AI 工具（Claude Code / OpenCode / OpenClaw …）的逐步配置**不在本文**，详见 `references/tools-setup.md`。

## 目录
1. [Agent Plan 是什么，与 Coding Plan / 标准 API 的区别](#1-agent-plan-是什么与-coding-plan--标准-api-的区别)
2. [专属 Base URL 与专属 API Key](#2-专属-base-url-与专属-api-key)
3. [四档套餐：价格、额度、支持的模型与 Harness](#3-四档套餐价格额度支持的模型与-harness)
4. [额度刷新、有效期、升配与退订规则](#4-额度刷新有效期升配与退订规则)
5. [AFP 抵扣公式与全部抵扣系数](#5-afp-抵扣公式与全部抵扣系数)
6. [配模型的两种方式：ark-code-latest / auto 与 Model Name](#6-配模型的两种方式ark-code-latest--auto-与-model-name)
7. [超额后付费：规则、支持范围、开关位置](#7-超额后付费规则支持范围开关位置)
8. [用 API 调用多模态模型（向量化 / 图片 / 视频 / 语音）](#8-用-api-调用多模态模型向量化--图片--视频--语音)
9. [Harness 一览](#9-harness-一览)
10. [Ark CLI 在 Agent Plan 下的用法](#10-ark-cli-在-agent-plan-下的用法)
11. [工具 → 协议 → Base URL 速查](#11-工具--协议--base-url-速查)
12. [常见问题](#12-常见问题)
13. [近期公告：模型上下线、抵扣系数调整、权益变化](#13-近期公告模型上下线抵扣系数调整权益变化)
14. [企业版与个人版的差异](#14-企业版与个人版的差异)
15. [套餐提货券](#15-套餐提货券)
- [来源页面](#来源页面)

---

## 1. Agent Plan 是什么，与 Coding Plan / 标准 API 的区别

方舟 Agent Plan 是面向个人用户的**订阅式**大模型套餐包（2026-05-07 上线），在 Coding Plan 基础上升级：支持全模态模型（文本、向量化、图片生成、视频生成、语音）与专属 Harness（豆包搜索、专业数据集、Agent 记忆、AI Native 应用开发底座、Agent 进化、Computer Use Agent），用 **AFP（Agent Fuel Point，Agent 燃料值）** 作为统一用量单位做积分抵扣。

| 对比 | 标准后付费 API | Coding Plan 个人版 | Agent Plan 个人版 |
|---|---|---|---|
| 定位 | 通用推理 API，按 token 后付费 | Coding 场景订阅包 | Agent 场景订阅包，多模态 + Harness |
| Base URL | `https://ark.cn-beijing.volces.com/api/v3` | `.../api/coding/v3`（OpenAI 协议）/ `.../api/coding`（Anthropic 协议） | `.../api/plan/v3`（OpenAI 协议，已支持 Responses API）/ `.../api/plan`（Anthropic 协议） |
| API Key | 方舟 API Key | 方舟 API Key（同一把） | **Agent Plan 专属 API Key**（与方舟 API Key、Coding Plan Key 均不通用） |
| `model` 字段 | 带日期版本的 Model ID（如 `doubao-seed-2-1-pro-260628`）或接入点 `ep-xxxx` | 小写 Model Name（`glm-5.3`、`doubao-seed-2.1-turbo`…）或 `ark-code-latest` | 小写 Model Name、`ark-code-latest`（**`auto` 不能直填**，实测 404，见第 6 节）；多模态用 `doubao-seedream-5.0-lite` / `doubao-seedance-2.0*` / `doubao-seed-tts-2.0` 等 |
| 模型范围 | 全部开通模型 | 语言模型、向量化模型 | 语言、向量化、视觉（生图 / 生视频）、语音 |
| Harness | — | / | 豆包搜索、专业数据集、Agent 记忆、AI Native 应用开发底座、Agent 进化、CUA |
| 档位 | — | 2 档（Lite / Pro） | 4 档（Small / Medium / Large / Max） |
| 计费 | 按 token | 预估模型调用次数 | AFP 抵扣，用量可查 |
| 控制台 | 开通管理 | Coding Plan 控制台（`advancedActiveKey=subscribe`） | Agent Plan 控制台（`advancedActiveKey=agentPlan`） |

**核心约束（文档原文）**：「文本生成模型及向量化模型不可用于 API 调用，在非 AI 工具中使用 Agent Plan 权益对应的 Base URL 和 API Key 有可能被识别为滥用/违规，会导致订阅停用或账号封禁。」而图片 / 视频 / 语音模型在 Agent Plan 中官方就是通过 API 接入（见第 8 节）。

---

## 2. 专属 Base URL 与专属 API Key

### 2.1 Base URL（三套入口绝不能混用）

**注意事项 —— 已用真实 API 验证（2026-09-04，Agent Plan Medium），按踩坑代价排序**
1. **Anthropic 入口会把 `claude-*` 模型名静默路由到 `doubao-seed-2.1-turbo`（抵扣系数 2.5）**：`POST /api/plan/v1/messages` 传 `model: "claude-sonnet-4-5"` → 200，响应 `"model":"doubao-seed-2-1-turbo-260628"`，不报错。Claude Code 忘设 `ANTHROPIC_MODEL` / `ANTHROPIC_DEFAULT_*_MODEL` 时不会失败，而是悄悄按 2.5 系数烧 AFP —— 这是最容易白扣额度的坑，务必显式配全模型名（见 `references/tools-setup.md` §3）。
2. **Agent Plan 专属 Key 只在 `/api/plan*` 有效**：拿它打 `/api/v3/chat/completions` 与 `/api/coding/v3/chat/completions` 都是 **401** `{"error":{"code":"AuthenticationError","message":"The API key or AK/SK in the request is missing or invalid. ...","type":"Unauthorized"}}`；打 `/api/plan/v3/chat/completions` 200。用错入口是**直接鉴权失败**，不是"套餐不支持"、也不是静默走后付费。
3. **`auto` 不能直填**：`model: "auto"` → **404** `UnsupportedModel`（控制台「Model Name: auto」标注有误），Auto 只能 `ark-code-latest` + 控制台选 Auto。
4. **Plan 入口接受带日期的 Model ID 但静默改版本**：`doubao-seed-2-0-lite-260428` → 200，响应 `model` 却是 `doubao-seed-2-0-lite-260215`；Model Name `doubao-seed-2.0-lite` 实际解析到的也是 `260215`（不是模型列表页最新的 `260428`）。想锁版本在 Plan 入口做不到。
5. `service_tier: "fast"` → **400** `InvalidParameter`「fast service tier does not support coding plan」（Agent Plan 入口报的是 coding plan 文案）。

| 用途 | Base URL / 地址 | 鉴权头 |
|---|---|---|
| OpenAI 兼容协议工具（Chat Completions；控制台注明「已支持 Responses API」） | `https://ark.cn-beijing.volces.com/api/plan/v3` | `Authorization: Bearer $ARK_AGENT_PLAN_API_KEY` |
| Anthropic 兼容协议工具（Claude Code 等） | `https://ark.cn-beijing.volces.com/api/plan`（Messages 接口全路径 `POST /api/plan/v1/messages`） | Claude Code 用 `ANTHROPIC_AUTH_TOKEN`。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：原生 HTTP 请求 `x-api-key: <PlanKey>` 与 `Authorization: Bearer <PlanKey>` **两种头都接受**（各配 `anthropic-version: 2023-06-01`），均 200；响应为标准 Anthropic Message 对象，思维链以 `{"type":"thinking","thinking":"..."}` block 返回，`usage` 含 `cache_read_input_tokens`；`thinking: {"type":"disabled"}` → 200 只剩 `text` block；`stream: true` → 标准 Anthropic SSE（`event: message_start` / `content_block_start` / `content_block_delta`(`text_delta`) …）。模型名映射见上方注意事项 1 |
| 图片生成 API | `https://ark.cn-beijing.volces.com/api/plan/v3/images/generations` | Bearer |
| 视频生成 API | `https://ark.cn-beijing.volces.com/api/plan/v3/contents/generations/tasks[/{id}]` | Bearer |
| 向量化（OpenAI SDK / OpenClaw / OpenViking 配置） | `https://ark.cn-beijing.volces.com/api/plan/v3`（`POST /embeddings` 与 `POST /embeddings/multimodal` 实测均可用，见 8.1） | Bearer |
| 语音 TTS / ASR | `wss://openspeech.bytedance.com/api/v3/plan/...`、`https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional` | `X-Api-Key: <专属 Key>` + `X-Api-Resource-Id` |
| 专业数据集 MCP | `https://datapro.hqd.cn-beijing.volces.com/mcp`（streamable-http） | `X-Agent-Plan-Key: <专属 Key>` |

控制台原话（Agent Plan 使用配置页）：「请勿使用 https://ark.cn-beijing.volces.com/api/v3，接入会产生额外费用。」文档同义：「Agent Plan 对应的 API 接口信息中包含 `/plan`，请勿混用其他 API 接口。」「产生额外费用」指的是拿**方舟 API Key** 打 `/api/v3`（走后付费）；**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：**Agent Plan 专属 Key** 打 `/api/v3` 或 `/api/coding/v3` 不会静默扣费，而是 401 `AuthenticationError`（见上方注意事项 2）。

### 2.2 专属 API Key

- 获取位置：Agent Plan 控制台 → **使用配置** 页签 → 第 3 步「配置专属API Key」。控制台原文：「Agent Plan个人版专属API Key是访问火山方舟大模型服务的重要凭证，长期有效」。列表列为 API Key（掩码）/ 创建时间 / 操作「更新API KEY」（轮换）。**一个账号只有一把**。
- 轮换：控制台「更新API KEY」，或 `arkcli plans personal rotate-apikey`（需二次确认，执行后旧 Key 立即失效）。
- 与其他 Key 的关系：「其他方舟 API Key 如 Coding Plan API Key 无法在 Agent Plan 中使用」；反向亦然。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Agent Plan Key → `/api/v3` **401**、→ `/api/coding/v3` **401**（同一段 `AuthenticationError` 报错）、→ `/api/plan/v3` 200（`model: doubao-seed-2.0-lite` 返回 `"model":"doubao-seed-2-0-lite-260215"`）。反向（方舟 Key 打 `/api/plan/v3`）无标准 Key 未测，推测同为 401。Agent 记忆（OpenViking）另有自己的 OpenViking API Key（见 9.3），不是 Agent Plan Key。
- 本文示例统一从环境变量 `ARK_AGENT_PLAN_API_KEY` 读取（官方示例写作 `AGENT_API_KEY`，语义相同）。
- 同一订阅套餐可在所有支持的工具中使用，**额度共享**。

---

## 3. 四档套餐：价格、额度、支持的模型与 Harness

### 3.1 价格与额度

| 套餐 | Small | Medium | Large | Max |
|---|---|---|---|---|
| 价格 | 40 元/月 | 200 元/月 | 500 元/月 | 1000 元/月 |
| 月额度（AFP） | 20,000 | 100,000 | 250,000 | 500,000 |
| 周额度（AFP） | 7,000 | 35,000 | 87,500 | 175,000 |
| 5 小时额度（AFP） | 2,000 | 10,000 | 25,000 | 50,000 |
| 日额度（AFP，仅部分模型 / Harness 适用） | 10,000 | 50,000 | 125,000 | 250,000 |
| 建议并行项目数（TPM 提示） | 单个项目 | 1–2 个 | 2+ 个 | 2+ 个 |

- 日额度统一为月额度的一半。图片生成、视频生成、语音模型、Harness **没有 5 小时 / 周额度限制**，仅受日额度、月额度限制。
- 官方注意：「Small、Medium 套餐仅供轻量化体验，不支持视频生成，建议选购 Large 和 Max」。
- 超高 TPM 需求建议用后付费 API。控制台「用量统计」可查模型调用明细、Harness 用量明细，明细数据延迟 0.5–1 天；超额后付费部分用量仅作预估，以账单为准。

### 3.2 支持的模型与 Harness（完整表）

| 分类 | 领域 | Model Name | 长度限制 | Small | Medium | Large | Max |
|---|---|---|---|---|---|---|---|
| 模型 | 文本生成（极速） | `doubao-seed-2.0-mini` | 上下文 256k / 最大输出 128k | √ | √ | √ | √ |
| | 文本生成（标准） | `doubao-seed-2.0-lite` | 256k / 128k | √ | √ | √ | √ |
| | 文本生成（标准） | `deepseek-v4-flash` | 1024k / 384k | √ | √ | √ | √ |
| | 文本生成（标准） | `glm-5.3-flash`（原生多模态，支持图片输入） | 1024k / 128k | √ | √ | √ | √ |
| | 文本生成（进阶） | `doubao-seed-2.1-turbo` | 256k / 256k | √ | √ | √ | √ |
| | 文本生成（进阶） | `doubao-seed-evolving` | 1024k / 256k | √ | √ | √ | √ |
| | 文本生成（进阶） | `minimax-m3` | 1024k / 128k | √ | √ | √ | √ |
| | 文本生成（进阶） | `glm-5.3`（别名 `glm-latest`，实测别名有效；默认开启思考，`thinking.disabled` 实测 400，但 `reasoning_effort: "low"` 实测 `reasoning_tokens: 0`，见第 6 节） | 1024k / 128k | √ | √ | √ | √ |
| | 文本生成（进阶） | `kimi-k2.7-code` | 256k / 32k | √ | √ | √ | √ |
| | 文本生成（进阶） | `deepseek-v4-pro`（正式版） | 1024k / 384k | √ | √ | √ | √ |
| | 文本生成（进阶） | `kimi-k3` | 1024k / 128k | × | √ | √ | √ |
| | 向量化 | `doubao-embedding-vision`（对应 `doubao-embedding-vision-251215`） | 上下文 128k | √ | √ | √ | √ |
| | 图片生成 | `doubao-seedream-5.0-lite` | - | √ | √ | √ | √ |
| | 视频生成 | `doubao-seedance-1.5-pro`（即将下线，2026-09-21） | - | × | √ | √ | √ |
| | 视频生成 | `doubao-seedance-2.0` | - | × | × | √ | √ |
| | 视频生成 | `doubao-seedance-2.0-fast` | - | × | × | √ | √ |
| | 视频生成 | `doubao-seedance-2.0-mini` | - | × | × | √ | √ |
| | 语音 | `doubao-seed-tts-2.0` | - | √ | √ | √ | √ |
| | 语音 | `doubao-seed-asr-2.0` | - | √ | √ | √ | √ |
| Harness | 专业数据集 | MCP | - | √ | √ | √ | √ |
| | 豆包搜索 | Skill / MCP | - | √（每月 500 次免费） | √（同） | √（同） | √（同） |
| | Agent 记忆（OpenViking Context） | Plugin / MCP / CLI / API / SDK | - | √ | √ | √ | √ |
| | AI Native 应用开发底座（火山引擎 Supabase） | MCP / Skill / CLI | - | √ | √ | √ | √ |
| | Agent 进化（Evolve） | Skill / CLI | - | √（前 50 个文件免费） | √（同） | √（同） | √（同） |
| | Computer Use Agent（CUA） | Skill | - | × | × | √ | √ |
| | ArkClaw（赠送权益，下线中） | 体验中心 | - | × | 2026-09-01 起不再赠送 | 同 | 同 |

补充：
- `glm-5.3`、`glm-5.3-flash`、`deepseek-v4-flash`、`deepseek-v4-pro`、`kimi-k3` 支持 1M 上下文窗口；在工具中开启 1M 上下文的方法见 `references/tools-setup.md`。
- 控制台 `ark-code-latest` 路由列表另标注：`doubao-seed-2.0-lite`、`doubao-seed-2.0-mini` 默认 thinking、支持关闭深度思考；`glm-5.3` 与 `kimi-k2.7-code` 标「尝鲜版」；`glm-5.3` 标「抵扣系数较高」。
- ⚠ 文档自相矛盾：快速开始页写「Medium 及以上套餐提供图片生成模型配额，Large 及以上套餐提供视频生成模型配额」，但套餐概览表中 `doubao-seedream-5.0-lite` 四档全 √（含 Small），且 Medium 仍列有 `doubao-seedance-1.5-pro`。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Medium 生图 `doubao-seedream-5.0-lite` 2k 成功（99 AFP）；Medium 视频 `doubao-seedance-2.0-mini` → **404** `{"error":{"code":"UnsupportedModel","message":"The requested model does not support the agent plan feature. Please refer to the documentation at https://www.volcengine.com/docs/82379/2366394 to select a compatible model. ..."}}`（错误码是通用 UnsupportedModel，不是额度 / 档位专用码）；`doubao-seedance-1.5-pro` 未测（即将下线）；Small 生图仍待实测。
- CUA 只出现在其自己的文档页（Large / Max），未出现在套餐概览表中；表中 CUA 一行来自 CUA 页与控制台。

---

## 4. 额度刷新、有效期、升配与退订规则

**刷新周期（未开启超额后付费时，额度耗尽需等下一周期恢复，不会消耗其他资源包或账户余额）**
- 5 小时限额：以**首次请求发生时间**起算，每 5 小时为周期刷新。
- 周限额：每周一 00:00:00 重置。
- 日限额：每日 00:00:00 重置。⚠ 文档自相矛盾：刷新规则处写「仅限视觉模型」，用量说明处却写图片 / 视频 / 语音 / Harness 都「仅受模型日额度、套餐月额度限制」。语音与 Harness 是否受日限额约束未明确。
- 月限额：每**订阅月**第 1 日 00:00:00 重置（订阅月 = 从购买日起算的配额刷新周期，与一次性购买的总时长无关；例：8 月 8 日购买 12 个月，则每月 8 日刷新）。

**开启超额后付费后**：文本 / 向量化模型触达 5 小时、周或月限额任一即自动切换到后付费；语音模型与 Harness 无 5 小时 / 周限额，仅触达月限额时切换。周期刷新后自动切回套餐内抵扣。详见第 7 节。

**有效期**：以自然月计，购买成功当日起算。例：01-31 订购，02-28 23:59 到期（非闰年）。

**购买 / 续费 / 升配 / 退订**
- 单次下单不超过 12 个月，存量 + 新购不超过 24 个月。
- 自动续费（下单勾选，每次续 1 个月）或在开通管理手动续费。
- **只支持升配，不支持降配**。补差价：`升配需补差价金额 = (升配套餐月价 - 原套餐月价) / 30 天 * 套餐剩余时长`（升配月价按应付金额、原月价按实付金额）。
- 升配后额度折算：月限额 `= 升配套餐月额度 * 当月剩余时长占比 + 原套餐月额度 * 当月已用时长占比`；5 小时与周限额直接变为升配套餐对应值；当月已用额度不清零。
- 退订：支持「非七天无理由自助退订」，路径为费用中心 → 退订管理 → 非七天无理由退订页签 → 产品列过滤「火山方舟订阅套餐」。

---

## 5. AFP 抵扣公式与全部抵扣系数

### 5.1 公式（单次请求）
| 类型 | 公式 |
|---|---|
| 文本生成、向量化 | `(输入 token × 输入系数 + 输出 token × 输出系数) / 10,000` |
| 视频生成 | `消耗的 token / 10,000 × 系数` |
| 图片生成 | `成功生成的图片张数 × 系数` |
| TTS `doubao-seed-tts-2.0` | `文本字符数 / 10,000 × 系数` |
| ASR `doubao-seed-asr-2.0` | `语音文件时长(小时) × 系数` |
| 专业数据集 / 豆包搜索 | `调用次数 × 系数` |

**2026-09-01 起**输入系数不再按输入长度分段（原分段系数：≤32k 为 0.67、32k–128k 为 1、>128k 为 2），统一等于模型系数。短输入 AFP 上升、超长输入 AFP 下降；输出系数与其他模态不变。

### 5.2 文本生成与向量化模型

| 类别 | Model Name | 输入系数 | 输出系数 |
|---|---|---|---|
| 极速 | `doubao-seed-2.0-mini` | 0.25 | 0.25 |
| 标准 | `doubao-seed-2.0-lite`、`deepseek-v4-flash` | 0.5 | 0.5 |
| 标准 | `glm-5.3-flash` | 0.5（2026-08-28 至 09-11 限时 0.25） | 0.5（同） |
| 进阶 | `doubao-seed-2.1-turbo`、`doubao-seed-evolving`、`minimax-m3` | 2.5 | 2.5 |
| 进阶 | `kimi-k2.7-code` | 4.5 | 4.5 |
| 进阶 | `glm-5.3`（`glm-latest`） | 4.5 | 4.5 |
| 进阶 | `deepseek-v4-pro` | 5.5 | 5.5 |
| 进阶 | `kimi-k3` | 10 | 10 |
| 向量化 | `doubao-embedding-vision` | 0.5 | 0.5 |
| Auto 模式 | `auto` / `ark-code-latest` 走 Auto | 2026-06-10 18:00 至 2026-11-08 23:59 活动期为 **0.5**，可路由到 `kimi-k3`（夜间 00:00–08:00 路由比例大幅提升）；活动外系数 ⚠ 文档未说明 | 同 |

示例：`doubao-seed-2.1-turbo` 输入 50k、输出 0.5k → `(50000×2.5 + 500×2.5)/10000 = 12.625 AFP`。

### 5.3 视觉模型

| 模型 | 系数（单位：token） |
|---|---|
| `doubao-seedance-1.5-pro`（即将下线） | 无声视频 36；有声视频 72 |
| `doubao-seedance-2.0` | 480p/720p：输入含视频 140 / 不含 230；1080p：155 / 255；4k：80 / 130 |
| `doubao-seedance-2.0-fast` | 输入含视频 110 / 不含 185 |
| `doubao-seedance-2.0-mini` | 输入含视频 70 / 不含 115 |
| `doubao-seedream-5.0-lite` | **99 AFP / 张**成功生成的图片 |

示例：`doubao-seedance-2.0-fast`、输入含视频、消耗 150k token → `150000/10000×110 = 1650 AFP`。视频 token 估算公式见方舟价格页「价格示例」。

### 5.4 语音模型
| 模型 | 系数 | 单位 |
|---|---|---|
| `doubao-seed-tts-2.0` | 1350 | 万字符（示例：2000 字符 → 270 AFP） |
| `doubao-seed-asr-2.0` | 450 | 小时 |

### 5.5 Harness

**专业数据集**（按次）：中国金融数据库 12；企业工商数据库 12；企业风险数据库 12；科研学术数据搜索服务 **24**；中国汽车车型配置库 12；中国汽车品牌销量数据 12；宏观经济数据库 12；其他专业数据搜索服务 12。

**豆包搜索**：5 AFP / 次（主账号维度每月 500 次免费，每月 1 日重置，免费额度在所有开通方式下优先消耗）。

**Agent 记忆（OpenViking Context，每个数据库独立计费）**：前 50 个文件免费；50 < 文件数 ≤ 4 万：5 AFP / 小时；文件数 > 4 万：1.5 AFP / 万个文件 / 小时。注意：开通抵扣后该账号下 OpenViking 所有数据库都从 Agent Plan 抵扣，不支持部分抵扣；关闭抵扣会立即关停 OpenViking 商品并不定期清理数据；账户余额须 ≥ 0。

**AI Native 应用开发底座（火山引擎 Supabase）** —— 数据库引擎：

| 计费项 | 系数 | 单位 |
|---|---|---|
| 数据库算力（1 CU = 1 核 4 GiB） | 250 | CU/小时 |
| Supabase 通用组件算力 | 250 | CU/小时 |
| Edge Function 执行次数 | 70 | 万次 |
| 对象存储容量 | 0.125 | GiB/小时 |
| 数据库存储容量 | 0.625 | GiB/小时 |
| Storage Vector Bucket 存储容量 | 0.575 | GiB/小时 |
| Storage Vector Bucket 数据查询 / 数据更新 | 0.045 / 0.045 | vCU/小时 |

最小规格（数据库算力 0.5 CU + 通用组件 0.25 CU）每小时约 187.5 AFP + 少量存储 AFP。文档单位列原文写作「元/CU/小时」等，实为 AFP 换算单位。

AI Gateway 服务模型（注意：**此处模型不是 Agent Plan 套餐内模型，是服务账号购买的模型**，仅折算为 AFP）：

| 模型 | 计费项 → 系数 |
|---|---|
| `doubao-seedance-2.0` | 480p/720p 含视频 21，不含 34.5；1080p 含视频 23.25，不含 38.25；4k 含视频 12，不含 19.5（单位 token） |
| `doubao-seedance-2.0-fast` | 含视频 16.5，不含 27.75 |
| `doubao-seedance-2.0-mini` | 含视频 10.5，不含 17.25 |
| `doubao-seedream-5.0-lite` | 文生图 165 / 张；图像编辑 165 / 张 |
| `doubao-seedream-5.0-pro` | 多于 1 张的输入图 15 / 张；≤236 万像素输出图 225 / 张；>236 万像素输出图 450 / 张 |
| `doubao-seed-2.1-pro` | 缓存-存储 0.01275；输入 4.5；输出 22.5（元/千 tokens/小时 口径） |
| `doubao-seed-2.1-turbo` | 缓存-存储 0.01275；输入 2.25；输出 11.25 |
| `doubao-seed-2.0-code` / `doubao-seed-2.0-pro` | ≤32k：缓存 0.01275 / 输入 2.4 / 输出 12；32k–128k：0.01275 / 3.6 / 18；128k–256k：0.01275 / 7.2 / 36 |
| `doubao-seed-2.0-lite` | ≤32k：0.01275 / 0.45 / 2.7；32k–128k：0.01275 / 0.675 / 4.05；128k–256k：0.01275 / 1.35 / 8.1 |
| `doubao-seed-2.0-mini` | ≤32k：0.01275 / 0.15 / 1.5；32k–128k：0.01275 / 0.3 / 3；128k–256k：0.01275 / 0.6 / 6 |

**Agent 进化**：250 AFP / 百万 token（云端 Agent 分析会话日志的 token 消耗，无其他服务费），暂不支持超额后付费。

**Computer Use Agent**：按小时抵扣，312.5 AFP/CU/小时，活动期 2 折 62.5 AFP/CU/小时；CUA 内 Agent 消耗的 token 也通过 Agent Plan 结算。套餐积分耗尽时默认关闭 CUA 入口，机器保留 7 天。（仅见于 CUA 页，未列入 AFP 抵扣规则页。）

---

## 6. 配模型的两种方式：ark-code-latest / auto 与 Model Name

控制台「使用配置 → 1 配置模型及Base URL → 语言模型」提供两种方式：

| 方式 | 工具里 `model` 填 | 切换模型 | 适用 |
|---|---|---|---|
| **配置 ark-code-latest** | `ark-code-latest` | 在控制台路由列表单选目标模型，**3–5 分钟生效**，无需改工具配置。默认 Auto 模式（「效果 + 速度」双维度智能算法自动选择） | 想一处切换、跟随控制台 |
| **配置 model-name** | 具体 Model Name（`glm-5.3`、`deepseek-v4-pro`…）；**不能填 `auto`**（实测 404） | 改工具配置文件；Claude Code 可 `claude --model <NAME>` 或对话中 `/model <NAME>` | 想在工具侧精确控制 |

- 控制台路由列表（Model Name）：`auto`（智能调度，**仅供控制台单选，不能作为请求 `model` 直填**）、`doubao-seed-evolving`、`doubao-seed-2.1-turbo`、`doubao-seed-2.0-lite`、`doubao-seed-2.0-mini`、`glm-5.3-flash`、`glm-5.3`、`deepseek-v4-pro`、`deepseek-v4-flash`、`kimi-k3`（仅 Medium 及以上）、`kimi-k2.7-code`、`minimax-m3`。「AFP抵扣系数根据模型层级存在不同」。
- **latest 别名**（推荐，规避模型下线）：`glm-latest` → `glm-5.3`；`minimax-latest` → `minimax-m3`；`kimi-latest` → `kimi-k2.7-code`；`deepseek-latest` → `deepseek-v4-pro`。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`model: "glm-latest"` → 200，响应 `"model":"glm-5.3"`，别名有效（其余三个别名未测）。
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：**`auto` 不能直填**。`model: "auto"` → **404** `{"error":{"code":"UnsupportedModel","message":"The requested model does not support the agent plan feature. Please refer to the documentation at https://www.volcengine.com/docs/82379/2366394 to select a compatible model. ..."}}`。控制台「Model Name: auto」的标注是错的，Coding Plan 文档「Model Name 不支持配置为 Auto，请通过控制台切换」是对的。要用 Auto 只能配 `ark-code-latest` 并在控制台选 Auto。
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`model: "ark-code-latest"`（控制台当前选 Auto）→ 200，响应 `"model":"auto"`，`usage.completion_tokens_details.reasoning_tokens: 0`——所以看响应 `model` 字段判断不出 Auto 实际路由到了哪个模型；`/responses` 接口传 `ark-code-latest` 同样可用，响应 `model: "auto"`。
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：**Model Name 与 Model ID 在 Plan 入口的真实解析**：`doubao-seed-2.0-lite` → 响应 `"model":"doubao-seed-2-0-lite-260215"`（不是模型列表页最新的 `260428`）；`doubao-seed-2.0-mini` → `doubao-seed-2-0-mini-260215`；`kimi-k3` → `kimi-k3`。传带日期的 Model ID `doubao-seed-2-0-lite-260428` → **200 但响应仍是 `260215`**：Plan 入口接受 Model ID 却**静默忽略版本号**，按 Name 路由。传老 Model ID `doubao-seed-1-8-251228`、套餐外 Name `doubao-seed-2.1-pro` → 404 UnsupportedModel（同 `auto` 的文案）。
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Plan 入口参数行为速记（详见 `references/chat.md`）：`messages[].role: "developer"` → **400** `InvalidParameter`「invalid value: `developer`, supported values are: `system`, `assistant`, `user`, `tool`」；`glm-5.3` + `thinking: {"type":"disabled"}` → **400**「thinking.type `disabled` is not supported by this model」，但 `reasoning_effort: "low"` → 200 且 `reasoning_tokens: 0`（事实上关掉了思考），`reasoning_effort: "none"` → **400**「reasoning_effort `none` is not supported by this model」；`doubao-seed-2.0-lite` 默认思考**开**（`reasoning_tokens: 109`），`thinking.disabled` 生效；豆包的 `max_tokens` 不限制思维链（`max_tokens: 64` 仍 `completion_tokens: 110`），而 `kimi-k3` 的 `max_tokens` **把思维链算进去**（`max_tokens: 64` → `finish_reason: "length"`、`content: ""`），改用 `max_completion_tokens` 即正常；`service_tier: "fast"` → **400** `{"error":{"code":"InvalidParameter","message":"The parameter `service_tier` specified in the request are not valid: fast service tier does not support coding plan. ...","param":"service_tier"}}`；强制 `tool_choice: {"type":"function",...}` 生效；`response_format: json_schema` 生效；`stream_options.include_usage` 下 `usage` 仅在末尾 chunk。
- `auto` 模式**不支持超额后付费**（文档原文）。
- **视觉模型、向量化模型不支持通过 Auto 及控制台切换**，只能在配置 / 请求中写具体 Model Name；向量化建议固定同一版本不要混用。
- 旧模型下线后：`glm-5.2` 到期自动路由到 `glm-5.3`；其他下线模型「到期未迁移会影响业务」。

---

## 7. 超额后付费：规则、支持范围、开关位置

**机制**：开启后，周期内额度未用尽优先扣套餐 AFP；用尽后**无需修改 Base URL / API Key / 模型名**，自动切到后付费并产生账单；周期刷新后自动切回。前提：账号已**实名认证**；模型超额还要求已在「开通管理」开通对应模型服务（若在开通管理关闭模型服务，则不能继续使用 Agent Plan 的模型超额后付费）。

**模型支持情况**

| 模型 | 支持超额后付费 | 后付费价格 |
|---|---|---|
| `doubao-seed-2.0-mini`、`doubao-seed-2.0-lite`、`deepseek-v4-flash`、`doubao-seed-2.1-turbo`、`doubao-seed-evolving`、`deepseek-v4-pro` | √ | 方舟「在线推理（常规）」标准价 |
| `doubao-embedding-vision` | √ | 方舟向量模型标准价 |
| `doubao-seed-tts-2.0` | √ | 3 元 / 万字符 |
| `doubao-seed-asr-2.0` | √ | 1 元 / 小时 |
| `glm-5.3-flash`、`minimax-m3`、`glm-5.3`、`kimi-k3`、`auto` 模式 | × | - |
| `doubao-seedream-5.0-lite`、`doubao-seedance-1.5-pro`、`doubao-seedance-2.0`、`-fast`、`-mini` | × | - |

**Harness 超额后付费**

| Harness | 支持 | 超额单价 |
|---|---|---|
| 专业数据集 | √ | 0.024 元/次；科研学术 0.048 元/次 |
| 豆包搜索 | √ | 0.020 元/次 |
| Agent 记忆 | √ | 按 OpenViking Context 计费说明 |
| AI Native 应用开发底座 | √ | 按火山引擎 Supabase 计费项与价格 |
| Agent 进化 | × | - |
| CUA | ⚠ 文档未说明是否支持后付费；积分耗尽默认关闭入口 | - |

**开关位置**
- 模型：Agent Plan 控制台套餐信息区 → **超额后付费管理** → **模型**页签逐个开关。
- Harness：两处等价 —— ①「超额后付费管理」→ **Harness** 页签；② 使用配置 → **配置 Harness** 区域，每张 Harness 卡片上有「开启抵扣」与「超额后付费」两个开关。
- Harness「开启抵扣」：购买套餐时勾选相关协议即自动开启，或在卡片开启。**关闭抵扣**后该 Harness 不再消耗套餐 AFP，其超额后付费也同时关闭（Agent 记忆关闭抵扣会立即关停 OpenViking 商品）。

---

## 8. 用 API 调用多模态模型（向量化 / 图片 / 视频 / 语音）

通用要求：专属 API Key + 专属 Base URL（含 `/plan`）+ 套餐支持的 Model Name，「否则可能会调用失败或产生额外费用」。SDK 方式 Base URL 统一 `https://ark.cn-beijing.volces.com/api/plan/v3`。AI 工具内建议走 Skill（8.5），不支持 Skill 或不在工具内用时走 API。

**`/api/plan/v3` 下各 endpoint 是否存在（**已用真实 API 验证（2026-09-04，Agent Plan Medium）**）**

| endpoint | 结果 |
|---|---|
| `POST /chat/completions` | 200 |
| `POST /responses` | 200；`store: true` → 响应含 `expire_at`；`GET /responses/{id}` 200；`previous_response_id` 续轮正确回忆；`DELETE /responses/{id}` → `{"id":...,"object":"response","deleted":true}` |
| `POST /embeddings`（OpenAI 形态） | 200，见 8.1 |
| `POST /embeddings/multimodal` | 200，见 8.1 |
| `POST /images/generations` | 200，见 8.2 |
| `POST /contents/generations/tasks` | Medium 档 404 UnsupportedModel（套餐不含视频），见 8.3 |
| `GET /models` | **404**（空 body）—— 不能用它列套餐内模型，以 3.2 表 / 控制台为准 |
| `POST /tokenization` | **404** |
| `POST /context/create` | **404** —— 上下文缓存 Context API 在 Plan 入口不存在（但请求头 `X-Prompt-Cache-Id` 不报错，单次无法证明命中） |
| `GET /files` | **404** —— Files API 在 Plan 入口不存在 |

### 8.1 向量化 `doubao-embedding-vision`
**Endpoint**: 两条路都实测可用（文档只给了 OpenClaw / OpenViking 配置，没给 HTTP 示例）：
| Endpoint | 输入 | 响应形态 |
|---|---|---|
| `POST https://ark.cn-beijing.volces.com/api/plan/v3/embeddings`（OpenAI 形态） | `input` **只收字符串**（或字符串数组） | `data[0].embedding` **数组** |
| `POST https://ark.cn-beijing.volces.com/api/plan/v3/embeddings/multimodal` | `input` 为 `[{"type":"text","text":...}, {"type":"image_url",...}]` 数组 | `data.embedding` **对象（不是数组）** |

**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：方舟「兼容 OpenAI SDK」页称「向量化能力模型不支持 OpenAI API」——在 Plan 入口**不成立**，`POST /embeddings` 字符串输入 200，`data[0].embedding` 为浮点数组，默认 **2048** 维，`usage: {"prompt_tokens":20,"total_tokens":20}`。但 OpenAI 形态给 `input` 传多模态对象数组 → **400**「The parameter `input[0]` ... expected a string, but got `map[text:a cat type:text]`」，图片必须走 `/embeddings/multimodal`（200，响应 `data.embedding` 对象、2048 维、`usage.prompt_tokens_details: {"text_tokens":20,"image_tokens":0}`、`model: doubao-embedding-vision-251215`）。
**用途**: 为工具提供语义检索层（记忆检索、知识库问答）。仅支持在配置文件写死 Model Name，不支持 Auto / 控制台切换。
**关键参数**
| 参数 | 值 | 说明 |
|---|---|---|
| `model` | `doubao-embedding-vision` | 对应 `doubao-embedding-vision-251215`（响应 `model` 字段即此 ID） |
| `dimensions` | int，可选 | **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：默认 **2048** 维（两条路一致；文档各处写的 2048 / 1024 / 3072 不一，以实测为准）；传 `dimensions: 1024` **生效**，返回 1024 维。OpenViking 配置里的 `dimension: 1024` 即对应此参数 |

**示例请求**（**已用真实 API 验证（2026-09-04，Agent Plan Medium）**，以下请求体均实际发过）
```bash
# OpenAI 形态：字符串输入，默认 2048 维；加 "dimensions":1024 得 1024 维
curl https://ark.cn-beijing.volces.com/api/plan/v3/embeddings \
  -H "Authorization: Bearer $ARK_AGENT_PLAN_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"doubao-embedding-vision","input":"Agent Plan 是什么","dimensions":1024}'
# 多模态形态：input 为对象数组，响应是 data.embedding（对象）
curl https://ark.cn-beijing.volces.com/api/plan/v3/embeddings/multimodal \
  -H "Authorization: Bearer $ARK_AGENT_PLAN_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"doubao-embedding-vision","input":[{"type":"text","text":"a cat"}]}'
```
```python
import os, requests
from openai import OpenAI
BASE = "https://ark.cn-beijing.volces.com/api/plan/v3"
KEY = os.environ["ARK_AGENT_PLAN_API_KEY"]
# OpenAI SDK（字符串输入）
client = OpenAI(base_url=BASE, api_key=KEY)
resp = client.embeddings.create(model="doubao-embedding-vision", input="Agent Plan 是什么", dimensions=1024)
print(len(resp.data[0].embedding))          # 1024（不传 dimensions 则 2048）
# 多模态（图文）走 /embeddings/multimodal，OpenAI SDK 无对应方法，用 requests
r = requests.post(f"{BASE}/embeddings/multimodal",
                  headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                  json={"model": "doubao-embedding-vision",
                        "input": [{"type": "text", "text": "a cat"}]}).json()
print(len(r["data"]["embedding"]), r["usage"]["prompt_tokens_details"])   # 2048 {'text_tokens': 20, 'image_tokens': 0}
```
**示例响应**（实测关键字段）：`/embeddings` → `{"object":"list","data":[{"object":"embedding","index":0,"embedding":[...]}],"model":"doubao-embedding-vision-251215","usage":{"prompt_tokens":20,"total_tokens":20}}`；`/embeddings/multimodal` → `{"data":{"object":"embedding","embedding":[...]},"model":"doubao-embedding-vision-251215","usage":{"prompt_tokens":20,"total_tokens":20,"prompt_tokens_details":{"text_tokens":20,"image_tokens":0}}}`。
**官方给出的两种配置片段**
```json
// OpenClaw ~/.openclaw/openclaw.json → agents.defaults
"memorySearch": {"provider": "openai", "model": "doubao-embedding-vision",
  "remote": {"baseUrl": "https://ark.cn-beijing.volces.com/api/plan/v3", "apiKey": "<ARK_AGENT_PLAN_API_KEY>"}}
// OpenViking ~/.openviking/ov.conf
"embedding": {"dense": {"api_base": "https://ark.cn-beijing.volces.com/api/plan/v3", "api_key": "<ARK_AGENT_PLAN_API_KEY>",
  "provider": "volcengine", "dimension": 1024, "model": "doubao-embedding-vision"}, "max_concurrent": 10}
```
**注意事项**: 向量化属于「不可用于 API 调用」的模型类别（第 1 节），在工具（OpenClaw / OpenViking）之外直接调用有被判滥用的风险；抵扣系数 0.5 / 0.5；支持超额后付费。

### 8.2 图片生成 `doubao-seedream-5.0-lite`
**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/plan/v3/images/generations`
**用途**: 文生图 / 图生图，同步返回。套餐四档均支持（Small 是否含生图配额见 3.2 补充中的矛盾说明）。
**关键参数**（完整参数表见图片生成 API 文档 / `references/image-video.md`）
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | - | `doubao-seedream-5.0-lite`（Agent Plan 生图仅此一个） |
| `prompt` | string | 是 | - | 提示词 |
| `size` | string | 否 | ⚠ 文档未说明 | **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：必须是 `WIDTHxHEIGHT`、`2k`、`3k` 或 `4k`；传 `"1K"` → **400**「size must be one of 'WIDTHxHEIGHT', '2k', '3k', or '4k'」（5.0-lite 不接受 1K）；传 `"2k"` → 200，响应 `size: "2048x2048"` |
| `output_format` | string | 否 | `jpeg` | `png` / `jpeg` |
| `response_format` | string | 否 | ⚠ 文档未说明 | `url` / `b64_json`。实测 `url` → `data[0].url` 为 TOS 签名链接，`X-Tos-Expires=86400`（**24 小时**后失效，要长期保存请及时下载） |
| `watermark` | bool | 否 | ⚠ 文档未说明 | 示例传 `false`（实测 `false` 生效）；OpenAI SDK 需放 `extra_body` |
| `sequential_image_generation` | string | 否 | - | Java 示例传 `disabled` |
| `stream` | bool | 否 | - | Java 示例传 `false` |

限制：提示词优化模式仅「标准模式」；输入参考图数量 + 最终生成图片数量 ≤ 15 张。
**示例请求**（**已用真实 API 验证（2026-09-04，Agent Plan Medium）**，`size: "2k"` + `watermark: false` + `response_format: "url"` 这组请求体实际发过并成功）
```bash
curl https://ark.cn-beijing.volces.com/api/plan/v3/images/generations \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ARK_AGENT_PLAN_API_KEY" \
  -d '{"model":"doubao-seedream-5.0-lite","prompt":"充满活力的特写编辑肖像，Vogue 封面美学，中画幅，工作室灯光",
       "size":"2k","response_format":"url","watermark":false}'
```
```python
import os
from openai import OpenAI   # 或 from volcenginesdkarkruntime import Ark（同一 endpoint，watermark 可直接作关键字参数）
client = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
                api_key=os.environ["ARK_AGENT_PLAN_API_KEY"])
r = client.images.generate(model="doubao-seedream-5.0-lite", prompt="充满活力的特写编辑肖像……",
                           size="2k", response_format="url",          # size 只接受 WIDTHxHEIGHT / 2k / 3k / 4k
                           extra_body={"watermark": False})
print(r.data[0].url)
```
**示例响应**（关键字段）：`created`、`model`、`data[].url`（或 `data[].b64_json`）、`data[].size`、`data[].output_format`、`usage.generated_images`、`usage.output_tokens`、`usage.total_tokens`。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：2k 一张图返回 `data[0].size: "2048x2048"`、`data[0].url` 为 `X-Tos-Expires=86400` 的签名链接、`usage: {"generated_images":1,"output_tokens":16384,"total_tokens":16384}`，控制台计 99 AFP。
**注意事项**: 每张成功图 99 AFP（与 `usage.output_tokens` 无关，按张计）；不支持超额后付费；不支持 Auto / 控制台切换；`size` 别写 `1K` / `2K` 大写以外的形态也没测，稳妥用小写 `2k` 或显式 `WIDTHxHEIGHT`；URL 24h 过期。

### 8.3 视频生成 `doubao-seedance-2.0` / `-fast` / `-mini`（Large、Max）
**Endpoint**（异步任务）
| 操作 | Endpoint |
|---|---|
| 创建任务 | `POST /api/plan/v3/contents/generations/tasks` |
| 查询任务 | `GET /api/plan/v3/contents/generations/tasks/{id}` |
| 查询任务列表 | `GET /api/plan/v3/contents/generations/tasks?page_num=&page_size=&filter.status=&filter.task_ids=&filter.model=` |
| 取消 / 删除任务 | `DELETE /api/plan/v3/contents/generations/tasks/{id}`（文档标题「取消或删除」；HTTP 方法 ⚠ 本页未写，按标准 API 文档） |

**用途**: 文 / 图 / 视频生视频；创建后轮询查询接口拿 `content.video_url`。
**关键参数**（Agent Plan 页示例中出现的；完整表见视频生成 API 文档 / `references/image-video.md`）
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | - | `doubao-seedance-2.0` / `doubao-seedance-2.0-fast` / `doubao-seedance-2.0-mini`（`1.5-pro` 即将下线） |
| `content` | array | 是 | - | 元素 `{"type":"text","text":...}`、`{"type":"image_url","image_url":{"url":...}}`；文本里可写镜头 / 音效描述 |
| `generate_audio` | bool | 否 | ⚠ 未说明 | 是否生成声音 |
| `ratio` | string | 否 | ⚠ 未说明 | 示例 `adaptive`；能力表支持 21:9 / 16:9 / 4:3 / 1:1 / 3:4 / 9:16 |
| `duration` | int | 否 | ⚠ 未说明 | 秒；2.0 系列 4–15 秒，1.5-pro 4–12 秒 |
| `watermark` | bool | 否 | ⚠ 未说明 | 示例 `false` |

能力：分辨率 `doubao-seedance-2.0` 480p/720p/1080p/4k；`-fast`、`-mini` 480p/720p；`1.5-pro` 480p/720p/1080p；输出 mp4。
**示例请求**
```bash
curl https://ark.cn-beijing.volces.com/api/plan/v3/contents/generations/tasks \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ARK_AGENT_PLAN_API_KEY" \
  -d '{"model":"doubao-seedance-2.0",
       "content":[{"type":"text","text":"女孩抱着狐狸，镜头缓缓拉出，头发被风吹动，可以听到风声"},
                  {"type":"image_url","image_url":{"url":"https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png"}}],
       "generate_audio":true,"ratio":"adaptive","duration":5,"watermark":false}'
# 轮询
curl -H "Authorization: Bearer $ARK_AGENT_PLAN_API_KEY" \
  https://ark.cn-beijing.volces.com/api/plan/v3/contents/generations/tasks/<id>
```
```python
import os, time, requests
BASE = "https://ark.cn-beijing.volces.com/api/plan/v3"
H = {"Authorization": f"Bearer {os.environ['ARK_AGENT_PLAN_API_KEY']}", "Content-Type": "application/json"}
task = requests.post(f"{BASE}/contents/generations/tasks", headers=H, json={
    "model": "doubao-seedance-2.0",
    "content": [{"type": "text", "text": "无人机航拍雪山日出，缓慢右移"}],
    "generate_audio": True, "ratio": "16:9", "duration": 5, "watermark": False}).json()
tid = task["id"]                                   # 形如 cgt-2026xxxx-xxxxxxxx
while True:
    r = requests.get(f"{BASE}/contents/generations/tasks/{tid}", headers=H).json()
    if r["status"] in ("succeeded", "failed", "cancelled"): break
    time.sleep(5)
print(r["status"], r.get("content", {}).get("video_url"))
# 官方 SDK 等价：Ark(base_url=BASE, api_key=...).content_generation.tasks.create(model=..., content=[...], generate_audio=True, ratio="adaptive", duration=5, watermark=False)
```
**示例响应**: 创建返回 `id`（任务 ID，仅保存 7 天）。查询返回 `id`、`model`、`status`（`queued` / `running` / `cancelled` / `succeeded` / `failed`）、`content.video_url`、`content.last_frame_url`（需 `return_last_frame: true`）、`created_at`、`usage.completion_tokens`、`usage.total_tokens`（视频不计输入 token，两者相等）。
**注意事项**: 只有 `queued` 状态可取消；AFP 按 `usage` 的 token × 分辨率 / 是否含视频系数；不支持超额后付费；不支持 Auto / 控制台切换；Small / Medium 不支持 2.0 系列。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Medium 档 `POST /contents/generations/tasks`，`model: doubao-seedance-2.0-mini` → **404** `{"error":{"code":"UnsupportedModel","message":"The requested model does not support the agent plan feature. Please refer to the documentation at https://www.volcengine.com/docs/82379/2366394 to select a compatible model. ..."}}`——报的是通用「模型不支持」，不是额度 / 档位专用错误码，排错时别被误导去查额度。以上请求体本身在 Large / Max 档的行为未实测。

### 8.4 语音：TTS `doubao-seed-tts-2.0` 与 ASR `doubao-seed-asr-2.0`
语音走 **openspeech 域名**而不是 ark 域名，鉴权头也不同：`X-Api-Key: <Agent Plan 专属 Key>`（不是 Bearer），并且**必须**带 `X-Api-Resource-Id`：TTS 为 `seed-tts-2.0`，ASR 为 `volc.seedasr.sauc.duration`。建议每次连接生成 UUID 作 `X-Api-Connect-Id` / `X-Api-Request-Id`，并记录响应头 `X-Tt-Logid` 便于排查。

**TTS Endpoint**
| 接口 | 协议 | 地址 | 场景 |
|---|---|---|---|
| 双流 | WebSocket | `wss://openspeech.bytedance.com/api/v3/plan/tts/bidirection` | 流式发文本、流式收音频，实时对话 |
| 单流 | WebSocket | `wss://openspeech.bytedance.com/api/v3/plan/tts/unidirectional/stream` | 一次发全文，流式收音频片段 |
| HTTP | HTTP POST（chunked） | `https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional` | 一次发文本、一次拿完整音频 |

**关键参数**（请求体 `req_params`；完整参数表见语音 API 文档 6561/1329505、1719100、1598757 及 `references/embeddings-speech.md`）
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `req_params.text` | string | 是 | 要合成的文本（双流接口逐字 / 逐句发） |
| `req_params.speaker` | string | 是 | 音色，示例 `zh_female_gaolengyujie_uranus_bigtts`、`zh_female_vv_uranus_bigtts` |
| `req_params.audio_params.format` | string | 否 | 示例 `mp3` |
| `req_params.audio_params.sample_rate` | int | 否 | 示例 `24000` |
| `req_params.audio_params.enable_timestamp` | bool | 否 | 双流示例 `false` |
| 头 `X-Control-Require-Usage-Tokens-Return: *` | header | 否 | 让连接结束时返回 `usage` |

**示例请求（HTTP 接口；由文档 Python 示例改写，未实测）**
```bash
curl -N https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional \
  -H "X-Api-Key: $ARK_AGENT_PLAN_API_KEY" -H "X-Api-Resource-Id: seed-tts-2.0" \
  -H "Content-Type: application/json" -H "X-Control-Require-Usage-Tokens-Return: *" \
  -d '{"req_params":{"text":"你好，这是通过 HTTP 接口合成的语音。","speaker":"zh_female_vv_uranus_bigtts",
       "audio_params":{"format":"mp3","sample_rate":24000}}}'
```
```python
import os, json, base64, requests
resp = requests.post("https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional",
    headers={"X-Api-Key": os.environ["ARK_AGENT_PLAN_API_KEY"], "X-Api-Resource-Id": "seed-tts-2.0",
             "Content-Type": "application/json", "X-Control-Require-Usage-Tokens-Return": "*"},
    json={"req_params": {"text": "你好，这是通过 HTTP 接口合成的语音。", "speaker": "zh_female_vv_uranus_bigtts",
                         "audio_params": {"format": "mp3", "sample_rate": 24000}}}, stream=True)
audio = bytearray()
for line in resp.iter_lines(decode_unicode=True):
    if not line: continue
    d = json.loads(line)
    if d.get("code", 0) == 0 and d.get("data"): audio.extend(base64.b64decode(d["data"]))
    if d.get("code", 0) == 20000000: break          # 文档示例：20000000 表示结束
    if d.get("code", 0) > 0: print("error", d); break
open("tts.mp3", "wb").write(audio)
```
**示例响应**（HTTP 接口，逐行 JSON）：每行 `{"code": 0, "data": "<base64 音频块>", ...}`；`code == 20000000` 结束；`code > 0` 为错误（文档示例代码推断，未实测）。WebSocket 接口为二进制帧协议，需要文档附件 `protocols.py`（`start_connection` / `start_session` / `task_request` / `finish_session` / `finish_connection`，事件 `ConnectionStarted` / `SessionStarted` / `SessionFinished` / `ConnectionFinished`，音频帧类型 `AudioOnlyServer`），完整示例见来源页。

**ASR Endpoint**（仅 WebSocket，无 curl 方式）
| 接口 | 地址 | 场景 |
|---|---|---|
| 双流 | `wss://openspeech.bytedance.com/api/v3/plan/sauc/bigmodel_async` | 边发音频边返回结果，实时转写 |
| 单流 | `wss://openspeech.bytedance.com/api/v3/plan/sauc/bigmodel_nostream` | 全部发送完或超 15s 后统一返回高精度结果 |

请求头：`X-Api-Key`、`X-Api-Resource-Id: volc.seedasr.sauc.duration`、`X-Api-Request-Id`、`X-Api-Connect-Id`（同一 UUID）、`X-Api-Sequence: -1`。二进制帧：4 字节头（协议版本 0b0001、消息类型 `CLIENT_FULL_REQUEST=0b0001` / `CLIENT_AUDIO_ONLY_REQUEST=0b0010`、flags `POS_SEQUENCE=0b0001` / 末包 `NEG_WITH_SEQUENCE=0b0011` 且 seq 取负、JSON 序列化 + GZIP 压缩）+ 4 字节 seq + 4 字节 payload 长度 + payload。首帧 JSON：
```json
{"user":{"uid":"demo_uid"},
 "audio":{"format":"wav","codec":"raw","rate":16000,"bits":16,"channel":1},
 "request":{"model_name":"bigmodel","enable_itn":true,"enable_punc":true,"enable_ddc":true,"show_utterances":true,"enable_nonstream":false}}
```
服务端响应 `SERVER_FULL_RESPONSE=0b1001` / `SERVER_ERROR_RESPONSE=0b1111`，解析出 `code`、`is_last_package`、`payload_msg`（JSON）。完整 Python（aiohttp，含 ffmpeg 转 16k 单声道 wav、200ms 分片）见来源页 2516286。
**注意事项**: TTS 1350 AFP / 万字符、ASR 450 AFP / 小时；两者都支持超额后付费（3 元 / 万字符、1 元 / 小时）；语音无 5 小时 / 周限额。

### 8.5 在 AI 工具中用 Skill 调多模态（推荐）
- 视频 Skill `byted-ark-seedance-skill`、图片 Skill `byted-ark-seedream-skill`：`npx skills add https://skills.volces.com/skills/volcengine/agentplan -s <skill> --agent <claude-code|openclaw|trae>`；Hermes Agent 下载 ZIP 解压到 `~/.hermes/skills/`。
- 一键：`arkcli helper`（ArkCLI Helper，macOS / Linux / Windows）或旧版 `ark-helper`（仅 macOS / Linux）会自动装好视觉 Skill 与豆包搜索 Skill / MCP。
- 快速开始页：「请先配置文本生成模型，后续图片生成模型、视频生成模型等可在 Claude Code 中使用自然语言/Skill 等方式完成配置」。

---

## 9. Harness 一览

所有 Harness 的共同前提：控制台 **使用配置 → 配置 Harness** 打开该卡片的「开启抵扣」开关；用 Agent Plan 专属 Key 鉴权（Agent 记忆例外）。均无 5 小时 / 周限额。

### 9.1 豆包搜索（Skill / MCP；5 AFP/次，主账号每月 500 次免费）
面向大模型的搜索 API：网页搜索（单次最多 50 条，含标题 / 站点 / URL / 摘要 / 正文）、多模态搜索（返回图片）、权威来源过滤、时间范围筛选、Query 改写。2026-06-22 由「联网搜索（Beta 版）」升级而来；Beta 版旧 Key 仍可鉴权但**不能用 AFP 抵扣**，控制台横幅提示旧版已下线、7 月 1 日起免费额度不再赠送、请停用旧密钥。Claude Code 原生搜索只支持 Claude 系列模型，第三方模型要靠此 Harness 获得搜索能力。
- Skill：`npx skills add https://skills.volces.com/skills/bytedance/agentkit-samples -s byted-web-search --agent <claude-code|opencode|openclaw|hermes-agent>`，启动后对话中提供 Agent Plan Key 完成配置。
- MCP：`uvx --from "git+https://github.com/volcengine/mcp-server#subdirectory=server/mcp_server_askecho_search_infinity" mcp-server-askecho-search-infinity`，环境变量 `ASK_ECHO_SEARCH_INFINITY_API_KEY=<Agent Plan Key>`（OpenClaw 需先 `npm install -g mcporter` 并启用 mcporter skill）。
- 付费用量在豆包搜索控制台数据管理查看；豆包搜索为按量后付费产品，官网无法主动关停，需工单。

### 9.2 专业数据集（MCP；12 AFP/次，科研学术 24 AFP/次）
聚合垂类数据源并按 Query 自动路由：中国金融数据库（单次 ≤3 只标的）、企业工商数据库（≤5 家）、企业风险数据库（≤5 家）、科研学术数据搜索（≤49 篇）、中国汽车车型配置库（≤5 款）、中国汽车品牌销量数据（3 个车系 × 6 个月）、宏观经济数据库（≤10 个指标）、其他专业数据搜索（兜底，≤20 条）。返回 JSON：`code`、`msg`、`trace_id`、`tool`（`dataPro_search`）或 `dataset_type`（`vehicle_config` / `vehicle_sales` / `macro`）、`items[]`、`hint`。
- MCP 地址 `https://datapro.hqd.cn-beijing.volces.com/mcp`，transport streamable-http，请求头 `X-Agent-Plan-Key: <Agent Plan Key>`。Claude Code：`claude mcp add --transport http datapro https://datapro.hqd.cn-beijing.volces.com/mcp --header "X-Agent-Plan-Key: $ARK_AGENT_PLAN_API_KEY"`；Codex `~/.codex/config.toml` `[mcp_servers.datapro]` + `http_headers`；OpenCode `type: remote` + `{env:AGENT_PLAN_KEY}`；OpenClaw `openclaw mcp set datapro '{...}'`。
- 要屏蔽某类数据集，在「高质量数据集管理控制台」开关。

### 9.3 Agent 记忆（OpenViking Context；前 50 文件免费，之后 5 AFP/小时/库）
基于开源 OpenViking 的托管上下文数据库（虚拟文件系统 + 分层上下文 + 目录递归检索），给 Agent 长期记忆、知识库、多 Agent 共享记忆。限制：需实名；仅北京地域；**仅 Agent Plan 个人版 + OpenViking Context 个人版**；子账号需 `VikingdbFullAccess`；账户余额 ≥ 0。
- 鉴权：**用 OpenViking 自己的 API Key**（OpenViking Context 控制台「用户管理」页），不是 Agent Plan Key。服务 URL `https://api.vikingdb.cn-beijing.volces.com/openviking`；MCP `https://api.vikingdb.cn-beijing.volces.com/openviking/mcp`（`Authorization: Bearer <OPENVIKING_API_KEY>`）；HTTP API 另带 `X-OpenViking-Agent: <agent_id>`。
- 接入：Claude Code / Codex 用 install.sh 装 memory plugin 并 `source` wrapper（`type claude` 应为 shell function，否则会静默连本地 127.0.0.1）；OpenClaw `openclaw plugins install clawhub:@openviking/openclaw-plugin && openclaw openviking setup`（需 OpenClaw ≥ 2026.5.2）；Hermes `hermes memory setup`；CLI `npm i -g @openviking/cli && ov config`；SDK `pip install openviking`，`ov.SyncHTTPClient(url, api_key, agent_id)`，`add_resource(path, to="viking://resources/...", wait=True)`，会话式写记忆 `create_session → add_message → commit_session`；HTTP：`POST /api/v1/resources/temp_upload` → `POST /api/v1/resources`；`POST /api/v1/sessions` → `/api/v1/sessions/{id}/messages` → `/api/v1/sessions/{id}/commit`。
- 额度不足且未开后付费导致服务停用：开启后付费立即恢复；或升配后等下一扣费周期（最长 1 小时）；或客服人工恢复。

### 9.4 AI Native 应用开发底座（火山引擎 Supabase；MCP / Skill / CLI）
100% 兼容开源 Supabase 的 Serverless BaaS：PostgreSQL、Auth、Storage、Edge Function、Realtime、MCP Server、前端 Push-to-Deploy（火山引擎 Pages）。首次使用需跨服务授权：主账号授权 `ServiceRoleForAIDAP` 角色；子账号另需 `AIDAPFullAccess`。
- 安装 `npx @byted-supabase/cli@latest install`（同时装好 MCP / Skill / CLI）；登录 `byted-supabase-cli login --is-agent-plan` 或 `configure set --ak <AK> --sk <SK> --is-agent-plan`；切换个人版 / 关闭 `configure agent-plan --profile <p> --is-agent-plan[=false]`。
- Skill：`npx skills add https://skills.volces.com/skills/bytedance/agentkit-samples -s byted-supabase --agent <...>`。MCP：`command: byted-supabase-cli`，`args: ["mcp","serve","--agent-plan"]`。CLI：`byted-supabase-cli projects create <name> --is-agent-plan` / `projects list [--workspace-id <id>]`。
- Workspace 详情页可查 Supabase URL、API Key、数据库连接串；暂停 Workspace 只停算力计费，数据保留。

### 9.5 Agent 进化（Evolve；250 AFP/百万 token，不支持后付费）
读取 Claude Code / OpenClaw / TraeCode 的会话日志（JSONL），提取 evidence，云端结合「基因库」生成 proposal（含原因、证据、risk、confidence、unified diff），确认后写入 CLAUDE.md / CLAUDE.local.md / `~/.claude/CLAUDE.md`（Claude Code）、AGENTS.md / SOUL.md / IDENTITY.md / USER.md / TOOLS.md / BOOTSTRAP.md / HEARTBEAT.md / MEMORY.md / skills/（OpenClaw）、项目级 AGENTS.md（TraeCode）。需 Python ≥ 3.9、公网。
- 安装：`curl -fsSL "https://ark-self-evolve.tos-cn-beijing.volces.com/evolve_skill/latest/install.sh" | bash`，或下载 `evolve-setup-<claude_code|openclaw|trae>.zip` 解压到 `~/.claude/skills/`、`~/.openclaw/workspace/skills/`、`~/.trae/skills/`。
- 鉴权：`export EVOLVE_API_KEY=<Agent Plan 专属 Key>`（文档强调「非方舟统一 API Key」）。首次对 Agent 说 `Set me up for evolve`；CLI：`python3 -m evolve_cli status | import --limit 5 | proposals | proposal <id> | apply <id> [--dry-run]`。
- 无独立回滚：追加式变更包在 `<!-- evolvor:chg_<id> -->…<!-- /evolvor:chg_<id> -->` 块中，删块即撤销；替换式按 diff 手动还原。

### 9.6 Computer Use Agent（CUA；Large / Max；312.5 AFP/CU/小时，活动 2 折 62.5）
用户专属 Windows 云桌面：浏览器自动化（DOM）、视觉自动化（截图 + UIA 操作原生应用）、长程任务（暂停等输入、定时 / 周期任务）、虚拟外设（本地摄像头 / 麦克风）。限制：需实名；同一桌面同时只跑一个任务；临时访问 URL（约 30 分钟有效）属敏感凭证；Agent Plan Key 只在本地终端输入缓存，禁止贴进对话 / 日志 / 仓库。
- 安装：`npm i @volcengine/ark-cli -g` 后 `arkcli helper mcp codex --capability cua`；或 `npx skills add https://skills.volces.com/skills/volcengine/ark -s byted-util-ark-cua --agent codex`。
- 任务 `outcome`：`in_progress`（继续 `watch` / `next.command`）、`needs_input`（转达 `input_request.question` 后 `answer`）、`completed`（取 `result.text` 与产物）、`failed`、`cancelled`。错误码：`AUTH_REQUIRED`（本地无有效 Key）、`DESKTOP_NOT_BOUND`（未分配桌面）、`ACTIVE_RUN_CONFLICT`（桌面已有任务）。（文档原文，未实测）
- 关闭 CUA 即停计费；关闭后机器仅保留 7 天，之后重建为全新机器。

### 9.7 ArkClaw（赠送权益，2026-09-01 起 Medium 及以上不再赠送）
一键云端部署 OpenClaw 的托管服务（专属 ECS、7×24 在线、可用 Agent Plan 额度）。存量用户可用至当前订阅月到期；到期后可在 ArkClaw 控制台单独开通付费版。体验中心创建入口「Agent > ArkClaw」；子账号需 `ArkClawXFullAccess`；套餐到期时 ArkClaw 删除、数据保留 24 小时。

---

## 10. Ark CLI 在 Agent Plan 下的用法

```bash
npm install -g @volcengine/ark-cli@latest && arkcli --version     # Node.js >= 16
arkcli auth login          # 首次：选 Project（可选「账号全部资源」）→ 消费模式 Type 选 agent-plan
arkcli auth status         # 查看登录状态；重选配置先 arkcli config reset
arkcli helper              # TUI：选 profile agent-plan_cn-beijing_personal (Agent Plan) → 默认 model → 要配置的 AI Agent → 逐个 Harness 选「配置 / 跳过」
```
ArkCLI Helper 是 Ark Helper 的升级版（支持 macOS / Linux / Windows），会自动写工具配置（含 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`）并安装所选 Harness 的 Skill / MCP。

| 范围 | 终端命令 | 也可对 Agent 说 |
|---|---|---|
| 交易 | `arkcli plans buy --plan agent-plan --type <small\|medium\|large\|max> [--duration 1-12] [--yes]`（不带 `--yes` 只预览订单与协议）；`arkcli plans renew --plan agent-plan [--duration N] [--yes]`；`arkcli plans get` | 「我想买一个 Agent Plan 个人版 Max，帮我下单」「帮我续费一个月 Agent Plan」 |
| 配置 | `arkcli helper`；`arkcli helper mcp <tool> --capability cua` | 「把 Agent Plan 的 harness 能力都配到我本机的 Claude Code 上」「帮我的 Codex 装上豆包搜索的 MCP」 |
| 用量 | （通过 Agent） | 「我这个月 Agent Plan 还剩多少」「我本周 doubao-seed-2.0-lite 用了多少」 |
| 安全 | `arkcli plans personal rotate-apikey`（二次确认，旧 Key 失效） | 「帮我轮换 Agent Plan 的 API Key」 |
| 生图 | `arkcli +gen "<prompt>" [--model doubao-seedream-5.0] [--size 1024x1024] [--image-count 4] [--input @./cat.png] [--save-to ./out]` | 「帮我使用 AgentPlan 生成一张 4k 大图……」 |
| 生视频 | `arkcli +gen "<prompt>" --modality video --duration 5 --ratio 16:9 [--wait --save-to ./out]`；`arkcli gen get cgt-xxx --save-to ./out`；`arkcli gen list --page-size 10`；`arkcli gen delete cgt-xxx --yes` | 「生成一段 5 秒 16:9 视频……」「刚刚的视频生成好了吗？」 |

⚠ 文档示例 `--model doubao-seedream-5.0` 与套餐支持的 `doubao-seedream-5.0-lite` 不一致，CLI 是否自动映射未说明。

---

## 11. 工具 → 协议 → Base URL 速查

| 工具 | 协议 | Base URL | 备注 |
|---|---|---|---|
| Claude Code | Anthropic | `https://ark.cn-beijing.volces.com/api/plan` | `ANTHROPIC_AUTH_TOKEN` = 专属 Key（实测 Bearer 头可用）；建议 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`（遥测会走 Base URL 占额度）；**必须显式设 `ANTHROPIC_MODEL` 与 `ANTHROPIC_DEFAULT_*_MODEL`**，否则 `claude-*` 名字被静默路由到 `doubao-seed-2.1-turbo`（系数 2.5，实测） |
| Codex CLI、OpenCode、OpenClaw、Hermes Agent、Cline / Roo Code / Kilo Code / Cursor、TraeCode、Pi、WorkBuddy、ZCode、DeepSeek Harness、OpenAI4S | OpenAI（Chat Completions / Responses） | `https://ark.cn-beijing.volces.com/api/plan/v3` | 各工具具体键名不同 |
| OpenClaw memorySearch / OpenViking embedding | OpenAI embeddings | `https://ark.cn-beijing.volces.com/api/plan/v3` | `model: doubao-embedding-vision`（`POST /embeddings` 实测可用，默认 2048 维） |

逐工具的配置文件、1M 上下文开启方法、思考开关等 **详见 `references/tools-setup.md`**。

---

## 12. 常见问题

- **Agent Plan 与 Coding Plan 区别？** 见第 1 节表。Agent Plan 多模态 + Harness + 4 档 + AFP 计费；Key 与 Base URL 不通用。
- **用了 `/api/v3` 会怎样？** 取决于 Key：拿**方舟 API Key** 打 `/api/v3` 不报错但按标准后付费计费、不消耗套餐（控制台原文「接入会产生额外费用」）；拿 **Agent Plan 专属 Key** 打 `/api/v3` 或 `/api/coding/v3` 直接 **401 AuthenticationError**（**已用真实 API 验证（2026-09-04，Agent Plan Medium）**）。所以 Claude Code 里配了 AP Key 却报 401，先查 Base URL 是否漏了 `/plan`。
- **能不能在自己的程序里直接调文本模型？** 官方口径：文本生成与向量化模型「不可用于 API 调用」，可能被判滥用导致停用 / 封禁；图片 / 视频 / 语音模型可以 API 调。
- **额度用完了怎么办？** 等周期刷新；或开超额后付费（需实名 + 开通管理已开通模型；`auto`、`glm-5.3*`、`minimax-m3`、`kimi-k3`、视觉模型不支持）；或升配（不可降配）。
- **切了控制台模型不生效？** `ark-code-latest` 路由切换 3–5 分钟生效；Claude Code 用 `/model` 确认。本地 `.bashrc` / `.zshrc` 里旧的 Anthropic 配置可能冲突，备份清理后重试。注意：控制台选 Auto 时，`ark-code-latest` 的响应 `model` 字段是 `"auto"`（**已用真实 API 验证（2026-09-04，Agent Plan Medium）**），不会告诉你实际路由到了哪个模型。
- **为什么没配错却烧得飞快？** 最常见原因是 Claude Code / 其他 Anthropic 协议工具没显式设模型名，请求里的 `claude-*` 被 Anthropic 入口静默换成 `doubao-seed-2.1-turbo`（系数 2.5）——**已用真实 API 验证（2026-09-04，Agent Plan Medium）**，见 2.1 注意事项 1。其次是 `glm-5.3` / `kimi-k3` 等高系数模型的思维链：`max_tokens` 对豆包不限制思维链，对 `kimi-k3` 则会把回答截空，用 `max_completion_tokens`。
- **`model: auto` 报 404？** `auto` 不能直填（**已用真实 API 验证（2026-09-04，Agent Plan Medium）**），改 `ark-code-latest` 并在控制台选 Auto。
- **视觉 / 向量化模型能用 Auto 吗？** 不能，也不能控制台切换，只能写具体 Model Name。
- **模型下线了配置怎么办？** 用 `ark-code-latest` 或 `*-latest` 别名；否则在下线前改配置文件。`glm-5.2` 下线后自动路由 `glm-5.3`。
- **豆包搜索怎么关？** 按量后付费产品，官网不能主动关停，需提交工单。
- **Agent 记忆关闭抵扣后想保留服务？** 关抵扣后立刻去 OpenViking Context 控制台重新开通商品（改为官网付费）。
- **明细延迟？** 模型调用明细延迟 0.5–1 天；超额部分仅预估，以账单为准。

---

## 13. 近期公告：模型上下线、抵扣系数调整、权益变化

**抵扣系数**
- 2026-09-01 起：文本 / 向量化模型输入系数取消长度分段（原 ≤32k ×0.67、32k–128k ×1、>128k ×2），统一等于模型系数。
- 限时折扣（自动生效）：Auto 模式 0.5（2026-06-10 18:00 至 2026-11-08 23:59，可路由 `kimi-k3`，夜间路由比例大幅提升）；`glm-5.3-flash` 5 折 = 0.25、可用配额 200%（2026-08-28 至 09-11）。已结束：`deepseek-v4-pro` 4 折（至 07-15）、`kimi-k2.7-code` 2.5 折（至 07-15）、`kimi-k2.6`、`glm-5.2`（至 08-08）。

**模型上线**：08-28 `glm-5.3-flash`；08-24 `deepseek-v4-pro` 正式版；08-14 `glm-5.3`；08-03 / 08-07 `deepseek-v4-flash` 正式版全量；07-23 `doubao-seed-2.1-turbo`；07-17 `kimi-k3`；07-15 `doubao-seed-evolving`；06-25 `doubao-seedance-2.0-mini`（仅 Large / Max）；06-17 `glm-5.2`、`kimi-k2.7-code`；06-11 `doubao-seed-tts-2.0`、`doubao-seed-asr-2.0`、专业数据集；06-08 `minimax-m3`；05-15 `deepseek-v4-flash` / `-pro`；05-07 Agent Plan 上线。

**模型下线**（「新用户」= 购买套餐但未用过该模型者，自启动日起即不可用，含超额后付费）

| 模型 | 停止服务 | 迁移目标 |
|---|---|---|
| `doubao-seedance-1.5-pro` | 2026-09-21 14:00 | `doubao-seedance-2.0-mini` |
| `glm-5.2` | 2026-08-31 14:00（到期自动路由） | `glm-5.3` |
| `kimi-k2.6`、`minimax-m2.7` | 2026-08-18 | `kimi-k2.7-code` / `kimi-k3`、`minimax-m3` |
| `doubao-seed-2.0-code`、`doubao-seed-2.0-pro` | 2026-08-08 | `doubao-seed-2.1-turbo` |
| `glm-5.1`、`deepseek-v3.2` | 2026-06-30 | `glm-5.2`（现应用 `glm-5.3`）、`deepseek-v4-pro` |
| `minimax-m2.5`、`kimi-k2.5`、`glm-4.7` | 2026-06-08 | - |

**套餐权益**
- 2026-09-01 起 Medium 及以上不再赠送 ArkClaw（存量用至当前订阅月末）。
- 2026-06-08 起 Medium 不再支持 `seedance 2.0` / `2.0-fast`；受影响用户 06-08 至 06-15 可免费升 Large（已过期）。
- 2026-07-01 Small / Medium 开放 AI Native 应用开发底座；2026-06-21 联网搜索 Beta 升级为豆包搜索、新增 Agent 记忆与底座。

---

## 14. 企业版与个人版的差异

| 项 | 个人版 | 企业版（Team Small / Medium / Large / Max） |
|---|---|---|
| 价格 | 40 / 200 / 500 / 1000 元/月 | 120 / 600 / 1500 / 3000 元/月/席位 |
| 月额度 | 20k / 100k / 250k / 500k AFP | 40k / 200k / 500k / 1,000k AFP |
| 周 / 5 小时 / 日额度 | 7k·2k·10k / 35k·10k·50k / 87.5k·25k·125k / 175k·50k·250k | 14k·4k·20k / 70k·20k·100k / 175k·50k·250k / 350k·100k·500k |
| 购买资格 | 个人账号 | 完成企业认证 + 管理员权限（`ArkFullAccess` / `AdministratorAccess`），IAM 用户登录 |
| 席位 | 无 | **5 席起售**，之后可增购（主账号总席位 ≥ 5）；席位从属 Project，不同项目不互通；一个子账号在一个 Project 下最多绑一个席位；一个席位一个订阅月只能换绑一次 |
| API Key | 一个账号一把，控制台「配置专属API Key」 | **每个席位一把**，分配给用户后生成；席位过期 Key 失效；解绑重绑后 Key 更新；换席位套餐要用新 Key 重新配工具 |
| Base URL | `/api/plan`、`/api/plan/v3` | 相同 |
| 模型 | 3.2 表 | 同表（企业版 1M 上下文说明未列 `kimi-k3`，表中仍有 `kimi-k3` Medium 及以上 ⚠ 文档自相矛盾） |
| Harness | 六项 + ArkClaw | 专业数据集、豆包搜索、AI Native 底座、Agent 进化；**无 Agent 记忆**（OpenViking 页明确仅支持个人版）；企业 FAQ 只提豆包搜索与底座 ⚠ 文档自相矛盾 |
| 升降配 | 仅升配 | **不支持升配或降配**（换更高套餐 = 解绑后绑到其他套餐的席位） |
| 退订 | 支持非七天无理由自助退订 | **不支持退订** |
| 控制台 | `.../openManagement?...advancedActiveKey=agentPlan`（或 `/subscription/agent-plan`） | `.../subscription/agent-plan-enterprise` 或 `advancedActiveKey=agentEnterprise`；页签：席位管理、用量统计；席位用户在「我的 → 使用配置」切 `ark-code-latest` 模型、看专属 Key 与 Base URL |
| 权限 | - | 建议两用户组：`AgentPlanTeam_Admin`（`ArkFullAccess`，可选 `AIDAPFullAccess`）、`AgentPlanTeam_User`（`ArkPlanUserAccess`，可选 `AIDAPFullAccess`）；分配席位后**还必须**加入用户组，否则看不到 / 用不了；可加自定义 Deny `aidap:DeleteWorkspace` 防误删 |
| 配额 | - | 项目配置 → 配额管理 → AgentPlan 可按项目分席位额度（未配则共享）；调主账号配额找销售 |
| 数据 | - | 「不记录用户请求与模型返回数据」 |
| 状态验证 | Claude Code `/model` | 企业版快速开始写 `/status` |

在企业账号下购买 / 管理 Agent Plan **个人版**，需加入 Agent Plan 管理员用户组。

---

## 15. 套餐提货券

集中采购 / 统一分发用。需企业认证方可购买；单次最多 2000 张；有效期 1 年内需完成绑定与提货；只能用于**新购**（不能续费 / 升降配）；绑定后即时生效、不可解绑转让；不支持退订；不记名电子凭证。个人版购买页 `console.volcengine.com/common-buy/ark_subscription_Voucher`，企业版 `.../ark_subscription_team_Voucher`。企业版首次提货单张额度须 ≥ 5 个·月（多张不可合并）。流程：购买生成兑换码 → 提货券管理「兑换码列表」兑换（或把 code 给他人在「提货券列表」兑换）→ 立即提货选时长。

---

## 来源页面

| 标题 | URL | 文档更新时间 |
|---|---|---|
| 套餐概览（个人版） | https://www.volcengine.com/docs/82379/2366394 | 2026-08-31 |
| 套餐内 AFP 抵扣规则 | https://www.volcengine.com/docs/82379/2516283 | 2026-09-01 |
| 超额后付费规则 | https://www.volcengine.com/docs/82379/2516284 | 2026-08-31 |
| 超额后付费管理 | https://www.volcengine.com/docs/82379/2516285 | 2026-09-01 |
| 快速开始（个人版） | https://www.volcengine.com/docs/82379/2373738 | 2026-08-28 |
| 常见问题（个人版） | https://www.volcengine.com/docs/82379/2377895 | 2026-08-24 |
| Agent/Coding Plan 套餐提货券使用指南 | https://www.volcengine.com/docs/82379/2545153 | 2026-09-01 |
| Ark CLI：Agent Plan 个人版使用指南 | https://www.volcengine.com/docs/82379/2656113 | 2026-08-21 |
| 接入向量化模型 | https://www.volcengine.com/docs/82379/2375464 | 2026-07-29 |
| 接入视觉模型 | https://www.volcengine.com/docs/82379/2375486 | 2026-08-24 |
| 接入语音模型 | https://www.volcengine.com/docs/82379/2516286 | 2026-07-29 |
| 豆包搜索 | https://www.volcengine.com/docs/82379/2301412 | 2026-08-03 |
| 专业数据集 | https://www.volcengine.com/docs/82379/2479086 | 2026-08-24 |
| Agent 记忆 | https://www.volcengine.com/docs/82379/2545595 | 2026-08-24 |
| AI Native 应用开发底座 | https://www.volcengine.com/docs/82379/2545596 | 2026-08-24 |
| Agent 进化 | https://www.volcengine.com/docs/82379/2545597 | 2026-08-24 |
| ArkClaw | https://www.volcengine.com/docs/82379/2407058 | 2026-08-28 |
| Computer Use Agent | https://www.volcengine.com/docs/82379/2670601 | 2026-09-02 |
| 功能发布公告 | https://www.volcengine.com/docs/82379/2477433 | 2026-08-28 |
| 模型上线公告 | https://www.volcengine.com/docs/82379/2578669 | 2026-08-28 |
| 模型下线公告 | https://www.volcengine.com/docs/82379/2578673 | 2026-08-24 |
| 模型抵扣系数调整公告 | https://www.volcengine.com/docs/82379/2658332 | 2026-08-24 |
| Agent/Coding Plan 指定模型抵扣系数限时折扣活动 | https://www.volcengine.com/docs/82379/2533565 | 2026-08-28 |
| Agent Plan 套餐赠送 ArkClaw 权益调整公告 | https://www.volcengine.com/docs/82379/2665218 | 2026-08-27 |
| Agent Plan Medium 套餐 seedance 2.0 系列模型调整公告 | https://www.volcengine.com/docs/82379/2525064 | 2026-06-07 |
| 套餐概览（企业版） | https://www.volcengine.com/docs/82379/2374452 | 2026-08-31 |
| 快速开始（企业版） | https://www.volcengine.com/docs/82379/2374453 | 2026-08-26 |
| 控制台操作指南（企业版） | https://www.volcengine.com/docs/82379/2374454 | 2026-07-22 |
| 用户组与权限管理（企业版） | https://www.volcengine.com/docs/82379/2602657 | 2026-07-23 |
| 常见问题（企业版） | https://www.volcengine.com/docs/82379/2381504 | 2026-07-02 |
| 视频生成 API：创建 / 查询任务（仅取响应字段名） | https://www.volcengine.com/docs/82379/1520757 、 /1521309 | 2026-08-21 / 2026-08-19 |
| 图片生成 API（仅取响应字段名） | https://www.volcengine.com/docs/82379/1541523 | 2026-08-28 |
| 控制台实读笔记（Agent Plan 使用配置页，ego-browser 2026-09-03） | https://console.volcengine.com/ark/region:cn-beijing/subscription/agent-plan | 2026-09-03 |
| 真实 API 验证记录（Agent Plan Medium 专属 Key，约 45 条请求 / 响应） | `volcengine-ark-workspace/verification-findings.md`、`verification-log.jsonl` | 2026-09-04 |
