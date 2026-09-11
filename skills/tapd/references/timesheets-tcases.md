# 工时（timesheet）与测试用例 / 测试计划（tcase / test_plan）

> 来源：`https://open.tapd.cn/document/api-doc/API文档/api_reference/timesheet/`（5 页）、`tcase/`（30 页）（抓取于 2026-09-11）。
> **文档版，未用真实凭证调用验证。** 报错与行为描述均为「文档原文，未实测」。
> 通用查询语法与错误处理见 `query-errors-limits.md`。

## 目录
1. 工时：记录 `POST /timesheets`
2. 工时：查询 `GET /timesheets` 与计数
3. 工时：更新 `POST /timesheets`（带 id）
4. 工时：删除 `POST /timesheets/delete_timesheets`
5. 测试用例：查询 `GET /tcases`
6. 测试用例：创建 / 批量创建 / 更新
7. 测试计划：查询与创建
8. 执行用例与查结果
9. 其他测试接口一览
10. ⚠ 本文件汇总

```python
import os, requests
BASE = "https://api.tapd.cn"
AUTH = (os.environ["TAPD_API_USER"], os.environ["TAPD_API_PASSWORD"])
WS = os.environ["TAPD_WORKSPACE_ID"]
```

---

## 1. 工时：记录

**Endpoint**: `POST /timesheets`
**用途**: 给需求 / 任务 / 缺陷记一条「花费工时」。一次一条。

**关键参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `workspace_id` | integer | **是** | 项目 ID |
| `entity_type` | string | **是** | 对象类型，如 `story`、`task`、`bug` |
| `entity_id` | integer | **是** | 对象 ID（19 位长 ID） |
| `timespent` | string | **是** | 花费工时 |
| `owner` | string | **是** | 花费创建人（昵称） |
| `spentdate` | date | 否 | 花费日期 `YYYY-MM-DD` |
| `timeremain` | string | 否 | 剩余工时 |
| `memo` | string | 否 | 描述 |

**示例请求**
```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  -d 'entity_type=story' -d 'entity_id=1010158231500709717' -d 'owner=anyechen' \
  -d 'timespent=2' -d 'spentdate=2020-05-05' -d "workspace_id=$TAPD_WORKSPACE_ID" \
  'https://api.tapd.cn/timesheets'
```
```python
import datetime
r = requests.post(f"{BASE}/timesheets", auth=AUTH, timeout=30, data={
    "workspace_id": WS, "entity_type": "task", "entity_id": task_id,
    "owner": "zhangsan", "timespent": "3", "spentdate": datetime.date.today().isoformat(),
    "memo": "联调"})
ts = r.json()["data"]["Timesheet"]
```

**示例响应**（文档原文）
```json
{"status": 1, "data": {"Timesheet": {"id": "1010158231001169003", "entity_type": "story",
  "entity_id": "1010158231500709717", "timespent": "2", "spentdate": "2020-05-05", "owner": "anyechen",
  "created": "2020-05-06 22:08:35", "workspace_id": "10158231", "memo": null}}, "info": "success"}
```

**注意事项**
- **唯一约束**（文档原文）：「同一 entity_type、entity_id、spentdate、owner，只能有一条工时记录」。
  同一天同一人对同一对象追加工时，要先 `GET /timesheets` 找到那条记录再**更新**，不能再建一条。重复创建时的报错文案 ⚠ 文档未说明。
- `timespent` 的单位（小时还是天）⚠ 文档未说明，取决于项目配置；文档示例数值为 2、3、8。
- `owner` 必填——不会自动取 API 账号本身。

## 2. 工时：查询与计数

**Endpoint**: `GET /timesheets`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `workspace_id` | integer | **是** | — | 项目 ID |
| `entity_type` / `entity_id` | — | 否 | — | 某个对象的工时 |
| `owner` | string | 否 | — | 某成员 |
| `spentdate` | date | 否 | — | 支持时间查询，如 `spentdate=2026-09-01~2026-09-07` |
| `modified` / `created` | date / datetime | 否 | — | 支持时间查询 |
| `is_delete` | integer | 否 | 0 | 默认不返回已删除记录；`1` 返回已删除的 |
| `include_parent_story_timesheet` | integer | 否 | — | `0` = 不返回父需求的花费 |
| `workflow_step` | string | 否 | — | 工作流节点原名 |
| `relation_type` | string | 否 | — | `entity`（直接关联业务对象）或 `workflow`（关联工作流节点） |
| `limit` / `page` / `order` / `fields` | — | 否 | 30 / 1 | 最大 200 |

