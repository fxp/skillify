已写好 `main.py`（同目录），只依赖 `requests`，直接 `python3 main.py` 即可跑。

## 两把 Key 怎么分工

智谱的**标准 API** 和 **GLM Coding Plan** 是两套隔离的计费体系：Key 不通用、Base URL 不同、可用能力不同。

| 步骤 | 能力 | 用哪把 Key | Base URL | 原因 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `embedding-3` 向量 | `ZHIPUAI_API_KEY`（按量付费） | `https://open.bigmodel.cn/api/paas/v4` | Embeddings **不在套餐内**，套餐 Key 调它（无论打哪个端点）都会返回 `429 + 1113 余额不足`，这不是要充值，是能力不在套餐里 |
| 2 | `glm-5.3` 对话 | `GLM_CODING_PLAN_API_KEY`（套餐） | `https://open.bigmodel.cn/api/coding/paas/v4`（注意多了 `/coding`） | 对话是套餐包含的能力，走 Coding 端点即可消耗套餐额度；打到标准端点 `…/api/paas/v4` 会报 `1113` |

所以"能用套餐额度的地方尽量用套餐额度"最终只有第 2 步能用套餐，第 1 步必须走标准 Key。

## 脚本要点

- **余弦相似度**用纯 Python 计算（无需 numpy），按返回的 `index` 对齐两条向量再算。
- **glm-5.3 强制开启思考、不能关闭**（标准端点传 `thinking: disabled` 报 `1210`），脚本用 `reasoning_effort: "low"` 把思考开销压到最低，两个端点都接受。
- **错误处理**：只对 429（限流/过载）和 5xx 做指数退避重试；遇到 `1113` 直接报错并提示"检查 Key/端点/能力是否匹配"，不做无意义重试。
- **回退**：没设 `GLM_CODING_PLAN_API_KEY`，或套餐调用失败（例如 5 小时额度用光），对话会自动回退到标准 Key + 标准端点，保证脚本能跑通，并在 stderr 里说明走了哪条路。
- 输出示例：

```
[1/2] 用 embedding-3（标准 API，ZHIPUAI_API_KEY）计算向量…
「今天天气很好」 vs 「天气不错」
余弦相似度 = 0.8xxx  （向量维度 2048）

[2/2] 用 glm-5.3（GLM Coding Plan 套餐额度）判断语义…
glm-5.3：这两句话意思相近，都是在说天气好。
```

## 运行

```bash
pip install requests
export ZHIPUAI_API_KEY=你的开放平台Key
export GLM_CODING_PLAN_API_KEY=你的套餐Key
python3 main.py
```

## 一点提醒

官方条款写明 Coding Plan 套餐"仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode 等）。自己用 `requests` 打 `…/api/coding/paas/v4` 技术上能通、也确实走套餐额度（已有实测），但属于条款之外的用法，是否长期可用以官方为准；生产环境建议用标准 Key。
