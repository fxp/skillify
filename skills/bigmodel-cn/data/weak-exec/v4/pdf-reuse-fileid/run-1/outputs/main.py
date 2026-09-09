#!/usr/bin/env python3
import os
import requests
import time

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"

if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

# 请求头
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 文件路径
PDF_FILE = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/v4/pdf-reuse-fileid/run-1/contract.pdf"

def upload_pdf_file(file_path):
    """上传PDF文件获取file_id"""
    print("正在上传PDF文件...")

    with open(file_path, "rb") as f:
        files = {"file": f}
        data = {"purpose": "user_data"}

        response = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers={"Authorization": f"Bearer {API_KEY}"},
            files=files,
            data=data
        )

    response.raise_for_status()
    file_id = response.json()["id"]
    print(f"文件上传成功，file_id: {file_id}")
    return file_id

def ask_question(file_id, question):
    """使用file_id提问"""
    payload = {
        "model": "glm-5.3-flash",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "file", "file": {"file_id": file_id}},
                    {"type": "text", "text": question}
                ]
            }
        ],
        "temperature": 0.1,
        "max_tokens": 1000
    }

    response = requests.post(
        f"{BASE_URL}/paas/v4/chat/completions",
        headers=headers,
        json=payload
    )
    response.raise_for_status()

    answer = response.json()["choices"][0]["message"]["content"]
    return answer

def main():
    try:
        # 1. 上传文件获取file_id
        file_id = upload_pdf_file(PDF_FILE)

        # 2. 定义三个问题
        questions = [
            "合同编号是什么？",
            "合同总金额是多少？",
            "违约金怎么算？"
        ]

        # 3. 依次提问并打印答案
        print("\n=== 开始提问 ===")
        for i, question in enumerate(questions, 1):
            print(f"\n问题 {i}: {question}")
            print("答案:")
            answer = ask_question(file_id, question)
            print(answer)
            print("-" * 50)

    except requests.exceptions.RequestException as e:
        print(f"请求错误: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应内容: {e.response.text}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()