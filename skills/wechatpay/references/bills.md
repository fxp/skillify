# 账单：申请交易账单 / 资金账单，下载与解析

> 来源：`pay.weixin.qq.com/doc/v3/merchant/` 下 4013071227（申请交易账单）、4013071235（申请资金账单）、4013071238（下载账单）、
> 4013071246 / 4013071249（交易账单、资金账单的字段说明）、4013071218（开发指引）、4013071254（FAQ），抓取于 2026-09-11。
>
> **验证状态**：没有用真实凭证调用过。错误码、生成时间、格式描述都是文档原文，未实测。
> 无凭证探测（2026-09-11）：不带 Authorization 调 `GET /v3/bill/tradebill?bill_date=2026-09-10`，返回 401 `SIGN_ERROR`「Http头Authorization值格式错误…」，说明 path 存在。

## 1. 流程：两步，第二步也要签名

```
① GET /v3/bill/tradebill 或 /v3/bill/fundflowbill   （正常签名 + 正常验签）
      → {hash_type: "SHA1", hash_value, download_url}
② GET <download_url>                                （正常签名；应答不带签名头，跳过验签）
      → 账单文件字节流（tar_type=GZIP 时是 gzip 压缩流）→ 自己算 SHA1，和 hash_value 比对
```

- `download_url` **5 分钟内有效**。
- 第二步**必须带 Authorization**，签名串第 2 行是 `download_url` 的 **path + query**（例如 `/v3/billdownload/file?token=xxx`）。
  文档原文：「不得直接在浏览器中访问」。
- 第二步的应答「请求头信息中不包含签名值，因此无需验签」。所以用官方 SDK 自带的 httpclient 下载时会报「验签失败」（FAQ），
  要自己发下载请求。第一步申请账单的应答是正常签名的，照常验签。
- 第二步的错误码（文档原文）：`400 INVALID_REQUEST`（重新走第一步拿新地址），`403 NO_AUTH`（下载账单的商户号和申请账单的商户号不一致）。

## 2. 申请交易账单

**Endpoint**: `GET /v3/bill/tradebill`
**用途**：拿到某一天交易（收款 / 退款）账单的下载地址。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `bill_date` | query | string(10) | 是 | `yyyy-MM-DD` 格式，只能是**三个月内**的日期，**不能是今天** |
| `bill_type` | query | string | 否 | `ALL`（默认）/ `SUCCESS` / `REFUND`，都不含充值退款订单 |
| `tar_type` | query | string | 否 | `GZIP`：第二步返回 gzip 压缩流；不填就返回未压缩的文件流 |

```python
from wechatpay_v3 import request
meta = request("GET", "/v3/bill/tradebill", query={"bill_date": "2026-09-10", "bill_type": "ALL", "tar_type": "GZIP"})
# {"hash_type": "SHA1", "hash_value": "79bb0f45…", "download_url": "https://api.mch.weixin.qq.com/…?token=xxx"}
```

- 只有支付成功的订单会出现在账单里。下单了但用户没付款的订单不会出账。
- 交易账单**只有收款类**。转账、红包这类付款类的流水要看资金账单（FAQ）。
- 同一个商户号的 v2 和 v3 交易都会出现在 v3 交易账单里，因为账单是按商户号生成的（FAQ）。
- 退款单**只要发起成功就会出账**，出账后退款状态**不会再更新**。要最新的退款状态，还是得用查询退款接口。

## 3. 申请资金账单

**Endpoint**: `GET /v3/bill/fundflowbill`
**用途**：商户账户的资金流水，包括交易入账、扣手续费、退款、充值 / 提现、分账等。

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `bill_date` | query | string(10) | 是 | 同上 |
| `account_type` | query | string | 否 | `BASIC`（默认，基本账户）/ `OPERATION`（运营账户）/ `FEES`（手续费账户） |
| `tar_type` | query | string | 否 | `GZIP` |

频率限制：以商户号维度 **3 QPS**（文档原文）。

## 4. 下载与校验（Python）

