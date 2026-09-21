# Contents：`POST /contents`（+ 已废弃的 `POST /findSimilar`）

> ⚠ 本文件全部内容整理自官方文档（https://docs.exa.ai/contents/quickstart 、`/docs/reference/get-contents`、`/docs/reference/find-similar-links`）与 OpenAPI 规范（`ContentsRequest`/`FindSimilarRequest` schema），**未经真实 API 调用验证**，全部标注 `⚠ 文档原文，未实测`。

目录：[Contents 基本用法](#contents-基本用法) · [内容选项](#内容选项已知-url) · [子页面抓取](#子页面抓取) · [响应与 URL 级失败](#响应与-url-级失败) · [已废弃的 findSimilar](#已废弃的-post-findsimilar) · [注意事项汇总](#注意事项汇总)

## Contents 基本用法

**Endpoint**: `POST https://api.exa.ai/contents`
**用途**: 已经拿到一批 URL（比如自己爬到的、`/search` 返回的、用户输入的），只想批量取正文/高亮/摘要，不需要再做一次检索排序。文档原文建议：如果场景本身就是"网页搜索工具调用"，优先直接在 `/search` 里带 `contents`（10 条结果内不额外计费），而不是先 `/search` 再 `/contents` 两次调用。

**关键参数**（请求体顶层——⚠ 与 `/search` 不同，这里**没有** `contents` 包装层，见下方"注意事项"）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `ids` | array\<string\> | 否* | 1–100 项，通常是 `/search` 结果里的 `results[].id`（多数情况下就是 URL 本身） |
| `urls` | array\<string\> | 否* | 1–100 项，"backwards compatible with the `ids` parameter"——即和 `ids` 是同一回事，任传一个即可 |
| `text` | boolean 或 `{maxCharacters, includeHtmlTags, verbosity, includeSections, excludeSections}` | 否 | 同 `/search` 里 `contents.text` 的选项，但直接在顶层 |
| `highlights` | boolean 或 `{query, verbosity, dynamic, maxCharacters}` | 否 | 同上，直接在顶层；`query` 强烈建议传，用来聚焦抽取重点 |
| `summary` | `{query, schema}` | 否 | 同上；`schema` 可传 JSON Schema 让摘要以匹配该 schema 的 JSON 字符串形式返回，需要自己 parse |
| `extras` | `{links, imageLinks, richImageLinks, richLinks, codeBlocks}` | 否 | 同 `/search` 的 `contents.extras` |
| `maxAgeHours` | integer | 否 | 语义同 `/search` 的 `contents.maxAgeHours`（省略=缓存优先、`0`=总是抓新、`-1`=只用缓存、正整数=新鲜度阈值），见 `references/search.md` |
| `livecrawlTimeout` | integer(ms) | 否 | 抓取超时，配合低 `maxAgeHours` 使用，防止一次抓取拖太久 |
| `snapshotAsOf` | string(date-time/date) | 否 | 同 `/search` 的历史快照，锚定到某个时间点的存量版本 |
| `subpages` | integer | 否 | 从每个起始 URL 跟随链接抓子页面的数量 |
| `subpageTarget` | string 或 array\<string\> | 否 | 优先抓包含这些关键词的子页面路径，如 `["api", "reference"]` |
| `compliance` | `"hipaa"` | 否 | 企业专属，要求只走缓存检索 |

*⚠ 文档未说明：OpenAPI 规范里 `ids`/`urls` 在 schema 层面都不是 `required`（没有顶层 `required` 列表），但两者都不传时行为如何完全没有文档说明——是 400 报错还是返回空结果，是 P1 验证项。

**示例请求**

```bash
curl -s -X POST "https://api.exa.ai/contents" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $EXA_API_KEY" \
  -d '{
    "ids": ["https://exa.ai/blog/dynamic-highlights"],
    "highlights": { "query": "token efficiency and quality results" }
  }'
```

```python
from exa_py import Exa

exa = Exa()
result = exa.get_contents(
    ["https://exa.ai/blog/dynamic-highlights"],
    highlights={"query": "token efficiency and quality results"},
)
print(result.results[0].highlights)
```

**示例响应**（⚠ 文档原文，未实测）

```json
{
  "requestId": "e492118ccdedcba5088bfc4357a8a125",
  "results": [
    {
      "id": "https://exa.ai/blog/dynamic-highlights",
      "title": "Dynamic Highlights",
      "url": "https://exa.ai/blog/dynamic-highlights",
      "highlights": ["With a 12k character budget, ... 40% average token efficiency gain..."]
    }
  ],
  "statuses": [
    { "id": "https://exa.ai/blog/dynamic-highlights", "status": "success", "source": "cached" }
  ],
  "costDollars": { "total": 0.001 }
}
```

## 内容选项（已知 URL）

三个视图（`text`/`highlights`/`summary`）语义和 `/search` 完全一致（参见 `references/search.md` 的"内容选项"一节），**建议三选一**，文档原文"Pick one content view per request. Requesting highlights, text, and summary together returns and bills each view separately."——即可以同传，但会分别计费返回。

`summary.schema` 结构化摘要示例：

```json
{
  "ids": ["https://example.com/company"],
  "summary": {
    "schema": {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "type": "object",
      "properties": {
        "name": { "type": "string" },
        "industry": { "type": "string" },
        "foundedYear": { "type": "number" }
      },
      "required": ["name"]
    }
  }
}
```

⚠ 文档原文：摘要以"匹配 schema 的 JSON 字符串"形式回填在 `summary` 字段，不是自动解析后的对象，调用方要自己 `json.loads`。

## 子页面抓取

`subpages` + `subpageTarget` 让 Exa 从起始 URL 顺着链接抓关联页面：

```json
{
  "ids": ["https://docs.example.com"],
  "subpages": 10,
  "subpageTarget": ["api", "reference", "guides"],
  "highlights": true
}
```

结果出现在每条 `results[].subpages[]` 里，结构和顶层 `results[]` 一致。⚠ 文档未说明：`subpages` 实际能抓到的数量"可能受系统限制"（"The actual number crawled may be limited by system constraints"），没给出具体上限数字；错误码表里另有 `SUBPAGES_LIMIT_EXCEEDED`（400），文档写的请求上限是"每次请求最多 100 个 subpages"，和这里"每个 URL 的 subpages 数量"是不是同一个限制未说明。

## 响应与 URL 级失败

`/contents` 是**批量端点，单个 URL 失败不会让整个请求失败**：整体 HTTP 仍是 200，失败的 URL 体现在 `statuses[]` 里，和 `results[]` 分开：

```json
{
  "results": [],
  "statuses": [
    {
      "id": "https://example.com",
      "status": "error",
      "error": { "tag": "CRAWL_NOT_FOUND", "httpStatusCode": 404 }
    }
  ]
}
```

`statuses[].error.httpStatusCode` 描述的是**目标页面**返回的状态码，不是 `/contents` 这次调用本身的状态码——容易和"这次 API 调用失败了"混淆。常见 `status` tag（⚠ 文档原文，未实测）：

| tag | 含义 |
|---|---|
| `CRAWL_NOT_FOUND` | 目标页面 404 |
| `CRAWL_HTTP_{status}` | 目标页面返回其他 HTTP 错误，如 `CRAWL_HTTP_403` |
| `CRAWL_TIMEOUT` | 抓取超时 |
| `CRAWL_LIVECRAWL_TIMEOUT` | 实时抓取超过了 `livecrawlTimeout` |
| `SOURCE_NOT_AVAILABLE` | 目标禁止访问或源不可用 |
| `UNSUPPORTED_URL` | URL scheme 不支持（非标准 http/https） |
| `CONTENT_NOT_CACHED` | 配合 `snapshotAsOf` 使用：该 URL 在快照窗口内没有存量版本 |

**`/search` 没有 `statuses` 字段**（文档原文明确说明），这个字段是 `/contents`（和带 `snapshotAsOf` 的历史请求）专属的。

## 已废弃的 `POST /findSimilar`

**Endpoint**: `POST https://api.exa.ai/findSimilar` — OpenAPI 规范把它标为 `deprecated: true`，`description` 原文："Find links similar to the provided URL and optionally retrieve their contents. Deprecated: prefer `/search` with a query describing the source."

这是 Exa 早期最出名的端点之一（"给一个 URL，找相似网页"），在大量旧博客/教程/训练语料里出现，但**当前文档明确建议不要再用**，改用 `/search` 并把源页面的主题/风格写进自然语言 `query`。它目前仍然存在于 OpenAPI 规范里（说明还没下线），但已经不在文档站的 `llms.txt` 一级导航索引里出现，只能在 API reference 深处找到。

**关键参数**（如果确实需要用它——比如维护存量代码）：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `url` | string | 是 | 要找相似链接的源页面 |
| `category` | string | 否 | 同 `/search`；`company`/`people` 类目下 `startPublishedDate`/`endPublishedDate`/`excludeDomains` 同样会 400 |
| `excludeSourceDomain` | boolean | 否 | `true` 时排除和源 URL 同域名的结果 |
| `numResults` / `includeDomains` / `excludeDomains` / `startPublishedDate` / `endPublishedDate` / `contents` | — | 语义与 `/search` 对应参数一致（`contents` 同样是包装对象，不是顶层平铺） |
| `startCrawlDate` / `endCrawlDate` | — | 同 `/search`：**已废弃，不生效** |

**迁移建议**（本 skill 给出的推断，非文档原文）：把 `findSimilar({url: X})` 改写成 `search({query: "<描述 X 页面主题/类型的自然语言>", excludeDomains: [<X 的域名>]})` 是文档暗示的方向，但具体应该怎么从一个 URL 自动生成这段 query，文档没有给出转换算法或示例代码，⚠ 文档未说明，需要调用方自己设计（比如先用 `/contents` 取 X 的标题/摘要，再拼进 `/search` 的 query）。

## 注意事项汇总

- **`/contents` 的内容选项在请求体顶层，没有 `/search` 那层 `contents: {...}` 包装**——这是文档专门用 `<Warning>` 强调的一点，两个端点的请求体结构不对称。
- `ids`/`urls` 两个参数功能等价（"backwards compatible"），任传一个即可，各自 1–100 项；同时传两个会怎样未说明。
- `results[].id` 多数情况下就是传入的 URL 本身，不是一个独立生成的不透明 ID。
- URL 级失败不算请求失败，走 `statuses[]`，整体请求仍是 HTTP 200；只有请求本身格式错误（比如 `ids`/`urls` 都缺失、schema 不合法）才会是 400。
- `POST /findSimilar` 已废弃，新代码不要用；遇到存量代码调用它时不要假设它还会长期维护或获得新功能。
