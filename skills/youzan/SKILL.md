---
name: youzan
description: 接入有赞云开放平台（Youzan Cloud，doc.youzanyun.com，接口域名 open.youzanyun.com）服务端 API 的使用手册——涵盖自用型（authorize_type=silent + 店铺 kdt_id）与工具型（授权 code、refresh_token）应用获取和刷新 access_token、按“API 名称 + 版本号”拼路径调用网关、订单列表与详情（youzan.trades.sold.get、youzan.trade.get）、发货（youzan.logistics.online.confirm）、售后退款、商品创建查询与上下架、客户 / 积分 / 标签（yz_open_id）、消息推送的订阅与 Event-Sign 验签去重、错误码（gw_err_resp）与限流额度。当用户提到"有赞""有赞云""有赞开放平台""Youzan""youzanyun""有赞微商城 API""kdt_id""yz_open_id""trade_TradeBuyerPay""Event-Sign""youzanyun-sdk"，或要写代码对接有赞店铺的订单、发货、退款、商品、会员、积分、消息推送时，应主动使用本技能，不要凭记忆编造接口参数，也不要套用老有赞开放平台 open.youzan.com、淘宝或微信的接口习惯。
---
# 有赞云（Youzan Cloud）开放平台接入指南

有赞云把有赞微商城 / 零售 / 连锁的交易、商品、客户等能力以“开放 API + 消息推送”开放：应用先按类型（自用型 / 工具型）换 access_token，
再用 `POST /api/{API 名称}/{版本号}?access_token=` 调网关；业务变更通过 HTTP 推送到你的地址。**本页只做分流与规则，字段表和示例在 references/。**

## ⚠ 验证状态

文档版：内容整理自 https://doc.youzanyun.com/ （抓取于 2026-09-11，126 个正文页 + 19 个 llms.txt 索引文件；其中 2 页只拿到 500 壳页），**未用真实凭证调用验证**。
另做了 22 次无凭证探测（伪造 client_id / token，确认网关错误结构、token 位置、路径规则、HTTP→HTTPS），命令与结果见 `youzan-workspace/probe-log.md`。
报错描述凡未标「无凭证探测」的，都是「文档原文，未实测」。拿到凭证后按 `youzan-workspace/verification-plan.md` 补测；对照实验待真实凭证到位后进行。

## 当前事实

| 项 | 值 |
| :--- | :--- |
| API 地址 | `POST https://open.youzanyun.com/api/{api_name}/{api_version}?access_token=TOKEN`，body 为 JSON。`youzan.trade.get.4.0.2` → `/api/youzan.trade.get/4.0.2` |
| 换 token | `POST https://open.youzanyun.com/auth/token`，**必须 `Content-Type: application/json`** |
| 鉴权 | **access_token 只放 URL query**。无凭证探测（×2）：放 `Authorization: Bearer` 头或 JSON body 都返回 `gw_err_resp.err_code 4201 非法的请求凭证` |
| 最容易选错 | **应用类型决定换 token 方式**：自用型 `authorize_type=silent` + `grant_id=kdt_id` + `refresh`；工具型 `authorization_code` + 回调推来的 `code`（2 分钟、一次性），之后用 `refresh_token`（28 天）续 |
| 有效期 | access_token 7 天；响应 `data.expires` 是**过期时刻的毫秒时间戳**；token 按「应用 + 店铺」生成，缓存键带 kdt_id |
| 错误判定 | 无凭证探测（×2）：错误响应 HTTP 状态都是 200；网关错误是 `{"gw_err_resp":{"err_code","err_msg","trace_id"}}`，`/auth/token` 与业务错误是 `{"success":false,"code":N,"message"}`；业务成功 `code=200` |
| 金额单位 | 订单 / 退款金额是**元（字符串）**；商品创建与查询价格是**分（Long）**；老接口 `item.sku.update` 价格是元（Double） |
| 消息验签 | 请求头 `Event-Sign = md5(client_id + 原始请求体 + client_secret)`；5 秒内返回含 `success` 的 body |

## 照通用经验写容易错的地方（来自文档，未实测）

1. **token 不是 Bearer 头。** 只能拼在 URL 的 `access_token` 参数里（FAQ 34579 原文）；这一条另有无凭证探测证实：放头或 body 都被当作未传（4201）。
2. **自用型和工具型换 token 完全不是一回事。** 自用型用 kdt_id 直接换、`refresh=true` 刷新；工具型要先接住订购回调（GET、GBK、不许带自定义参数、三条消息无序）里的 code 再换。用错 → `1105`。`expires` 按毫秒时间戳处理，不是秒数。
3. **API 按“名称 + 版本号”定位，版本是路径段。** 同名接口不同版本字段不同（订单列表 4.0.4 查不到 2020 年前订单，要用 4.0.0）；缺版本号 → 4001，版本不存在 → 4005（均为无凭证探测）。
4. **同一平台金额单位混用，且不会报错。** `trade.get` 的 `payment` 是 `"9.82"` 元，同一响应里 `deduction_pay` 是分；`item.common.create` 的 `skus.price` 要传分（19.90 元传 1990）；退款接口是元，“查询商品可退金额”是分。
5. **消息推送是 MD5 拼接验签 + urlencode 的 msg。** 对原始字节算 `md5(client_id+body+client_secret)`；交易类 `msg` 要先 urldecode 再解析；会重推、会乱序：用 `msg_id` 去重、`version` 丢弃旧消息；5 秒超时，先 ACK 后异步。
6. **“待发货”要听 `trade_TradeBuyerPay`，不是 `trade_TradePaid`。** 付款后可能是待成团 / 待接单；虚拟商品、电子卡券不会触发 BuyerPay。收到消息后等 30 秒以上再调订单详情 / 列表（接口有延迟）。
7. **写操作带版本号或幂等键。** 同意退款要带 `refund.get` 取到的最新 `version`；主动退款、积分加减用稳定的 `biz_value`（+`biz_token`）防重复；发货前查状态防 `102510001` / `102570007`。

