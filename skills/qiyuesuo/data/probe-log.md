# 契约锁 OpenAPI 无凭证探测日志

- 日期：2026-09-11（18:37 +0800 前后），脚本 `probe.sh`，原始输出 `probe-raw/P<n>_<run>.txt`。
- 全部请求使用伪造 AppToken=`test`、AppSecret=`test`（或不带鉴权头），不含任何真实凭证或个人信息，不创建任何资源。
- 每个探测**连续跑了两次**（run 1、run 2），两次结果逐字一致才写结论。单个接口最多 2 次请求。
- 响应里没有出现本机 IP。原始输出第一行 `HTTP/1.1 200 Connection established` 来自本机 HTTPS 代理，不是契约锁服务器的响应，下文已略去。

## 通用前置（每条命令先执行这段，生成时间戳 / nonce / 伪造签名）

```bash
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
TS=$(python3 -c 'import time;print(int(time.time()*1000))')
NONCE=$(python3 -c 'import uuid;print(uuid.uuid4())')
SIG=$(python3 -c "import hashlib,sys;print(hashlib.md5(sys.argv[1].encode()).hexdigest())" "testtest${TS}${NONCE}")
```

---

## P1 测试环境，伪造 token，合法格式的四个头

```bash
curl -sS -i -A "$UA" \
  -H "x-qys-open-accesstoken: test" -H "x-qys-open-timestamp: $TS" \
  -H "x-qys-open-nonce: $NONCE" -H "x-qys-open-signature: $SIG" \
  'https://openapi.qiyuesuo.cn/v2/contract/detail?contractId=1'
```
- run 1 / run 2：`HTTP/2 442`，`content-type: application/json;charset=UTF-8`，`server: elb`
- 响应体（两次一致）：`{"message":"INVALID TOKEN","code":442,"responseCode":"11990442"}`

## P2 正式环境，同 P1

```bash
curl -sS -i -A "$UA" \
  -H "x-qys-open-accesstoken: test" -H "x-qys-open-timestamp: $TS" \
  -H "x-qys-open-nonce: $NONCE" -H "x-qys-open-signature: $SIG" \
  'https://openapi.qiyuesuo.com/v2/contract/detail?contractId=1'
```
- run 1 / run 2：`HTTP/2 442`
- 响应体（两次一致）：`{"message":"INVALID TOKEN","code":442,"responseCode":"11990442"}`

## P3 测试环境，不带任何鉴权头

```bash
curl -sS -i -A "$UA" 'https://openapi.qiyuesuo.cn/v2/seal/list'
```
- run 1 / run 2：`HTTP/2 441`
- 响应体（两次一致）：`{"message":"HEADER REQUIRED,x-qys-open-accesstoken","code":441,"responseCode":"11990441"}`

## P4 测试环境，POST JSON 接口，伪造 token

```bash
curl -sS -i -A "$UA" \
  -H "x-qys-open-accesstoken: test" -H "x-qys-open-timestamp: $TS" \
  -H "x-qys-open-nonce: $NONCE" -H "x-qys-open-signature: $SIG" \
  -H 'Content-Type: application/json' -X POST --data '{}' \
  'https://openapi.qiyuesuo.cn/v2/contract/draft'
```
- run 1 / run 2：`HTTP/2 442`
- 响应体（两次一致）：`{"message":"INVALID TOKEN","code":442,"responseCode":"11990442"}`

## P5 测试环境，不存在的路径，伪造 token

```bash
curl -sS -i -A "$UA" \
  -H "x-qys-open-accesstoken: test" -H "x-qys-open-timestamp: $TS" \
  -H "x-qys-open-nonce: $NONCE" -H "x-qys-open-signature: $SIG" \
  'https://openapi.qiyuesuo.cn/v2/not-exist-xyz'
```
- run 1 / run 2：`HTTP/2 442`
- 响应体（两次一致）：`{"message":"INVALID TOKEN","code":442,"responseCode":"11990442"}`
- 结论：token 校验先于路由，不存在的路径也报 INVALID TOKEN，不是 404。

## P6 测试环境，只带三个头（照文档接口页示例，不带 nonce）

```bash
curl -sS -i -A "$UA" \
  -H "x-qys-open-accesstoken: test" -H "x-qys-open-timestamp: $TS" \
  -H "x-qys-open-signature: $SIG" \
  'https://openapi.qiyuesuo.cn/v2/category/list'
```
- run 1 / run 2：`HTTP/2 442`
- 响应体（两次一致）：`{"message":"INVALID TOKEN","code":442,"responseCode":"11990442"}`
- 结论：伪造 token 时，缺 nonce 不会先报错；**无法据此判断 nonce 是否必填**（留给有凭证的验证）。

## P7 测试环境，时间戳比当前早 20 分钟，伪造 token

```bash
OLD=$(( TS - 1200000 ))
SIGO=$(python3 -c "import hashlib,sys;print(hashlib.md5(sys.argv[1].encode()).hexdigest())" "testtest${OLD}${NONCE}x")
curl -sS -i -A "$UA" \
  -H "x-qys-open-accesstoken: test" -H "x-qys-open-timestamp: $OLD" \
  -H "x-qys-open-nonce: ${NONCE}x" -H "x-qys-open-signature: $SIGO" \
  'https://openapi.qiyuesuo.cn/company/token/get'
```
- run 1 / run 2：`HTTP/2 442`
- 响应体（两次一致）：`{"message":"INVALID TOKEN","code":442,"responseCode":"11990442"}`
- 结论：伪造 token 时时间戳过期也不单独报错；时间窗口大小文档未说明，也无法无凭证测出。

## P8 PHP 示例里出现的 `openapi.qiyuesuo.me`

```bash
curl -sS -i -A "$UA" 'https://openapi.qiyuesuo.me/'
```
- run 1 / run 2：`HTTP/2 441`
- 响应体（两次一致）：`{"message":"HEADER REQUIRED,x-qys-open-accesstoken","code":441,"responseCode":"11990441"}`
- 结论：该域名在线，返回与正式 / 测试环境同格式的网关错误；文档没说它是什么环境，skill 里不推荐使用。

---

## 汇总（两次一致，才写进 SKILL.md / site.json）

1. 测试 `openapi.qiyuesuo.cn` 与正式 `openapi.qiyuesuo.com` 都在线，鉴权失败时返回 JSON。
2. 错误响应**同时**有 `code`（整数）与 `responseCode`（8 位字符串），且 HTTP 状态码 = `code`（441、442，非标准状态码）。
   文档里一部分页面只写 `responseCode`，一部分只写 `code`。
3. 缺 `x-qys-open-accesstoken` → 441 `HEADER REQUIRED,x-qys-open-accesstoken` / `11990441`。
4. token 无效 → 442 `INVALID TOKEN` / `11990442`；token 校验先于路由、先于 nonce / 时间戳校验。
5. 这两个错误码（441/442、11990441/11990442）在文档的所有错误码表里都没有出现。
