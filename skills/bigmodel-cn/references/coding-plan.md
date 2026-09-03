# GLM Coding Plan（编程套餐）vs 标准 API

来源：`docs.bigmodel.cn/cn/coding-plan/overview`、`/cn/coding-plan/faq`、`/cn/coding-plan/tool/claude`、`/cn/coding-plan/tool/opencode`、`/cn/coding-plan/tool/others`、`/cn/coding-plan/mcp/*`（整理于 2026-09）。**文中标注「实测」的结论均已于 2026-09-03 用一把标准 Key 和一把 Coding Plan Key 对真实 API 逐条验证**，脚本见 `bigmodel-cn-workspace/coding-plan-probe.py`。

**一句话结论**：智谱有**两套彼此隔离的计费体系**——按 token 计费的**标准 API**，和按套餐额度计费的 **GLM Coding Plan**。两者的 **API Key 不通用、Base URL 不一样、可用模型范围不一样、允许使用的场景也不一样**。写代码/配工具之前必须先问清楚用户手里是哪一种 Key，用错组合的典型症状是明明买了套餐却报 `1113 余额不足`。

## 先判断用户属于哪一种

| 用户的说法 | 属于 | 该用的 Key | 该用的 Base URL |
| :--- | :--- | :--- | :--- |
| "开放平台 API Key""按量付费""资源包""我要调 embedding / 生图 / 语音" | 标准 API | 控制台 `https://bigmodel.cn/usercenter/proj-mgmt/apikeys` 创建的 Key | `https://open.bigmodel.cn/api/paas/v4`（OpenAI 兼容 / 原生）或 `https://open.bigmodel.cn/api/anthropic`（Anthropic 兼容） |
| "GLM Coding Plan""编程套餐""Lite / Pro / Max 套餐""套餐额度""5 小时额度" | Coding Plan | 个人版：`https://bigmodel.cn/coding-plan/personal/overview` 里新建的 Key；团队版：「团队编程套餐 > 我的套餐」里的团队 Key | `https://open.bigmodel.cn/api/coding/paas/v4`（OpenAI 兼容 / 原生）或 `https://open.bigmodel.cn/api/anthropic`（Anthropic 兼容） |

官方原话："团队套餐 Key 与平台其他 API Key 不通用，使用团队额度请务必使用团队套餐 Key"；"Base URL 配置错误将导致无法使用 GLM Coding Plan 额度"。

如果用户没说清楚，**直接问一句**"你用的是开放平台按量付费的 Key，还是 GLM Coding Plan 套餐的 Key？"——这比事后排查 1113 便宜得多。

## 端点与能力对照表

