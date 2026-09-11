# 组织与岗位：组织单元、职位、职务及其基础数据

来源：open.italent.cn 文档中心 › 新版接口 v3.0 › 组织员工 › 组织单元 / 职位 / 职务 / 职级 / 职等 / 职务序列（接口文档经
`https://open.italent.cn/api/OpenDocument/Get?id=…&platform=1` 抓取），社区文档「常见对接案例(组织员工)」。抓取于 2026-09-11。
**未用真实凭证验证**；报错与行为均为「文档原文，未实测」。鉴权与响应外壳见 `auth-and-conventions.md`。

Base URL：`https://openapi.italent.cn`，路径前缀 `/TenantBaseExternal/api/v5/`，全部 `POST` + JSON，
请求头 `Authorization: Bearer <access_token>`。

## 目录

1. 先懂三个概念：时间轴、OId、多维度上级
2. 时间窗滚动查询（组织员工所有 `GetByTimeWindow` 通用）
3. 组织单元：时间窗 / 按 OId / 按 Code / 下级列表
4. 职位与职务：时间窗
5. 其他基础数据（职级、职等、职务序列……）只列入口
6. 写接口只列入口

---

## 1. 三个概念

- **时间轴**。组织、职位、职务都有 `startDate` / `stopDate`（生效 / 失效日期），同一个 OId 在不同时间段可以有不同记录。
  文档原文（按 OId 查组织）：「组织有时间轴概念，默认查询当天的记录。如测试组织在2020-01-01至2020-12-31期间启用，在2021-01-01至9999-12-31期间停用，
  则今天（2021-04-01）查询的是停用的记录。」`isCurrentRecord` 表示是否当前生效。永久有效的记录 `stopDate` 是 `9999-12-31T00:00:00`。
- **OId**。组织单元 `oId` 是 int；**根组织 OId = 900 + 租户ID**（如 `900100000`），「默认组织OId为0」（下级组织接口提示原文）。
  职位 `oId` 是 GUID 字符串，职务 `oId` 是数字字符串（如 `"63167"`）——三者类型都不同，别用一个 int 字段存。
- **多维度上级**。组织有 `pOIdOrgAdmin`（行政维度上级 OId）、`pOIdOrgReserve2`（业务维度上级）、`pOIdOrgReserve3`（产品维度）。
  建组织树用 `pOIdOrgAdmin`。文档响应示例里 `pOIdOrgReserve2` 为 `-2`，`-2` 的含义 ⚠ 文档未说明（推测为“无”，未证实）。
- 状态 `status`：`0` 停用、`1` 启用（组织文档原文）。默认只返回**未删除、启用**的数据，要停用的传 `withDisabled: true`，要已删除的传 `isWithDeleted: true`。

## 2. 时间窗滚动查询（通用规则）

组织员工下所有「根据时间窗滚动查询变动的 XX 信息」接口（组织、职位、职务、职级、员工……）共用同一套参数与约束，文档原文要点：

| 规则 | 文档原文 / 说明 |
|---|---|
| 时间范围 | `startTime` / `stopTime` 必填，格式 `2021-01-01T00:00:00`；「不传递时分秒，则时分秒默认为 00:00:00」 |
| 90 天 | 警告写「建议限定查询范围在90天」，但异常示例是 `{"data":null,"code":"417","message":"只支持查询90天范围内的数据，请分段查询"}` ⚠ 文档自相矛盾（“建议” vs 报错）——**按硬限制处理，超过就分段** |
| 每批条数 | `capacity` 默认 100；「每批次数据量必须小于等于300」 |
| scrollId | 第一次传 `""`，之后传上次响应的 `scrollId`；「两次滚动查询接口调用间隔不能超出10秒，超出间隔后，查不到下批次数据。故必须通过while循环查出全部数据后再处理具体业务」；不能跳页、不能回跳 |
| 结束条件 | 「isLastData字段已废弃，推荐通过result.Data为空或空集合判断是否获取完毕」 |
| 查询类型 | `timeWindowQueryType`：`1` 修改时间（ModifiedTime，系统修改也会更新）、`2` 业务修改时间（BusinessModifiedTime，系统修改不更新）。增量同步业务变化用 `2` |
| 自定义字段过滤 | `extQueries: [{fieldName, queryType, values, includeLowerValue, includeUpperValue}]`，多条件只支持 and；`queryType`：1 大于、2 大于等于、3 小于、4 小于等于、5 等于、6 不等于、7 区间；等于 / 不等于最多 300 个值 |
| 查询列 | `columns`：「该参数仅表示是否查询该列的值，不控制响应模型的字段」——不选的列仍会出现在响应里，只是值为 null |
| 排序 | `sort`：`{"字段编码": 1}`，0 不排序、1 升序、2 降序；组织的 `OrderAdmin` / `OrderCode` 需「开通排序规则后才支持排序」，名称等分词字段不支持排序 |
| 新建数据 | 「创建后未修改过的数据，也可通过此接口查询（创建时，修改时间=业务修改时间=创建时间）」 |

