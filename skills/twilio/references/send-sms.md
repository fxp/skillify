# 发送 SMS / MMS — Messages 资源

⚠ 本文件里的每一条陈述都是 `⚠ 文档原文，未实测`（来自 `docs.twilio.com/messaging/api/message-resource`、`docs.twilio.com/api/errors/*`，以及 `twilio_api_v2010` OpenAPI 规范里的 `Api20100401Message` 定义，抓取于 2026-09-21），除非另有标注。

## 目录
- Endpoint
- E.164 是必须的，不是可选的
- 必填字段与 From / MessagingServiceSid 的坑
- 关键请求参数
- 示例请求
- 示例响应
- 消息状态生命周期
- 读取/列出消息
- 常见发送时错误

## Endpoint

**发送**：`POST https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Messages.json`
**读取单条/列表**：`GET https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Messages.json`

鉴权：HTTP Basic（见 `references/auth.md`）。请求 body 的 content type 是 **`application/x-www-form-urlencoded`，不是 JSON**——这是整个 `2010-04-01` Accounts 命名空间下的 REST API 约定（Messages、Calls 及大多数其他核心资源都一样）；如果是手写请求而不是走 SDK，不要发 `Content-Type: application/json` 配 JSON body。

## E.164 是必须的，不是可选的

`To` 和 `From`（或者通过 `MessagingServiceSid` 解析出的发送方）都必须是 **E.164 格式**：一个 `+`、国家码、然后是用户号码本身，不能有空格/连字符/括号——例如 `+14155552671`。这一点在 OpenAPI 规范里 `To` 字段的描述中直接写明（"The recipient's phone number in E.164 format... for SMS/MMS"），错误码 21211 的说明也印证了这点。

**违反这条规则实际会发生什么**（来自官方错误字典 `docs.twilio.com/api/errors/21211`、`21401`，抓取于 2026-09-21——这是文档记载的、结构化的错误响应，不是瞎猜，但本 skill 没有对着真实账号触发过）：

- **`To` 格式不对** → API 调用**同步失败，HTTP 400**，Twilio 错误码 **21211 "Invalid 'To' Phone Number"**。不会先排进队列再之后失败。文档记载的成因包括：缺 `+`、缺国家码、里面夹了空格/标点、没带国家码的本地格式号码、位数错误/多余/缺失，以及 `To` 和 `From` 用了同一个号码。

  | 输入（错误） | 问题 | 修正后（E.164） |
  |---|---|---|
  | `(555) 123-4567` | 缺 `+`/国家码，还带标点 | `+15551234567` |
  | `555-123-4567` | 缺 `+`/国家码 | `+15551234567` |
  | `+1 555 123 4567` | 带空格 | `+15551234567` |
  | `07911 123456` | 英国本地格式 | `+447911123456` |
  | `15551234567` | 缺 `+` 前缀 | `+15551234567` |

- **`From` 不是你名下有效的 Twilio 发送方** → HTTP 400，错误码 **21401 "Invalid Phone Number"**。这个错误不只在号码本身格式错误时触发，一个语法上合法的 E.164 号码，只要 Twilio 认不出它属于你的账号（一个你没购买/没转入的号码，或者一个在目的地国家不被允许使用的字母数字发送方 ID，比如 US/Canada），同样会触发。

错误响应的形状（Twilio 通用的 REST 错误信封）：

```json
{
  "code": 21211,
  "message": "The 'To' number +155512345 is not a valid phone number.",
  "more_info": "https://www.twilio.com/docs/errors/21211",
  "status": 400
}
```

**⚠ 未直接确认（重要）**：`create-doc-skill` 的任务简报特别问了非 E.164 号码会发生什么——"报错还是静默失败"。根据上面记载的错误码，平台文档描述的行为是**同步的、带具体错误码的 400**，不是静默接受/静默失败。**这一点没有对着真实 API 调用验证过**（没有可用的 key）。不要把这当成已确认的结论，有 key 之后要优先验证（见 `../twilio-workspace/verification-plan.md` 第 1 项）——Twilio 有些其他校验是已知的"静默失败"而不是"创建时就拒绝"（比如某些资源上不支持的参数），所以不要从这一个有文档记载的案例，就推广出"Twilio 一律同步拒绝"这个结论，务必自己验证。

## 必填字段与 From / MessagingServiceSid 的坑

- `To` 永远必填。
- 恰好需要一个发送方身份：**`From` 或 `MessagingServiceSid` 二选一**——不是两个都必填，也不是两个都可以不填。OpenAPI 规范的 `conditionalParameterMap` 明确把 `From` ↔ `MessagingServiceSid` 声明为互相关联的替代关系。如果只给了 `MessagingServiceSid`，Twilio 会从这个 Messaging Service 的号码池里自动选一个发送方；你也可以两个都给（从该池子里指定一个具体的 `From`）。
- ⚠ 文档自相矛盾 / 规范本身的局限：创建 Message 请求体的 OpenAPI 规范里，顶层 `required` 数组只列了 `To`——它**没有**把"From 或 MessagingServiceSid 必须给一个"编码成正式的 JSON Schema 约束（这条逻辑只存在于 `conditionalParameterMap` 和文字说明里）。如果你只根据 JSON Schema 的 `required` 数组去生成客户端代码，同时漏掉 `From` 和 `MessagingServiceSid` 是不会在客户端报错的——这个校验只在服务端生效。

## 关键请求参数

