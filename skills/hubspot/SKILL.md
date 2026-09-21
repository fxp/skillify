---
name: hubspot
description: 接入 HubSpot CRM API（developers.hubspot.com，api.hubapi.com）的开发手册，供构建管理 CRM 数据（联系人 contacts、公司 companies、交易 deals、自定义对象）的 AI Agent 使用——涵盖鉴权（私有应用 access token / 新版 Service Key beta / OAuth 应用与 scopes 模型）、统一的 crm/objects/{objectType} 对象增删改查、关联（associations，独立 API，不是字段）、搜索与过滤（filterGroups 的 AND/OR 语义）、批量操作（batch 端点及其硬上限）、自定义对象与自定义属性、限流（burst + daily 双重限制）与错误处理。当用户提到 "HubSpot" "hubapi.com" "developers.hubspot.com" "hubspot-api-client" "@hubspot/api-client" "private app access token" "HubSpot CRM API"，或要写代码调用 HubSpot 管理联系人/公司/交易/关联/自定义对象时，应主动使用本技能——不要凭训练记忆假设 HubSpot 仍用旧式 API Key（`hapikey`）鉴权（已弃用多年，现为私有应用 access token / OAuth），也不要把 `company` 这类文本属性误当成真实关联、或把 filterGroups 的 AND/OR 顺序搞反。
---

# HubSpot CRM API 接入指南

HubSpot 的 CRM API 以统一的"对象"模型组织：contacts（联系人）、companies（公司）、deals（交易）、tickets 等标准对象，以及账户自定义的 custom objects，全部共用同一套 `crm/objects/{objectType}` 增删改查、批量、搜索端点形状。本 skill 覆盖：鉴权、核心对象 CRUD、associations（对象间关联）、search（filterGroups 过滤）、batch（批量操作）、自定义对象/自定义属性、错误与限流。目标是 Agent 第一次写调用 HubSpot API 的代码就能跑通，而不是套用其他 CRM（Salesforce、Pipedrive 等）或训练记忆里过时的 HubSpot API Key 鉴权方式。

## ⚠ 验证状态

**文档版：内容整理自 `https://developers.hubspot.com/docs`（llms.txt 索引 + 官方 OpenAPI 规范片段 + Markdown 源页，抓取于 2026-09-21），尚未用真实 API Key 调用验证，也没有做 with/without skill 的对照实验。**

- 端点路径、参数、请求/响应示例：来自官方文档页面内嵌的 OpenAPI 片段与正文代码块，是当前最权威的公开材料，但**未实测**。
- 报错文案、状态码、限流数字：来自 `usage-guidelines.md`、`error-handling.md`、`crm/objects/*/guide` 等页面转录，同样**未实测**，全部标 `⚠ 文档原文，未实测`。
- 本 skill 抓取时发现文档站本身存在多处自相矛盾（见下方"跨领域通用规则"第 1、7 条），已如实标注、未擅自裁决对错。
- 拿到真实 Key 后的验证优先级清单见 `hubspot-workspace/verification-plan.md`；`evals/evals.json` 里的期望输出是"文档说应该这样"的假设，不是已验证结论。

## 用之前先确认 3 件事

1. **Base URL 固定为 `https://api.hubapi.com`**，所有 CRM 端点都在这个域名下（文档站 `developers.hubspot.com` 只是文档，不是 API 域名）。
2. **鉴权已不是"HubSpot API Key"**。HubSpot 多年前已弃用那种全局 `hapikey`（在所有请求上拼 `?hapikey=xxx` 的旧式全权限 key）作为标准 CRM 鉴权方式——**这是训练语料里最常见、但现在已经错的假设**。当前用 `Authorization: Bearer <token>` 请求头，token 来自私有应用（legacy private app）access token 或新版 Service Key（beta），两者格式都是 `pat-na1-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` 这样的前缀 token；只有极少数遗留的开发者账号级端点还认那个老 `hapikey` query 参数，跟 CRM 对象 API 无关。详见 `references/auth.md`。
3. **最容易选错的字段：CRM 对象属性的"内部名"和 HubSpot UI 上看到的"显示标签"经常不同**（例如 UI 上的 *Favorite Food* 字段，内部名可能是 `favorite_food`；生命周期阶段 UI 显示 *Marketing Qualified Lead*，内部值是 `marketingqualifiedlead`；自定义生命周期阶段的内部值甚至是纯数字字符串）。照着 UI 标签猜 API 属性名大概率错，必须调用 `GET /crm/properties/v3/{objectType}` 核对。详见 `references/objects.md`。

## 30 秒跑通第一个请求

最便宜、最常用的组合：用私有应用 access token 读取 10 条联系人。

```bash
curl -s "https://api.hubapi.com/crm/v3/objects/contacts?limit=10&archived=false" \
  -H "Authorization: Bearer $HUBSPOT_ACCESS_TOKEN"
```

