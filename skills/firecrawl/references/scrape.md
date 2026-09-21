# Firecrawl `/v2/scrape` — 单页同步抓取参考

`POST /v2/scrape` 是 Firecrawl 的核心端点：给一个 URL，同步返回该页面的内容（markdown / html / 结构化 JSON / 截图 / 音视频 / ...）。它与异步的 `/v2/crawl`、`/v2/batch/scrape`、`/v2/map` 不同——**不返回 job id，直接返回内容**（除非页面很大，走下方的 job 状态查询）。

本文档按"开发者想做什么"组织，而不是按 OpenAPI 字段顺序。每一节标注了内容来源：
- `已用真实 API 验证（2026-09-21）` = 本节内容对着线上 API 实际调用过，附真实响应片段或错误字符串。
- 没有该标注 = 内容转录自 OpenAPI 规范摘要或官方文档页面，**未实测**，字段名/枚举值准确，但行为细节（尤其是报错场景）未经验证。
- `⚠ 文档未说明` = 输入材料里没有回答的问题，本文档不猜测。
- `⚠ 文档自相矛盾` = OpenAPI 摘要与文档页之间，或文档页内部，出现了矛盾陈述，两边都写出来。

## 目录

- [认证与基础信息](#认证与基础信息)
- [基础抓取：获取页面的干净文本](#基础抓取获取页面的干净文本)
- [获取结构化 JSON（⚠ 头号陷阱）](#获取结构化-json⚠-头号陷阱)
- [截图页面](#截图页面)
- [提取媒体：音频 / 视频](#提取媒体音频--视频)
- [针对页面提问：question / highlights](#针对页面提问question--highlights)
- [变更追踪：changeTracking](#变更追踪changetracking)
- [加速重复抓取：maxAge / 缓存](#加速重复抓取maxage--缓存)
- [抓取前与页面交互：actions 与 Interact](#抓取前与页面交互actions-与-interact)
- [大页面 / 异步场景：GET /v2/scrape/{jobId}](#大页面--异步场景get-v2scrapejobid)
- [`/v2/extract` 已弃用，改用 scrape 的 json 格式](#v2extract-已弃用改用-scrape-的-json-格式)
- [积分成本汇总](#积分成本汇总)
- [未验证项清单](#未验证项清单)

---

## 认证与基础信息

**Base URL**: `https://api.firecrawl.dev/v2`
**认证**: `Authorization: Bearer <FIRECRAWL_API_KEY>` 请求头。示例代码一律从环境变量 `FIRECRAWL_API_KEY` 读取，绝不硬编码 key。

`已用真实 API 验证（2026-09-21）`——认证失败场景的真实响应：

| 场景 | HTTP 状态 | 响应体 |
|---|---|---|
| 完全不带 `Authorization` 头 | 403 | `{"success":false,"error":"Unfortunately, your IP address looks suspicious, so Firecrawl can't be used without an API key from here. ... (If you're an agent, you can also use https://firecrawl.dev/auth.md)"}` |
| Key 错误/失效 | 401 | `{"success":false,"error":"Unauthorized: Invalid token"}` |
| URL 格式非法（如 `"not-a-valid-url"`） | 400 | `{"success":false,"code":"BAD_REQUEST","error":"URL must have a valid top-level domain or be an IP address","details":[{"code":"custom","path":["url"],"message":"..."}]}` |

正常 200 响应中**没有观察到**限流相关的响应头（如 `X-RateLimit-*`）——⚠ 文档未说明限流信息通过什么渠道暴露给调用方。

`https://api.firecrawl.dev/v1` 在实测中仍能响应（响应形状与 v2 基本一致），但属于 legacy 版本；官方文档只主动介绍 v2，本参考只覆盖 v2。

两层状态码要分清（文档页 `features_scrape.md` 明确说明，未在本次会话单独复测，但与验证日志的 200 成功响应一致）：
- **API 请求状态**：Firecrawl 调用本身的 HTTP 状态 + 响应体里的 `success` 字段。请求被正常处理即返回 HTTP 200 + `success:true`，**即使目标页面本身返回了非 2xx**。
- **页面状态**（`data.metadata.statusCode`）：目标网站对该请求返回的真实 HTTP 状态（如 200/301/404/403/500）。判断页面是否抓取"干净"看这个字段，不是看外层 HTTP 状态。

---

## 基础抓取：获取页面的干净文本

### 基础抓取（markdown / html / rawHtml / summary）
**Endpoint**: `POST /scrape`
**用途**: 传一个 URL，同步拿到清洗后的正文内容。`formats` 数组默认是 `["markdown"]`；不传 `formats` 就只拿 markdown。这是本文档所有其他能力（JSON 提取、截图、问答……）共用的同一个端点，只是 `formats` 数组里放不同的条目。

**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| url | string(uri) | 是 | — | 要抓取的 URL。也支持直接传 PDF/DOCX 等文档 URL，会自动识别并转换为 markdown（本地文件走 `/parse`，不在本文档范围）。 |
| formats | array | 否 | `['markdown']` | 输出格式列表，字符串或对象混用，见下方"简单格式一览"表和后续各小节。 |
| onlyMainContent | boolean | 否 | `true` | 只返回正文（去掉 nav/footer/header 等），HTML 层面的确定性过滤，不经过 LLM。 |
| onlyCleanContent | boolean | 否 | `false`（Beta） | 在 markdown 上再跑一次 LLM 清洗，去掉 `onlyMainContent` 漏掉的 cookie 条、广告块、面包屑等。零数据保留（ZDR）请求不支持。 |
| includeTags / excludeTags | array\<string\> | 否 | — | CSS 选择器级别的白/黑名单，作用于**原始 DOM**（不是过滤后的结果），所以选择器要按源码 HTML 写。 |

**示例请求**
```bash
curl -s -X POST "https://api.firecrawl.dev/v2/scrape" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "formats": ["markdown"]}'
```
```python
import os, requests

resp = requests.post(
    "https://api.firecrawl.dev/v2/scrape",
    headers={
        "Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}",
        "Content-Type": "application/json",
    },
    json={"url": "https://example.com", "formats": ["markdown"]},
)
resp.raise_for_status()
print(resp.json()["data"]["markdown"])
```

**示例响应**
`已用真实 API 验证（2026-09-21）`——`{"url":"https://example.com"}`（默认 `formats:["markdown"]`）的真实返回：
```json
{
  "success": true,
  "data": {
    "markdown": "# Example Domain\n...",
    "metadata": {
      "title": "Example Domain",
      "language": "en",
      "scrapeId": "...",
      "sourceURL": "https://example.com",
      "url": "https://example.com/",
      "statusCode": 200,
      "contentType": "text/html",
      "proxyUsed": "basic",
      "cacheState": "hit",
      "cachedAt": "...",
      "creditsUsed": 1,
      "concurrencyLimited": false
    }
  }
}
```
一次纯 markdown 抓取消耗 **1 credit**。

**注意事项**
- `已用真实 API 验证（2026-09-21）`：真实响应里的 `data.metadata.scrapeId`、`proxyUsed`、`cacheState`、`cachedAt`、`creditsUsed` 这五个字段**都不在 OpenAPI 摘要的 `data.metadata` 响应 schema 里**（OpenAPI 只列了 title/description/language/sourceURL/url/keywords/ogLocaleAlternate/statusCode/numPages/totalPages/contentType/error/concurrencyLimited/concurrencyQueueDurationMs 以及一个类型为字符串的 `<any other metadata>` 兜底字段，无法覆盖 `creditsUsed` 这种数字字段）。⚠ 文档未说明——如果代码要读这些字段，按未文档化的隐藏字段处理，别指望类型系统能保证它们存在。
- `html`/`rawHtml`/`rawBase64` 的区别：`html` 是清洗过的（去掉 `<script>`/`<style>`/`<noscript>`/`<meta>`/`<head>`，相对链接转绝对路径，`srcset` 取最大图），`rawHtml` 是服务器返回的原始 HTML 不做任何处理，`rawBase64` 是把整个 HTTP 响应体做 Base64 编码后的**裸字符串**（不是 data URI，MIME 类型要看 `metadata.contentType`）。
- `rawBase64` 必须单独使用——和任何其他 format 一起传会被 API 拒绝，响应里也不会有 `markdown`/`html`/`rawHtml` 字段，且只拿到该 URL 本身的文件，不含 CSS/图片等子资源。

### 简单格式一览（无需额外配置，`{"type": "..."}` 即可）

下表覆盖 12 个"传字符串或裸 `{"type":...}` 对象就行、没有额外参数要调"的格式。除本节已详述的 markdown/html/rawHtml/rawBase64/summary 外，也包含 links/images（抓链接/图片）、branding/product/menu（结构化页面元数据）、audio/video（媒体提取，见下方专门小节的补充说明）。全部**未在本次会话实测**，字段名转录自 OpenAPI 摘要 + 对应文档页。

| type | 需要对象形式？ | 额外字段 | 一句话说明 |
|---|---|---|---|
| `markdown` | 否 | — | 清洗后的正文 markdown，默认格式。 |
| `html` | 否 | — | 清洗后的 HTML。 |
| `rawHtml` | 否 | — | 原始未处理 HTML。 |
| `rawBase64` | 否 | — | 整个响应体的 Base64（裸字符串）；**必须单独出现在 `formats` 里**。 |
| `summary` | 否 | — | LLM 生成的页面摘要。 |
| `links` | 否 | — | 页面上所有链接，`data.links: string[]`。 |
| `images` | 否 | — | 页面上所有图片 URL，`data.images`。 |
| `branding` | 否 | — | 品牌视觉系统（色板/字体/排版/组件样式），返回 `data.branding`，结构见文档页示例（颜色、`fontFamilies`、`buttonPrimary` 等）；**确定性提取，不经过 LLM**。 |
| `product` | 否 | — | 商品页结构化字段（标题/品牌/分类/变体/价格/库存/图片），`data.product`；**确定性合并多源数据（JSON-LD > microdata > RDFa > 前端框架内嵌状态 > OpenGraph），不经过 LLM**，非商品页会静默返回无 `product` 字段 + `warning`。⚠ 文档未说明：OpenAPI 摘要的响应 200 schema 里**根本没有列出 `data.product` 字段**（只列了 `data.branding`），这个响应形状只能从 `features_scrape.md` 文档页的示例里转录，规范本身不完整。 |
| `menu` | 否 | — | ⚠ 文档未说明：OpenAPI 摘要里 `menu` 作为 `formats[].type` 的合法枚举值存在，但**没有任何描述文字，响应 200 schema 里也没有对应的 `data.menu` 字段**，两份文档页材料里也没有提到它。除了"这是个合法枚举值"之外，本文档无法给出它返回什么、怎么用。 |
| `audio` | 否 | — | 从支持的视频网站（如 YouTube）提取音频，返回一个 1 小时后过期的签名 GCS URL，`data.audio`。 |
| `video` | 否 | — | 同上，提取最佳质量视频，`data.video`。 |

json / screenshot / question / highlights / changeTracking 这五个格式需要真正的对象形式配置，各自有独立小节，见下方。

---

## 获取结构化 JSON（⚠ 头号陷阱）

> **在写任何 `formats: ["json"]` 之前，先读这一段。**
>
> `已用真实 API 验证（2026-09-21）`：把 `"json"` 当**裸字符串**传进 `formats`（就像 `"markdown"`/`"html"`/`"links"` 那样传）——这是最自然的第一直觉，因为其他格式确实都能这么传——**会静默失败**。
>
> 请求：`formats: ["markdown", "json"]`（不带 `schema`）
> 响应：**HTTP 200，`success:true`**，但 `data.json` 是 **`null`**，唯一的信号藏在一个容易被忽略的 `data.warning` 字段里：
> ```
> "warning":"JSON extraction failed: Invalid schema for response_format 'response': In context=(), 'required' is required to be supplied and to be an array including every key in properties. Extra required key 'extractedData' supplied."
> ```
> 而且这次失败的调用照样扣了 **5 credits**（1 基础 + 4 JSON 附加），提取失败也不退款。
>
> 正确写法——`json` 必须是对象形式，带 `schema`（或至少带 `prompt`）：
> ```json
> {"type": "json", "schema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}}
> ```
> 用这个格式重新请求，`data.json` 正确返回 `{"title": "Example Domain"}`，无 warning，同样扣 5 credits。
>
> **这是一个静默失败陷阱，不是文档里写明的"注意事项"**：`success` 两种情况下都是 `true`，只有 `data.json === null` 加上一条藏在 `data.warning` 里的字符串能区分成功和失败。`formats` 数组里除了 `json` 和 `changeTracking`，其余条目全都能接受裸字符串；只有这两个真正要求对象形式 + 必填内容。任何习惯了裸字符串写法的 Agent，第一次几乎必然会先试 `formats: ["json"]`，然后被这个陷阱坑到——**必须在代码里显式检查 `data.json !== null`，不能只看 `success`**。

### JSON 结构化提取
**Endpoint**: `POST /scrape`（`formats` 内含 `{"type": "json", ...}`）
**用途**: 用 LLM 按 JSON Schema 和/或自然语言 prompt 从页面提取结构化数据。与 `product` 格式的区别：`product` 是确定性提取、专为商品页设计、不需要 schema；`json` 需要你定义 schema/prompt，适合自定义字段或非商品页。

**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| type | string | 是 | — | 固定为 `"json"`。 |
| schema | object | 否（但强烈建议） | — | 符合 [JSON Schema](https://json-schema.org/) 的结构定义。不传 schema 时可以只传 `prompt`，让 LLM 自己决定结构。 |
| prompt | string | 否 | — | 引导提取的自然语言提示，最多 10,000 字符。可以和 `schema` 一起用，也可以单独用。 |
| checkPromptInjection | boolean | 否 | `false` | 开启后会在提取前扫描页面内容是否有 prompt injection；检测到会以 HTTP 403 + `SCRAPE_PROMPT_INJECTION_DETECTED` 失败，扫描本身额外加 4 credits。 |

**示例请求**
```bash
curl -X POST https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "formats": [
      {"type": "json", "schema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}}
    ]
  }'
```
```python
import os, requests

resp = requests.post(
    "https://api.firecrawl.dev/v2/scrape",
    headers={
        "Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}",
        "Content-Type": "application/json",
    },
    json={
        "url": "https://example.com",
        "formats": [{
            "type": "json",
            "schema": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
        }],
    },
)
data = resp.json()["data"]
assert data["json"] is not None, data.get("warning")  # 不要只检查 success
print(data["json"])
```

**示例响应**
`已用真实 API 验证（2026-09-21）`——正确的对象形式（带 `schema`）对 `https://example.com` 的真实返回：
```json
{"success": true, "data": {"json": {"title": "Example Domain"}, "metadata": {"...": "..."}}}
```
`已用真实 API 验证（2026-09-21）`——**错误**的裸字符串形式（`formats: ["markdown", "json"]`，无 schema）的真实返回，作为反面对照：
```json
{"success": true, "data": {"json": null, "warning": "JSON extraction failed: Invalid schema for response_format 'response': In context=(), 'required' is required to be supplied and to be an array including every key in properties. Extra required key 'extractedData' supplied."}}
```

**注意事项**
- 见本节开头的头号陷阱说明——`success:true` 不代表提取成功，必须检查 `data.json !== null`。
- 成本：`已用真实 API 验证（2026-09-21）`，无论成功还是失败都扣 **5 credits**（文档页 `features_scrape.md` 给出的口径是"1 基础 + 4 JSON 附加"，与实测一致）。
- `checkPromptInjection: true` 额外 +4 credits（仅在扫描实际运行时收取，来自 OpenAPI 描述，未实测）。
- 官方文档明确把 `/v2/extract` 标为已弃用，运行时会引导你改用 `/v2/scrape` 的 `json` 格式——细节见文末 [`/v2/extract` 已弃用](#v2extract-已弃用改用-scrape-的-json-格式) 一节，那里有另一层文档互相矛盾的真实验证记录。

---

## 截图页面

### 截图（screenshot）
**Endpoint**: `POST /scrape`（`formats` 内含 `{"type": "screenshot", ...}`）
**用途**: 对页面截图，返回一个可下载的 URL。和 actions 数组里的 `screenshot` 动作不同——这是抓取当前渲染出的页面（抓取时机由 Firecrawl 决定），actions 里的 screenshot 是你在一串交互动作执行到某一步时手动截。

**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| type | string | 是 | — | 固定为 `"screenshot"`。 |
| fullPage | boolean | 否 | `false` | 截整页（忽略 viewport 高度）还是只截当前视口。 |
| quality | integer | 否 | — | 1–100，100 为最高质量。 |
| viewport | object `{width, height}` | 否 | — | 视口尺寸，最大分辨率 7680×4320（文档页 `advanced-scraping-guide.md`，未实测）。 |

**示例请求**
```bash
curl -X POST https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "formats": [{"type": "screenshot", "fullPage": true, "quality": 80}]
  }'
```
```python
import os, requests

resp = requests.post(
    "https://api.firecrawl.dev/v2/scrape",
    headers={
        "Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}",
        "Content-Type": "application/json",
    },
    json={
        "url": "https://example.com",
        "formats": [{"type": "screenshot", "fullPage": True, "quality": 80}],
    },
)
print(resp.json()["data"]["screenshot"])  # 24 小时后过期的 URL
```

**示例响应**
文档/规范转录，未实测：
```json
{"success": true, "data": {"screenshot": "https://.../screenshot-....png", "metadata": {"...": "..."}}}
```

**注意事项**
- 每次请求最多一个 `screenshot` format（文档页明确说明，未实测）。
- 截图 URL 24 小时后过期，过期后无法再下载（OpenAPI 摘要明确写明）。
- **与 ZDR 互斥**：`zeroDataRetention: true` 时若同时请求 `screenshot` 格式会报错——因为截图需要上传到持久化存储，与零数据保留承诺冲突（`features_scrape.md` 文档页，未实测）。
- **会绕开缓存**：自定义 `viewport` 或 `quality` 会让这次请求跳过缓存（`features_fast-scraping.md` 文档页明确列出，未实测）——如果你的截图请求总是很慢，这可能是原因,而不是 API 本身慢。

---

## 提取媒体：音频 / 视频

`audio` 和 `video` 两个格式都很小众，用法和"简单格式一览"表里其他条目一样——裸字符串 `"audio"` / `"video"` 即可，无需额外参数。仅支持部分视频网站（文档举例 YouTube）。

**成本**（文档页 `features_scrape.md`，未实测）：音频/视频提取各收 **5 credits/页**（1 基础 + 4 附加），返回的签名 GCS URL **1 小时后过期**——比截图的 24 小时短得多，下载要趁早。

```bash
curl -s -X POST "https://api.firecrawl.dev/v2/scrape" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=XXXXXXXXXXX", "formats": ["audio"]}'
```
```python
import os, requests

resp = requests.post(
    "https://api.firecrawl.dev/v2/scrape",
    headers={"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"},
    json={"url": "https://www.youtube.com/watch?v=XXXXXXXXXXX", "formats": ["audio"]},
)
print(resp.json()["data"]["audio"])
```

⚠ 文档未说明：自托管 Firecrawl 时如果没配置 `PRODUCT_EXTRACTION_SERVICE_URL`（对应 `product` 格式的服务），会静默返回 warning + 无数据；音频/视频格式文档提到"用同样的模式"处理服务不可用，但没写音频/视频对应的具体环境变量名。Firecrawl Cloud（即 `api.firecrawl.dev`）本身不受影响。

---

## 针对页面提问：question / highlights

这两个格式都是"一次调用里顺带问一句话"，常和 `markdown` 一起传，一次拿到正文 + 答案。**均未在本次会话实测**，转录自 `features_scrape.md`。

### question 格式
**Endpoint**: `POST /scrape`（`formats` 内含 `{"type": "question", "question": "..."}`）
**用途**: 对页面提一个自然语言问题，答案写入响应的 `data.answer` 字段。和 `json` 格式的区别：`question` 只返回一段自然语言文本，不是结构化对象；不需要 schema。

**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| type | string | 是 | — | 固定为 `"question"`。 |
| question | string | 是 | — | 要问的问题，最多 10,000 字符。 |

**示例请求**
```bash
curl -s -X POST "https://api.firecrawl.dev/v2/scrape" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://firecrawl.dev", "formats": [{"type": "question", "question": "What is Firecrawl?"}]}'
```
```python
import os, requests

resp = requests.post(
    "https://api.firecrawl.dev/v2/scrape",
    headers={"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"},
    json={
        "url": "https://firecrawl.dev",
        "formats": [{"type": "question", "question": "What is Firecrawl?"}],
    },
)
print(resp.json()["data"]["answer"])
```

**示例响应**
文档/规范转录，未实测：
```json
{"success": true, "data": {"answer": "Firecrawl turns web pages into clean, LLM-ready markdown and structured data.", "metadata": {"...": "..."}}}
```

**注意事项**
- 成本 5 credits/页（1 基础 + 4 LLM 调用附加，文档页口径，未实测）。
- 也可以在 `/search` 的 `scrapeOptions` 里用（未在本文档范围内）。
- ⚠ 文档自相矛盾：`features_scrape.md` 顶部"Scrape Formats"清单里写的是 **"Query (`query`, with `prompt` and optional `mode`)"**，但 OpenAPI 摘要的 `formats[].type` 枚举值里**根本没有 `query` 这个类型**——只有 `question`（字段名 `question`）和 `highlights`（字段名 `query`，见下节）。同一篇文档页往下翻到专门小节时，用的也是正确的 `question`/`type:"question"` 写法，和顶部清单自相矛盾。**以 OpenAPI 摘要和本节详细描述为准：是 `question`，不是 `query`。**

### highlights 格式
**Endpoint**: `POST /scrape`（`formats` 内含 `{"type": "highlights", "query": "..."}`）
**用途**: 从页面里挑出与某个查询相关的原文片段，结果写入 `data.highlights`。和 `question` 的区别：`highlights` 返回的是页面原文摘录，不是 LLM 生成的回答句子。

**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| type | string | 是 | — | 固定为 `"highlights"`。 |
| query | string | 是 | — | 文本选择查询，最多 10,000 字符。**注意字段名是 `query` 不是 `question`**——和上面 `question` 格式的字段名正好相反，容易记混。 |

**示例请求**
```bash
curl -s -X POST "https://api.firecrawl.dev/v2/scrape" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://firecrawl.dev", "formats": [{"type": "highlights", "query": "What is Firecrawl?"}]}'
```
```python
import os, requests

resp = requests.post(
    "https://api.firecrawl.dev/v2/scrape",
    headers={"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"},
    json={
        "url": "https://firecrawl.dev",
        "formats": [{"type": "highlights", "query": "What is Firecrawl?"}],
    },
)
print(resp.json()["data"]["highlights"])
```

**示例响应**
文档/规范转录，未实测：
```json
{"success": true, "data": {"highlights": "Firecrawl is the web data API for AI. ...", "metadata": {"...": "..."}}}
```

**注意事项**
- 成本同 `question`：5 credits/页（文档页口径，未实测）。
- 也可以在 `/search` 的 `scrapeOptions` 里用（未在本文档范围内）。

---

## 变更追踪：changeTracking

**Endpoint**: `POST /scrape`（`formats` 内必须同时含 `"markdown"` 和 `{"type": "changeTracking", ...}`）
**用途**: 把这次抓取的内容和你团队上一次抓取同一 URL 的快照比较，判断页面是新出现、未变、已变还是已删除。和 `/v2/monitor`（定时轮询 + webhook 通知，不在本文档范围）的区别：`changeTracking` 只是单次抓取时的 diff 原语，调度要你自己做（cron/云调度器）。**未在本次会话实测**，转录自 `features_change-tracking.md`。

**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| type | string | 是 | — | 固定为 `"changeTracking"`。 |
| modes | array\<string\> | 否 | `[]` | `"git-diff"`（逐行 diff）和/或 `"json"`（字段级比较，需要 `schema`）。 |
| schema | object | `json` 模式下必填 | — | 定义要比较哪些字段。 |
| prompt | string | 否 | — | 引导 `json` 模式提取的自定义提示。 |
| tag | string | 否 | `null` | 独立的追踪历史分支标识，同一 URL 不同 tag 的比较历史互不影响。 |

**示例请求**
```bash
curl -s -X POST "https://api.firecrawl.dev/v2/scrape" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/pricing",
    "formats": ["markdown", {"type": "changeTracking", "modes": ["git-diff"]}]
  }'
```
```python
import os, requests

resp = requests.post(
    "https://api.firecrawl.dev/v2/scrape",
    headers={"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"},
    json={
        "url": "https://example.com/pricing",
        "formats": ["markdown", {"type": "changeTracking", "modes": ["git-diff"]}],
    },
)
ct = resp.json()["data"]["changeTracking"]
if ct["changeStatus"] == "changed":
    print(ct["diff"]["text"])
```

**示例响应**
文档/规范转录，未实测（第一次抓取该 URL 的情形）：
```json
{
  "success": true,
  "data": {
    "markdown": "# Pricing\n\nStarter: $9/mo...",
    "changeTracking": {"previousScrapeAt": null, "changeStatus": "new", "visibility": "visible"}
  }
}
```

**注意事项**
- **`markdown` 必须同时在 `formats` 里**，否则比较无法进行（文档页原文警告）。
- **强制绕过缓存**：带 `changeTracking` 的请求会跳过索引缓存，`maxAge` 参数被忽略（文档页明确说明，与"加速重复抓取"一节互斥）。
- 成本：基础追踪和 `git-diff` 模式不额外收费（走普通抓取积分）；`json` 模式收 **5 credits/页**。
- `changeStatus` 取值 `"new"`/`"same"`/`"changed"`/`"removed"`；`visibility` 取值 `"visible"`/`"hidden"`（URL 通过历史记录发现但已不再被任何链接指向）。
- 比较基准是"你团队"对同一 URL 的上一次抓取——`includeTags`/`excludeTags`/`onlyMainContent` 在不同次抓取之间不一致会导致比较结果不可靠。
- 数据库查找上一次快照超时时，`changeTracking` 对象可能整个缺失——处理响应时要考虑这个字段可能不存在，光判断 `success` 不够。

---

## 加速重复抓取：maxAge / 缓存

**Endpoint**: `POST /scrape`（请求体顶层的 `maxAge` / `minAge` / `storeInCache` 参数）
**用途**: Firecrawl 默认会给页面加缓存，重复抓取同一 URL 时可以命中缓存直接返回，跳过完整抓取流程。和 `changeTracking`（永远绕开缓存）刚好相反——这里是主动利用缓存换取速度。

**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| maxAge | integer(ms) | 否 | `172800000`（2 天） | 缓存副本若比这个值新，直接返回缓存；否则重新抓取并更新缓存。设为 `0` 则每次都强制新鲜抓取（更慢，也更容易失败）。 |
| minAge | integer(ms) | 否 | — | 设置后**只查缓存，绝不触发新抓取**。有匹配缓存立即返回；没有则返回 404，错误码 `SCRAPE_NO_CACHED_DATA`。设为 `1` 表示接受任意年龄的缓存。 |
| storeInCache | boolean | 否 | `true` | 设为 `false` 则这次抓取结果不写入缓存（有数据保护顾虑时用）。 |

**示例请求**
```bash
# 用 10 分钟内的缓存，没有就抓新的
curl -s -X POST "https://api.firecrawl.dev/v2/scrape" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "maxAge": 600000, "formats": ["markdown"]}'
```
```python
import os, requests

resp = requests.post(
    "https://api.firecrawl.dev/v2/scrape",
    headers={"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"},
    json={"url": "https://example.com", "maxAge": 600000, "formats": ["markdown"]},
)
print(resp.json()["data"]["metadata"]["cacheState"])  # "hit" 或 "miss"
```

**示例响应**
`已用真实 API 验证（2026-09-21）`——见"基础抓取"一节的真实响应，`data.metadata.cacheState` 在重复抓取同一 URL 时确认返回 `"hit"`，且该字段是**主动出现的，不需要专门请求**（普通抓取的 metadata 里默认就带）。⚠ 文档未说明这个字段本身不在 OpenAPI 响应 schema 里（见"基础抓取"一节的详细说明）。

**注意事项**
- 命中缓存的结果**照样收 1 credit/页**——缓存省的是时间，不是积分（文档页明确说明，未单独实测积分数字，但与验证日志里普通抓取"1 credit"一致）。
- 以下情况会**自动绕开缓存**，即使你设了非零 `maxAge`（`features_fast-scraping.md` 文档页，未实测）：自定义 `headers`、`actions`（浏览器自动化步骤）、浏览器 `profile`、`changeTracking` 格式、自定义 `screenshot` 的 viewport/quality。
- 缓存命中要求这些参数在两次请求间**完全一致**：`url`、`mobile`、`location`、`waitFor`、`blockAds`、`screenshot`（开关和 fullPage）、enhanced 代理模式（文档页明确列出，未实测）。
- `maxAge` 控制的是"能不能返回缓存"，不代表内容本身是最新状态——需要绝对新鲜数据时用 `maxAge: 0`，然后自己检查返回内容和跳转/来源特定的状态信号。

---

## 抓取前与页面交互：actions 与 Interact

**⚠ 本节内容全部转录自文档，本次会话未对真实浏览器交互效果做过验证**（验证日志明确把 `actions` 列入"本轮未验证/超出范围"）。适合"需要点一下按钮/填个表单/等页面加载完再抓"这类场景；如果只是想跳过缓存拿最新数据，用上面的 `maxAge: 0` 就够了，不需要 actions。

### actions（同步内联，随 `/scrape` 一次性执行）
**Endpoint**: `POST /scrape`（顶层 `actions` 数组）
**用途**: 在正式抓取内容之前，按顺序在页面上执行一串浏览器动作（等待/点击/输入/滚动/截图/执行 JS/生成 PDF）。所有动作在同一次请求里**顺序执行**，执行完才抓取最终内容。

**关键参数**（各动作类型摘要，完整字段见 OpenAPI 摘要或 `advanced-scraping-guide.md`）
| 动作 type | 关键字段 | 说明 |
|---|---|---|
| `wait` | `milliseconds` 或 `selector`（二选一） | 固定延时，或等到某元素出现（等选择器时 30 秒超时）。 |
| `click` | `selector`, `all?` | 点击元素；`all:true` 点击所有匹配项。 |
| `write` | `text` | 往已聚焦的输入框打字——**必须先用 `click` 聚焦目标元素**。 |
| `press` | `key` | 按键盘键（如 `"Enter"`）。 |
| `scroll` | `direction?`, `selector?` | 滚动页面或指定元素。 |
| `screenshot` | `fullPage?`, `quality?`, `viewport?` | 截图，存入 `data.actions.screenshots`。 |
| `scrape` | — | 在动作序列执行到这一步时抓一次当前 HTML，存入 `data.actions.scrapes`。 |
| `executeJavascript` | `script` | 执行 JS，返回值存入 `data.actions.javascriptReturns`。 |
| `pdf` | `format?`, `landscape?`, `scale?` | 生成当前页 PDF，存入 `data.actions.pdfs`。 |

**示例请求**
```bash
curl -X POST https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/login",
    "formats": ["markdown"],
    "actions": [
      {"type": "click", "selector": "#username"},
      {"type": "write", "text": "demo"},
      {"type": "click", "selector": "button[type=\"submit\"]"},
      {"type": "wait", "milliseconds": 1500}
    ]
  }'
```
```python
import os, requests

resp = requests.post(
    "https://api.firecrawl.dev/v2/scrape",
    headers={"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"},
    json={
        "url": "https://example.com/login",
        "formats": ["markdown"],
        "actions": [
            {"type": "click", "selector": "#username"},
            {"type": "write", "text": "demo"},
            {"type": "click", "selector": 'button[type="submit"]'},
            {"type": "wait", "milliseconds": 1500},
        ],
    },
)
print(resp.json()["data"]["markdown"])
```

**示例响应**
文档/规范转录，未实测：
```json
{"success": true, "data": {"markdown": "...", "actions": {"screenshots": [], "scrapes": [], "javascriptReturns": [], "pdfs": []}}}
```

**注意事项**
- 最多 50 个动作/请求；所有 `wait`（含 `waitFor` 顶层参数）的累计等待时间不能超过 60 秒（文档页，未实测）。
- **不支持 PDF**：如果 URL 解析出来是 PDF，带 actions 的请求会直接失败（文档页，未实测）。
- 官方现在**更推荐 Interact**（见下方）而不是继续扩展 actions 数组，理由是 actions 只能"一次性顺序执行完再抓取"，Interact 是有状态的、可以跨多次调用保持会话。

### Interact（有状态浏览器会话，跨调用保持）
**Endpoint**: `POST /scrape/{jobId}/interact`（同一 jobId 上可继续用 `DELETE /scrape/{jobId}/interact` 关闭会话）
**用途**: 针对一次 `/scrape` 产生的浏览器会话，反复执行代码/自然语言指令，会话在调用之间保持存活（cookies、页面状态都还在）。和 `actions` 的本质区别：`actions` 是"这次抓取前先做完这些步骤"，`interact` 是"抓取完之后这个浏览器还活着，你可以再操作它"。⚠ 文档未说明：如何先拿到一个可用于 `/interact` 的 `jobId`——本文档拿到的材料里没有说明 `/scrape` 普通同步响应里是否带 `jobId`，还是需要专门用某种异步模式发起抓取才会有。

**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| jobId | string(uuid)，路径参数 | 是 | — | 抓取 job 的 ID。 |
| code | string | 是 | — | 在会话绑定的浏览器沙箱里执行的代码。 |
| language | string | 否 | `"node"` | `python` / `node` / `bash`（`bash` 用于 agent-browser CLI 命令）。 |
| timeout | integer(秒) | 否 | `30` | 执行超时。 |
| origin | string | 否 | — | 用于执行遥测的来源标签。 |

**示例请求**
```bash
curl -X POST "https://api.firecrawl.dev/v2/scrape/$JOB_ID/interact" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"code": "await page.click(\"#export\")", "language": "node"}'
```
```python
import os, requests

job_id = "REPLACE_ME"
resp = requests.post(
    f"https://api.firecrawl.dev/v2/scrape/{job_id}/interact",
    headers={"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"},
    json={"code": 'await page.click("#export")', "language": "node"},
)
print(resp.json())
```

**示例响应**
文档/规范转录，未实测：
```json
{"success": true, "cdpUrl": "wss://...", "liveViewUrl": "https://...", "stdout": "", "stderr": "", "exitCode": 0}
```

**注意事项**
- 支持 Playwright/Puppeteer 风格代码，也支持传自然语言 prompt 让内置 agent 操作页面（响应里的 `output` 字段是"AI agent 的最终回复，仅在用 prompt 时出现"——⚠ 文档未说明 prompt 具体通过哪个请求字段传入，OpenAPI 摘要里 `/interact` 的请求体只列了 `code`/`language`/`timeout`/`origin`，没有单独的 `prompt` 字段）。
- 失败场景很多，按 OpenAPI 摘要列出的状态码：400 无效 job ID、402 欠费、403 禁止、404 job 不存在、409 replay 上下文不可用/会话初始化失败、410 浏览器会话已销毁、429 活跃浏览器会话过多、502 与浏览器服务通信失败。这些错误码全部**未实测**，只是转录。
- 也支持 `profile`（顶层 `/scrape` 参数）在多次 scrape/interact 会话之间共享 cookies/localStorage——`profile.name` 相同即共享状态，`profile.saveChanges` 控制是否把变更写回 profile。

---

## 大页面 / 异步场景：GET /v2/scrape/{jobId}

**Endpoint**: `GET /scrape/{jobId}`
**用途**: 查询一个抓取 job 的状态/结果。`/v2/scrape` 通常是同步返回内容的，但 OpenAPI 摘要里确实存在这个独立的状态查询端点——⚠ 文档未说明它在什么条件下才需要用（比如页面特别大、或者显式要求异步模式时），两份文档页材料里都没有解释触发异步路径的方法，只有 OpenAPI 规范列出了这个端点本身存在。

**关键参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| jobId | string(uuid)，路径参数 | 是 | 抓取 job 的 ID。 |

**示例请求**
```bash
curl -s "https://api.firecrawl.dev/v2/scrape/$JOB_ID" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY"
```
```python
import os, requests

job_id = "REPLACE_ME"
resp = requests.get(
    f"https://api.firecrawl.dev/v2/scrape/{job_id}",
    headers={"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"},
)
print(resp.json())
```

**示例响应**
文档/规范转录，未实测——响应 `data` 对象的字段形状与普通 `/scrape` 响应完全一致（markdown/html/json/screenshot/metadata/warning/changeTracking/branding 等，取决于当初请求的 `formats`）：
```json
{"success": true, "data": {"markdown": "...", "metadata": {"...": "..."}}}
```

**注意事项**
- 响应 schema 与同步 `/scrape` 响应共享同一套字段定义，说明它服务的是"同一个抓取请求的结果"，只是查询方式换成了轮询而不是等待同步返回。
- 出错时返回 402（欠费）或 429（限流）或 500，字段形状与同步端点一致（OpenAPI 摘要，未实测）。

---

## `/v2/extract` 已弃用，改用 scrape 的 json 格式

这不是 `/v2/scrape` 本身的端点，但直接关系到"要不要用 json 格式做结构化提取"的决策，放在这里作为背景说明。

`已用真实 API 验证（2026-09-21）`：调用 `POST /v2/extract` 和 `GET /v2/extract/{id}` **两个调用都成功执行并返回了正确数据**，但都在响应里带上了弃用信号：
```json
{"success": true, "id": "...", "urlTrace": [], "warnings": ["/v2/extract is deprecated. Use /v2/scrape with formats including a 'json' format object."], "replacement": "/v2/scrape"}
```
```json
{"success": true, "data": {"title": "Example Domain"}, "status": "completed", "tokensUsed": 306, "creditsUsed": 21, "warnings": ["/v2/extract/:jobId is deprecated. Use /v2/scrape with formats including a 'json' format object."], "replacement": "/v2/scrape"}
```
**弃用只通过 `warnings` 数组 + `replacement` 字段体现，从来不是错误状态**——对 1 个 URL、1 个字段的提取收了 **21 credits**，比等价的 `/scrape` json 格式（5 credits）贵了约 4 倍。

⚠ 文档自相矛盾：这与 `docs.firecrawl.dev/developer-guides/usage-guides/choosing-the-data-extractor.md` 文档页正面冲突——那篇文档把 `/extract` 当作一等端点介绍，并建议迁移到 **`/agent`**（不是 `/scrape`）："We recommend migrating to `/agent`—it's faster, more reliable, doesn't require URLs, and handles all `/extract` use cases plus more."。两个权威来源（运行时警告 vs. 文档页）给出了两个不同的"该迁到哪"答案。`/agent` 是自主多步骤端点，成本模型不同，本次未验证，不在本文档范围内。本文档的立场：对于"已知 URL 的结构化提取"这类场景，按线上 API 自己给出的运行时提示，推荐用 `/scrape` 的 `json` 格式作为默认选择，同时把文档页的另一种建议原样列出，不擅自替你选边。

---

## 积分成本汇总

`已用真实 API 验证（2026-09-21）`部分 + 文档页口径，两者并列标注。套餐：1000 credits/周期，本次会话测试后剩余约 511 credits（查询方式：`GET /v2/team/credit-usage`，响应形如 `{"success":true,"data":{"remainingCredits":N,"planCredits":N,...}}`）。**这不是一张官方发布的定价表，而是本次实测观察到的真实扣费**：

| 操作 | 成本 | 来源 |
|---|---|---|
| 纯 markdown 抓取 | 1 credit | `已用真实 API 验证（2026-09-21）` |
| 带 `json` 格式的抓取（成功或失败都一样） | 5 credits | `已用真实 API 验证（2026-09-21）`；与文档页"1 基础 + 4 附加"口径一致 |
| 2 页迷你 crawl | 约 1 credit/页 | `已用真实 API 验证（2026-09-21）` |
| `/v2/extract`（1 URL，1 字段） | 21 credits | `已用真实 API 验证（2026-09-21）`——约为等价 `/scrape` json 格式的 4 倍 |
| `question` / `highlights` 格式 | 5 credits/页（1+4） | 文档页口径，未实测 |
| `audio` / `video` 格式 | 5 credits/页（1+4） | 文档页口径，未实测 |
| PII 脱敏（`redactPII`） | +4 credits/页 | 文档页口径，未实测 |
| PDF 解析（`parsers` 含 pdf，默认） | 1 credit/页 | 文档页 + OpenAPI 一致，未实测；`parsers: []` 时整份 PDF 按 base64 原样返回，flat rate 1 credit |
| `changeTracking` 基础追踪 / `git-diff` 模式 | 不额外收费 | 文档页口径，未实测 |
| `changeTracking` `json` 模式 | 5 credits/页 | 文档页口径，未实测 |
| `checkPromptInjection: true`（json 格式内） | +4 credits（仅扫描实际运行时） | OpenAPI 摘要，未实测 |
| `threatProtection.mode: "normal"` | +2 credits/被扫描的 URL | OpenAPI 摘要，未实测（企业功能） |
| `lockdown: true` | 命中 5 credits，未命中 1 credit | OpenAPI 摘要，未实测 |
| `zeroDataRetention: true` | +1 credit/页 | 文档页，未实测 |
| `branding` / `product` / `menu` / `links` / `images` / `summary` 格式单独成本 | ⚠ 文档未说明 | 两份文档页只列出了上面这些"附加"成本，没有单独提到这几个格式是否收取超出基础 1 credit 的额外费用——按未明确加价处理，但不保证。 |

---

## 未验证项清单

以下内容只来自 OpenAPI 摘要或文档页转录,**没有在本次会话对线上 API 验证过**,后续如果拿到更多测试额度,建议优先验证:

1. `screenshot` / `question` / `highlights` / `changeTracking` / `audio` / `video` 五个格式的真实响应形状和真实报错场景（目前全部是规范转录）。
2. `actions` 数组的真实交互效果——验证日志明确指出这需要一个"有真实可交互状态的页面"才能算真测试,单纯发请求验证不了实际问题。
3. `/scrape/{jobId}/interact` 的完整生命周期：如何先拿到 `jobId`（同步 `/scrape` 响应里到底带不带这个字段）、`code`/`language` 的实际执行效果、各种 4xx/5xx 错误码的真实触发条件。
4. `GET /v2/scrape/{jobId}`：什么条件下 `/scrape` 会真正走异步路径而不是同步返回,目前完全没有材料说明触发条件。
5. `menu` 格式的响应形状——OpenAPI 摘要里只有类型名,没有任何字段描述,两份文档页都没提到。
6. `branding`/`product`/`menu`/`links`/`images`/`summary` 这些"简单格式"各自的真实积分成本。
7. `advanced-scraping-guide.md` 提到的 `attributes` 格式（`selectors: [{selector, attribute}]`）——⚠ 文档自相矛盾：这个格式完全不在 OpenAPI 摘要列出的 17 个 `formats[].type` 枚举值里,可能是文档页超前于当前 OpenAPI 快照,也可能是文档页的错误,本文档不收录这个格式,直到能确认它是否真实存在。
8. Webhook 投递本身（签名校验、重试行为）——只从 `webhooks/events.md`、`webhooks/security.md` 转录,没有对着真实接收端触发过。
