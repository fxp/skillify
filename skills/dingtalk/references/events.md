# 事件订阅：Stream 模式 / HTTP 回调 / 加解密

来源：open.dingtalk.com/document 下「事件订阅概述」「配置事件推送方式」「开发事件推送服务」「HTTP回调概述」「通用回调事件」
「注册回调事件」「通讯录事件」「审批实例开始、结束、终止、删除」「审批任务开始，结束，转交」「套件票据」（抓取于 2026-09-11），
以及文档站链接的官方 GitHub `dingtalk-stream-sdk-python`、`dingtalk-callback-Crypto` README。
**除标注处外均为文档原文，未实测。** 本文件的解密代码用文档自带的测试向量做过**离线校验**（本地计算，不是 API 调用）。

## 目录

1. [选型：Stream / HTTP / SyncHTTP](#1-选型stream--http--synchttp)
2. [Stream 模式](#2-stream-模式)
3. [HTTP 推送：请求与应答格式](#3-http-推送请求与应答格式)
4. [HTTP 推送：加解密算法与 Python 实现](#4-http-推送加解密算法与-python-实现)
5. [ownerKey 到底填什么](#5-ownerkey-到底填什么)
6. [事件体：Stream 与 HTTP 字段不同](#6-事件体stream-与-http-字段不同)
7. [常用事件类型](#7-常用事件类型)
8. [旧版：用 API 注册回调（register_call_back）](#8-旧版用-api-注册回调register_call_back)
9. [⚠ 未说明 / 矛盾之处](#9--未说明--矛盾之处)

---

## 1. 选型：Stream / HTTP / SyncHTTP

| | Stream 模式（文档标"推荐"） | HTTP 推送（文档标"不推荐"） | SyncHTTP 推送 |
| --- | --- | --- | --- |
| 适用应用 | 企业内部应用、第三方企业应用 | 企业内部应用 | 第三方企业应用 |
| 需要公网地址 | 否（应用主动建 WebSocket 长连接） | 是 | 是 |
| 加解密 | 无需，收到的就是明文事件 | **需要**验签 + AES 解密 + 加密应答 | 需要（文档称可直接使用推送数据，细节本 skill 未覆盖） |
| 配置入口 | 开发者后台 → 应用 → 开发配置 → 事件订阅 → Stream 模式推送 | 同处选 HTTP 推送，填加密 aes_key / 签名 token / 请求网址 | 同处选 SyncHTTP |
| 覆盖范围 | 事件订阅、机器人收消息（topic `/v1.0/im/bot/messages/get`）、卡片回调（topic `/v1.0/card/instances/callback`） | 事件订阅 | 事件订阅 |

判断：**没有公网服务、或不想写加解密，就用 Stream。** 必须用 HTTP 的情况（已有网关、只能被动接收）才走第 3–5 节。
HTTP 推送的出口 IP 段（做白名单用）：`203.119.0.0/16`、`140.205.0.0/16`、`106.11.0.0/16`、`198.11.0.0/16`（文档原文）。
每个应用只能配置一个回调 URL，订阅的所有事件都推到这个地址。

---

## 2. Stream 模式

**官方 SDK**：Java（`com.dingtalk.open:app-stream-client`）、Go、Python（`pip install dingtalk-stream`）、Node.js。
Stream 连接用应用的 Client ID / Client Secret（即 AppKey/AppSecret 或 SuiteKey/SuiteSecret）鉴权。

配置顺序（文档原文）：先把 Stream 客户端跑起来 → 开发者后台点「已完成接入，验证连接通道」→「保存」→ 保存后事件订阅列表才会展示，再勾选要订阅的事件。
**客户端没连上就去后台保存会失败**，这是最常见的"配不上"原因。

```python
# pip install dingtalk-stream       —— 机器人回调示例，改写自官方 README
import os, dingtalk_stream
from dingtalk_stream import AckMessage

class Handler(dingtalk_stream.ChatbotHandler):
    async def process(self, callback: dingtalk_stream.CallbackMessage):
        msg = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
        self.reply_text("pong", msg)
        return AckMessage.STATUS_OK, "OK"

client = dingtalk_stream.DingTalkStreamClient(
    dingtalk_stream.Credential(os.environ["DINGTALK_APP_KEY"], os.environ["DINGTALK_APP_SECRET"]))
client.register_callback_handler(dingtalk_stream.chatbot.ChatbotMessage.TOPIC, Handler())
client.start_forever()          # 或在已有 asyncio loop 里 await client.start()，网络异常会自动重连
```

- 已有事件循环时用 `client.start()` + `client.stop()`；可用 `websocket_connect_options` 透传心跳 / 超时参数（README 原文）。
- 用 Python SDK 订阅**普通业务事件**（通讯录、审批）的 handler 写法，本次抓取的 README 未给示例 ⚠，参考 SDK 仓库示例或 Java 文档。
- FAQ 原文：一个应用可启动多个监听；企业内部应用"一个企业仅需配置一个Stream客户端"；第三方企业应用只需监听该应用即可收到所有授权企业的事件。
- Stream 事件体结构见第 6 节（外层 `eventType`/`eventCorpId`/`eventId`/`eventBornTime`，业务数据在 `data` 里）。
- 调用量超额时错误码 `20001`（消息服务暂停，需升级专业版 / 增购）。

---

## 3. HTTP 推送：请求与应答格式

**钉钉发给你**：

```
POST https://你的地址?signature=111108bb8e6dbc2xxxx&timestamp=1783610513&nonce=380320111
Content-Type: application/json

{"encrypt": "1ojQf0NSvw2WPvWxxxxxROsJq/HJ+q6tp1qhlxxxxxyBdI/dGOvsnBSCxxxxxQQasdfghjkl"}
```

**你必须回**（HTTP 200，JSON）：

```json
{"msg_signature": "111108bb8e6dbce3c9671d6fdb69d1506xxxx", "timeStamp": "1783610513", "nonce": "123456",
 "encrypt": "<字符串 success 加密后的密文>"}
```

- **应答里的 `encrypt` 是字符串 `"success"` 加密后的结果，不是明文 `success`，也不是空 200。** 只有返回它，钉钉才判定推送成功。
- 后台点「验证有效性」时，钉钉推一个 `EventType: check_url` 的事件，要求在 **1500ms 内**返回加密的 success（文档原文）。
- 应答字段名是 `msg_signature` 和 **驼峰的 `timeStamp`**；请求 URL 上文档写的是 `signature` 和 `timestamp`，
  而官方 Java 示例按 `msg_signature` 读 ⚠ 文档自相矛盾——官方 Crypto README 的写法是两种都兼容，照做：

```python
sig = request.args.get("msg_signature") or request.args.get("signature")
ts = request.args.get("timeStamp") or request.args.get("timestamp")
nonce = request.args.get("nonce")
encrypt = request.get_json()["encrypt"]
```

- 后台报"HTTP请求结果校验返回字段值失败"：返回的 JSON 某字段不对或不是 JSON（「配置事件推送方式 · 常见问题」原文）。
- ISV 的 `suite_ticket` 事件不回 success 会被连续推送，超过 100 次停止。

---

## 4. HTTP 推送：加解密算法与 Python 实现

算法（「HTTP回调概述」+ 官方 Java 类 `DingCallbackCrypto` 原文）：

- **签名**：`msg_signature = sha1("".join(sorted([token, timestamp, nonce, encrypt]))).hexdigest()`（四个字符串字典序排序后拼接）。
- **密钥**：`aes_key` 是后台填 / 生成的 **43 位**字符串；`key = Base64Decode(aes_key + "=")` 得 32 字节。
- **加密**：AES-256-CBC，**IV = key 前 16 字节**，PKCS7 填充，**块大小 32**（不是 AES 常见的 16）。
- **明文布局**：`random(16B) + msg_len(4B，网络字节序) + msg + ownerKey`；解密后要校验末尾的 ownerKey。
- 签名 token：3~32 位英文或数字（后台配置页原文）。

```python
# pip install cryptography
import base64, hashlib, os, secrets, struct, time
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

class DingCallbackCrypto:
    def __init__(self, token: str, aes_key: str, owner_key: str):
        self.token, self.owner_key = token, owner_key
        self.key = base64.b64decode(aes_key + "=")          # 43 位 → 32 字节

    def _sign(self, timestamp: str, nonce: str, encrypt: str) -> str:
        return hashlib.sha1("".join(sorted([self.token, timestamp, nonce, encrypt])).encode()).hexdigest()

    def decrypt(self, msg_signature: str, timestamp: str, nonce: str, encrypt: str) -> str:
        if self._sign(timestamp, nonce, encrypt) != msg_signature:
            raise ValueError("signature mismatch")
        d = Cipher(algorithms.AES(self.key), modes.CBC(self.key[:16])).decryptor()
        raw = d.update(base64.b64decode(encrypt)) + d.finalize()
        pad = raw[-1]
        if not 1 <= pad <= 32:
            raise ValueError("bad padding")
        raw = raw[:-pad]
        n = struct.unpack(">I", raw[16:20])[0]
        msg, owner = raw[20:20 + n].decode(), raw[20 + n:].decode()
        if owner != self.owner_key:
            raise ValueError(f"owner key mismatch: {owner}")   # 常见于 ownerKey 填错，见第 5 节
        return msg

    def encrypt_map(self, plaintext: str = "success") -> dict:
        ts, nonce = str(int(time.time() * 1000)), secrets.token_hex(8)
        data = plaintext.encode()
        body = os.urandom(16) + struct.pack(">I", len(data)) + data + self.owner_key.encode()
        pad = 32 - len(body) % 32
        body += bytes([pad]) * pad
        e = Cipher(algorithms.AES(self.key), modes.CBC(self.key[:16])).encryptor()
        enc = base64.b64encode(e.update(body) + e.finalize()).decode()
        return {"msg_signature": self._sign(ts, nonce, enc), "timeStamp": ts, "nonce": nonce, "encrypt": enc}
```

**离线校验（2026-09-11，本地计算）**：用「配置事件推送方式 · 常见问题」给的测试向量
（token `123456`、aes_key `1234567890123456789012345678901234567890123`、ownerKey `dingsnotzck6pm5veliw`、
signature `9a95a004dd16f5c307e849b994173f76aa26e5eb`、timestamp `1614767836`、nonce `A7Co0cJLMzIDtMMI`）解密得到 `"success"`；
`encrypt_map` → `decrypt` 往返一致。

Flask 接入骨架：

```python
import json
from flask import Flask, request, jsonify
app = Flask(__name__)
crypto = DingCallbackCrypto(os.environ["DINGTALK_CB_TOKEN"], os.environ["DINGTALK_CB_AES_KEY"],
                            os.environ["DINGTALK_APP_KEY"])        # 后台配置的事件订阅：ownerKey = AppKey

@app.post("/dingtalk/callback")
def callback():
    event = json.loads(crypto.decrypt(
        request.args.get("msg_signature") or request.args.get("signature"),
        request.args.get("timeStamp") or request.args.get("timestamp"),
        request.args["nonce"], request.get_json()["encrypt"]))
    if event.get("EventType") != "check_url":
        enqueue(event)                                # 先入队再返回，别在这里做慢操作
    return jsonify(crypto.encrypt_map("success"))
```

官方 Crypto 仓库另有 Java / Python2 / Python3 / PHP / C# 实现（Python 版依赖 `Crypto` 包），README 称"建议新的应用开发采用 DingTalk Stream Mode 代替 Webhook 方式"。

---

## 5. ownerKey 到底填什么

解密后末尾校验的 ownerKey 填错会报"计算解密文字corpid不匹配"。各页说法（原文）：

| 出处 | 说法 |
| --- | --- |
| 「HTTP回调概述」代码注释 | 开发者后台配置的订阅事件为**应用级**事件：企业内部应用填 **AppKey**，三方应用填 **SuiteKey**；调用订阅事件接口（register_call_back）订阅的为**企业级**事件：企业内部应用填 **CorpId**，三方应用填 SuiteKey |
| 官方 Java 类注释 | 企业自建应用-事件订阅用 appKey；企业自建应用-注册回调地址用 corpId |
| 「配置事件推送方式 · 常见问题」 | "owner_key需要传当前应用的appkey值" |
| Crypto README | "企业回调是corpId，三方应用回调是suiteKey" ⚠ 与前三处的"后台配置用 AppKey"不一致 |

按前三处执行：**后台配置的 HTTP 推送 → AppKey（三方 SuiteKey）；`register_call_back` 注册的 → CorpId。**
另外「HTTP回调概述」加密公式里写"key为应用的suiteKey"，是只按三方应用写的 ⚠。

---

## 6. 事件体：Stream 与 HTTP 字段不同

同一个审批实例事件（`bpms_instance_change`）两种通道的样子（文档原文示例）：

```jsonc
// Stream：外层元信息 + data
{"eventUnifiedAppId": "bbb381b6-...", "eventCorpId": "ding9f50b15bxxxx16741", "eventType": "bpms_instance_change",
 "eventId": "c7c7120f2c07419**ebdba0318c8", "eventBornTime": 1683533823336,
 "data": {"processInstanceId": "9Qgx5QqjR7axMwxxxx", "processCode": "Pro-xxx", "type": "finish", "result": "agree",
          "staffId": "manager75", "title": "自测-1016", "createTime": 1495592305000, "finishTime": 1495592272000}}

// HTTP（解密后）：扁平，元信息字段首字母大写
{"EventType": "bpms_instance_change", "EventTime": 1663143335567, "CorpId": "ding9f50b15bxxxx16741", "BizId": "1663**35567",
 "eventId": "c7c7120f2c07419**ebdba0318c8", "processInstanceId": "9Qgx5QqjR7axMwxxxx", "type": "finish", "result": "agree", ...}
```

**写一个同时支持两种通道的处理器时要先归一化**：Stream 取 `eventType` + `data`，HTTP 取 `EventType` + 顶层字段。
用 `eventId` 做幂等去重（两种通道都有）；⚠ 重复推送的条件与重试策略文档未说明。

---

## 7. 常用事件类型

**通用 / 平台**：`check_url`（验证回调地址）、`check_create_suite_url` / `check_update_suite_url`（三方应用）、`suite_ticket`（三方，约 5 小时一次）。

**通讯录**：HTTP 事件 `EventType` 示例 `user_add_org`，解密后 `{"EventType":"user_add_org","TimeStamp":...,"UserId":["user1","user2"],"CorpId":"..."}`
（`UserId` 是数组）。「通讯录事件」页（RDS / SyncHTTP 格式）列出的 syncAction：`user_add_org`、`user_modify_org`、`user_leave_org`、
`user_dept_change`、`user_role_change`、`user_active_org`、`org_dept_create`、`org_dept_modify`、`org_dept_remove`。
⚠ 这些名字在 Stream / HTTP 通道下是否全部作为 eventType 出现，本次抓取的页面未逐一说明。

**审批**（企业内部应用；Stream、HTTP 支持，SyncHTTP/RDS 不支持）：
- `bpms_instance_change`：实例开始 / 结束 / 终止 / 删除；`data.type` 示例值 `start`、`finish`，`result` 示例 `agree`。
- `bpms_task_change`：任务开始 / 结束 / 转交；多 `taskId`、`remark`。
- 订阅规则可以细到模板：`/v1.0/event/bpms_instance_change/processCode/{processCode}/type/{type}`，
  或加业务分类 `/bizCategoryId/{bizCategoryId}/...`（如 `attendance.goout` 外出、`hrm.hire` 入职）。
- ⚠ "终止""删除"对应的 `type` 取值文档示例未给出。
- 老版审批事件（biz_type=22 等 RDS 格式）文档标注 2023-05-15 起迁入历史文档，新接入用新事件。

---

## 8. 旧版：用 API 注册回调（register_call_back）

**Endpoint**: `POST https://oapi.dingtalk.com/call_back/register_call_back?access_token=...`
文档标注"后续将维持现有功能且不再新增能力"；企业内部应用推荐直接在开发者后台订阅。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| call_back_tag | String[] | 是 | 事件类型，如 `["user_add_org","user_modify_org","user_leave_org"]` |
| token | String | 是 | 加解密 token，"长度大于等于6个字符且少于64个字符" |
| aes_key | String | 是 | 固定 43 位，a-z A-Z 0-9 |
| url | String | 是 | 公网可访问的接收地址 |

注册时钉钉会先推 `check_url` 验证；`71006 回调地址已经存在`；一个应用只能注册一个 URL。
查询已注册：`GET oapi /call_back/get_call_back`（参数未转录）。这种方式订阅的是企业级事件，解密 ownerKey 用 **CorpId**（第 5 节）。

---

## 9. ⚠ 未说明 / 矛盾之处

- HTTP 回调 URL 参数名 `signature` / `msg_signature`、`timestamp` / `timeStamp` 各页不一致 ⚠ 文档自相矛盾（两种都读）。
- ownerKey：Crypto README 与另外三处说法不一致 ⚠ 文档自相矛盾。
- 签名 token 长度：后台配置"3~32 个字符"，register_call_back "≥6 且 <64" ⚠ 文档自相矛盾（取交集 6~32 最稳）。
- Python Stream SDK 订阅普通事件的写法、事件重推策略、审批 `type` 全部取值 ⚠ 文档未说明。
