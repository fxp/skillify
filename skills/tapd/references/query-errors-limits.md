# 通用查询语法、分页、响应结构、错误码与频率限制

> 来源：`https://open.tapd.cn/document/api-doc/` 下「API文档/使用必读」「API文档/API错误码」「API文档/subject/gzip/」及各接口页（抓取于 2026-09-11）。
> **文档版，未用真实凭证调用验证。** 标「无凭证探测（2026-09-11）」的结论已用伪造凭证复跑两次、结果一致（命令见 `tapd-workspace/probe-log.md`）；
> 其余错误码、行为描述均为「文档原文，未实测」。

## 目录
1. 请求格式（先看：文档示例命令里有个隐形字符）
2. 响应结构与成功判定
3. 查询语法：时间、枚举、模糊、不等于、多值、`field=OP<...>`
4. 分页：limit / page / 深分页上限 / 游标
5. 人员、时间、ID、优先级的格式约定
6. 错误码（文档）与无凭证探测结果
7. 频率限制与重试
8. gzip
9. 参考客户端（Python）
10. ⚠ 本文件汇总

---

## 1. 请求格式

- Base URL：`https://api.tapd.cn`。无凭证探测（2026-09-11）：`http://` 不跳转、直接处理，凭证会明文发出——必须写 https。
- **GET**：参数全部放 URL，并做 urlencode（使用必读原文举例 `order=id%20desc`）。
- **POST**：支持两种 body，要配对 Content-Type（使用必读原文）：
  - `application/x-www-form-urlencoded`（文档所有 curl 示例都用 `-d`，即这种）
  - `application/json`——**必须**加 `Content-Type: application/json`
  - 文件上传：`multipart/form-data`
- 创建和更新是**同一个 POST 路径**，带 `id` 就是更新（`POST /stories`、`/bugs`、`/tasks`、`/iterations`、`/timesheets`、`/tcases`）。文档里没有 PUT / PATCH / DELETE 方法的接口。
- 返回格式默认 JSON，URL 加 `__format=xml` 可要 XML（使用必读原文）。无凭证探测：401 错误响应即使带了 `__format=xml` 仍是 JSON。

<!-- Gap: 使用必读页（API文档/使用必读.html）全部 18 处示例命令写成 `curl –u`，其中是 EN DASH（U+2013）而不是 ASCII 减号。无凭证探测（2026-09-11，两次一致）：原样执行 `curl –u 'test:test' '.../stories/count?workspace_id=1'`，curl 把 `–u` 当成主机名（Could not resolve host: –u），`test:test` 当成第二个 URL，最后对真实 URL 发出的请求**不带任何凭证**，返回 401。复制文档示例时要把 `–u` 改成 `-u`；API配置指引页的示例是正常的 `-u`。 -->

## 2. 响应结构与成功判定

所有接口统一三字段（使用必读原文）：
| 字段 | 说明 |
|---|---|
| `status` | `1` 代表成功，其他代表失败 |
| `info` | 返回说明；出错时是错误信息 |
| `data` | 数据 |

**`data` 的形状因接口而异**，写解析代码时按这张表来：
| 接口类型 | `data` 形状 | 例 |
|---|---|---|
| 列表 | 数组，每项外面**包一层对象名** | `[{"Story": {...}}, {"Story": {...}}]`；缺陷 `Bug`、任务 `Task`、迭代 `Iteration`、工时 `Timesheet`、用例 `Tcase`、测试计划 `TestPlan`、项目 `Workspace`、成员 `UserWorkspace`、需求变更 `WorkitemChange`、缺陷变更 `BugChange` |
| 创建 / 更新 | 单个包装对象 | `{"Story": {...}}` |
| 计数 | `{"count": N}` | `/stories/count` |
| 字段元数据 | 以字段名为 key 的对象 | `/stories/get_fields_info` |
| 状态映射 | 英文 key → 中文名 | `/workflows/status_map` |
| 锁定迭代 | 字符串 | `"lock 1010... successfully"` |
| 推送事件 | 无 `data` 字段 | `/open_app_events/hook` |

