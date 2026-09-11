# 返回结构、报错与排错

> 来源：open.kingdee.com「API文档」各操作的「返回结果」模板（API 版本 7.5.1800.6，抓取于 2026-09-11）；
> 官方 Python SDK 8.2.0 源码；对旧公网网关 `api.kingdee.com/galaxyapi` 的无凭证探测（2026-09-11，见 `auth-and-connection.md` 第 9 节）。
> **业务层结构是文档原文，未实测；网关层是无凭证探测所得；SDK 行为来自源码阅读。**

## 目录

1. 一次调用可能在哪几层失败
2. 网关层（HTTP 519 + errcode）
3. SDK 层（RuntimeError / 返回异常对象）
4. 业务层：Result.ResponseStatus
5. 各接口返回模板汇总
6. 批量操作：用 DIndex 对应失败项
7. 异步任务状态
8. 没有文档化的错误码表
9. 推荐的统一检查函数
10. 排错清单

---

## 1. 一次调用可能在哪几层失败

```
你的代码
  └─ SDK（初始化检查、HTTP 状态检查、response_error 前缀检查）
       └─ 金蝶网关 / 反向代理（公有云场景；HTTP 519 + errcode）
            └─ 星空应用服务器（HTTP 200，body 里 Result.ResponseStatus.IsSuccess=false）
```

三层的错误结构完全不同，**只判 HTTP 状态码或只判 IsSuccess 都会漏**。

## 2. 网关层（无凭证探测，2026-09-11）

| HTTP | body | 含义（响应里的 description_cn） |
| --- | --- | --- |
| 519 | `{"errcode":5001,"description":"API not found[GW]","description_cn":"请求的API不存在[网关]"}` | 路径不存在 |
| 519 | `{"errcode":4002,"description":"Unauthorized, APP_ID is empty[GW]","description_cn":"认证失败, 应用ID为空[网关]"}` | 没有应用 ID |
| 519 | `{"errcode":4006,"description":"Unauthorized, errDescEn: X-Api-TimeStamp is invalid: <ts>[GW]","description_cn":"认证失败, errDescCn: X-Api-TimeStamp过期: <ts>[网关]"}` | 时间戳过期 |

- 状态码 **519 是非标准码**，很多 HTTP 客户端 / 重试中间件不会把它当成 4xx 鉴权错误处理。
- 响应头带 `X-Api-Requestid`（UUID），报障时附上。
- 只探测到这三个 errcode；完整的网关错误码表 ⚠ 文档未说明。客户私有部署直连星空时可能根本不经过这层网关。
- SDK 遇到非 200/206 会 `raise RuntimeError(res.text)`，所以用 SDK 时看到的是异常信息里的这段 JSON。

## 3. SDK 层（SDK 8.2.0 源码）

| 情况 | SDK 行为 |
| --- | --- |
| 构造 / InitConfig 时 ServerUrl 为空 | `raise RuntimeError('ServerUrl is required')` |
| 配置文件路径不存在 | `raise RuntimeError('Init config failed: Config file[...] not found!')` |
| 授权四项（账套ID、用户、应用ID、应用密钥）有空值 | 只 `print('SDK初始化失败，缺少必填授权项：...')`，不抛异常 |
| 未成功初始化就调接口 | `Execute()` **return** `RuntimeError('拒绝请求，请先正确初始化!')`——返回的是异常对象，不是抛出 |
| HTTP 状态不是 200 / 206 | `raise RuntimeError(响应文本)` |
| 响应文本以 `response_error:` 开头 | `raise RuntimeError(...)` |

- **「返回异常对象」是 SDK 的坑**：`json.loads(sdk.Save(...))` 会报 `TypeError: the JSON object must be str...`，看起来像是数据问题。
  调用前确认 `sdk.initialize is True`，或者对返回值做 `isinstance(raw, Exception)` 检查。
- SDK 用 `response_content.rstrip('response_error:')` 取错误信息——`rstrip` 删除的是**尾部**属于该字符集合的字符，不是去掉前缀，
  所以异常信息开头仍是 `response_error:`，且结尾可能被截掉几个字母（源码阅读结论，未实测）。需要完整报错时自己记录原始响应文本。
- `response_error:` 后面跟的内容格式 ⚠ 文档未说明。

## 4. 业务层：Result.ResponseStatus（文档原文，未实测）

