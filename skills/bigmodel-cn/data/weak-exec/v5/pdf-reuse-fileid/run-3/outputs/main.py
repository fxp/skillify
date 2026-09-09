import os
import requests

def upload_pdf_file(file_path):
    """上传PDF文件并获取file_id"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    headers = {"Authorization": f"Bearer {api_key}"}
    base_url = "https://open.bigmodel.cn/api/paas/v4"

    with open(file_path, "rb") as f:
        response = requests.post(
            f"{base_url}/files",
            headers=headers,
            files={"file": (os.path.basename(file_path), f, "application/pdf")},
            data={"purpose": "user_data"}
        )

    response.raise_for_status()
    return response.json()["id"]

def ask_question(file_id, question, model="glm-4.6"):
    """使用file_id向模型提问"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    headers = {"Authorization": f"Bearer {api_key}"}
    base_url = "https://open.bigmodel.cn/api/paas/v4"

    payload = {
        "model": model,
        "max_tokens": 800,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "file", "file_id": file_id},
                    {"type": "text", "text": question}
                ]
            }
        ]
    }

    response = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=payload
    )
    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"]

def main():
    # 合同文件路径
    contract_file = "contract.pdf"

    try:
        print("正在上传合同文件...")
        # 上传文件获取file_id
        file_id = upload_pdf_file(contract_file)
        print(f"文件上传成功，file_id: {file_id}")

        # 三个问题
        questions = [
            "合同编号是什么",
            "合同总金额是多少",
            "违约金怎么算"
        ]

        # 逐个提问并打印答案
        for i, question in enumerate(questions, 1):
            print(f"\n问题 {i}: {question}")
            print("-" * 50)
            try:
                answer = ask_question(file_id, question)
                print(f"答案: {answer}")
            except Exception as e:
                print(f"提问失败: {str(e)}")
            print("=" * 50)

    except Exception as e:
        print(f"程序执行失败: {str(e)}")

if __name__ == "__main__":
    main()