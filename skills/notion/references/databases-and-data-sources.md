# 数据库(database)与数据源(data source)

> ⚠ 本文件内容全部来自官方文档（`guides/data-apis/working-with-databases.md`、`guides/get-started/upgrade-guide-2025-09-03.md`、`reference/{database,data-source,property-object,query-a-data-source,filter-data-source-entries,sort-data-source-entries}.md`）与 OpenAPI 规范，抓取于 2026-09-21，**未经真实 API 调用验证**。这是本 skill 里训练记忆最容易过时的一块——如果你记得的 Notion API 是"database 就是一张表，直接 `POST /v1/databases/{id}/query`"，那是 2025-09-03 之前的模型，现在会报错或行为不对。

## 目录

- [核心心智模型：database → data source → page](#核心心智模型database--data-source--page)
- [为什么会有这个变化](#为什么会有这个变化)
- [发现流程：先拿 data_source_id，再做任何事](#发现流程先拿-data_source_id再做任何事)
- [Database 端点：管的是"容器"属性](#database-端点管的是容器属性)
- [Data source 端点：管的是"表结构"和"表数据"](#data-source-端点管的是表结构和表数据)
- [查询、过滤、排序](#查询过滤排序)
- [Property object：表结构里的一列长什么样](#property-object表结构里的一列长什么样)
- [Relation 属性的读写不对称](#relation-属性的读写不对称)
- [大数据源的完整读取](#大数据源的完整读取)

## 核心心智模型：database → data source → page

```
Database（数据库容器：标题、图标、封面、是否内嵌、parent）
   └── Data source（一份表结构 + 数据：properties schema、真正的"列"）
          └── Page（一行数据：properties 的值）
```

- 一个 **database** 可以包含 **一个或多个 data source**（"多源数据库"，2025-09-03 引入）。绝大多数现存的数据库仍然只有一个 data source，但 **不能假设永远只有一个** ——只要有人在 Notion UI 里给这个数据库加了第二个数据源，所有还在用旧版本 API（`database_id` 直连查询/创建）的连接就会开始报错或看不到新数据。
- **Database** 对象管的是"容器"层面的属性：`title`、`icon`、`cover`、`parent`（挂在哪个页面/工作区下）、`is_inline`（是否内嵌显示）、`in_trash`。
- **Data source** 对象管的是"表"层面的属性：`properties`（schema，即列定义）、`title`（这个数据源自己的名字，多源时每个数据源标题可以不同）、`description`、`icon`。
- **Page** 是数据源里的一行，`parent` 指向 `data_source_id`（2025-09-03 之前指向的是 `database_id`）。

## 为什么会有这个变化

以前一个数据库只能有一份数据（一份 schema），API 把"数据库"和"这份数据"两个概念合并成一个对象。现在 Notion 允许一个数据库下挂多个数据源（例如同一个数据库在不同视图里接入不同来源的数据），必须把"容器"和"表"拆成两个对象才能表达。**这不是一次纯新增功能的升级，是破坏性变更**：升级到 `2025-09-03` 或更新版本后，`POST /v1/pages` 的 `parent.database_id` 必须换成 `parent.data_source_id`，`PATCH /v1/databases/{id}/query` 这个端点被 `PATCH /v1/data_sources/{id}/query` 取代。

## 发现流程：先拿 data_source_id，再做任何事

只要手里只有一个 `database_id`（比如用户直接粘贴了一个 Notion 数据库链接、或者是历史代码里硬编码的），**第一步永远是**：

```bash
curl https://api.notion.com/v1/databases/$DATABASE_ID \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2026-03-11"
```

⚠ 文档原文，未实测。响应形状（Retrieve a database 现在只返回容器信息 + 数据源列表，不再直接带 schema）：

```json
{
  "object": "database",
  "id": "{database_id}",
  "title": [ /* rich text */ ],
  "parent": { "type": "page_id", "page_id": "..." },
  "is_inline": false,
  "in_trash": false,
  "data_sources": [
    { "id": "{data_source_id}", "name": "My Task Tracker" }
  ],
  "icon": null,
  "cover": null
}
```

拿到 `data_sources[0].id`（绝大多数情况下只有一个元素）之后，才去调用下面所有"查询/创建页面/定义 relation"相关的端点。**Notion 应用里也能直接拿**：数据库设置菜单里有 "Manage data sources → Copy data source ID"，如果用户是从 Notion UI 里操作过来的，可以让他们直接复制这个 ID，跳过一次 API 调用。

## Database 端点：管的是"容器"属性

| 操作 | Endpoint | 说明 |
| :--- | :--- | :--- |
| 创建数据库（连同它的初始数据源） | `POST /v1/databases` | `parent` + `title`/`icon`/`cover` 在顶层；初始数据源的列定义放在 `initial_data_source.properties` 里（不是顶层 `properties`） |
| 检索数据库 | `GET /v1/databases/{database_id}` | 见上一节，只返回容器信息 + `data_sources[]` 列表 |
| 更新数据库 | `PATCH /v1/databases/{database_id}` | 只能改：`parent`（移动数据库，公共连接甚至可以移到工作区级私有页面）、`title`、`is_inline`、`icon`、`cover`、`in_trash`。⚠ 文档原文，未实测：`cover` 在 `is_inline: true` 时不支持 |
| ~~List databases~~ | ~~`GET /v1/databases`~~ | **已废弃**，自 `2022-02-22` 起被移除，SDK v5 起也不再包含此方法；要列出可访问的数据库改用 Search |

创建数据库示例：

```json
POST /v1/databases
{
  "parent": { "type": "page_id", "page_id": "..." },
  "title": [{ "text": { "content": "Tasks" } }],
  "icon": { "type": "emoji", "emoji": "✅" },
  "initial_data_source": {
    "properties": {
      "Name": { "title": {} },
      "Done": { "checkbox": {} }
    }
  }
}
```

## Data source 端点：管的是"表结构"和"表数据"

| 操作 | Endpoint | 说明 |
| :--- | :--- | :--- |
| 创建数据源 | `POST /v1/data_sources` | 给**已有**数据库追加一个新数据源（新的一份 schema）；不要跟"创建数据库"混淆 |
| 检索数据源 | `GET /v1/data_sources/{data_source_id}` | 返回 `object: "data_source"`、`properties`（完整 schema）、`parent`（指向所属 `database_id`）、`database_parent`（数据库自己的父级，即"祖父"节点） |
| 更新数据源 | `PATCH /v1/data_sources/{data_source_id}` | 改：`properties`（改表结构——加列、删列、改列类型）、`title`、`in_trash`（归档/恢复这一个数据源，不影响同一数据库下的其它数据源） |
| 查询数据源 | `PATCH /v1/data_sources/{data_source_id}/query` | 见下节 |

⚠ 文档原文，未实测：schema 建议上限 **500 个属性或 50KB**，超限的更新会被服务端拒绝。

`data_source_id` 和 `database_id` **不可互换**——拿 database_id 去调 data source 端点，或反过来，预期是报错，不是静默兼容。

## 查询、过滤、排序

```bash
curl -X PATCH https://api.notion.com/v1/data_sources/$DATA_SOURCE_ID/query \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2026-03-11" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": { "property": "Done", "checkbox": { "equals": false } },
    "sorts": [{ "property": "Due date", "direction": "ascending" }]
  }'
```

```python
import os, requests

resp = requests.patch(
    f"https://api.notion.com/v1/data_sources/{data_source_id}/query",
    headers={
        "Authorization": f"Bearer {os.environ['NOTION_API_KEY']}",
        "Notion-Version": "2026-03-11",
    },
    json={
        "filter": {"property": "Done", "checkbox": {"equals": False}},
        "sorts": [{"property": "Due date", "direction": "ascending"}],
    },
)
```

不传 `filter` → 返回该数据源里所有未归档的页面（分页）。

**过滤器(filter)**：`{"property": "<列名或属性 id>", "<属性类型>": {"<操作符>": <值>}}`，属性类型和实际列类型必须匹配（比如 `select` 类型的列要用 `"select": {...}`，不能套用 `multi_select` 的操作符）。可以用 `"and"`/`"or"` 数组做复合、嵌套过滤，对应 Notion UI 里"且/或"链式条件。⚠ 文档原文，未实测——常见类型的操作符：

| 属性类型 | 操作符（部分） | 值的形状 |
| :--- | :--- | :--- |
| `checkbox` | `equals`、`does_not_equal` | `boolean` |
| `select` | `equals`、`does_not_equal`、`is_empty`、`is_not_empty` | `string`（也可以传字符串数组做多值匹配） |
| `multi_select` | `contains`、`does_not_contain`、`is_empty`、`is_not_empty` | `string` 或 `string[]` |
| `relation` | `contains`、`does_not_contain`、`is_empty`、`is_not_empty` | `string`（UUID，单个） |
| `rich_text` | `contains`、`does_not_contain`、`starts_with`、`ends_with`、`equals`、`is_empty`、`is_not_empty` | `string` |
| `number` | `equals`、`greater_than`、`less_than`、`greater_than_or_equal_to`、`less_than_or_equal_to`、`is_empty`、`is_not_empty` | `number` |
| `date` | `equals`、`before`、`after`、`on_or_before`、`on_or_after`、`past_week`/`this_week`/`next_month` 等相对日期、`is_empty`、`is_not_empty` | ISO 8601 字符串或 `{}`（相对日期） |
| `timestamp` | 用来按 `created_time`/`last_edited_time` 过滤，不针对某个用户属性，套 `date` 的操作符 | — |

**排序(sorts)**：`sorts` 是一个数组，每项 `{"property": "<列名>", "direction": "ascending"|"descending"}`，或者 `{"timestamp": "created_time"|"last_edited_time", "direction": ...}`。数组第一项优先级最高（嵌套排序）。

**分页**：响应带标准分页结构（`results`、`has_more`、`next_cursor`）。⚠ 文档未明确说明 query 端点 `page_size` 的默认值是多少——通用分页说明页给出的默认是"10 条"，但未确认这条对 query a data source 是否同样适用，务必显式传 `page_size`（最大 100）而不是依赖默认值。`next_cursor` 是不透明字符串，原样传回 `start_cursor` 即可，不要解析。

## Property object：表结构里的一列长什么样

`GET /v1/data_sources/{id}` 返回的 `properties` 是 schema（列定义），和"某一页里这一列的值"是两个不同的对象（见 `references/pages-and-blocks.md` 的属性值一节）。Schema 侧同样按类型分叉，例如：

```json
"Priority": {
  "id": "abcd",
  "name": "Priority",
  "type": "select",
  "select": {
    "options": [
      { "id": "1", "name": "Low", "color": "gray" },
      { "id": "2", "name": "High", "color": "red" }
    ]
  }
}
```

`select`/`status` 的 schema 里带完整的 `options` 列表（可选项及其颜色），`multi_select` 结构类似；`relation` 的 schema 侧带 `data_source_id`（指向关联的数据源）和 `type`（`single_property`/`dual_property`，即单向还是双向关系）；`rollup` 的 schema 侧带 `relation_property_name`、`rollup_property_name`、`function`（聚合函数）。**写 schema 迁移/自省代码时，同样不能用一份通用逻辑处理所有属性类型**，这一点和页面属性值的坑是同一类问题，但发生在 schema 层。

## Relation 属性的读写不对称

`relation` 类型的 schema 和属性值里，**响应**会同时带 `database_id`（关联的数据库）和 `data_source_id`（关联的具体数据源），是为了兼容方便；但**写入/更新**（创建关联、改 relation schema）**只能传 `data_source_id`**，不再接受 `database_id`。⚠ 文档原文，未实测：具体报错行为（传 `database_id` 会不会报错还是被忽略）未验证，按官方迁移指南的措辞是"请求对象必须只包含 data_source_id"，建议当作硬性要求处理，不要心存侥幸传 `database_id`。

另外：**要让 relation 属性值不为空，必须把 relation 指向的那个数据库/数据源也共享给连接**——如果只共享了当前数据源、没共享它关联的另一个数据库，relation 属性会读到空值而不是报错（`rollup`/`formula` 同理，依赖底层 relation 的可见性）。这是"共享陷阱"在 relation 场景下的变体，排查空 relation 时要检查两侧的共享状态。

## 大数据源的完整读取

数据源里的条目数超过单次查询上限时，用标准分页循环（`has_more` + `next_cursor` → 下次请求带 `start_cursor`）。官方文档专门有一篇 `guides/data-apis/query-large-data-sources.md` 讲这个模式，核心就是"不要假设第一页就是全部数据，循环到 `has_more: false` 为止"，这里不重复展开逻辑，只提醒：**分页游标不透明，不要试图跳页或计算总数**，要知道条目总数需要自己在遍历时累加计数,官方没有提供"总数"字段。
