# 订单与发货

内容整理自 https://doc.youzanyun.com/ （抓取于 2026-09-11）。**未用真实凭证验证。**
报错与行为描述未标注来源的都是「文档原文，未实测」；标「无凭证探测（2026-09-11）」的见 `youzan-workspace/probe-log.md`。
所有接口都按 `POST https://open.youzanyun.com/api/{api_name}/{version}?access_token=...` 调用（见 `auth-token.md` 第 4 节）。

## 目录
1. 同步订单的推荐做法
2. 查询订单列表 `youzan.trades.sold.get.4.0.4`
3. 查询订单详情 `youzan.trade.get.4.0.2`
4. 状态、类型、金额字段怎么读
5. 订单发货 `youzan.logistics.online.confirm.3.0.0`
6. 单商品多运单 `youzan.trade.dc.delivery.ordersingleitemsend.3.0.1`
7. 快递公司列表 `youzan.logistics.express.get.3.0.0`
8. 订单备注 `youzan.trade.memo.update.3.0.0`
9. 按买家手机号查订单
10. ⚠ 本文件的文档矛盾 / 未说明

---

## 1. 同步订单的推荐做法

文档（4978、5171、订单管理集成方案）给的组合：

| 目的 | 用什么 | 注意 |
|---|---|---|
| 实时 | 消息推送：`trade_TradeBuyerPay`（待发货）、`trade_TradeClose`、`trade_TradeSuccess`… | 见 `messages.md` |
| 补全单笔 | `youzan.trade.get.4.0.2` | 收到消息后**等 30 秒以上**再查，接口有延迟 |
| 历史 / 补漏 | `youzan.trades.sold.get.4.0.4` 按时间窗口轮询 | 同样有延迟；轮询间隔 > 30 秒，返回空可重试 |
| 2020 年以前的订单 | `youzan.trades.sold.get.4.0.0` | 4.0.4 查不到 |

- 标准能力只支持**把有赞订单同步到三方**；三方订单导入有赞需要大客定制或外部订单接口（`youzan.trade.order.out.create`，本 skill 不覆盖）。
- 同一店铺授权给多个 ERP 时，每个应用都会拿到全部订单，需要自行按商品编码等规则过滤。

## 2. 查询订单列表

**Endpoint**: `POST /api/youzan.trades.sold.get/4.0.4`
**用途**: 按时间 / 状态 / 买家搜索卖家已卖出的订单；用于历史拉取和补漏。不返回 `buyer_id`（用 `yz_open_id`）。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| start_created / end_created | Date | 否 | 按创建时间。格式 `yyyy-MM-dd HH:mm:ss`；**必须成对**、跨度 **≤ 3 个月**、结束 > 开始 |
| start_update / end_update | Date | 否 | 按更新时间（同上约束）；范围内订单是动态变化的 |
| start_success / end_success | Date | 否 | 按完成时间 |
| start_pay / end_pay | Date | 否 | 按支付完成时间 |
| status | String | 否 | **一次只能一种**：`WAIT_BUYER_PAY`、`WAIT_SELLER_SEND_GOODS`、`WAIT_BUYER_CONFIRM_GOODS`、`TRADE_SUCCESS`、`TRADE_CLOSED`、`TRADE_REFUND` |
| type | String | 否 | `NORMAL`、`GIFT`、`GROUP`、`HOTEL`、`KNOWLEDGE_PAY` 等 |
| tid | String | 否 | 订单号 |
| yz_open_id | String | 否 | 买家 |
| receiver_phone / receiver_name | String | 否 | **收货人**手机号 / 姓名（不是买家账号） |
| keywords | String | 否 | 订单号、收货人手机号或其后四位 |
| express_type | String | 否 | `EXPRESS`、`SELF_FETCH`、`LOCAL_DELIVERY` |
| page_no | Integer | 否 | 从 1 开始，**最大 100** |
| page_size | Integer | 否 | 默认 20，**最大 100** |
| need_order_url | Boolean | 否 | 是否返回订单 url |

