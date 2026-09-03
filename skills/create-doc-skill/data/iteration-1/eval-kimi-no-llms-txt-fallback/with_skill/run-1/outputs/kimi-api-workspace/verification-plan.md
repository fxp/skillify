# kimi-api skill · 真实 API 验证计划

状态：**全部未验证**（2026-09-03 无 API Key）。本计划留给拿到 key 的人按优先级执行，每条验证完把结论（日期 + 做了什么 + 原始响应/报错片段）写回对应 reference，并在 SKILL.md "验证状态" 一节更新。

执行约定：
- key 只走环境变量 `MOONSHOT_API_KEY`，不写进任何文件；跑完 `grep -rn "sk-" <skill-dir>` 确认无泄漏。
- 先充 ¥50 到 Tier1（Tier0 并发 1 / RPM 3，跑并行验证会一直 429）。整套计划预估花费 < ¥5（主要是 K3 几十次短对话和一个 10 行的 Batch）。
- 每条记录到 `verification-log.md`：日期、endpoint、请求要点、结果、花费。
- 测试产生的文件（`/v1/files`）和 Batch 任务用完立刻删除 / 取消。

## P0 — 全盘皆错的三件事（先用最便宜的只读接口打通）

| # | 要验证的结论 | endpoint | 方法 | 预期 / 判定 | 成本 |
|---|---|---|---|---|---|
| 0.1 | `Authorization: Bearer <key>` 有效；裸 key（无 Bearer）是否 401 | `GET /v1/models` | 两种 header 各发一次 | 前者 200 且 `data[].id` 含 `kimi-k3`；后者应 401 `invalid_authentication_error` | 免费 |
| 0.2 | 4 个在线模型名与 `GET /v1/models` 一致；`moonshot-v1-8k`、`kimi-k2.5`、`kimi-latest` 真返回 404 | `GET /v1/models` + `POST /v1/chat/completions` | 用下线模型名各发一次 | 404 `resource_not_found_error`，记录原文 message | ≈0 |
| 0.3 | 余额接口可用，用于后续算花费 | `GET /v1/users/me/balance` | 一次 | 记录响应字段名（文档 `data.available_balance` 等，核对） | 免费 |

## P1 — SKILL.md 通用规则里的每一条（每条一次最小调用）

| # | 规则 | 怎么测 | 判定 |
|---|---|---|---|
| 1.1 | 采样参数固定，传其他值报错 | `kimi-k3` 传 `temperature: 0.2`；再传 `temperature: 1.0`；再传 `top_p: 0.5` | 前者/后者是否都报 `invalid_request_error`？**关键：传等于默认值的 1.0 是否也报错**（决定 skill 建议"不传"还是"可传默认值"） |
| 1.2 | K3 不接受 `thinking`；K2.6 不接受 `reasoning_effort` | 交叉各传一次 | 报错原文，还是**静默忽略**（静默最危险，要升级到通用规则） |
| 1.3 | K2.6 `thinking: disabled` 生效 | 看响应是否无 `reasoning_content`、usage 变化 | 有 `reasoning_content` 说明未生效 |
| 1.4 | K2.7-code 传 `thinking: {"type":"disabled"}` 报错 | 一次 | 记录 message |
| 1.5 | Preserved Thinking：多轮不回传 `reasoning_content` 会怎样 | K3 两轮对话，第二轮 assistant 消息去掉 `reasoning_content` | 报错？静默降质？（文档只说"必须"，没说后果）→ 结论决定通用规则 3 的措辞 |
| 1.6 | `tool_choice: "required"` 在 K2.6 报错、在 K3 生效 | 各一次，带一个天气工具 | K2.6 报错原文；K3 响应 `finish_reason == "tool_calls"` |
| 1.7 | OpenAI 式 `tool_choice: {"type":"function","function":{"name":...}}` 在 K3 上是报错还是被当 auto | 一次 | ⚠ 文档未说明，静默降级要写进通用规则 4 |
| 1.8 | `partial: true` 在 assistant 消息上生效；作为顶层参数是报错还是忽略 | 各一次 | 输出是否紧接 prefix |
| 1.9 | `$web_search` 声明成功；把 `arguments` 原样回传后模型能给出带搜索结果的回答；普通 function 名带 `$` 是否报错 | 3 次 | 记录 `tool_calls` 结构和 usage（搜索是否额外计费，对照 pricing/tools） |
| 1.10 | 流式 `stream_options.include_usage`：不传时最后 chunk 是否也有 usage？ | 两次 | 决定"必须传"还是"建议传" |
| 1.11 | 错误结构 `{"error":{"type","message"}}` 无数字 code | 用 1.1 的报错核对 | 若带 `code` 字段要补进 errors-and-limits.md |
| 1.12 | 自动缓存：连续两次 >256 token 同前缀请求，第二次 usage 是否有 `cached_tokens` 类字段，字段名是什么 | 两次 | ⚠ 文档字段名待核对 |

## P2 — 文件与 Batch（有副作用，测完清理）

