---
name: browserbase
description: 接入 Browserbase（browserbase.com / docs.browserbase.com）云端无头浏览器基础设施的使用手册——涵盖原始会话管理 REST API（建会话、拿 CDP/Selenium 连接地址、列出/终止会话、录像与日志）、用 Playwright/Puppeteer/Selenium 驱动会话、Browserbase 自家的自然语言浏览器框架 Stagehand（act/extract/observe，@browserbasehq/stagehand 包）、完全托管的 Browserbase Agents 产品、代理/CAPTCHA 破解/Verified 反爬身份、会话生命周期与录像调试、以及按浏览器分钟/代理流量计费的费用模型。当用户提到 "Browserbase" "browserbase.com" "Stagehand" "docs.stagehand.dev" "@browserbasehq/sdk" "@browserbasehq/stagehand" "connectOverCDP" "无头浏览器 API" "云端浏览器" "remote Chrome session"，或要求写代码创建/驱动 Browserbase 浏览器会话、用自然语言操作网页时，应主动使用本技能，不要凭记忆编造字段名或端点、不要把 Stagehand v2/v3（基于 Playwright 的旧架构）的 API 形状套到当前 v4（CDP 原生架构）上、不要把 Stagehand（嵌入你代码里的库）和 Browserbase Agents（服务端托管的自主 agent 产品）混为一谈。
---

# Browserbase 接入指南

Browserbase（browserbase.com）是面向 AI agent 的云端浏览器基础设施："the Browser Agent Platform"——一个 API Key 下有 Browsers（远程 Chrome 会话，用 Playwright/Puppeteer/Selenium 驱动）、Stagehand（自然语言驱动浏览器的自家框架）、Browserbase Agents（完全托管的自主 agent）、Search、Fetch、Model Gateway 六块能力。本 skill 覆盖前四块里开发者最常需要的部分：原始会话管理、用标准自动化库驱动会话、Stagehand、代理/反爬身份、会话生命周期与计费。

## ⚠ 验证状态

**没有真实 API Key，本 skill 全部内容都是文档转录，未做过一次真实调用。** 每个 reference 文件顶部和关键结论处都标了 `⚠ 文档原文，未实测`。已知的几处**文档自身的矛盾/可疑之处**（不是我们编的，是抓取时发现的）列在下面"跨领域通用规则"第 7 条；一份按优先级排好、给拿到 Key 后的人用的验证清单在 `browserbase-workspace/verification-plan.md`。**在真实验证之前，任何"报错信息长什么样"的描述都不要当作调试依据，只当作起点。**

## 用之前先确认 3 件事

1. **两个完全独立的域名/包，不要混淆**：会话管理 REST API 在 `https://api.browserbase.com`（文档站 `docs.browserbase.com`，SDK 是 `@browserbasehq/sdk` / pip 包 `browserbase`）；Stagehand 是完全独立的产品，有自己的文档站 `docs.stagehand.dev`、自己的包（`@browserbasehq/stagehand` / pip 包 `stagehand` / Go 模块），版本号也独立（当前 v4，文档站同时还挂着 v2/v3 的旧文档，容易搜到过期内容）。
2. **鉴权**：REST API 固定用请求头 `x-bb-api-key: <BROWSERBASE_API_KEY>`（OpenAPI 规范里写作 `X-BB-API-Key`，HTTP 头大小写不敏感，两种写法功能等价；官方代码示例统一用小写）——**没有 `Bearer` 前缀**，key 本身就是头的值。Stagehand 不会替你读环境变量，必须在自己代码里 `os.environ[...]` / `process.env...` 读出来再显式传参。
3. **Stagehand v4 是 CDP 原生架构，不是包着 Playwright 的旧版本**——这是本 skill 存在的最大理由之一。如果你的训练记忆里 Stagehand 是"继承 Playwright 的 `Page` 对象、调 `page.act(...)`"，那是 v2/v3 的旧形状。v4 里 Stagehand 直接走 Chrome DevTools Protocol，**没有 Playwright/Puppeteer/Patchright 互操作层**；`act`/`extract`/`observe` 是 `Stagehand` 实例自己的方法，不挂在 `page` 上。详见 [`references/stagehand.md`](references/stagehand.md)。

## 30 秒跑通第一个请求

创建一个会话并用 Playwright 连接（Node.js，⚠ 文档原文）：

```bash
curl -X POST https://api.browserbase.com/v1/sessions \
  -H "Content-Type: application/json" \
  -H "x-bb-api-key: $BROWSERBASE_API_KEY" \
  -d '{}'
```

