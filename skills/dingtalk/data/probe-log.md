# 无凭证探测日志（dingtalk，2026-09-11）

所有请求只用明显伪造的 test 值，不含任何真实凭证；每个接口 ≤3 次。

## P1 旧版 gettoken（query 参数，伪造 appkey）
- 时间：2026-09-11 17:58:21 +0800
- 请求：`curl https://oapi.dingtalk.com/gettoken\?appkey=test\&appsecret=test `
- HTTP 状态 | content-type：`200|application/json`
- 响应片段：`{"errcode":40096,"errmsg":"不合法的appKey或appSecret"}`

## P2 旧版 gettoken（照文档 curl 写法：-X GET + -d 表单 body）
- 时间：2026-09-11 17:58:21 +0800
- 请求：`curl -X GET https://oapi.dingtalk.com/gettoken -H Content-Type:application/x-www-form-urlencoded\;charset=utf-8 -d appkey=test -d appsecret=test `
- HTTP 状态 | content-type：`200|application/json`
- 响应片段：`{"errcode":40035,"errmsg":"缺少参数 corpid or appkey"}`

## P3 新版 accessToken（伪造 appKey）
- 时间：2026-09-11 17:58:22 +0800
- 请求：`curl -X POST https://api.dingtalk.com/v1.0/oauth2/accessToken -H Content-Type:\ application/json -d \{\"appKey\":\"test\"\,\"appSecret\":\"test\"\} `
- HTTP 状态 | content-type：`400|application/json;charset=utf-8`
- 响应片段：`{"requestid":"01A08FE7-68C3-7BBD-B223-447768EA4B29","code":"invalidClientIdOrSecret","message":"无效的clientId或者clientSecret"}`

## P4 新版统一 token（/v1.0/oauth2/{corpId}/token，伪造 corpId/client_id）
- 时间：2026-09-11 17:58:22 +0800
- 请求：`curl -X POST https://api.dingtalk.com/v1.0/oauth2/dingtest/token -H Content-Type:\ application/json -d \{\"client_id\":\"test\"\,\"client_secret\":\"test\"\,\"grant_type\":\"client_credentials\"\} `
- HTTP 状态 | content-type：`500|application/json;charset=utf-8`
- 响应片段：`{"requestid":"01A08FE7-6920-789A-84FF-612C1DFD554D","code":"unknownError","message":"未知错误"}`

## P5 自定义机器人 webhook（伪造 access_token）
- 时间：2026-09-11 17:58:22 +0800
- 请求：`curl -X POST https://oapi.dingtalk.com/robot/send\?access_token=test -H Content-Type:\ application/json -d \{\"msgtype\":\"text\"\,\"text\":\{\"content\":\"probe\"\}\} `
- HTTP 状态 | content-type：`200|application/json`
- 响应片段：`{"errcode":660026,"errmsg":"sending too many messages per minute"}`

## P5b 自定义机器人 webhook（随机 64 位 hex 伪造 access_token，排除共享 test 值被限流的干扰）
- 时间：2026-09-11 17:58:48 +0800
- 请求：`curl -X POST https://oapi.dingtalk.com/robot/send\?access_token=<随机64位hex，非凭证> -H Content-Type:\ application/json -d \{\"msgtype\":\"text\"\,\"text\":\{\"content\":\"probe\"\}\} `
- HTTP 状态 | content-type：`200|application/json`
- 响应片段：`{"errcode":300005,"errmsg":"token is not exist"}`

## P6 新版 API 用 header x-acs-dingtalk-access-token（伪造值）
- 时间：2026-09-11 17:58:48 +0800
- 请求：`curl https://api.dingtalk.com/v1.0/contact/users/test -H x-acs-dingtalk-access-token:\ test `
- HTTP 状态 | content-type：`400|application/json;charset=utf-8`
- 响应片段：`{"code":"InvalidAuthentication","requestid":"01A08FE7-CD6B-79BB-8B2E-35D8768AD457","message":"不合法的access_token"}`

## P7 新版 API 改用旧版习惯：query ?access_token=（伪造值），不带 header
- 时间：2026-09-11 17:58:48 +0800
- 请求：`curl https://api.dingtalk.com/v1.0/contact/users/test\?access_token=test `
- HTTP 状态 | content-type：`400|application/json;charset=utf-8`
- 响应片段：`{"code":"AuthenticationFailed.MissingParameter","requestid":"01A08FE7-CDD1-7818-964E-AF384B54BB19","message":"缺少参数：x-acs-dingtalk-access-token"}`

## P8 旧版 API 用 query ?access_token=（伪造值）
- 时间：2026-09-11 17:58:48 +0800
- 请求：`curl -X POST https://oapi.dingtalk.com/topapi/v2/user/get\?access_token=test -H Content-Type:\ application/json -d \{\"userid\":\"test\"\} `
- HTTP 状态 | content-type：`200|application/json;charset=UTF-8`
- 响应片段：`{"errcode":88,"sub_code":"40014","sub_msg":"不合法的access_token","errmsg":"ding talk error[subcode=40014,submsg=不合法的access_token]","request_id":"16l4ew3d47pdp"}`

