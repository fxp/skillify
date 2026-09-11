# 自定义对象（apiName 以 `__c` 结尾）

> 来源：https://developer.fxiaoke.com/openapi_v2/object/CustomCapabilities/CustomObj/ 下 add / get / query / update / invalid /
> batchInvalid / delete / recover / changeOwner 各页（抓取于 2026-09-11），旧版 wiki「全局返回码」（artiId=27）。
> **本文件全部为文档原文，未实测。** 请求头、thirdTraceId、`FxkClient` 见 `auth.md`；查询条件见 `query-and-paging.md`。

## 目录
1. 什么时候走这组接口
2. 路径对照：预置 vs 自定义
3. 创建
4. 取详情
5. 列表查询
6. 修改
7. 作废（单条）与批量作废
8. 删除与恢复
9. 变更负责人
10. v1 → v2 的参数名变化
11. 本文件的 ⚠

---

## 1. 什么时候走这组接口

每个自定义对象页开头都写着：**本接口只适用于自定义对象（即对象的 ApiName 以 `__c` 结尾的对象）**。

- apiName 形如 `object_Nyeoj__c`、`object_d4fIq__c`——是后台建对象时系统生成的，**不是**中文名的拼音，也不是你起的显示名。
  用 `POST /cgi/crm/v2/object/list` 查准确值（见 `objects-and-fields.md`）。
- 字段描述接口是**共用的**：自定义对象的字段也用 `POST /cgi/crm/v2/object/describe`（`data.apiName` 填 `xxx__c`）。
- 判断规则写进代码里：`path_prefix = "/cgi/crm/custom/v2/data" if api_name.endswith("__c") else "/cgi/crm/v2/data"`。

## 2. 路径对照：预置 vs 自定义

| 动作 | 预置对象 | 自定义对象（`__c`） | body 差异 |
| --- | --- | --- | --- |
| 创建 | `/cgi/crm/v2/data/create` | `/cgi/crm/custom/v2/data/create` | 自定义多 `fillOutOwner` / `needConvertLookup` / `checkDuplicateSearch` |
| 详情 | `/cgi/crm/v2/data/get` | `/cgi/crm/custom/v2/data/get` | 相同 |
| 查询 | `/cgi/crm/v2/data/query` | `/cgi/crm/custom/v2/data/query` | 相同结构 |
| 修改 | `/cgi/crm/v2/data/update` | `/cgi/crm/custom/v2/data/update` | 自定义多 `skipDataStatusValidate` |
| 作废 | `/cgi/crm/v2/data/invalid` | `/cgi/crm/custom/v2/data/invalid` | 都是单条 `object_data_id` |
| 批量作废 | — | `/cgi/crm/custom/data/invalid`（**注意没有 v2**） | `idList` |
| 删除 | `/cgi/crm/v2/data/delete` | `/cgi/crm/custom/v2/data/delete` | `idList`，先作废 |
| 恢复 | `/cgi/crm/v2/data/recover` | `/cgi/crm/custom/v2/data/recover` | `idList` |
| 改负责人 | `/cgi/crm/v2/data/changeOwner` | `/cgi/crm/custom/v2/data/changeOwner` | `Data[]` |

无凭证探测（2026-09-11）：`POST /cgi/crm/custom/v2/data/query` 路径存在，伪造凭证返回
`{"errorMessage":"the cropId,cropAccessToken or authorization is error","errorCode":20016}`。
把 `__c` 对象发到预置对象路径（或反过来）会报什么错 ⚠ 未能验证（需要真实凭证）。

## 3. 创建

**Endpoint**: `POST /cgi/crm/custom/v2/data/create?thirdTraceId={uuid4}`

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| triggerWorkFlow | Boolean | 否 | true | 是否触发工作流 |
| triggerApprovalFlow | Boolean | 否 | true | 是否触发审批流 |
| hasSpecifyTime | Boolean | 否 | false | true 时才使用 `create_time` |
| includeDetailIds | Boolean | 否 | — | 主从一起创建时是否返回从对象 id 列表 |
| checkDuplicateSearch | Boolean | 否 | false | 是否验证查重规则（true 验证，false / 不传不验证） |
| data.object_data | Map | 是 | — | 主对象数据，和对象描述中的字段一一对应；**`dataObjectApiName` 放在这里面** |
| data.details | Map | 否 | — | 从对象数据，key 为从对象 apiName |
| data.fillOutOwner | Boolean | 否 | — | 是否自动填写外部负责人 |
| data.needConvertLookup | Boolean | 否 | — | 是否允许覆盖查找关联字段；允许时查找关联字段需加后缀 `__r` |

**示例请求**

