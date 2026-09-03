# 多模态生成与理解 API

本文档只讲图像 / 视频 / 语音相关 API 的**调用方式**（endpoint、参数、请求响应示例、注意事项）。模型选型建议（该用哪个模型、各模型的能力边界与价格）请查阅 `references/models.md`，本文不重复展开。

所有请求的完整地址 = Base URL `https://open.bigmodel.cn/api/` + 下文的 path；请求头需带 `Authorization: Bearer <API_KEY>`（API Key 获取地址：https://bigmodel.cn/usercenter/proj-mgmt/apikeys）。

## 异步任务通用说明

图像生成（异步）、视频生成都是**异步接口**：提交请求后立即返回一个任务 `id` 和 `task_status`（`PROCESSING`/`SUCCESS`/`FAIL`），真正的生成结果需要轮询通用的“查询异步结果”接口获取：

**Endpoint**: `GET /paas/v4/async-result/{id}`

- 视频任务成功后，响应里的 `video_result` 数组包含 `url`（视频链接）和 `cover_image_url`（封面图）。
- 图像异步任务成功后，响应里的 `image_result` 数组包含 `url`（图片链接，有效期 30 天）。
- `task_status` 仍为 `PROCESSING` 时表示还没生成完，需要客户端自行间隔轮询（建议几秒一次），直到状态变为 `SUCCESS` 或 `FAIL`。

```python
import time, requests

BASE = "https://open.bigmodel.cn/api"
headers = {"Authorization": f"Bearer {API_KEY}"}

def poll_async_result(task_id, interval=3, timeout=180):
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(f"{BASE}/paas/v4/async-result/{task_id}", headers=headers)
        data = r.json()
        if data.get("task_status") in ("SUCCESS", "FAIL"):
            return data
        time.sleep(interval)
    raise TimeoutError("polling timed out")
```

---

## 图像生成

### 图像生成（同步）

**Endpoint**: `POST /paas/v4/images/generations`

**用途**: 根据文本提示直接生成图像，同步返回图片 URL；支持 `glm-image`、`cogview-4` 系列、`cogview-3-flash` 等模型。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | - | `glm-image` / `cogview-4-250304` / `cogview-4` / `cogview-3-flash` |
| `prompt` | string | 是 | - | 图像的文本描述 |
| `quality` | string | 否 | `glm-image` 默认 `hd`，其它默认 `standard` | `hd`（更精细，约 20 秒）/ `standard`（更快，约 5-10 秒）。`glm-image` 仅支持 `hd` |
| `size` | string | 否 | `1280x1280` | `glm-image` 推荐：`1280x1280`、`1568x1056`、`1056x1568`、`1472x1088`、`1088x1472`、`1728x960`、`960x1728`（自定义需在 1024-2048px 之间，是 32 的倍数，像素总数 ≤ 2^22）。其它模型推荐：`1024x1024`、`768x1344`、`864x1152`、`1344x768`、`1152x864`、`1440x720`、`720x1440`（自定义需在 512-2048px 之间，被 16 整除，像素总数 ≤ 2^21） |
| `watermark_enabled` | boolean | 否 | `true` | `true` 添加显式+隐式水印（合规默认值）；`false` 需先在个人中心-安全管理-去水印管理签署免责声明 |
| `user_id` | string | 否 | - | 终端用户唯一 ID，6-128 字符，用于平台风控 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/images/generations \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "cogview-4",
    "prompt": "一只柯基犬在樱花树下奔跑，阳光透过花瓣，插画风格",
    "size": "1024x1024"
  }'
```

```python
import requests

resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/images/generations",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "cogview-4",
        "prompt": "一只柯基犬在樱花树下奔跑，阳光透过花瓣，插画风格",
        "size": "1024x1024",
    },
)
print(resp.json())
```

**示例响应**

```json
{
  "created": 1719900000,
  "data": [{ "url": "https://.../image.png" }],
  "content_filter": [{ "role": "user", "level": 3 }]
}
```

**注意事项**

- 返回的图片 URL 是**临时链接，有效期 30 天**，务必及时转存。
- `content_filter` 中 `level` 越小越严重（0 最严重，3 轻微），用于内容安全审计，不代表调用失败。
- 想要更长的自定义分辨率或更高一致性的批量生产场景，考虑用下面的异步接口，避免同步请求超时。

### 图像生成（异步）

**Endpoint**: `POST /paas/v4/async/images/generations`

**用途**: 仅支持 `GLM-Image` 模型，提交后立即返回任务 `id`，需配合通用异步结果查询接口（`GET /paas/v4/async-result/{id}`）获取图片结果，适合对响应时延不敏感、追求高保真的场景。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | - | 固定为 `glm-image` |
| `prompt` | string | 是 | - | 图像的文本描述 |
| `quality` | string | 否 | `hd` | 仅支持 `hd`，耗时约 20 秒 |
| `size` | string | 否 | `1280x1280` | 同上（`glm-image` 的尺寸规则） |
| `watermark_enabled` | boolean | 否 | `true` | 同上 |
| `user_id` | string | 否 | - | 同上，6-128 字符 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/async/images/generations \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "glm-image", "prompt": "赛博朋克风格的未来城市夜景"}'
```

```python
resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/async/images/generations",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={"model": "glm-image", "prompt": "赛博朋克风格的未来城市夜景"},
)
task_id = resp.json()["id"]
result = poll_async_result(task_id)  # 见上文“异步任务通用说明”
print(result["image_result"][0]["url"])
```

**示例响应（提交请求后）**

```json
{ "model": "glm-image", "id": "task_xxx", "request_id": "req_xxx", "task_status": "PROCESSING" }
```

**注意事项**

- 提交请求本身只返回任务状态，不含图片内容，必须轮询 `/paas/v4/async-result/{id}` 拿最终结果。
- 结果里的字段是 `image_result`（数组，含 `url`），不是同步接口里的 `data`。

---

## 视频生成（异步）

**Endpoint**: `POST /paas/v4/videos/generations`

**用途**: 文本生成视频、图像生成视频、首尾帧生成视频、多参考图生成视频等，覆盖 `CogVideoX` 系列与 `Vidu` 系列模型。**始终是异步接口**，提交后拿到任务 `id`，需配合 `GET /paas/v4/async-result/{id}` 轮询结果（`video_result` 数组，含 `url` 和 `cover_image_url`）。

不同 `model` 支持的参数组合不同，按生成模式分类如下。

### 通用参数（除 Vidu 系列外均适用）

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `prompt` | string | 视情况 | - | 视频文本描述，一般 ≤512 字符；`image_url` 与 `prompt` 不能同时为空 |
| `quality` | string | 否 | `speed` | `quality`（质量优先）/ `speed`（速度优先） |
| `with_audio` | boolean | 否 | `false` | 是否生成 AI 音效 |
| `watermark_enabled` | boolean | 否 | `true` | 同图像生成 |
| `request_id` | string | 否 | 平台自动生成 | 客户端请求唯一标识 |
| `user_id` | string | 否 | - | 终端用户唯一 ID，6-128 字符 |

### CogVideoX 系列

| model | image_url | size | fps | duration | 备注 |
|---|---|---|---|---|---|
| `cogvideox-3` | 单个 URL/Base64，或 `[首帧,尾帧]` 两张图数组 | `1280x720`/`720x1280`/`1024x1024`/`1920x1080`/`1080x1920`/`2048x1080`/`3840x2160`，默认短边 1080，最高 4K | `30`（默认）/`60` | `5`（默认）/`10` | `model` 必填 |
| `cogvideox-2`、`cogvideox-flash` | 单个 URL 或 Base64 | `720x480`/`1024x1024`/`1280x960`/`960x1280`/`1920x1080`/`1080x1920`/`2048x1080`/`3840x2160`，默认短边 1080 | `30`（默认）/`60` | 无 duration 字段 | `model` 必填 |

### Vidu 系列

Vidu 系列不支持上面的 `quality`/`with_audio` 顶层通用块，而是各自的模式化参数：