| # | 结论 | 怎么测 | 判定 / 清理 |
|---|---|---|---|
| 2.1 | `purpose="file-extract"` 上传 1 页 PDF → `GET /v1/files/{id}/content` 返回文本；响应是纯文本还是 JSON（SDK `.text` 能否直接用） | 上传 → 取内容 → 删除 | 记录 content-type 和结构 |
| 2.2 | `purpose` 非法值报错原文；`purpose="assistants"` 是否被拒 | 一次 | 应 400 `Invalid purpose: ...` |
| 2.3 | `purpose="image"` 上传 png，在 messages 中以 file id 引用的**精确 JSON 结构**（⚠ 文档形态需核对） | 一次 | 记录可用的 content part 格式 |
| 2.4 | Batch：10 行 JSONL，`model=kimi-k2.6`，`completion_window="24h"` 全流程；再提交一份 `model=kimi-k3` 的 | 创建 → 轮询 → 取 `output_file_id` → 取消/删除 | K3 那份在创建时报错还是逐行失败（决定写在哪一层）；记录状态机实际取值和 `request_counts` 字段 |
| 2.5 | Batch body 里带 `temperature` 是创建时拒绝还是行级 error | 一份 3 行 | 记录 |

## P3 — 其他两种协议与工具接口

| # | 结论 | 怎么测 |
|---|---|---|
| 3.1 | `POST /v1/responses` 最小请求；图片传公网 URL 是否真报错 | 两次 |
| 3.2 | `POST /anthropic/v1/messages` 用 anthropic SDK（base_url `https://api.moonshot.cn/anthropic`）跑通；`max_tokens` 缺省是否报错；`thinking` 块/`reasoning_effort` 在此协议下怎么传 | 三次 |
| 3.3 | `POST /v1/tokenizers/estimate-token-count` 响应结构 `data.total_tokens` | 一次 |
| 3.4 | `POST /v1/signatures/verify` 完整流程（⚠ 需先弄清签名从哪来） | 视文档 |

## P4 — 各 reference 里的 ⚠ 清单

（从 6 个 reference 文件的 ⚠ 标记自动汇总，行号对应 2026-09-03 版文件；每条 = 文件 · 行 · 原文。测法：对应 endpoint 各发一次最小请求，记录响应/报错原文写回。所有报错原文均为文档引用，非实测。）

