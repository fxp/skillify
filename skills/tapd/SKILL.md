---
name: tapd
description: 接入 TAPD（腾讯敏捷研发协作平台，tapd.cn；开放平台 open.tapd.cn，API 域名 api.tapd.cn）开放 API 的使用手册——涵盖 API 账号 HTTP Basic 鉴权与开放应用 access_token（client_credentials、OAuth 授权码、scope、安全 IP）、项目 workspace_id 与成员、需求 story、缺陷 bug、任务 task、迭代 iteration、工时 timesheet、测试用例 tcase 与测试计划、Webhook 事件订阅与报文格式、通用查询语法（时间区间、枚举、LIKE/EQ、游标翻页）、错误码与频率限制。当用户提到"TAPD""tapd.cn""api.tapd.cn""腾讯 TAPD""TAPD API""TAPD 开放平台""TAPD Webhook""workspace_id""api_user""story::update""tapd-node-sdk"，或要写代码同步、创建、查询 TAPD 的需求、缺陷、任务、迭代、工时、测试用例时，应主动使用本技能，不要凭记忆编造接口参数，也不要套用 Jira、禅道、Coding、飞书项目的接口习惯。
---
# TAPD 开放 API 接入指南

TAPD（腾讯敏捷研发协作平台）开放 API：用 API 账号（HTTP Basic）或开放应用 token 调 `https://api.tapd.cn`，
读写需求、缺陷、任务、迭代、工时、测试用例，并通过 Webhook 接收变更推送。**本页只做分流与规则，字段表和示例在 references/。**

## ⚠ 验证状态

文档版：内容整理自 https://open.tapd.cn/document/api-doc/ （抓取于 2026-09-11；站点的 sitemap.xml 不含文档页，
页面清单取自文档站 VuePress 路由表，共抓取 400 页），**未用真实凭证调用验证**。
另做了 20 次无凭证探测（10 个 URL 各复跑 2 次：不带凭证、伪造 Basic / Bearer、伪造 client 换 token、拼错路径、http 明文、
原样执行文档示例命令），并查了 3 个 SDK 包名在公共 npm / PyPI 的元数据（未下载）。
凡未标「无凭证探测」的报错与行为，都是「文档原文，未实测」。对照实验待真实凭证到位后进行。
拿到凭证后按 `tapd-workspace/verification-plan.md` 补测。

## 当前事实

| 项 | 值 |
| :--- | :--- |
| Base URL | `https://api.tapd.cn`（无凭证探测：`http://` 不跳转、直接处理，凭证会明文发出） |
| 鉴权 · API 账号 | HTTP Basic：`Authorization: Basic base64(api_user:api_password)`；API 账号由企业版公司管理员在后台申请，**不是个人登录账号** |
| 鉴权 · 开放应用 | `POST /tokens/request_token`（Basic `client_id:client_secret` + `grant_type=client_credentials`）→ `Authorization: Bearer <access_token>`，`expires_in` 7200 秒，无 refresh_token；文档也允许直接 Basic `client_id:client_secret` |
| 必传参数 | 几乎所有接口都要 `workspace_id`（项目 ID）；对象 ID 是 19 位长 ID，JSON 里是字符串 |
| 成功判定 | HTTP 200 **且** `status == 1` **且** `data` 形状符合预期。无凭证探测：拼错的顶层路径（如 `/storys`）不带凭证也返回 200 + `status:1` + `"Hello world from TAPD API..."`；伪造 Bearer 返回 **HTTP 422** `The access token provided is invalid`，不是 401 |
| 最容易选错 | 字段名因对象而异：需求 / 任务用 `name`、`owner`、`creator`，**缺陷用 `title`、`current_owner`、`reporter`**；优先级一律用 `priority_label` |

## 照通用经验写容易错的地方（来自文档，未实测）

1. **API 账号 ≠ 登录账号，Basic ≠ Bearer。** 企业脚本用管理员申请的 API 账号做 HTTP Basic；只有开放应用换到的 access_token 才用 `Bearer`。
   token 无 refresh_token，过期重新换；判断失效要覆盖 422（无凭证探测），不能只看 401。
