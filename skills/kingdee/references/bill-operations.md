# 单据保存 / 提交 / 审核 / 下推 / 状态操作

> 来源：open.kingdee.com「API文档」各业务对象的操作说明（API 版本 7.5.1800.6 / PT-146854，发布 2020-10-15，抓取于 2026-09-11）
> + 官方 Python SDK `kingdee.cdp.webapi.sdk` 8.2.0 源码。**全部是文档原文 / SDK 源码转录，未用真实凭证调用验证。**
> 请求体外层包装规则见 [`bill-query.md`](bill-query.md) 第 2 节；返回结构见 [`errors-and-responses.md`](errors-and-responses.md)。

## 目录

1. 生命周期：一张单据要调几次
2. Save：新建与修改
3. Model 数据包怎么写（基础资料引用、分录、布尔、日期）
4. 修改已有单据：NeedUpDateFields 与 IsDeleteEntry
5. Draft（暂存）与 BatchSave（批量保存，含异步轮询）
6. Submit / Audit / UnAudit / Delete
7. ExcuteOperation：禁用、作废、关闭、冻结等状态操作
8. Push：下推生成下游单据
9. WorkflowAudit：工作流审批
10. 端到端示例：建销售订单 → 提交 → 审核
11. SDK 里有、文档没收录的接口

---

## 1. 生命周期：一张单据要调几次

文档把保存、提交、审核列成**三个独立操作**，各有自己的 ServiceName：

```
Save（或 Draft 暂存） ──► Submit ──► Audit
                                 ◄── UnAudit（反审核）
Delete：删除（能删哪些状态 ⚠ 文档未说明）
```

- Save 之后单据是否自动提交 / 审核 ⚠ 文档未说明——**按三次调用写**，每一步都检查返回。
- 保存成功后从 `Result.ResponseStatus.SuccessEntitys[].Id / Number`（或 `Result.Id` / `Result.Number`）拿内码和编码，传给下一步。
- 单据状态字段是 `FDocumentStatus`，其枚举值 ⚠ 文档未说明（抓到的字段说明只列了字段名）。

| 操作 | ServiceName（`Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.` + ） | SDK 方法 | 外层 body |
| --- | --- | --- | --- |
| 保存 | `Save` | `Save(formid, data)` | `{"formid","data"}` |
| 暂存 | `Draft` | `Draft(formid, data)` | `{"formid","data"}` |
| 批量保存 | `BatchSave` | `BatchSave` / `BatchSaveQuery` | `{"formid","data"}` |
| 提交 | `Submit` | `Submit` | `{"formid","data"}` |
| 审核 | `Audit` | `Audit` | `{"formid","data"}` |
| 反审核 | `UnAudit` | `UnAudit` | `{"formid","data"}` |
| 删除 | `Delete` | `Delete` | `{"formid","data"}` |
| 状态操作（禁用、作废…） | `ExcuteOperation`（**拼写就是 Excute，没有 e**） | `ExcuteOperation(formid, opNumber, data)` | `{"formid","opNumber","data"}` |
| 下推 | `Push` | `Push` | `{"formid","data"}` |
| 工作流审批 | `WorkflowAudit` | `WorkflowAudit(data)` | `{"data"}` |

## 2. Save：新建与修改

**Endpoint**：`POST {ServerUrl}/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Save.common.kdsvc`
**用途**：保存一张单据 / 一条基础资料。新建和修改是同一个接口。

