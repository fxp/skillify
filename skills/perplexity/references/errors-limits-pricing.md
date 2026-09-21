# 错误处理、限流分级、各 API 定价、Embeddings API

⚠ 本文件全部内容整理自官方文档与 OpenAPI 规范，未用真实 Key 调用验证。定价与限流数字抓取于 2026-09-21。

## 目录
- [错误类型与常见状态码](#错误类型与常见状态码)
- [限流：按 API 分级的 usage tier](#限流)
- [定价：五套完全不同的计费形状](#定价)
- [Embeddings API](#embeddings-api)

## 错误类型与常见状态码

官方 Python/TypeScript SDK 提供分类异常：

| 异常类型 | 含义 |
|---|---|
| `APIConnectionError` | 网络连接问题 |
| `RateLimitError` | 触发限流 |
| `APIStatusError` | HTTP 4xx/5xx（用 `.status_code`/`.response` 取细节） |
| `AuthenticationError` | Key 无效或鉴权失败 |
| `ValidationError` | 请求参数不合法 |

```python
import perplexity
from perplexity import Perplexity

client = Perplexity()
try:
    search = client.search.create(query="...")
except perplexity.APIConnectionError as e:
    ...  # 网络问题，e.__cause__ 拿底层异常
except perplexity.RateLimitError as e:
    ...  # 限流，建议指数退避重试
except perplexity.APIStatusError as e:
    print(e.status_code, e.response)
```

**常见 HTTP 状态码**（文档原文）：`400` Bad Request、`401` Authentication、`403` Permission Denied、`404` Not Found、`429` Rate Limit、`5xx` Server Error。⚠ 文档未提供逐 endpoint 的完整错误码/错误体 schema 清单，本 skill 抓取到的具体错误案例只有两处：Anthropic 模型缺 `max_output_tokens` → `400` + `validation failed: max_output_tokens is required when using Anthropic models`（见 `references/agent-api.md`）；取消一个已终结的 Agent response → `400`；重连一个已过期重连窗口的 background 流 → `400`。其余错误体的精确 JSON 形状未文档说明，需要真实调用探测。

**`429` 不计费**：文档原文对 Router API 和 Search API 都明确说明"requests rejected with a `429` are not billed" / "invalid requests, rate-limited requests, and upstream failures are not billed"，可以合理推断对其他 API 同样成立，但仅 Router/Search 两处有明文，⚠ 其余 API 未逐一确认。

**推荐做法**（文档原文）：对 `RateLimitError` 做指数退避重试；不要只看 HTTP 状态码判断成功——Sonar 响应里如果有等价于"业务层错误码"的字段应该额外检查（⚠ 本次抓取未找到 Sonar/Agent API 响应体里业务层错误码字段的具体名字，不同于 wechat/dingtalk 那类"HTTP 200 + errcode"模式的中国平台,本次没有证据显示 Perplexity 这么做,但也未明确排除,标注为待验证项）。

## 限流

**Usage Tier 决定限流档位**，按账号**累计充值总额**（不是当前余额）自动升级，只升不降：

| Tier | 累计充值 |
|---|---|
| Tier 0 | $0（新账号） |
| Tier 1 | $50+ |
| Tier 2 | $250+ |
| Tier 3 | $500+ |
| Tier 4 | $1,000+ |
| Tier 5 | $5,000+ |

限流用漏桶算法（leaky bucket），允许突发但长期严格限速。

### Agent API 限流

同时套用两条独立限制，**都要满足**：API 级 QPS + 该请求所用模型的 RPM（不是从 QPS 反推出来的）。

| Tier | QPS | RPM |
|---|---|---|
| 0 | 1 | 50/min |
| 1 | 3 | 150/min |
| 2 | 8 | 500/min |
| 3 | 17 | 1,000/min |
| 4 | 33 | 4,000/min |
| 5 | 33 | 8,000/min |

### Search API 限流

与账号 usage tier **无关**，所有账号统一：`POST /search` 限速 50 query units/秒，突发容量 50 query units。**注意计费单位和限流单位不同**——见 `references/search-api.md`"计费与限流"一节。

### Sonar API 限流（按 tier、按具体模型分别限速）

| Tier | `sonar-deep-research` RPM | `sonar-reasoning-pro`/`sonar-pro`/`sonar` RPM | `POST /v1/async/sonar` RPM |
|---|---|---|---|
| 0 | 5 | 50 | 5 |
| 1 | 10 | 150 | 10 |
| 2 | 20 | 500 | 20 |
| 3 | 40 | 1,000 | 40 |
| 4 | 60 | 4,000 | 60 |
| 5 | 100 | 4,000 | 100 |

（`GET /v1/async/sonar` 固定 3000/min，`GET /v1/async/sonar/{request_id}` 固定 6000/min，不随 tier 变化。）

### Router API 限流

文档只说明"rate limited，`429` + `Retry-After` header 指示重试间隔"，没有给出具体数字表。⚠ 文档未说明。

### Embeddings API 限流

| Tier | Standard Embeddings QPS | Contextualized Embeddings QPS |
|---|---|---|
| 0 | 85 | 415 |
| 1–3 | 170 | 835 |
| 4–5 | 335 | 1,670 |

**⚠ Contextualized Embeddings 限流按"总 chunk 数"计，不是按请求数**——一个请求里塞多个 chunk 会比多个单 chunk 请求更快触发限流，按"请求数 × 平均耗时"估算容量会不准。

### 触发限流后

响应 `429`，携带重试指示头（`Retry-After`，Router API 文档明确提到）；建议指数退避重试。多数 API 的 `429` 请求不计费（见上）。

## 定价

**五套 API 是五种完全不同的计费形状**，套用其中一种估算另一种的成本会算错：

| API | 计费形状 |
|---|---|
| Router | 纯按 token（无请求费），各模型自己的费率，缓存读取享折扣价，推理 token 按输出价计 |
| Agent API | 按 token（模型价，直接一手厂商价无加价）+ 按工具调用次数（`web_search` $2.5/1K、`fetch_url` $0.5/1K、`people_search`/`finance_search` 各 $5/1K、`sandbox` $0.03/会话——会话是 20 分钟计费窗口不是运行时长上限，内部 SDK 检索另计 $2.5/1K） | 
| Search API | 纯按成功请求数，$5.00/1000 次请求（多查询请求仍算 1 次），无 token 费 |
| Sonar Chat Completions | 按 token（input/output）+ 按请求费（随 `search_context_size` 档位浮动，$5–$22/1000 请求视模型和 Pro Search 而定）+ 仅 `sonar-deep-research` 额外收引用 token/搜索查询/推理 token 三项 |
| Embeddings | 纯按 token，无请求费；standard 和 contextualized 两条模型线独立定价 |

**Cost Examples（文档给出的示例，⚠ 文档原文未实测）**：
- Agent API 用 `openai/gpt-5.2` + 1 次 `web_search`（500 input + 200 output tokens）：input $0.000875 + output $0.0028 + web_search $0.0025 = **$0.006175**
- Agent API `low` preset 代表性运行（2000 input + 1000 output tokens，1 次 `web_search` + 1 次 `fetch_url`）：≈ **$0.007**

每个完成的 response 的 `usage.cost.total_cost` 字段会给出该次请求的实际计算成本，比自己按费率表估算更可靠。

**购买方式**：控制台自助充值（按量付费，无订阅）；AWS Marketplace（合并计费，企业采购）；销售团队联系（定制价格、专属支持、企业功能）。

## Embeddings API

两条模型线，**互不兼容**（向量维度不同，不能混合比较）：

| 用途 | 模型 | 维度 | 价格（$/1M token） |
|---|---|---|---|
| 独立文本（查询、单句） | `pplx-embed-v1-0.6b` | 1024 | $0.004 |
| 独立文本（更大模型） | `pplx-embed-v1-4b` | 2560 | $0.03 |
| 文档分块（同文档 chunk 共享上下文） | `pplx-embed-context-v1-0.6b` | 1024 | $0.008 |
| 文档分块（更大模型） | `pplx-embed-context-v1-4b` | 2560 | $0.05 |

- **Endpoint**：`POST /v1/embeddings`（standard）、`POST /v1/contextualizedembeddings`（contextualized）。
- **⚠ 向量未归一化**：`base64_int8` 编码必须用**余弦相似度**比较；`base64_binary`（打包位）编码必须用**汉明距离**比较。不能用内积或 L2 距离，会得到错误的相似度排序。
- 所有模型用 mean pooling，**不需要指令前缀**，直接喂原始文本即可，不用做"query: "/"passage: "这类 prompt 包装。
- 支持 Matryoshka 降维（`dimensions` 参数：0.6b 模型 128–1024，4b 模型 128–2560），用更小维度换存储/速度。
- **限制**：单请求最多 512 条文本；单条文本最多 32K token；单请求所有文本合计最多 120,000 token；不允许空字符串。

```python
embeddings = client.embeddings.create(
    input=["First sentence.", "Second sentence."],
    model="pplx-embed-v1-0.6b"
)
```

⚠ 本 skill 未展开 Contextualized Embeddings 的具体请求体形状（chunk 分组字段名等），需要文档分块检索场景时读 `/docs/embeddings/contextualized-embeddings` 原文。

## API Key 管理

Key 在控制台生成（`https://console.perplexity.ai/project/keys`），**必须先创建 Project**。⚠ 文档原文警告：Key 只在创建时完整显示一次，关闭页面/丢失响应后无法再次查看完整值，只能撤销重建。

也有编程接口（规范 `openapi-auth.json`）：`POST /generate_auth_token`（用现有 Bearer Key 生成新 token）、`POST /revoke_auth_token`（撤销）。⚠ 本 skill 未展开这两个 endpoint 的完整请求/响应字段，管理面场景（批量轮换 key 等）需要时读 `/docs/admin/api-key-management` 原文。
