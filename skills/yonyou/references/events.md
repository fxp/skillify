# 事件订阅：订阅、验签、解密、事件体

> 来源：open.yonyoucloud.com「开放平台接入文档 → 事件推送」（事件推送场景 / 事件推送订阅 / 事件订阅开发）、「SDK 使用说明」、
> 事件文档（`/iuap-ipaas-base/openPortal/event/…` 公开 JSON），以及官方 gitee `yycloudopen/isv-demo` 的
> `IsvEventCrypto.java`、`SHA256.java`、`PKCS7Encoder.java` 源码网页与两个 demo 的 README，抓取于 2026-09-11。
> **本文件所有内容未实测**：没有凭证就收不到推送。签名算法三处写法互相矛盾，见 §3。

## 目录

1. 在工作台开通订阅
2. 推送报文格式
3. 验签：三种写法与建议
4. 解密：AES-CBC
5. 应答、超时与重试
6. 事件体（按业务对象）
7. 事件编码速查
8. ISV：SUITE_TICKET
9. Python 接收端示例
10. 本文件的 ⚠ 汇总

---

## 1. 在工作台开通订阅

文档原文步骤（企业自建应用）：

1. 登录用友云工作台 →「数字化建模 → 系统管理 → 我的应用」，找到应用点【开放平台】→【事件订阅】。
   （用「API 调用」页新增的授权 key 也可以在 key 上做事件订阅。）
2. 回调方式二选一：**REST 接口**（填回调地址）或**函数脚本**（租户自行开发函数并关联）。
3. 回调地址须**公网可访问**。保存订阅信息时，开放平台会向该地址推送测试事件（事件编码 `CHECK_URL`）验证有效性；
   也可以用「测试」按钮推送测试事件，测试成功后再订阅具体业务事件。
4. 可配置：**预警邮箱**（推送失败通知）、**限流配置**（多少秒内推送多少次，0 表示不限）、**重试次数**。
5. 【新增订阅】→ 勾选要订阅的事件（可多选）。

事件的完整清单在「文档中心 → 事件文档」，按与 API 文档相同的分类树组织（`用友 YonBIP` 事件树抓取时共 347 个节点）。

---

## 2. 推送报文格式

开放平台以 JSON **POST** 到回调地址：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| signature | string | 签名 |
| timestamp | number | Unix 时间戳（毫秒，示例 `1530862251583`） |
| nonce | string | 随机串（示例为 16 位字母数字） |
| encrypt | string | 加密后的消息体（Base64） |

```json
{"signature": "…", "timestamp": 1530862251583, "nonce": "uM48M4qajlEtVCz4", "encrypt": "9Mo8oaTF…JA=="}
```

- 按 body 解析 JSON，不要依赖请求头：SDK 文档里构造测试回调的 curl 用的是 `--header 'Content-Type: Content-Type: text/html'`
  （原文如此）。⚠ 文档未说明真实推送的 Content-Type。
- `timestamp` 参与签名时按**字符串**处理（Go SDK 注释：「这里需要先把时间戳转为字符串」）。

---

## 3. 验签：三种写法与建议

⚠ 文档自相矛盾——同一件事出现三种算法：

| 出处 | 写法 |
| --- | --- |
| A. 文档「事件订阅开发 → 加密流程」第 3–5 步 | 把 timestamp、nonce、encrypt「按照 key 首字母倒叙组合」得到 signData → HmacSHA256 → Base64 |
| B. 同页「推送格式」+ corp-demo README | `signature = SHA256( sort (appSecret, timestamp, nonce, encrypt))`，README 补充「SHA256 计算后取 16 进制字符串，全小写」；isv-demo README 同一句写成「SHA1 计算后取 16 进制」；示例签名 `2ff5a94ca2dd9376c8dcebde690b1b8e94741ec5` 为 40 位十六进制（SHA1 的长度） |
| C. isv-demo 源码 `SHA256.sign(token, timestamp, nonce, encrypt)` | 把 `[timestamp, nonce, encrypt]` 三个**值**按字典序排序后直接拼接，以 `token`（即 appSecret）为 key 做 **HmacSHA256**，输出 **Base64** |

SDK 文档里的真实风格示例签名（如 `j9k76js+sDzPF/BAOpsL4n7PlVtns6HrAU2hvR32KFI=`、`EtVCdBOyTZWCwV1FZiGsE4IyAEVfGAO3WmswUmkavxc=`）
都是 44 字符 Base64（32 字节），与 C 的输出形态一致，与 B 的 hex 形态不一致。

**建议**：

1. 能用官方 SDK 就用 SDK 解密验签（Java `EventParamDecrypt.selfAppParamDecrypt(holder, appKey, appSecret)`；
   Go `eventSdk.DecryptEventEncrypt(appSecret, holder)`；Python `decrypt_event_encrypt(app_secret, holder)`）。
