# 火山方舟 Responses API 参考（`POST /api/v3/responses` 及配套接口）

本文覆盖火山方舟 **Responses API**：与 Chat Completions 的差异与迁移映射、创建 Response 的完整参数、`input` 各 item / content 类型、响应对象与 `output[]` item 结构、查询 / 列输入项 / 删除三个配套接口、全部流式 SSE 事件名与关键字段，以及多轮对话、深度思考、多模态、结构化输出、上下文编辑、工具调用在 Responses 下的写法。内置工具（`web_search` / `image_process` / `knowledge_search` / `mcp` / `doubao_app`）只给索引表，详细参数见 `tools.md`。

> 所有内容仅依据文中「来源页面」列出的官方文档；未实测的行为描述均标注 **（文档原文，未实测）**；文档没写清的地方以「文档未说明」警示标记标出。
>
> **验证范围说明**：标 **已用真实 API 验证（2026-09-04，Agent Plan Medium）** 的结论全部来自 **Agent Plan 入口 `/api/plan/v3/responses`**（专属 Key，模型 `doubao-seed-2.0-lite` → 实际 `doubao-seed-2-0-lite-260215`）。标准入口 `/api/v3` 无 Key，**未实测**；"标准入口预期相同"均为推断。原始请求 / 响应见 `volcengine-ark-workspace/verification-log.jsonl`。

## 目录

