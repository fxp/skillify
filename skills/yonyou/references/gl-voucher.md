# 总账凭证与会计期间

> 来源：open.yonyoucloud.com API 文档「用友 YonBIP → 财务云 → 财务会计 → 总账 → 凭证」（`glVoucher`），经公开 JSON 抓取于 2026-09-11。
> 字段、示例、报错全部是**文档原文，未实测**（标「无凭证探测」的除外）。调用方式见 `auth-and-gateway.md`。

## 目录

1. 该分类有哪些接口
2. 凭证保存
3. 凭证列表查询
4. 凭证详情查询
5. 凭证删除
6. 会计期间查询
7. 凭证事件
8. 本文件的 ⚠ 汇总

---

## 1. 该分类有哪些接口

公开文档「凭证」分类下共 9 个接口（其中 1 个旧版「凭证列表查询」标为已废弃）：凭证详情查询、期间查询、凭证列表查询、
凭证保存、外部凭证信息回写、BIP 总账凭证冲销第三方系统凭证、凭证删除、下载凭证附件。本文件整理其中 5 个。

**没有凭证审核 / 记账接口。** 这些状态变化只能从事件感知（`GL_VOUCHER_EVENT_AUDIT_AFTER`、`GL_VOUCHER_EVENT_TALLY_AFTER`，见 §7）。
不要臆造 `/voucher/audit`、`/voucher/tally` 之类路径。

凭证状态码（`voucherStatus`，文档原文）：`00` 暂存、`01` 保存、`02` 错误、`03` 已审核、`04` 已记账、`05` 作废。

---

## 2. 凭证保存

**Endpoint**: `POST /yonbip/fi/ficloud/openapi/voucher/addVoucher`
**用途**: 由外部系统生成一张总账凭证。API 详情幂等配置为 `mdd`。

**请求体是顶层字段，没有 `data` 外壳**——和订单、档案的保存接口不同。

**关键参数（表头）**

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| accbookCode | string | **是** | | 账簿编码 |
| voucherTypeCode | string | **是** | | 凭证类型编码 |
| bodies | object[] | **是** | | 分录数组 |
| period | string | 否 | | 会计期间 `yyyy-MM`，支持调整期 |
| makerMobile / makerEmail | string | 二选一 | | 制单人手机号 / 邮箱，**不能都为空** |
| makeTime | string | 否 | 当前日期 | 制单日期 `yyyy-MM-dd` |
| billCode | int | 否 | 自动递增 | 凭证号 |
| code | string | 否 | | 凭证编码（≤32） |
| srcSystemCode | string | 否 | `figl` | 来源系统：总账 `figl`、产品成本 `fipcm`、固定资产 `assets`… |
| description | string | 否 | | 凭证头摘要 |
| attachedBill | int | 否 | 0 | 附单据数 |
| businessId | string | 否 | | 「业务唯一标识，用于业务幂等校验」 |
| externalSourceDataId / externalSourceDataType | string | 见说明 | | 外部来源数据 ID / 类型，说明写「(必填)」 |
| externalSourceSystemName / externalSourceDataCode | string | 否 | | 外部来源系统 / 编码 |
| voucherStatus | string | 否 | | 作废 `05`、正常 `00` |
| auditorMobile/Email、tallymanMobile/Email、signerMobile/Email 及对应 *Time | string | 否 | | 审核 / 记账 / 签字人与日期 |

**关键参数（分录 `bodies[]`）**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| description | string | **是** | 摘要 |
| accsubjectCode | string | **是** | 科目编码 |
| debitOriginal / creditOriginal | BigDecimal | 借贷二选一 | 原币借方 / 贷方金额 |
| debitOrg / creditOrg | BigDecimal | 借贷二选一 | 账簿本币借方 / 贷方金额 |
| organizeDebitAmount / debitGroup / debitGlobal（及 credit 对应） | BigDecimal | 否 | 组织本币 / 集团本币 / 全局本币（启用对应本币录入时） |
| currencyCode | string | 否 | 原币简称，默认账簿本位币 |
| rateType | string | 否 | 账簿汇率类型：`01` 基准、`02` 自定义 |
| rateOrg | BigDecimal | 否 | 账簿汇率；`rateOrgOps` 1 乘 / 2 除 |
| quantity / price | BigDecimal | 否 | 数量 / 单价 |
| busidate | string | 否 | 业务日期 `yyyy-MM-dd` |
| clientAuxiliaryList[] | object | 否 | 辅助核算：`filedCode`（辅助核算项编码，注意拼写 filed）、`valueCode`（档案值编码），两者必填 |
| cashflowList[] | object | 否 | 现金流量：`mainItemCode`、`amountOriginal`、`amountOrg` 必填 |
| settlementModeCode / billNo / billTime / bankVerifyCode | string | 否 | 结算方式 / 票据号 / 票据日期 / 银行对账码 |

