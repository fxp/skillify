# 控制 Perplexity 搜索什么：域名/时间/语言/地理位置过滤

⚠ 本文件全部内容整理自官方文档与 OpenAPI 规范，未用真实 Key 调用验证。

这些过滤字段**名字在 Sonar / Agent API / Search API 三处基本一致**，但**挂载位置不同**——这是最容易复制粘贴出错的地方。先看这张对照表，再看各字段细节。

## 挂载位置对照表

| 过滤能力 | Sonar Chat Completions（请求体顶层） | Agent API（`web_search` 工具对象内） | Search API（请求体顶层） |
|---|---|---|---|
| 域名过滤 | `search_domain_filter` | `filters.search_domain_filter` | `search_domain_filter` |
| 语言过滤 | `search_language_filter` | ❌ 没有等价物 | `search_language_filter` |
| 相对时间窗 | `search_recency_filter` | `filters.search_recency_filter` | `search_recency_filter` |
| 精确发布日期范围 | `search_after_date_filter` / `search_before_date_filter` | `filters.search_after_date_filter` / `filters.search_before_date_filter` | `search_after_date_filter` / `search_before_date_filter` |
| 精确更新日期范围 | `last_updated_after_filter` / `last_updated_before_filter` | `filters.last_updated_after_filter` / `filters.last_updated_before_filter` | `last_updated_after_filter` / `last_updated_before_filter` |
| 地理位置个性化 | `web_search_options.user_location` | `user_location`（挂在工具对象上，**不在** `filters` 里，与 `filters` 平级） | ❌ 没有独立 `user_location`，但有顶层 `country` 字段（见下） |
| 搜索上下文档位 | `web_search_options.search_context_size` | `search_context_size`（挂在工具对象上，**不在** `filters` 里） | `search_context_size` |
| 结果条数上限 | ❌ 没有直接对应（用 `web_search_options` 间接控制） | `max_results`（挂在工具对象上） | `max_results` |

## 域名过滤

**字段**：`search_domain_filter`，array of string，最多 20 个条目。

**Allowlist 模式**：条目不带前缀 → 只搜这些域名。
**Denylist 模式**：条目带 `-` 前缀 → 排除这些域名。
**⚠ 两种模式不能在同一个数组里混用**（文档原文明确警告），实际混用时的行为（报错还是部分生效）未文档说明。

条目可以是域名级（`wikipedia.org`）也可以是 URL 级更细粒度（`https://en.wikipedia.org/wiki/Chess`），后者⚠ 具体匹配规则（前缀匹配？路径级过滤？）文档未展开。

```python
# Sonar：Allowlist
client.chat.completions.create(
    model="sonar",
    messages=[...],
    search_domain_filter=["nasa.gov", "wikipedia.org", "space.com"]
)

# Sonar：Denylist
client.chat.completions.create(
    model="sonar",
    messages=[...],
    search_domain_filter=["-reddit.com", "-pinterest.com"]
)

# Agent API：注意挂在 filters 里面
response = client.responses.create(
    model="openai/gpt-5.6-sol",
    input="...",
    tools=[{"type": "web_search", "filters": {"search_domain_filter": [".gov"]}}]
)
```

## 相对时间窗 vs 精确日期范围

**相对窗口**：`search_recency_filter`，枚举 `hour`（过去 1 小时，适合突发新闻）/ `day`（过去 24 小时）/ `week`（过去 7 天）/ `month`（过去 30 天）/ `year`（过去 365 天）。

**精确日期**：`search_after_date_filter` / `search_before_date_filter`（按**发布日期**过滤）、`last_updated_after_filter` / `last_updated_before_filter`（按**最后更新日期**过滤）。两组可以组合使用（比如"2024 年发布但最近更新过"）。

**格式**：一律 `MM/DD/YYYY`（`%m/%d/%Y`），例如 `"3/1/2025"` 或 `"03/01/2025"` 都可接受。**不是** ISO 8601 的 `YYYY-MM-DD`。

**⚠ `search_recency_filter` 不能和精确日期过滤器同时使用**（文档原文，`search/filters/date-time-filters.md`"Best Practices"一节明确写"`search_recency_filter` cannot be combined with specific date filters"）。混传时的实际行为（报错 / 忽略其中一个 / 未定义）⚠ 文档未说明，是本 skill 优先验证项之一。

客户端校验用的正则（文档给出）：

```
^(0?[1-9]|1[0-2])/(0?[1-9]|[12][0-9]|3[01])/[0-9]{4}$
```

## 语言过滤

**字段**：`search_language_filter`，array of ISO 639-1 两位小写代码，最多 10 个。常用代码：`en`/`es`/`fr`/`de`/`it`/`ru`/`zh`/`ja`/`ko`/`ar`/`hi`/`pt` 等（完整列表见 ISO 639-1 标准）。

**⚠ Agent API 没有这个能力的等价物**——迁移指南把它列进"没有 Agent API 等价物，直接砍掉"的一类，不是改名换位置那种。需要按语言过滤检索结果时只能用 Sonar Chat Completions 或 Search API，不能迁移到 Agent API 的 `web_search` 工具。

## 地理位置个性化

`user_location` 接受任意组合：

- `country` — ISO 3166-1 alpha-2 两位代码（如 `"US"`、`"FR"`）
- `region` — 州/省名（如 `"California"`）
- `city` — 城市名（如 `"San Francisco"`）
- `latitude` / `longitude` — 精确坐标

**⚠ `latitude`/`longitude` 必须和 `country` 一起传，不能单独传**（文档原文明确警告）。`city`/`region` 能显著提升定位准确度，建议和 `country` 一起传。

Search API 没有完整的 `user_location` 对象，只有一个顶层 `country` 字段（ISO 3166-1 alpha-2），粒度比 Sonar/Agent API 粗。

## 搜索上下文档位（成本 vs 深度）

`search_context_size`：`low`（默认，最便宜最快）/ `medium`（均衡）/ `high`（最深，成本最高）。**只影响 Sonar 和 Agent API 的请求计价档位**（见 `references/errors-limits-pricing.md` 的费率表）；Search API 也接受这个字段但计费方式不同（Search API 是按请求数固定收费，不因 `search_context_size` 浮动，⚠ 文档未明确说明该字段在 Search API 里对价格是否有影响，只确认它能控制"每个结果页抽取多少内容"）。

**⚠ 与 `max_tokens`/`max_tokens_per_page` 互斥**：文档原文提示用 `max_tokens`/`max_tokens_per_page` 精细控制时应省略 `search_context_size`，两者同时传的行为未说明。

## 过滤器可以自由组合

文档原文（Agent API `web_search` 工具页）明确说"Filters compose freely... there's no per-request limit on filter combinations"——域名+日期+语言+地理位置可以同时用（除了上面提到的"相对窗口 vs 精确日期"这一组互斥）。
