# 合同草稿、合同文档与模板

> 来源：open.qiyuesuo.com「API文档 / 合同管理」「模板管理」「业务分类」「新手指南 / 名词解释、接入示例」「常见问题」（抓取于 2026-09-11）。
> **未用真实凭证验证。** 报错 / 行为描述除特别标注外均为文档原文，未实测。示例复用 [auth-and-signing.md](auth-and-signing.md) §4 的 `qys_call`。

## 目录

1. [先选路径：代码配置 vs 业务分类预设](#1-先选路径代码配置-vs-业务分类预设)
2. [创建合同草稿](#2-创建合同草稿)
3. [用文件添加合同文档](#3-用文件添加合同文档)
4. [用模板添加合同文档](#4-用模板添加合同文档)
5. [多文件合并添加合同文档](#5-多文件合并添加合同文档)
6. [发起合同](#6-发起合同)
7. [查模板与业务分类](#7-查模板与业务分类)
8. [合同详情与合同列表](#8-合同详情与合同列表)
9. [下载合同](#9-下载合同)
10. [其他合同管理接口（一览）](#10-其他合同管理接口一览)
11. [完整示例：本地 PDF → 草稿 → 加文档 → 发起](#11-完整示例本地-pdf--草稿--加文档--发起)
12. [注意事项与 ⚠](#12-注意事项与-)

---

## 1. 先选路径：代码配置 vs 业务分类预设

契约锁的合同 = **合同主体** + **合同文档** + **签署方**（每个公司签署方下有若干**签署动作**）。业务分类（在云平台「文件 → 业务分类」配置）决定了签署方、签署流程、模板、签署位置、回调、短信等默认值。

| 场景 | 路径 | 调用顺序 |
| --- | --- | --- |
| 签署方类型 / 数量不固定，文件每次不同（文档称"示例一"） | 代码配置 | `POST /v2/contract/draft`（`send: false`）→ `POST /v2/document/addbyfile` 或 `/addbytemplate` → `POST /v2/contract/send`（带签署位置） |
| 签署方固定，业务分类里已配好模板、签署方、签署位置（"示例二"） | 业务分类预设 | `POST /v2/contract/draft`（`category` + `templateParams` + `send: true`），一步创建并发起 |

关键约束（文档原文）：

- **合同文档在发起前必须存在**。`send: true` 但既没有业务分类模板、也没加文档 → `1401 DOCUMENT REQUIRED`。
- 发起后不能再添加文档、指定签署位置；**只有草稿状态的合同能加文档**（否则 `1101 INVALID CONTRACT STATUS`）。
- 业务分类"预设签署方"时，传入的签署方必须与配置**数量、类型、顺序完全一致**（否则 `1301 CATEGORY CONFIG NOT MATCH`），此时使用配置的签署动作 / 位置 / 印章，接口不用传 `actions`。
- 业务分类"非预设签署方"时以接口传入为准，公司签署方必须传 `actions`（否则 `1103 ACTION REQUIRED`）。
- 发起方的签署流程单独配置（"内部流程设置"）：预设时用配置的签署动作、印章、操作人、位置；非预设时要主动传。
- 不传 `category` 时使用云平台的"默认业务分类"（通常什么都没配）。

## 2. 创建合同草稿

**Endpoint**: `POST /v2/contract/draft`（`application/json;charset=UTF-8`）
**用途**: 创建合同草稿，可选同时发起（`send: true`）。草稿阶段可以用同一个 `id` 或 `bizId` 再调一次**覆盖修改**。草稿超过 1 年不发起会被自动删除。

**关键参数（Contract）**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `subject` | String(100) | 条件 | 合同名称；业务分类没配"文件主题按规则生成"时必传 |
| `signatories` | List<Signatory> | 是 | 签署方（公司 / 个人），顺序见 `serialNo` |
| `send` | Boolean | 否 | 是否创建即发起；代码配置路径传 `false`。⚠ 默认值文档未说明 |
| `ordinal` | Boolean | 否 | 是否顺序签署，**默认 true** |
| `bizId` | String(50) | 否 | 你方业务 ID，一个合同一个、不能重复；**草稿状态下同一 bizId 再创建会覆盖之前的草稿** |
| `category` | `{id}` 或 `{name}` | 否 | 业务分类；`id` 为空时按 `name` 匹配，要保证名字唯一。不传用默认业务分类 |
| `creator` | User | 否 | 创建人，默认虚拟用户；必须已加入对接方公司。**草稿只有创建人能在云平台看到** |
| `tenantName` | String(100) | 否 | 以子公司身份发起时传子公司名 |
| `expireTime` | String | 否 | 截止签署时间 `yyyy-MM-dd HH:mm:ss`；距发起超过 2 年会被自动改为发起时间 + 2 年 |
| `endTime` | String | 否 | 合同到期时间，会被重置为当天 23:59:59 |
| `templateParams` | List<`{name, value, readOnly}`> | 否 | 业务分类里模板的参数值（文本 / 单选 / 多选 / 日期 / 图片 base64 / 动态表格，规则见 §4） |
| `signFlowStrategy` | String | 否 | `ALL_SIGN_FINISH`（所有接收方签完才完成）/ `ANY_SIGN_FINISH`（任一接收方签完即完成） |
| `callbackUrl` | String(300) | 否 | 本合同的回调地址；不传则回调到应用配置的地址（见 [callbacks.md](callbacks.md)） |
| `businessData` | String(100) | 否 | 自定义业务数据，合同回调时原样带回 |
| `notifySponsor` | boolean | 否 | 发起时是否通知发起方经办人，默认 `false` |
| `stamperRule` | String | 否 | `MUST_FORBID` / `MUST_ALLOW` / `OPTIONAL`，不传以业务分类为准 |
| `copySendTime` / `copySendReceivers` | | 否 | 抄送时机 `SEND` / `FINISH` 与抄送人 |
| `sn`、`description`、`tags`、`relatedContractIds`（≤50）、`customFields` | | 否 | 编号、描述、标签、关联合同、自定义字段 |

**Signatory（签署方）**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `tenantType` | 是 | `COMPANY` / `PERSONAL` |
| `tenantName` | 条件 | 公司全名或个人姓名；`delaySet` 为 false 时必填 |
| `receiver` | 条件 | 接收人（经办人）`{name, contact, contactType}`；个人签署方必填；公司**接收方**必须指定经办人，发起方无需（经办人即发起人） |
| `serialNo` | 否 | 签署顺序 |
| `actions` | 条件 | 签署动作，`tenantType=COMPANY` 时必填（业务分类预设除外） |
| `stampers` | 否 | 签署位置（个人签署方的位置放这里） |
| `attachments` | 否 | 要求签署方上传的附件 `{title, required, needSign}` |
| `userAuthInfo` | 否 | 指定个人认证信息 `{idCardNo, bankNo, bankMobile, modifyFields}` |
| `delaySet` | 否 | 延迟设置签署方信息，默认 false；配合 `/v2/contract/joinurl` 使用 |
| `signatoryNo` | 否 | 你方给签署方编的唯一编号 |
| `fixedFlow` | 否 | true = 签署节点完全由接口指定，分类预设的节点不生效 |
| `category`、`defaultCategoryAccepted` | 否 | 仅内部企业接收方生效 |
| `signValidateWay` | 否 | 仅 SaaS 用户：`SAAS_CONFIG`（默认）/ `DEFAULT` / `SIGNPWD` / `PIN` / `FACE` / `FACE_DEFAULT` |

**User（联系人）**：`contact` + `contactType`，`contactType` 取 `MOBILE` / `EMAIL` / `EMPLOYEEID` / `NUMBER` / `BIZID`；`name` 作为抄送人时必传。

**Action（签署动作）**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `type` | 是 | `COMPANY`（企业签章）/ `OPERATOR`（经办人签字）/ `LP`（法定代表人签字）/ `AUDIT`（审批）/ `PERSONAL`（审批并签字）/ `PRACTICE`（个人执业章，仅发起方内部节点） |
| `serialNo` | 否 | 执行顺序，从 0 开始 |
| `name` | 否 | 名称 |
| `corpSealIds` | 否 | 可选印章 ID 列表（≤9 个）；仅发起方和内部企业接收方生效 |
| `corpOperators` | 否 | 操作人（签章人 / 审批人）列表；`AUDIT` 节点必须有操作人（否则 `1105`） |
| `autoSign` | 否 | 是否自动签，默认 false；仅发起方企业签章动作；为 true 时业务分类不应预设签署方，且 `send` 要设 false、后续调发起接口 |
| `stampers` | 否 | 该节点的签署位置 |
| `actionNo` | 否 | 你方给节点编的唯一编号 |

**示例请求（代码配置路径，Python）**

```python
draft = qys_call("POST", "/v2/contract/draft", json_body={
    "subject": "劳动合同-张三",
    "bizId": "HR-2026-0001",
    "send": False,                      # 先建草稿，加完文档再发起
    "ordinal": True,                    # 顺序签署（默认即 true）
    "signatories": [
        {   # 发起方公司：先盖公章
            "tenantType": "COMPANY",
            "tenantName": "示例科技有限公司",
            "serialNo": 1,
            "actions": [{"type": "COMPANY", "serialNo": 1, "name": "公司盖章",
                         "corpSealIds": [2490828768980361630]}],
        },
        {   # 个人接收方：后签字
            "tenantType": "PERSONAL",
            "tenantName": "张三",
            "serialNo": 2,
            "receiver": {"name": "张三", "contact": "13800000000", "contactType": "MOBILE"},
        },
    ],
})
contract_id = draft["id"]
company_action_id = draft["signatories"][0]["actions"][0]["id"]   # 发起时指定公章位置要用
personal_signatory_id = draft["signatories"][1]["id"]             # 指定个人签名位置要用
```

**示例请求（业务分类预设，一步发起，curl）**

```bash
curl -sS -X POST "$QYS_BASE_URL/v2/contract/draft" \
  -H "x-qys-open-accesstoken: $QYS_APP_TOKEN" -H "x-qys-open-timestamp: $TS" \
  -H "x-qys-open-nonce: $NONCE" -H "x-qys-open-signature: $SIG" \
  -H 'Content-Type: application/json' \
  -d '{"subject":"劳动合同-张三","category":{"name":"人事合同"},"send":true,
       "signatories":[{"tenantType":"COMPANY","tenantName":"示例科技有限公司"},
                      {"tenantType":"PERSONAL","tenantName":"张三",
                       "receiver":{"contact":"13800000000","contactType":"MOBILE"}}],
       "templateParams":[{"name":"乙方姓名","value":"张三"}]}'
```

**示例响应**：`result` 与请求结构相同，多了返回值字段：`id`（合同 ID）、`status`（`DRAFT` 等）、`signatories[].id`、`signatories[].actions[].id`、`documents[]`（业务分类带模板时有）。

**注意事项**

- 创建草稿返回的 `signatories[].id`（签署方 ID）和 `actions[].id`（签署节点 ID）要保存下来：发起时指定签署位置、催签、签署方编辑都要用。
- 草稿态合同只有 `creator` 能在云平台看到；想让同事在云平台接着编辑，传 `creator`（FAQ 原文）。
- 签署方重复 → `1102 DUPLICATE SIGNATORY`；公司签署方缺动作 → `1103`；缺签署方 → `1113`；审批缺操作人 → `1105`；经办人找不到 / 已离职 / 未注册 → `1701` / `1702` / `1705`；模板里发起方必填参数没填 → `1116`（错误码文档原文，完整表见 [errors-and-limits.md](errors-and-limits.md)）。
- 接收方手机号已实名、但传入的姓名与实名不符时，发起报"用户认证信息与合同经办人信息不匹配"（FAQ 原文）。
- ⚠ 文档自相矛盾：参数表里动作的印章 / 操作人字段叫 `corpSealIds` / `corpOperators`，但同页 Http 示例用 `operators`，C# / Python SDK 示例用 `SealId` / `set_sealId`（单个）、`set_operators`。手写 JSON 以参数表为准；用 SDK 时照 SDK 的方法名。
- ⚠ 文档自相矛盾：Stamper 在草稿接口里 `documentId` 标"必填"，描述却是"文件模板 id"；而发起 / 加文档接口里的 `documentId` 是合同文档 ID。草稿阶段还没有文档时，签署位置放到发起接口里指定更稳妥。

## 3. 用文件添加合同文档

**Endpoint**: `POST /v2/document/addbyfile`（**`multipart/form-data`**，不是 JSON）
**用途**: 上传本地文件作为草稿合同的一份合同文档。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `contractId` / `bizId` | String | 二选一 | 用 `bizId` 且合同以子公司身份创建时要带 `tenantName` |
| `title` | String(100) | 是 | 文档名称 |
| `file` | 文件 | 是 | ≤ 50MB |
| `fileSuffix` | String | 是 | `doc` `docx` `pdf` `jpeg` `png` `jpg` `gif` `tiff` `html` `htm` `xls` `xlsx`，**必须与文件真实类型一致** |
| `documentSort` | Integer | 否 | 文档排序 |
| `stampers` | List<Stamper> | 否 | 签署位置（公司位置用 `actionId`，个人位置用 `signatoryId`，见 [signing.md](signing.md) §3） |
| `stamperRule` | String | 否 | 同草稿接口 |

```python
with open("劳动合同.pdf", "rb") as f:
    doc = qys_call("POST", "/v2/document/addbyfile",
                   data={"contractId": contract_id, "title": "劳动合同", "fileSuffix": "pdf"},
                   files={"file": ("劳动合同.pdf", f, "application/pdf")})
document_id = doc["documentId"]
```

```bash
curl -sS -X POST "$QYS_BASE_URL/v2/document/addbyfile" \
  -H "x-qys-open-accesstoken: $QYS_APP_TOKEN" -H "x-qys-open-timestamp: $TS" \
  -H "x-qys-open-nonce: $NONCE" -H "x-qys-open-signature: $SIG" \
  -F "contractId=$CONTRACT_ID" -F "title=劳动合同" -F "fileSuffix=pdf" -F "file=@劳动合同.pdf"
```

**示例响应**：`result.documentId`（合同文档 ID）。
**注意事项**：Word 文件经 aspose 转换可能导致行距变化、文档变长，**用坐标定位的签署位置会错位，用关键字定位才会跟着内容走**（FAQ 原文）。文件损坏 / 类型不对 → `1403 INVALID FILE`。
⚠ 文档未说明：multipart 请求里 `stampers`（List）字段怎么编码（JSON 字符串还是多个表单字段）。需要位置时建议留到发起接口里用 JSON 指定。

## 4. 用模板添加合同文档

**Endpoint**: `POST /v2/document/addbytemplate`（JSON）
**用途**: 用云平台「文件模板」生成一份合同文档，并填入模板参数。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `contractId` / `bizId` | String | 二选一 | |
| `title` | String(100) | 是 | 文档名称 |
| `templateId` | String | 是 | **云平台**文件模板 ID（开放平台控制台的旧模板不能用） |
| `templateParams` | List<TemplateParam> | 条件 | 参数模板必填 |
| `documentSort`、`stampers`、`stamperRule` | | 否 | 同上 |

TemplateParam：`name`（参数名）、`value`（字符串）、`signatoryId`（参数填写方）、`readOnly`。`value` 规则（文档原文）：

- 普通文本 ≤ 1000 字（html 模板单行文本 ≤ 300）；日期 `yyyy-MM-dd`；身份证号 15 / 18 位；
- 单选传选项名；多选传选项名、逗号分隔；
- 图片传 `data:image/png;base64,...`（带前缀，按实际格式）；
- 动态表格传 JSON 字符串：`[{"column1":"1","column2":"2"}, ...]`；新版 HTML 编辑器还支持二维数组 `[["1","2"],["3","4"]]`。

```python
doc = qys_call("POST", "/v2/document/addbytemplate", json_body={
    "contractId": contract_id,
    "title": "劳动合同",
    "templateId": "2492236993899110515",
    "templateParams": [{"name": "乙方姓名", "value": "张三"},
                       {"name": "入职日期", "value": "2026-10-01"}],
})
```

**注意事项**：模板 ID 在云平台模板名称旁的 ID 图标里看，或用 §7 的模板列表接口查。Word 模板里参数写成 `{{参数名}}`，花括号要英文半角；同名参数会被同一个值替换（FAQ 原文）。"没有使用模板的权限 / 模板 Id 无效"通常是用了开放平台控制台的旧模板。

## 5. 多文件合并添加合同文档

**Endpoint**: `POST /v2/document/addbyfiles`（multipart）
**用途**: 多个本地文件**合并成一份**合同文档。参数：`contractId`/`bizId`、`tenantName`、`title`（必填）、`files`（必填，总大小 ≤ 50M）、`documentSort`。返回 `result.documentId`。
⚠ 文档自相矛盾：参数表没有 `fileSuffix`，但 Http 示例末尾带了 `fileSuffix=pdf`；返回参数写 `code`（Integer）。

## 6. 发起合同

**Endpoint**: `POST /v2/contract/send`（JSON）
**用途**: 发起草稿状态的合同，同时可指定签署位置。发起后签署方收到签署通知。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `contractId` / `bizId` | String | 二选一 | |
| `tenantName` | String | 否 | 用 bizId 且以子公司身份创建时带 |
| `stampers` | List<Stamper> | 否 | 签署位置：**公司位置必须带 `actionId`，个人位置必须带 `signatoryId`**，都要带 `documentId`（合同文档 ID） |
| `stamperRule` | String | 否 | |
| `locateAllStamperKeywords` | Boolean | 否 | 默认 true：所有关键字都必须找到，否则失败；false 时找到任意一个即可 |

```python
qys_call("POST", "/v2/contract/send", json_body={
    "contractId": contract_id,
    "stampers": [
        {"actionId": company_action_id, "documentId": document_id, "type": "COMPANY",
         "keyword": "甲方（盖章）", "offsetX": 0.05, "offsetY": -0.02},
        {"actionId": company_action_id, "documentId": document_id, "type": "TIMESTAMP",
         "keyword": "甲方（盖章）", "offsetX": 0.05, "offsetY": -0.08},
        {"signatoryId": personal_signatory_id, "documentId": document_id, "type": "PERSONAL",
         "keyword": "乙方（签字）", "offsetX": 0.05, "offsetY": -0.02},
    ],
})
```

**示例响应**：只有 `responseCode` / `message`，没有 `result`。
**注意事项**：只能发起草稿态合同（`1101`）；关键字没找到 → `1108 KEYWORD NOT FOUND`；页码超出 → `1109`；印章状态不对 → `1203`。坐标规则见 [signing.md](signing.md) §3。

## 7. 查模板与业务分类

| Endpoint | 用途 | 关键参数 | 关键返回 |
| --- | --- | --- | --- |
| `GET /v2/template/list` | 模板列表（含子公司） | `tenantName`、`selectOffset`（默认 0）、`selectLimit`（默认 1000）、`modifyTimeStart/End` | `totalCount`、`list[].id/name/state/parameters[{name,required,type}]` |
| `GET /v2/template/detail` | 模板详情 | `templateId`（必填） | `parameters[].options/defaultValue`（单选多选的可选值） |
| `GET /v2/category/list` | 业务分类列表 | `tenantName`、`selectOffset`、`selectLimit`、`modifyTimeStart/End` | `list[].id/name/createTime` |
| `GET /v2/category/detail` | 业务分类详情 | `categoryId` 或 `categoryName`（二选一）、`tenantName` | `templates[]`、`defineSignatories`、`defineSponsor`、`signatories[].actions[]` |

- 分页用 `selectOffset` + `selectLimit`（偏移量，不是页码）。
- 按业务分类发起前先调 `/v2/category/detail` 看 `defineSignatories`：true 时草稿接口的签署方必须和 `signatories` 一一对应。
- ⚠ 文档自相矛盾：`/v2/category/detail` 页的 Http 示例写的是 `GET /v2/category/list?categoryId=...`；模板详情页"公司不存在"写 `11041805`，其他页写 `11041801`。

## 8. 合同详情与合同列表

### 合同详情
**Endpoint**: `GET /v2/contract/detail`
**关键参数**：`contractId` 或 `bizId`（二选一，bizId + 子公司时带 `tenantName`）；可选 `queryActionOperator`、`queryLocation`、`queryRelatedContract`、`querySealStats`、`queryOperatorRealInfo`（都是 Boolean）。
**关键返回（result = Contract）**：`id`、`bizId`、`subject`、`status`、`signatories[].{id,tenantType,status,tenantName,receiver,actions[].{id,type,status,sealId,operators}}`、`documents[].{id,title,pageCount,contentType}`、`expireTime`、`publishTime`、`comments`（撤回 / 退回原因）、`invalidReason`、`businessData`。

合同状态 `status`：`DRAFT`（草稿）`FILLING`（拟定中）`SIGNING`（签署中）`COMPLETE`（已完成）`REJECTED`（已退回）`RECALLED`（已撤回）`EXPIRED`（已截止签署）`INVALIDING`（作废中）`INVALIDED`（已作废）`FORCE_END`（强制结束）。

```python
c = qys_call("GET", "/v2/contract/detail", params={"contractId": contract_id, "queryActionOperator": "true"})
if c["status"] == "COMPLETE":
    ...
```

### 合同列表
**Endpoint**: `GET /v2/contract/list`
**关键参数**：`status`、`selectOffset`（从 0）、`selectLimit`（默认 1000）、`tenantName`、`createTimeOrder`（`ASC`/`DESC`）、`categoryId`/`categoryName`、`publishTimeStart`/`publishTimeEnd`（**不传默认只查最近 6 个月**）、`signatoryType`（`SPONSOR` 默认 / `RECEIVER` / `ALL`）。
**关键返回**：`totalCount`、`list[].{id,subject,status,sn,expireTime,publishTime,category}`。

## 9. 下载合同

| Endpoint | 返回 | 关键参数 | 说明 |
| --- | --- | --- | --- |
| `GET /v2/document/download` | 单份合同文档 **PDF 文件流** | `documentId` | |
| `GET /v2/contract/download` | 合同文件 + 签署日志的 **ZIP 文件流**（默认） | `contractId`/`bizId`、`downloadItems`、`needCompressForOneFile`（单文件是否压缩，默认压缩）、`fileNameRule` | `downloadItems` 逗号分隔：`CONTRACT` `SIGNLOG` `ATTACHMENT` `NOTARY` `ENDSIGN_ATTACHMENT` `CERT`，默认 `CONTRACT,SIGNLOG` |
| `GET /v2/contract/downloadurl` | JSON：`downloadUrls[].{contractId,documentId,title,downloadItems,downloadUrl}` | 同上 + `compress`（默认 false，每个文件一个链接） | 链接**有效期 60 分钟** |
| `GET /v2/attachment/download` | 合同附件 | — | 详见文档页，未展开 |

```python
pdf = qys_call("GET", "/v2/document/download", params={"documentId": document_id}, raw=True)
open(f"contracts/{contract_id}.pdf", "wb").write(pdf)

zip_bytes = qys_call("GET", "/v2/contract/download",
                     params={"contractId": contract_id, "downloadItems": "CONTRACT"}, raw=True)
```

**频次限制（文档原文）**：同一合同文档两次下载间隔在 25 分钟内、连续 10 次后**锁定 12 小时**，锁定时间叠加。回调里收到"已完成"就下载一次并落盘，不要每次展示都去契约锁拉。
**注意**：`/v2/contract/download` 默认返回 ZIP，想直接拿 PDF 用 `/v2/document/download`（按 `documents[].id` 逐份下载），或 `needCompressForOneFile=false`。

## 10. 其他合同管理接口（一览）

| 接口 | Endpoint | 一句话 |
| --- | --- | --- |
| 抄送合同 | `POST /v2/contract/copysend` | 追加抄送人 |
| 合同延期 | `POST /v2/contract/delay` | 仅"签署中 / 已截止签署"；`days` 或 `expireDate`（二选一，同传取 days），距发起 ≤ 2 年 |
| 获取合同操作记录 | `GET /v2/contract/stream` | 签署日志流水 |
| 查询文件必填项填写详情 | `POST /v2/contract/required/detail` | |
| 修改合同 | `POST /v2/contract/contractModify` | |
| 重新发起合同 | `POST /v2/contract/resend` | 支持 `businessData` |
| 用文件添加合同附件 | `POST /v2/attachment/add` | 2026-07 新增（Java SDK 4.0.1 changelog） |
| 合同文档添加水印 | `POST /v2/contract/addwartermark` | 路径拼写就是 `wartermark` |
| 强制结束合同 | `POST /v2/contract/forceend` | `reason` 必填；见 [signing.md](signing.md) §9 |

这些接口的字段表本 skill 未展开，文档在 https://open.qiyuesuo.com/document/2725986623018775399 （接口列表）对应行。

## 11. 完整示例：本地 PDF → 草稿 → 加文档 → 发起

```python
from qys_client import qys_call

def create_and_send(pdf_path: str, employee_name: str, employee_mobile: str, seal_id: int) -> str:
    draft = qys_call("POST", "/v2/contract/draft", json_body={
        "subject": f"劳动合同-{employee_name}",
        "send": False,
        "signatories": [
            {"tenantType": "COMPANY", "tenantName": "示例科技有限公司", "serialNo": 1,
             "actions": [{"type": "COMPANY", "serialNo": 1, "corpSealIds": [seal_id]}]},
            {"tenantType": "PERSONAL", "tenantName": employee_name, "serialNo": 2,
             "receiver": {"name": employee_name, "contact": employee_mobile, "contactType": "MOBILE"}},
        ],
    })
    cid = draft["id"]
    company_action_id = draft["signatories"][0]["actions"][0]["id"]
    personal_id = draft["signatories"][1]["id"]

    with open(pdf_path, "rb") as f:
        doc_id = qys_call("POST", "/v2/document/addbyfile",
                          data={"contractId": cid, "title": "劳动合同", "fileSuffix": "pdf"},
                          files={"file": (pdf_path.rsplit("/", 1)[-1], f, "application/pdf")})["documentId"]

    qys_call("POST", "/v2/contract/send", json_body={
        "contractId": cid,
        "stampers": [
            {"actionId": company_action_id, "documentId": doc_id, "type": "COMPANY", "page": -1,
             "offsetX": 0.15, "offsetY": 0.2},
            {"signatoryId": personal_id, "documentId": doc_id, "type": "PERSONAL", "page": -1,
             "offsetX": 0.6, "offsetY": 0.2},
        ],
    })
    return cid
```

发起后公司盖章与员工签字见 [signing.md](signing.md)（`/v2/contract/companysign` + `/v2/contract/pageurl`）。

## 12. 注意事项与 ⚠

- 合同 ID、文档 ID、签署方 ID、节点 ID、印章 ID、模板 ID 都是 19 位左右的长整数。**在 JavaScript / 前端里一律当字符串处理**，避免精度丢失；文档示例里有的写成数字、有的写成字符串。
- `bizId` 是你方幂等键：推荐每份合同都传；但草稿态下重复 bizId 会**覆盖**而不是报错。
- 文档示例里大量 Boolean / 数字写成了字符串（`"offsetX": "0.1"`、`"page": "1"`、`"keywordIndex": "2"`），参数表类型是 Decimal / Integer，按参数表的类型发。
- ⚠ 文档自相矛盾：`send` 的默认值未写；Action 印章 / 操作人字段名（§2）；`addbyfiles` 的 `fileSuffix`（§5）；分类详情示例路径（§7）。
- ⚠ 文档未说明：multipart 下 `stampers` 的编码方式（§3）；下载接口失败时的响应格式（§9）。
