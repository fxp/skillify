# 鉴权与共享

> ⚠ 本文件内容全部来自官方文档（`guides/get-started/{internal-connections,public-connections,personal-access-tokens,authorization}.md`、`reference/{authentication,capabilities}.md`），抓取于 2026-09-21，**未经真实 API 调用验证**。凡是标了"⚠ 文档原文，未实测"的报错文案，都可能和真实响应有细微出入（措辞、字段名），但已验证日期版本会覆盖它。

## 目录

- [三种鉴权方式怎么选](#三种鉴权方式怎么选)
- [Internal connection（内部集成）](#internal-connection内部集成)
- [Personal access token（PAT）](#personal-access-tokenpat)
- [Public connection（OAuth）](#public-connectionoauth)
- [★ 最容易踩的坑：集成必须被显式共享](#最容易踩的坑集成必须被显式共享)
- [Connection capabilities（能力范围）](#connection-capabilities能力范围)
- [请求头格式](#请求头格式)

## 三种鉴权方式怎么选

Notion API 的所有请求都用同一种方式携带身份：`Authorization: Bearer <TOKEN>` 请求头。但 token 背后代表"谁在操作"，三种方式差别很大：

| 方式 | Token 的身份 | 要不要额外共享页面 | 典型场景 |
| :--- | :--- | :--- | :--- |
| **Internal connection**（内部集成） | 独立的 **bot 用户**，不绑定任何具体的工作区成员 | **要**——每个顶层页面/数据库必须手动 "Add connections" | 团队自己维护的自动化：同步外部系统、发通知、跑内部看板 |
| **Personal access token (PAT)** | 就是创建这个 token 的那个 **真人用户** 自己 | **不要**——PAT 直接沿用创建者本人在 Notion 里已有的访问权限 | 个人脚本、CLI 工具、notebook、给 Agent 用的"以我的身份操作" |
| **Public connection**（OAuth） | 每个安装该连接的用户各自拥有一个 **归属于该用户** 的 access token | 不需要手动共享——用户在 OAuth 授权流程里通过"页面选择器"自己选要开放哪些页面 | 面向多个 Notion 工作区分发的产品/插件，需要上架 Marketplace 或多工作区安装 |

判断依据很简单：**只服务你自己一个人/一个脚本 → PAT**；**团队内部、由一个固定身份长期跑的自动化，需要独立于某个人存在 → Internal connection**；**要分发给别人的工作区安装、每个用户各自独立授权 → Public connection（OAuth）**。给 AI Agent 做后端自动化，最常见的是 PAT 或 Internal connection 二选一，公共 OAuth 流程只有做面向第三方分发的产品时才需要。

## Internal connection（内部集成）

- 在 Developer portal（`app.notion.com/developers/connections`）创建，创建者必须是该工作区的 **Workspace Owner**。
- 创建后立刻在 "Configuration" 标签页拿到一个静态的 **Installation access token**，每次请求都带这同一个 token，没有 OAuth 流程、没有过期刷新的概念（除非手动 revoke）。
- 以独立 **bot 用户** 的身份运作：
  - 权限属于这个连接本身，不属于任何具体的人；哪个成员点了"共享"不影响连接的访问范围。
  - 访问权限沿父子关系继承：共享了父页面，子页面自动可访问。
  - 就算共享它的那个成员离开工作区，连接的访问权限依然保留。
  - 工作区里所有 Workspace Owner 都能在 Developer portal 里看到这个连接（包括别人创建的）。

## Personal access token（PAT）

- 在 `www.notion.so/developers/tokens` 创建。创建时选：token 名称、归属工作区、能力(capability)——**Notion API** 能力和 **Workers** 能力可以分别勾选。
- Business/Enterprise 计划默认限制谁能创建 PAT，需要工作区管理员在 `Settings → Connections` 里放开。
- PAT 认证方式和其他 token 完全一样（`Authorization: Bearer <PAT>`），**但它代表创建者本人**：
  - 能访问创建者本人能访问的一切页面/数据源/评论/文件——**不需要** "Add connections" 这一步。
  - 创建者本人失去某页面的访问权，PAT 对那个页面的访问权也随之失去；创建者离开工作区，PAT 直接失效。
  - 依赖"当前用户是谁"的行为（比如 `"me"` 过滤器、创建工作区级私有页面）都按 PAT 创建者本人算。
  - ⚠ 文档原文，未实测：`GET /v1/users`（List all users）**不支持 PAT** 调用；PAT 场景下要拿当前用户信息用 `GET /v1/users/me`（Retrieve token's bot user）代替。

PAT 是"以我自己的身份调 API"最简单的方式，适合本地脚本、开发调试、以及给 Agent 用的"直接用我的 Notion 权限操作"场景——**如果这么用，不需要额外去 Notion UI 里共享任何页面**，这点和 Internal connection 正好相反，两者不要混为一谈。

## Public connection（OAuth）

- 创建时选 **installation scope**：`Any workspace`（可上架 Marketplace，任何 Notion 用户都能安装）或 `Selected workspaces only`（只有创建时指定的工作区能安装，不能上架）。这个选择创建后不能改，选错了要建一个新连接。
- 和 Internal connection 的关键区别：
  - **身份**：以 **安装/授权它的那个具体用户** 的身份运作，token 归属这个人，不是独立 bot。
  - **页面授权方式**：不需要用户手动去每个页面点 "Add connections"，而是在 OAuth 授权流程里弹出 **页面选择器 (page picker)**，用户当场勾选要开放哪些页面。
- OAuth 2.0 标准流程：
  1. 用户访问连接的 authorization URL（在 Developer portal 的 Configuration 标签页拿到）。
  2. Notion 展示这个连接申请的能力(capabilities)列表，用户确认。
  3. 用户在页面选择器里勾选要授权访问的页面。
  4. 用户批准后，Notion 重定向到你配置的 redirect URI，带一个临时 `code`。
  5. 用这个 `code` 换 access token：`POST https://api.notion.com/v1/oauth/token`，用 **HTTP Basic Auth**（`client_id:client_secret` base64 编码）而不是 Bearer token 做这一次请求本身的鉴权，body 里带 `grant_type=authorization_code`、`code`、`redirect_uri`。
  6. 拿到的 `access_token` 之后按普通 Bearer token 用。
- 相关端点（`reference/create-a-token.md`、`introspect-token.md`、`revoke-token.md`、`refresh-a-token.md`）：创建/检查/撤销/刷新 token，⚠ 文档原文，未实测，具体参数以 `openapi-summary/OAuth.md` 为准。

给 AI Agent 场景基本用不到公共 OAuth（那是给"分发产品"用的），了解结构即可，不展开每个端点。

## ★ 最容易踩的坑：集成必须被显式共享

**这是整个 Notion API 接入过程里最容易让人卡住、也最难自己诊断出来的一步——尤其是 Internal connection 和 Public connection。**

具体表现：token 完全合法、格式完全正确、`Notion-Version` 头也带了，请求一个明明存在的页面/数据库 ID，得到的不是"权限不足"的 403，而是 **404 `object_not_found`**——看起来像是"这个资源根本不存在"，第一反应容易去怀疑 ID 抄错了、UUID 少了个连字符，但真正原因往往是：这个页面/数据库从来没有在 Notion UI 里被共享给这个集成。

⚠ 文档原文，未实测——官方文档给出的报错文案示例：

```json
{
  "object": "error",
  "status": 404,
  "code": "object_not_found",
  "message": "Could not find database with ID: be907abe-510e-4116-a3d1-7ea71018c06f. Make sure the relevant pages and databases are shared with your connection \"My Connection\"."
}
```

注意 `message` 里其实已经点出了原因（"确认相关页面和数据库已经共享给你的连接"），只是这段提示很容易在只看 `status`/`code` 做分支处理的代码里被忽略掉。

**怎么共享**：在 Notion 应用里打开目标页面，点右上角 `•••` 菜单，找到 `Add connections`，用搜索框找到并选中目标连接。共享一个页面会让该连接同时能访问它的所有子页面（继承），**但不会反向影响它的父页面或同级页面**——所以共享要在你实际要操作的内容树的最上层节点做一次，而不是每个子页面都手动共享一遍。**数据库同理**：要查询一个 database/data source，必须共享的是它所在的那个页面或数据库本身。

**给 Agent 写错误处理代码时的正确心智模型**：

1. 收到 404 `object_not_found`，且能确认 ID 格式本身没问题（是合法 UUID）时，**先假设是没共享，而不是先假设 ID 错了**——尤其是当这个 ID 是用户直接提供、或者是从 Notion UI 复制的链接里解析出来的。
2. 排查路径：确认使用的是哪种鉴权方式——如果是 **PAT**，共享步骤不适用，应该检查创建 PAT 的那个用户本人是否真的能在 Notion App 里看到这个页面；如果是 **Internal/Public connection**，才去检查 "Add connections" 列表里是否包含这个连接。
3. `Search`（`POST /v1/search`）只会返回"共享给当前连接"的内容——如果 Search 结果里看不到某个页面，同样大概率是没共享，而不是 Search 参数写错了（见 `references/search.md`）。

## Connection capabilities（能力范围）

除了"有没有被共享"，每个连接/PAT 还有独立的 **capabilities** 控制它能做什么操作，在 Developer portal（连接）或创建 PAT 时（PAT）配置：

| 类别 | 选项 | 影响 |
| :--- | :--- | :--- |
| Content | Read content | 能读已有内容（如 Retrieve database），不能写 |
| Content | Update content | 能改已有内容（如 Update page），不能新建 |
| Content | Insert content | 能新建内容（如 Create page），不能改已有内容，也不能完整读取对象 |
| Comments | Read comments | 能读评论 |
| Comments | Insert comments | 能发评论 |
| User information | No user information / Without email / With email | 控制 User 对象里返回多少信息 |

三个 Content 能力可以任意组合。**权限最小化原则**：只导入内容的连接只要 Insert；只导出/只读的连接只要 Read；只改属性/勾选框的连接只要 Update。公共连接申请的能力越少，工作区管理员越容易通过安装审批。

一个连接被授予访问某个页面后，它能读写该页面 **和它的所有子内容**（子页面、子数据库等）——这点和上面"共享会向子级继承"是一致的。

## 请求头格式

```
Authorization: Bearer ntn_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
Notion-Version: 2026-03-11
Content-Type: application/json
```

- 新签发的 token 前缀是 `ntn_`；旧文档示例、早期签发的 token 会看到 `secret_` 前缀——**两种前缀都是合法 token**，不要用前缀做校验或分支判断。
- `Notion-Version` 必须每次都带，见 `references/errors-and-limits.md`。
- Key 只放环境变量，绝不写进代码或提交到版本控制——官方文档专门有一节 `guides/get-started/handling-api-keys.md` 强调这点。
