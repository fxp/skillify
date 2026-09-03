# 视觉输入与文件 API

> 状态：文档草稿，基于 2026-09-03 抓取的 platform.moonshot.cn/docs 官方文档 + /docs/openapi.json 撰写，**尚未用真实 API 调用验证**。

本文覆盖三件事，它们在官方文档里分散在四个页面，但开发者的问题通常是同一个："我怎么把图片 / 视频 / PDF 喂给 Kimi？"

| 我想做什么 | 用哪条路 | 关键点 |
|---|---|---|
| 让模型看一张本地图片 | `chat/completions` + `image_url` = base64 data URL | **不支持公网 http(s) 图片 URL** |
| 让模型看视频 / 大图 / 多次复用的图 | 先 `POST /v1/files`（`purpose=image` 或 `video`），再用 `ms://<file_id>` 引用 | 请求体总大小 ≤ 100M，视频必须走上传 |
| 基于 PDF/Word/代码文件问答 | `POST /v1/files`（`purpose=file-extract`）→ `GET /v1/files/{id}/content` 取纯文本 → 塞进 `system` 消息 | 放**文件内容**，不是 file_id；图片不能 file-extract |
| 批量离线推理的输入 | `POST /v1/files`（`purpose=batch`） | 见 `batch.md` |

---

## 1. 图片 / 视频输入（Vision）

支持视觉的模型：`kimi-k3`、`kimi-k2.6`、`kimi-k2.7-code`、`kimi-k2.7-code-highspeed`（文档原文如此，全部在线模型都支持视觉）。

### 消息格式

用视觉能力时 `message.content` **必须是对象数组**，不能把数组序列化成字符串塞进 `content`：

```json
{"role": "user", "content": [
  {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
  {"type": "text", "text": "请描述这个图片"}
]}
```

内容块类型（OpenAPI `Message.content` 的 oneOf）：
| type | 字段 | 说明 |
|---|---|---|
| `text` | `text` | 文字 |
| `image_url` | `image_url.url`（也接受直接给字符串） | base64 data URL，或 `ms://<file_id>` |
| `video_url` | `video_url.url`（也接受直接给字符串） | `ms://<file_id>`（视频要先上传） |

### base64 直接传图（Python）

```python
import os, base64
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

image_path = "kimi.png"
with open(image_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()
ext = os.path.splitext(image_path)[1].lstrip(".")          # png / jpeg / webp ...
image_url = f"data:image/{ext};base64,{b64}"

completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[
        {"role": "system", "content": "你是 Kimi。"},
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": image_url}},
            {"type": "text", "text": "请描述图片的内容。"},
        ]},
    ],
)
print(completion.choices[0].message.content)
```

### 上传后用 `ms://<file_id>` 引用（视频 / 大文件 / 复用）

```python
from pathlib import Path
file_object = client.files.create(file=Path("video.mp4"), purpose="video")   # 图片用 purpose="image"

completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[{"role": "user", "content": [
        {"type": "video_url", "video_url": {"url": f"ms://{file_object.id}"}},  # ms = moonshot storage
        {"type": "text", "text": "请描述这个视频"},
    ]}],
)
```

curl 等价：
```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"kimi-k3","messages":[{"role":"user","content":[
        {"type":"image_url","image_url":{"url":"ms://file_xxx"}},
        {"type":"text","text":"请描述这个图片"}]}]}'
```

### 格式与限制（来源: docs/guide/use-kimi-vision-model）

- 图片 MIME：jpeg、png、gif、webp、bmp、heic、heif。**GIF/WebP 动图会按视频解码、按视频计 token**。
- **SVG 不支持**：无论 `purpose=image` 上传还是 base64 传 `image_url` 都会被拒绝；要理解 SVG 请把 SVG 源码当文本传。
- 视频 MIME：mp4、mpeg、mov、avi、x-flv、mpg、webm、wmv、3gpp。
- **不支持 URL 形式的图片**——只接受 base64 与 `ms://` 文件 ID（K3 quickstart 也重申：视觉输入不支持公网图片 URL）。
- 图片数量无上限，但整个请求 Body ≤ 100M；非常大的视频必须走文件上传。
- 推荐分辨率：图片 ≤ 4096×2160，视频 ≤ 1080p；更高分辨率只增加耗时和 token，不提升效果。
- token 按分辨率 / 关键帧数动态计算；可先用 `POST /v1/tokenizers/estimate-token-count` 预估（见 `errors-and-limits.md`）。
- Vision 支持多轮、流式、工具调用、JSON Mode、Partial Mode。
- 不要手动设置 `temperature` / `top_p` / `n`（各模型固定值不同，见 `models.md`）。

来源: docs/guide/use-kimi-vision-model, docs/guide/kimi-k3-quickstart（重要限制节）, schema Message.content

---

## 2. Files API

所有文件接口共用一个文件对象：

```json
{"id": "file_xxx", "object": "file", "bytes": 12345, "created_at": 1720000000,
 "filename": "xlnet.pdf", "purpose": "file-extract", "status": "ok", "status_details": ""}
```
（`status` 字符串取值文档未枚举；`status_details` 在失败/警告时出现。2026-08-31 起新文件 ID 统一带 `file_` 前缀。）

