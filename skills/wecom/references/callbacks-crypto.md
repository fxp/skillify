# 回调配置、消息加解密与接收消息 / 事件

来源：`developer.work.weixin.qq.com/document/path/90930`（回调配置）、`90968`（加解密方案说明）、`90238`（接收消息概述）、
`90239`（消息格式）、`90240`（事件格式）、`90241`（被动回复消息格式）、`92521`（回调 IP 段）。抓取于 2026-09-11。
**未用真实凭证验证**；行为描述均为「文档原文，未实测」。标「本地复算（2026-09-11）」的是用文档自带示例参数在本地重新计算的结果（不涉及网络请求），
标「无凭证探测（2026-09-11）」的是用伪造参数打接口的结果。

## 目录

1. 回调是什么、在哪配
2. 协议：GET 验证 URL 与 POST 推送
3. 签名与加解密算法（含 32 字节 PKCS#7 这个坑）
4. Python 实现（可直接用）
5. 官方加解密库
6. 解密后的消息与事件类型
7. 被动回复
8. 常见错误清单

## 1. 回调是什么、在哪配

企业微信把“用户发给应用的消息”和“各种事件”（通讯录变更、客户变更、审批状态、卡片点击……）以**加密 XML POST** 推到你配置的 URL。
配置三件套（90930）：

| 配置项 | 规则 |
|---|---|
| URL | 你的回调服务地址；企业微信会先发 GET 验证它。支持 http / https（建议 https） |
| Token | 英文或数字，**长度不超过 32 位**，参与签名 |
| EncodingAESKey | 英文或数字，**固定 43 位**，是 AESKey 的 Base64 编码（去掉了末尾的 `=`） |

在哪里配（各业务页原文）：

| 回调内容 | 配置位置 |
|---|---|
| 应用收到的消息、菜单 / 进入应用 / 卡片点击等事件 | 应用管理 → 自建应用 → 接收消息 → 设置 API 接收 |
| 通讯录变更（通讯录同步助手） | 管理工具 → 通讯录同步 → 设置接收事件服务器（URL 需是本企业主体域名） |
| 客户联系变更 | 已配置到客户联系“可调用接口的应用”的自建应用，在其“接收的消息事件类型”里勾选“外部联系人变更回调” |
| 审批状态变化 | 已配置到审批“可调用接口的应用”的自建应用，勾选“审批状态通知事件” |

回调里的 `ToUserName` 是企业 CorpID（第三方回调时是 suiteid），`AgentID` 是应用 id（仅应用相关回调带）。

## 2. 协议

### 2.1 GET：验证 URL 有效性（保存配置时触发）

```
GET https://your.host/wecom/callback?msg_signature=ASDFQWEXZCVAQFASDFASDFSS&timestamp=13500001234&nonce=123412323&echostr=ENCRYPT_STR
```

| 参数 | 说明 |
|---|---|
| msg_signature | 签名，由 token、timestamp、nonce、**echostr** 计算 |
| timestamp / nonce | 防重放 |
| echostr | 加密字符串，解密后得到 random、msg_len、msg、receiveid，**msg 即要返回的明文** |

你要做的（文档原文要点）：
1. 对参数做 **Urldecode**（「否则可能会验证不成功」）；
2. 用 token + timestamp + nonce + echostr 重算签名，与 msg_signature 比对；
3. 解密 echostr 得到 msg；
4. **1 秒内**响应，body 就是明文 msg——「不能加引号，不能带bom头，不能带换行符」。

常见失败：返回了 JSON / 带引号的字符串、`print` 带了换行、用框架默认的 `application/json` 序列化、1 秒内没返回（冷启动的 Serverless 函数容易超时）。
错误码 `40057`（文档原文）：不合法的 callbackurl 或 callbackurl 验证失败。

### 2.2 POST：接收业务数据

```
POST https://your.host/wecom/callback?msg_signature=...&timestamp=...&nonce=...

<xml>
   <ToUserName><![CDATA[toUser]]></ToUserName>
   <AgentID><![CDATA[toAgentID]]></AgentID>
   <Encrypt><![CDATA[msg_encrypt]]></Encrypt>
</xml>
```

