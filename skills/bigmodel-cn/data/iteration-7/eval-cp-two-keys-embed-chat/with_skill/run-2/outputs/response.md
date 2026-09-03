# 两把 Key 分工：embedding-3 余弦相似度 + glm-5.3 一句话判断

脚本已保存为 `main.py`，直接 `python3 main.py` 即可运行（依赖 `requests`，`pip install requests`）。

## 为什么要两把 Key 分开用

智谱有两套彼此隔离的计费体系，Key 不通用、Base URL 也不同：

| 步骤 | 能力 | 套餐能否覆盖 | 使用的 Key | Base URL |
| :--- | :--- | :--- | :--- | :--- |
| 1. 余弦相似度 | `embedding-3` | **不能**：embeddings 不在 GLM Coding Plan 套餐内，用套餐 Key 调无论打哪个端点都是 `429 + 1113` | `ZHIPUAI_API_KEY`（按量付费） | `https://open.bigmodel.cn/api/paas/v4` |
| 2. 一句话判断 | `glm-5.3` 对话 | **能**：套餐所有档位都含 `glm-5.3` / `glm-5.3-flash` | `GLM_CODING_PLAN_API_KEY`（套餐） | `https://open.bigmodel.cn/api/coding/paas/v4`（注意多了 `/coding`） |

所以"能用套餐额度的地方尽量用套餐额度"落到代码上就是：**向量走按量付费 Key，对话走套餐 Key**。

## 脚本做了什么

1. 读取两个环境变量。`ZHIPUAI_API_KEY` 缺失直接报错退出（embedding 没有替代方案）；`GLM_CODING_PLAN_API_KEY` 缺失只打印提示，对话回退到按量付费 Key。
2. 用标准 Key `POST …/api/paas/v4/embeddings`，`model=embedding-3`、`dimensions=1024`，一次传两句话，按返回的 `index` 对齐向量后用纯 Python 算余弦相似度并打印。
3. 用套餐 Key `POST …/api/coding/paas/v4/chat/completions`，`model=glm-5.3`，让模型用一句话判断两句话意思是否相近（prompt 里附上相似度分数作参考），打印回答和实际命中的模型名。
   - 加了 `reasoning_effort: "low"`：`glm-5.3` 在标准端点无法关闭思考，`low` 档实测 `reasoning_tokens=0`，简单判断题不用浪费额度；这个参数两个端点通用。
   - 如果套餐调用返回 `1113`（套餐额度用尽/不可用），自动回退到 `ZHIPUAI_API_KEY` + 标准端点，保证脚本仍能跑通。

## 运行

```bash
export ZHIPUAI_API_KEY="开放平台按量付费的 Key"
export GLM_CODING_PLAN_API_KEY="GLM Coding Plan 套餐的 Key"
python3 main.py
```

预期输出形如：

```
[向量] 使用开放平台按量付费 Key 调用 embedding-3（https://open.bigmodel.cn/api/paas/v4）
「今天天气很好」与「天气不错」的余弦相似度：0.8xxx
[对话] 使用 GLM Coding Plan 套餐额度（https://open.bigmodel.cn/api/coding/paas/v4，实际模型 glm-5.3）
glm-5.3 的判断：这两句话意思相近，都是在说天气好。
```

## 几点提醒

- 如果看到 `429` + `{"error":{"code":"1113","message":"余额不足或无可用资源包,请充值。"}}`，先别去充值：套餐 Key 打到 `…/api/paas/v4`、或者用套餐 Key 调 embeddings，都会报这个码。排查顺序是 Key 属于哪套体系 → Base URL 是否匹配 → 能力/模型是否在套餐内 → 最后才是余额。
- 官方条款规定套餐仅限在 Claude Code、OpenCode、Kilo Code 等指定工具环境内使用，自己写脚本打 Coding 端点技术上能通，但属于条款之外的用法，是否扣套餐额度、是否被限制以官方为准；生产系统建议用标准 API Key。
- 脚本兼容 Python 3.9+（已用 `from __future__ import annotations`），已在本机 `python3 -m py_compile` 和无 Key 干跑验证通过；有 Key 的实际调用请在你的环境执行。
