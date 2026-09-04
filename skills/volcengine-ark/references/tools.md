# 火山方舟 · 平台内置工具 / 插件与三方工具接入

本文覆盖：Responses API `tools[]` 里的 5 种平台内置工具（Web Search 联网内容插件、Image Process 图像处理、Knowledge Search 私域知识库搜索、云部署 MCP / Remote MCP、豆包助手 `doubao_app`）的声明方式、参数、返回结构、计费与限制，以及「接入三方工具」页里把方舟模型接进 Chatbox / Cherry Studio / Codex CLI / Claude Code / OpenCode / OpenClaw / TRAE / Cline / Cursor / Roo Code / Kilo Code 的配置要点。自定义函数（Function Calling）本身不在本文范围，只写它与内置工具的混用规则。

> **先分清两件事：标准 API 的 Web Search 工具 ≠ Agent Plan 的「豆包搜索」Harness。**
> - 本文讲的 **Web Search（联网内容插件）** 是标准 API（`https://ark.cn-beijing.volces.com/api/v3/responses`）里 `tools: [{"type": "web_search"}]` 这个内置工具：由**模型**决定是否搜、搜什么，结果以 `web_search_call` 输出项 + `annotations` 引用回到同一个 Response 里，按插件调用次数计费，用方舟 API Key。
> - **豆包搜索（Doubao Search）** 是 Agent Plan 套餐附带的一个 Harness：一个独立的搜索 API 服务（文档 `docs/87772/2272953`），在 Claude Code / OpenCode / OpenClaw / Hermes Agent 里通过 **Skill（`byted-web-search`）或 MCP Server** 接入，由 **Agent 工具** 调它，用 Agent Plan 专属 API Key，走 AFP 抵扣 + 每月 500 次账号级免费额度。它不是 `tools[]` 里的一个 `type`，也不经过 `/api/v3/responses`。Harness 的安装与配置细节见 `references/agent-plan.md`。

