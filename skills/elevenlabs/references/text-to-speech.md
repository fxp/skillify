# 文本转语音 Text to Speech

> 来源：`api-reference/text-to-speech/{convert,stream,v-1-text-to-speech-voice-id-stream-input}.md`、`eleven-api/guides/how-to/text-to-speech/{streaming,request-stitching,pronunciation-dictionaries}.md`、`eleven-api/guides/how-to/best-practices/latency-optimization.md`（抓取于 2026-09-21）。**⚠ 全文未用真实 API Key 验证**，字段名、默认值、报错行为均为文档/OpenAPI 导出页原文转录。

## 目录

- [三种调用形态怎么选](#三种调用形态怎么选)
- [批量端点：Create speech](#批量端点create-speech)
- [SSE 流式端点：Stream speech](#sse-流式端点stream-speech)
- [WebSocket 端点：双向流式](#websocket-端点双向流式)
- [请求拼接（保持多段语音的韵律连续）](#请求拼接保持多段语音的韵律连续)
- [发音词典](#发音词典)
- [延迟优化四原则](#延迟优化四原则)

## 三种调用形态怎么选

| 形态 | Endpoint | 协议 | 适合场景 |
| :--- | :--- | :--- | :--- |
| 批量 | `POST /v1/text-to-speech/{voice_id}` | HTTP，一次性返回完整音频文件 | 文本提前已知、不在意首字节延迟 |
| SSE 流式 | `POST /v1/text-to-speech/{voice_id}/stream` | HTTP，逐块用 Server-Sent Events 返回 | 文本提前已知，但想尽快开始播放（降低 TTFB） |
| WebSocket | `GET/WS /v1/text-to-speech/{voice_id}/stream-input` | `wss://`，双向流式 | 文本是边生成边喂进来的（比如接在 LLM 输出流后面），需要词到音频的对齐信息 |

**这不是同一个 endpoint 加参数切换的关系，是三个不同的 URL、不同的鉴权/参数携带方式。** 批量和 SSE 流式都是普通 HTTP POST，鉴权走 `xi-api-key` header、参数走 query string + JSON body；WebSocket 端点鉴权和大部分参数都在**连接时的 query string**里传（`model_id`、`language_code`、`output_format`、`auto_mode` 等，`xi-api-key` 通过 header 或握手时传），文本内容则通过后续帧以 JSON 消息逐条发送，不是一次性 HTTP body。

官方原文明确说 WebSocket "不是万能方案"：如果文本一开始就是完整的，用 WebSocket 反而因为缓冲机制可能比 SSE 流式或批量端点延迟更高；只有当文本本身是流式产生的（LLM 边吐 token 边喂给 TTS）时才应该选 WebSocket。**语音 Agent 场景（LLM 流式输出接 TTS）应该用 WebSocket；"把一整篇稿子念出来"场景不应该用 WebSocket。**

## 批量端点：Create speech

**Endpoint**: `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`
**Content-Type**: `application/json`，响应是音频文件（`Accept: audio/mpeg` 等）

**路径参数**
| 参数 | 说明 |
| :--- | :--- |
| `voice_id` | 目标声音 ID，用 `GET /v1/voices/search` 列出可用声音 |

**关键 query 参数**
| 参数 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `output_format` | enum | `mp3_44100_128` | 格式为 `codec_采样率_比特率`；192kbps MP3 需 Creator 及以上套餐，44.1kHz 的 PCM/WAV 需 Pro 及以上套餐；`ulaw_8000` 常用于 Twilio 音频输入 |
| `enable_logging` | boolean | `true` | 设为 `false` 即 Zero Retention Mode，**⚠ 文档原文写明仅 Enterprise 客户可用**，非企业账号传了会怎样未说明 |
| `optimize_streaming_latency` | integer, 已废弃 | — | 0~4 档延迟优化，官方标注 deprecated，新代码不要用 |

**关键 body 字段**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `text` | string | 是 | — | 要转换的文本 |
| `model_id` | string | **否** | `eleven_multilingual_v2` | ⚠ 见 SKILL.md 通用规则第 3 条：TTS 的 model_id 缺省会静默落到这个默认值，不报错 |
| `language_code` | string | 否 | — | ISO 639-1，用于强制语言；`multilingual_v2` 系列**不支持**这个参数（模型不支持时会被忽略，不报错，⚠ 文档原文） |
| `voice_settings` | object | 否 | — | `stability`（0~1，默认 0.5，越低情感越丰富越不稳定）、`similarity_boost`（默认 0.75）、`style`（默认 0，放大风格但增加延迟）、`use_speaker_boost`（默认 true，增加计算量和延迟）、`speed`（默认 1.0，范围按 WS 规范是 0.7~1.2） |
| `pronunciation_dictionary_locators` | array | 否 | — | 最多 3 个发音词典 locator，按顺序应用 |
| `seed` | integer | 否 | — | 尽力保证确定性输出，不保证 |
| `previous_text` / `next_text` | string | 否 | — | 用于拼接多段生成时保持韵律连续，见下文"请求拼接" |
| `previous_request_ids` / `next_request_ids` | array | 否 | — | 同上，效果优先于 `previous_text`/`next_text`（两者都传时文本参数被忽略），单次最多 3 个 |
| `apply_text_normalization` | enum | `auto` | `auto`/`on`/`off`，Flash 系模型默认关闭数字正规化，见 `models.md` |
| `apply_language_text_normalization` | boolean | `false` | 仅日语有效，**文档原文警告会显著增加延迟** |
| `use_pvc_as_ivc` | boolean, 已废弃 | `false` | 临时工作区：为 true 时 PVC 声音改用 IVC 版本生成，用于规避 PVC 版本延迟更高的问题 |

**响应**：200 直接是音频二进制；422 是标准 Validation Error（`detail[].loc/msg/type`）。响应 header 里有 `character-cost`（本次生成消耗的字符/credits 数）和 `request-id`（拼接后续请求要用）。

**最小示例**

```bash
curl -X POST "https://api.elevenlabs.io/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb?output_format=mp3_44100_128" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello World!", "model_id": "eleven_flash_v2_5"}' \
  --output out.mp3
```

```python
from elevenlabs.client import ElevenLabs

client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
audio = client.text_to_speech.convert(
    voice_id="JBFqnCBsd6RMkjVDRZzb",
    text="Hello World!",
    model_id="eleven_flash_v2_5",
    output_format="mp3_44100_128",
)
```

## SSE 流式端点：Stream speech

**Endpoint**: `POST /v1/text-to-speech/{voice_id}/stream`，参数与批量端点基本一致（同一套 body/query 字段），区别只在响应是逐块音频而不是一次性文件。SDK 用法：

```python
audio_stream = client.text_to_speech.stream(
    voice_id="pNInz6obpgDQGcFmaJgB",
    text=text,
    model_id="eleven_flash_v2_5",
)
for chunk in audio_stream:
    ...  # 边收边播放/边转发
```

## WebSocket 端点：双向流式

**Endpoint**: `wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input`（区域端点同理换 host，见 SKILL.md）

**连接参数（query string，非 body）**：`model_id`、`language_code`、`enable_logging`、`output_format`、`inactivity_timeout`、`sync_alignment`、`auto_mode`、`apply_text_normalization`、`seed`、`enable_ssml_parsing`、`authorization`/`single_use_token`。鉴权 header 仍可用 `xi-api-key`。

**服务端下发的消息类型**（二选一）：
- `AudioOutput`：`{"audio": "<base64 PCM/MP3 chunk>", "normalizedAlignment": {...}, "alignment": {...}}` —— `alignment`/`normalizedAlignment` 给出逐字符的时间戳，用于做字幕/唇形同步
- `FinalOutput`：`{"isFinal": true}`，此时 `audio` 为 null，表示这次生成已结束

**分块调度（`chunk_length_schedule`）**：WebSocket 端有一个缓冲机制，默认 `[120, 160, 250, 290]`——意思是收满 120 字符才开始生成第一块音频，再收满 160 字符生成第二块，以此类推。**`auto_mode=true` 时这套调度被自动接管，不需要手动攒够字符数**；如果关闭 `auto_mode` 又按小段文本高频发送（比如每次只发 50 字符，达不到 120 的门槛），模型会一直等到凑够字符才生成，**延迟不降反升**——latency-optimization 原文明确点了这个坑。语音 Agent 接 LLM 流式输出的场景，优先开 `auto_mode=true`。

**`RealtimeVoiceSettings`**：`speed` 参数范围是 **0.7~1.2**（与批量端点 `voice_settings.speed` 文档未标注范围不同，⚠ 文档自相矛盾，未验证是否 WS 端严格校验范围而批量端点不校验）。

## 请求拼接（保持多段语音的韵律连续）

大段文本分多次请求生成时，段落之间的语调容易"跳变"。用 `previous_request_ids`（把上一次生成返回的 `request-id` 响应头传进下一次请求）或 `previous_text`/`next_text`（直接传相邻文本内容）可以让模型据此维持韵律连续。**两者都传时 `previous_request_ids` 优先，`previous_text` 会被忽略**（文档原文）。`request-id` 只能从响应头拿，SDK 里要用 `with_raw_response` 变体才能读到 header（普通 `convert()` 调用拿不到）。

**⚠ `eleven_v3` 不支持请求拼接**（文档原文明确排除），只对 `eleven_multilingual_v2` 等其他模型有效。

## 发音词典

用 IPA 或 CMU 音标文件（`.pls` 格式）自定义特定词的发音，常用于纠正人名、地名、专业术语。**⚠ 关键限制**：音标标签（phoneme tag）只在 `eleven_flash_v2` 和 `eleven_v3` 两个模型上生效；其他模型（包括 `eleven_multilingual_v2`）会**静默跳过**音标标签、退回默认发音（不报错，容易误以为词典没生效是配置错误）。非英语场景要用 IPA/CMU 音标必须切到 `eleven_v3`。其他模型想控制发音只能用"alias 标签"（替换成拼写近似正确发音的写法），不是音标级别的精确控制。

发音词典通过 `pronunciation_dictionary_locators` 参数挂到具体请求上，一次最多挂 3 个，按数组顺序应用。

## 延迟优化四原则

官方 `latency-optimization.md` 把优化点归纳为四条：

1. **用 Flash 模型**：~75ms 推理延迟，代价是质量略降于 Multilingual v2。
2. **用流式（SSE 或 WebSocket）而不是批量端点**：降低 TTFB。SSE/WS 支持范围：Text to Speech、Voice Changer（Speech-to-Speech）、Audio Isolation 都有对应的 `/stream` 端点。
3. **选对地理区域**：`api.elevenlabs.io` 默认按就近路由（当前落地区域：美国、荷兰、新加坡），响应头 `x-region` 可查看实际命中区域；要固定美区可显式切到 `api.us.elevenlabs.io`（此前的 `api-global-preview.elevenlabs.io` 已废弃，全局路由现在是默认行为，不需要再显式 opt-in）。企业数据驻留（欧盟/印度专属环境）需要销售侧单独开通。
4. **选对声音类型**：延迟从快到慢依次是"默认声音（原 premade）/合成声音/IVC" → "PVC"。官方原文说明团队正在优化 PVC 在 Flash v2.5 上的延迟，**目前 PVC 声音用在低延迟场景本身就是一个已知的性能劣势，不是配置问题**。输出格式（`output_format`）质量越高（更高采样率/比特率）延迟也越高，需要按场景权衡。
