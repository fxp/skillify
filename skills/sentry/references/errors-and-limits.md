# 分页、限流、报错约定（Web API）

> ⚠ 全部内容来自 `docs.sentry.io/api/pagination.md`、`docs.sentry.io/api/ratelimits.md`、`docs.sentry.io/api/requests.md` 转录，未经真实调用验证。

## 目录

- [请求约定](#请求约定)
- [分页：Link Header + Cursor](#分页link-header--cursor)
- [限流](#限流)
- [HTTP 状态码与报错格式](#http-状态码与报错格式)

## 请求约定

- 全部请求走 `https://{region}.sentry.io/api/0/` 前缀,响应统一 JSON。
- HTTP 动词按标准 REST 语义:`GET` 读、`POST` 创建、`PUT` 更新(**支持部分字段更新,不要求传完整对象**)、`DELETE` 删除、`OPTIONS` 描述该 endpoint。官方原话:"we always prioritize usability over correctness"——即不严格照搬 REST 教条,遇到实际行为和"标准 REST 应该怎样"的直觉不一致时,以文档/实测为准。
- 请求体统一 `Content-Type: application/json`。**部分参数即使是 POST/PUT/DELETE,也会走 query string 而不是 body**(比如批量操作的 `id` 参数),具体哪个参数走 body、哪个走 query,以每个 endpoint 自己的参数表为准,不要假设"POST 的参数都在 body 里"。

```bash
curl -i https://sentry.io/api/0/organizations/acme/projects/1/groups/ \
    -d '{"status": "resolved"}' \
    -H 'Content-Type: application/json'
```

## 分页：Link Header + Cursor

**不是页码分页,是游标(cursor)分页,通过 HTTP `Link` header 传递。**

请求任意支持分页的 endpoint,响应 header 里会有形如这样的 `Link`:

```
Link: <...?&cursor=0:0:1>; rel="previous"; results="false"; cursor="0:0:1",
      <...?&cursor=0:100:0>; rel="next"; results="true"; cursor="0:100:0"
```

- 两个方向(`rel="previous"`、`rel="next"`)**总是都存在**,哪怕没有更多数据——用 `results="true"/"false"` 判断该方向是否真的还有数据,不要用"URL 存在与否"判断。
- 翻页逻辑:取 `rel="next"` 那个 URL 直接请求,重复直到它的 `results="false"`。
- `cursor` 值的三段结构:游标标识符(整数,通常是 0)、行偏移、是否反向(1/0)——**当成不透明字符串直接用即可,不要自己拼**。

```python
import requests

url = "https://us.sentry.io/api/0/organizations/acme/issues/123456/events/"
headers = {"Authorization": f"Bearer {token}"}

while url:
    resp = requests.get(url, headers=headers)
    for item in resp.json():
        yield item
    # 从 Link header 解析下一页(用 requests 自带的 resp.links)
    next_link = resp.links.get("next")
    url = next_link["url"] if next_link and next_link.get("results") == "true" else None
```

⚠ 文档原文,未实测:`requests` 库的 `resp.links` 能否正确解析出 `results` 这个自定义属性(标准 `Link` header 解析器通常只认 `rel`,`results` 是 Sentry 自定义的扩展属性,可能需要手动解析 header 原始字符串而不是依赖库的 `.links`)。

## 限流

每次响应都带以下 header,不需要靠猜就知道还剩多少配额:

| Header | 含义 |
| :--- | :--- |
| `X-Sentry-Rate-Limit-Limit` | 当前窗口允许的最大请求数 |
| `X-Sentry-Rate-Limit-Remaining` | 当前窗口剩余可用请求数 |
| `X-Sentry-Rate-Limit-Reset` | 窗口重置时间(UTC 秒级时间戳) |
| `X-Sentry-Rate-Limit-ConcurrentLimit` | 允许的最大并发请求数 |
| `X-Sentry-Rate-Limit-ConcurrentRemaining` | 剩余可用并发数 |

**限流按"调用方身份 + endpoint"的组合分别计算**,不同 endpoint 的具体阈值和窗口大小不一样,且**限流看的是调用方身份,不是具体用哪个 token**——换多个 token 也绕不过去(官方原话:"the rate limiter looks at the caller's identity instead of the bearer token or cookie")。

**轮询式地反复调用同一个 endpoint 检查是否有新数据,很容易触发限流。** 官方明确建议:需要"实时知道有没有新东西"这种场景,改用 webhook(见 `alerts-and-webhooks.md`)而不是轮询。

## HTTP 状态码与报错格式

标准 HTTP 状态码语义:

| 状态码 | 常见含义(来自本 skill 各 reference 里出现过的具体场景) |
| :--- | :--- |
| `200`/`201` | 成功(`201` 常见于创建类 POST) |
| `202` | 已接受,异步处理中(如删除 issue) |
| `204` | 成功但无内容(如批量操作没有匹配到任何记录、DELETE 成功) |
| `208` | Already Reported(创建 release 时,该 version 已存在,不算错误) |
| `401` | 鉴权失败(token 过期/无效/被吊销) |
| `403` | 鉴权成功但 scope/权限不够 |
| `404` | 资源不存在,**或者路径拼错**(org/project slug 写错、漏了路径段) |
| `429` | 触发限流(配合上面的 `X-Sentry-Rate-Limit-*` header 判断何时重试) |

**⚠ 具体的错误响应体格式,官方 OpenAPI 规范里没有统一定义**(规范里 4xx 响应大多只写了 `"description": "Forbidden"` 这样的文字说明,没有给出 JSON body 的 schema)。不要凭训练记忆假设一个固定的 `{"detail": "..."}` 或 `{"error": "..."}` 结构去写解析代码——**用之前先真实触发几种失败场景,把实际返回的 body 记录下来**,这是 `verification-plan.md` 里明确列出的一项。保险的写法是:先看 HTTP 状态码决定成功/失败,报错文本只用来记日志/展示给人看,不要用代码去解析报错 body 里的特定字段驱动业务逻辑分支(除非已经实测确认过那个字段稳定存在)。

## 与本 skill 其他文件的关系

- 具体某个 endpoint 需要哪个 scope,见 `auth-and-tokens.md` 的 scope 对照表——`403` 十有八九是这里的问题。
- 批量操作(issue 批量更新/删除)的"部分 ID 越权时静默跳过、不整体报错"这种行为,见 `issues.md`——不是这里的通用规则,是那几个特定 endpoint 自己的行为。
