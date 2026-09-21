把这份 skill 装进你的 Agent，让它接 Resend 发交易邮件时不再把 Node SDK 和 Python SDK 的错误处理方式搞反，也不会在未验证域名发信失败时把它当成「通用发送失败」盲目重试。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill resend --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill resend --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/resend/resend.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态 —— 先读这个」「用之前先确认 7 件事」「我要做什么 → 读哪一份」三节；
2. `references/` 下有 6 个 `.md`，其中 `batch-sending.md` 讲的是 `POST /emails/batch` 每次最多发 100 封各不相同的邮件；
3. 在 `SKILL.md` 里能搜到「⚠ 文档自相矛盾」字样，附带 OpenAPI 规范和文字文档在批量发送能不能带附件这件事上互相矛盾的具体出处。

## 这份 skill 覆盖什么

Resend（`resend.com/docs`，域名 `api.resend.com`）的交易邮件发送 API：`POST /emails` 单封发送（收件人、HTML/纯文本、附件、抄送密送、定时发送、幂等性）、`POST /emails/batch` 批量发送、域名验证（SPF/DKIM/DMARC）、模板/React Email、webhook 送达退信投诉通知、速率限制与配额；Broadcasts、Contacts/Automations 等营销功能不覆盖。

内容不是文档搬运，重点是两处真实发现的反直觉陷阱：一是 **Node 和 Python 两个官方 SDK 的错误处理方式是相反的**——Node 的 `resend.emails.send()` 对 API 层面的错误永远不会抛异常，会 resolve 成 `{ data, error }` 需要自己检查；Python 的 `resend.Emails.send()` 正好相反，任何 API 失败都会抛出 `ResendError`，成功时直接返回响应对象本身。用 `try/catch` 包 Node 调用等着抓 API 错误会永远进不了 catch 块，检查 Python 返回值里有没有 `error` 键的代码会在第一次真实报错时因为 `AttributeError` 崩溃——这是多语言代码库或把一个 SDK 的模式泛化到另一个 SDK 时最容易引入的 bug。二是**未验证/不匹配的发信域名会直接硬 403，不会静默降级成共享/测试域名**，官方错误码文档记录了确切的响应文案；如果 Agent 把这种情况当成通用发送失败去重试，会永远原样失败下去，正确修复方式是做域名验证而不是加重试逻辑。SKILL.md 还标注了一处 OpenAPI 规范和文字文档的自相矛盾：规范里 `POST /emails/batch` 复用了单封发送的 schema、看起来支持附件，但两处独立的文字文档页面都明确写批量端点不支持附件——已标记为优先验证项，未擅自裁决。

## 版本

文档版，抓取于 2026-09-21，未用真实凭证验证。实际调用时报错与 skill 不一致，
**以 API 的真实报错为准**，并去 `resend.com/docs` 核实最新情况。