```python
import gzip, hashlib, requests
from urllib.parse import urlsplit
from wechatpay_v3 import build_authorization

def download_bill(meta: dict, gzipped: bool) -> str:
    url = meta["download_url"]                         # 原样使用，不要自己拼（见 ⚠）
    req = requests.Request("GET", url, headers={"Accept": "application/json",
                                                "User-Agent": "my-shop-backend/1.0"}).prepare()
    parts = urlsplit(req.url)
    req.headers["Authorization"] = build_authorization("GET", parts.path + "?" + parts.query, "")
    resp = requests.Session().send(req, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"download failed {resp.status_code} {resp.text[:200]}")
    raw = gzip.decompress(resp.content) if gzipped else resp.content   # 压缩流要按二进制读，否则会乱码
    if hashlib.sha1(raw).hexdigest() != meta["hash_value"]:
        raise RuntimeError("bill SHA1 mismatch")
    return raw.decode("utf-8")
```

- ⚠ 文档未说明：`hash_value` 是按**压缩后**的字节流算的，还是按**解压后**的内容算的。
  官方 Java 示例（4013071238）是先解压写入文件，再对这个文件算 SHA1，所以上面按解压后的内容校验。拿到凭证后需要实测。
- 编码：UTF-8（FAQ：乱码通常是没用 UTF-8，或者用字符串流读了 gzip 数据）。

## 5. 文件格式与解析

- 文件是逗号分隔的文本，由两部分组成：**明细**（一行表头 + 多行数据）和**汇总**（一行表头 + 数据行）。
- **每个字段前面都有一个反引号 `` ` ``**，是为了防止 Excel 把长数字显示成科学计数法。计算前要去掉。
- **所有金额单位都是「元」，保留两位小数的字符串**（例如 `` `8.88 ``）。这和 API 里「整数分」不一样，对账时要统一单位（例如都换成分再比较）。
- 商户自定义的字段（商品名称、商户数据包、设备号）里的特殊字符会被转义，例如 `,` 变成 `\ `（反斜杠加空格），换行变成 `\n`。
  所以按逗号切分是安全的，但原文里的逗号会以转义形式出现。

```python
def parse_bill(text: str, summary_first_col: str):
    """summary_first_col：交易账单传「总交易单数」，资金账单传「资金流水总笔数」。"""
    rows = [[c.lstrip("`") for c in line.split(",")] for line in text.splitlines() if line.strip()]
    split = next(i for i, r in enumerate(rows) if r[0] == summary_first_col)
    header, details = rows[0], rows[1:split]
    summary = dict(zip(rows[split], rows[split + 1])) if split + 1 < len(rows) else {}
    return [dict(zip(header, r)) for r in details], summary

def yuan_to_fen(s: str) -> int:
    from decimal import Decimal
    return int((Decimal(s) * 100).to_integral_value())    # 不要用 float
```

**交易账单列**（`ALL` 类型，文档原文）：交易时间,公众账号ID,商户号,特约商户号,设备号,微信订单号,商户订单号,用户标识,交易类型,交易状态,付款银行,货币种类,
应结订单金额,代金券金额,微信退款单号,商户退款单号,退款金额,充值券退款金额,退款类型,退款状态,商品名称,商户数据包,手续费,费率,订单金额,申请退款金额,费率备注。
汇总列：总交易单数,应结订单总金额,退款总金额,充值券退款总金额,手续费总金额,订单总金额,申请退款总金额。

- `SUCCESS` 类型去掉了所有退款相关的列；`REFUND` 类型多了「退款申请时间」「退款成功时间」两列。**不同类型的列顺序不一样，要按表头名取值，不能按列号取值。**
- 「特约商户号」这一列：普通商户模式下是 `0`。
- 「交易状态」：`SUCCESS`（支付成功的订单行）/ `REFUND`（发起成功的退款行）/ `REVOKED`（付款码撤销）。
- 「退款状态」：`SUCCESS` / `PROCESSING` / `FAIL` / `CHANGE`（退款异常）。注意这组值**和退款 API 的 status 枚举不一样**（API 用的是 `CLOSED` / `ABNORMAL`）。
- 「应结订单金额」= 订单金额 − 免充值券金额。退款行里这一列是 `0.00`。
- 少部分商户的账单还是早期格式，没有「应结订单金额」「代金券金额」两列；在产品中心开通免充值优惠券功能后，第二天起会变成新格式。

**资金账单列**：记账时间,微信支付业务单号,资金流水单号,业务名称,业务类型,收支类型,收支金额(元),账户结余(元),资金变更提交申请人,备注,业务凭证号。
汇总列：资金流水总笔数,收入笔数,收入金额,支出笔数,支出金额。

### 5.1 T+1 对账

文档《支付回调和查单实现指引》（4012075249 §5.3）的做法是：T+1 日上午 10 点以后，拿 T 日的交易账单和商户系统里的订单逐笔核对。
核对时有四种情况，对应的处理如下（处理方式是文档原文）：

| 情况 | 处理 |
|---|---|
| 两边都有这笔订单，而且都是支付成功 | 正常，对账成功 |
| 两边都有，但商户系统里不是支付成功 | 按业务决定：要么补成支付成功并给用户发货，要么给用户发起退款 |
| 账单里有，商户系统里没有 | 异常：排查商户系统有没有丢数据 |
| 商户系统里是支付成功，账单里没有 | 异常：排查订单处理逻辑有没有 bug |

```python
def reconcile(bill_rows: list[dict], local_orders: dict[str, dict]) -> dict:
    """bill_rows 是 parse_bill 解析出来的明细；local_orders 以 out_trade_no 为键，每项形如 {"status": "PAID", "total_fen": 1250}。"""
    report = {"ok": [], "local_not_paid": [], "missing_local": [], "missing_in_bill": [], "amount_mismatch": []}
    paid_in_bill = {}
    for row in bill_rows:
        if row["交易状态"] != "SUCCESS":                    # REFUND / REVOKED 行另外核对退款
            continue
        paid_in_bill[row["商户订单号"]] = yuan_to_fen(row["订单金额"])
    for no, fen in paid_in_bill.items():
        local = local_orders.get(no)
        if local is None:
            report["missing_local"].append(no)
        elif local["status"] != "PAID":
            report["local_not_paid"].append(no)             # 补发货，或者退款
        elif local["total_fen"] != fen:
            report["amount_mismatch"].append(no)
        else:
            report["ok"].append(no)
    report["missing_in_bill"] = [no for no, o in local_orders.items()
                                 if o["status"] == "PAID" and no not in paid_in_bill]
    return report
