---
name: sentry
description: 接入 Sentry（docs.sentry.io，错误追踪 / 应用监控平台）的开发手册——面向两类任务：(1) 用 Web API（sentry.io/api/0/…，Bearer auth token）读取/管理已有的 error tracking 数据：组织、项目、issue 查询与解决/忽略/分派、事件与堆栈跟踪、release 与 deploy、alert 与 webhook；(2) 给应用接入 Sentry SDK（DSN，如 sentry-sdk / @sentry/node）让它自己上报错误。当用户提到 "Sentry""sentry.io""docs.sentry.io""sentry-sdk""@sentry/node""@sentry/react""Sentry API""Sentry DSN""Sentry issue""Sentry auth token""查 Sentry 报错""接入 Sentry 监控""给 Agent 装 Sentry 错误追踪"，或要求写代码调用上述任意能力时，应主动使用本技能——不要凭训练记忆编造 Web API 的鉴权方式、endpoint 路径或 issue 搜索语法，也不要把 DSN 和 API token 这两种完全不同的凭证搞混。
---

# Sentry 接入指南

Sentry 是错误追踪 / 应用监控平台。本 skill 面向两类开发者任务：

1. **给应用装上 Sentry**，让它把自己的错误上报给 Sentry（**ingestion**，用 DSN）。
2. **用代码去查询/管理已经在 Sentry 里的数据**——组织、项目、issue、event、release、alert（**Web API**，用 auth token）。

这两件事用的是**完全不同的两套 API 表面、两种完全不同的凭证**，混淆是本 skill 要防的头号错误，见下面「先分清楚」。

## ⚠ 验证状态

**本 skill 目前没有真实 Sentry 账号 / API token / DSN 可用，第 3 步（真实调用验证）尚未进行。** 全部内容来自：

- `https://docs.sentry.io` 的官方文档（Markdown 源页，抓取于 2026-09-21）
- `https://raw.githubusercontent.com/getsentry/sentry-api-schema/main/openapi-derefed.json` 的官方 OpenAPI 规范（同日抓取，147 个 path / 234 个 operation，是 docs.sentry.io API Reference 页面背后的权威数据源）

**每一处具体的字段名、参数表、响应结构、报错行为，都标了 `⚠ 文档原文，未实测`**——这些是文档和规范里写的,没有拿真实 token 跑过,不代表 Sentry 生产环境行为一定如此（尤其是 OpenAPI 规范里很多字段没写 `required`,不代表真的可选;是否报错、是否静默失效，完全没有验证）。有 key 之后按 `../sentry-workspace/verification-plan.md` 的清单逐条打真实请求，打完把对应结论改成"已用真实 API 验证（日期）：…"并附报错原文。**在验证完成之前，任何"应该不会有问题"的判断都不可信，遇到分歧以真实调用结果为准。**

## 先分清楚：ingestion 还是 Web API？

Sentry 有两套互相独立的 API 表面，agent 任务一上来就要判断落在哪一边——判断错了，代码方向就整个错了。完整对比、DSN 结构、SDK 初始化示例见 [`references/ingestion-vs-api.md`](references/ingestion-vs-api.md)，这里先给结论表：

| | Ingestion（上报错误） | Web API（读取/管理数据） |
| :--- | :--- | :--- |
| 任务例子 | "让我的 Node 服务自己把异常报给 Sentry" | "查一下我这个项目最近的未解决 issue" |
| 凭证 | **DSN**（Data Source Name，项目级，公开也安全，只能写不能读） | **Auth Token**（Bearer token，按 scope 授权，能读能写） |
| 怎么用 | 装官方 SDK（`sentry-sdk`、`@sentry/node`…），`init(dsn=...)`，**不要手搓 HTTP 调用** | 直接 HTTP 请求 `https://{region}.sentry.io/api/0/...`，带 `Authorization: Bearer <token>` |
| Base 端点 | `https://oXXXXXX.ingest.sentry.io/...`（DSN 里自带） | `https://{region}.sentry.io/api/0/...`（`us.sentry.io` 或 `de.sentry.io`，看组织的数据区域） |
| 本 skill 覆盖深度 | 到"怎么装、DSN 长什么样、去哪拿"为止，具体到每个语言/框架的细节交给官方 SDK 文档 | 全覆盖，是本 skill 的主体 |

**判断方法：如果任务是"把错误数据放进 Sentry"，去装 SDK；如果任务是"把 Sentry 里已有的数据取出来 / 改状态"，用 Web API + auth token。** 两者不能互相替代：DSN 打不了 `GET /issues/`，auth token 也不是 SDK 的 `dsn=` 参数。

## 用之前先确认这 3 件事