```python
def week_timesheets(ws, monday, sunday):
    out, page = [], 1
    while True:
        r = requests.get(f"{BASE}/timesheets", auth=AUTH, timeout=30, params={
            "workspace_id": ws, "spentdate": f"{monday}~{sunday}", "limit": 200, "page": page})
        rows = [x["Timesheet"] for x in r.json()["data"]]
        out += rows
        if len(rows) < 200:
            return out
        page += 1
```
- 计数：`GET /timesheets/count`（参数同上，含 `is_delete`），响应 `{"data":{"count":14}}`。
- 返回字段：`id`、`entity_type`、`entity_id`、`timespent`、`spentdate`、`owner`、`created`、`modified`、`memo`、`is_delete`、`workflow_step`、`relation_type`。

## 3. 工时：更新

**Endpoint**: `POST /timesheets`（带 `id`）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | integer | **是** | 工时记录 ID |
| `workspace_id` | integer | **是** | 项目 ID |
| `timespent` | string | 否 | 花费工时（覆盖为新值） |
| `timeremain` | string | 否 | 剩余工时 |
| `memo` | string | 否 | 描述 |

```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  -d 'id=1010158231001169003' -d 'timespent=3' -d "workspace_id=$TAPD_WORKSPACE_ID" \
  'https://api.tapd.cn/timesheets'
```
- 更新参数里**没有** `owner`、`spentdate`、`entity_id`：记错人 / 日期 / 对象只能删掉重建。
- `timespent` 是覆盖不是累加：要「再加 1 小时」先读出旧值自己相加。
- ⚠ 文档示例标题写「花费成为 5」，请求体却是 `timespent=3`，响应也是 3（示例笔误）。

## 4. 工时：删除

**Endpoint**: `POST /timesheets/delete_timesheets`
**用途**: 批量删除，一次最多 100 条。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `workspace_id` | integer | 是 | 项目 ID |
| `entity_type` | string | 是 | 对象类型 |
| `entity_id` | integer | 是 | 对象 ID（所有 cost_ids 必须属于这个对象） |
| `cost_ids` | array | 是 | 工时记录 ID 集合；表单编码写成 `cost_ids[]=a&cost_ids[]=b` |

```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  -d 'entity_type=story' -d 'entity_id=1148464494001000040' \
  -d 'cost_ids[]=1148464494001000097' -d 'cost_ids[]=1148464494001000099' -d 'workspace_id=48464494' \
  'https://api.tapd.cn/timesheets/delete_timesheets'
```
```python
r = requests.post(f"{BASE}/timesheets/delete_timesheets", auth=AUTH, timeout=30, data={
    "workspace_id": WS, "entity_type": "story", "entity_id": story_id,
    "cost_ids[]": ["1148464494001000097", "1148464494001000099"]})   # requests 会展开成两个 cost_ids[]=
result = r.json()["data"]["data"]            # 注意两层 data
failed = result.get("failed", [])
```

**示例响应**（文档原文，精简）
```json
{"status": 1, "data": {"msg": "delete completed", "data": {
  "success": {"cost_ids": ["1148464494001000111"], "msg": "delete success"},
  "failed": [{"cost_ids": ["1148464494001000106"],
              "msg": "the record does not belong to the specified entity (entity_type:story, entity_id:1148464494001000137)"}]}},
 "info": "success"}
```
- **部分失败时外层 `status` 仍是 1**，必须检查 `data.data.failed`。
- 删除后记录仍可用 `GET /timesheets?is_delete=1` 查到。

## 5. 测试用例：查询

**Endpoint**: `GET /tcases`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `workspace_id` | integer | **是** | — | 项目 ID |
| `id` | integer | 否 | — | 多 ID |
| `name` | string | 否 | — | 用例名称，模糊匹配 |
| `category_id` | integer | 否 | — | 用例目录（`-1` 在示例中表示未分目录） |
| `status` | enum | 否 | — | `normal` 正常 / `updating` 待更新 / `abandon` 已废弃 |
| `type` | string | 否 | — | 用例类型（中文值：功能测试 / 性能测试 / 安全性测试 / 其他） |
| `priority` | string | 否 | — | 用例等级（中文值：高 / 中 / 低） |
| `creator` / `modifier` | string | 否 | — | |
| `created` / `modified` | datetime | 否 | — | 时间查询 |
| `limit` / `page` / `order` / `fields` | — | 否 | 30 / 1 | 最大 200 |

