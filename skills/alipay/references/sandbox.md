# 沙箱环境

> 内容整理自 opendocs.alipay.com：common/097jyh（快速接入）、097jyi（支持的产品范围）、097oft（约束限制）、
> 097l48（环境升级说明）、097pw5（常见问题），open/00ip3n（当面付沙箱）、00dn7o（电脑网站沙箱）、00f7np（手机网站沙箱）、
> 00dn7d（APP 沙箱），open-v3/054oog（v3 接入点），common/0j01km（支付集成 Skill）。抓取于 2026-09-11。
> **未用真实凭证验证。** 标「无凭证探测」的是伪造 `app_id=test` 打出来的真实返回。

## 目录

1. [网关地址：新沙箱 vs 旧沙箱](#1-网关地址新沙箱-vs-旧沙箱)
2. [拿到沙箱应用信息](#2-拿到沙箱应用信息)
3. [沙箱支持哪些收款产品](#3-沙箱支持哪些收款产品)
4. [沙箱与生产的行为差异（按产品）](#4-沙箱与生产的行为差异按产品)
5. [沙箱钱包与测试账号](#5-沙箱钱包与测试账号)
6. [切换生产的检查单](#6-切换生产的检查单)
7. [常见报错](#7-常见报错)

---

## 1. 网关地址：新沙箱 vs 旧沙箱

| 用途 | 地址 | 状态 |
|---|---|---|
| 旧版网关（v2）沙箱 | `https://openapi-sandbox.dl.alipaydev.com/gateway.do` | **当前**（097l48、各产品沙箱页）。无凭证探测（2026-09-11）：伪造 app_id 请求返回 HTTP 200 + `isv.invalid-app-id`，网关存活 |
| v3 沙箱 | `https://openapi-sandbox.dl.alipaydev.com` + `/v3/...` 路径 | 当前（open-v3/054oog）。无凭证探测（2026-09-11）：`POST /v3/alipay/trade/query` 返回 HTTP 400 `invalid-app-id`，路径存活 |
| 消息网关（WebSocket） | `openchannel-sandbox.dl.alipaydev.com` | 当前 |
| 旧沙箱网关 | `https://openapi.alipaydev.com/gateway.do` | **已停止维护**；旧沙箱 APPID、账号在新沙箱都不能用 |
| 生产 | `https://openapi.alipay.com/gateway.do` / `https://openapi.alipay.com` | — |

<!-- Gap: 旧沙箱 https://openapi.alipaydev.com/gateway.do 仍出现在官方 Python SDK 文档（common/02np8q）示例中；无凭证探测（2026-09-11）该域名 TLS 证书已过期（curl: (60) certificate has expired） -->
<!-- Gap: 官方 v3 描述文件 openapi.yaml 的 servers 沙箱写 http://openapi.sandbox.dl.alipaydev.com；无凭证探测（2026-09-11）http 返回 404 Not Found，https 报证书主机名不匹配（no alternative certificate subject name matches target host name） -->
**无凭证探测（2026-09-11）发现两处文档错误：**
1. 官方 Python SDK 文档（common/02np8q）所有示例 `server_url` 仍是旧沙箱 `https://openapi.alipaydev.com/gateway.do`——该域名 **TLS 证书已过期**，照抄连不上。
2. 官方 v3 描述文件 `openapi.yaml` 的 `servers` 沙箱条目是 `http://openapi.sandbox.dl.alipaydev.com`（点号、http）——http 返回 **404**，https **证书主机名不匹配**。用 OpenAPI Generator / Postman 导入 openapi.yaml 时要手动把沙箱 server 改成 `https://openapi-sandbox.dl.alipaydev.com`（连字符）。

---

## 2. 拿到沙箱应用信息

来源：common/097jyh（文档原文，未实测）。

1. 从开放平台进入沙箱控制台 `https://open.alipay.com/develop/sandbox/app`。
2. 新版沙箱会分配一个网页/移动应用和一个小程序应用，**默认启用系统密钥**；在「公钥模式 → 查看」里可以直接复制**应用私钥**和**支付宝公钥**。
3. 需要证书模式时点「启用」，下载应用私钥、应用公钥证书、支付宝公钥证书、支付宝根证书。
4. 也可以「自定义密钥」上传自己生成的密钥 / CSR。CSR 的「组织/公司」：2020-07-24 后获取的沙箱账号填**沙箱商家账号**（如 `xxx@sandbox.com`），之前的填「沙箱环境」。
5. 沙箱与生产的 APPID、密钥、支付宝公钥**完全独立**。

沙箱**无需商业资质、无需签约开通产品**即可调用收款接口。

另：支付宝官方「支付集成 Skill」（common/0j01km）称使用它时会「自动分配快速沙箱和测试账号」，无需登录支付宝账号。⚠ 文档未说明该快速沙箱的网关与本节是否相同。

---

## 3. 沙箱支持哪些收款产品

来源：common/097jyi。

| 产品 | 沙箱 | 限制 |
|---|---|---|
| 当面付 | 支持 | 不支持小程序应用类型 |
| 订单码支付 | 支持 | — |
| 电脑网站支付 | 支持 | — |
| 手机网站支付 | 支持 | — |
| APP 支付 | 支持 | SDK 暂不支持鸿蒙 |
| JSAPI 支付、预授权支付、商家分账、转账到支付宝账户 | 支持 | 本 skill 不覆盖 |

各产品下的查询、退款、退款查询、关闭、撤销、账单下载地址接口在沙箱都支持；**退款冲退完成通知 `alipay.trade.refund.depositback.completed` 不支持**（沙箱不支持银行卡支付）。

**按接口的沙箱支持矩阵**（open/00ip3n、00dn7o、00f7np、00dn7d，文档原文，未实测）

| 接口 | 当面付 | 电脑网站 | 手机网站 | APP | 沙箱注意 |
|---|---|---|---|---|---|
| `alipay.trade.pay` | 支持 | — | — | — | 2000 元以上需输密码 |
| `alipay.trade.page.pay` | — | 支持 | — | — | — |
| `alipay.trade.wap.pay` | — | — | 支持 | — | 不支持浏览器内付款 |
| `alipay.trade.app.pay` | — | — | — | 支持 | 仅 Android |
| `alipay.trade.query` | 支持 | 支持 | 支持 | 支持 | — |
| `alipay.trade.refund` | 支持 | 支持 | 支持 | 支持 | 金额须等于支付金额，每笔只能调一次 |
| `alipay.trade.fastpay.refund.query` | 支持 | 支持 | 支持 | 支持 | — |
| `alipay.trade.close` | 支持 | 支持 | 支持 | 支持 | — |
| `alipay.trade.cancel` | 支持 | — | — | — | — |
| `alipay.data.dataservice.bill.downloadurl.query` | 支持 | 支持 | 支持 | 支持 | 只返回模板账单 |
| `alipay.trade.refund.depositback.completed`（通知） | 不支持 | 不支持 | 不支持 | 不支持 | 沙箱无银行卡支付 |

订单码支付（`alipay.trade.precreate`）在 097jyi 的产品列表中标为支持，⚠ 文档未给出订单码支付单独的沙箱接口矩阵。

---

## 4. 沙箱与生产的行为差异（按产品）

通用（097oft、各产品沙箱页，文档原文，未实测）：

- **非 100% 保真**：接口实际响应以生产为准，沙箱调通后仍需生产验收。
- **数据隔离**：沙箱返回的用户 ID 等在生产不存在，不能混用。
- **只支持余额支付**：不支持银行卡、余额宝、花呗、花呗分期、优惠核销。
- **会扣手续费**，但比例不代表生产。
- 建议「只传必传参数测试」，部分参数只对生产兼容。

| 差异项 | 沙箱 | 生产 |
|---|---|---|
| 退款 | **退款金额必须等于支付金额；每笔交易无论成败只能调一次退款** | 可多次部分退款 |
| `timeout_express` / `time_expire` | 不可超过当前时间 **15 小时** | 当面付默认 3h；电脑网站 / 手机网站 / APP 默认 15 天（最大不超过合约约定） |
| 对账单 | 只做模拟调用，下载的是模板，没有实际数据 | 真实账单 |
| 付款码支付输密码阈值 | 单笔 **2000 元**以上 | 单笔 **1000 元**以上 |
| `ext_user_info`（指定买家） | 不支持 / 无法校验 | 支持 |
| `extend_params` 花呗分期 | 不支持 | 支持 |

产品特有：
- **当面付**：条码付的 `auth_code` 要从**沙箱钱包**的付款码获取；扫码付用沙箱钱包扫一扫。
- **手机网站支付**：沙箱不支持浏览器内付款，要唤起沙箱 App；手机上同时装了正式版和沙箱版支付宝时，默认唤起**正式版**，会因数据不通而报错。系统默认浏览器（鸿蒙）无法唤起沙箱 App。
- **APP 支付**：只支持 Android；客户端在调用支付前调 `EnvUtils.setEnv(EnvUtils.EnvEnum.SANDBOX)` 切到沙箱，**生产必须删掉这行**。纯客户端 Demo 测试建议密钥用 PKCS8，但上线必须把签名放服务端（私钥不能进客户端）。

---

## 5. 沙箱钱包与测试账号

- 新沙箱默认给每个开发者 1 个商家账号 + 1 个买家账号，并默认充值；**不支持自定义创建账号、不支持配置手机号**（097oft）。
- 沙箱支付宝 App 从沙箱控制台左侧「沙箱工具」下载；**只支持 Android**（不支持 Android 6 及以下、Android 14 及以上），**不支持 iOS、不支持模拟器**，鸿蒙受限。
- 沙箱 App 只有：登录/登出、切换账号、扫一扫、付钱、授权管理、账单、余额。
- ⚠ 文档自相矛盾：097oft 说「沙箱仅支持 JSAPI 支付在小程序开发者工具 IDE 调试」，097l48 与 097pw5 说「沙箱暂无法支持小程序开发者工具 IDE 调试」。（与本 skill 的网页 / APP 收款无关。）

---

## 6. 切换生产的检查单

| 项 | 沙箱 | 生产 |
|---|---|---|
| 网关 | `https://openapi-sandbox.dl.alipaydev.com/gateway.do` | `https://openapi.alipay.com/gateway.do` |
| v3 host | `https://openapi-sandbox.dl.alipaydev.com` | `https://openapi.alipay.com` |
| APPID / 应用私钥 / 支付宝公钥（或三张证书） | 沙箱控制台 | 生产应用「开发设置」 |
| 应用状态 | 不需要上线 | 应用必须**已上线**（否则 `not-online-app`），且已绑定商家账号、已开通对应产品（否则 `ACQ.ACCESS_FORBIDDEN` / `isv.insufficient-isv-permissions`） |
| APP 客户端 | `EnvUtils.setEnv(SANDBOX)` | 删除这行 |
| 退款测试逻辑 | 只能全额一次 | 部分退款要换 `out_request_no` |
| 数据 | 沙箱用户 ID、交易号 | 不可混用 |

建议把这四项都放环境变量：`ALIPAY_GATEWAY`（或 `ALIPAY_V3_HOST`）、`ALIPAY_APP_ID`、`ALIPAY_APP_PRIVATE_KEY`、`ALIPAY_PUBLIC_KEY`，**成组切换**——只换网关不换密钥是最常见的沙箱报错来源。

**成组切换 + 冒烟测试（Python）**：用一个不存在的订单号查询，能拿到业务错误说明网关、APPID、私钥三者匹配。

```python
import os
ENVS = {
    "sandbox": {"gateway": "https://openapi-sandbox.dl.alipaydev.com/gateway.do",
                "v3_host": "https://openapi-sandbox.dl.alipaydev.com", "prefix": "ALIPAY_SANDBOX_"},
    "prod":    {"gateway": "https://openapi.alipay.com/gateway.do",
                "v3_host": "https://openapi.alipay.com", "prefix": "ALIPAY_PROD_"},
}
def load_env(name: str) -> dict:
    e = ENVS[name]; p = e["prefix"]
    return {**e,
            "app_id": os.environ[p + "APP_ID"],
            "app_private_key": os.environ[p + "APP_PRIVATE_KEY"],
            "alipay_public_key": os.environ[p + "PUBLIC_KEY"]}   # 三项与网关一起换

# 冒烟：call_v2("alipay.trade.query", {"out_trade_no": "SMOKE_NOT_EXIST_001"})
#   sub_code == "ACQ.TRADE_NOT_EXIST"      -> 配置正确（文档原文的业务错误码，未实测）
#   sub_code == "isv.invalid-signature"    -> 密钥与网关环境不匹配
#   sub_code == "isv.invalid-app-id"       -> APPID 不属于该环境（无凭证探测已见此返回）
```

---

## 7. 常见报错

来源：common/097pw5（文档原文，未实测）。

| 现象 | 排查 |
|---|---|
| `invalid-app-id` 或 `invalid-signature` | ① 网关是否为 `https://openapi-sandbox.dl.alipaydev.com/gateway.do`；② appId 是否在沙箱控制台列表里；③ 密钥 / 证书是否用的沙箱那一套 |
| 「系统繁忙」 | 仍在用旧沙箱，去控制台右上角「升级沙箱环境」 |
| 沙箱钱包无法登录 | 下载最新沙箱 App，用新沙箱账号登录 |
| `isv.missing-encypt-key`（原文拼写） | 沙箱控制台里给该应用设置了「接口内容加密」相关项，按控制台配置 |
| `checkNotifySign` 返回 false | 同 invalid-signature 排查 |
| 手机网站支付唤起后报错 | 唤起的是正式版支付宝，改用沙箱 App |

**无凭证探测（2026-09-11）**：沙箱网关对伪造 app_id 的返回（`"sub_msg":"无效的AppID参数"`）比生产（带「解决方案」链接）更短，其余结构一致。
