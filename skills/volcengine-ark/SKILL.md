---
name: volcengine-ark
description: 接入火山引擎·火山方舟（Volcengine Ark，ark.cn-beijing.volces.com，豆包 Doubao / Seed / Seedream / Seedance 及 DeepSeek、GLM、Kimi、MiniMax 等第三方模型）的完整 API 使用手册，并且重点区分三套互不通用的入口：标准后付费 API（/api/v3 + 方舟 API Key + 带日期的 Model ID）、Coding Plan 编程套餐（/api/coding 或 /api/coding/v3 + 方舟 API Key + 小写 Model Name）、Agent Plan 订阅套餐（/api/plan 或 /api/plan/v3 + Agent Plan 专属 API Key + AFP 抵扣）。覆盖 Chat Completions、Responses API、深度思考、Function Calling、结构化输出、上下文缓存、多模态理解（图片/视频/文档/音频/文件）、图片生成、视频生成、向量化、语音 TTS/ASR、批量推理、应用 Bot、内置工具（联网搜索/MCP/图像处理）、管控面 API（AK/SK 签名，含 Agent/Coding Plan 套餐与用量查询）、在 Claude Code / Codex / OpenCode / OpenClaw / Cline / Cursor / TRAE 等工具里配置套餐、Ark CLI、错误码与限流。当用户提到"火山方舟""火山引擎大模型""方舟""Ark""volces""豆包 API""Doubao""Seedream""Seedance""Agent Plan""Coding Plan""AFP""ark-code-latest""arkcli""volcenginesdkarkruntime"，或者要用这些模型写代码、配置编程工具套餐、排查"用了套餐还被扣费""Key 不对""模型不存在"时，务必加载本技能，不要凭记忆编造 Base URL、Key 类型或模型名格式。
---

# 火山方舟（Volcengine Ark）接入指南

火山方舟是火山引擎的大模型服务平台：提供豆包（Doubao Seed）系列及 DeepSeek / GLM / Kimi / MiniMax 等第三方文本模型、Seedream 图片生成、Seedance 视频生成、多模态向量化、语音模型，并以 OpenAI 兼容协议（Chat Completions + Responses API）和 Anthropic 兼容协议对外提供服务。本技能把官方文档站（`www.volcengine.com/docs/82379`，共 260 余页）和已登录控制台的真实页面浓缩成可直接照抄的调用规范，目标是让你写出**第一次就跑通、并且钱扣在正确的地方**的代码。

## ⚠ 验证状态

- 文档抓取日期 2026-09-03；控制台（Agent Plan / Coding Plan 订阅页）由已登录浏览器实读。
- **已用真实 API 验证（2026-09-04）的范围：Agent Plan 入口** `/api/plan/v3`（Chat Completions、Responses、embeddings 两条路、图片生成、视频拒绝、各 endpoint 存在性）与 `/api/plan/v1/messages`（Anthropic 协议），测试账号为 Agent Plan 个人版 **Medium** 套餐，约 45 次调用，消耗不到 120 AFP。结论汇总在文末"验证记录"，各 reference 里对应位置标 **已用真实 API 验证（2026-09-04，Agent Plan Medium）** 并附原始报错。
- **未验证**：标准后付费入口 `/api/v3`（无标准 Key）、Coding Plan 套餐内行为（未订阅）、语音 / 同传、管控面 Action、Harness。这些部分是文档转录，文档里抄来的报错文案一律标"文档原文，未实测"。Plan 入口的共性结论（Model Name 解析、`developer` role、思考开关）预期在 Coding Plan 入口一致，但仍按未测处理。

## 用之前先确认的四件事

### 1. 先分清用户手里是哪一套（这是本平台最容易全盘写错的地方）

同一个域名 `ark.cn-beijing.volces.com` 下有三套**互不通用**的入口。Base URL、Key、`model` 字段格式三者必须配套，配错的结果不是报错，而是**从后付费余额里扣钱**或**套餐额度不生效**：

