# 模型目录与选型

来源：`docs.bigmodel.cn/cn/guide/start/model-overview`、`docs.bigmodel.cn/cn/guide/start/concept-param`

调用任何接口前先确认 `model` 字段用的是这里列出的模型代码（区分大小写不敏感,但请照抄小写形式,比如 `glm-5.3`）。写代码时不要凭空编造模型名。

## 选型速查:我该用哪个模型?

| 需求 | 推荐模型 | 说明 |
| :--- | :--- | :--- |
| 通用旗舰对话/复杂推理/长程 Agent 任务 | `glm-5.3` | 编程与智能体能力对标 Claude Fable 5;1M 上下文,128K 最大输出 |
| 需要看图/看视频 + 生成代码的多模态旗舰 | `glm-5.3-flash` | 原生多模态,能理解图片视频、生成可交互代码 |
| 复杂长程任务、Coding 从生成走向工程交付 | `glm-5.2` | 1M 上下文,128K 最大输出 |
| 免费/低成本文本任务 | `glm-4.7-flash`、`glm-4.5-flash`、`glm-4-flash-250414` | 完全免费,但能力弱于旗舰模型 |
| 高并发、低延迟场景 | `glm-4.5-airx`、`glm-4-flashx-250414` | 极速版本 |
| 视觉理解 + Coding 基座 | `glm-5v-turbo` | 兼顾视觉理解、推理与代码生成 |
| 通用视觉问答/图像理解 | `glm-4.6v`(原生工具调用) / `glm-4.6v-flash`(免费) |  |
| 手机 App 自动化操作 | `autoglm-phone` | 手机智能助理框架 |
| 文生图 | `glm-image`(旗舰,文字渲染强) / `cogview-4`(通用) / `cogview-3-flash`(免费) |  |
| 文档/图片 OCR、版式解析 | `glm-ocr` | 轻量图文解析,单图 ≤10MB,PDF ≤50MB(最多100页) |
| 文生视频/图生视频 | `cogvideox-3`(旗舰,支持首尾帧) / `vidu-q1`、`vidu-2`(Vidu系列) / `cogvideox-flash`(免费) |  |
| 语音识别 ASR | `glm-asr-2512` | 高精度,支持自定义词汇,多语言/方言 |
| 语音合成 TTS | `glm-tts` | 支持流式/非流式,情感表达 |
| 音色克隆 | `glm-tts-clone` | 3 秒音频即可克隆音色 |
| 实时语音/视频通话 | `glm-realtime`、`glm-4-voice` | WebSocket 协议,见 `references/realtime.md` |
| 文本向量化/语义检索 | `embedding-3`(推荐,V3) / `embedding-2`(V2) | 8K 上下文 |
| 文本重排序 | `rerank` | 配合 embedding 做 RAG 精排 |
| 角色扮演/情感陪伴 | `charglm-4`(拟人对话) / `emohaa`(心理支持) |  |
| 代码补全(非对话式) | `codegeex-4` | 128K 上下文 |

## GLM Coding Plan（编程套餐）可用模型

套餐 Key 走 `…/api/coding/paas/v4` 或 `…/api/anthropic` 时，所有档位都支持 `glm-5.3`、`glm-5.3-flash`；传旧模型代码 `glm-5.2` / `glm-5.1` / `glm-5-turbo` / `glm-4.7` 会被自动路由到新版本。下表其余模型（视觉、生图、生视频、语音、embedding、rerank 等）**不在套餐内**，要用标准 API Key 走 `…/api/paas/v4`。详见 `references/coding-plan.md`。

## 文本模型全表

| 模型代码 | 特点 | 上下文 | 最大输出 |
| :--- | :--- | :--- | :--- |
| `glm-5.3` | 编程与智能体能力对标 Claude Fable 5,长程任务表现更佳 | 1M | 128K |
| `glm-5.2` | 支撑复杂长程任务,Coding 能力大幅提升 | 1M | 128K |
| `glm-5.1` | Coding 对齐 Claude Opus 4.6,可自主工作长达 8 小时 | 200K | 128K |
| `glm-5` | 编程能力对齐 Claude Opus 4.5,擅长长程规划执行 | 200K | 128K |
| `glm-5-turbo` | 长任务执行连续性好 | 200K | 128K |
| `glm-4.7` | 通用对话/推理/智能体能力升级 | 200K | 128K |
| `glm-4.7-flashx` | 轻量高速,小尺寸强能力 | 200K | 128K |
| `glm-4.6` | 擅长高级编码、复杂推理与工具调用 | 200K | 128K |
| `glm-4.5-air` | 轻量模型,推理/编码/智能体任务稳定 | 128K | 96K |
| `glm-4.5-airx` | 极速版本,低延迟高响应 | 128K | 96K |
| `glm-4-long` | 理解超长文本和记忆型任务 | 1M | 4K |
| `glm-4-flashx-250414` | Flash 增强高速版,适合高并发 | 128K | 16K |
| `glm-4.7-flash`(免费) | 延续 GLM-4.7 基座通用能力 | 200K | 128K |
| `glm-4.5-flash`(免费) | 最长 128K 上下文 | 128K | 96K |
| `glm-4-flash-250414`(免费) | 免费文本模型 | 128K | 16K |

## 视觉理解模型

