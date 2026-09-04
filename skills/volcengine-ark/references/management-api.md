# 火山方舟管控面 API（`ark.cn-beijing.volcengineapi.com`）

本文件覆盖**管控面 API**：用火山引擎 Access Key / Secret Key 签名调用的资源管理接口（`?Action=<Action>&Version=2024-01-01`），重点是 Agent Plan / Coding Plan 套餐与席位管理、用量查询、临时 API Key、基础模型与限流查询。模型推理（数据面 `/api/v3`、`/api/coding`、`/api/plan`）不在本文件，见同目录其他 reference。

## 目录
1. [鉴权与请求形态](#1-鉴权与请求形态)
2. [Agent Plan / Coding Plan 管理 Action 全表](#2-agent-plan--coding-plan-管理-action-全表)
   - 2.1 选型速查 · 2.2 个人版（8 个 Action）· 2.3 企业版（12 个 Action）· 2.4 AFP 额度 / 用量字段含义
3. [查询用量](#3-查询用量)
4. [管理 API Key：临时 API Key](#4-管理-api-key临时-api-key)
5. [基础模型与限流查询](#5-基础模型与限流查询)
6. [开通管理](#6-开通管理)
7. [其他管控面分组索引](#7-其他管控面分组索引)
8. [来源页面](#来源页面)

## 1. 鉴权与请求形态

| 要素 | 值 |
|---|---|
| Base URL | `https://ark.cn-beijing.volcengineapi.com/` |
| 请求 | `POST https://ark.cn-beijing.volcengineapi.com/?Action=<Action>&Version=2024-01-01`，`Content-Type: application/json`，参数全部放 JSON body（PascalCase） |
| 鉴权 | **仅支持 Access Key 签名**（HMAC-SHA256）。所有本文 Action 页面均写明"本接口仅支持 Access Key 鉴权"，方舟 API Key（`Bearer`）不能用 |
| 签名要素 | Service `ark`，Region `cn-beijing`；签名头 `Authorization: HMAC-SHA256 Credential=<AK>/<yyyyMMdd>/cn-beijing/ark/request, SignedHeaders=host;x-content-sha256;x-date, Signature=<sig>`，另需 `Host`、`X-Date`（如 `20240710T042925Z`）、`X-Content-Sha256`（body 的 SHA256） |
| AK/SK 获取 | 控制台 Access Key 管理 `https://console.volcengine.com/iam/keymanage`。文档建议不要用主账号 AK，改用授予方舟权限的 IAM 子用户 AK（`使用 IAM 管理权限` https://www.volcengine.com/docs/82379/1263493） |
| 响应信封 | 业务字段在 `Result` 内（续费个人版套餐页原文：成功时 HTTP 200，`Result` 为空对象 `{}`）。顶层其他信封字段（如 `ResponseMetadata`）⚠ 文档未说明 |
| 签名算法全文 | https://www.volcengine.com/docs/6369/67269（文档明确说"自行实现签名实现成本高，不推荐"） |

**推荐：用官方 SDK，不要手写签名。** 文档指向 SDK 接入指南 `https://api.volcengine.com/api-sdk/view?serviceCode=ark&version=2024-01-01&language=Java`（切换 language 参数可看 Python / Go 等）。Python 包为 `volcengine-python-sdk`（`pip install volcengine-python-sdk`），方舟管控面模块 `volcenginesdkark`，公共配置 `volcenginesdkcore`。⚠ 文档未说明：Go / Java 模块名、以及 2026 年新增的 Plan 相关 Action 在各语言 SDK 中的方法名——本文输入页面只给了指南链接，未列 SDK 方法；下面骨架里的方法名请以 SDK 指南为准。

### 通用调用骨架

curl（签名头用占位符；真实值需按签名算法计算，或用 SDK）：
```bash
curl -X POST 'https://ark.cn-beijing.volcengineapi.com/?Action=GetPersonalPlan&Version=2024-01-01' \
  -H 'Content-Type: application/json' \
  -H 'Host: ark.cn-beijing.volcengineapi.com' \
  -H 'X-Date: 20260903T042925Z' \
  -H 'X-Content-Sha256: <sha256(body)>' \
  -H 'Authorization: HMAC-SHA256 Credential=<AK>/20260903/cn-beijing/ark/request, SignedHeaders=host;x-content-sha256;x-date, Signature=<sig>' \
  -d '{"Plan":"AgentPlan"}'
```

Python（`volcengine-python-sdk`；AK/SK 从环境变量读，绝不硬编码）：
```python
import os
import volcenginesdkcore
import volcenginesdkark

cfg = volcenginesdkcore.Configuration()
cfg.ak = os.environ["VOLC_ACCESSKEY"]
cfg.sk = os.environ["VOLC_SECRETKEY"]
cfg.region = "cn-beijing"
volcenginesdkcore.Configuration.set_default(cfg)

# 已在本机核实（2026-09-04，volcengine-python-sdk 5.0.48）：volcenginesdkark.ARKApi 只有 17 个方法
# （create/get/list/delete/stop_endpoint、get_endpoint_certificate、create/list_batch_inference_jobs、
#   模型精调 6 个、create_evaluation_job、get_api_key），**没有** get_personal_plan / get_afp_usage /
#   list_model_rate_limit 这类 Plan、用量、限流 Action 的封装。写 api.get_afp_usage(...) 会 AttributeError。
# 这些 Action 要走通用签名调用 UniversalApi（同一 SDK 自带），Action 名和 body 照文档原样传：
client = volcenginesdkcore.ApiClient(cfg)
universal = volcenginesdkcore.UniversalApi(client)
info = volcenginesdkcore.UniversalInfo(method="POST", service="ark", version="2024-01-01",
                                       action="GetPersonalPlan", content_type="application/json")
resp = universal.do_call(info, {"Plan": "AgentPlan"})
print(resp)  # 返回 dict；响应字段见各 Action 小节。ARKApi 里已有封装的 Action（如 ListEndpoints、GetApiKey）也可以直接用 api.<snake_case>()。
```

后文各 Action 只给 **body JSON** 与响应关键字段，套进上面骨架即可（curl 的 `-d`，或 SDK 的 `<Action>Request` 参数）。

## 2. Agent Plan / Coding Plan 管理 Action 全表

### 2.1 选型速查：我想…

| 我想… | 个人版 | 企业版（席位制） |
|---|---|---|
| 买套餐 | `CreatePersonalPlan` | `CreateTeamSeats` |
| 续费 | `RenewPersonalPlan` | `RenewTeamSeats` |
| 查套餐状态 / 到期时间 | `GetPersonalPlan` | `ListSeatInfos` |
| 开 / 关自动续费 | 只能在创建时传 `AutoRenew` ⚠ 文档未说明个人版后续修改方式 | `UpdateSeatAutoRenew` |
| 把席位分给子用户 | — | `AssignTeamSeats` |
| **拿到 Agent Plan 专属 API Key（程序化）** | `RegeneratePersonalApiKey`（只返回 `Status`，**不返回明文 Key** ⚠ 见注意事项） | `GetTeamSeatApiKey`（返回明文 `APIKey`）、`ListSeatInfos`（`Data.ApiKey`） |
| 轮换 Key | `RegeneratePersonalApiKey` | `RegenerateTeamSeatApiKeys` |
| 查 AFP 额度（5h / 日 / 周 / 月） | `GetAFPUsage` | `GetSeatAFPUsage`（按 ID）、`ListSeatAFPUsage`（分页 / 排序） |
| 查按模型 / 按小时的调用明细 | `GetUsageDetails` | `GetSeatUsageDetails` |
| Coding Plan 席位额度用量 | — | `ListSeatInfoUsages`（批量）、`GetSeatInfoUsage`（单个） |
| 套餐内能用哪些模型 | `ListArkAgentPlanModel` / `ListArkCodingPlanModel` | 同左（`Edition=enterprise`） |

商品名（`Plan` 参数）四选一：`AgentPlan`、`CodingPlan`（个人版）；`AgentPlanTeam`、`CodingPlanTeam`（企业版）。档位（`PlanType`）：Agent Plan `Small`/`Medium`/`Large`/`Max`，Coding Plan `Lite`/`Pro`。

**程序化获取 Agent Plan 专属 Key 的途径**：个人版控制台创建的专属 Key 只能在 Agent Plan 控制台看；管控面里能返回 Key 明文的只有企业版的 `GetTeamSeatApiKey`（需 `ArkFullAccess` 权限）和 `ListSeatInfos` 的 `Data.ApiKey`。个人版 `RegeneratePersonalApiKey` 的响应字段只有 `Status`/`Message`，轮换后新 Key 如何取回 ⚠ 文档未说明（推测仍需控制台）。

下单类 Action（Create/Renew）共性：**异步下单、自动从云账户余额扣费**，下单后要用查询接口反查结果；都支持 `DryRun=true` 只校验不下单；`PricingCycle` 目前只有 `Month`；`Duration` 范围 `[1, 12]`。

### 2.2 个人版

#### 创建个人版套餐 — `CreatePersonalPlan`
**Endpoint**: `POST /?Action=CreatePersonalPlan&Version=2024-01-01`
**用途**: 购买 Agent Plan / Coding Plan 个人版；一次只能买一个 `PlanType`。
**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| AgreementAccepted | boolean | 是 | — | **2026-08-26 起新增必填**，只能传 `true`；缺失则"无法下单并返回参数缺失错误"（文档原文，未实测） |
| Plan | string | 是 | — | `AgentPlan` / `CodingPlan` |
| PlanType | string | 是 | — | AgentPlan: `Small` `Medium` `Large` `Max`；CodingPlan: `Lite` `Pro` |
| Duration | number | 是 | — | `[1, 12]`，单位由 PricingCycle 决定 |
| PricingCycle | string | 是 | — | 仅 `Month` |
| AutoRenew | boolean | 否 | false | 到期前自动从余额续费，"仅支持单次自动续费" |
| DryRun | boolean | 否 | false | 只做参数 / 额度校验，不扣款 |

**示例 body**
```json
{"AgreementAccepted": true, "Plan": "AgentPlan", "PlanType": "Medium", "Duration": 1, "PricingCycle": "Month", "AutoRenew": false, "DryRun": true}
```
**示例响应** `Result`: `{"PlanType": "Medium"}`
**注意事项**
- 同账号同档位同一时间只能有一个有效订阅，重复下单返回 `OperationDenied` 类错误（文档原文，未实测）。
- 异步下单，调用后用 `GetPersonalPlan` 反查最终结果。
- 调用即视为同意《火山引擎数据授权协议》《方舟平台专用条款》《Harness 能力说明和产品专用条款》等。

#### 续费个人版套餐 — `RenewPersonalPlan`
**Endpoint**: `POST /?Action=RenewPersonalPlan&Version=2024-01-01`
**用途**: 给已购个人版续期；与 Create 的区别是不传 `PlanType`/`AutoRenew`。
**关键参数**: `AgreementAccepted`(boolean, 必填, 只能 `true`, 2026-08-26 起) · `Plan`(必填, `AgentPlan`/`CodingPlan`) · `Duration`(必填, `[1,12]`) · `PricingCycle`(必填, `Month`) · `DryRun`(默认 false)
**示例 body**: `{"AgreementAccepted": true, "Plan": "CodingPlan", "Duration": 3, "PricingCycle": "Month"}`
**示例响应**: HTTP 200，`Result` 为 `{}`（无特有字段）。
**注意事项**: 异步执行、自动扣费；用 `GetPersonalPlan` 反查 `EndTime` 是否延长。

#### 查询个人版套餐 — `GetPersonalPlan`
**Endpoint**: `POST /?Action=GetPersonalPlan&Version=2024-01-01`
**用途**: 查当前账号某商品的个人版套餐（档位、状态、起止时间、自动续费）。
**关键参数**: `Plan`(string, 必填, `AgentPlan`/`CodingPlan`)
**示例 body**: `{"Plan": "AgentPlan"}`
**示例响应** `Result`: `{"PlanType": "Medium", "Status": "Running", "AutoRenew": false, "StartTime": "2026-08-01T00:00:00+08:00", "EndTime": "2026-09-01T00:00:00+08:00"}`
| 字段 | 说明 |
|---|---|
| PlanType | AgentPlan: `Small`/`Medium`/`Large`/`Max`；CodingPlan: `Lite`/`Pro` |
| Status | `Running` 生效中 / `Expired` 已过期 |
| StartTime / EndTime | ISO 8601（上面示例值为格式示意，非文档原值） |
| AutoRenew | 是否开启到期自动续费 |
**注意事项**: 未购买或已回收时返回 `ResourceNotFound.Plan` 错误（文档原文，未实测）。

#### 查询 Agent Plan 支持的模型列表 — `ListArkAgentPlanModel`
**Endpoint**: `POST /?Action=ListArkAgentPlanModel&Version=2024-01-01`
**用途**: 拿 Agent Plan 套餐内可调用的模型清单（用于前端展示 / 校验 model 名）。
**关键参数**: `Edition`(string, 可选, `personal` / `enterprise`；不传或传未识别值时返回"公共模型列表")
**示例 body**: `{"Edition": "personal"}`
**示例响应** `Result`: `{"Datas": [{"ModelID": "..."}]}` — 只有 `Datas[].ModelID` 一个字段。
**注意事项**: ⚠ 文档未说明 `ModelID` 返回的是 Plan 入口用的小写 Model Name（如 `doubao-seed-2.1-turbo`）还是标准入口的带日期 Model ID；Coding Plan 同类接口给的例子是 `doubao-seed-1.6`（小写 Model Name 形态），推测 Agent Plan 相同，待实测。不返回上下文长度、能力标签等元数据——那些要走第 5 节 `GetFoundationModelVersion`。

#### 查询 Coding Plan 支持的模型列表 — `ListArkCodingPlanModel`
**Endpoint**: `POST /?Action=ListArkCodingPlanModel&Version=2024-01-01`
**用途**: Coding Plan 当前可选模型列表；无请求参数（不区分个人 / 企业版）。
**示例 body**: `{}`
**示例响应** `Result`: `{"Datas": [{"ModelID": "doubao-seed-1.6"}]}`（文档示例值），`ModelID` 即调用时填 `model` 的值。

#### 获取套餐 AFP 额度 — `GetAFPUsage`
**Endpoint**: `POST /?Action=GetAFPUsage&Version=2024-01-01`
**用途**: 个人版 Agent Plan 的 AFP 额度 / 已用量，四个滚动窗口。企业版席位改用 `GetSeatAFPUsage`。无请求参数。
**示例 body**: `{}`
**示例响应** `Result`（字段含义见 2.4）
```json
{"PlanType": "Medium",
 "AFPFiveHour": {"Quota": "…", "Used": "…", "SubscribeTime": 1756800000000, "ResetTime": 1756818000000},
 "AFPDaily": {…}, "AFPWeekly": {…}, "AFPMonthly": {…}}
```
**注意事项**: `Quota`/`Used` 是 **string** 类型（单位 AFP），时间戳是 **epoch 毫秒**。Coding Plan 个人版没有对应的 AFP 查询 Action ⚠ 文档未说明 Coding Plan 个人版额度如何程序化查询。

#### 获取套餐用量详情 — `GetUsageDetails`
**Endpoint**: `POST /?Action=GetUsageDetails&Version=2024-01-01`
**用途**: 个人版 Agent Plan 按天 / 按小时、按模型聚合的调用用量明细（token / 图片数），区分套餐内 / 套餐外。企业版改用 `GetSeatUsageDetails`。
**关键参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| QueryInterval | string | 是 | `Day` / `Hour` |
| Filter.StartTime / Filter.EndTime | string | 是（Filter 本身可选，但传了就必填） | `YYYY-MM-DD` |
| Filter.ObjectName | string[] | 否 | 模型 / Harness 名称列表 |
| Filter.PlanType | **integer[]** | 否 | `1`=Small `2`=Medium `3`=Large `4`=Max（注意企业版同名参数是 string） |

**示例 body**
```json
{"QueryInterval": "Day", "Filter": {"StartTime": "2026-08-01", "EndTime": "2026-08-31", "PlanType": [2]}}
```
**示例响应** `Result.Details[]`: `{"Time": 1756656000000, "ObjectName": "doubao-seed-2.1-turbo", "BillingType": "WithinPlan", "Unit": "Tokens", "Usage": 123456}`
| 字段 | 说明 |
|---|---|
| BillingType | `WithinPlan` 套餐内 / `OutsideOfPlan` 套餐外（超额后付费部分） |
| ObjectName | 发生消耗的模型或 Harness 名称 |
| Unit / Usage | `Tokens`、`Images` 等；Usage 是整数 |
| Time | epoch 毫秒 |

#### 轮换个人版 API Key — `RegeneratePersonalApiKey`
**Endpoint**: `POST /?Action=RegeneratePersonalApiKey&Version=2024-01-01`
**用途**: 轮换个人版 Agent Plan 专属 Key；旧 Key 立即失效。
**关键参数**: `Plan`(string, 必填, 可选值仅 `AgentPlan`) · `ProjectName`(string, 可选, Key 所属项目空间)
**示例 body**: `{"Plan": "AgentPlan"}`
**示例响应** `Result`: `{"Status": "Success", "Message": ""}`；`Status` 为 `Failed` 时 `Message` 给原因，原 Key 仍有效。
**注意事项**
- **不可逆**；`Status=Success` 即旧 Key 失效，业务侧要先准备好切换。
- ⚠ 响应里**没有新 Key 明文**，新 Key 如何取回文档未说明（推测控制台 Agent Plan 页查看）。这与企业版 `GetTeamSeatApiKey` 能直接拿明文不同。
- `Plan` 只接受 `AgentPlan`：Coding Plan 用的是方舟 API Key（与标准 API 共用），不走这个接口。

### 2.3 企业版

企业版以**席位（Seat）**为单位：先 `CreateTeamSeats` 买席位 → `AssignTeamSeats` 绑到子用户 → `GetTeamSeatApiKey` 取 Key → 用 `ListSeatInfos` / `*AFPUsage` / `*UsageDetails` 监控。所有企业版 Action 都有 `ProjectName`（默认 `default`），资源不在默认项目时必须传。

#### 创建企业版席位 — `CreateTeamSeats`
**Endpoint**: `POST /?Action=CreateTeamSeats&Version=2024-01-01`
**用途**: 管理员批量买席位；一次可同时下多个档位（`Seats` 数组，每档位一项）。
**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| Plan | string | 是 | — | `AgentPlanTeam` / `CodingPlanTeam` |
| Seats[] | object[] | 是 | — | AgentPlanTeam 最多 4 项（Small/Medium/Large/Max 各一），CodingPlanTeam 最多 2 项（Lite/Pro）；`PlanType` 重复返回 `Duplicated.PlanType` 错误（文档原文，未实测） |
| Seats[].PlanType | string | 是 | — | 档位 |
| Seats[].SeatNumber | number | 是 | — | ≥1；**企业版首次购买要求：账号下 `Active` 席位数 + 本次新购总数 ≥ 5** |
| Seats[].Duration | number | 是 | — | `[1, 12]` |
| Seats[].PricingCycle | string | 是 | — | `Month` |
| Seats[].AutoRenew | boolean | 否 | false | 仅支持单次自动续费 |
| DryRun | boolean | 否 | — | 只校验，不占席位不扣款 |
| ProjectName | string | 否 | default | 不存在的项目返回 `NotFound.ProjectName`（文档原文，未实测） |

**示例 body**
```json
{"Plan": "AgentPlanTeam", "ProjectName": "default", "DryRun": false, "Seats": [{"PlanType": "Medium", "SeatNumber": 5, "Duration": 1, "PricingCycle": "Month", "AutoRenew": true}]}
```
**示例响应** `Result`: `{"Seats": [{"PlanType": "Medium", "SeatIds": ["<seat-id>", "…"]}]}` — `SeatIds` 长度等于 `SeatNumber`，是后续绑定 / 续费 / 取 Key 的入参。
**注意事项**: 幂等性由调用方保障，"请勿使用相同参数并发请求"；异步执行，用 `ListSeatInfos` 反查。**注意 Agreement**：企业版页面没有 `AgreementAccepted` 参数（个人版有），调用即视为同意《企业版产品和服务专用条款》等。

#### 续费企业版席位 — `RenewTeamSeats`
**Endpoint**: `POST /?Action=RenewTeamSeats&Version=2024-01-01`
**用途**: 按席位 ID 分组续费，不同组可不同时长。
**关键参数**: `Plan`(必填, `AgentPlanTeam`/`CodingPlanTeam`) · `Seats[]`(必填, 非空；每项 `SeatIds` string[] 必填非空、`Duration` `[1,12]` 必填、`PricingCycle` `Month` 必填) · `DryRun`(默认 false) · `ProjectName`(默认 default)
**示例 body**
```json
{"Plan": "AgentPlanTeam", "Seats": [{"SeatIds": ["<seat-a>", "<seat-b>"], "Duration": 3, "PricingCycle": "Month"},
                              {"SeatIds": ["<seat-c>"], "Duration": 1, "PricingCycle": "Month"}]}
```
**示例响应** `Result`: `{"SeatIds": ["<seat-a>", "<seat-b>", "<seat-c>"]}`（所有已续费席位汇总）。
**注意事项**: 异步、自动扣费。

#### 批量绑定企业版席位 — `AssignTeamSeats`
**Endpoint**: `POST /?Action=AssignTeamSeats&Version=2024-01-01`
**用途**: 把席位绑到 IAM 子用户。**部分成功语义**。
**关键参数**: `Data[]`(必填；每项 `SeatId`、`UserId`、`UserName` 三个 string 均必填) · `ProjectName`(默认 default)
**示例 body**: `{"Data": [{"SeatId": "<seat-a>", "UserId": "<sub-user-id>", "UserName": "alice"}]}`
**示例响应** `Result`: `{"SuccessIds": ["<seat-a>"], "FailedResult": [{"SeatId": "<seat-b>", "Message": "…"}]}`
**注意事项**: 已绑定其他用户的席位**不会被覆盖**，进 `FailedResult`。注意字段名是单数 `FailedResult`（其他部分成功接口是 `FailedResults`）。⚠ 文档未说明如何解绑 / 换绑（本次输入页面无 Unassign 类 Action）。

#### 获取企业版席位 API Key — `GetTeamSeatApiKey`
**Endpoint**: `POST /?Action=GetTeamSeatApiKey&Version=2024-01-01`
**用途**: **返回席位 API Key 明文**——程序化拿 Agent Plan（企业版）专属 Key 的正规途径。
**关键参数**: `SeatId`(string, 必填)
**示例 body**: `{"SeatId": "<seat-a>"}`
**示例响应** `Result`: `{"APIKey": "…"}`（注意大小写 `APIKey`）
**注意事项**: 仅限具备 `ArkFullAccess` 权限的身份调用；文档反复强调只在可信环境调用、妥善保管。拿到的 Key 用于 `/api/plan[/v3]`（Agent Plan）或 `/api/coding[/v3]`（Coding Plan）数据面，不要打到 `/api/v3`。

#### 批量更新（轮换）企业版席位 API Key — `RegenerateTeamSeatApiKeys`
**Endpoint**: `POST /?Action=RegenerateTeamSeatApiKeys&Version=2024-01-01`
**用途**: 批量轮换席位 Key，旧 Key 立即失效。部分成功语义。
**关键参数**: `Plan`(必填, `AgentPlanTeam`/`CodingPlanTeam`) · `SeatIds`(string[], 必填) · `ProjectName`(可选)
**示例 body**: `{"Plan": "AgentPlanTeam", "SeatIds": ["<seat-a>", "<seat-b>"]}`
**示例响应** `Result`: `{"SuccessIds": ["<seat-a>"], "FailedResults": [{"SeatId": "<seat-b>", "Message": "…"}]}`
**注意事项**: 不可逆；响应**不含新 Key 明文**，轮换后再调 `GetTeamSeatApiKey` 逐个取。

#### 查询席位基本信息列表 — `ListSeatInfos`
**Endpoint**: `POST /?Action=ListSeatInfos&Version=2024-01-01`
**用途**: 账号下所有席位的基础信息（状态、到期、绑定用户、限流、**ApiKey**），分页 + 筛选 + 排序；是拿 `SeatID` 的入口。
**关键参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| Filter | object | 是 | 可为空对象，但字段必须存在 |
| Filter.BillingStatus | integer[] | 否 | `1` pending 已下单未付费 / `2` running 已激活 / `3` expired / `4` reclaimed 已回收 |
| Filter.SeatStatus | integer | 否 | `1` Idle 未绑定 APIKey / `2` Active 已绑定 |
| Filter.BizInfo | string | 否 | 文档只列 `Lite` / `Pro` ⚠ 见注意事项 |
| Filter.SeatIDs | string[] | 否 | 最多 1000 |
| Filter.UserID / Filter.UserName | string | 否 | 绑定子用户 |
| PageNum / PageSize | integer | 否 | 页码从 1 起（注意此接口叫 `PageNum`，其他接口叫 `PageNumber`） |
| SortBy / SortOrder | string | 否 | 如 `OrderTimestamp`；`Asc` / `Desc` |
| ProjectName | string | 否 | 默认 default |

**示例 body**: `{"Filter": {"BillingStatus": [2], "SeatStatus": 2}, "PageNum": 1, "PageSize": 50, "SortBy": "OrderTimestamp", "SortOrder": "Desc"}`
**示例响应** `Result`（关键字段）
```json
{"Total": 12, "BizSummaries": [{"BizInfo": "Pro", "TotalCount": 10, "ActiveCount": 8}],
 "Data": [{"SeatID": "…", "AccountID": "…", "ProjectName": "default", "BizInfo": "Pro", "BillingStatus": 2, "SeatStatus": "2", "InstanceID": "…",
           "OrderTime": 1756800000, "ExpiredTime": 1759392000, "AutoRenew": true, "SubscribeMilestones": "…",
           "IdentityType": "SubUser", "IdentityId": "…", "IdentityDetail": "alice", "BindCount": 1, "ApiKeySID": "…", "ApiKey": "…",
           "RateLimit": {"RPM": 0, "TPM": 0, "TokenWindow": [{"DurationSeconds": 18000, "Token": 0}]},
           "ExtraConfig": {"ArkCodeLatestMappingModelID": "…"}, "CreateTime": 1756800000, "UpdateTime": "2026-09-01T00:00:00Z", "Version": 1}]}
```
| 字段 | 说明 |
|---|---|
| Data[].ApiKey / ApiKeySID | 席位绑定的 APIKey 密钥明文 / 其唯一标识（轮换用）——第二条拿 Key 的途径 |
| Data[].RateLimit | 席位限流：RPM、TPM、`TokenWindow[]`（窗口秒数 + 窗口 token 上限） |
| Data[].ExtraConfig.ArkCodeLatestMappingModelID | 别名 `ark-code-latest` 当前映射到的具体模型 ID |
| OrderTime / ExpiredTime / CreateTime | Unix **秒**（与 AFP 接口的毫秒不同）；UpdateTime 是 ISO 8601 |
| SubscribeMilestones | 席位资源刷新时间节点（string） |
**注意事项**
- ⚠ 文档自相矛盾：`BizInfo` 枚举只写了 `Lite`/`Pro`（Coding Plan 档位），但 `CreateTeamSeats` 页明确让用 `ListSeatInfos` 反查 **AgentPlanTeam** 席位；Agent Plan 席位的 `BizInfo` 取值（`Small`…`Max`？）文档未说明，待实测。
- 响应 `SeatStatus` 标注类型 `string` 但枚举是 `1`/`2`，请求侧是 integer；解析时按字符串兼容。

#### 查询席位 AFP 额度用量列表 — `ListSeatAFPUsage`
**Endpoint**: `POST /?Action=ListSeatAFPUsage&Version=2024-01-01`
**用途**: 企业版 Agent Plan 席位 AFP 用量**分页列表**，可按 5h / 周 / 月用量排序（找"谁用得最多"）。
**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| ProjectName | string | **是** | — | 此接口 ProjectName 必填 |
| Filter.PlanType | string[] | 否 | — | `Small`/`Medium`/`Large`/`Max` |
| Filter.SeatIDs / Filter.UserNames | string[] | 否 | — | 各最多 1000；多个条件 AND |
| PageNumber | integer | 否 | 1 | |
| PageSize | integer | 否 | 10 | `[10, 100]` |
| SortBy | string | 否 | CreateTime | `AFPFiveHour` / `AFPWeekly` / `AFPMonthly` / `CreateTime`（**没有** `AFPDaily`） |
| SortOrder | string | 否 | Desc | `Asc` / `Desc` |

**示例 body**: `{"ProjectName": "default", "Filter": {"PlanType": ["Medium"]}, "PageNumber": 1, "PageSize": 20, "SortBy": "AFPWeekly", "SortOrder": "Desc"}`
**示例响应** `Result`: `{"TotalCount": 12, "PageNumber": 1, "PageSize": 20, "ProjectName": "default", "Items": [{"SeatID": "…", "PlanType": "Medium", "AFPFiveHour": {…}, "AFPDaily": {…}, "AFPWeekly": {…}, "AFPMonthly": {…}}]}` — 窗口对象结构同 2.4。

#### 获取单个 / 多个席位的 AFP 额度用量 — `GetSeatAFPUsage`
**Endpoint**: `POST /?Action=GetSeatAFPUsage&Version=2024-01-01`
**用途**: 已知 SeatID 时精确查，最多 1000 个；与 `ListSeatAFPUsage` 的区别是不分页、不排序、无 ProjectName。
**关键参数**: `SeatIDs`(string[], 必填, ≤1000)
**示例 body**: `{"SeatIDs": ["<seat-a>", "<seat-b>"]}`
**示例响应** `Result`: `{"SeatAFPUsages": [{"SeatID": "<seat-a>", "PlanType": "Medium", "AFPFiveHour": {…}, "AFPDaily": {…}, "AFPWeekly": {…}, "AFPMonthly": {…}}]}`，按请求顺序返回。

#### 获取单个 / 多个席位的模型调用数据明细 — `GetSeatUsageDetails`
**Endpoint**: `POST /?Action=GetSeatUsageDetails&Version=2024-01-01`
**用途**: 企业版 Agent Plan 席位按天 / 小时、按模型的调用明细（个人版对应 `GetUsageDetails`）。
**关键参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| QueryInterval | string | 是 | `Day` / `Hour` |
| SeatIDs | string[] | 是 | ≤1000 |
| Filter.StartTime / Filter.EndTime | **integer** | 是 | **epoch 毫秒**（个人版是 `YYYY-MM-DD` 字符串，别混） |
| Filter.ModelID / Filter.ModelName | string | 否 | 模型 ID / 模型卡片名 |
| Filter.ObjectName | string[] | 否 | 对外展示的 Model / Harness 名称列表，不传返回全部 |
| Filter.PlanType | **string** | 否 | `Small`…`Max`（个人版是 integer[]） |
| Filter.UserName | string | 否 | 只统计该子用户绑定期间的用量 |

**示例 body**
```json
{"QueryInterval": "Hour", "SeatIDs": ["<seat-a>"], "Filter": {"StartTime": 1756656000000, "EndTime": 1756742400000, "UserName": "alice"}}
```
**示例响应** `Result`: `{"SeatUsageDetails": [{"SeatID": "<seat-a>", "Details": [{"Time": 1756656000000, "ObjectName": "…", "BillingType": "WithinPlan", "Unit": "Tokens", "Usage": 12345}]}]}`
**注意事项**: `Details[].ObjectName` 的文档描述被写成了请求参数的描述（"限定要查询的…不传则返回全部"），实际应为该条明细的模型 / Harness 名——按 `GetUsageDetails` 同名字段理解。

#### 批量开 / 关企业版席位自动续费 — `UpdateSeatAutoRenew`
**Endpoint**: `POST /?Action=UpdateSeatAutoRenew&Version=2024-01-01`
**用途**: 批量设置席位自动续费；部分成功语义。
**关键参数**: `Plan`(必填, `AgentPlanTeam`/`CodingPlanTeam`) · `SeatIds`(string[], 必填, ≤200，不允许空串 / 重复) · `AutoRenew`(boolean, 必填) · `ProjectName`(默认 default)
**示例 body**: `{"Plan": "CodingPlanTeam", "SeatIds": ["<seat-a>", "<seat-b>"], "AutoRenew": false}`
**示例响应** `Result`: `{"SuccessIds": ["<seat-a>"], "FailedResults": [{"SeatId": "<seat-b>", "Message": "…"}]}`

#### Coding Plan 企业版：查询席位信息及用量 — `ListSeatInfoUsages`
**Endpoint**: `POST /?Action=ListSeatInfoUsages&Version=2024-01-01`
**用途**: 批量查 Coding Plan 席位的**额度用量**（月 / 周 / 近 5 分钟）。Coding Plan 额度不是 AFP，字段体系与 Agent Plan 的 `*AFPUsage` 不同。
**关键参数**: `SeatIDs`(string[], 必填, ≤1000，来自 `ListSeatInfos`) · `ProjectName`(默认 default)
**示例 body**: `{"SeatIDs": ["<seat-a>", "<seat-b>"]}`
**示例响应** `Result`
```json
{"Total": 2, "Data": [{"SeatID": "<seat-a>", "AccountID": 210000000, "ProjectName": "default", "UserID": 300000000, "UserName": "alice",
                       "MonthlySubscribeMilestone": 0, "MonthlyResetMilestone": 0, "MonthlyUsage": "…", "WeeklyUsage": "…", "ShortTermUsage": "…"}]}
```
| 字段 | 说明 |
|---|---|
| MonthlySubscribeMilestone | 本计费月（按订阅周期划分）订阅额度上限（integer） |
| MonthlyResetMilestone | 本计费月已重置（已发放）的可用额度（integer） |
| MonthlyUsage / WeeklyUsage | 本计费月 / 本计费周累计用量（**string**） |
| ShortTermUsage | 最近 5 分钟用量，用于实时监控限流（string） |
| AccountID / UserID | 此接口为 integer（`ListSeatInfos` 里 AccountID 是 string） |
**注意事项**: 用量的计量单位 ⚠ 文档未说明（Coding Plan 按"次数估算"，字段却是 string）。

#### Coding Plan 企业版：查询个人席位信息及用量 — `GetSeatInfoUsage`
**Endpoint**: `POST /?Action=GetSeatInfoUsage&Version=2024-01-01`
**用途**: 单个席位版的 `ListSeatInfoUsages`。
**关键参数**: `SeatID`(string, 必填) · `ProjectName`(默认 default)
**示例 body**: `{"SeatID": "<seat-a>"}`
**示例响应** `Result`: `{"SeatInfoUsage": {…}}`，对象字段与 `ListSeatInfoUsages.Data[]` 完全相同（注意外层键是 `SeatInfoUsage` 单个对象，不是数组）。

### 2.4 AFP 额度 / 用量字段含义

AFP 窗口对象（`GetAFPUsage` 顶层、`ListSeatAFPUsage.Items[]`、`GetSeatAFPUsage.SeatAFPUsages[]` 内均相同）：

| 窗口键 | 含义 | 窗口对象字段 |
|---|---|---|
| `AFPFiveHour` | 近 5 小时滚动窗口 | `Quota` string：窗口总配额（AFP）|
| `AFPDaily` | 近 1 天滚动窗口 | `Used` string：窗口内已消耗 AFP |
| `AFPWeekly` | 近 1 周滚动窗口 | `SubscribeTime` integer：当前计费窗口起始，epoch 毫秒 |
| `AFPMonthly` | 近 1 月滚动窗口 | `ResetTime` integer：下一次额度重置时间，epoch 毫秒 |

- 剩余额度 = `Quota - Used`（两者都是字符串，需自行转数值）。任一窗口耗尽即受限（限流 / 超额后付费的具体行为 ⚠ 文档未说明，属于数据面文档范围）。
- 文档共四档（5 小时 / 天 / 周 / 月）；`ListSeatAFPUsage.SortBy` 只支持 5 小时 / 周 / 月三档排序。
- ⚠ 文档自相矛盾：`GetAFPUsage` 页把 AFP 展开为 "Agent **Frame** Point"，Agent Plan 产品页 / 控制台口径是 "Agent **Fuel** Point"（见 `auth.md`）。缩写一致，不影响调用。
- 套餐内 vs 套餐外：`GetUsageDetails` / `GetSeatUsageDetails` 的 `BillingType` 为 `OutsideOfPlan` 的部分即超出 AFP 额度后按量计费的用量。

## 3. 查询用量

三个 Action 都是**标准 API（后付费）**的用量，不涉及 Plan 套餐额度（那些在第 2 节）。

#### 查询推理用量 — `GetInferenceUsage`
**Endpoint**: `POST /?Action=GetInferenceUsage&Version=2024-01-01`
**用途**: 按天 / 小时聚合的 token 与请求数，可按 API Key、模型、接入点等过滤；返回"列定义 + 二维数组"表格。
**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| StartTime / EndTime | string | 是 | — | `yyyy-MM-dd`，北京时间 UTC+8；EndTime ≥ StartTime |
| QueryInterval | string | 是 | — | `Day` / `Hour` |
| Filters[] | object[] | 否 | — | 多项 AND |
| Filters[].Key | string | 是 | — | `ApikeyID`（API Key 资源 ID，**推荐**）、`AuthToken`（即将下线）、`ModelName`、`ModelVersion`、`ModelEndpoint`（接入点 ID）、`EndpointName`、`ModelUnitID`、`BillingStatus`、`BatchJobID`、`BatchType` |
| Filters[].Values | string[] | 是* | — | 过滤值；长度 0 = 不过滤但结果列里带上该 Key（即"按此维度分组"） |
| Filters[].ValueLike | string | 是* | — | 前缀 / 包含近似匹配；与 Values 不能同时传 |
| ProjectName | string | 否 | default | |
| ShowWindowDetail | boolean | 否 | false | 返回计费窗口详情列 |

\* ⚠ 文档自相矛盾：`Values` 与 `ValueLike` 都标为"必选"，同时又说"不能同时传递"。按语义应为二选一，待实测。

`BillingStatus` 取值：`normal`（正常后付费）、`no_need_billing`（未开通前体验）、`free_for_model_unit`、`free_for_free_quota` / `free_for_limit_boundary`（安心体验边界内 / 外）、`free_for_viptier`（TPM 保障包）。

**示例 body**（按 API Key 资源 ID 查、并按模型分组）
```json
{"StartTime": "2026-09-01", "EndTime": "2026-09-03", "QueryInterval": "Day",
 "Filters": [{"Key": "ApikeyID", "Values": ["<api-key-resource-id>"]}, {"Key": "ModelName", "Values": []}]}
```
**示例响应** `Result`
```json
{"DataCount": 1,
 "Fields": [{"Name": "AccountID", "Type": "string"}, {"Name": "Day", "Type": "string"}, {"Name": "Hour", "Type": "string"}, {"Name": "ModelName", "Type": "string"},
            {"Name": "InputTokens", "Type": "integer"}, {"Name": "OutputTokens", "Type": "integer"}, {"Name": "TotalTokens", "Type": "integer"}, {"Name": "ReqCnt", "Type": "integer"}],
 "Data": [["…", "2026-09-01", "", "doubao-seed-2-1-pro", "1000", "200", "1200", "3"]]}
```
默认列：`AccountID` `Day` `Hour` `InputTokens` `OutputTokens` `TotalTokens` `ReqCnt` + Filters 里的所有 Key；`ShowWindowDetail=true` 时另加 `BillingStatus` `WindowMatchOrder` `WindowDescription` `WindowMaxInputTokens` `WindowMaxOutputTokens`。`Data` 声明为 `string[]`（二维数组，每行列序同 `Fields`）。
**注意事项**
- **2026-08-12 及之后创建的 API Key 只能用 `ApikeyID` 查**；之前的存量 Key 暂时兼容 `AuthToken`，但该方式即将下线。`ApikeyID` = 控制台 API Key 管理页的"资源 ID"，**不是 Key 密钥本身**。
- `AuthToken` 的脱敏格式：传统 Key 前 8 + `****` + 后 12；新版方舟 Key 前 3 + `****` + 后 5（如 `ark****d5b88`）；JWT 鉴权为 `****`。
- Key 名大小写：文档标题写 `ApiKeyID`，取值列表写 `ApikeyID` ⚠ 文档自相矛盾，待实测哪种被接受。

#### 创建用量明细导出任务 — `CreateRecordExportTask`
**Endpoint**: `POST /?Action=CreateRecordExportTask&Version=2024-01-01`
**用途**: 异步导出**逐条**用量明细 CSV（比 `GetInferenceUsage` 的聚合更细）。
**关键参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| StartTime / EndTime | number | 是 | UTC Unix **秒**；`EndTime - StartTime ≤ 10800`（3 小时）；StartTime 最小 `1777593600`（2026-05-01 00:00 UTC） |
| Filters[] | object[] | 是（`model_name` 项必填） | `Key` ∈ `model_name`(必填) / `model_endpoint` / `batch_job_id` / `volc_instance_id`；`Values` string[] |

**示例 body**: `{"StartTime": 1756857600, "EndTime": 1756868400, "Filters": [{"Key": "model_name", "Values": ["doubao-seed-2-0-pro"]}]}`
**示例响应** `Result`: `{"Task": {"Id": "uet-20260903100000-a1b2c"}}`（格式 `uet-YYYYMMDDhhmmss-<5 位字母数字>`）
**注意事项**: 同账号活跃任务 ≤ 3；滚动 24 小时最多提交 100 个。更长区间按 3 小时切片多次提交。`model_name` 取值示例（文档）：`doubao-seed-2-0-pro`、`doubao-seed-2-0-lite`、`doubao-seed-2-0-mini`、`doubao-seed-2-0-code`、`doubao-seedance-2-0`、`doubao-seedance-2-0-fast`——注意是**不带日期**的模型名。

#### 查询用量明细导出任务状态 — `GetRecordExportTask`
**Endpoint**: `POST /?Action=GetRecordExportTask&Version=2024-01-01`
**关键参数**: `Id`(string, 必填)
**示例 body**: `{"Id": "uet-20260903100000-a1b2c"}`
**示例响应** `Result.Task`
```json
{"Id": "uet-…", "Status": "Succeeded", "CreateTime": 1756868400, "StartTime": 1756868405, "EndTime": 1756868460,
 "TotalCount": 120000, "ExportCount": 100000, "DownloadUrl": "https://…tos…", "DownloadUrlExpireTime": 1756911660,
 "FileExpired": false, "ErrorMessage": "", "QueryParams": "{…原始请求 JSON…}"}
```
| 字段 | 说明 |
|---|---|
| Status | `Pending` → `Running` → `Succeeded` / `Failed`（失败原因见 `ErrorMessage`） |
| DownloadUrl | TOS 一次性签发链接，仅 Succeeded 时有；**有效期 12 小时**，过期 `FileExpired=true`，需重新提交任务 |
| TotalCount / ExportCount | 命中行数 / 实际导出行数；ExportCount 上限 `100000`，TotalCount 更大说明被截断 |
| StartTime / EndTime | 任务进入 Running / 终态的时刻，处理中不返回 |
**注意事项**
- 轮询：提交后先等 5 秒，间隔 ≥ 5 秒，单任务总轮询 ≤ 5 分钟；拿到 `DownloadUrl` 立即下载。
- **CSV 计费列变更**：请求的 `EndTime` 晚于切换时刻（2026-09-02 前有调用的用户为 2026-09-15，之后新增用户为 2026-09-02）时，`input_token_charge_item` / `output_token_charge_item` / `cache_hit_token_charge_item` 三列不再单独返回，统一并入 `charge_value_list`；解析见《用量明细 CSV 解析最佳实践》https://docs.volcengine.com/docs/82379/2673887。
- `FileExpired` 类型标注为 `number` 但取值为 `true` ⚠ 文档自相矛盾（应为 boolean）。

## 4. 管理 API Key：临时 API Key

#### 获取临时 API Key — `GetApiKey`
**Endpoint**: `POST /?Action=GetApiKey&Version=2024-01-01`
**用途**: 用 AK/SK 换一把**有时效、绑定到指定资源**的数据面 API Key，用于把 Key 下发给前端 / 客户端等不可信环境。与控制台长期 API Key 的区别：有 `DurationSeconds` 到期时间、只能调 `ResourceIds` 列出的接入点 / 智能体、可由服务端按需签发而无需人在控制台创建。
**关键参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| DurationSeconds | integer | 是 | 有效期秒数，`[0, 2592000]`（最长 30 天） |
| ResourceType | string | 是 | `endpoint`（推理接入点）/ `bot`（智能体）/ `presetendpoint`（预置推理接入点） |
| ResourceIds | string[] | 是 | 对应资源 ID：endpoint ID（控制台 > 推理）或 bot ID（控制台 > 我的应用） |
| ProjectName | string | ResourceType=`presetendpoint` 时必填 | |

**示例 body**: `{"DurationSeconds": 3600, "ResourceType": "endpoint", "ResourceIds": ["ep-xxxxxxxx-xxxxx"]}`
**示例响应** `Result`: `{"ApiKey": "…", "ExpiredTime": 1756872000}`（ExpiredTime Unix **秒**）
**注意事项**
- 拿到的 Key 走数据面 `Authorization: Bearer <ApiKey>`，`model` 填对应 `ep-` 接入点 ID。
- ⚠ 文档未说明：临时 Key 能否用于 Coding Plan / Agent Plan 入口（`ResourceType` 只有 endpoint / bot / presetendpoint，推测不能）；`presetendpoint` 的资源 ID 从哪里取（可参考索引表里的 `InnerDescribeModelEndpoints`）。
- 长期方舟 API Key 的创建 / 删除没有本次输入范围内的管控面 Action，走控制台 API Key 管理页。

## 5. 基础模型与限流查询

这是**程序化获取"当前可用模型 ID / 上下文长度 / 能力标签"**的办法：`ListFoundationModels` 拿模型名（如 `doubao-seed-2-1-pro`）→ `ListFoundationModelVersions` 拿版本号（如 `260628`）→ 标准入口的 Model ID = `<Name>-<ModelVersion>`（如 `doubao-seed-2-1-pro-260628`）⚠ 拼接规则为根据 auth.md 示例推断，文档未明说，待实测。Plan 入口用的小写 Model Name 见 2.2 的 `ListArk*PlanModel`。

#### ListFoundationModels — 获取基础模型列表
**Endpoint**: `POST /?Action=ListFoundationModels&Version=2024-01-01`
**关键参数**
| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| Filter.Name / Filter.Names | string / string[] | — | 名称模糊 / 精确匹配 |
| Filter.DisplayName / Description / Introduction | string | — | 模糊匹配 |
| Filter.AccessTypes | string[] | — | `Public` / `Private` |
| Filter.FoundationModelTag.Domains | string[] | — | `LLM` `Audio` `ComputerVision` `MultiModal` `Embedding` `VLM` |
| Filter.FoundationModelTag.TaskTypes | string[] | — | `TextGeneration` `VisualQuestionAnswering` `TextToImage` `ImageToImage` `TextToVideo` `ImageToVideo` `TextTo3D` `ImageTo3D` `VoiceClone` `TextToSpeech` `SpeechToText` `SpeechToSpeech` `TextEmbedding` `ImageEmbedding` `MultimodalEmbedding` |
| Filter.FoundationModelTag.Languages / UsedLibraries | string[] | — | |
| Filter.SupportedCustomizationTypes | string[] | — | `Sft` `Lora` `ContinuePretrain` `FinetuneSft` `FinetuneLoRA` `DPOLoRA` `Pretrain` |
| TagFilters[] | object[] | — | `Key`(必填) + `Values` 自定义标签 |
| PageNumber / PageSize | integer | 1 / 10 | PageSize `[1, 100]` |
| SortBy / SortOrder | string | CreateTime / Desc | `CreateTime` / `UpdateTime`；`Asc` / `Desc` |
| ProjectName | string | default | |

**示例 body**: `{"Filter": {"FoundationModelTag": {"Domains": ["LLM"], "TaskTypes": ["TextGeneration"]}}, "PageSize": 100}`
**示例响应** `Result`
```json
{"TotalCount": 1, "PageNumber": 1, "PageSize": 100,
 "Items": [{"Name": "doubao-seed-2-1-pro", "DisplayName": "Doubao-Seed-2.1-pro", "VendorName": "…", "AccessType": "Public",
            "PrimaryVersion": "260628", "ProjectName": "default", "Description": "…",
            "FoundationModelTag": {"Domains": ["LLM"], "TaskTypes": ["TextGeneration"], "Languages": ["…"], "UsedLibraries": []},
            "FeaturedImage": {"BucketName": "…", "ObjectKey": "…"}, "Tags": [{"Key": "…", "Value": "…"}],
            "CreateTime": "2026-06-28T00:00:00Z", "UpdateTime": "2026-06-28T00:00:00Z"}]}
```
（示例值为形态示意，非文档原值。）`Items[].Introduction` 在 List 接口**不返回**（尺寸原因），要看介绍用 `GetFoundationModel`。`PrimaryVersion` 是当前主推版本号。

#### GetFoundationModel — 获取基础模型信息
**Endpoint**: `POST /?Action=GetFoundationModel&Version=2024-01-01`
**关键参数**: `Name`(string, 必填)
**示例 body**: `{"Name": "doubao-seed-2-1-pro"}`
**示例响应** `Result`: 与 List 的 Item 同构，另多 `Introduction`、`DisplayDescription`、`ShortName`、`RegionWhiteList`(string[])、`ResourceOrigin`。只含模型元数据，不含版本配置。

#### ListFoundationModelVersions — 获取基础模型版本列表
**Endpoint**: `POST /?Action=ListFoundationModelVersions&Version=2024-01-01`
**关键参数**: `FoundationModelName`(必填) · `Filter.ModelVersions`(string[], 精确) · `Filter.Statuses`(string[], `Unpublished`/`Published`/`Retiring`) · `Filter.Description` · `PageNumber`/`PageSize`(1/10, `[1,100]`) · `SortBy`/`SortOrder` · `ProjectName`
**示例 body**: `{"FoundationModelName": "doubao-seed-2-1-pro", "Filter": {"Statuses": ["Published"]}}`
**示例响应** `Result`: `{"TotalCount": 1, "Items": [{"FoundationModelName": "doubao-seed-2-1-pro", "ModelVersion": "260628", "Status": "Published", "ActiveConfigurationId": "…", "Description": "…", "PublishTime": "…", "CreateTime": "…", "UpdateTime": "…"}]}`
**注意事项**: 只返回已发布 / 下线中版本；`Unpublished` 可见性受账号权限控制。`Retiring` = 下线中，选模型时应避开。

#### GetFoundationModelVersion — 获取基础模型版本信息
**Endpoint**: `POST /?Action=GetFoundationModelVersion&Version=2024-01-01`
**用途**: 该版本当前生效配置快照——**上下文 / 输入长度、可调参数及范围、精调支持**都在这里。
**关键参数**: `FoundationModelName`(必填) · `ModelVersion`(必填)
**示例 body**: `{"FoundationModelName": "doubao-seed-2-1-pro", "ModelVersion": "260628"}`
**示例响应** `Result`（关键字段）
```json
{"FoundationModelName": "doubao-seed-2-1-pro", "ModelVersion": "260628", "Status": "Published", "ActiveConfigurationId": "…",
 "PublishTime": "…", "CreateTime": "…", "UpdateTime": "…", "Description": "…",
 "Configuration": {
   "AppSettings": {"MaxInputTokenLength": 0, "Greeting": "…",
     "Parameters": [{"Name": "temperature", "Type": "Float", "DefaultValue": "…", "Min": "…", "Max": "…", "Options": [], "DisplayName": "…", "Description": "…"}],
     "SystemPrompt": {"Message": "…", "MaxInputTokenLength": 0, "ModificationAllowed": true}, "Prompts": [{"Scenario": "…", "Message": "…"}]},
   "CustomizationJobSettings": {
     "SftSettings": {"Enabled": true, "Parameters": [...], "SupportPresetDatasets": [{"Name": "…", "Labelled": true, "SampleCount": 0, "Description": "…"}]},
     "LoraSettings": {...}, "LoraDPOSettings": {...}, "ContinuePretrainSettings": {...}}}}
```
| 字段 | 说明 |
|---|---|
| Configuration.AppSettings.MaxInputTokenLength | 用户输入允许的最大 token 长度（文档语境是"模型体验应用"配置 ⚠ 是否等于 API 上下文窗口，文档未说明） |
| Configuration.AppSettings.Parameters[] | 可配置参数：`Name` `Type`(`Int`/`Bool`/`Float`/`String`) `DefaultValue` `Min` `Max` `Options[]` |
| Configuration.CustomizationJobSettings.{Sft,Lora,LoraDPO,ContinuePretrain}Settings | 各精调类型 `Enabled` + 训练参数（多一个 `IncrementalLearningLocked`）+ `SupportPresetDatasets[]` |
**注意事项**: 三个 Get 页面都提到 `GetFoundationModelVersionConfiguration`（按配置 ID 查完整配置），该 Action 不在本次输入页面与导航中 ⚠ 文档未说明其参数。

#### ListModelRateLimit — 查询模型限流
**Endpoint**: `POST /?Action=ListModelRateLimit&Version=2024-01-01`
**用途**: 账号下各基础模型的默认 / 当前限流（RPM、TPM、TPD、图片 IPM、视频并发、实时连接），用于判断是否需要提额工单。
**关键参数**: `FoundationModelNames`(string[], 可选；空 = 全部模型)
**示例 body**: `{"FoundationModelNames": ["doubao-seed-2-1-pro"]}`
**示例响应** `Result`
```json
{"TotalCount": 1,
 "Items": [{"FoundationModelName": "doubao-seed-2-1-pro", "DefaultTpd": 0, "CurrentTpd": 0,
            "DefaultRateLimit": {"Rpm": 0, "Tpm": 0, "FastTpm": 0, "Ipm": 0, "LoraTpm": 0},
            "CurrentRateLimit": {"Rpm": 0, "Tpm": 0, "FastTpm": 0, "Ipm": 0, "LoraTpm": 0},
            "ContentGenerationRateLimit": {"ConcurrentRequests": 0, "ConcurrentRequestsFor4K": 0, "CreateTaskRpm": 0, "CreateTaskRpmFor4K": 0, "ListTaskRpm": 0, "DeleteTaskRpm": 0},
            "RealtimeRateLimit": {"ConcurrentConnections": 0, "CPMPerConnection": 0, "TPMPerConnection": 0}}]}
```
| 字段 | 说明 |
|---|---|
| DefaultRateLimit / CurrentRateLimit | 默认 vs 当前（可能已提额）：`Rpm`、`Tpm`、`FastTpm`（快速通道）、`Ipm`（每分钟图片）、`LoraTpm` |
| DefaultTpd / CurrentTpd | 每日 token 限额 |
| ContentGenerationRateLimit | 视频等内容生成任务：并发数（含 4K 档）、创建 / 查询 / 删除任务 RPM |
| RealtimeRateLimit | 实时对话：并发连接、单连接每分钟轮次 CPM、单连接 TPM |
**注意事项**: 限流是**账号 × 基础模型**维度，同一基础模型下所有接入点共享；只计按 token 后付费的调用，不含模型单元（见第 6 节）。数值 0 的含义（不限 / 无此能力）⚠ 文档未说明。

## 6. 开通管理

标准 API（后付费）的模型**必须先开通才能计费调用**，否则只能消耗免费额度；Plan 入口不受此约束（额度制）。控制台：`https://console.volcengine.com/ark/region:cn-beijing/openManagement`。

| 要点 | 内容（来源：开通管理页） |
|---|---|
| 开通状态 | `未开通`（可先用免费额度，耗尽后需开通）/ `已开通` / `邀测中`（不能自助开通，需提工单） |
| 自动开通开关 | 开通弹窗里勾选"全选"+"自动开通新增模型"，之后新增且支持自动开通的模型自动开通；**Doubao-Seed-Evolving 不在自动开通范围**，需手动开通 |
| 免费额度 | 每个模型有免费调用额度；开通后仍**优先消耗剩余免费额度** |
| 安心体验模式 | 新用户只消耗平台赠送的 50 万 token 免费额度，接近耗尽自动暂停；只抵扣推理 token，不抵扣插件 / 知识库费用 |
| 推理限额 | 每模型可设 token 限额，达到即暂停服务；仅在线推理（不含批量）、仅已开通且按 token 后付费的模型；与前缀缓存互斥；语音 / 多模态向量化模型不支持；已买 TPM 保障包 / 模型单元的接入点不支持；同一模型两次设置间隔 ≥ 2 小时；控制台免费额度数据有小时级延迟 |
| 模型级限流 | 每账号每基础模型有 RPM / TPM 限制（查询用第 5 节 `ListModelRateLimit`）；提额提工单 |

对应管控面 Action（本次未展开，见索引表"管理模型开通"）：`ActivateModels` 批量开通、`EnableAutoModelActivation` / `DisableAutoModelActivation` 自动开通开关、`GetModelActivation` / `ListModelActivations` 查询开通状态。

## 7. 其他管控面分组索引

未在本文展开的分组，URL 格式 `https://www.volcengine.com/docs/82379/<DocumentID>`：

| 分组 | 分组页 | 主要 Action（DocumentID） |
|---|---|---|
| 管理推理接入点（Endpoint） | 1261491 | CreateEndpoint 1262823 · GetEndpoint 1262431 · ListEndpoints 1262430 · UpdateEndpoint 1262814 · DeleteEndpoint 1262813 · StartEndpoint 1261492 · StopEndpoint 1262429 · GetEndpointCertificate 1357818 · InnerDescribeModelEndpoints（预置接入点列表）2535700 · CreateEndpointRolling 2582730 · GetEndpointRolling 2582731 · RollbackEndpointRolling 2582732 · CancelEndpointRolling 2582733 |
| 管理模型开通 | 2596253 | ActivateModels 2596254 · EnableAutoModelActivation 2596255 · DisableAutoModelActivation 2596256 · GetModelActivation 2596257 · ListModelActivations 2596258 |
| 管理 API Key | 1359520 | GetApiKey（临时 Key）1262825 —— 本文第 4 节 |
| 管理基础模型 | 1257586 | ListFoundationModels 1262849 · GetFoundationModel 1257587 · ListFoundationModelVersions 1262847 · GetFoundationModelVersion 1262848 —— 本文第 5 节 |
| 管理模型限流 | 2612139 | ListModelRateLimit 2612140 —— 本文第 5 节 |
| 查询用量 | 1390291 | GetInferenceUsage 2116766 · CreateRecordExportTask 2479853 · GetRecordExportTask 2479854 —— 本文第 3 节 |
| 管理 Agent / Coding Plan（总览 1820190） | 2636787 | 子分组：管理 Agent Plan 2649408 · 管理 Agent Plan（企业版）2649410 · 管理 Coding Plan 2649409 · 管理 Coding Plan（企业版）2649411 —— 本文第 2 节 |
| 管理模型精调 | 1262826 | 创建 1262829 · 获取信息 1262828 · 列表 1262830 · 更新 1262831 · 停止 1262827 · 重试 1344728 · 删除 1262832 · 精调效果指标 1511935 · 指标详细数据 1511933 |
| 管理模型评测 | 1262833 | 创建 1262837 · 获取 1262835 · 列表 1262836 · 更新 1262838 · 停止 1262834 · 删除 1262840 · 结果 1262841 · 结果列表 1262839 |
| 管理定制模型 | 1262842 | ListCustomModels 1262846 · GetCustomModel 1262844 · UpdateCustomModel 1262845 · DeleteCustomModel 1262843 |
| 安全审计 | 1289653 | ListAuditLogs 1289652 · CreateArkOfficialResultQuery 2588687 · GetArkOfficialResult 2598416 |
| 管理私域素材库 | 2333600 | 素材资产组合：创建 2318270 · 列表 2318272 · 信息 2318275 · 更新 2318276 · 删除 2341606；素材资产：创建 2318271 · 列表 2318273 · 信息 2318274 · 更新 2318277 · 删除 2318278；拉起真人认证 H5 2333587 · 获取真人 Asset Group ID 2333588 |
| 管理版权库 | 2652236 | 查询版权 IP 模板列表 2652237 |
| 效果上报 | 2389901 | 上报视频生成效果问题 2389900 · 查询视频结果 2551134 · 上报大语言模型效果问题 2670595 · 查询 LLM 结果 2670596 |

## 来源页面

| 标题 | URL | 文档更新时间 |
|---|---|---|
| Base URL 及鉴权 | https://www.volcengine.com/docs/82379/1298459 | 2026-06-23 |
| 创建个人版套餐（CreatePersonalPlan） | https://www.volcengine.com/docs/82379/2522497 | 2026-08-27 |
| 续费个人版套餐（RenewPersonalPlan） | https://www.volcengine.com/docs/82379/2546383 | 2026-08-27 |
| 查询个人版套餐（GetPersonalPlan） | https://www.volcengine.com/docs/82379/2546382 | 2026-08-20 |
| 查询 Agent Plan 支持的模型列表（ListArkAgentPlanModel） | https://www.volcengine.com/docs/82379/2546385 | 2026-08-26 |
| 查询 Coding Plan 支持的模型列表（ListArkCodingPlanModel） | https://www.volcengine.com/docs/82379/2546386 | 2026-08-20 |
| 获取套餐 AFP 额度（GetAFPUsage） | https://www.volcengine.com/docs/82379/2479847 | 2026-08-20 |
| 获取套餐用量详情（GetUsageDetails） | https://www.volcengine.com/docs/82379/2479849 | 2026-08-20 |
| 轮换个人版 API Key（RegeneratePersonalApiKey） | https://www.volcengine.com/docs/82379/2546380 | 2026-08-20 |
| 创建企业版席位（CreateTeamSeats） | https://www.volcengine.com/docs/82379/2522498 | 2026-08-21 |
| 续费企业版席位（RenewTeamSeats） | https://www.volcengine.com/docs/82379/2545601 | 2026-09-03 |
| 批量绑定企业版席位（AssignTeamSeats） | https://www.volcengine.com/docs/82379/2546378 | 2026-09-03 |
| 获取企业版席位 API Key（GetTeamSeatApiKey） | https://www.volcengine.com/docs/82379/2546379 | 2026-09-03 |
| 批量更新企业版席位 API Key（RegenerateTeamSeatApiKeys） | https://www.volcengine.com/docs/82379/2546384 | 2026-09-03 |
| 查询席位基本信息列表（ListSeatInfos） | https://www.volcengine.com/docs/82379/2307201 | 2026-08-27 |
| 查询席位 AFP 额度用量列表（ListSeatAFPUsage） | https://www.volcengine.com/docs/82379/2479850 | 2026-09-03 |
| 获取单个/多个席位的 AFP 额度用量（GetSeatAFPUsage） | https://www.volcengine.com/docs/82379/2479851 | 2026-09-03 |
| 获取单个/多个席位的模型调用数据明细（GetSeatUsageDetails） | https://www.volcengine.com/docs/82379/2479852 | 2026-09-03 |
| 批量开/关企业版席位自动续费（UpdateSeatAutoRenew） | https://www.volcengine.com/docs/82379/2657080 | 2026-08-27 |
| 查询席位信息及用量（ListSeatInfoUsages） | https://www.volcengine.com/docs/82379/2286756 | 2026-08-20 |
| 查询个人席位信息及用量（GetSeatInfoUsage） | https://www.volcengine.com/docs/82379/2306579 | 2026-08-20 |
| 查询推理用量（GetInferenceUsage） | https://www.volcengine.com/docs/82379/2116766 | 2026-09-02 |
| 创建用量明细导出任务（CreateRecordExportTask） | https://www.volcengine.com/docs/82379/2479853 | 2026-08-28 |
| 查询用量明细导出任务状态（GetRecordExportTask） | https://www.volcengine.com/docs/82379/2479854 | 2026-09-03 |
| 获取临时 API Key（GetApiKey） | https://www.volcengine.com/docs/82379/1262825 | 2026-08-20 |
| ListFoundationModels - 获取基础模型列表 | https://www.volcengine.com/docs/82379/1262849 | 2026-08-20 |
| GetFoundationModel - 获取基础模型信息 | https://www.volcengine.com/docs/82379/1257587 | 2026-08-20 |
| ListFoundationModelVersions - 获取基础模型版本列表 | https://www.volcengine.com/docs/82379/1262847 | 2026-08-20 |
| GetFoundationModelVersion - 获取基础模型版本信息 | https://www.volcengine.com/docs/82379/1262848 | 2026-08-20 |
| ListModelRateLimit - 查询模型限流 | https://www.volcengine.com/docs/82379/2612140 | 2026-08-20 |
| 开通管理 | https://www.volcengine.com/docs/82379/1159200 | 2026-08-13 |
| 文档导航（管控面 API 分组索引） | scratch/nav-969.tsv | 2026-09-03 抓取 |