文档对金额字段的说明原文：「借贷不能同时填写；原币和本币都要填写」。

**示例请求**

```bash
curl -sS -X POST "$YONBIP_GATEWAY_URL/yonbip/fi/ficloud/openapi/voucher/addVoucher?access_token=$TOKEN_ENC" \
  -H 'Content-Type: application/json' -d '{
  "accbookCode": "BOOK01", "voucherTypeCode": "01", "period": "2026-09",
  "makerMobile": "13800000000", "makeTime": "2026-09-11", "description": "差旅报销",
  "businessId": "EXP-20260911-0001",
  "bodies": [
    {"description": "差旅费", "accsubjectCode": "660201", "debitOriginal": 1200.00, "debitOrg": 1200.00},
    {"description": "差旅费", "accsubjectCode": "1002",   "creditOriginal": 1200.00, "creditOrg": 1200.00}
  ]}'
```

```python
from decimal import Decimal

def add_voucher(api, accbook: str, vtype: str, maker_mobile: str, lines: list[dict], biz_id: str) -> str:
    debit = sum(Decimal(str(l.get("debitOrg", 0))) for l in lines)
    credit = sum(Decimal(str(l.get("creditOrg", 0))) for l in lines)
    if debit != credit:
        raise ValueError(f"借贷不平: {debit} != {credit}")
    body = {"accbookCode": accbook, "voucherTypeCode": vtype, "makerMobile": maker_mobile,
            "businessId": biz_id, "bodies": lines}
    r = api.call("POST", "/yonbip/fi/ficloud/openapi/voucher/addVoucher", body=body)
    return r["data"]["voucherId"]
```

**示例响应**（文档原文）

```json
{"code": "200", "message": "OK",
 "data": {"voucherId": "2A4556F6-1AD0-47BA-9378-572B9B57D2FD", "voucherStatus": "01", "period": "2021-08",
          "billCode": 14, "totalDebitOrg": 12.00, "totalCreditOrg": 12.00,
          "accbook": {"id": "…", "code": "dxbook003", "name": "…"}, "voucherType": {"id": "…"}}}
```

失败：`{"code": "404", "message": "凭证保存不成功,账簿code不能为空！", "data": {}}`——**业务失败码是字符串 `"404"`，HTTP 状态并不是 404**，原因在 `message`。

**注意事项**

- 金额是「元」为单位的十进制数（示例 `13.10`），不是「分」。用 `Decimal` 或字符串避免浮点误差。
- 借方行只填 debit 系列、贷方行只填 credit 系列；不要用负数表示贷方。⚠ 文档未说明红字（负数）凭证的写法。
- ⚠ 文档自相矛盾：请求示例用 `"billno": "123"`（小写），参数表是 `billCode`（int）；示例分录里有 `secondOrgCode`，参数表只有 `twoLevelAccentityCode`。按参数表。
- ⚠ 文档自相矛盾：`externalSourceDataId`、`externalSourceDataType` 说明写「(必填)」，参数必填标记为否。
- ⚠ 文档自相矛盾：`voucherStatus` 入参说明「正常 00」，而返回与列表里 `00` 是「暂存」。
- ⚠ 文档未说明：MDD 幂等要求 `resubmitCheckKey` 放在 `data` 对象里（幂等性页原文「只对 body 体是 data 的结构有效」），
  但本接口没有 `data` 外壳；文档另给了 `businessId`（业务幂等校验）。建议传 `businessId`，重试前按 `externalSourceDataId` 或列表查一次。
