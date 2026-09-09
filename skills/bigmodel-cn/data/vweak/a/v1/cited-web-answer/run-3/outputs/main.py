# main.py

import os
import requests

# 获取 API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 定义接口 URL
url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 构建请求头
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

# 构建请求体
data = {
    "model": "glm-5.3",
    "messages": [
        {
            "role": "user",
            "content": "2026 年智谱 BigModel 发布了哪些新模型"}
        ]
    }
}

# 发送请求
response = requests.post(url, headers=headers, json=data)

# 打印结果
print(response.json()["choices"][0]["message"]["content"])

# 打印信息来源
print("信息来源：")
print("- https://docs.bigmodel.cn/")
