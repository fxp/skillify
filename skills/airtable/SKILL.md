---
name: airtable
description: 接入 Airtable Web API（airtable.com/developers/web/api）的开发者手册（文档版，未经真实调用验证）——涵盖鉴权（个人访问令牌 personal access token 取代了已于 2024-02-01 停用的旧版 API key，以及面向第三方集成的 OAuth）与细粒度 scope、记录的读取与分页（offset/pageSize/view）、filterByFormula 过滤（Airtable 自有公式语言，不是 SQL 也不是 MongoDB 风格操作符）、记录的创建/更新/删除（含单条与批量、10 条/请求上限、upsert、typecast）、字段类型与只读计算字段（formula/rollup/lookup/count 等无法通过写记录接口设置）、附件字段的专用上传流程、Metadata API（读取 base/table/field 结构）、错误码与限流（5 请求/秒/base，50 请求/秒/用户）。当用户提到 "Airtable" "airtable.com" "AIRTABLE_API_KEY"/"AIRTABLE_TOKEN" "pyairtable" "airtable.js" "baseId"/"appXXXXXXXXXXXXXX" "filterByFormula"，或要写代码读写 Airtable base/table/record 时，应主动使用本技能——不要凭训练记忆编造参数名或误用其他数据库/向量库/CRM API 的接口习惯（尤其不要把 filterByFormula 当成 MongoDB 那种字段名映射到 $gt/$eq 之类嵌套操作符的过滤器对象，也不要假设 formula/rollup 字段能像普通字段一样被写入）。
---

# Airtable Web API 接入指南

Airtable 的 Web API 以 base（相当于一个数据库/工作区）为顶层单位，base 内有多张 table，table 内是 record（行）与 field（列）。核心读写走 `api.airtable.com/v0/{baseId}/{tableIdOrName}`，结构（schema）读写走独立的 Metadata API（`api.airtable.com/v0/meta/...`），附件二进制上传又是另一个域名 `content.airtable.com`。本页只做分流与跨领域规则，字段表、请求/响应示例在 `references/`。

## ⚠ 验证状态

**文档版（2026-09-21）**：内容整理自 `https://airtable.com/developers/web/llms.txt` 索引下的全部 API reference 页面（Markdown 导出）+ 从 API reference 页面内嵌数据中提取出的完整官方 OpenAPI 3.1.0 规范（该规范未在任何 `/openapi.json` 之类的独立路径公开，只能从渲染后的页面 HTML 里的内嵌 JSON 提取）+ `support.airtable.com` 的公式函数参考页。**没有用真实 API Key 调用验证过任何一条结论**，也没有做 with/without skill 的对照实验。

- 字段名、类型、必填、请求/响应结构：来自官方 Markdown 文档与内嵌 OpenAPI 规范交叉核对，是当前流程里最权威的原始材料。
- 报错文案、状态码、限流数字：来自文档正文转录，全部标 `⚠ 文档原文，未实测`。
- **有一条业界公认的关键限制，官方当前文档正文和 OpenAPI 规范里都没有直接写出具体数字**：批量创建/更新/删除每次请求的记录数上限（见下方"跨领域规则"第 2 条与 `references/write-records.md`）——这是本次调研中最值得记录的"文档与现实的落差"，已作为验证计划 P0 第一项。
- 拿到真实 Key 后按优先级验证的清单见 `airtable-workspace/verification-plan.md`。

## 用之前先确认 3 件事

1. **鉴权精确格式**：`Authorization: Bearer <token>`。旧版 API key（无 Bearer 前缀、通过 URL 的 `api_key` 参数传）已于 **2024-02-01 停用**，现在只支持个人访问令牌（personal access token，前缀 `pat`）或 OAuth access token，两者用法完全一致。个人访问令牌需要同时具备**正确的 scope**（如 `data.records:write`）和**被显式授权访问的 base/workspace**——两个条件缺一个都会 403，token 本身还要求创建者对该 base 至少有对应的协作者权限。详见 `references/auth-and-scopes.md`。
2. **baseId 和 tableIdOrName 都可以用 ID 代替名字，官方推荐永远用 ID**（`appXXXXXXXXXXXXXX` / `tblXXXXXXXXXXXXXX`），因为用名字时改了 base/table 名称会导致 API 调用当场失效；fieldId（`fldXXXXXXXXXXXXXX`）同理。
3. **最容易选错的地方：`filterByFormula` 是 Airtable 自己的公式语言，不是 SQL、不是 MongoDB 风格的操作符对象**。写代码前必读下方"跨领域规则"第 1 条和 `references/read-and-filter-records.md`。

## 30 秒跑通第一个请求

```bash
export AIRTABLE_TOKEN="patXXXXXXXXXXXXXX.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

curl "https://api.airtable.com/v0/{baseId}/{tableIdOrName}?maxRecords=3" \
  -H "Authorization: Bearer $AIRTABLE_TOKEN"
```

