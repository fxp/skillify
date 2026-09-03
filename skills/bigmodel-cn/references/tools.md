# 文本处理与检索类工具

本文覆盖智谱开放平台（bigmodel.cn）面向文本处理、语义检索、文档解析、联网信息获取与内容安全的工具类 API：文本嵌入、重排序、分词器、文档解析（GLM-OCR）、网络搜索、网页阅读、内容安全审核。

- **Base URL**：`https://open.bigmodel.cn/api/`（下文 Endpoint 均为相对该 Base 的 path）
- **鉴权**：所有请求头需携带 `Authorization: Bearer <API_KEY>`，API Key 在 [智谱开放平台 API Key 管理页](https://bigmodel.cn/usercenter/proj-mgmt/apikeys) 获取

---

### 文本嵌入 Embeddings

**Endpoint**: `POST /paas/v4/embeddings`

**用途**: 使用 GLM Embedding 系列模型将文本转换为高维向量表示，用于语义相似度计算与语义检索（RAG 的基础环节）。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| model | string | 是 | 无 | `embedding-3` 或 `embedding-2` |
| input | string 或 string[] | 是 | 无 | 输入文本，支持单条字符串或字符串数组。`embedding-2` 单条请求最多 512 tokens，数组总长度不超过 8K tokens；`embedding-3` 单条最多 3072 tokens，数组最多 64 条 |
| dimensions | integer | 否 | `embedding-3` 默认 2048，`embedding-2` 固定 1024 | 输出向量维度。仅 `embedding-3` 支持自定义，可选 `256`、`512`、`1024`、`2048` |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/embeddings \
  -H "Authorization: Bearer $BIGMODEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "embedding-3",
    "input": ["智谱开放平台提供大模型 API 服务", "如何进行语义检索"],
    "dimensions": 1024
  }'
```

```python
import requests

resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/embeddings",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "embedding-3",
        "input": ["智谱开放平台提供大模型 API 服务", "如何进行语义检索"],
        "dimensions": 1024,
    },
)
print(resp.json())
```

**示例响应**

```json
{
  "model": "embedding-3",
  "object": "list",
  "data": [
    {"index": 0, "object": "embedding", "embedding": [0.0123, -0.045, "..."]},
    {"index": 1, "object": "embedding", "embedding": [0.0087, 0.021, "..."]}
  ],
  "usage": {"prompt_tokens": 18, "completion_tokens": 0, "total_tokens": 18}
}
```

**注意事项**

- `data` 数组中每个元素的 `index` 对应输入数组的下标，注意结果顺序与输入顺序一致但仍建议按 `index` 对齐，不要假设返回顺序。
- 向量维度一旦确定（写入向量库时），后续查询必须使用同一 `model` + `dimensions` 组合，否则向量空间不一致、检索结果失真。
- 超过单条/数组长度限制会报错，长文本需提前分段（chunking）后再调用。

---

### 文本重排序 Rerank

**Endpoint**: `POST /paas/v4/rerank`

**用途**: 接收查询文本（query）与候选文本列表（documents），计算每条候选文本与查询的相关性得分并排序，用于提升检索精排效果，常见于智能问答、信息检索场景。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| model | string | 是 | 无 | 固定为 `rerank` |
| query | string | 是 | 无 | 查询文本，最大长度 4096 字符 |
| documents | string[] | 是 | 无 | 候选文本数组，最多 128 条，单条最大长度 4096 字符 |
| top_n | integer | 否 | `0`（返回全部） | 返回得分最高的前 n 条结果 |
| return_documents | boolean | 否 | `false` | 是否在结果中返回原始文本 |
| return_raw_scores | boolean | 否 | `false` | 是否返回原始分数 |
| request_id | string | 否 | 平台自动生成 | 请求唯一标识，6-64 字符，建议用 UUID |
| user_id | string | 否 | 无 | 终端用户唯一 ID |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/rerank \
  -H "Authorization: Bearer $BIGMODEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "rerank",
    "query": "智谱开放平台的 API Key 在哪里获取",
    "documents": [
      "API Key 可在用户中心的项目管理页面获取",
      "智谱提供文本、图像、视频等多模态大模型",
      "开放平台支持 Function Call 与知识库检索"
    ],
    "top_n": 2,
    "return_documents": true
  }'
```

