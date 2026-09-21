---
name: notion
description: 接入 Notion API（developers.notion.com，域名 api.notion.com）的开发者手册——涵盖鉴权（internal connection / personal access token / public OAuth connection）与"必须先在 Notion UI 里把页面共享给集成"这个最容易踩的坑、数据库(database)/数据源(data source)双层模型（2025-09-03 起的架构变更）与查询过滤排序、页面与区块(block)内容树的读写、富文本(rich text)对象格式、Search、版本化的 Notion-Version 请求头、错误码与限流、官方 JS SDK（@notionhq/client）与 Python 现状。当用户提到"Notion API""developers.notion.com""api.notion.com""@notionhq/client""notion-client""集成 token""Notion 集成""database_id""data_source_id"，或要写代码读写 Notion 页面/数据库/区块时，应主动使用本技能，不要凭训练记忆里"只有 database 和 page"的旧模型编代码——2025-09-03 版本之后 database 和 data source 是两个不同的对象，database_id 和 data_source_id 不能互换。
---

# Notion API 接入指南

Notion API（developers.notion.com）让集成读写 Notion 工作区里的页面、数据库/数据源、区块、评论、用户和文件。本 skill 覆盖为 AI Agent / 自动化脚本接入 Notion 时最核心的 7 块：鉴权与共享、数据库/数据源模型与查询、页面与区块内容树、富文本格式、Search、版本化 API 与错误/限流、SDK。目标是第一次调用就跑通，不掉进"token 完全有效但查询返回空/404""database_id 和 data_source_id 混用""把富文本当字符串拼"这几个已知的坑里。

## ⚠ 验证状态

**没有可用的真实 API Key，本 skill 全部内容来自官方文档站 (`developers.notion.com/llms.txt` + `llms-full.txt`) 与官方 OpenAPI 规范 (`developers.notion.com/openapi.json`, 抓取于 2026-09-21)，未经过一次真实 API 调用验证。** 文件里所有具体的报错文案、字段行为、"静默失效 vs 报错"的判断，全部标注为 **⚠ 文档原文，未实测**——它们可能和真实接口行为不一致（create-doc-skill 方法论本身的经验：AutoDL、智谱等平台的官方文档都发现过和真实调用不一致的地方，Notion 没有理由例外）。拿到 key 后按 `notion-workspace/verification-plan.md` 的优先级逐条实测，重点是"必须共享页面"这条 404 的真实报错文案、database→data source 发现流程的实际响应形状、以及 select/multi_select/relation 三种属性值写入后的真实回读结果。

## 用之前先确认 3 件事

1. **Base URL 固定为 `https://api.notion.com`**，所有请求路径以 `/v1/` 开头（`v1` 只是路径的一部分，不是 Notion 自己的版本控制机制——见下面第 3 点）。
2. **鉴权**：请求头 `Authorization: Bearer <TOKEN>`。当前新签发的 token 前缀是 `ntn_`（旧文档示例里仍能看到 `secret_` 前缀，是历史格式，两者都是合法的 bearer token，不要用前缀判断 token 是否有效）。**光有合法 token 不够**——集成必须先在 Notion UI 里被显式"共享"到目标页面/数据库上，否则 API 会返回该资源不存在（404），而不是权限错误，非常容易被误诊为"ID 抄错了"。这是全篇最重要的一条坑，细节见 `references/auth-and-sharing.md`。
3. **每个请求都必须带 `Notion-Version` 头**（例：`Notion-Version: 2026-03-11`），缺失会直接返回 `400 missing_version`（好消息：不是"静默降级到旧行为"，是硬报错，比很多平台友好）。但版本之间字段命名/端点路径确实会变（例如 2025-09-03 之前用 `database_id`，之后大量端点要求 `data_source_id`），所以要显式锁定版本号、有计划地升级，不要用"不传就报错所以无所谓传哪个版本"的心态。细节见 `references/errors-and-limits.md`。

## 30 秒跑通第一个请求

