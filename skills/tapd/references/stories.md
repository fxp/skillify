# 需求（story）：查询、创建、更新、变更历史与字段元数据

> 来源：`https://open.tapd.cn/document/api-doc/API文档/api_reference/story/`（44 页）、`workflow/`、`subject/custom_priority/`（抓取于 2026-09-11）。
> **文档版，未用真实凭证调用验证。** 报错与行为描述均为「文档原文，未实测」，除非标注「无凭证探测」。
> 通用查询语法（时间区间、枚举 `|`、`LIKE<>`、游标翻页）与统一错误处理在 `query-errors-limits.md`，本文件不重复。

## 目录
1. 写代码前先拿三样元数据（状态、自定义字段、需求类别）
2. 查询需求 `GET /stories`
3. 计数 `GET /stories/count`
4. 创建需求 `POST /stories`
5. 更新需求 / 流转状态 `POST /stories`（带 id）
6. 变更历史 `GET /story_changes`（增量同步用）
7. 回收站 `GET /stories/get_removed_stories`
8. 优先级：`priority` 与 `priority_label`
9. 其他需求接口一览（未展开）
10. ⚠ 本文件汇总

示例统一用：
```python
import os, requests
BASE = "https://api.tapd.cn"
AUTH = (os.environ["TAPD_API_USER"], os.environ["TAPD_API_PASSWORD"])
WS = os.environ["TAPD_WORKSPACE_ID"]
```

---

## 1. 写代码前先拿三样元数据

需求的 `status`、`iteration_id`、`module`、分类等可选值**按项目动态配置**（story.html 原文：「属于动态可选值，需要通过接口获取」）。
不要硬编码 `planning / developing / resolved`，先查：

### 1a. 字段与候选值
**Endpoint**: `GET /stories/get_fields_info?workspace_id=`
返回 `data.<字段名> = {"name","options","html_type","label","pure_options","readonly"}`。`status.options` 是「英文 key → 中文名」映射，
文档示例里除默认的 `planning/developing/resolved/rejected` 外，还有 `status_1`、`status_3` ... 这类自定义状态 key。

### 1b. 状态中英文对照（按需求类别）
**Endpoint**: `GET /workflows/status_map`
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `workspace_id` | integer | 是 | 项目 ID |
| `system` | string | 是 | `story` 或 `bug` |
| `workitem_type_id` | integer | 否 | 需求类别 ID；**查询需求状态时需必传**（参数表说明原文） |

⚠ 文档自相矛盾：参数表把 `workitem_type_id` 标「否」，说明里又写「查询需求状态时需必传」，而示例 `?system=story&workspace_id=10158231` 没带。查需求时带上。

### 1c. 需求类别（workitem_type）
**Endpoint**: `GET /workitem_types?workspace_id=` —— 每个类别有自己的 `workflow_id`，不同类别的状态集合可以不同。
字段 `children_ids`：为空=允许任何子类别；为 `|`=不允许创建子需求（文档原文）。

### 1d. 自定义字段映射
**Endpoint**: `GET /stories/custom_fields_settings?workspace_id=`
返回 `CustomFieldConfig` 列表：`custom_field`（标识，如 `custom_field_one`）、`name`（显示名）、`type`、`options`（JSON 字符串）、`enabled`。
写入时既可以用 `custom_field_*`，也可以用 `cus_{显示名}`（后台自动转成对应的 custom_field_*）。

### 1e. 流转规则（改状态前需要补哪些字段）
**Endpoint**: `GET /workflows/all_transitions?workspace_id=&system=story&workitem_type_id=`
返回数组，每项 `Name`、`StepPrevious`、`StepNext`、`Appendfield[]`（`FieldName`、`Notnull`="yes" 为流转时必填）。
并行工作流中 `StepPrevious == StepNext` 的配置表示「完成该节点」需要的附加字段。

```python
def fields_info(ws):
    r = requests.get(f"{BASE}/stories/get_fields_info", auth=AUTH, params={"workspace_id": ws}, timeout=30)
    body = r.json(); assert body["status"] == 1, body.get("info")
    return body["data"]

status_options = fields_info(WS)["status"]["options"]     # {"planning": "规划中", ...}
```

