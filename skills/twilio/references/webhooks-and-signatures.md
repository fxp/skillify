# Webhook 与签名校验 — 接收入站短信/来电事件

⚠ 本文件里的每一条陈述都是 `⚠ 文档原文，未实测`（来自 `docs.twilio.com/usage/webhooks/webhooks-security`、`docs.twilio.com/usage/webhooks/messaging-webhooks`、`docs.twilio.com/usage/webhooks/voice-webhooks`，抓取于 2026-09-21），除非另有标注。

## 目录
- 两种"接收 Twilio 事件"
- 签名校验：X-Twilio-Signature
- 你的响应应该长什么样
- 状态回调（出站事件）
- 搭建接收端点

## 两种"接收 Twilio 事件"

本 skill 这部分范围特指入站事件：

1. **入站 SMS/MMS/WhatsApp 消息 webhook**——有人给你的 Twilio 号码发短信时触发。你的响应必须是 TwiML（见下文；注意这里用的是 `<Message>` TwiML，和 `references/voice-calls-and-twiml.md` 里的 Voice TwiML 是不同的东西）。
2. **入站语音来电 webhook**——有人拨打你的 Twilio 号码时触发。你的响应必须是 Voice TwiML——完整动词参考见 `references/voice-calls-and-twiml.md`，本文件只讲这两种 webhook 共用的机制/签名部分。

这两者都和**状态回调**（对你通过 REST API 主动发起的消息/通话的送达/进度通知）是分开的——下面会简单带一下状态回调，因为它们用的是同一套签名机制，但概念上它们是出站事件通知，不是"接收一条消息/一通来电"。

## 签名校验：X-Twilio-Signature

Twilio 发给你应用的每一个 webhook 请求——入站消息、入站来电，或任何状态回调——都带一个 `X-Twilio-Signature` 头。**在信任这个请求真的来自 Twilio 之前，一定要先校验它**；不校验的话，任何知道/猜到你 webhook URL 的人都能 POST 伪造的 `CallSid`/`From`/`Body` 数据。

**签名是怎么算出来的**（了解这个，才知道"用错了 secret"或"URL 不对"具体会破坏什么）：Twilio 用 **你的账号 Auth Token 作为密钥**，对下面这些内容做 HMAC-SHA1 签名：
- 完整的 webhook URL（包含 query string，和配置的一模一样），加上
- 所有 POST body 参数，按字母顺序排序后以 `key+value` 的形式拼接（针对 `application/x-www-form-urlencoded` 请求），**或者**
- 对于 `application/json` 请求体，Twilio 会改成在 URL 上追加一个 `bodySHA256` query 参数（原始 JSON body 的 SHA-256 哈希），然后对这个结果签名。

**关键且容易漏掉的一点：签名校验用的是 Auth Token，不是 API Key secret。** 如果你的应用给*出站* REST 调用用的是 API Key 鉴权（按 `references/auth.md` 的建议），校验*入站* webhook 签名时你依然需要账号的 **Auth Token**——这是单独的一份凭证。这两者不能互相替代；用 API Key Secret 算不出匹配的签名。

**不要自己手写这个逻辑。** Twilio 文档原文写得很明确：*"Twilio recommends using the provided signature validation library from a Twilio SDK. Don't implement your own signature validation."*（Twilio 建议使用 Twilio SDK 自带的签名校验库，不要自己实现签名校验。）每个服务端 SDK 都自带一个校验器：

```python
import os
from twilio.request_validator import RequestValidator

validator = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"])  # Auth Token，不是 API Key secret

# url 必须是 Twilio 实际调用的那个精确 URL，包含 query string
is_valid = validator.validate(
    "https://example.com/voice/answer",
    request.form.to_dict(),          # 所有 POST 表单参数，原样不改
    request.headers.get("X-Twilio-Signature", ""),
)
if not is_valid:
    return "Invalid signature", 403
```

```javascript
const twilio = require("twilio");
const isValid = twilio.validateRequest(
  process.env.TWILIO_AUTH_TOKEN,
  req.headers["x-twilio-signature"],
  "https://example.com/voice/answer",
  req.body // 表单参数，由类似 body-parser 的 urlencoded 中间件解析出来
);
```

对于 JSON body 的 webhook（比较少见；一些较新的事件类型），要用支持 body 的校验方式（Node 里是 `validateRequestWithBody`，Python 里是传原始 body 字符串的 `RequestValidator.validate(url, body_string, signature)`），不要把 JSON 字段当表单参数处理。

