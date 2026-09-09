#!/usr/bin/env python3
import os
import requests
import json

def upload_file(file_path):
    """上传文件获取 file_id"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    url = "https://open.bigmodel.cn/api/paas/v4/files"

    with open(file_path, "rb") as f:
        response = requests.post(
            url,
            headers=headers,
            files={"file": (os.path.basename(file_path), f, "application/pdf")},
            data={"purpose": "user_data"}
        )
        response.raise_for_status()

    result = response.json()
    return result["id"]

def ask_question(file_id, question, model="glm-5.3-flash"):
    """使用 file_id 提问"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    payload = {
        "model": model,
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

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    result = response.json()
    return result["choices"][0]["message"]["content"]

def main():
    # 检查环境变量
    if not os.environ.get('ZHIPUAI_API_KEY'):
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    pdf_file = "contract.pdf"

    # 检查 PDF 文件是否存在
    if not os.path.exists(pdf_file):
        print(f"错误：找不到 {pdf_file} 文件")
        return

    try:
        # 上传文件获取 file_id
        print("正在上传文件...")
        file_id = upload_file(pdf_file)
        print(f"文件上传成功，file_id: {file_id}")

        # 定义三个问题
        questions = [
            "合同编号是什么",
            "合同总金额是多少",
            "违约金怎么算"
        ]

        # 逐个提问
        print("\n开始提问：")
        for i, question in enumerate(questions, 1):
            print(f"\n问题 {i}: {question}")
            print("回答:", end=" ")
            try:
                answer = ask_question(file_id, question)
                print(answer)
            except Exception as e:
                print(f"提问失败: {e}")
                break

    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    main()