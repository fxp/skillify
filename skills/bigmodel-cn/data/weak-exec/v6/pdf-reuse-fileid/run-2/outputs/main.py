#!/usr/bin/env python3
"""
智谱 BigModel PDF 文件分析脚本
上传合同文件并复用 file_id 回答多个问题
"""

import os
import requests
import json
from pathlib import Path

# 配置
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# 合同文件路径
CONTRACT_PDF_PATH = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/v6/pdf-reuse-fileid/run-1/contract.pdf"

def upload_file():
    """上传PDF文件获取file_id"""
    print("正在上传合同文件...")

    try:
        with open(CONTRACT_PDF_PATH, "rb") as f:
            response = requests.post(
                f"{BASE_URL}/files",
                headers=HEADERS,
                files={"file": f},
                data={"purpose": "user_data"}
            )
            response.raise_for_status()

            file_info = response.json()
            file_id = file_info["id"]
            print(f"文件上传成功，file_id: {file_id}")
            return file_id

    except Exception as e:
        print(f"文件上传失败: {e}")
        raise

def ask_question(file_id, question):
    """使用file_id提问"""
    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=HEADERS,
            json={
                "model": "glm-5.3-flash",  # 使用支持视觉的模型
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "file", "file": {"file_id": file_id}},
                            {"type": "text", "text": question}
                        ]
                    }
                ],
                "max_tokens": 800
            }
        )
        response.raise_for_status()

        result = response.json()
        answer = result["choices"][0]["message"]["content"]
        return answer

    except Exception as e:
        print(f"提问失败: {e}")
        return None

def main():
    """主函数"""
    print("开始分析合同文件...")

    # 1. 上传文件获取file_id
    file_id = upload_file()

    # 2. 定义三个问题
    questions = [
        "合同编号是什么",
        "合同总金额是多少",
        "违约金怎么算"
    ]

    # 3. 逐个提问并打印答案
    print("\n=== 合同分析结果 ===")
    for i, question in enumerate(questions, 1):
        print(f"\n问题 {i}: {question}")
        print("-" * 50)

        answer = ask_question(file_id, question)
        if answer:
            print(f"答案: {answer}")
        else:
            print("无法获取答案")

        print("-" * 50)

    print("\n分析完成！")

if __name__ == "__main__":
    main()