2. 自己实现时按 C 实现，并在订阅时用 `CHECK_URL` 测试事件核对；对不上时把 A、B 的结果也算出来记日志，确认后固化。
3. 用常量时间比较（`hmac.compare_digest`）。

---

## 4. 解密：AES-CBC

以下据 isv-demo 源码（ISV 场景）；企业自建应用的对应关系由 Java SDK 方法签名 `selfAppParamDecrypt(holder, appKey, appSecret)`
推断（appKey 取代 suiteKey）。⚠ 自建应用没有独立的公开源码可核对。

1. **AES key**：文档原文「加密种子为 aesKey」「加密加签用到的 appSecret、AES key 同授权数据」。demo `buildAesKeyFromSecret(appSecret)`：
   去掉 `-`；长于 43 位截取前 43 位，短于 43 位右补字符 `0` 到 43 位；再 `Base64Decode(key43 + "=")` 得 32 字节 → **AES-256**。
2. **IV** = key 的前 16 字节。模式 `AES/CBC/NoPadding`，自行做 PKCS#7 去填充，**块大小 32**（`PKCS7Encoder.BLOCK_SIZE = 32`，不是 16）。
3. `encrypt` 先 Base64 解码再解密。
4. 明文字节布局：`16 字节随机串` + `4 字节网络字节序（大端）消息长度 N` + `N 字节消息 JSON` + `appKey（或 suiteKey）`。
5. 校验尾部的 appKey / suiteKey 与自己的一致，否则拒绝。

文档原文的 Java 注意事项：JDK 8 以下需替换 JCE 无限制策略文件（`local_policy.jar`、`US_export_policy.jar`），否则 256 位 AES 报 `Illegal key size`；
不同语言 Base64 / byte 边界（C# 0–255 vs Java −128–127）要注意转换。

---

## 5. 应答、超时与重试

- 文档原文：「推荐异步处理，**推送超时 5 秒**」。收到后先落库 / 入队，立即应答，再慢慢处理。
- 文档原文：「确认收到事件后，需返回**加密加签后的"success"**，通知事件处理成功。否则开放平台会尝试重试推送，对于超过 **24 小时**的推送失败的事件，开放平台将不再推送。」
- ⚠ 文档自相矛盾：Python SDK 示例的回调服务直接在 HTTP body 里返回明文 `success`；demo 的 `encryptMsg("success")` 会生成
  `{signature,timestamp,nonce,encrypt}` 格式的加密应答。先按文档返回加密 JSON；若 CHECK_URL 测试不通过再试明文，并记录结论。
- 重试意味着**同一事件可能收到多次**：用 `eventId` 去重（幂等处理）。
- 订阅侧还能配「重试次数」「限流」，推送失败发预警邮件（§1）。

---

## 6. 事件体（按业务对象）

**外层**（接入文档「事件格式」原文）：解密后是 JSON，含 `type`（事件类型）、`eventId`（uuid）、`timestamp`、`tenantId`，
部分通讯录类事件带 `staffId[]` / `deptId[]` / `userId[]`；「非必填项若为空 json 中会无此字段，而非 null」。

⚠ 文档未说明：业务事件（订单、凭证、档案）的业务数据放在外层的哪个字段里。事件文档每个事件只给了「事件字段描述」和「事件内容示例」，
示例本身的外壳也各不相同（下表）。**接收端请先把解密后的完整 JSON 原样记日志**，再按实际结构取字段。

| 事件 | 事件内容示例的外层（文档原文） | 关键字段 |
| --- | --- | --- |
| `st_purchaseorder_audit` 采购订单审核 | 整张单据对象 | `id`、`code`、`org`、`bustype`、`status`（0 开立 / 1 已审核 / 2 关闭 / 3 审核中）、`purchaseOrders[]`（`product`、`qty`、`priceQty`、`taxRate`…） |
| `SALE_AUDITORDER_NOTIFY_SENT` 销售订单审核 | `{"BILL_INFO": {…}}`（字段表却是顶层 `billId`） | `billId`、`billCode`、`billNo`（值为 `voucher_order`） |
| `GL_VOUCHER_EVENT_ADD_AFTER` 凭证新增 | `{"voucherVO": [ … ]}` | `accbook`、`periodunion`、`id`、`billcode`、`bussid` |
| `YXYBASEDOC_AA_MERCHANT_INSERT` 客户新增 | 扁平客户对象 | `id`、`code`、`name{zh_CN}`、`createOrg`、`transType`、`merchantAppliedDetail{…}` |
| `BASEDOC_VENDOR_ADD_AFTER` 供应商新增 | `{"userObject": {"archives": [ … ]}}` | `id`、`code`、`name{zh_CN,en_US,zh_TW}` |
| `YXYBASEDOC_PC_PRODUCT_INSERT` 物料新增 | `{"archive": {"id", "orgId"}}`（字段表却列了 30 多个顶层字段） | `id`、`orgId`、`code`、`manageClass`、`unit`… |
| `DEPT_ADD` 部门新增 | `{"model": {…}}` | `id`、`code`、`name`、`parentid`、`parentorgid`、`enable`、`dr`、`ts` |