处理步骤：校验 msg_signature（这次参与签名的是 **Encrypt 字段**）→ 解密 Encrypt 得明文 XML → （可选）构造被动回复 → 响应。

响应与重试（文档原文）：
- 「企业微信服务器在**五秒**内收不到响应会断掉连接，并且重新发起请求，**总共重试三次**」；
- 「http头部返回200表示接收ok，其他错误码企业微信后台会一律当做失败并发起重试」；
- 「假如企业无法保证在五秒内处理并回复，或者不想回复任何内容，可以直接返回200（即以空串为返回包）」；
- 排重：「有msgid的消息推荐使用msgid排重。事件类型消息推荐使用FromUserName + CreateTime排重」；
- 「目前无法保证100%回调成功，若开发者服务失败过多或者超时过多，企业微信可能会根据回调情况丢弃一些回调事件。建议开发者不要强依赖回调，需要额外机制对齐相关业务数据」；
- 不同业务回调要求的返回内容不同（空串、`success` 或加密的被动回复包），以各业务文档为准。本 skill 覆盖的应用消息 / 事件场景返回空串即可。

⚠ 文档未说明：90968 另给了一个 JSON 形式的回调包示例 `{"tousername": "...", "encrypt": "msg_encrypt", "agentid": "218"}`，
90238 目录里也有“设置接收消息的格式”一节标题，但抓到的正文没有说明如何切换 XML / JSON。默认按 XML 处理，同时兼容 JSON 更稳妥。

### 2.3 回调来源 IP

`GET /cgi-bin/getcallbackip?access_token=ACCESS_TOKEN` 返回企业微信回调使用的 IP 段（入方向白名单用），「建议企业每天定时拉取IP段」。
无凭证探测（2026-09-11）：假 token → `{"ip_list":[],"errcode":40014,...}`。详见 `access-token.md`。

## 3. 签名与加解密算法

**术语**（90968）

| 名称 | 定义 |
|---|---|
| EncodingAESKey | 43 字符，a-z / A-Z / 0-9 |
| AESKey | `Base64_Decode(EncodingAESKey + "=")`，**32 字节** |
| 算法 | AES-256-CBC；**IV = AESKey 前 16 字节** |
| 填充 | 「数据采用PKCS#7填充至**32字节**的倍数」 |
| msg_encrypt | 明文加密后的 Base64 |

**签名**

```
msg_signature = sha1( sort([token, timestamp, nonce, msg_encrypt]) 拼接 )   # 按字典序从小到大排序后直接拼接，结果小写 hex
```

注意：排序的是**四个参数值本身**（不是 key=value），不含分隔符；GET 验证时第四个值是 echostr，POST 时是 Encrypt。被动回复时用同样方法对**你生成的**密文签名。

**加密**：`rand_msg = random(16B) + msg_len(4B, 网络字节序/大端) + msg + receiveid` → PKCS#7(32) → AES-256-CBC → Base64。
**解密**：Base64 解码 → AES-256-CBC 解密 → 去填充 → 去掉前 16 字节随机串 → 读 4 字节 msg_len → 截 msg → 剩余为 receiveid，**校验 receiveid**。

receiveid 含义（附注原文）：企业应用回调 = **corpid**；第三方事件回调 = suiteid；个人主体第三方应用 = 空字符串。

**本地复算（2026-09-11）**：用 90968「举例说明」的参数（token=`QDG6eK`，EncodingAESKey=`jWmYm7qr5nMoAUwZRjGtBxmz3KA1tkAj3ykkR6q2B2C`，
timestamp=`1409659813`，nonce=`1372623149`，文档给出的 msg_encrypt）：
- 按上式算出的 sha1 为 `477715d11cdb4164915debcba66cb864d751f3e6`，与文档一致；
- 解密后**末字节（PKCS#7 填充长度）为 30**——大于 AES 块长 16，证明填充块确实是 32 字节。直接用 `cryptography` 的 `padding.PKCS7(128)` 或 PyCryptodome 的 `unpad(data, 16)` 会因为 30 > 16 **报 padding 错误**。去填充必须按 32 字节块处理（或手动取末字节截断）；
- 截出的明文是文档里的 `<xml>…<Content><![CDATA[hello]]></Content>…</xml>`，receiveid = `wx5823bf96d3bd56c7`，与文档一致。