排序规则（原文）：只有创建时间按创建时间排；有更新时间按更新时间排；有完成时间则按完成时间排；只有付款时间按付款时间排；**时间参数不成对出现时条件无效**。

**示例请求**
```bash
curl -X POST "https://open.youzanyun.com/api/youzan.trades.sold.get/4.0.4?access_token=$YOUZAN_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"start_update":"2026-09-10 00:00:00","end_update":"2026-09-11 00:00:00","page_no":1,"page_size":100}'
```
```python
from datetime import datetime, timedelta
FMT = "%Y-%m-%d %H:%M:%S"        # 只传日期会得到 5001 系统异常（FAQ 33694）

def iter_orders(call, kdt_id, start: datetime, end: datetime, window=timedelta(hours=6)):
    """按更新时间分窗口拉取；每个窗口最多 100 页 × 100 条，超了就缩小窗口。"""
    seen = set()
    t = start
    while t < end:
        t2 = min(t + window, end)
        for page in range(1, 101):
            data = call("youzan.trades.sold.get", "4.0.4",
                        {"start_update": t.strftime(FMT), "end_update": t2.strftime(FMT),
                         "page_no": page, "page_size": 100}, kdt_id=kdt_id) or {}
            rows = data.get("full_order_info_list") or []
            for row in rows:
                tid = row["full_order_info"]["order_info"]["tid"]
                if tid not in seen:            # 翻页期间订单变化会造成重复（FAQ 47347）
                    seen.add(tid); yield row["full_order_info"]
            if len(rows) < 100:
                break
        else:
            raise RuntimeError("窗口内超过 10000 单，缩小 window 重拉")
        t = t2
```

**示例响应**（精简）
```json
{"code": 200, "success": true, "message": "successful",
 "data": {"total_results": 1,
          "full_order_info_list": [{"full_order_info": {"order_info": {"tid": "E2019...", "status": "WAIT_SELLER_SEND_GOODS"}, "pay_info": {"payment": "9.82"}, "orders": [...]}}]}}
```

**注意事项**
- 翻页过程中有新订单或状态变化，记录会在页间移动，**同一订单可能出现两次**，必须按 tid 去重。
- 超过 100 页的数据要缩短时间窗口分多次查。
- 错误（文档原文，未实测）：`5000 每页最多显示100条数据`、`5000 开始时间不能大于结束时间`、`106000003` 结束时间不能超过当前日期后 7 天、`106000001` / `106100118` 请求超时可重试、`106100110` 订单号非法、`106100114` 手机号过长（>20）、`106100115` 用户名过长（>50）。
- 失败时 `data` 仍可能带空的 `full_order_info_list: []`，不要把“空列表”当成功。
- 无凭证探测（2026-09-11，×2）：token 放 `Authorization: Bearer` 头调用本接口 → `{"gw_err_resp":{"err_msg":"非法的请求凭证","err_code":4201}}`。

## 3. 查询订单详情

**Endpoint**: `POST /api/youzan.trade.get/4.0.2`
**用途**: 查单笔订单的全部信息（商品明细、金额、收货地址、优惠、退款、发货包裹）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| tid | String | 是 | 有赞订单号，E 开头 24 位；也支持 C 开头的送礼子订单号 |

```python
detail = call("youzan.trade.get", "4.0.2", {"tid": "E20190312105415047400001"}, kdt_id=kdt_id)
info = detail["full_order_info"]
print(info["order_info"]["status"], info["pay_info"]["payment"], info["buyer_info"]["yz_open_id"])
```

