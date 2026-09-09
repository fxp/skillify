#!/usr/bin/env python3
"""
情感分类 Batch 脚本
使用智谱 BigModel Batch API 对评论进行情感分类（正面/负面/中性）
"""

import os
import json
import requests
from pathlib import Path

# 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# Batch API 支持的最佳模型
MODEL = "glm-4-plus"

# 读取评论文件
def read_comments():
    comments_file = Path(__file__).parent.parent.parent.parent / "comments.txt"
    with open(comments_file, "r", encoding="utf-8") as f:
        comments = [line.strip() for line in f.readlines() if line.strip()]
    return comments

# 创建 Batch 请求的 JSONL 文件内容
def create_batch_requests(comments):
    requests = []
    for i, comment in enumerate(comments, 1):
        custom_id = f"request-{i:03d}"  # custom_id 最少需要6个字符

        # 构建请求体
        request_body = {
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的情感分析助手。请对用户评论进行情感分类，只返回一个标签：正面、负面或中性。评论可能涉及产品、服务、物流等多个方面。"
                },
                {
                    "role": "user",
                    "content": f"请对以下评论进行情感分类：{comment}"
                }
            ],
            "temperature": 0.1,  # 降低随机性，提高一致性
            "max_tokens": 50  # 限制输出长度
        }

        # 构建 Batch 请求行
        batch_request = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": request_body
        }

        requests.append(batch_request)

    return requests

# 上传 Batch 文件
def upload_batch_file(jsonl_content):
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    files = {
        "file": ("batch_requests.jsonl", jsonl_content, "application/jsonl")
    }
    data = {
        "purpose": "batch"
    }

    response = requests.post(
        f"{BASE_URL}/paas/v4/files",
        headers=headers,
        files=files,
        data=data
    )

    response.raise_for_status()
    file_info = response.json()
    return file_info["id"]

# 创建 Batch 任务
def create_batch_task(input_file_id):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分类任务",
            "model": MODEL,
            "total_requests": len(read_comments())
        }
    }

    response = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers=headers,
        json=payload
    )

    response.raise_for_status()
    batch_info = response.json()
    return batch_info

def main():
    print("开始创建 Batch 情感分类任务...")

    # 1. 读取评论
    print("1. 读取评论文件...")
    comments = read_comments()
    print(f"   读取到 {len(comments)} 条评论")

    # 2. 创建 Batch 请求
    print("2. 创建 Batch 请求...")
    batch_requests = create_batch_requests(comments)

    # 转换为 JSONL 格式
    jsonl_content = "\n".join([json.dumps(req, ensure_ascii=False) for req in batch_requests])

    # 3. 上传文件
    print("3. 上传 Batch 文件...")
    input_file_id = upload_batch_file(jsonl_content)
    print(f"   文件上传成功，ID: {input_file_id}")

    # 4. 创建 Batch 任务
    print("4. 创建 Batch 任务...")
    batch_info = create_batch_task(input_file_id)
    batch_id = batch_info["id"]

    print(f"\n✅ Batch 任务创建成功！")
    print(f"📋 任务 ID: {batch_id}")
    print(f"📊 任务状态: {batch_info['status']}")
    print(f"📝 请求数量: {batch_info['request_counts']['total']}")
    print(f"\n💡 提示：任务预计在 24 小时内完成，请使用任务 ID 查询状态")

if __name__ == "__main__":
    main()