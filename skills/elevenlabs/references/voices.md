# 克隆或设计一个声音

> 来源：`eleven-api/concepts/voice-cloning.md`、`eleven-api/guides/how-to/voices/{instant-voice-cloning,professional-voice-cloning,voice-design}.md`、`api-reference/voices/{ivc/create,pvc/create,pvc/verification/request}.md`、`api-reference/text-to-voice/{design,create,remix}.md`、`help-center/product/voices/voice-cloning/*.md`（抓取于 2026-09-21）。**⚠ 全文未用真实 API Key 验证。**

## 目录

- [三条路径怎么选](#三条路径怎么选)
- [⚠ 合规红线：同意与验证](#-合规红线同意与验证)
- [Instant Voice Cloning（IVC）](#instant-voice-cloningivc)
- [Professional Voice Cloning（PVC）](#professional-voice-cloningpvc)
- [Voice Design / Remix（从文字描述生成新声音）](#voice-design--remix从文字描述生成新声音)

## 三条路径怎么选

| 路径 | 输入 | 适合场景 | 套餐门槛 |
| :--- | :--- | :--- | :--- |
| Instant Voice Cloning (IVC) | 一段真人录音（<2分钟即可） | 快速原型、探索、对一致性要求不高的场景 | Starter 及以上（Free 不支持声音克隆，只支持 Voice Design） |
| Professional Voice Cloning (PVC) | 约 30 分钟高质量真人录音 | 生产环境、品牌代言声音、对一致性和情感表现要求高的场景 | **Creator 及以上** |
| Voice Design / Remix | 一段文字描述（Prompt），不需要真人录音 | 需要一个"不存在的人"的声音，或者基于现有声音调整特质（性别/口音/风格） | Free 套餐即可（Free 提供 3 个自定义声音槽位） |

**IVC 与 PVC 不是"快慢两个版本"，是两条根本不同的技术路径**：IVC 是推理时把你的录音当"条件信号"实时参考（few-shot，不更新模型权重）；PVC 是真正在你的录音上微调模型权重。这意味着：
- IVC 的质量上限被参考音频本身框死（背景噪音、压缩失真都会原样体现在输出里）；PVC 因为是微调,录音质量会影响模型权重本身,对录音质量要求更高。
- IVC 换一种说话风格（比如从平静叙述换成强烈情绪）时一致性会下降；PVC 在跨风格场景下更稳定。
- **⚠ PVC 训练耗时文档口径不一致**：`eleven-api/concepts/voice-cloning.md` 原文说 "PVC creation takes minutes rather than seconds"（几分钟量级）；但 Help Center FAQ 原文说 "usually fine-tuning will take 3-6 hours"（3~6 小时量级）。两处相差两个数量级，标 `⚠ 文档自相矛盾`，验证时要实测一次完整 PVC 训练耗时，按更保守的"数小时"去做用户预期管理，不要相信"几分钟"就能上线。

## ⚠ 合规红线：同意与验证

这是 ElevenLabs 明确作为产品/法律层面强制的规则，**不是技术限制，是平台策略**，代码实现再"正确"也绕不开：

1. **PVC 只能克隆账号本人的声音，即使拿到对方明确同意也不行。** Help Center 原文："No. You can only create a Professional Voice Clone of your own voice. Even with their consent, you cannot clone someone else's voice." 正确的"帮别人做声音"的方式是：对方自己注册账号、自己完成验证、创建自己的 PVC，然后用分享链接私下分享给你使用——不是你代替对方上传录音。
2. **IVC 和 PVC 都有身份验证步骤，使用 voice-captcha 技术**（要求录音提供者现场跟读一段随机文本，用于确认"提供录音的人此刻在场且主动配合"）。官方原文明确承认这个机制的局限："验证不能保证提交的录音真的属于申请人，只能确认申请人当时在场并主动参与"——最终的合法使用责任落在创建者身上（ToS + AI Safety 政策）。**写克隆功能时应该在产品层面提示用户"你是否有权克隆这个声音"，不能假设走完 API 流程就等于合规。**
3. **IVC 的 `POST /v1/voices/add` 响应里带 `requires_verification` 布尔字段**，说明部分 IVC 创建也会触发验证流程（比如声音与知名人物相似度较高时）。具体触发条件文档未说明，标 `⚠ 文档未说明`，验证清单已列入。
4. **PVC 还有一个独立的人工验证端点** `POST /v1/voices/pvc/{voice_id}/verification`（提交身份证明文件 `files` + 可选 `extra_text`），用于走不通自动验证时的人工审核通道。

## Instant Voice Cloning（IVC）

**Endpoint**: `POST https://api.elevenlabs.io/v1/voices/add`，`multipart/form-data`

| 参数 | 必填 | 说明 |
| :--- | :--- | :--- |
| `name` | 是 | 声音名称 |
| `files` | 是 | 一或多个音频文件路径（录音样本） |
| `remove_background_noise` | 否 | 用音频隔离模型去除背景噪音；**⚠ 文档原文提醒：如果样本本身没有背景噪音，打开这个开关反而会让质量变差**，不要无脑全开 |
| `description` | 否 | 声音描述 |
| `labels` | 否 | key 可以是 language/accent/gender/age |

**响应**：`{"voice_id": "...", "requires_verification": bool}`。

```python
from elevenlabs import ElevenLabs

client = ElevenLabs()
voice = client.voices.ivc.create(
    name="John Smith",
    files=["sample1.mp3", "sample2.mp3"],
)
```

## Professional Voice Cloning（PVC）

创建 PVC 是**三步流程**，不是一次调用：

1. **`POST /v1/voices/pvc`**（JSON）创建元数据壳（`name`、`language` 必填，`description`/`labels` 可选），此时还没有样本，只拿到 `voice_id`。
2. **`POST /v1/voices/pvc/{voice_id}/samples`**（multipart）上传训练音频样本，**官方建议约 30 分钟高质量录音**，样本越多效果越好；支持先做说话人分离（多人录音场景下先分离出目标说话人的音轨再喂进去，分离结果有轻微伪影，能用干净单人录音就不要依赖自动分离）。
3. **等待微调完成**（耗时口径矛盾，见上文），完成后收到邮件通知。如果自动验证没通过，走 `POST /v1/voices/pvc/{voice_id}/verification` 提交身份证明文件做人工审核。

```python
voice = client.voices.pvc.create(name="My Professional Voice Clone", language="en")
samples = client.voices.pvc.samples.create(voice_id=voice.voice_id, files=[...])
```

**套餐门槛**：创建 PVC 需要 **Creator 及以上套餐**（Help Center 与 API quickstart 两处口径一致，可信度较高，但仍未实测账号权限不够时报什么错）。

## Voice Design / Remix（从文字描述生成新声音）

不需要真人录音，用文字 Prompt 直接"设计"一个新声音，两步流程：

1. **`POST /v1/text-to-voice/design`**（预览）：传 `voice_description`（必填）+ 可选 `text`（100~1000 字符,用来试听这个声音）、`model_id`（默认 `eleven_multilingual_ttv_v2`，也可选 `eleven_ttv_v3`）、`loudness`（-1~1）、`guidance_scale`（默认 5，越高越贴合 prompt 但可能显得机械）、`auto_generate_text`（自动生成试听文本）。**⚠ `reference_audio_base64` 和 `prompt_strength` 两个参数只在 `eleven_ttv_v3` 模型下生效**（可以传一段参考音频，让生成的声音在此基础上按 prompt 调整,类似"声音混音"）。响应返回若干个 `generated_voice_id` 预览,每个带 base64 编码的试听音频。
2. **`POST /v1/text-to-voice`**（创建）：拿上一步的 `generated_voice_id` + `voice_name` + `voice_description` 正式创建一个可用的 `voice_id`。

**Remix**（`POST /v1/text-to-voice/{voice_id}/remix`，未展开详细字段，⚠ 待验证补充）用于在已有声音基础上调整性别/口音/风格/语速等特质再生成新的候选声音，同样走"预览 → create" 两步。

**套餐门槛**：Voice Design 在 Free 套餐即可使用（占用 Free 套餐提供的 3 个自定义声音槽位之一），门槛明显低于声音克隆——不需要真人录音、不涉及同意验证问题，做"需要一个独特声音但没有真人录音来源"的场景应该优先考虑 Voice Design 而不是想办法找录音去克隆。
