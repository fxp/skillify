# volcengine-ark skill · 价值评测（GLM-5.3 基准）

## 口径声明

**本报告只包含由 GLM-5.3 作为执行 Agent 产出的实验。** 早期用 Claude 模型执行的轮次已从本报告中删除，不作为本基准的任何依据——执行器不同的结果不可合并统计。

- **执行 Agent**：GLM-5.3。Claude Code CLI 仅作 harness，`ANTHROPIC_BASE_URL` 指向智谱 `…/api/anthropic`，配 GLM Coding Plan Key。
- **判分**：100% 由脚本真实执行火山方舟 Agent Plan 决定。判分标准开跑前冻结于 `glm-round/PROTOCOL.md`。
- **对照**：两侧都能 WebFetch 查官方文档，唯一差异是有没有读 `volcengine-ark` 技能。
- **账号限制**：测试账号只有 **Agent Plan 个人版 Medium**，没有标准方舟 Key、未订阅 Coding Plan，本轮只测 Plan 入口能覆盖的能力。

| 指标 | 值 |
| :--- | :--- |
| 场景数 | 3 |
| 总运行次数 | 30 |
| 统计显著优势（Fisher 双尾 p < 0.05） | **0 / 3** |
| 技能领先但不显著 | 2 / 3 |
| 技能略落后 | 1 / 3（场景设计失误，见下） |
| 实测查出并修正的文档 / SDK 错误 | 8 |

---

## 一句话结论

**三个场景没有一个达到统计显著。** 技能版在两个场景上领先、一个场景略落后，
但 n=5 撑不起 5/5 vs 2/5 这种差距的显著性。这是本平台在 GLM-5.3 口径下的真实结果，
和 bigmodel（4/8 显著）、autodl（1/3 显著）放在一起看才公平。

## 总表

| 场景 | n | skill | baseline | 满分率 | Fisher 双尾 p |
| :--- | :-: | :--- | :--- | :--- | :--- |
| `plan-embeddings-shape` | 5 | **1.000 ± 0.000** | 0.650 ± 0.300 | 5/5 vs 2/5 | 0.1667 |
| `kimi-max-tokens-empty` | 5 | **1.000 ± 0.000** | 0.900 ± 0.122 | 5/5 vs 3/5 | 0.4444 |
| `anthropic-entry-model-pinning` | 5 | 0.950 ± 0.100 | **1.000 ± 0.000** | 4/5 vs 5/5 | 1.0000 |
| 合并 | — | — | — | 14/15 vs 10/15 | 0.1686 |

**看到结果之后没有加样本量。** 按当前比例，`plan-embeddings-shape` 需要 n≥8 才可能到 p<0.05
（8/8 vs 3/8 → p=0.026）——但那是事后追加样本，属于 p-hacking，本轮不做。

原始数据在 `glm-round/`，逐轮复盘见 `glm-round/RESULTS.md`。

---

## `plan-embeddings-shape`：领先最多，但仍不显著

Plan 入口做**纯文本**向量化的坑有两层，开跑前用探针确认过：

1. **能用的模型只有 `doubao-embedding-vision`**（含带日期的 `-251215`）。最自然的三个名字
   `doubao-embedding-text` / `doubao-embedding` / `doubao-embedding-large` **全部 404 `UnsupportedModel`**。
   给纯文本做向量化却必须用一个叫 "vision" 的模型。
2. **两个端点响应形状不同**：`/embeddings` 返回 `data` 是数组、`dimensions:1024` 生效；
   `/embeddings/multimodal` 返回 `data` 是**对象**、维度固定 **2048**。抄错端点会拿到 2048 维。

skill 版 5/5 满分。baseline 5 次里 2 次满分、3 次踩坑（一次拿不到任何向量、一次崩在响应形状上、一次拿到 2048 维）。

## `kimi-max-tokens-empty`：坑真实存在，但 baseline 大多躲过去了

`kimi-k3` 的 `max_tokens` **把思维链算进去**——`max_tokens:64` 时 `finish_reason: "length"`、
`content: ""`、reasoning 61 token，返回 200 没有任何错误。开跑前探针复现无误。

skill 版 5/5 满分。baseline 5 次里 3 次也正确（改用 `max_completion_tokens` 或放大预算），2 次拿到空结果。

## `anthropic-entry-model-pinning`：场景设计失败，如实记录

这个场景本想测 Anthropic 入口的静默路由——不指定模型时传 `claude-sonnet-4-5` 返回 200
但被**静默换成 `doubao-seed-2-1-turbo-260628`**（抵扣系数 2.5）。探针确认这个行为真实存在。

但结果是 **baseline 5/5 全部正确锁定了模型**。原因很清楚：**我在任务描述里就把答案写进去了**
——"必须确保实际服务的模型就是 `doubao-seed-2.0-lite`"。被明确点名的模型，谁都会显式传。
坑要触发，前提是用户**没有**说该用哪个模型。

按区分度配方复盘，这个场景违反了第 ② 条（正确答案不应出现在任务本身里）。
**这是出题失误，不是技能失效。** 技能那次失分（run-4 确实没做回显核对）也是真实的。

---

## 评分器的一次自我纠错（如实记录）

`anthropic-entry-model-pinning` 一开始判成 **skill 0.800 输给 baseline 0.950**，
技能版 4/5 都栽在"脚本自己核对了回显模型"这一项。查下来是评分器的问题：

