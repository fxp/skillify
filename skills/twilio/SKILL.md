---
name: twilio
description: "接入 Twilio（twilio.com/docs，域名 api.twilio.com / verify.twilio.com）的短信/语音/OTP 验证 API 使用手册——涵盖用 REST API 发送/接收 SMS、MMS、WhatsApp 消息（Programmable Messaging）、用 TwiML 拨打和控制语音通话（Programmable Voice）、用 Verify API 跑手机号验证/OTP/两步验证流程，以及通过 webhook 接收入站短信/来电并用 X-Twilio-Signature 校验请求真实性。当用户提到 Twilio、twilio.com、`twilio` 这个 Python/Node 包、Account SID（`AC…`）、Auth Token、TwiML、Verify API，或者想写代码发短信、打电话、验证手机号、处理入站短信/语音 webhook 时，应主动使用本技能——不要凭记忆或套用其他消息/电话类 API 的习惯去猜鉴权方式（是 HTTP Basic，不是 Bearer）、手机号格式、或 TwiML 响应体的形状，Twilio 在这些地方的约定和别的平台不一样，猜错了往往不会报明显的错，而是静默失败或抛出一个容易误判方向的 401/400。"
---

# Twilio 接入指南 — 面向 AI Agent 的短信、语音与 Verify API

Twilio 是一个云通信平台：发送/接收 SMS、MMS、WhatsApp 消息（Programmable Messaging）、拨打和控制电话（Programmable Voice + TwiML）、跑手机号验证/OTP 流程（Verify）。本 skill 覆盖的是 Agent 构建一个"发短信、打电话、验证用户手机号"的应用所需要的 REST API 面——不包括 Twilio 其余 20 多个产品（Flex、Segment、SendGrid 邮件、Video、Sync、TaskRouter 等），那些不在本 skill 范围内。

## ⚠ 验证状态 — 先读这个

**撰写本 skill 时（2026-09-21）没有可用的真实 Twilio 凭证。`create-doc-skill` 方法论的第 1-2 步（抓取并整理真实文档与 OpenAPI 规范）已完成——第 3 步（真实 API 实测验证）和第 4 步（有/无 skill 对照实验）都被跳过了。**

- 本 skill 里的每一条事实性陈述——字段名、是否必填、错误码、HTTP 状态码、报错原文措辞——除非明确标注，否则在各 reference 文件里都标了 `⚠ 文档原文，未实测`。没有一条是对着真实 API 响应、真实的 400/401、或真实账单确认过的。
- 不要把本 skill 里的任何示例当成"真的跑过 Twilio"的证据，没有跑过。
- `evals/evals.json` 里的场景是基于文档和 OpenAPI 规范推测出的合理陷阱，不是已确认的真实失败模式。
- 一旦拿到真实 Twilio 凭证（Account SID + Auth Token，或一个 API Key），在把本 skill 当成生产决策依据之前，先按 `../twilio-workspace/verification-plan.md` 跑一遍验证，并按 `create-doc-skill/references/verify.md` 的方法把每一个 `⚠` 标记原地替换成验证日期和证据。

## 用之前先确认 5 件事