## 2. 查询需求

**Endpoint**: `GET /stories`
**用途**: 批量查询需求，也用于按 ID 取单条（结果仍是列表）。

**关键参数**（完整参数表 50+ 项，此处只列常用）
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `workspace_id` | integer | **是** | — | 项目 ID |
| `id` | integer | 否 | — | 支持多 ID：`id=a,b,c`（英文逗号） |
| `name` | string | 否 | — | 标题，支持模糊匹配 |
| `status` | string | 否 | — | 英文状态 key，支持枚举 `planning\|developing` |
| `v_status` | string | 否 | — | 用**中文**状态名查询 |
| `with_v_status` | string | 否 | — | `1` 时返回中文状态 |
| `owner` | string | 否 | — | 处理人，支持模糊匹配 |
| `creator` | string | 否 | — | 创建人，支持多人员查询 |
| `iteration_id` | string | 否 | — | 支持不等于 `<>` 和枚举 |
| `include_sub_iteration` | string | 否 | 0 | `0` / `1` |
| `workitem_type_id` | string | 否 | — | 需求类别，支持枚举 |
| `category_id` | integer | 否 | — | 需求分类；`include_sub_category` 0/1 |
| `parent_id` / `ancestor_id` | integer | 否 | — | 父需求 / 查询指定需求下所有子需求 |
| `children_id` | string | 否 | — | 查「没有子需求」传 `丨` ⚠（见第 10 节） |
| `include_leaf_stories` | string | 否 | 0 | 是否包含子需求 |
| `priority_label` | string | 否 | — | 优先级（推荐，见第 8 节） |
| `label` | string | 否 | — | 标签，支持枚举 |
| `created` / `modified` / `completed` | datetime | 否 | — | 支持时间查询 `>`、`<`、`~` |
| `begin` / `due` | date | 否 | — | 预计开始 / 结束，支持时间查询 |
| `custom_field_*` | string/int | 否 | — | 自定义字段，支持枚举 |
| `limit` | integer | 否 | 30 | **最大 200** |
| `page` | integer | 否 | 1 | 页码 |
| `order` | string | 否 | — | `字段名 ASC/DESC` 后 urlencode，如 `order=created%20desc` |
| `fields` | string | 否 | 全部 | 返回字段，逗号分隔 |

**示例请求**
```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  "https://api.tapd.cn/stories?workspace_id=$TAPD_WORKSPACE_ID&id=1010104801869398419&fields=id,name,status,owner"
```
```python
r = requests.get(f"{BASE}/stories", auth=AUTH, timeout=30, params={
    "workspace_id": WS,
    "status": "planning|developing",
    "modified": ">2026-09-01 00:00:00",          # 时间查询语法，见 query-errors-limits.md
    "fields": "id,name,status,owner,iteration_id,modified",
    "limit": 200, "page": 1,
})
body = r.json()
if r.status_code != 200 or body.get("status") != 1:
    raise RuntimeError(body.get("info"))
stories = [row["Story"] for row in body["data"]]   # 每一项外面包了一层 {"Story": {...}}
```

**示例响应**（文档原文，精简）
```json
{"status": 1,
 "data": [{"Story": {"id": "1010104801869398419", "name": "abbbb", "status": "planning", "owner": ""}}],
 "info": "success"}
```

**注意事项**
- 不传 `fields` 时每条需求带回 `custom_field_one` ... `custom_field_200`、`custom_plan_field_1..10` 等数百个字段（文档示例如此），
  大批量拉取务必传 `fields`；错误码页也把 502 归因于「单次请求返回的数据量超大」。
- 所有值（包括 id、数字）在示例 JSON 里都是字符串；空值有 `""` 和 `null` 两种。
- `owner` 值形如 `"anyechen;"`（结尾分号，文档更新示例的响应），解析时按 `;` 切分并去空。
- 文档写 `limit` 超过 200 取不到更多，深分页上限 `page*limit ≤ 20000`，更多数据用游标，见 `query-errors-limits.md`。

