# TAPD 无凭证探测记录（2026-09-11）

规则：不注册、不登录、不用任何真实凭证；只用明显伪造的值（`-u 'test:test'`、`Bearer faketoken000...`、`workspace_id=1`），不创建任何东西。
脚本：`probe.sh`（P1–P7）、`probe2.sh`（P8–P9）、`probe3.sh`（P10 + 文档链接 D1–D3）、`probe-sdk.sh`（S1–S3，只查注册表元数据）。
每个脚本都跑了两遍（参数 `1`、`2`），原始输出在同目录 `probe-raw-{1,2}.txt`、`probe2-raw-{1,2}.txt`、`probe3-raw-{1,2}.txt`、`probe-sdk-raw-{1,2}.txt`。
脚本对输出做了 IPv4 替换为 `<redacted>`；实际响应里没有出现本机出口 IP。

**说明**：原始输出中每个 https 请求前都有一行 `HTTP/1.1 200 Connection established`，那是本机 HTTPS 代理对 CONNECT 的应答，不是 TAPD 的响应，下表已略去。
TAPD 响应头里的 `Set-Cookie: tapdsession=...`、`X-WAF-UUID`、`P3P`、`Date` 与结论无关，也略去。

## 业务 API 探测（api.tapd.cn）

所有命令都可直接复制运行（UA 头与脚本一致）：

| # | 完整命令 | HTTP 状态行 | 响应片段 | 两次一致 |
|---|---|---|---|---|
| P1 | `curl -sS -D - --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' 'https://api.tapd.cn/tasks?workspace_id=1'` | `HTTP/1.1 401 Unauth` | 头 `WWW-Authenticate: Basic realm='TAPD API'`、`X-RateLimit-Limit: 10000`；body `{"status":401,"data":"","info":"401 Unauthorized","meta":{"request_id":"<32位hex>"}}` | 是 |
| P2 | `curl -sS -D - --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'test:test' 'https://api.tapd.cn/quickstart/testauth'` | `HTTP/1.1 401 Unauth` | 同 P1 | 是 |
| P3 | `curl -sS -D - --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -H 'Authorization: Bearer faketoken0000000000000000000000000000000' 'https://api.tapd.cn/bugs?workspace_id=1'` | **`HTTP/1.1 422 ParamError`** | 无 `WWW-Authenticate`；body `{"status":422,"data":"","info":"The access token provided is invalid","meta":{"request_id":"..."}}` | 是 |
| P4 | `curl -sS -D - --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'test:test' -d 'grant_type=client_credentials' 'https://api.tapd.cn/tokens/request_token'` | `HTTP/1.1 401 Unauth` | 同 P1 | 是 |
| P5 | `curl -sS -D - --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'test:test' 'https://api.tapd.cn/this_path_does_not_exist'` | **`HTTP/1.1 200 OK`** | 头 `Access-Control-Allow-Origin: *`；body `{"status":1,"data":"Hello world from TAPD API. <32位hex>","info":"Documents can be found in https:\/\/www.tapd.cn\/help\/view#1120003271001002318"}`（hex 每次不同） | 是 |
| P6 | `curl -sS -D - --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' 'http://api.tapd.cn/iterations?workspace_id=1'` | `HTTP/1.1 401 Unauth` | **没有 301/302 跳转**，明文 HTTP 直接返回 401 JSON | 是 |
| P7 | `curl -sS -D - --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'test:test' 'https://api.tapd.cn/timesheets?workspace_id=1&__format=xml'` | `HTTP/1.1 401 Unauth` | `Content-Type: application/json`，body 仍是 JSON（错误响应不受 `__format=xml` 影响） | 是 |
| P8 | `curl -sS -D - --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' 'https://api.tapd.cn/storys?workspace_id=1'`（不带凭证，`stories` 拼错） | **`HTTP/1.1 200 OK`** | 同 P5 的 Hello world body | 是 |
| P9 | `curl -sS -D - --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'test:test' 'https://api.tapd.cn/stories/not_a_real_action?workspace_id=1'` | `HTTP/1.1 401 Unauth` | 同 P1（真实资源下的未知子路径先鉴权） | 是 |
| P10 | `curl –u 'test:test' -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -sS --max-time 20 -w '\nHTTP %{http_code}\n' 'https://api.tapd.cn/stories/count?workspace_id=1'`（**第一个参数是 EN DASH `–u`，照抄使用必读页**） | 前两个"URL"：`HTTP 000`；真实 URL：`HTTP 401` | stderr `curl: (6) Could not resolve host: –u`、`curl: (3) URL rejected: Port number was not a decimal number between 0 and 65535`；最后对真实 URL 的请求**不带凭证** → 401 JSON | 是 |