```python
import requests

resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/rerank",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "rerank",
        "query": "智谱开放平台的 API Key 在哪里获取",
        "documents": [
            "API Key 可在用户中心的项目管理页面获取",
            "智谱提供文本、图像、视频等多模态大模型",
            "开放平台支持 Function Call 与知识库检索",
        ],
        "top_n": 2,
        "return_documents": True,
    },
)
print(resp.json())
```

**示例响应**

```json
{
  "id": "20250901xxxxxx",
  "results": [
    {"index": 0, "document": "API Key 可在用户中心的项目管理页面获取", "relevance_score": 0.93},
    {"index": 2, "document": "开放平台支持 Function Call 与知识库检索", "relevance_score": 0.41}
  ],
  "usage": {"prompt_tokens": 56, "total_tokens": 56}
}
```

**Rerank 与 Embeddings 如何配合使用**

典型 RAG 检索分两阶段：先用 embeddings 做**召回**（在向量库中做近似最近邻搜索，快但精度有限，通常召回 top 20-50 条），再用 rerank 做**精排**（对召回结果重新计算 query 与每条候选文本的相关性，取 top_n 条送入模型上下文）。两者结合能显著降低"看似相关但实际不匹配"的召回噪声，是提升 RAG 答案质量的常见组合。

**注意事项**

- `results` 中的 `index` 对应输入 `documents` 数组的下标，用于回溯原文档，`return_documents=true` 时也会直接带上原文本。
- rerank 只做相关性打分，不做语义向量生成，不能替代 embeddings 做首轮召回，二者定位不同。
- 候选文本条数与单条长度均有硬性上限（128 条 / 4096 字符），超长文本需先分段。

---

### 文本分词器 Tokenizer

**Endpoint**: `POST /paas/v4/tokenizer`

**用途**: 将文本按指定模型的分词规则切分为 token 并返回数量，用于文本长度评估、模型输入预估、对话上下文截断、费用计算等场景。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| model | string | 是 | `glm-5.2` | 计算分词所依据的模型代码，如 `glm-5.2`、`glm-4.6`、`glm-4.5` 等 |
| messages | array | 是 | 无 | 对话消息列表，结构与 chat/completions 一致（`system`/`user`/`assistant`），不能只包含 system 或 assistant 消息 |
| tools | array | 否 | 无 | 模型可调用的工具定义（Function Call 等），最多 128 个，会计入 token 统计 |
| request_id | string | 否 | 平台自动生成 | 请求唯一标识，6-64 字符 |
| user_id | string | 否 | 无 | 终端用户唯一 ID |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/tokenizer \
  -H "Authorization: Bearer $BIGMODEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-4.6",
    "messages": [
      {"role": "user", "content": "帮我总结一下这段文本的核心内容"}
    ]
  }'
```

```python
import requests

resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/tokenizer",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "glm-4.6",
        "messages": [{"role": "user", "content": "帮我总结一下这段文本的核心内容"}],
    },
)
print(resp.json())
```

**示例响应**

```json
{
  "id": "20250901xxxxxx",
  "usage": {
    "prompt_tokens": 12,
    "video_tokens": 0,
    "image_tokens": 0,
    "total_tokens": 12
  }
}
```

**注意事项**

- 该接口不生成回复内容，只做分词计数，`usage` 是唯一有效字段；不要拿它当作 chat/completions 的替代品。
- 不同模型的分词规则不同，估算某模型的调用成本或上下文占用时应传入与实际调用一致的 `model`。
- 传入多模态内容（图片/视频）时会分别统计 `image_tokens`、`video_tokens`，便于精细化估算多模态调用成本。

---

### 文档解析（GLM-OCR）

**Endpoint**: `POST /paas/v4/layout_parsing`

**用途**: 使用 GLM-OCR 模型解析图片或 PDF 文档的版面布局并提取文本内容，返回 Markdown 格式全文、详细布局信息（文本/表格/公式/图片位置及内容），可用于文档结构化预处理，是 RAG 流程中"文档解析"环节的常用能力。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| model | string | 是 | 无 | 固定为 `glm-ocr` |
| file | string | 是 | 无 | 需要识别的图片或 PDF，支持 `url` 或 `base64`。支持格式 PDF/JPG/PNG；单图 ≤10MB，PDF ≤50MB，最多 100 页 |
| return_crop_images | boolean | 否 | `false` | 是否返回各元素的截图信息 |
| need_layout_visualization | boolean | 否 | `false` | 是否返回带标注的布局可视化图片 |
| start_page_id | integer | 否 | 无 | PDF 起始解析页码（从 1 开始） |
| end_page_id | integer | 否 | 无 | PDF 结束解析页码 |
| request_id | string | 否 | 平台自动生成 | 请求唯一标识，6-64 字符 |
| user_id | string | 否 | 无 | 终端用户 ID，6-128 字符，用于滥用监控 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/layout_parsing \
  -H "Authorization: Bearer $BIGMODEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-ocr",
    "file": "https://example.com/report.pdf",
    "start_page_id": 1,
    "end_page_id": 5
  }'
```

