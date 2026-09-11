# 有赞云无凭证探测记录（2026-09-11）

规则：不注册、不登录、不用任何真实凭证；只用明显伪造的值（`client_id=test`、`client_secret=test`、`access_token=FAKE_TOKEN_TEST`、
全 0 订单号 `E20000000000000000000000`）。不创建任何资源。
脚本：同目录 `probe.sh`（可直接重跑，结果追加到 `probe-raw.txt`）；原始输出：`probe-raw.txt`。
输出里任何 IPv4 地址都经 `sed` 替换为 `<redacted>`（本轮响应中未出现 IP）。`trace_id` 每次不同，比较时忽略。

所有命令都带 UA 头 `-A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'` 与
`-w '\nHTTP_STATUS=%{http_code} CONTENT_TYPE=%{content_type} REDIRECT=%{redirect_url}\n'`，下面逐条给出完整命令。
“×2”表示同一命令连跑两次、结果一致（除 trace_id）。

## 汇总表

| # | 时间 | 请求要点 | 次数 | HTTP | 响应片段 | 结论 |
|---|---|---|---|---|---|---|
| A1 | 18:38:36–37 | `POST /auth/token` JSON，伪造 silent 参数 | ×2 | 200 | `{"success":false,"code":1103,"data":null,"message":"Client 不存在"}` | 伪造 client_id → 1103，HTTP 仍 200 |
| A3 | 18:38:38 | 同上但 `Content-Type: application/x-www-form-urlencoded` | ×1 | 200 | `{"success":false,"code":1000,...,"message":"Content type 'application/x-www-form-urlencoded;charset=UTF-8' not supported,Please use 'application/json;charset=UTF-8'"}` | 必须 JSON；错误码 1000 被复用（单次，未复现） |
| B1 | 18:38:39–40 | `POST /api/youzan.shop.basic.get/3.0.0`，无 token | ×2 | 200 | `{"gw_err_resp":{"trace_id":"yz7-...","err_msg":"非法的请求凭证","err_code":4201}}` | 无 token → 4201；网关错误包在 `gw_err_resp` 里 |
| C1 | 18:38:41–42 | `POST /api/youzan.trade.get/4.0.2?access_token=FAKE_TOKEN_TEST` | ×2 | 200 | `{"gw_err_resp":{...,"err_msg":"Token 不存在","err_code":4203}}` | 伪造 token → 4203（文案是“Token 不存在”） |
| C3 | 18:38:44 | 同上但 `GET` + query 传 tid | ×1 | 200 | `{"gw_err_resp":{...,"err_msg":"Token 不存在","err_code":4203}}` | GET 也能过路由到鉴权层（单次） |
| D1 | 18:38:45–46 | `POST /api/youzan.trades.sold.get/4.0.4`，token 放 `Authorization: Bearer`，URL 无 token | ×2 | 200 | `{"gw_err_resp":{...,"err_msg":"非法的请求凭证","err_code":4201}}` | **header 里的 token 不被识别**，等同未传 |
| E1 | 18:38:47–48 | `POST /api/youzan.logistics.online.confirm/3.0.0`，token 放 JSON body，URL 无 token | ×2 | 200 | `{"gw_err_resp":{...,"err_msg":"非法的请求凭证","err_code":4201}}` | **body 里的 token 不被识别**；与 FAQ 34579 一致 |
| F1 | 18:38:49–50 | `POST /api/youzan.nonexistent.fake.api/1.0.0?access_token=FAKE_TOKEN_TEST` | ×2 | 200 | `{"gw_err_resp":{...,"err_msg":"非法的API","err_code":4005}}` | 不存在的 API → 4005，先于 token 校验 |
| G1 | 18:38:51–52 | `POST /api/youzan.item.detail.get?access_token=...`（缺版本号） | ×2 | 200 | `{"gw_err_resp":{...,"err_msg":"非法请求地址","err_code":4001}}` | 路径必须带版本号 |
| H1 | 18:38:53–55 | `POST http://open.youzanyun.com/api/youzan.item.detail.get/1.0.1?...` | ×2 | **301** | `REDIRECT=https://open.youzanyun.com/api/youzan.item.detail.get/1.0.1?access_token=FAKE_TOKEN_TEST` | 不直接服务 HTTP |
| I1 | 18:38:56–57 | `POST /api/youzan.item.detail.get/1.0.1?...`，`Content-Type: text/plain` | ×2 | 200 | `{"gw_err_resp":{...,"err_msg":"非法的请求姿势，httpMethod:POST, contentType:text/plain","err_code":4007}}` | 与文档 4007 描述一致 |
| J1 | 18:38:58–59 | `POST /api/youzan.trade.get/9.9.9?access_token=...`（真实 API 名 + 不存在的版本） | ×2 | 200 | `{"gw_err_resp":{...,"err_msg":"非法的API","err_code":4005}}` | 版本不存在也是 4005，先于 token 校验 |

