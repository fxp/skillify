# 个人 / 企业认证与授权

> 来源：dev.fadada.com FASC OpenAPI 5.1「认证授权管理」（概述、获取个人/企业授权链接、查询个人/企业授权状态、解除个人/企业授权）、
> 「附录 / 基本概念」「附录 / 常用数据结构 / OpenId」「回调事件 / 授权相关事件」「错误码说明」，抓取于 2026-09-11。
> **未用真实凭证验证**：报错与行为描述均为文档原文，未实测。请求封装 `fasc_call`（Python）/ `fasc_call`（shell）见 [auth-and-signing.md](auth-and-signing.md)。

## 目录

1. [先分清几种 ID](#1-先分清几种-id)
2. [什么时候必须走授权](#2-什么时候必须走授权)
3. [授权范围与接口的对应关系](#3-授权范围与接口的对应关系)
4. [标准流程](#4-标准流程)
5. [获取个人授权链接](#5-获取个人授权链接)
6. [获取企业授权链接](#6-获取企业授权链接)
7. [授权结果：重定向参数与验签](#7-授权结果重定向参数与验签)
8. [查询个人授权状态](#8-查询个人授权状态)
9. [查询企业授权状态](#9-查询企业授权状态)
10. [解除授权](#10-解除授权)
11. [授权回调事件（摘要）](#11-授权回调事件摘要)
12. [相关错误码](#12-相关错误码)
13. [本文未展开的同域接口](#13-本文未展开的同域接口)
14. [⚠ 汇总](#14--汇总)

---

## 1. 先分清几种 ID

| ID | 谁定义 | 说明 |
| --- | --- | --- |
| `clientUserId` / `clientCorpId` | 你 | 你系统里个人 / 企业的唯一标识，最长 64 字符。对接前就要定好用什么（用户 ID、员工号、统一社会信用代码…），之后不要变 |
| `openUserId` / `openCorpId` | 法大大 | 该主体在**你这个 AppId** 范围内的唯一标识，最长 64 字符。同一个人在不同应用下 openId 不同 |
| 法大大号（`actorFDDId`） | 法大大 | 主体在法大大平台的全局号码（个人、企业各一套），最长 20 字符 |
| `memberId` | 法大大 | 企业成员 ID |

多数业务接口用 **OpenId 对象**指代主体（`initiator`、`ownerId` 等）：

```json
{"idType": "corp", "openId": "<openCorpId>"}
{"idType": "person", "openId": "<openUserId>"}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `idType` | string | 是 | `corp` 企业 / `person` 个人 |
| `openId` | string | 是 | `idType=corp` 时是 openCorpId，`person` 时是 openUserId；最长 64 |

## 2. 什么时候必须走授权

文档列出的场景（文档原文）：

- 应用要访问主体的资源：实名身份信息、签名 / 印章、签署任务、签署文档等；
- 应用要**以该主体名义发起签署**；
- 想让用户提前完成实名认证；
- 想拿到主体的 `openUserId` / `openCorpId` 便于后续维护。

不需要走授权的情况：

- **集成应用所属的企业自己**：创建应用时平台默认生成它的 openCorpId 并授予全部授权范围，在 SaaS「集成 - 应用详情」页面顶部可以看到。
  所以"企业自用、只以本企业名义发合同"不需要调企业授权接口。（文档：集团分、子公司不支持默认创建。）
- **只是来签字的外部签署方**：不是你应用用户的签署方不必登记到法大大，他们通过签署链接登录法大大完成实名和签署；
  在签署任务参与方里用 `identNameForMatch` / `certNoForMatch` / `accountName` 约束身份即可（见 [sign-tasks.md](sign-tasks.md)）。

## 3. 授权范围与接口的对应关系

`authScopes`（请求时传）/ `authScope`（结果里返回）的取值：

| 取值 | 个人 | 企业 | 含义（文档原文） | 典型依赖它的接口 |
| --- | --- | --- | --- | --- |
| `ident_info` | ✓ | ✓ | 获取身份 / 认证信息 | `/user/get-identity-info`、`/corp/get-identity-info` |
| `seal_info` | ✓ | ✓ | 获取签名 / 印章资源 | 印章、签名查询类接口 |
| `organization` | | ✓ | 获取企业组织数据 | 组织管理类接口 |
| `template` | | ✓ | 获取企业模板数据，可用其模板发起签署 | `/sign-template/*`、`/doc-template/*`、`/template/*/get-url` |
| `signtask_init` | ✓ | ✓ | 代表主体发起签署 | `/sign-task/create`、`/sign-task/create-with-template`、`/sign-task/start`、`/sign-task/abolish` |
| `signtask_info` | ✓ | ✓ | 获取主体的签署任务 | 查询签署任务详情、`/sign-task/owner/get-list`、`/sign-task/owner/get-file` |
| `signtask_file` | ✓ | ✓ | 获取主体的签署文件 | `/sign-task/owner/get-download-url` |
| `file_storage` | ✓ | ✓ | 签署文件存到应用的企业服务器（仅开启本地存储时生效） | — |
| `contract_info` | | ✓ | 获取企业合同数据 | 合同归档类 |
| `billaccount_info` | ✓ | ✓ | 获取计费数据 | 计费类 |
| `smartform` | | ✓ | 获取收集表数据 | 收集表类 |

缺授权时返回 `213001`–`213008`（文档标 HTTP 401），见 §12。

## 4. 标准流程

1. 服务端调 `/user/get-auth-url` 或 `/corp/get-auth-url`，传你的 `clientUserId` / `clientCorpId`、要申请的 `authScopes`、`redirectUrl`。
2. 把返回的 `authUrl`（个人还有 `authShortUrl`）交给用户打开，**7 天有效**。用户在法大大页面注册/登录、实名认证、确认授权。
3. 结果从两条通道回来：
   - 浏览器跳回 `redirectUrl`，URL 上带签名的 query 参数（§7）；
   - 服务端收到回调事件 `user-authorize` / `corp-authorize`（§11，验签见 [callbacks.md](callbacks.md)）。
   未设置 `redirectUrl` 时，授权结果只通过回调事件通知。
4. 保存 `clientXxxId ↔ openXxxId` 映射，之后发起签署、查询都用 openId。
5. 需要时用 `/user/get`、`/corp/get` 主动查询绑定、实名、授权范围。

建议以**回调事件或主动查询**为准，重定向参数只用于前端跳转展示。

## 5. 获取个人授权链接

**Endpoint**: `POST /user/get-auth-url`

**用途**: 获取一个页面链接，个人用户在里面完成实名认证和资源授权，授权后应用拿到 `openUserId`。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `clientUserId` | string | 是 | 个人在你系统中的唯一标识，≤64 |
| `accountName` | string | 否 | 法大大帐号（仅手机号或邮箱），≤60；未注册会以此注册 |
| `unbindAccount` | boolean | 否 | clientUserId 已绑定其他帐号或实名信息不一致时，是否默认解绑旧帐号并以本次信息更新，默认 false |
| `userIdentInfo` | object | 否 | 预填的个人认证信息 |
| `userIdentInfo.userName` | string | 否 | 真实姓名，≤80 |
| `userIdentInfo.userIdentType` | string | 否 | `id_card` / `hk_mac_rp` / `taiwan_rp` / `foreign_prc` / `passport` / `hk_macao` / `taiwan` / `hk_macao_foreigner`；带了它 `userIdentNo` 才生效 |
| `userIdentInfo.userIdentNo` | string | 否 | 证件号，≤50 |
| `userIdentInfo.nationalityCode` | string | 否 | 国籍代码，仅 `hk_macao_foreigner` 时有效 |
| `userIdentInfo.mobile` | string | 否 | 手机号，≤30 |
| `userIdentInfo.bankAccountNo` | string | 否 | 银行卡号，≤30 |
| `userIdentInfo.identMethod` | string[] | 否 | 实名方式，按顺序作为优先级：`face` / `mobile` / `bank` / `offline`（人工审核）；默认都可用 |
| `userIdentInfo.faceauthMode` | string | 否 | 刷脸方式：`tencent`（腾讯云 H5）/ `megvii`（旷视，可嵌小程序） |
| `nonEditableInfo` | string[] | 否 | 页面上不可编辑的项：`accountName` / `userName` / `userIdentType` / `userIdentNo` / `nationalityCode` / `mobile` / `bankAccountNo` |
| `authScopes` | string[] | 否 | 申请的授权范围，见 §3 |
| `freeSignInfo.businessId` | string | 否 | 授权同时把默认签名设为免验证签的场景码（人工审核认证完成后无法开通） |
| `redirectUrl` | string | 否 | 完成后跳转地址，≤1000，**需要 URL 编码**（文档示例 `URLEncoder.encode(url, "UTF-8")`） |
| `redirectMiniAppUrl` | string | 否 | 小程序原生页面路径（不支持 tabBar 页），需编码 |
| `callbackUrl` | string | 否 | 该用户授权事件单独的回调地址；设置后不再发到应用配置的回调地址 |

**示例请求**

```python
from urllib.parse import quote
from fasc_client import fasc_call

data = fasc_call("/user/get-auth-url", {
    "clientUserId": "u_10086",
    "accountName": "13800000000",
    "userIdentInfo": {
        "userName": "张三",
        "userIdentType": "id_card",
        "userIdentNo": "（用户真实证件号）",
        "identMethod": ["face", "mobile"],
    },
    "nonEditableInfo": ["userName", "userIdentNo"],
    "authScopes": ["ident_info", "signtask_init", "signtask_info", "signtask_file"],
    "redirectUrl": quote("https://app.example.com/fadada/auth-return", safe=""),
})
print(data["authUrl"], data.get("authShortUrl"))
```

```bash
fasc_call /user/get-auth-url '{"clientUserId":"u_10086","authScopes":["ident_info","signtask_init"]}'
```

**示例响应**

```json
{"code": "100000", "msg": "请求成功",
 "data": {"authUrl": "https://…/authorizeui/perlogin?authSerial=…", "authShortUrl": "…"}}
```

| 字段 | 说明 |
| --- | --- |
| `authUrl` | 授权链接，7 天有效，自适应 PC/H5；仅 PC 支持 iframe，H5 与微信小程序用 web-view，公众号内用跳转 |
| `authShortUrl` | 短链接，7 天有效 |

**注意事项**

- `clientUserId` 若未关联 openUserId，用户同意授权后才生成 openUserId，通过重定向或回调告知（文档原文）。
- ⚠ 文档自相矛盾：请求示例把 `userName`、`userIdentType`、`userIdentNo` 同时写在顶层和 `userIdentInfo` 里；字段表只在 `userIdentInfo` 下定义。按字段表放进 `userIdentInfo`。
- ⚠ `redirectUrl` 要求 URL 编码，而它本身又在 bizContent JSON 里、整个表单还会再编码一次；平台是否按"编码一次"解析，文档未说明，按文档写法编码一次。

## 6. 获取企业授权链接

**Endpoint**: `POST /corp/get-auth-url`

**用途**: 企业在页面里完成（经办人注册与实名、企业创建与实名、）授权；已认证企业只有超管能授权，或经办人发申请给超管。
集成应用所属企业默认已授权，**不需要调**。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `clientCorpId` | string | 是 | 企业在你系统中的唯一标识，≤64 |
| `clientUserId` | string | 否 | 经办人在你系统中的标识，用于经办人帐号免登映射 |
| `accountName` | string | 否 | 经办人法大大帐号（手机号或邮箱） |
| `corpIdentInfo.corpName` | string | 否 | 企业名称，≤128，用于从经办人的企业列表里精确匹配 |
| `corpIdentInfo.corpIdentType` | string | 否 | `corp`（默认）/ `individual_biz` 个体工商户 / `other` |
| `corpIdentInfo.corpIdentNo` | string | 否 | 统一社会信用代码，≤50 |
| `corpIdentInfo.legalRepName` | string | 否 | 法定代表人姓名 |
| `corpIdentInfo.licenseFileId` | string | 否 | 营业执照图片 fileId（`fileType=auth` 上传处理，≤5M，见 [files.md](files.md)） |
| `corpIdentInfo.corpIdentMethod` | array | 否 | `legalRep` / `legalRepFace` / `legalRepSms` / `agent` / `invite` / `bank` / `letter` |
| `corpNonEditableInfo` | string[] | 否 | `corpName` / `corpIdentType` / `corpIdentNo` |
| `oprIdentInfo` | object | 否 | 经办人信息：`userName`（仅中文）、`userIdentType`、`userIdentNo`、`nationalityCode`、`mobile`、`bankAccountNo`、`oprIdentMethod`（`face`/`mobile`/`bank`）、`faceauthMode` |
| `oprNonEditableInfo` | string[] | 否 | 经办人不可编辑项 |
| `authScopes` | string[] | 否 | 企业授权范围，见 §3 |
| `freeSignInfo.businessId` | string | 否 | 免验证签场景码（目前仅支持企业认证后自动生成的公章） |
| `redirectUrl` | string | 否 | ≤500，需 URL 编码 |
| `redirectMiniAppUrl` | string | 否 | 小程序页面路径 |
| `appDevelopInfo` | object | 否 | 委托代开发（仅开通该模式的第三方应用），本 skill 不展开 |
| `callbackUrl` | string | 否 | 该企业授权事件单独的回调地址 |

**示例请求**

```python
data = fasc_call("/corp/get-auth-url", {
    "clientCorpId": "corp_2001",
    "clientUserId": "u_10086",
    "corpIdentInfo": {"corpName": "示例科技有限公司", "corpIdentType": "corp",
                      "corpIdentNo": "（统一社会信用代码）"},
    "corpNonEditableInfo": ["corpName", "corpIdentNo"],
    "authScopes": ["ident_info", "seal_info", "template",
                   "signtask_init", "signtask_info", "signtask_file"],
    "redirectUrl": quote("https://app.example.com/fadada/corp-auth-return", safe=""),
})
print(data["authUrl"])
```

**示例响应**：`{"code":"100000","msg":"请求成功","data":{"authUrl":"https://…/authorizeui/corp/login?authSerial=…"}}`（7 天有效）

**注意事项**

- ⚠ 文档自相矛盾：请求示例把 `corpName`、`corpIdentNo`、`corpIdentType` 也写在顶层，并用了字段表里没有的 `oprIdentInfo.identType`；按字段表放在 `corpIdentInfo` / `oprIdentInfo.userIdentType`。
- 文档没有企业授权响应里 `authShortUrl` 的字段（个人有）。

## 7. 授权结果：重定向参数与验签

用户完成后跳回 `redirectUrl`，附带 query 参数：

| 参数 | 个人 | 企业 | 说明 |
| --- | --- | --- | --- |
| `timestamp` | ✓ | ✓ | 毫秒时间戳 |
| `signature` | ✓ | ✓ | 签名值，"您可自行决定是否验证该签名" |
| `clientUserId` / `clientCorpId` | ✓ | ✓ | 你的标识 |
| `openUserId` / `openCorpId` | ✓ | ✓ | 法大大分配的 openId |
| `authResult` | ✓ | ✓ | `success` / `fail` |
| `authFailedReason` | ✓ | ✓ | 个人：`exist`（已存在授权）；企业：`reject`（用户不允许）/ `exist` |
| `authScope` | ✓ | ✓ | 实际授权范围，逗号分隔 |

签名算法与请求签名相同（[auth-and-signing.md §4](auth-and-signing.md#4-签名算法逐步)），参数集合是上表除 `signature` 外的参数，时间戳用 query 里的 `timestamp`：

```python
import hmac
from fasc_client import fasc_sign, APP_SECRET

def verify_auth_redirect(query: dict) -> bool:
    """query：已 URL 解码的参数字典（如 Flask request.args.to_dict()）"""
    params = {k: v for k, v in query.items() if k != "signature"}
    expected = fasc_sign(params, params.get("timestamp", ""), APP_SECRET)
    return hmac.compare_digest(expected, query.get("signature", ""))
```

- ⚠ 文档自相矛盾：请求签名规则是"值为空的字段不参与签名"，但重定向验签的 Java 示例注释写"参数值为空，则传空串"（把 `authFailedReason=""` 放进参与签名的 map）。
  `FddCryptUtil.sortParameters` 会不会跳过空串文档没给出实现。上面的 `fasc_sign` 跳过空值；如果验不过，再试一次"空值也参与"的拼法。
- ⚠ 企业重定向的验签示例文档没给，参数集合按上表推断。
- ⚠ 如果你的 `redirectUrl` 本身带 query 参数，它们是否参与签名文档未说明——`redirectUrl` 尽量不带自己的参数。
- 结论：重定向只用于前端跳转，**业务状态以回调事件或 `/user/get`、`/corp/get` 查询结果为准**。

## 8. 查询个人授权状态

**Endpoint**: `POST /user/get`

**用途**: 查个人用户的绑定状态、实名状态、授权范围、启用状态。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `clientUserId` | string | 二选一 | 你的标识 |
| `openUserId` | string | 二选一 | 法大大 openId。**只能传一个，不能都不传**（两个都传 → `210055`，都不传 → `210053`） |

**示例请求**

```python
info = fasc_call("/user/get", {"clientUserId": "u_10086"})
if info["bindingStatus"] == "authorized" and "signtask_init" in (info.get("authScope") or []):
    ...
```

**示例响应**（文档示例节选）

```json
{"code": "100000", "msg": "请求成功",
 "data": {"clientUserId": "AutoClientUserId1656985245", "openUserId": "745c3bbcaddc46abbf01cd61e28d7aee",
          "bindingStatus": "unauthorized", "authScope": ["ident_info"],
          "identStatus": "unidentified", "availableStatus": "disable"}}
```

| 字段 | 说明 |
| --- | --- |
| `bindingStatus` | 字段表只列 `authorized`；示例里出现 `unauthorized` |
| `identStatus` | 字段表只列 `identified`；示例里出现 `unidentified` |
| `availableStatus` | `enable` / `disable` |
| `authScope` | 已授权范围数组 |

- ⚠ 文档自相矛盾：`bindingStatus`、`identStatus` 的字段表枚举不全（示例出现了表里没有的 `unauthorized` / `unidentified`）；代码按"不是 authorized / identified 就当未完成"处理。
- ⚠ 文档示例里有一个 `clientUserName` 字段、授权范围写成 `dent_info`（疑似笔误），字段表均无。
- ⚠ 文档请求示例同时传了 `clientUserId` 和 `openUserId`，与"只能二选一"的说明矛盾；按说明只传一个。

## 9. 查询企业授权状态

**Endpoint**: `POST /corp/get`

**用途**: 查企业绑定、授权范围、实名状态；已授权企业会返回认证信息。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `corpIdentNo` | string | 三选一 | 统一社会信用代码 |
| `clientCorpId` | string | 三选一 | 你的标识 |
| `openCorpId` | string | 三选一 | 法大大 openId。三个只能传一个、不能都不传 |

**示例响应字段**

| 字段 | 说明 |
| --- | --- |
| `clientCorpId` / `openCorpId` | 标识 |
| `entityType` | `primary` 主企业 / `subsidiary` 成员企业 |
| `bindingStatus` | `unauthorized` / `authorized` |
| `authScope` | 授权范围数组 |
| `identStatus` | `unidentified`（未授权绑定也当未认证）/ `identified` |
| `availableStatus` | `enable` / `disable` |

```bash
fasc_call /corp/get '{"clientCorpId":"corp_2001"}'
```

- ⚠ 文档请求示例同时传了 `openCorpId` 和 `clientCorpId`，与"三选一"矛盾（企业侧 `210056`：openCorpId 和 clientCorpId 不能同时传入）。

## 10. 解除授权

**Endpoint**: `POST /user/unbind`

**用途**: 解除个人的帐号绑定和授权范围。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `clientUserId` | string | 二选一 | 传它 = 只解除该 clientUserId 的**免登关系** |
| `openUserId` | string | 二选一 | 传它 = 解绑该 openUserId 并**清空授权范围**，同时解除免登 |

**Endpoint**: `POST /corp/unbind`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `openCorpId` | string | 是 | 要解绑的企业 |

两者成功响应都是 `{"code":"100000","msg":"请求成功"}`；解除后会有 `user-cancel-authorization` / `corp-cancel-authorization` 回调事件（文档把这两个事件描述为"用户取消授权后"触发，⚠ 接口解除是否也触发未说明）。
未实名绑定时解除：个人 `210051`，企业 `210052`。

## 11. 授权回调事件（摘要）

完整字段与验签见 [callbacks.md](callbacks.md)。

| 事件 ID（`X-FASC-Event`） | 触发 | 关键字段 |
| --- | --- | --- |
| `user-authorize` | 个人授权允许 / 不允许 / 身份匹配失败 | `clientUserId`、`openUserId`、`authResult`、`authFailedReason`、`authScope`、`identProcessStatus`、`identMethod`、`availableStatus`、`userName`/`identNo`（需 `ident_info`）、`existClientUserId`/`existOpenUserId` |
| `corp-authorize` | 企业授权允许后 | `clientCorpId`、`openCorpId`、`authResult`、`authScope`、`corpIdentProcessStatus`、`corpName`、`corpIdentNo`、`clientUserIds`、`memberId` |
| `user-cancel-authorization` | 个人取消授权 | `clientUserId`、`openUserId` |
| `corp-cancel-authorization` | 企业取消授权 | `clientCorpId`、`openCorpId` |

`authFailedReason=exist` 表示"当前应用已存在授权"，此时 `existOpenUserId` / `existOpenCorpId` 给出之前授权时的 openId——用它关联已有记录，不要当失败处理。

## 12. 相关错误码

文档原文，未实测。完整表见 [errors-and-limits.md](errors-and-limits.md)。

| code | 含义 | 处理 |
| --- | --- | --- |
| 213001 | 未授权【企业信息或身份信息】 | 走授权链接申请 `ident_info` |
| 213002 | 未授权【签署任务创建及发起】 | 申请 `signtask_init` |
| 213004 | 未授权管理【签署任务】 | 申请签署任务相关范围 |
| 213005 | 未授权管理【模板管理】 | 企业授权 `template` |
| 213006 | 未授权管理【签署文件】 | 申请 `signtask_file` |
| 213007 | 未授权查询【印章及用印员】 | 企业授权 `seal_info` |
| 213008 | 未授权查询【组织管理】 | 企业授权 `organization` |
| 210013 | 授权范围重复获取 | 已授权，无需再取链接 |
| 210022 / 210032 | 个人 / 企业用户不存在（或已禁用） | 检查 openId；已禁用先恢复 |
| 210023 / 210033 | 个人 / 企业未认证通过 | 引导完成实名授权 |
| 210026 / 210039 | clientUserId / clientCorpId 已被使用 | 已绑定其他 openId |
| 210053 / 210054 | open 与 client 两个标识不能同时为空 | 传一个 |
| 210055 / 210056 | open 与 client 两个标识不能同时传入 | 只传一个 |

## 13. 本文未展开的同域接口

以下接口在「API概览」中列出，本 skill 未展开参数，需要时去 dev.fadada.com 认证授权管理目录查看：

| 接口 | 说明 |
| --- | --- |
| `/user/get-identity-info`、`/corp/get-identity-info` | 查询实名身份信息（需 `ident_info`） |
| `/user/disable`、`/user/enable`、`/corp/disable`、`/corp/enable` | 禁用 / 恢复主体使用电子签服务 |
| `/corp/get-identified-status` | 按企业名称和统一社会信用代码判断是否已在法大大认证 |
| 获取企业控制台链接、获取更换登录帐号链接、获取找回帐号链接 | 页面类接口 |

## 14. ⚠ 汇总

- 个人 / 企业授权链接的请求示例与字段表结构不一致（§5、§6）。
- `redirectUrl` 编码次数（§5）。
- 重定向验签：空值是否参与签名、企业侧参数集合、redirectUrl 自带参数（§7）。
- `/user/get` 枚举不全、示例字段笔误、示例违反"二选一"（§8）；`/corp/get` 示例违反"三选一"（§9）。
- 接口解除授权是否触发取消授权回调（§10）。
