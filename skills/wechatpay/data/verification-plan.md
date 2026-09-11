# wechatpay skill 验证计划（留给拿到真实凭证的人）

**前提**：一个直连商户号，已经开通 Native 支付（最便宜、不需要 openid）；还要有 appid、商户 API 证书私钥和序列号、微信支付公钥和公钥 ID、APIv3 密钥。
凭证只通过环境变量传给命令，不写进任何文件。验证结束后用 `grep -rn "<私钥或密钥的前 8 位>"` 检查 skill 和 workspace，确认没有泄露。
下面的步骤**只有 V9 和 V10 真的会花钱**（0.01 元支付，然后全额退回）。其余都是只读请求、或者创建之后马上关闭的订单，不产生交易。

每一项做完，把结果写进对应 reference：写上日期和响应片段，把 ⚠ 改成已验证或者 `<!-- Gap: … -->`，并同步修改 SKILL.md 的汇总表。

| # | 优先级 | 要验证的结论 | 怎么测 | 成本 | 怎么判断 |
|---|---|---|---|---|---|
| V1 | P0 | `auth-signing.md` §3 的 Python 客户端能签对名 | `GET /v3/pay/transactions/out-trade-no/NOT_EXIST_TEST_001?mchid=…` | 0 | 返回 404 `ORDER_NOT_EXIST` 就说明签名通过；如果是 401，就对照 §9 排查 |
| V2 | P0 | 签名串必须包含 `?mchid=…` | 同 V1，但签名串故意不带 query | 0 | 应该返回 401 `SIGN_ERROR`，把 message 记下来 |
| V3 | P0 | 用 `requests` 的 `json=` 重新序列化会导致签名失败 | 用紧凑 JSON 签名、用 `json=payload` 发送 Native 下单 | 0（签名不通过，不会建单） | 应该返回 401；如果居然返回 200，说明服务端对 body 做了规范化，要修正 SKILL.md 第 1 条 |
| V4 | P0 | 2xx 应答带有 `Wechatpay-*` 头；请求带或不带 `Wechatpay-Serial: PUB_KEY_ID_…`，应答分别用哪把钥签名 | V1 改用一个存在的订单（V5 创建的） | 0 | 对照 `Wechatpay-Serial` 的值；公钥切换没开启时，看是否仍然用平台证书签名（FAQ 4013038816） |
| V5 | P1 | Native 下单 → 查单是 NOTPAY → 关单返回 204 → 查单是 CLOSED | 下单 0.01 元，**不扫码**，立刻关单 | 0 | 确认 `code_url` 格式；确认 204 应答验签时，第 3 行是空行；确认按商户订单号查单时，未支付订单不带 `transaction_id` |
| V6 | P1 | `amount.total=0` 的报错文本 | Native 下单时传 `total: 0` | 0 | 和 FAQ 给的原文比对，确认 `detail.field` 是不是 `/amount/total` |
| V7 | P1 | 同一个单号换了参数：返回 `403 OUT_TRADE_NO_USED` 还是 FAQ 说的「201」 | V5 的单号（关单之前）换一个金额再下单 | 0 | 记录 HTTP 状态码和 code，解决 `payments.md` §2 的 ⚠ |
| V8 | P1 | `/v3/certificates` 的 `effective_time` 类型、键名有没有尾随空格；公钥模式下的返回 | 调一次 | 0 | 解决 `auth-signing.md` §6 的 ⚠；如果只能用公钥，记录返回的错误 |
| V9 | P1 | 支付回调：4 个头都在；`associated_data` 的实际取值；解密代码能用；返回 204 后不再重发 | 真实支付 0.01 元（Native 扫码） | 0.01 元 | 把原始回调报文存成样本（脱敏）；解决 `notifications.md` §11 的 ⚠；确认 `bank_type` / `trade_type` 的值 |
| V10 | P1 | 退款全流程：申请退款返回 PROCESSING 或 SUCCESS；查询退款；退款回调里的字段名是 `refund_status`；传了 `notify_url` 收到的是 JSON | 对 V9 的订单全额退款 | 退回 0.01 元 | 确认回调和查询的字段名不一样；再用同一个 `out_refund_no` 重复申请一次，确认幂等 |
| V11 | P2 | 退款时不传 `notify_url`、商户平台上又配了地址，会收到 v2 XML 通知 | 需要另一笔 0.01 元的订单 | 0.01 元 | 按需测，可以跳过 |
| V12 | P1 | 账单：`download_url` 实际的 host 和 path；`hash_value` 是按压缩前还是压缩后算的；交易类型那一列的值 | V9 之后第二天 10 点以后，申请 `bill_type=ALL`，分别用 `tar_type=GZIP` 和不压缩各下载一次 | 0 | 分别对压缩流和解压后的内容算 SHA1，看哪个等于 `hash_value`；解决 `bills.md` §7 的 3 个 ⚠ |
| V13 | P2 | 下载账单的应答确实没有签名头；不带 Authorization 下载会返回什么 | 同 V12 | 0 | 记录状态码 |
| V14 | P2 | 敏感字段 OAEP 用 SHA-1 还是 SHA-256 | 只能通过「发起异常退款」触发，没有异常退款单就测不了 | —— | 保持 ⚠，等真的遇到再说 |
| V15 | P3 | 429 的 code 是 `FREQUENCY_LIMITED` 还是 `RATELIMIT_EXCEEDED` | **不要为了验证去压测**，只在日志里偶然碰到时记录 | —— | —— |

**离线就能补的**（不需要凭证）：Query 签名示例（4012365337）复算不出、公钥验签示例（4013053249）对不上，这两处可以反馈给微信支付文档团队。
