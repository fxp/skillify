# 采购订单与销售订单

> 来源：open.yonyoucloud.com API 文档「用友 YonBIP → 供应链云 → 采购供应 → 采购管理 → 采购订单」（`upu.st_purchaseorder`）与
> 「销售服务 → 销售管理 → 销售订单」（`udinghuo.voucher_order`），经公开 JSON 抓取于 2026-09-11。
> 字段、示例、报错全部是**文档原文，未实测**（标「无凭证探测」的除外）。调用方式见 `auth-and-gateway.md`。

## 目录

1. 单据接口的共同模式（先读）
2. 采购订单列表查询
3. 采购订单详情查询
4. 采购订单单个保存
5. 采购订单提交 / 审核 / 弃审
6. 采购订单删除
7. 销售订单列表查询
8. 销售订单详情查询
9. 销售订单单个保存
10. 销售订单提交 / 审核 / 弃审
11. 销售订单删除
12. 单据事件
13. 本文件的 ⚠ 汇总

---

## 1. 单据接口的共同模式（先读）

| 动作 | 采购订单 | 销售订单 | 请求体 |
| --- | --- | --- | --- |
| 列表 | `POST /yonbip/scm/purchaseorder/list` | `POST /yonbip/sd/voucherorder/list` | `pageIndex`、`pageSize` + `simpleVOs[]` 条件 + `queryOrders[]` 排序 |
| 详情 | `GET /yonbip/scm/purchaseorder/detail?id=` | `GET /yonbip/sd/voucherorder/detail?id=` | query |
| 保存 | `POST /yonbip/scm/purchaseorder/singleSave_v1` | `POST /yonbip/sd/voucherorder/singleSave` | `{"data":{…, "_status":"Insert", 子表:[{…,"_status":"Insert"}]}}` |
| 提交 | `POST …/purchaseorder/batchsubmit` | `POST …/voucherorder/batchsubmit` | `{"data":[{"id":…}]}` |
| 审核 | `POST …/purchaseorder/batchaudit` | `POST …/voucherorder/batchaudit` | `{"data":[{"id":…}]}` |
| 弃审 | `POST …/purchaseorder/batchunaudit` | `POST …/voucherorder/batchunaudit` | `{"data":[{"id":…}]}` |
| 删除 | `POST …/purchaseorder/delete` | `POST …/voucherorder/delete` | 采购 `{"data":[{"id","pubts"}]}`；销售 `{"data":{"id":[…],"code":[…]}}` |

要点：

1. **保存 ≠ 生效。** 保存后单据是开立态，要再调「提交」「审核」（受审批流控制时审核由流程驱动，`isWfControlled`）。
2. **保存必须带 `data` 外壳和 `_status`**：表头 `_status` 和**每一行**子表 `_status` 都必填，`Insert` 新增、`Update` 修改。
3. **保存是 MDD 幂等接口**（API 详情 `idempotent: "mdd"`）：在 `data` 里加 `resubmitCheckKey`（≤32 位，租户内同接口唯一）；
   有上游单据时文档建议用上游单据 ID 作键。提交 / 审核 / 弃审是 `non`，重试前先查状态。
4. **批量动作「code 200」不等于全部成功**：返回里有 `count`、`sucessCount`（官方拼写）、`failCount`、`messages[]`；
   文档的删除 / 提交错误示例都是 `"code":"200"` + `failCount: 1`。
5. **列表条件 `simpleVOs`**：`{"field": 字段名, "op": 比较符, "value1": 值, "value2": 区间上限, "logicOp": "and"/"or"}`；
   采购 op 列出 `eq/neq/lt/gt/between/in/nin…`，销售列出 `eq/neq/lt/gt/like/between`。字段名须是实体上存在的字段；子表字段写法 ⚠ 文档说明被截断。
6. **日期格式** `yyyy-MM-dd HH:mm:ss`（如 `vouchdate`），不是纯日期。
7. **限流**：2026-01-26 公告，自 2026-03-31 起销售订单列表 / 详情 / 单个保存「免费调用次数」**60 次/分钟**（见 `errors-and-limits.md`）。

