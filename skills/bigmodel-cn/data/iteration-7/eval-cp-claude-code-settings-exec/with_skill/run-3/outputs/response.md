把下面这段合并进 `~/.claude/settings.json` 即可（只需 `env` 一块，`<YOUR_KEY>` 换成你的 GLM Coding Plan API Key）：

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

- **Key 用 `ANTHROPIC_AUTH_TOKEN`，不是 `ANTHROPIC_API_KEY`**。Claude Code 读这个变量作为 Bearer token。
- **Key 必须是 Coding Plan 套餐的 Key**（个人版在 `https://bigmodel.cn/coding-plan/personal/overview` 里新建；团队版用「团队编程套餐 > 我的套餐」里的团队 Key）。开放平台按量付费的 Key 与套餐 Key 不通用——填平台 Key 也能跑，但走的是按 token 计费，不扣套餐额度。
- **Base URL 就是 `https://open.bigmodel.cn/api/anthropic`**，不要在后面再加 `/v1`（Claude Code 的 SDK 会自己拼 `/v1/messages`）。这个 Anthropic 兼容地址与标准 API 共用，靠 Key 区分走哪套额度。
- **三个 `ANTHROPIC_DEFAULT_*_MODEL` 不能省**：它们把 Claude Code 内部对 haiku / sonnet / opus 的引用映射到 `glm-5.3-flash` / `glm-5.3`，否则 Claude Code 会去请求不存在的 `claude-*` 模型名。主模型和 opus 都指向 `glm-5.3`，后台小任务（haiku 档）用更便宜的 `glm-5.3-flash`。
- 如果之前在 shell 里 `export` 过 `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL`，注意别和这里冲突。
- 套餐额度按 5 小时 + 每周两档滚动重置，用尽不会自动扣账户余额；如果套餐到期后报错，把 Base URL 改回标准 API、换平台 Key 即可继续走按量计费。
- 若遇到 `1113 余额不足`，先检查是不是 Key / Base URL 用错了组合（套餐 Key 打到了标准端点），不要急着充值。