⚠ 文档自相矛盾：`timeWindowQueryType` / `queryType` 在 schema 里是字符串枚举（`ModifiedTime`、`Equal`…），但字段说明和所有请求示例都用数字
（`"timeWindowQueryType":1`、`"queryType":5`）。**按示例传数字**；职位 / 职务文档还写成了「示例：[1]」（数组），应为单个值。

⚠ 文档未说明：`startTime` / `stopTime` 的时区（无时区后缀）。

**通用滚动循环（Python）**——把「边拉边处理」改成「先拉完再处理」，避免处理耗时超过 10 秒导致 scrollId 过期：

```python
from datetime import datetime, timedelta

def scroll_all(client, path, base_args, start, stop, window_days=90):
    """按 ≤90 天切片，每片用 scrollId 拉完。client.post 见 auth-and-conventions.md。"""
    rows, cur = [], start
    while cur < stop:
        seg_end = min(cur + timedelta(days=window_days), stop)
        scroll_id = ""
        while True:
            body = client.post(path, {**base_args,
                                      "startTime": cur.strftime("%Y-%m-%dT%H:%M:%S"),
                                      "stopTime": seg_end.strftime("%Y-%m-%dT%H:%M:%S"),
                                      "scrollId": scroll_id, "capacity": 300})
            batch = body.get("data") or []
            if not batch:          # 不用 isLastData（已废弃）
                break
            rows.extend(batch)     # 只收集，不在循环里做慢操作
            scroll_id = body.get("scrollId") or ""
        cur = seg_end
    return rows
```

## 3. 组织单元

### 时间窗查询变动的组织单元
**Endpoint**: `POST /TenantBaseExternal/api/v5/Organization/GetByTimeWindow`
**用途**: 全量 / 增量拉组织。「获取一段时间内发生变化的组织单元的最新数据」。限流 50 次/秒、1500 次/分钟（每企业）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `startTime` / `stopTime` | date-time | 是 | — | 见第 2 节 |
| `timeWindowQueryType` | 数字（见上） | 是 | — | 1 修改时间 / 2 业务修改时间 |
| `scrollId` | string | 是 | — | 首次 `""` |
| `capacity` | int | 否 | 100 | ≤300 |
| `withDisabled` | bool | 否 | false | 是否包含停用组织 |
| `isOnlyGetCurrent` | bool | 否 | false | 是否仅获取当前生效的组织 |
| `isWithDeleted` | bool | 否 | false | 是否包括已删除 |
| `columns` / `sort` / `extQueries` | | 否 | | 见第 2 节 |
| `enableTranslate` | bool | — | — | **已下线**，不要传（见 `employees.md` 翻译一节） |

```bash
curl -sS -X POST 'https://openapi.italent.cn/TenantBaseExternal/api/v5/Organization/GetByTimeWindow' \
  -H "Authorization: Bearer ${BEISEN_TOKEN}" -H 'Content-Type: application/json' \
  -d '{"timeWindowQueryType":2,"startTime":"2026-06-15T00:00:00","stopTime":"2026-09-11T00:00:00",
       "scrollId":"","capacity":300,"withDisabled":true,"columns":["Name","OId","Code","POIdOrgAdmin","Status","StartDate","StopDate"]}'
```

```python
orgs = scroll_all(client, "/TenantBaseExternal/api/v5/Organization/GetByTimeWindow",
                  {"timeWindowQueryType": 2, "withDisabled": True}, start, stop)
```

**示例响应**（文档原文，节选）

```json
{"scrollId": "DXF1ZXJ5QW5k…", "isLastData": true, "total": 96,
 "data": [{"name": "111Lfhahahha", "code": "rrrLF11", "oId": 1143532, "level": "5d0ed9c5-…",
           "status": 1, "startDate": "2020-01-01T00:00:00", "stopDate": "9999-12-31T00:00:00",
           "pOIdOrgAdmin": 389173, "pOIdOrgReserve2": -2, "isCurrentRecord": true,
           "personInCharge": null, "businessModifiedBy": 112862191}]}
```

