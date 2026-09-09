#!/usr/bin/env python3
import os
import json
import requests
import time
import uuid
from pathlib import Path

# 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# 读取评论文件
def read_comments():
    comments_file = Path(__file__).parent.parent.parent / "comments.txt"
    with open(comments_file, 'r', encoding='utf-8') as f:
        comments = [line.strip() for line in f if line.strip()]
    return comments

# 构造 batch 请求文件
def create_batch_requests(comments):
    requests = []
    for i, comment in enumerate(comments, 1):
        # 使用足够长的 custom_id（至少6个字符）
        custom_id = f"sentiment-{i:03d}"

        request_data = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-5.1",  # Batch API 支持的最好模型
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个情感分类专家。请对用户评论进行情感分类，只返回一个分类结果：正面、负面或中性。分类标准：\n- 正面：表达满意、赞扬、推荐等积极情绪\n- 负面：表达不满、抱怨、批评等消极情绪\n- 中性：客观描述、无明显情感倾向或混合情感\n\n请只返回分类结果，不要解释。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低随机性，提高一致性
                "max_tokens": 10  # 只要一个词的结果
            }
        }
        requests.append(request_data)
    return requests

# 上传 batch 文件
def upload_batch_file(requests):
    # 创建临时 JSONL 文件
    temp_file = Path("temp_batch_requests.jsonl")
    with open(temp_file, 'w', encoding='utf-8') as f:
        for req in requests:
            f.write(json.dumps(req, ensure_ascii=False) + '\n')

    # 上传文件
    with open(temp_file, 'rb') as f:
        files = {"file": f}
        data = {"purpose": "batch"}

        response = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers={"Authorization": f"Bearer {API_KEY}"},
            files=files,
            data=data
        )
        response.raise_for_status()
        file_info = response.json()
        print(f"文件上传成功: {file_info['id']}")

    # 删除临时文件
    temp_file.unlink()
    return file_info["id"]

# 创建 batch 任务
def create_batch_task(input_file_id):
    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分析任务",
            "model": "glm-5.1",
            "total_requests": len(read_comments())
        }
    }

    response = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json=payload
    )
    response.raise_for_status()
    batch_info = response.json()
    return batch_info

def main():
    try:
        # 1. 读取评论
        comments = read_comments()
        print(f"读取到 {len(comments)} 条评论")

        # 2. 构造 batch 请求
        requests = create_batch_requests(comments)
        print(f"构造了 {len(requests)} 个请求")

        # 3. 上传文件
        input_file_id = upload_batch_file(requests)
        print(f"文件上传完成，ID: {input_file_id}")

        # 4. 创建 batch 任务
        batch_info = create_batch_task(input_file_id)
        batch_id = batch_info["id"]
        print(f"Batch 任务创建成功!")
        print(f"任务 ID: {batch_id}")
        print(f"任务状态: {batch_info['status']}")

        # 打印任务 ID 到 stdout（符合要求）
        print(batch_id)

    except requests.exceptions.RequestException as e:
        print(f"API 请求错误: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应内容: {e.response.text}")
        raise
    except Exception as e:
        print(f"其他错误: {e}")
        raise

if __name__ == "__main__":
    main()