#!/usr/bin/env python3
import os
import requests
import json

# API配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
MODEL = "glm-5.3-flash"  # 支持文件上传的视觉模型

def upload_file(file_path):
    """上传PDF文件到智谱平台，获取file_id"""
    url = f"{BASE_URL}/paas/v4/files"

    with open(file_path, 'rb') as f:
        files = {'file': f}
        data = {'purpose': 'user_data'}  # 必须用user_data才能在对话中使用

        headers = {
            'Authorization': f'Bearer {API_KEY}'
        }

        print("正在上传文件...")
        response = requests.post(url, headers=headers, files=files, data=data)

        if response.status_code == 200:
            result = response.json()
            file_id = result.get('id')
            print(f"文件上传成功！file_id: {file_id}")
            return file_id
        else:
            print(f"文件上传失败: {response.status_code} - {response.text}")
            return None

def ask_question(file_id, question):
    """使用file_id向模型提问"""
    url = f"{BASE_URL}/paas/v4/chat/completions"

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "file",
                    "file": {
                        "file_id": file_id
                    }
                },
                {
                    "type": "text",
                    "text": question
                }
            ]
        }
    ]

    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json'
    }

    data = {
        "model": MODEL,
        "messages": messages
    }

    print(f"\n正在提问: {question}")
    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        result = response.json()
        answer = result['choices'][0]['message']['content']
        print("回答:", answer)
        return answer
    else:
        print(f"提问失败: {response.status_code} - {response.text}")
        return None

def main():
    if not API_KEY:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 合同文件路径
    contract_file = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/v2/pdf-reuse-fileid/run-3/contract.pdf"

    # 检查文件是否存在
    if not os.path.exists(contract_file):
        print(f"错误: 找不到合同文件 {contract_file}")
        return

    # 1. 上传文件获取file_id
    file_id = upload_file(contract_file)
    if not file_id:
        print("无法继续，文件上传失败")
        return

    # 2. 使用同一个file_id问三个问题
    questions = [
        "合同编号是什么",
        "合同总金额是多少",
        "违约金怎么算"
    ]

    print("\n" + "="*50)
    print("开始问答环节")
    print("="*50)

    for i, question in enumerate(questions, 1):
        ask_question(file_id, question)
        if i < len(questions):
            print("\n" + "-"*30)

if __name__ == "__main__":
    main()