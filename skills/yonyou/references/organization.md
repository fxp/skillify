# 组织：业务单元与部门

> 来源：open.yonyoucloud.com API 文档「用友 YonBIP → 应用平台 → 数字化建模 → 组织管理」（业务单元 `ucf-org-center.org_center_card`、
> 部门 `ucf-org-center.bd_admindepttree1`），经 `/iuap-ipaas-base/openPortal/api/getByVersionForTest/<apiId>/running` 公开 JSON 抓取于 2026-09-11。
> 字段表、示例、报错全部是**文档原文，未实测**。调用方式（网关域名、access_token）见 `auth-and-gateway.md`。
> 下文 `{gw}` = 数据中心查询得到的 `gatewayUrl`。

## 目录

1. 选哪个接口
2. 业务单元列表（树）查询
3. 业务单元详情查询
4. 业务单元保存（新增 / 修改）
5. 部门树查询
6. 部门条件查询（平铺）
7. 部门详情查询
8. 组织 / 部门变更事件
9. 本文件的 ⚠ 汇总

---

## 1. 选哪个接口

| 我要… | 用 | 说明 |
| --- | --- | --- |
| 拉全部业务单元及层级 | `POST /yonbip/digitalModel/orgunit/querytree` | 返回树（`children` 嵌套），可按 `pubts` 增量 |
| 看一个业务单元的全部职能（财务/采购/销售/库存…） | `GET /yonbip/digitalModel/orgunit/detail?id=` | 返回 `financeOrg`、`assetsOrg`、`factoryOrg` 等职能对象 |
| 新建 / 修改业务单元 | `POST /yonbip/digitalModel/orgunit/save` | `data` 包一层，`_status` 必填 |
| 某组织下的部门树 | `POST /yonbip/digitalModel/admindept/tree` | 请求体包在 `externalData` 里，`enable` 必填且是数组 |
| 按编码 / 时间戳平铺查部门 | `POST /yonbip/digitalModel/basedoc/dept/list` | 请求体包在 `data` 里，`code`、`pubts` 都是数组 |
| 一个部门的详情 | `GET /yonbip/digitalModel/admindept/detail?id=` | |

同分类下还有「组织部门全量查询」「业务单元 / 部门批量查询」「组织职能信息查询」「部门保存 / 批量保存 / 启停 / 删除」等接口，
本 skill 未逐一整理，文档在 open.yonyoucloud.com →「API 文档」→ 用友 YonBIP → 数字化建模 → 组织管理。

**三个请求体外壳互不相同**（`querytree` 顶层字段、`admindept/tree` 用 `externalData`、`dept/list` 与 `orgunit/save` 用 `data`），
照抄对应接口，不要统一成一种。

---

## 2. 业务单元列表（树）查询

**Endpoint**: `POST /yonbip/digitalModel/orgunit/querytree`
**用途**: 取租户下业务单元树；文档名「业务单元列表查询」，但返回的是带 `children` 的树。

**关键参数**（Body，全部选填）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| code | string | 否 | 组织编码 |
| name | string | 否 | 组织名称 |
| enable | string | 否 | 状态：`0` 未启用、`1` 启用、`2` 停用 |
| pubts | string | 否 | 时间戳，查询**大于**该时间的数据，如 `"2023-10-10 00:00:00"` |

**示例请求**

```bash
curl -sS -X POST "$YONBIP_GATEWAY_URL/yonbip/digitalModel/orgunit/querytree?access_token=$TOKEN_ENC" \
  -H 'Content-Type: application/json' -d '{"enable":"1"}'
```

```python
orgs = api.call("POST", "/yonbip/digitalModel/orgunit/querytree", body={"enable": "1"})["data"]
def walk(nodes, depth=0):
    for n in nodes:
        yield depth, n["id"], n["code"], n["name"]
        yield from walk(n.get("children") or [], depth + 1)
```

**示例响应**（关键字段）

```json
{"code": "200", "message": "操作成功",
 "data": [{"id": "1511040517705984", "code": "yontest", "name": "…", "level": 1, "parent": "", "dr": 0,
           "pubts": "2020-08-29 03:39:14",
           "children": [{"id": "1511042233094400", "parent": "1511040517705984", "code": "bj_cczx",
                         "orgtype": 1, "level": 2, "children": []}]}]}
```

**注意事项**

- `orgtype`：`1` 组织、`2` 部门（本接口返回说明）。`dr`：`0` 未删、`1` 已删——增量同步时要处理 `dr=1`。
- ⚠ 文档未说明：是否分页、单次最多返回多少节点。
- 错误示例（文档原文）：`{"code": 999, "message": "操作失败", "displayCode": "XXX-XXX-XXXXXX", "level": 0, "data": null}`——
  这里 `code` 是**数字** 999，而成功示例是字符串 `"200"`。按字符串比较前先 `str()`。

