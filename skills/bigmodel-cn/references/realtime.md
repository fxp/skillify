# GLM-Realtime 实时音视频通话

GLM-Realtime 提供基于 WebSocket 的实时音视频通话和多模态交互能力，支持实时语音对话、视频理解、函数调用等场景。协议定义为 AsyncAPI 规范，与 `references/chat.md` 里的一次性 HTTP 请求/流式响应模型完全不同：这是一条**持续保持打开的双向长连接**，客户端和服务端可以随时互相推送消息。更多模型能力细节参见智谱官方的 GLM-Realtime 模型指南（`/cn/guide/models/sound-and-video/glm-realtime`），本文档只讲协议本身——怎么连接、有哪些消息类型、怎么写一个最小可运行的客户端。

## 连接方式

- 协议：`wss`（WebSocket over TLS）
- Host：`open.bigmodel.cn`
- 完整地址：`wss://open.bigmodel.cn/api/paas/v4/realtime`

### 鉴权

标准方式是在 WebSocket 握手请求头里带：

```
Authorization: Bearer YOUR_API_KEY
```

（格式必须匹配 `^Bearer .+$`。）官方规范里这个请求头被描述为"鉴权信息，支持 JWT（客户端）或 Bearer API Key（服务端）"，也就是区分了两种典型场景：

- **服务端场景**（Node.js / Python 等后端发起连接）：可以像其它 `wss` 客户端一样正常设置 `Authorization: Bearer <API_KEY>` 请求头，直接用 API Key 鉴权。
- **浏览器 / 客户端场景**：由于浏览器的安全限制，浏览器原生 `WebSocket` API **不允许**在握手时添加自定义请求头（包括 `Authorization`），所以不能直接照搬上面服务端的做法。官方文档为此建议改用 JWT 方式鉴权，具体的浏览器端实现（如何签发、通过什么方式传递 JWT）请参考 GLM-Realtime 模型指南页面；本 AsyncAPI 规范本身没有给出浏览器端传参的示例代码。

**实践建议**：如果是给最终用户直接在浏览器里连接模型（语音助手网页等），不要把长期有效的 API Key 硬编码进前端代码；更安全的做法是让自己的后端持有 API Key，由后端代为建立到智谱的 WebSocket 连接（服务端鉴权方式），前端只和自己的后端通信，或者由后端签发短期 JWT 给前端。

生成 JWT 的方式与智谱 HTTP API 的 JWT 鉴权是同一套机制：用 API Key 里 `.` 分隔的 `id` 和 `secret` 两部分，构造包含 `api_key`（即 `id`）、`exp`（过期时间戳，毫秒）、`timestamp`（当前时间戳，毫秒）的 payload，用 `secret` 以 `HS256` 算法签名（`headers={"alg": "HS256", "sign_type": "SIGN"}`）即可得到可用于浏览器端场景的短期 Token，具体实现可参考本技能包对应 HTTP 鉴权说明中的 `PyJWT` 示例。

## 支持的消息类型

