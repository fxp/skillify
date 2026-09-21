# 错误码与限制速查

> 来自 https://supabase.com/docs/guides/api/rest/postgrest-error-codes、`guides/storage/debugging/error-codes`、`guides/functions/error-codes`、`guides/functions/status-codes`、`guides/functions/limits`、`guides/realtime/error_codes`、`guides/realtime/concepts`。抓取于 2026-09-21。**没有经过真实 API 调用验证**，本文件全篇均为 `⚠ 文档原文，未实测`。

## PostgREST / REST API（Data API）

响应统一是 JSON：`{"code": "...", "message": "...", "details": ..., "hint": ...}`。

**数据库层错误**（透传 Postgres 错误码，前两位/字母段决定分类）：

| Postgres 错误码 | HTTP | 含义 |
| --- | --- | --- |
| `23503` | 409 | 外键约束冲突 |
| `23505` | 409 | 唯一约束冲突 |
| `42501` | 已认证时 403，否则 401 | 权限不足（grant 缺失，见 `references/auth-and-rls.md`） |
| `42P01` | 404 | 表不存在 |
| `42703` | — | 列不存在（`message` 里通常会带"是不是想输入 XX"的 `hint`） |
| `42P17` | 500 | RLS policy 互相引用导致的无限递归 |
| `25006` | 405 | 只读事务里尝试写操作 |
| 其他 | 400 | 兜底 |

**API 层错误**（`PGRSTxxx`，PostgREST 自己抛出，和数据库无关）：

| Code | HTTP | 含义 |
| --- | --- | --- |
| `PGRST100` | 400 | query string 参数解析失败（filter 语法写错的典型表现） |
| `PGRST102` | 400 | 请求体格式不对（空 body、非法 JSON） |
| `PGRST106` | 406 | 请求的 schema 未被暴露给 API |
| `PGRST108` | 400 | 过滤条件作用在一个没出现在 `select` 里的关联资源上 |
| `PGRST114` / `PGRST115` | 400 | `PUT` 方式 upsert 时带了 limit/offset，或 query string 与 body 里的主键不一致 |
| `PGRST116` | 406 | 期望单条结果（比如客户端库的 `.single()`）但实际匹配 0 条或多条 |
| `PGRST120` | 400 | 对嵌套的关联资源用了 `is.null`/`not.is.null` 之外的过滤操作符（关联资源过滤有额外限制） |
| `PGRST200` | 400 | 外键关系找不到（schema 缓存过期，或关系确实不存在） |
| `PGRST201` | 300 | `select` 里的关联查询有歧义（多个外键都能匹配，需要显式指定用哪个） |
| `PGRST204` | 400 | `columns` 参数指定的列不存在 |
| `PGRST205` | 404 | URI 里的表/视图找不到（常见原因：确实不存在，或存在但没在 Exposed schemas/表里暴露） |

完整表见 postgrest.org 官方文档，此处只摘录高频出现的。

## Storage

响应格式：`{"code": "错误码字符串", "message": "..."}`。

| Code | HTTP | 含义 |
| --- | --- | --- |
| `NoSuchBucket` | 404 | bucket 不存在，或存在但当前角色无权限（两者同一响应） |
| `NoSuchKey` | 404 | 文件不存在，或无权限 |
| `InvalidJWT` | 401 | token 过期/格式错误 |
| `ResourceAlreadyExists` / `KeyAlreadyExists` | 409 | 路径冲突，没传 `x-upsert:true` |
| `AccessDenied` | 403 | RLS policy 不允许 |
| `EntityTooLarge` | 413 | 超过项目文件大小上限 |
| `InvalidMimeType` | 400 | Content-Type 不合法 |
| `MissingContentLength` | 411 | 缺 `Content-Length` header |

## Edge Functions

出错响应带 `sb-error-code` 响应头，代码里可以读它编程判断：

```js
const errorCode = response.headers.get('sb-error-code')
```

| Code | 含义 | 常见原因 |
| --- | --- | --- |
| `EDGE_FUNCTION_ERROR` | 函数抛了未捕获异常或返回 5xx | 缺少 try-catch |
| `IDLE_TIMEOUT` | 超过请求空闲超时未响应 | 慢查询、外部 API 调用无超时控制 |
| `WORKER_LIMIT` / `WORKER_RESOURCE_LIMIT` | 触发内存/CPU 等资源上限 | 参见 `references/edge-functions.md` 的限制表 |
| `WORKER_ERROR` | 未捕获异常（worker 层面） | 同 `EDGE_FUNCTION_ERROR`，触发时机略有不同 |

## Realtime

- 未升级到用户级鉴权的公开连接最长存活 **24 小时**，到点强制断开。
- 连接数/消息速率、数据库连接池大小按项目 Compute Add-on 规格分级（Nano 到 16XL+），规格越小限制越紧，具体数字见 `guides/realtime/concepts` 原文（不同规格差异较大，这里不逐档抄录，需要精确数字时直接查 Dashboard 当前项目规格对应的原始表格）。
- `realtime.messages` 表有清理策略，超过 3 天的消息记录会被清除（这张表本身不是消息队列，只是权限判断和广播的中转，不应该被当成消息持久化存储使用）。

## 通用建议

- **`42501`（grant 缺失）和"RLS policy 过滤掉了这一行"是两种不同的失败**，前者报错、后者静默返回空结果，排查方向完全不同，详见 `references/auth-and-rls.md`。
- Data API 的 body/query 错误信息里经常带 `hint` 字段（比如列名拼写建议、需要的 GRANT 语句），生产代码可以把 `hint` 一并记录/展示，比只看 `message` 更容易定位问题——`⚠ 文档原文，未实测`，这条建议本身合理但未验证 `hint` 在所有错误类型下是否总是存在。