| | 标准 API（后付费） | Coding Plan（编程套餐） | Agent Plan（订阅套餐） |
|---|---|---|---|
| OpenAI 协议 Base URL | `https://ark.cn-beijing.volces.com/api/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` | `https://ark.cn-beijing.volces.com/api/plan/v3`（已支持 Responses API） |
| Anthropic 协议 Base URL（Claude Code 等） | `https://ark.cn-beijing.volces.com/api/v3/compatible`（仅见于"Agent 场景模型调用的正确姿势"一页的 curl，同页另一处写 `/api/compatible`，⚠ 文档自相矛盾且未实测） | `https://ark.cn-beijing.volces.com/api/coding` | `https://ark.cn-beijing.volces.com/api/plan`（已实测：`/api/plan/v1/messages`） |
| 用哪把 Key | 方舟 API Key（控制台 → API Key 管理） | **同一把方舟 API Key** | **Agent Plan 专属 API Key**（Agent Plan 控制台第 3 步"配置专属API Key"，只有一把，可轮换；与方舟 API Key 不通用） |
| `model` 填什么 | 带日期版本的 **Model ID**：`doubao-seed-2-1-pro-260628`、`doubao-seed-2-0-lite-260428`、`deepseek-v4-pro-ga-260813`（版本号用连字符）或推理接入点 `ep-2024…` | 小写 **Model Name**：`doubao-seed-evolving` / `doubao-seed-2.1-turbo` / `doubao-seed-2.0-lite` / `glm-5.3` / `glm-5.3-flash` / `deepseek-v4-flash` / `deepseek-v4-pro` / `kimi-k2.7-code` / `minimax-m3`（版本号用点），或路由名 `ark-code-latest`（控制台切模型） | 同 Coding Plan 的 Model Name，另加 `doubao-seed-2.0-mini`、`kimi-k3`（Small 档不可用）、`auto`；多模态：`doubao-embedding-vision`、`doubao-seedream-5.0-lite`、`doubao-seedance-2.0*`（仅 Large/Max）、`doubao-seed-tts-2.0`、`doubao-seed-asr-2.0` |
| 计费 | 按 token / 张 / 秒后付费，需先在"开通管理"开通模型 | 套餐（Lite 9.9 元 / Pro 49.9 元每月），按次数估算 5 小时 / 周 / 月额度 | 套餐（Small 40 / Medium 200 / Large 500 / Max 1000 元每月），按 **AFP** 抵扣，可开"超额后付费" |
| 官方允许的用途 | 任何程序调用 | **仅限 AI 编程工具内**，"不能用于 API 调用"，非编程工具使用可能被判滥用停用 | 文本 / 向量化模型同样"不可用于 API 调用"；图片 / 视频 / 语音模型由 Agent 通过 API 调用 |
| 控制台 | `console.volcengine.com/ark/region:ark+cn-beijing/apiKey` | `console.volcengine.com/ark/region:cn-beijing/subscription/coding-plan` | `console.volcengine.com/ark/region:cn-beijing/subscription/agent-plan` |

控制台与文档反复强调的一句话："**请勿使用 `https://ark.cn-beijing.volces.com/api/v3`**，接入会产生额外费用"——指的是套餐用户。反过来，标准 API 用户也不要用 `/api/plan`、`/api/coding`。用户提到"套餐""Plan""AFP""额度""ark-code-latest"时，先读 [`references/agent-plan.md`](references/agent-plan.md) 或 [`references/coding-plan.md`](references/coding-plan.md)；两者差异见 agent-plan.md 开头的对比表。

### 2. 鉴权格式

- 三套 OpenAI 协议入口统一 **`Authorization: Bearer <KEY>`**，`Content-Type: application/json`。
- Anthropic 协议入口（`/api/plan`、`/api/coding`）在 Claude Code 里用 `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`；原生 HTTP 头写法以"验证记录"为准。
- 管控面 API（`https://ark.cn-beijing.volcengineapi.com/?Action=…&Version=2024-01-01`）**不是** API Key，而是火山引擎 Access Key / Secret Key 的 HMAC-SHA256 签名（Service `ark`，Region `cn-beijing`），用官方 SDK 签名，不要手写。见 [`references/management-api.md`](references/management-api.md)。
- Key 只走环境变量：`ARK_API_KEY`（标准 / Coding Plan）、`ARK_AGENT_PLAN_API_KEY`（Agent Plan）。

