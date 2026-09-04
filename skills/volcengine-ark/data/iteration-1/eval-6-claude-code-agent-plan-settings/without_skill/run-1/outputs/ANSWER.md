# Claude Code 切到火山方舟 Agent Plan：`~/.claude/settings.json` 说明

> 说明：本文件是**建议稿**，没有改动真实的 `~/.claude/settings.json`。
> 使用方式：把 `settings.json` 里的 `ANTHROPIC_AUTH_TOKEN` 占位符换成你的方舟 API Key，
> 然后复制到 `~/.claude/settings.json`（如已有文件，把 `env` / `model` 两块合并进去），重开 Claude Code。
> 如果之前用 `claude login` 登过 Anthropic 账号，先 `/logout`，否则 OAuth 登录态会优先于 `ANTHROPIC_AUTH_TOKEN`。
>
> 以下内容基于我对 Claude Code 与火山方舟 Anthropic 兼容接口的既有认知（没有查阅最新文档），
> 标注 ⚠️ 的项请到方舟控制台 / 文档核对一次（模型 ID、Base URL、Agent Plan 是否与 Coding Plan 共用网关）。

---

## 一、接入方舟（网关 + 鉴权）

| 键 | 值 | 作用 |
|---|---|---|
| `env.ANTHROPIC_BASE_URL` | `https://ark.cn-beijing.volces.com/api/coding` | 把 Claude Code 所有 `/v1/messages` 请求打到方舟的 Anthropic 兼容网关。⚠️ 这是 Coding Plan 的地址，Agent Plan 大概率沿用同一网关；若控制台给的是别的地址（例如 `.../api/v3`），以控制台为准。 |
| `env.ANTHROPIC_AUTH_TOKEN` | 你的方舟 API Key | 以 `Authorization: Bearer <key>` 方式鉴权，方舟网关认这个头。**填了 Key 后不要把 settings.json 提交进任何仓库。** |
| `env.ANTHROPIC_API_KEY` | `""`（空） | 显式清空，避免 shell 里残留的 Anthropic 官方 Key 与 `AUTH_TOKEN` 同时存在时 Claude Code 弹出"检测到冲突凭据"的提示。不想要这行可以删掉。 |

> 更安全的做法：把 `ANTHROPIC_AUTH_TOKEN` 从文件里去掉，改用 `"apiKeyHelper": "security find-generic-password -s ark-agent-plan -w"` 之类的命令从 macOS Keychain 读 Key。这里为了"一个文件即可用"没有这么写。

## 二、模型路由（主模型 glm-5.3，轻量任务 doubao-seed-2.0-mini）

Claude Code 内部把模型分三档：Opus（重）/ Sonnet（主力）/ Haiku（轻量、后台）。第三方网关下必须把三档都显式映射，否则它会去请求 `claude-*` 的官方模型名，方舟直接 404。

| 键 | 值 | 作用 |
|---|---|---|
| `model` 与 `env.ANTHROPIC_MODEL` | `glm-5.3[1m]` | 会话默认主模型。两处写一致是为了兼顾不同版本的 Claude Code（旧版只读 env，新版优先读顶层 `model`）。 |
| `env.ANTHROPIC_DEFAULT_OPUS_MODEL` | `glm-5.3[1m]` | 在 Claude Code 里输入 `/model opus` 时解析到的模型；一并指到 glm-5.3，防止误切到不存在的 Claude 模型。 |
| `env.ANTHROPIC_DEFAULT_SONNET_MODEL` | `glm-5.3[1m]` | 同上，`/model sonnet` 的映射。 |
| `env.ANTHROPIC_DEFAULT_HAIKU_MODEL` | `doubao-seed-2.0-mini` | **轻量任务**走的模型：会话标题生成、`@` 文件补全摘要、上下文压缩（`/compact` 的部分步骤）、快速判断类内部调用等。这些调用频繁但简单，用 mini 省额度。 |
| `env.ANTHROPIC_SMALL_FAST_MODEL` | `doubao-seed-2.0-mini` | 旧版 Claude Code 里同一用途的旧名字，已被 `ANTHROPIC_DEFAULT_HAIKU_MODEL` 取代；两者同时写可以覆盖新旧版本。 |
| `env.CLAUDE_CODE_SUBAGENT_MODEL` | `glm-5.3[1m]` | 子代理（`Agent` 工具派出的 Explore / general-purpose 等）用的模型。子代理经常要读大量代码并给结论，我保留了 glm-5.3；如果你想更省额度，把它改成 `doubao-seed-2.0-mini`。 |

