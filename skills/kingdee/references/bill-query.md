# 单据 / 基础资料查询（ExecuteBillQuery、View、QueryBusinessInfo）

> 来源：open.kingdee.com「API文档」各业务对象的操作说明（API 版本 7.5.1800.6 / PT-146854，发布 2020-10-15，抓取于 2026-09-11）
> + 官方 Python SDK `kingdee.cdp.webapi.sdk` 8.2.0 源码。**全部是文档原文 / SDK 源码转录，未用真实凭证调用验证。**
> 鉴权头怎么生成见 [`auth-and-connection.md`](auth-and-connection.md)；返回结构与报错见 [`errors-and-responses.md`](errors-and-responses.md)。

## 目录

1. 先选对接口
2. 请求体的外层包装（最容易漏）
3. ExecuteBillQuery：按条件查任意表单的任意字段
4. 分页拉全量
5. View：按编码 / 内码查一张单据的完整数据包
6. QueryBusinessInfo：查表单元数据（字段 key 从哪来）
7. QueryGroupInfo：查基础资料分组
8. BillQuery（仅 SDK 出现，文档未收录）
9. 常见 FormId 速查

---

## 1. 先选对接口

| 我要… | 用 | ServiceName（拼成 `{ServerUrl}/{ServiceName}.common.kdsvc`） |
| --- | --- | --- |
| 按条件批量查若干字段（列表、同步、对账） | ExecuteBillQuery | `Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery` |
| 已知一张单据的编码 / 内码，要它的完整数据包（含全部分录） | View | `Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.View` |
| 不知道某个字段的 key、想看表单结构 | QueryBusinessInfo | `Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.QueryBusinessInfo` |
| 查物料 / 客户 / 供应商的分组树 | QueryGroupInfo | `Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.QueryGroupInfo` |
| 查询结果想要带字段名的 JSON（而不是二维数组） | BillQuery ⚠ | `Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.BillQuery`（SDK 注释「2023-9-14新加」，2020 版文档没有） |

经验法则：**同步 / 列表 / 增量拉取一律 ExecuteBillQuery**；View 一次只看一张单据，返回的是整包数据，用它做批量拉取既慢又重。

## 2. 请求体的外层包装（最容易漏）

文档里「JSON格式数据」展示的只是 `data` 这一层。SDK 真正 POST 出去的 body 还要再包一层，
而且**不同接口包的键不一样**（来自 SDK 8.2.0 `main.py`）：

| 接口 | SDK 实际发送的 body |
| --- | --- |
| ExecuteBillQuery / BillQuery / QueryBusinessInfo / WorkflowAudit | `{"data": {...}}` —— **没有 formid**，FormId 写在 data 里面 |
| View / Save / Submit / Audit / Delete / Push … | `{"formid": "BD_MATERIAL", "data": {...}}` |
| ExcuteOperation（禁用、作废等） | `{"formid": "...", "opNumber": "Forbid", "data": {...}}` |

- 键名是小写 `formid`、`data`、`opNumber`（SDK 源码原样）。
- SDK 把 `data` 作为 JSON 对象发送；文档里的 .NET 示例是把 data 序列化成**字符串**再传。服务端是否两种都接受 ⚠ 文档未说明——拿不准就照 SDK 发对象。

## 3. ExecuteBillQuery

**Endpoint**：`POST {ServerUrl}/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc`
**用途**：对一个业务对象（单据或基础资料）按过滤条件查指定字段，返回二维数组。所有表单共用这一个接口，靠 `FormId` 区分。

