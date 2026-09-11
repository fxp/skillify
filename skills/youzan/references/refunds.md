# 售后与退款

内容整理自 https://doc.youzanyun.com/ （抓取于 2026-09-11）。**未用真实凭证验证**，本文件没有探测结论，
错误码与行为描述都是「文档原文，未实测」。调用格式见 `auth-token.md` 第 4 节。

## 目录
1. 两个关键点：refund_id 与 version 乐观锁
2. 查询售后单列表 `youzan.trade.refund.search.3.0.1`
3. 查询售后单详情 `youzan.trade.refund.get.3.0.1`
4. 商家处理买家申请：同意 / 拒绝 / 退货类
5. 商家主动退款 `youzan.trade.refund.seller.active.3.0.1`
6. 可退金额
7. 状态、消息与处理流程
8. ⚠ 本文件的文档矛盾 / 未说明

---

## 1. refund_id 与 version

- 一次售后 = 一张售后单，`refund_id`（年月日时分秒 + 10 位随机数，如 `201907042058500000031002`）。可从 `youzan.trade.refund.search`、`youzan.trade.get` 的 `refund_order[]`、退款消息里拿到。
- 售后单有 **`version`（Long）**：同意 / 拒绝等操作都要带**最新**的 version。版本不对 → `103010039 退款版本号错误`；状态已被别人改过 → `102010002 操作过期，请刷新后确认最新退款状态`。
- 正确流程：**先 `refund.get` 拿 status + version → 判断状态 → 带 version 操作 → 失败时重新 get 再判断**，不要缓存 version。

## 2. 查询售后单列表

**Endpoint**: `POST /api/youzan.trade.refund.search/3.0.1`
**用途**: 按订单、状态、时间筛售后单。**不传时间范围时默认只查最近 3 个月创建的。**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| tid | String | 否 | 订单号 |
| refund_id | String | 否 | 退款单号 |
| status | String | 否 | `WAIT_SELLER_AGREE`、`WAIT_BUYER_RETURN_GOODS`、`WAIT_SELLER_CONFIRM_GOODS`、`SELLER_REFUSE_BUYER`、`CLOSED`、`SUCCESS` 等 |
| type | Integer | 否 | 1 买家申请退款、2 商家主动退款、3 一键退款、4 零售门店换货、5 微商城换货 |
| demand | Integer | 否 | 1 仅退款、2 退货退款、3 换货 |
| create_time_start / create_time_end | Long | 否 | **Unix 时间戳，单位秒** |
| update_time_start / update_time_end | Long | 否 | 同上，秒 |
| yz_open_id / buyer_phone | String | 否 | 买家 |
| page_no | Integer | 否 | > 100 提示“查询页数超过100” |
| page_size | Integer | 否 | `page_no × page_size > 3000` 提示“超过ES搜索最大深度” |

注意时间格式和订单列表不同：订单列表是 `"yyyy-MM-dd HH:mm:ss"` 字符串，这里是**秒级时间戳**。

```bash
curl -X POST "https://open.youzanyun.com/api/youzan.trade.refund.search/3.0.1?access_token=$YOUZAN_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"status":"WAIT_SELLER_AGREE","update_time_start":1757433600,"update_time_end":1757520000,"page_no":1,"page_size":50}'
```
响应（摘录）：`data.total`、`data.refunds[]`：`refund_id`、`status`、`tid`、`kdt_id`、`return_goods`、`reason`（整数枚举）、`refund_fee`（**字符串，元**）、`created` / `modified`（`yyyy-MM-dd HH:mm:ss` 字符串）。错误 `53002 page_size type error`。

## 3. 查询售后单详情

**Endpoint**: `POST /api/youzan.trade.refund.get/3.0.1`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| refund_id | String | 是 | 售后单号 |
| query_option.include_all_consult_message | Boolean | 否 | 默认 false 只返回带附件的协商记录 |

