# 富文本(rich text)对象格式

> ⚠ 本文件内容全部来自官方文档 `reference/rich-text.md` 与 `reference/request-limits.md`，抓取于 2026-09-21，**未经真实 API 调用验证**。

## 核心事实：不是字符串，是对象数组

Notion 里任何"能被格式化的文字"——页面/数据源标题、`rich_text` 类型的属性值、大多数区块（段落、标题、列表项、to_do、callout、quote…）的文字内容——在 API 里都是**同一种富文本对象组成的数组**，不是一个普通字符串。**这是最容易被写错的地方**：Agent 训练数据里见过太多"title": "some string"这种简化写法，但 Notion API 从来不接受这种形状。

```json
[
  {
    "type": "text",
    "text": { "content": "Some words ", "link": null },
    "annotations": {
      "bold": false, "italic": false, "strikethrough": false,
      "underline": false, "code": false, "color": "default"
    },
    "plain_text": "Some words ",
    "href": null
  }
]
```

一段"看起来是一句话"的文字，在 API 里可能是**多个**富文本对象拼接而成的数组——比如一句话里一部分加粗、一部分是超链接，就要拆成 2-3 个独立元素,各自带自己的 `annotations`。**读取纯文本最简单的方式是把数组里每个元素的 `plain_text` 拼接起来**,不需要自己拼 `text.content`。

## 字段总览

| 字段 | 说明 |
| :--- | :--- |
| `type` | `"text"` / `"mention"` / `"equation"` 三选一 |
| `text` \| `mention` \| `equation` | 和 `type` 同名的那个 key 装类型专属内容（和 block 对象的设计规律一致） |
| `annotations` | 样式信息，见下 |
| `plain_text` | 纯文本,只读,不用在写入时传 |
| `href` | 链接或 Notion 内部提及的 URL,只读 |

**写入时只需要传最小必要字段**（通常是 `text.content` 和可选的 `annotations`），`plain_text`/`href` 是服务端算出来回填的,不需要（也不应该）在请求体里手写。

## annotations（样式）

```json
{
  "bold": false,
  "italic": false,
  "strikethrough": false,
  "underline": false,
  "code": false,
  "color": "default"
}
```

`color` 枚举值：`default`、`blue`、`brown`、`gray`、`green`、`orange`、`pink`、`purple`、`red`、`yellow`，以及每种颜色对应的 `<color>_background` 变体（如 `blue_background`）。**不传 `annotations` 时,写入端会用全 `false` + `default` 的默认样式**,⚠ 文档原文,未实测。

## 三种类型对象

### `text`

```json
{ "content": "inline link", "link": { "url": "https://developers.notion.com/" } }
```

- `content`：实际文字内容,`string`。
- `link`：可选,`{"url": "..."}` 表示行内超链接,没有链接时是 `null`（**不是省略这个 key**,显式传 `null`）。

### `mention`

`@` 提及,`mention.type` 决定内层结构：

| mention 类型 | 内层字段 | 说明 |
| :--- | :--- | :--- |
| `database` | `{"id": "<database_id>"}` | 提及一个数据库（不是 data source——`database mentions` 在迁移到 2025-09-03 之后**依然引用 database,不是 data source**,这是文档里明确指出的特例,和其它地方"一律换成 data_source_id"的规则不一样） |
| `page` | `{"id": "<page_id>"}` | 提及一个页面 |
| `user` | `{"object": "user", "id": "..."}` | 提及一个用户 |
| `date` | `{"start": "...", "end": null}` | 提及一个日期,形状同页面的 date 属性值 |
| `link_preview` | `{"url": "..."}` | 分享一个链接预览生成的提及 |
| `template_mention` | `{"type": "template_mention_date"\|"template_mention_user", ...}` | 模板按钮里的占位提及（"今天"/"我"）,复制模板时会被替换成真实值 |

**权限相关的静默降级**：连接没有权限看到被提及的对象时,不会报错,而是返回一个"脱敏"版本——`page`/`database` 提及只剩 `id`,`plain_text` 显示成 `"Untitled"`；`user` 提及的 `plain_text` 显示成 `"@Anonymous"`,`annotations` 用默认值。**用 `plain_text` 判断"这条提及是否有效"是不可靠的**,拿到 `"Untitled"`/`"@Anonymous"` 不代表提及对象不存在,可能只是连接没权限看,处理逻辑要能区分"真的是 Untitled 页面"和"没权限看到的页面"（⚠ 文档没有给出区分这两种情况的字段,可能需要额外用 id 单独 GET 一次来确认,未实测）。

### `equation`

```json
{ "expression": "E = mc^2" }
```

行内 LaTeX 公式,`expression` 是 LaTeX 字符串。

## 大小限制

来自 `reference/request-limits.md`：

| 限制项 | 上限 |
| :--- | :--- |
| `text.content` | 2000 字符 |
| `text.link.url` | 2000 字符 |
| `equation.expression` | 1000 字符 |
| 任意富文本对象数组（含区块/属性里的） | 100 个元素 |

超限返回 `400 validation_error`,⚠ 文档原文,未实测具体报错文案。长文本要自己在客户端按 2000 字符切成多个 `text` 元素,不能假设一个元素能装任意长度的字符串。
