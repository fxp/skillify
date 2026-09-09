import os
import json
import requests

# API 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def read_comments():
    """读取评论文件"""
    comments = []
    with open("../comments.txt", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:  # 跳过空行
                comments.append(line)
    return comments

def create_jsonl_file(comments):
    """创建 JSONL 请求文件"""
    requests_data = []

    # 使用最好的 Batch 模型（白名单中最好的）
    model = "glm-5.1"

    for i, comment in enumerate(comments, 1):
        # custom_id 至少需要6个字符
        custom_id = f"req_{i:04d}"

        request_data = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个专业的情感分析专家。请对用户评论进行情感分类，只返回一个标签：正面、负面或中性。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低随机性，提高一致性
                "max_tokens": 50  # 只需要返回分类结果，不需要太多token
            }
        }
        requests_data.append(request_data)

    # 写入 JSONL 文件
    jsonl_path = "batch_requests.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for request in requests_data:
            f.write(json.dumps(request, ensure_ascii=False) + "\n")

    return jsonl_path

def upload_file(jsonl_path):
    """上传 JSONL 文件到服务器"""
    with open(jsonl_path, "rb") as f:
        files = {"file": f}
        data = {"purpose": "batch"}

        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=HEADERS,
            files=files,
            data=data
        )
        resp.raise_for_status()

    file_info = resp.json()
    print(f"文件上传成功: {file_info['id']}")
    return file_info["id"]

def create_batch(input_file_id):
    """创建 Batch 任务"""
    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分析",
            "model": "glm-5.1"
        }
    }

    resp = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=payload
    )
    resp.raise_for_status()

    batch_info = resp.json()
    print(f"Batch 任务创建成功!")
    print(f"任务ID: {batch_info['id']}")
    print(f"任务状态: {batch_info['status']}")
    print(f"请记录此ID用于后续查询结果: {batch_info['id']}")

    return batch_info["id"]

def main():
    """主函数"""
    print("开始处理用户评论情感分析...")

    # 检查 API Key
    if not API_KEY:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 1. 读取评论
    print("1. 读取评论文件...")
    comments = read_comments()
    print(f"共读取 {len(comments)} 条评论")

    # 2. 创建 JSONL 文件
    print("\n2. 创建 JSONL 请求文件...")
    jsonl_path = create_jsonl_file(comments)
    print(f"JSONL 文件已创建: {jsonl_path}")

    # 3. 上传文件
    print("\n3. 上传文件到服务器...")
    input_file_id = upload_file(jsonl_path)

    # 4. 创建 Batch 任务
    print("\n4. 创建 Batch 任务...")
    batch_id = create_batch(input_file_id)

    print(f"\n任务创建完成! Batch ID: {batch_id}")
    print("请使用此ID去查询任务执行结果。")

if __name__ == "__main__":
    main()