1. [入口、鉴权与 model 字段](#1-入口鉴权与-model-字段)
2. [与 Chat Completions 的差异与迁移对照表](#2-与-chat-completions-的差异与迁移对照表)
3. [创建 Response](#3-创建-response)
   - 3.1 顶层 Body 参数表
   - 3.2 `input` item 类型
   - 3.3 消息 `content` 内容类型（多模态输入）
   - 3.4 `tools[]` 类型索引与 `tool_choice`
   - 3.5 `text.format`（结构化输出）
   - 3.6 `context_management`（上下文编辑）
   - 3.7 示例请求 / 示例响应
4. [响应对象结构](#4-响应对象结构)
   - 4.1 顶层字段与 `status`
   - 4.2 `output[]` item 类型
   - 4.3 `usage`
5. [查询 Response 详情](#5-查询-response-详情)
6. [查询 Response 输入项列表](#6-查询-response-输入项列表)
7. [删除 Response](#7-删除-response)
8. [流式事件全表](#8-流式事件全表)
9. [我想…（按场景）](#9-我想按场景)
   - 9.1 多轮对话：`previous_response_id` / `store` / `expire_at` / 删除做窗口截断 / `instructions`
   - 9.2 深度思考：`thinking` / `reasoning.effort` / 思考摘要 / `encrypted_content` 回传
   - 9.3 多模态输入：图片 / 视频 / 文件 / 音频
   - 9.4 结构化输出 `text.format`
   - 9.5 上下文编辑 / 自动裁剪
   - 9.6 Function Calling 多轮回传
   - 9.7 上下文缓存 `caching`
   - 9.8 续写模式 `partial`
10. [限制、QPS 与不支持的场景](#10-限制qps-与不支持的场景)
11. [来源页面](#11-来源页面)

---

## 1. 入口、鉴权与 model 字段

| 入口 | Base URL | Responses API 是否可用 | Key 环境变量 | `model` 填什么 |
|---|---|---|---|---|
| 标准 API（后付费） | `https://ark.cn-beijing.volces.com/api/v3` | 可用（本文所有文档示例均为此入口） | `ARK_API_KEY` | 带日期版本的 Model ID（如 `doubao-seed-2-1-pro-260628`）或推理接入点 `ep-xxxx`（Endpoint ID，用于多应用分权） |
| Agent Plan | `https://ark.cn-beijing.volces.com/api/plan/v3` | **已用真实 API 验证（2026-09-04，Agent Plan Medium）：可用。** `POST /responses` 200；`store: true` → 响应含 `expire_at`；`GET /responses/{id}` 200；`previous_response_id` 续轮正确回忆上一轮内容；`DELETE /responses/{id}` → `{"id":"resp_…","object":"response","deleted":true}`；`model: ark-code-latest` 也可用（响应 `"model":"auto"`）。`GET /responses/{id}/input_items` 未测 | `ARK_AGENT_PLAN_API_KEY` | 小写 Model Name（如 `doubao-seed-2.0-lite`，实测响应 `"model":"doubao-seed-2-0-lite-260215"`）或 `ark-code-latest`。**`model: "auto"` 不能直接填**——**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Chat 入口 `auto` → 404 `{"error":{"code":"UnsupportedModel","message":"The requested model does not support the agent plan feature. ..."}}`，Responses 入口同一模型解析逻辑（`ark-code-latest` 响应回 `"model":"auto"`）。控制台警告：请勿改用 `/api/v3`，会产生额外费用（实测 Plan Key 打 `/api/v3` 是 401 AuthenticationError） |
| Coding Plan | `https://ark.cn-beijing.volces.com/api/coding/v3` | ⚠ 文档未说明是否支持 `/responses`（只说明兼容 OpenAI 协议；官方口径 Coding Plan 仅限 AI 编程工具内使用） | `ARK_API_KEY`（与标准 API 同一把） | 小写 Model Name |

- HTTP 头：`Authorization: Bearer <key>`、`Content-Type: application/json`。
- Responses API 独有可选头 `X-Fornax-Trace: true`：开启数据上报，可在推理接入点「分析统计」页看 Trace（文档：当前仅 Responses API 支持此 header）。
- 迁移文档中内置工具示例还带了 beta 头：`ark-beta-image-process: true`、`ark-beta-knowledge-search: true`、`ark-beta-mcp: true`（分别对应图像处理 / 知识库搜索 / MCP 示例）。是否必需 ⚠ 文档未说明（参考页字段表未提及），详见 `tools.md`。
- 支持模型：250615 及之后版本的大语言模型默认支持 Responses API；`doubao-1-5-pro-32k-character-250715` 不支持（文档原文）。

---

## 2. 与 Chat Completions 的差异与迁移对照表

| 维度 | Chat Completions (`/chat/completions`) | Responses API (`/responses`) | 备注 |
|---|---|---|---|
| 输入 | `messages[]`（每轮必须传全量历史） | `input`：字符串（= 单条 user 文本）或 InputItem 数组 | 见 3.2 |
| 系统提示词 | `messages[].role = system` | `input` 里 `role: system` / `developer`，或顶层 `instructions`（仅作用于本轮，不随 `previous_response_id` 继承） | Chat API 不支持 `developer` role（auth.md 已知坑），Responses 的参考页写明支持 |
| 最大输出长度 | `max_completion_tokens`（迁移文档用词；Chat API 参考页另有 `max_tokens`，二者**不**同义、互斥——**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：豆包 `max_tokens` 不含思维链，`kimi-k3` 的 `max_tokens` 含思维链把回答截空，见 `chat.md` §2.1） | `max_output_tokens`（含思维链 + 回答；实测 Plan 入口 `max_output_tokens: 64` 时 `output_tokens: 60`，其中 `reasoning_tokens: 59`，回答 1 token） | 开思考时 Chat 侧统一用 `max_completion_tokens` |
| 结构化输出 | `response_format: {type: json_object \| json_schema}` | `text: {format: {type, name, schema, strict, description}}` | 两边都是 beta |
| 函数工具定义 | `tools[] = {type:"function", function:{name, description, parameters}}` | `tools[] = {type:"function", name, description, parameters}`（去掉 `function` 包一层） | 见 9.6 |
| 工具调用回传 | assistant `tool_calls` → `role: tool` 消息 | `output[]` 里 `function_call` item（`call_id`）→ 下一轮 `input` 里 `function_call_output` item（同 `call_id`） | |
| 内置工具 | 不支持（迁移文档原文） | `web_search` / `image_process` / `knowledge_search` / `mcp` / `doubao_app` | 详见 `tools.md` |
| 多轮 / 状态 | 无状态 | 文档：默认 `store: true`，用 `previous_response_id` 串联；`expire_at` 控制保留时长（默认 3 天，最长 7 天）。**已用真实 API 验证（2026-09-04，Agent Plan Medium）：Plan 入口不传 `store` 时响应回显 `"store":false` 且无 `expire_at`**——与文档默认值相反，要续轮必须显式 `store: true` | 见 9.1 |
| 上下文缓存 | Context API（`context.create` + `context.completions`） | `caching: {type:"enabled"}` + `previous_response_id`，同样受 `expire_at` 约束 | 250615 之后模型支持（迁移文档） |
| 深度思考开关 | `thinking: {type}` | `thinking: {type}` 同名，另有 `reasoning: {effort}` 调思考长度 | 见 9.2 |
| 思维链输出 | `choices[].message.reasoning_content` | `output[]` 中 `type: reasoning` item：`summary[].text`（摘要）/ `content[]`（`reasoning_text`）/ `encrypted_content` | 默认输出摘要而非原文 |
| 回答文本 | `choices[0].message.content` | `output[]` 中 `type: message` item → `content[].type = output_text` → `.text` | |
| 结束原因 | `finish_reason` | 顶层 `status`（`completed` / `incomplete` / `failed` / `in_progress`）+ `incomplete_details` | |
| usage | `prompt_tokens` / `completion_tokens` / `prompt_tokens_details.cached_tokens` / `completion_tokens_details.reasoning_tokens` | `input_tokens` / `output_tokens` / `input_tokens_details.cached_tokens` / `output_tokens_details.reasoning_tokens` / `tool_usage` | 见 4.3 |
| 流式 | `chat.completion.chunk` 对象流 | SSE 带 `event:` 名的类型化事件（`response.created` … `response.completed`），以 `data: [DONE]` 结束 | 见 8 |
| 响应对象 | `object: chat.completion`，`id` 无前缀 | `object: response`，`id` 形如 `resp_…`；item id 形如 `rs_…`（reasoning）、`msg_…`（message）、`fc_…`（function_call） | 文档示例观察，前缀规则 ⚠ 文档未说明 |
| 不支持场景 | — | TPM 保障包、精调后模型在线推理、智能模型路由、在线推理服务的模型版本切换（文档原文） | |

迁移建议（文档原文）：新模型在两套 API 同步适配；可先在工具调用与缓存场景切到 Responses，稳定后再全面替换。

---

## 3. 创建 Response

### 创建 Response
**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/v3/responses`（Agent Plan：`POST https://ark.cn-beijing.volces.com/api/plan/v3/responses`）
**用途**: 一次模型调用，产出一个可被存储、引用（`previous_response_id`）、查询、删除的 Response 对象；Chat Completions 的替代品，且是内置工具的唯一入口。

#### 3.1 顶层 Body 参数表

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | — | 标准入口：Model ID，或推理接入点 Endpoint ID。Plan 入口：小写 Model Name——**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`doubao-seed-2.0-lite` → 响应 `"model":"doubao-seed-2-0-lite-260215"`；`ark-code-latest` → 响应 `"model":"auto"`；`auto` 本身 404 UnsupportedModel（Chat 入口实测，同一解析逻辑）；带日期 Model ID 会被静默改版本（见 `models.md` §1.1） |
| `input` | string / object[] | 是 | — | 字符串 = 单条 user 文本；数组 = InputItem 列表（3.2） |
| `instructions` | string | 否 | — | 作为系统 / 开发者指令插到上下文首项。与 `previous_response_id` 同用时不继承到下一轮。**与缓存互斥**：配置后本轮不能写 / 读缓存——`caching: {type: enabled}` 会报错；带缓存的 `previous_response_id` 时 `cached_tokens` 为 0（文档原文，未实测） |
| `max_output_tokens` | integer | 否 | ⚠ 文档未说明（示例响应回显 32768） | 本次输出最大 token，含回答 + 思维链；实际上限受模型上下文长度限制 |
| `max_tool_calls` | integer | 否 | 按工具类型：`web_search` 3、`image_process` 10（不可改）、`knowledge_search` 3；`doubao_app` 不支持 | 最大工具调用**轮次**（一轮内不限次数），范围 `[1, 10]`；best effort，不保证 |
| `previous_response_id` | string | 否 | — | 上一轮 Response id，引入其输入与回答（输入 tokens 相应增加）。文档建议连续请求间隔约 100 ms，否则可能调用失败（文档原文，未实测）。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：第一轮 `store: true` 说"记住数字 42"（`input_tokens: 50`），第二轮带 `previous_response_id` 问"我刚说的数字是？" → `output_text: "42"`，`input_tokens: 90`（历史被计入），响应回显 `previous_response_id`；第二轮自身未传 `store`，回显 `"store":false` |
| `store` | boolean | 否 | 文档 `true`；**Plan 入口实测 `false`** | 是否存储本轮 input + output（不存思维链）供后续检索 / 引用。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：不传时 `/api/plan/v3/responses` 响应回显 `"store":false`、无 `expire_at`；显式 `"store": true` 后回显 `"store":true,"expire_at":1788746798`（= `created_at` 1788487599 + 259200，正好 3 天，与文档默认时长一致）。标准入口默认值未测 |
| `expire_at` | integer | 否 | 创建时刻 + 259200（3 天） | UTC Unix 秒；对 `store` 与 `caching` 都生效；范围 `(创建时刻, 创建时刻 + 604800]`（最多 7 天）；缓存存储计费按 `过期时刻 - 创建时刻`，不满 1 小时按 1 小时。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`store: true` 时响应自动带 `expire_at`，默认 +3 天 |
| `caching` | object | 否 | `{type: "disabled"}` | `type`: `enabled` / `disabled`；`prefix`（bool，默认 false）= 只写前缀缓存不生成回复。**不可与 `instructions`、`tools`（Function Calling 除外）一起用**。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：不传时响应顶层回显 `"caching":{"type":"disabled"}`；`enabled` 未测 |
| `context_management` | object | 否 | — | `edits[]`：`clear_thinking` / `clear_tool_uses` 策略（3.6） |
| `include` | string[] | 否 | — | 附加返回数据。文档唯一列出的值：`reasoning.encrypted_content`（返回加密压缩后的思考原文，可手动回传） |
| `reasoning` | object | 否 | 按模型（9.2） | `effort`: `none` / `minimal` / `low` / `medium` / `high` / `xhigh` / `max` |
| `thinking` | object | 否 | 未传 = 开启深度思考 | `type`: `enabled` / `disabled` / `auto`（`auto` 仅 `doubao-seed-1-6-250615` 支持） |
| `service_tier` | string | 否 | `default` | `default` 常规；`fast` 优先低延迟，无配额时自动降级为常规 |
| `stream` | boolean | 否 | `false` | `true` 走 SSE，以 `data: [DONE]` 结束 |
| `temperature` | number | 否 | `1.0` | 范围 `[0, 2]`。`doubao-seed-2-0-code-preview-260215` / `doubao-seed-2-0-pro-260215` / `doubao-seed-2-0-lite-260215` 固定为 1，传入被忽略 |
| `top_p` | number | 否 | `0.7` | 范围 `[0, 1]`。上述三款 260215 模型及 `doubao-seed-1-8-251228` 固定 0.95。建议只调 `temperature` 或 `top_p` 之一 |
| `text` | object | 否 | — | `format`（3.5） |
| `tools` | object[] | 否 | — | 内置工具 / MCP / function（3.4） |
| `tool_choice` | string / object | 否 | 无工具 `none`；有工具 `auto` | 字符串 `none` / `auto` / `required`，或对象 `{type, name}`；仅 Doubao Seed 1.8 / 2.0 系列支持 |

#### 3.2 `input` item 类型

`input` 为数组时，每个元素以 `type` 区分（消息可省略 `type`，默认 `message`）：

| `type` | 必填字段 | 可选字段 | 用途 |
|---|---|---|---|
| `message`（默认） | `content`（string 或 content[]，3.3） | `role`（`user` / `system` / `assistant` / `developer`）、`id`、`partial`（bool，仅 assistant，续写模式须显式 `true`） | 普通消息；developer / system 优先级高于 user |
| `function_call` | `type` | `call_id`、`id`、`name`、`arguments`（JSON 字符串）、`status`（`in_progress` / `completed` / `incomplete`） | 回传模型上一轮发起的函数调用（不用 `previous_response_id` 时手动拼历史） |
| `function_call_output` | `type` | `call_id`（须与 function_call 一致）、`id`、`output`（string，或与 3.3 相同的 content[]） | 把函数执行结果交给模型 |
| `reasoning` | `type`、`status` | `id`、`content[]`（`output_text` / `reasoning_text`）、`summary[]`（`{type:"summary_text", text}`）、`encrypted_content` | 手动管理思维链上下文。Agent 场景不用 `previous_response_id` 时**必须**回传 `encrypted_content`（`doubao-seed-2-0-lite-260428` 及后续） |
| `mcp_approval_request` | `type`、`arguments`、`name`、`server_label` | `id` | 回传历史 MCP 审批请求 |
| `mcp_approval_response` | `type`、`approval_request_id`、`approve`（bool） | `id`、`reason` | 回复 MCP 审批（批准 / 拒绝） |
| `mcp_list_tools` | `type`、`server_label` | `id`、`error`、`tools[]`（`name`、`description`、`input_schema`、`annotations`） | 回传历史 MCP 工具清单 |
| `mcp_call` | `type`、`name`、`server_label` | `id`、`arguments`、`output`、`error` | 回传历史 MCP 调用记录 |
| `item_reference` | `type`、`id` | — | 引用一条已存储的上下文条目（消息 / 助手回复 / 工具输出） |

#### 3.3 消息 `content` 内容类型（多模态输入）

`message.content` 与 `function_call_output.output` 可为字符串，或下列对象的数组：

| `type` | 字段 | 说明 |
|---|---|---|
| `input_text` | `text`（必填）、`translation_options`（object，源 / 目标语言，子字段 ⚠ 文档未说明） | 文本 |
| `input_image` | `image_url`（URL 或 `data:image/{格式};base64,{编码}`）、`file_id`、`detail`（`auto` / `low` / `high` / `xhigh`）、`image_pixel_limit: {min_pixels, max_pixels}` | `image_pixel_limit` 优先级高于 `detail`；像素范围须在 `[196, 36000000]` 否则直接报错（文档原文，未实测）。`max_pixels` 上限：seed-1.8 之前 4014080，seed-1.8 / 2.0 为 9031680；`min_pixels` 下限分别 3136 / 1764 |
| `input_video` | `video_url`（必填：HTTP(S) 或 data URL base64）、`file_id`、`fps`（`[0.2, 5]`） | 用 `file_id` 传视频时 `fps` 失效（抽帧在 Files API 上传时用 `preprocess_configs[video][fps]` 指定）。⚠ 文档自相矛盾：`video_url` 标「必选」但又说支持 `file_id` 传入 |
| `input_file` | `file_id`、`file_url`、`file_data`（base64）、`filename`（用 `file_data` 时必传） | 文件上限 50 MB（`file_data` / `file_url`）；PDF 会分页转多图输入 |
| `input_audio` | `audio_url`（URL 或 base64）、`file_id`、`chunking_strategy: {type:"server_vad", prefix_padding_ms, silence_duration_ms, threshold}` | 音频输入；对应输出 `transcription` item 与转写事件。支持模型 ⚠ 文档未说明 |
| `output_text` | `text`、`annotations[]`（`url_citation` / `doc_citation`） | 回传上一轮助手回答 |
| `reasoning_text` | `text`、`annotations[]` | 回传上一轮思维链文本 |

`file_id` 支持范围（三种模态相同）：`doubao-seed-2.0-mini` 260428 及后续；`doubao-seed-2.0-lite`、`doubao-seed-2.0-pro` 全版本。Files API 上传：`POST /api/v3/files`，`purpose=user_data`，单文件最大 512 MB，默认存 7 天（1–30 天可调）。

`annotations[]` 两种类型：`url_citation`（`title`、`url` 必填；`cover_image{height,url,width}`、`freshness_info`、`logo_url`、`mobile_url`、`publish_time`、`site_name`、`summary`）与 `doc_citation`（`doc_id`、`doc_name`、`chunk_id`、`chunk_attachment[]`）。

#### 3.4 `tools[]` 类型索引与 `tool_choice`

| `tools[].type` | 一句用途 | 关键字段（详见 `tools.md`） | 对应 `output[]` item |
|---|---|---|---|
| `function` | 自定义函数调用 | `name`（必填）、`description`、`parameters`（JSON Schema） | `function_call` |
| `web_search` | 联网搜索实时信息 | `limit`（默认 10，`[1,50]`）、`max_keyword`（`[1,50]`）、`sources[]`（`toutiao` / `douyin` / `moji` / `search_engine`）、`user_location{type:"approximate", city, country, region, timezone}` | `web_search_call` |
| `image_process` | 对输入图片画点 / 选区 / 缩放 / 旋转 | `grounding` / `point` / `rotate` / `zoom` 各 `{type: enabled\|disabled}`（默认 enabled）；缩放 0.5–2.0 倍，旋转 0–359 度 | `image_process` |
| `mcp` | 调远端 MCP Server（Remote MCP） | `server_label`、`server_url`（必填）、`allowed_tools`（string[] 或 `{tool_names}`）、`headers`（`Authorization` 不落库）、`require_approval`（默认 `always`；`never`；或 `{always:{tool_names}, never:{tool_names}}`）、`server_description` | `mcp_list_tools` / `mcp_approval_request` / `mcp_call` |
| `knowledge_search` | 检索私域知识库（仅旗舰版） | `knowledge_resource_id`（必填）、`limit`（默认 10，`[1,200]`）、`max_keyword`、`dense_weight`（默认 0.5，`[0.2,1]`）、`description`、`doc_filter`、`ranking_options{chunk_diffusion_count, chunk_group, get_attachment_link, rerank_model, rerank_only_chunk, rerank_switch, retrieve_count}` | `knowledge_search_call` |
| `doubao_app` | 使用豆包助手的聊天 / 深度聊天 / AI 搜索 / 推理搜索 | `feature{chat, deep_chat, ai_search, reasoning_search}` 各 `{type, role_description}`（`role_description` 与 system prompt / `instructions` 互斥，以它为准）、`user_location` | `doubao_app_call` |

`tool_choice` 对象形式：`{"type": "function" | "web_search" | "image_process" | "mcp" | "knowledge_search" | "doubao_app", "name": "<函数名或 MCP 工具名>"}`。

#### 3.5 `text.format`（结构化输出，beta）

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string（必填） | `text` / `json_object` / `json_schema`（后两者 beta） |
| `name` | string | `json_schema` 时需要 |
| `schema` | object | JSON Schema，`json_schema` 时必填 |
| `strict` | boolean | 严格校验，仅 `json_schema` 生效 |
| `description` | string | 格式描述 |

#### 3.6 `context_management`（上下文编辑，beta）

`context_management.edits[]` 按顺序执行；组合使用时 `clear_thinking` 必须排在 `clear_tool_uses` 之前。

| `edits[].type` | 字段 | 说明 |
|---|---|---|
| `clear_thinking` | `keep`（必填）：`"all"` 或 `{type:"thinking_turns", value: N}`（N ≥ 0 按参考页；教程页说 N 必须 > 0 ⚠ 文档自相矛盾） | 清除较旧轮次思维链。教程页默认值 `{type:"thinking_turns", value:1}` |
| `clear_tool_uses` | `trigger: {type:"tool_uses", value}`（累计工具调用达阈值触发）、`keep: {type:"tool_uses", value}`（保留最近 N 次，教程页默认 3）、`exclude_tools: string[]`、`clear_tool_inputs`（参考页：object，必填，`{clear_all: bool}` 或 `{tool_name_list: {clear_tool_names: []}}`；教程页：Bool，默认 false ⚠ 文档自相矛盾） | 清除较旧工具调用记录 |

响应中回显 `context_management.applied_edits[]`：`{type:"clear_thinking", cleared_thinking_turns}` / `{type:"clear_tool_uses", cleared_tool_uses}`。

#### 3.7 示例请求 / 示例响应

**示例请求（curl）**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/responses \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seed-2-1-pro-260628",
    "input": [
      {"role": "system", "content": "你是 AI 人工智能助手"},
      {"role": "user", "content": "常见的十字花科植物有哪些？"}
    ],
    "thinking": {"type": "enabled"},
    "reasoning": {"effort": "low"},
    "max_output_tokens": 1024
  }'
```

**示例请求（Python，OpenAI SDK）**

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key=os.getenv("ARK_API_KEY"),
)
resp = client.responses.create(
    model="doubao-seed-2-1-pro-260628",
    input=[
        {"role": "system", "content": "你是 AI 人工智能助手"},
        {"role": "user", "content": "常见的十字花科植物有哪些？"},
    ],
    reasoning={"effort": "low"},
    max_output_tokens=1024,
    # 方舟私有字段（thinking / caching / context_management / expire_at 等）用 OpenAI SDK 时放 extra_body
    extra_body={"thinking": {"type": "enabled"}},
)
for item in resp.output:
    if item.type == "message":
        for c in item.content:
            if c.type == "output_text":
                print(c.text)
```

官方 `volcenginesdkarkruntime` SDK 写法相同：`from volcenginesdkarkruntime import Ark; client = Ark(base_url=..., api_key=...); client.responses.create(model=..., input=..., thinking={"type": "enabled"})`，私有字段可直接作为关键字参数。底层同为 `POST /api/v3/responses`。

**示例响应（非流式）——已用真实 API 验证（2026-09-04，Agent Plan Medium），`POST /api/plan/v3/responses`，请求 `{"model":"doubao-seed-2.0-lite","input":"用一个词回答：1+1=?","max_output_tokens":64}`，原样返回（思维链文本截短）：**

```json
{
  "created_at": 1788487354,
  "id": "resp_0217884873503508b056a623bf426f62c797dc732369cf9be0fc2",
  "max_output_tokens": 64,
  "model": "doubao-seed-2-0-lite-260215",
  "object": "response",
  "output": [
    {
      "id": "rs_02178848735460400000000000000000000ffffac153770bbc592",
      "type": "reasoning",
      "summary": [{"type": "summary_text", "text": "\n用户现在需要用一个词回答1+1等于多少，首先常规数学里是2对吧……"}],
      "status": "completed"
    },
    {
      "type": "message",
      "role": "assistant",
      "content": [{"type": "output_text", "text": "2"}],
      "status": "completed",
      "id": "msg_02178848735556600000000000000000000ffffac1537709c1d90"
    }
  ],
  "service_tier": "default",
  "status": "completed",
  "usage": {
    "input_tokens": 59,
    "output_tokens": 60,
    "total_tokens": 119,
    "input_tokens_details": {"cached_tokens": 0},
    "output_tokens_details": {"reasoning_tokens": 59}
  },
  "caching": {"type": "disabled"},
  "store": false
}
```

实测形态要点（与迁移文档示例一致的部分不再重复）：
- `reasoning` item 的思维链在 `summary[].text`，`summary[].type` 为 `summary_text`；260215 明文模型这里就是完整原文而非摘要，**没有** `content[]`、**没有** `encrypted_content`（未传 `include`）。
- `message` item 的回答在 `content[0].text`，`content[0].type` 为 `output_text`；实测无 `annotations` 字段。
- `usage.output_tokens_details.reasoning_tokens` 存在；`usage.input_tokens_details` 只有 `cached_tokens`。
- 顶层默认回显 `"caching":{"type":"disabled"}` 与 `"store":false`（**文档说默认 `store: true`，Plan 入口实测为 `false`**，无 `expire_at`）。传 `store: true` 后回显 `"store":true,"expire_at":<created_at+259200>`；传 `thinking: {"type":"disabled"}` 后回显 `"thinking":{"type":"disabled"}` 且 `output[]` 只剩 `message` item。
- `model: ark-code-latest` 时响应 `"model":"auto"`、`reasoning_tokens: 0`、`output[]` 只有 `message` item（当次路由到的模型未开思考）。
- 迁移文档示例（`doubao-seed-2-1-pro-260628`，标准入口）多出的 `max_output_tokens: 32768` 默认回显、`store: true`、`expire_at` 在 Plan 入口未复现；标准入口未测。

**注意事项**
- `output[]` 顺序：开启思考时先 `reasoning` item 再 `message` item；有工具调用时会出现 `function_call` / 内置工具 item。取文本要按 `item.type == "message"` 过滤，不要写死 `output[0]`（实测 `ark-code-latest` / `thinking.disabled` 时 `output[0]` 就是 `message`，开思考时是 `reasoning`）。
- 非流式 + 深度思考容易超时；文档推荐深度思考场景使用流式（9.2）。
- `instructions` 与 `caching` 互斥；`caching` 与除 function 外的 `tools` 互斥。
- 三款 `*-260215` 模型 `temperature` / `top_p` 固定值，传参被忽略。

---

## 4. 响应对象结构

### 4.1 顶层字段与 `status`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | Response 唯一标识（`resp_…`） |
| `object` | string | 固定 `response` |
| `created_at` | integer | Unix 秒 |
| `model` | string | 实际使用的模型 |
| `status` | string | `completed` / `failed` / `in_progress` / `incomplete`（查询详情页给出的枚举） |
| `incomplete_details` | object | `reason`（string，枚举 ⚠ 文档未说明）、`content_filter{type, details}` |
| `error` | object | `code`、`message`（模型未能生成时） |
| `output` | object[] | 见 4.2 |
| `usage` | object | 见 4.3 |
| `previous_response_id` | string | 回显 |
| `instructions` / `max_output_tokens` / `max_tool_calls` / `temperature` / `top_p` / `service_tier` / `store` / `expire_at` / `thinking` / `reasoning` / `text` / `tool_choice` / `tools` / `caching` | 同请求 | 回显本次实际生效的配置。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：只回显传了的字段 + `service_tier`（`default`）、`caching`（`{"type":"disabled"}`）、`store`（未传时 `false`）、`max_output_tokens`（传了才回显）；`expire_at` 仅 `store: true` 时出现；`temperature` / `top_p` / `reasoning` 未传则不回显 |
| `context_management` | object | `applied_edits[]`（3.6） |

存储规则（文本生成页原文）：`status` 为 `completed`，或因长度限制截断为 `incomplete` 时都会存储本轮；若思维链触发长度截断，查询时 `output` 为空。

### 4.2 `output[]` item 类型

| `type` | 关键字段 | 说明 |
|---|---|---|
| `message` | `id`、`role`（固定 `assistant`）、`status`、`content[]`：`output_text{text, annotations[]}` / `reasoning_text{text, annotations[]}` | 模型回答 |
| `reasoning` | `id`、`status`、`summary[]{type:"summary_text", text}`、`content[]`（`output_text` / `reasoning_text`）、`encrypted_content`（仅 `include` 含 `reasoning.encrypted_content` 时返回；`doubao-seed-2-0-lite-260428` 及后续） | 思维链 |
| `function_call` | `id`、`call_id`、`name`、`arguments`（JSON 字符串）、`status` | 待你执行的函数调用 |
| `transcription` | `id`、`status`、`transcription[]{type:"transcription_text", text, chunks[]{start_time, end_time, text}}`（毫秒） | 音频输入的语音转写 |
| `web_search_call` | `id`、`status`（`in_progress` / `searching` / `completed` / `incomplete` / `failed`）、`action{type:"search", query}` | 联网搜索记录 |
| `image_process` | `id`、`status`、`action{type, result_image_url}`、`arguments`（object）、`error{message}` | 图像处理记录 |
| `mcp_list_tools` | `id`、`server_label`、`tools[]{name, description, input_schema, annotations}`、`error` | MCP 工具清单 |
| `mcp_approval_request` | `id`、`server_label`、`name`、`arguments` | 需要你用 `mcp_approval_response` 回复 |
| `mcp_call` | `id`、`server_label`、`name`、`arguments`、`output`、`error` | MCP 调用及结果（`arguments` 流式下由 `response.mcp_call_arguments.delta` 追加，`output_item.added` 时可能没有） |
| `knowledge_search_call` | `id`、`status`（`in_progress` / `searching` / `completed` / `failed` / `incomplete`）、`knowledge_resource_id`、`queries[]` | 知识库检索记录 |
| `doubao_app_call` | `id`、`status`、`feature`（`chat` / `deep_chat` / `ai_search` / `reasoning_search`）、`blocks[]`：`output_text{text}` / `reasoning_text{reasoning_text}` / `search{queries, results[]{text_card{sitename,title,url}}, summary}` / `reasoning_search{…同 search}`，每块含 `id`、`parent_id`、`status` | 豆包助手调用 |
| `agent_tool_call` | `id`、`name`、`status` | 智能体工具调用（对应哪个 `tools[].type` ⚠ 文档未说明） |

item 级 `status` 枚举（message / function_call / reasoning / transcription / image_process 等）：`completed` / `in_progress` / `incomplete` / `failed`。

### 4.3 `usage`

| 字段 | 说明 |
|---|---|
| `input_tokens` / `output_tokens` / `total_tokens` | 输入 / 输出 / 总量 |
| `input_tokens_details.cached_tokens` | 命中缓存的输入 token |
| `input_tokens_details.audio_tokens` / `audio_cached_tokens` | 音频输入 / 音频缓存 token |
| `output_tokens_details.reasoning_tokens` | 思维链 token（按**原始**思考内容计，即使只返回摘要） |
| `tool_usage.{web_search, knowledge_search, mcp, doubao_app}` | 各内置工具调用次数（integer） |
| `tool_usage_details.{web_search, knowledge_search, mcp, doubao_app}` | 各工具用量明细（object，子字段 ⚠ 文档未说明） |

---

## 5. 查询 Response 详情

### 查询 Response 详情
**Endpoint**: `GET https://ark.cn-beijing.volces.com/api/v3/responses/{response_id}`
**用途**: 按 id 取回已存储（`store: true`）的完整 Response 对象；与「列输入项」的区别是它返回的是**输出**侧（整个 Response），不是历史输入。

**关键参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `response_id` | path | string | 是 | Response ID |
| `include` | query | string[] | 否 | 如 `reasoning.encrypted_content` |

**示例请求**

```bash
curl "https://ark.cn-beijing.volces.com/api/v3/responses/$RESPONSE_ID?include=reasoning.encrypted_content" \
  -H "Authorization: Bearer $ARK_API_KEY"
```

```python
resp = client.responses.retrieve(response_id)          # OpenAI SDK / Ark SDK 同名
print(resp.status, [i.type for i in resp.output])
```

**示例响应**：与 4 节的 Response 对象结构完全一致。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`GET /api/plan/v3/responses/resp_0217884875989…` → 200，返回体与创建时的响应**逐字节一致**（含 `output[]`、`usage`、`thinking`、`store: true`、`expire_at`）。

**注意事项**
- 「如果 Response 仍在生成中，接口会返回错误码」——具体错误码 ⚠ 文档未说明（文档原文，未实测）。
- 账号维度 QPS 限流 20。
- `store: false` 的 Response 无法查询（由 `store` 语义推出，文档未直接写明）。

---

## 6. 查询 Response 输入项列表

### 查询 Response 输入项列表
**Endpoint**: `GET https://ark.cn-beijing.volces.com/api/v3/responses/{response_id}/input_items`
**用途**: 分页列出创建该 Response 时传入的 `input`，以及通过 `previous_response_id` 链上来的全部历史输入项——用来审计 / 还原对话上下文。

**关键参数**

| 参数 | 位置 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|---|
| `response_id` | path | string | 是 | — | |
| `after` | query | string | 否 | — | 返回该 item id 之后的项（向后翻页） |
| `before` | query | string | 否 | — | 返回该 item id 之前的项（向前翻页） |
| `limit` | query | integer | 否 | 20 | `[1, 100]` |
| `order` | query | string | 否 | `desc` | `asc` / `desc` |
| `include` | query | string[] | 否 | — | 唯一可选值 `message.input_image.image_url`：让返回包含输入图片的 URL（URL 传入返 URL，base64 传入返 base64） |

**示例请求**

```bash
curl "https://ark.cn-beijing.volces.com/api/v3/responses/$RESPONSE_ID/input_items?limit=50&order=asc" \
  -H "Authorization: Bearer $ARK_API_KEY"
```

```python
page = client.responses.input_items.list(response_id, limit=50, order="asc")
for item in page.data:
    print(item.type, getattr(item, "role", None))
```

**示例响应（结构）**

```json
{
  "data": [
    {"type": "message", "role": "system", "content": "你是李雷", "id": "..."},
    {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "我是方方"}], "id": "..."},
    {"type": "function_call_output", "call_id": "call_...", "output": "..."}
  ]
}
```

`data[]` 元素结构与 3.2 的 InputItem 完全一致。响应是否含 `first_id` / `last_id` / `has_more` 等分页游标字段 ⚠ 文档未说明（参考页只列出 `data`）。

**注意事项**：QPS 限流 20。默认不返回图片 URL / base64，需要时加 `include=message.input_image.image_url`。

---

## 7. 删除 Response

### 删除 Response
**Endpoint**: `DELETE https://ark.cn-beijing.volces.com/api/v3/responses/{response_id}`
**用途**: 删除一条已存储的 Response；也是「窗口截断」的手段——删掉链中的某一轮，后续 `previous_response_id` 引用链就不再包含它（9.1）。

**关键参数**：path `response_id`（string，必填）。

**示例请求**

```bash
curl -X DELETE "https://ark.cn-beijing.volces.com/api/v3/responses/$RESPONSE_ID" \
  -H "Authorization: Bearer $ARK_API_KEY"
```

```python
r = client.responses.delete(response_id)
print(r.deleted, r.id)
```

**示例响应**

```json
{"id": "resp_02178848759890133412155cdacfc777b8945c244aabe1bd32b5b", "object": "response", "deleted": true}
```

**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`DELETE /api/plan/v3/responses/{id}` 对 `store: true` 的 Response → 200，返回体就是上面这三字段。

`deleted`：`true` 删除成功，`false` 未删除成功。QPS 限流 20。删除后再用它作 `previous_response_id` 的行为 ⚠ 文档未说明（未实测）。

---

## 8. 流式事件全表

`stream: true` 时服务端以 SSE 推送，每条形如：

```
event: response.output_text.delta
data: {"type":"response.output_text.delta","item_id":"msg_...","output_index":1,"content_index":0,"delta":"十字花科","sequence_number":42}
```

所有事件共有 `type`（= 事件名）和 `sequence_number`（递增序号）。流以 `data: [DONE]` 结束。事件名与文档字段名以 `event:` 行 / `type` 字段为准。

**生命周期（payload 均为 `response` 对象，结构同非流式响应）**

| 事件 | 触发 | 关键字段 |
|---|---|---|
| `response.created` | 创建 | `response`（`status: in_progress` 阶段的对象，含 `id`、`model`、`store`、`expire_at` 等） |
| `response.in_progress` | 开始生成 | `response` |
| `response.completed` | 正常完成 | `response`（含完整 `output[]` 与 `usage`） |
| `response.incomplete` | 截断（如 `max_output_tokens`） | `response`（`incomplete_details`） |
| `response.failed` | 失败 | `response`（`error`） |

**Output Item 骨架**

| 事件 | 关键字段 |
|---|---|
| `response.output_item.added` | `output_index`、`item`（新 item，通常只有 `id` / `type` / `status: in_progress`） |
| `response.output_item.done` | `output_index`、`item`（完整 item） |

**文本回答（message item）**

| 事件 | 关键字段 |
|---|---|
| `response.content_part.added` | `item_id`、`output_index`、`content_index`、`part`（`output_text` 或 `reasoning_text`，含 `text`、`annotations`） |
| `response.content_part.done` | 同上，`part` 为完成态 |
| `response.output_text.delta` | `item_id`、`output_index`、`content_index`、`delta` |
| `response.output_text.done` | `item_id`、`output_index`、`content_index`、`text` |
| `response.output_text.annotation.added` | `item_id`、`output_index`、`content_index`、`annotation_index`、`annotation`（`url_citation` / `doc_citation`） |

**思维链（reasoning item）**

| 事件 | 关键字段 | 说明 |
|---|---|---|
| `response.reasoning_summary_part.added` / `.done` | `item_id`、`output_index`、`summary_index`、`part{type:"summary_text", text}` | 思考摘要分段（默认输出摘要） |
| `response.reasoning_summary_text.delta` | `item_id`、`output_index`、`summary_index`、`delta` | 摘要增量——**取思考文本用这个** |
| `response.reasoning_summary_text.done` | 同上，`text` | |
| `response.reasoning_text.delta` / `.done` | `item_id`、`output_index`、`content_index`、`delta` / `text` | `content[]` 中 `reasoning_text` 的增量 |
| `response.reasoning_raw_text.delta` / `.done` | `item_id`、`output_index`、`content_index`、`delta` / `text` | 原始推理文本；何时下发 ⚠ 文档未说明 |

流式下 `encrypted_content` 通过 `response.output_item.added` / `.done` / `response.completed` 等事件携带，按 `encrypted_content` 非空过滤。

**工具调用（通用与 function）**

| 事件 | 关键字段 |
|---|---|
| `response.function_call_arguments.delta` | `item_id`、`output_index`、`delta` |
| `response.function_call_arguments.done` | `item_id`、`output_index`、`arguments`（完整 JSON 字符串） |
| `response.agent_tool_call.in_progress` / `.completed` | `item_id`、`output_index`、`name` |

**内置工具事件**

| 工具 | 事件 | 附加字段（除 `item_id`、`output_index`、`sequence_number`、`type`） |
|---|---|---|
| web_search | `response.web_search_call.in_progress` / `.searching` / `.completed` | — |
| knowledge_search | `response.knowledge_search_call.in_progress` / `.searching` / `.completed` / `.failed` | — |
| image_process | `response.image_process_call.in_progress` | — |
| image_process | `response.image_process_call.progressing` / `.completed` | `action`、`arguments` |
| MCP | `response.mcp_approval_request` | `output_index`、`function_mcp_approval_request`（审批请求对象） |
| MCP | `response.mcp_list_tools.in_progress` / `.completed` / `.failed` | — |
| MCP | `response.mcp_call.in_progress` / `.completed` / `.failed` | — |
| MCP | `response.mcp_call_arguments.delta` / `.done` | `delta` / `arguments` |
| doubao_app | `response.doubao_app_call.in_progress` | `feature` |
| doubao_app | `response.doubao_app_call.completed` | `feature`、`blocks[]` |
| doubao_app | `response.doubao_app_call.failed` | `error_message` |
| doubao_app | `response.doubao_app_call_block.added` / `.done` | `block` |
| doubao_app | `response.doubao_app_call_output_text.delta` / `.done` | `block_index`、`delta` / `text` |
| doubao_app | `response.doubao_app_call_reasoning_text.delta` / `.done` | `block_index`、`delta` / `text` |
| doubao_app | `response.doubao_app_call_search.in_progress` / `.searching` / `.completed` | `block_index`；searching 带 `searching_state`；completed 带 `queries`、`results[]`、`summary` |
| doubao_app | `response.doubao_app_call_reasoning_search.in_progress` / `.searching` / `.completed` | 同上 |

**语音转写（transcription item）**

| 事件 | 关键字段 |
|---|---|
| `response.transcription_part.added` / `.done` | `item_id`、`output_index`、`transcription_index`、`part{type:"transcription_text", text, chunks[]}` |
| `response.transcription_text.delta` | `item_id`、`output_index`、`transcription_index`、`start_time`、`end_time`（毫秒）、`delta` |
| `response.transcription_text.done` | 同上，`text`、`chunks[]{start_time, end_time, text}` |

**错误事件**

| 事件 | 关键字段 |
|---|---|
| `error` | `code`、`message`、`param`（导致错误的参数名）、`sequence_number`、`type: "error"` |

**最小流式消费代码（Python，OpenAI SDK）**

```python
stream = client.responses.create(
    model="doubao-seed-2-1-pro-260628",
    input="常见的十字花科植物有哪些？",
    stream=True,
    extra_body={"thinking": {"type": "enabled"}},
)
for ev in stream:
    if ev.type == "response.reasoning_summary_text.delta":
        print(ev.delta, end="")                      # 思考摘要
    elif ev.type == "response.output_text.delta":
        print(ev.delta, end="")                      # 回答
    elif ev.type == "response.function_call_arguments.done":
        print("\nfunction args:", ev.arguments)
    elif ev.type == "response.completed":
        print("\nusage:", ev.response.usage)
    elif ev.type == "error":
        print("\nerror:", ev.code, ev.message)
```

curl 流式：在 body 加 `"stream": true` 即可，`-N` 关闭缓冲。

---

## 9. 我想…（按场景）

### 9.1 多轮对话：`previous_response_id` / `store` / `expire_at` / 删除截断 / `instructions`

工作原理（文本生成页）：每条信息是一个 item；`response_id` 代表「本轮输入 item + 回答 item」；下一轮的输入 = `previous_response_id` 所指的 item 链 + 本轮新 item，以链表形式串联。

```python
r1 = client.responses.create(model=M, input=[{"role": "user", "content": "Hi，帮我讲个笑话。"}])
r2 = client.responses.create(model=M, previous_response_id=r1.id,
                             input=[{"role": "user", "content": "这个笑话的笑点在哪？"}])
# 分叉：从 r1 再开一支
r2b = client.responses.create(model=M, previous_response_id=r1.id,
                              input=[{"role": "user", "content": "换一个更冷的。"}])
# 窗口截断：删掉中间某轮，后续引用链不再包含它
client.responses.delete(r2.id)
r3 = client.responses.create(model=M, previous_response_id=r2b.id, input="你刚讲了几个笑话？")
```

**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：上面这条链路的核心（`store: true` → `previous_response_id` 续轮 → `DELETE`）在 `/api/plan/v3` 全部走通：第一轮 `"记住数字 42"`，第二轮带 `previous_response_id` 问 `"我刚说的数字是？只答数字"` → `"42"`；`DELETE` 返回 `deleted: true`。**注意 Plan 入口不传 `store` 时回显 `store: false`**——上面示例代码没写 `store=True` 的话在 Plan 入口第二轮会因 r1 未存储而失败（未实测失败形态），务必显式传。分叉与删除后续轮未测。

要点（文档原文，未实测，除已标注项）：
- 文档：默认 `store: true`；存 `input` + `output`，**不存思维链**；当前不收费，数据加密存储。**实测 Plan 入口默认为 `false`**（3.1）。
- 存储时长默认 3 天，`expire_at` 最长 7 天。
- `store: true` 时输入受「模型上下文长度」与「最多 1000 个 item」双重约束，达上限无法继续对话，只能删 Response 清理；`store: false` 时仅受模型长度约束。
- 连续请求之间建议约 100 ms 间隔。
- `instructions` 只作用于本轮，用于在某一轮临时追加系统提示；配置后本轮不能用缓存。

```python
r3 = client.responses.create(
    model=M, previous_response_id=r1.id,
    instructions="增加一个要求：用小学生能听懂的方式解释。",
    input=[{"role": "user", "content": "请解释一下余弦相似度原理"}],
)
```

### 9.2 深度思考：`thinking` / `reasoning.effort` / 摘要 / `encrypted_content`

- 开关：`thinking.type` = `enabled`（默认）/ `disabled` / `auto`（仅 `doubao-seed-1-6-250615`）。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`/api/plan/v3/responses` + `doubao-seed-2.0-lite` 不传 `thinking` 时默认开（`output[0]` 为 `reasoning` item，`reasoning_tokens: 59`）；传 `thinking: {"type":"disabled"}` 后 `output[]` 只剩 `message`、`reasoning_tokens: 0`，响应回显 `"thinking":{"type":"disabled"}`。`glm-5.3` 在 Chat 入口 `disabled` 报 400（见 `chat.md` §4.1），Responses 入口未单独测。支持列表见深度思考页：doubao-seed-evolving、2.1 pro / turbo、2.0 lite / mini / pro / code-preview、1.8、1.6 系列、glm-5-2-260617、glm-4-7-251222、deepseek-v4 系列等，均默认 `enabled`。
- 思考长度：`reasoning.effort` 七档 `none` / `minimal` / `low` / `medium` / `high` / `xhigh` / `max`，所有支持模型都接受全部取值，但会按模型映射：

| 模型 | 默认 | 映射规则 |
|---|---|---|
| doubao-seed-evolving、doubao-seed-2-1-pro-260628、doubao-seed-2-1-turbo-260628 | `high` | `minimal` 关思考；`none`→`minimal`；`xhigh` / `max`→`high` |
| doubao-seed-2-0-lite/mini-260428、2-0-pro/lite/mini-260215、2-0-code-preview-260215、1-8-251228、1-6-251015、seed-character-260628 | `medium` | 同上 |
| glm-5-2-260617 | `high` | `none` / `minimal` 关思考；`low` / `medium`→`high`；`xhigh`→`max` |
| deepseek-v4-pro-ga-260813、deepseek-v4-flash-ga-260731 | `high` | `none` / `minimal` 关思考；`medium`→`low`；`xhigh`→`high` |
| deepseek-v4-pro-260425、deepseek-v4-flash-260425 | `high` | `minimal` 关思考；`none`→`minimal`；`low` / `medium`→`high`；`xhigh`→`max` |

- `thinking.type = enabled` 时可配 `reasoning.effort`（`minimal` 即关思考直接回答）；`thinking.type = disabled` 时 `reasoning.effort` 只能是 `minimal`，其他值报错（文档原文，未实测）。
- 思考摘要：doubao-seed-evolving / 2-1-pro / 2-1-turbo / 2-0-lite-260428 默认开启 thinking summary，返回摘要（`summary[]` / `response.reasoning_summary_text.delta`）而非原文；可能有较高包间延迟，需调大 timeout。`reasoning.effort` 只作用于原始思考；`reasoning_tokens` 按原始思考计费。
- 思考原文（加密）：请求加 `"include": ["reasoning.encrypted_content"]`，`reasoning` item 返回 `encrypted_content`；`doubao-seed-2-0-lite-260428` 及后续。
- 工具调用场景回传思考内容：优先 `previous_response_id`（自动）；否则把收到的 `reasoning` item（含 `encrypted_content`）原样放回 `input`，篡改后无法还原。Agent 场景不用 `previous_response_id` 时**必须**回传。
- 多轮工作原理：普通多轮下上一轮思维链不拼进上下文；工具调用场景（seed-1.8 及后续）服务端按需保留历史思维链，未输入模型的思维链不计费。
- 深度思考非流式易超时，推荐 `stream: true`；非流式需求可先流式收全再输出。

```bash
curl https://ark.cn-beijing.volces.com/api/v3/responses \
  -H "Authorization: Bearer $ARK_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"doubao-seed-2-1-pro-260628","input":"推理模型与非推理模型区别。",
       "thinking":{"type":"enabled"},"reasoning":{"effort":"low"},
       "include":["reasoning.encrypted_content"],"stream":true}'
```

### 9.3 多模态输入：图片 / 视频 / 文件 / 音频

三种传入方式：Files API `file_id`（推荐大文件 / 复用）、URL、base64。字段见 3.3。

```bash
# 1) 上传（视频可带抽帧配置）
curl https://ark.cn-beijing.volces.com/api/v3/files \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -F "purpose=user_data" -F "file=@/path/demo.mp4" -F "preprocess_configs[video][fps]=0.3"
# 2) 引用
curl https://ark.cn-beijing.volces.com/api/v3/responses \
  -H "Authorization: Bearer $ARK_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"doubao-seed-2-1-pro-260628","input":[{"role":"user","content":[
        {"type":"input_video","file_id":"file-20251018****"},
        {"type":"input_text","text":"描述视频中人物的一系列动作，JSON 输出 start_time/end_time/event/danger"}]}]}'
```

```python
f = client.files.create(file=open("demo.png", "rb"), purpose="user_data")
while f.status == "processing":
    time.sleep(2); f = client.files.retrieve(f.id)
resp = client.responses.create(
    model="doubao-seed-2-1-pro-260628",
    input=[{"role": "user", "content": [
        {"type": "input_image", "file_id": f.id},                       # 或 "image_url": "https://..." / data URL
        # {"type": "input_image", "image_url": "https://...", "detail": "high"},
        # {"type": "input_file", "file_url": "https://.../a.pdf"},
        # {"type": "input_file", "file_data": "<base64>", "filename": "a.pdf"},
        {"type": "input_text", "text": "图片里有什么？"},
    ]}],
)
```

注意：`input_image` 用 `image_url` 传 base64 时格式 `data:image/{格式};base64,{编码}`；`detail` 可选 `auto` / `low` / `high` / `xhigh`（输入项列表页只列 `low` / `high` / `xhigh` ⚠ 文档自相矛盾）；`fps` 对 `file_id` 无效；PDF 分页转图。

### 9.4 结构化输出 `text.format`（beta）

```python
# json_object：只保证合法 JSON，结构靠提示词
resp = client.responses.create(model="doubao-seed-1-6-251015",
    input=[{"role": "system", "content": "…返回 JSON，包含 explanation 和 answer 字段"},
           {"role": "user", "content": "根号三的近似值是多少"}],
    text={"format": {"type": "json_object"}},
    extra_body={"thinking": {"type": "disabled"}})

# json_schema（推荐）：可定义结构，strict 严格校验
resp = client.responses.create(model="doubao-seed-1-6-251015",
    input=[{"role": "user", "content": [{"type": "input_text", "text": "return in json format how can I solve 8x + 7 = -23"}]}],
    text={"format": {"type": "json_schema", "name": "math_reasoning", "strict": True,
          "schema": {"type": "object",
                     "properties": {"steps": {"type": "array", "items": {"type": "object",
                                    "properties": {"explanation": {"type": "string"}, "output": {"type": "string"}},
                                    "required": ["explanation", "output"], "additionalProperties": False}},
                                    "final_answer": {"type": "string"}},
                     "required": ["steps", "final_answer"], "additionalProperties": False}}},
    extra_body={"thinking": {"type": "disabled"}})
```

OpenAI SDK 还可用 `client.responses.parse(..., text_format=PydanticModel)` 直接得到 `response.output_parsed`（文档示例）。限制：TPM 保障包不支持结构化输出；seed-1.8 之前版本走模型单元部署时不支持；续写模式不支持。

### 9.5 上下文编辑 / 自动裁剪（beta）

支持模型：doubao-seed-evolving、2-1-pro/turbo-260628、2-0-lite/mini-260428、2-0-pro/lite/mini/code-preview-260215、1-8-251228、seed-character-260628。字段见 3.6。

```json
"context_management": {
  "edits": [
    {"type": "clear_thinking", "keep": {"type": "thinking_turns", "value": 3}},
    {"type": "clear_tool_uses",
     "trigger": {"type": "tool_uses", "value": 5},
     "keep": {"type": "tool_uses", "value": 3},
     "exclude_tools": ["web_search"]}
  ]
}
```

- `clear_thinking` 必须排在 `clear_tool_uses` 之前；先清思维链再清工具记录。
- 保留轮次同时覆盖工具 / 非工具场景，只按轮数判断。
- 与缓存协同工作（文档只说「智能缓存」，具体交互 ⚠ 文档未说明）。
- 除 `clear_tool_uses` 自动裁剪外，另一种手动「裁剪」是 9.1 的删除 Response。

### 9.6 Function Calling 多轮回传

```python
tools = [{"type": "function", "name": "get_weather",
          "description": "根据城市名称查询该城市当日天气（含温度、天气状况）",
          "parameters": {"type": "object",
                         "properties": {"location": {"type": "string", "description": "城市名称"}},
                         "required": ["location"]}}]

r1 = client.responses.create(model=M, store=True, tools=tools,
                             input=[{"type": "message", "role": "user", "content": "查询北京今天的天气"}])
fc = next(i for i in r1.output if i.type == "function_call")   # fc.call_id / fc.name / fc.arguments (JSON str)
result = {"city": "北京", "temperature": "18~28℃", "condition": "晴转多云"}

# 方式 A（推荐）：previous_response_id 自动带上历史（含思维链）
r2 = client.responses.create(model=M, previous_response_id=r1.id, tools=tools,
                             input=[{"type": "function_call_output", "call_id": fc.call_id,
                                     "output": json.dumps(result, ensure_ascii=False)}])

# 方式 B：store=False 手动拼历史 —— 需回传 reasoning item（含 encrypted_content）+ function_call + function_call_output
history = [{"type": "message", "role": "user", "content": "查询北京今天的天气"}]
history += [i.model_dump(exclude_none=True) for i in r1.output]   # reasoning / function_call 原样回传
history.append({"type": "function_call_output", "call_id": fc.call_id, "output": json.dumps(result)})
r2 = client.responses.create(model=M, store=False, tools=tools, input=history,
                             extra_body={"include": ["reasoning.encrypted_content"]})
```

第一轮响应示例（工具调用页）：`output[0] = {"type":"function_call","call_id":"call_abc…","name":"get_weather","arguments":"{\"location\":\"北京\"}","id":"fc_…","status":"completed"}`。

注意：迁移文档 Java 示例在第二轮也传了 `tools`，Python 示例未传；是否必须 ⚠ 文档未说明，稳妥起见每轮都传。`tool_choice` 仅 Seed 1.8 / 2.0 系列支持。

### 9.7 上下文缓存 `caching`

```python
r0 = client.responses.create(model=M, input=[{"role": "system", "content": "<长系统提示，≥256 tokens>"}],
                             extra_body={"caching": {"type": "enabled"}, "thinking": {"type": "disabled"}})
r1 = client.responses.create(model=M, previous_response_id=r0.id, input=[{"role": "user", "content": "我是方方"}],
                             extra_body={"caching": {"type": "enabled"}, "thinking": {"type": "disabled"}})
print(r1.usage.input_tokens_details.cached_tokens)
```

- 只写缓存不出结果：`caching: {"type": "enabled", "prefix": true}`。
- 前缀缓存要求输入 ≥ 256 tokens（续写模式页原文）。
- `expire_at` 同时约束缓存；缓存存储计费按小时向上取整。
- 与 `instructions`、非 function 的 `tools` 互斥。详细规则见上下文缓存专页（不在本文范围）。

### 9.8 续写模式 `partial`

`input` 最后一条为 `{"role": "assistant", "content": "def bubble_sort(arr):", "partial": true}`，模型在其后续写。支持模型：doubao-seed-evolving、2.1 pro/turbo、2.0 lite/mini/pro/code-preview、1.8、seed-character-260628、seed-code-preview-251028、1-6-251015。限制：不支持结构化输出；建议不与内置工具同用；assistant `content` 可为空以实现多轮连续回答；支持前缀 / Session 缓存。

---

## 10. 限制、QPS 与不支持的场景

| 项 | 值 |
|---|---|
| 创建 Response QPS（账号维度） | 无限制（文档原文） |
| 查询 / 列输入项 / 删除 QPS | 各 20；提升需提工单 |
| store 上限 | 1000 个 item / 链；默认 3 天，最长 7 天 |
| 不支持 | TPM 保障包；精调后模型在线推理；智能模型路由；模型版本切换；`doubao-1-5-pro-32k-character-250715` |
| 内置工具 | 不推荐 `doubao-seed-1-6-flash`（迁移文档原文） |
| 结构化输出 | TPM 保障包下不可用；seed-1.8 前模型单元部署不可用 |
| 多轮请求间隔 | 建议 ≥ 100 ms |

---

## 11. 来源页面

| 标题 | URL | 文档更新时间 |
|---|---|---|
| 创建 Response（主参考） | https://www.volcengine.com/docs/82379/1569618 | 2026-08-25 |
| 查询 Response 详情 | https://www.volcengine.com/docs/82379/1783709 | 2026-07-20 |
| 查询 Response 输入项列表 | https://www.volcengine.com/docs/82379/1783719 | 2026-07-20 |
| 删除 Response | https://www.volcengine.com/docs/82379/1584286 | 2026-07-20 |
| Response 生命周期（流式事件） | https://www.volcengine.com/docs/82379/2644693 | 2026-08-19 |
| Output Item 与文本回答（流式事件） | https://www.volcengine.com/docs/82379/2644694 | 2026-08-15 |
| 工具调用事件（流式事件） | https://www.volcengine.com/docs/82379/2644695 | 2026-08-15 |
| 语音转写与错误事件（流式事件） | https://www.volcengine.com/docs/82379/2644696 | 2026-08-15 |
| 迁移至 Responses API | https://www.volcengine.com/docs/82379/1585128 | 2026-08-24 |
| 文本生成（Responses API） | https://www.volcengine.com/docs/82379/1958520 | 2026-08-24 |
| 深度思考（Responses API） | https://www.volcengine.com/docs/82379/1956279 | 2026-08-19 |
| 多模态理解（Responses API） | https://www.volcengine.com/docs/82379/1958521 | 2026-08-05 |
| 工具调用（Responses API） | https://www.volcengine.com/docs/82379/1958524 | 2026-08-04 |
| 结构化输出(beta)（Responses API） | https://www.volcengine.com/docs/82379/1958523 | 2026-06-27 |
| 上下文编辑 | https://www.volcengine.com/docs/82379/2123215 | 2026-06-23 |
| Agent Plan 控制台实读（`/api/plan/v3` 已支持 Responses API） | https://console.volcengine.com/ark/region:cn-beijing/subscription/agent-plan | 2026-09-03 实读 |
| 真实 API 验证记录（Agent Plan Medium，`/api/plan/v3/responses`） | `volcengine-ark-workspace/verification-findings.md` + `verification-log.jsonl`（同批产出） | 2026-09-04 |
