# 文件管理、文档解析与批量处理

本文档覆盖智谱开放平台（bigmodel.cn）的文件管理、文件解析服务（同步/异步）、OCR 服务，以及 Batch 批量处理 API。

- **Base URL**: `https://open.bigmodel.cn/api/`（下文所有 `path` 均相对此 base）
- **鉴权**: 请求头 `Authorization: Bearer <API_KEY>`，API Key 在 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取
- 调用 Batch API 前必须完成实名认证（个人或企业），入口：https://open.bigmodel.cn/usercenter/settings/auth

---

## 一、文件管理 API

### 上传文件

**Endpoint**: `POST /paas/v4/files`

**用途**: 上传文件供 `Batch 任务`、`智能体`、`代码沙盒`等功能使用。`purpose` 字段决定文件用途、允许格式与大小限制，必须与后续场景匹配（例如给 Batch 任务用的文件必须以 `purpose=batch` 上传）。

**关键参数**（multipart/form-data）

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| file | binary | 是 | - | 要上传的文件 |
| purpose | string | 是 | - | 文件预期用途，见下表 |

**purpose 取值与限制**

| purpose | 支持格式 | 单文件大小限制 | 文件数量限制 | 说明 |
| --- | --- | --- | --- | --- |
| `batch` | `.jsonl` | 100MB | ≤1000 个 | Batch 批量任务请求文件 |
| `code-interpreter` | pdf, docx, doc, xls, xlsx, txt, png, jpg, jpeg, csv | 20MB（图片≤5MB） | ≤100 个 | 上传给代码沙盒 CI 使用 |
| `agent` | pdf, docx, doc, xls, xlsx, txt, png, jpg, jpeg, csv | 20MB（图片≤5MB） | ≤1000 个 | 智能体文件上传 |
| `voice-clone-input` | mp3, wav | - | - | 音色克隆功能的示例音频 |
| `user_data` | pptx, ppt, docx, doc, xlsx, xls, pdf | - | 每用户≤1T | 用户文件上传（未出现在部分接口的 `purpose` 枚举列表里，遇 400 报错请改用 `batch`/`agent`/`code-interpreter`） |

**示例请求**

```bash
curl --location --request POST 'https://open.bigmodel.cn/api/paas/v4/files' \
--header 'Authorization: Bearer YOUR_API_KEY' \
--form 'file=@batch_requests.jsonl' \
--form 'purpose="batch"'
```

```python
import requests

with open("batch_requests.jsonl", "rb") as f:
    resp = requests.post(
        "https://open.bigmodel.cn/api/paas/v4/files",
        headers={"Authorization": "Bearer YOUR_API_KEY"},
        files={"file": f},
        data={"purpose": "batch"},
    )
file_obj = resp.json()
print(file_obj["id"])
```

**示例响应**

```json
{"id": "file-xxxxxxxx", "object": "file", "bytes": 20480, "created_at": 1715959701, "filename": "batch_requests.jsonl", "purpose": "batch"}
```

**注意事项**

- `Try it` 在线试用仅支持小文件，实际大小限制以上表 `purpose` 说明为准。
- 文件仅保留 30 天，过期自动删除、无法恢复，请及时下载备份。
- Batch 用途文件每次最多上传 1000 个，任务量大时应及时删除已处理完的文件。

---

### 文件列表

**Endpoint**: `GET /paas/v4/files`

**用途**: 分页获取已上传文件列表，支持按 `purpose` 过滤和排序。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| purpose | string | 是 | - | 按用途过滤，枚举：`batch`, `code-interpreter`, `agent` |
| after | string | 否 | - | 分页游标，传入上一页某对象 ID，获取其后的下一页 |
| order | string | 否 | - | 排序方式，枚举：`created_at` |
| limit | integer | 否 | 20 | 每页数量，范围 1-100 |

**示例请求**

```bash
curl --location --request GET 'https://open.bigmodel.cn/api/paas/v4/files?purpose=batch&limit=10' \
--header 'Authorization: Bearer YOUR_API_KEY'
```

```python
import requests

resp = requests.get(
    "https://open.bigmodel.cn/api/paas/v4/files",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    params={"purpose": "batch", "limit": 10},
)
for f in resp.json()["data"]:
    print(f["id"], f["filename"], f["bytes"])
```

**示例响应**

