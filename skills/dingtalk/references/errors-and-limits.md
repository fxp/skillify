# 错误码、响应判定与限流

来源：open.dingtalk.com/document 下「全局错误码」「调用频率限制」及各接口页错误码表（抓取于 2026-09-11），
加上本次**无凭证探测（2026-09-11）**的真实返回（只用明显伪造的 `test` 值，未用任何真实凭证）。
除标「无凭证探测」的条目外，错误码含义均为**文档原文，未实测**。

## 目录

1. [两套响应格式：先判对"成功"](#1-两套响应格式先判对成功)
2. [无凭证探测记录](#2-无凭证探测记录)
3. [旧版常见 errcode](#3-旧版常见-errcode)
4. [新版常见 code](#4-新版常见-code)
5. [限流规则](#5-限流规则)
6. [业务级限额（静默丢弃型）](#6-业务级限额静默丢弃型)
7. [统一错误处理示例](#7-统一错误处理示例)
8. [⚠ 未说明 / 矛盾之处](#8--未说明--矛盾之处)

---

## 1. 两套响应格式：先判对"成功"

| | 旧版 `oapi.dingtalk.com` | 新版 `api.dingtalk.com` |
| --- | --- | --- |
| HTTP 状态 | **出错也是 200** | 出错返回 4xx / 5xx |
| 成功 body | `{"errcode":0,"errmsg":"ok",...}` | 业务字段本身，没有 errcode |
| 失败 body | `{"errcode":88,"sub_code":"40014","sub_msg":"...","errmsg":"...","request_id":"..."}` | `{"code":"InvalidAuthentication","message":"...","requestid":"..."}` |
| 判定写法 | `resp.json()["errcode"] == 0` | `resp.status_code // 100 == 2` |

**两种写法互不适用**：对旧版用 `raise_for_status()` 永远不会报错；对新版查 `errcode` 永远拿不到。

<!-- Gap: 全局错误码把 40014 等列为 errcode，并称 88「关注返回结果里的subCode和subMsg」；实测 errcode 为 88、真实原因在 snake_case 的 sub_code（字符串）/ sub_msg -->
**旧版的鉴权类错误被包在 `errcode: 88` 里。** 全局错误码表把 `40014 不合法的access_token` 列成一个 errcode，并在 `88 鉴权异常` 下写
"关注返回结果里的subCode和subMsg"。**无凭证探测（2026-09-11）**：伪造 token 调 `topapi/v2/user/get`，返回的是
`{"errcode":88,"sub_code":"40014","sub_msg":"不合法的access_token",...}`——字段名是 **snake_case 的 `sub_code` / `sub_msg`**（不是 subCode），
且 `sub_code` 是**字符串** `"40014"`。只写 `if errcode == 40014` 的重取 token 逻辑永远不会触发。

```python
def oapi_reason(d: dict) -> str:
    """旧版：真实原因优先取 sub_code。"""
    return str(d.get("sub_code") or d.get("errcode"))
```

另：`gettoken` 本身出错时**不包 88**，直接是 `{"errcode":40096,...}`（探测 P1）。

---

## 2. 无凭证探测记录

完整日志在 `dingtalk-workspace/probe-log.md`。每个接口 ≤3 次，均为伪造值。

| # | 请求 | HTTP | 返回（片段） | 结论 |
| --- | --- | --- | --- | --- |
| P1 | `GET oapi /gettoken?appkey=test&appsecret=test` | 200 | `{"errcode":40096,"errmsg":"不合法的appKey或appSecret"}` | 40096 不在全局错误码表 ⚠ |
| P2 | 同上，但按文档 curl 用 `-X GET -d appkey=... -d appsecret=...` | 200 | `{"errcode":40035,"errmsg":"缺少参数 corpid or appkey"}` | 文档 curl 示例错误（Gap） |
| P3 | `POST api /v1.0/oauth2/accessToken`（伪造） | 400 | `{"code":"invalidClientIdOrSecret","message":"无效的clientId或者clientSecret"}` | 与文档一致 |
| P4 | `POST api /v1.0/oauth2/dingtest/token`（伪造 corpId） | 500 | `{"code":"unknownError","message":"未知错误"}` | 非法 corpId 不给可诊断错误 ⚠ |
| P5 | `POST oapi /robot/send?access_token=test` | 200 | `{"errcode":660026,"errmsg":"sending too many messages per minute"}` | 通用假值 `test` 被很多人撞，先触发限流；660026 文档未列 |
| P5b | 同上，access_token 换成随机 64 位 hex | 200 | `{"errcode":300005,"errmsg":"token is not exist"}` | 文档写 400101（Gap，见 `messaging.md`） |
| P6 | `GET api /v1.0/contact/users/test`，header `x-acs-dingtalk-access-token: test` | 400 | `{"code":"InvalidAuthentication","message":"不合法的access_token"}` | 新版 token 无效的标准返回 |
| P7 | 同上，改用 `?access_token=test` | 400 | `{"code":"AuthenticationFailed.MissingParameter","message":"缺少参数：x-acs-dingtalk-access-token"}` | 新版不认 query |
| P8 | `POST oapi /topapi/v2/user/get?access_token=test` | 200 | `{"errcode":88,"sub_code":"40014","sub_msg":"不合法的access_token"}` | 旧版鉴权错误包在 88 里 |
| P9 | 同上，只放 header `x-acs-dingtalk-access-token` | 200 | `{"errcode":88,"sub_code":"40000","sub_msg":"access_token is blank"}` | 旧版不认 header |
| P10 | 新版接口用 `Authorization: Bearer test` | 400 | `缺少参数：x-acs-dingtalk-access-token` | 新版不认 Bearer |
| P11 | 旧版 POST，`access_token` 放在表单 body | 200 | `errcode 88 / sub_code 40014` | POST 表单 body 里的 token 会被读取 |
| P12 | `POST api /oauth2/corpAccessToken`（文档参数表路径） | 200 | `{"errcode":404,"errmsg":"请求的URI地址不存在"}` | 文档 URL 缺 `/v1.0`（Gap） |
| P13 | `POST api /v1.0/oauth2/corpAccessToken` | 400 | `{"code":"invalidSuiteKey","message":"suitekey不合法"}` | 正确路径 |
| P14 | `POST oapi /topapi/v2/user/notexist?access_token=test` | 200 | `{"errcode":22,"sub_msg":"不合法ApiName，ApiName = dingtalk.oapi.v2.user.notexist"}` | 旧版路径拼错不是 404，而是 errcode 22 |

---

## 3. 旧版常见 errcode

（全局错误码表摘录，文档原文，未实测）

| errcode | 含义 | 处理 |
| --- | --- | --- |
| -1 | 系统繁忙 | 文档："建议稍后再重试1次，最多重试3次" |
| 0 | 成功 | |
| 88 | 鉴权异常 | 看 `sub_code` / `sub_msg`（见第 1 节） |
| 22 | 不合法 ApiName（无凭证探测：路径拼错时返回） | 检查路径 |
| 33001 | 无效的企业ID | 检查 token 是否对应该企业 |
| 33012 | 无效的 USERID | |
| 40001 | 获取 access_token 时 Secret 错误，或 access_token 无效 | |
| 40003 | 不合法的 UserID | 确认 userid 属于该 token 对应企业 |
| 40014 | 不合法的 access_token（文档："access_token这个参数应该是带在url后面的"） | 重新取 token；实际出现在 `sub_code` |
| 40035 | 不合法的参数 / 缺少参数 | |
| 40078 | 不存在的临时授权码（免登码只能用一次） | |
| 40089 | 不合法的 corpid 或 corpsecret | |
| 41001 | 缺少 access_token 参数（"该参数必须跟在请求url中"） | |
| 42001 | access_token 超时 | 重新取 token |
| 43007 | 需要授权 | |
| 50002 | 企业员工不在授权范围 | 检查应用可使用范围 / 通讯录授权范围 |
| 60003 | 部门不存在 | |
| 60011 | 没有调用该接口的权限 | 开发者后台 → 权限管理 → 添加接口权限 |
| 60020 | 访问 ip 不在白名单之中 | 核对服务器出口 IP |
| 60121 | 找不到该用户 | |
| 71006 | 回调地址已经存在 | |
| 400002 | 参数错误 / 无效的参数 | |
| 90001–90014 | 各维度调用被暂时禁用（限流） | 见第 5 节 |

---

## 4. 新版常见 code

| HTTP | code | 含义（文档原文） |
| --- | --- | --- |
| 400 | InvalidAuthentication | 不合法的 access_token（过期或不存在，需要重新获取） |
| 400 | AuthenticationFailed.MissingParameter | 缺少参数：x-acs-dingtalk-access-token（**无凭证探测**所得，文档未列） |
| 400 | invalidClientIdOrSecret | 无效的 clientId 或者 clientSecret |
| 400 | apiPermissionDenied | 无权限访问此接口 |
| 400 | accesstoken.expired | 用户 accessToken 过期 |
| 400 | qps.exceed.limit / request.overlimit / oaplus.query.limit | 请求过于频繁 |
| 401 | unauthorized.client | 应用未被授权 |
| 403 | Forbidden.AccessDenied.AccessTokenPermissionDenied | 没有调用该接口的权限 → 去开发者后台申请权限点 |
| 403 | Forbidden.AccessDenied.IpNotInWhiteList | 访问 IP 不在白名单 |
| 403 | Forbidden.AccessDenied.QpsLimitForApi | 触发该接口全局 QPS 限流 |
| 403 | Forbidden.AccessDenied.QpsLimitForAppkeyAndApi / QpmLimitForAppkeyAndApi | 企业应用对该接口触发 QPS / QPM 限流 |
| 403 | Forbidden.AccessDenied.QpsLimitForSuitekeyAndOrgAndApi / QpmLimit... | ISV 应用对某客户企业触发限流 |
| 403 | - (Forbidden) | "请求被拒绝，通常由于权限不足或触发限流" |
| 409 | invalidRequest.duplicateClientToken | 幂等键重复 |

注意全局表里同一个 code 可能对应多个 HTTP 状态（如 `unauthorized` 标 400/401/500），**按 `code` 分支，不要按 HTTP 状态分支**。

---

## 5. 限流规则

（「调用频率限制」文档原文，未实测）

**全局维度**：所有企业、所有应用对**同一个接口**的累计调用达到上限后，所有调用方都会失败，返回 `errcode 90002`。
文档建议：立即暂停该接口的密集调用；指数退避（1s、2s、4s…）；用事件订阅代替轮询。

**IP 维度**：每个公网出口 IP 对**所有接口**的总调用量 **20 秒内最多 10000 次**，触发后该 IP **5 分钟**内禁止调用所有接口。
触发时"不会返回标准 JSON 错误结构"，而是 HTML 页面或：

```json
{"status": 1111, "wait": 5, "source": "x5", "punish": "deny", "uuid": "xxx"}
```

所以限流处理不能只看 `errcode` / `code`——还要识别非 JSON 响应和 `punish: deny`。多应用共享 NAT 出口时更容易触达。

**旧版分维度禁用码**（文档原文）：`90001` 服务器所有接口被禁用、`90002` 当前接口被禁用、`90003`–`90006` 企业 / CorpId 维度、
`90007`–`90014` ISV 维度（对某企业、某套件、某接口）。

**其他接口级限额**：
- 自定义机器人：每个机器人每分钟最多 20 条，超过限流 10 分钟（errcode `410100`）。
- AI 卡片流式更新：单次内容不要超过 1K，总大小建议 ≤3K。
- `gettoken` 类接口：文档反复强调"不能频繁调用"，必须缓存 token。
- 机器人 / Stream 调用量超出组织额度：消息服务暂停，收到的消息无 text/content，错误码 `20001`，需"升级钉钉专业版或购买增购包"。

---

## 6. 业务级限额（静默丢弃型）

最危险的一类：**接口返回成功，但消息实际没送达**。

工作通知（`asyncsend_v2`）文档原文："**超出以下限制次数后，接口返回成功，但用户无法接收到。**"
- 企业内部应用单次最多发 5000 人，第三方企业应用 1000 人；
- 给同一员工一天只能发一条**内容相同**的消息；
- 企业内部应用每天给每个员工最多 500 条，第三方企业应用 100 条（⚠ 另一页写 50 条，见第 8 节）；
- 每分钟最多 5000 人可以接收到消息。

发送后要用 `getsendresult` 查 `forbidden_user_id_list` / `forbidden_list`（流控 code `143105` 每日超限、`143106` 重复内容）确认实际送达，
详见 `messaging.md`。

---

## 7. 统一错误处理示例

```python
import time, requests

class DingTalkError(Exception):
    def __init__(self, reason: str, raw):
        super().__init__(f"{reason}: {raw}")
        self.reason, self.raw = reason, raw

TOKEN_INVALID = {"40014", "42001", "40001", "InvalidAuthentication", "accesstoken.expired"}
THROTTLED = {"90002", "90001", "410100", "qps.exceed.limit", "request.overlimit",
             "Forbidden.AccessDenied.QpsLimitForApi", "Forbidden.AccessDenied.QpsLimitForAppkeyAndApi"}

def parse(resp: requests.Response):
    try:
        d = resp.json()
    except ValueError:                           # IP 限流可能直接回 HTML
        raise DingTalkError("non_json_maybe_ip_throttled", resp.text[:200])
    if d.get("punish") == "deny":                # IP 维度限流的 JSON 形态
        raise DingTalkError("ip_throttled", d)
    if "api.dingtalk.com" in resp.url:           # 新版
        if resp.status_code // 100 != 2:
            raise DingTalkError(d.get("code", str(resp.status_code)), d)
        return d
    code = str(d.get("sub_code") or d.get("errcode"))   # 旧版：88 时看 sub_code
    if code != "0":
        raise DingTalkError(code, d)
    return d

def call_with_retry(do_request, refresh_token, attempts: int = 4):
    for i in range(attempts):
        try:
            return parse(do_request())
        except DingTalkError as e:
            if e.reason in TOKEN_INVALID and i == 0:
                refresh_token(); continue
            if e.reason in THROTTLED or e.reason == "-1":
                time.sleep(2 ** i); continue     # 文档建议的指数退避；-1 系统繁忙最多重试 3 次
            raise
    raise DingTalkError("retry_exhausted", None)
```

IP 维度被封是 5 分钟，指数退避几秒无济于事：遇到 `ip_throttled` 应直接熔断非关键任务（文档建议"熔断与降级"）。

---

## 8. ⚠ 未说明 / 矛盾之处

- `40096`（gettoken 伪造凭证）、`660026`、`300005`、`22`、`AuthenticationFailed.MissingParameter` 都是探测所得、全局错误码表未收录 ⚠ 文档未说明。
- 工作通知第三方应用每人每日上限：「发送工作通知」页写 100 条，「获取工作通知消息的发送结果」页错误码 `143105/143205` 说明写"ISV最多可发送50条" ⚠ 文档自相矛盾。
- 全局维度限流的具体阈值 ⚠ 文档未说明（只说"达到上限"）。
- 新版 403 `QpsLimit*` 的冷却时长 ⚠ 文档未说明。
