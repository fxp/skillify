# 智能体、助手与知识库（Agents / Assistant / Knowledge Base）参考

覆盖 bigmodel.cn 除基础 Chat Completions 外的三大能力：官方预置智能体（Agents）、对话式助手（Assistant）、GLM 全模态知识库（RAG），以及低代码 Agentic 应用的调用接口。

**通用约定**：Base URL `https://open.bigmodel.cn/api/`，本文 path 均相对该 base；鉴权用请求头 `Authorization: Bearer <API_KEY>`（[获取地址](https://bigmodel.cn/usercenter/proj-mgmt/apikeys)）。若要自建 embedding+rerank 检索管线而非用本文第三节的托管知识库，见 `references/tools.md`。

> 本文是托管知识库 / RAG 检索部分，从 `agents-assistant-knowledge.md` 拆出。
> 内置智能体、Assistant API、Agentic 应用调用见 [`agents-assistant.md`](agents-assistant.md)。

## 三、GLM 全模态知识库 / RAG 检索增强

> ### ⚠️ 使用这套知识库 API 前必须先读的两条（2026-09-07 用真实调用验证）
>
> **1）这一族接口出错时 HTTP 状态码依然是 200，真实结果在响应体的 `code` 里。**
> `llm-application/open/*` 下的所有端点（以及 `/zrag/*`）实测均如此：查一个不存在的知识库，
> 返回的是 `HTTP 200` + `{"code":100013,"message":"知识库不存在"}`；上传时字段名写错，
> 返回的是 `HTTP 200` + `{"code":400,"message":"Required request part 'files' is not present"}`。
> **`resp.raise_for_status()` 在这里永远不会触发**，必须判断 `resp.json()["code"] == 200`，
> 否则整条 RAG 流水线会带着错误继续跑下去。
>
> **2）上传成功 ≠ 文档可检索。向量化是后台异步的，失败时没有任何主动通知。**
> 实测：上传返回 `HTTP 200` 且 `data.successInfos` 里带回了 `documentId`（看起来完全成功），
> 但随后 `POST /knowledge/retrieve` **持续返回 `HTTP 200` + `{"code":200,"data":[]}`**——
> 空数组，不报错，无限等下去也不会有结果。唯一能看出真相的地方是 `GET /document/{id}`：
>
> | 字段 | 含义 |
> | :--- | :--- |
> | `embedding_stat` | `0`=处理中 `1`=成功 `2`=失败 |
> | `failInfo.embedding_code` / `failInfo.embedding_msg` | 失败原因，例如 `10001` / `知识不可用，文档损坏` |
>
> **正确写法是：上传后轮询 `GET /document/{id}` 直到 `embedding_stat == 1` 再去检索**，
> 拿到 `2` 就直接报错给用户，不要靠"检索为空"去推断——那和"确实没有相关内容"无法区分。
>
> 附一条如实记录的实测结果：在一个个人版账号上（存储用量 6196/5,000,000 字，远未超限），
> 分别上传 `.pdf`、`.md`、`.txt` 三种格式，**三份文档最终都是 `embedding_stat=2`、
> `embedding_msg="知识不可用，文档损坏"`**，检索始终为空。这可能是账号级权限或服务端当时的问题，
> 未必对所有账号成立——但它恰恰说明了为什么**必须检查 `embedding_stat` 而不能假设上传成功就万事大吉**。


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

