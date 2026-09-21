# 字段类型与 Metadata API

目录：[字段类型全表](#字段类型全表) · [值得单独展开的字段类型](#值得单独展开的字段类型) · [Metadata API：读 base/table 结构](#metadata-api读-basetable-结构) · [Metadata API：创建/更新字段与表](#metadata-api创建更新字段与表)

## 字段类型全表

Airtable 目前支持 32 种字段类型（`Field-Type` 模型，来自内嵌 OpenAPI 规范枚举）。"可写"列标的是**记录 cell 值**能否通过 Create/Update records 接口写入（不是字段定义本身能不能创建，见下文）。

| `type` 值 | 中文名 | cell 值可写？ | 备注 |
|---|---|---|---|
| `singleLineText` | 单行文本 | ✅ | — |
| `multilineText` | 长文本 | ✅ | — |
| `richText` | 富文本 | ✅ | Markdown 风格标记语言 |
| `email` | 邮箱 | ✅ | — |
| `url` | 链接 | ✅ | — |
| `phoneNumber` | 电话 | ✅ | — |
| `number` | 数字 | ✅ | `options.precision` 0-8 |
| `percent` | 百分比 | ✅ | 底层存小数（12.3% 存成 `0.123`） |
| `currency` | 货币 | ✅ | `options.precision` 0-7、`options.symbol` |
| `checkbox` | 复选框 | ✅ | cell 值恒为 `true`（未勾选是空值，不是 `false`） |
| `singleSelect` | 单选 | ✅ | 选项不匹配需 `typecast`，见 write-records.md |
| `multipleSelects` | 多选 | ✅ | 同上；写入是整体覆盖，非合并 |
| `date` | 日期 | ✅ | ISO 8601，如 `"2022-09-05"` |
| `dateTime` | 日期+时间 | ✅ | ISO 8601 UTC，如 `"2022-09-05T07:00:00.000Z"` |
| `duration` | 时长 | ✅ | 底层是秒数的整数 |
| `rating` | 评分 | ✅ | 正整数，不能是 0 |
| `barcode` | 条码 | ✅（未标 read only） | `{type?, text}`；主要靠 iOS/Android App 扫码录入 |
| `multipleAttachments` | 附件 | ✅（特殊写入流程） | 见 write-records.md |
| `singleCollaborator` | 单协作者 | ✅ | 写入传 `{id}` 或 `{email}` |
| `multipleCollaborators` | 多协作者 | ✅ | 写入传 `array<string>`（用户/群组 ID） |
| `multipleRecordLinks` | 链接记录 | ✅ | 写入传 `array<string>`（目标 record ID），见 write-records.md 第 6 条 |
| `externalSyncSource` | 同步来源 | ⚠ 文档未明确标注只读 | 只出现在被同步（synced）的表上，是否可写未实测确认 |
| `formula` | 公式 | ❌ 只读 | — |
| `rollup` | 汇总 | ❌ 只读 | — |
| `multipleLookupValues`（lookup） | 查找 | ❌ 只读 | — |
| `count` | 计数 | ❌ 只读 | 链接记录数量 |
| `autoNumber` | 自增编号 | ❌ 只读 | — |
| `createdTime` | 创建时间 | ❌ 只读 | — |
| `createdBy` | 创建者 | ❌ 只读 | — |
| `lastModifiedTime` | 最后修改时间 | ❌ 只读 | — |
| `lastModifiedBy` | 最后修改者 | ❌ 只读 | — |
| `button` | 按钮 | ❌ 只读 | 只能读 `label`/`url` |
| `aiText` | AI 文本 | ❌ 只读 | 可能处于 `loading`/`error` 状态 |

**⚠ 官方明确警告未来可能新增字段类型，且不算破坏性变更**——生产代码遇到未知 `type` 要优雅降级（比如原样透传或跳过），不要 `assert type in <上面这个列表>` 式地硬失败。

## 值得单独展开的字段类型

### 单选 / 多选（select）

写入传字符串（`singleSelect`）或字符串数组（`multipleSelects`），值必须精确匹配已存在选项的 `name`，大小写、空格都算数；不匹配报 `INVALID_MULTIPLE_CHOICE_OPTIONS`，除非 `typecast: true`（此时自动新建选项）。Schema 里能读到每个选项的 `id`/`name`/`color`；创建/更新字段定义时可以用 `choices` 数组的 `id` 来精确指定"复用哪个已有选项"（不传 `id` 就是新建选项）。

### 链接记录（`multipleRecordLinks`）

- **写入**永远是目标 record 的 **ID 字符串数组**（`array<string>`），不是对象数组。
- **读取**默认也是 ID 字符串数组；只有传了 `includeDateDependencyMetadata=true` 才会变成 `[{id, dateDependencyMetadata?}]` 对象数组。
- Schema 里能读到 `linkedTableId`（链到哪张表）、`inverseLinkFieldId`（对方表里反向链接这边的字段，可能没有）、`prefersSingleRecordLink`（UI 提示"只想要单条链接"，但**不是强约束**——哪怕这个值是 `true`，API/复制粘贴依然可能写入多条）。
- 传入不存在的 record ID、或试图用目标表的显示文本（而不是 record ID）来"匹配/新建"链接记录：⚠ 当前抓取的文档没有说明这两种情况的确切行为，不要凭其它平台的"upsert 自动匹配"经验假设，已列入验证计划。

### 附件（`multipleAttachments`）

见 `write-records.md` 的"附件上传"章节——读写形状不对称（读回来的对象字段远多于写入需要的字段），且大文件上传走完全不同的域名。

### Collaborator 类字段（`singleCollaborator`/`multipleCollaborators`/`createdBy`/`lastModifiedBy`）

读取都返回 `{id, email?, name?, permissionLevel?, profilePicUrl?}` 形状（后两个字段官方说"只在 webhooks 响应里才会带"，普通 REST 读取大概率拿不到）。可写的 `singleCollaborator`/`multipleCollaborators` 写入时只需要 `{id}` 或 `{email}`（单协作者）/ `array<string>` ID（多协作者），不需要也不能传完整对象。

## Metadata API：读 base/table 结构

### List bases

**Endpoint**: `GET https://api.airtable.com/v0/meta/bases`
**用途**: 列出 token 能访问的全部 base，1000 条/页，用 `offset` 翻页（和记录分页同一套机制）。
**Scope**: `schema.bases:read`。

返回每个 base 的 `id`/`name`/`permissionLevel`（`"none" | "read" | "comment" | "edit" | "create" | "interfaceOnly"`）——**Agent 写"批量操作多个 base"的代码前，应该先用这个接口枚举 token 实际能碰到哪些 base 以及各自的权限级别**，而不是假设 token 对所有已知 baseId 都有权限。

### Get base schema

**Endpoint**: `GET https://api.airtable.com/v0/meta/bases/{baseId}/tables`
**用途**: 返回该 base 下所有 table 的完整结构：每个 table 的 `id`/`name`/`description`/`primaryFieldId`，每个字段的 `id`/`name`/`type`/`options`/`description`，每个 view 的 `id`/`name`/`type`。
**Scope**: `schema.bases:read`。
**查询参数**: `include=visibleFieldIds`（可选）——附带每个 grid view 当前可见（未隐藏）的字段 ID 列表。

```bash
curl "https://api.airtable.com/v0/meta/bases/{baseId}/tables" -H "Authorization: Bearer $AIRTABLE_TOKEN"
```

**这是本 skill 里"写通用/动态代码"最关键的一个 endpoint**：

- 判断一个字段是否可写（排除 formula/rollup/lookup/count/…，见上表）。
- 拿到精确的字段 ID/表 ID，用 ID 而不是名字去拼后续的读写请求（名字可能被人改掉）。
- 拿到 `singleSelect`/`multipleSelects` 的合法选项列表，写入前本地校验，避免依赖 `typecast` 的"自动建选项"副作用（typecast 建的新选项通常没有明确的颜色/顺序，容易造成脏数据）。
- 拿到 `multipleRecordLinks` 字段的 `linkedTableId`，校验要写入的 record ID 是不是真的属于这张目标表。

## Metadata API：创建/更新字段与表

**Scope**: `schema.bases:write`，用户角色需要是 Base creator（比记录读写要求的 Base editor 更高）。

- **Create field**: `POST /v0/meta/bases/{baseId}/tables/{tableId}/fields`，body 是 `{name, type, description?, options?}`（`options` 的形状随 `type` 变化，和 `field-model` 里"Field type and options (write)"章节一一对应）。**连 `formula`/`rollup`/`count` 等只读类型的字段定义本身也能通过这个接口创建**（比如新建一个 formula 字段并指定 `options.formula`）——只读指的是"记录写接口不能设置这个字段的值"，不是"这个字段类型完全不能被 API 操作"，两件事不要混淆。
- **Update field**: `PATCH /v0/meta/bases/{baseId}/tables/{tableId}/fields/{fieldId}`，可改名字、description、部分 `options`（比如给 select 字段增删选项）。
- **Create table** / **Update table**: 建表、改表名/description/日期依赖设置。
- **Create base**: 一次性用一组 table 定义建一整个新 base。

这几个 endpoint 参数表较长（`create-field` 单是 request body 就有 30+ 个按 `type` 区分的 variant），本 skill 只标出关键判断，具体每种字段类型的 `options` 精确形状直接对照官方 `field-model`/`create-field` 页面（和上面"字段类型全表"是同一套结构，写入 options 形状基本对称，除了只读类型没有"写"形态）。
