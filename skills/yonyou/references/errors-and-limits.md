# 返回码、幂等、限流与平台变更

> 来源：open.yonyoucloud.com「开放平台接入文档 → 接入规范 → 返回码说明 / API 开发规范 → 幂等性」、各 API 详情 JSON 的错误示例、
> 平台公告（`/iuap-ipaas-base/openPortal/cms/doc/…`），抓取于 2026-09-11。
> 码表和行为描述是**文档原文，未实测**；标「无凭证探测（2026-09-11）」的是用伪造参数打出的真实返回，命令见 `yonyou-workspace/probe-log.md`。

## 目录

1. 成功判定速查
2. 响应外壳：文档写的 vs 探测到的
3. 平台码表（文档原文）
4. token 接口与网关查询接口的返回码
5. 业务错误的几种形态
6. MDD 幂等：resubmitCheckKey
7. 限流
8. 平台行为变更（按公告）
9. 排错清单
10. 本文件的 ⚠ 汇总

---

## 1. 成功判定速查

| 接口 | 成功条件 | 备注 |
| --- | --- | --- |
| 查数据中心网关 | `code == "00000"` | 字符串 |
| 取 access_token | `code == "00000"` | 字符串 |
| 业务接口（绝大多数） | `str(code) == "200"` | 文档示例里既有 `"200"` 也有 `200`，统一 `str()` 后比较 |
| 批量 / 状态动作（提交、审核、删除、分配、批量保存） | `code == "200"` **且** `data.failCount == 0` | 部分失败时仍返回 200 |
| 会计期间查询 | `code == "200"` 且 `success` 为真 | 失败示例是 `code: 0, success: false` |
| MDD 幂等接口 | `code` 为 `200` **或幂等重复码** | 见 §6 |

**不要只看 HTTP 状态码。** 探测到的鉴权失败全是 HTTP 200。

---

## 2. 响应外壳：文档写的 vs 探测到的

文档原文：「开放平台接口标准返回值结构包括：状态码 code、错误信息 message、返回数据 data（对象或者数组）」，示例 `{"code":200,"message":"…","data":{…}}`。

无凭证探测（2026-09-11，每条复跑两次结果一致）：

| 场景 | HTTP | Content-Type / body |
| --- | --- | --- |
| 不带 access_token（`vendor/list`） | 200 | `{"code":"310001","message":"access_token不能为空。"}` |
| 假 token（`vendor/list`、`merchant/idempotent/newinsert`、`sd/voucherorder/detail`） | 200 | `{"code":"310036","message":"非法token"}` |
| 未注册路径（任意 `/yonbip/…` 假路径，带假 token） | **404** | `{"code":"310404","message":"网关上没有注册此API[<路径>]，请确认后重新调用"}` |
| 假 token（`/yonbip/fi/fipub/basedoc/querybd/accperiod` 会计期间查询） | 200 | **`text/plain; charset=utf-8`，body 就是 `非法token`** |

<!-- Gap: 文档称开放平台接口统一返回 {code, message, data} JSON 结构；无凭证探测（2026-09-11，P7 三次一致）POST /yonbip/fi/fipub/basedoc/querybd/accperiod?access_token=test 返回 HTTP 200、Content-Type text/plain，body 为纯文本「非法token」 -->
**并非所有接口都返回 JSON。** 会计期间查询在 token 非法时返回纯文本 `非法token`（HTTP 200），与文档「标准返回值结构」不符。
客户端解析 JSON 失败时要把原文当错误信息处理，并按 token 失效走刷新流程。

观察到的规律：

1. 平台级错误的 `code` 是**字符串**（`"310001"`），而文档示例的成功 `code` 是数字 `200`——比较前统一转字符串。
2. 网关先校验路径，再校验 token：`310404` 优先于 `310036`。
3. 平台码的 message 与文档码表措辞不同（文档 `310036` 写「access_token验证失败」，实际 `非法token`），按 `code` 判断，不要匹配 message。

---

## 3. 平台码表（文档原文）

**平台级**

