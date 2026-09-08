# 智能体、助手与知识库（Agents / Assistant / Knowledge Base）参考

覆盖 bigmodel.cn 除基础 Chat Completions 外的三大能力：官方预置智能体（Agents）、对话式助手（Assistant）、GLM 全模态知识库（RAG），以及低代码 Agentic 应用的调用接口。

**通用约定**：Base URL `https://open.bigmodel.cn/api/`，本文 path 均相对该 base；鉴权用请求头 `Authorization: Bearer <API_KEY>`（[获取地址](https://bigmodel.cn/usercenter/proj-mgmt/apikeys)）。若要自建 embedding+rerank 检索管线而非用本文第三节的托管知识库，见 `references/tools.md`。

> 本文是内置智能体 / Assistant API / Agentic 应用调用部分。
> 托管知识库与 RAG 检索见 [`knowledge-rag.md`](knowledge-rag.md)。

## 本文目录

- [一、智能体 Agents API](#一智能体-agents-api)：[1.对话](#1-智能体对话) [2.异步结果](#2-智能体异步结果) [3.对话历史](#3-智能体对话历史)
- [二、助手 Assistant API](#二助手-assistant-api)：[4.对话](#4-助手对话) [5.列表](#5-助手列表) [6.会话列表](#6-助手会话列表)
- [三、GLM 全模态知识库 / RAG](#三glm-全模态知识库--rag-检索增强)
  - [知识库管理](#知识库管理)：[7.创建](#7-创建知识库) [8.列表](#8-知识库列表) [9.详情](#9-知识库详情) [10.编辑](#10-编辑知识库) [11.删除](#11-删除知识库) [12.用量](#12-知识库使用量)
  - [文档管理](#文档管理)：[13.列表](#13-文档列表) [14.传文件](#14-上传文件文档) [15.传URL](#15-上传url文档) [16.解析图片](#16-解析文档图片) [17.详情](#17-文档详情) [18.删除](#18-删除文档) [19.重新向量化](#19-重新向量化)
  - [检索/问答](#知识库检索--问答)：[20.个人库检索](#20-知识库检索个人知识库) [21.全模态检索](#21-全模态知识库检索) [22.问答Agent](#22-问答-agent-对话流式)
  - [检索结果怎么接入对话](#知识库检索结果怎么接入对话)
- [四、Agentic 应用调用](#四agentic-应用调用)：[23.输入参数](#23-获取智能体输入参数) [24.建会话](#24-创建新会话) [25.推理](#25-推理接口调用应用) [26.传文件](#26-文件上传应用专用) [27.文件状态](#27-获取文件解析状态) [28.切片位置](#28-知识库切片引用位置信息) [29.推荐问题](#29-推荐问题接口)

---

## 一、智能体 Agents API

官方预置的一批"专业智能体"（翻译、PPT 生成、AI 画图、票据/服装识别、教育解题、视频模板），用统一的 `agent_id` + `custom_variables` 模式调用，无需自己设计 Prompt。

### 1. 智能体对话

**Endpoint**: `POST /v1/agents`
**用途**: 与指定智能体对话，同步/流式均支持。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `agent_id` | string | 是 | - | `general_translation`(翻译)/`slides_glm_agent`(PPT)/`ai_drawing_agent`(画图)/`receipt_recognition_agent`(票据)/`clothes_recognition_agent`(服装)/`intelligent_education_solve_agent`(教育解题)/`vidu_template_agent`(视频模板) |
| `messages` | array | 是 | - | `{role: system/user/assistant, content}`；content 为字符串或多模态数组（`type: text/file_id/file_url/image_url`） |
| `stream` | boolean | 否 | `false` | 是否流式 |
| `custom_variables` | object | 否 | - | 各智能体扩展参数不同，需查各自文档；`general_translation` 示例见下 |

`general_translation` 的 `custom_variables`：`source_lang`(源语言,默认auto)、`target_lang`(目标语言,默认zh-CN)、`glossary`(术语表id)、`strategy`(策略,默认general,可选general/paraphrase/two_step/three_step/reflection/cot)、`strategy_config.general.suggestion`(风格建议)、`strategy_config.cot.reason_lang`(理由语言,from/to,默认to)。

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/v1/agents -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"general_translation","messages":[{"role":"user","content":"Hello, how are you?"}],"custom_variables":{"target_lang":"zh-CN"}}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/v1/agents",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"agent_id": "general_translation",
          "messages": [{"role": "user", "content": "Hello, how are you?"}],
          "custom_variables": {"target_lang": "zh-CN"}})
print(resp.json())
```

**示例响应**（已用真实 API 调用验证，2026-09；`general_translation`，输入 "Hello, how are you today?"）：

```json
{"id":"20260903150507d1397a8d3e6b4b0b","agent_id":"general_translation","status":"success",
 "choices":[{"index":0,"finish_reason":"stop",
   "messages":[{"role":"assistant","content":{"text":"你好，你今天怎么样？","type":"text"}}]}],
 "usage":{"prompt_tokens":12,"completion_tokens":11,"total_tokens":23,"total_calls":1}}
```

**注意事项**：`finish_reason` 可能是 `stop/length/sensitive/network_error`；耗时较长的智能体（生成文件类）会返回 `async_id`，需配合"异步结果"接口轮询；除 `general_translation` 外其他智能体的 `custom_variables` 字段需查各自文档，不要臆造。**重要（已用真实调用验证）**：`messages[].content` 不是纯字符串，而是一个 `{"type": "text"/"file_url"/"image_url"/"audio_url"/"video_url", "text"/"file_url"/...: ...}` 形式的对象——取文本要读 `content.text`，不能直接把 `content` 当字符串用（这是本文档早期版本的一个错误，已修正）。顶层还多一个 `status` 字段（如 `success`），以及 `usage.total_calls`；是否返回 `conversation_id` 因智能体而异，不要假设一定存在。

### 2. 智能体异步结果

**Endpoint**: `POST /v1/agents/async-result`
**用途**: 查询异步任务（`async_id`）的处理状态和结果，用于生成文件耗时较长的智能体。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `async_id` | string | 是 | 异步任务 ID，来自"智能体对话"响应 |
| `agent_id` | string | 是 | 需与发起时一致 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/v1/agents/async-result -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" -d '{"async_id":"async-xxx","agent_id":"slides_glm_agent"}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/v1/agents/async-result",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"async_id": "async-xxx", "agent_id": "slides_glm_agent"})
print(resp.json())
```

**示例响应**

```json
{"agent_id":"slides_glm_agent","async_id":"async-xxx","status":"success",
 "choices":[{"messages":[{"role":"assistant","content":[{"type":"file_url","file_url":"https://.../slides.pptx","tag_cn":"PPT文件","tag_en":"PPT File"}]}]}],
 "usage":{"total_tokens":1200}}
```

**注意事项**：`status` 为 `success/failed/pending`，需轮询直到非 `pending`；结果内容目前仅支持 `type=file_url`。

### 3. 智能体对话历史

**Endpoint**: `POST /v1/agents/conversation`
**用途**: 查询智能体对话历史，**官方文档明确说明目前仅支持 `slides_glm_agent`**（PPT 生成智能体）。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `agent_id` | string | 否* | 实际需传 `slides_glm_agent` |
| `conversation_id` | string | 否* | 对话 ID |
| `custom_variables.include_pdf` | boolean | 否 | 是否导出 PDF |
| `custom_variables.pages` | array | 否 | Slide 页信息 `{position, width, height}`（宽高单位 cm） |

\* schema 未标 required，但实际调用需传以定位会话。

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/v1/agents/conversation -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"slides_glm_agent","conversation_id":"conv-xxx","custom_variables":{"include_pdf":true}}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/v1/agents/conversation",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"agent_id": "slides_glm_agent", "conversation_id": "conv-xxx",
          "custom_variables": {"include_pdf": True}})
print(resp.json())
```

**示例响应**

```json
{"conversation_id":"conv-xxx","agent_id":"slides_glm_agent",
 "choices":[{"message":[{"role":"assistant","content":[{"type":"file_url","tag_cn":"PDF导出","file_url":"https://.../slides.pdf"}]}]}],
 "error":null}
```

**注意事项**：出错时 `error.code`/`error.message` 给出原因；`content` 支持 `file_url`/`image_url`。

---

## 二、助手 Assistant API

与上面 Agents API **不同的另一套体系**：`assistant_id` 对应平台预置的对话式助手（ChatGLM、数据分析、流程图、思维导图、AI 画图、AI 搜索、PPT 助手等），走更接近标准 Chat Completions 的形态（`model`+`messages`+`stream`），而非 `agent_id`+`custom_variables` 形态。两者是平台不同阶段推出的接口，覆盖能力有重叠，具体差异请以实际测试为准。

预置助手 `assistant_id` 列表：

| assistant_id | 名称 |
| --- | --- |
| `65940acff94777010aa6b796` | ChatGLM（官方，通用对话，默认） |
| `65a265419d72d299a9230616` | 数据分析（官方） |
| `664dd7bd5bb3a13ba0f81668` | 复杂流程图（官方） |
| `664e0cade018d633146de0d2` | 思维导图 MindMap（官方） |
| `6654898292788e88ce9e7f4c` | 提示词工程师（官方） |
| `66437ef3d920bdc5c60f338e` | AI画图（官方） |
| `659e54b1b8006379b4b2abd6` | AI搜索（官方） |
| `65d2f07bb2c10188f885bd89` | PPT助手（官方） |
| `663058948bb259b7e8a22730` | arXiv论文速读（官方） |
| `65a393b3619c6f13586246cd` | 程序员助手Sam（官方） |
| `65b356af6924a59d52832e54` | 网文写手（官方） |
| `668fdd45405f2e3c9f71f832` | 英语语法助手（官方） |

### 4. 助手对话

**Endpoint**: `POST /paas/v4/assistant`
**用途**: 与上表助手对话，支持流式（默认）/同步。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `assistant_id` | string | 是 | `65940acff94777010aa6b796` | 见上表 |
| `model` | string | 是 | `glm-4-assistant` | `glm-4-assistant`/`glm-4-alltools` |
| `messages` | array | 是 | - | **`role` 仅支持 `user`**（不接受 assistant/system 历史）；content 为字符串或多模态数组（text/image_url） |
| `conversation_id` | string | 否 | - | 传入以继续之前对话 |
| `stream` | boolean | 否 | 见下方警告 | 流式响应。**实测（2026-09-07）`glm-4-assistant` 只能 `stream: true`**：不传或传 `false` 都会返回 `1212 当前模型不支持SYNC调用方式`。文档声称默认 `true`，但实测不传就走同步并失败——请显式传 `true` |
| `request_id` | string | 否 | - | 6-64 位 |
| `user_id` | string | 否 | - | 终端用户ID，6-128 位 |
| `do_sample` | boolean | 否 | - | 是否稳定输出 |
| `attachments` | array | 否 | - | 附件列表 |
| `metadata` | object | 否 | - | 自定义元数据 |
| `extra_parameters.translate.{from,to}` | string | 否 | - | 翻译类扩展参数 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/assistant -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assistant_id":"65940acff94777010aa6b796","model":"glm-4-assistant","messages":[{"role":"user","content":"总结一下量子计算原理"}],"stream":true}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/paas/v4/assistant",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"assistant_id": "65940acff94777010aa6b796", "model": "glm-4-assistant",
          "messages": [{"role": "user", "content": "总结一下量子计算原理"}], "stream": True})  # 必须 true，见下
print(resp.json())
```

**示例响应**

```json
{"id":"resp-xxx","request_id":"req-xxx","created":1735689600,"model":"glm-4-assistant",
 "choices":[{"index":0,"message":{"role":"assistant","content":"量子计算利用叠加与纠缠……"},"finish_reason":"stop"}],
 "usage":{"prompt_tokens":15,"completion_tokens":120,"total_tokens":135}}
```

**注意事项**：**必须显式传 `stream: true`**——已用真实 API 验证（2026-09-07）：`glm-4-assistant` 不传 `stream` 或传 `false`，都会返回 `{"code":"1212","message":"当前模型不支持SYNC调用方式。"}`；只有 `true` 能拿到 `text/event-stream` 响应。官方文档把默认值写作 `true`，但实测省略该字段时走的是同步分支并直接失败，**照抄「同步调用」示例必然报错**；流式响应为 `text/event-stream`；`messages.role` 严格只允许 `user`，多轮上下文靠 `conversation_id` 维护而非传历史消息；`GLM-4.5V` 系列可能返回 `<think></think>`/`<|begin_of_box|>` 标签，`reasoning_content` 仅 `glm-4.5`/`glm-4.1v-thinking` 系列返回。

### 5. 助手列表

**Endpoint**: `POST /paas/v4/assistant/list`
**用途**: 查询指定或全部助手的详细配置、工具与元数据。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `assistant_id_list` | array\<string\> | 是 | `[]` | 空数组=查询所有 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/assistant/list -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" -d '{"assistant_id_list":[]}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/paas/v4/assistant/list",
    headers={"Authorization": "Bearer YOUR_API_KEY"}, json={"assistant_id_list": []})
print(resp.json())
```

**示例响应**

```json
{"success":true,"code":200,"msg":"ok",
 "data":[{"assistant_id":"65940acff94777010aa6b796","name":"ChatGLM","description":"嗨~我是清言……",
          "tools":["web_search"],"tags":[{"key":"category","label":"通用对话"}],"status":"active"}]}
```

**注意事项**：可作为动态发现助手能力（`tools`）的入口，无需硬编码清单。

### 6. 助手会话列表

**Endpoint**: `POST /paas/v4/assistant/conversation/list`
**用途**: 分页查询指定助手下的历史会话及 token 用量。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `assistant_id` | string | 是 | `65940acff94777010aa6b796` | 见助手列表 |
| `page` | integer | 否 | `1` | 页码 |
| `page_size` | integer | 否 | `5` | 1-100 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/paas/v4/assistant/conversation/list -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" -d '{"assistant_id":"65940acff94777010aa6b796","page":1,"page_size":10}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/paas/v4/assistant/conversation/list",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"assistant_id": "65940acff94777010aa6b796", "page": 1, "page_size": 10})
print(resp.json())
```

**示例响应**

```json
{"success":true,"code":200,"msg":"ok",
 "data":{"assistant_id":"65940acff94777010aa6b796",
   "conversation_list":[{"id":"conv-xxx","create_time":"2026-08-01T10:00:00Z",
     "usage":{"prompt_tokens":100,"completion_tokens":200,"total_tokens":300}}],
   "has_more":false}}
```

**注意事项**：`has_more=true` 时递增 `page` 继续拉取。

---

## 四、Agentic 应用调用

"应用"特指在智谱开放平台低代码工作台搭建的智能体应用/工作流（"我的智能体"列表页管理，对应一个 `app_id`）。典型调用顺序：`variables` 探明输入参数 → （对话类）`conversation` 建会话 → 需要传文件时先 `file_upload` 再 `file_stat` 确认解析完成 → `invoke` 推理接口获取结果 → 需要展示引用来源时用 `slice_info`；`history_session_record` 获取推荐问题。

### 23. 获取智能体输入参数

**Endpoint**: `GET /llm-application/open/v2/application/{app_id}/variables`
**用途**: 获取应用定义的输入参数（表单字段），用于外部系统动态构造调用表单。

**关键参数**：`app_id`（路径，必填，从"我的智能体"列表页获取）。

**示例请求**

```bash
curl https://open.bigmodel.cn/api/llm-application/open/v2/application/app-xxx/variables \
  -H "Authorization: Bearer YOUR_API_KEY"
```
```python
import requests
resp = requests.get(
    "https://open.bigmodel.cn/api/llm-application/open/v2/application/app-xxx/variables",
    headers={"Authorization": "Bearer YOUR_API_KEY"})
print(resp.json())
```

**示例响应**

```json
{"data":[{"id":"var-1","name":"城市","type":"selection_list","tips":"请选择城市",
  "allowed_values":["北京","上海","广州"],"input_template":{}}],
 "code":200,"message":"success"}
```

**注意事项**：`type` 取值 `Input`(文本)/`selection_list`(下拉)/`upload_file`/`upload_image`/`upload_video`/`upload_audio`；仅 `type=selection_list` 时 `allowed_values` 才有实际选项。

### 24. 创建新会话

**Endpoint**: `POST /llm-application/open/v2/application/{app_id}/conversation`
**用途**: 为对话类应用创建新会话，返回 `conversation_id` 供 `invoke`/临时文件上传使用。

**关键参数**：`app_id`（路径，必填）。

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/llm-application/open/v2/application/app-xxx/conversation \
  -H "Authorization: Bearer YOUR_API_KEY"
```
```python
import requests
resp = requests.post(
    "https://open.bigmodel.cn/api/llm-application/open/v2/application/app-xxx/conversation",
    headers={"Authorization": "Bearer YOUR_API_KEY"})
print(resp.json())
```

**示例响应**

```json
{"data":{"conversation_id":"app-conv-xxx"},"code":200,"message":"success"}
```

**注意事项**：文本型（非对话型）应用一般无需预先建会话，`invoke` 未传 `conversation_id` 时会自动创建。

### 25. 推理接口（调用应用）

**Endpoint**: `POST /llm-application/open/v3/application/invoke`
**用途**: 对话型或文本型应用的核心推理接口，触发一次应用运行，支持同步/流式（默认）。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `app_id` | string | 是 | - | 应用 ID |
| `messages` | array | 是 | - | `{role?, content}`；`content` 数组元素结构为 `ApplicationInvokeContent`，**原始 schema 未展开该 `$ref`**，需按接口23返回的变量类型构造，不要凭空编造字段 |
| `conversation_id` | string | 否 | 自动创建 | 建议先用接口24创建 |
| `role` | string | 对话类应用必填 | - | `user`/`assistant` |
| `third_request_id` | string | 否 | - | 三方请求ID，调用插件时传入便于排查 |
| `stream` | boolean | 否 | `true` | `false` 为同步 |
| `send_log_event` | boolean | 否 | `false` | 是否实时推送过程日志 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/llm-application/open/v3/application/invoke -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"app_id":"app-xxx","conversation_id":"app-conv-xxx","role":"user","stream":false,"messages":[{"role":"user","content":[{"type":"input","value":"帮我查一下北京明天的天气"}]}]}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/llm-application/open/v3/application/invoke",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"app_id": "app-xxx", "conversation_id": "app-conv-xxx", "role": "user", "stream": False,
          "messages": [{"role": "user", "content": [{"type": "input", "value": "帮我查一下北京明天的天气"}]}]})
print(resp.json())
```

**示例响应**

```json
{"request_id":"req-xxx","conversation_id":"app-conv-xxx","app_id":"app-xxx",
 "choices":[{"index":0,"finish_reason":"stop","delta":{},"messages":{}}],
 "usage":[{"model":"glm-4.6","nodeName":"生成节点","inputTokenCount":30,"outputTokenCount":80,"totalTokenCount":110}]}
```

**注意事项**：`messages[].content`（`ApplicationInvokeContent`）与 `choices[].delta`/`choices[].messages`（`ApplicationInvokeDelta`/`ApplicationInvokeMessages`）在官方 schema 中以 `$ref` 引用但未展开具体字段，本文不做臆测——接入前先用接口23查看该应用的输入变量类型，并通过官方在线调试（Try it）观察真实结构；`finish_reason=error` 时读 `error_msg.code`/`error_msg.msg`；`usage` 是数组，一次调用可能经过多个节点（`nodeName`），各自可能用不同模型。

### 26. 文件上传（应用专用）

**Endpoint**: `POST /llm-application/open/v2/application/file_upload`
**用途**: 向智能体应用上传文件（表单文本输入组件的文件，或对话中的临时文件），同步接口，实际解析结果需配合"获取文件解析状态"查询。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `app_id` | string | 是 | 应用 ID |
| `files` | binary | 是 | 支持多文件（字段可重复出现） |
| `upload_unit_id` | string | 否 | 上传组件 ID；文本类必传，对话类临时文件不传 |
| `conversation_id` | string | 条件必填 | 对话类型上传临时文件时必传（需先建会话）；文本类不传 |
| `file_type` | integer | 否 | `1`=excel `2`=文档 `3`=音频 `4`=图片 `5`=视频 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/llm-application/open/v2/application/file_upload \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "app_id=app-xxx" -F "conversation_id=app-conv-xxx" -F "file_type=2" -F "files=@/path/to/report.pdf"
```
```python
import requests
with open("/path/to/report.pdf", "rb") as f:
    resp = requests.post(
        "https://open.bigmodel.cn/api/llm-application/open/v2/application/file_upload",
        headers={"Authorization": "Bearer YOUR_API_KEY"},
        data={"app_id": "app-xxx", "conversation_id": "app-conv-xxx", "file_type": 2},
        files={"files": f})
print(resp.json())
```

**示例响应**

```json
{"data":{"success_info":[{"file_id":"file-xxx","file_name":"report.pdf"}],"fail_info":[]},
 "code":200,"message":"success"}
```

**注意事项**：`file_id` 需配合"获取文件解析状态"确认解析完成后，才能在 `invoke` 的 `messages[].content` 中引用。

### 27. 获取文件解析状态

**Endpoint**: `POST /llm-application/open/v2/application/file_stat`
**用途**: 查询已上传文件的解析状态，判断是否可用于 `invoke`。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `app_id` | string | 是 | 应用 ID |
| `file_ids` | array\<string\> | 是 | 文件 ID 列表 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/llm-application/open/v2/application/file_stat -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" -d '{"app_id":"app-xxx","file_ids":["file-xxx"]}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/llm-application/open/v2/application/file_stat",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"app_id": "app-xxx", "file_ids": ["file-xxx"]})
print(resp.json())
```

**示例响应**

```json
{"data":[{"file_id":"file-xxx","code":0,"msg":"解析完成"}],"code":200,"message":"success"}
```

**注意事项**：`data[].code` 的完整枚举未在官方 schema 给出，建议结合 `msg` 文本判断并做好轮询重试。

### 28. 知识库切片引用位置信息

**Endpoint**: `POST /llm-application/open/v2/application/slice_info`
**用途**: 应用回答引用了知识库内容时，按一次 `invoke` 返回的 `request_id` 和节点 `node_id`，获取具体引用切片及其在原文档中的位置（用于前端高亮/原文预览）。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `request_id` | string | 是 | `invoke` 接口返回的 `request_id` |
| `node_id` | string | 是 | 产生引用的节点 ID |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/llm-application/open/v2/application/slice_info -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" -d '{"request_id":"req-xxx","node_id":"node-xxx"}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/llm-application/open/v2/application/slice_info",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"request_id": "req-xxx", "node_id": "node-xxx"})
print(resp.json())
```

**示例响应**

```json
{"data":{"document_slices":[{"document":{},"slice_info":[{}],"hide_positions":false,"images":[]}],
  "has_old_document":false},
 "code":200,"message":"success"}