```json
{"object": "list", "data": [{"id": "file-xxx", "object": "file", "bytes": 20480, "created_at": 1715959701, "filename": "a.jsonl", "purpose": "batch"}], "has_more": false}
```

**注意事项**

- `purpose` 在接口定义中标记为必填参数，调用时须显式传入。
- 用 `has_more` 判断是否需要以最后一个对象的 `id` 作为下一次请求的 `after` 继续翻页。

---

### 删除文件

**Endpoint**: `DELETE /paas/v4/files/{file_id}`

**用途**: 永久删除指定文件及其所有关联数据，操作不可撤销。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| file_id | string (path) | 是 | - | 文件唯一标识符 |

**示例请求**

```bash
curl --location --request DELETE 'https://open.bigmodel.cn/api/paas/v4/files/file-xxxxxxxx' \
--header 'Authorization: Bearer YOUR_API_KEY'
```

```python
import requests

resp = requests.delete(
    "https://open.bigmodel.cn/api/paas/v4/files/file-xxxxxxxx",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
)
print(resp.json())
```

**示例响应**

```json
{"id": "file-xxxxxxxx", "object": "file", "deleted": true}
```

**注意事项**

- 删除不可逆，请确认文件（尤其 Batch 结果文件）已下载备份后再删除。

---

### 获取文件内容

**Endpoint**: `GET /paas/v4/files/{file_id}/content`

**用途**: 下载文件原始内容。**只支持 `batch` 类型文件**（即 Batch 任务的 `output_file_id` / `error_file_id`），不能下载 `agent`/`code-interpreter` 等其他 purpose 的文件。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| file_id | string (path) | 是 | - | 被请求文件的唯一标识符 |

**示例请求**

```bash
curl --location --request GET 'https://open.bigmodel.cn/api/paas/v4/files/file-output-xxx/content' \
--header 'Authorization: Bearer YOUR_API_KEY' \
--output batch_results.jsonl
```

```python
import requests

resp = requests.get(
    "https://open.bigmodel.cn/api/paas/v4/files/file-output-xxx/content",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
)
with open("batch_results.jsonl", "wb") as f:
    f.write(resp.content)
```

**示例响应**

响应为 `application/octet-stream` 二进制文件流，直接写入本地文件即可（Batch 输出通常是 `.jsonl`）。

**注意事项**

- 仅适用于 batch 文件；用它下载解析结果或其他类型文件会失败。
- 结合 Batch 任务的 `output_file_id`（成功结果）与 `error_file_id`（失败结果）分别下载。

---

## 二、文件解析服务（Document Parser）

面向大文档批量/结构化解析的独立服务，与对话内联使用的版面解析工具不同：这里是先上传文件创建解析任务，再单独取回结果，适合知识库构建、大模型前置解析等场景。提供三档异步解析工具（`lite`/`expert`/`prime`）和一个同步接口（`prime-sync`）。

### 解析工具对比

| 服务类型 | 支持格式 | 最大文件大小 | 解析结果 | 计费方式 |
| --- | --- | --- | --- | --- |
| **Prime**（异步） | pdf, docx, doc, xls, xlsx, ppt, pptx, png, jpg, jpeg, csv, txt, md, html, bmp, gif, webp, heic, eps, icns, im, pcx, ppm, tiff, xbm, heif, jp2 | PDF/DOC/DOCX/PPT ≤100MB；XLS/XLSX/CSV ≤10MB；PNG/JPG/JPEG ≤20MB | 图片+Markdown+布局 JSON（下载链接）或纯文本 | 按页数付费，优惠后约 0.12 元/页 |
| **Expert**（异步） | pdf | ≤100MB | 图片+Markdown（下载链接） | 按页数计费，优惠后约 0.012 元/页 |
| **Lite**（异步） | pdf, docx, doc, xls, xlsx, ppt, pptx, png, jpg, jpeg, csv, txt, md | ≤50MB | 纯文本（不保留图片） | 按调用次数计费，当前免费 |
| **Prime-sync**（同步） | wps, pdf, doc, docx, ppt, pptx, md, txt, xls, xlsx, csv, html, png, jpg, jpeg, bmp, gif, webp, heic, eps, icns, im, pcx, ppm, tiff, xbm, heif, jp2 | WPS/PDF/DOC/DOCX/PPT/PPTX ≤100MB；MD/TXT/XLS/XLSX/CSV ≤10MB；其他 ≤20MB | 图片+Markdown+布局 JSON（下载链接）或纯文本 | 按页数付费，优惠后约 0.12 元/页，效果与 Prime 持平但更快 |

