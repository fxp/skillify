import os
import json
import requests
from pathlib import Path

# 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

# 批量 API 支持的最好模型（从 Batch 白名单中选择质量最优的）
BATCH_MODEL = "glm-5.1"

# 读取评论文件
def read_comments():
    comments_file = Path(__file__).parent.parent.parent / "weak-exec" / "comments.txt"
    with open(comments_file, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

# 构造 JSONL 请求文件
def create_jsonl_input(comments):
    jsonl_lines = []
    for i, comment in enumerate(comments, 1):
        # custom_id 必须至少6个字符
        custom_id = f"request-{i:03d}"

        line = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": BATCH_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个情感分析专家。请对用户评论进行情感分类，只返回一个词：正面、负面或中性。分类标准：正面表达满意、推荐、超出预期等；负面表达不满、投诉、质量问题等；其他情况归为中性。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低温度以获得更一致的输出
                "max_tokens": 10    # 只需要一个词，限制输出长度
            }
        }
        jsonl_lines.append(json.dumps(line, ensure_ascii=False))

    return "\n".join(jsonl_lines)

# 上传请求文件
def upload_input_file(jsonl_content):
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    files = {
        "file": ("batch_requests.jsonl", jsonl_content.encode('utf-8'), "application/jsonl")
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
    print(f"文件上传成功: {file_info['id']}")
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
            "description": "评论情感分析批量任务",
            "total_comments": len(read_comments())
        }
    }

    response = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers=headers,
        json=payload
    )
    response.raise_for_status()

    batch_info = response.json()
    print(f"Batch 任务创建成功")
    print(f"任务ID: {batch_info['id']}")
    print(f"任务状态: {batch_info['status']}")
    print(f"请使用任务ID查询进度: {batch_info['id']}")

    return batch_info["id"]

def main():
    # 检查 API Key
    if not API_KEY:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY")
        return 1

    try:
        # 1. 读取评论
        print("正在读取评论文件...")
        comments = read_comments()
        print(f"读取到 {len(comments)} 条评论")

        # 2. 构造 JSONL 文件内容
        print("正在构造请求文件...")
        jsonl_content = create_jsonl_input(comments)

        # 3. 上传文件
        print("正在上传文件...")
        input_file_id = upload_input_file(jsonl_content)

        # 4. 创建 Batch 任务
        print("正在创建 Batch 任务...")
        batch_id = create_batch_task(input_file_id)

        # 输出任务 ID 到 stdout
        print(f"\nBatch 任务 ID: {batch_id}")

        return 0

    except requests.exceptions.RequestException as e:
        print(f"请求错误: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应内容: {e.response.text}")
        return 1
    except Exception as e:
        print(f"错误: {e}")
        return 1

if __name__ == "__main__":
    exit(main())