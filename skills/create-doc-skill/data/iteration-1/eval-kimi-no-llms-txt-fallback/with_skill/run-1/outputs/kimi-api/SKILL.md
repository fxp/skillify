---
name: kimi-api
description: 接入 Moonshot AI 月之暗面 Kimi 开放平台（platform.kimi.com / platform.moonshot.cn，API 域名 api.moonshot.cn）的 API 使用手册——涵盖 Chat Completions、Responses、Anthropic Messages 三种兼容协议，kimi-k3 / kimi-k2.7-code / kimi-k2.6 模型选型与思考模式（reasoning_effort、thinking、reasoning_content 回传），工具调用与内置 $web_search，视觉输入，文件问答（file-extract），Batch 批处理，JSON Mode / Partial Mode，错误码与限速。当用户提到 "Kimi""Moonshot""月之暗面""moonshot.cn""kimi.com""MOONSHOT_API_KEY""kimi-k3""kimi-k2.6"，或要写代码调用上述任意能力时，务必先读本技能，不要凭记忆使用 moonshot-v1-8k 等已下线模型名、也不要照搬 OpenAI 的 temperature / tool_choice / 文件附件习惯——Kimi 在这些地方的行为与 OpenAI 不同。
---

# Kimi 开放平台（Moonshot AI）接入指南

Kimi API 是月之暗面（Moonshot AI）的大模型服务，兼容 OpenAI Chat Completions / Responses 与 Anthropic Messages 三种协议，主力模型是 `kimi-k3`（1M 上下文、视觉、始终思考）。本 skill 的目标是让你第一次就写出能在真实 API 上跑通的代码——Kimi 和 OpenAI "长得像"，但在采样参数、思考配置、工具强制、文件用法上有一批不兼容点，凭 OpenAI 直觉写会直接报错。

## ⚠ 验证状态（2026-09-03）

**本 skill 全部内容均为文档转录，尚未用真实 API Key 调用验证。** 来源是 `platform.kimi.com/docs/openapi.json`（OpenAPI 3.1.0，16 个 endpoint）和 40 篇官方文档页（抓取于 2026-09-03）。每个 reference 文件顶部都有同样的声明；文档没写清的地方标了 `⚠ 文档未说明`，文档前后矛盾的地方标了 `⚠ 文档自相矛盾`。拿到 key 后按 `kimi-api-workspace/verification-plan.md` 逐条实测并把结论写回。本文和 reference 中引用的所有报错原文（如 `tool_choice 'specified' is incompatible with thinking enabled`、`tokenization failed`）都是**从文档页面抄录的，不是实测观察到的**。实际调用报错时，**优先信任 API 返回，而不是本文**。

## 用之前先确认 4 件事

1. **Base URL 按协议分三个**，不要混：
   - OpenAI Chat Completions / Responses：`https://api.moonshot.cn/v1`
   - Anthropic Messages：`https://api.moonshot.cn/anthropic`（endpoint 全路径 `/anthropic/v1/messages`）
2. **鉴权**：`Authorization: Bearer $MOONSHOT_API_KEY`（有 `Bearer ` 前缀，无第二个必需 header）。Key 在 https://platform.kimi.com/console/api-keys 创建。**中国站 platform.kimi.com 和国际站 platform.kimi.ai 的账号、余额、Key 完全隔离**，用错站点返回 401。
3. **模型名只有 4 个是活的**：`kimi-k3`、`kimi-k2.7-code`、`kimi-k2.7-code-highspeed`、`kimi-k2.6`。训练语料里常见的 `moonshot-v1-8k/32k/128k`、`moonshot-v1-auto`、`kimi-latest`、`kimi-k2-*`、`kimi-k2.5`、`kimi-thinking-preview` **全部已下线，调用返回 404**。不确定就用 `kimi-k3`。
4. **最容易选错的字段是"推理配置"，每个模型不一样**（详见 `references/models-and-thinking.md`）：
   - `kimi-k3`：顶层 `reasoning_effort: "low" | "high" | "max"`（默认 `max`），**不要传 `thinking`**
   - `kimi-k2.6`：`thinking: {"type": "enabled"}`（默认）或 `{"type": "disabled"}`；OpenAI SDK 里必须走 `extra_body`
   - `kimi-k2.7-code(-highspeed)`：思考强制开启，`thinking` 省略或只能是 `{"type":"enabled","keep":"all"}`，传 `disabled` 报错

