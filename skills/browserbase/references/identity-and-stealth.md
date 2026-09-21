# Agent Identity：代理身份与反检测（Proxies / CAPTCHA / Verified / 站点访问控制）

> 来源：docs.browserbase.com「Platform → Identity」（Overview / Proxies / Authentication / CAPTCHA solving / Verified customization）、「Platform → Browser → Security」（Allowed domains / Certificate validation / IP allowlisting）、「Account → Billing → Plans」，抓取于 2026-09-21。OpenAPI 字段名与默认值取自 `POST /v1/sessions` 与 `/v1/certificates*` 的 spec 摘要。
>
> **未用真实 API Key 验证**：以下字段名、默认值、报错行为均为文档原文转录，未经真实调用确认，实际调用报错优先信任真实 API。鉴权头 `x-bb-api-key: <BROWSERBASE_API_KEY>`（大小写不敏感）、Node SDK `@browserbasehq/sdk`、Python SDK `browserbase`，用法见 auth.md 共享笔记。本文所有代码示例都是 `bb.sessions.create(...)` 的 `browserSettings` / `proxies` / `proxySettings` 配置，不涉及 Stagehand 或 Browserbase Agents（那是另外两套产品，见 choosing-your-approach.md）。

## 0. 四条轴线：先分清它们各管什么

Browserbase 把"让会话看起来像一个真实、被授权的用户"拆成四条**相互独立、可以组合**的能力轴：

| 轴 | 解决什么问题 | 开通门槛 | 核心字段 |
| --- | --- | --- | --- |
| **Verified** | 让站点的反机器人系统把这个浏览器指纹识别为"真实设备"，而不是"被 Browserbase 的反检测伙伴认出的自动化浏览器" | Scale 计划（联系销售可在低档位试用），账单表里 Developer/Startup 显示为 "Basic" | `browserSettings.verified` |
| **Web Bot Auth** | 让代理**密码学证明**自己是被授权用户操作的（不依赖浏览器行为特征），基于 Cloudflare Signed Agents 计划 | Beta，需联系申请开通 | 无公开的 `browserSettings` 字段，通过账号级配置启用 |
| **CAPTCHA solving** | 遇到验证码时自动求解，让流程继续走下去 | 所有付费计划自动开启；Free 计划账单表标为 "No"（见下方 ⚠） | `browserSettings.solveCaptchas`（默认 `true`） |
| **Proxies** | 控制会话的出口 IP 和地理位置一致性，规避基于 IP 的封锁/风控 | Developer 计划及以上 | `proxies` / `proxySettings` |

**它们不是二选一，而是按需叠加**：文档反复强调 Verified 应该和 Proxies 搭配使用效果最好（"Proxies pair well with Verified sessions for the best experience on protected sites"）；CAPTCHA solving 与 Proxies 搭配可以提高求解成功率；Authentication（2FA/OAuth 会话保持）则是在前三者的基础上再叠加 Contexts（跨会话持久化 cookie）。不要把这四条轴线的作用范围搞混——比如"开了 Verified 就不用管 CAPTCHA 了"是错的，这两者各管各的，即便是 Verified 会话，遇到验证码时该走的 CAPTCHA solving 流程照样会走。

组合示例见第 3 节（Verified + 代理 + geolocation）。

---

## 1. Proxies（代理）

### 用途
控制会话的出口 IP 及地理位置一致性：需要"看起来像某个国家/城市的真实用户"、需要跨会话保持同一 IP、或者需要把不同域名的流量路由到不同代理（比如政府类站点走一个代理、其余走另一个）。代理解决的是**网络层**的身份问题；Verified 解决的是**浏览器指纹层**的身份问题；两者独立又互补。

Browserbase 提供三种代理模式，都通过创建 session 时的顶层 `proxies` 字段配置：

1. **内置代理**（`proxies: true` 或 `type: "browserbase"`）——Browserbase 托管的住宅代理网络。
2. **自定义代理**（`type: "external"`）——自带 HTTP/HTTPS 代理的 server + 账号密码。
3. **路由规则**——在同一个 session 里按 `domainPattern` 组合内置代理、自定义代理、甚至"不使用代理"（`type: "none"`）。

### 如何启用 / 配置

**最简单：内置代理，默认关闭**

```typescript
// Node.js
const session = await bb.sessions.create({ proxies: true });
```

```python
# Python
session = bb.sessions.create(proxies=True)
```

`proxies` 默认为 `false`。设为 `true` 时是"尽力使用美国代理"（best-effort US-based），如果附近没有可用的美国代理节点，Browserbase 可能会路由到邻近国家（如加拿大）。

### 关键参数（`POST /v1/sessions` 请求体，`proxies` 字段）

`proxies` 的类型是 `boolean | array<object>`。数组里每个元素是以下三种 anyOf 之一：

| type | 字段 | 必填 | 说明 |
| --- | --- | --- | --- |
| `browserbase` | `type` | 是，固定 `"browserbase"` | 使用 Browserbase 托管代理网络 |
| | `geolocation.country` | 是（若提供 `geolocation`） | ISO 3166-1 alpha-2 国家码 |
| | `geolocation.state` | 否 | 美国州代码（2 位），必须同时指定 `country: "US"` |
| | `geolocation.city` | 否 | 城市名，多词用空格；大小写不敏感 |
| | `domainPattern` | 否 | 该代理适用的域名正则；省略则匹配所有域名 |
| `external` | `type` | 是，固定 `"external"` | 使用自带代理 |
| | `server` | 是 | 代理服务器 URL |
| | `username` / `password` | 否 | 代理鉴权账号密码 |
| | `domainPattern` | 否 | 同上 |
| `none` | `type` | 是，固定 `"none"` | 该 `domainPattern` 命中的域名**不**走任何代理 |
| | `domainPattern` | 否 | 同上 |

