---
name: fadada
description: 接入法大大电子合同与电子签云平台（FASC OpenAPI 5.1，api.fadada.com，文档 dev.fadada.com）的 API 使用手册——涵盖 AppId/AppSecret 换 accessToken 与 X-FASC-* 请求头的 HMAC-SHA256 两步派生签名、个人/企业认证授权（clientUserId、openUserId、openCorpId）、文件上传与处理拿 fileId、签署任务（创建、添加文档与参与方、提交、撤销/删除/作废、查询、签署链接、下载）、签署模板与文档模板、回调事件接收与验签、错误码与限流。当用户提到"法大大""fadada""FASC""FASC OpenAPI""电子签 API""电子合同接口""签署任务""sign-task""X-FASC-Sign""bizContent""openCorpId"，或要写代码对接法大大发起合同签署、生成签署链接、处理签署完成回调时，应主动使用本技能，不要凭记忆编造签名算法和接口路径，也不要套用 e签宝、上上签、DocuSign 的接口习惯。
---
# 法大大（FASC OpenAPI 5.1）接入指南

法大大电子合同 / 电子签的服务端 OpenAPI：用 AppId/AppSecret 换 token，每个请求带一组 `X-FASC-*` 头和 HMAC-SHA256 签名，业务参数塞进表单字段 `bizContent`；核心业务对象是"签署任务"。
**本页只做分流与规则，字段表和示例在 references/。**

## ⚠ 验证状态

文档版：内容整理自 https://dev.fadada.com （FASC OpenAPI 5.1，经文档站背后的 `cloud.fadada.com/api/edge-developer/document/*` JSON 接口抓取，抓取于 2026-09-11）
和官方 Python SDK 源码（gitee `fadada-cloud/fasc-openapi-python-sdk`，`v5.1` 分支），**未用真实凭证调用验证**。
无凭证探测了 8 次：UAT / 生产换 token 接口（伪造 AppId、过期时间戳、GET 方法）、业务接口缺鉴权头、伪造 token 调业务接口与不存在的路径——结果见 auth-and-signing.md §10 与 errors-and-limits.md §3。
拿到凭证后按 `fadada-workspace/verification-plan.md` 补测；有 / 无 skill 的对照实验待真实凭证到位后进行。

## 当前事实

| 项 | 值 |
| --- | --- |
| Base URL | 生产 `https://api.fadada.com/api/v5`；测试 UAT `https://uat-api.fadada.com/api/v5`（两者均探测到在线） |
| 请求格式 | 一律 `POST` + `Content-Type: application/x-www-form-urlencoded`；业务参数是**一个**表单字段 `bizContent`，值为 JSON 字符串 |
| 鉴权头 | `X-FASC-App-Id`、`X-FASC-Sign-Type: HMAC-SHA256`、`X-FASC-Sign`、`X-FASC-Timestamp`（毫秒，±5 分钟）、`X-FASC-Nonce`（≤32，10 分钟内不重复）、`X-FASC-AccessToken`、`X-FASC-Api-SubVersion: 5.1` |
| 签名 | 参与签名的头 + `bizContent` 按键 ASCII 升序拼 `k=v&…`（值不编码）→ `signingKey = HMAC-SHA256(AppSecret, Timestamp)` → `Sign = hex(HMAC-SHA256(signingKey, sha256hex(拼接串)))`，小写 |
| Token | `POST /service/get-access-token`，头里用 `X-FASC-Grant-Type: client_credential` 代替 AccessToken；7200 秒，调用任何接口自动续期；按 AppId 缓存 |
| 成功判定 | `code == "100000"`（字符串）。探测：token 无效是 HTTP 401 + `100002`；AppId 无效 / 时间戳过期是 HTTP 200 + `100001` |
| 最容易选错的字段 | `docFileId` 必须是 `/file/process` 返回的 `fileId`，不是上传得到的 `fddFileUrl`；`initiator` / `ownerId` 是 `{"idType","openId"}` 对象，不是字符串 |

## 照通用经验写容易错的地方（来自文档，未实测）

1. **签名不是"用 AppSecret 直接 HMAC 待签名串"。** 要先用时间戳派生临时密钥，再对待签名串的 sha256 hex 做 HMAC。文档正文有一句写得像一步完成（⚠ 与同页伪代码矛盾），官方 SDK 按两步实现；本地测试向量在 auth-and-signing.md §4。
2. **业务参数不是 JSON body。** 是 form-urlencoded 的 `bizContent=<JSON 字符串>`，签名覆盖的必须是和发出去一模一样的那个字符串——先序列化一次，签名和发送共用。
3. **签署任务默认不会开始。** `autoStart` 默认 `false`，创建完停在 `task_created`，谁都收不到签署通知；要么调 `/sign-task/start`，要么创建时 `autoStart: true`——这时必须同时带齐 docs 和有签署权限的 actors，否则创建失败。
4. **发起方不会自动成为签署方。** 发起方（initiator，扣费主体）自己也要盖章时，必须再作为一个 actor 放进 `actors` 并给 `sign` 权限。
5. **文件要"上传 → /file/process"两步才有 fileId。** 本地文件是 `get-upload-url` → PUT 字节 → `process`（fileName 扩展名要与源文件一致）。
6. **撤销、删除、作废按状态区分。** 未提交用 `/sign-task/delete`，进行中用 `/sign-task/cancel`，已完成用 `/sign-task/abolish`（生成需原签署方再签的作废任务）；对未提交任务调 cancel 返回 `211126`。
7. **回调不是 JSON。** 法大大 POST 表单 `bizContent` + 头 `X-FASC-Event`；验签时 `X-FASC-Event` 参与签名、没有 AccessToken / SubVersion；3 秒内必须 HTTP 200 且 body 含 `success`，否则按 3m / 30m / 8h 重试——接收端要幂等。

