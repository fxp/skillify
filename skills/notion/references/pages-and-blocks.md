# 页面(page)与区块(block)内容

> ⚠ 本文件内容全部来自官方文档（`guides/data-apis/working-with-page-content.md`、`reference/{page,block,page-property-values,property-item-object,post-page,retrieve-a-page,patch-page,move-page,trash-page,patch-block-children,retrieve-a-block,get-block-children,update-a-block,delete-a-block}.md`）与 OpenAPI 规范，抓取于 2026-09-21，**未经真实 API 调用验证**。

## 目录

- [属性(properties) vs 内容(content)：先分清这两个概念](#属性properties-vs-内容content先分清这两个概念)
- [Page 对象](#page-对象)
- [创建页面](#创建页面)
- [检索/更新/移动/清除页面](#检索更新移动清除页面)
- [★ 页面属性值：按类型分叉，不要写通用代码](#页面属性值按类型分叉不要写通用代码)
- [Block 对象与内容树](#block-对象与内容树)
- [读取页面内容（区块树）](#读取页面内容区块树)
- [写入/修改页面内容（区块级操作）](#写入修改页面内容区块级操作)
- [Enhanced Markdown：便捷层，不是区块模型的替代品](#enhanced-markdown便捷层不是区块模型的替代品)

## 属性(properties) vs 内容(content)：先分清这两个概念

Notion 页面有两类完全不同的数据，写代码前先分清楚往哪边放：

- **Properties（属性）**：结构化字段，比如截止日期、分类、关联的另一个页面——对应数据源 schema 里定义的"列"。只有 **数据源里的页面** 才有除 `title` 之外的属性；独立页面（parent 是另一个页面或 workspace）只有 `title` 一个属性。
- **Content（内容）**：页面正文，自由格式的文字、列表、图片等——由一棵 **区块(block)树** 表示，和属性是完全独立的两套数据、两套 API。

一个常见的错误心智模型是"更新页面文本"应该对应一次简单的字段写入——**实际上"改标题"（属性）和"改正文"（内容）走的是两条完全不同的路径**，标题走 `PATCH /v1/pages/{id}` 的 `properties.title`，正文走区块级 API 或下面的 markdown 便捷层。

## Page 对象

| 字段 | 说明 |
| :--- | :--- |
| `object` | 固定 `"page"` |
| `id` | UUID |
| `parent` | `{"type": "workspace", "workspace": true}` / `{"type": "page_id", "page_id": "..."}` / `{"type": "data_source_id", "data_source_id": "...", "database_id": "..."}`（数据库场景下，`database_id` 是响应里附带的便利字段） / `{"type": "block_id", "block_id": "..."}` |
| `properties` | 见下方"页面属性值"一节；独立页面只有 `title` 一个 key |
| `icon` / `cover` | Emoji / 外部或上传的文件 / 自定义 emoji |
| `url` | 给人点开看的展示链接，**不是稳定标识符**，域名/路径格式可能变（例如文档提到 2026-06 从 `notion.so/{id}` 迁移到 `app.notion.com/p/{id}`），引用页面永远用 `id` |
| `public_url` | 页面公开分享时的链接，未公开分享为 `null` |
| `in_trash` | 是否在回收站；`archived` 字段 **自 API 版本 `2026-03-11` 起已被移除**，只认 `in_trash`（低于此版本仍可能返回/接受 `archived` 作为别名，⚠ 文档原文，未实测，按当前版本写代码就不要再用 `archived`） |

## 创建页面

`POST /v1/pages`，`parent` 三选一：

```json
// 挂在数据源下（最常见——相当于"在这个数据库里新建一行"）
{ "parent": { "type": "data_source_id", "data_source_id": "..." }, "properties": { ... } }

// 挂在另一个页面下
{ "parent": { "type": "page_id", "page_id": "..." }, "properties": { "title": [...] } }

// 挂在工作区顶层（新建一个独立私有页面）
{ "parent": { "type": "workspace", "workspace": true }, "properties": { "title": [...] } }
```

**⚠ 训练记忆里最容易写错的一点**：数据库场景下 `parent.database_id` 已经不是当前版本接受的形状——必须是 `parent.data_source_id`（见 `references/databases-and-data-sources.md` 的发现流程）。

正文内容有两种写法，二选一（也可以都传，但没必要）：

1. **`children`**：区块对象数组，精确控制每个区块的类型和样式。
2. **`markdown`**：一段 Notion 风味 Markdown 字符串，服务端自动转换成区块树（见文末"Enhanced Markdown"一节）。

```json
{
  "parent": { "type": "data_source_id", "data_source_id": "..." },
  "properties": { "Name": { "title": [{ "text": { "content": "New task" } }] } },
  "children": [
    {
      "object": "block",
      "type": "paragraph",
      "paragraph": { "rich_text": [{ "text": { "content": "First line." } }] }
    }
  ]
}
```

## 检索/更新/移动/清除页面

| 操作 | Endpoint | 要点 |
| :--- | :--- | :--- |
| 检索页面 | `GET /v1/pages/{page_id}` | 只返回属性 + 元数据，**不含内容**；`relation`/`people`/`rich_text`/`title` 类属性超过 25 个元素时只返回前 25 个并标 `has_more: true`，要拿全量用下面的"检索页面属性项" |
| 检索单个属性项（分页） | `GET /v1/pages/{page_id}/properties/{property_id}` | 用于 `relation`/`people`/`rich_text`/`title` 超过 25 项、或 `rollup` 聚合值的完整分页读取；`property_id` 从数据源 schema 里的 `properties.<name>.id` 拿 |
| 更新页面 | `PATCH /v1/pages/{page_id}` | 能改：`properties`、`icon`、`cover`、`in_trash`（trash/restore）。**不能改内容**——不接受 `children` |
| 移动页面 | `POST /v1/pages/{page_id}/move`（⚠ 文档原文，未实测，路径以 OpenAPI 规范为准） | 把页面移到新的 `parent`；仅支持"常规页面"，不支持移动数据库；bot 必须对新 parent 有编辑权限 |
| 清除（trash）页面 | `PATCH /v1/pages/{page_id}` body `{"in_trash": true}` | API **不支持永久删除**页面，只能移进回收站；恢复用同一端点传 `in_trash: false` |

## ★ 页面属性值：按类型分叉，不要写通用代码

`properties` 对象里，每个 key 是属性名，value 的形状完全由 `type` 决定——这是文档里最容易被写成"一份通用序列化逻辑"、但实际必须按类型分支的地方：

| 类型 | 写入时传什么 | 读取时长什么样（简化） |
| :--- | :--- | :--- |
| `title` / `rich_text` | 富文本对象数组（见 `references/rich-text.md`） | 同左，外加 `id` |
| `select` | `{"select": {"name": "Marketing"}}`（或用 `id` 代替 `name`） | `{"select": {"id": "...", "name": "...", "color": "..."}}`——**单个对象**，不是数组 |
| `multi_select` | `{"multi_select": [{"name": "A"}, {"name": "B"}]}` | `{"multi_select": [{"id","name","color"}, ...]}`——对象**数组** |
| `relation` | `{"relation": [{"id": "<page_id>"}, ...]}` | 同左 + `has_more`（超过 25 条为 `true`，要读全量走属性项分页端点） |
| `rollup` | 不可直接写（由源属性和聚合函数计算得出） | 依聚合类型不同（`number`/`date`/`array` 等），形状不统一 |
| `number` | `{"number": 42}` | 同左 |
| `checkbox` | `{"checkbox": true}` | 同左 |
| `date` | `{"date": {"start": "2026-01-01", "end": null}}` | 同左 |
| `people` | `{"people": [{"object": "user", "id": "..."}]}` | 同左，超过 25 条同样要走属性项分页 |
| `url` / `email` / `phone_number` | `{"url": "https://..."}` 等 | 同左；**Notion API 不支持空字符串**，要清空这些字段传显式 `null`，不要传 `""` |
| `files` | `{"files": [{"name": "...", "external": {"url": "..."}}]}` 或 `file_upload` 引用 | 类似，见 `guides/data-apis/working-with-files-and-media.md`（本 skill 不深入展开文件上传，超出范围） |
| `status` | `{"status": {"name": "In progress"}}` | 单对象，形状类似 `select` |
| `unique_id` | 只读，不能写 | `{"unique_id": {"prefix": "TASK", "number": 42}}` |
| `formula` / `verification` / `created_by` / `created_time` / `last_edited_by` / `last_edited_time` | 只读，不能写 | 各自独立形状 |

**给新增可选项的属性(`select`/`multi_select`/`status`)传一个之前不存在的 `name` 时，如果连接对该数据源有写权限，Notion 会自动把这个新选项加进 schema**——这是"隐式写 schema"的行为，写自动化代码时如果不希望意外扩张下拉选项列表，要先校验传入的 `name` 是否已经在已知选项集合里，而不是无脑透传用户输入。

`select`/`multi_select` 的值里 **`color` 字段不能通过 API 更新**（新建选项会有默认颜色分配，但不能指定颜色，也不能改已有选项的颜色）。⚠ 文档原文，未实测。

## Block 对象与内容树

一个区块对象的通用形状：

```json
{
  "object": "block",
  "id": "c02fc1d3-...",
  "parent": { "type": "page_id", "page_id": "..." },
  "type": "heading_2",
  "has_children": false,
  "in_trash": false,
  "created_time": "...", "created_by": {...},
  "last_edited_time": "...", "last_edited_by": {...},
  "heading_2": {
    "rich_text": [ /* 富文本数组 */ ],
    "color": "default",
    "is_toggleable": false
  }
}
```

**规律**：`type` 字段说明这是什么类型的区块，真正的内容永远嵌在和 `type` 同名的那个 key 下面（`heading_2` 类型的区块，内容在 `block["heading_2"]` 里）——这和页面属性值"外层 `type`，内层同名 key 装值"是同一套设计模式。

已知的区块 `type` 枚举（部分，完整列表见 `reference/block.md`）：`paragraph`、`heading_1/2/3/4`、`bulleted_list_item`、`numbered_list_item`、`to_do`、`toggle`、`quote`、`callout`、`code`、`divider`、`table_of_contents`、`breadcrumb`、`bookmark`、`embed`、`equation`、`file`/`image`/`pdf`/`video`、`link_preview`、`synced_block`、`table`/`table_row`、`column_list`/`column`、`child_page`/`child_database`、`template`、`transcription`、`unsupported`（服务端无法通过 API 表达的区块类型，只读，占位用）。

**支持子区块(children)的类型**（不完整列表，来自文档）：`bulleted_list_item`、`numbered_list_item`、`to_do`、`toggle`、`callout`、`quote`、`paragraph`（可以有缩进子内容）、`table`（子级是 `table_row`）、`column_list`（子级是 `column`）、`synced_block`、`child_page`、`child_database`。

**更新 `child_page`/`child_database` 类型的区块要走别的端点**：改 `child_page` 区块显示的文字，实际是改对应 **页面** 的 `title` 属性（`PATCH /v1/pages/{page_id}`），不是改区块本身；`child_database` 同理，走 `PATCH /v1/databases/{database_id}` 改数据库的 `title`。直接对这两种区块调用"更新区块"端点不会生效。

## 读取页面内容（区块树）

页面本身也是一个"块"，页面 ID 可以直接当 `block_id` 用来拿它的直接子内容：

```bash
curl "https://api.notion.com/v1/blocks/$PAGE_ID/children?page_size=100" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2026-03-11"
```

**关键点：这只返回第一层子区块。** 如果某个区块的 `has_children: true`（比如一个 toggle、一个缩进段落、一个 table），要拿到它内部的内容必须对**那个区块自己的 id** 再发一次 `GET /v1/blocks/{block_id}/children` 请求——想要完整还原一个页面的内容树，需要递归遍历所有 `has_children: true` 的节点,官方文档原话就是"可能需要递归检索子区块的子区块才能拿到完整表示"。这不是可选的优化，是拿到完整内容的唯一方式。

## 写入/修改页面内容（区块级操作）

| 操作 | Endpoint | 关键限制 |
| :--- | :--- | :--- |
| 追加子区块 | `PATCH /v1/blocks/{block_id}/children` | 单次请求最多 **100 个** 顶层子区块；允许子区块自带 **最多两层** 嵌套；用 `position` 控制插入位置（`{"type":"end"}` 默认追加到末尾 / `{"type":"start"}` 插入到最前 / `{"type":"after_block","after_block":{"id":"..."}}` 插入到指定区块之后——旧的 `after` 参数已废弃，不要新代码里再用）；**已追加的区块之后不能再用这个 API 挪动位置** |
| 检索单个区块 | `GET /v1/blocks/{block_id}` | 返回该区块自身,不含子级 |
| 更新区块 | `PATCH /v1/blocks/{block_id}` | 按区块类型传对应字段（如 `to_do` 传 `{"to_do": {"checked": true}}`）；**是整字段替换，不是合并**——传了某个字段就整体覆盖，不传的字段维持原样；`in_trash: true/false` 可以在这个端点里 trash/restore 单个区块；**不能**通过这个端点改子区块列表,加子区块必须用"追加子区块" |
| 删除（trash）区块 | `DELETE /v1/blocks/{block_id}` | 实际效果是把 `in_trash` 置为 `true`（软删除，进 Notion 回收站，可恢复），**不是真正物理删除**；恢复用"更新区块"或"更新页面"把 `in_trash` 改回 `false` |

三个端点分工：**追加用 `PATCH .../children`，改一个已存在区块自己的内容/样式用 `PATCH /v1/blocks/{id}`，去掉一个区块用 `DELETE /v1/blocks/{id}`（软删除）**。没有"替换某个区块及其所有子级"这种单步操作，要整体换掉一段内容,通常是先删旧区块再追加新的。

追加子区块示例（在页面末尾加一段文字）：

```python
import os, requests

requests.patch(
    f"https://api.notion.com/v1/blocks/{page_id}/children",
    headers={
        "Authorization": f"Bearer {os.environ['NOTION_API_KEY']}",
        "Notion-Version": "2026-03-11",
    },
    json={
        "children": [{
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": "New line."}}]},
        }]
    },
)
```

## Enhanced Markdown：便捷层，不是区块模型的替代品

除了 `children` 区块数组，创建/更新页面内容还有一层新增的 **enhanced markdown** 便捷 API（`guides/data-apis/{working-with-markdown-content,enhanced-markdown}.md`），⚠ 文档原文，未实测：

- `POST /v1/pages` 的 `markdown` 字段：整段 Notion 风味 Markdown，服务端转换成区块树,替代手写 `children`。
- `GET /v1/pages/{page_id}/markdown`（Retrieve a page as markdown，具体路径以 OpenAPI 为准）：把页面内容渲染回 markdown 字符串读取。
- `PATCH /v1/pages/{page_id}/markdown`（Update a page's content as markdown）：用一段新的 markdown **插入或替换** 页面内容。

**这不是"块模型被废弃了"，是多了一条更省事的路,两者语义不同**：

- Markdown 层的写操作是"整体替换/整体插入",不是"改某一句话"这种细粒度局部编辑;要精确控制某个区块的颜色、要用只有区块 API 才有的类型(比如 `synced_block`、`column_list` 分栏)、要在文档中间某个精确位置做增量修改,仍然要用区块级 `children`/`update block` API。
- 需要"读一段现有内容、只改其中一部分、写回去"这种场景,用 markdown 层意味着要处理整段文本的 diff/替换逻辑,往往不如直接定位到具体区块调用区块级 API 精确。
- 简单场景(新建一个页面并写入一段说明性文字、追加一段总结)用 `markdown` 更快更少出错,复杂场景(构建有嵌套结构、多种区块类型混排的内容)仍建议用 `children`。

选择原则：**"整体写一段新内容"倾向 markdown,"对已有结构做精确的局部编辑"倾向区块 API**,两者可以在同一个连接里按场景混用,不互斥。