## 我要做什么 → 读哪一份

| 我要做什么 | 读 | 核心 endpoint |
| :--- | :--- | :--- |
| 换取 / 刷新 / 缓存 access_token，工具型 code 回调，拼 API 调用 | [`auth-token.md`](references/auth-token.md) | `POST /auth/token` · `POST /api/{name}/{version}` |
| 拉订单列表与详情、读金额字段、发货、快递公司、备注 | [`orders-shipping.md`](references/orders-shipping.md) | `youzan.trades.sold.get 4.0.4` · `youzan.trade.get 4.0.2` · `youzan.logistics.online.confirm 3.0.0` |
| 查售后单、同意 / 拒绝退款、商家主动退款 | [`refunds.md`](references/refunds.md) | `youzan.trade.refund.search 3.0.1` · `youzan.trade.refund.get 3.0.1` · `youzan.trade.refund.agree 3.0.1` · `youzan.trade.refund.seller.active 3.0.1` |
| 创建 / 编辑 / 上下架 / 查询商品，改价改库存 | [`products.md`](references/products.md) | `youzan.item.common.create 1.0.0` · `youzan.item.itemdetail.get 1.0.0` · `youzan.item.base.search 1.0.0` · `youzan.item.display.update 1.0.0` |
| 客户创建查询、手机号换 yz_open_id、积分加减、打标签 | [`customers.md`](references/customers.md) | `youzan.scrm.customer.create 3.0.0` · `youzan.scrm.customer.detail.get 1.0.1` · `youzan.crm.customer.points.increase 4.0.0` · `youzan.scrm.tag.relation.add 4.0.0` |
| 订阅消息、接收推送、验签、去重、重推 | [`messages.md`](references/messages.md) | `POST 你的推送地址`（`Event-Sign` / `Event-Type` / `Client-Id`） |
| 判错、错误码含义、限流退避、额度计费 | [`errors-and-limits.md`](references/errors-and-limits.md) | `gw_err_resp.err_code` 4001–5003 · 限流 4101 |

本 skill 不覆盖：后端 / 前端扩展点、有容器应用开发与云函数、iPaaS、营销（优惠券、拼团）、分销、储值、客服、企微助手、装修、小程序与 App 开店 SDK、
电子面单与发票、跨境报关、应用市场内购、数据加解密 API（敏感字段密文存储要求见 `https://doc.youzanyun.com/resource/doc/3020`）。
入口均在 https://doc.youzanyun.com/llms.txt 的对应模块。

## House rules

- 凭证只走环境变量：`YOUZAN_CLIENT_ID`、`YOUZAN_CLIENT_SECRET`、`YOUZAN_KDT_ID`；不要把 client_secret 放进前端或日志。
- 所有调用走一个封装：token 进 query、解析 `gw_err_resp` 与 `success/code` 两种结构、4201/4202/4203 刷新一次重试一次、限流按 3/6/12/24/48 秒退避（`errors-and-limits.md`）。
- 文档写 `java.lang.String` 的传字符串、`java.util.Date` 的传 `yyyy-MM-dd HH:mm:ss`；类型不对多半报 `5001 系统异常`。
- 金额一律 `Decimal`，按接口区分元 / 分；时间戳看清秒还是毫秒（退款、客户列表是秒，商品查询是毫秒）。
- 多店铺：token、消息、数据都按 `kdt_id` 隔离；测试店与正式店靠 kdt_id 区分。
- 消息只做触发，状态以 API 查询为准；消息记录只留 7 天，订购到期期间的消息不补推，定期用列表接口对账。
- 大多数 API 计费；试用额度只含订单、商品试用接口；欠费会限流或停用 API 与消息。

## 文档自相矛盾 / 未说明之处（⚠ 汇总）

- 自用型 `refresh=true` 后旧 token 1 小时后失效 vs 立即失效；工具型刷新后旧 access_token 是否还能用 1 小时；自用型响应是否含 refresh_token → `auth-token.md`
- `refresh` 能否传字符串；`refresh_token` 刷新参数不在参数表；回调应返回什么；订购消息 AES 解密细节；IP 白名单正文页不可得 → `auth-token.md`
- 推送地址一个还是两个；无容器重推 16 次 vs 4 次；有容器扩展点重推 16 次 vs 无限；推送是否限流；body.sign 算法 → `messages.md`
- `trade.get` 时间格式描述与示例不一致；发货 `outer_sender` 类型；单商品多运单参数表未收录；手机号换 yz_open_id 用哪个接口 → `orders-shipping.md`
- 拒绝退款 / 退货类接口参数表未收录；可退金额单位是分；`refund_state` 枚举不全 → `refunds.md`
- 划线价单位；新版改价改库存接口未收录；异步删除延迟 → `products.md`
- `customer.detail.get` 必填项与 `created_at` 单位；客户已存在的两个错误码；积分 4.0.0 QPS → `customers.md`
- 订单类接口 QPS；限流 4101 完整结构；1000 / 4007 错误码复用 → `errors-and-limits.md`

## 文档与探测不符之处

reference 中用 `<!-- Gap: … -->` 标记，可 grep 定位（1 处）：全局错误码页只给出 `{success, code, data, message}` 结构，
无凭证探测（×2）`/api/` 网关层 4001 / 4005 / 4007 / 4201 / 4203 实际返回 `gw_err_resp.err_code / err_msg` → `errors-and-limits.md`。
