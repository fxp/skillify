---
name: bigmodel-cn
description: 接入智谱AI开放平台（bigmodel.cn / open.bigmodel.cn，GLM 系列模型）的完整 API 使用手册。当用户需要调用智谱/bigmodel.cn/GLM/CogView/CogVideoX/Zhipu AI 的任何能力时都应使用本技能——包括但不限于：GLM 对话补全（含流式、函数调用、深度思考、多模态）、图像生成（GLM-Image/CogView）、视频生成（CogVideoX/Vidu）、语音识别与合成（GLM-ASR/GLM-TTS/音色克隆）、文本向量与重排序（Embedding/Rerank）、联网搜索、网页阅读、内容安全审核、文档解析与 OCR、文件与批处理（Batch）API、托管知识库/RAG 检索、平台内置智能体（Agents/Assistant API）、GLM-Realtime 实时语音视频通话，以及通过 OpenAI SDK / Claude API / LangChain 兼容层快速迁移接入；也包括 GLM Coding Plan（编程套餐）的接入与排错——Coding Plan 的 API Key、Base URL、可用模型都与标准 API 不同，在 Claude Code / OpenCode / Kilo Code 等工具里配置套餐、或遇到"买了套餐却报 1113 余额不足"时也应加载本技能。只要用户提到"接入智谱""bigmodel.cn""open.bigmodel.cn""GLM 模型""智谱开放平台""zai-sdk""zhipuai""GLM Coding Plan""编程套餐"，或者要求写代码调用上述任意能力，都应主动加载本技能，不要凭记忆编造接口参数。
---

# 智谱AI开放平台（bigmodel.cn）接入指南

智谱开放平台（`bigmodel.cn`，API 域名 `open.bigmodel.cn`）是智谱 AI 的一站式大模型开发平台，提供 GLM 系列文本/多模态大模型、图像与视频生成、语音识别与合成、向量检索、联网搜索、托管知识库、Agent 等一整套 API。本技能包把官方开发者文档（`docs.bigmodel.cn`）浓缩成可直接照抄的调用规范，目标是让你写出**第一次就能跑通**的接入代码，而不是凭印象编参数名。

## 用之前先确认四件事

1. **先分清用户手里是标准 API Key 还是 GLM Coding Plan（编程套餐）Key**。两者是两套隔离的计费体系：Key 不通用、Base URL 不同（标准 `…/api/paas/v4` vs 套餐 `…/api/coding/paas/v4`）、套餐只含 `glm-5.3` / `glm-5.3-flash` 对话能力且只能在指定编码工具里用。用套餐 Key 打标准端点会报 `1113 余额不足`，这不是要充值。用户提到 "Coding Plan""编程套餐""Claude Code 套餐""套餐额度" 时，先读 [`references/coding-plan.md`](references/coding-plan.md)；下面 2–4 条默认针对标准 API。
2. **Base URL 固定为** `https://open.bigmodel.cn/api/`，所有接口路径都拼在它后面，例如完整地址是 `https://open.bigmodel.cn/api/paas/v4/chat/completions`。
3. **鉴权统一是 HTTP Bearer**：请求头 `Authorization: Bearer <API_KEY>`。API Key 从控制台获取：`https://bigmodel.cn/usercenter/proj-mgmt/apikeys`。永远不要把 Key 硬编码进代码，用环境变量（如 `ZHIPUAI_API_KEY`）读取。
4. **先确认 `model` 字段**：智谱的模型迭代很快，很多模型名字长得很像（如 `glm-4.6` vs `glm-4.6v` vs `glm-4.6v-flash`）。调用前对照 [`references/models.md`](references/models.md) 核实模型代码和它支持的能力（是否支持视觉输入、工具调用、思考模式等），选错模型是最常见的接入 bug 来源。

## 30 秒跑通第一个请求

```bash
curl -X POST "https://open.bigmodel.cn/api/paas/v4/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ZHIPUAI_API_KEY" \
  -d '{
    "model": "glm-5.3",
    "messages": [{"role": "user", "content": "你好，请介绍一下自己。"}],
    "stream": false
  }'
```

```python
import os, requests

resp = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    headers={"Authorization": f"Bearer {os.environ['ZHIPUAI_API_KEY']}"},
    json={
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "你好，请介绍一下自己。"}],
    },
)
resp.raise_for_status()
print(resp.json()["choices"][0]["message"]["content"])
```

