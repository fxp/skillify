# 智能体、助手与知识库（Agents / Assistant / Knowledge Base）参考

覆盖 bigmodel.cn 除基础 Chat Completions 外的三大能力：官方预置智能体（Agents）、对话式助手（Assistant）、GLM 全模态知识库（RAG），以及低代码 Agentic 应用的调用接口。

**通用约定**：Base URL `https://open.bigmodel.cn/api/`，本文 path 均相对该 base；鉴权用请求头 `Authorization: Bearer <API_KEY>`（[获取地址](https://bigmodel.cn/usercenter/proj-mgmt/apikeys)）。若要自建 embedding+rerank 检索管线而非用本文第三节的托管知识库，见 `references/tools.md`。

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
| `stream` | boolean | 否 | `true` | 流式响应 |
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
  -d '{"assistant_id":"65940acff94777010aa6b796","model":"glm-4-assistant","messages":[{"role":"user","content":"总结一下量子计算原理"}],"stream":false}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/paas/v4/assistant",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"assistant_id": "65940acff94777010aa6b796", "model": "glm-4-assistant",
          "messages": [{"role": "user", "content": "总结一下量子计算原理"}], "stream": False})
print(resp.json())
```

**示例响应**

```json
{"id":"resp-xxx","request_id":"req-xxx","created":1735689600,"model":"glm-4-assistant",
 "choices":[{"index":0,"message":{"role":"assistant","content":"量子计算利用叠加与纠缠……"},"finish_reason":"stop"}],
 "usage":{"prompt_tokens":15,"completion_tokens":120,"total_tokens":135}}
```

**注意事项**：`stream` 默认 `true`，同步需显式传 `false`；流式响应为 `text/event-stream`；`messages.role` 严格只允许 `user`，多轮上下文靠 `conversation_id` 维护而非传历史消息；`GLM-4.5V` 系列可能返回 `<think></think>`/`<|begin_of_box|>` 标签，`reasoning_content` 仅 `glm-4.5`/`glm-4.1v-thinking` 系列返回。

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

## 三、GLM 全模态知识库 / RAG 检索增强

平台托管的 RAG 服务：上传文本/图片/音频/视频文件，平台自动完成切分、向量化、索引构建，开发者通过 `knowledge_id` 检索或问答，无需自建 embedding+向量库+rerank 管线。个人免费存储 1GB。若要自己掌控每个环节，见 `references/tools.md` 的 Embeddings（`/paas/v4/embeddings`）与 Rerank 接口。

### 知识库管理

### 7. 创建知识库

**Endpoint**: `POST /llm-application/open/knowledge`
**用途**: 创建个人知识库，绑定向量化模型。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `embedding_id` | integer | 是 | - | `3`=Embedding-2，`11`=Embedding-3，`12`=Embedding-3-pro |
| `embedding_model` | string | 否 | - | 对应 code：`Embedding-2`/`Embedding-3`/`Embedding-3-pro` |
| `name` | string | 是 | - | 知识库名称 |
| `description` | string | 否 | - | 描述 |
| `contextual` | integer | 否 | - | 是否开启上下文增强 `0/1`；**不可逆** |
| `background` | string | 否 | `blue` | `blue/red/orange/purple/sky/green/yellow` |
| `icon` | string | 否 | `question` | `question/book/seal/wrench/tag/horn/house` |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/llm-application/open/knowledge -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"embedding_id":11,"name":"产品文档知识库","description":"产品说明书与FAQ","background":"blue","icon":"book"}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/llm-application/open/knowledge",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"embedding_id": 11, "name": "产品文档知识库", "description": "产品说明书与FAQ",
          "background": "blue", "icon": "book"})
print(resp.json())
```

**示例响应**

```json
{"data":{"id":"know-xxx"},"code":200,"message":"success","timestamp":1735689600}
```

**注意事项**：返回的 `data.id` 即后续上传文档/检索用的 `knowledge_id`；更换向量化模型需走"编辑知识库"，会触发重新向量化。

