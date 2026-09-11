# 查询条件、分页与深翻页

> 来源：https://developer.fxiaoke.com/openapi_v2/ 的「字段值说明（根据条件查询对象接口字段说明）」、各对象「根据条件查询…列表」页、
> 「深翻页文档」「查看如何获取列表中的查询条件」、「根据条件查询对象数据，只做基本的数据查询 / 只返回一条数据」页（抓取于 2026-09-11），
> 旧版 wiki「CRM对象接口调用说明」（artiId=1146）。**本文件全部为文档原文，未实测。**
> 请求头、thirdTraceId、`FxkClient` 见 `auth.md`。

## 目录
1. 查询接口一览
2. search_query_info 结构
3. operator 全表
4. 分页规则：limit ≤100、offset 为 limit 整数倍、offset ≤10000
5. 深翻页：用 `_id` 游标代替 offset
6. 要不要总数：三种参数名
7. 响应结构
8. findSimple / findOne
9. 完整示例：全量拉取客户
10. 从页面上抄查询条件
11. 本文件的 ⚠

---

## 1. 查询接口一览

| 场景 | Endpoint | 说明 |
| --- | --- | --- |
| 预置对象列表查询 | `POST /cgi/crm/v2/data/query` | 客户、联系人、线索、商机、部门、人员…… |
| 自定义对象（`__c`）列表查询 | `POST /cgi/crm/custom/v2/data/query` | 见 `custom-objects.md` |
| 只做基本数据查询 | `POST /cgi/crm/custom/v2/data/findSimple` | 文档归在「通用接口 / 其他」，路径在 custom 下 |
| 只返回一条 | `POST /cgi/crm/custom/v2/data/findOne` | 同上 |
| 按 id 取单条详情 | `POST /cgi/crm/v2/data/get` / `…/custom/v2/data/get` | 见各对象文件 |

所有查询都是 **POST + JSON**，条件放在 body 的 `data.search_query_info` 里，不走 query string。

## 2. search_query_info 结构

**Endpoint**: `POST /cgi/crm/v2/data/query?thirdTraceId={uuid4}`
**用途**: 按字段条件分页查询对象数据。条件**只能按对象的字段过滤**。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| includeNull | Boolean | 否 | false | 是否返回值为 null 的字段（顶层） |
| data.dataObjectApiName | String | 是 | — | 对象 apiName |
| data.search_query_info.limit | Int | 是 | — | 每页条数，**最大 100** |
| data.search_query_info.offset | Int | 是 | — | 偏移量，从 0 开始，**必须是 limit 的整数倍**；是偏移量不是页码 |
| data.search_query_info.filters | List | 是 | — | 过滤条件列表（多个条件是「且」关系，旧版 wiki 1090） |
| filters[].field_name | String | 是 | — | 字段 apiName（从 describe 拿） |
| filters[].field_values | List | 是 | — | **必须是列表**，等于 `"1"` 也要写 `["1"]` |
| filters[].operator | String | 是 | — | 见第 3 节 |
| data.search_query_info.orders | List | 是 | — | 排序；可以是空列表 |
| orders[].fieldName | String | 是 | — | 注意是驼峰 `fieldName`，和 filters 的 `field_name` 不同 |
| orders[].isAsc | Boolean | 是 | — | true 升序 / false 降序 |
| data.search_query_info.fieldProjection | List[String] | 见 ⚠ | — | 只返回这些字段，如 `["_id","name"]` |

**示例请求**

```json
{
  "data": {
    "dataObjectApiName": "AccountObj",
    "search_query_info": {
      "limit": 100,
      "offset": 0,
      "filters": [
        {"field_name": "account_type", "field_values": ["1"], "operator": "EQ"},
        {"field_name": "owner", "field_values": ["1000", "1001"], "operator": "IN"}
      ],
      "orders": [{"fieldName": "create_time", "isAsc": false}],
      "fieldProjection": ["_id", "name", "owner", "last_modified_time"]
    }
  }
}
```

