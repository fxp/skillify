#!/usr/bin/env python3

import os
import requests

# 读取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 定义请求头
headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json'
}

# 定义请求体
data = {
    'query': '退换货政策的有效期是多久',
    'knowledge_base': 'kb1',
}

# 发起请求
response = requests.post('https://api.bigmodel.cn/v1/knowledge/search', headers=headers, data=data)

# 打印结果
print(response.json()['results'][0]['content'])