## 3. 计数

**Endpoint**: `GET /stories/count` —— 参数与 `GET /stories` 基本相同（`workspace_id` 必填）。
响应：`{"status":1,"data":{"count":7},"info":"success"}`。适合在分页前算总页数。

## 4. 创建需求

**Endpoint**: `POST /stories`
**用途**: 新建一条需求，返回新建后的完整数据。一次一条。

**关键参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `workspace_id` | integer | **是** | 项目 ID |
| `name` | string | **是** | 标题（注意：缺陷是 `title`） |
| `owner` | string | 否 | 处理人昵称 |
| `creator` | string | 否 | 创建人 |
| `cc` / `developer` | string | 否 | 抄送人 / 开发人员 |
| `priority_label` | string | 否 | 优先级，推荐 |
| `iteration_id` | string | 否 | 迭代 ID（先用 `GET /iterations` 查到 ID） |
| `parent_id` | integer | 否 | 父需求 ID |
| `workitem_type_id` | integer | 否 | 需求类别 |
| `category_id` | integer | 否 | 需求分类 |
| `templated_id` | integer | 否 | 模板 ID |
| `begin` / `due` | date | 否 | 预计开始 / 结束 |
| `effort` | string | 否 | 预估工时 |
| `description` | string | 否 | 详细描述（HTML，文档示例返回 `<p>...</p>`） |
| `label` | string | 否 | 标签，不存在时自动创建；多个用 `\|` 分隔（原文「英文坚线」） |
| `cus_{自定义字段显示名}` | string | 否 | 按显示名写自定义字段 |
| `custom_field_*` | string/int | 否 | 按字段标识写自定义字段 |
| `is_apply_template_default_value` | integer | 否 | `1` 继承模板默认值、保密设置 |
| `apply_template` | string | 否 | `preset_stories`（预设子需求）、`preset_tasks`（预设子任务），逗号分隔 |

**示例请求**
```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  -d "workspace_id=$TAPD_WORKSPACE_ID" -d 'name=story_created_by_api' -d 'priority_label=High' -d 'owner=zhangsan;' \
  'https://api.tapd.cn/stories'
```
```python
r = requests.post(f"{BASE}/stories", auth=AUTH, timeout=30, data={      # 表单编码；也可 json=... （requests 会自动加 Content-Type）
    "workspace_id": WS, "name": "支付回调超时重试", "priority_label": "High",
    "owner": "zhangsan;", "iteration_id": iteration_id, "label": "后端|支付",
})
story = r.json()["data"]["Story"]           # 创建接口返回单个对象 {"Story": {...}}，不是列表
story_id = story["id"]                        # 19 位字符串
```

**示例响应**（文档原文，精简）
```json
{"status": 1, "data": {"Story": {"id": "1010104801124922063", "name": "story_created_by_api",
  "workspace_id": "10104801", "status": "planning", "created_from": "api", "priority_label": ""}}, "info": "success"}
```

**注意事项**
- 请求体格式：`application/x-www-form-urlencoded` 或 `application/json` 都行，但 JSON **必须**带 `Content-Type: application/json`（使用必读原文）。
- 状态不在创建参数表里——新需求进入工作流起始状态（文档示例为 `planning`）⚠ 文档未说明能否在创建时直接指定 status。
- 文档参数表把 `business_value` 列了两次（integer 与 string）⚠ 文档自相矛盾，按项目实际配置传。

## 5. 更新需求 / 流转状态

**Endpoint**: `POST /stories`（**同一路径，带 `id` 即为更新**；没有 PUT / PATCH）
**用途**: 改字段或流转状态，一次一条；返回更新后的数据。

**关键参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | integer | **是** | 需求 ID（19 位长 ID） |
| `workspace_id` | integer | **是** | 项目 ID |
| `status` | string | 否 | 英文状态 key。并行工作流时「按状态重置来更新节点」，进行中节点用 `update_story_step_status` |
| `v_status` | string | 否 | 用中文状态名流转 |
| `current_user` | string | 否 | 变更人（记在变更历史里） |
| `owner` | string | 否 | 处理人 |
| `iteration_id` | string | 否 | 挪到别的迭代 |
| `is_auto_close_task` | integer | 否 | 需求流转到结束状态时 `1`=自动关闭关联任务，默认 0 |
| 其余 | — | 否 | 与创建相同：`name`、`priority_label`、`label`、`cus_*`、`custom_field_*`…… |

