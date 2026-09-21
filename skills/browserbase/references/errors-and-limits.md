# Browserbase：错误处理、HTTP 状态码与限流

> ⚠ 本文件全部内容整理自 https://docs.browserbase.com 的已抓取页面（抓取于 2026-09-21），**未使用真实 API Key 验证**。实际调用报错请优先信任真实 API 返回，而不是本文件。

## ⚠ 重要提示：Browserbase 没有统一的错误码参考页

在抓取到的材料范围内（`reference/api/*`、`optimizations/concurrency/overview.md`、`platform/identity/proxies.md`、`platform/browser/long-sessions/timeouts.md`、`platform/browser/observability/*`、`account/billing/plans.md` 等所有列出的页面），**没有找到一个专门汇总"错误码 / 错误体格式"的独立参考页**，不像有些平台会有一页专门列出所有 4xx/5xx 语义。

⚠ 文档未说明：官方文档未提供统一错误码表，以下为分散在各页面中提到的具体报错。本文件只收录了在材料里**实际找到文字证据**的报错——**没有**发明一张通用的 401/403/404/429/500 REST 错误码表。凡是没有在源材料里看到文档明确写出的状态码或错误体，本文件都不列。已确认缺失的部分见文末"已知缺口"。

---

## 1. 按能力域列出的具体报错（找到什么就列什么）

### 会话超时

**来源**：`platform/browser/long-sessions/timeouts.md`、`platform/browser/getting-started/manage-browser-session.md`

会话运行超过 `timeout`（或项目默认超时）后：

```
TimeoutError: Timeout _____ms exceeded
```

`_____` 是文档原文里的占位符，代表实际超时的毫秒数，不是字面量。⚠ 文档没有说明这个错误是哪一层抛出的（SDK 客户端异常？CDP 连接错误？HTTP 响应体？），只给出了这一行文案。

### 代理连接失败

**来源**：`platform/identity/proxies.md`「Troubleshoot proxy errors」小节

```
ERR_TUNNEL_CONNECTION_FAILED
```

文档说明这个错误可能代表三种情况之一：目标站点不被 Browserbase 内置代理支持、指定的城市（city）不被支持、或临时性代理故障。这是一个 Chromium 网络层错误码（`net::ERR_*` 系列），不是 Browserbase 自定义的 HTTP 状态码。

另外，自定义代理（`type: "external"`）在会话创建时会被验证：

> "Browserbase validates proxy connections at session creation time. If Browserbase can't connect to the specified proxy, an error is thrown."

⚠ 文档未说明：这里"an error is thrown"具体是什么状态码或错误体，没有给出示例。

### 自定义 CA 证书 ID 无效

**来源**：`platform/identity/proxies.md`「Trusted CA certificates」小节

> "`caCertificates` accepts an array, so you can trust multiple custom CAs in a single session. If any ID doesn't exist or doesn't belong to your project, session creation fails with a **400**."

这是材料中少数几处明确给出具体 HTTP 状态码（400）的地方，但没有给出响应体的字段格式。

### Recording Downloads API（`/v1/sessions/{id}/recording/downloads`）

**来源**：`reference/api/create-session-recording-downloads.md`、`reference/api/list-session-recording-downloads.md`（对应 openapi-summary/v1.md）、`platform/browser/observability/recording-downloads.md`

这是材料中文档最齐全的一组错误响应，GET 和 POST 共用同一套：

| 状态码 | 含义 | 响应体字段 |
|---|---|---|
| `404` | 会话不存在，或该会话没有录像 | `statusCode`, `error`, `message` |
| `409` | 会话尚未结束——录像下载只在会话完成后才可用 | `statusCode`, `error`, `message` |
| `410` | 该会话录像已超出留存窗口（非 BYOS 31 天 / BYOS 24 小时），无法再组装 | `statusCode`, `error`, `message` |
| `422` | 该会话创建时 `recordSession: false`，没有录像可下载。精确响应体：`{"message": "Recording was disabled for this session"}` | `statusCode`, `error`, `message` |
| `502` | 未能连接到录制服务，建议重试 | `statusCode`, `error`, `message` |