**推荐做法**：把事件当「某 ID 变了」的信号，拿到 ID 后调对应详情接口取最新完整数据（订单 `…/detail?id=`、凭证 `queryVoucherById`、
档案 `…/detail` / 批量详情）；再配合各列表接口的 `pubts` 做定时增量兜底，防止漏推。

---

## 7. 事件编码速查

| 业务对象 | 事件编码 |
| --- | --- |
| 回调地址校验 | `CHECK_URL` |
| 业务单元 | `BASE_ORG_EVENT_ADD_AFTER`、`BASE_ORG_EVENT_UPDATE_AFTER`、`BASE_ORG_EVENT_DELETE_AFTER`、`BASE_ORG_EVENT_ENABLE_AFTER`、`BASE_ORG_EVENT_DISABLE_AFTER` |
| 部门 | `DEPT_ADD`、`DEPT_UPDATE`、`DEPT_DELETE`、`DEPT_ENABLE`、`DEPT_DISABLE` |
| 用户（企业信息） | `USER_ADD`、`USER_UPDATE`、`TENANTUSER_diwork`、`TENANT_UPDATE_TENANT_USER_NAME` |
| 客户 | `YXYBASEDOC_AA_MERCHANT_INSERT`、`YXYBASEDOC_AA_MERCHANT_UPDATE`、`YXYBASEDOC_AA_MERCHANT_DELETE`、`YXYBASEDOC_AA_MERCHANT_CARD_DELETE`、`YXYBASEDOC_AA_MERCHANTLIST_STOP`、`YXYBASEDOC_AA_MERCHANTLIST_UNSTOP`、`YXYBASEDOC_AA_MERCHANT_BATCH_STOP`、`YXYBASEDOC_AA_MERCHANT_BATCH_UNSTOP`、`YXYBASEDOC_AA_MERCHANT_ALLOCATEORG` |
| 供应商 | `BASEDOC_VENDOR_ADD_AFTER`、`BASEDOC_VENDOR_UPDATE_AFTER`、`BASEDOC_VENDOR_DELETE_AFTER`、`BASEDOC_VENDOR_ENABLE_AFTER`、`BASEDOC_VENDOR_DISABLE_AFTER` |
| 物料 | `YXYBASEDOC_PC_PRODUCT_INSERT`、`YXYBASEDOC_PC_PRODUCT_UPDATE`、`YXYBASEDOC_PC_PRODUCT_DELETE`、`YXYBASEDOC_PC_PRODUCT_STOP`、`YXYBASEDOC_PC_PRODUCT_UNSTOP`、`YXYBASEDOC_PC_PRODUCT_BATCHMODIFY`、`iuap-apdoc-material_PC_PRODUCT_ADDPROSUITORG_NOTIFY`、`iuap-apdoc-material_PC_PRODUCT_CANCELSUITORG_NOTIFY` |
| 采购订单 | `st_purchaseorder_save`、`st_purchaseorder_audit`、`st_purchaseorder_unaudit`、`st_purchaseorder_close`、`st_purchaseorder_open`、`st_purchaseorder_delete`、`st_purchaseorder_purchaseordermodifyaudit` |
| 销售订单 | `SALE_SAVEORDER_NOTIFY_SENT`、`SALE_SUBMITORDER_NOTIFY_SENT`、`SALE_UNSUBMITORDER_NOTIFY_SENT`、`SALE_AUDITORDER_NOTIFY_SENT`、`SALE_UNAUDITORDER_NOTIFY_SENT`、`SALE_OPPOSEORDER_NOTIFY_SENT`、`SALE_CLOSEORDER_NOTIFY_SENT`、`SALE_OPENORDER_NOTIFY_SENT`、`SALE_DELETEORDER_NOTIFY_SENT`、`SALE_AUDITORDER` |
| 总账凭证 | `GL_VOUCHER_EVENT_ADD_AFTER`、`…_UPDATE_AFTER`、`…_DELETE_AFTER`、`…_AUDIT_AFTER`、`…_UNAUDIT_AFTER`、`…_TALLY_AFTER`、`GL_VOUCHER_EVENT_UNTALLY_AFLTER`、`GL_VOUCHER_EVENT_EXTERNAL_INTEGRATION` |

