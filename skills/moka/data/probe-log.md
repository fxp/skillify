# Moka 无凭证探测记录（2026-09-11）

规则：不注册、不登录、不用任何真实凭证，不提交表单；只用明显伪造的值（`fake_probe_key`、`fake_probe_token`、`clientID=test`、`entCode=fakeent`、`sign=fakesign`、`jobId=probe`、`orgId=probe_fake_org`）。
所有请求都不会创建任何东西（伪造 Key 在鉴权层就被拒；少数 POST 写接口只为确认路由是否存在）。每个接口 ≤ 3 次。

**复跑方法**：下面每条命令都是完整命令（含全部请求头），可直接复制运行；也可用 `python3 probe.py probes-ats.txt <raw>` 批量复跑
（`probes-ats.txt` / `probes-people.txt` / `probes-ats-2.txt` / `probes-ats-3.txt` 里是同样的命令）。原始输出：`probe-raw-ats.txt`、`probe-raw-people.txt`、`probe-raw-ats-2.txt`、`probe-raw-ats-3.txt`。

**环境说明**：本机出网经过 HTTPS 代理，原始输出第一段是代理的 `HTTP/1.1 200 Connection established`，不是 Moka 的响应；`probe.py` 解析时已跳过。
响应中未出现本机 IP；`probe.py` 仍对输出里的 IPv4 做了 `<redacted>` 替换。

共 50 次请求（ATS 42 次、People 8 次）。凡写进 SKILL.md「当前事实」、site.json `probed` 或标 `<!-- Gap -->` 的结论，都来自下面**复跑两次结果一致**的条目。

UA 统一为 `-A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'`，下文命令里写全。

---

## A 组：ATS 鉴权、域名与路由（probes-ats.txt）

### A1 不带任何鉴权
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' 'https://api.mokahr.com/api-platform/v1/archiveReasons'
```
- run1 18:44:08 · run2 18:44:08 → `HTTP/1.1 500 Internal Server Error` · `{"code":-1,"success":false,"msg":"无法识别的认证信息"}`
- 结论：ATS 缺鉴权返回 **HTTP 500**（不是 401），body `code:-1`。

### A2 伪造 Basic Key
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' 'https://api.mokahr.com/api-platform/v1/departments'
```
- run1 18:44:09 · run2 18:44:09 → `HTTP/1.1 500` · `{"code":-1,"success":false,"msg":"无法识别的认证信息"}`
- 结论：伪造 Key 与不带鉴权表现相同。

### A3 伪造 Bearer
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -H 'Authorization: Bearer fake_probe_token' 'https://api.mokahr.com/api-platform/v1/locations'
```
- run1 18:44:09 · run2 18:44:09 → `HTTP/1.1 500` · `{"code":-1,"success":false,"msg":"无法识别的认证信息"}`
- 结论：与伪造 Basic 相同，无法判断该接口是否接受 Bearer。

### A4 OAuth2 换 token（伪造 clientID）
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -X POST -H 'Content-Type: application/json' -d '{"clientID":"test","clientSecret":"test","grantType":"client_credentials"}' 'https://api.mokahr.com/api-platform/v1/auth/oauth2/getToken'
```
- run1 18:44:10 · run2 18:44:10 → `HTTP/1.1 200 OK` · `{"code":110020,"msg":"unauthorized_client","data":{}}`
- 结论：与文档错误码一致；**失败时 HTTP 仍为 200**。

### A5 OAuth2 字段名改小写 `clientId`（1 次，getToken 共 3 次）
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -X POST -H 'Content-Type: application/json' -d '{"clientId":"test","clientSecret":"test","grantType":"client_credentials"}' 'https://api.mokahr.com/api-platform/v1/auth/oauth2/getToken'
```
- run1 18:44:10 → `HTTP/1.1 200 OK` · `{"code":110020,"msg":"unauthorized_client","data":{}}`
- 结论：与 A4 相同，**无法区分**字段名大小写是否敏感（单次，不作为事实）。

### A6 不存在的路径
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' 'https://api.mokahr.com/api-platform/v1/this_path_does_not_exist'
```
- run1 18:44:10 · run2 18:44:10 → `HTTP/1.1 404 Not Found` · `{"message":"您访问的页面不存在"}`
- 结论：**ATS 路由在鉴权之前**：404 = 路径不存在；500 + 鉴权错误 = 路径存在。B 组据此确认文档路径。

### A7 用 http://
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' 'http://api.mokahr.com/api-platform/v1/job_priority'
```
- run1 18:44:10 · run2 18:44:11 → `HTTP/1.1 500` · `{"code":-1,"success":false,"msg":"无法识别的认证信息"}`（无 `Location`，未跳转）
- 结论：http 不会被 301 到 https，请求（含凭据）以明文到达服务端。文档要求 HTTPS，但部分示例写 http://。

### A8 国际版域名
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' 'https://hire-r1-api.mokahr.com/api-platform/v1/archiveReasons'
```
- run1 18:44:11 · run2 18:44:14 → `HTTP/2 500` · `{"code":-1,"success":false,"msg":"无法识别的认证信息"}`
- 结论：国际版域名在线，鉴权失败格式与中国版一致。