## P9 旧版 API 改用新版习惯：header x-acs-dingtalk-access-token（伪造值），不带 query
- 时间：2026-09-11 17:58:48 +0800
- 请求：`curl -X POST https://oapi.dingtalk.com/topapi/v2/user/get -H x-acs-dingtalk-access-token:\ test -H Content-Type:\ application/json -d \{\"userid\":\"test\"\} `
- HTTP 状态 | content-type：`200|application/json;charset=UTF-8`
- 响应片段：`{"errcode":88,"sub_code":"40000","sub_msg":"access_token is blank","errmsg":"ding talk error[subcode=40000,submsg=access_token is blank]","request_id":"16kde384l16sp"}`

## P10 新版 API 用 Authorization: Bearer（伪造值）
- 时间：2026-09-11 17:58:48 +0800
- 请求：`curl https://api.dingtalk.com/v1.0/contact/users/test -H Authorization:\ Bearer\ test `
- HTTP 状态 | content-type：`400|application/json;charset=utf-8`
- 响应片段：`{"code":"AuthenticationFailed.MissingParameter","requestid":"01A08FE7-CF62-7186-917E-272C19339AC6","message":"缺少参数：x-acs-dingtalk-access-token"}`

## P11 旧版 API 照文档 curl 写法：access_token 放在 -d 表单 body（伪造值），不放 query
- 时间：2026-09-11 17:59:11 +0800
- 请求：`curl -X POST https://oapi.dingtalk.com/topapi/v2/user/get -H Content-Type:application/x-www-form-urlencoded\;charset=utf-8 -d access_token=test -d userid=test `
- HTTP 状态 | content-type：`200|application/json;charset=UTF-8`
- 响应片段：`{"errcode":88,"sub_code":"40014","sub_msg":"不合法的access_token","errmsg":"ding talk error[subcode=40014,submsg=不合法的access_token]","request_id":"15rajdcb5y1lp"}`

## P12 第三方授权企业 token，按文档表格路径（无 /v1.0）：POST /oauth2/corpAccessToken（伪造 suiteKey）
- 时间：2026-09-11 18:00:59 +0800
- 请求：`curl -X POST https://api.dingtalk.com/oauth2/corpAccessToken -H Content-Type:\ application/json -d \{\"suiteKey\":\"test\"\,\"suiteSecret\":\"test\"\,\"authCorpId\":\"dingtest\"\,\"suiteTicket\":\"test\"\} `
- HTTP 状态 | content-type：`200|application/json`
- 响应片段：`{"errcode":404,"errmsg":"请求的URI地址不存在"}`

## P13 第三方授权企业 token，按文档请求示例路径（带 /v1.0）：POST /v1.0/oauth2/corpAccessToken（伪造 suiteKey）
- 时间：2026-09-11 18:00:59 +0800
- 请求：`curl -X POST https://api.dingtalk.com/v1.0/oauth2/corpAccessToken -H Content-Type:\ application/json -d \{\"suiteKey\":\"test\"\,\"suiteSecret\":\"test\"\,\"authCorpId\":\"dingtest\"\,\"suiteTicket\":\"test\"\} `
- HTTP 状态 | content-type：`400|application/json;charset=utf-8`
- 响应片段：`{"requestid":"01A08FE9-CFA7-7AE1-9B46-1C681C6FFDD0","code":"invalidSuiteKey","message":"suitekey不合法"}`

## P14 旧版 oapi 不存在的路径（对照组：看 oapi 404 长什么样）
- 时间：2026-09-11 18:00:59 +0800
- 请求：`curl -X POST https://oapi.dingtalk.com/topapi/v2/user/notexist\?access_token=test -H Content-Type:\ application/json -d \{\} `
- HTTP 状态 | content-type：`200|application/json;charset=UTF-8`
- 响应片段：`{"errcode":22,"sub_msg":"不合法ApiName，ApiName = dingtalk.oapi.v2.user.notexist","errmsg":"Invalid method[submsg=不合法ApiName，ApiName = dingtalk.oapi.v2.user.notexist]","request_id":"15r6taqz8r6xu"}`

## 抓取层观察（非 API 探测）
- `https://open.dingtalk.com/llms.txt`：200，`content-type: text/plain;charset=UTF-8`（任务说明称标成 JSON，本次实际为 text/plain），209 条链接，二级索引 37 个（`/llms-docs/zh-CN/*.txt`）。
- `https://open.dingtalk.com/llms-full.txt`：200，但 `content-type: text/html`，内容是首页 SPA 壳（88 行），**不是全文**。
- `/openapi.json`、`/swagger.json`、`/api-docs`、`/sitemap.xml`：均 200 + text/html（SPA 回落），无公开规范。
- 页面 `https://open.dingtalk.com/document/<section>/<slug>.md` 返回 `text/markdown`；索引外的概念页（Stream、HTTP 回调、错误码、限流）同样可取；部分 slug 返回 302 到 HTML（已删除这些空壳）。
- 离线校验（本地计算，非 API 调用）：events.md 的 Python 解密类用「配置事件推送方式 · 常见问题」给出的测试向量解密得到 `success`。