时间：P1–P7 第一轮 18:37:43–18:37:45，第二轮 18:37:45–18:37:47；P8–P9 18:38:50–18:38:51（两轮）；P10 18:39:42 与 18:39:44（CST）。

### 每个 URL 的请求次数（BRIEF 限 ≤3 次）
`/tasks` 2、`/quickstart/testauth` 2、`/bugs` 2、`/tokens/request_token` 2、`/this_path_does_not_exist` 2、`http://…/iterations` 2、
`/timesheets` 2、`/storys` 2、`/stories/not_a_real_action` 2、`/stories/count` 2。合计 20 次，均为只读或伪造凭证，无副作用。

### 响应头观察（所有探测均出现）
- `X-RateLimit-Limit: 10000`，`X-RateLimit-Remaining` 随请求递减（两轮之间曾回到 9998，窗口长度无法从这些数据判断）。
- `X-Powered-By: PHP/7.2.25`。
- 这些值是**未鉴权 / 伪造凭证**状态下的，带真实凭证时的限额未验证。

## 文档链接探测（open.tapd.cn）

| # | 完整命令 | 结果 | 两次一致 |
|---|---|---|---|
| D1 | `curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' 'https://open.tapd.cn/document/api-doc/next/webhook/%E4%BA%8B%E4%BB%B6%E6%98%A0%E5%B0%84.html' \| grep -o '<title>[^<]*'` | HTTP 200，`<title>快速开始 \| 开放平台文档`（VuePress 兜底页，正文不是事件映射） | 是（外加首次勘探共 3 次） |
| D2 | 同上，路径 `.../next/webhook/%E9%85%8D%E7%BD%AEwebhook.html`（配置webhook） | 同 D1 | 是 |
| D3 | 同上，路径 `.../next/api/API%E8%B0%83%E7%94%A8%E8%AF%B4%E6%98%8E%E4%B9%A6/%E6%8E%88%E6%9D%83%E5%87%AD%E8%AF%81/%E5%BA%94%E7%94%A8%E6%80%81.html`（应用态） | 同 D1 | 是 |

对照：真实存在的页面（如 `API文档/使用必读.html`）的 `<title>` 是 `开放平台文档`，正文在 `.theme-default-content` 里；兜底页 41218 字节、标题固定为「快速开始」。
另 `.../next/api/API调用说明书/授权凭证/用户态.html` 首次勘探也是兜底页（只测 1 次，未写进结论）。

本地文件检查（非网络）：`python3 -c "s=open('raw/html/API文档_使用必读.html',encoding='utf-8').read(); print(s.count('curl –u'), s.count('curl -u'))"` → `18 0`；
同样检查 `API文档_API配置指引.html` → `0 1`。

## SDK 包名（公共注册表元数据，未下载任何包）

| # | 完整命令 | 结果 | 两次一致 |
|---|---|---|---|
| S1 | `curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' 'https://registry.npmjs.org/@opentapd%2ftapd-node-sdk'` | HTTP 200，`name=@opentapd/tapd-node-sdk`，`dist-tags.latest=1.68.0`，`time.modified=2026-08-06T08:44:14.407Z` | 是 |
| S2 | `curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' 'https://registry.npmjs.org/@tencent%2ftapd-node-sdk'` | HTTP 404，`{"error":"Not found"}` | 是 |
| S3 | `curl -sS -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' 'https://pypi.org/pypi/tapd-python-sdk/json'` | HTTP 404 | 是 |

## 文档站勘探（抓取前）

| 命令 | 结果 |
|---|---|
| `curl -sS -A '<UA>' -o /dev/null -w '%{http_code} %{content_type}' https://open.tapd.cn/sitemap.xml` | 200 `text/html`——返回的是 Nuxt 首页壳，**不是 XML sitemap** |
| `curl ... https://open.tapd.cn/llms.txt`、`/robots.txt` | 404 |
| `curl ... https://open.tapd.cn/document/sitemap.xml`、`/document/api-doc/sitemap.xml` | 200 `text/html`，VuePress 兜底页 |
| `curl ... https://www.tapd.cn/sitemap.xml` | 200 `text/xml`，营销站页面（lastmod 2018），不含开放平台文档 |

页面清单改从文档站 JS 包 `https://open.tapd.cn/document/assets/js/app.8609d7b8.js` 的 VuePress 路由表提取：`api-doc` 下 388 个 `.html` 页 + 12 个无子页的目录路由 = 400 页，
全部 HTTP 200，转 Markdown 存在 `pages/`，清单见 `index.tsv`（`fetch.sh` 可复现）。另手工抓了 2 个 SDK 说明页（`next-tool-doc/SDK/TAPD SDK/{Python,Node}-SDK.html`）。
