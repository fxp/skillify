#!/usr/bin/env python3

import os
import requests

# 获取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 定义模型和消息列表
model = 'glm-4.6'
messages = [
    '这句话情感很积极。',
    '这句话情感很消极。',
    '这句话是中性。'
]

# 发起请求
for message in messages:
    response = requests.post
    ("https://open.bigmodel.cn/api/paas/v4/chat/completions",
     headers=
     {
         "Authorization": f"Bearer {api_key}",
         "Content-Type": "application/json"
     },
     json=
     {
         "model": model,
         "messages": [
             {
                 "role": "user",
                 "content": message
             }
         ]
     }
    )
    # 打印请求结果
    print(response.json()['choices'][0]['message']['content'])
    # 打印模型信息
    print("我请求的模型：", model)
    print("接口实际使用的模型：", response.json()['model'])
    if model != response.json()['model']:
        print("警告：模型版本不匹配！")