**成功判定要同时看三件事：**
1. HTTP 状态码 200；
2. `body["status"] == 1`；
3. **`data` 的形状符合预期**——无凭证探测（2026-09-11，两次一致）：请求一个**不存在的顶层路径**（如把 `/stories` 拼成 `/storys`），
   即使**不带任何凭证**也返回 HTTP 200 + `{"status":1,"data":"Hello world from TAPD API. <随机串>","info":"Documents can be found in https://www.tapd.cn/help/view#1120003271001002318"}`。
   只判 `status == 1` 会把拼错的路径当成成功。已存在资源下的未知子路径（`/stories/not_a_real_action`）则先做鉴权、返回 401（带有效凭证时的行为未验证）。

## 3. 查询语法

来源：使用必读「数据查询接口特别说明」。各接口参数表的「特殊规则」列会标明某个字段支持哪种查询。

| 语法 | 写法（URL 解码后） | 例 |
|---|---|---|
| 时间：早于 | `created=<2016-01-01` | 等号后紧跟 `<` |
| 时间：晚于 | `created=>2016-01-01` | 等号后紧跟 `>` |
| 时间：区间 | `created=2016-02-01~2016-02-29` | 也支持到秒：`created=2024-12-23 14:00:00~2024-12-23 23:59:00` |
| 枚举（或） | `status=new\|in_progress` | 竖线 |
| 模糊匹配 | `title=api` | 标注「支持模糊匹配」的字段直接传即 LIKE |
| 不等于 | `iteration_id=<>1120003271001000275` | |
| 多 ID | `id=a,b,c` | **英文逗号** |
| 多人员：或 | `participator=A\|B` | |
| 多人员：与 | `participator=A;B` | |
| `LIKE` | `custom_field_one=LIKE<安卓>` | 任何字段都可用 |
| `LIKE_OR` | `name=LIKE_OR<安卓\|苹果>` | 多值模糊，任一匹配 |
| `EQ` | `name=EQ<完整标题>` | 全等（绕开模糊匹配） |
| `NOT_EQ` | `name=NOT_EQ<完整标题>` | 全等不匹配 |
| `CONTAINS` | `custom_field_1=CONTAINS<v1\|v2\|v3>` | 仅需求 / 缺陷 / 任务的多选自定义字段，同时包含 |
| `CONTAINS_OR` | `custom_field_1=CONTAINS_OR<v1\|v2>` | 同上，包含任一 |
| `USER_OR` | `owner=USER_OR<user1\|user2>` | 仅需求 / 缺陷 / 任务的用户字段 |

- 这些 `<`、`>`、`~`、`|`、空格都要 urlencode；用 `requests` 的 `params=` 会自动编码，手拼 URL 时别忘了。
- 使用必读原文特别提醒「要特别注意等号的位置和日期格式」——没有 `created_gt`、`modified_since`、`start/end` 这类参数，按别家习惯写会被当成未知参数。
- `name` / `title` 默认就是模糊匹配：按标题精确找一条要用 `EQ<...>`，或拿回结果后自己再精确过滤。

```python
params = {
    "workspace_id": WS,
    "modified": "2026-09-10 00:00:00~2026-09-10 23:59:59",
    "status": "planning|developing",
    "name": "EQ<支付回调超时重试>",
    "owner": "USER_OR<zhangsan|lisi>",
}
requests.get("https://api.tapd.cn/stories", auth=AUTH, params=params, timeout=30)
```

## 4. 分页

使用必读原文：
- 列表接口默认 30 条，`limit` 最大 **200**；`page` 从 1 开始。总数用对应的 `/count` 接口。
- **深分页上限：`page * limit` 最大 20000**（即 limit=200 最多翻到第 100 页），超过「服务端会返回错误」（错误码 / 文案 ⚠ 文档未说明）。
- **超过 20000 条改用游标：**
  1. 游标 = 上一页最后一条数据的 `id`；
  2. 翻页传 `cursor=<id>`，无需再递增 `page`；
  3. **仅支持 id 排序**（默认 `id DESC`，或显式 `order=id asc`），其他排序字段只能在 20000 深度以内翻；
  4. 翻页过程中查询条件、`limit`、排序不能变，且**串行翻页**，同一查询条件不要并发。
- 例外：需求变更历史 `GET /story_changes` 的 `limit` 最大 **100**；缺陷变更 `GET /bug_changes` 最大 200。
- 部分接口「无分页」一次返回全部：`/workspaces/users`、`/workspaces/projects`、`/workspaces/user_participant_projects`、`/stories/get_fields_info`。