---

## 2. 采购订单列表查询

**Endpoint**: `POST /yonbip/scm/purchaseorder/list`

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| pageIndex | long | **是** | 1 | |
| pageSize | long | **是** | 10 | |
| isSum | boolean | 否 | false | true 只查表头 |
| simpleVOs[] | object | 否 | | `field`、`op`、`value1` |
| queryOrders[] | object | 否 | | `field`、`order`(asc/desc) |

```python
r = api.call("POST", "/yonbip/scm/purchaseorder/list", body={
    "pageIndex": 1, "pageSize": 50, "isSum": False,
    "simpleVOs": [{"field": "vouchdate", "op": "between",
                   "value1": "2026-09-01 00:00:00", "value2": "2026-09-30 23:59:59"}],
    "queryOrders": [{"field": "id", "order": "asc"}]})
for row in r["data"]["recordList"]:
    ...
```

返回 `data.pageIndex / pageSize / recordCount / recordList[]`。`isSum=false` 时 `recordList` 每行是「表头 + 一行明细」的扁平记录
（如 `product_cCode`、`purchaseOrders_arrivedStatus`、`purchaseOrders_inWHStatus`），同一张单会出现多行。

状态枚举（文档原文）：`status` 0 开立 / 1 已审核 / 2 已关闭 / 3 审核中；`purchaseOrders_arrivedStatus` 1 到货完成 / 2 未到货 / 3 部分到货；
`purchaseOrders_inWHStatus` 1 入库完成 / 2 未入库 / 3 部分入库；`modifyStatus` 0 未变更 / 1 变更中 / 2 变更完成。

---

## 3. 采购订单详情查询

**Endpoint**: `GET /yonbip/scm/purchaseorder/detail?id=<采购订单ID>`

返回 `data`：表头（`id`、`code`、`org`、`vendor`、`vendor_code`、`bustype`、`currency`、`exchRate`、`vouchdate`、`pubts`…）和
子表 `purchaseOrders[]`。删除接口需要的 `pubts` 从这里取。

---

## 4. 采购订单单个保存

**Endpoint**: `POST /yonbip/scm/purchaseorder/singleSave_v1`（MDD 幂等）

**关键参数（表头，`data.` 下）**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| resubmitCheckKey | string | 否 | 幂等键 |
| _status | string | **是** | `Insert` / `Update` |
| id | string | 修改时必填 | |
| code | string | 条件 | 编码规则为手工编号时必填 |
| bustype_code | string | **是** | 交易类型编码，如 `A20001` |
| org_code | string | **是** | 采购组织编码 |
| vendor_code | string | **是** | 供应商编码 |
| invoiceVendor_code | string | **是** | 开票供应商编码 |
| vouchdate | string | **是** | `yyyy-MM-dd HH:mm:ss` |
| currency_code / natCurrency_code | string | **是** | 币种 / 本币，如 `CNY` |
| exchRate | number | **是** | 汇率 |
| exchRateType | string | **是** | 汇率类型 ID 或编码 |
| bAutoGetPriceForApi | boolean | 否 | 默认 false；自动询价 |
| operator / department | string | 否 | 采购员 / 部门，ID 或编码 |
| source / srcBill / srcBillNO | | 条件 | 推拉单（有来源单据）时必填 |
| purchaseOrders | object[] | **是** | 子表 |

**子表 `purchaseOrders[]` 必填项**：`_status`、`product_cCode`（物料编码）、`qty`、`subQty`（采购数量）、`priceQty`（计价数量）、
`unit_code` / `purUOM_Code` / `priceUOM_Code`（主 / 采购 / 计价单位编码）、`invExchRate` / `invPriceExchRate`（换算率）、
`unitExchangeType` / `unitExchangeTypePrice`（0 固定 / 1 浮动）、`oriUnitPrice` / `oriTaxUnitPrice` / `oriMoney` / `oriSum` / `oriTax`、
`natUnitPrice` / `natTaxUnitPrice` / `natMoney` / `natSum` / `natTax`、`taxitems_code`（税目编码）、`inOrg_code`（收货组织）、`inInvoiceOrg_code`（收票组织）。

