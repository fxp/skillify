# yonyou 无凭证探测日志

规则：不注册、不登录、不用任何真实凭证；只发明显伪造的值（`test`、`id=1`）；不创建任何东西。
时间均为 2026-09-11（UTC+8）。所有命令都可以直接复制到 bash / zsh 里运行，已包含全部请求头（只有 `User-Agent` 和 `Content-Type`）。
响应里没有出现本机出口 IP。

先设一个变量（后面所有命令都用它）：

```bash
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
```

## 目标主机从哪来

| 主机 | 来源 |
| --- | --- |
| `https://apigateway.yonyoucloud.com/open-auth/dataCenter/getGatewayAddress` | 官方 gitee `yycloudopen/corp-demo`、`isv-demo` README：「适配之后需要通过租户来获取（https://apigateway.yonyoucloud.com/open-auth/dataCenter/getGatewayAddress?tenantId=*****）」 |
| `https://api.diwork.com/open-auth/…` | 同上 README：「在进行多数据中心适配之前是 https://api.diwork.com」 |
| `https://c2.yonyoucloud.com/iuap-api-gateway` | API 文档详情 JSON 的 `address` 字段（如 `https://c2.yonyoucloud.com/iuap-api-gateway/yonbip/digitalModel/user/addScopeUser`） |
| `https://c2.yonyoucloud.com/iuap-api-auth` | 按文档示例 `tokenUrl` 形态（`…/iuap-api-auth`）类推；探测显示该服务存在 |

## 记录

| # | 时间 | HTTP | 响应片段 |
| --- | --- | --- | --- |
| P1a | 18:48:17 | 200 | `{"code":"500","message":"根据租户id获取网关地址出现异常"}` |
| P1b | 18:48:17 | 200 | 同上 |
| P3a | 18:48:17 | 200 | `{"code":"310001","message":"access_token不能为空。"}` |
| P3b | 18:48:17 | 200 | 同上 |
| P4a | 18:48:18 | 200 | `{"code":"310036","message":"非法token"}` |
| P4b | 18:48:18 | 200 | 同上 |
| P5a | 18:49:18 | 404 | `{"code":"310404","message":"网关上没有注册此API[/yonbip/skillify/not/exist]，请确认后重新调用"}` |
| P5b | 18:49:18 | 404 | 同上 |
| P2a | 18:49:43 | 200 | `{"code":"10018","message":"应用不存在或appKey已停用"}` |
| P2b | 18:49:44 | 200 | 同上 |
| P2c | 18:49:45 | 200 | 同上 |
| P2d | 18:49:47 | 200 | 同上 |
| P2e | 18:49:48 | 200 | 同上 |
| P2f | 18:49:49 | 200 | 同上 |
| P6a | 18:50:45 | 404 | `{"code":"310404","message":"网关上没有注册此API[/yonsuite/fi/fipub/basedoc/querybd/accperiod]，请确认后重新调用"}` |
| P6b | 18:50:46 | 404 | 同上 |
| P7a | 18:50:46 | 200 | body 纯文本 `非法token` |
| P7b | 18:50:46 | 200 | 同上 |
| P8a | 18:50:46 | 404 | `{"code":"310404","message":"网关上没有注册此API[/yonbip/digitalModel/merchant/newinsert_copy]，请确认后重新调用"}` |
| P8b | 18:50:47 | 404 | 同上 |
| P9a | 18:50:47 | 200 | `{"code":"310036","message":"非法token"}` |
| P9b | 18:50:47 | 200 | 同上 |
| P10a | 18:50:47 | 200 | `{"code":"310036","message":"非法token"}` |
| P10b | 18:50:47 | 200 | 同上 |
| P7c | 18:51:17 | 200 | 响应头 `content-type: text/plain; charset=utf-8`、`content-length: 11`，body `非法token` |

合计 25 次请求。每个接口的次数：getGatewayAddress 2、token base/v1@api.diwork.com 2、token 旧路径@api.diwork.com 2、token base/v1@c2 2、
**vendor/list 4（P3×2 + P4×2，超出「每个接口 ≤3 次」1 次，是我计划失误，之后未再碰该接口）**、未注册路径 2、
`/yonsuite/…/accperiod` 2、`/yonbip/…/accperiod` 3、`newinsert_copy` 2、`idempotent/newinsert` 2、`voucherorder/detail` 2。

