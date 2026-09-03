下面这段直接合并进 `~/.claude/settings.json` 即可（只含 `env` 一块，把 `<YOUR_KEY>` 换成你的 GLM Coding Plan Key）：

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "<YOUR_KEY>",
    "ANTHROPIC_BASE_URL": "https://open.bigmodel.cn/api/anthropic",
    "API_TIMEOUT_MS": "3000000",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-5.3-flash",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.3",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5.3"
  }
}
```

几个容易踩坑的点：

1. **Key 要用 Coding Plan 的 Key**，不是开放平台按量付费的 API Key。个人版在 `https://bigmodel.cn/coding-plan/personal/overview` 里新建；团队版用「团队编程套餐 > 我的套餐」里的团队 Key。两套 Key 不通用，用平台 Key 填进去也能跑，但走的是按 token 计费而不是套餐额度。
2. **变量名是 `ANTHROPIC_AUTH_TOKEN`**，不是 `ANTHROPIC_API_KEY`。Claude Code 把它当 Bearer token 发给智谱。
3. **Base URL 就是 `https://open.bigmodel.cn/api/anthropic`**，不要在后面加 `/v1`（Claude Code 的 SDK 自己会拼 `/v1/messages`）。这个地址和标准 API 的 Anthropic 兼容层是同一个，走套餐额度还是走余额完全由 Key 决定。
4. **三个 `ANTHROPIC_DEFAULT_*_MODEL` 不能省**：它们把 Claude Code 内部对 haiku / sonnet / opus 的引用映射到 `glm-5.3-flash` / `glm-5.3`，否则 Claude Code 会去请求不存在的 `claude-*` 模型名。套餐所有档位都支持 `glm-5.3` 和 `glm-5.3-flash`，这两个名字最稳，不要写旧代码（如 `glm-4.7`），旧代码会被静默路由到新版本，日志里看到的模型名会和配置不一致。
5. 如果之后看到 **HTTP 429 + `1113 余额不足或无可用资源包`**，不是要充值，而是 Key/Base URL 组合用错了（套餐 Key 打到了 `…/api/paas/v4` 标准端点）。排查顺序：先确认 Key 属于哪套体系 → 再核对 Base URL → 再核对模型名 → 最后才考虑额度。
6. 套餐额度是每 5 小时滚动重置一档 + 每 7 天重置一档，用完不会自动扣账户余额，等窗口刷新即可。

如果不想改 `settings.json`，用 shell 环境变量 `export ANTHROPIC_AUTH_TOKEN=... ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic ...` 也是等价的。