### 注意事项
- 代理规则**按数组顺序匹配，命中第一条即生效**。要"排除某些域名不走代理"，把 `type: "none"` 的规则放在数组最前面，后面再跟一条 `browserbase`/`external` 兜底规则（见下方"代理路由规则"小节）。
- 只需要「按国家/城市定向出口 IP」而不需要多代理组合时，直接用最简单的 `proxies: true` 或单元素数组即可，不必写路由规则。

---

### 代理地理位置定向（Geolocation targeting）

#### 用途
让代理出口 IP 落在指定国家 / 美国州 / 城市，用于访问有地区限制的内容，或者需要跟目标用户所在地保持一致以降低风控概率。

#### 如何启用 / 配置

```typescript
// Node.js — 定向到美国
const session = await bb.sessions.create({
  proxies: [{ type: "browserbase", geolocation: { country: "US" } }],
});
```

```python
# Python — 定向到美国
session = bb.sessions.create(
    proxies=[{"type": "browserbase", "geolocation": {"country": "US"}}]
)
```

非美国地区同样用 `country` 字段（如 `"GB"`、`"JP"`、`"BR"`）；只有需要精确到城市时才加 `city`（例如巴西圣保罗：`{"city": "SAO_PAULO", "country": "BR"}`）。

#### 关键参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `geolocation.country` | string | ISO 3166-1 alpha-2，必填（若提供 geolocation 对象） |
| `geolocation.state` | string | 仅美国内使用，2 位州代码，须同时指定 `country: "US"` |
| `geolocation.city` | string | 城市名，大小写不敏感；文档示例里多词城市用下划线连接大写（如 `SAO_PAULO`），也提到"用空格分隔多词城市名"——⚠ 文档未说明：`SAO_PAULO` 这种大写下划线格式与"用空格"的说法哪个是权威写法，两处描述不完全一致，建议先按文档示例的字面格式（大写+下划线）尝试 |

内置代理支持 **200+ 个国家/地区**，覆盖非洲、亚洲、欧洲、北美、大洋洲、南美六大洲（完整逐条列表见原文档 Proxies 页面的 "Supported countries" 折叠区，本文不逐条转录以控制篇幅）。代表性国家码举例：US、CA、GB、DE、FR、JP、CN、HK、SG、AU、BR、MX、IN、AE 等。

#### 注意事项
- **地理位置定向是尽力而为（best-effort），不是硬保证**：如果指定位置没有可用代理节点，会自动退化到"最近的可用代理"。
- **原则：用最宽泛的地理粒度**——先试 country，真正需要时才加 state/city。粒度越细，可选代理池越小，成功率和可用性越差。这是文档明确给出的最佳实践，不是猜测。
- geolocation 字段大小写不敏感，无需强制转大写/小写。

---

### 自定义代理（Custom / External Proxies）

#### 用途
接入自己的 HTTP/HTTPS 代理，用于满足企业安全策略、复用已购买的代理服务商、或需要把流量固定路由到某个可控出口（配合 IP 白名单场景，见第 8 节）。这是"带自己的代理"（bring your own proxy），与 Browserbase 托管的内置代理是完全不同的两回事。

#### 如何启用 / 配置

```typescript
// Node.js
const session = await bb.sessions.create({
  proxies: [
    { type: "external", server: "http://...", username: "user", password: "pass" },
  ],
});
```

```python
# Python
session = bb.sessions.create(
    proxies=[
        {"type": "external", "server": "http://...", "username": "user", "password": "pass"},
    ]
)
```

#### 关键参数

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `type` | string | 是 | 固定 `"external"` |
| `server` | string | 是 | 代理服务器 URL |
| `username` | string | 否 | 代理鉴权用户名 |
| `password` | string | 否 | 代理鉴权密码 |
| `domainPattern` | string | 否 | 该代理生效的域名正则，省略则匹配全部域名 |

#### 注意事项
- **Browserbase 在会话创建时就会校验代理连通性**：如果连不上指定代理，创建请求直接报错。确保代理服务器公网可达（或已建好隧道）且账号密码正确后再创建会话。
- 不是所有代理服务商都被支持，文档没有给出白名单/黑名单，只给了"并非所有代理提供商都受支持"这句提示（⚠ 文档未说明：哪些代理协议特性或提供商不受支持，只在 IP allowlisting 页面提到一条具体限制——不支持 SOCKS5，仅支持 HTTP/HTTPS）。
- 与内置代理一样可以配合 `domainPattern` 做路由规则组合（见下一节）。

---

### 代理路由规则（多代理组合 / 域名排除）

#### 用途
不同网站用不同代理策略——例如政府类网站走一个专用代理、一般浏览走 Browserbase 内置代理、某些域名完全不走代理。这是把上面两种代理类型在同一个 session 里按域名组合的机制，典型场景包括"某些站点必须走自己采购的合规代理，其余走 Browserbase 默认代理"。

#### 如何启用 / 配置

规则**按数组顺序求值，命中第一条匹配 `domainPattern` 的规则即生效**：

```typescript
// Node.js — wikipedia.org 走一个外部代理，其余 .gov 域名走另一个外部代理，兜底用内置代理
const session = await bb.sessions.create({
  proxies: [
    { type: "external", server: "http://...", username: "user", password: "pass", domainPattern: "wikipedia\\.org" },
    { type: "external", server: "http://...", username: "user", password: "pass", domainPattern: ".*\\.gov" },
    { type: "browserbase" }, // 不写这条,其余域名将不走任何代理
  ],
});
```

