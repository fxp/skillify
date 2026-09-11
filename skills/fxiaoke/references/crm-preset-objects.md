# CRM 预置对象：客户 / 联系人 / 线索 / 商机 的增删改查

> 来源：https://developer.fxiaoke.com/openapi_v2/object/ 下 CustomersAndContacts（AccountObj、ContactObj）、
> OpportunitiesAndLeads（LeadsObj、OpportunityObj、NewOpportunityObj）各页，common/system/team、common/system/lock 页（抓取于 2026-09-11），
> 旧版 wiki「全局返回码」（artiId=27）、「CRM对象接口调用说明」（artiId=1146）。**本文件全部为文档原文，未实测。**
> 请求头、thirdTraceId、`FxkClient` 见 `auth.md`；查询条件与分页见 `query-and-paging.md`；字段值格式见 `objects-and-fields.md`。

## 目录
1. 一套接口通吃所有预置对象
2. 创建：`/cgi/crm/v2/data/create`
3. 取详情：`/cgi/crm/v2/data/get`
4. 修改：`/cgi/crm/v2/data/update`
5. 删除三步曲：作废 invalid → 删除 delete；恢复 recover
6. 变更负责人：`/cgi/crm/v2/data/changeOwner`
7. 公海 / 线索池：领取 choose、退回 return、移除 remove
8. 相关团队：`/cgi/crm/team/*`
9. 锁定 / 解锁：`/cgi/crm/v2/object/lock|unlock`
10. 权限与业务限制
11. 本文件的 ⚠

---

## 1. 一套接口通吃所有预置对象

客户、联系人、线索、商机、部门、人员……**所有预置对象共用同一组路径**，只靠 `dataObjectApiName` 区分：

| 动作 | Endpoint | 关键 body |
| --- | --- | --- |
| 创建 | `POST /cgi/crm/v2/data/create` | `data.object_data` |
| 详情 | `POST /cgi/crm/v2/data/get` | `data.dataObjectApiName` + `data.objectDataId` |
| 列表查询 | `POST /cgi/crm/v2/data/query` | 见 `query-and-paging.md` |
| 修改 | `POST /cgi/crm/v2/data/update` | `data.object_data._id` |
| 作废 | `POST /cgi/crm/v2/data/invalid` | `data.object_data_id` |
| 删除（已作废的） | `POST /cgi/crm/v2/data/delete` | `data.idList` |
| 恢复（已作废的） | `POST /cgi/crm/v2/data/recover` | `data.idList` |
| 变更负责人 | `POST /cgi/crm/v2/data/changeOwner` | `data.Data[]` |
| 公海 / 线索池领取 | `POST /cgi/crm/v2/data/choose` | `data.apiName` + `data.objectIds` |
| 退回公海 / 线索池 | `POST /cgi/crm/v2/data/return` | `data.objectPoolId` + `backReason` |
| 从公海移除 | `POST /cgi/crm/v2/data/remove` | `data.objectPoolId` + `isKeepOwner` |

apiName：客户 `AccountObj`、联系人 `ContactObj`、销售线索 `LeadsObj`、商机 `OpportunityObj`、商机2.0 `NewOpportunityObj`，
更多见 `objects-and-fields.md` 第 1 节。**自定义对象（`__c`）不能用这组路径**，见 `custom-objects.md`。

## 2. 创建

**Endpoint**: `POST /cgi/crm/v2/data/create?thirdTraceId={uuid4}`
**用途**: 创建一条预置对象数据（可带从对象一起创建）。成功返回新数据的 `dataId`。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| triggerApprovalFlow | Boolean | 否 | **true** | 是否触发审批流（对所有对象有效） |
| triggerWorkFlow | Boolean | 否 | **true** | 是否触发工作流 |
| hasSpecifyTime | Boolean | 否 | false | true 时才使用 `object_data.create_time`，否则忽略 |
| hasSpecifyCreatedBy | Boolean | 否 | false | true 时才使用 `object_data.created_by`，否则忽略 |
| includeDetailIds | Boolean | 否 | false | 主从一起创建时是否返回从对象 id 列表 |
| data.object_data | Map | 是 | — | 主对象字段，**`dataObjectApiName` 也放在这里面** |
| data.details | Map | 否 | — | 从对象数据，key 为从对象 apiName |
| data.optionInfo | Map | 否 | — | `skipFuncValidate` / `isDuplicateSearch` / `useValidationRule`（⚠ 含义文档未说明） |

**示例请求**