```python
line = {"_status": "Insert", "product_cCode": "00000002", "qty": 10, "subQty": 10, "priceQty": 10,
        "unit_code": "001", "purUOM_Code": "001", "priceUOM_Code": "001",
        "invExchRate": 1, "invPriceExchRate": 1, "unitExchangeType": 0, "unitExchangeTypePrice": 0,
        "oriUnitPrice": 100, "oriTaxUnitPrice": 113, "oriMoney": 1000, "oriSum": 1130, "oriTax": 130,
        "natUnitPrice": 100, "natTaxUnitPrice": 113, "natMoney": 1000, "natSum": 1130, "natTax": 130,
        "taxitems_code": "VAT13", "inOrg_code": "991", "inInvoiceOrg_code": "991"}
body = {"data": {"resubmitCheckKey": f"po{ext_order_no}"[:32], "_status": "Insert",
                 "bustype_code": "A20001", "org_code": "991", "vendor_code": "0000000001",
                 "invoiceVendor_code": "0000000001", "vouchdate": "2026-09-11 00:00:00",
                 "currency_code": "CNY", "natCurrency_code": "CNY", "exchRate": 1, "exchRateType": "01",
                 "purchaseOrders": [line]}}
po = api.call("POST", "/yonbip/scm/purchaseorder/singleSave_v1", body=body)["data"]
po_id = po["id"]
```

（示例里的编码值如 `VAT13`、`01` 仅为占位，必须换成租户实际档案编码；⚠ 文档未给出税目 / 汇率类型的固定编码。）

**注意事项**

- 金额 / 单价的小数位取自币种档案的精度设置（文档原文），自己算好再传，含税 = 无税 + 税额要自洽。⚠ 文档未说明不自洽时是报错还是重算。
- `doFieldCheck` + `checkFieldKeys` 可让服务端按指定字段重算（默认 false）。
- 返回 `data.resubmitCheckKey` 示例形如 `OPENAPI_<apiId>_<…>`：网关会在调用方的键上拼 apiId 与 tenantId（幂等性页原文）。
- 错误示例：`{"code":"999","message":"服务端逻辑异常"}`；列表接口的错误示例 `code` 为数字 999。

---

## 5. 采购订单提交 / 审核 / 弃审

**Endpoint**: `POST /yonbip/scm/purchaseorder/batchsubmit`、`…/batchaudit`、`…/batchunaudit`

```python
def po_action(action: str, ids: list[int]) -> dict:
    r = api.call("POST", f"/yonbip/scm/purchaseorder/{action}", body={"data": [{"id": i} for i in ids]})
    d = r["data"]
    if d.get("failCount"):
        raise RuntimeError(f"{action} 部分失败: {d.get('messages')}")
    return d

po_action("batchsubmit", [po_id])
po_action("batchaudit", [po_id])
```

返回 `data.count / sucessCount / failCount / messages[] / infos[]`，`infos[]` 为单据最新状态（`verifystate`、`status`、`pubts`…）。

---

## 6. 采购订单删除

**Endpoint**: `POST /yonbip/scm/purchaseorder/delete`

```json
{"data": [{"id": 2172161512886528, "pubts": "2021-03-15 11:16:58"}]}
```

`id` 与 `pubts` **都必填**：`pubts` 是乐观锁时间戳，从详情取。错误示例（文档原文）：
`{"code":"200","message":"操作成功","data":{"failCount":1,"messages":["网络上有其他人操作或者已经关闭、审核,删除失败！"]}}`——
已审核单据要先弃审。

---

## 7. 销售订单列表查询

**Endpoint**: `POST /yonbip/sd/voucherorder/list`