技能版写的是先归一化再比对——`matched = (served_family == expected_family)`，
还打印了比对结论并在不一致时报警。而我的 AST 判据只认**字面含 `model`** 的比较节点，
变量取名叫 `served_family` 就漏检了。**判的是变量取名，不是行为**，漏判的恰恰是更严谨的写法。

放宽到一组模型相关标识符后两侧对称重判：技能版 0.800 → 0.950，
**baseline 也从 0.950 涨到 1.000**（run-3 同样受益）。修正后技能仍略落后，上表就是修正后的结果。

修正的口径始终一致：**只有当判分项在测量形式（用了哪个流、变量怎么取名、有没有某个子串）而不是结果时才改**，
改完两侧一起重判，涨跌都如实记录。

---

## 文档 / SDK 修正（8 条）

这些是只读文档抓不到、只有真实调用（或真实装一次 SDK）才会暴露的东西，全部已回写进 skill，
影响面最大的几条升到永远加载的 `SKILL.md`「跨领域通用规则」一层。基于 2026-09-04 用真实 Agent Plan Key 做的约 45 次实测（`verification-findings.md`、`verification-log.jsonl`）。

| 位置 | 文档 / 控制台怎么说 | 实测是什么 |
|---|---|---|
| SKILL.md 通用规则、agent-plan.md、models.md | 控制台模型列表列出 `Model Name: auto`，暗示可以直接填 | 直填 `model: "auto"` 返回 `404 UnsupportedModel`。要用 Auto 路由必须填 `ark-code-latest` 并在控制台选 Auto |
| SKILL.md 通用规则、models.md | 文档未提及 | Plan 入口**接受**带日期的 Model ID，但静默按 Name 路由：传 `doubao-seed-2-0-lite-260428` 返回 200，实际服务的是 `-260215`。确认版本只能看响应里的 `model` |
| SKILL.md 通用规则、tools-setup.md、errors-and-limits.md | 文档未提及 | Anthropic 协议入口把 `claude-*` 模型名静默路由到 `doubao-seed-2-1-turbo-260628`（抵扣系数 2.5）。Claude Code 忘设 `ANTHROPIC_MODEL` 时不报错，只是悄悄按 2.5 系数烧 AFP |
| embeddings-speech.md、sdk-and-compat.md、models.md | 「兼容 OpenAI SDK」页称"向量化能力模型不支持 OpenAI API" | Plan 入口 `POST /embeddings`（OpenAI 形态）可用；只是 `input` 只收字符串，多模态数组返回 400 |
| embeddings-speech.md、models.md | 维度写法三处不一（1024 / 2048 / 3072） | 两条路默认都是 **2048**，`dimensions: 1024` 生效；`/embeddings/multimodal` 的响应是 `data.embedding` **单个对象**而非数组 |
| image-video.md、agent-plan.md | 套餐表给 Medium 勾了视频模型，正文却说 Small/Medium 不支持视频 | 正文对：Medium 建视频任务返回 `404 UnsupportedModel` |
| image-video.md | 图片 `size` 档位沿用旧版 `1K` | `doubao-seedream-5.0-lite` 对 `1K` 返回 `400 size must be one of 'WIDTHxHEIGHT', '2k', '3k', or '4k'` |
| SKILL.md 通用规则、management-api.md、errors-and-limits.md | skill 初稿按 SDK 命名惯例写了 `ARKApi().get_afp_usage(...)` | 本机核实 `volcengine-python-sdk` 5.0.48 的 `ARKApi` 只有 17 个方法，**没有**这些，照抄会 `AttributeError`。必须走 `UniversalApi(...).do_call(...)` |

另外两条已写进 reference：`service_tier: "fast"` 在 **Agent Plan** 入口返回的报错文案却是
`fast service tier does not support coding plan`；`/api/plan/v3` 下 `/models`、`/tokenization`、
`/context/create`、`/files` 全部 404，套餐用户拿不到这四类能力。

---

## 触发描述优化

用 skill-creator 的 `run_loop.py` 跑了 3 轮（20 条查询，10 触发 / 10 近似误触，每条 3 次）。
结论：**保留原描述**——两个改写版在留出集上都没超过原版。三轮精确率都是 100%、召回率 6-17%，
即模型经常自己直接作答而不去查 skill。

> ⚠️ **这批触发数据不可信。** 后续在 bigmodel 轮次里发现该 harness 存在结构性缺陷
> （正面对照组在"每个请求都必须调用"的描述下仍读到 0%），触发率数字一律作废。
> 保留结论"保留原描述"只是因为没有相反证据，不构成正面依据。

---

## 边界与未解决的问题

- **0 个显著场景**。技能在两个场景上方向正确但样本量不够；一个场景是我出题失误。
- baseline 有 4 次运行首轮在 900 秒预算内没交付脚本（`exit 124` 超时，日志显示卡在反复抓官方文档）。
  以**完全相同的 900 秒预算**重跑后全部补齐。值得注意的是这 4 次全在 baseline 侧——
  没有说明书就得花更多时间查文档，这个不对称本身可能与实验条件相关。
- **待补**：拿到标准方舟 API Key 后补测 `/api/v3`（Model ID 精确匹配、`/context`、`/files`、
  `/tokenization`、Batch、Bot、Anthropic 兼容入口）；拿到 AK/SK 后补测管控面；
  订阅 Coding Plan 后验证 `/api/coding/v3` 的套餐内行为。
- n=5，场景由我设计，选题偏差存在。结论只针对 GLM-5.3 这一个执行器，不外推。