```bash
curl -sS -X POST "https://$FXK_HOST/cgi/crm/v2/data/create?thirdTraceId=$(uuidgen | tr A-Z a-z)" \
  -H "authorization: Bearer $FXK_TOKEN" -H "x-fs-ea: $FXK_EA" -H "x-fs-userid: $FXK_USER_ID" \
  -H 'Content-Type: application/json' \
  -d '{
    "triggerApprovalFlow": false,
    "data": {
      "object_data": {
        "dataObjectApiName": "AccountObj",
        "name": "上海示例科技有限公司"
      }
    }
  }'
```

```python
resp = fxk.post("/cgi/crm/v2/data/create", {
    "triggerApprovalFlow": False,       # 集成导入通常不想触发审批；按业务决定
    "data": {
        "object_data": {
            "dataObjectApiName": "LeadsObj",
            "name": "张三-官网留资",
            # 其余字段按 describe 的 type 填：数字/金额写字符串、日期写毫秒、单选写 options.value
        }
    },
})
new_id = resp["dataId"]
```

**示例响应**

```json
{"traceId": "E-O.827xxxxxx", "errorDescription": "success", "dataId": "68faxxxxxx", "errorMessage": "OK", "errorCode": 0}
```

**注意事项**
- `dataObjectApiName` 在 `data.object_data` **里面**，不是 `data` 下一层——这点和 get / query / invalid 不同（它们放在 `data` 下）。
- `triggerApprovalFlow` / `triggerWorkFlow` 默认都是 **true**：不显式传 false，接口写入的数据会进审批、触发工作流（发通知、改字段）。批量导入前先想清楚。
- 必填字段由 describe 的 `is_required` 决定，缺了会报错；负责人等字段是否必填也看 describe。
- ⚠ 文档未说明：示例 `object_data` 里同时有 `"object_describe_api_name": "hello"`（占位值），是否必填、要不要等于 apiName 没写。首次调通时建议两个都填对象 apiName，并按 verification-plan 核实。
- ⚠ 文档自相矛盾：`details` 在创建示例里是 `{"detail_api_name": {}}`（map），在修改示例里是 `{"api_name": [ {...} ]}`（列表）。从对象按「key = 从对象 apiName，value = 记录列表」写更合理，未证实。

## 3. 取详情

**Endpoint**: `POST /cgi/crm/v2/data/get?thirdTraceId={uuid4}`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| includeNull | Boolean | 否 | false | 是否返回 null 字段 |
| data.dataObjectApiName | String | 是 | — | 如 `AccountObj` |
| data.objectDataId | String | 是 | — | 数据 `_id` |

```python
acc = fxk.post("/cgi/crm/v2/data/get",
               {"data": {"dataObjectApiName": "AccountObj", "objectDataId": acc_id}})["data"]
print(acc.get("name"), acc.get("owner"), acc.get("owner__r"))
```

响应 `data` 就是这条记录的字段 map（`_id`、`name`、`create_time`、`lock_status`、`is_deleted`、`created_by__r`……）。值为空的字段不返回。

## 4. 修改

**Endpoint**: `POST /cgi/crm/v2/data/update?thirdTraceId={uuid4}`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| triggerApprovalFlow | Boolean | 否 | true | 同创建 |
| triggerWorkFlow | Boolean | 否 | true | 同创建 |
| data.object_data | Map | 是 | — | 要改的字段 + `_id` + `dataObjectApiName` |
| data.object_data._id | String | 是 | — | 被修改数据的 id |
| data.details | Map | 否 | — | 从对象数据 |
| data.optionInfo | Map | 否 | — | 同创建 |

```python
fxk.post("/cgi/crm/v2/data/update", {
    "triggerWorkFlow": False,
    "data": {"object_data": {"_id": acc_id, "dataObjectApiName": "AccountObj", "tel": "021-12345678"}},
})
```

**注意事项**
- **负责人（owner）不能通过修改接口改**，必须用第 6 节的 changeOwner（旧版 wiki 1146）。
- 只传要改的字段（⚠ 文档未说明未传字段是保持不变还是被清空，按 PATCH 语义推测，未证实）。
- 数据被锁定时修改会失败；自定义对象的修改接口有 `skipDataStatusValidate` 参数可改锁定数据，预置对象页没有列出（⚠ 文档未说明）。

## 5. 删除三步曲：作废 → 删除；恢复

纷享的删除是**两段式**：先「作废」（进回收站，可恢复），再对已作废的数据「删除」（彻底删）。直接对正常数据调 delete 不行。

### 5.1 作废

