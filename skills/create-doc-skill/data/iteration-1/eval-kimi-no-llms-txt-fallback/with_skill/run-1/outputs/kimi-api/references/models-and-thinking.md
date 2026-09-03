> 内容整理自 platform.kimi.com/docs（抓取于 2026-09-03），**尚未用真实 API 调用验证**；实际报错优先信任 API。

# Kimi 模型目录、选型与思考模式

- Base URL：`https://api.moonshot.cn/v1`（Chat Completions：`POST /v1/chat/completions`）
- 鉴权：`Authorization: Bearer $MOONSHOT_API_KEY`（唯一必需 header；JSON 请求另加 `Content-Type: application/json`）
- Python：`OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")`；Kimi 专有参数（`thinking`）必须走 `extra_body`，`reasoning_effort` 是 OpenAI SDK 原生参数可直接传。
- 国际站 `platform.kimi.ai` 的 Key 与中国站互不通用（混用 401）。

## 目录

1. [速查：模型 × 参数约束对照表](#1-速查模型--参数约束对照表)
2. [选型：我想做 X → 选哪个模型](#2-选型我想做-x--选哪个模型)
3. [当前可用模型目录](#3-当前可用模型目录)
4. [已下线模型清单（调用 404）](#4-已下线模型清单调用-404)
5. [列出模型 `GET /v1/models`](#5-列出模型-get-v1models)
6. [思考模式与 `reasoning_content`](#6-思考模式与-reasoning_content)
7. [K3：`reasoning_effort` 推理强度](#7-k3reasoning_effort-推理强度)
8. [K2.6：`thinking` 参数（开/关/keep）](#8-k26thinking-参数开关keep)
9. [K2.7 Code：思考强制开启](#9-k27-code思考强制开启)
10. [Preserved Thinking：多轮与工具调用回传](#10-preserved-thinking多轮与工具调用回传)
11. [固定采样参数与 `tool_choice` 约束](#11-固定采样参数与-tool_choice-约束)
12. [思考 token 计费与输出上限](#12-思考-token-计费与输出上限)
13. [从 K2.6 / K2.7 迁移到 K3](#13-从-k26--k27-迁移到-k3)
14. [定价](#14-定价)
15. [账户等级与限速](#15-账户等级与限速)
16. [文档矛盾与未说明项汇总](#16-文档矛盾与未说明项汇总)

---

## 1. 速查：模型 × 参数约束对照表

`kimi-k2.7-code-highspeed` 与 `kimi-k2.7-code` 为同一模型，参数约束完全一致，仅输出速度不同，下表合并为一列。

| 项目 | `kimi-k3` | `kimi-k2.7-code` / `-highspeed` | `kimi-k2.6` |
|---|---|---|---|
| 上下文窗口 | 1M tokens | 256K tokens | 256K tokens |
| 输入模态 | 文本 / 图片 / 视频 | 文本 / 图片 / 视频 | 文本 / 图片 / 视频 |
| 思考 | 始终开启，**关不掉** | 始终开启，**关不掉** | 默认开启，可关 |
| 顶层 `reasoning_effort` | `"low"` / `"high"` / `"max"`，默认 `"max"` | 不支持 | 不支持 |
| `thinking.type` | 不支持，不应传（传入是否报错 ⚠ 文档未说明） | 仅 `"enabled"`；传 `"disabled"` 报错 | `"enabled"`（默认）/ `"disabled"` |
| `thinking.keep` | —（Preserved Thinking 始终开启） | 不传 / `null` / `"all"` 均按 `"all"`；其他值报错 | `null`（默认，不保留）/ `"all"` |
| Preserved Thinking | 始终开启 | 始终开启 | 需显式 `keep: "all"` |
| `tool_choice` | `auto` / `none` / `required` / 指定函数对象 | `auto` / `none`；`required` 报错；指定函数对象 ⚠ 文档自相矛盾（见 §11） | 同 K2.7 |
| `temperature` | 固定 `1.0` | 固定 `1.0` | 思考 `1.0` / 非思考 `0.6` |
| `top_p` | 固定 `0.95` | 固定 `0.95` | 固定 `0.95` |
| `n` | 固定 `1` | 固定 `1` | 固定 `1` |
| `presence_penalty` / `frequency_penalty` | 固定 `0` | 固定 `0` | 固定 `0` |
| 输出上限 | `max_completion_tokens` 默认 131072，最大 1048576 | `max_tokens` 默认 32768 | `max_tokens` 默认 32768 |
| 访问条件 | 累计充值 ≥ ¥10 后解锁；15 元新人代金券不可用 | ⚠ 文档未说明 | ⚠ 文档未说明 |
| 输出速度 | ⚠ 文档未说明 | 普通版 ⚠ 未说明；高速版约 180 tok/s（短上下文可达 260） | ⚠ 文档未说明 |

"固定"表示：传入其他值会报错，**建议不要显式传入**。

## 2. 选型：我想做 X → 选哪个模型

| 我想做 | 选 | 依据 |
|---|---|---|
| 最强推理、长程 Agent、知识工作、超过 256K 的上下文 | `kimi-k3` | 旗舰；1M 上下文；`reasoning_effort` 可调 |
| 需要 `tool_choice: "required"` 或强制调用指定函数 | `kimi-k3` | 仅 K3 支持 `required`；K2.x 传入报错 |
| 已有 OpenAI 代码里用了 `reasoning_effort` | `kimi-k3` | 顶层字段直接兼容，取值改为 low/high/max |
| 编程 Agent / IDE 内长任务，追求速度 | `kimi-k2.7-code-highspeed` | 同 K2.7 Code 模型，输出约 180 tok/s（资源有限，体验可能波动） |
| 编程 Agent，常规吞吐 | `kimi-k2.7-code` | Coding 模型；长上下文指令遵循更可靠 |
| 简单对话 / 分类 / 抽取，要低延迟、**不要思考** | `kimi-k2.6` + `thinking: {"type": "disabled"}` | 唯一可关思考的在线模型 |
| 想省 token：跨轮不保留思考 | `kimi-k2.6`（默认 `keep: null`） | K3 / K2.7 跨轮思考始终保留并计费 |
| 用官方内置 `$web_search` | `kimi-k2.6` 非思考模式 | `$web_search` 与 K2.6 思考模式不兼容；且联网搜索正在升级，近期不建议使用 |
| 图片 / 视频理解 | 三者均可 | 均支持 `image_url` / `video_url`；不支持公网 URL，只能 base64 或 `ms://<file-id>` |
| 结构化输出（`response_format: json_schema`） | 三者均可（OpenAPI 各分支均含该字段） | K3 页面有完整示例；只解析 `content`，不解析 `reasoning_content` |
| 只有新人代金券、没充值 | `kimi-k2.7-code` / `kimi-k2.6` | 代金券不可用于 K3（K2.x 是否可用 ⚠ 文档未说明） |
| 想用 Claude Code / Anthropic SDK | 任一模型，base_url 改 `https://api.moonshot.cn/anthropic` | 见鉴权文档；本文只覆盖 Chat Completions |

## 3. 当前可用模型目录

### `kimi-k3`
- **用途**：旗舰模型（2.8 万亿参数，KDA + Attention Residuals，MoE 896 专家激活 16），面向长程编程、知识工作、深度推理；擅长结合截图/视觉反馈的软件工程任务。
- **上下文**：1M tokens；前缀缓存自动启用（前一请求 prompt tokens > 256 才会被缓存）。
- **模态**：文本、图片（base64）、视频（`client.files.create(purpose="video")` 后用 `ms://<file-id>`）。
- **思考**：始终开启，Preserved Thinking 始终开启；"可能返回 `reasoning_content`"（文档措辞为"可能"，非保证每次返回）。
- **访问**：累计充值 ≥ ¥10 解锁；新用户 15 元代金券不可用。
- **上线日期**：⚠ 文档未说明（changelog 无 K3 上线条目）。

### `kimi-k2.7-code` / `kimi-k2.7-code-highspeed`
- **用途**：Coding 模型，长上下文指令遵循更可靠、编程任务成功率更高；相比 K2.6：Kimi Code Bench v2 +21.8%、Program-Bench +11%、MLS Bench Lite +31.5%；Agent 基准约 +10%。
- **上下文**：256K。**模态**：文本、图片、视频。
- **思考**：始终开启，**不支持非思考模式**；Preserved Thinking 始终开启。
- **高速版**：同一模型，输出速度约为普通版 5-6 倍（中位输入约 180 tok/s，短上下文可达 260 tok/s）；资源有限，体验可能偶有波动。
- **上线日期**：⚠ 文档未说明。

### `kimi-k2.6`
- **用途**：通用模型，Agent / 代码 / 视觉综合能力；支持思考与非思考模式，对话与 Agent 任务。
- **上下文**：256K。**模态**：文本、图片、视频。
- **思考**：默认开启，可用 `thinking.type: "disabled"` 关闭；跨轮保留需 `thinking.keep: "all"`。
- **限制**：思考模式下官方内置 `$web_search` 不兼容。
- **上线日期**：⚠ 文档未说明。

### 多模态输入通用限制（三模型相同）
- 图片格式：png、jpeg、webp、gif；视频格式：mp4、mpeg、mov、avi、x-flv、mpg、webm、wmv、3gpp。
- 推荐图片 ≤ 4K（4096×2160）、视频 ≤ 1080p；更高分辨率只增加处理时间。
- 不支持公网 URL 图片，仅 base64（或上传文件后引用）；请求 body ≤ 100M；图片数量无上限。
- 图片/视频按动态 token 计费，可先用计算 token 接口预估。

## 4. 已下线模型清单（调用 404）

调用以下模型返回 **404（模型不存在）**，请迁移到 `kimi-k3`。

| 模型 | 下线日期 | 来源 |
|---|---|---|
| `kimi-k2.5` | 2026-08-31 16:00（国内外全平台） | 模型列表 + changelog |
| `moonshot-v1-8k` / `-32k` / `-128k` | 2026-08-31 | 同上 |
| `moonshot-v1-auto` | 2026-08-31（2024-08-28 上线） | 同上 |
| `moonshot-v1-8k-vision-preview` / `-32k-` / `-128k-` | 2026-08-31（vision-preview 2025-01-13 上线） | 同上 |
| `kimi-k2-0905-preview` / `kimi-k2-0711-preview` / `kimi-k2-turbo-preview` | 2026-05-25 | 模型列表 |
| `kimi-k2-thinking` / `kimi-k2-thinking-turbo` | 2026-05-25 | 模型列表 |
| `kimi-latest` | 2026-01-28（2025-02-17 上线） | 模型列表 |
| `kimi-thinking-preview` | 2025-11-11 | 模型列表 |

注意：changelog 只记录了 2026-08-31 这一批下线；`kimi-k2-*`、`kimi-latest`、`kimi-thinking-preview` 的下线日期仅见于模型列表页。

## 5. 列出模型 `GET /v1/models`

**用途**：运行时探测当前可用模型及其能力标志，避免硬编码已下线模型。

**响应字段**（OpenAPI）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `data[].id` | string | 模型 ID |
| `data[].created` | integer | 创建时间戳 |
| `data[].owned_by` | string | — |
| `data[].context_length` | integer | 最大上下文长度（tokens） |
| `data[].supports_image_in` | boolean | 是否支持图片输入 |
| `data[].supports_video_in` | boolean | 是否支持视频输入 |
| `data[].supports_reasoning` | boolean | 是否支持深度思考 |

```bash
curl https://api.moonshot.cn/v1/models \
  -H "Authorization: Bearer $MOONSHOT_API_KEY"
```

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")
for m in client.models.list().data:
    # context_length 等是 Kimi 扩展字段，SDK 类型里没有，用 model_extra 取
    extra = m.model_extra or {}
    print(m.id, extra.get("context_length"), extra.get("supports_reasoning"))
```

**注意**：仅 401 错误在 OpenAPI 中列出；能力字段的取值示例 ⚠ 文档未说明。

## 6. 思考模式与 `reasoning_content`

**用途**：思考模型先输出推理 token（`reasoning_content`），再输出最终回答（`content`）。三款在线模型都是思考模型。

**关键字段（响应）**：

| 字段 | 位置 | 说明 |
|---|---|---|
| `choices[].message.reasoning_content` | 非流式 | string \| null；仅思考启用时返回，与 `content` 同级 |
| `choices[].delta.reasoning_content` | 流式 | 增量思考；**一定先于 `content` 出现**，可用"出现 `content`"判定思考结束 |
| `choices[].finish_reason` | 两者 | `stop` / `length` / `tool_calls` |
| `usage.cached_tokens` | 两者 | 命中前缀缓存的 token 数 |

**示例请求**（K2.6 默认思考，无需任何额外参数）：

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k2.6",
    "messages": [{"role": "user", "content": "请解释 1+1=2。"}]
  }'
```

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

stream = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[{"role": "user", "content": "请解释 1+1=2。"}],
    max_tokens=1024 * 32,   # 不要传 temperature
    stream=True,
)
thinking = False
for chunk in stream:
    if not chunk.choices:
        continue
    delta = chunk.choices[0].delta
    # SDK 类型没有 reasoning_content 字段，只能 hasattr/getattr
    if delta and hasattr(delta, "reasoning_content"):
        if not thinking:
            thinking = True
            print("=== 思考开始 ===")
        print(getattr(delta, "reasoning_content"), end="")
    if delta and delta.content:
        if thinking:
            thinking = False
            print("\n=== 思考结束 ===")
        print(delta.content, end="")
```

**示例响应**（非流式，字段依据 OpenAPI 响应 schema；具体值为示意）：

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1756857600,
  "model": "kimi-k2.6",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "reasoning_content": "用户问的是皮亚诺公理下的加法定义……",
      "content": "1+1=2 可以从皮亚诺公理推出：……"
    },
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 12, "completion_tokens": 350, "total_tokens": 362, "cached_tokens": 0}
}
```

**注意事项**：
- openai SDK 的 `ChatCompletionMessage` / `ChoiceDelta` 类型没有 `reasoning_content` 属性，`message.reasoning_content` 直接访问不可靠，用 `hasattr` + `getattr`；裸 HTTP / 其他框架直接读同级字段。
- `reasoning_content` 的 token 受 `max_tokens` 约束：思考 + 回答 ≤ `max_tokens`。文档建议思考模型 **`max_tokens >= 16000`**，示例统一用 `1024*32`。
- 思考模型输出更长，建议 `stream=True` 以改善体验并减少网络超时。
- 结构化输出时只解析 `content`，不要解析 `reasoning_content`。

## 7. K3：`reasoning_effort` 推理强度

**用途**：K3 始终推理、不能关思考；用顶层 `reasoning_effort` 调节深度 / 延迟 / token 消耗。觉得思考太长就设 `"low"`。

**关键参数**：

| 字段 | 类型 | 必填 | 取值 | 默认 |
|---|---|---|---|---|
| `reasoning_effort` | string | 否 | `"low"` / `"high"` / `"max"` | `"max"` |

（没有 `"medium"`、`"minimal"`、`"none"` 等 OpenAI 取值；传入是否报错 ⚠ 文档未说明。）

**示例请求**：

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k3",
    "messages": [{"role": "user", "content": "请推导数列 1, 4, 9, 25, 64, ... 的通项公式。"}],
    "reasoning_effort": "high"
  }'
```

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[{"role": "user", "content": "请推导数列 1, 4, 9, 25, 64, ... 的通项公式。"}],
    reasoning_effort="high",   # OpenAI SDK 原生参数，直接传即可；不要传 thinking
)
message = completion.choices[0].message
if hasattr(message, "reasoning_content"):
    print(getattr(message, "reasoning_content"))
print(message.content)
```

**示例响应**：结构同 §6，`model` 为 `"kimi-k3"`；`reasoning_content` "可能返回"。

**注意事项**：
- **切换档位会破坏前缀缓存命中**：在会话开始前定好 `effort`，不要中途切换。
- K3 不支持 `thinking` 参数；从 K2.x 迁移时删掉 `thinking`。
- K3 多轮 / 工具调用必须把完整 assistant message（含 `reasoning_content` 和 `tool_calls`）原样回传，见 §10。

## 8. K2.6：`thinking` 参数（开/关/keep）

**用途**：K2.6 是唯一可关思考的在线模型；`thinking` 是 Kimi 专有参数。

**关键参数**：

| 字段 | 类型 | 取值 | 默认 | 说明 |
|---|---|---|---|---|
| `thinking.type` | string | `"enabled"` / `"disabled"` | `"enabled"` | 当前轮是否产生 `reasoning_content` |
| `thinking.keep` | string \| null | `null` / `"all"` | `null` | 是否把历史轮次的 `reasoning_content` 提供给模型；只影响历史轮，不影响当前轮是否思考 |

合法组合：`{"type":"enabled"}`、`{"type":"disabled"}`、`{"type":"enabled","keep":"all"}`。
⚠ 文档自相矛盾：K2.6 快速开始页参数表写"只能为 `{"type":"enabled"}` 或 `{"type":"disabled"}`"，未提 `keep`；模型参数参考、思考模型指南、OpenAPI 均列出 `keep: "all"`。以后三者为准。

**示例请求（关闭思考）**：

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k2.6",
    "messages": [{"role": "user", "content": "你好"}],
    "thinking": {"type": "disabled"}
  }'
```

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

response = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[{"role": "user", "content": "你好"}],
    extra_body={"thinking": {"type": "disabled"}},   # thinking 不是 SDK 参数，必须放 extra_body
    max_tokens=1024 * 32,
)
print(response.choices[0].message.content)
```

**示例响应**：关闭思考后 `message` 中没有 `reasoning_content`（或为 null），`content` 直接给出回答。

**注意事项**：
- 关闭思考后 `temperature` 固定值从 `1.0` 变为 `0.6`，仍不可显式传入其他值。
- 思考模式下 `tool_choice` 只能 `auto` / `none`；内置 `$web_search` 需先关思考。
- `keep: "all"` 推荐与 `type: "enabled"` 搭配；用法见 §10。

## 9. K2.7 Code：思考强制开启

**用途**：编程场景；`thinking` 可省略，模型始终输出 `reasoning_content`。

**关键参数**：

| 字段 | 允许值 | 说明 |
|---|---|---|
| `thinking.type` | 仅 `"enabled"` | 传 `"disabled"` 报错 |
| `thinking.keep` | 不传 / `null` / `"all"` | 均按 `"all"` 处理；其他值报错 |

OpenAPI 给出的默认值：`{"type": "enabled", "keep": "all"}`。
⚠ 文档自相矛盾：模型参数参考写"显式设置时仅接受 `{"type":"enabled","keep":"all"}`"，而 OpenAPI 与思考模型指南写 `keep` 不传或 `null` 也合法（即 `{"type":"enabled"}` 应可通过）。最稳妥做法：**不传 `thinking`**。

**示例请求**（流式，与 K2.6 完全同构，仅换 `model`）：

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k2.7-code-highspeed",
    "messages": [
      {"role": "system", "content": "你是 Kimi。"},
      {"role": "user", "content": "用 Python 实现快速排序。"}
    ],
    "stream": true
  }'
```

```python
stream = client.chat.completions.create(
    model="kimi-k2.7-code",       # 或 "kimi-k2.7-code-highspeed"
    messages=[{"role": "system", "content": "你是 Kimi。"},
              {"role": "user", "content": "用 Python 实现快速排序。"}],
    max_tokens=1024 * 32,
    stream=True,
    # 不传 thinking、不传 temperature
)
# 消费方式同 §6
```

**注意事项**：
- 由于 Preserved Thinking 始终开启，多轮对话**必须**把每轮历史 assistant 消息的 `reasoning_content` 原样保留在 `messages` 中。
- 除 `thinking` 外，其余参数约束与 K2.6 一致。

## 10. Preserved Thinking：多轮与工具调用回传

**用途**：让模型在本轮推理时延续历史轮次的思考脉络；在多步工具调用中保证推理连贯。

**各模型行为**：

| 模型 | 跨轮保留历史 `reasoning_content` | 是否必须回传 |
|---|---|---|
| `kimi-k3` | 始终 | **必须**：多轮与工具调用都要原样回传完整 assistant message（含 `reasoning_content`、`tool_calls`） |
| `kimi-k2.7-code` | 始终 | **必须** |
| `kimi-k2.6` | 仅 `thinking.keep: "all"` | `keep: null` 时服务端忽略历史 `reasoning_content`；单轮工具循环内建议保留，不回传不报错但可能影响效果 |

**示例请求**（K2.6 显式开启；K3 / K2.7 去掉 `thinking` 即可）：

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k2.6",
    "messages": [
      {"role": "system", "content": "你是 Kimi。"},
      {"role": "user", "content": "第一个问题..."},
      {"role": "assistant",
       "reasoning_content": "<上一轮 API 返回的 reasoning_content>",
       "content": "<上一轮 API 返回的最终回答>"},
      {"role": "user", "content": "请基于之前的分析继续推导下一步。"}
    ],
    "thinking": {"type": "enabled", "keep": "all"}
  }'
```

```python
import json, os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")
MODEL = "kimi-k3"
tools = [{"type": "function", "function": {
    "name": "get_weather", "description": "查询城市天气",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
messages = [{"role": "user", "content": "北京今天天气怎么样？"}]

for _ in range(10):
    completion = client.chat.completions.create(model=MODEL, messages=messages, tools=tools)
    message = completion.choices[0].message
    # 关键：整条 message 原样 append（reasoning_content 是 extra 字段，SDK 对象和 model_dump() 都会带上）
    messages.append(message)
    if not message.tool_calls:
        print(message.content)
        break
    for tc in message.tool_calls:
        args = json.loads(tc.function.arguments)
        result = json.dumps({"city": args["city"], "weather": "晴"}, ensure_ascii=False)
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
```

**注意事项**：
- 不要"只保留 `content`"再回传：把 assistant 消息重新组装成 `{"role":"assistant","content":...}` 会丢掉 `reasoning_content`，对 K3 / K2.7 属于违反必须项。
- 官方示例两种写法都有：`messages.append(message)` 和 `messages.append(message.model_dump())`。
- `keep` 只影响历史轮，不改变当前轮是否思考（由 `type` / 模型决定）。
- 历史 `reasoning_content` 持续占用上下文并计费（§12）。

## 11. 固定采样参数与 `tool_choice` 约束

**用途**：三款模型都把采样参数锁死；传入非固定值直接报错（400 `invalid_request_error` 一类，具体 `error.code` ⚠ 文档未说明）。

| 参数 | K3 | K2.7 Code | K2.6 |
|---|---|---|---|
| `temperature` | `1.0` | `1.0` | 思考 `1.0` / 非思考 `0.6` |
| `top_p` | `0.95` | `0.95` | `0.95` |
| `n` | `1` | `1` | `1` |
| `presence_penalty` | `0` | `0` | `0` |
| `frequency_penalty` | `0` | `0` | `0` |

（模型参数参考页还有一条"`temperature` 接近 0 时 `n` 只能为 1"的说明，在 temperature 已固定的前提下已无实际意义。）

**`tool_choice`**：

| 取值 | K3 | K2.7 Code / K2.6 |
|---|---|---|
| `"auto"`（默认） | 支持 | 支持 |
| `"none"` | 支持 | 支持 |
| `"required"` | 支持 | **报错** |
| `{"type":"function","function":{"name":...}}` | 支持 | ⚠ 文档自相矛盾：模型参数参考只说"不支持 `required`"；K2.6 / K2.7 快速开始页说"只能用 auto 和 none，取任何其他值将会报错"（K2.6 页限定为思考模式下）。按后者处理，即也不要传指定函数对象。 |

**K3 `tool_choice: "required"` 示例**：

```python
first = client.chat.completions.create(
    model="kimi-k3", messages=messages, tools=tools, tool_choice="required",
)
messages.append(first.choices[0].message)   # 原样回传
# ... 追加 tool 结果后，第二次调用不再传 tool_choice="required"
```

**注意事项**：
- 工具 `function.parameters` 需符合 MFJS（Moonshot Flavored JSON Schema）；`function.strict` 默认 `true`。
- K3 额外支持在 `messages` 中插入 `{"role":"system","tools":[...]}`（无 `content`）动态加载工具，仅对后续对话生效，且每次请求都要携带。

## 12. 思考 token 计费与输出上限

- `reasoning_content` **计入 token 消耗**（输出侧），开启 Preserved Thinking 后历史思考也作为输入持续计费。
- `reasoning_content` + `content` 共同受输出上限约束。
- 输出上限字段：⚠ 文档自相矛盾——OpenAPI 标注 `max_tokens` "已弃用，请使用 `max_completion_tokens`"（K3 默认 131072，最大 1048576）；而 K2.6 / K2.7 快速开始与思考模型指南全部使用 `max_tokens`（默认 32768，建议 ≥ 16000）。K2.x 的 `max_completion_tokens` 默认值 ⚠ 文档未说明。稳妥做法：K3 用 `max_completion_tokens`，K2.x 沿用 `max_tokens`。
- 输入 + 输出上限超过上下文窗口 → `invalid_request_error`；达到上限 → `finish_reason: "length"`。
- 前缀缓存命中的 token 由 `usage.cached_tokens` 体现；K3 输入价格区分缓存命中 / 未命中。

## 13. 从 K2.6 / K2.7 迁移到 K3

| 改动项 | K2.6 → K3 | K2.7 Code → K3 |
|---|---|---|
| `model` | 改为 `"kimi-k3"` | 改为 `"kimi-k3"` |
| `thinking` | **删除**（含 `disabled` / `keep`） | 删除（若曾显式传） |
| 推理强度 | 按需加顶层 `reasoning_effort`（默认 `max`） | 同左 |
| 历史消息回传 | 从"可选 / 仅 `keep: all`"变为**必须**原样回传完整 assistant message | 已是必须，保持不变 |
| `tool_choice` | 可开始使用 `required` / 指定函数 | 同左 |
| 关闭思考的调用 | K3 无法关闭；低延迟场景改用 `reasoning_effort: "low"` 或留在 K2.6 | — |
| 输出上限 | `max_tokens` 32768 → K3 默认 131072（建议改用 `max_completion_tokens`） | 同左 |
| 上下文 | 256K → 1M；注意 K3 按统一单价计费、不按上下文分段 | 同左 |
| 账户 | 需累计充值 ≥ ¥10；代金券不可用 | 同左 |
| 缓存 | 会话中途切换 `reasoning_effort` 会打断前缀缓存 | 同左 |

已有 OpenAI 代码里的 `reasoning_effort` 无需改字段名，只需把取值收敛到 `low` / `high` / `max`。

## 14. 定价

材料中的定价总页只给出计费规则，**具体单价在 `/docs/pricing/chat-k3`、`/docs/pricing/chat-k27-code`、`/docs/pricing/chat-k26` 子页，本次输入材料未包含 → 单价 ⚠ 文档未说明**。可依据的规则：

- 计费单元为 token（中文约 1 token ≈ 1.5-2 汉字）；输入与输出均按量计费。
- K3：不按上下文长度分段；输入区分**缓存命中 / 未命中**两档，输出统一单价。
- 图片 / 视频按动态 token 计费（分辨率、关键帧数越高越贵）；Vision 按推理总 token 计费。
- `reasoning_content` 计费；Preserved Thinking 的历史思考按输入计费。
- 文件相关接口（内容抽取 / 存储）限时免费；抽取出的文档内容作为输入时照常计费。
- 2025-04-07 changelog 记录过一次"模型产品降价"（具体幅度 ⚠ 文档未说明）。

## 15. 账户等级与限速

按**累计充值金额**（代金券不计入）划分等级：

| 等级 | 累计充值 | 并发 | RPM | TPM | TPD |
|---|---|---|---|---|---|
| Tier0 | ¥0 | 1 | 3 | 500,000 | 1,500,000 |
| Tier1 | ¥50 | 15 | 100 | 2,000,000 | Unlimited |
| Tier2 | ¥100 | 40 | 100 | 3,000,000 | Unlimited |
| Tier3 | ¥500 | 50 | 200 | 3,000,000 | Unlimited |
| Tier4 | ¥5,000 | 60 | 200 | 4,000,000 | Unlimited |
| Tier5 | ¥20,000 | 100 | 300 | 5,000,000 | Unlimited |

- 并发 = 同一时间处理中的请求数；RPM / TPM / TPD = 每分钟请求数 / 每分钟 token 数 / 每天 token 数。
- 限速按账户维度，不按模型区分（是否有按模型的额外限制 ⚠ 文档未说明）。
- K3 解锁门槛 ¥10 低于 Tier1 门槛 ¥50：充值 ¥10-49 的账户按表仍是 Tier0（并发 1 / RPM 3），文档未单独说明这一区间。
- 集群负载达上限时可能临时限流；触发风控限速后无法解除。
- K3 页面提示"预备在 8 月更新充值等级与限速规则"，本表抓取于 2026-09-03，是否已是更新后版本 ⚠ 文档未说明。
- 超限的 HTTP 状态码 / `error.code` ⚠ 文档未说明（本次材料未含错误码页）。

## 16. 文档矛盾与未说明项汇总

- ⚠ 文档自相矛盾：K2.6 快速开始页 `thinking` 只列 enabled/disabled，其余三处含 `keep: "all"`（§8）。
- ⚠ 文档自相矛盾：K2.7 显式传 `{"type":"enabled"}`（无 keep）是否合法，模型参数参考 vs OpenAPI（§9）。
- ⚠ 文档自相矛盾：K2.x `tool_choice` 指定函数对象是否可用（§11）。
- ⚠ 文档自相矛盾：`max_tokens` 已弃用 vs 全部示例仍用 `max_tokens`（§12）。
- ⚠ 文档未说明：K3 传入 `thinking` 是否报错；`reasoning_effort` 传非法值是否报错；三款模型上线日期；K2.x 访问条件与代金券可用性；具体单价；限速错误码；充值 ¥10-49 区间的等级；8 月限速规则是否已更新。
