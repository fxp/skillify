# Event 详情与堆栈跟踪（Web API）

> ⚠ 全部内容来自 `openapi-derefed.json`（`github.com/getsentry/sentry-api-schema`，抓取于 2026-09-21）转录，未经真实调用验证。Base URL 统一为 `https://{region}.sentry.io`。

## 目录

- [Event 是什么、和 Issue 什么关系](#event-是什么和-issue-什么关系)
- [列出一个 Issue 下的 Event](#列出一个-issue-下的-event)
- [取一个具体 Event（含堆栈跟踪）——latest/oldest/recommended](#取一个具体-event含堆栈跟踪latestoldestrecommended)
- [堆栈跟踪具体在响应的哪里](#堆栈跟踪具体在响应的哪里)
- [列出一个项目下的全部 Event](#列出一个项目下的全部-event)
- [Event 附件](#event-附件)
- [Source Map 调试信息](#source-map-调试信息)

## Event 是什么、和 Issue 什么关系

Event = 一次具体的错误发生（一次 `capture_exception` 调用对应一个 event）。多个相似 event 聚合成一个 issue（见 `issues.md`）。**"看某个报错的堆栈跟踪"这个任务的正确顺序永远是先找到 issue，再从 issue 下取一个具体 event**——issue 本身的详情 endpoint 不带堆栈跟踪。

两种 event 定位路径,取决于你已经有什么:

| 已知条件 | 用哪个 endpoint |
| :--- | :--- |
| 已知 `issue_id` + 想要"最新/最旧/推荐"的那次 | `GET /api/0/organizations/{org}/issues/{issue_id}/events/{event_id}/`,`event_id` 传字面量 `latest`/`oldest`/`recommended` |
| 已知 `issue_id` + 想要具体某个 32 位十六进制 event ID | 同上 endpoint,`event_id` 传那个 ID |
| 已知 `project` + 具体的 32 位 event ID(不知道属于哪个 issue) | `GET /api/0/projects/{org}/{project}/events/{event_id}/` |
| 只知道一个 event ID,连项目都不确定 | `GET /api/0/organizations/{org}/eventids/{event_id}/`(反查属于哪个 project/issue,见 `organizations-and-projects.md` 附近,此 endpoint 在 Organizations 分组下) |

## 列出一个 Issue 下的 Event

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/issues/{issue_id}/events/`
**用途**: 分页列出这个 issue 下的全部 event(默认不含完整 body)。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `start`/`end`/`statsPeriod` | — | 否 | 时间范围过滤 |
| `environment` | array<string> | 否 | 按 environment 过滤 |
| `query` | string | 否 | 事件属性搜索,语法同 issue 搜索,但字段集不同(见 `docs.sentry.io/concepts/search/searchable-properties/events.md`),示例:`query=transaction:foo AND release:abc` |
| `full` | boolean | 否 | `true` 时返回完整 event body(含堆栈跟踪),**但页大小上限降到 10** |
| `sample` | boolean | 否 | 伪随机顺序返回(相同查询结果稳定,不是每次都变) |
| `per_page` | integer | 否 | 默认/最大 100 |
| `cursor` | string | 否 | 分页游标 |

**注意事项**:想批量拿多个 event 的堆栈跟踪时,`full=true` 会把每页从 100 砍到 10,**流量和请求次数要按这个上限重新估算**,大批量场景考虑改用 Discover/Explore 类 endpoint 或逐个精确请求。

## 取一个具体 Event（含堆栈跟踪）——latest/oldest/recommended

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/issues/{issue_id}/events/{event_id}/`
**用途**: 这是"拿到一次具体报错的完整详情(含堆栈跟踪)"最常用的入口。

**关键点**:`event_id` 路径参数除了字面的 32 位十六进制 event ID,**还接受三个特殊字面量**:

| 值 | 含义 |
| :--- | :--- |
| `latest` | 最近一次发生的 event |
| `oldest` | 最早一次发生的 event(通常也是"首次触发"时的现场) |
| `recommended` | Sentry 认为最具代表性的一次(和排序里的 `recommended` sort 是同一套逻辑) |

不知道具体要哪次时,**`latest` 几乎总是你想要的**——不需要先调"列出 issue 下的 event"再挑最后一条,直接一次请求拿到。

**其他参数**:`environment`(过滤)、`llmFormat`(`json`/`markdown`/`xml`,加一个 `formatted` 字段,内容按格式渲染,方便 LLM 直接读,不用自己解析嵌套 JSON)。

**示例请求**

```bash
curl -s "https://us.sentry.io/api/0/organizations/acme/issues/123456/events/latest/?llmFormat=markdown" \
  -H "Authorization: Bearer $SENTRY_AUTH_TOKEN"
```

## 堆栈跟踪具体在响应的哪里

响应里和堆栈跟踪相关的字段:

- `entries`(`array<any>`)——**这是堆栈跟踪等结构化内容实际所在的字段**,但 OpenAPI 规范里类型标注就是 `any`,没有进一步展开子结构。按 Sentry 事件模型的一般约定,`entries` 是一个列表,其中 `type: "exception"` 的条目下有 `data.values[].stacktrace.frames`(每个 frame 含文件名/函数名/行号/源码上下文)。**这个嵌套结构没有在 OpenAPI 规范里精确定义,也没有真实调用验证过**——⚠ 是 `verification-plan.md` 里优先级最高的一条,因为这是"拿堆栈跟踪"这个核心任务能不能写对代码的关键。
- `groupingConfig`——用于计算指纹分组的配置,一般不用在业务代码里解析。
- `release`——这次 event 关联的 release(嵌套 `release.version`、`release.lastCommit`、`release.lastDeploy`),配合 `releases-and-deploys.md` 一起用可以定位"这个错误是哪次发布引入的"。
- `contexts`/`context`——运行时上下文(比如 `runtime`/`os`/`device`,具体键值未在规范里展开)。
- `occurrence`——如果这个 event 属于非传统错误类型的 issue(如性能问题),细节在这里而不是 `entries`。

⚠ 建议:第一次真实拿到一个 event 响应后,先把完整 JSON 存一份留着做字段参考,而不是完全照抄本文件里的猜测结构去解析。

## 列出一个项目下的全部 Event

**Endpoint**: `GET /api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/events/`
**用途**: 不按 issue 分组,直接看这个项目收到的原始 event 流(跨多个 issue)。参数结构和"issue 下的 event 列表"基本一致(`statsPeriod`/`start`/`end`/`full`/`sample`/`cursor`),**但没有 `query` 参数**,过滤能力弱于 issue 级的 event 列表 endpoint。

**Endpoint**: `GET /api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/events/{event_id}/`
**用途**: 已知项目和具体 32 位 event ID 时直接取详情,**不支持 `latest`/`oldest`/`recommended` 这几个特殊字面量**——这几个特殊值只在"issue 下的 event"那个 endpoint 里支持,⚠ 文档原文,未实测,这个差异容易被忽略而误用到项目级 endpoint 上导致 404。

## Event 附件

**Endpoint**: `GET /api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/events/{event_id}/attachments/`
**用途**: 列出这个 event 上传的附件(截图、日志文件、config 文件等)。**要求组织开通 `event-attachments` feature**,没开通时行为未知(⚠ 文档未说明是空列表还是报错)。支持 `query` 按名称子串或 `is:screenshot` 过滤。

**Endpoint**: `GET /api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/events/{event_id}/attachments/{attachment_id}/`
**用途**: 单个附件的元数据,或者**传任意值的 `download` query 参数**触发下载(返回二进制,响应可能是到存储服务的重定向,客户端要能跟随重定向)。

## Source Map 调试信息

**Endpoint**: `GET /api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/events/{event_id}/source-map-debug/`
**用途**: 前端 JS 报错时,用来诊断"为什么这个堆栈跟踪没有正确 unminify"。返回每一帧的 source map 查找过程(`source_file_lookup_result`/`source_map_lookup_result`,枚举 `found`/`wrong-dist`/`unsuccessful`),以及是否上传了带正确 debug id 的 artifact bundle。

**典型用途**:agent 在处理"这个 JS 报错的堆栈跟踪全是压缩后的乱码,看不出原始代码位置"这类任务时,先调这个 endpoint 确认是不是 source map 没传对,而不是直接假设堆栈跟踪数据本身有问题。

⚠ 文档原文,未实测:以上全部字段名、`entries` 的实际嵌套结构、`source-map-debug` 的判断逻辑均未拿真实前端项目验证过。
