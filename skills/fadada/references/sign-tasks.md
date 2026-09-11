# 签署任务：创建、添加文档与参与方、提交、撤销、查询

> 来源：dev.fadada.com FASC OpenAPI 5.1「API文档 / 签署任务」（概述、签署任务创建、参与方签署、签署任务查询、签署任务控制）、
> 「附录 / 常用数据结构」（Actor、Field、FieldPosition、OpenId）、「附录 / 基本概念」「错误码说明」，抓取于 2026-09-11。
> **未用真实凭证验证**：报错与行为描述均为文档原文，未实测。请求封装 `fasc_call` 见 [auth-and-signing.md](auth-and-signing.md)，文件上传见 [files.md](files.md)。

## 目录

1. [核心概念与状态机](#1-核心概念与状态机)
2. [选哪种创建方式](#2-选哪种创建方式)
3. [最小可用流程（Python）](#3-最小可用流程python)
4. [创建签署任务（基于文档）](#4-创建签署任务基于文档)
5. [Actor 参与方对象](#5-actor-参与方对象)
6. [控件 Field / FieldPosition（精简）](#6-控件-field--fieldposition精简)
7. [分步组装：添加签署任务文档](#7-分步组装添加签署任务文档)
8. [分步组装：添加签署任务参与方](#8-分步组装添加签署任务参与方)
9. [提交签署任务](#9-提交签署任务)
10. [获取签署任务编辑链接](#10-获取签署任务编辑链接)
11. [获取参与方签署链接](#11-获取参与方签署链接)
12. [定稿与结束](#12-定稿与结束)
13. [催办](#13-催办)
14. [撤销、删除、作废怎么选](#14-撤销删除作废怎么选)
15. [查询签署任务详情](#15-查询签署任务详情)
16. [查询签署任务列表](#16-查询签署任务列表)
17. [下载签署文档](#17-下载签署文档)
18. [查询签署完成的文件](#18-查询签署完成的文件)
19. [链接与时效汇总](#19-链接与时效汇总)
20. [常见错误码](#20-常见错误码)
21. [本文未展开的签署任务接口](#21-本文未展开的签署任务接口)
22. [⚠ 汇总](#22--汇总)

---

## 1. 核心概念与状态机

- **签署任务（SignTask）**：一次签署协作流程的容器，包含待签文档、附件、控件、参与方和流程参数。
- **发起方（initiator）**：一个任务只有一个，是**扣费主体**，拥有编辑、添加参与方、定稿、撤销等控制权。
  **发起方自己也要填写或签署时，必须再作为参与方加进 `actors`**（文档"特别注意"原文）。
- **参与方（actor）**：个人或企业，权限 `fill` 填写 / `sign` 签署 / `cc` 抄送（Actor 数据结构页还列了 `operator_sign` 仅经办人签字）。
- **控件（field）**：文档上的可变区域——填写控件（文本、日期、勾选…）和签章控件（个人签名、企业印章、骑缝章、日期戳…）。

| 状态 `signTaskStatus` | 含义 | 怎么进入 | 下一步 |
| --- | --- | --- | --- |
| `task_created` | 创建中，未提交 | 创建时 `autoStart=false`（默认） | `/sign-task/start` 提交；或 `/sign-task/delete` 删除 |
| `finish_creation` | 已创建，审批中 | 关联了发起审批流程 | 等审批 |
| `fill_progress` | 填写中 | 提交后存在填写方 | 填写方填写 |
| `fill_completed` | 填写已完成、未定稿 | `autoFillFinalize=false` 且必填控件都填完 | `/sign-task/doc-finalize` |
| `sign_progress` | 签署中 | 提交 / 定稿后 | 签署方签署 |
| `sign_completed` | 所有签署方已签 | — | `autoFinish=true`（默认）自动结束；否则 `/sign-task/finish` |
| `task_finished` | 任务已成功结束 | — | 下载文件；需要解除时 `/sign-task/abolish` |
| `task_terminated` | 异常停止 | 拒填、拒签、撤销 | — |
| `expired` | 已逾期 | 超过 `expiresTime` | — |
| `abolishing` | 作废中 | 发起作废后 | 作废任务签完 → `revoked` |
| `revoked` | 已作废 | — | — |

⚠ 「签署任务 / 概述」页的状态列表没有 `finish_creation`，详情和列表接口的字段表有；以接口字段表为准。

## 2. 选哪种创建方式

| 方式 | 适用 | 调用 |
| --- | --- | --- |
| A. 一次性创建（文档推荐） | 文档、参与方、控件位置都能在代码里确定 | `/sign-task/create` 带 `docs` + `actors`，`autoStart: true` |
| B. 创建 + 编辑页面（文档推荐） | 控件位置需要人在页面上拖 | `/sign-task/create`（`autoStart: false`）→ `/sign-task/get-edit-url` → 发起方在页面上完成并提交 |
| C. 空任务逐步添加（文档："非特殊情况不推荐"） | 文档或参与方要分几次确定 | `/sign-task/create` → `/sign-task/doc/add` → `/sign-task/actor/add` → `/sign-task/start` |
| D. 基于签署模板 | 固定格式合同 | `/sign-task/create-with-template`，见 [templates.md](templates.md) |

## 3. 最小可用流程（Python）

企业（本应用所属企业，默认已授权）发起，企业先盖章、个人后签字，拿到两个签署链接自行分发：

```python
import os, time
from fasc_client import fasc_call
from files_helper import upload_local_file      # files.md §8

OPEN_CORP_ID = os.environ["FASC_OPEN_CORP_ID"]  # 本企业在应用下的 openCorpId（SaaS「集成-应用详情」顶部）

file_id = upload_local_file("劳动合同.pdf")      # 必须是 /file/process 返回的 fileId

task = fasc_call("/sign-task/create", {
    "initiator": {"idType": "corp", "openId": OPEN_CORP_ID},
    "signTaskSubject": "劳动合同-张三",
    "expiresTime": str(int(time.time() * 1000) + 7 * 24 * 3600 * 1000),
    "autoStart": True,              # 默认 false；true 时必须带齐 docs 和签署方
    "signInOrder": True,
    "transReferenceId": "HR-2026-0001",
    "docs": [{
        "docId": "doc1", "docName": "劳动合同", "docFileId": file_id,
        "docFields": [
            {"fieldId": "seal_a", "fieldName": "甲方盖章", "fieldType": "corp_seal",
             "position": {"positionMode": "keyword", "positionKeyword": "甲方（盖章）"}},
            {"fieldId": "sign_b", "fieldName": "乙方签字", "fieldType": "person_sign",
             "position": {"positionMode": "keyword", "positionKeyword": "乙方（签字）"}},
        ],
    }],
    "actors": [
        {   # 发起方自己也要盖章 -> 必须作为参与方加入
            "actor": {"actorId": "甲方", "actorType": "corp", "actorName": "示例科技有限公司",
                      "permissions": ["sign"], "actorOpenId": OPEN_CORP_ID},
            "signFields": [{"fieldDocId": "doc1", "fieldId": "seal_a"}],
            "signConfigInfo": {"orderNo": 1},
        },
        {   # 非应用用户的个人：不传 actorOpenId，用身份信息约束谁能签
            "actor": {"actorId": "乙方", "actorType": "person", "actorName": "张三",
                      "permissions": ["sign"],
                      "identNameForMatch": "张三", "accountName": "13800000000"},
            "signFields": [{"fieldDocId": "doc1", "fieldId": "sign_b"}],
            "signConfigInfo": {"orderNo": 2, "verifyMethods": ["sms", "face"]},
        },
    ],
})
sign_task_id = task["signTaskId"]

for actor_id in ("甲方", "乙方"):
    urls = fasc_call("/sign-task/actor/get-url", {"signTaskId": sign_task_id, "actorId": actor_id})
    print(actor_id, urls["actorSignTaskUrl"])
```

之后等回调 `sign-task-finished`（[callbacks.md](callbacks.md)），再用 §17 下载。

## 4. 创建签署任务（基于文档）

**Endpoint**: `POST /sign-task/create`

**用途**: 用即时文档（fileId）或文档模板（docTemplateId）创建签署任务；可以一次带齐所有要素，也可以只建空任务。
**授权要求**: 发起方需授权 `signtask_init`（集成应用所属企业默认已授权）。

**关键参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `initiator` | OpenId 对象 | 是 | — | 发起方（扣费主体）`{"idType","openId"}`，需检查授权 |
| `initiatorMemberId` | string | 否 | — | 发起方企业成员（任务创建者）；不传表示由 AppId 创建。传了才会触发审批流程、自动归档 |
| `initiatorEntityId` | string | 否 | 主企业 | 一个企业帐号下有多个主体时指定 |
| `signTaskSubject` | string | 是 | — | 任务主题，≤200，会醒目展示给所有参与方 |
| `signDocType` | string | 否 | `contract` | `contract` 合同 / `document` 单据（只能有一个签署方）/ `credit_auth` 征信授权书 / `legal_letter` 律师函 |
| `expiresTime` | string | 否 | 不过期 | 截止时间，毫秒时间戳；到期未完成逾期作废 |
| `dueDate` | string | 否 | — | 合同到期日（毫秒），需大于任务过期当天，用于归档与履约提醒 |
| `autoStart` | boolean | 否 | **false** | 是否创建即提交。true 时"必须设置相关文档、参与方等必要信息"，不满足提交条件则创建失败 |
| `autoFillFinalize` | boolean | 否 | true | 有填写方时，填完是否自动定稿进入签署 |
| `autoFinish` | boolean | 否 | true | 全部签完是否自动结束 |
| `signInOrder` | boolean | 否 | false | 是否有序签署；true 时每个签署方都要 `signConfigInfo.orderNo` |
| `businessId` | string | 否 | — | 免验证签场景码（已审核通过），≤32 |
| `transReferenceId` | string | 否 | — | 你的业务参考号（如订单号），≤128，回调里会带回 |
| `callbackUrl` | string | 否 | — | 本任务专用回调地址，设置后本任务的回调不再发到应用配置的地址 |
| `catalogId` | string | 否 | — | 发起方 SaaS 文件夹 |
| `businessTypeId` / `businessCode` | long / string | 否 | — | 业务类型与编号 |
| `startApprovalFlowId` / `finalizeApprovalFlowId` | string | 否 | — | 发起 / 定稿审批流程（需同时传 `initiatorMemberId`） |
| `fileFormat` | string | 否 | `pdf` | `pdf` / `ofd` |
| `offerCopies` | string | 否 | true | 签完是否给参与方提供文件副本 |
| `useFda` | boolean | 否 | false | 签名是否使用 FDA 规范 |
| `docs` | Doc[] | 否 | — | 待签文档，≤50 份，顺序即展示顺序 |
| `docs[].docId` | string | 是 | — | 你自定义的文档标识，任务内唯一，≤64 |
| `docs[].docName` | string | 是 | — | 文档名，≤200，不能含特殊字符 |
| `docs[].docFileId` | string | 二选一 | — | `/file/process` 返回的 fileId，≤32 |
| `docs[].docTemplateId` | string | 二选一 | — | 文档模板 ID。与 `docFileId` **只能有一个且必须有一个** |
| `docs[].docFields` | Field[] | 否 | — | 在文档上添加控件，见 §6 |
| `attachs` | Attach[] | 否 | — | 附件，≤50；`attachId`（任务内唯一 ≤64）、`attachName`、`attachFileId`（均必填） |
| `actors` | SignTaskActor[] | 否 | — | 参与方列表，见下表与 §5 |
| `watermarks` | array | 否 | — | 水印，≤5 条（`type` text/picture、`content`、`position` 等） |

`actors[]` 每一项：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `actor` | Actor | 是 | 参与方基本信息，见 §5；支持抄送方 |
| `fillFields[]` | array | 否 | 填写方关联的填写控件：`fieldDocId`（必填）、`fieldId` 或 `fieldName`、`fieldValue`（缺省填充值，参与方可改） |
| `signFields[]` | array | 否 | 签署方关联的签章控件：`fieldDocId`（必填）、`fieldId` 或 `fieldName`（不能同时为空）、`sealId`（指定印章/签名 ID）。不设置则可在任意位置盖章 |
| `signConfigInfo` | object | 否 | 签署配置（仅签署权限参与方），见下表 |

`signConfigInfo` 常用字段：

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `orderNo` | int | — | 签署序号，`signInOrder=true` 时必传，从小到大 |
| `verifyMethods` | string[] | 除互动视频外都支持 | 意愿确认：`pw` 签署密码 / `sms` 短信 / `face` 刷脸 / `audio_video` 互动视频签（需订购） |
| `requestVerifyFree` | boolean | false | 免验证签（自动盖章），**必须同时传任务级 `businessId`**；未授权会转为手动签署 |
| `requestMemberSign` | boolean | false | 企业签署是否要求经办人也签名 |
| `signerSignMethod` | string | `unlimited` | `unlimited` / `standard` / `hand_write` / `ai_hand_write` |
| `blockHere` | boolean | false | 阻塞：暂不通知该参与方、流程暂停，需 `/sign-task/unblock` 解阻 |
| `joinByLink` | boolean | true | 企业任意成员可通过链接打开；false 时必须设置 `actorCorpMembers` |
| `readingToEnd` / `readingTime` | boolean / string | false / — | 需读到末页 / 最少阅读秒数（3–300） |
| `freeLogin` | boolean | false | 个人快捷签（跳过登录页）；文档建议有手机号时 `freeLogin=true`、`identifiedView=false`、`accountName=手机号` |
| `identifiedView` | boolean | true | 个人必须实名后才能查看 |
| `freeDragSealId` / `signAllDoc` / `resizeSeal` | — | — | 仅参与方未关联任何签章控件时有效 |
| `authorizeFreeSign` | boolean | false | 个人签署时顺便授权免验证签，需 `businessId` |
| `ageRequirement` | string | 无要求 | `no_requirement` / `above_eighteen` / `above_sixteen` |
| `actorAttachInfos[]` | array | — | 要求参与方上传的附件（`actorAttachName` ≤20、`required`），每方 ≤50 |

**示例请求**：见 §3。

```bash
fasc_call /sign-task/create '{"initiator":{"idType":"corp","openId":"'"$OPEN_CORP_ID"'"},"signTaskSubject":"测试合同","autoStart":false}'
```

**示例响应**：`{"code":"100000","msg":"请求成功","data":{"signTaskId":"1677137745347153488"}}`（`signTaskId` ≤20 字符）

**注意事项**

- 未设置 `autoStart` → 任务停在 `task_created`，**必须再调 `/sign-task/start`** 才会流转、才会通知参与方。
- `autoStart=true` 但缺文档 / 缺签署方 → 创建失败（`211145`、`211146`、`211161`，文档原文）。
- 设置 `autoFillFinalize=false` → 填完停在 `fill_completed`，要调 `/sign-task/doc-finalize`。
- 布尔字段传 JSON 布尔。⚠ 文档请求示例里写成 `"autoStart": "true"`、`"sendNotification": "false"` 等字符串，与字段表类型不一致，字符串是否被接受未验证。
- ⚠ 文档请求示例里有字段表没有的 `certCAOrg`（任务详情响应里有此字段），创建时是否可传未说明。

## 5. Actor 参与方对象

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `actorId` | string | 是 | 参与方标识，任务内唯一，≤32，如"甲方""借款人" |
| `actorType` | string | 是 | `corp` / `person` |
| `actorName` | string | 是 | 参与方名称，≤128 |
| `permissions` | string[] | 是 | `fill` / `sign` / `cc`（/ `operator_sign`）；`sign`、`operator_sign`、`cc` 不可同时传 |
| `actorOpenId` | string | 否 | 应用用户的 openCorpId / openUserId；非应用用户不传，他们用法大大外部链接签署 |
| `actorFDDId` | string | 否 | 法大大号；与 actorOpenId 同时传会校验一致性 |
| `actorEntityId` | string | 否 | 指定企业帐号下的具体主体 |
| `actorCorpMembers[]` | array | 否 | 指定企业经办成员（`memberId` 或 `accountName`），必须同时指定 actorOpenId 或 actorFDDId，成员须已激活 |
| `identNameForMatch` | string | 否 | 身份名称（姓名 / 企业全称），访问时校验，≤100；传了 actorOpenId/actorFDDId 时被忽略 |
| `certType` / `certNoForMatch` | string | 否 | 个人证件类型 / 证件号（或企业统信码 ≤32），访问时校验；传了 openId/FDDId 时被忽略 |
| `accountName` | string | 否 | 个人参与方的法大大帐号（手机号 / 邮箱）；指定后只有该帐号能加入 |
| `accountEditable` | boolean | 否 | true 时即使传了 accountName 也走二要素快捷签，默认 false |
| `clientUserId` | string | 否 | 签署过程中顺便做个人授权 / 免验证签授权时使用 |
| `authScopes` | array | 否 | 配合 clientUserId 的个人授权范围 |
| `sendNotification` | boolean | 否 | 是否由法大大发通知，默认 true |
| `notifyType` | array | 否 | `start` 待填待签通知 / `finish` 签署完成通知 / `cc` 抄送通知 |
| `notifyAddress` | string | 否 | 手机或邮箱 ≤64；个人已传 openId、FDDId 或 accountName 时被忽略 |
| `sendInSiteMessage` | boolean | 否 | 站内信，默认 true |

- 身份约束："如需签署人与指定信息一致，强烈建议传" `identNameForMatch` / `certNoForMatch`（文档原文）。
- ⚠ 文档自相矛盾：错误码 `211132`「签署任务应用外的个人参与方不能指定相对方个人隐私相关的身份匹配信息」与上面的"强烈建议传"冲突，触发条件文档未说明；遇到 211132 先去掉 `certNoForMatch` 再试。
- ⚠ 文档未说明：`sendNotification` 默认 true，但说明写"可在 notifyType 中指定发送哪些通知，**默认仅对抄送方发送抄送通知**"——签署方是否默认收到待签短信需实测。要法大大通知签署方，就显式传 `notifyType: ["start"]`；自己分发链接就传 `sendNotification: false`。

## 6. 控件 Field / FieldPosition（精简）

完整属性表在官网「附录 / 常用数据结构 / Field」。

| Field 字段 | 必填 | 说明 |
| --- | --- | --- |
| `fieldId` | 是 | 控件编码，文档内唯一（所有类型共享），≤32 |
| `fieldName` | 是 | 控件名称，可重名，≤32 |
| `fieldKey` | 否 | 控件标识 |
| `position` | 是 | FieldPosition |
| `fieldType` | 是 | 签章类：`person_sign` / `corp_seal` / `corp_seal_cross_page`（骑缝章）/ `date_sign` / `remark_sign`；填写类：`text_single_line` / `text_multi_line` / `number` / `id_card` / `fill_date` / `multi_radio` / `multi_checkbox` / `picture` / `select_box` / `table` / `verification_code` / `business_code` |
| `moveable` | 否 | 签署时签章控件能否拖动，默认 false |
| `fieldCorpSeal` / `fieldPersonSign` / `fieldTextSingleLine` / … | 否 | 各类型属性子对象（宽高、字体、`required`、`defaultValue`、`categoryType` 印章类型等） |

| FieldPosition 字段 | 说明 |
| --- | --- |
| `positionMode` | `pixel` 坐标 / `keyword` 关键字（必填） |
| `positionPageNo` | 页码，从 1 开始（骑缝章无效）；pixel 非骑缝章时必填 |
| `positionX` / `positionY` | 控件**中心点**坐标（数字字符串）；骑缝章只需 Y |
| `positionKeyword` | 关键字 ≤50；匹配多处时自动生成 `fieldId_1`、`fieldId_2`…；要关联全部位置用 `fieldName` 关联 |
| `keywordOffsetX` / `keywordOffsetY` | 偏移，正数向右 / 向下 |

- `multi_radio`、`multi_checkbox` 不支持接口新增，只能在编辑页面添加（文档原文）。
- 个人签署方只能用个人签章类控件，企业签署方要用企业章类控件（`211027`、`211028`、`211039`）。
- 坐标算法见官网「附录 / 文档页面坐标定位计算方法」；或先用 `/file/get-keyword-positions` 查关键字坐标。

## 7. 分步组装：添加签署任务文档

**Endpoint**: `POST /sign-task/doc/add`

**用途**: 在**提交之前**向任务追加文档（fileId 或文档模板），可同时设置控件。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `signTaskId` | string | 是 | 任务 ID |
| `docs[]` | array | 是 | 同 §4 的 Doc：`docId`、`docName`、`docFileId`/`docTemplateId` 二选一、`docFields` |

```bash
fasc_call /sign-task/doc/add '{"signTaskId":"1656656963244180430","docs":[{"docId":"doc2","docName":"补充协议","docFileId":"18438605689"}]}'
```

响应：`{"code":"100000","msg":"请求成功"}`

- 任务内文档总数 ≤50（`211072`）；`docId` 不能重复（`211073`）；非创建状态不能加（`211055`）。
- ⚠ 文档请求示例同时给了 `docFileId` 和 `docTemplateId`，违反"只能有一个"（会触发 `211100`）；只传一个。

## 8. 分步组装：添加签署任务参与方

**Endpoint**: `POST /sign-task/actor/add`

**用途**: 在**任务完成之前**追加参与方，并关联已存在的控件。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `signTaskId` | string | 是 | 任务 ID |
| `actors[]` | array | 是 | 同 §4 的 SignTaskActor；`signFields[]` 额外支持 `moveable` |

- 必须指定 `actorId`、`actorType`、`actorName`、`permissions`；`actorId` 不能与已有参与方重复。
- 关联的控件、文档必须已经存在于任务中，本接口不能新增文档或控件。
- 用在线编辑模板创建的任务，只能在定稿后、结束前调用（文档原文）。

```python
fasc_call("/sign-task/actor/add", {
    "signTaskId": sign_task_id,
    "actors": [{"actor": {"actorId": "丙方", "actorType": "person", "actorName": "李四",
                          "permissions": ["cc"], "accountName": "13900000000"}}],
})
```

## 9. 提交签署任务

**Endpoint**: `POST /sign-task/start`

**用途**: 提交 `task_created` 状态的任务，让流程开始运转（仅在创建时没有 `autoStart` 时调用）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `signTaskId` | string | 是 | 任务 ID |

提交前置条件（文档原文）：

1. 文档、签署权限的参与方不能为空；
2. 文档中的必填控件若未绑定参与方，必须已填充默认值；签章控件必须绑定参与方；
3. 填写权限的参与方必须关联填写控件；
4. 企业参与方要求骑缝章、签署日期、签名控件时，必须为其添加签章控件；
5. 个人参与方要求签署日期时，必须为其添加签名控件。

```bash
fasc_call /sign-task/start '{"signTaskId":"1656657193146145802"}'
```

提交后会触发 `sign-task-start` 回调。

## 10. 获取签署任务编辑链接

**Endpoint**: `POST /sign-task/get-edit-url`

**用途**: 返回一个 EUI 页面，PC 端可设置文档、附件、控件、参与方并直接提交；H5 端只能给参与方加签章控件。也可以不传 signTaskId、在页面里新建任务。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `signTaskId` | string | 二选一 | 已有任务；与 `initiator` 不可同时存在、不可同时为空 |
| `initiator` | OpenId 对象 | 二选一 | 不传 signTaskId 时必传，以该主体为发起方新建（需 `signtask_init`） |
| `createMethods` | array | 否 | 新建方式：`signTemplate` / `doc` |
| `nonEditableInfo` | array | 否 | 不可编辑项：`basicInfo` / `docs` / `attachs` / `actors` / `taskConfig` / `fields` / `existingContent` / `sealAttributes` |
| `showCategoryTypes` | array | 否 | 印章控件可选印章类型 |
| `redirectUrl` / `redirectMiniAppUrl` | string | 否 | 需 URL 编码 |
| `editAfterStart` | boolean | 否 | 提交后打开是否仍可编辑（可继续加参与方和控件），默认 false 仅预览 |

响应：`data.signTaskEditUrl`，**2 小时、1 次有效**（SaaS 可配置最长 30 天）。
链接**无需用户登录**，只发给发起方的操作人。

## 11. 获取参与方签署链接

**Endpoint**: `POST /sign-task/actor/get-url`

**用途**: 任务**提交后**获取某个参与方的签署链接，自行分发（由法大大通知的场景不必调用）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `signTaskId` | string | 是 | 任务 ID |
| `actorId` | string | 是 | 参与方标识（创建时自定义的那个，不是 openId） |
| `clientUserId` | string | 否 | 仅对长链接生效：建立你的用户与法大大帐号的免登映射；无需提前授权 |
| `redirectUrl` | string | 否 | 签完跳转地址，≤500，需 URL 编码 |
| `redirectMiniAppUrl` | string | 否 | 小程序路径 |

**示例响应字段**

| 字段 | 说明 |
| --- | --- |
| `actorSignTaskUrl` | 短链接，**一年有效**，自适应 PC/H5；需参与方用自己的法大大帐号登录 |
| `actorSignTaskEmbedUrl` | 长链接，**10 分钟、1 次有效**（SaaS 可配最长 30 天），可嵌入小程序 / iframe；无需解码 |
| `actorSignTaskMiniAppInfo` | `wxOriginalId`、`path`：在你的 App 里唤起法大大签署小程序 |

```python
urls = fasc_call("/sign-task/actor/get-url", {"signTaskId": sign_task_id, "actorId": "乙方"})
short_link = urls["actorSignTaskUrl"]          # 发短信 / 邮件用这个
embed_link = urls["actorSignTaskEmbedUrl"]     # 页面内嵌用这个，现取现用
```

- 在 `task_created` 状态调用：文档只说"在签署任务提交后"获取，⚠ 提交前调用返回什么未说明。

## 12. 定稿与结束

**Endpoint**: `POST /sign-task/doc-finalize` —— `autoFillFinalize=false` 的任务在 `fill_completed` 时调用，定稿后进入签署，文档不能再改。参数：`signTaskId`。非填写完成状态调用 → `211125`。

**Endpoint**: `POST /sign-task/finish` —— `autoFinish=false` 的任务在所有签署方签完后调用，驱动任务结束、生成完结合同。参数：`signTaskId`。

```bash
fasc_call /sign-task/doc-finalize '{"signTaskId":"1656928831553122296"}'
fasc_call /sign-task/finish '{"signTaskId":"1656928831553122296"}'
```

## 13. 催办

**Endpoint**: `POST /sign-task/urge`

**用途**: 给待填写 / 待签署的参与方发短信 / 邮件提醒。参数：`signTaskId`。

限制（文档原文）：每天最多催 2 次、每次间隔至少 2 小时；未指定通知对象或被阻塞的参与方无法催办；还没轮到的参与方会提示未轮到。

## 14. 撤销、删除、作废怎么选

| 任务所处状态 | 用哪个接口 | 效果 |
| --- | --- | --- |
| `task_created`（未提交） | `POST /sign-task/delete`（参数 `signTaskId`） | 删除；只能删"创建中"且属于本应用创建的任务 |
| 已提交未结束（`fill_*` / `sign_*`） | `POST /sign-task/cancel` | 撤销，流程终止 → `task_terminated`，触发 `sign-task-canceled` |
| `task_finished`（已完成） | `POST /sign-task/abolish` | 发起**作废任务**：原签署方签完解除协议后，原任务 → `revoked` |

`211126 当前签署任务状态不允许撤销`：不允许撤销的状态为已创建、任务已结束、任务已撤销、任务终止（文档原文）。

### 撤销签署任务

**Endpoint**: `POST /sign-task/cancel`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `signTaskId` | string | 是 | 任务 ID |
| `terminationNote` | string | 否 | 撤销原因，≤250 |

```bash
fasc_call /sign-task/cancel '{"signTaskId":"1656928831553122296","terminationNote":"信息填写错误"}'
```

### 作废签署任务

**Endpoint**: `POST /sign-task/abolish`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `signTaskId` | string | 是 | **已完成**的原任务 ID |
| `abolishedInitiator` | object | 是 | 作废发起方，`initiatorId`（原发起方）或 `actorId`（原签署方）二选一；都传优先发起方；需 `signtask_init` 授权 |
| `docSource` | string | 否 | `platform`（默认，用法大大解除协议模板，此时 `reason` 必填）/ `selfUpload`（自传协议，`docs` 必填） |
| `reason` | string | 条件必填 | 作废原因，≤200 |
| `autoStart` | boolean | 否 | 默认 false，同创建任务 |
| `followOriginalConfig` | boolean | 否 | 签署配置是否跟随原任务，默认 false |
| `actors` / `docs` / `signInOrder` / `signTaskSubject`（默认"原主题-解除协议"，≤100） / `callbackUrl` … | | 否 | 签署方只能是原任务的签署方 |

响应：`data.abolishedSignTaskId`（作废任务的 ID）。原签署方默认不发短信，需要通知时设置 `sendNotification`、`notifyType`。
完成后触发 `sign-task-abolish`（原任务状态 `revoked`）。

## 15. 查询签署任务详情

**Endpoint**: `POST /sign-task/get-detail`（新版）

**用途**: 查任务基本信息和状态；可附带文档、附件、水印、节点信息。
**授权要求**: `signtask_info`。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `signTaskId` | string | 是 | 任务 ID |
| `filter` | array | 否 | 额外返回：`doc` / `attach` / `watermark` / `signTaskNode`；默认只有基础信息 |

主要响应字段：`signTaskId`、`signTaskSubject`、`signTaskStatus`（枚举见 §1）、`signDocType`、`cancelStatus`、`faultStatus`、`terminationNote`、`createTime`、`startTime`、`finishTime`、`deadlineTime`、
`signTaskSource`（`fdd` / `api`）、`templateId`、`autoFillFinalize`、`autoFinish`、`signInOrder`、`transReferenceId`、`initiator`（`idType`、`ownerId`）、`initiatorMemberId`、
`docs[]`（`docId`、`docName`、`docFileId` = 原始底稿）、`attachs[]`、`watermarks[]`、`signTaskNodes[]`（节点名、顺序、类型、控件、参与方）、`abolishedSignTaskId`、`originalSignTaskId`。

```python
d = fasc_call("/sign-task/get-detail", {"signTaskId": sign_task_id, "filter": ["doc"]})
print(d["signTaskStatus"])
```

- ⚠ **两个详情接口并存**：新版 `/sign-task/get-detail`（详情页、常用接口清单）；旧版 `/sign-task/app/get-detail`（文档标"旧版不推荐"，说明写"以及各参与方的专属链接"）。
  「API概览」表格和官方 Python SDK 的常量仍是旧版路径。新代码用新版；无凭证探测两个路径都返回 `100002`，现状待真实凭证确认。
- ⚠ `cancelStatus`、`faultStatus` 字段表类型写 boolean，说明写"1-已撤销，0-未撤销"，取值类型不确定，按真值判断。
- 详情响应里**没有**参与方签署链接字段（新版）；要链接用 §11。参与方明细用 `/sign-task/actor/list`（本文未展开）。

## 16. 查询签署任务列表

**Endpoint**: `POST /sign-task/owner/get-list`

**用途**: 查某个主体（作为发起方或参与方）的签署任务。**授权要求**: `signtask_info`。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `ownerId` | OpenId 对象 | 是 | 查询哪个主体 |
| `ownerRole` | string | 否 | `initiator` / `actor`；不传查全部。与 `pendingRole` 不能同时传 |
| `pendingRole` | string | 否 | `owner` 待我处理 / `other` 待他方处理 |
| `memberId` | string | 否 | 企业主体下按成员过滤 |
| `catalogId` | string | 否 | 文件夹 |
| `listFilter` | object | 否 | 多条件"并且"：`signTaskId`、`signTaskSubject`（模糊）、`actorInfo`（模糊）、`signTaskStatus`（**数组**）、`startTimeFrom/To`、`finishTimeFrom/To`、`expiresTimeFrom/To`（成对出现，毫秒）、`businessTypeId`、`businessCode` |
| `listPageNo` | int | 否 | 页码，**从 1 开始** |
| `listPageSize` | int | 否 | 默认 100，最大 100 |

响应：`signTasks[]`（`signTaskId`、`signTaskSubject`、`signTaskStatus`、`initiatorName`、`createTime`、`finishTime`、`transReferenceId`、`actorResults[]`…）、`listPageNo`、`countInPage`、`listPageCount`、`totalCount`。

```python
page = fasc_call("/sign-task/owner/get-list", {
    "ownerId": {"idType": "corp", "openId": OPEN_CORP_ID},
    "ownerRole": "initiator",
    "listFilter": {"signTaskStatus": ["sign_progress", "fill_progress"]},
    "listPageNo": 1, "listPageSize": 100,
})
```

- ⚠ 文档请求示例里 `signTaskStatus` 写成字符串 `"task_created"`，字段表是数组；按数组传。

## 17. 下载签署文档

**Endpoint**: `POST /sign-task/owner/get-download-url`

**用途**: 获取签署文档 / 附件的下载地址。**授权要求**: `signtask_file`。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `ownerId` | OpenId 对象 | 是 | 任务的发起方或参与方 |
| `signTaskId` | string | 二选一 | 下载单个任务，直接返回 `downloadUrl`；与 `batchDownloadInfo` 不可同时存在 |
| `batchDownloadInfo[]` | array | 二选一 | 批量（≤50 个任务），返回 `downloadId`，打包好后通过 `sign-task-download` 回调给链接 |
| `customName` | string | 否 | 下载文件 / 压缩包名，≤85 |
| `compression` | boolean | 否 | 单个文档是否也打成 zip，默认 false |
| `downloadMode` | string | 否 | 单个文档：`preview`（**默认**，先打开预览页再点下载）/ `download`（直接下载） |
| `folderBySigntask` / `folderName` | — | 否 | 批量时的目录结构 |

```python
import requests
d = fasc_call("/sign-task/owner/get-download-url", {
    "ownerId": {"idType": "corp", "openId": OPEN_CORP_ID},
    "signTaskId": sign_task_id,
    "downloadMode": "download",          # 服务端直接取文件时显式指定
})
resp = requests.get(d["downloadUrl"], timeout=120)   # 1 小时有效，期内不限次数
ext = ".zip" if "zip" in resp.headers.get("Content-Type", "") else ".pdf"
open(f"contracts/{sign_task_id}{ext}", "wb").write(resp.content)
```

- 单个任务只有一个文件 → 下载该文件；多个文件（多文档或含附件）→ zip，内含 `document/`、`attachment/` 子目录。
- ⚠ 响应字段说明写"文件压缩格式 zip"，与"单个文件直接下载"的说明不一致；按 Content-Type 判断。`preview` 模式下服务端直接 GET 拿到的是什么，文档未说明——服务端下载一律传 `downloadMode: "download"`。
- 链接不支持小程序内嵌下载。

## 18. 查询签署完成的文件

**Endpoint**: `POST /sign-task/owner/get-file`

**用途**: 任务 `task_finished` 后查签署完成文件的 `fileId` 与临时下载地址（主要用于 OFD 签署后追加文档场景）。**授权要求**: 任一参与方主体的 `signtask_info`。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `signTaskId` | string | 是 | 任务 ID |
| `docId` | string | 否 | 只查某份文档 |

响应：`docs[]`（`docId`、`docName`、`fileId`、`fddFileUrl`（60 分钟有效））。下载到本地请用 §17。

## 19. 链接与时效汇总

| 链接 / 资源 | 来源接口 | 有效期（文档原文） |
| --- | --- | --- |
| `actorSignTaskUrl` | `/sign-task/actor/get-url` | 1 年，需登录 |
| `actorSignTaskEmbedUrl` | `/sign-task/actor/get-url` | 10 分钟、1 次（可配到 30 天） |
| `signTaskEditUrl` | `/sign-task/get-edit-url` | 2 小时、1 次（可配到 30 天），无需登录 |
| `downloadUrl` | `/sign-task/owner/get-download-url` | 1 小时，期内不限次数 |
| 批量下载 `downloadUrl` | `sign-task-download` 回调 | 1 小时 |
| `fddFileUrl`（完成文件） | `/sign-task/owner/get-file` | 60 分钟 |
| `authUrl` | `/user/get-auth-url`、`/corp/get-auth-url` | 7 天 |
| `uploadUrl` | `/file/get-upload-url` | 30 分钟 |

## 20. 常见错误码

文档原文，未实测；完整表见 [errors-and-limits.md](errors-and-limits.md)。

| code | 含义 | 常见原因 |
| --- | --- | --- |
| 211055 | 签署任务不是创建状态 | 已提交后还在 doc/add 等 |
| 211056 / 211145 | 发起 / 自动提交时文档为空 | autoStart=true 却没带 docs |
| 211146 / 211161 | 自动提交时参与方为空 / 没有签署权限的参与方 | autoStart=true 却没带签署方 |
| 211058 | 签署任务数可用量不足 | 套餐用量用完，联系法大大 |
| 211066 | 参与方不存在 | actorId 写错 |
| 211096 | 文档 fileId 不存在 | 传了 fddFileUrl 而不是 fileId，或 fileId 不属于本应用 |
| 211099 / 211100 | fileId 与文档模板 ID 同时为空 / 同时有值 | 两者只能传一个 |
| 211108 / 211155 | 有序签署未传 / 重复签署顺序 | `signInOrder=true` 时每个签署方都要唯一 `orderNo` |
| 211118 | 未指定业务场景标识，无法免验证签 | `requestVerifyFree=true` 但任务没传 `businessId` |
| 211125 | 不是填写完成状态，不允许定稿 | — |
| 211126 | 当前状态不允许撤销 | 未提交任务用 delete，已完成用 abolish |
| 211132 | 应用外个人参与方不能指定个人隐私身份匹配信息 | 见 §5 ⚠ |
| 211148 | 必填控件未填写 | — |
| 211154 | 文档内存在未关联参与方的签署控件 | 删掉多余签章控件或关联参与方 |

## 21. 本文未展开的签署任务接口

「API概览」和文档目录里还有（签名方式相同，参数去官网看）：
`/sign-task/field/add`、`/sign-task/field/delete`、`/sign-task/field/fill-values`（控件）；`/sign-task/attach/add`、`/sign-task/attach/delete`（附件）；
`/sign-task/actor/delete`、修改参与方、解绑参与方（参与方）；`/sign-task/block`、`/sign-task/unblock`、`/sign-task/extension`（阻塞、延期）、驳回填写；
`/sign-task/get-preview-url`、预填写链接、`/sign-task/get-batch-sign-url`（批量签署）；`/sign-task/actor/list`（参与方详情）、`/sign-task/field/list`（控件与填写内容）、
`/sign-task/get-approval-info`、签署业务类型、证据报告、刷脸底图、音视频、切图、签署文件夹、扫码签、基于模板批量发起、跨应用发收签。

## 22. ⚠ 汇总

- 详情接口新版 / 旧版两个路径并存，API概览与 SDK 仍用旧版（§15）。
- 请求示例的布尔写成字符串、`signTaskStatus` 写成字符串、`docFileId` 与 `docTemplateId` 同时给出，与字段表不一致（§4、§7、§16）。
- `certCAOrg` 出现在创建示例但不在字段表（§4）。
- `sendNotification` 默认值与"默认仅对抄送方发送通知"的关系（§5）；`211132` 与"强烈建议传身份匹配信息"冲突（§5）。
- 「概述」页状态列表缺 `finish_creation`（§1）；`cancelStatus` / `faultStatus` 类型（§15）。
- 提交前调用 `/sign-task/actor/get-url` 的行为（§11）；下载 `preview` 模式与 zip 描述（§17）。