```python
r = call("youzan.trade.refund.get", "3.0.1", {"refund_id": refund_id}, kdt_id=kdt_id)
status, version, fee = r["status"], r["version"], r["refund_fee"]   # fee 是元字符串，含邮费
```
关键响应字段：`refund_id`、`status`（含 `SELLER_REFUSE_BUYER_RETURN_GOODS` 卖家未收到货拒绝退款）、`tid`、`oid`（第一个退款商品的子单号）、`refund_fee`（元，含邮费）、`version`、
`refund_type`（`BUYER_APPLY_REFUND` / `SELLER_REFUND` / `EXCHANGE_GOODS` / `SYSTEM_REFUND`）、`demand`（1/2/3）、`return_goods`、`refund_success_time`。`item_id` 已废弃，用 `oid`。

错误：`103011024` 退款记录不存在、`103010052` 退款 ID 不合法、`103010054` 查询的店铺不符合该退款单权限。

## 4. 商家处理买家申请

| 动作 | API | 必需参数（文档） | 备注 |
|---|---|---|---|
| 同意退款 | `youzan.trade.refund.agree.3.0.1` | `refund_id`、`version` | 支持微商城、零售单店、连锁 D |
| 拒绝退款 | `youzan.trade.refund.refuse` | 退款 ID、版本号、拒绝理由（llms 摘要） | ⚠ 本 skill 未抓取参数表与版本号 |
| 同意退货 | `youzan.trade.returngoods.agree` | ⚠ 未抓取参数表 | 直播平台推广订单要用 3.0.0 并传省市区，否则 `103013007`（FAQ 5282） |
| 拒绝退货（未收到货） | `youzan.trade.returngoods.refuse` | ⚠ 未抓取参数表 | 买家已退货、等待卖家确认收货时用 |
| 审核售后单（新版） | `youzan.trade.refund.seller.operate.1.0.0` | ⚠ 未抓取参数表 | llms 摘要：审核售后单 |

同意退款示例：
```bash
curl -X POST "https://open.youzanyun.com/api/youzan.trade.refund.agree/3.0.1?access_token=$YOUZAN_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' -d '{"refund_id":"201903201354390000010886","version":1553482678792}'
```
```python
def agree_refund(call, kdt_id, refund_id):
    for _ in range(2):
        r = call("youzan.trade.refund.get", "3.0.1", {"refund_id": refund_id}, kdt_id=kdt_id)
        if r["status"] != "WAIT_SELLER_AGREE":
            return r["status"]                   # 已被处理或买家撤销，不再操作
        try:
            return call("youzan.trade.refund.agree", "3.0.1",
                        {"refund_id": refund_id, "version": r["version"]}, kdt_id=kdt_id)
        except YouzanError as e:
            if e.code in (103010039, 102010002):  # version 过期 / 状态已变：重新查
                continue
            raise
```
其他错误：`102010003` 操作太快、`102090108` 店铺余额不足（**退款需要店铺余额**）。

## 5. 商家主动退款

**Endpoint**: `POST /api/youzan.trade.refund.seller.active/3.0.1`
**用途**: 商家发起退款（无需买家申请）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| tid | String | 是 | 订单号 |
| biz_value | String | 是 | **调用方自定义的唯一请求标识**（建议时间戳 + 4 位随机数），用于防资损并发控制；同一笔退款重试要复用同一个值 |
| refund_fee | String | 是 | 退款金额，**元**；多商品整单退时为各项之和 |
| desc | String | 是 | 退款原因 |
| coupons | List<String> | 是 | 退款后失效的卡券列表；非卡券订单可传空数组 |
| oid | Long | 否 | 子单号；与 `items` 互斥，传了 items 则 oid 失效；两者必须传一个（仅退运费时都不传） |
| items[] | — | 否 | 多商品整单退时必填：`oid`、`refund_fee`（元）、`num`（仅已发货商品） |
| refund_fee_type | Integer | 否 | 1 = 只退运费 |

