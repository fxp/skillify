# 本地代码库 RAG 问答（智谱 embedding-3 + glm-5.3，纯 requests）

脚本只有一个文件：`code_rag.py`，两个子命令：`index`（切片 + 向量化 + 落盘）和 `ask`（检索 + 生成，支持流式输出和多轮交互）。

## 先说最重要的两个注意事项

### 1. Coding Plan 的额度大概率**不覆盖 embedding-3**

GLM Coding Plan 是面向 Claude Code / Cline / OpenCode 这类编码工具的包月套餐，走的是专用端点：

- OpenAI 兼容：`https://open.bigmodel.cn/api/coding/paas/v4`
- Anthropic 兼容：`https://open.bigmodel.cn/api/anthropic`

据我所知，这个套餐只包含 GLM 对话模型（glm-4.5/4.6/5 系列等），**embedding 模型不在套餐范围内**，需要走通用端点 `https://open.bigmodel.cn/api/paas/v4` 并按量付费（embedding-3 本身很便宜，一个中等规模仓库一般只需几毛到几块钱）。所以脚本默认把两类请求拆开：

| 请求 | 默认 base url | 环境变量 |
|---|---|---|
| `/chat/completions`（glm-5.3） | `https://open.bigmodel.cn/api/coding/paas/v4` | `ZHIPU_CHAT_BASE_URL` |
| `/embeddings`（embedding-3） | `https://open.bigmodel.cn/api/paas/v4` | `ZHIPU_EMBED_BASE_URL` |

**请务必在智谱控制台核实**：(a) 你的 Coding Plan 当前是否已把 embedding 纳入；(b) 通用端点账户里是否有余额。如果第一次 `index` 报 401/403 或余额不足，就是这个原因。如果官方后来把 embedding 也放进了 coding 端点，把 `ZHIPU_EMBED_BASE_URL` 改成 coding 端点即可，代码不用动。

另外 Coding Plan 的 key 和普通开放平台 key 通常是同一个账号下的同一把 key，脚本用一个 `ZHIPU_API_KEY` 同时打两个端点；如果你的情况不同，改一下 `_headers()` 即可。

### 2. 模型名和接口细节请以官方文档为准

我是凭记忆写的接口格式（`Authorization: Bearer <key>`、`POST /embeddings` 带 `model/input/dimensions`、`POST /chat/completions` 带 `messages/stream/thinking`），这些和智谱 v4 接口的 OpenAI 兼容风格一致，但没有真实联网验证。尤其是：

- `glm-5.3` 这个模型名，如果接口返回 "model not found"，用 `ZHIPU_CHAT_MODEL` 换成控制台里实际可用的名字。
- `thinking` 参数：脚本默认**不传**（用服务端默认），`--thinking on/off` 才会带上 `{"thinking": {"type": "enabled"|"disabled"}}`。如果报参数错误就去掉。
- embedding-3 的 batch 上限和单条 token 上限，我按保守值（每批 16 条、每段 ≤ 3000 字符）设置，可在文件顶部的常量里调。

## 安装与使用

```bash
pip install requests numpy
export ZHIPU_API_KEY="你的 key"

# 1) 建索引（增量：内容没变的文件直接复用旧向量，不重新扣费）
python code_rag.py index /path/to/your/repo --index ./myrepo.index

# 2) 单次提问
python code_rag.py ask --index ./myrepo.index "用户登录的 token 是在哪里签发和校验的？"

# 3) 交互模式（多轮，保留最近 3 轮问答历史）
python code_rag.py ask --index ./myrepo.index
```

常用选项：

- `index --rebuild`：忽略旧索引全量重建（换 embedding 模型/维度时会自动全量重建）。
- `index --ext .tf --ext .proto`：额外纳入的扩展名。
- `ask --top-k 12`：检索的片段数（默认 8）。
- `ask --path 'src/api/*'`：只在匹配路径的文件里检索，缩小范围。
- `ask --show-chunks`：先打印命中的文件/行号和相似度，方便判断检索是否靠谱。
- `ask --thinking off`：关闭深度思考，回答更快；`on` 则强制开启。
- 环境变量 `ZHIPU_EMBED_DIM`：embedding-3 支持 256/512/1024/2048 维，默认 1024（够用且省存储）。

## 工作原理

**索引阶段（`index`）**

1. `os.walk` 遍历仓库，跳过 `.git/node_modules/venv/dist/build` 等目录、lock 文件、压缩产物、二进制和 >1MB 的文件；按扩展名白名单收文件（常见语言 + md/yaml/json 等配置文档）。
2. 按行切片：每段 60 行、相邻段重叠 10 行；单段超过 3000 字符（例如一行巨长的压缩文件）再按字符硬切。每段记录 `file / start / end / text`。
3. 向量化时把 `文件: 路径 (第 x-y 行)` 前缀拼进文本，这样 "xxx 模块在哪" 这类按路径问的问题也能命中。
4. 每批 16 段调用 `/embeddings`，对 429/5xx 做指数退避重试；按返回的 `index` 字段回填，避免乱序。
5. 落盘到索引目录：`meta.json`（chunks + 每个文件的 sha1）和 `vectors.npy`。再次 `index` 时，sha1 没变的文件直接复用旧向量，只对改动过的文件重新向量化。

**问答阶段（`ask`）**

1. 把问题用同一个 embedding-3 向量化（维度自动跟索引对齐）。
2. 向量全部 L2 归一化后做一次矩阵乘法得到余弦相似度，取 top-k（可选路径过滤）。几万段规模纯 numpy 毫秒级，不需要向量数据库。
3. 把片段按 `[片段 n] 文件:起-止行` 的格式拼进 user 消息（总字符数受 `--max-context-chars` 限制，默认 24000），system prompt 要求模型只依据片段作答、引用文件路径和行号、没检索到就明说。
4. 用 `stream=True` 调 `/chat/completions`，逐行解析 SSE（`data: {...}` / `data: [DONE]`），`reasoning_content` 用灰色打印、`content` 正常打印。
5. 多轮模式下历史里只保留"问题 + 回答"，不重复塞代码片段，省 token。

## 已知局限与可改进的方向

- **切片是按行的，不是按语法结构的**。对 Python/JS 这类语言，一个函数可能被切成两半。想更精准可以用 `tree-sitter` 按函数/类切，接口不用变，只改 `chunk_file`。
- **纯向量检索对精确标识符不敏感**（比如问一个很生僻的函数名）。可以加一路关键词检索（BM25，或者简单地 `grep` 问题里的标识符）再和向量结果合并，这是最划算的提升。
- 没有 rerank。如果检索质量不够，可以把 top-k 放大到 30，再让 glm 先做一轮"哪些片段相关"的筛选。
- 索引不会自动感知文件删除后残留——每次 `index` 都是按当前目录重新生成 chunks 列表，删掉的文件自然不会出现，这点是没问题的；但索引目录本身不要放进仓库里被再次索引。
- 大仓库首次索引会打很多次 embedding 请求，如果遇到 QPS 限流，脚本会自动退避重试；也可以把 `EMBED_BATCH_SIZE` 调大一点（前提是不超过官方单次上限）。