### A9 ATS 测试环境域名
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' 'https://api-staging-3.mokahr.com/api-platform/v1/archiveReasons'
```
- run1 18:44:15 · run2 18:44:17 → `HTTP/1.1 500` · `{"code":-1,"success":false,"msg":"无法识别的认证信息"}`
- 结论：测试域名在线，格式一致。

### A10 `/open-api` 网关（V3 用户列表）
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' -X POST -H 'Content-Type: application/json' -d '{"limit":1}' 'https://api.mokahr.com/open-api/ats/v3/users/list'
```
- run1 18:44:17 · run2 18:44:17 → `HTTP/1.1 401 Unauthorized` · `{"code":-1,"msg":"无法识别的认证信息","subCode":"Unauthorized"}`（响应头带 `x-open-api-request-id`）
- 结论：`/open-api/ats/v3` 是另一套网关，鉴权失败为 401 且多 `subCode`。

### A11 申请增量拉取接口
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' 'https://api.mokahr.com/api-platform/v1/data/applications?limit=1'
```
- run1 18:44:17 · run2 18:44:17 → `HTTP/1.1 500` · `{"code":-1,"success":false,"msg":"无法识别的认证信息"}`
- 结论：路径存在。

---

## P 组：Moka People（probes-people.txt）

### P1 不带鉴权
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -X POST -H 'Content-Type: application/json' -d '{"pageSize":1,"pageNum":1}' 'https://api.mokahr.com/api-platform/hcm/oapi/v1/batch/data'
```
- run1 18:45:17 · run2 18:45:17 → `HTTP/1.1 403 Forbidden` · `{"success":false,"msg":"无法识别的认证信息"}`

### P2 伪造 Key + 伪造签名参数（1 次，batch/data 共 3 次）
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' -X POST -H 'Content-Type: application/json' -d '{"pageSize":1,"pageNum":1}' "https://api.mokahr.com/api-platform/hcm/oapi/v1/batch/data?userName=probe@example.com&entCode=fakeent&apiCode=fakeapi&nonce=ab12cd34&timestamp=$(date +%s)000&sign=fakesign"
```
- run1 18:45:17 → `HTTP/1.1 403 Forbidden` · `{"success":false,"msg":"无法识别的认证信息"}`

### P3 伪造 Key、不带签名参数（部门接口）
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' -X POST -H 'Content-Type: application/json' -d '{"pageSize":1,"pageNum":1}' 'https://api.mokahr.com/api-platform/hcm/oapi/v1/org/department/batchData'
```
- run1 18:45:17 · run2 18:45:17 → `HTTP/1.1 403 Forbidden` · `{"success":false,"msg":"无法识别的认证信息"}`

### P4 用 GET 调 POST 接口（1 次，部门接口共 3 次）
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' 'https://api.mokahr.com/api-platform/hcm/oapi/v1/org/department/batchData'
```
- run1 18:45:17 → `HTTP/1.1 403 Forbidden` · 同上（未走到文档写的 405 方法错误）

### P5 不存在的路径
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' -X POST -H 'Content-Type: application/json' -d '{}' 'https://api.mokahr.com/api-platform/hcm/oapi/v1/this_path_does_not_exist'
```
- run1 18:45:18 · run2 18:45:18 → `HTTP/1.1 403 Forbidden` · `{"success":false,"msg":"无法识别的认证信息"}`

**P 组结论**（P1、P3、P5 各复跑两次一致）：People 对一切未授权请求返回 **HTTP 403** `{"success":false,"msg":"无法识别的认证信息"}`，body **没有 `code` 字段**，且先鉴权后路由。
文档「全局错误码」写的是 HTTP 401 / 错误码 100001（「没有进入系统权限，请检查授权码是否准确」）→ 在 `references/auth.md` 标 `<!-- Gap -->`。

---

## B 组：ATS 文档路径存在性（probes-ats-2.txt）

依据 A6：带伪造 Key 时 404 = 路径不存在，500 + 鉴权错误 = 路径存在。

