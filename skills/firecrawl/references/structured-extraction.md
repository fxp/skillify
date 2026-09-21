# Structured Extraction: Which of Firecrawl's Three Options to Use

Firecrawl offers **three different endpoints** that all claim to do "structured data
extraction": `/scrape` (JSON format), `/extract`, and `/agent`. They overlap enough
in their pitch that an agent reading the docs top-to-bottom can reasonably pick any
of the three — and the docs themselves send mixed signals about which one is current.
This file exists to stop that: pick correctly from the decision table below, know
that `/extract` is deprecated even though calling it looks completely successful, and
know the docs page and the live API disagree about what to migrate to.

If you take one thing from this file: **inspect the `warnings` field on every
`/extract` response before trusting it's the right endpoint to be calling at all.**
A `200 success:true` from `/extract` does not mean `/extract` is the endpoint you
should be using.

⚠ This file also documents a place where two authoritative sources — the doc page
and the live API's own runtime warning — actively disagree about what to do next.
Both quotes are reproduced verbatim below rather than silently resolved in one
direction, per this skill's policy of flagging doc-vs-reality discrepancies instead
of picking a winner for you.

## Decision table

| Your situation | Recommended approach | Reference |
|---|---|---|
| Known single URL, you know exactly what fields you want | `/scrape` with a `json` format object | `references/scrape.md` |
| Known list of specific URLs, want the same schema from each | Batch `/scrape` + JSON format (preferred), or the deprecated-but-functional `/extract` if you must | `references/crawl-and-batch.md`; `/extract` section below |
| Don't know the URLs — need autonomous discovery across the web | `/agent` | out of scope here — see "`/agent`: out of scope" below |

The doc page this file is built from (`choosing-the-data-extractor.md`) phrases the
same decision as: *"Do you know the exact URL(s) containing your data? NO → `/agent`.
YES, single page → `/scrape` JSON mode. YES, multiple pages → `/agent` with URLs (or
batch `/scrape`)."* That framing is consistent with the table above except that the
doc page pushes `/agent` even for known-URL cases where you'd reach for `/extract` or
batch `/scrape` — see the contradiction discussion below for why this skill does not
follow that specific recommendation.

## Why three endpoints for one job

| | `/scrape` (json format) | `/extract` | `/agent` |
|---|---|---|---|
| URL required | Yes, exactly one | Yes (wildcards ok) | No — optional |
| Discovery | None — you supply the URL | Crawls from given URLs | Autonomous web search |
| Processing | Synchronous | Async (job id + poll) | Async |
| Status per doc page | Active | **"Use `/agent` instead"** | Active, positioned as `/extract`'s successor |
| Status per live API | Active | **Deprecated (runtime warning), replacement field says `/scrape`** | Not tested by this skill |
| Cost (1 URL / 1 field, observed) | 5 credits | 21 credits | Not tested (doc says ~100–500 credits typical) |

Two of the three rows above disagree with each other, on purpose — that disagreement
is exactly what the rest of this file documents.

## `/agent`: out of scope, not verified

⚠ The doc page describes `/agent` as Firecrawl's newest endpoint: no URL required, an
LLM agent autonomously searches and navigates the web, `POST /agent` with a `prompt`
and optional `schema`/`urls`/`model`/`maxCredits`, priced dynamically with "5 free
runs/day" per the doc's pricing table, running on a `spark-2` model ("Spark 1 models
are deprecated and route to `spark-2`" — again per the doc page, not observed live).
**None of this has been tested against the live API in this skill's verification
pass.** Everything in this paragraph is repeated from `choosing-the-data-extractor.md`
only — it is doc-only, unverified content, not confirmed behavior, and it should be
treated with the same suspicion this file applies to `/extract`'s own doc claims
(which turned out to be wrong about the live deprecation replacement — see below).
If your task genuinely needs autonomous URL discovery (you don't know which pages
contain the data), start from the doc page at `/features/agent` and verify its
behavior for yourself before depending on it — do not treat anything above as
confirmed.

## ⚠→✅ `/scrape` JSON-format trap (brief — full detail in `references/scrape.md`)

