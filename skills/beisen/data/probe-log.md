# 无凭证探测记录（2026-09-11）

规则：不注册、不登录、不使用任何真实凭证；只用明显伪造的值（`tenant_id=0`、`app_id=0`、`secret=probe-invalid-secret`、
`Authorization: Bearer probe-invalid-token`）。所有请求都是只读或会被鉴权拦下的写接口，不会创建任何数据。

- 探测脚本：`beisen-workspace/probe.sh`（`bash probe.sh <label>`），原始输出：`probe-raw-run1.txt`（18:47:22）、`probe-raw-run2.txt`（18:48:29）。
- **两次运行结果逐条一致**（HTTP 状态码、body 完全相同；只有 TraceID / 时间不同）。
- 每个接口 2 次（run1 + run2），均 ≤3 次。
- 请求经本机 HTTPS 代理发出（原始输出里的 `HTTP/1.1 200 Connection established` 是代理 CONNECT 行，不是北森的响应）。
- 响应中未出现本机出口 IP，无需打码。

## 可直接复制运行的命令

所有命令都带同一个 UA：`-A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'`。

| # | 命令 | HTTP（run1 / run2） | 响应 body（两次一致） | 结论 |
|---|---|---|---|---|
| P1 | `curl -sS -i -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -X POST 'https://openapi.italent.cn/OAuth/Token' -H 'Content-Type: application/x-www-form-urlencoded' --data 'app_id=0&tenant_id=0&secret=probe-invalid-secret&grant_type=client_credentials'` | 400 / 400 | `{"error":"invalid_tenantid"}` | token 接口路径存在；错误体是 OAuth 风格的 `{"error": "..."}`，不是业务接口的 `{code,message}`；响应头 `X-RateLimit-Limit-second: 400`、`X-RateLimit-Remaining-second: 399` |
| P2 | `curl -sS -i -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -X POST 'https://openapi.italent.cn/TenantBaseExternal/api/v5/Employee/GetByTimeWindow' -H 'Content-Type: application/json' --data '{}'` | 400 / 400 | `{"message":"Authorization header is empty"}` | 不带 Authorization 头是 **400** 而不是 401 |
| P3 | `curl -sS -i -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -X POST 'https://openapi.italent.cn/TenantBaseExternal/api/v5/Organization/GetByTimeWindow' -H 'Content-Type: application/json' -H 'Authorization: Bearer probe-invalid-token' --data '{}'` | 401 / 401 | `{"message":"un-authorized"}` | 伪造 Bearer token → 401 |
| P4 | `curl -sS -i -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -X POST 'https://openapi.italent.cn/TenantBaseExternal/api/v5/Employee/GetUserIDByEmail' -H 'Content-Type: application/json' -H 'Authorization: probe-invalid-token' --data '{}'` | 401 / 401 | `{"message":"un-authorized"}` | 不带 `Bearer ` 前缀也是同样的 401 —— 无凭证无法区分「前缀错」和「token 错」 |
| P5 | `curl -sS -i -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -X POST 'http://openapi.italent.cn/TenantBaseExternal/api/v5/Position/GetByTimeWindow' -H 'Content-Type: application/json' -H 'Authorization: Bearer probe-invalid-token' --data '{}'` | 401 / 401 | `{"message":"un-authorized"}` | `http://` 没有被 301 跳转，直接由网关回 401（响应头含 `EagleEye-TraceID`、`Area: BeiJing`）。文档写「所有的请求都为HTTPS协议」，仍应只用 https |
| P6 | `curl -sS -i -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -X GET 'https://openapi.italent.cn/token'` | 404 / 404 | HTML `The resource cannot be found.` | bundle 里「接口文档说明」模板写的请求地址 `https://openapi.italent.cn/token` 不是 token 接口；真正的是 `/OAuth/Token` |
| P7 | `curl -sS -i -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -X POST 'https://openapi.italent.cn/TenantBaseExternal/api/v5/Employee/NoSuchApiForProbe' -H 'Content-Type: application/json' -H 'Authorization: Bearer probe-invalid-token' --data '{}'` | 401 / 401 | `{"message":"un-authorized"}` | **不存在的路径也是 401**：网关先鉴权后路由。所以 P3/P4/P5/P9/P10 的 401 **不能证明**这些路径存在 |
| P8 | `curl -sS -i -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -X POST 'https://openapi.italent.cn/tenantbase/v1/0/employee/seviceinfo/email/search' -H 'Content-Type: application/json' -H 'Authorization: Bearer probe-invalid-token' --data '{}'` | 500 / 500 | 空 body；状态行 `HTTP/1.1 500 Falied to verify your credentials`；响应头 `X-Gray: Black` | v2.0 旧版路径（`/{tenantId}/` 风格）走的是另一套网关逻辑：伪造 token 返回 500 而不是 401 |
| P9 | `curl -sS -i -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -X POST 'https://openapi.italent.cn/AttendanceOpen/api/v1/Vacation/GetListByDate' -H 'Content-Type: application/json' -H 'Authorization: Bearer probe-invalid-token' --data '{}'` | 401 / 401 | `{"message":"un-authorized"}` | 假勤 v3.0 接口同样的鉴权错误格式 |
| P10 | `curl -sS -i -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -X POST 'https://openapi.italent.cn/RecruitV6/api/v1/Apply/GetApplyListByModifiedTime' -H 'Content-Type: application/json' -H 'Authorization: Bearer probe-invalid-token' --data '{}'` | 401 / 401 | `{"message":"un-authorized"}` | 招聘 v3.0 接口同样的鉴权错误格式 |

