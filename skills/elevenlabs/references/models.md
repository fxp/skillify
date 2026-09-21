# 模型选型：TTS / STT 该用哪个

> 来源：`https://elevenlabs.io/docs/overview/models.md`、`https://elevenlabs.io/docs/eleven-api/choosing-the-right-model.md`（抓取于 2026-09-21）。**全部内容为文档原文，未用真实 API 调用验证** model_id 是否仍然有效、延迟数字是否准确。`⚠ 文档原文，未实测` 适用于本文件全部内容。

## 目录

- [TTS 模型一览](#tts-模型一览)
- [按需求 / 用例选型](#按需求--用例选型)
- [字符上限](#字符上限)
- [STT 模型一览](#stt-模型一览)
- [并发与优先级](#并发与优先级)
- [已弃用模型](#已弃用模型)

## TTS 模型一览

| model_id | 说明 | 延迟（推理耗时，不含网络） | 语言数 | 字符上限/请求 |
| :--- | :--- | :--- | :--- | :--- |
| `eleven_v3` | 最具表现力/情感张力的模型，多角色对话、有声书旁白 | 未标注具体数字，设计定位非实时 | 70+ | 5,000 |
| `eleven_v3_conversational` | v3 的实时版，面向语音 Agent | ~280ms | 70+ | 未单独列出，参考 v3 |
| `eleven_multilingual_v2` | 情感最丰富的"稳定"模型，长文本最稳定 | 无 Flash 级别优化，明显慢于 Flash | 29 | 10,000 |
| `eleven_flash_v2_5` | 最快、最便宜，字符价格是 v2/v3 的一半 | ~75ms | 32（v2 语言 + 匈牙利语/挪威语/越南语） | 40,000 |
| `eleven_flash_v2` | 上一代 Flash，仅英语 | ~75ms | 1（`en`） | 30,000 |
| `eleven_multilingual_sts_v2` | Speech-to-Speech（声音转换器）专用 | — | 29 | 10,000 |
| `eleven_multilingual_ttv_v2` | Voice Design（Text to Voice）用的旧一代多语言模型 | — | 29 | — |
| `eleven_ttv_v3` | Voice Design（Text to Voice）用的 v3 模型 | — | 70+ | — |
| `eleven_english_sts_v2` | Speech-to-Speech 英语专用 | — | 1（`en`） | 10,000 |

† 延迟数字均为"模型推理耗时"，不含应用/网络传输延迟；官方原话强调这一点，实际 TTFB 会更高。

## 按需求 / 用例选型

官方选型指南（`choosing-the-right-model.md`）按两个维度给建议：

**按需求**

| 需求 | 推荐模型 |
| :--- | :--- |
| 质量优先 | `eleven_v3`（`eleven_multilingual_v2` 次选，长文本更稳） |
| 低延迟 | `eleven_flash_v2_5` 或 `eleven_flash_v2`（~75ms） |
| 实时且要表现力 | `eleven_v3_conversational`（~280ms） |
| 多语言 | `eleven_v3` 或 `eleven_v3_conversational`（70+ 语言） |
| 质量与速度平衡 | `eleven_flash_v2_5` 或 `eleven_v3_conversational` |

**按用例**

| 用例 | 推荐模型 |
| :--- | :--- |
| 内容创作（专业配音、有声书、视频旁白） | `eleven_v3`（或 `eleven_multilingual_v2`） |
| 对话式 Agent（电话/网页语音助手） | `eleven_v3_conversational`（最强表现力）或 `eleven_flash_v2_5`/`eleven_flash_v2`（最低延迟）；非英语场景用 2.5 版本 |
| 转录 | 批量用 `scribe_v2`，医疗场景用 `scribe_v2_medical`，实时用 `scribe_v2_realtime` |
| 声音转换器（Speech-to-Speech） | `eleven_multilingual_sts_v2` |

**⚠ 常见误区**：不要因为"质量最高"就把 `eleven_v3` 或 `eleven_multilingual_v2` 默认用在语音 Agent 上——官方文档在两处独立页面（`models.md` 和 `choosing-the-right-model.md`）都把 Agents Platform 用例映射到 Flash 系列或 `v3_conversational`，没有把这两个高质量模型列为实时候选。真人打电话场景下，用高延迟模型会导致用户明显感到"卡顿"，这不是文档吓唬人，是模型定位本身的取舍。

### 数字文本正规化的坑（Flash v2.5）

Flash v2.5 为了保低延迟，**默认关闭数字/日期/货币的文本正规化**（`apply_text_normalization` 默认行为），电话号码、日期可能被读错。文档原文建议：低延迟场景优先让上游 LLM 自己把文本正规化好再传给 TTS，或者传 `apply_text_normalization: "on"`（仅 Enterprise 套餐对 v2.5 系模型开放这个开关，⚠ 文档原文，未实测其他套餐传了会不会报错还是静默忽略）。`eleven_multilingual_v2` 的正规化做得更好，涉及电话号码等场景优先选它而不是 Flash。

## 字符上限

| model_id | 字符上限 | 约合音频时长 |
| :--- | :--- | :--- |
| `eleven_v3` | 5,000 | ~5 分钟 |
| `eleven_flash_v2_5` | 40,000 | ~40 分钟 |
| `eleven_flash_v2` | 30,000 | ~30 分钟 |
| `eleven_multilingual_v2` | 10,000 | ~10 分钟 |
| `eleven_multilingual_v1` | 10,000 | ~10 分钟 |
| `eleven_english_sts_v2` | 10,000 | ~10 分钟 |

超出上限需要自己拆分成多次请求（可用 `previous_text`/`previous_request_ids` 保持语调连续性，见 `references/text-to-speech.md` 的请求拼接一节）。

## STT 模型一览

| model_id | 说明 | 延迟 | 语言数 | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| `scribe_v2` | 当前旗舰批量转录模型 | 批量（非实时） | 90+ | 关键词提示最多 1000 个词、实体检测 65 类、最多 32 说话人分离、词级时间戳 |
| `scribe_v2_realtime` | 实时转录 | ~150ms | 90+ | PCM 8k~48kHz / μ-law，支持 VAD 与手动 commit |
| `scribe_v2_medical` | 临床音频微调版 | 批量 | 90+ | 与 `scribe_v2` 同接口同定价，临床音频错误率低 18%；**不做诊断**，仅供医护人员审核后使用；符合 HIPAA 资格，Enterprise 客户可签 BAA，可开 Zero Retention Mode |
| `scribe_v1` | 上一代（已被 v2 取代） | — | 90+ | 官方建议迁移到 `scribe_v2` |

STT 语言识别准确率（WER，词错误率）按语言分四档：≤5%（英语、法语、德语等 34 种主流语言）、5~10%、10~20%、25~50%（阿姆哈拉语、爱尔兰语等资源较少的语言）。做非主流语言的转录质量预期前先查一下自己的语言落在哪档，见 `overview/capabilities/speech-to-text.md` 的完整分档表。

## 并发与优先级

并发上限按套餐分级，Flash 模型的并发上限通常是 Multilingual v2 的 2 倍：

| 套餐 | Multilingual v2 并发 | Flash 并发 | STT 并发 | 实时 STT 并发 |
| :--- | :--- | :--- | :--- | :--- |
| Free | 2 | 4 | 8 | 6 |
| Starter | 3 | 6 | 12 | 9 |
| Creator | 5 | 10 | 20 | 15 |
| Pro | 10 | 20 | 40 | 30 |
| Scale | 15 | 30 | 60 | 45 |
| Business | 15 | 30 | 60 | 45 |
| Enterprise | 提升 | 提升 | 提升 | 提升 |

**⚠ 关键区分**：并发限制是"同时处理中的请求数"，不是"同时能维持的用户会话数"。官方给的经验法则是并发上限 5 大致能支撑约 100 路并发语音广播/对话（因为 TTS 生成耗时远小于音频播放耗时）。用并发上限直接当"最大同时通话数"来做容量规划会严重低估系统实际承载能力，压测方法见原文的 "Scale testing concurrency limits" 一节（附 locust 压测脚本示例）。

WebSocket 形态的计费也不同：HTTP 每次请求单独占用并发名额；TTS WebSocket 只有"模型正在生成音频"的时间段占用并发（大部分时间空闲的长连接几乎不占并发）；Text to Dialogue WebSocket（v3 对话模式）走独立的"dialogue session"计费池，一个连接从建立到关闭全程占用一个 session，与是否正在生成音频无关，20 秒无 `keep_alive` 消息会自动断开。三种计量方式，不能套用同一套并发预算模型。

## 已弃用模型

| model_id | 状态 | 替换建议 |
| :--- | :--- | :--- |
| `eleven_turbo_v2_5` | 已弃用（功能等价于 Flash，但延迟更高） | `eleven_flash_v2_5` |
| `eleven_turbo_v2` | 已弃用 | `eleven_flash_v2` |
| `scribe_v1` | 已弃用 | `scribe_v2` |

不要在新代码里再选 Turbo 系列——官方原文明确说 "outclassed by Flash models"，两者字段兼容、延迟更差，没有理由继续用。
