# 基础资料：物料、客户、供应商（多组织分配、禁用、分组）

> 来源：open.kingdee.com「API文档」`BD_MATERIAL` / `BD_Customer` / `BD_Supplier` 的操作说明
> （API 版本 7.5.1800.6 / PT-146854，发布 2020-10-15，抓取于 2026-09-11）+ 官方 Python SDK 8.2.0 示例。
> **全部是文档原文 / SDK 源码转录，未用真实凭证调用验证。**
> 通用的 Save / Submit / Audit / ExcuteOperation 参数见 [`bill-operations.md`](bill-operations.md)；查询见 [`bill-query.md`](bill-query.md)。
> 科目、凭证字、币别等财务基础资料见 [`finance-vouchers.md`](finance-vouchers.md)。

## 目录

1. 基础资料和单据的区别
2. 多组织：创建组织、使用组织、分配
3. 物料 BD_MATERIAL
4. 客户 BD_Customer
5. 供应商 BD_Supplier
6. 禁用 / 反禁用
7. 分组：GroupSave / QueryGroupInfo
8. 其他常用基础资料 FormId
9. 同步基础资料的推荐流程

---

## 1. 基础资料和单据的区别

- 接口完全相同（Save / Submit / Audit / View / ExecuteBillQuery / Delete），只是 FormId 不同。
- 基础资料多了三类操作：**Allocate（分配到其他组织）**、**Forbid / Enable（禁用 / 反禁用，走 ExcuteOperation）**、**GroupSave / QueryGroupInfo（分组）**。
- 在单据里引用基础资料时写 `{"FNumber": "编码"}`（前提是 Save 的 `NumberSearch` 为默认的 true）。
  所以**同步顺序是先基础资料、后单据**；被引用的基础资料是否必须已审核才能引用 ⚠ 文档未说明（星空常规业务如此，未实测）。

## 2. 多组织：创建组织、使用组织、分配

- 物料、供应商的 `FCreateOrgId`（创建组织）和 `FUseOrgId`（使用组织）都是**必填项**；客户的必填项里有 `FCreateOrgId`，`FUseOrgId` 在模板里但字段说明未标必填。
- 两者都是组织引用：`{"FNumber": "<组织编码>"}`。SDK 示例写 `{"FNumber": 100}`（数字）。
- 一条基础资料建在 A 组织，要在 B 组织使用，**不是再 Save 一次**，而是调 Allocate 分配：

**Endpoint**：`POST {ServerUrl}/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Allocate.common.kdsvc`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `formid`（外层） | 字符串 | 是 | 如 `BD_MATERIAL` |
| `data.PkIds` | 字符串 | 是 | 被分配的基础资料**内码**集合 `"PkId1,PkId2"`（模板里写成数字 `0`，⚠ 文档自相矛盾） |
| `data.TOrgIds` | 字符串 | 是 | 目标组织**内码**集合 `"TOrgId1,TOrgId2"` |

- 注意这里要的是**内码**（FMATERIALID / 组织内码），不是编码。组织内码怎么查：ExecuteBillQuery 查组织表单——组织机构的 FormId 不在本次抓取的操作说明里（官方文档树「基础管理 → 组织管理」子系统下，⚠ 本 skill 未核对具体 FormId），在账套里用 BOS 设计器或 QueryBusinessInfo 确认。
- 分配后在目标组织是否还需要审核 ⚠ 文档未说明。
- SDK 还有 `CancelAllocate`（取消分配），2020 版文档无参数说明。

```python
res = json.loads(sdk.Allocate("BD_MATERIAL", {"PkIds": "100358,100359", "TOrgIds": "100407"}))
```

## 3. 物料 BD_MATERIAL

