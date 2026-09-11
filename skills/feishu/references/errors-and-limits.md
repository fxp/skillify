# 错误码、频控与分页

来源：`open.feishu.cn/document/server-docs/api-call-guide/*`（调用 API、通用错误码、频控策略、IP 白名单）及各接口页（抓取于 2026-09-11）。
**错误码含义均为文档原文，未实测**；标注「无凭证探测（2026-09-11）」的是实际打出来的响应。

## 目录

1. [响应结构](#1-响应结构)
2. [HTTP 状态码的实际形态（探测）](#2-http-状态码的实际形态)
3. [通用错误码速查](#3-通用错误码速查)
4. [频控](#4-频控)
5. [分页通用规则与各接口 page_size 上限](#5-分页)
6. [IP 白名单](#6-ip-白名单)
7. [重试策略](#7-重试策略)
8. [排查手段](#8-排查手段)

---

## 1. 响应结构

绝大多数 OpenAPI 的响应体：

```json
{"code": 0, "msg": "success", "data": { }}
```

- `code == 0` 才是成功。**不要用 `msg` 判断**：文档明确 msg 可能随时优化调整。
- 操作类接口成功时可能没有 `data`。
- 失败时还有 `error` 对象：

```json
{"code": 99991672, "msg": "...",
 "error": {"log_id": "...", "troubleshooter": "https://open.feishu.cn/search?from=openapi&log_id=...&code=...",
           "message": "...", "field_violations": [{"field": "para_a", "value": "...", "description": "..."}],
           "permission_violations": [{"scope": "...", "url": "..."}],
           "helps": [{"url": "...", "description": "Learn more about scopes and how to add them: [...]"}]}}
```

  `field_violations` 是参数校验失败的字段；`permission_violations` / `helps` 给出缺的权限和开通链接；`troubleshooter` 链接可直接打开看排查建议。
- 每个响应头都有 **`X-Tt-Logid`**，报障时提供它。
- **例外**：tenant/app access token 接口字段在顶层（`tenant_access_token`、`expire`）；OAuth v3 令牌接口是 `code` + `access_token` 或 `error`/`error_description`；
  自定义机器人 webhook 另带兼容字段 `StatusCode`/`StatusMessage`。见 [auth.md](auth.md)、[messaging-bots.md](messaging-bots.md)。

---

## 2. HTTP 状态码的实际形态

文档说业务失败时"HTTP 状态码为 400 或 500 系列"。无凭证探测（2026-09-11）看到的实际情况更复杂：

| 场景 | HTTP | Content-Type | body |
|---|---|---|---|
| 普通业务接口鉴权失败（通讯录、消息、多维表格、审批、飞书人事、事件出口 IP） | 400 | `application/json` | `{"code":99991661/99991663/99991668,...,"error":{...}}` |
| **换 tenant/app access token 失败** | **200** | `application/json` | `{"code":10003,"data":{},"msg":"invalid param"}` |
| **自定义机器人 webhook 失败** | **200** | `application/json` | `{"code":19001,"data":{},"msg":"param invalid: incoming webhook access token invalid"}` |
| OAuth v3 / v2 令牌端点失败 | 400 | `application/json` | `{"error":"invalid_grant","error_description":"...","code":20003}` |
| **路径不存在** | **404** | **`text/plain`** | `404 page not found` |
| **HTTP 方法不对**（如 GET 换 token 接口） | **404** | **`text/plain`** | `404 page not found` |

另外文档中多维表格错误码表大多标 **HTTP 200 + 1254xxx**（未实测）。

<!-- Gap: 通用错误码表写"99991201 resource not find — 请求路径错误(404)"，无凭证探测（2026-09-11）GET https://open.feishu.cn/open-apis/nonexistent/v1/foo 实际返回 HTTP 404 + text/plain 的 "404 page not found"，没有 JSON、没有 code。 -->
<!-- Gap: 通用错误码表写"99991301 request method doesn't match — 请求方法与接口设置不一致"，无凭证探测（2026-09-11）用 GET 调 /open-apis/auth/v3/tenant_access_token/internal 实际返回 HTTP 404 + text/plain "404 page not found"，没有返回 99991301。 -->

**结论（写代码的规则）**：

1. 先判 `Content-Type` 是否 JSON，再 `resp.json()`；路径 / 方法写错时直接 `.json()` 会抛解析异常，而不是拿到错误码。
2. 不能靠 `raise_for_status()` 判成功：token 接口和 webhook 失败都是 200。**统一判 body 的 `code == 0`**。
3. 看到纯文本 `404 page not found`，先查 URL 拼写、`/open-apis` 前缀、HTTP 方法。

```python
def call(method, path, **kw):
    r = requests.request(method, f"{BASE}{path}", timeout=kw.pop("timeout", 10),
                         headers={"Authorization": f"Bearer {tenant_access_token()}", **kw.pop("headers", {})}, **kw)
    if "application/json" not in r.headers.get("Content-Type", ""):
        raise RuntimeError(f"HTTP {r.status_code} non-JSON ({r.text[:80]!r}) — check path/method")
    body = r.json()
    if body.get("code") != 0:
        raise FeishuError(body.get("code"), body.get("msg"), r.headers.get("X-Tt-Logid"), body.get("error"))
    return body.get("data")
```

---

## 3. 通用错误码速查

### 3.1 鉴权 / 权限（最常见）

| code | 含义 | 处理 |
|---|---|---|
| 99991661 | 没带 token（**也包括没写 `Bearer ` 前缀**，探测证实） | 头写成 `Authorization: Bearer <token>` |
| 99991663 | tenant_access_token 无效：过期，或**该接口不支持 tenant token** | 刷新 token；查接口文档 Authorization 一栏 |
| 99991664 / 99991665 | app_access_token / tenant_access_token 非法 | |
| 99991668 | user_access_token 无效或异常 | 按 msg 判断：失效就重新授权或刷新 |
| 99991677 | user token 过期 | 用 refresh_token 刷新 |
| 99991669 | refresh token 非法 | 重新授权 |
| 99991671 | token 格式错误（描述写 must start with t-/u-，⚠ 与新版 `eyJ` user token 矛盾，见 auth.md） | |
| 99991672 | 应用没申请该 API 权限 | 按返回的 scope 去开发者后台开通并发版 |
| 99991679 | 用户未授予该权限 | 重新发起授权，scope 拼上缺的权限 |
| 99991673 / 99991662 | 应用在当前租户不可用 / 已停用 | |
| 99991401 | IP 不在应用 IP 白名单 | 第 6 节 |
| 99991403 | **本月 API 调用次数已达上限**（自建应用调用量上限） | 联系管理员升级飞书版本 |
| 10003 | 参数无效（探测：换 token 时 app_id 不存在即返回此码） | |
| 10014 / 10015 | 应用状态不可用 / App Secret 错误 | |
| 20005 / 20006 | access_token 无效 / user token 过期 | |

### 3.2 ID 类（多为 `user_id_type` 用错）

| code | 含义 |
|---|---|
| 99992351 | 这些 open_id 不存在 |
| 99992360 | user_id 不存在 |
| 99992361 | **open_id 不属于当前应用**（A 应用拿到的 open_id 拿到 B 应用用；测试应用和正式应用也是两个应用） |
| 99992364 | 不能用其他租户的 user_id；也用于 union_id 不存在 |
| 99992381 | union_id 不属于当前租户 |
| 99992354 | message_id 不存在 |
| 99992355 / 99992356 | chat_id 不存在 |
| 99992357 / 99992380 | 部门 ID 不存在 |
| 40051 / 40052 / 40054 | open_id 非法 / 部门 ID 不存在 / user_id 与 open_id 至少提供一个 |

### 3.3 通讯录

`40004` 应用没有该部门的通讯录权限范围；`41050` 无用户权限（tenant token 看应用通讯录范围，user token 看用户组织架构可见范围）；
`40001` 商店应用不允许改通讯录；`40157`/`40161` 不能操作 / 查询根部门 0；`40162`/`43010` 子部门 >500 不支持递归；
`40009`/`40011`/`40012`/`40040`/`40041` 分页参数问题；更多见 [contacts.md](contacts.md)。

### 3.4 消息 / 机器人

`230xxx`（发送消息专有，见 [messaging-bots.md](messaging-bots.md)）；`10002`/`10030`/`11201` 机器人不在会话中；`11205`/`11240` 应用没开机器人能力；
`11225` 机器人对用户不可见（改可用范围并发布）；`11232`/`11233`/`11247` 创建消息触发限流；`19036` 消息超过 30 KB；
自定义机器人 `9499`（请求体格式错）、`19021`（签名）、`19022`（IP）、`19024`（关键词）、`19001`（hook 无效，探测所见，⚠ 文档未说明）。

### 3.5 审批

`60001` 参数错误；`60002` approval_code 找不到；`60003` instance_code 找不到；`60004` 用户找不到；`60005` 部门验证失败；
`60006` 表单校验失败；`60009` 权限不足；`60010` task_id 找不到；`60011` 付费审批免费版不能发起；`60012` uuid 冲突；
`1390001` 参数错误（含表单控件）；`1390015` 审批定义已停用；`1395001` 服务错误。见 [approval.md](approval.md)。

### 3.6 可重试的服务端错误

`1500`、`1663`、`1668`、`2200`（频繁调用时出现）、`5000`、`55001`、`65001`、`10101`、`20050`（OAuth）、`20072`（OAuth 503）、`1161000`（飞书人事）。

---

## 4. 频控

### 4.1 触发后的响应

HTTP **429**（部分旧版 OpenAPI 为 **400**），body `{"code":99991400,"msg":"request trigger frequency limit"}`，响应头：

| 头 | 含义 |
|---|---|
| `x-ogw-ratelimit-limit` | 窗口期上限 |
| `x-ogw-ratelimit-reset` | 距恢复的秒数——**等这么久再重试** |

处理：等待 `x-ogw-ratelimit-reset` 秒 → 重试 → 仍 429 则继续按该头延迟。判断限流要同时看 HTTP 429、HTTP 400 + `code 99991400`。

### 4.2 频控等级

按**每个 API × 每个应用 × 每个租户**计算；写接口通常比读接口低；同时存在 QPM 和 QPS 时任一超限都触发。

| 等级 | 限制 | 等级 | 限制 |
|---|---|---|---|
| 1 | 10 次/分 | 7 | 10 次/秒 |
| 2 | 20 次/分 | 8 | 20 次/秒 |
| 3 | 100 次/分 | 9 | 50 次/秒 |
| 4 | 1000 次/分 & 50 次/秒 | 10 | 基础版 50 次/秒，商业版 100 次/秒 |
| 5 | 1 次/秒 | 11 | 100 次/秒 |
| 6 | 5 次/秒 | 21 | 3 次/秒 |
| 特殊频控 | 非标准，联系技术支持 | | |

**不能自助提频**；数据迁移、大型活动可找企业的 CSM。**消息、群组、多维表格暂时不支持提频。**

### 4.3 本 skill 覆盖接口的频控（各接口页原文）

| 接口 | 频控 |
|---|---|
| 获取 / 刷新 user_access_token、授权页 | 1000 次/分钟、50 次/秒 |
| 通讯录用户读写、部门子部门、batch_get_id、scopes | 1000 次/分钟、50 次/秒 |
| 获取单个部门 `GET /contact/v3/departments/:id` | 特殊频控 |
| 发送 / 回复 / 编辑 / 撤回消息、群列表 | 1000 次/分钟、50 次/秒；**另：同一用户 5 QPS、同一群 5 QPS** |
| 自定义机器人 webhook | 单租户单机器人 100 次/分钟、5 次/秒；避开整点半点（11232） |
| 多维表格：创建 app | 20 次/分钟 |
| 多维表格：记录增删改（含批量） | 50 次/秒；同一多维表格建议串行写 |
| 多维表格：查询记录、批量获取、列字段 / 数据表 | 20 次/秒 |
| 审批：创建实例、撤回、同意 / 拒绝 / 转交、批量取实例 ID、订阅、查看定义 | 100 次/分钟 |
| 审批：查询实例列表 / 任务列表 | 1000 次/分钟、50 次/秒 |
| 飞书人事：批量查询员工、搜索员工、查询 / 搜索待入职 | 100 次/分钟 |
| 飞书人事：添加人员 | **20 次/分钟** |
| 飞书人事：创建待入职、完成入职、更新待入职 | 1000 次/分钟、50 次/秒 |
| 飞书人事（标准版）花名册 | 100 次/分钟 |

---

## 5. 分页

所有列表接口统一：

- 请求：`page_size`、`page_token`（**首次不传**）。
- 响应：`data.has_more`（布尔）、`data.page_token`——**只有 `has_more=true` 时才返回 page_token**。
- 循环条件用 `has_more`，不要用"items 为空"或"page_token 为空"之外的启发式。
- 翻页过程中排序参数（如 `sort_type`）不能变。

| 接口 | page_size 默认 / 上限 |
|---|---|
| 通讯录：部门直属用户、子部门 | 10 / **50** |
| 通讯录：授权范围 scopes | 50 / 100（三类资源合计） |
| 事件出口 IP | — / 50 |
| 群列表 `GET /im/v1/chats` | 20 / 100 |
| 历史消息 `GET /im/v1/messages` | 20 / 50 |
| 多维表格：查询记录 search | 20 / **500** |
| 多维表格：列出数据表、字段 | 20 / 100 |
| 审批：批量取实例 ID | 100 / 100（且时间窗 ≤10 小时） |
| 飞书人事：搜索员工 | 必填 / 100 |
| 飞书人事：查询待入职 | 必填 / **10** |
| 飞书人事 v1：任职信息 `job_datas` | 必填（**string 类型**）/ ⚠ 文档未说明 |
| 飞书人事（标准版）花名册 | 10 / 100 |

分页相关错误：`40009`（page size 超 50）、`40011`/`40041`（page_size 非法）、`40012`/`40040`/`100001`（page_token 非法）、`1254011`（多维表格 page_size 须 >0）。

---

## 6. IP 白名单

- 开发者后台「安全设置 → IP 白名单」，默认**不开启**，配置后立即生效。
- 只支持 **IPv4 公网单个地址**，不支持网段（注意：自定义机器人的 IP 白名单支持网段，是另一套设置）。
- **对获取 access_token 的接口不生效**。
- 不在白名单的请求返回 `99991401 ip %s is denied by app setting`。

---

## 7. 重试策略

基于文档的建议（策略本身未实测）：

| 情况 | 做法 |
|---|---|
| HTTP 429，或 HTTP 400 + `code 99991400` | 按 `x-ogw-ratelimit-reset` 等待后重试 |
| `11232`/`11233`/`11247`/`230020` 消息限流 | 退避重试；自定义机器人错开整点半点 |
| 3.6 节的服务端错误 | 指数退避，有限次数 |
| 99991663 / 99991677（token 过期） | 刷新 token 后**重试一次** |
| 99991672 / 99991679 / 40004 / 41050 / 230013 等权限与范围类 | **不要重试**，是配置问题：开权限、改范围、发布应用 |
| 1254002（多维表格并发写） | 减小批量、串行 |
| 写接口重试 | 带上幂等键：消息 `uuid`、多维表格 `client_token`、审批 `uuid`、通讯录 `client_token` |

---

## 8. 排查手段

1. 响应里的 `error.troubleshooter` 链接：直接给出错误原因分析。
2. 响应头 `X-Tt-Logid`：在开放平台官网搜索，或在开发者后台「日志检索 → 服务端日志检索」过滤。
3. 事件没收到：「日志检索 → 事件日志检索」。
4. API 调试台 `https://open.feishu.cn/api-explorer`：可一键取 token、复制各类 ID、生成 SDK 示例代码（私有化环境不支持）。
