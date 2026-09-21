# 从 run 里读结果：Dataset API + Key-value store API

> 内容来自 Apify 官方 OpenAPI 规范和 `docs.apify.com/storage/*`、`docs.apify.com/api/v2/*` 系列文档页（抓取于 2026-09-21）。**没有经过真实 API 调用验证**，标 `⚠ 文档原文，未实测` 处均为文档转录。

目录：
- [两种存储该用哪个](#两种存储该用哪个)
- [Dataset API：表格型结果](#dataset-api表格型结果)
- [Key-value store API：单值/文件型结果](#key-value-store-api单值文件型结果)
- [命名存储 vs 未命名存储、数据保留期](#命名存储-vs-未命名存储数据保留期)

## 两种存储该用哪个

每次 run 会自动分配三种默认存储（`defaultDatasetId`/`defaultKeyValueStoreId`/`defaultRequestQueueId`，来自启动 run 时的响应），其中和"读结果"相关的两种：

| 存储 | 存什么 | 典型场景 |
|---|---|---|
| **Dataset** | 一串结构相同（或相近）的 JSON 对象，类似表格里的行 | 抓取的商品列表、搜索结果、多条记录——绝大多数 Actor 的主要输出 |
| **Key-value store** | 任意 key → 任意二进制/文本值（图片、HTML、PDF、单个 JSON 对象……），每个 key 独立的 content-type | Actor 的 `INPUT`（每次 run 的输入永远存在这里，key 固定叫 `INPUT`）、单条计算结果（约定俗成的 key 叫 `OUTPUT`）、截图、导出文件 |

**⚠ 容易漏掉的一点**：不少人以为"Actor 的结果"只会在 dataset 里，但很多 Actor 同时会把一份汇总结果、截图或调试文件写进 key-value store 的自定义 key 下（不一定是 `OUTPUT`，具体 key 名由该 Actor 自己定义,要查它的说明或它的 [output schema](https://docs.apify.com/actors/development/actor-definition/output-schema)）。只读 dataset 可能会漏掉这部分结果。

## Dataset API：表格型结果

**Endpoint**: `GET /v2/datasets/{datasetId}/items`

**用途**：按各种格式读出数据集里的条目。

**关键参数**
| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `format` | string | `json` | `json`\|`jsonl`\|`csv`\|`html`\|`xlsx`\|`xml`\|`rss` |
| `offset` | number | `0` | 跳过开头多少条 |
| `limit` | number | **文档原文写"默认不限制条数"** | `⚠ 文档原文，未实测`——没有实测验证服务端是否真的无上限，大数据集务必显式传 `limit` 分页拉取，不要假设一次拿完 |
| `clean` | boolean | `false` | `skipHidden=true` + `skipEmpty=true` 的快捷开关：跳过空条目和以 `#` 开头的隐藏字段 |
| `fields` | string | — | 逗号分隔字段名，只保留这些字段，且按传入顺序排列输出 |
| `outputFields` | string | — | 配合 `fields` 用,按位置重命名字段（如 `fields=headline,url&outputFields=title,link`） |
| `omit` | string | — | 逗号分隔要剔除的字段 |
| `unwind` | string | — | 把某字段展开——数组字段则每个元素拆成独立条目并与父对象合并；对象字段则直接与父对象合并 |
| `flatten` | string | — | 把嵌套对象拍平成 `foo.bar` 形式的 key |
| `desc` | boolean | `false` | 是否倒序（默认按写入顺序返回） |
| `view` | string | — | 使用 dataset schema 里定义好的视图配置 |

**示例请求**
```bash
curl "https://api.apify.com/v2/datasets/$DATASET_ID/items?token=$APIFY_API_TOKEN&format=json&limit=1000&offset=0&clean=true"
```
```python
import os, requests

resp = requests.get(
    f"https://api.apify.com/v2/datasets/{dataset_id}/items",
    params={"token": os.environ["APIFY_API_TOKEN"], "format": "json", "limit": 1000, "offset": 0, "clean": True},
)
items = resp.json()  # 直接是数组，不是 {"data": [...]} 信封
```

**响应格式**：注意这个端点的响应体**不是**标准的 `{"data": {...}}` 信封，`format=json` 时直接就是条目数组（`format=csv`/`xlsx` 等则是对应格式的原始文件内容）。这一点和大部分其他"list"类端点（分页信封里有 `total`/`offset`/`limit`/`count`/`items`）不一样——`⚠ 文档原文，未实测`：具体是否所有格式都完全不带分页元信息（比如 `json` 格式下要不要另外调用 `GET /v2/datasets/{datasetId}` 或 `.../statistics` 才能拿到 `total` 条数）未经验证。

**用 apify-client 分页**（客户端库把这层差异封装掉了，统一暴露 `items`/`total`/`offset`/`count`/`limit`）：
```python
dataset_client = apify_client.dataset(dataset_id)
page = dataset_client.list_items(limit=1000, offset=0)
print(page.total)
for item in page.items:
    ...

# 或者用迭代器自动翻页，不用自己管 offset
for item in dataset_client.iterate_items(limit=1500, offset=100):
    ...
```

**写入数据集**：`POST /v2/datasets/{datasetId}/items`，请求体是单个 JSON 对象或对象数组。**注意事项**：如果该 dataset 定义了 schema 校验，且批量传入的条目里**任意一条**校验失败，**整个请求都会被拒绝**（400），不是"跳过坏的、写入好的"——批量写入前最好自己先过一遍校验，或缩小批次以便定位是哪条出错（错误响应里的 `error.data.invalidItems[].itemPosition` 会给出具体是第几条）。

**其他 endpoint**：`GET /v2/datasets/{datasetId}/statistics`（数据集统计信息）、`HEAD /v2/datasets/{datasetId}/items`（只拿 header，`⚠ 文档未说明` 具体返回什么头）、标准的 `GET/POST/PUT/DELETE /v2/datasets`、`/v2/datasets/{datasetId}` CRUD。

## Key-value store API：单值/文件型结果

**Endpoint**: `GET /v2/key-value-stores/{storeId}/records/{recordKey}`

**用途**：读一个 key 对应的值。

**注意事项**
- 响应体**就是**存进去时的原始内容，`Content-Type` 跟存的时候一致——**不是** JSON 信封，即使存的是 JSON 也不会包一层 `{"data": ...}`。
- 不带 `Accept-Encoding` 头时服务端会自动解压（存的时候如果用了 gzip/br 压缩）。
- 找 Actor 的输出，约定俗成先试 `recordKey=OUTPUT`（很多 Actor 遵循这个惯例，但不是强制规范，具体 key 名以该 Actor 的说明或其 [output schema](https://docs.apify.com/actors/development/actor-definition/output-schema) 为准）。

**示例请求**
```bash
curl "https://api.apify.com/v2/key-value-stores/$STORE_ID/records/OUTPUT?token=$APIFY_API_TOKEN"
```
```python
resp = requests.get(
    f"https://api.apify.com/v2/key-value-stores/{store_id}/records/OUTPUT",
    params={"token": os.environ["APIFY_API_TOKEN"]},
)
# resp.content 是原始字节；resp.headers["content-type"] 告诉你怎么解析
```

**写入**：`PUT /v2/key-value-stores/{storeId}/records/{recordKey}`，请求体就是原始值，`Content-Type` header 决定存储时的 content type；支持 `Content-Encoding: gzip`/`br`/`deflate` 压缩上传节省带宽。

**列出所有 key**：`GET /v2/key-value-stores/{storeId}/keys`——**分页方式和 Dataset 完全不同**，用的是 `exclusiveStartKey` 游标参数，不是 `offset`（因为 key 是按 UTF-8 二进制序排列，不是插入顺序）：
```json
{
  "data": {
    "limit": 1000,
    "isTruncated": true,
    "exclusiveStartKey": "my-key",
    "nextExclusiveStartKey": "some-other-key",
    "items": [ ... ]
  }
}
```
下一页请求把 `nextExclusiveStartKey` 的值传给 `exclusiveStartKey` 参数。

**批量导出**：`GET /v2/key-value-stores/{storeId}/records` 把整个 store 打包成 ZIP 下载（响应 `Content-Type: application/zip`），可用 `prefix`/`collection` 参数过滤子集——一般用不到，多用于人工导出而不是程序化集成。

**其他 endpoint**：`DELETE /v2/key-value-stores/{storeId}/records/{recordKey}`、标准的 `GET/POST/PUT/DELETE /v2/key-value-stores`、`/v2/key-value-stores/{storeId}` CRUD。

## 命名存储 vs 未命名存储、数据保留期

- run 默认分配的存储是**未命名**的，只能靠 ID 引用，**会按数据保留期自动删除**（保留期长短取决于订阅计划；免费版是"最近 10 次 run 保留 4 个月，超出的立即删"）。
- 给存储改名（`PUT /v2/datasets/{datasetId}` 等更新端点传 `name` 字段，或用 `username~store-name` 格式的引用）之后**永久保留**，不受保留期限制。
- **`⚠ 文档原文`**：run 结束后再对它的 dataset/KV store 做读写，依然会产生平台用量计费（不是"跑完就免费"），这一点适用于所有定价模型。
- 并发访问：dataset 和 key-value store 支持多个 run 同时读写；**request queue 只支持多个 run 同时新增数据，同一时刻只能有一个 run 在处理（消费）同一个 request queue**（见 `references/request-queues.md`）。