### 8. 知识库列表

**Endpoint**: `GET /llm-application/open/knowledge`
**用途**: 分页获取个人知识库列表。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 |
| --- | --- | --- | --- |
| `page` | integer | 否 | `1` |
| `size` | integer | 否 | `10` |

**示例请求**

```bash
curl -G https://open.bigmodel.cn/api/llm-application/open/knowledge -H "Authorization: Bearer YOUR_API_KEY" \
  -d page=1 -d size=10
```
```python
import requests
resp = requests.get("https://open.bigmodel.cn/api/llm-application/open/knowledge",
    headers={"Authorization": "Bearer YOUR_API_KEY"}, params={"page": 1, "size": 10})
print(resp.json())
```

**示例响应**

```json
{"data":{"list":[{"id":"know-xxx","embedding_id":11,"name":"产品文档知识库","document_size":12,
   "length":88000,"word_num":42000}],"total":1},"code":200,"message":"success"}
```

**注意事项**：`length` 为分词后总长度，`word_num` 为总字数，可结合"知识库使用量"核对配额。

### 9. 知识库详情

**Endpoint**: `GET /llm-application/open/knowledge/{id}`
**用途**: 按 ID 获取单个知识库详情。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id`（路径） | string | 是 | 知识库 ID |

**示例请求**

```bash
curl https://open.bigmodel.cn/api/llm-application/open/knowledge/know-xxx -H "Authorization: Bearer YOUR_API_KEY"
```
```python
import requests
resp = requests.get("https://open.bigmodel.cn/api/llm-application/open/knowledge/know-xxx",
    headers={"Authorization": "Bearer YOUR_API_KEY"})
print(resp.json())
```

**示例响应**

```json
{"data":{"id":"know-xxx","embedding_id":11,"name":"产品文档知识库","contextual":0,
  "background":"blue","icon":"book","document_size":12,"length":88000,"word_num":42000},
 "code":200,"message":"success"}
```

**注意事项**：字段结构与"知识库列表"单条记录一致。

### 10. 编辑知识库

**Endpoint**: `PUT /llm-application/open/knowledge/{id}`
**用途**: 编辑已创建的知识库，仅需传要修改的字段。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id`（路径） | string | 是 | 知识库 ID |
| `embedding_id`/`embedding_model` | - | 否 | 同"创建知识库" |
| `contextual` | integer | 否 | `0/1` |
| `name`/`description`/`background`/`icon` | string | 否 | 同"创建知识库" |
| `callback_url` | string | 否 | 修改向量模型触发重建时的回调地址 |
| `callback_header` | object | 否 | 回调 header k-v |

**示例请求**

```bash
curl -X PUT https://open.bigmodel.cn/api/llm-application/open/knowledge/know-xxx -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" -d '{"name":"产品文档知识库-v2"}'
```
```python
import requests
resp = requests.put("https://open.bigmodel.cn/api/llm-application/open/knowledge/know-xxx",
    headers={"Authorization": "Bearer YOUR_API_KEY"}, json={"name": "产品文档知识库-v2"})
print(resp.json())
```

**示例响应**

```json
{"code":200,"message":"success","timestamp":1735689600}
```

**注意事项**：修改 `embedding_id`/`embedding_model` 会触发全部文档重新向量化，可用 `callback_url` 接收完成通知。

### 11. 删除知识库

**Endpoint**: `DELETE /llm-application/open/knowledge/{id}`
**用途**: 删除个人知识库（含库内全部文档），不可恢复。

**关键参数**：`id`（路径，必填，知识库 ID）。

**示例请求**

```bash
curl -X DELETE https://open.bigmodel.cn/api/llm-application/open/knowledge/know-xxx -H "Authorization: Bearer YOUR_API_KEY"
```
```python
import requests
resp = requests.delete("https://open.bigmodel.cn/api/llm-application/open/knowledge/know-xxx",
    headers={"Authorization": "Bearer YOUR_API_KEY"})
print(resp.json())
```

**示例响应**