另：第一次尝试 P2 时 shell 变量没展开，curl 在本地就报 `URL rejected: No host part in the URL`，**请求没有发出**，已从日志中删除，不计入次数。

## 可复现命令

### P1（a、b 相同）数据中心查询，伪造租户

```bash
curl -sS -A "$UA" 'https://apigateway.yonyoucloud.com/open-auth/dataCenter/getGatewayAddress?tenantId=test'
```

### P2 token 接口，伪造 appKey（签名用伪造 secret `test` 现算）

```bash
read TS SIG < <(python3 -c "
import hmac,hashlib,base64,urllib.parse,time
ts=str(int(time.time()*1000)); s='appKeytesttimestamp'+ts
print(ts, urllib.parse.quote(base64.b64encode(hmac.new(b'test',s.encode(),hashlib.sha256).digest()).decode(),safe=''))")
# P2a / P2b：新路径 @ api.diwork.com
curl -sS -A "$UA" "https://api.diwork.com/open-auth/selfAppAuth/base/v1/getAccessToken?appKey=test&timestamp=$TS&signature=$SIG"
# P2c / P2d：旧路径 @ api.diwork.com
curl -sS -A "$UA" "https://api.diwork.com/open-auth/selfAppAuth/getAccessToken?appKey=test&timestamp=$TS&signature=$SIG"
# P2e / P2f：新路径 @ c2.yonyoucloud.com/iuap-api-auth
curl -sS -A "$UA" "https://c2.yonyoucloud.com/iuap-api-auth/open-auth/selfAppAuth/base/v1/getAccessToken?appKey=test&timestamp=$TS&signature=$SIG"
```

（每次调用前重新执行 `read TS SIG …` 取当前时间戳。日志里实际发出的一次示例：
`…/base/v1/getAccessToken?appKey=test&timestamp=1789123783390&signature=y5DMe%2BUkjSqbPVWsMvGUjfeX6gfCbXnvP0tAU1ZI0jw%3D`。）

### P3 业务接口，不带 access_token

```bash
curl -sS -A "$UA" -X POST -H 'Content-Type: application/json' -d '{"pageIndex":1,"pageSize":10}' \
  'https://c2.yonyoucloud.com/iuap-api-gateway/yonbip/digitalModel/vendor/list'
```

### P4 业务接口，假 token

```bash
curl -sS -A "$UA" -X POST -H 'Content-Type: application/json' -d '{"pageIndex":1,"pageSize":10}' \
  'https://c2.yonyoucloud.com/iuap-api-gateway/yonbip/digitalModel/vendor/list?access_token=test'
```

### P5 未注册路径 + 假 token

```bash
curl -sS -A "$UA" -o /dev/stdout -w '\nHTTP %{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{}' \
  'https://c2.yonyoucloud.com/iuap-api-gateway/yonbip/skillify/not/exist?access_token=test'
```

### P6 文档示例路径 `/yonsuite/…/accperiod` + 假 token

```bash
curl -sS -A "$UA" -w '\nHTTP %{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{}' \
  'https://c2.yonyoucloud.com/iuap-api-gateway/yonsuite/fi/fipub/basedoc/querybd/accperiod?access_token=test'
```

### P7 接口地址 `/yonbip/…/accperiod` + 假 token（P7c 加 `-i` 看响应头）

```bash
curl -sS -A "$UA" -i -X POST -H 'Content-Type: application/json' -d '{}' \
  'https://c2.yonyoucloud.com/iuap-api-gateway/yonbip/fi/fipub/basedoc/querybd/accperiod?access_token=test'
```

### P8 文档示例路径 `merchant/newinsert_copy` + 假 token

```bash
curl -sS -A "$UA" -w '\nHTTP %{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{}' \
  'https://c2.yonyoucloud.com/iuap-api-gateway/yonbip/digitalModel/merchant/newinsert_copy?access_token=test'
```

### P9 接口地址 `merchant/idempotent/newinsert` + 假 token

```bash
curl -sS -A "$UA" -w '\nHTTP %{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{}' \
  'https://c2.yonyoucloud.com/iuap-api-gateway/yonbip/digitalModel/merchant/idempotent/newinsert?access_token=test'
```

### P10 销售订单详情（GET）+ 假 token

