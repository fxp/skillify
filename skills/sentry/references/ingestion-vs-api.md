# Ingestion（上报错误）vs Web API（查询/管理数据）—— 怎么选

> ⚠ 本文件全部内容来自 `docs.sentry.io` 官方文档转录，**没有真实 SDK 初始化或真实 API 调用验证过**。标注方式见 SKILL.md 顶部「验证状态」。

## 目录

- [两套 API 表面的本质区别](#两套-api-表面的本质区别)
- [DSN 是什么、长什么样](#dsn-是什么长什么样)
- [Ingestion：装 SDK，不要手搓 HTTP](#ingestion装-sdk不要手搓-http)
- [Web API：直接 HTTP + auth token](#web-api直接-http--auth-token)
- [常见任务该走哪条路](#常见任务该走哪条路)
- [两者的交界点：用 Web API 查 DSN](#两者的交界点用-web-api-查-dsn)

## 两套 API 表面的本质区别

Sentry 对外暴露两套完全独立的接口，很多"Sentry 接入"任务里两者都会用到，但**方向相反、凭证不同、路径也不同**：

| | Ingestion | Web API |
| :--- | :--- | :--- |
| 方向 | 应用 → Sentry（写入错误事件） | 调用方 ↔ Sentry（读/写组织数据） |
| 凭证 | **DSN**（Data Source Name） | **Auth Token**（`Authorization: Bearer <token>`） |
| 凭证的权限 | 只能提交新事件，**不能读取任何数据** | 按 token 的 scope 授权，可读可写 |
| 典型端点 | `https://o<orgId>.ingest.sentry.io/...`（DSN 里自带，一般不用自己拼） | `https://{region}.sentry.io/api/0/...` |
| 推荐实现方式 | **装官方 SDK**（`sentry-sdk`、`@sentry/node`、`@sentry/react`…），调 `init()` | 直接发 HTTP 请求，或用 `sentry-cli` |
| DSN/token 泄漏的后果 | 任何人可以拿着公开的 DSN 灌垃圾事件到你的项目（文档原话：这是小概率的滥用场景，Sentry 有 IP 屏蔽等控制手段） | Token 泄漏 = 按 scope 拿到组织数据的读/写权限，风险远高于 DSN 泄漏 |

来源：`docs.sentry.io/concepts/key-terms/dsn-explainer.md`、`docs.sentry.io/api/auth.md`。

**判断方法**：任务动词是"上报/发送/捕获错误"→ ingestion；动词是"查询/列出/解决/分派/统计"→ Web API。

## DSN 是什么、长什么样

DSN（Data Source Name）在创建 Sentry 项目时自动生成，告诉 SDK 把事件发去哪个项目。结构：

```
{PROTOCOL}://{PUBLIC_KEY}:{SECRET_KEY}@{HOST}{PATH}/{PROJECT_ID}
```

示例（来自官方文档）：

```javascript
Sentry.init({ dsn: "https://public@sentry.example.com/1" });
```

- `SECRET_KEY` 部分已事实上废弃，SDK 仍会兼容旧格式但不再要求。
- **每个 Sentry 项目一个独立 DSN**。如果一个应用有前端 + 后端两部分，官方建议拆成两个 Sentry 项目、两个 DSN 分别接，方便按组件归因、做分布式追踪、分配责任团队。
- DSN 未配置或为空时，SDK 不会发起任何网络请求（不会报错，只是静默不上报）。
- 找 DSN 的位置：项目设置里的 **Client Keys (DSN)** 页面（`sentry.io/orgredirect/organizations/:orgslug/settings/projects/:projectId/keys/`），或通过 Web API 的 [`GET /api/0/projects/{org}/{project}/keys/`](organizations-and-projects.md#client-keysdsn) 用 auth token 查询（见下面"两者的交界点"）。
- **DSN 可以旋转/吊销**（如果怀疑泄漏被滥用），在同一个 Client Keys 页面操作。

来源：`docs.sentry.io/concepts/key-terms/dsn-explainer.md`。

## Ingestion：装 SDK，不要手搓 HTTP

Sentry 的官方立场（写在 `llms.txt` 给 AI 助手的说明里）：**SDK 版本、初始化选项经常变，不要凭训练记忆编，用官方 SDK 而不是自己拼 ingestion 协议的原始 HTTP 请求（Envelope 格式）**。Envelope 协议本身是公开的（文档在 `develop.sentry.dev/sdk/data-model/envelopes/`），但本 skill 不展开——它是给 SDK 作者用的底层协议，不是给应用开发者的推荐接入方式。

最小接入模式（各语言大同小异，以下两个来自官方 Quickstart，⚠ 文档原文未实测）：

**Python (`sentry-sdk`)**：

```python
import sentry_sdk

sentry_sdk.init(
    dsn="https://<key>@o<orgId>.ingest.sentry.io/<projectId>",
    send_default_pii=True,      # 附带 IP/请求头等用户上下文，视隐私要求决定是否开启
    traces_sample_rate=1.0,     # 需要 tracing 才设置；纯错误监控可省略
)
```

- 手动上报（不依赖自动捕获）：

```python
import sentry_sdk

try:
    a_potentially_failing_function()
except Exception as e:
    sentry_sdk.capture_exception(e)

sentry_sdk.capture_message("Something went wrong")  # 上报一条无异常的消息
```

**Node.js (`@sentry/node`)**：必须在其他模块 `require`/`import` 之前完成 `Sentry.init()`，否则自动埋点可能失效。

```javascript
// instrument.js —— 必须最先被 require
const Sentry = require("@sentry/node");

Sentry.init({
  dsn: "https://<key>@o<orgId>.ingest.sentry.io/<projectId>",
  tracesSampleRate: 1.0, // 可选
});
```

```javascript
// 应用入口，第一行
require("./instrument");
const http = require("http");
// ... 其余代码
```

**关键术语**（来自 `docs.sentry.io/platforms/python/usage.md`）：
- **event**：一次上报（通常是一个错误/异常）。
- **issue**：多个相似 event 的聚合分组，Sentry 按"指纹"（fingerprint）自动分组。
- **capturing**：上报这个动作本身叫 capture（`capture_exception`/`capture_message` 等 API）。

**其他语言/框架**：本 skill 不逐个复述。装哪个包、`init()` 支持哪些选项，直接查 `docs.sentry.io/platforms/<language>.md`（如 `platforms/go.md`、`platforms/java.md`、`platforms/php.md`），或用 `https://<page-url>.md` 后缀拿纯 Markdown。llms.txt 里列出的平台：.NET、Android、Apple(iOS/macOS/tvOS/…)、Dart/Flutter、Elixir、Go、Godot、Java、JavaScript（及一堆前端/后端框架）、Kotlin、Native、Nintendo Switch、PHP、PlayStation、PowerShell、Python、React Native、Ruby、Rust、Unity、Unreal、Xbox。

**环境变量约定**：官方建议 DSN 走 `SENTRY_DSN`（浏览器端不适用，因为没有环境变量概念）环境变量，不要硬编码进源码——即便 DSN 泄漏风险低，也别把它提交进代码仓库。

## Web API：直接 HTTP + auth token

这是本 skill 剩余 reference 文件的主体。核心事实：

- Base URL：`https://{region}.sentry.io/api/0/...`（`region` 通常是 `us` 或 `de`，也可能是裸 `sentry.io`，见 SKILL.md「先确认的 3 件事」）。
- 鉴权：`Authorization: Bearer <auth_token>`。
- 全部走标准 REST + JSON，响应用 HTTP 状态码 + `Link` header 分页。

详见 `auth-and-tokens.md`、`organizations-and-projects.md`、`issues.md`、`events.md`、`releases-and-deploys.md`、`alerts-and-webhooks.md`。

## 常见任务该走哪条路

| 任务 | 走哪条路 | 理由 |
| :--- | :--- | :--- |
| "帮我的 FastAPI 服务接入 Sentry 错误监控" | Ingestion（装 `sentry-sdk`） | 目标是让应用自己上报，不是查已有数据 |
| "查一下我这个项目最近 24 小时的未解决 issue" | Web API（auth token） | 读取动作 |
| "把这个 issue 标记为已解决" | Web API（auth token，`event:write` scope） | 写入动作，DSN 做不到 |
| "创建一个新的 Sentry 项目并拿到它的 DSN" | 先 Web API 创建项目 + 查 Client Key，再把查到的 DSN 交给 SDK | 两段接力，见下面"交界点" |
| "CI 里给这次构建打一个 release、关联 commit" | Web API（`project:releases` scope），或 `sentry-cli releases` | release 管理属于 Web API 表面，`sentry-cli` 底层也是调同一套 API |
| "上传 source map" | 通常用 `sentry-cli` 或构建插件（webpack/vite plugin），底层调 Web API 的 release 文件上传 endpoint | 本 skill 不展开 CLI/插件细节，见 `docs.sentry.io/cli/dif.md` |

## 两者的交界点：用 Web API 查 DSN

"创建项目并让它开始上报"这种任务，天然要跨两套 API：

1. 用 Web API + auth token 创建项目：`POST /api/0/organizations/{org}/projects/`（细节见 `organizations-and-projects.md`）。
2. 用 Web API + auth token 查这个项目的 Client Key（DSN 就在响应的 `dsn.public` / `dsn` 字段里）：`GET /api/0/projects/{org}/{project}/keys/`。
3. 把第 2 步拿到的 DSN 字符串交给 SDK 的 `init(dsn=...)`——**这一步之后就切换到 ingestion 表面了，不再需要 auth token**。

不要把 auth token 传给 SDK 的 `dsn=` 参数，也不要指望用 DSN 去调 `POST /api/0/organizations/.../projects/`——两个方向各管各的。
