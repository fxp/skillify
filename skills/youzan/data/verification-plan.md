# 有赞云 skill 验证计划（待真实凭证）

当前状态：文档版，抓取于 2026-09-11，**未用真实凭证验证**；无凭证探测见 `probe-log.md`。
需要的测试资源：有赞云开发者账号（完成认证）、一个**自用型无容器**应用 + 一个云测试店铺（微商城单店，免费、30 天有效）；
如要验证工具型流程，再建一个工具型无容器应用（需服务商身份）并用测试店铺“获取 code”。一个可公网访问、域名不含下划线的推送地址。
所有凭证只走环境变量（`YOUZAN_CLIENT_ID`、`YOUZAN_CLIENT_SECRET`、`YOUZAN_KDT_ID`）；测试店铺里的商品 / 订单 / 客户用完删除；全仓库 grep client_secret 前 8 位。
注意：试用额度仅 1 万次 / 60 天且只含订单、商品试用接口（`resource/doc/8770`），客户 / 积分类接口可能需要套餐。

## P0：开头几件事（错了全盘皆错）

| # | 要验证的结论 | 怎么测 | 判定 | 成本 |
|---|---|---|---|---|
| 1 | silent 换 token 成功，`data.expires` 是毫秒时间戳（≈ now+7 天） | `POST /auth/token` | `expires/1000 - now ≈ 604800` | 0 |
| 2 | 真实 token 放 `Authorization: Bearer` 头仍 4201（假 token 已探测） | 同一真实 token 分别放 header / query 调 `youzan.shop.basic.get/3.0.0` | header → 4201，query → 200 | 1 次计费调用 |
| 3 | 业务成功的结构是 `{code:200, success:true, data, message, trace_id}` | 调 `youzan.shop.basic.get` | 字段一致 | 同上 |
| 4 | 业务失败结构（不存在的订单号） | `youzan.trade.get/4.0.2` 传 `E2000...` | `code 5000 trade not found`，还是 `gw_err_resp` | 1 次 |
| 5 | 自用型响应是否带 `refresh_token` | 看 #1 的响应 | 有 / 无 → 修 auth-token.md ⚠ | 0 |

## P1：⚠ 清单（文档矛盾 / 未说明）

| # | ⚠ 条目 | 测法 | 判定 |
|---|---|---|---|
| 6 | 自用型 `refresh=true` 后旧 token 是 1 小时后失效还是立即失效 | refresh=true 后立刻、10 分钟、65 分钟用旧 token 调 `shop.basic.get` | 记录 4202/4203 出现时间 |
| 7 | `refresh` 传字符串 `"false"` 是否被接受 | 同一请求 refresh 分别传 `"false"` 与 `false` | 是否报错 / 行为是否一致 |
| 8 | 工具型刷新后旧 access_token 是否仍可用 1 小时 | 工具型应用 refresh_token 刷新后用旧 access_token 调用 | 同 #6 |
| 9 | form 编码换 token 返回 1000（单次探测）是否稳定 | 再跑 probe.sh 的 A3 | 两次一致才能进 SKILL.md |
| 10 | 推送地址是一个还是两个（正式 + 测试） | 控制台“消息订阅 → 推送网址”看有几个输入框 | 以控制台为准修 messages.md |
| 11 | 无容器推送重推次数与间隔（16 次 vs 4 次） | 推送地址故意返回 500，记录收到的次数与间隔（sendCount） | 记录实际序列 |
| 12 | Event-Sign 算法与大小写 | 用消息调试工具推一条，本地算 `md5(client_id+raw+secret)` | 相等则确认 |
| 13 | msg urlencode 的空格编码（%20 / +） | 构造含空格的备注触发 `trade_TradeMemoModified` | 看原始 msg |
| 14 | 新版 `youzan_trade_Refund*` 消息 msg 是否确为对象、是否也需 urldecode | 测试店铺发起退款 | 看原始 body |
| 15 | `youzan.logistics.online.confirm` 的 `outer_sender` 传对象还是 JSON 字符串 | 两种各发一次（用测试订单） | 哪种成功 |
| 16 | `youzan.scrm.customer.detail.get` 的 `created_at` 是秒还是毫秒 | 查一个测试客户 | 位数 |
| 17 | 手机号查 yz_open_id：`youzan.user.basic.get.3.0.1` 与 `youzan.users.info.query` 是否都可用 | 各调一次 | 记录可用性与权限包 |
| 18 | 订单类接口的限流阈值（文档未给） | **不做压测**；只在出现 4101 时记录 trace_id 咨询 | — |
| 19 | `item.common.create` 创建后微商城是否立即可售、`display` 默认值 | 创建一件测试商品 | 查 `itemdetail.get` 的上下架字段 |
| 20 | `youzan.item.delete.3.0.1` 异步删除的生效延迟 | 删除后轮询 `itemdetail.get` | 记录多久返回 122001001 |

## P2：没抓到 / 需要资料包才能确认的

- `resource/doc/7555`（IP 白名单正文）、`resource/doc/7635`（PHP 消息接入）抓取为 500 壳页；登录控制台或换时间重抓。
- 订购消息 AES 解密算法只在 zip demo（`java-AES.zip` / `PHP-AES.zip`）里，按规矩未下载；有权限的人下载后补进 auth-token.md。
- 官方 SDK（Java / PHP / Node）需在控制台“打包下载”，未核实 SDK 方法签名；补测时用 SDK 跑一遍 #1–#4。
- `youzan.trade.dc.delivery.ordersingleitemsend.3.0.1`（单商品多运单）只看到 FAQ 摘要，参数表未抓取。

## 判定后怎么改
每条结论改回对应 reference，写“已用真实凭证验证（日期）：…返回…”并附响应片段；文档错误用 `<!-- Gap: … -->` 标注并升到 SKILL.md。
