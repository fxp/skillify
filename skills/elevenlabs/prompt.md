把这份 skill 装进你的 Agent，让它调用 ElevenLabs 语音 API 时不再把 `model_id` 在 TTS 和 STT 上的必填/可选方向搞反，也不会把三种 TTS 调用形态（普通/流式/WebSocket）当成加个参数就能切换。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill elevenlabs --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill elevenlabs --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/elevenlabs/elevenlabs.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认 3 件事」和「能力域导航」三节；
2. `references/` 下有 6 个 `.md`，其中 `conversational-ai.md` 讲的是 ElevenAgents（对话式语音 Agent）的 SDK 命名空间和架构；
3. 在 `SKILL.md` 里能搜到「`model_id` 的必填/可选方向在 TTS 和 STT 上是相反的」字样。

## 这份 skill 覆盖什么

ElevenLabs（`elevenlabs.io/docs`，域名 `api.elevenlabs.io`）语音 AI 平台的四块能力：文本转语音 TTS（批量/SSE 流式/WebSocket 三种形态）、语音转文本 STT（产品名 Scribe，批量/实时两种形态）、语音克隆与设计（Instant/Professional Voice Cloning、Voice Design）、对话式语音 Agent 平台 ElevenAgents（把 STT+LLM+TTS+打断/轮次控制打包成实时语音助手）。

重点是两个反直觉陷阱：**`model_id` 的必填/可选方向在 TTS 和 STT 上正好相反**——TTS 的 `model_id` 是可选参数，不传会静默落到 `eleven_multilingual_v2`（不报错但可能不是想要的延迟/质量档位），而 STT 在 `POST /v1/speech-to-text` 上 `model_id` 是**必填**参数，抄错一边会得到"能跑但选错模型"和"直接 422"两种完全不同的失败模式；以及**三种 TTS 调用形态是三个不同的 endpoint / 协议**——普通端点一次性返回完整音频，SSE 流式端点路径不同、逐块返回，WebSocket 端点走 `wss://` 且鉴权/参数放在查询字符串或首帧消息里而不是 HTTP body，不是简单加个 `stream=true` 参数就能切换。此外 SKILL.md 还记录了文档营销页把语音 Agent 产品叫 "ElevenAgents"，但 SDK 里命名空间始终是 `conversational_ai`/`conversationalAi`（几十处代码示例口径一致，没有一处出现 `client.agents.*`）、三种产品线的计费单位互不通用（TTS 按字符数、STT 按音频时长且部分参数会静默叠加 10%~30% 附加费、ElevenAgents 按通话分钟计）、以及 Professional Voice Cloning 有一条产品层面的强制规则——即使拿到本人同意，也不能替别人创建 PVC。

内容不是文档搬运：整理自 `elevenlabs.io/docs` 的 `llms.txt` 索引页 + API Reference 每个 endpoint 的 Markdown 导出页 + 模型页与定价页；官方 OpenAPI/AsyncAPI 规范文件（`elevenlabs.io/docs/openapi.json` 等）在抓取时返回 401，即使不带任何 Header 也如此，说明需要登录态才能访问，本 skill 因此改用 API Reference 各 endpoint 自带的字段表，未做"规范与文档互相校验"这一步，标注在验证状态里。

## 版本

**文档版，抓取于 2026-09-21，未用真实凭证验证。** 全篇标注 `⚠ 文档原文，未实测`，没有做任何真实 API 调用，也没有做 with/without skill 的对照实验。实际调用时报错与 skill 不一致，**以 API 的真实报错为准**，并去 `elevenlabs.io/docs` 核实最新情况。
