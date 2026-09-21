把这份 skill 装进你的 Agent，让它接 Twilio 短信/语音/OTP 时不再凭其他 REST API 的手感把鉴权写成 Bearer（实际是 Basic Auth），也不会在语音/短信 webhook 里返回 JSON——那本该是 TwiML（XML）。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill twilio --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill twilio --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/twilio/twilio.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态 — 先读这个」「用之前先确认 5 件事」「我要做什么 → 读哪一份」三节；
2. `references/` 下有 6 个 `.md`，其中 `verify-otp.md` 讲的是 Verify 的「启动」和「校验」为什么是两次独立的 API 调用；
3. 在 `SKILL.md` 里能搜到「错误码 20003」字样，是鉴权方式用错（Bearer 而不是 Basic）时会撞上的具体错误码。

## 这份 skill 覆盖什么

Twilio（`twilio.docs`，域名 `api.twilio.com`/`verify.twilio.com`）服务端 REST API 里「发短信、打电话、验证手机号」这条主线：Programmable Messaging（SMS/MMS/WhatsApp）、Programmable Voice（TwiML 拨打与控制通话）、Verify API（OTP/两步验证）、webhook 的 `X-Twilio-Signature` 签名校验；Flex、Segment、SendGrid 邮件、Video、Sync、TaskRouter 等其余 20 多个产品不覆盖。

内容不是文档搬运，重点是两处真实发现的反直觉陷阱：一是**鉴权是 HTTP Basic，不是 Bearer**——Twilio 的每一个端点（Messages、Calls、Verify）都用 `-u user:pass`/`Authorization: Basic base64(...)`，如果这个 session 里刚接完其他用 Bearer 的 REST API，手感很容易带过来，写错会直接得到 401 或错误码 20003；二是 **TwiML（XML）和 REST 响应（JSON）是方向相反、却都叫「Twilio API」的东西**——你主动调用 Twilio（发消息、打电话）拿到的是 JSON，但 Twilio 反过来调用你的服务器（入站短信/来电 webhook）时，你的 HTTP 响应体必须是 TwiML（XML），从这类 webhook 返回 JSON 不会优雅降级，直接就是错的。SKILL.md 还提醒 Verify 的「启动」这一步永远不会把验证码返回给你（必须调用独立的 VerificationCheck 才能核对），以及新账号是 trial 账号，只能给约 5 个已验证号码收发消息，格式完全正确的请求发到未验证号码也会因账号状态失败（错误码 14111），不是格式问题。

## 版本

文档版，抓取于 2026-09-21，未用真实凭证验证。实际调用时报错与 skill 不一致，
**以 API 的真实报错为准**，并去 `docs.twilio.com` 核实最新情况。
