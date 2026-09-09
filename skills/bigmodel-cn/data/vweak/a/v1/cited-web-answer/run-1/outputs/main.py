#!/usr/bin/env python3
import os
import requests

# 读取 API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 构建请求头
headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {api_key}',
}

# 准备请求体
url = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
messages = [{'role': 'user', 'content': '2026年智谱 BigModel 发布了哪些新模型'}]
data = {
    'model': 'glm-5.3',
    'messages': messages,
    'stream': False,
}

# 发送请求
response = requests.post(url, headers=headers, json=data)
response.raise_for_status()
result = response.json()['choices'][0]['message']['content']

# 打印结果
print(result)
