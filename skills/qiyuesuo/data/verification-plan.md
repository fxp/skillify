# 契约锁 skill 验证计划（拿到沙箱凭证后执行）

前提：开放平台申请接入 → 开启沙箱，拿到**测试环境** AppToken / AppSecret（只放环境变量 `QYS_APP_TOKEN` / `QYS_APP_SECRET`），
云平台 `cloud.qiyuesuo.cn` 里有一个默认业务分类、一枚正常状态的公章。测试环境余额为 0 时发起合同会失败，需先联系客服充值。
全程只用测试环境 `https://openapi.qiyuesuo.cn`；测试产生的合同用 `/v2/contract/invalid` 删除 / 撤回。验证完 `grep -rn "<AppToken 前 6 位>"` 全仓库。

## P0 鉴权（决定所有示例代码对不对）

| # | 要验证的结论（出处） | 怎么测 | 判定 |
| --- | --- | --- | --- |
| 1 | 签名 = `md5(AppToken+AppSecret+ts+nonce)` 小写 hex（auth §3） | `GET /company/platforminfo` 用 §4 封装调用 | 返回 `code 0` / `responseCode 00000000` |
| 2 | 大写 hex 是否也被接受 | 同上，把签名 `.upper()` | 记录报错原文 |
| 3 | 缺 `x-qys-open-nonce` 是否被拒（文档示例只有三个头）（auth §3 ⚠） | 同上，去掉 nonce 头 | 记录；若被拒，把接口页示例的三头写法升为 Gap |
| 4 | 同一 nonce 10 分钟内复用被拒 | 连续两次用同一 ts+nonce | 记录错误码 |
| 5 | 时间戳偏差窗口（⚠ 文档未说明） | ts 分别偏 1、5、10、30 分钟 | 找出拒绝阈值与报错原文 |
| 6 | 成功响应是否同时带 `code` 与 `responseCode`，HTTP 是否 200（auth §8） | 任一成功调用，打印完整响应 | 更新 SKILL.md 当前事实"成功判定" |
| 7 | 签名错误时的错误码（不是 442 时是什么） | 正确 token + 错误 secret | 记录，补进 errors §2 |
| 8 | HmacSha256 鉴权的请求头与规则（auth §7 ⚠） | 需要新版 SDK 源码或契约锁答复；本次未下载 SDK 包 | 有资料后补 auth §7 |

## P1 合同主流程（contracts.md / signing.md）

| # | 结论 | 怎么测 | 判定 |
| --- | --- | --- | --- |
| 9 | `send` 默认值（⚠） | 草稿接口不传 `send` | 看返回 `status` 是 DRAFT 还是 SIGNING |
| 10 | Action 字段名 `corpSealIds`/`corpOperators` vs `sealId`/`operators`（contracts §2 ⚠） | 两种写法各建一份草稿，回查详情 `actions[].sealId` | 哪种生效；另一种是否静默忽略（最危险） |
| 11 | multipart 下 `stampers` 编码（contracts §3 ⚠） | addbyfile 传 `stampers` 为 JSON 字符串 | 回查详情 `queryLocation=true` 看位置是否生效 |
| 12 | 草稿态重复 bizId 覆盖（contracts §2） | 同 bizId 建两次草稿 | 返回同一 id 还是新 id |
| 13 | 发起时签署位置必须用 actionId / signatoryId 绑定（signing §3） | 公司位置不带 actionId | 记录报错 |
| 14 | 坐标原点左下角、`page=-1` 最后一页（signing §3） | 发起后下载 PDF 目测印章位置 | 与描述一致 |
| 15 | `companysign` 在没轮到时报 `1107` / `11011107`（signing §4） | 公章节点前放一个审批节点 | 记录错误码是 4 位还是 8 位 |
| 16 | pageurl `expireTime` + `DAYS` 生效；默认 30 分钟还是 10 分钟（signing §6 ⚠） | 各生成一个链接，过期后打开 | 更新 signing §6 |
| 17 | `/v2/contract/invalid` 对 DRAFT / SIGNING / COMPLETE / RECALLED 的行为（signing §9 ⚠） | 各状态各一份 | 回查详情状态 |
| 18 | add / edit 签署方的正确路径（`/add`、`/edit` vs 示例 `/modify`）（signing §8 ⚠） | 两条路径各调一次 | 哪条 404 / 报错，升 Gap |
| 19 | `/v2/contract/download` 默认 ZIP；`needCompressForOneFile=false` 返回 PDF（contracts §9） | 看 Content-Type | 更新 |
| 20 | 下载失败时响应格式（⚠） | 用不存在的 documentId 下载 | JSON 还是空流 |

## P1 回调（callbacks.md，全部未实测，价值最高）

| # | 结论 | 怎么测 | 判定 |
| --- | --- | --- | --- |
| 21 | 合同回调是 form-urlencoded，字段 `contractId/callbackType/contractStatus/...` | 用 `callbackUrl` 指向一个记录原始请求的临时地址，走完一份合同 | 保存原始 headers + body |
| 22 | `callbackType` 与 `contractStatus` 的真实取值（⚠ 文档无列表） | 同上，覆盖发起、签署、退回、撤回、完成、作废 | 补进 callbacks §2 |
| 23 | 合同回调要求的返回体（⚠） | 接收端分别回 `{"code":0}`、`success`、HTTP 500 | 看是否重推 |
| 24 | 合同回调有无签名头 / 签名参数（⚠） | 看 #21 的原始 headers 和 query | 补验签说明 |
| 25 | 开启加密后密文所在字段、ECB 零填充是否正确、CBC 的 IV（⚠） | `/company/token/update/callback` 开 `AES_ECB` 再走一份合同，用 callbacks §3 的函数解密；再换 `AES_CBC` | 更新 §3 |
| 26 | 业务分类回调与应用回调的优先级（⚠） | 两处配不同地址 | 看推到哪 |
| 27 | 个人签名授权回调 `secretKey` 是哪个（⚠） | 走一次个人签名授权 | 用 callbackSecretKey / AppSecret 分别验签 |

## P2 其他

| # | 结论 | 怎么测 |
| --- | --- | --- |
| 28 | 企业认证查询 / 回调的 status 口径（seals §6 ⚠） | 沙箱里给一个测试公司发认证链接，不提交 → 查询 |
| 29 | `/v2/seal/remove` 是 GET（seals §5） | 对一枚停用的测试章调 GET |
| 30 | 频次限制与 `11990006 接口调用频繁`（errors §6） | 不做压测；只在日志里观察是否出现 |
| 31 | 私有化部署 Base URL 与差异（⚠） | 需要私有化环境，向契约锁确认 |

## 资料包相关（本次按规矩未下载）

- 官方 SDK（Java 4.0.2 / Python 3.4.0 / PHP 3.6.8 / C# 3.4.0 / Go 3.1.5）只在下载中心提供；HmacSha256 规则、AES-CBC 解密方法、合同回调解析类都在 SDK 里，需下载后阅读源码确认 #8、#25。
- 「开放平台API接口调用自主问答解决手册」（PDF，dl.qiyuesuo.com）与「报错响应码以及解决方法汇总」（外部分享链接）未下载，可能包含完整错误码表与回调"操作手册"。
