# Firecrawl — real API verification log

Key used: a real `fc-...` key, ~1000 credits/month plan, passed only via env var
`FIRECRAWL_KEY`, never written to a file. Base URL tested: `https://api.firecrawl.dev/v2`
(current). `https://api.firecrawl.dev/v1` also tested and still functionally responds
(same basic scrape response shape) but v2 is what the docs actively document; v1 is legacy.

## 1. Basic scrape — POST /v2/scrape (2026-09-20/21)

`{"url":"https://example.com"}` →
```json
{"success":true,"data":{"markdown":"# Example Domain\n...","metadata":{"title":"Example Domain","language":"en","scrapeId":"...","sourceURL":"https://example.com","url":"https://example.com/","statusCode":200,"contentType":"text/html","proxyUsed":"basic","cacheState":"hit","cachedAt":"...","creditsUsed":1,"concurrencyLimited":false}}}
```
1 credit for a plain markdown scrape. `data.metadata.cacheState` present unprompted
(`"hit"` on a repeat scrape of the same URL — see maxAge/caching below).

## 2. No auth / bad auth / bad input (v1, but shape matches v2's error envelope)

- No `Authorization` header → HTTP 403: `{"success":false,"error":"Unfortunately, your IP address looks suspicious, so Firecrawl can't be used without an API key from here. ... (If you're an agent, you can also use https://firecrawl.dev/auth.md)"}`
- Wrong key → HTTP 401: `{"success":false,"error":"Unauthorized: Invalid token"}`
- Invalid URL (`"not-a-valid-url"`) → HTTP 400: `{"success":false,"code":"BAD_REQUEST","error":"URL must have a valid top-level domain or be an IP address","details":[{"code":"custom","path":["url"],"message":"..."}]}`
- No rate-limit headers observed on a normal 200 response.

## 3. ⚠→✅ CRITICAL: bare `"json"` format string silently fails (2026-09-21)

`formats: ["markdown", "json"]` (bare string, no schema — the natural first guess,
since bare strings work fine for `"markdown"`/`"html"`/`"links"`/etc.) →
HTTP 200, `success:true`, **`data.json` is `null`**, and the only signal is a
`data.warning` field:
```
"warning":"JSON extraction failed: Invalid schema for response_format 'response': In context=(), 'required' is required to be supplied and to be an array including every key in properties. Extra required key 'extractedData' supplied."
```
Cost: **5 credits**, charged even though extraction failed.

Correct form — `formats: ["markdown", {"type":"json","schema":{"type":"object","properties":{"title":{"type":"string"}},"required":["title"]}}]` →
`data.json: {"title":"Example Domain"}`, no warning, same 5 credits.

**This is a silent-failure trap, not a documented gotcha** — `success` stays `true`
either way; only `data.json === null` + a buried `data.warning` string distinguish
failure from success. Every other `formats` entry (`markdown`, `html`, `links`,
`screenshot`, ...) accepts a bare string; only `json` (and `changeTracking`) actually
require the object form with `schema`. An agent used to the bare-string pattern will
almost certainly try `formats: ["json"]` first.

## 4. Map — POST /v2/map (2026-09-21)

`{"url":"https://skillify.carbonleft.com"}` →
```json
{"success":true,"id":"...","links":[{"url":"https://skillify.carbonleft.com","title":"skillify-runtime"}],"warning":"Only 1 result(s) found. For broader coverage, try mapping the base domain: carbonleft.com"}
```
Maps only the exact path given, not automatically the whole site — contrary to what
"map a website" implies. The `warning` field is again where the actionable signal
lives, not an error.

## 5. Search — POST /v2/search (2026-09-21)

`{"query":"firecrawl web scraping api","limit":2}` → each result's `description`
field contains full scraped markdown-ish content (paragraphs, code blocks), not a
short snippet — confirmed by the OpenAPI spec: `scrapeOptions.formats` defaults to
`['markdown']`, so search scrapes every result by default. Costs more credits and
returns much more data per result than a "search" name implies; pass
`scrapeOptions: {formats: []}`-equivalent (check field for opt-out) to get
link/title/description only if that's what's wanted — ⚠ 文档未确认关闭方式的确切参数，
只从 schema 里看到默认值是 `['markdown']`，没有实测"如何要回纯摘要".

