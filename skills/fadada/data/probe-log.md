# 法大大 FASC 5.1 无凭证探测日志

全部请求均为伪造 AppId（`test`）或无鉴权头，不含任何真实凭证或个人信息；每个接口 ≤3 次。

## P1 UAT 换 token（伪造 AppId）
- 时间：2026-09-11 17:58:10 +0800
- 请求：`POST https://uat-api.fadada.com/api/v5/service/get-access-token` （header：X-FASC-App-Id=test、X-FASC-Sign-Type=HMAC-SHA256、X-FASC-Sign=伪造 64 位 hex、X-FASC-Timestamp=当前毫秒、X-FASC-Nonce=随机 32 位、X-FASC-Grant-Type=client_credential、X-FASC-Api-SubVersion=5.1；无 body）
- HTTP：200
- 响应头：content-type: application/json;charset=UTF-8 x-content-type-options: nosniff 
- 响应体：`{"msg":"未获取有效的平台信息","code":"100001","data":null,"success":false}`

## P2 生产 换 token（伪造 AppId）
- 时间：2026-09-11 17:58:11 +0800
- 请求：`POST https://api.fadada.com/api/v5/service/get-access-token` （header：X-FASC-App-Id=test、X-FASC-Sign-Type=HMAC-SHA256、X-FASC-Sign=伪造 64 位 hex、X-FASC-Timestamp=当前毫秒、X-FASC-Nonce=随机 32 位、X-FASC-Grant-Type=client_credential、X-FASC-Api-SubVersion=5.1；无 body）
- HTTP：200
- 响应头：content-type: application/json;charset=UTF-8 x-content-type-options: nosniff 
- 响应体：`{"msg":"未获取有效的平台信息","code":"100001","data":null,"success":false}`

## P3 UAT 业务接口无鉴权头
- 时间：2026-09-11 17:58:11 +0800
- 请求：`POST https://uat-api.fadada.com/api/v5/sign-task/create` （不带任何 X-FASC-* 头，body：bizContent={}）
- HTTP：200
- 响应头：content-type: application/json;charset=UTF-8 x-content-type-options: nosniff 
- 响应体：`{"msg":"X-FASC-App-Id 不能为空","code":"100012","data":null,"success":false}`

## P4 UAT 换 token 用 GET
- 时间：2026-09-11 17:59:45 +0800
- 请求：`GET https://uat-api.fadada.com/api/v5/service/get-access-token` （同 P1 的伪造 header，改用 GET）
- HTTP：200
- 响应头：content-type: application/json;charset=UTF-8 x-content-type-options: nosniff 
- 响应体：`{"msg":"未获取有效的平台信息","code":"100001","data":null,"success":false}`

## P5 UAT 不存在的路径
- 时间：2026-09-11 17:59:45 +0800
- 请求：`POST https://uat-api.fadada.com/api/v5/sign-task/not-exist-xyz` （伪造 header + X-FASC-AccessToken=fake，body bizContent={}）
- HTTP：401
- 响应头：content-type: application/json;charset=UTF-8 
- 响应体：`{"msg":"访问凭证失效","code":"100002","data":null,"success":false}`

## P6 UAT /sign-task/get-detail（详情页写法）
- 时间：2026-09-11 17:59:45 +0800
- 请求：`POST https://uat-api.fadada.com/api/v5/sign-task/get-detail` （伪造 header + X-FASC-AccessToken=fake，body bizContent={"signTaskId":"1"}）
- HTTP：401
- 响应头：content-type: application/json;charset=UTF-8 
- 响应体：`{"msg":"访问凭证失效","code":"100002","data":null,"success":false}`

## P7 UAT /sign-task/app/get-detail（API概览写法）
- 时间：2026-09-11 17:59:46 +0800
- 请求：`POST https://uat-api.fadada.com/api/v5/sign-task/app/get-detail` （伪造 header + X-FASC-AccessToken=fake，body bizContent={"signTaskId":"1"}）
- HTTP：401
- 响应头：content-type: application/json;charset=UTF-8 
- 响应体：`{"msg":"访问凭证失效","code":"100002","data":null,"success":false}`

## P8 UAT 换 token 过期时间戳
- 时间：2026-09-11 17:59:46 +0800
- 请求：`POST https://uat-api.fadada.com/api/v5/service/get-access-token` （伪造 header，X-FASC-Timestamp 设为 10 分钟前，含 X-FASC-Grant-Type）
- HTTP：200
- 响应头：content-type: application/json;charset=UTF-8 x-content-type-options: nosniff 
- 响应体：`{"msg":"请求已过期","code":"100001","data":null,"success":false}`

## 汇总（2026-09-11）

共 8 次请求：换 token 接口 UAT 3 次（P1/P4/P8）、生产 1 次（P2）；`/sign-task/create` 1 次（P3）；`/sign-task/not-exist-xyz`、`/sign-task/get-detail`、`/sign-task/app/get-detail` 各 1 次（P5–P7）。
全部为伪造 AppId `test` / 伪造签名 / 伪造 token，未发送任何真实个人信息，未创建任何资源。

| 结论 | 依据 | 与文档 |
| --- | --- | --- |
| UAT、生产两个 Base URL 在线，返回 JSON | P1、P2 | 一致 |
| AppId 无效 → HTTP 200 + `100001`「未获取有效的平台信息」 | P1、P2、P4 | 文档 100001 = HTTP 500「不可预知异常，请稍后重试」→ **不符** |
| 时间戳偏差 10 分钟 → HTTP 200 + `100001`「请求已过期」；时间戳校验先于 AppId 校验 | P8 | 文档无此说明 → **不符**（100001 多义） |
| 缺全部 X-FASC 头 → HTTP 200 + `100012`「X-FASC-App-Id 不能为空」 | P3 | 文档"请求头参数为空"是 100010 → **不符** |
| 伪造 token → HTTP 401 + `100002`「访问凭证失效」 | P5–P7 | 一致 |
| token 校验先于路由：不存在的路径也是 100002 | P5 | 文档未说明 |
| 新版 / 旧版详情路径在无凭证下无法区分 | P6、P7 | — |
| 错误响应多一个 `success: false` 字段 | 全部 | 文档未列 → **不符** |
| GET 换 token 与 POST 返回相同错误（方法校验不先于 AppId 校验） | P4 | — |

"不符"的 3 类（100012 vs 100010、100001 语义与 HTTP 状态、success 字段）已在 reference 中用 `<!-- Gap: … -->` 标记。