```json
{"code":200,"message":"success","timestamp":1735689600}
```

**注意事项**：不可逆，建议加二次确认逻辑。

### 12. 知识库使用量

**Endpoint**: `GET /llm-application/open/knowledge/capacity`
**用途**: 获取账号下知识库总使用量（字数/字节数），判断是否接近 1GB 免费配额。

**关键参数**：无。

**示例请求**

```bash
curl https://open.bigmodel.cn/api/llm-application/open/knowledge/capacity -H "Authorization: Bearer YOUR_API_KEY"
```
```python
import requests
resp = requests.get("https://open.bigmodel.cn/api/llm-application/open/knowledge/capacity",
    headers={"Authorization": "Bearer YOUR_API_KEY"})
print(resp.json())
```

**示例响应**

```json
{"data":{"used":{"word_num":42000,"length":88000},"total":{"word_num":5000000,"length":1073741824}},
 "code":200,"message":"success"}
```

**注意事项**：官方建议用量超 70% 时清理文件或升级套餐。

### 文档管理

### 13. 文档列表

**Endpoint**: `GET /llm-application/open/document`
**用途**: 获取指定知识库下的文档列表。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `knowledge_id` | string | 是 | - | 知识库 ID |
| `page` | integer | 否 | `1` | 页码 |
| `size` | integer | 否 | `10` | 每页数量 |
| `word` | string | 否 | - | 按文档名称筛选 |

**示例请求**

```bash
curl -G https://open.bigmodel.cn/api/llm-application/open/document -H "Authorization: Bearer YOUR_API_KEY" \
  -d knowledge_id=know-xxx -d page=1 -d size=10
```
```python
import requests
resp = requests.get("https://open.bigmodel.cn/api/llm-application/open/document",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    params={"knowledge_id": "know-xxx", "page": 1, "size": 10})
print(resp.json())
```

**示例响应**

```json
{"data":{"list":[{"id":"doc-xxx","knowledge_type":1,"sentence_size":300,"length":5000,
  "word_num":2400,"name":"产品说明书.pdf","url":"https://.../产品说明书.pdf","embedding_stat":1,"failInfo":null}],
  "total":1},"code":200,"message":"success"}
```

**注意事项**：`embedding_stat` 状态码含义未在 schema 完整枚举，建议结合"文档详情"的 `failInfo` 判断是否失败。

### 14. 上传文件文档

**Endpoint**: `POST /llm-application/open/document/upload_document/{id}`
**用途**: 向指定知识库上传文件类型文档，可指定切片方式，支持处理完成回调。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `id`（路径） | string | 是 | - | 知识库 ID |
| `files` | binary | 是 | - | 待上传文件，字段可重复出现以支持多文件 |
| `knowledge_type` | integer | 否 | 动态解析 | 见下表 |
| `custom_separator` | array\<string\> | 否 | `\n` | 仅 `knowledge_type=5` 生效 |
| `sentence_size` | integer | 否 | `300` | 20-2000，仅 `knowledge_type=5` 生效 |
| `parse_image` | boolean | 否 | `false` | 是否解析文档内图片 |
| `callback_url`/`callback_header` | - | 否 | - | 完成回调 |
| `word_num_limit` | string | 否 | - | 文档字数上限（数字字符串） |
| `req_id` | string | 否 | - | 请求唯一 ID |

`knowledge_type`：`1`=按标题段落切（txt/doc/pdf/url/docx/ppt/pptx/md）；`2`=按问答对切（同上格式）；`3`=按行切（xls/xlsx/csv）；`5`=自定义切（同 1 格式）；`6`=按页切（pdf/ppt/pptx）；`7`=按单个切（xls/xlsx/csv）。

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/llm-application/open/document/upload_document/know-xxx \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "files=@/path/to/产品说明书.pdf" -F "knowledge_type=1" -F "parse_image=true"
```
```python
import requests
with open("/path/to/产品说明书.pdf", "rb") as f:
    resp = requests.post(
        "https://open.bigmodel.cn/api/llm-application/open/document/upload_document/know-xxx",
        headers={"Authorization": "Bearer YOUR_API_KEY"},
        files={"files": f}, data={"knowledge_type": 1, "parse_image": "true"})
