# 火山方舟模型目录与选型（`model` 字段填什么）

本文件覆盖：`model` 字段的三种形态及各自生效的入口、标准 API 全部模型的能力/长度/限流目录、后付费单价、Coding Plan / Agent Plan 套餐内可用模型与 AFP 抵扣系数、选型建议、推理方式概念、近期上下线。鉴权与 Base URL 见 `auth.md`；各 endpoint 的参数细节见同目录其他 reference。

> **验证范围说明**：标 **已用真实 API 验证（2026-09-04，Agent Plan Medium）** 的结论全部来自 **Agent Plan 入口 `/api/plan/v3`**（专属 Key）及其 Anthropic 协议入口 `/api/plan/v1/messages`。标准入口 `/api/v3` 与 Coding Plan `/api/coding/v3` 没有 Key，**未实测**；"预期相同"均为推断。原始记录见 `volcengine-ark-workspace/verification-log.jsonl`。

## 目录

1. [`model` 字段三种形态与入口对应关系](#1-model-字段三种形态与入口对应关系)
2. [前置步骤：开通模型 → 拿 Key → 调用](#2-前置步骤开通模型--拿-key--调用)
3. [标准 API 模型目录（Model ID）](#3-标准-api-模型目录model-id)
4. [后付费单价（标准 API）](#4-后付费单价标准-api)
5. [Plan 内可用模型对照表（Model Name）](#5-plan-内可用模型对照表model-name)
6. [选型建议](#6-选型建议)
7. [推理方式概念（常规 / 低延迟 / TPM 保障包 / 模型单元 / 批量 / 智能路由）](#7-推理方式概念)
8. [近期上线 / 下线信息](#8-近期上线--下线信息)
9. [来源页面](#9-来源页面)

---

## 1. `model` 字段三种形态与入口对应关系

| 形态 | 示例 | 生效入口 | 鉴权 | 说明 |
|---|---|---|---|---|
| **(a) Model ID**（带日期版本，连字符分隔） | `doubao-seed-2-1-pro-260628`、`deepseek-v4-flash-ga-260731`、`doubao-seedream-5-0-260128` | 标准 `https://ark.cn-beijing.volces.com/api/v3` | 方舟 API Key（`ARK_API_KEY`） | 系统自动匹配"预置推理接入点"，不存在则自动创建。**唯一例外**：`doubao-seed-evolving` 没有日期后缀，是周级滚动更新的统一 ID |
| **(a') 推理接入点 Endpoint ID** | `ep-2xxxxxxx1-rr9kp` | 标准 `/api/v3` | 方舟 API Key；**使用 Access Key 签名鉴权时必须用 ep** | 控制台创建的自定义接入点。低延迟 / TPM 保障包 / 模型单元 / 智能路由 / 批量推理 / 精调模型都只能走 ep |
| **(b) Model Name**（无日期，小写，版本用点） | `doubao-seed-2.1-turbo`、`doubao-seed-2.0-lite`、`glm-5.3`、`deepseek-v4-pro`、`kimi-k2.7-code` | Coding Plan `/api/coding[/v3]`、Agent Plan `/api/plan[/v3]` | Coding Plan：方舟 API Key；Agent Plan：**专属** Key（`ARK_AGENT_PLAN_API_KEY`） | 文档说"支持通过 model name 及控制台选择进行访问"（`deepseek-v4-pro 正式版` 上线公告）。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Name 会被解析到一个**固定日期版本**并在响应 `model` 回显（`doubao-seed-2.0-lite` → `doubao-seed-2-0-lite-260215`），对照表见 1.1 |
| **(b') 路由名** | `ark-code-latest`（在控制台切目标模型，3–5 分钟生效）；`glm-latest` / `minimax-latest` / `kimi-latest` / `deepseek-latest`（自动指向该系列最新版） | Plan 入口 | 同上 | `latest` 对应关系（2026-08）：`glm-latest`→`glm-5.3`，`minimax-latest`→`minimax-m3`，`kimi-latest`→`kimi-k2.7-code`，`deepseek-latest`→`deepseek-v4-pro`。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`glm-latest` → 200，响应 `"model":"glm-5.3"`；`ark-code-latest` → 200，响应 `"model":"auto"`（控制台当前选 Auto）。其余 `*-latest` 未测 |

### 1.1 命名规则：Model ID 用连字符，Model Name 用点

同一个模型在两套入口里写法不同，这是 Agent 最容易混的地方：

| 标准 API Model ID（`/api/v3`） | Plan 入口 Model Name（`/api/coding`、`/api/plan`） | 价格页写法（1544106） |
|---|---|---|
| `doubao-seed-evolving` | `doubao-seed-evolving` | `doubao-seed-evolving` |
| `doubao-seed-2-1-turbo-260628` | `doubao-seed-2.1-turbo` | `doubao-seed-2.1-turbo` |
| `doubao-seed-2-1-pro-260628` | （Plan 内无此模型） | `doubao-seed-2.1-pro` |
| `doubao-seed-2-0-lite-260428` / `-260215` | `doubao-seed-2.0-lite`——**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Plan 入口实际服务 **`doubao-seed-2-0-lite-260215`**（响应 `model` 回显），不是模型列表最新的 `260428` | `doubao-seed-2.0-lite` |
| `doubao-seed-2-0-mini-260428` / `-260215` | `doubao-seed-2.0-mini`（仅 Agent Plan）——**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：实际服务 **`doubao-seed-2-0-mini-260215`** | `doubao-seed-2.0-mini` |
| `deepseek-v4-pro-ga-260813`（正式版）/ `deepseek-v4-pro-260425`（预览版） | `deepseek-v4-pro` | `deepseek-v4-pro正式版` / `预览版` |
| `deepseek-v4-flash-ga-260731`（正式版）/ `deepseek-v4-flash-260425`（预览版） | `deepseek-v4-flash` | `deepseek-v4-flash正式版` / `预览版` |
| `glm-5-2-260617` | `glm-5.2`（Plan 内已于 2026-08-31 下线，自动路由到 `glm-5.3`） | `glm-5.2` |
| ⚠ 标准 API 模型列表（1330310）中**没有** `glm-5-3`、`glm-5-3-flash`、`kimi-k2-7-code`、`kimi-k3`、`minimax-m3` 条目 | `glm-5.3`、`glm-5.3-flash`、`kimi-k2.7-code`、`kimi-k3`、`minimax-m3` | 价格页也没有这些模型的后付费单价 |
| `doubao-embedding-vision-251215` / `-250615` | `doubao-embedding-vision` | `doubao-embedding-vision` |
| `doubao-seedream-5-0-lite-260128`（与 `doubao-seedream-5-0-260128` 同一模型） | `doubao-seedream-5.0-lite`（仅 Agent Plan） | `doubao-seedream-5-0-lite` |
| `doubao-seedance-2-0-260128` / `-fast-260128` / `-mini-260615` | `doubao-seedance-2.0` / `-2.0-fast` / `-2.0-mini`（仅 Agent Plan Large/Max） | `doubao-seedance-2.0` 等 |
| ⚠ 模型列表页无语音模型 | `doubao-seed-tts-2.0`、`doubao-seed-asr-2.0`（仅 Agent Plan） | — |

要点：
- Plan 入口填带日期 Model ID——**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`model: "doubao-seed-2-0-lite-260428"` 打 `/api/plan/v3/chat/completions` → **200，但响应 `"model":"doubao-seed-2-0-lite-260215"`**。Plan 入口**接受** Model ID 却**静默忽略版本号**、按 Name 路由；Anthropic 入口 `/api/plan/v1/messages` 同样（`doubao-seed-2-0-lite-260428` → 服务模型 `doubao-seed-2-0-lite-260215`）。所以在 Plan 入口写 Model ID 不会报错、也不能锁版本。标准入口填 Model Name（如 `doubao-seed-2.1-turbo`）是否被接受**未测**（无标准 Key）。
- 套餐外 / 老模型——**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`doubao-seed-2.1-pro`（Plan 内无此模型）与 `doubao-seed-1-8-251228`（老 Model ID）打 Plan 入口都返回 **404** `{"error":{"code":"UnsupportedModel","message":"The requested model does not support the agent plan feature. Please refer to the documentation at https://www.volcengine.com/docs/82379/2366394 to select a compatible model. ...","param":"","type":""}}`。文档口径"Plan 入口只能用 Coding/Agent Plan 支持的模型"属实，错误码是 404 UnsupportedModel（不是 400/403）。
- 价格页（1544106）用的是点分写法且不带日期（如 `doubao-seed-2.1-pro`），查价时按系列名对应，不要拿它当 Model ID 用。
- 在 Plan 入口误用 `/api/v3`：控制台原话「请勿使用 https://ark.cn-beijing.volces.com/api/v3，接入会产生额外费用」；Coding Plan 文档：「如未使用指定的 Base URL，将无法使用 Coding Plan 额度，并可能产生额外 API 请求的费用」。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Agent Plan 专属 Key 打 `/api/v3` 或 `/api/coding/v3` 直接 **401** `{"error":{"code":"AuthenticationError","message":"The API key or AK/SK in the request is missing or invalid. ...","type":"Unauthorized"}}`，不会悄悄扣费；方舟标准 Key 打 `/api/plan/v3` 未测（推测同样 401）。
- `Auto` / `auto`：Coding Plan 文档表格把 `Auto` 列为"默认选择，智能调度模型"，但只给出两种配置方式——"配置 Model Name 实时切换" 或 "配置 `ark-code-latest` 在控制台切换"（`auth.md` 记录 Coding Plan 文档另说 Model Name 不支持填 `Auto`）；Agent Plan 控制台的 `ark-code-latest` 路由模型单选列表里却列出 `auto（智能调度）` 作为 Model Name。**已用真实 API 验证（2026-09-04，Agent Plan Medium）：`model: "auto"` → 404 UnsupportedModel（同上文案）——控制台"Model Name: auto"是错的，Coding Plan 文档"不支持配置为 Auto"是对的。** 要用智能调度只能 `model: "ark-code-latest"` + 控制台把路由目标选成 Auto（实测 200，响应 `"model":"auto"`，`reasoning_tokens: 0`）。已确定的是：`auto` 模式不支持超额后付费（2516284 原文）。

### 1.1.1 最容易踩的坑：Plan 入口 Model Name → 实际服务版本对照（已用真实 API 验证，2026-09-04，Agent Plan Medium）

| 你填的 `model` | 入口 | 实际服务模型（响应 `model` 回显） | 备注 |
|---|---|---|---|
| `doubao-seed-2.0-lite` | `/api/plan/v3` | `doubao-seed-2-0-lite-260215` | 不是最新的 `260428`；明文思维链、无 `encrypted_content` |
| `doubao-seed-2-0-lite-260428`（带日期） | `/api/plan/v3`、`/api/plan/v1/messages` | `doubao-seed-2-0-lite-260215` | **静默改版本**，不报错 |
| `doubao-seed-2.0-mini` | `/api/plan/v3` | `doubao-seed-2-0-mini-260215` | — |
| `glm-5.3` / `glm-latest` | `/api/plan/v3` | `glm-5.3` | 无日期版本号 |
| `kimi-k3` | `/api/plan/v3` | `kimi-k3` | Medium 档可用（Small 不可用，文档） |
| `ark-code-latest` | `/api/plan/v3`（Chat 与 Responses） | `auto` | 控制台当前路由目标为 Auto |
| `auto` | `/api/plan/v3` | **404 UnsupportedModel** | 不能直接填 |
| `doubao-seed-2.1-pro`、`doubao-seed-1-8-251228` | `/api/plan/v3` | **404 UnsupportedModel** | 套餐外 / 老模型 |
| **`claude-sonnet-4-5`（任何 `claude-*`）** | Anthropic 协议入口 `/api/plan/v1/messages` | **`doubao-seed-2-1-turbo-260628`** | **200，静默路由**，抵扣系数 2.5。Claude Code 忘设 `ANTHROPIC_MODEL` 时默认就是 `claude-*`，不会报错，而是悄悄用 2.1-turbo 烧 AFP——接 Claude Code 务必显式设 `ANTHROPIC_MODEL` 为套餐内 Model Name |
| `doubao-seedance-2.0-mini`（视频） | `/api/plan/v3/contents/generations/tasks`，Medium 档 | **404 UnsupportedModel** | Medium 不支持视频属实；错误不是"额度 / 档位"专用码，与套餐外模型同一文案 |

以上对照表只反映 2026-09-04 的解析结果；Name → 版本的映射由方舟侧维护、随时可能变，代码里不要依赖具体日期版本。

### 1.2 最小示例：同一请求在两套入口的 `model` 写法

curl（标准入口，Model ID）：
```bash
curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"doubao-seed-2-1-turbo-260628","messages":[{"role":"user","content":"hello"}]}'
```

curl（Agent Plan 入口，Model Name，专属 Key）：
```bash
curl https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions \
  -H "Authorization: Bearer $ARK_AGENT_PLAN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"doubao-seed-2.1-turbo","messages":[{"role":"user","content":"hello"}]}'
```

Python（`openai` SDK，切换 base_url + model 即可；Coding Plan 用 `/api/coding/v3` 与 `ARK_API_KEY`）：
```python
import os
from openai import OpenAI

# 标准入口
std = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/v3", api_key=os.environ["ARK_API_KEY"])
r = std.chat.completions.create(model="doubao-seed-2-1-turbo-260628",
                                messages=[{"role": "user", "content": "hello"}])

# Agent Plan 入口（文本模型官方口径仅限 AI 工具内使用，见 5.4）
plan = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/plan/v3", api_key=os.environ["ARK_AGENT_PLAN_API_KEY"])
r2 = plan.chat.completions.create(model="doubao-seed-2.1-turbo",
                                  messages=[{"role": "user", "content": "hello"}])
```

---

## 2. 前置步骤：开通模型 → 拿 Key → 调用

来自「快速入门」（1399008）与「产品简介」（1099455）：

1. **获取 API Key**：控制台左下角「API Key 管理」（`console.volcengine.com/ark/region:cn-beijing/apiKey`）创建，写入环境变量 `ARK_API_KEY`（macOS/Linux `export ARK_API_KEY="..."`；Windows CMD `setx`；PowerShell `$env:ARK_API_KEY`）。
2. **开通模型服务**：访问「开通管理」（`console.volcengine.com/ark/region:cn-beijing/openManagement`）逐个开通要用的模型。标准 API 按 token 后付费，**需先开通**才能调用。
3. **安装 SDK**（任选）：方舟 SDK `pip install 'volcengine-python-sdk[ark]'`（Windows CMD 用双引号）；或 `pip install openai`；Go `github.com/volcengine/volcengine-go-sdk`；Java `com.volcengine:volcengine-java-sdk-ark-runtime`。
4. **发起调用**：新用户直接用 Model ID 调用即可（方舟自动匹配预置接入点，无需部署）。快速入门示例统一用 `doubao-seed-2-1-pro-260628` + Responses API（`client.responses.create(model=..., input="hello")`），关闭思考传 `"thinking": {"type": "disabled"}`（OpenAI SDK 需放 `extra_body`）。
5. **文档导向**：新用户推荐 Responses API（更简洁的上下文管理与工具调用）；存量业务用 Chat API。生产接入参考「模型接入指南（LLM）- 标准流程」（2666489）。
6. Plan 用户不走上述 1–2 步开通逻辑：订阅套餐后在 Coding Plan / Agent Plan 控制台按「配置模型及 Base URL → 配置 Harness（可选，仅 Agent Plan）→ 配置专属 API Key（仅 Agent Plan）→ 接入使用」四步走（控制台实读）。

---

## 3. 标准 API 模型目录（Model ID）

数据来源：「模型列表」（1330310，更新 2026-09-02）。长度单位 token；"最大回答默认 4k"指 `max_tokens` 不传时的默认值。限流为"非刚性保障，受平台负载/调用方式影响"。`即将下线` 为文档原文标记，⚠ 具体下线日期文档未说明（Plan 侧日期见第 8 节）。

### 3.1 文本生成 / 深度思考模型

能力列缩写：思=深度思考，文=文本生成，多=多模态理解（图/视频/文档），定=视觉定位，GUI=GUI 任务，工=工具调用，结=结构化输出（`(js)` = 文档特别标注"推荐使用 `json_schema` 模式"）。

| Model ID | 能力 | 上下文 | 最大输入 | 最大输出 | 最大思维链 | RPM / TPM | 状态 |
|---|---|---|---|---|---|---|---|
| `doubao-seed-evolving` | 思 文 多 工 结(js) | 1024k | 1024k | 256k | 256k | 500 / 1,000,000 | **推荐**；快速迭代模型，无日期版本 |
| `doubao-seed-2-1-pro-260628` | 思 文 多 工 结(js) | 256k | 256k | 256k | 256k | 500 / 1,000,000 | **推荐** |
| `doubao-seed-2-1-turbo-260628` | 思 文 多 工 结 | 256k | 256k | 256k | 256k | 500 / 1,000,000 | **推荐** |
| `doubao-seed-2-0-lite-260428` | 思 文 多 工 结(js) | 256k | 224k | 128k | 128k | 30000 / 5,000,000 | 往期；音频理解推荐模型 |
| `doubao-seed-2-0-mini-260428` | 思 文 多 工 结 | 256k | 224k | 128k | 128k | 30000 / 5,000,000 | 往期；音频理解推荐模型 |
| `doubao-seed-2-0-pro-260215` | 思 文 多 定 工 结 | 256k | 224k | 128k | 128k | 30000 / 5,000,000 | 往期 |
| `doubao-seed-2-0-lite-260215` | 思 文 多 定 工 结 | 256k | 224k | 128k | 128k | 30000 / 5,000,000 | 往期 |
| `doubao-seed-2-0-mini-260215` | 思 文 多 定 工 结 | 256k | 224k | 128k | 128k | 30000 / 5,000,000 | 往期 |
| `doubao-seed-2-0-code-preview-260215` | 思 文 多 定 工 | 256k | 224k | 128k | 128k | 30000 / 5,000,000 | 往期；无结构化输出 |
| `doubao-seed-character-260628` | 思 文 多 工 结(js) | 128k | 96k | 32k | 128k | 30000 / 5,000,000 | 角色扮演 |
| `doubao-seed-character-251128` | 文 工 | 128k | 96k | 32k | — | 30000 / 5,000,000 | 角色扮演，无思考 |
| `doubao-seed-translation-250915` | 文（翻译增强） | 4k | 1k | 3k（默认 3k） | — | 5000 / 500,000 | 翻译专用 |
| `doubao-seed-1-8-251228` | 思 文 多 定 工 结 | 256k | 224k | 32k | 32k | 30000 / 5,000,000 | `即将下线` |
| `doubao-seed-code-preview-251028` | 思（编程增强）文 多 定 工 | 256k | 224k | 32k | 32k | 5000 / 1,200,000 | `即将下线` |
| `doubao-seed-1-6-251015` | 思 文 多 定 工 结 | 256k | 224k | 32k | 32k | 30000 / 5,000,000 | `即将下线` |
| `doubao-seed-1-6-250615` | 思 文 多 定 工 结 | 256k | 224k | 32k | 32k | 30000 / 5,000,000 | `即将下线` |
| `doubao-seed-1-6-flash-250828` | 思 文 定 多 工 结 | 256k | 224k | 32k | 32k | 30000 / 5,000,000 | `即将下线` |
| `doubao-seed-1-6-flash-250615` | 思 文 定 多 工 结 | 256k | 224k | 32k | 32k | 30000 / 5,000,000 | `即将下线` |
| `doubao-seed-1-6-vision-250815` | 思 文 多 定 GUI 工 结 | 256k | 224k | 32k | 32k | 30000 / 5,000,000 | `即将下线`；GUI 任务处理唯一推荐模型 |
| `doubao-1-5-pro-32k-250115` | 文 工（仅 Chat API） | 128k | — | 16k | — | 30000 / 5,000,000 | `即将下线` |
| `doubao-1-5-pro-32k-character-250715` | 文（角色扮演增强，仅 Chat API） | 32k | — | 12k | — | 15000 / 10,000,000 | `即将下线` |
| `doubao-1-5-lite-32k-250115` | 文 工（仅 Chat API） | 32k | — | 12k | — | 30000 / 5,000,000 | `即将下线` |
| `doubao-1-5-vision-pro-32k-250115` | 图片理解 工（仅 Chat API） | 32k | — | 12k | — | 30000 / 5,000,000 | `即将下线` |
| `glm-5-2-260617` | 思 文 工 | 1024k | 1024k | 128k | 128k | 500 / 1,000,000 | 无多模态、无结构化输出 |
| `glm-4-7-251222` | 思 文 工 | 200k | 200k | 128k | 128k | 15000 / 1,500,000 | `即将下线` |
| `deepseek-v4-pro-ga-260813` | 思 文 工 结 | 1024k | 1024k | 384k | 128k | 500 / 1,000,000 | 正式版 |
| `deepseek-v4-flash-ga-260731` | 思 文 工 结 | 1024k | 1024k | 384k | 128k | 500 / 1,000,000 | 正式版 |
| `deepseek-v4-pro-260425` | 思 文 工 | 1024k | 1024k | 384k | 128k | 15000 / 1,500,000 | 预览版，无结构化输出 |
| `deepseek-v4-flash-260425` | 思 文 工 | 1024k | 1024k | 384k | 128k | 15000 / 1,500,000 | 预览版，无结构化输出 |

补充：
- 文档把"文本生成能力"页签定义为"支持**无深度思考**的文本生成任务的模型"，上表所有带"思"的模型都同时出现在深度思考与文本生成两个页签下，即都支持关闭思考进行纯文本生成；⚠ 各模型默认思考行为文档只对个别模型说明，见 3.6。
- 音频理解推荐模型：仅 `doubao-seed-2-0-lite-260428`、`doubao-seed-2-0-mini-260428`（模型发布公告：260428 版支持文本/图片/语音/视频四模态）。`doubao-seed-evolving` 明确"未支持音频理解及视频中的音频理解"。
- 视觉理解推荐模型：`doubao-seed-evolving`、`doubao-seed-2-1-pro-260628`、`doubao-seed-2-1-turbo-260628`；`doubao-1-5-vision-pro-32k-250115` 仅"图片理解"。

### 3.2 工具调用能力矩阵

模型列表页的「工具调用能力」表（函数调用 / 知识库 / MCP / 联网内容插件 / 图像处理 / 豆包助手，除函数调用外均仅 Responses API）用图标表示支持与否，抓取后单元格为空。⚠ 文档未说明（图标不可抽取），只能确认：
- 表中列出的模型 = 3.1 全部模型；`doubao-1-5-*` 四个模型的函数调用标注"仅支持 Chat API"。
- 3.1 能力列中的"工"来自各能力页签，可作为函数调用支持的依据。
- 「Agent 场景模型调用的正确姿势」把 `doubao-seed-evolving`、`doubao-seed-2-1-pro-260628`、`doubao-seed-2-1-turbo-260628`、`doubao-seed-2-0-lite-260428`（加密思维链回传）与 `doubao-seed-1-8-251228`、`doubao-seed-2-0-pro/lite/mini-260215`、`deepseek-v4-pro-260425`、`deepseek-v4-flash-260425`、`deepseek-v4-flash-ga-260731`、`glm-5-2-260617`（明文思维链回传）列为工具调用场景的模型。

### 3.3 上下文缓存支持

| Model ID | 隐式缓存（自动，不保证命中） | 显式缓存 |
|---|---|---|
| `doubao-seed-evolving`、`doubao-seed-2-1-pro-260628`、`doubao-seed-2-1-turbo-260628`、`doubao-seed-2-0-lite/mini-260428`、`doubao-seed-2-0-pro/lite/mini-260215`、`doubao-seed-2-0-code-preview-260215`、`doubao-seed-character-260628`、`glm-5-2-260617`、`deepseek-v4-pro-ga-260813`、`deepseek-v4-flash-ga-260731`、`deepseek-v4-pro-260425`、`deepseek-v4-flash-260425` | Responses API、Chat API | Responses API：前缀缓存、Session 缓存 |
| `doubao-seed-1-8-251228`、`doubao-seed-1-6-*`（含 flash/vision）、`glm-4-7-251222` | 仅 Batch API | Responses API：前缀缓存、Session 缓存 |
| `doubao-seed-code-preview-251028` | 仅 Chat API | Responses API：前缀缓存、Session 缓存 |
| `doubao-seed-character-251128` | – | Responses API：前缀缓存、Session 缓存 |
| `doubao-1-5-pro-32k-250115`、`doubao-1-5-pro-32k-character-250715`、`doubao-1-5-lite-32k-250115` | 仅 Batch API | Context API：前缀缓存、Session 缓存的 rolling_tokens 模式 |

Batch 支持：模型列表页没有独立的 Batch 列；上表"Batch API"出现在隐式缓存列，价格页「批量推理」表列出了有批量单价的模型（见 4.3），可作为 Batch 支持依据。

### 3.4 结构化输出（beta）

推荐：`doubao-seed-evolving`、`doubao-seed-2-1-pro-260628`、`doubao-seed-2-1-turbo-260628`、`doubao-seed-2-0-lite-260428`、`doubao-seed-2-0-mini-260428`。往期：`doubao-seed-2-0-pro/lite/mini-260215`、`doubao-seed-1-8-251228`、`doubao-seed-1-6-vision-250815`、`doubao-seed-1-6-flash-250828/250615`、`doubao-seed-1-6-250615/251015`、`doubao-seed-character-260628`、`deepseek-v4-pro-ga-260813`、`deepseek-v4-flash-ga-260731`。不支持：`glm-*`、`deepseek-v4-*-260425` 预览版、`*-code-preview-*`、`doubao-1-5-*`、`doubao-seed-character-251128`、`doubao-seed-translation-250915`。

### 3.5 视频生成 / 图片生成 / 3D / 向量化

**视频生成**（Video Generation API，异步任务）

| Model ID | 能力 | 分辨率 / 时长 / 格式 | 在线限流 | 离线 |
|---|---|---|---|---|
| `doubao-seedance-2-5-260628` | 全模态参考生视频（参考生 / 编辑 / 延长）、首尾帧、首帧、文生视频 | 480p、720p（8bit）、1080p（10bit）；24fps；4–30 秒；mp4、mov | RPM 企业 600 / 个人 180；并发 企业 10 / 个人 3 | 暂不支持 |
| `doubao-seedance-2-0-260128` | 同上 | 480p、720p、1080p（8bit）、4k（10bit）；24fps；4–15 秒；mp4 | 非 4k：RPM 600/180，并发 10/3；4k：RPM 15，并发 1 | 暂不支持 |
| `doubao-seedance-2-0-fast-260128` | 同上 | 480p、720p；24fps；4–15 秒；mp4 | RPM 600/180；并发 10/3 | 暂不支持 |
| `doubao-seedance-2-0-mini-260615` | 同上 | 480p、720p；24fps；4–15 秒；mp4 | RPM 600/180；并发 10/3 | 暂不支持 |
| `doubao-seedance-1-5-pro-251215` `即将下线` | 首尾帧、首帧、文生视频 | 480p/720p/1080p；24fps；4–12 秒；mp4 | RPM 600；并发 10 | TPD 5000 亿 |
| `doubao-seedance-1-0-pro-250528` | 首尾帧、首帧、文生视频 | 480p/720p/1080p；24fps；2–12 秒；mp4 | RPM 600；并发 10 | TPD 5000 亿 |
| `doubao-seedance-1-0-pro-fast-251015` | 首帧、文生视频 | 480p/720p/1080p；24fps；2–12 秒；mp4 | RPM 600；并发 10 | TPD 5000 亿 |

**图片生成**（Image generation API，限流单位 IPM 张/分钟）

| Model ID | 能力 | IPM |
|---|---|---|
| `doubao-seedream-5-0-pro-260628` | 图层拆分；单图生成（文生图 / 单张图生图 / 多参考图生图） | 500 |
| `doubao-seedream-5-0-260128`（同时支持 `doubao-seedream-5-0-lite-260128`） | 单图生成 + 组图生成（文生组图 / 单张图生组图 / 多参考图生组图） | 500 |
| `doubao-seedream-4-5-251128` | 单图 + 组图 | 500 |
| `doubao-seedream-4-0-250828` | 单图 + 组图 | 500 |

**3D 生成**

| Model ID | 能力 | 产物 | 限流 | 免费额度 |
|---|---|---|---|---|
| `doubao-seed3d-2-0-260328` | 图生 3D（带纹理 + PBR） | 面数 10 万 / 50 万 / 100 万；glb、obj、usd、usdz | RPM 300；并发 5 | 200 万 token |
| `hyper3d-gen2-260112` | 文生 / 图生 3D（白模、纹理、PBR、纹理+PBR） | 三角面 [500, 1,000,000]、四边面 [1,000, 200,000]；glb、obj、stl、fbx、usdz | RPM 60；并发 3 | 15 万 token |
| `hitem3d-2-0-251223` | 图生 3D（标准/高精 白模/纹理） | 面数 [100000, 2000000]；glb、obj、stl、fbx、usdz；分辨率 1536 / 1536 pro | RPM 600；并发 30 | 50 万 token |

**向量化**（Embeddings Multimodal API）

| Model ID | 能力 | 上下文 | 最高维度 | 限流 |
|---|---|---|---|---|
| `doubao-embedding-vision-251215` | 多模态向量化（视频、文本、图片输入） | 128k | 2048（支持 1024 降维） | RPM 15000 / TPM 1,200,000 |
| `doubao-embedding-vision-250615` | 同上 | 128k | 2048（支持 1024 降维） | RPM 15000 / TPM 1,200,000 |

`auth.md` 记录的矛盾（「兼容 OpenAI SDK」页说向量化模型不支持 OpenAI API 需用方舟 SDK，而 Plan 的 OpenClaw 配置用 `provider: openai` 调 `doubao-embedding-vision`）——**已用真实 API 验证（2026-09-04，Agent Plan Medium）：在 Plan 入口文档说法不成立，OpenAI 形态可用。**
- `POST /api/plan/v3/embeddings`，`{"model":"doubao-embedding-vision","input":"<字符串>"}` → **200**，`data[0].embedding` 为数组，默认 **2048** 维，`usage: {"prompt_tokens":20,"total_tokens":20}`；加 `"dimensions": 1024` → 1024 维，生效。
- 同一 endpoint `input` 传多模态数组 `[{"type":"text","text":"a cat"}]` → **400** `{"error":{"code":"InvalidParameter","message":"The parameter `input[0]` specified in the request are not valid: expected a string, but got `map[text:a cat type:text]` instead. ...","param":"input[0]","type":"BadRequest"}}`——OpenAI 形态只收字符串，图片必须走 multimodal。
- `POST /api/plan/v3/embeddings/multimodal` → 200，响应 `model: "doubao-embedding-vision-251215"`，**`data.embedding` 是对象下的数组（`data` 不是数组）**，2048 维，`usage.prompt_tokens_details: {"text_tokens":20,"image_tokens":0}`。
- 文档里多模态向量化默认维度写法不一（2048 / 1024 / 3072）→ 实测两条路默认都是 2048。
- 标准入口 `/api/v3/embeddings` 是否接受 OpenAI 形态未测。

**语音模型**：模型列表页（1330310）没有 TTS/ASR 条目；`doubao-seed-tts-2.0`、`doubao-seed-asr-2.0` 只出现在 Agent Plan 文档中（见 5.2）。⚠ 标准 API 是否可调、Model ID 形态，本组输入文档未说明。

### 3.6 思考行为：默认是否开启、能否关闭

文档只对以下模型明确说明，其余 ⚠ 文档未说明（Coding Plan 文档：「在控制台可以查看模型在编码工具中默认的 thinking 行为，真实使用时可由编码工具通过指定参数修改」）：

| 模型 | 默认 | 能否关闭 | 备注 |
|---|---|---|---|
| `doubao-seed-evolving` | 开启（`thinking` 默认 enabled；`reasoning_effort` 默认 `high`，可选 `none/minimal/low/medium/high/xhigh/max`） | 可（`thinking: {"type":"disabled"}`） | 默认开启 thinking summary：返回摘要 + 加密原文，不返回原始思考内容 |
| `doubao-seed-2-1-pro-260628` | 快速入门示例默认带思考输出，注释给出 `thinking: {"type":"disabled"}` 手动关闭 | 可 | — |
| `doubao-seed-2.0-lite` / `doubao-seed-2.0-mini`（Agent Plan，实际 `260215`） | 「默认-thinking」——**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：lite 不传 `thinking` 时 `reasoning_content` 存在、`reasoning_tokens: 109`，默认**开** | **已用真实 API 验证**：`thinking: {"type":"disabled"}` 生效，`reasoning_tokens: 0`（lite、mini 均可关） | `max_tokens: 64` 时 `completion_tokens: 110`（思维链 109 + 回答 1）——豆包的 `max_tokens` **不**限制思维链，与文档一致 |
| `glm-5.3`（Plan） | 默认开启 | **不支持关闭**——**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`thinking: {"type":"disabled"}` → 400 `thinking.type `disabled` is not supported by this model`；`reasoning_effort: "none"` → 400 `reasoning_effort `none` is not supported by this model` | **绕法（实测）**：`reasoning_effort: "low"` → 200，`reasoning_tokens: 0`、无 `reasoning_content`，事实上等于关闭思考 |
| `deepseek-v4-flash` / `deepseek-v4-pro`（Plan） | 默认开启 | 支持手动关闭 | 模型发布公告：deepseek-v4 正式版"支持思考与非思考双模式"（未实测） |
| `kimi-k3`（Plan，Medium+） | **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：默认开（`reasoning_content` 存在，`reasoning_tokens: 61`） | 未测 | **`max_tokens` 含思维链**：`max_tokens: 64` → `finish_reason: "length"`、`content: ""`、`completion_tokens: 64`（reasoning 61）；去掉 `max_tokens` 改 `max_completion_tokens: 400` → 正常 `content: "2"`。开思考调 kimi-k3 一律用 `max_completion_tokens` |
| `kimi-k2.7-code`（Plan） | ⚠ 文档未说明 | ⚠ | 文档仅说"支持思考模式"（未实测） |

---

## 4. 后付费单价（标准 API）

来源：「模型价格」（1544106，更新 2026-08-27）。单位：元 / 百万 token；"条件"列为分段计费区间（千 token）。计费公式：`在线推理费用 = 输入(非音频)单价×输入token + 输入(音频)单价×音频token + 缓存命中单价×命中token + 缓存存储单价×存储token×时长 + 输出单价×输出token`。分段计费按**整次请求**的输入长度落在哪一档决定全部 token 单价（例：输入 200k、输出 14k → 落在 (128, 256] 档）。文档说明"本文价格仅作参考，以实际下单为准"。

### 4.1 在线推理（常规）

| 模型（价格页写法） | 条件（输入长度，千 token） | 输入 | 输入(音频) | 缓存存储（元/百万token/小时） | 缓存命中 | 缓存命中(音频) | 输出 |
|---|---|---|---|---|---|---|---|
| doubao-seed-evolving | [0, 1024] | 6.00 | – | 0.017 | 1.20 | – | 30.00 |
| doubao-seed-2.1-pro | [0, 256] | 6.00 | – | 0.017 | 1.20 | – | 30.00 |
| doubao-seed-2.1-turbo | [0, 256] | 3.00 | – | 0.017 | 0.60 | – | 15.00 |
| doubao-seed-2.0-pro | [0, 32] / (32, 128] / (128, 256] | 3.2 / 4.8 / 9.6 | – | 0.017 | 0.64 / 0.96 / 1.92 | – | 16.0 / 24.0 / 48.0 |
| doubao-seed-2.0-lite | [0, 32] / (32, 128] / (128, 256] | 0.6 / 0.9 / 1.8 | 9.0 / 13.5 / 27.0 | 0.017 | 0.12 / 0.18 / 0.36 | 1.8 / 2.7 / 5.4 | 3.6 / 5.4 / 10.8 |
| doubao-seed-2.0-mini | [0, 32] / (32, 128] / (128, 256] | 0.2 / 0.4 / 0.8 | 3.0 / 6.0 / 12.0 | 0.017 | 0.04 / 0.08 / 0.16 | 0.6 / 1.2 / 2.4 | 2.0 / 4.0 / 8.0 |
| doubao-seed-2.0-code | [0, 32] / (32, 128] / (128, 256] | 3.2 / 4.8 / 9.6 | – | 0.017 | 0.64 / 0.96 / 1.92 | – | 16.0 / 24.0 / 48.0 |
| doubao-seed-1.8 | [0,32] 且输出 [0,0.2] / [0,32] 且输出 >0.2 / (32,128] / (128,256] | 0.80 / 0.80 / 1.20 / 2.40 | – | 0.017 | 0.16 | – | 2.00 / 8.00 / 16.00 / 24.00 |
| doubao-seed-character | [0, 32] / (32, 128] | 0.80 / 1.20 | – | 0.017 | 0.16 | – | 2.00 / 6.00 |
| doubao-seed-code | [0, 32] / (32, 128] / (128, 256] | 1.20 / 1.40 / 2.80 | – | 0.017 | 0.24 | – | 8.00 / 12.00 / 16.00 |
| doubao-seed-1.6 | 同 1.8 四档 | 0.80 / 0.80 / 1.20 / 2.40 | – | 0.017 | 0.16 | – | 2.00 / 8.00 / 16.00 / 24.00 |
| doubao-seed-1.6-lite | 同 1.8 四档 | 0.30 / 0.30 / 0.60 / 1.20 | – | 0.017 | 0.06 | – | 0.60 / 2.40 / 4.00 / 12.00 |
| doubao-seed-1.6-flash | [0, 32] / (32, 128] / (128, 256] | 0.15 / 0.30 / 0.60 | – | 0.017 | 0.03 | – | 1.50 / 3.00 / 6.00 |
| doubao-seed-1.6-vision | [0, 32] / (32, 128] / (128, 256] | 0.80 / 1.20 / 2.40 | – | 0.017 | 0.16 | – | 8.00 / 16.00 / 24.00 |
| doubao-seed-translation | – | 1.20 | – | – | – | – | 3.60 |
| doubao-1.5-pro-32k | – | 0.80 | – | 0.017 | 0.16 | – | 2.00 |
| doubao-1.5-lite-32k | – | 0.30 | – | 0.017 | 0.06 | – | 0.60 |
| doubao-1.5-vision-pro | – | 3.00 | – | – | – | – | 9.00 |
| glm-5.2 | – | 8.00 | – | 0.017 | 2.00 | – | 28.00 |
| glm-4.7 | [0,32] 且输出 [0,0.2] / [0,32] 且输出 >0.2 / (32, 200] | 2.0 / 3.0 / 4.0 | – | 0.017 | 0.4 / 0.6 / 0.8 | – | 8.0 / 14.0 / 16.0 |
| deepseek-v4-pro 正式版 / 预览版 | – | 9.00 | – | 0.017 | 0.30 | – | 27.00 |
| deepseek-v4-flash 正式版 / 预览版 | – | 3.00 | – | 0.017 | 0.10 | – | 9.00 |

价格调整记录（原文）：deepseek-v4-pro 预览版 2026-08-28 起由 12/1/24 上调为 9/0.3/27（输入/命中/输出）；deepseek-v4-flash 预览版 2026-08-28 起由 1/0.2/2 上调为 3/0.1/9；deepseek-v4-flash 正式版 2026-08-21 起由 1/0.2/2 上调为 3/0.1/9。思考 token：价格页无单独"思考 token"列；「Agent 场景」页说明"输出思考内容部分计费会按原始思考内容 token 计算"，即思维链按**输出**单价计费。

### 4.2 在线推理（低延迟，Beta）

| 模型 | 条件 | 输入 | 输入(音频) | 缓存命中 | 缓存命中(音频) | 输出 |
|---|---|---|---|---|---|---|
| doubao-seed-2.1-turbo | [0, 256] | 6.00 | – | 1.20 | – | 30.00 |
| doubao-seed-2.0-pro | [0,32] / (32,128] / (128,256] | 9.6 / 14.4 / 28.8 | – | 1.92 / 2.88 / 5.76 | – | 48.0 / 72.0 / 144.0 |
| doubao-seed-2.0-lite | 同上三档 | 1.2 / 1.8 / 3.6 | 18.0 / 27.0 / 54.0 | 0.24 / 0.36 / 0.72 | 3.6 / 5.4 / 10.8 | 7.2 / 10.8 / 21.6 |
| doubao-seed-2.0-mini | 同上三档 | 0.4 / 0.8 / 1.6 | 6.0 / 12.0 / 24.0 | 0.08 / 0.16 / 0.32 | 1.2 / 2.4 / 4.8 | 4.0 / 8.0 / 16.0 |

即低延迟约为常规价的 2 倍。

### 4.3 批量推理（约为常规价一半，天级延迟）

| 模型 | 条件 | 输入 | 输入(音频) | 缓存命中 | 缓存命中(音频) | 输出 |
|---|---|---|---|---|---|---|
| doubao-seed-2.1-pro | [0, 256] | 3.00 | – | 1.20 | – | 15.00 |
| doubao-seed-2.1-turbo | [0, 256] | 1.50 | – | 0.60 | – | 7.50 |
| doubao-seed-2.0-pro | 三档 | 1.6 / 2.4 / 4.8 | – | 0.64 / 0.96 / 1.92 | – | 8.0 / 12.0 / 24.0 |
| doubao-seed-2.0-lite | 三档 | 0.3 / 0.45 / 0.9 | 4.5 / 6.75 / 13.5 | 0.12 / 0.18 / 0.36 | 1.8 / 2.7 / 5.4 | 1.8 / 2.7 / 5.4 |
| doubao-seed-2.0-mini | 三档 | 0.1 / 0.2 / 0.4 | 1.5 / 3.0 / 6.0 | 0.04 / 0.08 / 0.16 | 0.6 / 1.2 / 2.4 | 1.0 / 2.0 / 4.0 |
| doubao-seed-2.0-code | 三档 | 1.6 / 2.4 / 4.8 | – | 0.64 / 0.96 / 1.92 | – | 8.0 / 12.0 / 24.0 |
| doubao-seed-1.8 / 1.6 | 四档 | 0.40 / 0.40 / 0.60 / 1.20 | – | 0.16 | – | 1.00 / 4.00 / 8.00 / 12.00 |
| doubao-seed-1.6-vision | 三档 | 0.40 / 0.60 / 1.20 | – | 0.16 | – | 4.00 / 8.00 / 12.00 |
| doubao-seed-1.6-lite | 四档 | 0.15 / 0.15 / 0.30 / 0.60 | – | 0.06 | – | 0.30 / 1.20 / 2.00 / 6.00 |
| doubao-seed-1.6-flash | 三档 | 0.075 / 0.150 / 0.300 | – | 0.03 | – | 0.75 / 1.50 / 3.00 |
| doubao-seed-translation | – | 0.60 | – | 0.24 | – | 1.80 |
| doubao-1.5-pro-32k / lite-32k / doubao-pro-32k | – | 0.40 / 0.15 / 0.80 | – | 0.16 / 0.06 / 0.16 | – | 1.00 / 0.30 / 2.00 |
| glm-4.7 | 三档 | 1.00 / 1.50 / 2.00 | – | 0.40 / 0.60 / 0.80 | – | 4.00 / 7.00 / 8.00 |
| deepseek-v4-pro 正式版 / 预览版 | – | 4.50 | – | 0.30 | – | 13.50 |
| deepseek-v4-flash 正式版 / 预览版 | – | 1.50 | – | 0.10 | – | 4.50 |

注意：`doubao-seed-evolving`、`glm-5.2` **没有**批量推理单价（不在批量表中）。

### 4.4 在线推理（TPM 保障包）

仅老模型：doubao-seed-1.8 / 1.6 / 1.6-vision / 1.5-pro-32k / pro-32k：按购买时长后付费 输入 1.920 元/每 10K TPM/小时、输出 0.480 元/每 1K TPM/小时；包天预付费 23.040 / 5.760 元/天。doubao-seed-1.6-flash（0615 版不支持）0.360 / 0.360 元/小时，包天 4.320 / 4.320。doubao-1.5-vision-pro 7.200 / 2.160，包天 86.400 / 25.920。doubao-1.5-lite-32k 0.72 / 0.144，包天 8.64 / 1.728。支持模型以接入点创建页可选付费方式为准；seed-1.6 系列及之后"不同长度请求抵扣 TPM 速度不同"。

### 4.5 视频生成（按 token）

`视频价格 = token 单价 × token 用量`；`token 用量 ≈ (输入视频时长 + 输出视频时长) × 宽 × 高 × 帧率 / 1024`；准确用量以返回的 `usage.completion_tokens` 为准；仅对成功生成的视频计费。Seedance 2.0 系列 / 2.5 输入含视频时有最低 token 用量限制（与分辨率、宽高比、时长有关，文档给出外链表格）。

| 模型 | 在线推理 元/百万 token | 离线 |
|---|---|---|
| doubao-seedance-2.5 | 480p/720p：不含输入视频 70.00，含 42.00；1080p：不含 77.00、含 46.00（2026-08-14 14:00 至 09-17 14:00 限时 72 折） | 暂不支持 |
| doubao-seedance-2.0 | 480p/720p：46.00 / 28.00；1080p：51.00 / 31.00；4k：26.00 / 16.00（前者不含输入视频，后者含） | 暂不支持 |
| doubao-seedance-2.0-fast | 480p/720p：37.00 / 22.00（2026-08-07 至 09-07 限时 75 折） | 暂不支持 |
| doubao-seedance-2.0-mini | 480p/720p：23.00 / 14.00（2026-08-07 至 09-07 限时 4 折） | 暂不支持 |
| doubao-seedance-1.5-pro | 有声 16.00 / 无声 8.00（Draft 样片模式 token 折算系数：无声 0.7、有声 0.6） | 8.00 / 4.00 |
| doubao-seedance-1.0-pro | 15.00 | 7.50 |
| doubao-seedance-1.0-pro-fast | 4.20 | 2.10 |

价格示例（16:9、5 秒、不含输入视频，元/个）：Seedance 2.5 480p 3.36、720p 7.56、1080p 18.71；Seedance 2.0 480p 2.31、720p 4.97、1080p 12.39、4k 25.27；2.0-fast 480p 1.86、720p 4.00；2.0-mini 480p 1.16、720p 2.48；1.5-pro 有声 480p 0.80、720p 1.73、1080p 3.89。含输入视频（2–30 秒输入）Seedance 2.5 720p 8.16–31.75 元/个。版权 IP 生视频（仅体验中心）×1.1 或 ×1.5。

### 4.6 图片生成（按张）

| 模型 | 输入图单价（元/张） | 输出图单价（元/张） |
|---|---|---|
| doubao-seedream-5-0-pro | 首张免费，第 2 张起 0.02 | 单图生成：≤261 万像素（≤1.5K）0.30，>261 万像素 0.60；图层拆分：0.15 / 0.30（每个图层按实际像素档单独计费） |
| doubao-seedream-5-0-lite | 免费 | 0.22 |
| doubao-seedream-4-5 | 免费 | 0.25 |
| doubao-seedream-4-0 | 免费 | 0.20 |

审核失败未输出的图片不计费；组图场景按实际生成张数计费。

### 4.7 3D 生成（按次）

doubao-seed3d-2.0 2.40 元/次（3.00 万 token × 0.80 元/万 token）；Hyper3d-Gen2 1.80 元/次（有资源包：300 万 token 150 元 ≈ 1.5 元/次，3000 万 token 1000 元 ≈ 1 元/次）；Hitem3d-2.0 标准白模 5.80、标准纹理 10.15、高精白模 8.70、高精纹理 13.05 元/次。按成功输出文件数计费。

### 4.8 向量化

doubao-embedding-vision：文本输入 0.70 元/百万 token，图片输入 1.80 元/百万 token。`费用 = 文本 tokens × 0.70 + min(width×height/784, 1312) × 1.80`（图片 token 数公式，文档原文）。

### 4.9 套餐售价（价格页）

| 套餐 | 价格页（1544106，2026-08-27） | 控制台实读（2026-09-03） |
|---|---|---|
| Coding Plan Lite | 40 元/月、120 元/季 | 9.9 元/月 |
| Coding Plan Pro | 200 元/月、600 元/季 | 49.9 元/月（已售罄） |
| Agent Plan Small / Medium / Large / Max | 40 / 200 / 500 / 1000 元/月 | 同（Medium 200 元/月，控制台可见） |

⚠ 文档自相矛盾：Coding Plan 价格页与控制台售卖页不一致（可能是活动价 vs 刊例价，文档未说明）。

---

## 5. Plan 内可用模型对照表（Model Name）

### 5.1 Coding Plan（Lite / Pro 同一套模型）

来源：「套餐概览」（1925114）+ 控制台实读。Coding Plan 支持语言模型 + `doubao-embedding-vision`，**无**图片 / 视频 / 语音模型，**无** `kimi-k3`、**无** `doubao-seed-2.0-mini`（控制台列表）。所有 Model Name 小写。

| Model Name | 文档说明 | 上下文 / 最大输出 | 备注 |
|---|---|---|---|
| `Auto`（`ark-code-latest` 默认） | 智能调度，「效果 + 速度」双维度匹配，可优先体验最新模型 | – | 2026-06-10 18:00 至 11-08 活动期 Coding Plan 内抵扣系数 1 |
| `doubao-seed-evolving` | Coding & Agent，周级升级，1M 上下文 | 1024k / 256k | 2026-08-21 上线 Coding Plan |
| `doubao-seed-2.1-turbo` | 多模态视觉理解，复杂推理与长链路任务 | 256k / **64k**（⚠ 文档自相矛盾：标准 API 模型列表与 Agent Plan 页均为 256k） | — |
| `doubao-seed-2.0-lite` | 多模态视觉理解，通用生产级 | ⚠ 未在 Coding Plan 页给出（Agent Plan 页：256k / 128k） | — |
| `minimax-m3` | 多模态视觉理解，Agent 推理 / 工具调用 / 代码 / 长上下文 | 1024k / 128k | `minimax-latest` |
| `kimi-k2.7-code` | 文本 / 图片 / 视频输入，思考模式 | 256k / 32k（含思维链） | `kimi-latest` |
| `glm-5.3`（`glm-latest`） | 旗舰，编程与安全，1M 上下文 | 1024k / 128k | 抵扣系数高，推荐重难点问题；**默认开启思考且不支持关闭** |
| `glm-5.3-flash` | 首个原生多模态，支持图片输入 | 1024k / 128k | 2026-08-28 上线；08-28 至 09-11 抵扣系数 5 折 |
| `deepseek-v4-flash` | 快捷经济，默认开启思考，支持关闭 | 1024k / 384k | 正式版 2026-08-07 全量 |
| `deepseek-v4-pro`（`deepseek-latest`） | Agent 能力强，默认开启思考，支持关闭 | 1024k / 384k | 正式版 2026-08-26 上线；抵扣系数高 |
| `doubao-embedding-vision` | Embedding，为工具提供语义向量 | 128k | 2026-03-31 上线 |

Coding Plan 额度按"次数"估算而非 AFP（文档：用量因上下文长度、模型、是否开 thinking 波动大；Agent Team 模式消耗显著增加）。5 小时 / 周 / 月三级限额；⚠ 各模型具体抵扣系数 Coding Plan 页未给数值（只说 glm-5.3、deepseek-v4-pro "抵扣系数较高"）。1M 上下文可用于 `doubao-seed-evolving`、`glm-5.3`、`glm-5.3-flash`、`deepseek-v4-flash`、`deepseek-v4-pro`，需在工具中开启。

### 5.2 Agent Plan（Small / Medium / Large / Max 逐档）

来源：「套餐概览」（2366394）、「套餐内 AFP 抵扣规则」（2516283）、「超额后付费规则」（2516284）、控制台实读。

| 分类 | Model Name | 上下文 / 最大输出 | Small | Medium | Large | Max | AFP 输入 / 输出系数 | 超额后付费 |
|---|---|---|---|---|---|---|---|---|
| 文本（极速） | `doubao-seed-2.0-mini` | 256k / 128k | √ | √ | √ | √ | 0.25 / 0.25 | √（按在线推理常规价） |
| 文本（标准） | `doubao-seed-2.0-lite` | 256k / 128k | √ | √ | √ | √ | 0.5 / 0.5 | √ |
| 文本（标准） | `deepseek-v4-flash` | 1024k / 384k | √ | √ | √ | √ | 0.5 / 0.5 | √ |
| 文本（标准） | `glm-5.3-flash`（支持图片输入） | 1024k / 128k | √ | √ | √ | √ | 0.5 / 0.5（08-28 至 09-11 为 0.25） | × |
| 文本（进阶） | `doubao-seed-2.1-turbo` | 256k / 256k | √ | √ | √ | √ | 2.5 / 2.5 | √ |
| 文本（进阶） | `doubao-seed-evolving` | 1024k / 256k | √ | √ | √ | √ | 2.5 / 2.5 | √ |
| 文本（进阶） | `minimax-m3` | 1024k / 128k | √ | √ | √ | √ | 2.5 / 2.5 | × |
| 文本（进阶） | `kimi-k2.7-code` | 256k / 32k | √ | √ | √ | √ | 4.5 / 4.5 | ⚠ 2516284 表中未列出 |
| 文本（进阶） | `glm-5.3`（`glm-latest`，默认开思考不可关） | 1024k / 128k | √ | √ | √ | √ | 4.5 / 4.5 | × |
| 文本（进阶） | `deepseek-v4-pro` | 1024k / 384k | √ | √ | √ | √ | 5.5 / 5.5 | √ |
| 文本（进阶） | `kimi-k3`（原生视觉，1M） | 1024k / 128k | **×** | √（**已用真实 API 验证（2026-09-04）**：Medium 档 200，响应 `"model":"kimi-k3"`） | √ | √ | 10 / 10 | × |
| 路由 | `auto`（控制台 `ark-code-latest` 默认） | – | √ | √ | √ | √ | 活动期（2026-06-10 至 11-08）0.5，可路由到 kimi-k3，夜间 00:00–8:00 kimi-k3 比例大幅提升 | **×**（原文：auto 模式不支持超额后付费）。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`model: "auto"` 直接填 → 404 UnsupportedModel；必须填 `ark-code-latest`（响应 `"model":"auto"`），见 1.1.1 |
| 向量化 | `doubao-embedding-vision` | 128k | √ | √ | √ | √ | 0.5 / 0.5 | √（按向量模型价） |
| 图片生成 | `doubao-seedream-5.0-lite` | – | √ | √ | √ | √ | 99 AFP / 张 | × |
| 视频生成 | `doubao-seedance-1.5-pro` `即将下线` | – | × | √ | √ | √ | 无声 36 / 有声 72（每万 token） | × |
| 视频生成 | `doubao-seedance-2.0` | – | × | × | √ | √ | 480p/720p：含输入视频 140 / 不含 230；1080p：155 / 255；4k：80 / 130（每万 token） | × |
| 视频生成 | `doubao-seedance-2.0-fast` | – | × | × | √ | √ | 含输入视频 110 / 不含 185 | × |
| 视频生成 | `doubao-seedance-2.0-mini` | – | × | ×（**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`POST /api/plan/v3/contents/generations/tasks` → 404 UnsupportedModel，文案与套餐外模型相同） | √ | √ | 含输入视频 70 / 不含 115 | × |
| 语音 | `doubao-seed-tts-2.0` | – | √ | √ | √ | √ | 1350 / 万字符 | √（3 元/万字符） |
| 语音 | `doubao-seed-asr-2.0` | – | √ | √ | √ | √ | 450 / 小时 | √（1 元/小时） |

AFP 公式：文本/向量化 `(输入token×输入系数 + 输出token×输出系数)/10,000`；视频 `token/10,000×系数`；图片 `张数×系数`；TTS `字符数/10,000×1350`；ASR `小时×450`。文本模型系数不随输入长度变化。示例（文档原文）：`doubao-seed-2.1-turbo` 输入 50k、输出 0.5k → `(50000×2.5+500×2.5)/10000 = 12.625 AFP`。

套餐额度：

| 套餐 | 价格 | 月额度 AFP | 周额度 | 5 小时额度 | 日额度（仅图片/视频/语音/Harness） |
|---|---|---|---|---|---|
| Small | 40 元/月 | 20,000 | 7,000 | 2,000 | 10,000 |
| Medium | 200 元/月 | 100,000 | 35,000 | 10,000 | 50,000 |
| Large | 500 元/月 | 250,000 | 87,500 | 25,000 | 125,000 |
| Max | 1000 元/月 | 500,000 | 175,000 | 50,000 | 250,000 |

Harness（仅 Agent Plan）：豆包搜索 5 AFP/次（每月 500 次免费，超额后付费 0.020 元/次）；专业数据集 12 AFP/次（学术 24；超额 0.024 / 0.048 元/次）；Agent 记忆前 50 文件免费、之后 5 AFP/小时；Agent 进化 250 AFP/百万 token（不支持超额后付费）；AI Native 应用开发底座按量折算。

### 5.3 Plan 内 vs 后付费成本对比（按文档数字推算，非文档原文）

以 Medium（200 元 = 100,000 AFP → 0.002 元/AFP，满额使用）为例：文档示例请求（`doubao-seed-2.1-turbo`，输入 50k + 输出 0.5k）套餐内消耗 12.625 AFP ≈ 0.025 元；同一请求走标准 API 后付费 = 50k×3/1M + 0.5k×15/1M ≈ 0.158 元，约 6 倍。`doubao-seed-2.0-lite` 系数 0.5：1M 输入 token 仅 50 AFP ≈ 0.1 元，后付费 0.6 元起。反向：`kimi-k3` 系数 10，Medium 月额度 100,000 AFP 只够 1 亿 token（输入+输出合计）。结论：套餐额度用不完时 Plan 明显更便宜；但 Plan 有 5 小时 / 周额度墙，且**文本模型官方口径不可用于 API 调用**（见 5.4）。

### 5.4 Plan 使用限制（影响选型）

- Coding Plan：「套餐额度仅在 AI 编程工具中生效，不可用于 API 调用」，在非 AI 编程工具中使用可能被识别为滥用导致订阅停用或封号；企业级需求走标准 API。
- Agent Plan：「文本生成模型及向量化模型不可用于 API 调用」（同样的滥用条款）；图片 / 视频 / 语音模型则通过「接入视觉模型」「接入语音模型」页面的 API 方式调用。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：技术上 `/api/plan/v3/chat/completions`、`/responses`、`/embeddings` 用专属 Key 直接调都是 200——这条是**使用条款**限制而非接口限制，在非 AI 工具场景大量直调有被判滥用停用的风险，本次验证仅做了 2,000 token 级的探测。
- Agent Plan 开启超额后付费后：文本/向量化模型触达 5 小时 / 周 / 月任一限额即自动切到后付费（无需改 Base URL、Key、模型名），额度刷新后自动切回；语音模型与 Harness 无 5 小时/周限额，仅月限额触发。
- Small / Medium 不支持视频生成（文档建议选 Large / Max）；`kimi-k3` Small 不可用。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Medium 提交 `doubao-seedance-2.0-mini` 视频任务 → 404 UnsupportedModel（同套餐外模型文案，没有专门的"档位不够"错误码）；套餐概览表里 Medium 档 `doubao-seedance-1.5-pro` 打 √ 与正文矛盾，1.5-pro 未测（即将下线）。Medium 图片生成 `doubao-seedream-5.0-lite` 实测可用（`size` 须为 `WIDTHxHEIGHT` / `2k` / `3k` / `4k`，`1K` 报 400；详见 `image-video.md`）。
- TPM：Small 建议单项目、Medium 1–2 项目、Large/Max 2+ 项目；超高 TPM 用后付费 API。

---

## 6. 选型建议

### 6.1 按场景速查（标准 API）

| 我想… | 首选 | 备选 / 说明 |
|---|---|---|
| Coding / Agent，要最新能力、不想追版本 | `doubao-seed-evolving`（1M 上下文，256k 输出，周级更新自动生效） | 用它必须**回传思考内容加密原文**（Chat API `encrypted_content`；Responses API `previous_response_id` + `store: true` 或 `include: ["reasoning.encrypted_content"]`；Anthropic 兼容 `thinking.signature`），否则效果下降且不报错 |
| 高复杂度 Coding / 长链路 Agent，稳定版本 | `doubao-seed-2-1-pro-260628` | 与 evolving 同价（6 / 30 元）；有 Batch 半价 |
| 规模化生产、成本吞吐优先，效果比肩 pro | `doubao-seed-2-1-turbo-260628`（3 / 15 元，Batch 1.5 / 7.5） | 唯一有低延迟档的 2.1 系列 |
| 多模态含**音频**理解 | `doubao-seed-2-0-lite-260428` / `-mini-260428` | 2.1 系列与 evolving 不支持音频 |
| 低时延高并发、成本敏感 | `doubao-seed-2-0-mini-260428`（0.2 / 2.0 元起） | 系数 0.25，Plan 内最便宜 |
| 1M 上下文 + 结构化输出，开源模型 | `deepseek-v4-flash-ga-260731`（3 / 9 元）、`deepseek-v4-pro-ga-260813`（9 / 27 元） | 预览版 `-260425` 无结构化输出、RPM 更高（15000） |
| 长程自主编码，开源 | `glm-5-2-260617`（8 / 28 元，1M） | 无多模态、无结构化输出、无 Batch |
| GUI Agent（桌面/手机自动化） | `doubao-seed-1-6-vision-250815`（唯一 GUI 推荐模型，`即将下线`） | ⚠ 替代模型文档未说明 |
| 翻译 | `doubao-seed-translation-250915`（1.2 / 3.6 元；上下文 4k、输入 1k） | — |
| 角色扮演 | `doubao-seed-character-260628`（含思考、多模态） | `-251128` 无思考版 |
| 视觉定位 Grounding | `doubao-seed-2-0-pro/lite/mini-260215`、`doubao-seed-1-8-251228`、1.6 系列 | 260428 版与 2.1 系列能力表未标"视觉定位" |
| 视频生成 | `doubao-seedance-2-5-260628`（30 秒、1080p 10bit、mp4/mov） | 4k 只有 `doubao-seedance-2-0-260128`；低成本 `-2-0-mini-260615` |
| 图片生成 | `doubao-seedream-5-0-pro-260628`（图层拆分、精准定位、14 语言文字） | 组图用 `doubao-seedream-5-0-260128`（≡ `-lite`，0.22 元/张） |
| 向量化 | `doubao-embedding-vision-251215`（2048 维，可降 1024） | — |
| 不确定选哪个、想自动降本 | 智能模型路由接入点（ep）：新版"基线模型智能降本/增效"，备选集 `doubao-seed-2-0-pro-260215`、`doubao-seed-2-0-lite-260215` | 仅 Chat API、<32k 纯文本、不支持缓存与 `tool_choice`/`parallel_tool_calls`/`stop`/`logprobs`/`logit_bias`/`top_logprobs` |

### 6.2 Agent 场景调用姿势（2636748，直接影响选型后的效果）

| 项 | 推荐 | 错误后果 |
|---|---|---|
| 回传思考内容 | **加密原文**模型：`doubao-seed-evolving`、`doubao-seed-2-1-pro-260628`、`doubao-seed-2-1-turbo-260628`、`doubao-seed-2-0-lite-260428` → 原样回传 `encrypted_content`（Chat）/ `output[reasoning].encrypted_content`（Responses，需 `include`）/ `content[thinking].signature`（Anthropic）。**明文**模型：`doubao-seed-1-8-251228`、`doubao-seed-2-0-pro/lite/mini-260215`、`deepseek-v4-pro/flash-260425`、`deepseek-v4-flash-ga-260731`、`glm-5-2-260617` → 回传 `reasoning_content` / `summary[].text` / `thinking.thinking` | 多轮工具调用效果随轮数下降；篡改加密块返回 `Invalid signature`（文档原文，未实测）；不回传不报错但效果下降 |
| 版本升级陷阱 | `doubao-seed-2.0-lite-260215` 明文回传，`-260428` 起改加密块；升级版本必须同步改代码，**不会触发 API 报错** | 回传失效 |
| `max_tokens` / `max_output_tokens` | 必须显式传，Agent 场景 ≥ 128000（受模型最大输出限制） | `finish_reason`/`stop_reason` = `length`，工具参数 JSON 截断 |
| `thinking` | 显式 `{"type":"enabled"}`，不要用 `auto` | auto 下可能跳过规划 |
| `reasoning_effort` | `high` 或以上（Chat `reasoning_effort`；Responses `reasoning.effort`；Anthropic `output_config.effort`） | 工具选择/参数错误率上升 |
| `temperature` / `top_p` | 1 / 0.95 | 工具调用稳定性下降 |
| 缓存 | System Prompt 与工具定义放最前，同一 Session 内不改 thinking / effort / 采样参数 / System Prompt / 工具定义 | Prefix Cache 重置，成本上升 |
| Responses API 手动回传 | reasoning item 的 `id` 原样带回；`content` 可为 `[]` 但 `encrypted_content` 不能空；最后一条 user 之后的所有 item 按原顺序全带回 | 校验失败 |
| 流式（Chat） | 加密块由独立 chunk 下发（`content`、`reasoning_content` 可能均为空），合并逻辑必须处理 `delta.encrypted_content` | 丢加密块 |

### 6.3 Seed-Evolving 专项（2549861）

- 统一 Model ID `doubao-seed-evolving`，版本升级自动生效，无需迁移 Endpoint；最近版本更新 2026/08/27（8 月内两次更新，7 月支持 1M 上下文）。模型发布公告：「每周至少发布一个版本更新」。
- 长度：上下文 1024k、最大输入 1024k、最大思维链 256k、最大输出 256k；限流 RPM 500、TPM 1,000,000。
- 图片理解 `detail`：`low` [1, 1280] token / 像素 [1764, 2257920]；`high`（默认）1280 token / 2257920 像素；`xhigh` [1280, 5120] token / [2257920, 9031680] 像素。视频理解用 fps 控制精细度；>10MB 文件用 Files API。
- 工具调用开思考后不直接丢弃思维链，思维链参与后续轮次，输入 token 会增加；方舟在新问题开始时自行删除旧思维链。
- 隐式缓存默认开启（Responses、Chat）；显式缓存仅 Responses（前缀、Session）。
- 兼容 OpenAI 与 Anthropic 协议，可接 Claude Code / OpenCode / Codex。
- 模型迁移：官方提供 `ark-docs-assistant` Skill（需 `ark-docs-mcp`）做升级/迁移分析。

### 6.4 Plan 内选型（Coding Plan / Agent Plan）

- 日常：`doubao-seed-2.0-lite`（0.5）、`deepseek-v4-flash`（0.5）、`glm-5.3-flash`（0.5，活动 0.25）；最省：`doubao-seed-2.0-mini`（0.25，仅 Agent Plan）。
- 重难点：`glm-5.3`（4.5）、`deepseek-v4-pro`（5.5）、`kimi-k3`（10，Medium+）——文档明说"抵扣系数较高，额度消耗较快，推荐用于重难点复杂问题，日常建议切换其他模型"。
- 追新：`doubao-seed-evolving`（2.5）；均衡：`doubao-seed-2.1-turbo`（2.5）。
- 避免旧版本下线影响：配置 `ark-code-latest`（控制台切模型，不改配置文件）或 `glm-latest` / `minimax-latest` / `kimi-latest` / `deepseek-latest`（`glm-latest`、`ark-code-latest` 已实测可用，见 1.1.1）。
- 用 Anthropic 协议工具（Claude Code 等）接 Plan：**必须显式设模型**为套餐内 Model Name，`claude-*` 会被静默路由到 `doubao-seed-2.1-turbo`（系数 2.5），见 1.1.1。
- 开思考调 `kimi-k3`：用 `max_completion_tokens` 而不是 `max_tokens`（后者含思维链会把回答截空，见 3.6）。`glm-5.3` 想省思维链：`reasoning_effort: "low"`（实测 0 思维链）。
- 需要"套餐用完继续用不中断"：只选支持超额后付费的模型（doubao 系列、deepseek 系列、embedding、TTS/ASR）；`glm-5.3`、`glm-5.3-flash`、`minimax-m3`、`kimi-k3`、图片、视频、`auto` 都不支持。

---

## 7. 推理方式概念

来源：「推理方式概述」（2123245）、「在线推理（常规）」（2121998）。所有非常规方式都需要创建**自定义推理接入点**并用 `ep-` 调用。

| 方式 | 一句话 | 计费 | 价格档 | 适用 |
|---|---|---|---|---|
| 在线推理（常规） | 公共资源池，Model ID 直接调（预置接入点）或 ep | 按 token 后付费，不调用不计费 | 低 | 新手、个人、小业务；可接受偶发资源紧张报错 |
| 在线推理（低延迟，Beta） | 平台预留资源，更优 TPOT；可与常规组合，自动降级缓冲突增流量 | 按 token（约 2 倍常规价） | 中 | 交互延迟敏感、流量波动 |
| 在线推理（TPM 保障包） | 预留资源，保障并发达到购买的 TPM，溢出部分可叠加按 token | 按输入/输出 TPM 额度：包天预付费或按时长后付费 | 中 | 可预估的高流量、不能接受报错 |
| 模型单元 | 独占算力（A/B/C/D 型 10–25 元/小时或包月 7100–16700 元） | 按单元数：包月预付费或按时长后付费 | 高 | 全量精调模型大规模推理、高 SLA |
| 批量推理 | 天级延迟，配额高 | 按 token，常规价一半 | 最低 | 评测、批量回归、离线处理 |
| 智能模型路由 | 按 Prompt 动态选模型；旧版"多模型自主路由"（效果/成本/平衡三策略）与新版"基线模型智能降本/增效"（新用户只能选新版） | 按实际路由到的模型计费，路由模型内测免费；限流 5,000,000 TPM / 30,000 RPM 且同时消耗目标模型限流 | 低 | 选型困难、想让简单请求走小模型 |

预置接入点 vs 自定义接入点：预置只支持常规与低延迟、通过 Model ID 或 Endpoint ID 调用、不能开关/平滑切版本/评测/数据投递；自定义接入点支持全部方式、只能用 Endpoint ID、支持模型版本平滑切换。已在 MLP 部署的模型或自定义模型也可经方舟统一调用（方舟不计费 MLP 推理）。

---

## 8. 近期上线 / 下线信息

### 8.1 标准 API 模型发布公告（1159178，更新 2026-08-27）

| 月份 | 模型 | 类型 | 说明 |
|---|---|---|---|
| 2026-08 | `doubao-seed-evolving` ×2 次更新 | 深度思考 | Agent 任务链路、搜索/工具调用幻觉改善 |
| 2026-08 | `deepseek-v4-pro-ga-260813` 新发布 | 深度思考 | Agent 能力增强，思考/非思考双模式，1M |
| 2026-08 | `deepseek-v4-flash-ga-260731` 新发布 | 深度思考 | 自适应深度思考与通用对话双模式 |
| 2026-07 | `doubao-seed-evolving` 更新 | 深度思考 | 支持 1M 上下文，tokens 消耗更少 |
| 2026-07 | `glm-5-2-260617` 新发布 | 深度思考 | 长程自主编码，1M |
| 2026-06 | `doubao-seed-evolving` 新发布；`doubao-seed-2-1-pro-260628`、`doubao-seed-2-1-turbo-260628`、`doubao-seed-character-260628`、`doubao-seedance-2-5-260628`、`doubao-seedream-5-0-pro-260628` 新发布 | — | 2.1 系列为"面向 Coding 与 Agent 时代的新一代旗舰"；turbo 为低成本低时延版 |
| 2026-05 | `deepseek-v4-pro-260425`、`deepseek-v4-flash-260425` 新发布 | 深度思考 | 预览版 |
| 2026-04 | `doubao-seed-2-0-lite-260428`、`doubao-seed-2-0-mini-260428`（四模态）、`doubao-seed-character-251128`、`doubao-seed3d-2-0-260328`、`hyper3d-gen2-260112`、`hitem3d-2-0-251223` 新发布；`doubao-seedance-2-0[-fast]-260128` 全量发布（需资源包或余额 >200 元） | — | — |
| 2026-02 | `doubao-seed-2-0-pro/lite/mini-260215`、`doubao-seed-2-0-code-preview-260215` 新发布 | — | — |
| 2026-01 | `glm-4-7-251222` 新发布 | — | — |

模型列表页标 `即将下线` 的标准 API 模型：`doubao-seed-1-8-251228`、`doubao-seed-code-preview-251028`、`doubao-seed-1-6-*` 全部、`doubao-1-5-*` 全部、`glm-4-7-251222`、`doubao-seedance-1-5-pro-251215`。⚠ 标准 API 侧下线日期文档未说明。

### 8.2 Coding Plan 上线 / 下线（2578683 / 2578687）

上线：08-28 `glm-5.3-flash`；08-26 `deepseek-v4-pro` 正式版；08-21 `doubao-seed-evolving`；08-14 `glm-5.3`；08-04/07 `deepseek-v4-flash` 正式版；07-23 `doubao-seed-2.1-turbo`；06-18 `kimi-k2.7-code`；06-17 `glm-5.2`；06-08 `minimax-m3`；05-18 `deepseek-v4-flash/pro`。

下线：`glm-5.2` 2026-08-31 14:00 停服（自动路由到 `glm-5.3`）；`kimi-k2.6`、`minimax-m2.7` 08-18；`doubao-seed-2.0-code`、`doubao-seed-2.0-pro` 08-08；`doubao-seed-code` 08-05；`glm-5.1`、`deepseek-v3.2` 06-30；`minimax-m2.5`、`kimi-k2.5`、`glm-4.7` 06-08；`kimi-k2-thinking` 04-22。下线流程：启动通知当日即对"新用户"（购买套餐但未用过该模型）停服，约两周后全量停服。

### 8.3 Agent Plan 上线 / 下线（2578669 / 2578673）

上线：08-28 `glm-5.3-flash`；08-24 `deepseek-v4-pro` 正式版；08-14 `glm-5.3`；08-03/07 `deepseek-v4-flash` 正式版；07-23 `doubao-seed-2.1-turbo`；07-17 `kimi-k3`；07-15 `doubao-seed-evolving`；06-25 `doubao-seedance-2.0-mini`（仅 Large/Max）；06-17 `glm-5.2`、`kimi-k2.7-code`；06-11 `doubao-seed-tts-2.0`、`doubao-seed-asr-2.0`；06-08 `minimax-m3`；05-15 `deepseek-v4-flash/pro`。

下线：`glm-5.2` 2026-08-31（含超额后付费一并停，自动路由 `glm-5.3`）；`doubao-seedance-1.5-pro` **2026-09-21 14:00** 停服 → 迁移 `doubao-seedance-2.0-mini`；`kimi-k2.6` → `kimi-k2.7-code`/`kimi-k3`、`minimax-m2.7` → `minimax-m3` 08-18；`doubao-seed-2.0-code`/`-pro` → `doubao-seed-2.1-turbo` 08-08；`glm-5.1` → `glm-5.2`、`deepseek-v3.2` → `deepseek-v4-pro` 06-30；`minimax-m2.5`、`kimi-k2.5`、`glm-4.7` 06-08。

---

## 9. 来源页面

| 标题 | URL | 文档更新时间 |
|---|---|---|
| 模型列表 | https://www.volcengine.com/docs/82379/1330310 | 2026-09-02 |
| 模型价格 | https://www.volcengine.com/docs/82379/1544106 | 2026-08-27 |
| 最新模型：Seed-Evolving | https://www.volcengine.com/docs/82379/2549861 | 2026-08-27 |
| Agent 场景模型调用的正确姿势 | https://www.volcengine.com/docs/82379/2636748 | 2026-09-01 |
| 智能模型路由 | https://www.volcengine.com/docs/82379/1828788 | 2026-08-11 |
| 推理方式概述 | https://www.volcengine.com/docs/82379/2123245 | 2026-07-07 |
| 在线推理（常规） | https://www.volcengine.com/docs/82379/2121998 | 2026-08-11 |
| 快速入门 | https://www.volcengine.com/docs/82379/1399008 | 2026-09-01 |
| 产品简介 | https://www.volcengine.com/docs/82379/1099455 | 2026-08-24 |
| 模型发布公告 | https://www.volcengine.com/docs/82379/1159178 | 2026-08-27 |
| Agent Plan 个人版 · 套餐概览 | https://www.volcengine.com/docs/82379/2366394 | 2026-08-31 |
| Coding Plan 个人版 · 套餐概览 | https://www.volcengine.com/docs/82379/1925114 | 2026-08-31 |
| Agent Plan · 套餐内 AFP 抵扣规则 | https://www.volcengine.com/docs/82379/2516283 | 2026-09-01 |
| Agent Plan · 超额后付费规则 | https://www.volcengine.com/docs/82379/2516284 | 2026-08-31 |
| Agent Plan · 模型上线公告 | https://www.volcengine.com/docs/82379/2578669 | 2026-08-28 |
| Agent Plan · 模型下线公告 | https://www.volcengine.com/docs/82379/2578673 | 2026-08-24 |
| Coding Plan · 模型上线公告 | https://www.volcengine.com/docs/82379/2578683 | 2026-08-28 |
| Coding Plan · 模型下线公告 | https://www.volcengine.com/docs/82379/2578687 | 2026-08-24 |
| Agent Plan 控制台实读 | https://console.volcengine.com/ark/region:cn-beijing/subscription/agent-plan | 2026-09-03（实读） |
| Coding Plan 控制台实读 | https://console.volcengine.com/ark/region:cn-beijing/subscription/coding-plan | 2026-09-03（实读） |
| 鉴权与 Base URL 速查 | `auth.md`（同批产出） | 2026-09-03 |
| 真实 API 验证记录（Agent Plan Medium，`/api/plan/v3` + `/api/plan/v1/messages`） | `volcengine-ark-workspace/verification-findings.md` + `verification-log.jsonl`（同批产出） | 2026-09-04 |
