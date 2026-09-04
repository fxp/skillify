# 把 Agent Plan / Coding Plan 接入 AI 编程 & Agent 工具（配置速查）
本文件覆盖：火山方舟 **Agent Plan 个人版** 与 **Coding Plan 个人版** 在各 AI 编程 / Agent 工具中的具体配置（Base URL、Key 来源、配置文件路径、完整配置示例），以及两套 Plan 之间唯一的差异点。不覆盖套餐价格 / 额度、模型能力细节、标准 `/api/v3` 后付费 API（见 `auth.md` 与其他 reference）。

**目录**
- [0. 总表：工具 → 协议 → Base URL / Key → 配置文件](#0-总表)
- [1. 所有工具共用的规则](#1-所有工具共用的规则)
- [2. ArkCLI Helper 自动配置（推荐，所有工具通用）](#2-arkcli-helper-自动配置)
- [3. Claude Code](#3-claude-code)
- [4. Codex CLI / Codex 桌面端](#4-codex-cli--codex-桌面端)
- [5. OpenCode](#5-opencode)
- [6. OpenClaw](#6-openclaw)
- [7. Cline / Cursor / Roo Code / Kilo Code（"其他工具"）](#7-cline--cursor--roo-code--kilo-code)
- [8. TRAE（TraeCode）](#8-traetraecode)
- [9. Hermes Agent](#9-hermes-agent)
- [10. Pi](#10-pi)
- [11. ZCode](#11-zcode)
- [12. WorkBuddy](#12-workbuddy)
- [13. DeepSeek Harness](#13-deepseek-harness)
- [14. OpenAI4S（仅 Agent Plan）](#14-openai4s仅-agent-plan)
- [15. OpenViking](#15-openviking)
- [16. 报错与排查汇总（文档原文 + 部分实测）](#16-报错与排查汇总文档原文--部分实测)
- [来源页面](#来源页面)

## 0. 总表
约定：**AP** = Agent Plan 个人版，**CP** = Coding Plan 个人版。Key 类型只有两种：
- **AP Key**：Agent Plan 专属 API Key（Agent Plan 控制台「配置专属 API Key」），示例代码环境变量 `ARK_AGENT_PLAN_API_KEY`。
- **方舟 Key**：方舟平台 API Key（控制台 API Key 管理页），Coding Plan 直接用它，示例代码环境变量 `ARK_API_KEY`。

两把 Key **互不通用**：文档原话「Agent Plan 专属 API Key 与火山方舟平台的 API Key 不同，请勿混用」；「其他方舟 API Key 如 Coding Plan API Key 无法在 Agent Plan 中使用」。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：AP Key 打 `/api/v3/chat/completions` 与 `/api/coding/v3/chat/completions` 都返回 **401** `{"error":{"code":"AuthenticationError","message":"The API key or AK/SK in the request is missing or invalid. ...","type":"Unauthorized"}}`，打 `/api/plan/v3` 才 200。工具里看到 401 先查 Key 类型与 Base URL 里 `plan` / `coding` 是否配对。

| 工具 | 协议 | AP Base URL（填 AP Key） | CP Base URL（填方舟 Key） | 配置文件 / 入口 |
|---|---|---|---|---|
| ArkCLI Helper | — | `arkcli auth login` 选 `agent-plan` | `arkcli auth login` 选 `coding-plan` | `arkcli helper` 交互式写各工具配置 |
| Claude Code | Anthropic | `https://ark.cn-beijing.volces.com/api/plan` | `https://ark.cn-beijing.volces.com/api/coding` | `~/.claude/settings.json` + `~/.claude.json`（Win：`%USERPROFILE%\.claude\settings.json`、`%USERPROFILE%\.claude.json`） |
| Claude Code VSCode 插件 | Anthropic | 同上 | 同上 | VSCode `settings.json` 的 `claudeCode.environmentVariables` |
| CC Switch（Claude Code 配置管理） | Anthropic | 同上（供应商选「火山 Agentplan」，自动填） | 同上（供应商选「自定义配置」） | 桌面应用 |
| Codex CLI / 桌面端 | OpenAI（Responses） | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` | `~/.codex/config.toml`（Win：`%USERPROFILE%\.codex\config.toml`）+ 环境变量 |
| OpenCode | OpenAI（Responses 推荐 / Chat） | `…/api/plan/v3` | `…/api/coding/v3` | `~/.config/opencode/opencode.json`（Win：`%USERPROFILE%\.config\opencode\opencode.json`） |
| OpenClaw | OpenAI（Responses 推荐 / Chat） | `…/api/plan/v3` | `…/api/coding/v3` | `~/.openclaw/openclaw.json` 或 `openclaw dashboard` Web UI |
| Cline | OpenAI Compatible | `…/api/plan/v3` | `…/api/coding/v3` | VSCode 插件设置界面 |
| Cursor | OpenAI（Override Base URL） | `…/api/plan/v3` | `…/api/coding/v3` | Cursor Settings → Models（需 Cursor Pro 及以上） |
| Roo Code | OpenAI Compatible | `…/api/plan/v3` | `…/api/coding/v3` | VSCode 插件设置界面 |
| Kilo Code | OpenAI Compatible | `…/api/plan/v3` | `…/api/coding/v3` | Settings → Providers → Custom provider |
| TRAE（TraeCode） | 内置「火山引擎」服务商 | 配置方式选 **Agent Plan** | 配置方式选 **Coding Plan** | IDE 设置 → 模型 → 添加模型（不填 URL） |
| Hermes Agent | OpenAI（codex_responses 推荐 / chat_completions） | `…/api/plan/v3` | `…/api/coding/v3` | `~/.hermes/config.yaml` 或 `hermes config set` |
| Pi | OpenAI（openai-completions） | `…/api/plan/v3` | `…/api/coding/v3` | `~/.pi/agent/models.json` |
| ZCode | Anthropic Messages / Chat Completions / Responses 三选一 | Anthropic：`…/api/plan`；OpenAI 两种：`…/api/plan/v3` | Anthropic：`…/api/coding`；OpenAI 两种：`…/api/coding/v3` | `~/.zcode/v2/config.json`（Win：`%USERPROFILE%\.zcode\v2\config.json`）或客户端 UI |
| WorkBuddy | OpenAI（`/chat/completions`） | `…/api/plan/v3` | `…/api/coding/v3` | `~/.workbuddy/models.json` 或客户端 UI |
| DeepSeek Harness | openai-completions / openai-responses / anthropic-messages | OpenAI 两种：`…/api/plan/v3`；Anthropic：`…/api/plan` | OpenAI 两种：`…/api/coding/v3`；Anthropic：`…/api/coding` | `$DSH_HOME/settings.yaml` 或 Web UI（`npx @deepseek-ai/dsh web`） |
| OpenAI4S | 「ark 兼容协议」 | `…/api/plan/v3` | ⚠ 文档未说明（只有 Agent Plan 页面） | 设置 → 通用 → 模型与 API Key |
| OpenViking | volcengine backend（OpenAI 兼容路径） | `…/api/plan/v3` | `…/api/coding/v3` | `~/.openviking/ov.conf` + `OPENVIKING_CONFIG_FILE` |

`…` = `https://ark.cn-beijing.volces.com`。

## 1. 所有工具共用的规则
1. **Base URL 按协议二选一，绝不用 `/api/v3`**：
   | 协议 | Agent Plan | Coding Plan |
   |---|---|---|
   | Anthropic 兼容 | `https://ark.cn-beijing.volces.com/api/plan` | `https://ark.cn-beijing.volces.com/api/coding` |
   | OpenAI 兼容（Chat / Responses / Embeddings） | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |

   文档原话（Coding Plan）：「请勿使用 `https://ark.cn-beijing.volces.com/api/v3`：该 Base URL 不会消耗您的 Coding Plan 额度，而是会产生额外费用。」Agent Plan 页面：「为专属 Base URL，其他 Base URL 无法在 Agent Plan 中使用。」**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：「无法使用」= AP Key 打 `/api/v3` 或 `/api/coding/v3` 直接 401 AuthenticationError，不是静默后付费（静默后付费只会发生在用**方舟 Key** 填了 `/api/v3` 时）。

2. **model 字段填小写 Model Name**（不是标准 API 的带日期 Model ID / `ep-` 接入点）。Coding Plan 文档列出的 Model Name：`doubao-seed-evolving`、`doubao-seed-2.1-turbo`、`doubao-seed-2.0-lite`、`minimax-m3`、`glm-5.3`（别名 `glm-latest`）、`glm-5.3-flash`、`deepseek-v4-flash`、`deepseek-v4-pro`、`kimi-k2.7-code`。Agent Plan 的工具页配置示例还出现 `doubao-seed-2.0-mini`、`kimi-k3`（按套餐不同，Small 无 `kimi-k3`）。「支持使用全小写格式，同时也支持直接复制开通管理页面中的模型名称」。
   - ⚠ 文档自相矛盾：Coding Plan 的 TRAE 页与 OpenViking 页还列出 `minimax-m2.7`、`kimi-k2.6`，而同一套文档的「核心配置」列表里没有这两项；Cursor 小节的重命名提示也提到它们。是否仍可用待实测。
   - ⚠ 文档未说明：`doubao-seed-2.0-mini` 只出现在 Agent Plan 的 OpenCode / OpenClaw / Pi / ZCode 配置示例中，Coding Plan 是否支持未写。

3. **`ark-code-latest` = 控制台托管的模型别名**：配置文件填 `ark-code-latest`，然后在控制台「开通管理」页选择 / 切换目标模型，「切换后 3-5 分钟即可生效」；只有这条路能用 **Auto** 模式（「效果 + 速度」双维度自动选模型）。文档原话：「Model Name 不支持配置为 `Auto`，如需使用，请通过控制台切换该模式。」**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：**配置文件里 `model` 不能写 `auto`**——`model: "auto"` → **404** `{"error":{"code":"UnsupportedModel","message":"The requested model does not support the agent plan feature. Please refer to the documentation at https://www.volcengine.com/docs/82379/2366394 to select a compatible model. ..."}}`。Agent Plan 控制台列出的「Model Name: auto」是错的；要 Auto 就写 `ark-code-latest` 并在控制台选 Auto（此时响应 `model` 字段为 `"auto"`）。
   - 视觉模型（生图 / 生视频）「不支持通过 Auto 及控制台切换使用」，且只在 Agent Plan Medium（图）/ Large（视频）及以上套餐提供，通过 Skill 接入（配置视觉模型页，不在本文件范围）。

4. **Key 一律从环境变量读**（本 skill 约定）：Coding Plan / 标准 API 用 `ARK_API_KEY`，Agent Plan 用 `ARK_AGENT_PLAN_API_KEY`。官方文档的配置示例把 Key 直接写在 JSON 里并统一叫 `<ARK_API_KEY>`；下文保留其占位符写法，但每处都注明该占位符在 Agent Plan 下应是 AP Key。工具本身要求 Key 写进配置文件时无法避免，请把文件权限收紧。

5. **换 Plan 时先清旧环境变量**（文档原话，Claude Code 页）：
   ```bash
   unset ANTHROPIC_AUTH_TOKEN
   unset ANTHROPIC_BASE_URL
   ```
   「若变量在 `~/.bashrc` / `~/.zshrc` 中，可以备份并同步删除对应变量。」

6. **不要用 curl 直接打 Plan 入口做连通性测试**：文档原话「在非 AI 工具中使用方舟 Coding Plan / Agent Plan 权益对应的 Base URL 和 API Key 有可能被识别为滥用 / 违规，会导致订阅停用或账号封禁」。验证连通性请在工具内做（Claude Code `/status`、OpenCode / OpenClaw `/models`、Pi `/model`、发一句话看是否回复）。

7. **两套 Plan 在同一工具里的差异几乎只有两处**：Base URL（`plan` ↔ `coding`）和 Key 来源。下文每个工具用一张「差异表」列出，其余字段两边完全一样。

## 2. ArkCLI Helper 自动配置
ArkCLI Helper 是方舟官方的工具配置助手（基于旧 Ark Helper 升级），支持 macOS / Linux / Windows，会把 Base URL、Key、模型写进目标工具的配置文件，并自动设置 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` 之类的防漏额度项。文档对每个工具都把它列为「方式 1（推荐）」。

**支持的 AI Agent**（`arkcli helper` 第 4 步可选项，文档逐页列出）：Claude Code、Codex、OpenCode、OpenClaw、Hermes Agent、Pi、ZCode、WorkBuddy、DeepSeek Harness。TRAE、Cline / Cursor / Roo / Kilo、OpenAI4S、OpenViking 页面没有 ArkCLI Helper 小节 → 只能手动配置。
```bash
# 1. 安装 Ark CLI
npm install -g @volcengine/ark-cli@latest
arkcli --version

# 2. 登录（首次会依次问：Project、Type）
arkcli auth login
#   选择项目（Project）：按需选择，或默认「账号全部资源」
#   选择消费模式（Type）：agent-plan  ←Agent Plan
#                        coding-plan ←Coding Plan
#   之前登录过会沿用上次配置；要重选先执行：
arkcli config reset && arkcli auth login

# 3. 启动助手，按提示选
arkcli helper
#   Plan profile：agent-plan_cn-beijing_personal (Agent Plan)
#              或 coding-plan_cn-beijing_personal (Coding Plan)
#   默认 model：按需选择
#   要配置的 AI Agent：Claude Code / Codex / OpenCode / OpenClaw / Hermes Agent / Pi / ZCode / WorkBuddy / DeepSeek Harness
#   （仅 Agent Plan）Harness：豆包搜索、专业数据集、Agent 记忆（OpenViking）、AI Native 应用开发底座
#     → 逐项选「配置」或「跳过」，选了会自动安装对应 Harness 工具
#     Pi 页面列出的 Harness 是：AI Native 应用开发底座、云电脑
```

| 差异 | Agent Plan | Coding Plan |
|---|---|---|
| `arkcli auth login` 的 Type | `agent-plan` | `coding-plan` |
| `arkcli helper` 的 Plan profile | `agent-plan_cn-beijing_personal (Agent Plan)` | `coding-plan_cn-beijing_personal (Coding Plan)` |
| Harness 选择步骤 | 有（豆包搜索 / 专业数据集 / OpenViking / AI Native 底座） | 无 |
| 运行时要填的 Key | Agent Plan 专属 API Key（ZCode / WorkBuddy / DSH 页：「如需在本地环境变量中管理，可使用 `ARK_API_KEY` 作为变量名」） | 方舟 API Key |

旧版 Ark Helper（FAQ，文档原文，未实测）：升级 `curl -fsSL https://lf3-static.bytednsdoc.com/obj/eden-cn/ylwslo-yrh/ljhwZthlaukjlkulzlp/install.sh | sh`；卸载 `npm uninstall -g @byted-aml/ark-helper`。

## 3. Claude Code

> **先看这条 —— 已用真实 API 验证（2026-09-04，Agent Plan Medium）：不设 `ANTHROPIC_MODEL` / `ANTHROPIC_DEFAULT_{HAIKU,SONNET,OPUS}_MODEL` / `CLAUDE_CODE_SUBAGENT_MODEL` 时，Claude Code 请求里默认的 `claude-*` 模型名会被 Plan 的 Anthropic 入口静默换成 `doubao-seed-2.1-turbo`（响应 `"model":"doubao-seed-2-1-turbo-260628"`），不报错，但按 2.5 抵扣系数扣 AFP。** 实测请求：`POST /api/plan/v1/messages`，`model: "claude-sonnet-4-5"` → 200。也就是说「只配 `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` 就能用」是真的，但会用最贵的通用档位之一，且 Haiku 位（后台小任务）也会打到 2.1-turbo。**3.1 的五个模型变量一个都不要省。** 同理，Codex / OpenCode / 其他工具若不显式写 Model Name 而沿用工具默认模型名，OpenAI 入口对套餐外名字（如 `doubao-seed-2.1-pro`）实测返回 404 UnsupportedModel，`gpt-*` 之类默认名未测——不要依赖默认值，显式填。
>
> 其他实测结论（Anthropic 入口原生可用）：`x-api-key: <Key>` 与 `Authorization: Bearer <Key>` **两种鉴权头都接受**，所以 Claude Code 的 `ANTHROPIC_AUTH_TOKEN`（Bearer）没问题；响应是标准 Anthropic Message，思维链为 `{"type":"thinking","thinking":"..."}` block，`usage` 含 `cache_read_input_tokens`；`thinking: {"type":"disabled"}` → 200 只剩 `text` block；`stream: true` 为标准 Anthropic SSE（`message_start` / `content_block_start` / `content_block_delta` …）。配置文件里 `<MODEL_NAME>` **不能写 `auto`**（404），要 Auto 写 `ark-code-latest` + 控制台选 Auto。

协议：Anthropic。配置文件：`~/.claude/settings.json`（环境变量）+ `~/.claude.json`（跳过 onboarding）。安装：`npm install -g @anthropic-ai/claude-code`（Node.js 18+，Windows 另需 Git for Windows），`claude --version` 验证。

| 差异 | Agent Plan | Coding Plan |
|---|---|---|
| `ANTHROPIC_BASE_URL` | `https://ark.cn-beijing.volces.com/api/plan` | `https://ark.cn-beijing.volces.com/api/coding` |
| `ANTHROPIC_AUTH_TOKEN` | Agent Plan 专属 API Key（`$ARK_AGENT_PLAN_API_KEY`）；实测 Bearer 头在 `/api/plan` 可用 | 方舟 API Key（`$ARK_API_KEY`） |
| 原生 Web Search | 「通过 Messages API 接入的 Claude Code 也可原生使用 Web Search」，需先在控制台开启豆包搜索抵扣，否则按后付费计费 | 页面未提及 |
| CC Switch 供应商 | 选「火山 Agentplan」，请求地址自动填 | 选「自定义配置」，手填 `…/api/coding` |
| 其他所有 env | 完全一致 | 完全一致 |

### 3.1 完整 `~/.claude/settings.json`
```bash
mkdir -p ~/.claude && nano ~/.claude/settings.json
# Windows CMD：
#   if not exist "%USERPROFILE%\.claude" mkdir "%USERPROFILE%\.claude"
#   notepad "%USERPROFILE%\.claude\settings.json"
```
```json
{
    "env": {
        "ANTHROPIC_AUTH_TOKEN": "<PLAN_API_KEY>",
        "ANTHROPIC_BASE_URL": "<PLAN_BASE_URL>",
        "ANTHROPIC_MODEL": "<MODEL_NAME>",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "<MODEL_NAME>",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "<MODEL_NAME>",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "<MODEL_NAME>",
        "CLAUDE_CODE_SUBAGENT_MODEL": "<MODEL_NAME>",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
    }
}
```

| 占位符 | Agent Plan | Coding Plan |
|---|---|---|
| `<PLAN_BASE_URL>` | `https://ark.cn-beijing.volces.com/api/plan` | `https://ark.cn-beijing.volces.com/api/coding` |
| `<PLAN_API_KEY>` | Agent Plan 专属 API Key | 方舟 API Key |
| `<MODEL_NAME>` | 文本生成模型的 Model Name，或 `ark-code-latest`；**不能写 `auto`**（实测 404），也不要留空（见本节开头） | 同左 |

字段说明（文档原文整理）：
- `ANTHROPIC_DEFAULT_{HAIKU,SONNET,OPUS}_MODEL`：「推荐使用完整模型配置，并按任务复杂度选择模型：Haiku（轻量）、Sonnet（日常）、Opus（复杂）」；「`ANTHROPIC_DEFAULT_HAIKU_MODEL` 建议设置为小尺寸模型」。
- `CLAUDE_CODE_SUBAGENT_MODEL`：「建议与主模型保持一致」。
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`：「关闭 Claude Code 后台匿名遥测请求。遥测请求默认会走 `ANTHROPIC_BASE_URL` 并占用 Plan 配额，设为 `"1"` 可避免额度被静默消耗（ArkCLI Helper 会自动配置此项）」。**手动配置务必带上。**

### 3.2 `~/.claude.json`：跳过入门引导
```json
{
  "hasCompletedOnboarding": true
}
```
路径：macOS/Linux `~/.claude.json`；Windows `%USERPROFILE%\.claude.json`（`C:\Users\<用户名>\.claude.json`）。「修改或新增 `hasCompletedOnboarding` 字段值为 `true`，设置状态为完成入门引导」。保存后**新开终端**再运行。

### 3.3 开启 / 关闭思考（`CLAUDE_CODE_EXTRA_BODY`）
在 `env` 中加一项（值是**字符串化的 JSON**）：
```json
"CLAUDE_CODE_EXTRA_BODY": "{\"thinking\":{\"type\":\"enabled\"}}"
```
- 开启深度思考：`enabled`（FAQ「Claude Code 如何开启深度思考模式？」），改完重新执行 `claude`。
- 关闭思考：`disabled`（Claude Code 工具页「如需关闭思考（thinking）模式，需要在 env 中添加 …`disabled`…」）。
- 默认状态文档未写。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**（OpenAI 入口）：`doubao-seed-2.0-lite` 默认思考**开**（`reasoning_tokens: 109`），`thinking.disabled` 生效（→ 0）；`glm-5.3` 默认开且 `thinking: {"type":"disabled"}` → **400** `{"error":{"code":"InvalidParameter","message":"thinking.type `disabled` is not supported by this model ...","type":"BadRequest"}}`。Anthropic 入口 `thinking.disabled` 实测 200（非 glm 模型）。
- **由上条推论**（未在 Claude Code 内实测）：`CLAUDE_CODE_EXTRA_BODY` 里配了 `disabled` 后再 `/model glm-5.3`，请求会带 `thinking.type: disabled` 打到 glm-5.3 → 预期 400 报错而不是静默忽略。用 glm-5.3 时把这项去掉；想让 glm-5.3 少想，OpenAI 入口实测 `reasoning_effort: "low"` 可让 `reasoning_tokens: 0`（Anthropic 入口的对应参数未测）。

### 3.4 开启 1M 上下文
支持 1M 的模型：`glm-5.3`、`deepseek-v4-flash`、`deepseek-v4-pro`（Claude Code 页两版一致）。做法：模型名加 `[1m]` 后缀 + 设置压缩窗口。
```json
{
    "env": {
        "ANTHROPIC_AUTH_TOKEN": "<PLAN_API_KEY>",
        "ANTHROPIC_BASE_URL": "<PLAN_BASE_URL>",
        "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "1000000",
        "ANTHROPIC_MODEL": "glm-5.3[1m]",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-5.3[1m]",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.3[1m]",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5.3[1m]"
    }
}
```
（`<PLAN_BASE_URL>` / `<PLAN_API_KEY>` 取值同 3.1 的表。）「若模型参数加上 `[1m]` 后缀后，Claude Code 识别模型不存在，需升级 Claude Code 到最新版本后重试」（文档原文，未实测）。注意这段官方示例没有 `CLAUDE_CODE_SUBAGENT_MODEL` 和 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`，实际使用应把它们补回去。

### 3.5 启动、验证、切换模型
```bash
cd my-project
claude                      # 首次选择「信任此文件夹」
# 会话内：
/status                     # 确认模型（Agent Plan 快速开始页写的是 /model）
/model <MODEL_NAME>         # 对话期间切换
# 启动时指定：
claude --model <MODEL_NAME>
```

| 切换方式 | 做法 |
|---|---|
| 控制台切换 | 配置 `ark-code-latest`，去开通管理页选模型，3-5 分钟生效，`/status` 确认 |
| 命令参数 | `claude --model <MODEL_NAME>`（本次会话）/ `/model <MODEL_NAME>`（对话期间） |
| 改配置文件 | 修改 `settings.json` 中的 `<MODEL_NAME>` |

「Claude Code 的原生搜索工具仅支持 Claude 系列模型，第三方模型（如 Doubao、GPT 等）无法直接调用」，需通过豆包搜索 Harness（Agent Plan）或 MCP / Skill 补上。

### 3.6 VSCode / JetBrains 插件
插件依赖已装好并配置的 Claude Code CLI。VSCode：扩展市场搜 `claude code` 安装 → 设置 → Extensions → Claude Code → 「Claude Code: Environment Variables」→ Edit in settings.json：
```json
"claudeCode.environmentVariables": [
    { "name": "ANTHROPIC_BASE_URL", "value": "<PLAN_BASE_URL>" },
    { "name": "ANTHROPIC_AUTH_TOKEN", "value": "<PLAN_API_KEY>" },
    { "name": "ANTHROPIC_MODEL", "value": "<MODEL_NAME>" }
],
"claudeCode.selectedModel": "<MODEL_NAME>",
```
（占位符取值同 3.1。）「若在 Claude Code 对话框中输入 `/config`，插件仅返回可配置项的用法说明，不提供交互式编辑界面」，要走设置入口。保存后新开窗口。支持 VSCode 及 Cursor、TraeCode 等 VSCode 系 IDE。JetBrains：插件市场搜 `claude code`，重启 IDE 后点图标即用（复用 CLI 配置）。

### 3.7 CC Switch（多供应商切换）
跨平台桌面应用（Win10+、macOS 12+、Ubuntu 22.04+ / Debian 11+ / Fedora 34+）。安装：macOS `brew tap farion1231/ccswitch && brew install --cask cc-switch`；Arch `paru -S cc-switch-bin`；其他从 GitHub Releases 下载 `.deb/.rpm/.AppImage/.msi/.zip/.dmg`。
步骤：顶部选 Claude Code 图标 → 右上「+」→ 供应商：**Agent Plan 选「火山 Agentplan」**（请求地址自动填 `…/api/plan`）/ **Coding Plan 选「自定义配置」**（请求地址填 `…/api/coding`）→ 填 Key → 高级选项分别配 Sonnet / Opus / Fable / Haiku 模型（「建议 Haiku 设置为小尺寸模型」）→ 添加 → 首页「启用」→ 新开 Claude Code 会话生效。

## 4. Codex CLI / Codex 桌面端
协议：OpenAI **Responses API**（`wire_api = "responses"`；「Agent Plan / Coding Plan 支持 Responses API，可以使用最新版 Codex CLI」）。安装：`npm i -g @openai/codex`（Node.js 18+），`codex --version`。配置文件：`~/.codex/config.toml`（Windows `%USERPROFILE%\.codex\config.toml`）。

| 差异 | Agent Plan | Coding Plan |
|---|---|---|
| `base_url` | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| provider 名（文档示例，可自定） | `volcengine-agent-plan` | `volcengine-coding-plan` |
| `env_key` 指向的环境变量里放的 Key | Agent Plan 专属 API Key | 方舟 API Key |
```toml
model = "<Model_Name>"
model_provider = "<PROVIDER_NAME>"
model_supports_reasoning_summaries = true
# model_reasoning_effort = "medium"   # low / medium / high，控制思考长度
[model_providers.<PROVIDER_NAME>]
name = "<PROVIDER_NAME>"
base_url = "<PLAN_BASE_URL>"
env_key = "ARK_API_KEY"
wire_api = "responses"
```

| 占位符 | Agent Plan | Coding Plan |
|---|---|---|
| `<PLAN_BASE_URL>` | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| `<PROVIDER_NAME>` | `volcengine-agent-plan` | `volcengine-coding-plan` |
| `env_key` 环境变量的值 | Agent Plan 专属 API Key | 方舟 API Key |

注意（文档原文）：
- `env_key` 是**环境变量名**，「请不要直接修改 `ARK_API_KEY`，您需要在下一步设置该环境变量的值」。文档两套 Plan 都用 `ARK_API_KEY`；按本 skill 约定 Agent Plan 可改成 `env_key = "ARK_AGENT_PLAN_API_KEY"`，两者等价，只要 shell 里那个变量有值。
- `model_supports_reasoning_summaries = true`：开启推理能力；`model_reasoning_effort`：`low` / `medium` / `high`。参考（**已用真实 API 验证（2026-09-04，Agent Plan Medium）**，Chat Completions 入口，Responses API 的 `reasoning.effort` 未单独测）：`glm-5.3` 传 `reasoning_effort: "low"` → `reasoning_tokens: 0`（几乎不思考）；`"none"` → 400「reasoning_effort `none` is not supported by this model」，所以别写 `none`。
- 「kimi-k2.7-code 不支持设置 `model_supports_reasoning_summaries = true`」。

设置环境变量：
```bash
# macOS / Linux（按 echo $SHELL 选）
echo 'export ARK_API_KEY="YOUR_API_KEY"' >> ~/.zshrc && source ~/.zshrc   # 或 ~/.bashrc
# Windows CMD（新开窗口生效）
setx ARK_API_KEY "YOUR_API_KEY"
# Windows PowerShell
[Environment]::SetEnvironmentVariable("ARK_API_KEY", "YOUR_API_KEY", [EnvironmentVariableTarget]::User)
```
启动：`codex`。

**Codex 桌面端**：「OpenAI 更新后已取消 Codex 的独立应用，将其融入了 ChatGPT Desktop App」。ChatGPT 桌面端左上切到 Codex 模式 → 左下「设置」→「配置」→「打开 config.toml」→ 写入与上面完全相同的 TOML → 设同名环境变量 → **退出并重开 ChatGPT 桌面端**生效。

## 5. OpenCode
协议：OpenAI；两种 API 只差 `npm` 字段：Responses API `"npm": "@ai-sdk/openai"`（自动拼 `/responses`，「推荐，推理效果更好」）；Chat API `"npm": "@ai-sdk/openai-compatible"`（自动拼 `/chat/completions`）。安装：`npm install -g opencode-ai`（Node 18+）。配置文件：`~/.config/opencode/opencode.json`（Windows `%USERPROFILE%\.config\opencode\opencode.json`）。

| 差异 | Agent Plan | Coding Plan |
|---|---|---|
| `options.baseURL` | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| `options.apiKey` | Agent Plan 专属 API Key | 方舟 API Key |
| provider 键名（文档示例） | `volcengine-agent-plan` | `volcengine-plan` |
| 模型列表 | 多 `doubao-seed-2.0-mini`、`kimi-k3`（1M） | 无这两项 |

精简版（只放 3 个模型；完整列表见下表，逐条按同一格式追加）：
```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "<PROVIDER>/ark-code-latest",
  "provider": {
    "<PROVIDER>": {
      "npm": "@ai-sdk/openai",
      "name": "Volcano Engine（Responses API）",
      "options": {
        "baseURL": "<PLAN_BASE_URL>",
        "apiKey": "<PLAN_API_KEY>"
      },
      "models": {
        "ark-code-latest": {
          "name": "ark-code-latest",
          "limit": { "context": 256000, "output": 32000 },
          "modalities": { "input": ["text", "image"], "output": ["text"] }
        },
        "glm-5.3": {
          "name": "glm-5.3",
          "limit": { "context": 1024000, "output": 65536 },
          "modalities": { "input": ["text"], "output": ["text"] }
        },
        "doubao-seed-2.1-turbo": {
          "name": "doubao-seed-2.1-turbo",
          "limit": { "context": 256000, "output": 65536 },
          "modalities": { "input": ["text", "image"], "output": ["text"] }
        }
      }
    }
  }
}
```

| 占位符 | Agent Plan | Coding Plan |
|---|---|---|
| `<PLAN_BASE_URL>` | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| `<PLAN_API_KEY>` | Agent Plan 专属 API Key | 方舟 API Key |
| `<PROVIDER>` | `volcengine-agent-plan` | `volcengine-plan` |

文档给出的各模型 `limit` / `modalities`（两套 Plan 数值一致）：

| Model Name | context | output | input 模态 |
|---|---|---|---|
| `ark-code-latest` | 256000 | 32000 | text, image |
| `doubao-seed-2.1-turbo` | 256000 | 65536 | text, image |
| `doubao-seed-evolving` | 1024000 | 65536 | text, image |
| `doubao-seed-2.0-lite` | 256000 | 65536 | text, image |
| `doubao-seed-2.0-mini`（仅 AP 页） | 256000 | 65536 | text, image |
| `glm-5.3` / `glm-latest` | 1024000 | 65536 | text |
| `glm-5.3-flash` | 1024000 | 65536 | text, image |
| `deepseek-v4-flash` / `deepseek-v4-pro` | 1024000 | 65536 | text（CP 页示例未写 modalities） |
| `minimax-m3` | 1024000 | 65536 | text, image |
| `kimi-k2.7-code` | 256000 | 32000 | text, image |
| `kimi-k3`（仅 AP 页） | 1024000 | 65536 | text, image |

注意（文档原文）：
- 「`provider.<PROVIDER>.models` 节点下有两处（对象键、`name` 字段）需替换为同一 Model Name，切勿遗漏。」
- 1M 上下文通过 `limit.context` 显式指定（AP：glm-5.3 / deepseek-v4-flash / deepseek-v4-pro / kimi-k3；CP 无 kimi-k3）。
- 图片理解需在模型节点加 `"modalities": {"input": ["text", "image"], "output": ["text"]}`。
- 开启深度思考（FAQ，Coding Plan 示例，`@ai-sdk/openai-compatible`）：在模型节点加 `"options": {"thinking": {"type": "enabled"}}`，重启 `opencode`；看不到 Thinking 时 `ctrl+p` 搜 `think` 选 `Show thinking`。

启动 `opencode`，`/models` 选模型 / 切换；`ark-code-latest` 走控制台切换。

## 6. OpenClaw
协议：OpenAI；`models.providers.<id>.api` 二选一：`"openai-responses"`（推荐）/ `"openai-completions"`。安装（Node 22+）：macOS/Linux `curl -fsSL https://openclaw.ai/install.sh | bash`；Windows PowerShell `iwr -useb https://openclaw.ai/install.ps1 | iex`。首次向导按文档建议：Continue? Yes → Setup mode QuickStart → Model/auth provider **Skip for now** → Default model Keep current → channel / Search provider Skip → skills No → hooks Skip（空格选、回车下一步）→ Hatch in Terminal。配置文件：`~/.openclaw/openclaw.json`，或 `openclaw dashboard` Web UI（配置 → Settings → Advanced → Open；CP 页写的是 配置 → Advanced → Raw / open）。改完：文件方式 `openclaw gateway restart`；Web UI 保存后点 **Update**，需重新连接。

| 差异 | Agent Plan | Coding Plan |
|---|---|---|
| `baseUrl` | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| `apiKey` | Agent Plan 专属 API Key | 方舟 API Key |
| provider id（文档示例） | `volcengine-agent-plan` | `volcengine-plan` |
| 模型列表 | 多 `doubao-seed-2.0-mini`、`kimi-k3` | 无 |
| memorySearch Embedding `remote.baseUrl` | `…/api/plan/v3` | `…/api/coding/v3` |

「如果已经配置过 OpenClaw，请勿直接覆盖原有配置，建议根据提供的配置更新 `models`、`agents` 和 `gateway` 节点信息。」精简示例（模型字段 `contextWindow` / `maxTokens` / `input` 的取值与 §5 表中 context / output / input 一一对应）：
```json
{
  "models": {
    "providers": {
      "<PROVIDER>": {
        "baseUrl": "<PLAN_BASE_URL>",
        "apiKey": "<PLAN_API_KEY>",
        "api": "openai-responses",
        "models": [
          { "id": "ark-code-latest", "name": "ark-code-latest",
            "contextWindow": 256000, "maxTokens": 32000, "input": ["text", "image"] },
          { "id": "glm-5.3", "name": "glm-5.3",
            "contextWindow": 1024000, "maxTokens": 65536, "input": ["text"] },
          { "id": "kimi-k2.7-code", "name": "kimi-k2.7-code",
            "contextWindow": 256000, "maxTokens": 32000, "input": ["text", "image"] }
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": { "primary": "<PROVIDER>/ark-code-latest" },
      "models": {
        "<PROVIDER>/ark-code-latest": {},
        "<PROVIDER>/glm-5.3": {},
        "<PROVIDER>/kimi-k2.7-code": {}
      }
    }
  },
  "gateway": { "mode": "local" }
}
```

| 占位符 | Agent Plan | Coding Plan |
|---|---|---|
| `<PLAN_BASE_URL>` | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| `<PLAN_API_KEY>` | Agent Plan 专属 API Key | 方舟 API Key |
| `<PROVIDER>` | `volcengine-agent-plan` | `volcengine-plan` |

⚠ 文档自相矛盾（小）：Agent Plan 页 `models.providers` 里有 `doubao-seed-evolving`，但 `agents.defaults.models` 白名单漏了它；Coding Plan 页两处一致。要用该模型时把 `"<PROVIDER>/doubao-seed-evolving": {}` 补进白名单。

### 6.1 developer role 兼容（FAQ；报错原文已实测）
现象：Chat 发消息无响应，日志 `HTTP 400: The parameter messages.role specified in the request are not valid: invalid value: developer, supported values are: system, assistant, user, tool.`
**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：直接发 `messages[0].role = "developer"` 到 `/api/plan/v3/chat/completions` → **400** `{"error":{"code":"InvalidParameter","message":"The parameter `messages.role` specified in the request are not valid: invalid value: `developer`, supported values are: `system`, `assistant`, `user`, `tool`. ...","param":"","type":"BadRequest"}}`，与 FAQ 文案一致。
原因：「方舟 API 不支持 developer role（OpenAI 新版 API 格式）」。
解法：在**每个 model 对象内**加 `"compat": { "supportsDeveloperRole": false }`——「compat 配置必须放在 model 级别，不能放在 provider 级别，否则会报 `Unrecognized key: "compat"` 错误」。FAQ 示例用的是 `"api": "openai-completions"`：
```json
{ "id": "<Model_Name>", "name": "<Model_Name>", "reasoning": true, "input": ["text"],
  "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
  "contextWindow": 200000, "maxTokens": 8192,
  "compat": { "supportsDeveloperRole": false } }
```
然后 `pkill -f openclaw && openclaw gateway restart`。

### 6.2 图片识别（FAQ，文档原文，未实测）
1. 模型的 `input` 必须含 `"image"`（如 `kimi-k2.7-code`）。
2. 在 `agents.defaults.imageModel` 显式指定图片模型，并确保 `agents.defaults.models` 含该别名：
```json
"agents": { "defaults": {
    "imageModel": { "primary": "<PROVIDER>/kimi-k2.7-code" },
    "models": { "<PROVIDER>/kimi-k2.7-code": { "alias": "volcengine" } }
} }
```
3. `openclaw gateway restart`。

### 6.3 Embedding 记忆检索（`memorySearch`）
两套 Plan 都提供 `doubao-embedding-vision`。在 `agents.defaults` 下加：
```json
"memorySearch": {
  "provider": "openai",
  "model": "doubao-embedding-vision",
  "remote": {
    "baseUrl": "<PLAN_BASE_URL>",
    "apiKey": "<PLAN_API_KEY>"
  }
}
```
（占位符取值同上表。）保存后 `openclaw gateway restart` 或 Web UI Update。「兼容 OpenAI SDK」页说向量化模型不支持 OpenAI 协议，此处却用 `provider: openai` 调 Plan 入口的 embeddings——**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`POST /api/plan/v3/embeddings`（OpenAI 形态，`input` 字符串）**可用**，`data[0].embedding` 默认 **2048** 维，`dimensions: 1024` 生效，响应 `model: doubao-embedding-vision-251215`。OpenClaw 这样配是对的；注意 OpenAI 形态只收字符串输入，图文向量要走 `/embeddings/multimodal`（响应为 `data.embedding` 对象）。

### 6.4 思考、切换模型、飞书
- 深度思考（FAQ）：level 取 `off / minimal / low / medium / high / xhigh`。单条消息 `/think:high 你的问题`（或 `/t high …`）；会话级单发 `/think:high`；全局 `openclaw config set agents.defaults.thinkingDefault high` → `openclaw gateway restart` → `openclaw config get agents.defaults.thinkingDefault` 验证。
- 切换模型：永久改 `agents.defaults.model.primary` 后重启；临时在 `openclaw tui` 里 `/models`，返回 `model set to <Model_Name>` 即生效；`ark-code-latest` 走控制台。
- 使用：`openclaw dashboard`（Web Chat）或 `openclaw tui` + `/status`。
- 飞书机器人：`npx -y @larksuite/openclaw-lark-tools install`（报错加 `sudo`）→ 新建机器人 → 飞书扫码「一键创建」→ 给机器人发 `/feishu start` 返回版本号即成功。插件版本 2026.3.10，要求 OpenClaw Linux/macOS ≥ 2026.2.26、Windows ≥ 2026.3.2；升级 `npx -y @larksuite/openclaw-lark-tools update`；排查 `/feishu doctor`、`npx @larksuite/openclaw-lark-tools doctor --fix`。流式 / 耗时 / 状态：`openclaw config set channels.feishu.streaming true`、`channels.feishu.footer.elapsed true`、`channels.feishu.footer.status true`，改后 `openclaw gateway stop && openclaw gateway run`。群内是否需 @：`openclaw config set channels.feishu.requireMention true|false --json`（不需 @ 需在飞书开放平台开「获取群组中所有消息」权限并重新发布）；按群 `channels.feishu.groups.<群ID>.requireMention true --json`。

## 7. Cline / Cursor / Roo Code / Kilo Code
四个都是 UI 表单配置，协议 OpenAI Compatible，Base URL 用 `…/v3`。

| 差异 | Agent Plan | Coding Plan |
|---|---|---|
| Base URL | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| API Key | Agent Plan 专属 API Key | 方舟 API Key |
| 其余字段 | 相同 | 相同 |

| 工具 | 安装 | 字段 → 值 |
|---|---|---|
| **Cline** | VSCode 扩展市场搜 `Cline` | API Provider = `OpenAI Compatible`；Base URL = 上表；API Key；Model ID = `ark-code-latest` 或 Model Name |
| **Cursor** | cursor.com 下载；「只有订阅了 Cursor Pro 及以上套餐的用户才支持自定义配置模型」 | Settings → Models：OpenAI API Key = Plan Key；Override OpenAI Base URL = 上表；Add Custom Model = `ark-code-latest` 或 Model Name |
| **Roo Code** | VSCode 搜 `Roo Code`，信任发布者；「若模型表现异常，建议更新到 3.43.0 及后续版本」 | API Provider = `OpenAI Compatible`；Base URL；API Key；Model |
| **Kilo Code** | VSCode 搜 `kilo code`，信任发布者 | Settings → Providers → Custom provider：Provider ID / Display Name 自定；API Provider = `OpenAI Compatible`；Base URL；API Key；Model ID = `ark-code-latest` 等；Model Name 显示名自定。「UI 迭代较为频繁，字段名称、顺序或数量可能随版本变化」 |

Cursor 模型名冲突（文档原文，未实测）：配置 `minimax-m2.7`、`glm-5.3`、`glm-5.3-flash`、`kimi-k2.6`（CP 页另加 `kimi-k2.7-code`）遇到名称冲突时，改用 `minimax-m2-7`、`glm-5-3`、`glm-5-3-flash`、`kimi-k2-6`（`kimi-k2-7-code`），即把 `.` 换成 `-`。⚠ 该列表含 `minimax-m2.7` / `kimi-k2.6`，不在当前 Model Name 列表里。

## 8. TRAE（TraeCode）
不填 URL：TraeCode 内置「火山引擎」服务商，按「配置方式」区分 Plan。安装：trae.cn 下载；Agent Plan 需 **TraeCode ≥ 3.3.57**。

| 差异 | Agent Plan | Coding Plan |
|---|---|---|
| 添加模型 → 配置方式 | **Agent Plan** | **Coding Plan** |
| API 密钥 | Agent Plan 专属 API Key | 方舟 API Key |
| 版本要求 | ≥ 3.3.57 | 未写 |

步骤：个人用户入口登录 → 右上「设置」→ 左侧「模型」→「+ 添加模型」→ 服务商 **火山引擎** → 配置方式（见上表）→ 选模型：列表直选，或「使用其他模型」把 **模型 ID** 填成文本生成模型的 Model Name / `ark-code-latest`（Auto 只能走 `ark-code-latest` + 控制台）→ 填 API 密钥 → 添加。使用时在对话框右下角点模型名切换。⚠ Coding Plan TRAE 页的 Model Name 列表含 `minimax-m2.7`、`kimi-k2.6`（见 §1）。

## 9. Hermes Agent
协议：OpenAI；`model.api_mode` 二选一：`codex_responses`（Responses API，推荐）/ `chat_completions`。安装（会自动装 uv / Python / Node / ripgrep / ffmpeg）：macOS/Linux `curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash` 后 `source ~/.zshrc`；Windows PowerShell `iex (irm https://hermes-agent.nousresearch.com/install.ps1)` 后 `. $PROFILE`。配置文件 `~/.hermes/config.yaml`。

| 差异 | Agent Plan | Coding Plan |
|---|---|---|
| `model.base_url` | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| `model.api_key` | Agent Plan 专属 API Key | 方舟 API Key |
```bash
hermes config set model.provider custom
hermes config set model.base_url <PLAN_BASE_URL>
hermes config set model.api_key "$PLAN_API_KEY"      # 文档写的是字面量 <ARK_API_KEY>
hermes config set model.default ark-code-latest
hermes config set model.api_mode codex_responses      # 或 chat_completions
```
生成的 `~/.hermes/config.yaml`（可直接手编）：
```yaml
model:
  default: ark-code-latest
  provider: custom
  base_url: <PLAN_BASE_URL>
  api_key: <PLAN_API_KEY>
  api_mode: codex_responses
```

| 占位符 | Agent Plan | Coding Plan |
|---|---|---|
| `<PLAN_BASE_URL>` | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| `<PLAN_API_KEY>` / `$PLAN_API_KEY` | Agent Plan 专属 API Key（`$ARK_AGENT_PLAN_API_KEY`） | 方舟 API Key（`$ARK_API_KEY`） |

1M 上下文：「直接选择支持 1M 上下文的模型，Hermes Agent 会自动完成调整」；未识别时在 `config.yaml` 给该模型加 `context_length: 1048576`。启动 `hermes`。切换模型：改 `model.default`，或 `ark-code-latest` + 控制台。

飞书（基于 v0.8.0，2026.4.8）：`hermes gateway setup` → 平台 `Feishu / Lark` → AP 页：`Scan QR code to create a new bot automatically`；CP 页：`Enter existing App ID and App Secret manually` + Domain `feishu` + Connection mode `WebSocket` → DM 授权 `Use DM pairing approval` → 群 `Respond only when @mentioned in groups` → Home chat ID 暂不配 → done → 安装 launchd 服务 `Y` → 立即启动 `Y`。给机器人发任意消息拿配对码 → `hermes pairing approve feishu <pairing-code>` → 飞书里发 `/sethome`。

## 10. Pi
协议：OpenAI `"api": "openai-completions"`。安装（Node 20+）：`npm install -g @earendil-works/pi-coding-agent` 或 `curl -fsSL https://pi.dev/install.sh | sh`（Windows 只能 npm，且需 Git for Windows 提供 `bash.exe`）。配置文件 `~/.pi/agent/models.json`（目录不存在先建）。改完**不用重启**，会话里 `/model` 自动重载。

| 差异 | Agent Plan | Coding Plan |
|---|---|---|
| `baseUrl` | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| `apiKey` | Agent Plan 专属 API Key | 方舟 API Key |
| provider 键名（示例） | `agent-plan` | `coding-plan` |
| 模型列表 | 多 `doubao-seed-2.0-mini`、`kimi-k3` | 无 |
```json
{
  "providers": {
    "<PROVIDER>": {
      "api": "openai-completions",
      "apiKey": "<PLAN_API_KEY>",
      "baseUrl": "<PLAN_BASE_URL>",
      "models": [
        { "id": "ark-code-latest" },
        { "contextWindow": 1048576, "id": "doubao-seed-evolving", "input": ["text", "image"], "maxTokens": 256000 },
        { "contextWindow": 262144,  "id": "doubao-seed-2.1-turbo", "input": ["text", "image"], "maxTokens": 256000 },
        { "contextWindow": 1048576, "id": "glm-5.3",               "input": ["text"],          "maxTokens": 128000 },
        { "contextWindow": 1048576, "id": "deepseek-v4-pro",       "input": ["text"],          "maxTokens": 393216 },
        { "contextWindow": 262144,  "id": "kimi-k2.7-code",        "input": ["text", "image"], "maxTokens": 32768 },
        { "id": "minimax-m3" }
      ]
    }
  }
}
```
文档还列出（同格式追加）：`doubao-seed-2.0-lite` 262144 / text+image / 128000；`glm-5.3-flash` 1048576 / text+image / 128000；`glm-latest` 1048576 / text / 128000；`deepseek-v4-flash` 1048576 / text / 393216；仅 Agent Plan：`doubao-seed-2.0-mini` 262144 / text+image / 128000、`kimi-k3` 1048576 / text+image / 128000（字段顺序 contextWindow / input / maxTokens）。

| 占位符 | Agent Plan | Coding Plan |
|---|---|---|
| `<PLAN_BASE_URL>` | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| `<PLAN_API_KEY>` | Agent Plan 专属 API Key | 方舟 API Key |
| `<PROVIDER>` | `agent-plan` | `coding-plan` |

⚠ 文档自相矛盾：同一模型的输出上限在不同工具页数值不同（`doubao-seed-2.1-turbo`：OpenCode / OpenClaw 65536，Pi 256000，ZCode 262144；`glm-5.3`：65536 vs 128000 vs 131072）。这些只是客户端侧声明值，真实上限待实测。

启动 `pi` → `/model` 选 provider 与模型 → 发「简单介绍一下当前目录的文件结构」验证。图片 / 视频生成：`models[].input` 只声明输入模态，生成类能力要经工具调用 / MCP（配置视觉模型页）。

## 11. ZCode
智谱桌面客户端（macOS / Windows / Linux），同时支持 Anthropic 与 OpenAI 协议。下载 zcode.z.ai。UI：左下「设置」→「模型设置」→「添加供应商」→ 填名称、Base URL、API Key、**API 格式** → 「添加模型」（可多次）：模型 ID = Model Name / `ark-code-latest`，上下文窗口按模型上限填，最大输出 Token 可留空。也可直接编辑 `~/.zcode/v2/config.json`（Windows `%USERPROFILE%\.zcode\v2\config.json`；首次经 UI 配置后自动生成，在 `provider` 对象中追加）。

| 差异 | Agent Plan | Coding Plan |
|---|---|---|
| API 格式 Anthropic Messages → Base URL | `https://ark.cn-beijing.volces.com/api/plan` | `https://ark.cn-beijing.volces.com/api/coding` |
| API 格式 Chat Completions / Responses → Base URL | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| API Key | Agent Plan 专属 API Key（「请勿混用方舟平台的普通 API Key」） | 方舟 API Key |
| provider 键 / name（示例） | `ark-agent-plan` / `Ark Agent Plan` | `ark-coding-plan` / `Ark Coding Plan` |
| 模型列表 | 多 `doubao-seed-2.0-mini`、`kimi-k3` | 无 |

`kind` 与 API 格式对应：Anthropic Messages → `"kind": "anthropic"`；Chat Completions → `"kind": "openai-compatible"`；Responses → `"kind": "openai"`。
```json
{
  "provider": {
    "<PROVIDER>": {
      "name": "<DISPLAY_NAME>",
      "kind": "<KIND>",
      "options": {
        "apiKey": "<PLAN_API_KEY>",
        "baseURL": "<PLAN_BASE_URL>",
        "apiKeyRequired": true
      },
      "enabled": true,
      "source": "custom",
      "models": {
        "ark-code-latest": {
          "limit": { "context": 256000, "output": 32768 },
          "modalities": { "input": ["text", "image"], "output": ["text"] }
        },
        "deepseek-v4-pro": {
          "limit": { "context": 1024000, "output": 393216 },
          "modalities": { "input": ["text"], "output": ["text"] }
        }
      }
    }
  }
}
```

| 占位符 | Agent Plan | Coding Plan |
|---|---|---|
| `<PLAN_BASE_URL>` | `kind=anthropic`：`…/api/plan`；其他两种：`…/api/plan/v3` | `kind=anthropic`：`…/api/coding`；其他两种：`…/api/coding/v3` |
| `<PLAN_API_KEY>` | Agent Plan 专属 API Key | 方舟 API Key |
| `<PROVIDER>` / `<DISPLAY_NAME>` | `ark-agent-plan` / `Ark Agent Plan` | `ark-coding-plan` / `Ark Coding Plan` |

其余模型条目（文档值，context/output/input）：`doubao-seed-2.1-turbo` 256000/262144 text+image；`doubao-seed-evolving` 1024000/262144 text+image；`doubao-seed-2.0-lite`、`doubao-seed-2.0-mini`（AP） 256000/131072 text+image；`deepseek-v4-flash` 1024000/393216 text；`glm-5.3`、`glm-latest` 1024000/131072 text；`glm-5.3-flash` 1024000/131072 text+image；`minimax-m3` 1024000/131072 text+image；`kimi-k2.7-code` 256000/32768 text+image；`kimi-k3`（AP） 1024000/131072 text。「请删除您所选套餐不支持的条目，避免调用时收到 model not found 错误」（文档原文，未实测）。使用：主界面顶部模型下拉选中即可。

## 12. WorkBuddy
腾讯云桌面 AI 智能体客户端（QQ / 企微生态）。UI：左下头像 → 设置 → 模型 → 自定义模型「添加模型」→ 提供商 **自定义 / Custom**。也可直接编辑 `~/.workbuddy/models.json`，**保存即热加载，无需重启**，下拉里显示的是 `name`。

| 差异 | Agent Plan | Coding Plan |
|---|---|---|
| 接口地址 / `url` | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| API Key | Agent Plan 专属 API Key | 方舟 API Key |
| 高级工具建议 | 「建议开启工具调用、图片输入、思考模式」 | 「按需开启」 |
```json
[
  {
    "id": "doubao-seed-2.1-turbo",
    "name": "Doubao Seed 2.1 Turbo",
    "vendor": "Custom",
    "url": "<PLAN_BASE_URL>",
    "apiKey": "<PLAN_API_KEY>",
    "supportsToolCall": true,
    "supportsImages": false,
    "supportsReasoning": false,
    "useCustomProtocol": false
  }
]
```

| 占位符 | Agent Plan | Coding Plan |
|---|---|---|
| `<PLAN_BASE_URL>` | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| `<PLAN_API_KEY>` | Agent Plan 专属 API Key | 方舟 API Key |

`useCustomProtocol`：关闭（默认）时「使用标准 `/chat/completions` 路径，自动校验并补全接口地址」；开启则「直接使用用户填写的接口地址发起请求，跳过路径校验与自动补全」，只在经网关 / 代理封装时用。`supportsImages` / `supportsReasoning` 按模型能力改 `true`（文档示例都是 `false`，与其 UI 建议「开启图片输入、思考模式」并不一致，按需自行打开）。

## 13. DeepSeek Harness
「一切皆插件」的 Agent 框架，**开发者预览阶段**。启动 Web UI：`npx @deepseek-ai/dsh web`，默认 `http://127.0.0.1:3080/`（Node LTS）。三种接入方式：ArkCLI Helper（§2）、Web UI 手填、Ark 插件。

| 差异 | Agent Plan | Coding Plan |
|---|---|---|
| openai-completions / openai-responses → API 地址 | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| anthropic-messages → API 地址 | `https://ark.cn-beijing.volces.com/api/plan` | `https://ark.cn-beijing.volces.com/api/coding` |
| API 密钥 | Agent Plan 专属 API Key | 方舟 API Key |
| `settings.yaml` 示例 `apiKeyEnv` | `ARK_PLAN_API_KEY` | `CODING_PLAN_API_KEY` |
| 插件装好后选的 provider | **Ark Agent Plan** | **Ark Coding Plan** |

**Web UI 手填**：设置 → 模型 → 二选一：(a) DeepSeek 卡片「自定义设置」：API 密钥 + API 地址（`…/v3`）+ 添加模型；(b)「添加自定义提供方」：Provider ID（改名需删旧建新）、显示名称、**API 地址与 API 协议按上表对应，不要配错**、API 密钥、添加模型。

**图片输入**：模型页「打开配置文件」`$DSH_HOME/settings.yaml`，给模型加 `input: [text, image]`：
```yaml
llm-pi-ai:
  providers:
    ark-plan:
      displayName: ark-plan
      apiKeyEnv: <KEY_ENV>            # AP 示例 ARK_PLAN_API_KEY；CP 示例 CODING_PLAN_API_KEY
      api: openai-responses
      baseURL: <PLAN_BASE_URL>        # AP …/api/plan/v3；CP …/api/coding/v3
      models:
        - id: doubao-seed-2.1-turbo
          name: doubao-seed-2.1-turbo
          input: [text, image]
```
**Ark 插件**（两套 Plan 命令完全相同）：在 dsh 对话框输入
```
帮我安装下面的插件：curl -fsSL -o dsh-ark-plugin-install.sh "https://lf3-static.bytednsdoc.com/obj/eden-cn/ylwslo-yrh/ljhwZthlaukjlkulzlp/ark-cli-outer-resource/dsh-ark-plugin-install.sh" && bash dsh-ark-plugin-install.sh --plugin-name ark-plan-api
```
`ark-plan-api` 装好后「设置 > 模型」自动出现 Agent Plan、Coding Plan 与后付费三个 provider，只需填对应 Key；可选装插件市场：`帮我安装下面插件：dsh plugin --profile web add dshmarket`。使用：先「选择工作区」（启动 `dsh` 的目录），再在输入框右下角模型下拉选 Ark Agent Plan / Ark Coding Plan 下的模型。

## 14. OpenAI4S（仅 Agent Plan）
北大-元空 AI 开源科研 Agent（v0.2.0）。⚠ 文档未说明：只有 Agent Plan 页面，Coding Plan 是否可用未写（理论上填 `…/api/coding/v3` + 方舟 Key 即可，待实测）。

安装：Apple Silicon `.dmg`（首次启动前 `xattr -dr com.apple.quarantine /Applications/OpenAI4S.app`）；Linux x86_64 `.tar.gz` 解压后 `./OpenAI4S`；或 `pip install openai4s`（Python 3.10+）后 `openai4s serve`。UI 地址 `http://127.0.0.1:8760/`。

配置：设置 → 通用 → 模型与 API Key → 配置：名称自定（如 `方舟 AgentPlan`）；**兼容协议 = `ark 兼容协议`**；Base URL `https://ark.cn-beijing.volces.com/api/plan/v3`；模型 id = 文本生成模型 Model Name；API Key = Agent Plan 专属 Key → 保存 → 「设为当前」。

可选 Harness（都复用同一把 AP Key，「若当前使用的 Ark 模型已配置相同的 Agent Plan Key，OpenAI4S 会自动复用」，Key 保存后不回显）：
- 豆包搜索：设置 → 网络 → 开「允许联网」→「豆包搜索 Custom 版」卡片填 Key → 保存凭证。
- 专业数据集 DataPro：设置 → 连接器 → 「火山方舟专业数据集 DataPro」填 Key。「如返回 `4011`，可能为 API Key 无效、额度不足，或当前 Agent Plan 未开启专业数据集 Harness」（文档原文，未实测）。
- R 内核：需 conda / mamba / micromamba；`.dmg` 用户先 `sudo ln -sf /Applications/OpenAI4S.app/Contents/Resources/runtime/bin/openai4s /usr/local/bin/openai4s`，再 `openai4s setup`，重启。

## 15. OpenViking
火山开源的 Agent 上下文数据库（v0.4.15），需 Python 3.10+、Go 1.22+、GCC 9+ / Clang 11+。安装 `pip install openviking --upgrade --force-reinstall`，`openviking --version`。它用两个模型：`embedding.dense`（向量化，`doubao-embedding-vision`，dimension 1024，input multimodal）和 `vlm`（图像 / 内容理解，文本生成模型）。

| 差异 | Agent Plan | Coding Plan |
|---|---|---|
| `embedding.dense.api_base` / `vlm.api_base` | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| `api_key`（两处） | Agent Plan 专属 API Key | 方舟 API Key |
| VLM 可选模型 | 套餐支持的文本生成模型 | CP 页列表含 `minimax-m2.7`、`kimi-k2.6`（⚠ 见 §1） |

`~/.openviking/ov.conf`：
```json
{
  "storage": { "workspace": "/home/your-name/openviking_workspace" },
  "log": { "level": "INFO", "output": "stdout" },
  "embedding": {
    "dense": {
      "backend": "volcengine",
      "api_key": "<PLAN_API_KEY>",
      "model": "doubao-embedding-vision",
      "api_base": "<PLAN_BASE_URL>",
      "dimension": 1024,
      "input": "multimodal"
    }
  },
  "vlm": {
    "backend": "volcengine",
    "api_key": "<PLAN_API_KEY>",
    "model": "doubao-seed-2.1-turbo",
    "api_base": "<PLAN_BASE_URL>",
    "temperature": 0.1,
    "max_retries": 3
  }
}
```

| 占位符 | Agent Plan | Coding Plan |
|---|---|---|
| `<PLAN_BASE_URL>` | `https://ark.cn-beijing.volces.com/api/plan/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| `<PLAN_API_KEY>` | Agent Plan 专属 API Key | 方舟 API Key |

指向配置文件：macOS/Linux `export OPENVIKING_CONFIG_FILE=~/.openviking/ov.conf`；PowerShell `$env:OPENVIKING_CONFIG_FILE = "$HOME/.openviking/ov.conf"`；CMD `set "OPENVIKING_CONFIG_FILE=%USERPROFILE%\.openviking\ov.conf"`。

运行：另开终端 `openviking-server`（`curl http://localhost:1933/health` 返回 `"status":"ok"`），然后：
```python
import os
from openviking_sdk import SyncHTTPClient
# 文档示例把方舟 Key 传给本地 OpenViking 服务做 api_key；Agent Plan 换成 ARK_AGENT_PLAN_API_KEY
client = SyncHTTPClient(url="http://localhost:1933", api_key=os.environ["ARK_API_KEY"])
client.initialize()
root = client.add_resource(path="https://raw.githubusercontent.com/volcengine/OpenViking/refs/heads/main/README.md")["root_uri"]
client.wait_processed(timeout=120)                       # 等语义处理完成
print(client.abstract(root), client.overview(root))
for x in client.find("what is openviking", target_uri=root).get("resources", []):
    print(x["uri"], x["score"])                          # 期望：viking://resources/... (score: 0.85xx)
client.close()
```
⚠ 文档未说明：`SyncHTTPClient(api_key=...)` 与 `~/.openviking/ovcli.conf` 里的 `api_key` 填的是方舟 / AP Key，但它发往的是本地 `localhost:1933`；服务端是否拿它去鉴权方舟、还是任意 token 都行，文档没写。

CLI：`~/.openviking/ovcli.conf` = `{"url": "http://localhost:1933", "api_key": "<PLAN_API_KEY>", "output": "table"}`，然后 `openviking observer system` / `openviking add-resource <url>` / `openviking ls viking://resources` / `openviking find "what is openviking"`。HTTP：`POST /api/v1/resources {"path": ...}`、`GET /api/v1/fs/ls?uri=viking://resources/`、`POST /api/v1/search/find {"query": ...}`。
给 OpenClaw 加长期记忆：按 GitHub `examples/openclaw-plugin/INSTALL-ZH.md` 安装插件后，把 `ov.conf` 改成上面的 Plan 配置即可（ArkCLI Helper 的「Agent 记忆（OpenViking）」Harness 会自动做这件事，仅 Agent Plan）。

## 16. 报错与排查汇总（文档原文 + 部分实测）

标「实测」的行是 **已用真实 API 验证（2026-09-04，Agent Plan Medium）**拿到的原始报错；其余为文档原文，未实测。

| 现象 | 工具 | 原因 / 处理 |
|---|---|---|
| **额度烧得比预期快，但没报错**（实测） | Claude Code 及所有 Anthropic 协议工具 | 没显式设模型名 → 请求里的 `claude-*` 被 `/api/plan` 静默路由到 `doubao-seed-2.1-turbo`（响应 `"model":"doubao-seed-2-1-turbo-260628"`，系数 2.5）。配全 `ANTHROPIC_MODEL` / `ANTHROPIC_DEFAULT_*_MODEL` / `CLAUDE_CODE_SUBAGENT_MODEL` |
| `401 {"error":{"code":"AuthenticationError","message":"The API key or AK/SK in the request is missing or invalid. ..."}}`（实测） | 所有工具 | Key 与 Base URL 不配对：AP Key 打 `/api/v3` 或 `/api/coding/v3` 就是这个错。先查 URL 里的 `plan` / `coding`，再查 Key |
| `404 {"error":{"code":"UnsupportedModel","message":"The requested model does not support the agent plan feature. ..."}}`（实测） | 所有工具 | 三种情况同一文案：① `model` 写了 `auto`（改 `ark-code-latest` + 控制台选 Auto）；② 套餐外模型（如 Medium 填视频模型、`doubao-seed-2.1-pro`）；③ 老的带日期 Model ID（`doubao-seed-1-8-251228`）。注意套餐内模型的带日期 ID 会被接受但静默换成当前版本 |
| `400 ... service_tier ... fast service tier does not support coding plan`（实测） | 带 `service_tier` 默认值的 SDK / 工具 | Plan 入口不支持 `service_tier: "fast"`，去掉该字段 |
| 400 `InvalidParameter`「thinking.type `disabled` is not supported by this model」（实测） | 配了关闭思考的工具 + `glm-5.3` | glm-5.3 不能关思考；去掉 `disabled`，或用 `reasoning_effort: "low"`（实测 `reasoning_tokens: 0`）；`reasoning_effort: "none"` 同样 400 |
| kimi 模型回答为空、`finish_reason: "length"`（实测，`kimi-k3`） | 设了较小 `max_tokens` 的工具 | kimi 的 `max_tokens` 含思维链，会把回答截空；给足或改 `max_completion_tokens`。豆包模型的 `max_tokens` 不限制思维链 |
| Claude Code 配置后不生效 | Claude Code | 本地已有 `ANTHROPIC_*` 环境变量（`.bashrc` / `.zshrc`）冲突 → `unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL`，备份并删掉 rc 文件里的旧变量 |
| 加 `[1m]` 后提示模型不存在 | Claude Code | 升级 Claude Code 到最新版 |
| 额度被静默消耗 | Claude Code | 遥测走了 `ANTHROPIC_BASE_URL` → `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` |
| `HTTP 400 … invalid value: developer, supported values are: system, assistant, user, tool.`（报错原文实测，`code: InvalidParameter`） | OpenClaw（及任何发 `developer` role 的 OpenAI 客户端） | 方舟不支持 `developer` role → model 级 `"compat": {"supportsDeveloperRole": false}`（放 provider 级会报 `Unrecognized key: "compat"`，此条文档原文） |
| OpenClaw 不识别图片 | OpenClaw | 模型 `input` 加 `"image"`；`agents.defaults.imageModel.primary` 指向支持图片的模型；重启 gateway |
| `gateway connect failed: Error: pairing required` | OpenClaw 安装时 | `rm -rf ~/.openclaw/devices ~/.openclaw/identity && openclaw gateway install --force && openclaw gateway start` |
| `run error: 404 The model or endpoint xxx does not exist or you do not have access to it` | OpenClaw | `~/.openclaw/openclaw.json`（全局）与 `~/.openclaw/agents/main/agent/models.json`（单 Agent，优先级高）的 baseUrl 等不一致 → 删后者，按全局配置重启 |
| `model not found` | ZCode 等 | 配置里列了套餐不支持的模型 → 删掉对应条目 |
| `4011` | OpenAI4S 专业数据集 | Key 无效 / 额度不足 / Agent Plan 未开专业数据集 Harness |
| `pip install openviking` 报 `No matching distribution found` | OpenViking | Python < 3.10 |
| Cursor 自定义模型名冲突 | Cursor | `glm-5.3` → `glm-5-3` 等，`.` 换 `-` |
| 走 `/api/v3` 被后付费扣费 | 所有工具 | Base URL 必须是 `/api/plan[/v3]` 或 `/api/coding[/v3]` |
| 在非 AI 工具里用 Plan 的 URL + Key | — | 可能被判滥用，「导致订阅停用或账号封禁」 |

错误码全表见文档「错误码」页（DocumentID 1299023，不在本文件范围）。

## 来源页面
Agent Plan 个人版：
- 快速开始 — https://www.volcengine.com/docs/82379/2373738 — 2026-08-28
- Claude Code — https://www.volcengine.com/docs/82379/2373740 — 2026-08-26
- Codex — https://www.volcengine.com/docs/82379/2556054 — 2026-08-24
- OpenCode — https://www.volcengine.com/docs/82379/2373741 — 2026-08-28
- OpenClaw — https://www.volcengine.com/docs/82379/2373742 — 2026-08-28
- Hermes Agent — https://www.volcengine.com/docs/82379/2373743 — 2026-08-24
- TRAE — https://www.volcengine.com/docs/82379/2389869 — 2026-08-24
- 其他工具（Cline / Cursor / Roo Code / Kilo Code） — https://www.volcengine.com/docs/82379/2373746 — 2026-08-28
- Pi — https://www.volcengine.com/docs/82379/2666474 — 2026-08-28
- ZCode — https://www.volcengine.com/docs/82379/2628970 — 2026-08-28
- WorkBuddy — https://www.volcengine.com/docs/82379/2628963 — 2026-08-28
- DeepSeek Harness — https://www.volcengine.com/docs/82379/2637928 — 2026-08-28
- OpenAI4S — https://www.volcengine.com/docs/82379/2664199 — 2026-08-26
- OpenViking — https://www.volcengine.com/docs/82379/2373745 — 2026-08-24

Coding Plan 个人版：
- 快速开始 — https://www.volcengine.com/docs/82379/1928261 — 2026-08-28
- Claude Code — https://www.volcengine.com/docs/82379/1928262 — 2026-08-28
- Codex — https://www.volcengine.com/docs/82379/2556056 — 2026-08-28
- OpenCode — https://www.volcengine.com/docs/82379/2188958 — 2026-08-28
- OpenClaw — https://www.volcengine.com/docs/82379/2183190 — 2026-08-28
- Hermes Agent — https://www.volcengine.com/docs/82379/2318283 — 2026-08-28
- TRAE — https://www.volcengine.com/docs/82379/2205646 — 2026-08-28
- 其他工具（Cline / Cursor / Roo Code / Kilo Code） — https://www.volcengine.com/docs/82379/2188959 — 2026-08-28
- Pi — https://www.volcengine.com/docs/82379/2666476 — 2026-08-28
- ZCode — https://www.volcengine.com/docs/82379/2628972 — 2026-08-28
- WorkBuddy — https://www.volcengine.com/docs/82379/2628965 — 2026-08-28
- DeepSeek Harness — https://www.volcengine.com/docs/82379/2637930 — 2026-08-28
- OpenViking — https://www.volcengine.com/docs/82379/2288685 — 2026-08-28
- 常见问题（思考模式 / developer role / 图片 / pairing / 404 / Ark Helper） — https://www.volcengine.com/docs/82379/2165245 — 2026-08-24

真实 API 验证记录：`volcengine-ark-workspace/verification-findings.md`、`verification-log.jsonl` — 2026-09-04（Agent Plan Medium 专属 Key，`/api/plan/v3` 与 `/api/plan/v1/messages`；Coding Plan 入口仅验证了 AP Key 打过去返回 401）