## 30 秒跑通第一个请求

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{"model": "kimi-k3", "messages": [{"role": "user", "content": "你好，1+1 等于多少？"}]}'
```

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")
completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[{"role": "user", "content": "你好，1+1 等于多少？"}],
)
msg = completion.choices[0].message
print(getattr(msg, "reasoning_content", None))  # 思考模型会多返回这个字段
print(msg.content)
```

注意示例里**没有传 `temperature`**——Kimi 当前所有模型的 `temperature` / `top_p` / `n` / `presence_penalty` / `frequency_penalty` 都是固定值，传其他值会报 `invalid_request_error`。

## 能力域导航

| 我想做什么 | 读哪个文件 | 涉及的核心 endpoint |
|---|---|---|
| 选模型、开关思考、调推理强度、看各模型参数约束、迁移到 K3、定价与限速等级 | `references/models-and-thinking.md` | `GET /v1/models`、`POST /v1/chat/completions` 的 `model` / `thinking` / `reasoning_effort` |
| 普通对话、多轮上下文、流式输出、JSON Mode / `response_format`、Partial Mode 续写、图片/视频输入、自动缓存、断线重连 | `references/chat-completions.md` | `POST /v1/chat/completions` |
| 函数工具调用循环、`tool_choice`、内置联网搜索 `$web_search`、动态加载工具、K3 工具最佳实践、重复调用排查 | `references/tool-calling.md` | `POST /v1/chat/completions`（`tools` / `tool_calls`） |
| 上传文件做文档问答、图片/视频文件引用、Batch 批量推理 | `references/files-and-batch.md` | `POST/GET/DELETE /v1/files*`、`POST/GET /v1/batches*` |
| 用 OpenAI Responses 协议、用 Anthropic SDK / Claude Code 接入、算 token、查余额、校验签名 | `references/responses-messages-and-utilities.md` | `POST /v1/responses`、`POST /anthropic/v1/messages`、`POST /v1/tokenizers/estimate-token-count`、`GET /v1/users/me/balance`、`POST /v1/signatures/verify` |
| 处理报错、重试策略、限速等级、排障 | `references/errors-and-limits.md` | 所有 endpoint 的 `{"error": {"type", "message"}}` |

**不在本 skill 范围内**：Kimi 托管智能体（Hosted Agents，`/docs/hosted-agents/*`，独立的 64 个 REST endpoint，规范在 `https://platform.kimi.com/docs/openapi-hosted-agents.yaml`）。需要时直接抓那份 YAML，鉴权方式与本文相同（`Authorization: Bearer sk-...`）。

## 跨领域的通用规则（写代码前必读）

这些是"凭 OpenAI / 其他平台的经验一定会写错"的地方，全部来自官方文档；标注 ⚠ 的仍待真实调用确认。

