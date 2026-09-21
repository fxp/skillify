# 构建对话式语音 Agent（ElevenAgents / Conversational AI）

> 来源：`eleven-agents/{overview,quickstart,customization/llm,customization/conversation-flow,customization/llm/custom-llm,customization/tools/mcp,guides/burst-pricing,libraries/python}.md`（抓取于 2026-09-21）。**⚠ 全文未用真实 API Key 验证**，且这是 ElevenLabs 变化最快的产品线（文档本身多处出现未来时态的功能预告），务必以拿到 Key 后的实测为准。

## 目录

- [这是不是"三个 API 拼起来"](#这是不是三个-api-拼起来)
- [SDK 命名空间陷阱](#sdk-命名空间陷阱)
- [架构与四个核心组件](#架构与四个核心组件)
- [LLM 选择](#llm-选择)
- [自带 LLM（Custom LLM）](#自带-llmcustom-llm)
- [打断与轮次控制（Conversation flow）](#打断与轮次控制conversation-flow)
- [工具调用 / MCP](#工具调用--mcp)
- [SDK 与部署渠道](#sdk-与部署渠道)
- [Burst pricing（并发溢出计费）](#burst-pricing并发溢出计费)

## 这是不是"三个 API 拼起来"

是,但不止是拼接。ElevenAgents（文档里也叫 "Agents Platform"/"Conversational AI"）把 STT（语音识别）+ LLM（对话生成）+ TTS（语音合成）+ **一个专有的"轮次控制模型"（turn-taking model）** 打包成一个托管的实时语音会话服务。**轮次控制模型是这四个组件里唯一不能单独在 plain TTS/STT API 里买到的部分**——判断"用户是说完了还是只是停顿"这件事本身是一个独立的模型,不是简单的静音超时定时器（虽然也暴露了 `turn_timeout` 这类简单参数给你调,见下文）。如果只是想自己攒一个语音助手（自己写 STT→LLM→TTS 的胶水代码,自己写打断逻辑),ElevenAgents 提供的价值主要在打断/轮次这块和"托管的通话/呼叫基础设施"（电话号码、SIP、Twilio 集成、批量外呼），不是单纯把三个 API 换个名字重新卖。

## SDK 命名空间陷阱

**这是本 skill 里最值得单独拎出来的一条：** 网站/文档里这个产品处处被称为 "ElevenAgents"，但 Python/JS SDK 里从创建到更新 Agent 的所有方法,命名空间都是 `conversational_ai`（Python）/ `conversationalAi`（JS）,不是 `agents`：

```python
from elevenlabs import ElevenLabs
elevenlabs = ElevenLabs()
elevenlabs.conversational_ai.agents.update(agent_id="...", conversation_config={...})
elevenlabs.conversational_ai.settings.update(can_use_mcp_servers=True)
elevenlabs.conversational_ai.mcp_servers.create(config={...})
```

```typescript
import { ElevenLabsClient } from "@elevenlabs/elevenlabs-js";
const elevenlabs = new ElevenLabsClient();
await elevenlabs.conversationalAi.agents.update("agent_id", { conversationConfig: {...} });
```

Python 客户端 SDK（用于跑一个实时语音会话,不是管理配置）也是同样的模式：`from elevenlabs.conversational_ai.conversation import Conversation`。**几十处独立的官方代码示例口径完全一致,没有一处出现 `client.agents.*`**,这条可信度较高,但仍属于"读文档得出的结论,未实测"。凭直觉写 `client.agents.create(...)` 大概率是 `AttributeError`。

CLI 层面则相反,子命令确实叫 `elevenlabs agents pull/push`（不是 `conversational-ai pull`),说明"agents" 这个词在 CLI 和 dashboard UI 里通用,只有 SDK 方法命名空间坚持用 `conversational_ai`——三处（dashboard、CLI、SDK）叫法不统一,写代码时以 SDK 实际暴露的方法名为准,不要以为在 CLI/dashboard 里看到的名字能直接映射成 SDK 方法名。

## 架构与四个核心组件

官方 `eleven-agents/overview.md` 原文列出四个组件：
1. 经过微调的 STT（ASR）模型做语音识别
2. 你选择的 LLM（内置多家,或自带 Custom LLM)
3. 低延迟 TTS 模型,覆盖 5000+ 声音、70+ 语言
4. 专有的轮次控制模型,处理对话时序（打断、停顿判断)

## LLM 选择

内置支持 ElevenLabs 自家模型（Qwen3.6-35B-A3B 等）、Google Gemini 系列、OpenAI GPT 系列、Anthropic Claude 系列,在 Agent 配置里直接切换,**计费按 provider 的 token 价格单独计,不计入 ElevenLabs 的 TTS/STT credits**（"Pricing is typically denoted in USD per 1 million tokens"）。部分模型标注 "Hosted by ElevenLabs"——意味着请求在 ElevenLabs 自己的基础设施内处理,**原始模型提供商不会收到/访问你的输入输出**,这对需要避免数据流向第三方模型厂商的场景是个关键信息。

选型三个维度（官方原文）：延迟（实时语音场景要单独测,不能只看 benchmark 分数)、上下文窗口（长知识库/长对话历史场景需要)、成本（input/output/cache token 价格分开算)。**系统提示词上限是 2MB**,包含 agent instructions + knowledge base 内容 + 其他系统级上下文——知识库塞太多内容可能顶到这个上限。

**Reasoning（推理）配置**：支持 thinking budget（数值,设 0 关闭)或 reasoning effort（档位,取决于具体模型)。**官方原文明确建议:实时语音场景优先用较低的推理预算,因为额外的思考会拖慢轮次响应**——这是延迟与决策质量的直接取舍,复杂工作流步骤可以调高,但默认给语音 Agent 配置高推理预算是一个常见但错误的直觉("越聪明越好")。