| 模型代码 | 特点 | 上下文 | 最大输出 |
| :--- | :--- | :--- | :--- |
| `glm-5v-turbo` | 多模态 Coding 基座,视觉理解+推理+代码生成 | 200K | 128K |
| `glm-4.6v` | 原生支持工具调用,前端代码复刻效果稳定 | 128K | 32K |
| `autoglm-phone` | 手机智能助理框架,自然语言操作 App | 20K | 2048 |
| `glm-4.1v-thinking-flashx` | 复杂场景理解与多步骤分析,适合高并发视觉推理 | 64K | 16K |
| `glm-4.6v-flash`(免费) | 支持视觉推理 | 128K | 32K |
| `glm-4.1v-thinking-flash`(免费) | 支持视觉推理 | 64K | 16K |
| `glm-4v-flash`(免费) | 支持图像理解 | 16K | 1K |

## 图像/视频/音频/向量模型

| 类别 | 模型代码 | 特点 |
| :--- | :--- | :--- |
| 图像生成 | `glm-image` | 旗舰,复杂指令遵循强,文字渲染突出,支持多分辨率 |
| 图像生成 | `cogview-4` | 通用图像生成,质量高,画面细节完整 |
| 图像生成 | `cogview-3-flash`(免费) | 轻量图像创作 |
| 视频生成 | `cogvideox-3` | 旗舰,指令遵循与物理模拟更强,支持首尾帧生成 |
| 视频生成 | `vidu-q1` | 高质量视频生成,支持图像/文本/首尾帧 |
| 视频生成 | `vidu-2` | 高速低价,支持图像/参考/首尾帧 |
| 视频生成 | `cogvideox-flash`(免费) | 支持图像/文本 |
| OCR/文档解析 | `glm-ocr` | 单图 ≤10MB,PDF ≤50MB,最多100页 |
| 语音识别 ASR | `glm-asr-2512` | 高精度,低字符错误率,支持自定义词汇 |
| 语音合成 TTS | `glm-tts` | 支持流式/非流式,情感表达 |
| 音色克隆 | `glm-tts-clone` | 3 秒音频即可生成相似音色 |
| 实时音视频 | `glm-realtime` | 视频/音频/文本多模态实时交互 |
| 实时语音对话 | `glm-4-voice` | 文本/音频 |
| 文本向量 | `embedding-3` | V3,语义检索/聚类/主题建模/分类 |
| 文本向量 | `embedding-2` | V2 |
| 重排序 | `rerank` | 4K 上下文 |
| 角色扮演 | `charglm-4` | 拟人对话,8K 上下文,4K 最大输出 |
| 情感支持 | `emohaa` | 心理情感支持,8K 上下文,4K 最大输出 |
| 代码补全 | `codegeex-4` | 128K 上下文,32K 最大输出 |

## max_tokens 的默认值与上限(按模型)

`max_tokens` 只限制**生成内容**长度,不包括输入。不同模型的默认值/上限差异很大,建议显式传值而不是依赖默认值:

| 模型 | 默认 max_tokens | 最大 max_tokens |
| :--- | :---: | :---: |
| glm-5.3 / glm-5.3-flash / glm-5.2 / glm-5.1 / glm-5v-turbo / glm-5 / glm-5-turbo / glm-4.7 / glm-4.6 | 65536 | 131072 |
| glm-4.6v / glm-4.6v-flash / glm-4.6v-flashx | 16384 | 32768 |
| glm-4.5 / glm-4.5-air / glm-4.5-x / glm-4.5-flash | 65536 | 98304 |
| glm-4.5v | 16384 | 16384 |
| glm-4.1v-thinking-flashx | 16384 | 16384 |
| glm-4.1v-thinking-flash | 32768 | 32768 |
| glm-4-air-250414 | 16384 | 16384 |
| glm-4-flash-250414 | 32768 | 32768 |
| glm-4-plus / glm-4-air / glm-4-airx / glm-4-flash / glm-4-flashx(旧系列) | 动态计算 | 4095 |
| glm-4v-plus-0111 | 1024 | 8192 |
| glm-4v-flash | 1024 | 1024 |

## 深度思考(thinking)默认行为(按模型)

| 模型 | thinking 默认行为 |
| :--- | :--- |
| glm-5.3 / glm-5.3-flash | 标准端点**强制开启**,只能用 `reasoning_effort` 控制思考强度,传 `disabled` 报 `1210`；Coding 端点（`…/api/coding/paas/v4`）实测可以关闭,见 `references/coding-plan.md` |
| glm-4.7 / glm-4.5v | 强制思考 |
| glm-5.2 / glm-5.1 / glm-5 / glm-5-turbo / glm-5v-turbo / glm-4.6 / glm-4.6v / glm-4.5 | 模型自动判断是否思考(可通过 `thinking.type` 显式开关) |
| glm-4.5 以下版本 | 不支持 `thinking` 参数 |

`reasoning_effort` 仅 `glm-5.2` 及以上支持;`glm-5.3`/`glm-5.3-flash` 仅接受 `low`/`high`/`max`,`glm-5.2` 额外接受 `xhigh`/`medium`/`minimal`/`none`(会被归一化映射)。详见 `references/chat.md`。

## 价格与最新上架情况

模型仍在持续迭代,价格请始终以控制台为准,不要在代码或文档里硬编码价格:`https://bigmodel.cn/pricing`。模型概览页面(可能比本文件更新更及时):`https://docs.bigmodel.cn/cn/guide/start/model-overview`。
