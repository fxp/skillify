import os
import json
import requests
from pathlib import Path

def main():
    # Read API key from environment variable
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("Error: ZHIPUAI_API_KEY environment variable not set")
        return

    # Base URL for BigModel API
    base_url = "https://open.bigmodel.cn/api"

    # Read comments from comments.txt (assuming it's in the parent directory)
    try:
        comments_file = Path(__file__).parent.parent / "comments.txt"
        with open(comments_file, 'r', encoding='utf-8') as f:
            comments = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("Error: comments.txt not found")
        return

    # Create JSONL request content for batch processing
    # Using glm-4-plus which is in the Batch API whitelist and provides good quality
    jsonl_lines = []
    for i, comment in enumerate(comments, 1):
        # Create unique custom_id with at least 6 characters
        custom_id = f"sentiment-{i:04d}"

        # Request body for sentiment analysis
        request_body = {
            "model": "glm-4-plus",
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个情感分类专家。请将用户评论分类为以下三种情感之一：正面、负面、中性。请只返回分类结果，不要解释。"
                },
                {
                    "role": "user",
                    "content": f"请对以下评论进行情感分类：{comment}"
                }
            ],
            "temperature": 0.1,
            "max_tokens": 10
        }

        # Add to JSONL
        jsonl_lines.append({
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": request_body
        })

    # Write JSONL content to a temporary file
    jsonl_content = '\n'.join(json.dumps(line, ensure_ascii=False) for line in jsonl_lines)
    temp_file = Path(__file__).parent / "batch_requests.jsonl"

    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(jsonl_content)
        print(f"Created batch request file: {temp_file}")
    except Exception as e:
        print(f"Error creating JSONL file: {e}")
        return

    # Upload the JSONL file for batch processing
    try:
        with open(temp_file, 'rb') as f:
            upload_response = requests.post(
                f"{base_url}/paas/v4/files",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": f},
                data={"purpose": "batch"}
            )
            upload_response.raise_for_status()

        file_info = upload_response.json()
        input_file_id = file_info["id"]
        print(f"Uploaded file ID: {input_file_id}")

    except requests.exceptions.RequestException as e:
        print(f"Error uploading file: {e}")
        return

    # Create batch job
    try:
        batch_response = requests.post(
            f"{base_url}/paas/v4/batches",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "input_file_id": input_file_id,
                "endpoint": "/v4/chat/completions",
                "auto_delete_input_file": True,
                "metadata": {
                    "description": "User comment sentiment analysis",
                    "source_file": "comments.txt",
                    "total_requests": len(comments)
                }
            }
        )
        batch_response.raise_for_status()

        batch_info = batch_response.json()
        batch_id = batch_info["id"]
        print(f"Batch job created successfully!")
        print(f"Batch ID: {batch_id}")
        print(f"Status: {batch_info['status']}")

    except requests.exceptions.RequestException as e:
        print(f"Error creating batch job: {e}")
        return

    # Clean up temporary file
    try:
        temp_file.unlink()
        print(f"Cleaned up temporary file: {temp_file}")
    except Exception as e:
        print(f"Warning: Could not clean up temporary file: {e}")

if __name__ == "__main__":
    main()