# 让 Claude Code 用 GLM Coding Plan 跑 GLM-5.3

## 一、`~/.claude/settings.json` 里要加的内容

把下面的 `env` 块合并进 `~/.claude/settings.json`（文件不存在就直接新建成这样；已有其它键就只把 `env` 这一段加进去）：

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "在这里填你的 GLM Coding Plan 套餐 Key",
    "ANTHROPIC_BASE_URL": "https://open.bigmodel.cn/api/anthropic",
    "API_TIMEOUT_MS": "3000000",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5.3",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.3",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-5.3-flash"
  }
}
```

保存后重新启动 `claude` 即可。启动后可以用 `/status` 或 `/model` 看一眼，Base URL 应显示 `open.bigmodel.cn`，模型应显示 `glm-5.3`。

## 二、等价的环境变量写法（二选一即可）

不想改 settings.json 的话，把下面几行加到 `~/.zshrc`（或启动前 `export` 一遍），效果完全一样：

```bash
export ANTHROPIC_AUTH_TOKEN="在这里填你的 GLM Coding Plan 套餐 Key"
export ANTHROPIC_BASE_URL="https://open.bigmodel.cn/api/anthropic"
export API_TIMEOUT_MS="3000000"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1"
export ANTHROPIC_DEFAULT_OPUS_MODEL="glm-5.3"
export ANTHROPIC_DEFAULT_SONNET_MODEL="glm-5.3"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="glm-5.3-flash"
```

## 三、几个必须注意的点（配错就跑不起来）

1. **Key 一定要用 Coding Plan 套餐的 Key，不是开放平台的普通 API Key。**
   套餐 Key 在 `https://bigmodel.cn/coding-plan/personal/overview` 里新建（团队版在「团队编程套餐 > 我的套餐」）。开放平台 `usercenter/proj-mgmt/apikeys` 里创建的 Key 和套餐 Key 是两套隔离的计费体系，互不通用——用普通 Key 填进去也能跑，但走的是按 token 扣账户余额，不消耗套餐额度。
2. **变量名是 `ANTHROPIC_AUTH_TOKEN`，不是 `ANTHROPIC_API_KEY`。** Claude Code 读的是前者作为 Bearer token。
3. **Base URL 就是 `https://open.bigmodel.cn/api/anthropic`，不要加 `/v1`，也不要用 `/api/coding/paas/v4`。**
   `/api/coding/paas/v4` 是给 OpenAI 兼容客户端（OpenCode、Kilo Code、Cherry Studio 等）用的；Claude Code 走 Anthropic 兼容层，标准 API 和套餐共用这一个 `/api/anthropic` 地址，靠 Key 区分走哪套额度。SDK 自己会拼上 `/v1/messages`，这是正常的。
4. **三个 `ANTHROPIC_DEFAULT_*_MODEL` 不能省。** Claude Code 内部会按 opus / sonnet / haiku 三个别名去请求模型，不映射的话它会去请求不存在的 `claude-*` 模型名而报错。这里把 opus 和 sonnet 都指到 `glm-5.3`（旗舰，1M 上下文、128K 最大输出），haiku 指到 `glm-5.3-flash`（轻量，给后台小任务用，省额度）。套餐所有档位（Lite / Pro / Max）都包含这两个模型。
5. `API_TIMEOUT_MS=3000000` 是官方建议值——GLM-5.3 强制开启深度思考、无法关闭，长任务响应时间会比较久，超时给足避免被 Claude Code 掐断。`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` 关掉 Claude Code 往 Anthropic 发的非必要遥测请求。

## 四、如果报错怎么排查

- **报 429 且错误码 `1113 "余额不足或无可用资源包,请充值"`**：不是让你充值，是 Key 和端点对不上（比如把套餐 Key 打到了 `…/api/paas/v4` 标准端点，或者 settings 里填的其实是普通 Key）。回去核对第 1、3 条。
- **报 404**：多半是 Base URL 后面手动加了 `/v1` 或写成了别的路径，改回 `https://open.bigmodel.cn/api/anthropic`。
- **一段时间后突然全部报错**：可能是 5 小时滚动额度用完了（Lite 2,000 / Pro 12,000 / Max 28,000 点，每周另有上限），等窗口刷新即可；套餐整体到期的话，官方 FAQ 建议改用平台 Key 走按量计费。
- 排查顺序：先确认 Key 属于哪套体系 → 再核对 Base URL → 再核对模型名 → 最后才考虑额度问题。

## 五、可选：套餐附赠的 MCP 工具

Coding Plan 附带一个本地 MCP Server（视觉理解、联网搜索、网页阅读、开源仓库检索），走套餐额度。想在 Claude Code 里用的话，加到 `~/.claude.json` 或项目 `.mcp.json` 的 `mcpServers` 里：

```json
{
  "mcpServers": {
    "zai-mcp-server": {
      "command": "npx",
      "args": ["-y", "@z_ai/mcp-server"],
      "env": {
        "Z_AI_API_KEY": "你的 Coding Plan 套餐 Key",
        "Z_AI_MODE": "ZHIPU"
      }
    }
  }
}
```

---

两个可直接使用的文件已一并给出：`settings.json`（合并进 `~/.claude/settings.json`）和 `glm-coding-plan.env.sh`（环境变量版本），把占位符换成你的套餐 Key 即可。以上配置整理自 `docs.bigmodel.cn/cn/coding-plan/tool/claude`（2026-09）；智谱迭代较快，如实际报"模型不存在"之类错误，以 API 实际返回和官方文档最新说明为准。
