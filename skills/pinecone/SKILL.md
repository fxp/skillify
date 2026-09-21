---
name: pinecone
description: 接入 Pinecone（pinecone.io / docs.pinecone.io）托管向量数据库的开发者手册（文档版，未经真实调用验证）——涵盖三套并行的数据平面（Vectors API 经典向量索引、Records API 集成向量化、2026-07 新增的 Documents API 结构化文档索引）、创建与配置索引（serverless 为默认、pod 已于 2025-08 停止对新客户开放）、写入数据（upsert 覆盖写语义、批量限制、bulk import）、查询与 metadata 过滤（MongoDB 风格操作符）、命名空间与多租户隔离、混合检索（dense+sparse/BM25 三种组合方式）、Pinecone 托管的 embedding 与 rerank 模型、以及按 read units / write units 计费的用量模型。当用户提到 "Pinecone" "pinecone.io" "docs.pinecone.io" "PINECONE_API_KEY" "@pinecone-database/pinecone" "pinecone-client" "pc.create_index" "index.upsert" "向量数据库" "RAG 检索后端"，或要写代码调用上述任意能力时，应主动使用本技能——Pinecone 自 2024 年以来架构变化很大（serverless 取代 pod 成为默认、集成 embedding/rerank、sparse+dense 混合检索、2026-07 又新增了一整套 schema-based 的 Documents API），不要凭训练记忆编造参数名或字段结构，尤其不要假设 `dimension`/`metric` 是唯一的建索引方式，也不要套用 Elasticsearch/Weaviate/Qdrant 等其他向量库的接口习惯。
---

# Pinecone 接入指南

Pinecone 是面向 AI Agent 和应用的托管向量数据库：语义检索、RAG 知识库、长期记忆存储。核心概念层级是 organization → project → index → namespace，写入和查询请求都落在某一个 namespace 上。本页只做分流与跨领域规则，字段表、示例代码在 `references/`。

## ⚠ 验证状态

**文档版（2026-09-21）**：内容整理自 `https://docs.pinecone.io/llms.txt`（二级索引，指向 `pinecone-database.md` → `guides.md`/`reference.md`）+ 官方 OpenAPI 规范 `db_control_2026-07.oas.yaml` / `db_data_2026-07.oas.yaml` / `inference_2026-07.oas.yaml`（来自 `https://raw.githubusercontent.com/pinecone-io/pinecone-api`）+ 约 40 篇官方 guide 页面正文，**没有用真实 API Key 调用验证过任何一条结论**，也没有做 with/without skill 的对照实验。

- 字段名、类型、必填、枚举值：来自官方 OpenAPI 规范，是当前流程里最权威的原始材料，但规范本身可能滞后于线上真实行为。
- 请求/响应示例、报错文案、计费数字：来自文档站代码块或正文转录，全部标 `⚠ 文档原文，未实测`。
- **文档站内容存在至少一处内部日期/版本不一致**（见下方「跨领域规则」第 8 条 Go SDK 版本号），未实测确认哪个是权威版本。
- 拿到真实 Key 后按优先级验证的清单见 `pinecone-workspace/verification-plan.md`。
- ⚠ **索引创建/删除请谨慎**：serverless 索引虽是按用量计费（无流量时读写费用为 0），但**存储费用只要索引存在就计**，且部分操作（backup、import）会产生不可逆费用；详见 `references/pricing-and-limits.md` 和 verification-plan.md 里的清理约定。

## 用之前先确认 3 件事

1. **Base URL 分裂成两个**：控制面（建/删/配置索引、Inference API）固定是 `https://api.pinecone.io`；数据面（upsert/query/fetch/delete 等）**没有固定域名**，每个索引有自己的 `host`（形如 `xxx-xxxxxxx.svc.xxx.pinecone.io`），必须先 `describe_index` 或 `pc.describe_index(name).host` 拿到再用，不能对着 `api.pinecone.io` 发数据面请求。
2. **鉴权**：请求头 `Api-Key: <PINECONE_API_KEY>`（**不是** `Authorization: Bearer`），几乎所有请求还必须带 `X-Pinecone-Api-Version: 2026-07`（或更早的日期版本，如 `2025-10`）这个日期版本头——SDK 会替你加上，但直接拼 curl 时极易漏掉，漏掉的具体后果未实测确认（⚠ 文档未说明,推测走网关默认版本）。
3. **最容易选错的字段：一个 index 属于哪套数据平面（Vectors / Records / Documents）在创建时就固定死，创建后不能迁移、也不能混用**。三选一之后，所有后续代码都要用对应那一套方法，用错方法会被拒绝（⚠ 文档原文："A request sent to the wrong data-plane API is refused"，未实测报错原文）。三套怎么选、怎么建见下方「跨领域规则」第 1 条和 `references/indexes-and-schemas.md`。

