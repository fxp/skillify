# 总账凭证与应收应付（GL_VOUCHER、AR / AP）

> 来源：open.kingdee.com「API文档」`GL_VOUCHER`、`BD_Account`、`BD_VOUCHERGROUP`、`AR_receivable`、`AP_Payable`、`AR_RECEIVEBILL` 的操作说明
> （API 版本 7.5.1800.6 / PT-146854，发布 2020-10-15，抓取于 2026-09-11）。**全部是文档原文转录，未用真实凭证调用验证。**
> 通用的 Save / Submit / Audit 参数见 [`bill-operations.md`](bill-operations.md)；查询见 [`bill-query.md`](bill-query.md)。

## 目录

1. 凭证相关 FormId
2. 凭证的操作范围（没有过账接口）
3. 凭证 Model 结构与必填项
4. 借贷金额怎么写
5. 核算维度 FDetailID
6. 示例：保存 → 提交 → 审核一张凭证
7. 查询凭证与分录
8. 科目 BD_Account、凭证字 BD_VOUCHERGROUP
9. 应收单 AR_receivable / 应付单 AP_Payable
10. 收款单 AR_RECEIVEBILL
11. 财务类其他 FormId

---

## 1. 凭证相关 FormId（官方 API 文档树「财务会计 → 总账」）

| 名称 | FormId | 名称 | FormId |
| --- | --- | --- | --- |
| 凭证 | `GL_VOUCHER` | 科目 | `BD_Account` |
| 账簿 | `BD_AccountBook` | 凭证字 | `BD_VOUCHERGROUP` |
| 会计日历 | `BD_ACCOUNTCALENDAR` | 币别 | `BD_Currency` |
| 汇率 | `BD_Rate` | 结算方式 | `BD_SETTLETYPE` |
| 摘要库 | `GL_Explanation` | 现金流量项目 | `GL_CashFlow` |
| 模式凭证 | `GL_VoucherModel` | 会计核算体系 | `Org_AccountSystem` |

## 2. 凭证的操作范围

`GL_VOUCHER` 在官方文档里只有这些操作：**Delete、Draft、Save、View、Submit、Audit、UnAudit、BatchSave、ExecuteBillQuery、QueryBusinessInfo、WorkflowAudit**。

- **没有过账（Post）、作废、出纳复核的 WebAPI 操作说明。** 字段说明里有 `FPOSTERID`（过账人）、`FCASHIERID`（出纳）、`FInvalid`（作废状态），
  但没有对应的 opNumber。能否用 ExcuteOperation 调这些操作 ⚠ 文档未说明——不要凭"应该有 Post"去编一个接口名。
- 凭证没有 Forbid / Enable / Push。

## 3. 凭证 Model 结构与必填项

**Model 模板（文档原文）**

```json
{
  "FVOUCHERID": 0,
  "FAccountBookID": {"FNumber": ""},
  "FDate": "1900-01-01",
  "FBUSDATE": "1900-01-01",
  "FVOUCHERGROUPID": {"FNumber": ""},
  "FVOUCHERGROUPNO": "",
  "FATTACHMENTS": 0,
  "FISADJUSTVOUCHER": "false",
  "FDocumentStatus": "",
  "FYEAR": 0,
  "FSourceBillKey": {"FNumber": ""},
  "FPERIOD": 0,
  "FIMPORTVERSION": "",
  "FEntity": [{
    "FEntryID": 0,
    "FEXPLANATION": "",
    "FACCOUNTID": {"FNumber": ""},
    "FDetailID": {"FDETAILID__FFLEX4": {"FNumber": ""}, "...": "FFLEX5–FFLEX13"},
    "FCURRENCYID": {"FNumber": ""},
    "FEXCHANGERATETYPE": {"FNumber": ""},
    "FEXCHANGERATE": 0,
    "FUnitId": {"FNUMBER": ""},
    "FPrice": 0,
    "FQty": 0,
    "FAMOUNTFOR": 0,
    "FDEBIT": 0,
    "FCREDIT": 0,
    "FSettleTypeID": {"FNumber": ""},
    "FSETTLENO": "",
    "FEXPORTENTRYID": 0,
    "FBUSNO": ""
  }]
}
```

**必填项（字段说明原文）**

