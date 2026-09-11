# 错误码、返回结构与限流

内容整理自 https://doc.youzanyun.com/ （抓取于 2026-09-11）。**未用真实凭证验证。**
错误码与处理建议未标注来源的都是「文档原文，未实测」；标「无凭证探测（2026-09-11）」的见 `youzan-workspace/probe-log.md`。

## 目录
1. 三种返回结构（先分清再判错）
2. 网关错误码 4xxx / 5xxx
3. 获取 token 的错误码 1xxx
4. 常见业务错误码（按领域）
5. 限流：错误形态、建议 QPS、退避
6. 额度与计费
7. 统一调用封装（Python）
8. 排查工具
9. ⚠ 本文件的文档矛盾 / 未说明

---

## 1. 三种返回结构

有赞云不同层返回的结构**字段名不一样**，只判 `code` 会漏：

| 来源 | 结构 | 何时出现 |
|---|---|---|
| `/auth/token` | `{"success":false,"code":1103,"data":null,"message":"Client 不存在"}` | 换 token 失败（无凭证探测 ×2 证实） |
| `/api/...` 网关层 | `{"gw_err_resp":{"trace_id":"yz7-...","err_msg":"非法的请求凭证","err_code":4201}}` | 路径 / 版本 / Content-Type / token / 权限 / 限流等网关校验失败（无凭证探测 ×2 证实，4001/4005/4007/4201/4203） |
| `/api/...` 业务层 | 成功：`{"trace_id":"...","code":200,"data":{...},"success":true,"message":"successful"}`；失败：`{"code":102570020,"data":null,"success":false,"message":"订单没有可发货的商品","request_id":null}` | 请求已到达业务服务（文档示例） |

<!-- Gap: 全局错误码页（v2 FrEoweHuniNS0KkVtNzcEqQenSf / resource/doc/3027）只给出 {success, code, data, message} 一种返回结构（字段表写 code / msg）。无凭证探测（2026-09-11，每条 ×2）：/api/ 网关层的 4001、4005、4007、4201、4203 实际返回 {"gw_err_resp":{"trace_id","err_msg","err_code"}}，顶层没有 code / success 字段。 -->

- 无凭证探测（2026-09-11）：以上错误的 **HTTP 状态码都是 200**，必须解析 body 判断；`http://` 请求是 301。
- 业务成功的 `code` 是 200（不是 0）；业务错误码多为 9 位数字，也有 5000、50000 这类短码。
- 个别老接口结构不同：`youzan.trade.memo.update.3.0.0` 返回 `{"response":{"is_success":true}}` / `{"error_response":{"msg":"...","code":500}}`（文档原文）。
- 有的接口“成功”只代表受理：`youzan.item.delete.3.0.1` 底层异步，**返回成功不代表删除成功，需要二次反查**（llms 摘要原文）。
- 业务成功时 `data` 里还可能有 `is_success: false`，要一起判断。

## 2. 网关错误码（`gw_err_resp.err_code`）

| err_code | err_msg | 触发场景 | 处理 |
|---|---|---|---|
| 4001 | 非法请求地址 | 路径不是 `/api/{name}/{version}`。无凭证探测（×2）：缺版本号即 4001 | 检查 URL 拼接 |
| 4004 | 非法的Content | Content-Type 是 JSON 但 body 不是 JSON | 检查序列化 |
| 4005 | 非法的API | API 名或版本不存在。无凭证探测（×2）：不存在的名称、`youzan.trade.get/9.9.9` 都是 4005，先于 token 校验 | 核对名称与版本 |
| 4007 | 非法的请求 / 非法的请求姿势 | 方法或 Content-Type 不支持（只支持 GET / POST；POST 支持 json、x-www-form-urlencoded、multipart/form-data）。无凭证探测（×2）：`text/plain` → `非法的请求姿势，httpMethod:POST, contentType:text/plain`。FAQ 6241：**IP 白名单不通过也是 4007**（err_msg “源IP地址…非法调用有赞云”） | 看 err_msg 区分 |
| 4008 | 接口不支持富文本 | 路径出现 `/textarea` | — |
| 4009 | openid 不存在 | yz_open_id 找不到对应用户 | 核对 yz_open_id |
| 4010 | 参数类型不匹配 | 系统配置问题 | 联系技术支持 |
| 4101 | 请求太频繁 | 被限流 | 见第 5 节 |
| 4201 | 非法的请求凭证 | token 为空 / 授权关系过期 / 店铺关闭授权。无凭证探测（×2）：URL 不带 token、token 放 Authorization 头、token 放 body 都是 4201 | token 只放 URL query；授权问题需人工处理 |
| 4202 | 请求凭证过期 | token 过期 | 刷新 token 后重试一次 |
| 4203 | 请求凭证不存在 | token 不存在。无凭证探测（×2）：伪造 token 的 err_msg 是 “Token 不存在” | 刷新 token；确认没有混用老开放平台 `open.youzan.com` 的 token；确认没复制截断 |
| 4204 | 无权限访问 | 没有该 API 的能力包，或被风控 | 控制台申请能力包 |
| 5001 | 系统异常 | 网关无法识别的异常，**多数是参数类型不对** | 见下方例子 |
| 5002 | 业务异常 | 业务运行时异常 | 检查入参 |
| 5003 | 插件执行异常 | — | 联系技术支持 |

