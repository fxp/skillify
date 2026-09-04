# 图片生成与视频生成 API（Seedream / Seedance）

本文件覆盖火山方舟的**图片生成**（`POST /images/generations`，Seedream 5.0 pro / 5.0 lite / 4.5 / 4.0）与**视频生成**（`/contents/generations/tasks` 异步任务四件套，Seedance 2.5 / 2.0 系列 / 1.5 pro / 1.0 系列）API，含参数表、响应结构、流式事件、模型能力对照、限制与错误、Agent Plan 入口差异，以及 3D 生成的索引。鉴权与 Base URL 见 `auth.md`；AFP 抵扣细则见 `agent-plan.md`。标 **已用真实 API 验证（2026-09-04，Agent Plan Medium）** 的结论均在 Agent Plan `/api/plan/v3` 入口实测；标准 `/api/v3` 预期相同但未测。

## 目录

1. [入口与 model 字段速查](#1-入口与-model-字段速查)
2. [图片生成](#2-图片生成)
   - 2.1 我想选模型：Seedream 各版本能力对照
   - 2.2 生成图片（文生图 / 图生图 / 多图融合 / 组图）
   - 2.3 `size` 规则（档位 vs 像素值）
   - 2.4 响应结构（非流式）
   - 2.5 流式输出与 SSE 事件
   - 2.6 Seedream 5.0 pro 专属：交互编辑、图层拆分、透明背景
   - 2.7 输入限制、URL 有效期、限流、内容审核错误
3. [视频生成](#3-视频生成)
   - 3.1 我想选模型：Seedance 各版本能力对照
   - 3.2 创建视频生成任务
   - 3.3 查询单个任务（轮询）
   - 3.4 查询任务列表
   - 3.5 取消或删除任务
   - 3.6 Seedance 2.5 任务类型与报错机制
   - 3.7 token 用量估算与计费口径
   - 3.8 输入限制、保存时间、限流、人像与版权 IP
4. [Agent Plan 入口下调用图片 / 视频](#4-agent-plan-入口下调用图片--视频)
5. [3D 生成（索引）](#5-3d-生成索引)
6. [来源页面](#来源页面)

---

## 1. 入口与 model 字段速查

| 入口 | 图片生成 | 视频生成 | model 字段 | Key 环境变量 |
|---|---|---|---|---|
| 标准 API `https://ark.cn-beijing.volces.com/api/v3` | `POST /images/generations` | `POST/GET/DELETE /contents/generations/tasks[/{id}]` | 带日期 Model ID（如 `doubao-seedream-5-0-pro-260628`、`doubao-seedance-2-5-260628`）或推理接入点 `ep-xxxx` | `ARK_API_KEY` |
| Agent Plan `https://ark.cn-beijing.volces.com/api/plan/v3` | 同路径（`doubao-seedream-5.0-lite` 已实测 200，见 §2.4） | 同路径（Small / Medium 套餐不支持视频：Medium 档 `doubao-seedance-2.0-mini` 已实测 404 `UnsupportedModel`，见 §4） | 小写 Model Name：`doubao-seedream-5.0-lite`、`doubao-seedance-2.0` / `-fast` / `-mini`、`doubao-seedance-1.5-pro`（即将下线） | `ARK_AGENT_PLAN_API_KEY` |
| Coding Plan `https://ark.cn-beijing.volces.com/api/coding/v3` | ⚠ 文档未说明（auth.md 的 Coding Plan 模型列表中无图片 / 视频模型，按不可用处理） | 同左 | — | — |

HTTP 头统一：`Authorization: Bearer <key>`、`Content-Type: application/json`。

---

## 2. 图片生成

### 2.1 我想选模型：Seedream 各版本能力对照

来源：图片生成教程 / Seedream 5.0 pro 教程「模型能力」表。

| 能力 | Seedream 5.0 pro | Seedream 5.0 lite | Seedream 4.5 | Seedream 4.0 |
|---|---|---|---|---|
| Model ID（标准入口） | `doubao-seedream-5-0-pro-260628` | `doubao-seedream-5-0-260128`（同时支持 `doubao-seedream-5-0-lite-260128`） | `doubao-seedream-4-5-251128` | `doubao-seedream-4-0-250828` |
| 文生图 / 单图生图 / 多图生图 | ✓ | ✓ | ✓ | ✓ |
| 文生组图 / 图生组图（`sequential_image_generation=auto`） | 暂不支持 | ✓ | ✓ | ✓ |
| 交互编辑（`<point>` / `<bbox>` 坐标、手绘标记） | ✓ | ✗ | ✗ | ✗ |
| 图层拆分（`layer_decomposition=true`） | ✓ | ✗ | ✗ | ✗ |
| 流式输出（`stream=true`） | 暂不支持 | ✓ | ✓ | ✓ |
| 联网搜索（`tools[].type=web_search`） | 暂不支持 | ✓ | ✗ | ✗ |
| 透明背景（`background=transparent`） | ✓ | ✗（文档只列 5.0 pro） | ✗ | ✗ |
| 分辨率档位 | `1K` `1.5K` `2K` | `2K` `3K` `4K` | `2K` `4K` | `1K` `2K` `4K` |
| `output_format` | png / jpeg | png / jpeg | 仅 jpeg（不可设） | 仅 jpeg（不可设） |
| `optimize_prompt_options.mode` | standard / fast | 仅 standard | 仅 standard | standard / fast |
| 参考图上限 | 10 张 | 14 张 | 14 张 | 14 张 |
| 生成数量 | 单图；或 1 底图 + 最多 16 图层 | 参考图数 + 生成数 ≤ 15 | 同左 | 同左 |
| 限流 IPM（张 / 分钟） | 500 | 500 | 500 | 500 |
| 提示词语言 | 中英 + 俄 / 阿 / 菲 / 泰 / 土 / 韩 / 马 / 西 / 葡 / 印尼 / 法 / 德 / 越 / 日 | 中英 | 中英 | 中英 |

选型口径：要精准局部编辑、拆图层、透明底 → 5.0 pro；要一次出多张关联图（故事板、四季变体）、流式、联网时效性 → 5.0 lite；4.5 / 4.0 为旧版本，参数集是 5.0 lite 的子集。

### 2.2 生成图片（文生图 / 图生图 / 多图融合 / 组图）

**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/v3/images/generations`（Agent Plan：`/api/plan/v3/images/generations`）

**用途**: 同步接口，一次请求返回 1 张或一组图片。文生图、图生图、多图融合、组图、图层拆分全部走这一个 endpoint，靠 `image` / `sequential_image_generation` / `layer_decomposition` 区分场景。

**关键参数**（Body，字段名与 1541523 一致）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | — | Model ID 或 Endpoint ID（标准入口）；Agent Plan 填 `doubao-seedream-5.0-lite` |
| `prompt` | string | 图片生成场景必选；图层拆分场景可选 | — | 建议中文 ≤ 300 字 / 英文 ≤ 600 词。5.0 pro 交互编辑在此处写 `<point>x y</point>` / `<bbox>x1 y1 x2 y2</bbox>`（归一化 0–999） |
| `image` | string / string[] | 图生图可选；图层拆分必选 | — | 单张传字符串，多张传数组。每个元素为公网 URL 或 `data:image/<小写格式>;base64,<...>`。多图时 prompt 里用「图1」「图2」按数组顺序引用。5.0 pro ≤ 10 张，其余 ≤ 14 张；图层拆分仅 1 张 |
| `size` | string | 否 | 按模型不同（见 §2.3） | 档位（`1K`/`1.5K`/`2K`/`3K`/`4K`/`auto`）或像素 `宽x高`，两种方式不可混用。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：5.0 lite 传 `"1K"` → 400 `size must be one of 'WIDTHxHEIGHT', '2k', '3k', or '4k'`；传小写 `"2k"` → 200，`data[0].size: "2048x2048"`（服务端枚举写的是小写，大写 `2K` 未测） |
| `response_format` | string | 否 | `url` | `url`（24 小时内有效；实测为 TOS 签名链接，query 带 `X-Tos-Expires=86400`）/ `b64_json` |
| `output_format` | string | 否 | `jpeg` | `png` / `jpeg`。仅 5.0 pro / 5.0 lite 可设；图层拆分下只控制底图，图层固定 png |
| `watermark` | boolean | 否 | `true` | `true` 右下角加「AI 生成」水印。注意默认开，生产通常显式传 `false` |
| `sequential_image_generation` | string | 否 | `disabled` | `auto`：模型自行决定返回组图及张数；`disabled`：只出 1 张。5.0 pro 不支持 |
| `sequential_image_generation_options.max_images` | integer | 否 | `15` | 取值 `[1, 15]`；仅 `auto` 时生效。实际张数还受「参考图数 + 生成数 ≤ 15」约束 |
| `stream` | boolean | 否 | `false` | `true` 走 SSE，每张图生成完即推送（§2.5）。5.0 pro 不支持 |
| `optimize_prompt_options.mode` | string | 否 | `standard` | `standard` 质量高耗时长；`fast` 更快、效果略低。5.0 lite / 4.5 不支持 fast |
| `tools[].type` | string | 否 | — | 目前仅 `web_search`；仅 5.0 lite 支持。是否搜索由模型自判，次数在 `usage.tool_usage.web_search` |
| `layer_decomposition` | boolean | 否 | `false` | `true` 进入图层拆分模式（§2.6）。仅 5.0 pro |
| `background` | string | 否 | `opaque` | `transparent` / `opaque`。仅 5.0 pro；仅图生图且只能输入 1 张带透明通道的图；与 `output_format=jpeg` 互斥（文档原文：将触发报错，未实测） |
| `seed` | — | — | — | ⚠ 文档未说明：1541523 参数表中**没有** `seed` 字段（视频 API 才有）。不要在图片请求里传，是否被忽略或报错待实测 |
| `guidance_scale` | — | — | — | ⚠ 文档未说明：1541523 参数表中没有该字段，同上 |

**示例请求**

curl（5.0 lite，多图融合 → 单图，自定义像素）：

```bash
curl https://ark.cn-beijing.volces.com/api/v3/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedream-5-0-lite-260128",
    "prompt": "将图1的人物穿上图2的服装，保持人物面部特征，电影感光线",
    "image": [
      "https://example.com/person.png",
      "https://example.com/outfit.png"
    ],
    "size": "2048x2048",
    "sequential_image_generation": "disabled",
    "response_format": "url",
    "output_format": "png",
    "watermark": false
  }'
```

Python（`openai` SDK；方舟特有参数放 `extra_body`，与 2375486 的 OpenAI 页签写法一致）：

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key=os.environ["ARK_API_KEY"],
)

# 文生组图：一次最多 4 张关联图
resp = client.images.generate(
    model="doubao-seedream-5-0-lite-260128",
    prompt="生成一组共4张连贯插画，宽高比3:2，同一庭院一角的四季变迁，统一风格",
    size="2K",
    response_format="url",
    extra_body={
        "sequential_image_generation": "auto",
        "sequential_image_generation_options": {"max_images": 4},
        "output_format": "png",
        "watermark": False,
    },
)
for i, item in enumerate(resp.data):
    # 组图中单张失败时该元素带 error，其余不受影响
    err = getattr(item, "error", None)
    print(i, item.url if item.url else err)
print(resp.usage)  # generated_images / output_tokens / total_tokens
```

官方 SDK 等价写法：`from volcenginesdkarkruntime import Ark; Ark(base_url=..., api_key=...).images.generate(model=..., prompt=..., image=..., size=..., sequential_image_generation="auto", sequential_image_generation_options={"max_images": 4}, stream=False, watermark=False)`，底层同一 endpoint。

**示例响应**（非流式，见 §2.4）

**注意事项**

- `size` 两种方式不可混用：传 `2K` 就在 prompt 里用自然语言说宽高比；传 `2048x1024` 则必须同时满足总像素区间与宽高比 `[1/16, 16]`（§2.3）。
- 组图里「输入参考图数 + 最终生成数 ≤ 15」是硬约束，`max_images=15` 配 2 张参考图最多只会出 13 张。
- 组图中某张审核不通过：继续生成其余图片，失败那张在 `data[i].error` 里；某张 500 内部错误：不再继续后续图片（文档原文，未实测）。
- 图片 URL 只保留 24 小时，务必转存；文档推荐配置 TOS 数据订阅自动转存。
- `watermark` 默认 `true`，与视频 API（默认 `false`）相反。

### 2.3 `size` 规则（档位 vs 像素值）

| 模型 | 方式 1：档位（在 prompt 里描述宽高比） | 方式 2：`宽x高` 像素 | 默认值 |
|---|---|---|---|
| 5.0 pro（图片生成） | `1K` / `1.5K` / `2K`；文档注：`1.5K` 与 `1K` 价格相同且效果更好 | 总像素 `[1280x720=921600, 2048x2048x1.1025=4624220]`，宽高比 `[1/16, 16]` | `2K` |
| 5.0 pro（图层拆分） | `1K` / `1.5K` / `2K` / `auto`（按输入图尺寸：<1K 按 1K 出，>2K 按 2K 出，区间内按原尺寸） | 不支持像素值 | `auto` |
| 5.0 lite | `2K` / `3K` / `4K` | 总像素 `[2560x1440=3686400, 4096x4096=16777216]`，宽高比 `[1/16, 16]` | `2048x2048` |
| 4.5 | `2K` / `4K` | 同 5.0 lite | `2048x2048` |
| 4.0 | `1K` / `2K` / `4K` | 总像素 `[921600, 16777216]`，宽高比 `[1/16, 16]` | `2048x2048` |

档位 → 像素的常见映射（5.0 pro `2K`：1:1 `2048x2048`、16:9 `2816x1584`、9:16 `1584x2816`、21:9 `3136x1344`；5.0 lite `4K`：1:1 `4096x4096`、16:9 `5504x3040`），完整表见 1541523。文档给的正反例：5.0 pro `2048x1024` 有效、`512x512` 无效（低于 921600）；5.0 lite `3750x1250` 有效、`1500x1500` 无效（低于 3686400）。

**已用真实 API 验证（2026-09-04，Agent Plan Medium）**（`POST /api/plan/v3/images/generations`）：`doubao-seedream-5.0-lite` + `size: "1K"` → HTTP 400，原文 ``{"error":{"code":"InvalidParameter","message":"The parameter `size` specified in the request is not valid: size must be one of 'WIDTHxHEIGHT', '2k', '3k', or '4k'. Request id: ...","param":"","type":""}}`` —— 5.0 lite 只认 `2k` / `3k` / `4k`（服务端文案为小写）与 `WIDTHxHEIGHT`，与上表一致，注意 `type` 为空串；`size: "2k"` → 200，`data[0].size: "2048x2048"`。大写 `2K` 未测，若报错改小写。标准入口预期相同但未测。

⚠ 文档自相矛盾：4.0 模型 `1K` 档 16:9 的映射值，1541523 写 `1280x720` / 21:9 `1512x648`，1824121 写 `1312x736` / 21:9 `1568x672`。以实际返回的 `data[].size` 为准。

### 2.4 响应结构（非流式）

**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`POST /api/plan/v3/images/generations`，body `{"model":"doubao-seedream-5.0-lite","prompt":"a red circle on white background, minimal","size":"2k","response_format":"url","watermark":false}` → HTTP 200，原始响应（仅省略签名串）：

```json
{
  "model": "doubao-seedream-5.0-lite",
  "created": 1788487585,
  "data": [
    {
      "url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/doubao-seedream-5-0/021788487573482…_0.jpeg?X-Tos-Algorithm=TOS4-HMAC-SHA256&X-Tos-Credential=…&X-Tos-Date=20260904T020625Z&X-Tos-Expires=86400&X-Tos-Signature=…&X-Tos-SignedHeaders=host",
      "size": "2048x2048"
    }
  ],
  "usage": {"generated_images": 1, "output_tokens": 16384, "total_tokens": 16384}
}
```

实测要点：Plan 入口 `model` 回显 Model Name `doubao-seedream-5.0-lite`（不是带日期版本）；未传 `output_format` 时产物为 `.jpeg`，且 `data[0]` 里没有 `output_format` 字段（文档说该字段 5.0 pro 返回）；`X-Tos-Expires=86400` 即 24 h；`output_tokens = 2048 × 2048 / 256 = 16384`，与文档公式一致；这一张 2k 图抵扣 99 AFP。下面是文档另外定义、本次未触发的字段（文档原文，未实测）：

```json
{
  "data": [
    {"url": "https://...", "size": "2048x2048", "output_format": "png"},
    {"error": {"code": "OutputImageSensitiveContentDetected",
               "message": "The request failed because the output image may contain sensitive information."}}
  ],
  "tools": [{"type": "web_search"}],
  "usage": {"generated_images": 1, "output_tokens": 16384, "total_tokens": 16384, "tool_usage": {"web_search": 1}}
}
```

| 字段 | 说明 |
|---|---|
| `created` | Unix 秒 |
| `model` | `模型名称-版本` |
| `data[]` | 每张图一个对象。公共字段 `url`（`response_format=url` 时）/ `b64_json`（`b64_json` 时）/ `size`（`宽x高`）/ `output_format`（5.0 pro 返回） |
| `data[].error.code/message` | 组图场景单张失败时返回（5.0 lite / 4.5 / 4.0） |
| `data[].z_index` / `name` / `description` / `bounding_box.absolute` / `bounding_box.normalized` | 图层拆分场景返回，见 §2.6 |
| `error.code/message` | 顶层错误，整个请求没出任何图时返回 |
| `tools[]` | 实际被调用的工具（仅 5.0 lite） |
| `usage.generated_images` | 成功张数，仅对成功图计费 |
| `usage.input_images` | 输入图片张数（仅 5.0 pro 返回） |
| `usage.output_tokens` | `sum(图片长 × 图片宽) / 256` 取整 |
| `usage.total_tokens` | 当前不计输入 token，等于 `output_tokens` |
| `usage.tool_usage.web_search` | 联网搜索次数（开启时返回，0 表示没搜） |

### 2.5 流式输出与 SSE 事件

`stream: true`（5.0 lite / 4.5 / 4.0）时以 SSE 推送，单图与组图均生效。事件类型（1824137）：

| 事件 `type` | 何时 | 关键字段 |
|---|---|---|
| `image_generation.partial_succeeded` | 某张图生成成功 | `image_index`（从 0 起）、`url` 或 `b64_json`、`size`、`created`、`model` |
| `image_generation.partial_failed` | 某张图失败 | `image_index`、`error.code`、`error.message` |
| `image_generation.completed` | 全部结束 | `usage`（同非流式）、`tools` |
| `error` | 请求整体失败（缺参数、鉴权失败等） | `error.error.code` / `error.error.message`（注意多一层 `error`） |

⚠ 文档自相矛盾：1824121 的 Python 流式示例还处理了 `image_generation.partial_image` 事件（字段 `partial_image_index`、`b64_json`），但 1824137 事件列表中没有该事件。是否真实存在待实测。

curl：

```bash
curl -N https://ark.cn-beijing.volces.com/api/v3/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedream-5-0-lite-260128",
    "prompt": "参考图1，生成四张图片，人物分别戴墨镜、骑摩托、戴帽子、拿棒棒糖",
    "image": "https://example.com/person.png",
    "sequential_image_generation": "auto",
    "sequential_image_generation_options": {"max_images": 4},
    "size": "2K",
    "stream": true,
    "output_format": "png",
    "watermark": false
  }'
```

Python（`requests` 手动解析 SSE，不依赖 SDK 对事件的封装）：

```python
import os, json, requests

url = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
headers = {"Authorization": f"Bearer {os.environ['ARK_API_KEY']}",
           "Content-Type": "application/json"}
body = {
    "model": "doubao-seedream-5-0-lite-260128",
    "prompt": "参考图1，生成四张图片，人物分别戴墨镜、骑摩托、戴帽子、拿棒棒糖",
    "image": "https://example.com/person.png",
    "sequential_image_generation": "auto",
    "sequential_image_generation_options": {"max_images": 4},
    "size": "2K", "stream": True, "output_format": "png", "watermark": False,
}
with requests.post(url, headers=headers, json=body, stream=True, timeout=600) as r:
    r.raise_for_status()
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":          # ⚠ 是否有 [DONE] 结束标记文档未说明，此处兼容处理
            break
        ev = json.loads(payload)
        t = ev.get("type")
        if t == "image_generation.partial_succeeded":
            print("ok", ev["image_index"], ev.get("url"), ev.get("size"))
        elif t == "image_generation.partial_failed":
            print("fail", ev["image_index"], ev["error"]["code"])
        elif t == "image_generation.completed":
            print("usage", ev["usage"])
        elif "error" in ev:
            print("request error", ev["error"])
```

### 2.6 Seedream 5.0 pro 专属：交互编辑、图层拆分、透明背景

**交互编辑（同一 endpoint，靠 prompt 携带位置信息）**

两种定位方式（2582774）：

1. 任意标记 + 自然语言：在待编辑图上手绘框 / 涂鸦，prompt 直接说「在蓝色框内添加一个电视机」。
2. 坐标精准定位：前端把点选 / 框选换算成**归一化坐标（0–999，左上 `0,0`，右下 `999,999`）**写进 prompt：
   - 点：`<point>x y</point>`，`x = round(x_px / width * 1000)`，`y` 同理（`width/height` 为图片展示宽高）。
   - 框：`<bbox>x1 y1 x2 y2</bbox>`（左上 + 右下）。
   - 多图用「图1」「图2」对应 `image` 数组顺序。

| 场景 | prompt 写法 |
|---|---|
| 编辑点附近对象 | `把图1<point>520 460</point>位置换成皇冠` |
| 编辑区域 | `把图1<bbox>120 180 640 760</bbox>区域替换成花园` |
| 跨图放置 | `将图1<bbox>179 283 796 986</bbox>的主体放到图2<bbox>118 331 933 871</bbox>位置` |
| 框内多主体时指明对象 | `把图1<bbox>120 180 640 760</bbox>区域内的左侧人物换成机器人` |
| 标注保持不变区域 | `...替换成花园，图1<bbox>700 120 920 360</bbox>区域保持不变` |

多轮编辑：接口本身无会话状态，「多轮」= 把上一轮返回的 `data[0].url`（24 小时内有效，或 `b64_json`）作为下一轮的 `image` 再次调用；文档示例即用拆分出的图层 URL 作为输入再编辑（「将图片中的鹦鹉改为孔雀」）。

```python
# 交互编辑：官方后端示例改写为 openai SDK，Key 从环境变量读
resp = client.images.generate(
    model="doubao-seedream-5-0-pro-260628",
    prompt="将图1<bbox>179 283 796 986</bbox>的主体放到图2<bbox>118 331 933 871</bbox>位置",
    size="2K",
    response_format="url",
    extra_body={"image": ["https://example.com/a.png", "https://example.com/b.png"],
                "output_format": "png", "watermark": False},
)
edited_url = resp.data[0].url   # 下一轮编辑时作为 image 传入
```

（`image` 是否能作为 `openai` SDK 顶层参数传入 ⚠ 未实测；放 `extra_body` 最稳。）

**图层拆分（`layer_decomposition: true`）**

- `image` 必选且只能 1 张（png / jpeg，总像素 `[512x512, 6000x6000]`，≤ 30 MB）；`prompt` 可选：不传 → 自动拆所有主要元素；自然语言指定 → 「拆出人物、标题文字和右下角装饰图标」；精准 → `<bbox>` 列表。
- 输出 1 张底图 + 最多 16 个带透明通道的 PNG 图层；任一图层失败则整体报错，不支持部分成功（文档原文，未实测）。
- `size` 只能用档位（`1K`/`1.5K`/`2K`/`auto`，默认 `auto`）；`output_format` 只影响底图。
- 每次请求预扣 17 IPM，生成完按实际张数返还。
- 响应 `data[]`：底图 `z_index=0` 且无 `bounding_box`；图层 `z_index` 从 1 递增（越大越上层），带 `name`、`description`、`bounding_box.absolute=[left, top, right, bottom]`（输出底图像素坐标）与 `bounding_box.normalized`（0–1000 整数）。还原：图层缩放到 `(right-left) x (bottom-top)`，放到 `(left, top)`，按 `z_index` 由小到大叠放；自定义画布用 normalized 乘以画布宽高再除以 1000。
- `usage` 额外含 `input_images`。

```bash
curl https://ark.cn-beijing.volces.com/api/v3/images/generations \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{"model":"doubao-seedream-5-0-pro-260628","layer_decomposition":true,
       "image":"https://example.com/poster.png","size":"auto",
       "output_format":"png","watermark":false}'
```

**透明背景（`background: transparent`）**：仅图生图、只能输入 1 张带透明通道的图；输出默认 png，若同时传 `output_format=jpeg` 或输入 jpeg 会报错（文档原文，未实测）。

### 2.7 输入限制、URL 有效期、限流、内容审核错误

**输入图片约束**

| 约束 | 图片生成场景 | 图层拆分场景 |
|---|---|---|
| 格式 | jpeg、png、webp、bmp、tiff、gif、heic、heif | png、jpeg |
| 总像素（宽 × 高） | `[196, 6000×6000=3600万]` | `[512×512=262144, 3600万]` |
| 单边像素 | > 14 | — |
| 宽高比 | `[1/16, 16]` | `[1/16, 16]` |
| 大小 | ≤ 30 MB | ≤ 30 MB |
| 张数 | 5.0 pro ≤ 10；5.0 lite / 4.5 / 4.0 ≤ 14 | 1 |

- 图片 URL 保留 24 小时后自动清除（实测 URL 为 TOS 签名链接，`X-Tos-Expires=86400`，与 24 h 一致）。
- 限流：IPM（每分钟生成张数，区分模型版本）超限即报错；各模型 500 IPM。
- 内容审核相关错误码（错误码页 1299023，均为 HTTP 400 `BadRequest`，文档原文，未实测）：`InputTextSensitiveContentDetected`、`InputImageSensitiveContentDetected`、`OutputImageSensitiveContentDetected`、`InputImageSensitiveContentDetected.PrivacyInformation`（输入图含真人）、`InputImageSensitiveContentDetected.PolicyViolation`（版权限制）、`OutputImageSensitiveContentDetected.DeepFake`（伪造证件）、`InputImageRiskDetection` / `OutputImageRiskDetection`（风险识别产品拦截）。组图下这些错误出现在 `data[i].error`，单图下出现在顶层 `error`。
- 缺必填参数等整体失败：`BadRequest` + `The request failed because it is missing one or multiple required parameters.`（文档原文，未实测）。

---

## 3. 视频生成

### 3.1 我想选模型：Seedance 各版本能力对照

来源：视频生成教程「模型能力」表 + 创建任务 API 各参数「模型支持」+ Seedance 2.5 / 2.0 教程。

| 能力 | 2.5 | 2.0 | 2.0 fast | 2.0 mini | 1.5 pro | 1.0 pro | 1.0 pro fast |
|---|---|---|---|---|---|---|---|
| Model ID | `doubao-seedance-2-5-260628` | `doubao-seedance-2-0-260128` | `doubao-seedance-2-0-fast-260128` | `doubao-seedance-2-0-mini-260615` | `doubao-seedance-1-5-pro-251215` | `doubao-seedance-1-0-pro-250528` | `doubao-seedance-1-0-pro-fast-251015` |
| 文生视频 / 首帧 | ✓ / ✓ | ✓ / ✓ | ✓ / ✓ | ✓ / ✓ | ✓ / ✓ | ✓ / ✓ | ✓ / ✓ |
| 首尾帧 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| 全模态参考（图 / 视频 / 组合） | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| 仅音频输入 | ✓ | ✗（需配图 / 视频） | ✗ | ✗ | ✗ | ✗ | ✗ |
| 参考素材上限 | 30 图 + 10 视频 + 10 音频 | 9 图 + 3 视频 + 3 音频 | 同 2.0 | 同 2.0 | — | — | — |
| 编辑视频 / 延长视频 | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| 有声视频 `generate_audio` | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ |
| 联网搜索 `tools` | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| 样片模式 `draft` | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| 返回尾帧 `return_last_frame` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `resolution` 可选（默认） | 480p / 720p / 1080p(10bit)（720p） | 480p / 720p / 1080p / 4k(10bit)（720p） | 480p / 720p（720p） | 480p / 720p（720p） | 480p / 720p / 1080p（720p） | 480p / 720p / 1080p（1080p） | 480p / 720p / 1080p（1080p） |
| `ratio` | 6 种 + adaptive（默认 adaptive） | 同左 | 同左 | 同左 | 同左 | 6 种 + adaptive；文生视频默认 16:9 且不支持 adaptive | 同 1.0 pro |
| `duration` 秒 | `[4, 30]` 或 `-1`（默认 -1） | `[4, 15]` 或 `-1` | 同 2.0 | 同 2.0 | `[4, 12]` 或 `-1` | `[2, 12]` | `[2, 12]` |
| `frames` | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ `[29, 289]` | ✓ |
| `seed` / `camera_fixed` | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ |
| `output_format` | mp4 / mov | mp4 | mp4 | mp4 | mp4 | mp4 | mp4 |
| `service_tier=flex` 离线推理 | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ |
| `priority` | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| `omni_reference_task_type` | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| 输出帧率 | 24 fps（所有模型） | | | | | | |
| 提示词语言 | 中英 + 西 / 印尼 / 葡 / 日 / 马 / 泰 / 阿 / 越 / 韩 | 中英 + 西 / 印尼 / 葡 / 日 | 同 2.0 | 同 2.0 | 中英 | 中英 | 中英 |

⚠ 文档自相矛盾：`seed` 参数的「模型支持」只列 1.5 pro / 1.0 系列，但 2298881 的 Seedance 2.5 查询响应示例里返回了 `"seed": 58944`，且 1520757 顶部又说 seed 的 `--` 传参「所有模型均兼容」。2.x 是否接受请求中的 `seed` 待实测。

开通条件（1520757）：开通 Seedance 2.5 / 2.0 系列需满足账户余额 > 200 元、或购买 200 元档以上节省计划、或持有对应资源包之一。

### 3.2 创建视频生成任务

**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks`（Agent Plan：`/api/plan/v3/...`）

**用途**: 异步提交任务，立即返回任务 `id`（`cgt-` 开头），之后用 §3.3 轮询或 `callback_url` 收结果。文生 / 图生 / 全模态参考 / 编辑 / 延长 / 样片全部走此接口。

**关键参数**（Body）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | — | Model ID / Endpoint ID；Agent Plan 填 `doubao-seedance-2.0` 等 |
| `content[]` | object[] | 是 | — | 输入元素数组，见下表。组合：纯文本；文本(可选)+图片；+视频；+音频（仅 2.5 可只传音频）；+图片+音频；+图片+视频；+视频+音频；+图片+视频+音频；或 `draft_task` |
| `omni_reference_task_type` | string | 否 | `auto` | 仅 2.5。`auto` / `reference` / `edit` / `extend`，见 §3.6 |
| `resolution` | string | 否 | 按模型 | `480p` / `720p` / `1080p` / `4k`，取值范围见 §3.1 |
| `ratio` | string | 否 | `adaptive`（1.0 系列文生视频 `16:9`） | `16:9` `4:3` `1:1` `3:4` `9:16` `21:9` `adaptive`。2.5 的首帧 / 首尾帧 / 编辑 / 延长任务**只能** `adaptive` |
| `duration` | integer | 否 | 2.5 为 `-1`；其他 ⚠ 文档未说明 | 秒。`-1` = 模型在范围内自选整数秒；2.5 编辑任务只能 `-1`（输出与待编辑视频等长，可能非整数秒、误差约 0.4 s）。与 `frames` 二选一，`frames` 优先 |
| `frames` | integer | 否 | — | 仅 1.0 系列。`[29, 289]` 且满足 `25 + 4n`；帧数 = 时长 × 24 |
| `generate_audio` | boolean | 否 | `true` | 是否生成同步音频（人声 / 音效 / BGM，单声道）。对话建议放双引号内。仅 2.5 / 2.0 系列 / 1.5 pro |
| `watermark` | boolean | 否 | `false` | `true` 右下角「AI 生成」水印 |
| `output_format` | string | 否 | `mp4` | `mp4` / `mov`（H.264 + yuv444p + PCM，专业后期用，部分播放器不兼容）。仅 2.5 |
| `seed` | integer | 否 | `-1` | `[-1, 2147483647]`，`-1` 随机；相同 seed 结果类似但不保证一致。文档列支持：1.5 pro / 1.0 系列（见 §3.1 ⚠） |
| `camera_fixed` | boolean | 否 | `false` | 固定镜头（平台在 prompt 后追加，效果不保证）。1.5 pro / 1.0 系列；参考图场景不支持 |
| `return_last_frame` | boolean | 否 | `false` | `true` 时查询接口返回 `content.last_frame_url`（png，无水印，与视频同尺寸），用于「上一段尾帧 → 下一段首帧」串接长视频 |
| `draft` | boolean | 否 | `false` | 样片模式，仅 1.5 pro；强制 480p（其他分辨率报错）、不支持尾帧、不支持 flex；token 用量 = 正常 × 折算系数（有声 0.6 / 无声 0.7） |
| `service_tier` | string | 否 | `default` | `default` 在线；`flex` 离线（TPD 配额更高，价格为在线 50%，2.5 / 2.0 系列不支持）。提交后不可改 |
| `callback_url` | string | 否 | — | 状态变化时 POST 与查询接口同结构的 JSON；`succeeded` / `failed` 若 5 秒内未送达重试 3 次 |
| `execution_expires_after` | integer | 否 | `172800` | `[3600, 259200]` 秒，从 `created_at` 起算，超时任务标 `expired` |
| `priority` | integer | 否 | `0` | `[0, 9]`，数值大先执行，同 Endpoint 内有效，不打断 running；flex 不支持。仅 2.5 / 2.0 系列 |
| `safety_identifier` | string | 否 | — | 终端用户唯一标识（≤ 64 字符，建议哈希） |
| `tools[].type` | string | 否 | — | `web_search`（2.5 / 2.0 系列）；2291680 注明「联网搜索能力仅适用于纯文本输入」 |

`content[]` 元素：

| `type` | 对象字段 | `role` | 说明 |
|---|---|---|---|
| `text` | `text` | — | 提示词，中文 ≤ 500 字 / 英文 ≤ 1000 词。全模态参考时用「图片1」「视频1」「音频1」或 `@视频1` / `@image1` 按顺序引用素材 |
| `image_url` | `image_url.url` | `first_frame`（首帧，1 张时可不填）/ `last_frame`（尾帧，首尾帧时两张都必须填 role）/ `reference_image`（参考图，2.5 / 2.0 必填） | `url` 为公网 URL、`data:image/<小写格式>;base64,...` 或素材 ID `asset://<ASSET_ID>` |
| `video_url` | `video_url.url` | `reference_video`（固定） | 公网 URL 或 `asset://`；不支持 Base64。仅 2.5 / 2.0 系列 |
| `audio_url` | `audio_url.url` | `reference_audio`（固定） | 公网 URL、`data:audio/<格式>;base64,...` 或 `asset://`。2.0 系列不可只传音频 |
| `draft_task` | `draft_task.id` | — | 仅 1.5 pro。基于样片任务 ID 生成正式视频，自动复用 model / text / image_url / generate_audio / seed / ratio / duration / camera_fixed，其他参数可重设 |

三种图片场景（首帧、首尾帧、全模态参考）**互斥不可混用**；全模态参考可在 prompt 里说「首帧为图片1」间接实现首尾帧，但要严格一致优先用 `first_frame` / `last_frame`。

**两种传参方式**：推荐在 body 顶层传字段（强校验，错了立即报错）。旧方式是在 prompt 末尾追加 `--参数`（弱校验，错了忽略或报错），文档示例：`小猫对着镜头打哈欠 --rs 720p --rt 16:9 --dur 5 --seed 11 --cf false --wm true`，文档称 `resolution` / `ratio` / `duration` / `frames` / `seed` / `camera_fixed` / `watermark` 均支持此方式且所有模型兼容。⚠ 文档未说明：`frames` 的缩写、以及是否存在 `--fps` / `--camerafixed` 这类写法（文档只出现 `--cf`）。同名参数两处都传时谁优先 ⚠ 文档未说明。

**示例请求**

curl（Seedance 2.5，首尾帧 + 有声）：

```bash
curl -X POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-2-5-260628",
    "content": [
      {"type": "text", "text": "女孩抱着狐狸缓缓睁眼看向镜头，镜头拉出，风声。她轻声说：\"别怕。\""},
      {"type": "image_url", "image_url": {"url": "https://example.com/first.png"}, "role": "first_frame"},
      {"type": "image_url", "image_url": {"url": "https://example.com/last.png"},  "role": "last_frame"}
    ],
    "resolution": "720p",
    "ratio": "adaptive",
    "duration": 5,
    "generate_audio": true,
    "watermark": false,
    "return_last_frame": true
  }'
```

Python（`requests`；全模态参考 + 视频编辑，2.5）：

```python
import os, requests

BASE = "https://ark.cn-beijing.volces.com/api/v3"
H = {"Authorization": f"Bearer {os.environ['ARK_API_KEY']}", "Content-Type": "application/json"}

body = {
    "model": "doubao-seedance-2-5-260628",
    "content": [
        {"type": "text", "text": "视频编辑：删除 @视频1 中的所有人，除了主角。"},
        {"type": "video_url", "video_url": {"url": "https://example.com/clip.mov"}, "role": "reference_video"},
    ],
    "omni_reference_task_type": "edit",   # 编辑任务：提前同步校验 ratio/duration 限制
    "ratio": "adaptive", "duration": -1,  # 编辑任务只能这么配
    "generate_audio": True, "output_format": "mov",
}
r = requests.post(f"{BASE}/contents/generations/tasks", headers=H, json=body, timeout=60)
r.raise_for_status()
task_id = r.json()["id"]          # 例如 "cgt-2026****"
```

官方 SDK：`Ark(...).content_generation.tasks.create(model=..., content=[...], ratio=..., duration=..., generate_audio=True, ...)`，底层同一 endpoint。

**示例响应**

```json
{"id": "cgt-2026****"}
```

任务 ID 保存 7 天（从 `created_at` 起），过期自动清除。

**注意事项**

- 2.5 / 2.0 系列**不接受含真人人脸的参考图 / 视频**（错误码 `InputImageSensitiveContentDetected.PrivacyInformation` / `InputVideoSensitiveContentDetected.PrivacyInformation`，文档原文，未实测）；解法见 §3.8。
- 首尾帧宽高比不一致时以首帧为准，尾帧自动裁剪；图生视频 `ratio` 与图片不一致时**居中裁剪**（规则见 2298881「图片裁剪规则」），建议 ratio 尽量贴近原图。
- 2.5 的 1080p 与 2.0 的 4k 为 10bit + H.265/HEVC，部分播放器不兼容。
- 请求体 ≤ 64 MB，大文件不要用 Base64。
- `generate_audio` 默认 `true`，且有声视频与无声视频价格不同（1.5 pro 按此区分定价）。

### 3.3 查询单个任务（轮询）

**Endpoint**: `GET https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{id}`

**用途**: 查任务状态与产物。只能查最近 7 天（`[T-7天, T)`）；账号维度 QPS 上限 20。

**响应字段**

| 字段 | 说明 |
|---|---|
| `id` / `model` | 任务 ID / `模型名称-版本` |
| `status` | `queued` 排队 → `running` → `succeeded` / `failed`；`cancelled`（仅 queued 可取消，24 h 后自动删除）。⚠ 文档自相矛盾：查询接口枚举未列 `expired`，但 `callback_url` 说明、`execution_expires_after` 说明与 DELETE 接口状态表都有 `expired`；按可能出现处理 |
| `content.video_url` | 成功后的视频 URL，**24 小时有效**；Seedance 2.5 产物 URL 下载次数上限 100 次 |
| `content.last_frame_url` | `return_last_frame=true` 时返回，同样 24 h / 100 次 |
| `usage.completion_tokens` | 生成视频消耗 token，计费对账依据。2.0 系列有最低 token 用量，实际 < 最低时按最低返回并计费 |
| `usage.total_tokens` | 视频模型不统计输入 token，等于 `completion_tokens` |
| `usage.tool_usage.web_search` | 联网搜索次数 |
| `error.code` / `error.message` | 失败时返回，成功为 `null`。2.5 部分任务类型要排到被消费时才报错（§3.6） |
| `duration` 或 `frames` | 二者只返回一个：创建时传了 `frames` 返 `frames`，否则返 `duration`。`duration` = 实际总帧数 / 24 向下取整，可能与真实时长不同（133 帧 → 5） |
| `framespersecond` | 帧率（24） |
| `resolution` / `ratio` / `seed` / `generate_audio` / `output_format`（2.5）/ `service_tier` / `safety_identifier` / `draft` / `draft_task_id` / `tools[]` | 回显实际生效值 |
| `created_at` / `updated_at` / `execution_expires_after` | Unix 秒 / 秒 |

**示例**

```bash
curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/cgt-2026**** \
  -H "Authorization: Bearer $ARK_API_KEY"
```

```python
import time

def wait_video(task_id, interval=10, max_wait=1800):
    deadline = time.time() + max_wait
    while time.time() < deadline:
        r = requests.get(f"{BASE}/contents/generations/tasks/{task_id}", headers=H, timeout=30)
        r.raise_for_status()
        t = r.json()
        if t["status"] == "succeeded":
            return t["content"]["video_url"], t.get("content", {}).get("last_frame_url"), t["usage"]
        if t["status"] in ("failed", "cancelled", "expired"):
            raise RuntimeError(f"{t['status']}: {t.get('error')}")
        time.sleep(interval)   # QPS 上限 20，勿高频轮询
    raise TimeoutError(task_id)

video_url, last_frame, usage = wait_video(task_id)
print(video_url, usage["completion_tokens"])
```

成功响应示例（2298881）：

```json
{
  "id": "cgt-2025****",
  "model": "doubao-seedance-2-5-260628",
  "status": "succeeded",
  "content": {"video_url": "https://ark-content-generation-cn-beijing.tos-cn-beijing.volces.com/****"},
  "usage": {"completion_tokens": 246840, "total_tokens": 246840},
  "created_at": 1765510475, "updated_at": 1765510559,
  "seed": 58944, "resolution": "1080p", "ratio": "16:9", "duration": 5,
  "framespersecond": 24, "service_tier": "default", "execution_expires_after": 172800
}
```

官方 SDK：`client.content_generation.tasks.get(task_id=task_id)`。

### 3.4 查询任务列表

**Endpoint**: `GET https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks`

**用途**: 按条件批量查最近 7 天的任务。账号维度 QPS 上限仅 **1**，不要用它做轮询。

**Query 参数**

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `page_num` | integer | `1` | `[1, 500]` |
| `page_size` | integer | `20` | `[1, 500]` |
| `filter.status` | string | — | `queued` / `running` / `cancelled` / `succeeded` / `failed` |
| `filter.task_ids` | string[] | — | 精确匹配，多值重复参数名：`filter.task_ids=id1&filter.task_ids=id2` |
| `filter.model` | string | — | 文档写「推理接入点 ID（`ep-` 开头）精确搜索」。⚠ 文档未说明：用 Model ID 创建的任务能否用 Model ID 过滤 |
| `filter.service_tier` | string | `default` | `default` / `flex` |

**响应**: `{"items": [ <与 §3.3 单任务结构相同> ], "total": <符合条件总数>}`。

```bash
curl -G https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Authorization: Bearer $ARK_API_KEY" \
  --data-urlencode "filter.status=succeeded" \
  --data-urlencode "page_size=50"
```

```python
r = requests.get(f"{BASE}/contents/generations/tasks", headers=H,
                 params={"filter.status": "running", "page_num": 1, "page_size": 50}, timeout=30)
items, total = r.json()["items"], r.json()["total"]
```

### 3.5 取消或删除任务

**Endpoint**: `DELETE https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{id}`

**用途**: 同一接口两种语义，按当前状态决定；QPS 上限 20。

| 当前状态 | 支持 DELETE | 含义 | 之后状态 |
|---|---|---|---|
| `queued` | 是 | 取消排队 | `cancelled` |
| `running` | 否 | — | — |
| `succeeded` / `failed` / `expired` | 是 | 删除任务记录，之后不可查询 | — |
| `cancelled` | 否 | — | — |

成功 HTTP 200，响应体 `Result` 为空对象 `{}`（文档原文，未实测具体 JSON 外层结构）。

```bash
curl -X DELETE https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/cgt-2026**** \
  -H "Authorization: Bearer $ARK_API_KEY"
```

```python
requests.delete(f"{BASE}/contents/generations/tasks/{task_id}", headers=H, timeout=30).raise_for_status()
```

官方 SDK：`client.content_generation.tasks.delete(task_id=...)`。

### 3.6 Seedance 2.5 任务类型与报错机制

2.5 会根据素材和提示词**自动判定任务类型**，不同类型对 `ratio` / `duration` 有硬限制（2607688「使用前必读」）：

| 任务类型 | 触发条件 | 限制 |
|---|---|---|
| 文生视频 | 仅文本 | 无 |
| 首帧 / 首尾帧 | `role` = `first_frame` / `last_frame` | `ratio` 必须 `adaptive`（与首帧图一致） |
| 全模态 – 参考生视频 | 至少 1 个 `reference_*` 素材 | 无 |
| 全模态 – 视频编辑 | 有 `reference_video` + 编辑意图（关键词：编辑视频、增加 / 加上、删除 / 去掉、修改 / 替换 / 改成） | `ratio=adaptive`、`duration=-1`、参考视频 4–30 s |
| 全模态 – 视频延长 | 有 `reference_video` + 延长意图（向前 / 向后延长、延续、续写） | `ratio=adaptive`；`duration` 可 `[4,30]` 或 `-1` |

推荐配置：不确定子任务时 `omni_reference_task_type=auto` + `ratio=adaptive` + `duration=-1`，这套组合兼容三类子任务。明确是编辑 / 延长时显式传 `edit` / `extend`，把校验前置。

两种报错（文档原文，未实测）：

- **同步报错**（提交时）：显式 `edit` / `extend` 且参数不合限制 → 立即 400，任务不创建。
- **异步报错**（任务启动后，查询接口 `error` 才出现，可能要排队到被消费时才报）：
  - `InvalidParameter.TaskTypeConstraint`：`auto` 模式下模型判定的类型与参数不兼容；
  - `InvalidParameter.TaskTypeMismatch`：显式指定的类型与模型按提示词判定的类型不一致。

因此对 2.5 不能只看创建接口 200 就当成功，必须在轮询里处理 `failed` + `error.code`。

### 3.7 token 用量估算与计费口径

来源：模型价格页 1544106「视频生成模型」。

- 视频价格 = token 单价 × token 用量；仅对成功生成的视频计费，审核失败不收费。
- **token 用量估算公式**：`(输入视频时长 + 输出视频时长) × 输出视频宽 × 输出视频高 × 输出帧率 / 1024`（帧率固定 24；无输入视频时输入时长为 0）。
  - 例：720p 16:9（1280×720）、5 s、无输入视频 → `5 × 1280 × 720 × 24 / 1024 ≈ 108,000` token。
- 样片模式：`估算 token × 折算系数`，1.5 pro 无声 0.7 / 有声 0.6；其他模型不支持。
- 2.0 系列与 2.5 **输入包含视频时有最低 token 用量**（与分辨率、宽高比、时长有关，见价格页外链表格）；估算 < 最低时按最低计费，`usage.completion_tokens` 返回的也是最低值。
- 2.5 / 2.0 系列按「输出分辨率 × 输入是否含视频」区分单价；1.5 pro 按有声 / 无声区分；具体单价与限时折扣看价格页，本文不抄录。
- 准确用量以 `usage.completion_tokens` 为准。

### 3.8 输入限制、保存时间、限流、人像与版权 IP

**输入素材限制**

| 素材 | 要求 |
|---|---|
| 图片 | jpeg / png / webp / bmp / tiff / gif（1.5 pro 及以上加 heic / heif）；宽高比 `[0.4, 2.5]`；单边 `[300, 6000]` px；< 30 MB。张数：首帧 1、首尾帧 2、2.5 参考 1–30、2.0 参考 1–9 |
| 视频 | mp4（H.264 / H.265，AAC / MP3）、mov（H.264 / H.265，AAC / MP3 / PCM）；分辨率 480p–4k（⚠ 文档自相矛盾：2607688 使用限制写 2.5 输入视频仅 480p / 720p，1520757 写 480p / 720p / 1080p / 4k）；宽高比 `[0.4, 2.5]`；单边 `[300, 6000]`；总像素 `[407696, 8295044]`；≤ 200 MB；FPS `[24, 60]`。时长：2.5 非编辑 `[2, 30]` s、编辑 `[4, 30]` s，≤ 10 个且总长 ≤ 30 s；2.0 系列 `[2, 15]` s，≤ 3 个且总长 ≤ 15 s |
| 音频 | wav / mp3；≤ 15 MB。2.5：单段 `[2, 30]` s，≤ 10 段，总长 ≤ 30 s；2.0 系列：`[2, 15]` s，≤ 3 段，总长 ≤ 15 s |
| 请求体 | ≤ 64 MB |

**保存时间**：任务记录 7 天；视频 / 尾帧 URL 24 小时，2.5 产物下载 ≤ 100 次。建议配置 TOS 数据订阅自动转存。

**限流**（超限返回 `429 Too Many Requests`，文档原文，未实测）：

- 在线推理：RPM（每分钟创建任务数）+ 最大并发（达到后新任务排队）。2.5 与 2.0 系列非 4k：企业 600 RPM / 10 并发，个人 180 RPM / 3 并发；2.0 的 4k：15 RPM / 1 并发。其他模型见模型列表页。
- 离线推理（flex）：TPD 限制。
- 非推理接口 QPS：查询单任务 20、查询列表 1、取消 / 删除 20。

**人像**：2.5 / 2.0 系列不能直接上传含真人人脸的图 / 视频；可用「本账号近 30 天内 Seedance 2.5 / 2.0 生成的含人脸原始产物」、预置虚拟人像库（`asset://<ASSET_ID>`）或已授权真人素材，详见文档 2608626《Doubao Seedance 便利创作含肖像视频》。

**版权 IP 视频**：当前仅在控制台体验中心基于特定版权 IP 用 2.0 / 2.5 生视频（费用为普通视频的 1.1× / 1.5×），API 不涉及，详见价格页 1544106「版权视频生成价格」。

---

## 4. Agent Plan 入口下调用图片 / 视频

来源：2375486 接入视觉模型、2366394 套餐概览、auth.md。

- **Base URL**：`https://ark.cn-beijing.volces.com/api/plan/v3`，路径与标准入口完全一致（`/images/generations`、`/contents/generations/tasks[/{id}]`）。用错成 `/api/v3` 会走后付费产生额外费用。
- **Key**：Agent Plan 专属 API Key（`ARK_AGENT_PLAN_API_KEY`），方舟 API Key / Coding Plan Key 不通用。
- **model**：小写 Model Name。图片 `doubao-seedream-5.0-lite`；视频 `doubao-seedance-2.0`、`doubao-seedance-2.0-fast`、`doubao-seedance-2.0-mini`、`doubao-seedance-1.5-pro`（标注「即将下线」）。Agent Plan 文档未列 Seedream 5.0 pro 与 Seedance 2.5。
- **套餐限制**：2366394 原文「Small、Medium 套餐仅供轻量化体验，不支持视频生成」。文档自相矛盾（已实测裁决）：同页模型表中 `doubao-seedance-1.5-pro` 一列 Medium 打 √（Small ×），2.0 系列 Small / Medium 均 ×。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Medium 档 `POST /api/plan/v3/contents/generations/tasks`，`model: "doubao-seedance-2.0-mini"` → HTTP **404**，原文 `{"error":{"code":"UnsupportedModel","message":"The requested model does not support the agent plan feature. Please refer to the documentation at https://www.volcengine.com/docs/82379/2366394 to select a compatible model. Request id: ...","param":"","type":""}}` —— 正文「Small / Medium 不支持视频」属实，错误码是通用的 `UnsupportedModel`（与套餐外文本模型同一文案），不是额度 / 档位专用码；表格里 `doubao-seedance-1.5-pro` Medium √ 未测（即将下线）。图片 `doubao-seedream-5.0-lite` Medium 档实测 200。
- **参数子集**（2375486「支持模型及能力」）：`doubao-seedream-5.0-lite` 分辨率 2K / 3K / 4K、png / jpeg、仅标准提示词优化模式、组图 ≤ 15、支持流式与联网搜索；视频输出 mp4，2.0 480p–4k / fast 与 mini 480p–720p / 1.5 pro 480p–1080p，时长 2.0 系列 4–15 s、1.5 pro 4–12 s，均支持返回尾帧，1.5 pro 支持样片模式。
- **计费**：AFP 抵扣。图片 `成功张数 × 99 AFP`；视频 `token / 10000 × 抵扣系数`（系数按模型、分辨率、输入是否含视频区分，例如 2.0 720p 无视频输入 230）。完整系数表与超额后付费规则见 `agent-plan.md`。
- 官方 Skill 方式（`byted-ark-seedream-skill` / `byted-ark-seedance-skill`，`npx skills add https://skills.volces.com/skills/volcengine/agentplan -s <skill> --agent claude-code`）与 API 方式二选一，本文只讲 API。

```bash
curl https://ark.cn-beijing.volces.com/api/plan/v3/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_AGENT_PLAN_API_KEY" \
  -d '{"model":"doubao-seedream-5.0-lite","prompt":"Vogue 风格特写肖像，雕塑感帽子，浅景深",
       "size":"2k","output_format":"png","watermark":false}'
```
（`size` 用小写 `2k`：实测 5.0 lite 只认 `2k` / `3k` / `4k` / `WIDTHxHEIGHT`，`"1K"` 报 400，见 §2.3。）

```python
import os
from openai import OpenAI

plan = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
              api_key=os.environ["ARK_AGENT_PLAN_API_KEY"])
img = plan.images.generate(model="doubao-seedream-5.0-lite",
                           prompt="Vogue 风格特写肖像，雕塑感帽子，浅景深",
                           size="2k", response_format="url",   # 实测只认 2k/3k/4k/WIDTHxHEIGHT
                           extra_body={"output_format": "png", "watermark": False})
print(img.data[0].url)   # 实测响应：model "doubao-seedream-5.0-lite"、data[0].size "2048x2048"、usage.output_tokens 16384；抵扣 99 AFP

# 视频：同一把 Key，requests 直调。Large / Max 套餐才可用：Medium 档实测 404 UnsupportedModel（见上文「套餐限制」）
import requests
r = requests.post("https://ark.cn-beijing.volces.com/api/plan/v3/contents/generations/tasks",
    headers={"Authorization": f"Bearer {os.environ['ARK_AGENT_PLAN_API_KEY']}"},
    json={"model": "doubao-seedance-2.0",
          "content": [{"type": "text", "text": "女孩抱着狐狸睁开眼看向镜头，镜头缓缓拉出"},
                      {"type": "image_url", "image_url": {"url": "https://example.com/first.png"}}],
          "generate_audio": True, "ratio": "adaptive", "duration": 5, "watermark": False},
    timeout=60)
print(r.json()["id"])   # 之后 GET /api/plan/v3/contents/generations/tasks/{id} 轮询
```

---

## 5. 3D 生成（索引）

3D 生成也是异步任务，Python SDK 示例复用 `client.content_generation.tasks.create(...)`，即与视频相同的 `POST /api/v3/contents/generations/tasks` 路径，参数写在 `content[]` 的 text 里（如 `--subdivisionlevel medium --fileformat glb`）+ `image_url`；产物链接 24 小时有效，耗时分钟级。模型：`doubao-seed3d-2-0-260328`（图生 3D，glb / obj / usd / usdz，见「3D 生成 API」文档 2353367）、`hyper3d-gen2-260112`（影眸 API，文档 2279945）、`hitem3d-2-0-251223`（数美 API，文档 2307069）。参数与限制本文不展开，见原文档 1874993《3D 生成》。

---

## 来源页面

| 标题 | URL | 文档更新时间 |
|---|---|---|
| 图片生成 API | https://www.volcengine.com/docs/82379/1541523 | 2026-08-28 |
| 图片生成流式响应事件 | https://www.volcengine.com/docs/82379/1824137 | 2026-07-24 |
| 图片生成教程 | https://www.volcengine.com/docs/82379/1824121 | 2026-08-12 |
| Doubao Seedream 5.0 pro 教程 | https://www.volcengine.com/docs/82379/2582774 | 2026-08-28 |
| Doubao Seedream 5.0 pro 实现交互编辑指南 | https://www.volcengine.com/docs/82379/2582775 | 2026-08-17 |
| 创建视频生成任务 | https://www.volcengine.com/docs/82379/1520757 | 2026-08-21 |
| 查询视频生成任务 | https://www.volcengine.com/docs/82379/1521309 | 2026-08-19 |
| 查询视频生成任务列表 | https://www.volcengine.com/docs/82379/1521675 | 2026-08-28 |
| 取消或删除视频生成任务 | https://www.volcengine.com/docs/82379/1521720 | 2026-08-18 |
| 视频生成教程 | https://www.volcengine.com/docs/82379/2298881 | 2026-09-01 |
| Doubao Seedance 2.5 教程 | https://www.volcengine.com/docs/82379/2607688 | 2026-09-01 |
| Doubao Seedance 2.0 系列教程 | https://www.volcengine.com/docs/82379/2291680 | 2026-08-17 |
| 接入视觉模型（Agent Plan） | https://www.volcengine.com/docs/82379/2375486 | 2026-08-24 |
| 套餐概览（Agent Plan） | https://www.volcengine.com/docs/82379/2366394 | 2026-08-31 |
| 模型价格（仅取视频 token 公式与版权 IP 段） | https://www.volcengine.com/docs/82379/1544106 | 2026-08-27 |
| 错误码（仅取审核 / 任务类型相关） | https://www.volcengine.com/docs/82379/1299023 | 2026-08-18 |
| 3D 生成 | https://www.volcengine.com/docs/82379/1874993 | 2026-09-01 |
