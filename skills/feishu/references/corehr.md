# 飞书人事（企业版 CoreHR）：员工与入职；附标准版花名册

来源：`open.feishu.cn/document/corehr-v1/*`、`server-docs/corehr-v1/*`、`server-docs/ehr-v1/*`（抓取于 2026-09-11）。
Base URL `https://open.feishu.cn/open-apis`；本域**绝大多数接口只接受 tenant_access_token**（文档原文："目前大多数接口仅支持 tenant_access_token"）。
**报错码与行为描述除标注「无凭证探测」外均为文档原文，未实测。**

## 目录

1. [先分清：企业版（corehr）vs 标准版（ehr）](#1-企业版-vs-标准版)
2. [接入前提：API 权限 + 数据权限两道闸](#2-接入前提)
3. [ID 体系](#3-id-体系)
4. [查员工：按 ID 批量查、条件搜索](#4-查员工)
5. [添加人员（直接建档）](#5-添加人员)
6. [入职：创建待入职 → 查询 → 完成入职](#6-入职流程)
7. [任职信息（v1，默认 ID 类型不同！）](#7-任职信息-v1)
8. [事件](#8-事件)
9. [错误码](#9-错误码)
10. [标准版：批量获取员工花名册](#10-标准版花名册)
11. [容易写错的地方](#11-容易写错的地方)

---

## 1. 企业版 vs 标准版

| | 飞书人事（企业版） | 飞书人事（标准版） |
|---|---|---|
| API 前缀 | `/open-apis/corehr/v2/...`（少量 `/corehr/v1/`） | `/open-apis/ehr/v1/...` |
| 能力 | 员工、组织、入转调离、合同、假勤、薪酬……读写都有 | 只读：花名册 + 附件下载 |
| 典型报错 | 租户没开通企业版时报 `TenantID xxx not found. Please cheeck if the tenant has activated this app` | |

先问清楚客户用的是哪一版——两套接口和数据模型完全不同。
文档站的目录名是 `corehr-v1`，但本文列出的员工 / 待入职接口实际路径都是 **`/corehr/v2/`**
（无凭证探测（2026-09-11）：`POST /open-apis/corehr/v2/employees/batch_get` + 伪造 token → HTTP 400 `99991663`，路径存在）。

---

## 2. 接入前提

1. **API 权限**：按每个接口文档的「权限要求」在开发者后台申请（如员工查询、待入职读写）。
2. **数据权限**（容易漏）：开发者后台「权限管理 → 数据权限 → 飞书人事（企业版）数据权限范围」里申请：
   - 查员工要「员工资源」范围——接口"按应用拥有的员工数据权限范围返回数据"；
   - 查待入职要「待入职人员」范围。
   只有 API 权限没有数据权限时，接口可能成功但返回空（文档措辞是"按范围返回"，具体表现 ⚠ 文档未说明）。
   配置数据权限需要审核通过才生效；只有**自建应用**能配飞书人事（企业版）数据权限。
3. **字段权限**：很多字段（手机号、证件号、职级……）要单独的字段权限；未开时字段不返回。
   文档："字段未返回请检查：字段权限、用户该字段有值，以及飞书人事档案配置中字段是否启用"。
4. 大部分查询接口 `支持的应用类型` 只有 Custom App（批量查询员工、搜索员工、创建待入职）。

---

## 3. ID 体系

| ID | 含义 |
|---|---|
| `employment_id` | 雇佣 ID（一个人在公司的一段雇佣关系），**类型跟随 `user_id_type`** |
| `person_id` | 个人信息 ID |
| `pre_hire_id` | 待入职 ID |
| `people_corehr_id` | 飞书人事自有的用户 ID（`user_id_type` 的可选值之一） |
| 部门 ID | `department_id_type`：`open_department_id`（默认）/ `department_id` / `people_corehr_department_id` |

- 转换失败时 `employment_id` 会**返回 lark_id**，无法区分值的类型；文档新增 `employment_id_v2`，转换失败时返回空，**建议用 `_v2` 字段**。
- 开启"复用工号"后一个工号可对应多个员工，**不要用工号做唯一键**。

---

## 4. 查员工

### 4.1 批量查询员工信息

**Endpoint**: `POST /open-apis/corehr/v2/employees/batch_get`
**用途**: 已知雇佣 ID / 个人信息 ID / 工作邮箱，查工作信息和个人信息。频控 **100 次/分钟**。仅自建应用。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|---|
| `user_id_type` | query | string | 否 | `open_id` | 也可 `people_corehr_id` 等 |
| `department_id_type` | query | string | 否 | `open_department_id` | |
| `fields` | body | string[] | 否 | — | 要返回的字段（见文档"字段下钻"）；**为空时只返回 `employment_id`**，≤100 |
| `employment_ids` | body | string[] | 三选一 | — | **每次最多 100 个** |
| `person_ids` / `work_emails` | body | string[] | 三选一 | — | 三个都有值时只认第一个有值的：`employment_ids > person_ids > work_emails` |

```bash
curl -s -X POST 'https://open.feishu.cn/open-apis/corehr/v2/employees/batch_get?user_id_type=people_corehr_id' \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN" -H 'Content-Type: application/json; charset=utf-8' \
  -d '{"employment_ids":["7140964208476371111"],"fields":["person_info.phone_number","employee_number","department_id"]}'
```

响应 `data.items[]`：`employment_id`、`employment_id_v2`、`employee_number`、`department_id`、`job_level`、`employment_status`、`person_id`、以及 `fields` 里请求的字段。

注意：更新后有 **2–5 秒**延迟；**未完成入职的员工查不到**（待入职、撤销入职、删除雇佣）；部分计算字段在凌晨零点计算，别在零点查。

### 4.2 搜索员工信息（全量同步用这个）

**Endpoint**: `POST /open-apis/corehr/v2/employees/search`
**用途**: 按条件分页查员工，全量拉取的正路。频控 100 次/分钟。仅自建应用。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `page_size` | query | int | **是** | 1–100 |
| `page_token` | query | string | 否 | |
| `user_id_type` / `department_id_type` | query | string | 否 | 同上 |
| `fields` | body | string[] | 否 | 为空时只返回 `employment_id` |
| `employment_id_list` / `employee_number_list` | body | string[] | 否 | |
| `work_email` / `phone_number` | body | string | 否 | 精确匹配；按手机号搜要权限 `corehr:person.phone.search:read` |
| `key_word` | body | string | 否 | 邮箱 / 工号 / 姓名模糊匹配 |
| `employment_status` | body | string | 否 | `hired` 在职 / `terminated` 离职 |
| `department_id_list` / `department_id_list_include_sub` | body | string[] | 否 | 直属部门 / 含下级 |
| `effective_time_start` / `effective_time_end` | body | string | 否 | 入职日期范围 `YYYY-MM-DD`，要成对用 |
| `direct_manager_id_list`、`work_location_id_list_include_sub`、`cost_center_id_list`、`service_company_list` 等 | body | string[] | 否 | |

所有筛选条件之间是 **AND**；请求体不填默认为空。**本接口数据有 5 分钟延迟**；同样查不到未完成入职的员工。

```python
def all_hired(fields):
    token = None
    while True:
        params = {"page_size": 100, "user_id_type": "people_corehr_id"}
        if token:
            params["page_token"] = token
        d = requests.post(f"{BASE}/open-apis/corehr/v2/employees/search", params=params,
                          json={"fields": fields, "employment_status": "hired"},
                          headers={"Authorization": f"Bearer {tenant_access_token()}"}, timeout=30).json()
        if d.get("code") != 0:
            raise RuntimeError(d)
        yield from d["data"].get("items", [])
        if not d["data"].get("has_more"):
            break
        token = d["data"]["page_token"]
```

---

## 5. 添加人员

**Endpoint**: `POST /open-apis/corehr/v2/employees`
**用途**: 一次性建完整员工档案（基本信息、雇佣信息、入职任职记录等），跳过待入职流程。频控 **20 次/分钟**。支持自建和商店应用。

- **字段是否必填以租户「人事系统 → 人员档案配置」为准**，接口文档里的"是/否"不代表实际校验；文档建议对照飞书人事「我的团队 → 添加人员」页面传参。
- 开启工号自动编码时不用传工号。
- 顶层参数：`client_token`（UUIDv4 幂等键）、`rehire` / `rehire_employment_id`（离职重聘）、`force_submit`（跳过超编校验）、
  `ignore_working_hours_type_rule`、`personal_info.personal_basic_info.legal_name{...}` / `preferred_name{...}`（姓名结构按国家 / 地区规则，`country_region` 必填）……
  完整结构非常深，⚠ 以文档页为准。
- 校验失败统一返回 `1160002`，具体原因在错误信息里（见第 9 节）。

---

## 6. 入职流程

飞书人事的入职是"待入职人员（pre_hire）"在后台配置的入职流程里走任务节点，最后"完成入职"变成正式员工。

| 我想 | Endpoint | 频控 | 说明 |
|---|---|---|---|
| 直接创建待入职 | `POST /open-apis/corehr/v2/pre_hires` | 1000/分、50/秒 | 仅自建应用 |
| 更新待入职 | `PATCH /open-apis/corehr/v2/pre_hires/:pre_hire_id` | 1000/分、50/秒 | |
| 按 ID 查询待入职 | `POST /open-apis/corehr/v2/pre_hires/query` | 100/分 | `pre_hire_ids` ≤10；`page_size` 必填且 **1–10** |
| 搜索待入职 | `POST /open-apis/corehr/v2/pre_hires/search` | 100/分 | |
| 操作完成入职 | `POST /open-apis/corehr/v2/pre_hires/:pre_hire_id/complete` | 1000/分、50/秒 | 响应 `data.success` |
| 撤销入职 | `POST /open-apis/corehr/v2/pre_hires/withdraw_onboarding` | 100/分 | |

### 6.1 直接创建待入职

请求体两大块（文档示例节选）：

```json
{
  "basic_info": {
    "name": {"full_name": "李一一", "first_name": "一", "name_primary": "李", "local_first_name": "一", "local_primary": "李"},
    "phone_number": "138xxxx1234", "international_area_code": "86_china",
    "email": "xxxx@example.com", "date_of_birth": "2011-09-09", "gender_id": "male"
  },
  "offer_info": {
    "department_id": "7147562782945478177", "job_id": "6977976735715378724",
    "job_level_id": "6977971894960145950", "direct_leader_id": "7032210902531327521",
    "onboarding_date": "2022-10-08", "onboarding_location_id": "6977976687350924832",
    "employee_type_id": "6977973225846343171", "recruitment_type_id": "experienced_professionals",
    "probation_period": "6", "work_email": "xxxx@example.com"
  }
}
```

- `basic_info` 必填；日期都是 **`YYYY-MM-DD` 字符串**；`probation_period` 等数值也按示例是**字符串**。
- `gender_id`、`international_area_code` 等是枚举 ID，要先调「获取字段详情」接口查；国家 / 地区、国籍用对应 search 接口。
- `personal_id_number` / `personal_id_type` 标记"待废弃"，文档建议改用 `national_id_list`；两者同时传时 **`national_id_list` 被忽略**（文档原文如此）。
- `offer_info` 各字段必填性、完整字段列表 ⚠ 以文档页为准（租户档案配置会影响校验）。

### 6.2 查询待入职

`POST /open-apis/corehr/v2/pre_hires/query`：body `pre_hire_ids`（≤10）、`fields`（为空只返回 `pre_hire_id`；
格式如 `person_info.gender`、`employment_info.department`、`onboarding_info.onboarding_date`、`probation_info...`）。
主从延迟 2 秒内：**刚创建完 2 秒内可能查不到**。文档建议每批 <10 个、字段 <50 个。要「待入职人员」数据权限。

### 6.3 完成入职

`POST /open-apis/corehr/v2/pre_hires/:pre_hire_id/complete`，响应 `{"code":0,"data":{"success":true}}`。
成功后触发 `corehr.job_data.employed_v1` 事件，员工才能在 4.1 / 4.2 查到。
常见错误：`1161001`–`1161009`（job_level_id、job_family_id、job_id、offer_hr_id、direct_leader_id、onboarding_location_id、office_location_id、recruitment_type_id、employee_type_id 无效），`1161000` 系统错误。

```bash
curl -s -X POST "https://open.feishu.cn/open-apis/corehr/v2/pre_hires/$PRE_HIRE_ID/complete" \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN" -H 'Content-Type: application/json; charset=utf-8' -d '{}'
```

---

## 7. 任职信息 v1

**Endpoint**: `GET /open-apis/corehr/v1/job_datas`
**用途**: 批量查询任职记录（可取历史版本）。频控 1000 次/分钟、50 次/秒。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `page_size` | **string** | **是** | — | 注意类型是字符串（示例 `100`）；上限 ⚠ 文档未说明 |
| `page_token` | string | 否 | — | |
| `employment_id` | string | 否 | — | 与 `user_id_type` 一致 |
| `get_all_version` | boolean | 否 | `false` | `true` 返回所有版本的任职记录 |
| `user_id_type` | string | 否 | **`people_corehr_id`** | ⚠ 与平台其他接口默认 `open_id` 不同 |
| `department_id_type` | string | 否 | **`people_corehr_department_id`** | ⚠ 与其他接口默认 `open_department_id` 不同 |

从 v2 接口拿到的 open_id 形式的 employment_id 直接传进来会被当成 people_corehr_id——**调 v1 接口时显式传 `user_id_type`**。

---

## 8. 事件

| 事件 | event_type | 触发 |
|---|---|---|
| 员工完成入职 | `corehr.job_data.employed_v1` | 完成入职接口、添加人员接口、后台操作"完成入职"、花名册"添加 / 导入人员" |
| 人员信息变更 | `corehr.employee.domain_event_v2` | 员工信息变化，适合同步下游系统 |
| 待入职相关 | 入职流程状态变更、入职信息变更（event_type ⚠ 本 skill 未抓取） | |

配置事件订阅需公网可访问的回调地址（或长连接），做法见 [events-callbacks.md](events-callbacks.md)。

---

## 9. 错误码

添加 / 更新人员校验统一 `1160002`，看 msg 区分（文档原文节选）：

| 校验项 | 错误信息 |
|---|---|
| 工号 | 「工号」为必填；工号重复（检查待入职 / 在职 / 已离职 / 异动流程）；格式不合法 |
| 工作邮箱 | 与在职 / 待入职 / 离职人员重复；格式不正确；域名错误；与飞书企业邮箱已有邮箱重复 |
| 离职重聘 | 是否离职重聘为"否"时历史雇佣信息不为空；为"是"时历史雇佣信息必填；有疑似待入职记录 (pre_hire_id) |
| 通知期 / 司龄调整 | 未匹配到规则；超出可编辑范围；日期成对填写、不能倒置 |

`1160001` 系统错误。入职 `1161000`–`1161009` 见 6.3。其余通用错误码见 [errors-and-limits.md](errors-and-limits.md)。

---

## 10. 标准版花名册

**Endpoint**: `GET /open-apis/ehr/v1/employees`
**用途**: 飞书人事（标准版）批量获取员工花名册。仅自建应用、tenant_access_token；需开通标准版并申请其 OpenAPI 权限。频控 100 次/分钟。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `view` | string | 否 | `basic` | `basic` 只返回 id、name 等；`full` 返回系统标准字段 + 自定义字段 |
| `status` | int[] | 否 | 全部 | 1 待入职、2 在职、3 已取消入职、4 待离职、5 已离职；多值**重复传参** `status=2&status=4`（"实际在职 = 2 & 4"） |
| `type` | int[] | 否 | 全部 | 雇员类型（如 2 实习） |
| `user_id_type` | string | 否 | `open_id` | |
| `page_size` | int | 否 | `10` | 1–100 |
| `page_token` | string | 否 | — | |

```bash
curl -s 'https://open.feishu.cn/open-apis/ehr/v1/employees?view=full&status=2&status=4&page_size=100' \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN"
```

响应 `data.items[]`：`user_id`（类型随 `user_id_type`）、`system_fields{name, employee_no, status, ...}`、`custom_fields`。
附件（如身份证照片 token 在 `system_fields.id_photo.id`）：`GET /open-apis/ehr/v1/attachments/:token` 下载。

---

## 11. 容易写错的地方

1. 先确认企业版还是标准版；`TenantID xxx not found` = 没开通企业版。
2. **API 权限 + 数据权限（员工资源 / 待入职人员）两道闸**，缺数据权限查到的是空。
3. `fields` 不传只返回 ID——这是设计，不是 bug。
4. 批量查询员工 ≤100 个 ID；查询待入职 ≤10 个、page_size ≤10。
5. 未完成入职的人在员工接口里查不到；刚写入有 2–5 秒（batch_get）/ 5 分钟（search）/ 2 秒（pre_hire query）延迟。
6. **`/corehr/v1/job_datas` 默认 `user_id_type=people_corehr_id`、`department_id_type=people_corehr_department_id`，且 `page_size` 是必填字符串**。
7. 用 `employment_id_v2`，别用工号做唯一键。
8. 添加人员频控只有 20 次/分钟，批量导入要排队。