**关键参数（`data` 内，文档原文）**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `FormId` | 字符串 | 是 | — | 业务对象表单 Id，如 `BD_MATERIAL`、`SAL_SaleOrder` |
| `FieldKeys` | 字符串 | 是 | — | **逗号分隔的字符串** `"key1,key2,..."`，不是数组。查单据体内码要写 `单据体Key_FEntryId`，如 `FPOOrderEntry_FEntryId` |
| `FilterString` | 字符串 | 否 | ⚠ 文档未说明 | 过滤条件。语法 ⚠ 文档未说明 |
| `OrderString` | 字符串 | 否 | ⚠ 文档未说明 | 排序字段。语法 ⚠ 文档未说明 |
| `TopRowCount` | 整型 | 否 | ⚠ 文档未说明 | 文档称「返回总行数」，与 Limit 的关系 ⚠ 文档未说明 |
| `StartRow` | 整型 | 否 | ⚠ 文档未说明 | 开始行索引（0 起还是 1 起 ⚠ 文档未说明） |
| `Limit` | 整型 | 否 | ⚠ 文档未说明 | 最大行数，**不能超过 2000** |

**示例请求（Python，官方 SDK，推荐）**

```python
import json, os
from k3cloud_webapi_sdk.main import K3CloudApiSdk

sdk = K3CloudApiSdk(os.environ["KD_SERVER_URL"])          # 8.2.0 起 ServerUrl 必填，形如 http://erp.example.com/k3cloud/
sdk.InitConfig(os.environ["KD_ACCT_ID"], os.environ["KD_USERNAME"],
               os.environ["KD_APP_ID"], os.environ["KD_APP_SECRET"],
               os.environ["KD_SERVER_URL"], lcid=2052)

raw = sdk.ExecuteBillQuery({
    "FormId": "BD_MATERIAL",
    "FieldKeys": "FMATERIALID,FNumber,FName,FSpecification",   # 逗号分隔字符串
    "FilterString": "",                                        # 语法见下文 ⚠
    "OrderString": "",
    "TopRowCount": 0,
    "StartRow": 0,
    "Limit": 2000,
})
rows = json.loads(raw)            # SDK 返回的是 JSON 字符串，要自己 json.loads
for r in rows:
    mat_id, number, name, spec = r    # 按 FieldKeys 的顺序取列
```

**示例请求（curl）**——鉴权头由 `auth-and-connection.md` 里的 `kd_sign.py` 生成：

```bash
SVC=Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery
HDRS=(); while IFS= read -r h; do HDRS+=(-H "$h"); done < <(python3 kd_sign.py "$SVC")
curl -sS -X POST "${KD_SERVER_URL%/}/$SVC.common.kdsvc" "${HDRS[@]}" \
  -d '{"data":{"FormId":"BD_MATERIAL","FieldKeys":"FMATERIALID,FNumber,FName","StartRow":0,"Limit":2000}}'
```

**示例响应（文档原文，未实测）**

```json
[["FValue1","FValue2"],["FValue1","FValue2"]]
```

**注意事项**

- **返回是纯二维数组，没有字段名、没有总数、没有 `Result` 外壳。** 列顺序 = `FieldKeys` 顺序。
  SDK 注释也写明返回「`List<List<object>>` 的 json 串」。写代码时用 `zip(field_list, row)` 自己组字典。
- 查询失败时返回什么结构 ⚠ 文档未说明（文档「返回结果」只画了成功的二维数组）。
  防御写法：`json.loads` 后先判断 `rows and isinstance(rows[0], list) and rows[0] and isinstance(rows[0][0], dict)`，
  是 dict 就当作错误包打印出来，不要把它当数据行。
- 字段 key 是表单元数据里的**字段标识**（`FNumber`、`FName`、`FDate`、`FBillNo`…），不是中文名、不是数据库列名。
  单据体字段直接写它的 key（如 `FMaterialId`、`FQty`）；单据体内码写 `单据体Key_FEntryId`。
  各表单的单据体 key 见本文第 9 节和 [`bill-operations.md`](bill-operations.md)。
- 基础资料字段（如 `FMaterialId`、`FCustId`）直接查询时返回的是什么（内码还是编码）⚠ 文档未说明。
  社区常见写法 `FMaterialId.FNumber` 取编码，**抓到的官方文档里没有这种点号语法**，⚠ 需实测。