print(resp.json())
```

**示例响应**

```json
{"data":{"successInfos":[{"documentId":"doc-xxx","fileName":"产品说明书.pdf"}],"failedInfos":[]},
 "code":200,"message":"success"}
```

**注意事项**：单文档建议不超过 100MB；上传后需经历"数据处理中/索引构建中"才能被检索，是异步过程，建议轮询"文档详情"或用 `callback_url`；深度解析按页 0.12 元计费，在知识库/文档层面配置，不在本接口参数中。

### 15. 上传URL文档

**Endpoint**: `POST /llm-application/open/document/upload_url`
**用途**: 抓取网页 URL 内容作为文档导入知识库，支持批量 URL。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `knowledge_id` | string | 是 | - | 知识库 ID |
| `upload_detail` | array | 是 | - | 每项：`url`(必填)、`knowledge_type`(必填,同上表)、`custom_separator`(仅type=5)、`sentence_size`(仅type=5,默认300)、`callback_url`、`callback_header` |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/llm-application/open/document/upload_url -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"knowledge_id":"know-xxx","upload_detail":[{"url":"https://example.com/docs/faq","knowledge_type":1}]}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/llm-application/open/document/upload_url",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"knowledge_id": "know-xxx",
          "upload_detail": [{"url": "https://example.com/docs/faq", "knowledge_type": 1}]})
print(resp.json())
```

**示例响应**

```json
{"data":{"successInfos":[{"documentId":"doc-yyy","url":"https://example.com/docs/faq"}],"failedInfos":[]},
 "code":200,"message":"success"}
```

**注意事项**：只能抓取网页内容，不支持通过 URL 间接指向文件资源上传。

### 16. 解析文档图片

**Endpoint**: `POST /llm-application/open/document/slice/image_list/{id}`
**用途**: 获取文档解析出的图片序号与下载链接映射，配合"上传文件文档"的 `parse_image=true` 使用。

**关键参数**：`id`（路径，必填，文档 ID）。

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/llm-application/open/document/slice/image_list/doc-xxx \
  -H "Authorization: Bearer YOUR_API_KEY"
```
```python
import requests
resp = requests.post(
    "https://open.bigmodel.cn/api/llm-application/open/document/slice/image_list/doc-xxx",
    headers={"Authorization": "Bearer YOUR_API_KEY"})
print(resp.json())
```

**示例响应**

```json
{"data":{"images":[{"text":"图1","cos_url":"https://.../fig1.png"}]},"code":200,"message":"success"}
```

**注意事项**：`text` 为图片在原文档中的序号占位，`cos_url` 为可直接访问链接。

### 17. 文档详情

**Endpoint**: `GET /llm-application/open/document/{id}`
**用途**: 按文档 ID 获取详情，包括切片配置与向量化状态/失败原因。

**关键参数**：`id`（路径，必填，文档 ID）。

**示例请求**

```bash
curl https://open.bigmodel.cn/api/llm-application/open/document/doc-xxx -H "Authorization: Bearer YOUR_API_KEY"
```
```python
import requests
resp = requests.get("https://open.bigmodel.cn/api/llm-application/open/document/doc-xxx",
    headers={"Authorization": "Bearer YOUR_API_KEY"})
print(resp.json())
```

**示例响应**

```json
{"data":{"id":"doc-xxx","knowledge_type":1,"sentence_size":300,"length":5000,"word_num":2400,
  "name":"产品说明书.pdf","embedding_stat":1,"failInfo":{"embedding_code":0,"embedding_msg":""}},
 "code":200,"message":"success"}
