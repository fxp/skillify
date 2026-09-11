# 缺陷（bug）：查询、提交、流转、变更历史与枚举

> 来源：`https://open.tapd.cn/document/api-doc/API文档/api_reference/bug/`（23 页）、`workflow/`、`subject/custom_priority/`（抓取于 2026-09-11）。
> **文档版，未用真实凭证调用验证。** 报错与行为描述均为「文档原文，未实测」，除非标注「无凭证探测」。
> 通用查询语法与错误处理见 `query-errors-limits.md`；动态候选值（状态、模块、版本）的取法与需求相同，见 `stories.md` 第 1 节。

## 目录
1. 缺陷和需求的字段名不一样（最常见的错误）
2. 查询缺陷 `GET /bugs`
3. 计数 `GET /bugs/count`
4. 提交缺陷 `POST /bugs`
5. 更新 / 流转缺陷 `POST /bugs`（带 id）
6. 变更历史 `GET /bug_changes`
7. 静态枚举：优先级、严重程度、解决方法
8. 状态与流转规则
9. 其他缺陷接口一览
10. ⚠ 本文件汇总

示例统一用：
```python
import os, requests
BASE = "https://api.tapd.cn"
AUTH = (os.environ["TAPD_API_USER"], os.environ["TAPD_API_PASSWORD"])
WS = os.environ["TAPD_WORKSPACE_ID"]
```

---

## 1. 缺陷和需求的字段名不一样

同一个概念，缺陷用的字段名和需求 / 任务不同。从需求代码复制过来改路径，查询条件会被当成未知参数（是报错还是被忽略 ⚠ 文档未说明）：

| 概念 | 需求 `/stories` | 任务 `/tasks` | **缺陷 `/bugs`** |
|---|---|---|---|
| 标题 | `name` | `name` | **`title`** |
| 当前处理人 | `owner` | `owner` | **`current_owner`** |
| 创建人 | `creator` | `creator` | **`reporter`** |
| 最后修改人 | — | — | `lastmodify` |
| 开发 / 测试人员 | `developer` | — | `de` / `te` |
| 旧优先级取值 | `4/3/2/1` | `4/3/2/1` | `urgent/high/medium/low/insignificant` |
| 响应包装键 | `Story` | `Task` | `Bug` |
| 变更历史 | `GET /story_changes`（`WorkitemChange`） | `GET /task_changes` | `GET /bug_changes`（`BugChange`，结构不同） |

## 2. 查询缺陷

**Endpoint**: `GET /bugs`
**用途**: 批量查询缺陷（默认一页 30 条），也可按 id 查单条。

**关键参数**（完整表 60+ 项，只列常用）
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `workspace_id` | integer | **是** | — | 项目 ID |
| `id` | integer | 否 | — | 多 ID 用英文逗号 |
| `title` | string | 否 | — | 标题，模糊匹配 |
| `status` | string | 否 | — | 英文状态 key；支持**不等于**与**枚举**查询 |
| `v_status` | string | 否 | — | 中文状态名 |
| `severity` | string | 否 | — | 严重程度，支持枚举 |
| `priority_label` | string | 否 | — | 优先级（推荐） |
| `current_owner` | string | 否 | — | 处理人，模糊匹配 |
| `reporter` | string | 否 | — | 创建人，多人员查询 |
| `participator` | string | 否 | — | 参与人，`A\|B` 或、`A;B` 与 |
| `te` / `de` | string | 否 | — | 测试 / 开发人员，模糊匹配 |
| `iteration_id` / `module` | string | 否 | — | 支持枚举 |
| `version_report` | string | 否 | — | 发现版本，枚举查询 |
| `resolution` / `source` / `frequency` | string | 否 | — | 支持枚举 |
| `created` / `modified` / `resolved` / `closed` / `in_progress_time` / `verify_time` / `reject_time` | datetime | 否 | — | 支持时间查询 |
| `label` | string | 否 | — | 标签，支持枚举 |
| `custom_field_*` | string/int | 否 | — | 支持枚举 |
| `limit` | integer | 否 | 30 | 最大 200 |
| `page` | integer | 否 | 1 | 页码 |
| `order` | string | 否 | — | 如 `created%20desc` |
| `fields` | string | 否 | 全部 | 逗号分隔 |