**关键响应字段**：`name`（及 `name_en_US`、`name_zh_TW`）、`shortName`、`code`（组织编码）、`oId`、`level`（组织层级实体 GUID）、
`status`、`establishDate`、`startDate`、`stopDate`、`changeDate`、`pOIdOrgAdmin`、`pOIdOrgReserve2`、`pOIdOrgReserve3`、`isCurrentRecord`、
`personInCharge`（负责人 UserID）、`hRBP`、`shopOwner`、`administrativeAssistant`、`personInChargeDeputy`（**逗号分隔的字符串**，如 `"101500177,101500178"`）、
`costCenterOIdV2`、`businessModifiedBy` / `businessModifiedTime`。

**注意事项**
- 默认排序：「若排序参数为空，则默认按照行政维度顺序号(OrderAdmin)升序」。
- 返回的是每个组织**最新**数据；要历史时间段的版本，用下面按 OId / Code 查询并传日期。
- 组织名称里的特殊符号可能被转码（文档引用了「特殊符号被转码转译」参考文档，正文未抓取，⚠ 文档未说明细节）。

### 按 OId 批量取组织
**Endpoint**: `POST /TenantBaseExternal/api/v5/Organization/GetByIds`
**用途**: 已知组织 OId，取组织信息（含薪酬成本中心 `costCenterOId`）。限流 50/秒、1500/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `oIds` | int[] | 是 | 组织 OId，**≤300 个**，「OIds所有元素必须为大于等于0的整数」 |
| `isWithDeleted` | bool | 否 | 包含已删除时「可能会有同一个OId有一条未删除的、一条已删除的情况」 |
| `columns` | string[] | 否 | 默认 null = 全部 |

```json
{"oIds": [4745240, 4745241], "isWithDeleted": false, "columns": null}
```

注意：**没有日期参数，按“今天”取时间轴上的记录**（见第 1 节原文）。

### 按组织编码取组织（可指定时间点）
**Endpoint**: `POST /TenantBaseExternal/api/v5/Organization/GetOrganizationInfoByCodes`
**用途**: 用组织 `code`（你们系统里通常对得上的那个编码）取组织，可指定生效时间点。限流 50/秒、1300/分钟。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `codes` | string[] | 是 | 组织 Code 集合（数量上限 ⚠ 文档未说明） |
| `activeDate` | date-time | 否 | 组织生效时间点；空 = 当前日期；「必须大于等于1900-01-01T00:00:00」 |
| `columns` / `isWithDeleted` | | 否 | 同上 |

异常示例（文档原文）：`{"data":null,"code":"417","message":"时间节点必须大于1900-01-01T00:00:00"}`。
文档请求示例里 `"activeDate":null` 后缺逗号（示例 JSON 本身不合法），照抄会解析失败。

### 取某组织的下级组织
**Endpoint**: `POST /TenantBaseExternal/api/v5/Organization/GetSubOrganizations`
**用途**: 已知组织，取其下级组织列表（可多层）。限流 30/秒、1300/分钟。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `oId` | int | 是 | — | 「默认组织OId为0，根组织OId为900+租户ID，如：900100000」 |
| `level` | int | 否 | 20 | 查询层级，「默认组织查询20层」 |
| `isWithSelf` | bool | 否 | false | 是否包含自身 |
| `isWithDisable` | bool | 否 | false | 是否包含停用组织（**注意拼写：这里是 `isWithDisable`，时间窗接口是 `withDisabled`**） |
| `queryDate` | date-time | 否 | 今天 | 时间轴日期 |
| `isWithDeleted` / `columns` / `sort` | | 否 | | |

```python
tree = client.post("/TenantBaseExternal/api/v5/Organization/GetSubOrganizations",
                   {"oId": 900000000 + int(os.environ["BEISEN_TENANT_ID"]), "level": 20,
                    "isWithSelf": True, "isWithDisable": False})["data"]
```

「若对应的组织单元不存在，则进行错误提示」；异常示例 `{"data":null,"code":"417","message":"OId必须大于等于0"}`。
另有「批量查询指定组织的下级组织树分支」`POST /TenantBaseExternal/api/v5/Organization/GetSubOrganizationTrees`，本 skill 未整理字段。

## 4. 职位与职务

北森区分**职务**（JobPost，如“产品经理”，全公司通用的岗位类别）和**职位**（JobPosition，挂在某个组织下的具体岗位，引用职务）。
职位响应里 `oIdJobPost` 指向职务、`oIdOrganization` 指向所属组织。

### 时间窗查询变动的职位
**Endpoint**: `POST /TenantBaseExternal/api/v5/Position/GetByTimeWindow`
**用途**: 全量 / 增量拉职位。限流 50/秒、**1000/分钟**。