**响应结构**（`data` 下，字段名与层级摘自文档）
```
full_order_info
├── order_info: tid, status, status_str, type, created, update_time, pay_time, consign_time, success_time,
│               refund_state, express_type, close_type, pay_type, channel_type, order_tags{is_virtual, is_refund, ...}, order_extra{...}
├── buyer_info: yz_open_id, buyer_phone（绑定手机号才有）, outer_user_id（微信 openid 或 App open_user_id）
├── address_info: receiver_name, receiver_tel, delivery_province/city/district/address, delivery_postal_code, address_extra（JSON 字符串，百度坐标）, self_fetch_info
├── pay_info: total_fee, post_fee, payment, real_payment, deduction_pay, deduction_real_pay, transaction[], outer_transactions[], phase_payments[]
├── orders[]: oid, item_id, sku_id, title, num, price, total_fee, payment, discount_price, outer_item_id, outer_sku_id, sku_properties_name, item_type, is_present, buyer_messages
├── remark_info: buyer_message（买家留言）, trade_memo（卖家备注）
└── child_info.child_orders[]（送礼子单）
order_promotion: item[], order[], item_discount_fee, order_discount_fee, adjust_fee
refund_order[]: refund_id, refund_type, refund_state, refund_fee, refund_time, oids[]
delivery_order[]: express_state(0 待发货/1 已发货), express_type(0 后台手动/1 API 发货), oids[], dists[]
```

**异常示例**（文档原文）
```json
{"trace_id": "yz7-...", "code": 5000, "success": false, "message": "trade not found",
 "data": {"delivery_order": [], "refund_order": [], "full_order_info": {"orders": [], "pay_info": {"phase_payments": []}}}}
```
- `5000 trade not found`：订单号错，或**用 A 店铺的 token 查 B 店铺的订单**（FAQ 34556）。
- `106000004` 订单号非法。
- 成功但字段为空：先核对 token 对应的店铺是否就是订单所属店铺（FAQ 41640）。
- `buyer_info` 里的 `fans_id` / `fans_type` / `fans_nickname` 已废弃，用 `yz_open_id`。昵称是下单时的快照（FAQ 41544）。
- 收货地址经纬度是**百度坐标系**；接高德要转换（FAQ 4118 摘要：经度 −0.0065、纬度 −0.006）。
- 时间字段的描述写“yyyy年-MM月-dd日 HH时:mm分:ss秒”，示例值却是 `2019-08-20 10:19:43` → ⚠ 文档自相矛盾，按示例格式解析并做容错。

## 4. 状态、类型、金额字段

**主订单状态 `order_info.status`**：`WAIT_BUYER_PAY`（含定金待付 / 尾款待付）→ `TRADE_PAID`（**瞬时**，稍后变为后续状态）→ `WAIT_CONFIRM`（待成团、待接单）→ `WAIT_SELLER_SEND_GOODS` → `WAIT_BUYER_CONFIRM_GOODS` → `TRADE_SUCCESS`；任意阶段可到 `TRADE_CLOSED`。
- 虚拟商品 / 电子卡券 / 知识付费没有待发货状态（支付后自动发货，T+7 自动确认收货）。
- `refund_state`：0 未退款、2 部分退款成功、12 全额退款成功；1 部分退款中、11 全额退款中为瞬时状态，建议重试查询。
- `express_type`：0 快递、1 到店自提、2 同城配送、9 无需发货。
- `close_type`：1 过期关闭、2 标记退款、3 订单取消、4 买家取消、5 卖家取消、6 部分退款…（完整枚举见文档）。
- 交易关闭的三种原因：主动取消、超时未付、全额退款（FAQ 33681）。

**金额单位（最容易错）**

| 字段 | 类型 | 单位 |
|---|---|---|
| `pay_info.total_fee` / `post_fee` / `payment` / `real_payment` | String | **元**（如 `"9.82"`） |
| `orders[].price` / `total_fee` / `payment` / `discount_price` | String | 元 |
| `refund_order[].refund_fee` | String | 元 |
| `pay_info.deduction_pay` / `deduction_real_pay`（礼品卡 / 储值卡抵扣） | Long | **分** |
| `order_extra.cash` / `t_cash` / `tm_cash`（返现） | Integer | 分 |

