# 审批：模板详情、提交申请、拉取审批单、状态回调

来源：`developer.work.weixin.qq.com/document/path/91854`（概述）、`91982`（获取审批模板详情）、`91853`（提交审批申请）、
`91816`（批量获取审批单号）、`91983`（获取审批申请详情）、`91815`（审批申请状态变化回调通知）、`90240`（事件格式·审批状态通知事件）、
`90313`（错误码）。抓取于 2026-09-11。
**未用真实凭证验证**；报错与行为均为「文档原文，未实测」，标「无凭证探测（2026-09-11）」的除外。

## 目录

1. 先分清：“审批应用”接口 vs “审批流程引擎”
2. 前置配置与 token
3. 获取审批模板详情 `oa/gettemplatedetail`
4. 提交审批申请 `oa/applyevent`（含各控件 value 写法）
5. 批量获取审批单号 `oa/getapprovalinfo`
6. 获取审批申请详情 `oa/getapprovaldetail`
7. 审批状态变化回调 `sys_approval_change`
8. 错误码
9. 典型任务：代员工提报销单并跟踪结果

## 1. 先分清：“审批应用”接口 vs “审批流程引擎”

| | 审批应用接口（本文件主体） | 审批流程引擎（90269，本 skill 未展开） |
|---|---|---|
| 作用对象 | 企业微信自带的“审批”应用里的单据 | 在你的自建 / 第三方应用里挂审批流程，不影响“审批”应用 |
| 回调事件名 | **`sys_approval_change`**（91815） | **`open_approval_change`**（90240「审批状态通知事件」） |
| 单号字段 | `SpNo` / `SpNoStr` | `ThirdNo`（开发者自定义） |
| 状态字段 | `SpStatus`：1 审批中 2 已通过 3 已驳回 4 已撤销 6 通过后撤销 7 已删除 10 已支付 | `OpenSpStatus`：1 审批中 2 已通过 3 已驳回 4 已取消 |

文档原文：「“审批流程引擎”相关接口，是在“自建应用”或“第三方应用”中增加流程相关功能，使用和作用对象都为“自建应用”或“第三方应用”，不会影响企业微信“审批应用”」。
按事件名分支处理，两套字段不要混用。

## 2. 前置配置与 token

- 自建应用必须配置到「审批 → 可调用接口的应用」中，用**该自建应用的 secret** 换 token（权限表原文：「配置到「审批 - 可调用接口的应用」中」）。
- 各页注明：「从2023年12月1日0点起，不再支持通过系统应用secret调用接口，存量企业暂不受影响」。
- 91816 另写：「自建应用调用此接口，需在“管理后台-应用管理-审批-API-审批数据权限”中，授权应用允许提交审批单据」。
- ⚠ 文档自相矛盾：91816 参数表写 access_token「必须使用**审批应用**或企业内自建应用的secret获取」，与同页“2023-12-01 起不再支持系统应用 secret”冲突。新接入按后者，只用自建应用 secret。
- 申请人 / 提单者必须在应用可见范围内；未配置时报 `301055`。
- 所有审批新接口：**600 次/分钟**。

## 3. 获取审批模板详情

**Endpoint**: `POST /cgi-bin/oa/gettemplatedetail?access_token=ACCESS_TOKEN`
**用途**: 拿模板里每个控件的 `control` 类型和 `id`——提交申请时 `apply_data.contents[].id` 必须用这里的 id。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| template_id | string | 是 | 模板 id。可从审批单详情 / 回调里取，也可在管理后台模板编辑页 URL 中取；早期模板 id 是 `1910324946027731_1688852032423522_...` 这样的数字串 |

```python
tpl = wecom_call(tok, "POST", "oa/gettemplatedetail", json={"template_id": os.environ["WECOM_TPL_ID"]})
for c in tpl["template_content"]["controls"]:
    p = c["property"]
    print(p["control"], p["id"], p["title"][0]["text"], "必填" if p["require"] else "")
```

响应要点：
- `template_content.controls[].property`：`control`（Text / Textarea / Number / Money / Date / Selector / Contact / Tips / File / Table / Attendance / Vacation / Location / RelatedApproval / Formula / DateRange / BankAccount）、`id`、`title[]`（多语言）、`placeholder[]`、`require`（1 必填）、`un_print`。
- `controls[].config`：Date 的 `date.type`（day / hour）、Selector 的 `selector.type`（single / multi）与 `options[].key`（**提交时用 key，不用显示文本**）、Contact、Table 子控件、Attendance 等。
- 权限：自建应用 secret 可获取**企业自建模板**的详情；第三方应用只能获取第三方应用添加的模板。
- 无凭证探测（2026-09-11）：假 token → `{"errcode":40014,"errmsg":"invalid access_token","template_names":[]}`，路径存在。
- 错误：`301025` template_id 非法；`301026` 拉取模板失败（全局错误码表补充：「可能是审批模板未通过审核」）。