```bash
curl -sS -X POST "https://$FXK_HOST/cgi/crm/v2/data/query?thirdTraceId=$(uuidgen | tr A-Z a-z)" \
  -H "authorization: Bearer $FXK_TOKEN" -H "x-fs-ea: $FXK_EA" -H "x-fs-userid: $FXK_USER_ID" \
  -H 'Content-Type: application/json' \
  -d '{"data":{"dataObjectApiName":"LeadsObj","search_query_info":{"limit":50,"offset":0,"filters":[{"field_name":"create_time","field_values":["1757000000000"],"operator":"GT"}],"orders":[{"fieldName":"create_time","isAsc":true}],"fieldProjection":["_id","name"]}}}'
```

**注意事项**
- 大小写和下划线：`search_query_info`、`field_name`、`field_values` 是下划线；`fieldName`、`isAsc`、`fieldProjection`、`dataObjectApiName` 是驼峰。混写是最常见的低级错误。
- 时间字段（`create_time`、`last_modified_time`）比较值用**毫秒时间戳**，放进字符串列表。
- 人员类型字段做范围查询**必须用 `IN`，值必须传 openUserId**（旧版 wiki 1146，基于旧版传参）；新版传参下填员工 ID 还是 FSUID，⚠ 文档未说明，参考 `objects-and-fields.md` 第 4 节的 convertUserId。

## 3. operator 全表

| operator | 含义 | operator | 含义 |
| --- | --- | --- | --- |
| EQ | 等于 | N | 不等于（**可以查出空值**） |
| GT | 大于 | GTE | 大于等于 |
| LT | 小于 | LTE | 小于等于 |
| LIKE | 包含 | NLIKE | 不包含 |
| IS | 为空 | ISN | 不为空 |
| IN | 属于 | NIN | 不属于 |
| BETWEEN | 介于 | NBETWEEN | 不介于 |
| STARTWITH | 开始于（`LIKE%`） | ENDWITH | 结束于（`%LIKE`） |
| HASANYOF | 有重叠元素 | NHASANYOF | 没有重叠 |
| CONTAINS | 数组包含 | | |

- 「不等于」是 `N`，不是 `NE` / `NEQ`。
- ⚠ 文档自相矛盾：预置对象查询页列 `HASANYOF` / `NHASANYOF`，不列 `CONTAINS`；自定义对象查询页和旧版 wiki 列 `CONTAINS`（Array 包含），不列 HASANYOF。
- ⚠ 文档未说明：`IS` / `ISN` 时 `field_values` 填什么（示例没有）；`BETWEEN` 的两个端点怎么放（推测为两元素列表，未证实）。

## 4. 分页规则

- `limit` 最大 **100**。
- `offset` 从 0 开始，**必须是 limit 的整数倍**（limit=100 时 offset 只能是 0、100、200……）。
- `offset` **不能超过 10000**。超过时返回（「深翻页文档」页原文，未实测）：

```json
{"errorDescription": "offset 不能超过10000", "errorMessage": "offset out of range 10000", "errorCode": 10013}
```

- ⚠ 文档自相矛盾：这里的 `10013` 在「全局返回码」表里是「缺少参数corpAccessToken」。别用错误码判断这个情况，数据量可能过万时直接用第 5 节的方案。
- ⚠ 文档自相矛盾：旧版 wiki 1146 注意事项写「一次查询的数据列表最多返回200条」，与 limit 最大 100 冲突，按 100 写。

## 5. 深翻页：用 `_id` 游标代替 offset

数据量可能超过 1 万条（全量同步、导出）时，文档给的方案：

1. `orders` 只按 `_id` 升序：`[{"fieldName": "_id", "isAsc": true}]`
2. `offset` 始终为 0
3. 从第二页起加过滤 `{"operator": "GT", "field_name": "_id", "field_values": ["<上一页最后一条的 _id>"]}`
4. 返回条数 < limit 时结束

