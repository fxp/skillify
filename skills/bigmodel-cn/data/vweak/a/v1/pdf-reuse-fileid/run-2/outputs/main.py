#!/usr/bin/env python3

import os
import requests

def read_pdf_text(file_path):
    # 这里应该是一个读取PDF文本的函数
    # 由于我们不能使用像PyPDF2、pdfplumber或pypdf这样的库，
    # 我们将尝试使用Python内置的库来访问PDF内容。
    # 这可能需要使用其他方法，例如使用PDF的元数据或尝试打开PDF作为图像并提取文本。
    pass

if __name__ == '__main__':
    api_key = os.environ['ZHIPUAI_API_KEY']
    url = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    file_path = 'contract.pdf'
    pdf_text = read_pdf_text(file_path)

    # 提问并获取答案
    questions = ['合同编号是什么', '合同总金额是多少', '违约金怎么算']
    for question in questions:
        data = {
            'model': 'glm-5.3',
            'messages': [{
                'role': 'user',
                'content': question
            }],
            'stream': False
        }
        response = requests.post(url, headers=headers, json=data)
        print(response.json()['choices'][0]['message']['content'])
