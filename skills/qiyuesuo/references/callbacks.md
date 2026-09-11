# 回调：接收、解密、验签与重复推送

> 来源：open.qiyuesuo.com「合同管理 / 创建合同草稿（回调一节）」「开放平台应用」「个人认证 / 企业认证 回调说明」「印章管理 / 创建图片印章回调说明」「授权管理 / 个人签名授权回调说明」「常见问题 / 其他问题」（抓取于 2026-09-11）；
> GitHub `qiyuesuo/jssdk-server`（`jssdk-csharp-server/proxy-csharp/Tools/CryptUtils.cs`）；下载中心 SDK changelog。
> **未用真实凭证验证，也没有收到过任何真实回调。** 本页全部为文档原文或官方示例代码转述，未实测。

## 目录

1. [五种回调一览（格式、重试、要回什么）](#1-五种回调一览格式重试要回什么)
2. [合同状态回调](#2-合同状态回调)
3. [加密回调与解密](#3-加密回调与解密)
4. [企业认证 / 个人认证回调](#4-企业认证--个人认证回调)
5. [图片印章审核回调](#5-图片印章审核回调)
6. [个人签名授权回调（唯一写明验签算法的）](#6-个人签名授权回调唯一写明验签算法的)
7. [配置回调地址的接口](#7-配置回调地址的接口)
8. [Flask 接收端示例](#8-flask-接收端示例)
9. [注意事项与 ⚠](#9-注意事项与-)

---

## 1. 五种回调一览（格式、重试、要回什么）

**所有回调都是 `POST` + `application/x-www-form-urlencoded`，不是 JSON body**（各回调页原文）。

| 回调 | 配置在哪 | 重试（文档原文） | 接收端要返回什么（文档原文） | 验签 |
| --- | --- | --- | --- | --- |
| 合同状态 | 应用配置 / 业务分类 / 创建草稿的 `callbackUrl` | 初次失败后再试 **7 次**：5 分钟、2 小时（×4）、12 小时、24 小时 | ⚠ 文档未说明 | ⚠ 文档未说明（可选加密） |
| 企业认证结果 | 认证链接接口的 `callbackUrl` | 不通立即重复一次，1 分钟后再 2 次，**共 4 次** | JSON `{"code":0}`；`code` 非 0 视为失败 | 无 |
| 个人认证结果 | 认证链接接口的 `callbackUrl` | 同上，共 4 次 | JSON `{"code":0}` | 无 |
| 图片印章审核 | `createbyimage` 的 `callbackUrl` | 再试 4 次：5 分钟、2 小时、12 小时、24 小时（页内又说"5 次回调结束后"） | `{"responseCode":00000000}` | 无 |
| 个人签名授权 | ⚠ 文档未说明 | 再试 4 次：5 分钟、2 小时、12 小时、24 小时 | HTTP 状态码 **< 400** 即成功，body 随意 | `MD5(timestamp + secretKey) == signature` |

共同原则（从上表推出，不是文档原话）：

- 用 `request.form` 读参数，不要 `request.get_json()`。
- 会**重复推送**（失败重试，最长跨度一天以上），处理必须**幂等**。
- 快速返回成功，把下载合同之类的重活放到后台。
- 每种回调要求的返回体不同，不要写一个通用的 `return "success"` 了事。

## 2. 合同状态回调

**触发**：合同签署、拒签、撤回、退回等状态变化（名词解释 / FAQ 原文）。

**回调地址的三处来源**：

1. 开放平台应用的回调地址：云平台集成管理配置，或 `POST /company/token/update/callback`（§7）；
2. 业务分类「回调设置」（FAQ 原文："在业务分类中的回调设置里配置好回调地址"）；
3. 创建合同草稿时的 `callbackUrl`（String ≤ 300）："若接口未传入回调地址，则向应用配置的回调地址回调"。
   ⚠ 文档未说明：业务分类回调与应用回调同时存在时的优先级。

**参数（创建合同草稿页"回调"一节，文档原文）**

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `contractId` | String | 合同 ID |
| `callbackType` | String | 通知类型，"具体类型信息见后方列表" |
| `contractStatus` | String | 合同状态，"具体类型信息见后方列表" |
| `tenantType` | String | 签署方类型 `PERSONAL` / `COMPANY` |
| `tenantName` | String | 签署方名称 |
| `contact` | String | 联系方式 |
| `tenantId` | String | 签署方 ID（组织为单位 ID，个人为用户 ID） |

另外：创建草稿 / 重新发起时传的 `businessData`（≤100 字）"会在合同回调时作为参数回调"。

- ⚠ 文档未说明：页面写"见后方列表"，但**后方没有列表**——`callbackType` 的取值在文档站任何页面都找不到。`contractStatus` 可以先按合同详情的状态枚举理解（`SIGNING` `COMPLETE` `REJECTED` `RECALLED` `EXPIRED` `INVALIDING` `INVALIDED` `FORCE_END`…，见 [signing.md](signing.md) §10），但回调里的实际取值未确认。
- ⚠ 文档未说明：接收端返回什么才算成功；有没有签名头可以验证来源。

**稳妥做法**（建议，不是文档要求）：回调只当"有变化了"的通知，拿 `contractId` 回头调 `GET /v2/contract/detail` 取权威状态再推进业务；这样既不依赖未公开的 `callbackType` 枚举，也等于用 AppToken/AppSecret 做了一次来源确认。

## 3. 加密回调与解密

- 应用可以开启回调加密：`encrypt`（Boolean）+ `encryptType`（`AES_ECB` / `AES_CBC`），密钥是 `callbackSecretKey`，都能从 `GET /company/token/get` 读到（[auth-and-signing.md](auth-and-signing.md) §9）。
- FAQ 原文："如果是希望明文反馈，配置好地址后停用加密即可。如果选择加密回调，具体看'操作手册'中的回调说明"——**这份"操作手册"不在开放平台文档站上**。
- 多个公司共用一个回调接口时，在回调地址后面拼参数区分，例如 `http://callback.com?company=A`，参数会原样带回，再按公司取各自的 key 解密（FAQ 原文）。
- SDK changelog：Python 3.3.7 / PHP 3.6.5 / Go 3.1.2（2025-10-28）"添加方法【用CBC模式进行AES解密】"；Java 3.9.8（2025-12-03）"用指定IV值使用CBC模式进行AES解密"。

官方 GitHub 示例（`qiyuesuo/jssdk-server` 的 C# `CryptUtils.AESDecrypt`，注释"AES 工具类用于解密回调数据"）的做法：Base64 解码 → AES **ECB** → 填充 `PaddingMode.Zeros` → 密钥是 secret 字符串的 UTF-8 字节 → UTF-8 解码。等价的 Python（需要第三方库 `pycryptodome`）：

```python
import base64
from Crypto.Cipher import AES   # pycryptodome

def qys_aes_ecb_decrypt(cipher_b64: str, secret_key: str) -> str:
    """按官方 jssdk-server C# 示例改写：AES-ECB，零填充，key = secret 的 UTF-8 字节。"""
    raw = base64.b64decode(cipher_b64)
    plain = AES.new(secret_key.encode("utf-8"), AES.MODE_ECB).decrypt(raw)
    return plain.rstrip(b"\x00").decode("utf-8")
```

- ⚠ 文档未说明：加密后**哪个表单字段**装密文、解密后是 JSON 还是表单串；`AES_CBC` 的 IV 取值；密钥长度要求（AES 要 16/24/32 字节）。以上只能用官方 SDK 的解密方法或向契约锁确认，拿到第一条真实回调时把原始 body 记日志对照。
- 没有这些信息之前，**最省事的选择是不开加密**，用 §2 的"回查合同详情"确认状态。

## 4. 企业认证 / 个人认证回调

### 企业认证
参数（「企业认证 / 回调说明」页）：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `status` | Integer | 0 认证中、1 认证成功、2 认证失败 |
| `actionEvent` | Integer | 0 提交基本信息、1 基本信息审核通过、2 基础信息审核失败、4 授权书审核失败、7 认证成功 |
| `requestId` | String | 认证请求 ID（获取链接时返回的那个） |
| `authInfo` | String | **JSON 字符串**：`{name, registerNo, legalPerson}`（汇总页另有 `applicantName`、`applicantPhone`） |

返回 `{"code":0}`；`{"code":1001}` 之类非 0 值表示接收失败。
⚠ 文档自相矛盾：汇总页「企业认证」里回调 `status` 只有 1 / 2，没有 `actionEvent`。

### 个人认证
参数：`mode`（`IVS` / `FACE` / `BANK` / `MANUAL`）、`status`（`1` 通过、`2` 不通过、`3` 人工审核中，**字符串**）、`authId`。返回 `{"code":0}`。

## 5. 图片印章审核回调

参数：`applyId`（创建图片印章返回的申请 ID）、`result`（`PASS` / `REJECT`）、`detail`（**JSON 字符串**：`sealType`、`sealName`、`sealId`（仅通过时）、`rejectReason`（仅拒绝时））。
返回（文档原文）：

```
{"responseCode":00000000}
```

⚠ 文档原文里的 `00000000` 没加引号，不是合法 JSON 数字写法（前导零）；按其他接口的习惯返回 `{"responseCode":"00000000"}` 是否被接受 ⚠ 文档未说明。

## 6. 个人签名授权回调（唯一写明验签算法的）

参数（文档原文）：

| 参数 | 位置 | 说明 |
| --- | --- | --- |
| `signature` | URL 参数 | 32 位小写 hex |
| `timestamp` | URL 参数 | 契约锁发送消息的时间戳 |
| `content` | 表单 | 业务数据 JSON 字符串：`companyId`、`companyName`、`assignee`（申请授权公司）、`user`、`userType`（`MOBLIE` / `EMAIL`，原文拼写）、`authDeadline`、`remark`、`item`（`AUTHORIZE` / `DEAUTHORIZE`）、`deauthorizeDate` |

验签（文档原文）：`MD5(timestamp + secretKey) == signature`。

```python
import hashlib, hmac

def verify_personalsign_callback(timestamp: str, signature: str, secret_key: str) -> bool:
    expected = hashlib.md5((timestamp + secret_key).encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected, signature)
```

- ⚠ 文档未说明：`secretKey` 具体是哪个密钥（应用的 `callbackSecretKey`？AppSecret？）；时间戳是秒还是毫秒（示例 `1675406185942` 为 13 位）、要不要做时效校验。
- 返回：HTTP 状态码 < 400 就算成功。

## 7. 配置回调地址的接口

### 修改开放平台应用回调配置
**Endpoint**: `POST /company/token/update/callback`（JSON）
**用途**: 把当前 AppToken 对应应用的回调地址 / 加密方式改成本次传入的值。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `callbackUrl` | String | 新回调地址 |
| `encrypt` | Boolean | 是否加密 |
| `encryptType` | String | `AES_ECB` / `AES_CBC` |

三者不能同时为空。返回 `result` = 应用信息（`appName`、`accessToken`、`callbackUrl`、`encrypt`、`callbackSecretKey`、`encryptType`）。
⚠ 文档自相矛盾：参数表把 `encryptType` 类型写成 `Boolean`，取值却是字符串枚举；按字符串传。

```python
app = qys_call("POST", "/company/token/update/callback",
               json_body={"callbackUrl": "https://your.app/qys/contract-callback", "encrypt": False})
```

### 查询
`GET /company/token/get`，见 [auth-and-signing.md](auth-and-signing.md) §9。

## 8. Flask 接收端示例

合同状态回调：表单读参数 → 幂等去重 → 立即返回 → 后台回查详情并下载。

```python
# pip install flask requests   （自行安装；本 skill 不附带依赖）
import threading
from flask import Flask, request, jsonify
from qys_client import qys_call

app = Flask(__name__)
_seen = set()          # 生产环境换成数据库唯一索引 / Redis SETNX

@app.post("/qys/contract-callback")
def contract_callback():
    form = request.form.to_dict()            # application/x-www-form-urlencoded
    contract_id = form.get("contractId")
    dedup_key = "|".join([contract_id or "", form.get("callbackType", ""),
                          form.get("contractStatus", ""), form.get("tenantId", "")])
    if contract_id and dedup_key not in _seen:
        _seen.add(dedup_key)
        threading.Thread(target=handle_contract_change, args=(contract_id,), daemon=True).start()
    # ⚠ 合同回调要求的返回体文档未说明；认证类回调要求 {"code":0}，这里沿用
    return jsonify({"code": 0})


def handle_contract_change(contract_id: str):
    c = qys_call("GET", "/v2/contract/detail", params={"contractId": contract_id})   # 以详情为准
    if c["status"] == "COMPLETE":
        for d in c.get("documents", []):
            if d.get("contentType", "CONTRACT") == "CONTRACT":
                pdf = qys_call("GET", "/v2/document/download", params={"documentId": d["id"]}, raw=True)
                with open(f"contracts/{contract_id}_{d['id']}.pdf", "wb") as f:
                    f.write(pdf)
    # 其他状态：SIGNING / REJECTED / RECALLED / EXPIRED / INVALIDED … 按业务更新


@app.post("/qys/companyauth")
def companyauth_callback():
    status = request.form.get("status")      # 0 认证中 / 1 成功 / 2 失败（回调口径）
    request_id = request.form.get("requestId")
    # ... 更新本地记录，可再调 GET /companyauth/result?requestId=... 核对
    return jsonify({"code": 0})
```

- 下载频次有锁定规则（同一文档 25 分钟内连续 10 次 → 锁 12 小时），重复回调时不要重复下载，见 [errors-and-limits.md](errors-and-limits.md) §6。
- 重试间隔最长 24 小时：回调入口挂了一天，恢复后仍会收到旧通知，所以一定要回查详情而不是信任回调里的状态顺序。

## 9. 注意事项与 ⚠

- ⚠ 文档未说明：合同回调 `callbackType` 枚举、返回体、验签方式、业务分类回调与应用回调的优先级（§2）；加密字段 / CBC IV / 密钥长度（§3）；个人签名授权回调的 `secretKey` 来源（§6）。
- ⚠ 文档自相矛盾：图片印章回调"尝试 4 次"vs"5 次回调结束后"；企业认证回调两套 `status`（§4）；`encryptType` 类型（§7）；个人签名授权 `userType` 拼写 `MOBLIE`。
- 回调来源 IP 文档未公布，无法按 IP 白名单过滤。
