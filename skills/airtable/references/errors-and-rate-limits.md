# 错误码与限流

目录：[错误响应结构](#错误响应结构) · [状态码表](#状态码表) · [限流（重点：按 base 维度）](#限流重点按-base-维度) · [官方与社区 SDK](#官方与社区-sdk)

## 错误响应结构

出错时返回 JSON body，形如：

```json
{"error": {"type": "INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND", "message": "人类可读的说明"}}
```

个别老 endpoint（如 404）历史上可能只返回 `{"error": "NOT_FOUND"}`（`error` 是字符串而不是对象）——解析错误响应的代码建议兼容两种形状（`error` 可能是字符串或 `{type, message}` 对象），不要假设永远是后者。

## 状态码表

| 状态码 | 含义 | 备注 |
|---|---|---|
| `200` | 成功 | 企业账号特例：返回 200 但 `bases` 是空数组，通常是企业管理员开了 API 访问限制，不是 token 权限问题，见 auth-and-scopes.md |
| `400` | 请求体不是合法 JSON | — |
| `401` | 未鉴权 / token 无效 | — |
| `403` | 无权限访问该资源 | 常见原因排查顺序见 auth-and-scopes.md 最后一节 |
| `404` | 路由或资源不存在 | 包括资源已被删除的情况 |
| `413` | 请求体超过大小上限 | 官方原文"正常使用不应该遇到" |
| `422` | 请求数据校验失败 | 会带具体错误码和消息，比如字段类型不匹配、选项不存在等 |
| `429` | 触发限流 | 见下方"限流"章节，**固定等待 30 秒**再重试 |
| `500` | 服务端内部错误 | — |
| `502` | 服务重启/临时故障 | 官方原文"可以安全重试" |
| `503` | 服务暂时不可用/处理超时 | 建议退避后重试；可能带 `Retry-After` 响应头 |

**常见 `422`/`403` 错误类型示例**（均为文档原文转录，⚠ 未实测确认精确文案是否仍然一致）：

- `INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND` — 权限不足或资源不存在（403，两种原因返回同一个错误类型，故意不区分以避免暴露资源是否存在）。
- `INVALID_PERMISSIONS` — 更具体的权限不足场景，`message` 里会带具体的 table/field 名字，比如"不允许在表 X 创建记录"、"不允许写字段 Y"。
- `INVALID_REQUEST_UNKNOWN` — 通用的请求体校验失败（422）。
- `INVALID_MULTIPLE_CHOICE_OPTIONS` — 单选/多选传了不存在的选项且未开 `typecast`。
- `RATE_LIMIT_REACHED` — 429，见下方。
- `RETRIABLE_ERROR` — 503，明确提示可以安全重试。
- `LIST_RECORDS_ITERATOR_NOT_AVAILABLE` — List records 分页游标失效（422），需要从第一页重新开始。

## 限流（重点：按 base 维度）

官方 `rate-limits.md` 原文（抓取于 2026-09-21）：

> The API is limited to **5 requests per second per base**.
> Additionally, there is a limit of **50 requests per second** for all traffic using personal access tokens from a given user or service account.

两层限速同时生效：

1. **每个 base 5 请求/秒**——这是主要约束，且是**按 baseId 维度独立计数**的。
2. **每个用户（或 service account）名下所有请求加总 50 请求/秒**——覆盖该用户/账号名下所有 base 的总流量。

**给多 base Agent 的实现建议**：限流器要按 `baseId` 分别维护独立的令牌桶/计数器（每个上限 5 req/s），而不是共用一个全局计数器——用一个全局计数器要么在只操作单个 base 时误伤（把 50/s 的总闸当成单 base 的 5/s 用，浪费配额），要么在同时操作多个 base 时漏算（以为总共还有余量，实际某个 base 已经单独触顶）。全局的 50/s 闸门需要额外再包一层跨 base 共享的计数器。

**触发限流后的行为**：返回 `429` + `{"error": {"type": "RATE_LIMIT_REACHED", "message": "Rate limit exceeded. Please try again later"}}`，**必须等待 30 秒**才能继续成功请求——官方文档没有提"指数退避"，而是给了一个固定的等待时长，这点和很多其它主流 REST API（用 `Retry-After` 头 + 指数退避）的常见约定不同，写重试逻辑时不要想当然套用指数退避的默认实现，至少要保证首次重试间隔 ≥ 30 秒。

其它相关点：

- **Upsert（`performUpsert`）请求可能有独立于标准限流的节流策略**，官方保留权限单独调整，具体数字未给出（⚠ 未实测确认）。
- Billing plan 影响的是**能不能访问哪些 endpoint**（Free/Teams/Business 能访问除 Views 外的全部"Base Data"接口；Business 额外有 SCIM；Enterprise Scale 能访问全部含企业 API），不影响每秒请求数限制本身；另外官方提到 "Public API limit" 目前只在 Free 计划强制执行（月度调用总量上限，独立于这里的秒级限流，详见 [`managing-api-call-limits-in-airtable`](https://support.airtable.com/docs/managing-api-call-limits-in-airtable)）。
- 官方建议：预期读取量大的场景加一层自己的缓存代理，而不是每次都直接打 Airtable API。

## 官方与社区 SDK

| SDK | 语言 | 状态 | 备注 |
|---|---|---|---|
| [`airtable.js`](https://github.com/Airtable/airtable.js) | JavaScript（Node.js + 浏览器） | **官方维护** | 官方文档列为唯一 "Official API client"；内置退避重试逻辑 |
| [`pyairtable`](https://github.com/gtalarico/pyairtable) | Python 3 | 社区维护，官方文档并列推荐 | 内置批量分批（10 条/请求）、分页迭代器；见 write-records.md |
| [`airtable.py`](https://github.com/josephbestjames/airtable.py) | Python 2/3 | 社区维护 | 官方文档列出，未展开评估 |
| [`airrecord`](https://github.com/sirupsen/airrecord) | Ruby | 社区维护 | — |
| [`airtable.net`](https://github.com/ngocnicholas/airtable.net) | .NET | 社区维护 | — |

新写 Python 代码优先用 `pyairtable`（`pip install pyairtable`）而不是手写 HTTP 请求，能免费拿到批量分批、分页、字段 ID/名互转这些已经踩过的坑；新写 Node.js/浏览器代码优先用官方 `airtable.js`。手写 HTTP 请求（curl / `requests` / `fetch`）适合快速验证或语言没有对应 SDK 的场景，本 skill 的示例默认给这两种。