```python
r = requests.get(f"{BASE}/tcases", auth=AUTH, timeout=30,
                 params={"workspace_id": WS, "status": "normal", "limit": 200})
cases = [x["Tcase"] for x in r.json()["data"]]
```
- 用例的 `type` 与 `priority` 取值是**中文字面值**（文档原文表中「取值」与「字面值」相同），和缺陷的英文枚举不同。
- 使用必读的游标翻页示例正是 `GET /tcases`：不传 cursor 取第一页（默认 `id DESC`），之后 `cursor=<上一页最后一条 id>`，见 `query-errors-limits.md`。

## 6. 测试用例：创建 / 批量创建 / 更新

### 创建
**Endpoint**: `POST /tcases`
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `workspace_id` | integer | **是** | 项目 ID |
| `name` | string | **是** | 用例名称 |
| `steps` / `precondition` / `expectation` | string | 否 | 步骤 / 前置条件 / 预期结果 |
| `category_id` | integer | 否 | 用例目录 |
| `status` | enum | 否 | `updating` / `abandon` / `normal` |
| `type` / `priority` | string | 否 | 中文值 |
| `creator` | string | 否 | 创建人 |
| `cus_{显示名}` / `custom_field_*` | — | 否 | 自定义字段 |

```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  -d 'name=登录-错误密码提示' -d "workspace_id=$TAPD_WORKSPACE_ID" -d 'priority=高' -d 'steps=1. 输入错误密码' \
  'https://api.tapd.cn/tcases'
```
- ⚠ 文档自相矛盾：参数表 `status` 是英文枚举，而第二个示例传 `status=待更新`（中文），同一示例的 URL 还残留模板变量 `{{ $page.apiHost }}`。写入用英文枚举。
- ⚠ 示例 `type=其它`，枚举表写的是「其他」（它 / 他 不同字）。

### 批量创建
**Endpoint**: `POST /tcases/batch_save`，每次最多 **200** 条；请求体是用例对象的 **JSON 数组**，每个对象都要带 `workspace_id` 和 `name`。
```python
r = requests.post(f"{BASE}/tcases/batch_save", auth=AUTH, timeout=60,
                  json=[{"workspace_id": WS, "name": "用例1", "creator": "zhangsan"},
                        {"workspace_id": WS, "name": "用例2", "creator": "zhangsan"}])   # json= 自动带 Content-Type
created = [x["Tcase"] for x in r.json()["data"]]
```
- ⚠ 文档自相矛盾：文档的 curl 示例用 `-d '[{...}]'` 发 JSON，**没加** `Content-Type: application/json`（curl `-d` 默认是 form 编码），
  而使用必读要求 JSON 请求必须带该头。自己写时一定加上：`-H 'Content-Type: application/json'`。

### 更新
**Endpoint**: `POST /tcases`（带 `id`）—— 可改 `name`、`steps`、`status`、`category_id`、`type`、`priority`、`precondition`、`expectation`、自定义字段。一次一条。

## 7. 测试计划：查询与创建

### 查询
**Endpoint**: `GET /test_plans`
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `workspace_id` | integer | 是 | 项目 ID |
| `id` / `name` / `owner` / `version` / `type` | — | 否 | 过滤 |
| `status` | string | 否 | `open` 开启 / `close` 关闭 |
| `start_date` / `end_date` | date | 否 | 预计开始 / 结束 |
| `limit` / `page` / `order` / `fields` | — | 否 | 默认 30，最大 200 |

响应包装键 `TestPlan`：`id`、`name`、`owner`、`status`、`start_date`、`end_date`、`creator`、`created`……
⚠ 文档字段说明表写的是 `startdate` / `enddate`，而参数表与示例都是 `start_date` / `end_date`；说明表还把 `creator` 解释为「结束时间」。以示例为准。

