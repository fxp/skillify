# 鉴权、Test/Live 模式隔离、给 Agent 用的 Key

> ⚠ 本文件全部内容转录自 docs.stripe.com（抓取于 2026-09-21），未经真实 API 调用验证。使用前建议至少用测试模式 key 跑通「30 秒请求」核实鉴权格式仍然成立。

## 目录

- [Base URL](#base-url)
- [鉴权 header 精确格式](#鉴权-header-精确格式)
- [三种 API Key 类型](#三种-api-key-类型)
- [Test 模式 vs Live 模式：两个完全隔离的世界](#test-模式-vs-live-模式两个完全隔离的世界)
- [给 Agent 用的 Key：Restricted Key + 审批机制](#给-agent-用的-key-restricted-key--审批机制)
- [Webhook 签名密钥不是 API Key](#webhook-签名密钥不是-api-key)
- [Sandbox vs 传统 Test Mode](#sandbox-vs-传统-test-mode)

## Base URL

```
https://api.stripe.com/v1
```

多数资源在 `/v1` 下。少数较新引入的资源（event destinations、approval requests 等）挂在 `/v2` 下，并且 `/v2` 的请求需要额外带一个 `Stripe-Version` header 指定预览版本号（⚠ 文档示例里看到的是 `Stripe-Version: 2026-08-26.preview`，这个值会随时间变化，不要硬编码，创建 key 前建议在 Dashboard 或对应 API 文档页确认当前值）。本 skill 覆盖的核心支付/客户/订阅/webhook 能力都在 `/v1` 下。

## 鉴权 header 精确格式

Stripe 用 [HTTP Basic Auth](http://en.wikipedia.org/wiki/Basic_access_authentication)：**把 API key 作为用户名，密码留空**。

```bash
curl https://api.stripe.com/v1/customers \
  -u "sk_test_xxx:" \
  # 冒号防止 curl 交互式询问密码，不能省略
```

跨域请求（浏览器直接发请求）场景下用 Bearer 格式：

```
Authorization: Bearer sk_test_xxx
```

两种写法等价，官方 SDK 内部走的是 Bearer 格式。**没有专属的自定义 header（不是 `X-Api-Key`），也不需要额外的 account ID header**（除非在用 Connect 访问连接账号，那种场景会用到 `Stripe-Account` header，超出本 skill 范围）。

所有请求必须走 HTTPS；明文 HTTP 请求直接失败，未带鉴权的请求也直接失败（⚠ 文档原文，未实测）。

## 三种 API Key 类型

| 前缀 | 可否暴露给客户端 | 用途 |
|---|---|---|
| `pk_...` | 可以 | Publishable key，给 Stripe.js / Elements / 移动端 SDK 用，只能创建 token/PaymentMethod，不能读账户数据或创建 charge |
| `rk_...` | **不可以** | Restricted key，权限完全自定义（按资源选 Read/Write/None），**Stripe 官方推荐服务端 / Agent 场景优先用这个** |
| `sk_...` | **不可以** | Secret key，对账户所有资源有完整权限，一旦泄露攻击面等于整个账户 |

每种 key 都有 test/live 两个变体，前缀会体现出来：`pk_test_` / `pk_live_`、`rk_test_` / `rk_live_`、`sk_test_` / `sk_live_`。

Key 的存放：不要写进代码仓库，用平台的 secrets vault，没有的话用环境变量。Live 模式下 Stripe 生成的 key 只在创建时显示一次，丢了只能 rotate（旋转）出一个新的，旧 key 有最多 7 天的双活宽限期以避免服务中断（⚠ 文档原文，未实测）。

## Test 模式 vs Live 模式：两个完全隔离的世界

> **这是本平台最容易踩、也最不会在代码审查里被发现的坑**：test 模式和 live 模式不是"同一份数据的两个开关"，而是完全独立的两套数据。

- Test 模式（或更细粒度的 Sandbox，见下）下的 API 调用只操作**模拟对象**：你能创建、读取、更新的 `Customer`、`PaymentIntent`、`Refund`、`Subscription` 等对象全部是测试数据，卡网络和支付渠道不会真的处理这些"支付"。
- Live 模式下的调用操作**真实对象**，真实资金会被扣、卡网络真的处理支付。
- **每种模式有自己独立的一套 key**：`sk_test_...` 只能操作测试模式的数据，`sk_live_...` 只能操作 live 模式的数据。用 live key 去 `GET /v1/customers/{test 模式创建的 cus_id}` 会失败（⚠ 文档原文"objects in one mode aren't accessible to the other"，未实测报错具体形态，按经验大概率是 `resource_missing` 类的 404，需要真实验证补充确认）。
- **陷阱所在**：test 模式的对象 ID（`cus_xxx`、`pi_xxx`、`sub_xxx`……）和 live 模式的对象 ID **格式完全一样**，字符串本身看不出是哪个模式创建的。唯一能确定一个 ID 属于哪个模式的方法，是记住"这个 ID 是用哪个 key 的响应里拿到的"。如果系统里把 test 模式产生的 ID 意外落进了本该存 live ID 的字段（比如联调阶段用测试 key 跑通流程、上线时忘记换全部相关配置），后续用 live key 查询这个 ID 会直接报错而不是静默返回别的数据——这点是好事（不会读错对象），但报错本身容易被误判成"网络问题"或"权限问题"而不是"key/ID 模式不匹配"，排查时第一件事应该是确认 key 前缀和 ID 所属模式是否一致。

## 给 Agent 用的 Key：Restricted Key + 审批机制

这是 Stripe 官方文档里专门给"AI Agent 使用 Stripe API"场景写的架构建议（⚠ 文档原文，未实测，但内容明确、可操作，建议直接采纳）：

1. **永远用 Restricted Key（`rk_...`），不要把无限制的 `sk_...` 直接交给 Agent**。创建 RAK 时按资源精确勾选 Read / Write / None，只给 Agent 完成任务真正需要的权限（例如只给 `PaymentIntents: Write`、`Customers: Read`，其余全部 None）。
2. **创建 key 时选择 "Authorizing agent access to your account"**，把这个 key 标记为 *agent-tagged*。标记之后：
   - Stripe 会自动为这个 key 发起的一批敏感操作启用**两方审批规则**（默认覆盖：创建退款、取消订阅；可以在 Dashboard **Settings → Approvals** 里自行加上"创建 PaymentIntent"、"银行账户变更"、"创建订阅"等）。
   - Agent 尝试执行被规则覆盖的操作时，API 不会直接执行，而是返回 `approval_required` 错误，并自动生成一个待人工审批的请求。
   - 指定的人工审核者在 Dashboard 批准后，操作才会真正执行；拒绝则该操作作废，不产生任何变更。
   - 可以通过审批相关的 webhook 事件（`v2.core.approval_request.created` / `.approved` / `.rejected` / `.expired` / `.succeeded` / `.failed`）异步感知审批结果。
   - 单人账户（个人开发者账户）依然可以对 agent-tagged key 配置这套规则，因为"Agent 的 key"在 Stripe 眼里算一个独立于账户所有者的 actor。
3. **本 skill 生成的任何"Agent 自动创建退款 / 取消订阅 / 发起大额收款"之类代码，都应该假设背后配了这套审批机制、或者显式加一层人工确认**，不要把"API 调用成功"等同于"资金操作已经安全授权"。

## Webhook 签名密钥不是 API Key

`whsec_...` 是每个 webhook 端点单独生成的**签名密钥**，跟 API Key 是两回事：一个账户下的多个 webhook 端点各有各的 `whsec_`；同一个端点在 test 和 live 模式下的 `whsec_` 也不同。签名验证细节见 [webhooks.md](webhooks.md)。

## Sandbox vs 传统 Test Mode

⚠ 文档原文（`llms.txt` 明确建议，未实测）：**新集成建议用「通用 Sandbox」而不是账户自带的默认 Test Mode**，本地开发和 CI 各用独立的 sandbox，避免共享同一份测试数据导致互相污染设置和数据；已经依赖账户默认 test mode 的老集成、或者用到了 sandbox 暂不支持的功能时才继续用传统 test mode。两者的 key 前缀规则相同（`sk_test_` 等），本 skill 后续统称为"测试模式"，不特别区分具体是哪种 sandbox。