**关键参数（`data` 内，文档原文）**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `Model` | JSON 对象 | 是 | — | 表单数据包，结构见各表单的 JSON 模板 |
| `NeedUpDateFields` | 数组 | 否 | — | 需要更新的字段 `[key1,key2]`；**更新单据体字段要把单据体 key 也加上** |
| `NeedReturnFields` | 数组 | 否 | — | 需返回的字段 `[key, entitykey.key]`；单据体字段写 `单据体key.字段key` |
| `IsDeleteEntry` | 布尔 | 否 | **true** | 是否删除已存在的分录（见第 4 节） |
| `SubSystemId` | 字符串 | 否 | — | 表单所在子系统内码 |
| `IsVerifyBaseDataField` | 布尔 | 否 | false | 是否验证所有基础资料有效性 |
| `IsEntryBatchFill` | 布尔 | 否 | true | 是否批量填充分录 |
| `ValidateFlag` | 布尔 | 否 | true | 是否验证标志 |
| `NumberSearch` | 布尔 | 否 | true | 是否用编码搜索基础资料（为 true 时基础资料引用可以写 `{"FNumber": "..."}`） |
| `InterationFlags` | 字符串 | 否 | — | 交互标志，分号分隔 `"flag1;flag2"`；文档举例：允许负库存 `STK_InvCheckResult` |

文档备注（原文要点）：
1. Model 里的**字段顺序不建议改变**，否则可能相互影响；出现字段值被覆盖或丢失，可以尝试把字段顺序向后调整。
2. 模板默认包含允许引入的字段，实际按需构建即可。
3. 创建关联关系参考的是 `club.kingdee.com` 的一个老帖链接（已无法访问，⚠ 文档未说明具体做法；关联上下游请用第 8 节 Push）。

**示例响应（文档原文，未实测）**

```json
{"Result":{"ResponseStatus":{"ErrorCode":"","IsSuccess":"false","Errors":[{"FieldName":"","Message":"","DIndex":0}],
 "SuccessEntitys":[{"Id":"","Number":"","DIndex":0}],"SuccessMessages":[{"FieldName":"","Message":"","DIndex":0}],"MsgCode":""},
 "Id":"","Number":"","NeedReturnData":[{}]}}
```

## 3. Model 数据包怎么写

以下规则全部来自各表单的官方 JSON 模板：

- **基础资料 / 组织引用写成对象**：`"FCustId": {"FNumber": "CUST0001"}`、`"FSaleOrgId": {"FNumber": "100"}`。
  直接写字符串 `"FCustId": "CUST0001"` 在模板里没有出现过。
- **引用对象里的键名不统一**：多数是 `FNumber`，但也有 `FNUMBER`（如 `FBillTypeID`、凭证的 `FUnitId`）、`FNAME`（销售订单 `FReceiveContact`）、`FUserID`（供应商 `FForbiderId`）。
  是否大小写敏感 ⚠ 文档未说明——**逐字照抄该表单模板**，不要统一改写。
- SDK 示例里组织编码写的是数字 `{"FNumber": 100}`，模板里是字符串 `""`；两者是否等价 ⚠ 文档未说明，建议传字符串。
- **单据体是数组**：`"FSaleOrderEntry": [{...}, {...}]`；表头下的「子单据头」（如销售订单 `FSaleOrderFinance`、应收单 `FsubHeadFinc`）是**对象**不是数组。
- **主键**：表头主键（如 `FID`、`FMATERIALID`、`FCUSTID`、`FVOUCHERID`）和分录主键 `FEntryID` 模板里都是 `0`。
  新建时传 0 / 不传、修改时传已有内码——这是按「实体主键」字段语义的推断，⚠ 文档未明确写「0 表示新建」。
- **布尔值**：参数说明写「布尔类型」，模板里却是字符串 `"true"` / `"false"`（⚠ 文档自相矛盾）。两种写法服务端是否都认 ⚠ 未实测。
- **日期**：模板占位是 `"1900-01-01"`，格式 `yyyy-MM-dd`；带时间的格式 ⚠ 文档未说明。
- **必填字段看字段说明里的 `(必填项)`**，各表单清单见 [`master-data.md`](master-data.md)、[`finance-vouchers.md`](finance-vouchers.md) 和第 10 节。
- **单据类型 `FBillTypeID` 在采购订单、销售订单、应收应付单、入库出库单里都是必填项**，值是单据类型编码（`{"FNUMBER": "..."}`），
  具体编码因账套而异 ⚠ 文档未给出，先用 ExecuteBillQuery 查已有单据的 `FBillTypeID` 或问实施顾问。

