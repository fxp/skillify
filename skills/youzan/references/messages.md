# 消息推送：订阅、接收、验签、去重与重推

内容整理自 https://doc.youzanyun.com/ （抓取于 2026-09-11）。**未用真实凭证验证**；消息推送是有赞 → 开发者方向，无凭证无法触发，
本文件没有任何探测结论，全部是「文档原文，未实测」。

## 目录
1. 前置条件与订阅配置
2. 无容器应用：HTTP 推送的请求长什么样
3. 验签：Event-Sign 怎么算
4. 解析消息体：msg 的两种形态
5. 返回、超时、重推、熔断
6. 顺序、去重、延迟：写消费端的规则
7. 可直接用的 Flask 接收端
8. 常用消息类型速查
9. 有容器应用：MessageHandler
10. 排查清单
11. ⚠ 本文件的文档矛盾 / 未说明

---

## 1. 前置条件与订阅配置

有赞只把消息推给同时满足三个条件的应用：
1. 应用开启了消息推送服务；
2. 消息里的店铺与应用有**生效中**的授权关系；
3. 应用订阅了这类消息，且**订阅时间早于事件发生时间**（先发生、后订阅的事件不会补推）。

配置路径：控制台 → 应用 → 类目能力 → 消息订阅：开启服务、配置推送网址、勾选消息事件。只能订阅已获得能力包里的消息（找不到消息 → 先去“类目管理”申请能力包）。

推送网址要求：
- 公网可访问；**域名里不能有下划线**（`dev_admin.xxx.com` 非法，路径里可以有）（FAQ 3939）。
- 修改地址后最迟 3 分钟生效（7634）。
- 能配几个地址：7634（新版）与 FAQ 3943 说**两个**（正式店铺推送网址必填 + 云测试店铺推送网址选填，不填则全部推到正式地址）；
  ZnS3 / 41536 / FAQ 51411 / FAQ 3938 说**只能一个** → ⚠ 文档自相矛盾。无论哪种，**都要按消息里的 `kdt_id` 区分店铺 / 环境**（FAQ 3940）。
- 订阅范围（7634 新增）：“所有授权店铺默认推送”或“打标店铺才推送”；后者用 API 管理订阅关系：
  创建 `detail/API/0/5049`、查询 `5080`、删除 `5050`（店铺范围冲突返回 `PUSH_ADMIN_500008`）。

## 2. 无容器应用：HTTP 推送的请求

- 方法与编码：**POST，`application/json`（输入流）**（7634 原文）。
- 请求头：

| Header | 含义 |
|---|---|
| `Event-Sign` | 防伪签名：`MD5(client_id + entity + client_secret)`，entity 是**原始 RequestBody** |
| `Event-Type` | 消息业务标识，如 `trade_TradeSuccess`、`trade_refund_SysRefund` |
| `Client-Id` | 你的 client_id |

- 请求体（以交易消息为例，字段来自各消息页）：

```json
{
  "client_id": "...", "kdt_id": 56232, "kdt_name": "有赞的店", "root_kdt_id": 74234,
  "id": "E20200525201253074004153", "type": "trade_TradeClose", "status": "TRADE_CLOSED",
  "msg": "%7B%22tid%22%3A%22E2021...%22%2C...%7D",
  "msg_id": "6dc15f0b-8682-4812-b635-ab66e199f330",
  "version": 1621946649, "sendCount": 1, "sign": "...", "test": false, "mode": 1
}
```
`id` 一般是订单号（交易）/ 商品 id（商品）/ 用户 id（客户）。`sendCount` 只在重推时出现，第几次重推就是几（FAQ 3941）。

## 3. 验签：Event-Sign

```python
import hashlib, hmac
def verify(raw_body: bytes, event_sign: str, client_id: str, client_secret: str) -> bool:
    expected = hashlib.md5(client_id.encode("utf-8") + raw_body + client_secret.encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected, (event_sign or "").lower())
```
- 是**普通 MD5 拼接**，不是 HMAC-SHA256，也没有时间戳 / nonce。
- 必须用**收到的原始字节**，不能 `json.loads` 再 `json.dumps`（空格、字段顺序、转义都会变）。Flask 用 `request.get_data()`；Spring 用 `@RequestBody String`（不能用 `request.getParameter`，FAQ 33555）。
- 编码用 UTF-8：官方 FAQ 34663 提醒 Java `getBytes()` 不指定 UTF-8 时，在默认 GBK 的服务器上会校验失败。
- 文档示例的 Java 代码用的是 `com.youzan.platform.util.security.MD5`，官方说**没有提供这个包**，自己实现 MD5 即可。
- 消息体里的 `sign` 字段：交易消息写 `MD5(client_id+msg+client_secrect)`，客户消息写 `Md5(clientId + ToJSONString(msg) + clientSecret)`，积分消息只写“MD5或者其他方式”——文档自己也说**不建议用 body 里的 sign，用请求头 Event-Sign** → ⚠ 文档未说明 body.sign 的精确算法。
- 验签失败时文档示例返回 `{"code":0,"msg":"failed"}`（不含 success → 有赞视为失败并重推）。

