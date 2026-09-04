# Claude Code 切到火山方舟 Agent Plan：`~/.claude/settings.json` 逐项说明

配置目标：主模型 `glm-5.3`、轻量任务 `doubao-seed-2.0-mini`、开深度思考、开 1M 上下文、关掉会吃 AFP 额度的后台遥测。完整文件见同目录 `settings.json`，本文解释每一项为什么这么填，以及几个不这么填就会"不报错但白烧额度"的坑。

> 依据：volcengine-ark skill 的 `SKILL.md`、`references/tools-setup.md` §1/§3/§16、`references/agent-plan.md` §2/§3/§5/§6/§7/§12、`references/models.md` §5。标 **实测** 的结论来自 skill 于 2026-09-04 用 Agent Plan Medium 专属 Key 打真实 API 的验证记录；其余为官方文档转录。

## 0. 先做两件事

1. **拿对 Key**：Agent Plan 控制台（`console.volcengine.com/ark/region:cn-beijing/subscription/agent-plan`）→ 使用配置 → 第 3 步「配置专属 API Key」。这把 **Agent Plan 专属 Key** 和「API Key 管理」页的方舟 API Key **互不通用**。实测：拿 Agent Plan Key 打 `/api/v3` 或 `/api/coding/v3` 直接 401 `AuthenticationError`；反过来方舟 Key 打 `/api/plan` 也不会生效。
2. **清掉 shell 里的旧变量**（文档原话）：`unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL`，并检查 `~/.zshrc` / `~/.bashrc` 里有没有残留的 `ANTHROPIC_*`。shell 环境变量会覆盖 `settings.json`，是"配了不生效"的头号原因。

如果你现在的 `~/.claude/settings.json` 里已经有 `permissions`、`hooks` 等其他字段，只把下面的 `env` 块合并进去，不要整文件覆盖。

## 1. 逐项说明

### `ANTHROPIC_BASE_URL` = `https://ark.cn-beijing.volces.com/api/plan`

Agent Plan 的 **Anthropic 协议**入口，Claude Code 实际打的是 `POST /api/plan/v1/messages`（实测 200，返回标准 Anthropic Message，流式为标准 Anthropic SSE）。同域名下另外两套入口都不能用：

| 入口 | 结果 |
|---|---|
| `/api/v3`（标准后付费） | 用 Agent Plan Key → 401；用方舟 Key → 能通，但**走后付费余额扣钱，不消耗套餐**（控制台原话「接入会产生额外费用」） |
| `/api/coding`（Coding Plan） | 用 Agent Plan Key → 401 |
| `/api/plan/v3` | 这是 OpenAI 协议入口，给 Codex / OpenCode 用的；Claude Code 不要带 `/v3` |

### `ANTHROPIC_AUTH_TOKEN` = Agent Plan 专属 API Key

Claude Code 把它作为 `Authorization: Bearer <Key>` 发出；实测 `/api/plan` 对 Bearer 和 `x-api-key` 两种头都接受，所以用 `ANTHROPIC_AUTH_TOKEN` 即可。`settings.json` 的 `env` 值是**字面字符串**，Claude Code 不会展开 `$ARK_AGENT_PLAN_API_KEY` 之类的写法，所以 Key 只能直接写进去——请把文件权限收紧（`chmod 600 ~/.claude/settings.json`），并且不要把这份文件提交到任何仓库。Key 泄露时在控制台「更新 API KEY」轮换（一个账号只有一把，旧 Key 立即失效）。

### 五个模型变量：一个都不能省

| 变量 | 值 | 为什么 |
|---|---|---|
| `ANTHROPIC_MODEL` | `glm-5.3[1m]` | 主模型。`glm-5.3` 是 Agent Plan 四档都可用的旗舰编程模型，1024k 上下文 / 128k 输出；`[1m]` 后缀是 Claude Code 开 1M 上下文的官方写法（见下文） |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | `glm-5.3[1m]` | Claude Code 内部"Opus 档"（复杂任务）映射到主模型 |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | `glm-5.3[1m]` | "Sonnet 档"（日常任务）同样映射到主模型 |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | `doubao-seed-2.0-mini` | "Haiku 档"是 Claude Code 后台的轻量任务（会话标题、快速总结、部分工具辅助调用等）。文档建议「Haiku 建议设置为小尺寸模型」；`doubao-seed-2.0-mini` 是 Agent Plan 内 AFP 系数最低的模型（0.25，glm-5.3 是 4.5，差 18 倍），四档套餐都可用，且**仅 Agent Plan 有**，Coding Plan 列表里没有它。**注意这里不加 `[1m]`**：mini 的上下文是 256k，不在 1M 支持列表里 |
| `CLAUDE_CODE_SUBAGENT_MODEL` | `glm-5.3[1m]` | 子 Agent 用的模型，文档建议「与主模型保持一致」。如果你更在意省额度，可以改成 `doubao-seed-2.0-lite`（系数 0.5）之类，但子 Agent 通常承担真实的搜索 / 编码工作，用 mini 会明显掉效果 |

