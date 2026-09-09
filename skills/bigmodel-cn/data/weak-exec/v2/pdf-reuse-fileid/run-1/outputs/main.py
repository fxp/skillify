#!/usr/bin/env python3
import os
import requests
import json

def upload_file(file_path, api_key):
    """上传文件到智谱平台，返回 file_id"""
    url = "https://open.bigmodel.cn/api/paas/v4/files"

    with open(file_path, "rb") as f:
        files = {"file": f}
        data = {"purpose": "user_data"}

        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        response = requests.post(url, headers=headers, files=files, data=data)

        if response.status_code == 200:
            result = response.json()
            return result["id"]
        else:
            raise Exception(f"文件上传失败: {response.status_code} - {response.text}")

def ask_question(api_key, file_id, question):
    """使用已上传的文件提问"""
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    payload = {
        "model": "glm-5.3-flash",  # 使用支持视觉输入的模型
        "messages": [
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
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)

    if response.status_code == 200:
        result = response.json()
        return result["choices"][0]["message"]["content"]
    else:
        raise Exception(f"提问失败: {response.status_code} - {response.text}")

def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise Exception("请设置环境变量 ZHIPUAI_API_KEY")

    # 合同文件路径
    contract_file = "contract.pdf"

    # 1. 上传文件
    print("正在上传合同文件...")
    file_id = upload_file(contract_file, api_key)
    print(f"文件上传成功，file_id: {file_id}")

    # 2. 问三个问题
    questions = [
        "合同编号是什么？",
        "合同总金额是多少？",
        "违约金怎么算？"
    ]

    print("\n开始提问...")

    for i, question in enumerate(questions, 1):
        print(f"\n问题 {i}: {question}")
        print("答案:", end=" ")

        try:
            answer = ask_question(api_key, file_id, question)
            print(answer)
        except Exception as e:
            print(f"错误: {e}")

if __name__ == "__main__":
    main()