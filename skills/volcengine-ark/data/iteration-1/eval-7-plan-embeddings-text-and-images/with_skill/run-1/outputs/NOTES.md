# NOTES — 火山方舟 Agent Plan 向量化：为什么这样写

## 1. 入口 / Key / 模型名（配错不是报错，而是扣错钱或 401）

| 项 | 取值 | 原因 |
|---|---|---|
| Base URL | `https://ark.cn-beijing.volces.com/api/plan/v3` | Agent Plan 专属入口，路径里必须含 `/plan`。控制台原话「请勿使用 `…/api/v3`，接入会产生额外费用」。 |
| API Key | 环境变量 `ARK_AGENT_PLAN_API_KEY` | Agent Plan 控制台「使用配置 → 第 3 步 配置专属 API Key」，一个账号只有一把。**与方舟 API Key / Coding Plan Key 不通用**：实测 Agent Plan Key 打 `/api/v3` 或 `/api/coding/v3` 直接 `401 AuthenticationError`。 |
| `model` | `doubao-embedding-vision`（小写 Model Name） | Plan 入口用 Model Name 而不是带日期的 Model ID；服务端解析到 `doubao-embedding-vision-251215`（响应 `model` 字段会写出来，代码把它记进 `meta.json`）。 |

OpenAI SDK 只需改 `base_url` + `api_key`，鉴权仍是 `Authorization: Bearer <KEY>`。

## 2. 为什么文本和图片都走 `POST /embeddings/multimodal`，不用 `client.embeddings.create`

Plan 入口两条向量化路径都实测存在，但形态不同：

| 路径 | `input` | 响应 | 备注 |
|---|---|---|---|
| `POST /embeddings`（OpenAI 形态） | **只收字符串**（传多模态数组 → `400 InvalidParameter: input[0] expected a string`） | `data[0].embedding`（数组） | `client.embeddings.create()` 走的就是它 |
| `POST /embeddings/multimodal`（方舟原生） | `[{"type":"text","text":…}, {"type":"image_url","image_url":{"url":…}}]` | **`data.embedding`，`data` 是单个对象不是数组**（`object` 字段虽写 `list`） | OpenAI SDK 没有对应方法 |

选择全部走 multimodal 的三个理由：

1. 截图必须走 multimodal，OpenAI 形态根本收不了图片。
2. 官方反复要求同一向量库的 Query 与 Corpus「固定同一版本、请勿混用」；两条路径的 `instructions` 支持情况不同（`/embeddings` 上是否生效未实测），文本走 A、图片走 B 会让文本向量和图片向量不在同一"指令空间"里，跨模态检索质量没有保证。
3. 检索效果靠 `instructions`（见 §4），该参数只在 multimodal 路径有文档保证。

实现上仍然用 `openai.OpenAI` 客户端，靠 `client.post("/embeddings/multimodal", cast_to=object, body=…)` 直接打这个路径：SDK 会把相对路径拼到 `base_url` 后（得到 `/api/plan/v3/embeddings/multimodal`），`cast_to=object` 返回原始 JSON dict。这样 base_url / Bearer 头 / 超时 / 代理都由 SDK 统一管理，不必再引 `requests`。

### 响应解析

```json
{"id":"…","model":"doubao-embedding-vision-251215","object":"list",
 "data":{"object":"embedding","embedding":[…]},
 "usage":{"prompt_tokens":20,"total_tokens":20,
          "prompt_tokens_details":{"text_tokens":20,"image_tokens":0}}}
```

代码按 `resp["data"]["embedding"]` 取值，并保留 `data` 为列表时取 `data[0]["embedding"]` 的兜底（文档另一处这样描述过）。

### 一次请求只放一个元素

multimodal 接口把整个 `input[]` **融合成一条向量**（这就是为什么 `data` 是单对象），不是"N 个输入 → N 个向量"。所以每个笔记块 / 每张图各发一次请求；没有批量 endpoint，`build_index.py` 用线程池并发（默认 4）。

## 3. 维度：1024 vs 2048

- `dimensions` 只允许 `1024` 或 `2048`，两条路径默认都是 **2048**（文档里出现过的 3072 是过期示例，实测不存在）。
- 本项目默认 **1024**（`ARK_EMBED_DIMENSIONS` 或 `--dimensions` 可改为 2048）：本地笔记库几千条以内，1024 维存储与点积开销减半，也是官方 Agent Plan 向量化配置（OpenViking `"dimension": 1024`）用的值。要更高精度就建库时选 2048。
- 维度、模型版本一旦建库就不能改：`meta.json` 记录 `dimensions` 与 `model`，`search.py` 会以同一维度请求查询向量，并在服务端模型版本漂移时告警提示重建。

## 4. `instructions`（直接影响召回质量）

官方加粗警告「请勿直接使用系统默认值」，模板里 `{}` 以外的固定文字不能改。本项目是"底库同时有独立的文本样本和图片样本，用文本提问"的跨模态问答场景，按官方给的现成配置：