请求参数同第 2 节（`startTime`、`stopTime`、`timeWindowQueryType` 必填，`withDisabled`、`scrollId`、`capacity`、`sort`、`extQueries`、`isWithDeleted`、`columns`）。
默认「未删除、启用」，默认排序「按照组织名称升序」。

关键响应字段：`name`、`code`、`oId`（**GUID 字符串**）、`status`、`startDate`、`stopDate`、`oIdJobPost`（职务 OId，数字字符串）、
`oIdJobGrade`、`oIdJobLevelType`、`oIdProfessionalLine`、`oIdJobSequence`、`oIdOrganization`（int）、`oIdJobLevel`（最低职级）、`highestOIdJobLevel`（最高职级）、
`description`、`place`（地点字典键，如 `"1100"` 北京市）、`positionKey`、`positionSecret`。

⚠ 文档自相矛盾：职位 / 职务的时间窗文档把 `isLastData` 写成正常字段（没有标“已废弃”），组织 / 员工文档标了已废弃。统一用 `data` 为空判断结束。

### 时间窗查询变动的职务
**Endpoint**: `POST /TenantBaseExternal/api/v5/JobPost/GetByTimeWindow`
**用途**: 全量 / 增量拉职务。限流 50/秒、1500/分钟。参数同上。

关键响应字段：`name`、`oId`（数字字符串）、`code`、`status`、`startDate`、`stopDate`、`oIdResourceSet`、`oIdJobGradeLow` / `oIdJobGradeHigh`、
`oIdJobSequence`、`oIdJobLevel` / `highestOIdJobLevel`、`oIdJobLevelType`、`oIdProfessionalLine`、`oIdTalentCriterion`、`order`、`score`。

按 OId 取：`POST /TenantBaseExternal/api/v5/Position/GetByOIds`（职位）、`POST /TenantBaseExternal/api/v5/JobPost/GetByOIds`（职务），本 skill 未整理字段表。

## 5. 其他基础数据：只列入口（均为 POST，时间窗规则同第 2 节）

| 对象 | 时间窗接口 | 其他 |
|---|---|---|
| 职级 | `/TenantBaseExternal/api/v5/JobLevel/GetByTimeWindow` | Create、Update |
| 职级类别 | `/TenantBaseExternal/api/v5/JobLevelType/GetByTimeWindow` | |
| 职等 | `/TenantBaseExternal/api/v5/JobGrade/GetByTimeWindow` | |
| 职务序列 | `/TenantBaseExternal/api/v5/JobSequence/GetByTimeWindow` | Create、Update |
| 职层 | `/TenantBaseExternal/api/v5/JobLayer/GetByTimeWindow` | |
| 组织类型 / 组织层级 | `/OrganizationType/GetByTimeWindow`、`/OrganizationLevel/GetByTimeWindow` | 按名称查、Create/Update/Enable/Disable/Delete |
| 多维度组织 | `/MultOrg/GetMultOrgByTimeWindow` | `GetMultOrgInfoByCodes`、Batch* |
| 组织编制 | `/OrganizationEstablishment/GetEstablishment` 等 | `VerifyEstablishmentNumber`（任职超编校验） |
| 法人公司 | `/Corporation/GetByTimeWindow` | 按名称 / 编码查 |

字段表请查 open.italent.cn 文档中心对应条目（本地渲染副本在 `beisen-workspace/pages/open/组织员工/`）。

## 6. 写接口只列入口

组织单元：`Organization/Create`、`Update`、`Change`（变更）、`Enable`、`Disable`、`RevokeChange`（撤销变更）；
职位：`Position/Create`、`Update`、`Change`、`BatchUpdate`、`Enable`、`Disable`、`BatchDelete`（DELETE）；
职务：`JobPost/Create`、`Update`、`Enable`、`Disable`、`BatchDelete`（DELETE）。

本 skill 未逐一整理这些写接口的字段表（避免照抄出错）。共性规则（见 `employee-lifecycle.md`）：可以用 `originalId` / `XXXOriginalId` 引用第三方系统 ID；
「OriginalId」映射改错了用 `SourceIdMapping/UpdateOriginalIdByTargetId` 修；组织变更类接口涉及时间轴，传生效日期而不是直接覆盖。

社区文档「常见对接案例(组织员工)」给了三方系统主数据同步到北森的三种主键方案（原文）：
方案一「使用北森组织Oid和北森员工UserId做主键对接」；方案二「使用OriginalId（即：三方系统主键【UUID】）做主键对接」；
方案三「使用组织Code和员工工号/邮箱做主键对接」。各方案的详细步骤在子页面，未抓取。
