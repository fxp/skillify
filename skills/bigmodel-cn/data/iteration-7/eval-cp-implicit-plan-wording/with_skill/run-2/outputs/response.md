# main.py：用 GLM Coding Plan（Pro）套餐 Key 调 glm-5.3

脚本已保存为 `main.py`，运行方式：

```bash
pip install requests
export ZHIPU_API_KEY=<你的编程套餐 Key>
python3 main.py
```

## 关键点：编程套餐的 Base URL 和按量付费不一样

你买的是按 5 小时额度算的 GLM Coding Plan（Pro 档），它和开放平台按量付费是**两套隔离的计费体系**：

| | 按量付费（标准 API） | GLM Coding Plan（你这种） |
| :--- | :--- | :--- |
| Key 来源 | `bigmodel.cn/usercenter/proj-mgmt/apikeys` | `bigmodel.cn/coding-plan/personal/overview` 里新建的套餐 Key |
| Base URL | `https://open.bigmodel.cn/api/paas/v4` | `https://open.bigmodel.cn/api/coding/paas/v4`（多一级 `/coding`） |
| 可用模型 | 全部 | `glm-5.3`、`glm-5.3-flash` |

所以脚本里请求的是 `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`，鉴权是 `Authorization: Bearer $ZHIPU_API_KEY`，请求体和标准接口完全一样（`model` / `messages`）。

**如果你把 Base URL 写成标准的 `…/api/paas/v4`，套餐 Key 会报 HTTP 429 + `{"error":{"code":"1113","message":"余额不足或无可用资源包,请充值。"}}`**——这不是要你充值，是端点用错了。脚本对 1113 做了专门提示。另外路径里不要多拼 `/v1`（`…/coding/paas/v4/v1/chat/completions` 是 404）。

## 脚本做了什么

- 从 `ZHIPU_API_KEY` 读 Key，没设就提示退出。
- `requests.post` 打 Coding 端点，`model="glm-5.3"`，问“用一句话介绍 Rust”，`stream=False`。
- 加了 `"reasoning_effort": "low"`：glm-5.3 强制开启深度思考，默认强度 `max`，一句话问答用 `low` 能少扣不少套餐额度（额度按 输入×6.9 + 输出×24 折算，思考 token 算输出）。不想调可以把这行删掉。
- 非 200 时打印 `code` / `message`，1113 时给出排查提示；正常时打印 `choices[0].message.content`。

## 两点提醒

1. 官方条款写明套餐"仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode、Kilo Code、Cherry Studio 等）。自己写脚本打 Coding 端点技术上能通（已实测），但属于条款之外的用法，是否长期可用以官方为准；正式项目建议用标准 API Key。
2. 套餐不含 embeddings、生图、语音等能力，套餐 Key 调这些接口同样报 1113；需要的话得另用标准 Key 走 `…/api/paas/v4`。
