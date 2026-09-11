# 事件订阅与回调（长连接 / Webhook、challenge、验签、解密、去重）

来源：`open.feishu.cn/document/server-docs/event-subscription-guide/*`、`event-subscription-guide/callback-subscription/*`、
`server-side-sdk/python--sdk/handle-events.md`（抓取于 2026-09-11）。**本文所有行为描述均为文档原文，未实测**；
无凭证探测只覆盖了出口 IP 接口（第 12 节）。

## 目录

1. [事件 vs 回调](#1-事件-vs-回调)
2. [两种接收方式：长连接 vs 发送至开发者服务器](#2-两种接收方式)
3. [开发者后台配置顺序（漏了"发布"就收不到）](#3-开发者后台配置顺序)
4. [长连接：Python SDK](#4-长连接python-sdk)
5. [Webhook ①：请求地址校验（challenge）](#5-webhook-请求地址校验)
6. [Webhook ②：签名校验](#6-webhook-签名校验)
7. [Webhook ③：解密](#7-webhook-解密)
8. [事件结构 v1.0 vs v2.0](#8-事件结构)
9. [推送、重试、去重、有序](#9-推送重试去重有序)
10. [完整手写接收器（Flask）](#10-完整手写接收器)
11. [用 SDK 做 Webhook 接收](#11-用-sdk-做-webhook-接收)
12. [获取事件出口 IP](#12-获取事件出口-ip)
13. [回调（卡片交互、链接预览）](#13-回调)
14. [本 skill 涉及的事件速查](#14-事件速查)
15. [排错](#15-排错)
16. [容易写错的地方](#16-容易写错的地方)

---

## 1. 事件 vs 回调

| | 事件 | 回调 |
|---|---|---|
| 性质 | 异步通知（员工离职、收到消息、审批状态变了） | 同步请求（用户点了卡片按钮、打开链接预览），前端在等你的响应 |
| 你要返回什么 | 3 秒内 HTTP 200 即可 | **3 秒内返回业务响应内容**（新卡片、toast、预览数据） |
| 失败补推 | 有：15 秒、5 分钟、1 小时、6 小时，最多 4 次 | **没有**，超时即失败，客户端显示报错 |
| 加密 / 验签 | 同一套 | 同一套（旧版卡片回调 `card.action.trigger_v1` 例外） |

---

## 2. 两种接收方式

| | 使用长连接接收 | 发送至开发者服务器（Webhook） |
|---|---|---|
| 原理 | 用官方 SDK 与平台建 WebSocket，事件从通道推过来 | 平台向你配置的公网 URL 发 HTTP POST |
| 适用 | **仅企业自建应用**（商店应用只能用 Webhook） | 自建、商店都可 |
| 公网要求 | 只要能访问公网，不需要公网 IP / 域名 / 内网穿透 | 需要 **IPv4 公网地址**（`http://` 或 `https://`） |
| 加解密 / 验签 | SDK 在建连时鉴权，之后推送是明文，**无需解密验签** | 自己按 Encrypt Key 解密、验签 |
| 限制 | 每应用最多 50 个连接；**集群模式**：多个客户端时只有随机一个收到；3 秒内处理完且不抛异常 | **每个应用只能配一个请求地址**，所有事件都发到这里 |

文档推荐：已集成 SDK 的企业自建应用用长连接。

---

## 3. 开发者后台配置顺序

1. **（Webhook 才需要）加密策略**：「开发配置 → 事件与回调 → 加密策略」配置 `Encrypt Key`（建议配，配了推送就是密文）；`Verification Token` 自动生成。
2. **订阅方式**：「事件与回调 → 事件配置 → 订阅方式」选长连接或填请求地址。
   - 长连接：要先让 SDK 客户端连上，才能保存"使用长连接接收事件"。
   - Webhook：点保存时平台立刻发 challenge 校验（第 5 节），不通过保存不了。
3. **添加事件**：选"应用身份订阅"或"用户身份订阅"，勾选事件，一键开通所需权限。
   大多数事件用应用身份；日历、邮箱事件只支持用户身份；云文档两者都支持。
4. **发布应用**：即使权限已审批通过，**添加事件后也必须创建版本并发布，配置才生效**。
5. 某些业务还要额外调接口开启：**审批事件必须调 `POST /open-apis/approval/v4/approvals/:approval_code/subscribe`**（见 [approval.md](approval.md)）。

同一事件不要同时订阅 v1.0 和 v2.0，否则收到两份（例如"通讯录变更 v1.0"+"员工离职 v2.0"）。

---

## 4. 长连接：Python SDK

```python
import os
import lark_oapi as lark

def on_message(data: lark.im.v1.P2ImMessageReceiveV1) -> None:          # v2.0 事件：P2 + 事件类型驼峰
    print(lark.JSON.marshal(data, indent=2))

def on_v1_event(data: lark.CustomizedEvent) -> None:                     # v1.0 事件一律用 CustomizedEvent
    print(lark.JSON.marshal(data, indent=2))

handler = lark.EventDispatcherHandler.builder("", "") \
    .register_p2_im_message_receive_v1(on_message) \
    .register_p1_customized_event("approval_instance", on_v1_event) \
    .build()

cli = lark.ws.Client(os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"],
                     event_handler=handler, log_level=lark.LogLevel.INFO)
cli.start()     # 阻塞；连上后日志打印 "connected to wss://..."
```

- 长连接模式下 `EventDispatcherHandler.builder` 的两个参数**必须填空字符串**。
- 注册方法名规则：`register_p2_<事件类型把 . 换成 _>`，如 `im.message.receive_v1` → `register_p2_im_message_receive_v1`，
  类型 `lark.im.v1.P2ImMessageReceiveV1`；v1.0 事件用 `register_p1_customized_event("<事件 type>", fn)`。
- handler 里不要做耗时操作（3 秒）；抛异常会被当作失败而重推。

---

## 5. Webhook ①：请求地址校验

在后台保存请求地址时，平台 POST 一个校验请求，**必须在 1 秒内原样返回 `challenge`**，否则报"Challenge code 没有返回"。

未配置 Encrypt Key 时请求体：

```json
{"challenge": "ajls384kdjxxxx", "token": "xxxxxx", "type": "url_verification"}
```

配置了 Encrypt Key 时请求体是 `{"encrypt": "..."}`，**先解密**得到上面的结构。两种情况响应都是：

```json
{"challenge": "ajls384kdjxxxx"}
```

- 校验请求**不需要做签名校验**（文档：安全校验"不包括请求网址校验"）。
- 本地测试（文档给的命令，确认未配置 Encrypt Key）：

```bash
curl -v "$YOUR_CALLBACK_URL" -H 'Content-Type: application/json' \
  --data '{"challenge":"ajls384kdj1234","type":"url_verification","token":"<your verification token>"}'
```

---

## 6. Webhook ②：签名校验

配置了 Encrypt Key 时，每个事件请求头带：

| 请求头 | 含义 |
|---|---|
| `X-Lark-Request-Timestamp` | 时间戳 |
| `X-Lark-Request-Nonce` | 随机串 |
| `X-Lark-Signature` | 签名 |

算法：**`sha256( timestamp + nonce + encrypt_key + 原始请求体 )` 的十六进制小写串**，与 `X-Lark-Signature` 比较。

- **是纯 SHA-256 摘要，不是 HMAC-SHA256**，encrypt_key 是拼进内容里的，不是 HMAC 的 key。
- body 必须是**原始字节**，不能先 `json.loads` 再 `json.dumps`（文档 Go / PHP 示例注释："不要在反序列化后再计算"）。

```python
import hashlib, hmac

def verify_signature(headers, raw_body: bytes, encrypt_key: str) -> bool:
    ts = headers.get("X-Lark-Request-Timestamp", "")
    nonce = headers.get("X-Lark-Request-Nonce", "")
    expected = hashlib.sha256((ts + nonce + encrypt_key).encode("utf-8") + raw_body).hexdigest()
    return hmac.compare_digest(expected, headers.get("X-Lark-Signature", ""))
```

时间戳的可接受偏差、防重放窗口 ⚠ 文档未说明。

**Verification Token 校验**（安全性较低的替代方案）：比较事件里的 token 与后台的 Verification Token——
v1.0 事件在顶层 `token`，v2.0 事件在 `header.token`。未配 Encrypt Key 时它是明文传输的，文档建议有 Encrypt Key 就用签名校验。

---

## 7. Webhook ③：解密

加密原理（文档原文）：AES-256-CBC；key = `SHA256(Encrypt Key)`（32 字节）；随机 16 字节 IV；PKCS7 填充；
收到的密文 = `base64(iv + encrypted_event)`。

```python
import base64, hashlib, json
from Crypto.Cipher import AES          # pip install pycryptodome

def decrypt_event(encrypt: str, encrypt_key: str) -> dict:
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    raw = base64.b64decode(encrypt)
    iv, ciphertext = raw[:16], raw[16:]
    plain = AES.new(key, AES.MODE_CBC, iv).decrypt(ciphertext)
    plain = plain[:-plain[-1]]          # 去 PKCS7 填充
    return json.loads(plain.decode("utf-8"))
```

文档自测向量：`decrypt("P37w+VZImNgPEO1RBhJ6RtKl7n6zymIbEG1pReEzghk=", key="test key")` 的明文是 `hello world`（非 JSON，测试时直接看字节串）。

---

## 8. 事件结构

**v2.0**（推荐；有 `schema` 字段）：

```json
{"schema": "2.0",
 "header": {"event_id": "f7984f25108f8137722bb63cee927e66", "token": "066zT6pS...",
            "create_time": "1603977298000000", "event_type": "contact.user_group.created_v3",
            "tenant_key": "xxxxxxx", "app_id": "cli_xxxxxxxx"},
 "event": {}}
```

**v1.0**（无 `schema`；审批事件仍是这个结构）：

```json
{"ts": "1502199207.7171419", "uuid": "bc447199585340d1f3728d26b1c0297a",
 "token": "41a9425ea7df4536a7623e38fa321bae", "type": "event_callback",
 "event": {"type": "p2p_chat_create", "app_id": "cli_...", "tenant_key": "..."}}
```

判断方法：有 `schema == "2.0"` → 事件类型在 `header.event_type`；否则 → 在 `event.type`。

---

## 9. 推送、重试、去重、有序

- **超时**：TCP 建连 2 秒、整体 3 秒内要返回 HTTP 200（长连接：3 秒内处理完且不抛异常）。耗时业务先落库 / 入队再异步处理。
- **失败重推**：15 秒、5 分钟、1 小时、6 小时，最多 4 次——重复窗口约 **7.1 小时**。
- **成功也可能重复**："至少一次"投递，链路超时会触发内部重发。所以**必须幂等**：
  - v1.0 用 `uuid`；v2.0 用 `header.event_id`；
  - 例外：`im.message.receive_v1` 文档要求用 `message.message_id` 去重、"不要依赖 event_id"。⚠ 文档自相矛盾（通用规则 vs 该事件页）。
  - 审批事件：文档说可用 `event_id` 或 `uuid`，按具体事件结构确定。
- **有序事件**：部分事件（如审批）按顺序推送，**前一个没成功响应，后一个不会推**，会进重试队列排队。
  一个事件处理失败会卡住同类后续事件（审批 FAQ 原文："服务端未及时响应时，开放平台将不会继续发送审批实例 A 的其他状态变更事件"）。
- 查看是否推送成功：开发者后台「日志检索 → 事件日志检索」，状态 `SUCCESS`；`retry cnt > 1` 说明是重推。

---

## 10. 完整手写接收器

不依赖 SDK，同时处理 challenge、签名、解密、token 校验、去重、快速响应（按文档规则组织，**未实测**）：

```python
import base64, hashlib, hmac, json, os, threading
from Crypto.Cipher import AES
from flask import Flask, request, jsonify

ENCRYPT_KEY = os.environ.get("FEISHU_ENCRYPT_KEY", "")          # 未配置加密策略时为空
VERIFICATION_TOKEN = os.environ["FEISHU_VERIFICATION_TOKEN"]
app = Flask(__name__)
_seen = set()                                                  # 生产用 Redis SETNX + 过期 8 小时

def _decrypt(enc: str) -> dict:
    key = hashlib.sha256(ENCRYPT_KEY.encode()).digest()
    raw = base64.b64decode(enc)
    plain = AES.new(key, AES.MODE_CBC, raw[:16]).decrypt(raw[16:])
    return json.loads(plain[:-plain[-1]].decode())

def _sig_ok(raw: bytes) -> bool:
    h = request.headers
    s = hashlib.sha256((h.get("X-Lark-Request-Timestamp", "") + h.get("X-Lark-Request-Nonce", "")
                        + ENCRYPT_KEY).encode() + raw).hexdigest()
    return hmac.compare_digest(s, h.get("X-Lark-Signature", ""))

@app.post("/feishu/events")
def events():
    raw = request.get_data()                                   # 原始字节，先于任何 JSON 解析
    data = json.loads(raw)
    if "encrypt" in data:
        data = _decrypt(data["encrypt"])
    if data.get("type") == "url_verification":                 # 1 秒内原样返回
        if data.get("token") != VERIFICATION_TOKEN:
            return "", 403
        return jsonify({"challenge": data["challenge"]})
    if ENCRYPT_KEY and not _sig_ok(raw):
        return "", 401
    is_v2 = data.get("schema") == "2.0"
    token = data["header"]["token"] if is_v2 else data.get("token")
    if token != VERIFICATION_TOKEN:
        return "", 403
    event_type = data["header"]["event_type"] if is_v2 else data["event"]["type"]
    if event_type == "im.message.receive_v1":
        dedup_key = data["event"]["message"]["message_id"]
    else:
        dedup_key = data["header"]["event_id"] if is_v2 else data["uuid"]
    if dedup_key in _seen:
        return "", 200
    _seen.add(dedup_key)
    threading.Thread(target=handle, args=(event_type, data), daemon=True).start()   # 3 秒内先回 200
    return "", 200

def handle(event_type, data):
    ...
```

---

## 11. 用 SDK 做 Webhook 接收

```python
from flask import Flask
import lark_oapi as lark
from lark_oapi.adapter.flask import *
from lark_oapi.api.im.v1 import *

app = Flask(__name__)

def on_message(data: P2ImMessageReceiveV1) -> None:
    print(lark.JSON.marshal(data))

handler = lark.EventDispatcherHandler.builder(ENCRYPT_KEY, VERIFICATION_TOKEN, lark.LogLevel.DEBUG) \
    .register_p2_im_message_receive_v1(on_message) \
    .build()

@app.route("/event", methods=["POST"])
def event():
    return parse_resp(handler.do(parse_req()))
```

Webhook 模式下后台配了 Encrypt Key / Verification Token 的，**必须传给 builder**（长连接模式则传空字符串）。SDK 处理了 challenge、解密、验签。

---

## 12. 获取事件出口 IP

**Endpoint**: `GET /open-apis/event/v1/outbound_ip`
**用途**: 拿平台推送事件用的出口 IP，配置防火墙白名单。需 tenant_access_token + 权限 `event:ip_list`。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `page_size` | int | 否 | 最大 50 |
| `page_token` | string | 否 | |

响应 `data.ip_list`（string[]）、`has_more`、`page_token`。IP 可能变更，文档建议定期拉取自动更新；变更前平台会发卡片消息和更新日志。
错误码 `1810001 param is invalid`（分页参数）。

无凭证探测（2026-09-11）：不带 token → HTTP 400 `{"code":99991661,"msg":"Missing access token for authorization..."}`，路径存在。

---

## 13. 回调

| 回调 | 类型 | 说明 |
|---|---|---|
| 卡片回传交互 | `card.action.trigger` | 用户点击卡片上配置了回传交互的组件；可返回 toast、更新后的卡片 |
| 拉取链接预览数据 | `url.preview.get` | 用户在聊天里看到匹配应用 URL 规则的链接；返回文字链或卡片预览 |
| 消息卡片回传交互（旧） | `card.action.trigger_v1` | 旧协议，兼容历史机器人配置；**本文的验签和解密不适用**，要看旧版「配置回调请求地址」文档 |

回调结构与 v2.0 事件相同（`schema`、`header.token`、`header.event_type`、`event.operator`、`event.context`...），
接收方式、challenge、签名、解密与事件相同，但要在 **3 秒内返回业务响应**，且没有补推。
Python SDK 处理回调见 `server-side-sdk/python--sdk/handle-callbacks`（本 skill 未展开，⚠ 以文档页为准）。

---

## 14. 事件速查

| 业务 | event_type | 结构版本 | 详见 |
|---|---|---|---|
| 接收消息 | `im.message.receive_v1` | 2.0 | [messaging-bots.md](messaging-bots.md) |
| 员工入职 / 离职 / 信息变更 | `contact.user.created_v3` / `contact.user.deleted_v3` / `contact.user.updated_v3` | 2.0 | [contacts.md](contacts.md) |
| 部门新建 | `contact.department.created_v3` | 2.0 | [contacts.md](contacts.md) |
| 审批实例 / 任务状态变更 | `approval_instance` / `approval_task` | **1.0** | [approval.md](approval.md) |
| 多维表格记录变更 | `drive.file.bitable_record_changed_v1` | 2.0 | [bitable.md](bitable.md) |
| 飞书人事：员工完成入职 / 人员信息变更 | `corehr.job_data.employed_v1` / `corehr.employee.domain_event_v2` | 2.0 | [corehr.md](corehr.md) |
| 机器人菜单 | `application.bot.menu_v6` | 2.0 | |
| 商店应用 app_ticket | `app_ticket`（每小时推送） | ⚠ 未抓取 | [auth.md](auth.md) |

---

## 15. 排错

| 现象 | 查什么 |
|---|---|
| 保存请求地址报"Challenge code 没有返回" | 1 秒内返回？配了 Encrypt Key 时先解密再取 challenge？地址是 IPv4 公网、以 http(s):// 开头？ |
| 提示"请填写有效的 HTTP/HTTPS URL" | 先用第 5 节 curl 本地测；防火墙是否挡了平台请求；内网穿透工具是否稳定 |
| 配好了收不到事件 | 应用**发布**了吗？事件所需权限开了吗？审批事件调了 subscribe 吗？「事件日志检索」有没有推送记录？ |
| 同一事件收到两次 | 3 秒内没回 200 被重推（看 retry cnt）；或同时订阅了 v1.0 和 v2.0 版本 |
| 审批事件突然都不来了 | 有序事件被前一个未成功响应的事件卡住 |
| 长连接多实例只有一个收到 | 集群模式设计如此，不是广播 |

---

## 16. 容易写错的地方

1. 签名是 `sha256(timestamp + nonce + encrypt_key + raw_body)`，**不是 HMAC**；body 用原始字节。
2. 解密 key 是 `SHA256(Encrypt Key)`，IV 是密文 base64 解码后的**前 16 字节**。
3. challenge 要 **1 秒内**返回，配了加密要先解密；校验请求不做签名校验。
4. 事件 3 秒内回 200，业务异步做；否则重推 4 次、窗口约 7 小时，还可能卡住有序事件。
5. 去重：v2 用 `event_id`、v1 用 `uuid`，**接收消息事件用 `message_id`**。
6. 改完事件订阅要**发布应用**；审批事件还要调 subscribe 接口。
7. 长连接只支持自建应用；多个客户端是"随机一个收到"，不是每个都收到。
8. v2.0 的 token 在 `header.token`，v1.0 在顶层 `token`；审批事件是 v1.0 结构。