Even when `/scrape` JSON mode is the right call per the table above, there is a live,
verified silent-failure trap worth knowing before you leave this file: passing a bare
string `"json"` inside `formats` (the pattern that works fine for `"markdown"`,
`"html"`, `"links"`, etc.) returns `HTTP 200, success:true` with `data.json: null` and
the only failure signal buried in a `data.warning` string — cost 5 credits, charged
even on failure. `已用真实 API 验证（2026-09-21）`. The correct form requires the object
shape: `{"type":"json","schema":{...}}`. `json` (and `changeTracking`) are the only
`formats` entries that actually require the object form — every other format accepts
the bare string. See `references/scrape.md` for the full write-up; this paragraph
exists only so a reader who lands directly on this file doesn't miss it.

---

## ⚠→✅ `/extract`（已废弃，仍能用）

**Endpoint**: `POST /extract` + `GET /extract/{id}`

**用途**: 从一个或多个指定 URL（支持通配符，如 `example.com/*`）用 LLM 抽取结构化数据；
异步任务模式，`POST` 返回 job id，需要轮询 `GET /extract/{id}` 拿结果，和 `/crawl` 的模式
一样。按 OpenAPI 字段摘要，这是官方仍然维护 schema 的一个"正式"端点——但见下方"注意事项"，
运行时行为已经不这么说了。

**关键参数**（来自 `Extraction.md` 的 OpenAPI 摘要，POST /extract 请求体）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `urls` | array<string(uri)> | 是 | — | 目标 URL 列表，支持通配符 |
| `prompt` | string | 否 | — | 引导抽取过程的自然语言提示 |
| `schema` | object | 否 | — | 抽取结果结构，需符合 JSON Schema |
| `enableWebSearch` | boolean | 否 | `false` | 为 true 时允许用网页搜索补充数据 |
| `ignoreSitemap` | boolean | 否 | `false` | 为 true 时扫描网站时忽略 sitemap.xml |
| `includeSubdomains` | boolean | 否 | `true` | 是否同时扫描给定 URL 的子域名 |
| `showSources` | boolean | 否 | `false` | 为 true 时响应里带上 `sources` 字段 |
| `scrapeOptions` | object | 否 | — | 同 `/scrape` 的选项（`formats` 等），包括 `formats[].type=json` |
| `ignoreInvalidURLs` | boolean | 否 | `true` | 为 true 时无效 URL 不会导致整个请求失败，会被收集进响应的 `invalidURLs` |

**POST /extract 响应 200 字段**（OpenAPI 文档记录的部分）：`success` (boolean)、`id`
(string)、`invalidURLs` (array\<string>，仅 `ignoreInvalidURLs=true` 时出现)。
**GET /extract/{id} 响应 200 字段**：`success`、`data` (object)、`status`
(`completed`/`processing`/`failed`/`cancelled`)、`expiresAt`、`tokensUsed`（仅完成后
才有）。

注意：下面示例响应里出现的 `warnings` 和 `replacement` 字段，**不在 OpenAPI 文档记录的
字段列表里**——它们是运行时真实观察到的，文档目前没有描述它们的存在。

**示例请求**

```bash
curl -s -X POST "https://api.firecrawl.dev/v2/extract" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com"],
    "schema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}
  }'
```

**示例响应**（下面两段是本次会话对真实 API 实测抓到的原始 JSON，未做任何改写——见
`firecrawl-workspace/verification-log.md` 第 7 节）

`POST /v2/extract` 响应：

```json
{"success":true,"id":"...","urlTrace":[],"warnings":["/v2/extract is deprecated. Use /v2/scrape with formats including a 'json' format object."],"replacement":"/v2/scrape"}
```

`GET /v2/extract/{id}` 响应（轮询后）：

```json
{"success":true,"data":{"title":"Example Domain"},"status":"completed","tokensUsed":306,"creditsUsed":21,"warnings":["/v2/extract/:jobId is deprecated. Use /v2/scrape with formats including a 'json' format object."],"replacement":"/v2/scrape"}
```

**注意事项**

`已用真实 API 验证（2026-09-21）`。这是本文件最核心的事实，完整展开如下：

1. **两次调用都"成功"，数据也是对的。** `POST` 返回 `success:true`，`GET` 轮询后
   `status:"completed"`，`data.title` 抽取正确。**废弃信号只通过 `warnings` 数组和
   `replacement` 字段传达，从来没有任何非 200 状态码或错误信息。** 一个不主动检查
   `warnings` 字段的 agent 永远不会发现自己在用一个废弃端点——两次响应各自带着几乎
   相同的警告字符串：
   - POST: `"/v2/extract is deprecated. Use /v2/scrape with formats including a 'json' format object."`
   - GET: `"/v2/extract/:jobId is deprecated. Use /v2/scrape with formats including a 'json' format object."`