## 4. 提交审批申请

**Endpoint**: `POST /cgi-bin/oa/applyevent?access_token=ACCESS_TOKEN`
**用途**: 以某员工身份提交一张审批单。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| creator_userid | string | 是 | 申请人 userid，需在应用可见范围内 |
| template_id | string | 是 | 模板 id；**不支持**提交[打卡补卡][调班]模板 |
| use_template_approver | int | 是 | 0：接口指定审批人 / 抄送人（此时 `process` 必填）；1：用模板在后台设置的流程（流程中不能有“申请人自选”节点），支持条件审批。⚠ 文档自相矛盾：标为必填，同时写「默认为0」 |
| choose_department | int | 否 | 提单部门 id，默认主部门 |
| process.node_list[] | object[] | use_template_approver=0 时必填 | `type` 1 审批人 / 2 抄送人 / 3 办理人；`apv_rel`（type 为 1、3 时必填）1 会签 / 2 或签 / 3 依次审批；`userid[]` |
| apply_data.contents[] | object[] | 是 | `{control, id, value}`；模板必填控件必须有值 |
| summary_list[] | object[] | 是 | 最多 3 行，每行 `summary_info[{text, lang}]`；text 不超过 20 个字符；**lang 用 `zh_CN`（下划线，不是 zh-CN）** 或 `en` |

**各控件 value 写法（文档原文，注意字段名带 new_ 前缀、数值用字符串）**

| control | value |
|---|---|
| Text / Textarea | `{"text": "内容"}`（Text 不支持换行符） |
| Number | `{"new_number": "700"}` |
| Money | `{"new_money": "700"}` |
| Date | `{"date": {"type": "day", "s_timestamp": "1569859200"}}`（type 与模板一致；**s_timestamp 是字符串**） |
| Selector | `{"selector": {"type": "multi", "options": [{"key": "option-15111111111"}]}}`（key 来自模板详情） |
| Contact（成员） | `{"members": [{"userid": "WuJunJie", "name": "Jackie"}]}` |
| Contact（部门） | `{"departments": [{"openapi_id": "2", "name": "销售部"}]}` |
| Tips | 后台自动填充，无需赋值 |
| File | `{"files": [{"file_id": "<media/upload 返回的 media_id>"}]}`；全单最多 6 个附件 |
| Table | `{"children": [{"list": [<子控件 {control,id,value}>...]}]}`；**不能为空数组，至少一个子明细，且必须包含模板全部子控件** |
| DateRange | `{"date_range": {"type": "halfday", "new_begin": 1570550400, "new_end": 1570593600, "new_duration": 86400}}`；halfday 时 begin/end 只能是当天 00:00:00 或 12:00:00 的时间戳 |
| Vacation | `{"vacation": {"selector": {...假期类型...}, "attendance": {"date_range": {...}, "type": 1}}}` |
| Attendance | `{"attendance": {"date_range": {...}, "type": 3, "slice_info": {"day_items": [{"daytime": ..., "duration": ...}]}}}`；type 1 请假 / 3 出差 / 4 外出 / 5 加班；加班跨度 ≤7 天 |
| Location | `{"location": {"latitude": "30.547239", "longitude": "104.063291", "title": "...", "address": "...", "time": 1605690460}}` |
| RelatedApproval | `{"related_approval": [{"sp_no": "202011180001"}]}` |
| Formula | 后台自动计算，提交时无需填写 |

```bash
curl -s -X POST "https://qyapi.weixin.qq.com/cgi-bin/oa/applyevent?access_token=${TOKEN}" \
  -H 'Content-Type: application/json' -d @apply.json
```

```python
apply = {
    "creator_userid": "WangXiaoMing",
    "template_id": os.environ["WECOM_TPL_ID"],
    "use_template_approver": 1,                    # 用后台配置的流程，就不用传 process
    "apply_data": {"contents": [
        {"control": "Text",  "id": "Text-15111111111",  "value": {"text": "差旅报销"}},
        {"control": "Money", "id": "Money-1522222222",  "value": {"new_money": "1280.50"}},
        {"control": "Date",  "id": "Date-1533333333",   "value": {"date": {"type": "day", "s_timestamp": "1789000000"}}},
    ]},
    "summary_list": [{"summary_info": [{"text": "差旅报销 1280.50 元", "lang": "zh_CN"}]}],
}
sp_no = wecom_call(tok, "POST", "oa/applyevent", json=apply)["sp_no"]
```

