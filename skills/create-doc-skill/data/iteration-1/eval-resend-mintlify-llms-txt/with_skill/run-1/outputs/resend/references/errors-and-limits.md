# Resend · 错误码、限额、分页、重试

> **⚠ 验证状态：本文件全部内容为 OpenAPI 规范（resend/resend-openapi v1.5.1）与 https://resend.com/docs 页面的转录（抓取于 2026-09），尚未用真实 API key 调用验证。实际报错以 API 为准；未验证细节以 ⚠ 标出。**

来源页：`api-reference/introduction`、`api-reference/errors`、`api-reference/rate-limit`、`api-reference/pagination`、`knowledge-base/403-error-1010`。

## 目录
1. 错误响应结构
2. 错误码总表（按 HTTP 状态）
3. 速率限制与配额（响应头）
4. 分页（cursor）
5. 重试策略（官方给 AI 的建议）
6. 用 TypeScript 统一处理

## 1. 错误响应结构

REST 错误体是扁平 JSON，三个字段：

```json
{ "statusCode": 422, "name": "validation_error", "message": "The pagination limit must be a number between 1 and 100. ..." }
```

- `name` 是机器可读的错误类型（见下表），`message` 是给人看的说明。
- Node SDK 不抛异常，而是返回 `{ data: null, error: { name, message } }`；只有网络层故障才会 throw。
- 官方文档 FAQ：目前**没有 API 版本机制**，将来计划用日历式 header 做版本，现在不需要传版本头。

## 2. 错误码总表

| HTTP | `name` | 含义 / 触发条件 | 建议动作 |
|---|---|---|---|
| 400 | `invalid_idempotency_key` | `Idempotency-Key` 长度不在 1–256 | 换合法 key 重试 |
| 400 | `validation_error` | 字段校验失败，`message` 里说明是哪个字段 | 修请求，不要重试 |
| 401 | `missing_api_key` | 没带 `Authorization: Bearer …` | 补 header |
| 401 | `restricted_api_key` | key 是 `sending_access`，却调了发信以外的接口 | 换 `full_access` key |
| 403 | `email_above_quota` | 收到的邮件超配额，无法读取正文 | 升级计划 |
| 403 | `invalid_permission` | OAuth access token 缺 scope | 申请含所需 scope 的 token |
| 403 | `restricted_api_key` | "API key is not active"（⚠ 文档把 `restricted_api_key` 同时列在 401 和 403 下，两种 message 不同，实测才能确认各自触发条件） | 去控制台检查 key |
| 403 | `suspended_api_key` | key 被停用 | 联系支持 |
| 403 | `validation_error` | 用 `onboarding@resend.dev` 发给非本账号邮箱："You can only send testing emails to your own email address" | 验证自己的域名并改 `from` |
| 403 | `validation_error` | `from` 域名未验证："The domain.com domain is not verified" | 先在 /domains 验证 |
| 403 | `validation_error` | 域名已被别的团队注册 | 检查登录账号 / 联系支持 |
| 403 | （HTTP 错误码 `1010`） | **缺 `User-Agent` header**。这是 Cloudflare 层拦截，不是 Resend 的 `name` 字段——用 `fetch`/裸 HTTP 时最常见的"key 明明对却 403" | 加 `User-Agent: my-app/1.0` |
| 403 | `validation_error` | 联系人超配额后发 broadcast："You have reached your contacts quota" | 升级 Marketing 计划 |
| 404 | `not_found` | 路径不存在 | 检查 URL |
| 405 | `method_not_allowed` | 方法不对 | — |
| 409 | `concurrent_idempotent_requests` | 同一 idempotency key 的请求还在处理 | 稍后重试 |
| 409 | `invalid_idempotent_request` | 24 小时内同 key + 同 method/endpoint，但 body 不同 | 换 key 或改回原 payload |
| 409 | `resource_locked` | 另一个请求正在更新该资源 | 短暂延迟后重试 |
| 422 | `invalid_attachment` | attachment 既无 `content` 也无 `path` | 二选一 |
| 422 | `invalid_parameter` | 参数不是合法 UUID | 检查 id |
| 422 | `missing_required_field` / `missing_required_parameter` | 缺必填字段 / 参数，`message` 列出缺哪些 | 补齐 |
| 429 | `daily_quota_exceeded` | 免费计划每日发信配额用尽（收+发都计入） | 等 24h 或升级 |
| 429 | `monthly_quota_exceeded` | 月配额用尽 | 升级 |
| 429 | `rate_limit_exceeded` | 超过每秒请求数 | 读 `retry-after` 退避 |
| 500 | `application_error` | 服务端异常 | 指数退避重试 |
| 503 | `service_unavailable` | 服务暂不可用 | 重试 / 看 resend-status.com |

