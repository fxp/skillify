# 写入数据：upsert / update / delete / fetch / list / 批量导入

> 整理自 `guides/index-data/upsert-data`、`guides/manage-data/*`、`guides/index-data/import-data`、`guides/index-data/data-modeling`，以及 OpenAPI 规范 `db_data_2026-07.oas.yaml`。抓取于 2026-09-21，**未经真实调用验证**。三套数据平面（Vectors / Records / Documents）的方法名不同，本文件按平面分节，先看 SKILL.md 跨领域规则第 1 条确认你的索引属于哪一套。

## 目录

- [核心心智模型：upsert 是覆盖写，不是追加](#核心心智模型upsert-是覆盖写不是追加)
- [Vectors API：upsert / update / delete / fetch / list](#vectors-api)
- [Records API：upsert_records（集成 embedding）](#records-api)
- [Documents API：documents.upsert / update / delete / fetch / list](#documents-api)
- [批量导入（bulk import）](#批量导入bulk-import)
- [结构化 ID 与分块（chunking）实践](#结构化-id-与分块chunking实践)

## 核心心智模型：upsert 是覆盖写，不是追加

三套 API 的 upsert 语义完全一致：**按 `id`（Vectors/Records）或 `_id`（Documents）做 upsert（存在则整条替换，不存在则新建）**。这不是"追加新版本"，旧数据会被新数据**整条覆盖**（Documents API 的 `update` 端点才是字段级 patch，upsert 依然是整条替换）。

常见事故：用自增序号、简单时间戳、或未加租户/文档前缀的短 ID，导致不同来源的数据意外撞 ID，静默覆盖彼此的记录且不报任何错误。解决办法是用结构化 ID，见本文件最后一节。

## Vectors API

### Upsert

```python
from pinecone.grpc import PineconeGRPC as Pinecone  # 高吞吐场景推荐 grpc 变体

pc = Pinecone(api_key="YOUR_API_KEY")
index = pc.Index(host="INDEX_HOST")  # 数据面用 host，不是 index 名字，见下方"如何拿 host"

index.upsert(
    namespace="example-namespace",
    vectors=[
        {"id": "doc1#chunk1", "values": [0.02, -0.03, ...],  # 长度必须等于索引 dimension
         "metadata": {"document_id": "doc1", "chunk_number": 1, "chunk_text": "..."}},
    ],
)
```

**如何拿 host**：`pc.describe_index(name).host`（一次性拿到后建议缓存/写进配置，不要每次请求都现查）。数据面请求打 `https://<host>/...`，不是 `https://api.pinecone.io`。

**批量限制**（来自官方 Upsert limits 页面，转录未实测）：

| 限制项 | 数值 |
|---|---|
| 单批最大记录数（带向量） | 1,000 |
| 单请求最大体积 | 2 MB |
| 单批最大记录数（集成 embedding 的文本 upsert，Records API） | 96（受 embedding 模型 `max_batch_size` 限制，不是 upsert 本身的限制） |

按 dimension/metadata 大小换算的建议批大小（官方示例表，未实测）：dimension 768 + 100B metadata 时单批可以到约 1000 条；dimension 1536 + 1KB metadata 时批大小要相应调小以不超 2MB。生产代码建议按固定批次数（如 200 条/批）分批，而不是硬编码单一批大小。

### Query 相关的 fetch / list（也算作"数据操作"）

- `index.fetch(ids=[...], namespace=...)`：按 ID 精确取记录（含向量值+metadata）。
- `index.query(..., include_values=False)` 只要 ID/分数/metadata 时优先用 query 而不是 fetch，因为 fetch 总是返回向量值，query 默认不返回（省 egress 费用，见 pricing-and-limits.md）。
- `index.list(prefix="doc1#", namespace=...)`：按 ID 前缀列出 ID（不返回向量值/metadata），分页,默认每页 100 条。

### Update（按 ID 或按 metadata filter）

```python
index.update(
    id="doc1#chunk2",
    values=new_vector,               # 传了就整体覆盖向量值
    set_metadata={"updated_at": "2026-09-21"},  # 只更新给出的 key，其余 metadata 保留
    namespace="example-namespace",
)
```

`set_metadata` 是**字段级合并**（不是整体替换 metadata 对象）——这一点和 upsert 不同，容易混淆：upsert 整条覆盖，update 的 `set_metadata` 只合并给出的字段。

### Delete（按 ID / 按 metadata filter / 整个 namespace）

```python
# 按 ID
index.delete(ids=["doc1#chunk1"], namespace="example-namespace")

# 按 metadata filter（MongoDB 风格操作符，见 query-and-search.md）
index.delete(filter={"document_id": {"$eq": "doc1"}}, namespace="example-namespace")

# 清空整个 namespace
index.delete(delete_all=True, namespace="example-namespace")
```

⚠ 文档原文，未实测：删除是异步生效的，Pinecone 整体是 eventually consistent（见下方一致性说明）。

## Records API

集成 embedding 索引用 `upsert_records`（不是 `upsert`），字段名必须匹配建索引时的 `embed.field_map`：

```python
index.upsert_records(
    "example-namespace",
    [
        {"_id": "doc1#chunk1", "chunk_text": "First chunk of the document content...",
         "document_id": "doc1", "chunk_number": 1},  # 除 chunk_text 外都自动存为 metadata
    ],
)
```

注意这里用的是 `_id`（下划线前缀，和 Vectors API 的裸 `id` 不同），字段名大小写、拼写要和 `field_map` 完全一致。

**限制**：集成 embedding 索引不支持文本形式的 `update`（只能传预先算好的向量做更新）；不支持文本形式的批量 `import`（同理）。

## Documents API

```python
index = pc.Index(name="articles-multi")  # Documents API 索引也用 pc.Index 拿连接对象

index.documents.upsert(
    namespace="__default__",
    documents=[
        {"_id": "1", "embedding": [0.12, 0.04, ...], "title": "...", "body": "...", "category": "tutorial"},
    ],
)

# 局部更新：按 _id 逐条 patch，或按 filter 批量 patch
index.documents.update(documents=[{"_id": "1", "title": "Updated title"}])
index.documents.update(documents=[{"_id": "2", "_remove_fields": ["body"]}])  # 删字段

# 删除：ids / filter / delete_all 三选一（filter 删除不支持 text-match 操作符，只支持标准 metadata 操作符）
index.documents.delete(ids=["1", "2"])
```

Documents API 的 `update` 响应里，按 filter 更新会返回 `matched_records`（更新发起时的匹配数，异步生效，是"某一时刻的快照"不是最终保证数）；按 `_id` 更新不返回这个计数。`delete` 按 filter 时同理返回 `matched_records`。

**注意事项**

- Documents API 的 upsert 请求体校验规则见 `indexes-and-schemas.md` 的 Schema 校验表——任何一条 document 不合规,整批都不写入。
- 全部 202（Accepted）响应,写入本身是异步的（和 Vectors/Records API 一致）。

## 批量导入（bulk import）

大批量灌数据（远超单次 upsert 的量级）时,从对象存储（S3/GCS/Azure Blob）导入比逐条 upsert 更省钱（见 pricing-and-limits.md 的 Imports 一节）。

| 索引类型 | 文件格式 | 必需列/字段 |
|---|---|---|
| Vectors API（dense） | Parquet | `id`、`values`、`metadata`（可选） |
| Vectors API（sparse） | Parquet | `id`、`sparse_values`、`metadata`（可选） |
| Documents API | JSON Lines（`.jsonl` 或 `.jsonl.gz`） | 每行一个 document，形状与 `documents.upsert` 相同 |

```python
resp = index.start_import(
    uri="s3://BUCKET_NAME/IMPORT_DIR",       # 子目录按 namespace 划分，目标 namespace 必须尚不存在
    integration_id="YOUR_INTEGRATION_ID",     # 控制台 Storage integrations 页面拿
    error_mode="continue",                    # 或 "abort"
)
# resp.status / resp.percent_complete / resp.records_imported
```

**注意事项**

- 目标 namespace **必须事先不存在**（⚠ 文档原文，具体报错未实测）。
- Parquet 导入时,不在必需列表里的额外列会被**静默忽略**（不报错，也不当成 metadata），这和 upsert 时"schema 外字段自动存为 metadata"的行为不一致——容易被误以为导入了额外字段实际却没有。
- JSONL（Documents API）导入则相反：未声明在 schema 里的字段**会**被当 metadata 存下来（和 `documents.upsert` 行为一致）。
- 单文件最大 10 GB。
- 集成 embedding（Records API）索引和 `semantic_text` 类型字段**不支持** bulk import 原始文本。
- 导入失败（比如遇到维度不对的向量,`on_error="abort"`）仍会**按已读取的记录量计费**,除非是内部系统错误导致的失败（文档明确写"You will still be charged"）。

## 结构化 ID 与分块（chunking）实践

官方建议的 ID 模式（不是强制规则，纯粹是最佳实践）：

- 文档分块：`document_id#chunk_number`（如 `doc1#chunk1`）
- 用户数据：`user_id#data_type#item_id`
- 多租户数据：`tenant_id#document_id#chunk_id`

用一个不会出现在 ID 内容本身里的分隔符（`#`/`_`/`:`）。结构化 ID 的好处：可以用 `list(prefix=...)` 按前缀批量拿到一个文档的所有分块 ID,再批量 fetch/update/delete，不需要额外维护一张"文档→分块 ID 列表"的映射表。

**一致性提示**（来自 `data-modeling` 页面原文）：Pinecone 是 eventually consistent,写入（upsert/update/delete）后立刻读（query/list/fetch）可能读不到最新状态。对一致性要求高的场景要加短延迟或重试逻辑（见 pricing-and-limits.md 的重试建议）。