**Endpoint**: `POST /cgi/crm/v2/data/invalid?thirdTraceId={uuid4}`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data.dataObjectApiName | String | 是 | 如 `AccountObj` |
| data.object_data_id | String | 是 | **单个**数据 id（字符串，不是列表） |

```json
{"data": {"object_data_id": "5a9ce894f125ae9befxxxxxx", "dataObjectApiName": "AccountObj"}}
```

- ⚠ 文档自相矛盾：参数说明写「数据id列表」，类型却是 String、示例是单个字符串。自定义对象页明确说 v2 作废**不支持批量**，预置对象按单条写。

### 5.2 删除（只能删已作废的）

**Endpoint**: `POST /cgi/crm/v2/data/delete?thirdTraceId={uuid4}`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data.dataObjectApiName | String | 是 | 对象 apiName |
| data.idList | List | 是 | 数据 id 列表。「删除之前请先作废数据，价目表明细可以直接删除」 |

```python
fxk.post("/cgi/crm/v2/data/invalid", {"data": {"dataObjectApiName": "AccountObj", "object_data_id": acc_id}})
fxk.post("/cgi/crm/v2/data/delete",  {"data": {"dataObjectApiName": "AccountObj", "idList": [acc_id]}})
```

- 页面错误：客户分组下的「删除」页（`AccountObj/delete.html`）正文其实是**费用明细 FeeDetailObj**；客户删除看 `AccountObj/delete-acc.html`。参数结构一致。

### 5.3 恢复已作废的数据

**Endpoint**: `POST /cgi/crm/v2/data/recover?thirdTraceId={uuid4}` —— `data.dataObjectApiName` + `data.idList`（列表）。

## 6. 变更负责人

**Endpoint**: `POST /cgi/crm/v2/data/changeOwner?thirdTraceId={uuid4}`
**用途**: 改数据的负责人。这是改负责人的**唯一**途径（update 改不了）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data.dataObjectApiName | String | 是 | 如 `AccountObj`、`LeadsObj` |
| data.Data | List | 文档标「否」 | 每项 `{"objectDataId": 数据id, "ownerId": 负责人}`；注意是**大写 D 的 `Data`** |

```json
{
  "data": {
    "dataObjectApiName": "AccountObj",
    "Data": [{"objectDataId": "5a9914fcf125ae0a1axxxxxx", "ownerId": ["1000"]}]
  }
}
```

- ⚠ 文档自相矛盾：预置对象页示例写 `"ownerId": "[1000]"`（字符串里套方括号），自定义对象页 V2 示例写 `"ownerId": ["1000"]`（列表）。上面按列表写；若报参数错误再试另一种（见 verification-plan）。
- ⚠ 文档自相矛盾：`Data` 实际上不可能是可选的，参数表却标「否」。
- **在公海 / 线索池里的数据，任何人都没有改负责人的权限**，会报「无此操作的数据权限」——先用第 7 节 choose 领取出来再改（旧版 wiki 27）。

## 7. 公海 / 线索池：领取、退回、移除

客户可以在「公海」（`HighSeasObj`）里，线索可以在「线索池」里。这些数据没有负责人，普通修改 / 改负责人都会被拒。

### 7.1 领取

**Endpoint**: `POST /cgi/crm/v2/data/choose?thirdTraceId={uuid4}`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data.apiName | String | 是 | 只支持 `AccountObj`、`LeadsObj`（注意这里叫 `apiName`，不是 `dataObjectApiName`） |
| data.objectIds | List[String] | 是 | 数据 id 列表 |

```json
{"data": {"apiName": "LeadsObj", "objectIds": ["603dabc14ae65400011aec90"]}}
```

领取人是谁 ⚠ 文档未说明——推测为 `x-fs-userid` 对应的员工；要分给别人，领取后再 changeOwner。

### 7.2 退回公海 / 线索池

**Endpoint**: `POST /cgi/crm/v2/data/return?thirdTraceId={uuid4}`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data.apiName | String | 是 | `AccountObj` 或 `LeadsObj` |
| data.objectIds | List[String] | 是 | 被退回的数据 id |
| data.objectPoolId | String | 是 | 线索池 id 或客户公海 id |
| data.backReason | String | 是 | 退回原因：`0`、`1`、`2`、`other` |
| data.backReason__o | String | 否 | backReason 为 `other` 时的文字说明，不传则原因为空 |

- ⚠ 文档未说明：`backReason` 的 0 / 1 / 2 各代表什么；公海 / 线索池 id 从哪查（`HighSeasObj` 可按 data/query 查，线索池对象 apiName 文档未给出）。

### 7.3 从公海移除