**同步 vs 异步选型建议**：小文件、需要立即拿到结果的在线链路（上传后马上问答/预览）→ 用 `POST /paas/v4/files/parser/sync`（`tool_type=prime-sync`），一次请求直接返回结果，无需轮询。大文件、极复杂版面、高并发或可后台处理的批量任务 → 用异步接口：先 `POST /paas/v4/files/parser/create` 拿到 `task_id`，再轮询 `GET /paas/v4/files/parser/result/{taskId}/{format_type}` 直到 `status` 变为 `succeeded`/`failed`。

### 创建文件解析任务（异步）

**Endpoint**: `POST /paas/v4/files/parser/create`

**用途**: 上传文件并创建异步解析任务，返回 `task_id`，随后需轮询结果接口获取解析内容。

**关键参数**（multipart/form-data）

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| file | binary | 是 | - | 待解析文件 |
| tool_type | string | 是 | - | 解析工具类型：`lite`, `expert`, `prime` |
| file_type | string | 否 | - | 文件类型（如 `PDF`, `DOCX`），需与 `tool_type` 支持范围匹配（见上方对比表） |

**示例请求**

```bash
curl --location --request POST 'https://open.bigmodel.cn/api/paas/v4/files/parser/create' \
--header 'Authorization: Bearer YOUR_API_KEY' \
--form 'file=@example.pdf' \
--form 'tool_type="prime"' \
--form 'file_type="PDF"'
```

```python
import requests

with open("example.pdf", "rb") as f:
    resp = requests.post(
        "https://open.bigmodel.cn/api/paas/v4/files/parser/create",
        headers={"Authorization": "Bearer YOUR_API_KEY"},
        files={"file": f},
        data={"tool_type": "prime", "file_type": "PDF"},
    )
task_id = resp.json()["task_id"]
```

**示例响应**

```json
{"success": true, "message": "任务创建成功", "task_id": "task_id_xxx"}
```

**注意事项**

- `file_type` 支持范围因 `tool_type` 而异：Lite 仅支持办公文档常见格式；Expert 仅支持 pdf；Prime 支持最全。
- 创建成功后须保存 `task_id` 用于后续轮询，任务不会主动推送结果。

---

### 查询解析结果（异步）

**Endpoint**: `GET /paas/v4/files/parser/result/{taskId}/{format_type}`

**用途**: 使用 `task_id` 轮询异步解析任务的结果，可选择返回纯文本或下载链接。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| taskId | string (path) | 是 | - | 文件解析任务 ID |
| format_type | string (path) | 是 | - | 结果格式：`text`（直接返回文本，最长约 1M 以内）或 `download_link`（返回图片+Markdown+布局 JSON 的下载链接，响应更快） |

**示例请求**

```bash
curl --request GET \
--url 'https://open.bigmodel.cn/api/paas/v4/files/parser/result/task_id_xxx/text' \
--header 'Authorization: Bearer YOUR_API_KEY'
```

```python
import time
import requests

HEADERS = {"Authorization": "Bearer YOUR_API_KEY"}

def poll_parse_result(task_id, format_type="text", max_retry=100, interval=3):
    url = f"https://open.bigmodel.cn/api/paas/v4/files/parser/result/{task_id}/{format_type}"
    for _ in range(max_retry):
        data = requests.get(url, headers=HEADERS).json()
        if data["status"] == "succeeded":
            return data
        if data["status"] == "failed":
            raise RuntimeError(data["message"])
        time.sleep(interval)  # status == "processing"
    raise TimeoutError("解析任务超时，请稍后自行查询")

result = poll_parse_result(task_id)
print(result["content"])
```

**示例响应**

```json
{"status": "succeeded", "message": "结果获取成功", "content": "parsed result text", "task_id": "task_id_xxx", "parsing_result_url": "download url"}
```

**注意事项**

- `status` 取值：`processing`（处理中）、`succeeded`（成功）、`failed`（失败）。
- `content` 仅在 `format_type=text` 时有值；`parsing_result_url` 仅在 `format_type=download_link` 时有值，未请求的字段为 `null`。
- 下载链接（`parsing_result_url`）有效期 **24 小时**，过期需重新调用解析接口生成新链接。
- 需直接喂给大模型时用 `text`；需保留图片和排版信息时用 `download_link`。

