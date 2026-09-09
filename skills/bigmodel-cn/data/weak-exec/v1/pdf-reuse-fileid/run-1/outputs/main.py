#!/usr/bin/env python3
"""
合同分析脚本
将合同PDF上传至智谱AI平台，使用file_id进行多轮提问，避免重复上传文件
"""

import os
import requests
import json
from typing import Optional, Dict, Any

# API配置
API_BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# headers
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def upload_file(file_path: str, purpose: str = "user_data") -> str:
    """上传文件并返回file_id"""

    # 检查文件是否存在
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 准备上传
    with open(file_path, 'rb') as f:
        files = {
            'file': f
        }
        data = {
            'purpose': purpose
        }

        response = requests.post(
            f"{API_BASE_URL}/paas/v4/files",
            headers={"Authorization": f"Bearer {API_KEY}"},
            files=files,
            data=data
        )

    response.raise_for_status()
    result = response.json()
    file_id = result.get("id")

    if not file_id:
        raise ValueError("上传文件失败，未获取到file_id")

    print(f"文件上传成功，file_id: {file_id}")
    return file_id

def ask_question(file_id: str, question: str, model: str = "glm-5.3") -> str:
    """使用file_id提问"""

    # 构建消息，使用file类型引用上传的文件
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": question
                },
                {
                    "type": "file",
                    "file": {
                        "file_id": file_id
                    }
                }
            ]
        }
    ]

    payload = {
        "model": model,
        "messages": messages,
        "stream": False
    }

    response = requests.post(
        f"{API_BASE_URL}/paas/v4/chat/completions",
        headers=HEADERS,
        json=payload
    )

    response.raise_for_status()
    result = response.json()

    # 提取回答内容
    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

    return content

def main():
    # 文件路径
    contract_file = "contract.pdf"

    # 检查文件是否存在
    if not os.path.exists(contract_file):
        print(f"错误：在当前目录中未找到 {contract_file}")
        print("请确保 contract.pdf 文件与脚本在同一目录下")
        return

    try:
        # 1. 上传文件获取file_id
        print("正在上传合同文件...")
        file_id = upload_file(contract_file)

        print(f"\n文件已上传，file_id: {file_id}")
        print("开始分析合同...\n")

        # 2. 问三个问题
        questions = [
            "合同编号是什么？",
            "合同总金额是多少？",
            "违约金怎么算？"
        ]

        for i, question in enumerate(questions, 1):
            print(f"问题 {i}: {question}")
            answer = ask_question(file_id, question)
            print(f"答案 {i}: {answer}")
            print("-" * 50)

        print("\n分析完成！")

    except Exception as e:
        print(f"发生错误: {str(e)}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())