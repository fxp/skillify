---
name: elevenlabs
description: 接入 ElevenLabs（elevenlabs.io / elevenlabs.io/docs，域名 api.elevenlabs.io）语音 AI 平台的 API 使用手册——涵盖文本转语音 Text to Speech（含 WebSocket/SSE 流式）、语音转文本 Speech to Text（Scribe，含实时转录）、语音克隆与设计 Voice Cloning/Voice Design（Instant/Professional Voice Cloning 的同意与验证要求）、对话式语音 Agent 平台 ElevenAgents（Conversational AI，原 Conversational AI Platform）、以及各产品的计费单位与并发限制。当用户提到 "ElevenLabs""elevenlabs.io""xi-api-key""Scribe""ElevenAgents""Conversational AI agent""Eleven v3""eleven_multilingual_v2""eleven_flash""elevenlabs-js""@elevenlabs/elevenlabs-js""elevenlabs (Python)" 或要求写代码调用文本转语音、语音克隆、语音转录、构建语音助手/电话机器人等能力时，应主动使用本技能，不要凭记忆编造 model_id、接口路径或误用其他语音平台（如 OpenAI TTS/Whisper、Azure Speech、Deepgram、PlayHT）的接口习惯。
---

# ElevenLabs 接入指南

ElevenLabs（elevenlabs.io）是语音 AI 平台，API 覆盖四块：文本转语音（TTS，含批量/流式/WebSocket 三种形态）、语音转文本（STT，产品名 Scribe，含批量/实时两种形态）、语音克隆与设计（Instant/Professional Voice Cloning、Voice Design/Remix）、对话式语音 Agent 平台（ElevenAgents，文档站内也称 "Agents Platform"/"Conversational AI"，把 STT + LLM + TTS + 打断/轮次控制打包成一个实时语音助手）。
**本页只做分流与规则，字段表和示例在 `references/`。**

## ⚠ 验证状态

**本 skill 尚未用真实 API Key 验证，全部内容来自官方文档原文（含 llms.txt 索引页、API Reference 的展开 Markdown、模型页与定价页，抓取于 2026-09-21），标 `⚠ 文档原文，未实测` 的结论一律未经真实调用确认。** 用户明确要求先完成抓取与结构化撰写（第 1、2 步），验证与对照实验（第 3、4 步）留到拿到 Key 之后再做，计划见 `elevenlabs-workspace/verification-plan.md`。

尤其要注意：本 skill 里所有"会报错""会静默失效""必填字段" 之类的行为描述，全部是文档措辞或 OpenAPI 规范的转录，不是实测结果——文档本身完全可能有错（参见 create-doc-skill 方法论的教训：AutoDL 文档就把 GET 接口的传参方式写错了）。拿到 Key 后按验证计划逐条打真实请求，发现不一致立刻回来改这份 skill，并把验证日期和报错原文写回对应位置。

另外，`https://elevenlabs.io/docs/openapi.json`（及 `.yaml`、`asyncapi.json`）在抓取时返回 `401 {"error":"Unauthorized"}`——即使不带任何 Header 直接用浏览器打开也是如此，说明官方的原始 OpenAPI/AsyncAPI 规范文件目前需要登录态或额外授权才能访问，不是本环境的网络问题。本 skill 的字段表全部来自 API Reference 每个 endpoint 自己的 Markdown 导出页（`/docs/api-reference/.../xxx.md`），这些页面本身就包含完整的参数表和多语言 SDK 示例，可读性不低于展开后的 OpenAPI 摘要，但**没有做"规范与文档互相校验"这一步**，请在验证阶段留意。

## 用之前先确认 3 件事

1. **Base URL 固定为 `https://api.elevenlabs.io`**；企业数据驻留客户另有区域专属域名：`api.us.elevenlabs.io`（默认已是全球就近路由，"opt-in 到 US" 只是显式锁定）、`api.eu.residency.elevenlabs.io`、`api.in.residency.elevenlabs.io`、`api.sg.residency.elevenlabs.io`（文档原文，未实测）。WebSocket 用 `wss://api.elevenlabs.io/...`。
2. **鉴权 header 是 `xi-api-key: <key>`，不是 `Authorization: Bearer`。** 这是 ElevenLabs 与大多数平台不同的地方，官方文档反复用这个 header 名。部分端点（浏览器端场景）支持"single-use token"作为替代鉴权，见 `references/text-to-speech.md` 与 `references/speech-to-text.md` 里的说明。
3. **最容易选错的字段是 `model_id`，且不同产品线的"缺省行为"不一样：** TTS 的 `model_id` 是可选参数，缺省会静默落到 `eleven_multilingual_v2`（不报错，但可能不是你想要的延迟/质量档位）；STT 的 `model_id` 在 `POST /v1/speech-to-text` 是**必填**参数——两者行为相反，抄错一边就会得到"能跑但选错模型"或者"直接 422"两种完全不同的失败模式。具体 model_id 清单见 `references/models.md`，不要凭训练记忆编（`eleven_turbo_v2_5` 已被标为过时，官方建议换 `eleven_flash_v2_5`）。