| 维度 | 标准 API | GLM Coding Plan |
| :--- | :--- | :--- |
| OpenAI 兼容 / 原生 HTTP Base URL | `https://open.bigmodel.cn/api/paas/v4` | `https://open.bigmodel.cn/api/coding/paas/v4` |
| Anthropic 兼容 Base URL | `https://open.bigmodel.cn/api/anthropic` | **同一个** `https://open.bigmodel.cn/api/anthropic`，靠 Key 区分走哪套额度 |
| 鉴权 | `Authorization: Bearer <KEY>`（Anthropic 兼容层也接受 `x-api-key`） | 同左，只是换成套餐 Key |
| 计费 | 按 token / 资源包，上下文缓存命中打折 | 套餐额度，**每 5 小时**滚动重置一档 + **每 7 天**重置一档；额度用尽不会自动扣账户余额（"无额度溢出"）；缓存计费规则**不适用**套餐 |
| 可用模型 | 全部（见 `references/models.md`） | 官方：所有档位都支持 `glm-5.3`、`glm-5.3-flash`；旧代码自动路由到新版本。**实测**（套餐 Key 打 Coding 端点，看响应里的 `model` 字段）：`glm-5.2`/`glm-5.1` → `glm-5.3`；`glm-5-turbo`/`glm-4.7`/`glm-4.6`/`glm-4.5-air` → `glm-5.3-flash`；视觉模型 `glm-4.6v`、`glm-5v-turbo` 原样可用；免费模型 `glm-4.7-flash`/`glm-4.5-flash`/`glm-4-flash-250414` 原样可用；`glm-4-long`/`charglm-4`/`codegeex-4` 报 `1113`。**别依赖自动路由**：请求 `glm-4.5-air` 实际跑的是 `glm-5.3-flash`，日志/计费里看到的模型名会和代码里写的不一样 |
| 可用能力 | 对话、多模态、embeddings、rerank、图像/视频/语音生成、文件/Batch、知识库…… | **实测**套餐 Key 在 Coding 端点：`chat/completions`（含函数调用、`response_format: json_object`、思考）✅、`reader` 网页阅读 ✅；`embeddings`、`rerank`、`tokenizer`、`async/chat/completions`、`web_search`（独立端点）、`images/generations` 全部 **429 + `1113`**。`chat/completions` 里挂 `web_search` 工具类型返回 200 但响应没有 `web_search` 结果字段（搜索没真正执行），套餐的联网搜索要走官方 MCP。这些能力需要另用标准 Key 走 `paas/v4` |
| 使用范围 | 任意程序 | 官方原话："套餐仅限在官方支持的指定工具与产品环境中使用"（Claude Code、Kilo Code、OpenClaw、OpenCode、TRAE、CodeBuddy、Cherry Studio 等）；在指定环境之外调用"无法享受套餐权益" |
| 思考模式默认值 | Preserved Thinking 默认**关**，`thinking.clear_thinking:false` 开 | Preserved Thinking 在 Coding 端点默认**开**（见 `references/chat.md`） |
| `thinking: {"type":"disabled"}` 对 `glm-5.3` / `glm-5.3-flash` | **实测** 400 + `1210 该模型始终思考，不支持关闭思考；请使用 low、high 或 max` | **实测** 200 且 `reasoning_tokens=0`——同一个请求体在 Coding 端点被接受并真的关掉了思考（标准 Key、套餐 Key 都一样）。两个端点的参数校验不一致，写跨端点通用代码时不要假设行为相同 |
| 标准 Key 能不能打 Coding 端点 | — | **实测可以**：标准 Key 在 `…/api/coding/paas/v4` 上 chat/embeddings/rerank/images/web_search/async 全部 200，按标准计费走。所以「Coding 端点 = 套餐专用」不成立，Coding 端点是一条能同时服务两种 Key 的路由；反过来套餐 Key 打标准端点则必定 `1113` |
| `GET /models` | 返回 10 个文本模型 | 返回**同一份** 10 个模型列表（`glm-4.5` … `glm-5.3-flash`），不是套餐专属列表，不能用它判断套餐权益 |
| OpenClaw 等非编码 Agent | — | "二级调度"：尽力交付，高峰期 Coding Agent 任务优先 |

额度扣减公式（官方，以 `glm-5.3` 为例）：`(输入 tokens × 6.9 + 缓存命中输入 × 1.7 + 输出 × 24) ÷ 10000`，非高峰时段（周一至周五 14:00–18:00 UTC+8 之外）按半价扣。各档 5 小时 / 每周额度：Lite 2,000 / 10,000，Pro 12,000 / 60,000，Max 28,000 / 140,000（数字会调整，以 `docs.bigmodel.cn/cn/coding-plan/overview` 为准）。

## 典型报错与排查顺序