## 4. 解析消息体：msg 的两种形态

| 形态 | 出现在 | 处理 |
|---|---|---|
| **UrlEncode(UTF-8) 后的 JSON 字符串** | `trade_*`（交易创建 / 支付 / 待发货 / 发货 / 关闭 / 成功…）、`POINTS`、`SCRM_CUSTOMER_EVENT` 等，字段说明写“经过UrlEncode(UTF-8)编码,需要解码” | `json.loads(urllib.parse.unquote(msg))` |
| **JSON 对象** | `youzan_trade_RefundCreated`、`youzan_trade_RefundSuccess` 等新版退款消息，字段类型写 `Object` | 直接当 dict |

```python
import json, urllib.parse
def decode_msg(body: dict) -> dict:
    m = body.get("msg")
    if isinstance(m, str):
        return json.loads(urllib.parse.unquote(m))
    return m or {}
```
- 收到 msg “乱码”就是没做 urldecode（FAQ 3926）。
- 用 `unquote` 而不是 `unquote_plus`：⚠ 文档未说明空格编码成 `%20` 还是 `+`，建议先用 `unquote`，若解析失败再试 `unquote_plus` 并记录样本。
- 很多消息只带关键字段（如 `trade_TradeClose` 只有 tid / close_type / close_reason / update_time），需要详情时再调 API。

## 5. 返回、超时、重推、熔断

- 成功标识：HTTP 正常返回且**响应体包含 `success`**；建议返回 `{"code":0,"msg":"success"}`。
- 超时 **5 秒**（无容器 HTTP 推送）；超时也算失败。所以要**先返回、后异步处理**。
- 自动重推（无容器，7634 / DX7Q 原文）：最多 **16 次**，间隔 10s、30s、1min、2min、3min … 10min、20min、30min、1h、2h；期间手动重推会中止自动重推；耗尽后进死信队列。
  但各消息字段表里 `sendCount` 的说明写“**最多重推 4 次**，每次间隔 5s、5m20s、21m20s、2h”（trade_TradeClose、POINTS、SCRM_CUSTOMER_EVENT）→ ⚠ 文档自相矛盾。消费端按“会重推、次数不定”设计即可。
- 熔断：应用 10 秒内推送失败率 > 80% 自动熔断；之后每 5 秒放 1 条做心跳，成功即恢复。一个坏掉的接收端会让**所有**消息延迟。
- 手动重推：控制台“类目能力 → 消息记录”，只保留 **7 天**，只能重推 7 天内的失败消息，“全部重推”峰值约 100 条/秒、从最近的开始。超过 7 天只能用业务 API 主动拉。
- 应用订购到期期间的消息**不会发送，续费后也不补推**（FAQ 5180）→ 定期对账。
- 推送侧限流：DX7Q 说可以发邮件到 isv@youzan.com 申请按应用或店铺配置推送限流；FAQ 45224 说“消息推送没有限流” → ⚠ 文档自相矛盾（二者可能指不同层面，未说明）。

## 6. 顺序、去重、延迟

