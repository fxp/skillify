# Search

> ⚠ 本文件内容全部来自官方文档 `reference/{post-search,search-optimizations-and-limitations}.md` 与 `guides/get-started/upgrade-guide-2025-09-03.md`，抓取于 2026-09-21，**未经真实 API 调用验证**。

## 端点

```
POST /v1/search
```

按标题搜索 **已经共享给当前连接** 的页面和数据源（`data_source`,不是 `database` ——见下方"2025-09-03 变更"）。不传 `query` 时返回共享给连接的全部内容（分页）。

```json
{
  "query": "quarterly report",
  "filter": { "value": "page", "property": "object" },
  "sort": { "direction": "descending", "timestamp": "last_edited_time" },
  "page_size": 20
}
```

| 参数 | 说明 |
| :--- | :--- |
| `query` | 匹配标题的关键词,不传则不过滤,返回全部共享内容 |
| `filter.property` | 固定 `"object"` |
| `filter.value` | `"page"` 或 `"data_source"`（**2025-09-03 之前是 `"database"`**,升级后必须改成 `"data_source"`,否则过滤条件不会按预期生效——⚠ 文档原文,未实测具体是报错还是静默返回空结果,按官方迁移指南的措辞升级时必须同步改这个值） |
| `filter.in_trash` | `true` 时只列回收站内容,可以单独用,也可以和 object 过滤组合 |
| `sort` | `{"timestamp": "last_edited_time", "direction": "ascending"\|"descending"}` 或 `{"property": "relevance"}` 二选一 |
| `page_size` | **默认值是 100**（注意：这和 `reference/intro.md` 里"分页端点默认 10 条"的通用说法不一致,是 Search 端点自己更大的默认值——⚠ 文档自相矛盾,以 `search-optimizations-and-limitations.md` 这条更具体的说明为准,但建议不管默认是多少都显式传 `page_size`,不要依赖任何一份文档里的默认值） |
| `start_cursor` | 分页游标,原样透传上次响应的 `next_cursor`,不要解析 |

## 2025-09-03 变更：搜索结果现在是 data source,不是 database

- `filter.value` 只接受 `"page"` 或 `"data_source"`,不再接受 `"database"`。
- 响应里代表数据库的结果,`object` 字段是 `"data_source"`,`id` 是 data source 的 ID,不是 database 的 ID——**如果代码期待拿到 `database_id` 直接去查,会拿到错误类型的 ID**,响应里其它字段（含 `properties` schema）基本不变。
- **如果一个数据库有多个数据源,每个数据源会作为独立的结果分别出现**,不是数据库本身只出现一条——query 匹配的仍然是数据库标题,不是每个数据源各自的标题,但命中后会把它名下的每个数据源都作为独立结果返回。
- 查询标题匹配的语义本身（模糊匹配、匹配范围）本次改版没有变。

## 限制：Search 不是为这三件事设计的

官方文档明确指出以下三类用法不适合用 Search（⚠ 文档原文，未实测）：

1. **穷举一个连接能访问的全部内容**——Search **不保证返回全部结果**,索引在遍历过程中可能变化,不要把它当成"列出所有可访问页面"的可靠数据源。
2. **在某一个具体数据源内部搜索/过滤**——用错误的工具做这件事效果很差,正确做法是先拿到 `data_source_id`,再用 `PATCH /v1/data_sources/{id}/query`（见 `references/databases-and-data-sources.md`),Search 只按标题匹配,不支持按属性值过滤。
3. **要求立即拿到最新结果**——Search 索引 **不是实时的**。一个页面刚被共享给连接（比如 OAuth 授权刚完成）之后立刻搜索,响应里可能还没有这个页面,是索引延迟,不是共享失败。需要展示搜索结果驱动的界面时,建议给用户一个"刷新重试"按钮,而不是把第一次搜索的空结果当成最终结论。
   - **例外**：**直接共享给连接的页面/数据库保证会被搜索返回,不受索引延迟影响**（这是官方给出的一个优化保证）。间接可见的内容（比如某个页面的子页面,只共享了父页面）没有这个保证,可能有延迟。

## 和"必须共享"坑的关系

Search 天然只返回共享给当前连接的内容——**如果预期应该出现的页面没有出现在搜索结果里,大概率原因和"查询具体 ID 返回 404"是同一个：没有共享,而不是查询语法错了**。排查步骤见 `references/auth-and-sharing.md` 的"★ 最容易踩的坑"一节。
