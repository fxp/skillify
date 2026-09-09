#!/usr/bin/env python3
import os
import requests
import json

# 配置
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

# 检查 API Key 是否设置
if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

# headers
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def upload_file(file_path):
    """上传文件获取 file_id"""
    print("正在上传文件...")
    with open(file_path, "rb") as f:
        files = {"file": f}
        data = {"purpose": "user_data"}
        response = requests.post(f"{BASE_URL}/files", headers=headers, files=files, data=data)

    if response.status_code != 200:
        print(f"上传失败: {response.text}")
        return None

    result = response.json()
    file_id = result.get("id")
    print(f"文件上传成功，file_id: {file_id}")
    return file_id

def ask_question(file_id, question):
    """使用 file_id 提问"""
    payload = {
        "model": "glm-5.3-flash",  # 使用视觉模型
        "max_tokens": 800,
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

    response = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload)

    if response.status_code != 200:
        print(f"提问失败: {response.text}")
        return None

    result = response.json()
    return result["choices"][0]["message"]["content"]

def main():
    # 文件路径
    file_path = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/v6/pdf-reuse-fileid/run-1/contract.pdf"

    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"错误：文件 {file_path} 不存在")
        exit(1)

    # 1. 上传文件获取 file_id
    file_id = upload_file(file_path)
    if not file_id:
        exit(1)

    print("\n" + "="*50)

    # 2. 依次问三个问题
    questions = [
        "合同编号是什么",
        "合同总金额是多少",
        "违约金怎么算"
    ]

    for i, question in enumerate(questions, 1):
        print(f"\n问题 {i}: {question}")
        print("-" * 30)

        answer = ask_question(file_id, question)
        if answer:
            print("答案:", answer)
        else:
            print("无法获取答案")

        print("\n" + "="*50)

if __name__ == "__main__":
    main()