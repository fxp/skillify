# volcengine-ark · 真实 API 验证结论（2026-09-04）

测试账号：Agent Plan 个人版 **Medium** 套餐（生效中），使用 **Agent Plan 专属 Key**。**没有**标准方舟 API Key、**未订阅** Coding Plan，因此 `/api/v3` 与 `/api/coding/v3` 只验证了"拿 Agent Plan Key 打过去会怎样"，其余标准 / Coding Plan 结论仍是文档转录。原始请求 / 响应见同目录 `verification-log.jsonl`（约 45 条），探测脚本 `probe.py`。总消耗：文本类约 2,000 token 级别（不足 20 AFP）+ 一张 2k 图（99 AFP）。

写回 reference 时统一用这个格式：**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：…，并附下面的原始报错 / 响应片段。

## A. Key 与入口隔离
| # | 做了什么 | 结果 |
|---|---|---|
| A1 | Agent Plan Key 打 `https://ark.cn-beijing.volces.com/api/v3/chat/completions` | **401** `{"error":{"code":"AuthenticationError","message":"The API key or AK/SK in the request is missing or invalid. ...","param":"","type":"Unauthorized"}}` |
| A2 | Agent Plan Key 打 `/api/coding/v3/chat/completions` | **401** 同上 |
| A3 | Agent Plan Key 打 `/api/plan/v3/chat/completions`，model `doubao-seed-2.0-lite` | **200**，响应 `"model":"doubao-seed-2-0-lite-260215"` |
结论：Agent Plan 专属 Key 只在 `/api/plan*` 有效，文档"其他 Base URL 无法在 Agent Plan 中使用"属实；错误码是 401 AuthenticationError 而不是"套餐不支持"。

## B. `model` 字段在 Plan 入口的真实行为（最重要）
| # | model 值 | 结果 |
|---|---|---|
| B1 | `doubao-seed-2.0-lite` | 200，实际服务模型 **`doubao-seed-2-0-lite-260215`**（不是模型列表页最新的 `260428`） |
| B2 | `doubao-seed-2-0-lite-260428`（带日期 Model ID） | **200，但响应 `model` 仍是 `doubao-seed-2-0-lite-260215`** —— Plan 入口接受 Model ID 却**静默忽略版本号**，按 Name 路由 |
| B3 | `auto` | **404** `{"error":{"code":"UnsupportedModel","message":"The requested model does not support the agent plan feature. Please refer to the documentation at https://www.volcengine.com/docs/82379/2366394 to select a compatible model. ..."}}` —— 控制台"Model Name: auto"是错的，Coding Plan 文档"不支持配置为 Auto"是对的 |
| B4 | `ark-code-latest` | 200，响应 `"model":"auto"`（控制台当前选的是 Auto 路由；`reasoning_tokens: 0`） |
| B5 | `doubao-seed-2.1-pro`（套餐外模型） | 404 UnsupportedModel（同 B3 文案） |
| B6 | `doubao-seed-1-8-251228`（老 Model ID） | 404 UnsupportedModel |
| B7 | `kimi-k3`（Medium 档） | 200，`"model":"kimi-k3"` |
| B8 | `doubao-seed-2.0-mini` | 200，`doubao-seed-2-0-mini-260215` |
| B9 | `glm-latest` | 200，`"model":"glm-5.3"` —— `*-latest` 别名有效 |
| B10 | 视频 `doubao-seedance-2.0-mini` on Medium | **404 UnsupportedModel**（同 B3 文案）—— Medium 不支持视频属实，错误不是"额度/档位"专用码 |
| B11 | Anthropic 入口 `model: "claude-sonnet-4-5"` | **200，被静默路由到 `doubao-seed-2-1-turbo-260628`**（抵扣系数 2.5）。Claude Code 忘设 `ANTHROPIC_MODEL` 时不会报错，而是悄悄用 2.1-turbo 烧 AFP |
| B12 | Anthropic 入口 `model: "doubao-seed-2-0-lite-260428"` | 200，服务模型 `doubao-seed-2-0-lite-260215`（同 B2 静默换版本） |

## C. 参数行为
| # | 做了什么 | 结果 |
|---|---|---|
| C1 | `messages[0].role = "developer"` | **400** `{"error":{"code":"InvalidParameter","message":"The parameter `messages.role` specified in the request are not valid: invalid value: `developer`, supported values are: `system`, `assistant`, `user`, `tool`. ...","param":"","type":"BadRequest"}}` |
| C2 | `glm-5.3` + `thinking: {"type":"disabled"}` | **400** `{"error":{"code":"InvalidParameter","message":"thinking.type `disabled` is not supported by this model ...","type":"BadRequest"}}` |
| C3 | `glm-5.3` + `reasoning_effort: "low"` | 200，`reasoning_tokens: 0`，无 `reasoning_content` —— 事实上相当于关掉了思考 |
| C4 | `glm-5.3` + `reasoning_effort: "none"` | **400** `reasoning_effort `none` is not supported by this model` |
| C5 | `doubao-seed-2.0-lite` 默认 | 思考默认**开**（`reasoning_content` 存在，`reasoning_tokens: 109`）；`thinking.disabled` 生效（reasoning_tokens 0） |
| C6 | `doubao-seed-2.0-lite` `max_tokens: 64` 且思考开 | `completion_tokens: 110`（reasoning 109 + 回答 1）—— **`max_tokens` 不限制豆包的思维链** |
| C7 | `kimi-k3` `max_tokens: 64` | `finish_reason: "length"`，`content: ""`，reasoning 61 —— **kimi-k3 的 `max_tokens` 把思维链算进去**，回答被截空；改 `max_completion_tokens: 400`（去掉 max_tokens）后正常 `content: "2"` |
| C8 | `service_tier: "fast"` | **400** `{"error":{"code":"InvalidParameter","message":"The parameter `service_tier` specified in the request are not valid: fast service tier does not support coding plan. ...","param":"service_tier"}}`（Agent Plan 入口报的却是 coding plan 文案） |
| C9 | `stream: true` + `stream_options.include_usage` | 标准 SSE，`delta.reasoning_content` 逐 token 下发，chunk 里 `usage: null` 直到末尾 |
| C10 | `tool_choice: {"type":"function","function":{"name":"get_weather"}}` 对无关问题"讲个笑话" | 200，`finish_reason: "tool_calls"`，模型编造参数 `{"city":"济南"}` 强制调用 —— **强制 tool_choice 在方舟生效**（与智谱不同） |
| C11 | `response_format: json_schema` | 200，`content: "{\"answer\": 2}"` 合法 JSON |
| C12 | 请求头 `X-Prompt-Cache-Id: skill-probe-1` | 200，不报错（`cached_tokens: 0`，单次无法证明缓存命中） |