每条客户端发出的事件都共享一组公共字段（`BaseEvent`）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event_id` | string | 由客户端生成的事件 ID，用于标识此事件 |
| `type` | string | 事件类型（见下表） |
| `client_timestamp` | integer | 调用端发起调用的时间戳，毫秒 |

### 客户端 → 服务端（send）

| `type` 值 | 用途 | 关键字段 |
| --- | --- | --- |
| `session.update` | 配置或更新会话参数（模型、音频格式、声音、工具、模态等） | `session`（会话配置对象，见下） |
| `input_audio_buffer.append` | 上传一段音频数据 | `audio`：音频（wav 或 pcm）二进制的 base64 编码字符串，必填 |
| `input_audio_buffer.commit` | 提交音频缓冲区（表示一段语音输入结束） | 无附加字段，仅 `type` |
| `response.create` | 请求模型创建一次响应 | 无附加字段，仅 `type` |
| `response.cancel` | 取消正在进行中的响应 | 无附加字段，仅 `type` |

### 服务端 → 客户端（receive）

| `type` 值 | 用途 | 关键字段 |
| --- | --- | --- |
| `session.created` | 连接建立后服务端**自动**推送的初始会话状态（不是对 `session.update` 的回执，握手一成功就会收到，早于任何客户端消息）；见下方验证说明 | `session`（初始/默认配置对象，字段与 `session.update` 基本一致） |
| `session.updated` | 确认会话配置已生效，回显完整的会话配置 | `session`（同 `session.update` 里的配置对象） |
| `response.created` | 响应开始创建，返回初始 `response` 对象 | `response.id`、`response.object`（固定为 `realtime.response`）、`response.status` |
| `response.audio.delta` | 流式返回一段音频增量 | `response_id`、`item_id`、`output_index`、`content_index`、`delta`（base64 编码的 PCM 音频数据增量，24kHz 单声道） |
| `response.text.delta` | 流式返回一段文本增量 | `response_id`、`item_id`、`delta`（模型生成的文本片段） |
| `response.done` | 响应结束，返回带最终 `usage` 统计的完整 `response` 对象 | `response.status`、`response.usage` |
| `error` | 服务器错误信息 | `error.code`、`error.message`（实测未观察到独立的 `error.type` 字段，见下方验证说明） |
| `heartbeat` | 心跳信号，用于保持 WebSocket 连接活跃 | 仅 `type: "heartbeat"`、`event_id`、`client_timestamp` |

> **已用真实 WebSocket 连接验证（2026-09）**：用文档里的连接方式（`wss://open.bigmodel.cn/api/paas/v4/realtime` + `Authorization: Bearer <API_KEY>` 请求头）成功建立了连接，证实鉴权方式文档无误。但实测到的事件序列和本文档早期版本的描述有出入，已在上表订正：连接建立后立即收到一条 `heartbeat`，紧接着是一条**规范原本没有列出的 `session.created` 事件**（携带一个默认会话对象，此时客户端的 `session.update` 消息可能还没被处理），而不是文档一开始假设的"服务端先回 `session.updated`"。实测返回的 `session.created.session.model` 是 `"glm-realtime"`，与请求里传的 `"glm-realtime-flash"` 不同——具体是命名归一化还是账号权限导致的替换未定论。此外单次连接实测中途收到过 `{"type":"error","error":{"code":"downstream_reconnect_exceeded","message":"下游重连次数超限（3/3），连接关闭"}}` 并断开，这看起来更像是测试时后端不稳定/限流，而不是请求本身有误——`error.type` 字段在这次实测响应里没有出现，只有 `code`/`message`。**给使用本协议的开发者的建议**：不要死等 `session.updated` 才认为连接就绪，`session.created`/`heartbeat` 都可能先到；`error` 事件要做好断线重连；工具调用等更细的行为建议先用一次真实连接跑通再定协议假设，不要完全依赖本文档或规范文件的字面描述。
>
> 本 AsyncAPI 规范本身也没有单独给出"函数调用结果"专属的事件 schema——`session.update` 里可以配置 `tools` 列表（当前仅 `audio` 模式支持工具调用），但工具调用的触发/结果具体走哪个事件字段，规范未明确列出，实现时请以官方最新文档或联调时观察到的实际消息为准。

### 会话配置对象（`session.update` 里的 `session` 字段）

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `model` | string | - | `glm-realtime-flash` 或 `glm-realtime-air` |
| `input_audio_format` | string | `wav` | 音频输入格式，支持 `wav`、`pcm`；输入 PCM 格式需要标注采样率，如 `pcm16`、`pcm24`（必填） |
| `output_audio_format` | string | 固定 `pcm` | 音频输出格式，当前仅支持 `pcm`，采样率 24kHz、单声道、16 位深（必填） |
| `instructions` | string | - | 系统指令，用于引导模型生成期望的响应 |
| `voice` | string | `tongtong` | 声音类型：`tongtong` / `female-tianmei` / `male-qn-daxuesheng` / `male-qn-jingying` / `lovely_girl` / `female-shaonv` |
| `temperature` | number | - | 模型温度，控制输出的随机性和创造性，区间 0-1 |
| `max_response_output_tokens` | string | - | 回复的最大长度，对应文本 token 计数，范围 0-1024 |
| `turn_detection.type` | string | `client_vad` | VAD（语音活动检测）类型：`server_vad` 或 `client_vad`（必填） |
| `tools` | array | - | 工具（函数调用）列表，每项含 `type`（固定 `function`）、`name`、`description`、`parameters`；当前仅 `audio` 模式支持 |
| `modalities` | array | `["text", "audio"]` | 输出模态，可选 `text` 和/或 `audio` |
| `input_audio_noise_reduction.type` | string | - | 降噪类型：`near_field`（近距离麦克风）或 `far_field`（远距离麦克风） |
| `beta_fields.chat_mode` | string | `audio` | 通话模式：`audio` 或 `video_passive`（必填，属于 `beta_fields` 内） |
| `beta_fields.tts_source` | string | 固定 `e2e` | 文本转语音方式 |
| `beta_fields.auto_search` | boolean | `true` | 是否开启内置自动搜索，仅在 `audio` 模式下生效 |
| `greeting_config.enable` | boolean | - | 是否开启开场白 |
| `greeting_config.content` | string | - | 开场白内容 |

