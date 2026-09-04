# 批量推理与应用(Bot) API

本文件覆盖火山方舟三类"非普通在线 Chat"的调用入口：**批量(Chat) API**（批量推理接入点，同步接口形态）、**批量(Job) API**（离线任务，输入/输出走对象存储 TOS，管控面接口）、**应用(Bot) API**（应用实验室零/低代码应用的调用入口，含联网/知识库插件引用结构）以及 Beta 的智能体插件 API。

## 目录

- [1. 选型：三条路各解决什么问题](#1-选型三条路各解决什么问题)
- [2. 批量推理两种模式对比（Chat 接入点 vs Job 任务）](#2-批量推理两种模式对比chat-接入点-vs-job-任务)
- [3. 批量(Chat) API](#3-批量chat-api)
- [4. 批量(Job) API：离线任务](#4-批量job-api离线任务)
  - [4.1 前提与 JSONL 输入文件格式](#41-前提与-jsonl-输入文件格式)
  - [4.2 管控面请求形态与签名](#42-管控面请求形态与签名)
  - [4.3 CreateBatchInferenceJob](#43-createbatchinferencejob)
  - [4.4 ListBatchInferenceJobs / GetBatchInferenceJob](#44-listbatchinferencejobs--getbatchinferencejob)
  - [4.5 Update / Stop / Resume / Delete](#45-update--stop--resume--delete)
  - [4.6 任务状态机](#46-任务状态机)
  - [4.7 输出文件位置与行格式](#47-输出文件位置与行格式)
  - [4.8 配额、时长与计费](#48-配额时长与计费)
  - [4.9 （可选）SNS 完成/失败通知](#49-可选sns-完成失败通知)
- [5. 应用(Bot) API](#5-应用bot-api)
  - [5.1 与普通 Chat 的差异](#51-与普通-chat-的差异)
  - [5.2 Endpoint 详解](#52-endpoint-详解)
  - [5.3 references：联网插件 / 知识库插件数据结构](#53-references联网插件--知识库插件数据结构)
  - [5.4 智能体插件 API（Beta）](#54-智能体插件-apibeta)
- [6. Plan 入口（Coding Plan / Agent Plan）可用性](#6-plan-入口coding-plan--agent-plan可用性)
- [来源页面](#来源页面)

---

## 1. 选型：三条路各解决什么问题

| 我想… | 用哪条路 | 入口 / 鉴权 | model 字段 |
|---|---|---|---|
| 大批量离线跑 Chat / 向量化请求，能接受天级延迟，要 50% 价格 + 独立配额，数据已在 TOS | **批量(Job) API**（批量推理任务） | 管控面 `https://ark.cn-beijing.volcengineapi.com/?Action=…&Version=2024-01-01`，AK/SK HMAC-SHA256 签名 | 不在请求行里填；任务级 `ModelReference`（基础模型 Name+ModelVersion 或 CustomModelId） |
| 现有在线 Chat 代码改动最小地切到批量价格，数据是动态产生的 | **批量(Chat) API**（批量推理接入点） | 数据面 `POST /api/v3/batch/chat/completions`，API Key 或 Access Key | 批量推理接入点 ID（控制台创建，格式 `ep-bi-***`） |
| 调用在"应用实验室"里配好的零/低代码应用（带联网、知识库等插件） | **应用(Bot) API** | 数据面 `POST /api/v3/bots/chat/completions`，API Key（Access Key 需走 SDK） | 应用 ID（Bot ID） |

定位说明：
- Bot API 是**应用实验室**产物的 API 出口：插件（联网、知识库、群聊角色等）在控制台里配置，请求体基本沿用 Chat 结构，响应多出 `references`、`bot_usage`。它与 Responses API 的内置工具（模型侧按请求声明工具）是两条独立的路，不要混用字段。
- 批量推理不包含批量视频生成；视频离线推理见文档 1366799（本文件不覆盖）。
- 支持批量推理的模型"以控制台可选模型为准"，文档未给静态列表。

---

## 2. 批量推理两种模式对比（Chat 接入点 vs Job 任务）

来自《批量推理》指南（1399517），文档原话：**"当两种方式都可满足业务需求时，推荐优先使用批量推理任务的方式"**。

| 维度 | 批量推理任务（Job API） | 批量推理接入点（Batch Chat API） |
|---|---|---|
| 工作方式 | 请求写成 JSONL 上传到 TOS → `CreateBatchInferenceJob` → 轮询状态 → 从 TOS 读结果 | 像在线 Chat 一样逐条请求，平台"一段时间后"返回结果（时长受资源影响） |
| 适用场景 | 数据已静态存于 TOS；日处理量大；多模态批量（带宽压力大） | 数据非静态、改造成 JSONL 复杂；上下游都是在线链路；只想换一个方法名 |
| 核心流程 | 1 上传（>5 GB 分片）2 创建任务 3 查状态 4 读结果 | 1 控制台创建批量推理接入点 2 用 `batch.chat.completions` 调用，**配置 >30 分钟超时与并发数** |
| 优势 | 规模/带宽上限更高；平台托管调度、吞吐最优；高峰仍有处理效率；透明前缀缓存折扣 | 改造成本小；高峰仍有处理效率；透明前缀缓存折扣 |
| 劣势 | 有工程改造量（上传、分片、目录切分） | 高峰期会收到较多 `ServerOverloaded` 报错（文档原文，未实测），需重试退避（方舟 SDK 在超时范围内自动处理）；每日吞吐可控性稍弱 |
| 价格 | 输入输出单价为在线推理的 **50%**；命中透明前缀缓存的输入再降 60% | 同左 |
| 配额 | 默认 **100 亿 token/天**（TPD），可工单提额；与在线推理限流（TPM）**隔离**，不消耗在线配额 | 同左（"每个主账户至少 10B token/天"） |

⚠ 文档自相矛盾：指南称两种模式都"支持透明前缀缓存能力，命中缓存的 token 会有更低折扣"，但《批量(Chat) API》响应参数写明 `usage.prompt_tokens_details.cached_tokens`"本接口暂不支持该字段，此处应为 0"；Job 结果文件示例中 `cached_tokens` 也为 0。缓存折扣是否真正生效、如何在 usage 里体现，待实测。

---

## 3. 批量(Chat) API

### 批量推理接入点对话补全
**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/v3/batch/chat/completions`
**用途**: 与 `/api/v3/chat/completions` 参数一致的"批量价格版"同步接口；区别是 `model` 必须填**批量推理接入点** ID（`ep-bi-***`，控制台"批量推理 → 开始批量推理 → 调用方式选'创建批量推理接入点'"），且需要很长的客户端超时。预置接入点（直接填 Model ID）不支持批量推理，必须自建接入点（《推理方式概述》功能表）。

**鉴权**: API Key（`Authorization: Bearer $ARK_API_KEY`）或 Access Key 签名。仅标准 `/api/v3` 入口；Plan 入口见 §6。

**关键参数**（请求体与 Chat API 相同，此处只列文档页明确给出的）
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | — | 批量推理接入点 Endpoint ID |
| `messages` | object[] | 是 | — | `system` / `user` / `assistant`(content 与 tool_calls 至少其一)；user/system 的 content 支持 string 或多模态数组（`text` / `image_url` / `video_url`） |
| `messages[].content[].image_url.detail` | string | 否 | user 消息默认 `low`，system 消息默认 `auto`（文档两处写法不一致，⚠ 文档自相矛盾） | `high` / `low` / `auto`；`high` 时 min_pixels 3136、max_pixels 4014080，`low` 时 max_pixels 1048576 |
| `messages[].content[].image_url.image_pixel_limit` | object | 否 | null | `{min_pixels, max_pixels}`，3136 ≤ min < max ≤ 4014080；优先级高于 `detail` |
| `messages[].content[].video_url.fps` | float | 否 | 1 | [0.2, 5] |
| `thinking` | object | 否 | `{"type":"enabled"}` | `type`: `enabled` / `disabled` / `auto` |
| `max_tokens` | integer | 否 | 4096 | 与 `max_completion_tokens` **互斥，同时设置直接报错**（文档原文，未实测） |
| `max_completion_tokens` | integer | 否 | — | [0, 64k]；含思维链；文档列出的支持模型：`deepseek-r1-250528`、`doubao-seed-1-6-250615`、`doubao-seed-1-6-flash-250615` |
| `stop` | string / string[] | 否 | null | 最多 4 个；深度思考模型不支持 |
| `temperature` / `top_p` | float | 否 | 1 / 0.7 | [0,2] / [0,1]，建议只调其一 |
| `frequency_penalty` / `presence_penalty` | float | 否 | 0 | [-2.0, 2.0] |
| `logprobs` / `top_logprobs` | bool / int | 否 | false / 0 | top_logprobs [0,20]，需 logprobs=true |
| `logit_bias` | map | 否 | null | `{"<token_id>": -100..100}` |
| `tools` | object[] | 否 | null | 仅 `type: "function"`，`function.{name, description, parameters(JSON Schema)}` |

⚠ 文档未说明：该页参数表**没有列出** `stream` / `stream_options` / `response_format`。批量接入点是否支持流式，待实测。

**示例请求**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/batch/chat/completions \
  --max-time 86400 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "ep-bi-xxxxxxxx",
    "messages": [{"role": "user", "content": "天空为什么这么蓝？"}],
    "thinking": {"type": "disabled"},
    "max_tokens": 1000
  }'
```

```python
# 官方方舟 SDK：底层就是 POST /api/v3/batch/chat/completions
import os
from volcenginesdkarkruntime import Ark

client = Ark(
    api_key=os.environ["ARK_API_KEY"],
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    timeout=24 * 3600,          # 文档推荐 24~72 小时（支持 1~72 小时）
)
completion = client.batch.chat.completions.create(
    model="ep-bi-xxxxxxxx",
    messages=[{"role": "user", "content": "天空为什么这么蓝？"}],
)
print(completion.choices[0].message.content)
```

```python
# 不用官方 SDK 时用 requests；注意超时要给得很长
import os, requests
r = requests.post(
    "https://ark.cn-beijing.volces.com/api/v3/batch/chat/completions",
    headers={"Authorization": f"Bearer {os.environ['ARK_API_KEY']}"},
    json={"model": "ep-bi-xxxxxxxx",
          "messages": [{"role": "user", "content": "天空为什么这么蓝？"}]},
    timeout=24 * 3600,
)
r.raise_for_status()
print(r.json()["choices"][0]["message"]["content"])
```

**示例响应**（非流式，字段与 Chat 一致）

```json
{
  "id": "0217…",
  "object": "chat.completion",
  "created": 1768279310,
  "model": "doubao-seed-2-1-pro-260628",
  "service_tier": "default",
  "choices": [{
    "index": 0,
    "finish_reason": "stop",
    "message": {"role": "assistant", "content": "…", "reasoning_content": "…", "tool_calls": null},
    "logprobs": null,
    "moderation_hit_type": null
  }],
  "usage": {
    "prompt_tokens": 49, "completion_tokens": 210, "total_tokens": 259,
    "prompt_tokens_details": {"cached_tokens": 0},
    "completion_tokens_details": {"reasoning_tokens": 169}
  }
}
```

`finish_reason` 枚举：`stop` / `length`（max_tokens、max_completion_tokens 或 context_window 任一触发）/ `content_filter` / `tool_calls`。`service_tier` 目前只有 `default`（未使用 TPM 保障包）。`moderation_hit_type`（`severe_violation` / `violence`）仅视觉理解模型且接入点内容护栏设为 Basic 时返回。

**注意事项（来自指南，均为文档口径）**
- **超时**：`timeout` 推荐 24~72 小时（取值支持 1~72 小时）。长超时不影响配额；短超时在深度思考/长输出场景容易中途断开，"既浪费 token 成本，又无法输出内容"。
- **重试**：无需自己写重试。客户端（方舟 SDK）在 `timeout` 内自动重试或按服务端要求暂停后重试；服务端会按负载"暂不处理、排队、指定客户端若干时间后重试"。用 `requests` 裸调时这部分要自己补。
- **并发**：文档建议"保持高并发推压，例如创建大量（10 万+）线程/协程"；单副本并发数 `workerNum ≈ 服务器 QPS 上限 × 平均时延`，副本数 ≈ 业务 QPS / 单机 QPS。Python 优先 `AsyncArk` + `asyncio.Queue` 协程池；Go 用 `arkruntime.WithBatchMaxParallel(n)` + `CreateBatchChatCompletion`；Java 用 `service.createBatchChatCompletion`，且**为 batch 单独建 `ArkService` 实例，不同接入点也不要复用**。
- 单副本内全局复用一个 client（单例），避免大量实例。
- 视觉理解批量（接入点模式）：图片/视频可用 TOS 链接（推荐）、其他可访问链接、Base64；链接需长期可用（推荐 7 天），TOS 预签名默认 1 小时，需设 `expires=604800`。

---

## 4. 批量(Job) API：离线任务

### 4.1 前提与 JSONL 输入文件格式

前提：
1. 开通目标模型服务。
2. 开通 TOS 并创建存储桶，**region 必须是华北 2（北京）`cn-beijing`**，输入桶与输出桶都要在该地域且与任务同一账号。
3. SDK 方式需要：TOS SDK（`pip install tos`）、火山引擎 SDK（`volcenginesdkcore` + `volcenginesdkark`）、Access Key（示例代码从 `VOLC_ACCESSKEY` / `VOLC_SECRETKEY` 环境变量读取）。

**输入行格式**（每行一个 JSON 对象）

```jsonl
{"custom_id": "request-1", "body": {"messages": [{"role": "user", "content": "天空为什么这么蓝？"}], "max_tokens": 1000, "top_p": 1, "temperature": 0.7}}
{"custom_id": "request-2", "body": {"messages": [{"role": "system", "content": "You are an unhelpful assistant."}, {"role": "user", "content": "天空为什么这么蓝？"}], "thinking": {"type": "disabled"}}}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `custom_id` | string | 是 | **文件内唯一**，用于把结果行对回请求行（结果顺序不保证） |
| `body` | object | 是 | 与底层模型 API 的 request body 一致的合法 JSON Object：对话用 Chat API 请求体（`messages`、`max_tokens`、`thinking`、`temperature`、`top_p` …），文本向量化用 `{"input": ["天很蓝","海很深"]}`，图像向量化用 `{"input": [{"type":"text","text":"…"},{"type":"image_url","image_url":{"url":"…"}}]}` |

- `body` 里**不填 `model`**：模型在任务级 `ModelReference` 指定；文档示例中也没有 `model` 字段。
- 每条请求独立发送、独立收到结果；多条共用同一 system prompt 也要每行都写。
- 多模态：Job 教程原文"支持 TOS（火山引擎对象存储）链接，不支持其他链接和 Base64 编码"，链接需长期可用（推荐 7 天预签名）。（接入点模式的限制更宽，见 §3。）
- 文件限制：默认单文件最大 **5 GB**（可工单提额）；"单个文件只能包含一个批量推理接入点的请求"（文档原文）。⚠ 文档未说明：单文件**行数**上限。
- 上传：普通上传 ≤ 5 GB；> 5 GB 走分片上传（最大 48.8 TB，单片 4 MB~5 GB，最多 10000 片，建议 50 MB~1 GB）；控制台分片上传最大 50 GB。
- 官方提供 `jsonl_linter.py` 校验脚本（指南页附件），任务因格式错误会整体 `Failed`（失败通知示例："第361行非json数据"）。

### 4.2 管控面请求形态与签名

所有 Job 接口都是**管控面** Action：

```
POST https://ark.cn-beijing.volcengineapi.com/?Action=<ActionName>&Version=2024-01-01
Host: ark.cn-beijing.volcengineapi.com
Content-Type: application/json; charset=UTF-8
X-Date: 20250115T094923Z
X-Content-Sha256: <body 的 SHA256 hex>
Authorization: HMAC-SHA256 Credential=<AK>/<yyyymmdd>/cn-beijing/ark/request, SignedHeaders=host;x-content-sha256;x-date, Signature=<sig>

{ ...JSON body... }
```

- `Action` 与 `Version` 走 **Query 参数**，业务参数走 **JSON body**（`ResumeBatchInferenceJob` 的文档示例把 `Id` 放在 Query 里且 body 为 `{}`，其他接口放 body；见 §4.5）。
- 签名：火山引擎通用签名 v4（文档 6369/67269），Service=`ark`，Region=`cn-beijing`。**不支持 API Key**（每页均写"本接口仅支持 Access Key 鉴权"）。官方口径：自行实现签名"实现成本高，不推荐"，用 SDK。
- 响应统一外壳：`{"ResponseMetadata": {"RequestId", "Action", "Version", "Service": "ark", "Region": "cn-beijing"}, "Result": {...}}`。Python SDK 返回的对象字段是 snake_case（如 `resp.id`、`items[].status.phase`）。
- ⚠ 文档自相矛盾：`StopBatchInferenceJob` 页的请求示例 Host 写成 `open.volcengineapi.com`，其余页面与《Base URL 及鉴权》均为 `ark.cn-beijing.volcengineapi.com`。以后者为准。

SDK 客户端初始化（后续 Python 示例共用）：

```python
import os
import volcenginesdkcore, volcenginesdkark

conf = volcenginesdkcore.Configuration()
conf.ak = os.environ["VOLC_ACCESSKEY"]
conf.sk = os.environ["VOLC_SECRETKEY"]
conf.region = "cn-beijing"
conf.client_side_validation = True
volcenginesdkcore.Configuration.set_default(conf)
ark = volcenginesdkark.ARKApi(volcenginesdkcore.ApiClient(conf))
```

### 4.3 CreateBatchInferenceJob
**Endpoint**: `POST https://ark.cn-beijing.volcengineapi.com/?Action=CreateBatchInferenceJob&Version=2024-01-01`
**用途**: 创建离线批量推理任务。带**幂等控制**：同一用户 + `ProjectName` + 输入桶 + 输入 ObjectKey 只允许一个活跃任务（排队或运行），重复提交报错并在错误信息里带上已存在任务的 ID（文档原文，未实测）。

**关键参数**（JSON body）
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `Name` | string | 是 | — | 任务名，控制台与查询接口里的标识 |
| `InputFileTosLocation.BucketName` | string | 是 | — | 输入桶，必须 `cn-beijing` |
| `InputFileTosLocation.ObjectKey` | string | 是 | — | JSONL 文件完整 object key，如 `input/data.jsonl` |
| `OutputDirTosLocation.BucketName` | string | 是 | — | 输出桶，与输入同地域 |
| `OutputDirTosLocation.ObjectKey` | string | 是 | — | 输出**文件夹**，建议以 `/` 结尾，如 `output/` |
| `ModelReference.FoundationModel.Name` | string | 二选一 | — | 基础模型名。⚠ 文档自相矛盾：参数表示例为 `doubao-seed-2-1-pro-260628`（带日期），但 SDK 示例 `MODEL_NAME="doubao-seed-2-1-pro"` + `MODEL_VERSION="260628"`，List 响应示例 `name: doubao-seed-1-8`, `model_version: 251228`（不带日期）。以"Name 不带日期、日期放 ModelVersion"为优先尝试 |
| `ModelReference.FoundationModel.ModelVersion` | string | 是（选 FoundationModel 时） | — | 版本号，如 `260628` |
| `ModelReference.CustomModelId` | string | 二选一 | — | 定制（精调）模型 ID，与 `FoundationModel` **需且仅需指定其一** |
| `CompletionWindow` | string | 否 | ⚠ 文档未说明默认值（响应示例出现 `28d`） | 最大等待时间，超过则自动终止；"常见取值如 `1d`" |
| `Description` | string | 否 | — | 任务描述 |
| `ProjectName` | string | 否 | `default` | IAM 项目名 |
| `Tags` | object[] | 否 | — | `[{Key, Value}]`，用于分组与计费分摊 |
| `DryRun` | boolean | 否 | false | true 只校验参数与权限，不创建 |

**示例请求**

```bash
# 签名头用占位符；实际请用 SDK 或签名工具生成
curl -X POST 'https://ark.cn-beijing.volcengineapi.com/?Action=CreateBatchInferenceJob&Version=2024-01-01' \
  -H 'Content-Type: application/json' \
  -H 'Host: ark.cn-beijing.volcengineapi.com' \
  -H 'X-Date: <YYYYMMDDTHHMMSSZ>' \
  -H 'X-Content-Sha256: <sha256-of-body>' \
  -H 'Authorization: HMAC-SHA256 Credential=<AK>/<YYYYMMDD>/cn-beijing/ark/request, SignedHeaders=host;x-content-sha256;x-date, Signature=<sig>' \
  -d '{
    "Name": "demo",
    "ProjectName": "default",
    "InputFileTosLocation":  {"BucketName": "input-bucket",  "ObjectKey": "input/data.jsonl"},
    "OutputDirTosLocation":  {"BucketName": "output-bucket", "ObjectKey": "output/"},
    "ModelReference": {"FoundationModel": {"Name": "doubao-seed-2-1-pro", "ModelVersion": "260628"}},
    "CompletionWindow": "1d"
  }'
```

```python
req = volcenginesdkark.CreateBatchInferenceJobRequest(
    name="demo",
    project_name="default",
    input_file_tos_location=volcenginesdkark.InputFileTosLocationForCreateBatchInferenceJobInput(
        bucket_name="input-bucket", object_key="input/data.jsonl"),
    output_dir_tos_location=volcenginesdkark.OutputDirTosLocationForCreateBatchInferenceJobInput(
        bucket_name="output-bucket", object_key="output/"),
    model_reference=volcenginesdkark.ModelReferenceForCreateBatchInferenceJobInput(
        foundation_model=volcenginesdkark.FoundationModelForCreateBatchInferenceJobInput(
            name="doubao-seed-2-1-pro", model_version="260628")),
)
resp = ark.create_batch_inference_job(req)
print(resp.id)          # 形如 bi-20260112213907-*****
```

**示例响应**: `{"ResponseMetadata": {...}, "Result": {"Id": "bi-20260112213907-*****"}}`

**注意事项**
- 输出实际落在 `{OutputDirTosLocation.ObjectKey}{Id}/output/results.jsonl` 与 `{...}{Id}/error/errors.jsonl`（§4.7），所以多个任务可以共用一个输出目录。
- 不同 `ProjectName` 的同一输入文件不受幂等限制。

### 4.4 ListBatchInferenceJobs / GetBatchInferenceJob

**ListBatchInferenceJobs**
**Endpoint**: `POST …/?Action=ListBatchInferenceJobs&Version=2024-01-01`
**用途**: 分页列出任务，可按 ID、名称、状态、模型、标签筛选。查单个任务状态时用 `Filter.Ids=[id]` 或直接用 Get。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `Filter.Ids` | string[] | 否 | — | 任务 ID 列表 |
| `Filter.Name` | string | 否 | — | 名称模糊匹配 |
| `Filter.Phases` | string[] | 否 | — | `Queued` / `Running` / `Completed` / `Terminating` / `Terminated` / `Failed`（注意：筛选枚举**不含** `Initializing`，但状态字段会返回它） |
| `Filter.FoundationModels` | object[] | 否 | — | `[{Name, ModelVersions: []}]` |
| `Filter.CustomModelIds` | string[] | 否 | — | |
| `TagFilters` | object[] | 否 | — | `[{Key, Values: []}]` |
| `PageNumber` / `PageSize` | integer | 否 | 1 / 10 | PageSize [1, 100] |
| `SortBy` / `SortOrder` | string | 否 | — | `CreateTime` / `UpdateTime`；`Asc` / `Desc` |
| `ProjectName` | string | 否 | `default` | |

响应 `Result`: `{Items: [<任务对象>], PageNumber, PageSize, TotalCount}`。

**GetBatchInferenceJob**
**Endpoint**: `POST …/?Action=GetBatchInferenceJob&Version=2024-01-01`，body `{"Id": "bi-…"}`
**用途**: 单任务详情；比 List 多返回 `ErrorFileTosLocation`（错误文件位置）。

任务对象字段（Get 的 `Result` 顶层 / List 的 `Items[]`）：

| 字段 | 说明 |
|---|---|
| `Id`, `Name`, `Description`, `ProjectName`, `Tags[]` | 基本信息 |
| `InputFileTosLocation{BucketName, ObjectKey}`, `OutputDirTosLocation{…}` | 输入/输出位置 |
| `ErrorFileTosLocation{BucketName, ObjectKey}` | 仅 Get 返回；错误文件位置 |
| `ModelReference{CustomModelId, FoundationModel{Name, ModelVersion}}` | 模型 |
| `RequestCounts{Total, Completed, Failed}` | 请求计数（**完成率 = Completed / Total**；排队时可能全 0） |
| `Status{Phase, PhaseTime, Message}` | 状态、状态更新时间（RFC 3339）、补充说明/失败原因 |
| `CompletionWindow`, `ExpireTime` | 最大等待时长与到期时间（示例：`28d` → ExpireTime = CreateTime + 28 天） |
| `CreateTime`, `UpdateTime` | RFC 3339 |

```python
# 查单任务状态（SDK 示例来自官方指南）
flt = volcenginesdkark.FilterForListBatchInferenceJobsInput(ids=["bi-20260112213907-*****"])
resp = ark.list_batch_inference_jobs(volcenginesdkark.ListBatchInferenceJobsRequest(filter=flt))
job = resp.items[0]
print(job.status.phase, job.request_counts.completed, "/", job.request_counts.total)
```

⚠ 文档未说明：Get 的 Python SDK 方法名/请求类名（指南只给了 Create 与 List 的 SDK 示例）。按 SDK 命名规律应为 `ark.get_batch_inference_job(volcenginesdkark.GetBatchInferenceJobRequest(id=...))`，未实测。

### 4.5 Update / Stop / Resume / Delete

| Action | body 参数 | 返回 `Result` | 说明 |
|---|---|---|---|
| `UpdateBatchInferenceJob` | `Id`(必) `Name` `Description` `DryRun` | `{}` | 只能改名称与描述 |
| `StopBatchInferenceJob` | `Id`(必) `DryRun` | `{}` | 运行中 → `Terminating` → `Terminated` |
| `ResumeBatchInferenceJob` | `Id`(必) | `{"Id": "bi-…"}` | 重启 `Terminated` / `Failed` 的任务。文档示例把 `Id` 放在 **Query** 里（`?Action=ResumeBatchInferenceJob&Version=2024-01-01&Id=bi-…`）且 body 为 `{}`；参数表未区分位置。⚠ 文档未说明 Resume 是否只重跑失败/未完成的行还是全量重跑 |
| `DeleteBatchInferenceJob` | `Id`(必) `DryRun` | `{}` | 删除任务记录；⚠ 文档未说明能否删除运行中任务、是否连带删除 TOS 输出 |

`DryRun=true` 只做参数/权限预检。所有这些接口都没有特有返回参数，成功只看 `ResponseMetadata` 里有无 `Error`（公共错误码见文档 1299023，本文件不展开）。

```bash
curl -X POST 'https://ark.cn-beijing.volcengineapi.com/?Action=StopBatchInferenceJob&Version=2024-01-01' \
  -H 'Content-Type: application/json' -H 'Host: ark.cn-beijing.volcengineapi.com' \
  -H 'X-Date: <…>' -H 'X-Content-Sha256: <…>' -H 'Authorization: HMAC-SHA256 Credential=<AK>/<date>/cn-beijing/ark/request, SignedHeaders=host;x-content-sha256;x-date, Signature=<…>' \
  -d '{"Id": "bi-20260112213907-*****"}'
```

### 4.6 任务状态机

```
Queued ──► Initializing ──► Running ──► Completed
                              │
                              ├──(Stop / 到期 / 系统)──► Terminating ──► Terminated ──┐
                              │                                                       ├─ Resume ─► 重新排队
                              └──(输入文件校验失败、超时等)──────────► Failed ─────────┘
```

| Phase | 含义（文档口径） |
|---|---|
| `Queued` | 提交成功，因账号下并发任务数达上限等原因排队 |
| `Initializing` | 初始化中 |
| `Running` | 运行中 |
| `Completed` | 所有请求处理完毕（**包含失败行**，失败行进 errors.jsonl，任务仍是 Completed） |
| `Terminating` | 取消中（到期、系统原因或手动 Stop） |
| `Terminated` | 已终止 |
| `Failed` | 任务级失败，"通常由输入文件校验失败"、"超时等原因" |

`Terminated` / `Failed` 可 `Resume`；`Completed` 不可（文档未提及 Completed 后 Resume 的行为）。

### 4.7 输出文件位置与行格式

| 文件 | TOS 路径 | 内容 |
|---|---|---|
| `results.jsonl` | `{OutputDirectory}/{batch_job_id}/output/results.jsonl` | 成功请求的集合；**顺序可能与输入不一致，用 `custom_id` 对齐** |
| `errors.jsonl` | `{OutputDirectory}/{batch_job_id}/error/errors.jsonl` | 失败请求，每个失败请求一行 |

成功行：

```json
{"id": "0217…4984d6", "custom_id": "request-2", "error": null,
 "response": {"request_id": "0217…4984d6", "status_code": 200,
   "body": {"id": "…", "object": "chat.completion", "created": 1768279310, "model": "doubao-seed-2-1-pro-260628", "service_tier": "default",
            "choices": [{"index": 0, "finish_reason": "stop", "logprobs": null,
                         "message": {"role": "assistant", "content": "…", "reasoning_content": "…"}}],
            "usage": {"prompt_tokens": 49, "completion_tokens": 210, "total_tokens": 259,
                      "prompt_tokens_details": {"cached_tokens": 0}, "completion_tokens_details": {"reasoning_tokens": 169}}}}}
```

失败行：

```json
{"id": "batch-req-456", "custom_id": "request-2", "response": null,
 "error": {"code": "AccessDenied", "type": "Forbidden", "message": "The request failed because you do not have access to the requested resource."}}
```

即：每行 `{id, custom_id, response: {request_id, status_code, body} | null, error: {code, type, message} | null}`，`response.body` 就是对应在线 API 的完整响应体。

下载：TOS SDK `client.get_object_to_file(bucket, f"{output_key}{job_id}/output/results.jsonl", local_path)`；两文件任一可能不存在（全成功则无 errors.jsonl），要分别 try。

### 4.8 配额、时长与计费

- **TPD 配额**：按模型设定，账户下所有子账号、同一模型的所有版本共享；与在线推理限流隔离；超配额任务"在平台资源空闲时尝试继续执行"（不是直接失败）。具体数值以控制台为准，可工单提额。
- **任务数**：单项目 7 天内最多提交 **5000** 个任务；单项目同时 `Running` 最多 **20** 个，多余的排 `Queued`；实际并发还受平台总体资源与调度影响。
- **文件**：单任务文件默认 5 GB。
- **时长**：由 `CompletionWindow` 控制，到期自动进入 `Terminating`；文档只给出 `1d` 作为"常见取值"、响应示例出现 `28d`，⚠ 文档未说明可选取值范围与上限。
- **计费**：输入输出单价为在线推理 50%，命中透明前缀缓存的输入再降 60%（具体价格见文档 1544106《模型价格》，本文件不抄价目）。同一 `Tags` 可用于计费分摊。

### 4.9 （可选）SNS 完成/失败通知

用火山引擎消息通知服务（SNS）订阅事件 `BatchJobFinished` / `BatchJobFailed`（需工单"SNS 开白"）。主题发布者选账号 `2100444922`、服务 `ark`；订阅推送类型 HTTP/HTTPS 或函数服务；首次需回调 `SubscribeURL` 确认。

通知 `Message` 为 JSON 字符串：`{EventID, Project, EventName, EventTime, AccountID, JobInfo{JobID, JobName, Message, FailNum, TotalNum, SuccessNum, FailFileTOSPath{BucketName, ObjectKey}, SuccessFileTOSPath{BucketName, ObjectKey}}}`；失败事件的 `JobInfo` 只有 `JobID, JobName, Message`（失败原因）。

---

## 5. 应用(Bot) API

### 5.1 与普通 Chat 的差异

| 项 | 普通 Chat (`/api/v3/chat/completions`) | Bot (`/api/v3/bots/chat/completions`) |
|---|---|---|
| `model` | Model ID 或 `ep-` 接入点 | **应用 ID（Bot ID）**，在控制台应用实验室 / 《获取 Bot ID》(1267885) 获取。⚠ 输入文档未给出 ID 格式示例 |
| 鉴权 | API Key / Access Key | 文档页写"支持 API Key 鉴权"；Access Key 需走 SDK |
| 工具 | 请求里声明 `tools` | 插件（联网、知识库、群聊角色…）在应用配置里；请求仍可带 `tools`（function） |
| 额外请求参数 | — | `metadata`（群聊角色配置、联网用户地理信息、意图信号） |
| 用量字段 | `usage` | **`bot_usage`**（`model_usage[]` 按 endpoint 分、`action_usage[]`、`action_details[]`）。⚠ 文档未说明响应里是否同时还有顶层 `usage` |
| 引用 | — | **`references[]`**：插件返回的引用，结构按插件而异（§5.3） |
| `service_tier` | 有 | 响应参数表未列出 |

### 5.2 Endpoint 详解

### 应用对话补全
**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/v3/bots/chat/completions`
**用途**: 调用应用实验室里配置好的应用；应用内部再去调模型接入点和插件。

**关键参数**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | — | Bot ID |
| `messages` | object[] | 是 | — | `system` / `user`（可带 `name`）/ `assistant`（content 与 tool_calls 至少其一）/ `tool`（`content` + `tool_call_id` 必填）；content 支持 string 或 `text` / `image_url` 多模态数组（**未列出 `video_url`**） |
| `stream` | boolean | 否 | false | true 时 SSE，以 `data: [DONE]` 结束 |
| `stream_options.include_usage` | boolean | 否 | false | true 时 `[DONE]` 前多一个 `choices=[]` 的块承载整段 usage |
| `thinking.type` | string | 否 | `enabled` | `enabled` / `disabled` / `auto` |
| `max_tokens` | integer | 否 | 4096 | 参数表**未列出** `max_completion_tokens` |
| `stop` / `temperature` / `top_p` / `frequency_penalty` / `presence_penalty` / `logprobs` / `top_logprobs` / `logit_bias` | 同 Chat | 否 | null / 1 / 0.7 / 0 / 0 / false / 0 / null | 同 Chat |
| `tools` | object[] | 否 | null | `type: "function"`；`function.name/description/parameters` 三者在本页都标必选 |
| `metadata.group_chat_config.characters[]` | object[] | 群聊应用必填 | — | `{name, system_prompt, model_desc: {endpoint_id}}`，运行时动态传入角色 |
| `metadata.group_chat_config.description` | string | 否 | null | 群聊场景描述 |
| `metadata.group_chat_config.user_name` | string | 否 | `用户` | "我"扮演的角色名 |
| `metadata.target_character_name` | string | 否 | null | 本轮要发言的角色，必须在 `characters` 里 |
| `metadata.user_info` | **string** | 否 | null | 联网应用用；**可反序列化成 JSON 的字符串**，必须含 `city` 与 `district`，如 `"{\"city\":\"北京\",\"district\":\"海淀区\"}"` |
| `metadata.emit_intention_signal_extra` | **string** | 否 | `"false"` | `"true"` 时中途返回 intention 状态"正在搜索"（字符串，不是布尔） |

**示例请求**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/bots/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "<BOT_ID>",
    "messages": [{"role": "user", "content": "北京今天天气怎么样？"}],
    "metadata": {"user_info": "{\"city\":\"北京\",\"district\":\"海淀区\"}"}
  }'
```

```python
import os, json, requests
r = requests.post(
    "https://ark.cn-beijing.volces.com/api/v3/bots/chat/completions",
    headers={"Authorization": f"Bearer {os.environ['ARK_API_KEY']}"},
    json={
        "model": os.environ["ARK_BOT_ID"],
        "messages": [{"role": "user", "content": "北京今天天气怎么样？"}],
        "metadata": {"user_info": json.dumps({"city": "北京", "district": "海淀区"}, ensure_ascii=False)},
    },
    timeout=120,
)
data = r.json()
print(data["choices"][0]["message"]["content"])
for ref in data.get("references", []):        # 联网插件时是 SearchDocument 结构
    print(ref.get("site_name"), ref.get("title"), ref.get("url"))
print(data["bot_usage"]["model_usage"])
```

⚠ 未实测：用 `openai` SDK 调 Bot 需把 `base_url` 设为 `https://ark.cn-beijing.volces.com/api/v3/bots`（SDK 自动拼 `/chat/completions`），文档未提及此用法；官方 `volcenginesdkarkruntime` 是否有 bot 专用方法，输入文档未涉及。

**示例响应**（非流式；字段名与层级按文档）

```json
{
  "id": "…", "object": "chat.completion", "created": 1730000000, "model": "doubao-seed-…",
  "choices": [{
    "index": 0, "finish_reason": "stop",
    "message": {"role": "assistant", "content": "…", "reasoning_content": null, "tool_calls": null},
    "logprobs": null, "moderation_hit_type": null
  }],
  "references": [ { "…": "见 §5.3，按插件不同" } ],
  "bot_usage": {
    "model_usage": [{"name": "<模型 ID>", "prompt_tokens": 1200, "completion_tokens": 300, "total_tokens": 1500}],
    "action_usage": [{"action_name": "content_plugin", "count": 1}],
    "action_details": [{
      "name": "content_plugin", "count": 1,
      "tool_details": [{"name": "<工具名>", "input": {}, "output": {}, "created_at": 1730000000, "completed_at": 1730000003}]
    }]
  },
  "metadata": null
}
```

- `bot_usage.model_usage[].prompt_tokens` **包含插件返回给模型的内容**，所以比用户输入大得多。
- `action_usage[].action_name` / `action_details[].name` 是插件分类名（文档示例 `content_plugin` 内容插件）；具体工具名在 `tool_details[].name`。
- 响应的 `metadata` 结构与请求相同（回显）。

**流式返回**：`object` 为 `chat.completion.chunk`，`choices[].delta.{role, content, reasoning_content, tool_calls[]{index, id, type, function}}`；`bot_usage`、`references`、`metadata` 同样列在流式响应字段里。⚠ 文档未说明 `references` / `bot_usage` 在流式下出现在哪个 chunk（首块、末块还是每块），也未说明 `emit_intention_signal_extra` 的"正在搜索"信号具体以什么字段/事件下发。

### 5.3 references：联网插件 / 知识库插件数据结构

`references` 是 `object[]`，元素结构由触发的插件决定，文档只给了两种：

**联网插件 → `SearchDocument`**（1285209）

| 字段 | 类型 | 说明 |
|---|---|---|
| `site_name` | string | 站点名，如"抖音百科" |
| `summary` | string | 对该搜索结果的总结文本 |
| `publish_time` | string | 发布时间 |
| `title` | string | 标题（部分内容源才有） |
| `url` | string | 引用链接（部分内容源才有） |
| `mobile_url` | string | 移动端链接（部分内容源才有） |
| `logo_url` | string | 站点 logo（部分内容源才有） |
| `cover_image` | CoverImage `{url, width, height}` | 封面图（部分内容源才有） |
| `extra` | ExtraContent | 非通用字段；目前只有 `weather_card_data.display`，含 `aqi`、`aqiForecast`、`aqiForecastHourly`、`aqi_url`、`city`、`condition`、`condition_url`、`seven_forecast_data`（均为 object/string，内部结构文档未展开） |

**知识库插件 → `KnowledgeBaseChunk`**（1285210）

| 字段 | 类型 | 说明 |
|---|---|---|
| `collection_name` | string | 知识库 Collection 名 |
| `project` | string | Collection 所在 project |
| `doc_id` / `doc_name` / `doc_type` / `doc_title` | string | 文档标识、名称、类型、标题 |
| `chunk_id` / `chunk_title` | string | 分块 ID 与标题 |

⚠ 文档未说明：`KnowledgeBaseChunk` 里**没有分块正文字段**（如 `content`），实际是否返回正文待实测；也未说明 `references[]` 元素上是否带区分插件类型的字段（如 `type`），解析时建议按"有 `chunk_id` 即知识库、有 `site_name`/`url` 即联网"做鸭子类型判断。

### 5.4 智能体插件 API（Beta）

来源 1263406，页面顶部标注 **"Beta 版本，如遇到问题请联系 PDSA"**。这两个接口把"联网"拆成两步可单独调用，请求/响应类型为 `MaasChatRequest` / `MaasChatResponse`（老 MaaS 协议）。

| 接口 | 路径 | 作用 |
|---|---|---|
| Search Intention | `POST /api/v2/action/SearchIntention` | 新鲜度 + 检索意图判断，返回是否需要联网 |
| Search Summary | `POST /api/v2/action/SearchSummary` | 执行检索并基于结果生成摘要 |

⚠ 文档未说明：这两个 `/api/v2/action/*` 路径对应的 **Base URL**（页面只写"鉴权方式：SDK 鉴权"并链到《Base URL 及鉴权》；`/api/v2` 不在该页列出的 `/api/v3` 数据面与管控面之内）。

SearchIntention 请求关键字段：`tools[0].type="SearchIntention"`，`tools[0].options.keywords[]`（可选），`tools[0].options.result_mapping`（必填，`{"需要": true, "不需要": false, ...}`，把模型回答映射成布尔），`messages[]`（role 固定 `user`，content 里要自带"请回答需要或不需要"的引导语）。响应 `choices[0].message.content` 为"需要"/"不需要"等文本，`usage` 三个 token 字段。

SearchSummary 请求关键字段：`tools[0].type="SearchSummary"`，`options.keywords[]`，`options.action_name`（默认 `"WebBrowsing"`，目前只支持它），`options.summary_top_k`（默认 5），`tools[0].user_info.{city, district}`（表中标必选）。响应 `choices[0].message.content` 为摘要文本。

⚠ 文档自相矛盾：参数表把用户消息写成 `tools[*].message.role/content`，示例却用顶层 `messages`；SearchSummary 示例又写成单数 `message`；示例 JSON 里还有中文逗号（`True，`）。以顶层 `messages` 为优先尝试，未实测。

---

## 6. Plan 入口（Coding Plan / Agent Plan）可用性

| 能力 | 标准 `/api/v3` | Coding Plan `/api/coding/v3` | Agent Plan `/api/plan/v3` |
|---|---|---|---|
| 批量(Chat) `/batch/chat/completions` | ✅（model 填 `ep-bi-` 批量接入点） | ⚠ 文档未说明；Coding Plan 文档口径"仅限 AI 编程工具内使用，不可用于 API 调用"，且 model 只接受小写 Model Name、无接入点概念 | ⚠ 文档未说明；同样没有接入点概念 |
| 批量(Job) 管控面 Action | ✅（AK/SK 签名） | ❌ 与 Plan 无关：管控面只认 AK/SK，任务按模型后付费计费，不走套餐额度 | ❌ 同左 |
| 应用(Bot) `/bots/chat/completions` | ✅（model 填 Bot ID） | ⚠ 文档未说明 | ⚠ 文档未说明 |
| 智能体插件 `/api/v2/action/*` | ⚠ Base URL 未说明 | ⚠ 文档未说明 | ⚠ 文档未说明 |

结论：本文件三类接口目前只能按**标准入口 + 方舟 API Key / AK-SK** 使用。控制台与 Plan 文档反复警告"请勿使用 `/api/v3`，接入会产生额外费用"——反过来说，批量与 Bot 走 `/api/v3` 就是按量后付费，不消耗 Coding/Agent Plan 额度。

---

## 来源页面

| 标题 | URL | 文档更新时间 |
|---|---|---|
| 批量(Chat) API | https://www.volcengine.com/docs/82379/1528783 | 2026-08-17 |
| 批量推理（指南） | https://www.volcengine.com/docs/82379/1399517 | 2026-08-17 |
| 创建批量推理任务 CreateBatchInferenceJob | https://www.volcengine.com/docs/82379/1339603 | 2026-08-27 |
| 获取批量推理任务列表 ListBatchInferenceJobs | https://www.volcengine.com/docs/82379/1339606 | 2026-08-27 |
| 获取批量推理任务 GetBatchInferenceJob | https://www.volcengine.com/docs/82379/1339609 | 2026-08-27 |
| UpdateBatchInferenceJob | https://www.volcengine.com/docs/82379/1339610 | 2025-05-23 |
| DeleteBatchInferenceJob | https://www.volcengine.com/docs/82379/1339613 | 2025-05-23 |
| StopBatchInferenceJob | https://www.volcengine.com/docs/82379/1339616 | 2026-08-12 |
| ResumeBatchInferenceJob | https://www.volcengine.com/docs/82379/1433715 | 2025-05-23 |
| 应用(bot) API | https://www.volcengine.com/docs/82379/1526787 | 2026-08-12 |
| 智能体插件 API | https://www.volcengine.com/docs/82379/1263406 | 2026-08-17 |
| 联网插件 数据结构 | https://www.volcengine.com/docs/82379/1285209 | 2025-05-23 |
| 知识库插件 数据结构 | https://www.volcengine.com/docs/82379/1285210 | 2025-05-23 |
| Base URL 及鉴权 | https://www.volcengine.com/docs/82379/1298459 | 2026-06-23 |
| 推理方式概述（批量推理仅自定义接入点支持） | https://www.volcengine.com/docs/82379/2123245 | 2026-07-07 |
| Coding Plan 快速开始（Base URL 警告） | https://www.volcengine.com/docs/82379/1928261 | 2026-08-28 |
