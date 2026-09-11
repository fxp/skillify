# 基础档案：客户、供应商、物料、计量单位

> 来源：open.yonyoucloud.com API 文档「用友 YonBIP → 应用平台 → 基础数据」下的客户信息 / 供应商信息 / 物料信息分类，
> 经公开 JSON `/iuap-ipaas-base/openPortal/api/getByVersionForTest/<apiId>/running` 抓取于 2026-09-11。
> 字段、示例、报错全部是**文档原文，未实测**；标「无凭证探测」的除外。调用方式见 `auth-and-gateway.md`。

## 目录

1. 先读：三个档案共同的坑
2. 客户档案列表查询
3. 客户详情批量查询
4. 客户档案保存（MDD 幂等）
5. 客户档案批量保存
6. 客户档案分配组织
7. 供应商档案列表查询
8. 供应商档案详情查询
9. 供应商档案批量保存（新）
10. 供应商档案分配组织
11. 物料档案分页查询
12. 物料档案批量详情查询
13. 物料档案保存（MDD 幂等）
14. 物料档案批量保存
15. 物料档案分配组织
16. 计量单位列表查询
17. 档案变更事件
18. 本文件的 ⚠ 汇总

---

## 1. 先读：三个档案共同的坑

1. **多语言字段有两套写法，按接口照抄。**
   - `merchant/idempotent/newinsert`、`product/idempotent/save`、`product/batchsave`：`{"simplifiedName","englishName","traditionalName"}`
   - `batch/merchant/save`、`vendor/batchSaveV2`、组织接口：`{"zh_CN","en_US","zh_TW"}`
   写错不会有编译期提示。⚠ 文档未说明传错形式时是报错还是静默丢弃。
2. **ID 与编码同时传时谁优先，每个接口不一样。** 客户详情「ID 优先」；物料保存「Code 优先」（`orgCode` 优先于 `orgId`、
   `manageClassCode` 优先于 `manageClass`）；采购类分类「ID > Code > Name」。只传一个最稳。
3. **「保存」多是 upsert。** 物料保存：「编码不存在视为新增，编码存在则为修改」；供应商 `_status` 支持 `InsertUpdate`。
   同步程序用编码当业务主键，别先删后建。
4. **管理组织 vs 使用组织。** 档案建在管理组织（`createOrg` / `org`），其他组织要用须「分配组织」（§6 §10 §15），不是再保存一次。
5. **写接口的外壳不统一**：客户保存 `{"data":{…}}`，客户批量 `{"data":[…]}`，物料批量保存文档示例直接是数组 `[{…}]`，
   详情批量查询示例也是数组。以各节为准。
6. **增量同步用 `pubts` / `beganTime`**，每个接口字段名不同（见各节），且是「大于」还是「大于等于」各写各的。

---

## 2. 客户档案列表查询

**Endpoint**: `POST /yonbip/digitalModel/merchant/newlist`
**用途**: 按条件分页查客户档案（不含子表）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| pageIndex | long | **是** | 1 | 页码 |
| pageSize | long | **是** | 500 | 每页条数，**最大 5000** |
| code / name | string | 否 | | 精确匹配 |
| fuzzyName / fuzzyShortname | string | 否 | | 模糊匹配 |
| createOrgId / createOrgCode | string | 否 | | 管理组织 |
| customerClassId / customerClassCode / customerClassIdList / customerClassCodeList | | 否 | | 客户分类 |
| creditCode / creditCodeList | | 否 | | 证照号码 |
| beganTime / endTime | DateTime | 否 | | 时间范围 `yyyy-MM-dd HH:mm:ss` |
| pubts | date | 否 | | 时间戳，「大于（或等于）当前值」 |
| filterPotential | boolean | 否 | true | 过滤潜在客户 |

```python
page, rows = 1, []
while True:
    r = api.call("POST", "/yonbip/digitalModel/merchant/newlist",
                 body={"pageIndex": page, "pageSize": 500, "pubts": "2024-04-10 14:50:00"})
    batch = r["data"] or []
    rows += batch
    if len(batch) < 500:
        break
    page += 1
```

