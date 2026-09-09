#!/usr/bin/env python3
import os
import json
import requests
import io

# API配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def read_comments():
    """读取评论文件"""
    comments_file = "../run-4/comments.txt"
    with open(comments_file, 'r', encoding='utf-8') as f:
        comments = [line.strip() for line in f if line.strip()]
    return comments

def create_jsonl_batch_input(comments):
    """构造Batch API所需的JSONL格式输入"""
    lines = []
    for i, comment in enumerate(comments):
        # custom_id最少需要6个字符，使用格式化的ID
        custom_id = f"req-{i+1:05d}"

        line = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-5.1",  # Batch白名单内的最强模型
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个情感分类器，请对用户评论进行情感分类。请以JSON格式返回，包含sentiment字段（值为'正面'、'负面'或'中性'）和score字段（0-1之间的数字，1表示最积极）。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 200
            }
        }
        lines.append(json.dumps(line, ensure_ascii=False))

    return "\n".join(lines)

def upload_batch_file(jsonl_content):
    """上传Batch文件"""
    buffer = io.BytesIO(jsonl_content.encode('utf-8'))

    files = {"file": ("batch_requests.jsonl", buffer, "application/json")}
    data = {"purpose": "batch"}

    response = requests.post(
        f"{BASE_URL}/files",
        headers=HEADERS,
        files=files,
        data=data
    )

    if response.status_code != 200:
        raise Exception(f"文件上传失败: {response.text}")

    result = response.json()
    if "id" not in result:
        raise Exception(f"上传响应格式错误: {result}")

    print(f"文件上传成功，file_id: {result['id']}")
    return result["id"]

def create_batch_task(input_file_id):
    """创建Batch任务"""
    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分析",
            "model": "glm-5.1",
            "created_by": "batch_sentiment_analysis"
        }
    }

    response = requests.post(
        f"{BASE_URL}/batches",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=payload
    )

    if response.status_code != 200:
        raise Exception(f"创建Batch任务失败: {response.text}")

    result = response.json()
    if "id" not in result:
        raise Exception(f"Batch任务创建响应格式错误: {result}")

    print(f"Batch任务创建成功！")
    print(f"Batch ID: {result['id']}")
    print(f"任务状态: {result.get('status', 'unknown')}")
    print(f"请使用以下ID查询任务状态: {result['id']}")

    return result["id"]

def main():
    """主函数"""
    try:
        print("开始执行情感分析Batch任务...")

        # 1. 读取评论
        print("1. 读取评论文件...")
        comments = read_comments()
        print(f"   读取到 {len(comments)} 条评论")

        # 2. 构造JSONL输入
        print("2. 构造Batch请求JSONL...")
        jsonl_content = create_jsonl_batch_input(comments)

        # 3. 上传文件
        print("3. 上传Batch文件...")
        input_file_id = upload_batch_file(jsonl_content)

        # 4. 创建Batch任务
        print("4. 创建Batch任务...")
        batch_id = create_batch_task(input_file_id)

        print("\n任务执行完成！")
        print(f"请保存此Batch ID用于后续查询: {batch_id}")

    except Exception as e:
        print(f"错误: {str(e)}")
        raise

if __name__ == "__main__":
    main()