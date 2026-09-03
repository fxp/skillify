# 让 Claude Code 走智谱 GLM Coding Plan（GLM-5.3）

智谱为 Coding Plan 提供了一个 **Anthropic 协议兼容端点**，Claude Code 不需要改代码，只要把 base URL、API Key 和默认模型名换掉即可。

## 方式一：写进 `~/.claude/settings.json`（推荐，全局生效）

把下面内容合并进 `~/.claude/settings.json`（如果文件已有 `env` 字段，把这些键并进去；没有就直接新建）：

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "在这里填你的智谱 API Key",
    "ANTHROPIC_BASE_URL": "https://open.bigmodel.cn/api/anthropic",
    "API_TIMEOUT_MS": "3000000",
    "ANTHROPIC_MODEL": "glm-5.3",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5.3",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.3",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-4.5-air",
    "ANTHROPIC_SMALL_FAST_MODEL": "glm-4.5-air",
    "CLAUDE_CODE_SUBAGENT_MODEL": "glm-5.3",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
  }
}
```

各项说明：

| 键 | 作用 |
|---|---|
| `ANTHROPIC_AUTH_TOKEN` | 智谱开放平台的 API Key（Coding Plan 开通后在 bigmodel.cn 控制台“API Keys”里生成）。注意用 `AUTH_TOKEN` 而不是 `ANTHROPIC_API_KEY`，智谱端点走的是 `Authorization: Bearer` 头。 |
| `ANTHROPIC_BASE_URL` | 智谱的 Anthropic 兼容端点。国内版是 `https://open.bigmodel.cn/api/anthropic`；如果你买的是海外 Z.ai 的 Coding Plan，改成 `https://api.z.ai/api/anthropic`。 |
| `API_TIMEOUT_MS` | 把请求超时拉长到 50 分钟，避免 GLM 长输出/长思考时被 Claude Code 默认超时掐断。 |
| `ANTHROPIC_MODEL` / `ANTHROPIC_DEFAULT_*_MODEL` | Claude Code 内部会按 opus / sonnet / haiku 三档去请求模型，这里把三档都映射到 GLM。主力 `glm-5.3`；haiku 档（用于标题生成、快速小任务）映射到轻量的 `glm-4.5-air` 省额度，也可以一并写成 `glm-5.3`。 |
| `CLAUDE_CODE_SUBAGENT_MODEL` | 子 Agent 使用的模型，同样指到 `glm-5.3`。 |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | 关掉 Claude Code 对 Anthropic 官方的非必要请求（遥测、更新检查等），避免在第三方端点下报错或泄漏流量。 |

保存后，**重新启动 `claude`** 即可。在会话里输入 `/status` 或 `/model`，能看到当前模型是 `glm-5.3`、API 地址是智谱的，就说明生效了。

> 如果之前已经用 Anthropic 账号 `claude login` 过，建议先 `claude logout`（或在 `/status` 里确认认证方式是 API key），否则可能仍优先走官方 OAuth。

## 方式二：等价的环境变量（临时用 / 按项目切换）

不想改全局文件，可以直接在 shell 里导出，效果完全一样（`settings.json` 的 `env` 本质就是启动时注入这些变量）：

```bash
export ANTHROPIC_AUTH_TOKEN="在这里填你的智谱 API Key"
export ANTHROPIC_BASE_URL="https://open.bigmodel.cn/api/anthropic"
export API_TIMEOUT_MS=3000000
export ANTHROPIC_MODEL="glm-5.3"
export ANTHROPIC_DEFAULT_OPUS_MODEL="glm-5.3"
export ANTHROPIC_DEFAULT_SONNET_MODEL="glm-5.3"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="glm-4.5-air"
export ANTHROPIC_SMALL_FAST_MODEL="glm-4.5-air"
export CLAUDE_CODE_SUBAGENT_MODEL="glm-5.3"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

claude
```

想长期生效就把这段追加到 `~/.zshrc`。一个常见的做法是包一个别名，官方 Claude 和 GLM 随时切换：

```bash
alias claude-glm='ANTHROPIC_AUTH_TOKEN="你的Key" ANTHROPIC_BASE_URL="https://open.bigmodel.cn/api/anthropic" ANTHROPIC_MODEL="glm-5.3" API_TIMEOUT_MS=3000000 claude'
```

也可以只在某个项目生效：把同样的 `env` 块写进该项目的 `.claude/settings.json`（或不入库的 `.claude/settings.local.json`），项目级会覆盖全局。

## 几点提醒

1. **模型名请以智谱控制台/文档为准。** 我是凭记忆写的 `glm-5.3` 和 `glm-4.5-air`，Coding Plan 页面会列出你套餐里可用的模型 ID；如果启动后报 `model not found`，把名字改成文档里的即可（其他配置不用动）。
2. **Coding Plan 的 Key 只能走这个 `/api/anthropic` 端点**，不要拿它去调普通的 `/api/paas/v4` 计费接口，也不要拿普通按量计费的 Key 来配这里，套餐额度不通用。
3. `settings.json` 会明文存 Key，注意别把它提交进 git；公司机器建议用方式二放在 shell 配置里。
4. 智谱端点目前不支持 Anthropic 的部分扩展功能（如 prompt caching 统计、web search 内置工具等），Claude Code 会自动降级，属正常现象。

附带文件：`settings.json`（可直接合并到 `~/.claude/settings.json`）、`glm-env.sh`（环境变量版）。
