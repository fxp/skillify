import os
import json
import requests
import io

def main():
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # Base URL
    base_url = "https://open.bigmodel.cn/api"
    headers = {"Authorization": f"Bearer {api_key}"}

    # 读取comments.txt中的评论
    try:
        with open("../comments.txt", "r", encoding="utf-8") as f:
            comments = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("错误：找不到comments.txt文件")
        return

    print(f"读取到 {len(comments)} 条评论")

    # 构造JSONL请求文件
    jsonl_lines = []
    for i, comment in enumerate(comments):
        # custom_id必须至少6个字符
        custom_id = f"req-{i:05d}"

        # 构造请求体
        request_body = {
            "model": "glm-5.1",  # Batch支持的最佳模型
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的情感分类师。请对用户的评论进行情感分类，只返回以下三种之一：正面、负面、中性。评论可能涉及产品、服务、物流等多个方面。"
                },
                {
                    "role": "user",
                    "content": f"请对以下评论进行情感分类：{comment}"
                }
            ],
            "max_tokens": 50,  # 情感分类只需要简短回答
            "temperature": 0.1,  # 降低随机性，提高一致性
            "stream": False
        }

        # 构造JSONL行
        jsonl_line = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": request_body
        }

        jsonl_lines.append(json.dumps(jsonl_line, ensure_ascii=False))

    # 创建JSONL文件内容
    jsonl_content = "\n".join(jsonl_lines)

    # 上传文件
    print("正在上传请求文件...")
    try:
        files = {
            "file": ("batch_requests.jsonl", io.BytesIO(jsonl_content.encode("utf-8")), "application/json")
        }
        data = {"purpose": "batch"}

        upload_response = requests.post(
            f"{base_url}/paas/v4/files",
            headers=headers,
            files=files,
            data=data
        )
        upload_response.raise_for_status()
        file_info = upload_response.json()
        input_file_id = file_info["id"]
        print(f"文件上传成功，文件ID: {input_file_id}")
    except requests.exceptions.RequestException as e:
        print(f"文件上传失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应内容: {e.response.text}")
        return

    # 创建Batch任务
    print("正在创建Batch任务...")
    try:
        batch_request = {
            "input_file_id": input_file_id,
            "endpoint": "/v4/chat/completions",
            "auto_delete_input_file": True,
            "metadata": {
                "description": "评论情感分析任务",
                "total_requests": len(comments)
            }
        }

        batch_response = requests.post(
            f"{base_url}/paas/v4/batches",
            headers={**headers, "Content-Type": "application/json"},
            json=batch_request
        )
        batch_response.raise_for_status()
        batch_info = batch_response.json()
        batch_id = batch_info["id"]

        print(f"Batch任务创建成功！")
        print(f"Batch ID: {batch_id}")
        print(f"任务状态: {batch_info.get('status', 'unknown')}")
        print(f"请使用此ID查询任务状态和结果")

    except requests.exceptions.RequestException as e:
        print(f"创建Batch任务失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应内容: {e.response.text}")
        return

if __name__ == "__main__":
    main()