### 3. `model` 字段是本平台第二大坑

标准入口的 Model ID 带日期后缀且用连字符（`doubao-seed-2-0-lite-260428`），Plan 入口的 Model Name 不带日期且用点（`doubao-seed-2.0-lite`）；两者互换是否被接受见"验证记录"。写代码前对照 [`references/models.md`](references/models.md) 查当前可用的 ID / Name、上下文窗口、是否默认开思考、能否关思考（`glm-5.3` 默认开且不可关）、是否支持视觉输入。用 Access Key 鉴权时 `model` 必须填 `ep-` 接入点 ID。

### 4. 标准 API 要先"开通模型"

按量付费模型需在控制台"开通管理"逐个开通（或开自动开通），否则调用报模型未开通类错误；Coding / Agent Plan 购买即开通，无需创建接入点。

## 30 秒跑通第一个请求

标准 API（后付费）：

```bash
curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seed-2-0-lite-260428",
    "messages": [{"role": "user", "content": "你好，用一句话介绍你自己。"}],
    "thinking": {"type": "disabled"}
  }'
```

```python
import os
from openai import OpenAI

client = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/v3", api_key=os.environ["ARK_API_KEY"])
resp = client.chat.completions.create(
    model="doubao-seed-2-0-lite-260428",
    messages=[{"role": "user", "content": "你好，用一句话介绍你自己。"}],
    extra_body={"thinking": {"type": "disabled"}},   # 方舟私有字段走 extra_body
)
print(resp.choices[0].message.content)
```

Agent Plan（订阅套餐，专属 Key）只换两处：`base_url="https://ark.cn-beijing.volces.com/api/plan/v3"`、`api_key=os.environ["ARK_AGENT_PLAN_API_KEY"]`、`model="doubao-seed-2.0-lite"`。Coding Plan 换成 `/api/coding/v3` + `ARK_API_KEY`。

## 能力域导航

| 我想做什么 | 参考文件 | 涉及的核心 endpoint |
| :--- | :--- | :--- |
| 弄清 Agent Plan：套餐档位、AFP 抵扣系数、5小时/周/月额度、超额后付费、Harness（豆包搜索 / 专业数据集 / Agent 记忆 / Supabase 底座）、在 Plan 内调向量化 / 图片 / 视频 / 语音模型、企业版席位 | [`references/agent-plan.md`](references/agent-plan.md) | `https://ark.cn-beijing.volces.com/api/plan[/v3]` |
| 弄清 Coding Plan：Lite/Pro、支持的 Model Name、`ark-code-latest`、额度估算、Embedding 专属权益、常见报错 | [`references/coding-plan.md`](references/coding-plan.md) | `https://ark.cn-beijing.volces.com/api/coding[/v3]` |
| 把套餐配进 Claude Code / Codex / OpenCode / OpenClaw / Cline / Cursor / Roo / Kilo / TRAE / Hermes / Pi / ZCode / WorkBuddy / OpenViking，或用 `arkcli helper` 自动配置 | [`references/tools-setup.md`](references/tools-setup.md) | 各工具配置文件 |
| 该用哪个模型、Model ID 与 Model Name 对照、上下文/输出上限、思考默认值、后付费价格、Plan 内可用模型与 AFP 系数 | [`references/models.md`](references/models.md) | — |
| 文本对话、流式、深度思考 / `reasoning_effort`、Function Calling、结构化输出、续写、上下文缓存（会话缓存 vs 前缀缓存）、分词 | [`references/chat.md`](references/chat.md) | `POST /chat/completions`、`POST /context/create`、`POST /context/chat/completions`、`POST /tokenization` |
| 给模型喂图片 / 视频 / PDF 文档 / 音频 / 上传文件，GUI Agent 坐标输出，视觉定位 | [`references/multimodal-input.md`](references/multimodal-input.md) | `messages[].content[]` 各 part、`POST /files`、`GET /files/{id}` |
| 用 Responses API（多轮 `previous_response_id`、`input` items、流式事件、上下文编辑、从 Chat 迁移） | [`references/responses.md`](references/responses.md) | `POST /responses`、`GET /responses/{id}`、`GET /responses/{id}/input_items`、`DELETE /responses/{id}` |
| 平台内置工具：联网搜索、图像处理、知识库检索、Remote MCP、豆包助手；接入 Dify / LangChain 等三方框架 | [`references/tools.md`](references/tools.md) | Responses API `tools[]`（`web_search` / `image_process` / `knowledge_search` / `mcp`） |
| 文生图 / 图生图 / 组图 / 交互编辑（Seedream），文生视频 / 图生视频 / 参考视频（Seedance）与任务轮询 | [`references/image-video.md`](references/image-video.md) | `POST /images/generations`、`POST /contents/generations/tasks`、`GET /contents/generations/tasks/{id}` |
| 向量化（多模态 embedding）、语音合成 TTS、语音识别 ASR、同声传译 | [`references/embeddings-speech.md`](references/embeddings-speech.md) | `POST /embeddings/multimodal`、语音 / 同传 WebSocket |
| 批量推理（在线批量 Chat vs 离线 Job）、调用应用实验室的 Bot | [`references/batch-and-bot.md`](references/batch-and-bot.md) | `POST /batch/chat/completions`、`CreateBatchInferenceJob`、`POST /bots/chat/completions` |
| 管控面：程序化查询 / 创建 Agent & Coding Plan 套餐、AFP 额度与用量、轮换 Plan Key、企业版席位、查询模型列表与限流、临时 API Key | [`references/management-api.md`](references/management-api.md) | `https://ark.cn-beijing.volcengineapi.com/?Action=…&Version=2024-01-01` |
| 官方 SDK（Python `volcenginesdkarkruntime` / Go / Java）、OpenAI SDK / LangChain 兼容、Ark CLI、方舟文档 MCP | [`references/sdk-and-compat.md`](references/sdk-and-compat.md) | — |
| 报错排查、错误码全表、限流、Plan 用户最常见的报错、重试策略、计费口径 | [`references/errors-and-limits.md`](references/errors-and-limits.md) | — |