2. **两个"权威来源"给出两个不同的迁移建议，互相矛盾：**
   - **活的 API 运行时警告**（上面两条 `warnings` + `replacement: "/v2/scrape"`）说：
     迁移到 `/scrape`，用带 `json` format 对象的形式。
   - **官方文档页** `choosing-the-data-extractor.md` 原文说的是另一件事：
     > "**Use `/agent` instead**: We recommend migrating to `/agent`—it's faster,
     > more reliable, doesn't require URLs, and handles all `/extract` use cases
     > plus more."
     文档页整节都在推 `/extract` → `/agent` 的迁移路径（见该文档 "Migration:
     `/extract` → `/agent`" 一节的代码示例），完全没提运行时警告说的 `/scrape`。

   这两个建议不是同一件事的两种说法——`/agent` 和 `/scrape` 是两个完全不同的端点，
   定价模型、是否需要 URL、同步/异步都不一样。本文件不替你 silently 选一个：需要已知
   URL 的确定性抽取，用运行时警告指向的 `/scrape`（也是下面成本对比里更便宜的那个，
   且本技能已验证其行为）；需要自主发现型抓取，才去看文档指向的 `/agent`（本技能未
   验证，见上方"`/agent`: out of scope"）。

3. **成本对比**：同一个 1 URL / 1 字段的最小抽取任务，`/extract` 花了 **21 credits**
   （`tokensUsed:306`，按 token 计费），而等价的 `/scrape` + `json` format 只需
   **5 credits**（1 base + 4 for JSON mode，固定费率）——`/extract` 大约是它自己
   宣称的替代端点的 **4 倍价格**。`已用真实 API 验证（2026-09-21）`。

4. **结论**：`/extract` 目前仍然能跑、数据也对，但（a）官方运行时已经标记为废弃，
   （b）比推荐的替代方案贵 4 倍，（c）文档和 API 对"该迁移到哪"意见不一致。除非有
   `/extract` 独有而 `/scrape`/批量做不到的需求（比如同一次请求里跨多个未知具体路径
   的 `example.com/*` 通配符抓取），否则默认走 `/scrape` JSON format（单页，见
   `references/scrape.md`）或批量 `/scrape`（已知多 URL，见
   `references/crawl-and-batch.md`）。

---

## Checklist: how to tell you're about to make this mistake

Before calling `POST /extract`, ask:

1. **Do I actually know the URL(s)?** If yes and it's a single page, you almost
   certainly want `/scrape` JSON format instead — stop and go to
   `references/scrape.md`.
2. **Am I calling `/extract` only because the doc page listed it as one of three
   "legitimate" options?** That framing is accurate about `/extract` existing and
   working, but the doc page's own text one paragraph later says *"Use `/agent`
   instead"* — it is not recommending `/extract` for new code, it's describing it
   on the way to telling you not to use it.
3. **After calling `/extract`, did I check `response.warnings`?** If you skip this,
   you will not find out you used a deprecated, 4x-more-expensive endpoint — nothing
   else in the response signals it. Both the `POST` response and every `GET
   /extract/{id}` poll carry the warning; check both, not just one.
4. **Am I about to copy the doc page's "Migration: `/extract` → `/agent`" example
   verbatim?** That migration path is real per the doc, but the live API is telling
   you `/scrape` instead. If your use case has known URLs (the common case), `/scrape`
   is cheaper, synchronous, and already verified in this skill — prefer it over
   chasing the doc's `/agent` migration unless you specifically need autonomous
   discovery.

## Summary

- **Know the exact URL(s) and want a fixed schema?** Use `/scrape` with a `json`
  format object (single URL) or batch `/scrape` (multiple known URLs). Cheapest,
  synchronous, and the only one of the three fully verified in this skill.
- **Tempted to use `/extract` because the doc page lists it as a first-class
  option?** It still works, but it is runtime-deprecated (confirmed live), ~4x the
  cost of the `/scrape` equivalent, and the two sources that describe it disagree
  about what to replace it with. Prefer `/scrape`/batch `/scrape` instead.
  If you do use `/extract` anyway, always check the response's `warnings` array —
  don't assume `success:true` means it's the right endpoint.
- **Don't know the URLs at all?** That's `/agent`'s job per the docs — not verified
  by this skill, treat its documented behavior as unconfirmed until tested.
