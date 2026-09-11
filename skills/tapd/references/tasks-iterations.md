# 任务（task）与迭代（iteration）

> 来源：`https://open.tapd.cn/document/api-doc/API文档/api_reference/task/`（11 页）、`iteration/`（16 页）（抓取于 2026-09-11）。
> **文档版，未用真实凭证调用验证。** 报错与行为描述均为「文档原文，未实测」。
> 通用查询语法与错误处理见 `query-errors-limits.md`。

## 目录
1. 任务：查询 `GET /tasks`
2. 任务：创建 `POST /tasks`
3. 任务：更新 / 完成 `POST /tasks`（带 id）
4. 任务：计数、变更、回收站、字段元数据
5. 迭代：查询 `GET /iterations`
6. 迭代：创建 `POST /iterations`
7. 迭代：更新 `POST /iterations`（带 id）
8. 迭代：锁定 / 解锁、类别、计划应用
9. 把需求 / 缺陷 / 任务放进迭代
10. ⚠ 本文件汇总

```python
import os, requests
BASE = "https://api.tapd.cn"
AUTH = (os.environ["TAPD_API_USER"], os.environ["TAPD_API_PASSWORD"])
WS = os.environ["TAPD_WORKSPACE_ID"]
```

---

## 1. 任务：查询

**Endpoint**: `GET /tasks`
**用途**: 批量查询任务（默认 30 条，最大 200）。

**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `workspace_id` | integer | **是** | — | 项目 ID |
| `id` | integer | 否 | — | 多 ID 逗号分隔 |
| `name` | string | 否 | — | 任务标题，模糊匹配 |
| `status` | string | 否 | — | `open` / `progressing` / `done`，支持枚举 |
| `owner` | string | 否 | — | 当前处理人，模糊匹配 |
| `creator` | string | 否 | — | 多人员查询 |
| `story_id` | integer | 否 | — | 关联需求，多 ID |
| `iteration_id` | integer | 否 | — | 所属迭代，支持枚举 |
| `priority_label` | string | 否 | — | 优先级（推荐） |
| `created` / `modified` / `completed` | datetime | 否 | — | 时间查询 |
| `begin` / `due` | date | 否 | — | 时间查询 |
| `effort` / `effort_completed` / `remain` / `exceed` | — | 否 | — | 工时字段 |
| `custom_field_*` | — | 否 | — | 自定义字段 |
| `limit` / `page` / `order` / `fields` | — | 否 | 30 / 1 | 同其它列表 |

**示例请求**
```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  "https://api.tapd.cn/tasks?workspace_id=$TAPD_WORKSPACE_ID&story_id=1010158231500709717&fields=id,name,status,owner,effort"
```
```python
r = requests.get(f"{BASE}/tasks", auth=AUTH, timeout=30,
                 params={"workspace_id": WS, "status": "open|progressing", "owner": "zhangsan", "limit": 200})
tasks = [row["Task"] for row in r.json()["data"]]
```

**示例响应**（文档原文，精简）
```json
{"status": 1, "data": [{"Task": {"id": "1020358627854792559", "name": "测试2", "status": "open",
  "owner": "", "story_id": "0", "iteration_id": "0", "effort": "0", "effort_completed": "0", "remain": "0"}}]}
```

**注意事项**
- 任务状态是固定三值（文档原文）：`open` 未开始、`progressing` 进行中、`done` 已完成——与需求 / 缺陷的可配置工作流不同。
- `story_id` / `iteration_id` 为 `"0"` 表示未关联。
- ⚠ 文档示例 JSON 的 `data` 数组里直接写 `"Task": {...}`，少了一层 `{}`（其它接口都是 `[{"Task": {...}}]`），属于示例笔误，解析按 `row["Task"]`。

## 2. 任务：创建

**Endpoint**: `POST /tasks`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `workspace_id` | integer | **是** | 项目 ID |
| `name` | string | **是** | 任务标题 |
| `story_id` | integer | 否 | 关联需求 ID |
| `iteration_id` | integer | 否 | 所属迭代 ID |
| `owner` / `creator` / `cc` | string | 否 | 人员 |
| `begin` / `due` | date | 否 | 预计开始 / 结束 |
| `effort` | string | 否 | 预估工时 |
| `priority_label` | string | 否 | 优先级（推荐） |
| `description` | string | 否 | 描述 |
| `label` | string | 否 | 多个 `\|` 分隔，不存在自动创建 |
| `cus_{显示名}` / `custom_field_*` | — | 否 | 自定义字段 |