- 账簿、凭证类型、科目、辅助核算项的**编码因租户而异**，不要写死示例值；科目编码体系由租户会计科目表决定。

---

## 3. 凭证列表查询

**Endpoint**: `POST /yonbip/fi/ficloud/openapi/voucher/queryVouchers`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| accbookCode | string | **是** | 账簿编码 |
| pager.pageIndex / pager.pageSize | int | 否 | 分页在 `pager` 对象里；每页**最多 1000** |
| periodStart / periodEnd | string | 否 | `yyyy-MM`，默认当前年月 |
| makeTimeStart / makeTimeEnd | string | 否 | `yyyy-MM-dd` |
| voucherStatusList | string[] | 否 | 如 `["01","03"]`；空则全部 |
| voucherTypeCodeList | string[] | 否 | 凭证类型编码 |
| accsubjectCodeList | string[] | 否 | 科目编码，自动包含下级科目 |
| billcodeMin / billcodeMax | int | 否 | 凭证号区间 |
| moneyRangeMin / moneyRangeMax | BigDecimal | 否 | 分录金额区间 |
| tsStart / tsEnd | string | 否 | 最后操作时间区间 `yyyy-MM-dd HH:mm:ss`（增量同步用） |
| srcSystemCode | string | 否 | 来源系统 |
| makerNameList / auditorNameList / tallymanNameList | string[] | 否 | 按人员**用户名**过滤 |

```python
r = api.call("POST", "/yonbip/fi/ficloud/openapi/voucher/queryVouchers", body={
    "accbookCode": "BOOK01", "pager": {"pageIndex": 1, "pageSize": 200},
    "periodStart": "2026-09", "periodEnd": "2026-09", "voucherStatusList": ["03", "04"]})
for rec in r["data"]["recordList"]:
    head, lines = rec["header"], rec["body"]
```

返回 `data.pageIndex / pageSize / recordCount / recordList[]`，每条 `{header, body[], externalMainMarking, externalSystemType,
externalIntegrationStatus}`。`header` 里是小写风格字段：`billcode`、`displayname`（如「记-32」）、`voucherstatus`、`totaldebit_org`、`maker{…}`。

**注意事项**

- 列表的分页是 `pager` 子对象，不是顶层 `pageIndex`（订单 / 档案接口是顶层）。
- 列表返回字段是 `billcode` / `voucherstatus` 小写，详情接口是 `billCode` / `voucherStatus` 驼峰——同一概念两种命名。
- 错误示例：`{"code":"404","message":"账簿code不能为空！","data":{}}`。

---

## 4. 凭证详情查询

**Endpoint**: `POST /yonbip/EFI/openapi/voucher/queryVoucherById`

```json
{"voucherId": "1674770115738468360"}
```

返回 `data`：`id`、`accBook` / `accBookObj{id,code,name}`、`periodUnion`、`voucherType` / `voucherTypeObj`、`billCode`、`makeTime`、
`displayName`、`voucherStatus`、`description`、`srcSystem` / `srcSystemObj[]`、`externalSource*`，以及分录。

**注意事项**

- 路径前缀是 `/yonbip/EFI/…`，和保存 / 列表的 `/yonbip/fi/ficloud/…` 不同，照抄。
- 虽是查询，方法是 **POST**、ID 放 body。

---

## 5. 凭证删除

**Endpoint**: `POST /yonbip/fi/voucher/del`

```json
{"ids": ["E5919010-0035-4996-A492-EB53F73CE6BA"]}
```

- `ids` 是数组，但文档原文「目前只支持单个 ID 删除」。
- 成功 `{"code":"200","message":"操作成功！","data":{}}`；失败 `{"code":"404","message":"凭证删除异常，未找到相应凭证！"}`。
- 文档请求示例 URL 写成 `//yonbip/fi/voucher/del`（双斜杠），⚠ 按单斜杠调用。⚠ 文档未说明已审核 / 已记账凭证能否删除。

---

## 6. 会计期间查询

**Endpoint**: `POST /yonbip/fi/fipub/basedoc/querybd/accperiod`

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| fields | string[] | 要返回的字段，如 `["id","code","name"]` |
| pageIndex / pageSize | long | 分页 |
| conditions[] | object | `{"field": "accperiodscheme", "operator": "=", "value": "<期间方案ID>"}` |
| disableshow | boolean | true 不显示停用 |

