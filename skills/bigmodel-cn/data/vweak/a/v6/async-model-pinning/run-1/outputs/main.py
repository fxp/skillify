#!/usr/bin/env python3

import os
import requests

# 读取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 模型信息
model_info = {'model': 'glm-4.6', 'used_model': 'glm-4.6'}

# 对三句话进行情感分类
texts = ['这是一个很好的产品', '这个产品很糟糕', '我对这个产品感觉一般']

# 对每句话发起请求
for text in texts:
    response = requests.post

    # 设置请求头
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}

    # 设置请求参数
    data = {'model': 'glm-4.6', 'messages': [{'role': 'user', 'content': text}]}

    # 发送请求
    response = requests.post('https://open.bigmodel.cn/api/paas/v4/chat/completions', headers=headers, json=data)

    # 解析响应
    try:
        response.raise_for_status()
        result = response.json()
        sentiment = result['choices'][0]['message']['content']
        print(f'原文：{text}，情感分类：{sentiment}')
    except requests.exceptions.HTTPError as e:
        print(f'请求失败：{e}')
    except KeyError as e:
        print(f'解析错误：{e}')

# 打印模型信息
print('我请求的模型：', model_info['model'])
print('接口实际使用的模型：', model_info['used_model'])