```python
# Python — 同上
session = bb.sessions.create(
    proxies=[
        {"type": "external", "server": "http://...", "username": "user", "password": "pass", "domainPattern": "wikipedia\\.org"},
        {"type": "external", "server": "http://...", "username": "user", "password": "pass", "domainPattern": ".*\\.gov"},
        {"type": "browserbase"},
    ]
)
```

**从代理中排除特定域名**：把 `type: "none"` 的规则放在数组最前面，命中的域名完全不走代理；后面再跟一条兜底规则给其余域名用代理：

```json
[
  { "type": "none", "domainPattern": "^([a-zA-Z0-9-]+\\.)*(example\\.com|test\\.com|demo\\.com)$" },
  { "type": "browserbase", "geolocation": {} }
]
```

#### 关键参数

| 参数 | 说明 |
| --- | --- |
| `domainPattern` | 域名匹配的正则表达式；省略即匹配所有域名（常用于数组最后一条兜底规则） |
| 规则求值顺序 | **第一条匹配的规则生效**，不是"最具体的规则生效"，所以更精确的规则要写在前面 |
| 兜底规则缺失的后果 | 如果没有任何一条规则匹配到某个域名（且没有 `type: "browserbase"` 的兜底条目），该域名的请求**不走代理** |

#### 注意事项
- 规则顺序错误是最容易踩的坑：把兜底的 `{ "type": "browserbase" }` 放在前面会导致所有流量都命中它，后面更精确的规则永远不会生效。**精确规则在前，兜底规则在最后。**
- 排除域名用 `type: "none"`，同样遵循"放最前面"的原则，否则会被后面更宽泛的代理规则先一步匹配掉。

---

### 自定义代理的可信 CA 证书（Trusted CA Certificates）

#### 用途
当自定义代理会对 TLS 做中间人解密再转发（TLS interception，常见于企业出口代理、MITM 网关、自建网关）时，浏览器不认识代理签发证书用的私有 CA，HTTPS 请求会直接报证书错误。这个功能让 Browserbase 会话信任你上传的指定私有 CA，同时**不影响**对其他公共 CA 签发证书的正常校验——这与第 9 节的 `ignoreCertificateErrors`（整个 session 完全关闭证书校验）是两个不同粒度的机制，不要混用。

#### 如何启用 / 配置

分两步：先把 PEM 证书上传到 Certificates API 拿到证书 ID，再在创建 session 时通过 `proxySettings.caCertificates` 引用。

**第一步：上传证书**（`POST /v1/certificates`，`multipart/form-data`，字段名 `file`，PEM 编码，最大 100 MB，可包含多个证书块）：

```typescript
// Node.js
import { Browserbase, toFile } from "@browserbasehq/sdk";
import { readFile } from "node:fs/promises";

const bb = new Browserbase({ apiKey: process.env.BROWSERBASE_API_KEY! });
const pem = await readFile("./corporate-ca.pem");
const certificate = await bb.certificates.create({
  file: await toFile(pem, "corporate-ca.pem"),
});
console.log("Certificate ID:", certificate.id);
```

```python
# Python
from browserbase import Browserbase
import os

bb = Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])
with open("./corporate-ca.pem", "rb") as f:
    certificate = bb.certificates.create(file=f)
print("Certificate ID:", certificate.id)
```

**第二步：会话创建时引用证书 ID**：

```typescript
// Node.js
const session = await bb.sessions.create({
  proxies: [
    { type: "external", server: "http://corporate-proxy.example.com:8080", username: "user", password: "pass" },
  ],
  proxySettings: { caCertificates: ["<certificate-id>"] },
});
```

```python
# Python
session = bb.sessions.create(
    proxies=[
        {"type": "external", "server": "http://corporate-proxy.example.com:8080", "username": "user", "password": "pass"},
    ],
    proxy_settings={"ca_certificates": ["<certificate-id>"]},
)
```

#### 关键参数

| 参数 | 位置 | 类型 | 说明 |
| --- | --- | --- | --- |
| `file` | `POST /v1/certificates` 请求体 | string(binary) | PEM 编码，最多 100 MB，可含多个证书块 |
| `proxySettings.caCertificates` | `POST /v1/sessions` 请求体 | `array<string(uuid)>`，默认 `[]` | 要信任的证书 ID 列表，可传多个 |
| 证书对象响应字段 | `GET/POST /v1/certificates` 响应 | — | 只有 `id` / `createdAt` / `updatedAt` / `projectId` 四个字段——**不会把 PEM 内容原样返回**，上传后请自行妥善保管原始文件 |

Certificates API 完整端点：`GET /v1/certificates`（列表）、`POST /v1/certificates`（上传）、`GET /v1/certificates/{id}`（详情）、`DELETE /v1/certificates/{id}`（删除）。证书归属于 API Key 所在的 project，一直保留直到手动删除。

#### 注意事项
- Browserbase 在上传时会校验文件是"可解析的 PEM 证书"，格式不对会在上传阶段直接报错，而不是等到 session 创建时才发现。
- `caCertificates` 传入的任意一个 ID 不存在、或不属于当前 project，**session 创建会以 HTTP 400 失败**。
- 这个机制只解决"代理自己签发的私有 CA 不被信任"（对应 `ERR_CERT_AUTHORITY_INVALID`）。证书过期或者域名不匹配（`ERR_CERT_DATE_INVALID` / `ERR_CERT_COMMON_NAME_INVALID`）不属于这个机制能解决的范畴——那是"目标网站自己的证书有问题"，只能用 `ignoreCertificateErrors`（见第 9 节）。

