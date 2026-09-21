# 关联对象（Associations）——独立的 API，不是记录上的字段

目录：[核心认知](#核心认知) · [创建时内联关联](#创建记录时内联关联) · [事后关联/取消关联](#事后关联单条) · [批量关联端点](#批量关联端点) · [查询记录的关联](#查询一条记录的关联) · [关联类型 ID 表](#默认关联类型-id-常用组合) · [限流](#限流)

全部内容 ⚠ 文档原文，未实测（整理自 `docs/api-reference/latest/crm/associations/associate-records/guide`、`crm/understanding-the-crm`，抓取于 2026-09-21）。

## 核心认知

**HubSpot 里"两条记录之间有关系"这件事，永远是一次独立的 API 写操作（或者创建时 payload 里一个独立的 `associations` 数组），绝不是在某条记录的 `properties` 里塞一个"外键"字段。** 这是本 skill 反复强调的最大陷阱，因为它和关系型数据库的直觉（"公司表有个 `contact_id` 外键列"）完全相反,而且 HubSpot 自己的对象上恰好**存在**几个名字像是外键、实际只是纯文本的历史遗留属性（联系人的 `company` 就是最典型的例子，见 `references/objects.md`）,极容易让人误以为设置这类字段就等于建立了关联。

判断关联是否"真实存在"的标准：能不能被 associations API 查到、能不能在 HubSpot 记录详情页对应的关联卡片里看到、能不能被依赖关联的汇总/自动化用到（比如交易金额按公司汇总）。只写了一个同名文本属性，以上全部不成立。

Associations API 有两组端点：

- **Association details**（本文件主要内容）：创建/编辑/删除具体两条记录之间的关联。
- **Association schema**（`/crm/associations/v3/{fromObjectType}/{toObjectType}/labels` 等）：管理账号级别"这两类对象之间允许哪些关联标签"的定义，自定义对象必须先在 schema 里声明关联对象类型（见 `references/objects.md`），自定义标签也要在这里创建。本文件只讲怎么用已存在的关联类型去关联记录，不讲怎么定义新标签。

## 创建记录时内联关联

创建/批量创建记录的请求体里可以带一个 `associations` 数组，一步到位建好关联：

```json
{
  "properties": { "dealname": "New deal", "dealstage": "contractsent", "pipeline": "default" },
  "associations": [
    {
      "to": { "id": "201" },
      "types": [{ "associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 5 }]
    },
    {
      "to": { "id": "301" },
      "types": [{ "associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3 }]
    }
  ]
}
```

- `to.id`：目标记录的 ID。
- `types`：一个记录对之间可以同时挂多个标签（比如既是"默认关联"又是"决策人"），每个标签用 `{associationCategory, associationTypeId}` 表示。
- `associationCategory`：`HUBSPOT_DEFINED`（HubSpot 内置的默认标签，如"Primary company"）或 `USER_DEFINED`（账号自定义标签）。⚠ 文档在别处还提到 `INTEGRATOR_DEFINED`、`WORK` 两个枚举值，但没有给出使用场景，未验证什么情况下会用到。

## 事后关联（单条）

**不带标签**（默认关联）：

```
PUT /crm/objects/v3/{fromObjectType}/{fromObjectId}/associations/default/{toObjectType}/{toObjectId}
```

**带标签**：

```
PUT /crm/objects/v3/{fromObjectType}/{fromObjectId}/associations/{toObjectType}/{toObjectId}
```
请求体是一个标签数组（注意不是单个对象，是数组，哪怕只传一个标签）：
```json
[{ "associationCategory": "USER_DEFINED", "associationTypeId": 36 }]
```

**取消关联**：同样的 URL 形状换成 `DELETE`。删除全部关联标签会让两条记录彻底不再关联；如果只想移除某个特定标签、保留其他标签（含默认无标签关联），用下方批量"移除指定标签"端点，不要用这个会删光所有标签的单条 DELETE。

`fromObjectType`/`toObjectType` 可以用标准对象名（`contact`/`company`/`deal`……，注意这里官方示例用的是**单数**，和 `crm/objects/v3/{objectType}` 端点用**复数**不一致，⚠ 容易搞混，务必对照具体端点的示例确认单复数）或 `objectTypeId`。

## 批量关联端点

批量端点走的是完全不同的路径前缀 `/crm/associations/v3/`（不是 `/crm/objects/v3/.../associations`）：

| 操作 | Endpoint | 单请求上限 |
|---|---|---|
| 批量建立默认（无标签）关联 | `POST /crm/associations/v3/{fromObjectType}/{toObjectType}/batch/associate/default` | ⚠ 文档未单独标注，参照批量创建关联上限 2000 |
| 批量建立带标签的关联 | `POST /crm/associations/v3/{fromObjectType}/{toObjectType}/batch/create` | **2,000** inputs |
| 批量读取关联 | `POST /crm/associations/v3/{fromObjectType}/{toObjectType}/batch/read` | **1,000** inputs |
| 批量移除全部关联（记录对） | `POST /crm/associations/v3/{fromObjectType}/{toObjectType}/batch/archive` | **100** 个唯一 `from` 输入 |
| 批量移除指定标签（保留其他标签） | `POST /crm/associations/v3/{fromObjectType}/{toObjectType}/batch/labels/archive` | **100** inputs |

批量读取示例（拿多条联系人各自关联的公司）：

```json
{ "inputs": [{ "id": "33451" }, { "id": "29851" }] }
```

响应按 `from` 分组，每个 `to` 记录带着它当前挂的所有标签：

```json
{
  "status": "COMPLETE",
  "results": [
    {
      "from": { "id": "33451" },
      "to": [
        {
          "toObjectId": 5790939450,
          "associationTypes": [
            { "category": "HUBSPOT_DEFINED", "typeId": 1, "label": "Primary" },
            { "category": "USER_DEFINED", "typeId": 28, "label": "Billing contact" }
          ]
        }
      ]
    }
  ]
}
```

## 查询一条记录的关联

`GET /crm/objects/v3/{fromObjectType}/{objectId}/associations/{toObjectType}`——单条记录、单个目标对象类型的场景用这个；批量场景（多条记录，或想在读记录的同时把关联一起拿回来）用上面批量读接口或在 `GET .../{objectType}/{id}` 上加 `?associations={toObjectType}` 参数（仅限单条 GET，批量 GET 不支持这个参数，见 `references/objects.md`）。

## 默认关联类型 ID（常用组合）

以下 `associationTypeId` 是 HubSpot 内置的默认标签，`associationCategory` 都是 `HUBSPOT_DEFINED`。自定义标签的 ID 因账号而异，要通过 `GET /crm/associations/v3/{fromObjectType}/{toObjectType}/labels` 现查。**方向敏感**：contact→company 和 company→contact 是两个不同的 ID，别搞反。

| From → To | typeId | 说明 |
|---|---|---|
| Contact → Company | `279` | 普通关联 |
| Contact → **Primary** Company | `1` | 标记为该联系人的主公司 |
| Contact → Deal | `4` | |
| Contact → Ticket | `15` | |
| Company → Contact | `280` | 普通关联 |
| Company → **Primary** Contact | `2` | |
| Company → Deal | `342` | |
| Company → **Primary** Deal | `6` | |
| Company → Ticket | `340` | |
| Company → Company（母子公司） | `13`（parent→child）/ `14`（child→parent） | |
| Deal → Contact | `3` | |
| Deal → Company | `341` | |
| Deal → **Primary** Company | `5` | |
| Deal → Ticket | `27` | |
| Deal → Line item | `19` | |
| Ticket → Contact | `16` | |
| Ticket → Company | `339` | |
| Ticket → Deal | `28` | |

完整表（含订单、发票、报价、活动类记录等全部对象组合，近 200 组）见抓取的原文 `hubspot-workspace/scratch/pages/associate-records-guide.md`，需要时按对象名搜索原文件而不要在这里全部展开。**⚠ 存在一套独立的 v1（更早的旧版本）associations 类型 ID 表**，数值和这套现行默认表大部分重合但不完全一致（例如 v1 表里 "Company to contact (all labels)" 是 `280`，和现行表的 company→contact `280` 一致，但 v1 表额外区分了 "Company to contact (default)" = `2`，现行表里 `2` 的含义是 company→primary contact，需要用哪一套要看你对接的是新旧哪个版本的接口，不要把两套表混用）。

## 限流

关联 API 的限流是**独立**于对象 API 通用限流的一套数字（见 `references/errors-and-limits.md` 的通用表之外）：

- 每日：Professional / Enterprise 账号 **500,000** 次；购买 API Limit Increase 后最高 **1,000,000** 次/天（这个上限**不会**因为额外购买多份加购而继续叠加）。
- 每 10 秒 burst：Free/Starter **100** 次，Professional/Enterprise **150** 次；购买 API Limit Increase 后最高 **200** 次/10秒（同样不因多份加购继续叠加）。

⚠ 注意这几个数字和"私有应用总览页"/"限流总页"关于对象 API 通用 burst 限速互相矛盾的那两组数字（见 SKILL.md 通用规则第 1 条）都不是同一件事——关联 API 有自己独立的一套官方给出的数字，且**加购 API Limit Increase 对关联 API 请求上限的提升幅度和对普通对象 API 的提升幅度不是同一个数字**，预算并发额度时不要混用。

购买了 API 加购套餐后想知道自己账号有多少即将接近关联数量上限的记录，可以调 `POST /crm/associations/v3/usage/high-usage-report/{userID}` 生成一份报告（用到 80% 以上限额的记录会被列出），报告会发到该 `userID` 对应用户的邮箱。
