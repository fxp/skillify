# 多维表格（Bitable / Base）

来源：`open.feishu.cn/document/server-docs/docs/bitable-v1/*`、`docs/bitable-v1/*`（抓取于 2026-09-11）。
Base URL `https://open.feishu.cn/open-apis`，鉴权 `Authorization: Bearer <tenant_access_token 或 user_access_token>`。
**报错码与行为描述除标注「无凭证探测」外均为文档原文，未实测。**

## 目录

1. [概念与 ID：app_token / table_id / view_id / record_id](#1-概念与-id)
2. [权限前提（最常见的失败原因）](#2-权限前提)
3. [使用限制](#3-使用限制)
4. [建多维表格、数据表、字段](#4-建多维表格数据表字段)
5. [字段值格式：写入 vs 读出不一样](#5-字段值格式)
6. [新增 / 更新 / 删除记录（单条与批量）](#6-新增--更新--删除记录)
7. [查询记录：search + filter + 分页](#7-查询记录)
8. [按 record_id 批量获取](#8-按-record_id-批量获取)
9. [附件字段](#9-附件字段)
10. [记录变更事件](#10-记录变更事件)
11. [错误码](#11-错误码)
12. [容易写错的地方](#12-容易写错的地方)

---

## 1. 概念与 ID

| ID | 是什么 | 怎么拿 |
|---|---|---|
| `app_token` | 一个多维表格（Base App）的唯一标识 | URL 以 `feishu.cn/base/` 开头：路径里 `base/` 后那一段；URL 以 `feishu.cn/wiki/` 开头：**URL 里的是 wiki 节点 token，不是 app_token**，要调知识库「获取知识空间节点信息」接口，`obj_type` 为 `bitable` 时 `obj_token` 才是 app_token；嵌在文档里的：调「获取文档所有块」，`bitable.token` 是 `app_token_table_id` 用 `_` 拼接 |
| `table_id` | 数据表 | URL 里 `table=tbl...`；或列出数据表接口。长度 ≤50 |
| `view_id` | 视图 | URL 里 `view=vew...`；或列出视图接口；嵌入文档的多维表格暂时拿不到 view_id |
| `record_id` | 一行记录 | 查询记录接口，形如 `recxxxx` |
| `field_id` / 字段名 | 一列 | 列出字段接口。**记录读写时 `fields` 的 key 是字段名（列标题），不是 field_id** |

一个多维表格可以是独立文件、知识库节点、文档内嵌块或电子表格内嵌块四种形态，app_token 获取方式各不相同（见上表）。

---

## 2. 权限前提

- **用 tenant_access_token 访问时，应用必须是该多维表格的所有者或协作者**，否则调用失败。两种办法：
  在多维表格里"添加文档应用"把应用加为协作者；或者直接用应用身份创建多维表格再操作。
- 写记录前，调用身份要有编辑权限，否则接口返回 **HTTP 403 或 400**（文档原文）。
- 多维表格开了**高级权限**时，调用身份要有"可管理"权限，否则可能**调用成功但返回数据为空**（查询记录页原文）。
- 用 user_access_token 调用时，数据范围是该用户能看到的；创建出来的多维表格所有者是该用户。
- API 权限（任一）：写记录 `base:record:create` / `base:record:update` 或 `bitable:app`；查询 `base:record:retrieve`、`bitable:app` 或 `bitable:app:readonly`。

---

## 3. 使用限制

- 批量接口单次最多 **1,000 条**，且**要么全部成功要么全部失败**，没有部分成功。
- 为保证稳定性，**对同一个多维表格同一时间只发一个写请求**（文档建议）。并发写是 `1254002 Fail` 等错误的常见原因。
- 单个多维表格：字段 300 个（公式字段 ≤100）、视图 200 个、数据表 + 仪表盘 100 个、高级权限自定义角色 30、协作者 200。
- 记录数：概述页说"不同租户最大数量不同，开放平台没有额外限制"；错误码表却有 `1254103 RecordExceedLimit, 限制20,000条`。⚠ 文档自相矛盾。
- 多维表格**不支持提升频控**（频控策略页原文）。
- 从其他数据源同步来的数据表，不能通过接口增删改记录。

频控：新增 / 更新 / 删除（含批量）50 次/秒；查询、批量获取 20 次/秒；列出数据表 / 字段 20 次/秒；新增数据表 / 字段 10 次/秒；**创建多维表格 20 次/分钟**。

---

## 4. 建多维表格、数据表、字段

| 我想 | Endpoint | 关键参数 |
|---|---|---|
| 创建多维表格 | `POST /open-apis/bitable/v1/apps` | body `name`（≤255）、`folder_token`（默认云空间根目录）、`time_zone`（如 `Asia/Macau`） |
| 取多维表格元数据 | `GET /open-apis/bitable/v1/apps/:app_token` | |
| 列出数据表 | `GET /open-apis/bitable/v1/apps/:app_token/tables` | `page_size` 默认 20、最大 100；`page_token` |
| 新增数据表 | `POST /open-apis/bitable/v1/apps/:app_token/tables` | |
| 列出字段 | `GET /open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields` | `view_id`、`page_size`（默认 20、最大 100）、`text_field_as_array` |
| 新增字段 | `POST /open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields` | `field_name`、`type`、`ui_type`、`property`（见字段编辑指南） |

```bash
curl -s -X POST 'https://open.feishu.cn/open-apis/bitable/v1/apps' \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN" -H 'Content-Type: application/json; charset=utf-8' \
  -d '{"name":"客户跟进","time_zone":"Asia/Shanghai"}'
```

字段 `type` 枚举（同一 type 用 `ui_type` 区分展示形态）：

| type | 字段 | ui_type |
|---|---|---|
| 1 | 文本 / 条码 / 邮箱 | `Text` / `Barcode` / `Email` |
| 2 | 数字 / 进度 / 货币 / 评分 | `Number` / `Progress` / `Currency` / `Rating` |
| 3 / 4 | 单选 / 多选 | `SingleSelect` / `MultiSelect` |
| 5 | 日期 | `DateTime` |
| 7 | 复选框 | `Checkbox` |
| 11 | 人员 | `User` |
| 13 | 电话号码 | `Phone` |
| 15 | 超链接 | `Url` |
| 17 | 附件 | `Attachment` |
| 18 / 21 | 单向关联 / 双向关联 | `SingleLink` / `DuplexLink` |
| 19 / 20 | 查找引用 / 公式 | `Lookup` / `Formula` |
| 22 | 地理位置 | `Location` |
| 23 | 群组 | `GroupChat` |
| 24 | 流程 | （数据结构页的 ui_type 列表未收录） |
| 1001 / 1002 | 创建时间 / 最后更新时间 | `CreatedTime` / `ModifiedTime` |
| 1003 / 1004 | 创建人 / 修改人 | `CreatedUser` / `ModifiedUser` |
| 1005 | 自动编号 | `AutoNumber` |
| 3001 | 按钮 | `Button` |

---

## 5. 字段值格式

**写入和读出的格式不对称**，这是最容易写错的地方。`fields` 是 `map<字段名, 值>`。

| 字段类型 | 写入（新增 / 更新记录） | 读出（查询记录返回） |
|---|---|---|
| 文本 (1) | `"拜访潜在客户"`（字符串；批量接口说明"原值展示，不支持 markdown"） | **对象列表** `[{"type":"text","text":"..."}]`，还可能有 `mention`、`url` 类型片段 |
| 数字 / 货币 / 评分 / 进度 (2) | 数字：`10`、`3`、`0.25` | 数字 |
| 单选 (3) | 选项名字符串 `"进行中"`；**不存在的选项会被自动新建** | 字符串 |
| 多选 (4) | `["选项1","选项2"]`；新值自动建选项，重复的新值会建出多个同名选项 | 字符串数组 |
| 日期 (5) | **毫秒**时间戳 `1674206443000` | 毫秒时间戳 |
| 复选框 (7) | `true` / `false` | 布尔 |
| 人员 (11) | `[{"id":"ou_xxx"}]`，**ID 类型必须与 query 参数 `user_id_type` 一致** | `[{"id","name","en_name","email","avatar_url"}]` |
| 群组 (23) | `[{"id":"oc_xxx"}]` | `[{"id","name","avatar_url"}]` |
| 电话 (13) | 字符串，匹配 `(\+)?\d*`，≤64 | 字符串 |
| 超链接 (15) | `{"text":"飞书多维表格官网","link":"https://..."}` | 同 |
| 附件 (17) | `[{"file_token":"..."}]`（先上传到**该**多维表格，见第 9 节） | `[{"file_token","name","size","type","url","tmp_url"}]` |
| 单向 / 双向关联 (18/21) | 新增记录示例为 `["recHTLvO7x","recbS8zb2m"]`（记录 ID 数组） | `{"link_record_ids":[...]}` |
| 地理位置 (22) | `"116.397755,39.903179"`（经度,纬度字符串） | 对象 `{location, pname, cityname, adname, address, name, full_address}` |
| 创建 / 修改时间、创建 / 修改人、自动编号、公式、查找引用 | 只读，不能写 | 见记录数据结构页 |

⚠ 文档自相矛盾：关联字段在「记录数据结构」页的 value 描述为 `{"link_record_ids": [...]}` 对象，而「新增记录」请求示例直接写 `["recHTLvO7x", ...]` 数组。
写入时以新增记录示例为准，读出时按对象解析；拿到凭证后需实测。

单元格上限：文本 10 万字符；多选单元格 ≤1000 个选项、字段 ≤20000 个选项；附件 ≤100；关联 ≤500；群组 ≤10。

---

## 6. 新增 / 更新 / 删除记录

| 我想 | Endpoint | 请求体 |
|---|---|---|
| 新增一条 | `POST /open-apis/bitable/v1/apps/:app_token/tables/:table_id/records` | `{"fields": {...}}` |
| 新增多条（≤1000） | `POST .../records/batch_create` | `{"records": [{"fields": {...}}, ...]}` |
| 更新一条 | `PUT .../records/:record_id` | `{"fields": {...}}`（只传要改的字段） |
| 更新多条（≤1000） | `POST .../records/batch_update` | `{"records": [{"record_id": "rec...", "fields": {...}}]}`——`record_id` 表格标"否"但文档注明**实际必填** |
| 删除一条 | `DELETE .../records/:record_id` | |
| 删除多条 | `POST .../records/batch_delete` | `{"records": ["rec1", "rec2"]}`（字符串数组） |

写接口共有的 query 参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `user_id_type` | string | 否 | `open_id` | 决定人员字段里 `id` 的类型 |
| `client_token` | string | 否 | — | **标准 uuidv4**，幂等键（batch_update 无此参数） |
| `ignore_consistency_check` | boolean | 否 | `false` | `true` 提高性能但可能短暂读写不一致 |

**示例请求**

```bash
curl -s -X POST "https://open.feishu.cn/open-apis/bitable/v1/apps/$APP_TOKEN/tables/$TABLE_ID/records/batch_create?user_id_type=open_id&client_token=$(uuidgen | tr A-Z a-z)" \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN" -H 'Content-Type: application/json; charset=utf-8' \
  -d '{"records":[{"fields":{"任务名称":"拜访潜在客户","工时":10,"单选":"进行中","日期":1674206443000,"人员":[{"id":"ou_2910013f1e6456f16a0ce75ede9abcef"}]}}]}'
```

```python
import uuid, requests

def batch_create(app_token, table_id, rows, id_type="open_id"):
    """rows: list[dict]，每个 dict 是 {字段名: 写入格式的值}；自动按 1000 条切片、串行写。"""
    url = f"{BASE}/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
    ids = []
    for i in range(0, len(rows), 1000):
        chunk = rows[i:i + 1000]
        r = requests.post(url, params={"user_id_type": id_type, "client_token": str(uuid.uuid4())},
                          headers={"Authorization": f"Bearer {tenant_access_token()}"},
                          json={"records": [{"fields": f} for f in chunk]}, timeout=30)
        body = r.json()
        if body.get("code") != 0:     # 1254xxx 业务错误多数是 HTTP 200
            raise RuntimeError(body)
        ids += [rec["record_id"] for rec in body["data"]["records"]]
    return ids
```

**示例响应**：`{"code":0,"msg":"success","data":{"records":[{"record_id":"rec...","fields":{...}}]}}`（单条接口是 `data.record`）。

注意：写接口响应里 `created_by`、`created_time`、`last_modified_*`、`shared_url`、`record_url` **不返回**（文档原文）。

---

## 7. 查询记录

**Endpoint**: `POST /open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/search`
**用途**: 条件筛选、排序、分页读取记录。**是 POST**，条件放 body。频控 20 次/秒。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|---|
| `user_id_type` | query | string | 否 | `open_id` | |
| `page_size` | query | int | 否 | `20` | **最大 500** |
| `page_token` | query | string | 否 | — | |
| `view_id` | body | string | 否 | — | **filter 或 sort 非空时 view_id 被忽略**，对全表筛选 |
| `field_names` | body | string[] | 否 | 全部字段 | 只返回这些列 |
| `sort` | body | object[] | 否 | — | `[{"field_name":"日期","desc":true}]`，≤100 |
| `filter` | body | object | 否 | — | `{"conjunction":"and","conditions":[...]}`；`conjunction` 表格标"否"但文档注明实际必填 |
| `filter.conditions[]` | body | object[] | — | — | `{"field_name","operator","value":[...]}`，≤50 条 |
| `automatic_fields` | body | boolean | 否 | `false` | 是否返回创建 / 修改时间、创建人 / 修改人 |

`operator`：`is`、`isNot`、`contains`、`doesNotContain`、`isEmpty`、`isNotEmpty`、`isGreater`、`isGreaterEqual`、`isLess`、`isLessEqual`；`like`、`in` 暂未支持。
`value` **永远是字符串数组**，空值也要写 `"value": []`。

**日期筛选特殊规则**：operator 只能用 `is`、`isEmpty`、`isNotEmpty`、`isGreater`、`isLess`；value 写 `["ExactDate","1702449755000"]`（毫秒），
或 `["Today"]` 等相对日期；**ExactDate 的时间戳会被转成文档时区当天零点**，所以不能按小时筛。

```python
def search_all(app_token, table_id, conditions, field_names=None):
    url = f"{BASE}/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/search"
    body = {"filter": {"conjunction": "and", "conditions": conditions}, "automatic_fields": False}
    if field_names:
        body["field_names"] = field_names
    token = None
    while True:
        params = {"page_size": 500, "user_id_type": "open_id"}
        if token:
            params["page_token"] = token
        d = requests.post(url, params=params, json=body,
                          headers={"Authorization": f"Bearer {tenant_access_token()}"}, timeout=30).json()
        if d.get("code") != 0:
            raise RuntimeError(d)
        yield from d["data"].get("items", [])
        if not d["data"].get("has_more"):
            break
        token = d["data"]["page_token"]

rows = list(search_all(APP, TBL, [
    {"field_name": "状态", "operator": "is", "value": ["进行中"]},
    {"field_name": "日期", "operator": "isGreater", "value": ["ExactDate", "1702449755000"]},
]))
```

响应 `data`：`items[]`（`record_id`、`fields`）、`has_more`、`page_token`、`total`。

---

## 8. 按 record_id 批量获取

**Endpoint**: `POST .../records/batch_get`
body：`record_ids`（必填）、`user_id_type`（**在 body 里**，本页未写默认值 ⚠ 文档未说明）、`with_shared_url`（默认 false）、`automatic_fields`（默认 false）。
频控 20 次/秒。record_ids 数量上限 ⚠ 文档页被截断，以文档为准。

---

## 9. 附件字段

1. 调云文档「上传素材」或「分片上传素材」接口，把文件上传到**这个**多维表格，拿 `file_token`（上传接口不在本 skill 覆盖范围）。
2. 新增 / 更新记录时写 `"附件": [{"file_token": "..."}]`。
3. `file_token` **只在当前多维表格有效**，换一个多维表格要重新上传。
4. 下载：用查询记录拿到 `file_token`，调「下载素材」或「获取素材临时下载链接」；开了高级权限时要带 `extra` 查询参数，
   查询记录返回的附件 `url` / `tmp_url` 里已经带好了（需 URL 编码）。

---

## 10. 记录变更事件

**事件类型**: `drive.file.bitable_record_changed_v1`（多维表格记录变更）。另有字段变更事件 `bitable_field_changed`。
前置订阅方式（云文档事件需先对文件"订阅云文档事件"）⚠ 本 skill 未展开，以文档页为准。事件接收通用做法见 [events-callbacks.md](events-callbacks.md)。

---

## 11. 错误码

多维表格业务错误**大多是 HTTP 200 + 非 0 code**（文档表格原文，未实测）：

| code | 含义 |
|---|---|
| 1254000 / 1254001 | 请求体 JSON / 内容错误 |
| 1254002 | Fail：常见于单次改动量太大或**并发写同一个多维表格**，减量、串行 |
| 1254003 / 1254040 | app_token 错误 / 不存在（wiki 节点 token 当成 app_token 是常见原因） |
| 1254004 / 1254041 | table_id 错误 / 不存在 |
| 1254005 / 1254042 | view_id 错误 / 不存在 |
| 1254006 / 1254043 | record_id 错误 / 不存在 |
| 1254045 | 字段名不存在（与表头**完全匹配**，含空格） |
| 1254011 | page_size 非法（HTTP 400） |
| 1254016 / 1254018 / 1254024 | sort / filter / field_names 参数错误 |
| 1254030 | 响应体过大 |
| 1254036 | 多维表格复制中（HTTP 400），稍后重试 |
| 1254060–1254069、1254072 | 各类型字段值转换失败（文本、数字、单选、多选、日期、复选框、**人员（1254066：user_id_type 与传入 ID 不匹配）**、关联、超链接、附件、电话） |
| 1254100 / 1254101 | 数据表 + 仪表盘超 100 / 视图超 200 |
| 1254103 / 1254104 | 记录数超限 / 单次超 1000 条 |
| 1254107 | filter 超 2000 字符 |

无凭证探测（2026-09-11）：`POST /bitable/v1/apps/bascnFAKE/tables/tblFAKE/records/search` + 伪造 token → HTTP 400 `99991663`（鉴权先于参数校验）。

---

## 12. 容易写错的地方

1. **wiki 链接里的 token 不是 app_token**，要先换；URL `base/` 后面那段才是。
2. **tenant_access_token 要先把应用加为多维表格协作者**，不然 403/400 或查询为空。
3. 文本字段写入是字符串、读出是 `[{"type":"text","text":...}]`，回写前要转换。
4. 日期是**毫秒**；日期筛选用 `["ExactDate","<毫秒>"]` 且按天生效。
5. 人员字段 `[{"id":...}]` 的 ID 类型跟着 `user_id_type`（默认 open_id）。
6. 查询记录是 **POST /records/search**，`page_size` 最大 500，`value` 永远是数组。
7. 批量 ≤1000 条且全成全败；同一个多维表格串行写。
8. 单选 / 多选写入不存在的选项会**静默新建选项**，不会报错——拼错字会污染选项列表。
9. 字段 key 用列名，改列名会让旧代码写入 1254045。
