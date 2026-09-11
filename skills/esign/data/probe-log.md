# e签宝 SaaS API V3 无凭证探测日志（2026-09-11）

全部请求只用伪造的 `appId=test`、伪造签名 `dGVzdHNpZ25hdHVyZQ==`（base64 "testsignature"）和伪造 token `test`，
不含任何真实凭证或个人信息，不创建任何资源。每个接口共请求 2 次（run1 18:39:59、run2 紧随其后，+0800），
两次结果逐条一致。脚本：`esign-workspace/probe.sh`；原始输出：`raw/probe_run1.txt`、`raw/probe_run2.txt`。
响应里没有出现本机出口 IP（无需脱敏）。

## 复现方法

先在 shell 里定义变量（与脚本一致），再复制下面每条命令运行：

```bash
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
NOW=$(python3 -c 'import time;print(int(time.time()*1000))')
OLD=$(python3 -c 'import time;print(int(time.time()*1000)-20*60*1000)')
MD5=$(printf '%s' '{}' | openssl dgst -md5 -binary | base64)   # = mZFLkyvTelC5g8XnyQrpOw==
```

## P1 沙箱：伪造 appId + 伪造签名，POST /v3/files/file-upload-url

```bash
curl -sS -A "$UA" -i -X POST 'https://smlopenapi.esign.cn/v3/files/file-upload-url' \
  -H 'X-Tsign-Open-App-Id: test' -H 'X-Tsign-Open-Auth-Mode: Signature' \
  -H "X-Tsign-Open-Ca-Timestamp: $NOW" -H 'X-Tsign-Open-Ca-Signature: dGVzdHNpZ25hdHVyZQ==' \
  -H 'Accept: */*' -H 'Content-Type: application/json; charset=UTF-8' -H "Content-MD5: $MD5" \
  --data '{}'
```
- run1 / run2：HTTP/2 401；响应头有 `x-tsign-elapse-time`、空的 `x-tsign-trace-id`，**无 content-type**
- 响应体：`{"success":false,"code":401,"message":"无效的应用"}`

## P2 正式：同 P1，域名换成 openapi.esign.cn

```bash
curl -sS -A "$UA" -i -X POST 'https://openapi.esign.cn/v3/files/file-upload-url' \
  -H 'X-Tsign-Open-App-Id: test' -H 'X-Tsign-Open-Auth-Mode: Signature' \
  -H "X-Tsign-Open-Ca-Timestamp: $NOW" -H 'X-Tsign-Open-Ca-Signature: dGVzdHNpZ25hdHVyZQ==' \
  -H 'Accept: */*' -H 'Content-Type: application/json; charset=UTF-8' -H "Content-MD5: $MD5" \
  --data '{}'
```
- run1 / run2：HTTP/1.1 401 Unauthorized（正式域名走 HTTP/1.1，沙箱走 HTTP/2）
- 响应体：`{"success":false,"code":401,"message":"无效的应用"}`

## P3 沙箱：不带任何 X-Tsign-Open-* 头

```bash
curl -sS -A "$UA" -i -X POST 'https://smlopenapi.esign.cn/v3/files/file-upload-url' \
  -H 'Accept: */*' -H 'Content-Type: application/json; charset=UTF-8' --data '{}'
```
- run1 / run2：HTTP/2 401
- 响应体：`{"success":false,"code":401,"message":"TOKEN_CANT_BE_NULL"}`

## P4 沙箱：GET /v3/sign-flow/test/detail，伪造 appId + 伪造签名，无 body、无 Content-MD5

```bash
curl -sS -A "$UA" -i -X GET 'https://smlopenapi.esign.cn/v3/sign-flow/test/detail' \
  -H 'X-Tsign-Open-App-Id: test' -H 'X-Tsign-Open-Auth-Mode: Signature' \
  -H "X-Tsign-Open-Ca-Timestamp: $NOW" -H 'X-Tsign-Open-Ca-Signature: dGVzdHNpZ25hdHVyZQ==' \
  -H 'Accept: */*' -H 'Content-Type: application/json; charset=UTF-8'
```
- run1 / run2：HTTP/2 401；`{"success":false,"code":401,"message":"无效的应用"}`

## P5 沙箱：时间戳为 20 分钟前（文档说 15 分钟有效）

