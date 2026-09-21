# 语音通话与 TwiML — 两个方向相反、却都叫"Twilio API"的东西

⚠ 本文件里的每一条陈述都是 `⚠ 文档原文，未实测`（来自 `docs.twilio.com/voice/api`、`docs.twilio.com/voice/twiml*`，以及 `twilio_api_v2010` OpenAPI 规范里的 `Api20100401Call` 定义，抓取于 2026-09-21），除非另有标注。

## 目录
- 这个坑：两种不相关的响应格式，方向相反
- 发起一通外呼 —— REST 的 Calls 资源
- TwiML 具体是什么
- 处理一通入站来电 —— 你的 webhook 必须返回 TwiML
- 关键 TwiML 动词
- 用 SDK 生成 TwiML，还是手写 XML
- 应答机检测（Answering Machine Detection）
- 常见错误

## 这个坑：两种不相关的响应格式，方向相反

下面这两者都叫"Twilio Voice API"，因为它们共用一些词汇（都在讲"call"），很容易被混为一谈，但它们控制的是**信息流的两个相反方向**：

| | REST Calls API | TwiML |
|---|---|---|
| 谁发起 | **你**调用 Twilio（`POST /Calls.json`） | **Twilio** 调用**你的服务器**（一个 webhook 请求） |
| 格式 | HTTPS 上的 JSON 请求/响应，HTTP Basic 鉴权 | 你的服务器作为 HTTP 响应体返回的 XML 文档 |
| 用途 | 把一通通话当作资源来发起、查询、修改或挂断 | 告诉 Twilio *接下来在一通进行中的通话里做什么*（念一段文字、收集按键、拨给另一方、录音、挂断） |
| 什么时候用 | 用程序发起一通外呼 | 每次 Twilio 需要指令的时候：外呼刚接通时，或者有人拨打你的 Twilio 号码的那一刻 |

**一个只知道"Twilio 的 API 返回 JSON"的 Agent，在这里很容易搞反方向**：当 Twilio 请求你的 webhook URL 时（因为有人拨打了你的 Twilio 号码，或者因为一个 `<Gather>`/`<Dial>` 执行完了），你的服务器对*这个*请求的 HTTP 响应必须是 **TwiML（XML）**，不是 JSON——即便你调用过的其他所有 Twilio 端点都是返回 JSON 的。从一个语音 webhook 返回 JSON 不会"优雅降级"——Twilio 没法把它当作通话指令来解析，这通电话通常会直接出错或被挂断。

## 发起一通外呼 —— REST 的 Calls 资源

**Endpoint**：`POST https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Calls.json`
鉴权：HTTP Basic（见 `references/auth.md`）。Body：`application/x-www-form-urlencoded`。

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `To` | string（E.164 / SIP / client） | **是** | E.164 规则和 Messages 一样——见 `references/send-sms.md`。 |
| `From` | string（E.164 / client） | **是** | 必须是你名下的 Twilio 号码，或一个已验证的 Outgoing Caller ID。 |
| `Url` **或** `Twiml` **或** `ApplicationSid` | — | 三选一 | 告诉 Twilio 通话接通后要执行哪段 TwiML——见下一节。`Twiml` 是内联的（最多 4000 字符），如果同时给了 `Url` 会被忽略。 |
| `Method` | `GET`/`POST` | 否 | 获取 `Url` 时用的 HTTP 方法。默认 `POST`。 |
| `StatusCallback` / `StatusCallbackEvent` | string / array | 否 | 通知用的 webhook + 要通知哪些事件（`initiated`/`ringing`/`answered`/`completed`）。 |
| `Record` | boolean | 否 | 录制整通电话；默认 `false`。 |
| `MachineDetection` | `Enable` / `DetectMessageEnd` | 否 | 见下方"应答机检测"。 |
| `Timeout` | integer（秒） | 否 | 放弃前的响铃时长；默认 60，最大 600。 |

```bash
curl -X POST "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/Calls.json" \
  -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
  --data-urlencode "To=+14155552671" \
  --data-urlencode "From=+14155238886" \
  --data-urlencode "Url=https://example.com/voice/answer"
```

```python
call = client.calls.create(
    to="+14155552671",
    from_="+14155238886",
    url="https://example.com/voice/answer",  # 通话接通后 Twilio 会 GET/POST 这个地址，期望拿到 TwiML
)
print(call.sid, call.status)
```

创建响应是 JSON，这里的 `status` 是通话这个 REST 资源自己的生命周期状态（`queued`、`ringing`、`in-progress`、`completed`、`busy`、`failed`、`no-answer`、`canceled`）——**不是** TwiML，用的也不是 Message 资源那套状态词汇。

## TwiML 具体是什么

TwiML（Twilio Markup Language）是一份 XML 文档，里面是 Twilio 定义的标签（"动词"），告诉 Twilio 在一通通话中该做什么（或者，以一种平行的形式，在一段短信对话中该做什么——见 `docs.twilio.com/messaging/twiml`，不在本文件范围内）。最简示例：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Hello, world!</Say>
</Response>
```

Twilio 在两个时机会请求 TwiML：
1. **通过 REST API 发起的外呼刚接通时**——Twilio 会获取你在 `Calls.json` 创建请求里给的 `Url`。
2. **有人拨打你名下某个 Twilio 号码的那一刻**——Twilio 会获取该号码配置的"A call comes in"webhook URL（在 Console 里设置，或者通过 IncomingPhoneNumber 资源的 `VoiceUrl` 设置）。

这两种情况下，**你服务器的任务是：接收 Twilio 发来的 HTTP 请求，把 TwiML 作为响应体返回，`Content-Type` 为 `text/xml`（或 `application/xml`）**。然后 Twilio 会按顺序执行里面的动词。

## 处理一通入站来电 —— 你的 webhook 必须返回 TwiML

```python
# Flask 示例
from flask import Response
from twilio.twiml.voice_response import VoiceResponse