| code | 说明 | 处理 |
| --- | --- | --- |
| 200 | 调用成功 | |
| 202 | 幂等接口，后端服务正在处理中 | 稍后用**相同** resubmitCheckKey 取结果 |
| 10004 | 幂等接口，重复提交请求 | 不同请求换新键；相同请求从 data 取主键（⚠ 与幂等性页的 `100004` 矛盾，见 §6） |
| 315001 | 未知错误 | 联系管理员 |

**客户端级**

| code | 说明 | 处理 |
| --- | --- | --- |
| 310001 | access_token 不能为空 | URL 上加 `access_token` |
| 310002 | 请求体必须是 JSON 结构 | |
| 310003 | 获取 token 失败 | |
| 310005 | 应用不存在 | |
| 310006 | 应用已停用 | 启用应用 |
| 310008 | 参数校验失败，缺少必填参数 | |
| 310015 | 参数校验错误，未通过参数正则匹配 | |
| 310023 | 参数类型校验失败 | |
| 310025 | 文件大小超过限制 | |
| 310031 | 系统级 IP 访问控制 | |
| 310032 | 触发了系统级限流 | 稍后再试 |
| 310036 | access_token 验证失败 | token 有时效，失效后重新获取 |
| 310037 | API 未被授权 | 管理员在「开放平台 → API 授权」勾选该 API 所在末级分类 |
| 310038 | 应用级 IP 访问控制 | |
| 310039 | 触发了应用级限流 | 稍后再试 |
| 310041 | 产品级 IP 访问控制 | |
| 310042 | 触发了产品级限流 | 稍后再试 |
| 310046 | 触发了 API 级限流 | 稍后再试 |
| 310047 | API 级 IP 访问控制 | |
| 310404 | 网关上没有注册此 API | 检查路径 / 是否发布 |
| 310405 | 请求方法不允许 | 检查 GET / POST |

**服务端级**

| code | 说明 |
| --- | --- |
| 310007 | 初始化 API 信息出错 |
| 310009 | 参数赋默认值时格式转换错误 |
| 310043 | 此 API 触发熔断 |
| 310061–310066 | 各类插件执行报错 / 业务扩展插件返回为空 |
| 310071 | HTTP 请求失败（后端服务异常） |
| 310072 | HTTP 连接被拒绝 |
| 310076 | NC 服务请求失败 |
| 310077 | IRIS 服务请求失败 |
| 310504 | 请求超时 |

---

## 4. token 接口与网关查询接口的返回码

- 成功：`"00000"`（文档原文）。
- 无凭证探测（2026-09-11）：伪造 appKey 调 token 接口（新旧路径、两个主机）均返回 HTTP 200 +
  `{"code":"10018","message":"应用不存在或appKey已停用"}`。`10018` 不在 §3 任何表里。
- 无凭证探测（2026-09-11）：伪造 tenantId 调数据中心查询返回 HTTP 200 + `{"code":"500","message":"根据租户id获取网关地址出现异常"}`。
- ⚠ 文档未说明：签名错误、时间戳过期、appSecret 错误时 token 接口分别返回什么（需真实 appKey 才能区分）。

---

## 5. 业务错误的几种形态

各 API 详情里的错误示例（文档原文）形态不统一：

| 形态 | 出现在 |
| --- | --- |
| `{"code":"999","message":"服务端逻辑异常"}`（或数字 `999`） | 订单、供应商、物料、组织等大多数接口 |
| `{"code":"404","message":"凭证保存不成功,账簿code不能为空！","data":{}}` | 凭证保存 / 列表 / 删除——**业务失败码 "404"，HTTP 并非 404** |
| `{"message":"客户名称不能为空!","code":0,"data":null}` | 客户档案保存 |
| `{"success":false,"message":"…","data":null,"code":0}` | 会计期间查询 |
| `{"code":999,"message":"操作失败","displayCode":"XXX-XXX-XXXXXX","level":0}` | 组织 / 部门接口 |
| `code "200"` + `data.failCount > 0` + `data.messages[]`（或字符串） | 批量保存、提交 / 审核 / 删除 |