```

- 拿「订单金额」（含代金券）去和下单时的 `amount.total` 比较。「应结订单金额」扣掉了免充值券，用它比较的话，用了券的订单会被误判为金额不一致。
- `local_orders` 只放 T 日的订单。跨天的订单（例如 23:59 下单、第二天 00:01 付款）按「交易时间」归到付款的那一天，比对前要按付款时间取数。

## 6. 什么时候能下载、错误码

| HTTP | code | 含义 | 处理（文档原文） |
|---|---|---|---|
| 400 | `NO_STATEMENT_EXIST` | 账单文件不存在：那天没有交易或退款（资金账单：那个账户没有资金变动） | 这是正常结果，**不要重试** |
| 400 | `STATEMENT_CREATING` | 账单生成中 | 第二天 10 点后再请求；还是这个错误的话，每隔半小时重试一次，直到成功或者返回「账单不存在」 |
| 400 | `INVALID_REQUEST` | 参数错误 | 检查 `bill_date` 格式和范围 |
| 429 | `FREQUENCY_LIMITED` | 请求过于频繁 | 降频 |

- 当天的账单不能下载。文档原文：「微信将在次日9点开始生成前一天的对账单，建议商户在次日10点后获取」。
  交易账单页的写法是「每日10点后生成昨日交易账单文件」。**定时任务放在 10 点以后**。

## 7. 本文件 ⚠

- ⚠ 文档自相矛盾：申请账单的示例响应里，`download_url` 是 `https://api.mch.weixin.qq.com/v3/bill/downloadurl?token=xxx`；
  下载账单页的示例是 `https://api.mch.weixin.qq.com/v3/billdownload/file?token=xxx`。**原样使用接口返回的 `download_url`**，不要自己拼。
- ⚠ 文档自相矛盾：交易账单的「交易类型」列举了 `MICROPAY` / `JSAPI` / `NATIVE` / `APP` / `FACE`（写着「包括但不限于」），
  而查单接口的 `trade_type` 枚举是 `FACEPAY`，还有 `MWEB`（H5）。不要把账单的交易类型和 API 的 `trade_type` 做严格的枚举映射。
- ⚠ 文档笔误：资金账单「收支金额(元)」的说明写成了「收支类型是 `收入` 时表示余额的增加金额，收支类型是 `收入` 时表示余额的减少金额」。
  第二个「收入」按上下文应该是「支出」。
- ⚠ 文档未说明：`hash_value` 是按压缩前还是压缩后的内容算的（见 §4）。
- 字段说明里「商品名称」写的是「对应下单接口里的body字段」，`body` 是 v2 的字段名；v3 下单接口里对应的是 `description`。
