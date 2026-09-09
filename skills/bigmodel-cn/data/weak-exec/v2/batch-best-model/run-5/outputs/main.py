#!/usr/bin/env python3
import os
import json
import requests
import time

def read_comments():
    """读取评论文件"""
    with open("comments.txt", "r", encoding="utf-8") as f:
        comments = [line.strip() for line in f if line.strip()]
    return comments

def create_jsonl_file(comments):
    """构造 .jsonl 请求文件"""
    jsonl_lines = []
    for i, comment in enumerate(comments, 1):
        line = {
            "custom_id": f"request-{i:03d}",  # custom_id 最少需要6个字符
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-5.1",  # Batch API 支持的最佳模型
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个情感分析专家。请对用户评论进行情感分类，只返回一个分类结果：正面、负面或中性。评论可能涉及产品质量、物流速度、客服态度、价格、包装等方面。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低随机性，提高一致性
                "max_tokens": 10  # 只要分类结果，不需要长文本
            }
        }
        jsonl_lines.append(json.dumps(line, ensure_ascii=False))
    return "\n".join(jsonl_lines)

def upload_file(jsonl_content):
    """上传文件到 Batch API"""
    files = {"file": ("batch_requests.jsonl", jsonl_content.encode("utf-8"), "application/json")}
    data = {"purpose": "batch"}

    url = "https://open.bigmodel.cn/api/paas/v4/files"
    headers = {
        "Authorization": f"Bearer {os.environ['ZHIPUAI_API_KEY']}"
    }

    response = requests.post(url, headers=headers, files=files, data=data)
    response.raise_for_status()

    file_info = response.json()
    print(f"文件上传成功，文件ID: {file_info['id']}")
    return file_info["id"]

def create_batch(input_file_id):
    """创建 Batch 任务"""
    url = "https://open.bigmodel.cn/api/paas/v4/batches"
    headers = {
        "Authorization": f"Bearer {os.environ['ZHIPUAI_API_KEY']}",
        "Content-Type": "application/json"
    }

    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分析",
            "model": "glm-5.1",
            "task_type": "sentiment_analysis"
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    batch_info = response.json()
    print(f"Batch 任务创建成功")
    print(f"任务ID: {batch_info['id']}")
    print(f"任务状态: {batch_info['status']}")
    print(f"请使用以下ID查看任务状态: {batch_info['id']}")

    return batch_info["id"]

def main():
    """主函数"""
    # 检查 API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    try:
        # 1. 读取评论
        print("正在读取评论文件...")
        comments = read_comments()
        print(f"读取到 {len(comments)} 条评论")

        # 2. 创建 JSONL 文件内容
        print("正在构造请求文件...")
        jsonl_content = create_jsonl_file(comments)

        # 3. 上传文件
        print("正在上传文件...")
        input_file_id = upload_file(jsonl_content)

        # 4. 创建 Batch 任务
        print("正在创建 Batch 任务...")
        batch_id = create_batch(input_file_id)

        # 输出 batch 任务 ID
        print("\n" + "="*50)
        print(f"BATCH 任务 ID: {batch_id}")
        print("="*50)

    except requests.exceptions.RequestException as e:
        print(f"API 请求失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应内容: {e.response.text}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()