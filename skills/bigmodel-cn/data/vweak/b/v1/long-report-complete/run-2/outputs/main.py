# main.py
import os
import requests

# 读取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# API URL
url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 构造请求数据
data = {
    "model": "glm-5.3",
    "messages": [
        {
            "role": "user",
            "content": "请生成一份关于2026年中国新能源汽车出口的市场简报，不少于600字，包括小标题和具体数据。"
        }
    ],
    "stream": false
}

# 发送请求
response = requests.post(url, headers={
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}, json=data)

# 打印结果
print(response.json()['choices'][0]['message']['content'])
