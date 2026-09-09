#!/usr/bin/env python3
import os
import requests
import json

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

def upload_file(file_path):
    """上传文件并返回file_id"""
    headers = {"Authorization": f"Bearer {API_KEY}"}

    with open(file_path, "rb") as f:
        response = requests.post(
            f"{BASE_URL}/files",
            headers=headers,
            files={"file": f},
            data={"purpose": "user_data"}
        )

    response.raise_for_status()
    file_info = response.json()
    return file_info["id"]

def ask_question(file_id, question):
    """使用file_id提问并获取回答"""
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    payload = {
        "model": "glm-4.6",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "file", "file_id": file_id},
                    {"type": "text", "text": question}
                ]
            }
        ],
        "max_tokens": 800
    }

    response = requests.post(
        f"{BASE_URL}/chat/completions",
        headers=headers,
        json=payload
    )

    response.raise_for_status()
    result = response.json()
    return result["choices"][0]["message"]["content"]

def main():
    # 检查API Key
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 上传PDF文件
    pdf_path = "contract.pdf"
    if not os.path.exists(pdf_path):
        print(f"错误：找不到文件 {pdf_path}")
        return

    print("正在上传文件...")
    file_id = upload_file(pdf_path)
    print(f"文件上传成功，file_id: {file_id}")

    # 三个问题
    questions = [
        "合同编号是什么",
        "合同总金额是多少",
        "违约金怎么算"
    ]

    # 依次提问
    for i, question in enumerate(questions, 1):
        print(f"\n问题 {i}: {question}")
        print("答案:")
        answer = ask_question(file_id, question)
        print(answer)

if __name__ == "__main__":
    main()