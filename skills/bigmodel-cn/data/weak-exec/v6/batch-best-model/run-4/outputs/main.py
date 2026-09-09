#!/usr/bin/env python3
import os
import json
import requests
import io

def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # Base URL
    base_url = "https://open.bigmodel.cn/api"
    headers = {"Authorization": f"Bearer {api_key}"}

    # 读取评论文件
    try:
        with open("../run-2/comments.txt", "r", encoding="utf-8") as f:
            comments = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("错误：找不到 comments.txt 文件，请在正确位置运行脚本")
        return

    print(f"读取到 {len(comments)} 条评论")

    # 构造 JSONL 文件内容
    jsonl_lines = []
    for i, comment in enumerate(comments):
        # custom_id 必须至少 6 个字符
        custom_id = f"req-{i+1:05d}"

        line = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-5.1",  # Batch 支持的最好模型
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个情感分类专家。请对用户评论进行情感分类，只返回一个词：正面、负面或中性。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "max_tokens": 10,  # 只要一个词，不需要太多
                "temperature": 0.1  # 降低随机性
            }
        }
        jsonl_lines.append(json.dumps(line, ensure_ascii=False))

    jsonl_content = "\n".join(jsonl_lines)
    print("已构造 JSONL 请求文件")

    # 上传文件
    print("正在上传文件...")
    try:
        files = {
            "file": ("batch_requests.jsonl", io.BytesIO(jsonl_content.encode()), "application/json")
        }
        data = {"purpose": "batch"}

        upload_resp = requests.post(
            f"{base_url}/paas/v4/files",
            headers=headers,
            files=files,
            data=data
        )
        upload_resp.raise_for_status()
        file_info = upload_resp.json()
        input_file_id = file_info["id"]
        print(f"文件上传成功，文件 ID: {input_file_id}")
    except Exception as e:
        print(f"文件上传失败: {e}")
        return

    # 创建 Batch 任务
    print("正在创建 Batch 任务...")
    try:
        batch_data = {
            "input_file_id": input_file_id,
            "endpoint": "/v4/chat/completions",
            "auto_delete_input_file": True,
            "metadata": {
                "description": "用户评论情感分析",
                "comment_count": len(comments),
                "model": "glm-5.1"
            }
        }

        batch_resp = requests.post(
            f"{base_url}/paas/v4/batches",
            headers={**headers, "Content-Type": "application/json"},
            json=batch_data
        )
        batch_resp.raise_for_status()
        batch_info = batch_resp.json()
        batch_id = batch_info["id"]

        print(f"Batch 任务创建成功！")
        print(f"任务 ID: {batch_id}")
        print(f"任务状态: {batch_info['status']}")
        print(f"请使用此 ID 查询任务状态和获取结果")

    except Exception as e:
        print(f"创建 Batch 任务失败: {e}")
        return

if __name__ == "__main__":
    main()