---

### 代理支持的站点类别与限制（重要，务必先读）

#### 用途
这不是一个"可以启用的功能"，而是一个**必须提前知道的真实限制**：Browserbase 的内置住宅代理走的是第三方代理服务商网络，每个服务商都有自己的可接受使用政策（acceptable-use policy），会限制高风险站点类别以防止网络滥用。**这是代理提供商层面的限制，不是 Browserbase 自己设的黑名单**，但后果一样——某些站点用代理访问会不稳定或直接失败。

#### 关键参数（受影响的站点类别，文档原文列举，非穷尽）

| 类别 | 举例 |
| --- | --- |
| 银行与金融服务 | 银行、信用社、支付处理商、卡组织、加密货币交易所 |
| 政府域名 | 绝大多数 `.gov` 站点 |
| 流媒体与娱乐 | 视频/音频流媒体平台、Netflix、Spotify、游戏平台（如 PlayStation、Steam） |
| 票务 | Ticketmaster、Eventbrite 一类站点 |
| 网页邮箱服务商 | Outlook、Yahoo Mail 等 |
| 博彩 | 在线赌场、投注类站点 |

#### 注意事项
- **同一个域名这次能用、下次可能不能用**：是否可用取决于该 session 具体分配到了哪个代理提供商及其当前的限制策略，随时间变化，**不是确定性的**。生产环境里对关键站点要做好"测试后再依赖"的假设，不能默认某个域名一定能通过代理访问。
- 文档明确建议：如果目标站点访问失败，可以尝试 **Verified 与代理的不同组合**——有些站点只需要 Verified、有些只需要代理、有些两者都需要、还有些两者都不需要。不要默认"代理越多越好"。
- 这份类别列表是**举例性质，不是穷尽列表**（"illustrative, not exhaustive"）。如果某个具体域名对业务至关重要，文档建议直接联系 support@browserbase.com 确认是否支持,而不是自己试错后假设结论适用于所有情况。

### 排查代理错误

`ERR_TUNNEL_CONNECTION_FAILED` 可能意味着：站点不被内置代理支持（见上方限制类别）、指定的城市不受支持、或临时性代理故障。排查顺序：

1. 先不带代理访问该站点，确认是否属于"代理受限站点"。
2. 如果指定了 `city`，去掉它或换一个城市重试。
3. 重新创建 session 排除临时性代理故障的可能。

如果需要的特定城市当前不受支持，联系 support@browserbase.com，文档说"可能能够支持"（we may be able to support it）。

### 代理计费

- **谁能用**：Developer 计划及以上可使用内置代理和自定义代理；Free 计划代理配额为 0 GB，无法使用（无论内置还是自定义）。
- **计量方式**：按通过代理传输的总数据量计费，包括网页内容、下载文件、媒体文件、HTTP headers、鉴权数据、加密开销——任何经过代理的流量都算。
- **计费下限**：使用代理的 session 有 **1 MB 最低消费**，之后按 MB 向上取整。
- **超额单价**（来自账单表，⚠ 数字类信息，随时可能过期）：Developer 计划 1 GB 额度内含，超出 $12/GB；Startup 计划 5 GB 额度内含，超出 $10/GB；Scale 计划按量计费、单价面议。
- 降低代理用量的具体手法见 cost-optimization 相关文档（不在本文件覆盖范围）。

---

## 2. CAPTCHA 自动求解

### 用途
遇到验证码挑战时自动识别并求解，让自动化流程不因验证码卡死。这与 Verified（让站点一开始就不触发验证码）是互补关系——Verified 能显著减少遇到验证码的次数，但不能保证完全不遇到；CAPTCHA solving 是兜底机制。

### 如何启用 / 配置

**⚠ 真正的陷阱：CAPTCHA solving 默认是开启的**（`solveCaptchas` 默认值为 `true`），不需要显式开启任何东西。很多同类平台默认关闭这项能力、需要显式 opt-in，Browserbase 反过来——这是本条目里最值得写进技能通用规则的一点：如果你的场景**不希望**自动求解验证码（比如要自己接管、或者担心产生额外费用/延迟），必须显式设置 `solveCaptchas: false`，而不是假设它默认关闭。

禁用示例：

```typescript
// Node.js
const session = await bb.sessions.create({
  browserSettings: { solveCaptchas: false },
});
```

```python
# Python
session = bb.sessions.create(
    browser_settings={"solveCaptchas": False},
)
```

### 关键参数

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `browserSettings.solveCaptchas` | boolean | `true` | 是否在浏览器里启用验证码求解 |
| `browserSettings.captchaImageSelector` | string | — | 非标准/自定义验证码提供商：验证码图片元素的 CSS 选择器 |
| `browserSettings.captchaInputSelector` | string | — | 非标准/自定义验证码提供商：填写答案的输入框 CSS 选择器 |

### 求解耗时与事件监听

典型求解耗时 **5–30 秒**，取决于挑战类型。Browserbase 在检测到验证码并开始求解时会往浏览器 console 打日志，可以监听这两个文本值判断求解进度：`browserbase-solving-started` / `browserbase-solving-finished`。

**Playwright（Node.js）**：

```typescript
const recaptcha = await page.goto("https://www.google.com/recaptcha/api2/demo");

page.on("console", (msg) => {
  if (msg.text() == "browserbase-solving-started") {
    console.log("Captcha Solving In Progress");
  } else if (msg.text() == "browserbase-solving-finished") {
    console.log("Captcha Solving Completed");
  }
});
```