事件编码大小写、前缀风格各业务线不统一（`st_…` 小写、`SALE_…` 大写、`iuap-apdoc-…` 带连字符），**逐字照抄**，不要自己规整。
销售订单同时存在 `SALE_AUDITORDER` 和 `SALE_AUDITORDER_NOTIFY_SENT` 两个审核事件，⚠ 文档未说明区别。

---

## 8. ISV：SUITE_TICKET

ISV 套件会在回调 URL 收到 `type: "SUITE_TICKET"` 的推送（格式、加密同上），明文含 `suiteKey`、`suiteTicket`；
isv-demo README：「ISV 需要将其中的 suiteTicket 进行保存，在后续获得调用接口令牌时需要使用」。新生态应用是否仍需要见 `auth-and-gateway.md` §4。

---

## 9. Python 接收端示例

```python
# pip install flask pycryptodome
import base64, hashlib, hmac, json, os, struct
from Crypto.Cipher import AES
from flask import Flask, request

APP_KEY, APP_SECRET = os.environ["YONBIP_APP_KEY"], os.environ["YONBIP_APP_SECRET"]
app = Flask(__name__)

def aes_key(secret: str) -> bytes:
    k = secret.replace("-", "")
    k = k[:43] if len(k) >= 43 else k.ljust(43, "0")
    return base64.b64decode(k + "=")

def sign(secret: str, timestamp, nonce: str, encrypt: str) -> str:          # 按 §3 写法 C
    plain = "".join(sorted([str(timestamp), nonce, encrypt]))
    return base64.b64encode(hmac.new(secret.encode(), plain.encode(), hashlib.sha256).digest()).decode()

def decrypt(secret: str, expect_key: str, encrypt: str) -> dict:
    key = aes_key(secret)
    raw = AES.new(key, AES.MODE_CBC, key[:16]).decrypt(base64.b64decode(encrypt))
    pad = raw[-1]
    if 1 <= pad <= 32:                                                        # PKCS#7，块大小 32
        raw = raw[:-pad]
    n = struct.unpack(">I", raw[16:20])[0]
    msg, tail = raw[20:20 + n].decode("utf-8"), raw[20 + n:].decode("utf-8")
    if tail != expect_key:
        raise ValueError("appKey 不匹配")
    return json.loads(msg)

def encrypt_reply(secret: str, app_key: str, text: str = "success") -> dict:
    import secrets, time
    key, rnd = aes_key(secret), secrets.token_urlsafe(12)[:16].encode()
    body = rnd + struct.pack(">I", len(text.encode())) + text.encode() + app_key.encode()
    pad = 32 - len(body) % 32
    enc = base64.b64encode(AES.new(key, AES.MODE_CBC, key[:16]).encrypt(body + bytes([pad]) * pad)).decode()
    ts, nonce = int(time.time() * 1000), secrets.token_hex(8)
    return {"signature": sign(secret, ts, nonce, enc), "timestamp": ts, "nonce": nonce, "encrypt": enc}

@app.post("/yonbip/callback")
def callback():
    h = json.loads(request.get_data(as_text=True))
    if not hmac.compare_digest(sign(APP_SECRET, h["timestamp"], h["nonce"], h["encrypt"]), h["signature"]):
        app.logger.warning("验签失败，原始报文: %s", h)                       # §3：三种写法矛盾，先记日志核对
        return "invalid signature", 400
    event = decrypt(APP_SECRET, APP_KEY, h["encrypt"])
    app.logger.info("事件原文: %s", event)                                     # §6：业务数据位置未说明，先原样记录
    if event.get("type") != "CHECK_URL":
        enqueue(event)                                                         # 异步处理，按 eventId 去重
    return encrypt_reply(APP_SECRET, APP_KEY)                                   # §5：加密的 "success"；不通过再试明文
```

（`enqueue` 为你自己的队列写入函数。）

---

## 10. 本文件的 ⚠ 汇总

- ⚠ 文档自相矛盾：验签算法 A / B / C 三种写法，B 内部又有 SHA256 与 SHA1 两种描述——§3
- ⚠ 文档自相矛盾：应答加密的 "success" vs SDK 示例明文 `success`——§5
- ⚠ 文档自相矛盾：销售订单、物料、凭证事件的示例外壳与字段表不一致——§6
- ⚠ 文档未说明：业务事件数据在外层 JSON 的位置；真实推送的 Content-Type；自建应用解密的独立源码——§2 §4 §6
- ⚠ 文档未说明：`SALE_AUDITORDER` 与 `SALE_AUDITORDER_NOTIFY_SENT` 的区别——§7
