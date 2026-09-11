# 对象、字段描述、字段值格式与文件上传

> 来源：https://developer.fxiaoke.com/openapi_v2/ 的「查询对象列表」「查询对象描述」「参数填写说明」「字段值说明」「文件上传」页
> （抓取于 2026-09-11），旧版 wiki「CRM对象接口调用说明」（artiId=1146）。**本文件全部为文档原文，未实测。**
> 请求头、thirdTraceId、`FxkClient` 见 `auth.md`。

## 目录
1. 对象 apiName：预置对象 vs 自定义对象
2. 查询企业有哪些对象：`/cgi/crm/v2/object/list`
3. 查询对象字段描述：`/cgi/crm/v2/object/describe`
4. 创建 / 修改时字段值怎么填（按字段 type）
5. 读数据时看到的特殊后缀字段
6. 附件 / 图片字段：先上传文件拿 npath
7. 本文件的 ⚠

---

## 1. 对象 apiName：预置对象 vs 自定义对象

纷享 CRM 的一切业务数据都是「对象」，每个对象有一个 apiName，字段也各有 apiName。

| 类型 | apiName 形态 | 读写接口前缀 | 例子 |
| --- | --- | --- | --- |
| 预置对象（系统自带，`defineType: package`） | `XxxObj` | `/cgi/crm/v2/data/*` | `AccountObj`、`ContactObj`、`LeadsObj` |
| 自定义对象 | **以 `__c` 结尾** | `/cgi/crm/custom/v2/data/*` | `object_Nyeoj__c`、`object_d4fIq__c` |

文档里出现过的常用预置对象 apiName（以企业实际启用为准，用第 2 节接口核对）：

| 业务名 | apiName | 业务名 | apiName |
| --- | --- | --- | --- |
| 客户 | `AccountObj` | 联系人 | `ContactObj` |
| 销售线索 | `LeadsObj` | 商机 | `OpportunityObj` |
| 商机2.0 | `NewOpportunityObj` | 商机2.0明细 | `NewOpportunityLinesObj` |
| 商机联系人 | `NewOpportunityContactsObj` | 公海 | `HighSeasObj` |
| 客户地址 | `AccountAddrObj` | 合作伙伴 | `PartnerObj` |
| 竞争对手 | `CompetitorObj` | 市场活动 | `MarketingEventObj` |
| 活动成员 | `CampaignMembersObj` | 行为记录 | `BehaviorRecordObj` |
| 部门 | `DepartmentObj` | 人员 | `PersonnelObj` |
| 产品 | `ProductObj` | 费用明细 | `FeeDetailObj` |

- 「商机」和「商机2.0」是两个不同对象（`OpportunityObj` / `NewOpportunityObj`），文档各有一套页面。企业用的是哪个，⚠ 文档未说明如何判断——调 `object/list` 看 `isActive`，或问 CRM 管理员。
- 字段 apiName 也分预置字段和自定义字段；自定义字段名同样以 `__c` 结尾（⚠ 文档未明说，只在对象层面说明了 `__c` 规则，字段层面以 describe 返回为准）。
- 文档站按业务分组列了 40 多类预置对象（工单、库存、财务、订单……），读写方式与本 skill 覆盖的客户 / 线索 / 商机完全相同，只换 `dataObjectApiName`。

## 2. 查询企业有哪些对象

**Endpoint**: `POST /cgi/crm/v2/object/list?thirdTraceId={uuid4}`
**用途**: 列出企业可用的全部对象（预置 + 自定义），拿到准确的 `describeApiName`。对接前先调一次，别凭名字猜 apiName。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| includeNull | Boolean | 否 | false | 是否返回值为 null 的字段 |

**示例请求**

```bash
curl -sS -X POST "https://$FXK_HOST/cgi/crm/v2/object/list?thirdTraceId=$(uuidgen | tr A-Z a-z)" \
  -H "authorization: Bearer $FXK_TOKEN" -H "x-fs-ea: $FXK_EA" -H "x-fs-userid: $FXK_USER_ID" \
  -H 'Content-Type: application/json' -d '{"includeNull": false}'
```

```python
objs = fxk.post("/cgi/crm/v2/object/list", {"includeNull": False})["data"]["objects"]
custom = [o["describeApiName"] for o in objs if o["describeApiName"].endswith("__c")]
```

**示例响应**（节选）

