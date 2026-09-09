#!/usr/bin/env python3
import os
import requests
import json
import time
from datetime import datetime

# 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# 读取评论数据
def read_comments():
    comments_file = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/comments.txt"
    with open(comments_file, "r", encoding="utf-8") as f:
        comments = [line.strip() for line in f if line.strip()]
    return comments

# 创建 JSONL 请求文件
def create_jsonl_requests(comments):
    jsonl_lines = []
    for i, comment in enumerate(comments, 1):
        # 使用 request-001 格式的 custom_id，确保至少6个字符
        custom_id = f"request-{i:03d}"

        request_data = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-4-plus",  # Batch 白名单中最好的文本模型
                "messages": [
                    {
                        "role": "system",
                        "content": """你是一个情感分类专家。请对用户评论进行情感分类，只返回一个标签：
- 正面：表达满意、推荐、超出预期等积极情绪
- 负面：表达不满、失望、投诉等消极情绪
- 中性：客观描述、中性评价，无明显情感倾向

请直接返回"正面"、"负面"或"中性"，不要解释。"""
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低随机性，提高分类一致性
                "max_tokens": 10  # 只需要返回分类标签，限制输出长度
            }
        }
        jsonl_lines.append(json.dumps(request_data, ensure_ascii=False))
    return "\n".join(jsonl_lines)

# 上传 Batch 文件
def upload_batch_file(jsonl_content):
    files = {
        "file": ("batch_requests.jsonl", jsonl_content.encode("utf-8"), "application/jsonl")
    }
    data = {
        "purpose": "batch"
    }

    response = requests.post(
        f"{BASE_URL}/paas/v4/files",
        headers={"Authorization": f"Bearer {API_KEY}"},
        files=files,
        data=data
    )

    if response.status_code != 200:
        raise Exception(f"文件上传失败: {response.text}")

    file_info = response.json()
    print(f"✅ 文件上传成功，ID: {file_info['id']}")
    return file_info["id"]

# 创建 Batch 任务
def create_batch_task(file_id):
    payload = {
        "input_file_id": file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分析任务",
            "created_at": datetime.now().isoformat(),
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

    if response.status_code != 200:
        raise Exception(f"Batch 任务创建失败: {response.text}")

    batch_info = response.json()
    print(f"✅ Batch 任务创建成功")
    return batch_info

def main():
    print("🚀 开始创建 Batch 情感分析任务...")

    # 1. 读取评论
    comments = read_comments()
    print(f"📝 读取到 {len(comments)} 条评论")

    # 2. 创建 JSONL 请求文件
    print("📄 正在构造 JSONL 请求文件...")
    jsonl_content = create_jsonl_requests(comments)
    print(f"📄 已构造 {len(comments)} 条请求")

    # 3. 上传文件
    print("📤 正在上传文件...")
    file_id = upload_batch_file(jsonl_content)

    # 4. 创建 Batch 任务
    print("🔄 正在创建 Batch 任务...")
    batch_info = create_batch_task(file_id)

    # 5. 输出结果
    batch_id = batch_info["id"]
    print("\n" + "="*50)
    print("🎉 Batch 任务创建成功！")
    print(f"📋 任务 ID: {batch_id}")
    print(f"📊 任务状态: {batch_info['status']}")
    print(f"📝 请求数量: {batch_info['request_counts']['total']}")
    print("="*50)
    print("\n💡 提示：")
    print("- 任务预计 24 小时内完成")
    print("- 可以使用任务 ID 查询任务状态")
    print("- 完成后可以通过 output_file_id 下载结果")
    print("\n🔍 查询任务状态命令：")
    print(f"curl -H 'Authorization: Bearer {API_KEY}' '{BASE_URL}/paas/v4/batches/{batch_id}'")

if __name__ == "__main__":
    main()