### 签名校验特有的坑

- **要用 Twilio 实际调用的那个精确 URL，包括 URL 编码字符和 query string，原样不改。** 在校验前对 URL 做解码或重新编码——哪怕只是把 `%20` 改成一个字面空格——都会导致签名校验失败。如果你在反向代理/负载均衡后面，而代理会重写 scheme/host（内部用 `http`、由 LB 终结 `https` 是很常见的架构），要重建出 Twilio 实际用的*外部*URL，而不是你应用看到的内部 URL。
- **传入收到的每一个参数，不要只传一个硬编码的子集。** Twilio 官方原文警告：*"parameters included in webhook events vary by channel and event type and might change in the future... Twilio occasionally adds parameters without advance notice."*（webhook 事件里包含的参数因渠道和事件类型而异，将来还可能变化……Twilio 有时会不做提前通知就新增参数。）如果你的校验器只接收今天预期的那几个字段，等 Twilio 明天加了个新字段，校验就会开始失败——永远转发完整解析出来的表单 body（或原始 JSON body），不要传一份手工整理过的字典。
- **query 参数也算在签名里。** 如果你的 webhook URL 本身带 query string（比如 `?tenant=acme`），这段字符串也是被签名内容的一部分——要把带 query string 的完整 URL 传给校验器，不要把它拆开、单独传 query 参数。

## 你的响应应该长什么样

具体到入站消息/来电 webhook（不是状态回调——那些不期待响应体），你的 HTTP 响应体必须是 **TwiML**，`Content-Type` 为 `text/xml`（或 `application/xml`）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response></Response>
```

一个空的 `<Response>` 是文档规定的、"收到入站消息/来电但**不**回任何东西"的正确写法（比如你只是想记个日志然后结束）——这不是"没有响应"，而是一份明确的、空但合法的 TwiML 文档。真的什么都不返回，或者返回一个非 TwiML 的响应体，是另一种（出错的）情况——这会产生什么后果见 `references/voice-calls-and-twiml.md` 的错误表（11200/12300）。

要回复一条入站短信，用消息类 TwiML 的 `<Message>` 动词：

```xml
<Response>
  <Message>Thanks for your message! We'll get back to you soon.</Message>
</Response>
```

## 状态回调（出站事件）

对于*你*通过 REST API 发起的通话/消息，你可以额外主动选择在创建请求上设置 `StatusCallback`（加上可选的 `StatusCallbackEvent`、`StatusCallbackMethod`，`Calls.json` 或 `Messages.json`——见 `references/send-sms.md` 和 `references/voice-calls-and-twiml.md`）来接收进度通知。这些 webhook 请求带的也是同样的 `X-Twilio-Signature` 头，校验方式也一样。和入站消息/来电 webhook 不同的是，**状态回调不期待一个 TwiML 响应体**——直接返回 `200 OK` 就行；不管你这里返回什么，通话/消息都会继续（或者其实已经结束了）。

- Voice：默认只通知 `completed` 事件；`initiated`、`ringing`、`answered` 需要通过 `StatusCallbackEvent` 单独开启。
- Messaging：状态变化（`queued → sent → delivered`，或 `failed`/`undelivered`）会实时推送；也可以不用回调，改为轮询 Message 资源的 `status` 字段。
- 录音状态回调是第三种独立的回调类型（`RecordingStatus`：`in-progress`/`completed`/`absent`/`failed`），在 Twilio 完成一段通话录音的转码之后触发——通过 `<Record>` 或 Calls 资源上的 `RecordingStatusCallback` 配置。

## 搭建接收端点

1. 你的 webhook 端点必须能通过 **HTTPS 访问，且证书有效（不能是自签名证书）**——Twilio 不会连接一个自签名 HTTPS 端点。纯 HTTP 可以接受，但不推荐。
2. 在 Console 里针对每个号码配置这个 URL（"A call comes in" / "A message comes in"），或者通过 `IncomingPhoneNumber` REST 资源的 `VoiceUrl` / `SmsUrl` 字段用程序配置。
3. 本地开发时，用 ngrok 这类工具把本地服务器做隧道穿透，然后把 Console 里的 webhook 指向这个隧道的 HTTPS URL——这是 Twilio 自己在 Flask、Express、Django 等各框架专属教程里统一采用的方法。
4. 如果架构上有负载均衡/DMZ 代理，要确保代理把请求原样转发（头、精确的路径+query）到真正执行签名校验的地方。