| 模式 | model | 必填 | 关键参数 |
|---|---|---|---|
| 文生视频 | `viduq1-text` | `model`、`prompt` | `style`（`general` 默认 / `anime`）、`duration`（仅 `5`）、`aspect_ratio`（`16:9` 默认/`9:16`/`1:1`）、`size`（仅 `1920x1080`）、`movement_amplitude`（`auto` 默认/`small`/`medium`/`large`） |
| 图生视频 | `viduq1-image`、`vidu2-image` | `model` | `image_url`（URL 或 Base64）、`duration`（`viduq1-image` 仅 `5`，`vidu2-image` 仅 `4`）、`size`（`viduq1-image` 仅 `1920x1080`，`vidu2-image` 仅 `1280x720`）、`movement_amplitude`、`with_audio`（仅当最终时长为 4 秒时支持） |
| 首尾帧生成 | `viduq1-start-end`、`vidu2-start-end` | `model` | `image_url`（数组，恰好 2 张：第一张=首帧，第二张=尾帧；两图分辨率比例需在 0.8-1.25，宽高比 < 1:4 或 4:1）、`duration`（`viduq1` 仅 `5`，`vidu2` 仅 `4`）、`size`（`viduq1` 仅 `1920x1080`，`vidu2` 为 `1280x720`/`480x360`）、`movement_amplitude`、`with_audio` |
| 参考图生成（多图一致主体） | `vidu2-reference` | `model` | `image_url`（数组，1-3 张参考图，分辨率不小于 128x128，宽高比 < 1:4 或 4:1）、`duration`（仅 `4`）、`aspect_ratio`、`size`（仅 `1280x720`）、`movement_amplitude`、`with_audio` |

`image_url` 支持的图片格式：`png`/`jpeg`/`.jpg`/`webp`，单张文件 ≤50MB；用 Base64 时需带 `data:image/png;base64,{base64_encode}` 这样的 content-type 前缀，解码后字节数同样 ≤50MB。

**示例请求（CogVideoX-3 文生视频）**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/videos/generations \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "cogvideox-3",
    "prompt": "无人机航拍海边日出，慢镜头",
    "quality": "quality",
    "size": "1920x1080",
    "duration": 5
  }'
```

```python
resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/videos/generations",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "cogvideox-3",
        "prompt": "无人机航拍海边日出，慢镜头",
        "quality": "quality",
        "size": "1920x1080",
        "duration": 5,
    },
)
task_id = resp.json()["id"]
result = poll_async_result(task_id)
print(result["video_result"][0]["url"], result["video_result"][0]["cover_image_url"])
```

**示例请求（Vidu 图生视频）**

```python
resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/videos/generations",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "vidu2-image",
        "prompt": "画面中的人物微笑并转头",
        "image_url": "https://example.com/portrait.png",
        "duration": 4,
        "with_audio": True,
    },
)
```

**示例响应（提交请求后）**

```json
{ "model": "cogvideox-3", "id": "task_xxx", "request_id": "req_xxx", "task_status": "PROCESSING" }
```

**注意事项**

- 提交接口本身不返回视频内容，必须轮询 `GET /paas/v4/async-result/{id}`，成功后从 `video_result[0].url` 取视频、`video_result[0].cover_image_url` 取封面。
- 不同 `model` 对 `size`/`duration`/`image_url` 的取值范围差异很大（见上表），传入模型不支持的枚举值会报错，写代码前先确认目标 `model` 属于哪一类。
- `viduq1-*`/`vidu2-*` 系列不认识顶层的 `quality`/`with_audio`（除各自模式表里列出的以外）通用参数，混用会被忽略或报错，按模式表里列的参数来传。
- 首尾帧模式（`*-start-end`）对两张图的分辨率比例、宽高比有硬性限制，超出范围会导致生成失败。

---

## 语音转文本（ASR）

**Endpoint**: `POST /paas/v4/audio/transcriptions`

**用途**: 使用 `GLM-ASR-2512` 模型将音频文件转录为文本，支持多语言，支持一次性返回或流式（Event Stream）逐块返回。

**关键参数**（`multipart/form-data`）

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `file` | binary | 是（或 `file_base64`） | - | 音频文件，支持 `.wav`/`.mp3`；文件 ≤25MB，时长 ≤30 秒 |
| `file_base64` | string | 否 | - | 音频 Base64 编码，与 `file` 二选一，同时传以 `file` 为准 |
| `model` | string | 是 | `glm-asr-2512` | 固定为 `glm-asr-2512` |
| `prompt` | string | 否 | - | 长文本场景下可传入前序转录结果作为上下文，建议 <8000 字 |
| `hotwords` | array[string] | 否 | - | 热词表，提升特定词汇识别率，建议 ≤100 个 |
| `stream` | boolean | 否 | `false` | `true` 时以 Event Stream 逐块返回，结束时发 `data: [DONE]` |
| `request_id` | string | 否 | 平台自动生成 | 6-64 字符，建议用 UUID |
| `user_id` | string | 否 | - | 终端用户唯一 ID，6-128 字符 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/audio/transcriptions \
  -H "Authorization: Bearer $API_KEY" \
  -F "model=glm-asr-2512" \
  -F "file=@meeting.mp3"
```

