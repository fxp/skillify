# 纷享销客 OpenAPI 无凭证探测日志

- 日期：2026-09-11（北京时间 17:58–18:05）
- 原则：不注册、不登录、不用任何真实凭证；只用明显伪造的值（`FSAID_test` / `test` / `FAKE_TOKEN_FOR_PROBE`）；每个接口 ≤3 次；不创建任何数据。
- 工具：`curl -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'`，`thirdTraceId` 每次用新的 UUID v4。

| # | 时间 | 请求（已去敏） | HTTP | 响应片段 | 结论 |
|---|---|---|---|---|---|
| P1 | 17:58:40 | `POST https://open.fxiaoke.com/oauth2.0/token?thirdTraceId=<uuid>` body `{"appId":"FSAID_test","appSecret":"test","permanentCode":"test","grantType":"app_secret"}` | 200 | `{"errorCode":10006,"errorMessage":"the parameter appSecret is missing or illegal","errorDescription":"缺少参数或参数不合法","error":"非法请求","error_description":"缺少参数或参数不合法"}` | 路径存在；错误也回 HTTP 200；**错误码 10006 与文档返回码表（10006=缺少参数scope）不符** |
| P2 | 17:58:40 | `POST https://open.fxiaoke.com/cgi/corpAccessToken/get/V2?thirdTraceId=<uuid>` body `{"appId":"FSAID_test","appSecret":"test","permanentCode":"test"}` | 200 | `{"errorCode":10006,"errorMessage":"the parameter appSecret is missing or illegal","errorDescription":"缺少参数或参数不合法","traceId":"open-api-gateway-web/…"}` | 旧版换 token 路径仍在服务；同样回 10006 |
| P3 | 17:58:40 | `POST https://open.fxiaoke.com/cgi/crm/v2/data/query?thirdTraceId=<uuid>`，**不带任何鉴权 header、body 里也没有 corpAccessToken**，body 为 AccountObj 查询 | 200 | `{"traceId":"E-O.null.-1000-…","errorMessage":"corpAccessToken为必填项，不能为空","errorCode":20017}` | 缺鉴权回 **20017**，文档表里 20017=corpId未找到、缺 corpAccessToken 应为 10013 —— 不符 |
| P4 | 17:59:06 | 同 P3 路径，header `authorization: Bearer FAKE_TOKEN_FOR_PROBE`、`x-fs-ea: test`、`x-fs-userid: 1000` | 200 | `{"traceId":"E-O.null.-1000-…","errorMessage":"the cropId,cropAccessToken or authorization is error","errorCode":20016}` | 新版 header 被网关识别（不再报"必填"）；伪造 token 回 20016（与文档"corpAccessToken不存在或者已经过期"一致） |
| P5 | 17:59:08 | 同 P4，但 **URL 不带 thirdTraceId** | 200 | 同 P4：`errorCode 20016` | 缺 thirdTraceId 没有先于鉴权被拒；真实 token 下是否校验 ⚠ 未能判定 |
| P6 | 17:59:08 | `POST https://open.fxiaoke.com/cgi/crm/custom/v2/data/query?thirdTraceId=<uuid>`，旧版传参（body 里 `corpAccessToken:"FAKE"`、`corpId:"FSCID_test"`、`currentOpenUserId:"FSUID_test"`），对象 `object_test__c` | 200 | `{"traceId":"E-O.null.-1000-…","errorMessage":"the cropId,cropAccessToken or authorization is error","errorCode":20016}` | 自定义对象路径存在；旧版 body 传参仍被网关识别 |
| P7 | 17:59:08 | `POST https://www.fxiaoke.com/cgi/crm/v2/data/get?thirdTraceId=<uuid>`（文档「公共参数填写」页示例用的域名），伪造 Bearer | 302 | HTML `302 Found … FS_SRV` | `www.fxiaoke.com` 不是 OpenAPI 网关，返回 302 而不是 JSON；OpenAPI 要打 `open.fxiaoke.com`（或所在云的 `open-*` 域名） |
| P10 | 17:59:54 | 同 P7 再发一次，只看响应头 | 302 | `location: https://www.fxiaoke.com/messageform/website/html/home.html` | 确认 `www.fxiaoke.com/cgi/*` 被重定向到官网页面 |
| P8 | 17:59:09 | `POST https://open.fxiaoke.com/oauth2.0/token?thirdTraceId=<uuid>`，**body 不带 appSecret 字段** | 200 | 同 P1：`errorCode 10006 … appSecret is missing or illegal` | "缺少"和"不合法"共用 10006，不是文档表里的 10002 / 11002 |
| P9 | 17:59:09 | `POST https://open-hwcloud.fxiaoke.com/oauth2.0/token?thirdTraceId=<uuid>`，伪造凭证 | 200 | 同 P1：`errorCode 10006` | 华为云域名可达，行为与纷享云一致 |

## 汇总

1. **所有鉴权 / 参数错误都返回 HTTP 200**，必须判 body 里的 `errorCode != 0`。
2. **实际错误码与文档「全局返回码」表对不上**（P1/P3/P8，均为探测证实）：
   - 换 token 时 appSecret 缺失或非法 → 实际 `10006`（文档：10006=缺少参数scope；应为 10002/11002）
   - 业务接口完全不带鉴权 → 实际 `20017` + "corpAccessToken为必填项"（文档：20017=corpId未找到；应为 10013）
   - 伪造 token → `20016`，与文档一致
3. 新版 header 传参（`authorization: Bearer …` + `x-fs-ea` + `x-fs-userid`）与旧版 body 传参（`corpAccessToken` + `corpId` + `currentOpenUserId`）在网关层**都被识别**。
4. `www.fxiaoke.com/cgi/...`（文档示例里出现的域名）返回 302 HTML，不是 API 入口。
5. 未能用无凭证方式验证的：`thirdTraceId` 是否强制、`currentOpenUserId`/`x-fs-userid` 缺失时的报错、`limit>100` 与 `offset>10000` 的真实报错、`__c` 对象误走预置对象路径时的报错——都在 verification-plan.md 里。
