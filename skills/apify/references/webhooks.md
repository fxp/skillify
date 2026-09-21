# Webhooks：run 完成时收到通知

> 来自 Apify 官方 OpenAPI 规范和 `docs.apify.com/integrations/webhooks*` 系列文档页（抓取于 2026-09-21）。**没有经过真实 API 调用验证**，标 `⚠ 文档原文，未实测` 处均为文档转录。

目录：
- [两种 webhook：标准 vs ad-hoc](#两种-webhook标准-vs-ad-hoc)
- [标准 webhook：POST /v2/webhooks](#标准-webhookpost-v2webhooks)
- [Ad-hoc webhook：启动 run 时临时挂一个](#ad-hoc-webhook启动-run-时临时挂一个)
- [事件类型](#事件类型)
- [投递、重试、payload 模板](#投递重试payload-模板)

## 两种 webhook：标准 vs ad-hoc

| 类型 | 怎么创建 | 生命周期 | 适合场景 |
|---|---|---|---|
| 标准（standing） | `POST /v2/webhooks`，在 Apify Console 里对某个 Actor/Task 配置，或直接调 API | 持久生效，这个 Actor/Task 之后**每一次** run 触发对应事件都会调用 | "这个 Actor 只要跑完就通知我"这种固定规则 |
| Ad-hoc | 启动 run 时在 URL 上带 `?webhooks=<base64 JSON 数组>` 参数，或 Actor 代码内部调用 `Actor.addWebhook()` | **一次性**，只对这一次 run 生效 | "这次特定的调用完成后通知我"，不想为每次调用都单独去 Console 配置持久规则 |

## 标准 webhook：`POST /v2/webhooks`

**请求体**
| 字段 | 必填 | 说明 |
|---|---|---|
| `eventTypes` | 是 | 事件类型数组，见下方"事件类型" |
| `condition` | 是 | `{actorId}` / `{actorTaskId}` / `{actorRunId}` 三选一，决定这个 webhook 监听哪个范围 |
| `requestUrl` | 是 | 触发时 POST 到这个 URL |
| `idempotencyKey` | 否 | 避免重复创建同一个 webhook——多次用相同 key 调用只有第一次真正创建，后续调用返回已存在的那个 |
| `payloadTemplate` | 否 | 自定义 payload 结构，不传则用默认模板 |
| `headersTemplate` | 否 | 自定义额外请求头 |
| `ignoreSslErrors` | 否 | 目标 URL 证书有问题时是否忽略 |
| `doNotRetry` | 否 | 关闭失败重试 |

**示例**
```bash
curl -X POST "https://api.apify.com/v2/webhooks?token=$APIFY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "eventTypes": ["ACTOR.RUN.SUCCEEDED", "ACTOR.RUN.FAILED"],
    "condition": {"actorId": "apify~website-content-crawler"},
    "requestUrl": "https://example.com/apify-callback"
  }'
```

## Ad-hoc webhook：启动 run 时临时挂一个

在启动 Actor/Task 的 endpoint 上加 `webhooks` query 参数，值是 base64 编码的 JSON 数组：

```python
import base64, json, os, requests

webhooks = [
    {"eventTypes": ["ACTOR.RUN.SUCCEEDED"], "requestUrl": "https://example.com/run-succeeded"},
    {"eventTypes": ["ACTOR.RUN.FAILED"], "requestUrl": "https://example.com/run-failed"},
]
webhooks_b64 = base64.b64encode(json.dumps(webhooks).encode()).decode()

requests.post(
    f"https://api.apify.com/v2/actors/{actor_id}/runs",
    params={"token": os.environ["APIFY_API_TOKEN"], "webhooks": webhooks_b64},
    json={"startUrls": [{"url": "https://apify.com"}]},
)
```

也可以在 Actor 代码内部用 SDK 动态添加（只在自己写 Actor 时用得到，调用方角度一般用不到）：
```python
from apify import Actor
async with Actor:
    await Actor.add_webhook(
        event_types=["ACTOR.RUN.FAILED"],
        request_url="https://example.com/run-failed",
        idempotency_key=os.environ["APIFY_ACTOR_RUN_ID"],  # 用 run ID 做幂等键，防止 Actor 重启时重复创建
    )
```

## 事件类型

**Actor run 事件**：`ACTOR.RUN.CREATED` / `ACTOR.RUN.SUCCEEDED` / `ACTOR.RUN.FAILED` / `ACTOR.RUN.ABORTED` / `ACTOR.RUN.TIMED_OUT` / `ACTOR.RUN.RESURRECTED`

**Actor build 事件**：`ACTOR.BUILD.CREATED` / `ACTOR.BUILD.SUCCEEDED` / `ACTOR.BUILD.FAILED` / `ACTOR.BUILD.ABORTED` / `ACTOR.BUILD.TIMED_OUT`

**⚠ 提醒**：`ACTOR.RUN.SUCCEEDED` 只反映平台层面的终态（见 `references/running-actors.md` 里关于 `status` 字段的说明），不代表 Actor 真正抓到了有意义的数据——webhook 收到"成功"通知后，如果业务上关心结果是否非空，仍然要读一次 dataset/KV store 确认。

## 投递、重试、payload 模板

- **重试**：目标地址返回非 2xx 时会指数退避重试，第 1 次约 1 分钟后，第 2 次约 2 分钟，……直到第 11 次（约 32 小时后）放弃。**要求你的接收端是幂等的**——极少数情况下同一个 webhook 会被投递不止一次。
- **超时**：webhook 的 HTTP 请求本身有 2 分钟超时，接收端应该立刻返回 2xx 确认收到，耗时处理放到异步队列里做，不要在 webhook handler 里同步等长任务。
- **默认 payload**：
  ```json
  {
    "userId": "...",
    "createdAt": "2019-01-09T15:59:56.408Z",
    "eventType": "ACTOR.RUN.SUCCEEDED",
    "eventData": { "actorId": "...", "actorRunId": "..." },
    "resource": { "id": "...", "status": "SUCCEEDED", "...": "完整 Run 对象" }
  }
  ```
  `resource` 字段就是触发时刻 `GET Actor run` 端点会返回的完整对象——想在收到通知后立刻用其中字段（如 `defaultDatasetId`）去读结果，不需要额外查询。
- **自定义 payload 模板**：用 `{{variable}}` 语法（如 `{{resource.id}}`、`{{eventType}}`），可用变量有 `userId`/`createdAt`/`eventType`/`eventData`/`resource`/`globals`（含 `dateISO`/`dateUnix`）。
- **出站 IP 固定**：Apify 从一组固定 IP 发送 webhook 请求，接收端在防火墙后面时需要把这些 IP 加白名单（具体 IP 列表见 `docs.apify.com/integrations/webhooks/actions.md`，会变化，建议直接查文档页取最新列表而不要硬编码进代码）。