- **乱序**：消息无序到达，每条带 `version`，“高版本覆盖低版本”。消费端按 `(type, id)` 记录已处理的最大 version，低于它的直接丢弃。
- **去重**：会重推（`sendCount`），也会有高频重复（商品库存变更文档明确建议去重防抖）。用 `msg_id` 做幂等键；没有 `msg_id` 的消息（如 `youzan_item_SkuStockChanged`）用 `(type, kdt_id, id/sku_id, version)`。
- **连锁**：总部和分店可能各推一条相同事件（商品消息页）；带 `root_kdt_id` / `head_kdt_id` 的消息按需要过滤。
- **查详情要延迟**：订单批量接口和详情接口“有一定延时”，文档建议**收到交易消息后间隔 30 秒以上**再调 `youzan.trade.get` / `youzan.trades.sold.get`；返回空可以重试（4978、trade.get 描述）。
- **状态不是一一对应**：`trade_TradePaid` 只表示付过款，之后可能是待成团、待接单、定金待尾款；OMS / ERP 接待发货订单应监听 **`trade_TradeBuyerPay`**（主订单进入“等待商家发货”）。**虚拟商品、电子卡券、知识付费订单不会触发 `trade_TradeBuyerPay`**（它们没有待发货状态）。
- 同一店铺授权给多个 ERP 时，每个应用都会收到全部订单消息，需自行按商品编码等规则过滤（FAQ 42289）。

## 7. Flask 接收端（验签 + 快速 ACK + 异步 + 幂等 + 顺序）

```python
import json, os, hashlib, hmac, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify

app = Flask(__name__)
CLIENT_ID = os.environ["YOUZAN_CLIENT_ID"]
CLIENT_SECRET = os.environ["YOUZAN_CLIENT_SECRET"]
pool = ThreadPoolExecutor(max_workers=8)      # 生产环境换成消息队列

def verify(raw: bytes, sign: str) -> bool:
    exp = hashlib.md5(CLIENT_ID.encode() + raw + CLIENT_SECRET.encode()).hexdigest()
    return hmac.compare_digest(exp, (sign or "").lower())

@app.post("/youzan/push")
def push():
    raw = request.get_data()                       # 原始字节，别先 parse
    if not verify(raw, request.headers.get("Event-Sign")):
        return jsonify(code=0, msg="failed")       # 不含 success → 有赞会重推
    body = json.loads(raw)
    if body.get("client_id") and str(body["client_id"]) != CLIENT_ID:
        return jsonify(code=0, msg="failed")
    pool.submit(handle, request.headers.get("Event-Type"), body)
    return jsonify(code=0, msg="success")          # 5 秒内返回

def handle(event_type: str, body: dict):
    dedup_key = body.get("msg_id") or f"{event_type}:{body.get('kdt_id')}:{body.get('id')}:{body.get('version')}"
    if seen_before(dedup_key):                     # Redis SETNX + TTL（>7 天）
        return
    if not newer_than_stored(event_type, body.get("kdt_id"), body.get("id"), body.get("version")):
        return                                      # 旧版本，丢弃
    m = body.get("msg")
    msg = json.loads(urllib.parse.unquote(m)) if isinstance(m, str) else (m or {})
    if event_type == "trade_TradeBuyerPay":
        enqueue_order_sync(body["kdt_id"], msg["full_order_info"]["order_info"]["tid"], delay_seconds=30)
    elif event_type == "trade_TradeClose":
        mark_closed(body["kdt_id"], msg["tid"], msg.get("close_type"))
    elif event_type in ("youzan_trade_RefundCreated", "youzan_trade_RefundSuccess"):
        sync_refund(body["kdt_id"], msg["tid"], msg["refund_id"], msg["version"])
```

## 8. 常用消息类型速查（`Event-Type` / body.type）

**交易正向**

| 消息 | 触发 | msg 关键字段 |
|---|---|---|
| `trade_TradeCreate` | 订单创建 | 完整订单结构 |
| `trade_TradePaid` | 支付成功（不等于待发货） | 完整订单结构 |
| `trade_TradeBuyerPay` | 进入“等待商家发货”（含周期购待发货、拼团成功）；虚拟 / 卡券不触发 | `full_order_info`、`order_promotion`、`delivery_order` |
| `trade_TradePartlySellerShip` | 部分发货 | `tid`、`oids`、`express_id` |
| `trade_TradeSellerShip` | 全部发货，status=`WAIT_BUYER_CONFIRM_GOODS` | `tid`、`update_time` |
| `trade_TradeSuccess` | 确认收货 / 自动确认 → 交易成功 | — |
| `trade_TradeClose` | 买家 / 卖家取消、超时未付、全额退款 | `tid`、`close_type`、`close_reason` |
| `trade_TradeMemoModified` | 卖家改备注 | — |
| `trade_MessagesTheChangeAddresses` / `youzan_trade_MessagesTheChangeAddressesByBuyer` | 卖家 / 买家改收货地址 | `tid`、`address` |

**交易逆向（两套并存）**

