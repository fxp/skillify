# pinecone skill 验证计划（待真实 API Key）

现状：文档版，抓取于 2026-09-21。依据 `https://docs.pinecone.io/llms.txt`（二级索引 → `pinecone-database.md` → `guides.md`/`reference.md`）+ 官方 OpenAPI 规范 `db_control_2026-07.oas.yaml` / `db_data_2026-07.oas.yaml` / `inference_2026-07.oas.yaml`（来自 `raw.githubusercontent.com/pinecone-io/pinecone-api`）+ 约 40 篇官方 guide 正文整理，**没有做过任何真实 API 调用**，也没有跑 with/without skill 对照实验。

## 测试原则

- Key 只走环境变量 `PINECONE_API_KEY`，不写入任何文件；验证完成后全仓库 `grep -rn "<key 前 8 位>"` 一遍确认无残留。
- 每条结论改回对应 reference 时按固定格式写"已用真实 API 验证（日期）：传 X 返回 `{...}`"，文档本身的错误同时升到 `SKILL.md` 的"跨领域的通用规则"。
- **索引创建/删除要谨慎**：Serverless 索引本身按用量计费（无流量时读写费用为 0），但存储费用只要索引里有数据就持续产生；backup 同理持续计费直到手动删除。验证计划里"建索引"类的项，建完立刻做完对应测试就删,不要留到验证周期结束才批量清理。用一个专门的、名字带时间戳的测试索引（如 `skill-verify-20260921`），避免和真实项目资源混淆。
- Starter（免费）计划的限制（区域只能 `us-east-1`、有限的 embedding/rerank 月度额度）可能导致部分 P1/P2 项跑不通，跑不通时在 verification-log.md 里如实记录"权限/额度不足，未验证"，不要跳过不提。
- 每次调用记录到 `pinecone-workspace/verification-log.md`：日期、endpoint/SDK 方法、请求要点、原始响应片段、花费（如可获取）。

## P0 —— SKILL.md"先确认的三件事"+ 本 skill 标为最高优先级的假设（低成本、优先测）

| # | 结论/假设 | 怎么测 | 预期成本 | 判定 |
|---|---|---|---|---|
| 1 | 数据面必须用索引专属 `host`，不能打 `api.pinecone.io` | 建一个 dense 索引，`describe_index` 拿 host，分别对 `host` 和 `api.pinecone.io` 发一次 `POST /query`，对比响应 | 建索引本身的存储成本（几 KB） | 确认后者是否 404/重定向/明确报错，记录报错原文 |
| 2 | `X-Pinecone-Api-Version` 缺失时的行为 | 对 `POST /indexes`（控制面）分别带和不带该头各发一次 | 0（多为 4xx，通常不计费，需确认） | 确认是报错、还是走某个默认版本；如果是后者，记录默认版本号 |
| 3 | `2026-07` 版本头下 `POST /indexes` 是 schema-only，旧版 `dimension`/`metric`/`spec` 请求体会被拒绝 | 用 `2026-07` 头发一个旧版请求体（顶层 `dimension`），再用 `2025-10` 头发同样请求体 | 建索引成本，测完立刻删 | 确认 `2026-07` 是否真的拒绝旧请求体、报错内容；`2025-10` 是否成功 |
| 4 | 三套数据平面互相调用会被拒绝 | 建一个 Vectors API 索引，尝试对它的 host 发 `POST /namespaces/{ns}/documents/upsert`（Documents API 端点） | 0（应该是 4xx） | 记录报错内容，验证 SKILL.md 规则第 1 条 |
| 5 | 鉴权头 `Api-Key` 的精确大小写、错误 key 的报错格式 | 用一个错误的 key 调一次任意端点 | 0 | 记录 401 响应体格式 |

## P1 —— evals.json 的 5 个陷阱场景对应的裁决项（中等优先级）