**Playwright（Python）**：

```python
def handle_console(msg):
    if msg.text == "browserbase-solving-started":
        print("Captcha Solving In Progress")
    elif msg.text == "browserbase-solving-finished":
        print("Captcha Solving Completed")

page.on("console", handle_console)
```

**Selenium（Node.js）** —— Selenium 拿不到浏览器 console 事件流，要用 `goog:loggingPrefs` 打开 driver 日志再过滤：

```typescript
const driver = new Builder()
  .withCapabilities({
    browserName: "chrome",
    "goog:loggingPrefs": { driver: "ALL" },
  })
  .usingHttpAgent(customHttpAgent)
  .usingServer(session.seleniumRemoteUrl)
  .build();

const driverLogs = await driver.manage().logs().get("driver");
driverLogs
  .filter((log) => log.message.includes("browserbase-solving"))
  .forEach((log) => console.log(log.message));
```

**Selenium（Python）**：

```python
options = webdriver.ChromeOptions()
options.set_capability("goog:loggingPrefs", {"driver": "ALL"})
driver = webdriver.Remote(command_executor=session.selenium_remote_url, options=options)

logs = driver.get_log("driver")
for log in logs:
    if "browserbase-solving-started" in log["message"]:
        print("Captcha Solving In Progress")
    elif "browserbase-solving-finished" in log["message"]:
        print("Captcha Solving Completed")
```

### 自定义 CAPTCHA 选择器（非标准验证码提供商）

对不是主流验证码服务（如 reCAPTCHA/hCaptcha）的自定义验证码，需要手动指定两个 CSS 选择器：验证码图片元素、答案输入框元素。做法：右键检查验证码图片元素，取其 `id`（例如 `c_turingtestpage_ctl00_maincontent_captcha1_CaptchaImage`）；同样方式取输入框的 `id`（例如 `ctl00_MainContent_txtTuringText`），然后：

```javascript
browserSettings: {
  captchaImageSelector: "#c_turingtestpage_ctl00_maincontent_captcha1_CaptchaImage",
  captchaInputSelector: "#ctl00_MainContent_txtTuringText"
}
```

### 注意事项
- **默认开启**是最容易被训练记忆或其他平台习惯带偏的地方，写代码前先确认这个场景到底要不要自动求解。
- 与代理搭配使用能提升求解成功率（文档原文表述，具体提升幅度未给出数字）。
- 只在**用户与网站方都授权**的工作流里使用 CAPTCHA solving,遵守目标网站的服务条款和访问控制——这是文档明确写出的使用边界,不是可选建议。
- 账单表把 "Captcha" 能力标为 Free 计划 "No"、Developer/Startup/Scale 均为 "Auto"。⚠ 文档未说明：这与 captcha-solving 页面"Browserbase enables CAPTCHA solving by default for all sessions"（未提及任何计划限制）的表述之间的关系——账单表暗示 Free 计划完全没有这项能力，但功能页没提这个限制,两处未能完全对齐,以实际计划权限为准。

---

## 3. Verified（真实指纹 / stealth 模式）

### 用途
让会话使用 Browserbase 专门构建的 Chromium 浏览器,携带**真实的浏览器指纹**(而不是随机生成的伪造指纹配置),这些指纹被 Browserbase 的反机器人合作伙伴直接识别为"合法"。相比标准会话,能显著减少触发验证码的次数、提高对受保护站点的访问成功率。这与"代理"是完全不同的轴:代理管的是网络层的 IP/地理位置,Verified 管的是浏览器指纹层的可信度,两者组合使用效果最好。

`browserSettings.verified` 取代了旧字段 `browserSettings.advancedStealth`——OpenAPI 对 `advancedStealth` 的描述直接写着 "Deprecated: use `verified` instead"。如果见到旧代码/旧记忆里用的是 `advancedStealth` 或"stealth mode"这个说法,要改用 `verified`。

### 如何启用 / 配置

**默认配置**（自动使用标准桌面指纹），可选加 `os` 指定操作系统指纹（`os` 只在 `verified: true` 时有意义）：

```typescript
// Node.js — 默认桌面指纹
const session = await bb.sessions.create({
  browserSettings: { verified: true }, // 加 os: "mac" 可指定平台指纹
  proxies: true,
});
```

```python
# Python — 默认桌面指纹
session = bb.sessions.create(
    proxies=True,
    browser_settings={"verified": True},  # 加 "os": "mac" 可指定平台指纹
)
```

### 关键参数

| 参数 | 类型 | 取值 | 说明 |
| --- | --- | --- | --- |
| `browserSettings.verified` | boolean | — | 开启 Verified 模式 |
| `browserSettings.os` | string | `windows` / `mac` / `linux` / `mobile` / `tablet` | 改变 user agent 及浏览器环境信号以匹配所选平台;**只有搭配 `verified: true` 才有意义** |
| `browserSettings.advancedStealth` | boolean | — | **已废弃**,用 `verified` 代替 |

### OS 指纹对应的视口尺寸（近似值，随时可能变）

| OS | 视口 | 用途 |
| --- | --- | --- |
| `linux` | 1280x720 | Linux 环境桌面自动化 |
| `windows` | 1280x720 | Windows 专属测试 |
| `mac` | 1280x720 | macOS 自动化 |
| `mobile` | 384x696 | 移动端 App 测试 |
| `tablet` | 800x1200 | 平板响应式测试 |

### 报错与校验规则（文档原文表格）

