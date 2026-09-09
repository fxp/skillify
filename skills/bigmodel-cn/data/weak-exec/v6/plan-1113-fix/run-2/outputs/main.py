import os
import requests

# 使用 Coding Plan 的端点
url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

# 从环境变量读取 GLM_KEY
api_key = os.environ.get("GLM_KEY")
if not api_key:
    raise ValueError("请设置环境变量 GLM_KEY")

# 设置请求头
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# 请求数据
data = {
    "model": "glm-5.3",
    "messages": [
        {
            "role": "user",
            "content": "用一句话介绍 Python"
        }
    ],
    "stream": False
}

# 发送请求
response = requests.post(url, headers=headers, json=data)
response.raise_for_status()  # 检查请求是否成功

# 打印回答
result = response.json()
print(result["choices"][0]["message"]["content"])