@app.route("/voice/answer", methods=["POST"])
def answer_call():
    resp = VoiceResponse()
    resp.say("Thanks for calling. Please hold.")
    return Response(str(resp), mimetype="text/xml")
```

入站 webhook 请求本身是一个 **`POST`，body 是 `application/x-www-form-urlencoded`**（表单参数如 `CallSid`、`From`、`To`、`CallStatus`），不是 JSON——这和 `references/webhooks-and-signatures.md` 里描述的 webhook payload 是同一套约定。所以整个往返是：Twilio → 你的服务器（form-encoded POST）→ 你的服务器 → Twilio（XML/TwiML 响应体）。两段都不是 JSON，这和 REST 的 Calls/Messages API 模式正好相反。

## 关键 TwiML 动词

| 动词 | 用途 | 关键属性 |
|---|---|---|
| `<Say>` | 文字转语音 | `voice`、`language`、`loop` |
| `<Play>` | 播放一段音频文件 URL | `loop` |
| `<Gather>` | 收集 DTMF 按键和/或语音，然后把结果 POST 到 `action` URL | `input`（`dtmf`\|`speech`\|`dtmf speech`，默认 `dtmf`）、`action`（省略时默认是**当前文档自己的 URL**——见下方循环陷阱）、`numDigits`、`timeout`、`speechTimeout` |
| `<Dial>` | 把通话连接到另一个号码/SIP/client/会议 | `action`、`method`、`timeout`、`record`、`answerOnBridge` |
| `<Record>` | 录制来电者的声音 | `action`、`maxLength`、`transcribe` |
| `<Redirect>` | 把通话控制权交给另一个 URL | — |
| `<Hangup>` | 结束通话 | — |
| `<Pause>` | 插入静音 | `length`（秒） |
| `<Enqueue>` / `<Queue>` | 呼叫排队集成（常和 TaskRouter 搭配） | — |

**`<Gather>` 有文档记载的循环陷阱**（来自 `docs.twilio.com/voice/twiml/gather`，抓取于 2026-09-21）：如果省略 `action`，Twilio 会把收集到的输入 POST 回**提供这份 TwiML 文档的那个同一个 URL**——如果这个处理逻辑没有针对 `Digits`/`SpeechResult` 是否存在做分支，来电者可能会卡在反复听到同一段提示的死循环里。永远显式设置一个指向不同处理逻辑的 `action`，或者在服务端根据输入参数是否存在来分支。

**`<Dial>` 有文档记载的行为**：如果给 `<Dial>` 设置了 `action` URL，Twilio 会在被拨打方挂断*之后*请求这个 URL，**原来的通话会在该 `action` 响应返回的任何 TwiML 指令下继续进行**——写在*原*文档里 `</Dial>` 之后的任何动词都不会被执行到。如果省略 `action`，Twilio 就直接落到同一份文档里的下一个动词（如果没有下一个动词就挂断）。

**绝对 URL 与相对 URL**：`<Gather>`、`<Record>`、`<Pay>` 的 `action` URL 通常可以是相对路径——**除非**这通电话是通过 Calls 资源的内联 `Twiml` 参数（而不是 `Url`）发起或更新的，这种情况下这些 `action` URL **必须是绝对路径**。⚠ 文档原文，未实测。

## 用 SDK 生成 TwiML，还是手写 XML

官方 SDK 里都带有 TwiML 构建类（Python/Node 里的 `VoiceResponse`），能生成转义正确的 XML——优先用这些，而不是手动拼接 XML 字符串，尤其是当用户输入的文本要出现在 `<Say>` 里时，避免 XML 注入/格式错误的文档这类问题。

```javascript
const VoiceResponse = require("twilio").twiml.VoiceResponse;
const response = new VoiceResponse();
const gather = response.gather({ input: "dtmf", numDigits: 1, action: "/voice/menu-selected", method: "POST" });
gather.say("Press 1 for sales, 2 for support.");
response.say("We didn't get your input. Goodbye.");
res.type("text/xml").send(response.toString());
```

## 应答机检测（Answering Machine Detection）

在 Calls 创建请求上设置 `MachineDetection=Enable`（或 `DetectMessageEnd`），是让 Twilio 判断接电话的是人还是机器（`human` vs `machine`），结果会体现在状态回调/通话资源的 `AnsweredBy` 字段里。这会给你的 TwiML 开始执行前增加延迟（Twilio 需要几秒钟的音频来做判断），而且**不能**和 `SendDigits` 一起用——OpenAPI 规范明确写了，如果提供了 `SendDigits`，`MachineDetection` 会被忽略。⚠ 文档原文，未实测。

## 常见错误

| 错误码 | 含义 |
|---|---|
| 21201 | No Called number specified |
| 21211 | Invalid 'To' Phone Number（和 SMS 一样——要求 E.164） |
| 13223 | Dial: Invalid phone number format（在 `<Dial>` 动词里） |
| 11200 | HTTP retrieval failure —— Twilio 没能获取到你的 `Url`/TwiML 端点（服务器宕机、TLS 错误、超时、返回了非 2xx/非 XML 的内容） |
| 12300 | Invalid Content-Type —— 你 webhook 的响应没有被识别为 TwiML（比如你返回了 JSON 或 HTML 而不是 XML） |

以上表格是 ⚠ 文档原文，未实测（来自通用错误字典索引，没有真实触发过）。错误 12300 正是本文开头描述的"返回了 JSON 而不是 TwiML"这个坑具体的失败表现——有 key 之后要确认它精确的触发条件（见 `../twilio-workspace/verification-plan.md`）。
