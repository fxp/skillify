---
name: alipay
description: 接入支付宝开放平台（opendocs.alipay.com / openapi.alipay.com）商户收款的 API 使用手册——覆盖旧版 gateway.do 网关与新版 v3 两套协议的公共参数和 RSA2 签名（公钥模式 / 公钥证书模式）、当面付（付款码 alipay.trade.pay、订单码 alipay.trade.precreate、轮询与撤销）、电脑网站支付 alipay.trade.page.pay、手机网站支付 alipay.trade.wap.pay、APP 支付 alipay.trade.app.pay、交易查询 / 退款 / 退款查询 / 关闭 / 对账单、异步通知 notify_url 验签与 success 应答、沙箱环境、错误码。当用户提到"支付宝""Alipay""支付宝支付""当面付""扫码支付""付款码""电脑网站支付""手机网站支付""APP 支付""支付宝退款""支付宝回调""异步通知验签""RSA2""支付宝公钥""公钥证书""支付宝沙箱""gateway.do""alipay-sdk-python""alipay.trade"时应主动使用本技能，不要凭记忆编造参数名，也不要套用微信支付等其它支付平台的签名、金额单位和回调应答习惯。
---
# 支付宝开放平台（商户收款）接入指南

支付宝开放平台把收款能力开放成 OpenAPI：线下当面付、电脑 / 手机网站支付、APP 支付，以及配套的查询、退款、关单、对账和异步通知。
本 skill 的目标是让 Agent 第一次就写对签名、金额、回调和结果判定。**本页只做分流与规则，字段表和示例在 references/。**

## ⚠ 验证状态

文档版：内容整理自 <https://opendocs.alipay.com/>（抓取于 2026-09-11），**未用真实凭证调用验证**。
无凭证探测（伪造 `app_id=test`、只读查询、每接口 ≤3 次）打过：旧版生产 / 沙箱网关、旧沙箱域名、v3 生产 / 沙箱路径、
openapi.yaml 里的沙箱 server、页面跳转接口的错误页——结果写在各 reference 的「无凭证探测（2026-09-11）」段落。
签名能否通过、业务错误码、异步通知真实报文都**没有**测到。拿到凭证后按 `alipay-workspace/verification-plan.md` 补测。

## 当前事实

| 项 | 值 |
| :--- | :--- |
| 旧版网关（v2） | `POST https://openapi.alipay.com/gateway.do`，接口名放 `method`，业务参数 JSON 串放 `biz_content` |
| 新版 v3 | `https://openapi.alipay.com/v3/alipay/trade/query` 这类路径 + JSON body；方法以官方 openapi.yaml 为准（`trade/query` 是 POST，账单下载地址是 GET） |
| 沙箱 | `https://openapi-sandbox.dl.alipaydev.com`（`/gateway.do` 或 `/v3/...`）；APPID、私钥、支付宝公钥与生产完全独立 |
| v2 鉴权 | 参数 `sign`：除 `sign` 和空值外全部参数按 key 升序 `k=v&…`（**`sign_type` 参与**），SHA256WithRSA，`sign_type=RSA2`，`timestamp=yyyy-MM-dd HH:mm:ss` |
| v3 鉴权 | 头 `Authorization: ALIPAY-SHA256withRSA app_id=…,timestamp=<毫秒>,nonce=<随机>,sign=<base64>`；签 `authString\nMETHOD\n/path?query\nbody\n` |
| 密钥 | 应用私钥签名；**验签用「支付宝公钥」（不是应用公钥）**；每个 APPID 只能选「密钥」或「证书」一种；转账 / 红包必须证书 |
| 金额 | `total_amount` / `refund_amount` 单位**元**，两位小数字符串，`[0.01, 100000000]` |
| 出错形态 | v2：**HTTP 200**，看 `<method>_response.code`（`10000` 成功）；v3：HTTP 4xx/5xx + `{code,message,links}`（均经无凭证探测证实） |
| Python | 官方只有旧版 SDK `alipay-sdk-python`（`alipay.aop.api`）；**v3 没有 Python SDK**，要自己签名 |

## 照通用经验写容易错的地方（来自文档，未实测）