## 4. 修改已有单据：NeedUpDateFields 与 IsDeleteEntry

这是改单时最容易丢数据的地方：

- `IsDeleteEntry` **默认 true**，文档含义是「是否删除已存在的分录」。按字面理解：用默认值修改一张 5 行的订单、Model 里只放 1 行，
  **另外 4 行会被删掉**。只改部分分录时显式传 `"IsDeleteEntry": "false"`（⚠ 未实测，文档只有参数说明没有示例）。
- 只更新部分字段时用 `NeedUpDateFields` 列出要改的 key；**改单据体字段时，单据体 key 本身也要列进去**（文档原文：「更新单据体字段得加上单据体key」）。
- 要改的分录必须带上它的 `FEntryID`，否则会被当成新分录（推断，⚠ 文档未说明）。分录内码可用 ExecuteBillQuery 查 `单据体Key_FEntryId`。
- 已审核的单据能否直接 Save 修改 ⚠ 文档未说明；通常要先 UnAudit。

```python
# 只把采购订单 CGDD000123 的第 2 行数量改成 50，其他行不动
data = {
    "IsDeleteEntry": "false",
    "NeedUpDateFields": ["FPOOrderEntry", "FQty"],
    "Model": {
        "FID": po_id,                                   # 表头内码
        "FPOOrderEntry": [{"FEntryID": entry_id, "FQty": 50}],
    },
}
res = json.loads(sdk.Save("PUR_PurchaseOrder", data))
```

## 5. Draft 与 BatchSave

**Draft（暂存）**：参数与 Save 完全相同，ServiceName `...DynamicFormService.Draft`。
Push 的 `IsDraftWhenSaveFail` 说明里写「暂存的单据是没有编码的」，暂存单据是否校验必填项 ⚠ 文档未说明。

**BatchSave**：`...DynamicFormService.BatchSave`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `Model` | **JSON 数组** | 是 | — | 多个数据包（Save 是对象，BatchSave 是数组） |
| `BatchCount` | 整型 | 否 | — | 服务端开启的线程数；「数据包数应大于此值，否则无效」 |
| 其余 | — | — | — | 与 Save 相同（NumberSearch、ValidateFlag、IsDeleteEntry、IsEntryBatchFill、NeedUpDateFields、NeedReturnFields、SubSystemId、InterationFlags、IsVerifyBaseDataField） |

返回模板：`{"Result":{"ResponseStatus":{...},"NeedReturnData":[{}]}}`。每条数据的成败看 `Errors[].DIndex` / `SuccessEntitys[].DIndex`（数据包下标）。
单次数据包条数上限 ⚠ 文档未说明。

**异步轮询模式（SDK `BatchSaveQuery`，源码转录）**：大批量时 SDK 会在 body 顶层额外加两个键：

```json
{"formid": "BD_MATERIAL", "data": {...}, "beginmethod": "BeginQueryImpl", "querymethod": "QueryAsyncResult"}
```

响应是 `{"Status": 0|1|2, "TaskId": "...", "Result": ...}`（0=Pending、1=Running、2=Complete，来自 SDK 枚举）。
未完成时每秒 POST 一次 `...DynamicFormService.QueryAsyncResult.common.kdsvc`，body 为
`{"queryInfo": "{\"TaskId\": \"...\", \"Cancelled\": false}"}`（注意 `queryInfo` 的值是**字符串化的 JSON**），直到 `Status == 2` 取 `Result`。
这套协议 2020 版文档里没有，⚠ 仅见于 SDK 源码。

## 6. Submit / Audit / UnAudit / Delete

四个接口的 `data` 结构几乎相同（文档原文）：

