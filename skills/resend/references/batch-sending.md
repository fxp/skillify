# 批量发送

> ⚠ 本文件的全部内容都是 `⚠ 文档原文，未实测`——整理自 `resend.com/docs` 和 `resend.com/openapi.json`（抓取于 2026-09-21），未经真实 API 调用确认。见 SKILL.md 里的验证状态说明。

## 批量发送邮件 — `POST /emails/batch`

**Endpoint**：`POST https://api.resend.com/emails/batch`
**用途**：一次 API 调用发送多达 **100 封结构上互相独立的邮件**——每一项可以有完全不同的 `to`、`subject`、`html` 等。这是用来低成本触发大量*各不相同*的交易邮件的（比如一次请求给 80 个不同客户发订单确认），**不是**用来给一个大列表发共享内容的营销/批量活动（那种场景用 Broadcasts——本 skill 不覆盖）。

**Auth**：和 `POST /emails` 一样的 Bearer token。

**请求体**：一个 **JSON 数组**（不是对象），最多 100 项，每一项的结构和单封 `POST /emails` 的请求体*完全一样*（`from`、`to`、`subject`、`html`/`text`、`cc`、`bcc`、`reply_to`、`headers`、`scheduled_at`、`tags`、`template`、`topic_id`——每项都支持）。每一项的 `from`/`to`/`subject` 都是必填。

**请求头**：`Idempotency-Key`（可选，和单封发送一样的 24 小时/256 字符规则——见 `sending-emails.md`）。对批量请求来说，key 应该代表*整个批次*（比如 `team-quota/123456789`），而不是某一个收件人。

**响应 200**

```json
{
  "data": [
    { "id": "ae2014de-c168-4c61-8267-70d2662a1ce1" },
    { "id": "faccb7a5-8a28-4e9a-ac64-8da1cc3bc1cb" }
  ]
}
```

`data[i]` 对应请求数组里的第 `i` 项（从 0 开始，顺序和提交时一致）——这是把返回的 id 对应回具体收件人的唯一方式，因为响应里不会回显原始的 `to`/subject。

**示例 — curl**

```bash
curl -X POST 'https://api.resend.com/emails/batch' \
  -H "Authorization: Bearer $RESEND_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '[
    {"from":"Acme <onboarding@resend.dev>","to":["foo@example.com"],"subject":"Welcome","html":"<p>Hi foo</p>"},
    {"from":"Acme <onboarding@resend.dev>","to":["bar@example.com"],"subject":"Welcome","html":"<p>Hi bar</p>"}
  ]'
```

**示例 — Python**

```python
import os, resend
from typing import List

resend.api_key = os.environ["RESEND_API_KEY"]

params: List[resend.Emails.SendParams] = [
    {"from": "Acme <onboarding@resend.dev>", "to": ["foo@example.com"], "subject": "Welcome", "html": "<p>Hi foo</p>"},
    {"from": "Acme <onboarding@resend.dev>", "to": ["bar@example.com"], "subject": "Welcome", "html": "<p>Hi bar</p>"},
]

result = resend.Batch.send(params)  # raises ResendError on failure, same as Emails.send
```

**示例 — Node.js**

```ts
import { Resend } from 'resend';

const resend = new Resend(process.env.RESEND_API_KEY);

const { data, error } = await resend.batch.send([
  { from: 'Acme <onboarding@resend.dev>', to: ['foo@example.com'], subject: 'Welcome', html: '<p>Hi foo</p>' },
  { from: 'Acme <onboarding@resend.dev>', to: ['bar@example.com'], subject: 'Welcome', html: '<p>Hi bar</p>' },
]);
```

## 限制（三条都要读——第一条是最容易踩的坑）

1. **⚠ 文档自相矛盾 —— 这里不支持附件，尽管 OpenAPI schema 看起来允许。** 这个端点的 OpenAPI 请求体 schema 就是单封发送用的同一个 `SendEmailRequest` 类型，`attachments` 字段也在里面，规范本身没有针对批量场景的任何说明。但**两个独立的**文字文档页面（`/docs/dashboard/emails/attachments`："We currently do not support sending attachments when using our batch endpoint"；`/docs/dashboard/emails/send-batch-emails` API 参考："The `attachments` field is not supported yet"）都明确禁止这么做。在这一点被真实调用验证之前，**不要通过批量端点发送附件**——假定这条被重复陈述了两次的文字限制，胜过 schema 表面上的宽松。如果一个 agent 需要给不同收件人发送不同的 PDF，改成循环调用单封的 `POST /emails`（并注意速率限制——见 `errors-and-limits.md`）。
2. **每次批量请求最多 100 封邮件。**
3. **批次里的每封邮件都是独立处理的**——不同的收件人、subject、HTML、附件情况（如上，n/a）、排期等等，在同一次批量调用里随便混用都没问题。
4. **只要数组里有任何一项无效，整个请求就会原子性地失败。** "The request will fail and return an error if any email in your payload is invalid (for example, required fields are missing or fields contain invalid data)"——这读起来像是在真正发送之前，对整个数组做一次全有或全无的校验，而不是部分成功、部分按条目报错的响应。⚠ 文档未说明 部分内容无效时具体是怎么上报的（错误体里会不会指出是数组里第几项出了问题）——依赖这一点做精细化错误处理之前先验证。
5. **排期是按条目生效的。** 批次里的每一项都可以带自己独立的 `scheduled_at`（自然语言或 ISO 8601)——不需要把整个批次都排在同一个时刻。
6. **所有批量发送的邮件在被逐条处理之前都会先进入 `queued` 状态**，在 dashboard 里和单条发送的邮件一起显示。
7. **一次批量调用 = 对速率限制只算一次请求**，不管里面装了多少封邮件（最多 100 封）。这是文档给出的、应对默认 10 req/s 限流下高发送量的官方方案——见 `errors-and-limits.md`。

## 批量发送 vs 循环单封发送 vs Broadcasts，该用哪个

| 需求 | 用 |
|---|---|
| 现在就要发最多 100 封各不相同的交易邮件，收件人/内容各不同 | `POST /emails/batch` |
| 单封邮件需要带附件 | `POST /emails`（多封就循环调用）—— 按限制第 1 条，**不能**用批量 |
| 一次逻辑操作里超过 100 封各不相同的交易邮件 | 多次调用 `POST /emails/batch`（注意速率限制——每次批量只算 1 次请求，所以理论上限是 10 批/秒 ≈ 1,000 封/秒，实际会先被配额/信誉限制卡住） |
| 一份内容发给一个大的订阅列表，需要处理退订/合规 | Broadcasts（`POST /broadcasts`）——本 skill 不覆盖，见 `resend.com/docs/dashboard/broadcasts/introduction` |
