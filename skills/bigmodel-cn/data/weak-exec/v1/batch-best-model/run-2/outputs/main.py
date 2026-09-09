#!/usr/bin/env python3
"""
使用智谱 BigModel Batch API 进行情感分类
"""

import os
import json
import requests
from pathlib import Path

def read_comments():
    """读取评论文件"""
    comments_file = Path(__file__).parent / "comments.txt"
    with open(comments_file, 'r', encoding='utf-8') as f:
        comments = [line.strip() for line in f if line.strip()]
    return comments

def create_jsonl_file(comments):
    """创建 JSONL 格式的请求文件"""
    requests_data = []

    for i, comment in enumerate(comments, 1):
        custom_id = f"sentiment-{i:03d}"  # custom_id 最短 6 个字符

        # 构造请求体
        request_body = {
            "model": "glm-5.1",  # Batch API 支持的最佳模型
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个情感分析专家。请将用户评论分为三类：正面、负面、中性。请只返回一个分类标签，不要解释。"
                },
                {
                    "role": "user",
                    "content": f"请对以下评论进行情感分类：{comment}"
                }
            ],
            "temperature": 0.1,  # 降低随机性，提高分类一致性
            "max_tokens": 10  # 只要分类结果，不需要长文本
        }

        requests_data.append({
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": request_body
        })

    # 写入 JSONL 文件
    jsonl_file = Path(__file__).parent / "batch_requests.jsonl"
    with open(jsonl_file, 'w', encoding='utf-8') as f:
        for request in requests_data:
            f.write(json.dumps(request, ensure_ascii=False) + '\n')

    return jsonl_file

def upload_file(jsonl_file):
    """上传文件到 bigmodel API"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/files"

    with open(jsonl_file, 'rb') as f:
        files = {"file": f}
        data = {"purpose": "batch"}
        headers = {"Authorization": f"Bearer {api_key}"}

        response = requests.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()

    return response.json()

def create_batch(input_file_id):
    """创建 Batch 任务"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/batches"

    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分析",
            "model": "glm-5.1"
        }
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    return response.json()

def main():
    try:
        # 1. 读取评论
        print("正在读取评论文件...")
        comments = read_comments()
        print(f"读取到 {len(comments)} 条评论")

        # 2. 创建 JSONL 请求文件
        print("正在创建 JSONL 请求文件...")
        jsonl_file = create_jsonl_file(comments)
        print(f"已创建请求文件: {jsonl_file}")

        # 3. 上传文件
        print("正在上传文件...")
        upload_result = upload_file(jsonl_file)
        input_file_id = upload_result["id"]
        print(f"文件上传成功，文件ID: {input_file_id}")

        # 4. 创建 Batch 任务
        print("正在创建 Batch 任务...")
        batch_result = create_batch(input_file_id)
        batch_id = batch_result["id"]
        print(f"Batch 任务创建成功，任务ID: {batch_id}")

        # 输出结果
        print("\n" + "="*50)
        print("任务信息：")
        print(f"Batch ID: {batch_id}")
        print(f"任务状态: {batch_result['status']}")
        print(f"请使用此 Batch ID 查询任务状态")
        print("="*50)

    except Exception as e:
        print(f"错误: {str(e)}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())