# 回调通知：接收、验签、重试与事件对照（SaaS API V3）

> 内容整理自 e签宝开放平台《回调通知服务 V3》（`open.esign.cn/doc/opendoc/notify3/*`）、《公有云API域名列表》（抓取于 2026-09-11）。
> **未用真实凭证验证，也没有收到过真实回调**；报错与行为均为「文档原文，未实测」。
> 验签函数用自造的本地向量校验过拼接逻辑（`esign-workspace/sign_check.py`）；文档自带示例的密钥已脱敏，示例签名**无法复现**。

## 目录

1. [回调地址怎么配：Webhook 与 notifyUrl](#1-回调地址怎么配webhook-与-notifyurl)
2. [e签宝发来的请求长什么样](#2-e签宝发来的请求长什么样)
3. [验签](#3-验签)
4. [怎么响应、重试机制](#4-怎么响应重试机制)
5. [Flask 接收端完整示例](#5-flask-接收端完整示例)
6. [事件（action）对照表](#6-事件action对照表)
7. [两个最常用的签署事件字段](#7-两个最常用的签署事件字段)
8. [网络与安全：IP 白名单](#8-网络与安全ip-白名单)
9. [回调 vs 前端重定向 vs 主动查询](#9-回调-vs-前端重定向-vs-主动查询)
10. [⚠ 本文件的未说明 / 矛盾之处](#10--本文件的未说明--矛盾之处)

---

## 1. 回调地址怎么配：Webhook 与 notifyUrl

| 方式 | 在哪配 | 覆盖 |
| --- | --- | --- |
| 方式一：开放平台 Webhook 事件订阅（**文档标注推荐**） | 控制台 →【正式服务】/【沙箱服务】→ 应用管理 → 我的应用 →【配置】→ Webhook → 添加 Webhook，并勾选要订阅的事件（签署类勾【v3版签署服务】） | 按勾选的事件 |
| 方式二：接口参数 `notifyUrl` | `create-by-file` / 页面发起的 `signFlowConfig.notifyUrl`；认证授权接口的 `notifyUrl`；流程模板发起的 `signFlowConfig.notifyUrl` | 该次流程 / 认证 |

**两种都配时两边都会推送；地址相同就会收到两次**（《签署回调通知接收说明》原文）。接收端必须幂等。

URL 格式要求：`{scheme}://{host}:{port}/{path}`，公网可访问；允许带 query（如 `/notify?type=x`）；不能有空格等特殊字符；
`localhost`、`127.0.0.1`、`192.168.x.x` 这类内网地址收不到。沙箱与正式分别配置。

---

## 2. e签宝发来的请求长什么样

- 方法：**HTTP POST**，body 是 **JSON**。
- 请求头（文档示例）：

```
X-Tsign-Open-App-Id: 74XXXXXX
X-Tsign-Open-TIMESTAMP: 1713508339505
X-Tsign-Open-SIGNATURE-ALGORITHM: hmac-sha256
X-Tsign-Open-SIGNATURE: 60c6719d33…
```

注意这几个头名的大小写与请求签名用的 `X-Tsign-Open-Ca-Signature` / `X-Tsign-Open-Ca-Timestamp` **不同**（`SIGNATURE`、`TIMESTAMP` 大写，没有 `Ca-`）。
HTTP 头名大小写不敏感，用框架的 headers 对象取值即可；PHP 里是 `$_SERVER['HTTP_X_TSIGN_OPEN_SIGNATURE']`。

- body 示例（签署方签署完成）：

```json
{"action":"SIGN_MISSON_COMPLETE","timestamp":1650262138252,"signFlowId":"38fe9cd191**bf9eefe74",
 "customBizNum":"xxxxx0408111","signOrder":1,"operateTime":1650262135000,"signResult":2,
 "resultDescription":"签署完成","operator":{"psnId":"c7e002947291***ea310541e7","psnAccount":{"accountMobile":"183****0101"}}}
```

用 `action` 分发；**action 以后可能新增**，只处理自己关心的，其余直接回 200 忽略。

---

## 3. 验签

文档提供两种安全机制，可单用或组合：IP 白名单（§8）、签名验签（本节）。

```
待验数据 = X-Tsign-Open-TIMESTAMP
         + 回调 URL 上 query 参数的“值”按 key 的 ASCII 升序直接拼接（没有 key、没有 = 和 &；URL 无 query 就是空串）
         + 请求 body 的原始字节
签名     = hex( HmacSHA256( key = AppSecret, msg = 待验数据 ) )，小写
比较对象 = 请求头 X-Tsign-Open-SIGNATURE
```

与**请求签名**的区别——最容易写错的地方：

| | 调 API 的请求签名 | 回调验签 |
| --- | --- | --- |
| 签名输出 | **Base64** | **hex（小写）** |
| 原文 | 7 行 `\n` 拼接的 StringToSign | `timestamp + query 值 + body`，没有换行、没有 method / path |
| 时间戳头 | `X-Tsign-Open-Ca-Timestamp` | `X-Tsign-Open-TIMESTAMP` |
| 签名头 | `X-Tsign-Open-Ca-Signature` | `X-Tsign-Open-SIGNATURE` |

实现要点：
- **用原始 body 字节**（Flask `request.get_data()`），不要 `json.loads` 再 `json.dumps`——键序、空格、中文转义一变签名就不对。
- query 只拼**值**：回调地址是 `http://demo.tsign.cn/notify?orderNo=001&belong=pinjie` 时，按 key 排序是 belong、orderNo，拼出 `pinjie001`。
  e签宝不会往你的 URL 上追加参数，所以 query 只可能是你自己配置时写的那些。
- 用常量时间比较（`hmac.compare_digest`）；.NET 示例是先算大写 hex 再 `ToLower()`，Java / PHP 示例直接是小写。
- ⚠ 文档没有规定时间戳的有效窗口，也没说重试时 `X-Tsign-Open-TIMESTAMP` 是否刷新；如果自己加“5 分钟内”的防重放校验，要先确认重试请求会不会被误拒。

```python
import hashlib, hmac

def verify_esign_callback(timestamp: str, signature: str, query: dict, raw_body: bytes, app_secret: str) -> bool:
    q = "".join(str(query[k]) for k in sorted(query)) if query else ""
    data = timestamp.encode("utf-8") + q.encode("utf-8") + raw_body
    calc = hmac.new(app_secret.encode("utf-8"), data, hashlib.sha256).hexdigest()
    return hmac.compare_digest(calc, (signature or "").lower())
```

本地向量（自造，AppSecret=`dummysecret`，timestamp=`1729489875363`，query `belong=pinjie&orderNo=001`，
body=`{"action":"SIGN_MISSON_COMPLETE","signFlowId":"x"}`）→ `3c736f140e22adf842c3c7d71dfd641e4f6c35c2109403b67ebb915d43a47e0c`。

---

## 4. 怎么响应、重试机制

- 返回 **HTTP 200–299** 即视为通知成功，否则视为失败。
- 建议 body 回 `{"code":"200","msg":"success"}`（e签宝不校验 body，但文档提醒 body 里不要有空格、`\/` 等，避免解析失败导致重复通知）。
- **建议 5 秒内返回**；业务处理（下载合同、写库、发消息）放到异步队列里做。
- 失败后**最多重试 16 次**，文档说不同模块有两种重试节奏，具体间隔只以**图片**给出（⚠ 本 skill 无法转录图片内容）；中途成功即停止。
- 重试时 body 里的 `timestamp` 字段**保持第一次的时间**（签署事件字段表原文“如重试多次均返回第一次时间”）。
- 长时间收不到回调，用查询接口兜底（`GET /v3/sign-flow/{signFlowId}/detail` 等）。

幂等建议：以 `action + signFlowId + signOrder/operator.psnId + body.timestamp`（签署方事件）或 `action + signFlowId`（流程结束事件）为去重键；
同一回调可能因重试或“Webhook + notifyUrl 双配置”到达多次。

---

## 5. Flask 接收端完整示例

```python
import json, os
from flask import Flask, request, jsonify

app = Flask(__name__)
APP_SECRET = os.environ["ESIGN_APP_SECRET"]

@app.post("/esign/notify")
def esign_notify():
    raw = request.get_data()                                # 原始字节，验签用
    ok = verify_esign_callback(
        request.headers.get("X-Tsign-Open-TIMESTAMP", ""),
        request.headers.get("X-Tsign-Open-SIGNATURE", ""),
        request.args.to_dict(),                             # 回调 URL 自带的 query（没有就是空）
        raw, APP_SECRET)
    if not ok:
        return jsonify({"code": "401", "msg": "bad signature"}), 401
    evt = json.loads(raw)
    action = evt.get("action")
    if action == "SIGN_FLOW_COMPLETE" and str(evt.get("signFlowStatus")) == "2":
        enqueue_download(evt["signFlowId"])                 # 异步：调 sign-flows.md §12 下载
    elif action == "SIGN_MISSON_COMPLETE":
        record_signer_result(evt["signFlowId"], evt.get("signResult"), evt.get("customBizNum"))
    # 其他 action 忽略
    return jsonify({"code": "200", "msg": "success"}), 200
```

`enqueue_download` / `record_signer_result` 由业务实现（务必幂等）。

---

## 6. 事件（action）对照表

签署类（订阅【v3版签署服务】或传 `notifyUrl`）：

| action | 事件 | 触发 |
| --- | --- | --- |
| `SIGN_FLOW_INITIATED` | 签署发起成功 | 签署流程发起成功 |
| `OPERATOR_READ` | 签署方-已读 | 签署方打开签署页 |
| `SIGN_MISSON_COMPLETE` | 签署方-签署结果（含拒签） | 某个签署方签完或拒签（**拼写就是 MISSON，少一个 I**） |
| `SIGN_FLOW_COMPLETE` | 签署流程结束（含拒签 / 撤销 / 过期） | 整个流程结束 |

目录中另有：签署方加入扫码签任务、签署人更正个人信息、经办人转交签署任务、用印审批驳回、合同发起解约、合同解约成功、
抄送方-已读、批量签署结果、签署文件加密完成、文件异步验签结果等通知（本 skill 未抓取其 action 值，见 `notify3` 目录）。

认证授权类：`AUTH_PASS`（实名认证通过）、`AUTHORIZE_FINISH`（授权完成）、`AUTHORIZE_CHANGE`（授权范围变更），字段见 [identity-authorization.md §9](identity-authorization.md)。

文件与模板类：`FILL_DOCTEMPLATE`（文件模板填写完成）、`FILL_DOCTEMPLATE_FAIL`（填写失败）、`GET_SEAL_POSITION`（获取签章位置信息）；另有“文件模板创建或编辑完成”（action 未抓取）。

流程模板类：`DRAFT_COMPLETE`（合同拟定结果）、`SIGN_FLOW_INITIATE_RESULT`（签署流程发起结果）；另有“流程模板创建完成”“流程填写人填写状态”（action 未抓取）。

印章、审批、企业控制台、账号管理、购买套餐、e签宝全网通知不在本 skill 范围，见 `https://open.esign.cn/doc/opendoc/notify3/pmy852` 目录。

---

## 7. 两个最常用的签署事件字段

**`SIGN_MISSON_COMPLETE`**（签署方维度）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| action | string | `SIGN_MISSON_COMPLETE` |
| timestamp | int64 | 回调触发时间（毫秒；重试也是第一次的时间） |
| signFlowId | string | 流程 ID |
| operateTime | int64 | 签署 / 拒签时间 |
| signResult | int32 | **2 签署完成，4 拒签** |
| resultDescription | string | 原因描述 |
| signOrder | int32 | 签署顺序 |
| customBizNum | string | 发起时签署区的 `customBizNum`；同一签署方多个签署区时逗号分隔返回多个 |
| operator | object | `psnId`、`psnName`、`psnAccount.{accountMobile, accountEmail}` |
| organization | object | 机构签署方时有：`orgId`、`orgName` |

**`SIGN_FLOW_COMPLETE`**（流程维度）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| signFlowId / signFlowTitle | string | |
| signFlowStatus | **string** | `"2"` 已完成，`"3"` 已撤销，`"5"` 已过期，`"7"` 已拒签（**注意是字符串，详情接口里同名字段是 int**） |
| statusDescription | string | 非完成结束时的原因 |
| signFlowCreateTime / signFlowStartTime / signFlowFinishTime | int64 | 毫秒 |

触发条件：autoFinish=true 时全部签完自动触发；autoFinish=false 时**只有调用 `/finish` 成功后才触发**；拒签、过期、撤销也会触发。
所以“收到 SIGN_FLOW_COMPLETE 就去下载”必须先判断 `signFlowStatus == "2"`。

---

## 8. 网络与安全：IP 白名单

回调来源 IP（入站白名单）：**正式 118.31.35.8，沙箱 47.96.79.204**，端口随机。文档给的 Nginx 示例：

```nginx
geo $remote_addr $ip_whitelist { default 0; include ip_white.conf; }   # ip_white.conf: allow 47.96.79.204; allow 118.31.35.8;
location /esign/notify {
    if ($ip_whitelist = 1) { proxy_pass http://127.0.0.1:8000; break; }
    return 403;
}
```

在反向代理后面取来源 IP 时看 `X-Forwarded-For` 的第一个值。IP 白名单和验签可以同时用。

---

## 9. 回调 vs 前端重定向 vs 主动查询

| 渠道 | 可信度 | 用途 |
| --- | --- | --- |
| 服务端回调（验签通过） | 高 | 驱动业务状态 |
| 前端重定向 `redirectUrl?tsignCode=0&signFlowId=…` | 低（用户可改 URL） | 只用于页面展示 |
| `GET /v3/sign-flow/{id}/detail` | 高 | 回调丢失时兜底、对账 |

---

## 10. ⚠ 本文件的未说明 / 矛盾之处

| 位置 | 问题 |
| --- | --- |
| §3 | 回调时间戳的有效窗口、重试时 `X-Tsign-Open-TIMESTAMP` 头是否更新 ⚠ 文档未说明 |
| §3 | 文档 Java 示例的 appSecret 已脱敏（含 `1111`），按示例数据算出的签名与示例给出的不一致，不能当测试向量 |
| §4 | 16 次重试的间隔只以图片给出，文字未说明 |
| §7 | `signFlowStatus` 回调里是 string、详情接口里是 int（⚠ 类型不一致） |
| §2 | 回调 body 的 Content-Type、字符集 ⚠ 文档未说明（示例为 JSON） |