```python
import os, requests

token = os.environ["AIRTABLE_TOKEN"]
base_id = "appXXXXXXXXXXXXXX"
table = "tblXXXXXXXXXXXXXX"  # 或用表名

resp = requests.get(
    f"https://api.airtable.com/v0/{base_id}/{table}",
    headers={"Authorization": f"Bearer {token}"},
    params={"maxRecords": 3},
)
resp.raise_for_status()
print(resp.json()["records"])
```

⚠ 文档原文，未实测：URL、Header 格式来自官方文档正文，响应结构来自官方示例代码块，未真实调用确认。

## 能力域导航

| 我想做什么 | 参考文件 | 涉及的核心 endpoint |
|---|---|---|
| 鉴权：个人访问令牌 vs OAuth 怎么选、scope 怎么配、token 权限排查 | `references/auth-and-scopes.md` | `GET /v0/meta/whoami`、`/oauth2/v1/authorize`、`/oauth2/v1/token` |
| 读记录：分页（offset/pageSize/maxRecords）、`view` 参数、排序、只取部分字段、`filterByFormula` 公式语法 | `references/read-and-filter-records.md` | `GET /v0/{baseId}/{tableIdOrName}`、`GET /v0/{baseId}/{tableIdOrName}/{recordId}` |
| 写记录：创建/更新/删除（单条与批量）、10 条/请求上限、upsert、typecast、附件上传 | `references/write-records.md` | `POST`/`PATCH`/`PUT`/`DELETE /v0/{baseId}/{tableIdOrName}`、`POST https://content.airtable.com/v0/{baseId}/{recordId}/{fieldIdOrName}/uploadAttachment` |
| 字段类型怎么读怎么写、哪些字段只读（formula/rollup/lookup/count/…）、附件/链接记录/单选多选的 cell value 形状、Metadata API 读写 base/table/field 结构 | `references/field-types-and-schema.md` | `GET /v0/meta/bases`、`GET /v0/meta/bases/{baseId}/tables`、`POST/PATCH /v0/meta/bases/{baseId}/tables/{tableId}/fields` |
| 错误码怎么判、429 限流怎么退避、per-base vs per-user 限速、官方/社区 SDK 怎么选 | `references/errors-and-rate-limits.md` | 全局 |

**本 skill 不覆盖**：Webhooks API（`references` 没有专门文件，需要实时变更通知时查 `webhooks-overview` 等官方页）；评论 API（record comments）；Base/Table/Workspace 协作者管理与分享链接；企业管理面（SCIM、审计日志、change events、eDiscovery、组织管理）；HyperDB；Block/Extension 安装管理；Sync CSV 专用端点；Interfaces 相关 API。这些在文档站里都是独立分组，需要时单独查官方文档。

## 跨领域的通用规则（写代码前必读）

1. **`filterByFormula` 是 Airtable 自有的公式语言，语法接近 Excel，不是 SQL、也不是 MongoDB/Pinecone 那种 `{field: {$gt: value}}` 操作符对象**。这是本 skill 认定的头号陷阱：如果 Agent 刚写过 MongoDB/Pinecone 之类的过滤器代码，很容易照搬 `{"age": {"$gt": 18}}` 这种结构传给 `filterByFormula`，Airtable 会把它当成字符串处理，**不会报错，只会静默返回不符合预期的结果（要么全部记录、要么空结果）**——这是最危险的一类问题，静默失效而非报错。正确写法是一个求值为布尔的公式字符串，如 `AND({Status} = "Active", {Age} > 18)`；字段名多于一个单词要用花括号包起来（如 `{Sale Price}`），逻辑连接用 `AND()`/`OR()` 函数而不是 `&&`/`||`，等值比较用单个 `=` 而不是 `==`，字符串字面量用双引号。完整语法与更多例子见 `references/read-and-filter-records.md`。
2. **⚠ 批量写请求的记录数上限，官方 Web API 文档正文和内嵌 OpenAPI 规范里都没有直接写出具体数字**——这本身是一处值得记录的文档缺口。业界广泛引用、且官方维护的 Python 客户端 `pyairtable` 源码里硬编码 `MAX_RECORDS_PER_REQUEST = 10` 并据此自动分批（见 `pyairtable/api/api.py`），与长期以来的社区共识一致，但这不等于真实调用验证。写批量创建/更新/删除代码时，**默认按 10 条/请求分批**，且预留"服务端返回的真实错误码/上限可能与此不同"的可能性；拿到 Key 后这是 verification-plan.md 的 P0 第一项。
3. **计算字段（formula / rollup / lookup / count / autoNumber / createdTime / createdBy / lastModifiedTime / lastModifiedBy / button / aiText）的值只读，不能通过 Create/Update records 接口写入**。官方 `field-model` 文档对这些类型都明确标注 "(read only)"。给"批量更新记录"这类通用函数传参前，必须先用 Metadata API（`GET /v0/meta/bases/{baseId}/tables`）读一遍字段清单排除掉这些 `type`,否则会拿到 422/`INVALID_REQUEST_UNKNOWN` 或类似校验错误(⚠ 具体错误码文档未给出针对性示例,未实测确认)。注意区别:这些类型的**字段定义(schema)本身可以通过 Metadata API 的 Create field 接口创建/更新**(比如新建一个 formula 字段并指定公式);只读的是"通过写记录接口设置它的计算结果值"这件事。
4. **附件字段的写入不是"塞一个文件"，也不是走主 API 域名**:
   - 给 cell 塞一个**公网可访问的 URL**(`[{"url": "https://..."}]`),Airtable 服务端会自己去抓取,写在 `POST/PATCH https://api.airtable.com/v0/{baseId}/{tableIdOrName}` 里,和其它字段一起提交即可,不需要单独调用。⚠ 这个写入形状(除了 `url` 还需不需要传 `filename`)官方 `field-model` 文档和内嵌 OpenAPI 规范都只写了 `array<object>`,没有给出精确字段表(读格式的 `id`/`filename`/`size`/`thumbnails` 等字段明确标了是响应专用),这是另一处文档缺口,已列入验证计划。
   - 直接上传**本地文件字节**(≤5MB)要用完全不同的域名和端点:`POST https://content.airtable.com/v0/{baseId}/{recordId}/{attachmentFieldIdOrName}/uploadAttachment`,body 是 base64 编码的 `file` + `contentType` + `filename`,而且**record 必须已经存在**(先创建空记录或已有记录,再对着这条记录的这个字段上传)。超过 5MB 的文件只能走上面的公网 URL 方式。
   - 返回的所有附件 `url` **2 小时后过期**,要长期保存必须下载存到自己的存储,不能只存这个 URL。
