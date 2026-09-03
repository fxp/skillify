下面这段可以直接合并进 `~/.claude/settings.json`（只含 `env` 一块，把 `<YOUR_KEY>` 换成你在智谱开放平台生成的 API Key）：

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "<YOUR_KEY>",
    "ANTHROPIC_BASE_URL": "https://open.bigmodel.cn/api/anthropic",
    "ANTHROPIC_MODEL": "glm-5.3",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5.3",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.3",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-4.5-air",
    "CLAUDE_CODE_SUBAGENT_MODEL": "glm-5.3",
    "API_TIMEOUT_MS": "3000000",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
  }
}
```

各字段说明：

| 字段 | 作用 |
|---|---|
| `ANTHROPIC_AUTH_TOKEN` | 智谱 API Key（Coding Plan 的 Key 直接填这里；用 `AUTH_TOKEN` 而不是 `API_KEY`，网关按 Bearer 方式鉴权） |
| `ANTHROPIC_BASE_URL` | 智谱的 Anthropic 兼容网关（国内站）。如果你买的是海外 Z.ai 的 Coding Plan，改成 `https://api.z.ai/api/anthropic` |
| `ANTHROPIC_MODEL` / `*_OPUS_MODEL` / `*_SONNET_MODEL` | Claude Code 内部按 opus/sonnet 档位选模型，这三项统一映射到 `glm-5.3`，保证 `/model` 切换或默认模型都落到 GLM-5.3 |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | haiku 档位负责标题生成、轻量分类等后台小任务，映射到便宜快速的 `glm-4.5-air` 即可；想全走 5.3 也可以改成 `glm-5.3` |
| `CLAUDE_CODE_SUBAGENT_MODEL` | 子 agent（Task/Agent 工具）使用的模型 |
| `API_TIMEOUT_MS` | 超时拉长到 50 分钟，避免长推理/大 diff 场景下被 Claude Code 默认超时掐断 |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | 关闭遥测、自动更新检查等非必要请求，减少对 Anthropic 官方域名的无谓访问 |

几点注意：

1. 合并时如果 `settings.json` 里已经有 `env` 对象，把上面这些键合进去即可，不要整个覆盖掉原有的 `permissions`、`hooks` 等配置。
2. 确认你的 Coding Plan 套餐里确实包含 `glm-5.3` 这个模型 ID；如果控制台里显示的名字不同（比如带后缀），以控制台/套餐页面列出的模型 ID 为准替换掉三处 `glm-5.3`。我这里的模型名是按智谱一贯的命名规则写的，没有联网核对，建议合并前到开放平台「模型列表」确认一下。
3. 改完后重开 Claude Code，运行 `/status` 或 `/model` 可以看到当前 base URL 和模型；随便发一句话，如果回复正常且控制台有用量记录，说明接通了。
4. 如果之前用过 `ANTHROPIC_API_KEY` 环境变量或者 `claude login` 登录过 Anthropic 账号，建议先 `unset ANTHROPIC_API_KEY`，否则可能出现两套凭据互相干扰的情况。
