# 创建/读取/更新 CRM 对象：contacts / companies / deals / 自定义对象

目录：[统一的对象模型](#统一的对象模型) · [创建记录](#创建记录) · [读取记录](#读取记录) · [更新记录](#更新记录) · [Upsert](#upsert-创建或更新) · [合并 / 删除](#合并--删除) · [属性 API](#属性-api) · [自定义对象与 Schemas API](#自定义对象与-schemas-api)

全部内容 ⚠ 文档原文，未实测（整理自 `docs/api-reference/latest/crm/using-object-apis`、`crm/objects/{contacts,companies,deals,custom-objects}/guide`、`crm/properties/guide`、`crm/objects/schemas/guide`、`crm/understanding-the-crm`，抓取于 2026-09-21）。

## 统一的对象模型

HubSpot 的所有 CRM 对象——无论是内置的 contacts/companies/deals，还是账号自己定义的 custom object——共用同一套端点形状：

```
POST    /crm/objects/{version}/{objectType}                 创建一条记录
GET     /crm/objects/{version}/{objectType}/{recordId}       读取一条记录
GET     /crm/objects/{version}/{objectType}                  分页列出所有记录
PATCH   /crm/objects/{version}/{objectType}/{recordId}       局部更新
DELETE  /crm/objects/{version}/{objectType}/{recordId}       归档（移入回收站，非永久删除）
POST    /crm/objects/{version}/{objectType}/merge            合并两条同类型记录
POST    /crm/objects/{version}/{objectType}/search            搜索（见 references/search.md）
POST    /crm/objects/{version}/{objectType}/batch/{action}    批量操作（见 references/batch.md）
```

- `{version}`：本 skill 示例统一用 `v3`（见 SKILL.md 通用规则第 8 条），2026-09 起也可以用 `2026-09`，两者当前描述为等价。
- `{objectType}`：标准对象可以用复数小写名字（`contacts`、`companies`、`deals`、`tickets`……），也可以用数字 `objectTypeId`（`0-1`=contacts、`0-2`=companies、`0-3`=deals、`0-5`=tickets，完整表见下方"对象类型 ID"）；自定义对象**只有** `objectTypeId`（格式 `2-XXXXXXX`）或 `p{HubID}_{object_name}` 这个 fully-qualified-name 可用，没有内置的英文单数名。
- `{recordId}`：默认是 HubSpot 生成的内部 `hs_object_id`（字符串数字），也可以用自定义唯一标识属性 + `?idProperty=<propName>` query 参数定位记录（比如用邮箱定位联系人：`PATCH /crm/objects/v3/contacts/user@example.com?idProperty=email`）。

### 对象类型 ID（常用对象）

| 对象 | objectTypeId | 创建记录必需属性 |
|---|---|---|
| Contacts | `0-1` | 无强制要求，但建议至少给 `email`/`firstname`/`lastname` 之一 |
| Companies | `0-2` | 至少给 `domain`（推荐，唯一标识/去重依据）或 `name` 之一 |
| Deals | `0-3` | `dealname`、`dealstage`，多 pipeline 账号还要给 `pipeline`（不传则用默认 pipeline） |
| Tickets | `0-5` | `subject`、`hs_pipeline_stage`、`hs_pipeline` |
| Custom objects | `2-XXXXXXX`（每个账号各自不同，创建 schema 时分配） | 该 schema 的 `requiredProperties` 里指定的属性 |

`Custom objects` 的 objectTypeId 拿不到时，调 `GET /crm-object-schemas/v3/schemas` 查全部自定义对象的 schema（含 objectTypeId）。⚠ 文档原文，未实测：`crm-object-schemas` 是一个和 `crm/objects`、`crm/properties` 平级但路径前缀完全不同的独立路径（不是 `crm/objects/v3/schemas`），容易凭"都是 CRM 相关端点"的直觉拼错成 `crm/objects/...`。

## 创建记录

请求体最外层是 `properties`（必需的 key-value 对象）+ 可选的 `associations` 数组：

```json
{
  "properties": {
    "email": "jane@example.com",
    "firstname": "Jane",
    "lastname": "Doe",
    "company": "HubSpot",
    "website": "hubspot.com"
  }
}
```

```bash
curl -s -X POST "https://api.hubapi.com/crm/v3/objects/contacts" \
  -H "Authorization: Bearer $HUBSPOT_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"properties": {"email": "jane@example.com", "firstname": "Jane", "lastname": "Doe"}}'
```

**⚠ 上面例子里的 `company: "HubSpot"` 是纯文本属性，不是关联！** 这是官方文档自己给出的示例（"Using Object APIs"页），刻意保留在这里是因为它本身就是 SKILL.md 第 2 条通用规则说的那个陷阱的活证据——联系人对象确实有一个叫 `company` 的历史遗留文本属性，写进去只是存了一个字符串，不会让这条联系人出现在任何公司记录的"关联联系人"列表里，也查不到 `associations.company`。想要真实关联，必须走 `associations` 数组或 `references/associations.md` 里的专门端点。

**⚠ 文档自相矛盾**：所有 endpoint 页面内嵌的 OpenAPI 片段里，`SimplePublicObjectInputForCreate`（单条创建）和 `SimplePublicObjectBatchInputForCreate`（批量创建）两个 schema 都把 `associations` 列为 `required` 字段（和 `properties` 并列）；但站内**每一个**创建记录的代码示例——contacts、companies、deals、custom objects，单条和批量——只要没有要关联的记录，都是直接省略 `associations` 字段，不传空数组也不传 `null`。规范和示例代码明显不一致，未实测哪个是权威行为（省略是否真的报错要求必填），保守起见照抄文档示例省略即可，若报错再按规范补一个空数组 `"associations": []` 试试。

响应（`SimplePublicObject`）：

```json
{
  "id": "512",
  "properties": { "...": "..." },
  "createdAt": "2026-09-01T12:00:00.000Z",
  "updatedAt": "2026-09-01T12:00:00.000Z",
  "archived": false
}
```

## 读取记录

- 单条：`GET /crm/objects/v3/{objectType}/{recordId}`，可选 query 参数 `properties`（逗号分隔要返回的属性）、`propertiesWithHistory`（同时返回历史值）、`associations`（逗号分隔要一并返回的关联对象类型）、`idProperty`（用自定义唯一属性代替 `hs_object_id` 定位）。
- 列表：`GET /crm/objects/v3/{objectType}`，同样支持 `properties`/`associations`；分页参数是 `limit`（默认 10，单页最大 100，⚠ 文档原文未标注单条 GET-list 端点的确切上限数字，与批量端点的 100 是否共用同一上限未验证）+ `after`（游标，取自上一页响应 `paging.next.after`）。
- **不指定 `properties` 时只返回该对象的默认属性子集**，不是全部属性；想要某个自定义属性出现在响应里必须显式加进 `properties` 参数。
- **批量读**（`POST .../batch/read`）**不支持 `associations` 参数**——批量端点这条路走不通，要批量拿多条记录的关联得用 `references/associations.md` 里专门的关联批量读端点。

## 更新记录

`PATCH /crm/objects/v3/{objectType}/{recordId}`，请求体只需要包含要改的字段：

```json
{ "properties": { "jobtitle": "Manager", "lifecyclestage": "customer" } }
```

- **把某个属性清空**：把值设为空字符串 `""`，不是 `null`、不是省略这个 key。
- **多选 checkbox 属性追加值而不覆盖**：在原有值前加分号，新值间也用分号分隔，例如已有 `DECISION_MAKER`，追加两个值写成 `";BUDGET_HOLDER;END_USER"`（注意开头的分号，没有它会变成整体覆盖）。
- **日期/日期时间属性**：接受 ISO 8601 字符串或毫秒级 UNIX 时间戳；`date` 类型（只存日期）如果用时间戳必须是 UTC 零点，`datetime` 类型两种格式都行、显示时按查看者本地时区转换。
- **指派记录 owner**：值必须是 owner 的数字 `id`（来自 owners API 或属性设置页），不是 owner 的姓名或邮箱字符串。

**⚠ 2026-09 起的新变化（未实测，见 SKILL.md 通用规则第 7 条）**：文档在 `properties/guide` 和 `using-object-apis` 两页都插入了同一段警告——从 2026-09 API 版本 GA（2026-09-08）起，HubSpot 会对所有 CRM API 写路径强制执行**管理员在账号设置里配置的校验规则**（property validation rules）。这意味着一个之前能跑通的 `PATCH`/`POST` 写请求，可能因为账号管理员后来加了新的校验规则而开始报错，跟你的代码本身有没有 bug 无关。写代码前建议先用 `GET /crm/property-validations/v3/...`（property validation API）或账号设置页确认目标属性有没有配置校验规则。

## Upsert（创建或更新）

批量端点 `POST /crm/objects/v3/{objectType}/batch/upsert`：按 `idProperty` 指定的唯一标识属性判断记录是否已存在，存在则更新、不存在则创建。请求体每个 input 都要带 `id`（该唯一属性的值）+ `idProperty`（属性名）：

```json
{
  "inputs": [
    { "id": "jane@example.com", "idProperty": "email", "properties": { "phone": "5555555555" } }
  ]
}
```

⚠ 官方文档专门提示一条反直觉细节：**用 `email` 作为 contacts 的 `idProperty` 时不支持"部分 upsert"**——如果目标记录已存在，用 email 做 upsert 只能整体覆盖指定的属性，不能像自定义唯一属性那样做局部合并（原文只给出这个警告，没有展开说明"整体覆盖"具体行为差异是什么，⚠ 文档未说明清楚，需要真实调用对比验证）。想要稳定的局部更新语义，改用自定义唯一标识属性（见下方"创建自定义唯一属性"）而不是内置的 `email`。

## 合并 / 删除

- **合并**：`POST /crm/objects/v3/{objectType}/merge`，请求体 `{"primaryObjectId": "<保留的记录ID>", "objectIdToMerge": "<被合并掉的记录ID>"}`。合并后活动记录、关联、大部分属性值会被保留合并进主记录。⚠ 文档原文：如果账号开通了 "Primary ID Preservation for Merged Records" 公测功能，合并后 ID 会保留 `primaryObjectId` 而不是像默认行为那样生成一个新 ID，两种行为二选一取决于账号是否开通该公测，未实测默认是哪种。
- **删除**：`DELETE /crm/objects/v3/{objectType}/{recordId}`，只是移入回收站（90 天内可在 HubSpot UI 里恢复），不是永久删除，API 层面没有"彻底清除"的操作。

## 属性 API

`GET/POST/PATCH/DELETE /crm/properties/v3/{objectType}[/{propertyName}]`。

### 内部名（`name`）vs 显示标签（`label`）

创建属性时两个字段都必填、含义完全不同：

```json
{
  "groupName": "contactinformation",
  "name": "favorite_food",
  "label": "Favorite Food",
  "type": "string",
  "fieldType": "text"
}
```

- `name`：内部名，读写记录属性值时**只用这个**（`properties.favorite_food`），创建后不可改。
- `label`：HubSpot UI 上展示给人看的标签，和 `name` 没有强制的拼写对应关系（管理员完全可以把内部名 `favorite_food` 的属性在 UI 上改标签显示成"Fave Snack"）。

**这是本 skill 明确标注的最高优先级陷阱之一**：一个开发者照着 HubSpot UI 截图里的字段标签直接拼 API 属性名（比如把 UI 上的 *Deal Amount* 猜成 `dealAmount` 或 `deal_amount`），大概率是错的——真实内部名是 `amount`。同理 `dealstage`/`lifecyclestage`/自定义下拉选项的**取值**也是内部值，不是 UI 文字（默认生命周期阶段是 `subscriber`/`marketingqualifiedlead` 这类固定英文 token；自定义阶段的内部值是纯数字字符串）。**唯一可靠的做法是调 `GET /crm/properties/v3/{objectType}` 拿到该对象全部属性的真实 `name` 列表**，不要靠猜、不要照抄 UI 文案。

### type / fieldType

`type` 决定数据类型（`string`/`number`/`bool`/`enumeration`/`date`/`datetime`），`fieldType` 决定在表单/UI 里怎么展示（`text`/`textarea`/`number`/`select`/`checkbox`/`radio`/`date`/`html`/`phonenumber`/`file`/`calculation_equation`）。`enumeration` 类型的选项值分号分隔，`fieldType` 常配 `select`/`radio`/`checkbox`（多选）。

### 创建唯一标识属性

`hasUniqueValue: true`，最多 10 个/对象。创建后可以用它代替 `hs_object_id` 定位记录（`?idProperty=<name>`）。⚠ 注意：克隆记录时唯一属性值**不会**被复制到新记录（避免冲突），需要克隆后另外设置。

### 检索敏感属性

默认 `GET /crm/properties/v3/{objectType}` 只返回非敏感属性，要拿到 Enterprise 敏感数据属性需要显式加 `?dataSensitivity=sensitive`（配合有 `.sensitive`/`.highly_sensitive` scope 的 token，见 `references/auth.md`）。

## 自定义对象与 Schemas API

自定义对象分两层：**Schema**（定义对象本身：名字、属性、能关联哪些对象——用 `crm-object-schemas` 路径管理）+ **记录**（该 schema 下的具体数据行——用标准的 `crm/objects/{v}/{objectTypeId}` 路径管理，和内置对象完全一样的增删改查/批量/搜索形状）。

**⚠ 路径陷阱**：Schemas API 的路径前缀是 `/crm-object-schemas/v3/schemas`，**不是** `/crm/objects/v3/schemas`、也不是 `/crm/schemas/v3`——三种看起来都"合理"的拼法里只有第一种是对的，容易凭对其他端点路径规律的直觉猜错。

### 创建 schema

`POST /crm-object-schemas/v3/schemas`：

```json
{
  "name": "cars",
  "labels": { "singular": "Car", "plural": "Cars" },
  "primaryDisplayProperty": "model",
  "secondaryDisplayProperties": ["make"],
  "searchableProperties": ["year", "make", "VIN", "model"],
  "requiredProperties": ["year", "make", "VIN", "model"],
  "properties": [
    { "name": "make", "label": "Make", "type": "string", "fieldType": "text" },
    { "name": "VIN", "label": "VIN", "type": "string", "hasUniqueValue": true, "fieldType": "text" }
  ],
  "associatedObjects": ["0-1", "0-2"]
}
```

- `name`：对象内部名，只能含字母/数字/下划线，首字符必须是字母，**创建后不可改**。
- `associatedObjects`：列出这个自定义对象可以和哪些其他对象类型关联（用 objectTypeId），**必须先在这里声明，之后才能对这两类对象之间调用 associations API**——不声明直接尝试关联会失败。自定义对象默认已经能和活动类记录（emails/meetings/notes/tasks/calls/conversations）关联，不需要额外声明。
- 响应会带回分配的 `objectTypeId`（`2-XXXXXXX`），**务必记下来**，后续读写这个自定义对象的记录/属性都要用它。

### 查 / 改 / 删 schema

- `GET /crm-object-schemas/v3/schemas` 列出全部自定义对象 schema（含各自的 `objectTypeId`）。
- `GET /crm-object-schemas/v3/schemas/{objectTypeId 或 fullyQualifiedName}` 查单个（`fullyQualifiedName` 格式是 `p{HubID}_{object_name}`）。
- `PATCH /crm-object-schemas/v3/schemas/{objectTypeId}` 改 schema 级配置（如 `secondaryDisplayProperties`）；**给新属性加进 `requiredProperties`/`searchableProperties`/display properties 之前，属性本身必须先用属性 API 单独创建好**，不能在 PATCH schema 的同一次请求里顺带新建属性。
- `DELETE /crm-object-schemas/v3/schemas/{objectType}` 删除 schema，**前提是该对象下所有记录、关联、属性都已经先删干净**；要用同名重新建一个新 schema，需要加 `?archived=true` 做硬删除，否则名字会被占用。

### 自定义对象记录的增删改查

和标准对象完全一致的端点形状，只是 `{objectType}` 换成分配到的 `objectTypeId`：

```bash
curl -s -X POST "https://api.hubapi.com/crm/objects/v3/2-3465404" \
  -H "Authorization: Bearer $HUBSPOT_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"properties": {"VIN": "1FT8W3A68HEC69514", "year": "2026", "make": "BMW", "model": "X1"}}'
```

批量端点上限同样是 **100 条/请求**（见 `references/batch.md`）。和标准对象唯一的区别是：自定义对象与其他对象之间的关联类型（`associationTypeId`）需要通过 schema 声明后自己去 `GET /crm/associations/v3/{fromObjectType}/{toObjectType}/labels` 查出来，不像标准对象之间有一份公开的默认类型 ID 表（见 `references/associations.md`）。