```python
import time, random
params = {"tid": tid, "oid": int(oid), "refund_fee": "12.50", "desc": "缺货退款", "coupons": [],
          "biz_value": f"{int(time.time()*1000)}{random.randint(1000, 9999)}"}   # 持久化后再调用，重试复用
res = call("youzan.trade.refund.seller.active", "3.0.1", params, kdt_id=kdt_id)
# res: {"refund_id": "...", "is_success": true}
```
- 响应 `code` 在文档里是 `java.lang.String` 类型（其他接口是 int）→ 比较时两种都兼容。
- 写操作不要在超时后换新 biz_value 重发，否则可能退两次。

## 6. 可退金额

- `youzan.trade.refund.amount.get.1.0.0`（查询订单售后金额详情）：传 `tid`、`oids`，返回 `data.item_aggregate`（llms 摘要；参数表未抓取）。
- “查询商品可退金额”（`detail/API/0/1047`）：传订单号和子订单号，返回剩余可退金额与数量，**金额单位是分**，不支持称重商品（llms 摘要）。
  → 和退款接口的“元”不一样 → ⚠ 同域内单位不一致，使用前按字段说明换算。

## 7. 状态、消息与流程

**售后单状态**（refund.get / search 的 `status`）：
`WAIT_SELLER_AGREE`（等待卖家同意）→ `WAIT_BUYER_RETURN_GOODS`（同意退货，等买家寄回）→ `WAIT_SELLER_CONFIRM_GOODS`（买家已寄回）→ `SUCCESS`；
分支：`SELLER_REFUSE_BUYER`（拒绝退款）、`SELLER_REFUSE_BUYER_RETURN_GOODS`（未收到货拒绝）、`CLOSED`（买家撤销）。

**`trade.get` 里的 `refund_order[].refund_state` 是另一套整数**：1 买家申请等待卖家同意、10 卖家拒绝、20 卖家同意退货等待买家退货、30 买家已退货等待卖家确认、40 卖家未收到货拒绝……（其余取值见文档原文）。两套不要混用。

**消息**（详见 `messages.md` 第 8 节）：旧版 `trade_refund_BuyerCreated`、`trade_refund_RefundSellerAgree`、`trade_refund_RefundSuccess`、`trade_refund_RefundClosed`、`trade_refund_SysRefund`…；
新版 `youzan_trade_RefundCreated` / `RefundSellerAgree` / `RefundSuccess` / `RefundClosed`（msg 是对象，带 `refund_id`、`version`、`refunded_fee`（元）、`refund_type`）。
收到消息后等 30 秒以上再调 `trade.get` / `refund.get`（trade.get 描述原文）。

**一键 / 系统退款**（`trade_refund_SysRefund`，由有赞自动触发）场景包括：订单关闭退款、拼团未成团、返现、送礼子单未领取、少付 / 超付、酒店或外卖拒单、代付过期、会员卡发卡失败等（FAQ 34662、41665）。这类退款没有商家审批环节，ERP 只需同步结果。

**典型 ERP 流程**
1. 订阅新版 `youzan_trade_RefundCreated`（或旧版 `trade_refund_BuyerCreated`）→ 入待审队列；
2. 审核时 `refund.get` 取最新 status + version；
3. 仅退款：`refund.agree`；退货退款：`returngoods.agree` → 等 `WAIT_SELLER_CONFIRM_GOODS` → 仓库收货后 `refund.agree`（或 `returngoods.refuse`）；
4. 以 `youzan_trade_RefundSuccess` / `trade_refund_RefundSuccess` 为最终结果，定期用 `refund.search` 按 `update_time_*` 对账。

## 8. ⚠ 本文件的文档矛盾 / 未说明

- `refund.refuse`、`returngoods.agree`、`returngoods.refuse`、`refund.seller.operate`、`refund.amount.get` 的完整参数表 → ⚠ 未收录（只见 llms 摘要）
- 可退金额接口单位是分，退款接口是元 → ⚠ 同域单位不一致（按各自字段说明处理）
- `refund.seller.active` 响应 `code` 类型为 String → ⚠ 与其他接口不一致
- `refund_state` 完整枚举 → ⚠ 文档字段描述被截断，本 skill 未收全