## 30 秒跑通第一个请求

最便宜的只读请求：列出可用模型。

```bash
curl 'https://api.elevenlabs.io/v1/models' \
  -H 'Content-Type: application/json' \
  -H "xi-api-key: $ELEVENLABS_API_KEY"
```

```python
import os
from elevenlabs.client import ElevenLabs

client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
print(client.models.list())
```

Python 包名是 `elevenlabs`（`pip install elevenlabs`，`from elevenlabs.client import ElevenLabs` 或 `from elevenlabs import ElevenLabs`），REST API 和 ElevenAgents 共用同一个包。Node/TS 包名是 `@elevenlabs/elevenlabs-js`（`import { ElevenLabsClient } from "@elevenlabs/elevenlabs-js"`）。ElevenAgents 前端场景另有独立的 `@elevenlabs/client`（原生 JS）、`@elevenlabs/react`、`@elevenlabs/react-native` 包，不要和 REST SDK 混淆（文档原文，未实测）。

## 能力域导航

| 我想做什么 | 参考文件 | 涉及的核心 endpoint |
| :--- | :--- | :--- |
| 选模型：TTS 该用哪个模型、STT 该用哪个模型、延迟/质量/语言怎么取舍 | [`models.md`](references/models.md) | `GET /v1/models` |
| 把文本转成语音：批量、SSE 流式、WebSocket 双向流式、发音词典、请求拼接 | [`text-to-speech.md`](references/text-to-speech.md) | `POST /v1/text-to-speech/{voice_id}`、`.../stream`、`.../stream-input`（WS） |
| 把语音转成文本：批量转录、Webhook 异步、实时 WebSocket 转录、说话人分离、关键词提示 | [`speech-to-text.md`](references/speech-to-text.md) | `POST /v1/speech-to-text`、`.../speech-to-text/realtime`（WS） |
| 克隆一个真人的声音，或从文字描述设计一个新声音；同意与验证要求 | [`voices.md`](references/voices.md) | `POST /v1/voices/add`（IVC）、`POST /v1/voices/pvc`（PVC）、`POST /v1/text-to-voice/design`（Voice Design） |
| 搭一个能打电话/网页对话的语音 Agent：架构、LLM 选型、打断与轮次控制、工具调用/MCP、SDK | [`conversational-ai.md`](references/conversational-ai.md) | `elevenlabs.conversational_ai.agents.*`（SDK 命名空间，不是 `agents.*`） |
| 搞清楚这次调用花多少钱、并发上限、credits 是什么 | [`pricing-and-limits.md`](references/pricing-and-limits.md) | 各产品 `/pricing` 页 + `GET /v1/user/subscription` |

本 skill 不覆盖：Dubbing（配音翻译）、Eleven Music（音乐生成）、Image & Video / Flows（图像视频生成）、Studio/Audiobooks 等 ElevenCreative 内容生产工作流、Reception AI（前台预约类垂直产品）、企业级 Workspace/SSO/审计日志管理。这些的文档入口在 `elevenlabs.io/docs` 左侧导航，抓取范围见 `elevenlabs-workspace/scratch/llms.txt`。

## 跨领域的通用规则（写代码前必读）

