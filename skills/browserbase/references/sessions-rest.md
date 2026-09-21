# Sessions REST API / SDK 参考（Playwright / Puppeteer / Selenium 直连）

> ⚠ 本文件是纯文档整理，未使用真实 API Key 做过任何调用验证。所有"行为如何"的描述均来自
> docs.browserbase.com 抓取页面与 OpenAPI 摘要的转录，不是实测结论。凡是超时时长、URL
> 是否可复用、计费行为等"意外/关键"结论，行内标注 `⚠ 文档原文，未实测`。真实调用报错时，
> 优先信任真实 API 返回，而不是本文件。

本文件覆盖的能力域：**用原始 REST API / 官方 SDK 创建并连接一个远程浏览器 session，然后自己
用 Playwright / Puppeteer / Selenium 驱动它**——即"自己写自动化逻辑"这条路径。

这与另外两条路径不同，分别由其他参考文件覆盖：
- **Stagehand**（`@browserbasehq/stagehand` / `stagehand` 包）：给 `act`/`extract`/`observe`
  这类自然语言原语，但控制流仍由你写。
- **Browserbase Agents**（`/v1/agents`、`/v1/agents/runs`）：全托管、自主的 Agent 产品，你只
  提交一个 `task`，Browserbase 内部（用 Stagehand）跑完整个循环。

## 目录

