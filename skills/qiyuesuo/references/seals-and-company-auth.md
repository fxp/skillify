# 印章、企业认证与个人认证

> 来源：open.qiyuesuo.com「API文档 / 印章管理」「企业认证」「个人认证」「组织架构 / 公司信息、对接方信息」「新手指南 / 接入流程、名词解释」「常见问题」（抓取于 2026-09-11）。
> **未用真实凭证验证。** 报错 / 行为描述除特别标注外均为文档原文，未实测。示例复用 [auth-and-signing.md](auth-and-signing.md) §4 的 `qys_call`。

## 目录

1. [印章从哪来、谁能用](#1-印章从哪来谁能用)
2. [查印章：列表、详情、图片](#2-查印章列表详情图片)
3. [自动生成印章（免审核）](#3-自动生成印章免审核)
4. [上传图片创建印章（需审核）](#4-上传图片创建印章需审核)
5. [编辑、停用 / 启用、删除印章](#5-编辑停用--启用删除印章)
6. [企业认证](#6-企业认证)
7. [个人认证](#7-个人认证)
8. [公司信息](#8-公司信息)
9. [注意事项与 ⚠](#9-注意事项与-)

---

## 1. 印章从哪来、谁能用

- 印章在**契约锁云平台**维护（企业 → 印章管理），也可以用本页接口创建。开放平台**控制台**里的旧印章只给老接口用，新接口不认（FAQ 原文）。
- 两种来源：**自动生成**（免审核，立即可用）；**拍照 / 扫描件上传**（外观与实体章一致，需契约锁客服审核）。
- 真正有法律效力的是印章背后的数字证书（公有云为上海 CA 颁发的事件型证书），证书颁发给对接方公司，**只能维护和使用自己公司（及已加入下级法人单位的子公司）的印章**（FAQ 原文）。
- 权限：印章管理员（在"角色与权限"里设置）拥有所有印章的使用权；印章使用者由管理员在印章详情里添加，**必须是本公司员工**（未注册 / 已离职 / 不在公司都会报错）。
- 签署时印章的选择：创建合同时 Action 指定了 `corpSealIds` 就只能用这些章；没指定就可用操作人有权限的任一公章；法人章每家公司最多一个，不能在创建合同时指定（名词解释原文）。
- 印章 ID 在云平台印章详情里显示为"印章编号"，或用 §2 的列表接口查。

## 2. 查印章：列表、详情、图片

### 印章列表
**Endpoint**: `GET /v2/seal/list`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `selectOffset` | Integer | 否 | 起始位置，默认 0 |
| `selectLimit` | Integer | 否 | 数量，默认 1000 |
| `tenantName` | String | 否 | 子公司名；默认平台方主公司 |
| `status` | String | 否 | `NORMAL`（默认）/ `FREEZE`（停用）/ `ALL` |
| `modifyTimeStart` / `modifyTimeEnd` | String | 否 | `yyyy-MM-dd HH:mm:ss` |

**返回**：`result.totalCount`、`result.list[].{id, name, sealType, spec, status, createTime}`；`sealType` 取 `ENTERPRISE`（单位电子章）/ `LP`（法人章）/ `PRACTICING_SEAL`（个人执业章）。

```python
seals = qys_call("GET", "/v2/seal/list", params={"status": "NORMAL", "selectLimit": 100})
company_seal_ids = [s["id"] for s in seals["list"] if s["sealType"] == "ENTERPRISE"]
```

报错（文档原文）：`11041801` 公司不存在、`11041802` 公司权限不足（子公司没挂到下级法人单位时常见）。

### 印章详情 / 图片 / 员工默认签名图片

| Endpoint | 参数 | 返回 |
| --- | --- | --- |
| `GET /v2/seal/sealdetail` | `sealId`（必填） | `id, name, sealType, spec, users[], createTime`；印章不存在 `11011201` |
| `GET /v2/seal/image` | `sealId`（必填） | **图片流**（不是 JSON，用 `qys_call(..., raw=True)`） |
| `GET /v2/seal/employeesealimage` | 见文档页 | 员工默认签名图片（未展开） |

## 3. 自动生成印章（免审核）

**Endpoint**: `POST /v2/seal/autocreate`
**用途**: 直接为公司（或子公司）生成电子印章并指定使用者，不经契约锁审核。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `name` | String(100) | 是 | 印章名称 |
| `sealImageInfo.style` | String | 是 | `UNIVERSAL_SEAL`（单位电子章）/ `SPECIAL_SEAL`（专用章）/ `SPECIAL_SEAL_WITHSTAR` / `YOUTH_LEAGUE_SEAL` / `FOREIGN_SEAL` / `FOREIGN_MIX_SEAL` |
| `sealImageInfo.spec` | String | 否 | `CIRCULAR_42`（默认）/ `CIRCULAR_40` / `CIRCULAR_44` / `CIRCULAR_45` / `OVAL_45_30` |
| `sealImageInfo.foot` | String | 条件 | 下方横排文字；`SPECIAL_SEAL` 必传 |
| `sealImageInfo.enContent` | String | 条件 | `FOREIGN_MIX_SEAL` 必传 |
| `sealImageInfo.enterpriseCode`、`branchName`、`edgeWidth`、`starSize` | | 否 | 企业编码、分公司名、圆边宽、五角星直径 |
| `tenantName` | String | 否 | 为子公司生成时传 |
| `users` | List<User> | 否 | 印章使用者（必须是员工）；为空时取印章管理员 |

```python
seal = qys_call("POST", "/v2/seal/autocreate", json_body={
    "name": "合同专用章",
    "sealImageInfo": {"style": "SPECIAL_SEAL", "foot": "合同专用章", "spec": "CIRCULAR_42"},
    "users": [{"contact": "13800000000", "contactType": "MOBILE"}],
})
seal_id = seal["id"]
```

报错：`12072210` 印章自动生成失败、`11990005` 参数错误（文档原文）。
⚠ 文档自相矛盾：`starSize` 说明里提到 `spec` 为 `CIRCULAR_38` 的情况，但 `spec` 枚举里没有 `CIRCULAR_38`；Http 示例 JSON 末尾多一个逗号。

## 4. 上传图片创建印章（需审核）

**Endpoint**: `POST /v2/seal/createbyimage`（JSON，图片用 base64）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sealName` | String(100) | 是 | |
| `sealImage` | String | 是 | 章面图片 base64，**不带** `data:image/...;base64,` 前缀 |
| `sealType` | String | 否 | `ENTERPRISE`（默认）/ `LP` |
| `lpLetter` | String | 条件 | 法人授权书图片 base64（不带前缀）；`sealType=LP` 时必传 |
| `sealSpec` | String | 否 | 单位章默认圆形 42mm、法人章默认正方形 20mm；可选 `CIRCULAR_60/58/50/46/45/44/42/40/38`、`OVAL_45_30`、`OVAL_40_30`、`SQUARE_25_25/22_22/20_20/18_18`、`RECTANGLE_50_30`、`RECTANGLE_40_16`、`DIY_SPEC` |
| `width` / `height` | Integer | 否 | 毫米，仅 `DIY_SPEC` |
| `sealUsers` | List<User> | 否 | 默认印章管理员 |
| `tenantName` | String | 否 | 子公司 |
| `callbackUrl` | String | 否 | 审核结果回调地址 |

**返回**：`result.applyId`（印章申请 ID，不是印章 ID）。审核通过后印章 ID 在回调的 `detail.sealId` 里，见 [callbacks.md](callbacks.md) §5。
报错（文档原文）：`11990010` 文件超限、`11011204` 已存在法人章、`11011205` 已存在待审批的法人章、`11041701/1702/1705` 使用者不是员工 / 已离职 / 未注册。
⚠ 注意 base64 前缀规则与模板图片参数相反：模板参数的图片**要**带 `data:image/png;base64,` 前缀（[contracts.md](contracts.md) §4），这里**不要**带。

## 5. 编辑、停用 / 启用、删除印章

| Endpoint | 参数 | 说明 |
| --- | --- | --- |
| `POST /v2/seal/edit` | `sealId`（必填）、`sealName`、`operate`（`ADD` 默认 / `REMOVE`）、`sealUsers` | 改名、增删使用者。**频次限制：同一请求 1 小时内连续 5 次后锁定 18 小时，时间叠加**（文档原文） |
| `POST /v2/seal/status` | `sealId`、`operate`（`ENABLE` / `DISABLE`），都必填 | 停用业务分类里指定的印章后，签章人可以任选有权限的章签，谨慎操作 |
| `GET /v2/seal/remove` | `sealId` | **只能删除已停用的印章**，删除不可恢复；未停用 / 已删除报 `11011203` |

注意删除印章是 **GET** 请求（文档原文）。

## 6. 企业认证

对接方自己的企业认证在开放平台 / 云平台页面上完成（接入流程原文）。下面这组接口用于**帮你的客户企业**做认证：拿一个认证页面链接给对方填写。

### 获取企业认证链接

| Endpoint | 端 | 请求格式 |
| --- | --- | --- |
| `POST /companyauth/pcpage` | PC | JSON |
| `POST /companyauth/h5page` | H5 | JSON |
| `POST /companyauth/pcpagewithlicense` | PC，附营业执照 | **multipart**：`applicantInfo`、`pageStyleInfo` 是 JSON **字符串**，`license` 是文件 |
| `POST /companyauth/h5pagewithlicense` | H5，附营业执照 | multipart（同上） |

注意路径**没有** `/v2` 前缀。

| 参数（pcpage / h5page） | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `companyName` | String | 是 | 待认证公司名称 |
| `applicant` | `{name, contact, contactType}` | 是 | 认证提交人；认证通过后**自动成为该企业系统管理员**；`contactType` 只能 `MOBILE` / `EMAIL` |
| `registerNo`、`legalPerson`、`legalContact` | String | 否 | 预填信息 |
| `callbackUrl` | String | 否 | 认证结果回调地址（[callbacks.md](callbacks.md) §4） |
| `modifyFields` | String | 否 | 允许用户修改的预填项，逗号分隔：`corpName,registerNo,legalPerson,legalContact`；不传则都不能改 |
| `closeButton` | Boolean | 否 | 默认 true |
| `lang`、`pageStyle.themeColor` | | 否 | |

**返回**：`result.authUrl`（认证链接）、`result.requestId`（查结果用）。公司已认证 → `1605 COMPANY ALREADY AUTHED`。

```python
r = qys_call("POST", "/companyauth/h5page", json_body={
    "companyName": "示例客户有限公司",
    "applicant": {"name": "李四", "contact": "13900000000", "contactType": "MOBILE"},
    "registerNo": "91310000XXXXXXXXXX",
    "callbackUrl": "https://your.app/qys/companyauth",
})
auth_url, request_id = r["authUrl"], r["requestId"]
```

认证材料与方式（接入流程原文）：单位名称、统一社会信用代码、法定代表人姓名、营业执照；授权方式二选一——法定代表人在线签署认证授权书，或线下盖章授权书 + 对公打款。

### 查询认证结果
**Endpoint**: `GET /companyauth/result`，参数 `companyName` 或 `requestId`。
返回 `status`：`-1` 无认证记录、`1` 未提交、`2` 认证通过、`3` 认证不通过、`4` 认证中、`6` 已过期；另有 `basicStatus`（1 审核中 / 2 失败 / 3 成功）、`basicReason`、`operAuthorizationReason`、`authEndTime`（授权有效期）。
⚠ 文档自相矛盾：独立的「查询认证结果」页有 `6 已过期` 和 `applicantName`，「企业认证」汇总页没有 `6`、字段叫 `applicant`；企业认证**回调**的 `status` 又是另一套（0 认证中 / 1 成功 / 2 失败），不要把回调的 1 当成查询接口的 1。

## 7. 个人认证

### 获取个人认证链接
**Endpoint**: `POST /v2/personalauth`
**用途**: 拿个人实名认证页面链接。**链接只能打开一次，未打开 5 分钟失效，打开后页面会话 15 分钟**（文档原文）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `user` | `{contact, contactType}` | 是 | `MOBILE` / `EMAIL` |
| `mode` | String | 否 | `IVS`（手机三要素）/ `FACE` / `BANK`；默认 `DEFAULT`（可用的都行） |
| `otherModes` | List | 否 | 降级方式：`IVS` `FACE` `BANK` `MANUAL` |
| `paperType` | String | 否 | `IDCARD`（默认）/ `PASSPORT` / `HKMP` / `MTPS` |
| `username`、`idCardNo`、`bankNo`、`bankMobile` | String | 否 | 预填 |
| `modifyFields` | List | 否 | 允许修改：`USERNAME` `IDCARDNO` `BANKNO` `BANKMOBILE` |
| `callbackUrl` / `callbackPage` | String | 否 | 结果回调 / 完成后跳转 |

**返回**：`result.authUrl`、`result.authId`。

- 默认流程：手机三要素 → 人脸，任一步通过即结束（FAQ 原文）。
- 不能通过接口直接替用户完成认证，只能预填信息后让用户在页面提交（FAQ 原文）。

### 查询个人认证状态
**Endpoint**: `GET /v2/personalauth/result`，参数 `authId`，或 `contact` + `contactType`（二者不能同时为空）。
返回 `realName`（Boolean）、`mode`（仅按 authId 查时返回：`IVS` / `FACEID` / `BANK` / `MANUAL`）。未匹配 → `1604 INVALID_AUTHID`。
⚠ 文档自相矛盾：请求里人脸模式叫 `FACE`，查询返回里叫 `FACEID`。

签署合同时的个人认证方式也可以在业务分类里配（默认 / 人脸 / 银行卡），或者设为"无需认证"（需签风险须知）（FAQ 原文）。

## 8. 公司信息

| Endpoint | 参数 | 返回 |
| --- | --- | --- |
| `GET /v2/company/detail` | `companyName` 或 `registerNo` | `status`（`UNREGISTERED` / `AUTH_SUCCESS`）、`id`、`name`、`registerNo`、`legalPerson`、`authEndTime` |
| `GET /company/platforminfo` | 无 | 对接方自己的公司信息 |
| `GET /v2/company/list` | 见文档 | 子公司列表（未展开） |

发合同给外部公司前，可以先用 `/v2/company/detail` 看对方是否已在契约锁认证。

## 9. 注意事项与 ⚠

- 员工、角色、子公司邀请等组织架构接口（`/v2/employee/*`、`/v2/role/manage`、`/v2/subcompany/*`）本 skill 未展开；印章使用者、合同 `creator`、签章操作人都必须是已加入公司的员工，员工接口文档在接口列表「组织架构」一节。
- ⚠ 文档自相矛盾：自动生成印章的 `CIRCULAR_38`（§3）；企业认证状态码三套（§6）；`FACE` vs `FACEID`（§7）；印章接口的 `responseCode` 在参数表里写成 `Integer`，其他页是 `String`。
- ⚠ 文档未说明：印章审核时长；企业认证链接的有效期。