## 30 秒跑通第一个请求（Bring-your-own-vectors，最常见路径）

```bash
export PINECONE_API_KEY="YOUR_API_KEY"

# 1. 建一个经典向量索引（dimension/metric 方式，Vectors API）
curl -s -X POST "https://api.pinecone.io/indexes" \
  -H "Api-Key: $PINECONE_API_KEY" -H "Content-Type: application/json" \
  -H "X-Pinecone-Api-Version: 2025-10" \
  -d '{"name":"quickstart","vector_type":"dense","dimension":8,"metric":"cosine",
       "spec":{"serverless":{"cloud":"aws","region":"us-east-1"}}}'
```

```python
import os, time
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])

if not pc.has_index("quickstart"):
    pc.create_index(
        name="quickstart", dimension=8, metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        deletion_protection="disabled",
    )
while not pc.describe_index("quickstart").status.ready:
    time.sleep(1)

index = pc.Index(name="quickstart")  # SDK internally resolves the index host
index.upsert(vectors=[{"id": "v1", "values": [0.1] * 8, "metadata": {"genre": "doc"}}],
             namespace="example-namespace")
time.sleep(2)  # eventually consistent — a query right after upsert may miss it
resp = index.query(namespace="example-namespace", vector=[0.1] * 8, top_k=3,
                    include_metadata=True)
print(resp)
```

⚠ 文档原文，未实测：以上字段名与响应结构来自官方 guide 代码块，未真实调用确认。

## 能力域导航

| 我想做什么 | 参考文件 | 涉及的核心 endpoint / SDK 方法 |
|---|---|---|
| 建索引：选 serverless/pod、选三套数据平面之一、选 metric/dimension、多语言 SDK 代码、备份 | `references/indexes-and-schemas.md` | `POST /indexes`、`POST /indexes/create-for-model`、`pc.create_index` / `pc.create_index_for_model` / `pc.indexes.create` |
| 写数据：upsert（自带向量 / 集成 embedding 自动向量化 / schema 化 document）、更新、删除、批量 import | `references/upsert-and-data-ops.md` | `POST /vectors/upsert`、`POST /records/namespaces/{ns}/upsert`、`POST /namespaces/{ns}/documents/upsert`、`POST /bulk/imports` |
| 查询与 metadata 过滤：三套数据平面各自的 query/search、`$eq`/`$in`/`$and` 等操作符、text-match 过滤 | `references/query-and-search.md` | `POST /query`、`POST /records/namespaces/{ns}/search`、`POST /namespaces/{ns}/documents/search` |
| 混合检索（keyword + 语义）怎么选、Pinecone 托管的 embedding 模型、独立/集成 rerank | `references/hybrid-search-and-inference.md` | `POST /embed`、`POST /rerank`、`POST /query`（sparse_vector）、`score_by` |
| 命名空间怎么建、多租户隔离设计、命名空间会不会被查询意外穿透 | `references/namespaces-and-multitenancy.md` | `POST /namespaces`、`GET /namespaces` |
| 按 RU/WU 计费怎么算、免费额度、错误码、限流、SDK 包名与版本 | `references/pricing-and-limits.md` | 全局 |

**本 skill 不覆盖**：Pinecone Assistant（RAG 聊天助手产品，独立的 `/assistant/*` API 与文档树）；Pinecone Nexus（"agent 知识引擎"，独立产品，`/api-reference/manage-workspaces` 等一整套 workspace/context API）；Admin API（组织/项目/服务账号管理）；BYOC 部署细节；Private Endpoints、CMEK、SSO 等企业安全功能；Dedicated Read Nodes 的容量规划细节。这些在文档站里都是独立的一级导航，需要时应单独查 `docs.pinecone.io`。

## 跨领域的通用规则（写代码前必读）

