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
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def upload_file(file_path):
    """上传文件并获取 file_id"""
    print(f"正在上传文件: {file_path}")

    with open(file_path, "rb") as f:
        response = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers={"Authorization": f"Bearer {API_KEY}"},
            files={"file": f},
            data={"purpose": "user_data"}
        )

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
        "model": "glm-5.3-flash",  # 使用支持文件输入的模型
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
        "stream": False
    }

    try:
        response = requests.post(
            f"{BASE_URL}/paas/v4/chat/completions",
            headers=HEADERS,
            json=payload,
            timeout=60
        )

        if response.status_code != 200:
            print(f"提问失败: {response.text}")
            return None

        result = response.json()
        return result["choices"][0]["message"]["content"]

    except requests.exceptions.RequestException as e:
        print(f"请求异常: {e}")
        return None

def main():
    # 文件路径
    contract_path = "../run-1/contract.pdf"

    # 检查文件是否存在
    if not os.path.exists(contract_path):
        print(f"错误：找不到合同文件 {contract_path}")
        exit(1)

    # 上传文件获取 file_id
    file_id = upload_file(contract_path)
    if not file_id:
        print("文件上传失败，退出程序")
        exit(1)

    print("\n" + "="*50)
    print("开始提问...")
    print("="*50 + "\n")

    # 三个问题
    questions = [
        "合同编号是什么？",
        "合同总金额是多少？",
        "违约金怎么算？"
    ]

    for i, question in enumerate(questions, 1):
        print(f"问题 {i}: {question}")
        print("-" * 30)

        answer = ask_question(file_id, question)
        if answer:
            print("回答:")
            print(answer)
        else:
            print("未能获取到回答")

        print("\n" + "="*50 + "\n")
        time.sleep(1)  # 避免请求过快

if __name__ == "__main__":
    main()