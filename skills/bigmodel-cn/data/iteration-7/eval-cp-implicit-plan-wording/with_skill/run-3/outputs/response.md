已写好 `main.py`，可以直接 `ZHIPU_API_KEY=你的套餐Key python3 main.py` 运行（需要 `pip install requests`）。

## 关键点：套餐 Key 必须打 Coding 专用端点

你买的是 GLM Coding Plan（Pro 套餐，按 5 小时额度滚动重置），它和开放平台按量付费是**两套隔离的计费体系**，所以脚本里有两处和"普通调法"不同：

| 项目 | 标准 API（按量付费） | 你的 Coding Plan |
| :--- | :--- | :--- |
| Base URL | `https://open.bigmodel.cn/api/paas/v4` | `https://open.bigmodel.cn/api/coding/paas/v4`（多了 `/coding`） |
| Key | 控制台 API Key | 套餐页面 `bigmodel.cn/coding-plan/personal/overview` 里新建的 Key |
| 可用模型 | 全部 | `glm-5.3`、`glm-5.3-flash` |

如果把套餐 Key 打到标准端点，会收到 **HTTP 429 + 业务码 `1113` "余额不足或无可用资源包，请充值"**——这不是让你充值，是端点用错了。脚本里对这个错误码做了专门提示。另外注意路径没有 `/v1` 这一级，`.../coding/paas/v4/v1/chat/completions` 会 404。

## 脚本做了什么

```python
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
CHAT_URL = f"{BASE_URL}/chat/completions"

resp = requests.post(
    CHAT_URL,
    headers={"Authorization": f"Bearer {os.environ['ZHIPU_API_KEY']}",
             "Content-Type": "application/json"},
    json={
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "用一句话介绍 Rust"}],
        "stream": False,
        "reasoning_effort": "low",   # glm-5.3 默认深度思考，简单问题用 low 更快更省额度
        "max_tokens": 1024,
    },
    timeout=120,
)
print(resp.json()["choices"][0]["message"]["content"])
```

- 鉴权是标准的 `Authorization: Bearer <Key>`，请求体字段和标准 `chat/completions` 完全一致。
- `reasoning_effort: "low"`：glm-5.3 默认会深度思考（`max` 档），"一句话介绍 Rust"这种问题没必要，`low` 档实测基本不产生思考 token，响应更快、扣的套餐额度更少。套餐额度按 `输入×6.9 + 输出×24 ÷ 10000` 扣，输出 token 最贵，所以少思考很划算。
- 非 200 时打印 HTTP 状态和业务码；`1113` 时额外提示按"端点 → 模型 → Key"顺序排查。
- `finish_reason` 不是 `stop`（如 `length`、`sensitive`）时会在 stderr 里提示。

## 两点提醒

1. 官方条款写明套餐"仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode、Kilo Code 等）。自己写脚本调 Coding 端点技术上能通、也是扣套餐额度，但属于条款之外的用法；如果是生产系统，建议用标准 API Key 走 `…/api/paas/v4`。
2. 5 小时额度用完时会收到 429 类响应，等窗口滚动刷新即可，不要写死重试时间、也别高频重试。
