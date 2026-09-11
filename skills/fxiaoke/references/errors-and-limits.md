# 错误码、限流与常见报错排查

> 来源：https://developer.fxiaoke.com/openapi_v2/start/guide/codes.html（全局返回码）、`start/guide/rate.html`（频次限制）、
> FAQ「无此操作的数据权限」「人员对象查不到数据」「深翻页文档」（抓取于 2026-09-11），旧版 wiki「全局返回码」（artiId=27）、「接口调用说明」（artiId=169）。
> 标「无凭证探测（2026-09-11）」的是实际打出来的响应；其余**全部为文档原文，未实测**。探测明细见 `fxiaoke-workspace/probe-log.md`。

## 目录
1. 怎么判断成功 / 失败
2. 无凭证探测到的真实错误响应
3. 全局返回码表（文档原文）
4. 频次限制与配额
5. 常见业务报错与处理
6. 推荐的错误处理 / 重试代码
7. 本文件的 ⚠

---

## 1. 怎么判断成功 / 失败

- **HTTP 状态码没有意义**：无凭证探测（2026-09-11）中，缺参数、伪造凭证、缺鉴权的请求全部返回 **HTTP 200**，错误只在 body 里。
- 判 body 的 `errorCode`：`0` 成功，其余都是失败。
- **不要用 `errorMessage` 做逻辑判断**——每个接口页都写着「不能使用返回值的 message 字段做逻辑判断，errorMessage 会有变化」。
- 失败时把 `traceId` 记进日志，找纷享排查时要用。
- 响应公共字段：`errorCode`（Int）、`errorMessage`、`errorDescription`、`traceId`。换 token 接口的错误响应还多 `error`、`error_description`。
- 文件上传第二步（上传到 `img.fxiaoke.com` 之类的地址）响应格式不同：`{"success": bool, "code": 200, "message": …, "data": …}`，见 `objects-and-fields.md`。
- 非 JSON 响应（HTML）通常说明域名错了：`www.fxiaoke.com/cgi/...` 返回的是 302 HTML（见 `auth.md`）。

## 2. 无凭证探测到的真实错误响应

| 场景 | 请求 | 实际响应（HTTP 200） |
| --- | --- | --- |
| 换 token，appSecret 伪造 | `POST /oauth2.0/token`，`grantType=app_secret` | `{"errorCode":10006,"errorMessage":"the parameter appSecret is missing or illegal","errorDescription":"缺少参数或参数不合法","error":"非法请求","error_description":"缺少参数或参数不合法"}` |
| 换 token，body 里根本没有 appSecret | 同上 | 同上，`errorCode 10006` |
| 旧版换 token，伪造凭证 | `POST /cgi/corpAccessToken/get/V2` | `{"errorCode":10006,"errorMessage":"the parameter appSecret is missing or illegal","errorDescription":"缺少参数或参数不合法","traceId":"open-api-gateway-web/…"}` |
| 业务接口，完全不带鉴权 | `POST /cgi/crm/v2/data/query` | `{"traceId":"E-O.null.-1000-…","errorMessage":"corpAccessToken为必填项，不能为空","errorCode":20017}` |
| 业务接口，伪造 Bearer + x-fs-ea + x-fs-userid | `POST /cgi/crm/v2/data/query` | `{"traceId":"E-O.null.-1000-…","errorMessage":"the cropId,cropAccessToken or authorization is error","errorCode":20016}` |
| 自定义对象接口，旧版 body 伪造 corpAccessToken | `POST /cgi/crm/custom/v2/data/query` | 同上，`errorCode 20016` |

<!-- Gap: 文档「全局返回码」表：10002=缺少参数appSecret、11002=参数appSecret不合法、10006=缺少参数scope。无凭证探测（2026-09-11）：换 token 时 appSecret 缺失或非法，实际都返回 errorCode 10006 + "the parameter appSecret is missing or illegal"。码表与网关实际行为不一致。 -->
<!-- Gap: 文档「全局返回码」表：10013=缺少参数corpAccessToken、20017=corpId未找到。无凭证探测（2026-09-11）：业务接口完全不带鉴权时实际返回 errorCode 20017 + "corpAccessToken为必填项，不能为空"。 -->