## 我要做什么 → 读哪一份

| 我要做什么 | 读 | 核心 endpoint |
| --- | --- | --- |
| 换 token、生成 X-FASC-Sign、封装请求（Python / curl / 官方 SDK） | [auth-and-signing.md](references/auth-and-signing.md) | `POST /service/get-access-token` |
| 个人 / 企业认证授权，拿 openUserId / openCorpId，查授权状态 | [identity-authorization.md](references/identity-authorization.md) | `/user/get-auth-url` · `/corp/get-auth-url` · `/user/get` · `/corp/get` |
| 上传合同文件、拿 fileId | [files.md](references/files.md) | `/file/get-upload-url` · `/file/upload-by-url` · `/file/process` |
| 创建 / 提交 / 撤销 / 查询签署任务，参与方签署链接，下载签署文件 | [sign-tasks.md](references/sign-tasks.md) | `/sign-task/create` · `/sign-task/start` · `/sign-task/cancel` · `/sign-task/get-detail` · `/sign-task/actor/get-url` |
| 查询 / 填充模板，基于签署模板发起 | [templates.md](references/templates.md) | `/sign-template/get-list` · `/sign-template/get-detail` · `/doc-template/fill-values` · `/sign-task/create-with-template` |
| 接收回调、验签、事件 ID 对照 | [callbacks.md](references/callbacks.md) | 法大大 POST 到你的回调地址（头 `X-FASC-Event`） |
| 错误码含义、限流、重试策略 | [errors-and-limits.md](references/errors-and-limits.md) | 公共码 `100000`–`100020`、业务码 `21xxxx` |

本 skill 不覆盖：组织管理（部门 / 成员）、印章与个人签名管理、计费、审批、合同起草、合同归档、智能比对、收集表、工具能力服务（要素校验 / OCR / 身份核验）、扫码签、跨应用发收签、第三方应用的应用模板（`/app-template/*`）。
这些接口签名与请求格式相同，文档在 https://dev.fadada.com/api-doc/JW0PWCKYCY/CBKDZOBKIGINHNT2/5-1 （API概览）下的对应目录。

## House rules

- 先在 UAT（`uat-api.fadada.com`）联调，上线再切生产 Base URL；两套环境各自配置 AppId/AppSecret 与 IP 白名单（API 服务端 IP 和回调来源 IP 是两套）。
- 先解析 JSON 再判断：以 `code` 为准（字符串比较），不要只看 HTTP 状态码。**`100001` 要看 msg**：探测到它同时代表"AppId 无效""请求已过期"，这两种重试无效。
- accessToken 按 AppId 缓存；收到 `100002` 重新换一次再重试，不要每个请求都换 token。
- 每个请求现生成 Timestamp（毫秒）和 Nonce；服务器做 NTP 校时。
- 时间字段一律毫秒时间戳字符串；布尔字段按 JSON 布尔传，不要照抄文档示例里的 `"true"`。
- 日志里记下响应头 `X-FASC-Request-Id`，找法大大排查时要用。
- 签署进度以回调（`sign-task-finished` 等）为主、查询接口兜底，不要高频轮询（单接口默认 20 QPS）。
- 编辑链接、模板链接等 EUI 链接**无需登录**就能操作，只发给该操作的人，不要写进日志或公开页面。
- 需要示例代码时，复用 auth-and-signing.md §6 的 `fasc_call` / `fasc_sign`，不要每个接口重写一遍签名。

## 文档自相矛盾 / 未说明之处（⚠ 汇总）

| 位置 | 问题 |
| --- | --- |
| auth-and-signing.md §4 | 签名正文"用 AppSecret 签名"与伪代码 / SDK 的两步派生不一致；"urlencoded"是否编码值 |
| auth-and-signing.md §9 | 错误响应多出文档未写的 `success` 字段（探测证实） |
| errors-and-limits.md §3 | 缺鉴权头实际返回 `100012` 而非表中 `100010`；`100001` 实际在 HTTP 200 下表示多种原因（探测证实） |
| sign-tasks.md §15 | 新版 `/sign-task/get-detail` 与旧版 `/sign-task/app/get-detail` 并存，API概览和官方 Python SDK 仍用旧版 |
| sign-tasks.md §5 | `sendNotification` 默认 true 却"默认仅对抄送方发送通知"；`211132` 与"强烈建议传身份匹配信息"冲突 |
| 多个请求示例 | 布尔写成字符串、数组写成对象、字段放错层级、互斥字段同时出现，与字段表不一致 |
| identity-authorization.md §7 | 授权重定向验签时空值是否参与签名，说法矛盾 |
| callbacks.md §4、§7 | 重试是否复用原时间戳（影响 5 分钟窗口校验）；部分事件字段名大小写 / 拼写不一 |
