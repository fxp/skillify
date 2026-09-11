# 飞书开放平台 · 无凭证探测日志（2026-09-11）

规则（BRIEF 硬规矩 1、2）：不注册、不登录、不使用任何真实 App ID / App Secret / token；所有 ID、token、code
都是明显伪造的值（`app_id=test`、`Bearer t-fakefakefakefake`、全零 webhook ID、`client_id=cli_test`）；
不创建任何资源；每个接口 ≤3 次。请求一律带浏览器 UA。原始输出（含响应头）见同目录 `probe-raw.txt`。

## 抓取阶段的发现

| # | 时间 (+0800) | 请求 | HTTP | 响应片段 | 结论 |
|---|---|---|---|---|---|
| F1 | 17:5x | `GET https://open.feishu.cn/llms-full.txt` | 200 `text/html` | `<div class="open-platform-desc">The page does not exist.` | **软 404**：状态码 200，但内容是 HTML 的"页面不存在"，不是全文。只能用 `llms.txt`（二级索引）逐页抓 |
| F2 | 17:5x | `GET https://open.feishu.cn/llms.txt` | 200 `text/markdown` | 119 行，54 条二级索引 `llms-docs/zh-CN/llms-*.txt` | 真索引；二级索引内每页 URL 以 `.md` 结尾，可直接取 Markdown |
| F3 | 18:0x | `GET /openapi.json`、`/openapi.yaml`、`/swagger.json`、`/document/openapi.json` | 全部 200 `text/html` | 同 F1 的软 404 页（7720 / 7256 字节） | 没有公开 OpenAPI 规范；字段表只能来自 Markdown 页 |
| F4 | 17:5x | `GET .../authentication-management/access-token/get-user-access-token-v3.md` | 404 | `This document is not found` | v3 页不在索引路径下；换成 `/document/uAjLw4CM/ukTMukTMukTM/authentication-management/access-token/get-user-access-token-v3.md` 才是 200 |

## 接口探测