```bash
curl -sS -A "$UA" -w '\nHTTP %{http_code}\n' \
  'https://c2.yonyoucloud.com/iuap-api-gateway/yonbip/sd/voucherorder/detail?access_token=test&id=1'
```

## 结论（只陈述观察到的，均复跑 ≥2 次一致）

1. 鉴权失败不走 HTTP 4xx：不带 token → `310001`、假 token → `310036`，HTTP 都是 200，`code` 是 JSON **字符串**。（P3、P4、P9、P10）
2. 网关先校验路径再校验 token：未注册路径带假 token 得到 HTTP 404 + `310404`，不是 `310036`。（P5、P6、P8）
   据此可以无副作用地确认某个路径是否在网关上注册。
3. 文档两处请求示例 URL 在 c2 网关上未注册：`/yonsuite/fi/fipub/basedoc/querybd/accperiod`（P6）、`/yonbip/digitalModel/merchant/newinsert_copy`（P8）；
   对应的接口地址 `/yonbip/fi/fipub/basedoc/querybd/accperiod`（P7）、`/yonbip/digitalModel/merchant/idempotent/newinsert`（P9）已注册。
   → 在 reference 里标了 `<!-- Gap: … -->`。**只证明 c2 这个数据中心的网关如此**，其他数据中心未测。
4. 会计期间查询带假 token 返回 `text/plain` 纯文本 `非法token`，不是文档所说的 `{code,message,data}` JSON（P7 三次）。→ Gap。
5. token 接口：`api.diwork.com` 上新路径 `base/v1` 与 2023-07 前的旧路径都在线，伪造 appKey 都返回 `{"code":"10018","message":"应用不存在或appKey已停用"}`；
   `c2.yonyoucloud.com/iuap-api-auth` 同样。`10018` 不在文档「返回码说明」里。（P2）
6. 数据中心查询在 `apigateway.yonyoucloud.com` 在线，伪造租户返回 `{"code":"500","message":"根据租户id获取网关地址出现异常"}`（HTTP 200，code 为字符串）。（P1）

## 未能探测、留给有凭证的人

见 `verification-plan.md`：签名细节（毫秒 / 秒、二次编码容忍度）、token 放 header 是否可行、各业务接口必填与返回结构、幂等码、事件验签算法。

## 文档抓取（不是探测，列出来便于复现材料来源）

站点是 SPA，文档正文来自下列公开 JSON / HTML（均为 GET、无需登录）：

```bash
B=https://open.yonyoucloud.com/iuap-ipaas-base/openPortal
curl -sS -A "$UA" "$B/cms/classify/getTreeDataWithDocByCode?level=0&code=open_jrwd&containsRoot=1&isAjax=1"   # 接入文档树（236 个页面）
curl -sS -A "$UA" "$B/cms/doc/docInfo/<文档ID>?isAjax=1"                                                    # 单页元数据（url 字段）
curl -sS -A "$UA" "https://open.yonyoucloud.com<url 字段再做一次 percent-encode>?isAjax=1"                   # 页面正文 .md.html
curl -sS -A "$UA" "$B/api/listIntegrateSys?scene=open&isAjax=1"                                             # API 分类树（yonsuite 1305 个节点，ybp 0 个）
curl -sS -A "$UA" "$B/api/groupApiByApiClassify?scene=open&domainAppCode=<分类ID>&treeNodeType=4&integrateSysId=yonsuite&isOrigin=0&isAjax=1"  # 分类下 API 列表
curl -sS -A "$UA" "$B/api/getByVersionForTest/<apiId>/running?scene=open&isOrigin=1&isAjax=1"                # API 详情（参数、示例、错误码）
curl -sS -A "$UA" "$B/event/listEventTree/yonsuite?isAjax=1"                                                # 事件分类树
curl -sS -A "$UA" "$B/event/listEvent/domainApp/<分类ID>?isAjax=1"                                          # 分类下事件列表
curl -sS -A "$UA" "$B/event/eventDetail/<事件ID>?isAjax=1"                                                  # 事件详情（字段、示例）
curl -sS -A "$UA" "$B/cms/doc/listByClassifyCode?code=OpenNotice&all=1&pageIndex=1&pageSize=30&isAjax=1"    # 平台公告列表
```

注意：`docInfo` 返回的 `url` 已经是 percent-encoded 的中文路径，浏览器请求时会**再编码一次**（`%E4` → `%25E4`），直接用原值会 404。