`displayCode` 是 2025-07-18 起新增的「业务异常码」（公告原文：「业务异常码是对错误码的细化，返回参数中增加 displayCode 字段，
请开发者根据业务异常码（displayCode）做不同异常的处理」）；`level` 0 错误 / 1 警告。多数 API 的业务异常码表在抓取时为空。

建议的统一判定：

```python
def check(resp: dict) -> dict:
    code = str(resp.get("code"))
    if code != "200" or resp.get("success") is False:
        raise YonBIPError(code, resp.get("displayCode"), resp.get("message"))
    data = resp.get("data")
    if isinstance(data, dict) and data.get("failCount"):
        raise YonBIPPartialFailure(data.get("messages"), data.get("infos"))
    return resp
```

---

## 6. MDD 幂等：resubmitCheckKey

文档「幂等性」页原文要点：

- 网关支持**基于用友 MDD 框架**的接口幂等；目前只支持**单条数据保存接口**，且「只对 body 体是 data 的结构有效」。
  哪些接口支持：看 API 详情 JSON 的 `idempotent` 字段（`"mdd"` 支持，`"non"` 不支持）。本 skill 覆盖的 `mdd` 接口：
  采购订单 `singleSave_v1`、销售订单 `singleSave` 与 `delete`、客户 `idempotent/newinsert`、物料 `idempotent/save`、凭证 `addVoucher`。
- 用法：在 `data` 对象里加 `resubmitCheckKey`，**长度不超过 32 位**；有上游单据用上游单据 ID，没有则由调用方确保「同一个接口在租户内唯一」。
- 网关会在键上拼接 apiId 与 tenantId；成功结果缓存 **1 小时**。
- 1 小时内用同一个键重复调用：返回第一次的成功结果（格式同正常成功）。
- 1 小时后用同一个键：返回重复提交码，`data` 里只有主键 `{"id": …}`。
- 调用方注意事项（原文）：出现超时 `310504` 或处理中 `202` 时，「可以使用相同的 resubmitCheckKey，等待 5 秒后重新请求接口」；
  「判断返回结果 code，若为 200 或者 100004 都是接口处理成功了，仅从返回数据 data 里获取主键 id 值」。

⚠ 文档自相矛盾：重复提交码在「返回码说明」表里是 `10004`，在「幂等性」页正文与示例里是 `100004`。两个都当成功处理。

⚠ 文档未说明：凭证保存 `addVoucher` 标为 `mdd` 但请求体没有 `data` 外壳，resubmitCheckKey 放哪；该接口另有 `businessId`（业务幂等校验）。

```python
import time, uuid

def save_idempotent(api, path: str, data: dict, key: str | None = None, tries: int = 4) -> dict:
    data = dict(data, resubmitCheckKey=(key or uuid.uuid4().hex)[:32])   # 同一业务重试必须用同一个键
    for i in range(tries):
        try:
            r = api.raw("POST", path, body={"data": data})               # raw：不抛业务错，返回 dict
        except TimeoutError:
            time.sleep(5); continue
        code = str(r.get("code"))
        if code in ("200", "100004", "10004"):
            return r["data"]
        if code in ("202", "310504"):
            time.sleep(5); continue
        raise RuntimeError(r)
    raise RuntimeError("幂等重试耗尽")
```

非 MDD 接口（提交、审核、批量保存等）**没有**网关幂等：超时后先查单据状态再决定是否重发。

---

## 7. 限流

- 触发码：`310032` 系统级、`310039` 应用级、`310042` 产品级、`310046` API 级（§3）。文档处理建议只有「请稍后再试」；
  ⚠ 文档未说明窗口、配额和是否返回 Retry-After，按指数退避重试。
- 平台公告里公布的「免费调用次数」（摘录与本 skill 相关的部分）：