**示例请求**
```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  "https://api.tapd.cn/bugs?workspace_id=$TAPD_WORKSPACE_ID&status=<>closed&severity=fatal|serious&limit=2"
```
```python
r = requests.get(f"{BASE}/bugs", auth=AUTH, timeout=30, params={
    "workspace_id": WS,
    "status": "<>closed",                          # 不等于查询
    "severity": "fatal|serious",                   # 枚举查询
    "modified": "2026-09-10 00:00:00~2026-09-10 23:59:59",
    "fields": "id,title,status,severity,current_owner,modified",
    "limit": 200,
})
body = r.json()
if r.status_code != 200 or body.get("status") != 1:
    raise RuntimeError(body.get("info"))
bugs = [row["Bug"] for row in body["data"]]
```

**示例响应**（文档原文，精简）
```json
{"status": 1, "data": [{"Bug": {"id": "1010158231500628817", "title": "【示例】新官网Chrome浏览器兼容性bug",
  "priority": "high", "severity": "prompt", "status": "in_progress", "reporter": "anyechen",
  "current_owner": null, "created": "2017-06-20 16:49:19", "modified": "2018-01-12 14:45:27",
  "flows": "new", "label": "阻塞|重点关注"}}]}
```

**注意事项**
- `current_owner`、`de`、`te` 等人员字段在示例里可能是 `null` 而不是 `""`，两种都要处理。
- 文档的 get_bugs 示例 JSON 不完整（有尾逗号、省略号），不能当作完整字段表，字段以 `bug.html` 字段说明为准。

## 3. 计数

**Endpoint**: `GET /bugs/count` —— 参数同 `GET /bugs`，响应 `{"status":1,"data":{"count":2},"info":"success"}`。
文档示例：`/bugs/count?workspace_id=10158231&current_owner=anyechen;&priority=high&status=new`（注意 `anyechen;` 的分号）。

## 4. 提交缺陷

**Endpoint**: `POST /bugs`
**用途**: 创建一个缺陷，一次一条，返回新建数据（`data.Bug`）。

**关键参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `workspace_id` | integer | **是** | 项目 ID |
| `title` | string | **是** | 缺陷标题 |
| `description` | string | 否 | 详细描述，可含 HTML（文档示例 `<img src="..."/>`） |
| `severity` | string | 否 | 严重程度，取值见第 7 节 |
| `priority_label` | string | 否 | 优先级（推荐） |
| `current_owner` | string | 否 | 处理人 |
| `reporter` | string | 否 | 创建人 |
| `cc` / `participator` / `te` / `de` | string | 否 | 人员字段 |
| `module` / `feature` / `iteration_id` / `release_id` | — | 否 | 归属 |
| `version_report` / `baseline_find` | string | 否 | 发现版本 / 发现基线 |
| `bugtype` / `source` / `frequency` / `originphase` / `platform` / `os` | string | 否 | 分类字段 |
| `template_id` | integer | 否 | 模板 ID |
| `is_apply_template_default_value` | integer | 否 | `1` 继承模板默认值 |
| `label` | string | 否 | 不存在自动创建，多个 `\|` 分隔 |
| `effort` | integer | 否 | 预估工时 |
| `cus_{显示名}` / `custom_field_*` | — | 否 | 自定义字段 |

**示例请求**
```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  -d "workspace_id=$TAPD_WORKSPACE_ID" -d 'title=登录页在 Safari 下白屏' -d 'severity=serious' \
  -d 'priority_label=高' -d 'current_owner=lisi;' \
  'https://api.tapd.cn/bugs'
```
```python
r = requests.post(f"{BASE}/bugs", auth=AUTH, timeout=30, data={
    "workspace_id": WS, "title": "登录页在 Safari 下白屏",
    "severity": "serious", "priority_label": "高", "current_owner": "lisi;",
    "description": "<p>复现步骤：...</p>",
})
bug = r.json()["data"]["Bug"]
print(bug["id"], bug["status"])          # 文档示例新缺陷 status 为 "new"
```