1. **Base URL 必须带区域（region）前缀**：`https://us.sentry.io/api/0/...` 或 `https://de.sentry.io/api/0/...`，不要硬编码成裸的 `sentry.io`。Sentry 支持数据存储在 US 或 EU 两个区域（组织创建时选定，之后不能改）；US 区域用 `sentry.io` 也能工作，但 EU 区域的组织必须打 `de.sentry.io`，否则请求会被路由错误（⚠ 文档原文，未实测：具体报什么错没验证）。最稳的做法：先调一次 `GET /api/0/organizations/` 或 `GET /api/0/organizations/{org}/`，响应里的 `links.regionUrl` 字段就是这个组织该用的 base URL，别自己猜。
2. **鉴权精确格式**：`Authorization: Bearer <token>`（标准 Bearer，没有奇怪前缀）。token 从哪儿来、三种 token 类型（Organization Token / Internal Integration / Personal Token）怎么选，见 [`references/auth-and-tokens.md`](references/auth-and-tokens.md)——选错类型会导致要么权限不够、要么权限过大。
3. **最容易选错的字段：`organization_id_or_slug`**。几乎每个 Web API endpoint 路径里都有它，可以传组织的数字 ID 或 slug（URL 里那串），两者等价；但**项目级 endpoint 的路径是 `/api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/...`，组织 slug 也必须写在前面**——很容易漏掉，写成 `/api/0/projects/{project_id_or_slug}/...` 直接 404。

## 30 秒跑通第一个请求

最便宜的只读 endpoint：列出这个 token 能访问的组织，顺便拿到每个组织该用的 region URL。

```bash
curl -s "https://sentry.io/api/0/organizations/" \
  -H "Authorization: Bearer $SENTRY_AUTH_TOKEN"
```

```python
import os, requests

resp = requests.get(
    "https://sentry.io/api/0/organizations/",
    headers={"Authorization": f"Bearer {os.environ['SENTRY_AUTH_TOKEN']}"},
)
resp.raise_for_status()
for org in resp.json():
    print(org["slug"], org["links"]["regionUrl"])
```

⚠ 文档原文，未实测：响应字段名、`links.regionUrl` 的实际取值格式来自 OpenAPI 规范，没有拿真实 token 验证过。

## 能力域导航

| 我想做什么 | 读哪个文件 | 涉及的核心 endpoint |
| :--- | :--- | :--- |
| 判断该用 SDK 还是 Web API；DSN 长什么样、去哪拿；SDK 初始化最小示例 | [`references/ingestion-vs-api.md`](references/ingestion-vs-api.md) | （SDK `init()`，不是 HTTP endpoint） |
| 搞清楚三种 auth token（Organization / Internal Integration / Personal）该用哪种；scope 对照表；OAuth2 / Device Flow | [`references/auth-and-tokens.md`](references/auth-and-tokens.md) | `POST /oauth/token/`、`GET /api/0/organizations/` |
| 列出组织、项目；建项目；拿到项目的 Client Key（DSN 从这来） | [`references/organizations-and-projects.md`](references/organizations-and-projects.md) | `GET /api/0/organizations/{org}/projects/`、`GET /api/0/projects/{org}/{project}/keys/` |
| 查询 issue 列表（Sentry 自己的搜索 DSL）、解决/忽略/分派/合并/删除 issue、Seer 自动修复 | [`references/issues.md`](references/issues.md) | `GET/PUT/DELETE /api/0/organizations/{org}/issues/` |
| 拿一个 issue 下的具体 event（含堆栈跟踪）、event 附件、source map 调试 | [`references/events.md`](references/events.md) | `GET /api/0/organizations/{org}/issues/{issue_id}/events/{event_id}/` |
| 创建/查询 release，关联 deploy、commit，上传 release 文件 | [`references/releases-and-deploys.md`](references/releases-and-deploys.md) | `POST /api/0/organizations/{org}/releases/`、`.../deploys/` |
| Sentry 端的告警（Detector + Workflow，新版统一告警系统）、Service Hook、Integration Platform Webhook | [`references/alerts-and-webhooks.md`](references/alerts-and-webhooks.md) | `GET /api/0/organizations/{org}/detectors/`、`POST /api/0/projects/{org}/{project}/hooks/` |
| 分页、限流、报错格式、并发限制 | [`references/errors-and-limits.md`](references/errors-and-limits.md) | （跨端点的通用行为） |

## 跨领域的通用规则（写代码前必读）

