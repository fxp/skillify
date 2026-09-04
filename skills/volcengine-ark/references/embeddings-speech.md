# 向量化（Embedding）、语音（TTS / ASR）、同声传译

本文件覆盖火山方舟三类非文本生成能力的接入方式：多模态向量化 `doubao-embedding-vision`、Agent Plan 语音模型 `doubao-seed-tts-2.0` / `doubao-seed-asr-2.0`、同声传译（`service=clasi`）WebSocket API。每个 endpoint 标明在标准 `/api/v3`、Coding Plan `/api/coding/v3`、Agent Plan `/api/plan/v3` 三套入口中的可用性。鉴权与 Base URL 总表见 `auth.md`（同级 reference）。标 **已用真实 API 验证（2026-09-04，Agent Plan Medium）** 的结论均在 Agent Plan `/api/plan/v3` 入口实测；标准 `/api/v3` 与 Coding Plan 入口预期相同但未测。

## 目录

1. [入口与可用性总览](#1-入口与可用性总览)
2. [向量化：我想把文本 / 图片 / 视频变成向量](#2-向量化)
   - 2.1 模型版本选型
   - 2.2 多模态向量化 API（`POST /api/v3/embeddings/multimodal`）
   - 2.3 OpenAI 风格 `POST /embeddings` 是否可用（Plan 入口已实测：可用，仅字符串输入）
   - 2.4 `instructions` 怎么写（直接决定效果）
   - 2.5 维度、相似度、归一化
   - 2.6 输入限制（图片 / 视频 / Base64）
   - 2.7 最小 Python 示例：以文搜图
   - 2.8 批量处理
   - 2.9 Coding Plan / Agent Plan 里配置向量化（OpenClaw / OpenViking）
3. [语音：我想做 TTS / ASR（Agent Plan）](#3-语音agent-plan)
   - 3.1 核心配置与鉴权头
   - 3.2 流式语音合成 TTS（双流 / 单流 / HTTP）
   - 3.3 流式语音识别 ASR（双流 / 单流）
   - 3.4 计费（AFP 抵扣）
4. [同声传译：我想实时把语音转录并翻译](#4-同声传译)
   - 4.1 Endpoint、鉴权、模型
   - 4.2 客户端事件
   - 4.3 服务端事件
   - 4.4 限制与超时
   - 4.5 最小 Python 示例
5. [来源页面](#5-来源页面)

---

## 1. 入口与可用性总览

| 能力 | 标准 API（`ark.cn-beijing.volces.com/api/v3`，`ARK_API_KEY`） | Coding Plan（`/api/coding/v3`，`ARK_API_KEY`） | Agent Plan（`/api/plan/v3`，`ARK_AGENT_PLAN_API_KEY`） |
|---|---|---|---|
| 多模态向量化 | `POST /api/v3/embeddings/multimodal`，model 填 Model ID `doubao-embedding-vision-251215` / `-250615` 或 `ep-xxx` | 文档只给出在 OpenClaw / OpenViking 配置文件里填 `baseUrl=/api/coding/v3` + `model=doubao-embedding-vision`；具体 HTTP 路径 ⚠ 文档未说明（Agent Plan 入口实测 `/embeddings` 与 `/embeddings/multimodal` 两条路径都存在，Coding Plan 预期相同但未测，见 2.3） | **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`POST /api/plan/v3/embeddings`（OpenAI 形态，`input` 字符串）与 `POST /api/plan/v3/embeddings/multimodal`（方舟原生形态）均 200，model 填 `doubao-embedding-vision`（响应 `model: doubao-embedding-vision-251215`），详见 2.3；官方口径「向量化模型不可用于 API 调用」仍在（在非 AI 工具内直接调可能被判滥用） |
| TTS `doubao-seed-tts-2.0` | ⚠ 文档未说明（语音模型只出现在 Agent Plan 文档） | ⚠ 文档未说明 | 走 **另一个域名** `openspeech.bytedance.com/api/v3/plan/tts/...`，头 `X-Api-Key` + `X-Api-Resource-Id: seed-tts-2.0` |
| ASR `doubao-seed-asr-2.0` | ⚠ 文档未说明 | ⚠ 文档未说明 | `wss://openspeech.bytedance.com/api/v3/plan/sauc/...`，头 `X-Api-Key` + `X-Api-Resource-Id: volc.seedasr.sauc.duration` |
| 同声传译 | `wss://ark-beta.cn-beijing.volces.com/api/v3/realtime?service=clasi&model=<Model>`，邀测能力需提工单 | ⚠ 文档未说明 | ⚠ 文档未说明 |

要点：
- 语音（TTS / ASR）不走 `ark.cn-beijing.volces.com`，而是 `openspeech.bytedance.com`，鉴权头也不是 `Authorization: Bearer`，是 `X-Api-Key`。
- 同声传译走 `ark-beta` 子域，不是 `ark`。
- 向量化 model 字段：标准入口用带日期的 Model ID（`doubao-embedding-vision-251215`）或接入点 `ep-`；两套 Plan 入口用小写 Model Name `doubao-embedding-vision`（文档说它对应 `doubao-embedding-vision-251215`；Agent Plan 入口已实测，`/embeddings/multimodal` 响应 `model` 即 `doubao-embedding-vision-251215`，与文档一致）。

---

## 2. 向量化

### 2.1 模型版本选型

文本向量化旧模型已逐步下线（「兼容 OpenAI SDK」页原文：「文本向量化模型已经逐步下线，建议您使用多模态向量化模型」），新项目一律用 `doubao-embedding-vision`。

| 模型版本 | 输入 | 稀疏向量 | 多向量 | 视频自定义抽帧 | `instructions` | 上下文 / 最高维度 / 限流（模型列表页） |
|---|---|---|---|---|---|---|
| `doubao-embedding-vision-250615` | 不限数量的文本、图片、视频混合 | 支持（仅纯文本输入） | 不支持 | 不支持 | 不支持 | 128k / 2048（支持 1024 降维） / RPM 15000、TPM 1200000 |
| `doubao-embedding-vision-251215` 及后续 | 同上 | 支持（仅纯文本输入） | 支持，`compression=blosc2/zstd` | 支持 | 支持 | 同上 |

- 三种向量输出：稠密向量（所有版本默认）、稀疏向量（250615 起，仅文本）、多向量 / token 级（251215 起）。
- Plan 文档反复强调：「建议固定使用同一版本的向量化模型，请勿混用不同版本」——同一向量库的 Query 与 Corpus 必须用同一版本产出。
- 批量示例代码里出现的 `doubao-embedding-vision-241215` 不在模型列表页里，⚠ 文档自相矛盾（可能是旧版本），不要照抄。

### 2.2 多模态向量化 API

**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal`（标准入口；两套 Plan 入口的路径见 2.3）
**用途**: 把一组文本 / 图片 / 视频 `input[]` 编码成向量。注意：整个 `input[]` 列表被编码为 **一条** 结果（响应 `data` 是对象不是数组，Plan 入口已实测证实，见下方注意事项），要给 N 条素材各生成一个向量就发 N 次请求。
**鉴权**: `Authorization: Bearer $ARK_API_KEY`

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | — | Model ID（`doubao-embedding-vision-251215`）或 Endpoint ID（`ep-xxx`，可得限流 / 监控等高级能力） |
| `input` | object[] | 是 | — | 待向量化内容列表，元素按 `type` 分三种 |
| `input[].type` | string | 是 | — | `text` / `image_url` / `video_url` |
| `input[].text` | string | `type=text` 时必填 | — | UTF-8 文本，长度不超过模型最大输入 token |
| `input[].image_url.url` | string | `type=image_url` 时必填 | — | 图片 URL 或 `data:image/{格式};base64,{编码}` |
| `input[].video_url.url` | string | `type=video_url` 时必填 | — | 视频 URL 或 `data:video/{格式};base64,{编码}`；.mp4 / .avi / .mov，格式小写，≤50MB，不理解音轨 |
| `input[].video_url.fps` | number | 否 | 模型默认抽帧策略 | `[0.2, 5]` 帧/秒；仅 251215+ |
| `input[].video_url.max_video_tokens` | integer | 否 | 同上 | `[10240, 204800]`，整段视频送入模型的 token 上限 |
| `input[].video_url.min_frame_tokens` | integer | 否 | 同上 | `[16, 128]` 单帧 token 下限 |
| `input[].video_url.max_frame_tokens` | integer | 否 | 同上 | `[128, 640]` 单帧 token 上限，且 `>= min_frame_tokens` |
| `input[].video_url.min_frames` | integer | 否 | 同上 | `[5, 16]` 最少抽帧数（极短视频兜底） |
| `dimensions` | integer | 否 | `2048` | 稠密向量维度，只能 `1024` 或 `2048`；对 `data.embedding` 生效，多向量子向量列数随之变化；稀疏向量固定维度不受影响。250615 起支持 |
| `encoding_format` | string | 否 | `float` | 稠密向量返回格式：`float` / `base64` / `null` |
| `instructions` | string | 否 | 按输入模态生成默认值 | 推理提示词；仅 251215+。文档加粗：**请勿直接使用系统默认值**，见 2.4 |
| `multi_embedding.type` | string | 否 | `disabled` | `enabled` 时额外返回 `data.multi_embedding`（token 级二维向量）；仅 251215+。**不允许传空对象 `{}`**（文档原文，未实测：会报错） |
| `multi_embedding.compression` | string | 否 | 不压缩 | `blosc2` / `zstd`；仅 `type=enabled` 时生效，与 `encoding_format` 正交 |
| `sparse_embedding.type` | string | 否 | `disabled` | `enabled` 时额外返回 `data.sparse_embedding`；**仅纯文本输入支持**；250615 起 |

**示例请求**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-embedding-vision-251215",
    "encoding_format": "float",
    "dimensions": 1024,
    "instructions": "Target_modality: image.\nInstruction:Compress the text into one word.\nQuery:",
    "input": [
      {"type": "text", "text": "蓝色海景"}
    ]
  }'
```

```python
import os, requests

resp = requests.post(
    "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal",
    headers={"Authorization": f"Bearer {os.environ['ARK_API_KEY']}",
             "Content-Type": "application/json"},
    json={
        "model": "doubao-embedding-vision-251215",
        "encoding_format": "float",
        "dimensions": 1024,
        "input": [
            {"type": "video_url", "video_url": {
                "url": "https://ark-project.tos-cn-beijing.volces.com/doc_video/ark_vlm_video_input.mp4",
                "fps": 1, "max_video_tokens": 120000,
                "min_frame_tokens": 32, "max_frame_tokens": 640, "min_frames": 10}},
            {"type": "image_url", "image_url": {
                "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/tower.png"}},
            {"type": "text", "text": "视频和图片里有什么"},
        ],
    },
    timeout=60,
)
resp.raise_for_status()
vec = resp.json()["data"]["embedding"]   # 注意是 data.embedding，不是 data[0].embedding
```

官方 SDK 等价写法（底层就是上面的 endpoint）：`from volcenginesdkarkruntime import Ark; Ark(base_url="https://ark.cn-beijing.volces.com/api/v3", api_key=os.environ["ARK_API_KEY"]).multimodal_embeddings.create(model=..., input=[...], encoding_format="float")`。

**示例响应**（开启稀疏向量时，字段层级以文档为准）

```json
{
  "created": 1752133360,
  "data": {
    "embedding": [-0.046875, -0.048828125, 0.02001953125, "..."],
    "sparse_embedding": [
      {"index": 1, "value": 0.0887451171875},
      {"index": 13, "value": 0.0887451171875}
    ],
    "object": "embedding"
  },
  "id": "0217521333598639064...",
  "model": "doubao-embedding-vision-251215",
  "object": "list",
  "usage": {
    "prompt_tokens": 25,
    "prompt_tokens_details": {"image_tokens": 0, "text_tokens": 25},
    "total_tokens": 25
  }
}
```

响应字段：`data.embedding`（`float[]`，或 `encoding_format=base64` 时为字符串）、`data.multi_embedding`（开启多向量时：不压缩为 `float[][]` fp16；带 `compression` 时为 base64 字符串，需 base64 解码 → 按压缩算法解压 → 按 fp16（2 字节小端）解析 → reshape 为 `[num_tokens, dimensions]`）、`data.sparse_embedding[]`（`{index, value}`）、`usage.prompt_tokens` / `usage.prompt_tokens_details.{image_tokens,text_tokens}` / `usage.total_tokens`。

**注意事项**
- 文档自相矛盾（已实测裁决）：API 页把 `data` 标为 `object`，描述却是「向量化结果列表，与 `input` 中的元素一一对应」；两页的示例响应都是单个对象 `data.embedding`，官方 Python 示例还同时兼容 `data` 为 dict 和 list 两种形态；批量附录又说「API 仅支持单次传入单张图片的限制」。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`POST /api/plan/v3/embeddings/multimodal` 的响应 `data` 是**单个对象**，原始响应骨架 `{"id":"...","model":"doubao-embedding-vision-251215","created":...,"object":"list","data":{"embedding":[...]},"usage":{...,"prompt_tokens_details":{"text_tokens":20,"image_tokens":0}}}`——`object` 字段虽写 `list`，`data` 却不是数组；`data.embedding` 为 2048 维数组。写代码按 `data["embedding"]` 取（可保留 list 兜底）；每条素材单独请求。Plan 入口实测，标准入口 `/api/v3` 预期相同但未测。
- 文档自相矛盾（已实测裁决）：向量化指南的运行结果示例打印「文本向量维度: 3072」，而 API 页 `dimensions` 只允许 1024 / 2048（默认 2048），模型列表页最高维度也是 2048。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`/embeddings/multimodal` 与 OpenAI 形态 `/embeddings` 默认都返回 **2048** 维，传 `dimensions: 1024` 返回 1024 维；3072 视为过期输出。
- `multi_embedding` 与 `sparse_embedding` 可同时开启，但稀疏向量仍只对纯文本输入生效；`input` 里混入图片 / 视频再开 `sparse_embedding` 的行为 ⚠ 文档未说明。
- 视频 token 用量：单视频 `[10k, 80k]` token；帧图像被等比压缩到 `[128, 640]` token（约 10 万–50 万像素）；`fps × 时长` 超过 640 帧会按 128 token/帧均匀抽 640 帧，不足 16 帧则按 640 token/帧均匀抽 16 帧（251215+ 可用 `video_url.*` 参数改这套策略）。
- 图片 token 公式：`min(宽 × 高 / 784, 单图 token 限制)`，文档示例的单图上限为 1312。
- 方舟不保留提交的图片 / 视频 / 文本用于训练；图像处理后从服务器删除（文档原文）。

### 2.3 OpenAI 风格 `POST /embeddings` 是否可用（Plan 入口已实测）

三处文档互相打架：

| 来源 | 说法 |
|---|---|
| 「兼容 OpenAI SDK」页（1330626） | 「向量化能力模型不支持 OpenAI API，请使用方舟 SDK」 |
| Coding Plan「记忆增强-Embedding 模型」（2279748） | 专属 Base URL `https://ark.cn-beijing.volces.com/api/coding/v3`「（兼容 OpenAI 接口协议）」；OpenClaw 配置用 `"provider": "openai"` + `model: doubao-embedding-vision` |
| Agent Plan「接入向量化模型」（2375464） | OpenClaw 同样 `"provider": "openai"`，Base URL `/api/plan/v3`；OpenViking 用 `"provider": "volcengine"` + `"dimension": 1024` |

OpenClaw 的 `provider: openai` 只可能调 OpenAI 风格 `POST {baseUrl}/embeddings`（body `{"model","input":["..."]}`，响应 `data[0].embedding`），说明 Plan 入口至少接受这种形态；而 1330626 又明说不支持。文档自相矛盾，**已用真实 API 验证（2026-09-04，Agent Plan Medium）**裁决如下：

| # | 请求（Agent Plan 入口，`Authorization: Bearer $ARK_AGENT_PLAN_API_KEY`） | 结果 |
|---|---|---|
| 1 | `POST https://ark.cn-beijing.volces.com/api/plan/v3/embeddings`，body `{"model":"doubao-embedding-vision","input":"hello"}` | **200**。响应 `data[0].embedding` 为数组（OpenAI 形态），默认 **2048** 维；加 `"dimensions": 1024` 返回 1024 维；`usage: {"prompt_tokens":20,"total_tokens":20}`。「兼容 OpenAI SDK」页「向量化不支持 OpenAI API」在 Plan 入口**不成立** |
| 2 | 同一 endpoint，`input` 传方舟多模态数组 `[{"type":"text","text":"a cat"},{"type":"image_url","image_url":{"url":"..."}}]` | **400**，原文 ``{"error":{"code":"InvalidParameter","message":"The parameter `input[0]` specified in the request are not valid: expected a string, but got `map[text:a cat type:text]` instead. Request id: ...","param":"input[0]","type":"BadRequest"}}`` —— OpenAI 形态的 `input` 只收**字符串**，含图片 / 视频必须走第 3 行 |
| 3 | `POST https://ark.cn-beijing.volces.com/api/plan/v3/embeddings/multimodal`，body `{"model":"doubao-embedding-vision","input":[{"type":"text","text":"hello"}]}` | **200**。响应 `{"id":"...","model":"doubao-embedding-vision-251215","created":...,"object":"list","data":{"embedding":[...]},"usage":{...,"prompt_tokens_details":{"text_tokens":20,"image_tokens":0}}}`，2048 维 —— `data` 是**单对象**不是数组（2.2 的裁决） |
| 4 | 标准入口 `POST /api/v3/embeddings`（OpenAI 形态）、Coding Plan `/api/coding/v3/embeddings[/multimodal]` | ⚠ 未测（无标准 Key / 未订阅 Coding Plan）。Plan 入口两条路径都存在，标准 / Coding Plan 预期相同但未测 |

同样未测：`input` 传**字符串数组** `["a","b"]`（OpenClaw 实际发的形态）是否被 `/embeddings` 接受、返回几条；`instructions` / `encoding_format` 等方舟参数在 `/embeddings` 上是否生效。

**选型**
- 只有文本 → 两条路都行。最省事是 `openai` SDK `client.embeddings.create(model="doubao-embedding-vision", input="...")`，取 `data[0].embedding`（一次一条字符串，数组形态见上面未测项）。
- 含图片 / 视频 → 必须走 `/embeddings/multimodal`（参数表见 2.2），且要按 `data["embedding"]` 单对象取值，不是 `data[0]`。
- 两条路默认都是 2048 维、`dimensions: 1024` 都生效；同一向量库不要混用两条路径或两种维度。
- Agent Plan 官方口径仍是「向量化模型不可用于 API 调用」，程序直连的合规风险自负；在 OpenClaw / OpenViking 里按 2.9 配置最稳。

示例（Agent Plan 入口，OpenAI 形态，与实测请求一致）：

```bash
curl https://ark.cn-beijing.volces.com/api/plan/v3/embeddings \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_AGENT_PLAN_API_KEY" \
  -d '{"model": "doubao-embedding-vision", "input": "hello", "dimensions": 1024}'
```

```python
import os
from openai import OpenAI

client = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
                api_key=os.environ["ARK_AGENT_PLAN_API_KEY"])
resp = client.embeddings.create(model="doubao-embedding-vision", input="hello", dimensions=1024)
vec = resp.data[0].embedding      # 实测 list[float]，len == 1024（不传 dimensions 时 2048）
print(len(vec), resp.usage.prompt_tokens, resp.usage.total_tokens)   # 实测 usage: prompt_tokens 20 / total_tokens 20
```

### 2.4 `instructions` 怎么写（直接决定效果）

仅 251215+ 支持。文档加粗警告：**请勿直接使用系统默认值** `Compress the text into one word`，`Target_modality` 填错「会直接导致检索精度下降」。模板里 `{}` 以外的固定文字 **禁止修改**。

| 任务类型 | 区分 Query / Corpus | 模板 |
|---|---|---|
| 召回、排序 | 是 | Query 侧：`Target_modality: {}.\nInstruction:{}\nQuery:`<br>Corpus 侧：`Instruction:Compress the {} into one word.\nQuery:` |
| 聚类、分类、STS | 否，所有数据同一条 | `Target_modality: {}.\nInstruction:{}\nQuery:` |

`Target_modality` 的填法（Query 侧）：**与 Query 自身模态无关**，取决于 Corpus 底库的模态。底库全是文本 → `text`；全是图文组合 → `text and image`；混有独立的 text / image / video 三类样本 → `text/image/video`（`/` 分隔多种独立模态，`and` 连接同一样本内的多模态）。Corpus 侧模板的 `{}` 只填当前这一条样本的模态：`text` / `image` / `video` / `text and image` / `text and video` / `image and video`。

文档给出的现成配置：

| 场景 | Query 侧 `instructions` | Corpus 侧 `instructions` |
|---|---|---|
| STS 语义相似（两句互比） | `Target_modality: text.\nInstruction:Retrieve semantically similar text\nQuery:` | 同 Query 侧 |
| 问答 / 摘要搜全文 | `Target_modality: text.\nInstruction:为这个句子生成表示以用于检索相关文章\nQuery:` | `Instruction:Compress the text into one word.\nQuery:` |
| 文搜图 | `Target_modality: image.\nInstruction:Compress the text into one word.\nQuery:` | `Instruction:Compress the image into one word.\nQuery:` |
| 文搜视频 | `Target_modality: video.\nInstruction:Compress the text into one word.\nQuery:` | `Instruction:Compress the video into one word.\nQuery:` |
| 图搜文 | `Target_modality: text.\nInstruction:Compress the image into one word.\nQuery:` | `Instruction:Compress the text into one word.\nQuery:` |
| 图搜图（整体匹配） | `Target_modality: image.\nInstruction:Compress the image into one word.\nQuery:` | `Instruction:Compress the image into one word.\nQuery:` |
| 跨模态问答（底库文本 + 图片） | `Target_modality: text/image.\nInstruction:根据这个问题，找到能回答这个问题的相应文本或图片\nQuery:` | 文本：`...Compress the text...`；图片：`...Compress the image...` |
| 原图检索（忽略 PS） | `Target_modality: image.\nInstruction:查找与本图完全相同的图片，可能经过了ps处理，包含缩放、裁剪和水印，请忽略PS处理痕迹\nQuery:` | `Instruction:Compress the image into one word.\nQuery:` |
| 电商同款（忽略背景 / 人物） | `Target_modality: image.\nInstruction:忽略背景以及人物主体并查找这张图片中出现的同款商品图片\nQuery:` | 同上 |
| 商品描述搜图 | `Target_modality: image.\nInstruction:根据下面的文本中对商品的描述，找到对应的符合条件的商品图片\nQuery:` | 同上 |
| 菜品描述搜图 | `Target_modality: image.\nInstruction:根据这段文本中提到的有关的菜品，找到相关的菜品的图片\nQuery:` | 同上 |

短词文搜图（如「蓝色海景」）建议 Query 侧 Instruction 换成 `Find me an everyday image that matches the given caption`。图片局部截取搜原图属于非对称检索，按非对称配置。更多指令可参考 MTEB 仓库 `seed_1_6_embedding_models.py`（文档给的链接）。

### 2.5 维度、相似度、归一化

- **维度**：`dimensions` 只能 `1024` 或 `2048`（默认 2048）。Plan 文档的 OpenViking 配置用 `"dimension": 1024`。同一向量库内维度必须一致；建库时定下来就别改。
- **相似度**：文档原文「余弦相似度 = 向量 L2 归一化后做点积」。

| 向量类型 | 支持版本 | 计算方法 |
|---|---|---|
| 稠密向量 | 所有版本 | 余弦相似度：先 L2 归一化，再点积 |
| 稀疏向量 | 250615+ | 余弦相似度，仅对非零元素做点积，效率更高；**仅文本输入** |

- 文档没有说返回向量是否已归一化 → 自己归一化一次再点积最稳妥（⚠ 文档未说明返回向量是否已 L2 归一化）。
- 文档示例中「香蕉」文本向量与最相似水果图的余弦分数是 0.6462，跨模态相似度绝对值偏低是正常的，阈值要按自己的数据调。

### 2.6 输入限制（图片 / 视频 / Base64）

| 项目 | 限制（文档原文） |
|---|---|
| 图片大小 | 单张 < 10 MB；Base64 方式下整个请求体 ≤ 64 MB |
| 图片像素 | 宽、高各 > 14 px；宽 × 高 < 3600 万 px |
| 图片格式 | JPEG(.jpg/.jpeg) PNG(.png/.apng) GIF WEBP BMP TIFF(.tiff/.tif) ICO DIB ICNS SGI JPEG2000(.jp2 等)；扩展名 / Base64 声明必须与实际格式一致；TIFF / SGI / ICNS / JPEG2000 需对象存储元数据对齐否则解析失败 |
| 视频格式 | MP4(`video/mp4`) AVI(`video/avi`) MOV(`video/quicktime`)，扩展名小写；单文件 ≤ 50 MB；不理解音轨；250615 起支持视频 |
| 数量 | 250615 起「不限数量的视频、文本和图片混合输入」（但见 2.2：全部融合成一条向量，`data` 为单对象已实测） |
| Base64 格式 | 图片 `data:image/<格式>;base64,<编码>`，视频 `data:video/<格式>;base64,<编码>` |

```python
import base64
def to_data_url(path, mime="image/jpeg"):
    with open(path, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"
```

### 2.7 最小 Python 示例：以文搜图

用 `requests` + `numpy`，不依赖 sklearn；对图库和查询分别用 Corpus / Query 侧 `instructions`。

```python
import os
import numpy as np
import requests

URL = "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal"
HEADERS = {"Authorization": f"Bearer {os.environ['ARK_API_KEY']}",
           "Content-Type": "application/json"}
MODEL = "doubao-embedding-vision-251215"
DIM = 1024

def embed(item: dict, instructions: str) -> np.ndarray:
    body = {"model": MODEL, "encoding_format": "float", "dimensions": DIM,
            "instructions": instructions, "input": [item]}
    r = requests.post(URL, headers=HEADERS, json=body, timeout=60)
    r.raise_for_status()
    data = r.json()["data"]
    emb = data["embedding"] if isinstance(data, dict) else data[0]["embedding"]  # 实测 data 为单对象（2.2）；保留 list 兜底
    v = np.asarray(emb, dtype=np.float32)
    return v / (np.linalg.norm(v) + 1e-12)          # L2 归一化后点积 = 余弦相似度

CORPUS_INS = "Instruction:Compress the image into one word.\nQuery:"
QUERY_INS  = "Target_modality: image.\nInstruction:Compress the text into one word.\nQuery:"

image_urls = [f"https://ark-project.tos-cn-beijing.volces.com/doc_image/Fruit{i}.jpg" for i in range(1, 6)]
matrix = np.stack([embed({"type": "image_url", "image_url": {"url": u}}, CORPUS_INS) for u in image_urls])

q = embed({"type": "text", "text": "香蕉"}, QUERY_INS)
scores = matrix @ q
best = int(scores.argmax())
print(image_urls[best], f"{scores[best]:.4f}")
```

### 2.8 批量处理

- 没有批量 endpoint；文档附录的方案是 `volcenginesdkarkruntime.AsyncArk` + `asyncio.gather` 并发多次 `multimodal_embeddings.create`，「全组失败回滚」+ 重试（`AsyncArk(max_retries=2)`）。
- 限流参考模型列表页：`doubao-embedding-vision-*` 最大 RPM 15000、TPM 1200000（「非刚性保障，受平台负载 / 调用方式影响」）。
- 文档批量示例默认 `model="doubao-embedding-vision-241215"`，该版本不在模型列表中（见 2.1 ⚠），换成 `-251215`。

### 2.9 Coding Plan / Agent Plan 里配置向量化（OpenClaw / OpenViking）

两套 Plan 的文档内容几乎相同，差别只有 Base URL 和 Key：

| | Coding Plan | Agent Plan |
|---|---|---|
| Base URL | `https://ark.cn-beijing.volces.com/api/coding/v3`（文档注「兼容 OpenAI 接口协议」） | `https://ark.cn-beijing.volces.com/api/plan/v3`（「包含 `/plan`，请勿混用其他 Base URL」） |
| Key | 方舟 API Key（`ARK_API_KEY`） | Agent Plan 专属 Key（`ARK_AGENT_PLAN_API_KEY`），「其他方舟 API Key 如 Coding Plan API Key 无法在 Agent Plan 中使用」 |
| Model Name | `doubao-embedding-vision`（对应 `doubao-embedding-vision-251215`） | 同左（Agent Plan 入口实测响应 `model: doubao-embedding-vision-251215`，属实）；「只支持在配置文件中指定 Model Name，不支持通过 Auto 及控制台切换」 |
| 计费 | 「与其他模型一致，均会消耗套餐额度，按模型调用次数进行估算」 | AFP 抵扣（向量化系数 ⚠ 文档未说明，本任务输入页未列） |

OpenClaw（`~/.openclaw/openclaw.json` 的 `agents.defaults` 节点，改完 `openclaw gateway restart`）：

```json
"memorySearch": {
  "provider": "openai",
  "model": "doubao-embedding-vision",
  "remote": {
    "baseUrl": "https://ark.cn-beijing.volces.com/api/coding/v3",
    "apiKey": "<ARK_API_KEY>"
  }
}
```

OpenViking（`~/.openviking/ov.conf`）：

```json
"embedding": {
  "dense": {
    "api_base": "https://ark.cn-beijing.volces.com/api/coding/v3",
    "api_key": "<ARK_API_KEY>",
    "provider": "volcengine",
    "dimension": 1024,
    "model": "doubao-embedding-vision"
  },
  "max_concurrent": 10
}
```

Agent Plan 把上面两处 `api/coding/v3` 换成 `api/plan/v3`、Key 换成专属 Key 即可。

---

## 3. 语音（Agent Plan）

语音模型在全部输入文档中 **只出现在 Agent Plan 语境**（「接入语音模型」页 + AFP 抵扣规则页）。标准后付费 API、Coding Plan 是否有同样的 endpoint ⚠ 文档未说明；下面所有 URL 都带 `/plan/` 路径段，不要拿去标准入口试。

### 3.1 核心配置与鉴权头

| 项 | 值 |
|---|---|
| 域名 | `openspeech.bytedance.com`（不是 `ark.cn-beijing.volces.com`） |
| Key | Agent Plan 专属 API Key（`ARK_AGENT_PLAN_API_KEY`），放在 **`X-Api-Key`** 头，不是 `Authorization: Bearer` |
| `X-Api-Resource-Id` | TTS：`seed-tts-2.0`；ASR：`volc.seedasr.sauc.duration` |
| `X-Api-Connect-Id` / `X-Api-Request-Id` | 每次连接 / 请求生成一个 UUID（文档「接口接入建议」） |
| `X-Control-Require-Usage-Tokens-Return: *` | TTS 示例都带，用于在结束事件里拿到 `usage` |
| `X-Api-Sequence: -1` | ASR 示例的连接头 |
| 响应头 `X-Tt-Logid` | 「始终记录」，排障用（WebSocket 里读 `websocket.response.headers['x-tt-logid']`） |

模型名 `doubao-seed-tts-2.0` / `doubao-seed-asr-2.0` **不出现在请求体里**，只用于控制台和计费；协议层靠 `X-Api-Resource-Id` 区分。

### 3.2 流式语音合成 TTS（双流 / 单流 / HTTP）

| 接口 | 协议 | Endpoint | 适用 |
|---|---|---|---|
| 双流 | WebSocket | `wss://openspeech.bytedance.com/api/v3/plan/tts/bidirection` | 流式发文本、流式收音频，实时对话 |
| 单流 | WebSocket | `wss://openspeech.bytedance.com/api/v3/plan/tts/unidirectional/stream` | 一次发完全部文本，流式收音频片段，长文本播报 |
| HTTP | `POST` | `https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional` | 一次发文本，chunked 流式返回，简单 / 非实时 |

两个 WebSocket 接口使用二进制帧协议，文档要求先下载官方 `protocols.py`（`https://arkdocs.tos-cn-beijing.volces.com/files/CodingPlan/protocols.py`），它封装了 `start_connection` / `start_session` / `task_request` / `finish_session` / `finish_connection` / `receive_message` 与 `MsgType`（`FullServerResponse` / `AudioOnlyServer` / `Error`）、`EventType`（`ConnectionStarted` / `SessionStarted` / `TaskRequest` / `SessionFinished` / `ConnectionFinished`）。帧格式细节见文档链接的语音服务 API 文档（6561/1329505、1719100、1598757），本文件输入页未包含。

**请求体**（三种接口相同）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `req_params.text` | string | 是 | — | 待合成文本；双流模式下每个 `TaskRequest` 可以只发一个字符 |
| `req_params.speaker` | string | 是 | — | 音色。文档示例只出现两个：`zh_female_gaolengyujie_uranus_bigtts`、`zh_female_vv_uranus_bigtts`；完整音色列表 ⚠ 文档未说明 |
| `req_params.audio_params.format` | string | 否 | ⚠ 文档未说明 | 示例用 `mp3`；其他取值 ⚠ 文档未说明 |
| `req_params.audio_params.sample_rate` | integer | 否 | ⚠ 文档未说明 | 示例用 `24000` |
| `req_params.audio_params.enable_timestamp` | boolean | 否 | ⚠ 文档未说明 | 双流示例传 `False` |
| `event`（双流） | integer | 双流必填 | — | `EventType.StartSession` / `EventType.TaskRequest`，由 `protocols.py` 提供 |

**示例请求（HTTP 接口）**

```bash
curl -N https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional \
  -H "X-Api-Key: $ARK_AGENT_PLAN_API_KEY" \
  -H "X-Api-Resource-Id: seed-tts-2.0" \
  -H "X-Control-Require-Usage-Tokens-Return: *" \
  -H "Content-Type: application/json" \
  -d '{"req_params":{"text":"你好，这是通过 HTTP 接口合成的语音。","speaker":"zh_female_vv_uranus_bigtts","audio_params":{"format":"mp3","sample_rate":24000}}}'
```

```python
import base64, json, os, requests

url = "https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional"
headers = {
    "X-Api-Key": os.environ["ARK_AGENT_PLAN_API_KEY"],
    "X-Api-Resource-Id": "seed-tts-2.0",
    "Content-Type": "application/json",
    "Connection": "keep-alive",
    "X-Control-Require-Usage-Tokens-Return": "*",
}
payload = {"req_params": {"text": "你好，这是通过 HTTP 接口合成的语音。",
                          "speaker": "zh_female_vv_uranus_bigtts",
                          "audio_params": {"format": "mp3", "sample_rate": 24000}}}
audio = bytearray()
with requests.post(url, headers=headers, json=payload, stream=True, timeout=120) as resp:
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        data = json.loads(line)              # 每行一个 JSON
        if data.get("code", 0) == 0 and data.get("data"):
            audio.extend(base64.b64decode(data["data"]))
        if data.get("code", 0) == 20000000:  # 结束标记（文档示例代码，未实测）
            break
        if data.get("code", 0) > 0:
            raise RuntimeError(data)
open("tts.mp3", "wb").write(audio)
```

**示例响应（HTTP）**：按行返回 JSON，每行 `{"code": 0, "data": "<base64 音频块>", ...}`；`code == 20000000` 表示结束（来自文档示例代码，未实测）；`code > 0` 为错误。其他字段 ⚠ 文档未说明。

**双流 WebSocket 流程**（照文档示例）：`websockets.connect(URL, additional_headers=headers, max_size=10*1024*1024)` → `start_connection` 并等待 `ConnectionStarted` → 每句话 `start_session(ws, json.dumps({"event": EventType.StartSession, "req_params": {...}}).encode(), session_id)` 等 `SessionStarted` → 逐字 `task_request(...)`（示例每字间隔 5 ms）→ `finish_session` → 循环 `receive_message`：`AudioOnlyServer` 帧的 `payload` 是音频字节，`FullServerResponse` 且 `event == SessionFinished` 结束本句 → 全部结束后 `finish_connection`，`ConnectionFinished` 的 payload 里带 `usage`。单流接口更简单：`full_client_request(ws, json.dumps(body).encode())` 一次发完，然后同样循环收音频直到 `SessionFinished`。

### 3.3 流式语音识别 ASR（双流 / 单流）

| 接口 | 协议 | Endpoint | 适用 |
|---|---|---|---|
| 双流 | WebSocket | `wss://openspeech.bytedance.com/api/v3/plan/sauc/bigmodel_async` | 边发音频边实时返回识别结果 |
| 单流 | WebSocket | `wss://openspeech.bytedance.com/api/v3/plan/sauc/bigmodel_nostream` | 流式发音频，全部发完或超过 15s 后统一返回高精度结果 |

两者客户端代码完全相同，只换 URL。ASR 没有 HTTP 接口。

**二进制帧协议**（文档示例代码内嵌，未提供独立协议页）：4 字节 header + 4 字节 big-endian `seq`（int32）+ 4 字节 payload 长度（uint32）+ gzip 压缩后的 payload。

| header 字节 | 内容 |
|---|---|
| byte0 | `(protocol_version=0b0001) << 4 \| header_size=1` |
| byte1 | `message_type << 4 \| flags`。message_type：`0b0001` CLIENT_FULL_REQUEST（首包 JSON 配置）、`0b0010` CLIENT_AUDIO_ONLY_REQUEST（音频）、服务端 `0b1001` FULL_RESPONSE、`0b1111` ERROR。flags：`0b0001` POS_SEQUENCE（普通包）、`0b0011` NEG_WITH_SEQUENCE（最后一包，且 seq 取负） |
| byte2 | `serialization << 4 \| compression`：JSON `0b0001`，GZIP `0b0001` |
| byte3 | 保留 `0x00` |

**首包 JSON（CLIENT_FULL_REQUEST，seq=1）**

| 参数 | 类型 | 说明（来自文档示例） |
|---|---|---|
| `user.uid` | string | 任意用户标识 |
| `audio.format` | string | 示例 `wav`（示例用 ffmpeg 转成 16k / 16bit / 单声道 PCM WAV） |
| `audio.codec` | string | 示例 `raw` |
| `audio.rate` / `audio.bits` / `audio.channel` | integer | 示例 `16000` / `16` / `1` |
| `request.model_name` | string | 示例 `bigmodel` |
| `request.enable_itn` / `enable_punc` / `enable_ddc` | boolean | 逆文本规整 / 标点 / 语义顺滑，示例都 `true`（含义为通常理解，文档未解释） |
| `request.show_utterances` | boolean | 示例 `true` |
| `request.enable_nonstream` | boolean | 示例 `false` |

其他取值范围 ⚠ 文档未说明（详见文档链接的 6561/1354869「大模型流式语音识别 API」，不在本任务输入页内）。

**音频包**：把 WAV 数据按 `声道数 × 采样字节 × 采样率 × 200ms` 切段，每段 gzip 后作为 CLIENT_AUDIO_ONLY_REQUEST 发送，`seq` 从 2 递增，最后一段用 NEG_WITH_SEQUENCE 且 `seq = -seq`；示例每段之间 `sleep(200ms)` 模拟实时流。

**服务端响应解析**：`header_size = msg[0] & 0x0f`（×4 字节），`flags & 0x01` → 后接 4 字节 `payload_sequence`；`flags & 0x02` → `is_last_package=True`；`flags & 0x04` → 后接 4 字节 `event`。FULL_RESPONSE 后接 4 字节 payload_size；ERROR 后接 4 字节 `code` + 4 字节 size。payload gzip 解压后是 JSON（识别文本结构 ⚠ 文档未说明，示例只是原样打印 `payload_msg`）。收到 `is_last_package` 或 `code != 0` 即结束。

**示例（Python，双流；依赖 `aiohttp`）**——文档示例约 500 行，核心骨架：

```python
import asyncio, gzip, json, os, struct, uuid, aiohttp

URL = "wss://openspeech.bytedance.com/api/v3/plan/sauc/bigmodel_async"

def frame(msg_type, flags, payload: bytes, seq: int) -> bytes:
    hdr = bytes([(0b0001 << 4) | 1, (msg_type << 4) | flags, (0b0001 << 4) | 0b0001, 0x00])
    body = gzip.compress(payload)
    return hdr + struct.pack(">i", seq) + struct.pack(">I", len(body)) + body

async def main(pcm_wav: bytes):
    rid = str(uuid.uuid4())
    headers = {"X-Api-Key": os.environ["ARK_AGENT_PLAN_API_KEY"],
               "X-Api-Resource-Id": "volc.seedasr.sauc.duration",
               "X-Api-Request-Id": rid, "X-Api-Connect-Id": rid, "X-Api-Sequence": "-1"}
    cfg = {"user": {"uid": "demo"},
           "audio": {"format": "wav", "codec": "raw", "rate": 16000, "bits": 16, "channel": 1},
           "request": {"model_name": "bigmodel", "enable_itn": True, "enable_punc": True,
                       "enable_ddc": True, "show_utterances": True, "enable_nonstream": False}}
    async with aiohttp.ClientSession() as s, s.ws_connect(URL, headers=headers) as ws:
        await ws.send_bytes(frame(0b0001, 0b0001, json.dumps(cfg).encode(), 1))
        await ws.receive()                       # 首包确认
        seg = 16000 * 2 * 1 * 200 // 1000        # 200ms 一段
        chunks = [pcm_wav[i:i + seg] for i in range(0, len(pcm_wav), seg)]
        async def sender():
            for i, c in enumerate(chunks, start=2):
                last = i == len(chunks) + 1
                await ws.send_bytes(frame(0b0010, 0b0011 if last else 0b0001, c, -i if last else i))
                await asyncio.sleep(0.2)
        asyncio.create_task(sender())
        async for m in ws:
            if m.type != aiohttp.WSMsgType.BINARY:
                break
            b = m.data; hs = (b[0] & 0x0f) * 4; mt = b[1] >> 4; fl = b[1] & 0x0f; p = b[hs:]
            if fl & 0x01: p = p[4:]
            if fl & 0x04: p = p[4:]
            code = 0
            if mt == 0b1001: p = p[4:]
            elif mt == 0b1111: code = struct.unpack(">i", p[:4])[0]; p = p[8:]
            if p: print(json.loads(gzip.decompress(p)))
            if fl & 0x02 or code != 0:
                break
```

curl 无法演示 WebSocket 二进制协议，此处不给 curl。

### 3.4 计费（AFP 抵扣）

| 模型 | 抵扣系数 | 单位 |
|---|---|---|
| `doubao-seed-tts-2.0` | 1350 | 万字符 |
| `doubao-seed-asr-2.0` | 450 | 小时 |

文档示例：TTS 请求 2000 字符 → `2000 / 10000 × 1350 = 270 AFP`。未开超额后付费时只扣套餐内 AFP，不动其他资源包 / 余额；开启后套餐用尽会自动切到后付费（Base URL / Key / 模型名都不用改）。

---

## 4. 同声传译

### 4.1 Endpoint、鉴权、模型

**Endpoint**: `wss://ark-beta.cn-beijing.volces.com/api/v3/realtime?service=clasi&model=<Model>`
**用途**: 推送音频流，服务端实时返回原文转录（`response.input_audio_transcription.delta`）和译文（`response.input_audio_translation.delta`）。与 3.3 ASR 的区别：ASR 只转写；同传同时给转录 + 翻译，且走方舟自己的 realtime 事件协议（JSON 文本帧，不是二进制）。
**入口**: 标准 API 语境（示例用 `ARK_API_KEY`），且是 **邀测能力**，需提交测试申请工单。Coding / Agent Plan 是否可用 ⚠ 文档未说明。
**鉴权**: 「支持 API Key 鉴权方式」。WebSocket 握手时 Key 放在哪个头 ⚠ 文档未说明（示例代码在 zip 附件里，本任务输入页未包含）；按方舟数据面惯例应为 `Authorization: Bearer $ARK_API_KEY`，待实测。
**模型**: URL 里的 `<Model>` 文档只写「替换为模型的 Model ID，需配置同声传译模型」，服务端回显形如 `doubao-clasi-***`；具体 Model ID ⚠ 文档未说明（模型列表页也没有同传模型条目）。

### 4.2 客户端事件

**`session.update`**——建连后先发，随时可再发；服务端回 `session.updated`（含完整生效配置）。要清除某字段就把它设为空。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `event_id` | string | 否 | — | 客户端生成的事件 ID |
| `type` | string | 是 | — | 固定 `session.update` |
| `session.modalities` | list | 否 | `["text"]` | 目前只支持 `text` |
| `session.input_audio_format` | string | 是 | `pcm16` | `pcm16`（16 kHz、16 bit、单通道、未压缩）或 `opus` |
| `session.input_audio_translation.source_language` | string | 是 | `zh` | ISO 639-1，目前仅 `zh` / `en` |
| `session.input_audio_translation.target_language` | string | 是 | `en` | 仅 `en` / `zh`；**必须与源语种不同** |
| `session.input_audio_translation.add_vocab.hot_word_list` | list | 否 | — | 源语言热词，其他语言无效 |
| `session.input_audio_translation.add_vocab.glossary_list` | list | 否 | — | 术语对照 `[{"input_audio_transcription": "原文", "input_audio_translation": "译文"}]` |
| `session.speaker_detection.enable_speaker_change_detection` | boolean | 否 | `false` | 开启后 delta 事件带 `speaker_change` |

热词 + 术语合计不超过 200 个，超过报错（文档原文，未实测）。

**`input_audio.commit`**——`{"type": "input_audio.commit", "audio": "<base64>"}`。音频须是 `input_audio_format` 指定的格式，**单次 ≤ 10 KB**（超过则服务端跳过并回 `error`）；建议每 100–200 ms 发一次；单连接 **CPM ≤ 700 次/分钟**，超出的事件被跳过并回 `error`。

**`input_audio.done`**——`{"type": "input_audio.done"}`，之后服务端不再接受 `commit`，处理完剩余音频后发 `response.done`。

### 4.3 服务端事件

| 事件 `type` | 何时 | 关键字段 |
|---|---|---|
| `session.created` | 连接建立后立即 | `session.id`（`sess_***`）、`session.object="realtime.session"`、`session.model`（`doubao-clasi-***`）、`session.input_audio_format`、`session.modalities`、`session.input_audio_translation.*`、`session.speaker_detection`（初始 `null`） |
| `session.updated` | 收到 `session.update` 后 | 同上，为完整生效配置 |
| `response.created` | 新 Response 创建 | `response.id`（`resp_***`）、`response.object="realtime.response"`、`response.status="in_progress"`、`response.usage.{total_tokens,input_tokens,output_tokens,input_token_details.audio_tokens}` |
| `response.input_audio_transcription.delta` | 流式转录 | `response_id`、`delta`（文本）、`language`（`zh`/`en`）、`start_ms` / `end_ms`（在原始音频中的时间段）、`speaker_change`（仅开启说话人检测时返回） |
| `response.input_audio_translation.delta` | 流式译文 | 字段同上 |
| `response.done` | 服务端处理完全部音频 | `response.status`：`completed` / `failed` / `timeout`；`response.usage.*` |
| `error` | 出错（多数可恢复，连接保持） | `error.type`（如 `BadRequest`）、`error.code`（如 `MissingParameter`、`InvalidParameter`）、`error.message`、`error.param`、`error.event_id`（引发错误的客户端事件） |

示例（文档原文）：

```json
{"event_id": "event_127", "type": "response.input_audio_transcription.delta",
 "response_id": "resp_0217...", "delta": "定制服务", "language": "zh",
 "start_ms": 0, "end_ms": 800, "speaker_change": true}
{"event_id": "event_128", "type": "response.input_audio_translation.delta",
 "response_id": "resp_0217...", "delta": "The customized service", "language": "en",
 "start_ms": 0, "end_ms": 800, "speaker_change": true}
{"event_id": "event_129", "type": "error",
 "error": {"code": "InvalidParameter", "type": "BadRequest", "param": "input audio format must be pcm16",
           "message": "A parameter specified in the request is not valid: input audio format must be pcm16 Request id: ****"}}
```

### 4.4 限制与超时

| 项目 | 限制（文档原文，未实测） |
|---|---|
| 单连接最长 | 2 小时，超时强制断连，`response.done.status="timeout"` |
| 单连接静默 | 0.5 小时，同上 |
| 主账号同时在线连接数 | 100 |
| 单次 `input_audio.commit` 音频 | ≤ 10 KB，超过跳过不处理 |
| 单连接 CPM | 700 次/分钟，每连接独立 |
| 单连接 output TPM | 1200 tokens/分钟，每连接独立 |
| 语种 | 仅 `zh` ↔ `en` |
| 中途切换语种 | 不建议直接 `session.update`；先静默 ≥ 4 秒（不发音频）、等已发音频的结果全部返回，再更新 |

### 4.5 最小 Python 示例

文档只提供 Node.js / Java / Python 工程 zip（`ark_clasi_*_beta.zip`，运行前 `export ARK_API_KEY=...`，用 FFmpeg 把 MP3 转为 PCM）。下面是按事件表写的骨架（依赖 `websockets`）；鉴权头形式见 4.1 ⚠。

```python
import asyncio, base64, json, os, websockets

MODEL = "<Model>"   # 同传模型 Model ID，⚠ 文档未给出具体值
URL = f"wss://ark-beta.cn-beijing.volces.com/api/v3/realtime?service=clasi&model={MODEL}"

async def main(pcm16_bytes: bytes):
    headers = {"Authorization": f"Bearer {os.environ['ARK_API_KEY']}"}  # ⚠ 头名待实测
    async with websockets.connect(URL, additional_headers=headers) as ws:
        print(json.loads(await ws.recv())["type"])          # session.created
        await ws.send(json.dumps({"type": "session.update", "session": {
            "input_audio_format": "pcm16", "modalities": ["text"],
            "input_audio_translation": {"source_language": "zh", "target_language": "en",
                                        "add_vocab": {"glossary_list": [
                                            {"input_audio_transcription": "大模型",
                                             "input_audio_translation": "LLM"}]}}}}))

        async def sender():
            step = 16000 * 2 * 200 // 1000                   # 200ms 的 pcm16 = 6400 字节 < 10KB
            for i in range(0, len(pcm16_bytes), step):
                await ws.send(json.dumps({"type": "input_audio.commit",
                                          "audio": base64.b64encode(pcm16_bytes[i:i + step]).decode()}))
                await asyncio.sleep(0.2)                     # 文档建议 100–200ms 一次
            await ws.send(json.dumps({"type": "input_audio.done"}))
        asyncio.create_task(sender())

        async for raw in ws:
            ev = json.loads(raw)
            t = ev["type"]
            if t == "response.input_audio_transcription.delta":
                print("原文", ev["start_ms"], ev["end_ms"], ev["delta"])
            elif t == "response.input_audio_translation.delta":
                print("译文", ev["start_ms"], ev["end_ms"], ev["delta"])
            elif t == "error":
                print("error", ev["error"])
            elif t == "response.done":
                print(ev["response"]["status"], ev["response"]["usage"])
                break
```

curl 不支持 WebSocket 事件交互，此处不给 curl。

---

## 5. 来源页面

| 标题 | URL | 文档更新时间 |
|---|---|---|
| 多模态向量化 API | https://www.volcengine.com/docs/82379/1523520 | 2026-08-27 |
| 向量化（指南） | https://www.volcengine.com/docs/82379/1409291 | 2026-07-31 |
| 兼容 OpenAI SDK（仅向量化一节） | https://www.volcengine.com/docs/82379/1330626 | 2026-06-23 |
| Agent Plan 接入向量化模型 | https://www.volcengine.com/docs/82379/2375464 | 2026-07-29 |
| Coding Plan 记忆增强-Embedding 模型 | https://www.volcengine.com/docs/82379/2279748 | 2026-04-14 |
| Agent Plan 接入语音模型 | https://www.volcengine.com/docs/82379/2516286 | 2026-07-29 |
| 同声传译 API | https://www.volcengine.com/docs/82379/1394617 | 2026-08-13 |
| 同声传译（指南） | https://www.volcengine.com/docs/82379/1433754 | 2026-07-22 |
| 套餐内 AFP 抵扣规则（仅语音模型系数） | https://www.volcengine.com/docs/82379/2516283 | 2026-09-01 |
| 模型列表（仅向量化能力一节） | https://www.volcengine.com/docs/82379/1330310 | 2026-09-02 |