（示例中的控件 id 为占位，必须替换成 `gettemplatedetail` 返回的真实 id。）

响应：`{"errcode":0,"errmsg":"ok","sp_no":"202001010001"}`
无凭证探测（2026-09-11）：假 token + 空 body → `{"errcode":40014,"errmsg":"invalid access_token"}`（token 校验先于参数校验）。

注意：
- 金额单位 ⚠ 文档未说明：`new_money` 示例为字符串 `"700"`，没写是元还是分、能否带小数。先用模板里填一笔、再用 getapprovaldetail 读回来对照。
- 错误：`301025` 参数错误（值为空 / 与模板不一致，建议对照已有单据的 `apply_data`）；`301055` 无权限或提单者不在可见范围；`301056` 审批应用已停用；`301057` 通用内部错误；`301079` 假勤时间冲突。
- 40058 排查原文：「部分接口要求参数必填（如提交审批接口，要求申请人userid必填）时，如果输入参数值为空则报此错误」。

## 5. 批量获取审批单号

**Endpoint**: `POST /cgi-bin/oa/getapprovalinfo?access_token=ACCESS_TOKEN`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| starttime | string | 是 | 提交时间范围开始，Unix 时间戳（示例为字符串 `"1569546000"`） |
| endtime | string | 是 | 结束时间戳；**必须大于 starttime，跨度不超过 31 天** |
| new_cursor | string | 是 | 分页游标，首次传空串 `""`，之后用返回的 `new_next_cursor` |
| size | int | 是 | 默认 100，**上限 100** |
| filters[] | object[] | 否 | `{key, value}`；key：template_id / creator / department / sp_status / record_type |

- filters 规则：仅“部门”支持多个；不同类型之间“与”、同类型之间“或”；record_type（1 请假 2 打卡补卡 3 出差 4 外出 5 加班 6 调班 7 会议室预定 8 退款审批 9 红包报销审批）仅支持 2021-05-31 以后提交的单。
- 自建应用只能拿到可见范围内申请人提交的单，所以「返回的sp_no_list个数可能和size不一致」——**不要用“返回数 < size”判断结束**，用游标。
- 老字段 `cursor` / `next_cursor` 待废弃。
- ⚠ 文档自相矛盾：size 说明里写「开发者需用next_cursor判断表单记录是否拉取完」，参数说明又要求改用 `new_cursor` / `new_next_cursor`；返回示例里也没有出现 `new_next_cursor`。文档表格写「当返回结果没有该字段时表示审批单已经拉取完」，以此为准。
- 错误：`301055` 无审批数据拉取权限（离职成员 userid 作为 creator 过滤也会报）；`301025` 参数错误；`301026` 内部失败；`301112` 请缩小查询时间范围。

```python
def iter_sp_nos(tok, start: int, end: int, filters=None):
    cursor = ""
    while True:
        r = wecom_call(tok, "POST", "oa/getapprovalinfo", json={
            "starttime": str(start), "endtime": str(end),
            "new_cursor": cursor, "size": 100, "filters": filters or [],
        })
        yield from r.get("sp_no_list", [])
        cursor = r.get("new_next_cursor")
        if not cursor:
            return
```

## 6. 获取审批申请详情

**Endpoint**: `POST /cgi-bin/oa/getapprovaldetail?access_token=ACCESS_TOKEN`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| sp_no | string | 是 | 审批单编号 |

响应 `info` 关键字段（文档原文）：

| 字段 | 说明 |
|---|---|
| sp_no / sp_name / template_id / apply_time | 单号 / 模板名 / 模板 id / 提交时间 |
| sp_status | 1 审批中；2 已通过；3 已驳回；4 已撤销；6 通过后撤销；7 已删除；10 已支付 |
| applyer.userid / applyer.partyid | 申请人（与 `batch_applyer` 互斥） |
| sp_record[] | 旧版节点：`sp_status`、`approverattr`（1 或签 2 会签）、`details[]{approver.userid, speech, sp_status, sptime, media_id[]}` |
| process_list.node_list[] | 新版流程：`node_type`（1 审批人 2 抄送人 3 办理人）、`sp_status`、`apv_rel`（1 会签 2 或签 3 依次）、`sub_node_list[]{userid, speech, sp_yj, sptime, media_ids}` |
| notifyer[] | 抄送人 |
| apply_data.contents[] | 与提交时同构；每个控件的 value 会带上其他控件类型的空字段（`tips`、`members`、`files`、`children`…），按 control 取对应字段 |
| comments[] | 备注，`commentUserInfo.userid`、`commenttime`、`commentcontent`、`commentid`、`media_id[]` |

