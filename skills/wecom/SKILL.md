---
name: wecom
description: 接入企业微信（WeCom / WeChat Work，developer.work.weixin.qq.com，接口域名 qyapi.weixin.qq.com）服务端 API 的使用手册——涵盖 access_token 与各类应用 secret 的选择与缓存、可信 IP、通讯录（成员/部门/标签）、应用消息与群机器人 webhook、应用群聊与素材上传、客户联系（外部联系人、客户群、「联系我」、企业群发、新客户欢迎语、客户标签）、审批（模板详情、提交申请、拉取审批单、状态回调）、回调 URL 验证与消息加解密（WXBizMsgCrypt、EncodingAESKey）、错误码与频率限制。当用户提到"企业微信""企微""WeCom""WeChat Work""qyapi""corpid""corpsecret""agentid""通讯录同步""企微机器人 webhook""客户联系""external_userid""联系我""企微审批""WXBizMsgCrypt""EncodingAESKey"，或要写代码对接企业微信时，应主动使用本技能，不要凭记忆编造接口参数，也不要套用微信公众号、飞书、钉钉的接口习惯。
---
# 企业微信（WeCom）服务端 API 接入指南

企业微信服务端 API：企业自建应用用 `corpid + 应用 secret` 换 access_token，调用通讯录、应用消息、客户联系（企微的 CRM 能力）、审批等接口，
并通过加密回调接收消息与事件。**本页只做分流与规则，字段表和示例在 references/。**

## ⚠ 验证状态

文档版：内容整理自 https://developer.work.weixin.qq.com/document/ （抓取于 2026-09-11，共 69 页服务端 API 文档），**未用真实凭证调用验证**。
另做了 26 次无凭证探测（伪造 corpid / token / webhook key，确认路径存在、鉴权失败格式、token 位置、HTTP→HTTPS 行为），
并用文档自带示例在本地复算了回调签名与 AES 解密。报错描述凡未标「无凭证探测」的，都是「文档原文，未实测」。
拿到凭证后按 `wecom-workspace/verification-plan.md` 补测。对照实验待真实凭证到位后进行。

## 当前事实

| 项 | 值 |
| :--- | :--- |
| Base URL | `https://qyapi.weixin.qq.com/cgi-bin/`（无凭证探测：`http://` 返回 301） |
| 鉴权 | **access_token 只放 URL query**：`?access_token=ACCESS_TOKEN`。无凭证探测：放 `Authorization: Bearer` 头或 JSON body 都返回 `41001 access_token missing` |
| 换 token | `GET /cgi-bin/gettoken?corpid=ID&corpsecret=SECRET` → `expires_in` 7200 秒；token 最长 512 字节；**按应用分别缓存** |
| 最容易选错 | **用哪个 secret**：自建应用 secret（发消息、读可见范围通讯录）/ 通讯录同步 secret（写通讯录）/ 客户联系、审批要先把自建应用加进各自的「可调用接口的应用」再用它的 secret |
| 响应判定 | HTTP 200 + `errcode`：存在且不为 0 即失败；失败响应仍带空的默认字段；未知路径是 HTTP 404 空 body（均为无凭证探测） |
| 回调加解密 | `sha1(sort([token, timestamp, nonce, encrypt]))`；AESKey = `b64decode(EncodingAESKey + "=")`；AES-256-CBC，IV = AESKey[:16]；**PKCS#7 按 32 字节** |
| 群机器人 | `POST /cgi-bin/webhook/send?key=KEY`，不用 access_token；每个机器人 20 条/分钟 |

## 照通用经验写容易错的地方（来自文档，未实测）

1. **token 不是 header，是 query 参数。** 按 OAuth 习惯写 `Authorization: Bearer` 一定失败；文档 41001 排查原文「access_token需要拼接在URL中，不能放在请求包体中」，无凭证探测也证实了 header / body 都不认。
2. **secret 按应用区分，token 不能混用。** 通讯录同步 token 不能发消息；自建应用 token 不能写通讯录；2022-08-15 起通讯录同步 secret 从新 IP 读不到姓名等详情（48009）；
   客户联系 / 审批 2023-12-01 起不再支持系统应用 secret，要把自建应用配进「可调用接口的应用」，否则 48002 / 301055。2022-06-20 后新建自建应用还必须配企业可信 IP（60020）。
3. **token 必须缓存，别每次请求都换。** 频繁调 gettoken 会被频率拦截；secret 错误多次会把**同一出口 IP 封禁一小时**；平台可能提前让 token 失效，遇 40014 / 42001 要强制刷新重试一次。
4. **HTTP 200 不代表成功，errcode 0 也不代表全部成功。** 发应用消息部分接收人无效时仍返回 `errcode: 0` 加 `invaliduser`；超频的消息被**静默丢弃不下发**。
5. **接收人格式因接口而异。** `message/send` 的 touser 是 `"a|b|c"` 竖线字符串；标签、应用群聊、更新模板卡片的成员列表是 JSON 数组。写成数组或写成字符串都会报 40035 / 40070 一类错误。
6. **回调 AES 填充块是 32 字节，不是 16。** 本地复算文档示例，填充长度为 30，16 字节块的标准 unpad 会报错；GET 验证要 1 秒内返回裸明文（无引号 / 换行），POST 5 秒不回会重试三次，要幂等。
7. **客户联系的几个“直觉相反”：** API 操作不会产生回调；WelcomeCode 只有 20 秒且可能缺失；`add_msg_template` 只创建群发任务，**需成员确认才发出**；同一客户对不同调用方 external_userid 不同。

