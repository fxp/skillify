# 支付宝 skill · 验证计划（拿到凭证后执行）

现状：文档版，抓取于 2026-09-11，**未用真实凭证验证**。已做的无凭证探测见 `probe-log.md`。
建议全部先在**沙箱**完成（无需签约、零真实资金），生产只做最后的只读验证。

## 需要的凭证

- 沙箱：沙箱控制台（open.alipay.com/develop/sandbox/app）的 APPID、应用私钥、支付宝公钥（公钥模式）；可选再开证书模式拿三张证书。
- 沙箱买家账号 + Android 沙箱支付宝 App（付款码 / 扫码 / 手机网站 / APP 支付需要）。
- 可选：生产 APPID（已上线、已签约当面付或电脑网站支付），只做查询类只读调用。
- 所有密钥只走环境变量：`ALIPAY_APP_ID`、`ALIPAY_APP_PRIVATE_KEY(_PEM)`、`ALIPAY_PUBLIC_KEY(_PEM)`、`ALIPAY_GATEWAY` / `ALIPAY_V3_HOST`。

## P0 · SKILL.md「当前事实」—— 错了全盘皆错

| # | 结论 | 怎么测 | 判定 | 成本 |
|---|---|---|---|---|
| 1 | 旧版签名：`sign_type` 参与签名、`biz_content` 放 body、其余放 query、form-urlencoded | 用 `signing-and-protocols.md` 的 `call_v2` 调沙箱 `alipay.trade.query`（不存在的单号） | 返回 `40004 ACQ.TRADE_NOT_EXIST` 而非 `isv.invalid-signature` | 0 |
| 2 | 旧版用 `-F`（multipart）传 biz_content 是否也被接受（⚠ 文档自相矛盾） | 同 1，改 multipart | 记录两种 Content-Type 的结果 | 0 |
| 3 | v3 签名：`Authorization: ALIPAY-SHA256withRSA app_id=…,timestamp=…,nonce=…,sign=…`，内容 `auth\nPOST\n/path\nbody\n` | `call_v3("POST","/v3/alipay/trade/query",{…})` | 返回 `ACQ.TRADE_NOT_EXIST` 类业务错误而非签名错误 | 0 |
| 4 | v3 authString 带 / 不带 `expired_seconds` 都能过（⚠） | 同 3，去掉 `expired_seconds` | 记录 | 0 |
| 5 | v3 签名错误返回 401 还是 400（⚠ 文档自相矛盾；探测到无签名是 400 missing-timestamp） | 同 3，故意改坏 sign | 记录 HTTP 状态和 code | 0 |
| 6 | v3 响应验签 `alipay-timestamp\nalipay-nonce\nbody\n` | 对第 3 步成功 / 业务错误响应验签 | 通过；并记录 4xx 业务错误是否带 `alipay-signature` | 0 |
| 7 | 旧版同步响应验签要用 `xxx_response` 原始子串 | 对第 1 步响应手工验签 | 通过；`json.dumps` 重新序列化后失败 | 0 |

## P1 · 收款主链路（沙箱）

| # | 结论 | 怎么测 | 判定 | 成本 |
|---|---|---|---|---|
| 8 | 订单码 `precreate` 需 `product_code=QR_CODE_OFFLINE`；与当面付 `FACE_TO_FACE_PAYMENT` 的关系（⚠） | 两个 product_code 各调一次 | 记录哪个成功 / 报什么 | 沙箱 0 |
| 9 | 用户扫码前 `alipay.trade.query` 返回什么（⚠ 文档未说明） | precreate 后立刻查询 | 记录 `ACQ.TRADE_NOT_EXIST` 还是 `WAIT_BUYER_PAY` | 0 |
| 10 | 付款码 `alipay.trade.pay`：`10000` / `10003` 分支；2000 元以上沙箱要输密码 | 沙箱钱包付款码，分别 0.01 元和 2001 元 | 小额 10000，大额 10003 | 沙箱余额 |
| 11 | `scene` 不传是否默认 bar_code（⚠ 必选 vs 默认值矛盾） | pay 时省略 scene | 记录 | 沙箱 |
| 12 | 轮询超时后 `cancel` 的 `action=close` / `refund` | 10003 后不付款 → cancel；付款后 → cancel | 分别返回 close / refund | 沙箱 |
| 13 | page.pay / wap.pay 用 `page_execute` 生成 form / GET URL；Python SDK 类名、`notify_url`/`return_url` 属性名（⚠ 推断） | 安装 `alipay-sdk-python`，按 web-and-app-pay.md 示例运行 | 能生成 form；浏览器能打开沙箱收银台 | 0 |
| 14 | APP 支付 `sdk_execute` 方法名、`product_code` 不传的默认值（⚠） | Python SDK 生成 orderStr；Android 沙箱 App 支付 | 生成成功；记录默认值行为 | 沙箱 |

## P2 · 回调与退款

| # | 结论 | 怎么测 | 判定 | 成本 |
|---|---|---|---|---|
| 15 | 通知是表单 POST；验签去掉 sign 与 sign_type；空值是否剔除（⚠ 自相矛盾） | 公网 notify_url（如 ngrok）接一次真实沙箱通知，两种拼法各验一次 | 记录哪种通过 | 沙箱 |
| 16 | 默认只有 TRADE_SUCCESS 触发；关单、全额退款不通知 | 付款 → 退款 → 看是否收到第二条通知 | 记录 | 沙箱 |
| 17 | 回非 `success` 的重试节奏（立即 3 次？⚠ 各页不一致） | notify 故意返回 `ok`，记录到达时间 | 记录间隔 | 沙箱 |
| 18 | 退款 `fund_change`；沙箱只能全额退一次 | 退款两次（部分 + 全额） | 第二次报错内容记录 | 沙箱 |
| 19 | 退款查询 `out_request_no` 错误时返回 10000 但无退款信息 | 用错误请求号查 | 记录 | 沙箱 |
| 20 | v3 通知格式是否与 v2 相同（⚠） | 用 v3 `/v3/alipay/trade/precreate` 下单，传 notify_url | 记录通知报文 | 沙箱 |

## P3 · 其它

| # | 结论 | 怎么测 |
|---|---|---|
| 21 | 账单：v3 为 GET + query；沙箱返回模板 | `GET /v3/alipay/data/dataservice/bill/downloadurl/query?bill_type=trade&bill_date=<昨天>` |
| 22 | 证书模式：`app_cert_sn` / `alipay_root_cert_sn`（v2），authString `app_cert_sn` + 头 `alipay-root-cert-sn`（v3） | 沙箱启用证书模式后重跑 P0-1、P0-3 |
| 23 | 生产只读：`alipay.trade.query` 查一个不存在的单号 | 生产 APPID，确认生产网关与签名 |

## 执行后

- 每条结论写回对应 reference：「已用真实 API 验证（YYYY-MM-DD）：做了什么 + 原始响应片段」，并删除已解决的 ⚠。
- 文档错误（与 ⚠ 相符的不一致）加 `<!-- Gap: … -->` 并升到 SKILL.md。
- 按 `evals/evals.json` 跑 with / without skill 对照，写 `comparison-report.md`（Markdown）。
- 同步 SkillForge 站上的数字（见站点 site.json）。