**已抓到的操作**：Delete、View、Draft、Save、Submit、Audit、UnAudit、Forbid、Enable、Allocate、CopyMtrl（物料模板复制）、
CMK_RetailStopSale / CMK_RetailResumeSale（零售停售 / 恢复）、BeforeCopy、UpdateBranchPrice、CreateBranchCatalog、
BatchSave、ExecuteBillQuery、QueryBusinessInfo、WorkflowAudit、GroupSave、QueryGroupInfo。

**Model 结构（模板节选，文档原文）**

```json
{
  "FMATERIALID": 0,
  "FCreateOrgId": {"FNumber": ""},
  "FUseOrgId": {"FNumber": ""},
  "FNumber": "",
  "FName": "",
  "FSpecification": "",
  "FMnemonicCode": "",
  "FOldNumber": "",
  "FDescription": "",
  "FMaterialGroup": {"FNumber": ""},
  "FSubHeadEntity": { "FEntryId": 0, "...": "零售特性（_CMK 字段）" },
  "SubHeadEntity":  { "FEntryId": 0, "FErpClsID": "", "FCategoryID": {"FNumber": ""}, "...": "基本信息" }
}
```

⚠ 模板里同时出现 `FSubHeadEntity`（零售特性）和 `SubHeadEntity`（没有 F 前缀，含物料属性、存货类别等），两个 key 仅差一个 `F`，
照模板原样写，不要"修正"。

**必填项（字段说明原文，按单据头 / 子单据头）**

| 位置 | 字段 key | 含义 |
| --- | --- | --- |
| 单据头 | `FName` | 名称 |
| 单据头 | `FCreateOrgId` | 创建组织 |
| 单据头 | `FUseOrgId` | 使用组织 |
| 零售特性 `FSubHeadEntity` | `FCodeType_CMK`、`FUnitId_CMK` | 条形码类型、计量单位 |
| 规格属性列表 / 基本信息等 | `FErpClsID` | 物料属性 |
| 同上 | `FBaseUnitId` | 基本单位 |
| 同上 | `FCategoryID` | 存货类别 |
| 同上 | `FSuite`、`FFeatureItem` | 套件、特征件子项 |
| 库存 | `FStoreUnitID`、`FCurrencyId`、`FUnitConvertDir` | 库存单位、币别、换算方向 |
| 销售 / 采购 | `FSaleUnitId`、`FSalePriceUnitId`、`FPurchaseUnitId`、`FPurchasePriceUnitId`、`FQuotaType` | 销售单位、销售计价单位、采购单位、采购计价单位、配额方式 |
| 计划 / 生产 | `FPlanningStrategy`、`FOrderPolicy`、`FFixLeadTimeType`、`FVarLeadTimeType`、`FCheckLeadTimeType`、`FOrderIntervalTimeType`、`FReserveType`、`FPlanOffsetTimeType`、`FIssueType`、`FOverControlMode`、`FMinIssueUnitId`、`FStandHourUnitId`、`FBackFlushType` | 计划与生产参数 |
| 序列号 | `FSNGenerateTime`、`FSNManageType` | 序列号生成时机、业务范围 |
| 库存属性 `FEntityInvPty` | `FInvPtyId` | 库存属性 |

- 字段说明把 30 多个字段标成必填，但 SDK 官方示例只传了 `FCreateOrgId`、`FUserOrgId`、`FNumber`、`FName` 四个就调 Save——
  这些「必填项」是否都有系统默认值 ⚠ 文档未说明（⚠ 文档与 SDK 示例不一致）。实践上先传最小集，按 `Errors[].FieldName` 补。
- ⚠ **SDK 示例写的是 `FUserOrgId`（多一个 r），模板和字段说明写的是 `FUseOrgId`**。以模板 `FUseOrgId` 为准；SDK 示例的拼写会不会被静默忽略 ⚠ 未实测。
- 编码 `FNumber` 在物料字段说明里没标必填：是否由编码规则自动生成取决于账套配置，⚠ 文档未说明。对接时建议总是显式传外部系统的编码，便于幂等。

**示例：保存 → 提交 → 审核一个物料**