```bash
curl -X POST https://api.notion.com/v1/pages \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2026-03-11" \
  -H "Content-Type: application/json" \
  -d '{
    "icon": { "emoji": "🚀" },
    "markdown": "# Hello from the API\n\nThis page was created with the Notion API."
  }'
```

```python
import os, requests

resp = requests.post(
    "https://api.notion.com/v1/pages",
    headers={
        "Authorization": f"Bearer {os.environ['NOTION_API_KEY']}",
        "Notion-Version": "2026-03-11",
        "Content-Type": "application/json",
    },
    json={
        "icon": {"emoji": "🚀"},
        "markdown": "# Hello from the API\n\nThis page was created with the Notion API.",
    },
)
print(resp.json()["url"])
```

⚠ 文档原文，未实测：成功会创建一个私有页面（parent 为 `workspace`），并把 `# heading` 一行自动当作页面标题；响应对象里应有 `url` 字段可以在浏览器里打开确认。`markdown` 是请求体的一个便捷字段，服务端会把它转换成区块（block）树——这是相对新的能力，不代表区块模型被取代，见下方"跨领域通用规则"第 4 条。

## 能力域导航

| 我想做什么 | 参考文件 | 涉及的核心 endpoint |
| :--- | :--- | :--- |
| 搞清楚用哪种鉴权、以及为什么查询返回空/404（"必须先共享页面"） | [`references/auth-and-sharing.md`](references/auth-and-sharing.md) | Developer portal 创建流程、`GET /v1/users/me` |
| 理解 database vs data source 双层模型，创建/查询/过滤/排序数据 | [`references/databases-and-data-sources.md`](references/databases-and-data-sources.md) | `GET/POST/PATCH /v1/databases`、`GET/POST/PATCH /v1/data_sources`、`PATCH /v1/data_sources/{id}/query` |
| 创建/更新/检索页面，读写页面内容（区块树） | [`references/pages-and-blocks.md`](references/pages-and-blocks.md) | `POST /v1/pages`、`PATCH /v1/pages/{id}`、`GET/PATCH /v1/blocks/{id}/children`、`PATCH/DELETE /v1/blocks/{id}` |
| 给文本加粗/加颜色/加链接、处理 @提及 | [`references/rich-text.md`](references/rich-text.md) | 富文本对象是 `rich_text` 字段里的数组，不是独立 endpoint |
| 按标题搜索工作区里共享给本集成的页面/数据源 | [`references/search.md`](references/search.md) | `POST /v1/search` |
| 查报错含义、判断要不要重试、请求体/属性值的大小限制、SDK 包名 | [`references/errors-and-limits.md`](references/errors-and-limits.md) | 错误码表、限流规则、`@notionhq/client` |

## 跨领域的通用规则（写代码前必读）

