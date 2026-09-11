---
name: dingtalk
description: 接入钉钉开放平台（open.dingtalk.com；服务端 API 分新版 api.dingtalk.com 与旧版 oapi.dingtalk.com 两套）的接入手册——涵盖 access token（企业内部应用、第三方企业应用、用户 OAuth、免登）、通讯录（用户、部门、userid 与 unionid 转换）、工作通知、自定义机器人与企业机器人收发消息、互动卡片与 AI 流式卡片、OA 审批（发起、查询、同意拒绝、撤销）、考勤打卡与请假、事件订阅（Stream 模式与 HTTP 回调加解密）、错误码与限流。当用户提到"钉钉""DingTalk""钉钉开放平台""钉钉机器人""钉钉 webhook""工作通知""钉钉审批""钉钉考勤""Stream 模式""x-acs-dingtalk-access-token""oapi.dingtalk.com""dingtalk-stream""alibabacloud_dingtalk"，或要写代码调用钉钉任何服务端接口、接收钉钉回调时，应主动使用本技能，不要凭记忆混用新旧两套 API 的鉴权位置、路径和字段名。
---
# 钉钉开放平台 接入指南

钉钉开放平台的服务端 API 同时存在新旧两套：新版 `api.dingtalk.com/v1.0/...`（token 放 header）和旧版
`oapi.dingtalk.com/topapi/...`（token 放 query），两套开放的能力不完全重叠，一个项目里并用是常态。
本 skill 覆盖企业开发最常接的 7 块：鉴权、通讯录、消息、审批、考勤、事件订阅、错误与限流。
**本页只做分流与规则，字段表和示例在 references/。**

## ⚠ 验证状态

文档版：内容整理自 https://open.dingtalk.com/document/ （页面 `.md` 源，经 https://open.dingtalk.com/llms.txt 索引定位，
抓取于 2026-09-11），**未用真实凭证调用验证**。`llms-full.txt` 实际返回首页 HTML，不是全文；没有公开的 OpenAPI 规范。
无凭证探测（只用伪造的 `test` 值）做了 14 次：两套 API 放错 token 位置的报错、各 token 接口对伪造凭证的返回、
自定义机器人伪造 token、第三方 corpAccessToken 两个路径、旧版错误路径（明细见 `references/errors-and-limits.md` 第 2 节）。
事件回调解密代码用文档自带测试向量做过离线校验。对照实验待真实凭证到位后进行；
拿到凭证后按 `dingtalk-workspace/verification-plan.md` 补测。

## 当前事实

| 项 | 值 |
| :--- | :--- |
| 新版 Base URL | `https://api.dingtalk.com`，路径 `/v1.0/<产品>/...`，JSON，字段 camelCase |
| 新版鉴权 | header **`x-acs-dingtalk-access-token: <token>`**；不认 `Authorization: Bearer`、不认 `?access_token=`（无凭证探测证实） |
| 旧版 Base URL | `https://oapi.dingtalk.com`，路径 `/topapi/...`、`/attendance/...`、`/robot/send` 等，字段 snake_case |
| 旧版鉴权 | query **`?access_token=<token>`**；只放 header 会报 `errcode 88 / sub_code 40000 access_token is blank`（探测） |
| 应用 token | `POST api /v1.0/oauth2/accessToken`（body `appKey`/`appSecret`，回 `accessToken`/`expireIn`）或 `GET oapi /gettoken?appkey=&appsecret=`；7200 秒，须缓存 |
| 成功判定 | 旧版：HTTP 200 **且** `errcode == 0`（出错也是 200）；新版：HTTP 2xx，出错 4xx/5xx + `{"code","message","requestid"}` |
| 最容易选错 | 员工 ID 用 **userid**（又叫 staffId）；unionid 只在"开发者账号"范围唯一；机器人消息里的 `senderId` 是加密 ID，userid 在 `senderStaffId` |
| 事件接收 | Stream 模式（`pip install dingtalk-stream`，免公网、免加解密）优先；HTTP 回调须验签 + AES 解密 + 回加密的 `success` |

## 照通用经验写容易错的地方（来自文档，未实测）