| 场景 | 结果 | 说明 |
| --- | --- | --- |
| `verified: false` + 指定 `os` | 报错 | 不开 Verified 不能用 `os` |
| 无效的 `os` 值（如 `"android"`） | 报错 | 只支持 windows/mac/linux/mobile/tablet 五个值 |
| 不指定 `os` | 使用默认配置 | 回退到默认桌面指纹 |

### 注意事项——`viewport` 在 Verified 会话里会被忽略

这是一个**明确写在文档里、极容易被忽视的限制**:无论选择哪个 `os`,Verified 会话一律使用标准化视口配合完整的预制指纹档案,**`browserSettings.viewport` 的自定义设置对 Verified 会话不生效**,即便你在请求里传了 `viewport.width`/`viewport.height` 也一样。上表列出的视口尺寸只是"大致参考值",随时可能因 Browserbase 优化指纹档案而变化,**不要在自动化逻辑里硬编码依赖这些具体数值**。如果业务场景必须要自定义视口,只能关闭 Verified(`verified: false`),按标准方式配置 `browserSettings.viewport`(见 Viewports 相关文档,不在本文件覆盖范围)。

同理,文档建议:通过 Playwright 等框架去修改视口尺寸或 user agent 字符串会破坏预制指纹档案的完整性,不要这么做——这些指纹字段是作为一整套互相配合的档案设计的,单独改动其中一项反而会让指纹显得不自然。

### 计划门槛

Verified 是 **Scale 计划**的能力,联系 hello@browserbase.com 可以在低档位试用或讨论升级。可以先用标准会话 + 代理搭建概念验证(proof of concept)。

**⚠ 文档未说明**:账单表(Identity & bot detection 一节)把 Developer / Startup 两档标注为 Verified = **"Basic"**,只有 Scale 档标注为完整的 "Verified"。overview 页面的措辞则是"Browserbase offers Verified on the Scale plan"(暗示低档位完全没有)。两处对不上——"Basic" 档到底解锁了 `verified: true` 的哪部分能力(是否有指纹质量差异、是否有 `os` 定制、是否有次数限制)文档完全没有解释。写代码前建议先用最低成本的方式(比如 Developer 计划直接调用 `verified: true` 试一次)实测确认,而不是假设它完全不可用或完全等同于 Scale 档。

此外该页面明确写着"这个功能目前处于 Beta"(This feature is currently in beta)——指的是第二节的 OS 定制能力,不是 Verified 整体。

### 最佳实践（文档原文）

- 大多数场景直接用 `verified: true`、不指定 `os`,默认档已经是为最高成功率优化过的。
- 只有明确要匹配目标平台(比如测 Windows 专属功能)时才指定 `os`。
- 搭配 Contexts(跨 session 持久化 cookie/登录态)使用时,**切换 `os` 可能降低自动化成功率**——文档给出的是一条警告,没有解释具体机制,视为需要实测验证的经验性提示。
- 始终搭配代理一起使用以获得最高成功率。

---

## 4. Web Bot Auth（Cloudflare Signed Agents 集成）

### 用途
让代理能够**密码学证明**自己是被授权用户在操作,而不是依赖浏览器行为特征被动地"看起来像真人"。Browserbase 与 Cloudflare 的 Signed Agents 计划合作,让接入该计划的网站可以显式地允许 Browserbase 会话通过,同时不必单纯依赖浏览器行为判断来识别授权代理。

### 关键信息（文档内容很简略,如实转录）

- 代理通过 Cloudflare Web Bot Auth 完成鉴权。
- 网站所有者可以显式允许 Browserbase 会话。
- 参与该计划的网站能够识别被授权的代理,而不必只依赖浏览器行为特征。
- **当前处于 Beta,需要通过 https://www.browserbase.com/contact-web-bot-auth 申请获取访问权限**才能为账号启用。

### 注意事项
- ⚠ 文档未说明:没有给出对应的 `browserSettings` 字段名、请求参数或任何代码示例——目前看是账号级别的开通配置,不是每次创建 session 时传的参数。是否需要额外的会话字段待申请开通后确认。
- 与 Verified 的区别:Verified 是"让浏览器指纹看起来真实",Web Bot Auth 是"密码学签名证明授权",两者是完全不同的机制,不要混为一谈。

---

## 5. 网站身份验证管理（2FA / OAuth / 会话保持）

### 用途
处理站点自身的登录/多因素认证流程,并让登录状态能跨会话复用,避免每次自动化都要重新走一遍登录+验证码+2FA。这不是一个单一开关,而是一套组合策略:Contexts(持久化登录态)+ Verified(降低被拦截概率)+ 代理(IP 一致性)+ 人工在环(Session Live View)。

### 如何启用 / 配置

**策略一:创建带 Context + 代理 + 指纹的会话,登录一次后持久化**

```typescript
// Node.js
import { Browserbase } from "@browserbasehq/sdk";

async function createAuthSession(contextId: string) {
  const bb = new Browserbase({ apiKey: process.env.BROWSERBASE_API_KEY! });
  const session = await bb.sessions.create({
    browserSettings: {
      context: { id: contextId, persist: true },
    },
    proxies: [{
      type: "browserbase",
      geolocation: { city: "New York", state: "NY", country: "US" },
    }],
  });
  return session;
}
```

```python
# Python
from browserbase import Browserbase
import os

bb = Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])

def create_auth_session(context_id: str):
    return bb.sessions.create(
        browser_settings={"context": {"id": context_id, "persist": True}},
        proxies=[{"type": "browserbase", "geolocation": {"city": "New York", "state": "NY", "country": "US"}}],
    )
```

