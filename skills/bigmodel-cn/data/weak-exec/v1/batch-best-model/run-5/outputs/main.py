#!/usr/bin/env python3
import os
import requests
import json
import time

# 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def read_comments(file_path):
    """读取评论文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def create_jsonl_file(comments):
    """创建 Batch API 请求的 JSONL 文件"""
    jsonl_data = []

    # 使用 Batch 支持的最好的模型：glm-4v-plus-0111（在 Batch 白名单中，是较新的模型，情感分类能力更强）
    model = "glm-4v-plus-0111"

    system_prompt = """你是一个专业的情感分类助手。请将用户评论分类为以下三种情感之一：
- 正面：表达满意、赞扬、推荐等积极情感
- 负面：表达不满、批评、抱怨等消极情感
- 中性：客观描述、中性表达或无法确定明确情感

请只返回一个分类标签：正面/负面/中性，不要解释。"""

    for i, comment in enumerate(comments, 1):
        custom_id = f"request-{i:03d}"  # custom_id 至少6个字符

        jsonl_data.append({
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请对以下评论进行情感分类：{comment}"}
                ],
                "temperature": 0.1,  # 降低随机性，提高分类一致性
                "max_tokens": 10  # 只需要返回分类结果
            }
        })

    # 写入 JSONL 文件
    jsonl_file_path = "batch_requests.jsonl"
    with open(jsonl_file_path, 'w', encoding='utf-8') as f:
        for item in jsonl_data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

    return jsonl_file_path

def upload_batch_file(file_path):
    """上传文件到 Batch API"""
    print("上传 Batch 文件...")

    with open(file_path, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=HEADERS,
            files={"file": f},
            data={"purpose": "batch"}
        )
        response.raise_for_status()

    file_info = response.json()
    print(f"文件上传成功，文件ID: {file_info['id']}")
    return file_info['id']

def create_batch_job(input_file_id):
    """创建 Batch 任务"""
    print("创建 Batch 任务...")

    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分类任务",
            "model": "glm-5v-turbo",
            "total_requests": len(open('comments.txt', 'r', encoding='utf-8').readlines())
        }
    }

    response = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=payload
    )
    response.raise_for_status()

    batch_info = response.json()
    print(f"Batch 任务创建成功！")
    print(f"任务ID: {batch_info['id']}")
    print(f"任务状态: {batch_info['status']}")
    print(f"请记录任务ID，可用于后续查询进度和结果")

    return batch_info['id']

def main():
    """主函数"""
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    try:
        # 1. 读取评论
        print("读取评论文件...")
        comments = read_comments("comments.txt")
        print(f"读取到 {len(comments)} 条评论")

        # 2. 创建 JSONL 文件
        print("创建 Batch 请求文件...")
        jsonl_file_path = create_jsonl_file(comments)
        print(f"JSONL 文件已创建: {jsonl_file_path}")

        # 3. 上传文件
        input_file_id = upload_batch_file(jsonl_file_path)

        # 4. 创建 Batch 任务
        batch_id = create_batch_job(input_file_id)

        # 5. 输出结果
        print("\n" + "="*50)
        print("任务创建完成！")
        print(f"Batch ID: {batch_id}")
        print("="*50)

        # 删除临时 JSONL 文件
        os.remove(jsonl_file_path)
        print(f"临时文件 {jsonl_file_path} 已删除")

    except requests.exceptions.RequestException as e:
        print(f"API 请求错误: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应内容: {e.response.text}")
    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    main()