```python
import os, requests

resp = requests.get(
    "https://api.hubapi.com/crm/v3/objects/contacts",
    headers={"Authorization": f"Bearer {os.environ['HUBSPOT_ACCESS_TOKEN']}"},
    params={"limit": 10, "archived": "false"},
)
resp.raise_for_status()
print(resp.json())
```

官方 SDK：Python `pip install hubspot-api-client`（PyPI 最新 12.0.0，仓库 `HubSpot/hubspot-api-python`）；Node `npm install @hubspot/api-client`（npm 最新 14.x，仓库 `HubSpot/hubspot-api-nodejs`）。SDK 内部就是对这套 REST API 的封装，字段名和这里文档的一致，遇到 SDK 方法不确定时直接看它底层调用的 endpoint。⚠ 文档原文，未实测。

## 能力域导航

| 我想做什么 | 参考文件 | 涉及的核心 endpoint |
|---|---|---|
| 搞清楚用私有应用 token 还是 OAuth 应用、scopes 怎么选、token 怎么拿 | `references/auth.md` | `/oauth/v1/token`、私有应用 token（控制台生成，非 API） |
| 增删改查 contacts / companies / deals / 任意标准对象，属性内部名 vs 显示标签，自定义对象与自定义属性（schemas API） | `references/objects.md` | `POST/GET/PATCH/DELETE /crm/objects/{version}/{objectType}[/{id}]`、`/crm/properties/{version}/{objectType}`、`/crm-object-schemas/{version}/schemas` |
| 把两条记录关联起来（联系人挂到公司、交易挂到联系人），带标签的关联、查一条记录的所有关联 | `references/associations.md` | `PUT/GET/DELETE /crm/objects/{version}/{fromType}/{id}/associations/{toType}/{toId}`、`/crm/associations/{version}/{fromType}/{toType}/batch/*` |
| 按属性值筛选/搜索记录，多条件组合，通过关联搜索 | `references/search.md` | `POST /crm/objects/{version}/{objectType}/search` |
| 一次请求创建/读取/更新/upsert/删除多条记录，避免限流 | `references/batch.md` | `POST /crm/objects/{version}/{objectType}/batch/{create,read,update,upsert,archive}` |
| 处理报错、算限流（burst + daily 两套限制）、重试策略 | `references/errors-and-limits.md` | 全端点通用；`X-HubSpot-RateLimit-*` 响应头 |

## 跨领域的通用规则（写代码前必读）

以下每条都标了来源，多数**未经真实调用验证**：