| 参数 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `To` | string（E.164） | 是 | 接收方。SMS/MMS：E.164 格式手机号。WhatsApp：`whatsapp:+15552229999` 这种带渠道前缀的形式。 |
| `From` | string（E.164） | 条件必填 | 必须是你账号名下的 Twilio 托管发送方（已购买/已转入的号码、字母数字发送方 ID、短码）。除非给了 `MessagingServiceSid`，否则必填。 |
| `MessagingServiceSid` | string（`MG…`） | 条件必填 | 用来代替/配合 `From`，让 Twilio 从一个号码池里自动选发送方。 |
| `Body` | string | 否 * | 最多 1600 字符。超过 160 个 GSM-7 字符（或 70 个 UCS-2 字符）的 SMS 会被分段，按段计费。*除非走 `ContentSid` 模板或纯 `MediaUrl` 的 MMS，否则必填。 |
| `MediaUrl` | array\<string(uri)\> | 否 | MMS 附件；每条消息最多 10 个 URL，jpeg/jpg/png/gif 最大 5MB，其他支持的类型最大 500KB。 |
| `StatusCallback` | string（uri） | 否 | 送达状态更新的 webhook URL——见 `references/webhooks-and-signatures.md`。 |
| `ValidityPeriod` | integer（秒） | 否 | 一条排队中的消息在 Twilio 放弃发送前最多等待的时间。默认 `36000`（10 小时）；可接受范围 1–36000。不建议把 `validity_period` 设成 ≤ 5。 |
| `ShortenUrls` | boolean | 否 | 仅 Messaging Service 场景可用，需要配置了 Link Shortening；同时必须给 `messaging_service_sid`。 |
| `ContentSid` | string（`HX…`） | 否 | 用一个预先审批过的 Content Template（很多 WhatsApp / 受监管渠道的发送都要求这个）来代替自由格式的 `Body`。 |
| `SendAt` + `ScheduleType=fixed` | — | 否 | 预约未来发送；仅 Messaging Service 场景可用。 |
| `MaxPrice` | number | — | **自 2024-06-03 起已废弃**——这个字段还存在于 API 里，但已经不起作用了。不要靠它来做成本上限控制。 |

## 示例请求

```bash
curl -X POST "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/Messages.json" \
  -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
  --data-urlencode "To=+14155552671" \
  --data-urlencode "From=+14155238886" \
  --data-urlencode "Body=Hello from Twilio"
```

```python
import os
from twilio.rest import Client

client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])

message = client.messages.create(
    to="+14155552671",       # E.164 —— 必填
    from_="+14155238886",    # 你的 Twilio 号码，E.164 格式；注意结尾的下划线（因为 from 是 Python 关键字）
    body="Hello from Twilio",
)
print(message.sid, message.status)
```

```javascript
const twilio = require("twilio");
const client = twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN);

const message = await client.messages.create({
  to: "+14155552671",
  from: "+14155238886",
  body: "Hello from Twilio",
});
console.log(message.sid, message.status);
```

## 示例响应

```json
{
  "sid": "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "status": "queued",
  "to": "+14155552671",
  "from": "+14155238886",
  "body": "Hello from Twilio",
  "num_segments": "1",
  "direction": "outbound-api",
  "price": null,
  "price_unit": "USD",
  "error_code": null,
  "error_message": null,
  "date_created": "Mon, 21 Sep 2026 12:00:00 +0000"
}
```

`price` / `price_unit` 和最终的 `status` 是在消息**真正发出之后**才会被填充，不是在创建时的立即响应里——创建响应反映的是这条消息被接受进了 Twilio 的发送管道（`status: "queued"` 或 `"accepted"`），不代表已送达。要知道最终结果，得轮询这个资源，或者用 `StatusCallback`。

## 消息状态生命周期

`accepted → scheduled → queued → sending → sent → delivered`（正常路径），`failed` / `undelivered` / `canceled` 是终态的失败状态，入站消息是 `receiving → received`。`read` 只用于 WhatsApp。当 `status` 是 `failed` 或 `undelivered` 时，`error_code` / `error_message` 会被填充——见下方错误表。

## 读取/列出消息

`GET .../Messages.json` 支持按 `To`、`From`、`DateSent` 过滤（`DateSent<` / `DateSent>` 区间变体也支持），加上标准的 `PageSize`/`Page`/`PageToken` 分页（默认分页大小 50，最大 1000）。

## 常见发送时错误

| 错误码 | 含义 | 典型触发场景 |
|---|---|---|
| 21211 | Invalid 'To' Phone Number | `To` 不是 E.164 格式，或者 `To` 和 `From` 相同 |
| 21401 | Invalid Phone Number（发送方） | `From` 不属于你的账号、不是 E.164 格式，或者是目的地国家不支持的字母数字 ID |
| 21606 | 'From' number is not a valid message-capable Twilio number for this account | 用了一个只支持语音的号码，或者一个没开通 SMS 能力的号码 |
| 21614 | 'To' number is not a valid mobile number | 发 SMS/MMS 到一个不允许接收短信的固话号码 |
| 30003–30008（区间） | 各种运营商侧的未送达原因（用户手机关机/不可达、被拦截、未知错误） | 出现在异步 `status` 更新里的 `error_code`，不是在创建响应里 |

以上所有行都是 ⚠ 文档原文，未实测——来自 `docs.twilio.com/api/errors` 索引和各错误码页面，没有真实触发过。验证的优先顺序见 `../twilio-workspace/verification-plan.md`。