- `FilterString` 的语法文档只说「过滤条件，字符串类型」。按字段 key 写 SQL WHERE 片段（如 `FNumber='WL0001'`）
  是常见用法，但 ⚠ 文档未说明语法、转义规则、日期格式，上线前用真实账套测一次。
- 多组织账套下查询会不会按当前用户组织过滤、`X-KDApi-OrgNum` 是否影响结果 ⚠ 文档未说明。

## 4. 分页拉全量

文档只给了 `StartRow`、`Limit`（≤2000）、`TopRowCount`，**没有 page / pageSize、没有 total、没有 next 游标**。
能从文档推出的最保守写法：固定 `Limit`，每页 `StartRow += Limit`，**返回行数 < Limit 就停**。

```python
def query_all(sdk, form_id, fields, filter_str="", order="", page=2000):
    keys = [k.strip() for k in fields.split(",")]
    start = 0
    while True:
        rows = json.loads(sdk.ExecuteBillQuery({
            "FormId": form_id, "FieldKeys": ",".join(keys),
            "FilterString": filter_str, "OrderString": order,
            "StartRow": start, "Limit": page,
        }))
        if rows and isinstance(rows[0], list) and rows[0] and isinstance(rows[0][0], dict):
            raise RuntimeError(f"ExecuteBillQuery 返回错误包: {rows[0][0]}")   # 结构 ⚠ 文档未说明
        for r in rows:
            yield dict(zip(keys, r))
        if len(rows) < page:
            break
        start += page
```

- `Limit` 超过 2000 会怎样（报错 / 截断）⚠ 文档未说明——**不要传 5000 指望一次拉完**。
- 翻页时一定带稳定的 `OrderString`（如按内码），否则两页之间可能重复 / 漏行（⚠ 排序语法文档未说明，推断）。
- 查单据体时每条分录是一行，表头字段会在每行重复出现；分页是按「行」分，不是按「单据」分。
- 增量同步：用修改日期字段（多数表单是 `FModifyDate`，见各表单字段说明）写进 `FilterString`。

## 5. View：查一张单据的完整数据包

**Endpoint**：`POST {ServerUrl}/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.View.common.kdsvc`
**用途**：按编码或内码取单张单据 / 基础资料的完整数据（含所有单据体），适合「保存前先读回来改几个字段」。

**关键参数（文档原文）**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `formid`（外层） | 字符串 | 是 | 业务对象表单 Id |
| `data.CreateOrgId` | 字符串 | 否 | 创建者组织内码（JSON 示例里是整数 `0`，⚠ 文档自相矛盾） |
| `data.Number` | 字符串 | 编码 / 内码二选一 | 单据编码 |
| `data.Id` | 字符串 | 编码 / 内码二选一 | 表单内码 |

```python
raw = sdk.View("BD_MATERIAL", {"Number": "WL0001"})
res = json.loads(raw)
if str(res["Result"]["ResponseStatus"]["IsSuccess"]).lower() != "true":
    raise RuntimeError(res["Result"]["ResponseStatus"])
```

**示例响应（文档原文，未实测）**：`{"Result":{"ResponseStatus":{"IsSuccess":"false"},"Result":"{}"}}`

**注意事项**
- 注意 View 的单数键 `Number` / `Id`，和 Submit / Audit / Delete 的复数键 `Numbers`（数组）/ `Ids`（逗号串）不同。
- 数据包在 `Result.Result` 里（两层 Result）。文档模板里它是字符串 `"{}"`，实际是对象还是需要二次 `json.loads` ⚠ 文档未说明，两种都兼容。
- 文档模板里 `IsSuccess` 是字符串 `"false"`，判断时统一 `str(...).lower() == "true"`。

## 6. QueryBusinessInfo：查表单元数据

**Endpoint**：`POST {ServerUrl}/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.QueryBusinessInfo.common.kdsvc`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `data.FormId` | 字符串 | 是 | 业务对象表单 Id |