**Endpoint**: `POST /cgi/crm/v2/data/remove?thirdTraceId={uuid4}`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data.apiName | String | 是 | `AccountObj`、`LeadsObj` |
| data.objectIDs | List | 是 | 要移除的数据 id（注意大写 `IDs`） |
| data.objectPoolId | String | 是 | 公海 id（可按公海对象条件查询获取） |
| data.isKeepOwner | Boolean | 是 | 是否保持原负责人 |
| data.owner | String | 否 | 移除后的负责人；`isKeepOwner=true` 时可不传 |

## 8. 相关团队

目前只支持 `AccountObj` 和 `OpportunityObj`。**注意这组接口的 `apiName` 在 body 顶层，其余参数在 `data` 里。**

| 动作 | Endpoint | body |
| --- | --- | --- |
| 新增成员 | `POST /cgi/crm/team/add` | `apiName` + `data.dataIDs`、`data.teamMemberEmployee`、`data.teamMemberRole`、`data.teamMemberPermissionType`、`data.ignoreSendingRemind` |
| 编辑 | `POST /cgi/crm/team/edit` | `apiName` + `data.dataID` + `data.teamMemberInfos[]` |
| 查询 | `POST /cgi/crm/team/get` | `apiName` + `data.dataID` |
| 删除成员 | `POST /cgi/crm/team/delete` | `apiName` + `data.dataIDs` + `data.teamMemberEmployee` |

枚举（均为字符串）：`teamMemberRole` 1 负责人 / 2 联合跟进人 / 3 售后服务人员 / 4 普通成员；`teamMemberPermissionType` 1 只读 / 2 读写。
`ignoreSendingRemind`：是否不发 CRM 消息提醒，默认 false（文档示例写成字符串 `"false"`，参数表是 Boolean）。

```json
{
  "apiName": "AccountObj",
  "data": {
    "dataIDs": ["289eb6014a344c3b8e62cafc94bd2fef"],
    "teamMemberEmployee": ["1000"],
    "teamMemberRole": "2",
    "teamMemberPermissionType": "2",
    "ignoreSendingRemind": true
  }
}
```

- 注意 `dataIDs`（add/delete，列表）和 `dataID`（edit/get，单个）的大小写与单复数。
- team/get 的返回结构 ⚠ 文档未说明（示例只有 errorCode）。

## 9. 锁定 / 解锁

| 动作 | Endpoint |
| --- | --- |
| 锁定 | `POST /cgi/crm/v2/object/lock` |
| 解锁 | `POST /cgi/crm/v2/object/unlock` |

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data.dataObjectApiName | String | 是 | 对象 apiName |
| data.dataIds | List | 是 | 数据 id 列表 |
| data.detailObjStrategy | Int | 是 | 0 只处理当前对象，1 级联处理关联的从对象，默认 1 |

- ⚠ 文档笔误：锁定接口的 `detailObjStrategy` 说明也写成「0表示只解锁…1表示级联解锁」，应理解为锁定。

## 10. 权限与业务限制

- 接口以 `x-fs-userid`（旧版 `currentOpenUserId`）对应员工的身份执行：没权限时报「无此操作的数据权限」或「没有XXXX权限」。CRM 管理员默认拥有除人员对象外所有数据的权限，集成账号通常用管理员。
- 查不到数据先排查：offset 当成页码了？该员工对这批数据没有可见权限？（到网页版用同一个人登录看列表对比）
- 公海 / 线索池里的数据要先领取才能改负责人（第 6、7 节）。
- 不要用 `errorMessage` 做逻辑判断（每个接口页都有这句），判 `errorCode`。

## 11. 本文件的 ⚠

- ⚠ 文档未说明：`optionInfo` 三个开关含义；`object_describe_api_name` 是否必填；修改时未传字段的处理；预置对象能否改锁定数据（第 2、4 节）。
- ⚠ 文档自相矛盾：`details` 是 map 还是列表（第 2 节）；invalid 的 `object_data_id` 是「列表」还是单个（第 5.1 节）。
- ⚠ 文档自相矛盾：changeOwner `ownerId` 字符串 `"[1000]"` 还是列表 `["1000"]`；`Data` 标为可选（第 6 节）。
- ⚠ 文档未说明：choose 的领取人；`backReason` 枚举含义；线索池对象 apiName；team/get 返回结构（第 7、8 节）。
- ⚠ 文档笔误：lock 的 detailObjStrategy 说明（第 9 节）。
- 页面错误：`AccountObj/query.html` 实为公海查询、`AccountObj/delete.html` 实为费用明细删除（第 5.2 节、`query-and-paging.md`）。