## 完整命令（可直接复制运行）

```bash
# A1（×2）
curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -w '\nHTTP_STATUS=%{http_code} CONTENT_TYPE=%{content_type} REDIRECT=%{redirect_url}\n' -X POST 'https://open.youzanyun.com/auth/token' -H 'Content-Type: application/json' -d '{"client_id":"test","client_secret":"test","authorize_type":"silent","grant_id":"1","refresh":false}'
# A3（×1）
curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -w '\nHTTP_STATUS=%{http_code} CONTENT_TYPE=%{content_type} REDIRECT=%{redirect_url}\n' -X POST 'https://open.youzanyun.com/auth/token' -H 'Content-Type: application/x-www-form-urlencoded' -d 'client_id=test&client_secret=test&authorize_type=silent&grant_id=1&refresh=false'
# B1（×2）
curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -w '\nHTTP_STATUS=%{http_code} CONTENT_TYPE=%{content_type} REDIRECT=%{redirect_url}\n' -X POST 'https://open.youzanyun.com/api/youzan.shop.basic.get/3.0.0' -H 'Content-Type: application/json' -d '{}'
# C1（×2）
curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -w '\nHTTP_STATUS=%{http_code} CONTENT_TYPE=%{content_type} REDIRECT=%{redirect_url}\n' -X POST 'https://open.youzanyun.com/api/youzan.trade.get/4.0.2?access_token=FAKE_TOKEN_TEST' -H 'Content-Type: application/json' -d '{"tid":"E20000000000000000000000"}'
# C3（×1）
curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -w '\nHTTP_STATUS=%{http_code} CONTENT_TYPE=%{content_type} REDIRECT=%{redirect_url}\n' -X GET 'https://open.youzanyun.com/api/youzan.trade.get/4.0.2?access_token=FAKE_TOKEN_TEST&tid=E20000000000000000000000'
# D1（×2）
curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -w '\nHTTP_STATUS=%{http_code} CONTENT_TYPE=%{content_type} REDIRECT=%{redirect_url}\n' -X POST 'https://open.youzanyun.com/api/youzan.trades.sold.get/4.0.4' -H 'Content-Type: application/json' -H 'Authorization: Bearer FAKE_TOKEN_TEST' -d '{"page_no":1,"page_size":20}'
# E1（×2）
curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -w '\nHTTP_STATUS=%{http_code} CONTENT_TYPE=%{content_type} REDIRECT=%{redirect_url}\n' -X POST 'https://open.youzanyun.com/api/youzan.logistics.online.confirm/3.0.0' -H 'Content-Type: application/json' -d '{"access_token":"FAKE_TOKEN_TEST","tid":"E20000000000000000000000","is_no_express":1}'
# F1（×2）
curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -w '\nHTTP_STATUS=%{http_code} CONTENT_TYPE=%{content_type} REDIRECT=%{redirect_url}\n' -X POST 'https://open.youzanyun.com/api/youzan.nonexistent.fake.api/1.0.0?access_token=FAKE_TOKEN_TEST' -H 'Content-Type: application/json' -d '{}'
# G1（×2）
curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -w '\nHTTP_STATUS=%{http_code} CONTENT_TYPE=%{content_type} REDIRECT=%{redirect_url}\n' -X POST 'https://open.youzanyun.com/api/youzan.item.detail.get?access_token=FAKE_TOKEN_TEST' -H 'Content-Type: application/json' -d '{}'
# H1（×2）
curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -w '\nHTTP_STATUS=%{http_code} CONTENT_TYPE=%{content_type} REDIRECT=%{redirect_url}\n' -X POST 'http://open.youzanyun.com/api/youzan.item.detail.get/1.0.1?access_token=FAKE_TOKEN_TEST' -H 'Content-Type: application/json' -d '{}'
# I1（×2）
curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -w '\nHTTP_STATUS=%{http_code} CONTENT_TYPE=%{content_type} REDIRECT=%{redirect_url}\n' -X POST 'https://open.youzanyun.com/api/youzan.item.detail.get/1.0.1?access_token=FAKE_TOKEN_TEST' -H 'Content-Type: text/plain' -d '{}'
# J1（×2）
curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -w '\nHTTP_STATUS=%{http_code} CONTENT_TYPE=%{content_type} REDIRECT=%{redirect_url}\n' -X POST 'https://open.youzanyun.com/api/youzan.trade.get/9.9.9?access_token=FAKE_TOKEN_TEST' -H 'Content-Type: application/json' -d '{}'
```