| 参数 | 类型 | 必填 | 说明 | 出现在 |
| --- | --- | --- | --- | --- |
| `CreateOrgId` | 字符串 | 否 | 创建者组织内码（模板里是 `0`） | 全部 |
| `Numbers` | **数组** | 编码 / 内码二选一 | `["No1","No2"]` | 全部 |
| `Ids` | **逗号分隔字符串** | 编码 / 内码二选一 | `"Id1,Id2"` | 全部 |
| `NetworkCtrl` | 布尔 | 否 | 是否启用网控，默认 false | 全部 |
| `SelectedPostId` | 整型 | 否 | 工作流发起员工岗位内码；身兼多岗不传时默认第一个岗位 | 仅 Submit |
| `InterationFlags` | 字符串 | 否 | 交互标志，分号分隔（如 `STK_InvCheckResult`） | Audit、UnAudit |

- **`Numbers` 是数组、`Ids` 是字符串**——同一个请求里两个「集合」参数类型不同，别都写成数组。
- 返回结构同 Save（无 `Id`/`Number`/`NeedReturnData`）。批量提交时逐条看 `Errors` / `SuccessEntitys` 的 `DIndex`。

```python
num = "XSDD000001"
for step in ("Submit", "Audit"):
    res = json.loads(getattr(sdk, step)("SAL_SaleOrder", {"Numbers": [num]}))
    st = res["Result"]["ResponseStatus"]
    if str(st["IsSuccess"]).lower() != "true":
        raise RuntimeError(f"{step} 失败: {st.get('Errors')}")
```

## 7. ExcuteOperation：状态操作

**Endpoint**：`POST {ServerUrl}/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExcuteOperation.common.kdsvc`
**用途**：执行「禁用 / 反禁用 / 作废 / 反作废 / 关闭 / 冻结 / 终止…」这类没有独立接口的操作，靠 `opNumber` 指定。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `formid`（外层） | 字符串 | 是 | 业务对象表单 Id |
| `opNumber`（外层） | 字符串 | 是 | 操作编码，见下表 |
| `data.CreateOrgId` | 字符串 | 否 | 创建者组织内码 |
| `data.Numbers` | 数组 | 二选一 | 单据编码集合 |
| `data.Ids` | 字符串 | 二选一 | 单据内码 `"Id1,Id2"` |
| `data.PkEntryIds` | 集合 | 分录级操作时必录 | `[{"Id":"Id1","EntryIds":"EntryId1,EntryId2"}]`（文档写「字符串类型」，模板是数组，⚠ 文档自相矛盾） |
| `data.NetworkCtrl` | 布尔 | 否 | 是否启用网控 |

已抓到的 opNumber（按表单，全部来自官方操作列表，**大小写照抄**）：

| 表单 | opNumber |
| --- | --- |
| 物料 / 客户 / 供应商 / 科目 / 凭证字 | `Forbid`（禁用）、`Enable`（反禁用） |
| 采购订单 `PUR_PurchaseOrder` | `Cancel`、`Uncancel`、`MRPClose`、`UnMRPClose`、`Terminate`、`UnTerminate`、`Freeze`、`UnFreeze`、`BillClose`、`BillUnClose` |
| 销售订单 `SAL_SaleOrder` | `Cancel`、`YLBillClose`、`YLUnBillClose`、`YLTerminate`、`YLUnTerminate`、`YLFreeze`、`YLUnFreeze`、`YLMRPClose`、`YLUnMRPClose` |
| 采购入库 / 销售出库 | `Cancel`、`UnCancel`、`BackServiceUnAudit`、`PayableClose` / `PayableUnClose`（入库） |
| 收款单 `AR_RECEIVEBILL` | `Cancel`、`ALLReFund` |

