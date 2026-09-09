#!/usr/bin/env python3
import os
import requests
import time

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"

if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# 上传文件
def upload_file(file_path):
    url = f"{BASE_URL}/paas/v4/files"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    with open(file_path, "rb") as f:
        response = requests.post(
            url,
            headers=headers,
            files={"file": f},
            data={"purpose": "user_data"}
        )

    response.raise_for_status()
    return response.json()

# 向模型提问
def ask_question(file_id, question):
    url = f"{BASE_URL}/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # 使用支持文件输入的模型
    payload = {
        "model": "glm-5.3-flash",  # 支持文件输入的多模态模型
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "file", "file": {"file_id": file_id}},
                    {"type": "text", "text": question}
                ]
            }
        ],
        "max_tokens": 2000,
        "stream": False
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    result = response.json()
    return result["choices"][0]["message"]["content"]

def main():
    # 合同文件路径
    contract_file = "contract.pdf"

    # 1. 上传合同文件
    print("正在上传合同文件...")
    upload_result = upload_file(contract_file)
    file_id = upload_result["id"]
    print(f"文件上传成功，file_id: {file_id}")

    # 2. 问三个问题
    questions = [
        "合同编号是什么",
        "合同总金额是多少",
        "违约金怎么算"
    ]

    print("\n开始提问...")
    for i, question in enumerate(questions, 1):
        print(f"\n问题 {i}: {question}")
        print("答案:", end=" ")
        answer = ask_question(file_id, question)
        print(answer)
        print("-" * 50)

    print("\n所有问题回答完成！")

if __name__ == "__main__":
    main()