---

### 文件解析（同步）

**Endpoint**: `POST /paas/v4/files/parser/sync`

**用途**: 一次请求即返回解析结果，无需轮询，适合小文件、低延迟的在线处理链路。效果与 Prime 持平但速度更快。

**关键参数**（multipart/form-data）

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| file | binary | 是 | - | 待解析文件 |
| tool_type | string | 是 | - | 固定为 `prime-sync` |
| file_type | string | 否 | - | 文件类型，见对比表 Prime-sync 一行支持范围 |

**示例请求**

```bash
curl --location --request POST 'https://open.bigmodel.cn/api/paas/v4/files/parser/sync' \
--header 'Authorization: Bearer YOUR_API_KEY' \
--form 'file=@example.pdf' \
--form 'tool_type="prime-sync"' \
--form 'file_type="PDF"'
```

```python
import requests

with open("example.pdf", "rb") as f:
    resp = requests.post(
        "https://open.bigmodel.cn/api/paas/v4/files/parser/sync",
        headers={"Authorization": "Bearer YOUR_API_KEY"},
        files={"file": f},
        data={"tool_type": "prime-sync", "file_type": "PDF"},
    )
print(resp.json()["content"])
```

**示例响应**

```json
{"status": "succeeded", "message": "结果获取成功", "content": "parsed result text", "task_id": "task_id_xxx", "parsing_result_url": "download url"}
```

**注意事项**

- 响应结构与异步查询结果接口一致（`status`/`content`/`parsing_result_url`），但结果在本次请求内同步返回。
- 超大文件、极复杂版面、高并发批量任务不适用同步接口，请改用异步解析（create + 轮询）。
- 下载链接同样 24 小时后失效。

---

### OCR 服务

**Endpoint**: `POST /paas/v4/files/ocr`

**用途**: 对图片中的文字进行光学字符识别，支持印刷体与手写体，支持中、英、日、韩、法等 20+ 种语言，返回每行文本及坐标位置，可选返回置信度。

**关键参数**（multipart/form-data）

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| file | binary | 是 | - | 待识别图片，支持 PNG/JPG/JPEG/BMP，大小 ≤8M |
| tool_type | string | 是 | - | 固定为 `hand_write`（识别模式） |
| language_type | string | 否 | `CHN_ENG` | 识别语言，`AUTO` 为自动检测，其他可选：`ENG, JAP, KOR, FRE, SPA, POR, GER, ITA, RUS, DAN, DUT, MAL, SWE, IND, POL, ROM, TUR, GRE, HUN, THA, VIE, ARA, HIN` |
| probability | boolean | 否 | false | 是否返回每行识别结果的置信度信息 |

**示例请求**

```bash
curl --location --request POST 'https://open.bigmodel.cn/api/paas/v4/files/ocr' \
--header 'Authorization: Bearer YOUR_API_KEY' \
--form 'file=@handwriting.jpg' \
--form 'tool_type="hand_write"' \
--form 'language_type="CHN_ENG"' \
--form 'probability="true"'
```

```python
import requests

with open("handwriting.jpg", "rb") as f:
    resp = requests.post(
        "https://open.bigmodel.cn/api/paas/v4/files/ocr",
        headers={"Authorization": "Bearer YOUR_API_KEY"},
        files={"file": f},
        data={"tool_type": "hand_write", "language_type": "CHN_ENG", "probability": "true"},
    )
for line in resp.json()["words_result"]:
    print(line["words"])
```

**示例响应**

```json
{
  "task_id": "658c5c5e9d4f4f8c8c8c8c8c",
  "message": "success",
  "status": "succeeded",
  "words_result_num": 11,
  "words_result": [
    {"location": {"left": 125, "top": 76, "width": 756, "height": 127}, "words": "book ruler pencil schoolbag", "probability": {"average": 0.98, "variance": 0.001, "min": 0.9}}
  ]
}
```

失败示例：`{"task_id": null, "message": "上传的图片格式错误（仅支持PNG、JPG、JPEG、BMP）", "status": null, "words_result_num": 0}`

**注意事项**

- 单次仅支持单页（单张图片）识别，大小上限 8M，超出格式/大小直接返回失败响应而非报错任务；计费按页数，单价约 0.01 元/次（页）。
- `probability` 字段仅在请求传 `probability=true` 时才出现在返回结果中。
- 最佳实践：图片清晰无遮挡反光；手写体建议深色墨迹配浅色背景；对置信度做业务层过滤。

