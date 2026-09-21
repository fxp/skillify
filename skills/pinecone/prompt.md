把这份 skill 装进你的 Agent，让它接入 Pinecone 向量数据库时不再默认只知道 Vectors API 的 `dimension`/`metric` 建索引方式，也不会把控制面和数据面的 Base URL 搞混。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill pinecone --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill pinecone --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/pinecone/pinecone.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认 3 件事」和「能力域导航」三节；
2. `references/` 下有 6 个 `.md`，其中 `indexes-and-schemas.md` 讲的是 Vectors / Records / Documents 三套数据平面怎么选；
3. 在 `SKILL.md` 的"跨领域的通用规则"一节能搜到「一个 index 只能属于三套数据平面之一」字样，并标注了来源是官方迁移指南。

## 这份 skill 覆盖什么

Pinecone（`pinecone.io`，控制面 `api.pinecone.io`）2024 年以来架构变化很大：serverless 已取代 pod 成为默认（pod 自 2025-08 起停止向新客户开放），而且现在**并行存在三套互不兼容的数据平面**——经典的 Vectors API（`dimension`/`metric` 建索引，`upsert`/`query` 自带向量）、集成 embedding 的 Records API（建索引时绑定模型，upsert 传原始文本自动向量化），以及 2026-07 才新增、训练数据大概率完全不知道的 Documents API（schema 化，支持一个索引内声明 dense/sparse/全文检索多种字段，`score_by` 挑排序信号）。

重点是两个反直觉陷阱：**一个 index 创建时就固定属于三套数据平面之一，创建后不能迁移、不能混用**，而且同一个 REST 端点 `POST /indexes` 在不同的 `X-Pinecone-Api-Version` 请求头下接受完全不同形状的请求体（2026-07 版是 schema-only，不再接受旧版顶层 `dimension`/`metric`/`vector_type`）——这是纯靠读文档才能发现的坑；以及 **read units 计价只看目标 namespace 的总 GB 数，和返回结果多寡无关**，`top_k`、`include_metadata`、`include_values` 这些参数完全不影响 RU 计费（文档原文明确排除），这和"按返回条数计费"的直觉相反。此外 SKILL.md 还记录了 upsert 是按 ID 覆盖写而非追加、metadata 过滤是 MongoDB 风格操作符而非 SQL、Python SDK 包名已从 `pinecone-client` 改成 `pinecone`（但 Java SDK 的 Maven artifact 反而叫 `pinecone-client`），以及站内 Go SDK 示例自身存在 v4/v5/v6 三个版本号并存的内部不一致，未实测确认哪个权威。

内容不是文档搬运：整理自 `docs.pinecone.io/llms.txt` 二级索引 + 官方 OpenAPI 规范（`db_control_2026-07.oas.yaml`/`db_data_2026-07.oas.yaml`/`inference_2026-07.oas.yaml`）+ 约 40 篇官方 guide 页面正文，字段名/类型/必填以 OpenAPI 规范为准，请求示例、报错文案、计费数字来自文档转录，全部标注为 `⚠ 文档原文，未实测`。

## 版本

**文档版，抓取于 2026-09-21，未用真实凭证验证。** 全篇标注 `⚠ 文档原文，未实测`，没有做任何真实 API 调用，也没有做 with/without skill 的对照实验。实际调用时报错与 skill 不一致，**以 API 的真实报错为准**，并去 `docs.pinecone.io` 核实最新情况。