**结论**：文档码表和网关实际返回对不上（上方两条 Gap）。代码里：
- 不要按码表写 `switch` 精确分支（尤其 1xxxx 参数类错误）；
- 可以依赖的只有：`0` = 成功；`20016` = token 无效或过期（探测与文档一致）→ 重新换 token 重试一次；
- 其余一律当失败，记录 `errorCode` + `errorMessage` + `traceId`，人工排查。

## 3. 全局返回码表（文档原文，未实测）

| 返回码 | 说明 | 返回码 | 说明 |
| --- | --- | --- | --- |
| -2 | 系统错误 | -1 | 系统繁忙 |
| 0 | 请求成功 | 10001 | 缺少参数 appId |
| 10002 | 缺少参数 appSecret | 10003 | 缺少参数 appAccessToken |
| 10004 | 缺少参数 redirectUri | 10005 | 缺少参数 responseType |
| 10006 | 缺少参数 scope（**探测实为 appSecret 缺失或非法**） | 10007 | 缺少参数 state |
| 10008 | 缺少参数 code | 10009 | 缺少参数 appAccount |
| 10010 | 缺少参数 openUserId | 10012 | 缺少参数 permanentCode |
| 10013 | 缺少参数 corpAccessToken（**深翻页文档里又表示 offset 超过 10000**） | 10014 | 缺少参数 corpId |
| 10015 | 缺少参数 toUser | 11001 | 参数 appId 不合法 |
| 11002 | 参数 appSecret 不合法 | 11003 | 参数 appAccessToken 不合法 |
| 11004 | 参数 redirectUri 不合法 | 11005 | 参数 responseType 不合法 |
| 11006 | 参数 scope 不合法 | 11007 | 参数 state 不合法 |
| 11008 | 参数 openUserId 不合法 | 11009 | 参数 departmentId 不合法 |
| 11010 | 参数 code 不合法 | 11011 | 参数 appAccount 不合法 |
| 11013 | 参数 permanentCode 不合法 | 11014 | 参数 corpAccessToken 不合法 |
| 11015 | 参数 corpId 不合法 | 11016 | 参数 toUser 不合法 |
| 11017 | 参数 msgType 不合法 | 11018 | 参数 templateId 不合法 |
| 12002 | 登录状态错误 | 12003 | 未支持的消息类型 |
| 12004 | POST 的数据包为空 | 12005 | 文本消息内容为空 |
| 14001 | 接口调用超过限制 | 15002 | 参数不合法 |
| 15003 | APP 没有访问权限 | 20005 | accessToken 不存在或者已经过期 |
| 20006 | appId 或 appSecret 错误 | 20010 | CODE 不存在或者已经过期 |
| 20012 | openUserId 未找到 | 20014 | 应用没有获取该员工的数据的权限 |
| 20015 | 永久授权码错误 | 20016 | corpAccessToken 不存在或者已经过期（**探测一致**） |
| 20017 | corpId 未找到（**探测实为缺 corpAccessToken / 鉴权**） | 20020 | 应用没有获取该企业的数据的权限 |
| 20021 | 在当前企业下，该 app 的状态为停用 | 20022 | 企业没有对该 app 授权 |
| 20023 | APP 没有访问 department 的权限 | 30002 | 当天访问频次超限（0 点重新统计） |
| 30003 | 客户没有购买 openapi 配额，需要提 open api 订单购买 | 30004 | 秒频次超限 |
| 30007 | 部门不存在 | 30027 | 员工不存在 |
| 32000 | 参数错误 | 40010 | templateId 不合法 |
| 50009 | 服务异常，如超时（新版表有，旧版表无） | | |

## 4. 频次限制与配额

「频次限制说明」页 + 旧版 wiki 169（文档原文，未实测）：

| 限制 | 值 | 超限表现（码表） |
| --- | --- | --- |
| 单接口调用频率 | **100 次 / 20 秒**（每个接口单独计） | `30004` 秒频次超限 / `14001` 接口调用超过限制（⚠ 哪个码对应哪种超限文档未说明） |
| 每日总调用次数 | 按购买的「Open API [100000 次]」资源包计，买多个叠加 | `30002` 当天访问频次超限，0 点重新统计 |
| 未购买配额 | — | `30003` 客户没有购买 openapi 配额 |
| 换 token 接口 | 每分钟 ≤10 次，**不能并发** | ⚠ 文档未说明超限码 |

