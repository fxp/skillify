# 写记录：创建 / 更新 / 删除

目录：[Create records](#create-records) · [Update records（单条与批量、upsert）](#update-records单条与批量upsert) · [Delete records](#delete-records单条与批量) · [批量上限（重点）](#批量上限重点) · [typecast](#typecast) · [计算字段不可写（重点）](#计算字段不可写重点) · [附件上传](#附件上传)

所有写操作都要求 `data.records:write` scope，且创建 token 的用户对目标 base 至少是 Base editor 角色。

## Create records

**Endpoint**: `POST https://api.airtable.com/v0/{baseId}/{tableIdOrName}`
**用途**: 创建一条或多条记录。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `records` | array\<{fields}\> | 二选一 | 批量创建，每个元素是 `{"fields": {...}}` |
| `fields` | object | 二选一 | 单条创建时直接传这个顶层字段，不用套 `records` 数组 |
| `typecast` | boolean | 否，默认 `false` | 见下方专门章节 |
| `returnFieldsByFieldId` | boolean | 否，默认 `false` | 响应里 `fields` 的 key 用字段 ID 还是字段名 |

**示例请求（批量）**

```bash
curl -X POST "https://api.airtable.com/v0/{baseId}/{tableIdOrName}" \
  -H "Authorization: Bearer $AIRTABLE_TOKEN" -H "Content-Type: application/json" \
  -d '{"records": [{"fields": {"Name": "Union Square", "Visited": true}},
                    {"fields": {"Name": "Ferry Building"}}]}'
```

```python
resp = requests.post(
    f"https://api.airtable.com/v0/{base_id}/{table}",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json={"records": [{"fields": {"Name": "Union Square", "Visited": True}}]},
)
new_ids = [r["id"] for r in resp.json()["records"]]
```

**示例响应**：返回新建记录的 `id`/`createdTime`/`fields`（结构与 List/Get records 一致）。附件字段如果部分文件抓取失败，响应会额外带 `details: {message: "partialSuccess", reasons: ["attachmentsFailedUploading" | "attachmentUploadRateIsTooHigh"]}`，此时记录本身已经创建成功，只是附件没传上——**不能只看 HTTP 状态码判断"附件也成功了"，要检查 `details`**。

## Update records（单条与批量、upsert）

**Endpoint（批量）**: `PATCH`/`PUT https://api.airtable.com/v0/{baseId}/{tableIdOrName}`（body 里带 `records` 数组，每个元素含 `id` 或走 upsert）
**Endpoint（单条）**: `PATCH`/`PUT https://api.airtable.com/v0/{baseId}/{tableIdOrName}/{recordId}`（body 直接是 `{"fields": {...}}`）

**PATCH vs PUT**：PATCH 只更新请求里出现的字段，其余保持不变；**PUT 是破坏性更新，会清空所有没在这次请求里出现的字段**。绝大多数"更新记录"场景应该用 PATCH；只有明确想清空未提及字段时才用 PUT。

**关键参数（批量）**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `records` | array\<{id?, fields}\> | 是 | `id` 在非 upsert 场景必填；upsert 场景可选 |
| `performUpsert` | {fieldsToMergeOn: array\<string\>} | 否 | 见下方 upsert 小节 |
| `typecast` | boolean | 否，默认 `false` | — |
| `returnFieldsByFieldId` | boolean | 否，默认 `false` | — |

### Upsert（`performUpsert`）

设置 `performUpsert.fieldsToMergeOn` 后：

- `fieldsToMergeOn` 是 1~3 个字段名/ID 的数组，**必须是能唯一标识一条记录的字段**，且**不能是计算字段**（formula/lookup/rollup），类型必须是 number / text / long text / single select / multiple select / date 之一。
- 数组里的 record **可以不传 `id`**：没传 `id` 的 record 会用 `fieldsToMergeOn` 指定的字段去匹配已有记录——零匹配则新建，一个匹配则更新，**多个匹配则整个请求失败**（不会随便更新其中一条）。
- 传了 `id` 的 record 会忽略 `fieldsToMergeOn`，按普通更新处理；如果这个 `id` 不存在，请求失败、不会退化成创建。
- 响应会比普通更新多两个字段：`createdRecords`（本次实际新建的 record ID 数组）和 `updatedRecords`（本次实际更新的 record ID 数组），据此判断每条记录最终走的是创建还是更新路径。
- 官方原文提示：**upsert 请求的限流策略可能和标准限流不同**（"Airtable reserves the right to throttle upsert requests differently from the standard rate limit throttling policy"），具体数字未给出，⚠ 未实测确认。

**示例请求（批量 upsert）**

```bash
curl -X PATCH "https://api.airtable.com/v0/{baseId}/{tableIdOrName}" \
  -H "Authorization: Bearer $AIRTABLE_TOKEN" -H "Content-Type: application/json" \
  -d '{"performUpsert": {"fieldsToMergeOn": ["Name"]},
       "records": [{"fields": {"Name": "New Park", "Visited": true}}]}'
```

## Delete records（单条与批量）

**Endpoint（批量）**: `DELETE https://api.airtable.com/v0/{baseId}/{tableIdOrName}?records[]=recXXX&records[]=recYYY`——注意这是 **query string**，不是请求体（和 create/update 不同）。
**Endpoint（单条）**: `DELETE https://api.airtable.com/v0/{baseId}/{tableIdOrName}/{recordId}`

```bash
curl -X DELETE "https://api.airtable.com/v0/{baseId}/{tableIdOrName}?records[]=rec560UJdUtocSouk&records[]=rec3lbPRG4aVqkeOQ" \
  -H "Authorization: Bearer $AIRTABLE_TOKEN"
```

响应是 `{"records": [{"id": "...", "deleted": true}, ...]}`。

## 批量上限（重点）

**⚠ 文档缺口**：官方 Web API 文档正文和内嵌的 OpenAPI 规范里，Create/Update/Delete records 三个 endpoint 都**没有**对 `records` 数组给出显式的 `maxItems` 或"最多 N 条"的文字说明——这在调研过程中反复用关键词检索（"10 records"、"up to N record"、`maxItems` 等）确认过，确实找不到。

但业界广泛引用、且被官方文档列为社区常用客户端的 [`pyairtable`](https://github.com/gtalarico/pyairtable) 源码里硬编码：

```python
# pyairtable/api/api.py
MAX_RECORDS_PER_REQUEST = 10
```

并且 `batch_create`/`batch_update`/`batch_upsert`/`batch_delete` 都会按这个数字自动切片分批发送。这与长期以来社区的共识一致（"Airtable 每次批量写请求最多 10 条记录"），但**不等于真实调用验证过当前这个数字仍然准确**——完全可能是历史遗留限制，也可能官方已经放宽/收紧过。

**给通用"批量写记录"函数的建议**：默认按 **10 条/请求** 做客户端分批，超过 10 条的 `records` 数组自己切片、多次请求；如果实际调用发现服务端返回的真实上限不同（比如某个错误响应里带了具体数字），以真实返回为准并更新这份文档。这是 `airtable-workspace/verification-plan.md` 的 P0 第一项。

```python
def chunked(seq, size=10):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]

def batch_create(base_id, table, headers, records):
    created = []
    for chunk in chunked(records, 10):
        r = requests.post(f"https://api.airtable.com/v0/{base_id}/{table}",
                           headers=headers, json={"records": [{"fields": f} for f in chunk]})
        r.raise_for_status()
        created.extend(r.json()["records"])
    return created
```

## typecast

`typecast: true`（Create/Update 都支持）让 Airtable 尝试把字符串值"尽力"转换成目标字段类型的合适值——例如把字符串 `"123"` 转成 number 字段的 `123`，或者给 single/multiple select 传一个不存在的选项名时自动新建这个选项（而不是报 `INVALID_MULTIPLE_CHOICE_OPTIONS`）。默认是 `false`，官方原文强调这是为了"保证数据完整性"，只在对接第三方数据源、能接受"尽力而为"的自动转换时才建议打开。

## 计算字段不可写（重点）

以下字段类型的值是**只读**的，`field-model` 文档对每一个都明确标注 `(read only)`；给这些字段传值会被当成校验失败（具体错误码⚠文档未给出针对性示例，未实测确认，大概率是 422 `INVALID_REQUEST_UNKNOWN` 或类似的字段级校验错误）：

| 只读字段类型 | 说明 |
|---|---|
| `formula` | 公式计算结果 |
| `rollup` | 汇总链接表的数据 |
| `lookup`（`multipleLookupValues`） | 引用链接表字段的值 |
| `count` | 链接记录数量 |
| `autoNumber` | 自增编号 |
| `createdTime` | 记录创建时间 |
| `createdBy` | 记录创建者 |
| `lastModifiedTime` | 最后修改时间 |
| `lastModifiedBy` | 最后修改者 |
| `button` | UI 按钮，只有 `label`/`url` 可读 |
| `aiText` | AI 生成文本 |

**给"批量更新记录"这类通用函数的实现建议**：不要假设调用方传来的 `fields` 字典里全是可写字段。生产代码应该先用 Metadata API（`GET /v0/meta/bases/{baseId}/tables`，见 `field-types-and-schema.md`）取一次字段清单，过滤掉 `type` 落在上表里的字段，再组装写请求体，否则一旦调用方不小心把只读字段也塞进去（很常见，比如"把读到的整条记录原样传回去更新"这种写法），整个批量请求可能因为一个字段而报错。

**注意区分两件事**：上表是"**记录级别的 cell 值**不能通过 Create/Update records 写入"，不等于"这些字段类型完全不能被 API 涉及"——字段的**定义（schema）本身**（比如新建一个 formula 字段、指定它的公式表达式）是可以通过 Metadata API 的 Create field / Update field 接口读写的，那是另一件事，见 `field-types-and-schema.md`。

## 附件上传

给 `multipleAttachments` 字段写入的两条路径：

### 路径 1：公网 URL（推荐，无大小限制受制于源文件本身）

直接把 URL 当成普通字段值，跟着其它字段一起走 Create/Update records：

```json
{"fields": {"Attachments": [{"url": "https://example.com/file.pdf"}]}}
```

Airtable 服务端会异步抓取这个 URL 的内容存成附件。**⚠ 这个写入形状的完整字段表文档没有给出**——官方 `field-model` 页对附件字段的 "Cell format (write)" 只写了 `array<object>`，没有列出 `url` 是否是唯一必填字段、`filename` 要不要一起传；内嵌的 OpenAPI 规范里也只找到读格式（`id`/`url`/`filename`/`size`/`type`/`width`/`height`/`thumbnails` 全部标 required，明显是响应专用形状），没有单独的写格式 schema。已列入验证计划优先核实。

抓取失败时不会让整个写请求报错，而是记录创建/更新成功，响应带 `details: {message: "partialSuccess", reasons: [...]}`（见上文 Create records 小节）。

### 路径 2：直接上传文件字节（≤5MB）

**Endpoint**: `POST https://content.airtable.com/v0/{baseId}/{recordId}/{attachmentFieldIdOrName}/uploadAttachment`

**注意：域名是 `content.airtable.com`，不是 `api.airtable.com`**——这是本 skill 认定的第二个容易漏掉的坑，照抄其它端点的 base URL 会直接连不上。而且这个端点作用于**已存在的记录**（`recordId` 是路径参数），不能用它一步创建带附件的新记录，需要先创建空记录再调这个接口。

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `contentType` | string | 是 | MIME 类型，如 `"image/jpeg"`，限 255 字符 |
| `file` | string | 是 | 文件内容的 **base64** 编码字符串 |
| `filename` | string | 是 | 文件名 |

```bash
curl -X POST "https://content.airtable.com/v0/{baseId}/{recordId}/{attachmentFieldIdOrName}/uploadAttachment" \
  -H "Authorization: Bearer $AIRTABLE_TOKEN" -H "Content-Type: application/json" \
  -d '{"contentType": "text/plain", "file": "SGVsbG8gd29ybGQ=", "filename": "sample.txt"}'
```

响应带 `id`/`createdTime`/`fields`（`fields` 用**字段 ID**做 key，不是字段名，和其它写接口默认行为不同）。

**超过 5MB 的文件只能走路径 1**（公网 URL），uploadAttachment 端点本身限制 5MB。

### 附件 URL 的时效性

无论走哪条路径，读回来的附件 `url`（包括 thumbnails 里的 url）都是**签名过期链接，2 小时后失效**。需要长期保存的场景必须在拿到响应后立刻下载存到自己的对象存储，不能把这个 URL 当永久链接持久化。