1. **鉴权是 HTTP Basic，不是 Bearer。** Twilio 的每一个 REST 端点（Messages、Calls、Verify，所有的）都用 `-u user:pass` / `Authorization: Basic base64(user:pass)` 做鉴权，用的是你的 **Account SID + Auth Token**，或者 **API Key SID + API Key Secret**（Twilio 官方建议：应用优先用 API Key，Account SID + Auth Token 只用在文档特别指明的场景）。**这里写 `Authorization: Bearer <token>` 是错的，会得到 401 / 错误码 20003** ——如果你这个 session 里刚接完其他 REST API，默认手感很容易带过来，这是最容易踩的坑。完整细节，包括另一套独立的（默认不在本 skill 范围内的可选）OAuth Bearer 方案：见 `references/auth.md`。
2. **手机号必须是 E.164 格式**（`+14155552671`——`+`、国家码、用户号码本身，不能有空格/连字符/括号），Messages、Calls、Verify 里所有的 `To`/`From` 字段都要遵守。格式不对的号码，文档说会同步报错（Messages/Calls 的 `To` 是 21211，Verify 是 60200），不是被悄悄接受——**这一点没有真实验证过**，见 `references/send-sms.md`。
3. **Verify 是两次独立的 API 调用，不是一次。** `POST .../Verifications`（启动——发验证码）和 `POST .../VerificationCheck`（校验——核对用户输入的验证码）是同一个 Verify **Service** 下的两个不同子资源。不存在一个"验证这个码"就搞定的单一端点，第一步也从来不会把验证码返回给你。完整流程见 `references/verify-otp.md`。
4. **TwiML（XML）和 REST 响应（JSON）是两个方向相反、却都叫"Twilio API"的东西。** 当*你*调用 Twilio（发消息、打电话）时，拿到的是 JSON。当*Twilio*调用*你的服务器*时（入站短信/来电 webhook，或者通话需要下一步指令），**你服务器的 HTTP 响应体必须是 TwiML——XML，不是 JSON。** 从语音/短信 webhook 返回 JSON 不会"优雅降级"，直接就是错的；见 `references/voice-calls-and-twiml.md` 和 `references/webhooks-and-signatures.md`。
5. **计费按每条消息/每分钟算，且随目的地国家和运营商浮动——没有统一单价。** 不要把美国的价格硬编码进成本估算，涉及成本、尤其是可能发往美国以外地区时，用 Pricing API 查一下（`references/pricing-and-errors.md`）。

## 30 秒跑通第一个请求

