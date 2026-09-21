# Stripe Skill 验证计划

本 skill（`/Users/chopinfeng/Workspace/Skillify/stripe/`）在没有真实 Stripe API Key 的情况下完成了第 1、2 步（抓取真实文档、结构化撰写），**第 3 步（真实调用验证）和第 4 步（with/without 对照实验）尚未执行**。本文件是拿到 key 之后按优先级执行验证的清单，对应 `create-doc-skill` 的 verify.md 降级方案。

## ⚠⚠ 执行验证时的强制规则

1. **只用测试模式密钥**：`sk_test_...` 或 `rk_test_...`。**任何情况下都不能用 `sk_live_` / `rk_live_` 做本清单里的验证**，不需要真实资金也能覆盖以下全部项目。
2. **只用 Stripe 官方测试卡号**（`4242 4242 4242 4242` 等，见 `references/accepting-payments.md` 和 [testing.md](https://docs.stripe.com/testing.md)），不能用任何真实持卡人信息。
3. Key 只通过环境变量传给验证脚本，不写入任何文件；验证完成后全仓库 `grep` 一遍确认没有残留。
4. 创建的测试资源（Customer、Subscription、webhook 端点等）验证完成后清理或明确记录为测试数据，不留垃圾。
5. 每验证一条，按 `verify.md` 的格式把结论写回对应 reference 文件："已用真实 API 验证（日期）：... + 原始报错/响应片段"，同时把状态从 `⚠ 文档原文，未实测` 改掉，并同步更新 `SKILL.md` 顶部的「验证状态」章节。

## 优先级 1：先确认「先确认的几件事」不出错（成本最低、影响面最大）

- [ ] 鉴权格式：`curl -u sk_test_xxx:` 和 `Authorization: Bearer sk_test_xxx` 两种写法是否都如文档所述可用；缺失鉴权时报错的精确 JSON 结构。
- [ ] test/live 隔离：用 test key 创建一个 Customer，记下 `cus_...` ID；尝试用（不同账户或同账户的）live key 查询这个 ID，确认报错类型和 `error.code`（文档原文猜测是 `resource_missing`，需要实测确认精确值）。
- [ ] 30 秒请求：SKILL.md 里的 `POST /v1/payment_intents`（amount=2000, currency=usd, automatic_payment_methods.enabled=true）真实跑通，记录真实响应结构，核对 SKILL.md/accepting-payments.md 里贴的示例响应字段是否仍然一致（OpenAPI 规范和示例可能已经比文档描述新增/删除了字段）。

## 优先级 2：PaymentIntents 核心流程（低成本，文本类调用）

- [ ] 创建 PaymentIntent 省略必填的 `amount` / `currency`，确认报错精确文案和 `error.param`。
- [ ] 用 `pm_card_visa` 测试 PaymentMethod 走「创建 + confirm」两步流程，确认状态从 `requires_payment_method` → `succeeded` 的完整流转,比对 accepting-payments.md 里画的状态图是否准确。
- [ ] 故意传一个不在允许范围内的 `payment_method_types` 值,确认是报错还是静默忽略（verify.md 点名的「静默失效最危险」类型陷阱，本 skill 目前完全没有实测数据）。
- [ ] 用 `4000000000000002`（通用拒付）对应的 `pm_card_visa_chargeDeclined` 测试确认，核对返回的 `error.code`/`decline_code` 是否与 errors-and-limits.md 表格一致。
- [ ] 用 zero-decimal 货币（如 `jpy`）创建一个 PaymentIntent，确认 `amount` 是否确实不需要 ×100（比如传 `amount=500, currency=jpy`），核实 accepting-payments.md「金额」一节的结论。
- [ ] `setup_future_usage=off_session` 创建 + 确认后，查询 Customer 确认 PaymentMethod 是否真的自动 attach。

## 优先级 3：Customers / PaymentMethod / SetupIntent

- [ ] 创建 Customer 只传 `name`，不传 `email`，确认是否报错（文档标了都是 optional，但要实测确认没有隐藏的必填组合）。
- [ ] 直接调用 `/payment_methods/{id}/attach` vs 通过 SetupIntent attach，对比返回对象的字段差异，尝试找到文档里提到的「未经优化」在响应里有没有可观察的信号（比如某个 `allow_redisplay` 或类似字段的差异）——这是 verify.md 点名的「平台独有、其他家没有对应物」的细节，值得重点测。
- [ ] SetupIntent 完整流程（create → confirm）走一遍，确认 `usage=off_session` 时的状态流转和最终 PaymentMethod 是否正确 attach。

## 优先级 4：Subscriptions（低成本，用最小金额的 Price）

- [ ] 创建一个 `$1.00`/月的测试 Price，跑通「创建 Customer → attach 支付方式 → 创建 Subscription」全流程。
- [ ] 分别用 `payment_behavior=allow_incomplete`（默认）和 `default_incomplete` 各跑一次，实测确认两者在「是否同步尝试扣款」上的行为差异是否真的如 subscriptions-and-billing.md 描述——这是本 skill 目前最大的一条未实测但影响面很大的结论。
- [ ] 用拒付测试卡作为默认支付方式创建订阅，确认订阅最终状态、以及能不能从返回的 `latest_invoice.payment_intent` 拿到需要客户端处理的 next action。
- [ ] 确认 500/订阅/月每分钟 10 张发票这类限流数字是否仍然准确（多数情况下正常测试不会触碰到，可以只做文档核实，不需要真的打满限流）。

## 优先级 5：Webhooks（需要能收公网请求，或用 Stripe CLI 本地转发）

- [ ] 用 `stripe listen --forward-to localhost:PORT/webhook` + `stripe trigger payment_intent.succeeded`，跑通 webhooks.md 里贴的 Python/Node 签名校验示例代码，确认能验证通过。
- [ ] 故意用错误的 `whsec_` 或改动 payload 后验证签名，确认确实会抛 `SignatureVerificationError`（验证"不验证=不安全"这条结论背后的机制真的按文档描述工作，而不只是理论正确）。
- [ ] 核对 `Stripe-Signature` header 的真实格式是否和文档给的例子完全一致（`t=...,v1=...,v0=...`）。
- [ ] 如果有条件，手写一遍 HMAC-SHA256 验证算法（不用 SDK），跑通后和 SDK 结果对比，确认 webhooks.md「手写验证算法」章节的步骤描述准确无误。

## 优先级 6：Idempotency（低成本，但需要构造网络失败场景）

- [ ] 用同一个 `Idempotency-Key` 连续发两次一模一样的 PaymentIntent 创建请求，确认第二次返回 `Idempotent-Replayed: true` 且没有创建第二个对象。
- [ ] 用同一个 key、不同参数发两次请求，确认精确报错的 `error.type`（应为 `idempotency_error`）和文案。
- [ ] 故意制造一个 400（比如缺 `amount`），用同一个 key 重试，确认确实拿到缓存的同一个 400（验证 idempotency-and-retries.md 里「4xx 复用 key 只会拿到缓存结果，不会重新校验」这条结论）。

## 优先级 7：Errors and limits（大多可以和上面几步合并测，无需单独预算）

- [ ] 核对本 skill errors-and-limits.md 里列的每个 HTTP 状态码含义，是否和实测报错状态码一致。
- [ ] 如果条件允许（不建议专门为此消耗配额），确认一次 429 响应的 `Stripe-Rate-Limited-Reason` header 是否如文档所述出现。

## 第 4 步：with/without 对照实验（第 3 步完成后再排期）

按 `create-doc-skill` 的 evaluate.md 流程，用 `evals/evals.json` 里的 5 个场景，各起一个读了 skill 的子 Agent 和一个完全不给 skill 的子 Agent，同一个 prompt 生成代码后，用第 3 步实测过的真实行为（而不是"代码读起来像不像对"）判定两版代码谁在真实环境跑得通。5 个场景分别对应：

1. 金额单位（100 倍错误）
2. 幂等键复用（防重复扣款）
3. webhook 签名校验（安全漏洞）
4. test/live 模式混淆
5. 当前推荐的首选支付 API（Checkout Sessions vs 手搭 PaymentIntents，Charges 已废弃）

对照实验报告产出 `stripe-workspace/comparison-report.md`（Markdown，按仓库约定不做 HTML/Artifact），格式遵循 `create-doc-skill` 的 evaluate.md 规范，包含每个场景的 Task/Why 段落和评分表格，并如实记录平局。
