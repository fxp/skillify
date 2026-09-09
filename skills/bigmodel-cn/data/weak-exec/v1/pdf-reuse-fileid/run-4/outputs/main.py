#!/usr/bin/env python3
import os
import requests
import time

# API配置
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def upload_pdf_file(file_path):
    """上传PDF文件获取file_id"""
    print(f"正在上传文件: {file_path}")

    with open(file_path, "rb") as f:
        files = {"file": f}
        data = {"purpose": "user_data"}

        response = requests.post(
            f"{BASE_URL}/files",
            headers=HEADERS,
            files=files,
            data=data
        )

        if response.status_code != 200:
            print(f"上传失败: {response.status_code}")
            print(response.text)
            return None

        result = response.json()
        file_id = result.get("id")
        print(f"文件上传成功，file_id: {file_id}")
        return file_id

def ask_question(file_id, question):
    """使用file_id提问"""
    payload = {
        "model": "glm-5.3-flash",  # 使用支持视觉的模型
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
        ],
        "max_tokens": 2000
    }

    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=HEADERS,
            json=payload,
            timeout=60
        )

        if response.status_code != 200:
            print(f"提问失败: {response.status_code}")
            print(response.text)
            return None

        result = response.json()
        answer = result["choices"][0]["message"]["content"]
        return answer

    except requests.exceptions.Timeout:
        print("请求超时")
        return None
    except Exception as e:
        print(f"请求出错: {str(e)}")
        return None

def main():
    # 检查API Key
    if not API_KEY:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 检查PDF文件是否存在
    pdf_file = "contract.pdf"
    if not os.path.exists(pdf_file):
        print(f"错误: 找不到文件 {pdf_file}")
        return

    # 1. 上传PDF文件获取file_id
    file_id = upload_pdf_file(pdf_file)
    if not file_id:
        print("文件上传失败，程序退出")
        return

    print(f"\n已成功上传文件，file_id: {file_id}")
    print("现在开始提问...\n")

    # 2. 依次问三个问题
    questions = [
        "合同编号是什么",
        "合同总金额是多少",
        "违约金怎么算"
    ]

    for i, question in enumerate(questions, 1):
        print(f"问题 {i}: {question}")
        answer = ask_question(file_id, question)

        if answer:
            print(f"答案 {i}: {answer}\n")
        else:
            print(f"问题 {i} 回答失败\n")

        # 避免请求过于频繁
        if i < len(questions):
            time.sleep(1)

if __name__ == "__main__":
    main()