```python
meta = json.loads(sdk.QueryBusinessInfo({"FormId": "SAL_SaleOrder"}))
```

- 文档返回模板：`{"Result":{"ResponseStatus":"","NeedReturnData":"{}"}`（模板本身括号不配对，⚠ 文档自相矛盾）；元数据的具体结构 ⚠ 文档未说明。
- 用途：拿到字段标识（key）、单据体 key，再去写 `FieldKeys` / Save 的 Model。客户做过二开的字段（通常以 `F_` 开头）只能这样查到。
- 文档 .NET 示例写成 `client.QueryBusinessInfo("GL_VOUCHER","{...}")` 带了 formid 参数，而 SDK 只传 `data`——以 SDK 为准。

## 7. QueryGroupInfo：查基础资料分组

**Endpoint**：`POST {ServerUrl}/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.QueryGroupInfo.common.kdsvc`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `formid`（外层，文档写了） | 字符串 | 是 | 业务对象表单 Id；⚠ SDK 的 `QueryGroupInfo(data)` 只发 `{"data":...}`，文档与 SDK 不一致 |
| `data.FormId` | 字符串 | 是 | 业务对象表单 Id |
| `data.GroupFieldKey` | 字符串 | 是 | 分组字段 Key（「不填时取默认，无默认，取第一个分组」——文档原文同时写了「必录」和「不填时…」，⚠ 文档自相矛盾） |
| `data.GroupPkIds` | 字符串 | 条件 | 分组内码 `"Id1,Id2"`；与 Ids 同时传时分组内码优先 |
| `data.Ids` | 字符串 | 条件 | 单据内码 `"Id1,Id2"` |

返回模板同 QueryBusinessInfo。分组的新建见 [`master-data.md`](master-data.md) 的 GroupSave。

## 8. BillQuery（仅 SDK 出现）

SDK 8.2.0：`BillQuery(data)` → `Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.BillQuery`，docstring「单据查询（json） 2023-9-14新加」，返回 string。
2020 版官方文档没有这个接口，参数与返回结构 ⚠ 文档未说明；老版本星空服务器上可能不存在。**默认用 ExecuteBillQuery。**

## 9. 常见 FormId 速查（来自官方 API 文档树，版本 7.5.1800.6）

| 业务对象 | FormId | 常用单据体 key（来自字段说明） |
| --- | --- | --- |
| 物料 | `BD_MATERIAL` | — |
| 客户 | `BD_Customer` | — |
| 供应商 | `BD_Supplier` | — |
| 科目 | `BD_Account` | — |
| 凭证 | `GL_VOUCHER` | `FEntity` |
| 采购订单 | `PUR_PurchaseOrder` | `FPOOrderEntry` |
| 采购入库单 | `STK_InStock` | `FInStockEntry` |
| 销售订单 | `SAL_SaleOrder` | `FSaleOrderEntry` |
| 销售出库单 | `SAL_OUTSTOCK` | `FEntity` |
| 即时库存 | `STK_Inventory` | — |
| 应收单 | `AR_receivable` | `FEntityDetail` |
| 应付单 | `AP_Payable` | `FEntityDetail` |
| 收款单 | `AR_RECEIVEBILL` | `FRECEIVEBILLENTRY` |
| 付款单 | `AP_PAYBILL` | ⚠ 未抓取该表单字段说明 |

- **FormId 大小写不统一**（`BD_MATERIAL` 全大写、`BD_Customer` 驼峰、`AR_receivable` 小写），照抄，不要「规范化」。
  SDK 示例里同一个物料既写过 `BD_Material`（Save 示例）也写过 `BD_MATERIAL`（查询示例），服务端是否大小写不敏感 ⚠ 文档未说明。
- 全部 942 个业务对象的 FormId 清单在 skill 工作区 `kingdee-workspace/openapi-summary/formid-catalog.md`（不随 skill 分发）；
  客户账套里真实可用的表单以 `QueryBusinessInfo` 或星空 BOS 设计器为准。