**示例请求**
```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  -d 'id=1010104801125341253' -d "workspace_id=$TAPD_WORKSPACE_ID" -d 'v_status=实现中' -d 'current_user=zhangsan' \
  'https://api.tapd.cn/stories'
```
```python
r = requests.post(f"{BASE}/stories", auth=AUTH, timeout=30,
                  data={"id": story_id, "workspace_id": WS, "status": "developing", "current_user": "zhangsan"})
body = r.json()
if body.get("status") != 1:
    raise RuntimeError(body.get("info"))     # 流转缺少必填附加字段等情况的报错文案文档未列出 ⚠
```

**注意事项**
- 改状态前用 `GET /workflows/all_transitions` 看目标流转有没有 `Notnull="yes"` 的附加字段，一并传上。
- `parent_id` 有专门接口 `POST /stories/update_story_parent`；改需求类别用 `POST /stories/change_workitem_type`（未展开）。
- 批量更新：`POST /stories/batch_update_story`（未展开，参数见该文档页）。
- 在抓取的 api_reference 路由表里**没有删除需求本身的接口**（只有回收站查询）。

## 6. 变更历史（增量同步用）

**Endpoint**: `GET /story_changes`
**用途**: 拿需求的字段变更记录。做状态停留时长分析，文档建议改用 `measure/get_life_times`（本 skill 未覆盖）。

**关键参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `workspace_id` | integer | **是** | 项目 ID |
| `story_id` | integer | 二选一 | 需求 ID，支持多 ID |
| `created` | datetime | 二选一 | **填日期**，如 `created=2022-02-22` 返回这一天的变更；也支持时间查询语法 |
| `change_field` | string | 否 | 只要某字段的变更，如 `status` |
| `change_type` | string | 否 | `sync_copy` / `story_status_relation` / `story_task_relation` / `api` / `smart_commit` / `auto_task` / `auto_workflow` / `manual_update` / `import_update` |
| `need_parse_changes` | integer | 否 | 默认 1 返回 `field_changes`；0 不返回 |
| `limit` | integer | 否 | 默认 30，**最大 100**（比列表接口的 200 小） |
| `page` / `order` / `fields` | — | 否 | 同列表接口 |

**示例请求**
```python
r = requests.get(f"{BASE}/story_changes", auth=AUTH, timeout=30, params={
    "workspace_id": WS, "created": "2026-09-10", "change_field": "status", "limit": 100, "page": 1})
for row in r.json()["data"]:
    ch = row["WorkitemChange"]
    for fc in ch.get("field_changes", []):
        print(ch["story_id"], ch["creator"], ch["created"], fc["field"], fc["value_before"], "->", fc["value_after"])
```

**示例响应**（文档原文，精简）
```json
{"status": 1, "data": [{"WorkitemChange": {
  "id": "1010104801027730979", "creator": "anyechen", "created": "2015-06-30 14:28:53",
  "changes": "[{\"field\":\"parent_id\",\"value_before\":\"0\",\"value_after\":\"1010104801056751739\"}]",
  "entity_type": "Story",
  "field_changes": [{"field": "parent_id", "value_before": "0", "value_after": "1010104801056751739",
                     "value_before_parsed": "0", "value_after_parsed": "工具调研", "field_label": "父需求"}],
  "story_id": "1010104801056751735"}}]}
```

**注意事项**
- 包装键是 `WorkitemChange`，不是 `StoryChange`；`changes` 是 **JSON 字符串**，`field_changes` 才是已解析的数组。
- 缺陷的变更历史结构完全不同（`BugChange`，一行一个字段），见 `bugs.md`。
- 字段说明表把 `app_id` 解释为「检查项」、`change_type_detail` 解释为「api账号」⚠ 文档说明疑似错位。
- 计数：`GET /story_changes/count`。