2. **没有 PUT / PATCH / DELETE。** 创建和更新是同一个 `POST /stories`（`/bugs`、`/tasks`、`/iterations`、`/timesheets`、`/tcases` 同理），带 `id` 就是更新；
   抓取的路由表里没有删除需求 / 缺陷 / 任务本身的接口。POST 发 JSON 必须带 `Content-Type: application/json`，否则用表单编码。
3. **查询运算符写在值里，不是另起参数名。** `modified=>2026-09-01`、`created=2026-09-01~2026-09-07`、`status=a|b`、`id=a,b`、
   `iteration_id=<>0`、`name=EQ<完整标题>`。没有 `modified_after` / `since` 这类参数；`name` / `title` 默认是模糊匹配。
4. **分页上限低，深翻要游标。** `limit` 最大 200，`page × limit` 最大 20000；更多数据用 `cursor=<上一页最后一条 id>`，仅支持 id 排序且必须串行。
   需求变更历史 `/story_changes` 的 `limit` 最大 100，且必须带 `story_id` 或按天的 `created`。
5. **状态、模块、自定义字段按项目配置，不能硬编码。** `status` 是英文 key（还有 `status_3` 这类自定义 key），先查 `/workflows/status_map`、`/stories/get_fields_info`；
   缺陷 `resolution=fix` 的字面值是「延期解决」，已修复是 `fixed`；用例的 `type` / `priority` 却是中文值。
6. **工时有唯一约束且更新是覆盖。** 同一对象 + 日期 + 人只能有一条工时，追加要先查再 `POST /timesheets` 带 `id` 覆盖 `timespent`；`owner` 必填。
7. **Webhook 没有签名，默认是 form 编码。** 只能比对 body 里明文的 `secret` 字段；更新类报文只带 `old_*` 旧值和 `change_fields`，新值要再调 API 取。

## 我要做什么 → 读哪一份

| 我要做什么 | 读 | 核心 endpoint |
| :--- | :--- | :--- |
| 选凭证、换 token、OAuth 与 scope；查项目 ID、成员昵称；短 ID 换长 ID；SDK 现状 | [`auth.md`](references/auth.md) | `GET /quickstart/testauth` · `POST /tokens/request_token` · `GET /workspaces/projects` · `GET /workspaces/users` |
| 查询、创建、更新、流转需求；状态与自定义字段元数据；变更历史 | [`stories.md`](references/stories.md) | `GET /stories` · `POST /stories` · `GET /story_changes` · `GET /workflows/status_map` |
| 提交、查询、流转缺陷；严重程度 / 解决方法枚举；缺陷变更历史 | [`bugs.md`](references/bugs.md) | `GET /bugs` · `POST /bugs` · `GET /bug_changes` · `GET /workflows/all_transitions` |
| 任务的增改查与完成；迭代的创建、更新、锁定，把工作项放进迭代 | [`tasks-iterations.md`](references/tasks-iterations.md) | `GET /tasks` · `POST /tasks` · `GET /iterations` · `POST /iterations` |
| 记录与修改工时；测试用例、批量建用例、测试计划、执行结果 | [`timesheets-tcases.md`](references/timesheets-tcases.md) | `POST /timesheets` · `GET /timesheets` · `GET /tcases` · `POST /tcases/batch_save` · `POST /tcase_instance/execute` |
| 接收 Webhook（两条渠道、事件名、报文字段、验证）；向 TAPD 推送事件 | [`webhooks-events.md`](references/webhooks-events.md) | 你的回调 URL · `POST /open_app_events/hook` |
| 查询语法、分页与游标、响应结构、错误码、频率限制、参考客户端 | [`query-errors-limits.md`](references/query-errors-limits.md) | 全局 `status` / `info` / `data` · `limit` / `page` / `cursor` |

本 skill 不覆盖：Wiki、发布计划与发布评审（release）、源码与流水线（source / pipeline）、看板（board）、附件与图片上传（attachment / storage）、
评论（comment）、标签管理（label）、版本 / 模块 / 基线 / 特性配置（setting）、度量与报表（measure / report）、项目集（program）、
TestX 新测试模块（testx）、轻协作（mini_api_reference）、前端扩展模块。文档都在 https://open.tapd.cn/document/api-doc/ 的「API文档 / api_reference」对应目录下。

