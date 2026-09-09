#!/usr/bin/env python3
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

    # 基础配置
    base_url = "https://open.bigmodel.cn/api"
    headers = {"Authorization": f"Bearer {api_key}"}

    # 读取评论文件
    try:
        with open("../comments.txt", "r", encoding="utf-8") as f:
            comments = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("错误：找不到 comments.txt 文件")
        return

    print(f"读取到 {len(comments)} 条评论")

    # 构造 Batch 请求的 JSONL 内容
    # 使用 Batch API 支持的最强模型 glm-4-plus
    requests_data = []
    for i, comment in enumerate(comments):
        # custom_id 必须至少6个字符
        custom_id = f"req-{i:05d}"

        request_line = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-4-plus",  # Batch API 支持的最强模型
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个情感分类助手。请对用户评论进行情感分类，只返回一个结果，分类结果必须是：正面、负面、中性之一。不要解释，只返回分类结果。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低随机性，提高一致性
                "max_tokens": 10  # 只需要返回分类结果
            }
        }
        requests_data.append(request_line)

    # 创建 JSONL 文件内容
    jsonl_content = "\n".join(json.dumps(req, ensure_ascii=False) for req in requests_data)

    # 1. 上传 JSONL 文件
    print("正在上传请求文件...")
    try:
        files = {
            "file": ("batch_requests.jsonl", io.BytesIO(jsonl_content.encode("utf-8")), "application/json")
        }
        data = {"purpose": "batch"}

        upload_response = requests.post(
            f"{base_url}/paas/v4/files",
            headers=headers,
            files=files,
            data=data
        )
        upload_response.raise_for_status()
        file_info = upload_response.json()
        input_file_id = file_info["id"]
        print(f"文件上传成功，文件ID: {input_file_id}")
    except requests.exceptions.RequestException as e:
        print(f"文件上传失败: {e}")
        if e.response:
            print(f"响应内容: {e.response.text}")
        return

    # 2. 创建 Batch 任务
    print("正在创建 Batch 任务...")
    try:
        batch_request = {
            "input_file_id": input_file_id,
            "endpoint": "/v4/chat/completions",
            "auto_delete_input_file": True,
            "metadata": {
                "description": "评论情感分析任务",
                "model": "glm-4-plus",
                "total_requests": len(requests_data)
            }
        }

        batch_response = requests.post(
            f"{base_url}/paas/v4/batches",
            headers={**headers, "Content-Type": "application/json"},
            json=batch_request
        )
        batch_response.raise_for_status()
        batch_info = batch_response.json()
        batch_id = batch_info["id"]

        print(f"Batch 任务创建成功！")
        print(f"任务ID: {batch_id}")
        print(f"任务状态: {batch_info['status']}")
        print(f"请使用此任务ID查询结果: {batch_id}")

    except requests.exceptions.RequestException as e:
        print(f"创建 Batch 任务失败: {e}")
        if e.response:
            print(f"响应内容: {e.response.text}")
        return

if __name__ == "__main__":
    main()