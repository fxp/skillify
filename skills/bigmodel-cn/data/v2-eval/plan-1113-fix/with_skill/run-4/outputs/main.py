import os

import requests

# GLM Coding Plan（编程套餐）Key 不能打标准端点 …/api/paas/v4（会报 429 + 1113 余额不足），
# 必须走套餐专用的 …/api/coding/paas/v4。
resp = requests.post(
    "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions",
    headers={"Authorization": f"Bearer {os.environ['GLM_KEY']}"},
    json={
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
    },
    timeout=60,
)
resp.raise_for_status()
print(resp.json()["choices"][0]["message"]["content"])