- 注意反作废：采购订单是 `Uncancel`（小写 c），入库 / 出库单是 `UnCancel`（大写 C）；销售订单的关闭 / 冻结类操作带 `YL` 前缀。
  这些 opNumber 是否大小写敏感 ⚠ 文档未说明。
- 客户账套二开后操作编码可能不同，以星空 BOS 里该表单的操作列表为准。

```python
res = json.loads(sdk.ExcuteOperation("BD_MATERIAL", "Forbid", {"Numbers": ["WL0001"]}))
```

## 8. Push：下推

**Endpoint**：`POST {ServerUrl}/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Push.common.kdsvc`
**用途**：按单据转换规则由上游单据生成下游单据（如采购订单 → 采购入库单），会建立上下游关联。**不要用 Save 自己拼下游单据来"模拟"下推**——那样没有关联关系。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `Ids` | 字符串 | 二选一 | — | 上游单据内码 `"Id1,Id2"` |
| `Numbers` | 数组 | 二选一 | — | 上游单据编码 |
| `EntryIds` | 字符串 | 按分录下推时必录 | — | 分录内码，逗号分隔；**按分录下推时单据内码和编码不用填，否则按整单下推** |
| `RuleId` | 字符串 | 未启用默认规则时必录 | — | 转换规则内码 |
| `TargetFormId` | 字符串 | 启用默认规则时必录 | — | 目标单据 FormId，如 `STK_InStock` |
| `IsEnableDefaultRule` | 布尔 | 否 | false | 是否启用默认转换规则 |
| `TargetBillTypeId` | 字符串 | 否 | — | 目标单据类型内码 |
| `TargetOrgId` | 整型 | 否 | — | 目标组织内码 |
| `IsDraftWhenSaveFail` | 布尔 | 否 | false | 下游保存失败时是否暂存（暂存单据没有编码） |
| `CustomParams` | 字典 | 否 | — | 透传给转换插件，平台不解析 |

- **`RuleId` 和 `TargetFormId + IsEnableDefaultRule` 二选一**：不传 RuleId 就必须 `"IsEnableDefaultRule": "true"` 并给 `TargetFormId`。
- 返回：文档备注「`ConvertResponseStatus` 返回的是单据转换的结果，`ResponseStatus` 返回的是单据转换后下游单据保存的结果」，
  但返回模板里只有 `ResponseStatus`（⚠ 文档自相矛盾），两个都要检查。
- 下推生成的下游单据是保存状态，仍需自己 Submit / Audit（推断，⚠ 文档未说明）。

```python
res = json.loads(sdk.Push("PUR_PurchaseOrder", {
    "Numbers": ["CGDD000123"],
    "TargetFormId": "STK_InStock",
    "IsEnableDefaultRule": "true",
}))
```

## 9. WorkflowAudit：工作流审批

**Endpoint**：`POST {ServerUrl}/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.WorkflowAudit.common.kdsvc`（外层只有 `data`）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `FormId` | 字符串 | 是 | 业务对象表单 Id |
| `Ids` | 字符串（模板为数组 `[]`，⚠ 文档自相矛盾） | 二选一 | 单据内码 |
| `Numbers` | 数组 | 二选一 | 单据编码 |
| `UserId` | 整型 | ⚠ 未标必填 | 审批人用户 Id |
| `UserName` | 字符串 | ⚠ 未标必填 | 用户名称 |
| `ApprovalType` | 整型 | ⚠ 未标必填 | **1 审批通过、2 驳回、3 终止** |
| `ActionResultId` | 字符串 | ⚠ 未标必填 | 审批项 Id |

返回模板：`{"Result":{"ResponseStatus":"","OperationResults":"{}"}`。
没有启用工作流的单据直接用 Audit；启用了工作流的单据用 Audit 会怎样 ⚠ 文档未说明。

## 10. 端到端示例：建销售订单 → 提交 → 审核