返回 `data` **直接是数组**（不是 `{recordList, recordCount}`）：每项 `id`、`code`、`name{simplifiedName…}`、`createOrgId/Code`、
`belongOrgId/Code`（使用组织）、`transTypeId/Code`（客户类型）、`customerClassId/Code`、`taxPayingCategories`（0 一般 / 1 小规模 / 2 境外 / 99 其他）…

**注意事项**

- 没有总数字段，翻页靠「本页条数 < pageSize」判断结束。⚠ 文档未说明。
- 本接口超时配置 10 秒（API 详情 JSON `timeOut`），大页可能超时，pageSize 取几百即可。
- 成功示例 `code` 是数字 `200`。

---

## 3. 客户详情批量查询

**Endpoint**: `POST /yonbip/digitalModel/merchant/newBatchDetail`

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| id | long | 客户 ID；与 code 同时给时 **ID 优先** |
| code | string | 客户编码 |
| belongOrgId / belongOrgCode | string | 使用组织；同时给时 ID 优先 |

返回 `data[]`，字段同列表并含地址、联系人等子表。

**注意事项**

- ⚠ 文档自相矛盾：参数表把 `id/code/…` 列为顶层字段，请求示例却是数组 `[{"id":…, "code":…}]`，且示例 URL 是
  `/merchant/batchDetail`（少了 `new`）。按接口地址 `newBatchDetail`；body 形态需实测（见 verification-plan）。

---

## 4. 客户档案保存（MDD 幂等）

**Endpoint**: `POST /yonbip/digitalModel/merchant/idempotent/newinsert`
**用途**: 单个客户新增，支持 `resubmitCheckKey` 幂等（API 详情 `idempotent: "mdd"`）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data | object | 是 | 外壳 |
| data.resubmitCheckKey | string | 否 | 幂等键，≤32 位，租户内同一接口唯一（见 `errors-and-limits.md`） |
| data.code | string | 是（说明文字） | 客户编码 |
| data.name | object | 是（说明文字） | `{"simplifiedName": 必填, "englishName", "traditionalName"}` |
| data.createOrgCode | string | 是（说明文字） | 管理组织**编码** |
| data.transTypeCode | string | 否 | 客户类型编码，不填用默认交易类型 |
| data.customerClassCode | string | 否 | 客户分类编码 |
| data.enterpriseNature | short | 否 | 0 企业 / 1 个人 / 2 其他；决定 `enterpriseName` / `personName` / `orgName` 哪个必填 |
| data.licenseType / creditCode | | 否 | 0 统一社会信用代码 / 1 营业执照 / 3 身份证…；证照号码 |
| data.taxPayingCategories | short | 否 | 0 一般纳税人（默认）… |
| data.merchantAddressInfos[] | | 否 | `addressCode`、`address`、`isDefault` 必填，默认只能一个 |
| data.merchantContactInfos[] | | 否 | `fullName`、`isDefault` 必填 |
| data.merchantAgentFinancialInfos[] | | 否 | `currencyName`、`accountType`(0 对公/1 对私)、`bankName`、`openBankName`、`bankAccount`、`bankAccountName`、`isDefault` 必填 |
| data.merchantApplyRanges[] | | 否 | 适用范围 `orgIdCode`；新增不传按分级管控默认处理 |

```python
body = {"data": {"resubmitCheckKey": f"cust-{ext_id}"[:32],
                 "code": "C0001", "name": {"simplifiedName": "北京某某科技有限公司"},
                 "createOrgCode": "global00", "enterpriseNature": 0,
                 "enterpriseName": "北京某某科技有限公司", "licenseType": 0, "creditCode": "9111…"}}
r = api.call("POST", "/yonbip/digitalModel/merchant/idempotent/newinsert", body=body)
new_id = r["data"][0]["id"]          # 返回 data 是数组 [{"id","code"}]
```

成功（文档原文）：`{"code":"200","success":true,"data":[{"id":123456,"code":"编码"}]}`；
失败：`{"message":"客户名称不能为空!","code":0,"data":null}`——业务失败 `code` 为数字 0。

**注意事项**

