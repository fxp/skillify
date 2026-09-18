# 事件与消息推送：服务器配置、接入校验、消息加解密

目录：[1. 服务器配置](#1-服务器配置) · [2. 接入校验（GET）](#2-接入校验get) · [3. 三种加解密模式](#3-三种加解密模式) · [4. 安全模式的签名与 AES 加解密](#4-安全模式的签名与-aes-加解密) · [5. 收到的消息与事件类型速查](#5-收到的消息与事件类型速查) · [6. 注意事项汇总](#6-注意事项汇总)

**除标「无凭证探测」的条目外，行为描述均为文档原文，未实测。**

被动回复本身（5 秒机制、回复 XML 结构）见 `messaging.md` 第 1 节；这里只讲"微信怎么把消息/事件送到你的服务器"这一段的配置、校验与加解密。

## 1. 服务器配置

在「微信开发者平台 - 我的业务 - 服务号 - 消息与事件推送」处配置：

| 配置项 | 说明 |
| --- | --- |
| URL 服务器地址 | 接收消息和事件的接口 URL，必须 `http://` 或 `https://` 开头，分别对应 80/443 端口 |
| Token 令牌 | 开发者任意填写的字符串，用于生成签名，会和 URL 里带的 `token` 参数配合校验来源 |
| EncodingAESKey | 手动填写或随机生成，43 位字符，用作消息体加解密密钥 |
| 消息加解密方式 | 明文模式 / 兼容模式 / 安全模式，见第 3 节 |
| 数据格式 | 消息体格式；**页面说明写"仅支持 XML"**，但见下方 ⚠，加解密说明页的示例同时给出了 JSON 回包格式 |

配置提交后**立即生效**，改错会导致收不到消息，务必谨慎。

## 2. 接入校验（GET）

提交服务器配置后，微信会向填写的 URL 发一个 **GET** 请求做一次性接入验证：

**请求参数**（Query String）
| 参数 | 说明 |
| --- | --- |
| signature | 微信加密签名，由 `token` + `timestamp` + `nonce` 计算得出 |
| timestamp | 时间戳 |
| nonce | 随机数 |
| echostr | 随机字符串，验证通过需原样返回 |

**签名算法**
1. 将 `token`、`timestamp`、`nonce` 三个字符串按字典序排序。
2. 拼接成一个字符串，做 SHA1。
3. 与 `signature` 对比，相等则来源合法。

验证通过后必须**原样返回 `echostr` 参数内容**（不是 JSON、不是其他包装），接入才算成功。

**示例（Python）**
```python
import hashlib

def check_signature(token, signature, timestamp, nonce):
    s = "".join(sorted([token, timestamp, nonce]))
    return hashlib.sha1(s.encode()).hexdigest() == signature
```

## 3. 三种加解密模式

| 模式 | 说明 |
| --- | --- |
| 明文模式（默认） | 不加解密，消息体明文收发，安全性低，不建议使用 |
| 兼容模式 | 消息同时含明文和密文，包体膨胀约 3 倍；回复明文或密文都行，方便调试期使用 |
| 安全模式（推荐） | 消息体只含密文，回复也必须是密文 |

选择兼容模式或安全模式前，必须先在开发者中心填写好 `EncodingAESKey`。

## 4. 安全模式的签名与 AES 加解密

启用加解密后，微信推送消息的 URL 会额外带两个参数：`encrypt_type`（如 `aes`）和 `msg_signature`。

### 4.1 收到消息时的验签

**参数**：URL 上的 `timestamp`/`nonce`/`msg_signature`，body 内的 `Encrypt` 字段。

**校验方法**（**注意：安全模式下不能再用第 2 节的 `signature` 校验，必须用 `msg_signature`**）：
1. 将 `token`、`timestamp`、`nonce`、`Encrypt`（body 里的密文字段）四个参数字典序排序。
2. 拼接后做 SHA1。
3. 与 `msg_signature` 对比。

### 4.2 解密 `Encrypt` 字段

1. `AESKey = Base64_Decode(EncodingAESKey + "=")`——EncodingAESKey 尾部补一个 `=`，Base64 解码得到 32 字节密钥。
2. 将 body 里的 `Encrypt` 做 Base64 解码，得到密文字节串。
3. 用 AESKey 以 **AES-CBC** 模式解密；**密钥长度 32 字节（256 位）**，**PKCS#7 填充块大小按 32 字节计算**（不是 AES 常见的 16 字节块）：设 `K=32`，`N` 为明文字节数，末尾补 `(K - N%K)` 个字节，每个字节内容都是 `(K - N%K)`。
4. 解密结果 `FullStr = random(16B) + msg_len(4B, 网络字节序) + msg + appid`：跳过开头 16 字节随机串，接下来 4 字节大端序读出 `msg` 长度，取出 `msg`（这才是真正的消息明文），末尾剩下的是 `appid`。
5. **校验 `appid` 与自己账号一致**，防止跨账号重放。

### 4.3 回包加密

无论对接入校验(check_url)还是业务消息，回包都要：
1. 明文内容按具体接口要求确定（无特殊要求时是字符串 `success`，此时**不需要加密**，直接回；其他内容需要加密）。
2. `Encrypt` 生成：构造 `FullStr = random(16B) + msg_len(4B) + msg(明文) + appid`，用同样的 AESKey + AES-CBC + PKCS7(块大小 32) 加密，Base64 编码得到 `Encrypt`。
3. `MsgSignature`：`token`、`TimeStamp`（用当前时间戳）、`Nonce`（回填收到时的 `nonce`）、`Encrypt` 四者字典序排序拼接后 SHA1。
4. 回包格式（JSON 或 XML，取决于配置的数据格式）：
```json
{"Encrypt": "...", "MsgSignature": "...", "TimeStamp": 1713424427, "Nonce": "415670741"}
```
```xml
<xml>
  <Encrypt><![CDATA[...]]></Encrypt>
  <MsgSignature><![CDATA[...]]></MsgSignature>
  <TimeStamp>1713424427</TimeStamp>
  <Nonce><![CDATA[...]]></Nonce>
</xml>
```

**注意事项**
- 官方提供 C++/PHP/Java/Python/C# 五种语言的示例代码（`cryptoDemo.zip`，需要资料包才能下载，本 skill 按 BRIEF 规则不下载安装任何压缩包，只记录该资源存在，见 `wechat-mp-workspace/verification-plan.md`），**强烈建议直接用官方示例代码，不要自己重新实现 PKCS7 去填充**，尤其块大小是 32 字节这个非标准细节容易写错。
- `⚠ 文档未说明`：本页给出了 `AESKey` 的推导方式，但**没有单独说明 CBC 模式的 IV（初始向量）怎么取**。通用的 WeChat/企业微信同源加解密方案里 IV 惯例上取 `AESKey` 的前 16 字节，但这是行业惯例、不是这页文档写的，接入前建议用官方示例代码或 debug 工具（下方）交叉验证，不要凭记忆假设。
- 官方提供在线调试工具："请求构造"（生成 `debug_demo` 事件的发包/回包调试信息）与"调试工具"（拿账号的 access_token + 配置好的服务器地址，实际推送一条 `debug_demo` 事件），二者都在 `developers.weixin.qq.com/apiExplorer?type=messagePush`，是排查加解密实现的官方手段。
- **⚠ 文档自相矛盾**：第 1 节服务器配置页写"数据格式：仅支持 XML"；本节回包格式明确给出了 JSON 和 XML 两种选项，且解密后的 `msg` 示例也是 JSON（`{"ToUserName":...}`）。未做真实推送验证具体哪个准确，接入时以账号后台"数据格式"配置项的实际可选值为准，不要假设只能用 XML。

## 5. 收到的消息与事件类型速查

**普通消息**（`MsgType` 为具体类型，非 `event`）：`text`（`Content`）、`image`（`PicUrl`/`MediaId`）、`voice`（`MediaId`，可能带 `Recognition` 语音识别结果）、`video`/`shortvideo`（`MediaId`/`ThumbMediaId`）、`location`（`Location_X`/`Location_Y`/`Scale`/`Label`）、`link`（`Title`/`Description`/`Url`）。所有类型都带 `MsgId`（64 位整型，用于去重）；来自图文文章的消息额外带 `MsgDataId`/`Idx`。

**事件消息**（`MsgType=event`）：关注/取消关注、扫码、菜单点击等，详见 `messaging.md` 第 2 节与 `menu.md` 第 5 节，不在本节重复。

## 6. 注意事项汇总

- 接入校验用 `signature`（三参数排序），安全模式下的消息验签用 `msg_signature`（四参数排序，多一个 `Encrypt`）——**两套签名字段不可混用**，安全模式下如果继续用 `signature` 校验会验签失败或校验了错误的内容。
- PKCS7 填充块大小是 **32 字节**，不是 AES-256 常见认知里的 16 字节 block size 误解（16 字节是 AES 的分组长度，32 字节是这里业务层选择的填充粒度）。
- 加解密涉及的随机串、长度字段、appid 校验都是为了防重放和防跨账号伪造，实现时不要为了"简化"而跳过 appid 校验这一步。
- 5 秒/3 次重试机制在明文、兼容、安全模式下都适用，加解密只影响包体内容，不改变时间窗口。