## 4. Python 实现

依赖：`pip install cryptography flask`。以下类只依据 90968 的算法编写。
本地测试（2026-09-11，Python 3.9 + cryptography 43）：用文档示例签名与密文调 `decrypt_post` 得到文档明文；`encrypt_reply` → `decrypt_post` 往返一致；
错误签名、receiveid 不符均被拒绝；同一密文用 `padding.PKCS7(128)` 去填充报 `Invalid padding bytes`。
⚠ 加密 / 被动回复路径未与真实企业微信往返验证。

```python
import base64, hashlib, os, struct, time, secrets
import xml.etree.ElementTree as ET
from typing import Optional
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

class WeComCryptoError(Exception):
    pass

class WeComCrypto:
    BLOCK = 32                                   # PKCS#7 按 32 字节，不是 16

    def __init__(self, token: str, encoding_aes_key: str, receive_id: str):
        self.token = token
        self.key = base64.b64decode(encoding_aes_key + "=")
        if len(self.key) != 32:
            raise WeComCryptoError("EncodingAESKey 必须是 43 位")
        self.iv = self.key[:16]
        self.receive_id = receive_id             # 企业自建应用 = corpid

    def signature(self, timestamp: str, nonce: str, encrypt: str) -> str:
        return hashlib.sha1("".join(sorted([self.token, timestamp, nonce, encrypt])).encode()).hexdigest()

    def _check(self, msg_signature, timestamp, nonce, encrypt):
        if not secrets.compare_digest(self.signature(timestamp, nonce, encrypt), msg_signature):
            raise WeComCryptoError("签名校验失败")

    def decrypt(self, encrypt_b64: str) -> str:
        d = Cipher(algorithms.AES(self.key), modes.CBC(self.iv)).decryptor()
        raw = d.update(base64.b64decode(encrypt_b64)) + d.finalize()
        pad = raw[-1]
        if not 1 <= pad <= self.BLOCK:
            raise WeComCryptoError("填充非法")
        body = raw[16:-pad]                      # 去 16 字节随机串和填充
        n = struct.unpack(">I", body[:4])[0]     # 网络字节序
        msg, rid = body[4:4 + n], body[4 + n:]
        if rid.decode() != self.receive_id:
            raise WeComCryptoError(f"receiveid 不匹配: {rid!r}")
        return msg.decode("utf-8")

    def encrypt(self, msg: str) -> str:
        m = msg.encode("utf-8")
        raw = os.urandom(16) + struct.pack(">I", len(m)) + m + self.receive_id.encode()
        pad = self.BLOCK - len(raw) % self.BLOCK
        raw += bytes([pad]) * pad
        e = Cipher(algorithms.AES(self.key), modes.CBC(self.iv)).encryptor()
        return base64.b64encode(e.update(raw) + e.finalize()).decode()

    # —— 三个对外方法，与官方库的 VerifyURL / DecryptMsg / EncryptMsg 一一对应 ——
    def verify_url(self, msg_signature, timestamp, nonce, echostr) -> str:
        self._check(msg_signature, timestamp, nonce, echostr)
        return self.decrypt(echostr)

    def decrypt_post(self, msg_signature, timestamp, nonce, post_body: bytes) -> str:
        encrypt = ET.fromstring(post_body).findtext("Encrypt")
        self._check(msg_signature, timestamp, nonce, encrypt)
        return self.decrypt(encrypt)

    def encrypt_reply(self, reply_xml: str, nonce: Optional[str] = None, timestamp: Optional[str] = None) -> str:
        nonce = nonce or secrets.token_hex(8)
        timestamp = timestamp or str(int(time.time()))
        enc = self.encrypt(reply_xml)
        sig = self.signature(timestamp, nonce, enc)
        return (f"<xml><Encrypt><![CDATA[{enc}]]></Encrypt><MsgSignature><![CDATA[{sig}]]></MsgSignature>"
                f"<TimeStamp>{timestamp}</TimeStamp><Nonce><![CDATA[{nonce}]]></Nonce></xml>")

def parse_xml(xml: str) -> dict:
    return {c.tag: (c.text or "") for c in ET.fromstring(xml)}
```