1. **文档里的产品名和 SDK 里的方法名不是一回事。** 网站营销页和文档导航把语音 Agent 产品叫 "ElevenAgents" / "Agents Platform"，但 Python/JS SDK 里对应的命名空间始终是 `conversational_ai`（Python，如 `elevenlabs.conversational_ai.agents.update(...)`）/ `conversationalAi`（JS）——文档示例代码里没有任何一处出现 `client.agents.*`。凭直觉写 `client.agents.create(...)` 大概率是错的（⚠ 文档原文，未实测，但文档里几十处代码示例口径一致，可信度较高）。
2. **三种计费单位，不能互相套用。** TTS 按"credits"（官方文档写明 "Credits were previously referred to as characters"，即按字符数计，pay-as-you-go 报价约 $0.05~$0.10 / 1K 字符，视模型而定）；STT 按音频时长计（约 $0.22~$0.39 / 小时，`keyterms`/`entity_detection`/`entity_redaction`/`detect_speaker_roles` 等参数会在基础转录费上叠加 10%~30% 的附加费，开了参数不会报错但账单会变，属于"静默生效的隐藏加价"，见 `references/speech-to-text.md`）；ElevenAgents/Speech Engine 按通话分钟计（约 $0.08/分钟标准价，超出并发上限后 burst 容量按 2x 计费）。三套单位、三套计价方式，写成本估算代码前先确认调用的是哪个产品。
3. **model_id 的必填/可选方向在 TTS 和 STT 上是相反的。** 见上文"用之前先确认"第 3 条；`references/models.md` 有完整 model_id 表和延迟/质量对照。
4. **低延迟场景（实时语音 Agent、直播配音）默认高质量模型会不可用，不是"能用但慢"。** `eleven_v3` 面向内容创作，未标注具体延迟但设计上不是实时模型；`eleven_multilingual_v2` 质量最高但延迟明显高于 Flash 系列；真正为实时对话设计的是 `eleven_flash_v2_5`（~75ms 推理延迟）和 `eleven_v3_conversational`（~280ms，表现力更强）。官方模型选型指南把 "Agents Platform" 用例直接映射到 Flash / v3 Conversational，没有把 `eleven_v3`/`eleven_multilingual_v2` 列进实时候选——选型时别只看"质量最高"就默认拍 `eleven_multilingual_v2` 或 `eleven_v3` 用在语音 Agent 上。
5. **Instant Voice Cloning（IVC）和 Professional Voice Cloning（PVC）不是"快慢两版"，是两种不同技术路径**（IVC 是推理时条件化，几秒钟出结果；PVC 是真正微调模型权重，需要约 30 分钟高质量录音、耗时数分钟、且要求 Creator 及以上套餐）。两者都有身份验证步骤（voice-captcha），**但 PVC 有一条绝对规则：即使拿到本人同意，也不能替别人创建 PVC——PVC 只能克隆"账号本人"的声音，规范用法是本人验证后创建，再用分享链接私下分享给你**（来自官方 Help Center FAQ 原文，非 API 行为层面的软限制，是产品层面的强制规则）。IVC 的 `POST /v1/voices/add` 响应里有 `requires_verification` 字段，说明 IVC 有时也会触发验证流程，具体触发条件文档未说明，标 `⚠ 文档未说明`。
6. **三种 TTS 调用形态选错会导致协议、鉴权方式都不同，不是简单加个 `stream=true` 参数。** 普通端点（`POST /v1/text-to-speech/{voice_id}`）一次性返回完整音频；SSE 流式端点（`.../stream`）路径不同、逐块返回音频；WebSocket 端点（`.../stream-input`，双向）走 `wss://`、鉴权和参数都放在查询字符串或首帧消息里，不是 HTTP body。三者是三个不同的 endpoint / URL scheme，代码结构完全不同，见 `references/text-to-speech.md`。
7. **`enable_logging=false` / Zero Retention Mode 只对 Enterprise 客户开放。** TTS、STT 的请求都支持这个参数关闭历史留存，但文档原文写明"Zero retention mode may only be used by enterprise customers"——非企业账号传这个参数会发生什么（报错还是被忽略）文档未说明，标 `⚠ 文档未说明`，验证清单里已列。
8. **地理路由是默认行为，不是"未配置region"。** `api.elevenlabs.io` 默认按就近路由到美国/欧洲/东南亚等区域后端（可用响应头 `x-region` 查看实际命中区域），要固定使用美国服务器才需要显式换成 `api.us.elevenlabs.io`；企业数据驻留（EU/India/Singapore 专属环境）需要销售侧开通,不是换个 base URL 就能自助获得同等的合规保证。

## 目录结构

```
elevenlabs/
├── SKILL.md
├── references/
│   ├── models.md
│   ├── text-to-speech.md
│   ├── speech-to-text.md
│   ├── voices.md
│   ├── conversational-ai.md
│   └── pricing-and-limits.md
└── evals/
    └── evals.json
```

内容整理自 `elevenlabs.io/docs`（llms.txt 索引页 + 各 API Reference/概念页的 Markdown 导出，抓取于 2026-09-2）及 `elevenlabs.io/pricing/api`、`elevenlabs.io/pricing/agents`（定价计算器页面文本，抓取于 2026-09-21）。**实际调用报错优先信任 API**，本 skill 未经验证的内容一律标注 `⚠`，验证计划见 `elevenlabs-workspace/verification-plan.md`。