### Session Replay API（`/v1/sessions/{id}/replays[/{pageId}]`）

**来源**：`platform/browser/observability/session-replay.md`

- 留存窗口过期后（非 BYOS 31 天 / BYOS 24 小时），或会话本来就没有录像（`recordSession: false`）：两种情况**返回完全相同的响应** —— `404 Not Found`，响应体 `{"message": "Replay not found"}`。文档明确指出这两种情况从错误本身无法区分。
- 播放列表端点 `GET /v1/sessions/{id}/replays/{pageId}` 限流：**每个项目每分钟 120 次请求**（持续 2 RPS，允许短时突发）。超限返回 `429`，"带标准限流响应头"（文档原文如此表述，没有像并发限流那节那样给出具体头名称示例——参见下文第 2 节的 `x-ratelimit-*` 头，大概率是同一套，但这里文档没有重复给出）。

### Fetch API（`POST /v1/fetch`）

**来源**：openapi-summary/v1.md 对 `POST /v1/fetch` 的响应定义（这是材料里 OpenAPI 层面记录最完整的一组错误响应）

| 状态码 | 含义 | 响应体字段 |
|---|---|---|
| `400` | 请求体无效，或该 `format` 不支持所抓取内容的 content type | `statusCode`, `error`, `message`, `id`(可选) |
| `402` | Free 计划该 format 的配额已用完 | 无响应体字段定义 |
| `403` | 项目未启用该 `format`；不启用的情况下只有 `raw` 可用 | 无响应体字段定义 |
| `429` | 并发 fetch 请求数超限 | `statusCode`, `error`, `message`, `id`(可选) |
| `502` | 抓取到的响应过大，或 TLS 证书验证失败 | `statusCode`, `error`, `message`, `id` |
| `503` | fetch 服务暂时不可用 | `statusCode`, `error`, `message`, `id` |
| `504` | fetch 请求超时 | `statusCode`, `error`, `message`, `id` |

⚠ 文档未说明：这组状态码来自 OpenAPI spec 的响应 schema 定义，`reference/api/fetch-a-page.md` 页面本身在抓取材料里没有额外的散文说明这些错误分别在什么场景触发（比如 402 的具体触发条件、429 的窗口时长）——除了状态码语义描述本身，没有更多上下文。

### Agent Runs（`/v1/agents/runs/*`）

**来源**：openapi-summary/v1.md

Agent run 对象上有一个结构化失败字段 `cause`：

```json
{
  "cause": {
    "code": "RUNNER_HEARTBEAT_LOST",
    "message": "..."
  }
}
```

`code` 字段类型是 string，openapi-summary 只给出了一个示例值 `RUNNER_HEARTBEAT_LOST`，**没有给出完整的枚举列表**。停止一个已经结束的 run（`POST /v1/agents/runs/{runId}/stop`）会返回 conflict（文档原文："Stopping a run that has already finished returns a conflict"，未给出具体状态码数字，合理推测是 `409` 但文档没有明说）。

### Functions（`/v1/functions/*`）—— ⚠ 超出本次抓取材料的核心范围，仅记录 openapi-summary 里出现的结构化失败码

Function Build 失败码（`cause.code` 枚举）：`NO_MANIFESTS_FOUND`, `TOO_MANY_MANIFESTS`, `MANIFEST_TOO_LARGE`, `INVALID_SESSION_CREATE_PARAMS`, `TIMED_OUT`

Function Invocation 失败码（`cause.code` 枚举）：`TIMED_OUT`, `INTERNAL_ERROR`, `WORKLOAD_ERROR`

这两组是 OpenAPI schema 里定义的 enum，不是从正文散文里找到的说明，Functions 本身不在本次要求覆盖的核心范围内，此处仅作为"确实在材料里出现过的具体报错字符串"补充记录。

### Webhooks

