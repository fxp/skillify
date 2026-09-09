import os
import json
import requests
import io

# API 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

def read_comments():
    """读取评论文件"""
    # 相对于脚本位置的 comments.txt 文件路径
    comments_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "comments.txt")
    with open(comments_file, "r", encoding="utf-8") as f:
        comments = [line.strip() for line in f if line.strip()]
    return comments

def create_jsonl_request(comments):
    """构造 Batch API 所需的 .jsonl 请求文件内容"""
    lines = []
    for i, comment in enumerate(comments):
        # custom_id 最少需要 6 个字符，使用 request-xxxxx 格式
        custom_id = f"req-{i+1:05d}"

        line = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-5.1",  # Batch API 白名单中最好的模型
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个专业的情感分类助手。请对以下用户评论进行情感分类，只返回一个结果：正面、负面或中性。请确保分类准确。"
                    },
                    {
                        "role": "user",
                        "content": f"请对这条评论进行情感分类：{comment}"
                    }
                ],
                "max_tokens": 50,  # 情感分类只需要简短回答
                "temperature": 0.1,  # 降低随机性，提高一致性
                "stream": False
            }
        }
        lines.append(json.dumps(line, ensure_ascii=False))

    return "\n".join(lines)

def upload_batch_file(jsonl_content):
    """上传 Batch 请求文件"""
    print("正在上传 Batch 请求文件...")

    files = {
        "file": ("batch_requests.jsonl", io.BytesIO(jsonl_content.encode()), "application/json")
    }
    data = {"purpose": "batch"}

    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        response = requests.post(
            f"{BASE_URL}/files",
            headers=headers,
            files=files,
            data=data
        )
        response.raise_for_status()
        file_info = response.json()
        print(f"文件上传成功，文件 ID: {file_info['id']}")
        return file_info["id"]
    except requests.exceptions.RequestException as e:
        print(f"文件上传失败: {e}")
        if e.response:
            print(f"错误响应: {e.response.text}")
        raise

def create_batch_task(input_file_id):
    """创建 Batch 任务"""
    print("正在创建 Batch 任务...")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分类任务",
            "model": "glm-5.1",
            "task_type": "sentiment_analysis"
        }
    }

    try:
        response = requests.post(
            f"{BASE_URL}/batches",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        batch_info = response.json()
        print(f"Batch 任务创建成功！")
        return batch_info["id"]
    except requests.exceptions.RequestException as e:
        print(f"创建 Batch 任务失败: {e}")
        if e.response:
            print(f"错误响应: {e.response.text}")
        raise

def main():
    """主函数"""
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    try:
        # 1. 读取评论
        print("正在读取评论文件...")
        comments = read_comments()
        print(f"读取到 {len(comments)} 条评论")

        # 2. 创建 JSONL 请求文件
        print("正在构造 JSONL 请求文件...")
        jsonl_content = create_jsonl_request(comments)
        print(f"JSONL 文件内容大小: {len(jsonl_content)} 字符")

        # 3. 上传文件
        input_file_id = upload_batch_file(jsonl_content)

        # 4. 创建 Batch 任务
        batch_id = create_batch_task(input_file_id)

        # 5. 输出结果
        print("\n" + "="*50)
        print("任务创建成功！")
        print(f"Batch 任务 ID: {batch_id}")
        print("="*50)
        print("\n提示：")
        print("- 您可以使用这个 ID 来查询任务状态")
        print("- 任务完成后，可以通过 output_file_id 下载结果")
        print("- Batch API 价格为标准 API 的 50%，可以节省成本")

    except Exception as e:
        print(f"程序执行失败: {e}")
        return

if __name__ == "__main__":
    main()