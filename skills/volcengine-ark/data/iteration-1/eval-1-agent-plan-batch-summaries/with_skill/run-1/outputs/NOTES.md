# NOTES — 用 Agent Plan（Medium）额度批量摘要 notes/*.md

## 文件

| 文件 | 作用 |
|---|---|
| `summarize_notes.py` | 主脚本：`notes/**/*.md` → `doubao-seed-2.0-lite` 三句话摘要 → `summaries/**/*.md`（保持子目录结构） |
| `requirements.txt` | 只依赖 `openai>=1.0`（方舟 OpenAI 兼容协议） |
| `.env.example` | 环境变量说明；Key 只走环境变量，不落盘 |

```bash
pip install -r requirements.txt
export ARK_AGENT_PLAN_API_KEY='<Agent Plan 专属 Key>'
python summarize_notes.py --dry-run          # 先看要处理哪些文件、粗估 AFP
python summarize_notes.py                    # 正式跑；默认 2 并发
python summarize_notes.py --budget-afp 300   # 可选：本次最多花约 300 AFP
```

## 三个必须配套的选择（配错任何一个要么 401 要么走后付费）

| 项 | 本脚本用的值 | 为什么 |
|---|---|---|
| **Base URL** | `https://ark.cn-beijing.volces.com/api/plan/v3` | Agent Plan 的 OpenAI 协议入口。`/api/v3` 是标准后付费入口——控制台原话「请勿使用 …/api/v3，接入会产生额外费用」；`/api/coding/v3` 是 Coding Plan 的，Agent Plan Key 打过去也是 401。 |
| **Key** | 环境变量 `ARK_AGENT_PLAN_API_KEY` | Agent Plan 有**专属** Key（控制台 → Agent Plan → 使用配置 → 第 3 步「配置专属API Key」，一个账号只有一把）。它与「API Key 管理」里的方舟 API Key **互不通用**：专属 Key 打 `/api/v3` 是 401（已实测），方舟 Key 打 `/api/v3` 则会成功但从余额扣钱。脚本故意不读 `ARK_API_KEY`，检测到只设了它会直接报错提示。 |
| **model** | `doubao-seed-2.0-lite`（小写、带点的 **Model Name**） | Plan 入口用 Model Name，不用带日期的 Model ID（`doubao-seed-2-0-lite-260428`）。实测 Plan 入口对带日期 ID 不报错但**静默改版本**，所以写 ID 没意义。Medium 档可用；AFP 系数 0.5/0.5，是套餐内除 `doubao-seed-2.0-mini`（0.25）外最省的文本模型，摘要任务够用。 |

## 「不能从后付费余额扣钱」是怎么保证的

1. **走对入口 + 对的 Key**：上表三项写死在代码里。`ARK_AGENT_PLAN_BASE_URL` 允许覆盖，但脚本会拒绝任何不含 `/api/plan` 的 URL。
2. **额度耗尽时的行为取决于控制台开关，不是代码**：Agent Plan 套餐有 5 小时 / 周 / 月三级 AFP 额度（Medium：10,000 / 35,000 / 100,000）。**未开启「超额后付费」**时，额度用完请求直接返回 `429 QuotaExceeded`，不会扣余额、也不消耗其他资源包；**开启后**会在不改任何配置的情况下自动切到后付费并出账单。所以请到 Agent Plan 控制台 → 「超额后付费管理」→ 模型页签，确认 `doubao-seed-2.0-lite` 的超额后付费是**关闭**的。这是唯一一个代码管不到、必须由你自己确认的点。
3. **`QuotaExceeded` 立刻停批次，不重试**：脚本收到 `QuotaExceeded` / `AuthenticationError` / `InvalidSubscription` / `UnsupportedModel` / 401 / 403 时整批停止（其他线程也不再发新请求）。额度刷新后（5 小时窗按首次请求起算；周一 0 点；订阅月首日）直接重跑，已生成的摘要会被跳过。
4. **校验响应里的 `model`**：Plan 入口会静默改写模型名。每次响应都检查 `model` 以 `doubao-seed-2-0-lite` 开头，否则视为被路由到了别的（可能系数更高的）模型并停止。
5. **关闭深度思考省 AFP**：`doubao-seed-2.0-lite` 默认**开**思考（实测不传 `thinking` 时 `reasoning_tokens≈109`），思维链 token 一样按 0.5 系数扣。三句话摘要不需要思考，脚本传 `extra_body={"thinking": {"type": "disabled"}}`（实测在该模型上生效，`reasoning_tokens=0`），并在响应里若发现 `reasoning_tokens>0` 就告警。
6. **可选 AFP 预算**：`--budget-afp N` 用响应 `usage` 按 `(prompt×0.5 + completion×0.5)/10000` 累计估算，超过即停（已写好的摘要保留）。`--dry-run` 给一个粗估。

