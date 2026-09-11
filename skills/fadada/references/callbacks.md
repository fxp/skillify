# 回调事件：接收、验签、事件列表

> 来源：dev.fadada.com FASC OpenAPI 5.1「回调事件」（概要说明、回调事件对接流程、接收事件回调并响应、回调通知安全机制、事件列表-授权 / 签署任务 / 模板相关事件）
> 与「API文档 / 回调管理 / 查询回调列表」，抓取于 2026-09-11。
> **未用真实凭证验证，也没有收到过真实回调**：以下均为文档原文，未实测。签名函数 `fasc_sign` 见 [auth-and-signing.md](auth-and-signing.md)。

## 目录

1. [配置回调地址](#1-配置回调地址)
2. [法大大发来的请求长什么样](#2-法大大发来的请求长什么样)
3. [你必须怎么响应](#3-你必须怎么响应)
4. [验签](#4-验签)
5. [接收端完整示例（Flask）](#5-接收端完整示例flask)
6. [签署任务事件速查](#6-签署任务事件速查)
7. [签署任务事件字段](#7-签署任务事件字段)
8. [授权事件](#8-授权事件)
9. [模板事件](#9-模板事件)
10. [其他事件类别](#10-其他事件类别)
11. [查询回调列表](#11-查询回调列表)
12. [⚠ 汇总](#12--汇总)

---

## 1. 配置回调地址

- 在法大大 SaaS 企业后台「应用配置 - 事件订阅」维护异步通知地址，并**勾选要订阅的业务事件**（对接流程页原文；下载接口页写作「SaaS - 集成 - 事件订阅」）。没勾选的事件不会推送。
- 地址格式 `schema://{host}:{port}/{path}`，**必须公网可访问**，需支持 HTTP POST。
- 单条覆盖：`/sign-task/create`、`/sign-task/create-with-template`、`/sign-task/abolish`、`/user/get-auth-url`、`/corp/get-auth-url` 都支持 `callbackUrl`；
  设置后，该任务 / 该用户授权的事件**只发到这个地址，不再发到应用配置的地址**。
- 某些事件需在事件订阅里单独打开开关，例如批量下载完成事件 `sign-task-download`。
- ⚠ 文档写"通知地址 URL 是 HTTP 协议地址，并且必须支持 HTTPS"，是否允许纯 HTTP 地址说法含糊；按 HTTPS 部署。

## 2. 法大大发来的请求长什么样

- 方法 `POST`，`Content-Type: application/x-www-form-urlencoded`。
- **事件数据在表单字段 `bizContent` 里（JSON 字符串），不是 JSON body**。

| 参数 | 位置 | 说明 |
| --- | --- | --- |
| `X-FASC-App-Id` | header | 你的 AppId |
| `X-FASC-Sign-Type` | header | `HMAC-SHA256` |
| `X-FASC-Sign` | header | 签名值 |
| `X-FASC-Timestamp` | header | 毫秒时间戳 |
| `X-FASC-Nonce` | header | 随机串，≤32 |
| `X-FASC-Event` | header | **事件 ID**，如 `sign-task-finished`、`user-authorize` |
| `bizContent` | body（表单） | 事件内容 JSON 字符串 |

回调请求里**没有** `X-FASC-AccessToken` 和 `X-FASC-Api-SubVersion`。

`bizContent` 示例（个人授权事件，文档原文；注意文档这段 JSON 末尾多了一个逗号，本身不是合法 JSON）：

```json
{"eventTime": "1648174466368", "signature": "xxxx", "openUserId": "xxxx", "authResult": "success",
 "authScope": ["ident_info"], "identMethod": "face", "identProcessStatus": "success"}
```

## 3. 你必须怎么响应

| 规则（文档原文） | 含义 |
| --- | --- |
| 请求超时 3 秒 | 3 秒内没响应就算失败 |
| 返回 HTTP 200 **且 body 中包含 `success`** 才算成功 | 建议 `{"msg":"success"}` |
| 失败按 **3m / 30m / 8h** 重试，中间成功就停止 | 同一事件可能到达多次 |
| 建议收到后**异步**处理业务 | 先落库 / 入队，再慢慢下载文件、改状态 |

所以接收端要**幂等**：用 `(X-FASC-Event, signTaskId, eventTime)` 之类的组合去重（数据库唯一索引 / Redis SETNX）。

## 4. 验签

算法与请求签名完全相同（[auth-and-signing.md §4](auth-and-signing.md#4-签名算法逐步)），只是参与签名的参数换成：

```
X-FASC-App-Id, X-FASC-Event, X-FASC-Nonce, X-FASC-Sign-Type, X-FASC-Timestamp, bizContent
```

按键 ASCII 升序拼接 `k=v&…`，`signingKey = HMAC-SHA256(AppSecret, X-FASC-Timestamp)`，`sign = hex(HMAC-SHA256(signingKey, sha256hex(拼接串)))`，与 `X-FASC-Sign` 比较。

要点：

- `bizContent` 用**收到的原始字符串**参与签名，不要先 `json.loads` 再 `dumps`。
- 用常量时间比较（`hmac.compare_digest`）。
- 顺便校验 `X-FASC-App-Id` 等于你的 AppId。
- 文档 Java 示例在**验签失败时也返回 success**，注释是"为了不重复接收该请求，建议这里返回 success，返回 success 后这条消息法大大将中断重试回调机制"——即：验签失败只记日志告警、不处理业务，但仍回 success。

另一层防护是 **IP 白名单**（文档原文）：

| 环境 | 回调来源公网 IP |
| --- | --- |
| 生产 | 118.89.112.13、115.159.196.132 |
| 测试 | 111.229.217.225、111.231.141.181 |

- ⚠ 文档把请求头表格里的"与当前时间戳正负不能相差 5 分钟"也照抄到了回调头表格。你若在接收端做 5 分钟时间窗校验，而 3m / 30m / 8h 的**重试是否会换新的时间戳**文档没说——
  如果重试沿用首次的时间戳，30 分钟和 8 小时的重试会被你自己拒掉。建议：时间窗只用于告警，或以 nonce 去重代替。

## 5. 接收端完整示例（Flask）

```python
import hmac
import json
import queue
import threading

from flask import Flask, request
from fasc_client import fasc_sign, fasc_call, APP_ID, APP_SECRET

app = Flask(__name__)
jobs: "queue.Queue[tuple[str, dict]]" = queue.Queue()
seen = set()          # 演示用；生产换成数据库唯一索引 / Redis SETNX


def verify(headers, biz: str) -> bool:
    ts = headers.get("X-FASC-Timestamp", "")
    params = {
        "X-FASC-App-Id": headers.get("X-FASC-App-Id", ""),
        "X-FASC-Sign-Type": headers.get("X-FASC-Sign-Type", ""),
        "X-FASC-Timestamp": ts,
        "X-FASC-Nonce": headers.get("X-FASC-Nonce", ""),
        "X-FASC-Event": headers.get("X-FASC-Event", ""),
        "bizContent": biz,
    }
    expected = fasc_sign(params, ts, APP_SECRET)
    return headers.get("X-FASC-App-Id") == APP_ID and hmac.compare_digest(expected, headers.get("X-FASC-Sign", ""))


@app.post("/fadada/callback")
def fadada_callback():
    biz = request.form.get("bizContent", "")          # 表单字段，不是 request.get_json()
    event = request.headers.get("X-FASC-Event", "")
    if not verify(request.headers, biz):
        app.logger.warning("fadada callback bad signature, event=%s", event)
        return {"msg": "success"}                      # 按文档建议：不处理，但回 success 停止重试
    data = json.loads(biz)
    task_id = data.get("signTaskId") or data.get("signtaskId")   # sign-task-pending 用的是小写 t
    key = (event, task_id, data.get("eventTime"))
    if key not in seen:
        seen.add(key)
        jobs.put((event, data))                        # 3 秒内必须响应，重活丢给后台
    return {"msg": "success"}


def worker():
    while True:
        event, data = jobs.get()
        try:
            if event == "sign-task-finished":
                d = fasc_call("/sign-task/owner/get-download-url", {
                    "ownerId": {"idType": "corp", "openId": "<发起方 openCorpId>"},
                    "signTaskId": data["signTaskId"],
                    "downloadMode": "download",
                })
                # requests.get(d["downloadUrl"]) 下载保存，链接 1 小时有效（见 sign-tasks.md §17）
            elif event in ("sign-task-canceled", "sign-task-sign-rejected", "sign-task-fill-rejected", "sign-task-expire"):
                ...   # 标记业务单据失败 / 过期
            elif event in ("user-authorize", "corp-authorize"):
                ...   # 保存 clientXxxId -> openXxxId（见 identity-authorization.md）
        finally:
            jobs.task_done()


threading.Thread(target=worker, daemon=True).start()
```

Flask 返回 dict 时自动序列化为 JSON、状态码 200，body 为 `{"msg": "success"}`，满足"包含 success"。

## 6. 签署任务事件速查

| 事件 ID（`X-FASC-Event`） | 何时触发 | 事件后状态 |
| --- | --- | --- |
| `sign-task-created` | 扫码签生成任务，或用户通过签署编辑 EUI 创建任务 | — |
| `sign-task-start` | 任务提交后 | `fill_progress` / `fill_completed` / `sign_progress` |
| `sign-task-joined` | 参与方加入（自动加入不触发） | 同上 |
| `sign-task-join-failed` | 参与方加入失败（如姓名不匹配） | 同上 |
| `sign-task-actor-removed` | 参与方被解绑 | 同上 |
| `sign-task-member-joined` / `sign-task-member-removed` | 企业参与方成员加入 / 被移出 | 同上 |
| `sign-task-read` | 参与方或抄送方打开阅读 | 当前状态 |
| `sign-task-filled` | 填写方完成填写 | `fill_progress` / `fill_completed` / `sign_progress` |
| `sign-task-fill-rejected` | 填写方拒填 | `task_terminated` |
| `sign-task-ignore` | 手动定稿的任务被驳回填写 | `fill_progress` / `fill_completed` |
| `sign-task-finalize` | 定稿后（**自动定稿不触发**） | `sign_progress` |
| `sign-task-signed` | 每个签署方签署成功 | `sign_progress` / `sign_completed` / `task_finished` |
| `sign-task-sign-failed` | 免验证签或手动签署失败 | `sign_progress` |
| `sign-task-sign-rejected` | 签署方拒签 | `task_terminated` |
| `sign-task-finished` | **任务完成** | `task_finished` |
| `sign-task-canceled` | 任务被撤销 | `task_terminated` |
| `sign-task-expire` | 超过截止时间未完成（**每天凌晨 1 点统一触发**） | `expired` |
| `sign-task-extension` | 任务延期 | 当前状态 |
| `sign-task-abolish` | 作废任务完成，原任务作废 | `revoked` |
| `sign-task-download` | 批量下载打包完成 | — |
| `report-download` | 证据报告生成成功 / 失败 | — |
| `sign-task-pending` | 全网回调：其他企业任务里包含你接收的用户、轮到其待填待签 | — |
| `sign-task-receive-all` | 设置 / 取消接收用户全网回调 | — |

"合同签完了"用 `sign-task-finished`，不要用 `sign-task-signed`（后者每个签署方签完都会来一次）。
`sign-task-expire` 是每天凌晨 1 点批量推，不是到点实时推。

## 7. 签署任务事件字段

所有事件都有 `eventTime`（毫秒时间戳字符串）。大多数签署任务事件还有 `signTaskId`（≤20）、`signTaskStatus`、`transReferenceId`（创建时你传的业务参考号）。

| 事件 | 额外字段 |
| --- | --- |
| `sign-task-created` | `batchId`（扫码签批次号） |
| `sign-task-joined` | `actorId`、`userName` |
| `sign-task-join-failed` | `actorId`、`reason` |
| `sign-task-actor-removed` | `actorId` |
| `sign-task-member-joined` / `-removed` | `actorIInfo[]` → `actorId`、`memberInfo[]`（`memberId`、`userName`、`permission`：`fill`/`sign`/`manage`/`fill_sign`/`view`） |
| `sign-task-read` | `actorId` |
| `sign-task-filled` | `actorId`、`userName`、`memberId` |
| `sign-task-fill-rejected` | `actorId`、`fillRejectReason`、`userName`、`memberId` |
| `sign-task-ignore` | `userName`、`memberId` |
| `sign-task-signed` | `actorId`、`verifyFreeSign`、`userName`（企业免验证签时为空）、`memberId`、`signTaskSubject`、`corpName`、`openCorpId`、`openUserId` |
| `sign-task-sign-failed` | `actorId`、`verifyFreeSign`、`signFailedReason`（如印章未启用、印章未绑定场景码、免验证签授权已过期） |
| `sign-task-sign-rejected` | `actorId`、`signRejectReason`、`userName`、`memberId` |
| `sign-task-canceled` | `userName`（接口撤销时为集成应用名称）、`memberId`、`terminationNote` |
| `sign-task-extension` | `expiresTime`、`userName`、`memberId` |
| `sign-task-abolish` | `abolishedSignTaskId` |
| `sign-task-download` | `downloadId`、`downloadUrl`（zip，1 小时有效）、`status`（`success` / `fail`）——无 signTaskId |
| `report-download` | `reportDownloadId`、`reportType`、`status`（`success` / `failed`）、`failReason` |
| `sign-task-pending` | `signtaskId`（小写 t）、`actorId`、`corpName`、`openCorpId`、`userName`、`openUserId` |
| `sign-task-receive-all` | `corpName`、`openCorpId`、`manageType`（`receive` / `cancel`）、`userName`、`openUserId` |

- ⚠ 文档自相矛盾：`sign-task-pending` 的任务 ID 字段写作 `signtaskId`，其余事件都是 `signTaskId`；解析时两个都兼容。
- ⚠ 疑似笔误：成员加入 / 移出事件的数组字段写作 `actorIInfo`（两个 I），文档未说明是否真实字段名；兼容 `actorIInfo` 与 `actorInfo`。
- ⚠ 同名字段类型不一：`memberId` 在 `sign-task-signed`、`sign-task-sign-rejected` 里标 `long`，在其他事件里标 `string`；按字符串处理，避免大整数精度问题。
- ⚠ `status` 在 `sign-task-download` 是 `fail`，在 `report-download` 是 `failed`。

## 8. 授权事件

| 事件 ID | 触发 | 主要字段 |
| --- | --- | --- |
| `user-authorize` | 个人授权允许、不允许或身份信息匹配失败 | `clientUserId`、`openUserId`、`existClientUserId`、`existOpenUserId`、`authResult`、`authFailedReason`（`exist`）、`verifyStatus`（`verifying` 人工审核中）、`authScope[]`、`identProcessStatus`（`failed`/`success`/`no_start`）、`identFailedReason`、`identMethod`、`availableStatus`、`userName`、`identNo`（后两者需 `ident_info` 授权） |
| `corp-authorize` | 企业授权允许后 | `clientCorpId`、`openCorpId`、`existClientCorpId`、`existOpenCorpId`、`clientUserIds[]`、`memberId`、`authResult`、`authFailedReason`（`reject`/`exist`）、`verifyStatus`、`authScope[]`、`corpIdentProcessStatus`、`corpIdentFailedReason`、`corpIdentMethod`、`availableStatus`、`corpName`、`corpIdentNo` |
| `user-cancel-authorization` | 个人取消授权 | `clientUserId`、`openUserId` |
| `corp-cancel-authorization` | 企业取消授权 | `clientCorpId`、`openCorpId` |
| `app-develop` | 企业新增 / 取消委托代开发 | `clientCorpId`、`openCorpId`、`appId`、`appAuthCode`、`status`、`appStatus`、`failedReason`、`type` |

处理建议见 [identity-authorization.md](identity-authorization.md) §11：`authFailedReason=exist` 时用 `existOpenUserId` / `existOpenCorpId` 关联已有记录。
⚠ `user-authorize` 的 `existOpenUserId` 说明里写"之前授权时产生的 openCorpId"，疑似笔误。

## 9. 模板事件

| 事件 ID | 触发 |
| --- | --- |
| `template-creating` | EUI 创建模板草稿或复制新增模板 |
| `template-create` | EUI 创建模板完成 |
| `template-enable` | 启用模板；编辑模板并提交也会触发 |
| `template-disable` | 停用模板 |
| `template-delete` | 删除模板 |

字段：`eventTime`、`openCorpId`（应用级模板为空）、`templateId`、`type`（`doc` / `sign`）、`createSerialNo`（仅 creating / create）、`clientCorpId`。详见 [templates.md](templates.md) §11。

## 10. 其他事件类别

文档「回调事件 / 事件列表」还有：部门、成员、成员企业、印章、签名、审批、计费、信息比对、身份核验、合同起草、合同归档、收集表、文件相关事件。
验签和响应规则与上面完全相同，字段表本 skill 未收录。

## 11. 查询回调列表

**Endpoint**: `POST /callback/get-list`

**用途**: 查询指定时间段内某类回调的推送记录（含是否发送成功）。**目前只支持审批类回调**，不能用来补拉签署任务事件。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `callbackType` | string | 是 | 目前只有 `approval` |
| `startTime` | string | 是 | 毫秒时间戳，范围最长 3 个月 |
| `endTime` | string | 是 | 毫秒时间戳，超过当前时间以服务器时间为准 |
| `listPageNo` / `listPageSize` | int | 否 | 默认 100，最大 100 |

响应：`callbackInfos[]`（`eventId`：`approval-create` / `approval-change`；`eventInfo`：回调内容 JSON 字符串；`success`：是否发送成功）+ 分页字段。

```bash
fasc_call /callback/get-list '{"callbackType":"approval","startTime":"1685779302000","endTime":"1686645975188","listPageNo":1,"listPageSize":10}'
```

签署任务事件漏收时，只能用 `/sign-task/get-detail` 或 `/sign-task/owner/get-list` 主动查询补偿。

## 12. ⚠ 汇总

- 回调地址是否允许 HTTP（§1）。
- 重试是否复用原时间戳，影响 5 分钟窗口校验（§4）。
- `bizContent` 示例 JSON 末尾多逗号（§2）。
- `signtaskId` / `signTaskId` 大小写、`actorIInfo` 疑似笔误、`memberId` 类型不一、`fail` / `failed` 不一（§7）。
- `existOpenUserId` 说明笔误（§8）。