```bash
curl -sS -X POST "https://$FXK_HOST/cgi/crm/custom/v2/data/create?thirdTraceId=$(uuidgen | tr A-Z a-z)" \
  -H "authorization: Bearer $FXK_TOKEN" -H "x-fs-ea: $FXK_EA" -H "x-fs-userid: $FXK_USER_ID" \
  -H 'Content-Type: application/json' \
  -d '{
    "triggerApprovalFlow": false,
    "triggerWorkFlow": false,
    "data": {
      "object_data": {
        "dataObjectApiName": "object_Hk2p1__c",
        "name": "2026Q4 回款计划-示例",
        "amount__c": "12000.50",
        "plan_date__c": 1790784000000,
        "owner": ["1000"]
      }
    }
  }'
```

```python
import datetime as dt

def ms(d: dt.date) -> int:              # 日期字段：毫秒时间戳（时分秒会被忽略）
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone(dt.timedelta(hours=8))).timestamp() * 1000)

resp = fxk.post("/cgi/crm/custom/v2/data/create", {
    "triggerApprovalFlow": False,
    "data": {"object_data": {
        "dataObjectApiName": "object_Hk2p1__c",
        "name": "2026Q4 回款计划-示例",
        "amount__c": "12000.50",           # currency：字符串
        "plan_date__c": ms(dt.date(2026, 10, 1)),
        "owner": ["1000"],                 # employee：列表；新版传参填员工 ID
    }},
})
```

上例的字段名（`amount__c`、`plan_date__c`、`owner`）只是示意，真实字段 apiName 与 type 以 describe 为准。

**示例响应**（文档原文）

```json
{"traceId": "E-O.827xxxxxx", "errorDescription": "success", "errorMessage": "OK", "errorCode": 0}
```

**注意事项**
- ⚠ 文档未说明：返回示例里**没有** `dataId`（预置对象创建会返回 `dataId`）。新数据 id 在哪个字段需要实测；拿不到时可按业务唯一字段再查一次。
- ⚠ 文档自相矛盾：参数表把 `checkDuplicateSearch` 列为顶层参数，示例也放顶层；但 `fillOutOwner` / `needConvertLookup` 在示例里放在 `data` 下。按示例写。
- 默认会触发审批流和工作流，批量导入时显式关掉。

## 4. 取详情

**Endpoint**: `POST /cgi/crm/custom/v2/data/get?thirdTraceId={uuid4}`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| includeNull | Boolean | 否 | 默认 false |
| data.dataObjectApiName | String | 是 | `xxx__c` |
| data.objectDataId | String | 文档标「否」 | 数据 id（⚠ 取详情不可能不传 id，文档必填标错） |

```json
{"data": {"dataObjectApiName": "object_Hk2p1__c", "objectDataId": "5f323dd6d97520000155369f"}}
```

返回结构：⚠ 文档未说明（示例只有 errorCode 等公共字段）；预置对象的 get 把记录放在 `data` 里，可按此预期。

## 5. 列表查询

**Endpoint**: `POST /cgi/crm/custom/v2/data/query?thirdTraceId={uuid4}`

结构与预置对象查询完全相同（`data.dataObjectApiName` + `data.search_query_info`），limit ≤100、offset 为 limit 整数倍、offset ≤10000，
深翻页用 `_id` 游标——全部见 `query-and-paging.md`。

```json
{
  "data": {
    "dataObjectApiName": "object_Hk2p1__c",
    "find_explicit_total_num": false,
    "search_query_info": {
      "limit": 100, "offset": 0,
      "filters": [{"field_name": "plan_date__c", "operator": "GTE", "field_values": ["1790784000000"]}],
      "orders": [{"fieldName": "_id", "isAsc": true}]
    }
  }
}
```

- ⚠ 文档自相矛盾：参数表把 `find_explicit_total_num` 类型标为 String（示例值 `"hello"`）、把 `search_query_info` 标为 String，
  其他页面都是 Boolean / Map。按 Boolean / Map 写。
- ⚠ 文档页面错误：`dataObjectApiName` 说明写「固定取值：DeliveryNoteProductObj」（从发货单产品页复制过来的），实际填你的 `__c` apiName。
- 自定义对象页的 operator 表有 `CONTAINS`，没有 `HASANYOF`（见 `query-and-paging.md` 第 3 节）。

## 6. 修改

**Endpoint**: `POST /cgi/crm/custom/v2/data/update?thirdTraceId={uuid4}`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| triggerWorkFlow | Boolean | 否 | 默认 true |
| data.object_data | Map | 是 | 要改的字段 + `_id` + `dataObjectApiName` |
| data.object_data._id | String | 是 | 被修改数据 id |
| data.skipDataStatusValidate | Boolean | 否 | 是否修改**锁定**的数据 |

```json
{
  "triggerWorkFlow": false,
  "data": {
    "skipDataStatusValidate": false,
    "object_data": {"_id": "5f323dd6d97520000155369f", "dataObjectApiName": "object_Hk2p1__c", "amount__c": "13000.00"}
  }
}
```