5. **单选/多选字段(`singleSelect`/`multipleSelects`)传入的字符串必须和已存在的选项名精确匹配,不匹配会报 `INVALID_MULTIPLE_CHOICE_OPTIONS`**,除非请求带 `typecast: true`(此时会自动新建一个匹配不到的选项)。多选、多协作者、附件这类数组型字段在更新时是**整体覆盖**,不是合并/追加——只传子集会导致原有其它选中项丢失,需要保留时要先读出当前值再拼接新值一起传回去。
6. **链接记录字段(`multipleRecordLinks`)写入时传的是目标 record 的 `array<string>` ID 数组,不是对象数组**(响应里读到的可能是对象数组,取决于 `includeDateDependencyMetadata` 等参数,但写入始终是 ID 字符串数组)。传入非法或不存在的 record ID 会报错还是被忽略、传入目标表的显示文本能否借助 `typecast` 自动匹配/新建链接记录,⚠ 当前抓取的文档没有明确说明,已列入验证计划,不要凭其它平台"upsert 时自动匹配"的经验假设行为。
7. **限流是按 base 维度的,不是全局的**:5 请求/秒/base,另外每个用户(或 service account)名下所有 base 加起来还有 50 请求/秒的总闸。一个 Agent 如果同时操作多个 base,需要**按 baseId 分别维护限流计数器**,而不是用一个全局计数器,否则要么低估(漏算跨 base 的总闸)要么高估(把不同 base 的配额混在一起浪费)。触发 429 后按文档要求**固定等待 30 秒**再重试(不是标准的指数退避,这点和很多其它 REST API 不同),详见 `references/errors-and-rate-limits.md`。
8. **官方与常用 SDK**:唯一被官方文档列为 "Official API client" 的是 JavaScript 的 [`airtable.js`](https://github.com/Airtable/airtable.js)(Node.js + 浏览器均可,内置退避重试)。Python 生态里事实标准是社区维护、但被官方文档并列推荐的 [`pyairtable`](https://github.com/gtalarico/pyairtable)(`pip install pyairtable`),它替调用方处理了批量分批(见第 2 条)、分页迭代、字段名/ID 互转等细节;直接手写 HTTP 请求时这些都要自己实现。

## 目录结构

```
airtable/
├── SKILL.md
├── references/
│   ├── auth-and-scopes.md          个人访问令牌、OAuth、scope 列表、whoami
│   ├── read-and-filter-records.md  List/Get records、分页、view、filterByFormula 公式语法
│   ├── write-records.md            Create/Update/Delete(单条+批量)、upsert、typecast、附件上传
│   ├── field-types-and-schema.md   字段类型全表(读/写/只读)、Metadata API
│   └── errors-and-rate-limits.md   错误码、429 与限流策略、官方/社区 SDK
└── evals/
    └── evals.json
```

内容整理自 `https://airtable.com/developers/web/api`（抓取于 2026-09），实际调用报错优先信任真实 API 返回，而非本文档。
