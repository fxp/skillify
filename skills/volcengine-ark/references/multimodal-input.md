# 多模态输入：给模型喂图片 / 视频 / PDF 文档 / 音频（含 Files API）

本文只讲**输入侧**多模态理解：如何把图片、视频、PDF、音频放进 `messages[].content`（Chat Completions）或 `input[].content`（Responses API），每种 part 的精确 JSON 结构、大小 / 格式 / 张数限制、token 计算、Files API（上传后用 `file_id` 复用）、GUI Agent / Grounding 的坐标输出格式，以及多模态长会话的上下文建议。图片 / 视频 / 语音**生成**不在本文范围。

鉴权与 Base URL 见 `auth.md`：标准入口 `https://ark.cn-beijing.volces.com/api/v3`，`Authorization: Bearer $ARK_API_KEY`。本文所有教程页示例均基于标准入口。Agent Plan 入口的可用性见 §10（Files API **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`/api/plan/v3/files` 不存在，`file_id` 方式在 Plan 不可用）。

## 目录

1. [选型速查：模态 × 传入方式 × 两套 API 的 part 写法](#1-选型速查)
2. [哪些模型支持哪种输入（文档模型表）](#2-模型支持)
3. [图片输入](#3-图片输入)
4. [视频输入](#4-视频输入)
5. [PDF 文档输入](#5-pdf-文档输入)
6. [音频输入](#6-音频输入)
7. [Files API：上传 / 查询 / 列表 / 删除，file object](#7-files-api)
8. [GUI Agent 与视觉定位 Grounding（坐标输出格式）](#8-gui-agent-与-grounding)
9. [多模态长会话的上下文管理](#9-多模态长会话的上下文管理)
10. [三套入口下的可用性（标准 / Coding Plan / Agent Plan）](#10-三套入口下的可用性)
11. [常见报错与排查（文档原文，未实测）](#11-常见报错与排查)
12. [来源页面](#来源页面)

---

## 1. 选型速查

### 1.1 三种传入方式怎么选

| 方式 | 适用 | 图片 | 视频 | PDF | 音频 |
|---|---|---|---|---|---|
| 公网 URL | 文件已在公网 / TOS 上；文档建议放火山 TOS（内网直连、省时延和流量） | 单张 ≤ 10 MB | ≤ 50 MB | ≤ 50 MB | ≤ 25 MB，时长 ≤ 120 min |
| Base64 data URI（`data:{mime};base64,{data}`） | 小文件、不想开公网 | 单张 ≤ 10 MB，请求体 ≤ 64 MB | ≤ 50 MB，请求体 ≤ 64 MB | ≤ 50 MB，请求体 ≤ 64 MB | ≤ 25 MB，时长 ≤ 120 min |
| Files API 上传后用 `file_id`（推荐） | 大文件、多次请求复用、想把预处理（视频抽帧 / PDF 分页）和推理解耦 | ≤ 512 MB | 方舟托管存储 ≤ 512 MB；自有 TOS Bucket ≤ 2 GB | ≤ 512 MB | ≤ 512 MB |
| `file://本地路径`（仅 Python / Go 官方 SDK + Responses API，SDK 内部自动走 Files API） | 懒人模式 | ≤ 512 MB | ⚠ 文档仅在图片理解页提到 | ⚠ 同左 | ⚠ 同左 |

`file_id` 的先决条件：文件 `status` 必须已是 `active`（上传后先 `processing`，要轮询 `GET /files/{id}`）；`file_id` 对应的文件类型要和 part 的 `type` 一致；API Key 所属项目要和上传时一致。

### 1.2 两套 API 的 part 结构对照（字段名和嵌套层级都不同，别混用）

| 模态 | Chat Completions `messages[].content[]` | Responses API `input[].content[]` |
|---|---|---|
| 文本 | `{"type":"text","text":"..."}` | `{"type":"input_text","text":"..."}` |
| 图片 | `{"type":"image_url","image_url":{"url":"<URL 或 data URI>","detail":"high","image_pixel_limit":{...}}}` 或 `{"type":"image_url","image_url":{"file_id":"file-xxx"}}` | `{"type":"input_image","image_url":"<URL 或 data URI>","detail":"high","image_pixel_limit":{...}}` 或 `{"type":"input_image","file_id":"file-xxx"}` |
| 视频 | `{"type":"video_url","video_url":{"url":"<URL 或 data URI>","fps":1}}` 或 `{"type":"video_url","video_url":{"file_id":"file-xxx"}}` | `{"type":"input_video","video_url":"<URL 或 data URI>","fps":1}` 或 `{"type":"input_video","file_id":"file-xxx"}` |
| PDF | `{"type":"file","file":{"file_id":"file-xxx"}}` / `{"file_url":"..."}` / `{"file_data":"data:application/pdf;base64,...","filename":"a.pdf"}` | `{"type":"input_file","file_id":"file-xxx"}` / `{"type":"input_file","file_url":"..."}` / `{"type":"input_file","file_data":"data:application/pdf;base64,...","filename":"a.pdf"}` |
| 音频 | `{"type":"input_audio","input_audio":{"data":"<纯 base64，不带 data: 前缀>","format":"mp3"}}` 或 `{"input_audio":{"url":"...","format":"mp3"}}` 或 `{"input_audio":{"file_id":"file-xxx"}}` | `{"type":"input_audio","audio_url":"<URL 或 data:audio/mpeg;base64,...>"}` 或 `{"type":"input_audio","file_id":"file-xxx"}` |

要点：

- Chat API 的媒体字段是**对象**（`image_url: {url, detail, ...}`），Responses API 的媒体字段是**字符串**（`image_url: "..."`），`detail` / `fps` / `image_pixel_limit` 提到 part 顶层。
- 音频 Base64 在两套 API 里格式不同：Chat 用 `input_audio.data`（裸 base64）+ `input_audio.format`；Responses 用 `audio_url` 装 data URI。
- 图文混排顺序自由，可放在 system 或 user 消息里；文档建议"多图 + 一段文字"时把文字放在图片之后。
- Chat API 无状态：同一张图多轮问答，每轮都要重传（或复用 `file_id`）。Responses API 可用 `previous_response_id` 串接，见第 9 节。
- 视觉理解请求不支持 `frequency_penalty`、`presence_penalty`、`n`。

---

## 2. 模型支持

以下来自「模型列表」页（更新 2026-09-02），只列能力列，不要自行推断。

### 2.1 视觉理解（图片 / 视频 / PDF）

| Model ID | 能力列（文档原文） | 上下文 / 最大输入 | 备注 |
|---|---|---|---|
| `doubao-seed-evolving` | 深度思考、文本生成、多模态理解、工具调用、结构化输出 | 1024k / 1024k | 推荐，快速迭代模型 |
| `doubao-seed-2-1-pro-260628` | 同上 | 256k / 256k | 推荐；教程页默认示例模型 |
| `doubao-seed-2-1-turbo-260628` | 同上 | 256k / 256k | 推荐 |
| `doubao-seed-2-0-lite-260428` / `doubao-seed-2-0-mini-260428` | 同上 | 256k / 224k | 往期 |
| `doubao-seed-2-0-pro-260215` / `-lite-260215` / `-mini-260215` / `-code-preview-260215` | 多模态理解、**视觉定位**、… | 256k / 224k | 往期 |
| `doubao-seed-character-260628` | 多模态理解、… | 128k / 96k | 往期 |
| `doubao-seed-1-8-251228`、`doubao-seed-1-6-*`、`doubao-seed-code-preview-251028` | 多模态理解、视觉定位、… | 256k / 224k | `即将下线` |
| `doubao-seed-1-6-vision-250815` | 多模态理解、视觉定位、**GUI 任务处理** | 256k / 224k | `即将下线` |
| `doubao-1-5-vision-pro-32k-250115` | 图片理解、工具调用（无视频 / 思考） | 32k | `即将下线` |

⚠ 文档自相矛盾：Grounding 教程用 `doubao-seed-2-1-pro-260628` 输出 bbox，但模型列表里 2.1 系列能力列没有标"视觉定位"（只有 2.0-260215 及更早版本标了）。

### 2.2 音频理解

只有两款推荐模型：`doubao-seed-2-0-lite-260428`、`doubao-seed-2-0-mini-260428`（音频教程全部示例用 `doubao-seed-2-0-lite-260428`）。2.1 系列在音频理解表中**未列出**——不要拿 `doubao-seed-2-1-pro` 喂音频。

### 2.3 GUI 任务处理

模型列表只列了 `doubao-seed-1-6-vision-250815`（即将下线）。⚠ 文档自相矛盾：GUI Agent 教程写"支持模型：Doubao Seed 系列模型"，参考分数用 `doubao-seed-2.1-turbo` 跑出。

### 2.4 `file_id` 传入的模型范围

Chat API 与 Responses API 参考页均注明：通过 `file_id` 传文件仅以下模型支持——`doubao-seed-2.0-mini`（`260428` 及后续）、`doubao-seed-2.0-lite`（全版本）、`doubao-seed-2.0-pro`（全版本）。⚠ 文档自相矛盾：教程页所有 `file_id` 示例都用 `doubao-seed-2-1-pro-260628`，而参考页的支持列表里没有 2.1 系列。

---

## 3. 图片输入

### 图片理解（Chat / Responses）
**Endpoint**: `POST /api/v3/chat/completions` 或 `POST /api/v3/responses`
**用途**: 单图 / 多图问答、描述、分类、OCR、图文混排；Grounding / GUI 见第 8 节。

**关键参数**（图片 part）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| Chat `image_url.url` / Responses `image_url` | string | 与 `file_id` 二选一 | — | 公网 URL 或 `data:image/{格式};base64,{编码}`；格式声明须与实际一致且小写 |
| `file_id` | string | 与 url 二选一 | — | Files API 返回的 id，须 `active`；模型范围见 2.4 |
| `detail` | string | 否 | seed-1.8 之前 `low`；seed-1.8 及以后 `high` | Chat 参考页可选值 `low` / `high` / `xhigh`；Responses 参考页可选值 `auto` / `low` / `high` / `xhigh`（`auto` 在 Chat 页未列出，⚠ 文档未说明 Chat 是否接受） |
| `image_pixel_limit.max_pixels` | integer | 否 | 随 `detail` | 大于则等比缩小。seed-1.8 之前最大 `4014080`；seed-1.8 / 2.0 最大 `9031680` |
| `image_pixel_limit.min_pixels` | integer | 否 | 随 `detail` | 小于则等比放大。seed-1.8 之前最小 `3136`；seed-1.8 / 2.0 最小 `1764` |

`image_pixel_limit` 优先级高于 `detail`；只设其中一个 `min/max` 时缺省值取 `detail` 对应值。Java / Go SDK 不支持 `image_pixel_limit`。

**`detail` 与 token 的关系**（文档表）

| detail | seed-1.8 之前：单图 token / 像素区间 | seed-1.8：单图 token / 像素区间 | seed-2.0 及以后：单图 token / 像素区间 |
|---|---|---|---|
| `low` | [4, 1312] / [3136, 1048576] | [1, 1213] / [1764, 2139732] | [1, 1280] / [1764, 2257920] |
| `high` | [4, 5120] / [3136, 4014080] | [1, 5120] / [1764, 9031680] | 固定 1280 / 2257920 |
| `xhigh` | — | — | [1280, 5120] / [2257920, 9031680] |

seed-2.0 及以后默认 `high` = 单图固定 1280 token；需要更多细节（小字、地图）才用 `xhigh`。不在区间内的图会被等比缩放进区间。

**图片 token 计算公式**

- seed-1.8 之前：`min(width × height ÷ 784, max_image_tokens)`
- seed-1.8 / 2.0 及以后：`min(width × height ÷ 1764, max_image_tokens)`
- 例：2.0 模型 `high`（上限 1280）：1280×960 → 697 token；2560×1440 → 2090 > 1280 → 计 1280，且图片被压缩（小字可能识别不出）。

**硬限制**（超出"直接报错"，文档原文，未实测）

- 宽 > 14 px 且高 > 14 px；宽×高 ∈ [196, 36 000 000] px；宽高比 ∈ [1/150, 150]。
- 张数：无固定上限，受模型上下文窗口约束；文档例：32k 窗口、每图 1312 token → 约 24 张；每图 256 token → 约 125 张。过多图会拉低回答质量。
- 格式（扩展名 / Content-Type 必须匹配实际内容）：JPEG `image/jpeg`、PNG `image/png`、GIF `image/gif`、WEBP `image/webp`、BMP / DIB `image/bmp`、TIFF `image/tiff`、ICO `image/x-icon`、ICNS `image/x-icns`、SGI `image/sgi`、JPEG2000 `image/jp2`、HEIC / HEIF `image/heic`（doubao-1.5-vision-pro 及以后）。TIFF / SGI / ICNS / JPEG2000 依赖 URL 返回的 Content-Type 元数据，放 TOS 时要设对。
- 处理完后文件从方舟服务器删除，不用于训练（文档原文）。

**示例请求**

```bash
# Chat Completions：URL 图 + detail
curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Authorization: Bearer $ARK_API_KEY" -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seed-2-1-pro-260628",
    "messages": [{"role": "user", "content": [
      {"type": "image_url", "image_url": {"url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/ark_demo_img_1.png", "detail": "high"}},
      {"type": "text", "text": "Which model series supports image input?"}
    ]}]
  }'

# Responses API：Base64 多图 + image_pixel_limit
B64=$(base64 < demo.png) && curl https://ark.cn-beijing.volces.com/api/v3/responses \
  -H "Authorization: Bearer $ARK_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "model": "doubao-seed-2-1-pro-260628",
  "input": [{"role": "user", "content": [
    {"type": "input_image", "image_url": "data:image/png;base64,$B64",
     "image_pixel_limit": {"max_pixels": 3014080, "min_pixels": 3136}},
    {"type": "input_image", "image_url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/ark_demo_img_2.png"},
    {"type": "input_text", "text": "两张图分别讲了什么？"}
  ]}]
}
EOF
```

```python
import base64, os
from openai import OpenAI

client = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=os.environ["ARK_API_KEY"])

with open("demo.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

# Chat Completions
r = client.chat.completions.create(
    model="doubao-seed-2-1-pro-260628",
    messages=[{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}},
        {"type": "text", "text": "描述这张图"},
    ]}],
)
print(r.choices[0].message.content)

# Responses API（同一 SDK，字段名不同）
resp = client.responses.create(
    model="doubao-seed-2-1-pro-260628",
    input=[{"role": "user", "content": [
        {"type": "input_image", "image_url": f"data:image/png;base64,{b64}", "detail": "high"},
        {"type": "input_text", "text": "描述这张图"},
    ]}],
)
for item in resp.output:
    if item.type == "message":
        print("".join(c.text for c in item.content if c.type == "output_text"))
```

**示例响应**（Responses API，关键字段）：`output[]` 里 `type:"reasoning"` 项的 `summary[].text` 是思维链，`type:"message"` 项的 `content[].type == "output_text"` 是回答；`usage.input_tokens / output_tokens / total_tokens`。Chat API 则是 `choices[0].message.content`（思维链在 `message.reasoning_content`）。

**注意事项**

- URL 图下载超时默认 5 s（FAQ 原文）；慢源 / 大图建议放 TOS 或压到 100 kB 以下。
- `file://` 本地路径写法只在官方 Python / Go SDK 的 `responses.create` 里有效（SDK 自动上传），对 HTTP 请求或 openai SDK 无效。
- 图片理解页写"Chat API 是无状态的"——需要多轮看同一张图时用 `file_id` 复用，或改用 Responses API `previous_response_id`。

---

## 4. 视频输入

### 视频理解（Chat / Responses）
**Endpoint**: `POST /api/v3/chat/completions` 或 `POST /api/v3/responses`
**用途**: 视频内容描述、动作 / 事件计数、时序问答（"裁判什么时间点出现"）、视频内嵌音频理解（需音频模型，见第 6 节）。

**关键参数**（视频 part）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| Chat `video_url.url` / Responses `video_url` | string | 与 `file_id` 二选一 | — | 公网 URL 或 `data:video/mp4;base64,...`。Responses 参考页把 `video_url` 标为"必选"，但 `file_id` 示例里没有它 → ⚠ 文档自相矛盾 |
| `file_id` | string | 与 url 二选一 | — | 用 `file_id` 时 **fps 参数失效**（Responses 参考页原文；抽帧策略在上传时由 `preprocess_configs.video` 决定）。Chat 页未说明 → ⚠ |
| `fps` | number | 否 | 1 | 抽帧帧率，取值 `[0.2, 5]`。画面变化剧烈 / 要数动作次数 → 调高；画面静态 → 调低省 token |

**格式与容量**

- 格式：MP4 `video/mp4`、AVI `video/x-msvideo`、MOV `video/quicktime`；格式变种多，"不能保证所有文件都能被识别"（文档原文）。TS 请先 `ffmpeg -i input.ts -c copy output.mp4`。
- 容量：URL ≤ 50 MB；Base64 ≤ 50 MB 且请求体 ≤ 64 MB；Files API 托管 ≤ 512 MB、自有 TOS Bucket ≤ 2 GB。
- 时长：⚠ 文档未给出秒数上限，只给 token 上限——单视频最大 80k token，并受模型上下文窗口 / 最大输入长度约束。

**视频 token 的算法（抽帧策略）**

原理：按 `fps` 抽帧 → 每帧前插时间戳文本 → 交给模型的等价于"文本 + 多图"序列。seed-2.0 及以后时间戳格式 `4.0 second`，之前是 `[4.0 second]`。

| 项 | seed-1.8 之前 | seed-1.8、seed-2.0 及后续 |
|---|---|---|
| `max_frame_tokens`（单帧上限） | 离散 128/160/256/384/512/640，默认 640 | 1.8：离散 64/128/192/256/320/384，默认 384；2.0+：[64, 384] 连续，默认 384 |
| `min_frame_tokens`（单帧下限） | 默认 64 | 默认 64 |
| 单帧 max_pixels | `max_frame_tokens × 28 × 28`，[10w, 50w] | `max_frame_tokens × 42 × 42`，[11w, 67w] |
| 抽帧数范围 | [16, 640]（80×1024 ÷ 128） | [16, 1280]（80×1024 ÷ 64） |
| `min_frames` | 16 | 16 |
| `max_video_tokens` | 81920 | 81920 |
| 帧数超上限时 | 按 128 token/帧、间隔 `时长/640` 均匀抽 640 帧 | 按 64 token/帧、间隔 `时长/1280` 均匀抽 1280 帧 |
| 帧数 < 16 时 | 总帧 ≥ 16 均匀抽 16 帧；否则全抽 | 同左 |

粗算：`帧数 = 时长 × fps`，`视频 token ≈ Σ 单帧 token`，方舟会按帧数把单帧压到 `[min_frame_tokens, max_frame_tokens]` 里使总量不超 `max_video_tokens`。视频未含帧数编码信息时按 fps 均匀抽帧，此时 token 可能超 80k；超过模型最大输入才报错。

**示例请求**

```bash
# Chat：URL + fps
curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Authorization: Bearer $ARK_API_KEY" -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seed-2-1-pro-260628",
    "messages": [{"role": "user", "content": [
      {"type": "video_url", "video_url": {"url": "https://ark-project.tos-cn-beijing.volces.com/doc_video/video-understanding.mp4", "fps": 5}},
      {"type": "text", "text": "裁判什么时间点出现的？"}
    ]}],
    "max_tokens": 300
  }'

# Responses：先 Files API 上传（抽帧参数在这里定），再用 file_id
curl https://ark.cn-beijing.volces.com/api/v3/files \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -F 'purpose=user_data' -F 'file=@/path/demo.mp4' \
  -F 'preprocess_configs[video][fps]=0.3' \
  -F 'preprocess_configs[video][model]=doubao-seed-2-1-pro-260628'
# 轮询 GET /files/{id} 直到 status=active，然后：
curl https://ark.cn-beijing.volces.com/api/v3/responses \
  -H "Authorization: Bearer $ARK_API_KEY" -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seed-2-1-pro-260628",
    "input": [{"role": "user", "content": [
      {"type": "input_video", "file_id": "file-20251018****"},
      {"type": "input_text", "text": "按 JSON 输出人物动作的 start_time/end_time/event/danger，时间用 HH:mm:ss"}
    ]}]
  }'
```

```python
import os, time
from openai import OpenAI

client = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=os.environ["ARK_API_KEY"])

f = client.files.create(file=open("demo.mp4", "rb"), purpose="user_data")
while f.status == "processing":          # 文档示例：2 秒轮询
    time.sleep(2)
    f = client.files.retrieve(f.id)
assert f.status == "active", f.error

# Chat API 用 file_id
r = client.chat.completions.create(
    model="doubao-seed-2-1-pro-260628",
    messages=[{"role": "user", "content": [
        {"type": "video_url", "video_url": {"file_id": f.id}},
        {"type": "text", "text": "What is in the video?"},
    ]}],
)
print(r.choices[0].message.content)
```

**注意事项**

- 用 openai SDK 的 `files.create` 传不了 `preprocess_configs`（multipart 额外字段）；需要自定义抽帧时用 curl / `requests` 或官方 `volcenginesdkarkruntime`（见第 7 节）。
- 上传时不填 `preprocess_configs.video.model`，默认按 **seed-1.8 之前**的策略抽帧（最多 640 帧）——即使推理用 2.x 模型，理解的帧数也会变少。要用新模型抽 1280 帧，上传时把 `model` 填上。
- 想让模型听视频里的声音：`preprocess_configs.video.model` 必须填支持音频理解的模型（2.0-lite / 2.0-mini），推理也用它。
- 预处理超时 5 min；1080p 抽帧容易超时，建议 `ffmpeg -vf scale=1280:720` 压到 720p（推理阶段本来就会压分辨率，提高原始像素无增益）。

---

## 5. PDF 文档输入

### 文档理解（Responses 为主；Chat 参考页也定义了 `file` part）
**Endpoint**: `POST /api/v3/responses`；`POST /api/v3/chat/completions`（⚠ 文档自相矛盾：文档理解教程页"API 接口"只列 Responses API，但 Chat API 参考页定义了 `type:"file"` part 且说"当前仅支持 PDF 文件"）
**用途**: 整本 PDF 的视觉理解——方舟把 PDF 逐页转成图片（预处理时不缩放，保真），再按 `detail` 的 `auto` 行为缩放喂给模型。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `file_id` | string | 三选一 | — | Files API 上传（`purpose=user_data`），≤ 512 MB |
| Responses `file_url` / Chat `file.file_url` | string | 三选一 | — | 公网 URL，≤ 50 MB |
| Responses `file_data` / Chat `file.file_data` | string | 三选一 | — | `data:application/pdf;base64,...`，≤ 50 MB，请求体 ≤ 64 MB |
| `filename` | string | 用 `file_data` 时必填 | — | 如 `demo.pdf` |

**限制**

- 格式：只有 PDF（`application/pdf`）。Word / Excel / PPT 等 Office 格式**不支持**（Files API 文件类型表里"文档"一栏只有 `.pdf`）。
- 页数上限：⚠ 文档未说明；只提到"预处理超时 5 min，受 PDF 页数、单页像素影响"。
- 每页按一张图计 token（见第 3 节公式）。

**示例请求**

```bash
# Responses：URL 直传
curl https://ark.cn-beijing.volces.com/api/v3/responses \
  -H "Authorization: Bearer $ARK_API_KEY" -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seed-2-1-pro-260628",
    "input": [{"role": "user", "content": [
      {"type": "input_file", "file_url": "https://ark-project.tos-cn-beijing.volces.com/doc_pdf/demo.pdf"},
      {"type": "input_text", "text": "按段落给出文档中的文字内容，以JSON格式输出，包括段落类型（type）、文字内容（content）信息。"}
    ]}]
  }'
```

```python
import base64, os
from openai import OpenAI

client = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=os.environ["ARK_API_KEY"])
with open("demo.pdf", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

resp = client.responses.create(
    model="doubao-seed-2-1-pro-260628",
    input=[{"role": "user", "content": [
        {"type": "input_file", "file_data": f"data:application/pdf;base64,{b64}", "filename": "demo.pdf"},
        {"type": "input_text", "text": "总结这份 PDF 的要点"},
    ]}],
    stream=False,
)
print(resp.output_text if hasattr(resp, "output_text") else resp.output)
```

Chat API 写法（参考页定义，教程无示例）：`{"type": "file", "file": {"file_id": "file-xxx"}}`。

**注意事项**：长 PDF 建议 `stream: true` 规避客户端超时（文档在每个 Files API 小节都这么提示）。

---

## 6. 音频输入

### 音频理解（Chat / Responses）
**Endpoint**: `POST /api/v3/chat/completions` 或 `POST /api/v3/responses`
**用途**: 通用音频问答、音频 Caption、ASR（含时间戳 / 字幕对齐）、多说话人 ASR（`spk0`/`spk1`）、说话人日志（`[spkN][开始-结束] 内容`）、语音翻译 AST、视频内嵌音轨理解。这些都是靠 prompt 驱动同一个多模态模型，不是独立 endpoint。ASR 支持 19 种语种 + 多种中文方言，AST 15 种语种（文档原文）。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| Chat `input_audio.data` | string | 三选一 | **裸 Base64**（无 `data:` 前缀），此时 `format` 必填 |
| Chat `input_audio.url` | string | 三选一 | 公网 URL，示例里也带了 `format` |
| Chat `input_audio.file_id` | string | 三选一 | Files API 返回 |
| Chat `input_audio.format` | string | 用 `data` 时必填 | 示例值 `mp3`；参考页给的是 MIME 列表 |
| Responses `audio_url` | string | 与 `file_id` 二选一 | 公网 URL 或 `data:audio/mpeg;base64,...` |
| Responses `file_id` | string | 与 `audio_url` 二选一 | Files API 返回 |
| Responses `chunking_strategy` | object | 否 | `{"type":"server_vad","prefix_padding_ms":..,"silence_duration_ms":..,"threshold":..}`，仅参考页列出 → ⚠ 文档未说明用途与默认值 |

**格式与限制**

- 纯音频：mp3 `audio/mpeg`、wav `audio/wav`、aac `audio/aac`、m4a（音频教程页 `audio/x-m4a`，Chat 参考页 `audio/mp4` → ⚠ 文档自相矛盾）。
- 视频内嵌音频额外支持 ac3 `audio/ac3`、alac `audio/mp4`；Chat 参考页还列了 pcm `audio/L16`（教程页没有）。
- 容量：Files API ≤ 512 MB；Base64 / URL ≤ 25 MB 且时长 ≤ 120 min。Chat 参考页补充"单次请求音频总时长 ≤ 120 min，仅统计纯音频，视频内嵌音频不计入"。
- token：约 **6.25 token / 秒**，以返回的 `audio_tokens` 为准（⚠ 文档未说明 `audio_tokens` 在 `usage` 的哪一层；教程示例响应只有 `input_tokens/output_tokens/total_tokens`）。
- ⚠ 文档自相矛盾：音频教程页说 Files API 方式"当前 Responses API 支持"，Chat 参考页却定义了 `input_audio.file_id`。

**示例请求**

```bash
# Responses：URL 音频 + instructions
curl https://ark.cn-beijing.volces.com/api/v3/responses \
  -H "Authorization: Bearer $ARK_API_KEY" -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seed-2-0-lite-260428",
    "instructions": "你是音频理解专家，擅长分析音频信息来回答问题。",
    "input": [{"type": "message", "role": "user", "content": [
      {"type": "input_audio", "audio_url": "https://ark-project.tos-cn-beijing.volces.com/doc_audio/ark_demo_audio.mp3"},
      {"type": "input_text", "text": "请识别这段音频内容"}
    ]}]
  }'

# Chat：Base64 音频（裸 base64 + format）
B64=$(base64 < demo.mp3) && curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Authorization: Bearer $ARK_API_KEY" -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "model": "doubao-seed-2-0-lite-260428",
  "messages": [{"role": "user", "content": [
    {"type": "input_audio", "input_audio": {"data": "$B64", "format": "mp3"}},
    {"type": "text", "text": "请识别音频中的内容"}
  ]}]
}
EOF
```

```python
import base64, os
from openai import OpenAI

client = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=os.environ["ARK_API_KEY"])
b64 = base64.b64encode(open("demo.mp3", "rb").read()).decode()

# Chat：说话人日志式 ASR（prompt 驱动）
r = client.chat.completions.create(
    model="doubao-seed-2-0-lite-260428",
    messages=[{"role": "user", "content": [
        {"type": "input_audio", "input_audio": {"data": b64, "format": "mp3"}},
        {"type": "text", "text": "区分说话人并转写，格式：[spkN][开始-结束] 内容"},
    ]}],
)
print(r.choices[0].message.content)

# 视频内嵌音频：直接喂视频，模型自动取音轨（Responses）
resp = client.responses.create(
    model="doubao-seed-2-0-lite-260428",
    input=[{"role": "user", "content": [
        {"type": "input_video", "video_url": "https://ark-project.tos-cn-beijing.volces.com/doc_video/video_by_sd2.mp4", "fps": 1},
        {"type": "input_text", "text": "识别视频中的语音内容，并分析音色、语气、语速与情感"},
    ]}],
)
```

**注意事项**：多轮音频对话用 Responses API `previous_response_id` 追加第二段录音（教程示例），比 Chat API 重传整段 base64 省得多。

---

## 7. Files API

Files API 本身免费；文件存方舟托管空间有 **20 GB 免费额度**（满了无法上传，删文件释放），存自有 TOS Bucket 按 TOS 计费。限流：上传 20 QPS / 100 Mbps，检索 / 列表 / 删除各 20 QPS。

**入口**：本节路径均为标准入口 `/api/v3/files`。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`GET https://ark.cn-beijing.volces.com/api/plan/v3/files` → HTTP **404**（空 body）——Files API 在 Agent Plan 入口不存在，Plan 用户不能用 `file_id`，只能 URL / Base64 内联（见 §10）。Coding Plan `/api/coding/v3/files` 未测。

### 上传文件
**Endpoint**: `POST /api/v3/files`（`multipart/form-data`）
**用途**: 上传图片 / 视频 / PDF / 音频拿 `file_id`，触发预处理（视频抽帧、PDF 分页）。与直传 URL 的区别：大文件、复用、预处理与推理解耦。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `file` | binary | 与 `url` 二选一 | — | 本地二进制文件 |
| `url` | string | 与 `file` 二选一 | — | HTTP/HTTPS 公网 URL，或 TOS URI `tos://<bucket>/<prefix>/<file_name>`（TOS URI 时必须同时传 `tos.bucket`、`tos.prefix`） |
| `purpose` | string | 是 | — | 文档只列了一个枚举：`user_data`（任意用途） |
| `tos.bucket` / `tos.prefix` | string | 否 | — | 传了就存到自有 TOS Bucket（需控制台先授权）；不传存方舟托管空间。预处理产物落在 `<bucket>/<prefix>/ark_processed/{file_id}/` |
| `expire_at` | integer | 否 | 当前 + 7 天 | UTC Unix 秒，范围 `[now+86400, now+2592000]`（1–30 天），到期自动删 |
| `preprocess_configs.video.fps` | number | 否 | 1 | `[0.2, 5]`；单视频 token 用量范围 `[10k, 80k]` |
| `preprocess_configs.video.model` | string | 否 | — | Model ID 或 Endpoint ID，只决定抽帧策略，与推理模型不强耦合；不传 = seed-1.8 之前策略；配置后自动填充下面四个默认值 |
| `preprocess_configs.video.max_video_tokens` | integer | 否 | 81920 | `[10240, 204800]` |
| `preprocess_configs.video.min_frame_tokens` | integer | 否 | 64 | `[16, 128]` |
| `preprocess_configs.video.max_frame_tokens` | integer | 否 | 随模型 | `[128, 640]` |
| `preprocess_configs.video.min_frames` | integer | 否 | 16 | `[5, 16]` |

**存储位置对比**

| | 方舟托管默认空间 | 自有 TOS Bucket |
|---|---|---|
| 授权 | 无需 | 控制台先授权 |
| 单文件 | 512 MB | 视频 2 GB，其他 512 MB |
| 总容量 | 20 GB | 无限制 |
| 存储时长 | 默认 7 天，`expire_at` 1–30 天 | 同左 |
| 删除 | 只能走 Files API DELETE | 托管后 TOS 侧只读，不能在 TOS 控制台 / API 删改；仍走 Files API DELETE |

**支持的文件类型**：图片 `.jpg .jpeg .png .gif .webp .bmp .tiff .ico .icns .sgi .jp2 .heic .heif`；视频 `.mp4 .avi .mov`；文档 `.pdf`；音频 `.mp3 .wav .aac .m4a`。

**示例请求**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/files \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -F 'purpose=user_data' \
  -F 'file=@/path/demo.mp4' \
  -F 'preprocess_configs[video][fps]=0.3' \
  -F "expire_at=$(( $(date +%s) + 86400 ))"

# 用 URL 上传；或 TOS URI 上传到自有 Bucket
curl -X POST https://ark.cn-beijing.volces.com/api/v3/files \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -F "purpose=user_data" -F "url=tos://my-bucket/source/raw_video.mp4" \
  -F "tos[bucket]=my-bucket" -F "tos[prefix]=ark-files/"
```

```python
import os, time, requests

BASE = "https://ark.cn-beijing.volces.com/api/v3"
H = {"Authorization": f"Bearer {os.environ['ARK_API_KEY']}"}

with open("demo.mp4", "rb") as f:
    up = requests.post(f"{BASE}/files", headers=H,
                       files={"file": ("demo.mp4", f, "video/mp4")},
                       data={"purpose": "user_data",
                             "preprocess_configs[video][fps]": "0.3",
                             "preprocess_configs[video][model]": "doubao-seed-2-1-pro-260628"}).json()
file_id = up["id"]
while up["status"] == "processing":
    time.sleep(2)
    up = requests.get(f"{BASE}/files/{file_id}", headers=H).json()
if up["status"] == "failed":
    raise RuntimeError(up["error"])
```

官方 SDK：`from volcenginesdkarkruntime import Ark; Ark(base_url=..., api_key=...).files.create(file=open(...,'rb'), purpose='user_data')`，底层同样是 `POST /api/v3/files`。

**示例响应**（file object）

```json
{
  "object": "file",
  "id": "file-20251018114827-6zgrb",
  "purpose": "user_data",
  "filename": "demo.mp4",
  "bytes": 695110,
  "mime_type": "video/mp4",
  "created_at": 1760759307,
  "expire_at": 1761364107,
  "status": "processing",
  "preprocess_configs": {"video": {"fps": 0.3}}
}
```

**file object 字段**：`object`（固定 `file`）、`id`、`purpose`、`scope{type:"session", id}`（会话作用域，Managed Agents 场景）、`filename`、`tos{bucket, object_key}`（仅传了 `tos` 时返回）、`bytes`（查询详情时仅 `active` 才返回）、`created_at`、`expire_at`、`mime_type`、`status`（`processing` 不可用 / `active` 可用 / `failed`）、`error{code, message}`（仅 `failed`）、`preprocess_configs.video{fps, model, max_video_tokens, min_frame_tokens, max_frame_tokens, min_frames}`。

### 查询文件详情
**Endpoint**: `GET /api/v3/files/{file_id}`
**用途**: 轮询 `status`；拿 `expire_at`、`mime_type`。返回 file object（同上）。

```bash
curl https://ark.cn-beijing.volces.com/api/v3/files/file-20251014**** -H "Authorization: Bearer $ARK_API_KEY"
```

### 查询文件列表
**Endpoint**: `GET /api/v3/files?after={after}&limit={limit}&purpose={purpose}&order={order}&scope_id={scope_id}`

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `after` | string | — | 返回该文件 ID 之后的文件（分页游标，配合响应 `last_id`） |
| `limit` | integer | 100 | 1–100 |
| `purpose` | string | — | 按用途筛选 |
| `order` | string | `desc` | 按 `created_at` 排序：`asc` / `desc` |
| `scope_id` | string | — | 会话 ID，仅 Managed Agents 场景 |

响应：`{"object":"list","data":[file object...],"first_id":"...","last_id":"...","has_more":true|false}`。

### 删除文件
**Endpoint**: `DELETE /api/v3/files/{file_id}`
**用途**: 释放 20 GB 额度；删除后不可恢复、不可再被推理引用。响应 `{"deleted": true, "id": "file-xxx", "object": "file"}`。

```bash
curl -X DELETE https://ark.cn-beijing.volces.com/api/v3/files/file-20251014**** -H "Authorization: Bearer $ARK_API_KEY"
```

### 把 `file_id` 放进消息

对照第 1.2 节表：Responses 用 `input_image` / `input_video` / `input_file` / `input_audio` + 顶层 `file_id`；Chat 用 `image_url.file_id` / `video_url.file_id` / `file.file_id` / `input_audio.file_id`。⚠ 文档自相矛盾：文件输入指南的 curl 示例把**视频** file_id 放在 `{"type":"input_file","file_id":...}` 里，而同页 Python 示例和视频理解页都用 `input_video`。以参考页"`file_id` 对应的文件类型需要和 `type` 保持一致"为准，视频用 `input_video`。

---

## 8. GUI Agent 与 Grounding

两者都不是独立 endpoint，而是用 Chat Completions + 图片 part + 特定 prompt，让 Doubao Seed 模型输出**归一化坐标**。

### 8.1 GUI Agent（截图 → 下一步动作）

- **关键约定**：调用 `chat.completions.create` 时**不要传 `tools`**。动作块直接写在 `message.content`，思维链在 `message.reasoning_content`。传了 `tools` 会走 function calling，输出格式完全不同。
- **动作输出格式**（模型按 system prompt 里的定义输出）：

  ```xml
  <seed:tool_call><function name="click"><parameter name="point" string="true"><point>900 11</point></parameter></function></seed:tool_call>
  ```

  官方示例定义 8 个动作：`click / drag / hotkey / left_double / right_single / scroll / type / wait`；`drag` 有 `start_point` / `end_point`；`scroll` 有 `direction ∈ up/down/left/right`；`type` 内容末尾 `\n` 表示提交。
- **坐标**：`<point>x y</point>`，x、y 均为 **0–1000 归一化**（取值 [0, 999]，与截图分辨率无关），可选一位小数。映射回像素：`px = round(x / 1000 * width)`，`py = round(y / 1000 * height)`。
- **结束条件**：回复是纯文本且不含 `<seed:tool_call>` → 任务完成，该文本即最终答案。
- **消息结构**：两条 system（任务框架 `TASK_SP` + 动作定义 `FUNCTION_SP`，含哨兵串 `think_never_used_51bce0c785ca2f68081bfa7d91973934` 包裹思考）+ user `[{"type":"text",...},{"type":"image_url",{"url": data_url}}]`。解析用 `ui-tars` 包 `parse_xml_action_65_with_validate_soft`。
- **工程提示**（文档原文）：RGBA 截图先 `convert("RGB")` 再编码；首个多模态请求约 10–23 s，`timeout ≥ 120`；批量并发建议 4–8，`max-retries ≥ 3`。
- 专用模型：模型列表只标了 `doubao-seed-1-6-vision-250815`（即将下线）有"GUI 任务处理"；教程用 2.1-turbo 跑分（sspro ~54–56%，osworld-g ~84–86%，3000×3000、`temperature=0`）。⚠ 见 2.3。

### 8.2 视觉定位 Grounding（自然语言 → bbox / 点）

- **bbox 输出格式**：`<bbox>x_min y_min x_max y_max</bbox>`，四个整数，**归一化到 1000×1000**，取值 [0, 999]，原点在图片左上角。映射：`x_real = x_min / 1000 * w`。
- prompt 示例：`框出中间狼卡通形象的头部的位置，输出 bounding box 的坐标`；教程代码要求返回以 `<bbox>` 开头、`</bbox>` 结尾。
- 单点定位（GUI Agent 页"方式二"）：只保留 `click` 动作定义，一条指令 + 一张截图 → 一个 `<point>x y</point>`。

```python
import base64, os, re
from openai import OpenAI

client = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=os.environ["ARK_API_KEY"])
b64 = base64.b64encode(open("shot.png", "rb").read()).decode()
r = client.chat.completions.create(
    model="doubao-seed-2-1-pro-260628",
    messages=[{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        {"type": "text", "text": "框出登录按钮的位置，输出 bounding box 的坐标"},
    ]}],
)
m = re.fullmatch(r"<bbox>(\d+) (\d+) (\d+) (\d+)</bbox>", r.choices[0].message.content.strip())
x0, y0, x1, y1 = (int(v) for v in m.groups())      # 0-999 归一化，乘 w/1000、h/1000 得像素
```

---

## 9. 多模态长会话的上下文管理

来自「上下文管理」页，与多模态相关的要点：

- **Chat API 无状态**：多轮必须自己把历史 user/assistant 交替拼进 `messages`，图片每轮都重传（`image_url` 示例在该页多轮示例里原样出现）。图片 token 每轮都重新计入输入。用 `file_id` 复用至少省去重复上传 / 下载，token 不省。
- **Responses API 有状态**：默认持久化输入输出，下一轮只传 `previous_response_id` + 新 `input`，上一轮的图 / 音频不必重传（音频教程的多轮示例就是这么做的）。
- **思维链不进上下文**：多轮对话中上一轮的 CoT 不会拼进下一轮（工具调用场景 seed-1.8 及以后由平台决定是否带入）。
- **长度预算**：图片张数受"上下文窗口 − 思维链窗口 = 最大输入长度（问答配额）"约束，回答配额 = `min(max_tokens, 最大输入长度 − 实际输入)`。输入超最大输入长度直接报错（文档原文，未实测）；多图请求先算 token（第 3 节公式），必要时降 `detail` 或减图。
- **输出长度**：Chat 用 `max_tokens`（默认 4096，只管回答）或 `max_completion_tokens`（回答 + 思维链，设了它 `max_tokens` 默认值失效）；Responses 用 `max_output_tokens`。`reasoning_effort` 七档 `none / minimal / low / medium / high / xhigh / max` 控制思维链长度。
- **超时**：视频 / 长 PDF / 大音频建议 `stream: true`，避免客户端超时。

---

## 10. 三套入口下的可用性

| 能力 | 标准 `/api/v3` | Coding Plan `/api/coding/v3` | Agent Plan `/api/plan/v3` |
|---|---|---|---|
| 图片 part（`image_url` / `input_image`） | ✅ 本文全部示例 | 模型侧：Coding Plan 套餐概览写 `doubao-seed-2.1-turbo`、`doubao-seed-2.0-lite`、`minimax-m3`、`kimi-k2.7-code`"支持多模态视觉理解"，`kimi-k2.7-code`"支持文本、图片与视频输入"，`glm-5.3-flash`"原生多模态模型，支持图片输入"。请求写法 ⚠ 文档未说明（Coding Plan FAQ 只给了 OpenClaw 里把模型 `input` 设为 `["text","image"]` 的配置，暗示 OpenAI 协议 `image_url` 可用） | 模型侧：Agent Plan 套餐概览只对 `glm-5.3-flash` 标注"支持图片输入"；其余文本模型 ⚠ 文档未说明。Agent Plan"接入视觉模型"页讲的是**生图 / 生视频**，不是理解 |
| 视频 part | ✅ | 仅 `kimi-k2.7-code` 提到视频输入；写法 ⚠ 文档未说明 | ⚠ 文档未说明 |
| PDF / 音频 part | ✅ | ⚠ 文档未说明 | ⚠ 文档未说明（Agent Plan 的 `doubao-seed-asr-2.0` 是独立语音识别模型，不是 `input_audio` part） |
| Files API `/files` | ✅ | ⚠ 文档未说明是否存在 `/api/coding/v3/files`（Agent Plan 入口实测不存在，Coding Plan 预期相同但未测） | **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`GET https://ark.cn-beijing.volces.com/api/plan/v3/files` → HTTP **404**，body 为空——Files API 在 Agent Plan 入口不存在，所以 `file_id` 方式（`image_url.file_id` / `input_file` 等）在 Plan 不可用，只能 URL / Base64 内联 |
| `detail` / `fps` / `image_pixel_limit` 等方舟扩展字段对第三方模型（glm / kimi / minimax / deepseek）是否生效 | — | ⚠ 文档未说明 | ⚠ 文档未说明 |
| model 字段 | 带日期 Model ID 或 `ep-xxx` | 小写 Model Name（`kimi-k2.7-code` 等） | 小写 Model Name；Key 用 `ARK_AGENT_PLAN_API_KEY` |

另注：Coding Plan 套餐额度"仅在 AI 编程工具中生效，不可用于 API 调用"，非工具内直连有被判滥用风险（文档原文）；Anthropic 协议入口（`/api/coding`、`/api/plan`）下多模态输入的写法 ⚠ 文档未说明。

---

## 11. 常见报错与排查

以下均为文档原文描述，未实测：

| 现象 | 文档给的原因 / 处理 |
|---|---|
| 视觉理解报 `InvalidParameter` | ① 图片下载超时（默认 5 s）→ 放 TOS 或压到 100 kB 以下；② URL 返回 403（源站 ACL 禁了火山来源）；③ 格式不支持或与元数据不匹配——jpg/png/gif/webp/bmp/dib/ico 按前 512 字节校验，TIFF/SGI/ICNS/JPEG2000 按 URL 的 `Content-Type` 校验，TOS/OSS 上要设对 |
| 像素不在 [196, 36 000 000]、宽或高 ≤ 14、宽高比超 [1/150, 150] | 直接报错，先自行缩放 |
| token 过长报错 | 减图、压图（降 `detail` / `image_pixel_limit`）、精简 prompt |
| 视频总 token 超模型最大输入 | 报错；降 `fps`、剪短视频；未超但 > 80k 不报错 |
| Files API 预处理超时（5 min） | 视频压到 720p；PDF 页数 / 单页像素过大也会 |
| `file_id` 报错 | 检查 `status == active`、文件类型与 part `type` 一致、API Key 与上传时同项目、模型在 2.4 支持列表内 |
| TS 视频不识别 | `ffmpeg -i input.ts -c copy output.mp4` |
| 图片 `mime_type` 大写 | 文档要求格式声明小写 |

---

## 来源页面

| 标题 | URL | 文档更新时间 |
|---|---|---|
| 图片理解 | https://www.volcengine.com/docs/82379/1362931 | 2026-08-13 |
| 视频理解 | https://www.volcengine.com/docs/82379/1895586 | 2026-08-31 |
| 文档理解 | https://www.volcengine.com/docs/82379/1902647 | 2026-06-23 |
| 音频理解 | https://www.volcengine.com/docs/82379/2377589 | 2026-08-19 |
| 文件输入(File API) | https://www.volcengine.com/docs/82379/1885708 | 2026-08-07 |
| 上传文件 | https://www.volcengine.com/docs/82379/1870405 | 2026-08-22 |
| 查询文件详情 | https://www.volcengine.com/docs/82379/1870406 | 2026-08-24 |
| 查询文件列表 | https://www.volcengine.com/docs/82379/1870407 | 2026-07-06 |
| 删除文件 | https://www.volcengine.com/docs/82379/1870408 | 2026-08-20 |
| The file object | https://www.volcengine.com/docs/82379/1873424 | 2026-07-06 |
| GUI Agent 能力 | https://www.volcengine.com/docs/82379/1584296 | 2026-07-20 |
| 视觉定位 Grounding | https://www.volcengine.com/docs/82379/1616136 | 2026-08-06 |
| 上下文管理 | https://www.volcengine.com/docs/82379/2123288 | 2026-08-19 |
| 多模态理解（Responses API 指南，file_id 示例） | https://www.volcengine.com/docs/82379/1958521 | 2026-08-05 |
| 对话(Chat) API 参考（content part 字段定义） | https://www.volcengine.com/docs/82379/1494384 | 2026-08-28 |
| 创建 Response 参考（input.content 字段定义） | https://www.volcengine.com/docs/82379/1569618 | 2026-08-25 |
| 模型列表（能力支持表） | https://www.volcengine.com/docs/82379/1330310 | 2026-09-02 |
| 常见问题（InvalidParameter / TS 格式） | https://www.volcengine.com/docs/82379/1359411 | 2026-07-07 |
| Agent Plan 个人版 · 套餐概览 | https://www.volcengine.com/docs/82379/2366394 | 2026-08-31 |
| Coding Plan 个人版 · 套餐概览 | https://www.volcengine.com/docs/82379/1925114 | 2026-08-31 |
| Coding Plan 个人版 · 常见问题（OpenClaw 图片识别） | https://www.volcengine.com/docs/82379/2165245 | 2026-08-24 |
