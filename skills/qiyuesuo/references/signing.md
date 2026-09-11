# 签署流程：签署方、签署位置、签署、链接、撤回与作废

> 来源：open.qiyuesuo.com「API文档 / 签署服务」「合同管理 / 签署合同、添加签署方、修改签署方、强制结束合同」「新手指南 / 名词解释」「常见问题」（抓取于 2026-09-11）。
> **未用真实凭证验证。** 报错 / 行为描述除特别标注外均为文档原文，未实测。示例复用 [auth-and-signing.md](auth-and-signing.md) §4 的 `qys_call`。

## 目录

1. [哪些签署动作能用接口完成](#1-哪些签署动作能用接口完成)
2. [签署顺序](#2-签署顺序)
3. [签署位置 Stamper 通用规则](#3-签署位置-stamper-通用规则)
4. [发起方静默签：公章 / 法人章 / 审批](#4-发起方静默签公章--法人章--审批)
5. [个人签名静默签（需授权）](#5-个人签名静默签需授权)
6. [让接收方签：签署页面与各种链接](#6-让接收方签签署页面与各种链接)
7. [催签](#7-催签)
8. [发起后添加 / 修改签署方](#8-发起后添加--修改签署方)
9. [撤回、删除、作废、强制结束](#9-撤回删除作废强制结束)
10. [状态枚举](#10-状态枚举)
11. [完整示例：公司自动盖章 + 员工在 H5 页面签字](#11-完整示例公司自动盖章--员工在-h5-页面签字)
12. [注意事项与 ⚠](#12-注意事项与-)

---

## 1. 哪些签署动作能用接口完成

| 签署动作（Action.type） | 谁执行 | 能否用接口直接完成 |
| --- | --- | --- |
| `COMPANY` 企业签章 | 指定操作人 / 有该印章权限的人 / 公章管理员 | **发起方（平台方及其子公司）可以**：`/v2/contract/companysign` |
| `LP` 法定代表人签字 | 法人或有法人章权限的人 | **发起方可以**：`/v2/contract/legalpersonsign` |
| `AUDIT` 审批 | 必须指定操作人，只有发起方能设置 | **发起方可以**：`/v2/contract/employeeaudit` |
| `OPERATOR` 经办人签字 | 经办人 | **不能**。经办人必须登录契约锁或打开签署页面签（FAQ 原文） |
| `PERSONAL`（个人签名） | 个人签署方本人 | 获得用户"个人签名授权"后可用 `/v2/contract/personalsign`；否则用签署页面 |
| 接收方（外部公司 / 个人）的任何节点 | 接收方 | 不能替对方签；给对方签署链接或等对方登录契约锁 |

- 只能替**对接方自己的公司（含子公司）**盖章。对接方在云平台维护别家公司的印章没有法律效力，接口签章的数字证书颁发给对接方公司（FAQ 原文）。
- 合同有"经办人签字"节点排在公章前面时，公章接口会报"未轮到签署"，要等经办人在页面签完（FAQ 原文）。

## 2. 签署顺序

- `ordinal`（合同级）默认 **true = 顺序签署**：按签署方 `serialNo` 依次流转；前一方没签完，后一方收不到短信、也不能签。
- `ordinal: false` 无序签署：发起后所有接收方同时收到通知。
- 公司签署方内部按 `actions[].serialNo`（从 0 开始）执行。
- `signFlowStrategy`：`ALL_SIGN_FINISH`（所有接收方签完才完成）/ `ANY_SIGN_FINISH`（任一接收方签完即完成）。
- 发起方**不能**规定接收方公司内部的签署流程，只能提签署要求；接收方没设置收件流程时默认顺序为经办人签字 → 法定代表人签字 → 企业签章（FAQ 原文）。

## 3. 签署位置 Stamper 通用规则

两种定位方式（文档原文）：

| 方式 | 字段 | 取值 |
| --- | --- | --- |
| 关键字定位 | `keyword` + `keywordIndex` + `offsetX` / `offsetY` | 偏移量是相对值，页宽 / 页高 = 1，范围 (-1, 1)；最终坐标 = 关键字坐标 + 偏移 |
| 坐标定位 | `page` + `offsetX` / `offsetY` | `page` 从 **1** 开始，`0` = 所有页，`-1` = 最后一页；坐标范围 [0, 1) |

- **坐标原点在页面左下角**，坐标指的是印章图片**左下角**的位置（不是 PDF 常见的左上角原点、也不是像素 / 点）。
- `keywordIndex`：`1` 第 1 个（默认）、`0` 所有、`-1` 倒数第 1 个。
- `type`：`COMPANY`（公章 / 个人执业章）、`PERSONAL`（个人签名）、`LP`（法人章）、`TIMESTAMP`（时间戳）、`ACROSS_PAGE`（骑缝章）、`ACROSS_PAGE_ODD` / `ACROSS_PAGE_EVEN` / `ACROSS_PAGE_SCOPE`（配合 `sealPageConfig`，如 `"2,4~7"`）。
- **绑定到谁**：在发起 / 加文档接口里，公司的位置用 `actionId`（签署节点 ID），个人的位置用 `signatoryId`（签署方 ID），两者都来自创建草稿的返回值；`documentId` 是合同文档 ID。签署接口（companysign 等）里不需要 actionId。
- `width`（10–120）/ `height`（4–48）只对个人签名、时间戳生效；`rotationDegrees` 0–360 顺时针。
- 时间戳格式：发起 / 加文档接口用 `datePatterns`（List），签署接口用 `datePattern`（String）：`HYPHEN` / `Chinese` / `ALL_Chinese` / `ENGLISH`。
- 业务分类里预设了签署动作 + 印章 + 位置时，签署接口可以不传 `stampers`（FAQ 原文）；发起方用接口签署、且之前没指定位置时，**必须**传位置参数（名词解释原文）。
- Word 转 PDF 可能导致排版变化，**关键字定位比坐标定位稳**（FAQ 原文）。

## 4. 发起方静默签：公章 / 法人章 / 审批

### 签署公章
**Endpoint**: `POST /v2/contract/companysign`
**用途**: 合同轮到平台方公司（或子公司）的公章节点时，用接口直接盖章。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `contractId` / `bizId` | String | 二选一 | |
| `tenantName` | String | 条件 | 以子公司身份签时传子公司全名，不传默认平台方 |
| `sealId` | String | 否 | 印章 ID；stamper 里没写 sealId 时从这里取 |
| `stampers` | List<Stamper> | 否 | 类型只能是 `COMPANY` / `TIMESTAMP` / `ACROSS_PAGE*`；`documentId` 必填 |
| `locateAllStamperKeywords` | Boolean | 否 | 默认 true |
| `draftsmanName` | String | 否 | 用 bizId 定位合同时辅助定位 |

```python
qys_call("POST", "/v2/contract/companysign", json_body={
    "contractId": contract_id,
    "sealId": "2490828768980361630",
    "stampers": [
        {"type": "COMPANY", "documentId": document_id, "keyword": "甲方（盖章）", "offsetX": 0.05, "offsetY": -0.02},
        {"type": "ACROSS_PAGE", "documentId": document_id, "offsetY": 0.5},   # 骑缝章，文档 >1 页才生效
    ],
})
```

响应只有 `responseCode` / `message`。报错（文档原文）：`1107 NOT SIGN STEP`（未轮到 / 没有公章节点）、`1106` 签章类型不对、`1109` 页码超出、`1201` 找不到印章、`1101` 合同状态不对。英文报错 "this contract is not turn to sign or has bean signed" 同义：合同未发起 / 已完成、没有调用方的公章节点、或前面有经办人签字节点没签（FAQ 原文）。

### 签署法人章
**Endpoint**: `POST /v2/contract/legalpersonsign`
参数同公章，`stampers[].type` 只能是 `LP` / `TIMESTAMP`；`sealId` 都不传时"使用该单位下最早的一枚法定代表人章"（文档原文）。法人章每家公司最多一个，创建合同时不能指定法人章。

### 审批
**Endpoint**: `POST /v2/contract/employeeaudit`
参数：`contractId`/`bizId`、`tenantName`、`pass`（Boolean，必填）、`comment`。没轮到审批 → `1107`。

## 5. 个人签名静默签（需授权）

**Endpoint**: `POST /v2/contract/personalsign`
**前置**: 用户已通过「授权管理 → 个人签名授权页面」（`POST /v2/personalsign/authurl`）授权；授权结果回调见 [callbacks.md](callbacks.md) §6。
**参数**：`contractId`/`bizId`、`tenantName`、`user`（`{contact, contactType}`，必填）、`stampers`（`PERSONAL` / `TIMESTAMP`）、`companySignatory`（`{id}` 或 `{name}`，签企业签署方下的个人签字节点时传，仅限平台方及子公司）。找不到个人签名 → `1201`。

## 6. 让接收方签：签署页面与各种链接

| 接口 | Endpoint | 适用状态 | 链接有效期 | 关键参数 |
| --- | --- | --- | --- | --- |
| 签署页面 | `POST /v2/contract/pageurl` | 签署中 | 默认 30 分钟；可用 `expireTime` + `expireTimeUnit`（`MINUTES` 默认 / `DAYS`）设 5 分钟 – 90 天 | `user`（必填，签署人） |
| 获取短链接 | `GET /v2/contract/shorturl` | 非草稿 | ⚠ 文档未说明 | `contact`（指定登录账号） |
| 浏览页面 | `GET /v2/contract/viewurl` | 有文档即可 | 30 分钟 | `documentId`、`downloadButton`、`printButton` |
| 预签署页面 | `POST /v2/contract/appointurl` | 草稿 | 默认 30 分钟，同样可设 5 分钟 – 90 天 | `pageType`：`APPOINT`（指定位置，默认）/ `FILL_PARAMETERS`（填参）/ `DRAFT`（基础信息） |
| 签署方待加入链接 | `GET /v2/contract/joinurl` | 签署方 `delaySet` 的合同 | ⚠ 文档未说明 | `type`（`COMPANY` / `PERSONAL`，必填）→ `joinUrls[].{serialNo,url}` |
| 未知个人签署方链接 | `GET /v2/contract/personal/joinurl` | 签署中 / 拟定中 | ⚠ 文档未说明 | → `joinUrls[].{serialNo,url}` |

### 签署页面（最常用）
**Endpoint**: `POST /v2/contract/pageurl`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `contractId` / `bizId` | String | 二选一 | |
| `user` | User | 是 | 操作人 `{contact, contactType}`（`MOBILE` / `EMAIL` / `EMPLOYEEID` / `NUMBER`）；**必须是当前可签的签署方**，否则 `1110 NO VIEW PERMISSION` / `11011121` |
| `pageType` | String | 否 | `SIGN`（默认）/ `PRINT`（仅 PC）/ `DIRECT_SIGN`（直接签署页，H5） |
| `callbackPage` | String | 否 | 签完跳转地址 |
| `expireTime` / `expireTimeUnit` | Integer / String | 否 | 见上表 |
| `hideReturnButton` / `hideRecallButton` / `hideRejectButton`（默认 **true** 隐藏退回）/ `hideEndButton` / `hideStateButton` / `showResendButton` | Boolean | 否 | 页面按钮控制 |
| `allowPasswordSign` | Boolean | 否 | 首次验证码签署后 30 分钟内可用密码签 |
| `lang`、`pageStyle.themeColor` | | 否 | 语言 / 主题色 |

```python
page = qys_call("POST", "/v2/contract/pageurl", json_body={
    "contractId": contract_id,
    "user": {"contact": "13800000000", "contactType": "MOBILE"},
    "pageType": "DIRECT_SIGN",
    "expireTime": 7, "expireTimeUnit": "DAYS",
    "callbackPage": "https://your.app/contracts/done",
})
sign_url = page["pageUrl"]
```

- 接收方通过免登录的签署链接签署时，只能用**短信验证码**确认意愿（防伪造页面）；发起方默认用签署密码（FAQ 原文）。
- 签署链接可以嵌进你的网站 / APP（支持跨域）；小程序用小程序插件、无法内嵌时用 JS-SDK 方案（接入示例原文），本 skill 未展开。
- 不想让契约锁发短信：在业务分类「短信设置」关闭（接入示例原文），接口参数里没有对应开关。
- ⚠ 文档自相矛盾：签署页面接口页写链接有效期 30 分钟，FAQ「接口问题」写"获取到的链接有效期为10分钟"；FAQ 又说"手机短信发送的签署链接不会过期"（受合同截止签署时间约束）。以接口页 + `expireTime` 参数为准，拿到链接尽快下发。

## 7. 催签

**Endpoint**: `POST /v2/contract/notice`
参数：`contractId`/`bizId`、`tenantName`、`signatoryId`（不传时催谁 ⚠ 文档未说明）。

## 8. 发起后添加 / 修改签署方

| 接口 | Endpoint | 条件 / 说明 |
| --- | --- | --- |
| 添加签署方 | `POST /v2/signatory/add` | 合同"签署中"或"已完成"，且业务分类开启了"发起后允许继续发送签署"（否则 `11011304`）；body：`contractId`/`bizId` + `signatory`（结构同草稿接口） |
| 修改签署方 | `POST /v3/signatory/edit` | 补全 / 修改签署方名称、接收人、签署校验方式；公司类型"已接收则不可修改"；body：`signatoryId`（必填）+ `tenantName` / `signValidateWay`（至少一个）+ `receiver` + `operator` |
| 修改签署节点签署人 | `POST /v2/signatory/operators/edit` | 未展开 |

- ⚠ 文档自相矛盾：添加签署方页路径写 `/v2/signatory/add`，同页 Http 示例却是 `POST /v2/signatory/modify`；修改签署方页路径 `/v3/signatory/edit`，示例是 `POST /v3/signatory/modify`。以"请求地址"和接口列表为准（add / edit）。

## 9. 撤回、删除、作废、强制结束

**一个接口按合同当前状态做不同的事**：

**Endpoint**: `POST /v2/contract/invalid`

| 合同当前状态 | 调用效果（文档原文） |
| --- | --- |
| `DRAFT` 草稿 | **删除**合同 |
| `SIGNING` 签署中（及 `FILLING`） | **撤回**，合同变为 `RECALLED` |
| `COMPLETE` 已完成 | **发起作废**：自动生成作废文件，发起方在作废文件上签公章，所有签署方都签完作废文件后变为 `INVALIDED` |
| `EXPIRED` / `RECALLED` / `REJECTED` | 签署服务页说"删除合同"；签署合同汇总页的状态表里没有这几项（⚠ 文档自相矛盾） |

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `contractId` / `bizId` | String | 二选一 | |
| `tenantName` | String | 否 | |
| `sealId` | String | 否 | 作废时发起方签作废文件用的印章；**发起方原来没签过时必须传**（汇总页原文），已签过默认用原印章 |
| `reason` | String | 否 | 撤回 / 作废原因 |
| `deleteDoc` | Boolean | 否 | 作废完成或撤回后是否删除合同文件，默认 false |
| `autoSign` | Boolean | 否 | 发起作废时是否自动签作废文件，默认 true |
| `receivers` | List | 否 | 作废通知接收人（仅单方作废生效） |
| `expireTime` | String | 否 | 作废截止日期 `yyyy-MM-dd`（3 年内）；到期没作废完成，文件自动恢复"已完成" |

```python
c = qys_call("GET", "/v2/contract/detail", params={"contractId": contract_id})
qys_call("POST", "/v2/contract/invalid", json_body={
    "contractId": contract_id,
    "reason": "信息填写错误",
    **({"sealId": "2589678690921123947"} if c["status"] == "COMPLETE" else {}),
})
```

相关接口：

| 接口 | Endpoint | 说明 |
| --- | --- | --- |
| 签署作废合同 | `POST /v2/contract/invalidsign` | 发起方签作废文件（`autoSign: false` 或自定义文件作废时用），可传 `sealId`、`stampers` |
| 自定义文件作废 | `POST /v2/contract/invalidbyfile` | 用自己上传的作废文件（未展开） |
| 自定义模板文件作废 | `POST /v2/contract/invalidbytemplate` | 用模板生成作废文件（未展开） |
| 强制结束合同 | `POST /v2/contract/forceend` | `reason` 必填；状态变为 `FORCE_END`；附件用 `/v2/contract/forceend/addattachment` |

- 作废期间状态是 `INVALIDING`；签署方拒绝作废或超过截止日期，合同详情里 `invalidFailType` 为 `INVALID_REJECTED` / `INVALID_CANCEL`。
- 状态不支持时返回 `1101 INVALID CONTRACT STATUS`。

## 10. 状态枚举

| 对象 | 字段 | 取值 |
| --- | --- | --- |
| 合同 | `status` | `DRAFT` `FILLING` `SIGNING` `COMPLETE` `REJECTED` `RECALLED` `EXPIRED` `INVALIDING` `INVALIDED` `FORCE_END` |
| 签署方 | `signatories[].status` | `DRAFT` `FILLING` `WAITING`（待签署）`SIGNING` `SIGNED` `RECALLED` `REJECTED` `EXPIRED` `FORCE_END` `INVALIDING` `INVALIDED` `CLOSED` |
| 签署动作 | `actions[].status` | `INIT` `START` `FINISH` `STOP`（审批不通过 / 作废、撤回、回退被拒）`END`（强制结束） |
| 签署方类型 | `tenantType`（详情返回） | `COMPANY` `PERSONAL` `C_NO_RECEIVER` `P_NO_RECEIVER` |

## 11. 完整示例：公司自动盖章 + 员工在 H5 页面签字

接 [contracts.md](contracts.md) §11 的 `create_and_send`：

```python
from qys_client import qys_call, QysError

cid = create_and_send("劳动合同.pdf", "张三", "13800000000", seal_id=2490828768980361630)

# 1) 发起方公章：位置已在发起时指定，这里只给印章
try:
    qys_call("POST", "/v2/contract/companysign",
             json_body={"contractId": cid, "sealId": "2490828768980361630"})
except QysError as e:
    # 1107 / 11011107：没轮到公章节点（例如前面还有经办人签字、审批）
    raise

# 2) 员工的签署链接，给 3 天
url = qys_call("POST", "/v2/contract/pageurl", json_body={
    "contractId": cid,
    "user": {"contact": "13800000000", "contactType": "MOBILE"},
    "pageType": "DIRECT_SIGN",
    "expireTime": 3, "expireTimeUnit": "DAYS",
})["pageUrl"]

# 3) 完成状态以回调为主、合同详情兜底（见 callbacks.md）
```

## 12. 注意事项与 ⚠

- 签署接口都是"对当前轮到的节点操作"：调之前可以用 `/v2/contract/detail?queryActionOperator=true` 看哪个 action 是 `START`。
- 签署链接、认证链接不要经 QQ / 微信等聊天软件转发测试：聊天软件的安全扫描会在后台先打开一次，"只能打开一次"的链接会直接失效（FAQ 原文，针对认证链接）。
- 印章大小在创建印章时决定，签署时不能改（FAQ 原文）。
- ⚠ 文档自相矛盾：签署链接有效期 30 分钟 vs 10 分钟（§6）；invalid 对 `EXPIRED`/`RECALLED`/`REJECTED` 的行为（§9）；add / edit 示例路径（§8）；签署合同汇总页的公章返回写 `code`（Integer），单独的签署公章页写 `responseCode`（String）。
- ⚠ 文档未说明：短链接 / 待加入链接的有效期；催签不传 `signatoryId` 的行为。