| 旧版（`trade_refund_*`） | 新版（`youzan_trade_Refund*`，msg 为对象、“不计费”） |
|---|---|
| `trade_refund_BuyerCreated` 买家发起退款 | `youzan_trade_RefundCreated`（买家发起 / 再次发起 / 卖家主动 / 系统退款） |
| `trade_refund_RefundSellerAgree` 卖家同意退款（终态） | `youzan_trade_RefundSellerAgree` |
| `trade_refund_RefundSuccess` 退货退款成功（终态） | `youzan_trade_RefundSuccess`（仅退款同意 / 退货退款确认收货并退款 / 主动退款 / 系统退款） |
| `trade_refund_RefundClosed` 买家取消 | `youzan_trade_RefundClosed` |
| `trade_refund_SysRefund` 一键 / 系统退款 | （并入 RefundCreated / RefundSuccess） |

新版退款消息的 `refunded_fee` 是**字符串、单位元**；`refund_type` 取 `REFUND_ONLY` / `REFUND_AND_RETURN` / `EXCHANGE_GOODS_FLOW`；
支持店铺类型比旧版少（文档列微商城单店、连锁 D、教育多校区总部）→ 零售 / 连锁 L 店铺先确认能收到哪套。

**商品 / 客户 / 积分**

| 消息 | 触发 | 说明 |
|---|---|---|
| `ITEM_INFO` / `ITEM_STATE` / `ITEM_SKU_INFO` | 商品新增编辑 / 上下架售罄删除 / 规格变更 | ITEM_STATE 的 msg 是 `{"data": {...最新值}, "change_fields": [...]}` |
| `youzan_item_SkuStockChanged` | 规格库存变更 | **不含库存数值**，要再调查询接口 |
| `SCRM_CUSTOMER_EVENT` | 客户创建 / 更新 / 注销 | status=`CUSTOMER_CREATED` / `CUSTOMER_UPDATED`；msg 含 mobile、is_member、`is_log_off` |
| `POINTS` | 积分变更 | `amount`、`total`、`biz_value`、`client_hash`（= md5(client_id)，用来识别“是不是我自己调接口产生的”变动，防回环）；有容器积分扩展点产生的变动不推送 |

## 9. 有容器应用：MessageHandler

- 有容器应用不配推送网址，用“消息扩展点”：Java 实现 `MessageHandler` 并用 `@Topic("trade_TradeSuccess")` 绑定；PHP 在 `config/meps.php` 注册；Node.js 放 `app/Mep`，每个文件一个 topic。
- 正常处理不用返回值；想让有赞重推就**抛异常**。
- 超时 **1 秒**，超时或抛异常进入重推：DX7Q 说最多 16 次后进死信；FAQ 34757 说“没有次数限制，一直重复调用” → ⚠ 文档自相矛盾。所以扩展点里的处理必须幂等、不能有永久性异常。
- 调试：有容器在测试环境用“消息推送调试工具”；无容器在正式环境调试（XPWx 页）。

## 10. 排查清单（FAQ 3939、33464）

1. 控制台订阅开关是否开启、推送网址是否公网可达、域名是否含下划线。
2. 店铺与应用授权是否生效（自用型在店铺后台“设置 → 有赞服务 → 定制服务”确认；连锁要单独授权）。
3. 消息是否已订阅、订阅时间是否早于事件。
4. 业务场景是否真的触发（例：虚拟商品不会有 `trade_TradeBuyerPay`）。
5. 看“消息记录”里的失败详情（只显示最新一次失败原因），修复后手动重推。

## 11. ⚠ 本文件的文档矛盾 / 未说明

- 推送地址一个还是两个（正式 + 测试） → ⚠ 文档自相矛盾（7634 / 3943 vs ZnS3 / 41536 / 51411 / 3938）
- 无容器重推次数与间隔：16 次（10s…2h）vs 4 次（5s、5m20s、21m20s、2h） → ⚠ 文档自相矛盾
- 有容器消息扩展点重推：16 次后进死信 vs 无次数限制 → ⚠ 文档自相矛盾
- 推送是否有限流 → ⚠ 文档自相矛盾（DX7Q vs FAQ 45224）
- body 里 `sign` 字段的精确算法各消息写法不一 → ⚠ 文档未说明（用 Event-Sign）
- msg urlencode 时空格编码为 `%20` 还是 `+` → ⚠ 文档未说明
- 官方 PHP 接入指南页 `resource/doc/7635` 抓取失败（500 壳页），PHP 细节以 ZnS3 页的示例为准
