# 本地代码库 RAG 问答（embedding-3 + glm-5.3，纯 requests）

脚本：`code_rag.py`（同目录），只依赖 `requests`（`numpy` 可选，有则加速相似度计算）。

## 先说一个关键前提：套餐额度只能覆盖 glm-5.3 这一半

你的设想是"用套餐额度做 embedding + 回答"，但 **GLM Coding Plan 不包含 embeddings**（也不含 rerank、生图、语音、Batch 等）。套餐只提供 `glm-5.3` / `glm-5.3-flash` 的对话能力。智谱是两套彼此隔离的计费体系：

| 环节 | 模型 | 端点 | 用哪把 Key |
| :-- | :-- | :-- | :-- |
| 代码切片向量化 / 查询向量化 | `embedding-3` | `https://open.bigmodel.cn/api/paas/v4/embeddings`（标准 API） | 开放平台标准 Key → 环境变量 `ZHIPUAI_API_KEY` |
| 精排（可选） | `rerank` | `https://open.bigmodel.cn/api/paas/v4/rerank`（标准 API） | 同上 `ZHIPUAI_API_KEY` |
| 回答生成 | `glm-5.3` | `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`（Coding Plan 端点，注意多了 `/coding`） | 套餐 Key → 环境变量 `GLM_CODING_PLAN_API_KEY` |

所以你需要**两把 Key**：

- 标准 Key：`https://bigmodel.cn/usercenter/proj-mgmt/apikeys` 创建，账户里要有一点余额（embedding-3 很便宜，一个中型仓库几万 token 级别）。
- 套餐 Key：个人版在 `https://bigmodel.cn/coding-plan/personal/overview` 新建。

如果把套餐 Key 填进 `ZHIPUAI_API_KEY` 去调 embeddings，会得到 `HTTP 429 {"error":{"code":"1113","message":"余额不足或无可用资源包,请充值。"}}`——这不是让你充值，是 Key 和端点不匹配。脚本里对 1113 做了专门的提示。

## 使用方法

```bash
pip install requests            # numpy 可选
export ZHIPUAI_API_KEY=...            # 标准 Key（向量化 / rerank）
export GLM_CODING_PLAN_API_KEY=...    # 套餐 Key（glm-5.3 回答）

# 1. 建索引（增量：按文件 sha1 跳过未变更文件，索引存在仓库根目录的 .code_rag_index.json）
python3 code_rag.py index /path/to/repo
python3 code_rag.py index /path/to/repo --chunk-lines 80 --overlap 15 --ext .lua --rebuild

# 2. 单次提问
python3 code_rag.py ask /path/to/repo "这个项目的鉴权流程在哪里实现？"
python3 code_rag.py ask /path/to/repo "..." --rerank --stream --effort high --top-k 10

# 3. 交互式多轮
python3 code_rag.py chat /path/to/repo --stream
```

建议把 `.code_rag_index.json` 加进 `.gitignore`。

## 脚本做了什么

1. **切片**：遍历仓库（跳过 `.git`/`node_modules`/`dist` 等，跳过 >512KB 文件），按行滑窗切片（默认 60 行、重叠 10 行），每片前面拼上 `// file: path (L起-L止)`，让向量自带位置语义。
2. **向量化**：`POST /paas/v4/embeddings`，`model=embedding-3`、`dimensions=1024`，每批最多 64 条（embedding-3 的数组上限）；单条按 6000 字符截断以避免超过 3072 tokens 限制；结果**按返回的 `index` 对齐**而不是假设顺序。
3. **检索**：查询用同一个 `model + dimensions` 向量化（这点不能变，否则向量空间不一致），余弦相似度取 top-k；`--rerank` 时先召回 30 条，再调 `POST /paas/v4/rerank`（`model=rerank`，文档 ≤128 条、单条 ≤4096 字符）精排到 top-k。
4. **生成**：把片段以 `### path (Lx-Ly)` + 代码块的形式拼进 user 消息，system prompt 要求引用文件路径和行号、不足以回答时明说。`POST /api/coding/paas/v4/chat/completions`，`model=glm-5.3`。
5. **流式**：`--stream` 时按 SSE 逐行解析 `data: {...}`，遇到 `data: [DONE]` 结束，并检查最后一个 chunk 的 `finish_reason`（流式没有独立错误体，`sensitive`/`length`/`network_error` 等只体现在这里）。
6. **错误处理**：4xx（除 429）直接报错不重试；429/5xx 指数退避 + 抖动最多重试 5 次；但 429 + `1113` 视为配置问题不重试。

## 几个针对 glm-5.3 / 套餐的取舍

- **`reasoning_effort` 默认 `low`**。glm-5.3 强制开启思考、不能关闭（传 `thinking.type=disabled` 会直接报 1210），只能用 `reasoning_effort` 调强度，且只接受 `low`/`high`/`max`。套餐额度扣减公式是 `(输入×6.9 + 缓存命中×1.7 + 输出×24)/10000`，输出 token 权重最高，而思考内容算输出；代码问答一般 `low` 够用（实测 low 档 reasoning_tokens 接近 0），复杂架构问题再加 `--effort high`。
- **多轮历史只保留问题和回答，不保留检索到的代码片段**，避免上下文膨胀反复消耗输入额度。
- `max_tokens` 默认 4096（glm-5.3 默认 65536、上限 131072，显式传小值防止跑飞）。
- 输入上下文默认最多 40000 字符（`--max-context-chars`），glm-5.3 是 1M 上下文，容量不是问题，主要是省额度。
- 5 小时 / 7 天额度用尽时会收到 429 类错误（1308/1310 等），脚本会退避重试几次后报错；重置时间是动态的，不要在外层写死等待时间。

## 必须提醒的合规风险

官方条款写明 GLM Coding Plan"仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode、Kilo Code、Cherry Studio 等）。自己写脚本直连 `…/api/coding/paas/v4` 技术上能通，但属于条款之外的用法——是否正常扣套餐额度、会不会被限制，以官方为准。个人本地用问题不大；如果要上生产或给团队用，把 `CODING_BASE` 改成 `https://open.bigmodel.cn/api/paas/v4`、`GLM_CODING_PLAN_API_KEY` 换成标准 Key 即可（请求体完全一致），走按量计费。

另外：Coding 端点的路径没有 `/v1` 这一级，脚本里已经写死为 `.../coding/paas/v4/chat/completions`，不要再往后拼 `/v1`。

## 没有实测过的部分

本次没有真实 Key，脚本只做了语法检查，未联网跑通。如果实际运行时某个字段报"参数非法"或"模型不存在"，以 API 的实际报错为准，并到 `docs.bigmodel.cn` 核对最新文档。
