# ElevenLabs skill 验证计划

写于 2026-09-21，此时没有真实 API Key。本文件是 `elevenlabs` skill 里每一处 `⚠ 文档原文，未实测` / `⚠ 文档未说明` / `⚠ 文档自相矛盾` 标注的验证清单，按"花费小、出结果快"优先排序（参照 create-doc-skill 方法论 verify.md）。拿到 Key 后按顺序打真实请求，每完成一条就回到对应 `references/*.md` 文件按固定格式写回："**已用真实 API 验证（日期）**：...，附报错原文/响应片段"。全部测完后在 `verification-log.md` 记一份日期/endpoint/结果/花费的流水账，供第 4 步对照实验引用。

## 卫生提醒

- Key 只作为环境变量（`ELEVENLABS_API_KEY`）传给测试脚本，不写进任何文件。
- 测试全部跑完后，全仓库 `grep -rn "<key 前 8 位>"` 一遍确认没有泄漏。
- 测试中创建的声音（IVC/PVC/Voice Design）、发音词典、webhook 配置，用完立即在 Dashboard 或 API 里删除，不留垃圾。
- 优先用免费/最低档账号测试"套餐门槛"类问题（比如 PVC 是否真的卡 Creator 以下），如果只有高档账号，测试结果要注明"未覆盖低套餐场景"。

## 第一优先级：零成本或近零成本（只读 / 校验类请求）

1. **鉴权 header 精确格式**：不带 `xi-api-key` 直接调 `GET /v1/models`，确认报错格式（是 401 还是别的）；再故意传一个格式错误的 key，对比两种报错是否有区分度。SKILL.md 目前只是转录文档没有实测过报错文案。
2. **STT `model_id` 是否真必填**：调 `POST /v1/speech-to-text` 故意不传 `model_id`（其余参数给一个几秒钟的短音频或 `source_url`），确认是否 422，报错文案是什么。这是 SKILL.md 通用规则第 3 条、evals 场景 4 的核心依据，且理论上验证型错误不产生音频时长费用，成本接近零。
3. **TTS `model_id` 省略时的静默默认**：省略 `model_id` 调一次 `POST /v1/text-to-speech/{voice_id}`（用最短的文本，如 "Hi"），对比响应 header（`character-cost`、有无模型相关 header）能否间接确认落到了 `eleven_multilingual_v2`；如果响应本身不暴露实际使用的模型，退而求其次：分别用省略 `model_id` 和显式传 `eleven_multilingual_v2` 各生成一次同样文本，比较两次 `character-cost` 是否一致（如果计费按模型有差异，能间接印证默认值)。成本：两次几字符的 TTS 请求，几乎免费。
4. **`enable_logging=false` 在非 Enterprise 账号上的行为**：用普通账号传 `enable_logging: false` 调一次最短 TTS/STT 请求，看是报错、还是被静默忽略当作 `true` 处理、还是真的生效。SKILL.md 通用规则第 7 条目前完全没验证。
5. **`output_format` 套餐门槛报错文案**：用低档账号请求 `output_format=mp3_44100_192`（需 Creator+）或 `pcm_44100`（需 Pro+），确认是 422 还是别的错误码，报错信息是否直接提示"需要升级套餐"。
6. **公开 Agent 免 Key 访问**：用一个未开启 authentication 的公开测试 Agent，不带 `xi-api-key` 直接建立 Conversation/WebSocket，确认 `conversational-ai.md` 里"public agent 不需要 key"这条是否成立。
7. **IVC 响应里的 `requires_verification` 触发条件**：用一段完全普通、非名人声音的短样本（几秒即可）调 `POST /v1/voices/add`，看 `requires_verification` 是否为 `false`；如果账号允许，再试一次用合成语音（比如用 TTS 生成的音频回传去克隆）看是否会被判定需要验证。用完立即删除测试声音。

## 第二优先级：小额可控成本（TTS 几十字符 / STT 几十秒音频）