```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  -d "workspace_id=$TAPD_WORKSPACE_ID" -d 'name=接口联调' -d 'story_id=1010158231500709717' -d 'owner=zhangsan;' -d 'effort=4' \
  'https://api.tapd.cn/tasks'
```
```python
r = requests.post(f"{BASE}/tasks", auth=AUTH, timeout=30, data={
    "workspace_id": WS, "name": "接口联调", "story_id": story_id, "owner": "zhangsan;", "effort": "4"})
task = r.json()["data"]["Task"]
```
- 文档示例创建后 `status` 为 `null`、`owner` 为 `null` ⚠ 文档未说明新任务的默认状态是否会被补成 `open`。
- 创建参数表里没有 `status`，要直接建成「进行中」需再调一次更新。

## 3. 任务：更新 / 完成

**Endpoint**: `POST /tasks`（带 `id`）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | integer | **是** | 任务 ID |
| `workspace_id` | integer | **是** | 项目 ID |
| `status` | string | 否 | `open` / `progressing` / `done` |
| `current_user` | string | 否 | 操作人 |
| `owner` | string | 否 | 处理人 |
| `auto_complete_effort` | integer | 否 | 取 `1` 且状态流转到 `done` 时，自动补齐工时 |
| `story_id` / `iteration_id` | integer | 否 | 改关联 |
| 其余 | — | 否 | 同创建 |

```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  -d 'id=1010158231500600385' -d "workspace_id=$TAPD_WORKSPACE_ID" -d 'status=done' -d 'current_user=zhangsan' \
  'https://api.tapd.cn/tasks'
```
```python
r = requests.post(f"{BASE}/tasks", auth=AUTH, timeout=30,
                  data={"id": task_id, "workspace_id": WS, "status": "done", "current_user": "zhangsan",
                        "auto_complete_effort": 1})
print(r.json()["data"]["Task"]["completed"])    # 文档示例：流转到 done 后 completed 被填上时间
```
- 文档 update_task 参数表把 `priority` 列了两遍 ⚠ 文档排版重复，无实质影响。
- 批量更新：`POST /tasks/batch_update_task`（未展开）。抓取的路由表里没有删除任务的接口。

## 4. 任务：计数、变更、回收站、字段元数据

| 能力 | Endpoint | 备注 |
|---|---|---|
| 计数 | `GET /tasks/count` | 参数同列表；`id` 在计数接口标注「支持多ID查询、模糊匹配」 |
| 变更历史 | `GET /task_changes`、`GET /task_changes/count` | 参数与返回结构见文档页 ⚠ 本 skill 未展开，不要套用需求或缺陷的结构 |
| 回收站 | `GET /tasks/get_removed_tasks` | |
| 字段与候选值 | `GET /tasks/get_fields_info?workspace_id=` | |
| 自定义字段 | `GET /tasks/custom_fields_settings?workspace_id=` | |
| 视图下的任务 | `GET /tasks/get_tasks_by_view_conf_id` | |

任务优先级旧取值同需求：`4` High / `3` Middle / `2` Low / `1` Nice To Have，文档标注「将不再使用」，用 `priority_label`。

## 5. 迭代：查询

**Endpoint**: `GET /iterations`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `workspace_id` | integer | **是** | — | 项目 ID |
| `id` | integer | 否 | — | 多 ID |
| `name` | string | 否 | — | 标题，**模糊匹配**（按名字找迭代时注意会匹配到多个） |
| `status` | string | 否 | — | 系统状态 `open` / `done`；自定义状态可直接传中文 |
| `startdate` / `enddate` | date | 否 | — | 支持时间查询 |
| `workitem_type_id` | integer | 否 | — | 迭代类别 |
| `plan_app_id` | integer | 否 | — | 计划应用 ID |
| `creator` / `locker` | string | 否 | — | 创建人 / 锁定人 |
| `created` / `modified` | datetime | 否 | — | 时间查询 |
| `limit` / `page` / `order` / `fields` | — | 否 | 30 / 1 | |

```python
def find_iteration(ws, name):
    r = requests.get(f"{BASE}/iterations", auth=AUTH, timeout=30,
                     params={"workspace_id": ws, "name": name, "fields": "id,name,status,startdate,enddate"})
    rows = [x["Iteration"] for x in r.json()["data"]]
    exact = [x for x in rows if x["name"] == name]     # name 是模糊匹配，自己再做一次精确过滤
    if len(exact) != 1:
        raise LookupError(f"迭代 {name!r} 匹配到 {len(exact)} 个")
    return exact[0]["id"]
```

**示例响应**（文档原文，精简）
```json
{"status": 1, "data": [{"Iteration": {"id": "1010158231000388075", "name": "迭代2", "workspace_id": "10158231",
  "startdate": "2017-06-26", "enddate": "2017-07-07", "status": "open", "creator": "anyechen"}}]}
```
- 迭代状态：`open` 开启、`done` 已关闭（文档原文）。计数 `GET /iterations/count`。

## 6. 迭代：创建