```

**注意事项**：`document`/`slice_info`/`images` 对应 `DocumentInfo`/`SliceInfo`/`SliceImage`，官方 schema 以 `$ref` 引用但未展开字段，接入前建议用在线调试观察真实结构，不要臆造字段名；`hide_positions=true` 或 `has_old_document=true` 表示存在缺少位置信息的历史文档，前端应做降级展示。

### 29. 推荐问题接口

**Endpoint**: `GET /llm-application/open/history_session_record/{app_id}/{conversation_id}`
**用途**: 获取指定会话下的推荐追问问题列表，用于展示"猜你想问"。

**关键参数**：`app_id`、`conversation_id`（均为路径参数，必填）。

**示例请求**

```bash
curl https://open.bigmodel.cn/api/llm-application/open/history_session_record/app-xxx/app-conv-xxx \
  -H "Authorization: Bearer YOUR_API_KEY"
```
```python
import requests
resp = requests.get(
    "https://open.bigmodel.cn/api/llm-application/open/history_session_record/app-xxx/app-conv-xxx",
    headers={"Authorization": "Bearer YOUR_API_KEY"})
print(resp.json())
```

**示例响应**

```json
{"data":{"problems":["退货需要多久到账？","换货是否收取运费？"]},"code":200,"message":"success"}
```

**注意事项**：路径名为 `history_session_record`（历史会话记录），但按官方 `summary` 描述实际用途是推荐问题，返回也只有 `problems` 数组，不含历史消息本身；如需拉取完整历史消息请用其他会话/消息接口。