这只是最基础的同步文本对话。**真正开发时几乎总会用到下面某个能力域的参考文档** —— 直接跳到对应文件，里面有精确的字段表、curl/Python 示例、响应示例和踩坑提示，全部来自官方 OpenAPI 定义，不是凭空写的。

## 能力域导航

按你要实现的功能去读对应的参考文件，**不需要每次都通读全部文件**——这些文件是为按需查阅设计的：

| 我想做什么 | 参考文件 | 涉及的核心 endpoint |
| :--- | :--- | :--- |
| 文本对话、流式输出、函数调用（Function Calling）、多模态输入（图/视频/文件）、深度思考、结构化输出、上下文缓存、异步对话 | [`references/chat.md`](references/chat.md) | `POST /paas/v4/chat/completions`、`POST /paas/v4/async/chat/completions`、`GET /paas/v4/async-result/{id}` |
| 文生图/图生图、文生视频/图生视频/首尾帧、语音识别（ASR）、语音合成（TTS）、音色克隆 | [`references/media.md`](references/media.md) | `POST /paas/v4/images/generations`、`POST /paas/v4/videos/generations`、`POST /paas/v4/audio/transcriptions`、`POST /paas/v4/audio/speech`、`POST /paas/v4/voice/clone` 等 |
| 文本向量化（Embeddings）、重排序（Rerank）、Token 计数、文档版式解析、联网搜索、网页阅读、内容安全审核 | [`references/tools.md`](references/tools.md) | `POST /paas/v4/embeddings`、`POST /paas/v4/rerank`、`POST /paas/v4/tokenizer`、`POST /paas/v4/layout_parsing`、`POST /paas/v4/web_search`、`POST /paas/v4/reader`、`POST /paas/v4/moderations` |
| 文件上传/管理、大文件异步解析、OCR、批量处理（Batch，类似 OpenAI Batch API） | [`references/files-batch.md`](references/files-batch.md) | `POST /paas/v4/files`、`POST /paas/v4/files/parser/*`、`POST /paas/v4/files/ocr`、`POST /paas/v4/batches` |
| 平台内置智能体对话、助手（Assistant）API、托管知识库（上传文档自动切分/向量化/检索）、多模态检索、Agentic 应用调用 | [`references/agents-assistant-knowledge.md`](references/agents-assistant-knowledge.md) | `POST /v1/agents`、`POST /paas/v4/assistant`、`POST /llm-application/open/knowledge*`、`POST /zrag/*` |
| 用现成的 OpenAI SDK / Claude API SDK / LangChain 快速接入，或用官方 Python/Java SDK | [`references/sdk-and-compat.md`](references/sdk-and-compat.md) | 兼容层 base_url 配置方式 |
| 我买的是 GLM Coding Plan（编程套餐）：在 Claude Code / OpenCode / Kilo Code / Cherry Studio 里配置套餐、在自己代码里用套餐 Key、套餐 Key 报 1113、套餐与标准 API 的区别、套餐附赠的 MCP 工具 | [`references/coding-plan.md`](references/coding-plan.md) | `https://open.bigmodel.cn/api/coding/paas/v4/*`、`https://open.bigmodel.cn/api/anthropic/v1/messages` |
| 实时语音/视频通话（WebSocket） | [`references/realtime.md`](references/realtime.md) | GLM-Realtime WebSocket 协议 |
| 该用哪个模型、模型上下文/输出上限、思考模式默认行为 | [`references/models.md`](references/models.md) | — |
| 报错排查、重试策略、速率限制 | [`references/errors-and-limits.md`](references/errors-and-limits.md) | — |

## 跨领域的通用规则（写代码前必读）

这几条不属于任何单一接口，但几乎每个能力域都会踩到：