```python
import requests

resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/layout_parsing",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "glm-ocr",
        "file": "https://example.com/report.pdf",
        "start_page_id": 1,
        "end_page_id": 5,
    },
)
print(resp.json())
```

**示例响应**

```json
{
  "id": "20250901xxxxxx",
  "created": 1756789000,
  "model": "glm-ocr",
  "md_results": "# 报告标题\n\n正文内容...\n\n| 列1 | 列2 |\n| --- | --- |\n...",
  "layout_details": [
    [
      {"index": 0, "label": "text", "bbox_2d": [0.05, 0.03, 0.9, 0.08], "content": "报告标题"},
      {"index": 1, "label": "table", "bbox_2d": [0.1, 0.2, 0.9, 0.5], "content": "<table>...</table>"}
    ]
  ],
  "data_info": {"num_pages": 5},
  "usage": {"prompt_tokens": 2400, "completion_tokens": 1800, "total_tokens": 4200}
}
```

**注意事项**

- `md_results` 是拼接好的全文 Markdown，适合直接做后续切分（chunking）；`layout_details` 是按页组织的元素级数组，`label` 取值为 `text`/`table`/`formula`/`image`，`bbox_2d` 是归一化坐标（0-1）。
- `table` 元素的 `content` 是 HTML 表格字符串而非纯文本，做切分时要注意区分处理，避免破坏表格结构。
- PDF 页数超过限制或超过 `end_page_id` 范围会报错，大文档建议分批调用（配合 `start_page_id`/`end_page_id`）。
- `need_layout_visualization=true` 会返回标注图片 URL，便于人工核对解析准确性，但会增加响应体积，生产环境按需开启。

---

### 网络搜索 Web Search

**Endpoint**: `POST /paas/v4/web_search`

**用途**: 面向大模型的搜索引擎接口，在传统搜索结果基础上增强了意图识别能力，返回适合 LLM 处理的结构化结果（标题、URL、摘要、网站名、图标等），支持多搜索引擎、时间范围与域名过滤。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| search_query | string | 是 | 无 | 搜索内容，建议不超过 70 字符 |
| search_engine | string | 是 | 无 | `search_std`（智谱基础版）、`search_pro`（智谱高阶版）、`search_pro_sogou`（搜狗）、`search_pro_quark`（夸克） |
| search_intent | boolean | 是 | `false` | 是否先做搜索意图识别，识别到意图后才执行搜索；`false` 则跳过识别直接搜索 |
| count | integer | 否 | `10` | 返回结果条数，1-50；`search_pro_sogou` 仅支持 10/20/30/40/50 |
| search_domain_filter | string | 否 | 无 | 限定返回结果的白名单域名（如 `www.example.com`），支持 `search_std`/`search_pro`/`search_pro_sogou` |
| search_recency_filter | string | 否 | `noLimit` | 时间范围：`oneDay`/`oneWeek`/`oneMonth`/`oneYear`/`noLimit` |
| content_size | string | 否 | 无 | `medium`（摘要，满足常规问答）或 `high`（更详细内容） |
| request_id | string | 否 | 平台自动生成 | 请求唯一标识，6-64 字符 |
| user_id | string | 否 | 无 | 终端用户唯一 ID，6-128 字符 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/web_search \
  -H "Authorization: Bearer $BIGMODEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "search_query": "2025年智谱AI最新发布的模型",
    "search_engine": "search_pro",
    "search_intent": false,
    "count": 10,
    "search_recency_filter": "oneMonth",
    "content_size": "high"
  }'