本 skill **不覆盖**：Managed Agents（托管智能体平台及其 API）、知识库产品、模型精调 / 评测、推理接入点 Endpoint 管理、3D 生成、私域人像 / 版权库。这些在 `www.volcengine.com/docs/82379` 对应分区，management-api.md 末尾有索引。

## 跨领域的通用规则（写代码前必读）

- **三套入口不能混用，Key 也不能混用**：Agent Plan 专属 Key ≠ 方舟 API Key；Coding Plan 用的是方舟 API Key。已用真实 API 验证（2026-09-04）：Agent Plan Key 打 `/api/v3` 或 `/api/coding/v3` 一律 `401 AuthenticationError`，不是"套餐不支持"。同一项目既要套餐额度跑对话、又要调套餐外能力时，要同时管理两个 Base URL、两把 Key，分开命名（`ARK_AGENT_PLAN_API_KEY` / `ARK_API_KEY`）。
- **`model` 格式随入口变，而且 Plan 入口会静默改写**：`/api/v3` 用带日期的 Model ID（或 `ep-`），`/api/plan/v3` `/api/coding/v3` 用小写 Model Name。已用真实 API 验证（2026-09-04，Agent Plan）：传 `doubao-seed-2-0-lite-260428` 这种带日期 ID **不报错，但实际服务的是 `doubao-seed-2-0-lite-260215`**——版本号被无视；`doubao-seed-2.0-lite` 也解析到 260215。要确定版本，看响应里的 `model` 字段。直填 `model: "auto"` 实测 `404 UnsupportedModel`（控制台"Model Name: auto"是错的，Coding Plan 文档"不支持填 Auto"是对的）；想用 Auto 路由填 `ark-code-latest` 并在控制台选 Auto，响应 `model` 会显示 `auto`。套餐外模型、老 Model ID、Medium 档调视频模型返回的都是同一个 `404 UnsupportedModel`。
- **Anthropic 协议入口会把 `claude-*` 模型名静默换成豆包**：已用真实 API 验证（2026-09-04）：`/api/plan/v1/messages` 传 `model: "claude-sonnet-4-5"` 返回 200，响应 `model` 是 `doubao-seed-2-1-turbo-260628`（抵扣系数 2.5）。这意味着 Claude Code 只设了 `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` 而**忘设 `ANTHROPIC_MODEL` 与 `ANTHROPIC_DEFAULT_*_MODEL`** 时不会报错，只会悄悄按 2.1-turbo 扣 AFP。配置工具时四个模型变量都要显式填。
- **`messages[].role` 只接受 `system` / `user` / `assistant` / `tool`**。已用真实 API 验证（2026-09-04）：`developer` role 返回 `400 InvalidParameter`："invalid value: `developer`, supported values are: `system`, `assistant`, `user`, `tool`"。用 OpenAI SDK 新版或 OpenClaw 等默认发 `developer` 的客户端时要改成 `system`（OpenClaw 在 model 级加 `compat.supportsDeveloperRole: false`）。
- **深度思考因模型而异，关思考的写法也因模型而异**：`thinking.type` 取 `enabled` / `disabled` / `auto`；另有 `reasoning_effort`（`none` / `minimal` / `low` / `medium` / `high`）。已用真实 API 验证（2026-09-04，Agent Plan）：`doubao-seed-2.0-lite/mini` 默认开思考、`thinking.disabled` 生效；`glm-5.3` 传 `thinking.disabled` → `400 thinking.type disabled is not supported by this model`，传 `reasoning_effort: "none"` → 同样 400，但 `reasoning_effort: "low"` 被接受且 `reasoning_tokens: 0`，是 glm-5.3 事实上的"关思考"写法。思维链在 `choices[].message.reasoning_content`（流式 `delta.reasoning_content`），不在 `content` 里。用 OpenAI SDK 时这些私有字段走 `extra_body`。
- **`max_tokens` 对思维链的口径各模型不一致，开思考一律用 `max_completion_tokens`**。已用真实 API 验证（2026-09-04）：`doubao-seed-2.0-lite` 设 `max_tokens: 64` 仍返回 `completion_tokens: 110`（思维链 109 不受限，回答正常）；`kimi-k3` 设 `max_tokens: 64` 则 `finish_reason: "length"`、`content: ""`——思维链吃光额度、回答为空；改 `max_completion_tokens: 400`（不能与 `max_tokens` 同传）后正常。
- **Plan 入口只有一部分 endpoint**。已用真实 API 验证（2026-09-04，`/api/plan/v3`）：`/chat/completions`、`/responses`（含 `store`、`previous_response_id`、GET / DELETE）、`/embeddings`、`/embeddings/multimodal`、`/images/generations`、`/contents/generations/tasks` 存在；`/models`、`/tokenization`、`/context/create`（上下文缓存 Context API）、`/files`（Files API）全部 **404**。`service_tier: "fast"` 在 Plan 入口 `400 fast service tier does not support coding plan`。需要这些能力只能走标准后付费入口。
- **向量化两条路都能走，但形态不同**。已用真实 API 验证（2026-09-04，Agent Plan）：OpenAI 形态 `POST /embeddings`（`input` 只能是字符串或字符串列表，传多模态数组 → `400 expected a string`）返回 `data[0].embedding`，默认 **2048** 维，`dimensions: 1024` 生效；`POST /embeddings/multimodal` 返回的是 **`data.embedding` 单个对象**（不是数组），同样 2048 维。文档"向量化不支持 OpenAI API"在 Plan 入口不成立。
- **Agent Plan 的额度分三档刷新**：5 小时（按首次请求起算）/ 周（周一 0 点）/ 月（订阅月首日），图片 / 视频 / 语音 / Harness 不受 5 小时与周限额约束，只受日（月额度一半）与月限额。额度耗尽且未开"超额后付费"时请求会失败，而不是从余额扣钱；开了则**无需改任何配置**自动切到后付费（`auto`、`glm-5.3`、`kimi-k3`、`minimax-m3`、`glm-5.3-flash`、图片 / 视频模型不支持超额后付费）。
- **AFP 抵扣系数差 40 倍**：文本模型 `doubao-seed-2.0-mini` 0.25、`doubao-seed-2.0-lite` / `deepseek-v4-flash` 0.5、`doubao-seed-2.1-turbo` / `doubao-seed-evolving` / `minimax-m3` 2.5、`glm-5.3` / `kimi-k2.7-code` 4.5、`deepseek-v4-pro` 5.5、`kimi-k3` 10；一张 `doubao-seedream-5.0-lite` 图 99 AFP。写"帮用户省额度"的逻辑时按这张表选模型，详见 agent-plan.md。
- **视频生成永远是异步任务**：创建任务拿 `id`，轮询 `GET /contents/generations/tasks/{id}` 直到 `status` 终态；Agent Plan Small / Medium 档**不支持视频生成**（已用真实 API 验证（2026-09-04，Agent Plan Medium）：建 `doubao-seedance-2.0-mini` 任务 → `404 UnsupportedModel`）。图片生成是同步接口，也有流式事件版本；`doubao-seedream-5.0-lite` 的 `size` 只认 `WIDTHxHEIGHT` / `2k` / `3k` / `4k`，传 `1K` 报 400（实测），一张 2k 图 `usage.output_tokens` 16384、URL 是 24 小时有效的 TOS 签名链接。
- **强制 `tool_choice` 与 `json_schema` 在方舟是真生效的**（与某些国内平台不同）。已用真实 API 验证（2026-09-04）：`tool_choice: {"type":"function","function":{"name":"get_weather"}}` 对无关问题也返回 `finish_reason: "tool_calls"`（模型会编造参数）；`response_format: {"type":"json_schema",...}` 返回合法 JSON。
- **流式是标准 SSE**：`data: {...}` 逐行，`data: [DONE]` 结束；要 usage 需 `stream_options: {"include_usage": true}`（实测 chunk 内 `usage: null` 直到末尾）。Anthropic 入口的流式是标准 Anthropic 事件（`message_start` / `content_block_delta`…），鉴权头 `x-api-key` 与 `Authorization: Bearer` 都接受（实测）。
- **管控面 API 与数据面是两个世界**：域名、鉴权（AK/SK 签名）、请求形态（`?Action=X&Version=2024-01-01` + JSON body）全都不同。想在代码里"查我的 Agent Plan 还剩多少 AFP""轮换 Plan Key""列出当前可用 Model ID"，走管控面，不要试图用 API Key。用官方 `volcengine-python-sdk` 时注意：已在本机核实（2026-09-04，5.0.48）`volcenginesdkark.ARKApi` 只封装了接入点 / 批量 / 精调 / GetApiKey 等 17 个方法，**没有** `get_afp_usage`、`get_personal_plan`、`list_model_rate_limit`；Plan、用量、限流类 Action 要用同一 SDK 的 `volcenginesdkcore.UniversalApi(...).do_call(UniversalInfo(method="POST", service="ark", version="2024-01-01", action="GetAFPUsage", content_type="application/json"), body)`。
- **文档抄来的报错文案都标了"未实测"**，遇到实际报错以 API 返回为准，并对照 errors-and-limits.md 的错误码表。