```json
{
  "traceId": "E-O.cdklrj.2121-20251124113618-b6a1cb",
  "errorDescription": "success",
  "data": {
    "objects": [
      {"describeApiName": "AccountObj", "describeDisplayName": "客户", "defineType": "package",
       "isActive": true, "iconPath": "", "iconIndex": 0, "hideButton": false, "publicObject": false},
      {"describeApiName": "LeadsObj", "describeDisplayName": "销售线索", "defineType": "package",
       "isActive": true, "hideButton": false, "publicObject": false}
    ]
  }
}
```

**注意事项**
- 文档请求示例是 `{"includeNull": true,}`（带尾逗号，不是合法 JSON）——照抄会被 JSON 库拒绝，去掉逗号。
- 自定义对象的 `defineType` 值 ⚠ 文档未说明（示例里只有 `package`）；用 apiName 是否以 `__c` 结尾判断更可靠。

## 3. 查询对象字段描述

**Endpoint**: `POST /cgi/crm/v2/object/describe?thirdTraceId={uuid4}`
**用途**: 拿一个对象的全部字段：字段 apiName、`type`、是否必填、单选 / 多选的 options、小数位数等。**写创建 / 修改代码前必调**。
管理员也可以在管理后台的对象管理里看字段列表。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| includeNull | Boolean | 否 | false | 是否返回 null 字段 |
| data.apiName | String | 是 | — | 对象 apiName（预置、自定义都用这个接口） |
| includeDetail | Boolean | 是 | — | 是否包括从对象 |

**示例请求**

```json
{
  "includeNull": true,
  "includeDetail": true,
  "data": { "apiName": "AccountObj" }
}
```

```python
desc = fxk.post("/cgi/crm/v2/object/describe",
                {"includeDetail": False, "data": {"apiName": "AccountObj"}})["data"]["describe"]
for api_name, f in desc["fields"].items():
    print(api_name, f["type"], f.get("is_required"), f.get("label"))
```

**示例响应**（节选，文档用 ProductObj 举例）

```json
{
  "data": {
    "describe": {
      "api_name": "ProductObj",
      "fields": {
        "price": {
          "api_name": "price", "label": "标准价格", "type": "currency",
          "decimal_places": 2, "is_required": true, "default_value": "0",
          "currency_unit": "￥", "define_type": "package", "is_active": true
        },
        "off_shelves_time": {
          "api_name": "off_shelves_time", "label": "下架时间", "type": "date_time",
          "date_format": "yyyy-MM-dd HH:mm", "time_zone": "GMT+8", "is_required": false
        }
      }
    }
  }
}
```

读取路径：`data.describe.fields.<字段apiName>.type`。单选 / 多选字段的选项在 `options: [{"label": "辆", "value": "18"}, …]`。

**注意事项**
- ⚠ 文档自相矛盾：参数表把 `includeDetail` 列在 `data` 下面一行（像是 data 的子字段），请求示例却把它放在 JSON 顶层。首次调用按示例放顶层，拿不到从对象再试放进 `data`。
- 字段是否必填看 `is_required`；创建时必填字段必须填，格式必须按 `type`（旧版 wiki 1146）。

## 4. 创建 / 修改时字段值怎么填（按字段 type）

先从 describe 拿到字段 `type`，再按下表填（「字段值说明」页 + 旧版 wiki 1146）。**最容易写错的是：数字 / 金额是字符串、日期是毫秒 Long、单选传 value 不传 label。**