```

```python
import requests

resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/web_search",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "search_query": "2025年智谱AI最新发布的模型",
        "search_engine": "search_pro",
        "search_intent": False,
        "count": 10,
        "search_recency_filter": "oneMonth",
        "content_size": "high",
    },
)
print(resp.json())
```

**示例响应**

```json
{
  "id": "20250901xxxxxx",
  "created": 1756789000,
  "search_intent": [
    {"query": "2025年智谱AI最新发布的模型", "intent": "SEARCH_ALL", "keywords": "2025 智谱AI 最新模型"}
  ],
  "search_result": [
    {
      "title": "智谱发布新一代 GLM 模型",
      "content": "摘要内容……",
      "link": "https://example.com/news/1",
      "media": "示例媒体",
      "icon": "https://example.com/icon.png",
      "refer": "ref_1",
      "publish_date": "2025-08-20"
    }
  ]
}
```

**何时使用 / 最佳实践**

- 智谱提供三层联网检索能力：① 本接口 `web_search`（直接拿结构化搜索结果，自己决定如何拼接进 prompt）；② `chat/completions` 中通过 `tools: [{"type": "web_search", ...}]` 让模型自动检索并生成带来源标注的回答（意图判断、检索、生成一体化，更省心）；③ 智能体对话（Assistant API）中的 Search Agent，会对复杂问题做 query 拆解、多轮检索并综合生成报告，适合"全面分析报告"类深度问题。三者可按需要的自动化程度和控制粒度选用。
- 四个搜索引擎的能力和计费不同：`search_std` 性价比最高，适合日常查询；`search_pro` 多引擎协同、召回率更高；`search_pro_sogou` 在腾讯生态和知乎内容、百科医疗等垂直领域权威性强；`search_pro_quark` 适合垂直内容精准检索。同时指定 `search_domain_filter` 和 `search_recency_filter` 时 `count` 不生效。
- `search_query` 限长 70 字符，需要检索长问题时应先做 query 改写/摘要再传入。

---

### 网页阅读 Web Reader

**Endpoint**: `POST /paas/v4/reader`

**用途**: 读取并解析指定 URL 的网页内容，提取正文、标题、描述等信息，可控制返回格式、缓存、图片保留与链接/图片摘要选项，常用于把网络搜索结果的链接进一步抓取全文，供模型深入阅读。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| url | string | 是 | 无 | 需要抓取的网页地址 |
| timeout | integer | 否 | `20` | 请求超时时间（秒） |
| no_cache | boolean | 否 | `false` | 是否禁用缓存 |
| return_format | string | 否 | `markdown` | 返回格式，如 `markdown`、`text` |
| retain_images | boolean | 否 | `true` | 是否保留图片 |
| no_gfm | boolean | 否 | `false` | 是否禁用 GitHub Flavored Markdown |
| keep_img_data_url | boolean | 否 | `false` | 是否保留图片的 data URL |
| with_images_summary | boolean | 否 | `false` | 是否包含图片摘要 |
| with_links_summary | boolean | 否 | `false` | 是否包含链接摘要 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/reader \
  -H "Authorization: Bearer $BIGMODEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/article/123",
    "return_format": "markdown",
    "retain_images": false,
    "with_links_summary": true
  }'
```

```python
import requests

resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/reader",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "url": "https://example.com/article/123",
        "return_format": "markdown",
        "retain_images": False,
        "with_links_summary": True,
    },
)
print(resp.json())
```

**示例响应**

```json
{
  "id": "20250901xxxxxx",
  "created": 1756789000,
  "model": "reader",
  "reader_result": {
    "title": "文章标题",
    "description": "文章简要描述",
    "url": "https://example.com/article/123",
    "content": "# 文章标题\n\n正文内容（Markdown 格式）..."
  }
}
```

**注意事项**