5001 的两个典型原因（FAQ 33694）：
- `youzan.trades.sold.get` 的 `start_created` 传 `"2019-06-01"` → 5001；必须带时分秒 `"2019-06-01 17:26:25"`。
- `youzan.users.account.check` 的 `account_id` 传数字 `1441668074` → 5001；必须是字符串 `"1441668074"`。
即：**文档写 `java.lang.String` 的就传字符串，写 `java.util.Date` 的传 `yyyy-MM-dd HH:mm:ss`。**

## 3. 获取 token 的错误码

见 `auth-token.md` 第 8 节（1000 / 1004 / 1005 / 1103 ×3 种含义 / 1105）。

## 4. 常见业务错误码（文档原文，未实测）

| 领域 | code | 含义 / 处理 |
|---|---|---|
| 订单 | 5000 `trade not found` | 订单号错，或**用 A 店铺的 token 查 B 店铺的订单** |
| 订单 | 106000004 / 106100110 | 订单号非法（不是有赞订单号） |
| 订单列表 | 5000 `每页最多显示100条数据`、`开始时间不能大于结束时间` | 分页 / 时间参数错 |
| 订单列表 | 106000001 / 106100118 / 106000003 | 请求超时，重试；106000003 另指结束时间超过当前日期后 7 天 |
| 发货 | 102570020 | 订单没有可发货的商品 |
| 发货 | 102510001 | 不能同时发起两笔相同的发货请求（并发） |
| 发货 | 102570007 | 不能重复提交已发过货的商品 |
| 发货 | 102599996 | oids 不是纯数字 |
| 发货 | 105000003 | 快递单号只能包含字母、数字或中划线 |
| 发货 | 102570038 | 分销单只允许分销系统同步发货 |
| 单商品多运单 | 102570059 | 各包裹数量之和必须等于该商品购买总数 |
| 退款 | 103010039 | 退款版本号错误：先 `youzan.trade.refund.get` 取最新 `version` |
| 退款 | 102010002 | 操作过期，退款状态已变更，重新查询 |
| 退款 | 102010003 | 退款操作太快 |
| 退款 | 102090108 | 店铺余额不足 |
| 商品 | 122001001 / 123005001 | 商品不存在 |
| 商品 | 123004002 | SKU 不存在 |
| 商品 | 123003023 | 开启了库存同步，修改库存不生效（零售） |
| 商品 | 121009313 | 至少上传一张图片 |
| 客户 | 141500101 | 参数错误（最常见：手机号不是 11 位） |
| 客户 | 143001027 / 141502109 | 客户已存在 |
| 客户 | 141001107 / 141502108 | 客户不存在，先 `youzan.scrm.customer.create` |
| 积分 | 142100106 | 重复操作（幂等键命中） |
| 积分 | 142100002 | 连锁网店 / 门店不能加减积分，只能总部 |
| 积分 | 141500203 | api rate limiting：对同一客户减少并发 |

## 5. 限流

### 5.1 被限流时长什么样
限流页（`resource/develop-guide/27027/41693`）列出三种形态（文档原文，未实测）：
- `{code:"4101", msg:"访问频繁"}`（网关层，实际应在 `gw_err_resp` 里，⚠ 文档未给出完整结构）
- `{"msg":"请求被限流","code":500100004}`
- `{"code":123000042,"success":false,"message":"请求被限流"}`
另有积分域 `141500203 api rate limiting`。

### 5.2 建议退避（文档原文）
以 **3s、6s、12s、24s、48s** 间隔重试 5 次；5 次都失败且提示相同，记录日志并联系技术支持。不要长时间循环或短时间多线程高频调用，否则可能被限流**甚至关闭调用权限**。

### 5.3 建议单店 QPS（摘录，单位：次/秒/店铺）

| API | 建议 QPS |
|---|---|
| youzan.item.get.3.0.0、youzan.item.search.3.0.0、youzan.items.onsale.get.3.0.0、youzan.items.inventory.get.3.0.0 | 300 |
| youzan.item.add.1.0.0 | 30 |
| youzan.item.update.3.0.1 / 4.0.0 | 40 |
| youzan.item.create.3.0.1、youzan.item.delete.3.0.1、上下架 3.0.1 | 20 |
| youzan.item.sku.update.3.0.0 | 50 |
| youzan.item.quantity.update.3.0.0 | 30 |
| youzan.scrm.customer.create.3.0.0 | 200 |
| youzan.scrm.tag.relation.add.4.0.0 / delete.4.0.0 | 5 |
| youzan.scrm.tag.relation.get.4.0.0 | 10 |
| youzan.crm.customer.points.increase / decrease / sync.3.1.0 | 100 |
| youzan.user.openid.get.1.0.0 | 100 |

