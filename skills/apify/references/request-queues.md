# Request Queue API

> 来自 Apify 官方 OpenAPI 规范和 `docs.apify.com/storage/request-queue.md`（抓取于 2026-09-21）。**没有经过真实 API 调用验证**，标 `⚠ 文档原文，未实测` 处均为文档转录。

## 什么时候需要直接碰这个 API

Request Queue 是 Actor 内部维护"待抓取 URL 队列"的存储——**绝大多数情况下这是 Actor 自己的爬取框架（Crawlee）在内部管理的实现细节，调用方不需要、也不应该直接操作它**。作为"调用别人 Actor"的一方，通常只会用到 Dataset 和 Key-value store（见 `references/reading-run-output.md`）。

真正需要直接调这套 API 的场景只有两类：
1. **给一个支持"从外部 request queue 读取种子 URL"的 Actor 提前灌好一批 URL**（作为该 Actor 的输入之一，具体是否支持、input 里传什么字段引用这个 queue，取决于该 Actor 自己的 input schema）；
2. **自己搭一套爬虫逻辑，但想复用 Apify 的托管队列**（而不用 Crawlee/Apify SDK），直接通过 REST API 管理待处理 URL。

## 核心操作

**创建/复用队列**：`POST /v2/request-queues?name=<可选名字>`——如果传的 `name` 已存在同名队列，直接返回已有队列对象（不会报错或创建重复）。

**队列对象核心字段**：
| 字段 | 说明 |
|---|---|
| `totalRequestCount` | 队列里请求总数 |
| `handledRequestCount` | 已处理数 |
| `pendingRequestCount` | 待处理数 |
| `hadMultipleClients` | 这个队列是否被多个不同客户端访问过——用来判断队列有没有被并发消费（配合下面的并发限制） |

**批量添加请求**：`POST /v2/request-queues/{queueId}/requests/batch`——**单次最多 25 条**，请求体是数组：
```json
[
  { "url": "https://example.com/a", "uniqueKey": "https://example.com/a" },
  { "url": "https://example.com/b", "method": "GET" }
]
```
| 字段 | 必填 | 说明 |
|---|---|---|
| `url` | 是 | 请求 URL |
| `uniqueKey` | 是 | 去重键，相同 `uniqueKey` 的请求被视为同一条，重复添加不会产生重复任务（响应里 `wasAlreadyPresent` 会标出来） |
| `method` | 否 | `GET`/`HEAD`/`POST`/`PUT`/`DELETE`/`CONNECT`/`OPTIONS`/`TRACE`/`PATCH` |
| `payload` | 否 | POST/PUT 请求体 |
| `userData` | 否 | 挂载任意自定义数据，供后续处理时读取 |

响应把结果分成 `processedRequests`（成功入队）和 `unprocessedRequests`（因限流等原因失败，建议指数退避重试）两组。

**其他操作**：`GET .../requests`（列表）、`GET/PUT/DELETE .../requests/{requestId}`（单条操作）、`GET .../head`（读队列头部，即将被处理的下一批）、`.../requests/{requestId}/lock` 与 `.../requests/unlock`（并发消费时的请求锁定机制，防止多个 worker 抢同一条）。

## 注意事项

- **并发限制**：Dataset 和 Key-value store 允许多个 run 同时写入/读取；**Request Queue 同一时刻只允许一个 Actor run 在"处理"它**（多个 run 可以同时往里加新请求，但不能同时消费）——这和另外两种存储的并发模型不一样，别假设三者行为一致。
- 未命名的队列同样受数据保留期约束，超出保留期自动清理。
- `POST .../requests` 和 `.../requests/batch` 这类写操作的限流阈值比默认更高（400 请求/秒/资源，而不是默认的 60），见 `references/errors-and-limits.md`。
