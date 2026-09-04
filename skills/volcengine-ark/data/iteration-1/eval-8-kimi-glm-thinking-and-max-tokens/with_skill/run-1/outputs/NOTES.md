# NOTES — kimi-k3 vs glm-5.3 code review 对比脚本

文件：`code_review_compare.py`（依赖 `requirements.txt`：`openai>=1.40`）。未做真实调用；`--dry-run` 可查看实际发出的请求参数。

## 入口 / Key / 模型名（三者必须配套）

| 项 | 取值 | 为什么 |
|---|---|---|
| Base URL | `https://ark.cn-beijing.volces.com/api/plan/v3` | Agent Plan 的 OpenAI 兼容入口。**不能**用 `/api/v3`（会从后付费余额扣钱且 Plan Key 直接 401），也不能用 `/api/coding/v3`。 |
| Key | 环境变量 `ARK_AGENT_PLAN_API_KEY` | Agent Plan 控制台第 3 步的「专属 API Key」，与方舟 API Key 不通用。脚本只从 env 读，缺失时给出明确提示退出。 |
| `model` | `kimi-k3`、`glm-5.3` | Plan 入口用小写 Model Name（无日期）。响应里的 `model` 字段会回显实际服务版本，脚本把它打印为 `served`。kimi-k3 需要 Medium 及以上档位。 |
| role | 只用 `system` / `user` | Plan 入口对 `developer` role 返回 400。 |

## 输出长度怎么限（"300 token 左右"）

两个模型都在 system prompt 里被要求"回答 ≤ 300 token、每条一行、不要复述代码"，这是软控制；硬控制按模型分别处理：

### kimi-k3
- 实测事实：kimi-k3 **把思维链算进 `max_tokens`**——`max_tokens: 64` 时 `finish_reason: "length"`、`content: ""`，思维链吃光额度、回答为空。
- 因此脚本**绝不传 `max_tokens`**，只传 `max_completion_tokens`（= 回答 + 思维链总预算，二者互斥不能同传）：`300（回答）+ 1500（思维链预算）= 1800`。
- 回答本身约 300 token 主要靠 prompt 约束；对比表里用 `completion_tokens - reasoning_tokens` 单独算出"回答 token"，方便核对是否守住了 300 左右。
- 兜底：若仍出现 `finish_reason == "length"` 且回答为空（思维链过长），脚本把 `max_completion_tokens` 翻倍重试一次（`KIMI_MAX_ATTEMPTS = 2`），再失败则报错并提示调大 `KIMI_REASONING_BUDGET`。

### glm-5.3
- `reasoning_effort: "low"` 实测 `reasoning_tokens: 0`、无 `reasoning_content`，所以预算几乎全归回答，直接 `max_completion_tokens: 300`。
- 同样使用 `max_completion_tokens` 而不是 `max_tokens`，是因为在开思考的模型上 `max_tokens` 口径各家不一致（豆包不含思维链、kimi 含），统一用总预算参数更可预测。

## 思维链怎么控

### glm-5.3（用户要求：不要思维链，直接给结论）
- glm-5.3 默认开思考且**不支持关闭**：`thinking: {"type": "disabled"}` → 400 `thinking.type disabled is not supported by this model`；`reasoning_effort: "none"` → 400 `reasoning_effort none is not supported by this model`。脚本里两者都没有用，代码注释中特别标注了不要加回去。
- 实测唯一有效的"事实上关掉思考"写法是 **`reasoning_effort: "low"`**（返回 `reasoning_tokens: 0`）。`reasoning_effort` 是 openai SDK 原生参数，直接作为 kwarg 传，不需要 `extra_body`。
- 因为没有思维链，输出就是结论本身，满足"直接给结论"。

### kimi-k3（用户未要求关思考）
- 保留默认的深度思考（`thinking` 字段不传；kimi-k3 上 `thinking.disabled` 的行为未经实测，所以不去碰它）。
- 思维链在 `choices[0].message.reasoning_content`（方舟私有字段，用 `getattr` 取），默认不打印，加 `--show-reasoning` 才显示。
- 思维链 token 在 `usage.completion_tokens_details.reasoning_tokens`，对比表单列一行。

## 其他实现要点
- 两个模型并发调用（`ThreadPoolExecutor`），互不影响：一个失败另一个仍会输出。
- 单例 `OpenAI` client，`max_retries=2`（SDK 对 429 / 5xx 指数退避），`timeout` 默认 300 s（思考模型可 `--timeout` 加大）。
- 错误按方舟的 `error.code` 汇总（不解析 message 做判断），并带上 `x-request-id` 便于提工单。常见：`401 AuthenticationError`（用错 Key / 入口）、`404 UnsupportedModel`（套餐档位不含该模型，如 Small 档调 kimi-k3）、`429 QuotaExceeded`（5 小时 / 周 / 月额度耗尽）。
- `temperature=0.2` 让两次评审更可比。
- `--json` 输出结构化结果（含 served model、finish_reason、各类 token、耗时、思维链原文）。

## 注意
- AFP 抵扣系数：kimi-k3 为 10、glm-5.3 为 4.5，二者都**不支持超额后付费**，额度耗尽时请求失败而不是扣余额。
- 官方口径：Agent Plan 的文本模型"不可用于 API 调用"，在 AI 工具之外直连 `/api/plan/v3` 有被判滥用、停用订阅的风险。脚本是按用户要求写的，但请在自己的风险判断下使用。
- kimi-k3 上 `reasoning_effort` 的映射未经实测，因此没有拿它来压缩 kimi 的思维链；如需进一步省额度，可以自行试 `reasoning_effort: "low"` 并看 `reasoning_tokens`。