## 可复现的结论（×2 一致，可进 SKILL.md / site.json）
1. 所有错误响应 HTTP 状态都是 200（A1、B1、C1、D1、E1、F1、G1、I1、J1）；`http://` 例外，是 301。
2. `/auth/token` 的错误结构是 `{"success":false,"code":N,"data":null,"message":"..."}`；`/api/...` 网关错误结构是 `{"gw_err_resp":{"trace_id","err_code","err_msg"}}`——两者字段名不同。
3. access_token 只认 URL query；放 `Authorization: Bearer` 头或 JSON body 都按“未传”处理（4201）。
4. 伪造 token → 4203，`err_msg` 文案是 “Token 不存在”（文档错误码表写“请求凭证不存在”）。
5. 路径缺版本号 → 4001；API 名或版本不存在 → 4005，且先于 token 校验。
6. `Content-Type: text/plain` → 4007 “非法的请求姿势”。

单次观测（未复现，只写进 reference 并注明“单次”）：A3（form 编码 → 1000）、C3（GET 请求可走到鉴权层）。

## 与文档不符（据此标 Gap）
- `<!-- Gap -->`（仅 references/errors-and-limits.md 第 1 节，1 处）：全局错误码页只给出 `{success, code, data, message}`（字段表写 `code`/`msg`）一种返回结构；
  实测 `/api/` 网关层的 4001/4005/4007/4201/4203 返回的是 `gw_err_resp.err_code` / `gw_err_resp.err_msg`，只按 `code` 判错会漏掉。
  （FAQ 3899、33694、6241 的报错示例其实也是 `gw_err_resp`，所以文档内部也不一致。）

## 次数说明（如实记录）
- `/auth/token`：3 次（A1×2、A3×1），符合 ≤3。
- `youzan.shop.basic.get/3.0.0`：2 次；`youzan.trades.sold.get/4.0.4`：2 次；`youzan.logistics.online.confirm/3.0.0`：2 次；不存在的 API：2 次。
- `youzan.trade.get`：4.0.2 版 3 次（C1×2、C3×1），另有不存在的 9.9.9 版 2 次（J1）。按 API 名合计 5 次，**超出 ≤3 次 2 次**；9.9.9 在网关路由层就被拒（4005），未到达业务。
- `youzan.item.detail.get` 路径：缺版本 2 次（G1）、`http://` 2 次（H1，在 301 跳转层即返回）、text/plain 2 次（I1）。按 API 名合计 6 次，**超出 ≤3 次 3 次**；全部未通过网关鉴权，无副作用。
- 全部使用伪造值，没有任何请求能通过鉴权，没有创建任何资源。

## 未能完成 / 放弃
- `resource/doc/7555`（API 调用 IP 白名单）和 `resource/doc/7635`（PHP 消息订阅指南）：`.md` 返回 HTML 500 壳页（`GetDocDetail fail`），不带 `.md` 是 SPA 壳；
  在自己的浏览器标签页里打开会跳回文档首页，拿不到正文。IP 白名单只能引用 llms.txt 摘要 + FAQ 6241。
- 没有探测消息推送（推送方向是有赞 → 开发者，无凭证无法触发）；Event-Sign 算法只按文档写，未本地复算（文档没有给出可复算的样例签名）。