1. **"token 有效"和"集成能看到这个页面/数据库"是两回事，而且失败模式是 404 不是 403。** Internal connection 和 public connection 都以独立的 bot 身份运作，必须在 Notion UI 里对每个顶层页面/数据库手动"Add connections"，子页面会继承父页面的共享（不用逐个共享子页）；**Personal access token (PAT) 是例外**——PAT 直接继承创建它的那个 Notion 用户自己的权限，不需要额外的"Add connections"步骤。Agent 写请求异常处理代码时，遇到"明明 ID 是对的却 404"，第一反应应该是检查共享状态，而不是怀疑 ID 拼错或 token 过期。详见 `references/auth-and-sharing.md`。
2. **2025-09-03 起，database 和 data source 是两个不同的对象，`database_id` 和 `data_source_id` 不能互换。** 一个 database 下面可以挂多个 data source（多源数据库），几乎所有"读写数据库行"的操作（创建页面时的 parent、查询、过滤、relation 属性）现在都要用 `data_source_id`，而不是 `database_id`。凭训练记忆写"Notion 数据库只有 database_id 一种 ID"的代码，在新数据源加入后会直接报错或查到空结果。正确流程永远是：先 `GET /v1/databases/{database_id}` 拿到 `data_sources[]` 列表（含 id 和 name），再用其中的 `data_source_id` 去查询/创建页面/建关系。详见 `references/databases-and-data-sources.md`。
3. **页面内容是区块(block)组成的树，不是一个 markdown 字符串字段——但 API 现在也提供了 markdown 便捷层，两者语义不同，不要混淆。** `POST /v1/pages` 和新增的 markdown 内容端点接受一个 `markdown` 字段/整段替换，服务端会自动转成区块；但这是"整体写入/整体替换"，不是"在某一段插入一句话"这种局部编辑——要做局部编辑（在某个区块后插入、改某一个区块的样式、挑出某个 toggle/table 精确操作）仍然要用区块级 API（`PATCH /v1/blocks/{id}/children` 追加、`PATCH /v1/blocks/{id}` 改单个区块）。判断该用哪条路径：只是要写一段新内容→markdown 更快；要做精确/增量的结构化编辑→区块 API。详见 `references/pages-and-blocks.md`。
4. **页面属性(property)值的 JSON 形状按属性类型完全不同，不能写一份通用代码处理所有属性。** `select` 的值是单个 `{id, name, color}` 对象，`multi_select` 是这种对象的数组，`relation` 是 `{id: <page_id>}` 的数组外加一个 `has_more` 标志（超过 25 条要用专门的分页端点才能拿全），`rollup`/`formula` 又是各自独立的嵌套结构。按属性类型分支处理，不要假设"反正都是往 properties 里塞一个值"。详见 `references/pages-and-blocks.md` 和 `references/databases-and-data-sources.md`。
5. **富文本(rich text)从来不是一个纯字符串，而是一个对象数组**——标题、`rich_text` 类型的属性值、大多数区块的文字内容都是这种数组，每个元素带自己的 `annotations`（加粗/斜体/颜色等）。`plain_text` 字段可以快速拿纯文本，但**写入**时必须构造完整数组，不能直接传字符串。详见 `references/rich-text.md`。
6. **`Notion-Version` 必须显式指定并锁定，不要依赖 SDK/客户端的默认值。** 版本之间存在破坏性变更（最近一次是 2025-09-03 引入 data source 模型），不同版本下同一个字段名、同一个 endpoint 路径可能不一样。省略这个头会直接 400，但传了一个过旧的版本号不会报错，只会让你继续用旧的 API 形状——升级要主动做，不会被强制推着走。
7. **分页游标 (`next_cursor`/`start_cursor`) 是不透明字符串，不要解析、校验或存储它的内部结构**，原样传回即可；同理页面/数据库自己的 `url` 字段是给人点开看的展示用链接，域名和路径格式可能变，不要当稳定标识符用——引用记录永远用 `id`。
8. **限流：普通计划 180 次/分钟，Business/Enterprise 600 次/分钟（单连接维度），另有一个跨连接共享的工作区级限流。** 遇到 429/529 要读 `Retry-After` 头等待后重试，不要固定 sleep 时长；4xx（除 429）通常是请求本身错了，重试前先改参数。详见 `references/errors-and-limits.md`。

## 目录结构

```
notion/
├── SKILL.md
├── references/
│   ├── auth-and-sharing.md              # 三种鉴权方式 + "必须共享页面给集成"的坑
│   ├── databases-and-data-sources.md    # database/data source 双层模型、创建/查询/过滤/排序
│   ├── pages-and-blocks.md              # 页面 CRUD、属性值形状、区块树读写
│   ├── rich-text.md                     # 富文本对象格式、annotations、mention
│   ├── search.md                        # 按标题搜索
│   └── errors-and-limits.md             # Notion-Version、错误码、限流、大小限制、SDK
└── evals/
    └── evals.json                       # 对照实验场景（打包时自动排除）
```

内容整理自 `developers.notion.com`（`llms.txt`/`llms-full.txt` + `openapi.json`，抓取于 2026-09-21，当时最新 API 版本为 `2026-03-11`），**未经真实 API 调用验证**。实际调用报错优先信任 API 本身的返回，而不是本 skill 里转录的文档文案；发现不一致请按 `notion-workspace/verification-plan.md` 的格式补充"已用真实 API 验证（日期）"记录并更新对应 reference。