以下每条都来自文档正文或 OpenAPI 规范交叉阅读，**全部未经真实调用验证**，是本 skill 认为最值得优先验证的直觉陷阱（详见 verification-plan.md 的 P0/P1 清单）：

1. **一个 index 只能属于三套数据平面之一，创建后终身不变，不能迁移，不能混用**（来自官方迁移指南 `guides/index-data/adopt-the-documents-api`）：
   - **Vectors API**（"经典"，训练数据里最熟悉的那套）：`pc.create_index(dimension=..., metric=..., vector_type=...)` 建索引，`index.upsert()` / `index.query()` / `index.fetch()` 读写。record 以 `values`(dense) / `sparse_values`(sparse) + 扁平 `metadata` 的形式存在。
   - **Records API**（"集成 embedding"，2024 年之后引入，仍然完全独立维护，不受下面第 3 套影响）：`pc.create_index_for_model(embed={...})` 建索引，`index.upsert_records()` / `index.search()` 读写，upsert 时传原始文本，Pinecone 用建索引时绑定的模型自动转向量。
   - **Documents API**（**2026-07 新增**，训练数据大概率完全不知道这套东西存在）：`pc.indexes.create(schema=SchemaBuilder()...)` 建索引，`index.documents.upsert()` / `index.documents.search()` 读写。一个 schema 可以同时声明 `dense_vector`、`sparse_vector`、`full_text_search` 的 `string` 字段，document 是任意 JSON，查询时用 `score_by` 挑一种排序信号。**这是新项目、尤其是需要全文/BM25 检索或"一个索引多种排序信号"的默认推荐路径**——但如果 Agent 是从旧教程或训练记忆里抄代码，几乎必然写成 Vectors API 那套 `index.upsert(vectors=...)`，这并不算错（Vectors API 完全受支持），只是拿不到 Documents API 的能力（全文检索、单索引多字段 schema）。三套的选型对比见 `references/indexes-and-schemas.md`。
   - 直接调 REST 且不传 `X-Pinecone-Api-Version` 或传 `2026-07`：`POST /indexes` 是 schema-only 的（不再接受旧版顶层 `dimension`/`metric`/`vector_type`/`spec`）；想继续发旧版请求体要么用 SDK（SDK 自动帮你转成 schema），要么显式把版本头钉在 `2026-04` 或更早。**这是一个纯靠读文档才能发现的坑：同一个 REST 端点 `POST /indexes` 在不同版本头下接受完全不同的请求体形状。**

2. **upsert 是按 `_id`/`id` 覆盖写，不是追加**（三套 API 通用）：ID 已存在时新数据整条替换旧数据（Documents API 的 `update` 端点才是局部patch）。误用自增/时间戳生成的短 ID、或忘记加租户前缀，会静默覆盖别的记录而不报错。推荐结构化 ID（如 `tenant_id#doc_id#chunk_id`），见 `references/upsert-and-data-ops.md`。

3. **metadata 过滤是 MongoDB 风格操作符，不是 SQL**：`$eq`/`$ne`/`$gt`/`$gte`/`$lt`/`$lte`/`$in`/`$nin`/`$exists`/`$and`/`$or`/`$not`。顶层裸操作符（如直接写 `{"$gt": 5}`）不合法，必须嵌在字段名下面；`$in`/`$nin` 最多 10000 个值。metadata 本身是扁平 JSON（**不支持嵌套对象**），值只能是 string/number/boolean/字符串数组，`null` 值不支持（要删字段而不是设 `null`)。完整操作符表见 `references/query-and-search.md`。

4. **命名空间隔离是真实的、按设计生效的，但默认命名空间容易踩坑**：一次 query/upsert/fetch/delete 请求永远只作用于一个 namespace，**不存在"查询意外跨命名空间"这回事**（这点符合直觉，不用特别防）。真正的坑是反过来的：不传 `namespace` 参数时请求会落到默认命名空间（Vectors API 里未显式传参时落在空字符串 `""` 命名空间；Documents API 的示例里出现的是字面量 `"__default__"`，两者是否是同一回事⚠未实测确认），如果 upsert 时忘记传 namespace、query 时又传了显式的 namespace（或反过来），会查到 0 条结果但**不报错**，容易被误判成"索引是空的"。生产代码建议永远显式传 namespace,不依赖默认值。