同一个响应里元和分混用；统一用 `Decimal` 处理，元字段**不要再除以 100**。

金额关系（FAQ 29773，文档示例）：
```
pay_info.payment = pay_info.total_fee − (order_promotion.order_discount_fee + order_promotion.item_discount_fee)
                   + order_promotion.adjust_fee + pay_info.post_fee        # 9.82 = 13 − (1.18 + 4.00) + 0 + 2
sum(orders[].payment) = pay_info.payment                                 # 子单实付是分摊后的，含订单级优惠与邮费分摊
orders[].total_fee = price × num − 商品级优惠                              # 订单级优惠不从 total_fee 扣
```
- 订单优惠总额 ≈ `pay_info.total_fee − pay_info.payment`（FAQ 34321 摘要，不适用于分销采购单）。
- 按供货商分账直接用子单 `orders[].payment`。
- `fenxiao_price` / `fenxiao_payment` 是分销商（供货单）维度的金额。

## 5. 订单发货

**Endpoint**: `POST /api/youzan.logistics.online.confirm/3.0.0`（计费）
**用途**: 确认发货，订单状态由“买家已付款”变为“卖家已发货”。支持普通、周期购、送礼、采购单；支持快递和“无需物流”。
**不支持**：单品多运单（用第 6 节接口）、含非实物商品的订单、分销单、同城送、零售连锁版订单。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| tid | String | 是 | 有赞订单号 |
| oids | String | 否 | 子订单号，**多个用英文逗号拼成一个字符串**；部分发货时必传，整单发货不传；`is_no_express=1` 时不用传 |
| is_no_express | Integer | 否 | 0 或不传：物流发货；1：无需物流 |
| out_stype | String | 条件必填 | 物流公司 id（来自 `youzan.logistics.express.get`），物流发货时必传 |
| out_sid | String | 条件必填 | 快递单号，物流发货时必传；只能含字母、数字、中划线 |
| gift_order_no | String | 否 | 送礼子单号（C 开头，来自 `trade.get` 的 `child_info.child_orders[].tid`） |
| outer_sender.sender_mobile | String | 否 | 发货人手机号，用于订阅物流轨迹，**顺丰必传** |
| admin_id | Long | 否 | 操作人 id |

```bash
curl -X POST "https://open.youzanyun.com/api/youzan.logistics.online.confirm/3.0.0?access_token=$YOUZAN_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"tid":"E20190716165622057400039","out_stype":"1","out_sid":"90898989089380"}'
```
```python
def ship(call, kdt_id, tid, express_id, waybill, oids=None, sender_mobile=None):
    params = {"tid": tid, "is_no_express": 0, "out_stype": str(express_id), "out_sid": waybill}
    if oids:
        params["oids"] = ",".join(str(o) for o in oids)       # 逗号字符串，不是数组
    if sender_mobile:
        params["outer_sender"] = {"sender_mobile": sender_mobile}
    return call("youzan.logistics.online.confirm", "3.0.0", params, kdt_id=kdt_id)
```
**响应**：`{"code":200,"success":true,"data":{"is_success":true},"message":"successful","trace_id":"..."}`

**注意事项**
- 错误码（文档原文，未实测）：`102570020` 没有可发货商品、`102510001` 不能同时发起两笔相同的发货请求、`102570007` 不能重复提交已发货商品、`102599996` oids 含非数字、`105000016` 订单不存在、`105000003` 快递单号格式、`102570038` 分销单只能由分销系统发货、`-100` 操作异常可重试。
- 发货是写操作：先查 `delivery_order` / 状态，或用本地幂等表，避免并发和重复发货。
- 没传发货人时，店铺后台把 **access_token 所属应用的名称**记为发货人（FAQ 5208）。
- 文档示例把 `outer_sender` 写成 JSON 字符串 `"{\"sender_mobile\":\"...\"}"`，参数表写 object → ⚠ 文档自相矛盾；按 object 传。
- 描述里“不支持零售连锁版订单发货”与“仅支持零售连锁专业版，且多仓改派的不支持”并列 → ⚠ 文档未说明清楚，零售连锁店铺先在测试店验证。
- 无凭证探测（2026-09-11，×2）：把 access_token 放 JSON body（URL 不带）→ `{"gw_err_resp":{"err_msg":"非法的请求凭证","err_code":4201}}`。