---

## 三、批量处理 Batch API

Batch API 用于提交大规模、无需即时反馈的请求：通过文件批量提交任务，价格为标准 API 的 **50%**（GLM-4-Flash 免费），且不占用模型实时并发限额（Batch 有独立排队限制）。典型场景：文章批量分类、情感分析、批量信息抽取。

### 创建批处理任务

**Endpoint**: `POST /paas/v4/batches`

**用途**: 基于已上传的 `.jsonl` 请求文件创建批处理任务。

**关键参数**（application/json）

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| input_file_id | string | 是 | - | 上传文件的 ID，文件须为 `.jsonl` 格式，且上传时 `purpose` 须为 `batch` |
| endpoint | string | 是 | - | Batch 中所有请求使用的端点，目前仅支持 `/v4/chat/completions` |
| auto_delete_input_file | boolean | 否 | true | 是否自动删除 batch 原始输入文件 |
| metadata | object \| null | 否 | - | 附加键值对信息，最多 16 个，键长度 ≤64 字符，值长度 ≤512 字符 |
| completion_window | string | 已废弃 | - | 原时间参数已失效，任务预计 24 小时内完成，超 7 天未处理完将自动取消 |

**示例请求**

```bash
curl --location --request POST 'https://open.bigmodel.cn/api/paas/v4/batches' \
--header 'Authorization: Bearer YOUR_API_KEY' \
--header 'Content-Type: application/json' \
--data '{"input_file_id": "file-xxxxxxxx", "endpoint": "/v4/chat/completions", "auto_delete_input_file": true, "metadata": {"description": "商品评价情感分析"}}'
```

```python
import requests

resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/batches",
    headers={"Authorization": "Bearer YOUR_API_KEY", "Content-Type": "application/json"},
    json={
        "input_file_id": "file-xxxxxxxx",
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {"description": "商品评价情感分析"},
    },
)
batch = resp.json()
print(batch["id"], batch["status"])
```

**示例响应**（Batch 对象，节选）

**示例响应**（已用真实 API 调用替换为验证过的真实返回结构，2026-09；原文档示例把计数字段错误地放在顶层，已订正）：

```json
{"id": "batch_2095408344001937408", "object": "batch", "endpoint": "/v4/chat/completions",
 "input_file_id": "1788419253_167220ae09214e3d8cd523adb7fed489", "completion_window": null,
 "status": "validating", "output_file_id": null, "error_file_id": null,
 "created_at": 1788419254671, "in_progress_at": null, "expires_at": null, "finalizing_at": null,
 "completed_at": null, "failed_at": null, "expired_at": null, "cancelling_at": null, "cancelled_at": null,
 "request_counts": {"total": 2, "completed": null, "failed": null}, "metadata": null}
```

**注意事项**

- `endpoint` 目前只支持 `/v4/chat/completions`；`.jsonl` 中每行的 `url` 字段需与之一致。一个 batch 文件只能包含对**单一模型**的请求；每个请求必须包含唯一的 `custom_id`，用于结果与输入的匹配。**`custom_id` 最短 6 个字符**（已用真实调用验证：传 `"r1"` 这种两三位短字符串会在文件上传阶段直接报错 `1210`："custom id 长度不足, 最短: 6"），别用 `id-1`/`r1` 这类过短的编号，建议用 `request-001` 这种格式或 UUID。
- 单个 batch 文件最多 50,000 个请求且不超过 100MB；向量模型（Embedding-2/Embedding-3）批量请求数不超过 10,000 次。各模型有独立的 Batch 排队上限（如 GLM-4-Plus/GLM-4-Air-250414/Embedding 系列约 200 万次，GLM-4V 系列约 1 万次），达到上限需等待当前任务完成后再提交。
- 调用 Batch API 前必须完成实名认证。
- **计数字段是嵌套的 `request_counts.{total,completed,failed}`，不是顶层的 `total`/`completed`/`failed`**（已用真实调用验证；上一版文档示例是错的，读代码时用 `batch["request_counts"]["total"]` 而不是 `batch["total"]`）。
- **⚠️ Batch 只支持一份模型白名单，不是平台全部模型**（已用真实调用验证，2026-09）：把 `.jsonl` 里的 `body.model` 写成 `glm-4-flash-250414` 上传时，**整份文件在上传阶段就被拒绝**（业务错误码 `1210`：`模型名称错误`），实测报错信息里给出的完整白名单是：`glm-5.1、glm-5-turbo、glm-4、glm-4-0520、glm-4-plus、glm-4-long、glm-4-plus-0111、glm-4-air、glm-4-air-0111、glm-4-air-250414、glm-4-flash、glm-4-flashx-250414、glm-3-turbo、glm-4v、glm-4v-plus、glm-5v-turbo、glm-4v-plus-0111、cogview-3、cogview-3-plus、cogview-4-250304、embedding-2、embedding-3、cogvideox、cogvideox-2`（截至验证时；该白名单会随平台更新变化，报错信息本身就是最权威的来源，不要死记这份列表）。**关键含义**：`references/models.md` 里推荐的旗舰模型（`glm-5.3`、`glm-5.2`、`glm-image` 等）目前都不在这份白名单里，写 Batch 任务前必须先确认目标模型在不在这份名单内，不能想当然地把同步接口能用的模型直接套进 Batch；且校验发生在**文件上传**这一步（`POST /paas/v4/files`），不是等到创建 batch 任务才报错。