`session` 对象里 `input_audio_format`、`output_audio_format`、`turn_detection` 三个字段是必填的。

### `response` 对象结构（`response.created` / `response.done` 共用）

`response.created` 和 `response.done` 事件里都带一个 `response` 对象，字段完全相同，区别只是 `response.created` 推送时状态通常是 `in_progress`（响应刚开始），`response.done` 推送时是最终状态（带完整的 `usage` 统计）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 响应的唯一 ID（必填） |
| `object` | string | 固定为 `realtime.response`（必填） |
| `status` | string | 响应状态：`completed` / `cancelled` / `failed` / `incomplete` / `in_progress`（必填） |
| `usage.total_tokens` | integer | 总共使用的令牌数量 |
| `usage.input_tokens` | integer | 输入令牌数量 |
| `usage.output_tokens` | integer | 输出令牌数量 |
| `usage.input_token_details.cached_tokens` | integer | 使用缓存令牌的数量 |
| `usage.input_token_details.text_tokens` | integer | 输入中文本令牌的数量 |
| `usage.input_token_details.audio_tokens` | integer | 输入中音频令牌的数量 |
| `usage.output_token_details.text_tokens` | integer | 输出中文本令牌的数量 |
| `usage.output_token_details.audio_tokens` | integer | 输出中音频令牌的数量 |

### 关键事件的原始 JSON 示例

以下示例摘自官方 AsyncAPI 规范（字段名均为真实字段，值为占位符），可以直接对照理解每类事件的 JSON 结构：

`response.audio.delta` / `response.text.delta`（两者结构一致，只是 `type` 和 `delta` 的内容含义不同）：

```json
{
  "event_id": "<string>",
  "type": "response.audio.delta",
  "response_id": "<string>",
  "item_id": "<string>",
  "output_index": 123,
  "content_index": 123,
  "delta": "<string>"
}
```

`error`：

```json
{
  "event_id": "<string>",
  "type": "error",
  "error": {
    "type": "<string>",
    "code": "<string>",
    "message": "<string>"
  }
}
```

`heartbeat`：

```json
{
  "type": "heartbeat"
}
```

## 典型交互流程

1. **建立连接**：客户端以 `wss://open.bigmodel.cn/api/paas/v4/realtime` 发起 WebSocket 握手（服务端场景带 `Authorization: Bearer <API_KEY>` 请求头）。
2. **发送会话配置**：连接建立后立即发送一条 `session.update` 事件，设置 `model`、音频格式、`voice`、`turn_detection`（决定是服务端自动判断说话结束还是客户端自己判断）、`tools`、`modalities` 等参数。
3. **等待确认**：服务端回一条 `session.updated`，回显生效后的完整会话配置。
4. **发送音频/文本流**：
   - 持续发送 `input_audio_buffer.append`，把麦克风采集到的音频块以 base64 编码逐段推给服务端。
   - 若 `turn_detection.type` 为 `client_vad`，需要客户端自己判断语音段落结束，然后发送 `input_audio_buffer.commit` 提交缓冲区，再发送 `response.create` 触发模型生成响应；若为 `server_vad`，服务端会自动检测语音停顿并触发响应。
5. **接收模型回复**：服务端先推送 `response.created`（带初始状态的 `response` 对象），随后连续推送多条 `response.audio.delta`（语音增量，需要客户端自行拼接/播放）和 `response.text.delta`（文本增量，如果 `modalities` 里包含 `text`），最后以 `response.done`（带最终 `usage` 统计）结束这一轮响应。
6. **打断/取消**：如果在模型还在生成时想打断，发送 `response.cancel`。
7. **心跳与保活**：服务端会周期性推送 `heartbeat` 事件用于保持连接活跃；规范未说明客户端是否需要显式回应，正常维持底层 WebSocket 连接（不主动断开、不超时）即可。
8. **异常处理**：任何阶段服务端都可能推送 `error` 事件（含 `type`/`code`/`message`），客户端应监听并做相应的重试或提示。
9. **结束会话**：业务逻辑结束后，客户端直接关闭底层 WebSocket 连接即可（规范中没有单独定义"结束会话"的专属事件）。

### `item_id` / `output_index` / `content_index` 的语义

`response.audio.delta` 和 `response.text.delta` 里除了 `response_id`（本轮响应的唯一 ID）之外，还带三个用于定位增量数据归属的字段：

- `item_id`：这条增量属于响应内哪一个"会话项"（一次 `response` 内部可能包含多个 item，例如先有一段文本、再有一段音频）。
- `output_index`：该 item 在这次 `response` 的输出列表里的索引。
- `content_index`：该 item 内容数组中，这段内容片段的索引（用于同一个 item 里可能存在多段内容的情况）。