## 6. 单商品多运单

**Endpoint**: `POST /api/youzan.trade.dc.delivery.ordersingleitemsend/3.0.1`
**用途**: 同一商品拆成多个运单（例：10 件苹果分两箱）。多种商品分别发货用第 5 节接口即可（FAQ 3405）。
- 本 skill 只抓到 FAQ（3405、37050 摘要），参数表未抓取：示例涉及 `tid`、`oid`、`ex_packages`（每个包裹含物流信息与数量 `num`）、`request_id`、`total_num` → ⚠ 文档未说明（本 skill 未收录完整参数表，写代码前打开原文）。
- 每种商品必须一次性发完：`ex_packages[].num` 之和必须等于该商品购买数，否则 `102570059`。
- 多门店拆单：每个商品 oid 分别调用，不能把不同商品合并一次发（FAQ 43357 摘要）。

## 7. 快递公司列表

**Endpoint**: `POST /api/youzan.logistics.express.get/3.0.0`，无业务参数（传 `{}`）。
响应 `data.allExpress[]`：`id`（物流公司编号，即发货的 `out_stype`）、`name`（如“申通快递”）、`display`（0 显示、1 不显示）。
建议启动时拉一次缓存，按名称映射 id；**不要把快递公司名称直接当 out_stype**。

## 8. 订单备注

**Endpoint**: `POST /api/youzan.trade.memo.update/3.0.0`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| tid | String | 是 | 订单号 |
| memo | String | 是 | 卖家备注 |
| flag | String | 否 | 打星 1~5 |

- 响应结构与其他接口不同：`{"response":{"is_success":true}}`；失败 `{"error_response":{"msg":"...","code":500}}`；`50000` 订单不存在。
- 改卖家备注会触发 `trade_TradeMemoModified` 消息；但**在平台更新卖家留言不会改变订单更新时间**（FAQ 34760），按 `start_update` 增量拉取抓不到这类变化。
- 订单更新时间在状态更新、改价、买家账号迁移、商家添加备注后变化（FAQ 33682 摘要）。

## 9. 按买家手机号查订单

`youzan.trades.sold.get` 不能直接按**买家**手机号查（`receiver_phone` 是收货人）。先把手机号换成 `yz_open_id`，再作为 `yz_open_id` 参数查列表：
- FAQ 43206：用 `youzan.user.basic.get`（3.0.1，`mobile` 与 `yz_open_id` 二选一，返回 `data.yz_open_id`）；
- FAQ 4946（较新）：用 `youzan.users.info.query`。
两份 FAQ 给的接口不同 → ⚠ 文档自相矛盾（可能两个都可用，未说明差异）。详见 `customers.md`。

## 10. ⚠ 本文件的文档矛盾 / 未说明

- `trade.get` 时间字段格式描述与示例不一致 → ⚠ 文档自相矛盾
- `logistics.online.confirm` 的 `outer_sender` 类型（object vs JSON 字符串）；零售连锁支持范围描述 → ⚠ 文档自相矛盾 / 未说明
- 单商品多运单接口完整参数表 → ⚠ 未收录（只见 FAQ）
- 手机号换 yz_open_id 用 `user.basic.get` 还是 `users.info.query` → ⚠ 文档自相矛盾
- 订单类接口的 QPS 限额 → ⚠ 文档未说明（见 `errors-and-limits.md`）
