下面这段可以直接合并进 `~/.claude/settings.json`（只含 `env` 部分，把 `<YOUR_KEY>` 换成你在智谱开放平台生成的 API Key）：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://open.bigmodel.cn/api/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "<YOUR_KEY>",
    "ANTHROPIC_MODEL": "glm-5.3",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5.3",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.3",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-5.3",
    "API_TIMEOUT_MS": "3000000",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
  }
}
```

各项说明：

- `ANTHROPIC_BASE_URL`：智谱国内站的 Anthropic 兼容端点（GLM Coding Plan 走这个）。如果你买的是海外 Z.ai 的套餐，改成 `https://api.z.ai/api/anthropic`。
- `ANTHROPIC_AUTH_TOKEN`：填智谱的 API Key。注意用 `AUTH_TOKEN` 而不是 `ANTHROPIC_API_KEY`，并确保 shell 里没有残留的 `ANTHROPIC_API_KEY` 环境变量，否则会优先使用它。
- `ANTHROPIC_MODEL` + 三个 `ANTHROPIC_DEFAULT_*_MODEL`：把 Claude Code 内部对 Opus / Sonnet / Haiku 的请求全部映射到 `glm-5.3`，这样 `/model` 切换、子代理、后台小任务都不会落回 Anthropic 的模型名。如果想省额度，可以把 `HAIKU` 那一项换成套餐里更轻量的模型（例如 `glm-4.7-flash` 之类，以你控制台里的可用模型列表为准）。
- `API_TIMEOUT_MS`：GLM 长上下文/长推理时响应较慢，把超时拉长到 50 分钟避免中途断开。
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`：关掉遥测等非必要请求，减少对 Anthropic 域名的访问。

合并后重新打开 Claude Code，运行 `/status` 应能看到 Base URL 指向 `open.bigmodel.cn`、模型显示 `glm-5.3`。
