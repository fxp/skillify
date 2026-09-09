import os
import requests

# 使用 GLM Coding Plan 端点
url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

# 从环境变量读取 GLM_KEY
api_key = os.environ["GLM_KEY"]

# 发送请求
response = requests.post(
    url,
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    json={
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "用一句话介绍 Python"}]
    }
)

# 打印回答
print(response.json()["choices"][0]["message"]["content"])