---

### 列出批处理任务

**Endpoint**: `GET /paas/v4/batches`

**用途**: 分页获取批处理任务列表。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| after | string | 否 | - | 分页游标，传入上一页最后一个对象 ID 获取下一页 |
| limit | integer | 否 | 20 | 返回数量，范围 1-100 |

**示例请求**

```bash
curl --location --request GET 'https://open.bigmodel.cn/api/paas/v4/batches?limit=10' \
--header 'Authorization: Bearer YOUR_API_KEY'
```

```python
import requests

resp = requests.get(
    "https://open.bigmodel.cn/api/paas/v4/batches",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    params={"limit": 10},
)
for b in resp.json()["data"]:
    print(b["id"], b["status"])
```

**示例响应**

```json
{"object": "list", "data": [{"id": "batch_xxx", "object": "batch", "status": "completed", "total": 10, "completed": 10, "failed": 0}], "first_id": "batch_xxx", "last_id": "batch_yyy", "has_more": false}
```

**注意事项**

- 用 `has_more` + `last_id` 配合 `after` 参数翻页。

---

### 检索批处理任务

**Endpoint**: `GET /paas/v4/batches/{batch_id}`

**用途**: 根据 `batch_id` 查询批处理任务详细状态，用于轮询任务是否完成。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| batch_id | string (path) | 是 | - | 批处理任务的唯一标识符 |

**示例请求**

```bash
curl --location --request GET 'https://open.bigmodel.cn/api/paas/v4/batches/batch_1791490810192076800' \
--header 'Authorization: Bearer YOUR_API_KEY'
```

```python
import requests

batch_id = "batch_1791490810192076800"
resp = requests.get(
    f"https://open.bigmodel.cn/api/paas/v4/batches/{batch_id}",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
)
batch = resp.json()
print(batch["status"], batch["completed"], batch["failed"])
```

**示例响应**: 同"创建批处理任务"返回的 Batch 对象结构。

**状态取值（status）**

| 状态 | 描述 |
| --- | --- |
| validating | 文件正在验证中，任务未开始 |
| failed | 文件未通过验证 |
| in_progress | 文件已验证通过，任务正在进行中 |
| finalizing | 任务已完成，结果正在准备中 |
| completed | 任务已完成，结果已准备好 |
| expired | 任务未能在限期内完成 |
| cancelling | 任务正在取消中 |
| cancelled | 任务已取消 |

**注意事项**

- 建议轮询间隔 20-30 秒，避免过于频繁请求。任务过期（`expired`）后未完成的请求会被取消；已完成的请求仍可通过文件获取，并需支付相应费用。
- Batch 文件（含结果文件）只保留 30 天，过期自动删除、无法恢复，请及时下载。

---

### 取消批处理任务

**Endpoint**: `POST /paas/v4/batches/{batch_id}/cancel`

**用途**: 取消正在运行的批处理任务。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| batch_id | string (path) | 是 | - | 要取消的批处理任务的唯一标识符 |

**示例请求**

```bash
curl --location --request POST 'https://open.bigmodel.cn/api/paas/v4/batches/batch_1791490810192076800/cancel' \
--header 'Authorization: Bearer YOUR_API_KEY'
```