**为什么必须全填、不能只配 Base URL + Key**（这是本平台最贵的一个坑，实测）：不设模型变量时 Claude Code 发出的是 `claude-sonnet-4-5` 之类的原生模型名，`/api/plan` **不报错**，而是静默路由到 `doubao-seed-2.1-turbo`（响应 `"model":"doubao-seed-2-1-turbo-260628"`），按 2.5 系数扣 AFP——连 Haiku 位的后台小任务也会打到 2.1-turbo。漏掉任何一个 `ANTHROPIC_DEFAULT_*_MODEL`，对应档位就会掉进这个默认路由。

其他关于模型名的规则：
- Plan 入口填的是**小写 Model Name**（`glm-5.3`、`doubao-seed-2.0-mini`，版本号用点），不是标准 API 那种带日期的 Model ID（`doubao-seed-2-0-mini-260428`）。带日期 ID 实测会被接受但版本号被无视。
- **不能填 `auto`**（实测 404 `UnsupportedModel`）。想用控制台的 Auto 智能路由，填 `ark-code-latest` 并在控制台选 Auto——但那样你就无法固定 glm-5.3 了，所以本配置不用。
- `glm-latest` 是 `glm-5.3` 的别名（实测有效），以后 glm 升级版本时能自动跟随。想省得改配置可以把三处 `glm-5.3[1m]` 换成 `glm-latest[1m]`；本文件用显式名字是为了和你的要求一一对应，且 `glm-latest[1m]` 这种别名 + 后缀的组合 skill 没有实测。

### 1M 上下文：`[1m]` 后缀 + `CLAUDE_CODE_AUTO_COMPACT_WINDOW`

文档（Claude Code 页 §3.4）给出的做法有两步，缺一不可：
1. 模型名加 `[1m]` 后缀 → `glm-5.3[1m]`。支持 1M 的 Plan 内模型只有 `glm-5.3`、`glm-5.3-flash`、`deepseek-v4-flash`、`deepseek-v4-pro`、`kimi-k3`（及 `doubao-seed-evolving`）；`doubao-seed-2.0-mini` / `2.0-lite` / `2.1-turbo` 都是 256k，**不要**给它们加后缀。
2. `"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "1000000"`：把 Claude Code 自动压缩上下文的触发阈值抬到 1M，否则模型虽然能吃 1M，Claude Code 仍会在默认窗口附近就开始 compact。

文档提示：「若模型参数加上 `[1m]` 后缀后，Claude Code 识别模型不存在，需升级 Claude Code 到最新版本后重试」（`npm install -g @anthropic-ai/claude-code`）。

代价提醒：2026-09-01 起 AFP 输入系数**不再按输入长度分段**，统一等于模型系数，所以 glm-5.3 每 1M 输入 token ≈ 1,000,000 × 4.5 / 10,000 = **450 AFP**。Medium 档 5 小时额度 10,000 AFP、周额度 35,000 AFP，一次塞满 1M 上下文的请求就是 5 小时额度的 4.5%。真正长任务再用满，平时让它自然 compact 也无妨。

### 思考：`CLAUDE_CODE_EXTRA_BODY` = `{"thinking":{"type":"enabled"}}`

值必须是**字符串化的 JSON**（注意转义），Claude Code 会把它合并进每个请求体。文档 FAQ「Claude Code 如何开启深度思考模式？」给的就是这个写法。

两个模型的实测行为：
- `glm-5.3`：**默认开思考且不可关**——传 `thinking.type: disabled` 会 400 `thinking.type disabled is not supported by this model`，`reasoning_effort: none` 同样 400。所以这里千万不要把值写成 `disabled`，否则 `/model glm-5.3` 后每个请求都会报错。`enabled` 对它是安全的。
- `doubao-seed-2.0-mini`：默认也开思考，`enabled` 同样安全。

思维链在响应里是 `{"type":"thinking",...}` block，Claude Code 原生能显示。思维链 token 计入输出并按系数扣 AFP（glm-5.3 输出系数同样 4.5）。

