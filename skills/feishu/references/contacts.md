# 通讯录：用户与部门

来源：`open.feishu.cn/document/server-docs/contact-v3/*`（抓取于 2026-09-11）。
Base URL `https://open.feishu.cn/open-apis`，鉴权 `Authorization: Bearer <tenant_access_token 或 user_access_token>`（见 [auth.md](auth.md)）。
**报错码与行为描述均为文档原文，未实测**；本域唯一的无凭证探测见第 9 节。

## 目录

1. [先懂三件事：ID 类型、权限范围、根部门](#1-先懂三件事)
2. [用手机号 / 邮箱换用户 ID（最常用的入口）](#2-用手机号--邮箱换用户-id)
3. [读用户：单个、批量、部门直属成员](#3-读用户)
4. [写用户：创建、修改、删除](#4-写用户)
5. [读部门：单个、批量、子部门、父部门、搜索](#5-读部门)
6. [写部门：创建、修改、删除](#6-写部门)
7. [查应用的通讯录授权范围](#7-查应用的通讯录授权范围)
8. [通讯录事件](#8-通讯录事件)
9. [容易写错的地方](#9-容易写错的地方)

---

## 1. 先懂三件事

### 1.1 用户 ID 有三种，靠 `user_id_type` 查询参数区分

| ID | 形态 | 作用域 | 什么时候用 |
|---|---|---|---|
| `open_id` | `ou_` 开头 | **某个应用内**的用户身份；同一用户在不同应用中不同 | 单应用内部；**不要跨应用传**（报 `99992361 open_id cross app`） |
| `union_id` | `on_` 开头 | 同一**应用开发商**的多个应用间一致 | 同一开发商的多个应用间关联用户；文档"推荐优先使用" |
| `user_id` | 租户自定义（常用工号 / 邮箱前缀），不填则随机生成 | 某个**租户内**一致，所有应用（含商店应用）相同 | 组织人员管理、和企业既有系统打通；**只有自建应用能申请**，且响应里要有字段权限 `contact:user.employee_id:readonly` 才返回 |

- 几乎所有接口都有 `user_id_type` 查询参数，**默认值 `open_id`**（本次抓取的 38 个页面里 37 个默认 `open_id`；唯一例外是
  飞书人事 `GET /corehr/v1/job_datas`，默认 `people_corehr_id`，见 [corehr.md](corehr.md)）。
- **路径参数、请求体里的用户 ID 和响应里的用户 ID，都按这个参数解释**。传了 user_id 却没设 `user_id_type=user_id`，
  服务端会把它当 open_id 查——结果是"用户不存在"类错误（`40007` / `99992351` / `99992360` 等），而不是"类型不对"。
- 用户 ID 也叫 employee_id（除招聘业务外两者等价）。另有 `lark_id`（全局物理身份），开发者不可见、无需关注。

### 1.2 部门 ID 有两种，靠 `department_id_type` 区分

| ID | 形态 | 说明 |
|---|---|---|
| `open_department_id` | `od-` 开头 | 系统生成，租户内全局唯一，各应用看到的值相同。**`department_id_type` 默认值** |
| `department_id` | 自定义 | 创建部门时可自定义（不能以 `od-` 开头、不能是 `0`/`1`），**删除后可被复用**，所以只在"未删除部门"范围内唯一；只能修改一次 |

**根部门 ID 固定是 `0`**（虚拟部门，不能查详情、不能改、不能删，报 `40157`/`40161`）。

### 1.3 数据范围：应用通讯录权限范围 vs 用户组织架构可见范围

- 用 **tenant_access_token**：只能访问开发者后台「开发配置 → 权限管理 → 数据权限 → 通讯录权限范围」里的部门 / 用户。
  范围外报 `40004 no dept authority error` 或 `41050 no user authority error`。有某个部门的范围 = 拥有其下所有用户和子部门。
- 用 **user_access_token**：不受上面这个范围影响，受该用户的**组织架构可见范围**（管理后台 → 安全 → 成员权限）影响。
- 以下操作要求通讯录权限范围是**全部成员**：在根部门下建部门 / 建用户、查根部门的子部门、查根部门直属用户、把父部门改成根部门、删根部门下的子部门或用户、创建用户组。
- 通讯录权限范围选"与应用的可用范围一致"时，要在**发布版本**时配置可用范围并发布才生效（`40004` 的排查说明）。
- 权限范围改完要**发布应用**才生效。
- 另外还有"API 权限"（scope，如 `contact:contact.base:readonly`）和"字段权限"（如 `contact:user.phone:readonly` 才返回手机号）。
  字段权限没开时，接口成功但**对应字段直接不返回**。

---

## 2. 用手机号 / 邮箱换用户 ID

**Endpoint**: `POST /open-apis/contact/v3/users/batch_get_id`
**用途**: 已知员工手机号或邮箱，拿到其 open_id / union_id / user_id 和状态。发消息、审批发起人、多维表格人员字段都常先走这一步。频控 1000 次/分钟、50 次/秒。

**关键参数**

| 参数 | 位置 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|---|
| `user_id_type` | query | string | 否 | `open_id` | 返回哪种 ID：`open_id` / `union_id` / `user_id` |
| `emails` | body | string[] | 否 | 空 | 最多 50 个；**不支持企业邮箱** |
| `mobiles` | body | string[] | 否 | 空 | 最多 50 个；非中国大陆号码要带 `+` 国家码 |
| `include_resigned` | body | boolean | 否 | `false` | 是否包含离职员工 |

`emails` 与 `mobiles` 相互独立，返回条数 = 两者之和。

**示例请求**

```bash
curl -s -X POST 'https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id' \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d '{"emails":["zhangsan@example.com"],"mobiles":["13011111111"],"include_resigned":false}'
```

```python
def ids_by_contact(emails=(), mobiles=(), id_type="open_id"):
    r = requests.post(f"{BASE}/open-apis/contact/v3/users/batch_get_id",
                      params={"user_id_type": id_type},
                      headers={"Authorization": f"Bearer {tenant_access_token()}"},
                      json={"emails": list(emails), "mobiles": list(mobiles)}, timeout=10)
    body = r.json()
    if body.get("code") != 0:
        raise RuntimeError(body)
    # 查不到的条目只有 email/mobile、没有 user_id
    return {(u.get("email") or u.get("mobile")): u.get("user_id") for u in body["data"]["user_list"]}
```

**示例响应**（文档原文，节选）

```json
{"code": 0, "msg": "success", "data": {"user_list": [
  {"user_id": "ou_979112345678741d29069abcdef01234", "email": "zhanxxxxx@a.com",
   "status": {"is_frozen": false, "is_resigned": false, "is_activated": true, "is_exited": false, "is_unjoin": false}}
]}}
```

**注意事项**

- 返回的 ID 字段**统一叫 `user_id`**，其值的类型由 `user_id_type` 决定（`open_id` 时 `user_id` 里装的是 `ou_...`）。
- 文档列出查不到 ID 的可能原因：token 对应的应用不对；手机号 / 邮箱不在企业内；用户不在应用的通讯录权限范围内。
- 要返回真正的 user_id，还要开通「获取用户 User ID」权限。

---

## 3. 读用户

### 3.1 获取单个用户

**Endpoint**: `GET /open-apis/contact/v3/users/:user_id`
**用途**: 按 ID 取一个用户的详情。频控 1000 次/分钟、50 次/秒。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|---|
| `user_id` | path | string | 是 | — | 类型与 `user_id_type` 一致 |
| `user_id_type` | query | string | 否 | `open_id` | |
| `department_id_type` | query | string | 否 | `open_department_id` | 响应里 `department_ids` 用哪种部门 ID |

```bash
curl -s "https://open.feishu.cn/open-apis/contact/v3/users/7be5fg9a?user_id_type=user_id" \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN"
```

注意：用 tenant_access_token 调用时**不返回 `department_path`**；要该字段需申请「获取成员所在部门路径」并用 user_access_token。
响应主体在 `data.user` 下。

### 3.2 批量获取用户

**Endpoint**: `GET /open-apis/contact/v3/users/batch`
**用途**: 一次按 ID 取最多 50 个用户。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `user_ids` | query | string[] | 是 | **同名参数重复传**：`?user_ids=a&user_ids=b`；单次最多 50 |
| `user_id_type` | query | string | 否 | 默认 `open_id` |
| `department_id_type` | query | string | 否 | 默认 `open_department_id` |

```python
r = requests.get(f"{BASE}/open-apis/contact/v3/users/batch",
                 params=[("user_ids", u) for u in ids] + [("user_id_type", "user_id")],   # 列表元组 → 重复参数
                 headers={"Authorization": f"Bearer {tenant_access_token()}"}, timeout=10)
```

注意：该接口不返回席位（`assign_info`）和部门路径（`department_path`）。

### 3.3 获取部门直属用户列表（遍历全员的正路）

**Endpoint**: `GET /open-apis/contact/v3/users/find_by_department`
**用途**: 列出某部门**直属**用户（不含子部门成员）。遍历全公司 = 递归子部门 + 每个部门调一次本接口。频控 1000 次/分钟、50 次/秒。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|---|
| `department_id` | query | string | 是 | — | 类型与 `department_id_type` 一致；根部门为 `0`（需全员范围） |
| `user_id_type` | query | string | 否 | `open_id` | |
| `department_id_type` | query | string | 否 | `open_department_id` | |
| `page_size` | query | int | 否 | `10` | **最大 50** |
| `page_token` | query | string | 否 | — | 首次不填；之后用上次响应的 `page_token` |

```python
def users_in_department(dept_id: str, id_type="open_id"):
    token = None
    while True:
        params = {"department_id": dept_id, "user_id_type": id_type,
                  "department_id_type": "open_department_id", "page_size": 50}
        if token:
            params["page_token"] = token
        body = requests.get(f"{BASE}/open-apis/contact/v3/users/find_by_department", params=params,
                            headers={"Authorization": f"Bearer {tenant_access_token()}"}, timeout=10).json()
        if body.get("code") != 0:
            raise RuntimeError(body)
        yield from body["data"].get("items", [])
        if not body["data"].get("has_more"):
            break
        token = body["data"]["page_token"]
```

响应 `data.items[]` 关键字段：`open_id`、`union_id`、`user_id`（需字段权限）、`name`、`en_name`、`email`（需 `contact:user.email:readonly`）、
`mobile`（需 `contact:user.phone:readonly`）、`department_ids`、`leader_user_id`、`employee_type`（1 正式 / 2 实习 / 3 外包 / 4 劳务 / 5 顾问，或自定义值）、
`job_title`、`status{is_frozen,is_resigned,is_activated,is_exited,is_unjoin}`；外加 `has_more`、`page_token`。

注意：用 user_access_token 调用时，结果按该用户的组织架构可见范围过滤。

### 3.4 搜索用户（只能用户身份）

**Endpoint**: `GET /open-apis/search/v1/user`
**用途**: 按名字关键词搜人。**仅支持 user_access_token**；搜不到外部企业和已离职用户。参数细节本 skill 未展开，⚠ 以文档页为准。

---

## 4. 写用户

### 4.1 创建用户（≈ 员工入职）

**Endpoint**: `POST /open-apis/contact/v3/users`
**用途**: 在通讯录建一个用户，系统会以短信或邮件邀请，用户同意后才能访问企业。**只支持自建应用**（商店应用改通讯录报 `40001`）。频控 1000 次/分钟、50 次/秒。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|---|
| `user_id_type` / `department_id_type` | query | string | 否 | `open_id` / `open_department_id` | 决定 body 里 `leader_user_id`、`department_ids` 的解释 |
| `client_token` | query | string | 否 | 空 | 幂等键，防重复创建 |
| `name` | body | string | 是 | — | ≤255 字符 |
| `mobile` | body | string | 是 | — | 租户内不可重复；**未认证企业只能加中国大陆手机号** |
| `department_ids` | body | string[] | 是 | — | 最多 50 个 |
| `employee_type` | body | int | 是 | — | 1 正式员工、2 实习生、3 外包、4 劳务、5 顾问（也支持自定义类型值） |
| `user_id` | body | string | 否 | 随机生成 | 自定义 user_id，≤64 字符，租户内唯一，建议用工号 / 邮箱前缀 |
| `email` | body | string | 否 | 空 | 设置非中国大陆手机号时**必须同时设置**邮箱；租户内不可重复 |
| `en_name` / `nickname` | body | string | 否 | 空 | |
| `gender` | body | int | 否 | `0` | 0 保密、1 男、2 女、3 其他 |
| `leader_user_id` | body | string | 否 | — | 直属主管 |
| `join_time` | body | int | 否 | 请求时刻 | **秒级**时间戳 |
| `employee_no` | body | string | 否 | 空 | 工号，租户内不可重复 |
| `mobile_visible` | body | boolean | 否 | — | 手机号是否对其他员工可见 |
| `city` / `country` / `work_station` | body | string | 否 | — | `country` 用国家/地区 Code 参照表 |
| `orders[]` | body | object[] | 否 | — | `department_id`、`user_order`、`department_order`、`is_primary_dept` |
| `custom_attrs[]` | body | object[] | 否 | — | 自定义字段，类型 TEXT / HREF / ENUMERATION / PICTURE_ENUM / GENERIC_USER |

```bash
curl -s -X POST 'https://open.feishu.cn/open-apis/contact/v3/users?user_id_type=user_id&department_id_type=open_department_id&client_token=7f0b2c8e-onboard-0001' \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN" -H 'Content-Type: application/json; charset=utf-8' \
  -d '{"user_id":"E1001","name":"张三","mobile":"13011111111","department_ids":["od-4e6ac4d14bcd5071a37a39de902c7141"],"employee_type":1}'
```

常见错误（文档原文）：`40101`/`41001` 手机号已存在；`40102`/`41002` 邮箱已存在；`40103` 手机与邮箱属于两个飞书账号；
`40107`/`40108` 超出未认证企业 / 套餐人数上限；`40111` user_id 已存在；`40113` 没指定部门；`40119` 自定义 user_id 只能设置或更新一次；
`41059` employee_type 不在 1–5。

### 4.2 修改用户部分信息

**Endpoint**: `PATCH /open-apis/contact/v3/users/:user_id`
**用途**: 部分更新，**未传的字段不更新**。改部门时涉及的所有部门都要在权限范围内。
文档提醒：并发冻结用户会因事务冲突概率性失败，要降速或串行。字段同创建接口。

### 4.3 删除用户（≈ 员工离职）

**Endpoint**: `DELETE /open-apis/contact/v3/users/:user_id`
**用途**: 删除用户，可通过参数把其群组、文档、日程、应用等数据转让给他人。通讯录权限范围必须包含该用户。
资源接收者必须是在职用户（`40138` / `41052`）。转让参数本 skill 未展开，⚠ 以文档页为准。

---

## 5. 读部门

### 5.1 获取子部门列表（组织架构遍历入口）

**Endpoint**: `GET /open-apis/contact/v3/departments/:department_id/children`
**用途**: 列出某部门下的子部门。频控 1000 次/分钟、50 次/秒。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|---|
| `department_id` | path | string | 是 | — | 根部门用 `0`（tenant token 需全员范围） |
| `department_id_type` | query | string | 否 | `open_department_id` | 路径参数和响应都按它解释 |
| `user_id_type` | query | string | 否 | `open_id` | 影响 `leader_user_id` |
| `fetch_child` | query | boolean | 否 | `false` | `true` 时递归返回所有层级子部门 |
| `page_size` | query | int | 否 | `10` | **最大 50** |
| `page_token` | query | string | 否 | — | |

```bash
curl -s "https://open.feishu.cn/open-apis/contact/v3/departments/0/children?department_id_type=open_department_id&fetch_child=true&page_size=50" \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN"
```

响应 `data.items[]`：`name`、`department_id`、`open_department_id`、`parent_department_id`（父为根部门时是 `"0"`）、`leader_user_id`、
`member_count`、`status.is_deleted`；外加 `has_more`、`page_token`。

注意：用 user_access_token 且 `fetch_child=true` 时最多查到 1000 个部门；子部门超过 500 个的部门不支持递归查询（`40162`/`43010`），要自己分层遍历。

### 5.2 其他部门读接口

| 我想 | Endpoint | 备注 |
|---|---|---|
| 取单个部门 | `GET /open-apis/contact/v3/departments/:department_id` | 频控为**特殊频控**；不能查根部门 `0` |
| 批量取部门 | `GET /open-apis/contact/v3/departments/batch` | 同名参数重复传 ID |
| 递归取父部门链 | `GET /open-apis/contact/v3/departments/parent` | tenant token 只返回权限范围内的父部门 |
| 按名称搜部门 | `POST /open-apis/contact/v3/departments/search` | **只能用 user_access_token** |

---

## 6. 写部门

### 6.1 创建部门

**Endpoint**: `POST /open-apis/contact/v3/departments`
**用途**: 在权限范围内的父部门下建部门；在根部门下建需全员范围。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `department_id_type` / `user_id_type` | query | string | 否 | 默认 `open_department_id` / `open_id` |
| `client_token` | query | string | 否 | 幂等键 |
| `name` | body | string | 是 | 不能含 `/`；同级不能重名（`40153`） |
| `parent_department_id` | body | string | 是 | 根部门下填 `0` |
| `department_id` | body | string | 否 | 自定义 ID，不能以 `od-` 开头、不能是 `0`/`1` |
| `leader_user_id` | body | string | 否 | 部门主管 |
| `order` | body | string | 否 | **字符串形式的非负整数**，越小越靠前，同级不可重复 |
| `create_group_chat` | body | boolean | 否 | 是否建部门群，默认 `false` |
| `leaders[]` / `department_hrbps[]` / `unit_ids[]` / `i18n_name{zh_cn,en_us,ja_jp}` | body | — | 否 | 负责人（须指定一名主负责人）/ HRBP / 绑定单位 / 多语言名 |

```bash
curl -s -X POST 'https://open.feishu.cn/open-apis/contact/v3/departments?department_id_type=department_id' \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN" -H 'Content-Type: application/json; charset=utf-8' \
  -d '{"name":"研发中心","parent_department_id":"0","department_id":"RD001","order":"10"}'
```

### 6.2 修改 / 删除部门

| 我想 | Endpoint | 备注 |
|---|---|---|
| 部分更新 | `PATCH /open-apis/contact/v3/departments/:department_id` | 涉及的所有部门都要在范围内；不能把子部门设为父部门 |
| 删除 | `DELETE /open-apis/contact/v3/departments/:department_id` | 需同时有该部门及其父部门的范围；**部门下有用户或子部门时不能删**（`40159`/`40160`） |

---

## 7. 查应用的通讯录授权范围

**Endpoint**: `GET /open-apis/contact/v3/scopes`
**用途**: 查当前应用被授权访问的部门、用户、用户组。排查 `40004`/`41050` 时先调它。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `user_id_type` / `department_id_type` | string | 否 | `open_id` / `open_department_id` | |
| `page_size` | int | 否 | `50` | 范围 1–100；**三类资源合计不超过 page_size**，顺序为先 user_ids、再 department_ids、最后 group_ids |
| `page_token` | string | 否 | — | |

范围是"全部成员"时返回根部门下的一级部门、直属用户和所有用户组。`user_ids` 需要「获取用户 User ID」权限才返回。

---

## 8. 通讯录事件

| 事件 | event_type | 触发 |
|---|---|---|
| 员工入职 | `contact.user.created_v3` | 管理后台加人、调用创建用户 API |
| 员工离职 | `contact.user.deleted_v3` | 管理后台离职、调用删除用户 API |
| 员工信息被修改 | `contact.user.updated_v3` | ID、姓名、邮箱、手机号、部门、主管、状态等变化；事件里有 `old_object` |
| 部门新建 | `contact.department.created_v3` | |

订阅方式、验签、去重见 [events-callbacks.md](events-callbacks.md)。文档提醒：若同时订阅 v1.0「通讯录变更」和 v2.0「员工离职」，同一次离职会收到两条。

---

## 9. 容易写错的地方

1. **所有 ID 都跟着 `user_id_type` / `department_id_type` 走，默认 `open_id` / `open_department_id`。** 手里拿的是工号式 user_id 就必须显式带 `user_id_type=user_id`，否则按 open_id 解释，报"用户不存在"。
2. **分页上限普遍是 50**（用户列表、子部门），不是 100；首次不带 `page_token`，`has_more=false` 时响应里没有 `page_token`。
3. **根部门 ID 是 `"0"`**，且根部门相关操作要全员通讯录范围。
4. **tenant token 的数据范围 ≠ API 权限。** API 权限开了、通讯录范围没配，照样 `40004`/`41050`；改完范围要发版。
5. **字段权限没开，字段直接缺失**（邮箱、手机号、user_id），不报错。
6. `GET /users/batch`、`/departments/batch` 的多个 ID 是**重复同名 query 参数**，不是逗号拼接。
7. 创建用户的 `join_time` 是**秒**，部门 `order` 是**字符串**。
8. 无凭证探测（2026-09-11）：`GET /open-apis/contact/v3/users/find_by_department?department_id=0` 不带 token → HTTP 400 `99991661`；
   `Bearer t-伪造` → HTTP 400 `99991663`；只写 token 不带 `Bearer ` → `99991661`。