在采购订单列表参数之外，还有顶层快捷条件：`code`、`nextStatusName`（如 `CONFIRMORDER` 已创建、`DELIVERY_PART` 部分发货…）、
`open_orderDate_begin/end`、`open_vouchdate_begin/end`、`open_hopeReceiveDate_begin/end`（均 `yyyy-MM-dd HH:mm:ss`）。
返回 `data.recordList[]`：`id`、`code`、`vouchdate`、`salesOrgId`、`agentId`（客户 ID）、`agentId_name`、`transactionTypeId`、
`orderPrices{currency, natCurrency, exchRate, …}` 等。

---

## 8. 销售订单详情查询

**Endpoint**: `GET /yonbip/sd/voucherorder/detail?id=<订单ID>`

- 文档请求示例是 `http://api.diwork.com/yonsuite/sd/voucherorder/detail?access_token=…&id=…`（http、旧域名、`/yonsuite` 前缀）。
  ⚠ 文档自相矛盾：接口地址是 `/yonbip/sd/voucherorder/detail`。无凭证探测（2026-09-11）：`/yonbip/sd/voucherorder/detail` 在 c2 网关已注册
  （假 token 返回 `310036`）。按 `{gatewayUrl}/yonbip/…` 调用。
- 错误示例：`{"code":"999","message":"未获取到当前订单商品信息"}`。

---

## 9. 销售订单单个保存

**Endpoint**: `POST /yonbip/sd/voucherorder/singleSave`（MDD 幂等）

**表头必填（`data.` 下）**：`_status`、`salesOrgId`（**传 ID 或编码**）、`transactionTypeId`（ID 或编码）、`vouchdate`、
`agentId`（客户，ID 或编码）、`settlementOrgId`（开票组织）、`invoiceAgentId`（开票客户）、`payMoney`（含税总额，**须等于子表含税金额合计**）、
`orderPrices!currency`、`orderPrices!natCurrency`、`orderPrices!exchRate`、`orderPrices!exchangeRateType`、`orderPrices!taxInclusive`、`orderDetails[]`。

**子表 `orderDetails[]` 必填**：`_status`、`productId`（ID 或编码）、`stockOrgId`、`settlementOrgId`、`masterUnitId`（主单位）、
`iProductAuxUnitId`（销售单位）、`iProductUnitId`（计价单位）、`qty`、`subQty`、`priceQty`、`invExchRate`、`invPriceExchRate`、
`unitExchangeType`、`unitExchangeTypePrice`、`taxId`（税目）、`orderProductType`（`SALE` / `GIFT` / `MARKUP` / `REBATE`…）、`oriTaxUnitPrice`、`oriSum`，
以及 `orderDetailPrices!oriUnitPrice`、`orderDetailPrices!oriMoney`、`orderDetailPrices!oriTax`、`orderDetailPrices!natUnitPrice`、
`orderDetailPrices!natTaxUnitPrice`、`orderDetailPrices!natMoney`、`orderDetailPrices!natSum`、`orderDetailPrices!natTax`。

**`!` 是字段名的一部分**：`"orderPrices!currency"` 是一个扁平的 JSON 键，**不是**嵌套对象 `{"orderPrices":{"currency":…}}`（文档示例就是扁平写法）。

