# 电脑网站支付、手机网站支付、APP 支付

> 内容整理自 opendocs.alipay.com：open/00dn7j / 00dn7k / 028r8t（电脑网站支付产品介绍 / 快速接入 / alipay.trade.page.pay）、
> 00f7nf / 00f7nh / 02ivbs / 00f7nn / 00f7nk / 00f7nm（手机网站支付）、00dn73 / 01dcc0 / 02e7gq / 00iki4（APP 支付）、
> common/0i2kxr（自行实现页面跳转接口）、02kdne（pageExecute 生成 URL）、open-v3/065bsc（v3 SDK pageExecute / sdkExecute）。
> 抓取于 2026-09-11。**未用真实凭证验证**；返回、行为描述均为「文档原文，未实测」，另有标注的除外。

## 目录

1. [三个产品的共同点：服务端只「签名」，不「下单」](#1-三个产品的共同点服务端只签名不下单)
2. [电脑网站支付 alipay.trade.page.pay](#2-电脑网站支付-alipaytradepagepay)
3. [手机网站支付 alipay.trade.wap.pay](#3-手机网站支付-alipaytradewappay)
4. [APP 支付 alipay.trade.app.pay](#4-app-支付-alipaytradeapppay)
5. [三者公共的业务参数](#5-三者公共的业务参数)
6. [pageExecute / sdkExecute 在各 SDK 里的写法](#6-pageexecute--sdkexecute-在各-sdk-里的写法)
7. [出错时看到的是什么](#7-出错时看到的是什么)

---

## 1. 三个产品的共同点：服务端只「签名」，不「下单」

| 产品 | method | `product_code` | 服务端 SDK 方法 | 服务端产出 | 交给谁 |
|---|---|---|---|---|---|
| 电脑网站支付 | `alipay.trade.page.pay` | `FAST_INSTANT_TRADE_PAY`（「目前电脑支付场景下仅支持」） | `pageExecute` | HTML form（POST）或 URL（GET） | 用户浏览器 |
| 手机网站支付 | `alipay.trade.wap.pay` | `QUICK_WAP_WAY` | `pageExecute` | 同上 | 手机浏览器 |
| APP 支付 | `alipay.trade.app.pay` | `QUICK_MSECURITY_PAY`（示例值；参数表标「可选」） | `sdkExecute` | 签名串 `orderStr` | 商户 APP → 支付宝客户端 SDK |

**关键认知**（00dn7k、02e7gq，文档原文）：

- 对页面跳转类 API，「SDK 不会也无法像系统调用类 API 一样自动请求支付宝并获得结果」，而是生成完整的 form HTML（含自动提交脚本）或 URL。**不要对 page.pay / wap.pay 用 `execute`，也不要自己 `requests.post` 到网关再解析 JSON**——拿不到交易号，交易是用户在浏览器里提交后才创建的。
- APP 支付的 `alipay.trade.app.pay` 是「签名数据准备接口」：服务端生成 `orderStr`，**支付宝侧此时还没有交易**（01dcc0 时序图：「1.6 支付预下单（此时交易未创建）」）。
- 所以这三类下单**没有同步的 `trade_no`**；支付结果只能靠异步通知 + `alipay.trade.query`（见 [notify-and-verify.md](notify-and-verify.md)）。
- **私钥必须在服务端**。APP 支付不要把签名放到客户端（00dn7d：「避免私钥设置在客户端导致泄漏、资损」）。
- **v3 没有这三个接口的路径**：官方 openapi.yaml 中无 `/v3/alipay/trade/page/pay`、`wap/pay`、`app/pay`。v3 SDK 调用它们时仍用 `pageExecute` / `sdkExecute`，「无 request 类，需组装 map 或 json；需传入 api 的方法名（method）」（065bsc），产出的仍是 gateway.do 协议的表单 / 签名串。
  ⚠ 文档自相矛盾：v3「基本原则」页（054oog）说「页面重定向接口，例如手机网站支付，请求处理成功，支付宝返回 302 跳转到用户支付页面」，暗示存在 v3 形态的页面接口，但描述文件里没有对应路径。按「这三类仍走旧网关协议」实现。

---

## 2. 电脑网站支付 alipay.trade.page.pay

**Endpoint**: `https://openapi.alipay.com/gateway.do`（由浏览器提交，`method=alipay.trade.page.pay`）
**用途**: PC 网页下单，用户跳到支付宝收银台扫码或登录账号付款。

**公共参数里的额外项**：`return_url`（付款后浏览器跳回的地址，可选）、`notify_url`（异步通知，**不传就收不到支付通知**）。

**关键业务参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `out_trade_no` | string(64) | 是 | 商户订单号 |
| `total_amount` | price(11) | 是 | **元**，两位小数，`[0.01, 100000000]`，「金额不能为 0」 |
| `subject` | string(256) | 是 | 不能含 `/ = &` |
| `product_code` | string(64) | 是 | 固定 `FAST_INSTANT_TRADE_PAY` |
| `qr_pay_mode` | string(2) | 否 | PC 扫码方式：`0` 简约前置（iframe ≥600×300）、`1` 前置（iframe ≥300×600）、`3` 迷你前置（≥75×75）、`4` 可定义宽度嵌入式、`2` 跳转模式 |
| `qrcode_width` | number(4) | 否 | 仅 `qr_pay_mode=4` 有效 |
| `time_expire` | string(32) | 否 | 绝对超时 `yyyy-MM-dd HH:mm:ss`，范围 1m~15d |
| `timeout_express` | string | 否 | 相对超时；与 `time_expire` 都传时以 `time_expire` 为准。沙箱页称生产默认 15 天 |
| `goods_detail` | array | 否 | 商品明细 |
| `integration_type` / `request_from_url` | string | 否 | `ALIAPP`（支付宝钱包内）等；用户中途取消返回 `request_from_url` |
| `passback_params` | string(512) | 否 | 公用回传参数，**需 UrlEncode**，只在异步通知里原样返回 |
| `extend_params.hb_fq_num` / `hb_fq_seller_percent` | string | 否 | 花呗分期（沙箱不支持） |

⚠ 文档自相矛盾：`qr_pay_mode` 描述写了 `2：订单码-跳转模式`，但【枚举值】清单只列 `0、1、3、4`，没有 `2`。

**示例请求（Python，官方旧版 SDK）**

```python
from alipay.aop.api.domain.AlipayTradePagePayModel import AlipayTradePagePayModel
from alipay.aop.api.request.AlipayTradePagePayRequest import AlipayTradePagePayRequest
# client 初始化见 signing-and-protocols.md 第 3 节

m = AlipayTradePagePayModel()
m.out_trade_no = "20150320010101001"
m.total_amount = "88.88"                     # 元
m.subject = "Iphone6 16G"
m.product_code = "FAST_INSTANT_TRADE_PAY"
req = AlipayTradePagePayRequest(biz_model=m)
req.notify_url = "https://api.example.com/alipay/notify"
req.return_url = "https://www.example.com/pay/result"
html_form = client.page_execute(req)                     # 默认 POST：返回 <form>…<script>submit</script>
pay_url = client.page_execute(req, http_method="GET")    # GET：返回可 302 的支付宝 URL
# Web 框架里：return html_form（Content-Type: text/html）或 redirect(pay_url)
```

`page_execute(request)` / `page_execute(request, http_method="GET")` 的写法来自 common/02kdne。
⚠ 文档未说明：Python SDK 中 `AlipayTradePagePayModel` / `AlipayTradePagePayRequest` 的类名与 `req.notify_url` / `req.return_url` 属性名——Python 文档只演示了 `AlipayTradeCreateRequest`；此处按 Java 类名规则（`AlipayTradePagePayRequest`、`setNotifyUrl`/`setReturnUrl`）推断，写代码前请在已安装的包里核对。

**文档给出的 form 输出（028r8t 响应示例）**

```html
<form name="punchout_form" method="post" action="https://openapi.alipay.com/gateway.do?charset=UTF-8&method=alipay.trade.page.pay&format=json&sign=...&version=1.0&app_id=...&sign_type=RSA2&timestamp=...">
<input type="hidden" name="biz_content" value="{...}">
<input type="submit" value="立即支付" style="display:none" >
</form>
<script>document.forms[0].submit();</script>
```

**同步跳转**：用户付款后浏览器 GET 跳回 `return_url`，带公共参数（`app_id`、`method=alipay.trade.page.pay.return` 类、`sign_type`、`sign`、`charset`、`timestamp`、`version`）和业务参数（`out_trade_no`、`trade_no`、`total_amount`、`seller_id`）。「支付结果必须以异步通知或查询接口返回为准，不能依赖同步跳转。」
（字段表抄自手机网站支付附录 00f7nh；⚠ 文档未单独给出电脑网站支付的回跳参数表。）

**其它注意**（00dn7k 原文）
- `partnerId + out_trade_no` 唯一对应一笔单据；重复的 `out_trade_no` 会关联到原单据，基本信息一致时以原单据为准支付。
- 超时关单通常靠 `timeout_express` / `time_expire`，也可以主动 `alipay.trade.close`。
- 退款周期 12 个月。

---

## 3. 手机网站支付 alipay.trade.wap.pay

**Endpoint**: `https://openapi.alipay.com/gateway.do`（由手机浏览器提交，`method=alipay.trade.wap.pay`）
**用途**: 移动端 H5 下单；已装支付宝的手机会唤起支付宝 App，否则走 H5 收银台。

**关键业务参数**：同第 5 节，另有

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `product_code` | string(64) | 是 | `QUICK_WAP_WAY` |
| `total_amount` | price(9) | 是 | 元，两位小数 |
| `quit_url` | string(400) | 否 | 用户付款中途退出返回商户网站的地址 |
| `time_expire` | string(32) | 否 | 绝对超时，1m~15d |
| `passback_params` | string(512) | 否 | 需 UrlEncode；只在异步通知返回 |

⚠ 文档自相矛盾：`total_amount` 最大长度电脑网站支付页写 price(11)，手机网站支付页写 price(9)，取值范围都写 `[0.01, 100000000]`（9 位长度装不下 `100000000.00`）。

**同步跳转参数**（00f7nh 附录）：公共参数 `app_id`、`method`（示例 `alipay.trade.wap.pay.return`）、`sign_type`、`sign`、`charset`、`timestamp`、`version`；业务参数 `out_trade_no`、`trade_no`、`total_amount`、`seller_id`。
iOS 唤起支付宝客户端付款完成后**不会自动跳回** `return_url`。

**扩展**
- 商户 APP 内嵌 H5 时，官方推荐「手机网站支付转 Native 支付」（00f7nn）或拦截 `alipays://` 协议唤起支付宝 App（00f7nk）以提高成功率。本 skill 不展开，文档见 open/00f7nn、00f7nk。
- 旧版手机网站支付仍可用，但「不建议与新版混用」（00f7nm）。

**沙箱**：不支持浏览器内付款，要唤起沙箱 App；同时装了正式版支付宝会默认唤起正式版而报错。

---

## 4. APP 支付 alipay.trade.app.pay

**Endpoint**: 不直接请求；服务端用 `sdkExecute` 生成 `orderStr`，商户 APP 调支付宝客户端 SDK 发起支付。

**流程**（01dcc0）
1. APP 请求商户服务端下单；
2. 服务端调 `alipay.trade.app.pay`（`sdkExecute`）得到 `orderStr`，返回给 APP；
3. APP 调支付宝客户端 SDK 的支付接口，传入 `orderStr`；
4. 支付宝 App 收银台完成支付，SDK 同步返回 `resultStatus`（见 [notify-and-verify.md](notify-and-verify.md) 第 9 节）；
5. 支付宝服务端向 `notify_url` 发异步通知；没收到就 `alipay.trade.query`。

**关键业务参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `out_trade_no` | string(64) | 是 | 商户订单号 |
| `total_amount` | price | 是 | 元 |
| `subject` | string(256) | 是 | 不能含 `/ = &` |
| `product_code` | string(64) | 否 | 「销售产品码，商家和支付宝签约的产品码」，示例 `QUICK_MSECURITY_PAY` |
| `time_expire` | string(32) | 否 | `yyyy-MM-dd HH:mm:ss` |
| `passback_params` | string | 否 | 需 UrlEncode |
| `notify_url`（公共参数） | string(256) | 否 | 异步通知地址 |

⚠ 文档未说明：APP 支付 `product_code` 不传时的默认值。

**`orderStr` 长什么样**（02e7gq 响应示例）：一个已 URL 编码的 `key=value&…` 串，包含 `app_id`、`biz_content`、`charset`、`method`、`sign_type`、`sign`、`timestamp`、`version`、`notify_url` 等。**原样**交给客户端 SDK，客户端不要再解析、重排或二次编码。

**示例（Java，文档原文 02e7gq）**

```java
AlipayTradeAppPayResponse response = alipayClient.sdkExecute(request);
String orderStr = response.getBody();   // 直接下发给 APP
```

**示例（Python）**

```python
from alipay.aop.api.domain.AlipayTradeAppPayModel import AlipayTradeAppPayModel
from alipay.aop.api.request.AlipayTradeAppPayRequest import AlipayTradeAppPayRequest
m = AlipayTradeAppPayModel()
m.out_trade_no = "20150320010101001"; m.total_amount = "9.00"; m.subject = "大乐透"
m.product_code = "QUICK_MSECURITY_PAY"
req = AlipayTradeAppPayRequest(biz_model=m)
req.notify_url = "https://api.example.com/alipay/notify"
order_str = client.sdk_execute(req)
```

⚠ 文档未说明：Python SDK 的 `sdk_execute` 方法名、`AlipayTradeAppPay*` 类名——文档只给了 Java / C# / PHP / Node.js 示例（Node.js 为 `alipaySdk.sdkExec("alipay.trade.app.pay", {...})`）。写代码前在已安装的 `alipay-sdk-python` 里核对。

**客户端 SDK**：Android 走 Maven（`00dn75`）、iOS 走 CocoaPods / 手动（`00dn76`）、鸿蒙 ohpm（`0f71b5`）；iOS 建议配置 Universal Links（SDK ≥ 15.8.12，`0b9qzi`）。本 skill 不展开客户端集成细节。
**沙箱**：只支持 Android；调支付前 `EnvUtils.setEnv(EnvUtils.EnvEnum.SANDBOX)`，生产必须删除。

---

## 5. 三者公共的业务参数

| 参数 | 规则（文档原文） |
|---|---|
| `total_amount` | **单位元**，精确到小数点后两位，`[0.01, 100000000]`。不是分，不能为 0 |
| `subject` | 不可使用 `/`、`=`、`&` 等特殊字符 |
| `out_trade_no` | ≤64 字符，字母 / 数字 / 下划线；商户端不重复 |
| `timeout_express` | `1m`～`15d`，`m`/`h`/`d`，`1c` 表示当天 0 点关闭；**不接受小数**（`1.5h` 写 `90m`） |
| `time_expire` | `yyyy-MM-dd HH:mm:ss`；与 `timeout_express` 同时传以它为准 |
| `passback_params` | 必须 UrlEncode；只在异步通知里回来 |
| `business_params.mc_create_trade_ip` | 用户端外网 IP；无代理时直接取建连 IP，**不要信 X-Forwarded-For**（05zrno 摘要） |
| 自定义字段 | 「传入非接口文档中的参数是无效的，并且可能会导致请求被拦截或其它异常」；参数值里不要出现 `body`、`subject`、`out_trade_no`、`total_fee` 等支付宝关键 key，否则可能被判 `isv.suspected-attack` |

---

## 6. pageExecute / sdkExecute 在各 SDK 里的写法

来源：common/02kdne（文档原文）。

| 语言 | 生成 form（POST，默认） | 生成 URL（GET） |
|---|---|---|
| Java | `alipayClient.pageExecute(req).getBody()` | `alipayClient.pageExecute(req, "GET").getBody()` |
| PHP | `$aop->pageExecute($request)` | `$aop->pageExecute($request, "GET")` |
| .NET | `client.pageExecute(request)` | `client.pageExecute(request, "", "GET")`（**GET 必须大写，放第三个参数**） |
| Python | `client.page_execute(request)` | `client.page_execute(request, http_method="GET")` |
| Node.js | `AlipayFormData`（默认 post） | `formData.setMethod('get')` |

- 「Alipay Easy SDK（新版）目前只支持输出 form 表单，不支持打印出 url 链接」。
- APP 支付用 `sdkExecute`（Java）/ `sdkExec`（Node.js）。

---

## 7. 出错时看到的是什么

**无凭证探测（2026-09-11）**：用伪造 `app_id=test` 以 GET 方式请求 `alipay.trade.page.pay` 的跳转 URL，网关返回 **HTTP 200、`Content-Type: text/html;charset=GBK`** 的 HTML 错误页，正文（GBK 解码）为「调试错误，请回到请求来源地，重新发起请求。错误代码 invalid-app-id 错误原因: 无效的AppID参数」。

含义：
- 页面跳转类接口的参数 / 签名错误**不会**回到你的服务端，而是**展示给用户**。上线前务必在沙箱用真实浏览器走一遍。
- 这个页面是 **GBK 编码**的；如果你在服务端抓它调试，按 GBK 解码。
- 对 APP 支付，错误体现为客户端 `resultStatus != 9000`，`result` 里带 `sub_code` / `sub_msg`（01dcc0）。
