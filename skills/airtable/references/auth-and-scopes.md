# 鉴权与 Scope

目录：[鉴权方式](#鉴权方式) · [个人访问令牌](#个人访问令牌-personal-access-token) · [OAuth](#oauth-集成) · [Scope 列表](#scope-列表) · [常见 403 排查](#常见-403-排查)

## 鉴权方式

Airtable 当前只支持两种鉴权方式，都通过标准的 `Authorization: Bearer <token>` 请求头传递：

- **个人访问令牌（personal access token，简称 PAT）**：面向"给自己/客户/公司写集成"的场景，token 代表创建它的那个用户账号。
- **OAuth access token**：面向"第三方服务代表其它用户访问 Airtable"的场景，用户在授权流程里自己选择要开放的 scope 和 base/workspace。

```
Authorization: Bearer YOUR_TOKEN
```

**⚠ 旧版 API key 已经彻底停用**：官方文档原文——"As of February 1st 2024, the deprecation period for Airtable API keys has ended. Users of Airtable API keys must migrate to the new authentication methods to continue using Airtable's API."（`authentication.md`，抓取于 2026-09-21）。通过遗留的 URL 参数 `api_key` 传 token 也不再支持。如果在旧教程或训练数据里看到 `?api_key=` 的写法，一律按已废弃处理。

## 个人访问令牌 (personal access token)

在 [`airtable.com/create/tokens`](https://airtable.com/create/tokens) 创建和管理。创建时需要配置两件独立的事，缺一个 API 调用都会失败：

1. **Scope**：控制这个 token 能调用哪些 endpoint（见下方列表）。
2. **Resources（base/workspace 访问权限）**：控制这个 token 能碰到哪些 base 或 workspace。可以逐个勾选，也可以授权"当前账号能访问的全部 base/workspace"；企业用户还能看到"按组织授权"的选项。

Token 本身以 `pat` 为前缀，之后的部分官方明确说是**不透明、变长的字符串**——不要依赖固定长度或格式做校验，官方表示未来改变 token 格式不算破坏性变更。Token 创建后**只显示一次**，要立刻复制保存，Airtable 自己不存储明文。可以随时改 scope/base、重新生成（旧 token 立即失效）、或删除。

**Token 的实际权限是"scope ∩ 用户本身在该 base 上的权限"的交集**：例如 token 有 `data.records:write` scope、也被授权了某个 base，但创建这个 token 的用户在该 base 只有只读权限（viewer），写操作依然会失败——因为 token 本质上是代表用户在行动，不能绕过用户自己的权限上限。

## OAuth 集成

在 [`airtable.com/create/oauth`](https://airtable.com/create/oauth) 注册集成，标准 OAuth 2.0 + PKCE 流程：

- 授权请求：`GET https://airtable.com/oauth2/v1/authorize`，必须带 `code_challenge`（PKCE，`S256` 方法）。
- 换 token：`POST https://airtable.com/oauth2/v1/token`，**必须在授权请求后 10 分钟内完成**，否则 grant code 过期。
- 生产环境使用（不只是开发调试）前，必须在集成管理页配置 Terms of Service URL、Support Email、Privacy Policy URL，否则用户授权时会收到 `access_denied`。
- Refresh token 刷新逻辑：短时间内多次刷新（官方原文：超过 10 次/秒）才会使旧 access token 失效，正常使用不受影响（2024-11-25 changelog）。

完整路由、请求参数表、错误码见官方 [`oauth-reference`](https://airtable.com/developers/web/api/oauth-reference) 页；官方提供了一个可运行的示例仓库 [`Airtable/oauth-example`](https://github.com/Airtable/oauth-example)。

## 获取当前 token 的身份和 scope

```
GET https://api.airtable.com/v0/meta/whoami
```

不需要任何 scope，任何合法 token 都能调用。返回 `id`（用户 ID）；如果 token 带 `user.email:read` scope 会额外返回 `email`；如果是 OAuth token 会额外返回它被授予的 `scopes` 数组。**排查"为什么我的 token 调不通某个接口"时，这是第一个该打的 endpoint**——用它确认 token 本身有效、以及（OAuth 场景下）到底拿到了哪些 scope。

```bash
curl "https://api.airtable.com/v0/meta/whoami" -H "Authorization: Bearer $AIRTABLE_TOKEN"
```

```json
{"id": "usrL2PNC5o3H4lBEi", "email": "foo@bar.com"}
```

## Scope 列表

Scope 决定"能调哪些 endpoint"，和 base/workspace 授权（"能碰哪些资源"）是两个独立维度，两者都要满足。下面是基础版（所有用户可用）和企业版分类：

### 基础 scope（所有用户可用）

| Scope | 用途 | 覆盖的 endpoint |
|---|---|---|
| `data.records:read` | 读记录 | List records、Get record |
| `data.records:write` | 增删改记录 | Create/Update/Delete records（单条+批量）、Sync CSV |
| `data.recordComments:read` | 读评论 | List comments |
| `data.recordComments:write` | 增删改评论 | Create/Update/Delete comment |
| `schema.bases:read` | 读 base/table 结构 | List bases、Get base schema、Get base collaborators |
| `schema.bases:write` | 改 base/table/field 结构 | Create base/table/field、Update table/field、Sync CSV |
| `workspacesAndBases:read` | 读 workspace/base/view 元数据（含协作者） | Get base collaborators、List views、Get view metadata、Get interface 等 |
| `webhook:manage` | Webhook 全套管理 | List/Create/Delete/Refresh webhook、启停通知 |
| `block:manage` | 通过 Blocks CLI 发布自定义 Extension | — |
| `user.email:read` | 在 whoami 里附带邮箱 | — |

### 企业成员 / 企业管理员 scope

企业版还有一大批 `enterprise.*` / `workspacesAndBases:write` / `workspacesAndBases:manage` / `enterprise.scim.usersAndGroups:manage` / `hyperDB.*` 等 scope，覆盖组织成员管理、SCIM、审计日志、change events、eDiscovery、HyperDB 等企业专属能力——这些不在本 skill 覆盖范围内，完整表见官方 [`scopes`](https://airtable.com/developers/web/api/scopes) 页。

## 常见 403 排查

按官方 `errors.md` 原文整理的判断顺序：

1. 先确认 token 本身有效（`whoami` 200）。
2. 确认 token 的 scope 里有这个 endpoint 要求的那个（每个 endpoint 页顶部的 "Requirements" 都写了要求的 scope，见各 reference 文件里的端点小节）。
3. 确认该 base 已经被显式加进 token 的资源列表（不是"用户有权限访问"就够，token 自己也要单独被授权）。
4. 确认创建 token 的**用户本身**对该 base/table/field 有对应的编辑权限（参考 [field/table editing permissions](https://support.airtable.com/docs/using-field-and-table-editing-permissions)）——scope 和资源授权都对，但用户自己权限不够，一样 403。
5. 企业账号特例：收到 `200 OK` 但 base 列表是空数组，通常不是 token 问题，而是企业管理员在 **Integrations and Development** 设置里开了 "Block API access to organization-owned apps & workspaces"，需要管理员调整该设置。
