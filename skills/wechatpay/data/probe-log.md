# 微信支付 APIv3 无凭证探测日志

- 执行日期：2026-09-11（北京时间 17:58–18:01）
- 执行环境：本机 curl，User-Agent `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)`（P6 除外）
- 规则：不用任何真实凭证；商户号一律用明显伪造的 `1900000000`，签名一律是 `ZmFrZQ==`（"fake" 的 base64），
  证书序列号全 0；只打查询类 / 必然被鉴权拦下的请求，**没有发起、也不可能发起任何真实交易**。每个 path ≤3 次。
- 原始响应头与响应体保存在 `probe-raw/<编号>.headers|.body`。

| # | 时间 | 请求（已脱敏，全部为伪造值） | HTTP | 响应片段 | 结论 |
|---|---|---|---|---|---|
| P1 | 17:58:31 | `GET https://api.mch.weixin.qq.com/v3/certificates`，**不带 Authorization**，`Accept: application/json` | 401 | `{"code":"SIGN_ERROR","message":"Http头Authorization值格式错误，请参考《微信支付商户REST API签名规则》"}`；有 `Request-ID` 头；**无任何 `Wechatpay-*` 头** | 缺 Authorization 报 401 SIGN_ERROR（不是 400） |
| P2 | 17:58:32 | `POST /v3/pay/transactions/native`，不带 Authorization，body 用伪造 appid/mchid `1900000000`、`amount.total=1` | 401 | `{"code":"SIGN_ERROR","message":"签名信息错误，验签失败"}`；**无 Request-ID、无 `Wechatpay-*` 头** | 同样是缺头，`/v3/pay/transactions/*` 返回的 message 与 P1 不同 |
| P3 | 17:58:32 | `GET /v3/pay/transactions/out-trade-no/PROBE_FAKE_0001?mchid=1900000000`，`Authorization: Bearer fake-token` | 401 | `{"code":"SIGN_ERROR","message":"签名信息错误，验签失败"}` | 用 Bearer 等其他平台的鉴权方案 → 401 SIGN_ERROR |
| P4 | 17:58:32 | 同 P3 的 path，`Authorization: WECHATPAY2-SHA256-RSA2048 mchid="1900000000",nonce_str="PROBE…0001",signature="ZmFrZQ==",timestamp="<当前秒>",serial_no="000…0"` | 401 | `{"code":"SIGN_ERROR","message":"签名错误"}` | 认证类型与字段格式正确、签名是假的 → message 变成「签名错误」 |
| P5 | 17:59:01 | `GET https://api2.mch.weixin.qq.com/v3/certificates`，不带 Authorization | 401 | 与 P1 完全相同的 body，带 `Request-ID` | 备域名 `api2.mch.weixin.qq.com` 存在且行为与主域名一致 |
| P6 | 17:59:01 | `GET /v3/certificates`，**去掉 User-Agent 头**（`-H 'User-Agent:'`），`Accept: application/json` | **400** | `{"code":"INVALID_REQUEST","message":"Http头缺少Accept或User-Agent"}` | 文档说「很可能会拒绝」无 UA 请求——实测是**硬拒绝**，且检查早于签名校验 |
| P7 | 17:59:01 | 同 P3 的 path，Authorization 格式正确但 `timestamp="1554208460"`（文档示例里的 2019 年时间戳） | 401 | `{"code":"SIGN_ERROR","message":"Http头Authorization中的timestamp与发起请求的时间不得超过5分钟"}` | 时间戳 ±5 分钟窗口是真实校验，而且**先于签名校验**：照抄文档示例时间戳会得到这个报错而不是「签名错误」 |
| P8 | 17:59:02 | `GET /v3/pay/transactions/native`（该接口应为 POST） | 405 | 空 body（`Content-Length: 0`） | 方法错误 → 405、无 JSON 错误体 |
| P9 | 17:59:02 | `POST https://api.mch.weixin.qq.com/pay/orderquery`（**v2** 接口），XML body，伪造 mch_id `1900000000`、伪造 32 位 sign | **200** | `Content-Type: text/plain`；`<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA[签名错误]]></return_msg></xml>` | v2 失败也返回 HTTP 200 + XML，必须解析 `return_code`；v3 用 HTTP 状态码 + JSON。两套错误处理不能共用 |
| P10 | 18:01:12 | `GET /v3/certificates`，`Accept: */*`（多数 HTTP 客户端的默认值），不带 Authorization | 401 | 与 P1 相同 | `Accept: */*` 能过「缺少 Accept」检查（进入了鉴权阶段） |
| P11 | 18:01:13 | `POST /v3/refund/domestic/refunds`，不带 Authorization，伪造单号 | 401 | 与 P1 相同 body，带 `Request-ID` | 退款 path 存在（被鉴权拦下，不是 404） |
| P12 | 18:01:13 | `GET /v3/bill/tradebill?bill_date=2026-09-10`，不带 Authorization | 401 | 与 P1 相同 body，带 `Request-ID` | 交易账单 path 存在 |
| P13 | 18:01:13 | `GET /v3/pay/transactions/no-such-endpoint-probe`，不带 Authorization | 404 | 空 body | 不存在的 path → 404 空 body，可以和「path 存在但鉴权失败」（401 JSON）区分开 |

## 汇总出的事实（写进 skill 时标「无凭证探测（2026-09-11）」）