| type | 含义 | JSON 类型 | 示例 | 备注 |
| --- | --- | --- | --- | --- |
| text | 文本 | String | `"hello world"` | |
| long_text | 多行文本 | String | `"hello world"` | |
| html_rich_text | 富文本 | String | `"hello world"` | |
| select_one | 单选 | String | `"18"` | 传 describe 里 `options[].value`，**不是 label** |
| select_many | 多选 | List[String] | `["18","19"]` | 同上 |
| number | 数字 | **String** | `"100.01"` | 小数位数见 describe |
| currency | 金额 | **String** | `"100.01"` | 小数位数见 describe；不是「分」 |
| date | 日期 | Long | `1619712000000` | 毫秒时间戳，时分秒会被忽略 |
| time | 时间 | Long | `9000000` | 毫秒 |
| date_time | 日期时间 | Long | `1619422813071` | 毫秒时间戳 |
| phone_number | 手机号 | String | `"1527XXX7499"` | |
| email | 邮箱 | String | `"528XXXXXX7@fxiaoke.com"` | |
| url | 网址 | String | `"http://www.fxiaoke.com"` | |
| true_or_false | 布尔 | **Boolean** | `true` | 不是字符串 `"true"` |
| percentile | 百分数 | String | `"95.0"` | 不是 `"95.0%"` |
| department / department_many | 部门 / 部门多选 | List[String] | `["1000","1001"]` | 单选部门也是列表 |
| employee / employee_many | 员工 / 人员多选 | List[String] | 新版 `["1000"]`；旧版 `["FSUID_xx1"]` | 单选员工也是列表；见下方 ⚠ |
| master_detail | 主从关系 | String | `"603dabc14ae65400011aec90"` | 主对象数据的 `_id` |
| object_reference | 查找关联 | String | `"603dabc14ae65400011aec90"` | 被关联数据的 `_id` |
| object_reference_many | 查找关联多选 | List[String] | `["603dab…"]` | |
| file_attachment | 附件 | List[Map] | `[{"name":"aaa.jpg","path":"<npath 或 mediaId>"}]` | 见第 6 节 |
| image | 图片 | List[Map] | `[{"ext":"png","isImage":true,"filename":"weixin","path":"…","size":51200.0}]` | size 单位 byte |
| signature | 签名 | — | — | 同图片字段 |
| tag / array | 标签 / 数组 | List[String] | | |
| auto_number | 自增编号 | String | | 系统生成 |
| formula / count / quote | 计算 / 统计 / 引用 | — | — | 自动计算或随引用字段，不用写 |
| group（地区定位） | 地区定位组件 | Map | 见下 | |

地区定位字段：

```json
{
  "location": "1#%$2#%$湖北省武汉市",
  "country": "248", "province": "265", "city": "451", "district": "2155",
  "address": "湖北省武汉市"
}
```
`location` 格式为 `{经度}#%${纬度}#%${地址}`；country / province / city / district 编号从「获取国家省市地区选项代码」接口取（district 必须从该接口取）；各项都非必填。

- ⚠ 文档自相矛盾：新版「字段值说明」员工字段示例是 `["1000","1000"]`（CRM 员工 ID），旧版 wiki 是 `["FSUID_xx1"]`（openUserId）。
  结合公共参数 `convertUserId`：新版 header 传参默认填员工 ID；传了 `"convertUserId": true` 或走旧版传参时填 `FSUID_…`。
- ⚠ 文档自相矛盾：新版 location 格式写成 `{经度}#%${纬度}#%$`（少了地址段），旧版是 `{经度}#%${纬度}#%${地址}`；示例值 `1#%$2#%$湖北省武汉市` 符合旧版写法。
- 负责人（owner）不能用「修改」接口改，必须走 `changeOwner`（旧版 wiki 1146 注意事项）——见 `crm-preset-objects.md`。

## 5. 读数据时看到的特殊后缀字段

查询 / 详情返回里会出现带后缀的派生字段（「查询对象描述」页的字段说明）：

| 后缀 | 出现在哪类字段后 | 含义 |
| --- | --- | --- |
| `__r` | 国家 / 省 / 市 / 区 / 镇 | 存储 label 值 |
| `__r` | object_reference / object_reference_many | 被关联数据的名称信息 |
| `__r` | employee / out_employee、department、relevant_team、master_detail | 人员 / 部门 / 团队信息 |
| `__l` | department_many、employee_many | 部门 / 人员信息（列表） |
| `__o` | select_one / select_many | 选了「其他」时填写的内容 |
| `__o` | 富文本 | 纯文本化后的内容 |
| `__v` | quote（引用） | 选项的 value 值 |
| `__p` | phone_number | 手机归属地 |
| `__relation_ids` | object_reference、master_detail | 关联 id |
| `__e` | 富文本 | 未经处理的富文本 |

这些是**只读派生字段**。写入时用原字段名（`owner`、`parent_id`），不要写 `owner__r`。
例外：自定义对象创建接口的 `needConvertLookup: true` 时，查找关联字段要加 `__r` 后缀（见 `custom-objects.md`）。

另外：查询接口默认 `includeNull=false`，**值为空的字段不会出现在返回里**，解析时用 `.get()`，不要假设字段一定存在。

## 6. 附件 / 图片字段：先上传文件拿 npath