**注意事项**
- 用 `-d` 传含 HTML 的 description 时，`&`、`+` 等字符要 urlencode（curl 用 `--data-urlencode`，requests 的 `data=` 会自动处理）。
- 缺陷描述里的图片，文档示例直接内嵌外链 `<img>`；上传图片接口在 attachment 目录（本 skill 未覆盖）。

## 5. 更新 / 流转缺陷

**Endpoint**: `POST /bugs`（同一路径，带 `id`；没有 PUT）
**用途**: 改字段或流转状态，一次一条；批量用 `POST /bugs/batch_update_bug`（未展开）。

**关键参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | integer | **是** | 缺陷 ID |
| `workspace_id` | integer | **是** | 项目 ID |
| `status` / `v_status` | string | 否 | 英文 key / 中文名流转 |
| `current_user` | string | 否 | 变更人 |
| `current_owner` | string | 否 | 新处理人 |
| `keep_owner` | integer | 否 | `1` = 保留处理人（流转时不按工作流自动改处理人 ⚠ 文档只写「是否保存处理人」） |
| `resolution` | string | 否 | 解决方法，取值见第 7 节 |
| `fixer` / `closer` / `confirmer` | string | 否 | 修复人 / 关闭人 / 验证人 |
| `version_fix` / `version_close` | string | 否 | 合入版本 / 关闭版本 |
| 其余 | — | 否 | 与创建相同 |

**示例请求**
```bash
curl -u "$TAPD_API_USER:$TAPD_API_PASSWORD" \
  -d 'id=1010158231500628817' -d "workspace_id=$TAPD_WORKSPACE_ID" \
  -d 'status=resolved' -d 'resolution=fixed' -d 'current_user=lisi' \
  'https://api.tapd.cn/bugs'
```
```python
r = requests.post(f"{BASE}/bugs", auth=AUTH, timeout=30, data={
    "id": bug_id, "workspace_id": WS, "status": "resolved", "resolution": "fixed", "current_user": "lisi"})
if r.json().get("status") != 1:
    raise RuntimeError(r.json().get("info"))
```

**注意事项**
- `resolved` / `closed` 等状态 key 是**项目可配置**的，先用 `GET /workflows/status_map?system=bug&workspace_id=` 确认（第 8 节）。
- 目标流转若有必填附加字段（`all_transitions` 里 `Notnull="yes"`），要一起传。
- 抓取的路由表里**没有删除缺陷本身的接口**，只有 `GET /bugs/get_removed_bugs`（回收站）。

## 6. 变更历史

**Endpoint**: `GET /bug_changes`

**关键参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `workspace_id` | integer | **是** | 项目 ID |
| `bug_id` | integer | 见下 | 缺陷 ID，支持多 ID |
| `created` | datetime | 见下 | 按天：`created=2022-02-22` |
| `field` | string | 否 | 只看某字段的变更 |
| `author` | string | 否 | 变更人 |
| `include_add_bug` | integer | 否 | `1` 返回「创建缺陷」这条记录 |
| `limit` | integer | 否 | 默认 30，最大 200 |
| `page` / `order` / `fields` | — | 否 | 同列表 |

⚠ 文档自相矛盾：「请求数限制」写 `created` 与 `bug_id` **二选一必填**，参数表却把两者都标为「是」。按二选一实现，至少带一个。

**示例请求**
```python
r = requests.get(f"{BASE}/bug_changes", auth=AUTH, timeout=30,
                 params={"workspace_id": WS, "created": "2026-09-10", "field": "status", "limit": 200})
for row in r.json()["data"]:
    c = row["BugChange"]
    print(c["bug_id"], c["author"], c["created"], c["field"], c["old_value"], "->", c["new_value"])
```

**示例响应**（文档原文）
```json
{"status": 1, "data": [{"BugChange": {"id": "10101582315000015921", "bug_id": "1010158231500628815",
  "author": "anyechen", "field": "severity", "old_value": "serious", "new_value": "normal",
  "memo": null, "created": "2019-06-26 20:48:52", "workspace_id": "10158231"}}]}
```

