#!/usr/bin/env python3
"""
情感分类 Batch 处理脚本
使用智谱 Batch API 对 comments.txt 中的评论进行情感分类
"""

import os
import json
import io
import requests
from typing import List

def read_comments(file_path: str) -> List[str]:
    """读取评论文件，每行一条评论"""
    comments = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:  # 忽空行
                comments.append(line)
    return comments

def create_jsonl_file(comments: List[str]) -> str:
    """创建 Batch API 所需的 jsonl 文件内容"""
    lines = []
    for i, comment in enumerate(comments):
        # custom_id 最少6个字符，使用 request-xxxxx 格式
        custom_id = f"req-{i+1:05d}"

        # 构建请求体，进行情感分类
        line = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                # 使用 Batch API 白名单内的最强模型 glm-4-plus
                "model": "glm-4-plus",
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个情感分析专家。请对用户评论进行情感分类，只返回一个 JSON 对象，包含 sentiment（情感：正面/负面/中性）和 confidence（置信度：0-1 的数字）。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低随机性，确保结果一致性
                "max_tokens": 100
            }
        }
        lines.append(json.dumps(line, ensure_ascii=False))

    return "\n".join(lines)

def upload_batch_file(jsonl_content: str, api_key: str) -> str:
    """上传 jsonl 文件到智谱平台"""
    base_url = "https://open.bigmodel.cn/api"
    headers = {"Authorization": f"Bearer {api_key}"}

    # 创建文件对象
    file_obj = io.BytesIO(jsonl_content.encode('utf-8'))

    # 上传文件，purpose 必须为 "batch"
    files = {"file": ("batch_requests.jsonl", file_obj, "application/json")}
    data = {"purpose": "batch"}

    response = requests.post(
        f"{base_url}/paas/v4/files",
        headers=headers,
        files=files,
        data=data
    )
    response.raise_for_status()

    file_info = response.json()
    print(f"文件上传成功: {file_info['id']}")
    return file_info["id"]

def create_batch_task(file_id: str, api_key: str) -> str:
    """创建 Batch 任务"""
    base_url = "https://open.bigmodel.cn/api"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "input_file_id": file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "评论情感分析任务",
            "model": "glm-4-plus",
            "total_requests": len(open("comments.txt").readlines())
        }
    }

    response = requests.post(
        f"{base_url}/paas/v4/batches",
        headers=headers,
        json=payload
    )
    response.raise_for_status()

    batch_info = response.json()
    print(f"Batch 任务创建成功！")
    print(f"Batch ID: {batch_info['id']}")
    print(f"任务状态: {batch_info['status']}")

    return batch_info["id"]

def main():
    # 配置
    comments_file = "comments.txt"
    api_key = os.environ.get("ZHIPUAI_API_KEY")

    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    print("开始处理情感分类任务...")

    # 1. 读取评论
    print(f"正在读取评论文件: {comments_file}")
    comments = read_comments(comments_file)
    print(f"读取到 {len(comments)} 条评论")

    # 2. 创建 JSONL 文件
    print("正在创建 JSONL 批处理文件...")
    jsonl_content = create_jsonl_file(comments)
    print(f"JSONL 文件大小: {len(jsonl_content)} 字符")

    # 3. 上传文件
    print("正在上传文件到智谱平台...")
    file_id = upload_batch_file(jsonl_content, api_key)

    # 4. 创建 Batch 任务
    print("正在创建 Batch 任务...")
    batch_id = create_batch_task(file_id, api_key)

    print("\n任务创建完成！")
    print("=" * 50)
    print(f"请使用 Batch ID 跮询任务状态: {batch_id}")
    print("任务预计在 24 小时内完成")
    print("完成后可以通过 API 下载结果文件")

if __name__ == "__main__":
    main()