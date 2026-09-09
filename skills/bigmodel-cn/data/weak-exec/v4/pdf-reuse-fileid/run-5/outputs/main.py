#!/usr/bin/env python3
"""
使用智谱AI GLM模型读取PDF合同并回答三个问题
1. 合同编号是什么
2. 合同总金额是多少
3. 违约金怎么算

流程：
1. 上传PDF文件到智谱平台，获取file_id
2. 使用file_id进行多轮对话，复用同一个文件
3. 分别询问三个问题并打印答案
"""

import os
import requests
import json


def upload_file(file_path, api_key):
    """上传PDF文件到智谱平台，返回file_id"""
    url = "https://open.bigmodel.cn/api/paas/v4/files"

    with open(file_path, "rb") as f:
        files = {"file": f}
        data = {"purpose": "user_data"}
        headers = {"Authorization": f"Bearer {api_key}"}

        response = requests.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()

        return response.json()["id"]


def ask_question(api_key, file_id, question):
    """使用file_id询问问题"""
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    payload = {
        "model": "glm-5.3-flash",  # 使用支持文件输入的视觉模型
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

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    result = response.json()
    return result["choices"][0]["message"]["content"]


def main():
    # 从环境变量读取API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # PDF文件路径
    pdf_file = "contract.pdf"

    if not os.path.exists(pdf_file):
        print(f"错误：找不到文件 {pdf_file}")
        return

    try:
        print("正在上传PDF文件...")
        # 上传文件获取file_id
        file_id = upload_file(pdf_file, api_key)
        print(f"文件上传成功，file_id: {file_id}")

        # 三个问题
        questions = [
            "合同编号是什么？",
            "合同总金额是多少？",
            "违约金怎么算？"
        ]

        print("\n开始问答：")
        print("=" * 50)

        # 依次询问三个问题
        for i, question in enumerate(questions, 1):
            print(f"\n问题 {i}: {question}")
            print("-" * 30)

            answer = ask_question(api_key, file_id, question)
            print(f"答案 {i}: {answer}")
            print("=" * 50)

    except requests.exceptions.RequestException as e:
        print(f"API请求错误: {e}")
    except Exception as e:
        print(f"发生错误: {e}")


if __name__ == "__main__":
    main()