```python
detail = {"_status": "Insert", "productId": "000001", "stockOrgId": "991", "settlementOrgId": "991",
          "masterUnitId": "001", "iProductAuxUnitId": "001", "iProductUnitId": "001",
          "qty": 10, "subQty": 10, "priceQty": 10, "invExchRate": 1, "invPriceExchRate": 1,
          "unitExchangeType": 0, "unitExchangeTypePrice": 0, "taxId": "VAT13", "orderProductType": "SALE",
          "oriTaxUnitPrice": 113, "oriSum": 1130,
          "orderDetailPrices!oriUnitPrice": 100, "orderDetailPrices!oriMoney": 1000, "orderDetailPrices!oriTax": 130,
          "orderDetailPrices!natUnitPrice": 100, "orderDetailPrices!natTaxUnitPrice": 113,
          "orderDetailPrices!natMoney": 1000, "orderDetailPrices!natSum": 1130, "orderDetailPrices!natTax": 130}
body = {"data": {"resubmitCheckKey": f"so{ext_no}"[:32], "_status": "Insert",
                 "salesOrgId": "991", "transactionTypeId": "SO01", "vouchdate": "2026-09-11 00:00:00",
                 "agentId": "C0001", "settlementOrgId": "991", "invoiceAgentId": "C0001", "payMoney": 1130,
                 "orderPrices!currency": "CNY", "orderPrices!natCurrency": "CNY", "orderPrices!exchRate": 1,
                 "orderPrices!exchangeRateType": "01", "orderPrices!taxInclusive": True,
                 "orderDetails": [detail]}}
so = api.call("POST", "/yonbip/sd/voucherorder/singleSave", body=body)["data"]
```

（编码值为占位。）

**注意事项**

- 与采购订单相反：销售订单的组织 / 客户 / 物料字段是「一个字段接受 ID 或编码」（`salesOrgId`、`agentId`、`productId`），
  采购订单用 `_code` 后缀字段（`org_code`、`vendor_code`、`product_cCode`）。不要互相套用。
- 文档成功返回示例的 `code`、`message` 为空字符串（模板未填），⚠ 以通用约定 `code == "200"` 判定。
- 限流 60 次/分钟（2026-03-31 起）。

---

## 10. 销售订单提交 / 审核 / 弃审

**Endpoint**: `POST /yonbip/sd/voucherorder/batchsubmit`、`…/batchaudit`、`…/batchunaudit`，body `{"data":[{"id":…}]}`。

提交返回 `infos[]` 含 `nextStatus`（如 `APPROVING` 审批中、`CONFIRMORDER`）。弃审错误示例：`code "200"` + `failCount: 1` + `messages: ["null"]`。

---

## 11. 销售订单删除

**Endpoint**: `POST /yonbip/sd/voucherorder/delete`（MDD 幂等）

```json
{"data": {"resubmitCheckKey": "…", "id": [2446326816231680], "code": ["UO-164820210917000001"]}}
```

`id` 与 `code` 都是**数组**且放在 `data` **对象**里（和采购删除的 `data` 数组不同）；两者不能同时为空，同时给时 ID 优先。

---

## 12. 单据事件

| 单据 | 事件编码 |
| --- | --- |
| 采购订单 | `st_purchaseorder_save`、`st_purchaseorder_audit`、`st_purchaseorder_unaudit`、`st_purchaseorder_close`、`st_purchaseorder_open`、`st_purchaseorder_delete`、`st_purchaseorder_purchaseordermodifyaudit` |
| 销售订单 | `SALE_SAVEORDER_NOTIFY_SENT`、`SALE_SUBMITORDER_NOTIFY_SENT`、`SALE_AUDITORDER_NOTIFY_SENT`、`SALE_UNAUDITORDER_NOTIFY_SENT`、`SALE_CLOSEORDER_NOTIFY_SENT`、`SALE_DELETEORDER_NOTIFY_SENT`、`SALE_AUDITORDER`… |

采购审核事件体是整张单据（表头 + `purchaseOrders[]`）；销售审核事件体只有 `billId`、`billCode`、`billNo`（示例外层还包了 `BILL_INFO`）。
收到后按 ID 调详情取完整数据。详见 `events.md`。

---

## 13. 本文件的 ⚠ 汇总

- ⚠ 文档自相矛盾：销售订单详情示例 URL 用 `http://api.diwork.com/yonsuite/…`——§8
- ⚠ 文档自相矛盾：列表错误示例 `code` 为数字 999，成功为字符串 `"200"`——§4
- ⚠ 文档未说明：`simpleVOs` 子表字段写法（说明文字被截断）、op 全集——§1
- ⚠ 文档未说明：金额不自洽时的行为；税目 / 汇率类型编码——§4 §9
- ⚠ 文档未说明：销售保存成功示例 code 为空串——§9
