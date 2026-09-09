#!/usr/bin/env python3
import os
import json
import requests
import time
from pathlib import Path

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"

def main():
    # 检查 API Key
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    headers = {"Authorization": f"Bearer {API_KEY}"}

    # 读取评论文件
    comments_file = Path(__file__).parent.parent / "comments.txt"
    if not comments_file.exists():
        print(f"错误：找不到评论文件 {comments_file}")
        return

    # 读取所有评论
    with open(comments_file, "r", encoding="utf-8") as f:
        comments = [line.strip() for line in f.readlines() if line.strip()]

    print(f"读取到 {len(comments)} 条评论")

    # 构造 JSONL 请求文件
    jsonl_lines = []
    for i, comment in enumerate(comments, 1):
        custom_id = f"sentiment-{i:03d}"  # 至少6个字符

        request_line = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-5.1",  # Batch 支持的最佳模型
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个专业的情感分类助手。请对用户评论进行情感分类，只返回以下三个标签之一：正面、负面、中性。不要解释，不要输出其他内容。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低随机性，提高一致性
                "max_tokens": 10
            }
        }
        jsonl_lines.append(request_line)

    # 保存为临时 JSONL 文件
    temp_jsonl = Path("/tmp/batch_requests.jsonl")
    with open(temp_jsonl, "w", encoding="utf-8") as f:
        for line in jsonl_lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    print(f"构造了 {len(jsonl_lines)} 个请求，保存到 {temp_jsonl}")

    # 上传文件
    print("正在上传文件...")
    try:
        with open(temp_jsonl, "rb") as f:
            upload_resp = requests.post(
                f"{BASE_URL}/paas/v4/files",
                headers=headers,
                files={"file": f},
                data={"purpose": "batch"}
            )
        upload_resp.raise_for_status()
        file_info = upload_resp.json()
        input_file_id = file_info["id"]
        print(f"文件上传成功，文件 ID: {input_file_id}")
    except requests.exceptions.RequestException as e:
        print(f"文件上传失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应内容: {e.response.text}")
        return

    # 创建 Batch 任务
    print("正在创建 Batch 任务...")
    try:
        batch_resp = requests.post(
            f"{BASE_URL}/paas/v4/batches",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "input_file_id": input_file_id,
                "endpoint": "/v4/chat/completions",
                "auto_delete_input_file": True,
                "metadata": {
                    "description": "用户评论情感分析任务",
                    "request_count": len(comments)
                }
            }
        )
        batch_resp.raise_for_status()
        batch_info = batch_resp.json()
        batch_id = batch_info["id"]

        print(f"Batch 任务创建成功！")
        print(f"任务 ID: {batch_id}")
        print(f"任务状态: {batch_info['status']}")

        # 打印任务信息
        if "request_counts" in batch_info:
            print(f"请求数: {batch_info['request_counts']['total']}")

        # 临时文件已上传，可以删除本地临时文件
        try:
            os.remove(temp_jsonl)
            print(f"临时文件 {temp_jsonl} 已删除")
        except:
            pass

    except requests.exceptions.RequestException as e:
        print(f"创建 Batch 任务失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应内容: {e.response.text}")
        return

if __name__ == "__main__":
    main()