| # | 完整命令 | run1 / run2 | 结果（两次一致） | 结论 |
| :--- | :--- | :--- | :--- | :--- |
| B1 | `curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' -X POST -H 'Content-Type: application/json' -d '{"applicationIds":[1]}' 'https://api.mokahr.com/api-platform/v3/data/getApplictaions'` | 18:47:40 / 18:47:40 | 500 `{"code":-1,"success":false,"msg":"系统中不存在该apiKey"}` | 文档拼写 `getApplictaions` 的路由存在 |
| B2 | `curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' -X POST -H 'Content-Type: application/json' -d '{"applicationIds":[1]}' 'https://api.mokahr.com/api-platform/v3/data/getApplications'` | 18:47:40 / 18:47:41 | **404** `{"message":"您访问的页面不存在"}` | 拼写"正确"的 `getApplications` 不存在 |
| B3 | `curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' -X POST -H 'Content-Type: application/json' -d '{}' 'https://api.mokahr.com/api-platform/v1/public/switchStatus'` | 18:47:41 / 18:47:41 | 500 `系统中不存在该apiKey` | 路径存在（文档写成 `hhttps://…` 是笔误） |
| B4 | `curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' -X POST -H 'Content-Type: application/json' -d '{"departments":[]}' 'https://api.mokahr.com/api-platform/v2/departments/sync/incremental'` | 18:47:41 / 18:47:41 | 500 `无法识别的认证信息` | 路径存在 |
| B5 | `curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' -X POST -H 'Content-Type: application/json' -d '{}' 'https://api.mokahr.com/api-platform/v3/applications/list_by_condition'` | 18:47:41 / 18:47:41 | 500 `系统中不存在该apiKey` | 路径存在 |
| B6 | `curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' -X POST -H 'Content-Type: application/json' -d '{"hireMode":"social"}' 'https://api.mokahr.com/api-platform/v1/jobs/getJobs'` | 18:47:41 / 18:47:41 | 500 `系统中不存在该apiKey` | 路径存在 |
| B7 | `curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' 'https://api.mokahr.com/api-platform/v1/jobs/getJobs'`（1 次） | 18:47:42 | 403 `{"message":"招聘模式 必填","msg":"招聘模式 必填","code":3}` | GET 命中的是官网路由 `GET /v1/jobs/{orgId}`（orgId=`getJobs`），见 C1 |
| B8 | `curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' -X POST 'https://api.mokahr.com/api-platform/v3/candidate/uploadResume'` | 18:47:42 / 18:47:42 | 500 `无法识别的认证信息` | 路径存在 |
| B9 | `curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' -X POST -H 'Content-Type: application/json' -d '{}' 'https://api.mokahr.com/api-platform/v1/create-offer'` | 18:47:42 / 18:47:42 | 500 `无法识别的认证信息` | 路径存在 |
| B10 | `curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' -u 'fake_probe_key:' 'https://api.mokahr.com/api-platform/v1/data/job_stages?jobId=probe'` | 18:47:42 / 18:47:43 | 500 `无法识别的认证信息` | 路径存在 |

附带发现：ATS 的伪造 Key 错误文案有两种——`无法识别的认证信息`（v1 / v2 多数接口）与 `系统中不存在该apiKey`（v3 查询、getJobs、switchStatus），HTTP 都是 500。

---

## C 组：招聘官网职位列表是否需要鉴权（probes-ats-3.txt）

### C1 不带任何鉴权头，伪造 orgId，不带 `mode`
```bash
curl -s -i --max-time 20 -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' 'https://api.mokahr.com/api-platform/v1/jobs/probe_fake_org'
```
- run1 18:50:27 · run2 18:50:27 → `HTTP/1.1 403 Forbidden` · `{"message":"招聘模式 必填","msg":"招聘模式 必填","code":3}`
- 结论：该路由（`GET /v1/jobs/{orgId}`，含 B7 共 3 次）不带 API Key 也走到了参数校验，返回的是参数错误而非鉴权错误；与文档示例不带 `-u` 一致。
  **未证实**不带 Key 能否拿到数据（没有真实 orgId，也未补 `mode` 再调，以免超过每接口 3 次）。

---

## 本地复算（非网络请求，脚本在 `local-checks/`）

| 脚本 | 做了什么 | 结果（复跑两次一致） |
| :--- | :--- | :--- |
| `hmac_check.py` | 用 ATS 文档 webhook 示例（body `{name:'test',email:'test@mokahr.com'}`、key `qwer`）重算 HMAC-SHA256 | 紧凑 JSON → `7d6981cc…dd2a32d`，**与文档一致**；Python 默认 `json.dumps`（带空格）→ `7c94db41…f08b105`，不一致 |
| `aes_check.js`（Node v26） | 用文档的 `dataEncrypt` 加密，再用文档的 `dataDecrypt` 解密；另写一个 hex→utf8 的正确版本 | 文档解密函数抛 `ERR_OSSL_BAD_DECRYPT`；正确版本还原原文 → 文档示例代码编码写反 |
| `aes_py_check.py` | 用 `references/webhooks.md` 的 Python 解密函数解 Node 加密出的 hex | 还原 `{"applicationId":1,"name":"测试"}` |
| `people_sign_check.py` | 用 People 文档 Java 示例里的测试 RSA 密钥对，跑 `references/auth.md` 的 `people_sign()` | 排序串与文档示例一致；签名与 `openssl dgst -md5 -sign` **逐字节相同**；文档公钥验签通过 |

运行：`cd moka-workspace/local-checks && python3 hmac_check.py && node aes_check.js && python3 aes_py_check.py && python3 people_sign_check.py`
（需要本机已有的 `cryptography` 与 `openssl`；未安装任何新包。）

## 未能完成 / 未尝试

- 石墨文档《Moka ATS 标准交付集成开发方案》（`shimo.im/docs/RosVRgWWM7ILGTvV`）与《Moka People 用户帮助中心》（`mokapeople.moyincloud.com`）未抓取（外部站点，可能需登录）。
- ATS 文档里的「系统内置字段code映射表.xlsx」（OSS 链接）按规矩未下载。
- People 无法用无凭证探测区分路径（先鉴权后路由）。
