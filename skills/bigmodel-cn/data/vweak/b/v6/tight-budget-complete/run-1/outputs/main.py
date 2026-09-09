#!/usr/bin/env python3

import os
import requests

# 获取 API Key
api_key = os.getenv('ZHIPUAI_API_KEY')

# API 地址
url = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'

# 准备请求参数
data = {
    'model': 'glm-5.3',
    'messages': [{
        'role': 'user',
        'content': '请生成一份关于2026年中国新能源汽车出口的市场简报。'}],
    'max_tokens': 1000
}

# 发送请求
response = requests.post(url, headers={'Authorization': f'Bearer {api_key}'}, json=data)

# 检查请求是否成功
if response.status_code == 200:
    content = response.json()['choices'][0]['message']['content']
else:
    content = '请求失败，请检查 API Key 是否有效。'

# 打印内容并输出字数
print(content)
print(len(content), 'Chinese characters')
