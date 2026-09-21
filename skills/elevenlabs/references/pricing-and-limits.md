# 定价与限制

> 来源两类，标注方式不同：
> - **文档站原文**（`overview/administration/billing.md`、`overview/models.md` 的并发表、`overview/capabilities/speech-to-text.md` 的计费说明,抓取于 2026-09-21)：产品机制层面的说明,相对稳定。
> - **定价计算器页面实时抓取**（`elevenlabs.io/pricing/api`、`elevenlabs.io/pricing/agents`,用内置 Browser 于 2026-09-21 当天读取渲染后的页面文本)：具体价格数字,**这是电商类定价页,随时可能调整**,标注为"定价页原文（2026-09-21 读取）"而不是"API 文档",可信度上二者都属于"未经真实调用验证",但定价页数字比 API 文档里的价格描述更新更及时（API 文档基本不写具体价格）。
>
> **⚠ 全文未用真实 API Key 验证账单行为**（比如"传了某参数账单具体多扣了多少"这类结论完全没有实测,只是把文档里明说的加价百分比抄了下来）。

## 目录

- [核心概念：credits（原 characters）](#核心概念credits原-characters)
- [各产品计费单位速查](#各产品计费单位速查)
- [Pay-as-you-go 参考单价（定价页原文，2026-09-21）](#pay-as-you-go-参考单价定价页原文2026-09-21)
- [并发限制](#并发限制)
- [订阅套餐与 Credit Rollover](#订阅套餐与-credit-rollover)

## 核心概念：credits（原 characters）

官方原文："Credits were previously referred to as 'characters'. We updated this terminology to streamline pricing... though the value remains unchanged."——也就是说**文档里旧版提到的"characters"和新版的"credits"是同一个东西改了名字**,遇到新旧文档混用两个词不要以为是两套独立的计量单位。credits 消耗量取决于套餐、走网页还是 API、具体产品、具体模型。

## 各产品计费单位速查

| 产品 | 计费单位 | 备注 |
| :--- | :--- | :--- |
| Text to Speech | 按字符（= credits）计,`character-cost` 响应头能读到单次实际消耗 | 不同模型单价不同,Flash/v3 Conversational 比 v3/Multilingual v2 便宜一半 |
| Speech to Text | 按音频**时长**（小时）计,不是按字符 | `keyterms`/`entity_detection`/`entity_redaction`/`detect_speaker_roles` 在基础费上叠加 10%~30% 附加费（见 `references/speech-to-text.md`）；多声道按声道数 × 时长线性计费 |
| ElevenAgents / Speech Engine | 按通话**分钟**计 | LLM token 费用单独计,不算在这个分钟费里;电话号码/Telephony 费用也单独计 |
| Voice Isolator / Voice Changer / Sound Effects | 按分钟计 | |
| Music | 按分钟计,另有单独的 Finetune 一次性费用 | |
| Dubbing | 按分钟计,v1/v2 价差巨大 | v2 是端到端新模型,单价约为 v1 的 6~7 倍 |

**⚠ 关键提醒**：写"预估这次调用要花多少钱"的代码时,先确认调的是哪个产品——同一个"发一次请求"的动作,TTS 按字符数算,STT 按音频分钟数算,ElevenAgents 按通话分钟数算,三套完全不同的估算公式,不能复用同一个计价函数。

## Pay-as-you-go 参考单价（定价页原文，2026-09-21）

以下数字来自 `elevenlabs.io/pricing/api` 与 `elevenlabs.io/pricing/agents` 定价计算器页面在 2026-09-21 当天渲染的文本,**不是从 API 或 OpenAPI 规范里读到的**,随时可能变,只作数量级参考,报价前一定要让用户去定价页确认当天数字：

| 产品/模型 | Pay-as-you-go 单价 |
| :--- | :--- |
| TTS `v3` | $0.10 / 1K 字符 |
| TTS `v3 Conversational` | $0.05 / 1K 字符 |
| TTS `v2 Multilingual` | $0.10 / 1K 字符 |
| TTS `Flash / Turbo` | $0.05 / 1K 字符 |
| STT `Scribe v2` / `Scribe v2 Medical` | $0.22 / 小时（+ entity detection $0.070/小时、keyterm prompting $0.050/小时 的口径单独列在计算器里,与 speech-to-text.md 里"基础费 +30%/+20%"的口径不是同一份说法,⚠ 文档自相矛盾,两处都未验证哪个是最终账单逻辑) |
| STT `Scribe v2 Realtime` | $0.39 / 小时 |
| ElevenAgents / Speech Engine | $0.08 / 分钟标准价,Burst 期间 $0.16 / 分钟（与 `conversational-ai.md` 的 burst pricing 说明一致） |
| Music | $0.15 / 分钟 |
| Voice Isolator / Voice Changer / Sound Effects | $0.12 / 分钟 |
| Dubbing v1（带水印） | $0.33 / 分钟；去水印 $0.50 / 分钟 |
| Dubbing v2 | $2.20 / 分钟 |

**关于 STT 附加费口径矛盾**：`speech-to-text.md` 引用的是 API Reference 参数说明里的百分比加价（entity_detection +30% 等,这是相对"基础转录费"的比例）；这里引用的是定价计算器页面单独列出的"每小时固定加价"（$0.070/hr entity detection、$0.050/hr keyterm prompting）。两种表述方式（比例 vs 固定单价）理论上应该能换算一致（$0.070/$0.22 ≈ 32%,和 +30% 大致对得上；$0.050/$0.22 ≈ 23%,和 +20% 有出入),但没有做实际请求去核对账单明细,标 `⚠ 文档自相矛盾`,验证清单已列入。

ElevenAgents 定价计算器页面另外展示了"按分钟计的 LLM 模型成本"（例如 Gemini 2.5 Flash 约 $0.0012/分钟,取决于对话平均 token 消耗),这是叠加在通话分钟费**之上**的独立成本,不要漏算。

## 并发限制

见 `references/models.md` 的"并发与优先级"一节,按套餐分档,TTS/STT/实时 STT 三套独立的并发计数器。**⚠ 关键区分（原文强调）**：并发上限不等于最大同时通话数——TTS 生成耗时远小于音频播放耗时,官方给的经验法则是并发 5 大致能撑约 100 路语音广播,做容量规划不要直接拿并发上限当并发用户数上限用。

## 订阅套餐与 Credit Rollover

- 公开套餐：Free / Starter / Creator / Pro / Scale / Business,另有面向大客户的定制 Enterprise。
- **未用完的月度 credits 最多可以滚存两个月**（"up to two months' worth of unused credits can roll over"）,降级或取消订阅**不触发**滚存,直接清零。
- Pay As You Go（预付费）是新自助套餐的默认加量方式,替代了老的"用量超额计费"（Usage Based Billing,该功能已标为 legacy,新自助套餐不再提供,只有 Enterprise 和部分 legacy 套餐还保留）。
- 语音克隆相关：**Free 套餐不能用 Voice Cloning（IVC/PVC),但可以用 Voice Design**（3 个自定义声音槽位）;声音克隆功能从 Starter 套餐开始解锁,PVC 需要 Creator 及以上（与 `references/voices.md` 一致）。
- 生成内容的商用授权:**付费套餐生成的内容有商用权;Free 套餐只能非商用使用且要署名**——用 Free key 做的任何 POC 产出,交付给客户前要提醒这条。
