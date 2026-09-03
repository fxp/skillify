已写好 `main.py`（同目录），只依赖 `requests`，`python3 main.py` 即可运行。

## 两把 Key 的分工

| 步骤 | 模型 | 用哪把 Key | Base URL | 原因 |
| :--- | :--- | :--- | :--- | :--- |
| 计算余弦相似度 | `embedding-3` | `ZHIPUAI_API_KEY`（按量付费） | `https://open.bigmodel.cn/api/paas/v4` | embeddings **不在 Coding Plan 套餐内**，套餐 Key 无论打哪个端点都会 `429 + 1113`，只能走标准 Key |
| 一句话判断是否相近 | `glm-5.3` | `GLM_CODING_PLAN_API_KEY`（套餐） | `https://open.bigmodel.cn/api/coding/paas/v4` | 套餐包含 `glm-5.3`，走 Coding 端点才会扣套餐额度；若没配套餐 Key 会自动退回标准 Key + 标准端点 |

两套 Key/Base URL 彼此隔离、不能混用；脚本里把它们分开管理，套餐 Key 打标准端点会直接报 `1113 余额不足`，那不是要充值，是端点用错了。

## 脚本要点

- **Embeddings**：一次请求同时传入两句话，`dimensions: 1024`，结果按返回的 `index` 对齐后再算余弦相似度（纯 Python 实现，无需 numpy）。
- **Chat**：`glm-5.3` 在标准端点强制开启思考、不能传 `thinking: disabled`，所以用 `reasoning_effort: "low"` 把思考开销压到最低，`max_tokens: 256` 足够一句话回答。提示词里顺带把相似度数值喂给模型，让它的判断有依据。
- **错误处理**：对 `429/5xx` 做指数退避重试；遇到 `1113` 直接抛出并提示按「端点 → 能力 → 模型」顺序排查，而不是笼统地让你充值。
- 缺少对应环境变量时会给出明确的中文提示并退出。

## 运行

```bash
export ZHIPUAI_API_KEY="你的开放平台 Key"
export GLM_CODING_PLAN_API_KEY="你的 Coding Plan Key"
pip install requests
python3 main.py
```

预期输出示例：

```
[embed] 使用开放平台按量付费 Key 调用 embedding-3
「今天天气很好」与「天气不错」的余弦相似度：0.8xxx
[chat] 使用 GLM Coding Plan 套餐额度 调用 glm-5.3
glm-5.3：这两句话意思相近，都在表达天气好。
```

## 一点提醒

官方条款写明 Coding Plan 套餐"仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode 等）。自己写脚本打 Coding 端点在技术上能通、也确实走套餐额度，但属于条款之外的用法，是否持续可用以官方为准；生产系统建议用标准 API Key。