5. **集成 embedding（Records API）的索引，upsert 文本字段名必须和建索引时的 `embed.field_map` 完全一致**，字段名不匹配会怎样（报错还是被当成普通 metadata 静默存储、不生成向量）⚠未实测确认，是 P0 验证项。集成 embedding 索引**不支持** `update`（局部更新）和 `import`（批量导入）时传原始文本——这两个操作在集成 embedding 索引上只接受预先算好的向量。

6. **read units 计价按"目标 namespace 的总大小"而非返回结果多寡**：一次 query 的 RU 消耗只取决于该 namespace 的 GB 数（1 RU/GB，最低 0.25 RU），**`top_k`、`include_metadata`、`include_values` 这些参数完全不影响 RU 计费**（文档原文明确排除）。这和"按返回条数计费"的直觉相反，也是为什么按租户拆分 namespace 通常比单一大 namespace + metadata 过滤更省钱。egress（响应体积计费)则相反,确实跟 `include_values` 等参数相关。完整计费模型见 `references/pricing-and-limits.md`。

7. **Python SDK 包名是 `pinecone`，不是 `pinecone-client`**（`pip install --upgrade pinecone`，需要 gRPC 时装 `pinecone[grpc]` extra）。`pinecone-client` 是旧包名，训练数据/网上教程里大量出现，当前官方文档所有 Python 示例都用新包名。**注意 Java SDK 的 Maven artifact 恰好反过来叫 `io.pinecone:pinecone-client`**——这是两种语言 SDK 命名不对称,容易在多语言项目里搞混。Node.js 包名 `@pinecone-database/pinecone` 未变。

8. **⚠ 文档站内部版本号不一致**：`guides/production/error-handling.md` 的 Go SDK 示例 import `github.com/pinecone-io/go-pinecone/v6/pinecone`,但站内绝大多数其它页面（`create-an-index`、`manage-namespaces`、`rerank-results` 等 60+ 处）的 Go 示例都 import `.../v4/pinecone`,还有 2 处出现 `v5`。三个大版本号同时出现在同一天抓取的文档里，未实测确认哪个是当前 `go get` 会装到的版本,写 Go 代码前建议先 `go list -m -versions github.com/pinecone-io/go-pinecone` 核实。

9. **Reranking 模型 `cohere-rerank-3.5` 已于 2026-07-01 标记为 deprecated，自 2026-08-31 起请求被静默路由到 `cohere-rerank-4-fast` 处理**（文档原文），两者返回的相关性分数不可比,如果代码里对 rerank score 设了硬编码阈值(比如 `score > 0.7` 才采用)要重新校准。建议新代码直接指定 `cohere-rerank-4-fast`。

10. **Schema 定义后不可修改（Documents API）**：索引一旦用某个 schema 创建,不能增删字段,要变更 schema 只能建新索引、重新灌数据（文档原文明确警告）。这和 Vectors API 的索引一样，`dimension`/`metric` 建完也不能改，但 Documents API 的 schema 覆盖面更大（多个字段类型），改动成本更高，规划阶段要格外谨慎。

11. **Pod-based 索引自 2025 年 8 月起停止向新客户开放**，训练数据/旧教程里大量出现的 `pod_type`、`p1.x1`、`replicas`/`shards` 建索引方式属于遗留能力,新项目一律用 serverless（`spec.serverless` / `deployment.deployment_type: "managed"`)。除非用户账号本来就有存量 pod 索引要维护,否则不要生成 pod 相关代码。

## 目录结构

```
pinecone/
├── SKILL.md
├── references/
│   ├── indexes-and-schemas.md       建索引：三套数据平面选型、serverless/pod、metric、备份
│   ├── upsert-and-data-ops.md       写入/更新/删除/批量导入、批量限制
│   ├── query-and-search.md          查询、metadata 过滤操作符
│   ├── hybrid-search-and-inference.md  混合检索三种模式、embedding/rerank 模型
│   ├── namespaces-and-multitenancy.md  命名空间 CRUD、多租户设计
│   └── pricing-and-limits.md        RU/WU/存储/egress 计费、错误码、限流、SDK 包名版本
└── evals/
    └── evals.json
```

内容整理自 `https://docs.pinecone.io`（抓取于 2026-09），实际调用报错优先信任真实 API 返回，而非本文档。
