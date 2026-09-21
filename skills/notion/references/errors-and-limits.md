# Notion-Version、错误码、限流、SDK

> ⚠ 本文件内容全部来自官方文档 `reference/{versioning,status-codes,request-limits,workspace-block-limits,changes-by-version}.md`、`guides/get-started/upgrade-guide-2025-09-03.md` 与 GitHub `makenotion` 组织仓库列表，抓取/核实于 2026-09-21，**未经真实 API 调用验证**。

## 目录

- [Notion-Version 请求头](#notion-version-请求头)
- [错误响应格式与状态码](#错误响应格式与状态码)
- [★ Free 工作区的区块数量上限（新增的 403 来源）](#free-工作区的区块数量上限新增的-403-来源)
- [限流](#限流)
- [请求体大小限制](#请求体大小限制)
- [SDK 与包名](#sdk-与包名)

## Notion-Version 请求头

**每一个请求都必须带这个头**，例如：

```
Notion-Version: 2026-03-11
```

- 当前（抓取时）最新版本是 **`2026-03-11`**。
- **缺失这个头会直接报 `400 missing_version`**——这是明确报错,不是"静默用某个默认版本",相对友好,但也意味着"没报错就等于版本对了"这个假设是错的：传了一个**过旧但合法**的版本号不会报错,只会让你的请求继续用那个旧版本的字段形状和端点路径,不会主动提示你有新版本。
- **版本之间存在破坏性变更**,升级前要看变更日志（`reference/changes-by-version.md`）和对应的迁移指南。已知的两次重大变更：
  - `2021-05-13`：属性类型字段名从 `"text"` 改成 `"rich_text"`。
  - `2025-09-03`：引入 data source 模型,`database_id` 在大量端点被 `data_source_id` 取代（见 `references/databases-and-data-sources.md`）,这是**近期最大的一次破坏性变更**,凭旧记忆写的代码大概率在这个版本之后会报错或查到空结果。
  - `2026-03-11`（当前最新版本）：`archived` 字段被移除,只接受 `in_trash`（见 `references/pages-and-blocks.md`）。
- **哪些变更不需要新版本号（向后兼容,随时可能发生,不受 pin 版本保护）**：新增端点、新增可选请求参数、响应里新增字段、排序 tie-break 规则的调整、限流数值调整、错误信息文案措辞的润色（错误 `code` 值本身稳定,`message` 的具体文字不稳定,不要用 `message` 字符串做逻辑判断）。**反序列化响应时用"忽略未知字段"的宽松解析器**,严格解析在这类新增字段面前迟早会崩。
- **Beta 功能**：部分端点需要额外带 `Notion-Beta: <beta-name>-<YYYY-MM-DD>` 才能启用新契约（不带这个头,行为保持不变）,多个 beta 用逗号分隔。beta 修订号可能有破坏性变更,未带当前修订号会报错并在错误信息里点出正确的 flag 值。⚠ 文档原文,未实测。

## 错误响应格式与状态码

```json
{
  "object": "error",
  "status": 404,
  "code": "object_not_found",
  "message": "..."
}
```

| HTTP | `code` | 含义 | 备注 |
| :--- | :--- | :--- | :--- |
| 400 | `invalid_json` | 请求体不是合法 JSON | |
| 400 | `invalid_request_url` | URL 不合法 | |
| 400 | `invalid_request` | 不支持这个请求 | |
| 400 | `validation_error` | 请求体不符合 schema | 看 `message` 具体字段 |
| 400 | `missing_version` | 没带 `Notion-Version` 头 | 见上一节 |
| 400 | `invalid_beta` | `Notion-Beta` 头格式错/名字不认识/修订号不支持 | |
| 401 | `unauthorized` | bearer token 不合法（过期/撤销/拼写错误） | 不是"没共享"的错误码,见下 |
| 403 | `restricted_resource` | 权限不够,**或** 触发了工作区区块数上限 | 看 `message`/`additional_data`,见下一节 |
| 404 | `object_not_found` | 按当前 token 的视角,该资源不存在 | **最常见原因是没有共享给这个连接**,不一定是 ID 错了——见 `references/auth-and-sharing.md` |
| 409 | `conflict_error` | 写入冲突,或文件上传第三方存储抖动 | 可重试 |
| 429 | `rate_limited` | 超过限流 | 见下方限流一节 |
| 500/502/503/504 | `internal_server_error`/`bad_gateway`/`service_unavailable`/`gateway_timeout` | 服务端错误 | 幂等请求（GET/DELETE）可重试 |
| 529 | `service_overload` | 临时过载 | 按 429 同样处理,读 `Retry-After` |

**401 vs 404 的区分很重要**：401 是"这个 token 根本不被信任"（token 本身有问题）;404 更常见的实际原因是"token 合法,但它看不到这个资源"（没共享）。不要把两者合并成一种"鉴权失败"处理逻辑,应对方式完全不同——401 该去检查 token 是否正确/过期,404 该去检查共享状态。

## ★ Free 工作区的区块数量上限（新增的 403 来源）

这是一个和"限流"不同性质的限制,容易被误判成限流问题反复重试：**超过一个人的 Free 工作区（人数 >1）有生命周期总计 1000 个区块的硬上限**,付费工作区和单人 Free 工作区不受限。规则要点（⚠ 文档原文,未实测）：

- 触发上限后写入返回 **403 `restricted_resource`**,`additional_data.block_limit` 字段专门标出这是区块上限触发的（不要靠 `message` 文本判断,用这个字段）。
- **这不是限流,重试同一个请求没有用**,必须由工作区管理员升级付费计划才能恢复写入。
- 触及上限的第一次写入会成功,并开启一个 **3 天宽限期**,宽限期内仍可以继续创建;宽限期过后所有"会创建新区块"的写操作失败,**读、删除、不创建新区块的编辑仍然可用**。
- 影响面：`POST /v1/pages`（页面本身是一个区块）、`POST /v1/databases`（数据库是一个区块）、`PATCH /v1/blocks/{id}/children`（追加的每个子区块都算）、`markdown` 更新（如果新增了区块）、`PATCH /v1/pages/{id}`（如果这次更新新增了区块,比如套用模板;只改标题/属性不受影响）、带附件的评论。**`POST /v1/data_sources`（给已有数据库加数据源）不受影响**——`2025-09-03` 之后新增数据源不再创建新区块。
- **此限制不适用于 personal access token,也不适用于面向所有工作区开放安装的 public connection**;只影响 internal connection 和"仅限指定工作区安装"的 public connection。
- 套用模板等异步任务即使当时写入返回成功,实际执行时也会重新检查这个上限——**返回成功不代表模板一定完整执行完**,没有失败回调/任务状态查询端点,只能设超时后自己去读区块子级确认结果,且**不要在部分完成的页面上自动重跑模板**,避免内容重复。

## 限流

两层限流,任一层超限都返回 `429 rate_limited`：

| 维度 | 限制 |
| :--- | :--- |
| 单连接（按 60 秒滑动窗口） | Business/Enterprise 计划 600 次/分钟；其它计划 180 次/分钟 |
| 整个工作区（所有连接共享） | 按计划设定,单独触发时和单连接限流无关,`Retry-After` 可能超过 60 秒 |

- 429 响应带 `Retry-After` 头（秒数）,per-connection 触发时还会在 `additional_data.retry_after` 里重复一份（给读不到响应头的客户端用）；429/529 都用同一个字段。
- `additional_data.rate_limit_reason` 区分是哪层限流触发的（例如 `public_api_request_rate_limit` / `public_api_space_request_rate_limit`）。
- **重试策略**：429/529 重试;500/502/503/504 只对幂等请求（GET/DELETE）重试;4xx 里其它错误先修请求本身,重试没用。用指数退避 + 抖动,设置最大重试次数,不要多个 worker 各自独立重试（容易在延迟到期的同一时刻造成二次流量尖峰）,统一在一个出口做请求队列。官方 JS SDK 对 429 全量重试、对 GET/DELETE 的 500/503 也重试,直接调 REST API 要自己实现同等策略（含 529）。

## 请求体大小限制

| 限制项 | 上限 |
| :--- | :--- |
| 单次请求最大 payload | 500 KB,且最多 1000 个 block 元素 |
| 富文本 `text.content` | 2000 字符 |
| 富文本 `text.link.url` | 2000 字符 |
| 富文本 `equation.expression` | 1000 字符 |
| 任意 URL | 2000 字符 |
| 任意 email | 200 字符 |
| 任意 phone number | 200 字符 |
| `multi_select` 单次写入 | 100 个选项 |
| `relation` 单次写入 | 100 个关联页面 |
| `people` 单次写入 | 100 个用户 |
| 数据源 schema | 建议不超过 500 个属性 / 50KB |
| 追加子区块 | 单次最多 100 个,嵌套最多 2 层（见 `references/pages-and-blocks.md`） |

**这些是"单次请求"的限制,不是"属性能存多少"的限制**——比如一个 relation 属性实际能关联远超 100 个页面,只是单次写入操作最多加 100 个;读取超出部分要用 `GET /v1/pages/{id}/properties/{property_id}` 分页。超限统一返回 `400 validation_error`。

## SDK 与包名

| 语言 | 官方 SDK | 包名 | 备注 |
| :--- | :--- | :--- | :--- |
| JavaScript/TypeScript | ✅ 官方维护（`makenotion/notion-sdk-js`） | `@notionhq/client`（npm） | 初始化 `new Client({auth, notionVersion})`,`notionVersion` 不传会用 SDK 自带的默认版本,**建议显式传当前版本**,不要依赖 SDK 默认值随升级自动变化 |
| Python | ❌ **没有官方 SDK** | 无官方包 | `developers.notion.com` 文档站、示例代码、`makenotion` GitHub 组织仓库列表（已核实,2026-09-21）里都只有 JS SDK,**不要编造一个"官方 Python SDK"包名**;需要 Python 时用 `requests` 直接调 REST API（本 skill 各 reference 里的 Python 示例都是这么写的）,或者自行评估社区维护的第三方封装（例如 PyPI 上的 `notion-client`,由 `ramnes/notion-sdk-py` 维护,**非 Notion 官方**,版本兼容性和更新节奏要自己核实,不代表官方对其行为背书） |

**SDK 大版本和 API 版本绑定**：⚠ 文档原文,未实测——JS SDK 的 major 版本升级可能连带改变默认 `Notion-Version` 并丢弃对老 API 版本的支持（例如文档提到 v5.0.0 起不再支持 `2022-06-28` 及更早版本,v5.12.0 起才支持 `2026-03-11`）。锁定 SDK 版本和显式传 `notionVersion` 双管齐下,不要只做其中一件。SDK 走 npm 常规 semver（major/minor/patch）,minor/patch 升级通常不需要改代码,major 升级要看 release notes。
