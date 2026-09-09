import os
import json
import io
import requests

def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # Base URL
    base_url = "https://open.bigmodel.cn/api/paas/v4"

    # 读取 comments.txt 文件
    try:
        with open("../run-4/comments.txt", "r", encoding="utf-8") as f:
            comments = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("错误：找不到 comments.txt 文件")
        return

    print(f"读取到 {len(comments)} 条评论")

    # 构造 JSONL 请求文件
    jsonl_lines = []
    for i, comment in enumerate(comments):
        custom_id = f"sentiment-{i+1:04d}"  # 确保至少6个字符
        request = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-4-plus",  # Batch 支持的较强模型
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个情感分析专家。请对用户评论进行情感分类，只返回一个词：正面、负面或中性。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "max_tokens": 10,
                "temperature": 0.1  # 降低随机性，提高一致性
            }
        }
        jsonl_lines.append(json.dumps(request, ensure_ascii=False))

    # 创建临时 JSONL 文件
    jsonl_content = "\n".join(jsonl_lines)
    print(f"构造了包含 {len(jsonl_lines)} 个请求的 JSONL 文件")

    # 上传文件
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        with io.BytesIO(jsonl_content.encode('utf-8')) as f:
            upload_response = requests.post(
                f"{base_url}/files",
                headers=headers,
                files={"file": ("batch_requests.jsonl", f, "application/json")},
                data={"purpose": "batch"}
            )
            upload_response.raise_for_status()
            upload_result = upload_response.json()
            input_file_id = upload_result["id"]
            print(f"文件上传成功，文件ID: {input_file_id}")
    except Exception as e:
        print(f"文件上传失败: {e}")
        return

    # 创建 Batch 任务
    try:
        batch_response = requests.post(
            f"{base_url}/batches",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "input_file_id": input_file_id,
                "endpoint": "/v4/chat/completions",
                "auto_delete_input_file": True,
                "metadata": {
                    "description": "评论情感分析 Batch 任务",
                    "total_requests": len(comments)
                }
            }
        )
        batch_response.raise_for_status()
        batch_result = batch_response.json()
        batch_id = batch_result["id"]
        print(f"Batch 任务创建成功！")
        print(f"Batch ID: {batch_id}")

        # 打印任务状态信息
        print(f"任务状态: {batch_result.get('status', 'unknown')}")
        print(f"请使用 Batch ID: {batch_id} 来查询任务进度和结果")

    except Exception as e:
        print(f"创建 Batch 任务失败: {e}")
        return

if __name__ == "__main__":
    main()