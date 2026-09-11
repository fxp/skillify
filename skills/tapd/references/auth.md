# 鉴权、凭证与项目前置（workspace_id / 成员 / 长短 ID / SDK）

> 来源：`https://open.tapd.cn/document/api-doc/` 下「API文档/使用必读」「API配置指引」「授权凭证/*」「TAPD OAuth 接入文档」「快速入门/开发应用/*」「next/api/」
> 以及 `api_reference/workspace/*`（抓取于 2026-09-11）。
> **文档版，未用真实凭证调用验证。** 报错与行为描述除标「无凭证探测（2026-09-11）」外，均为「文档原文，未实测」。
> 探测命令全文见 `tapd-workspace/probe-log.md`。

## 目录
1. 先选凭证类型
2. API 账号 + HTTP Basic（企业内部脚本最常用）
3. 开放应用：client_credentials 换 access_token（Bearer）
4. 开放应用直接用 client_id:client_secret 做 Basic
5. 用户态 OAuth（授权码）
6. OAuth 跳转模式（平台级系统）
7. scope、应用权限与安全 IP
8. 项目前置：拿到 workspace_id、公司 ID 与成员昵称
9. 短 ID 换长 ID
10. 官方 SDK 现状
11. ⚠ 本文件汇总

---

## 1. 先选凭证类型

Base URL 只有一个：`https://api.tapd.cn`。所有业务接口（需求、缺陷、任务……）对下面几种凭证都一样，区别只在「请求头怎么带」和「能访问哪些数据」。

| 凭证 | 适合 | 请求头 | 来源页 |
|---|---|---|---|
| **API 账号 + API 口令** | 企业自己的同步脚本、报表、CI 集成 | `Authorization: Basic base64(api_user:api_password)` | 使用必读、API配置指引 |
| 开放应用 `client_id` + `client_secret` 直接 Basic | 开放平台应用，调已授权项目的数据 | `Authorization: Basic base64(client_id:client_secret)` | next/api/、TAPD OAuth 接入文档 第 6 步 |
| 开放应用 access_token（项目态 / 应用态） | 开放平台应用 | `Authorization: Bearer ACCESS_TOKEN` | 授权凭证/项目态、快速入门/开发应用/使用API |
| 用户态 access_token（OAuth 授权码） | 需要「以某个用户身份」读用户信息、用户待办 | `Authorization: Bearer ACCESS_TOKEN` | 授权凭证/用户态 |

- **API 账号不是个人登录账号。** 文档原文：「TAPD API是TAPD的商业化模块，TAPD企业版的公司管理员可以在公司管理>开放集成>API账号管理中申请试用90天」。
  用自己的 TAPD 登录邮箱 + 密码做 Basic 不是文档描述的用法。
- 申请入口两页写法不同：使用必读写「公司管理 > 开放集成 > API账号管理」，API配置指引写「公司管理 -> 开放平台」 ⚠ 文档自相矛盾（可能是改版前后的菜单名）。
- 凭证一律走环境变量：`TAPD_API_USER` / `TAPD_API_PASSWORD`，或 `TAPD_CLIENT_ID` / `TAPD_CLIENT_SECRET`。

## 2. API 账号 + HTTP Basic

### 测试连通
**Endpoint**: `GET /quickstart/testauth`
**用途**: 验证账号口令是否正确，不读业务数据。

**示例请求**
```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" 'https://api.tapd.cn/quickstart/testauth'
```
```python
import os, requests
r = requests.get("https://api.tapd.cn/quickstart/testauth",
                 auth=(os.environ["TAPD_API_USER"], os.environ["TAPD_API_PASSWORD"]), timeout=30)
print(r.status_code, r.json().get("status"), r.json().get("info"))
```

**示例响应**（文档原文，未实测）
```json
{"status":1,"data":{"api_user":"api_user","api_password":"api.password","request_ip":"172.8.8.8"},"info":"success"}
```

**注意事项**
- 文档示例的 `data` 里回显了口令字段 → **不要把 testauth 的完整响应写进日志**。
- 无凭证探测（2026-09-11，两次一致）：不带凭证或伪造 Basic 时返回 HTTP `401 Unauth`，
  body `{"status":401,"data":"","info":"401 Unauthorized","meta":{"request_id":"..."}}`，
  响应头 `WWW-Authenticate: Basic realm='TAPD API'`。
- 使用必读页里的示例命令写的是 `curl –u`（EN DASH，不是减号），照抄会**不带凭证**发出请求，详见 `query-errors-limits.md` 第 1 节的 Gap。
- Basic 头手工拼法（API配置指引原文）：`base64("api_user:api_password")`，例 `api_user:api_password` → `YXBpX3VzZXI6YXBpX3Bhc3N3b3Jk`，
  写成 `Authorization: Basic YXBpX3VzZXI6YXBpX3Bhc3N3b3Jk`。requests 的 `auth=(u, p)`、curl 的 `-u` 会自动完成这一步。
- 必须用 `https://`。无凭证探测（2026-09-11，两次一致）：`http://api.tapd.cn/...` **不跳转**，直接按明文 HTTP 处理并返回 401——
  写成 http 时凭证会以明文发出。

## 3. 开放应用：client_credentials 换 access_token

**Endpoint**: `POST /tokens/request_token`
**用途**: 开放应用用「应用ID + 应用密钥」换项目访问 token（文档称「项目态」，next 文档称「应用态」）。

**关键参数**
| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `grant_type` | POST body | 是 | 固定 `client_credentials` |
| client_id / client_secret | HTTP Basic 头 | 是 | `Authorization: Basic base64(client_id:client_secret)` |

**示例请求**
```bash
curl -u "$TAPD_CLIENT_ID:$TAPD_CLIENT_SECRET" -d 'grant_type=client_credentials' \
  'https://api.tapd.cn/tokens/request_token'
```
```python
import os, time, requests

_token = {"value": None, "exp": 0}

def app_token():
    if _token["value"] and time.time() < _token["exp"] - 300:   # 提前 5 分钟换新
        return _token["value"]
    r = requests.post("https://api.tapd.cn/tokens/request_token",
                      auth=(os.environ["TAPD_CLIENT_ID"], os.environ["TAPD_CLIENT_SECRET"]),
                      data={"grant_type": "client_credentials"}, timeout=30)
    body = r.json()
    if r.status_code != 200 or body.get("status") != 1:
        raise RuntimeError(f"request_token failed: HTTP {r.status_code} {body.get('info')}")
    _token["value"] = body["data"]["access_token"]
    _token["exp"] = time.time() + int(body["data"]["expires_in"])
    return _token["value"]

r = requests.get("https://api.tapd.cn/bugs",
                 headers={"Authorization": f"Bearer {app_token()}"},
                 params={"workspace_id": os.environ["TAPD_WORKSPACE_ID"], "fields": "id,title"}, timeout=30)
```

**示例响应**（文档原文，未实测）
```json
{
  "status": 1,
  "data": {
    "access_token": "24dc73683d28abf36af4cc83a2b8be147b1389aa",
    "expires_in": 7200,
    "token_type": "Bearer",
    "scope": "bug devops iteration release story task tcase webhook webhook wiki app_auth ",
    "resource": {"type": "open_app_auth", "app_id": "404"},
    "now": "2021-07-06 17:08:10"
  },
  "info": "success"
}
```

**注意事项**
- `expires_in` 单位是秒，示例为 7200。**文档没有 refresh_token，也没有刷新接口** ⚠ 文档未说明——过期就重新走 client_credentials。
- 无凭证探测（2026-09-11，两次一致）：
  - 伪造 client 调 `/tokens/request_token` → HTTP 401，body 与 Basic 失败相同。
  - **伪造的 Bearer token 调业务接口返回 HTTP `422 ParamError`**，body `{"status":422,"data":"","info":"The access token provided is invalid",...}`，
    **不是 401**。所以「token 失效时刷新重试」的逻辑不能只判 401，要把 `422` + `info` 含 `access token` 也算进去。
    真实过期 token 是否也是 422 ⚠ 未验证。
- 开放应用只能调「应用权限」里勾选模块的 API（见第 7 节）；设置了安全 IP 后只能从这些 IP 调用。
- `get_workitems_long_id_by_short_ids` 页的第二个示例把 token 放在 query：`...&access_token=ACCESS_TOKEN`，
  而「使用API」页说 token 放 HTTP header ⚠ 文档自相矛盾——query 方式是否被所有接口接受未知，统一用 header。

## 4. 开放应用直接用 client_id:client_secret 做 Basic

文档原文（next/api/）：「应用ID和应用秘钥对应的就是API账号和密码」，示例
`curl -u '应用ID:应用秘钥' 'https://api.tapd.cn/stories?workspace_id=10104801'`；
TAPD OAuth 接入文档第 6 步同样 `curl -u 'client_id:client_secret' 'https://api.tapd.cn/bugs/count?workspace_id=69990779'`。

- 能访问的项目 = 已安装 / 已授权该应用的项目；能访问的接口 = 应用权限里声明的 scope（next/api/「数据权限」）。
- 与第 3 节 Bearer 方式并存，文档没有说明两者在权限、限流上是否有差别 ⚠ 文档未说明。

<!-- Gap: next/api/ 授权凭证页链接的「应用态」页 https://open.tapd.cn/document/api-doc/next/api/API调用说明书/授权凭证/应用态.html 无凭证探测（2026-09-11，两次一致）返回的是站点兜底页（<title>快速开始 | 开放平台文档），不是应用态说明；应用态的实际说明只能看旧版「API文档/授权凭证/项目态.html」。 -->

## 5. 用户态 OAuth（授权码）

**用途**: 以当前 TAPD 用户身份调用「用户态接口」（如 `GET /users/info`、`GET /user_oauth/get_user_todo_story`），或做应用免登。
文档原文：「用户态鉴权仅限访问支持用户态接口」。

**步骤**（授权凭证/用户态.html）
1. 浏览器跳转：
   `https://www.tapd.cn/oauth/?response_type=code&client_id=%s&redirect_uri=%s&scope=%s&state=%s&auth_by=%s`
   - 多个 scope 用空格分隔并 urlencode：`story#read bug#read` → `story%23read%20bug%23read`
   - `auth_by` 目前支持 `user`
2. 用户选公司 → 回跳 `redirect_uri?code=...&state=...&resource={"type":"workspace","workspace_id":10022001}`
   - `code` 有效期 **5 分钟**；`resource` 里的 workspace_id 是本次授权的项目，只能读这个项目的数据
3. 用 code 换 token：`POST https://api.tapd.cn/tokens/request_token`

**关键参数**
| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `grant_type` | body | 是 | 固定 `authorization_code` |
| `redirect_uri` | body | 是 | 与跳转时一致 |
| `code` | body | 是 | 回跳带回的 code |
| client_id / client_secret | Basic 头 | 是 | 同第 3 节 |

**示例请求**
```bash
curl -u "$TAPD_CLIENT_ID:$TAPD_CLIENT_SECRET" \
  -d "grant_type=authorization_code&redirect_uri=$REDIRECT_URI&code=$CODE" \
  'https://api.tapd.cn/tokens/request_token'
```
```python
r = requests.post("https://api.tapd.cn/tokens/request_token",
                  auth=(os.environ["TAPD_CLIENT_ID"], os.environ["TAPD_CLIENT_SECRET"]),
                  data={"grant_type": "authorization_code", "redirect_uri": redirect_uri, "code": code},
                  timeout=30)
tok = r.json()["data"]          # access_token / expires_in / token_type / scope / resource / now
```

**示例响应**（文档原文，未实测）：与第 3 节同结构，`resource` 为 `{"type":"workspace","workspace_id":10104801}`，示例 `expires_in` 7200。

**注意事项**
- 过期后文档的做法是「前端调用 TAPD 方法获取新的 code」再换一次，没有 refresh_token ⚠ 文档未说明刷新机制。
- 文档里的回调示例域名 `lion.oa.com` 是示例值，不要照抄。

## 6. OAuth 跳转模式（平台级系统）

「TAPD OAuth 接入文档」描述的是在第三方平台里发起授权、授权后回跳的模式：
1. 应用「安全配置 → 三方应用数据授权」添加回调 URL 白名单（URL 不能包含 `#`）
2. 跳转 `https://tapd.woa.com/oauth/open_app_install?test=1&show_installed=0&client_id=%s&cb=%s&state=%s`
   - `test`：应用未上架前取 1，上架后改 0；`show_installed=1` 显示已授权过的项目
3. 回跳带 `code`、`state`、`resource`（含 workspace_id）
4. 之后用 `curl -u 'client_id:client_secret'` 调该项目数据

- ⚠ 文档写的跳转域名 `tapd.woa.com` 是腾讯内网域名，同页开头又提到 `https://o.tapd.woa.com/`。外部企业（`www.tapd.cn`）应使用的对应地址文档未说明。
- 回跳示例同时出现拼错的 `resouce=` 和正确的 `resource=` 两个参数 ⚠ 文档示例瑕疵，读 `resource`。

## 7. scope、应用权限与安全 IP

**scope**（授权凭证/scopes.html，节选；完整表共百余项）
| scope | 权限 | scope | 权限 |
|---|---|---|---|
| `story` / `story#read` / `story#write` | 需求 | `bug` / `bug#read` / `bug#write` | 缺陷 |
| `task` / `task#read` / `task#write` | 任务 | `iteration` / `iteration#read` / `iteration#write` | 迭代 |
| `tcase` / `tcase#read` / `tcase#write` | 测试模块 | `timesheet` / `timesheet#read` | 工时花费 |
| `workspace` / `workspace#read` / `workspace#write` | 项目信息 | `webhook` / `webhook#read` / `webhook#write` | Webhook 配置 |
| `user` / `user#read` / `user#write` | 用户信息 | `app.event` | 事件推送 |
| `setting` / `setting#read` | 基线、版本、模板、标签 | `workflow` / `workflow#read` | 工作流 |

- 不带 `#` 的是读写，`#read` / `#write` 为单向。开发者在应用插件的 `plugin.yaml` 里声明，如 `scopes: [story, bug#read]`（next/api/）。
- 应用权限（开发者后台 → 应用开发 → 应用权限）：只能调用已拥有权限模块的 API；**Webhook 也只推送有权限模块的事件**。
- 安全 IP（开发者后台 → 应用开发 → 安全设置）：设置后只能从这些 IP 请求 API；IP 段写通配符，如 `116.31.81.*`。
- 每个项目安装的应用版本可能不同，某个项目的可用 scope 取决于该项目所装版本声明的 scope（next/api/）。

## 8. 项目前置：workspace_id、公司 ID 与成员昵称

几乎所有业务接口都**必传 `workspace_id`**（项目 ID）。文档写的查看方式是「进入对应项目空间，点击左上角项目名称」，但页面给的域名是内网 `tapd.woa.com` ⚠。
用 API 查：

### 列出公司下的项目
**Endpoint**: `GET /workspaces/projects`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `company_id` | integer | 是 | 公司 ID，一次只能查一个公司 |
| `category` | string | 否 | `organization` 公司 / `product` / `project` 项目协作 / `mini_project` 轻协作 / `program` 项目集；多个用半角逗号 |
| `with_extends` | integer | 否 | `1` 返回自定义字段 |

```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" 'https://api.tapd.cn/workspaces/projects?company_id=20003261&category=project'
```
响应（文档原文节选）：`{"status":1,"data":[{"Workspace":{"id":"20026861","name":"产品运营2015","status":"normal","category":"project",...}}]}`。无分页。

### 单个项目信息
**Endpoint**: `GET /workspaces/get_workspace_info?workspace_id=` —— 返回 `Workspace.id/name/pretty_name/category/status/company_id...`；
`status` 取值 `normal` 正常 / `closed` 关闭 / `suspend` 挂起（文档原文）。

### 某用户参与的项目
**Endpoint**: `GET /workspaces/user_participant_projects`
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `nick` | string | 是 | 成员昵称 |
| `company_id` | int | 是 | 公司 ID |

⚠ 文档自相矛盾：参数表标 `company_id` 必填，示例 `?nick=anyechen` 没带。按参数表传。

### 项目成员
**Endpoint**: `GET /workspaces/users`
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `workspace_id` | integer | 是 | 项目 id **或者公司 id** |
| `user` | string | 否 | 用户昵称，多个用 `,` 分隔 |
| `fields` | string | 否 | `user,user_id,role_id,name,email,real_join_time` 可选，`,` 分隔 |

```python
r = requests.get("https://api.tapd.cn/workspaces/users", auth=AUTH,
                 params={"workspace_id": WS, "fields": "user,name,email"}, timeout=30)
members = [row["UserWorkspace"] for row in r.json()["data"]]   # user 字段就是后续 owner 等字段要填的昵称
```
- 无分页、一次一个项目。用户组 ID（role_id）对照：`GET /roles`（本 skill 未展开）。
- **处理人、创建人等人员字段填的是昵称（`user`），不是邮箱或 user_id**；文档示例写入时常带结尾分号，如 `owner=anyechen;`，见 `query-errors-limits.md`。

## 9. 短 ID 换长 ID

界面上看到的是短 ID（如 `1000276`），API 的 `id` 是 19 位长 ID（如 `1148464494001000276`）。

**Endpoint**: `GET /workspaces/get_workitems_long_id_by_short_ids`
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `workspace_id` | integer | 是 | 项目 id |
| `entity_type` | string | 是 | `story` / `task` / `bug` |
| `short_ids` | string | 否* | 多个以 `;` 分隔 |
| `long_ids` | string | 否* | 多个以 `;` 分隔（*两者不能都不传） |

```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  'https://api.tapd.cn/workspaces/get_workitems_long_id_by_short_ids?short_ids=1000276;1000277&workspace_id=48464494&entity_type=story'
```
响应（文档原文节选）：
```json
{"status":1,"data":{"valid_id_map":[{"short_id":"1000276","long_id":"1148464494001000276","entity_type":"story","workspace_id":"48464494","company_id":"39418254"}],
 "invalid_long_ids":["1000104"],"invalid_short_ids":[]},"info":"success"}
```
- 注意这里多值分隔符是 `;`，而列表接口的「多 ID 查询」用 `,`（使用必读）。
- 19 位 ID 超出 JavaScript `Number` 的安全整数范围（2^53），JS / TS 里一律按字符串处理；文档所有 JSON 示例里 id 也都是字符串。

## 10. 官方 SDK 现状

| SDK | 文档写法 | 无凭证探测（2026-09-11，两次一致，只查注册表元数据，未下载） |
|---|---|---|
| Node | `SDK/node-README.html`：`npm install @opentapd/tapd-node-sdk`，`new SDK({client, secret})`，方法名如 `getStories` / `addStory` / `addBug` / `updateTask` | 公共 npm 上存在，latest `1.68.0` |
| Node | `next-tool-doc/SDK/TAPD SDK/Node-SDK.html`：先 `npm config set registry https://mirrors.tencent.com/npm/` 再 `npm install @tencent/tapd-node-sdk` | 公共 npm 返回 404 |
| Python | `Python-SDK.html`：`pip install tapd-python-sdk -i https://mirrors.tencent.com/repository/pypi/tencent_pypi/simple ...`，`TapdAPIClient(client_id=, client_secret=)`，`sdk.get_stories({...})` | 公共 PyPI 返回 404 |

- ⚠ 两页 Node SDK 包名不同（`@opentapd` vs `@tencent`）；Python SDK 只在腾讯镜像源。SDK 页的应用申请链接全部指向内网 `o.tapd.woa.com`。
- 各接口页的「SDK 方法名」只给了 nodeJs（如 `addStory`、`getIterationsCount`、`getTcaseResult`）。
- 本 skill 的示例一律用 curl + requests 直接调 HTTP（SDK 底层也是这些 endpoint）。SDK 的参数校验、重试行为 ⚠ 未核实。

## 11. ⚠ 本文件汇总
- API 账号申请菜单两页写法不同（开放集成 > API账号管理 vs 开放平台） — 第 1 节
- 没有 refresh_token / 刷新接口 — 第 3、5 节
- 真实过期 token 是否也返回 422 未验证（伪造 token 为 422，无凭证探测） — 第 3 节
- token 放 query（`access_token=`）与放 header 两种写法并存 — 第 3 节
- 应用 Basic 与 Bearer 两种方式的差异未说明 — 第 4 节
- OAuth 跳转模式与项目 ID 查看方式使用内网域名 `tapd.woa.com` — 第 6、8 节
- `user_participant_projects` 的 company_id 必填但示例未传 — 第 8 节
- 两个 Node SDK 包名不一致、Python SDK 不在公共 PyPI — 第 10 节
- Gap 1 处：next 文档「应用态」链接指向不存在的页面 — 第 4 节