---

## 3. 业务单元详情查询

**Endpoint**: `GET /yonbip/digitalModel/orgunit/detail?id=<业务单元ID>`

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | query | 是 | 业务单元 ID |

```python
unit = api.call("GET", "/yonbip/digitalModel/orgunit/detail", query={"id": "1791386861752549384"})["data"]
```

返回（关键字段）：`id`、`code`、`name`（多语言对象 `{"zh_CN": …}`）、`shortname`、`parent`、`enable`（0/1/2）、
`orgtype`、`taxpayerid`（统一社会信用代码）、`taxpayertype`（1 一般纳税人 / 2 小规模）、`exchangerate`（汇率类型 ID）、
`pubts`，以及各职能对象 `assetsOrg`、`factoryOrg` 等（其中 `finorgid` 为关联核算主体）。

**注意事项**

- ⚠ 文档自相矛盾：本接口返回表把 `orgtype` 标为 boolean（说明却写「2-部门，1-组织」），`querytree` 标为 long `1/2`，
  `orgunit/save` 的入参是 boolean（true 表示部门类组织）、出参说明又写「1 为部门，0 为非部门」。读写时都做兼容。
- 多语言字段在这里是 `{"zh_CN": …}` 形式；客户、物料接口用的是 `simplifiedName` 形式（见 `master-data.md`），不要混用。

---

## 4. 业务单元保存（新增 / 修改）

**Endpoint**: `POST /yonbip/digitalModel/orgunit/save`
**用途**: 新增或修改一个业务单元及其职能。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data | object | 是 | 业务单元 `[org.func.BaseOrg]` |
| data._status | string | **是** | `Insert` 新增 / `Update` 修改 |
| data.code | string | **是** | 编码 |
| data.id | string | 修改时必填 | 新增不填 |
| data.name / shortname | object | 否 | 多语言 `{"zh_CN","en_US","zh_TW"}` |
| data.parent | string | 否 | 上级业务单元 ID |
| data.orgtype | boolean | 否 | true 表示部门类组织 |
| data.enable | int | 否 | 0 未启用 / 1 启用 / 2 停用 |
| data.taxpayerid / taxpayername / taxpayertype | string | 否 | 统一社会信用代码 / 纳税人名称 / 1 一般 2 小规模 |
| data.financeOrg / fundsOrg / salesOrg / purchaseOrg / inventoryOrg / factoryOrg / assetsOrg / taxpayerOrg / adminOrg | object | 否 | 各职能设置 |
| externalData.typelist | string[] | 否 | 职能类型列表，如 `adminorg`、`salesorg`、`purchaseorg`… |

**示例请求**

```python
body = {"data": {"_status": "Insert", "code": "BJ01",
                 "name": {"zh_CN": "北京分公司"}, "shortname": {"zh_CN": "北京"},
                 "parent": parent_id, "orgtype": False, "enable": 1},
        "externalData": {"typelist": ["salesorg", "purchaseorg"]}}
api.call("POST", "/yonbip/digitalModel/orgunit/save", body=body)
```

**注意事项**

- 文档的请求示例 URL 是 `/0000L6YQ8AVLFUZPXD0000/yonbip/digitalModel/orgunit/save`（路径前多了一段租户 ID 样的前缀）。
  ⚠ 文档自相矛盾：接口地址是 `/yonbip/digitalModel/orgunit/save`，示例里的前缀未作说明，按接口地址调用。未探测该前缀。
- 该接口幂等配置为 `non`（非 MDD 幂等），重试前先按 `code` 查一次避免重复建。
- 返回示例的 `code`、`message` 都是空字符串（文档原文），⚠ 成功判定只能参照通用约定 `code == "200"`。

---

## 5. 部门树查询

**Endpoint**: `POST /yonbip/digitalModel/admindept/tree`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| externalData | object | **是** | 外壳 |
| externalData.enable | string[] | **是** | 启用状态数组：`"0"` 未启用、`"1"` 启用、`"2"` 停用 |
| externalData.parentorgid | string | 二选一 | 行政组织 ID（与 `parentorgcode` 不能同时为空） |
| externalData.parentorgcode | string | 二选一 | 行政组织编码 |
| externalData.pubts | string | 否 | 查询大于该时间戳的数据 |

```python
depts = api.call("POST", "/yonbip/digitalModel/admindept/tree",
                 body={"externalData": {"parentorgcode": "yontest", "enable": ["1"]}})["data"]
```

返回每个节点：`id`、`code`、`name`、`parent`、`parent_code`、`parentorgid`（所属业务单元）、`orgtype`（2 部门）、
`is_biz_unit`、`isEnd`（是否末级）、`enable`、`principal`（负责人）、`pubts`、`children`。