⚠ 文档自相矛盾：`validation_error` 在 errors 页标为 400，而 pagination 页的示例错误体里 `statusCode` 是 422。具体哪些校验返回 400、哪些返回 422 需要真实调用确认；写代码时把 400 和 422 都当"请求参数错误、不要重试"处理即可。

## 3. 速率限制与配额

- 默认 **10 requests/second/team**，团队下所有 API key 共享；可申请提升，当前值在 Settings → Usage 页看。
- 每次响应都带（IETF ratelimit-headers 草案第 6 版格式）：

| Header | 含义 |
|---|---|
| `ratelimit-limit` | 窗口内允许的最大请求数 |
| `ratelimit-remaining` | 当前窗口剩余 |
| `ratelimit-reset` | 距窗口重置的秒数 |
| `retry-after` | 建议等待秒数（429 时用它） |
| `x-resend-daily-quota` | 已用日配额（**只有免费计划返回**） |
| `x-resend-monthly-quota` | 已用月配额 |

- 三类限制：每秒请求数（429 `rate_limit_exceeded`）、邮件配额（429 `daily_/monthly_quota_exceeded`，**收件也计入**）、联系人配额（超出后 broadcast 发送返回 403 `validation_error`，但仍可继续新增联系人）。
- 批量发送 `POST /emails/batch` 一次最多 100 封，只算 1 次请求——需要高吞吐时优先用它而不是并发 100 次 `POST /emails`。

## 4. 分页（cursor-based）

- 参数：`limit`（1–100，默认 20）、`after`（取"该 id 之后"的一页）、`before`（取"该 id 之前"的一页）。**`after` 和 `before` 不能同时传**，否则 `validation_error`。
- cursor 就是对象的 `id`；cursor 本身不包含在结果里。
- 响应：`{ "object": "list", "has_more": true, "data": [ ... ] }`。**先看 `has_more` 再翻页**。
- 两类 list 接口行为不同：
  - **老接口**（List Domains / API Keys / Broadcasts / Segments / Contacts / Receiving Emails / Receiving Email Attachments）：`limit` 可选，**不传 `limit` 时一次返回全部**。
  - **新接口**（List Emails / Templates / Topics）：总是分页。
- ⚠ 文档未说明：不传 `limit` 的老接口在数据量很大时是否有隐式上限。

```ts
import { Resend } from 'resend';
const resend = new Resend(process.env.RESEND_API_KEY);

async function allContacts() {
  const out: { id: string; email: string }[] = [];
  let after: string | undefined;
  while (true) {
    const { data, error } = await resend.contacts.list({ limit: 100, after });
    if (error) throw new Error(`${error.name}: ${error.message}`);
    out.push(...data.data);
    if (!data.has_more) break;
    after = data.data[data.data.length - 1].id;
  }
  return out;
}
```

## 5. 重试策略（来自官方 ai-onboarding 页的建议）

| 状态 | 动作 |
|---|---|
| 400 / 422 | 修参数，不重试 |
| 401 / 403 | 检查 key / 域名验证 / User-Agent，不重试 |
| 409 | 幂等冲突——换 key 或修 payload |
| 429 | 指数退避重试（1s, 2s, 4s…），最多 3–5 次，优先按 `retry-after` |
| 500 / 503 | 指数退避重试 |

**重试发信请求时必须带 `Idempotency-Key`**（`POST /emails`、`POST /emails/batch` 支持；SMTP 用 `Resend-Idempotency-Key` 邮件头），否则重试会重复发送。详见 `sending.md`。

## 6. 用 TypeScript 统一处理

```ts
// 裸 HTTP 版：把三个必需 header 和错误结构一次封装好
type ResendError = { statusCode: number; name: string; message: string };

export async function resendFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`https://api.resend.com${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
      'User-Agent': 'my-app/1.0',          // 缺它会被 403 (code 1010) 拦截
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
  });
  if (res.status === 429) {
    const wait = Number(res.headers.get('retry-after') ?? 1);
    throw Object.assign(new Error(`rate limited, retry after ${wait}s`), { retryAfter: wait });
  }
  const body = await res.json();
  if (!res.ok) {
    const e = body as ResendError;
    throw new Error(`Resend ${e.statusCode ?? res.status} ${e.name}: ${e.message}`);
  }
  return body as T;
}
```