| 位置 | 字段 key | 含义 |
| --- | --- | --- |
| 单据头 | `FAccountBookID` | 账簿 |
| 单据头 | `FDate` | 日期 |
| 单据头 | `FVOUCHERGROUPID` | 凭证字 |
| 单据头 | `FVOUCHERGROUPNO` | 凭证号 |
| 单据头 | `FDocumentStatus` | 审核状态 |
| 单据体 `FEntity` | `FACCOUNTID` | 科目编码 |
| 单据体 | `FCURRENCYID` | 币别 |
| 单据体 | `FEXCHANGERATETYPE` | 汇率类型 |

- **凭证号 `FVOUCHERGROUPNO` 和审核状态 `FDocumentStatus` 被标成必填**，但它们的取值规则（是否可以留空由系统编号、状态枚举值）⚠ 文档未说明。
  先按模板传空串 `""` 试，报错再按 `Errors` 调整。
- 单据头分录 key 是 **`FEntity`**，不是 `FEntry`、不是 `FVoucherEntry`。
- 字段 key 大小写混杂（`FVOUCHERGROUPID` 全大写、`FAccountBookID` 驼峰、`FUnitId` 里用 `FNUMBER`），逐字照抄。
- 会计年度 `FYEAR`、期间 `FPERIOD` 在模板里但未标必填，是否由 `FDate` 自动推出 ⚠ 文档未说明。
- 业务类型 `FSourceBillKey`、来源系统 `FSystemID` 用于标记外部来源，取值 ⚠ 文档未说明。

## 4. 借贷金额怎么写

- 每条分录有 `FDEBIT`（借方金额）和 `FCREDIT`（贷方金额）两个字段，另有 `FDC`（借贷方向）和 `FAMOUNTFOR`（原币金额）、`FAmount`（本位币金额）。
  模板只放了 `FDEBIT` / `FCREDIT` / `FAMOUNTFOR`，没放 `FDC` 和 `FAmount`。
- 按模板：**借方分录填 `FDEBIT`、贷方分录填 `FCREDIT`，另一个填 0**；不要只填金额再用正负号表示方向（⚠ 推断，文档未说明负数含义）。
- 金额单位是「元」还是「分」：模板为数值 `0`，⚠ 文档未说明单位；星空界面金额以元为单位（未实测）。不要套用支付类 API「整数分」的习惯。
- 外币凭证：`FCURRENCYID` + `FEXCHANGERATETYPE` + `FEXCHANGERATE` + `FAMOUNTFOR`（原币），本位币金额是否自动算 ⚠ 文档未说明。
- 借贷不平衡时 Save 是否拒绝 ⚠ 文档未说明；自己在调用前校验 `sum(FDEBIT) == sum(FCREDIT)`。

## 5. 核算维度 FDetailID

- 科目挂了核算维度（客户、供应商、部门、员工…）时，分录要在 `FDetailID` 里按维度填：
  `"FDetailID": {"FDETAILID__FFLEX4": {"FNumber": "..."}, "FDETAILID__FFLEX6": {"FNumber": "..."}}`。
- 模板给出的 key 是 `FDETAILID__FFLEX4` ~ `FDETAILID__FFLEX13`（**两个下划线**），**每个 FLEX 编号对应哪种维度 ⚠ 文档未说明**，
  且随账套的核算维度设置而变。用 `QueryBusinessInfo({"FormId":"GL_VOUCHER"})` 或查一张现有凭证（View）确认映射，不要猜。
- 科目的核算维度设置在 `BD_Account` 的单据体 `FEntity`（核算维度）里，必录类型 `FInputType` 为必填项。

## 6. 示例：保存 → 提交 → 审核一张凭证

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

CUR = {"FNumber": "<币别编码>"}              # 所有 <…> 都要先用 ExecuteBillQuery 在客户账套里查出来
RATE_TYPE = {"FNumber": "<汇率类型编码>"}
entries = [
    {"FEXPLANATION": "报销差旅费", "FACCOUNTID": {"FNumber": "<费用科目编码>"},
     "FCURRENCYID": CUR, "FEXCHANGERATETYPE": RATE_TYPE,
     "FDEBIT": 1200.00, "FCREDIT": 0},
    {"FEXPLANATION": "报销差旅费", "FACCOUNTID": {"FNumber": "<库存现金科目编码>"},
     "FCURRENCYID": CUR, "FEXCHANGERATETYPE": RATE_TYPE,
     "FDEBIT": 0, "FCREDIT": 1200.00},
]
assert round(sum(e["FDEBIT"] for e in entries), 2) == round(sum(e["FCREDIT"] for e in entries), 2)