- <!-- Gap: 文档请求示例 URL 为 /yonbip/digitalModel/merchant/newinsert_copy，无凭证探测（2026-09-11，P8 两次）在 c2 网关返回 HTTP 404 {"code":"310404","message":"网关上没有注册此API[/yonbip/digitalModel/merchant/newinsert_copy]…"}；接口地址 /merchant/idempotent/newinsert 带假 token 返回 310036（已注册，P9 两次） -->
  **文档示例 URL `…/merchant/newinsert_copy` 是错的**：无凭证探测（2026-09-11）该路径在网关上未注册（`310404`），
  而接口地址 `…/merchant/idempotent/newinsert` 已注册。按接口地址调用。
- ⚠ 文档自相矛盾：`code` / `name` / `createOrgCode` 在说明里写「必填」，参数表的 required 标记却是否。当作必填。

---

## 5. 客户档案批量保存

**Endpoint**: `POST /yonbip/digitalModel/batch/merchant/save`（幂等配置 `non`）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data | object[] | 是 | 客户数组 |
| data[]._status | string | **是** | `Insert` 新增 / `Update` 修改 |
| data[].code | string | **是** | 客户编码 |
| data[].org_code | string | **是** | 管理组织编码 |
| data[].name | object | **是** | `{"zh_CN": 必填}`——注意这里是 zh_CN 形式 |
| data[].customerClass_code | string | **是** | 客户分类编码（或 `customerClassErpCode` 二选一） |
| data[].merchantAppliedDetail | object | **是** | 客户业务信息（适用范围详情） |
| data[].merchantApplyRanges[] | | 否 | 修改时不填 |
| data[].merchantContacterInfos[] / merchantAddressInfos[] / merchantAgentFinancialInfos[] / merchantAgentInvoiceInfos[] | | 否 | 修改时传已存在的联系人名 / 地址编码 / 银行账号 / 发票抬头即视为修改该条 |

**注意事项**

- 子表行也要带 `_status`（示例里每行 `"_status": "Insert"`）。
- 布尔在示例里常写成字符串 `"isDefault": "true"`。⚠ 文档未说明是否接受 JSON 布尔。
- 失败示例 `{"code":"999","message":"服务端逻辑异常"}`。⚠ 文档未说明部分成功时的返回形态。

---

## 6. 客户档案分配组织

**Endpoint**: `POST /yonbip/digitalModel/merchant/batchDo`

```json
{"data": [{"merchantId": 2285747004510464, "orgIds": ["2285679325860352"], "createOrgId": 2285747049763072}]}
```

三个字段都必填；`orgIds` 是字符串数组，`merchantId`、`createOrgId` 是数字。返回 `data.sucessCount / failCount / messages[]`
（注意官方拼写 `sucessCount`）。文档注明这些计数「异步调用时无效」。

---

## 7. 供应商档案列表查询

**Endpoint**: `POST /yonbip/digitalModel/vendor/list`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| pageIndex / pageSize | int | **是** | 默认 1 / 10 |
| code | string | 否 | 供应商编码 |
| vendorclass | string | 否 | 分类 ID |
| org / vendororg | string[] | 否 | 管理组织 / 使用组织 ID 数组 |
| stopstatus | boolean | 否 | false 启用 / true 停用 |
| freezestatus | string | 否 | 0 正常 / 1 冻结 / 2 黑名单 |
| queryChildrenTable | string | 否 | 是否返回子表，文档不建议传（影响性能） |
| simple.pubts | string | 否 | 查询**大于等于**该时间的档案 |

返回 `data.recordList[]`（`id`、`code`、`name`、`org`、`vendorclass`、`vendorApplyRangeId`、`stop`、`pubts`…）、
`data.recordCount`、`data.pageCount`。

**注意事项**

- 增量字段在 `simple` 子对象里：`{"simple": {"pubts": "…"}}`，不是顶层 `pubts`。
- 同一供应商在每个使用组织下各有一条 `vendorApplyRangeId`，列表可能按使用组织重复出现。⚠ 文档未说明去重规则。
- 无凭证探测（2026-09-11）：本路径不带 token 返回 `310001`、假 token 返回 `310036`（HTTP 均 200），路径已注册。

---

## 8. 供应商档案详情查询

**Endpoint**: `GET /yonbip/digitalModel/vendor/detail?id=<ID>&vendorApplyRangeId=<…>&orgId=<…>`

