#!/usr/bin/env python3
import os
import requests

def main():
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # API基础配置
    base_url = "https://open.bigmodel.cn/api/paas/v4"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 合同文件路径（从run-1目录获取）
    contract_path = "../run-1/contract.pdf"

    try:
        # 第一步：上传文件获取file_id
        print("正在上传合同文件...")
        with open(contract_path, "rb") as f:
            upload_response = requests.post(
                f"{base_url}/files",
                headers=headers,
                files={"file": ("contract.pdf", f, "application/pdf")},
                data={"purpose": "user_data"}  # 必须是user_data
            )
            upload_response.raise_for_status()
            file_id = upload_response.json()["id"]
            print(f"文件上传成功，file_id: {file_id}")

        # 第二步：使用同一个file_id问三个问题
        questions = [
            "合同编号是什么",
            "合同总金额是多少",
            "违约金怎么算"
        ]

        print("\n开始分析合同内容...")

        for i, question in enumerate(questions, 1):
            print(f"\n问题 {i}: {question}")

            # 构建请求，复用同一个file_id
            chat_response = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={
                    "model": "glm-4.6",  # 使用支持多模态的模型
                    "max_tokens": 800,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "file", "file_id": file_id},  # 复用file_id
                                {"type": "text", "text": question}
                            ]
                        }
                    ]
                }
            )
            chat_response.raise_for_status()
            answer = chat_response.json()["choices"][0]["message"]["content"]
            print(f"答案: {answer}")

        print(f"\n所有问题回答完成！共复用了file_id: {file_id}")

    except FileNotFoundError:
        print(f"错误：找不到合同文件 {contract_path}")
    except requests.exceptions.RequestException as e:
        print(f"API请求错误: {e}")
        if e.response is not None:
            print(f"响应内容: {e.response.text}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()