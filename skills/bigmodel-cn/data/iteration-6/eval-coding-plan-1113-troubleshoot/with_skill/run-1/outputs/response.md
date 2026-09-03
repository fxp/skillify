# 结论：不是智谱的 bug，也不需要充值——你把 Coding Plan 的套餐 Key 打到了标准 API 端点上

## 诊断

智谱有**两套彼此隔离的计费体系**：

| | 标准 API（按 token / 资源包计费） | GLM Coding Plan（套餐额度计费） |
| :--- | :--- | :--- |
| Key 来源 | 控制台 `bigmodel.cn/usercenter/proj-mgmt/apikeys` | 套餐页 `bigmodel.cn/coding-plan/personal/overview` 里新建的 Key |
| OpenAI 兼容 Base URL | `https://open.bigmodel.cn/api/paas/v4` | `https://open.bigmodel.cn/api/coding/paas/v4` |
| 额度 | 账户余额 / 资源包 | 套餐额度（5 小时 + 7 天双重滚动重置），**不会**自动扣账户余额 |

两套 Key **不通用**，Base URL 也不一样。你的代码里 `base_url='https://open.bigmodel.cn/api/paas/v4/'` 是**标准 API** 端点，这个端点只认账户余额和资源包，完全看不到你的 Max 套餐额度。你账户里没有充值过按量余额，所以服务端如实返回：

```
HTTP 429
{"error": {"code": "1113", "message": "余额不足或无可用资源包,请充值。"}}
```

这个报错是"Key 与端点不匹配"的典型症状，社区里多个仓库（openclaw#63687、QwenPaw#202 等）复现的都是同一个错误码。官方文档也明确写了："Base URL 配置错误将导致无法使用 GLM Coding Plan 额度"。

**所以：不要去充值。** 充值之后这段代码确实能跑，但走的是按 token 计费，你花钱买的套餐额度还是一分没用上。

## 修复：把 Base URL 改成 Coding 端点

只需改一个地方——在路径里加上 `/coding`：

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["GLM_KEY"],                           # 必须是套餐页里新建的 Coding Plan Key
    base_url="https://open.bigmodel.cn/api/coding/paas/v4/",  # 注意多了 /coding
)
r = client.chat.completions.create(
    model="glm-5.3",
    messages=[{"role": "user", "content": "hi"}],
)
print(r.choices[0].message.content)
```

## 改完之前再对照三点

按这个顺序排查，别一上来就怀疑余额：

1. **确认 `GLM_KEY` 真的是套餐 Key**。它必须是在 `https://bigmodel.cn/coding-plan/personal/overview`（团队版是「团队编程套餐 > 我的套餐」）里创建的 Key。如果你拿的是控制台「API Keys」页面里的平台 Key，那它属于标准体系，改了 Base URL 也不会走套餐额度。
2. **Base URL 填到 `.../coding/paas/v4` 为止**，不要让客户端再自动拼 `/v1`——请求打到 `.../coding/paas/v4/v1/chat/completions` 会 404。`openai` 官方 SDK 不会额外加 `/v1`，直接照上面写即可；其它工具（OpenCode、Kilo Code 等）要关掉"自动追加 /v1"。
3. **模型范围**：套餐所有档位都支持 `glm-5.3` 和 `glm-5.3-flash`，你用 `glm-5.3` 没问题。但套餐**只含对话/编码能力**，embeddings、生图、生视频、语音、Batch、知识库都不在套餐内，这些要另外用标准 Key 走 `…/api/paas/v4`。同一个项目要两种都用时，把两个 Key 分开命名（如 `GLM_CODING_PLAN_API_KEY` 与 `ZHIPUAI_API_KEY`），别混。

## 另一种写法：走 Anthropic 兼容层

如果你更习惯 Anthropic SDK / Claude Code，套餐也支持，这时 Base URL 和标准 API **一样**，靠 Key 区分走哪套额度：

```python
import os, anthropic

client = anthropic.Anthropic(
    api_key=os.environ["GLM_KEY"],
    base_url="https://open.bigmodel.cn/api/anthropic",
)
msg = client.messages.create(
    model="glm-5.3", max_tokens=1024,
    messages=[{"role": "user", "content": "hi"}],
)
print(msg.content[0].text)
```

Claude Code 的话在 `~/.claude/settings.json` 里配 `ANTHROPIC_AUTH_TOKEN`（注意不是 `ANTHROPIC_API_KEY`）、`ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic`，并把 `ANTHROPIC_DEFAULT_HAIKU/SONNET/OPUS_MODEL` 分别映射到 `glm-5.3-flash` / `glm-5.3` / `glm-5.3`。

## 一个必须提醒的条款问题

官方条款写明：**套餐仅限在官方支持的指定工具与产品环境中使用**（Claude Code、Kilo Code、OpenCode、OpenClaw、TRAE、CodeBuddy、Cherry Studio 等）。像你这样自己写 Python 脚本直接调 Coding 端点，技术上能通，但属于条款之外的用法——是否正常扣套餐额度、会不会被限制，以官方为准。如果这段代码是要放进生产系统或长期跑的服务，建议还是用标准 API Key + `…/api/paas/v4`，按量付费才是被支持的用法。

## 如果改完还报 1113

那基本可以断定 `GLM_KEY` 不是套餐 Key（见上面第 1 点），去套餐页重新生成一个再试。真正的套餐额度用完时（5 小时窗口打满）也会收到 429，但那是另一种情况，等窗口刷新即可，代码里对 429 做退避重试就行，不要写死重置时间。