**注意事项**
- `BugChange` 一行一个字段（`field` / `old_value` / `new_value`），和需求的 `WorkitemChange`（`field_changes` 数组）结构不同。
- 缺陷变更 `limit` 最大 200，需求变更最大 100。
- 计数：`GET /bug_changes/count`。

## 7. 静态枚举

来源 `bug.html`（文档原文）。**优先级旧取值文档标注「将不再使用」，写入改用 `priority_label`。**

| 优先级 priority（旧） | 字面值 |
|---|---|
| `urgent` | 紧急 |
| `high` | 高 |
| `medium` | 中 |
| `low` | 低 |
| `insignificant` | 无关紧要 |

| 严重程度 severity | 字面值 |
|---|---|
| `fatal` | 致命 |
| `serious` | 严重 |
| `normal` | 一般 |
| `prompt` | 提示 |
| `advice` | 建议 |

| 解决方法 resolution | 字面值 | resolution | 字面值 |
|---|---|---|---|
| `ignore` | 无需解决 | `intentional` | 设计如此 |
| `fix` | 延期解决 | `unclear` | 问题描述不准确 |
| `failed` | 无法重现 | `hold` | 挂起 |
| `external` | 外部原因 | `feature` | 需求变更 |
| `duplicated` | 重复 | `fixed` | 已解决 |
| `transferred to story` | 已转需求 | | |

- 注意 `fix` 的字面值是「延期解决」，**已修复是 `fixed`**——凭英文直觉会传错。
- `transferred to story` 取值带空格，放 URL 时要 urlencode。
- `custom_priority` 页的缺陷示例：新 `priority_label=低` / 旧 `priority=low`；新 `priority_label=高` / 旧 `priority=high`。

## 8. 状态与流转规则

- 状态中英文：`GET /workflows/status_map?system=bug&workspace_id=`。文档示例（某项目，**非通用**）：
  `new` 新、`in_progress` 接受/处理、`resolved` 已解决、`verified` 已验证、`reopened` 重新打开、`rejected` 已拒绝、`closed` 已关闭。
- 流转细则：`GET /workflows/all_transitions?system=bug&workspace_id=` —— `StepPrevious` → `StepNext`，`Appendfield[].Notnull="yes"` 为必填。
- 所有结束状态：`GET /workflows/all_last_steps`；起始状态：`GET /workflows/first_step`（参数见文档页，未展开）。
- 候选值总表：`GET /bugs/get_fields_info?workspace_id=`（返回「英文 Key」与「中文值」）；自定义字段：`GET /bugs/custom_fields_settings?workspace_id=`。

```python
def bug_status_map(ws):
    r = requests.get(f"{BASE}/workflows/status_map", auth=AUTH, timeout=30,
                     params={"workspace_id": ws, "system": "bug"})
    return r.json()["data"]           # {"new": "新", "resolved": "已解决", ...}

closed_keys = [k for k, v in bug_status_map(WS).items() if v in ("已关闭",)]
```

## 9. 其他缺陷接口一览（未展开）

| 能力 | Endpoint |
|---|---|
| 批量更新 / 流转 | `POST /bugs/batch_update_bug` |
| 回收站 | `GET /bugs/get_removed_bugs` |
| 缺陷关联的需求 | `GET /bugs/get_related_stories` |
| 缺陷间关联 | `GET /bugs/get_link_bugs`、`POST /bugs/link_bugs`、`POST /bugs/delete_link_bugs` |
| 模板 | `GET /bugs/template_list`、`GET /bugs/get_default_bug_template` |
| 字段中英文 | `GET /bugs/get_fields_lable` |
| 修改系统字段选项（会覆盖原有选项） | `POST /bugs/update_system_select_field_options` |
| 复制缺陷 | `/bugs/copy_bug`（文档未写 HTTP 方法 ⚠） |

## 10. ⚠ 本文件汇总
- 用错字段名（如对 `/bugs` 传 `name`）时是报错还是静默忽略未说明 — 第 1 节
- `keep_owner` 的确切语义只写了「是否保存处理人」 — 第 5 节
- `bug_changes` 的 `created` / `bug_id`：正文二选一、参数表都标必填 — 第 6 节
- `copy_bug` 未写 HTTP 方法 — 第 9 节