```python
def iter_all(path, wrapper, params, limit=200):
    """按游标遍历（默认 id DESC）。wrapper 如 'Story' / 'Bug' / 'Tcase'。"""
    base = {k: v for k, v in params.items() if k not in ("page", "order", "cursor")}
    base["limit"] = limit
    cursor, seen = None, set()
    while True:
        p = dict(base, **({"cursor": cursor} if cursor else {}))
        data = tapd.call("GET", path, params=p)
        rows = [row[wrapper] for row in data]
        rows = [r for r in rows if r["id"] not in seen]    # 文档未说明游标是否包含边界那条，去一次重
        if not rows:
            return
        for r in rows:
            seen.add(r["id"])
            yield r
        if len(data) < limit:
            return
        cursor = rows[-1]["id"]
```
- 游标翻页在使用必读里只以 `/tcases` 举例，是否所有列表接口都支持 `cursor` ⚠ 文档未逐一说明。拿到凭证后先在目标接口上验证；
  不支持时退回「按 `modified` / `created` 时间窗切片 + page 翻页」，把每个窗口控制在 20000 条以内。
- 使用必读的游标示例 URL 里残留模板变量 `{{ $page.apiHost }}`，实际应为 `https://api.tapd.cn`。

## 5. 格式约定

| 项 | 约定 | 来源 |
|---|---|---|
| 人员字段 | 填 TAPD **昵称**（`/workspaces/users` 的 `user`），文档写入示例常带结尾分号：`owner=anyechen;`、`current_owner=anyechen;`；读回也是 `"anyechen;"` | update_story / update_bug / get_bugs_count 示例 |
| 多个处理人 | 写入时的分隔规则 ⚠ 文档未明确说明（查询时 `\|` 为或、`;` 为与；返回值用 `;` 分隔） | 使用必读 |
| 日期 | `YYYY-MM-DD`（`begin`、`due`、`startdate`、`spentdate`） | 各参数表 `date` 类型 |
| 时间 | `Y-m-d H:i:s`，如 `2017-04-12 09:04:29`；**不带时区** ⚠ 时区文档未说明 | webhook_document、各示例 |
| 空时间 | `null`；部分示例出现 `0000-00-00 00:00:00` | custom_fields_settings、get_test_plan_tcase 示例 |
| ID | 19 位长 ID，JSON 里是**字符串**；JS / TS 不要转 Number | 各示例 |
| 未关联 | `iteration_id` / `story_id` / `parent_id` 为 `"0"` | 各示例 |
| 标签 | 多个用 `\|` 分隔，不存在自动创建 | 各创建接口 |
| 优先级 | 用 `priority_label`，不用旧 `priority` 的数字 / 英文映射 | subject/custom_priority |

## 6. 错误码

### 文档的错误码表（API错误码.html，文档原文，未实测）
| 错误码 | 说明 | 排查建议 |
|---|---|---|
| `401 Unauthorized` | 账号密码没有传 / 错误 / 代码问题 | 检查是否传了账号密码、是否正确 |
| `404 workspace 1010480 not existed` | 项目 ID 不存在或错误 | 核实 workspace_id |
| `422` | 通常为参数错误或必填参数没填 | 看提示语 |
| `429 To many requests, api account brookechen max request rates is 6000req/10min` | 超过请求频率限制 | 降低频率；「默认频率为60req/1min」 |
| `500` | 服务器报错，属于超大量请求超频出现 | 减少请求频率 |
| `502` | ① 并发太多 ② 单次返回数据量超大（如变更历史） | 降低并发；传 `limit` 减小每页、再 `page` 翻页 |

### 无凭证探测（2026-09-11，每条两次一致）
| 场景 | HTTP 状态行 | body |
|---|---|---|
| 不带 Authorization | `401 Unauth` + `WWW-Authenticate: Basic realm='TAPD API'` | `{"status":401,"data":"","info":"401 Unauthorized","meta":{"request_id":"..."}}` |
| 伪造 Basic（`-u test:test`） | 同上 401 | 同上 |
| 伪造 Bearer token | **`422 ParamError`** | `{"status":422,"data":"","info":"The access token provided is invalid","meta":{...}}` |
| 拼错的顶层路径（带或不带凭证） | **`200 OK`** | `{"status":1,"data":"Hello world from TAPD API. ...","info":"Documents can be found in ..."}` |
| `http://` 明文 | 401（不跳转 https） | 同 401 |

