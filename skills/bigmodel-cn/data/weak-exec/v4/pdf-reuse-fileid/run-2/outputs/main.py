#!/usr/bin/env python3
"""
合同信息提取脚本
使用智谱BigModel API读取PDF合同并回答问题
"""

import os
import requests
import json

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"

if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

# 上传文件
def upload_file(file_path):
    """上传文件并获取file_id"""
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    with open(file_path, "rb") as f:
        files = {"file": f}
        data = {"purpose": "user_data"}

        response = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=headers,
            files=files,
            data=data
        )

    if response.status_code != 200:
        print(f"上传文件失败: {response.status_code}")
        print(response.text)
        return None

    result = response.json()
    file_id = result.get("id")
    print(f"文件上传成功，file_id: {file_id}")
    return file_id

# 询问问题
def ask_question(file_id, question):
    """使用file_id提问"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "glm-5.3-flash",  # 使用支持视觉的模型
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "file", "file": {"file_id": file_id}}
                ]
            }
        ]
    }

    try:
        response = requests.post(
            f"{BASE_URL}/paas/v4/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )

        if response.status_code != 200:
            print(f"请求失败: {response.status_code}")
            print(response.text)
            return None

        result = response.json()
        return result["choices"][0]["message"]["content"]

    except Exception as e:
        print(f"请求出错: {str(e)}")
        return None

def main():
    # 文件路径
    file_path = "contract.pdf"

    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"错误：文件 {file_path} 不存在")
        return

    # 1. 上传文件获取file_id
    print("正在上传文件...")
    file_id = upload_file(file_path)
    if not file_id:
        return

    # 2. 准备三个问题
    questions = [
        "合同编号是什么？",
        "合同总金额是多少？",
        "违约金怎么算？"
    ]

    # 3. 使用同一个file_id依次回答三个问题
    print("\n开始提问：")
    for i, question in enumerate(questions, 1):
        print(f"\n问题 {i}: {question}")
        print("答案:", end=" ")

        answer = ask_question(file_id, question)
        if answer:
            print(answer)
        else:
            print("无法获取答案")

    print("\n所有问题回答完毕")

if __name__ == "__main__":
    main()