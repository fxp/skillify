# 定价与错误码 — 按条/按分钟计费，且因国家不同差异巨大

⚠ 本文件里的每一条陈述都是 `⚠ 文档原文，未实测`（来自 `docs.twilio.com/messaging/api/pricing`、`docs.twilio.com/voice/pricing`、`docs.twilio.com/api/errors`、`docs.twilio.com/usage/trials`，抓取于 2026-09-21），除非另有标注。

## 目录
- 这个坑：不存在统一单价
- 用程序查真实价格：Pricing API
- 到底是什么在决定价格
- Trial 账号的限制（也和成本估算有关）
- 通用错误响应形状
- 实际会遇到的错误码区间

## 这个坑：不存在统一单价

不存在一个全平台通用的"每条短信 $X"或"每分钟 $Y"这种数字。Twilio 是**按消息段/按分钟、按目的地国家、往往还要再细分到具体运营商**来定价的——一条美国到美国的短信、一条美国到印度的短信、一条美国到英国的短信，每段的单价可能差得很明显，语音每分钟的费率也一样因目的地不同而不同（有时还看落地的是手机号还是固话）。**一个把美国的统一单价（比如"$0.0079/条"）硬编码进成本估算、预算检查或限流计算的 Agent，一旦消息或通话涉及非美国目的地，估算会严重偏低**——国际费率可能是美国费率的好几倍，有些目的地国家还有额外的监管附加费，这些都不会体现在一个简单的按条估算里。

另外：**Message 或 Call 资源上的 `price` 在发送/通话真正完成之前都是 `null`**——你没法从创建响应里读出费用；它是异步填充的（见 `references/send-sms.md` 和 `references/voice-calls-and-twiml.md`）。不要设计一套"响应里告诉了我费用"的成本追踪流程——费用要么提前查（Pricing API），要么事后轮询/等待资源更新。

## 用程序查真实价格：Pricing API

**Messaging**：`GET https://pricing.twilio.com/v1/Messaging/Countries/{IsoCountry}`——返回 `outbound_sms_prices`（一个按运营商分组的数组，每条是 `{carrier, mcc, mnc, prices: [{base_price, current_price, number_type}]}`——注意**一个国家对应多个价格**，按运营商和号码类型分别列出，不是一个数字）以及类似结构的 `inbound_sms_prices`。

**Voice**：`GET https://pricing.twilio.com/v1/Voice/Countries/{IsoCountry}`（结构和 messaging 类似：`outbound_prefix_prices` 按号段前缀/运营商列出，`inbound_call_price`）。

```python
country = client.pricing.v1.messaging.countries("IN").fetch()  # 印度举例——用之前先查，不要默认用美国费率
for p in country.outbound_sms_prices:
    print(p)  # 按运营商分别定价，不是一个统一数字
```

两者的鉴权方式都和其他 Twilio API 一样，是 Basic Auth（见 `references/auth.md`）。也有查全部国家的变体（`GET .../Countries`，不带具体的 ISO 国家码），如果需要建一整张定价表而不是一次查一个目的地，可以用这个。

如果只是要给人看的定价摘要（不能用于程序化计算成本，因为它不反映账号级的议价费率或促销价），Twilio 也公开了 `twilio.com/en-us/pricing` 这个页面。

## 到底是什么在决定价格

- **目的地国家**（永远是决定因素）。
- **该国家内的运营商 / MCC-MNC**——同一个国家里不同移动运营商的费率可能不一样。
- **号码类型**——比如免费号码或短码作为发送方，和普通长号码相比，无论发送还是接收，定价都可能不同。
- **消息分段**——超过 160 个 GSM-7 字符（或 70 个 UCS-2 字符，即非拉丁文字/大量 emoji）的 `Body` 会被拆成多段，按段计费，不是按消息计费——见 `references/send-sms.md`。这会和按国家定价叠加：一条发往高价目的地的长消息，费用是"段数 × 每段单价"，不是一个固定的整条消息费。
- **方向**——入站和出站有各自独立的价格记录；入站短信/来电不是免费的，即使不是你的应用发起的。

## Trial 账号的限制（也和成本估算有关）

一个全新的 Twilio 账号是**trial 账号**，按产品给了免费额度（不是一笔美元余额）——按 trial 文档说是 100 条短信、75 分钟语音——而且关键是：

- **trial 状态下只能给"已验证（Verified）"号码发消息/打电话**——最多 5 个接收号码，每个都要通过 Twilio 发给它的验证码来验证。在 trial 账号上给一个未验证的号码发消息/打电话，失败的方式和普通送达失败不一样（比如错误码 14111 "Invalid To phone number for Trial mode"——见下文）——这是账号状态层面的限制，不是单次请求的格式问题，排查"这个格式完全正确的 E.164 号码为什么失败"时，应该先查是不是 trial 状态，而不是先重新检查格式。
- trial 状态下，SMS/语音还被限制在你注册时所在的国家。
- 升级账号（绑定支付方式）之后，这些限制会完全解除——这是一个值得提前告知负责搭建账号的人的成本/行为差异，"我拿自己已验证的号码在 trial 里测试通过了"并不代表升级之前它对任意目的地都能用。

## 通用错误响应形状

Twilio 各个产品的 REST API 都用同一个 JSON 信封返回错误：

```json
{
  "code": 21211,
  "message": "human-readable description, sometimes includes the offending value",
  "more_info": "https://www.twilio.com/docs/errors/21211",
  "status": 400
}
```

`code` 是 Twilio 自己的数字错误码（可以在 `www.twilio.com/docs/api/errors/{code}` 查——这也是 `more_info` 链接指向的地方）；`status` 是 HTTP 状态码。**异步资源（一个后来失败的 `Message` 或 `Call`）上的 `error_code`/`error_message`，和上面这个同步的请求拒绝信封用的是同一套数字编码空间，但它们是不同的字段**——一条消息可能已经被接受了（HTTP 201，响应体里没有 error），但*之后* Twilio/运营商处理完之后依然变成 `status: "failed"`，并带上一个填充了的 `error_code`。不要把"创建调用返回了 201"当作最终成功的证据。

## 实际会遇到的错误码区间

| 区间 | 领域 | 说明 |
|---|---|---|
| 11xxx–13xxx | 语音/TwiML 获取与执行 | 例如 11200 HTTP retrieval failure、12300 invalid Content-Type、13223 Dial: invalid phone number format |
| 14xxx | Trial 模式专属 | 例如 14111 Invalid To phone number for Trial mode |
| 20xxx | 账号/鉴权/通用 REST | 例如 20003 Permission Denied（鉴权方式错了——见 `references/auth.md`）、20404 not found |
| 21xxx | 消息（`2010-04-01` Messages 资源） | E.164/发送方校验——见 `references/send-sms.md` |
| 30xxx | 消息送达（运营商侧，异步） | 出现在运营商处理完之后 Message 资源的 `error_code` 里，不是创建时 |
| 60xxx | Verify | Service/Verification/Check 校验——见 `references/verify-otp.md` |

以上全部是 ⚠ 文档原文，未实测——本 skill 没有对着真实账号触发过这些错误码。见 `../twilio-workspace/verification-plan.md`。