| 文件 | 行 | ⚠ 原文（截断） |
|---|---|---|
| models-and-thinking.md | 41 | \| `thinking.type` \| 不支持，不应传（传入是否报错 ⚠ 文档未说明） \| 仅 `"enabled"`；传 `"disabled"` 报错 \| `"enabled"`（默认）/ `"disabled"` \| |
| models-and-thinking.md | 44 | \| `tool_choice` \| `auto` / `none` / `required` / 指定函数对象 \| `auto` / `none`；`required` 报错；指定函数对象 ⚠ 文档自相矛盾（见 §11） \| 同 K2.7 \| |
| models-and-thinking.md | 50 | \| 访问条件 \| 累计充值 ≥ ¥10 后解锁；15 元新人代金券不可用 \| ⚠ 文档未说明 \| ⚠ 文档未说明 \| |
| models-and-thinking.md | 51 | \| 输出速度 \| ⚠ 文档未说明 \| 普通版 ⚠ 未说明；高速版约 180 tok/s（短上下文可达 260） \| ⚠ 文档未说明 \| |
| models-and-thinking.md | 69 | \| 只有新人代金券、没充值 \| `kimi-k2.7-code` / `kimi-k2.6` \| 代金券不可用于 K3（K2.x 是否可用 ⚠ 文档未说明） \| |
| models-and-thinking.md | 80 | - **上线日期**：⚠ 文档未说明（changelog 无 K3 上线条目）。 |
| models-and-thinking.md | 87 | - **上线日期**：⚠ 文档未说明。 |
| models-and-thinking.md | 94 | - **上线日期**：⚠ 文档未说明。 |
| models-and-thinking.md | 151 | **注意**：仅 401 错误在 OpenAPI 中列出；能力字段的取值示例 ⚠ 文档未说明。 |
| models-and-thinking.md | 245 | （没有 `"medium"`、`"minimal"`、`"none"` 等 OpenAI 取值；传入是否报错 ⚠ 文档未说明。） |
| models-and-thinking.md | 296 | ⚠ 文档自相矛盾：K2.6 快速开始页参数表写"只能为 `{"type":"enabled"}` 或 `{"type":"disabled"}`"，未提 `keep`；模型参数参考、思考模型指南、OpenAPI 均列出 `keep: "all"`。以后三者为准。 |
| models-and-thinking.md | 345 | ⚠ 文档自相矛盾：模型参数参考写"显式设置时仅接受 `{"type":"enabled","keep":"all"}`"，而 OpenAPI 与思考模型指南写 `keep` 不传或 `null` 也合法（即 `{"type":"enabled"}` 应可通过）。最稳妥做法：**不传 `thinkin |
| models-and-thinking.md | 444 | **用途**：三款模型都把采样参数锁死；传入非固定值直接报错（400 `invalid_request_error` 一类，具体 `error.code` ⚠ 文档未说明）。 |
| models-and-thinking.md | 463 | \| `{"type":"function","function":{"name":...}}` \| 支持 \| ⚠ 文档自相矛盾：模型参数参考只说"不支持 `required`"；K2.6 / K2.7 快速开始页说"只能用 auto 和 none，取任何其他值将会报错"（K2.6 页限定为思考 |
| models-and-thinking.md | 483 | - 输出上限字段：⚠ 文档自相矛盾——OpenAPI 标注 `max_tokens` "已弃用，请使用 `max_completion_tokens`"（K3 默认 131072，最大 1048576）；而 K2.6 / K2.7 快速开始与思考模型指南全部使用 `max_tokens`（默认 32 |
| models-and-thinking.md | 506 | 材料中的定价总页只给出计费规则，**具体单价在 `/docs/pricing/chat-k3`、`/docs/pricing/chat-k27-code`、`/docs/pricing/chat-k26` 子页，本次输入材料未包含 → 单价 ⚠ 文档未说明**。可依据的规则： |
| models-and-thinking.md | 513 | - 2025-04-07 changelog 记录过一次"模型产品降价"（具体幅度 ⚠ 文档未说明）。 |
| models-and-thinking.md | 529 | - 限速按账户维度，不按模型区分（是否有按模型的额外限制 ⚠ 文档未说明）。 |
| models-and-thinking.md | 532 | - K3 页面提示"预备在 8 月更新充值等级与限速规则"，本表抓取于 2026-09-03，是否已是更新后版本 ⚠ 文档未说明。 |
| models-and-thinking.md | 533 | - 超限的 HTTP 状态码 / `error.code` ⚠ 文档未说明（本次材料未含错误码页）。 |
| models-and-thinking.md | 537 | - ⚠ 文档自相矛盾：K2.6 快速开始页 `thinking` 只列 enabled/disabled，其余三处含 `keep: "all"`（§8）。 |
| models-and-thinking.md | 538 | - ⚠ 文档自相矛盾：K2.7 显式传 `{"type":"enabled"}`（无 keep）是否合法，模型参数参考 vs OpenAPI（§9）。 |
| models-and-thinking.md | 539 | - ⚠ 文档自相矛盾：K2.x `tool_choice` 指定函数对象是否可用（§11）。 |
| models-and-thinking.md | 540 | - ⚠ 文档自相矛盾：`max_tokens` 已弃用 vs 全部示例仍用 `max_tokens`（§12）。 |
| models-and-thinking.md | 541 | - ⚠ 文档未说明：K3 传入 `thinking` 是否报错；`reasoning_effort` 传非法值是否报错；三款模型上线日期；K2.x 访问条件与代金券可用性；具体单价；限速错误码；充值 ¥10-49 区间的等级；8 月限速规则是否已更新。 |
| chat-completions.md | 36 | \| `max_tokens` \| integer \| 否 \| — \| OpenAPI 标记**已弃用**，改用 `max_completion_tokens`；但所有 guide 示例仍在用 `max_tokens`（⚠ 文档自相矛盾，两者目前应都可用，实测为准） \| |
| chat-completions.md | 44 | `temperature`、`top_p`、`n`：⚠ 文档未说明 —— OpenAPI 摘要里**没有**这三个字段；vision 页只说"各模型取值约束不同，建议不要手动设置"；streaming 页说当前模型 `n` 固定为 1，>1 返回 400 `invalid n: only 1 is  |
| chat-completions.md | 102 | - `logprobs` 返回位置：OpenAPI 描述写"响应 message 的 logprobs 字段"，但响应 schema 未定义该字段 —— ⚠ 文档未说明（OpenAI 在 `choices[].logprobs`），实测为准。 |
| chat-completions.md | 252 | - `usage` 出现位置 —— ⚠ 文档自相矛盾：API 页示例把 `usage` 放在 `finish_reason="stop"` 那个 chunk 的**顶层**（且未开 `include_usage`）；streaming guide 示例是 finish chunk 里的 `choic |
| chat-completions.md | 253 | - `cached_tokens`：OpenAPI 顶层 chunk `usage` 有，`ChoiceDelta.usage` 没有 —— ⚠ 文档未说明流式下该字段在哪一层可靠出现。 |
| chat-completions.md | 344 | - `strict` 默认值 —— ⚠ 文档自相矛盾：OpenAPI 写 `default: true`，guide 说"省略时 k2.6 更易输出 schema 外字段、建议显式设 true"。**始终显式写 `strict: true`** 就没有歧义。 |
| chat-completions.md | 416 | - 思考模式下续写必须带回 `reasoning_content`；不带会怎样 ⚠ 文档未说明（示例注释只写"思考模式需要 reasoning_content"）。 |
| chat-completions.md | 417 | - `partial` 放在非末尾消息上的行为 ⚠ 文档未说明（OpenAPI 只说"在最后一条 assistant 消息中设置为 true"）。与 `response_format` 的兼容性见 §4。 |
| chat-completions.md | 480 | - 命中门槛：**前一个请求的 prompt tokens > 256** 时，新请求才能命中前缀缓存；前一个请求 < 256 则不会被缓存（原文"被丢弃"）。恰好 256 ⚠ 文档未说明。 |
| chat-completions.md | 481 | - `usage.cached_tokens` 来自 OpenAPI 与 API 页示例；caching guide 正文完全没提该字段或任何 usage 字段（⚠ 文档未说明 cached_tokens 是否即"命中缓存的 prompt token 数"，按字段描述推断是）。 |
| chat-completions.md | 482 | - 缓存 TTL、上限、跨 key / 跨模型是否共享：⚠ 文档未说明（只说"生命周期由系统自动管理"）；`prompt_cache_key` 只出现在 OpenAPI，caching guide 说"无需添加额外参数"—— 不冲突（可选优化），但效果 ⚠ 文档未说明。 |
| chat-completions.md | 560 | - 上传 `purpose` 取值：材料里只出现 `"image"`（SVG 一节）与 `"video"`，完整枚举 ⚠ 文档未说明（在 files 文档）。 |
| chat-completions.md | 616 | - auto-reconnect 页摘要写"为流式请求实现断线重连，并结合 Partial Mode 从中断处继续生成"，但正文代码只有**非流式的 try/except 重试** —— ⚠ 文档未说明流式续写的官方实现；`stream_with_resume` 是按 §5 规则组合的推断写法。 |
| chat-completions.md | 633 | \| `temperature`, `top_p`, `n`, `frequency_penalty`, `presence_penalty`, `seed` \| — \| ⚠ 文档未说明：OpenAPI 未列出；`n` 仅支持 1 \| |
| chat-completions.md | 650 | 其它错误码（429 限流等）⚠ 文档未说明（本材料未含错误码总表）。 |
| tool-calling.md | 18 | 10. [⚠ 汇总](#10--汇总) |
| tool-calling.md | 27 | \| `tool_choice: {"type":"function","function":{"name":...}}` \| 文档支持该写法，但 **"思考开启时传入会返回 400 错误（`tool_choice 'specified' is incompatible with thinking |
| tool-calling.md | 75 | `function.arguments` 是 **JSON 字符串**，要 `json.loads`。`finish_reason` 枚举：`stop` / `length` / `tool_calls`；为 `tool_calls` 时 `content` 通常为空，偶尔是模型对"为什么调用"的解 |
| tool-calling.md | 168 | - 文档把 `role=tool` 消息的 `name` 字段写在示例里，OpenAPI 摘要中 tool 消息是否要求 `name` ⚠ 文档未说明；照示例带上最稳妥。 |
| tool-calling.md | 169 | - ⚠ 文档自相矛盾：guide/use-official-tools 的示例回传 assistant 消息时只保留 `role/content/tool_calls` 三个字段（丢掉 `reasoning_content`），而 guide/use-thinking-models 明确要求 K3  |
| tool-calling.md | 180 | - 思考模型工具循环建议 `max_tokens >= 16000`，避免 `reasoning_content` + `content` 截断。⚠ 文档自相矛盾：OpenAPI 把 `max_tokens` 标为"已弃用，请使用 `max_completion_tokens`"，而思考模型 / 联 |
| tool-calling.md | 257 | - 流式下 `tool_call.type` 与声明一致（`function` / `builtin_function`）。⚠ 文档自相矛盾：OpenAPI 响应 schema 里 `tool_calls[].type` 枚举只有 `function`，流式指南却说会返回 `builtin_func |
| tool-calling.md | 258 | - ⚠ 文档自相矛盾：tool_calls 指南的流式示例把 `messages` 初始化为 `[{}, {}]` 并注释"设置了 n=2"，但请求里没传 `n`，且 models-overview 写明 `n` 固定为 1；只处理 `choices[0]` 即可。 |
| tool-calling.md | 272 | \| `{"type": "function", "function": {"name": "get_weather"}}` \| 强制调用指定工具 \| 文档原文："思考开启时传入会返回 400 错误（`tool_choice 'specified' is incompatible with th |
| tool-calling.md | 301 | - ⚠ 文档自相矛盾：openapi.json 对 `kimi-k2.6` / `kimi-k2.7-code` 的请求 schema 也把 `required` 列在 `tool_choice` 枚举里，而 models-overview 明确说这两个模型不支持、传入报错；以 models-ove |
| tool-calling.md | 302 | - 想"指定单个工具"又要用 K3：文档没有给可行写法。替代做法是 `required` + `tools` 里只放那一个工具（⚠ 未验证是否等价）。 |
| tool-calling.md | 379 | - 搜索结果会进入 prompt，`prompt_tokens` 会明显变大；文档示例从 `arguments["usage"]["total_tokens"]` 读取搜索内容占用的 token 数（⚠ 该字段结构文档只在示例里出现，未在参数表中定义）。 |
| tool-calling.md | 380 | - ⚠ 文档未说明：`$web_search` 的 `arguments` 除 `usage` 外还有哪些字段；是否支持 `tool_choice: "required"` 强制搜索；每次搜索的调用费金额（pricing/tools 页不在本次材料内）。 |
| tool-calling.md | 394 | \| `web-search` \| 实时信息及互联网检索（按次收费，单价 ⚠ 文档未说明） \| |
| tool-calling.md | 446 | messages.append(message)          # 原样回传（含 reasoning_content）；官方示例只挑了三个字段，见 ⚠ |
| tool-calling.md | 465 | 失败时 `status` 为各类错误值，错误信息可能在顶层 `error` 或 `context.error`（思考模型指南示例两处都查）；⚠ 文档未说明 `status` 完整枚举。 |
| tool-calling.md | 471 | - ⚠ 文档未说明：Formula 端点的完整请求/响应 schema（不在 openapi.json）、免费工具的免费期限、Formula 接口是否受 RPM 限速。 |
| tool-calling.md | 472 | - ⚠ 文档自相矛盾：Formula 示例的 `tool` 消息没有 `name` 字段，而 tool_calls 指南示例有；`reasoning_content` 的处理也不一致（见 §2）。 |
| tool-calling.md | 545 | - ⚠ 文档未说明：单条 system-tools 消息可注入的工具数量上限；动态注入的工具与顶层同名时以谁为准。 |
| tool-calling.md | 604 | ## 10. ⚠ 汇总 |
| files-and-batch.md | 93 | - 文件问答指南的步骤 2 写的是"通过文件抽取接口 `/v1/files/{file_id}`"，但代码与 OpenAPI 都是 `/v1/files/{file_id}/content`；`GET /v1/files/{file_id}` 只返回元数据。`⚠ 文档自相矛盾`（几乎肯定是笔误，以  |
| files-and-batch.md | 94 | - 上传后是否要等待 `status` 变为某个值才能取 content：`⚠ 文档未说明`（所有示例都是上传后立刻取 content）。 |
| files-and-batch.md | 122 | - 图片 / 视频的格式、尺寸、时长限制：`⚠ 文档未说明`（本次材料未含视觉模型指南 `/docs/guide/use-kimi-vision-model`；`ms://` 写法取自 Batch 指南的 chat body，实时调用 body 结构相同）。 |
| files-and-batch.md | 150 | `purpose` 枚举（`⚠ 文档自相矛盾`：主 OpenAPI 与 Hosted Agents 规范都只列 4 个值；errors 页的报错文案列了 6 个）： |
| files-and-batch.md | 158 | \| `batch_output` \| 仅在 errors 页 `Invalid purpose` 报错文案中出现 \| 推测是 Batch 输出/错误文件的 purpose，`⚠ 文档未说明` 能否由用户主动上传 \| errors \| |
| files-and-batch.md | 159 | \| `lambda` \| 仅在 errors 页报错文案中出现 \| 用途 `⚠ 文档未说明` \| errors \| |
| files-and-batch.md | 161 | Hosted Agents 规范另说 `purpose` "默认为 `file-extract`"（即可省略），主 OpenAPI 标为必填。`⚠ 文档自相矛盾`——保险做法：永远显式传。 |
| files-and-batch.md | 191 | - `status`：文件处理状态，主 OpenAPI **未给枚举**（`⚠ 文档未说明`）；Hosted Agents 规范的对应字段 `extract_status` 为 `ready` \| `error`（`error` = 文档解析失败，文件仍可见、可删除）。 |
| files-and-batch.md | 200 | - 上传是否同步完成解析、`status` 何时变化：`⚠ 文档未说明`。 |
| files-and-batch.md | 213 | \| （无） \| \| \| \| OpenAPI 未定义任何 query 参数；**是否分页、能否按 `purpose` 过滤：`⚠ 文档未说明`** \| |
| files-and-batch.md | 233 | - 顶层 `object` 的取值 OpenAPI 只标 string（`"list"` 是 OpenAI 惯例）；OpenAI SDK 会把 `purpose=` 等参数透传成 query，Kimi 是否理会：均 `⚠ 文档未说明`。 |
| files-and-batch.md | 261 | - 404 的 `error.type` 为 `resource_not_found_error`。若想用它轮询"解析完成"，需要 `status` 的枚举，主 OpenAPI 未给出（`⚠ 文档未说明`）。 |
| files-and-batch.md | 290 | - `object` 的取值 OpenAPI 只标 string（`⚠ 文档未说明`，OpenAI 惯例是 `"file"`）。兼容模式返回 200；带 `kimi-api-version` 头时返回 204（无 body）。 |
| files-and-batch.md | 291 | - Hosted Agents 规范："文件删除后，仍可能残留在活跃会话的工具调用中"。删除 batch 输入文件是否影响进行中的 batch：`⚠ 文档未说明`。 |
| files-and-batch.md | 323 | - `⚠ 文档自相矛盾`：Hosted Agents 规范说 file-extract 的内容端点"返回一个携带解析出的 Markdown 的 **JSON 对象**"，主 OpenAPI 与所有示例代码都是 `text/plain` 直接 `.text` 使用。可能与 `kimi-api-vers |
| files-and-batch.md | 324 | - 对 `image` / `video` 文件调用：不可用（Hosted Agents 规范），具体 HTTP 状态、内容大小上限、是否分页：`⚠ 文档未说明`。 |
| files-and-batch.md | 335 | - 模型：只能 `kimi-k2.7-code` 或 `kimi-k2.6`；`kimi-k3` 不支持；`kimi-k2.7-code-highspeed` 是否支持 `⚠ 文档未说明`。 |
| files-and-batch.md | 337 | - body 里**不要写** `temperature` / `top_p` / `n` / `presence_penalty` / `frequency_penalty`（这些模型在 Batch 下不可修改）。写了会怎样（忽略 or 校验失败）：`⚠ 文档未说明`。 |
| files-and-batch.md | 339 | - 输入文件：`.jsonl` 扩展名、非空、≤ 100MB、`purpose="batch"`；每组织最多 1000 个 batch 类型文件。与单用户 1000 个文件的关系、单文件最大行数、并发 batch 数：`⚠ 文档未说明`。 |
| files-and-batch.md | 417 | - 输出行是否保持输入顺序：`⚠ 文档未说明`，按 `custom_id` 对齐。`error_file_id` 里每行的格式：`⚠ 文档未说明`（只说"包含错误文件 ID"）。 |
| files-and-batch.md | 418 | - `expired` / `cancelled` 时已完成的部分是否产出 `output_file_id`、是否计费；40% 折扣如何体现、Batch 是否有独立的 RPM/TPM 限制：`⚠ 文档未说明`。 |
| files-and-batch.md | 419 | - 输出文件的 `purpose`：推测为 errors 页出现的 `batch_output`；它是否计入 1000 个文件配额、保留多久：`⚠ 文档未说明`。 |
| files-and-batch.md | 479 | （其余时间戳字段见第 5 节表；batch `id` 前缀、创建时 `request_counts.total` 是否已知：`⚠ 文档未说明`。） |
| files-and-batch.md | 483 | - 校验是**异步**的：创建返回 200 不代表文件合法，要等 `validating` → `in_progress` 或 `failed`。校验失败的具体原因写在哪（响应 body？error 文件？）`⚠ 文档未说明`。 |
| files-and-batch.md | 513 | - `request_counts` 在 `validating` 阶段是否有值：文档示例做了 `if batch.request_counts else 0` 的防御，暗示可能为空（`⚠ 文档未说明`，OpenAPI 标为 required）。 |
| files-and-batch.md | 526 | \| `limit` \| integer (query) \| 否 \| 20 \| 每页数量；最大值 `⚠ 文档未说明` \| |
| files-and-batch.md | 546 | - OpenAI SDK 的 `SyncCursorPage` 自动翻页依赖 `has_more` + 最后一个 `id`，与这里的 `after` 语义一致。是否支持按 `status` 过滤、排序方式：`⚠ 文档未说明`。 |
| files-and-batch.md | 576 | - 取消前已完成的请求是否计费、是否产出部分结果：`⚠ 文档未说明`。 |
| files-and-batch.md | 595 | Batch 校验失败（`status=failed`）的常见原因（batch-create 页限制表）：非 `.jsonl` 扩展名、空文件或 > 100MB、组织 batch 文件超 1000、同批多个模型、`custom_id` 重复、模型不存在或无权限。这些是在 `validating` 阶段 |
| files-and-batch.md | 599 | **⚠ 文档自相矛盾（汇总，详见各小节）**：(1) `purpose` 枚举 4 值（两份 OpenAPI）vs 6 值（errors 页文案）；(2) `purpose` 必填（主 OpenAPI）vs 可省略默认 `file-extract`（Hosted Agents 规范）；(3) fil |
| responses-messages-and-utilities.md | 188 | - `tool_choice` 枚举只有 `auto`；传 `required`/`none`/指定函数对象会怎样 `⚠ 文档未说明`。 |
| responses-messages-and-utilities.md | 190 | - `text.format` 只有 `json_schema`，且 `schema` 必填；`{"type": "text"}` / `json_object` 是否被接受 `⚠ 文档未说明`。 |
| responses-messages-and-utilities.md | 191 | - 请求体规范未列出 `temperature`、`top_p`、`metadata`、`parallel_tool_calls`、`service_tier`（响应体里 `temperature`/`top_p`/`metadata`/`service_tier` 为可空字段，`parallel_ |
| responses-messages-and-utilities.md | 192 | - `input[].role` 枚举为 `user`/`assistant`/`developer`，没有 `system`；`role: system` 是否被接受 `⚠ 文档未说明`，系统提示请用 `instructions` 或 `developer`。 |
| responses-messages-and-utilities.md | 193 | - 流式各事件除 `type`/`sequence_number` 外的载荷字段（如 `delta`、`item`、`response`）`⚠ 文档未说明`，上面示例按 OpenAI 惯例读取 `delta`。 |
| responses-messages-and-utilities.md | 335 | - `tool_choice.type` 只有 `auto`/`any`/`none`，**没有原生的 `{type: tool, name}`**（强制调用指定工具）；也未列出 `disable_parallel_tool_use`。传了会怎样 `⚠ 文档未说明`。 |
| responses-messages-and-utilities.md | 336 | - 推理控制用 Kimi 的 `output_config.effort`，规范未列出原生 `thinking: {type: enabled, budget_tokens}`；传原生 `thinking` 参数是否被接受/忽略 `⚠ 文档未说明`。`effort` 没有"关闭"档，thinking |
| responses-messages-and-utilities.md | 339 | - 规范未列出 `temperature`、`top_p`、`top_k`、`cache_control`（`cache_creation_input_tokens` 表明缓存是自动的）；这些参数传入后是否生效 `⚠ 文档未说明`。 |
| responses-messages-and-utilities.md | 341 | - 流式事件里未列出原生 Anthropic 的 `ping` 与 `error` 事件；流中出错如何表达 `⚠ 文档未说明`。 |
| responses-messages-and-utilities.md | 342 | - 401 的响应体在规范中引用的是 OpenAI 风格 `{"error": {"message", "type", "code"}}`，与 400/500 的 Anthropic 格式不同；这会不会影响 anthropic SDK 的异常解析 `⚠ 文档未说明`（规范原文如此，两处都列出以备核对 |
| responses-messages-and-utilities.md | 343 | - `model` 字段规范同时写了 `required` 与 `default: kimi-k3` `⚠ 文档自相矛盾`（必填字段不该有默认值）；保险起见总是显式传 `model`。 |
| responses-messages-and-utilities.md | 344 | - **Claude Code 接入**：文档只有一句"已经在使用 Anthropic SDK、Claude Code 等工具的开发者，只需把 base URL 指向 `https://api.moonshot.cn/anthropic`"；具体的环境变量名 / 配置项 / 模型名映射 `⚠ 文档未 |
| responses-messages-and-utilities.md | 399 | - `object`、`owned_by` 的具体取值 `⚠ 文档未说明`（上面示例值仅为占位）。 |
| responses-messages-and-utilities.md | 462 | - 请求体没有 `tools` 字段，工具定义占用的 Token 无法用本接口估算 `⚠ 文档未说明`。 |
| responses-messages-and-utilities.md | 463 | - 只接受 Chat Completions 风格的 messages；Responses 的 `input[]` item 和 Messages 的 content block 需自行转换后再估算，直接传是否会拒绝或误算 `⚠ 文档未说明`。名字是"估算"，与真实 `usage` 是否严格一致 ` |
| responses-messages-and-utilities.md | 509 | - 响应壳是 `code`（0 表示成功）/ `data` / `scode`（状态码，取值 `⚠ 文档未说明`）/ `status`（boolean），不是 OpenAI 风格；成功判据用 `code == 0`。 |
| responses-messages-and-utilities.md | 598 | - 签名与 API Key 的关系（能否用另一个 Key 校验别人的签名）`⚠ 文档未说明`；文档说"持有四元组的任何一方都可以验证"，但接口本身仍要求 Bearer 鉴权。 |
| errors-and-limits.md | 39 | `/docs/api/errors` 的表格里有多行"典型 message"列实际填的是原因说明、message 原文缺失；这些行统一标 `⚠ 文档未说明`，不要拿说明文字去做字符串匹配。 |
| errors-and-limits.md | 46 | \| 400 \| `invalid_request_error` \| ⚠ 文档未说明 \| 请求格式错误、缺少必填参数或参数类型非法 \| 对照接口文档检查请求体 \| |
| errors-and-limits.md | 48 | \| 400 \| `invalid_request_error` \| ⚠ 文档未说明 \| `prompt_tokens + max_tokens` 超过模型规格 \| 减小 `max_completion_tokens`（`max_tokens` 已弃用）或换模型 \| |
| errors-and-limits.md | 52 | \| 400 \| `invalid_request_error` \| ⚠ 文档未说明 \| 上传文件总数超过上限（上限数值 ⚠ 文档未说明） \| 删除不再使用的早期文件后重试 \| |
| errors-and-limits.md | 73 | \| 404 \| `resource_not_found_error` \| ⚠ 文档未说明 \| 模型不存在（含已下线的 `moonshot-v1-*`、`kimi-k2.5`、`kimi-k2-*`、`kimi-latest`），或当前账号无权访问该模型（如未充值就调 `kimi-k3`） \ |
| errors-and-limits.md | 84 | \| 429 \| `exceeded_current_quota_error` \| ⚠ 文档未说明 \| 账户欠费或已停用 \| 检查余额与账单 \| |
| errors-and-limits.md | 85 | \| 429 \| `exceeded_current_quota_error` \| ⚠ 文档未说明 \| 账户 token 额度不足（含代金券失效） \| 调查询余额接口（文档 `/docs/api/balance`，路径未在本材料中给出）看 `available_balance`，充值后再试  |
| errors-and-limits.md | 86 | \| 429 \| `rate_limit_reached_error` \| ⚠ 文档未说明 \| 触发组织级**并发**限制 \| 降低并发或等待指定时间后重试 \| |
| errors-and-limits.md | 87 | \| 429 \| `rate_limit_reached_error` \| 片段：`Your account reached max request`（完整原文 ⚠ 文档未说明） \| 触发组织级 **RPM** 限制；常因 SDK 自动重试放大请求数 \| 按响应提示等待后重试；Tier0 注 |
| errors-and-limits.md | 89 | \| 429 \| `rate_limit_reached_error` \| ⚠ 文档未说明 \| 触发组织级 **TPD** 限制（仅 Tier0 有 TPD 上限） \| 次日恢复或充值升级 \| |
| errors-and-limits.md | 98 | \| 499 \| `client_closed_request` \| ⚠ 文档未说明 \| 客户端在服务端返回前断开：流式响应被中间代理切断、用户主动取消、本地超时太短 \| 检查 KeepAlive、SDK / 代理超时设置；注意服务端可能已完成并计费 \| |
| errors-and-limits.md | 99 | \| 500 \| `server_error` \| ⚠ 文档未说明 \| 服务端内部错误 \| 稍后重试；持续出现则附 `request_id` 联系 api-service@moonshot.ai \| |
| errors-and-limits.md | 100 | \| 500 \| `unexpected_output` \| ⚠ 文档未说明 \| 服务端内部错误（模型输出异常） \| 同上 \| |
| errors-and-limits.md | 101 | \| 503 \| `server_unavailable` \| ⚠ 文档未说明 \| 服务暂时不可用，通常与节点扩容 / 维护有关 \| 稍后重试 \| |
| errors-and-limits.md | 104 | ⚠ 文档自相矛盾 —— 504 的触发时长：`/docs/api/errors` 说"服务端 **900 秒**无响应，网关返回 HTML 超时页面"；`/docs/introduction#处理响应` 说"通常我们会设置一个 **2 小时**的超时时间，单个请求超过这个时间返回 504"。两处都写 |
| errors-and-limits.md | 135 | - **TPM 的计数方式**：按 `prompt tokens + 请求里的 max_completion_tokens` 预估，**不看实际生成量**；没传 `max_completion_tokens` 就用模型默认值计。`kimi-k3` 的默认 `max_completion_tokens |
| errors-and-limits.md | 136 | - 限速作用范围：`/docs/introduction` 说"在**用户级别**而非密钥级别实施"，`/docs/api/errors` 说"**组织级**"并发 / RPM / TPM / TPD —— ⚠ 文档自相矛盾（也可能只是措辞不同）。共同点：**不是按 Key 分的**，多建 Key  |
| errors-and-limits.md | 145 | \| 429 `rate_limit_reached_error`（并发 / RPM / TPM） \| 重试 \| 按 message 提示等待；RPM / TPM 是分钟窗口，退避不要短于几秒；文档未说明这类响应是否带 `Retry-After` ⚠ 文档未说明 \| |
| errors-and-limits.md | 171 | \| `request_id` 怎么拿 \| 文档多处要求提供 `request_id`，但**在哪个响应头 / 字段里 ⚠ 文档未说明**。可尝试：openai SDK 的 `e.request_id` / `completion._request_id`（读 `x-request-id` 头，K |
| errors-and-limits.md | 293 | - 判断 TPD 用的是 message 关键字匹配，因为四种 `rate_limit_reached_error` 共用同一个 `type`，只有 message 能区分；TPD 的 message 原文 ⚠ 文档未说明，实际以 API 返回为准。 |

## P5 — 子 Agent 汇报的、值得优先实测的文档矛盾（摘录）

| 矛盾 | 文档 A | 文档 B | 测法 |
|---|---|---|---|
| 504 超时阈值 | api/errors：900 秒 | introduction：2 小时 | 非流式请求让 K3 生成超长输出，记录实际超时秒数 |
| 限速作用域 | pricing/limits：组织级 | introduction："用户级别而非密钥级别" | 同组织两个 key 并发触发 429，看是否共享配额 |
| K2.x `tool_choice` | api/models-overview：仅不支持 `required` | guide/kimi-k2-6-quickstart：除 auto/none 外都报错 | K2.6 思考开 / 关各传一次函数对象 |
| 回传 assistant 消息 | guide/use-thinking-models：必须含 `reasoning_content` | guide/use-official-tools 示例只留 role/content/tool_calls | K3 工具循环去掉 `reasoning_content` 回传，看报错还是静默 |
| `max_tokens` | openapi：已弃用，用 `max_completion_tokens` | 所有示例仍用 `max_tokens` | 两个都传 / 只传旧的，看是否 warning 或报错 |
| `purpose` 枚举 | openapi：file-extract/image/video/batch | api/errors 报错文案多出 batch_output/lambda | 传 `lambda` 看是否接受 |
| `/files/{id}/content` 返回 | 主 openapi + 示例：text/plain | files-upload 页内嵌的 Hosted Agents 规范：JSON（Markdown 字段） | 带 / 不带 `kimi-api-version` 头各取一次 |
| Messages `model` | 规范同时标 `required` 与 `default: kimi-k3` | — | 不传 model 看是否 400 |
| Messages `stop_reason` | 命中 stop_sequences 时返回 `end_turn` 而非 Anthropic 原生 `stop_sequence` | — | 传 stop_sequences 触发一次 |
| Responses / Messages 模型范围 | 规范只列 `kimi-k3` | Chat 支持全部 4 个 | 在 Responses 传 `kimi-k2.6` |