## 目录
1. [总览：内置工具怎么声明、在哪能用、怎么计费](#1-总览)
2. [Web Search（联网内容插件）`type: web_search`](#2-web-search联网内容插件)
3. [Image Process（图像处理）`type: image_process`](#3-image-process图像处理)
4. [Knowledge Search（私域知识库搜索）`type: knowledge_search`](#4-knowledge-search私域知识库搜索)
5. [云部署 MCP / Remote MCP `type: mcp`](#5-云部署-mcp--remote-mcp)
6. [豆包助手 `type: doubao_app`](#6-豆包助手)
7. [接入三方工具（Chatbox / Cherry Studio / Codex / Claude Code / OpenCode / OpenClaw / TRAE / Cline / Cursor / Roo Code / Kilo Code）](#7-接入三方工具)
8. [来源页面](#来源页面)

---

## 1. 总览

### 1.1 声明方式与通用规则

所有内置工具都只在 **Responses API**（`POST https://ark.cn-beijing.volces.com/api/v3/responses`）里通过顶层 `tools[]` 数组声明，一个元素一个工具，用 `type` 区分。Chat Completions（`/chat/completions`）的 `tools` 只支持 `type: "function"`；模型列表页「工具调用能力」表把函数调用标为「Responses API & Chat API」，其余五种内置工具全部只标「Responses API」。Remote MCP 文档另有原文：「目前云部署 MCP / Remote MCP 仅支持通过 Responses API 调用」。

| 工具 | `tools[].type` | 额外 HTTP 头（Beta 期间必须） | 前置开通 | 计费口径 | 默认限流 | Chat Completions | Plan 入口 |
|---|---|---|---|---|---|---|---|
| Web Search 联网内容插件 | `web_search` | 无 | 控制台「服务组件库」开通联网内容插件 | 按插件**实际使用次数**计费（一轮可能多个关键词 = 多次），另加模型 tokens | 账号 5 QPS | ✗（文档只给 Responses API） | ⚠ 文档未说明 |
| Image Process 图像处理 | `image_process` | `ark-beta-image-process: true` | 无（Beta） | 公测期间免费，收费前 2 周通知 | ⚠ 文档未说明 | ✗ | ⚠ 文档未说明 |
| Knowledge Search 私域知识库搜索 | `knowledge_search` | `ark-beta-knowledge-search: true` | 项目授权或 IAM 授权 + **旗舰版**知识库 | 按「知识库计费」页（docs 1263336）；一轮多关键词并行 = 多次 | ⚠ 文档未说明 | ✗ | ⚠ 文档未说明 |
| 云部署 MCP / Remote MCP | `mcp` | `ark-beta-mcp: true` | 需完成 MCP 服务开通及模型权限申请（文档原文） | **只消耗模型 tokens，不收 MCP 附加费** | 账号 1000 RPM | ✗（文档明确仅 Responses API） | ⚠ 文档未说明 |
| 豆包助手 | `doubao_app` | `ark-beta-doubao-app: true` | 联系销售 / 工单申请 Beta 资格 → 控制台「应用组件库 › 豆包助手 API」开通 | **按次计费，不收 token 费**（docs 1998171） | 账号 2 QPS | ✗ | ⚠ 文档未说明 |
| 自定义函数 | `function` | 无 | 无 | 模型 tokens | — | ✓ | ✓（见 responses/chat 参考） |

关于 Plan 入口：`auth.md` 记录 Agent Plan `/api/plan/v3` 已支持 Responses API，但 8 个输入页面全部只用 `/api/v3` 和方舟 API Key 举例，没有任何一处提到在 `/api/plan/v3` 或 `/api/coding/v3` 上使用内置工具；Agent Plan 官方口径又是「文本生成模型不可用于 API 调用」。因此**内置工具默认只在标准入口用**，model 字段填带日期的 Model ID（示例统一 `doubao-seed-2-1-pro-260628`）或 `ep-` 接入点。

通用参数 / 返回字段（来自「创建 Response」参数页）：

| 字段 | 位置 | 说明 |
|---|---|---|
| `max_tool_calls` | 请求顶层 | 一次 Response 内工具调用最大轮次。`web_search` 默认 `3`、`knowledge_search` 默认 `3`、`image_process` 默认 `10` 且**不支持修改**；Web Search 页给出取值范围 `1`～`10`。豆包助手 FAQ：该参数「当前无效，使用会返回冲突错误」（文档原文，未实测；FAQ 写的是 `max_tool_call`，疑为笔误） |
| `tool_choice` | 请求顶层 | 字符串 `none` / `auto` / `required`，或对象 `{"type": "...", "name": "..."}`；`type` 可选 `function`、`web_search`、`image_process`、`mcp`、`knowledge_search`、`doubao_app`。⚠ 文档自相矛盾：Image Process 页明确「不支持通过 `tool_choice` 参数指定调用 image_process」 |
| `caching` | 请求顶层 | Web Search / Image Process / Knowledge Search / MCP / 豆包助手 五页都写「暂不支持 `caching` 参数，使用会返回 400 错误」（文档原文，未实测） |
| `usage.tool_usage` | 响应 | 对象，按工具类型计次：`web_search` / `mcp` / `knowledge_search` / `doubao_app`（integer） |
| `usage.tool_usage_details` | 响应 | 同名四个 object，按来源细分，如 `web_search: {"search_engine": 2, "toutiao": 2}`、`doubao_app: {"ai_search": 1}` |
| `store` + `previous_response_id` | 请求顶层 | 多轮串联。**`store` 不会保存 `tools` 配置**，每轮都要重传相同的 `tools`（豆包助手页原文，对 MCP 审批多轮同样适用——示例每轮都重传了 tools） |

**函数命名冲突**：自定义函数不要叫 `web_search`（否则模型按内置优先级判断）；与 `knowledge_search`、`image_process`、`mcp_call` 重名时文档说「由模型自行判断，无需配置」。

**混用矩阵**（文档明示的组合）：

| | 自定义函数 | Web Search | Image Process | Knowledge Search | MCP | 豆包助手 |
|---|---|---|---|---|---|---|
| Web Search | ✓ | — | ✗ | ⚠ 未说明 | ✓ | ✗ |
| Image Process | ✓ | ✗ | — | ⚠ 未说明 | ⚠ 未说明 | ✗ |
| Knowledge Search | ✓ | ⚠ 未说明 | ⚠ 未说明 | — | ✓ | ✗ |
| MCP | ✓（工具组合数量不限） | ✓ | ⚠ 未说明 | ✓ | — | ✗ |
| 豆包助手 | ✗ | ✗ | ✗ | ✗ | ✗ | 单次只能开 1 个 feature |

### 1.2 支持的模型（模型列表页「工具调用能力」表）

该表用图标表示支持/不支持，以下按图标 URL 还原（⚠ 由图标还原，建议实测复核）。「即将下线」的 1.5 / 1.6 / seed-code-preview 系列略去。

| Model ID | 函数调用 | 知识库 | MCP | 联网内容插件 | 图像处理 | 豆包助手 |
|---|---|---|---|---|---|---|
| `doubao-seed-evolving`（快速迭代模型） | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `doubao-seed-2-1-pro-260628` / `doubao-seed-2-1-turbo-260628` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `doubao-seed-2-0-pro-260215` / `-lite-260428` / `-lite-260215` / `-mini-260428` / `-mini-260215` / `-code-preview-260215` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `doubao-seed-1-8-251228`（即将下线）、`doubao-seed-character-260628` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `doubao-seed-character-251128` | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `glm-5-2-260617`、`glm-4-7-251222` | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ |
| `deepseek-v4-pro-ga-260813` / `deepseek-v4-flash-ga-260731` / `deepseek-v4-pro-260425` / `deepseek-v4-flash-260425` | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ |

Image Process 示例页统一用 `doubao-seed-2-0-lite-260215`；其余四个工具示例统一用 `doubao-seed-2-1-pro-260628`。

---

## 2. Web Search（联网内容插件）

### 联网搜索 `web_search`
**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/v3/responses`（`tools[].type = "web_search"`）
**用途**: 让模型在需要时自动发起公开网页搜索（新闻、商品、天气等）。与豆包助手 `ai_search` 的区别：Web Search 可自定义来源 / 条数 / 关键词数、可与函数和 MCP 混用、计入 `web_search_call` 输出项；豆包助手是封装好的「豆包 App 同款」能力，参数不可调、不可混用。

**关键参数**（`tools[]` 元素内）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `type` | string | 是 | — | 固定 `web_search` |
| `max_keyword` | integer | 否 | ⚠ 文档未说明 | 单轮最大并行关键词数，范围 `1`～`50`；文档建议按场景设 1～10。直接决定计费次数 |
| `limit` | integer | 否 | `10` | 单轮搜索最大返回结果条数，范围 `1`～`50`；「单次搜索最多返回 20 条，单轮可能多次搜索」 |
| `sources` | string[] | 否 | 仅 `search_engine` | 附加来源：`douyin`（抖音百科）、`moji`（墨迹天气）、`toutiao`（头条图文）；参数页枚举还含 `search_engine`。是否用哪个来源由模型判断 |
| `user_location` | object | 否 | — | `type` 固定 `approximate`；`country` / `region` / `city` 字符串；参数页另有 `timezone`（number），指南未举例 |
| 顶层 `max_tool_calls` | integer | 否 | `3` | 本 Response 内搜索轮次上限，范围 `1`～`10` |

时间范围筛选：⚠ 文档未说明（Web Search 工具没有时间参数；「时间范围筛选」是 Agent Plan 豆包搜索 API 的能力，别混）。

**示例请求**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/responses \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seed-2-1-pro-260628",
    "stream": true,
    "max_tool_calls": 3,
    "tools": [{
      "type": "web_search",
      "max_keyword": 2,
      "limit": 10,
      "sources": ["toutiao", "douyin", "moji"],
      "user_location": {"type": "approximate", "country": "中国", "region": "浙江", "city": "杭州"}
    }],
    "input": [{"role": "user", "content": [{"type": "input_text", "text": "今天有什么热点新闻？"}]}]
  }'
```

```python
import os
from openai import OpenAI

client = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=os.environ["ARK_API_KEY"])

resp = client.responses.create(
    model="doubao-seed-2-1-pro-260628",
    input=[{"role": "user", "content": [{"type": "input_text", "text": "今天有什么热点新闻？"}]}],
    tools=[{"type": "web_search", "max_keyword": 2, "limit": 10,
            "sources": ["toutiao", "douyin", "moji"]}],
    max_tool_calls=3,
    stream=True,
)
for ev in resp:
    t = ev.type
    if t == "response.reasoning_summary_text.delta":
        print(ev.delta, end="")                       # 模型判断“要不要搜”的思考
    elif t == "response.output_item.done" and ev.item.type == "web_search_call":
        print("\n[搜索关键词]", ev.item.action.query)  # item.id 以 ws_ 开头
    elif t == "response.output_text.delta":
        print(ev.delta, end="")
    elif t == "response.completed":
        u = ev.response.usage
        print("\n计费次数:", u.tool_usage.web_search, u.tool_usage_details.web_search)
```
官方 `volcenginesdkarkruntime.Ark(base_url=..., api_key=...)` 的 `client.responses.create(...)` 参数同上，底层同一 endpoint。

**示例响应**（非流式；关键字段）

```json
{
  "output": [
    {"type": "web_search_call", "id": "ws_xxx", "status": "completed",
     "action": {"type": "search", "query": "今日 热点新闻"}},
    {"type": "message", "role": "assistant", "status": "completed",
     "content": [{
       "type": "output_text",
       "text": "……[1]……",
       "annotations": [{
         "type": "url_citation", "title": "…", "url": "https://…",
         "site_name": "…", "summary": "…", "publish_time": "…", "freshness_info": "…",
         "logo_url": "…", "mobile_url": "…",
         "cover_image": {"url": "…", "width": 0, "height": 0}
       }]
     }]}
  ],
  "usage": {"tool_usage": {"web_search": 2},
            "tool_usage_details": {"web_search": {"search_engine": 2, "toutiao": 2}}}
}
```
- `web_search_call.status` 枚举：`in_progress` / `searching` / `completed` / `incomplete` / `failed`。
- 流式事件名：`response.web_search_call.in_progress` / `...searching` / `...completed`（示例代码按 `"web_search_call" in type` 判断）。
- 引用在 `message.content[].annotations[]`，`type` 固定 `url_citation`，必填 `title` / `url`。

**注意事项**
- 是否搜索由模型决定；系统提示词对触发率影响很大，文档给了两份模板（要点：时效性 / 知识盲区 / 信息不足三种情况才调 `web_search`；正文用 `[1] (URL)` 引用；结尾列参考资料）。
- 账号级 5 QPS；更高并发文档建议接「豆包搜索」产品（即 Agent Plan Harness 那套独立 API）。
- 支持 VLM 模型图文混合输入后再决定是否搜索。
- 不能与 Image Process、豆包助手混用；可与函数、MCP 混用。
- `caching` 参数 → 400（文档原文，未实测）。

---

## 3. Image Process（图像处理）

### 图像处理 `image_process`
**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/v3/responses` + 头 `ark-beta-image-process: true`
**用途**: 让 VLM 模型在推理中主动对输入图片做画点（Point）、框选/裁剪（Grounding）、缩放（Zoom）、旋转（Rotate），上一轮结果图自动成为下一轮输入（image0→image1→image2）。适合看路牌小字、计数、定位标注等「看不清就放大再看」的场景。与自己在客户端裁图再重传的区别：整个多轮循环在服务端一次 Response 内完成。

**关键参数**（`tools[]` 元素内）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `type` | string | 是 | — | 固定 `image_process` |
| `point.type` | string | 否 | `enabled` | 画点/画线开关，`enabled` / `disabled` |
| `grounding.type` | string | 否 | `enabled` | 框选/裁切开关，返回检测框或裁切区域坐标 |
| `zoom.type` | string | 否 | `enabled` | 缩放开关；缩放倍率 0.5～2.0 倍 |
| `rotate.type` | string | 否 | `enabled` | 旋转开关；角度 0～359 度 |
| 顶层 `max_tool_calls` | integer | — | `10` | **不支持修改** |

四个子功能默认全开；官方示例都是显式只开一个、其余 `disabled`。

**示例请求**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/responses \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -H "ark-beta-image-process: true" \
  -d '{
    "model": "doubao-seed-2-0-lite-260215",
    "stream": true,
    "tools": [{"type": "image_process",
               "point": {"type": "disabled"}, "grounding": {"type": "disabled"},
               "zoom": {"type": "enabled"}, "rotate": {"type": "disabled"}}],
    "input": [{"type": "message", "role": "user", "content": [
      {"type": "input_image", "image_url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/image_process_1.jpg"},
      {"type": "input_text", "text": "前方路牌写了什么？"}
    ]}]
  }'
```

```python
import os
from openai import OpenAI

client = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=os.environ["ARK_API_KEY"],
                default_headers={"ark-beta-image-process": "true"})

resp = client.responses.create(
    model="doubao-seed-2-0-lite-260215",
    tools=[{"type": "image_process",
            "point": {"type": "enabled"}, "grounding": {"type": "disabled"},
            "zoom": {"type": "disabled"}, "rotate": {"type": "disabled"}}],
    input=[{"type": "message", "role": "user", "content": [
        {"type": "input_image", "image_url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/image_process_2.jpg"},
        {"type": "input_text", "text": "数一数有多少颗草莓？"},
    ]}],
    stream=True,
)
for chunk in resp:
    if hasattr(chunk, "delta"):
        print(chunk.delta, end="", flush=True)
```
官方 SDK：`Ark(...).responses.create(..., extra_headers={"ark-beta-image-process": "true"})`。

**示例响应**（输出项，按参数页字段）

```json
{"type": "image_process", "id": "…", "status": "completed",
 "action": {"type": "…", "result_image_url": "https://…"},
 "arguments": {"…": "…"},
 "error": {"message": "…"}}
```
- ⚠ 参数页把该输出项的 `type` 写成固定 `image_process`（不是 `image_process_call`，与 `web_search_call` / `knowledge_search_call` / `doubao_app_call` 的命名模式不一致），待实测确认。
- `status`：`completed` / `in_progress` / `incomplete` / `failed`（失败原因看 `error.message`）。
- `action.result_image_url` 是处理后的图，`arguments` 是本次动作的参数键值对。

**注意事项**
- 图片规格：体积 ≤ 10MB；总像素 ≤ 36,000,000；宽高均 > 14 px；长宽比 < 150:1。支持 .gif/.jpg/.jpeg/.png/.webp/.bmp/.tiff/.ico/.icns/.jp2；不支持 .dib/.sgi/.heic/.heif。
- 多图 + 一段文字时，把文字放在 content 末尾（文档建议）。
- 不能与 Web Search 混用；不支持 `tool_choice` 指定 `image_process`；`caching` → 400（文档原文，未实测）。可与自定义函数混用。
- 多轮处理会把上一轮图片计入下一轮输入 tokens，成本随轮次上升。
- 工具概述页的图像处理示例把图片放在 `role: "system"` 消息里，其他页面全部用 `role: "user"`——照 `user` 写。

---

## 4. Knowledge Search（私域知识库搜索）

### 私域知识库搜索 `knowledge_search`
**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/v3/responses` + 头 `ark-beta-knowledge-search: true`
**用途**: 模型自动判断是否检索指定的方舟**旗舰版**知识库（标准版不支持），把切片作为上下文回答，引用以 `doc_citation` 注释返回。与 Web Search 的区别：只查你授权的私域库；与自己调知识库 Search API 再拼 prompt 的区别：改写、多关键词并行、重排、多轮都在一次 Response 内由平台完成。

**前置资源**
1. 授权：控制台「项目授权」页为项目点「授权」（推荐，默认 `default` 项目），或 IAM 自定义策略 `Action: vikingdb:*`、`Resource: trn:ark:*:<YourAccountID>:knowledgebase/*` 挂到角色 `ArkAccessRole_项目名称`。
2. 已开通并构建好的旗舰版知识库，拿到 `knowledge_resource_id`（「查看知识库详情」页）。注意知识库配额（docs 1343907）。

**关键参数**（`tools[]` 元素内）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `type` | string | 是 | — | 固定 `knowledge_search` |
| `knowledge_resource_id` | string | 是 | — | 知识库 ID |
| `description` | string | 否 | — | 知识库描述，帮模型判断何时用 |
| `limit` | integer | 否 | `10` | 最大结果数，范围 `1`～`200` |
| `max_keyword` | integer | 否 | — | 最大并行关键词数 `1`～`50`。⚠ 文档自相矛盾：Knowledge Search 页说「暂不支持通过参数设置改写后问题的个数，需用 system prompt / instructions 控制」 |
| `dense_weight` | number | 否 | `0.5` | 混合检索中语义向量权重，`0.2`～`1`，仅索引算法 `hnsw_hybrid` 生效 |
| `doc_filter` | object | 否 | — | 文档字段过滤，支持 `doc_id`（手动创建库）/ `_sys_auto_doc_id` / 自定义文档标签，And / Or 组合，语法见 VikingDB「filter 表达式」 |
| `ranking_options.get_attachment_link` | boolean | 否 | `false` | 返回切片内图片的临时下载链接 |
| `ranking_options.chunk_diffusion_count` | integer | 否 | `0` | 命中切片上下扩散片数，`0`～`5` |
| `ranking_options.chunk_group` | boolean | 否 | `false` | 按文档顺序聚合切片 |
| `ranking_options.rerank_switch` | boolean | 否 | `false` | 开启重排 |
| `ranking_options.rerank_model` | string | 否 | `base-multilingual-rerank` | 或 `m3-v2-rerank`；仅重排开启时生效 |
| `ranking_options.rerank_only_chunk` | boolean | 否 | `false` | `true` 只按 chunk 内容打分，`false` 按 title + 内容 |
| `ranking_options.retrieve_count` | integer | 否 | `25` | 进入重排的切片数，**必须 ≥ `limit`**，否则报错（文档原文，未实测） |
| 顶层 `max_tool_calls` | integer | 否 | `3` | 检索轮次上限 |
| 顶层 `thinking` | object | 否 | — | 示例用 `{"type": "disabled"}` 直接检索，或 `auto` 让模型判断 |

**示例请求**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/responses \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -H "ark-beta-knowledge-search: true" \
  -d '{
    "model": "doubao-seed-2-1-pro-260628",
    "stream": true,
    "thinking": {"type": "disabled"},
    "max_tool_calls": 1,
    "tools": [{"type": "knowledge_search",
               "knowledge_resource_id": "<knowledge_resource_id>",
               "limit": 2,
               "ranking_options": {"get_attachment_link": true}}],
    "input": [{"role": "user", "content": "机票选择页面中，如何选择该航班不同价格的机票？"}]
  }'
```

```python
import os
from openai import OpenAI

client = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=os.environ["ARK_API_KEY"],
                default_headers={"ark-beta-knowledge-search": "true"})

resp = client.responses.create(
    model="doubao-seed-2-1-pro-260628",
    input=[{"role": "user", "content": [{"type": "input_text",
             "text": "应用实验室里有类似实时视频理解的agent demo么？"}]}],
    tools=[{"type": "knowledge_search",
            "knowledge_resource_id": os.environ["ARK_KB_ID"], "limit": 10}],
    stream=True,
    extra_body={"thinking": {"type": "auto"}},
)
for chunk in resp:
    if hasattr(chunk, "delta"):
        print(chunk.delta, end="", flush=True)
```

**示例响应**（关键字段）

```json
{"output": [
  {"type": "knowledge_search_call", "id": "…", "status": "completed",
   "knowledge_resource_id": "…", "queries": ["改写后的检索词1", "检索词2"]},
  {"type": "message", "role": "assistant", "content": [{
    "type": "output_text", "text": "…",
    "annotations": [{"type": "doc_citation", "doc_id": "…", "doc_name": "…",
                     "chunk_id": 0, "chunk_attachment": [{"…": "…"}]}]}]}
 ],
 "usage": {"tool_usage": {"knowledge_search": 1},
           "tool_usage_details": {"knowledge_search": {"…": 1}}}}
```
`knowledge_search_call.status`：`in_progress` / `searching` / `completed` / `failed` / `incomplete`。`chunk_attachment` 内部结构 ⚠ 文档未说明。

**注意事项**
- 仅旗舰版知识库；与自定义函数、MCP 可混用；与 Web Search / Image Process 的组合 ⚠ 文档未说明；不能与豆包助手混用。
- 一轮可能多关键词并行 → 多次计费，看 `usage.tool_usage`。
- 系统提示词模板：定义「企业知识」类问题才调 `knowledge_search`，引用格式 `[1] (URL)`。
- `caching` → 400（文档原文，未实测）。

---

## 5. 云部署 MCP / Remote MCP

### 远程 MCP 工具 `mcp`
**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/v3/responses` + 头 `ark-beta-mcp: true`
**用途**: 模型在云端直接连接一个 **Streamable HTTP** 的 MCP Server，自动 `list_tools` → 选工具 → 调用 → 把结果喂回模型，多轮循环。与 Function Calling 的区别：工具执行在方舟侧完成，客户端不用写执行循环；代价是**不支持本地 stdio MCP**。MCP URL 来源：「智能体工具商店」（MCP Marketplace）详情页生成带授权信息的个人 URL，或任何公网 Streamable HTTP MCP（示例 `https://mcp.deepwiki.com/mcp`）。

**关键参数**（`tools[]` 元素内）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `type` | string | 是 | — | 固定 `mcp` |
| `server_label` | string | 是 | — | Server 唯一标签，输出项用它标明来源 |
| `server_url` | string | 是 | — | MCP Server 的 HTTP(S) 地址（Streamable HTTP） |
| `server_description` | string | 否 | — | 帮模型判断何时用这个 Server |
| `allowed_tools` | string[] 或 object | 否 | 全部 | 允许的工具名：直接数组，或 `{"tool_names": ["tool1", "tool2"]}`（指南用对象形式） |
| `headers` | object | 否 | — | 调 Server 时附加的 HTTP 头，常放 `Authorization: Bearer <token>`；文档称 `Authorization` 不会被服务端存储 |
| `require_approval` | string 或 object | 否 | `always` | `"always"` / `"never"`；或按工具粒度 `{"always": {"tool_names": [...]}, "never": {"tool_names": [...]}}`。⚠ Java SDK 注释提到 `AUTO` 模式，参数页只列 always / never |

**审批流程**（`require_approval` 为 `always` 或命中 always 列表时）
1. 第 1 轮：模型输出 `mcp_list_tools`（工具清单）→ 决定调哪个 → 输出 `mcp_approval_request`（含 `id`、`name`、`arguments`、`server_label`），Response 结束。
2. 第 2 轮：带 `previous_response_id`，`input` 放 `{"type": "mcp_approval_response", "approval_request_id": "<第1轮 id>", "approve": true, "reason": "可选"}`，并**重传同样的 `tools`**。
3. 方舟执行调用，输出 `mcp_call`（含 `arguments`、`output` / `error`），模型继续生成，可能再次发起审批。
`"never"` 则跳过 1→2，一轮内直接出现 `mcp_list_tools` → `mcp_call` → `message`。

**示例请求**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/responses \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -H "ark-beta-mcp: true" \
  -d '{
    "model": "doubao-seed-2-1-pro-260628",
    "stream": true,
    "tools": [{
      "type": "mcp",
      "server_label": "deepwiki",
      "server_url": "https://mcp.deepwiki.com/mcp",
      "allowed_tools": {"tool_names": ["read_wiki_structure", "ask_question"]},
      "headers": {"Authorization": "Bearer <mcp_provider_token>"},
      "require_approval": "never"
    }],
    "input": [{"role": "user", "content": [{"type": "input_text", "text": "看一下volcengine/ai-app-lab这个repo的文档"}]}]
  }'
```

```python
import os
from openai import OpenAI

client = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=os.environ["ARK_API_KEY"],
                default_headers={"ark-beta-mcp": "true"})
MODEL = "doubao-seed-2-1-pro-260628"
tools = [{"type": "mcp", "server_label": "qianchuan-mcp",
          "server_url": "https://mcp.qianchuan.com/mcp", "require_approval": "always"}]

# 1) 首轮：模型发起审批请求
first = client.responses.create(model=MODEL, tools=tools,
    input=[{"role": "user", "content": [{"type": "input_text", "text": "分析今日直播间竞价推广数据"}]}])
req = next(i for i in first.output if i.type == "mcp_approval_request")
print("待审批:", req.server_label, req.name, req.arguments)

# 2) 二轮：同意并继续（tools 必须重传）
second = client.responses.create(model=MODEL, tools=tools,
    previous_response_id=first.id,
    input=[{"type": "mcp_approval_response", "approval_request_id": req.id, "approve": True}])
for item in second.output:
    if item.type == "mcp_call":
        print("调用:", item.name, "→", (item.output or item.error))
    elif item.type == "message":
        print(item.content[0].text)
```

**示例响应**（输出项）

```json
[
  {"type": "mcp_list_tools", "id": "…", "server_label": "deepwiki",
   "tools": [{"name": "ask_question", "description": "…", "input_schema": {"…": "…"}, "annotations": {}}],
   "error": null},
  {"type": "mcp_approval_request", "id": "mcpr_…", "server_label": "deepwiki",
   "name": "ask_question", "arguments": "{\"repoName\":\"volcengine/ai-app-lab\",…}"},
  {"type": "mcp_call", "id": "…", "server_label": "deepwiki", "name": "ask_question",
   "arguments": "{…}", "output": "…", "error": null},
  {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "…"}]}
]
```
流式事件：`response.mcp_list_tools.in_progress` / `.completed`、`response.mcp_call_arguments.delta`（`arguments` 增量，`output_item.added` 时可能还没有该字段）、`response.mcp_call.completed`；审批请求在 `response.output_item.done` 的 `item` 里。以上事件名取自 Go SDK 枚举 `EventType_response_mcp_*`。

**注意事项**
- 仅 Responses API；仅 Streamable HTTP；不支持本地 MCP。
- 需「完成 MCP 服务开通及对应模型权限申请」，否则无法触发（文档原文，未实测）。
- 账号 1000 RPM，超限失败，扩容提工单。
- 计费只算模型 tokens；MCP 工具本身若第三方收费与方舟无关。
- 可与自定义函数、Web Search、Knowledge Search 混用，组合数量不限；不能与豆包助手混用。
- `caching` → 400（文档原文，未实测）。

---

## 6. 豆包助手

### 豆包助手 `doubao_app`
**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/v3/responses` + 头 `ark-beta-doubao-app: true`
**用途**: 把「豆包 App 同款」四种能力之一（日常沟通 / 深度沟通 / 联网搜索 / 边想边搜）作为一个黑盒工具接进自己的应用。与 Web Search + 自己写 prompt 的区别：效果对齐豆包 App、按次计费不算 token，但**不可调内部参数、不可混用任何其他工具或函数、只支持文本输入、不能调 `temperature` / `top_p` / `max_tokens`**。Beta，需要销售 / 工单申请资格。

**功能标识**（`tools[].feature.<key>`，**单次只能开一个**）

| key | 名称 | 特点 |
|---|---|---|
| `chat` | 日常沟通 | 轻量自然对话，无实时信息 |
| `deep_chat` | 深度沟通 | 输出思维链 + 结构化回答，无实时数据 |
| `ai_search` | 联网搜索 | 实时搜索，侧重结果呈现（流式可见 `queries`） |
| `reasoning_search` | 边想边搜 | 思考 ↔ 搜索多轮交替，逻辑链完整 |

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `type` | string | 是 | — | 固定 `doubao_app` |
| `feature` | object | 是 | — | 四个子对象 `chat` / `deep_chat` / `ai_search` / `reasoning_search` |
| `feature.<key>.type` | string | 否 | `disabled` | `enabled` / `disabled`；只能有一个 `enabled` |
| `feature.<key>.role_description` | string | 否 | `你的名字是豆包,有很强的专业性。` | 自定义角色。⚠ 文档自相矛盾：参数页说与 system prompt / `instructions`「互斥，同时配置时以本字段为准」；FAQ 说同时指定「返回 400 错误」（文档原文，未实测）。自定义 system prompt 需工单申请 |
| `user_location` | object | 否 | — | `type: approximate` + `country` / `region` / `city`，只支持行政区划级别 |
| 顶层 `store` / `previous_response_id` | — | 否 | — | 连续对话最多 20 轮；`store` 不保存 `tools`，每轮重传 |
| 顶层 `max_tool_calls` | — | — | — | 当前无效，传了报冲突错误（文档原文，未实测） |

**示例请求**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/responses \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -H "ark-beta-doubao-app: true" \
  -d '{
    "model": "doubao-seed-2-1-pro-260628",
    "stream": true,
    "tools": [{
      "type": "doubao_app",
      "feature": {"ai_search": {"type": "enabled", "role_description": "你是科技领域助手，专业解答行业问题"},
                  "chat": {"type": "disabled"}, "deep_chat": {"type": "disabled"}, "reasoning_search": {"type": "disabled"}},
      "user_location": {"type": "approximate", "country": "中国", "region": "浙江", "city": "杭州"}
    }],
    "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "今天有什么AI领域热点新闻"}]}]
  }'
```

```python
import os
from openai import OpenAI

client = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=os.environ["ARK_API_KEY"],
                default_headers={"ark-beta-doubao-app": "true"})
tools = [{"type": "doubao_app",
          "feature": {"reasoning_search": {"type": "enabled",
                      "role_description": "你是专业资讯助手，通过搜索获取准确信息，详细说明思考过程"}}}]
resp = client.responses.create(
    model="doubao-seed-2-1-pro-260628",
    input=[{"role": "user", "content": "2024年AI行业有哪些重大技术突破？"}],
    tools=tools, stream=True, store=True)
final = None
for ev in resp:
    if ev.type == "response.completed":
        final = ev
    elif ev.type.startswith("response.doubao_app_call."):
        print(ev)                      # 见下方事件列表
print(final.response.usage.tool_usage, final.response.usage.tool_usage_details)
# ToolUsage(doubao_app=1) ToolUsageDetails(doubao_app={'ai_search': 1})
```

**示例响应**（输出项与事件）
- 输出项 `type: "doubao_app_call"`，内容在 `blocks[]`：每块 `type`（如 `output_text`）、`id`、`parent_id`、`status`、`text`。⚠ 除 `output_text` 外的 block 类型（思维链、搜索）文档未列出。
- 流式事件（Go SDK 枚举）：`response.doubao_app_call.search.searching`（`searching_state`）、`response.doubao_app_call.search.completed`（`summary`，如「搜索 2 个关键词，参考 5 篇资料」）、`response.doubao_app_call.reasoning_search.completed`、`response.doubao_app_call.output_text.delta` / `.done`、`response.doubao_app_call.reasoning_text.delta` / `.done`。⚠ 事件名由 Go 枚举名 `EventType_response_doubao_app_call_search_searching` 等推断，分隔点位置待实测。
- `usage.tool_usage.doubao_app` 计次，`tool_usage_details.doubao_app` 按 feature 细分。

**注意事项**
- 不能与 Web Search / Knowledge Search / MCP / Image Process / 自定义函数任何一个混用。
- 仅文本输入，不支持图片、视频。
- 账号 2 QPS，扩容提工单；「功能未授权」错误 = 未开通豆包助手 API。
- `caching` → 400（文档原文，未实测）。
- 对外宣传须写「本产品由豆包助手 API 提供技术支持」，不得称「与豆包联合出品」。

---

## 7. 接入三方工具

「接入三方工具」页（2026-09-01 更新）覆盖的是 **AI 编程工具 / 聊天客户端**，不含 Dify / LangChain / LlamaIndex / n8n（⚠ 文档未说明；这些框架按 OpenAI 兼容协议配 `base_url=https://ark.cn-beijing.volces.com/api/v3` + `api_key=$ARK_API_KEY` + `model=<Model ID>` 即可，但无官方页面背书）。

**协议与 Base URL（标准 API，用方舟 API Key）**

| 协议 | Base URL | 适用工具 |
|---|---|---|
| Anthropic 兼容 | `https://ark.cn-beijing.volces.com/api/compatible` | Claude Code（含 IDE 插件、CC Switch） |
| OpenAI 兼容 | `https://ark.cn-beijing.volces.com/api/v3` | Chatbox、Cherry Studio、OpenClaw、TRAE、Cline、Cursor、Kilo Code、Roo Code、OpenCode、Codex CLI |

对照 Agent Plan：Anthropic 兼容 `https://ark.cn-beijing.volces.com/api/plan`，OpenAI 兼容 `https://ark.cn-beijing.volces.com/api/plan/v3`，用 Agent Plan 专属 Key。页面反复提示「个人开发场景推荐订阅 Agent Plan」。注意 `auth.md` 写标准 API「文档未列出 Anthropic 兼容入口」——本页给出了 `/api/compatible`，以本页为准。所有工具配置前需在控制台「开通管理」开通对应模型。

### Chatbox
Settings › Model Provider › 添加提供商，**API Mode** = `OpenAI API Compatible`；**API Host** `https://ark.cn-beijing.volces.com/api/v3`；**API Path** `/chat/completions`；**API Key** 方舟 Key；**Model** 填 Model ID。

### Cherry Studio
设置 › 模型服务 › 添加提供商，**提供商类型** = `OpenAI`；**API 地址** `https://ark.cn-beijing.volces.com/api/v3`；**API 密钥** 方舟 Key；「添加模型」填 Model ID。

### Codex CLI
`npm i -g @openai/codex`（Node.js ≥ 18）。配置 `~/.codex/config.toml`（Windows `%USERPROFILE%\.codex\config.toml`）：
```toml
model = "<Model ID>"
model_provider = "volcengine"

[model_providers.volcengine]
name = "volcengine"
base_url = "https://ark.cn-beijing.volces.com/api/v3"
env_key = "ARK_API_KEY"        # 环境变量名，值另行 export
wire_api = "responses"
```
可选：`model_supports_reasoning_summaries = true` 开推理、`model_reasoning_effort = "low" | "medium" | "high"`；`minimax-m2.7`、`kimi-k2.6`、`kimi-k2.7-code` 不支持 `model_supports_reasoning_summaries = true`。然后 `export ARK_API_KEY=...`（zsh 写 `~/.zshrc`，Windows `setx`）。页面还提到「Coding Plan 支持 Responses API，可以使用最新版 Codex CLI」。

### Claude Code
`npm install -g @anthropic-ai/claude-code`（Node.js ≥ 18；Windows 另装 Git for Windows）。`~/.claude/settings.json`：
```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "<ARK_API_KEY>",
    "ANTHROPIC_BASE_URL": "https://ark.cn-beijing.volces.com/api/compatible",
    "ANTHROPIC_MODEL": "doubao-seed-2-1-pro-260628",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "doubao-seed-2-0-lite-260428",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "doubao-seed-2-1-pro-260628",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "doubao-seed-2-1-pro-260628",
    "CLAUDE_CODE_SUBAGENT_MODEL": "doubao-seed-2-1-pro-260628"
  }
}
```
再在 `~/.claude.json` 写 `{"hasCompletedOnboarding": true}`，新终端 `claude`，`/status` 验证。建议 Haiku 槽位用小模型、Subagent 与主模型一致。⚠ 文档自相矛盾：正文示例 Haiku 用 `doubao-seed-2-0-lite-260428`，注意框写 `doubao-seed-2-0-lite-250428`（模型列表里只有 260428 / 260215）。
- **CC Switch**（多工具配置管理器）：`brew tap farion1231/ccswitch && brew install --cask cc-switch`；添加供应商 → 自定义配置 → 请求地址 `https://ark.cn-beijing.volces.com/api/compatible` + API Key，高级选项里分别填 Sonnet / Opus / Fable / Haiku 模型，启用后新开会话。
- **VS Code 插件**（也适用 Cursor / Trae）：`/config` → Edit in settings.json，`claudeCode.environmentVariables` 里放 `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL`，并设 `claudeCode.selectedModel`。JetBrains 插件安装后直接复用 CLI 配置。

### OpenCode
`npm install -g opencode-ai`。`~/.config/opencode/opencode.json`：
```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "myprovider": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "volcengine",
      "options": {"baseURL": "https://ark.cn-beijing.volces.com/api/v3", "apiKey": "<ARK_API_KEY>"},
      "models": {"doubao-seed-evolving": {"name": "doubao-seed-evolving"}}
    }
  }
}
```
启动 `opencode`，`/models` 选模型。（示例 model 用的是不带日期的 `doubao-seed-evolving`，它在模型列表里是「快速迭代模型」Model ID。）

### OpenClaw（原 Clawdbot）
安装 `curl -fsSL https://openclaw.ai/install.sh | bash`（Windows `iwr -useb https://openclaw.ai/install.ps1 | iex`），向导里 Model/auth provider、channel、skills、hooks 全选 Skip / No，Hatch in Terminal。编辑 `~/.openclaw/openclaw.json`（或 `openclaw dashboard` › Settings › Advanced），只更新 `models` / `agents` / `gateway` 节点：
```json
{
  "models": {"providers": {"volcengine": {
      "baseUrl": "https://ark.cn-beijing.volces.com/api/v3",
      "apiKey": "<ARK_API_KEY>",
      "api": "openai-completions",
      "models": [{"id": "doubao-seed-1-8-251228", "name": "doubao-seed-1-8-251228"}]}}},
  "agents": {"defaults": {"model": {"primary": "volcengine/doubao-seed-1-8-251228"},
                          "models": {"volcengine/doubao-seed-1-8-251228": {}}}},
  "gateway": {"mode": "local"}
}
```
`openclaw gateway restart` 生效；`openclaw tui` + `/status` 检查。`glm-5.2` / `deepseek-v4-flash` / `deepseek-v4-pro` 支持 1M 上下文，可用 `contextWindow` 字段显式指定。⚠ 官方示例模型 `doubao-seed-1-8-251228` 在模型列表里已标「即将下线」，实际请换 2.x。

### TRAE（CN）
设置 › 模型 › 添加模型：**服务商** = 火山引擎；模型从预置列表选或「使用其他模型」填 Model ID；API 密钥填方舟 Key。对话框右下角切换模型。

### Cline / Roo Code / Kilo Code（VS Code 扩展）
三者配置一致：**API Provider** = `OpenAI Compatible`；**Base URL** `https://ark.cn-beijing.volces.com/api/v3`；**API Key** 方舟 Key；**Model (ID)** 填 Model ID。Kilo Code 先选「Use your own API key」。⚠ 文档在这三节写「（Agent Plan 接口兼容 OpenAI 标准）」却给的是标准 API 的 `/api/v3`——若要走 Agent Plan 套餐，Base URL 应为 `/api/plan/v3` + 专属 Key，否则按 token 后付费。

### Cursor
仅 Cursor Pro 及以上可自定义模型。Models 模块：OpenAI API Key 填方舟 Key；Override OpenAI Base URL `https://ark.cn-beijing.volces.com/api/v3`；Add Custom Model 填 Model ID。

---

## 来源页面

| 标题 | URL | 文档更新时间 |
|---|---|---|
| 工具概述 | https://www.volcengine.com/docs/82379/1827538 | 2026-08-10 |
| Web Search（联网内容插件） | https://www.volcengine.com/docs/82379/1756990 | 2026-07-30 |
| Image Process（图像处理） | https://www.volcengine.com/docs/82379/1798161 | 2026-08-10 |
| 私域知识库搜索 Knowledge Search | https://www.volcengine.com/docs/82379/1873396 | 2026-08-03 |
| 云部署 MCP / Remote MCP | https://www.volcengine.com/docs/82379/1827534 | 2026-08-10 |
| 豆包助手 | https://www.volcengine.com/docs/82379/1978533 | 2026-08-10 |
| 接入三方工具 | https://www.volcengine.com/docs/82379/2160841 | 2026-09-01 |
| 工具调用（使用 Responses API） | https://www.volcengine.com/docs/82379/1958524 | 2026-08-04 |
| 创建 Response（仅取 `tools` / 输出项 / `usage` 字段定义） | https://www.volcengine.com/docs/82379/1569618 | 2026-08-25 |
| 模型列表（仅取「工具调用能力」表） | https://www.volcengine.com/docs/82379/1330310 | 2026-09-02 |
| 豆包搜索（Agent Plan Harness，仅用于开头的区分说明） | https://www.volcengine.com/docs/82379/2301412 | 2026-08-03 |