### 遥测：`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` = `"1"`

文档原文：「关闭 Claude Code 后台匿名遥测请求。遥测请求默认会走 `ANTHROPIC_BASE_URL` 并占用 Plan 配额，设为 `"1"` 可避免额度被静默消耗。」官方的 `arkcli helper` 自动配置会加这一项，手动配置务必带上。文档 §3.4 的 1M 官方示例恰好漏了这一项和 `CLAUDE_CODE_SUBAGENT_MODEL`，本文件已补回。

## 2. 配完之后

```bash
# 跳过首次引导（可选；新终端再启动 claude）
echo '{"hasCompletedOnboarding": true}' > ~/.claude.json   # 若文件已存在，只添加 / 修改这个字段

chmod 600 ~/.claude/settings.json
cd my-project && claude
# 会话内：
/status          # 应显示 glm-5.3[1m]；也可 /model 查看
```

- **不要用 curl 直打 `/api/plan` 做连通性测试**。文档原话：在非 AI 工具中使用 Plan 的 Base URL 和 Key「有可能被识别为滥用 / 违规，会导致订阅停用或账号封禁」。验证就在 Claude Code 里发一句话，然后去控制台「用量统计」核对模型明细（延迟 0.5–1 天）——重点确认明细里出现的是 `glm-5.3` 和 `doubao-seed-2-0-mini-*`，而不是 `doubao-seed-2-1-turbo-*`。
- 临时换模型：`claude --model deepseek-v4-flash[1m]`（本次会话）或对话中 `/model doubao-seed-2.0-lite`。切到 glm 以外的模型时，`CLAUDE_CODE_EXTRA_BODY` 里的 `enabled` 对 Plan 内所有文本模型都合法，无需改。
- Claude Code 原生 Web Search 工具：文档说「通过 Messages API 接入的 Claude Code 也可原生使用 Web Search」，但要先在 Agent Plan 控制台开启「豆包搜索」抵扣（每月 500 次免费，之后 5 AFP/次），否则按后付费计费。

## 3. 额度相关的几个事实（决定你怎么用这套配置）

| 事项 | glm-5.3（主模型） | doubao-seed-2.0-mini（Haiku 位） |
|---|---|---|
| AFP 系数（输入 / 输出） | 4.5 / 4.5，文档标「抵扣系数较高，推荐用于重难点复杂问题，日常建议切换其他模型」 | 0.25 / 0.25，Plan 内最低 |
| 上下文 / 最大输出 | 1024k / 128k | 256k / 128k |
| 套餐档位 | Small / Medium / Large / Max 全部可用 | 全部可用 |
| **超额后付费** | **不支持**：额度耗尽时请求直接失败，不会自动切后付费 | 支持（需实名 + 开通管理已开通该模型） |
| 思考 | 默认开，不可关 | 默认开，可关 |

额度分三档刷新：5 小时（从首次请求起算）/ 周（周一 0 点）/ 月（订阅月首日）。Medium 档为 10,000 / 35,000 / 100,000 AFP。因为 glm-5.3 不支持超额后付费，跑到额度上限时 Claude Code 会开始报错而不是悄悄扣钱；如果需要"不中断"，日常可 `/model deepseek-v4-flash[1m]`（系数 0.5、1M、支持超额后付费）或 `doubao-seed-2.0-lite`（0.5、256k、支持超额后付费）。

## 4. 常见报错对照

| 现象 | 原因 → 处理 |
|---|---|
| 401 `AuthenticationError ... API key or AK/SK ... missing or invalid` | Key 与 Base URL 不配对：填了方舟 API Key，或 Base URL 漏了 `/plan` |
| 404 `UnsupportedModel ... does not support the agent plan feature` | 模型名写成 `auto`、写了套餐外模型（如 `doubao-seed-2.1-pro`）、或写了老的带日期 ID |
| 400 `thinking.type disabled is not supported by this model` | `CLAUDE_CODE_EXTRA_BODY` 里写了 `disabled` 却在用 glm-5.3 → 改回 `enabled` |
| 提示 `glm-5.3[1m]` 模型不存在 | Claude Code 版本太旧 → 升级到最新版 |
| 配置改了不生效 | shell 里有旧的 `ANTHROPIC_*` 变量覆盖了 settings.json → `unset` 并清理 rc 文件，新开终端 |
| 没报错但额度烧得飞快 | 某个 `ANTHROPIC_DEFAULT_*_MODEL` 漏填 → 请求被静默路由到 2.1-turbo（系数 2.5）；或遥测没关 → 补 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` |
