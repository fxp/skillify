import os
import requests

def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # API 基础 URL
    base_url = "https://open.bigmodel.cn/api/paas/v4"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        # 1. 上传 PDF 文件获取 file_id
        print("正在上传合同文件...")
        with open("contract.pdf", "rb") as f:
            upload_response = requests.post(
                f"{base_url}/files",
                headers=headers,
                files={"file": ("contract.pdf", f, "application/pdf")},
                data={"purpose": "user_data"}
            )
            upload_response.raise_for_status()
            upload_data = upload_response.json()
            file_id = upload_data["id"]
            print(f"文件上传成功，file_id: {file_id}")

        # 2. 定义三个问题
        questions = [
            "合同编号是什么",
            "合同总金额是多少",
            "违约金怎么算"
        ]

        # 3. 使用同一个 file_id 依次提问
        print("\n开始提问：")
        for i, question in enumerate(questions, 1):
            print(f"\n问题 {i}: {question}")
            print("回答:", end=" ")

            # 构建多模态请求，包含文件引用和文本问题
            chat_response = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={
                    "model": "glm-4.6",  # 使用支持多模态的模型
                    "max_tokens": 800,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "file", "file_id": file_id},  # 复用同一个 file_id
                            {"type": "text", "text": question}
                        ]
                    }]
                }
            )
            chat_response.raise_for_status()
            answer = chat_response.json()["choices"][0]["message"]["content"]
            print(answer)

        print("\n所有问题回答完成！")

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
    except KeyError as e:
        print(f"响应格式错误，缺少字段: {e}")
    except FileNotFoundError:
        print("错误：当前目录下找不到 contract.pdf 文件")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()