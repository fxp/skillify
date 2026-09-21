# 查询与 metadata 过滤

> 整理自 `guides/search/search-overview`、`guides/search/semantic-search`、`guides/search/filter-by-metadata`、`guides/search/full-text-search`、`guides/index-data/indexing-overview`、`guides/manage-data/target-an-index`，以及 OpenAPI 规范。抓取于 2026-09-21，**未经真实调用验证**。

## 目录

- [先选检索方式](#先选检索方式)
- [怎么定位到要查询的索引（host vs 名字）](#怎么定位到要查询的索引)
- [Vectors API：POST /query](#vectors-api-post-query)
- [Records API：index.search（可传文本或向量）](#records-api-indexsearch)
- [Documents API：index.documents.search 与 score_by](#documents-api-indexdocumentssearch-与-score_by)
- [metadata 过滤操作符（MongoDB 风格）](#metadata-过滤操作符mongodb-风格)
- [text-match 过滤操作符（Documents API 专属）](#text-match-过滤操作符documents-api-专属)
- [容易搞反的两个细节](#容易搞反的两个细节)

## 先选检索方式

官方决策树（转录自 `search-overview`，未实测但是纯逻辑判断，可信度较高）：

1. 查询词和数据共享具体 token（型号、报错信息、代码、专有名词）→ **全文检索**（BM25，仅 Documents API）。
2. 自然语言、语义/同义词匹配比精确用词更重要 → **语义检索**（dense vector）。
3. 同一份数据既要关键词又要语义信号 → **混合检索**（见 `hybrid-search-and-inference.md`）。
4. 你自己上游产出了稀疏向量表示（如 `pinecone-sparse-english-v0`）→ **sparse-vector 检索**。

## 怎么定位到要查询的索引

数据面请求打索引专属的 `host`（不是固定域名，也不是索引名字拼出来的 URL）：

```python
host = pc.describe_index("my-index").host   # 建议缓存，避免每次都现查
index = pc.Index(host=host)
```

⚠ 文档原文，未实测：也可以 `pc.Index(name="my-index")` 让 SDK 内部自动解析 host，但生产环境官方推荐显式传 `host` 以减少一次控制面往返。

## Vectors API: POST /query

```python
resp = index.query(
    namespace="example-namespace",
    vector=[0.1, 0.2, ...],          # 长度必须等于索引 dimension
    sparse_vector={"indices": [...], "values": [...]},  # 仅 dense+sparse 混合索引需要，见 hybrid 文档
    top_k=10,
    filter={"genre": {"$eq": "documentary"}},
    include_values=False,   # 默认 False，省 egress
    include_metadata=True,
)
# resp.matches[i].id / .score / .values / .metadata
# resp.usage.read_units
```

也可以传 `id=` 而不是 `vector=`，用某条已存在记录本身作为查询向量。

## Records API: index.search

```python
resp = index.search(
    namespace="example-namespace",
    query={"inputs": {"text": "What is a vector database?"}, "top_k": 3,
           "filter": {"document_id": "document1"}},
    fields=["chunk_text"],
)
# 集成 embedding 索引才能传 inputs.text；传向量则用 query.vector
```

可选 `rerank` 参数做集成重排，见 `hybrid-search-and-inference.md`。

## Documents API: index.documents.search 与 score_by

Documents API 的核心心智模型：一次请求**只能选一种排序信号**，用 `score_by` 显式指定类型：

```python
resp = index.documents.search(
    namespace="reviews",
    top_k=10,
    score_by=[{"type": "text", "fields": ["review_text"], "query": "civilization"}],
    # 其它 type 可选值：
    #   "dense_vector"  -> 需要 "fields" + "values"（浮点数组，不是 "query"）
    #   "sparse_vector" -> 需要 "fields" + "sparse_values"（{indices, values} 对象）
    #   "query_string"  -> Lucene 语法，"query" 是字符串
    filter={"category": {"$eq": "science-fiction"}},
    include_fields=["*"],  # 省略/空 = 不返回任何字段；["*"] = 返回全部
)
# resp.matches[i]._id / ._score / 具体 include_fields 请求的字段
```

**每个 `score_by` clause 必须带 `type`**，缺失会 400（⚠ 文档原文，未实测报错格式）。`type: "text"` 支持多字段（多个 clause 或一个 clause 多个 `fields`），服务端会把多字段 BM25 分数合并成一个排序，`2026-07` 版本里每个字段权重相等，没有单独的权重参数。

## metadata 过滤操作符（MongoDB 风格）

三套 API 通用（Documents API 额外支持 text-match 操作符，见下一节）：

| 操作符 | 作用 | 支持类型 |
|---|---|---|
| `$eq` | 等于 | number, string, boolean |
| `$ne` | 不等于 | number, string, boolean |
| `$gt` / `$gte` | 大于 / 大于等于 | number |
| `$lt` / `$lte` | 小于 / 小于等于 | number |
| `$in` | 在数组内（最多 10,000 个值） | string, number |
| `$nin` | 不在数组内（最多 10,000 个值） | string, number |
| `$exists` | 字段存在 | number, string, boolean |
| `$and` | 逻辑与 | - |
| `$or` | 逻辑或 | - |
| `$not` | 取反包裹的子句 | - |

**语法规则**：

- 顶层可以列多个字段（隐式 AND），或用 `$and`/`$or` 显式组合子句。
- **顶层不能出现裸比较操作符**：`{"$gt": 5}` 非法，必须嵌在字段名下：`{"year": {"$gt": 2019}}`。
- 字符串数组类型的 metadata 值（如 `"genre": ["comedy", "documentary"]`）表示该字段**同时取多个值**；`{"genre": "comedy"}` 或 `{"genre": {"$in": [...]}}` 都能匹配到含该值的数组，但 `{"$and": [{"genre": "comedy"}, {"genre": "drama"}]}` 这种要求单个字段同时等于两个不同字面量的写法**不会匹配**（AND 是对同一个逻辑判断取交集，不是"数组包含这两个值")。
- `{"genre": ["comedy", "documentary"]}`（不带任何操作符直接传数组）和 `{"genre": {"$eq": [...]}}` 都是**非法查询**，会编译报错（⚠ 文档原文，未实测具体报错）。

## text-match 过滤操作符（Documents API 专属）

只对声明了 `full_text_search` 的 `string` 字段生效，用在 `filter` 里（不是 `score_by`）：

| 操作符 | 作用 |
|---|---|
| `$match_phrase` | 字段包含该短语（按顺序） |
| `$match_all` | 字段包含全部给定 token（顺序不限） |
| `$match_any` | 字段包含任意一个给定 token |

```python
index.documents.search(
    namespace="reviews", top_k=5,
    score_by=[{"type": "dense_vector", "fields": ["review_embedding"], "values": query_embedding}],
    filter={"review_text": {"$match_phrase": "beautifully written"}},
)
```

这是官方文档里"最常见的混合检索模式"：用 text-match filter 先圈定候选范围，再用 dense_vector 排序，一次请求、一次计费（见 pricing-and-limits.md）。不支持在**删除**请求的 filter 里用 text-match 操作符（`documents.delete` 的 filter 只接受标准操作符）。

## 容易搞反的两个细节

1. **`score_by: "text"` 是 OR 语义，不是短语匹配**：`{"type": "text", "fields": ["body"], "query": "machine learning"}` 会匹配包含 "machine" 或 "learning" 任意一个词的文档（BM25 按匹配程度打分），**不要求**两个词都出现、更不要求相邻。想要精确短语，用 `filter` 里的 `$match_phrase`，或者 `score_by: "query_string"` 配合 Lucene 语法写 `body:("machine learning")`。
2. **`AND`/`OR`/`NOT`/`*`/`~`/`^` 这些操作符只在 `score_by: "query_string"`（Lucene 语法）里生效**；用在 `score_by: "text"` 里会被当成字面词去做 token 匹配（不报错，只是查询结果很可能不是你想要的）。`query_string` 对无引号的多词查询默认也是 OR（`body:(machine learning)` 匹配任一词），要求同时出现需要显式 `AND` 或 `+`。

`top_k` 上限 10,000，单次查询返回体最大 4 MB（超限的具体行为未实测确认，⚠）。
