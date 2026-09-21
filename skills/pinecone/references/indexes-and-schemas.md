# 建索引：三套数据平面怎么选、怎么建

> 全部内容整理自 `docs.pinecone.io`（`guides/index-data/create-an-index`、`guides/index-data/indexing-overview`、`guides/index-data/adopt-the-documents-api`、`guides/index-data/data-modeling`）与官方 OpenAPI 规范 `db_control_2026-07.oas.yaml`，抓取于 2026-09-21。**未经真实调用验证**，报错文案与字段行为一律标 `⚠ 文档原文，未实测`。

## 目录

- [先选数据平面](#先选数据平面)
- [控制面 Base URL 与鉴权](#控制面-base-url-与鉴权)
- [Vectors API：经典 dimension/metric 索引](#vectors-api经典-dimensionmetric-索引)
- [Records API：集成 embedding 索引](#records-api集成-embedding-索引)
- [Documents API：schema 化索引（2026-07 新增）](#documents-apischema-化索引2026-07-新增)
- [云与区域](#云与区域)
- [相似度 metric](#相似度-metric)
- [索引管理：list/describe/configure/delete](#索引管理)
- [备份与从备份建索引](#备份与从备份建索引)
- [Pod-based 索引（遗留，新客户不可用）](#pod-based-索引遗留新客户不可用)

## 先选数据平面

Pinecone 目前有三套彼此独立、创建后不能互相转换的"索引类型 + 读写 API"组合。选错之后代价很高（不能迁移，只能建新索引重新灌数据），下表是官方迁移指南给出的对照：

| | Vectors API（经典） | Records API（集成 embedding） | Documents API（2026-07 新增） |
|---|---|---|---|
| 建索引 | `pc.create_index(dimension=..., metric=..., vector_type=...)` | `pc.create_index_for_model(embed={"model":..., "field_map":...})` | `pc.indexes.create(schema=SchemaBuilder()...build())` |
| 读写方法 | `index.upsert()` / `index.query()` / `index.fetch()` / `index.update()` / `index.delete()` | `index.upsert_records()` / `index.search()` | `index.documents.upsert()` / `.search()` / `.fetch()` / `.update()` / `.delete()` |
| 数据单元 | record：`id` + `values`(dense)/`sparse_values`(sparse) + 扁平 `metadata` | record：`_id` + 文本字段（自动转向量）+ 其它字段作 metadata | document：`_id` + schema 声明的字段（dense_vector/sparse_vector/full_text_search string）+ 其它字段自动作 metadata |
| 全文检索(BM25) | 不支持 | 不支持 | 支持（`full_text_search` 字段） |
| 单索引混合多信号 | 支持（dense+sparse 单条 record 两个向量，见 hybrid-search-and-inference.md） | 不支持 | 支持（同一 schema 声明 dense_vector + sparse_vector + 多个 full_text_search 字段） |
| 何时用 | 已有外部 embedding 流程、只需要语义或 sparse 检索 | 想让 Pinecone 代管 embedding、不需要全文检索 | 新项目、需要全文检索或单索引多种排序信号 |

⚠ 文档原文，未实测："A request sent to the wrong data-plane API is refused, and the error guides you to the correct API"——具体报错内容未实测确认。

**SDK 语言支持不对称**：Documents API 目前只有 Python SDK（v10+）和 REST 支持；Node.js 等其他语言 SDK 官方文档写"coming soon"（抓取于 2026-09-21，可能已变化）。Records API 和 Vectors API 全语言 SDK（Python/Node/Go/Java）都支持。

## 控制面 Base URL 与鉴权

- 建索引、列索引、删索引、备份、Inference（embed/rerank）等**控制面**操作固定打 `https://api.pinecone.io`。
- 请求头：`Api-Key: <PINECONE_API_KEY>` + `X-Pinecone-Api-Version: <YYYY-MM>`（本文档基于 `2026-07`，见 SKILL.md 关于版本头如何影响 `POST /indexes` 请求体形状的说明）。
- SDK 初始化：`pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])`（Python）；一般会自动带上匹配 SDK 版本的 API 版本头。

## Vectors API：经典 dimension/metric 索引

```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="YOUR_API_KEY")

pc.create_index(
    name="standard-dense-py",
    vector_type="dense",       # 或 "sparse"
    dimension=1536,            # 必须匹配你的 embedding 模型输出维度；sparse 索引不设 dimension
    metric="cosine",           # cosine / dotproduct / euclidean；sparse 索引必须用 dotproduct
    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    deletion_protection="disabled",  # "enabled" 时 DELETE /indexes/{name} 会被拒绝
    tags={"environment": "development"},
)
```

```bash
curl -X POST "https://api.pinecone.io/indexes" \
  -H "Api-Key: $PINECONE_API_KEY" -H "Content-Type: application/json" \
  -H "X-Pinecone-Api-Version: 2025-10" \
  -d '{
    "name": "standard-dense-curl",
    "vector_type": "dense", "dimension": 1536, "metric": "cosine",
    "spec": {"serverless": {"cloud": "aws", "region": "us-east-1"}},
    "deletion_protection": "disabled"
  }'
```

**注意事项**

- `vector_type: "sparse"` 的索引**必须**用 `metric: "dotproduct"`,其它 metric 会被拒绝（⚠ 文档未明确是建索引时报错还是查询时才报错，见 verification-plan.md）。
- `dimension` 和 `metric` 一旦创建**不可修改**,选错只能删了重建（删除会丢数据,先 backup）。
- `dimension` 要和你选用的 embedding 模型输出维度严格一致,不一致时的报错内容⚠未实测。
- 索引创建是异步的,`status.ready` 变 `true` 前不能写入/查询,SDK 惯用轮询：`while not pc.describe_index(name).status.ready: time.sleep(2)`。
- `spec.serverless` 与 `deployment.deployment_type: "managed"` 在 2026-07 控制面下是等价写法,SDK 帮你转换;直接调 REST 时字段名以 API 版本头对应的规范为准。

## Records API：集成 embedding 索引

不想自己管 embedding 模型时用这套。`embed.field_map` 声明你 upsert 时哪个字段名是要转向量的原始文本；`embed.model` 从 [Pinecone 托管模型列表](hybrid-search-and-inference.md#pinecone-托管的-embedding-模型) 里选。

```python
pc.create_index_for_model(
    name="integrated-dense-py",
    cloud="aws", region="us-east-1",
    embed={"model": "llama-text-embed-v2", "field_map": {"text": "chunk_text"}},
)
```

```javascript
await pc.createIndexForModel({
  name: 'integrated-dense-js',
  cloud: 'aws', region: 'us-east-1',
  embed: { model: 'llama-text-embed-v2', fieldMap: { text: 'chunk_text' } },
  waitUntilReady: true,
});
```

```bash
curl -X POST "https://api.pinecone.io/indexes/create-for-model" \
  -H "Api-Key: $PINECONE_API_KEY" -H "Content-Type: application/json" \
  -H "X-Pinecone-Api-Version: 2025-10" \
  -d '{"name":"integrated-dense-curl","cloud":"aws","region":"us-east-1",
       "embed":{"model":"llama-text-embed-v2","field_map":{"text":"chunk_text"}}}'
```

**注意事项**

- `field_map` 里的 key（示例中的 `"text"`）是 Pinecone 内部对"要 embed 的字段角色"的命名,value（`"chunk_text"`）才是你实际 upsert 时用的字段名。upsert 时字段名必须和 `field_map` 的 value 完全一致,不一致的行为⚠未实测（见 SKILL.md 跨领域规则第 5 条）。
- 建 sparse 集成 embedding 索引时把 `embed.model` 换成 `pinecone-sparse-english-v0` 即可,其余参数结构不变。
- 集成 embedding 索引**不支持**用原始文本做 `update`（局部更新）或 `import`（批量导入),这两类操作在这类索引上只接受预先算好的向量值。
- 索引一旦绑定了某个 embedding 模型,模型本身不能改;只有该模型自身的 `write_parameters`/`read_parameters` 可以后续 `PATCH /indexes/{name}` 调整。

## Documents API：schema 化索引（2026-07 新增）

训练数据里大概率不存在这套 API（2026-07 才引入）。用 `SchemaBuilder` 声明一个或多个字段,每个字段是 `dense_vector`、`sparse_vector`、或带 `full_text_search` 配置的 `string`,一个 schema 里最多 1 个 `dense_vector` 字段 + 最多 1 个 `sparse_vector` 字段 + 最多 100 个 FTS `string` 字段。

```python
from pinecone import Pinecone, SchemaBuilder

pc = Pinecone(api_key="YOUR_API_KEY")

# 最小示例：只做 BM25 全文检索
schema = SchemaBuilder().add_string_field(name="body", full_text_search={}).build()
pc.indexes.create(name="articles", schema=schema)

# 多字段示例：BM25 + 语义检索在同一个索引
schema = (
    SchemaBuilder()
    .add_string_field(name="title", full_text_search={})
    .add_string_field(name="body", full_text_search={})
    .add_dense_vector_field(name="embedding", dimension=1536, metric="cosine")
    .build()
)
pc.indexes.create(name="articles-multi", schema=schema)
```

```bash
curl -X POST "https://api.pinecone.io/indexes" \
  -H "Api-Key: $PINECONE_API_KEY" -H "Content-Type: application/json" \
  -H "X-Pinecone-Api-Version: 2026-07" \
  -d '{
    "name": "articles-multi",
    "deployment": {"deployment_type": "managed", "cloud": "aws", "region": "us-east-1"},
    "schema": {"fields": {
      "title":     {"type": "string", "full_text_search": {}},
      "body":      {"type": "string", "full_text_search": {}},
      "embedding": {"type": "dense_vector", "dimension": 1536, "metric": "cosine"}
    }}
  }'
```

**Schema 字段类型**

| 类型 | 用途 | 说明 |
|---|---|---|
| `dense_vector` | 语义检索 | 需要 `dimension` + `metric`；一个 schema 最多 1 个 |
| `sparse_vector` | 稀疏向量检索 | 一个 schema 最多 1 个 |
| `string` + `full_text_search: {}` | BM25 全文检索 | 可选子字段 `language`/`stemming`/`stop_words`；最多 100 个；`{}` 用全部默认值 |

**Schema 校验规则**（来自 `guides/index-data/data-modeling` 的官方表格，转录未实测）：

| 场景 | 结果 |
|---|---|
| 字段值类型与 schema 声明不符 | 报错，整个 upsert 请求失败，不写入任何数据 |
| document/请求超出大小限制 | 报错 |
| 字段不在 schema 里 | 存为 metadata，自动建索引用于过滤 |
| 字段名以 `_` 或 `$` 开头 | 报错（`_` 保留给 `_id`/`_score`，`$` 保留给过滤操作符） |
| document 缺少某个 schema 字段 | 允许，schema 字段都是可选的，只要 document 至少带一个 |
| document 只有 `_id` 和 metadata（不带任何 schema 字段） | 报错 |
| document 缺少 `_id` | 报错 |

**注意事项**

- **Schema 定义后不可修改**：不能增删字段，要改 schema 只能建新索引重新灌数据（官方原文明确警告，不是本 skill 推测）。
- 一次 upsert 请求里只要有一个 document 校验失败，**整批都不写入**（不是部分成功）。
- 集成 embedding（Records API 的能力）**不能**用在 Documents API 索引上；Documents API 的向量字段只接受你自己算好的向量。
- 目前只有 Python SDK 和 REST 支持这套 API。

## 云与区域

| Cloud | Region | 支持的 Plan |
|---|---|---|
| `aws` | `us-east-1`（Virginia） | Starter / Builder / Standard / Enterprise |
| `aws` | `us-west-2`（Oregon）、`eu-west-1`（Ireland）、`eu-central-1`（Frankfurt）、`ap-southeast-1`（Singapore） | Builder / Standard / Enterprise |
| `gcp` | `us-central1`（Iowa）、`europe-west4`（Netherlands） | Builder / Standard / Enterprise |
| `azure` | `eastus2`（Virginia） | Builder / Standard / Enterprise |

Starter（免费）计划只能建在 `aws us-east-1`。云/区域创建后不可更改。

## 相似度 metric

| metric | 说明 |
|---|---|
| `cosine` | 最常用，分数归一化到 `[-1, 1]`，选用与 embedding 模型训练时一致的 metric |
| `dotproduct` | sparse 索引和单索引 dense+sparse 混合必须用这个 |
| `euclidean` | 平方欧氏距离，**分数越低越相似**（和 cosine/dotproduct 分数方向相反，容易在排序逻辑里写反） |

## 索引管理

- `GET /indexes` / `pc.list_indexes()`：列出项目下所有索引。
- `GET /indexes/{name}` / `pc.describe_index(name)`：拿 `host`、`status.ready`、`schema` 等。
- `PATCH /indexes/{name}`：只能改部分字段（pod 索引的 `replicas`/`pod_type`；Documents API 索引里 `semantic_text` 类型字段的 `read_parameters`/`write_parameters`）。**不能**改 `dimension`/`metric`/schema 字段/deployment 类型。
- `DELETE /indexes/{name}`：`deletion_protection: "enabled"` 时会被拒绝（403），必须先 `PATCH` 关掉保护再删。**不可逆**。

## 备份与从备份建索引

- `POST /indexes/{name}/backups`：创建静态快照（异步）。
- `POST /backups/{backup_id}/create-index`：从备份新建索引（可改名字/tags/deletion_protection，模型配置会保留）。
- 备份**产生持续存储费用**，用完要 `DELETE /backups/{backup_id}` 清理（见 pricing-and-limits.md）。
- `POST /indexes/{name}/backup-schedules`：定时自动备份。

## Pod-based 索引（遗留，新客户不可用）

⚠ **自 2025 年 8 月起，pod-based 索引不再向新客户开放**（文档原文明确标注"Legacy"）。旧教程/训练数据里常见的 `pod_type`（`s1`/`p1`/`p2` + `.x1`/`.x2`/`.x4`/`.x8`）、`replicas`、`shards`、`environment` 这些建索引参数属于这套遗留体系。除非用户账号本来就有存量 pod 索引要维护，新项目一律生成 serverless 代码。已有 pod 索引可迁移到 serverless，见官方 `guides/indexes/pods/migrate-a-pod-based-index-to-serverless`（本 skill 未详细覆盖，需要时单独查文档）。