**Backup LLM（降级链)**：可配置"主 LLM 失败时的备用序列",官方原文强调"禁用备用 LLM 会导致对话在主 LLM 故障时直接中断,生产环境强烈不建议禁用"。

## 自带 LLM（Custom LLM）

可以接一个自己的 OpenAI-key,或者接一个自建的、兼容 OpenAI 接口形态的 LLM 服务端（Chat Completions `/v1/chat/completions` 或 Responses API `/v1/responses` 二选一实现）。**⚠ 硬性要求:响应必须是 SSE 格式（`Content-Type: text/event-stream`),每个 chunk 格式为 `data: {json}\n\n`,流结束发 `data: [DONE]\n\n`**——普通 JSON 响应的 LLM 服务端接不上,必须自己包一层 SSE。要返回推理过程（reasoning)的话,Chat Completions 格式走响应 delta 里的 `reasoning`/`reasoning_content` 字段（Gemini 兼容端点要额外处理 `google.thinking_config.include_thoughts`),Responses API 格式走独立的 `reasoning` output item。

## 打断与轮次控制（Conversation flow）

这是 ElevenAgents 相对纯 TTS/STT 拼接最有产品差异化的一块,关键配置项（都在 `conversation_config` 下,可通过 dashboard / CLI / API 三种方式改):

| 配置项 | 字段路径 | 范围/默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| 最长对话时长 | `conversation.max_duration_seconds` | 默认 600 秒,60~7200 秒 | 全局硬上限,从对话开始计时,独立于单轮超时 |
| 静音后判定轮次结束 | `turn.turn_timeout` | 1~30 秒 | 用户沉默多久后 Agent 主动接话；WhatsApp 消息场景另有独立的 15 分钟不活跃超时,优先级高于这个全局设置 |
| Soft timeout（思考中填充语) | `turn.soft_timeout_config` | 默认关闭（`-1`),范围 0.5~8.0 秒,推荐 3.0 秒 | LLM 响应慢时先说一句"嗯..."之类的过渡语,避免尴尬沉默;每轮最多触发一次 |
| 是否允许打断 | Dashboard「Client Events」里勾选 interruption | — | 法律免责声明、安全须知等"必须完整播完"的场景应该关闭 |
| 轮次响应积极度 | `turn.turn_eagerness` | `eager` / `normal` / `patient` | 客服场景用 eager 提高响应速度;采集电话号码/邮箱等结构化信息场景用 patient,给用户更多时间说完 |

**⚠ 常见误区**：把这些参数当作"能不能打断"的开关来理解太窄——`turn_eagerness` 影响的是"多快认为用户说完了",不是单纯的打断开关,eager 模式下即使用户只是短暂停顿,Agent 也可能提前插话,选错模式在信息采集场景（电话号码、邮箱这类中间会自然停顿的输入)会导致 Agent 频繁抢话。

## 工具调用 / MCP

