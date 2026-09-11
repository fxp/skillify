# 审批（原生审批 approval/v4）

来源：`open.feishu.cn/document/server-docs/approval-v4/*`（抓取于 2026-09-11）。
Base URL `https://open.feishu.cn/open-apis`；本域接口基本只接受 **tenant_access_token**（查询用户任务列表还接受 user_access_token）。
**报错码与行为描述除标注「无凭证探测」外均为文档原文，未实测。** 三方审批（外部审批系统同步）不在本文范围。

## 目录

1. [概念：定义、实例、任务、表单控件](#1-概念)
2. [接入前提与关键 ID 从哪来](#2-接入前提与关键-id)
3. [查看审批定义（拿表单结构和节点）](#3-查看审批定义)
4. [创建审批实例](#4-创建审批实例)
5. [表单控件值 form 怎么写](#5-表单控件值)
6. [上传附件 / 图片（特殊域名）](#6-上传附件--图片)
7. [查实例：详情、按定义批量取 ID、条件查询](#7-查实例)
8. [处理任务：同意、拒绝、转交；撤回实例](#8-处理任务与撤回)
9. [查任务列表](#9-查任务列表)
10. [审批事件（必须先调 subscribe）](#10-审批事件)
11. [错误码与 FAQ 要点](#11-错误码与-faq-要点)
12. [容易写错的地方](#12-容易写错的地方)

---

## 1. 概念

| 资源 | 标识 | 说明 |
|---|---|---|
| 审批定义 | `approval_code`（形如 `7C468A54-8745-2245-9675-08B7C63E7A85`） | 一类审批（请假、报销）的表单 + 流程 |
| 审批实例 | `instance_code` | 员工发起的一次审批；接口路径里叫 `instance_id` |
| 审批任务 | `task_id` | 实例流转到某节点时给每个审批人生成的任务 |
| 节点 | `node_id` / `custom_node_id` | 流程中的审批节点 |
| 表单控件 | 控件 `id` | 在开发者模式下可自定义 ID |

实例状态：`PENDING` 审批中、`APPROVED` 通过、`REJECTED` 拒绝、`CANCELED` 撤回、`DELETED` 删除（定义被停用 / 删除）。
事件里还有 `REVERTED`（撤销已通过的审批）、`OVERTIME_CLOSE`、`OVERTIME_RECOVER`。
任务状态：`PENDING`、`APPROVED`、`REJECTED`、`TRANSFERRED`、`DONE`。
审批方式：`AND` 会签、`OR` 或签、`AUTO_PASS`、`AUTO_REJECT`、`SEQUENTIAL`。

---

## 2. 接入前提与关键 ID

- 权限：`approval:approval`（查看、创建、更新、删除审批应用相关信息），或更细的 `approval:instance`、`approval:task`、`approval:definition`、`approval:approval:readonly`。
- 需要使用审批的员工要在应用**可用范围**内。
- **tenant_access_token 在审批域默认拥有租户下所有审批数据**（文档提醒审核时注意管控）。
- **approval_code 获取**：打开 `https://www.feishu.cn/approval/admin/approvalList?devMode=on`（开发者模式，可给控件和节点设置自定义 ID），
  编辑某个审批，浏览器地址栏的 `definitionCode=...` 就是 approval_code。拿到它就能读该定义下所有数据，注意保密。
- **建议在审批管理后台创建审批定义**，不建议用 API：API 创建的定义**无法删除**，API 方式一般用于商店应用（`POST /open-apis/approval/v4/approvals`）。

---

## 3. 查看审批定义

**Endpoint**: `GET /open-apis/approval/v4/approvals/:approval_code`
**用途**: 拿到表单控件列表（每个控件的 `id`、`type`、单选多选的选项 value、金额币种）和节点列表（`node_id`、`custom_node_id`），创建实例前必调。频控 100 次/分钟。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `approval_code` | path | string | 是 | |
| `locale` | query | string | 否 | `zh-CN` / `en-US` / `ja-JP` 等 |
| `user_id_type` | query | string | 否 | 默认 `open_id` |

```bash
curl -s "https://open.feishu.cn/open-apis/approval/v4/approvals/$APPROVAL_CODE?locale=zh-CN" \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN"
```

响应 `data.form` 是**JSON 字符串**，要再 `json.loads` 一次才能拿到控件数组；`data.node_list` 里有节点 ID。

---

## 4. 创建审批实例

**Endpoint**: `POST /open-apis/approval/v4/instances`
**用途**: 以某员工身份发起一个审批。频控 **100 次/分钟**。只接受 tenant_access_token。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `approval_code` | string | 是 | 审批定义 Code |
| `user_id` / `open_id` | string | 二选一 | 发起人；**两个都传时优先 user_id**。注意这里不走 `user_id_type`，字段名本身区分类型 |
| `form` | **string** | 是 | 控件值数组 **JSON 序列化后的字符串**，见第 5 节 |
| `department_id` | string | 否 | 发起人部门；只属于一个部门可不填，多部门不填取第一个；**必须是 `department_id` 类型（不是 od-），不能是根部门** |
| `node_approver_user_id_list` / `node_approver_open_id_list` | object[] | 否 | 流程里有"发起人自选审批人"节点时必填：`[{"key": "<node_id 或 custom_node_id>", "value": ["<用户ID>"]}]`；同时传取并集 |
| `node_cc_user_id_list` / `node_cc_open_id_list` | object[] | 否 | 自选抄送人，≤20 |
| `uuid` | string | 否 | 幂等键，1–64 字符；**同一 uuid 只能创建一个实例，冲突报 60012** |
| `allow_resubmit` / `allow_submit_again` / `forbid_revoke` | boolean | 否 | 退回后可重新提交 / 显示"再次提交" / 禁止撤销（默认 false） |
| `cancel_bot_notification` | string | 否 | 位运算：`1` 取消通过推送、`2` 取消拒绝推送、`4` 取消撤回推送，组合相加如 `"3"` |
| `title` + `i18n_resources` | — | 否 | 自定义实例标题：`title` 填 `@i18n@` 开头的 key，在 `i18n_resources[].texts` 里赋值 |
| `node_auto_approval_list` | object[] | 否 | 设置自动通过的节点，≤10 |

**示例请求**

```bash
curl -s -X POST 'https://open.feishu.cn/open-apis/approval/v4/instances' \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN" -H 'Content-Type: application/json; charset=utf-8' \
  -d '{"approval_code":"7C468A54-8745-2245-9675-08B7C63E7A85","open_id":"ou_3cda9c969f737aaa05e6915dce306cb9","form":"[{\"id\":\"widget1\",\"type\":\"input\",\"value\":\"申请打扫工位卫生\"}]","uuid":"7C468A54-8745-2245-9675-08B7C63E7A87"}'
```

```python
import json, uuid, requests

def create_instance(approval_code: str, open_id: str, widgets: list[dict], idem_key: str | None = None) -> str:
    body = {"approval_code": approval_code,
            "open_id": open_id,
            "form": json.dumps(widgets, ensure_ascii=False),        # 字符串，不是数组
            "uuid": idem_key or str(uuid.uuid4())}
    r = requests.post(f"{BASE}/open-apis/approval/v4/instances", json=body,
                      headers={"Authorization": f"Bearer {tenant_access_token()}"}, timeout=10)
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError(d)       # 1390001 多为控件值不对：拿 approval/get 的 form 对照控件 id、type
    return d["data"]["instance_code"]

create_instance(APPROVAL_CODE, "ou_xxx", [
    {"id": "reason", "type": "textarea", "value": "客户拜访"},
    {"id": "amount", "type": "amount", "value": 1280.5, "currency": "CNY"},
    {"id": "date", "type": "date", "value": "2026-09-11T09:00:00+08:00"},
])
```

**示例响应**：`{"code":0,"msg":"success","data":{"instance_code":"81D31358-93AF-92D6-7425-01A5D67C4E71"}}`

**注意事项**（含 FAQ 原文）

- **必填控件不传也不会报错**，实例照样创建成功；但一旦传了某控件的 JSON，就必须带 `value`，否则报错。所以业务必填项要自己校验。
- 相同请求 1 秒内调两次不会产生两个审批流（FAQ："只会更新"）；首次用某 uuid 成功后，再用相同 uuid 创建会报错。
- 无凭证探测（2026-09-11）：伪造 token → HTTP 400 `99991663`，路径存在。

---

## 5. 表单控件值

`form` 是数组，每个元素 `{"id": "<控件 id>", "type": "<控件类型>", "value": ...}`，**type 必须与定义里的控件类型一致**：

| 控件 | type | value 格式 |
|---|---|---|
| 单行 / 多行文本 | `input` / `textarea` | 字符串 |
| 数字 | `number` | float |
| 金额 | `amount` | float，另加 `"currency": "USD"`（取值范围看定义里该控件的 value） |
| 计算公式 | `formula` | float，须与定义里公式算出的值一致，否则报错 |
| 日期 | `date` | **RFC3339 字符串** `"2019-10-01T08:12:01+08:00"`（不是时间戳） |
| 日期区间 | `dateInterval` | `{"start": RFC3339, "end": RFC3339, "interval": 1.0}` |
| 单选 | `radio` / `radioV2` | 字符串：**选项的 value**（形如 `k2b8mkx0-h71x5gl1234-1`），不是显示文字 |
| 多选 | `checkbox` / `checkboxV2` | 字符串数组，同上 |
| 联系人 | `contact` | `"value": ["<user_id>"]`，`"open_ids": ["ou_..."]`——**value 装的是 user_id** |
| 关联审批 | `connect` | 被关联的 instance_code 数组 |
| 附件 | `attachmentV2` | 上传文件接口返回的 code 数组 |
| 图片 | `image` / `imageV2` | 同上 |
| 明细 / 表格、部门、电话、地址、请假 / 加班 / 换班 / 外出控件组 | 见文档「审批实例表单控件参数」 | ⚠ 结构较复杂，本 skill 未展开 |

部分控件审批实例 API 不支持（文档有专门列表 ⚠ 以原页为准）。单选 / 多选关联了外部选项时的传值方式见审批 FAQ。

---

## 6. 上传附件 / 图片

**Endpoint**: `POST https://www.feishu.cn/approval/openapi/v2/file/upload`——**注意域名是 `www.feishu.cn`，路径不在 `/open-apis` 下**
**用途**: 表单有图片或附件控件时，先上传拿 code，再填进 `form`。

| 字段（multipart/form-data） | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | 文件名，需含扩展名，如 `文件.doc` |
| `type` | string | 是 | `image` 或 `attachment`，与控件类型对应 |
| `content` | file | 是 | 文件本体 |

每次只能传一个文件；附件 ≤50 MB，图片 ≤10 MB。SDK 没有封装，要用"原生模式"调用。

```bash
curl -s -X POST 'https://www.feishu.cn/approval/openapi/v2/file/upload' \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN" \
  -F 'name=invoice.pdf' -F 'type=attachment' -F 'content=@./invoice.pdf'
```

响应字段 ⚠ 文档页被截断，本 skill 未确认（文档说"接口会返回文件的 code"）。
无凭证探测（2026-09-11）：不带 token POST 该地址 → HTTP 400 `{"code":99991661,"msg":"Missing access token..."}`，说明这个特殊域名路径存在且走同一网关鉴权。

---

## 7. 查实例

### 7.1 获取单个实例详情

**Endpoint**: `GET /open-apis/approval/v4/instances/:instance_id`（`instance_id` 就是 instance_code；创建时传过 uuid 的也可用 uuid 查）
query：`locale`、`user_id`、`user_id_type`（默认 `open_id`）。频控 1000 次/分钟、50 次/秒。

响应 `data` 关键字段：`approval_name`、`start_time` / `end_time`（**毫秒**时间戳字符串，未完成时 end_time 为 `0`）、`user_id`、`open_id`、
`serial_number`（审批单编号）、`department_id`、`status`、`uuid`、`form`（**JSON 字符串**）、
`task_list[]`（`id` 即 task_id、`user_id`、`open_id`、`status`、`node_id`、`node_name`、`custom_node_id`、`type`、`start_time`、`end_time`）、`comment_list[]`、`timeline[]`。
`task_list` 返回**全部**审批任务，不只是当前审批人的（FAQ）。

### 7.2 按定义批量取实例 ID

**Endpoint**: `GET /open-apis/approval/v4/instances`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `approval_code` | string | 是 | — | |
| `start_time` / `end_time` | string | 是 | — | **毫秒**时间戳；**单次时间范围不要超过 10 小时** |
| `page_size` | int | 否 | `100` | 1–100 |
| `page_token` | string | 否 | — | |

只返回 `instance_code_list`，详情要再逐个调 7.1。拉一整天的数据要切成 ≥3 个时间窗。频控 100 次/分钟。

```python
def instance_codes(approval_code, start_ms, end_ms, window_ms=10 * 3600 * 1000):
    t = start_ms
    while t < end_ms:
        t2 = min(t + window_ms, end_ms)
        token = None
        while True:
            params = {"approval_code": approval_code, "start_time": str(t), "end_time": str(t2), "page_size": 100}
            if token:
                params["page_token"] = token
            d = requests.get(f"{BASE}/open-apis/approval/v4/instances", params=params,
                             headers={"Authorization": f"Bearer {tenant_access_token()}"}, timeout=10).json()
            if d.get("code") != 0:
                raise RuntimeError(d)
            yield from d["data"].get("instance_code_list", [])
            if not d["data"].get("has_more"):
                break
            token = d["data"]["page_token"]
        t = t2
```

### 7.3 条件查询实例列表

**Endpoint**: `POST /open-apis/approval/v4/instances/query`（频控 1000 次/分钟、50 次/秒）
body 可按 `user_id`、`approval_code`、`instance_code`、`instance_external_id`、`group_external_id` 等过滤；这几个过滤条件的组合约束 ⚠ 文档页截断，以原页为准。

---

## 8. 处理任务与撤回

| 我想 | Endpoint | body |
|---|---|---|
| 同意 | `POST /open-apis/approval/v4/tasks/approve` | `approval_code`、`instance_code`、`user_id`（审批人）、`task_id`、`comment`（可选）、`form`（可选，**有条件分支时要传分支所需控件值**，JSON 字符串） |
| 拒绝 | `POST /open-apis/approval/v4/tasks/reject` | 同上 |
| 转交 | `POST /open-apis/approval/v4/tasks/transfer` | 同上 + 被转交人（字段名 ⚠ 本 skill 未抓取，以文档页为准） |
| 撤回实例 | `POST /open-apis/approval/v4/instances/cancel` | `approval_code`、`instance_code`、`user_id`（**提交人**） |

- query 参数 `user_id_type`（默认 `open_id`）决定 body 里 `user_id` 的类型——这里的字段名叫 `user_id`，但**装什么 ID 由 user_id_type 决定**。
- `task_id` 从实例详情 `task_list[].id` 取。频控均为 100 次/分钟。
- 其他任务操作（退回、加签、重新提交、抄送）见文档对应页。

```bash
curl -s -X POST 'https://open.feishu.cn/open-apis/approval/v4/tasks/approve?user_id_type=open_id' \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN" -H 'Content-Type: application/json; charset=utf-8' \
  -d '{"approval_code":"7C468A54-...","instance_code":"81D31358-...","user_id":"ou_xxx","task_id":"12345","comment":"OK"}'
```

---

## 9. 查任务列表

| 我想 | Endpoint | 说明 |
|---|---|---|
| 查某人的待办 / 已办 / 已发起 | `GET /open-apis/approval/v4/tasks/query` | query `user_id`（必填）、`topic`（必填：`1` 待办、`2` 已办、`3` 已发起、`17` 未读知会、`18` 已读知会）、`user_id_type`；支持 tenant 或 user token |
| 条件搜索任务 | `POST /open-apis/approval/v4/tasks/search` | 按 `user_id`、`approval_code`、`instance_code` 等过滤 |

---

## 10. 审批事件

**必须两步都做**，只做第一步收不到：

1. 开发者后台订阅审批事件（事件与回调 → 添加事件，如"审批实例状态变更"）并发布应用。
2. **对每个 approval_code 调一次订阅接口**：

**Endpoint**: `POST /open-apis/approval/v4/approvals/:approval_code/subscribe`
同一应用只需调用一次；取消用 `.../unsubscribe`。重复订阅报 `60007`，未订阅就取消报 `60008`（通用错误码表）。频控 100 次/分钟。

```bash
curl -s -X POST "https://open.feishu.cn/open-apis/approval/v4/approvals/$APPROVAL_CODE/subscribe" \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN"
```

**审批实例状态变更**（`type: approval_instance`）——**v1.0 事件结构**：

```json
{"ts": "1502199207.7171419", "uuid": "bc447199585340d1f3728d26b1c0297a",
 "token": "41a9425ea7df4536a7623e38fa321bae", "type": "event_callback",
 "event": {"app_id": "cli_xxx", "tenant_key": "xxx", "type": "approval_instance",
           "approval_code": "7C468A54-...", "instance_code": "81D31358-...", "status": "PENDING",
           "operate_time": "1666079207003", "instance_operate_time": "1666079207003", "uuid": "6525bffb"}}
```

- `status`：`PENDING`、`APPROVED`、`REJECTED`、`CANCELED`、`DELETED`、`REVERTED`、`OVERTIME_CLOSE`、`OVERTIME_RECOVER`。
- **`REVERTED` 时 `operate_time` 是 int64，其他状态是字符串**——解析时要兼容两种类型。
- **状态以事件为准做区分**：FAQ 说实例详情接口**不会返回 `REVERTED`**——审批未结束就取消是 `CANCELED`，审批结束后取消（撤销）事件里是 `REVERTED`。
- 事件 `uuid`（顶层）用于去重；`event.uuid` 是创建实例时你传的 uuid。

**审批任务状态变更**：`type: approval_task`，含 `approval_code`、`instance_code`、`user_id`（自动通过时为空）等。
其他：审批抄送状态变更、审批定义更新，以及请假 / 出差 / 加班 / 外出 / 补卡 / 换班等特殊审批事件。

**有序推送**：同一实例的审批事件按顺序推，**你没成功响应前一个，后续同类事件都不会推**（审批事件 FAQ）。接收端先回 200 再异步处理。
接收、验签、解密见 [events-callbacks.md](events-callbacks.md)。

---

## 11. 错误码与 FAQ 要点

创建实例专有（HTTP 400）：`1390001` 参数错误（报错信息里有控件 ID 时，拿 approval/get 或 instance/get 的 `form` 对照）、
`1390015` 审批定义已停用、`1390013` 不支持自定义审批流程、`1395001` 服务错误（先查参数再降频重试）。

通用：`60001` 参数错误、`60002` 定义不存在、`60003` 实例不存在、`60004` 用户不存在、`60005` 部门验证失败、`60006` 表单验证失败、
`60009` 权限不足、`60010` 任务不存在、`60011` 付费审批免费版不能发起、`60012` uuid 冲突、`4002`/`4003`/`4004` 旧版同类错误。

FAQ 要点：form 参数需要"压缩转义为字符串"；department_id 不能填根部门；只有发起人可以撤回（其他人撤回的方式 ⚠ 以 FAQ 原文为准）；
serial_number 的唯一性与能否据此查详情 ⚠ 以 FAQ 原文为准。

---

## 12. 容易写错的地方

1. **`form` 是字符串**（JSON 数组序列化后），不是数组；响应里的 `form` 也是字符串。
2. 日期控件是 **RFC3339 字符串**；实例 / 任务时间字段是**毫秒**时间戳字符串。
3. 单选 / 多选传**选项 value**（从审批定义里查），不是选项文字。
4. 联系人控件 `value` 是 user_id 数组，open_id 放 `open_ids`。
5. 必填控件漏传**不报错**，实例照样创建。
6. 批量取实例 ID 的时间窗 ≤10 小时。
7. 收事件除了后台订阅，还要**每个 approval_code 调一次 subscribe**；审批事件是 v1.0 结构、有序推送。
8. 上传附件在 `https://www.feishu.cn/approval/openapi/v2/file/upload`，不在 `open.feishu.cn/open-apis` 下。
9. 创建实例用 `user_id` 或 `open_id` 字段名区分类型；任务操作的 `user_id` 字段则跟随 query 的 `user_id_type`。