新版传参默认文件参数用 **npath**（不再用 mediaId；要用 mediaId 需在 body 顶层传 `"convertMediaId": true`）。上传分两步。

### 6.1 生成上传凭证

**Endpoint**: `POST /cgi/crm/v2/generatorFileUploadCredential?thirdTraceId={uuid4}`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data.expireTime | integer | 是 | 凭证有效期（秒），60–604800 |
| data.resourceType | string | 是 | `N` 企业正式文件（长期）；`TN` 临时文件（3 天过期，存进业务数据时自动转正） |
| data.isStreamUpload | boolean | 是 | true 流式上传 / false 表单上传 |
| data.filename | string | 是 | 带扩展名的完整文件名（会自动 URL 编码） |
| data.extension | string | 是 | 扩展名，不带点；与文件名不一致时以它为准 |
| data.fileSize | integer | 是 | 字节数，1–104857600（100 MB） |

响应 `data`：`method`、`url`、`acid`、`resource`、`ak`、`sign`、`expiry`、`filename`、`size`、`digest`、`contentType`，以及顶层 `traceId`。

### 6.2 上传文件

`POST {data.url}?traceId={随机串}&linkId={第 1 步响应的 traceId}`

- header：第 1 步返回的 `acid`、`resource`、`ak`、`sign`、`expiry`、`filename`、`size`、`digest` 原样作为 header；`contentType` 的 header 名是 `Content-Type`。
- 表单上传：`multipart/form-data`，表单项名必须是 `facishareFile`，一次只收一个文件。
- 流式上传（文档推荐）：`Content-Type: application/octet-stream`，body 是文件二进制。
- 成功：`{"success": true, "code": 200, "message": "success", "data": "TN_7c1fabc747264f4a9e0ae7301430df18"}`，`data` 就是 npath。
- 失败示例：`{"success": false, "code": 400, "message": "签名已过期", "data": null}`。**这一步的响应格式和 OpenAPI 其他接口不同**（`success`/`code` 而不是 `errorCode`）。

```python
import os, uuid, requests

def upload_file(fxk, path: str, resource_type: str = "N") -> str:
    size = os.path.getsize(path)
    name = os.path.basename(path)
    cred = fxk.post("/cgi/crm/v2/generatorFileUploadCredential", {"data": {
        "expireTime": 600, "resourceType": resource_type, "isStreamUpload": True,
        "filename": name, "extension": name.rsplit(".", 1)[-1], "fileSize": size}})
    d = cred["data"]
    headers = {k: str(d[k]) for k in ("acid", "resource", "ak", "sign", "expiry", "filename", "size", "digest")}
    headers["Content-Type"] = "application/octet-stream"
    with open(path, "rb") as fh:
        r = requests.post(d["url"], params={"traceId": str(uuid.uuid4()), "linkId": cred["traceId"]},
                          headers=headers, data=fh, timeout=120)
    j = r.json()
    if not j.get("success"):
        raise RuntimeError(j)
    return j["data"]          # npath，填进附件 / 图片字段的 path

# npath = upload_file(fxk, "合同.pdf")
# object_data["attach__c"] = [{"name": "合同.pdf", "path": npath}]
```

**注意事项**（文档原文，未实测）
- 一个签名只能用一次；上传的文件大小、类型必须与生成签名时一致；header 参数不可修改。
- 上传 URL 路径末尾的 `/` 不能去掉（严格匹配）。
- 流式上传时签名里 `isStreamUpload` 要为 true（⚠ 文档没明说 isStreamUpload 与实际上传方式不一致时会怎样）。

## 7. 本文件的 ⚠

- ⚠ 文档未说明：如何判断企业用的是「商机」还是「商机2.0」（第 1 节）；自定义字段是否一律 `__c` 结尾（第 1 节）；自定义对象的 `defineType` 取值（第 2 节）。
- ⚠ 文档自相矛盾：describe 的 `includeDetail` 放顶层还是 `data` 里（第 3 节）。
- ⚠ 文档自相矛盾：员工字段填员工 ID 还是 FSUID（第 4 节）；地区定位 location 格式新旧版不同（第 4 节）。
- ⚠ 文档未说明：isStreamUpload 与实际上传方式不一致的后果（第 6 节）。
- 文档示例错误（非探测证实）：object/list 请求示例带尾逗号，不是合法 JSON（第 2 节）。
