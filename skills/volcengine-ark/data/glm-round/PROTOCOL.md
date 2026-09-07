# volcengine-ark · GLM-5.3 执行轮 · 协议（开跑前冻结）

## 口径

- **执行 Agent**：GLM-5.3。Claude Code CLI 仅作 harness，`ANTHROPIC_BASE_URL` 指向智谱 `…/api/anthropic`，配 GLM Coding Plan Key。
- **被测平台**：火山方舟 Agent Plan（个人版 Medium），入口 `https://ark.cn-beijing.volces.com/api/plan/v3` 与 Anthropic 协议入口 `…/api/plan/v1/messages`。
- **对照**：两侧都能 WebFetch 查官方文档；唯一差异是 `with_skill` 先读 `volcengine-ark/SKILL.md` 及其 references，`without_skill` 被明确禁止读取该目录与任何 `.skill` 文件。
- **n = 5**，每场景每配置 5 次，共 3 × 2 × 5 = **30 次运行**。
- **判分 100% 由脚本真实执行决定**。Agent 写代码时**不调用 API**（环境里没给它 Key），由评分器统一用真实 Key 执行并按下面的冻结标准判分。

## 场景与冻结判分标准

### 1. `anthropic-entry-model-pinning`

**任务**：在方舟 Agent Plan 上用 **Anthropic 协议**入口写一个脚本，成本敏感，必须确保**实际服务的模型就是指定的 `doubao-seed-2.0-lite`**，脚本跑完要打印实际服务的模型名并核对。

**踩的坑**（实测 B11）：Anthropic 入口传 `model: "claude-sonnet-4-5"` 返回 **200**，但被**静默路由到 `doubao-seed-2-1-turbo-260628`**（抵扣系数 2.5）。不报错、不警告，账单静默翻倍。

| # | 判分项 | 通过条件 |
| :-: | :--- | :--- |
| 1 | 无未捕获异常 | stdout+stderr 无 `Traceback` |
| 2 | 真的打印了服务端回显的模型名 | stdout 出现 `doubao-seed-` 开头的实际模型名 |
| 3 | **实际服务模型确实是 lite 而不是被静默换掉的 turbo** | stdout 含 `doubao-seed-2-0-lite`，且**不含** `doubao-seed-2-1-turbo` |
| 4 | 脚本自己做了核对而不是只打印 | 代码里出现对回显 model 的比较/断言（AST 或文本检出比较逻辑） |

### 2. `kimi-max-tokens-empty`

**任务**：用 `kimi-k3` 写一个短文本情感分类脚本，输出必须很短、要控制成本，把输出上限压到 64 token 以内；**但必须真的拿到分类结果**。

**踩的坑**（实测 C7）：`kimi-k3` 的 `max_tokens` **把思维链算进去**——`max_tokens: 64` 时 `finish_reason: "length"`、`content: ""`、reasoning 61 token。返回 200，没有任何错误，只是答案是空的。改用 `max_completion_tokens`（去掉 `max_tokens`）才正常。

| # | 判分项 | 通过条件 |
| :-: | :--- | :--- |
| 1 | 无未捕获异常 | 无 `Traceback` |
| 2 | **真的拿到了非空的分类结果** | stdout 出现非空的分类标签（正面/负面/中性 或 positive/negative/neutral 之一） |
| 3 | 没有把空回答当成功 | 不存在"打印了空 content 却宣称完成"的情况：若 stdout 含 `finish_reason` 为 `length` 且分类结果为空则判失败 |
| 4 | 脚本检查了 `finish_reason` | 代码中出现 `finish_reason` |

### 3. `plan-embeddings-shape`

**任务**：用方舟 Agent Plan 给三段文本做向量化，**维度要 1024**，打印每条向量的实际长度。

**踩的坑**（开跑前 2026-09-07 重新探针确认，两层）：

1. **模型名**：Plan 入口能做向量化的**只有 `doubao-embedding-vision`**（含带日期的 `-251215`）。
   最自然的三个名字 `doubao-embedding-text` / `doubao-embedding` / `doubao-embedding-large`
   **全部 404 `UnsupportedModel`**。给纯文本做向量化却必须用一个叫 "vision" 的模型，
   这既不直觉、官方文档也没在 Plan 语境下列出来。
2. **端点形状**：`POST /api/plan/v3/embeddings` 返回 `data` 是**数组**、`dimensions: 1024` 生效；
   而 `POST /api/plan/v3/embeddings/multimodal` 返回 `data` 是**对象**、维度固定 **2048**。
   抄错端点会拿到 2048 维并在取 `data[0]` 时 `TypeError`。

另外文档称"向量化不支持 OpenAI API"，但 Plan 入口的 OpenAI 形态实测 200——文档与实际相反。

| # | 判分项 | 通过条件 |
| :-: | :--- | :--- |
| 1 | 无未捕获异常 | 无 `Traceback` |
| 2 | 真的拿到了向量 | stdout 打印出了向量长度（1024 或 2048） |
| 3 | **维度确实是 1024**（没走成 2048 维的 multimodal 端点） | stdout 含 `1024` 且不含 `2048` |
| 4 | 三段文本都处理了 | stdout 中 `1024` 出现 ≥ 3 次 |

> 判分项在**开跑前**据探针结果调整过一次（原稿的"没有错误地断言平台不支持"改成"三段都处理了"，
> 因为 `UnsupportedModel` 已并入维度判定）。此后冻结，跑完不改。

## 事前声明

- 判分标准以本文件为准，跑完不再修改。若发现评分器 bug，修正后**全部重判**并在报告中如实记录。
- 平台侧 5xx 抖动不改判分标准，按实际结果计入并在报告注明。