**来源**：openapi-summary/v1.md

创建/更新 Webhook 时，`eventTypes` 字段如果包含未知事件类型：「Unknown types are rejected」。⚠ 文档未说明具体状态码或响应体格式。

---

## 2. 并发限流与会话创建速率限流（429）——文档里最完整的一段限流处理指南

**来源**：`optimizations/concurrency/overview.md`，交叉核对 `account/billing/plans.md` 的 Accordion

这是材料中**唯一**一处给出了完整重试/退避范式的地方，值得重点参考。

### 两条独立限制

- **Max Concurrent Browsers**（并发上限）：同一时刻最多能跑多少个会话
- **Session Creation Limit**（创建速率上限）：任意 60 秒窗口内最多能新建多少个会话

任意一个被命中，新建会话的请求就会收到 `429 Too Many Requests`，请求被直接丢弃。

### 各计划限额

| Plan | Free | Developer | Startup | Scale |
|---|---|---|---|---|
| Max Concurrent Browsers | 3 | 25 | 100 | 250+ |
| Session Creation Limit / 分钟 | 5 | 25 | 50 | 150+ |

官方算例：Startup 计划并发上限 100、创建速率 50/分钟——即便并发允许 100 个同时跑，一次性创建 100 个会话也要大约 **2 分钟**才能全部建完，因为创建速率是瓶颈。

### 429 响应头

```
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
x-ratelimit-limit: 25
x-ratelimit-remaining: 0
x-ratelimit-reset: 45
retry-after: 45
```

| 响应头 | 含义 |
|---|---|
| `x-ratelimit-limit` | 该窗口内允许的最大请求数 |
| `x-ratelimit-remaining` | 该窗口内剩余可用请求数 |
| `x-ratelimit-reset` | 距限流重置还有多少秒 |
| `retry-after` | 必须等待多少秒才能再次请求 |

### 官方给出的重试模式（指数退避 + 尊重 `retry-after`）

```typescript
const MAX_RETRIES = 5;

async function createSessionWithRetry() {
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    try {
      return await bb.sessions.create();
    } catch (error: any) {
      if (error.status !== 429 || attempt === MAX_RETRIES - 1) throw error;
      const retryAfter = parseInt(error.headers?.["retry-after"] ?? "2", 10);
      const backoff = retryAfter * 1000 * Math.pow(2, attempt);
      await new Promise((resolve) => setTimeout(resolve, backoff));
    }
  }
}
```

```python
MAX_RETRIES = 5

async def create_session_with_retry():
    for attempt in range(MAX_RETRIES):
        try:
            return bb.sessions.create()
        except Exception as error:
            status = getattr(error, "status_code", None)
            if status != 429 or attempt == MAX_RETRIES - 1:
                raise
            retry_after = int(getattr(error, "headers", {}).get("retry-after", 2))
            backoff = retry_after * (2 ** attempt)
            await asyncio.sleep(backoff)
```

命中限流长期化的话：升级计划，或用 keep-alive 复用会话减少创建频率，或联系 `support@browserbase.com`。

---

## 3. Search / Fetch API 的速率限制

**来源**：`account/billing/plans.md`「API allocations」表

| API | 速率限制（所有计划一致） | 月度额度（Free / Developer / Startup） |
|---|---|---|
| **Search** | 2 次/秒 | 1,000 次（三档一致） |
| **Fetch** | 5 次/秒 | 1,000 次 / 1,000 次 / 10,000 次 |

⚠ 文档未说明：这两条速率限制超限后具体返回什么状态码/响应体——Fetch 的 `POST /v1/fetch` 端点在 OpenAPI 里确实定义了 `429`（"Concurrent fetch request limit exceeded"，见第 1 节），但那描述的是"并发请求数"超限，和这里"每秒次数"限制是不是同一套机制，文档没有说清楚，也没有找到 Search API（`POST /v1/search`）对应的错误响应定义。

---

## 4. 请求失败时该怎么办——只收录文档给出的具体建议