1. **Issue ≠ Event。Issue 是"一组相似错误的聚合"，Event 是"一次具体发生"。** "帮我看下这个报错"这种任务通常要分两步：先按条件/ID 找到 issue（`shortId` 形如 `PROJECT-1A2`，或数字 `issue_id`），再从这个 issue 下面取一个具体 event 才能看到堆栈跟踪。`GET /api/0/organizations/{org}/issues/{issue_id}/events/{event_id}/` 的 `event_id` 除了传 32 位十六进制 event ID，**还接受字面量 `latest` / `oldest` / `recommended`**（⚠ 文档原文/规范字段，未实测），这是拿"最新一次报错详情"最直接的写法，不需要先列出全部 event 再挑最后一个。
2. **Issue 搜索是 Sentry 自己的一套 DSL，不是关键词全文搜索。** 语法是 `key:value` token 组合 + 可选的一段裸文本（裸文本按标题/消息做子串匹配）。空 `query` 参数返回全部；**不传 `query` 时默认应用 `is:unresolved`**，这是最容易踩的坑——以为"没传条件=全部"，实际上默认过滤掉了已解决/已忽略的。常用 key：`is:unresolved`/`is:resolved`/`is:ignored`/`is:assigned`、`assigned:me`/`assigned:#team-name`、`age:-24h`（24 小时内新增）、`firstSeen:-7d`、`error.type:ValueError`。`OR`/`AND`/括号只在 Explore、Dashboards、Monitors 里支持，**issue 搜索本身不支持布尔操作符**，多值用列表语法 `issue.priority:[high, medium]`。完整 key 列表见 `references/issues.md`。
3. **组织级 vs 项目级 endpoint 路径结构不同，很多资源两边都有对应 endpoint。** `/api/0/organizations/{org}/issues/` vs 已废弃的 `/api/0/projects/{org}/{project}/issues/`（官方文档标注为 Deprecated，建议改用组织级 + `project` query 参数过滤）。新代码优先用组织级 endpoint；只有确实没有组织级替代时才用项目级（比如 client key / DSN 管理只有项目级）。
4. **DSN 和 Auth Token 不能互换，DSN 天生只写不读。** 官方原话："DSNs are safe to keep public because they only allow submission of new events and related event data; they do not allow read access to any information." 如果任务需要"读"任何东西（哪怕只是查一下项目名），DSN 做不到，必须用 auth token。反过来，SDK 的 `dsn=` 参数不能填 auth token。
5. **分页用 HTTP `Link` header + `cursor` 参数，不是页码。** 响应 header 里的 `Link` 会给出 `rel="next"` 和 `rel="previous"` 两个 URL，各自带 `results="true"/"false"` 指示是否还有数据；照着 `rel="next"` 的 URL 一直请求直到 `results="false"`。不要自己拼 `?page=N`。
6. **限流看响应 header，不要靠猜。** 每次请求都会返回 `X-Sentry-Rate-Limit-Limit` / `-Remaining` / `-Reset` / `-ConcurrentLimit` / `-ConcurrentRemaining`。轮询式地反复调用容易很快触发限流；文档明确建议改用 webhook 而不是轮询。
7. **部分 endpoint 支持 `?llmFormat=json|markdown|xml`（issue、event、Seer autofix 详情）**，会在响应里加一个 `formatted` 字段，把内容渲染成给 LLM 读的格式（⚠ 文档原文，未实测，具体覆盖哪些 endpoint 未逐一验证）。如果调用方本身就是个 agent，优先试一下这个参数，可能比自己解析嵌套 JSON 省事。
8. **Sentry 的 "Monitors" 在文档里指两个不同的东西**，容易和"issue 告警"搞混：一个是 **Crons**（定时任务打卡监控，`/api/0/organizations/{org}/monitors/`），另一个是新版统一告警系统里的 **Detector**（`/api/0/organizations/{org}/detectors/`，UI 上也叫 "Monitors"，是触发条件；配对的 **Workflow** 定义触发后执行的动作）。本 skill 的"alert"指后者，见 `references/alerts-and-webhooks.md`；Crons 定时任务监控不在本 skill 覆盖范围内。

## 目录结构

```
sentry/
├── SKILL.md                              # 本文件：路由 + 通用规则
├── references/
│   ├── ingestion-vs-api.md               # SDK/DSN 上报 vs Web API 查询，怎么选
│   ├── auth-and-tokens.md                # 三种 token、scope 对照表、OAuth2/Device Flow
│   ├── organizations-and-projects.md     # 组织/项目列表、Client Key(DSN) 管理
│   ├── issues.md                         # issue 查询 DSL、resolve/ignore/assign/merge、Seer autofix
│   ├── events.md                         # event 详情、堆栈跟踪、附件、source map 调试
│   ├── releases-and-deploys.md           # release 创建、deploy、commit 关联、文件上传
│   ├── alerts-and-webhooks.md            # Detector/Workflow 告警、Service Hook、Integration Platform Webhook
│   └── errors-and-limits.md              # 分页、限流、HTTP 状态码约定
└── evals/
    └── evals.json                        # 对照场景（打包时排除，不分发）
```

内容整理自 `docs.sentry.io`（抓取于 2026-09-21）与 `github.com/getsentry/sentry-api-schema` 的 OpenAPI 规范（同日抓取）。**没有真实调用验证过**——实际调用报错永远优先信任，发现和本 skill不一致的地方，按文档里的报错格式记录下来，改回对应 reference 文件。
