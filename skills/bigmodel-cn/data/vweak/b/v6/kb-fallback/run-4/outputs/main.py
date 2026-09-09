#!/usr/bin/env python3

import os
import requests

# 读取 API 密钥
api_key = os.environ['ZHIPUAI_API_KEY']

# 智谱开放平台基础 URL
base_url = 'https://open.bigmodel.cn/api/paas/v4'

# 创建检索请求
def search_knowledge_base(question):
    # 设置请求头
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}

    # 设置请求参数
    params = {'model': 'glm-5.3', 'messages': [{'role': 'user', 'content': question}]}

    # 发送请求
    response = requests.post(f'{base_url}/chat/completions', headers=headers, json=params)

    # 检查响应状态码
    if response.status_code == 200:
        # 解析响应内容
        data = response.json()
        # 提取答案
        answer = data['choices'][0]['message']['content']
        return answer
    else:
        # 如果响应状态码不是 200，返回错误信息
        return f'Error: {response.status_code}'

# 主函数
if __name__ == '__main__':
    # 读取 FAQ 文件
    with open('faq.txt', 'r', encoding='utf-8') as file:
        faq_content = file.read()

    # 将 FAQ 内容写入知识库
    question = '退换货政策的有效期是多久'
    answer = search_knowledge_base(question)

    # 打印检索到的原文片段
    print(answer)