```python
with open("meeting.mp3", "rb") as f:
    resp = requests.post(
        "https://open.bigmodel.cn/api/paas/v4/audio/transcriptions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        data={"model": "glm-asr-2512"},
        files={"file": ("meeting.mp3", f, "audio/mpeg")},
    )
print(resp.json()["text"])
```

**示例响应（非流式）**

```json
{
  "id": "task_xxx",
  "created": 1719900000,
  "request_id": "req_xxx",
  "model": "glm-asr-2512",
  "text": "大家好，今天我们讨论一下……"
}
```

流式响应每个事件是 `type` 为 `transcript.text.delta`（增量文本在 `delta` 字段）或 `transcript.text.done`（转录完成）的 JSON。

**注意事项**

- 单次请求音频限制较严格：≤25MB 且 ≤30 秒，超长音频需自行分段调用。
- `file` 与 `file_base64` 同时传入时以 `file` 为准，避免冗余传输。
- 流式模式下需按标准 SSE（`Event Stream`）协议解析，收到 `data: [DONE]` 即结束。

---

## 文本转语音（TTS）

**Endpoint**: `POST /paas/v4/audio/speech`

**用途**: 使用 `GLM-TTS` 模型将文本合成为自然语音，支持多种系统音色/复刻音色、语速语调调节、流式与非流式输出。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | `glm-tts` | 固定为 `glm-tts` |
| `input` | string | 是 | - | 待合成文本，≤1024 字符 |
| `voice` | string | 是 | `tongtong` | 系统音色：`tongtong`（彤彤）/`chuichui`（锤锤）/`xiaochen`（小陈）/`jam`/`kazi`/`douji`/`luodo`；也可传自己复刻出的音色名（见音色复刻） |
| `speed` | number | 否 | `1.0` | 语速，范围 `[0.5, 2]` |
| `volume` | number | 否 | `1.0` | 音量，范围 `(0, 10]` |
| `response_format` | string | 否 | `pcm` | `wav`/`pcm`；**流式输出仅支持 `pcm`** |
| `encode_format` | string | 否 | - | 仅流式返回时生效，`base64`/`hex`，决定分块内容的编码格式 |
| `stream` | boolean | 否 | `false` | `true` 通过 Event Stream 逐块返回音频 |
| `watermark_enabled` | boolean | 否 | `true` | 同图像/视频生成 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/audio/speech \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-tts",
    "input": "你好，欢迎使用智谱开放平台。",
    "voice": "tongtong",
    "response_format": "wav"
  }' --output speech.wav
```

```python
resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/audio/speech",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "glm-tts",
        "input": "你好，欢迎使用智谱开放平台。",
        "voice": "tongtong",
        "response_format": "wav",
    },
)
with open("speech.wav", "wb") as f:
    f.write(resp.content)
```

**示例响应**

非流式响应为二进制音频（`audio/wav` 或原始 `pcm` 字节流），直接落盘或流式播放即可，不是 JSON。

**注意事项**

- 响应不是 JSON，而是音频二进制（或流式场景下的 SSE 数据块），用 `resp.content` 直接写文件，不要 `resp.json()`。
- 流式生成时 `response_format` 只能是 `pcm`，`wav` 只在非流式场景可用。
- `voice` 既可以传官方系统音色，也可以传下面“音色复刻”生成的自定义音色名。

---

## 音色复刻（Voice Clone）

**Endpoint**: `POST /paas/v4/voice/clone`

**用途**: 基于一段示例音频克隆出一个新音色，之后可在 TTS 的 `voice` 参数中直接使用该音色名。

**前置步骤**：先用文件上传接口 `POST /paas/v4/files`（`purpose=voice-clone-input`）上传示例音频，拿到 `file_id`；示例音频 ≤10MB，建议时长 3-30 秒，支持 `mp3`/`wav`。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | `glm-tts-clone` | 固定为 `glm-tts-clone` |
| `voice_name` | string | 是 | - | 指定唯一的音色名称，后续 TTS 的 `voice` 参数会用到 |
| `file_id` | string | 是 | - | 示例音频的 `file_id`（通过 `POST /paas/v4/files` 上传获取） |
| `input` | string | 是 | - | 用该新音色生成试听音频的目标文本 |
| `text` | string | 否 | - | 示例音频对应的文本内容（选填，有助于提升复刻效果） |
| `request_id` | string | 否 | 平台自动生成 | 6-64 字符，建议用 UUID |

**示例请求**

```bash
# 第一步：上传示例音频
curl -X POST https://open.bigmodel.cn/api/paas/v4/files \
  -H "Authorization: Bearer $API_KEY" \
  -F "purpose=voice-clone-input" \
  -F "file=@sample_voice.mp3"

