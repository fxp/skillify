已写好 `main.py`，直接 `export GLM_KEY=<你的 Coding Plan Key> && python3 main.py` 即可，模型的回答会打印到 stdout。

## main.py 要点

```python
import os, sys
import requests

BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"   # Coding Plan 专用端点，注意多了 /coding
CHAT_URL = f"{BASE_URL}/chat/completions"
MODEL = "glm-5.3"

api_key = os.environ["GLM_KEY"]
resp = requests.post(
    CHAT_URL,
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    json={"model": MODEL,
          "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
          "stream": False},
    timeout=120,
)
print(resp.json()["choices"][0]["message"]["content"].strip())
```

完整脚本另外做了三件事：`GLM_KEY` 未设置时报错退出；非 200 响应时把智谱的 `error.code` / `error.message` 打到 stderr；如果错误码是 `1113`，额外提示这是 Key/端点不匹配而非欠费。

## 几个关键点（都是 Coding Plan 特有的坑）

1. **Base URL 必须是 `https://open.bigmodel.cn/api/coding/paas/v4`**，不是标准 API 的 `…/api/paas/v4`。套餐 Key 和开放平台按量付费 Key 是两套隔离的计费体系，套餐 Key 打标准端点会返回 `429` + `{"error":{"code":"1113","message":"余额不足或无可用资源包,请充值。"}}`——这不是要你充值，是端点用错了。
2. **路径里没有 `/v1`**：完整地址是 `…/coding/paas/v4/chat/completions`，写成 `…/v4/v1/chat/completions` 会 404。
3. **鉴权是 `Authorization: Bearer <Key>`**，Key 从 `https://bigmodel.cn/coding-plan/personal/overview`（个人版）或「团队编程套餐 > 我的套餐」（团队版）里拿，不要用控制台 API Keys 页面创建的平台 Key。
4. **模型用 `glm-5.3`**（套餐所有档位都支持，另一个是 `glm-5.3-flash`）。请求体格式与 OpenAI 兼容，回答在 `choices[0].message.content`；`glm-5.3` 默认开思考，思维链在 `reasoning_content` 字段里，脚本只打印 `content`。
5. **一个提醒**：官方条款写的是套餐"仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode、Kilo Code 等）。自己写脚本打 Coding 端点技术上是通的（已有实测），但属于条款之外的用法，是否消耗套餐额度、是否被限制以官方为准；生产系统建议用标准 API Key 走 `…/api/paas/v4`。

依赖只有 `requests`：`pip install requests`。
