# 个人与机构的实名认证、用户授权（SaaS API V3）

> 内容整理自 e签宝开放平台《实名认证和授权服务API V3》（`open.esign.cn/doc/opendoc/auth3/*`）、
> 《SaaS API产品概念说明》、《认证授权回调通知》、错误码页 `codemsg-v3/agi7xuv4yrw1i8f3`（抓取于 2026-09-11）。
> **未用真实凭证调用验证**；报错与行为除特别注明外均为「文档原文，未实测」。
> 示例里的 `esign_request()` 是 [auth-and-signing.md §5](auth-and-signing.md) 的签名封装。

## 目录

1. [先判断：你到底需不需要这组接口](#1-先判断你到底需不需要这组接口)
2. [两种模式：实名认证模式 vs 授权认证模式](#2-两种模式实名认证模式-vs-授权认证模式)
3. [查询个人认证信息（拿 psnId）](#3-查询个人认证信息拿-psnid)
4. [查询机构认证信息（拿 orgId）](#4-查询机构认证信息拿-orgid)
5. [获取个人认证&授权页面链接](#5-获取个人认证授权页面链接)
6. [获取机构认证&授权页面链接](#6-获取机构认证授权页面链接)
7. [授权范围 authorizedScopes 对照](#7-授权范围-authorizedscopes-对照)
8. [查询授权信息与认证授权流程详情](#8-查询授权信息与认证授权流程详情)
9. [认证授权相关回调](#9-认证授权相关回调)
10. [⚠ 本文件的未说明 / 矛盾之处](#10--本文件的未说明--矛盾之处)

---

## 1. 先判断：你到底需不需要这组接口

- **企业自用系统**（OA、HRM、CRM，由平台自身企业发起并盖章，对方只是签字）：文档原文“通常情况下不需要使用授权服务”。
  签署人没实名也没关系——签署页自带实名认证，`create-by-file` 里直接用手机号 + 姓名指定签署人即可（见 [sign-flows.md §3.4](sign-flows.md)）。
  可选：签署前先单独做实名，避免签署时因信息不符卡住。
- **第三方平台**（SaaS 服务商，要以客户企业 / 个人的名义发起签署、查其身份信息、管理其印章或模板）：必须先让用户完成**授权**，
  否则相关接口返回 `1436116 用户:%s未授权:org_initiate_sign` 之类的错误。
- **版本限制**（文档原文，页面顶部红字）：自 2024-09-12 起，`authorizedScopes` 的部分权限需要 e签宝**高级版或生态伙伴版**；
  例如 `psn_initiate_sign`、`use_org_order` 仅生态伙伴版可指定，`get_psn_identity_info`、`manage_psn_resource` 需高级版或生态伙伴版。
  标准版应用传这些 scope 的结果 ⚠ 文档未说明具体报错。

两个账号 ID：个人 `psnId`（一个手机号 / 邮箱对应一个），机构 `orgId`（一个企业名称对应一个）。
文档建议开发者在本地保存“账号 ID ↔ 手机号 / 邮箱 / 企业名称”的对应关系。

---

## 2. 两种模式：实名认证模式 vs 授权认证模式

同一个“获取认证&授权页面链接”接口，靠 `authorizeConfig.authorizedScopes` 切换：

| 模式 | 怎么触发 | 用户已实名时 |
| --- | --- | --- |
| 实名认证模式 | 不传 `authorizeConfig`，或 `authorizedScopes` 为空 | **接口直接报错**：个人 `1450005 个人用户已实名`，机构 `1450006 企业用户已实名` |
| 授权认证模式 | `authorizedScopes` 有值 | 正常返回链接；用户只需做意愿认证（刷脸或短信验证码）后授权 |

所以正确顺序是：**先查认证信息（§3/§4）→ 未实名才用实名模式；需要授权就用授权模式。**
机构授权时若经办人既不是法定代表人也不是管理员，授权后还需管理员审批才生效（`authorizedStatus=2 授权中` / `3 审批未通过`）。

---

## 3. 查询个人认证信息（拿 psnId）

**Endpoint**: `GET /v3/persons/identity-info`

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| psnId | query | 三选一 | 个人账号 ID |
| psnAccount | query | 三选一 | 手机号或邮箱 |
| psnIDCardNum | query | 三选一 | 证件号；传它时 `psnIDCardType` 必传 |
| psnIDCardType | query | 条件 | `CRED_PSN_CH_IDCARD` / `CRED_PSN_CH_HONGKONG` / `CRED_PSN_CH_MACAO` / `CRED_PSN_CH_TWCARD` / `CRED_PSN_PASSPORT` |

```python
r = esign_request("GET", "/v3/persons/identity-info", query={"psnAccount": "13800000000"})
d = r["data"]
print(d["realnameStatus"], d["authorizeUserInfo"], d["psnId"])
```

响应关键字段：`realnameStatus`（0 未实名，1 已实名）、`authorizeUserInfo`（是否已授权给当前应用）、`psnId`；
`psnAccount`、`psnInfo`（姓名 / 证件等）**只有用户授权过 `get_psn_identity_info` 且 `authorizeUserInfo=true` 时才返回**。
错误码：`1450008 未找到用户信息，请检查查询数据的正确性 :%s`（从没注册过）、`1435203 账号不存在或已注销 :%s`。

GET 的 query 参数要进签名串（按 key 升序、值不编码），实际 URL 里中文要 urlencode——`esign_request` 已处理。

---

## 4. 查询机构认证信息（拿 orgId）

**Endpoint**: `GET /v3/organizations/identity-info`

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| orgId | query | 三选一 | 机构账号 ID（优先级最高） |
| orgName | query | 三选一 | 机构名称（次之） |
| orgIDCardNum | query | 三选一 | 机构证件号（最低）；传它时 `orgIDCardType` 必传（`CRED_ORG_USCC` 统一社会信用代码 / `CRED_ORG_REGCODE` 工商注册号） |

```python
r = esign_request("GET", "/v3/organizations/identity-info", query={"orgName": "某某科技有限公司"})
org_id = r["data"]["orgId"]
```

响应关键字段：`realnameStatus`、`authorizeUserInfo`、`orgId`、`orgName`、`orgAuthMode`、
`orgInfo.{orgIDCardNum, orgIDCardType, legalRepName, adminName(脱敏), adminAccount(脱敏)}`；
法定代表人证件号、对公账户、`cert`（数字证书）等需 `get_org_identity_info` 授权后才返回。
**平台自身企业的 orgId** 也可以用这个接口按企业名称查（帮助文档另有页面方式）。

---

## 5. 获取个人认证&授权页面链接

**Endpoint**: `POST /v3/psn-auth-url`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| psnAuthConfig | object | **是** | 不传账号时用户自己在页面填手机号 / 邮箱注册 |
| psnAuthConfig.psnAccount / psnId | string | 二选一 | 不知道 psnId 就传手机号 / 邮箱 |
| psnAuthConfig.psnInfo | object | 否 | `psnName`、`psnIDCardNum`、`psnIDCardType`、`psnMobile`（运营商或银行卡预留手机号，仅认证用）、`bankCardNum` |
| psnAuthConfig.psnIdentityVerify | boolean | 否 | 默认 false；true 时若传入信息与该账号在 e签宝的信息不一致则报错 |
| psnAuthConfig.psnAuthPageConfig | object | 否 | `psnDefaultAuthMode`（默认 `PSN_FACE`；另有 `PSN_MOBILE3`、`PSN_BANKCARD4`）、`psnAvailableAuthModes`、`psnEditableFields`（name / IDCardNum / mobile / bankCardNum）、`advancedVersion` |
| authorizeConfig.authorizedScopes | list | 否 | 传了 = 授权认证模式，见 §7 |
| redirectConfig.redirectUrl | string | 否 | 认证完成跳转，域名须在控制台放行 |
| redirectConfig.redirectDelayTime | **string** | 否 | 授权模式默认 3 秒；实名模式默认 5 秒（且只有 0 或 5 两种效果） |
| notifyUrl | string | 否 | 认证 / 授权结果回调地址 |
| clientType | string | 否 | `ALL`（默认）/ `H5` / `PC` |
| noticeTypes | string | 否 | `""` 不通知（默认）/ `1` 短信 / `2` 邮件 |

**iframe 内嵌不支持刷脸认证**（文档原文）。

```python
r = esign_request("POST", "/v3/psn-auth-url", body={
    "psnAuthConfig": {
        "psnAccount": "13800000000",
        "psnInfo": {"psnName": "张三"},
        "psnAuthPageConfig": {"psnDefaultAuthMode": "PSN_MOBILE3",
                              "psnAvailableAuthModes": ["PSN_MOBILE3", "PSN_FACE"]},
    },
    "authorizeConfig": {"authorizedScopes": ["get_psn_identity_info"]},
    "notifyUrl": "https://app.example.com/esign/auth-notify",
    "redirectConfig": {"redirectUrl": "https://app.example.com/auth-done"},
    "clientType": "ALL",
})
auth_flow_id, auth_url = r["data"]["authFlowId"], r["data"]["authShortUrl"]
```

响应：`authUrl`（长链接，30 天）、`authShortUrl`（短链接，30 天）、`authFlowId`（保存它，§8 查询用）。
文档概念页：30 天内用相同入参再次发起，`authFlowId` 不变。
错误码：`1450001 缺少参数：%s`、`1450002 参数错误：%s`、`1450003 参数格式错误：%s`、`1450005 个人用户已实名`、
`1450004 用户id：%s 由于接口版本问题不可用，请使用用户信息发起授权`（此时改传 psnAccount 而不是 psnId）。

---

## 6. 获取机构认证&授权页面链接

**Endpoint**: `POST /v3/org-auth-url`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| orgAuthConfig | object | **是** | 机构认证配置 |
| orgAuthConfig.orgName / orgId | string | 二选一 | 不知道 orgId 就传名称 |
| orgAuthConfig.orgInfo | object | 否 | `orgIDCardNum`、`orgIDCardType`、`legalRepName`、`legalRepIDCardNum`、`legalRepIDCardType`、`orgBankAccountNum`（仅对公打款认证） |
| orgAuthConfig.orgAuthPageConfig | object | 否 | `orgDefaultAuthMode` / `orgAvailableAuthModes`（`ORG_BANK_TRANSFER` 对公打款，`ORG_ALIPAY_CREDIT` 法人快捷，`ORG_LEGALREP_INVOLVED` 法定代表人 / 法人授权…）、`orgEditableFields` |
| orgAuthConfig.transactorInfo | object | 否 | 经办人：`psnId` 或 `psnAccount`，`psnInfo.{psnName, psnIDCardNum, psnIDCardType, bankCardNum, psnMobile}`、`psnIdentityVerify` |
| orgAuthConfig.transactorAuthPageConfig | object | 否 | 经办人个人认证页配置（同个人） |
| authorizeConfig.authorizedScopes | list | 否 | 见 §7 |
| authorizeConfig.transactorUseSeal | boolean | 否 | 默认 false；经办人非管理员时是否为其申请企业全部印章的用印权限（仅授权模式生效） |
| redirectConfig / notifyUrl / clientType / appScheme / noticeTypes | — | 否 | 同个人 |
| orgIdentityVerify | boolean | 否 | 默认 false；按证件号校验时企业名称与 e签宝已有信息不一致是否报错 |

```python
r = esign_request("POST", "/v3/org-auth-url", body={
    "orgAuthConfig": {
        "orgName": "某某科技有限公司",
        "orgInfo": {"orgIDCardNum": "91330000XXXXXXXXXX", "orgIDCardType": "CRED_ORG_USCC"},
        "transactorInfo": {"psnAccount": "13900000000", "psnInfo": {"psnName": "李四"}},
    },
    "authorizeConfig": {"authorizedScopes": ["get_org_identity_info", "org_initiate_sign", "psn_initiate_sign"]},
    "notifyUrl": "https://app.example.com/esign/auth-notify",
    "clientType": "ALL",
})
```

响应同个人：`authUrl`、`authShortUrl`、`authFlowId`。错误码多一个 `1450006 企业用户已实名`。
**首次为企业做实名的经办人自动成为企业管理员**（概念页原文）。

---

## 7. 授权范围 authorizedScopes 对照

| scope | 主体 | 允许应用做什么 |
| --- | --- | --- |
| `get_psn_identity_info` | 个人 / 经办人 | 获取姓名、手机号 / 邮箱、证件号等 |
| `get_org_identity_info` | 机构 | 获取机构基本信息（法定代表人证件号、对公打款信息等） |
| `psn_initiate_sign` | 个人 / 经办人 | 代表个人发起合同签署并查询详情 |
| `org_initiate_sign` | 机构 | 代表机构发起合同签署并查询详情（含下载） |
| `manage_psn_resource` | 个人 | 管理个人印章等资源 |
| `manage_org_resource` | 机构 | 管理机构印章、组织成员等资源 |
| `manage_org_member` / `manage_org_seal` / `manage_org_template` | 机构 | 分别管理成员 / 印章 / 模板 |
| `use_org_template` | 机构 | 使用机构的模板 |
| `use_org_order` | 机构 | 使用机构的套餐订单（“发起方付费”场景） |
| `org_approval_info` | 机构 | 获取用印审批信息 |
| `manage_org_contract` | 机构 | 合同管理（2026-01-22 新增） |
| `org_sign_file_storage` / `psn_sign_file_storage` | 机构 / 个人 | 专属云本地存储 |
| `apply_psn_evidence` | 个人 | 代个人申请出证（2025-09-22 新增） |

以平台身份代客户企业发起签署（`signFlowInitiator.orgInitiator`）通常需要 `org_initiate_sign` + 经办人的 `psn_initiate_sign`。

---

## 8. 查询授权信息与认证授权流程详情

| Endpoint | 用途 |
| --- | --- |
| `GET /v3/persons/{psnId}/authorized-info` | 个人（或经办人）授予当前应用的 scope 与 `effectiveTime` / `expireTime`（毫秒）；未实名报 `1450910 个人未实名` |
| `GET /v3/organizations/{orgId}/authorized-info` | 机构授予的 scope 与有效期；未实名报 `1450909 企业未实名` |
| `GET /v3/auth-flow/{authFlowId}` | 一次认证授权流程的详情；不存在报 `1450007 授权流程id不存在` |

`/v3/auth-flow/{authFlowId}` 关键响应字段：`authType`（ORG / PSN）、`realNameOrWillingness`（realName / willingness / none）、
`realNameStatus`（0/1）、`authorizedStatus`（**0 流程过期失效，1 已授权，2 授权中，3 审批未通过**）、`authUrl`、
`authInfo.{willingnessAuthModes, psnAuthMode, orgAuthMode}`、`person.{psnId, psnAccount, psnInfo}`、
`organization.{orgId, orgName, orgInfo}`、`authorizedInfo[].{authorizedScope, effectiveTime, expireTime}`。

---

## 9. 认证授权相关回调

回调地址：接口里的 `notifyUrl`，或控制台 Webhook（见 [callbacks.md](callbacks.md)）。验签方式与签署回调相同。

| action | 触发 | 关键字段 |
| --- | --- | --- |
| `AUTH_PASS` | 个人或机构实名认证通过 | `authFlowId`、`authType`（PSN/ORG）、`bizType`（`REAL_NAME` / `UPDATE-INFO`）、`psnInfo.psnId` 或 `organization.{orgId, orgName, transactor}` |
| `AUTHORIZE_FINISH` | 授权完成 | `psnId`（经办人）、`orgId`、`authFlowId`、`authorizedInfo[].{authorizedScope, effectiveTime, expireTime}`、`legalRepCheck`、`adminCheck`、`transactorUseSeal` |
| `AUTHORIZE_CHANGE` | 授权范围变更 | 字段见原文 `notify3/cgw9f3sa5dgoqynf`（本 skill 未展开） |

实践建议：收到 `AUTH_PASS` 时保存 `psnId` / `orgId`；收到 `AUTHORIZE_FINISH` 时保存 `expireTime`，到期前重新发起授权。

---

## 10. ⚠ 本文件的未说明 / 矛盾之处

| 位置 | 问题 |
| --- | --- |
| §8 | 错误码页把“查询机构授权信息”写成 `GET /v3/persons/{psnId}/authorized-info`，接口页是 `GET /v3/organizations/{orgId}/authorized-info`（⚠ 文档自相矛盾，按接口页） |
| §5 | `redirectDelayTime` 在认证接口里类型是 string，签署接口里是 int32（⚠ 同名字段类型不一致） |
| §1 | 标准版应用传高级版 / 生态伙伴版才支持的 scope 时返回什么 ⚠ 文档未说明 |
| §6 | 机构授权需管理员审批时，`AUTHORIZE_FINISH` 是在审批通过后才推送还是提交时推送 ⚠ 文档未说明 |