### 上传文件
**Endpoint**: `POST /v1/files`（multipart/form-data）
**用途**: 上传用于内容抽取、图片/视频理解或 Batch 输入的文件。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | file | 是 | 文件本体 |
| `purpose` | string | 是 | `file-extract`（文本类抽取，**不支持图片**）/ `image` / `video` / `batch`（.jsonl） |

```bash
curl https://api.moonshot.cn/v1/files \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -F purpose="file-extract" -F file="@xlnet.pdf"
```
```python
from pathlib import Path
file_object = client.files.create(file=Path("xlnet.pdf"), purpose="file-extract")
print(file_object.id, file_object.status)
```

**注意事项**（来源: docs/api/files-upload）
- 配额：每用户最多 1000 个文件，单文件 ≤ 100MB，总量 ≤ 10G。文件解析限时免费，高峰期可能限流。
- `file-extract` 支持格式：`.pdf .txt .csv .doc .docx .xls .xlsx .ppt .pptx .md .dot .epub .html .json .mobi .log` 及 `.go .h .c .cpp` 等常见源码后缀（完整列表见原页面）。
- 2026-08-31 起**图片不再做 OCR 抽取**，`file-extract` 传图片会失败；图片理解走 `purpose="image"` + `ms://`。
- 同名文件上传时服务端自动重命名，不报错。

### 文件列表 / 获取 / 删除 / 取内容

| 功能 | Endpoint | 返回 |
|---|---|---|
| 列表 | `GET /v1/files` | `{"object": "list", "data": [FileObject...]}`（文档未描述分页参数） |
| 元数据 | `GET /v1/files/{file_id}` | FileObject；404 表示不存在 |
| 删除 | `DELETE /v1/files/{file_id}` | `{"id","object","deleted": true}` |
| 抽取内容 | `GET /v1/files/{file_id}/content` | **`text/plain` 纯文本**（仅对 `purpose=file-extract` 的文件有意义；Batch 结果文件也从这里下载） |

```python
files = client.files.list()
meta = client.files.retrieve(file_object.id)
text = client.files.content(file_object.id).text      # 旧 SDK 用 files.retrieve_content()
client.files.delete(file_object.id)
```

来源: docs/api/files, files-list, files-retrieve, files-delete, files-content, schema/files

---

## 3. 基于文件问答（PDF/Word/代码）

官方推荐的**唯一**路径：上传 → 取抽取文本 → 把文本放进 `system` 消息 → 提问。

```python
import os
from pathlib import Path
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

file_object = client.files.create(file=Path("moonshot.pdf"), purpose="file-extract")
file_content = client.files.content(file_id=file_object.id).text   # 已对齐成模型易读格式

messages = [
    {"role": "system", "content": "你是 Kimi，由 Moonshot AI 提供的人工智能助手。"},
    {"role": "system", "content": file_content},        # <-- 文件内容本身，不是 file_id
    {"role": "user", "content": "请简单介绍 moonshot.pdf 的具体内容"},
]
completion = client.chat.completions.create(model="kimi-k3", messages=messages)
print(completion.choices[0].message.content)
```

多文件：每个文件单独一条 `system` 消息，全部放在对话最前面（`[*file_messages, system_prompt, user]`）。

要点（来源: docs/guide/use-kimi-api-for-file-based-qa）：
- 放**内容**不放 `file_id`——Chat API 不认识 file_id，不会自动去读文件。
- 抽取出来的文档内容按输入 token 计费（来源: docs/pricing/chat）。
- 多个大文件时注意上下文窗口（K3 1M / K2.x 256K），可结合上下文缓存降低重复成本（见 `chat-completions.md`）。
- 想让模型"看"扫描件/图片里的文字：不能 file-extract，改走 Vision（`purpose=image` + `ms://`）。

---

## 待验证疑点

- **[文档自相矛盾] `docs/api/files-upload` 的 Python 示例对 `kimi-k3` 传了 `temperature=0.6`**，而 `docs/api/models-overview` 明确说 K3 的 temperature 固定 1.0、"传入其他值会报错"。需实测：传 0.6 是报错、被忽略、还是生效？
- `GET /v1/files/{file_id}/content` 对 `purpose=image/video` 的文件返回什么（404？空？二进制？），文档未说明。
- 文件对象 `status` 的枚举值（`ok`? `processing`? `error`?）文档未列；上传大 PDF 时是同步返回抽取完成还是需要轮询，未说明。
- `GET /v1/files` 是否支持分页（`after`/`limit`），schema 没有查询参数；1000 个文件时是否一次全返回。
- Vision 文档说所有在线模型都支持视频输入；K2.7 Code quickstart 是否也支持 `video_url`，需实测。
- 公网图片 URL "不支持"是报错（哪个 error code）还是静默失败，需实测并记下报错原文。
- `image_url` 直接给字符串（schema oneOf[1]）与给 `{"url": ...}` 对象是否都被接受。
- GIF/WebP "按视频计费" 的具体 token 差异未量化，可用 estimate-token-count 对比。
- 请求 Body 100M 上限是文档值，实际网关限制（以及超限时的报错）需实测。
- `file-extract` 完整支持后缀列表在原页面被截断，导出时需核对原页面。
