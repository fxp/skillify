#!/usr/bin/env python3
import os
import requests
import json

# 配置
API_BASE = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
PDF_FILE_PATH = "contract.pdf"

# 检查 API Key
if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

# 请求头
headers = {
    "Authorization": f"Bearer {API_KEY}"
}

def upload_file():
    """上传 PDF 文件并获取 file_id"""
    print("正在上传文件...")

    with open(PDF_FILE_PATH, "rb") as f:
        files = {"file": f}
        data = {"purpose": "user_data"}  # 必须使用 user_data

        resp = requests.post(
            f"{API_BASE}/paas/v4/files",
            headers=headers,
            files=files,
            data=data
        )

    if resp.status_code != 200:
        print(f"上传失败: {resp.text}")
        return None

    file_id = resp.json()["id"]
    print(f"文件上传成功，file_id: {file_id}")
    return file_id

def ask_question(file_id, question):
    """使用 file_id 提问"""
    payload = {
        "model": "glm-5.3",  # 使用支持多模态的模型
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "file", "file": {"file_id": file_id}},
                    {"type": "text", "text": question}
                ]
            }
        ]
    }

    resp = requests.post(
        f"{API_BASE}/paas/v4/chat/completions",
        headers=headers,
        json=payload
    )

    if resp.status_code != 200:
        print(f"提问失败: {resp.text}")
        return None

    answer = resp.json()["choices"][0]["message"]["content"]
    return answer

def main():
    # 1. 上传文件获取 file_id
    file_id = upload_file()
    if not file_id:
        return

    # 2. 提三个问题
    questions = [
        "合同编号是什么？",
        "合同总金额是多少？",
        "违约金怎么算？"
    ]

    print("\n开始提问...")
    for i, question in enumerate(questions, 1):
        print(f"\n问题 {i}: {question}")
        answer = ask_question(file_id, question)
        if answer:
            print(f"答案 {i}: {answer}")
        else:
            print(f"问题 {i} 获取答案失败")

if __name__ == "__main__":
    main()