1. **`code=10000` 只代表请求成功。** 付款码支付要看查询 / 通知的 `trade_status`；退款要看 `fund_change=Y` 或退款查询的 `refund_status=REFUND_SUCCESS`；查询接口 `10000` 只代表查到了。
2. **异步通知验签要去掉 `sign` 和 `sign_type` 两个参数，请求签名时 `sign_type` 却要参与。** 通知是表单 POST（不是 JSON），验签后还要比对 `out_trade_no`、`total_amount`、`seller_id`、`app_id`，最后回**纯文本 `success`**（恰好 7 个字符），否则会一直重发。
3. **支付结果只发到下单时传的 `notify_url`，不是控制台的「应用网关」。** 默认只有 `TRADE_SUCCESS` 触发通知；关单、全额退款默认不通知。`TRADE_SUCCESS` 和 `TRADE_FINISHED` 都算付款成功；`TRADE_CLOSED` 也可能是「付过后全额退款」。
4. **电脑网站 / 手机网站 / APP 支付的服务端不「下单」，只签名。** 用 `pageExecute`（form 或 GET URL）/ `sdkExecute`（`orderStr`）交给浏览器或 APP；没有同步 `trade_no`。v3 描述文件里没有这三个接口的路径，v3 SDK 也仍用 `pageExecute` / `sdkExecute` 传 method。
5. **当面付付款码返回 `10003`（等待付款）或 `20000`（未知）时，要轮询查询，超时后紧接着撤销 `alipay.trade.cancel`。** 撤销只用于结果未知；正常退款一律走 `alipay.trade.refund`。订单码 `product_code=QR_CODE_OFFLINE`，付款码默认 `FACE_TO_FACE_PAYMENT`。
6. **部分退款：每笔新退款换 `out_request_no`，同一笔重试必须沿用原 `out_request_no` 和金额。** 同一交易两次退款间隔 ≥3 秒，退款查询间隔 ≥10 秒；沙箱只能全额退一次。
7. **同步返回不可信。** 旧版同步响应验签要取 `xxx_response` 的原始 JSON 子串（不能反序列化再序列化）；`return_url` 回跳和 APP 的 `resultStatus=9000` 只能用来展示，最终以通知 / 查询为准。

## 我要做什么 → 读哪一份

| 我要做什么 | 读 | 核心 endpoint |
| :--- | :--- | :--- |
| 选 v2 还是 v3、配密钥 / 证书、初始化 SDK、自己实现签名与响应验签 | [`signing-and-protocols.md`](references/signing-and-protocols.md) | `POST /gateway.do` · `POST /v3/alipay/trade/*` |
| 线下收银：扫用户付款码、生成订单二维码、轮询与撤销 | [`face-to-face.md`](references/face-to-face.md) | `alipay.trade.pay` · `alipay.trade.precreate` · `alipay.trade.cancel` |
| 电脑网站、手机网站 H5、APP 内拉起支付宝 | [`web-and-app-pay.md`](references/web-and-app-pay.md) | `alipay.trade.page.pay` · `alipay.trade.wap.pay` · `alipay.trade.app.pay` |
| 查订单、退款、查退款、关单、下载对账单 | [`trade-query-refund-close.md`](references/trade-query-refund-close.md) | `alipay.trade.query` · `alipay.trade.refund` · `alipay.trade.fastpay.refund.query` · `alipay.trade.close` · `alipay.data.dataservice.bill.downloadurl.query` |
| 接收支付结果回调、验签、应答、处理重试；同步回跳 | [`notify-and-verify.md`](references/notify-and-verify.md) | `POST notify_url`（trade_status_sync） |
| 沙箱网关、沙箱账号 / 钱包、沙箱与生产差异、切生产 | [`sandbox.md`](references/sandbox.md) | `https://openapi-sandbox.dl.alipaydev.com/gateway.do` |
| 看懂报错、区分「失败」和「结果未知」、限流 | [`errors.md`](references/errors.md) | 公共 `code/sub_code` · v3 HTTP 状态 + `code` · `ACQ.*` |

