# 签署流程：发起、签署方与签署区、链接、查询、撤销、完结、下载（SaaS API V3）

> 内容整理自 e签宝开放平台《合同文件签署服务API V3》（`open.esign.cn/doc/opendoc/pdf-sign3/*`）、
> 《合同签署服务API V3 错误码》《签署流程状态详解》《签署页重定向跳转说明》（抓取于 2026-09-11）。
> **未用真实凭证调用验证**；报错与行为除特别注明外均为「文档原文，未实测」。
> 示例里的 `esign_request()` 是 [auth-and-signing.md §5](auth-and-signing.md) 的签名封装。

## 目录

1. [状态机：先搞清 autoStart / autoFinish](#1-状态机先搞清-autostart--autofinish)
2. [三种发起方式怎么选](#2-三种发起方式怎么选)
3. [基于文件发起签署 create-by-file](#3-基于文件发起签署-create-by-file)
4. [signers 传参规则速查（四种典型签署方）](#4-signers-传参规则速查四种典型签署方)
5. [开启签署流程 start](#5-开启签署流程-start)
6. [获取签署页面链接 sign-url](#6-获取签署页面链接-sign-url)
7. [查询签署流程详情 detail](#7-查询签署流程详情-detail)
8. [查询签署流程列表](#8-查询签署流程列表)
9. [撤销签署流程 revoke](#9-撤销签署流程-revoke)
10. [完结签署流程 finish](#10-完结签署流程-finish)
11. [延期与催签](#11-延期与催签)
12. [下载已签署文件](#12-下载已签署文件)
13. [流程中追加 / 删除签署区、文件、抄送方](#13-流程中追加--删除签署区文件抄送方)
14. [签署完成后的前端重定向](#14-签署完成后的前端重定向)
15. [⚠ 本文件的未说明 / 矛盾之处](#15--本文件的未说明--矛盾之处)

---

## 1. 状态机：先搞清 autoStart / autoFinish

`signFlowStatus`（查询详情返回 int）：**0 草稿，1 签署中，2 完成，3 撤销，5 过期，7 拒签**。

```
create-by-file ──autoStart=true(默认)──▶ 1 签署中 ──全部签完──┬─ autoFinish=true ─▶ 2 完成（自动）
      │                                   │                   └─ autoFinish=false(默认) ─▶ 仍是 1，须调 /finish 才到 2
      └─autoStart=false──▶ 0 草稿 ──/start──▶ 1               ├─ /revoke ─▶ 3 撤销
                                                              ├─ 过截止时间 ─▶ 5 过期
                                                              └─ 任一方拒签 ─▶ 7 拒签
```

两个默认值是整个接入里最容易踩的：

| 参数 | 默认 | 后果 |
| --- | --- | --- |
| `signFlowConfig.autoStart` | **true** | 创建即进入“签署中”并按配置通知签署人；**自动开启的流程不允许再追加待签文件**；此时 docs 与签署人不能为空（否则 `1435011 流程自动开启的场景文档和签署人信息不能为空`） |
| `signFlowConfig.autoFinish` | **false** | 所有人签完后流程**仍停在 1**：不会触发 `SIGN_FLOW_COMPLETE` 回调、下载接口报 `1437518 流程非签署完成状态，不允许下载文档`，必须主动调 `POST /v3/sign-flow/{id}/finish`。设了 true 的流程则不允许再追加签署区、抄送方 |

各状态允许的操作（《签署流程状态详解》原文）：
- **草稿 0**：追加 / 删除待签文件与附属材料、追加 / 删除签署区、添加 / 删除抄送方，最后必须 `/start`。
- **签署中 1**：获取签署链接、批量签链接、催签、追加签署区（仅 autoFinish=false）、删除未签署的签署区、追加附属材料、增删抄送方（添加仅 autoFinish=false）、延期、撤销。
- **完成 2**：只有这个状态能下载已签文件。

---

## 2. 三种发起方式怎么选

| 方式 | Endpoint | 说明 |
| --- | --- | --- |
| API 直接发起（本文主线） | `POST /v3/sign-flow/create-by-file` | 文件、签署方、签署区全部由接口指定 |
| 页面发起 | `POST /v3/sign-flow/sign-flow-initiate-url/by-file` | 返回一个发起页面，由人在页面上拖签署区、选签署方（字段未在本 skill 展开） |
| 流程模板发起 | `POST /v3/sign-flow/create-by-sign-template` | 用企业配置的流程模板，见 [files-and-templates.md §7](files-and-templates.md) |

《（精简版）基于文件发起签署》和《（完整版）基于文件发起签署》是**同一个接口**，精简版只是挑了常用参数。

---

## 3. 基于文件发起签署 create-by-file

**Endpoint**: `POST /v3/sign-flow/create-by-file`
**用途**: 用已上传且状态为 2/5 的 fileId 发起签署流程，返回 `signFlowId`。

**限制**（文档原文）：单流程文件 ≤50 个、单文件 ≤50MB、单页 ≤20MB、文件总和 ≤500MB；一次创建时 `signers` ≤10 个（超过报 `1437608`，之后用追加签署区，全流程 ≤50 个签署方）；签署区总数 ≤300。

### 3.1 顶层结构

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| docs | array | 否* | 待签文件 `[{fileId, fileName, contractNo, neededPwd, fileEditPwd, order}]`；`fileName` 要带真实后缀；*不传 docs 时 signers 也不传且 `autoStart` 必须 false |
| attachments | array | 否 | 附属材料（只看不签）`[{fileId, fileName}]` |
| signFlowConfig | object | **是** | 流程配置，见 3.2 |
| signFlowInitiator | object | 否 | 发起方（合同归属方），见 3.3；不传 = 应用 ID 所属企业 |
| signers | array | 否* | 签署方，见 3.4；*指定签署方时 `signFields` 必传 |
| copiers | array | 否 | 抄送方：抄送机构时 `copierOrgInfo{orgId|orgName}` 与 `copierPsnInfo{psnAccount|psnId}` 都要传；抄送个人只传 `copierPsnInfo` |

### 3.2 signFlowConfig（常用字段）

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| signFlowTitle | string | **是** | — | 流程主题，不可含 `/ \ : * " < > | ？` 与 emoji |
| signFlowExpireTime | int64 | 否 | 创建后 90 天 | **毫秒**时间戳，最多 90 天内（超出 `1435002 签署截止时间signFlowExpireTime不能超过发起后90天`） |
| autoStart | boolean | 否 | **true** | 见 §1 |
| autoFinish | boolean | 否 | **false** | 见 §1 |
| identityVerify | boolean | 否 | true | 传入的签署人信息与其 e签宝实名信息不一致时：true 报错（`1437328`），false 正常发起并允许签署人更正（配合“签署人更正个人信息”回调） |
| notifyUrl | string | 否 | — | 本流程的回调地址，见 [callbacks.md](callbacks.md)；若控制台 Webhook 也订阅了签署事件，两边都会推送（同地址推两次） |
| redirectConfig.redirectUrl | string | 否 | — | 签署完成后跳转地址；域名须在控制台放行，否则出现风险提示页 |
| redirectConfig.redirectDelayTime | int32 | 否 | 3 | 0 或 3；不传 redirectUrl 时**不能**传它（`1435002 redirectUrl为空时，不允许传入redirectDelayTime`） |
| noticeConfig.noticeTypes | string | 否 | `""` 不通知 | `1` 短信、`2` 邮件、`3` 钉钉、`5` 微信、`6` 企业微信、`7` 飞书，逗号分隔；3/5/6/7 仅正式环境 |
| noticeConfig.examineNotice | boolean | 否 | 取 noticeTypes | 是否通知用印审批人 |
| signConfig.availableSignClientTypes | string | 否 | — | `1` 网页、`2` 支付宝 |
| authConfig.psnAvailableAuthModes / orgAvailableAuthModes / willingnessAuthModes | list | 否 | — | 签署页可选的实名 / 意愿认证方式 |

**默认不发任何通知**：`noticeTypes` 默认空串。要 e签宝发短信就显式传 `"1"`；自己发链接就保持默认并用 §6 取链接。

### 3.3 signFlowInitiator（发起方）

```json
{"orgInitiator": {"orgId": "<机构账号ID>", "transactor": {"psnId": "<经办人账号ID>"}}}
```
或 `{"psnInitiator": {"psnId": "<个人账号ID>"}}`，二者**只能传一个**。
- 只能用账号 ID（orgId / psnId），拿法：`GET /v3/organizations/identity-info`、`GET /v3/persons/identity-info`（见 [identity-authorization.md](identity-authorization.md)）。
- 文档原文：自 2024-09-12 起，仅高级版 / 生态伙伴版支持指定非应用 ID 所属企业作为机构发起方，仅生态伙伴版支持个人发起方；
  生态版需先拿到 `org_initiate_sign`（及经办人的 `psn_initiate_sign`）授权，否则 `1436116 用户:%s未授权:org_initiate_sign`。
- 企业自用系统（OA / HR）通常**不传**发起方，由平台自身企业发起。

### 3.4 signers[]（签署方）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| signerType | int32 | **是** | 0 个人，1 企业/机构，2 法定代表人，3 经办人（⚠ 见 §15：错误码表写“signerType只支持0或1”） |
| signConfig.signOrder | int32 | 否 | 1–255，小的先签；同时签时可重复 |
| signConfig.forcedReadingTime | int32 | 否 | 强制阅读秒数，默认 0，最大 999 |
| signConfig.signTaskType | int32 | 否 | 0 会签（默认，全部要签）；1 或签（≥2 个签署方、配置一致、不允许自动签） |
| noticeConfig.noticeTypes | string | 否 | 该签署方的通知方式，同 3.2 |
| psnSignerInfo | object | 个人必传 | `psnAccount`（手机号或邮箱）与 `psnId` **二选一**；传 `psnAccount` 时 `psnInfo.psnName` 必传；`psnInfo` 还可带 `psnIDCardNum`、`psnIDCardType`（默认 `CRED_PSN_CH_IDCARD`）、`psnMobile`、`bankCardNum` |
| orgSignerInfo | object | 机构手动签必传 | `orgId` 与 `orgName` 二选一；手动签必须带经办人 `transactorInfo`（`psnAccount`+`psnInfo.psnName`，或 `psnId`）；**机构与经办人必须成对：orgId 配 psnId，orgName 配 psnAccount**；自动落章时建议整个对象不传 |
| signFields | array | **是**（指定签署方时） | 签署区，见 3.5 |

### 3.5 signFields[]（签署区）

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| fileId | string | **是** | — | 必须已在 `docs` 里，否则 `1435002 文件id不在签署流程中…` |
| customBizNum | string | 否 | — | 自定义业务编号，签署方签署结果回调里原样返回 |
| signFieldType | int32 | 否 | 0 | 0 签章区，1 备注区（用 `remarkSignFieldConfig`，只能给个人签署方），2 独立签署日期（用 `dateSignFieldConfig`） |
| mustSign | boolean | 否 | true | false 为选签，选签不允许自动落章 |
| normalSignFieldConfig.freeMode | boolean | 否 | false | 自由签章：不限位置 / 个数；**不支持自动签署** |
| normalSignFieldConfig.autoSign | boolean | 否 | false | 后台静默落章。**个人不支持**（`1435002 个人签署不支持自动签署`）；应用 ID 所属企业自身可以；其他机构需先有印章授权（自 2024-09-12 起需高级版 / 生态伙伴版）；自动签机构只能传 orgId 且不能传 transactorInfo |
| normalSignFieldConfig.assignedSealId | string | 否 | 平台默认章 | 指定印章 ID |
| normalSignFieldConfig.orgSealBizTypes | string | 否 | ALL | 页面可选章类型：PUBLIC / CONTRACT / FINANCE / PERSONNEL / COMMON；与指定印章不能同时用 |
| normalSignFieldConfig.psnSealStyles | string | 否 | `0,1` | 0 手写签名，1 姓名印章，2 手写 AI 校验，3 图片签名（仅海外签） |
| normalSignFieldConfig.signFieldStyle | int32 | 否 | — | 1 单页签章，2 骑缝签章 |
| normalSignFieldConfig.signFieldPosition | object | 非自由模式必传 | — | `positionPage`（string，单页只能一个页码；骑缝 + `acrossPageMode=AssignedPages` 可写 `1-3,6-10`）、`positionX`、`positionY`（float；骑缝时 X 不生效）；单页签章缺任一项报 `1435002 单页签章区，positionX、positionY、positionPage不能为空` |
| normalSignFieldConfig.signFieldSize / signFieldWidth+Height | float / int | 否 | 印章原始大小 | 二者不能同时传 |
| signDateConfig | object | 否 | — | 签署日期：`dateFormat`（默认 `yyyy年MM月dd日`）、`showSignDate`（0 不显示，1 固定位置，2 用户自选）、`signDatePositionX/Y` |

坐标可以用 [files-and-templates.md §5](files-and-templates.md) 的关键字检索得到。

### 3.6 示例：个人员工签字 + 平台自身企业自动盖章

```python
import time
body = {
    "docs": [{"fileId": file_id, "fileName": "张三-劳动合同.pdf"}],
    "signFlowConfig": {
        "signFlowTitle": "张三劳动合同签署",
        "signFlowExpireTime": int(time.time() * 1000) + 7 * 24 * 3600 * 1000,   # 毫秒，≤90 天
        "autoStart": True,
        "autoFinish": True,             # 不设就得自己调 /finish
        "notifyUrl": "https://hr.example.com/esign/notify",
    },
    "signers": [
        {   # 员工：个人手动签
            "signConfig": {"signOrder": 1},
            "noticeConfig": {"noticeTypes": "1"},
            "signerType": 0,
            "psnSignerInfo": {"psnAccount": "13800000000", "psnInfo": {"psnName": "张三"}},
            "signFields": [{
                "fileId": file_id, "customBizNum": "HR-2026-0001-emp",
                "normalSignFieldConfig": {"signFieldStyle": 1,
                    "signFieldPosition": {"positionPage": "3", "positionX": 400, "positionY": 190}},
            }],
        },
        {   # 平台自身企业：自动落章，不传 orgSignerInfo
            "signConfig": {"signOrder": 2},
            "signerType": 1,
            "signFields": [{
                "fileId": file_id, "customBizNum": "HR-2026-0001-org",
                "normalSignFieldConfig": {"autoSign": True, "signFieldStyle": 1,
                    "signFieldPosition": {"positionPage": "3", "positionX": 150, "positionY": 190}},
            }],
        },
    ],
}
sign_flow_id = esign_request("POST", "/v3/sign-flow/create-by-file", body=body)["data"]["signFlowId"]
```

示例响应：`{"code":0,"message":"成功","data":{"signFlowId":"165467****000"}}`。
文档自带示例的 `signFlowExpireTime` 是 `169111118000`（12 位，折合 1975 年），**不要照抄**（⚠ 文档示例值无效）。

**常见错误码**（文档原文，未实测）

| code | message | 含义 |
| --- | --- | --- |
| 1435002 | 参数错误: 个人签署方psnId和psnAccount不能同时为空或同时传值 | 二选一 |
| 1435002 | 参数错误: 机构签署方与机构签署经办人传入必须为orgId与psnId或orgName与psnAccount | ID 与账号标识不能混搭 |
| 1435002 | 参数错误: 非自动签签署机构签署方经办人transactorInfo不能为空 | 机构手动签缺经办人 |
| 1435002 | 参数错误: 自动签署机构账号只允许传orgId / 自动签署不支持传入transactorInfo / 自由模式不支持自动签署 | 自动签约束 |
| 1435011 | 机构签署账号:%s 不允许自动签署 | 没有该机构的印章授权 |
| 1437182 | 未获取该企业有效的印章授权 | 同上 |
| 1437513 | 文档未成功转换成pdf, 请稍后重试 | 没等 fileStatus=2/5 就发起 |
| 1437306 | 单页签署: 签署页码超出文档页数 | positionPage 越界 |
| 1437328 | 传入的签署人用户信息与e签宝用户信息不一致… | 姓名 / 证件与实名不符（identityVerify=true） |
| 1435404 / 1435405 | 企业账户中电子合同份数不足… | 套餐余量不足 |
| 1437608 | 流程创建签署人或签署主体个数%s超过数量限制，最多允许创建10个。 | signers 超 10 |

---

## 4. signers 传参规则速查（四种典型签署方）

（《精简版》附录原文整理）

| 字段 \ 场景 | 应用 ID 所属企业自动落章 | 其他机构自动落章 | 机构手动签署 | 个人手动签署 |
| --- | --- | --- | --- | --- |
| signerType | 1 | 1 | 1 | 0 |
| orgSignerInfo | 不传 | 不传 | 传 orgId 或 orgName，**且**传经办人 transactorInfo | 不传 |
| psnSignerInfo | 不传 | 不传 | 不传 | psnAccount 或 psnId |
| autoSign | true | true | false | false |
| assignedSealId | 不传（默认章）或自身印章 ID | 该机构授权给平台企业的印章 ID | 不传 | 不传 |

---

## 5. 开启签署流程 start

**Endpoint**: `POST /v3/sign-flow/{signFlowId}/start`（无 body）
草稿（autoStart=false）流程补齐文件 / 签署方后调用。开启后不能再增删文件。
错误码：`1437169 流程已过期`、`1435405 企业账户中电子合同份数不足…`。

---

## 6. 获取签署页面链接 sign-url

**Endpoint**: `POST /v3/sign-flow/{signFlowId}/sign-url`
**前提**：流程已开启（状态 1），否则 `1437103 流程未开启`。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| operator.psnAccount / operator.psnId | string | 大多数场景必传 | — | 当前要签的人（机构签署传经办人），二选一，**必须与发起时传的方式和值一致**；不传时返回平台方的预览链接（⚠ 见 §15） |
| organization.orgId / orgName | string | 否 | — | 一个经办人代多个机构签时指定取哪个机构的链接 |
| urlType | int32 | 否 | 2 | 1 预览（免登录，不能签），2 签署 |
| needLogin | boolean | 否 | false | 是否需要登录 |
| clientType | string | 否 | ALL | `H5` / `PC` / `ALL`（大写） |
| redirectConfig.redirectUrl / redirectDelayTime | — | 否 | — | 同 3.2 |
| appScheme | string | 否 | — | App 内嵌时支付宝刷脸跳回 |

```python
r = esign_request("POST", f"/v3/sign-flow/{sign_flow_id}/sign-url", body={
    "operator": {"psnAccount": "13800000000"}, "urlType": 2, "clientType": "ALL"})
short_url, long_url = r["data"]["shortUrl"], r["data"]["url"]
```

响应：`shortUrl`（**90 天有效**）、`url`（长链接，永久有效；小程序 H5 内嵌要用长链接）。
错误码：`1437114 当前用户不是流程参与人, 无权查看流程`、`1435002 参数错误: 该appId没有权限获取该流程的签署链接`、`1435011 流程不存在:%s`。
多个流程一起签用 `POST /v3/sign-flow/batch-sign-url`（字段未展开；报错 `1437199 获取批量签署链接失败: …`）。

---

## 7. 查询签署流程详情 detail

**Endpoint**: `GET /v3/sign-flow/{signFlowId}/detail`
指定过发起方的流程需要该发起方的 `org_initiate_sign` / `psn_initiate_sign` 授权。

关键响应字段（`data` 下）：
- `signFlowStatus`（int：0/1/2/3/5/7）、`signFlowDescription`（撤销 / 拒签时为原因）、`revokeReason`、`rescissionStatus`（0 未解约，1 解约中，2 部分解约，3 已解约）
- `signFlowCreateTime` / `signFlowStartTime` / `signFlowFinishTime`（毫秒）
- `signFlowInitiator.{orgInitiator|psnInitiator}`、`signFlowConfig.{signFlowTitle, autoFinish, signFlowExpireTime, notifyUrl, noticeConfig, ...}`
- `docs[].{fileId, fileName, contractNum}`、`attachments[]`
- `signers[].{psnSigner|orgSigner, signerType(0 个人 / 1 机构), signOrder, signStatus}`，`signStatus`：0 等待签署，1 签署中，2 已签署，3 等待审批，4 已拒签
- `signers[].signFields[].{signFieldId, signFieldStatus, customBizNum, fileId, signFieldSealType(0 个人/1 机构/2 法人/3 经办人), normalSignFieldConfig...}`，`signFieldStatus`：0 等待执行，1 执行中，2 执行失败，3 审批中，4 执行完成（**字段表写 string，示例是 `"4"`**）

错误码：`1435011 流程不存在:%s`、`1435002 参数错误: 该接口仅能查询SaaS Api免登版发起的流程信息…`、`1436116 用户:%s未授权:org_initiate_sign`。

---

## 8. 查询签署流程列表

**Endpoint**: `POST /v3/sign-flow/sign-flow-list`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| pageNum | int32 | 是 | ≥1 |
| pageSize | int32 | 是 | 1–100 |
| signFlowStartTimeFrom / To | int64 | 否 | 发起时间区间（毫秒），区间 ≤1 年，只能查近 5 年 |
| signFlowFinishTimeFrom / To | int64 | 否 | 完结时间区间，同上 |
| signFlowStatus | list | 否 | 1/2/3/5/7，默认全部 |
| operator | object | 否 | `psnId` 或 `psnAccount` |

另有 `POST /v3/organizations/sign-flow-list`（查询集成方企业流程列表），校验规则相同。

---

## 9. 撤销签署流程 revoke

**Endpoint**: `POST /v3/sign-flow/{signFlowId}/revoke`
body：`{"revokeReason": "合同条款错误"}`（可选，≤50 字）。
- **只有“签署中”能撤销**：`1437203 非签署中的流程不允许撤销`、`1437168 流程已撤销`。草稿、已完成都不能用它。
- 已有签署方盖章后撤销，文档提示须先征得已签署方同意（法律风险）。
- 默认由平台发起的流程**只能通过接口撤销**，SaaS 官网上撤不了。
- 撤销成功会触发 `SIGN_FLOW_COMPLETE` 回调，`signFlowStatus` 为 `"3"`。

---

## 10. 完结签署流程 finish

**Endpoint**: `POST /v3/sign-flow/{signFlowId}/finish`（无 body）
仅在 `autoFinish=false` 时需要；全部签署区完成后才能调。
错误码：`1437113 签署区没有全部完成`、`1437112 非开启状态不允许归档流程`、`1437170 没有签署，无需归档`、`1437136 流程已归档`。

---

## 11. 延期与催签

- `POST /v3/sign-flow/{signFlowId}/delay`，body `{"signFlowExpireTime": <毫秒>}`（必填）。**每个流程只能延期一次**（`1435011 流程只能延期一次`），且只能对签署中的流程（`1437201`）。
- `POST /v3/sign-flow/{signFlowId}/urge`，body 可选 `noticeTypes`（`1` 短信 / `2` 邮件）、`urgedOperator`（不传 = 催当前轮到的所有人）。
  频率限制：发起后半小时内不能催（`1437137`），之后每 10 分钟一次（`1437138`）。

---

## 12. 下载已签署文件

**Endpoint**: `POST /v3/sign-flow/{signFlowId}/file-download-url`（2025-12-11 起推荐）；旧版 `GET …/file-download-url?urlAvailableDate=3600` 保留但不再加功能。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| urlAvailableDate | int | 否 | 3600 | 链接有效秒数，1–3600 |
| aesEncrypt | boolean | 否 | false | true 时不直接返回下载地址，改由《签署文件加密完成通知》回调给出 |
| rsaSecret + rsaSecretKey | string | 否 | — | RSA 公钥加密模式，两者必须同时传 |

```python
r = esign_request("POST", f"/v3/sign-flow/{sign_flow_id}/file-download-url", body={"urlAvailableDate": 3600})
for f in r["data"]["files"]:
    content = requests.get(f["downloadUrl"], timeout=120).content   # 链接默认 60 分钟有效，拿到就下
    open(f"contracts/{sign_flow_id}-{f['fileName']}", "wb").write(content)
```

响应：`files[].{fileId, fileName, downloadUrl}`、`attachments[]`、`certificateDownloadUrl`（海外签）、`aesSecret`。
- **只有状态 2（完成）能下载**：`1437518 流程非签署完成状态，不允许下载文档`——autoFinish=false 又没调 /finish 时就会遇到。
- 签署中想看当前文件用 `GET /v3/sign-flow/{signFlowId}/preview-file-download-url`。
- 文档示例把 `urlAvailableDate` 写成字符串 `"3600"`，字段表是 int（⚠ 按 int 传）。

---

## 13. 流程中追加 / 删除签署区、文件、抄送方

| 操作 | Endpoint | 允许的状态 / 限制 |
| --- | --- | --- |
| 追加签署区（含新签署方） | `POST /v3/sign-flow/{id}/signers/sign-fields`（body `signers[]`，结构同 3.4） | 草稿；签署中仅 autoFinish=false |
| 删除签署区 | `DELETE /v3/sign-flow/{id}/signers/sign-fields?signFieldIds=a,b` | 未签署的签署区 |
| 追加待签文件 | `POST /v3/sign-flow/{id}/unsigned-files` | **仅草稿**（`1437502 流程非草稿状态，不允许添加文档`） |
| 删除待签文件 | `DELETE /v3/sign-flow/{id}/unsigned-files?fileIds=a,b` | 草稿 |
| 追加 / 删除附属材料 | `POST /v3/sign-flow/{id}/attachments`、`DELETE …/attachments?fileIds=` | 追加在草稿和签署中都可；已完结报 `1437402` |
| 添加 / 删除抄送方 | `POST /v3/sign-flow/{id}/copiers`、`POST /v3/sign-flow/{id}/copiers/delete` | 自动完结流程不允许（`自动归档流程开启后，不允许添加抄送人`） |

注意删除抄送方是 **POST** `/copiers/delete`，而删除签署区 / 文件是 **DELETE** 带 query——DELETE 的 query 参数要进签名串的 PathAndParameters。

---

## 14. 签署完成后的前端重定向

手动签署完成后，签署页跳到 `redirectUrl` 并拼上参数：
`?tsignType=SIGN&tsignCode=0&tsignDes=签署成功&signFlowId=...`，`tsignCode`：0 签署成功，1 无权访问，2 流程被拒签。
这只是前端展示用，**业务状态以回调或详情接口为准**（URL 参数可被用户篡改）。

---

## 15. ⚠ 本文件的未说明 / 矛盾之处

| 位置 | 问题 |
| --- | --- |
| §3.4 signerType | 字段表写 0/1/2/3 四种，错误码表有 `参数错误: signerType只支持0或1`，详情响应里也只有 0/1（⚠ 文档自相矛盾；2/3 的可用条件以实测为准） |
| §3.6 | 文档示例 `signFlowExpireTime: 169111118000` 不是有效的毫秒时间戳（⚠ 示例值错误，未实测是否会被拒） |
| §3.5 坐标 | `positionX/Y` 的单位与原点、指的是签章区中心还是角点 ⚠ 本 skill 抓取的页面未说明（在未抓取的《印章图片尺寸和坐标》帮助页） |
| §6 operator | 标注“必选：是”，说明又写“若不传此参数，系统将默认使用 appId 对应的主体信息”（⚠ 文档自相矛盾） |
| §7 signFieldStatus | 字段表类型 string，其余状态字段为 int；回调里 `signFlowStatus` 也是 string（`"2"`），详情里是 int（⚠ 类型不一致，比较时统一转 int） |
| §12 | `urlAvailableDate` 示例是字符串 `"3600"`，字段表是 int |
| §3.2 | 《签署回调通知接收说明》写明控制台 Webhook 与 `notifyUrl` 都配置时**两边都会推送，地址相同就推两次**；而 `notifyUrl` 字段说明本身没提这一点——接收端必须幂等 |