- 需要提升单接口频率要找纷享购买「独立库产品」；每日配额要买资源包。**这是企业的采购问题，代码重试解决不了。**
- 设计同步任务时先算账：全量拉 3 万条客户 = 300 次 query（limit 100），再加每条详情 / 关联查询就可能上万次，注意每日配额。
- 能用 `fieldProjection` 一次拿全需要的字段，就不要每条再调 get。

## 5. 常见业务报错与处理

（FAQ 与旧版 wiki 27，文档原文，未实测）

| 报错 | 原因 | 处理 |
| --- | --- | --- |
| 无此操作的数据权限 | `x-fs-userid` / `currentOpenUserId` 对应员工的角色没有这条数据的权限 | 换 CRM 管理员的员工 ID，或给该员工加权限 |
| 无此操作的数据权限（改线索 / 客户负责人时） | 数据在线索池 / 公海里，**任何人都没有操作权限** | 先 `data/choose` 领取，再 changeOwner（`crm-preset-objects.md` 第 7 节） |
| 没有XXXX权限 | 查询接口相当于该员工访问一次列表，员工没有该对象的列表权限 | 同上，换管理员或加权限 |
| Bad Request | 调 **v1** 自定义对象接口时 `currentOpenUserId` 不是 CRM 管理员 | 换成 CRM 管理员 openUserId；或改用 v2 接口 |
| 人员对象查不到 / 查不全 | 人员对象独立的查询权限，管理员默认也没有 | 申请灰度或配共享规则（`org-directory.md` 第 8 节） |
| 查询结果比网页少 | offset 当成页码；或该员工看不到部分数据 | offset = 页号 × limit；用同一员工登录网页对比 |
| `offset 不能超过10000`（errorCode 10013） | offset 超过 1 万 | 改用 `_id` 游标深翻页（`query-and-paging.md` 第 5 节） |
| 20016 | token 不存在或已过期 | 重新换 token 重试一次；检查是否超过 7200 秒没刷新 |

## 6. 推荐的错误处理 / 重试代码

```python
import time
from collections import defaultdict

# 仅按文档码表含义挑出的「可以稍后重试」的码；码表与实测有出入，以日志为准再调整
RETRY_LATER = {-1, 50009, 30004, 14001}
STOP_NOW = {30002, 30003, 20021, 20022}     # 当日配额用尽 / 没买配额 / 应用停用 / 未授权：重试没用

class RateLimiter:
    """单接口 100 次 / 20 秒 → 每个 path 至少间隔 0.2 秒。"""
    def __init__(self, per_path_interval=0.2):
        self.gap = per_path_interval
        self.last = defaultdict(float)

    def wait(self, path):
        delta = time.time() - self.last[path]
        if delta < self.gap:
            time.sleep(self.gap - delta)
        self.last[path] = time.time()

limiter = RateLimiter()

def call(fxk, path, body, max_retry=3):
    for i in range(max_retry + 1):
        limiter.wait(path)
        try:
            return fxk.post(path, body)            # FxkClient.post 已处理 20016 → 刷新 token 重试
        except FxkError as e:                       # FxkError / FxkClient 定义见 auth.md 第 10 节
            if e.code in STOP_NOW:
                raise
            if e.code in RETRY_LATER and i < max_retry:
                time.sleep(2 ** i * 5)
                continue
            raise
```

写入类接口（create）重试前先想清楚幂等：超时不代表没写成功，重试可能产生重复数据。可以在重试前按业务唯一字段查一次，
或打开查重（自定义对象 `checkDuplicateSearch: true`，预置对象 `optionInfo.isDuplicateSearch` ⚠ 含义文档未说明）。

## 7. 本文件的 ⚠

- Gap（探测证实）：appSecret 缺失 / 非法实际返回 10006，与码表不符（第 2 节）。
- Gap（探测证实）：不带鉴权实际返回 20017「corpAccessToken为必填项」，与码表不符（第 2 节）。
- ⚠ 文档自相矛盾：10013 在码表是「缺少参数 corpAccessToken」，在深翻页文档是「offset 不能超过10000」（第 3 节）。
- ⚠ 文档未说明：14001 与 30004 分别对应哪种超限；换 token 超频的错误码（第 4 节）。
- ⚠ 文档自相矛盾：新版码表有 50009，旧版没有（第 3 节）。