⚠️ `glm-5.3`、`doubao-seed-2.0-mini` 请在方舟"模型广场 → Agent Plan 可用模型"里核对准确 ID（方舟模型 ID 有时带版本后缀，如 `doubao-seed-2.0-mini-2xxxxx`，也可能需要先在控制台开通该模型）。

## 三、开思考（Extended Thinking）

| 键 | 值 | 作用 |
|---|---|---|
| `alwaysThinkingEnabled` | `true` | Claude Code 顶层开关，等价于在 `/config` 里把 Thinking mode 打开：每一轮请求都带 `thinking: {type: "enabled", budget_tokens: ...}`，而不是只在提示词里出现 "think" 时才开。 |
| `env.MAX_THINKING_TOKENS` | `32000` | 思考预算上限（`budget_tokens`）。GLM 系列在方舟上属于"开关式"思考（enabled/disabled），网关一般会接受并忽略具体预算；给 32000 是为了让 Claude Code 端不要把预算设得过低导致中途截断。如果发现 mini 模型不支持 thinking 而报 400，可把这个值调小或去掉；主模型仍会因 `alwaysThinkingEnabled` 开启思考。 |

## 四、开 1M 上下文

| 键 | 值 | 作用 |
|---|---|---|
| 模型名后缀 `[1m]` | `glm-5.3[1m]` | 这是 Claude Code 自己的记号：见到 `[1m]` 后缀，它会**去掉后缀**再发送模型名，并在请求头加 `anthropic-beta: context-1m-2025-08-07`，同时把本地的上下文预算/自动压缩阈值按 1M 计算（否则会在 ~200K 就开始自动 `/compact`）。 |

⚠️ 两个前提请核对：
1. 方舟上的 glm-5.3 实际支持的上下文长度确实 ≥ 1M（若只有 200K/256K，`[1m]` 只是让 Claude Code 不提前压缩，超长请求会被网关拒绝）。
2. 方舟网关对未知的 `anthropic-beta` 头是**忽略**而不是报错。据我了解方舟是忽略的；若报 400，去掉 `[1m]` 后缀并改用 `"env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": ...}` 一类的本地阈值参数（不同版本名称不同，以 `claude --help` / 文档为准）。

配套的两个参数：

| 键 | 值 | 作用 |
|---|---|---|
| `env.CLAUDE_CODE_MAX_OUTPUT_TOKENS` | `32000` | 单次回复最大输出。长上下文 + 思考模式下，默认值（通常 8K~32K，随版本变化）可能不够写大文件；32K 在 GLM 的输出上限之内。 |
| `env.API_TIMEOUT_MS` | `600000` | 单请求超时 10 分钟。1M 上下文 + 深度思考，首 token 可能等很久，默认超时会误报失败并重试（重试也是在烧额度）。 |

## 五、别让遥测 / 后台流量偷吃额度

先澄清一点：Claude Code 的**遥测本身**（Statsig 事件、Sentry 错误报告）是发到 Anthropic 的，不走你的方舟 Key，不消耗额度。真正会"偷吃"方舟额度的是它**后台发起的模型调用**。所以下面两类都关掉：

### 5.1 真正吃额度的：后台模型调用

| 键 | 值 | 作用 |
|---|---|---|
| `env.DISABLE_NON_ESSENTIAL_MODEL_CALLS` | `1` | **最关键的一项。** 关闭非必要的模型调用：会话标题/摘要自动生成、终端里那些"正在思考中的花式文案"、某些建议提示等。这些都会走 Haiku 档（也就是 mini），每次都是一笔真实的方舟请求。 |
| `env.DISABLE_COST_WARNINGS` | `1` | 关掉基于 Anthropic 官方定价算出来的花费提醒——在方舟计划下这个数字是错的，而且只会制造噪音。 |
| Haiku 档映射到 mini | 见第二节 | 即便还有少量必要的轻量调用（比如上下文压缩），也确保它们走最便宜的 mini 而不是 glm-5.3。 |

