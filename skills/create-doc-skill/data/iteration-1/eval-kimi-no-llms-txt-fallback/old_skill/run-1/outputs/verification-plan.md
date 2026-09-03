# Kimi API Skill — 真实 API 验证计划

> 状态：待执行。本技能（`kimi-api/`）目前是纯文档草稿。拿到 `MOONSHOT_API_KEY` 后按本计划逐条实测，把结论（含报错原文 / 响应片段 + 验证日期）回写到对应 reference 文件，并把"待验证疑点"逐条消掉。
> 预算：绝大多数测试是几十到几百 token 的短对话，总花费预计 < ¥5（K3 需先充值 ≥ ¥10 解锁；Tier0 限速 RPM 3、并发 1，建议先充 ¥50 到 Tier1 再跑，否则脚本要串行并 sleep）。

## 0. 准备

```bash
export MOONSHOT_API_KEY=...        # 只在 shell 里，不写进任何文件
uv run --with openai --with anthropic --with requests python verify.py
```
- 全部脚本放在 `verification/` 目录，输出写 `verification/results-YYYY-MM-DD.jsonl`（每条：test_id、request 摘要、http status、`error.type`、message 原文、关键响应字段）。
- 每个测试独立 try/except，不因一条失败中断。
- 测完 `grep -r "sk-" kimi-api/ verification/` 确认无 Key 泄漏；清理上传的测试文件与 Batch。

## 1. 基础连通与模型目录（P0，成本≈0）

| ID | 测试 | 预期（按文档） | 回写到 |
|---|---|---|---|
| M1 | `GET /v1/models`，记录全部 `id` 及 `context_length` / `supports_*` 扩展字段 | 4 个在线模型；扩展字段存在 | models.md、errors-and-limits.md |
| M2 | `model="moonshot-v1-8k"` / `"kimi-latest"` / `"kimi-k2.5"` 各调一次 | 404 `resource_not_found_error`，记 message 原文 | models.md |
| M3 | `GET /v1/users/me/balance` | `{"code":0,"data":{...}}` 包装结构 | errors-and-limits.md |
| M4 | 错误 Key → 401；缺 header → 401；记录两种 `error.type` | `invalid_authentication_error` / `incorrect_api_key_error` | errors-and-limits.md |
| M5 | 错误响应是否含 `error.code` 字段 | OpenAPI 有、错误页无 | errors-and-limits.md |

## 2. Chat Completions 参数行为（P0）

| ID | 测试 | 疑点来源 |
|---|---|---|
| C1 | K3 传 `temperature=0.6` / `=1.0` / `top_p=0.5` / `n=2` / `presence_penalty=0.5` 各一次 | files-upload 示例 vs models-overview 矛盾 |
| C2 | K2.6 思考模式传 `temperature=0.6`；非思考传 `1.0`；K2.7-code 传 `0.6` | "传其他值报错" 的精确 error.type/message |
| C3 | 只传 `max_tokens`（不传 `max_completion_tokens`）；两者都传且不同 | 弃用字段是否仍生效、优先级 |
| C4 | K3 `max_completion_tokens=1048576` + 短输入 | 是报错还是自动裁剪 |
| C5 | `reasoning_effort="medium"`；K3 传 `thinking={"type":"disabled"}`；K2.6 传 `reasoning_effort` | 跨模型参数：报错 or 忽略 |
| C6 | K2.7-code 传 `thinking={"type":"disabled"}`；`keep: null` | 报错原文 |
| C7 | 非流式响应：`message.reasoning_content` 是否存在；`usage` 是否有 `cached_tokens`、有无 `completion_tokens_details.reasoning_tokens` | usage 结构 |
| C8 | 流式：`stream=True` 不带 `stream_options` 时 usage 在哪一帧、哪一层（top-level vs `choices[].usage`）；带 `include_usage=True` 时是否多一帧 `choices=[]`；`delta.reasoning_content` 是否出现 | 三处文档不一致 |
| C9 | 多轮：第二轮回传 assistant message（a）含 `reasoning_content`（b）不含，K3 / K2.7-code / K2.6(keep=all) 各测 | "必须原样回传"是硬错误还是降级 |
| C10 | 同一 system prompt（>256 token）连发两次，看第二次 `cached_tokens`；prompt 恰好 256 与 255 token 各测；加 `prompt_cache_key` 对比 | 缓存阈值与 key 作用 |
| C11 | `response_format={"type":"json_object"}` 不在 prompt 提 JSON；`json_schema` strict=true 用含 `additionalProperties`/`$ref` 的 schema | strict 校验：报错 / warning / 200 |
| C12 | Partial Mode：最后一条 assistant `partial: true` + `content` 前缀；`content: ""`；与 `json_object` 同用 | 响应是否含前缀；空 content 是否被拒 |
| C13 | `stop` 传 6 个 / 单个 >32 字节 | 报错原文 |
| C14 | `logprobs=True, top_logprobs=3` on K3 | 返回结构 |
| C15 | 带 `X-Msh-Request-Nonce` 的流式与非流式请求 → `POST /v1/signatures/verify`；nonce 重放 | 签名头在流式下是否返回 |

