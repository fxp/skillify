import os
import requests

# 使用 GLM Coding Plan 端点
url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

# 从环境变量读取 API Key
api_key = os.environ.get("GLM_KEY")
if not api_key:
    raise ValueError("请设置环境变量 GLM_KEY")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

data = {
    "model": "glm-5.3",
    "messages": [{"role": "user", "content": "用一句话介绍 Python"}]
}

response = requests.post(url, headers=headers, json=data)
response.raise_for_status()  # 检查请求是否成功

# 打印模型的回答
print(response.json()["choices"][0]["message"]["content"])