Flask 回调服务：

```python
import os, threading
from flask import Flask, request, Response

crypto = WeComCrypto(os.environ["WECOM_CALLBACK_TOKEN"], os.environ["WECOM_ENCODING_AES_KEY"], os.environ["WECOM_CORP_ID"])
app = Flask(__name__)

@app.get("/wecom/callback")
def verify():
    a = request.args                                  # Flask 已做 URL decode
    try:
        plain = crypto.verify_url(a["msg_signature"], a["timestamp"], a["nonce"], a["echostr"])
    except WeComCryptoError:
        return Response("", status=403)
    return Response(plain, mimetype="text/plain")     # 原样明文：无引号、无换行

@app.post("/wecom/callback")
def receive():
    a = request.args
    xml = crypto.decrypt_post(a["msg_signature"], a["timestamp"], a["nonce"], request.get_data())
    ev = parse_xml(xml)
    threading.Thread(target=handle, args=(ev,), daemon=True).start()   # 业务异步，5 秒内先回 200
    return ""                                                            # 空串 = 接收成功、不被动回复

def handle(ev: dict):
    key = ev.get("MsgId") or f'{ev.get("FromUserName")}:{ev.get("CreateTime")}'   # 文档建议的排重键
    if seen(key):
        return
    ...
```

⚠ 文档未说明：echostr / Encrypt 是 Base64，可能含 `+`。文档只要求“做 Urldecode”，没说明企业微信是否对 `+` 做了百分号编码。
若签名总是校验失败，检查框架是否把 query 里的 `+` 解码成了空格（form 风格解码的常见行为）。

## 5. 官方加解密库

- 文档（90968）：「目前已有c++/python/php/java/golang/c#等语言版本。均提供了解密、加密、验证URL三个接口」，类名 `WXBizMsgCrypt`，
  构造参数 `(sToken, sEncodingAESKey, sReceiveId)`，方法 `VerifyURL` / `DecryptMsg` / `EncryptMsg`（C++ 签名见文档）。
- 下载入口：`https://developer.work.weixin.qq.com/devtool/introduce?id=36388`（「加解密库下载与返回码」）。
  ⚠ 无凭证探测（2026-09-11）时该页返回 302（疑似需登录），**各语言库的文件名、Python 版本兼容性、返回码表均未核实**。
  能下载到官方库时优先用官方库；拿不到时用上面的实现，但务必先用 90968 的示例参数自测。

## 6. 解密后的消息与事件类型

**普通消息**（成员在应用里发的，`MsgType` 取值，90239）：`text`、`image`、`voice`、`video`、`location`、`link`。
公共字段：`ToUserName`（CorpID）、`FromUserName`（成员 UserID）、`CreateTime`、`MsgType`、`MsgId`（64 位整型）、`AgentID`。
例：`<xml><ToUserName>…</ToUserName><FromUserName>…</FromUserName><CreateTime>1348831860</CreateTime><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[this is a test]]></Content><MsgId>1234567890123456</MsgId><AgentID>1</AgentID></xml>`

**事件**（`MsgType = event`，按 `Event` 分支）：