| 现象 | 真实原因 | 处理 |
| :--- | :--- | :--- |
| 买了 Coding Plan，用 `https://open.bigmodel.cn/api/paas/v4` 调用报 **HTTP 429**，`{"error":{"code":"1113","message":"余额不足或无可用资源包,请充值。"}}` | 套餐 Key 打到了标准 API 端点，标准端点只认账户余额/资源包，看不到套餐额度 | **不要让用户去充值**，把 Base URL 改成 `https://open.bigmodel.cn/api/coding/paas/v4`。**已实测复现**：同一把套餐 Key，标准端点 `1113`，Coding 端点 200 |
| 请求打到了 `.../api/coding/paas/v4/v1/chat/completions` 报 404（**实测**响应体 `{"status":404,"error":"Not Found","path":"/v4/v1/chat/completions"}`） | 很多客户端会自动在 Base URL 后面拼 `/v1`；Coding 端点的路径没有 `/v1` 这一级 | Base URL 填到 `.../coding/paas/v4` 为止，关闭客户端"自动追加 /v1"的行为；Claude Code 走 `/api/anthropic` 时 SDK 自己会拼 `/v1/messages`，那是正常的 |
| 团队套餐成员用了个人 Key / 平台 Key，额度没从团队扣 | 团队 Key 与其他 Key 不通用 | 用「团队编程套餐 > 我的套餐」里的 Key |
| 套餐到期后工具全部报错 | 套餐额度失效，但账户里可能还有资源包 | 官方 FAQ 建议此时把 Base URL 改回 `https://open.bigmodel.cn/api/paas/v4` 并换成平台 Key 走资源包/按量计费 |
| 用套餐 Key 调 `embeddings` / `rerank` / `tokenizer` / `async/chat` / `images/generations` / 独立 `web_search`（无论打哪个端点） | **实测**全部 429 + `1113`：这些能力不在套餐内，错误码和「打错端点」一模一样，光看错误码分不清 | 换标准 Key 走 `paas/v4`；同一个脚本里两套 Key 分开管理（例如 `ZHIPUAI_API_KEY` 与 `GLM_CODING_PLAN_API_KEY`） |
| 用套餐 Key 请求 `glm-4-long` / `charglm-4` / `codegeex-4` 等模型 | **实测** `1113`，模型不在套餐内 | 换 `glm-5.3` / `glm-5.3-flash`，或用标准 Key |
| 5 小时额度用光 | 套餐额度到顶，等窗口刷新 | 官方定位是"动态重置"，不要写死时间；在代码里对 429 类响应做退避，不要重试风暴 |

排查顺序：**1. 先确认 Key 属于哪套体系 → 2. 再核对 Base URL 是否与之匹配 → 3. 再核对模型是否在该体系可用 → 4. 最后才考虑余额/额度问题。**

## 在 Claude Code 里使用 Coding Plan

官方（`/cn/coding-plan/tool/claude`）给出的 `~/.claude/settings.json` 环境变量配置：

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "你的 Coding Plan API Key",
    "ANTHROPIC_BASE_URL": "https://open.bigmodel.cn/api/anthropic",
    "API_TIMEOUT_MS": "3000000",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-5.3-flash",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.3",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5.3"
  }
}
```

要点：

- 注意变量名是 `ANTHROPIC_AUTH_TOKEN`（Claude Code 读它作为 Bearer token），不是 `ANTHROPIC_API_KEY`。
- Base URL 与标准 API 的 Anthropic 兼容层完全一样，**区别只在 Key**。用平台按量 Key 填这里也能跑，只是走的是按 token 计费。
- 三个 `ANTHROPIC_DEFAULT_*_MODEL` 把 Claude Code 内部对 haiku/sonnet/opus 的引用映射到 GLM 模型，否则 Claude Code 会去请求不存在的 `claude-*` 模型名。
- 用 shell 环境变量 `export ANTHROPIC_AUTH_TOKEN=... ANTHROPIC_BASE_URL=...` 也可以，效果相同。

## 在自己的代码 / 其它工具里使用 Coding Plan

OpenAI SDK（Python）：

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["GLM_CODING_PLAN_API_KEY"],          # 套餐 Key，不是平台 Key
    base_url="https://open.bigmodel.cn/api/coding/paas/v4",  # 注意多了 /coding
)
resp = client.chat.completions.create(
    model="glm-5.3",
    messages=[{"role": "user", "content": "写一个快速排序"}],
)
print(resp.choices[0].message.content)
```

Anthropic SDK（Python）：

```python
import os, anthropic

client = anthropic.Anthropic(
    api_key=os.environ["GLM_CODING_PLAN_API_KEY"],
    base_url="https://open.bigmodel.cn/api/anthropic",
)
msg = client.messages.create(
    model="glm-5.3", max_tokens=1024,
    messages=[{"role": "user", "content": "写一个快速排序"}],
)
print(msg.content[0].text)
```

