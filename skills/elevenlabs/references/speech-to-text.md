# 语音转文本 Speech to Text（Scribe）

> 来源：`api-reference/speech-to-text/{convert,v-1-speech-to-text-realtime}.md`、`overview/capabilities/speech-to-text.md`、`eleven-api/guides/how-to/speech-to-text/{batch/webhooks,batch/multichannel-transcription,batch/keyterm-prompting,realtime/client-side-streaming,realtime/server-side-streaming}.md`（抓取于 2026-09-21）。**⚠ 全文未用真实 API Key 验证。**

## 目录

- [批量转录](#批量转录)
- [附加参数的隐藏加价](#附加参数的隐藏加价)
- [Webhook 异步转录](#webhook-异步转录)
- [多声道转录](#多声道转录)
- [实时转录（WebSocket）](#实时转录websocket)
- [文件与格式限制](#文件与格式限制)

## 批量转录

**Endpoint**: `POST https://api.elevenlabs.io/v1/speech-to-text`，`multipart/form-data`

**关键字段**
| 参数 | 必填 | 说明 |
| :--- | :--- | :--- |
| `model_id` | **是** | ⚠ 与 TTS 相反，这里没有默认值，不传直接 422（文档原文标注 required；见 SKILL.md 通用规则第 3 条） |
| `file` | 否（与 `source_url` 二选一） | 最小音频长度 100ms，最大 5GB |
| `source_url` | 否 | 支持 HTTPS 直链、YouTube、TikTok 链接；替代已废弃的 `cloud_storage_url`（该参数文档标 Deprecated，仍可用但会被移除） |
| `language_code` | 否 | 不传则自动检测语言 |
| `diarize` | 否 | 说话人分离开关，最多识别 32 个说话人 |
| `num_speakers` | 否 | 显式指定说话人数上限，与 `diarization_threshold` 互斥（只能设置其中一个） |
| `timestamps_granularity` | 否 | `word`（词级）或 `character`（字符级） |
| `webhook` | 否 | 见下文"Webhook 异步转录" |
| `use_multi_channel` | 否 | 见下文"多声道转录" |
| `no_verbatim` | 否 | 仅 `scribe_v2` 支持，开启后去掉填充词/口误，适合字幕/摘要场景 |

**响应**：200（同步）直接返回 `SpeechToTextChunkResponseModel`（含 `text`、`words[]`，每个词有 `start`/`end`/`speaker_id`、`type` 为 `word`/`spacing`/`audio_event` 三类之一）；202 表示走了异步路径（见 webhook）。

## 附加参数的隐藏加价

**⚠ 这是本文档少见的、官方在字段说明里直接写了价格影响的地方，不是"未说明"，是明确写了但很容易被忽略：**

| 参数 | 额外费用 | 说明 |
| :--- | :--- | :--- |
| `keyterms` | **基础转录费 +20%** | 最多 1000 个关键词（每个 ≤50 字符，≤5 个词），超过 100 个关键词时单次请求**最低按 20 秒计费** |
| `entity_detection` | **基础转录费 +30%** | 检测 `pii`/`phi`/`pci`/`other`/`offensive_language` 等类别实体 |
| `entity_redaction` | **基础转录费 +30%** | 必须是 `entity_detection` 集合的子集；开启后响应里不再返回 `entities` 字段 |
| `detect_speaker_roles` | **基础转录费 +10%** | 要求 `diarize=true`，且不能和 `use_multi_channel=true` 同时使用；开启后 `speaker_id` 从 `speaker_0/1/...` 变成语义化的 `agent`/`customer` |

这些参数**不会报错、也不会在响应里提醒你多付了钱**——传了就按新费率计费，是纯粹的"选项越多越贵"，容易在写批量转录脚本时因为图省事全部打开而不知不觉推高账单。生产环境按需开启，不要把这些参数当默认全量开启的"更全的转录结果"。

## Webhook 异步转录

请求体加 `webhook: true`（可选 `webhook_id` 指定具体某个 webhook，不传则发给该 workspace 配置的所有 STT webhook），响应立即返回（202），转录完成后 ElevenLabs 向 Dashboard 里配置的回调 URL 发 POST。Webhook 鉴权方式是 HMAC 或 OAuth，**文档原文明确写"由客户端自行实现验证，ElevenLabs 只是发送允许验证的 header，不强制校验"**——也就是说不做签名校验也能收到回调，但生产环境应该自己校验签名，不能假设"能收到就是合法请求"。`webhook_metadata` 可以带最大 16KB、最多 2 层深度的自定义 JSON，用于请求关联。

## 多声道转录

`use_multi_channel=true`，最多支持 5 个声道，每个声道当作独立说话人独立转录（`channel_index` 字段标出每个词属于哪个声道）。`multichannel_output_style` 控制输出形状：默认 `separate`（每声道一份 transcript，在 `transcripts[]` 数组里），`combined` 把所有声道按时间排序合并成一份（**⚠ combined 模式要求 `timestamps_granularity` 不能是 none，且不支持实体检测/脱敏**）。

**⚠ 计费坑**：文档原文写明"每个声道按完整音频时长独立计费"，即一段 10 分钟的 5 声道录音是按 50 分钟计费，不是按 10 分钟的整体时长计费。多声道场景做成本估算前一定要按这条算。

**⚠ 时长限制不一致**：`overview/capabilities/speech-to-text.md` 的 "Key facts" 部分写多声道模式上限是 1 小时，但同一份文档正文里 FAQ 部分写的是"合并后各声道总时长不超过 10 小时"（标准模式）——两处口径不完全一致，标 `⚠ 文档自相矛盾`，验证时留意具体触发的上限。

## 实时转录（WebSocket）

**Endpoint**: `wss://api.elevenlabs.io/v1/speech-to-text/realtime`（`GET` 升级为 WS），模型固定用 `scribe_v2_realtime`。

**鉴权两种方式**：服务端直连用 `xi-api-key` header；**客户端（浏览器/移动端）场景必须用一次性 token**（`token` query 参数），通过服务端先调 `POST /v1/single-use-token`（或 SDK 的 `client.tokens.single_use.create("realtime_scribe")`）换取，**token 15 分钟后过期、只能用一次**。绝不能把 `xi-api-key` 直接下发到客户端——这是文档反复强调的一条硬规则,不是建议。

**连接参数（query string）**：`model_id`、`token`、`audio_format`、`language_code`、`secondary_languages`、`commit_strategy`（手动 commit 还是 VAD 自动 commit）、`vad_threshold`、`vad_silence_threshold_secs`、`min_speech_duration_ms`、`min_silence_duration_ms`、`include_timestamps`、`include_language_detection`、`keyterms`（实时场景上限降到 **50 个关键词，每个 ≤20 字符**，明显低于批量的 1000/50）、`no_verbatim`、`entity_detection`、`filter_background_audio`、`enable_logging`。

**事件流**：客户端发 `input_audio_chunk` 消息推音频；服务端下发 `partial_transcript`（未定稿，随时可能被后续内容覆盖）和 `committed_transcript`（该语音段已定稿）。commit 触发方式二选一：手动调用 commit，或让 VAD（静音检测）自动判定语音段结束。

**支持音频格式**：PCM（8kHz~48kHz）和 μ-law 编码。

## 文件与格式限制

- 最大文件体积：**3 GB**（批量转录，`file` 参数；`source_url` 走 URL，另有独立的 2GB 限制标注在已废弃的 `cloud_storage_url` 参数上，⚠ 文档未明确 `source_url` 是否也是 2GB）
- 最长时长：标准模式 10 小时，多声道模式见上文"多声道转录"里的矛盾点
- 支持音频格式：AAC、AIFF、OGG、MP3、OPUS、WAV、FLAC、M4A、WebM 等
- 支持视频格式：MP4、AVI、MKV、MOV、WMV、FLV、WebM、MPEG、3GPP（会自动抽取音轨转录）