## 目录结构

```
volcengine-ark/
├── SKILL.md                       # 你正在读的这份：三套入口对比 + 导航 + 通用规则 + 验证记录
└── references/
    ├── agent-plan.md              # Agent Plan：套餐/AFP/超额后付费/Harness/多模态接入/企业版
    ├── coding-plan.md             # Coding Plan：Lite/Pro、Model Name、ark-code-latest、Embedding 权益、FAQ
    ├── tools-setup.md             # 各 AI 编程 / Agent 工具的两套 Plan 配置，ArkCLI Helper
    ├── models.md                  # Model ID / Model Name 对照、能力矩阵、价格、Plan 内可用模型与 AFP 系数
    ├── chat.md                    # Chat Completions：参数全表、流式、思考、工具调用、结构化输出、缓存、分词
    ├── multimodal-input.md        # 图片/视频/文档/音频/文件输入、Files API、GUI Agent、Grounding
    ├── responses.md               # Responses API 全参数、input items、流式事件、迁移对照
    ├── tools.md                   # 内置工具（联网搜索/图像处理/知识库/Remote MCP/豆包助手）、三方框架接入
    ├── image-video.md             # Seedream 图片生成、Seedance 视频生成任务
    ├── embeddings-speech.md       # 多模态向量化、TTS/ASR、同声传译
    ├── batch-and-bot.md           # 批量(Chat)/批量(Job) API、应用 Bot API
    ├── management-api.md          # 管控面：Plan 套餐/用量/Key 管理、模型与限流查询
    ├── sdk-and-compat.md          # 官方 SDK、OpenAI/LangChain 兼容、Ark CLI、文档 MCP
    └── errors-and-limits.md       # 错误码全表、限流、Plan 常见报错、重试与计费口径
```