```python
import json, os
from k3cloud_webapi_sdk.main import K3CloudApiSdk

sdk = K3CloudApiSdk(os.environ["KD_SERVER_URL"])
sdk.InitConfig(os.environ["KD_ACCT_ID"], os.environ["KD_USERNAME"], os.environ["KD_APP_ID"],
               os.environ["KD_APP_SECRET"], os.environ["KD_SERVER_URL"])

def ok(raw, step):
    res = json.loads(raw); st = res["Result"]["ResponseStatus"]
    if str(st["IsSuccess"]).lower() != "true":
        raise RuntimeError(f"{step}: {json.dumps(st.get('Errors'), ensure_ascii=False)}")
    return res

org = {"FNumber": "100"}
ok(sdk.Save("BD_MATERIAL", {"Model": {
    "FCreateOrgId": org, "FUseOrgId": org,
    "FNumber": "WL0001", "FName": "六角螺栓 M8", "FSpecification": "M8x30",
}}), "Save")
ok(sdk.Submit("BD_MATERIAL", {"Numbers": ["WL0001"]}), "Submit")
ok(sdk.Audit("BD_MATERIAL", {"Numbers": ["WL0001"]}), "Audit")
```

**幂等写法**：先 `ExecuteBillQuery` 按 `FNumber` 查内码，查到就带 `FMATERIALID` + `NeedUpDateFields` 更新，查不到再新建。
同一编码重复 Save 新建会怎样（报重复还是生成新记录）⚠ 文档未说明。

## 4. 客户 BD_Customer

**已抓到的操作**：Delete、View、Draft、Save、Submit、Audit、UnAudit、Forbid、Enable、Allocate、BatchSave、ExecuteBillQuery、QueryBusinessInfo、WorkflowAudit、GroupSave、QueryGroupInfo。

**必填项（字段说明原文）**：`FName`（客户名称）、`FCreateOrgId`（创建组织）、`FTRADINGCURRID`（结算币别）。

**Model 结构（模板节选）**

```json
{
  "FCUSTID": 0,
  "FCreateOrgId": {"FNumber": ""},
  "FNumber": "",
  "FUseOrgId": {"FNumber": ""},
  "FName": "",
  "FShortName": "",
  "FCOUNTRY": {"FNumber": ""},
  "FPROVINCIAL": {"FNumber": ""},
  "FADDRESS": "",
  "FTEL": "",
  "FINVOICETITLE": "",
  "FTAXREGISTERCODE": "",
  "FINVOICEBANKNAME": ""
}
```

- 主键是 `FCUSTID`（全大写），不是 `FCustomerId`；单据里引用客户的字段名又各不相同：销售订单 `FCustId`、销售出库 `FCustomerID`、应收单 `FCUSTOMERID`。**逐表单照抄。**
- `BD_Customer_All` 是「客户(包含非交易客户)」，与 `BD_Customer` 是两个 FormId，查询时别混用。
- 结算币别 `FTRADINGCURRID` 在模板里的位置 ⚠ 本次未展开核对（模板很长），写之前用 `QueryBusinessInfo` 或 View 一条现有客户确认层级。

## 5. 供应商 BD_Supplier

**已抓到的操作**：同客户。

**必填项（字段说明原文）**

| 位置 | 字段 key | 含义 |
| --- | --- | --- |
| 单据头 | `FName`、`FCreateOrgId`、`FUseOrgId` | 名称、创建组织、使用组织 |
| 财务信息 `FFinanceInfo` | `FPayCurrencyId` | 结算币别 |
| 组织信息 `FLocationInfo` | `FLocName`、`FLocAddress`、`FLocMobile`、`FLocNewContact` | 地点名称、通讯地址、手机、联系人 |

**子结构**：基本信息 `FBaseInfo`、商务信息 `FBusinessInfo`、财务信息 `FFinanceInfo`、银行信息 `FBankInfo`、组织信息 `FLocationInfo`、联系人 `FSupplierContact`。
其中哪些是对象、哪些是数组，以该表单 JSON 模板为准（`FBaseInfo` 模板里是对象，含 `FEntryId`）。

