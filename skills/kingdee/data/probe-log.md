# kingdee 无凭证探测日志

规则：不注册、不登录、不用任何真实凭证；只发明显伪造的值（`test`）；每个接口 ≤3 次。
时间均为 2026-09-11（UTC+8）。

## 背景：为什么探测目标是 api.kingdee.com/galaxyapi

金蝶云星空 WebAPI 部署在客户自己的服务器（`http(s)://<客户域名>/k3cloud/`）或金蝶公有云租户域名上，
没有公共、无租户的业务端点。官方 Python SDK（`kingdee.cdp.webapi.sdk` 8.2.0）源码里曾把
`https://api.kingdee.com/galaxyapi/` 作为默认网关，现已注释掉（注释原文：「取消默认旧网关，要求必须输入url by Ann 2025-01-15」）。
这是唯一能无凭证触达的公开网关，所以只在它上面做探测。**它的行为不代表客户私有部署服务器的行为。**

## 记录

| # | 时间 | 请求（已去敏） | HTTP | 响应片段 |
| --- | --- | --- | --- | --- |
| G1 | 17:58:56 | `GET https://api.kingdee.com/galaxyapi/` | 519 | `{"errcode":5001,"description":"API not found[GW]","description_cn":"请求的API不存在[网关]"}` |
| G2 | 17:58:56 | `GET https://api.kingdee.com/` | 519 | 同上 5001 |
| T1 | 17:59:29 | `POST /galaxyapi/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc`，无任何鉴权头，body `{"data":{"FormId":"BD_MATERIAL","FieldKeys":"FNumber"}}` | 519 | `{"errcode":4002,"description":"Unauthorized, APP_ID is empty[GW]","description_cn":"认证失败, 应用ID为空[网关]"}` |
| T2 | 17:59:29 | 同 T1 路径，带 SDK 同形的伪造头：`X-Api-ClientID: test`、`X-Api-Auth-Version: 2.0`、`x-api-timestamp: 1789120000`（约 13 分钟前）、`x-api-nonce`、`x-api-signheaders: x-api-timestamp,x-api-nonce`、`X-Api-Signature`、`X-Kd-Appkey: test_test`、`X-Kd-Appdata`、`X-Kd-Signature`（值均为 `dGVzdA==`） | 519 | `{"errcode":4006,"description":"Unauthorized, errDescEn: X-Api-TimeStamp is invalid: 1789120000[GW]","description_cn":"认证失败, errDescCn: X-Api-TimeStamp过期: 1789120000[网关]"}` |
| T3 | 17:59:29 | `POST /galaxyapi/Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc`，body 全部为 `test`，无鉴权头 | 519 | 同 T1 `4002 APP_ID is empty` |
| T4 | 17:59:59 | 同 T2，但 `x-api-timestamp` 用当前秒级时间戳 | 519 | `{"errcode":4002,"description":"Unauthorized, APP_ID is empty[GW]",...}`；响应头带 `X-Api-Requestid: <uuid>`，`Server: nginx` |

ExecuteBillQuery 路径共 3 次（T1/T2/T4），ValidateUser 1 次，已到上限，停止。

## 结论（只陈述观察到的）

1. `.common.kdsvc` 服务路径在该网关上被识别为 API（鉴权错误而不是 5001 not found），与 SDK 的拼 URL 方式一致。
2. 网关失败时 HTTP 状态是 **519**（非标准码），body 是 `{"errcode","description","description_cn"}`——
   与业务层返回的 `Result.ResponseStatus` 结构完全不同。写错误处理时两种都要接住。
3. 网关先校验时间戳：13 分钟前的秒级时间戳被判「过期」（errcode 4006）。时间窗口具体多长 ⚠ 未测出（只测了一个点）。
4. T4 用 SDK 同形的 `X-Api-ClientID: test` 仍报「应用ID为空」。说明该网关读取 APP_ID 的来源不是（或不只是）
   `X-Api-ClientID` 头，⚠ 原因未查明（可能网关读别的头 / 该网关已停用第三方授权通道）。**不能据此判定 SDK 的头名是错的**——
   SDK 现在要求填客户自己的 ServerUrl，签名头是在客户服务器上校验的。
5. `ValidateUser`（账号密码登录）走该网关同样先被网关要求 APP_ID——公有云网关不接受裸账号密码登录。