发一条短信（最便宜、最常见的起点）：

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
message = client.messages.create(to="+14155552671", from_="+14155238886", body="Hello from Twilio")
print(message.sid, message.status)  # status 这里是 "queued"/"accepted"，不是最终送达状态
```

预期返回 HTTP 201，一个 `Message` 资源，`status: "queued"`（或 `"accepted"`），`price: null`（之后才会填充——见 `references/pricing-and-errors.md`）。⚠ 文档原文，未实测——没有对着真实账号跑过。

## 我要做什么 → 读哪一份

| 我想做什么 | 读 | 核心 endpoint |
|---|---|---|
| 鉴权请求；决定用 Account SID+Token 还是 API Key | `references/auth.md` | （全部——Basic Auth 通用） |
| 通过 REST API 发送/接收 SMS、MMS 或 WhatsApp 消息 | `references/send-sms.md` | `POST/GET /2010-04-01/Accounts/{Sid}/Messages.json` |
| 跑手机号验证 / OTP / 两步验证（发验证码、查验证码） | `references/verify-otp.md` | `POST /v2/Services`、`POST /v2/Services/{Sid}/Verifications`、`POST /v2/Services/{Sid}/VerificationCheck` |
| 发起一通外呼，或写 TwiML 控制正在进行的通话 | `references/voice-calls-and-twiml.md` | `POST /2010-04-01/Accounts/{Sid}/Calls.json`，`<Say>`/`<Dial>`/`<Gather>`/`<Record>` 等 TwiML 动词 |
| 接收入站短信/来电 webhook，并验证它确实来自 Twilio | `references/webhooks-and-signatures.md` | `X-Twilio-Signature` 头校验；TwiML 响应体要求 |
| 查真实的分国家定价；了解错误响应的形状和常见错误码 | `references/pricing-and-errors.md` | `GET /v1/Messaging/Countries/{IsoCountry}`、`GET /v1/Voice/Countries/{IsoCountry}`（`pricing.twilio.com`） |

**本 skill 不覆盖**（按任务范围明确排除——需要的话直接查 `docs.twilio.com`）：Flex、Segment、SendGrid 邮件、Video、Sync、TaskRouter、Conversations、Proxy、Elastic SIP Trunking 配置、Lookup、Trust Hub / A2P 10DLC 合规注册，以及客户端 JS/iOS/Android Voice SDK（浏览器/移动端拨打——本 skill 只覆盖服务端 REST API 和 TwiML）。

## 跨领域的通用规则（写代码前必读）

1. **全线 Basic Auth，两种可能的凭证对。** 不要假设"这个 API 用的是上一个 API 那套鉴权方式"。Account SID+Token 和 API Key 怎么选、各自哪些场景不能用（比如 Standard API key 不能调 `/Accounts` 或 `/Keys`），见 `references/auth.md`。
2. **每一个 REST 创建/更新请求的 body 都是 `application/x-www-form-urlencoded`，不是 JSON**，Messages、Calls、Verify（`2010-04-01` 和 `v2` 两个命名空间都一样）——尽管响应是 JSON。如果是手写请求而不是走 SDK，这里搞错了会拿到一个含糊的 400，而不是一个"content type 错了"这种直白的报错。
3. **凡是涉及手机号的字段都要求 E.164**——Messages 的 `To`/`From`、Calls 的 `To`/`From`、Verify 的 `To`。各处校验方式不完全一样（Messages/Calls：文档说是同步拒绝；Verify：也是文档说的同步拒绝，但错误码不同，是 60200）——具体看各自的 reference 文件，不要假设"SMS 这样能行，Verify 也一定行"而不去核实。
4. **TwiML 不是 JSON，而且它的流向和本 skill 里其他所有 Twilio 交互是反的。** REST 调用：你 → Twilio，进去是 JSON，出来也是 JSON。Webhook/通话控制：Twilio → 你（form-encoded POST），你 → Twilio（TwiML/XML 响应）。写代码前先搞清楚当前这段代码是在哪个方向上，再决定响应格式。
5. **Verify 的"启动"这一步永远不会把验证码返回给你。** 如果你的设计是让客户端拿 `POST .../Verifications` 返回的东西去和用户输入做比对，那是设计上的 bug，不是缺了什么功能——验证码只会通过你选的渠道（短信/电话等）送到用户手上，只有 `POST .../VerificationCheck` 才能告诉你用户提交的码对不对。
6. **入站 webhook 一定要校验 `X-Twilio-Signature`，用 Auth Token（不是 API Key secret），而且要用 Twilio 实际调用的那个精确 URL**（包含 query string，原样不改）。用 SDK 自带的校验器——不要自己手写 HMAC。见 `references/webhooks-and-signatures.md`。
7. **不存在统一单价。** SMS 是分段数 × 按国家/运营商定价的单段价格；语音是按分钟 × 按目的地定价。用美国价格去估算任意目的地的成本会算错，而且经常错得很离谱。见 `references/pricing-and-errors.md`。
8. **新账号是 trial 账号**，在升级（绑定支付方式）之前，只能给约 5 个"已验证"号码、且只能在注册国家范围内收发短信/打电话——一个格式完全正确的请求，如果发往一个未验证/境外的号码，在 trial 账号上会因为账号状态原因失败（错误码 14111），不是因为格式问题。排查前先确认是不是 trial 账号，再去查 E.164 格式对不对。
9. **官方服务端 SDK**：Python `pip install twilio`（`from twilio.rest import Client`），Node `npm install twilio`（`const twilio = require("twilio")`）；此外还有官方的 C#、Java、PHP、Ruby、Go 库（`docs.twilio.com/libraries`）。SDK 会帮你搞定 Basic Auth 头的拼装、TwiML XML 的生成/转义、以及 webhook 签名校验——优先用 SDK 而不是手搓 HTTP + XML 字符串拼接，尤其是 TwiML（有 XML 注入风险）和签名校验（Twilio 明确说了不要自己手写）。

## 目录结构

```
twilio/
├── SKILL.md                          # 本文件——路由 + 跨领域通用规则
├── references/
│   ├── auth.md                       # Basic Auth、Account SID+Token 与 API Key 怎么选、OAuth apps
│   ├── send-sms.md                   # Messages 资源：收发 SMS/MMS/WhatsApp、E.164、错误码
│   ├── verify-otp.md                 # Verify：Service → Verification（启动）→ VerificationCheck
│   ├── voice-calls-and-twiml.md      # Calls 资源（外呼）+ TwiML 动词（通话中控制）
│   ├── webhooks-and-signatures.md    # X-Twilio-Signature 校验、入站短信/来电 webhook
│   └── pricing-and-errors.md         # Pricing API、通用错误信封、错误码区间
└── evals/
    └── evals.json                    # 有/无 skill 对照实验场景（还没跑——见 twilio-workspace/）
```

内容整理自 `docs.twilio.com`（用每个页面的 `.md` 后缀导出 Markdown）以及 `github.com/twilio/twilio-oai` 上的官方 OpenAPI 规范（`twilio_api_v2010.json`、`twilio_verify_v2.json`、`twilio_iam_v1.json`），抓取于 2026-09-21。**真实 API 调用结果永远优先于本文写的任何内容**——本 skill 尚未对着真实账号跑过（见上方的验证状态说明）。
