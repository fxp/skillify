# 组织与项目（Web API）

> ⚠ 全部字段/参数表来自 `openapi-derefed.json`（`github.com/getsentry/sentry-api-schema`，抓取于 2026-09-21）转录，未经真实调用验证。Base URL 统一为 `https://{region}.sentry.io`。

## 目录

- [列出当前 token 能访问的组织](#列出当前-token-能访问的组织)
- [组织详情](#组织详情)
- [组织下的项目列表](#组织下的项目列表)
- [创建项目](#创建项目)
- [项目详情 / 更新](#项目详情--更新)
- [Client Keys（DSN）——ingestion 和 Web API 的交界点](#client-keysdsningestion-和-web-api-的交界点)
- [其他项目相关 endpoint（简表）](#其他项目相关-endpoint简表)

## 列出当前 token 能访问的组织

**Endpoint**: `GET /api/0/organizations/`
**用途**: 拿到 token 能访问的组织列表，以及每个组织应该用哪个 region base URL（`links.regionUrl`）。这是"30 秒跑通第一个请求"用的那个 endpoint，也是判断该往哪个域名发后续请求的起点。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `owner` | boolean | 否 | `true` 只返回你是 owner 的组织 |
| `query` | string | 否 | 按 slug/id/status/email/member_id 等过滤，支持 `AND`/`OR`，如 `query=(slug:foo AND status:active)` |
| `sortBy` | string | 否 | `members` 或 `events`（按过去 24h 事件数） |
| `per_page` | integer | 否 | 默认/最大 100 |

**示例请求**

```bash
curl -s "https://sentry.io/api/0/organizations/" \
  -H "Authorization: Bearer $SENTRY_AUTH_TOKEN"
```

**示例响应（关键字段,精简)**

```json
[
  {
    "id": "1",
    "slug": "acme",
    "name": "Acme Inc",
    "status": {"id": "active", "name": "active"},
    "links": {"organizationUrl": "https://acme.sentry.io", "regionUrl": "https://us.sentry.io"}
  }
]
```

**注意事项**

- API key（遗留 Basic Auth）方式调用这个 endpoint 只会返回该 key 绑定的那一个组织，不是全部。
- `links.regionUrl` 是后续所有针对这个组织的请求应该用的 base URL——不要在拿到这个值之后还硬编码 `sentry.io`。

## 组织详情

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/`
**用途**: 单个组织的详情，包含 `access`（当前 token/用户在这个组织的权限列表）、`features`（组织开通的功能开关）、`links.regionUrl`。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `organization_id_or_slug` | path | 是 | 组织 ID 或 slug |
| `detailed` | query string | 否 | 传 `"0"` 可以拿到不含 projects/teams 的精简版（省流量） |

更新组织：`PUT /api/0/organizations/{organization_id_or_slug}/`（需要 `org:write`）——本 skill 不展开可更新字段清单，属于组织设置管理，用到时查 OpenAPI 规范或官方文档。

## 组织下的项目列表

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/projects/`
**用途**: 列出这个组织下的全部项目（这是当前**推荐**的项目列表 endpoint，不是项目级的某个"列出兄弟项目"接口)。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `query` | string | 否 | 按项目名/slug 过滤 |
| `per_page` | integer | 否 | 默认/最大 100 |
| `cursor` | string | 否 | 分页游标 |

**响应关键字段**：`id`、`slug`、`name`、`platform`、`team`/`teams`（归属团队）、`firstEvent`（首次收到事件的时间，`null` 说明项目还没接过任何数据——排查"我的 SDK 接了但 Sentry 里看不到东西"时先看这个字段）、`hasMonitors`/`hasReplays`/`hasProfiles`/`hasLogs` 等一堆 `has*` 功能开关（说明该项目实际用了哪些 Sentry 产品）。

## 创建项目

**Endpoint**: `POST /api/0/organizations/{organization_id_or_slug}/projects/`
**用途**: 新建项目。**副作用**：会自动创建一个"个人 team"（`team-{username}`，调用者拿 Team Admin 角色）并把项目绑定给它——不是绑定到组织的默认 team,除非组织关闭了成员建项目权限（`disable_member_project_creation`）,此时需要 `org:write` scope 而不是普通的 `project:write`。

**请求体**

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `name` | string | 是 | 项目名 |
| `slug` | string | 否 | 不传则从 name 自动生成 |
| `platform` | string | 否 | 平台标识（如 `python`、`node`），影响 Sentry UI 里显示的 onboarding 指引 |
| `default_rules` | boolean | 否 | 默认 `true`：新 issue 自动触发默认告警。设 `false` 关闭默认告警，需要自己建 |

**示例请求**

```bash
curl -s -X POST "https://us.sentry.io/api/0/organizations/acme/projects/" \
  -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-service", "platform": "python"}'
```

⚠ 文档原文，未实测：创建成功后是否已经生成了默认 Client Key（DSN）——按 Sentry 一般行为推断"应该有"，但没有验证过，用之前先调下面的 Client Keys 列表确认。

## 项目详情 / 更新

**Endpoint**: `GET /api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/`
**用途**: 单个项目详情，字段比组织下的列表接口更全（包含 `digestsMinDelay`/`resolveAge`/`dataScrubber` 等项目级配置项）。

**Endpoint**: `PUT /api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/`
**注意事项**: 官方文档明确写了一条权限细节——**只有 `project:read` scope（没有 `project:write`）时，可更新的字段被限制在一个白名单内**（`isBookmarked`、`autofixAutomationTuning`、`seerScannerAutomation` 等几个跟"自动化/个人偏好"相关的字段），其余字段更新需要 `project:write`。这是一个容易被忽略的细节：**不是"没权限就整体报错"，而是"没权限时能改的字段集合缩水"**，⚠ 文档原文，未实测具体是报错还是静默忽略多传的字段。

**Endpoint**: `DELETE /api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/`——需要 `project:admin`。

## Client Keys（DSN）——ingestion 和 Web API 的交界点

这组 endpoint 是"用 Web API 查/管理 ingestion 用的 DSN"，详见 `ingestion-vs-api.md`。

**Endpoint**: `GET /api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/keys/`
**用途**: 列出项目的全部 Client Key。每个 key 都带一份完整的 DSN 集合（不止一个 URL）。

**响应关键字段**

| 字段 | 说明 |
| :--- | :--- |
| `dsn.public` | 标准 DSN，SDK `init(dsn=...)` 用这个 |
| `dsn.secret` | 遗留字段，SDK 一般不再需要 |
| `dsn.csp` / `dsn.security` | CSP/安全策略报告专用端点 |
| `dsn.minidump` / `dsn.unreal` | 原生崩溃转储（游戏引擎等）专用端点 |
| `dsn.crons` | Cron 监控 check-in 专用端点 |
| `dsn.otlp_traces` / `dsn.otlp_logs` | OpenTelemetry Protocol 接入端点 |
| `isActive` | key 是否处于启用状态,被禁用的 key 上报的事件会被丢弃 |
| `rateLimit` | 可选的按窗口限流（`window` 秒数 + `count` 上限） |

**Endpoint**: `POST /api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/keys/`
**用途**: 新建一个 Client Key（即新 DSN）。`useCase` 枚举 `user`/`profiling`/`tempest`/`demo`（默认 `user`）。

**Endpoint**: `GET`/`PUT`/`DELETE /api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/keys/{key_id}/`——单个 key 的查/改/删（旋转 DSN 就是删旧建新，或者看 UI 是否支持原地 regenerate,⚠ 文档未说明 API 侧是否有"regenerate"动作，看起来只有 CRUD）。

**注意事项**：一个项目可以有**多个** Client Key/DSN 同时生效（比如给不同环境发不同 DSN，方便单独吊销）。查 DSN 时不要假设只有一个,要遍历列表或按 `useCase`/`isActive` 过滤。

## 其他项目相关 endpoint（简表）

以下 endpoint 存在但本 skill 不展开字段细节（不属于"读/管理错误数据"或"instrument 应用"这两个核心场景，用到时查 OpenAPI 规范）：

| Endpoint | 用途 |
| :--- | :--- |
| `GET /api/0/projects/{org}/{project}/members/` | 项目成员 |
| `GET /api/0/projects/{org}/{project}/teams/`、`POST/DELETE .../teams/{team}/` | 项目关联的 team |
| `GET/PUT /api/0/projects/{org}/{project}/ownership/` | Ownership Rules（issue 自动分派规则的配置源，写在这里但生效于 issue 分派） |
| `GET /api/0/projects/{org}/{project}/filters/`、`PUT .../filters/{filter_id}/` | Inbound Data Filter（服务端丢弃哪些事件，如过滤特定 IP/legacy 浏览器） |
| `GET/POST /api/0/projects/{org}/{project}/user-feedback/` | 用户反馈（前端 SDK 收集的用户报告，和"错误事件"是两个概念） |
| `POST/DELETE /api/0/organizations/{org}/spike-protections/` | Spike Protection（突发流量保护开关） |
| `GET /api/0/projects/{org}/{project}/stats/` | 项目级事件量统计 |
| `GET /api/0/organizations/{org}/members/`、`.../repos/`、`.../shortids/{issue_id}/` | 组织成员、关联代码仓库、按 short ID 反查 issue |

`GET /api/0/organizations/{org}/shortids/{issue_id}/` 值得单独一提：**把 UI 上看到的 short ID（如 `MYPROJ-1A2`）反查成 issue 详情**,拿到 UI 链接里那种短码、要转成 API 可用的 issue_id 时用这个。