- 组织信息 `FLocationInfo` 的 4 个字段标了必填——是否只在传了该分录时才校验 ⚠ 文档未说明。
- 主键 `FSupplierId`；分组字段 `FGroup`；禁用人 `FForbiderId` 引用写的是 `{"FUserID": ""}`（不是 FNumber）。

## 6. 禁用 / 反禁用

走通用的 ExcuteOperation（拼写 Excute），opNumber 为 `Forbid` / `Enable`：

```python
json.loads(sdk.ExcuteOperation("BD_Customer", "Forbid", {"Numbers": ["CUST0001"]}))
json.loads(sdk.ExcuteOperation("BD_Customer", "Enable", {"Numbers": ["CUST0001"]}))
```

参数表见 [`bill-operations.md`](bill-operations.md) 第 7 节。禁用后的基础资料能否再被单据引用 ⚠ 文档未说明。

## 7. 分组：GroupSave / QueryGroupInfo

**GroupSave**：`POST {ServerUrl}/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.GroupSave.common.kdsvc`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `formid`（外层） | 字符串 | 是 | 如 `BD_MATERIAL` |
| `data.GroupFieldKey` | 字符串 | 是 | 分组字段 Key；「不填时取默认，无默认，取第一个分组」（与「必录」矛盾，⚠ 文档自相矛盾） |
| `data.FParentId` | 整型 | 否 | 父分组内码 |
| `data.FNumber` | 字符串 | 是 | 分组编码，**必须唯一** |
| `data.FName` | 字符串 | 是 | 分组名 |
| `data.FDescription` | 字符串 | 否 | 分组描述 |

返回模板：`{"Result":{"ResponseStatus":{...},"Id":""}}`——新分组内码在 `Result.Id`。
物料的分组字段在 Model 里是 `FMaterialGroup`，供应商是 `FGroup`；GroupFieldKey 应填哪个 ⚠ 文档未给示例值。

**QueryGroupInfo**：参数见 [`bill-query.md`](bill-query.md) 第 7 节。SDK 另有 `GroupDelete(data)`，2020 版文档无参数说明。

## 8. 其他常用基础资料 FormId（官方 API 文档树「基础资料」子系统）

| 名称 | FormId | 名称 | FormId |
| --- | --- | --- | --- |
| 部门 | `BD_Department` | 员工 | `BD_Empinfo` |
| 计量单位 | `BD_UNIT` | 仓库 | `BD_STOCK`（库存管理子系统） |
| 税率 | `BD_TaxRate` | 银行 | `BD_BANK` |
| 银行账号 | `CN_BANKACNT` | 付款条件 / 收款条件 | `BD_PaymentCondition` / `BD_RecCondition` |
| 销售员 | `BD_Saler` | 业务员 | `BD_OPERATOR` |
| 存货类别 | `BD_MATERIALCATEGORY` | 物料单位换算 | `BD_MATERIALUNITCONVERT` |
| 其他往来单位 | `FIN_OTHERS` | 联系对象 | `BD_ContactObject` |

这些表单本次只抓了名称和 FormId，没有抓操作说明；字段 key 用 `QueryBusinessInfo` 取。

## 9. 同步基础资料的推荐流程

1. 用 `ExecuteBillQuery` 按 `FNumber` 批量查已存在的内码（分页见 bill-query.md 第 4 节）。
2. 不存在的：`Save`（或 `BatchSave`）→ `Submit` → `Audit`；存在的：带内码 + `NeedUpDateFields` 更新。
3. 需要其他组织使用：`Allocate`（内码 + 目标组织内码）。
4. 每一步都检查 `Result.ResponseStatus.IsSuccess`，把 `Errors[].FieldName` / `Message` 写进日志。
5. 批量时按 `DIndex` 把失败项和原始数据对应起来。