```

**注意事项**：批量导入后建议轮询本接口的 `embedding_stat`/`failInfo` 确认向量化成功，失败按 `embedding_msg` 排查。

### 18. 删除文档

**Endpoint**: `DELETE /llm-application/open/document/{id}`
**用途**: 按文档 ID 删除文档（不影响知识库本身）。

**关键参数**：`id`（路径，必填，文档 ID）。

**示例请求**

```bash
curl -X DELETE https://open.bigmodel.cn/api/llm-application/open/document/doc-xxx -H "Authorization: Bearer YOUR_API_KEY"
```
```python
import requests
resp = requests.delete("https://open.bigmodel.cn/api/llm-application/open/document/doc-xxx",
    headers={"Authorization": "Bearer YOUR_API_KEY"})
print(resp.json())
```

**示例响应**

```json
{"code":200,"message":"success","timestamp":1735689600}
```

**注意事项**：仅移除该文档及其切片，不删除知识库。

### 19. 重新向量化

**Endpoint**: `POST /llm-application/open/document/embedding/{id}`
**用途**: 重新执行向量化（重试失败任务，或 URL 类知识源内容更新场景）。同步调用仅表示"任务已接受"，完成后走 `callback_url` 通知，或轮询"文档详情"。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id`（路径） | string | 是 | 文档 ID |
| `callback_url`/`callback_header` | - | 否 | 完成后回调 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/llm-application/open/document/embedding/doc-xxx \
  -H "Authorization: Bearer YOUR_API_KEY" -H "Content-Type: application/json" -d '{}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/llm-application/open/document/embedding/doc-xxx",
    headers={"Authorization": "Bearer YOUR_API_KEY"}, json={})
print(resp.json())
```

**示例响应**

```json
{"code":200,"message":"success","timestamp":1735689600}
```

**注意事项**：本身不返回向量化结果，务必配合回调或轮询确认最终状态。

### 知识库检索 / 问答

### 20. 知识库检索（个人知识库）

**Endpoint**: `POST /llm-application/open/knowledge/retrieve`
**用途**: 对个人知识库检索，支持向量/关键词/混合检索与自定义重排模型，返回带分数的切片列表供业务侧自行拼 Prompt。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `query` | string | 是 | - | 查询内容，≤1000 字 |
| `knowledge_ids` | array\<string\> | 是 | - | 知识库 ID 列表 |
| `document_ids` | array\<string\> | 否 | - | 限定检索范围的文档 ID |
| `request_id` | string | 否 | - | 用于定位日志 |
| `top_k` | integer | 否 | `8` | 最终召回数量，1-20 |
| `top_n` | integer | 否 | `10` | 初始召回数量，1-100 |
| `recall_method` | string | 否 | `mixed` | `embedding`/`keyword`/`mixed` |
| `recall_ratio` | integer | 否 | `80` | 混合检索向量权重，0-100 |
| `rerank_status` | integer | 否 | 不开启 | `0`/`1` |
| `rerank_model` | string | 否 | - | `rerank`/`rerank-pro` |
| `fractional_threshold` | number | 否 | - | 相似度阈值，0-1 |

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/llm-application/open/knowledge/retrieve -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"退货政策是什么？","knowledge_ids":["know-xxx"],"top_k":5,"rerank_status":1,"rerank_model":"rerank-pro"}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/llm-application/open/knowledge/retrieve",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"query": "退货政策是什么？", "knowledge_ids": ["know-xxx"], "top_k": 5,
          "rerank_status": 1, "rerank_model": "rerank-pro"})
print(resp.json())
```

**示例响应**

```json
{"data":[{"text":"自购买之日起7天内，商品未拆封可无理由退货……","score":0.83,
  "metadata":{"_id":"slice-xxx","knowledge_id":"know-xxx","doc_id":"doc-xxx",
    "doc_name":"退换货政策.pdf","doc_url":"https://...","contextual_text":""}}],
 "code":200,"message":"success"}
```

**注意事项**：`contextual_text` 仅知识库开启"上下文增强"（`contextual=1`）时才有内容；本接口面向文本版/QA 版知识库，全模态版（含图片/音视频）应用下方"全模态知识库检索"。

### 21. 全模态知识库检索