### 5.2 不吃额度但也没必要往外发的：遥测 / 自动更新 / 错误上报

| 键 | 值 | 作用 |
|---|---|---|
| `env.CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | `1` | 一键总开关：等价于同时设置下面的 `DISABLE_AUTOUPDATER`、`DISABLE_BUG_COMMAND`、`DISABLE_ERROR_REPORTING`、`DISABLE_TELEMETRY`。 |
| `env.DISABLE_TELEMETRY` | `1` | 关闭 Statsig 使用统计上报。 |
| `env.DISABLE_ERROR_REPORTING` | `1` | 关闭 Sentry 错误上报。 |
| `env.DISABLE_BUG_COMMAND` | `1` | 禁用 `/bug`（它会把会话片段发给 Anthropic）。 |
| `env.DISABLE_AUTOUPDATER` | `1` | 关闭自动更新检查/下载。顺带好处：版本固定后，模型映射的 env 名字不会因升级悄悄变化。想升级时手动 `npm i -g @anthropic-ai/claude-code`。 |
| `env.CLAUDE_CODE_ENABLE_TELEMETRY` | `0` | 确保 OpenTelemetry 导出（metrics/logs）关闭。默认就是关的，这里显式写出以防某个企业策略/环境变量把它打开。 |

上面几个总开关和单项有重叠，是刻意的：不同版本的 Claude Code 对总开关的覆盖范围略有差别，单项写全最稳。

## 六、其他

| 键 | 值 | 作用 |
|---|---|---|
| `$schema` | JSON Schema 地址 | 让 VS Code 等编辑器对 settings.json 做补全和校验，不影响运行。 |
| `includeCoAuthoredBy` | `false` | 由 Claude Code 生成的 git commit 不再自动追加 `Co-Authored-By: Claude` 尾注。与额度无关，属个人偏好，可删。 |
| `cleanupPeriodDays` | `30` | 本地会话记录保留 30 天后自动清理。与额度无关，可删。 |

## 七、上手后自检清单

1. `claude` 启动后输入 `/status`（或 `/config`），确认显示的 API Base URL 是方舟地址、模型是 `glm-5.3[1m]`。
2. 随便问一句，观察响应是否带思考过程（有 thinking 块会在界面上显示"Thinking…"折叠区）。
3. 到方舟控制台"用量"页面看：主对话计入 glm-5.3，且应**几乎没有** doubao-seed-2.0-mini 的零散调用（只有压缩上下文时才会有）；如果 mini 调用很多，说明 `DISABLE_NON_ESSENTIAL_MODEL_CALLS` 没生效（检查是否被 shell 里的同名环境变量覆盖）。
4. 如果启动就报 `model not found`：大概率是模型 ID 与方舟实际 ID 不一致，或该模型未在 Agent Plan 内开通。
5. 如果报与 `anthropic-beta` 相关的 400：去掉所有 `[1m]` 后缀再试。

## 八、我不确定、需要你核对的点（汇总）

- Agent Plan 的 Base URL 是否与 Coding Plan 相同（`/api/coding`）。
- `glm-5.3`、`doubao-seed-2.0-mini` 在方舟上的准确模型 ID，以及它们是否在 Agent Plan 的可用模型列表里。
- glm-5.3 在方舟上的真实上下文上限是否达到 1M；方舟网关是否忽略 `context-1m-2025-08-07` 这个 beta 头。
- doubao-seed-2.0-mini 是否接受 `thinking` 参数（不接受时轻量调用可能报 400；届时可把 `MAX_THINKING_TOKENS` 去掉，只靠 `alwaysThinkingEnabled` 对主模型生效，或给 mini 换一个支持思考的模型）。