- 限流表**没有列出订单类接口**（trade.get、trades.sold.get、logistics.online.confirm）→ ⚠ 文档未说明其 QPS。
- 表里多为旧版本号（如积分 3.1.0），新版本（4.0.0）的限额 → ⚠ 文档未说明。
- 标签 FAQ 建议客户标签接口限频 5、5、10 次/秒（与上表一致）。
- 接口超时 5 秒（FAQ 41466）。

## 6. 额度与计费（`resource/doc/8770`，2026-02-28 调整，文档原文）

- 大多数 API / 消息标注“计费”，按次消耗月度额度。自 2025-07-01 起改为**先付后用**：先订购 API 套餐包或购买带赠送套餐的 SaaS 版本并绑定应用。
- 套餐：试用 1 万次 / 60 天（仅订单、商品试用接口）；A 套餐 50 万 API + 50 万消息 / 月；B 套餐 200 万 + 200 万；C 套餐 1200 万 + 1200 万。额度当月有效不结转，每月 1 日发放。
- API 套餐每月发放到店铺绑定的**第一个无容器应用**，不发到有容器应用。
- **欠费后系统会限制 API 相关功能，包括限流和停用 API、消息推送**；缴清或升级后恢复。
- 所以线上看到大面积 4101 / 限流时，除了降并发，还要检查额度与账单。

## 7. 统一调用封装（Python）

```python
import time, requests

API_BASE = "https://open.youzanyun.com/api"
TOKEN_ERRORS = {4201, 4202, 4203}
RATE_LIMIT = {4101, 500100004, 123000042, 141500203}
RETRYABLE_BIZ = {106000001, 106100118, 5001}   # 5001 多为参数错，仅在确认参数无误时保留
BACKOFF = [3, 6, 12, 24, 48]                   # 文档建议的限流退避

class YouzanError(Exception):
    def __init__(self, code, msg, trace_id=None):
        super().__init__(f"{code} {msg} trace_id={trace_id}")
        self.code, self.msg, self.trace_id = code, msg, trace_id

def _parse(body: dict):
    if "gw_err_resp" in body:                       # 网关层（探测证实）
        e = body["gw_err_resp"]
        raise YouzanError(e.get("err_code"), e.get("err_msg"), e.get("trace_id"))
    if body.get("success") is False or (body.get("code") not in (None, 200)):
        raise YouzanError(body.get("code"), body.get("message"), body.get("trace_id"))
    return body.get("data")

def call(api: str, version: str, params: dict, token_provider, kdt_id: str):
    refreshed = False
    for attempt in range(len(BACKOFF) + 1):
        token = token_provider(kdt_id, force_refresh=False)
        r = requests.post(f"{API_BASE}/{api}/{version}",
                          params={"access_token": token}, json=params, timeout=10)
        try:
            return _parse(r.json())
        except YouzanError as e:
            if e.code in TOKEN_ERRORS and not refreshed:
                token_provider(kdt_id, force_refresh=True); refreshed = True; continue
            if e.code in RATE_LIMIT and attempt < len(BACKOFF):
                time.sleep(BACKOFF[attempt]); continue
            raise
```
- 业务码之外，写操作（发货、退款、加积分）**不要盲目重试**：先用幂等键（积分的 `biz_value`、主动退款的 `biz_value`）或先查询状态，避免重复发货 / 重复退款。
- 记录 `trace_id`，提工单和查 API 日志都靠它。

## 8. 排查工具（文档原文）

- 控制台 **API 日志**：按时间、traceID、API 名称、返回码查请求与响应，最多保留 7 天，单次查询时间范围 1 小时，生产与开发环境分开（`resource/doc/3705` 摘要）。
- **API 调试工具**：绑定云测试店铺后可自动带 token 调试接口；在线调试会影响真实数据。
- 云测试店铺：每类最多 3 个，有效期 30 天（`resource/doc/3673` 摘要）。

## 9. ⚠ 本文件的文档矛盾 / 未说明

- 全局错误码页的返回结构与网关实际结构不一致（见第 1 节 Gap 注释）
- 4203 的 err_msg：错误码表写“请求凭证不存在”，探测到的是“Token 不存在”（只是文案差异，按 err_code 判断即可）
- 1000 在错误码表中是“client_secret 不正确”，探测（单次）中也用于 Content-Type 错误 → 看 message
- 4007 同时用于“请求方式 / Content-Type 不对”和“IP 白名单不通过”（FAQ 6241）→ 看 err_msg
- 订单类接口的 QPS、新版本积分接口的 QPS → ⚠ 文档未说明
- 限流时 4101 的完整 JSON 结构 → ⚠ 文档未说明