**流程**:①创建带 `browserSettings.context.id` + `persist: true` 的会话 → ②用 Session Live View URL 打开该会话,人工手动登录一次 → ③登录完成后,该 context 的 cookie/session token/local storage 已经落盘 → ④以后所有新会话只要引用同一个 `context.id`,创建出来就已经是登录状态,不需要再走一遍登录流程。

### 2FA 挑战的两种处理策略

1. **关闭 2FA 或创建应用专用密码**——如果是内部工具场景,考虑直接关闭目标账号的两步验证;如果安全要求不允许关闭,改用"应用密码"(app password)登录。
2. **把控制权交还给终端用户**——如果两步验证机制无法绕过/关闭,用 Session Live URL 让终端用户在自动化流程中亲自完成这一步验证。

### 用 Verified 应对反自动化的登录流程

很多登录流程会用这些手段拦截自动化:IP 地址限制、User-Agent 过滤、CAPTCHA、限流。Browserbase 给出的应对组合就是本文前几节已经讲过的:代理(保证地理位置/网络身份一致)+ Verified(被反机器人伙伴识别为合法)。

### 复用 Cookie 加速自动化(跳过重复登录)

对基于 Cookie 的会话站点,可以把登录后拿到的 Cookie 存起来,下次直接注入 Cookie 跳过登录流程,而不必依赖 Context 机制。示例逻辑(Playwright,Node.js):先尝试用存储的 cookie 访问受保护页面,如果没被重定向说明已认证、直接跳过登录;否则走正常登录流程,登录后把关键 session cookie(例如 `session_id`)存下来供下次使用。Python 版示例同理,用文件持久化 cookie 列表,每次运行前先 `restore_cookies`,登录成功后 `store_cookies`。

### 处理 Passkey(通行密钥)

Passkey 通常需要真人交互,自动化场景一般要**禁用/绕过**它。做法是通过 Chrome DevTools Protocol 打开一个虚拟 WebAuthn authenticator,让浏览器不再弹出真实的 passkey 提示,从而可以走其他登录方式(如用户名密码):

```typescript
// Node.js（Python 等价写法：page.context.new_cdp_session(page) + client.send("WebAuthn.enable") /
// client.send("WebAuthn.addVirtualAuthenticator", {"options": {...同下, 蛇形/驼峰按 SDK 语言转换...}})）
const client = await page.context().newCDPSession(page);
await client.send('WebAuthn.enable');
await client.send('WebAuthn.addVirtualAuthenticator', {
  options: {
    protocol: 'ctap2',
    transport: 'internal',
    hasResidentKey: true,
    hasUserVerification: true,
    isUserVerified: true,
    automaticPresenceSimulation: true,
  },
});
```

禁用 passkey 后,通常网站还会留一个替代登录入口("Sign in with password"、"Other sign-in options"、用户名密码表单切换等),自动化流程转而走这些入口。

### 注意事项
- 本节内容确实主要来自 `platform/identity/authentication` 这一篇页面,内容本身并不单薄——覆盖了 Contexts 组合策略、Session Live View 人工登录、2FA 两种应对方式、Cookie 复用、Passkey CDP 绕过五个子话题,都有可运行的代码示例。
- 文档在 identity/overview 页面另外链接了一个 "1Password credentials" 集成(从 1Password vault 直接取凭证,不必硬编码),但那是单独一篇集成文档,**本文件的输入材料没有抓取这篇页面**,如实说明未覆盖,不要凭空脑补它的字段名或用法。
- 部署为 Functions(Browserbase 的 serverless 执行环境)时,可以把 `contextId` 定义在 function 的 session 配置里,让认证状态跨函数调用保持——这属于 Functions 专门的机制,不在本文件展开。

---

## 6. 允许域名限制（`allowedDomains`）——限制的是导航,不是整张网络

### 用途
限制一个 session 能够**顶层导航**跳转到的域名范围,防止自动化流程意外跑到目标域名之外的地方去。这是一个访问控制/护栏功能,目的是"让自动化会话专注在预期范围内",不是完整的网络流量沙箱——这一点极容易被想当然地理解错,必须明确强调。

### 如何启用 / 配置

```typescript
// Node.js
const session = await bb.sessions.create({
  browserSettings: {
    allowedDomains: ["example.com", "docs.example.com"],
  },
});
```

```python
# Python
session = bb.sessions.create(
    browser_settings={"allowedDomains": ["example.com", "docs.example.com"]},
)
```

### 关键参数

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `browserSettings.allowedDomains` | `array<string>` | `[]` | 允许顶层导航跳转到的域名列表;空数组(默认)表示不启用限制 |

匹配规则:域名级匹配,加了 `example.com` 会自动放行所有子域名(`www.example.com`、`a.b.example.com` 等),不需要逐个列出子域名;但**不会**放行完全不同的域名(如 `notexample.com`)。

### ⚠ 关键限制,务必明确知道:这不是网络沙箱

- **只检查顶层(main-frame)导航**。iframe/子 frame 里的跳转、页面内的资源请求(图片、脚本、XHR 等)**完全不受限制**,可以自由加载允许列表之外的域名。如果需要的是"完全隔离该 session 能访问的所有网络目的地",`allowedDomains` 做不到,需要另找方案(比如结合代理路由规则里的域名白名单)。
- 不对 `about:blank`、`chrome://`、`file://` 等非 HTTP(S) 协议的导航生效。
- 这是一个**实验性功能**(experimental),文档明确写了行为未来可能变化,不要把它当作稳定的安全边界来设计关键业务逻辑。

