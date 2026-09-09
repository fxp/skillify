#!/usr/bin/env python3
import os
import json
import requests

# API 配置
API_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

def upload_file(file_path):
    """上传文件到智谱平台，返回 file_id"""
    headers = {"Authorization": f"Bearer {API_KEY}"}

    with open(file_path, "rb") as f:
        files = {"file": ("contract.pdf", f, "application/pdf")}
        data = {"purpose": "user_data"}

        response = requests.post(
            f"{API_BASE_URL}/files",
            headers=headers,
            files=files,
            data=data
        )
        response.raise_for_status()

        result = response.json()
        file_id = result["id"]
        print(f"文件上传成功，file_id: {file_id}")
        return file_id

def ask_question(file_id, question):
    """使用 file_id 提问"""
    headers = {"Authorization": f"Bearer {API_KEY}"}

    payload = {
        "model": "glm-5.3-flash",  # 使用支持视觉的模型
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

    response = requests.post(
        f"{API_BASE_URL}/chat/completions",
        headers=headers,
        json=payload
    )
    response.raise_for_status()

    result = response.json()
    return result["choices"][0]["message"]["content"]

def main():
    # 检查 API Key
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 合同文件路径
    contract_path = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/v6/pdf-reuse-fileid/run-1/contract.pdf"

    if not os.path.exists(contract_path):
        print(f"错误：找不到合同文件 {contract_path}")
        return

    try:
        # 1. 上传文件获取 file_id
        print("正在上传合同文件...")
        file_id = upload_file(contract_path)

        # 2. 定义三个问题
        questions = [
            "合同编号是什么",
            "合同总金额是多少",
            "违约金怎么算"
        ]

        # 3. 依次提问并打印答案
        print("\n开始提问：")
        for i, question in enumerate(questions, 1):
            print(f"\n问题 {i}: {question}")
            print("-" * 50)
            try:
                answer = ask_question(file_id, question)
                print(f"答案: {answer}")
            except Exception as e:
                print(f"提问失败: {e}")

    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()