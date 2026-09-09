#!/usr/bin/env python3
"""
用户评论情感分类 - 使用智谱AI Batch API
将评论分类为正面/负面/中性，使用Batch API节省50%费用
"""

import os
import json
import requests
from pathlib import Path

def read_comments(file_path):
    """读取评论文件，每行一条评论"""
    with open(file_path, 'r', encoding='utf-8') as f:
        comments = [line.strip() for line in f if line.strip()]
    return comments

def create_jsonl_batch_file(comments, output_path):
    """构造Batch API需要的.jsonl请求文件"""
    requests_data = []

    for i, comment in enumerate(comments):
        # custom_id必须至少6个字符
        custom_id = f"req-{i+1:04d}"

        request_data = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-5.1",  # Batch白名单中最好的模型
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个专业的情感分类器。请将用户评论分为三类：正面、负面、中性。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类，只返回一个词：正面、负面或中性。\n评论：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低随机性，提高分类一致性
                "max_tokens": 10  # 只要分类结果，不需要长文本
            }
        }
        requests_data.append(request_data)

    # 写入.jsonl文件
    with open(output_path, 'w', encoding='utf-8') as f:
        for req in requests_data:
            f.write(json.dumps(req, ensure_ascii=False) + '\n')

    return requests_data

def upload_batch_file(file_path, api_key):
    """上传Batch请求文件到智谱AI"""
    url = "https://open.bigmodel.cn/api/paas/v4/files"

    with open(file_path, 'rb') as f:
        files = {"file": f}
        data = {"purpose": "batch"}
        headers = {"Authorization": f"Bearer {api_key}"}

        response = requests.post(url, headers=headers, files=files, data=data)

    if response.status_code != 200:
        raise Exception(f"文件上传失败: {response.text}")

    return response.json()

def create_batch_task(input_file_id, api_key):
    """创建Batch任务"""
    url = "https://open.bigmodel.cn/api/paas/v4/batches"

    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分类",
            "model": "glm-5.1",
            "task_type": "sentiment_analysis"
        }
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        raise Exception(f"Batch任务创建失败: {response.text}")

    return response.json()

def main():
    # 配置
    comments_file = "comments.txt"
    jsonl_file = "batch_requests.jsonl"
    api_key = os.environ.get("ZHIPUAI_API_KEY")

    # 检查API Key
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 检查评论文件是否存在
    if not Path(comments_file).exists():
        print(f"错误：找不到评论文件 {comments_file}")
        return

    try:
        # 1. 读取评论
        print("正在读取评论文件...")
        comments = read_comments(comments_file)
        print(f"共读取 {len(comments)} 条评论")

        # 2. 创建JSONL请求文件
        print("正在构造Batch请求文件...")
        create_jsonl_batch_file(comments, jsonl_file)
        print(f"已创建请求文件: {jsonl_file}")

        # 3. 上传文件
        print("正在上传文件到智谱AI...")
        upload_result = upload_batch_file(jsonl_file, api_key)
        input_file_id = upload_result["id"]
        print(f"文件上传成功，文件ID: {input_file_id}")

        # 4. 创建Batch任务
        print("正在创建Batch任务...")
        batch_result = create_batch_task(input_file_id, api_key)
        batch_id = batch_result["id"]
        print(f"Batch任务创建成功！")
        print(f"任务ID: {batch_id}")
        print(f"任务状态: {batch_result['status']}")
        print(f"请保存任务ID，稍后可以通过任务ID查询结果")

        # 输出到stdout
        print(batch_id, flush=True)

    except Exception as e:
        print(f"错误: {str(e)}")

if __name__ == "__main__":
    main()