- 默认返回 Markdown 格式且保留图片，若只需要纯文本用于拼接 prompt，建议设置 `retain_images=false`、`return_format=text` 以减小体积、节省 token。
- 默认启用缓存（`no_cache=false`），抓取同一 URL 的最新内容时需显式传 `no_cache=true`。
- 常见搭配：先用 `web_search` 拿到候选链接列表，再对最相关的几条链接调用 `reader` 抓取全文，比只用搜索摘要能获得更完整的上下文。

---

### 内容安全审核 Moderation

**Endpoint**: `POST /paas/v4/moderations`

**用途**: 对文本、图片、音频、视频内容进行违规检测，精准识别涉黄、涉暴、违法违规等风险内容，返回结构化审核结果（内容类型、处置建议、风险类型），用于在生成/发布前做内容合规拦截。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| model | string | 是 | `moderation` | 固定为 `moderation` |
| input | string 或 object 或 object[] | 是 | 无 | 待审核内容。可以是纯文本字符串（最长 2000 字符）；或单个多模态对象 `{"type": "text"/"image_url"/"video_url"/"audio_url", ...}`；或多模态对象数组（混合审核文本+图片等）。图片 <10MB，分辨率 20×20 至 6000×6000；视频建议时长 30 秒；音频建议时长 60 秒 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/moderations \
  -H "Authorization: Bearer $BIGMODEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "moderation",
    "input": [
      {"type": "text", "text": "待审核的文本内容"},
      {"type": "image_url", "image_url": {"url": "https://example.com/pic.jpg"}}
    ]
  }'
```

```python
import requests

resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/moderations",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "moderation",
        "input": [
            {"type": "text", "text": "待审核的文本内容"},
            {"type": "image_url", "image_url": {"url": "https://example.com/pic.jpg"}},
        ],
    },
)
print(resp.json())
```

**示例响应**

```json
{
  "id": "20250901xxxxxx",
  "created": 1756789000,
  "result_list": [
    {"content_type": "text", "risk_level": "PASS", "risk_type": []},
    {"content_type": "image", "risk_level": "REVIEW", "risk_type": ["涉黄"]}
  ],
  "usage": {"moderation_text": {"call_count": 1}}
}
```

**何时使用 / 最佳实践**

- `risk_level` 是处置建议，从轻到重依次为 `PASS`（正常放行）、`REVIEW`（可疑，建议人工复核）、`BLOCK`（一般违规，可拦截但不必终止多轮对话）、`REJECT`（违规，拦截并终止对话）、`HIGH`（高危，需拦截并对已生成内容做回撤处理）。业务侧应按此分级设计自动拦截 + 人工复核的流程。
- 该接口是主动审核工具，独立于智谱模型内置的安全审核机制——后者会在 chat/completions 调用时对输入/输出自动检测，命中时返回错误码 `1301`，流式响应中会返回 `finish_reason: "sensitive"`，无需额外调用 moderations 接口。两者可结合使用：内置机制做实时拦截兜底，`moderations` 接口用于对用户生成内容（UGC）、素材库等场景做主动批量审核。
- 建议在请求中携带 `user_id`（6-128 字符）标识终端用户，便于平台对违规用户的行为进行干预、避免企业账号因终端用户滥用受影响；这是 chat 类接口的通用做法，也适用于内容安全体系的整体治理。

---

## RAG 检索增强生成的典型组合拳

自建 RAG（检索增强生成）pipeline 的常见流程是：先用 `layout_parsing`（GLM-OCR）解析 PDF/图片文档拿到结构化 Markdown 全文，按语义或版面边界切分成小段（chunking）；再用 `embeddings` 把每个分段转换为向量并存入向量数据库。检索时，先用同一 `embeddings` 模型把用户 query 转成向量做召回，再用 `rerank` 对召回的候选段落做相关性精排，取 top_n 条拼接进 `chat/completions` 的 prompt，让模型基于这些上下文生成最终答案。

如果不想自建这一整套解析、切分、向量存储、召回、精排的 pipeline，智谱开放平台也提供了托管的知识库服务，可直接上传文档由平台完成检索增强，详见 `references/agents-assistant-knowledge.md`。