### 代理相关报错（`ERR_TUNNEL_CONNECTION_FAILED`）

来源：`platform/identity/proxies.md`

1. 先尝试不用代理直接访问该站点（部分站点本身对代理有限制，见该文档"Site restrictions"清单：银行金融、政府域名、流媒体、票务、webmail、博彩类站点对第三方住宅代理支持较差）
2. 如果指定了城市，去掉城市限制重试，或换一个城市
3. 重试该会话，排除临时性代理故障
4. 如果需要的城市当前不支持，联系 `support@browserbase.com`

### Recording Downloads 失败排查

来源：`platform/browser/observability/recording-downloads.md`

| 现象 | 原因 |
|---|---|
| GET 返回 `409` | 会话还没结束，只有结束后才能组装下载 |
| GET 返回 `410` | 录像已超出留存窗口（非 BYOS 31 天 / BYOS 24 小时），无法再组装 |
| 某个 page 一直卡在 `PENDING` | 大录像组装较慢，继续轮询即可；只有变成 `FAILED` 才需要重新 POST |
| `COMPLETED` 但没有 `downloadUrl` | 该项目是 BYOS，文件在你自己的 bucket 里，API 不会返回签名 URL |

### Session Replay 播放排查

来源：`platform/browser/observability/session-replay.md`

| 现象 | 原因 / 处理 |
|---|---|
| 播放列表加载了但没有画面 | 部分 HLS 播放器在 `loadedmetadata` 后不会自动播放，需要手动调用 `video.play()`；多数浏览器要求 `muted` 才允许自动播放 |
| 播放几小时后分段请求开始失败 | 分段签名 URL 签发后 6 小时过期，重新拉一次播放列表即可拿到新链接 |
| Chromium 走了原生 HLS 而不是自己接入的 JS 播放器 | Chromium 自带原生 HLS，可能绕过播放器库的 `canPlayType` 检测；优先用库自身的能力检测（如 `Hls.isSupported()`）而不是依赖原生回退 |

### 通用调试建议（Session Inspector）

来源：`platform/browser/observability/observability.md`「Debugging tips」表格，原样保留：

| Issue | Solution |
|---|---|
| Session terminated unexpectedly | Check Status Bar for termination reason |
| Selector not found | Use DOM view to inspect element state at failure point |
| Network request failed | Check Network tab for status codes and response details |
| Bot protection issues | Review console logs for solving events, check Agent Identity |

有问题可邮件 `support@browserbase.com`。

---

## 已知缺口（明确说明缺什么，而不是假装齐全）

以下几类信息在本次抓取的材料范围内**没有找到**，不要凭训练记忆或其他平台的经验去猜：

- **认证失败的错误体格式**：API Key 缺失/无效时，`x-bb-api-key` 校验失败具体返回什么状态码（大概率是 401，但材料里没有一处明确写出）、响应体长什么样——完全没有文档证据。
- **一份统一的"全端点错误码总表"**：不存在。每个端点的错误响应要看该端点自己的 OpenAPI 定义（多数端点，比如 `POST /v1/sessions`，OpenAPI 里甚至只定义了成功响应 `201`，没有定义任何 4xx/5xx schema）。
- **Search API（`POST /v1/search`）的错误响应**：openapi-summary 里这个端点只有 `200` 的 schema，没有错误响应定义。
- **超过并发/创建速率之外的其它限流场景（比如认证失败次数限流、Contexts/Certificates/Extensions 的错误响应）**：材料中未见文档说明。
- **SDK（Node/Python）把 HTTP 错误包装成什么异常类型/字段**：并发限流那节的重试范例代码里用了 `error.status` / `error.headers`（TS）和 `error.status_code` / `error.headers`（Python），这是目前材料里唯一能看到的 SDK 错误对象访问方式，但没有一份专门的"SDK 异常类型参考"。

---

内容整理自 https://docs.browserbase.com（抓取于 2026-09-21），未使用真实 API Key 验证，实际调用报错优先信任真实 API。