8. **WebSocket 消息形状**：连接 TTS WebSocket 端点，发送一句极短文本（"Hello"）+ `auto_mode=true`，确认真实收到的消息是否严格符合 `AudioOutput`/`FinalOutput` 两种 schema，`isFinal` 时 `audio` 是否确实为 null。成本：一次几字符的 TTS 生成。
9. **发音词典模型限制**：创建一个只含一个词的发音词典（如 "tomato"），分别用 `eleven_flash_v2`、`eleven_v3`、`eleven_multilingual_v2` 三个模型各生成一次含这个词的短句，听感对比音标是否生效（`eleven_multilingual_v2` 应该"静默跳过"）。这是 `text-to-speech.md` 里明确写了"其他模型会静默跳过"的结论，值得用最短文本验证一次。成本：三次几字符 TTS。
10. **请求拼接 `previous_request_ids`**：用 SDK `with_raw_response` 拿到第一次生成的 `request-id`，第二次请求带上这个 id，确认响应是否 200 且听感上韵律衔接更自然于不传的对照组。成本：两次短文本 TTS。
11. **STT 附加参数的真实计费**：转录一段固定的、几十秒的测试音频四次——(a) 不加任何附加参数，(b) 只加 `keyterms`，(c) 只加 `entity_detection`，(d) 都加——用 `GET` usage/character 相关接口（`api-reference/usage/get-character-stats`）在每次调用前后读一次余额差值，核对是否真的是 +20%/+30%（API 参数说明口径）还是定价页写的"每小时固定加价"口径（两者数字换算基本一致但不完全一致，`pricing-and-limits.md` 已标注矛盾）。这是本次抓取里少数"文档自己给了两套互相矛盾的具体数字"的地方，值得优先测。
12. **Voice Design 预览到创建两步流程**：用一句简短描述（如 "a calm female narrator voice"）调 `POST /v1/text-to-voice/design`，拿到 `generated_voice_id` 后调 `POST /v1/text-to-voice` 正式创建，确认两步流程、字段名、响应结构与 `voices.md` 描述一致。用完删除测试声音。

## 第三优先级：耗时长或成本较高，视额度酌情安排

13. **PVC 训练耗时口径矛盾（"几分钟" vs "3~6 小时"）**：需要真的跑一次完整 PVC（约 30 分钟高质量录音，Creator 及以上套餐），记录从上传样本到收到"训练完成"邮件通知的真实耗时。这个测试跨度长（可能数小时），且要求账号在 Creator 及以上套餐，安排在其他测试都完成、且确认账号套餐满足条件之后再做；如果没有 Creator+ 账号，明确标注"未验证，保留文档矛盾"。
14. **PVC 人工验证通道**：`POST /v1/voices/pvc/{voice_id}/verification` 需要真实提交身份证明文件，涉及个人信息，除非有专门的测试账号愿意配合，否则跳过，只保留文档转录。
15. **多声道时长上限矛盾（1 小时 vs 10 小时）**：需要准备一段长音频（接近 1 小时）做多声道转录测试，成本较高（按声道数 × 时长计费），优先级放最后，如果预算不允许可以只用极短的多声道样本（几分钟）验证"能不能跑通"，不验证具体时长上限数字。
16. **MCP `can_use_mcp_servers` 权限范围（`convai_write` key 能否开关整个 workspace）**：需要一个仅有 `convai_write` 权限、非 admin 的 API Key 才能验证，如果测试账号只有一个 admin 级别的 key，此项标注"未覆盖，保留文档转录"。

## 不建议验证 / 无法验证的部分

- 区域路由的具体后端位置（USA/荷兰/新加坡）：`x-region` 响应头能读到,但"是否覆盖所有列出的区域"这种全集验证意义不大,读一次自己请求命中的 `x-region` 即可,不用专门测。
- 定价页具体数字（$0.08/分钟等）：这是营销页面而非 API,数字随时会变,验证的意义是"页面结构没变",不是"数字精确"，不需要反复验证，每次大改版重新读一次即可。