**Endpoint**: `POST /zrag/retrieval/retrieve`
**用途**: 对全模态知识库检索，支持文本或图片查询（`multimodal_parts`），支持查询重写/扩召/重排/标签与 QA 干预，结果含图片/视频等媒体信息及召回/重排位次。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `knows` | array | 是 | - | `{id, doc_ids?}` |
| `query` | string | 否* | - | 文本查询 |
| `multimodal_parts` | array | 否* | - | 仅支持 `{type:"image_url", url}` |
| `multimodal` | boolean | 否 | `true` | 是否走多模态检索路径 |
| `top_k`/`top_n` | integer | 否 | `8`/`10` | 召回数量 |
| `recall_method` | string | 否 | `mixed` | `embedding`/`keyword`/`mixed` |
| `recall_ratio` | number | 否 | `0.8` | 混合检索向量权重，**0-1**（与接口20的0-100整数不同） |
| `enable_rerank`/`enable_rewrite`/`enable_expansion` | boolean | 否 | `false` | 重排/查询重写/扩召 |
| `similarity_threshold` | number | 否 | `0.2` | 相似度阈值 |
| `messages` | array | 否 | - | `{role:user/assistant, content}`，配合 `enable_rewrite` 多轮改写 |
| `search_filters.index_types` | array | 否 | - | `{know_id, index_type_id}` |
| `search_filters.tags` | array | 否 | - | `{tag_id, value_type(fixed/ref), filter_type(1:>= 2:<= 3:包含 4:不包含), filter_value, multiple_value}` |
| `search_filters.qa_intervention` | object | 否 | - | `{qa_similarity_threshold(默认0.6), qa_intervention_ids}` |

\* `query` 与 `multimodal_parts` 二选一必填。

**示例请求**

```bash
curl -X POST https://open.bigmodel.cn/api/zrag/retrieval/retrieve -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"knows":[{"id":"know-xxx"}],"query":"这个零件的安装步骤是什么？","top_k":5,"enable_rerank":true,"enable_rewrite":true}'
```
```python
import requests
resp = requests.post("https://open.bigmodel.cn/api/zrag/retrieval/retrieve",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"knows": [{"id": "know-xxx"}], "query": "这个零件的安装步骤是什么？",
          "top_k": 5, "enable_rerank": True, "enable_rewrite": True})
print(resp.json())
```

**示例响应**

```json
{"data":{"contents":[{"id":"uuid-slice-xxx","know_id":"know-xxx","doc_id":"doc-xxx",
   "text":"第三步：将支架对准卡槽后垂直下压……",
   "medias":[{"id":"img-1","url":"https://.../fig3.png","description":"安装示意图"}],
   "index":0,"score":0.79,"rerank_index":0,"rerank_score":0.91,
   "metadata":{"doc_type":"pdf","doc_name":"安装说明书.pdf","page_index":3}}],
  "rewritten_query":{"original_query":"这个零件的安装步骤是什么？","multi_queries":["零件安装步骤"]},
  "elapsed_ms":320,"total_tokens":45,"request_id":"req-xxx"},
 "code":200,"message":"success"}
```

**注意事项**：视频/音频切片的 `metadata` 会额外含 `clip_index`/`start_time`/`end_time`/`duration`/`frames`，内容通过 `video_url`/`image_url` 返回；`recall_ratio` 本接口是 0-1 小数，接口20是 0-100 整数，不要混用。

### 22. 问答 Agent 对话（流式）

