#!/usr/bin/env python3
import os
import requests
import json

def upload_file(file_path, api_key):
    """上传文件获取file_id"""
    url = "https://open.bigmodel.cn/api/paas/v4/files"

    with open(file_path, 'rb') as f:
        files = {'file': f}
        data = {'purpose': 'user_data'}
        headers = {'Authorization': f'Bearer {api_key}'}

        response = requests.post(url, files=files, data=data, headers=headers)
        response.raise_for_status()

        result = response.json()
        return result['id']

def ask_question(api_key, file_id, question):
    """使用file_id提问"""
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    payload = {
        'model': 'glm-5.3',
        'messages': [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'file',
                        'file': {
                            'file_id': file_id
                        }
                    },
                    {
                        'type': 'text',
                        'text': question
                    }
                ]
            }
        ],
        'stream': False
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    result = response.json()
    return result['choices'][0]['message']['content']

def main():
    # 读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 合同文件路径
    contract_path = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/v4/pdf-reuse-fileid/run-4/contract.pdf"

    # 检查文件是否存在
    if not os.path.exists(contract_path):
        print(f"错误：找不到合同文件 {contract_path}")
        return

    try:
        print("正在上传合同文件...")
        file_id = upload_file(contract_path, api_key)
        print(f"文件上传成功，file_id: {file_id}")

        # 三个问题
        questions = [
            "合同编号是什么？",
            "合同总金额是多少？",
            "违约金怎么算？"
        ]

        print("\n开始回答问题：")
        for i, question in enumerate(questions, 1):
            print(f"\n问题 {i}: {question}")
            print("答案: ", end="")

            answer = ask_question(api_key, file_id, question)
            print(answer)

    except requests.exceptions.RequestException as e:
        print(f"API请求错误: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()