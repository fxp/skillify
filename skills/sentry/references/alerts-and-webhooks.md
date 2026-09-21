# 告警与 Webhook（Web API）

> ⚠ 全部内容来自 `openapi-derefed.json`（`github.com/getsentry/sentry-api-schema`，抓取于 2026-09-21）与 `docs.sentry.io/integrations/integration-platform/webhooks.md` 转录，未经真实调用验证。Base URL 统一为 `https://{region}.sentry.io`。

## 目录

- [三套容易混淆的"告警/监控"机制](#三套容易混淆的告警监控机制)
- [Detector：定义触发条件](#detector定义触发条件)
- [Workflow：定义触发后的动作](#workflow定义触发后的动作)
- [Service Hook（项目级简单 webhook）](#service-hook项目级简单-webhook)
- [Integration Platform Webhook（完整集成，收 Sentry 事件）](#integration-platform-webhook完整集成收-sentry-事件)
- [Spike Protection 通知（专用，不要和通用告警混淆)](#spike-protection-通知专用不要和通用告警混淆)

## 三套容易混淆的"告警/监控"机制

Sentry 文档和 API 里至少有三套名字相近、实际不同的机制,写代码前先分清楚要用哪个:

| 机制 | 对应 API tag / endpoint | 用途 |
| :--- | :--- | :--- |
| **Detector + Workflow**(新版统一告警系统,本文重点) | `Monitors` tag,`/detectors/`、`/workflows/` | issue 触发条件 + 触发后动作(通知/建 ticket),UI 上叫 "Monitors"(*不是*下面的 Crons) |
| **Crons**(定时任务打卡监控,不在本 skill 覆盖范围) | `Crons` tag,`/api/0/organizations/{org}/monitors/` | 你的 cron job 有没有按时跑,和"错误追踪"关系不大 |
| **Service Hook / Integration Platform Webhook**(接收 Sentry 发来的事件) | `Projects` 分组下的 `/hooks/`;Integration Platform 的 webhook 机制 | 让外部服务被动收到 Sentry 的事件推送 |

**如果任务是"我想在某类 issue 出现时被通知/自动执行动作"**——用 Detector+Workflow(定义"什么时候触发"+"触发后干什么")。
**如果任务是"我想让我的服务实时收到 Sentry 发生的事情"**——用 webhook(Service Hook 或 Integration Platform,取决于你是内部脚本还是要发布成正式集成)。

## Detector：定义触发条件

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/detectors/`
**用途**: 列出组织的全部 Detector(监控/触发条件定义)。

**关键参数**:`project`(过滤)、`query`(搜索,支持字段 `name`/`type`/`assignee`)、`type`(按监控类型过滤,如 `error`/`metric_issue`/`issue_stream`)、`enabled`(布尔)、`sortBy`(`name`/`id`/`type`/`connectedWorkflows`/`latestGroup`/`openIssues`)。

**Endpoint**: `POST /api/0/organizations/{organization_id_or_slug}/projects/{project_id_or_slug}/detectors/`
**用途**: 为某个项目新建一个 Detector。**注意路径里同时有 org 和 project**——是 Monitors 分组里少数几个"看起来是组织级、实际路径夹了 project slug"的创建型 endpoint。

**关键请求体字段**

| 字段 | 说明 |
| :--- | :--- |
| `name` | 监控名称 |
| `type` | 目前示例只给了 `metric_issue`(⚠ 文档未列出完整枚举) |
| `data_sources` | 定义"测量什么"——不同监控类型结构不同,常见几种(节选自规范里的示例): |

- **错误数量监控**:`{"aggregate": "count()", "dataset": "events", "eventTypes": ["default","error"], "query": "is:unresolved", "timeWindow": 3600}`
- **受影响用户数监控**:`aggregate` 换成 `count_unique(tags[sentry:user])`
- **吞吐量/延迟/失败率/LCP 等性能类监控**:`dataset: "events_analytics_platform"`,`aggregate` 用 `count(span.duration)`/`p95(span.duration)`/`failure_rate()`/`p95(measurements.lcp)` 等聚合函数

| 字段 | 说明 |
| :--- | :--- |
| `config.detectionType` | `static`(固定阈值)/`percent`(环比变化)/`dynamic`(异常检测,自动学习基线) |
| `config.comparisonDelta` | `percent` 类型时,和多久之前的数据比较(分钟数:`300`/`900`/`3600`/`86400`/`604800`/`2592000`) |
| `condition_group.conditions[].type` | `gt`(大于)/`lte`(小于等于)/`anomaly_detection`(动态) |
| `condition_group.conditions[].comparison` | 阈值(整数),或 dynamic 类型时是 `{"seasonality": "auto", "sensitivity": "low"\|"medium"\|"high", "thresholdType": 0\|1\|2}` |
| `condition_group.conditions[].conditionResult` | 越过阈值后 issue 的优先级:`75`=high、`50`=medium/low(两处文档口径不一致,⚠ 文档自相矛盾,一处写"50: Low priority"另一处写"75: High priority ... 50: Medium priority",具体映射需要真实调用确认)、`0`=resolved |
| `workflow_ids` | 关联到哪些 Workflow(触发后执行哪些动作),需要先建好 Workflow 拿到 ID |
| `enabled` | 布尔,默认启用 |

**易错点**:**`condition_group.conditions[].conditionResult` 的优先级数值映射在文档两处描述不完全一致**(⚠ 文档自相矛盾,留给真实调用去判)——建之前先用小范围测试确认 `75`/`50`/`0` 具体对应什间关系,不要直接照抄示例硬编码。

`GET/PUT/DELETE /api/0/organizations/{organization_id_or_slug}/detectors/{detector_id}/`——单个 Detector 查/改/删。`PUT .../detectors/`(不带 ID,批量)——批量启用/禁用。

## Workflow：定义触发后的动作

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/workflows/`
**用途**: 列出组织的全部 Workflow(触发条件满足后要做的事)。参数:`detector`(按关联的 Detector ID 过滤)、`sortBy`(`name`/`dateCreated`/`connectedDetectors`/`actions`/`priorityDetector` 等)。

**Endpoint**: `POST /api/0/organizations/{organization_id_or_slug}/workflows/`
**用途**: 新建 Workflow。核心结构是 `triggers`(什么条件下动作会执行) + `actionFilters`(每组条件对应哪些具体动作)。

**`triggers.conditions[].type` 常见取值**(节选,来自规范示例):`first_seen_event`(issue 首次出现)、`issue_resolved_trigger`、`reappeared_event`(已解决/忽略的 issue 又出现了)、`regression_event`、`seer_activity_trigger`(Seer 分析进度变化,值如 `rca_completed`/`solution_completed`/`pr_ready_for_review`)。

**`actionFilters[].conditions[].type` 的完整条件类型清单**(这是过滤"该不该触发动作"的条件,和上面 `triggers` 的条件是两层不同的东西):

| 条件类型 | 用途 | 关键字段 |
| :--- | :--- | :--- |
| `age_comparison` | issue 存在时长 | `time`(`minute`/`hour`/`day`/`week`) + `value` + `comparisonType`(`older`/`newer`) |
| `assigned_to` | 按分派对象 | `targetType`(`Unassigned`/`Member`/`Team`) + `targetIdentifier` |
| `issue_category` | 按 issue 分类 | `value`:`1`=Error、`6`=Feedback、`10`=Outage、`11`=Metric、`12`=DB Query、`13`=HTTP Client、`14`=Frontend、`15`=Mobile、`17`=Preprod、`19`=Configuration |
| `issue_occurrences` | 出现次数阈值 | `value` |
| `issue_priority_deescalating` / `issue_priority_greater_or_equal` | 优先级变化/门槛(`75`=high、`50`=medium、`25`=low) | `comparison` |
| `event_unique_user_frequency_count` | 影响用户数阈值 | `value` + `interval`(`1min`~`30d`) |
| `event_frequency_count` / `event_frequency_percent` | 事件数阈值/环比 | `value` + `interval` (+ `comparisonInterval`) |
| `percent_sessions_count` / `percent_sessions_percent` | 受影响 session 占比 | 同上结构 |
| `event_attribute` | 匹配事件属性 | `attribute`(`message`/`exception.type`/`user.email`/`http.status_code` 等一长串) + `match`(`co`/`nc`/`eq`/`ne`/`sw`/`ew`/`is`/`ns`) + `value` |
| `tagged_event` | 匹配 tag | `key` + `match` + `value` |
| `latest_release` / `latest_adopted_release` | 是否来自最新 release | — |
| `level` | 事件严重级别 | `match`(`eq`/`gte`/`lte`) + `level`(`50`=Fatal…`0`=Sample) |

**`actionFilters[].actions[].type` 支持的通知渠道**(节选):`email`(`targetType`: `user`/`team`/`issue_owners`)、`slack`、`pagerduty`、`discord`、`msteams`、`opsgenie`、`vsts`(Azure DevOps)、`jira`/`jira_server`(建 ticket)、`github`(建 issue)。每种渠道需要不同的 `config`/`integrationId`/`data` 组合,具体字段名见规范里对应示例(本 skill 未逐一展开,用到哪个渠道就查 `openapi-derefed.json` 里 `Monitors` 分组下 `POST .../workflows/` 的完整参数说明)。

**易错点**:`triggers` 里的条件类型和 `actionFilters` 里的条件类型**是两套不同的枚举**,不能混用——比如 `first_seen_event` 只在 `triggers` 里出现,`age_comparison` 只在 `actionFilters` 里出现,照抄示例时容易张冠李戴。

`GET/PUT/DELETE /api/0/organizations/{organization_id_or_slug}/workflows/{workflow_id}/`——单个 Workflow 查/改/删。`PUT .../workflows/`(批量)——批量启用/禁用。

## Service Hook（项目级简单 webhook）

**Endpoint**: `GET /api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/hooks/`
**用途**: 列出项目上注册的 service hook。**需要项目开通 `servicehooks` feature**,未开通时行为未知(⚠ 文档未说明)。

**Endpoint**: `POST /api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/hooks/`
**用途**: 注册一个新 hook,收到事件时 Sentry 会 POST 到指定 URL。支持的 `events` 目前文档列出两个:`event.alert`(告警规则触发时)、`event.created`(新事件被处理时)。

**响应示例**

```json
{
  "id": "4f9d73e63b7144ecb8944c41620a090b",
  "url": "https://empowerplant.io/sentry-hook",
  "events": ["event.alert", "event.created"],
  "secret": "8fcac28aaa4c4f5fa572b61d40a8e084364db25fd37449c299e5a41c0504cbc2",
  "status": "active"
}
```

`secret` 用于校验请求确实来自 Sentry(⚠ 文档未说明具体签名算法,Service Hook 和下面 Integration Platform Webhook 的签名机制可能不同,不要假设通用)。`GET/PUT/DELETE .../hooks/{hook_id}/`——单个 hook 的查/改/删。

**这是最轻量的方式**——不需要建一个完整的 Integration,适合"我自己的脚本想收到通知"这种场景。想要更结构化的事件类型(issue/comment/preprod artifact 等)、想发布成正式集成给别人用,走下面的 Integration Platform Webhook。

## Integration Platform Webhook（完整集成，收 Sentry 事件）

面向"要构建一个正式的 Sentry 集成"(Internal 或 Public)的场景,见 `docs.sentry.io/integrations/integration-platform.md`。在 Sentry UI 的 **Settings > Developer Settings** 创建 Internal/Public Integration 时配置 webhook URL。

**请求头**(每个 webhook 请求都带):

```
Content-Type: application/json
Request-ID: <request_uuid>
Sentry-Hook-Resource: <resource>
Sentry-Hook-Timestamp: <timestamp>
Sentry-Hook-Signature: <generated_signature>
```

**`Sentry-Hook-Resource` 枚举**:`installation`、`event_alert`、`issue`、`metric_alert`、`error`、`comment`、`seer`、`preprod_artifact`。

**签名校验**(`Sentry-Hook-Signature`,用 Integration 的 Client Secret 做 HMAC-SHA256):

```javascript
const crypto = require("crypto");

function verifySignature(request, secret = "") {
  const hmac = crypto.createHmac("sha256", secret);
  hmac.update(JSON.stringify(request.body), "utf8");
  const digest = hmac.digest("hex");
  return digest === request.headers["sentry-hook-signature"];
}
```

**请求体通用结构**:`action`(和 resource 搭配,如 resource=`issue` 时 action 可能是 `created`)、`installation.uuid`(用于映射到具体安装实例)、`data`(具体内容,随 resource 类型变化)、`actor`(谁触发的:`type: "user"` 用户触发 / `type: "application"` 集成自己触发 / `type: "application", id: "sentry"` Sentry 系统自动触发,比如自动 resolve)。

**响应要求**:**必须在 1 秒内响应**,否则算超时——webhook handler 里不要做同步的慢操作(下游处理放到队列里异步做)。

**鉴权 token**:Public Integration 走 OAuth2 流程发 token,Internal Integration 安装后自动生成 token(都是普通 Bearer auth token,见 `auth-and-tokens.md`)。

**本地调试**:官方建议用 HTTP catch-all 服务(先看 payload 长什么样)+ 内网穿透工具(把本地端口暴露成临时公网 URL)配合开发。

## Spike Protection 通知（专用，不要和通用告警混淆)

**Endpoint**: `GET/POST /api/0/organizations/{organization_id_or_slug}/notifications/actions/`
**用途**: **专门给 Spike Protection(流量突增保护)这一个场景用的通知渠道配置**,`trigger_type` 目前文档写死只支持 `spike-protection` 一个值——**不是通用的"新建一个通知渠道给任意告警用"的 endpoint**,名字里的 "Notifications" 容易让人误以为是通用机制,实际作用域很窄。

`service_type` 支持 `email`/`slack`/`sentry_notification`/`pagerduty`/`opsgenie`。`slack`/`pagerduty`/`opsgenie` 需要额外传 `integration_id`(先用 `GET /api/0/organizations/{org}/config/integrations/` 查已装的 integration 列表)。

想给普通 issue 告警配置 Slack/PagerDuty 等通知渠道,用上面的 Workflow `actionFilters[].actions`,不要用这个 Spike Protection 专用 endpoint。
