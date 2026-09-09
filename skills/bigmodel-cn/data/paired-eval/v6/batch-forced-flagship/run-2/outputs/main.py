#!/usr/bin/env python3
"""
Batch sentiment classification using Zhipu AI's Batch API
- Reads comments from comments.txt (one per line)
- Creates JSONL batch requests for sentiment classification
- Uploads file with purpose="batch"
- Creates batch task
- Prints batch ID upon creation
"""

import os
import json
import requests
import time

def read_comments(file_path):
    """Read comments from text file, one per line"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            comments = [line.strip() for line in f if line.strip()]
        print(f"Read {len(comments)} comments from {file_path}")
        return comments
    except FileNotFoundError:
        print(f"Error: {file_path} not found")
        return []
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return []

def create_jsonl_batch_requests(comments, model="glm-4"):
    """Create JSONL batch requests for sentiment classification"""
    batch_requests = []

    # System prompt for sentiment classification
    system_prompt = """你是一个情感分析专家。请对用户评论进行情感分类，并按照指定格式返回结果。
分类类别：正面、负面、中性
输出格式必须是JSON，包含以下字段：
- sentiment: "正面" | "负面" | "中性"
- confidence: 0-1之间的数字，表示分类的置信度
- keywords: 评论中影响情感的关键词数组（1-3个）
- reason: 简要说明分类理由（1-2句话）"""

    for i, comment in enumerate(comments):
        # custom_id must be at least 6 characters
        custom_id = f"req-{i:05d}"

        request = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：\n{comment}"
                    }
                ],
                "temperature": 0.1,  # Lower temperature for more consistent results
                "max_tokens": 200
            }
        }
        batch_requests.append(request)

    return batch_requests

def upload_batch_file(jsonl_content, headers):
    """Upload JSONL file for batch processing"""
    try:
        # Convert JSONL to bytes
        file_content = jsonl_content.encode('utf-8')

        files = {
            "file": ("batch_requests.jsonl", file_content, "application/json")
        }
        data = {"purpose": "batch"}

        resp = requests.post(
            "https://open.bigmodel.cn/api/paas/v4/files",
            headers=headers,
            files=files,
            data=data
        )
        resp.raise_for_status()

        file_info = resp.json()
        print(f"File uploaded successfully: {file_info['id']}")
        return file_info['id']

    except requests.exceptions.RequestException as e:
        print(f"Error uploading batch file: {e}")
        if e.response:
            print(f"Response: {e.response.text}")
        return None

def create_batch_task(file_id, headers):
    """Create batch task with uploaded file"""
    try:
        payload = {
            "input_file_id": file_id,
            "endpoint": "/v4/chat/completions",
            "auto_delete_input_file": True,
            "metadata": {
                "description": "评论情感分析任务",
                "created_at": int(time.time()),
                "total_requests": None  # Will be set after file upload
            }
        }

        resp = requests.post(
            "https://open.bigmodel.cn/api/paas/v4/batches",
            headers={**headers, "Content-Type": "application/json"},
            json=payload
        )
        resp.raise_for_status()

        batch_info = resp.json()
        print(f"Batch task created successfully!")
        print(f"Batch ID: {batch_info['id']}")
        print(f"Status: {batch_info['status']}")
        print(f"Total requests: {batch_info['request_counts']['total']}")

        return batch_info['id']

    except requests.exceptions.RequestException as e:
        print(f"Error creating batch task: {e}")
        if e.response:
            print(f"Response: {e.response.text}")
        return None

def main():
    # Configuration
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    comments_file = "comments.txt"

    if not api_key:
        print("Error: ZHIPUAI_API_KEY environment variable not set")
        return

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    # Read comments
    comments = read_comments(comments_file)
    if not comments:
        print("No comments found or error reading comments")
        return

    # Note: glm-5.3 is not available for Batch API
    # Use the best available model in Batch whitelist
    # According to the documentation, the best models in Batch whitelist are:
    # glm-4-plus, glm-4-air-250414, glm-4-air-0111, etc.
    batch_model = "glm-4-plus"  # Best model available in Batch whitelist

    print(f"Using model: {batch_model}")
    print(f"Processing {len(comments)} comments...")

    # Create JSONL batch requests
    batch_requests = create_jsonl_batch_requests(comments, model=batch_model)

    # Convert to JSONL format
    jsonl_lines = []
    for req in batch_requests:
        jsonl_lines.append(json.dumps(req, ensure_ascii=False))

    jsonl_content = "\n".join(jsonl_lines)
    print(f"Created JSONL with {len(jsonl_lines)} requests")
    print(f"JSONL size: {len(jsonl_content)} bytes")

    # Upload batch file
    file_id = upload_batch_file(jsonl_content, headers)
    if not file_id:
        return

    # Create batch task
    batch_id = create_batch_task(file_id, headers)
    if not batch_id:
        return

    print("\n" + "="*50)
    print("任务创建成功！")
    print(f"Batch ID: {batch_id}")
    print("请使用此ID查询任务状态和获取结果")
    print("="*50)

    # Save batch ID to file for future reference
    with open("batch_id.txt", "w") as f:
        f.write(batch_id)
    print(f"Batch ID已保存到 batch_id.txt")

if __name__ == "__main__":
    main()