# 模板：签署模板、文档模板与基于模板发起

> 来源：dev.fadada.com FASC OpenAPI 5.1「API文档 / 模板管理」（概述、查询签署任务模板列表/详情、查询文档模板列表、填充文档模板生成文件、获取模板管理/新增链接）、
> 「签署任务 / 创建签署任务(基于签署任务模板)」「回调事件 / 模板相关事件」「附录 / 基本概念」「API概览」，抓取于 2026-09-11。
> **未用真实凭证验证**：报错与行为描述均为文档原文，未实测。请求封装 `fasc_call` 见 [auth-and-signing.md](auth-and-signing.md)。

## 目录

1. [两种模板，别混](#1-两种模板别混)
2. [模板在哪里制作](#2-模板在哪里制作)
3. [获取模板管理链接](#3-获取模板管理链接)
4. [获取模板新增链接](#4-获取模板新增链接)
5. [查询签署模板列表](#5-查询签署模板列表)
6. [查询签署模板详情](#6-查询签署模板详情)
7. [基于签署模板创建签署任务](#7-基于签署模板创建签署任务)
8. [查询文档模板列表](#8-查询文档模板列表)
9. [填充文档模板生成文件](#9-填充文档模板生成文件)
10. [启用 / 停用 / 删除](#10-启用--停用--删除)
11. [模板回调事件](#11-模板回调事件)
12. [端到端示例：按模板名发起](#12-端到端示例按模板名发起)
13. [相关错误码](#13-相关错误码)
14. [⚠ 汇总](#14--汇总)

---

## 1. 两种模板，别混

| | 签署模板（SignTaskTemplate） | 文档模板（DocTemplate） |
| --- | --- | --- |
| 包含什么 | 若干文档 + 附件 + 控件 + **参与方及权限** + 流程参数（有序、定稿方式…） | 一份文档底稿 + 控件 |
| 适合 | 流程、参与方都固定的合同（如劳动合同：用人单位 + 劳动者） | 同一份合同内容反复使用，参与方每次不同 |
| 怎么用来发起 | `/sign-task/create-with-template` | 在 `/sign-task/create` 的 `docs[].docTemplateId` 里引用；或 `/doc-template/fill-values` 填充成文件拿 fileId |
| ID | `signTemplateId` | `docTemplateId` |
| 查询 | `/sign-template/get-list`、`/sign-template/get-detail` | `/doc-template/get-list`、`/doc-template/get-detail` |

还有一套**应用模板**（`/app-template/*`、`/app-sign-template/*`、`/app-doc-template/*`，面向第三方应用给多个企业共用），本 skill 不覆盖。

授权：查询 / 使用某企业的模板需要该企业授权 `template`（集成应用所属企业默认已授权），否则 `213005`。

## 2. 模板在哪里制作

模板的文档上传和控件拖放在**法大大页面**里完成，接口只负责拿页面链接：

| 接口 | 页面 |
| --- | --- |
| `/template/manage/get-url` | 模板管理（新增、编辑、删除、启用、停用） |
| `/template/create/get-url` | 新增模板 |
| `/template/edit/get-url`、`/template/preview/get-url` | 编辑 / 预览（本文未展开参数） |

这些链接：**有效期 2 小时、1 次有效、仅 PC**，且**无需用户登录**——业务系统要自己控制分发（文档原文）。
另有 `/doc-template/create`、`/doc-template/copy-create`（接口方式创建 / 复制文档模板），本文未展开。

## 3. 获取模板管理链接

**Endpoint**: `POST /template/manage/get-url`

**用途**: 返回企业模板管理页面链接。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `openCorpId` | string | 是 | 企业 openCorpId（**字符串**，不是 OpenId 对象） |
| `signTemplateType` | string | 否 | 点"新增"后的制作方式：`pdf`（本地上传，版式）/ `html`（在线编辑，动态模板）/ `all`（下拉选择） |
| `showFieldCatalog` | array | 否 | 只展示这些自定义控件文件夹 |
| `redirectUrl` | string | 否 | ≤500，需 URL 编码 |

```bash
fasc_call /template/manage/get-url '{"openCorpId":"cf6c41520b6544f590b6e6909ca7d488"}'
```

响应：`data.templateManageUrl`。

## 4. 获取模板新增链接

**Endpoint**: `POST /template/create/get-url`

**用途**: 返回新增模板页面链接；用 `createSerialNo` 把之后的回调事件和你的业务记录对应起来。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `openCorpId` | string | 是 | 企业 openCorpId |
| `type` | string | 是 | `doc` 文档模板 / `sign` 签署模板 |
| `createSerialNo` | string | 否 | 你定义的创建序列号，`template-create` 等回调里会带回，用来对应 templateId |
| `showFieldCatalog` | array | 否 | 只展示这些自定义控件文件夹 |
| `disabledStandardFieldCodes` | string[] | 否 | 置灰的标准控件编码（与 Field 的 `fieldType` 一致），`["*"]` 置灰全部 |
| `redirectUrl` | string | 否 | ≤500，需 URL 编码 |

```python
from fasc_client import fasc_call
url = fasc_call("/template/create/get-url", {
    "openCorpId": OPEN_CORP_ID, "type": "sign", "createSerialNo": "tpl-req-0001",
})["templateCreateUrl"]
```

响应：`data.templateCreateUrl`。用户保存后会收到 `template-creating`（草稿）/ `template-create` 回调，里面有 `templateId` 和 `createSerialNo`。

## 5. 查询签署模板列表

**Endpoint**: `POST /sign-template/get-list`

**用途**: 按更新时间倒序列出企业的签署模板。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `ownerId` | OpenId 对象 | 是 | 模板归属方 `{"idType":"corp","openId":…}` |
| `listFilter.signTemplateName` | string | 否 | 名称模糊匹配，≤100 |
| `listFilter.signTemplateStatus` | string | 否 | `invalid` 停用 / `valid` 启用 / `creating` 草稿；默认都查 |
| `listFilter.businessTypeNames` / `businessTypeIds` | array | 否 | 按业务类型过滤，各 ≤50 |
| `listPageNo` | int | 否 | 从 1 开始 |
| `listPageSize` | int | 否 | 默认 100，最大 100 |

**示例响应**

```json
{"code": "100000", "msg": "请求成功",
 "data": {"signTemplates": [{"signTemplateId": "101115", "signTemplateName": "模板1",
                             "signTemplateStatus": "invalid", "createTime": "1677115605000"}],
          "listPageNo": 1, "countInPage": 3, "listPageCount": 5, "totalCount": 20}}
```

`signTemplates[]` 字段：`signTemplateId`、`signTemplateName`、`signTemplateStatus`、`signTemplateType`（`pdf` / `html`）、`templateVersion`（`v3` / `v5`）、`catalogName`、`businessTypeName`、
`createSerialNo`、`creatorMemberId` / `creatorMemberName`、`description`、`storageType`、`createTime`、`updateTime`（毫秒）。

- **停用和草稿状态的模板无法创建签署任务**（`211052 签署模板未启用`）——发起前过滤 `valid`。
- ⚠ 文档响应示例里 `listPageNo` 为 0，与"页码从 1 开始"不一致。

## 6. 查询签署模板详情

**Endpoint**: `POST /sign-template/get-detail`

**用途**: 拿模板的文档、控件、参与方（及各自的填写 / 签章控件）——发起前用它确定 `actorId`、`fieldDocId`、`fieldId`。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `ownerId` | OpenId 对象 | 是 | 模板归属方 |
| `signTemplateId` | string | 是 | 模板 ID |

主要响应字段：

| 字段 | 说明 |
| --- | --- |
| `signTemplateId` / `signTemplateName` / `signTemplateStatus` / `signTemplateType` | 基本信息 |
| `signInOrder` / `autoFillFinalize` / `effectiveDuration` | 流程参数；`effectiveDuration`（有效天数）**不会自动带入**新任务，要自己算 `expiresTime` |
| `docs[]` | `docId`、`docName`、`docFields[]`（Field：`fieldId`、`fieldName`、`fieldType`、`position`…） |
| `attachs[]` | `attachId`、`attachName` |
| `actors[].actorInfo` | `actorId`、`actorType`、`permissions`、`isInitiator`、`identNameForMatch`、`certType`、`certNoForMatch`、`memberIds` |
| `actors[].fillFields[]` / `signFields[]` | 该参与方关联的 `fieldDocId` + `fieldId`（签章控件还有 `sealId`） |
| `actors[].signConfigInfo` | `orderNo`、`verifyMethods`、`signerSignMethod`、`readingToEnd`… |
| `actors[].notification` | `notifyWay`（`mobile` / `email`）、`notifyAddress` |
| `watermarks[]` / `approvalInfos[]` | 水印、审批流程 |

- ⚠ 文档响应示例里 `docId`、`attachId`、`fieldDocId` 是数字 `0`，字段表写 string；代码里统一按字符串处理。

## 7. 基于签署模板创建签署任务

**Endpoint**: `POST /sign-task/create-with-template`

**用途**: 从签署模板复制文档、控件和参与方，给每个参与方指定具体的人 / 企业后发起。
**授权要求**: 发起方 `signtask_init`；模板归属企业 `template`。

**关键参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `initiator` | OpenId 对象 | 是 | — | 发起方（扣费主体） |
| `signTemplateId` | string | 是 | — | 签署模板 ID |
| `signTaskSubject` | string | 是 | — | 任务主题，≤200 |
| `autoStart` | boolean | 否 | **false** | 同 `/sign-task/create`；不自动提交就要再调 `/sign-task/start` |
| `autoFillFinalize` / `autoFinish` | boolean | 否 | true / true | 同 `/sign-task/create` |
| `expiresTime` / `dueDate` | string | 否 | — | 毫秒时间戳 |
| `freeSignType` | string | 否 | `business` | 免验证签类型：`business`（按场景码，需 `businessId`）/ `template`（按模板） |
| `businessId` | string | 否 | — | 免验证签场景码 |
| `transReferenceId` / `callbackUrl` / `catalogId` / `initiatorMemberId` / `businessTypeId` … | | 否 | — | 同 `/sign-task/create` |
| `actors[]` | array | 否 | — | 给模板里的参与方指定具体主体 |
| `actors[].actor.actorId` | string | 是 | — | **必须是模板里存在的参与方标识**（仅抄送方可以新增） |
| `actors[].actor.actorName` | string | 是 | — | 具体的企业全称 / 个人名称，不能为空 |
| `actors[].actor.actorOpenId` / `accountName` / `identNameForMatch` / … | | 否 | — | 同 Actor（[sign-tasks.md §5](sign-tasks.md#5-actor-参与方对象)） |
| `actors[].fillFields[]` | array | 否 | — | 只在要改填写控件默认值时传；`fieldDocId`（模板 `docs[].docId`）、`fieldId`/`fieldName`、`fieldValue`（**此处必填**）；参与方与控件关系必须和模板一致 |
| `actors[].signFields[]` | array | 否 | — | 以模板为准；可指定 `sealId` |
| `actors[].signConfigInfo` | object | 否 | — | `orderNo`、`signerSignMethod`、`readingToEnd`、`readingTime` 传了会覆盖模板配置 |
| `watermarks` | array | 否 | — | 水印 |

**示例响应**：`{"code":"100000","msg":"请求成功","data":{"signTaskId":"1677138236850120874"}}`

**注意事项**（文档原文）

- 接口里指定的文档标识、控件编码和名称、参与方标识、参与方与控件关系**必须与签署模板完全匹配**，**不支持新增签署任务要素**。
- 参与方的 `actorType`、`permissions` 以模板为准，传了会被忽略。
- 模板中参与方主体类型与接口里不一致 → `211014`；填写方标识在模板中不存在 → `211081`；模板没有参与方 / 文档 → `211053` / `211054`。
- ⚠ 文档自相矛盾：Actor 对象字段表把 `actorType`、`permissions` 标为必填，而模板场景又说它们被忽略。稳妥做法是**从模板详情原样抄过来**（见 §12）。
- ⚠ 文档请求示例里 `fillFields` 写成对象 `{…}`，字段表是数组 `FillField[]`；按数组传。
- ⚠ 同一页面"免验证签使用说明"的链接指向 `api-path/…`，创建（基于文档）页指向 `api-help/…`，是两个不同的帮助文档地址。

## 8. 查询文档模板列表

**Endpoint**: `POST /doc-template/get-list`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `ownerId` | OpenId 对象 | 是 | 模板归属方 |
| `listFilter.docTemplateName` | string | 否 | 名称模糊匹配 |
| `listFilter.docTemplateStatus` | array | 否 | `invalid` / `valid` / `creating` |
| `listPageNo` / `listPageSize` | int | 否 | 从 1 开始；默认 100，最大 100 |

响应：`docTemplates[]`（`docTemplateId`、`docTemplateName`、`docTemplateStatus`、`templateVersion`、`catalogName`、`createSerialNo`、`storageType`、`createTime`、`updateTime`…）+ 分页字段。
文档模板详情（控件列表）用 `/doc-template/get-detail`（本文未展开参数）。

```bash
fasc_call /doc-template/get-list '{"ownerId":{"idType":"corp","openId":"'"$OPEN_CORP_ID"'"},"listFilter":{"docTemplateStatus":["valid"]},"listPageNo":1,"listPageSize":50}'
```

- ⚠ 文档请求示例把 `listPageNo`、`listPageSize` 写成字符串 `"2"`、`"4"`，字段表是 int。

## 9. 填充文档模板生成文件

**Endpoint**: `POST /doc-template/fill-values`

**用途**: 用文档模板 + 填写值生成一份 PDF 待签文件，直接得到 `fileId`（可作为 `docFileId` 发起签署）。
**授权要求**: 企业 `template`。文档注明"该接口要求支持 OPDM 本地版本大于 1.0.7 版本"（本地存储部署相关）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `openCorpId` | string | 否 | 模板归属企业（**字符串**）；不传表示接入方自己的模板 |
| `docTemplateId` | string | 是 | 文档模板 ID |
| `fileName` | string | 是 | 生成文件名；不能含 `/ \ : * " < > ？` 和 emoji |
| `docFieldValues[]` | array | 是 | 仅支持填写类控件 |
| `docFieldValues[].fieldId` | string | 否 | 控件编码；与 `fieldName` 不能同时为空 |
| `docFieldValues[].fieldName` | string | 否 | 控件名称，同名控件都会被填充；传了 fieldId 时忽略 |
| `docFieldValues[].fieldValue` | string | 是 | 值格式随控件类型：单选 `[false,true,false]`、复选 `[false,false,true,true]`、日期 `YYYY年MM月DD日`、图片 = 图片 fileId、表格 `[["11","12"],["21","22"]]` |

```python
r = fasc_call("/doc-template/fill-values", {
    "openCorpId": OPEN_CORP_ID,
    "docTemplateId": "1690360801365154633",
    "fileName": "劳动合同-张三",
    "docFieldValues": [
        {"fieldId": "employee_name", "fieldValue": "张三"},
        {"fieldId": "start_date", "fieldValue": "2026年10月01日"},
    ],
})
file_id = r["fileId"]                 # 可直接作为 /sign-task/create 的 docFileId
```

响应：`fileId`、`fileDownloadUrl`（15 分钟有效）。

- ⚠ 文档响应示例的键写成 `"fileDownloadUrl "`（末尾多一个空格），字段表是 `fileDownloadUrl`；按字段表取值，必要时两个都试。
- 注意同一套模板接口里，查询类用 `ownerId`（OpenId 对象），链接类和填充接口用 `openCorpId`（字符串），参数形状不统一。

## 10. 启用 / 停用 / 删除

来自「API概览」（本文未展开参数）：

| 接口 | 说明 |
| --- | --- |
| `/sign-template/set-status` | 启用或停用签署模板；**只有停用的模板才可以被删除** |
| `/doc-template/set-status` | 启用或停用文档模板；只有停用的才可删除 |
| `/sign-template/delete`、`/doc-template/delete` | 删除 |
| 复制新增签署模板、复制新增文档模板（`/doc-template/copy-create`） | 复制 |

## 11. 模板回调事件

| 事件 ID | 触发 | 字段 |
| --- | --- | --- |
| `template-creating` | 通过 EUI 创建模板**草稿**、或复制新增模板后 | `eventTime`、`openCorpId`、`templateId`、`type`（`doc` / `sign`）、`createSerialNo`、`clientCorpId` |
| `template-create` | 通过 EUI 创建模板后 | 同上；应用级模板时 `openCorpId` 为空 |
| `template-enable` | 启用模板；**编辑模板并提交也会触发**，可借此监听模板被修改 | `eventTime`、`openCorpId`、`templateId`、`type`、`clientCorpId` |
| `template-disable` | 停用模板 | 同上 |
| `template-delete` | 删除模板 | 同上 |

收到事件后调模板详情接口取具体内容。回调接收与验签见 [callbacks.md](callbacks.md)。

## 12. 端到端示例：按模板名发起

```python
import os, time
from fasc_client import fasc_call

OPEN_CORP_ID = os.environ["FASC_OPEN_CORP_ID"]
OWNER = {"idType": "corp", "openId": OPEN_CORP_ID}

# 1. 找到启用状态的模板
tpls = fasc_call("/sign-template/get-list", {
    "ownerId": OWNER,
    "listFilter": {"signTemplateName": "劳动合同", "signTemplateStatus": "valid"},
    "listPageNo": 1, "listPageSize": 20,
})["signTemplates"]
if not tpls:
    raise SystemExit("没有启用的劳动合同模板")
tpl_id = tpls[0]["signTemplateId"]

# 2. 读模板详情，拿参与方与控件
detail = fasc_call("/sign-template/get-detail", {"ownerId": OWNER, "signTemplateId": tpl_id})
actors_in_tpl = {a["actorInfo"]["actorId"]: a for a in detail.get("actors", [])}
print({k: (v["actorInfo"]["actorType"], v["actorInfo"]["permissions"]) for k, v in actors_in_tpl.items()})

def actor_from_tpl(actor_id: str, **extra) -> dict:
    info = actors_in_tpl[actor_id]["actorInfo"]
    # actorType / permissions 以模板为准：原样抄过来，避免必填校验
    return {"actorId": actor_id, "actorType": info["actorType"], "permissions": info["permissions"], **extra}

# 3. 发起（actorId 必须与模板一致，不能新增文档或控件）
task = fasc_call("/sign-task/create-with-template", {
    "initiator": OWNER,
    "signTemplateId": tpl_id,
    "signTaskSubject": "劳动合同-张三",
    "expiresTime": str(int(time.time() * 1000) + 7 * 24 * 3600 * 1000),
    "autoStart": True,
    "actors": [
        {"actor": actor_from_tpl("用人单位", actorName="示例科技有限公司", actorOpenId=OPEN_CORP_ID)},
        {"actor": actor_from_tpl("劳动者", actorName="张三", accountName="13800000000",
                                 identNameForMatch="张三")},
    ],
})
print(task["signTaskId"])
```

模板里的 `"用人单位"`、`"劳动者"` 只是示例 actorId，以你的模板详情为准。

## 13. 相关错误码

文档原文，未实测。

| code | 含义 |
| --- | --- |
| 213005 | 用户未授权应用管理【模板管理】权限 |
| 211014 | 参与方主体类型不匹配（模板与接口不一致） |
| 211052 | 签署模板未启用 |
| 211053 / 211054 | 签署模板下参与方 / 文档列表为空 |
| 211081 | 填写方标识在签署模板下不存在 |
| 211085 / 211089 / 211091 / 211093 | 填写控件编码 / 名称不存在 |
| 211101 | 文档列表中文档模板 ID 不能重复 |

## 14. ⚠ 汇总

- 列表响应示例 `listPageNo=0`（§5）；详情示例 ID 为数字（§6）；文档模板列表示例分页参数为字符串（§8）。
- 模板发起：Actor 必填与"被忽略"的矛盾、`fillFields` 示例写成对象、帮助文档链接不一致（§7）。
- `fill-values` 响应键名末尾空格（§9）。
