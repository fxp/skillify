#!/usr/bin/env python3
import os
import json
import requests
from io import BytesIO

def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("Error: Please set ZHIPUAI_API_KEY environment variable")
        return

    # Base URL
    base_url = "https://open.bigmodel.cn/api/paas/v4"

    # 读取评论文件
    comments_file = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/v6/batch-best-model/run-2/comments.txt"
    with open(comments_file, 'r', encoding='utf-8') as f:
        comments = [line.strip() for line in f if line.strip()]

    print(f"Loaded {len(comments)} comments")

    # 构造 Batch 请求的 JSONL 内容
    jsonl_lines = []
    for i, comment in enumerate(comments):
        # custom_id 必须至少6个字符
        custom_id = f"req-{i+1:05d}"

        # 构造请求体
        request_body = {
            "model": "glm-4-plus",  # Batch API 中最强的模型
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个情感分类专家。请对用户的评论进行情感分类，只返回一个分类结果：正面、负面或中性。"
                },
                {
                    "role": "user",
                    "content": f"请对以下评论进行情感分类：{comment}"
                }
            ],
            "max_tokens": 50,
            "temperature": 0.1,
            "stream": False
        }

        # 构造 Batch 请求行
        line = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": request_body
        }

        jsonl_lines.append(json.dumps(line, ensure_ascii=False))

    # 创建 JSONL 文件内容
    jsonl_content = "\n".join(jsonl_lines)
    print(f"Created JSONL with {len(jsonl_lines)} requests")

    # 上传文件到 Batch
    print("Uploading file for batch processing...")
    files = {
        "file": ("batch_requests.jsonl", BytesIO(jsonl_content.encode('utf-8')), "application/json")
    }
    data = {"purpose": "batch"}

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    try:
        upload_response = requests.post(
            f"{base_url}/files",
            headers=headers,
            files=files,
            data=data
        )
        upload_response.raise_for_status()
        file_info = upload_response.json()
        input_file_id = file_info["id"]
        print(f"File uploaded successfully. File ID: {input_file_id}")
    except requests.exceptions.RequestException as e:
        print(f"Error uploading file: {e}")
        if e.response:
            print(f"Response: {e.response.text}")
        return

    # 创建 Batch 任务
    print("Creating batch task...")
    batch_payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分类任务",
            "total_requests": len(comments)
        }
    }

    try:
        batch_response = requests.post(
            f"{base_url}/batches",
            headers={**headers, "Content-Type": "application/json"},
            json=batch_payload
        )
        batch_response.raise_for_status()
        batch_info = batch_response.json()
        batch_id = batch_info["id"]

        print(f"Batch task created successfully!")
        print(f"Batch ID: {batch_id}")
        print(f"Task status: {batch_info.get('status', 'unknown')}")
        print(f"Total requests: {batch_info.get('request_counts', {}).get('total', 'unknown')}")

    except requests.exceptions.RequestException as e:
        print(f"Error creating batch task: {e}")
        if e.response:
            print(f"Response: {e.response.text}")
        return

if __name__ == "__main__":
    main()