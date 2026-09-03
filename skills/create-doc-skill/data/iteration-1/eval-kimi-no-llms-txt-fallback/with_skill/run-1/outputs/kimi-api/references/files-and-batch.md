> 内容整理自 platform.kimi.com/docs（抓取于 2026-09-03），**尚未用真实 API 调用验证**；实际报错优先信任 API。

# Kimi API：文件接口与批处理（Files / Batch）

来源：`/docs/openapi.json`（Files / Batch 两组）、`/docs/api/files-upload`、`/docs/guide/use-kimi-api-for-file-based-qa`、`/docs/api/batch-create`、`/docs/guide/use-batch-api`、`/docs/api/errors`（仅文件相关行）。Base URL 与鉴权见 `auth.md`。

## 目录

- [0. 速查：和 OpenAI 的关键差异](#0-速查和-openai-的关键差异)
- [1. 我想让模型读一份文档（文件问答完整流程）](#1-我想让模型读一份文档文件问答完整流程)
- [2. 我想让模型看图片 / 视频（purpose=image / video）](#2-我想让模型看图片--视频purposeimage--video)
- [3. Files 端点参考](#3-files-端点参考)
  - [3.1 上传文件 `POST /v1/files`](#31-上传文件)
  - [3.2 列出文件 `GET /v1/files`](#32-列出文件)
  - [3.3 获取文件信息 `GET /v1/files/{file_id}`](#33-获取文件信息)
  - [3.4 删除文件 `DELETE /v1/files/{file_id}`](#34-删除文件)
  - [3.5 获取文件内容 `GET /v1/files/{file_id}/content`](#35-获取文件内容)
- [4. 我想低成本跑一大批离线请求（Batch 完整流程）](#4-我想低成本跑一大批离线请求batch-完整流程)
- [5. Batch 端点参考](#5-batch-端点参考)
  - [5.1 创建批处理任务 `POST /v1/batches`](#51-创建批处理任务)
  - [5.2 获取任务详情 `GET /v1/batches/{batch_id}`](#52-获取任务详情)
  - [5.3 列出批处理任务 `GET /v1/batches`](#53-列出批处理任务)
  - [5.4 取消批处理任务 `POST /v1/batches/{batch_id}/cancel`](#54-取消批处理任务)
- [6. 文件相关错误速查 + 文档矛盾汇总](#6-文件相关错误速查--文档矛盾汇总)

---

## 0. 速查：和 OpenAI 的关键差异

| 事项 | Kimi | OpenAI 直觉（会写错） |
|---|---|---|
| 文档问答的 `purpose` | `file-extract` | `assistants` / `user_data`（Kimi 直接 400 `Invalid purpose`） |
| 把文档交给模型的方式 | 先 `GET /v1/files/{id}/content` 拿**抽取后的文本**，再作为 **system 消息**塞进 `messages` | 在 message 里放 `file_id` / `input_file` 内容块 |
| `files.content()` 返回什么 | `file-extract` 文件返回抽取后的纯文本（`text/plain`），不是原始字节 | 返回原始文件字节 |
| 图片 / 视频 | `purpose="image"` / `"video"` 上传后，在 `image_url.url` / `video_url.url` 里写 `ms://<file_id>` | `image_url` 只接受 http(s)/data URL |
| Batch 支持的模型 | 仅 `kimi-k2.7-code`、`kimi-k2.6`；**不支持 `kimi-k3`** | 任意模型 |
| Batch 的采样参数 | `temperature` / `top_p` / `n` / `presence_penalty` / `frequency_penalty` **不可设置** | 随意设置 |
| `completion_window` | 语义化时长，最小 `12h`、最大 `7d`（如 `12h`、`24h`、`1d`、`3d`、`7d`） | 只能 `"24h"` |
| 定价 | 比实时调用节省 40%（文档原话） | 50% off |
| 文件 ID | 2026-08-31 起统一 `file_` 前缀 | `file-...` |

---

## 1. 我想让模型读一份文档（文件问答完整流程）

四步：**上传（purpose=file-extract）→ 取 content → 作为 system 消息放进 messages → 提问**。

关键点（文档反复强调）：放进 `messages` 的是**抽取后的文件内容**，不是 `file_id`。文件内容返回时"已经对齐了推荐的、模型易于理解的格式"；多文件时**每个文件单独一条 system 消息**，官方建议放在 messages 列表头部。

```python
import os
from pathlib import Path
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

def upload_files(paths: list[str]) -> list[dict]:
    """每个文件 -> 上传 -> 抽取 -> 一条 role=system 的消息"""
    messages = []
    for p in paths:
        file_object = client.files.create(file=Path(p), purpose="file-extract")
        # 旧版 SDK 用 client.files.retrieve_content(file_id=...)，新版已标 warning，改用 .content(...).text
        file_content = client.files.content(file_id=file_object.id).text
        messages.append({"role": "system", "content": file_content})
    return messages

file_messages = upload_files(["report.pdf", "notes.md"])

messages = [
    *file_messages,                       # 文件内容在前
    {"role": "system", "content": "你是 Kimi，由 Moonshot AI 提供的人工智能助手。"},
    {"role": "user", "content": "总结一下这些文件的内容。"},
]

completion = client.chat.completions.create(model="kimi-k3", messages=messages)
print(completion.choices[0].message.content)
```

curl 版：

```bash
curl https://api.moonshot.cn/v1/files -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -F purpose="file-extract" -F file="@report.pdf"          # -> {"id":"file_...", ...}
curl https://api.moonshot.cn/v1/files/$FILE_ID/content -H "Authorization: Bearer $MOONSHOT_API_KEY" -o report.txt
# 再把 report.txt 的内容作为一条 {"role":"system","content":"..."} 放进 /v1/chat/completions 的 messages
```

**最佳实践（来自文档）**

- 抽取结果可以**本地缓存**：下次问同一份文件时不必再上传 + 抽取。
- 单用户最多 1000 个文件，抽取完就**定期清理**：`for f in client.files.list().data: client.files.delete(file_id=f.id)`。
- 文件解析服务"限时免费"，高峰期可能限流。
- 文件问答指南的步骤 2 写的是"通过文件抽取接口 `/v1/files/{file_id}`"，但代码与 OpenAPI 都是 `/v1/files/{file_id}/content`；`GET /v1/files/{file_id}` 只返回元数据。`⚠ 文档自相矛盾`（几乎肯定是笔误，以 `/content` 为准）。
- 上传后是否要等待 `status` 变为某个值才能取 content：`⚠ 文档未说明`（所有示例都是上传后立刻取 content）。

---

## 2. 我想让模型看图片 / 视频（purpose=image / video）

和文档问答是**两条完全不同的路径**：

| | 文档（file-extract） | 图片 / 视频（image / video） |
|---|---|---|
| 上传 `purpose` | `file-extract` | `image` / `video` |
| 是否走 `/content` | 是，取抽取文本 | **否**——图片/视频的内容端点不可用（Hosted Agents 规范原话） |
| 进入对话的形式 | 抽取文本作为 `system` 消息 | `file_id` 以 `ms://<file_id>` 形式放进 user 消息的内容块 |
| 内容块类型 | 纯字符串 content | `{"type":"image_url","image_url":{"url":"ms://file_..."}}` / `{"type":"video_url","video_url":{"url":"ms://file_..."}}` |
| 2026-08-31 起 | 图片**不再做 OCR**；用 `file-extract` 传图片不再支持 | 由模型原生理解 |

```python
img = client.files.create(file=open("photo.png", "rb"), purpose="image")
completion = client.chat.completions.create(
    model="kimi-k3",   # 需支持视觉的模型
    messages=[{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"ms://{img.id}"}},
        {"type": "text", "text": "描述这张图片"},
    ]}],
)
```

- 也可以不上传，直接用 `data:image/png;base64,...` / `data:video/mp4;base64,...` 内嵌；上传 + `ms://` 适合大文件或多次复用。`video_url` 是 Kimi 扩展的内容块类型，OpenAI SDK 原样透传。
- 图片 / 视频的格式、尺寸、时长限制：`⚠ 文档未说明`（本次材料未含视觉模型指南 `/docs/guide/use-kimi-vision-model`；`ms://` 写法取自 Batch 指南的 chat body，实时调用 body 结构相同）。

---

## 3. Files 端点参考

所有 Files 端点：`Authorization: Bearer $MOONSHOT_API_KEY`；成功 200；401 鉴权失败；500 服务端错误；带 `{file_id}` 的端点 404 表示文件不存在。错误体统一为 `{"error": {"message", "type", "code"}}`。

**全局限制（files-upload 页）**：单用户最多 **1000 个文件**；单文件 **≤ 100MB**、不能为空；所有文件总容量 **≤ 10G**。

**2026-08-31 更新**：新文件 ID 统一 `file_` 前缀；同名文件服务端自动重命名（如 `report (1).txt`）；图片不再 OCR；上传后的文件不可修改。

**关于 `kimi-api-version` 头**：files-upload 页内嵌的是 **Hosted Agents 规范（`2026-09-01-beta`）**，它声明：不带 `kimi-api-version` 头时 `/v1/files*` 走**兼容行为**——上传/删除返回 200（而非 201/204），文件记录使用 `status` / `status_details`（而非 `extract_status`）。本文按**不带该头**的兼容行为（即主 OpenAPI）描述；若你带了 `kimi-api-version: 2026-09-01-beta`，响应变为 201、字段变为 `mime_type` / `size_bytes` / `created_at`(RFC3339 字符串) / `extract_status`(`ready` | `error`)。

### 3.1 上传文件

**Endpoint**: `POST /v1/files`（`multipart/form-data`）

**用途**: 把文件传到 Kimi 侧，供文本抽取（file-extract）、视觉理解（image / video）或批处理输入（batch）。它只是"放上去"；文档要进对话还得走 3.5 取内容。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `file` | binary | 是 | — | 文件字节；须携带文件名 |
| `purpose` | string | 是（主 OpenAPI）| — | 枚举见下表 |
| `filename` | string | 否 | 文件部分自身的名字 | 显式覆盖文件名，maxLength 4096。**仅 Hosted Agents 规范提到**，主 OpenAPI 无此字段 |

`purpose` 枚举（`⚠ 文档自相矛盾`：主 OpenAPI 与 Hosted Agents 规范都只列 4 个值；errors 页的报错文案列了 6 个）：

| 值 | 用途 | 限制 / 说明 | 出处 |
|---|---|---|---|
| `file-extract` | 抽取文本类文件内容（pdf/doc/txt/…）供模型使用；文档（含表格、公式）解析为模型友好格式 | **不支持图片**（2026-08-31 起）；支持格式：`.pdf .txt .csv .doc .docx .xls .xlsx .ppt .pptx .md .dot .epub .html .json .mobi .log .go .h .c .cpp .cxx .cc .cs .java .js .css .jsp .php .py .py3 .asp .yaml .yml .ini .conf .ts .tsx` 等 | OpenAPI + files-upload |
| `image` | 上传图片供视觉理解 | 跳过文档解析，不做 OCR；`/content` 不可用；只有检测为图片的文件才会做媒体处理 | OpenAPI + files-upload |
| `video` | 上传视频供视频理解 | 同上 | OpenAPI + files-upload |
| `batch` | 上传 JSONL 作为批处理输入 | 必须 `.jsonl`、非空、≤ 100MB；每组织最多 **1000 个 batch 类型文件**；`/content` 返回上传的文件（服务端规范化后字节可能与原文件不同）；只有上传者本人可读/删；不能挂载到会话 | OpenAPI + batch-create + Hosted Agents |
| `batch_output` | 仅在 errors 页 `Invalid purpose` 报错文案中出现 | 推测是 Batch 输出/错误文件的 purpose，`⚠ 文档未说明` 能否由用户主动上传 | errors |
| `lambda` | 仅在 errors 页报错文案中出现 | 用途 `⚠ 文档未说明` | errors |

Hosted Agents 规范另说 `purpose` "默认为 `file-extract`"（即可省略），主 OpenAPI 标为必填。`⚠ 文档自相矛盾`——保险做法：永远显式传。

**示例请求**
```bash
curl https://api.moonshot.cn/v1/files \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -F purpose="file-extract" \
  -F file="@xlnet.pdf"
```
```python
from pathlib import Path
file_object = client.files.create(file=Path("xlnet.pdf"), purpose="file-extract")
# 也可以 file=open("xlnet.pdf", "rb")
print(file_object.id)
```

**示例响应**（主 OpenAPI，兼容模式）
```json
{
  "id": "file_...",
  "object": "file",
  "bytes": 123456,
  "created_at": 1756600000,
  "filename": "xlnet.pdf",
  "purpose": "file-extract",
  "status": "...",
  "status_details": "..."
}
```

- `status`：文件处理状态，主 OpenAPI **未给枚举**（`⚠ 文档未说明`）；Hosted Agents 规范的对应字段 `extract_status` 为 `ready` | `error`（`error` = 文档解析失败，文件仍可见、可删除）。
- `status_details`：处理失败或有警告时的详情，可能缺省。
- 带 `kimi-api-version` 头时示例：`{"id":"file_01h455vb4pex5vsknk084sn02q","filename":"report.txt","mime_type":"text/plain","size_bytes":15,"created_at":"2026-08-26T12:00:00.000Z","purpose":"file-extract","extract_status":"ready"}`，HTTP 201。

**注意事项**

- 400 常见文案：`Invalid purpose: xxx, only ...accepted`、`File size is too large, max file size is 100MB...`、`File size is zero...`、上传总数超上限；`error.type` 均为 `invalid_request_error`。
- 图片走 `file-extract` 会失败或没有内容（不再 OCR），用 `image`。
- 同名不会报错，会被服务端重命名，靠 `id` 而不是 `filename` 来区分。
- 上传是否同步完成解析、`status` 何时变化：`⚠ 文档未说明`。
- OpenAI Python SDK 的 `purpose` 类型标注是 OpenAI 的枚举，传 `"file-extract"` 只是静态类型告警，运行时正常透传。

### 3.2 列出文件

**Endpoint**: `GET /v1/files`

**用途**: 列出当前用户上传的所有文件（主要用于配额清理）。与 3.3 的区别：这是全量列表，3.3 查单个。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| （无） | | | | OpenAPI 未定义任何 query 参数；**是否分页、能否按 `purpose` 过滤：`⚠ 文档未说明`** |

**示例请求**
```bash
curl https://api.moonshot.cn/v1/files -H "Authorization: Bearer $MOONSHOT_API_KEY"
```
```python
file_list = client.files.list()
for f in file_list.data:
    print(f.id, f.filename, f.purpose, f.status)
```

**示例响应**
```json
{"object": "list", "data": [{"id": "file_...", "object": "file", "bytes": 123456, "created_at": 1756600000,
  "filename": "xlnet.pdf", "purpose": "file-extract", "status": "...", "status_details": "..."}]}
```

**注意事项**

- 顶层 `object` 的取值 OpenAPI 只标 string（`"list"` 是 OpenAI 惯例）；OpenAI SDK 会把 `purpose=` 等参数透传成 query，Kimi 是否理会：均 `⚠ 文档未说明`。
- 1000 个文件的上限达到后上传会 400；用这个接口配合 3.4 清理。

### 3.3 获取文件信息

**Endpoint**: `GET /v1/files/{file_id}`

**用途**: 查单个文件的元数据（状态、大小、purpose）。**不返回内容**——内容在 3.5。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `file_id` | string (path) | 是 | — | 文件 ID |

**示例请求**
```bash
curl https://api.moonshot.cn/v1/files/$FILE_ID -H "Authorization: Bearer $MOONSHOT_API_KEY"
```
```python
meta = client.files.retrieve(file_id=file_object.id)
print(meta.status, meta.status_details)
```

**示例响应**：与 3.1 的单文件对象相同（`id / object / bytes / created_at / filename / purpose / status / status_details`）。

**注意事项**

- 404 的 `error.type` 为 `resource_not_found_error`。若想用它轮询"解析完成"，需要 `status` 的枚举，主 OpenAPI 未给出（`⚠ 文档未说明`）。

### 3.4 删除文件

**Endpoint**: `DELETE /v1/files/{file_id}`

**用途**: 释放配额（1000 个 / 10G）。
**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `file_id` | string (path) | 是 | — | 文件 ID |

**示例请求**
```bash
curl -X DELETE https://api.moonshot.cn/v1/files/$FILE_ID -H "Authorization: Bearer $MOONSHOT_API_KEY"
```
```python
resp = client.files.delete(file_id=file_object.id)
print(resp.deleted)
```

**示例响应**
```json
{"id": "file_...", "object": "file", "deleted": true}
```

**注意事项**

- `object` 的取值 OpenAPI 只标 string（`⚠ 文档未说明`，OpenAI 惯例是 `"file"`）。兼容模式返回 200；带 `kimi-api-version` 头时返回 204（无 body）。
- Hosted Agents 规范："文件删除后，仍可能残留在活跃会话的工具调用中"。删除 batch 输入文件是否影响进行中的 batch：`⚠ 文档未说明`。

### 3.5 获取文件内容

**Endpoint**: `GET /v1/files/{file_id}/content`

**用途**: 对 `file-extract` 文件，返回**抽取后的文本**（这是文件问答的核心一步）；对 `batch` 文件，返回 JSONL 本身；Batch 的 `output_file_id` / `error_file_id` 也用这个端点下载。图片 / 视频不可用。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `file_id` | string (path) | 是 | — | 文件 ID |

**示例请求**
```bash
curl https://api.moonshot.cn/v1/files/$FILE_ID/content -H "Authorization: Bearer $MOONSHOT_API_KEY" -o content.txt
```
```python
text = client.files.content(file_id=file_object.id).text          # file-extract：抽取文本
lines = client.files.content(batch.output_file_id).text.strip().split("\n")   # batch 输出：JSONL
# 裸 HTTP
import requests, os
r = requests.get(f"https://api.moonshot.cn/v1/files/{file_object.id}/content",
                 headers={"Authorization": f"Bearer {os.environ['MOONSHOT_API_KEY']}"})
r.raise_for_status(); text = r.text
```

**示例响应**：主 OpenAPI 标 `200 text/plain`，无结构化字段；body 就是抽取后的文本（或 JSONL）。

**注意事项**

- `⚠ 文档自相矛盾`：Hosted Agents 规范说 file-extract 的内容端点"返回一个携带解析出的 Markdown 的 **JSON 对象**"，主 OpenAPI 与所有示例代码都是 `text/plain` 直接 `.text` 使用。可能与 `kimi-api-version` 头有关；不带头时按 `text/plain` 处理，若拿到 JSON 再解析。
- 对 `image` / `video` 文件调用：不可用（Hosted Agents 规范），具体 HTTP 状态、内容大小上限、是否分页：`⚠ 文档未说明`。
- 旧版 SDK 的 `files.retrieve_content()` 已标 warning，用 `files.content(...).text`。

---

## 4. 我想低成本跑一大批离线请求（Batch 完整流程）

适合大规模、低实时性任务；文档承诺比实时调用**节省 40%** 推理费用。

**硬性前提（创建前先核对）**

- 模型：只能 `kimi-k2.7-code` 或 `kimi-k2.6`；`kimi-k3` 不支持；`kimi-k2.7-code-highspeed` 是否支持 `⚠ 文档未说明`。
- 同一个文件里**所有行 `model` 必须相同**。
- body 里**不要写** `temperature` / `top_p` / `n` / `presence_penalty` / `frequency_penalty`（这些模型在 Batch 下不可修改）。写了会怎样（忽略 or 校验失败）：`⚠ 文档未说明`。
- `endpoint` / 每行 `url` 只能是 `/v1/chat/completions`。
- 输入文件：`.jsonl` 扩展名、非空、≤ 100MB、`purpose="batch"`；每组织最多 1000 个 batch 类型文件。与单用户 1000 个文件的关系、单文件最大行数、并发 batch 数：`⚠ 文档未说明`。

**输入 JSONL 行格式**（四个字段全部必填）

```json
{"custom_id": "request-1", "method": "POST", "url": "/v1/chat/completions", "body": {"model": "kimi-k2.6", "messages": [{"role": "system", "content": "你是一个文本分类助手"}, {"role": "user", "content": "请分类这段文本：人工智能正在改变世界"}]}}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `custom_id` | 是 | 文件内唯一，用于对应结果 |
| `method` | 是 | 固定 `POST` |
| `url` | 是 | 固定 `/v1/chat/completions` |
| `body` | 是 | 与 Chat Completions 请求体一致（除上述禁用参数） |

**多模态行**：`body.messages[].content` 用内容块数组，图片 `{"type":"image_url","image_url":{"url": "data:image/png;base64,..." 或 "ms://<file_id>"}}`，视频 `{"type":"video_url","video_url":{"url": "data:video/mp4;base64,..." 或 "ms://<file_id>"}}`；`ms://` 引用的文件需先以 `purpose="image"` / `"video"` 上传。base64 会膨胀约 33%，注意 100MB 上限。

**端到端脚本**

```python
import json, os, time
from pathlib import Path
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")
MODEL = "kimi-k2.6"

# 1. 构造输入
reqs = [{"custom_id": f"text_{i}", "method": "POST", "url": "/v1/chat/completions",
         "body": {"model": MODEL, "messages": [{"role": "user", "content": f"请分类：{t}"}]}}
        for i, t in enumerate(["哈姆雷特", "宜居行星", "红烧肉做法"])]
path = Path("requests.jsonl")
path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in reqs), encoding="utf-8")

# 2. 上传（purpose=batch）
file_object = client.files.create(file=path, purpose="batch")

# 3. 创建任务
batch = client.batches.create(input_file_id=file_object.id,
                              endpoint="/v1/chat/completions",
                              completion_window="24h")

# 4. 轮询（建议 10-60s 一次）
while True:
    batch = client.batches.retrieve(batch.id)
    print(batch.status, batch.request_counts.completed, "/", batch.request_counts.total)
    if batch.status == "completed":
        break
    if batch.status in ("failed", "expired", "cancelled"):
        raise SystemExit(f"终止: {batch.status}")
    time.sleep(10)

# 5. 取结果 / 错误
for line in client.files.content(batch.output_file_id).text.strip().split("\n"):
    d = json.loads(line)
    print(d["custom_id"], d["response"]["body"]["choices"][0]["message"]["content"])
if batch.error_file_id:
    print(client.files.content(batch.error_file_id).text)
```

**状态机（8 个状态）**

- 主线：`validating`（已创建，异步校验输入）→ `in_progress`（执行中）→ `finalizing`（准备结果）→ `completed`（终态）
- 分支：校验失败 → `failed`（终态）；未在 `completion_window` 内完成 → `expired`（终态）
- 取消：`validating` / `in_progress` / `finalizing` 下调用 cancel → `cancelling` → `cancelled`（终态）
- 轮询时终态集合：`completed` / `failed` / `expired` / `cancelled`

**输出文件行格式**（每行一个请求的结果）

```json
{"id": "request-1", "custom_id": "request-1",
 "response": {"status_code": 200, "request_id": "",
   "body": {"id": "chatcmpl-xxx", "object": "chat.completion", "created": 1711475054, "model": "kimi-k2.6",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "这段文本属于科技类。"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40}}},
 "error": null}
```

- 输出行是否保持输入顺序：`⚠ 文档未说明`，按 `custom_id` 对齐。`error_file_id` 里每行的格式：`⚠ 文档未说明`（只说"包含错误文件 ID"）。
- `expired` / `cancelled` 时已完成的部分是否产出 `output_file_id`、是否计费；40% 折扣如何体现、Batch 是否有独立的 RPM/TPM 限制：`⚠ 文档未说明`。
- 输出文件的 `purpose`：推测为 errors 页出现的 `batch_output`；它是否计入 1000 个文件配额、保留多久：`⚠ 文档未说明`。

---

## 5. Batch 端点参考

Batch 对象字段（4 个端点返回同一结构）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 任务 ID |
| `object` | string | 固定 `batch` |
| `endpoint` | string | `/v1/chat/completions` |
| `input_file_id` | string | 输入文件 ID |
| `completion_window` | string | 创建时传入的时间窗口 |
| `status` | string | 8 个状态见第 4 节 |
| `output_file_id` | string \| null | 成功结果文件 |
| `error_file_id` | string \| null | 失败请求的错误文件 |
| `created_at` | integer | Unix 秒 |
| `in_progress_at` / `expires_at` / `finalizing_at` / `completed_at` / `failed_at` / `cancelling_at` / `cancelled_at` | integer \| null | 各阶段时间戳 |
| `request_counts.total` / `.completed` / `.failed` | integer | 请求计数 |
| `metadata` | object \| null | 自定义元数据 |

### 5.1 创建批处理任务

**Endpoint**: `POST /v1/batches`（`application/json`）

**用途**: 用一个已上传的 `purpose="batch"` JSONL 文件创建异步任务。与实时 `/v1/chat/completions` 的区别：异步、便宜 40%、模型与采样参数受限。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `input_file_id` | string | 是 | — | 必须是 `purpose="batch"` 上传的 `.jsonl` |
| `endpoint` | string | 是 | — | 枚举：仅 `/v1/chat/completions` |
| `completion_window` | string | 是 | — | 语义化时长：`12h`、`1d`、`3d`… 最小 `12h`，最大 `7d`；示例用 `24h`；大数据集建议 `3d` / `7d` |
| `metadata` | object | 否 | — | 最多 16 个键值对，key ≤ 64 字符，value ≤ 512 字符，值为 string |

**示例请求**
```bash
curl https://api.moonshot.cn/v1/batches \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input_file_id": "'"$FILE_ID"'", "endpoint": "/v1/chat/completions", "completion_window": "24h", "metadata": {"job": "classify"}}'
```
```python
batch = client.batches.create(
    input_file_id=file_object.id,
    endpoint="/v1/chat/completions",
    completion_window="24h",       # SDK 类型标注是 Literal["24h"]，传 "3d" 只是静态告警，运行时透传
    metadata={"job": "classify"},
)
```

**示例响应**
```json
{"id": "...", "object": "batch", "endpoint": "/v1/chat/completions", "input_file_id": "file_...", "completion_window": "24h",
 "status": "validating", "output_file_id": null, "error_file_id": null, "created_at": 1756600000, "expires_at": 1756686400,
 "request_counts": {"total": 0, "completed": 0, "failed": 0}, "metadata": {"job": "classify"}}
```
（其余时间戳字段见第 5 节表；batch `id` 前缀、创建时 `request_counts.total` 是否已知：`⚠ 文档未说明`。）

**注意事项**

- 校验是**异步**的：创建返回 200 不代表文件合法，要等 `validating` → `in_progress` 或 `failed`。校验失败的具体原因写在哪（响应 body？error 文件？）`⚠ 文档未说明`。
- `completion_window` 超出 `12h`–`7d` 或格式不对 → 400。
- 时间窗口越长完成率越高（文档建议）。
- `expires_at` 由服务端按 `completion_window` 计算。

### 5.2 获取任务详情

**Endpoint**: `GET /v1/batches/{batch_id}`

**用途**: 轮询状态、拿 `output_file_id` / `error_file_id`。
**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `batch_id` | string (path) | 是 | — | 任务 ID |

**示例请求**
```bash
curl https://api.moonshot.cn/v1/batches/$BATCH_ID -H "Authorization: Bearer $MOONSHOT_API_KEY"
```
```python
batch = client.batches.retrieve(batch_id)
```

**示例响应**：完整 Batch 对象（同 5.1）。

**注意事项**

- 404 → 任务不存在。
- 轮询间隔建议 10–60 秒。
- `request_counts` 在 `validating` 阶段是否有值：文档示例做了 `if batch.request_counts else 0` 的防御，暗示可能为空（`⚠ 文档未说明`，OpenAPI 标为 required）。

### 5.3 列出批处理任务

**Endpoint**: `GET /v1/batches`

**用途**: 分页列出当前组织的任务（注意：是**组织**级，不是单用户）。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `after` | string (query) | 否 | — | 分页游标，传上一页最后一个 batch 的 `id` |
| `limit` | integer (query) | 否 | 20 | 每页数量；最大值 `⚠ 文档未说明` |

**示例请求**
```bash
curl "https://api.moonshot.cn/v1/batches?limit=10" -H "Authorization: Bearer $MOONSHOT_API_KEY"
```
```python
page = client.batches.list(limit=10)
for b in page.data:
    print(b.id, b.status, b.request_counts.completed, "/", b.request_counts.total)
# 下一页：client.batches.list(limit=10, after=page.data[-1].id)
```

**示例响应**
```json
{"object": "list", "data": [ { ...Batch 对象... } ], "has_more": false}
```

**注意事项**

- OpenAI SDK 的 `SyncCursorPage` 自动翻页依赖 `has_more` + 最后一个 `id`，与这里的 `after` 语义一致。是否支持按 `status` 过滤、排序方式：`⚠ 文档未说明`。

### 5.4 取消批处理任务

**Endpoint**: `POST /v1/batches/{batch_id}/cancel`

**用途**: 取消进行中的任务。只有 `validating` / `in_progress` / `finalizing` 可取消；其余状态返回 400。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `batch_id` | string (path) | 是 | — | 任务 ID |
| （body） | — | 否 | — | 无请求体 |

**示例请求**
```bash
curl -X POST https://api.moonshot.cn/v1/batches/$BATCH_ID/cancel -H "Authorization: Bearer $MOONSHOT_API_KEY"
```
```python
batch = client.batches.cancel(batch_id)
print(batch.status)   # cancelling
```

**示例响应**：Batch 对象，`status` 为 `cancelling`（随后异步变为 `cancelled`），`cancelling_at` 有值。

**注意事项**

- 取消是异步的：返回时是 `cancelling`，要再轮询到 `cancelled`。
- 400 = 状态不允许取消（已 `completed` / `failed` / `expired` / `cancelled` / `cancelling`）。
- 取消前已完成的请求是否计费、是否产出部分结果：`⚠ 文档未说明`。

---

## 6. 文件相关错误速查 + 文档矛盾汇总

错误体：`{"error": {"message": "...", "type": "...", "code": "..."}}`（`code` 可能缺省）。

| HTTP | `error.type` | 典型 message | 处理 |
|---|---|---|---|
| 400 | `invalid_request_error` | `Invalid purpose: xxx, only file-extract, batch, batch_output, lambda, image and video accepted` | `purpose` 拼错（如用了 OpenAI 的 `assistants`） |
| 400 | `invalid_request_error` | `File size is too large, max file size is 100MB, please confirm and re-upload the file` | 拆分 / 压缩 |
| 400 | `invalid_request_error` | `File size is zero, please confirm and re-upload the file` | 文件为空 |
| 400 | `invalid_request_error` | （上传文件总数超过上限） | 用 `GET /v1/files` + `DELETE` 清理（上限 1000） |
| 400 | — | Batch 参数无效 / 状态不允许取消 | 见 5.1 / 5.4 |
| 401 | `invalid_authentication_error` / `incorrect_api_key_error` | Invalid Authentication / Incorrect API key provided | 检查 Key；中国站与国际站 Key 不通用 |
| 404 | `resource_not_found_error` | — | `file_id` / `batch_id` 不存在 |
| 429 / 500 | `rate_limit_reached_error` / `server_error` | — | 文件解析高峰期可能限流；退避重试 |

Batch 校验失败（`status=failed`）的常见原因（batch-create 页限制表）：非 `.jsonl` 扩展名、空文件或 > 100MB、组织 batch 文件超 1000、同批多个模型、`custom_id` 重复、模型不存在或无权限。这些是在 `validating` 阶段异步暴露还是创建时同步 400：`⚠ 文档未说明`。

---

**⚠ 文档自相矛盾（汇总，详见各小节）**：(1) `purpose` 枚举 4 值（两份 OpenAPI）vs 6 值（errors 页文案）；(2) `purpose` 必填（主 OpenAPI）vs 可省略默认 `file-extract`（Hosted Agents 规范）；(3) file-extract 的 `/content` 返回 `text/plain`（主 OpenAPI + 示例）vs "携带 Markdown 的 JSON 对象"（Hosted Agents 规范）；(4) 文件问答指南把内容抽取接口写成 `/v1/files/{file_id}`，实为 `/v1/files/{file_id}/content`；(5) 文件对象两套字段集（`bytes/status` vs `size_bytes/extract_status`），规范称由 `kimi-api-version` 头决定。