- **标准 API 与 Coding Plan 不能混用**：套餐 Key 只能打 `…/api/coding/paas/v4`（或 `…/api/anthropic`），标准 Key 走 `…/api/paas/v4`。同一个项目里如果既要用套餐额度跑对话、又要调 embeddings / 生图等套餐不含的能力，就要**同时管理两个 Key、两个 Base URL**，分开命名（如 `GLM_CODING_PLAN_API_KEY` 与 `ZHIPUAI_API_KEY`）。详见 `references/coding-plan.md`。
- **同步 vs 异步的选择**：图像生成、视频生成、部分对话场景都同时提供同步和异步两种接口。视频生成**只有**异步接口。异步接口统一返回一个任务 id，用通用的 `GET /paas/v4/async-result/{id}` 轮询结果——这个查询接口在 `references/chat.md` 里有详细说明，`media.md` 直接复用它，不要重复实现两套轮询逻辑。
- **流式输出统一是 SSE**：`stream: true` 后响应是 `Server-Sent Events`，以 `data: [DONE]` 结束。消费代码要按行解析 `data:` 前缀的 JSON，并且要检查每个 chunk 的 `finish_reason`（流式没有独立的错误码，异常会体现在 `finish_reason` 里）。详见 `references/chat.md`。
- **深度思考（thinking）因模型而异**：`glm-5.3`/`glm-5.3-flash` 在标准端点强制开启思考、传 `disabled` 报 `1210`，只能用 `reasoning_effort` 调节强度（Coding 端点实测反而能关，两端点校验不一致）；`glm-4.5` 以下版本完全不支持 `thinking` 参数。写通用封装代码时不要假设所有模型行为一致，参考 `references/models.md` 里的对照表。
- **速率限制按并发数计算，不是 QPS**，且没有 API 可查询具体额度（只能去控制台看）。批量/非实时场景优先用 Batch API 或异步接口，不要对同步接口猛发并发请求。见 `references/errors-and-limits.md`。
- **多模态输入统一用 `content` 数组** 而不是纯字符串（`[{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "..."}}]`），图片/文件可以是 base64 data URI 或先上传拿到的文件引用，具体取决于接口，见各参考文件里的示例。
- **默认开启 AI 生成内容水印**（图像/音频等生成类接口），关闭需要额外权限，别假设默认是关闭的。
- **RAG（检索增强生成）有两条路可走**：自己用 `references/tools.md` 里的 embeddings + rerank 拼 pipeline，掌控力强；或者直接用 `references/agents-assistant-knowledge.md` 里的托管知识库服务，平台代管切分/向量化/检索，省事但灵活度低。按需求复杂度选。
- **别指望 OpenAI 风格的强制 `tool_choice` 能生效**：`tool_choice` 目前只支持字符串 `"auto"`。传 `{"type":"function","function":{"name":"x"}}` 这种强制指定单个函数的写法——已用真实 API 验证：不会报错，但会被当成 `auto` 静默处理，模型完全可能对无关问题直接跳过工具调用。如果业务上"某个函数必须被调用"是硬性要求（如客服机器人必须先查订单），不要依赖这个参数，改成在代码里无条件先调用该函数、再把结果作为上下文喂给模型。
- **`response_format: {"type":"json_schema", ...}` 目前不受支持，会被静默忽略**：已用真实 API 验证——传这个参数不报错，但约束完全不生效，模型可能返回夹带解释文字的自由文本而不是合法 JSON。需要保证输出是合法 JSON 时，只能用 `response_format: {"type":"json_object"}` 搭配在 prompt 里明确描述目标字段结构，并且客户端仍要做 `json.loads` 失败重试/校验兜底，不能假设返回值 100% 合法。

## 目录结构

```
bigmodel-cn/
├── SKILL.md                              # 你正在读的这份，能力域导航 + 通用规则
└── references/
    ├── models.md                         # 模型目录、选型建议、max_tokens/thinking 对照表
    ├── chat.md                           # 对话补全全家桶：流式/函数调用/结构化输出/思考/缓存
    ├── media.md                          # 图像/视频生成、语音识别与合成、音色克隆
    ├── tools.md                          # Embeddings/Rerank/Tokenizer/文档解析/联网搜索/网页阅读/内容安全
    ├── files-batch.md                    # 文件管理、文件解析服务、OCR、批量处理 Batch API
    ├── agents-assistant-knowledge.md     # 内置智能体、Assistant API、托管知识库/RAG、Agentic 应用调用
    ├── sdk-and-compat.md                 # OpenAI/Claude/LangChain 兼容层、官方 Python/Java SDK
    ├── coding-plan.md                    # GLM Coding Plan（编程套餐）：专用 Key/Base URL、可用模型、Claude Code 配置、1113 排错
    ├── realtime.md                       # GLM-Realtime 实时语音视频 WebSocket 协议
    └── errors-and-limits.md              # 错误码、速率限制、重试与并发建议
```

所有内容整理自官方文档站 `docs.bigmodel.cn`（数据抓取于 2026-09）。平台迭代较快，如果某个字段/模型在实际调用中报"参数非法"或"模型不存在"，优先信任 API 的实际报错，并建议用户去 `docs.bigmodel.cn` 核实最新情况，而不是死守本技能包的内容。