**Endpoint**: `POST /zrag/agent/chat`
**用途**: 基于 ReAct 推理引擎的一体化问答接口。预设 `retrieval` 参数后，模型自主决定是否调用知识检索、查询重写等工具，通过 SSE 实时推送思考过程、工具调用、工具结果与最终回答——检索与生成都由平台完成，无需自己先检索再拼 Prompt。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `messages` | array | 是 | - | `role` 仅支持 `user`，content 支持文本或多模态数组 |
| `retrieval.know_ids` | array\<string\> | 是 | - | 知识库 ID 列表 |
| `retrieval.top_k`/`top_n` | integer | 否 | `8`/`10` | 检索/召回数量 |
| `retrieval.enable_rerank` | boolean | 否 | `false` | 是否重排 |
| `retrieval.similarity_threshold` | number | 否 | `0.2` | 相似度阈值 |
| `model` | string | 否 | `glm-5v-turbo` | LLM 模型 |
| `temperature` | number | 否 | `0.7` | 采样温度 |
| `max_steps` | integer | 否 | `10` | 最大推理步数 |
| `enable_thinking` | boolean | 否 | `false` | 启用后通过 `reasoning` 事件流式返回推理过程 |
| `X-Session-Id`（请求头） | string | 否 | - | 续聊时传入以保持上下文 |

**示例请求**

```bash
curl -N -X POST https://open.bigmodel.cn/api/zrag/agent/chat -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"查一下退货政策，总结三条要点"}],"retrieval":{"know_ids":["know-xxx"],"enable_rerank":true},"enable_thinking":true}'
```
```python
import json, requests
resp = requests.post("https://open.bigmodel.cn/api/zrag/agent/chat",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"messages": [{"role": "user", "content": "查一下退货政策，总结三条要点"}],
          "retrieval": {"know_ids": ["know-xxx"], "enable_rerank": True},
          "enable_thinking": True}, stream=True)
for line in resp.iter_lines():
    if line and line.startswith(b"data:"):
        event = json.loads(line[len(b"data:"):].strip())
        print(event["type"], event.get("data"))
```

**示例响应（SSE，每行一个事件）**

```json
{"type":"session_created","sessionId":"sess-xxx"}
{"type":"tool_call","data":{"callId":"call-1","toolName":"knowledge_retrieve","arguments":{"query":"退货政策"}}}
{"type":"tool_result","data":{"callId":"call-1","status":"success","durationMs":280,"result":{}}}
{"type":"answer","data":"根据知识库内容，退货政策要点如下：1) ..."}
{"type":"done","messageId":"msg-xxx","usage":{"prompt_tokens":50,"completion_tokens":120,"total_tokens":170,"total_calls":1}}
```

**注意事项**：事件 `type` 取值 `session_created/reasoning(仅enable_thinking时)/thought/tool_call/tool_result/answer/done/error`；`usage` 仅在 `done` 事件出现，含 `total_calls`；续多轮对话从首个 `session_created` 事件取 `sessionId`，后续通过 `X-Session-Id` 请求头传入，无需重传完整历史。

### 知识库检索结果怎么接入对话

检索到的知识片段接入对话，常见三种方式：

1. **自行拼接 Prompt**：调用第 20/21 节检索接口拿到 `text` 片段，按相关性拼接后放入 `chat/completions` 的 `system` 消息（背景资料）或 `user` 消息前缀，再正常调用模型生成。最灵活，可自定义拼接模板、截断策略、引用角标。
2. **在 Chat Completions 中直接挂 `retrieval` 工具**：调用 `/paas/v4/chat/completions` 时在 `tools` 传入 `{"type":"retrieval","retrieval":{"knowledge_id":"...","prompt_template":"从文档\n\"\"\"\n{{knowledge}}\n\"\"\"\n中找问题\n\"\"\"\n{{question}}\n\"\"\"\n的答案……"}}`，模型生成前自动检索该知识库并套入模板（`{{knowledge}}`/`{{question}}` 占位）。仅支持单个 `knowledge_id`，适合快速接入；具体 `chat/completions` 参数见对应 Chat Completions 参考文件。
3. **用一体化问答接口**：直接调用本节第 22 条 `POST /zrag/agent/chat`，由平台自主判断何时检索、如何生成，SSE 返回完整过程，适合多轮对话与可观测推理场景，只需预设 `retrieval.know_ids` 等参数。

选择建议：需要精细控制上下文格式或拼接多路检索结果用方式 1；只想给普通对话"挂一个知识库"快速上线用方式 2；需要模型自主判断检索与否、支持多轮追问用方式 3。

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