| 生效 | 接口 | 免费调用次数 |
| --- | --- | --- |
| 2026-03-31 | 销售订单列表查询 `/yonbip/sd/voucherorder/list`、详情 `/yonbip/sd/voucherorder/detail`、单个保存 `/yonbip/sd/voucherorder/singleSave` | 60 次/分钟 |
| 2025-09-15 | 财务云一批接口，如凭证类型查询 `/yonbip/AMP/yonbip-fi-epub/vouchertype/bill/list`、会计期间方案查询 `/yonbip/digitalModel/bill/list`、成本中心批量新增 `/yonbip/AMP/bd/v1/integration/costcenter/batchSave`、固定资产若干审核接口 | 40 次/分钟 |
| 2025-10-15 | 人力云时间管理一批接口（休假、出差、加班、排班、考勤日报等 `/yonbip/hrcloud/time/…`） | 40 次/分钟 |

- ⚠ 文档未说明「免费调用次数」之外是被限流拒绝还是计费（API 详情 JSON 有 `chargeStatus` 字段，公开文档未解释）。
- 事件推送侧的限流在订阅页配置（`events.md` §1）。

---

## 8. 平台行为变更（按公告）

| 公告日期 | 变更 | 对代码的影响 |
| --- | --- | --- |
| 2025-02-21 | 自 3 月 15 日起，勾选「入参映射（过滤未知参数）」的 OpenAPI，入参值为 `null` 时由「开放平台丢弃」改为「**透传到后台领域服务参与处理**」 | 不要用 `null` 表示「不修改」；不改的字段直接不传 |
| 2025-07-22 | 7 月 18 日起：API 分类树改为「领域云-领域-应用-业务对象」四级；**接口版本化**（v1、v2…，不同版本允许不兼容，首选最新版）；历史版本与「即将废弃」接口需勾选「展示历史 API」才显示；新增业务异常码 `displayCode` | 按 URL 而不是名称检索历史接口；新接入用最新版本；避开标为 deprecated 的接口 |
| 2025 起多次 | 「OpenAPI 接口下架公告」 | 定期关注公告；开放平台提供公告与接口变更订阅（2026-01-26 上线） |
| 2026-03-27 | 公有云所有 OpenAPI 端点禁用 TLS 1.0/1.1 与不安全套件，最低 TLS 1.2 | 老 JDK（7 以下）、老 HttpClient 需升级 |

本 skill 覆盖接口里标为已废弃的：旧版「凭证列表查询」、旧版「物料档案保存」「自定义保存物料档案」、供应商「属性」两个查询接口。

---

## 9. 排错清单

| 现象 | 先查 |
| --- | --- |
| `310404` + HTTP 404 | 路径是否与 API 详情「请求地址」一致（示例 URL 常写错，如 `/yonsuite/` 前缀、`_copy` 后缀）；gatewayUrl 是否已含 `/iuap-api-gateway` |
| `310036` / 纯文本 `非法token` | token 过期（2 小时）、token 未 URL 编码、token 属于别的数据中心 |
| `310037` | 应用未授权该 API 分类 |
| token 接口 `10018` | appKey 错或应用停用；tokenUrl 与租户数据中心不匹配 |
| `310008` / `310015` / `310023` | 必填、正则、类型；布尔 / 数字是否写成了字符串 |
| `999 服务端逻辑异常` | 编码在该租户是否存在（组织、客户、物料、税目、交易类型）；`_status` 是否缺失；金额是否自洽 |
| 批量 `code 200` 但数据没变 | `data.failCount`、`data.messages` |
| 同一单据被建了两次 | 保存接口是否传了稳定的 `resubmitCheckKey`；是否在非幂等接口上盲目重试 |

---

## 10. 本文件的 ⚠ 汇总

- Gap（探测证实）：会计期间查询在假 token 时返回 `text/plain` 纯文本 `非法token`，不是文档所说的标准 JSON 结构——§2
- ⚠ 文档自相矛盾：重复提交码 `10004`（码表）vs `100004`（幂等性页）——§3 §6
- ⚠ 文档自相矛盾：`310036` message 措辞（文档「access_token验证失败」，实测「非法token」）——§2
- ⚠ 文档未说明：token 接口错误码表（探测到 `10018`）；网关查询错误码（探测到 `"500"`）——§4
- ⚠ 文档未说明：凭证保存无 `data` 外壳时的幂等键位置——§6
- ⚠ 文档未说明：限流窗口 / 配额 / 超出免费次数后的处理与计费——§7