### 注意事项
- 把 `allowedDomains` 当成"防止代理跑偏、聚焦在预期站点范围"的护栏来用是合理场景;把它当成"给会话做网络隔离/防数据泄漏"的安全控制来用则是误用——真出于安全考虑做网络隔离,要另外设计方案。

---

## 7. IP 白名单（把 Browserbase 流量路由进客户自己的 VPN）

### 用途
当下游系统(防火墙、API 网关、第三方系统)只允许来自可信 IP 的流量时,用这个模式把 Browserbase 会话的出口流量路由进客户自己控制的静态代理/VPN,这样下游只需要把这一个代理 IP 加入白名单,而不用管 Browserbase 自身会用哪些出口 IP。

### 如何启用 / 配置

机制上就是"自定义代理"(第 1 节的 `type: "external"`)的一种使用场景,配置字段完全一样:

```typescript
// Node.js
const session = await bb.sessions.create({
  proxies: [
    { type: "external", server: "http://...", username: "user", password: "pass" },
  ],
});
```

流程:①在可信网络内部署一个 VPN 或代理服务器 → ②把这个代理的 IP 加入自己防火墙/后端/第三方系统的白名单 → ③把代理配置传给 Browserbase session → ④Browserbase 的浏览器流量就经由这个代理出站。

### 关键要求

- 代理必须支持 HTTP 或 HTTPS(**不支持 SOCKS5**)。
- 代理必须能被 Browserbase 访问到(公网 IP,或者通过隧道)。
- 需要自己在防火墙/VPN 配置里放行来自 Browserbase 的流量。

### 排查

session 连接失败时依次检查:代理服务器是否公网可达或隧道是否正常、代理 IP 是否正确加入白名单、代理鉴权凭证是否正确、协议是否为 HTTP/HTTPS(而非 SOCKS5)、以及先在本地机器上验证代理本身能否正常工作(排除代理服务器自身的问题)。

### 注意事项
- 这个功能页面本身内容很简短,核心就是"用自定义代理机制反向实现出口 IP 白名单",没有额外的专属字段——字段和第 1 节的自定义代理完全一样,只是使用意图不同(控制自己下游系统的入站白名单,而不是伪装地理位置)。

---

## 8. TLS 证书验证（`ignoreCertificateErrors`）—— 与"信任自定义 CA"是两回事

### 用途
处理浏览器访问目标站点时遇到的 TLS 证书错误(比如目标网站本身证书过期、自签名、或域名不匹配)。**这是一个"整体关闭该 session 的证书校验"的粗粒度开关**,和第 1 节里"给自定义代理的 TLS 拦截行为配置可信 CA"(`proxySettings.caCertificates`)是两种不同粒度、解决不同问题的机制,不要混淆:
- `proxySettings.caCertificates`:**只**让浏览器多信任一个你指定的私有 CA,其余校验逻辑(包括对公共 CA 的校验)照常生效。适用场景:你自己控制的代理/CA 做 TLS 中间人。
- `browserSettings.ignoreCertificateErrors`:**整个 session** 完全不做证书校验,来者不拒。适用场景:目标站点本身的证书有问题(过期、自签名、域名不匹配),而你并不掌控该证书的签发方。

### 常见报错

| 错误码 | 含义 |
| --- | --- |
| `ERR_CERT_AUTHORITY_INVALID` | 浏览器不信任签发者(比如自签名证书或私有 CA)——**这个可以用信任自定义 CA 解决** |
| `ERR_CERT_COMMON_NAME_INVALID` | 证书覆盖的域名和实际访问的域名不匹配——只能用 `ignoreCertificateErrors` |
| `ERR_CERT_DATE_INVALID` | 证书已过期或尚未生效——只能用 `ignoreCertificateErrors` |

只有**顶层导航**失败会抛出脚本可捕获的错误;子资源(比如页面里嵌的分析脚本)证书校验失败是静默的,除非专门监听 `requestfailed` 事件。

### 如何启用 / 配置

```typescript
// Node.js
const session = await bb.sessions.create({
  browserSettings: { ignoreCertificateErrors: true },
});
```

```python
# Python
session = bb.sessions.create(
    browser_settings={"ignoreCertificateErrors": True},
)
```

### 关键参数

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `browserSettings.ignoreCertificateErrors` | boolean | `false` | `false` 时正常执行 TLS 证书校验;`true` 时接受目标主机提供的任意证书 |

### 如何选择:两种机制对应关系

| 报错 | 解决方式 |
| --- | --- |
| `ERR_CERT_AUTHORITY_INVALID`(链本身合法,只是浏览器不认识签发者) | 上传并信任对应的 CA(`proxySettings.caCertificates`,见第 1 节) |
| `ERR_CERT_DATE_INVALID` / `ERR_CERT_COMMON_NAME_INVALID`(证书本身就是无效的) | 只能用 `ignoreCertificateErrors: true`,信任任何 CA 都解决不了 |

### 注意事项(安全警告,文档原文强调)
- `ignoreCertificateErrors` 会对**整个 session** 关闭证书校验,意味着攻击者可以在网络层拦截或篡改流量而浏览器完全无法察觉——这是文档明确给出的安全警告,不是夸大。
- 如果证书问题的根源是"你自己控制签发方"(比如企业代理、自建测试 CA),优先用上传 CA 的方式,把 `ignoreCertificateErrors` 限制在真正必要的那些 session 上,不要图省事全局打开。

---

内容整理自 https://docs.browserbase.com(抓取于 2026-09-21),未使用真实 API Key 验证,实际调用报错优先信任真实 API。
