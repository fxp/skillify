#!/usr/bin/env python3
import os
import requests

# 从环境变量读取API Key
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

# API配置
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def upload_contract_pdf():
    """上传合同PDF文件到智谱平台"""
    pdf_path = "../contract.pdf"

    if not os.path.exists(pdf_path):
        print(f"错误：找不到合同文件 {pdf_path}")
        exit(1)

    try:
        with open(pdf_path, "rb") as f:
            response = requests.post(
                f"{BASE_URL}/files",
                headers=HEADERS,
                files={"file": f},
                data={"purpose": "user_data"}
            )
            response.raise_for_status()

            file_data = response.json()
            file_id = file_data["id"]
            print(f"文件上传成功，file_id: {file_id}")
            return file_id

    except requests.exceptions.RequestException as e:
        print(f"文件上传失败: {e}")
        if e.response:
            print(f"响应内容: {e.response.text}")
        exit(1)

def ask_question_with_file(file_id, question):
    """使用上传的file_id向模型提问"""
    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=HEADERS,
            json={
                "model": "glm-5v-turbo",  # 使用视觉理解模型
                "max_tokens": 800,
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
        )
        response.raise_for_status()

        result = response.json()
        answer = result["choices"][0]["message"]["content"]
        return answer

    except requests.exceptions.RequestException as e:
        print(f"提问失败: {e}")
        if e.response:
            print(f"响应内容: {e.response.text}")
        return None

def main():
    """主函数：上传文件并问三个问题"""
    print("开始处理合同文件...")

    # 1. 上传合同文件获取file_id
    file_id = upload_contract_pdf()

    # 2. 定义三个问题
    questions = [
        "合同编号是什么",
        "合同总金额是多少",
        "违约金怎么算"
    ]

    # 3. 依次提问并打印答案
    print("\n开始提问...")
    for i, question in enumerate(questions, 1):
        print(f"\n问题 {i}: {question}")
        print("-" * 50)

        answer = ask_question_with_file(file_id, question)
        if answer:
            print(f"答案: {answer}")
        else:
            print("无法获取答案")

        print("=" * 50)

if __name__ == "__main__":
    main()