## House rules

- 凭证只走环境变量：`TAPD_API_USER` / `TAPD_API_PASSWORD`（API 账号），或 `TAPD_CLIENT_ID` / `TAPD_CLIENT_SECRET`（开放应用）；项目用 `TAPD_WORKSPACE_ID`。
- 所有调用走一个封装（`query-errors-limits.md` 第 9 节）：只用 https、判 HTTP + `status` + `data` 形状、429 / 500 / 502 指数退避、按文档最保守的 60 次 / 分钟节流、翻页串行。
- 列表接口一律传 `fields=`：不传时每条需求带回数百个 `custom_field_*`，文档把 502 归因于返回量过大。
- 列表每项外面包了对象名：`row["Story"]`、`row["Bug"]`、`row["Task"]`……创建 / 更新返回 `data["Story"]` 单个对象。
- 人员字段填 TAPD 昵称（`/workspaces/users` 的 `user`），文档示例写入与读回都带结尾分号 `zhangsan;`；解析时按 `;` 切分去空。
- 19 位 ID 一律按字符串存储和比较；界面短 ID 先用 `/workspaces/get_workitems_long_id_by_short_ids` 换长 ID。
- 写状态前查 `/workflows/all_transitions`：目标流转有 `Notnull="yes"` 的附加字段要一起传。
- Webhook 接收端：同时接 form 与 JSON、拒绝空 secret、`event_id` 去重、先回 200 再异步用 API 拉最新数据。
- 日志里不打印 Authorization 头，也不打印 `/quickstart/testauth` 的完整响应（文档示例回显口令字段）。
- 复制文档里的 curl 示例时，把 `–u`（EN DASH）改成 `-u`，并把残留的 `{{ $page.apiHost }}` 换成 `https://api.tapd.cn`。

## 文档自相矛盾 / 未说明之处（⚠ 汇总）

- 频率限制：错误码页 429 示例写「6000req/10min」，同行又写「默认 60req/1min」；无凭证探测到的 `X-RateLimit-Limit: 10000` 含义未说明 → `query-errors-limits.md`
- 深分页超 20000 的错误码、游标是否全接口支持、游标是否包含边界记录、时间字段时区、多处理人写入分隔规则均未说明 → `query-errors-limits.md`
- 无 refresh_token；真实过期 token 是否也是 422 未验证；token 放 query（`access_token=`）与放 header 两种写法并存；API 账号申请菜单两页写法不同；
  OAuth 跳转与项目 ID 查看用内网域名 `tapd.woa.com`；两个 Node SDK 包名不一致、Python SDK 不在公共 PyPI → `auth.md`
- `status_map` 的 `workitem_type_id` 标选填又说查需求必传；优先级示例 `priority=3` / `priority=高` 与映射表矛盾；`business_value` 参数重复 → `stories.md`
- `bug_changes` 的 `created` / `bug_id` 正文二选一、参数表都标必填；用错字段名时是否报错未说明 → `bugs.md`
- `update_iteration` 的 `id` 必填但示例未带；get_tasks 示例 JSON 少一层 → `tasks-iterations.md`
- add_tcase 示例用中文 `status=待更新`；batch_save 示例没带 JSON Content-Type；测试计划 `start_date` 与 `startdate` 混用；execute 的 `last_executor` 必填但示例未传 → `timesheets-tcases.md`
- Webhook 无签名、重试 / 超时 / 顺序未说明；`id` 类型 integer 与示例字符串矛盾；任务状态变更事件名未给出；`open_app_events/hook` 必填参数示例未传 → `webhooks-events.md`

## 文档与探测不符之处

reference 中用 `<!-- Gap: … -->` 标记，可 grep 定位（3 处，均为无凭证探测复跑两次一致）：
使用必读页 18 处 `curl –u` 用的是 EN DASH，照抄会不带凭证发请求（`query-errors-limits.md`）；
next 文档「事件映射」「配置webhook」链接指向不存在的页面（`webhooks-events.md`）；next 文档「应用态」链接指向不存在的页面（`auth.md`）。