1. **不要显式传采样参数。** `temperature`、`top_p`、`n`、`presence_penalty`、`frequency_penalty` 在 `kimi-k3` / `kimi-k2.7-code` / `kimi-k2.6` 上全是固定值（temperature 1.0；k2.6 非思考模式 0.6），传其他值直接报错。要"更确定的输出"靠 prompt 和 JSON Mode，不靠 temperature。
2. **推理配置按模型二选一，不能通用。** K3 用顶层 `reasoning_effort`（OpenAI SDK 原生参数，直接传），K2.x 用 `thinking`（OpenAI SDK 里必须 `extra_body={"thinking": {...}}`，顶层传会被 SDK 拒绝）。给 K3 传 `thinking`、给 K2.x 传 `reasoning_effort` 都不支持。切换 `reasoning_effort` 档位会打断前缀缓存，会话开始时定好。
3. **思考模型的多轮 / 工具循环必须原样回传完整 assistant 消息，包括 `reasoning_content`。** K3 和 K2.7-code 的 Preserved Thinking 始终开启，只把 `content` 塞回 `messages` 会丢掉推理链，工具调用场景尤其明显。用 OpenAI SDK 时把 `choice.message` 整个（或 `model_dump(exclude_none=True)`）追加进 `messages`，不要手工只挑 `role` / `content` / `tool_calls`。
4. **`tool_choice: "required"` 只有 `kimi-k3` 支持**，`kimi-k2.6` / `kimi-k2.7-code` 传了会报错；`auto` / `none` 三个模型都行。OpenAI 式的 `{"type":"function","function":{"name":...}}` 指定单个工具文档也支持，但文档原文说"思考开启时传入会返回 400 错误（`tool_choice 'specified' is incompatible with thinking enabled`）"——K3 和 K2.7-code 的思考关不掉，所以按文档推断这种写法只在 `kimi-k2.6` + `thinking: disabled` 下可用（⚠ 文档推断，未实测）。
5. **`partial: true` 写在 `messages` 里最后一条 assistant 消息上，不是顶层参数。** 思考模型下这条 assistant 消息还要带 `reasoning_content`。
6. **文件问答不是 OpenAI 的 file attachment / Assistants 流程。** 步骤是：`files.create(file=..., purpose="file-extract")` → `files.content(file_id).text` 取回抽取后的文本 → 作为一条 `system` 消息放进 `messages`。图片 / 视频文件用 `purpose="image"` / `"video"` 上传后以 file id 引用（见 chat-completions.md）。`purpose` 只接受 `file-extract` / `batch` / `batch_output` / `lambda` / `image` / `video`，单文件 ≤100MB。
7. **内置联网搜索是 `{"type": "builtin_function", "function": {"name": "$web_search"}}`**，不是 `web_search` / `web_search_preview`；`$` 前缀是 Kimi 内置工具约定，普通 function 名里不允许出现 `$`。收到 `$web_search` 的 `tool_calls` 后，把模型给的 `arguments` 原样作为 tool 消息内容回传即可，搜索由平台执行。每次请求都要完整带上 `tools` 声明。动态加载工具（在 `messages` 里插 `{"role":"system","tools":[...]}`，不能带 `content`）**仅 `kimi-k3` 支持**，其他模型报 `tokenization failed`。回传工具结果时每个 `tool_call` 都要有一条 `role=tool` 消息（带 `tool_call_id`），少一条整个请求被拒。
8. **Batch 只支持 `kimi-k2.7-code` 和 `kimi-k2.6`，不支持 `kimi-k3`**；输入是 JSONL（每行 `custom_id` / `method` / `url` / `body`），以 `purpose="batch"` 上传，`completion_window` 文档示例用 `"24h"`（接受 `12h`–`7d`）。body 里同样不要写采样参数。价格为按量的 40% 折扣（不是 OpenAI 的 50%）；取消是异步的（先 `cancelling` 再 `cancelled`）。图片不要用 `file-extract` 上传做 OCR（2026-08-31 起不再支持），改用 `purpose="image"`。
9. **流式输出要 usage 需显式 `stream_options: {"include_usage": true}`**，最后一个 chunk 才带 `usage`（该 chunk `choices` 为空，遍历时跳过）；思考内容在 `delta.reasoning_content` 里增量到达。**非流式长请求会被网关 504（返回 HTML 页面，不是 JSON）**——超时阈值文档自相矛盾（errors 页 900 秒、introduction 页 2 小时，⚠ 待验证），长输出一律用 `stream=True`。输出上限参数用 `max_completion_tokens`（`max_tokens` 已标弃用，但官方示例仍在用）；K3 默认 131072、最大 1048576。
10. **错误结构是 `{"error": {"type": "...", "message": "..."}}`**，没有数字 code；按 `error.type` 分支处理。429 有四种 type：`engine_overloaded_error`（退避重试）、`rate_limit_reached_error`（降并发）、`exceeded_current_quota_error`（充值）——不要一律重试。**Tier0（未充值）并发 1、RPM 3**，写并发脚本前先看 `errors-and-limits.md` 的等级表。另外 **`kimi-k3` 要账户累计充值 ≥ ¥10 才解锁，新人 15 元代金券不能用于 K3**——新账号直接调 K3 会失败（⚠ 报错形态文档未说明）。
11. **Responses API 的图片只接受 `data:` URL（base64），不支持公网 http(s) URL**；Chat Completions 支持 URL / base64 / file id。
12. **自动上下文缓存无需配置**，但只有上一次请求 prompt tokens > 256 时后续才可能命中；保持 system prompt 和 tools 定义稳定放在前面。

## 目录结构

```
kimi-api/
├── SKILL.md                                   # 本文：路由 + 通用规则
├── references/
│   ├── models-and-thinking.md                 # 模型目录、参数约束、思考模式、定价限速
│   ├── chat-completions.md                    # /v1/chat/completions 全部用法
│   ├── tool-calling.md                        # tools / tool_choice / $web_search / 动态工具
│   ├── files-and-batch.md                     # /v1/files*、/v1/batches*
│   ├── responses-messages-and-utilities.md    # /v1/responses、/anthropic/v1/messages、工具类接口
│   └── errors-and-limits.md                   # 错误码、限速、重试
└── evals/evals.json                           # 对照实验场景（打包时排除）
```

内容整理自 https://platform.kimi.com/docs（`platform.moonshot.cn/docs` 同源，抓取于 2026-09-03）；实际调用报错优先信任 API。
