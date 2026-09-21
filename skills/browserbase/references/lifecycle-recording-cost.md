# Browserbase：会话生命周期、超时、Keep-Alive、可观测性与成本控制

> ⚠ 本文件全部内容整理自 https://docs.browserbase.com 的已抓取页面（抓取于 2026-09-21），**未使用真实 API Key 验证**，是纯文档转写稿。所有字段名、状态枚举、限额数字均按文档原文转录；凡文档未明确说明或几处文档互相矛盾的地方，已用 `⚠ 文档未说明` / `⚠ 文档自相矛盾` 标出。实际调用报错请优先信任真实 API 返回，而不是本文件。

## 目录

1. [会话终止的四种场景](#1-会话终止的四种场景)
2. [超时（Timeouts）](#2-超时timeouts)
3. [Keep-Alive](#3-keep-alive)
4. [成本控制清单（重点）](#4-成本控制清单重点)
5. [可观测性（Observability）](#5-可观测性observability)
6. [文件：下载 / 上传 / 截图 / PDF](#6-文件下载--上传--截图--pdf)
7. [用量追踪 / Measuring Usage](#7-用量追踪--measuring-usage)
8. [区域（Regions）与速度优化](#8-区域regions与速度优化)
9. [并发（Concurrency）：并发上限 vs 创建速率上限](#9-并发concurrency并发上限-vs-创建速率上限)

---

## 1. 会话终止的四种场景

来源：`platform/browser/getting-started/manage-browser-session.md`。一个 Browserbase 浏览器会话（session）只会以下面四种方式之一结束：

1. **自动超时（Automatic timeout）**
   会话在项目级别有一个默认超时（project-level default timeout），创建会话时可以覆盖。长任务应启用 [Keep-Alive](#3-keep-alive)。

2. **手动终止（Manual termination）**
   显式结束会话的三种方式：
   - 在自动化代码里调用 `browser.close()`（Playwright/Puppeteer）或 `driver.quit()`（Selenium）
   - 调用 Sessions API
   - 对 keep-alive 会话调用 `POST /v1/sessions/{id}` 释放（见下文 `REQUEST_RELEASE`）

3. **未处理的异常（Unhandled errors）**
   自动化代码里未捕获的异常会导致脚本与浏览器断开连接，从而提前终止会话。常见场景：网络中断、未捕获的异常、超出资源限制。文档建议在代码里做好错误处理与清理逻辑，避免会话提前终止。

4. **CDP 空闲超时（CDP inactivity timeout）**
   CDP（Chrome DevTools Protocol）连接在 **10 分钟内没有任何 CDP 命令** 就会被关闭。如果脚本长时间持有一个会话但不发送任何 CDP 命令（例如在等待一个很慢的 LLM 调用），连接会被终止。

   解决方法是定期发送一个轻量的心跳 CDP 命令：

   ```javascript
   // Node.js —— 每 5 分钟发一次心跳，防止 CDP 空闲超时
   setInterval(async () => {
     await page.evaluate(() => undefined);
   }, 5 * 60 * 1000);
   ```

   ```python
   import asyncio

   # Python —— 每 5 分钟发一次心跳，防止 CDP 空闲超时
   async def heartbeat(page):
       while True:
           try:
               await asyncio.sleep(5 * 60)
               await page.evaluate("undefined")
           except Exception:
               break

   asyncio.create_task(heartbeat(page))
   ```

   ⚠ 文档未说明：这个 10 分钟 CDP 空闲超时和下面第 2 节的「session timeout」是两个不同的计时器——CDP 空闲超时只看有没有发 CDP 命令，session timeout 看的是会话创建以来的总时长（或 `timeout` 参数）。两者互不替代，长任务通常需要同时应对。

### 调试已结束的会话

会话结束后，用 [Session Inspector](#5-可观测性observability) 分析：Session Replay（回放）、Network Monitor、Console & Logs、Performance。

---

## 2. 超时（Timeouts）

**用途**：控制一个会话从创建起最长能运行多久，超过后自动终止，防止会话无限期运行。

### 关键参数/字段

| 层级 | 配置方式 | 字段 | 默认值 | 范围 |
|---|---|---|---|---|
| 项目级（Project-wide） | Dashboard → Project settings 的 toggle | `defaultTimeout`（Project 对象字段，来自 `GET /v1/projects/{id}`） | 项目设置的默认值 | — |
| 会话级（Per-session） | `POST /v1/sessions` 请求体 | `timeout`（integer，单位秒） | 未传时使用项目的 `defaultTimeout` | **最小 60 秒，最大 21600 秒（6 小时）** |

这个 min/max 数字直接来自 OpenAPI spec（`POST /v1/sessions` 请求体 `timeout` 字段：`minimum: 60`, `maximum: 21600`）。

### 示例

```typescript
// Node.js SDK —— 会话超时设为 3600 秒（1 小时），覆盖项目默认值
import Browserbase from "browserbase";

const bb = new Browserbase({ apiKey: process.env.BROWSERBASE_API_KEY! });
const session = await bb.sessions.create({
  timeout: 3600,
});
```

```python
# Python SDK
from browserbase import Browserbase
import os

bb = Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])
session = bb.sessions.create(
    api_timeout=3600  # 注意：Python SDK 的参数名是 api_timeout，不是 timeout
)
```

```bash
curl --request POST \
  --url https://api.browserbase.com/v1/sessions \
  --header 'Content-Type: application/json' \
  --header 'X-BB-API-Key: <api-key>' \
  --data '{"timeout": 3600}'
```

### `TimeoutError` 的形状

一旦会话运行超过设定的超时值，文档给出的错误信息形状是：

```
TimeoutError: Timeout _____ms exceeded
```

`_____` 是实际超时的毫秒数占位符（文档原文如此，是一段占位符文案，不是某个固定数字）。

### 注意事项

- **设置自定义 `timeout` 并不会让会话在断开连接后存活。** 只要客户端断开连接（disconnect），会话立刻结束，无论 `timeout` 设的是多少。要跨断连存活，必须配合 [Keep-Alive](#3-keep-alive)。
- 会话超时上限**固定是 6 小时，与计划（plan）无关**——`account/billing/plans.md` 的 Free 计划例外：Free 计划的会话时长上限是 **15 分钟**，不是 6 小时；Developer / Startup / Scale 才是 6 小时上限。
- 一旦会话超时（timed out），该会话就不能再被使用。
- 项目级默认超时可以在 Dashboard 的 Settings 里通过一个 toggle 修改；如果你要的默认值不在 toggle 提供的选项里，就在创建会话时用 `timeout` 参数显式传。

---

## 3. Keep-Alive

**用途**：让会话在客户端断开连接（disconnect）之后继续存活、可被重新连接，而不是断开即结束。

### Keep-Alive 解决的问题和 Timeout 不是一回事

来源：`platform/browser/long-sessions/overview.md` 的对照表，原样保留：

| Feature | Problem it solves |
|---|---|
| **Session Timeouts** | "我需要会话运行得比默认超时更久" |
| **Keep Alive** | "我需要断开再重连，而不是让会话结束" |

以及 `keep-alive.md` 的另一张对照表：

| | 连接关闭时会发生什么 |
|---|---|
| **不开 Keep Alive** | 会话结束 |
| **开了 Keep Alive** | 会话保持可用，等待重连 |

**两者可以叠加使用**（既要断连存活，又要跑得久）：

```typescript
const session = await bb.sessions.create({
  keepAlive: true,
  timeout: 3600, // 1 小时
});
```

叠加后，Keep-Alive 会话仍然**遵守 session timeout**——超过 `timeout` 之后，即便开了 keepAlive，会话也会被终止。

### 关键参数/字段

| 字段 | 位置 | 类型 | 说明 |
|---|---|---|---|
| `keepAlive` | `POST /v1/sessions` 请求体 | boolean | 设为 `true` 使会话在断连后保持存活可重连 |
| `status` | `POST /v1/sessions/{id}` 请求体 | string，枚举值仅 `REQUEST_RELEASE` | 请求释放（关闭）会话 |

⚠ 文档自相矛盾：OpenAPI spec 对 `keepAlive` 字段的描述写的是 "Available on the **Hobby Plan** and above"，但当前公开计划列表（`account/billing/plans.md`）里根本没有叫 "Hobby" 的计划，计划名是 Free / Developer / Startup / Scale。而 `platform/browser/long-sessions/keep-alive.md` 和 `overview.md` 两篇正文都只说「仅限付费计划（paid plans）」。判断：OpenAPI 里的 "Hobby Plan" 字样是过时文案，应以「Developer 及以上」为准，但建议拿到真实 key 后用 Free 计划账号实测一次 `keepAlive: true` 确认到底是被拒绝还是被忽略。

### 示例

**创建 keep-alive 会话：**

```typescript
// Node.js SDK
const bb = new Browserbase({ apiKey: process.env.BROWSERBASE_API_KEY! });
const session = await bb.sessions.create({
  keepAlive: true,
});

// 之后重连要用同一个 connectUrl
console.log("Connect URL:", session.connectUrl);
```

```python
# Python SDK
bb = Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])
session = bb.sessions.create(
    keep_alive=True
)
print("Connect URL:", session.connect_url)
```

**释放（关闭）一个 keep-alive 会话——`REQUEST_RELEASE`：**

```typescript
// Node.js SDK
await bb.sessions.update(session.id, {
  status: "REQUEST_RELEASE",
});
```

```python
# Python SDK
bb.sessions.update(
    session.id,
    status="REQUEST_RELEASE"
)
```

```bash
curl --request POST \
  --url https://api.browserbase.com/v1/sessions/<session-id> \
  --header 'Content-Type: application/json' \
  --header 'X-BB-API-Key: <api-key>' \
  --data '{"status": "REQUEST_RELEASE"}'
```

### ⚠ 计费警告（原文逐字保留，这是本文件最重要的一段）

> "Stop your keep alive sessions explicitly when no longer needed. They'll time out eventually, but you may be charged for the unneeded browser minutes."

以及 `keep-alive.md` 里另一处措辞几乎相同的提示：

> "Release keep alive sessions when you're done to avoid being charged for unused browser minutes."

也就是说：**keep-alive 会话不会自动省钱**——它只是不会因为断连而结束，但只要没有显式 `REQUEST_RELEASE`，它会一直计费到达到 `timeout`（默认或你设置的值，最长 6 小时）为止。忘记释放的 keep-alive 会话是本领域最典型、最容易返工的计费陷阱。

### 注意事项

- Keep-Alive 会话的 `connectUrl` 在断连后**可以复用**去重连同一个会话；⚠ 文档未明确说明：对于**非** keep-alive 的普通会话，一旦断连会话就结束，`connectUrl` 是否严格意义上"一次性失效"文档没有用一句话直接断言，只是从「reconnect using the same connect URL」这类表述反推出来的，建议实测验证。
- Keep-Alive 也有一个文档明确提到的**省钱**用法：如果你要跑很多个「单次运行时间远低于 1 分钟」的短任务，用一个 keep-alive 会话反复复用，可以避开逐次创建新会话触发的「每次会话至少 1 分钟计费」这条规则（见下节成本控制清单）。原文措辞：「Billing optimization: keep alive lets you avoid minimum browser usage charges if running many short-lived sessions (under 1 minute)」。

---

## 4. 成本控制清单（重点）

来源：`optimizations/cost/cost-optimization.md`、`optimizations/cost/measuring-usage.md`、`account/billing/plans.md`、`platform/browser/long-sessions/*`、`platform/identity/proxies.md`。这是本领域最容易踩坑、也是这份技能包最需要"随手可查"的一节，按优先级列出：

1. **永远做好释放路径**：会话结束前主动调用 `status: REQUEST_RELEASE`（keep-alive 会话必须这么做），或者让非 keep-alive 会话尽快自然超时——不要"创建了就不管"。已开 keep-alive 但没有释放路径的会话，会一直计费到 `timeout` 上限（最长 6 小时）为止。
2. **不要为 `keepAlive: true` 的会话省略释放逻辑**。如果你的代码只是"创建会话 → 用一下 → 忘记关"，keepAlive 会把这个疏忽从几十秒放大成最多 6 小时的计费。写代码时把 `REQUEST_RELEASE` 放在 `finally` / `try...finally` 里，和 `browser.close()` 同级。
3. **1 分钟最低计费**：浏览器时间按分钟计费，**每个会话至少收 1 分钟的费用**，哪怕你只用了 5 秒就关掉了。所以「创建大量短会话」比「创建少量长会话、内部复用」更贵——短任务应该复用同一个会话（存 `sessionId`，用 `sessionId` 查询参数重连），而不是每个短任务都新建一个会话。
4. **代理带宽单独计费，且有 1 MB 最低消费**：文档原文（`platform/identity/proxies.md`）——"Sessions using Browserbase proxies have a 1 MB minimum. Any usage thereafter is rounded to the nearest MB." 代理用量按"经过代理的总字节数"计（网页内容、下载、媒体文件、HTTP 头、认证数据、加密开销……所有经过代理服务器的流量都算）。不需要代理时不要设 `proxies: true`，能省一笔。
5. **Agents / Search / Fetch / Extract 各有独立的按月额度**，和浏览器分钟数、代理 GB 是三套不同的预算，超额后各自按各自的费率计费（见下表）。一个同时用了 Sessions + Agents + Search 的工作流，会同时消耗三种不同的额度，容易被漏算进成本估算。
6. **图片加载可关，但要看场景**：为节省代理带宽，可以用 `page.route()` / request interception 拦截 `image` 类型请求。⚠ 但文档明确警告：很多 bot 防护系统依赖图片和字体加载来判断"这是不是真实浏览器行为"，拦截请求可能反而让会话被识别为 bot、拖累成功率。仅在确认目标站点没有 bot 防护时使用这个优化。
7. **短时、事件驱动的任务优先考虑 Functions（`platform/runtime/overview`）而不是手动管理 Session**：文档原文列出的卖点是 "No minimum runtime waste"（不吃最低计费）、"Zero infrastructure overhead"、"Automatic cleanup"。⚠ 文档未说明：Functions 具体的计费方式本文件没有再展开（材料范围之外），只能确认它和 Session 是不同的执行模型；需要用到 Functions 时应单独查证。
8. **大规模用量找销售拿折扣**：文档原文提示——如果要规模化使用，联系 `hello@browserbase.com` 询问批量折扣（bulk usage discounts）。

### 各计划的费率速查表（来自 `account/billing/plans.md`）

| | Free $0 | Developer $20 | Startup $99 | Scale |
|---|---|---|---|---|
| **浏览器小时额度** | 1 hr | 100 hrs | 500 hrs | Flexible |
| *超额费率* | N/A | $0.12/hr | $0.10/hr | Custom |
| **代理额度** | 0 GB | 1 GB | 5 GB | Usage-based |
| *代理超额费率* | N/A | $12/GB | $10/GB | Custom |
| **并发上限** | 3 | 25 | 100 | 250+ |
| **单会话最长时长** | 15 分钟 | 6 小时 | 6 小时 | 6+ 小时 |
| **会话创建速率** | 5/分钟 | 25/分钟 | 50/分钟 | 150+/分钟 |
| **Agents 额度** | 3 次调用 | 15 次调用 | 50 次调用 | Custom |
| **Search 额度 / 速率** | 1,000 次 / 2 次/秒 | 1,000 次 / 2 次/秒 | 1,000 次 / 2 次/秒 | Custom |
| *Search 超额费率* | N/A | $7/千次 | $7/千次 | Custom |
| **Fetch 额度 / 速率** | 1,000 次 / 5 次/秒 | 1,000 次 / 5 次/秒 | 10,000 次 / 5 次/秒 | Custom |
| *Fetch 超额费率* | N/A | $1/千次 | $0.5/千次 | Custom |
| *Extract 超额费率* | N/A | $4/千次 | $4/千次 | Custom |
| **数据留存** | 7 天 | 7 天 | 30 天 | 30+ 天 |

⚠ 文档自相矛盾：`welcome/getting-started.md` 原文写 Free 计划包含 "One browser session running at a time"（并发 1），而 `account/billing/plans.md` 定价表明确写 Free 计划 **Concurrency: 3**。两者互相矛盾。以定价表（更像是当前权威数字）为准，但建议用真实 Free 账号 key 实测确认——如果实测发现只能跑 1 个并发，说明 pricing 表是错的，getting-started 页反而对。

Fetch/Extract 走代理时费率更高：Fetch + 代理 $4/千次，Extract + 代理 $7/千次（`platform/identity/proxies.md` 及 billing 页的 Accordion 说明）。

---

## 5. 可观测性（Observability）

来源：`platform/browser/observability/observability.md`、`session-live-view.md`、`session-replay.md`、`recording-downloads.md`。

### Session Inspector（Dashboard）

在 Dashboard 点开任意一个会话（`https://www.browserbase.com/sessions/{session.id}`）即可打开 Session Inspector，包含：视频回放（Video replay，最多支持 10 个 tab）、Live view 入口、Status Bar（会话元数据）、Events & Pages 时间线、Stagehand tab（如果用了 Stagehand）、Console logs、Network logs。

**视频回放留存期**：非 BYOS 项目会话结束后保留 **31 天**；[BYOS](/account/enterprise/byos-setup-guide)（Bring Your Own Storage）项目只保留 **24 小时**。过期后 Session Inspector / Session Replay API / Recording Downloads API 都拿不到这个录像了；要长期保存必须在留存窗口内下载成 MP4（见下文 Recording Downloads）。

### Session Live View

**用途**：实时观看并可交互操控一个正在运行的会话（点击、输入、滚动）。

**关键参数/字段**：

| 字段 | 来源 | 说明 |
|---|---|---|
| `debuggerFullscreenUrl` | `GET /v1/sessions/{id}/debug` 响应 | 全屏 Live View 链接（无浏览器边框） |
| `debuggerUrl` | 同上 | 带边框、模拟真实浏览器外观的 Live View 链接 |
| `pages[].debuggerUrl` / `pages[].debuggerFullscreenUrl` | 同上 | 每个 tab 各自的 Live View 链接 |
| `wsUrl` | 同上 | Live View 的 WebSocket 端点 |

**Endpoint**: `GET /v1/sessions/{id}/debug`

**示例**：

```typescript
const liveViewLinks = await bb.sessions.debug(session.id);
const liveViewLink = liveViewLinks.debuggerFullscreenUrl;
console.log(`Live View Link: ${liveViewLink}`);
```

```python
live_view_links = bb.sessions.debug(session.id)
live_view_link = live_view_links.debuggerFullscreenUrl
```

**Human-in-the-loop 使用场景（文档明确列出的用途）**：

- **调试与可观测**：实时看正在发生什么，也可以分享给同事/用户看
- **Human in the loop**：需要人瞬间接管或输入的场景——
  - 处理 iframe：加载的第三方内容可能随时变化或报错，需要人工介入
  - **委托凭证（delegate credentials）**：把控制权交给终端用户本人，让他自己输入密码/验证码——这正是处理 **CAPTCHA / 2FA 人工接管**的标准做法，Browserbase 不要求你把用户的登录凭证经手一遍
  - 上传文件：结合 [uploads guide](#6-文件下载--上传--截图--pdf) 通过 Live View 手动上传
- **嵌入（Embedding）**：嵌入到自己的桌面 / 移动端应用里

**嵌入方式**：把 Live View 链接放进一个 `<iframe>`：

```html
<!-- 只读 -->
<iframe
  src="{liveViewLink}"
  sandbox="allow-same-origin allow-scripts"
  allow="clipboard-read; clipboard-write"
  style="pointer-events: none;"
/>

<!-- 可读写（人工可接管操作） -->
<iframe
  src="{liveViewLink}"
  sandbox="allow-same-origin allow-scripts"
  allow="clipboard-read; clipboard-write"
/>
```

移动端 Live View：把 session 的 `browserSettings.viewport` 设成手机尺寸（如 360×800）即可展示移动端视图；虚拟键盘官方不保证支持，需要自己转发按键事件。

**断连处理**：会话结束时 iframe 会 `postMessage` 一条 `"browserbase-disconnected"` 消息，可监听后做清理。

### Session Replay（HLS 流式回放）

**用途**：把已结束会话的录像以 HLS（`.m3u8`）格式流式提供，方便嵌入到自己的应用里做回放播放器，而不是下载文件。

**Endpoint**：
- `GET /v1/sessions/{id}/replays` —— 拿到每个 tab（page）的元数据列表
- `GET /v1/sessions/{id}/replays/{pageId}` —— 拿到该 page 的 HLS `.m3u8` 播放列表（`Content-Type: application/vnd.apple.mpegurl`）

**关键参数/字段**：

| 字段 | 说明 |
|---|---|
| `pages[].pageId` | 每个 tab 的编号，从 `"0"` 升序 |
| `pages[].startTimeMs` / `endTimeMs` | **相对会话开始的毫秒数**，不是 Unix epoch |
| `pageCount` | 该会话记录的 tab 总数 |

**示例**：

```bash
curl https://api.browserbase.com/v1/sessions/$SESSION_ID/replays \
  -H "x-bb-api-key: $BROWSERBASE_API_KEY"

curl https://api.browserbase.com/v1/sessions/$SESSION_ID/replays/0 \
  -H "x-bb-api-key: $BROWSERBASE_API_KEY"
```

```typescript
const meta = await bb.sessions.replays.retrieve(sessionId);
const firstPage = meta.pages[0];
const playlist = await bb.sessions.replays.retrievePage(sessionId, firstPage.pageId);
const m3u8 = await playlist.text();
```

**注意事项**：

- 播放列表里的分段 URL（segment URL）是签名的、**签发后 6 小时过期**；过期后重新拉一次播放列表即可拿到新的签名 URL。
- **不要直接从浏览器前端调用这个 API**——会暴露你的 `BROWSERBASE_API_KEY`。推荐做法是自己的后端代理这个请求，把 `.m3u8` 原样转发给前端，播放器再直接去 CDN 拉分段（分段 URL 本身是签名的，不需要经过你的后端）。
- 每个会话最多记录 **10 个并发 tab**；超过 10 个之后新开的 tab 不会出现在回放里。
- 播放列表接口 `GET /v1/sessions/{id}/replays/{pageId}` 限流为**每个项目每分钟 120 次请求**（持续 2 RPS，允许短时突发超过 2 RPS，只要每分钟总数不超 120）。超限返回 `429`。
- 留存窗口过期（非 BYOS 31 天 / BYOS 24 小时）后，两个 replay 端点都返回 `404 Not Found`，响应体 `{"message": "Replay not found"}`——和"这个会话本来就没录像"返回的错误完全一样，无法从错误本身区分是"过期了"还是"从没录过"。
- 创建会话时传 `browserSettings.recordSession: false` 可以完全跳过录制；这类会话的 replay 端点同样返回上面那个 404。

### Recording Downloads（异步 MP4 文件）

**用途**：把已结束会话的录像组装成可下载的 MP4 文件，每个 tab（page）一个文件，适合归档 / 离线审阅，区别于 Session Replay 的"流式嵌入播放"。

**Endpoint**：
- `POST /v1/sessions/{id}/recording/downloads` —— 触发组装
- `GET /v1/sessions/{id}/recording/downloads` —— 轮询状态、拿下载链接

**关键参数/字段**：

| 字段 | 说明 |
|---|---|
| `downloads[].pageId` | 会话内的 tab 编号，从 `"0"` 升序 |
| `downloads[].status` | 四态枚举：`NOT_REQUESTED` / `PENDING` / `COMPLETED` / `FAILED` |
| `downloads[].downloadUrl` | 短时签名 CDN 链接，仅当 `status: COMPLETED` 且非 BYOS 项目时才有 |
| `downloads[].completedAt` | MP4 生成完成时间，仅 `COMPLETED` 时才有 |

**状态含义**：

| Status | Meaning |
|---|---|
| `NOT_REQUESTED` | 该会话还没请求过下载 |
| `PENDING` | 正在排队或组装中 |
| `COMPLETED` | MP4 已就绪 |
| `FAILED` | 组装失败，重新 POST 即可重试该 page |

**流程（异步、两个调用同一路径）**：

1. `POST .../recording/downloads` —— 只要会话已结束且仍在留存窗口内，返回 `202`，每个 page 标记为 `PENDING`。**重复 POST 会重新入队所有 page 并重试失败的 page**，可以安全地重复调用。
2. `GET .../recording/downloads` —— 轮询每个 page 的状态，直到变成 `COMPLETED`（或 `FAILED`）。
3. 打开 `COMPLETED` page 的 `downloadUrl` 即可直接下载 MP4，保存为 `{sessionId}-{pageId}.mp4`。

**示例**：

```typescript
// Node.js
await bb.sessions.recording.downloads.create(sessionId);

let downloads;
do {
  await new Promise((resolve) => setTimeout(resolve, 3000));
  ({ downloads } = await bb.sessions.recording.downloads.list(sessionId));
} while (downloads.some((page) => page.status === "PENDING"));

for (const page of downloads) {
  console.log(page.pageId, page.status, page.downloadUrl);
}
```

```python
# Python
bb.sessions.recording.downloads.create(session_id)

while True:
    downloads = bb.sessions.recording.downloads.list(session_id).downloads
    if not any(page.status == "PENDING" for page in downloads):
        break
    time.sleep(3)
```

```bash
curl -X POST https://api.browserbase.com/v1/sessions/$SESSION_ID/recording/downloads \
  -H "x-bb-api-key: $BROWSERBASE_API_KEY"

curl https://api.browserbase.com/v1/sessions/$SESSION_ID/recording/downloads \
  -H "x-bb-api-key: $BROWSERBASE_API_KEY"
```

**注意事项**：

- **`downloadUrl` 签发后 6 小时过期**；`GET` 每次调用都会重新铸造（re-mint）一个新的签名 URL，链接过期了就再 `GET` 一次。
- 只有在会话已经**结束**、且仍在留存窗口内（非 BYOS 31 天 / BYOS 24 小时）才能请求下载。
- BYOS 项目：MP4 会写到你自己的 S3 bucket，API 响应里**不会**有 `downloadUrl` / `completedAt` 字段；文档特别提示"BYOS 只把最终编码好的 MP4 发到你的 bucket，组装过程中的原始帧数据仍会在 Browserbase 自己的存储里停留最长 24 小时"——如果合规要求"内容绝不落地 Browserbase 存储"，唯一办法是那些会话直接禁用录制（`recordSession: false`）。
- **POST 端点限流：每个项目每分钟 5 次请求**（因为每次调用都会触发一次组装任务）。BYOS 企业客户可申请更高限额。
- 每个会话最多 10 个并发录制 tab，一次 POST 请求会给所有已录制的 page 各生成一个 MP4。

---

## 6. 文件：下载 / 上传 / 截图 / PDF

来源：`platform/browser/files/*`。

### 下载（Downloads）

浏览器内触发的下载文件会**自动同步到 Browserbase 云存储**，不需要配置下载路径。文件名会被加上 Unix 时间戳后缀防止冲突（如 `report.pdf` → `report-1719265797164.pdf`；API 里查到的 `filename` 字段不含这个后缀）。

Playwright/Puppeteer 必须显式调用 CDP `Browser.setDownloadBehavior`，且 `downloadPath` 参数**必须原样写成字符串 `"downloads"`**（不是本地绝对路径），否则文件不会同步到 Browserbase 存储。常见踩坑：用绝对路径（如 `/tmp/downloads`）、漏调这个方法、`behavior` 没设成 `"allow"`。

**Endpoint**：
- `GET /v1/downloads?sessionId=...` —— 列出某会话的所有下载，支持按 `filename` / `mimeType` / `minSize` / `maxSize` / `createdAfter` / `createdBefore` / `limit`（1-100，默认 20）/ `offset` 过滤
- `GET /v1/downloads/{id}` —— `Accept: application/json` 拿元数据，`Accept: application/octet-stream`（默认）拿文件内容
- `DELETE /v1/downloads/{id}` —— 删除，成功返回 `204`

下载对象字段：`id` / `sessionId` / `filename` / `mimeType` / `size`（字节） / `checksum`（SHA256） / `createdAt`。

⚠ 大文件可能不会立刻出现在 `/downloads` 列表接口里，文档建议加重试逻辑轮询。

打开一个 PDF 的 URL 同样会触发下载到云存储（除非设置了 `enablePdfViewer`，见下文）。

### 上传（Uploads）

- **Playwright 直接上传**：用 `locator.setInputFiles("本地路径")` 上传本地文件（相对于当前工作目录）。
- **大文件**：走 `POST /v1/sessions/{id}/uploads`（`multipart/form-data`，字段 `file`），上传后再用 CDP `DOM.setFileInputFiles` 把服务器上的临时路径（`/tmp/.uploads/{fileName}`）绑定到页面的 file input 节点上。
- **通过 Live View 手动上传**：因为浏览器跑在远端，点击 file input 弹出的是远端浏览器的文件选择器，摸不到本地文件。做法是监听 Playwright 的 `page.on('filechooser')` 事件，拦截后弹出自己的本地文件选择 UI，再走上面的 Uploads API + `DOM.setFileInputFiles` 完成绑定。

**Endpoint**: `POST /v1/sessions/{id}/uploads`（`multipart/form-data`，`file` 字段必填）

### 截图（Screenshots）

推荐用 **CDP** 而不是各框架自带的截图方法，文档强调 CDP 截图明显更快、更省内存：

```typescript
const client = await defaultContext.newCDPSession(page);
const { data } = await client.send("Page.captureScreenshot", {
  format: "jpeg",
  quality: 80,
  captureBeyondViewport: true, // 去掉或设 false 则只截可视区域
});
const buffer = Buffer.from(data, "base64");
```

Selenium 没有 CDP 捷径，走的是 `driver.save_screenshot()` 这类框架自带方法。

### PDF

- **生成**：Playwright 的 `page.pdf({ path, format })`。
- **下载**：导航到一个 PDF URL 会自动触发下载并取消导航（这是浏览器行为，不是 Browserbase 特有逻辑），文件同样落进云存储，走 Downloads API 取回。
- **查看而非下载**：创建会话时设置 `browserSettings.enablePdfViewer: true`，PDF 会直接在 tab 里展示，而不是触发下载。

---

## 7. 用量追踪 / Measuring Usage

来源：`optimizations/cost/measuring-usage.md`、`platform/browser/getting-started/manage-browser-session.md`。

### Dashboard

`https://www.browserbase.com/overview` 提供实时用量视图：总会话数、浏览器分钟数、平均会话时长、代理数据量、会话状态分布（错误/超时/完成率）。支持按 24 小时 / 7 天 / 30 天 / 账单周期切换时间范围。

`https://www.browserbase.com/sessions` 可以浏览具体会话的历史记录（时长、状态、资源消耗）。

### Project Usage API

**Endpoint**: `GET /v1/projects/{id}/usage`

**用途**：以编程方式获取项目用量，用于自动生成用量报表、设置用量预警、接入外部计费/监控系统。

**关键参数/字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `browserMinutes` | integer | 累计浏览器分钟数 |
| `proxyBytes` | integer | 累计代理流量字节数 |

**示例**：

```typescript
import { Browserbase } from "@browserbasehq/sdk";

const bb = new Browserbase({ apiKey: process.env.BROWSERBASE_API_KEY! });
const projectId = process.env.BROWSERBASE_PROJECT_ID!;
const usage = await bb.projects.usage(projectId);
console.log(usage);
```

```python
from browserbase import Browserbase
import os

bb = Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])
project_id = os.environ["BROWSERBASE_PROJECT_ID"]
usage = bb.projects.usage(project_id)
```

⚠ 文档未说明：这个响应里只有 `browserMinutes` 和 `proxyBytes` 两个字段（根据 OpenAPI summary），文档正文没有给出 Agents / Search / Fetch / Extract 各自用量在这个端点里怎么体现——这几项有独立的按月额度（见成本清单），但没找到对应的用量查询字段，需要实测确认是否要另开端点查。

### 用 `userMetadata` 分段追踪用量

创建会话时可以传 `userMetadata`（任意 JSON 对象），之后可以用 `q` 查询参数按元数据过滤 `GET /v1/sessions`：

```
query = "user_metadata['client']:'enterprise_customer_xyz'"
```

查询字符串需要 URL encode（`[` → `%5B`，`]` → `%5D`，`:` → `%3A`）。典型用途：按客户 / 工作流类型 / 地区 / test id 分组统计用量。

---

## 8. 区域（Regions）与速度优化

来源：`optimizations/latency/multi-region.md`、`optimizations/latency/speed-optimization.md`。

### 可选区域

**关键参数/字段**：`region`（`POST /v1/sessions` 请求体字段，也出现在会话对象的响应里）

| 值 | 地点 | 备注 |
|---|---|---|
| `us-west-2` | Oregon | **默认值** |
| `us-east-1` | Virginia | |
| `eu-central-1` | Frankfurt | |
| `ap-southeast-1` | Singapore | |

**示例**：

```typescript
const session = await bb.sessions.create({
  region: "ap-southeast-1",
});
```

```python
session = bb.sessions.create(
    region="ap-southeast-1",
)
```

**注意事项**：显式创建会话（不指定 region 走默认值）把"创建会话"和"连接会话"解耦，这对并行跑批、长任务都有用，也是自定义 region 的前提。

### 速度优化要点（文档原文汇总）

架构层面：
- **就近部署，缩短 RTT**：把浏览器会话开在离你部署代码更近的 region，文档给的数字是可能带来 **8-9 倍**的性能提升，且不用改代码。CAPTCHA 求解、代理这类非本地能力会放大跨区域延迟的影响。
- **并行处理**：用 `Promise.all` / `asyncio.gather` 并发跑任务，而不是顺序跑。
- **把会话创建和应用初始化并行**：应用如果有启动准备步骤，可以和 Sessions API 的创建调用并行发起，抵消掉创建会话的感知延迟。
- **按场景选运行时**：I/O 密集型任务 Node.js 可能比 Python 快；CPU 密集型任务 Python 可能更合适（文档原话，未给出具体基准数字）。

会话配置层面：
- **避免多 tab 会话**：同一个会话开多个 tab 通常会拖慢性能，用多个单 tab 会话代替。
- **`waitUntil: "domcontentloaded"`**：导航时用这个而不是默认的 `"load"`，可以显著减少感知加载时间（不等外部资源如样式表、图片、iframe 全部加载完）。

```javascript
await page.goto("https://example.com", { waitUntil: "domcontentloaded" });
```

---

## 9. 并发（Concurrency）：并发上限 vs 创建速率上限

来源：`optimizations/concurrency/overview.md`、`account/billing/plans.md` 的 Accordion。这是一个常被忽略、但文档专门用手风琴强调的区分点：**并发上限（concurrency）和会话创建速率上限（session creation rate）是两条独立的限制**，谁都不能替代谁。

- **Max Concurrent Browsers（并发上限）**：同一时刻能运行的会话总数。
- **Session Creation Limit（创建速率上限）**：任意 60 秒滚动窗口内能创建的新会话数。

**触发条件**：两个限制任意一个被命中，新建会话请求都会收到 `429 Too Many Requests`；请求被直接丢弃（不排队）。

**关键参数/字段（按计划）**：

| Plan | Free | Developer | Startup | Scale |
|---|---|---|---|---|
| Max Concurrent Browsers | 3 | 25 | 100 | 250+ |
| Session Creation Limit / 分钟 | 5 | 25 | 50 | 150+ |

⚠ 见第 4 节：Free 计划的并发数字（3）与 `welcome/getting-started.md` 里"1 个并发"的说法矛盾。

### 官方给出的具体算例（"并发上限允许更多，但创建速率跟不上"）

原文原样保留（来自 `account/billing/plans.md` 手风琴）：

> For example: On the Startup Plan, your session creation limit is 50 per minute and your max concurrency is 100. It will take about 2 minutes to spin up all 100 sessions.

也就是说：Startup 计划并发上限是 100，但每分钟只能新建 50 个会话——即使你的代码想一次性开满 100 个并发会话，实际也要花大约 **2 分钟**才能全部创建完成，因为创建速率是瓶颈，不是并发上限。

**组织级 vs 项目级并发分配**：并发额度是在**组织（organization）级别**分配的。比如 Developer 计划总共 25 个并发，默认全部分给第一个项目；新建第二个项目时，会自动从第一个项目里"挪"1 个并发给新项目（因为每个项目至少要有 1 个并发才能跑）：

- Developer 计划两个项目：Project 1 拿到 24 个，Project 2 拿到 1 个
- Startup 计划两个项目：Project 1 拿到 99 个，Project 2 拿到 1 个
- Scale 计划：完全自定义

可以在 Dashboard 的 Settings → Organization → Projects 里手动调整每个项目的并发分配。

### 命中 429 之后：响应头 + 重试模式

命中限流时响应头包含（文档原文示例）：

```
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
x-ratelimit-limit: 25
x-ratelimit-remaining: 0
x-ratelimit-reset: 45
retry-after: 45
```

| 响应头 | 含义 |
|---|---|
| `x-ratelimit-limit` | 该时间窗口内允许的最大请求数 |
| `x-ratelimit-remaining` | 该窗口内剩余可用请求数 |
| `x-ratelimit-reset` | 距限流重置还有多少秒 |
| `retry-after` | 必须等待多少秒才能再次请求（[RFC 定义](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Retry-After)） |

文档给出的重试范式：带指数退避的重试封装，读取 `retry-after` 头作为基准等待时间：

```typescript
const MAX_RETRIES = 5;

async function createSessionWithRetry() {
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    try {
      return await bb.sessions.create();
    } catch (error: any) {
      if (error.status !== 429 || attempt === MAX_RETRIES - 1) throw error;
      const retryAfter = parseInt(error.headers?.["retry-after"] ?? "2", 10);
      const backoff = retryAfter * 1000 * Math.pow(2, attempt);
      await new Promise((resolve) => setTimeout(resolve, backoff));
    }
  }
}
```

```python
MAX_RETRIES = 5

async def create_session_with_retry():
    for attempt in range(MAX_RETRIES):
        try:
            return bb.sessions.create()
        except Exception as error:
            status = getattr(error, "status_code", None)
            if status != 429 or attempt == MAX_RETRIES - 1:
                raise
            retry_after = int(getattr(error, "headers", {}).get("retry-after", 2))
            backoff = retry_after * (2 ** attempt)
            await asyncio.sleep(backoff)
```

### 注意事项

- 短生命周期会话建议改用 keep-alive 复用同一个会话，而不是反复新建——既省创建速率额度，也省 1 分钟最低计费（见第 4 节）。
- 需要更大并发/创建速率，升级计划或联系 `support@browserbase.com`。
- 对高并发、事件驱动场景，文档建议考虑 Functions（`platform/runtime/overview`），号称自带并发管理和自动会话生命周期，不需要手动管理——⚠ 本文件未深入展开 Functions 细节，超出本次抓取范围。

---

内容整理自 https://docs.browserbase.com（抓取于 2026-09-21），未使用真实 API Key 验证，实际调用报错优先信任真实 API。