| # | 陷阱 | 怎么测 | 预期成本 | 判定 |
|---|---|---|---|---|
| 6 | upsert 是覆盖写，同 ID 二次 upsert 是否整条替换（eval #2） | 建索引，upsert 一条带 metadata A 的记录，再 upsert 同 ID、不同 metadata B 的记录（B 不含 A 的字段），fetch 该 ID | 建索引+几次 upsert，成本很低 | 确认最终记录里 A 的字段是否消失（整条覆盖）还是保留（字段级合并） |
| 7 | RU 计费是否真的和 `top_k` 无关（eval #3） | 同一个 namespace 分别用 `top_k=5` 和 `top_k=1000` 各查一次，对比响应里的 `usage.read_units` | 几次 query，低成本 | 确认两次 RU 是否相同；如不同，这是 SKILL.md 需要撤回/改写的重点结论 |
| 8 | Documents API 的 `score_by` 能否单请求同时排 dense+文本两种信号（eval #1 的"不存在单请求混合参数"断言） | 尝试构造一个 `score_by` 数组同时含 `dense_vector` 和 `text` 两个 clause 发给 `documents.search` | 0（预期报错或只生效一个） | 记录真实行为：报错、忽略其中一个、还是文档遗漏的真实支持 |
| 9 | 集成 embedding 索引 upsert 字段名与 `field_map` 不匹配时的行为（eval #4 相关，SKILL.md 规则 5） | 建一个 `field_map: {"text": "chunk_text"}` 的集成 embedding 索引，upsert 一条用错误字段名（如 `"content"` 而非 `"chunk_text"`）的记录 | 建索引+一次 upsert，低成本 | 确认报错、还是被当成普通 metadata 静默存储且不生成向量（最危险的情况） |
| 10 | metadata filter 顶层裸操作符是否真的编译报错（eval #5） | 用 `filter={"$gte": 100}`（不嵌字段名）发一次 query | 0（预期 400） | 记录报错文案，判定"编译错误"的具体形式 |
| 11 | 默认命名空间：Vectors API 的 `""` 和 Documents API 的 `"__default__"` 是否指向同一底层命名空间 | 用 Vectors API 索引 upsert 不传 namespace，再用 `list_namespaces` 看实际生成的 namespace 名字；Documents API 索引重复同样测试 | 低成本 | 确认两套 API 的默认命名空间字符串，更新 namespaces-and-multitenancy.md |

## P2 —— 影响准确性但优先级略低的项

| # | 结论 | 怎么测 | 预期成本 | 判定 |
|---|---|---|---|---|
| 12 | sparse 索引用非 `dotproduct` metric 建索引时，是建索引报错还是查询时才报错 | 尝试用 `vector_type="sparse", metric="cosine"` 建索引 | 0（预期建索引就报错，需确认） | 记录实际报错阶段 |
| 13 | 单索引 dense+sparse：非 dotproduct 索引 upsert 带 sparse_values 是否真的"写入成功、查询才报错"（hybrid-search-and-inference.md 引用的文档原文） | 用 `metric="cosine"` 的 dense 索引 upsert 一条带 `sparse_values` 的记录，再查询 | 低成本 | 确认 upsert 阶段是否真的不报错，查询阶段报错内容 |
| 14 | `cohere-rerank-3.5` 是否真的被静默路由到 `cohere-rerank-4-fast`，返回的 `model` 字段显示哪个 | 分别用两个模型名调一次 `/rerank` 对同一输入 | 按请求次数计费，2 次 | 对比响应体 `model` 字段和分数分布 |
| 15 | Go SDK 当前实际可安装的最新大版本 | `go list -m -versions github.com/pinecone-io/go-pinecone`（不需要 Pinecone Key，纯 Go 工具链） | 0 | 确认 v4/v5/v6 哪个是当前默认，更新 pricing-and-limits.md |
| 16 | Parquet 导入时未声明列被静默忽略 vs JSONL 导入时未声明字段被存为 metadata，两种行为是否如文档所述 | 各构造一个小样本文件到测试 bucket 分别导入 | 需要先配置对象存储集成，成本略高，可选做 | 确认两种导入路径对"多余字段"的处理是否如实测 |
| 17 | Documents API 的 Node.js SDK 是否已经从"coming soon"变为已发布 | 查 `@pinecone-database/pinecone` npm changelog / GitHub release，不需要真实调用 | 0 | 更新 pricing-and-limits.md 的 SDK 语言支持说明 |

## P3 —— 低优先级/需要企业权限或额外条件，暂不强求

| # | 项目 | 备注 |
|---|---|---|
| 18 | Dedicated Read Nodes 相关行为 | 需要企业版权限，测试账号大概率没有，先跳过 |
| 19 | CMEK / Private Endpoints / SSO | 企业安全功能，本 skill 明确不覆盖，不在验证范围 |
| 20 | Backup schedule 定时备份的实际触发 | 需要长时间观察，成本和时间都偏高，可选做 |
| 21 | Pinecone Assistant / Nexus | 本 skill 明确不覆盖的独立产品，不在验证范围 |

## 完成后

- 每条结论改回对应 reference 文件，写「已用真实 API 验证（日期）：传 X 返回 `{...}`」；文档本身的错误同时升到 `SKILL.md`"跨领域的通用规则"一节。
- `SKILL.md`"⚠ 验证状态"从"文档版，未验证"改成分区写清"已验证 / 仍是文档转录"，参照本工作区其它 skill（如 `firecrawl`）的写法。
- 跑 `evals/evals.json` 的 5 个场景做 with/without skill 对照（子 Agent 各写一版代码，用本计划里验证过的真实报错去判两版代码能不能在生产环境跑通），写 `pinecone-workspace/comparison-report.md`（Markdown，按本工作区 `CLAUDE.md` 的约定，不生成 HTML/Artifact）。
- 全仓库 `grep` Key 前 8 位，确认没有残留；删除测试中创建的所有索引、命名空间、备份（`DELETE /indexes/{name}`、`DELETE /backups/{id}`），避免持续计费。
