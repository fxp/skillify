#!/usr/bin/env python3
"""
合同PDF信息提取脚本
将合同文件上传至智谱AI平台，然后复用file_id进行多轮问答
"""

import os
import requests
import time

# API配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# 合同文件路径
CONTRACT_FILE_PATH = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/v4/pdf-reuse-fileid/run-2/contract.pdf"

# 头部配置
headers = {
    "Authorization": f"Bearer {API_KEY}"
}


def upload_contract_file():
    """上传合同文件，获取file_id"""
    print("正在上传合同文件...")

    with open(CONTRACT_FILE_PATH, "rb") as f:
        files = {"file": f}
        data = {"purpose": "user_data"}

        response = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=headers,
            files=files,
            data=data
        )
        response.raise_for_status()

        file_info = response.json()
        file_id = file_info["id"]
        print(f"文件上传成功，file_id: {file_id}")

        return file_id


def ask_question_with_file(file_id, question, system_prompt="请仔细阅读以下合同内容，并准确回答我的问题。"):
    """使用file_id向模型提问"""
    payload = {
        "model": "glm-5.3-flash",  # 使用支持文件处理的模型
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
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

    response = requests.post(
        f"{BASE_URL}/paas/v4/chat/completions",
        headers={**headers, "Content-Type": "application/json"},
        json=payload
    )
    response.raise_for_status()

    result = response.json()
    return result["choices"][0]["message"]["content"]


def main():
    """主函数"""
    print("开始处理合同文件...")

    # 1. 上传文件，获取file_id
    try:
        file_id = upload_contract_file()
        print(f"✅ 文件上传成功，file_id: {file_id}")
    except Exception as e:
        print(f"❌ 文件上传失败: {e}")
        return

    # 2. 准备三个问题
    questions = [
        "合同编号是什么？",
        "合同总金额是多少？",
        "违约金怎么算？"
    ]

    # 3. 使用同一个file_id依次回答三个问题
    print("\n开始回答问题...")
    for i, question in enumerate(questions, 1):
        print(f"\n--- 问题 {i}: {question} ---")
        try:
            answer = ask_question_with_file(file_id, question)
            print(f"答案: {answer}")
        except Exception as e:
            print(f"❌ 回答第{i}个问题时出错: {e}")


if __name__ == "__main__":
    main()