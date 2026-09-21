# 读取与过滤记录

目录：[List records](#list-records) · [Get record](#get-record) · [分页](#分页-offsetpagesizemaxrecords) · [filterByFormula 公式语法（重点）](#filterbyformula-公式语法重点) · [其它查询参数](#其它查询参数)

## List records

**Endpoint**: `GET https://api.airtable.com/v0/{baseId}/{tableIdOrName}`
**用途**: 列出一张表里的记录，支持分页、排序、过滤、字段裁剪。`tableIdOrName` 可以传表名也可以传表 ID，官方建议用 ID（`tblXXXXXXXXXXXXXX`），避免表改名后调用当场失效。
**Scope / 权限**: `data.records:read`，base 只读即可。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `pageSize` | number | 否 | 100 | 每页记录数，**必须 ≤ 100** |
| `maxRecords` | number | 否 | 无上限 | 总共最多返回多少条，跨多页时会在达到这个数后停止翻页 |
| `offset` | string | 否 | — | 上一页响应里的 `offset`，传入以取下一页 |
| `view` | string | 否 | — | view 名字或 ID，只返回该 view 内的记录，且默认按该 view 的排序（除非同时传了 `sort`）。view 里被隐藏的字段依然会被返回，要裁剪字段用 `fields` 参数 |
| `sort` | array\<{field, direction}\> | 否 | — | `direction` 是 `"asc"`/`"desc"`，默认 `"asc"`；会覆盖 `view` 自带的排序 |
| `filterByFormula` | string | 否 | — | 见下方专门章节 |
| `fields` | array\<string\> | 否 | 全部字段 | 只返回列出的字段（名字或 ID），减少传输量 |
| `cellFormat` | `"json"` \| `"string"` | 否 | `"json"` | `"string"` 会把所有 cell 格式化成用户可见的字符串，此时必须同时传 `timeZone` 和 `userLocale`；官方明确说不要依赖这个字符串格式的具体样式，随时可能变 |
| `returnFieldsByFieldId` | boolean | 否 | `false` | `true` 时响应里的 `fields` 对象用字段 ID 做 key 而不是字段名 |
| `recordMetadata` | array\<`"commentCount"`\> | 否 | — | 传了才会在每条记录里附带 `commentCount` |

**示例请求**

```bash
curl -G "https://api.airtable.com/v0/{baseId}/{tableIdOrName}" \
  -H "Authorization: Bearer $AIRTABLE_TOKEN" \
  --data-urlencode "pageSize=50" \
  --data-urlencode "view=Grid view" \
  --data-urlencode "filterByFormula={Status}=\"Active\""
```

```python
import requests

resp = requests.get(
    f"https://api.airtable.com/v0/{base_id}/{table}",
    headers={"Authorization": f"Bearer {token}"},
    params={"pageSize": 50, "view": "Grid view", "filterByFormula": '{Status}="Active"'},
)
```

**示例响应**

```json
{
  "records": [
    {"id": "rec560UJdUtocSouk", "createdTime": "2022-09-12T21:03:48.000Z",
     "fields": {"Name": "Union Square", "Visited": true}}
  ],
  "offset": "itr23sEjsdfEr3282/rec3lbPRG4aVqkeOQ"
}
```

"空值"字段（`""`、`[]`、`false`）不会出现在 `fields` 里——读完之后不要假设某个字段"没出现"就等于报错或字段不存在，也可能只是当前值为空。

**注意事项**

- **URL 长度上限 16000 字符**：`filterByFormula` 编码后很容易超限（复杂公式 + URL 编码膨胀）。超限时改用 `POST https://api.airtable.com/v0/{baseId}/{tableIdOrName}/listRecords`，把同样这些参数放进请求体（而不是 query string）发送，其它行为不变。`fields`、长 `sort` 数组同理可能撞到这个上限。
- **游标式分页会超时**：`offset` 对应的服务端游标可能因为客户端翻页太慢或服务端重启而失效，此时返回 `422 LIST_RECORDS_ITERATOR_NOT_AVAILABLE`，需要从第一页重新开始翻页，不能从半途的 `offset` 续。
- 用 `view` 时字段依然全量返回（不受 view 里"隐藏某些列"的影响），只有记录的**集合和排序**受 view 限定；要精简字段用 `fields` 参数。

## Get record

**Endpoint**: `GET https://api.airtable.com/v0/{baseId}/{tableIdOrName}/{recordId}`
**用途**: 取单条记录。参数（`cellFormat`、`returnFieldsByFieldId`）与 List records 一致，但没有分页/过滤相关参数。
**Scope / 权限**: `data.records:read`，base 只读即可。

**注意事项**：官方文档原文提到一个容错行为——"如果在给定 table 里找不到这条记录，请求会退化成整个 base 范围的搜索，只要这个 record ID 合法、且记录确实在同一个 base 里，依然会返回它"。也就是说 `tableIdOrName` 传错了表（但 base 对、record ID 对）不一定会 404，这点和大多数 REST API"路径不匹配就 404"的直觉不同，写"校验记录属于哪张表"的逻辑时不能只靠这个 endpoint 是否成功来判断。

## 分页（offset/pageSize/maxRecords）

标准游标分页：

1. 第一次请求不传 `offset`。
2. 响应里如果有 `offset` 字段，说明还有下一页；把它原样传入下一次请求的 `offset` 参数。
3. 响应里**没有** `offset` 字段，说明已经是最后一页。
4. 如果传了 `maxRecords`，会在总数达到这个值后提前停止翻页（哪怕原本还有更多）。

```python
def list_all_records(base_id, table, headers, filter_formula=None):
    records, offset = [], None
    while True:
        params = {"pageSize": 100}
        if filter_formula:
            params["filterByFormula"] = filter_formula
        if offset:
            params["offset"] = offset
        r = requests.get(f"https://api.airtable.com/v0/{base_id}/{table}",
                          headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        records.extend(data["records"])
        offset = data.get("offset")
        if not offset:
            return records
```

`pyairtable`/`airtable.js` 都内置了等价的自动翻页迭代器，手写 HTTP 请求时才需要自己写这个循环。

## filterByFormula 公式语法（重点）

**这是最容易被误用的参数**。`filterByFormula` 的值是 **Airtable 自有的公式语言**的一个字符串表达式（和 Airtable 里"公式字段"用的是同一套语言），**不是 SQL，也不是 MongoDB/Pinecone 那种 `{field: {$gt: value}}` 风格的过滤对象**。公式对每条记录求值，结果不是 `0`/`false`/`""`/`NaN`/`[]`/`#Error!` 这几种"假值"的记录就会被保留。

### 基本语法要点（来自 `support.airtable.com` 公式函数参考，抓取于 2026-09-21）

- **字段引用**：单个单词的字段名可以裸写（如 `Price`），**包含空格或特殊字符的字段名必须用花括号包起来**（如 `{Sale Price}`）。也可以用字段 ID 代替字段名引用（字段改名不会打断公式）。
- **比较运算符**：`=`（等于，不是 `==`）、`!=`（不等于）、`>`、`<`、`>=`、`<=`。
- **逻辑组合用函数，不是符号**：`AND(expr1, expr2, ...)`、`OR(expr1, expr2, ...)`、`NOT(expr)`——**没有 `&&`/`||`/`!` 这种运算符写法**。
- **字符串字面量用双引号**：`{Status} = "Active"`。
- 常用函数举例（完整列表见官方公式函数参考）：`IF(expr, then, else)`、`BLANK()`、`FIND()`/`SEARCH()`、`LEN()`、`LEFT()`/`RIGHT()`、`DATETIME_DIFF()`、`IS_BEFORE()`/`IS_AFTER()`、`ARRAYJOIN()`。

### 示例

```
AND({Status} = "Active", {Priority} > 3)
```

```
OR({Stage} = "Won", {Stage} = "Closed")
```

```
NOT({Archived})
```

```
SEARCH("urgent", LOWER({Notes})) > 0
```

### ⚠ 头号陷阱：不要传 MongoDB/Pinecone 风格的过滤对象

如果 Agent 刚写过 Pinecone/MongoDB 一类数据库的过滤器代码，很容易把 `filterByFormula` 也写成这样：

```python
# 错误：filterByFormula 不接受这种结构，Airtable 会把它当普通字符串处理
params = {"filterByFormula": {"Status": {"$eq": "Active"}}}
```

**这不会报错**——大多数 HTTP 客户端会把这个 dict 序列化成某种字符串（或者直接报参数类型错误，取决于客户端），但即使侥幸序列化成了字符串，Airtable 收到的也只是一段不构成合法公式语法的文本，公式求值结果通常是 `#Error!` 或恒为假，导致返回值要么是全部记录（`filterByFormula` 参数被忽略/求值失败时的具体行为⚠文档未明确说明，未实测确认）要么是空结果——**没有任何报错提示你传错了格式**。正确写法永远是上面"示例"里那种公式字符串。

### 编码与请求方式

- 公式必须先做 URL 编码才能作为 query string 的值。Airtable 官方提供了一个 [URL 编码小工具](https://codepen.io/airtable/full/MeXqOg)。用 `requests`/`axios` 等库的 `params`/`data` 机制传参时库会自动处理编码，手动拼 URL 字符串时容易漏掉。
- 编码后的公式很容易让整个 URL 超过 16000 字符上限，超限时改用 `POST /v0/{baseId}/{tableIdOrName}/listRecords`（body 传参，见上文）。
- `filterByFormula` 里既可以用字段名也可以用字段 ID。
- 和 `view` 参数一起用时是交集：先限定在该 view 的记录范围内，再应用公式过滤。

## 其它查询参数

- `includeDateDependencyMetadata`（List/Get 都有）：`true` 时链接记录字段返回 `{id, dateDependencyMetadata?}` 对象数组而不是纯 record ID 字符串数组；只有配置了日期依赖（date dependency，项目管理类模板的功能）的链接字段才会带 `dateDependencyMetadata`。
- `timeZone`/`userLocale`：只有 `cellFormat=string` 时才需要，且此时是必填。
