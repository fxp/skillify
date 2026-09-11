# OA 审批：发起、查询、处理、撤销

来源：open.dingtalk.com/document 下「发起审批实例」「获取表单 schema」「获取审批实例ID列表」「获取单个审批实例详情」
「同意或拒绝审批任务」「撤销审批实例」及对应旧版页面（抓取于 2026-09-11）。**全部为文档原文，未实测。**
本文件以**新版** `https://api.dingtalk.com/v1.0/workflow/...`（header `x-acs-dingtalk-access-token`）为主，旧版对照见第 7 节。审批事件见 `events.md`。

## 目录

1. [概念与调用顺序](#1-概念与调用顺序)
2. [获取表单 schema（拿控件 label）](#2-获取表单-schema拿控件-label)
3. [发起审批实例](#3-发起审批实例)
4. [formComponentValues 各控件的 value 写法](#4-formcomponentvalues-各控件的-value-写法)
5. [查询：实例 ID 列表 → 实例详情](#5-查询实例-id-列表--实例详情)
6. [处理与撤销](#6-处理与撤销)
7. [旧版接口对照](#7-旧版接口对照)
8. [⚠ 未说明 / 矛盾之处](#8--未说明--矛盾之处)

---

## 1. 概念与调用顺序

| 名词 | 说明 |
| --- | --- |
| processCode | 审批模板唯一码，形如 `PROC-...`，在审批模板编辑页 URL 里能看到 |
| processInstanceId | 审批实例 ID（发起接口返回的 `instanceId`） |
| taskId | 审批任务 ID，从实例详情的 `tasks[]` 取；同意 / 拒绝要用它 |
| originatorUserId | 发起人 userid |

典型顺序：**schema（知道控件叫什么）→ 发起 → 订阅 `bpms_instance_change` 事件或轮询详情 → 处理 / 撤销**。
文档原文："发起审批实例后，无法通过API修改审批实例信息"；"假勤、人事、财税、法务、商旅等套件暂不支持直接通过本接口发起审批实例"。

---

## 2. 获取表单 schema（拿控件 label）

**Endpoint**: `GET https://api.dingtalk.com/v1.0/workflow/forms/schemas/processCodes?processCode=PROC-xxx`
**权限**: `Workflow.Form.Read`。文档原文："第三方企业应用没有权限获取组织内的表单schema"。

| 参数（query） | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| processCode | String | 是 | 模板唯一码 |
| appUuid | String | 否 | 应用搭建隔离信息 |

响应关键路径：`result.schemaContent.items[]`，每个控件 `componentName`（TextField / DDSelectField / DDMultiSelectField / DDDateField /
DDDateRangeField / TextNote …）、`props.id`、`props.label`、`props.required`、`props.options`（单选选项）、`props.bizAlias`。

```python
import requests

def form_labels(token: str, process_code: str) -> list[dict]:
    r = requests.get("https://api.dingtalk.com/v1.0/workflow/forms/schemas/processCodes",
                     headers={"x-acs-dingtalk-access-token": token},
                     params={"processCode": process_code}, timeout=10)
    r.raise_for_status()
    items = r.json()["result"]["schemaContent"]["items"]
    return [{"type": i["componentName"], **{k: i["props"].get(k) for k in ("id", "label", "required", "options")}}
            for i in items]
```

---

## 3. 发起审批实例

**Endpoint**: `POST https://api.dingtalk.com/v1.0/workflow/processInstances`
**权限**: `Workflow.Instance.Write`；企业内部应用、第三方企业应用均可。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| originatorUserId | String | 是 | 发起人 userid |
| processCode | String | 是 | 模板唯一码 |
| deptId | Long | 否 | 发起人部门。**不传 approvers（复用后台审批流）时必填**；根部门填 **-1**（⚠ 示例写的是 1） |
| microappAgentId | Long | 否 | 应用 AgentId |
| formComponentValues | Array | 是 | 表单值，≤150 项；每项 `name`（必填，= 模板控件 label）、`value`（必填，字符串，≤65535）、`id`/`bizAlias`/`extValue`/`componentType`/`details` 可选 |
| approvers | Array | 否 | 直接指定审批人（会**覆盖**后台审批流），≤20 项：`{actionType: AND/OR/NONE, userIds: [...]}` |
| targetSelectActioners | Array | 否 | 复用后台审批流且有"发起人自选"节点时必填：`{actionerKey, actionerUserIds}`；actionerKey 从「获取审批单流程中的节点信息」拿 |
| ccList | Array | 否 | 抄送 userid，≤50；**复用后台审批流时不生效** |
| ccPosition | String | 否 | START / FINISH / START_FINISH；复用后台审批流时不生效 |
| bizDetailPageUrl | String | 否 | 三方审批单详情页，OA 高级版专享（否则 `benefitStatusInvalid`） |

两种发起方式（文档原文要点）：
- **不传 approvers**：审批人、抄送人都复用后台设置（支持或签、会签、条件审批、自选等）；接口里传的 ccList / ccPosition 不生效；
  若流程里有自选节点，要传 `targetSelectActioners`。
- **传 approvers**：不复用后台审批流，**模板的高级设置（手写签名、表单操作权限等）全部失效**；也不能把审批人设为"发起人自选"。

```python
import json, requests

def start_approval(token: str, originator: str, dept_id: int, process_code: str, fields: dict) -> str:
    body = {
        "originatorUserId": originator,
        "processCode": process_code,
        "deptId": dept_id,                           # 根部门 -1
        "formComponentValues": [{"name": k, "value": v} for k, v in fields.items()],
    }
    r = requests.post("https://api.dingtalk.com/v1.0/workflow/processInstances",
                      headers={"x-acs-dingtalk-access-token": token}, json=body, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(r.text)                   # 如 400 {"code":"formConverterError","message":"表单数据校验失败，失败控件：..."}
    return r.json()["instanceId"]

start_approval(token, "manager432", -1, "PROC-XXXX", {
    "单行输入框": "采购笔记本",
    "数字输入框": "3",
    "多选框": json.dumps(["选项1", "选项2"], ensure_ascii=False),   # 多选：数组转字符串
    "日期": "2026-09-11",                                         # 只支持 yyyy-MM-dd
})
```

**示例响应**：`{"instanceId": "91ef1076-c3ed-4a78-xxxx-fa29ef2d6252"}`

**常见错误**（文档原文）：`processCodeError`（模板不存在或已删除）、`processInstanceInvalidParameter`（发起人/审批人/抄送人 userid 错、部门错、发起人不在部门中）、
`invalidParameter`（企业 ID、模板 code 错或发起人已离职）、`formConverterError`（表单校验失败，会带失败控件名）、`targetSelectApproverMissing`、
`needAuth`、`autoflowLikeTriggerRateLimited`（业务规则触发限速）。

文档"特别提醒"：后续将加强校验——单选 / 多选值必须在选项列表里、联系人必须是在职 userid、部门 ID 必须合法、关联审批单 ID 必须存在，
"违背以上规则发起的审批单，后期…有发起失败的风险"。

---

## 4. formComponentValues 各控件的 value 写法

**所有 value 都是字符串**；结构化数据要先 JSON 序列化成字符串（文档示例注释原文："如果数据是 json 格式，也需要先转义为字符串格式"）。

| 控件 | name | value 示例 | 备注 |
| --- | --- | --- | --- |
| 单行 / 多行 / 数字 / 金额 / 评分 | 控件 label | `"100"` | 数字也用字符串 |
| 单选 | label | `"选项1"` | 必须是配置过的选项 |
| 多选 | label | `"[\"选项1\",\"选项2\"]"` | 即使只选一个也要数组 |
| 日期 | label | `"2021-08-17"` | 只支持 `yyyy-MM-dd` |
| 日期区间 | **`"[\"开始时间\",\"结束时间\"]"`** | `"[\"2019-02-19\",\"2019-02-25\"]"` | name 本身也是数组字符串 |
| 图片 | label | `"[\"http://url1\",\"http://url2\"]"` | |
| 明细（表格） | label | `"[[{\"name\":\"单行输入框\",\"value\":\"x\"},{\"name\":\"数字输入框\",\"value\":\"100\"}]]"` | 二维数组：每行一个数组 |
| 附件 | label | `"[{\"spaceId\":\"...\",\"fileName\":\"a.jpg\",\"fileSize\":\"333\",\"fileType\":\"jpg\",\"fileId\":\"...\"}]"` | 五个字段都要，来自审批钉盘上传 |
| 联系人 | label | `"[\"4525xxxx77041\"]"` | userid 数组 |
| 关联审批单 | label | `"[\"fa2aa864-...\"]"` | 实例 ID 数组 |
| 部门 | label | `"部门id1,部门id2"` | **逗号分隔，不是数组** |
| 省市区 | label | `"北京,北京市,河东区"` | 英文逗号 |
| 电话 | label | `"157xxxx4545"` | 国内号码 +86 可省 |
| 当前时间 + 地点 | `"[\"当前时间\",\"当前地点\"]"` | `"[\"2025-01-03 14:27:20\",120.021195,30.281506,\"地址\",100]"` | |

"该接口当前尚未支持审批应用中的所有控件，以以下列出示例的控件为准"（文档原文）。

---

## 5. 查询：实例 ID 列表 → 实例详情

### 获取审批实例 ID 列表

**Endpoint**: `POST https://api.dingtalk.com/v1.0/workflow/processes/instanceIds/query`（仅企业内部应用，`Workflow.Instance.Read`）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| processCode | String | 是 | |
| startTime | Long | 是 | 毫秒时间戳；只传 startTime 时距今 ≤120 天 |
| endTime | Long | 否 | 与 startTime 跨度 ≤120 天，且 startTime 距今 ≤365 天 |
| nextToken | Long | 是 | 首次传 0，之后传返回的 nextToken |
| maxResults | Long | 是 | **最多 20** |
| userIds | Array | 否 | 发起人，≤10 个 |
| statuses | Array | 否 | RUNNING / TERMINATED / COMPLETED，不传为全部 |

响应：`{"result": {"list": ["123"], "nextToken": "10"}, "success": true}`——`nextToken` **不为空表示还有数据**，且返回的是字符串。
循环获取的实例 ID 总数最多 10000（文档原文）。OA 高级版可查 5 年内数据。

```python
def list_instance_ids(token: str, process_code: str, start_ms: int, end_ms: int) -> list[str]:
    ids, nxt = [], 0
    while True:
        r = requests.post("https://api.dingtalk.com/v1.0/workflow/processes/instanceIds/query",
                          headers={"x-acs-dingtalk-access-token": token},
                          json={"processCode": process_code, "startTime": start_ms, "endTime": end_ms,
                                "nextToken": nxt, "maxResults": 20}, timeout=10)
        r.raise_for_status()
        res = r.json()["result"]
        ids.extend(res.get("list", []))
        if not res.get("nextToken"):
            return ids
        nxt = int(res["nextToken"])      # 请求类型是 Long，响应是 String
```

### 获取单个审批实例详情

**Endpoint**: `GET https://api.dingtalk.com/v1.0/workflow/processInstances?processInstanceId=...`（`Workflow.Instance.Read`）

**判断"审批通过"要同时看两个字段**（文档原文）：`status == "COMPLETED"` **且** `result == "agree"`。
`status` 只有 RUNNING / TERMINATED（已撤销）/ COMPLETED；被拒绝的单子也是 COMPLETED，只是 `result == "refuse"`。

| 字段（`result` 下） | 说明 |
| --- | --- |
| title / businessId / originatorUserId / originatorDeptId（-1 为根部门） | 基础信息 |
| status / result | 见上 |
| approverUserIds | **只有接口发起的单子才返回**；在 OA 应用手动发起的不返回 |
| tasks[] | `taskId`、`userId`、`status`（NEW/RUNNING/PAUSED/CANCELED/COMPLETED/TERMINATED）、`result`（AGREE/REFUSE/REDIRECTED）、`activityId`、`pcUrl`、`mobileUrl` |
| operationRecords[] | `userId`、`date`、`type`（EXECUTE_TASK_NORMAL / START_PROCESS_INSTANCE / TERMINATE_PROCESS_INSTANCE / ADD_REMARK …）、`result`、`remark` |
| formComponentValues[] | `id`、`name`、`value`、`extValue`、`componentType`、`bizAlias` |
| bizAction | MODIFY / REVOKE / NONE |

注意大小写：实例级 `result` 是小写 `agree/refuse`，任务级和操作记录里是大写 `AGREE/REFUSE`。
时间字段示例为 `"2022-08-31T11:52Z"` 形式的字符串（与事件体里的毫秒时间戳不同）。

---

## 6. 处理与撤销

### 同意或拒绝审批任务

**Endpoint**: `POST https://api.dingtalk.com/v1.0/workflow/processInstances/execute`（仅企业内部应用）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| processInstanceId | String | 是 | |
| taskId | Long | 是 | 从实例详情 `tasks[]` 取 |
| actionerUserId | String | 是 | 操作人 userid（任务处理人） |
| result | String | 是 | `agree` / `refuse` |
| remark | String | 否 | 审批意见，≤1024 |
| file | Object | 否 | `photos[]`、`attachments[{spaceId,fileSize,fileId,fileName,fileType}]`（≤20） |

多人审批时同意单个任务只会流转到下一个审批人；拒绝单个任务则流程结束（文档原文）。响应 `{"result": true, "success": true}`。

### 撤销审批实例

**Endpoint**: `POST https://api.dingtalk.com/v1.0/workflow/processInstances/terminate`（仅企业内部应用）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| processInstanceId | String | 是 | |
| isSystem | Boolean | 否（⚠ 见下） | true 系统直接终止；false 由指定操作者终止 |
| operatingUserId | String | 否 | isSystem=false 时必传，且须是**发起人** |
| remark | String | 否 | ≤1024 |

前置条件（文档原文）：
- **发起后 15 秒内不能撤销**（`aflowProcessInstStatusException`）；已完成的实例不能撤销。
- 必须先在 OA 审批管理后台该模板「高级设置 → 撤销/修改审批单」勾选"允许提交人撤销审批中的审批单"，否则报
  `errcode:820008 … 审批系统错误`（您没有任务处理的权限）。这是后台配置问题，重试无效。

---

## 7. 旧版接口对照

（均为 `https://oapi.dingtalk.com<path>?access_token=...`，参数未逐一转录，新代码优先用新版）

| 能力 | 旧版 path | 新版 |
| --- | --- | --- |
| 发起实例 | `POST /topapi/processinstance/create` | `POST /v1.0/workflow/processInstances` |
| 实例详情 | `POST /topapi/processinstance/get` | `GET /v1.0/workflow/processInstances` |
| 实例 ID 列表 | `POST /topapi/processinstance/listids` | `POST /v1.0/workflow/processes/instanceIds/query` |
| 同意 / 拒绝 | `POST /topapi/process/instance/execute` | `POST /v1.0/workflow/processInstances/execute` |
| 撤销 | `POST /topapi/process/instance/terminate` | `POST /v1.0/workflow/processInstances/terminate` |
| 添加评论 | `POST /topapi/process/instance/comment/add` | 本 skill 未覆盖 |
| 用户可见模板 | `POST /topapi/process/listbyuserid` | `GET /v1.0/workflow/processes/userVisibilities/templates` |
| 待审批数量 | `POST /topapi/process/gettodonum` | 本 skill 未覆盖 |
| 附件下载 | `POST /topapi/processinstance/file/url/get` | 本 skill 未覆盖 |
| 创建 / 更新模板 | `POST /topapi/process/save` | `POST /v1.0/workflow/forms` |

新旧字段风格不同：旧版 `process_code`、`originator_user_id`（snake_case，token 放 query），新版 `processCode`、`originatorUserId`。
错误码体系也不同：旧版是数字 `errcode`（HTTP 200），新版是字符串 `code`（HTTP 4xx/5xx），⚠ 两套错误码的对应关系文档未说明。

---

## 8. ⚠ 未说明 / 矛盾之处

- `deptId` 根部门：参数说明写"若为根部门ID需填-1"，请求示例写 `"deptId": 1`；通讯录接口里根部门又是 1 ⚠ 文档自相矛盾。
- `terminate` 的 `isSystem` 参数表标"否"，错误码表却有 `invalidInstanceTerminateIsSystem`（"是否通过系统操作参数不能为空"）⚠ 文档自相矛盾——建议总是显式传。
- 发起接口请求示例里有一个参数表没有的 `"RequestId"` 字段 ⚠ 文档未说明。
- 实例 ID 列表示例的 startTime 与 endTime 取值相同，⚠ 仅为占位。
- 同意 / 拒绝接口页的错误码表为空 ⚠ 文档未说明。