## D. 各 endpoint 在 `/api/plan/v3` 是否存在
| endpoint | 结果 |
|---|---|
| `POST /chat/completions` | 200 |
| `POST /responses` | 200；`store: true` → 响应含 `expire_at`；`GET /responses/{id}` 200；`previous_response_id` 续轮正确回忆；`DELETE /responses/{id}` → `{"id":...,"object":"response","deleted":true}`；`model: ark-code-latest` 也可用（响应 `model: "auto"`） |
| `POST /embeddings`（OpenAI 形态，`input` 字符串） | **200**，`data[0].embedding` 数组，默认 **2048** 维，`dimensions: 1024` 生效；`usage: {"prompt_tokens":20,"total_tokens":20}` —— 文档"向量化不支持 OpenAI API"在 Plan 入口**不成立** |
| `POST /embeddings`（`input` 为 `[{"type":"text"...}]` 多模态数组） | **400** `The parameter `input[0]` ... expected a string, but got `map[text:a cat type:text]`` —— OpenAI 形态只收字符串，图片必须走 multimodal |
| `POST /embeddings/multimodal` | 200，响应 **`data.embedding`（对象，不是数组）**，2048 维，`usage.prompt_tokens_details: {"text_tokens":20,"image_tokens":0}`，`model: doubao-embedding-vision-251215` |
| `POST /images/generations` `size: "1K"` | **400** `size must be one of 'WIDTHxHEIGHT', '2k', '3k', or '4k'` —— 5.0-lite 不接受 `1K` |
| `POST /images/generations` `size: "2k"`, `watermark: false`, `response_format: url` | 200，`data[0].url` 为 TOS 签名链接（`X-Tos-Expires=86400`，24h），`size: "2048x2048"`，`usage: {"generated_images":1,"output_tokens":16384,"total_tokens":16384}` |
| `POST /contents/generations/tasks`（Medium） | 404 UnsupportedModel（见 B10） |
| `GET /models` | **404**（空 body） |
| `POST /tokenization` | **404** |
| `POST /context/create` | **404** —— 上下文缓存 Context API 在 Plan 入口不存在 |
| `GET /files` | **404** —— Files API 在 Plan 入口不存在 |

## E. Anthropic 协议入口 `https://ark.cn-beijing.volces.com/api/plan/v1/messages`
| # | 做了什么 | 结果 |
|---|---|---|
| E1 | `Authorization: Bearer <PlanKey>` + `anthropic-version: 2023-06-01` | 200，标准 Anthropic Message 对象，思维链以 `{"type":"thinking","thinking":"..."}` block 返回，`usage.cache_read_input_tokens` |
| E2 | `x-api-key: <PlanKey>` | 200 —— **两种头都接受** |
| E3 | `thinking: {"type":"disabled"}` | 200，只剩 `text` block |
| E4 | `stream: true` | 标准 Anthropic SSE：`event: message_start` / `content_block_start` / `content_block_delta`(`text_delta`) … |
| E5 | model 见 B11 / B12 | Claude 模型名被静默映射到 2.1-turbo；带日期 Model ID 被静默换版本 |

## F. 文档本身写错 / 前后矛盾，已被实测裁决
1. 控制台列出 `Model Name: auto` → 实测 404 UnsupportedModel；只能通过 `ark-code-latest` + 控制台选 Auto。
2. 文档「兼容 OpenAI SDK」页称向量化不支持 OpenAI API → Plan 入口 `POST /embeddings` 实测可用（仅字符串输入）。
3. 文档多模态向量化默认维度写法不一（2048 vs 1024 vs 3072）→ 实测两条路默认都是 2048，`dimensions: 1024` 生效。
4. Agent Plan 套餐概览表 Medium 档 `doubao-seedance-1.5-pro` 打 √ 但正文说 Small/Medium 不支持视频 → 实测 `doubao-seedance-2.0-mini` 404；1.5-pro 未测（即将下线）。
5. `service_tier: fast` 的报错文案在 Agent Plan 入口说的是 "coding plan"。
6. 文档从未提及：Plan 入口接受带日期的 Model ID 但静默改版本；Anthropic 入口把 `claude-*` 模型名静默路由到 `doubao-seed-2.1-turbo`。

## G. 未验证（无标准 Key / 未订阅 Coding Plan）
- `/api/v3` 全部行为（Model ID 精确匹配、小写 Name 是否被接受、`/context`、`/files`、`/tokenization`、`/batch`、Bot、`/api/v3/compatible/v1/messages` Anthropic 兼容入口）。
- `/api/coding/v3` 套餐内行为；方舟 API Key 打 `/api/plan/v3` 会返回什么（推测 401，同 A1）。
- 语音（openspeech 域名）、管控面 Action（需 AK/SK）、Harness。