### 创建
**Endpoint**: `POST /test_plans`
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | **是** | 测试计划标题 |
| `workspace_id` | integer | **是** | 项目 ID |
| `iteration_id` | integer | 否 | 关联迭代 |
| `owner` / `creator` / `modifier` | string | 否 | |
| `start_date` / `end_date` | date | 否 | |
| `version` | string | 否 | 版本号 |
| `type` | float | 否 | 测试类型 ⚠ 类型标为 float，与查询接口的 string 不一致 |
| `status` | string | 否 | 默认 `open` |

- 编辑：`POST /test_plans`（带 id，参数见 update_test_plan 页，未展开）。
- 把用例加进计划：`POST /test_plans/create_tcase_relation`；关联需求：`POST /test_plans/create_story_relation`（参数见文档页，未展开）。
- 计划里的用例：`GET /test_plans/get_test_plan_tcase?workspace_id=&test_plan_id=`，返回 `TestPlanStoryTcaseRelation`（`tcase_id`、`story_id`、`test_plan_id`）。

## 8. 执行用例与查结果

### 执行（录入结果）
**Endpoint**: `POST /tcase_instance/execute`，最多 10 条。
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `test_plan_id` | integer | 是 | 测试计划 ID |
| `tcase_id` | integer | 是 | 用例 ID，支持批量 |
| `workspace_id` | integer | 是 | 项目 ID |
| `result_status` | string | 是 | `pass` 通过 / `no_pass` 不通过 / `block` 阻塞 |
| `last_executor` | string | 是 | 执行人 |
| `result_remark` | string | 否 | 实际执行结果 |

```python
r = requests.post(f"{BASE}/tcase_instance/execute", auth=AUTH, timeout=30, data={
    "workspace_id": WS, "test_plan_id": plan_id, "tcase_id": case_id,
    "result_status": "no_pass", "last_executor": "zhangsan", "result_remark": "提示文案错误"})
```
- 响应 `{"status":1,"data":[],"info":"success"}`。
- ⚠ 文档自相矛盾：`last_executor` 标必填，文档示例却没传。
- 「支持批量」时多个 tcase_id 的传法（逗号？数组？）⚠ 文档未说明。

### 查执行结果
**Endpoint**: `GET /tcase_instance/result?workspace_id=&test_plan_id=&tcase_id=` —— 一次一条用例；
`data` 是以执行记录 ID 为 key 的对象（不是数组），每项 `executed_at`、`executor`、`result_status`、`result_remark`、`bug_id`、`Bug`。

## 9. 其他测试接口一览（未展开）

| 能力 | Endpoint |
|---|---|
| 用例计数 | `GET /tcases/count` |
| 用例目录 | `GET/POST /tcase_categories`、`GET /tcase_categories/count` |
| 用例字段 / 自定义字段 | `GET /tcases/get_fields_info`、`GET /tcases/custom_fields_settings` |
| 用例关联的需求 | `GET /tcases/get_story_by_tcase_id?workspace_id=&tcase_ids=a,b` |
| 分配执行人 | `POST /tcase_instance/assign` |
| 移出测试计划 | `POST /tcase_instance/remove_tcase`、`POST /tcase_instance/delete_tcase_story_relation` |
| 计划进度 / 结果 / 缺陷 | `GET /test_plans/progress`、`GET /test_plans/details`、`GET /test_plans/result_relation_bugs` |
| 迭代下的测试计划 | `GET /test_plans/get_by_iteration_id` |
| 计划计数 / 字段 | `GET /test_plans/count`、`GET /test_plans/get_fields_info` |

TestX 新测试模块（`api_reference/testx/`，46 页）本 skill 不覆盖。

## 10. ⚠ 本文件汇总
- 重复创建工时的报错文案未说明；`timespent` 单位未说明 — 第 1 节
- update_timesheet 示例标题「成为 5」与请求 `timespent=3` 不符 — 第 3 节
- add_tcase 示例 `status=待更新`（中文）与英文枚举矛盾；`type=其它` vs「其他」；示例残留 `{{ $page.apiHost }}` — 第 6 节
- batch_save 示例未带 JSON Content-Type，与使用必读矛盾 — 第 6 节
- 测试计划字段说明 `startdate`/`enddate` 与参数 `start_date`/`end_date` 矛盾；`creator` 说明错写；`type` 类型 float/string 不一致 — 第 7 节
- execute 的 `last_executor` 必填但示例未传；批量 tcase_id 传法未说明 — 第 8 节
