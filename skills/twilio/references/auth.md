# 鉴权 — HTTP Basic Auth，不是 Bearer

⚠ 本文件里的每一条陈述都是 `⚠ 文档原文，未实测`（来自 `docs.twilio.com` 以及 `twilio_api_v2010` / `twilio_iam_v1` OpenAPI 规范，抓取于 2026-09-21），除非另有标注。没有一条是对着真实 Twilio 账号确认过的。

## 目录
- 这个坑：是 Basic Auth，不是 Bearer
- 两套凭证对，一种鉴权方式
- 该用哪一种？
- 凭证在哪、怎么拿
- 第三种、不相关的鉴权方式：OAuth apps
- Region 相关的凭证
- 鉴权错了会发生什么

## 这个坑：是 Basic Auth，不是 Bearer

**Twilio 的每一个 REST API 请求（Messages、Calls、Verify、Voice、Pricing、IAM……）都用 HTTP Basic Auth 鉴权，不是 `Authorization: Bearer <token>`。** 每个产品的 OpenAPI 规范（`twilio_api_v2010.json`、`twilio_verify_v2.json`、`twilio_iam_v1.json`）里的 `securitySchemes` 都把 `accountSid_authToken: {scheme: "basic", type: "http"}` 声明为主鉴权方式。

```bash
curl -X GET "https://api.twilio.com/2010-04-01/Accounts.json?PageSize=20" \
  -u $TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN
```

`-u user:pass`（或者你自己手动构造的 `Authorization: Basic base64(user:pass)` 头）是对的。**如果你写的是 `Authorization: Bearer $TWILIO_AUTH_TOKEN`——这是这个时代接完大多数其他 REST API 之后的默认手感——每个请求都会失败，报 HTTP 401 / 错误码 20003（"Permission Denied"）。** 这个报错看起来就像凭证错了，而不是鉴权方式错了，这正是这个坑容易被漏掉的原因：修法不是"换一个新 token"，而是"别发 `Bearer` 了"。

Twilio 的服务端 SDK（Python/Node 的 `twilio` 包等）会帮你把 Basic Auth 头拼好——条件允许就用它们，这整类 bug 就不存在了。

## 两套凭证对，一种鉴权方式

Twilio 有**两种不同的凭证，都通过 HTTP Basic Auth 鉴权**——不要把"用哪种 scheme"（永远是 Basic）和"用哪对凭证"（有两种）搞混：

| 凭证对 | 用户名 | 密码 | 从哪拿 |
|---|---|---|---|
| Account SID + Auth Token | `TWILIO_ACCOUNT_SID`（以 `AC…` 开头） | `TWILIO_AUTH_TOKEN` | Twilio Console 首页 |
| API Key SID + API Key Secret | `TWILIO_API_KEY`（以 `SK…` 开头） | `TWILIO_API_SECRET` | Console → API keys & tokens，或 Key 资源的 API |

两者作为 HTTP Basic Auth 的 `user:pass` 用法完全一样——*方式*不变，变的只是*用哪一对*：

```bash
# Account SID + Auth Token
curl -u $TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN https://api.twilio.com/2010-04-01/Accounts.json

# API Key SID + API Key Secret（同样的鉴权方式，不同的凭证对）
curl -u $TWILIO_API_KEY:$TWILIO_API_SECRET https://api.twilio.com/2010-04-01/Accounts.json
```

```python
# Python SDK — API Key + Secret，Account SID 单独传
from twilio.rest import Client
client = Client(api_key, api_secret, account_sid)

# Python SDK — Account SID + Auth Token（两参数写法）
client = Client(account_sid, auth_token)
```

```javascript
// Node SDK — API Key + Secret，Account SID 放在 options 里
const client = twilio(apiKey, apiSecret, { accountSid: accountSid });

// Node SDK — Account SID + Auth Token（两参数写法）
const client = twilio(accountSid, authToken);
```

注意**构造函数的参数顺序因凭证类型而不同**——SDK 会根据调用的形状来推断你传的是哪一对，如果参数传反了（比如把 `authToken` 传到了期望 `apiSecret` 的位置），不会抛出一个友好的报错；它只会像任何一个错误凭证一样鉴权失败。

## 该用哪一种？

Twilio 官方的说法（`docs.twilio.com/usage/requests-to-twilio`，抓取于 2026-09-21）：

> "Use API keys for your applications unless the API reference or guide specifies Account SID and Auth Token authentication."
>（应用应该用 API key，除非某个 API 参考文档或指南特别指明要用 Account SID 和 Auth Token 鉴权。）

API Key 的类型：