`id` 必填；`vendorApplyRangeId` 与 `orgId` 说明写「二选一必填」，又写「orgId 不传则查管理组织」。⚠ 文档自相矛盾，
想取管理组织视角时只传 `id` 试一次，取使用组织视角时传 `orgId`。返回 `data` 含企业信息、`vendorextends`（业务属性）等。

---

## 9. 供应商档案批量保存（新）

**Endpoint**: `POST /yonbip/digitalModel/vendor/batchSaveV2`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data | object[] | 是 | |
| data[]._status | string | **是** | `Insert` / `Update` / `InsertUpdate`（按 code 判断，存在则更新） |
| data[].code | string | **是** | 供应商编码 |
| data[].name | muti_lang | **是** | `{"zh_CN","en_US","zh_TW"}` |
| data[].org / org_code | string | 二选一 | 管理组织 ID / 编码，不能同时为空 |
| data[].vendorclass / vendorclass_code | string | 二选一 | 分类 ID / 编码，不能同时为空 |
| data[].id | string | 修改时必填 | |
| data[].vendorextends | object | 否 | 业务属性：`taxitems_code`、`currency_code`、`settlemethod_code`、`paymentagreement_code`、`department_code`… |
| data[].vendorcontactss[] / vendorbanks[] / vendorOrgs[] / vendorAddresses[] | | 否 | 联系人 / 银行 / 适用范围 / 地址 |

```python
body = {"data": [{"_status": "InsertUpdate", "code": "V0001", "name": {"zh_CN": "上海某某材料有限公司"},
                  "org_code": "global00", "vendorclass_code": "001"}]}
r = api.call("POST", "/yonbip/digitalModel/vendor/batchSaveV2", body=body)
if r["data"]["failCount"]:
    raise RuntimeError(r["data"]["messages"])
```

**注意事项**

- 文档给了两个错误示例：整体失败 `{"code":"999","message":"服务端逻辑异常"}`；部分失败时 **`code` 仍为 `"200"`**，
  `data.failCount: 1`、`data.messages: [{"message":"国家编码:CNX未找到","key":…}]`。必须检查 `failCount`。
- 联系人子表字段名是 `vendorcontactss`（两个 s），照抄。

---

## 10. 供应商档案分配组织

**Endpoint**: `POST /yonbip/digitalModel/vendor/addvendorsuitorg`

```json
{"data": [{"vendorId": 2016415922573568, "orgIds": ["666666", "1649769528807680"]}]}
```

与客户分配不同：只要 `vendorId` + `orgIds`，没有 `createOrgId`。

---

## 11. 物料档案分页查询

**Endpoint**: `POST /yonbip/digitalModel/product/listproductbycondition`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| pageIndex / pageSize | int | **是** | 默认 1 / 10 |
| productCode / productName | string | 否 | 物料编码 / 名称 |
| managerClassIdList / managerClassCodeList | string[] | 否 | 物料分类 |
| orgId | string | 否 | 使用组织 ID |
| beganTime / endTime | DateTime | 否 | 时间戳比较区间 |
| erpCodeList | string[] | 否 | 商家编码 |

返回 `data.recordList[]`（`id`、`code`、`name`、`unitId/unitCode/unitName`、`manageClass/Code/Name`、`createOrgId`…）
和 `data.recordCount`、`data.pageCount`。注意请求里叫 `managerClassCodeList`，返回里叫 `manageClassCode`（多一个 r 少一个 r）。

---

## 12. 物料档案批量详情查询

**Endpoint**: `POST /yonbip/digitalModel/product/batchdetailnew`

参数 `id` 或 `productCode`（同给时 ID 优先）、`orgId` 或 `orgCode`（**必须二选一**，同给时 ID 优先）。返回 `data[].detail`，
含采购 / 库存 / 批发 / 零售各业务单位及价格。

⚠ 文档自相矛盾：参数表是顶层对象，请求示例是数组 `[{…}]`。

---

## 13. 物料档案保存（MDD 幂等）