**Endpoint**: `POST /iterations`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | **是** | 标题 |
| `workspace_id` | integer | **是** | 项目 ID |
| `startdate` | date | **是** | 开始日期 `YYYY-MM-DD` |
| `enddate` | date | **是** | 结束日期 |
| `creator` | string | **是** | 创建人（**必填**，其它对象的 creator 都是可选） |
| `workitem_type_id` | integer | 否 | 迭代类别，取自 `GET /iterations/workitem_types` |
| `plan_app_id` | integer | 否 | 计划应用 ID |
| `entity_type` | string | 否 | 默认 `iteration`；也可建 `release`（迭代的上层计划） |
| `parent_id` | integer | 否 | 默认 0；只能把 `release` 指定为 `iteration` 的上层 |
| `description` / `status` / `label` | string | 否 | |
| `cus_{显示名}` / `custom_field_*` | — | 否 | 自定义字段 |
| `custom_moment_*` | string | 否 | 关键日期，按 `GET /iterations/template_fields` 的 `crucial_moment` 配置 |

```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  -d 'name=2026-W38' -d 'startdate=2026-09-14' -d 'enddate=2026-09-25' \
  -d "workspace_id=$TAPD_WORKSPACE_ID" -d 'creator=zhangsan' \
  'https://api.tapd.cn/iterations'
```
```python
r = requests.post(f"{BASE}/iterations", auth=AUTH, timeout=30, data={
    "name": "2026-W38", "startdate": "2026-09-14", "enddate": "2026-09-25",
    "workspace_id": WS, "creator": "zhangsan"})
it = r.json()["data"]["Iteration"]          # 返回含 entity_type、parent_id
```

## 7. 迭代：更新

**Endpoint**: `POST /iterations`（带 `id`）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | integer | **是** | 迭代 ID |
| `workspace_id` | integer | **是** | 项目 ID |
| `current_user` | string | **是** | 变更人（**必填**） |
| `name` / `startdate` / `enddate` / `description` / `status` | — | 否 | |
| `cus_*` / `custom_field_*` | — | 否 | |

```python
r = requests.post(f"{BASE}/iterations", auth=AUTH, timeout=30,
                  data={"id": iteration_id, "workspace_id": WS, "current_user": "zhangsan", "status": "done"})
```
- ⚠ 文档自相矛盾：参数表 `id` 必填，文档示例 `-d 'workspace_id=10104801&current_user=v_xuanfang&description=test111'` 却没带 `id`（示例标题还写成「在项目下创建迭代」）。按参数表带 `id`；不带 `id` 时会不会变成新建未知。

## 8. 迭代：锁定 / 解锁、类别、计划应用

### 锁定迭代
**Endpoint**: `POST /iterations/lock_iteration`
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `iteration_id` | integer | 是 | 迭代 ID（注意不是 `id`） |
| `workspace_id` | integer | 是 | 项目 ID |
| `lock_types` | string | 否 | `__ALL_STORY__` / `__ALL_BUG__`，多个逗号分隔 |

响应：`{"status":1,"data":"lock 1010104801000723579 successfully","info":"success"}`（`data` 是字符串）。

### 其他
| 能力 | Endpoint |
|---|---|
| 解锁 | `POST /iterations/unlock_iteration`（参数见文档页，未展开） |
| 迭代类别列表 | `GET /iterations/workitem_types` |
| 迭代模板 / 模板字段 | `GET /iterations/template_list`、`GET /iterations/template_fields` |
| 迭代自定义字段 | `GET /iterations/custom_fields_settings` |
| 迭代变更历史 | `GET /iteration_changes` |
| 计划应用 | `GET /plan_apps`、`GET /plan_apps/count`（需求 / 缺陷的 `custom_plan_field_*` 由此而来） |

## 9. 把需求 / 缺陷 / 任务放进迭代

没有专门的「加入迭代」接口，改对象的 `iteration_id` 字段：
```python
requests.post(f"{BASE}/stories", auth=AUTH, data={"id": story_id, "workspace_id": WS, "iteration_id": it_id}, timeout=30)
requests.post(f"{BASE}/bugs",    auth=AUTH, data={"id": bug_id,   "workspace_id": WS, "iteration_id": it_id}, timeout=30)
requests.post(f"{BASE}/tasks",   auth=AUTH, data={"id": task_id,  "workspace_id": WS, "iteration_id": it_id}, timeout=30)
```
查询迭代下的内容：`GET /stories?workspace_id=&iteration_id=`（需求还支持 `include_sub_iteration=1`）、`GET /bugs?...&iteration_id=`、`GET /tasks?...&iteration_id=`。
迭代下的测试计划：`GET /test_plans/get_by_iteration_id`（见 `timesheets-tcases.md`）。

## 10. ⚠ 本文件汇总
- get_tasks 示例 JSON 少一层 `{}` — 第 1 节
- 新建任务默认 status / owner 为 null 的含义未说明 — 第 2 节
- update_task 参数表 `priority` 重复 — 第 3 节
- `task_changes` 参数与返回结构本 skill 未展开 — 第 4 节
- update_iteration：`id` 必填但示例未带 — 第 7 节
