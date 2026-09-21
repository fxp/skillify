# 搜索与过滤：CRM Search API

目录：[基本形状](#基本形状) · [filterGroups 的 AND/OR 语义](#filtergroups-的-andor-语义——最容易搞反的地方) · [操作符](#过滤操作符) · [通过关联搜索](#通过关联搜索) · [默认可搜索属性](#默认可搜索属性文本模糊搜索) · [排序与分页](#排序与分页) · [限制](#限制)

全部内容 ⚠ 文档原文，未实测（整理自 `docs/api-reference/latest/crm/search-the-crm`，抓取于 2026-09-21）。

## 基本形状

```
POST /crm/objects/v3/{objectType}/search
```

请求体核心字段：`filterGroups`（过滤条件，见下）、`query`（自由文本模糊搜索，跨该对象的默认可搜索属性）、`properties`（要返回的属性数组）、`sorts`（排序规则）、`limit`/`after`（分页）。

```bash
curl -s -X POST "https://api.hubapi.com/crm/v3/objects/contacts/search" \
  -H "Authorization: Bearer $HUBSPOT_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "filterGroups": [
      { "filters": [ { "propertyName": "email", "operator": "CONTAINS_TOKEN", "value": "*@hubspot.com" } ] }
    ]
  }'
```

不显式传 `properties` 时，响应只带该对象的一小组默认属性（例如 contacts 默认只有 `createdate`/`email`/`firstname`/`hs_object_id`/`lastmodifieddate`/`lastname`），不是全部属性——想要别的字段必须显式列出来。

## filterGroups 的 AND/OR 语义——最容易搞反的地方

这是本 skill 明确标记为最高优先级陷阱的行为：

> **`filterGroups` 数组里不同元素之间是 OR。同一个 `filterGroups` 元素内、`filters` 数组里的多个条件之间是 AND。**

用自然语言表达"名字是 Alice 且姓不是 Smith，或者压根没填邮箱"：

```json
{
  "filterGroups": [
    {
      "filters": [
        { "propertyName": "firstname", "operator": "EQ", "value": "Alice" },
        { "propertyName": "lastname", "operator": "NEQ", "value": "Smith" }
      ]
    },
    {
      "filters": [
        { "propertyName": "email", "operator": "NOT_HAS_PROPERTY" }
      ]
    }
  ]
}
```

**记忆方法**：`filterGroups` 的复数形式暗示"多组条件，任一组满足即可"（OR）；单个 group 内部的 `filters` 数组暗示"这一组要求全部同时满足"（AND）。写代码前默念一遍这句话，或者干脆把"要不要拆成多个 group"当成判断题：只要有任何一条"或者"的语义，就必须拆成不同的 `filterGroups` 元素，绝不能塞进同一个 group 的 `filters` 数组里指望它们之间是 OR——那样实际执行的是 AND，会静默返回一个远比预期小（甚至为空）的结果集，而不是报错，非常容易被忽略。

**限制**：最多 **5** 个 `filterGroups`，每组最多 **6** 个 `filters`，全部 `filterGroups` 里的 `filters` 总数不超过 **18** 个。超限报 `VALIDATION_ERROR`（是报错，不是静默截断）。

## 过滤操作符

| Operator | 含义 |
|---|---|
| `LT` / `LTE` / `GT` / `GTE` | 小于/小于等于/大于/大于等于 |
| `EQ` / `NEQ` | 等于/不等于 |
| `BETWEEN` | 区间，用 `value`（下界）+ `highValue`（上界）两个字段，不是数组 |
| `IN` / `NOT_IN` | 在/不在给定列表里，用 `values` 数组（复数），精确匹配；**字符串属性用这两个操作符时，`values` 里的值必须是小写**，否则匹配不到 |
| `HAS_PROPERTY` / `NOT_HAS_PROPERTY` | 该属性有值/没有值，不需要 `value` 字段 |
| `CONTAINS_TOKEN` / `NOT_CONTAINS_TOKEN` | 包含/不包含某个 token，支持 `*` 通配符（如 `*@hubspot.com`） |

大小写规则：**大多数过滤值不区分大小写**，但两个例外——① 过滤枚举（`enumeration`）类型属性时，**所有**操作符都区分大小写；② 用 `IN`/`NOT_IN` 过滤字符串属性时，`values` 必须是全小写。

`BETWEEN` 示例：

```json
{ "propertyName": "hs_lastmodifieddate", "operator": "BETWEEN", "value": "1579514400000", "highValue": "1642672800000" }
```

`IN` 示例（注意 `values` 数组 + 小写）：

```json
{ "propertyName": "enumeration_property", "operator": "IN", "values": ["value_1", "value_2"] }
```

## 通过关联搜索

用伪属性 `associations.{objectType}` 当作过滤条件的 `propertyName`，`value` 传目标记录 ID：

```json
{ "filters": [ { "propertyName": "associations.contact", "operator": "EQ", "value": "123" } ] }
```

**⚠ 自定义对象之间的关联目前不支持通过 search 端点搜索**（文档原文明确写出这条限制），要用 `references/associations.md` 里的关联 API 单独查。

## 默认可搜索属性（文本模糊搜索）

不传 `filterGroups`、只传顶层 `query` 时，是在该对象一组**固定的默认文本属性**里做模糊匹配（不是全部属性）。例如 contacts 默认搜 `firstname`/`lastname`/`email`/`phone`/`hs_additional_emails`/`fax`/`mobilephone`/`company`/`hs_marketable_until_renewal`；companies 默认搜 `website`/`phone`/`name`/`domain`；deals 默认搜 `dealname`/`pipeline`/`dealstage`/`description`/`dealtype`；custom objects 默认搜账号为该对象指定的最多 20 个 `searchableProperties`。**这份默认搜索属性列表和 `properties` 参数控制的"返回哪些属性"是两回事**，`query` 搜到的字段不代表这些字段就会出现在响应里，展示字段照样要靠 `properties` 参数单独指定。

⚠ 过滤 calls/conversations/emails/meetings/notes/tasks 时，`hs_body_preview_html` 属性**不支持**作为过滤条件；emails 额外还有 `hs_email_html`、`hs_body_preview` 两个也不支持。

## 排序与分页

排序：`sorts` 数组，**只能有一条排序规则**（不支持多字段排序）：

```json
{ "sorts": [ { "propertyName": "createdate", "direction": "DESCENDING" } ] }
```

不传时默认按创建时间升序（最早创建的在前）。

分页：`limit`（默认 10，单页最大 **200**）+ `after`（取自上次响应 `paging.next.after`，必须格式化成整数字符串）。没有 `paging.next` 字段就代表没有下一页了。

## 限制

- Search 端点有**独立于**通用对象 API 的限流：**每秒 5 次请求**（不是每 10 秒多少次那套通用burst 限制）。
- Search 响应**不带任何** `X-HubSpot-RateLimit-*` 限流响应头，没法从响应头里读剩余配额，只能靠客户端自己节流到 5 QPS 以内。
- **单次查询最多返回 10,000 条结果**（`total` 字段可能显示更大的数字，但翻页翻到超过 10,000 会直接报 400），需要拿更多结果得缩小过滤条件分批查，而不是无限翻页。
- 单页最多 200 条（`limit` 参数上限）。
- 请求体 `query` 字段最长 3,000 字符，超过报 400。
- 新创建/更新的记录**不保证立即**出现在搜索结果里（有索引延迟，⚠ 文档未说明具体延迟量级，官方原文只写"可能需要几分钟"）。
- 已归档（删除）的记录不会出现在任何搜索结果里。
- 搜索电话号码属性时，HubSpot 内部用 `hs_searchable_calculated_*` 开头的计算属性做标准化匹配，**只取区号+本地号码**，过滤条件里不要带国家代码，否则匹配不到。