本 skill 不覆盖：JSAPI / 小程序支付（opendocs.alipay.com/mini）、商家扣款 / 周期扣款、预授权支付、刷脸付设备接入、分账、转账到支付宝账户与红包（资金支出，须证书模式）、花呗分期细节、营销 / 会员 / 电子发票、服务商代开发与 `app_auth_token` 授权流程、APP 客户端 SDK 集成细节——文档见 <https://opendocs.alipay.com/open/065yhr>（产品地图）与 <https://opendocs.alipay.com/isv>。

## House rules

- 密钥只走环境变量（`ALIPAY_APP_ID`、`ALIPAY_APP_PRIVATE_KEY`、`ALIPAY_PUBLIC_KEY`、`ALIPAY_GATEWAY`），沙箱 / 生产**成组切换**；私钥永远不进客户端代码。
- 金额在代码里用 Decimal 或「分」整数存，调接口前格式化成两位小数的**元**字符串；比较通知金额用 Decimal。
- 不往 `biz_content` 塞文档外的字段（「可能导致请求被拦截」「退款失败或重复退款」）；`subject` 不含 `/ = &`。
- 下单一定传 `notify_url`，并同时实现主动查询兜底；换 `out_trade_no` 重下单前先查旧单，未付则先关单。
- 结果未知（`20000`、`isp.unknow-error`、`ACQ.SYSTEM_ERROR`、超时）一律查询确认，绝不直接判失败、绝不换号重扣。
- 错误处理按协议分开写：v2 看 `code/sub_code`，v3 看 HTTP 状态 + `code`；匹配错误码用包含判断。
- Python 调 v3 时，签名用的 body 字符串必须与发送的字节一致（`data=` 发送，不要 `json=`）。

## 文档与无凭证探测不符之处（`<!-- Gap: … -->`，已在 reference 中标记）

- 官方 Python SDK 文档示例的 `server_url` 仍是旧沙箱 `https://openapi.alipaydev.com/gateway.do`：**TLS 证书已过期**，连不上（`signing-and-protocols.md`、`sandbox.md`）。
- 官方 v3 描述文件 openapi.yaml 的沙箱 server `http://openapi.sandbox.dl.alipaydev.com`：http 返回 404、https 证书主机名不匹配；应为 `https://openapi-sandbox.dl.alipaydev.com`（`sandbox.md`）。
- v3 签名页说无签名返回 401；实际不带 `Authorization` 返回 **400 `missing-timestamp`**（`signing-and-protocols.md`、`errors.md`）。
- openapi.yaml 把错误体 `links` 声明为 string，实际是 `[{link, desc}]` 数组（`errors.md`）。

## 文档自相矛盾 / 未说明之处（⚠ 汇总）

- v3 authString 参数表没有 `expired_seconds`，示例与官方 Postman 脚本都带；`appAuthToken` 表中列为 authString 字段、正文却作为单独一行签名（`signing-and-protocols.md` §6）。
- 旧版签名页要求 form-urlencoded，API 页 cURL 用 `-F` multipart（§4）；`isv.invalid-signature-type` 说支持 RSA/RSA2/HMAC_SHA1，签名页说 RSA2/SM2（`errors.md` §2）。
- v3 SDK 页对支持语言说法三处不一（§3）；v3 基本原则说手机网站支付返回 302，但描述文件无该路径（`web-and-app-pay.md` §1）。
- 付款码 `scene` 标必选又写默认值；precreate 的 `product_code` 在当面付与订单码两处归属不一；轮询总时长 30 秒 / 60 秒两说（`face-to-face.md`）。
- `qr_pay_mode` 枚举缺 `2`；`total_amount` 长度 price(9) vs price(11)（`web-and-app-pay.md`）。
- 通知重试是否先「立即 3 次」各页不一；通知验签是否剔除空值两页说法不一（`notify-and-verify.md` §4、§7）。
- v3 错误码表把 missing/invalid-signature 放 400、签名页说 401；`unknow-error` 同时在 400 和 500；`AQC.SYSTEM_ERROR` / `TRADE_NOT_EXIST` / `INVAILID_ARGUMENTS` 等拼写不一（`errors.md`）。
- 未说明：v3 描述文件不标任何必填字段（必填性取自旧版页面）；Python SDK 的通知验签函数名、`page_execute` 以外的类名 / 属性名；用户扫码前查询返回什么；APP 支付 `product_code` 默认值；v3 通知报文是否与 v2 一致；具体 QPS。