## 可以写进 skill 的结论（两次一致）

1. token 接口：`POST https://openapi.italent.cn/OAuth/Token`（form 编码）存在；伪造 tenant_id 得到 HTTP 400 + `{"error":"invalid_tenantid"}`。
2. 业务接口鉴权失败有两种形态：缺 Authorization 头 → **400** `{"message":"Authorization header is empty"}`；token 无效 → **401** `{"message":"un-authorized"}`。
   两者都不是文档里业务接口的 `{"code": "...", "message": ...}` 结构，错误处理不能只解析 `code`。
3. 401 发生在路由之前：对不存在的路径也返回 401，所以无凭证探测**无法**确认任何业务路径是否存在。
4. v2.0 旧版路径（`/tenantbase/v1/{tenantId}/...`）伪造 token 返回 HTTP 500（reason phrase `Falied to verify your credentials`），空 body。
5. `https://openapi.italent.cn/token` 是 404，不是 token 接口。

## 做不到 / 没有做的

- 带 `Bearer` 前缀与不带前缀对真实 token 是否都能用：无凭证无法区分（P3 与 P4 同为 401）。
- token 接口的 JSON body 是否被接受、缺 `app_id` 时的行为、`expires_in` 的真实类型与数值：需要真实凭证。
- 受信 IP（403）和限频（429）的真实响应体：无凭证触发不了。
- 任何业务路径是否真实存在（见结论 3）。

## 文档站抓取（不是 API 探测，列在这里便于复现）

文档内容全部来自开放平台前端自己调用的匿名 GET 接口（`https://open.italent.cn/api/...`）和社区文档匿名接口：

```bash
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
curl -sS -A "$UA" 'https://open.italent.cn/api/OpenDocumentMenu/GetLevel1Menus'                       # 新版 v3.0 一级应用列表
curl -sS -A "$UA" 'https://open.italent.cn/api/OpenDocumentMenu/GetMenusByAppId?open_system_application_id=b3909a33-ebf4-4f8a-b5bb-f613988a0aef'   # 组织员工目录
curl -sS -A "$UA" 'https://open.italent.cn/api/OpenDocumentMenu/GetMenusByfolderId?open_system_application_id=b3909a33-ebf4-4f8a-b5bb-f613988a0aef&folderId=fb9276b5-ce4d-484d-8150-9910d652505e'  # 组织单元文件夹
curl -sS -A "$UA" 'https://open.italent.cn/api/OpenDocument/Get?id=d2405033-0bb3-4574-ad82-b959799e8882&platform=1'   # 单个接口文档（员工时间窗）
curl -sS -A "$UA" 'https://open.italent.cn/api/V20DocumentMenu/GetLevel1Menus'                        # 旧版 v2.0
curl -sS -A "$UA" 'https://open.italent.cn/api/ErrorCode/Search?page=1&perpageCount=30'              # 错误码表（perpageCount 最大 30，共 276 条）
curl -sS -A "$UA" 'https://users.italent.cn/AnnoyDocument/GetHelpDocument?pageId=80117962'           # 社区文档（匿名）
curl -sS -A "$UA" 'https://users.italent.cn/Document/GetHelpDocument?pageId=80117962'                # 同一篇走登录版接口 → {"Code":403,...Login...}
```

脚本：`crawl_menus.py`（目录树 → `index-menus.tsv`）、`fetch_docs.py`（896 篇接口文档 → `raw/docs/`）、`render_docs.py`（→ `pages/open|v2.0/...md`）、
`fetch_guides.py`（社区文档 → `pages/guide-*.md`）、`extract_guide.py`（bundle 里的开发指南）。
