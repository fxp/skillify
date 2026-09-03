# 模型目录与选型

> 状态：文档草稿，基于 2026-09-03 抓取的 platform.moonshot.cn/docs 官方文档 + /docs/openapi.json 撰写，**尚未用真实 API 调用验证**。

## 在线模型（2026-09-03）

| 模型 ID | 定位 | 上下文 | 视觉 | 思考 | 备注 |
|---|---|---|---|---|---|
| `kimi-k3` | 旗舰：长程编程、知识工作、深度推理 | **1M** | 图片+视频 | 始终开启，`reasoning_effort` low/high/max（默认 max） | 需充值 ≥¥10 解锁；新用户 ¥15 代金券不可用；**不支持 Batch** |
| `kimi-k2.7-code` | Coding 模型，长上下文指令遵循更稳 | 256K | 图片+视频 | 始终开启，`thinking` 只接受 `{"type":"enabled","keep":"all"}` | 支持 Batch |
| `kimi-k2.7-code-highspeed` | 同上，高速版（~180 tok/s，短上下文可达 260） | 256K | 同上 | 同上 | 同一模型、参数约束完全一致，仅速度/价格不同 |
| `kimi-k2.6` | 通用：对话、Agent、视觉、推理 | 256K | 图片+视频 | 可开关：`thinking` = `{"type":"enabled"}`（默认）/ `{"type":"disabled"}` / `{"type":"enabled","keep":"all"}` | 支持 Batch |

选型：不确定就用 `kimi-k3`；纯代码生成/编程 Agent 且要快 → `kimi-k2.7-code-highspeed`；需要**关闭思考**的低延迟场景或 Batch → `kimi-k2.6`。

用 `GET /v1/models` 可动态确认当前 Key 能用哪些模型（响应含 `context_length`、`supports_image_in`、`supports_video_in`、`supports_reasoning`）。

## 已下线模型（调用返回 404 `resource_not_found_error`）

| 模型 | 下线日期 |
|---|---|
| `kimi-k2.5` | 2026-08-31 |
| `moonshot-v1-8k` / `-32k` / `-128k` / `-auto` 及 `-vision-preview` 全系 | 2026-08-31 |
| `kimi-k2-0905-preview` / `kimi-k2-0711-preview` / `kimi-k2-turbo-preview` / `kimi-k2-thinking` / `kimi-k2-thinking-turbo` | 2026-05-25 |
| `kimi-latest` | 2026-01-28 |
| `kimi-thinking-preview` | 2025-11-11 |

**这意味着训练语料里常见的 `moonshot-v1-8k` / `moonshot-v1-128k` / `kimi-latest` 都不能再用**——写代码时一律用上表在线模型。

## 各模型参数约束（来源: docs/api/models-overview）

| 参数 | `kimi-k3` | `kimi-k2.7-code` 系列 | `kimi-k2.6` |
|---|---|---|---|
| `temperature` | 固定 1.0，**传其他值报错** | 固定 1.0，传其他值报错 | 思考 1.0 / 非思考 0.6，传其他值报错 |
| `top_p` | 固定 0.95 | 固定 0.95 | 固定 0.95 |
| `n` | 固定 1 | 固定 1 | 固定 1 |
| `presence_penalty` / `frequency_penalty` | 固定 0 | 固定 0 | 固定 0 |
| 推理配置 | 顶层 `reasoning_effort` | `thinking`（仅 enabled+keep all） | `thinking`（enabled/disabled/keep all） |
| `tool_choice: "required"` | 支持 | **不支持，报错** | **不支持，报错** |
| `max_completion_tokens` 默认 / 上限 | 131072 / 1048576 | — / `256*1024 - prompt_tokens` | — / `256*1024 - prompt_tokens` |

官方建议：**不要显式传 `temperature` / `top_p` / `n` / penalties**。OpenAI SDK 不认识 `thinking`，要用 `extra_body={"thinking": {...}}` 传；`reasoning_effort` SDK 原生支持但只接受 `low`/`high`/`max`（没有 OpenAI 的 `medium`/`minimal`）。

## 模型间迁移

- `kimi-k2.6` → `kimi-k3`：换 `model`，删掉 `thinking`，需要时用顶层 `reasoning_effort`；多轮/工具调用要把 API 返回的**完整 assistant message（含 `reasoning_content`）原样回传**。
- `kimi-k2.7-code` → `kimi-k3`：只换 `model`，继续原样回传 assistant message。
- 从 OpenAI 迁移：换 `base_url` + Key + `model`；删除 `temperature`/`top_p`/`n`/penalties；`max_tokens` 改 `max_completion_tokens`（旧字段已弃用但仍被接受？见疑点）。
- 输出长度：K3 约 150 万汉字上下文，K2.x 约 40 万汉字（估算值）。

## 思考模式要点（详见 chat-completions.md）

- 思考内容在响应 `message.reasoning_content`（流式在 `delta.reasoning_content`）。
- K3 与 K2.7 Code 的 Preserved Thinking 始终开启：多轮对话与工具调用循环中，必须把上一轮 assistant message 原样（含 `reasoning_content`）放回 `messages`。
- K3 思考关不掉；嫌长就 `reasoning_effort="low"`。切换 effort 档位会打破前缀缓存，会话开始前定好。

来源: docs/models, docs/api/models-overview, docs/guide/kimi-k3-quickstart, docs/guide/kimi-k2-7-code-quickstart, docs/guide/kimi-k2-6-quickstart, docs/guide/troubleshooting, docs/get-api-key

---

## 待验证疑点

- `temperature=0.6` 传给 `kimi-k3` 的真实行为（docs/api/files-upload 示例这么写了，models-overview 说会报错）——两处文档矛盾，必须实测。
- `max_tokens`（已弃用）是否仍被接受并等价于 `max_completion_tokens`，还是报错/被忽略。
- `reasoning_effort="medium"`（OpenAI 值）是报错还是被映射。
- `kimi-k2.6` 非思考模式的 temperature 固定 0.6：传 1.0 会不会报错（文档说"传其他值报错"，但 1.0 是思考模式的固定值）。
- `GET /v1/models` 返回的模型列表与本表是否一致（是否还有文档未列的模型 ID，如带日期的快照版本）。
- `kimi-k3` 未充值账号调用的精确报错（403 permission_denied 还是 404）。
- 高速版与标准版的实际吞吐差异未量化。
