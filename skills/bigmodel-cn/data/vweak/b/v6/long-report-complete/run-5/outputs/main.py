# main.py
import os
import requests

# 读取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 设置API URL
url = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'

# 构造请求头
headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {api_key}',
}

# 构造请求体
data = {
    'model': 'glm-5.3',
    'messages': [{
        'role': 'user',
        'content': '请生成一份关于2026年中国新能源汽车出口的市场简报，不少于600字，包含小标题和具体数据。',
    }],
}

# 发送请求
response = requests.post(url, headers=headers, json=data)

# 打印结果
print(response.json()['choices'][0]['message']['content'])