```bash
curl -sS -A "$UA" -i -X POST 'https://smlopenapi.esign.cn/v3/files/file-upload-url' \
  -H 'X-Tsign-Open-App-Id: test' -H 'X-Tsign-Open-Auth-Mode: Signature' \
  -H "X-Tsign-Open-Ca-Timestamp: $OLD" -H 'X-Tsign-Open-Ca-Signature: dGVzdHNpZ25hdHVyZQ==' \
  -H 'Accept: */*' -H 'Content-Type: application/json; charset=UTF-8' -H "Content-MD5: $MD5" \
  --data '{}'
```
- run1 / run2：HTTP/2 401；`{"success":false,"code":401,"message":"无效的应用"}`
- 结论：应用校验先于时间戳校验，伪造 appId 下**测不到** `INVALID_TIMESTAMP`；15 分钟窗口仍是文档原文，未实测。

## P6 沙箱：不存在的路径 POST /v3/not-exist-xyz

```bash
curl -sS -A "$UA" -i -X POST 'https://smlopenapi.esign.cn/v3/not-exist-xyz' \
  -H 'X-Tsign-Open-App-Id: test' -H 'X-Tsign-Open-Auth-Mode: Signature' \
  -H "X-Tsign-Open-Ca-Timestamp: $NOW" -H 'X-Tsign-Open-Ca-Signature: dGVzdHNpZ25hdHVyZQ==' \
  -H 'Accept: */*' -H 'Content-Type: application/json; charset=UTF-8' -H "Content-MD5: $MD5" \
  --data '{}'
```
- run1 / run2：HTTP/2 401；`{"success":false,"code":401,"message":"无效的应用"}`
- 结论：网关先鉴权后路由，路径写错在鉴权失败时看不出来（不能用 401 判断路径是否存在）。

## P7 沙箱：OAuthToken 换 token（伪造 appId / secret）

```bash
curl -sS -A "$UA" -i -X GET 'https://smlopenapi.esign.cn/v1/oauth2/access_token?appId=test&secret=test&grantType=client_credentials'
```
- run1 / run2：**HTTP/2 200**；`content-type: application/json;charset=UTF-8`；带非空 `x-tsign-trace-id`
- 响应体：`{"code":72000032,"message":"应用停用或应用不存在","data":null}`
- 结论：换 token 接口的失败走 HTTP 200 + 业务码 `72000032`（该码在抓到的错误码页里没有出现），与网关 401 不同。

## P8 沙箱：OAuthToken 鉴权头（伪造 token）调业务接口

```bash
curl -sS -A "$UA" -i -X POST 'https://smlopenapi.esign.cn/v3/files/file-upload-url' \
  -H 'X-Tsign-Open-App-Id: test' -H 'X-Tsign-Open-Token: test' \
  -H 'Content-Type: application/json; charset=UTF-8' --data '{}'
```
- run1 / run2：HTTP/2 401；`{"success":false,"code":401,"message":"无效的应用"}`

## P9 沙箱：只带 X-Tsign-Open-App-Id，漏掉 Auth-Mode / Signature / Timestamp

```bash
curl -sS -A "$UA" -i -X POST 'https://smlopenapi.esign.cn/v3/files/file-upload-url' \
  -H 'X-Tsign-Open-App-Id: test' \
  -H 'Accept: */*' -H 'Content-Type: application/json; charset=UTF-8' --data '{}'
```
- run1 / run2：HTTP/2 401；`{"success":false,"code":401,"message":"TOKEN_CANT_BE_NULL"}`
- 结论：漏传 `X-Tsign-Open-Auth-Mode: Signature` 时网关按 OAuthToken 模式处理，报的是 “TOKEN 不能为空”，
  与 401 排查页“如果没有指定该请求头，默认为 OAuthToken 鉴权模式”一致。签名模式下看到 `TOKEN_CANT_BE_NULL` 先查 Auth-Mode。

## 汇总

| # | 结论（两次复现一致） | 与文档关系 |
| --- | --- | --- |
| P1/P2 | 两个域名都在线；伪造 appId → HTTP 401 + `{"success":false,"code":401,"message":"无效的应用"}` | 与 401 排查页一致；公共响应格式表没写 `success` 字段和 HTTP 401 |
| P3/P9 | 缺 Auth-Mode（或缺全部头）→ `TOKEN_CANT_BE_NULL` | 与 401 排查页一致 |
| P5 | 过期时间戳在伪造 appId 下仍报“无效的应用” | 15 分钟窗口无法无凭证验证 |
| P6 | 不存在的路径也是 401 | 文档未说明鉴权与路由的先后 |
| P7 | 换 token 失败是 HTTP 200 + `72000032` | 错误码页未收录 72000032 |
| P8 | 伪造 token → “无效的应用” | — |

没有发现能证实“文档写错”的探测结果，因此 skill 中没有 `<!-- Gap: … -->` 标记。
