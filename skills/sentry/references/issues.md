# Issue 查询与管理（Web API）

> ⚠ 全部内容来自 `docs.sentry.io/concepts/search.md`、`docs.sentry.io/concepts/search/searchable-properties/issues.md` 及 `openapi-derefed.json` 转录，未经真实调用验证。Base URL 统一为 `https://{region}.sentry.io`，鉴权 `Authorization: Bearer <token>`（见 `auth-and-tokens.md`）。

## 目录

- [先搞清楚：Issue 是什么](#先搞清楚issue-是什么)
- [Issue 搜索语法（Sentry 自己的 DSL）](#issue-搜索语法sentry-自己的-dsl)
- [可搜索字段速查](#可搜索字段速查)
- [列出 Issue](#列出-issue)
- [单个 Issue 详情](#单个-issue-详情)
- [更新 Issue（resolve / ignore / assign / merge…）](#更新-issueresolve--ignore--assign--merge)
- [批量更新 / 批量删除 Issue](#批量更新--批量删除-issue)
- [Issue 的 Tag 值](#issue-的-tag-值)
- [Seer 自动修复（实验性,AI 相关)](#seer-自动修复实验性ai-相关)

## 先搞清楚：Issue 是什么

**Issue 是"一组相似错误事件的聚合"，不是单次报错本身。** Sentry 用事件的"指纹"（fingerprint，通常由异常类型+堆栈帧等特征自动计算）把相似的 event 分到同一个 issue 下。所以：

- "看这个错误发生了多少次" → 看 issue 的 `count`/`timesSeen` 字段，不是数 event 列表长度（虽然也能数，但字段更直接）。
- "看这个错误的完整堆栈跟踪" → issue 详情里**没有**堆栈跟踪，必须再调一次拿具体 event（见 `events.md`），issue 只给"最近一次事件的摘要"。
- 每个 issue 有两种 ID：数字 `issue_id`（API 路径用这个）和人类可读的 `shortId`（如 `MYPROJ-1A2`，UI 上显示、告警通知里用这个）。两者能互相转换：`GET /api/0/organizations/{org}/shortids/{issue_id}/` 按 short ID 反查（见 `organizations-and-projects.md`）。

## Issue 搜索语法（Sentry 自己的 DSL）

**不是关键词全文搜索，是 `key:value` token 组合。** 来自 `docs.sentry.io/concepts/search.md`：

```
is:resolved user.username:"Jane Doe" server:web-8 example error
```

拆成 4 个 token：`is:resolved`、`user.username:"Jane Doe"`、`server:web-8`（自定义 tag）、`example error`（裸文本，按标题/消息子串匹配，只能有一段裸文本，且必须是整段字符串）。

**语法要点**：

| 语法 | 说明 | 示例 |
| :--- | :--- | :--- |
| 比较操作符 | 数值/时间类字段支持 `>` `<` `>=` `<=` | `count():>100`（注意这是聚合函数，issue 搜索本身较少用）、`event.timestamp:>2023-09-28T00:00:00-07:00` |
| 相对时间 | `age`/`firstSeen`/`lastSeen` 等用 Unix `find` 风格：`m`/`h`/`d`/`w` 后缀 | `age:-24h`（24 小时内新增）、`age:+12h age:-24h`（12~24 小时前新增，两个 token 是 AND 关系） |
| 多值列表 | `key:[v1, v2]` 等价于 `key:v1 OR key:v2` | `release:[12.0, 13.0]`；**`is:` 和通配符不支持这个语法** |
| 排除 | `!` 前缀取反 | `is:unresolved !user.email:example@customer.com` |
| 通配符 | `*` 占位 | `browser:"Safari 11*"`、`!message:"*Timeout"` |
| 显式 tag 语法 | 自定义 tag 撞了保留关键字名（如 `project_id`）时用 | `tags[project_id]:tag_value` |
| `AND`/`OR`/括号 | **issue 搜索本身不支持**，只在 Explore/Dashboards/Monitors 里可用 | — |

**默认查询是 `is:unresolved`**——不传 `query` 参数时会隐式加这个过滤,拿"全部 issue"（包括已解决/已忽略）要显式传 `query=`（空字符串)。

## 可搜索字段速查

节选自 `docs.sentry.io/concepts/search/searchable-properties/issues.md`（完整列表在官方文档，这里挑了 issue 场景最常用的）：

| 字段 | 说明 | 类型 |
| :--- | :--- | :--- |
| `is` | 状态：`unresolved`/`resolved`/`archived`/`assigned`/`unassigned`/`for_review`/`linked`/`unlinked` | status |
| `assigned` | 分派给谁：邮箱、`me`、`none`、`my_teams`、`#team-name` | team or org user |
| `assigned_or_suggested` | 分派或"建议分派"（按 ownership rule / suspect commit 推断） | team or org user |
| `age` | 相对创建时间，如 `age:-24h` | relative time |
| `firstSeen` / `lastSeen` | 首次/末次出现时间，语法同 `age` | datetime |
| `issue` | short ID，如 `issue:SENTRY-ABC` | string |
| `issue.category` | `error`/`performance`/`frontend`/`outage` 等 | string |
| `issue.type` | 更细的类型,如 `issue.type:performance_n_plus_one_db_queries` | string |
| `level` | `fatal`/`error`/`warning`/`info`/`debug` | string |
| `error.type` / `error.value` | 异常类名 / 异常信息原文 | array |
| `error.handled` / `error.unhandled` | 是否被 try/catch 捕获 | boolean |
| `release` / `release.version` / `firstRelease` | 关联 release,`firstRelease:latest` 取最新 release | string/datetime |
| `assigned`/`bookmarks` | 值可以是 `me` | — |
| `has` | 存在某个字段/tag（不管值），如 `has:user` | — |
| `timesSeen` | 出现次数(同 event 侧的 `count()`) | number |
| `platform.name` | SDK 平台标识 | string |

**易错点**：`is:` 的合法值列表是固定枚举（见上表），传别的值大概率被忽略或报错，⚠ 文档原文，未实测具体行为（静默失效还是报错,按 verify.md 的方法论这正是最该优先测的一类)。

## 列出 Issue

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/issues/`
**用途**: 组织范围内查询 issue,**这是当前推荐的 issue 列表 endpoint**（项目级的 `GET /api/0/projects/{org}/{project}/issues/` 已被文档标注为 Deprecated,建议改用这个 + `project` 参数过滤)。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `project` | array<int\|string> | 否 | 项目 ID/slug 过滤,可多个,`-1` 表示全部可访问项目,不传也是全部 |
| `query` | string | 否 | 见上面的搜索 DSL,不传时隐式 `is:unresolved` |
| `environment` | array<string> | 否 | 按 environment 过滤 |
| `statsPeriod` | string | 否 | `24h`/`14d` 等,和 `start`/`end` 二选一 |
| `sort` | string | 否 | `date`(默认,Last Seen)/`new`/`trends`/`freq`/`user`/`inbox`/`recommended` |
| `limit` | integer | 否 | 最大 100 |
| `shortIdLookup` | `0`/`1` | 否 | 传 `1` 时 `query` 里出现的 short ID 会被单独解析 |
| `expand` | array<string> | 否 | 附加返回数据 |
| `collapse` | array<string> | 否 | 从响应里剔除某些字段以提速 |
| `cursor` | string | 否 | 分页游标 |

**示例请求**

```bash
curl -s "https://us.sentry.io/api/0/organizations/acme/issues/?project=1234&query=is%3Aunresolved+age%3A-24h&sort=freq&limit=25" \
  -H "Authorization: Bearer $SENTRY_AUTH_TOKEN"
```

**示例响应（关键字段,精简)**

```json
[
  {
    "id": "123456",
    "shortId": "MYPROJ-1A2",
    "title": "ZeroDivisionError: division by zero",
    "culprit": "myapp.views.checkout in process",
    "level": "error",
    "status": "unresolved",
    "substatus": "ongoing",
    "priority": "high",
    "count": "42",
    "userCount": 7,
    "firstSeen": "2026-09-15T10:00:00Z",
    "lastSeen": "2026-09-21T08:00:00Z",
    "project": {"id": "1234", "slug": "my-service"},
    "assignedTo": null,
    "permalink": "https://acme.sentry.io/issues/123456/"
  }
]
```

**注意事项**

- `status` 枚举:`resolved`/`ignored`/`pending_deletion`/`pending_merge`/`reprocessing`/`unresolved`;`substatus` 是更细的子状态(`archived_until_escalating`/`escalating`/`regressed`/`new` 等),两个字段都要看才能准确判断"这个 issue 现在到底是什么状态"。
- `priority` 是 Sentry 自动/手动打的优先级(`low`/`medium`/`high`),和 `level`(事件严重级别,如 fatal/error/warning)是两个不同维度,别混。
- 响应带 `seerFixabilityScore`/`seerAutofixLastTriggered` 等字段,是 Seer AI 分析结果的附带信息,见下文"Seer 自动修复"。

## 单个 Issue 详情

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/issues/{issue_id}/`
**用途**: 单个 issue 的详情,包含评论数、用户反馈数、`derivedData`(Seer 分析出来的进度状态,如 `hasOpenFixPr`/`hasRootCause`)。**仍然不含堆栈跟踪**——要看堆栈跟踪必须转到 `events.md` 里"取一个具体 event"的 endpoint。

**参数**:`environment`(过滤)、`expand`/`collapse`(同上)。`issue_id` 既可以是数字 ID,也支持 short ID(⚠ 文档未明确说明是否两种都直接支持,规范里字段类型是 string,若传 short ID 报错,退回先用 `shortids` 反查)。

## 更新 Issue（resolve / ignore / assign / merge…）

**Endpoint**: `PUT /api/0/organizations/{organization_id_or_slug}/issues/{issue_id}/`
**用途**: 单个 issue 的属性更新,**只更新传了的字段**。这是"resolve 一个 issue"的核心 endpoint。

**关键请求体字段**

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `status` | enum | `resolved`/`unresolved`/`ignored`/`resolvedInNextRelease`/`muted` |
| `statusDetails.inRelease` | string | 标记"在这个 release 里已解决";传 `latest` 用最新 release |
| `statusDetails.inNextRelease` | boolean | 标记"下一个 release 解决" |
| `statusDetails.inCommit.commit`/`.repository` | string | 标记"这次 commit 解决" |
| `statusDetails.ignoreDuration`/`ignoreCount`/`ignoreWindow`/`ignoreUserCount`/`ignoreUserWindow` | integer | ignore 的各种条件(时长/次数窗口/影响用户数窗口,窗口类最大 7 天) |
| `assignedTo` | string | `<user_id>`、`user:<user_id>`、`<username>`、`<email>`、或 `team:<team_id>` |
| `priority` | enum | `low`/`medium`/`high` |
| `merge` | boolean | 合并 issue(和批量接口配合用,单个 PUT 里语义是"把这个 issue 标记参与合并") |
| `isPublic` | boolean | 公开分享开关 |
| `isBookmarked`/`isSubscribed`/`hasSeen` | boolean | 用户级标记(收藏/订阅/已读) |

**示例请求(resolve 一个 issue)**

```bash
curl -s -X PUT "https://us.sentry.io/api/0/organizations/acme/issues/123456/" \
  -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "resolved"}'
```

**示例请求(分派给某人)**

```bash
curl -s -X PUT "https://us.sentry.io/api/0/organizations/acme/issues/123456/" \
  -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"assignedTo": "jane@example.com"}'
```

**Endpoint**: `DELETE /api/0/organizations/{organization_id_or_slug}/issues/{issue_id}/`——异步删除,响应 `202 Accepted`(排队删除,不是立即完成,⚠ 文档未说明如何轮询确认删除完成)。

需要的 scope:更新是 `event:write`,删除是 `event:admin`(见 `auth-and-tokens.md` 的 scope 表)。

## 批量更新 / 批量删除 Issue

**Endpoint**: `PUT /api/0/organizations/{organization_id_or_slug}/issues/`
**用途**: 一次改最多 **1000 个** issue。请求体结构和单个更新的 `PUT .../{issue_id}/` 基本一致(`status`/`assignedTo`/`priority`/`merge`/`discard` 等)。

**关键点**:
- **非状态类更新必须带 `id` query 参数**(重复传,如 `?id=1&id=2`)。
- **状态类更新可以不传 `id`**——此时隐式"更新全部匹配 `query` 过滤条件的 issue"(批量 resolve 一整批搜索结果时用这个,但要小心"忘了加过滤条件=改了一大批不想改的 issue")。
- 部分 ID 不在权限范围内时,**不报错**,只是那部分不生效,响应仍是成功(⚠ 文档原文,未实测,这是典型的"静默部分失败",用之前要考虑清楚要不要自己二次校验结果)。
- 没有任何 issue 匹配条件时返回 `204 No Content`。

**Endpoint**: `DELETE /api/0/organizations/{organization_id_or_slug}/issues/`——批量永久删除。**如果传了 `id`,会忽略 `query` 过滤条件**;不传 `id` 时尝试删除前 1000 个匹配的 issue。**这是破坏性操作且是批量的,写自动化脚本时要格外小心不要在没有精确 `id` 列表的情况下裸调这个 endpoint。**

## Issue 的 Tag 值

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/issues/{issue_id}/tags/{key}/values/`
**用途**: 查某个 tag(如 `browser`、`release`、自定义业务 tag)在这个 issue 下都出现过哪些值,附带每个值的 `count`/`lastSeen`/`firstSeen`。用于"这个错误主要发生在哪些浏览器/版本上"这类聚合分析,不需要拉全部 event 自己统计。

## Seer 自动修复（实验性,AI 相关)

对"AI agent 管理错误追踪数据"这个场景直接相关:Sentry 自带一个叫 **Seer** 的 AI 根因分析/自动修复功能,可以通过 API 触发。**官方标注为 Experimental,API 可能变动**。

**Endpoint**: `POST /api/0/organizations/{organization_id_or_slug}/issues/{issue_id}/autofix/`
**用途**: 触发 Seer 对一个 issue 做根因分析 → 提出方案 → 生成代码改动 → 开 PR,异步执行。

**关键请求体字段**

| 字段 | 说明 |
| :--- | :--- |
| `step` | 跑到哪一步:`root_cause`(默认)/`solution`/`code_changes`/`pr_iteration`/`open_pr`/`coding_agent_handoff` |
| `stopping_point` | 停在哪一步,不传则只跑到 `root_cause` |
| `sentry_run_id` | 继续一个已有的 run(UUID,优先于已废弃的 `run_id`) |
| `repo_name` | 指定在哪个仓库开 PR,不传则所有相关仓库都尝试 |

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/issues/{issue_id}/autofix/`——查当前 run 的状态(步骤、根因分析结果、代码改动)。两个 endpoint 都支持 `?llmFormat=json|markdown|xml`,专门为 LLM 消费格式化输出。

**Endpoint**: `GET /api/0/seer/models/`——查 Seer 当前用的模型列表,**这个 endpoint 文档写明不需要鉴权**,可以拿来试探 Seer 是否可用而不消耗 token。

⚠ 文档原文,未实测:整个 autofix 流程涉及异步执行、可能触发真实代码改动/PR,没有真实账号跑不出行为细节;`verification-plan.md` 里把它列为低优先级(需要接了 repo 的账号,成本高于其他条目)。