1. **token 放哪取决于域名，不是个人习惯。** 新版只认 `x-acs-dingtalk-access-token` header，旧版只认 `access_token` 参数；
   放错时新版回 `AuthenticationFailed.MissingParameter`，旧版回 `errcode 88`（这两条是无凭证探测实测到的）。先看 host 再写鉴权。
2. **旧版的鉴权错误包在 `errcode: 88` 里。** 真实原因在 snake_case 的 `sub_code`（字符串，如 `"40014"`）/ `sub_msg`；
   全局错误码表把 40014 写成 errcode、把字段写成 subCode——按表写 `if errcode == 40014` 永远不触发（探测证实）。
3. **工作通知 errcode=0 不等于送达。** 文档原文：超出限额后"接口返回成功，但用户无法接收到"（同一员工同内容每天一条、
   内部应用每人每天 500 条等）。重要通知发完用 `getsendresult` 查 `forbidden_user_id_list`。`userid_list` 是逗号分隔字符串，≤100。
4. **HTTP 事件回调必须回"加密后的 success"。** 应答是 `{"msg_signature","timeStamp","nonce","encrypt"}`；AES-256-CBC，
   key = Base64Decode(aes_key + "=")，IV = key 前 16 字节，PKCS7 **块大小 32**；解密后校验 ownerKey（后台配置的事件用 AppKey）。
   嫌麻烦就用 Stream 模式，收到的就是明文。
5. **企业机器人接口的 `msgParam` 是 JSON 字符串，不是对象**；工作通知字段是 snake_case（`action_card`），
   自定义机器人字段是 camelCase（`actionCard`）；自定义机器人的 token 是 Webhook 里的，不是应用 token。
6. **审批表单的 value 一律是字符串。** 多选、图片、联系人、明细要先 JSON 序列化；日期区间连 `name` 都是
   `"[\"开始时间\",\"结束时间\"]"`；判断通过要 `status == "COMPLETED"` **且** `result == "agree"`（被拒也是 COMPLETED）。
7. **考勤两个打卡接口参数名不同、时间语义不同。** `/attendance/list` 用 `workDateFrom/To`、`userIdList`、按整天；
   `/attendance/listRecord` 用 `checkDateFrom/To`、`userIds`、按精确时刻；都限 7 天、50 人。请假 `duration_percent` 是时长 × 100。

## 我要做什么 → 读哪一份

| 我要做什么 | 读 | 核心 endpoint |
| :--- | :--- | :--- |
| 拿应用 token / 用户 OAuth 登录 / 免登 / 第三方应用 token、分清 ID 体系 | [`auth.md`](references/auth.md) | `POST /v1.0/oauth2/accessToken`、`GET /gettoken`、`POST /v1.0/oauth2/userAccessToken`、`POST /topapi/v2/user/getuserinfo` |
| 查员工 / 部门、unionid 与手机号转 userid、遍历全员 | [`contacts.md`](references/contacts.md) | `POST /topapi/v2/user/get`、`POST /topapi/v2/department/listsub`、`POST /topapi/user/listid`、`POST /topapi/user/getbyunionid` |
| 发工作通知、机器人发 / 收消息、互动卡片与 AI 流式卡片 | [`messaging.md`](references/messaging.md) | `POST /topapi/message/corpconversation/asyncsend_v2`、`POST /robot/send`、`POST /v1.0/robot/groupMessages/send`、`POST /v1.0/card/instances/createAndDeliver` |
| 发起 / 查询 / 同意拒绝 / 撤销 OA 审批 | [`oa-approval.md`](references/oa-approval.md) | `POST /v1.0/workflow/processInstances`、`GET /v1.0/workflow/processInstances`、`POST /v1.0/workflow/processes/instanceIds/query` |
| 拉打卡结果与明细、考勤组、请假、考勤报表 | [`attendance.md`](references/attendance.md) | `POST /attendance/list`、`POST /attendance/listRecord`、`POST /topapi/attendance/getleavestatus` |
| 接收事件：选 Stream 还是 HTTP、写回调加解密 | [`events.md`](references/events.md) | Stream topic `/v1.0/im/bot/messages/get`、HTTP 回调、`POST /call_back/register_call_back` |
| 解读错误码、处理限流与重试 | [`errors-and-limits.md`](references/errors-and-limits.md) | 全局错误码、IP 维度 20 秒 10000 次、`90002` |