| # | 时间 (+0800) | 请求（已去敏） | HTTP | 响应片段 | 结论 |
|---|---|---|---|---|---|
| P01 | 18:00:23 | `POST open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal` body `{"app_id":"test","app_secret":"test"}` | **200** | `{"code":10003,"data":{},"msg":"invalid param"}` | 换 token 失败时 **HTTP 仍是 200**，只能靠 `code != 0` 判失败 |
| P02 | 18:00:24 | 同上，路径带尾斜杠 `/internal/`（文档「调用 API」页示例写法） | 200 | `{"code":10003,...,"msg":"invalid param"}` | 尾斜杠也可达，行为相同 |
| P03 | 18:00:25 | `GET .../auth/v3/tenant_access_token/internal`（错误方法） | **404** `text/plain` | `404 page not found` | 方法不对返回纯文本 404，**不是**通用错误码表写的 JSON `99991301` |
| P04 | 18:00:26 | `POST open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal` 伪造 app_id | 200 | `{"code":10003,"data":{},"msg":"invalid param"}` | Lark 国际版域名同路径存在，响应结构一致 |
| P05 | 18:00:28 | `POST .../auth/v3/app_access_token/internal` body `{"app_id":"cli_test","app_secret":"test"}` | 200 | `{"code":10003,"data":{},"msg":"invalid param"}` | 同 P01 |
| P06 | 18:00:29 | `GET .../contact/v3/users/find_by_department?department_id=0`，**不带** Authorization | 400 | `{"code":99991661,"msg":"Missing access token for authorization...","error":{"log_id":"...","troubleshooter":"..."}}` | 业务类接口鉴权失败：HTTP 400 + `code` + `error.log_id/troubleshooter` |
| P07 | 18:00:30 | 同上，`Authorization: Bearer t-fakefakefakefake` | 400 | `{"code":99991663,"msg":"Invalid access token for authorization..."}` | 伪造 tenant token → 99991663 |
| P08 | 18:00:31 | 同上，`Authorization: t-fakefakefakefake`（**不带 Bearer**） | 400 | `{"code":99991661,"msg":"Missing access token..."}` | 缺 `Bearer ` 前缀时服务端当作"没带 token"，报 99991661 而不是"格式错误" |
| P09 | 18:00:32 | 同上，`Authorization: Bearer eyJhbGciOiJFUzI1NiIs...`（伪造的新版 user token 形态） | 400 | `{"code":99991668,"msg":"Invalid access token for authorization..."}` | `eyJ` 开头被识别为 user_access_token（99991668），**没有**返回通用错误码表 99991671 描述的 "must start with t-/u-" |
| P10 | 18:00:33 | `POST .../im/v1/messages?receive_id_type=open_id`，`Bearer t-fake` | 400 | `{"code":99991663,...}` | 同 P07 |
| P11 | 18:00:34 | `POST .../bot/v2/hook/00000000-0000-0000-0000-000000000000` body `{"msg_type":"text","content":{"text":"probe"}}` | **200** | `{"code":19001,"data":{},"msg":"param invalid: incoming webhook access token invalid"}` | 自定义机器人 webhook 失败时 HTTP 200；错误码 **19001** 在自定义机器人指南里没有列出 |
| P12 | 18:00:35 | `POST https://accounts.feishu.cn/oauth/v3/token`，`application/x-www-form-urlencoded`，`grant_type=authorization_code&client_id=cli_test&client_secret=test&code=test` | 400 | `{"error":"invalid_grant","error_description":"The authorization code is not found...","code":20003}` | v3 令牌端点存在；失败为 HTTP 400 + OAuth 风格 `error`/`error_description` + `code` |
| P13 | 18:00:37 | 同上，改为 JSON body | 400 | 同 P12，`code":20003` | 文档说 v3 "兼容 application/json"——JSON 请求也走到了同一校验分支 |
| P14 | 18:00:38 | `POST open.feishu.cn/open-apis/authen/v2/oauth/token` JSON，伪造 code | 400 | 同 P12，`code":20003` | 已标"历史版本"的 v2 端点仍在响应 |
| P15 | 18:00:39 | `POST .../bitable/v1/apps/bascnFAKE/tables/tblFAKE/records/search`，`Bearer t-fake` | 400 | `{"code":99991663,...}` | 路径存在，鉴权先于参数校验 |
| P16 | 18:00:40 | `POST .../approval/v4/instances`，`Bearer t-fake` | 400 | `{"code":99991663,...}` | 路径存在 |
| P17 | 18:00:41 | `POST .../corehr/v2/employees/batch_get`，`Bearer t-fake` | 400 | `{"code":99991663,...}` | 路径存在（文档目录名是 corehr-v1，实际接口是 `/corehr/v2/`） |
| P18 | 18:00:42 | `GET .../event/v1/outbound_ip`，不带 Authorization | 400 | `{"code":99991661,...}` | 路径存在 |
| P19 | 18:00:44 | `POST https://www.feishu.cn/approval/openapi/v2/file/upload`，不带 Authorization | 400 | `{"code":99991661,...}` | 审批上传文件的**特殊域名路径**确实存在，且走同一套网关鉴权 |
| P20 | 18:00:46 | `GET .../open-apis/nonexistent/v1/foo`，`Bearer t-fake` | **404** `text/plain` | `404 page not found` | 路径不存在返回纯文本 404，**不是**通用错误码表写的 JSON `99991201` |

## 汇总：和文档不符 / 文档没写的

1. **路径或方法错误时不返回 JSON 错误码**（P03、P20）：通用错误码表列了 `99991201 resource not find（请求路径错误 404）`
   和 `99991301 request method doesn't match`，实测两种情况都是 HTTP 404 + `text/plain` 的 `404 page not found`。
   解析响应前要先看 Content-Type，别对它 `resp.json()`。→ 写入 `errors-and-limits.md` 的 `<!-- Gap -->`。
2. **换 token 接口失败 HTTP 200**（P01、P04、P05）：文档没写失败时的 HTTP 状态，实测是 200 + `code:10003`。
3. **不带 `Bearer ` 前缀 = 没带 token**（P08）：返回 99991661，报错信息不会提示"缺少 Bearer"。
4. **自定义机器人 webhook 失败码 19001**（P11）：指南只列了 9499、19021、19022、19024。
5. **v3 令牌端点 JSON 与表单都可达**（P12、P13），v2 端点仍在（P14）。
6. **`eyJ` 形态 token 被识别为 user token**（P09），通用错误码表 99991671 的 "must start with t-/u-" 已跟不上新格式。
7. **Lark 域名同路径可达**（P04）。

## 没做 / 做不到的

- 任何需要真实凭证才能进入业务校验分支的行为（字段必填、ID 类型混用、分页上限、频控头）一律未测，列在 `verification-plan.md`。
- 没有向任何真实群、真实用户发送消息；P11 的 webhook ID 为全零伪造值。
