下面这段可以直接合并进 `~/.claude/settings.json`（只含 `env` 一块，把 `<YOUR_KEY>` 换成你在智谱开放平台生成的 API Key 即可）：

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "<YOUR_KEY>",
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

| 变量 | 作用 |
|---|---|
| `ANTHROPIC_AUTH_TOKEN` | 智谱 API Key。Claude Code 会把它作为 Bearer token 发给网关；注意用 `AUTH_TOKEN` 而不是 `ANTHROPIC_API_KEY`。 |
| `ANTHROPIC_BASE_URL` | 智谱提供的 Anthropic 兼容端点（Coding Plan 走这个域名）。 |
| `API_TIMEOUT_MS` | 请求超时时间，调大以免长任务被中断。 |
| `ANTHROPIC_MODEL` | 主模型，指定为 `glm-5.3`。 |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` / `SONNET_MODEL` / `HAIKU_MODEL` | Claude Code 内部按 opus / sonnet / haiku 三档路由模型，这里把前两档映射到 GLM-5.3，haiku 档（用于轻量后台调用）映射到更便宜的 `glm-4.5-air`。 |
| `ANTHROPIC_SMALL_FAST_MODEL` | 旧版本 Claude Code 使用的"小快模型"变量，与 haiku 档保持一致，兼容新旧版本。 |
| `CLAUDE_CODE_SUBAGENT_MODEL` | 子 agent 使用的模型，同样指向 GLM-5.3。 |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | 关闭遥测、自动更新检查等非必要请求，避免向 Anthropic 官方端点发送无关流量。 |

使用注意：

1. 合并时如果 `settings.json` 已有 `env` 对象，把上面的键并进去即可，不要整体覆盖其他配置（如 `permissions`、`hooks`）。
2. 如果你的 shell 里已经 `export` 了 `ANTHROPIC_API_KEY` 或 `ANTHROPIC_BASE_URL`，环境变量优先级更高，记得先清掉，否则会与 settings 冲突。
3. 如果某个模型名报 404 / model not found，请以智谱控制台「Coding Plan」页面列出的可用模型名为准，把对应值替换掉（例如 haiku 档换成 Coding Plan 套餐内的其他小模型）。
4. 改完后重新启动 Claude Code，输入 `/status` 或 `/model` 可以确认当前使用的 base URL 和模型。
