# 混合检索、Pinecone 托管的 embedding 与 rerank

> 整理自 `guides/search/hybrid-search`、`guides/search/hybrid-search/single-index`、`guides/search/reciprocal-rank-fusion`、`guides/search/rerank-results`、`guides/index-data/create-an-index#embedding-models`，以及 OpenAPI 规范 `inference_2026-07.oas.yaml`。抓取于 2026-09-21，**未经真实调用验证**。

## 目录

- ["混合检索"不是单一方法，三种模式选一个](#混合检索不是单一方法三种模式选一个)
- [模式一：Documents API 上的 text-match filter + dense 排序](#模式一documents-api-上的-text-match-filter--dense-排序)
- [模式二：客户端融合（RRF）](#模式二客户端融合rrf)
- [模式三：Vectors API 单索引 dense+sparse（alpha 加权）](#模式三vectors-api-单索引densesparse alpha-加权)
- [Pinecone 托管的 embedding 模型](#pinecone-托管的-embedding-模型)
- [独立调用 embedding：POST /embed](#独立调用-embeddingpost-embed)
- [Rerank：集成 vs 独立调用](#rerank集成-vs-独立调用)
- [Pinecone 托管的 rerank 模型](#pinecone-托管的-rerank-模型)

## "混合检索"不是单一方法，三种模式选一个

文档原文特别提醒："Hybrid" isn't one fixed method——它是"结合关键词信号和语义信号"这个目标的统称，具体实现三选一，且和你的索引属于哪套数据平面强绑定（见 `indexes-and-schemas.md`）：

| 模式 | 怎么工作 | 适用场景 | 所属数据平面 |
|---|---|---|---|
| Filter, then rank | 用 text-match filter（`$match_phrase`/`$match_all`/`$match_any`）圈定候选，再用 dense_vector 排序，一次请求 | 新的文档/文本项目，一个索引一次请求搞定 | Documents API |
| 客户端融合（RRF） | 分别跑关键词检索和语义检索,拿两份排序列表用倒数排名融合 | 两个信号都要参与排序（不只是过滤），两套 API 都能用 | Vectors 或 Documents API |
| 服务端组合（alpha 加权） | 单条 record 同时存 dense+sparse 向量,一次 query 服务端合并 | 已有的向量/records 工作负载 | Vectors API |

⚠ 重要（官方迁移指南 FAQ）：Documents API **没有**"单请求同时按 dense 和 sparse 排序"的组合查询（不同于 Vectors API 的 alpha 加权模式）——要在 Documents API 上融合两个信号，只能用模式一（filter+rank）或模式二（RRF），不能照搬 Vectors API 的单请求思路。

## 模式一：Documents API 上的 text-match filter + dense 排序

```python
index.documents.search(
    namespace="reviews", top_k=5,
    score_by=[{"type": "dense_vector", "fields": ["review_embedding"], "values": query_embedding}],
    filter={"review_text": {"$match_phrase": "beautifully written"}},
)
```

一次请求、一次计费（按 RU，见 pricing-and-limits.md）。这是文档明确推荐的默认混合检索路径。

## 模式二：客户端融合（RRF）

```python
dense_hits = index.documents.search(
    namespace="reviews", top_k=50,
    score_by=[{"type": "dense_vector", "fields": ["review_embedding"], "values": query_embedding}],
)
bm25_hits = index.documents.search(
    namespace="reviews", top_k=50,
    score_by=[{"type": "text", "fields": ["review_text"], "query": "beautifully written"}],
)
# 应用层用 reciprocal rank fusion 合并 dense_hits 与 bm25_hits 的排名（不是分数）
```

RRF 融合的是**排名**（rank position），不是原始分数——这也是为什么它能跨不同量纲的分数体系（BM25 分数和 cosine 相似度分数完全不在一个尺度上）工作。**跑两次查询算两次 RU**（模式一只算一次），成本上要权衡。具体 RRF 公式见官方 `guides/search/reciprocal-rank-fusion`（本 skill 未展开抄录）。

## 模式三：Vectors API 单索引 dense+sparse（alpha 加权）

前提：索引 `vector_type="dense"` 且 `metric="dotproduct"`——**这是唯一支持单索引 dense+sparse 组合查询的 metric 组合**，其它 metric 的索引即便 upsert 时塞进了 `sparse_values` 也会在查询时报错（⚠ 文档原文，未实测报错内容,但明确写了"Upserting such records into an index with a different distance metric will succeed, but querying will return an error"——即写入不报错、查询才报错,是个静默陷阱）。

```python
pc.create_index(name="hybrid-index", vector_type="dense", dimension=1024,
                 metric="dotproduct", spec=ServerlessSpec(cloud="aws", region="us-east-1"))

# upsert 时一条 record 同时带 values（dense）和 sparse_values（sparse）
index.upsert(vectors=[{"id": "vec1", "values": dense_vec,
                        "sparse_values": {"indices": [...], "values": [...]},
                        "metadata": {"text": "..."}}], namespace="ns")

# 查询时同样两者都传
index.query(namespace="ns", top_k=10, vector=dense_query, sparse_vector=sparse_query)
```

**alpha 加权**：Pinecone 本身不提供"dense 权重 vs sparse 权重"的参数——服务端把 dense+sparse 当成一个向量整体处理。要控制两者的相对贡献，得在**发请求前自己缩放向量值**：

```python
def hybrid_score_norm(dense, sparse, alpha: float):
    # combined = alpha * dense + (1 - alpha) * sparse
    hs = {"indices": sparse["indices"], "values": [v * (1 - alpha) for v in sparse["values"]]}
    return [v * alpha for v in dense], hs
```

- `alpha=1.0` 纯 dense（语义）；`alpha=0.0` 纯 sparse（关键词）；`alpha=0.75` 是官方给的"自然语言查询"起点；`alpha=0.25` 适合关键词特异性强的查询（SKU/技术 ID）。**没有普适最优值**，官方建议在自己的标注数据集上试。
- sparse（BM25 风格）分数是无界的（可能到两位数），dense 分数通常在 `[-1,1]` 左右；不做 alpha 归一化时 sparse 分量会主导合并分数。

## Pinecone 托管的 embedding 模型

| 模型 | 类型 | 维度 | 最大序列长度 | 推荐 metric | 备注 |
|---|---|---|---|---|---|
| `multilingual-e5-large` | dense | 1024 | 507 tokens | cosine | 多语言，短查询/中长段落 |
| `llama-text-embed-v2` | dense | 1024（默认，可选 2048/768/512/384） | 2048 tokens | cosine | 长文本/结构化文档表现较好 |
| `pinecone-sparse-english-v0` | sparse | - | 512 或 2048 tokens（`max_tokens_per_sequence` 控制） | dotproduct | 基于 DeepImpact 架构，替代传统 BM25 的学习型稀疏表示 |

共同参数：`input_type`（必填，`"query"` 或 `"passage"`，query/文档要用不同值）；`truncate`（`"END"` 默认截断，`"NONE"` 超长直接报错）。`llama-text-embed-v2` 额外支持 `dimension` 参数覆盖默认输出维度。

## 独立调用 embedding：POST /embed

不建索引，只是想拿向量自己处理时用（比如做集成 embedding 之外的自定义流程,或者单索引 dense+sparse 混合场景里分别生成两种向量,见上方模式三）：

```python
result = pc.inference.embed(
    model="llama-text-embed-v2",
    inputs=["some text to embed"],
    parameters={"input_type": "passage", "truncate": "END"},
)
# result[i].values（dense）或 .sparse_indices/.sparse_values（sparse）
```

响应带 `usage.total_tokens`，按 token 数计费（见 pricing-and-limits.md 的 Embedding 一节）。

## Rerank：集成 vs 独立调用

**集成**（在 Records API 的 `search` 或 Documents API 的 `documents.search` 里传 `rerank` 参数，一次请求内完成"检索 + 重排"）：

```python
ranked = index.search(
    namespace="example-namespace",
    query={"inputs": {"text": "Disease prevention"}, "top_k": 4},
    rerank={"model": "bge-reranker-v2-m3", "top_n": 2, "rank_fields": ["chunk_text"]},
    fields=["category", "chunk_text"],
)
```

`rank_fields` 指定用哪个/哪些字段的文本内容去和 query 比对相关性（大多数模型只支持单字段，见下表"支持字段数"）。

**独立调用**（`POST /rerank`，对任意一批你自己准备好的文档做重排，不依赖 Pinecone 索引）：

```python
result = pc.inference.rerank(
    model="bge-reranker-v2-m3",
    query="The tech company Apple is known for its innovative products like the iPhone.",
    documents=[{"id": "doc1", "text": "..."}, {"id": "doc2", "text": "..."}],
    top_n=2, return_documents=True,
)
# result.data[i].index（原始顺序下标）/ .score（0~1，越接近 1 越相关）/ .document
```

## Pinecone 托管的 rerank 模型

| 模型 | 支持多字段 `rank_fields` | 备注 |
|---|---|---|
| `cohere-rerank-4-fast` | 是（按传入字段顺序排序） | Cohere 最新一代，部署在 Azure AI Global Standard，请求可能被路由到美国以外地区处理 |
| `cohere-rerank-3.5` | 是（按传入字段顺序排序） | **已于 2026-07-01 标记 deprecated；自 2026-08-31 起请求被自动路由到 `cohere-rerank-4-fast` 处理**，两者返回分数不可直接比较，硬编码分数阈值的代码需要重新校准。新代码直接写 `cohere-rerank-4-fast` |
| `bge-reranker-v2-m3` | 否，只支持单个 `rank_fields` | 多语言，适合短查询/中等长度段落（1-2 段） |
| `pinecone-rerank-v0` | 否，只支持单个 `rank_fields` | 最长处理约 512 token（1-2 段） |

（来源：`guides/search/rerank-results#reranking-models` 原文明确写"The bge-reranker-v2-m3 and pinecone-rerank-v0 models support only a single rerank field. cohere-rerank-4-fast and cohere-rerank-3.5 support multiple rerank fields, ranked based on the order of the fields specified."）

Rerank 按请求次数计费（不是按文档数或 token 数，见 pricing-and-limits.md）。