Agent 可以调用两类外部能力：
1. **原生 Tools**（客户端函数调用 / webhook 工具,未在本次抓取范围详细展开,⚠ 待验证补充,见 `references/` 导航表之外的 `customization/tools` 分支)。
2. **外部 MCP Server**：把 Agent 接到任意 Model Context Protocol 服务器（比如 Zapier MCP),让 Agent 能调用该 MCP 暴露的工具集。**关键规则**：
   - MCP 默认对每个 workspace 关闭,第一次有人从 dashboard 添加 MCP server 时会弹出条款确认,同意后对**整个 workspace** 生效,不是按 Agent 单独开关。
   - API 层面用 `can_use_mcp_servers` workspace 设置控制,任何有 `convai_write` 权限的 API Key 都能开关它,**不限于 admin**——这是一个容易被忽视的权限面,普通开发者的 key 就能切换全 workspace 的 MCP 开关。
   - **Zero Retention Mode 或 HIPAA 合规模式下,MCP 完全不可用,即使 `can_use_mcp_servers=true` 也无效**（原文明确写"不覆盖"这条限制)。
   - **第三方 MCP server 的安全性、合规性、行为完全是接入者自己的责任**,ElevenLabs 官方原文用"User Responsibility"单独一节撇清了这部分——把 MCP server URL 当成密码级别的密钥对待,存 workspace secret,不要明文写在配置里。
   - 支持 SSE 和 HTTP streamable 两种 MCP 传输方式；**MCP server 目前不能通过 CLI 管理,只能用 dashboard 或 SDK**（⚠ 文档原文,可能随版本变化)。

## SDK 与部署渠道

| 用途 | 包 | 备注 |
| :--- | :--- | :--- |
| REST API（含创建/管理 Agent 配置) | Python `elevenlabs`（PyPI)、JS `@elevenlabs/elevenlabs-js`（npm) | 与纯 TTS/STT 共用同一个包 |
| 浏览器原生 JS 语音会话 | `@elevenlabs/client`（npm) | 不是 `@elevenlabs/elevenlabs-js`,是独立的包 |
| React | `@elevenlabs/react`（npm) | 提供 hooks 组件 |
| React Native | `@elevenlabs/react-native`（npm) | |
| iOS | Swift,GitHub `elevenlabs/ElevenLabsSwift` | |
| Android | Kotlin,Maven `io.elevenlabs:elevenlabs-android` | |
| Flutter | `elevenlabs_agents`（pub.dev) | 社区/非核心包名单独列出 |
| CLI | `elevenlabs`（brew/npm/scoop 安装) | `elevenlabs agents pull/push --agent <name>` 把 Agent 配置拉到本地 JSON 做版本管理,`elevenlabs generate-skills` 能把 CLI 全量能力生成一批 SKILL.md（读 CLI 内嵌的 API 定义,不需要 key,离线可用) |
| 电话接入 | SIP trunk、Twilio 原生集成、批量外呼（Batch calls) | 电话号码本身走 ElevenLabs 或自带 SIP,Telephony 费用在定价页里单独列,不含在语音通话分钟费里 |

Python 客户端跑一个本地语音会话的最小骨架：

```python
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface

elevenlabs = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
conversation = Conversation(
    elevenlabs, os.getenv("AGENT_ID"),
    requires_auth=bool(os.getenv("ELEVENLABS_API_KEY")),
    audio_interface=DefaultAudioInterface(),
    callback_agent_response=lambda r: print(f"Agent: {r}"),
    callback_user_transcript=lambda t: print(f"User: {t}"),
)
```

**⚠ 公开 Agent 不需要 API key 也能跑**（文档原文:"API key is only required for non-public agents that have authentication enabled"),意味着默认创建的 Agent 若未开启 authentication,任何拿到 `agent_id` 的人都能发起对话——生产环境暴露的 Agent 应该显式检查是否开了 `authentication`,不要假设"没给 key 就连不上"。

## Burst pricing（并发溢出计费）

Agent 通话的标准并发上限之外,可以额外开启"突发容量"：并发超出订阅上限时,最多可以额外扩到 **3 倍标准并发上限,或 300 路,取较小值**（非 Enterprise 客户硬上限就是 300)，超出部分按 **2 倍标准分钟费率**计费,再超出突发上限的呼叫会被拒绝（除非同时开启了 call queueing,这种情况下呼叫方会被放进队列等待容量释放)。突发容量部分的语音处理**优先级更低**,延迟可能高于正常容量内的呼叫,不要在容量测算里把突发容量当成和标准容量同等质量的资源。开启方式：dashboard「Security → Limits → Enable bursting」,或 API 里 `platform_settings.call_limits.bursting_enabled`。