- ⚠ 文档页面错误：参数表把 `data` 描述成「String，关联主对象apiName」、把 `object_data` 描述成「计划执行时间，未来某个时间的时间戳」——明显是从别的页面复制的说明，以示例结构为准。
- 预置对象页列了 `triggerApprovalFlow`，本页没列（⚠ 文档未说明自定义对象修改是否支持该开关）。
- 负责人仍然要用第 9 节的 changeOwner 改。

## 7. 作废（单条）与批量作废

### 7.1 作废单条

**Endpoint**: `POST /cgi/crm/custom/v2/data/invalid?thirdTraceId={uuid4}`

```json
{"data": {"object_data_id": "5a9ce894f125ae9befxxxxxx", "dataObjectApiName": "object_d4fIq__c"}}
```

文档「特殊说明」：v1 的关键字是 `idList`，**v2 的关键字是 `object_data_id`，并且 v2 不支持批量作废**。

### 7.2 批量作废

**Endpoint**: `POST /cgi/crm/custom/data/invalid?thirdTraceId={uuid4}` —— 注意路径里**没有 `v2`**。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data.dataObjectApiName | String | 是 | `xxx__c` |
| data.idList | List[String] | 是 | 数据 id 列表 |

```json
{"data": {"dataObjectApiName": "object_d4fIq__c", "idList": ["603dabc14ae65400011aec90"]}}
```

批量作废 / 删除走旧式路径时要注意第 10 节的「v1 且 currentOpenUserId 非管理员 → Bad Request」。

## 8. 删除与恢复

| 动作 | Endpoint | body |
| --- | --- | --- |
| 删除（先作废） | `POST /cgi/crm/custom/v2/data/delete` | `data.dataObjectApiName` + `data.idList`（「删除之前请先作废数据」） |
| 恢复已作废 | `POST /cgi/crm/custom/v2/data/recover` | `data.dataObjectApiName` + `data.idList` |

```python
def hard_delete(fxk, api_name: str, ids: list[str]):
    """自定义对象彻底删除：逐条作废（v2 不支持批量）→ 批量删除。"""
    for i in ids:
        fxk.post("/cgi/crm/custom/v2/data/invalid", {"data": {"dataObjectApiName": api_name, "object_data_id": i}})
    fxk.post("/cgi/crm/custom/v2/data/delete", {"data": {"dataObjectApiName": api_name, "idList": ids}})
```

（量大时第一步可改用 7.2 的批量作废。）

## 9. 变更负责人

**Endpoint**: `POST /cgi/crm/custom/v2/data/changeOwner?thirdTraceId={uuid4}`

按文档「特殊说明」的 V2 入参写：

```json
{
  "data": {
    "dataObjectApiName": "object_Nyeoj__c",
    "Data": [{"objectDataId": "5a9914fcf125ae0a1axxxxxx", "ownerId": ["1000"]}]
  }
}
```

- 注意关键字从 v1 的 `dataList` 变为了 v2 的 **`Data`**（大写 D）；`ownerId` 是列表。
- ⚠ 文档自相矛盾：本页参数表写的是 `data.idList`（List，必填），请求示例是 `"idList": ""`，和下方「特殊说明」的 V2 入参 `Data[]` 完全不同。以特殊说明为准（参数表像是从删除页复制的）。

## 10. v1 → v2 的参数名变化

文档保留了 v1 入参对比，看到老代码 / 网上旧示例时对照改：

| 动作 | v1（旧版传参，body 带 corpAccessToken/corpId/currentOpenUserId） | v2 |
| --- | --- | --- |
| 作废 | `data.idList`（可批量） | `data.object_data_id`（单条）；批量走 `/cgi/crm/custom/data/invalid` |
| 改负责人 | `data.dataList[]` | `data.Data[]` |
| 鉴权 | body 三件套 | 新版 header（也兼容旧版 body，探测 P6） |

旧版 wiki（artiId=27）：调用 **v1 版本自定义对象接口**时，如果 `currentOpenUserId` 不是 CRM 管理员会报 **`Bad Request`**，
需要换成 CRM 管理员的 openUserId（文档原文，未实测）。

## 11. 本文件的 ⚠

- ⚠ 文档未说明：创建成功后新数据 id 的字段名（第 3 节）；get 的返回结构（第 4 节）；修改是否支持 triggerApprovalFlow（第 6 节）。
- ⚠ 文档自相矛盾：`checkDuplicateSearch` 与 `fillOutOwner` / `needConvertLookup` 的层级（第 3 节）；get 的 `objectDataId` 标为非必填（第 4 节）。
- ⚠ 文档自相矛盾：query 页 `find_explicit_total_num` / `search_query_info` 类型标为 String，`dataObjectApiName` 固定取值写成 DeliveryNoteProductObj（第 5 节）。
- ⚠ 文档自相矛盾：update 页 `data` / `object_data` 的说明是复制错的（第 6 节）。
- ⚠ 文档自相矛盾：changeOwner 参数表 `idList` vs 特殊说明 `Data[]`（第 9 节）。
- ⚠ 未能验证：`__c` 对象误走预置路径的报错（第 2 节）。
