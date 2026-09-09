#!/usr/bin/env python3
"""
合同信息提取脚本
上传 contract.pdf 到智谱AI平台，然后使用同一个 file_id 询问多个问题
"""

import os
import requests
import json

# 配置
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
MODEL = "glm-5.3-flash"  # 必须使用视觉模型才能处理文件输入

def upload_pdf_file():
    """上传PDF文件到平台，返回file_id"""
    print("正在上传合同文件...")

    # 读取合同文件
    with open("contract.pdf", "rb") as f:
        files = {"file": ("contract.pdf", f, "application/pdf")}
        data = {"purpose": "user_data"}  # 重要：必须使用 user_data

        headers = {"Authorization": f"Bearer {API_KEY}"}

        try:
            response = requests.post(
                f"{BASE_URL}/files",
                headers=headers,
                files=files,
                data=data
            )
            response.raise_for_status()
            upload_result = response.json()
            file_id = upload_result["id"]
            print(f"✓ 文件上传成功，file_id: {file_id}")
            return file_id
        except requests.exceptions.RequestException as e:
            print(f"✗ 文件上传失败: {e}")
            if e.response:
                print(f"响应内容: {e.response.text}")
            return None

def ask_questions(file_id, questions):
    """使用同一个file_id询问多个问题"""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    results = {}

    for i, question in enumerate(questions, 1):
        print(f"\n问题 {i}/{len(questions)}: {question}")

        # 构建消息，包含文件引用和问题文本
        message_data = [
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

        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": message_data
                }
            ],
            "max_tokens": 1000
        }

        try:
            response = requests.post(
                f"{BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()

            # 提取回答
            answer = result["choices"][0]["message"]["content"]
            results[question] = answer
            print(f"✓ 回答: {answer}")

        except requests.exceptions.RequestException as e:
            error_msg = f"✗ 询问失败: {e}"
            print(error_msg)
            if e.response:
                print(f"响应内容: {e.response.text}")
            results[question] = error_msg

    return results

def main():
    """主函数"""
    # 检查API Key
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 检查合同文件是否存在
    if not os.path.exists("contract.pdf"):
        print("错误：contract.pdf 文件不存在")
        return

    questions = [
        "合同编号是什么",
        "合同总金额是多少",
        "违约金怎么算"
    ]

    # 1. 上传文件
    file_id = upload_pdf_file()
    if not file_id:
        print("无法继续，请检查网络连接和API Key")
        return

    print(f"\n开始使用 file_id: {file_id} 询问 {len(questions)} 个问题")

    # 2. 询问多个问题（复用同一个file_id）
    answers = ask_questions(file_id, questions)

    # 3. 打印最终结果
    print("\n" + "="*50)
    print("最终结果汇总:")
    print("="*50)
    for i, question in enumerate(questions, 1):
        answer = answers[question]
        print(f"\n问题{i}: {question}")
        print(f"答案: {answer}")

if __name__ == "__main__":
    main()