```json
"search_query_info": {
  "limit": 100, "offset": 0,
  "filters": [{"operator": "GT", "field_name": "_id", "field_values": ["0329115a0d70455f9852bbcbbaf452e0"]}],
  "orders": [{"fieldName": "_id", "isAsc": true}]
}
```

业务过滤条件（如 `last_modified_time GT …`）可以和 `_id GT` 放在同一个 filters 列表里一起用（且关系）。

## 6. 要不要总数：三种参数名

⚠ 文档自相矛盾——同一个「是否返回总数」在不同页面有三种写法：

| 参数 | 位置 | 类型 | 出现的页面 | 语义 |
| --- | --- | --- | --- | --- |
| `returnTotalNum` | 顶层 | Int | 线索、联系人、商机2.0、人员、部门、公海的查询页 | 1 精确总数 / 2 预估总数 / 3 或不传：不返回（更快） |
| `find_explicit_total_num` | `data` 内 | Boolean | 客户查询页（query-acc）、findSimple、深翻页示例；自定义对象页标为 String | true 返回 total（**默认 true**）/ false 不返回，更快 |
| `need_return_count_num` | 顶层 | Boolean | 「参数填写说明」页、旧版 wiki | true 返回精确总数（**默认 false**） |

建议：不需要总数时两个都显式关掉（`"returnTotalNum": 3` + `"find_explicit_total_num": false`），翻页用第 5 节的「返回条数 < limit 即结束」判断，不依赖 total。
需要总数时，先在真实环境对照看哪个参数生效（见 verification-plan）。

## 7. 响应结构

⚠ 文档自相矛盾：各对象查询页的「返回示例」把 `data` 画成**单条记录**：

```json
{"traceId": "E-O.827xxxxxx", "errorDescription": "success",
 "data": {"created_by__r": {}, "lock_status": "0", "is_deleted": false, "create_time": 1612247399397, "name": "xxxxxx", "_id": "69046aexxxxxxx"},
 "errorMessage": "OK", "errorCode": 0}
```

而「深翻页文档」和旧版 wiki 的真实出参示例是**列表 + 分页信息**：

```json
{
  "traceId": "E-O.74164.1063-61c99d4033ca46c5",
  "data": {
    "dataList": [{"_id": "0039b47555cf4be98b8ff85d1ca70144"}, {"_id": "0329115a0d70455f9852bbcbbaf452e0"}],
    "offset": 0, "limit": 5, "total": 0
  },
  "errorDescription": "success", "errorMessage": "OK", "errorCode": 0
}
```

列表查询按 `data.dataList` 解析（后者是带真实 traceId 的出参，更可信），并对单条 map 的形态做兜底。
`total` 在关闭总数时为 0（上例 `find_explicit_total_num: false`），不能拿它判断是否还有下一页。

其他：
- 值为空的字段不返回（除非 `includeNull: true`）。
- 不要用 `errorMessage` 做逻辑判断，它会变；判 `errorCode == 0`。

## 8. findSimple / findOne

**Endpoint**: `POST /cgi/crm/custom/v2/data/findSimple?thirdTraceId={uuid4}`
**用途**: 「只做基本的数据查询」。文档说对计算字段、统计字段、引用字段**不实时计算**。适合只要原始字段的增量同步。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data.dataObjectApiName | String | 是 | 对象 apiName |
| data.find_explicit_total_num | Boolean | 否 | 默认 true |
| data.search_query_info | Map | 是 | 结构同第 2 节 |
| data.field_projection | List[String] | 见 ⚠ | 返回字段，空则返回所有字段 |

文档示例（按增量同步写法）：

```json
{
  "data": {
    "dataObjectApiName": "AccountObj",
    "search_query_info": {
      "offset": 0, "limit": 10,
      "orders": [{"fieldName": "last_modified_time", "isAsc": false}],
      "filters": [{"operator": "GT", "field_name": "last_modified_time", "field_values": ["1744094120158"]}]
    },
    "field_projection": ["_id"]
  }
}
```

