#!/usr/bin/env python3

import os
import requests

# 环境变量 GLM_KEY 保存的名称
GLM_KEY_NAME = 'GLM_KEY'

# 模型名称
MODEL_NAME = 'glm-5.3'

# 请求智谱AI开放平台API的URL
API_URL = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'

# 获取环境变量中的GLM_KEY
GLM_KEY = os.environ[GLM_KEY_NAME]

# 构建请求头
headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {GLM_KEY}',
}

# 构建请求参数
data = {
    'model': MODEL_NAME,
    'messages': [
        {
            'role': 'user',
            'content': '用一句话介绍 Python',
        },
    ],
}

# 发送请求
response = requests.post(API_URL, headers=headers, json=data)

# 检查响应状态码
if response.status_code == 200:
    # 打印响应内容
    print(response.json()['choices'][0]['message']['content'])
else:
    # 打印错误信息
    print('Error:', response.status_code, response.json()['error']['message'])