```python
import requests

batch_id = "batch_1791490810192076800"
resp = requests.post(
    f"https://open.bigmodel.cn/api/paas/v4/batches/{batch_id}/cancel",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
)
print(resp.json()["status"])
```

**示例响应**: 返回 Batch 对象，`status` 变为 `cancelling`（随后转为 `cancelled`）。

**注意事项**

- 取消是异步过程：调用后状态先变为 `cancelling`，稍后才最终变为 `cancelled`。
- 取消前已完成的请求仍会计费并可通过结果文件获取。

---

### 端到端工作流程

完整流程：**准备 JSONL 请求文件 → 上传文件（`purpose=batch`）→ 创建 Batch 任务（引用 `input_file_id`）→ 轮询任务状态 → 完成后用文件内容接口下载 `output_file_id` / `error_file_id`**。

`.jsonl` 每行是一个独立请求，必须包含唯一 `custom_id`：

```json
{"custom_id": "request-1", "method": "POST", "url": "/v4/chat/completions", "body": {"model": "glm-4-plus", "messages": [{"role": "system", "content": "你是一个意图分类器."}, {"role": "user", "content": "对评论进行情感分类：订单处理速度太慢。"}], "temperature": 0.1}}
{"custom_id": "request-2", "method": "POST", "url": "/v4/chat/completions", "body": {"model": "glm-4-plus", "messages": [{"role": "system", "content": "你是一个意图分类器."}, {"role": "user", "content": "对评论进行情感分类：客服很耐心，解决问题很快。"}], "temperature": 0.1}}
```

```python
import time
import requests

BASE = "https://open.bigmodel.cn/api"
HEADERS = {"Authorization": "Bearer YOUR_API_KEY"}
TERMINAL_STATES = {"completed", "failed", "expired", "cancelled"}

# 1. 上传 batch 请求文件（purpose=batch）
with open("batch_requests.jsonl", "rb") as f:
    upload_resp = requests.post(f"{BASE}/paas/v4/files", headers=HEADERS,
                                 files={"file": f}, data={"purpose": "batch"})
input_file_id = upload_resp.json()["id"]

# 2. 创建 batch 任务，引用 input_file_id
create_resp = requests.post(
    f"{BASE}/paas/v4/batches",
    headers={**HEADERS, "Content-Type": "application/json"},
    json={
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {"project": "sentiment_analysis"},
    },
)
batch_id = create_resp.json()["id"]

# 3. 轮询任务状态
while True:
    batch = requests.get(f"{BASE}/paas/v4/batches/{batch_id}", headers=HEADERS).json()
    print("任务状态:", batch["status"])
    if batch["status"] in TERMINAL_STATES:
        break
    time.sleep(30)

# 4. 下载结果文件（成功结果 + 错误结果）
if batch["status"] == "completed":
    if batch.get("output_file_id"):
        content = requests.get(f"{BASE}/paas/v4/files/{batch['output_file_id']}/content", headers=HEADERS)
        open("batch_results.jsonl", "wb").write(content.content)
    if batch.get("error_file_id"):
        errors = requests.get(f"{BASE}/paas/v4/files/{batch['error_file_id']}/content", headers=HEADERS)
        open("batch_errors.jsonl", "wb").write(errors.content)
```

输出结果文件中每行结构（`custom_id` 与输入一一对应）：

```json
{"response": {"status_code": 200, "body": {"model": "glm-4", "choices": [{"finish_reason": "stop", "index": 0, "message": {"role": "assistant", "content": "{\"分类标签\": \"负面\", \"特定问题标注\": \"订单处理慢\"}"}}], "usage": {"completion_tokens": 26, "prompt_tokens": 89, "total_tokens": 115}}}, "custom_id": "request-1", "id": "batch_1791490810192076800"}
```

**注意事项**

- 结果文件按成功/失败分开保存：`output_file_id` 存放成功执行请求的输出，`error_file_id` 存放出错请求的信息，需分别下载；文件内容接口（`/files/{file_id}/content`）只支持 `batch` 类型文件。
- Batch 结果文件下载后请及时备份，30 天后过期自动删除、不可恢复。上传 Batch 文件每次最多 1000 个，任务量大时应及时用删除文件接口清理已处理完的文件，为新文件腾出配额。