1. **所有被拒的 v3 应答都不带 `Wechatpay-Signature` / `Wechatpay-Serial` / `Wechatpay-Timestamp` / `Wechatpay-Nonce`**
   （P1–P7、P10–P12 的 4xx 均如此）。平台证书验签页写「所有应答，微信支付都会使用平台证书私钥签名（文件下载接口和首次下载平台证书除外）」。
   至少对鉴权失败的 4xx 这句话不成立 → 商户的应答验签代码必须先判 HTTP 状态码，对 4xx/5xx 不能因为「缺签名头」就抛异常掩盖真实错误码。
   （对 2xx 应答是否一定带签名头，无凭证无法验证。）
2. **缺 UA → 400 `INVALID_REQUEST`「Http头缺少Accept或User-Agent」**；这个检查先于鉴权。
3. **timestamp 偏差 >5 分钟 → 401 `SIGN_ERROR`「…timestamp与发起请求的时间不得超过5分钟」**，先于签名校验。
4. 同为 401 `SIGN_ERROR`，message 至少有 4 种：「Http头Authorization值格式错误…」「签名信息错误，验签失败」「签名错误」「…timestamp…不得超过5分钟」。
   → 代码只能按 `code` 分支，message 只用于日志（与文档「同一 code 可能对应多个不同的 message」一致）。
5. `/v3/pay/transactions/*` 的 401 不带 `Request-ID`，`/v3/certificates`、`/v3/refund/*`、`/v3/bill/*` 的 401 带 `Request-ID`。
   文档「基本规则」说「请求的唯一标识包含在应答的HTTP头Request-ID中」——至少在交易类接口的鉴权失败应答里没有。日志代码要容忍 Request-ID 缺失。
6. 备域名 `api2.mch.weixin.qq.com` 可达，行为与主域名一致。
7. v2（`/pay/*`，XML，HTTP 200 + `return_code=FAIL`）与 v3（`/v3/*`，JSON，HTTP 4xx）错误模型完全不同。
8. 405 / 404 为空 body，错误处理代码解析 JSON 前要判空。

## 离线复算（不联网、不用真实凭证）：`offline_vectors.py` → `offline_vectors.out`

文档公开了一对**测试用**商户 API 私钥和若干算好的签名值。用 skill 推荐的 Python 代码（`cryptography`）逐个复算：

| 文档示例 | 结果 | 备注 |
|---|---|---|
| Body 签名（4012365336，JSAPI 下单） | ✅ 一致 | 5 行签名串算法无误 |
| Path 签名（4012365334，查询退款） | ✅ 一致 | |
| Query 签名（4012365337，委托营销查询） | ❌ 不一致 | 见下方单独排查 |
| JSAPI 调起支付 paySign（4012365339） | ✅ 与「得出的签名值」代码块一致 | 但同页 JS 请求示例里的 `paySign` 末尾多了一个 `%`（shell 无换行输出残留），照抄即签名错 |
| APP 调起支付 sign（4012365340） | ✅ 一致 | 同页 iOS 示例 `request.sign` 末尾同样多一个 `%` |
| 应答验签示例（签名 `mfI1CP…`） | 平台证书页（4013053420）的公钥 ✅；**微信支付公钥页（4013053249）的公钥 ❌** | 两页复用同一个签名值，但公钥页换了一把公钥，按该页操作得到 Verification Failure |
| AEAD_AES_256_GCM | ✅ 自加密往返；AAD 不同则 `InvalidTag` | 验证了 nonce / associated_data 按 UTF-8 原串参与、密文 base64 的约定 |

Query 示例单独排查（`scratchpad/qv.py`）：
- 同页测试私钥和 Body 页的是同一把；
- 签名串按文档原样（query 已 URL 编码）、query 先解码、去掉 query，三种写法都算不出文档给的 `UkBXG+nh…`；
- 所以判断文档给的签名值不是按页面上这个签名串算出来的。

以上是文档示例的**内部一致性**问题，不是 API 行为，按 BRIEF 规则在 skill 里标 ⚠，不用 `<!-- Gap -->`。

## 协调者复测（2026-09-11，同样只用伪造商户号）

| # | 请求 | HTTP | 响应 | 结论 |
|---|---|---|---|---|
| R1 | `curl -s -H 'User-Agent:' -H 'Accept: application/json' https://api.mch.weixin.qq.com/v3/certificates`（×2） | 400 | `{"code":"INVALID_REQUEST","message":"Http头缺少Accept或User-Agent"}` | P6 复现 |
| R2 | `curl -s -H 'User-Agent:' -H 'Accept: application/json' https://api.mch.weixin.qq.com/v3/refund/domestic/refunds/probe0001` | 400 | 同上 | 退款接口也有 UA 检查 |
| R3 | `curl -s -H 'User-Agent:' -H 'Accept: application/json' -H 'Content-Type: application/json' -X POST https://api.mch.weixin.qq.com/v3/pay/transactions/native -d '{…伪造 mchid 1900000000…}'` | 401 | `{"code":"SIGN_ERROR","message":"签名信息错误，验签失败"}` | **交易类接口没有 UA 检查**，先报签名错误 → 原结论「缺 UA 必 400、先于鉴权」只对部分接口成立，SKILL.md / reference / site.json 已改 |