内容整理自 `https://www.volcengine.com/docs/82379`（抓取于 2026-09-03，经 `docs.volcengine.com/api/doc/getDocDetail` 取 Markdown 原文）及已登录控制台页面。平台迭代很快（模型周级上下线、抵扣系数有限时活动），字段或模型报"参数非法 / 模型不存在"时优先信任 API 实际返回，并建议用户去文档站核实。

## 验证记录（2026-09-04，Agent Plan 个人版 Medium，专属 Key）

| 做了什么 | 结果 |
|---|---|
| Agent Plan Key 打 `/api/v3`、`/api/coding/v3` | `401 {"error":{"code":"AuthenticationError","message":"The API key or AK/SK in the request is missing or invalid...","type":"Unauthorized"}}` |
| `/api/plan/v3/chat/completions` model `doubao-seed-2.0-lite` / `doubao-seed-2-0-lite-260428` | 均 200，响应 `"model":"doubao-seed-2-0-lite-260215"`（带日期 ID 被静默改版本） |
| model `auto` / `doubao-seed-2.1-pro` / `doubao-seed-1-8-251228` / Medium 档 `doubao-seedance-2.0-mini` | `404 {"error":{"code":"UnsupportedModel","message":"The requested model does not support the agent plan feature. Please refer to the documentation at https://www.volcengine.com/docs/82379/2366394 ..."}}` |
| model `ark-code-latest` / `glm-latest` / `kimi-k3` / `doubao-seed-2.0-mini` | 200；响应 model 分别为 `auto`、`glm-5.3`、`kimi-k3`、`doubao-seed-2-0-mini-260215` |
| `role: developer` | `400 InvalidParameter ... invalid value: developer, supported values are: system, assistant, user, tool` |
| `glm-5.3` + `thinking.disabled` / `reasoning_effort: none` / `reasoning_effort: low` | 400 `thinking.type disabled is not supported by this model` / 400 `reasoning_effort none is not supported by this model` / 200 且 `reasoning_tokens: 0` |
| `kimi-k3` `max_tokens: 64` → `max_completion_tokens: 400` | `finish_reason: length`、`content: ""` → 正常回答 |
| `service_tier: fast` | `400 InvalidParameter: fast service tier does not support coding plan`（`param: "service_tier"`） |
| 强制 `tool_choice` / `response_format json_schema` / `stream` + `include_usage` / `X-Prompt-Cache-Id` 头 | 均 200，行为符合预期 |
| `POST /embeddings` 字符串 / 多模态数组 / `dimensions: 1024` | 200 `data[0].embedding` 2048 维 / `400 input[0] expected a string` / 200 1024 维 |
| `POST /embeddings/multimodal` | 200 `data.embedding`（对象）2048 维，`model: doubao-embedding-vision-251215` |
| `POST /responses` 基础 / `store: true` + GET / `previous_response_id` / DELETE / `ark-code-latest` | 全部 200；DELETE 返回 `{"id":...,"object":"response","deleted":true}` |
| `POST /images/generations` `size: 1K` / `size: 2k` | 400 `size must be one of 'WIDTHxHEIGHT', '2k', '3k', or '4k'` / 200 `size: 2048x2048`，`output_tokens: 16384` |
| `GET /models`、`POST /tokenization`、`POST /context/create`、`GET /files` | 全部 404 |
| `/api/plan/v1/messages`（Anthropic）Bearer / `x-api-key` / `thinking.disabled` / `stream` / `model: claude-sonnet-4-5` | 均 200；思维链为 `thinking` block；Claude 模型名被路由到 `doubao-seed-2-1-turbo-260628` |

原始请求与完整响应在 `volcengine-ark-workspace/verification-log.jsonl`，探测脚本 `volcengine-ark-workspace/probe.py`（Key 只走环境变量）。
