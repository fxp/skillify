# 计费模型、错误码、限流、SDK 包名与版本

> 整理自 `guides/manage-cost/understanding-cost`、`guides/production/error-handling`、OpenAPI 规范里的错误 schema、以及各官方 guide 页面里出现的 SDK 安装指令。抓取于 2026-09-21，**未经真实调用验证**。具体费率数字（$/GB、$/次等）请始终以 https://www.pinecone.io/pricing/ 为准，本文件只转录计费**模型**（按什么计量、怎么算），不转录会过期的价格数字。

## 目录

- [Pinecone 不是简单的"按调用次数扣 credits"模型](#pinecone-不是简单的按调用次数扣-credits模型)
- [Read Units（RU）](#read-unitsru)
- [Write Units（WU）](#write-unitswu)
- [存储（Storage）](#存储storage)
- [Egress](#egress)
- [Import / Backup / Embedding / Rerank](#import--backup--embedding--rerank)
- [Plan 与月度最低消费](#plan-与月度最低消费)
- [索引存在本身要不要花钱](#索引存在本身要不要花钱)
- [错误码](#错误码)
- [重试与限流](#重试与限流)
- [SDK 包名、安装命令、版本注意事项](#sdk-包名安装命令版本注意事项)

## Pinecone 不是简单的"按调用次数扣 credits"模型

Serverless 索引按**四个独立的用量维度**计费：Read Units（RU）、Write Units（WU）、存储（GB/月）、Egress（返回数据量）。不同操作类型消耗不同维度，同一个操作在不同请求参数下消耗的单位数量也不同（尤其 RU，和常见的"每次调用扣固定 credits"模型不同）。全文检索、语义检索、混合检索用的是**同一套四个计量维度**，没有单独的"混合检索附加费"。

## Read Units（RU）

计 RU 的操作：query、fetch、list、全文检索（Documents API 的 search）。

| 操作 | 计费公式 |
|---|---|
| Query / 全文检索 | **1 RU / 1 GB 目标 namespace 大小**，最低 0.25 RU/次。**`top_k`、`include_metadata`、`include_values` 这些参数不影响 RU**（文档原文明确排除，和"按返回结果多寡计费"的直觉相反） |
| Fetch | 1 RU / 每 10 条记录，最低 1 RU/次。按 metadata 过滤 fetch 用相同公式 |
| List | 固定 1 RU/次（每次最多 100 条） |

⚠ 上表"Query"行的计费口径意味着：同一个 namespace 里,不管你 `top_k=3` 还是 `top_k=1000`,RU 消耗完全一样,只取决于该 namespace 存了多少数据。这是本 skill 认为最反直觉、最值得优先验证的一条计费规则。

Dedicated Read Nodes（专用读节点）索引**不受** RU 用量限制约束（付费买断读吞吐,而非按次计费,细节见 `guides/index-data/dedicated-read-nodes/overview`,本 skill 未展开）。

## Write Units（WU）

计 WU 的操作：upsert、update、delete。

| 操作 | 计费公式 |
|---|---|
| Upsert | 1 WU / 每 1 KB 请求体，最低 5 WU/次；如果覆盖了已存在的记录，**旧记录的大小也额外计入** |
| Update | 1 WU / 每 1 KB（新记录 + 旧记录大小），最低 5 WU/次 |
| Delete | 1 WU / 每 1 KB 被删除的记录大小，最低 5 WU/次；指定不存在的 ID 或重复 ID 不增加 WU；删整个 namespace（`delete_all`）固定 5 WU |

Documents API 的写操作用**同一套公式**（文档原文明确："Writes to a document index use the same cost models as writes to a vector index"）。

## 存储（Storage）

按索引所有 namespace 的记录总大小,月度 GB 计费。计算公式（三种索引形态,取决于是否存 dense/sparse 向量）：

```
纯 dense 索引:  索引大小 = 记录数 × (ID 大小 + metadata 大小 + dense 维度 × 4 字节)
纯 sparse 索引: 索引大小 = 记录数 × (ID 大小 + metadata 大小 + 非零 sparse 值数 × 8 字节)
dense+sparse:  索引大小 = 记录数 × (ID 大小 + metadata 大小 + dense 维度×4字节 + 非零sparse值数×8字节)
```

## Egress

**读请求返回给你的数据量**计费（query/fetch/list/文本检索/全文检索）,按响应体总字节数。写请求（upsert/update/delete/import）、`describe_index_stats`、索引管理请求**不计 egress**。

- `include_values=False`（query 默认值）能降低 egress,但**不能豁免计费**——ID 和分数依然会返回、依然计入。
- `fetch` **总是**返回向量值（没有 `include_values` 开关）,egress 天然比等价的 query 高。**只要 ID/metadata 不要向量值时优先用 query 而不是 fetch。**
- 各 plan 有月度 egress 免费额度（Starter 1GB / Builder 10GB / Standard、Enterprise 100GB）。超额后：付费计划按超额费率计费并继续服务；免费/Flat-fee 计划（Starter/Builder）读请求直接被 `429 RESOURCE_EXHAUSTED` 拒绝,写请求和索引管理不受影响,额度下个计费周期重置。

## Import / Backup / Embedding / Rerank

- **Import**：按读取的记录大小计费,**不论导入是否成功**（`on_error="abort"` 中途失败仍按已读取部分计费）;只有 Pinecone 内部系统错误导致失败才不计费。
- **Backup**：存储费用按备份大小,持续产生,直到手动删除。
- **Restore**（从备份建索引）：按索引大小计费。
- **Embedding**：按 token 数计费（`usage.total_tokens`）,查询文本和文档文本用同一费率。
- **Rerank**：按**请求次数**计费（不是按候选文档数,也不是按 token 数）。

## Plan 与月度最低消费

| Plan | 月度最低消费 | 说明 |
|---|---|---|
| Starter | $0 | 免费,适合早期开发测试 |
| Builder | $20（固定费用） | 超出 Builder 用量上限**直接拒绝服务**，不是按超额计费 |
| Standard | $50 | 超出最低消费部分按实际用量计费 |
| Enterprise | $500 | 同上 |

## 索引存在本身要不要花钱

**这是本 skill 认为需要在用户执行"建索引做测试"之前重点确认的一点**：Serverless 索引本身是"按用量付费",**没有流量时读写费用为 0**,但**存储费用只要索引里有数据就持续产生**（哪怕索引空闲无请求）。空的索引（0 条记录）存储费用应为 0（未实测确认,按公式"记录数 × ..."推算,记录数为 0 时公式结果为 0）,但一旦 upsert 了任何数据,存储费用开始按月计,直到数据被删除或索引被删除。Backup 同理只要不删除就持续计费。测试用完的索引/备份要主动清理,见 `pinecone-workspace/verification-plan.md`。

## 错误码

标准 HTTP 状态码语义（`guides/production/error-handling` 原文转录）：

| 状态码 | 含义 | 处理建议 |
|---|---|---|
| 400 | 参数无效 | 检查请求格式,不要重试 |
| 401 | API Key 缺失或无效 | 检查 Key,不要重试 |
| 402 | 账号欠费 | 检查控制台账单状态,不要重试 |
| 403 | 超出配额,或触发了 deletion protection | 检查配额/关闭保护,不要重试 |
| 404 | 资源不存在 | 检查名字拼写和是否已被删除 |
| 409 | 资源已存在（如重复建索引） | 不要重试,先检查是否已存在 |
| 429 | 触发限流 | 指数退避重试 |
| 500/502/503/504 | 服务端错误（通常是瞬时的） | 指数退避重试 |

错误响应体结构（来自 OpenAPI 规范,control-plane 与部分 data-plane 端点通用）：`{"status": <int>, "error": {"code": "<GRPC 风格错误码，如 INVALID_ARGUMENT/NOT_FOUND/RESOURCE_EXHAUSTED>", "message": "<可读描述>", "details": {...}}}`。**注意**：Vectors API 一部分端点（如 `/query`、`/vectors/upsert`）的 400/4xx/5xx 响应体结构和 Documents/control-plane 端点**不完全一致**（前者是 `{"code": <int>, "message": <string>, "details": [...]}` 扁平结构,后者是 `{"status": <int>, "error": {"code": <string>, ...}}` 嵌套结构）——⚠ 这一差异来自 OpenAPI 规范交叉阅读,未实测确认,给所有端点复用同一个错误解析函数前建议先核实。

## 重试与限流

- 只重试 5xx 和 429,**不要重试其它 4xx**（不会因为重试而变好）。
- 官方建议指数退避 + 抖动（jitter),设最大重试次数和最大延迟上限。
- Go SDK 内置 `RetryPolicy`（默认 3 次重试,500ms 基础延迟,30s 上限,2 倍退避),自动覆盖 REST（控制面/数据面/inference）和 gRPC（数据面）客户端;其它语言 SDK 需要应用层自己实现退避逻辑（Python/Node 官方文档给的是纯手写重试函数示例,SDK 本身不内置)。
- 多数限流值可以联系 Support 申请提高。

## SDK 包名、安装命令、版本注意事项

| 语言 | 包名 | 安装命令 |
|---|---|---|
| Python | `pinecone`（**不是** `pinecone-client`,后者是旧包名） | `pip install --upgrade pinecone`；需要 gRPC 数据面客户端（高吞吐场景）加 extra：`pip install "pinecone[grpc]"` |
| Node.js | `@pinecone-database/pinecone` | `npm install @pinecone-database/pinecone` |
| Java | Maven artifact `io.pinecone:pinecone-client`（**Java 这边包名恰好就叫 pinecone-client**,和 Python 的情况相反,两种语言容易搞混） | Maven/Gradle 依赖声明 |
| Go | `github.com/pinecone-io/go-pinecone/<version>/pinecone` | `go get github.com/pinecone-io/go-pinecone/...` |

⚠ **Go SDK 版本号在文档站内部不一致**：抓取材料中 60+ 处示例 import `go-pinecone/v4/pinecone`,`error-handling` 页面的 Go 示例却 import `go-pinecone/v6/pinecone`,另有 2 处出现 `v5`。三个大版本号同一天抓取到,未实测确认当前 `go get` 实际会解析到哪个版本、v4 代码在 v6 下是否兼容。写 Go 代码前建议先 `go list -m -versions github.com/pinecone-io/go-pinecone` 或查 https://pkg.go.dev/github.com/pinecone-io/go-pinecone 确认当前最新大版本,不要直接照抄某一篇文档页面的 import 路径。

Documents API（`index.documents.*`）目前只有 **Python SDK（v10 及以上）** 和 REST 支持;文档原文写"Node.js and other SDKs for the Documents API are coming soon"（抓取于 2026-09-21,可能已上线,用前建议查最新 SDK changelog 确认）。