- ⚠ 文档自相矛盾：参数表写 `field-projection`（连字符），示例写 `field_projection`（下划线），而 data/query 用 `fieldProjection`（驼峰，放在 search_query_info 里）。
- ⚠ 文档示例错误：原示例把 `offset`/`limit` 写成字符串、`isAsc` 写成 `"false"`、`filters` 写成对象而不是列表、`field_values` 写成字符串 `"[1744094120158]"`，还有拼写 `igonreMediaIdConvert`。上面的示例已按参数表类型改正，未实测。

**Endpoint**: `POST /cgi/crm/custom/v2/data/findOne?thirdTraceId={uuid4}` —— 按条件只返回一条。参数：`data.dataObjectApiName`、`data.search_query_info`、`data.field_projection`（同上）。返回结构 ⚠ 文档未说明。

## 9. 完整示例：全量拉取客户

```python
def iter_all(fxk, api_name: str, fields: list[str], extra_filters=None, page=100):
    """深翻页全量遍历，适用于预置对象；自定义对象把 path 换成 /cgi/crm/custom/v2/data/query。"""
    last_id = None
    while True:
        filters = list(extra_filters or [])
        if last_id:
            filters.append({"field_name": "_id", "operator": "GT", "field_values": [last_id]})
        body = {
            "returnTotalNum": 3,                     # 不要总数，响应更快
            "data": {
                "dataObjectApiName": api_name,
                "find_explicit_total_num": False,
                "search_query_info": {
                    "limit": page, "offset": 0,       # offset 永远 0，靠 _id 游标
                    "filters": filters,
                    "orders": [{"fieldName": "_id", "isAsc": True}],
                    "fieldProjection": fields if "_id" in fields else ["_id", *fields],
                },
            },
        }
        data = fxk.post("/cgi/crm/v2/data/query", body)["data"]
        rows = data.get("dataList") if isinstance(data, dict) and "dataList" in data else [data]
        for row in rows:
            yield row
        if len(rows) < page:
            return
        last_id = rows[-1]["_id"]

# for acc in iter_all(fxk, "AccountObj", ["name", "owner", "last_modified_time"]):
#     ...
```

配合 `errors-and-limits.md` 的限流：单接口 100 次 / 20 秒，全量循环里每次请求间隔 ≥0.2 秒。

## 10. 从页面上抄查询条件

文档的查询条件描述不全时（「查看如何获取列表中的查询条件」页）：在纷享网页版打开对象列表 → F12 → 设置筛选条件并搜索 →
在 Network 里找 List 请求 → 看「载荷 / Payload」→ 复制其中的 `search_query_info`。这是拿到复杂条件（多选、关联字段、日期区间）真实写法的最快办法。

## 11. 本文件的 ⚠

- ⚠ 文档自相矛盾：总数参数三种写法（第 6 节）。
- ⚠ 文档自相矛盾：查询响应是单条 map 还是 `data.dataList`（第 7 节）。
- ⚠ 文档自相矛盾：offset 超限错误码 10013 与码表冲突；「最多返回 200 条」与 limit ≤100 冲突（第 4 节）。
- ⚠ 文档自相矛盾：operator 列表在预置 / 自定义 / 旧版三处不一致（第 3 节）。
- ⚠ 文档自相矛盾：`fieldProjection` 在预置查询页必填，在「参数填写说明」页非必填；findSimple 里又叫 `field-projection` / `field_projection`（第 2、8 节）。
- ⚠ 文档未说明：IS/ISN、BETWEEN 的 field_values 写法；findOne 返回结构；新版传参下人员字段 IN 查询填哪种 ID（第 2、3、8 节）。
- 文档示例错误（非探测证实）：findSimple 示例类型全错（第 8 节）。
- 页面错误：客户对象的「根据条件查询」页（`AccountObj/query.html`）正文其实是**公海对象 HighSeasObj** 的查询；客户查询看 `AccountObj/query-acc.html`。