Save / Submit / Audit / UnAudit / Delete / ExcuteOperation / Allocate / GroupSave 等「写」操作的返回模板：

```json
{
  "Result": {
    "ResponseStatus": {
      "ErrorCode": "",
      "IsSuccess": "false",
      "Errors": [{"FieldName": "", "Message": "", "DIndex": 0}],
      "SuccessEntitys": [{"Id": "", "Number": "", "DIndex": 0}],
      "SuccessMessages": [{"FieldName": "", "Message": "", "DIndex": 0}],
      "MsgCode": ""
    },
    "Id": "",
    "Number": "",
    "NeedReturnData": [{}]
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `Result.ResponseStatus.IsSuccess` | 是否成功。**模板里是字符串 `"false"`**，实际可能是布尔也可能是字符串 ⚠，统一 `str(x).lower() == "true"` |
| `Errors[]` | 失败明细：`FieldName`（出错字段 key）、`Message`（中文说明）、`DIndex`（数据包下标） |
| `SuccessEntitys[]` | 成功的单据：`Id`（内码）、`Number`（编码）、`DIndex`。拼写就是 `Entitys`，不是 `Entities` |
| `SuccessMessages[]` | 成功时的提示信息 |
| `ErrorCode` / `MsgCode` | 错误码 / 消息码，取值 ⚠ 文档未说明 |
| `Result.Id` / `Result.Number` | 仅 Save / Draft 模板里有，单条保存的内码与编码 |
| `Result.NeedReturnData` | Save / Draft / BatchSave：`NeedReturnFields` 指定字段的返回值 |

- **业务失败时 HTTP 状态码是多少 ⚠ 文档未说明**（SDK 把 200/206 都当正常响应处理）。判断成败只看 `IsSuccess`。
- 结构是 `Result.ResponseStatus`（两层），不要写成顶层 `ResponseStatus` 或 `result.status`。

## 5. 各接口返回模板汇总（文档原文）

| 接口 | 返回模板要点 |
| --- | --- |
| Save / Draft | `Result.ResponseStatus{...}` + `Result.Id` + `Result.Number` + `Result.NeedReturnData` |
| BatchSave | `Result.ResponseStatus{...}` + `Result.NeedReturnData` |
| Submit / Audit / UnAudit / Delete / ExcuteOperation / Allocate | `Result.ResponseStatus{...}` |
| GroupSave | `Result.ResponseStatus{...}` + `Result.Id`（新分组内码） |
| View | `{"Result":{"ResponseStatus":{"IsSuccess":"false"},"Result":"{}"}}`——数据在 `Result.Result` |
| ExecuteBillQuery | `[["FValue1","FValue2",...],...]`——**纯二维数组，没有 Result 外壳**；失败时结构 ⚠ 文档未说明 |
| QueryBusinessInfo / QueryGroupInfo | `{"Result":{"ResponseStatus":"","NeedReturnData":"{}"}`（模板括号不配对，⚠ 文档自相矛盾） |
| WorkflowAudit | `{"Result":{"ResponseStatus":"","OperationResults":"{}"}`（同样括号不配对） |
| Push | `Result.ResponseStatus{...}`；备注另提到 `ConvertResponseStatus`（单据转换结果），模板里没有 ⚠ |
| ValidateUser | `{"Message":"！","MessageCode":"","LoginResultType":0,"Context":null,"FormId":null}`；`LoginResultType` 枚举 ⚠ 文档未说明 |

## 6. 批量操作：用 DIndex 对应失败项

BatchSave、以及一次传多个 `Numbers` / `Ids` 的 Submit / Audit / Delete：
- 整体 `IsSuccess` 与部分成功的关系 ⚠ 文档未说明（可能部分成功部分失败）。
- **逐条以 `DIndex` 回查原始数据**：`Errors[i].DIndex` 指向 Model 数组（或 Numbers 数组）里的下标。
- 成功的那部分已经落库，重试时只重发失败的 DIndex，避免重复创建。

```python
def split_batch(res, payloads):
    st = res["Result"]["ResponseStatus"]
    failed = {e.get("DIndex"): e for e in (st.get("Errors") or [])}
    ok = {s.get("DIndex"): s for s in (st.get("SuccessEntitys") or [])}
    return ([(payloads[i], ok[i]) for i in sorted(k for k in ok if k is not None)],
            [(payloads[i], failed[i]) for i in sorted(k for k in failed if k is not None)])
```

## 7. 异步任务状态（SDK `BatchSaveQuery` 源码）

| `Status` | 含义（SDK 枚举 `QueryState`） |
| --- | --- |
| 0 | Pending |
| 1 | Running |
| 2 | Complete（此时读 `Result`） |

轮询接口 `...DynamicFormService.QueryAsyncResult`，body `{"queryInfo": "<JSON 字符串：{\"TaskId\":..,\"Cancelled\":false}>"}`；
SDK 每次间隔 1 秒，异常时最多重试 5 次。协议细节见 [`bill-operations.md`](bill-operations.md) 第 5 节。⚠ 2020 版文档未收录。

## 8. 没有文档化的错误码表

抓到的官方材料里**没有**：`ErrorCode` / `MsgCode` 的取值表、`Errors[].Message` 的枚举、限流（QPS）规则、单次请求条数上限。
只能以 `Errors[].FieldName + Message` 的原文判断。**不要写 `switch(ErrorCode)` 的分支逻辑**，把整段 `ResponseStatus` 写日志。
文档里唯一给出具体值的是：ExecuteBillQuery `Limit` 不能超过 2000；WorkflowAudit `ApprovalType` 1 通过 / 2 驳回 / 3 终止。

## 9. 推荐的统一检查函数

```python
import json

class KingdeeError(RuntimeError):
    pass

def kd_check(raw, step=""):
    """适用于 Save/Submit/Audit/Delete/View 等返回 Result.ResponseStatus 的接口（不适用于 ExecuteBillQuery）"""
    if isinstance(raw, Exception):                      # SDK 未初始化时返回异常对象
        raise KingdeeError(f"{step}: SDK 未初始化: {raw}")
    res = json.loads(raw) if isinstance(raw, str) else raw
    if isinstance(res, dict) and "errcode" in res:      # 网关层（通常已被 SDK 作为异常抛出）
        raise KingdeeError(f"{step}: 网关 {res['errcode']} {res.get('description_cn')}")
    st = (res.get("Result") or {}).get("ResponseStatus") if isinstance(res, dict) else None
    if isinstance(st, dict) and str(st.get("IsSuccess")).lower() != "true":
        errs = st.get("Errors") or []
        detail = "; ".join(f"[{e.get('DIndex')}] {e.get('FieldName')}: {e.get('Message')}" for e in errs)
        raise KingdeeError(f"{step}: {detail or json.dumps(st, ensure_ascii=False)}")
    return res

def kd_rows(raw, step=""):
    """ExecuteBillQuery 专用：返回二维数组；遇到疑似错误包就抛出（错误包结构 ⚠ 文档未说明）"""
    if isinstance(raw, Exception):
        raise KingdeeError(f"{step}: SDK 未初始化: {raw}")
    rows = json.loads(raw)
    if isinstance(rows, dict) or (rows and isinstance(rows[0], list) and rows[0] and isinstance(rows[0][0], dict)):
        raise KingdeeError(f"{step}: 查询返回的不是数据行: {json.dumps(rows, ensure_ascii=False)[:500]}")
    return rows
```

## 10. 排错清单

| 现象 | 先查 |
| --- | --- |
| HTTP 519 | 网关层，看 errcode（§2）；公有云地址 / 鉴权头 / 时间戳 |
| `json.loads` 报 TypeError | SDK 未初始化返回了异常对象（§3） |
| `IsSuccess` 为 false，`Errors[].FieldName` 是某个基础资料字段 | 引用的编码在当前组织不存在 / 未审核 / 未分配（⚠ 推断）；检查 `{"FNumber": ...}` 的键名大小写是否与模板一致 |
| 修改单据后分录少了 | `IsDeleteEntry` 默认 true（见 bill-operations.md §4） |
| ExecuteBillQuery 返回空数组 | FormId 拼写 / 大小写、FilterString 语法、使用组织过滤（均 ⚠ 文档未说明） |
| 查询只拿到 2000 行 | `Limit` 上限 2000，按 StartRow 翻页 |
| 提交 / 审核报参数错误 | `Numbers` 要数组、`Ids` 要逗号分隔字符串 |
| ExcuteOperation 接口 404 或找不到 | 拼写是 `ExcuteOperation`（没有 e）；opNumber 大小写照抄 |
