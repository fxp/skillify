#!/usr/bin/env python3
"""
合同信息提取工具
使用智谱 BigModel 的多模态能力读取 PDF 合同并回答问题
"""

import os
import requests
import time

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"
MODEL = "glm-5.3-flash"  # 支持多模态的模型

# 全局变量，存储文件ID
file_id = None

def upload_pdf(file_path):
    """上传PDF文件并获取file_id"""
    global file_id

    if file_id:
        print("文件已上传，file_id:", file_id)
        return file_id

    url = f"{BASE_URL}/paas/v4/files"

    with open(file_path, "rb") as f:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {API_KEY}"},
            files={"file": f},
            data={"purpose": "user_data"}
        )

    if response.status_code != 200:
        raise Exception(f"上传失败: {response.text}")

    result = response.json()
    file_id = result["id"]
    print(f"文件上传成功，file_id: {file_id}")
    return file_id

def ask_question(question, file_id=None):
    """使用file_id向模型提问"""
    url = f"{BASE_URL}/paas/v4/chat/completions"

    messages = [{"role": "system", "content": "你是一个专业的合同分析助手，请准确回答用户的问题。"}]

    # 如果提供了file_id，添加文件引用
    if file_id:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "file", "file": {"file_id": file_id}}
            ]
        })
    else:
        messages.append({"role": "user", "content": question})

    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 1000,
        "temperature": 0.1
    }

    response = requests.post(url, json=payload, headers={"Authorization": f"Bearer {API_KEY}"})

    if response.status_code != 200:
        raise Exception(f"API调用失败: {response.text}")

    result = response.json()
    return result["choices"][0]["message"]["content"]

def main():
    """主函数"""
    if not API_KEY:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY")
        return

    pdf_file = "contract.pdf"

    # 检查PDF文件是否存在
    if not os.path.exists(pdf_file):
        print(f"错误: 找不到 {pdf_file} 文件")
        return

    try:
        # 上传PDF文件
        file_id = upload_pdf(pdf_file)

        # 问三个问题
        questions = [
            "合同编号是什么",
            "合同总金额是多少",
            "违约金怎么算"
        ]

        print("\n=== 开始提取合同信息 ===\n")

        for i, question in enumerate(questions, 1):
            print(f"问题 {i}: {question}")
            answer = ask_question(question, file_id)
            print(f"答案 {i}: {answer}\n")

            # 稍微延迟，避免请求过快
            time.sleep(0.5)

        print("=== 信息提取完成 ===")

    except Exception as e:
        print(f"发生错误: {str(e)}")

if __name__ == "__main__":
    main()