| Key 类型 | 权限范围 | 能在 Console 创建 | 能通过 API 创建 |
|---|---|---|---|
| `Main` | 完全权限，等同于 Account SID + Auth Token | 是 | 否 |
| `Standard` | 除 `/Accounts` 和 `/Keys` 外的所有资源 | 是 | 是 |
| `Restricted` | 按资源细粒度授权 | 是 | 是（仅限 v1 Key 资源） |

**Account SID + Auth Token** 专门用在：账号管理类端点（母账号凭证管理子账号）、Auth Token 轮换 / Secondary Auth Token 相关端点、测试凭证示例，以及任何文档明确说要用它的场景（比如 A2P 10DLC ISV 入驻流程）。Standard API key 不能调 `/Accounts` 或 `/Keys`——用它调这两个会导致错误码 20003，这是文档写明的行为，不是你的 key 有问题。

**本地开发/快速脚本**：Account SID + Auth Token 最简单（不用先去创建 key）。**生产环境**：应该去申请一个 API Key，这样长期有效的 Auth Token 就不会出现在应用代码里，泄露了也能单独吊销这个 key 而不用轮换 Auth Token（轮换 Auth Token 会连带破坏所有用它做 webhook 签名校验的地方——见 `references/webhooks-and-signatures.md`）。

## 凭证在哪、怎么拿

- Account SID + Auth Token：Twilio Console 首页（`twilio.com/console`）。
- API Key：Console → **Account → API keys & tokens**，或者通过 API 调 `POST /v1/Keys`（需要用 Account SID + Auth Token 或一个 Main key 才能创建）。
- 这些都应该存在环境变量里（`TWILIO_ACCOUNT_SID`、`TWILIO_AUTH_TOKEN`、`TWILIO_API_KEY`、`TWILIO_API_SECRET`）——不要硬编码或提交进代码仓库。API Key 的 **Secret 只在创建时显示一次**；丢了的话只能吊销这个 key 再新建一个（没有"重新查看 secret"这个功能）。⚠ 文档原文，未实测——"secret 只显示一次"是 Console 文档写的，没有亲自验证过。

## 第三种、不相关的鉴权方式：OAuth apps

Verify 和 IAM 的 OpenAPI 规范里还声明了第二种 scheme，`access_token_bearer: {type: "http", scheme: "bearer", bearerFormat: "access_token"}`。这是真正的 `Authorization: Bearer <token>`——但它属于一个**独立的、需要主动开启的功能**（面向组织级或账号级访问的 OAuth 2.0 Client Credentials / Authorization Code 应用，`docs.twilio.com/iam/oauth-apps`），不是调这些 API 的默认方式。不要因为规范里出现了这个 scheme，就推断 Bearer token 在 Twilio 全平台是常态——对绝大多数集成场景（Messages、Calls、Verify 自己的 SID+Token 流程）你用的都是上面说的 Basic Auth。OAuth apps 不在本 skill 范围内；如果确实需要组织级 OAuth，见 `docs.twilio.com/iam/oauth-apps/overview`。

## Region 相关的凭证

如果账号开启了 **Twilio Regions**（数据驻留/区域路由），凭证是按 region 划分的资源——在一个 region 创建的 key 可能无法给路由到另一个 region 边缘节点的请求鉴权。⚠ 文档原文，未实测。如果适用你的场景，见 `docs.twilio.com/global-infrastructure/manage-regional-api-credentials`；大多数账号没开 Regions，可以忽略这条。

## 鉴权错了会发生什么

HTTP 401，带一个 JSON 错误体，Twilio 错误码 **20003 "Permission Denied"**。根据错误字典（抓取于 2026-09-21），文档记载的、和本 skill 这些坑相关的原文原因包括：

- Account SID / Auth Token 组合错误，或者 Auth Token 已被删除/轮换。
- 用 Standard API key 去调需要 Main key 的端点（`/Accounts`、`/v1/Keys`）。
- 该用 API Key SID + Secret 的地方用了 Auth Token（比如签发 Twilio Access Token / JWT——这是另一种面向客户端 SDK 的 token 类型，不在本 skill 范围内）。
- 用测试凭证（Test Credentials）去调正式资源，或反过来。
- 代理/中间件在请求到达 Twilio 之前把 `Authorization` 头剥掉了。

错误体的形状（Twilio 各产品通用的错误信封）：

```json
{
  "code": 20003,
  "message": "...",
  "more_info": "https://www.twilio.com/docs/errors/20003",
  "status": 401
}
```

**⚠ 未直接确认**：发送 `Authorization: Bearer <Auth Token>` 具体会产生 20003 还是另一个不那么精确的 401，没有测试过（没有真实凭证可用）。如果"用你确信是对的凭证，在每一个端点上都立刻拿到 401"，把这当成一个强信号，先去检查鉴权*方式*（Basic 还是 Bearer），再去检查*凭证的值*对不对。