## 我要做什么 → 读哪一份

| 我要做什么 | 读 | 核心 endpoint |
| :--- | :--- | :--- |
| 换取并缓存 access_token、选对 secret、配置可信 IP 与 IP 段 | [`access-token.md`](references/access-token.md) | `GET /cgi-bin/gettoken` · `GET /cgi-bin/get_api_domain_ip` |
| 同步通讯录：成员、部门、标签的读写与变更回调 | [`contacts.md`](references/contacts.md) | `POST /cgi-bin/user/create` · `GET /cgi-bin/user/get` · `POST /cgi-bin/user/list_id` · `GET /cgi-bin/department/simplelist` |
| 发应用消息、群机器人 webhook、应用群聊、上传素材 | [`messaging.md`](references/messaging.md) | `POST /cgi-bin/message/send` · `POST /cgi-bin/webhook/send` · `POST /cgi-bin/media/upload` |
| 客户联系：客户与客户群、客户标签、「联系我」、群发、欢迎语 | [`customer-contact.md`](references/customer-contact.md) | `GET /cgi-bin/externalcontact/get` · `POST /cgi-bin/externalcontact/add_contact_way` · `POST /cgi-bin/externalcontact/send_welcome_msg` |
| 审批：模板详情、代员工提交、批量拉单、状态回调 | [`approval.md`](references/approval.md) | `POST /cgi-bin/oa/gettemplatedetail` · `POST /cgi-bin/oa/applyevent` · `POST /cgi-bin/oa/getapprovaldetail` |
| 回调 URL 验证、消息加解密、接收消息与事件、被动回复 | [`callbacks-crypto.md`](references/callbacks-crypto.md) | `GET` / `POST` 你的回调 URL · `GET /cgi-bin/getcallbackip` |
| 错误码含义、频率限制、重试策略 | [`errors-and-limits.md`](references/errors-and-limits.md) | 全局 `errcode` 表 |

本 skill 不覆盖：身份验证（OAuth2 网页授权 / 扫码登录，文档 `document/path/91020` 分组）、第三方应用与服务商代开发（suite_access_token）、
应用管理与自定义菜单、微信客服、会话内容存档、打卡 / 汇报 / 日程 / 会议 / 微盘 / 文档 / 邮件、企业支付、家校与政民沟通、JS-SDK。
这些都在 https://developer.work.weixin.qq.com/document/ 的对应目录下。

## House rules

- 凭证只走环境变量：`WECOM_CORP_ID`、`WECOM_APP_SECRET`、`WECOM_CONTACT_SYNC_SECRET`、`WECOM_WEBHOOK_KEY`、`WECOM_CALLBACK_TOKEN`、`WECOM_ENCODING_AES_KEY`。webhook key 泄漏即可被人往群里发消息。
- 所有调用走一个封装：token 进 query、`raise_for_status()`、判 `errcode`、40014 / 42001 刷新重试一次、`-1` 等可重试码指数退避（见 `errors-and-limits.md`）。
- 成功分支也要检查部分失败字段：`invaliduser` / `invalidparty` / `invalidtag` / `unlicenseduser`、`invalidlist`、`fail_list`、`fail_info`。
- GET 接口参数走 query string，POST 走 JSON body。删除成员 `user/delete`、删除部门 `department/delete` 是 **GET**。
- 时间戳一律是秒；审批控件里 `s_timestamp`、`new_money`、`new_number` 按文档写成字符串。
- 回调“先回 200、后异步处理”，并用 MsgId 或 FromUserName+CreateTime 排重；不要强依赖回调，定期用列表接口对账。
- 上传素材的 media_id 3 天过期；群机器人的文件必须用 `webhook/upload_media` 上传，应用的 media_id 不通用。

## 文档自相矛盾 / 未说明之处（⚠ 汇总）

- 上传临时素材：90253 写图片 10MB、语音 2MB；全局错误码 45001 写图片 / 音频 5M → `messaging.md`、`errors-and-limits.md`
- `user/list` 参数表无 `fetch_child`，错误码 45029 排查却提到 `fetch_child=1` → `contacts.md`
- 部门写接口权限只写“第三方仅通讯录应用”，未提通讯录同步助手（概述页说可写） → `contacts.md`
- 删除部门时部门非空是否允许未说明 → `contacts.md`
- 回调 IP 段示例一处是精确 IP，一处带 `*` 通配 → `access-token.md`
- gettoken 频率上限、45033 并发上限未给数字 → `access-token.md`、`errors-and-limits.md`
- `applyevent.use_template_approver` 标必填又写默认 0；金额 `new_money` 单位未说明 → `approval.md`
- `getapprovalinfo` 游标字段 `next_cursor` / `new_next_cursor` 说法不一，返回示例缺游标；token 来源说法与“2023-12-01 起不支持系统应用 secret”冲突 → `approval.md`
- 欢迎语 `attachments.msgtype` 可选值未列 `file`，示例却有 → `customer-contact.md`
- `remark_mobiles` 清空时传 `""` 还是 `[""]` 未说明 → `customer-contact.md`
- 回调 JSON 格式如何开启未说明；echostr 中 `+` 的编码未说明；取消关注事件字面值未核对；官方加解密库下载页未能抓取 → `callbacks-crypto.md`

## 文档与探测不符之处

reference 中用 `<!-- Gap: … -->` 标记，可 grep 定位（1 处）：客户联系多个接口文档把请求方式标为“POST(HTTP)”，无凭证探测 `http://` 实际 301 跳转到 https → `customer-contact.md`。