- 错误 body 的 `status` 字段等于 HTTP 状态码数字（401 / 422），并带 `meta.request_id`——报障时附上。
- token 失效的判断要覆盖 **422 + info 含 `access token`**，不能只看 401。
- 文档表中 404 的描述是「workspace ... not existed」，HTTP 状态行 / body 形状 ⚠ 未实测。

## 7. 频率限制与重试

- ⚠ 文档自相矛盾：429 的示例文案是某账号「6000req/10min」，同一行的排查建议又说「默认频率为60req/1min」（相当于 600 次 / 10 分钟），两个数字差 10 倍。
  可能是按账号单独配置，文档未说明怎么查自己的额度。
- 无凭证探测（2026-09-11，两次一致）：所有响应（包括 401、422、404 路径）都带 `X-RateLimit-Limit: 10000` 和递减的 `X-RateLimit-Remaining`。
  这个 10000 的时间窗口、按 IP 还是按账号计数 ⚠ 文档未说明，与上面两个数字都对不上；带真实凭证时的值未验证。
- 建议：客户端按「60 次 / 分钟」这个文档里最保守的数字做节流；读响应头的 `X-RateLimit-Remaining` 作为参考；
  429 / 500 / 502 指数退避重试；502 同时把 `limit` 调小、加 `fields=` 减小响应体；翻页串行。

## 8. gzip

`subject/gzip/` 原文：推荐调用时启用 gzip——请求头带 `Accept-Encoding: gzip`，响应 `Content-Encoding` 含 gzip 时解压。
Python `requests`、Node `axios`、Go `net/http` 默认自动处理；Java `HttpURLConnection` 要自己加头和 `GZIPInputStream`（文档给了完整 Java 示例）。

## 9. 参考客户端（Python）

```python
import os, time, requests

class TapdError(RuntimeError):
    pass

class Tapd:
    BASE = "https://api.tapd.cn"                       # 只用 https

    def __init__(self, user=None, password=None, bearer=None, min_interval=1.0):
        self.s = requests.Session()
        if bearer:
            self.s.headers["Authorization"] = f"Bearer {bearer}"
        else:
            self.s.auth = (user or os.environ["TAPD_API_USER"], password or os.environ["TAPD_API_PASSWORD"])
        self.min_interval = min_interval               # 1 秒 1 次 ≈ 文档的 60 req/min
        self._last = 0.0

    def call(self, method, path, *, params=None, data=None, json=None, retries=4):
        for attempt in range(retries + 1):
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            r = self.s.request(method, self.BASE + path, params=params, data=data, json=json, timeout=60)
            if r.status_code in (429, 500, 502) and attempt < retries:
                time.sleep(min(120, 5 * 2 ** attempt))
                continue
            try:
                body = r.json()
            except ValueError:
                raise TapdError(f"{method} {path}: HTTP {r.status_code}, non-JSON body {r.text[:200]!r}")
            if r.status_code != 200 or body.get("status") != 1:
                raise TapdError(f"{method} {path}: HTTP {r.status_code} status={body.get('status')} "
                                f"info={body.get('info')} request_id={(body.get('meta') or {}).get('request_id')}")
            d = body.get("data")
            if isinstance(d, str) and d.startswith("Hello world from TAPD API"):
                raise TapdError(f"{path}: 路径不存在（TAPD 对未知路径返回 status=1 的 Hello world）")
            return d
        raise TapdError(f"{method} {path}: 重试 {retries} 次仍失败")

tapd = Tapd()
count = tapd.call("GET", "/bugs/count", params={"workspace_id": os.environ["TAPD_WORKSPACE_ID"]})["count"]
```
- 日志里不要打印 `testauth` 的完整响应（文档示例回显口令字段），也不要打印 Authorization 头。

## 10. ⚠ 本文件汇总
- Gap 1 处：使用必读 18 处 `curl –u`（EN DASH），照抄不带凭证 — 第 1 节
- 深分页超过 20000 时的错误码 / 文案未说明 — 第 4 节
- 游标 `cursor` 只以 `/tcases` 举例，是否全接口支持、是否包含边界记录未说明；示例残留 `{{ $page.apiHost }}` — 第 4 节
- 多处理人写入的分隔规则未明说；时间字段时区未说明 — 第 5 节
- 404 workspace 错误的实际状态行 / body 未实测 — 第 6 节
- 频率：6000req/10min 与 60req/1min 矛盾；探测到的 `X-RateLimit-Limit: 10000` 含义未说明 — 第 7 节