# 第二步：用返回的 file_id 发起音色复刻
curl -X POST https://open.bigmodel.cn/api/paas/v4/voice/clone \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-tts-clone",
    "voice_name": "my_custom_voice",
    "file_id": "file_xxx",
    "input": "这是使用新音色合成的试听文本。"
  }'
```

```python
with open("sample_voice.mp3", "rb") as f:
    up = requests.post(
        "https://open.bigmodel.cn/api/paas/v4/files",
        headers={"Authorization": f"Bearer {API_KEY}"},
        data={"purpose": "voice-clone-input"},
        files={"file": ("sample_voice.mp3", f, "audio/mpeg")},
    )
file_id = up.json()["id"]

resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/voice/clone",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "glm-tts-clone",
        "voice_name": "my_custom_voice",
        "file_id": file_id,
        "input": "这是使用新音色合成的试听文本。",
    },
)
print(resp.json())
```

**示例响应**

```json
{
  "voice": "my_custom_voice",
  "file_id": "file_yyy",
  "file_purpose": "voice-clone-output",
  "request_id": "req_xxx"
}
```

**注意事项**

- `voice_name` 必须全局唯一，重复会冲突；建议加上业务前缀或用户标识避免撞名。
- 响应里的 `file_id` 是新生成的**试听音频文件**（`file_purpose=voice-clone-output`），不是输入音频的 `file_id`。
- 复刻完成后，`voice_name` 就可以作为 TTS 接口 `voice` 参数的值直接使用。

---

## 音色管理

### 音色列表

**Endpoint**: `GET /paas/v4/voice/list`

**用途**: 列出可用音色，支持按名称模糊搜索、按类型（官方/自定义）过滤。

**关键参数**（query string）

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `voiceName` | string | 否 | - | 按音色名称模糊搜索；传中文需做 URL encode |
| `voiceType` | string | 否 | - | `OFFICIAL`（官方音色）/`PRIVATE`（自定义/复刻音色） |

**示例请求**

```bash
curl -G https://open.bigmodel.cn/api/paas/v4/voice/list \
  -H "Authorization: Bearer $API_KEY" \
  --data-urlencode "voiceType=PRIVATE"
```

```python
resp = requests.get(
    "https://open.bigmodel.cn/api/paas/v4/voice/list",
    headers={"Authorization": f"Bearer {API_KEY}"},
    params={"voiceType": "PRIVATE"},
)
print(resp.json()["voice_list"])
```

**示例响应**

```json
{
  "voice_list": [
    {
      "voice": "my_custom_voice",
      "voice_name": "my_custom_voice",
      "voice_type": "PRIVATE",
      "download_url": "https://.../preview.wav",
      "create_time": "2026-08-01 10:00:00"
    }
  ]
}
```

**注意事项**

- 不传任何 query 参数则返回全部音色（官方 + 自定义）。
- `download_url` 是试听音频下载链接，可用于在自己的后台展示音色预览。

### 删除音色

**Endpoint**: `POST /paas/v4/voice/delete`

**用途**: 删除一个自定义（复刻）音色。

**关键参数**

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `voice` | string | 是 | - | 要删除的音色标识（即复刻时的 `voice_name`） |
| `request_id` | string | 否 | 平台自动生成 | 请求唯一标识 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/voice/delete \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"voice": "my_custom_voice"}'
```

```python
resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/voice/delete",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={"voice": "my_custom_voice"},
)
print(resp.json())
```

**示例响应**

```json
{ "voice": "my_custom_voice", "update_time": "2026-09-03 12:00:00" }
```

**注意事项**

- 删除是不可逆操作，且官方音色（`OFFICIAL`）无法删除，只能删除自己复刻的 `PRIVATE` 音色。
- 删除后该 `voice` 名称不能再用于 TTS 接口的 `voice` 参数。
