#!/usr/bin/env python3
"""
情感分析批量处理脚本
使用智谱AI Batch API对comments.txt中的评论进行情感分类
"""

import os
import json
import requests
from pathlib import Path

def read_comments(comments_file):
    """读取评论文件"""
    with open(comments_file, 'r', encoding='utf-8') as f:
        comments = [line.strip() for line in f if line.strip()]
    return comments

def create_jsonl_requests(comments, model="glm-4-plus"):
    """创建Batch API所需的JSONL格式请求文件"""
    lines = []

    for i, comment in enumerate(comments):
        custom_id = f"sentiment-{i+1:04d}"  # 确保custom_id至少6个字符

        request = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个专业的情感分类助手。请对用户评论进行情感分类，只返回一个情感标签：正面、负面或中性。评论可能包含对产品质量、客服态度、物流速度、价格等方面的评价。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低随机性，提高一致性
                "max_tokens": 10    # 只要一个词，不需要太多token
            }
        }
        lines.append(json.dumps(request, ensure_ascii=False))

    return "\n".join(lines)

def upload_batch_file(jsonl_content, headers):
    """上传JSONL文件到Batch API"""
    files = {
        "file": ("batch_requests.jsonl", jsonl_content, "application/jsonl")
    }
    data = {"purpose": "batch"}

    response = requests.post(
        "https://open.bigmodel.cn/api/paas/v4/files",
        headers=headers,
        files=files,
        data=data
    )
    response.raise_for_status()
    return response.json()

def create_batch_task(input_file_id, headers):
    """创建Batch任务"""
    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分析",
            "total_requests": len(open("outputs/batch_requests.jsonl").readlines())
        }
    }

    response = requests.post(
        "https://open.bigmodel.cn/api/paas/v4/batches",
        headers={**headers, "Content-Type": "application/json"},
        json=payload
    )
    response.raise_for_status()
    return response.json()

def main():
    # 检查API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    headers = {"Authorization": f"Bearer {api_key}"}

    # 读取评论
    comments_file = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/v1/batch-best-model/run-2/comments.txt"
    try:
        comments = read_comments(comments_file)
        print(f"成功读取 {len(comments)} 条评论")
    except Exception as e:
        print(f"读取评论文件失败: {e}")
        return

    # 确保输出目录存在
    os.makedirs("outputs", exist_ok=True)

    # 创建JSONL请求
    jsonl_content = create_jsonl_requests(comments, model="glm-4-plus")
    jsonl_file = "outputs/batch_requests.jsonl"

    with open(jsonl_file, "w", encoding="utf-8") as f:
        f.write(jsonl_content)
    print(f"已生成JSONL请求文件: {jsonl_file}")

    # 上传文件
    try:
        upload_result = upload_batch_file(jsonl_content, headers)
        input_file_id = upload_result["id"]
        print(f"文件上传成功，文件ID: {input_file_id}")
    except Exception as e:
        print(f"文件上传失败: {e}")
        return

    # 创建Batch任务
    try:
        batch_result = create_batch_task(input_file_id, headers)
        batch_id = batch_result["id"]
        status = batch_result["status"]
        print(f"Batch任务创建成功！")
        print(f"任务ID: {batch_id}")
        print(f"初始状态: {status}")
        print("\n任务已提交，请稍后使用任务ID查询结果。")
    except Exception as e:
        print(f"创建Batch任务失败: {e}")
        return

if __name__ == "__main__":
    main()