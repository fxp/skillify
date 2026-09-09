#!/usr/bin/env python3
"""
合同PDF信息提取脚本
使用智谱AI GLM模型读取合同PDF并回答问题
"""

import os
import requests
import time

# API配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# 合同PDF文件路径
CONTRACT_PDF_PATH = "../run-1/contract.pdf"

# 请求头
HEADERS = {
    "Authorization": f"Bearer {API_KEY}"
}

def upload_file(file_path, purpose="user_data"):
    """上传文件到智谱平台"""
    print(f"正在上传文件: {file_path}")

    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=HEADERS,
            files={"file": f},
            data={"purpose": purpose},
        )
        resp.raise_for_status()
        file_info = resp.json()
        file_id = file_info["id"]
        print(f"文件上传成功，file_id: {file_id}")
        return file_id

def ask_question_with_file(file_id, question, model="glm-5.3-flash"):
    """使用上传的文件提问"""
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "file", "file": {"file_id": file_id}}
                ]
            }
        ],
        "stream": False
    }

    resp = requests.post(
        f"{BASE_URL}/paas/v4/chat/completions",
        headers=HEADERS,
        json=payload,
    )
    resp.raise_for_status()
    result = resp.json()
    return result["choices"][0]["message"]["content"]

def main():
    print("=== 合同PDF信息提取程序 ===")

    # 1. 上传PDF文件
    try:
        file_id = upload_file(CONTRACT_PDF_PATH)
        print()

        # 2. 问三个问题
        questions = [
            "合同编号是什么？",
            "合同总金额是多少？",
            "违约金怎么算？"
        ]

        for i, question in enumerate(questions, 1):
            print(f"--- 问题 {i}: {question} ---")
            answer = ask_question_with_file(file_id, question)
            print("答案:")
            print(answer)
            print()

        print("=== 提取完成 ===")

    except Exception as e:
        print(f"发生错误: {e}")
        raise

if __name__ == "__main__":
    main()