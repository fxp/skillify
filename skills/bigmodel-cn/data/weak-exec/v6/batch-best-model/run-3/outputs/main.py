#!/usr/bin/env python3
"""
使用智谱 BigModel Batch API 对评论进行情感分类
"""

import os
import json
import io
import requests
from typing import List, Dict

# 配置
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
COMMENTS_FILE = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/v6/batch-best-model/run-2/comments.txt"

# Batch API 支持的最好模型（根据白名单）
BATCH_MODEL = "glm-4-plus"

def read_comments() -> List[str]:
    """读取评论文件"""
    with open(COMMENTS_FILE, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def create_batch_requests(comments: List[str]) -> List[Dict]:
    """创建 Batch API 请求列表"""
    requests = []

    for i, comment in enumerate(comments, 1):
        # custom_id 最少需要6个字符
        custom_id = f"req-{i:05d}"

        request = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": BATCH_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个情感分析专家。请对用户评论进行情感分类，只输出一个JSON对象，包含sentiment字段（值为\"正面\"、\"负面\"或\"中性\"）和confidence字段（0-1之间的数字表示置信度）。不要输出其他任何文字。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低随机性，提高一致性
                "max_tokens": 100
            }
        }
        requests.append(request)

    return requests

def upload_batch_file(requests: List[Dict]) -> str:
    """上传 Batch 文件"""
    # 转换为 JSONL 格式
    jsonl_content = "\n".join(
        json.dumps(req, ensure_ascii=False) for req in requests
    )

    # 创建文件对象
    file_buffer = io.BytesIO(jsonl_content.encode('utf-8'))

    # 上传文件
    response = requests.post(
        f"{BASE_URL}/files",
        headers={"Authorization": f"Bearer {API_KEY}"},
        files={"file": ("batch_requests.jsonl", file_buffer, "application/json")},
        data={"purpose": "batch"}
    )

    response.raise_for_status()
    file_info = response.json()

    if "id" not in file_info:
        raise RuntimeError(f"文件上传失败：{file_info}")

    print(f"文件上传成功，文件ID：{file_info['id']}")
    return file_info["id"]

def create_batch_job(input_file_id: str, total_requests: int) -> str:
    """创建 Batch 任务"""
    response = requests.post(
        f"{BASE_URL}/batches",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "input_file_id": input_file_id,
            "endpoint": "/v4/chat/completions",
            "auto_delete_input_file": True,
            "metadata": {
                "description": "评论情感分析任务",
                "total_requests": total_requests
            }
        }
    )

    response.raise_for_status()
    batch_info = response.json()

    if "id" not in batch_info:
        raise RuntimeError(f"创建 Batch 任务失败：{batch_info}")

    return batch_info["id"]

def main():
    """主函数"""
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 读取评论
    print("正在读取评论...")
    comments = read_comments()
    print(f"读取到 {len(comments)} 条评论")

    # 创建 Batch 请求
    print("正在创建 Batch 请求...")
    requests_list = create_batch_requests(comments)
    print(f"创建了 {len(requests_list)} 个请求")

    # 上传文件
    print("正在上传 Batch 文件...")
    input_file_id = upload_batch_file(requests_list)

    # 创建 Batch 任务
    print("正在创建 Batch 任务...")
    batch_id = create_batch_job(input_file_id, len(requests_list))

    # 输出结果
    print(f"\n✅ Batch 任务创建成功！")
    print(f"📋 Batch ID: {batch_id}")
    print(f"💡 请稍后通过查询任务状态来获取结果")

if __name__ == "__main__":
    main()