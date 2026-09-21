# Stagehand（v4）—— 用自然语言驱动浏览器

> 覆盖范围：Browserbase 自家的高层浏览器自动化框架 Stagehand（`@browserbasehq/stagehand` / `stagehand` / Go `sdk-go/v4`）。
> 不覆盖：原始 REST Sessions API + 你自己接 Playwright/Puppeteer/Selenium（见 `sessions-rest.md`）；也不覆盖全托管、异步、服务端运行的 Browserbase Agents 产品（`/v1/agents` REST API，见另一份 reference 文件）。

## ⚠ 最重要的一件事：这不是你记忆里的 Stagehand

**Stagehand v4 是一次从零重写：它直接通过 Chrome DevTools Protocol（CDP）驱动浏览器，不再依赖 Playwright / Puppeteer / Patchright。** v2/v3 时代 Stagehand 字面意义上"继承"了一个 Playwright `Page` 对象，绝大多数示例长这样：

```typescript
// ⚠ 这是 v2/v3 的写法，v4 里不存在
const stagehand = new Stagehand({ env: "BROWSERBASE" });
await stagehand.init();
await stagehand.page.act("...");
```

如果你的训练记忆里 Stagehand "基于 Playwright 构建"、或者见过 `new Stagehand({env: "BROWSERBASE", ...})` / `stagehand.page.act(...)` 这样的写法 —— **那是 v2/v3 的 API，v4 完全不适用。** v4 的写法是：先从一个"浏览器工厂"拿到 `browser` 句柄，再用它创建 `Stagehand` 实例，`act`/`extract`/`observe` 是 `Stagehand` 实例上的方法（不是 `page` 上的），而且**没有 Playwright page 对象可以 import**。本文件除"迁移说明"一节外，其余代码全部是 v4 API；迁移旧代码请看本文件末尾及 `v4_migrations_v3.md` / `v4_migrations_playwright.md`。

## 目录