## 6. Crawl — async job pattern confirmed (2026-09-21)

`POST /v2/crawl {"url":"https://skillify.carbonleft.com","limit":2}` →
`{"success":true,"id":"01a0bf91-...","url":"https://api.firecrawl.dev/v2/crawl/01a0bf91-..."}`
— **no page content in this response**, just a job id + status URL. This is the
single most likely "intuition trap": scrape returns content synchronously, crawl does
not, despite superficially similar request shapes.

`GET /v2/crawl/{id}` (polled ~3s later) →
```json
{"success":true,"status":"scraping","completed":2,"total":2,"creditsUsed":2,"expiresAt":"...","next":"https://api.firecrawl.dev/v2/crawl/{id}?skip=2","data":[{...scraped page...}]}
```
Results arrive embedded in the status response itself once available (no separate
results endpoint); `next` carries a `?skip=` pagination cursor once the result set
outgrows one page. `status` values seen: `"scraping"` (crawl.md doc lists `"completed"`
and `"failed"` too, not independently observed here — flagged ⚠ 文档原文，未逐一实测每个
status 值).

## 7. ⚠→✅ CRITICAL: /v2/extract is deprecated, contradicts its own doc page (2026-09-21)

`POST /v2/extract {"urls":["https://example.com"],"schema":{...}}` →
```json
{"success":true,"id":"...","urlTrace":[],"warnings":["/v2/extract is deprecated. Use /v2/scrape with formats including a 'json' format object."],"replacement":"/v2/scrape"}
```
`GET /v2/extract/{id}` (polled) →
```json
{"success":true,"data":{"title":"Example Domain"},"status":"completed","tokensUsed":306,"creditsUsed":21,"warnings":["/v2/extract/:jobId is deprecated. Use /v2/scrape with formats including a 'json' format object."],"replacement":"/v2/scrape"}
```
**Both calls succeed and return correct data — deprecation is signaled only via a
`warnings` array + `replacement` field, never an error status.** 21 credits for a
single 1-URL, 1-field extraction (vs. 5 for the equivalent via `/scrape` JSON format)
— extract is also ~4x more expensive than the endpoint it tells you to use instead.

**This directly contradicts `docs.firecrawl.dev/developer-guides/usage-guides/choosing-the-data-extractor.md`**,
which frames `/extract` as a first-class endpoint and recommends migrating away from
it to **`/agent`** (not `/scrape`) — "We recommend migrating to `/agent`—it's faster,
more reliable, doesn't require URLs, and handles all `/extract` use cases plus more."
Two authoritative sources give two different replacements for the same deprecated
endpoint. `/agent` is out of scope for this skill (autonomous multi-step, separate
cost model, not verified here) — the skill recommends `/scrape` JSON mode as the
practical default for known-URL structured extraction, per the live API's own runtime
warning, and notes the doc page's conflicting recommendation explicitly rather than
picking one silently.

## Credits

Plan: 1000 credits/period, ~511 remaining after this session's testing (check
`GET /v2/team/credit-usage`, `{"success":true,"data":{"remainingCredits":N,"planCredits":N,...}}`).
Rough costs observed: plain markdown scrape = 1 credit; scrape with JSON format = 5
credits (win or fail); tiny 2-page crawl = 1 credit/page; `/v2/extract` (1 URL, 1
field) = 21 credits. Not a documented flat-rate table — these are the actual charges
seen, not doc claims.

## Not verified this round (explicitly out of scope / not tested)

- `/agent`, `/interact`, `/monitor`, `/parse` (document parsing), `/search/research/*`,
  `/search/developer` — all real endpoints, all out of scope for this skill (see
  SKILL.md's "not covered" section). Not tested.
- Webhook delivery itself (signature verification, retry behavior) — documented from
  `webhooks/events.md` and `webhooks/security.md` only, not triggered against a real
  receiving endpoint. Marked 文档原文，未实测 wherever it appears.
- `actions` (browser interaction: click/scroll/wait sequences within scrape) —
  documented from `advanced-scraping-guide.md` only, not exercised for real (would
  need a page with meaningful interactive state to be a real test, not just a cost
  question).
