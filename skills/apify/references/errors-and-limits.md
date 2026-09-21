# 错误结构、限流、分页约定速查

> 来自 Apify 官方 OpenAPI 规范的 `info.description`（鉴权/分页/错误/限流章节的官方原文）和 `docs.apify.com/storage.md`（抓取于 2026-09-21）。**没有经过真实 API 调用验证**，标 `⚠ 文档原文，未实测` 处均为文档转录。

## 通用响应信封

成功响应包在 `{"data": {...}}` 里；出错时 `data` 被替换成 `error`：

```json
{
  "error": {
    "type": "record-not-found",
    "message": "Store was not found."
  }
}
```

**例外**（不走这个信封，见对应 reference 文件）：`GET /v2/datasets/{datasetId}/items`（`format=json` 时直接是数组）、`GET /v2/key-value-stores/{storeId}/records/{recordKey}`（直接是原始值）、`run-sync`/`run-sync-get-dataset-items`。

## 常见 HTTP 状态码

| 状态码 | `error.type` 示例 | 含义 |
|---|---|---|
| 400 | `invalid-request` / `invalid-value` / `invalid-record-key` | 请求体或参数不合法 |
| 401 | `token-not-provided` | 需要鉴权但没带 token |
| 402 | — | Payment required：用量超限、余额不足，或 agentic 调用缺少支付凭证 |
| 403 | — | 权限不足（比如访问别人未开放的私有资源） |
| 404 | `record-not-found` | 资源不存在 |
| 405 | `method-not-allowed` | 该端点不支持这个 HTTP 方法 |
| 408 | — | 请求超时（常见于 `run-sync*` 端点等待超过 300 秒） |
| 413 | — | 请求体过大 |
| 415 | — | `Content-Encoding` 不支持 |
| 429 | `rate-limit-exceeded` | 触发限流 |

**⚠ 文档原文**：规范里 `error.type` 定义了一份巨大的错误码枚举（数百个，覆盖账单、审核、GitHub 集成等平台各处场景），大多数和本 skill 覆盖的核心 API 无关，这里只列了最常出现在 Actor 运行/存储场景的几个。遇到没见过的 `error.type`，直接按字面意思判断即可，不需要死记硬背整张表。

## 分页：三套并存的约定，不要混用

| 存储/资源类型 | 分页方式 |
|---|---|
| 大多数 list 端点（Actors、Runs、Webhooks、Store 搜索……） | `offset` + `limit`，响应信封里有 `total`/`offset`/`limit`/`count`/`desc`/`items` |
| Dataset items（`GET /v2/datasets/{datasetId}/items`） | 同样是 `offset`/`limit`，但**响应体本身不带这层信封**（`format=json` 直接是数组） |
| Key-value store 的 key 列表（`GET .../keys`） | **游标式**：`exclusiveStartKey`/`nextExclusiveStartKey`，因为 key 按 UTF-8 二进制序排列，不是插入顺序 |

`desc=1` 让大多数支持 offset 分页的端点倒序返回（从新到旧）——注意 `unwind` 展开后的条目会忽略 `desc` 参数（Dataset items 端点的特例，见 `references/reading-run-output.md`）。

## 限流

- **全局限流**：250,000 请求/分钟。已鉴权请求按用户计数，未鉴权按 IP 计数。
- **单资源默认限流**：60 请求/秒/资源（这里的"资源"指单个 Actor、单个 run、单个 dataset、单个 KV store 等）。
- **更高限流的例外端点**（200 或 400 请求/秒/资源）：
  - Key-value store 记录的 CRUD：**200/秒**
  - `POST /v2/actors/{actorId}/runs`（启动 Actor）、启动 task 的两个 endpoint、`POST .../metamorph`、Dataset 的 `POST .../items`（写入）、Request queue 请求的 CRUD：**400/秒**
- 429 时响应体是标准的 `rate-limit-exceeded` 错误，配合 `X-RateLimit-Limit` 响应头（每个端点各自的限流值会在这个头里体现）。

**重试策略（官方建议的指数退避伪代码）**：
```
DELAY = 500ms
发请求
if 状态码 != 429: 结束
else:
  等待 [DELAY, 2*DELAY] 之间的随机时长
  DELAY *= 2
  重试
```
`apify-client`（JS 和 Python 官方客户端）内建了这套退避逻辑，用官方 client 时不需要自己实现。

## 引用资源的三种写法

| 写法 | 示例 | 何时用 |
|---|---|---|
| 资源 ID | `iKkPcIgVvwmztduf8` | 通用，任何时候都可以 |
| `username~resourcename` | `apify~website-content-crawler` | 引用别人命名过的资源，**必须带 token 且有权限** |
| `~resourcename` | `~my-dataset` | 引用**自己**账号下命名过的资源，同样需要 token |

## Content-Type 与方法覆盖

- 带 JSON body 的请求必须显式带 `Content-Type: application/json` header。
- 只能发 GET 请求的客户端，可以用 `?method=POST` 这类 query 参数覆盖实际 HTTP 方法，让 Apify 把这次 GET 当成 POST 处理（`⚠ 文档原文，未实测`，适用范围未验证）。