1. [Stagehand 是什么，和 Browserbase 什么关系](#stagehand-是什么和-browserbase-什么关系)
2. [安装与运行时要求](#安装与运行时要求)
3. [三种浏览器工厂](#三种浏览器工厂三选一先拿-browser-再建-stagehand)
4. [act() —— 执行一步动作](#act--执行一步动作)
5. [extract() —— 抽取结构化数据](#extract--抽取结构化数据)
6. [observe() —— 规划/发现可执行动作](#observe--规划发现可执行动作)
7. [模型配置：Model Gateway vs 显式模型](#模型配置model-gateway-vs-显式模型)
8. [服务端缓存（cache）](#服务端缓存cache)
9. [Keep-alive 行为（按环境）](#keep-alive-行为按环境)
10. [DOM settle timeout](#dom-settle-timeout)
11. [变量与密钥（variables）](#变量与密钥variables)
12. [多标签页 / 多 page 定位](#多标签页--多-page-定位)
13. [Search 与 Fetch 两个轻量 add-on](#search-与-fetch-两个轻量-add-on)
14. [如果你记得的 Stagehand 不是这样：迁移说明](#如果你记得的-stagehand-不是这样迁移说明)
15. [⚠ 文档未说明 / 待确认清单](#-文档未说明--待确认清单汇总)

---

## Stagehand 是什么，和 Browserbase 什么关系

Stagehand 是一个**独立发布的 npm/pip/Go 包**（不是 Browserbase 平台内置功能），提供 AI 驱动的浏览器操作原语：`act()`（执行动作）、`extract()`（结构化抽取）、`observe()`（发现候选动作），外加一套 Playwright 风格的确定性 `page` API（`goto`、`locator`、`click`、`screenshot` 等）。两层可以在同一脚本里混用，自己决定哪一步用 AI、哪一步用确定性选择器。

Stagehand 与 Browserbase 的关系：它的"云模式"浏览器工厂 `browserbase.launch()` 在底层会**创建并驱动一个真正的 Browserbase Session**（即 `/v1/sessions` 背后的那个会话）——所以用 Stagehand 跑在 Browserbase 上，本质上是"Stagehand 帮你调用 Sessions API + 自动接管这个 session"。Stagehand 也可以完全不碰 Browserbase：`localBrowser.launch()` 直接在你自己机器上启动本地 Chrome。

三条路线的定位差异（引用自 auth.md 的既有结论）：

| 方式 | 你写什么 | 控制权在谁 |
| --- | --- | --- |
| 原始 Sessions API + Playwright/Puppeteer/Selenium | 全部确定性逻辑 | 你自己 |
| **Stagehand**（本文件） | 嵌入自己代码里的库；`act`/`extract`/`observe` 一次只做一步 | 你自己写控制流循环 |
| Browserbase Agents（`/v1/agents`，另一份文件） | 一句自然语言 `task` | Browserbase 服务端全权托管（内部用 Stagehand 驱动浏览器） |

---

## 安装与运行时要求

⚠ 文档原文，未实测（无真实 API Key，以下均转录自 fetched 文档）。

| 语言 | 包名 | 运行时最低版本 |
| --- | --- | --- |
| TypeScript/Node | `@browserbasehq/stagehand`（npm/pnpm/yarn/bun） | Node.js ≥ 22.18 |
| Python | `stagehand`（pip/uv/poetry） | Python ≥ 3.11 |
| Go | `github.com/browserbase/stagehand/packages/sdk-go/v4` | Go ≥ 1.26 |

- **TypeScript 必须把 Zod 钉在 `zod@~4.4.3`**：`pnpm add @browserbasehq/stagehand 'zod@~4.4.3'`。更新的 Zod 4.x 小版本会让传给 `extract()` 的 schema 出现 TypeScript 类型报错。
- Bun 受支持（因为 v4 走 CDP，没有 Playwright 依赖，不存在运行时兼容问题）。
- 本地跑需要机器上装好 Chrome；跑在 Browserbase 上则不需要本地装浏览器。
- **Stagehand 从不替你读环境变量、也不会自动加载 `.env` 文件**——`BROWSERBASE_API_KEY`、模型 provider key 等都要在自己代码里 `process.env.X` / `os.environ["X"]` 读出来再显式传入（包括非生产环境的 `BROWSERBASE_BASE_URL`/`STAGEHAND_API_URL` 覆盖，也要用 `baseUrl`/`apiUrl` 参数显式传，而不是设环境变量）。

安装：

```bash
# TypeScript
pnpm add @browserbasehq/stagehand 'zod@~4.4.3'
# Python
pip install stagehand
# Go
go get github.com/browserbase/stagehand/packages/sdk-go/v4@v4.0.0
```

---

## 三种浏览器工厂：三选一，先拿 `browser` 再建 Stagehand

`Stagehand.create({ browser })` 是**唯一**创建实例的方式（没有公开构造函数，返回的实例已初始化）。`browser` 来自下面四个工厂函数之一：

| 工厂 | 用途 |
| --- | --- |
| `browserbase.launch({ apiKey })` | 云端：新建一个 Browserbase 托管的浏览器会话 |
| `localBrowser.launch({...})` | 本地：在你自己机器上启动一个真实 Chrome 进程 |
| `localBrowser.connect({ cdpUrl })` | 附加到一个已经在运行、暴露了 CDP 端点的 Chromium（任意来源，不一定是 Browserbase） |
| `browserbase.connect({ apiKey, sessionId })` | 附加到一个**已经用原始 Sessions API/SDK（如 `@browserbasehq/sdk`）创建好的 Browserbase session** —— 复用一个已建会话，而不是新建一个 |

```typescript
const cloud = await browserbase.launch({ apiKey: process.env.BROWSERBASE_API_KEY });
const local = await localBrowser.launch({ headless: true });
const connected = await localBrowser.connect({ cdpUrl: "http://127.0.0.1:9222" });

const stagehand = await Stagehand.create({ browser: cloud });
```

**Stagehand 只会关闭自己启动（`.launch()`）的浏览器**；`.connect()` 得到的浏览器，`close()` 只断开 Stagehand 连接，浏览器本身继续跑。`stagehand.close()` 和 `browser.close()` 是两个独立调用，务必都调用（顺序：先 `stagehand.close()`，再 `browser.close()`）。

### Browserbase vs Local 环境对比（原文表格，直接复用）

| 特性 | Browserbase | Local |
| --- | --- | --- |
| 可扩展性 | 高（云端托管） | 受限于本地资源 |
| 反检测/隐身能力 | 高级指纹伪装 | 基础隐身 |
| 代理支持 | 内置住宅代理 | 手动配置 |
| 会话持久化 | 云端 context 存储 | 基于文件的用户数据 |
| 地理分布 | 多区域部署 | 单机 |
| 调试方式 | 会话录制 + 日志 | 直接 DevTools 访问 |
| 搭建复杂度 | 只需 API key | 需要装浏览器 |
| **服务端缓存** | **支持** | **不支持** |
| **Model Gateway** | **支持** | **不支持** |
| 成本模型 | 按用量计费 | 基础设施与维护成本 |
| 适用场景 | 生产、规模化、合规 | 开发、调试 |

多区域（仅 Browserbase）：`region` 支持 `us-west-2`（默认）、`us-east-1`、`eu-central-1`、`ap-southeast-1`。一般不需要手动配置区域端点——Stagehand 会自动匹配 session 所在区域（包括缓存服务的路由）；只有传了显式的 Stagehand `apiUrl` 才会覆盖这个自动选择。

---

## act() —— 执行一步动作

**用途**：用自然语言描述"做一件事"（点击、填写、悬停、滚动、拖拽等），Stagehand 推理出目标元素并执行。**一次只做一步**——多步指令（"打开筛选面板、选 4 星、点应用"）应拆成多个 `act()` 调用，而不是塞进一句话。

**签名 / 用法**

```typescript
// 自然语言指令（走推理）
await stagehand.act("click the add to cart button");

// 传入 observe() 返回的 Action（零推理，确定性回放）
const { data: actions } = await stagehand.observe("click the sign in button");
if (actions[0]?.method === "click") {
  await stagehand.act(actions[0]);
}

// 指定目标 page、模型、超时、locator 范围
await stagehand.act("choose 'Peach' from the favorite color dropdown", {
  model: { modelName: "google/gemini-3.8-flash", apiKey: process.env.GOOGLE_API_KEY },
  timeout: 10000,
  page: page2,
  locator: page.locator("form"),
  ignoreLocators: [page.locator(".promo-modal")],
});
```

```python
await stagehand.act("click on add to cart")

result = await stagehand.observe("click the sign in button")
if result.data and result.data[0].method == "click":
    await stagehand.act(result.data[0])

await stagehand.act(
    "choose 'Peach' from the favorite color dropdown",
    model=ModelConfig(model_name="google/gemini-3.8-flash", api_key=os.environ["GOOGLE_API_KEY"]),
    timeout=10000,
    page=page2,
    locator=page.locator("form"),
    ignore_locators=[page.locator(".promo-modal")],
)
```

**关键参数**

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `instruction` | `string \| Action` | 自然语言指令（走推理），或 `observe()` 返回的 `Action` 对象（确定性回放，无推理） |
| `page` | `Page` | 目标标签页，默认当前 active page |
| `model` | `{ modelName, apiKey?, headers? }` | 本次调用的模型覆盖 |
| `timeout` | `number`（ms） | 操作超时 |
| `variables` | `Record<string,string>` | `%varName%` 占位符对应的真实值，本地替换，不进模型 prompt |
| `locator` / `ignoreLocators` | `Locator` / `Locator[]` | 限定/排除快照范围（只对**指令型**调用生效；传 `Action` 时 Stagehand 直接回放其 selector，这两个参数不起作用） |
| `cache` | `boolean \| { threshold }` | 覆盖实例级缓存设置（见下文缓存章节） |

`method` 支持的动作种类（`observe()` 返回的 `Action.method` 取值）：`click`、`doubleClick`、`fill`、`type`、`press`、`hover`、`scrollTo`、`nextChunk`/`prevChunk`、`selectOptionFromDropdown`、`dragAndDrop`。

**返回值**

`{ data, metadata }`：

- `data.success: boolean`，`data.message: string`，`data.actionDescription: string`
- `data.actions: Action[]`——实际执行的动作列表，每个含 `selector`（XPath，形如 `xpath=/html[1]/...`）、`description`、`method`、`arguments`
- `metadata.actionId: string`——用于日志/追踪
- `metadata.cache: { status: "HIT"|"MISS"|"DISABLED", missReason?, count?, threshold?, tokensSaved? }`
- `metadata.usage: { inputTokens, outputTokens, reasoningTokens, cachedInputTokens, inferenceTimeMs }`——本次调用消耗的 token 统计，未走推理时全 0

**注意事项**

- **只做一步**：好例子 `"click the sign in button"` / `"type 'hello' into the search input"`；坏例子 `"order me pizza"` / `"fill in the search bar and hit enter"`（多步）。要编排多步流程，串行调用多次 `act()`。
- **observe-then-act 零推理回放模式（推荐）**：先 `observe()` 拿到候选 `Action`，检查/校验后传给 `act()`——这次 `act()` 跳过推理、跳过页面快照、**跳过 DOM-settle 等待**，也**不查服务端缓存**。如果记录的 selector 失效且 `selfHeal` 开着，Stagehand 会重新推理并重试一次。
- 传入的目标 `locator`/`ignoreLocators` 只影响指令型调用；回放 `Action` 时这些参数不起作用。
- 指令型 `act()` 若带 `locator` 或 `ignoreLocators`，会**跳过服务端缓存**，`metadata.cache.status` 报 `DISABLED`。
- iFrame 和 Shadow DOM 自动处理，无需额外配置（快照默认合并所有 frame 的可访问性树）。
- 敏感数据用 `variables`（见下文"变量与密钥"一节），不要拼进指令字符串。

---

## extract() —— 抽取结构化数据

**用途**：用自然语言指令 + 一个输出 schema，从当前页面抽取结构化、已校验、已带类型的数据。schema 是**必需**的（TS 用 Zod、Python 用 Pydantic、Go 用类型参数自动生成 JSON Schema）。

**签名 / 用法**

```typescript
import { z } from "zod/v4";

// 基本抽取
const { data } = await stagehand.extract(
  "extract product details",
  z.object({ name: z.string(), price: z.number(), inStock: z.boolean() }),
);

// 数组
const { data: listings } = await stagehand.extract(
  "extract all apartment listings",
  z.object({ apartments: z.array(z.object({ address: z.string(), price: z.string() })) }),
);

// 单值也要包一层字段
const { data: price } = await stagehand.extract("extract the price", z.object({ price: z.number() }));

// URL/链接用 z.url()
const { data: link } = await stagehand.extract(
  "extract the link to the 'contact us' page",
  z.object({ contactLink: z.url() }),
);

// 限定/排除范围
const { data } = await stagehand.extract(
  "extract the reason why script injection fails",
  z.object({ reason: z.string() }),
  { locator: page.locator("#main-content"), ignoreLocators: [page.locator("nav"), page.locator(".cookie-banner")] },
);
```

```python
from pydantic import BaseModel

class Product(BaseModel):
    name: str
    price: float
    in_stock: bool

result = await stagehand.extract("extract product details", Product)

class Apartments(BaseModel):
    apartments: list[Apartment]  # Apartment: address/price/sqft

result = await stagehand.extract("extract all apartment listings", Apartments)

from pydantic import AnyUrl
class ContactLink(BaseModel):
    url: AnyUrl

result = await stagehand.extract(
    "extract the reason why script injection fails",
    Reason,
    locator=page.locator("#main-content"),
    ignore_locators=[page.locator("nav"), page.locator(".cookie-banner")],
)
```

**关键参数**

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `instruction` | `string` | 自然语言抽取指令 |
| `schema` | Zod/Pydantic/Go 类型 | 必需（省略时默认 `{ extraction: string }`） |
| `page` | `Page` | 目标标签页 |
| `model` | `ModelConfig` | 本次调用模型覆盖 |
| `timeout` | `number`（ms） | 超时 |
| `locator` / `ignoreLocators` | `Locator` / `Locator[]` | 限定/排除抽取范围（省 token、更准），目前仅支持 CSS 和 XPath locator（`text=` locator 暂不支持范围限定） |
| `screenshot` | `boolean` | 让抽取额外看当前视口的截图（不是整页），用于纯视觉信息（如未在 DOM 文本里体现的样式类提示） |
| `cache` | `boolean \| { threshold }` | 覆盖实例级缓存设置 |

**返回值**

`{ data, metadata }`：

- `data`：按你传入 schema 校验后的值（TS 是 `z.output<Schema>`，Python 是 Pydantic 模型实例，Go 是泛型解码结果）
- `metadata.actionId`、`metadata.cache.status`（`HIT`/`MISS`/`DISABLED`）、`metadata.usage`（同 act）

**注意事项**

- schema 永远必需，抽单个值也要包一层对象字段（`z.object({ price: z.number() })`），不能直接返回裸标量。
- **targeted/scoped 抽取**：`locator` 把快照范围收窄到一个子树（用 `nth` 定位第几个匹配），`ignoreLocators` 把匹配到的节点及其子孙整体从快照里剔除——两者都能显著降低 token 用量、提高准确率。
- 带 `locator`/`ignoreLocators` 的抽取调用**跳过服务端缓存**，`metadata.cache.status = DISABLED`。
- `screenshot: true` 的可视化抽取**永远跳过服务端缓存**（缓存 key 基于 DOM 状态构建，无法代表模型实际看到的像素）。
- 链接抽取内部机制：模型选一个 ID，Stagehand 在"ID→URL 映射表"里查出真实 URL；查看 LLM trace 日志时看到的是 ID，最终结果里才是真实 URL。
- 大页面/大量数据建议分批抽取（比如按分页循环调用 `extract()`），而不是一次性抽整个页面。

---

## observe() —— 规划/发现可执行动作

**用途**：发现页面上的可交互元素，返回结构化的候选 `Action` 列表（selector + method + arguments + description），供你在**执行前**检查、校验，或直接回放给 `act()`。适合：探索页面、规划多步流程、缓存动作、执行关键操作前先验证元素存在。

**签名 / 用法**

```typescript
const { data: actions } = await stagehand.observe("find the login button");
const [action] = actions;
if (action) console.log(action.selector, action.method, action.arguments);

// 带占位变量（避免密码等直接出现在返回结果里）
const { data: formActions } = await stagehand.observe("find the login form fields", {
  variables: {
    username: { value: "user@example.com", description: "The login email" },
    password: { value: process.env.USER_PASSWORD, description: "The login password" },
  },
});
```

```python
result = await stagehand.observe("find the login button")
action = result.data[0] if result.data else None
if action is not None:
    print(action.selector, action.method, action.arguments)
```

**关键参数**

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `instruction` | `string`（可选） | 自然语言指令；省略时行为 ⚠ 文档未明确说明（未给出"省略 instruction"的具体示例/返回内容） |
| `page` | `Page` | 目标标签页 |
| `model` | `ModelConfig` | 模型覆盖 |
| `timeout` | `number` | 超时 |
| `variables` | 同 act，但值经描述化包装 `{ value, description }` | 返回的 `Action.arguments` 里会是 `%varName%` 占位符，不含真实值 |
| `locator` / `ignoreLocators` | 同 extract | 限定/排除范围（仅 CSS/XPath） |
| `cache` | `boolean \| { threshold }` | 覆盖实例级缓存 |

**返回值**

`{ data, metadata }`：

- `data: Action[]`，每个 `Action` 含 `selector`（XPath 字符串，前缀 `xpath=`）、`description`、`method`、`arguments`
- `metadata.cache.status`、`metadata.usage` 同上

**注意事项**

- **observe-then-act 零推理模式**：`observe()` 一次调用拿到全部候选动作，逐个传给 `act()` 回放——每个回放都不再产生 LLM 调用（"一次 observe 的推理成本，替代 N 次 act 的推理成本"），这是官方推荐的多步表单/流程模式。
- 指令要具体（"find the primary call-to-action button in the hero section"），避免泛泛的"find buttons"；要拿数据用 `extract()` 而不是 `observe()`（"what is the page title?" 不该问 observe）。
- 安全敏感流程（登录等）：先 `observe()` 拿到带 `%varName%` 占位符的候选 `Action`，校验字段确实是你要的（通过 `arguments` 里包含哪个变量名判断），再把变量真实值传给 `act()` 执行——期间密码从不进入模型看到的内容。
- 缓存规则与 act/extract 相同：带 `locator`/`ignoreLocators` 跳过缓存。
- `observe()` 是**安全的重试对象**——它只做规划、不产生副作用，可以放心重试；`act()` 不能随便重试，因为失败前可能已经点击/提交过了（详见下方迁移说明里的"Escalate on observe(), never on act()"提示）。

---

## 模型配置：Model Gateway vs 显式模型

**关键差异点**（这是 Stagehand 相对其它自动化方案的一个显著卖点）：

| 配置 | 推理走向 |
| --- | --- |
| 不传 `model` | 走 **Model Gateway**，Browserbase 每次调用自动选模型 |
| 传 `model` 但不传 `apiKey` | 走 Model Gateway，但**锁定**成你指定的那个模型 |
| 传 `model` + `apiKey` | **绕过 Gateway**，直连该 provider |
| 传自定义 `generate` 回调（bring-your-own-LLM） | 绕过 Gateway，推理在你自己进程里跑 |

- **Model Gateway 只对 Browserbase 托管浏览器可用**——本地浏览器没有 Browserbase session 可以计费/鉴权，所以本地浏览器**必须**显式传 `model` + 该 provider 的 `apiKey`（否则第一次 `act()`/`extract()`/`observe()` 调用时报错 `An LLM was not configured during Stagehand initialization`）。
- Model Gateway 优势：一个 Browserbase key 统一计费推理+浏览器+缓存；按市场价收费无加价；Browserbase 处理重试/退避/限流；新模型上线即用，无 provider 侧分级门槛。
- Model Gateway **不支持 `stopSequences`**（会报错 `Browserbase Model Gateway does not support stop sequences`）——需要的话必须传自有 provider key 绕过 Gateway。
- 支持的 provider 前缀（模型名必须带 `provider/` 前缀，5 个之外的一律走 bring-your-own-LLM 回调）：`openai`、`anthropic`、`google`、`groq`、`cerebras`。示例模型名：`openai/gpt-5.6-sol`、`anthropic/claude-sonnet-5`、`google/gemini-3.8-flash`。⚠ 这些具体型号名极易过时，实际调用前应以当时文档/SDK 报错为准。
- **per-call 覆盖**：每个 `act`/`extract`/`observe` 调用都能单独传 `model` 覆盖实例默认模型，方便"默认用便宜模型，个别难任务临时升级"。
- **模型配置不计入缓存 key**——换模型不会让缓存失效（见下节）。
- Stagehand 会校验完整模型名（provider 前缀 + 已知型号列表），未知模型直接在 `Stagehand.create()` 或调用发起时本地报错，不会真的打到 provider。

---

## 服务端缓存（cache）

**只对 Browserbase 浏览器 + Browserbase API key 生效；本地浏览器上 `cache` 选项完全无效（每次都会真正推理）。**

```typescript
const browser = await browserbase.launch({ apiKey: process.env.BROWSERBASE_API_KEY });
const stagehand = await Stagehand.create({
  browser,
  cache: true,              // 或 { threshold: 1 }，阈值降到 1 即"跑一次就开始命中"
});

await stagehand.act("click the login button", { cache: false }); // 单次调用关闭
const result = await stagehand.act("click the login button");
console.log(result.metadata.cache.status); // "HIT" | "MISS" | "DISABLED"
```

**缓存 key 的构成**：指令文本 + 页面内容 + 调用时传的 options（**不包括**模型配置——所以换模型不失效）。缓存存在 Browserbase 服务端，跨脚本执行、跨机器都能命中。

**关键限制**：

- 页面 URL 也算进缓存 key，带动态 query string 的页面缓存效果可能打折扣（Browserbase 会过滤掉一部分推荐/统计类 query 参数，但不是全部）。
- 页面内容/结构变了，这次会 MISS 并真正调用 LLM，后续调用再命中新缓存条目。
- 缓存是 best-effort：缓存服务不可达时自动退化为正常推理，不会导致调用失败。
- 缓存命中回放 `act()` 时**关闭 selfHeal**（不会重新推理修复失效 selector），selector 失效则整体回退到完整推理。
- 带 `locator`/`ignoreLocators` 的调用永远 `DISABLED`（不读不写缓存）——因为缓存约定是基于未限定范围的请求构建的。
- 指令字符串本身是 key 的一部分，措辞变化（同义词、多余形容词、标点)都会导致新 key/MISS——保持指令锚定可见 UI 文案、简短、不含运行时可变文本。

**⚠ 密钥与缓存交互（务必注意）**：`variables` 的值本身**不会**进入发给模型的 prompt（模型只看到 `%varName%` 占位符），**但**开启服务端缓存时，变量的真实值会**作为请求的一部分传到缓存服务**——所以任何携带凭证的调用，必须显式把这次调用的 `cache` 设为 `false`。

---

## Keep-alive 行为（按环境）

Keep-alive 控制的是"`close()` 之后浏览器是否继续活着"，默认关闭（Stagehand 关闭它启动的浏览器并清理全部资源）。

| 行为 | keep-alive 开 | keep-alive 关（默认） |
| --- | --- | --- |
| **Browserbase** | `close()` 后 session 继续存活，可稍后用 `browserbase.connect({ sessionId })` 重连 | session 通过 API 被终止 |
| **本地** | Chrome 进程继续跑（脚本退出后窗口还在） | Chrome 进程被杀，临时 profile 目录被删 |
| **附加（CDP connect）** | 始终保持运行 | 始终保持运行（Stagehand 从未拥有这个浏览器，不会管它的生死） |

- **Browserbase 上的 keep-alive 需要 Startup 套餐及以上**。
- 本地 keep-alive 建议配合固定 `port`，方便之后 `localBrowser.connect({ cdpUrl })` 重新接上。
- 本地临时 user data 目录默认在浏览器关闭时被删；要保留需自己传 `userDataDir`（此时无论 keep-alive 与否都保留），或对自动生成的临时目录开 `preserveUserDataDir`。

---

## DOM settle timeout

- 默认 **5000ms**。作用于**指令型** `act()` 调用——执行前 Stagehand 会等待页面网络活动"安静下来"（最长等到超时），给懒加载内容、JS 更新、动态渲染留出完成时间。
- **回放 `Action`（observe→act 零推理模式）跳过这个等待**；`observe()` 和 `extract()` 读的是"当下"的页面快照，也不走这个等待逻辑。
- 调低（如 500ms）：静态、快速加载的页面，减少不必要等待。
- 调高（如 5000ms 以上）：动画多、懒加载/无限滚动、React/Vue/Angular 等重前端框架页面、复杂 SPA。
- 设置方式：`Stagehand.create({ browser, domSettleTimeoutMs: 3000 })`。
- 设太低可能导致动作打在还没就绪的元素上；设太高会无谓拉长执行时间。

---

## 变量与密钥（variables）

用 `%varName%` 语法把敏感值排除在发给模型的 prompt 之外：

```typescript
await stagehand.act("type %password% into the password field", {
  variables: { password: process.env.USER_PASSWORD },
});
```

- 模型只看到占位符 `%password%`，真实值在本地被替换进最终动作，记录下来的也是占位符而非明文。
- `act()` 和 `observe()` 都接受 `variables`；`observe()` 版本的值是 `{ value, description }` 描述化对象，返回的候选 `Action.arguments` 里会带 `%varName%` 占位符，供你在真正执行前先确认字段对不对。
- **唯一例外**：开启服务端缓存（`cache`）时，变量真实值会作为请求一部分传到缓存服务——凡是携带凭证的调用，务必单独把 `cache` 设为 `false`。
- 处理敏感数据时同时把日志级别设为 `logging: { level: "off" }`，防止密钥出现在日志里。
- 永远从环境变量读密钥，不要硬编码；Stagehand 不会替你读环境变量。

---

## 多标签页 / 多 page 定位

- `act()`/`extract()`/`observe()` 默认作用于**当前 active page**（Chrome 上一次聚焦的标签页）——网页自己弹出并聚焦的新标签会自动成为默认目标，无需手动接管。
- **陷阱**：点击前拿到的 `page` 变量引用的是点击前那个标签；如果点击触发了新标签打开，要重新 `await browser.context.activePage()` 或显式持有每个标签的引用，否则会操作错标签。
- 显式指定目标：任何原语的 `{ page }` 选项。

```typescript
await browser.context.newPage();
const [githubPage, pythonPage] = await browser.context.pages();

await githubPage.goto("https://github.com/browserbase/stagehand");
await pythonPage.goto("https://github.com/browserbase/stagehand-python");

// 并发操作两个标签
const [a, b] = await Promise.all([
  stagehand.extract("extract the repository stars", starsSchema, { page: githubPage }),
  stagehand.extract("extract the repository stars", starsSchema, { page: pythonPage }),
]);

// 切换默认目标
await browser.context.setActivePage(githubPage);
```

- `page.locator(selector)` 创建的 locator 绑定在创建它的那个 page 上，不能跨标签复用。

---

## Search 与 Fetch 两个轻量 add-on

这两个是**独立于完整浏览器会话之外**的轻量 API——都只需要 Browserbase API key，不涉及启动浏览器/Stagehand 实例，本地浏览器没有等价能力。

### `browserbase.search()` —— 全网搜索，拿排序后的 URL 列表

一次调用返回一批排过序的结果（`id`/`title`/`url` 必有，`author`/`favicon`/`image`/`publishedDate` 视来源而定）。适合"agent 不知道从哪个页面开始"的场景——不用真的启动浏览器加载搜索引擎页面再解析结果。限制：查询 1–200 字符，`numResults` 1–25（默认 10），限流 120 次/分钟/项目。当只是要"发现值得看的 URL"、还没决定要不要真正进入交互页面时，比起花一个完整 Stagehand 浏览器会话去手动导航搜索引擎要便宜得多。

```typescript
const { results } = await browserbase.search({
  apiKey: process.env.BROWSERBASE_API_KEY,
  query: "browser agent frameworks",
  numResults: 5,
});
```

### `browserbase.fetch()` —— 把任意 URL 变成可读文本，不启动浏览器

对一个 URL 发 HTTP 请求并把响应转成 `markdown`（默认可读性最好）、`json`（配 JSON Schema，服务端直接抽取结构化对象，不消耗你自己的模型调用）、或 `raw`（原始响应体，默认格式，最便宜）。限制：内容上限 5MB，请求超时 60 秒，**不执行 JavaScript**（页面不会被渲染，看不到客户端渲染后才出现的内容），**PDF 无法转 markdown/json**。当页面是客户端渲染、需要登录、或内容要交互（滚动/点标签/关弹窗）才出现时，`fetch()` 看不到——这时才该换成 `browserbase.launch()` + `extract()`。典型模式：先 `fetch()`，缺内容再退回真实浏览器会话。

```typescript
const { content } = await browserbase.fetch({
  apiKey: process.env.BROWSERBASE_API_KEY,
  url: "https://example.com",
  format: "markdown",
});
```

---

## 如果你记得的 Stagehand 不是这样：迁移说明

v2/v3 时代 Stagehand **把自己接在一个 Playwright `Page` 上**，暴露 `page.act()` / `page.extract()` / `page.observe()`，还有一个**完整的 `agent()` 方法**（`stagehand.agent(config)` 返回一个 `AgentInstance`，`.execute(instruction)` 跑一个多步自主循环，内部会退化到 computer-use 模式；配置项包含 `systemPrompt`、`tools`、`mode: "dom"|"hybrid"|"cua"` 等）。

**v4 是 CDP 原生架构，这一切都变了：**

- **没有 Playwright page 可以 import**。Stagehand 直接通过 CDP 驱动浏览器，`page` 现在来自 `browser.context.newPage()` / `browser.context.activePage()` / `browser.context.pages()`，且都是 async。
- `act()`/`extract()`/`observe()` 现在是 **`Stagehand` 实例上的顶层方法**（不是 `page` 上的），通过 `{ page }` 选项指定目标标签。
- **`agent()` 在 v4 里彻底消失，没有一对一替代品**。官方原文（`v4_migrations_v3.md`）明确写道："**`agent()` is gone. Nothing in v4 replaces it one-for-one.**"、"There is no agent API in v4."（`v4_first-steps_ai-rules.md` 三种语言的规则文件里都重复了这句），`v4_best-practices_mcp-integrations.md` 也重申"Stagehand v4 does not include an autonomous agent or a general-purpose MCP client"。这**不是文档遗漏或语焉不详**，是官方明确的架构决策，四份不同的 v4 文档相互印证，可视为确定事实，不需要标 ⚠。
  - 官方给出的两条替代路径：**Code mode**（让编码助手写一次性脚本，你运行它，模型不在运行时参与循环——官方推荐起点）；**Tool calling**（自己写一个工具调用循环，把 `page.goto/locator/snapshot` 等确定性方法 + `stagehand.act/extract/observe` 都注册成模型的工具，模型在运行时驱动，但控制流是你自己的代码，不是 Stagehand 内置的）。
  - 明确提示：**升级/重试要 escalate 在 `observe()` 上，不要 escalate 在 `act()` 上**——`act()` 失败前可能已经真的点击/提交过了，重试会重复副作用；`observe()` 只做规划，重试是安全的。
- 每个原语现在统一返回 `{ data, metadata }`（v3 是直接返回裸值/数组）。
- `extract()` 现在是位置参数 `extract(instruction, schema, options?)`，不再是一个配置对象。
- 模型配置从 `modelName` + `modelClientOptions` 合并成一个 `model: { modelName, apiKey }` 对象，且名字必须带 provider 前缀。
- 缓存从构造函数里的 `enableCaching: true` 变成 `cache: true`（服务端缓存，不是本地）。
- `page.deepLocator()` 消失，功能并入普通 `page.locator()`（`>>` 跨 iframe 语法不变）。

如果要真正迁移一份 v3/Playwright 代码，请让编码助手先读 `v4_migrations_v3.md`（v3→v4 迁移，含完整对照表）或 `v4_migrations_playwright.md`（Playwright→v4 迁移，含"缺失 API 怎么用 `page.evaluate()` 重建"的完整配方），不要凭训练记忆直接改写。

---

## ⚠ 文档未说明 / 待确认清单汇总

- `observe()` 的 `instruction` 参数标注为可选，但抓取到的文档页里没有给出"完全省略 instruction 时具体返回什么/如何工作"的示例或说明。
- 本文引用的具体模型型号名（如 `openai/gpt-5.6-sol`、`anthropic/claude-sonnet-5`、`google/gemini-3.8-flash` 等）来自 2026-09-21 抓取的文档快照，型号迭代速度快，实际调用前应以 SDK 当时校验结果 / Model Gateway 实际支持列表为准，不要死记这些具体名字。
- 未读取 `v4_reference_context.md`、`v4_reference_locator.md`、`v4_reference_response.md`、`v4_best-practices_deployments.md`（仅读了开头的 Vercel 部署骨架）、`v4_best-practices_cost-optimization.md`/`v4_best-practices_speed-optimization.md`（仅读了前 100-120 行）的完整内容——本文对这几部分的覆盖仅限于其在 act/extract/observe/caching/models 等页面中被引用到的片段，未展开的具体 API 细节（如 `Locator` 的完整方法列表、`Response` 的字段）不在本文件覆盖范围内，需要时应直接查阅对应原始文档页。
- 未使用真实 Browserbase API Key 或模型 provider Key 做过任何实际调用验证——本文件全部内容转录自文档，实际行为、错误信息、返回字段以未来真实调用结果为准。

---

内容整理自 https://docs.stagehand.dev（v4 文档，抓取于 2026-09-21），未使用真实 API Key/SDK 验证，实际调用报错优先信任真实 API。