- [创建 Session](#创建-session)
- [List / Get / Update Session](#list--get--update-session)
- [连接：Playwright / Puppeteer / Selenium](#连接playwright--puppeteer--selenium)
- [最佳实践：使用默认 context/page](#最佳实践使用默认-contextpage)
- [连接时序陷阱](#连接时序陷阱)
- [Contexts：跨 session 持久化登录态](#contexts跨-session-持久化登录态)
- [Viewports](#viewports)
- [Session Metadata](#session-metadata)
- [Browser Extensions](#browser-extensions)
- [Node.js SDK / Python SDK](#nodejs-sdk--python-sdk)
- [Techniques：Dialogs / Timezones](#techniquesdialogs--timezones)

---

## 创建 Session

### 创建一个 Browser Session
**Endpoint**: `POST /v1/sessions`
**用途**: 在云端启动一个浏览器实例（一个"session"是 Browserbase 的基本单元）。创建成功后拿到
`connectUrl`（CDP/WebSocket，给 Playwright/Puppeteer 用）和 `seleniumRemoteUrl`（HTTP，给
Selenium 用），才能开始驱动浏览器。

**关键参数**（请求体 `application/json`，全部字段均可省略，省略即用默认值；来源：OpenAPI
`Sessions_create`）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `projectId` | string | 否 | 从 API Key 推断 | Project ID，Settings 页可查；不传则从 API Key 推断 |
| `extensionId` | string | 否 | — | 已上传的 Extension ID（`POST /v1/extensions` 的返回值） |
| `timeout` | integer | 否 | Project 的 `defaultTimeout` | 秒，session 自动结束前的时长。最小 60，最大 21600（6 小时） |
| `keepAlive` | boolean | 否 | — | 设为 `true` 使 session 在断开连接后仍保活。文档原文写"Available on the Hobby Plan and above"——⚠ 文档自相矛盾：当前公开的方案名称是 Free/Developer/Startup/Scale，没有"Hobby Plan"，这应是过期文案；`long-sessions` 系列页面写的是"仅付费方案（Developer 及以上）可用"，更可能是当前事实，但未实测确认 |
| `region` | string(enum) | 否 | `us-west-2` | `us-west-2` \| `us-east-1` \| `eu-central-1` \| `ap-southeast-1` |
| `userMetadata` | object | 否 | — | 任意 JSON 对象，用于打标签、后续按 `q` 查询（见下方 Session Metadata 章节） |
| `proxies` | boolean 或 数组 | 否 | — | `true` 用默认代理；或传数组做更细粒度配置（Browserbase 托管代理 / 外部代理 / 不用代理，可按 `domainPattern` 混用） |
| `proxySettings.caCertificates` | array\<uuid\> | 否 | `[]` | 要信任的 TLS 证书 ID 列表 |
| `browserSettings.context.id` | string | 是（若传 `context`） | — | 要复用的 Context ID |
| `browserSettings.context.persist` | boolean | 否 | `false` | 是否在浏览结束后把变更写回该 Context |
| `browserSettings.extensionId` | string | 否 | — | 与顶层 `extensionId` 同义，两个位置都能传（⚠ 文档未说明两者同时传时谁优先） |
| `browserSettings.viewport.width` / `.height` | integer | 否 | — | 浏览器视口宽高 |
| `browserSettings.blockAds` | boolean | 否 | `false` | 广告拦截 |
| `browserSettings.solveCaptchas` | boolean | 否 | `true` | 验证码自动求解 |
| `browserSettings.recordSession` | boolean | 否 | `true` | Session Replay 录制 |
| `browserSettings.logSession` | boolean | 否 | `true` | Session 日志记录 |
| `browserSettings.advancedStealth` | boolean | 否 | — | 已废弃，改用 `verified` |
| `browserSettings.verified` | boolean | 否 | — | Verified Browser 模式（文档提到 Scale 方案专属，⚠ 未在本文档核实是否所有付费方案通用） |
| `browserSettings.captchaImageSelector` / `.captchaInputSelector` | string | 否 | — | 自定义验证码图片/输入框选择器 |
| `browserSettings.os` | string(enum) | 否 | — | `windows` \| `mac` \| `linux` \| `mobile` \| `tablet`，仅用于 stealth/指纹模拟 |
| `browserSettings.allowedDomains` | array\<string\> | 否 | `[]` | 限制顶层页面导航只能到这些域名（含子域名）；只拦主 frame 导航，不拦 iframe/图片/脚本/XHR |
| `browserSettings.ignoreCertificateErrors` | boolean | 否 | `false` | 是否忽略 TLS 证书错误 |

**示例请求**

```bash
curl --request POST \
  --url "https://api.browserbase.com/v1/sessions" \
  --header "Content-Type: application/json" \
  --header "x-bb-api-key: $BROWSERBASE_API_KEY" \
  --data '{ "browserSettings": { "viewport": { "width": 1920, "height": 1080 } }, "timeout": 3600 }'
```

```javascript
import { Browserbase } from "@browserbasehq/sdk";

const bb = new Browserbase({ apiKey: process.env.BROWSERBASE_API_KEY });
const session = await bb.sessions.create({
  browserSettings: { viewport: { width: 1920, height: 1080 } },
  timeout: 3600,
});
```

```python
import os
from browserbase import Browserbase

bb = Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])
session = bb.sessions.create(
    browser_settings={"viewport": {"width": 1920, "height": 1080}},
    timeout=3600,
)
```

**示例响应**（201，关键字段；来源：OpenAPI `Session` schema + create 响应的额外字段）：
`{ "id": "...", "status": "RUNNING", "projectId": "...", "region": "us-west-2", "keepAlive": false,
"proxyBytes": 0, "contextId": null, "userMetadata": {}, "createdAt": "...", "expiresAt": "...",
"connectUrl": "wss://connect.browserbase.com/...", "seleniumRemoteUrl": "https://connect.browserbase.com/...",
"signingKey": "..." }`

**注意事项**
- `connectUrl`（WebSocket/CDP）和 `seleniumRemoteUrl`（HTTP）是两个不同端点，分别对应
  Playwright/Puppeteer 与 Selenium，不要混用（见下方连接章节）。
- `region` 的合法值只有 4 个，且默认 `us-west-2`；传其它字符串会怎样，⚠ 文档未说明（大概率
  校验失败，但未实测确认错误形态）。
- 计费口径：浏览器时间按分钟计费、每 session 最低 1 分钟；使用代理按 MB 计费、最低 1 MB；
  这些是文档原文表述，⚠ 文档原文，未实测。

---

## List / Get / Update Session

### List Sessions
**Endpoint**: `GET /v1/sessions`
**用途**: 列出账号下的 session（不分页字段，直接返回数组）。可按 `status` 过滤，或用 `q` 按
`userMetadata` 查询。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `status` | query, string(enum) | 否 | — | `PENDING` \| `RUNNING` \| `ERROR` \| `TIMED_OUT` \| `COMPLETED` |
| `q` | query, string | 否 | — | 形如 `user_metadata['env']:'staging'` 的查询串，直接调 REST 时要做 URL encode（SDK 会自动处理） |

**示例请求**

```bash
curl "https://api.browserbase.com/v1/sessions?status=RUNNING" \
  -H "x-bb-api-key: $BROWSERBASE_API_KEY"
```

**示例响应**：`Session` 对象数组，字段与创建响应的基础字段一致（不含 `connectUrl` 等连接信息）。

### Get a Session
**Endpoint**: `GET /v1/sessions/{id}`
**用途**: 取单个 session 的当前状态；响应里**包含** `connectUrl` / `seleniumRemoteUrl` /
`signingKey`（三者均标为非必填，⚠ 文档未说明具体哪些状态下会缺失——例如已结束的 session 是否
仍返回可用的 `connectUrl`）。

### Update a Session
**Endpoint**: `POST /v1/sessions/{id}`
**用途**: 主动结束一个还在跑的 session（在超时之前手动释放，避免多计费）。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `status` | string(enum) | 是 | — | 唯一合法值 `REQUEST_RELEASE` |

**示例请求**

```bash
curl -X POST "https://api.browserbase.com/v1/sessions/$SESSION_ID" \
  -H "Content-Type: application/json" \
  -H "x-bb-api-key: $BROWSERBASE_API_KEY" \
  -d '{"status": "REQUEST_RELEASE"}'
```

**注意事项**
- ⚠ 文档自相矛盾：`llms.txt` 对这个端点的摘要写的是"Close a Browserbase session by updating
  its status to REQUEST_RELEASE, **or update other mutable session fields**"，暗示还能改别的
  字段；但 OpenAPI 的请求体 schema 里 `status` 是唯一定义的属性，且只有一个枚举值
  `REQUEST_RELEASE`。在有相反证据之前，按**只支持 `status: REQUEST_RELEASE` 这一种调用**来用，
  不要假设能用这个端点改 `timeout`、`userMetadata` 等其它字段。
- 结束 session 更常见的方式其实是在自动化代码里调用 `browser.close()`
  (Playwright/Puppeteer) 或 `driver.quit()` (Selenium)，Browserbase 会在断开时自动处理终止；
  这个 REST 端点是"在你的代码断开之前，从外部/另一进程主动喊停"的场景。

---

## 连接：Playwright / Puppeteer / Selenium

创建 session 后，用 `connectUrl` 或 `seleniumRemoteUrl` 连接。三者中 Selenium 明显不同——它走
HTTP + 自定义请求头注入，而不是像另外两个那样直接拿一个 URL 去连。

### Playwright
**用途**: 用 `chromium.connectOverCDP()` 直接接到远程 Chromium 的 CDP 端点。

```javascript
import { chromium } from "playwright-core";
import { Browserbase } from "@browserbasehq/sdk";

const bb = new Browserbase({ apiKey: process.env.BROWSERBASE_API_KEY });
const session = await bb.sessions.create();

const browser = await chromium.connectOverCDP(session.connectUrl);

// 使用默认 context 和 page，见下方"最佳实践"
const context = browser.contexts()[0];
const page = context.pages()[0];
```

```python
from playwright.sync_api import sync_playwright
from browserbase import Browserbase
import os

bb = Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])
session = bb.sessions.create()

with sync_playwright() as playwright:
    browser = playwright.chromium.connect_over_cdp(session.connect_url)
    context = browser.contexts[0]
    page = context.pages[0]
```

### Puppeteer
**用途**: 用 `puppeteer.connect({ browserWSEndpoint })` 接到同一个 CDP 端点（Puppeteer 官方文档
只有 Node.js/TS，本材料中没有 Python 示例，⚠ 文档未说明 Python 下是否有对应连接方式——Python
生态里 Puppeteer 本身就不是官方产物）。

```javascript
import puppeteer from "puppeteer-core";
import { Browserbase } from "@browserbasehq/sdk";

const bb = new Browserbase({ apiKey: process.env.BROWSERBASE_API_KEY });
const session = await bb.sessions.create();

const browser = await puppeteer.connect({
  browserWSEndpoint: session.connectUrl,
});

// 使用默认 page
const page = (await browser.pages())[0];
```

**注意事项**
- Puppeteer 默认视口是 `800x600`；如果在 `browserSettings.viewport` 里设置了自定义尺寸，连接
  时还要额外传 `defaultViewport: null`，否则 Puppeteer 会用自己的默认值覆盖：

```javascript
const browser = await puppeteer.connect({
  browserWSEndpoint: session.connectUrl,
  defaultViewport: null, // 防止被 800x600 默认视口覆盖
});
```

### Selenium
**用途**: Selenium 走 **WebDriver 协议 / HTTP**，不是 CDP，所以不能直接拿 `connectUrl` 去连；
要用 `session.seleniumRemoteUrl` 作为 `RemoteConnection`/`Builder` 的 server 地址，并且**必须
自己在每个 HTTP 请求上注入认证头**（`x-bb-api-key` + `session-id`），因为 Selenium 的
WebDriver 客户端本身没有"额外 header"这个概念，需要包一层自定义 executor/connection 类。

```javascript
import { Builder } from 'selenium-webdriver';
import { Options } from 'selenium-webdriver/chrome';
import { Browserbase } from "@browserbasehq/sdk";

class BrowserbaseConnection {
  constructor(sessionId) {
    this.sessionId = sessionId;
  }
  getHeaders() {
    return {
      'x-bb-api-key': process.env.BROWSERBASE_API_KEY,
      'session-id': this.sessionId,
    };
  }
}

const bb = new Browserbase({ apiKey: process.env.BROWSERBASE_API_KEY });
const session = await bb.sessions.create();

const connection = new BrowserbaseConnection(session.id);

const driver = await new Builder()
  .usingServer(session.seleniumRemoteUrl)
  .setChromeOptions(new Options())
  .build();

// 给每个请求追加自定义头
const originalExecute = driver.executor_.execute.bind(driver.executor_);
driver.executor_.execute = async function (command) {
  command.headers = { ...command.headers, ...connection.getHeaders() };
  return originalExecute(command);
};
```

```python
import os
from selenium import webdriver
from selenium.webdriver.remote.remote_connection import RemoteConnection
from browserbase import Browserbase

class BrowserbaseConnection(RemoteConnection):
    def __init__(self, session_id, *args, **kwargs):
        self.session_id = session_id
        super().__init__(*args, **kwargs)

    def get_remote_connection_headers(self, parsed_url, keep_alive=False):
        headers = super().get_remote_connection_headers(parsed_url, keep_alive)
        headers.update({
            "x-bb-api-key": os.environ["BROWSERBASE_API_KEY"],
            "session-id": self.session_id,
        })
        return headers

bb = Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])
session = bb.sessions.create()

connection = BrowserbaseConnection(session.id, session.selenium_remote_url)
driver = webdriver.Remote(
    command_executor=connection,
    options=webdriver.ChromeOptions()
)
```

**注意事项**
- ⚠ 文档自相矛盾（两处官方 Node.js 代码样例不一致）：`using-browser-session` 页用的是上面这种
  ——包一个 `BrowserbaseConnection` 类，改写 `driver.executor_.execute` 注入 `x-bb-api-key` +
  `session-id` 头；而 `welcome/quickstarts/selenium` 页的 Node.js 示例，用的是另一种写法——自
  定义 `http.Agent`，通过 `.usingHttpAgent(...)` 注入 **`x-bb-signing-key: session.signingKey`**
  （不是 `x-bb-api-key`/`session-id`）。两页对"该注入哪个头、用哪种机制"给出了不同答案，未实测
  确认哪个当前有效，都记录下来供验证时对照。Python 侧两页写法一致，都是重写 `RemoteConnection`
  注入 `x-bb-api-key` + `session-id`。
- Selenium 连接**不会**自动使用默认 context——文档原文说"Uses default context automatically"，
  不需要（也没有）像 Playwright/Puppeteer 那样手动取 `contexts()[0]`/`pages()[0]`。

---

## 最佳实践：使用默认 context/page

无论哪个框架，**尽量使用 session 自带的默认 context 和默认 page**，而不是自己新建一个：

```typescript
// Playwright
const context = browser.contexts()[0];
const page = context.pages()[0];

// Puppeteer
const page = (await browser.pages())[0];

// Selenium：自动使用默认 context，无需手动操作
```

**为什么**：文档原文明确写"Always use the default context and page when possible to ensure
proper functionality of Verified features"——即如果你开了 `browserSettings.verified`
（Verified 反检测模式），它依赖默认 context/page 才能正常工作；自己 `browser.newPage()` /
`context.newPage()` 开一个新页面，可能绕开 Verified 的效果。⚠ 文档没有进一步说明具体会失效到
什么程度，只给了这条建议本身。

---

## 连接时序陷阱

- **5 分钟连接超时** ⚠ 文档原文，未实测：session 创建后，如果 5 分钟内没有建立连接，
  session 会被回收终止。应对方式：创建后立即连接；需要长时间存活的场景用 `keepAlive: true`。
- **10 分钟 CDP 空闲超时** ⚠ 文档原文，未实测：已连接的 CDP 连接，如果 10 分钟内没有发送任何
  CDP 命令，连接会被断开。应对方式：起一个定时心跳，每 ~5 分钟发一次无副作用的 CDP 命令，例如
  `page.evaluate(() => undefined)`：

```javascript
// Node.js：每 5 分钟发一次心跳，防止 CDP 空闲超时
setInterval(async () => { await page.evaluate(() => undefined); }, 5 * 60 * 1000);
```

```python
# Python：同样每 5 分钟发一次心跳（用 asyncio.create_task 起一个后台循环）
import asyncio
async def heartbeat(page):
    while True:
        await asyncio.sleep(5 * 60)
        await page.evaluate("undefined")
```

- **`connectUrl` 是否可重复使用** ⚠ 文档未明确说明单次性，需要重点验证：keep-alive 相关文档
  的措辞是"reconnect using the same connect URL"，暗示只有 `keepAlive: true` 创建的 session
  才能在断开后用同一个 `connectUrl` 重连；对普通（非 keepAlive）session，一旦断开，session 即
  结束，此时它的 `connectUrl` 大概率不能再用了。但材料中没有一句直接写"connect URL 是一次性
  的"，这是从旁证推断出来的，**当作"把 connectUrl 当单次使用对待，除非开了 keepAlive"这条经验
  规则来用，等真实 Key 到位后要专门验证**。
- 5 分钟连接超时与 10 分钟 CDP 空闲超时是两个不同的计时器：前者管"创建后多久必须连上"，后者管
  "连上之后多久不发命令会被断开"，不要混为一谈。

---

## Contexts：跨 session 持久化登录态

Contexts 解决的是**"让不同 session 共享同一份 cookie/登录态/localStorage"**的问题，是与
`keepAlive`（让*同一个* session 的连接在断开后继续存活）完全不同的机制——两者可以同时用，但没
有互相蕴含的关系：`keepAlive` 保的是一条连接，Context 保的是跨 session 的浏览器数据。

### 创建 Context
**Endpoint**: `POST /v1/contexts`
**用途**: 生成一个新的、空的 Context，拿到 `id` 后传给之后创建的 session 使用。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `projectId` | string | 否 | 从 API Key 推断 | 同 session 创建 |
| `name` | string | 否 | — | 可选的人类可读名字；同一 project 内、在存活的 Context 之间按大小写不敏感唯一；首尾空白会被裁剪 |

**示例请求 / 响应**

```javascript
import { Browserbase } from "@browserbasehq/sdk";

const bb = new Browserbase({ apiKey: process.env.BROWSERBASE_API_KEY });
const context = await bb.contexts.create({ name: "my-context" });
console.log("Context ID:", context.id);
// Python 对称写法: bb.contexts.create(name="my-context")
```

响应（201）：`{ "id": "...", "publicKey": "...", "cipherAlgorithm": "AES-256-CBC",
"initializationVectorSize": 16 }`——后三个字段是给客户端加密 user-data-directory 用的元数据。

### 使用 Context（在创建 session 时传入）
把 Context ID 放进 `browserSettings.context`，`persist: true` 表示这次 session 里的变更
（登录、写 cookie 等）会在结束时写回 Context 供下次使用；`persist: false`（默认）只读复用，
不保存本次的任何变更：

```javascript
const session = await bb.sessions.create({
  browserSettings: { context: { id: contextId, persist: true } },
});
// Python: bb.sessions.create(browser_settings={"context": {"id": context_id, "persist": True}})
```

### Context 存的是什么数据
来源于 Chromium 的 user data directory，包括：**cookies**（显式备份/恢复的 session cookies）、
**localStorage**、**IndexedDB**、**Session Storage**、**Service Workers**、**Web Data**（表单
自动填充）、**浏览器偏好设置**（站点级权限、HSTS 等安全状态）。**不包含** HTTP 缓存（图片、
CSS、JS、字体）——每个 session 都会重新从网络拉取页面资源；但如果站点用 Service Worker 做缓存，
由于 Service Worker 本身会被持久化，页面加载速度仍可能受益。

### 登录（login）工作流模式
1. 创建 Context，拿到 `contextId`。2. 用 `contextId` + `persist: true` 开第一个 session。
3. 在 session 里登录目标网站（可通过 Live View 手动登录，也可代码登录）。4. 结束该 session。
5. 等几秒，确保 Context 数据已同步写回（文档原文明确提示这一步，⚠ 未给出具体应等多久）。
6. 之后所有 session 用**同一个** `contextId`（`persist` 视是否要继续写回变更而定）访问同一
网站，应能直接保持登录。**最佳实践**：避免多个 session 同时用同一 Context 登录同一站点（可能
触发强制登出）；对校验地理位置的网站配合[地理定位代理](/platform/identity/proxies)；建议一个
Context 只对应一个站点的一个登录，避免数据量过大拖慢 session 启动。

### Context 过期语义
Context **本身不会自动过期**，可跨周/跨月反复复用，直到被显式删除或失效：**客户端失效**——
显式 Delete Context、所属 project 被删除、账号被暂停/删除；**应用层失效**（Context 还在但数据
可能已不可用）——网站让登录 cookie 过期（如 30 天）、改密码使旧 session cookie 失效、网站服务
端主动登出全部设备、OAuth token 被撤销、网站检测到可疑活动强制要求重新认证。需要在自动化里检测
"看起来已登出"的状态并重新走登录流程。

### 删除 Context
**Endpoint**: `DELETE /v1/contexts/{id}`
**用途**: 永久删除一个 Context；删除后不能再用于创建新 session（不可撤销）。

```bash
curl -X DELETE https://api.browserbase.com/v1/contexts/$CONTEXT_ID \
  -H "x-bb-api-key: $BROWSERBASE_API_KEY"
```

```javascript
await bb.contexts.delete(contextId); // Python: bb.contexts.delete(context_id)
```

**注意事项**
- Context 数据因为可能含敏感凭证，文档说明会在静态存储时加密（对应创建响应里的
  `publicKey`/`cipherAlgorithm`/`initializationVectorSize` 字段），但具体加密细节以外的实现，
  ⚠ 文档未说明。

---

## Viewports

**用途**: 设置浏览器窗口的可见区域尺寸，用于视觉测试、截图、依赖精确布局的自动化。视口是可选
配置，不设置就用平台默认值（默认具体数值 ⚠ 文档未说明）。

**关键参数**：见上方创建 session 的 `browserSettings.viewport.width` / `.height`（都是
`integer`，非必填）。

```javascript
const session = await bb.sessions.create({
  browserSettings: { viewport: { width: 1920, height: 1080 } },
});
// Python: bb.sessions.create(browser_settings={"viewport": {"width": 1920, "height": 1080}})
```

**注意事项**
- **Verified 模式下自定义视口不生效**：开启 `browserSettings.verified` 时，Browserbase 会用
  它自己固定管理的视口，此时传的自定义 `width`/`height` 会被忽略（Node.js SDK 参考页原文注释
  写的是"ignored when verified is enabled"）。
- **Puppeteer 有自己的默认视口 `800x600`**，会覆盖你在创建 session 时设置的自定义尺寸，除非
  连接时额外传 `defaultViewport: null`（见上方 Puppeteer 章节的完整示例）。这是 Puppeteer 客户
  端行为，不是 Browserbase 服务端行为。

---

## Session Metadata

**用途**: 给 session 打自定义 JSON 标签，方便之后用 `List Sessions` 的 `q` 参数按标签过滤/组
织（比如按测试运行 ID、环境、团队分类）。

**关键参数**：`userMetadata`（创建 session 时的顶层字段），类型为任意 JSON 对象。

**结构限制**：
- 整个 JSON 对象序列化后必须小于 512 字符。
- 只支持嵌套字段，**不支持数组**。
- 查询时只支持**字符串精确匹配**——数字、布尔值要先转成字符串（例如 `"priority": "5"`、
  `"active": "true"`）才能被查询到。
- Metadata 在整个 session 生命周期内持续存在。

**示例请求（写入 + 查询）**：查询串格式固定为 `user_metadata['path']['to']['field']:'value'`。

```javascript
const session = await bb.sessions.create({ userMetadata: { env: "staging" } });
// Python: bb.sessions.create(user_metadata={"env": "staging"})

const query = "user_metadata['env']:'staging'";
const sessions = await bb.sessions.list({ q: query });
// Python: bb.sessions.list(q="user_metadata['env']:'staging'")
```

```bash
curl "https://api.browserbase.com/v1/sessions?q=user_metadata%5B%27env%27%5D%3A%27staging%27" \
  -H "x-bb-api-key: $BROWSERBASE_API_KEY"
```

**注意事项**
- 直接调 REST（curl/`fetch`）时必须自己做 URL encode；SDK 会自动处理，不需要手动 encode。
- 没有匹配结果时返回空数组 `[]`，不是报错。
- 只支持 `user_metadata` 这一个查询"命名空间"，没有其它可查询的内置字段。

---

## Browser Extensions

Extensions 让你把自己的 Chrome 扩展加载进 session，是**两步流程**：先上传拿到 `extensionId`，
再在创建 session 时引用。所有 Core Features（含 Extensions）都遵循同一条规则——**在 session
创建时一次性设置好，不是运行时可以动态增删的东西**（`core-features/overview` 页原文："All
features are set at session creation"）。⚠ 文档未明确写"session 启动后能否追加/替换扩展"这句
话本身，但从"扩展只能通过创建时的 `extensionId` 传入、且加载扩展需要重启浏览器进程"可合理推断：
扩展是创建时定死的，运行中无法动态加载。

### 上传扩展
**Endpoint**: `POST /v1/extensions`
**用途**: 上传一个打包好的 Chrome 扩展（`.zip`，根目录必须有 `manifest.json`，文件大小
≤ 100 MB）。

**关键参数**（`multipart/form-data`）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | binary | 是 | 扩展的 `.zip` 文件 |

**示例请求 / 响应**

```javascript
import { Browserbase } from '@browserbasehq/sdk';
import fs from 'fs';

const bb = new Browserbase({ apiKey: process.env.BROWSERBASE_API_KEY });
const file = fs.createReadStream('extension.zip');
const extension = await bb.extensions.create({ file });
console.log(`Extension uploaded with ID: ${extension.id}`);
// Python: with open("extension.zip", "rb") as f: extension = bb.extensions.create(file=f)
```

响应（200）：`{ "id": "...", "fileName": "extension.zip", "projectId": "...", "createdAt": "...",
"updatedAt": "..." }`

### 用扩展创建 session
```javascript
const session = await bb.sessions.create({ extensionId: 'your-extension-id' });
// Python: bb.sessions.create(extension_id="your-extension-id")
```

**注意事项**
- 带扩展启动 session 会**增加创建耗时**——浏览器必须重启才能加载扩展，这本身也需要时间
  （⚠ 文档原文，未实测，没有给出具体增加多少）。
- `extensionId` 在请求体里出现两处：顶层 `extensionId` 和 `browserSettings.extensionId`，两个
  都在 OpenAPI schema 里定义，⚠ 文档未说明两者是否等价、同时传时哪个生效——本文档的所有示例
  都用顶层字段，建议照抄以避免歧义。
- `DELETE /v1/extensions/{id}` 可删除已上传的扩展（204 No Content）；删除后已经在跑的 session
  不受影响，但显然不能再用这个 ID 创建新 session（⚠ 这点是推断，文档没有专门写"删除后创建新
  session 会怎样"）。

---

## Node.js SDK / Python SDK

### Node.js SDK
**用途**: `@browserbasehq/sdk` 是官方 Node.js 客户端，封装了 Sessions / Contexts /
Extensions / Agents 等 REST 端点；本文件前面所有 Node.js 示例都基于这个包。

**安装**: `npm install -S @browserbasehq/sdk`（pnpm/yarn 同理换命令）。**基础用法**：见上方
"创建 Session"和"连接：Playwright"两节的完整示例（`new Browserbase({ apiKey })` →
`bb.sessions.create()` → 用返回的 `connectUrl`/`seleniumRemoteUrl` 连接）。

### Python SDK
**用途**: `browserbase` 是官方 Python 客户端；`Browserbase` 是同步客户端，`AsyncBrowserbase`
是异步变体，方法集与同步版一致、仅需加 `await`（⚠ 文档只给了方法列表对称这一句话，具体每个方
法的异步签名未在材料中逐一列出）。

**安装**: `pip install browserbase`。**基础用法**：同样见上方"创建 Session"和"连接：
Playwright"两节的 Python 示例。

**两个 SDK 的共同注意事项**
- 命名风格不同：Node.js 用驼峰（`browserSettings`、`keepAlive`），Python 用 snake_case
  （`browser_settings`、`keep_alive`）；但传进 `browser_settings` 字典*内部*的字段名（如
  `blockAds`、`solveCaptchas`）在 Python 里仍保持驼峰——只有 SDK 方法自己的关键字参数名是
  snake_case，字典里的 JSON 字段名沿用 API 原始命名，照抄官方示例的大小写即可。
- 两个 SDK 都**不会**自动读取 `.env` 文件，需要自己 `process.env.X` / `os.environ["X"]`
  显式读取后传入。

---

## Techniques: Dialogs / Timezones

### Dialogs（浏览器原生弹窗）
**用途**: Chrome 的原生对话框（`alert()`/`confirm()`/`prompt()`/`window.print()`）不是网页内
容，而是 Chrome 自身弹出的模态框，会**阻塞该页面的 JS 执行**直到被处理，自动化脚本如果不做处
理会直接卡死。

**处理方式**：在页面加载任何脚本之前，用 `addInitScript()` 覆盖这些原生函数：

```javascript
await page.context().addInitScript(() => {
  window.alert = () => {};
  window.confirm = () => true;
  window.prompt = () => '';
});
await page.goto("https://example.com");
// Python: context.add_init_script("window.alert=()=>{};window.confirm=()=>true;window.prompt=()=>'';")
//         page.goto("https://example.com")
```

**注意事项**
- 必须在 `page.goto()` **之前**注册 init script，否则页面自身脚本可能已经调用过原生弹窗函数。
- PDF 场景（点击触发生成 PDF、或 `window.print()`）需要额外处理：同页替换时用
  `context.route('**/*.pdf', ...)` 拦截网络请求；新标签页打开时用拦截
  `URL.createObjectURL()` 捕获客户端生成的 PDF blob。这两种手法都要求先覆盖
  `window.print = () => {}` 防止打印对话框卡住脚本。具体实现较长，参见官方
  `platform/browser/techniques/dialogues` 页的完整代码（本文件不重复贴长示例，只记录方法论：
  拦截网络 + 拦截 blob 创建，二选一或都做）。

### Timezones
**用途**: 网站可以读取浏览器时区；跑自动化脚本的 Node.js/Python 进程自身的时区，网站看不到。

**行为**：
- 使用 Browserbase 代理时，浏览器时区会**自动对齐代理的地理位置**（⚠ 文档原文，未实测）。
- 不用代理、或想强制指定时区时，需要通过 CDP 的 `Emulation.setTimezoneOverride` 手动设置，用
  [IANA 时区标识符](https://nodatime.org/TimeZones)（例如 `America/Chicago`）。

```typescript
const cdp = await context.newCDPSession(page);
await cdp.send("Emulation.setTimezoneOverride", { timezoneId: "America/Chicago" });
// Python: cdp = context.new_cdp_session(page)
//         cdp.send("Emulation.setTimezoneOverride", {"timezoneId": "America/Chicago"})
```

**注意事项**
- 这个 override 是**按 page 生效**的，不是全局/全 context 一次设置就对所有标签页生效——每打开
  一个新 page/tab，都要在导航前重新设置一次。

---

内容整理自 https://docs.browserbase.com（抓取于 2026-09-21），未使用真实 API Key 验证，实际调用报错优先信任真实 API。