saved = ok(sdk.Save("GL_VOUCHER", {"Model": {
    "FAccountBookID": {"FNumber": "<账簿编码>"},     # BD_AccountBook
    "FDate": "2026-09-11",
    "FVOUCHERGROUPID": {"FNumber": "<凭证字编码>"},  # BD_VOUCHERGROUP
    "FVOUCHERGROUPNO": "",                         # ⚠ 必填项但取值规则未说明
    "FDocumentStatus": "",                         # ⚠ 必填项但枚举未说明
    "FEntity": entries,
}}), "Save")

vid = saved["Result"]["ResponseStatus"]["SuccessEntitys"][0]["Id"]
ok(sdk.Submit("GL_VOUCHER", {"Ids": str(vid)}), "Submit")     # Ids 是逗号分隔字符串
ok(sdk.Audit("GL_VOUCHER", {"Ids": str(vid)}), "Audit")
```

- 上例所有编码（科目、币别、汇率类型、凭证字、账簿）都是占位，**金蝶没有全账套通用的固定编码**，先用 ExecuteBillQuery 查
  `BD_AccountBook`、`BD_VOUCHERGROUP`、`BD_Currency`、`BD_Account`。
- 凭证提交 / 审核后能否再 Save 修改 ⚠ 文档未说明，一般要先 UnAudit。
- 需要过账的话：WebAPI 文档里没有过账操作（见第 2 节），要和客户确认是否在星空里手工 / 自动过账。

## 7. 查询凭证与分录

```python
fields = "FVOUCHERID,FBillNo,FDate,FVOUCHERGROUPID,FVOUCHERGROUPNO,FEntity_FEntryID,FEXPLANATION,FACCOUNTID,FDEBIT,FCREDIT"
rows = json.loads(sdk.ExecuteBillQuery({
    "FormId": "GL_VOUCHER", "FieldKeys": fields,
    "FilterString": "", "StartRow": 0, "Limit": 2000,
}))
```

- 分录内码写 `FEntity_FEntryID`（单据体 key + 下划线 + 分录主键；文档示例写 `FEntryKey_FEntryId`，凭证分录主键字段是 `FEntryID`，大小写是否敏感 ⚠ 文档未说明）。
- 凭证编号字段是 `FBillNo`，凭证号是 `FVOUCHERGROUPNO`，两者不同。
- 每条分录一行，表头字段在每行重复；分页规则见 [`bill-query.md`](bill-query.md) 第 4 节。

## 8. 科目 BD_Account、凭证字 BD_VOUCHERGROUP

**BD_Account 操作**：Delete、View、Draft、Save、Submit、Audit、UnAudit、Forbid、Enable、BatchSave、ExecuteBillQuery、QueryBusinessInfo、WorkflowAudit（**没有 Allocate**）。

**BD_Account 必填项（字段说明原文）**：`FName`（名称）、`FNumber`（编码）、`FCreateOrgId`、`FUseOrgId`、`FGROUPID`（科目类别）、
`FDC`（余额方向）、`FAMOUNTDC`（发生额方向）；核算维度单据体 `FEntity` 的 `FInputType`（必录类型）。
子结构：外币核算 `FAcctCy`、核算维度 `FEntity`、分配信息 `FDistEntity`。`FDC` / `FAMOUNTDC` 的取值 ⚠ 文档未说明。

**BD_VOUCHERGROUP 操作**：同科目。字段说明本 skill 未展开，写入前用 QueryBusinessInfo 确认。
对接时通常只**查**凭证字（拿编码填 `FVOUCHERGROUPID`），不新建。

## 9. 应收单 AR_receivable / 应付单 AP_Payable

**操作**：Delete、Draft、Save、View、Submit、Audit、UnAudit、Push、BatchSave、ExecuteBillQuery、QueryBusinessInfo、WorkflowAudit。

**应收单必填项（字段说明原文）**

| 位置 | 字段 key | 含义 |
| --- | --- | --- |
| 单据头 | `FDATE` | 业务日期 |
| 单据头 | `FSETTLEORGID` | 结算组织 |
| 单据头 | `FCURRENCYID` | 币别 |
| 单据头 | `FBillTypeID` | 单据类型 |
| 单据头 | `FENDDATE_H` | 到期日 |
| 单据头 | `FCancelStatus` | 作废状态 |
| 单据头 | `FCUSTOMERID` | 客户 |
| 单据头 | `FPAYORGID` | 收款组织 |
| 表头财务 `FsubHeadFinc`（对象） | `FMAINBOOKSTDCURRID`、`FEXCHANGETYPE`、`FACCNTTIMEJUDGETIME` | 本位币、汇率类型、到期日计算日期 |

明细单据体是 **`FEntityDetail`**（数组），物料字段 `FMATERIALID`；收款计划 `FEntityPlan`；表头客户子结构的 key 是 `FsubHeadSuppiler`（原文如此拼写）。

**应付单必填项**：与应收单结构对称，差异是 `FSUPPLIERID`（供应商）替代客户，另多 `FDOCUMENTSTATUS`（单据状态）和 `FBUSINESSTYPE`（业务类型）为必填；`FPAYORGID` 在应付单里是「付款组织」。

- **应收单的日期是 `FDATE`（全大写），销售订单是 `FDate`**；应收的客户是 `FCUSTOMERID`，销售订单是 `FCustId`。从销售订单代码复制过来会写错 key。
- `FCancelStatus`（作废状态）、`FDOCUMENTSTATUS` 标了必填但枚举值 ⚠ 文档未说明。
- 通常应收单由销售出库单 Push 生成（带关联），而不是直接 Save；直接 Save 的应收单没有上游关联。

## 10. 收款单 AR_RECEIVEBILL

**操作**：Delete、Draft、Save、View、Submit、Audit、UnAudit、Push、Cancel、ALLReFund、BatchSave、ExecuteBillQuery、QueryBusinessInfo、WorkflowAudit。

**必填项（字段说明原文）**：单据头 `FDOCUMENTSTATUS`、`FCURRENCYID`、`FDATE`、`FBillTypeID`、`FCancelStatus`、
`FCONTACTUNITTYPE`（往来单位类型）、`FCONTACTUNIT`（往来单位）、`FPAYUNITTYPE`（付款单位类型）、`FPAYUNIT`（付款单位）、
`FBUSINESSTYPE`、`FPAYORGID`（收款组织）、`FSETTLECUR`（结算币别）、`FSETTLEMAINBOOKID`（结算本位币）；
明细 `FRECEIVEBILLENTRY` 的 `FSETTLETYPEID`（结算方式）、`FPURPOSEID`（收款用途）、`FPOSTDATE`（登账日期）。

- 往来单位是「类型 + 单位」两个字段成对出现（`FCONTACTUNITTYPE` + `FCONTACTUNIT`），类型的取值 ⚠ 文档未说明（用于区分客户 / 供应商 / 员工等）。
- 其他子单据体：源单明细 `FRECEIVEBILLSRCENTRY`、关联销售订单 `FASSSALESORDER`、应收票据明细 `FBILLRECEIVABLEENTRY`。

## 11. 财务类其他 FormId（仅名称与 FormId，未抓操作说明）

| 名称 | FormId | 名称 | FormId |
| --- | --- | --- | --- |
| 付款单 | `AP_PAYBILL` | 付款退款单 | `AP_REFUNDBILL` |
| 收款退款单 | `AR_REFUNDBILL` | 其他应收单 | `AR_OtherRecAble` |
| 其他应付单 | `AP_OtherPayable` | 应收核销单 | `AR_Match` |
| 应付核销单 | `AP_Match` | 手工日记账 | `CN_JOURNAL` |
| 银行对账单 | `CN_BANKACNTSTATE` | 付款申请单 | `CN_PAYAPPLY` |
| 应收票据 / 应付票据 | `CN_BILLRECEIVABLE` / `CN_BILLPAYABLE` | 资金调拨单 | `SC_FundsTransf` |