本 skill 不覆盖：钉钉文档 / 知识库 / 云盘、日程与视频会议、待办、DING 消息、宜搭与多维表、智能 CRM、智能人事花名册、
项目管理、直播与教育、硬件与智能会议室、AI 助理、H5 / 小程序前端 JSAPI、第三方个人应用。这些的文档入口按产品线列在
https://open.dingtalk.com/llms.txt （各产品线子索引 `llms-docs/zh-CN/*.txt`，全量目录 `llms-api-catalog.txt`），页面 URL 加 `.md` 即得 Markdown 源。

## House rules

- 凭证只走环境变量：`DINGTALK_APP_KEY` / `DINGTALK_APP_SECRET`（Client ID / Secret）、`DINGTALK_AGENT_ID`、`DINGTALK_ROBOT_CODE`，
  自定义机器人 `DINGTALK_WEBHOOK_TOKEN` / `DINGTALK_WEBHOOK_SECRET`，HTTP 回调 `DINGTALK_CB_TOKEN` / `DINGTALK_CB_AES_KEY`。
- token 按应用缓存、提前几分钟刷新；文档反复要求"不能频繁调用 gettoken"。
- 同一个 HTTP 客户端要按 host 区分两套响应判定（见 `errors-and-limits.md` 第 7 节的 `parse()`），不要全局 `raise_for_status()`。
- 新代码优先用新版接口；某能力只有旧版（工作通知、考勤、大部分通讯录）就用旧版，不要凭记忆拼 `topapi` 以外的"旧旧版"路径（如 `/user/get`）。
- 报 `60011` 或 403 `Forbidden.AccessDenied.AccessTokenPermissionDenied` 是没申请权限点：去开发者后台「权限管理」开通，不是代码问题。
- 事件处理先回 ack / 加密 success，再异步处理；用 `eventId` 去重。
- 批量拉通讯录、考勤时控制节奏：同一出口 IP 20 秒超过 10000 次会被封 5 分钟，且返回可能是 HTML 而非 JSON。
- 旧版 SDK 的 Python 示例是 Python 2 语法（`except Exception,e`），不要照抄；示例统一用 `requests`，新版官方 SDK 为 `alibabacloud_dingtalk`。

## 文档自相矛盾 / 未说明之处（⚠ 汇总）

**探测证实的文档错误**（reference 里用 `<!-- Gap: … -->` 标记，共 4 处）：
- 旧版 `gettoken` 文档 curl 用 `-X GET -d` 传参，实测返回 `40035 缺少参数`，必须 query string（`auth.md`）。
- 第三方授权企业 token 的参数表 URL 缺 `/v1.0`，无凭证探测返回 HTTP 200 + `errcode 404`「请求的URI地址不存在」；正确是 `/v1.0/oauth2/corpAccessToken`（`auth.md`）。
- 自定义机器人 token 不存在，文档写 `400101`，实测 `300005 token is not exist`（`messaging.md`）。
- 全局错误码把 40014 列为 errcode、字段写 subCode，实测是 `errcode 88` + `sub_code: "40014"`（`errors-and-limits.md`）。

**⚠ 文档自相矛盾 / 未说明**（详见各 reference 末节）：
- 同一应用的新旧 token 能否互用；topapi 是否接受 JSON body（文档 curl 全是表单）——均未验证。
- 工作通知三方应用每人每日上限 100 vs 50；`getsendprogress` 时间窗 7 天 vs 24 小时；机器人单聊批量 20 vs 100（`messaging.md`）。
- HTTP 回调 URL 参数 `signature`/`msg_signature`、`timestamp`/`timeStamp` 各页不一；ownerKey 四处说法不一；token 长度 3–32 vs 6–64（`events.md`）。
- 审批根部门 `deptId` -1 vs 1；撤销的 `isSystem` 标可选但报"不能为空"（`oa-approval.md`）。
- 打卡结果 `limit` 上限 50 但示例传 100；打卡详情参数名与说明不一致（`attendance.md`）。
- 大量旧版响应示例把数字 / 布尔写成字符串（`"errcode": "0"`、`"boss": "true"`），解析要兼容（`contacts.md`）。
- 统一 token 接口对非法 corpId 返回 500 unknownError；`gettoken` 的 40096 不在错误码表（`auth.md`）。
