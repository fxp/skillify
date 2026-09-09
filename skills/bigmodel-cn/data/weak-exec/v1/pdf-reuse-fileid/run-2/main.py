#!/usr/bin/env python3
"""
合同信息提取脚本
上传合同PDF到智谱AI平台，获取file_id，然后提出三个问题并获取答案。
"""

import os
import requests
import time

# API配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# 文件路径
PDF_FILE_PATH = "contract.pdf"

def upload_file(file_path, purpose="user_data"):
    """上传文件获取file_id"""
    print(f"正在上传文件: {file_path}")

    with open(file_path, "rb") as f:
        response = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers={"Authorization": f"Bearer {API_KEY}"},
            files={"file": f},
            data={"purpose": purpose}
        )

    if response.status_code != 200:
        print(f"上传失败: {response.text}")
        raise Exception(f"文件上传失败: {response.status_code}")

    result = response.json()
    file_id = result["id"]
    print(f"文件上传成功，file_id: {file_id}")
    return file_id

def ask_question(file_id, question, model="glm-5.3"):
    """使用file_id向模型提问"""
    payload = {
        "model": model,
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

    response = requests.post(
        f"{BASE_URL}/paas/v4/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=60
    )

    if response.status_code != 200:
        print(f"提问失败: {response.text}")
        raise Exception(f"提问失败: {response.status_code}")

    result = response.json()
    return result["choices"][0]["message"]["content"]

def main():
    print("=== 合同信息提取程序 ===")

    # 1. 上传文件获取file_id
    try:
        file_id = upload_file(PDF_FILE_PATH)
    except Exception as e:
        print(f"错误: {e}")
        return

    print("\n开始提问...")

    # 2. 提出三个问题
    questions = [
        "合同编号是什么？",
        "合同总金额是多少？",
        "违约金怎么算？"
    ]

    for i, question in enumerate(questions, 1):
        print(f"\n问题 {i}: {question}")
        print("答案:")

        try:
            answer = ask_question(file_id, question)
            print(answer)
        except Exception as e:
            print(f"获取答案失败: {e}")

    print("\n=== 程序执行完成 ===")

if __name__ == "__main__":
    main()