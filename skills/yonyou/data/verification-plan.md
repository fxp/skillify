# yonyou 验证计划（拿到凭证后执行）

前提：一个 YonBIP 公有云**测试租户**（不要用生产）、一个企业自建应用的 appKey / appSecret，并在「API 授权」勾选：
组织管理、客户信息、供应商信息、物料信息、采购订单、销售订单、凭证 这几个末级分类；再在该租户建好测试用的组织、客户、供应商、物料、账簿。
Key 只走环境变量 `YONBIP_TENANT_ID` / `YONBIP_APP_KEY` / `YONBIP_APP_SECRET`，结束后全仓库 `grep` 前 8 位。
每条结果按「验证日期 + 做了什么 + 原始响应片段」写回对应 reference，文档错误升到 SKILL.md。

## P0 —— 不通这几条，整份 skill 的示例都跑不起来

| # | 要验证的结论 | 怎么测 | 判定 / 写回 |
| --- | --- | --- | --- |
| 1 | 数据中心查询对真实租户返回 `"00000"` 与两个域名，域名已含 `/iuap-api-auth`、`/iuap-api-gateway` | `GET apigateway.yonyoucloud.com/open-auth/dataCenter/getGatewayAddress?tenantId=$YONBIP_TENANT_ID` | 记录真实 gatewayUrl 形态；`auth-and-gateway.md` §2 |
| 2 | 签名：`appKey<v>timestamp<v>`、HmacSHA256、Base64、URL 编码一次即可取到 token | `auth-and-gateway.md` §3 的 Python | 拿到 token 即通过 |
| 3 | timestamp 用**秒**是否也被接受；时间戳偏差多大被拒 | 同上，分别传秒、毫秒−10 分钟、毫秒−1 小时 | 解决「毫秒 vs 秒」⚠；记录错误码 |
| 4 | 签名二次编码（`%252F`）/ 未编码（含 `/`、`+`）是否被接受 | 手工拼三种 URL | 写进 §3 注意事项 |
| 5 | token 放 header（`access_token:` 或 `Authorization: Bearer`）是否被接受 | 调 `vendor/list` | 写进 §5 |
| 6 | 新 token 是否真含特殊字符、不编码直接拼 URL 会怎样 | 打印 token，分别编码 / 不编码调用 | §3 / §5 |
| 7 | 签名错 / appSecret 错 / 时间戳过期时 token 接口的错误码（探测只见过 `10018`） | 故意制造 | `errors-and-limits.md` §4 |
| 8 | 各业务接口成功时 `code` 是字符串 `"200"` 还是数字 | 每个 reference 的列表接口各调一次 | SKILL「当前事实」 |

## P1 —— 写接口与幂等（成本：在测试租户产生少量单据，测完删除）

| # | 结论 | 怎么测 |
| --- | --- | --- |
| 9 | 采购订单 `singleSave_v1` 的真正最小必填集；金额不自洽时报错还是重算 | 按 §4 示例建一张，逐个去掉字段；改错一个金额 |
| 10 | 重复提交码是 `10004` 还是 `100004`；1 小时内重放是否返回同结果 | 同一 `resubmitCheckKey` 连调两次；隔 1 小时再调 |
| 11 | `resubmitCheckKey` 超过 32 位的行为 | 传 33 位 |
| 12 | 凭证 `addVoucher`（无 data 外壳）的幂等键放哪：`businessId`？顶层 `resubmitCheckKey`？ | 同一 businessId 连调两次 |
| 13 | 销售订单 `orderPrices!currency` 扁平键 vs 嵌套对象哪个生效 | 两种写法各建一张 |
| 14 | 客户 `newBatchDetail`、物料 `batchdetailnew` 的 body 是对象还是数组 | 两种都试 |
| 15 | 多语言写错（`zh_CN` 传给要 `simplifiedName` 的接口）是报错还是静默丢名称 | 客户保存用错写法 |
| 16 | 批量接口部分失败时 `messages` 的真实结构（数组 / 字符串 / 对象数组） | 供应商 batchSaveV2 一条对一条错 |
| 17 | 采购订单删除不带 `pubts` / 带旧 `pubts` 的行为 | |
| 18 | 凭证删除对已审核凭证的行为；是否真的没有审核 / 记账 OpenAPI | 在 API 文档搜索 + 调用 |
| 19 | null 入参透传（2025-03-15 公告）对修改接口的实际影响 | 修改时传某字段为 null |

## P1 —— 事件推送（需要一个公网回调地址，例如临时隧道）

| # | 结论 | 怎么测 |
| --- | --- | --- |
| 20 | 验签算法到底是 A / B / C 哪种（`events.md` §3） | 订阅时收 `CHECK_URL`，三种都算，看哪个等于 signature |
| 21 | AES key 派生与 PKCS#7 块大小 32 对自建应用是否成立；明文尾部是 appKey | 解密 CHECK_URL |
| 22 | 应答需要加密 JSON 还是明文 `success` | 两种都试，看是否被重推 |
| 23 | 业务事件的外层结构：业务数据在哪个字段 | 订阅 `st_purchaseorder_audit`、`GL_VOUCHER_EVENT_ADD_AFTER`，审核一张单 / 建一张凭证 |
| 24 | 真实推送的 Content-Type、重试间隔 | 日志 |

## P2 —— 限流与杂项

| # | 结论 | 怎么测 |
| --- | --- | --- |
| 25 | 超过「免费调用次数」（销售订单 60/分钟）返回什么码、是否计费 | 小心：只在测试租户、短时间内打 70 次 `voucherorder/list` |
| 26 | `querytree` 是否分页、大租户返回规模 | |
| 27 | `orgtype` / `isEnd` 在各组织接口里的真实类型与取值 | |
| 28 | SDK 的 `setEnv` / `host_url` 生产环境该传什么，是否内部做数据中心查询 | **需要从用友下载 Python whl / Java jar 才能看源码**，本次按规矩未下载 |
| 29 | ISV：新生态应用是否仍需要 `suiteTicket` | 需 ISV 账号 |

## 需要资料包才能确认的点（本次按规矩未下载）

- Python SDK `yonbip_open_api_sdk` / `yonbip_open_event_sdk`（whl，不在 PyPI）：`token_opt.opt_self_token` 用秒还是毫秒、签名编码方式、事件解密实现。
- Java SDK `yonbip-open-api-sdk-1.0.0-RELEASE.jar`：`EventParamDecrypt.selfAppParamDecrypt` 的 AES key 来源。
- corp-demo 的 `PushController.java`、`AppController.java` 可以网页浏览，但本次只看了 isv-demo 的加解密三个文件；下次可补看 corp-demo 版本核对自建应用差异。

## 探测阶段已知的违规 / 偏差

- `vendor/list` 被调用 4 次（超出每接口 ≤3 次 1 次），见 `probe-log.md`。
