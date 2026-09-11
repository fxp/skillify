# 支付宝开放平台 · 无凭证探测日志（2026-09-11）

规则：只用明显伪造的 `app_id=test`、伪造签名 `sign=ZmFrZQ==`（"fake" 的 base64），只调只读接口
`alipay.trade.query` / `/v3/alipay/trade/query`，外加一次页面跳转接口 `alipay.trade.page.pay`（app_id 无效，不可能生成真实交易）。
不带任何真实凭证、不带真实个人信息。每个 endpoint × host ≤ 3 次。所有请求带浏览器 UA。
原始响应保存在 `probes/`（P1–P5）。

| # | 时间 (CST) | 请求（已去敏） | HTTP | 响应片段 | 结论 |
|---|---|---|---|---|---|
| P1 | 2026-09-11 17:59 | `POST https://openapi.alipay.com/gateway.do?app_id=test&method=alipay.trade.query&format=JSON&charset=utf-8&sign_type=RSA2&timestamp=…&version=1.0&sign=ZmFrZQ%3D%3D`，body `biz_content={"out_trade_no":"PROBE_FAKE_0001"}`（x-www-form-urlencoded） | 200 | `{"alipay_trade_query_response":{"code":"40002","msg":"Invalid Arguments","sub_code":"isv.invalid-app-id","sub_msg":"无效的AppID参数，解决方案：https://open.alipay.com/api/errCheck?traceId=…&source=openapi"}}`；响应头 `content-type: text/html;charset=utf-8` | 旧网关出错也回 **HTTP 200**，错误在 `<method 下划线>_response` 里；错误响应**不带 `sign`**；Content-Type 声明为 text/html 但正文是 JSON |
| P2 | 2026-09-11 17:59 | 同 P1，host 换成 `https://openapi-sandbox.dl.alipaydev.com/gateway.do` | 200 | `{"alipay_trade_query_response":{"code":"40002","msg":"Invalid Arguments","sub_code":"isv.invalid-app-id","sub_msg":"无效的AppID参数"}}` | 新版沙箱网关存活，错误结构同生产（sub_msg 无解决方案链接） |
| P3 | 2026-09-11 17:59 | 同 P1，host 换成旧沙箱 `https://openapi.alipaydev.com/gateway.do` | —（TLS 失败） | `curl: (60) SSL certificate problem: certificate has expired` | **旧沙箱域名证书已过期**，Python SDK 文档（common/02np8q）示例里的 `server_url` 已不可用 |
| P4 | 2026-09-11 17:59 | 同 P1 但**不带 `sign`** | 200 | `{"alipay_trade_query_response":{"code":"40002",…,"sub_code":"isv.invalid-app-id",…}}` | app_id 校验先于签名存在性校验；拿假 app_id 探测不到 `isv.missing-signature` |
| V1 | 2026-09-11 18:03 | `POST https://openapi.alipay.com/v3/alipay/trade/query`，`Content-Type: application/json`，`Authorization: ALIPAY-SHA256withRSA app_id=test,timestamp=<当前毫秒>,nonce=<uuid>,sign=ZmFrZQ==`，`alipay-request-id: <uuid>`，body `{"out_trade_no":"PROBE_FAKE_0001"}` | 400 | `{"code":"invalid-app-id","links":[{"link":"https://open.alipay.com/api/errCheck?traceId=…&source=openapi","desc":"解决方案"}],"message":"无效的AppID参数"}`；响应头 `content-type: application/json;charset=UTF-8`、`alipay-trace-id: …`；**无** `alipay-signature` 头 | v3 错误用 **HTTP 状态码 + 扁平 `{code,message,links}`**，`code` 是不带 `isv.` 前缀的 kebab-case；`links` 实为**数组**（openapi.yaml 声明为 string） |
| V2 | 2026-09-11 18:03 | 同 V1，host 换成 `https://openapi-sandbox.dl.alipaydev.com/v3/alipay/trade/query` | 400 | `{"code":"invalid-app-id","message":"无效的AppID参数"}` | 沙箱网关同样支持 v3 路径 |
| V3 | 2026-09-11 18:03 | 同 V1，host 换成 openapi.yaml `servers` 里写的 `http://openapi.sandbox.dl.alipaydev.com/v3/alipay/trade/query` | 404 | `404 Not Found`（`Content-Type: application/octet-stream`） | openapi.yaml 的沙箱 server URL（http + `openapi.sandbox`）不可用 |
| V4 | 2026-09-11 18:04 | 同 V3 但改用 **https** | —（TLS 失败） | `curl: (60) SSL: no alternative certificate subject name matches target host name 'openapi.sandbox.dl.alipaydev.com'` | 该主机名没有有效证书；沙箱请用文档写的 `openapi-sandbox.dl.alipaydev.com` |
| V5 | 2026-09-11 18:03 | 同 V1 但**不带 `Authorization` 头** | 400 | `{"code":"missing-timestamp","message":"缺少时间戳参数"}` | 文档（open-v3/054q58）说「无签名 或 签名验证失败的请求将被拒绝，并返回 401 Unauthorized」；实际无签名返回 **400 missing-timestamp** |
| P5 | 2026-09-11 18:04 | `GET https://openapi.alipay.com/gateway.do?app_id=test&method=alipay.trade.page.pay&…&sign=ZmFrZQ%3D%3D&biz_content=<urlencoded, out_trade_no=PROBE_FAKE_0001, total_amount=0.01, product_code=FAST_INSTANT_TRADE_PAY>` | 200 | `content-type: text/html;charset=GBK`，HTML 页面正文（GBK 解码后）：「调试错误，请回到请求来源地，重新发起请求。错误代码 invalid-app-id 错误原因: 无效的AppID参数」 | 页面跳转类接口出错时回的是**给用户看的 GBK 编码 HTML 错误页**，不是 JSON——服务端拿不到结构化错误，只能在浏览器里看到 |

## 未能探测 / 探测不到的

- 签名本身是否正确（需要真实 app_id 才能走到验签那一步——P4、V5 都说明 app_id 校验在前）。
- v3 的 401（签名错误）路径、`nonce` 重放、`timestamp` 超 10 分钟拒绝——都在 app_id 校验之后。
- 异步通知的真实报文、重试节奏、`success` 应答判定——需要真实交易。
- 任何业务错误码（`ACQ.*`）——需要有效 app_id。

## DNS（非 HTTP 请求，仅解析）

`openapi.sandbox.dl.alipaydev.com` 与 `openapi-sandbox.dl.alipaydev.com` 均解析到 110.75.132.25；
`openapi.alipaydev.com` → `openapi.alipaydev.alipaydns.com.` 110.75.132.131；`openapi.alipay.com` → 110.75.244.202 / 110.75.231.202。
