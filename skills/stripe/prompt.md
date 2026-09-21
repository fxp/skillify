把这份 skill 装进你的 Agent，让它写 Stripe 支付集成代码时不再凭记忆把已废弃的 Charges API 当成推荐方案、不再把 100 倍金额错误埋进代码，也不会漏掉 webhook 签名校验这种能直接导致资金损失的安全漏洞。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill stripe --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill stripe --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/stripe/stripe.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「⚠⚠ 真实资金安全边界（务必遵守）」「用之前先确认 3 件事」三节；
2. `references/` 下有 7 个 `.md`，其中 `idempotency-and-retries.md` 讲的是创建类 `POST` 请求怎么安全带 `Idempotency-Key` 重试；
3. 在 `SKILL.md` 里能搜到「approval_required」字样，是 Stripe 官方给 agent-tagged 受限 key 配的两方审批机制说明。

## 这份 skill 覆盖什么

Stripe API（`api.stripe.com`，文档 `docs.stripe.com/api`）开发最常接的一条主线：鉴权与 test/live 模式隔离、PaymentIntents 支付流程与 Checkout Sessions 的选型、Customers 与已保存的 PaymentMethod、Subscriptions/Billing、webhook 事件与 `Stripe-Signature` 签名校验、幂等重试（`Idempotency-Key`）、错误码与限流；Connect、Tax、Issuing、Terminal 等专项能力不覆盖。

**这份 skill 涉及真实支付，SKILL.md 里明确写了一条安全边界，不能跳过**：本 skill 是「帮 Agent/开发者写对集成代码」的文档参考，**不是「授权 Agent 自主花钱」的许可**——任何会创建真实收费、退款、订阅变更的代码，在连接 live 环境前必须有人明确确认；后续对本 skill 的真实调用验证也只能用 `sk_test_`/`rk_test_` 测试模式密钥配合官方测试卡号，绝不能用 `sk_live_`/`rk_live_`。SKILL.md 还记录了 Stripe 官方给「Agent 该用什么 key」的推荐架构：用受限密钥（`rk_...`）并在创建时标记为 agent-tagged key，Stripe 会对这类 key 发起的敏感操作（创建退款、取消订阅等）自动要求人工审批（返回 `approval_required`，等审核者批准才生效）——这是把「Agent 集成 Stripe」和「Agent 能无监督转移真实资金」解耦的官方机制。

内容不是文档搬运，重点标注了两处真实发现的陷阱：一是**金额永远是目标货币最小单位的整数**（`amount=2000` 是 $20.00），但极少数「零小数货币」（JPY、KRW 等）整数值本身就是金额，不用再乘 100，这是全平台最经典的 100 倍错误来源；二是 **test 和 live 是两套完全隔离的数据世界**，`sk_test_` 和 `sk_live_` 创建的对象 ID（`cus_...`、`pi_...`）字符串格式长得一模一样，光看 ID 本身分辨不出是哪个模式创建的，这是新手极易踩、且不会在代码审查里被发现的坑。另外 SKILL.md 记录了 Stripe「首选支付集成方式」的迁移历史：已废弃的 Charges API → 曾经主流、也是训练语料里常见答案的 PaymentIntents + Elements → 抓取时（2026-09）官方默认推荐的 Checkout Sessions + Payment Element，凭训练记忆写集成代码容易停留在中间那一版。

## 版本

文档版，抓取于 2026-09-21，未用真实凭证验证。实际调用时报错与 skill 不一致，
**以 API 的真实报错为准**，并去 `docs.stripe.com/api` 核实最新情况。涉及真实资金的任何操作，务必遵守上面「安全边界」一节，不要因为 skill 写了怎么调用就默认可以自主执行。
