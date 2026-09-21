# 手机号验证 / 两步验证 — Verify API（两步调用，不是一次）

⚠ 本文件里的每一条陈述都是 `⚠ 文档原文，未实测`（来自 `docs.twilio.com/verify/api`、`docs.twilio.com/verify/api/rate-limits-and-timeouts`、`docs.twilio.com/verify/api/error-codes`，以及 `twilio_verify_v2` OpenAPI 规范，抓取于 2026-09-21），除非另有标注。

## 目录
- 这个坑：是两次独立的 API 调用，不是一次
- 第 0 步：创建一个 Verify Service（只需一次，不是每次验证都建）
- 第 1 步：启动一次验证
- 第 2 步：核对验证码
- Base URL 与鉴权
- 验证码有效期、速率限制与渠道
- 常见错误

## 这个坑：是两次独立的 API 调用，不是一次

Twilio Verify **不是**"一次调用发个码"这种模式。它是一个有状态的两步流程，针对一个 Verify **Service** 下的两个不同子资源：

1. **`POST .../Verifications`**——"启动一次验证"：告诉 Twilio 生成一个验证码，并通过短信/电话/WhatsApp/邮件等渠道发出去。响应是 `status: "pending"`，**不会返回验证码本身**（这很合理——验证码已经发到用户手机上了）。
2. **`POST .../VerificationCheck`**——"核对一次验证"：你的应用收集用户输入的验证码，提交到这里让 Twilio 校验。响应是 `status: "approved"`（正确）或 `"pending"`/其他值（还不对/还没输入）。

一个曾经见过"验证手机号"类 API 是单一 `POST /verify {phone, code}` 调用的 Agent，很自然会想把这两步合并成一次请求，或者试图在客户端拿第一步返回的东西去比对——**这两种做法都行不通**：第一步永远不会返回验证码（除非你主动开启 `CustomCode` 这个高级功能），也不存在一个"发码+核对"一步到位的端点。

```
Service（创建一次）
  └─ Verification        （启动——用户请求验证码时调用）
  └─ VerificationCheck   （核对——用户提交验证码时调用）
```

## 第 0 步：创建一个 Verify Service（只需一次，不是每次验证都建）

一个 Verify **Service** 是一个可复用的配置容器（品牌、验证码长度、渠道、速率限制）——每个应用/场景创建一次即可，不是每个用户或每次 OTP 尝试都建一个。它的 SID（`VAxxxxxxxx…`）是每次 Verification/Check 调用都需要的路径参数。

**Endpoint**：`POST https://verify.twilio.com/v2/Services`

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `FriendlyName` | string | **是** | 最多 32 字符；会出现在验证消息正文里；不能含 PII，总共不超过 4 位数字。 |
| `CodeLength` | integer | 否 | 4–10，默认值因渠道而异（SMS 常见是 4 或 6 位，取决于 Console 默认配置）。 |
| `DoNotShareWarningEnabled` | boolean | 否 | 在短信正文里附加一句防钓鱼提示。 |
| `CustomCodeEnabled` | boolean | 否 | 允许*你的*应用自己提供验证码，而不是由 Twilio 生成（启动时对应 `CustomCode` 参数）——高级功能/涉及反欺诈，默认关闭。 |

```bash
curl -X POST "https://verify.twilio.com/v2/Services" \
  -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
  --data-urlencode "FriendlyName=My App"
```

```python
service = client.verify.v2.services.create(friendly_name="My App")
service_sid = service.sid  # 保存下来——这是个配置，要复用
```

## 第 1 步：启动一次验证

**Endpoint**：`POST https://verify.twilio.com/v2/Services/{ServiceSid}/Verifications`

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `To` | string | **是** | **E.164 格式**的手机号（如果配置了 `email` 渠道，也可以是邮箱）。E.164 规则和 SMS 一样——见 `references/send-sms.md`。 |
| `Channel` | string | **是** | `sms`、`call`、`whatsapp`、`email`、`sna`、`auto` 之一。 |
| `Locale` | string | 否 | 覆盖自动检测出的消息语言。 |
| `CustomCode` | string | 否 | 4–10 个字符；只有 Service 开启了 `CustomCodeEnabled` 才生效。 |

```bash
curl -X POST "https://verify.twilio.com/v2/Services/$VERIFY_SERVICE_SID/Verifications" \
  -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
  --data-urlencode "To=+14155552671" \
  --data-urlencode "Channel=sms"
```

```python
verification = client.verify.v2.services(service_sid).verifications.create(
    to="+14155552671", channel="sms"
)
print(verification.status)  # "pending" —— 验证码刚发出去，这里不会返回验证码
```

响应（创建成功，`201`）：

```json
{
  "sid": "VExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "service_sid": "VAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "to": "+14155552671",
  "channel": "sms",
  "status": "pending",
  "valid": false,
  "date_created": "Mon, 21 Sep 2026 12:00:00 +0000"
}
```