| 侧 | instructions |
|---|---|
| Query（用户问题） | `Target_modality: text/image.\nInstruction:根据这个问题，找到能回答这个问题的相应文本或图片\nQuery:` |
| Corpus 文本块 | `Instruction:Compress the text into one word.\nQuery:` |
| Corpus 图片 | `Instruction:Compress the image into one word.\nQuery:` |

`Target_modality` 由**底库**模态决定，与 Query 自身模态无关；`text/image` 表示底库里有独立的文本样本和图片样本两类。如果以后只搜文本，把 Query 侧改成 `Target_modality: text.` 并重建索引。

## 5. 相似度与归一化

文档定义「余弦相似度 = 向量 L2 归一化后做点积」，但没说返回向量是否已归一化，所以代码在入库和查询时都自己做一次 L2 归一化，`vectors.npy` 里存的是归一化后的 float32，检索就是一次 `matrix @ q`。跨模态相似度绝对值偏低是正常现象（官方示例文搜图最佳匹配约 0.65），不要拿文本-文本的阈值去卡图片结果。

## 6. 图片输入

- 走 `data:image/png;base64,…` 内联（本地文件没有公网 URL）。限制：单张 < 10 MB，Base64 请求体 ≤ 64 MB，宽高各 > 14 px，**扩展名 / MIME 必须与真实格式一致**——代码按魔数校验，避免把 jpg 改名成 png 后被拒。不合规的图片在收集阶段被跳过并打印 `[skip]` 警告，不会中断整库构建（配置 / 额度类错误才会中止）。
- 图片 token 大约 `min(宽×高/784, 1312)`，一张普通截图约几百到 1312 token。

## 7. 错误处理与重试

客户端 `max_retries=0`，重试逻辑自己写，以便区分：

| 情况 | 处理 |
|---|---|
| 429 `RateLimitExceeded.*` / `ModelAccount*RateLimitExceeded` / `AccountRateLimitExceeded` / `ServerOverloaded` / `RequestBurstTooFast` | 指数退避 + 抖动重试（起始 1.5 s，最多 5 次）；限流请求不计费 |
| 429 `QuotaExceeded`（Agent Plan 5 小时 / 周 / 月额度耗尽） | **不重试**，直接中止建库并提示等 `reset_time` 或开「超额后付费」（向量化模型支持超额后付费，开了会自动切后付费、无需改配置） |
| 401 | 不重试，提示 Key 与入口不配套 |
| 404 `UnsupportedModel` | 不重试，提示 model 必须是套餐内 Model Name |
| 5xx / 网络 / 超时 | 有限次重试 |

建库过程中任何不可恢复错误会取消剩余任务且**不写盘**，避免留下半成品索引。

## 8. 用量 / 费用

Agent Plan 向量化按 AFP 抵扣，系数 0.5：`AFP = (text_tokens + image_tokens) × 0.5 / 10000`。`build_index.py` 结束时按响应 `usage.prompt_tokens_details` 打印本次估算值。向量化受 5 小时 / 周 / 月三档额度约束（Medium 档：10,000 / 35,000 / 100,000 AFP），几百条笔记 + 几张图通常不到 1 AFP。

## 9. 合规提示（务必知悉）

Agent Plan 官方口径：文本生成模型与**向量化模型「不可用于 API 调用」**，仅允许在 AI 工具（OpenClaw / OpenViking / Claude Code 等）内使用；技术上 `/api/plan/v3/embeddings*` 用专属 Key 直调是 200，但这是使用条款而非接口限制，在非 AI 工具场景大量直调有被判滥用、订阅停用的风险。本项目是个人本地小体量笔记检索，请自行评估；若要完全合规或大规模使用，改用标准后付费入口：`base_url=https://ark.cn-beijing.volces.com/api/v3`、`api_key=$ARK_API_KEY`（方舟 API Key，需先在「开通管理」开通模型）、`model=doubao-embedding-vision-251215`（带日期 Model ID），代码里只需改这三处常量；标准入口 `/api/v3/embeddings/multimodal` 的请求 / 响应形态与文档一致，但未在本次验证中实测。

## 10. 未实测项（写在这里以免误以为已验证）

- 本仓库代码在无 Key 环境下编写，只用 `httpx.MockTransport` 做了离线联调（URL 拼接、响应解析、重试分支、建库 → 检索流程），**没有打过真实 API**。
- `instructions` / `encoding_format` 在 Plan 入口 multimodal 路径上的行为依据文档；参数表来自标准入口文档，Plan 入口只实测过 `model` / `input` / `dimensions`。
- 标准 `/api/v3` 与 Coding Plan `/api/coding/v3` 的向量化路径未实测。

参考：火山方舟文档站 `www.volcengine.com/docs/82379`（向量化 API、Agent Plan 接入向量化模型、错误码表），以及本 skill 2026-09-04 在 Agent Plan Medium 套餐上的真实 API 验证记录。
