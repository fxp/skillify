把下面这段合并进 `~/.claude/settings.json`（如果文件里已有 `env`，把这些键并进去即可；`<YOUR_KEY>` 换成你在 `https://bigmodel.cn/coding-plan/personal/overview` 里新建的 **Coding Plan 专用 Key**，不是开放平台按量付费的 Key）：

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

几个要点：

- **变量名是 `ANTHROPIC_AUTH_TOKEN`**，不是 `ANTHROPIC_API_KEY`——Claude Code 把它当 Bearer token 发给智谱。
- **Base URL 是 `https://open.bigmodel.cn/api/anthropic`**（Anthropic 兼容层），不要加 `/v1`，Claude Code 的 SDK 会自己拼 `/v1/messages`。这个地址和标准 API 的 Anthropic 兼容层是同一个，走套餐额度还是按量计费完全由 Key 决定。
- 三个 `ANTHROPIC_DEFAULT_*_MODEL` 把 Claude Code 内部对 haiku / sonnet / opus 的引用映射到 GLM：sonnet 和 opus 都指向 `glm-5.3`，haiku 指向更快更省额度的 `glm-5.3-flash`（用于子任务、标题生成等轻量调用）。不配的话 Claude Code 会去请求不存在的 `claude-*` 模型名。
- `API_TIMEOUT_MS` 调大是因为 GLM-5.3 在长任务里思考时间可能很长；`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` 关掉 Claude Code 对 Anthropic 官方的非必要请求。
- 如果改完启动 Claude Code 报 `1113 余额不足`，**不是要充值**——多半是 Key 用成了开放平台的按量 Key，或者 Key 没填对；排查顺序是先确认 Key 属于 Coding Plan，再核对 Base URL，最后才看额度。
- 套餐额度按 5 小时 / 7 天两档滚动重置，用完不会自动扣账户余额，等窗口刷新即可。

改完重启 Claude Code 生效；也可以用 `export ANTHROPIC_AUTH_TOKEN=... ANTHROPIC_BASE_URL=...` 等 shell 环境变量代替，效果相同。