- 附件 media_id 可用“获取临时素材”下载，「微盘文件无法获取」。
- 错误：`301055` / `301025` / `301026`。

## 7. 审批状态变化回调

订阅条件：自建应用配置在「审批 - 可调用接口的应用」中，并在应用“接收消息 → 设置 API 接收”里勾选“审批状态通知事件”。签名 / 解密见 `callbacks-crypto.md`。
「状态变化包括但不限于：催办、撤销、同意、驳回、转审、添加备注等情况」——**一张单会回调很多次**，不是只在终态回调。

解密后明文（节选，文档原文）：

```xml
<xml>
  <ToUserName><![CDATA[ww1cSD21f1e9c0caaa]]></ToUserName>
  <FromUserName><![CDATA[sys]]></FromUserName>
  <CreateTime>1571732272</CreateTime>
  <MsgType><![CDATA[event]]></MsgType>
  <Event><![CDATA[sys_approval_change]]></Event>
  <AgentID>3010040</AgentID>
  <ApprovalInfo>
    <SpNoStr><![CDATA[202506110001]]></SpNoStr>
    <SpNo>202506110001</SpNo>
    <SpName><![CDATA[示例模板]]></SpName>
    <SpStatus>1</SpStatus>
    <TemplateId><![CDATA[3TkaH5KFbrG9heEQWLJjhgpFwmqAFB4dLEnapaB7aaa]]></TemplateId>
    <ApplyTime>1571728713</ApplyTime>
    <Applyer><UserId><![CDATA[WuJunJie]]></UserId><Party><![CDATA[1]]></Party></Applyer>
    <StatuChangeEvent>10</StatuChangeEvent>
  </ApprovalInfo>
</xml>
```

| 字段 | 说明 |
|---|---|
| SpNoStr | 审批编号（字符串）——**推荐用它代替 SpNo** |
| SpNo | 审批编号；「局校审批单不返回此字段…不推荐使用」 |
| SpStatus | 单据状态，枚举同详情接口 |
| StatuChangeEvent | 本次变化类型：1 提单；2 同意；3 驳回；4 转审；5 催办；6 撤销；8 通过后撤销；10 添加备注；11 回退给指定审批人；12 添加审批人；13 加签并同意；14 已办理；15 已转交 |
| SpRecord / ProcessList / Notifyer / Comments | 流程、抄送、备注信息 |

处理建议：用 `SpNoStr + StatuChangeEvent + CreateTime` 做幂等；终态判断看 `SpStatus in (2, 3, 4, 6, 7, 10)`；需要完整表单数据时再调 `getapprovaldetail`。

## 8. 错误码

| errcode | 说明（文档原文） |
|---|---|
| 301025 | 审批开放接口参数错误：值为空或 null；提交的数据格式与模板不一致；template_id 非法 |
| 301026 | 拉取审批模板 / 批量拉取 / 拉取详情内部接口失败；全局表：可能是审批模板未通过审核 |
| 301055 | 无审批应用权限 / 无审批数据拉取权限；自建应用需配置到审批“可调用接口的应用”；离职成员 userid 不支持作为过滤条件；参数无法解析 |
| 301056 | 审批应用已停用 |
| 301057 | 提交审批单内部接口失败 |
| 301079 | 审批单假勤时间有冲突 |
| 301112 | 请缩小查询时间范围重试 |
| 45009 | 频率超限（本组接口 600 次/分钟） |

## 9. 典型任务：代员工提报销单并跟踪结果

1. 管理后台把自建应用加到「审批 → 可调用接口的应用」，应用可见范围覆盖申请人；应用开启 API 接收并勾选“审批状态通知事件”。
2. `gettemplatedetail` 取控件 id / 类型 / 选项 key，缓存下来（模板改版后控件 id 会变，定期刷新）。
3. 按控件类型组装 `apply_data`（注意 `new_money` / `new_number` / `s_timestamp` 字符串写法、Table 至少一行），`use_template_approver=1` 走后台流程。
4. `applyevent` 拿到 `sp_no` 落库。
5. 回调里按 `Event == "sys_approval_change"` 分支，用 `SpNoStr` 匹配本地单据，按 `SpStatus` 更新状态；漏回调时用 `getapprovalinfo`（≤31 天窗口）+ `getapprovaldetail` 补偿对账。