拼接流式音频/文本时，建议按 `item_id` + `content_index` 分组累加 `delta`，而不是简单假设消息按单一顺序到达——尤其是在开启多模态（`modalities: ["text", "audio"]`）同时输出文本和语音的场景下，两类 `delta` 事件会交替出现。

## Python 最小骨架示例（`websockets` 库）

以下示例演示服务端场景下的连接、发送 `session.update`、推送一段音频、以及按 `type` 字段分发接收到的流式事件。字段名均来自上文表格，未做任何编造：

```python
import asyncio
import base64
import json

import websockets

API_KEY = "YOUR_API_KEY"
URL = "wss://open.bigmodel.cn/api/paas/v4/realtime"


async def run_session():
    headers = {"Authorization": f"Bearer {API_KEY}"}

    async with websockets.connect(URL, extra_headers=headers) as ws:
        # 1. 发送会话配置
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "model": "glm-realtime-flash",
                "input_audio_format": "wav",
                "output_audio_format": "pcm",
                "voice": "tongtong",
                "turn_detection": {"type": "server_vad"},
                "modalities": ["text", "audio"],
                "instructions": "你是一个友好的语音助手",
            },
        }))

        # 2. 推送一段音频（示例：读取本地 wav 文件并整体作为一次 append）
        with open("input.wav", "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")
        await ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": audio_b64,
        }))
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        await ws.send(json.dumps({"type": "response.create"}))

        # 3. 接收流式响应
        audio_chunks = []
        async for raw_message in ws:
            event = json.loads(raw_message)
            event_type = event.get("type")

            if event_type == "session.created":
                # 连接建立后服务端自动推送，早于 session.updated；实测里排在 heartbeat 之后
                print("收到初始会话状态:", event["session"]["model"])

            elif event_type == "session.updated":
                print("会话配置已生效:", event["session"]["model"])

            elif event_type == "response.created":
                print("开始生成响应:", event["response"]["id"])

            elif event_type == "response.text.delta":
                print(event["delta"], end="", flush=True)

            elif event_type == "response.audio.delta":
                audio_chunks.append(base64.b64decode(event["delta"]))

            elif event_type == "response.done":
                print("\n响应完成，usage:", event["response"].get("usage"))
                break

            elif event_type == "error":
                print("服务器错误:", event["error"])
                break

            elif event_type == "heartbeat":
                # 心跳事件，维持连接，无需特殊处理
                continue

        # 拼接并保存收到的 PCM 音频（24kHz、单声道、16 位）
        if audio_chunks:
            with open("output.pcm", "wb") as f:
                f.write(b"".join(audio_chunks))


asyncio.run(run_session())
```

浏览器端场景中，由于无法直接设置 `Authorization` 请求头，需要按照 GLM-Realtime 模型指南里描述的 JWT 方式改造鉴权部分（例如通过后端签发短期凭证），其余消息收发逻辑与上述示例一致。

## 注意事项

- **适用场景**：语音助手、实时客服、陪练对话等需要低延迟、双向、可打断的语音（及视频理解）交互场景。`beta_fields.chat_mode` 支持 `video_passive`，说明该接口也用于视频理解场景，但本规范给出的消息类型里没有单独列出"发送视频帧"的事件 schema，具体的视频输入方式请以模型指南或联调实测为准。
- **和普通 `chat/completions` 流式输出的区别**：
  - `chat/completions` 的 `stream=true` 是一次性 HTTP 请求 + 单向 SSE 流，服务端只能向客户端推送文本增量，请求发出后无法再修改这次请求、也无法中途打断。
  - GLM-Realtime 是长期保持的 WebSocket 双向连接：客户端可以持续推流式输入（音频块）、可以随时发 `response.cancel` 打断正在生成的响应、服务端也可以在同一条连接上推送多轮响应（`session.update` 之后可以反复发起多轮 `response.create`）。
- **音频格式**：输出格式固定为 `pcm`（24kHz、单声道、16 位深），不可配置；输入格式支持 `wav` 或 `pcm`，用 `pcm` 时需要在格式字符串里标注采样率（如 `pcm16`、`pcm24`）。
- **VAD 模式选择**：`turn_detection.type` 为 `server_vad` 时，模型自动检测语音停顿并触发响应，客户端只需持续 `append` 音频；为 `client_vad`（默认）时，客户端需要自己判断说话结束的时机，主动发送 `input_audio_buffer.commit` + `response.create`。
- **鉴权方式选择**：服务端环境直接用请求头 `Authorization: Bearer <API_KEY>`；浏览器环境不能加鉴权请求头，需改走 JWT 方案，具体步骤参见 GLM-Realtime 模型指南页面。