**注意**：`valid` 是一个遗留的布尔字段，文档明确说不要再用它，改用 `status`——新代码里不要根据 `valid` 做分支判断。

## 第 2 步：核对验证码

**Endpoint**：`POST https://verify.twilio.com/v2/Services/{ServiceSid}/VerificationCheck`

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `Code` | string | 条件必填 | 用户输入的 4–10 位验证码。 |
| `To` | string | 条件必填 | `To` 和 `VerificationSid` 必须给一个（规范没有把任何一个单独标记为硬性必填，但至少要给一个才能确定要核对哪一次验证）。 |
| `VerificationSid` | string | 条件必填 | 第 1 步返回的 `sid`——作为重新传 `To` 的替代方案。 |

```bash
curl -X POST "https://verify.twilio.com/v2/Services/$VERIFY_SERVICE_SID/VerificationCheck" \
  -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
  --data-urlencode "To=+14155552671" \
  --data-urlencode "Code=123456"
```

```python
check = client.verify.v2.services(service_sid).verification_checks.create(
    to="+14155552671", code=user_supplied_code
)
if check.status == "approved":
    ...  # 手机号确认通过
```

响应：

```json
{
  "sid": "VExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "status": "approved",
  "valid": true
}
```

两个资源共用的 `status` 取值：`pending`、`approved`、`canceled`、`max_attempts_reached`、`deleted`、`failed`、`expired`。**要检查 `status == "approved"`，不要检查 `valid == true`**（遗留字段），也不要只看"HTTP 200"（提交了错误的验证码，响应依然是 `200`/`201`，`status` 字段反映的是验证码不匹配，不是一个 4xx——这正是一个假设"REST 惯例里错误就该是错误状态码"的 Agent 容易踩的坑，会把一次失败的核对误判为成功）。

⚠ 未直接确认：提交了错误验证码的 VerificationCheck 响应，字面上是不是依然显示 `status: "pending"`（表示还可以重试），还是在第一次输错时就变成一个独立的失败值，这一点没有测试过。在做只根据 HTTP 状态码分支的"验证码错误"提示上线之前，先确认这一点。

## Base URL 与鉴权

Base URL：`https://verify.twilio.com/v2/`。鉴权：HTTP Basic——Account SID + Auth Token，或者 API Key SID + Secret（见 `references/auth.md`）。Verify 的 OpenAPI 规范里，除了 Basic，还列了一个 OAuth Bearer scheme（`access_token_bearer`）——这是 `references/auth.md` 里提到的同一个组织级 OAuth 功能，不是默认路径；除非你专门要接入 Twilio OAuth apps，否则忽略它。

## 验证码有效期、速率限制与渠道

- **默认验证码有效期：从生成起 10 分钟**。可配置范围 2 分钟–24 小时，但截至本次抓取，只能联系 Twilio 支持来改，不是一个自助的 API 参数。
- 在有效期窗口内重复请求，验证码保持不变——在第一个码过期前重新请求 `sms` 渠道，**不一定**会生成一个新码，可能只是把同一个码再发一遍。⚠ 文档原文，未实测。
- **状态查询的速率限制**（查验证状态，不是核对验证码这个动作本身）：按文档是 60/分钟、180/小时、250/天。这和 Service 级别可配置的 Programmable Rate Limits 是两回事（`references/pricing-and-errors.md` 里有这些错误码的链接）。
- 渠道：`sms`、`call`（语音 OTP——用 TTS 朗读验证码）、`whatsapp`、`email`（需要接入 SendGrid）、`sna`（Silent Network Auth——运营商级验证，用户不用输入验证码）、`auto`（由 Twilio 挑选最佳渠道）。

## 常见错误

| 错误码 | 含义 | 触发场景 |
|---|---|---|
| 60200 | Invalid parameter | `To` 格式不对/缺 `+`，`Channel` 不是有效选项或该 Service 未启用此渠道，核对时 `Code` 不是 4–10 位数字 |
| 60202 | Max check attempts reached | 针对同一个 Verification 提交了太多次错误验证码 |
| 60203 | Max send attempts reached | 同一个窗口内针对同一个 `To` 调用了太多次 `Verifications`（启动） |
| 60212 | Too many concurrent requests for phone number | 针对同一个号码并发发起了多个启动请求 |
| 20404（通用 REST） | Not found | `ServiceSid` 错误/已删除，或核对的这次 Verification 已过期并被清除 |

以上表格是 ⚠ 文档原文，未实测。错误信封的形状和 Twilio 通用格式一致（`code`/`message`/`more_info`/`status`），60200 的官方示例已确认这一形状：

```json
{"code": 60200, "message": "Invalid parameter: To", "more_info": "https://www.twilio.com/docs/errors/60200", "status": 400}
```