**注意事项**

- `enable` 是**数组**，文档示例给的是 `[""]`（空串元素）。⚠ 文档未说明传空串的效果；要全部状态就显式传 `["0","1","2"]`。
- ⚠ 文档自相矛盾：`isEnd` 在本接口写「1 是末级，0 否」，在部门详情写「0 是，1 否」。

---

## 6. 部门条件查询（平铺）

**Endpoint**: `POST /yonbip/digitalModel/basedoc/dept/list`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data | object | **是** | 外壳 |
| data.code | string[] | 否 | 部门编码数组 |
| data.pubts | string[] | 否 | 时间戳数组，查**大于等于**该时间的数据 |

多个条件是 and 关系（文档示例三）。

```bash
curl -sS -X POST "$YONBIP_GATEWAY_URL/yonbip/digitalModel/basedoc/dept/list?access_token=$TOKEN_ENC" \
  -H 'Content-Type: application/json' -d '{"data":{"pubts":["2021-01-07 15:33:14"]}}'
```

返回 `data[]`：`id`、`code`、`name`、`parentid`、`parentCode`、`parentorgid`、`orgtype`、`enable`（0 初始化 / 1 启用 / 2 停用）、
`dr`、`tenantid`、`pubts`；另有顶层 `displayCode`（业务异常码）、`level`（0 错误 / 1 警告）。

**注意事项**

- 这里 `pubts` 是「大于等于」，`querytree` / `admindept/tree` 写的是「大于」——做增量水位时注意边界重复或遗漏。
- 成功示例的 `code` 是数字 `200`。

---

## 7. 部门详情查询

**Endpoint**: `GET /yonbip/digitalModel/admindept/detail?id=<部门ID>`

返回 `id`、`code`、`name`（多语言 `{"zh_CN","en_US","zh_TW"}`）、`parent`、`parent_code`、`parentorgid`、`depttype`（部门性质）、
`principal`、`branchleader`、`enable`、`is_biz_unit`、`orgtype`、`path`、`effectivedate`、`creationtime` 等。

**注意事项**

- 文档请求示例是 `/yonsuite/digitalModel//admindept/detail?access_token=**&id=**`（`/yonsuite` 前缀加双斜杠）。
  ⚠ 文档自相矛盾：接口地址是 `/yonbip/digitalModel/admindept/detail`。同类 `/yonsuite/` 前缀在凭证期间查询接口上已被探测证实不存在
  （见 `gl-voucher.md` §6），这里按 `/yonbip/` 调用。
- ⚠ 文档自相矛盾：返回表里混有 `pageIndex`、`pageSize`、`recordCount` 等分页字段并标为必有，与「详情」语义不符。

---

## 8. 组织 / 部门变更事件

来自事件文档（`/iuap-ipaas-base/openPortal/event/listEvent/domainApp/…`），订阅与解密见 `events.md`：

| 对象 | 事件编码 | 含义 |
| --- | --- | --- |
| 业务单元 | `BASE_ORG_EVENT_ADD_AFTER` / `_UPDATE_AFTER` / `_DELETE_AFTER` / `_ENABLE_AFTER` / `_DISABLE_AFTER` | 新增 / 修改 / 删除 / 启用 / 停用后 |
| 部门 | `DEPT_ADD` / `DEPT_UPDATE` / `DEPT_DELETE` / `DEPT_ENABLE` / `DEPT_DISABLE` | 同上 |

`DEPT_ADD` 事件内容示例（文档原文）的外层是 `{"model": {"id","code","name","multiLangName","parentid","parentorgid","enable","dr","ts",…}}`；
而 corp-demo README 描述的老格式是 `{"type":"DEPT_ADD","deptId":[…]}`。⚠ 文档自相矛盾，解密后按实际字段兼容。

推荐做法：事件只当「有变化」的信号，收到后按 ID 调 §3 / §7 详情接口取最新数据，再配合 `pubts` 定时增量兜底。

---

## 9. 本文件的 ⚠ 汇总

- ⚠ 文档自相矛盾：`orgtype` 类型与取值在 querytree / detail / save 三处不一致——§3
- ⚠ 文档自相矛盾：`orgunit/save` 示例 URL 带未说明的租户前缀——§4
- ⚠ 文档自相矛盾：`isEnd` 含义在部门树与部门详情相反——§5
- ⚠ 文档自相矛盾：部门详情示例用 `/yonsuite/…//admindept/detail`；返回表混入分页字段——§7
- ⚠ 文档自相矛盾：`DEPT_ADD` 事件体 `model` 结构 vs README 的 `deptId[]` 结构——§8
- ⚠ 文档未说明：querytree 是否分页；`enable:[""]` 的效果；`orgunit/save` 成功时 code 取值——§2 §4 §5
