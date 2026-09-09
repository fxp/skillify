#!/usr/bin/env python3

import os
import requests

# 从环境变量中读取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# Base URL
base_url = 'https://open.bigmodel.cn/api/paas/v4/batches'

# 构造请求体
data = {
    "model": "glm-5.3",
    "inputs": [
        {
            "file_id": "file_id_1"
        },
        {
            "file_id": "file_id_2"
        }
    ]
}

# 创建batch任务
response = requests.post(base_url, headers={
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}, json=data)

# 打印batch任务ID
print(response.json()['batch_id'])