原生 HTTP：把 `references/chat.md` 里所有 `https://open.bigmodel.cn/api/paas/v4/...` 换成 `https://open.bigmodel.cn/api/coding/paas/v4/...`，请求体字段完全一致。

其它编码工具（OpenCode、Kilo Code、Cherry Studio、cc-switch 等）的配置都是同一件事：提供商选"智谱 / Zhipu AI Coding Plan"，Base URL 填 `https://open.bigmodel.cn/api/coding/paas/v4`（Cherry Studio 文档写法带末尾斜杠 `.../v4/`），模型填 `glm-5.3` 或 `glm-5.3-flash`，上下文窗口按模型填（`glm-5.2`/`glm-5.3` 为 1,000,000，其余 200,000）。

**务必提醒用户**：官方条款规定套餐只能在指定工具环境内使用，自己写脚本调 Coding 端点在技术上能通，但属于条款之外的用法，是否消耗套餐额度、是否被限制以官方为准；生产系统应当用标准 API Key。

## 套餐附赠的 MCP 工具

Coding Plan 用户可以用智谱提供的本地 MCP Server（视觉理解、联网搜索、网页阅读、开源仓库检索等），通过 `npx -y "@z_ai/mcp-server"` 启动，环境变量：

```json
{
  "mcpServers": {
    "zai-mcp-server": {
      "command": "npx",
      "args": ["-y", "@z_ai/mcp-server"],
      "env": {
        "Z_AI_API_KEY": "你的 Coding Plan API Key",
        "Z_AI_MODE": "ZHIPU"
      }
    }
  }
}
```

官方定位："智谱为 GLM Coding Plan 用户开发的专属 Local MCP Server"——这些 MCP 走的是套餐额度，和 `references/tools.md` 里的 `/paas/v4/web_search`、`/paas/v4/reader` 独立 HTTP 端点（标准 API 计费）是两条路。

## 实测记录（2026-09-03，给维护者）

用一把标准 Key（`ZHIPUAI_API_KEY`）和一把个人 Coding Plan Key（`GLM_CODING_PLAN_API_KEY`）运行 `bigmodel-cn-workspace/coding-plan-probe.py` 及补充探测，结论：

| 组合 | 结果 |
| :--- | :--- |
| 套餐 Key → `…/api/paas/v4/chat/completions` | 429 `1113` |
| 套餐 Key → `…/api/coding/paas/v4/chat/completions`（glm-5.3 / glm-5.3-flash） | 200 |
| 套餐 Key → `…/api/anthropic/v1/messages`（Bearer 或 `x-api-key` 都行） | 200 |
| 套餐 Key → Coding 端点 embeddings / rerank / tokenizer / async chat / web_search / images | 429 `1113` |
| 套餐 Key → Coding 端点 `reader` | 200 |
| 套餐 Key → Coding 端点 函数调用 / `json_object` | 200，`tool_calls` 正常返回 |
| 标准 Key → Coding 端点（chat / embeddings / rerank / images / web_search / async） | 全部 200 |
| `thinking.disabled` on glm-5.3(-flash) | 标准端点 400 `1210`；Coding 端点 200 且 `reasoning_tokens=0` |
| `GET /models` 两个端点 | 同一份 10 个模型列表 |
| `…/coding/paas/v4/v1/chat/completions` | 404 |

**与官方文档不一致的地方**（已在上文标注）：官方只列了 4 个自动路由的旧模型代码，实测 `glm-4.6`、`glm-4.5-air` 也被路由；官方没说视觉模型 `glm-4.6v` / `glm-5v-turbo` 可用，实测可用；官方把 Coding 端点描述成套餐专用，实测标准 Key 也能用。这些行为没有文档背书，随时可能变，代码里只依赖 `glm-5.3` / `glm-5.3-flash` 最稳。

**未覆盖**：团队套餐 Key、套餐额度耗尽时的具体错误码、`glm-4.6v-flash`（探测时恰好 `1305` 过载）。