| Event | 场景 | 出处 |
|---|---|---|
| subscribe / unsubscribe（⚠ 本次只核对到 subscribe 字面值） | 成员关注 / 取消关注 | 90240 |
| enter_agent | 进入应用（EventKey 为空） | 90240 |
| LOCATION | 上报地理位置（**大写**） | 90240 |
| batch_job_result | 异步任务完成 | 90240 |
| change_contact | 通讯录变更，ChangeType：create_user / update_user / delete_user / create_party / update_party / delete_party / update_tag | 90240、90970、90971 |
| click / view / view_miniprogram | 菜单：拉取消息 / 跳转链接 / 跳转小程序 | 90240 |
| scancode_push / scancode_waitmsg | 扫码推事件 / 扫码推且弹“消息接收中” | 90240 |
| pic_sysphoto / pic_photo_or_album / pic_weixin / location_select | 拍照发图 / 拍照或相册 / 微信相册 / 地理位置选择器 | 90240 |
| template_card_event / template_card_menu_event | 模板卡片按钮点击 / 右上角菜单点击（带 `ResponseCode`，72 小时有效、一次） | 90240 |
| open_approval_change | **审批流程引擎**的审批状态变化 | 90240 |
| sys_approval_change | **审批应用**的审批状态变化 | 91815（见 `approval.md`） |
| share_agent_change / share_chain_change | 企业互联 / 上下游共享应用变更 | 90240 |
| inactive_alert / close_inactive_agent / reopen_inactive_agent | 长期未使用应用停用预警 / 临时停用 / 重新启用 | 90240 |
| low_active_alert / low_active / active_restored | 应用低活跃预警 / 低活跃 / 活跃恢复 | 90240 |
| change_external_contact / change_external_chat / change_external_tag | 客户、客户群、客户标签变更 | 92130（见 `customer-contact.md`） |

⚠ 取消关注事件的 Event 字面值本次未从正文核对（只核对到 subscribe），使用前请查 90240。

## 7. 被动回复

在 POST 的响应里直接回一条消息给该成员（仅限 5 秒内）。明文结构（加密前）：

```xml
<xml>
   <ToUserName><![CDATA[toUser]]></ToUserName>      <!-- 成员 UserID -->
   <FromUserName><![CDATA[fromUser]]></FromUserName> <!-- 企业 CorpID -->
   <CreateTime>1348831860</CreateTime>
   <MsgType><![CDATA[text]]></MsgType>
   <Content><![CDATA[this is a test]]></Content>     <!-- ≤2048 字节，超过截断 -->
</xml>
```

- 注意方向：**被动回复里 ToUserName 是成员、FromUserName 是 CorpID**，和收到的消息相反。
- 支持的回复类型：text、image（`<Image><MediaId>`）、voice、video、news（`ArticleCount` + `Articles/item{Title,Description,PicUrl,Url}`，Title ≤128 字节、Description ≤512 字节）、
  以及模板卡片更新：`update_button`（更新点击者的按钮文案）/ `update_template_card`（更新点击者的整张卡片）。
- 用 `crypto.encrypt_reply(明文xml)` 得到 `<xml><Encrypt/><MsgSignature/><TimeStamp/><Nonce/></xml>` 响应包；Nonce 由企业自行生成。
- **支持被动回复的事件类型**（90241 原文）：成员关注事件、进入应用、上报地理位置、点击菜单拉取消息、点击菜单跳转链接、点击菜单跳转小程序、
  扫码推事件且弹出“消息接收中”提示框、通用模板卡片右上角菜单事件。其他事件回空串，需要回复时改用主动发消息接口（`messaging.md`）。

## 8. 常见错误清单

1. 签名排序了 `key=value` 或拼了 `&`——应该只排序四个**值**直接拼接。
2. 忘了在 EncodingAESKey 后补 `=` 再 Base64 解码，或把 EncodingAESKey 直接当 AES key（文档原文：「使用AESKey做AES解密（**注意，不是EncodingAESKey**）」）。
3. IV 用了全 0 或随机值——IV 固定是 AESKey 前 16 字节。
4. 用 16 字节块的标准 PKCS7 unpad——会在填充长度 17~32 时报错（本地复算：文档示例的填充长度就是 30）。
5. msg_len 按小端或按字符数解析——是 4 字节**网络字节序**、**字节数**。
6. 不校验 receiveid——可能接受了其他企业 / 套件的包。
7. GET 验证返回 JSON 或带引号 / 换行；超过 1 秒。
8. POST 同步处理重业务逻辑导致超过 5 秒 → 被重试三次 → 重复处理。
9. 以为 API 写操作会触发回调——客户联系 API 操作「不会产生回调」；通讯录同步助手自己用 API 新增的成员也不回调给自己。
