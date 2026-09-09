#!/usr/bin/env python3

import os
import requests

# 从环境变量中读取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 模型URL
model_url = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'

# 构造请求参数
data = {
    "model": "glm-5.3",
    "messages": [
        {
            "role": "user",
            "content": "评论内容"
        }
    ],
    "stream": false
}

# 发送请求
response = requests.post(model_url, headers={
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"}, json=data)

# 打印batch任务ID
print(response.json()['batch_task_id'])