1. **⚠ 文档自相矛盾——同一个"API Limit Increase"加购项的 burst 限速，两处官方文档给的数字不一样**：`docs/apps/legacy-apps/private-apps/overview`（私有应用页）写购买后是 **200 次/10 秒**；`docs/developer-tooling/platform/usage-guidelines`（限流总页）写的是 **250 次/10 秒**。两页都是当前有效文档，抓取时间同为 2026-09。没有真实账号无法裁决哪个对，**以响应头 `X-HubSpot-RateLimit-Max` 的实际返回值为准**，不要硬编码任一个数字做限速预算。详见 `references/errors-and-limits.md`。
2. **关联（association）不是记录上的一个字段，是独立的 API 调用/独立对象**。HubSpot 自己的文档示例里就有这个陷阱的活证据：创建联系人时文档给出的示例请求体里，`company: "HubSpot"` 是一个纯文本属性（历史遗留，只是字符串，不建立任何可查询关系），要让这条联系人真正"挂"在一家公司记录下（能在公司详情页的关联联系人列表里看到、能被交易汇总、能被 associations API 查到），必须**另外**在 `associations` 数组里传目标公司的 `id` + `associationTypeId`，或者事后调用 `PUT /crm/objects/{v}/contacts/{id}/associations/companies/{companyId}/{typeId}`。只设置 `company` 文本字段会"看起来做对了"（属性确实保存了公司名字符串）但不会创建任何真实关联，静默失败。详见 `references/associations.md`。
3. **Search 的 `filterGroups` 之间是 OR，同一个 `filterGroups` 内的 `filters` 之间是 AND**——这个方向非常容易记反。要表达"A 且 B"：把两个 filter 放进同一个 `filterGroups[].filters` 数组；要表达"A 或 B"：把它们分别放进两个不同的 `filterGroups` 元素。最多 5 个 `filterGroups`，每组最多 6 个 `filters`，总数不超过 18 个，超限报 `VALIDATION_ERROR`。详见 `references/search.md`。
4. **属性的"内部名"（`name`）≠ HubSpot UI 上看到的"标签"（`label`）**，二者在创建属性时都要传，但读写记录只用 `name`。同理，`dealstage`、`pipeline`、`lifecyclestage`、自定义下拉/单选属性的取值也必须是内部值（常是全小写、下划线分隔的字符串，自定义阶段可能是纯数字字符串），不是 UI 上的展示文字；照着界面截图里看到的文字直接拼进请求体大概率是错的，先 `GET /crm/properties/{v}/{objectType}` 或对应的 pipelines/lifecycle 端点核对。
5. **Batch 端点硬上限 100 条/请求**（`batch/create`、`batch/read`、`batch/update`、`batch/upsert`、`batch/archive`，标准对象和自定义对象都一样）。超过 100 条不是自动分页处理，而是直接报错，需要自己在客户端分批。Associations 的批量端点上限不同（`batch/read` 1000、`batch/create` 2000、`batch/archive`/`batch/labels/archive` 100），不要和对象 batch 的 100 混用同一个假设。详见 `references/batch.md`。
6. **鉴权已从"一把全权限 API Key"变成"按 scope 授权的 token"**，且 scope 本身还分敏感度档位：多数标准 CRM 对象既有基础 `crm.objects.<object>.read/write`，也有 `.sensitive.<read|write>.v2` / `.highly_sensitive.<read|write>.v2` 两档，只在账号开通 Enterprise 的敏感数据属性功能时用得到。⚠ 未实测：拥有基础 read scope 但没有 sensitive scope 时，`GET` 记录默认是否会连非敏感属性一起报错，还是只是悄悄不返回敏感属性（文档措辞暗示是后者——不带 `dataSensitivity=sensitive` 查询参数时默认只返回非敏感属性）。
7. **⚠ 文档自相矛盾/新变化——2026-09 起 HubSpot 对 CRM 写操作强制执行管理员配置的校验规则**：文档原文写"Starting with the GA release of API version `/2026-09/` on September 8, 2026, HubSpot will enforce admin-configured validation rules on all CRM API write paths"，出现在 `properties/guide` 和 `crm/using-object-apis` 两个页面，但措辞是否只影响走 `/2026-09/` 路径前缀的请求、还是影响所有版本前缀（含 legacy `v3`）的写请求，文档没有明确说清楚。这是训练语料截止后新出现的行为，**之前能跑通的写请求现在可能因为账号新增的校验规则而报错**，优先验证项之一，见 `hubspot-workspace/verification-plan.md`。
8. **`/crm/v3/objects/...` 和 `/crm/objects/2026-09/...` 目前都能用，但连 HubSpot 自己当前文档里也没统一**：2026-09 起 HubSpot 把 REST API 改成按日期命名版本（如同 Stripe），`v1`-`v4` 等旧式语义化版本号"legacy 版本"仍在原路径上完全可用（官方明确承诺：GA 后 Current 6 个月、Supported 6 个月、18 个月后才 Unsupported）。但即使是 2026-09 抓取的当前文档，新写的指南页（Search、Associations、Properties、Using Object APIs）示例已经全部换成 `/crm/objects/2026-09/...`，而同样是 2026-09 新发布的 Service Key beta 指南、以及私有应用总览页的示例代码，仍然用的是 `/crm/v3/objects/...`。本 skill 的代码示例统一用 `v3`（目前用得最广、和官方 SDK 及第三方集成最兼容的写法），但两种前缀在文档描述的行为上是等价的（除第 7 条提到的写校验强制执行范围未定论外），需要 2026-09 独有字段/行为时才切到 `2026-09`。

## 目录结构

```
hubspot/
├── SKILL.md
├── references/
│   ├── auth.md               # 私有应用 access token / Service Key beta / OAuth 应用、scopes 模型
│   ├── objects.md            # contacts/companies/deals 等标准对象 CRUD、属性 API、自定义对象与 schemas API
│   ├── associations.md       # 关联 API（不是字段）、关联类型 ID 表、按关联搜索
│   ├── search.md             # CRM Search API、filterGroups AND/OR、操作符、排序分页
│   ├── batch.md              # 批量创建/读取/更新/upsert/删除、各批量端点的硬上限
│   └── errors-and-limits.md  # 错误响应结构、HTTP 状态码、burst+daily 限流、重试
└── evals/
    └── evals.json            # 5 个"有经验的开发者会凭其他 CRM/旧版 HubSpot 直觉写错"的场景（未验证，期望输出是假设）
```

内容整理自 `https://developers.hubspot.com/docs`（llms.txt 索引 + OpenAPI 规范片段，抓取于 2026-09-21）。**这份文档的抓取日期晚于本模型的训练截止日期（2026-01），HubSpot 在此期间发布了日期版本化 API（2026-09）、Service Key beta、2026-09 起的 CRM 写校验强制执行**，凭训练记忆写 HubSpot 代码本身就不完全可靠，务必读 reference 文件而不是靠记忆编参数。实际调用报错优先信任 API 返回，其次信任本 skill 标了验证日期的结论，最后才是未标注来源的转录内容。