销售订单 `SAL_SaleOrder` 的必填项（字段说明原文）：表头 `FSaleOrgId`、`FDate`、`FCustId`、`FSalerId`、`FBillTypeID`；
财务信息 `FSaleOrderFinance.FSettleCurrId`；明细 `FSaleOrderEntry` 的 `FMaterialId`、`FUnitID`、`FPriceUnitId`、`FSettleOrgIds`、
`FDeliveryDate`、`FReserveType`、`FStockUnitID`、`FOUTLMTUNIT`。明细数量 / 单价 / 含税单价 / 税率的 key 是 `FQty`、`FPrice`、`FTaxPrice`、`FEntryTaxRate`。

```python
import json, os
from k3cloud_webapi_sdk.main import K3CloudApiSdk

sdk = K3CloudApiSdk(os.environ["KD_SERVER_URL"])
sdk.InitConfig(os.environ["KD_ACCT_ID"], os.environ["KD_USERNAME"], os.environ["KD_APP_ID"],
               os.environ["KD_APP_SECRET"], os.environ["KD_SERVER_URL"])

def ok(raw, step):
    res = json.loads(raw)
    st = res["Result"]["ResponseStatus"]
    if str(st["IsSuccess"]).lower() != "true":
        raise RuntimeError(f"{step} 失败: {json.dumps(st.get('Errors'), ensure_ascii=False)}")
    return res

model = {
    "FBillTypeID": {"FNUMBER": "<销售订单单据类型编码>"},   # 账套相关，先查
    "FDate": "2026-09-11",
    "FSaleOrgId": {"FNumber": "100"},
    "FCustId": {"FNumber": "CUST0001"},
    "FSalerId": {"FNumber": "<销售员编码>"},
    "FSaleOrderFinance": {"FSettleCurrId": {"FNumber": "<币别编码>"}},   # 账套相关，先查 BD_Currency
    "FSaleOrderEntry": [{
        "FMaterialId": {"FNumber": "WL0001"},
        "FUnitID": {"FNumber": "<计量单位编码>"},     # 账套相关，先查 BD_UNIT
        "FPriceUnitId": {"FNumber": "<计量单位编码>"},
        "FStockUnitID": {"FNumber": "<计量单位编码>"},
        "FQty": 10,
        "FTaxPrice": 113,
        "FEntryTaxRate": 13,
        "FDeliveryDate": "2026-09-20",
        "FSettleOrgIds": {"FNumber": "100"},
    }],
}
saved = ok(sdk.Save("SAL_SaleOrder", {"Model": model, "NeedReturnFields": ["FBillNo"]}), "Save")
number = saved["Result"]["ResponseStatus"]["SuccessEntitys"][0]["Number"]
ok(sdk.Submit("SAL_SaleOrder", {"Numbers": [number]}), "Submit")
ok(sdk.Audit("SAL_SaleOrder", {"Numbers": [number]}), "Audit")
```

- 上例中 `FReserveType`、`FOUTLMTUNIT` 标了必填但没传：它们是否有默认值 ⚠ 文档未说明，保存报错时按 `Errors[].FieldName` 补。
- 编码类值（单据类型、币别、计量单位、组织）全部因账套而异，**不要把示例里的编码当成金蝶的固定值**。

## 11. SDK 里有、文档没收录的接口

SDK 8.2.0 还封装了以下 ServiceName（`DynamicFormService.` 之后），2020 版文档里没有参数说明，⚠ 文档未说明，用前先在客户服务器上确认版本支持：
`FlexSave`（弹性域保存）、`SendMsg`（发送消息）、`GroupDelete`（分组删除）、`SwitchOrg`（切换组织，SDK 示例 `{"Model":{"FSALEORGID":{"FNumber":102}}}`）、
`Disassembly`（拆单，文档操作列表里入库 / 出库单有此项但无参数说明）、`CancelAllocate`、`CancelAssign`、`GetSysReportData`（报表数据）、
`AttachmentUpload` / `AttachmentDownLoad`（附件）。