成功示例（文档原文）：`{"code":"200","success":"true","data":"{code: 2020-04, name: 2020-04, id: 2110181413671168}","total":"1"}`——
`data` 在示例里是一个**字符串**。⚠ 文档自相矛盾：返回参数表把 `data` 标为 object。解析时两种都兼容。
失败示例：`{"success":false,"message":"查询失败：…","data":null,"code":0}`，业务失败码为数字 0。

<!-- Gap: 文档请求示例 URL 为 /yonsuite/fi/fipub/basedoc/querybd/accperiod；无凭证探测（2026-09-11，P6 两次）在 c2 网关返回 HTTP 404 {"code":"310404","message":"网关上没有注册此API[/yonsuite/fi/fipub/basedoc/querybd/accperiod]…"}；接口地址 /yonbip/fi/fipub/basedoc/querybd/accperiod 已注册（P7 三次） -->
**文档请求示例的 `/yonsuite/…` 前缀是错的。** 无凭证探测（2026-09-11，复跑两次一致）：`/yonsuite/fi/fipub/basedoc/querybd/accperiod`
在网关上返回 `310404` 未注册；接口地址 `/yonbip/fi/fipub/basedoc/querybd/accperiod` 已注册。一律用 `/yonbip/`。

另：该接口带假 token 时返回的是 `text/plain` 纯文本 `非法token`，不是 JSON（见 `errors-and-limits.md` §2）。

---

## 7. 凭证事件

| 事件编码 | 含义 |
| --- | --- |
| `GL_VOUCHER_EVENT_ADD_AFTER` | 凭证新增后 |
| `GL_VOUCHER_EVENT_UPDATE_AFTER` | 凭证修改后 |
| `GL_VOUCHER_EVENT_DELETE_AFTER` | 凭证删除后 |
| `GL_VOUCHER_EVENT_AUDIT_AFTER` | 凭证审核后 |
| `GL_VOUCHER_EVENT_UNAUDIT_AFTER` | 凭证取消审核后 |
| `GL_VOUCHER_EVENT_TALLY_AFTER` | 凭证记账后 |
| `GL_VOUCHER_EVENT_UNTALLY_AFLTER` | 凭证取消记账后（编码里 `AFLTER` 是官方拼写，照抄） |
| `GL_VOUCHER_EVENT_EXTERNAL_INTEGRATION` | 总账外部集成事件 |

`GL_VOUCHER_EVENT_ADD_AFTER` 事件内容示例（文档原文）：

```json
{"voucherVO": [{"accbook": "xxx", "periodunion": "xxx", "id": "xxx", "billcode": 1, "bussid": "xxx"}]}
```

⚠ 文档自相矛盾：字段表把 `voucherVO` 标为 object，示例是数组。收到后用 `id` 调 §4 取完整凭证。订阅与解密见 `events.md`。

限流相关：2025-09-05 公告里，财务云「凭证类型查询 `/yonbip/AMP/yonbip-fi-epub/vouchertype/bill/list`」「会计期间方案查询
`/yonbip/digitalModel/bill/list`」等接口自 2025-09-15 起免费调用次数 40 次/分钟；本文件的凭证接口不在该公告列表中（见 `errors-and-limits.md` §7）。

---

## 8. 本文件的 ⚠ 汇总

- Gap（探测证实）：会计期间查询示例 URL 的 `/yonsuite/` 前缀未注册——§6
- ⚠ 文档自相矛盾：`billno` vs `billCode`、`secondOrgCode` vs `twoLevelAccentityCode`——§2
- ⚠ 文档自相矛盾：`externalSourceData*` 必填说明 vs 标记；`voucherStatus` 00 的含义——§2
- ⚠ 文档自相矛盾：期间查询 `data` 类型（字符串 vs object）；`voucherVO` 类型（数组 vs object）——§6 §7
- ⚠ 文档未说明：无 `data` 外壳的 MDD 幂等怎么传键；红字凭证写法；已审核凭证能否删除——§2 §5