## 其他守住的坑

- **`role` 只能是 `system/user/assistant/tool`**：方舟不接受 OpenAI 新版的 `developer` role（400 `InvalidParameter`，已实测），脚本用 `system`。
- **`max_tokens` vs `max_completion_tokens`**：两者互斥。因为思考已关闭，`max_tokens=512` 只限制回答本身，够三句话；如果以后改成开思考，或换成 `kimi-k3` 这类把思维链计入 `max_tokens` 的模型，要改用 `max_completion_tokens`，否则回答会被思维链吃光变成空串。
- **不传 `service_tier`**：Plan 入口传 `fast` 会 400。
- **不用 `stop` / `logprobs` / `frequency_penalty`**：思考模型不支持前两者，Seed 1.8+ 不支持 penalty。`temperature`/`top_p` 在 `doubao-seed-2-0-lite-260215` 上是固定值、传了也被忽略，所以没传。
- **重试策略**：`openai` SDK 的 `max_retries` 设 0，自己按方舟 `error.code` 判别——`RateLimitExceeded.*`、`*RateLimitExceeded`、`ServerOverloaded`、`RequestBurstTooFast`、`InternalServiceError` 与网络错误做指数退避（起始 1.5s，上限 30s，最多 6 次；限流请求不计费可放心重试）；400 参数类不重试记为该文件失败；上文致命错误码停整批。程序判别只看 `error.code`，不解析 `message`。
- **并发默认 2**：Medium 档官方只说「满足正常开发需求的 TPM，建议同时 1–2 个项目」，没有公开 RPM/TPM 数值。开太大只会撞 429 然后退避，并没有更快。
- **超长笔记**：模型上下文 256k，脚本按 120,000 字符保守截断并告警，避免撞上限。
- **幂等 / 原子写**：目标文件已存在且比源文件新就跳过（`--force` 覆盖）；先写 `.tmp` 再 `replace`，中断不会留下半截文件。
- **可追溯**：每个请求带 `X-Client-Request-Id` 头，并写进摘要文件顶部的 HTML 注释（含实际 `model`、token 数、估算 AFP），方便和控制台用量明细对账（明细有 0.5–1 天延迟）。
- **Plan 入口没有的能力**：`/tokenization`、`/context/create`、`/files`、`/models`、`/batch/chat/completions` 在 `/api/plan/v3` 下都是 404 或未开放，所以脚本没用批量推理接口或分词接口——批量推理（Job / Batch Chat）只在标准 `/api/v3` 入口、按量后付费，正是要避开的。

## 需要你知道的两件事

1. **使用条款风险（重要）**：火山方舟 Agent Plan 文档明确写着文本生成 / 向量化模型「**不可用于 API 调用**」，仅面向 AI 编程 / Agent 工具内使用，在非 AI 工具场景直调「可能被识别为滥用，导致订阅停用或账号封禁」（图片 / 视频 / 语音模型才是官方允许 API 直调的）。技术上 `/api/plan/v3/chat/completions` 用专属 Key 直调是 200（已实测），这是**条款**限制而非接口限制。本脚本满足了你的需求，但请自行评估风险：控制批量规模、不要拿它做高频生产流水线；如果这批笔记量很大或要长期跑，更稳的做法是走标准 `/api/v3` + 方舟 API Key + `doubao-seed-2-0-lite-260428`（按量后付费，1M 输入 token 约 0.6 元），或者用 Coding Plan / Agent Plan 支持的 AI 工具（Claude Code / OpenCode 等）来跑。
2. **版本不可锁**：Plan 入口把 `doubao-seed-2.0-lite` 解析到哪个日期版本由方舟侧决定（2026-09-04 实测为 `260215`），会随时间变化；脚本只校验前缀，实际版本记录在每个摘要文件头部。

## 本次未做真实调用

按任务要求没有 API Key，脚本未对真实接口跑过；上述「已实测」结论来自 skill 的 2026-09-04 Agent Plan Medium 验证记录。已用 mock 客户端覆盖：请求形态（model / thinking.disabled / system role / max_tokens / 自定义头）、限流重试、`QuotaExceeded` 与 401 即时停批、模型漂移停批、400 不重试、幂等重跑、AFP 预算停批；`--dry-run`、缺 Key、错 Base URL 三个守卫也已跑过。