**Endpoint**: `POST /yonbip/digitalModel/product/idempotent/save`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data | object | **是** | 外壳 |
| data.resubmitCheckKey | string | 否 | 幂等键 |
| data.code | string | **是** | 物料编码；**不存在则新增，存在则修改** |
| data.name | object | **是** | `{"simplifiedName",…}` |
| data.orgCode / orgId | string | 二选一 | 管理组织；同给时 **Code 优先** |
| data.manageClassCode / manageClass | string | 二选一 | 物料分类；Code 优先 |
| data.realProductAttribute | int | **是** | 1 实物 / 2 虚拟 |
| data.unitUseType | long | **是** | 1 用物料模板的计量单位 / 2 用物料自己的 |
| data.unitCode / unit | | 条件 | 主计量单位（`unitUseType=2` 时需要）；Code 优先 |
| data.detail | object | **是** | 物料业务信息：`purchaseUnitCode`、`stockUnitCode`、`businessAttribute`（"1,7" 逗号串：1 采购 7 销售 3 自制 2 委外）… |
| data.productOrges[] | | 否 | 分配组织，只能新增不能改删 |

返回 `{"code":"200","message":"操作成功","data":{"id":…}}`。

---

## 14. 物料档案批量保存

**Endpoint**: `POST /yonbip/digitalModel/product/batchsave`（幂等配置 `non`）

字段与 §13 相同但**没有 `data` 外壳**：参数表是顶层字段，文档示例是数组 `[{ "orgCode":…, "code":…, "detail":{…} }]`。
部分成功示例：`{"code":"200","data":{"count":2,"sucessCount":1,"failCount":1,"messages":"物料分类编码:00000111未找到","infos":[…]}}`——
`messages` 这里是**字符串**，客户 / 供应商批量接口里是数组。

---

## 15. 物料档案分配组织

**Endpoint**: `POST /yonbip/digitalModel/product/assignOrg`

```json
{"data": [{"productId": 2285747004510464, "orgIds": ["2285679325860352"], "createOrgId": 2285747049763072}]}
```

---

## 16. 计量单位列表查询

**Endpoint**: `POST /yonbip/digitalModel/unit/list`

`pageIndex`、`pageSize` 必填；`code`、`simple.name`、`simple.code`、`open_pubts_begin` / `open_pubts_end` 选填。
返回 `recordList[]`：`id`、`code`、`name`、`unitGroup`、`precision`、`truncationType`（4 四舍五入 / 1 舍 / 0 入）、`stopstatus`。
物料、订单里的单位字段多用单位**编码**（如 `KGM`、`001`），先用本接口建映射。

---

## 17. 档案变更事件

| 对象 | 事件编码（节选） |
| --- | --- |
| 客户 | `YXYBASEDOC_AA_MERCHANT_INSERT` / `_UPDATE` / `_DELETE`、`YXYBASEDOC_AA_MERCHANTLIST_STOP` / `_UNSTOP`、`YXYBASEDOC_AA_MERCHANT_ALLOCATEORG` |
| 供应商 | `BASEDOC_VENDOR_ADD_AFTER` / `_UPDATE_AFTER` / `_DELETE_AFTER` / `_ENABLE_AFTER` / `_DISABLE_AFTER` |
| 物料 | `YXYBASEDOC_PC_PRODUCT_INSERT` / `_UPDATE` / `_DELETE` / `_STOP` / `_UNSTOP`、`iuap-apdoc-material_PC_PRODUCT_ADDPROSUITORG_NOTIFY`（分配组织） |

事件体结构互不相同（客户是扁平对象、供应商是 `userObject.archives[]`、物料示例是 `archive{…}`），见 `events.md` §6。

---

## 18. 本文件的 ⚠ 汇总

- Gap（探测证实）：客户保存示例 URL `newinsert_copy` 未注册——§4
- ⚠ 文档自相矛盾：客户保存必填项（说明 vs 标记）——§4；客户 / 物料批量详情的 body 形态与示例 URL——§3 §12
- ⚠ 文档自相矛盾：供应商详情 `vendorApplyRangeId` / `orgId` 必填规则——§8
- ⚠ 文档未说明：多语言写法用错的后果、ID/Code 优先级之外的冲突处理——§1
- ⚠ 文档未说明：客户列表无总数时的终止条件、供应商列表按使用组织重复、布尔是否接受字符串——§2 §5 §7
