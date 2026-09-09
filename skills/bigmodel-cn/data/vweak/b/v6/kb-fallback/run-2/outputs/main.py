#!/usr/bin/env python3

import os
import requests

# 读取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 准备请求参数
url = 'https://api.bigmodel.cn/path/to/api'
headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json'
}

# 发送请求
response = requests.get(url, headers=headers)

# 打印响应内容
print(response.json()['data'])