## 7. 回收站

**Endpoint**: `GET /stories/get_removed_stories`
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `workspace_id` | integer | 是 | 项目 ID |
| `id` / `creator` | — | 否 | 过滤 |
| `is_archived` | integer | 否 | 默认 0 不返回归档；`1` 仅返回归档的需求 |
| `created` / `deleted` | date | 否 | 创建 / 删除时间 |
| `limit` / `page` | integer | 否 | 默认 30，最大 200 |

响应 `RemovedStory`：`id`、`name`、`creator`、`created`、`operation_user`（删除人）、`deleted`、`is_archived`。
增量同步时用它识别「已删除」，列表接口不会返回已删除的需求 ⚠ 文档未明说，按常理推断，拿到凭证后需验证。

## 8. 优先级：`priority` 与 `priority_label`

`subject/custom_priority/` 原文结论：「建议使用所见即所得，无映射关系的 `priority_label` 字段」。

| 对象 | 旧 `priority` 取值（文档称「将不再使用」） | `priority_label` |
|---|---|---|
| 需求 | `4`=High、`3`=Middle、`2`=Low、`1`=Nice To Have | 直接传显示值，如 `High` |
| 缺陷 | `urgent` / `high` / `medium` / `low` / `insignificant` | 如 `高`、`低` |
| 任务 | 同需求 4/3/2/1 | 如 `High` |

- 项目一旦启用自定义优先级，旧 `priority` 的返回值会变成任意字符串（原文举例 `priority=非常高`）。
- ⚠ 文档自相矛盾：`custom_priority` 页的「获取需求」示例用 `priority=3` 表示 High，而映射表里 High 是 `4`；
  `update_story` 页示例又直接传 `priority=高`。统一改用 `priority_label` 可以绕开。
- 可选值从 `GET /stories/get_fields_info` 的 `priority_label` / `priority` 字段取。

## 9. 其他需求接口一览（未展开，参数见对应文档页）

| 能力 | Endpoint |
|---|---|
| 批量更新 | `POST /stories/batch_update_story` |
| 复制需求 | `/stories/copy_story`（文档未写 HTTP 方法 ⚠） |
| 需求分类 CRUD | `GET/POST /story_categories`、`GET /story_categories/count` |
| 需求 ↔ 缺陷关联 | `GET /stories/get_related_bugs`、`POST /stories/remove_story_bug_raletions`（路径原文拼写 raletions） |
| 需求 ↔ 测试用例 | `GET /stories/get_story_tcase`、`POST /stories/add_story_tcase` |
| 需求间关联 / 前后置 | `GET /stories/get_link_stories`、`POST /stories/add_story_link_relations`、`POST /stories/save_time_relations` |
| 并行工作流节点 | `GET /stories/get_story_step_list`、`POST /stories/update_story_step_status`、`POST /stories/reset_workitem_steps` |
| 保密需求 | `GET /secret_stories`、`GET /stories/get_secret_info` |
| 模板 | `GET /stories/template_list`、`GET /stories/get_default_story_template` |
| 字段中英文 | `GET /stories/get_fields_lable`（路径原文拼写 lable） |

## 10. ⚠ 本文件汇总
- `status_map` 的 `workitem_type_id`：标「否」却写「查询需求状态时需必传」，示例未传 — 1b
- `children_id` 查空传 `丨`（全角/中文竖线字形）还是半角 `|` 不明 — 第 2 节
- 创建时能否直接指定 `status` 未说明 — 第 4 节
- `business_value` 在参数表出现两次、类型不同 — 第 4 节
- 流转缺字段时的报错文案未列出 — 第 5 节
- `story_changes` 字段说明 `app_id`=「检查项」、`change_type_detail`=「api账号」疑似错位 — 第 6 节
- 列表接口是否排除已删除需求未明说 — 第 7 节
- 优先级示例 `priority=3`/`priority=高` 与映射表矛盾 — 第 8 节
- `copy_story` 未写 HTTP 方法 — 第 9 节