```javascript
import { chromium } from "playwright-core";
import { Browserbase } from "@browserbasehq/sdk";

const bb = new Browserbase({ apiKey: process.env.BROWSERBASE_API_KEY });
const session = await bb.sessions.create();
const browser = await chromium.connectOverCDP(session.connectUrl);

const context = browser.contexts()[0];
const page = context.pages()[0];
await page.goto("https://news.ycombinator.com/");
await browser.close();
console.log(`Recording: https://browserbase.com/sessions/${session.id}`);
```

成功创建返回 `201`，响应体含 `id`、`connectUrl`（WebSocket/CDP 地址）、`seleniumRemoteUrl`（Selenium 用的 HTTP 地址）、`status`、`expiresAt` 等字段（精确字段表见 [`references/sessions-rest.md`](references/sessions-rest.md)）。**用完一定要关**——见下方通用规则第 1 条，未显式关闭的会话会持续按分钟计费。

## 能力域导航

| 我想做什么 | 读 | 涉及的核心 endpoint / 包 |
| :--- | :--- | :--- |
| 先搞清楚该用 REST+库、Stagehand、还是 Browserbase Agents，或者根本用不到浏览器（Search/Fetch 就够） | [`choosing-your-approach.md`](references/choosing-your-approach.md) | — |
| 建会话、用 Playwright/Puppeteer/Selenium 连接并驱动、管理 Context（跨会话保留登录态）、扩展/视口/元数据 | [`sessions-rest.md`](references/sessions-rest.md) | `POST/GET/PATCH /v1/sessions*`、`/v1/contexts*`、`/v1/extensions*` |
| 用自然语言操作页面（Stagehand 的 act/extract/observe）、选浏览器来源（云端/本地/attach）、配置模型 | [`stagehand.md`](references/stagehand.md) | `@browserbasehq/stagehand` / `stagehand`（Python）包，无独立 REST 端点 |
| 代理、CAPTCHA 自动破解、Verified 反爬身份、允许域名限制、自定义 CA 证书 | [`identity-and-stealth.md`](references/identity-and-stealth.md) | `browserSettings.*`、`proxies`、`/v1/certificates*` |
| 超时/keep-alive、CDP 空闲断连、Live View/Replay/录像下载、用量与计费、并发与创建速率限制、区域 | [`lifecycle-recording-cost.md`](references/lifecycle-recording-cost.md) | `/v1/sessions/{id}/debug`、`/replays`、`/recording/downloads`、`/v1/projects/{id}/usage` |
| 报错处理、限流、Search/Fetch 的错误码 | [`errors-and-limits.md`](references/errors-and-limits.md) | 见文件内说明（官方无统一错误码表，是零散发现） |

## 跨领域的通用规则（写代码前必读）

1. **会话不显式关闭会持续计费，这是本平台最容易踩的坑。** 浏览器时长按分钟计费、**1 分钟最低消费**；`keepAlive: true` 的会话不会自己结束（会一直跑到超时上限 6 小时），文档原文明确写着"stop your keep alive sessions explicitly...you may be charged for the unneeded browser minutes"。写代码时永远要有一条"用完调 `bb.sessions.update(id, {status: "REQUEST_RELEASE"})`"的路径（`try/finally` 或等价机制），不要假设脚本正常退出就等于会话结束——异常退出、连接断开不等于服务端立刻停止计时到 0。
2. **新建会话有 5 分钟连接窗口，CDP 连接本身有 10 分钟空闲断连。** 会话创建后必须尽快连接，否则自动终止；连上之后如果长时间不发 CDP 命令（比如中间在等一次很慢的 LLM 调用），10 分钟不活动会被断开——需要长时间挂起的流程要发心跳（如 `page.evaluate(() => undefined)`）。这两个超时是独立的两件事，不要合并理解。
3. **`connectUrl` 是否可复用取决于有没有开 `keepAlive`。** ⚠ 文档未明确写"connect URL 单次性"这句话，但从 keep-alive 文档的措辞（"reconnect using the *same* connect URL"仅出现在 keepAlive 场景）推断：普通会话一旦断开就结束，它的 `connectUrl` 不能再用；只有 `keepAlive: true` 创建的会话，断开后还能用同一个 `connectUrl` 重连。写"重连"逻辑前先确认会话是不是 keep-alive 的，这条待真实验证确认（见 verification-plan.md）。
4. **Contexts（跨会话保留登录态）和 keepAlive（同一会话断线重连）是两个不相关的机制，容易被想成同一件事。** Context 解决的是"下次开新会话时还记得我登录过"；keepAlive 解决的是"这一个会话断线之后还能接回来"。两者可以同时用，但开了其中一个不代表另一个自动生效——想要"登录态在多次运行之间保留"，要用 Context + `persist: true`，不是 keepAlive。详见 [`sessions-rest.md`](references/sessions-rest.md)。
5. **CAPTCHA 自动破解默认开启，代理默认关闭——两个安全/反爬相关开关的默认值不对称。** `solveCaptchas` 默认 `true`（遇到验证码会自动尝试解决，耗时 5-30 秒，这段时间你的脚本在等它），`proxies` 默认 `false`。如果你只是想要一个"干净、不做任何额外网络/反爬处理"的会话用于内部工具测试，两个都要显式设置，不能假设都是关闭的。详见 [`identity-and-stealth.md`](references/identity-and-stealth.md)。
6. **三种"让 AI 操作浏览器"的方式不是同一件事，选错会导致预期完全对不上：** (a) Stagehand 的 `act`/`extract`/`observe` 是你代码里调用的单步原语，控制流还是你自己写；(b) Stagehand 也有自己的 `agent()`（⚠ 本 skill 未能确认 v4 是否仍保留此方法，v4 导航里没有独立的 agent 页面，标记为 `⚠ 文档未说明`，待验证）；(c) **Browserbase Agents**（`/v1/agents/runs`）是完全独立的服务端托管产品，你只给一句自然语言 `task`，整个循环（含浏览器会话、模型调用、Search、文件、shell）都在 Browserbase 那边跑,你只负责轮询结果。三者计费方式、可观测性、错误处理模型都不同。选型见 [`choosing-your-approach.md`](references/choosing-your-approach.md)。
7. **已发现的文档自身矛盾/可疑之处**（这些不是我们编的坑，是抓取比对多个官方页面后发现的不一致，真实验证时优先确认）：
   - `welcome/getting-started.md` 说免费版"一次只能跑一个会话"，但 `account/billing/plans.md` 的定价表写免费版并发数是 **3**——两个官方页面互相矛盾。
   - `POST /v1/sessions` 的 OpenAPI 规范里，`keepAlive` 字段的说明写着"Available on the Hobby Plan and above"，但当前公开的方案名称是 Free/Developer/Startup/Scale，**没有"Hobby"这个方案**——大概率是没更新的旧文案，其他页面统一说"付费方案即可"。
   - "Update a Session" 的 llms.txt 摘要说可以"更新其他可变字段"，但 OpenAPI 规范里 `POST /v1/sessions/{id}` 的请求体 schema 只定义了一个字段 `status`（且只接受枚举值 `REQUEST_RELEASE`）——在证实之前，只把这个端点当作"仅用于请求释放会话"，不要假设能改其他字段。
   详见各 reference 文件里对应位置的 `⚠ 文档自相矛盾` 标注。
8. **两条 API 基础设施是分开的、可以分别指向非生产环境。** Browserbase 会话管理走 `baseUrl`（`https://api.browserbase.com`），Stagehand 自己的托管服务（Model Gateway、server-side cache）走独立的 `apiUrl`（`https://api.stagehand.dev.browserbase.com`）。两个 SDK 都不读环境变量来决定这两个地址，必须显式传参覆盖。

## 目录结构

```
browserbase/
├── SKILL.md
├── references/
│   ├── choosing-your-approach.md   # REST+库 / Stagehand / Browserbase Agents / Search / Fetch 怎么选
│   ├── sessions-rest.md            # 建会话、Playwright/Puppeteer/Selenium 连接、Contexts、扩展/视口/元数据
│   ├── stagehand.md                # Stagehand v4：act/extract/observe、浏览器来源、模型配置、缓存
│   ├── identity-and-stealth.md     # 代理、CAPTCHA、Verified、允许域名、自定义 CA 证书
│   ├── lifecycle-recording-cost.md # 超时/keep-alive、可观测性、录像、计费、并发限制
│   └── errors-and-limits.md        # 报错、限流（官方无统一错误码表，本文件如实说明覆盖不到的部分）
└── evals/
    └── evals.json                  # 对照实验场景（打包时自动排除）
```

内容整理自 https://docs.browserbase.com 与 https://docs.stagehand.dev（抓取于 2026-09-21），**未使用真实 API Key/SDK 验证**，实际调用报错优先信任真实 API/SDK 而不是本 skill 的转录。