## 3. 工具调用（P0）

| ID | 测试 |
|---|---|
| T1 | 标准 function 循环（K3）：记录 `tool_calls[].id` 格式；回传 tool 消息带/不带 `name`；`tool_call_id` 错配 |
| T2 | `tool_choice="required"` on K2.6 / K2.7-code → 报错原文；`tool_choice={"type":"function",...}` on K3（思考开启）是否 400 |
| T3 | `function.name` 含 `.`；两个同名工具；`strict=true` + 非 MFJS schema |
| T4 | 流式工具调用：`delta.tool_calls[].index` 拼接；`reasoning_content` 与 `tool_calls` 出现顺序 |
| T5 | `$web_search`（`type: "builtin_function"`）on K3 / K2.6：能否调用、`arguments.usage.total_tokens`、账单里是否按次计费 |
| T6 | K3 动态工具消息 `{"role":"system","tools":[...]}`：K3 正常；K2.6 报错原文（"tokenization failed"?）；同名重复声明 |
| T7 | 只传 `functions` / `function_call`（OpenAI 旧式）→ 报错还是忽略 |

## 4. 文件与视觉（P1）

| ID | 测试 |
|---|---|
| F1 | 上传小 PDF `purpose=file-extract` → `status` 值、是否立即可 `content`；文件 ID 是否 `file_` 前缀 |
| F2 | 上传 PNG `purpose=file-extract` → 报错原文；`purpose=batch_output` / `lambda` 由用户上传 → 报错 or 成功 |
| F3 | `GET /v1/files/{id}/content` 对 `purpose=image` 文件 |
| F4 | `GET /v1/files` 返回结构、有无分页字段 |
| F5 | 视觉：base64 PNG；`image_url` 直接给字符串；公网 https URL（记报错原文）；`ms://<file_id>`；SVG；GIF（对比 estimate token） |
| F6 | `content` 传序列化字符串（错误格式）→ 行为 |
| F7 | K2.7-code 传 `video_url` |
| F8 | 请求体 > 100M（可选，先用 estimate 接口试 20M base64 是否被拒） |

## 5. Batch（P1，用 3 条请求最小规模）

| ID | 测试 |
|---|---|
| B1 | K2.6 三条 JSONL 全流程：状态迁移时间线、结果行结构（`response.status_code`、error 行结构，故意放一条超长输入） |
| B2 | `model: kimi-k3` → 哪一步报错、状态 |
| B3 | body 带 `temperature=0.5` → 整批 failed / 单行 error / 忽略 |
| B4 | `completion_window="30m"` / `"1d"` / `"7d"` / `"8d"` |
| B5 | 混两个模型的 JSONL；`custom_id` 重复 |
| B6 | output 文件是否在 `GET /v1/files` 出现、可否删除；结果顺序与输入是否一致 |

## 6. Responses 与 Messages 入口（P1）

| ID | 测试 |
|---|---|
| R1 | `responses.create` 基础调用 + 流式，记录事件类型全集 |
| R2 | `model="kimi-k2.6"` → 报错；`tool_choice="required"` → 报错 or 当 auto；请求带 `temperature` |
| R3 | `namespace` 工具 via OpenAI SDK 是否被客户端拦截 |
| A1 | Anthropic SDK 默认头（`x-api-key`、`anthropic-version`）能否直接过；只用 `Authorization: Bearer` 的 requests 版本 |
| A2 | 缺 `max_tokens` → 400？；传 `thinking={"type":"enabled","budget_tokens":1024}` → 报错/忽略 |
| A3 | 多轮回传 `thinking` 块（含/不含 `signature`） |
| A4 | 图片 `media_type: image/bmp` |
| A5 | 同一 system 前缀在 chat / responses / messages 三入口间是否共享缓存命中 |

## 7. 限速与工具接口（P2）

| ID | 测试 |
|---|---|
| L1 | Tier1 账号：`max_completion_tokens=131072` 连续 20 次并发 5 → 是否 `rate_limit_reached_error`（TPM 预扣）；不传时对比 |
| L2 | 429 响应是否带 `Retry-After` |
| L3 | `estimate-token-count` 带 `tools`、带 `ms://` 引用 |
| L4 | 未充值账号调 K3 的报错（若能造出此状态） |

## 8. 回写规则

- 每条结论在 reference 文件对应位置加：`✅ 已用真实 API 验证 2026-MM-DD：<一句话结论>`，附报错 `type`/`message` 原文或响应片段（≤5 行）。
- 与文档不符的，额外在文件顶部加一个 `## 文档 vs 实测差异` 小节集中列出（tag：**[DOC-MISMATCH]**），便于后续人快速判断哪些结论可能过期。
- 验证完成后更新 `SKILL.md` 顶部状态行，把"尚未验证"改为"已验证（日期），未覆盖项见 verification-plan.md 剩余项"。
- 然后跑 `evals/evals.json`（with-skill vs baseline）用真实报错做 grader 依据，产出 iteration-N 对照报告。
