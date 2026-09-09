#!/usr/bin/env python3
"""
使用智谱AI Batch API对评论进行情感分类
使用最好的模型glm-4-plus进行情感分析（正面/负面/中性）
"""

import os
import json
import requests
from pathlib import Path

def main():
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # Base URL
    base_url = "https://open.bigmodel.cn/api"

    # 读取评论文件
    comments_file = Path(__file__).parent.parent / "run-2" / "comments.txt"
    if not comments_file.exists():
        print(f"错误：找不到评论文件 {comments_file}")
        return

    # 读取评论
    with open(comments_file, 'r', encoding='utf-8') as f:
        comments = [line.strip() for line in f.readlines() if line.strip()]

    # 构造JSONL请求文件
    jsonl_lines = []
    for i, comment in enumerate(comments):
        # custom_id 至少需要6个字符
        custom_id = f"req-{i+1:03d}"

        # 构造请求体
        request_data = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-4-plus",  # 使用Batch支持的最好模型
                "messages": [
                    {
                        "role": "system",
                        "content": """你是一个专业的情感分析专家。请对用户评论进行情感分类，只返回以下三种之一：正面、负面、中性。
分类标准：
- 正面：表达满意、赞扬、推荐等积极情绪
- 负面：表达不满、批评、抱怨等消极情绪
- 中性：客观描述、中性评价或情感不明显的评论

请只返回一个词：正面、负面或中性。"""
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低随机性，提高一致性
                "max_tokens": 10  # 只要一个词，不需要太多token
            }
        }
        jsonl_lines.append(json.dumps(request_data, ensure_ascii=False))

    # 写入JSONL文件
    jsonl_file = "batch_requests.jsonl"
    with open(jsonl_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(jsonl_lines))

    print(f"已构造 {len(comments)} 条评论的JSONL请求文件：{jsonl_file}")

    # 上传文件
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        with open(jsonl_file, 'rb') as f:
            upload_resp = requests.post(
                f"{base_url}/paas/v4/files",
                headers=headers,
                files={"file": f},
                data={"purpose": "batch"}
            )
            upload_resp.raise_for_status()

        input_file_id = upload_resp.json()["id"]
        print(f"文件上传成功，文件ID: {input_file_id}")

        # 创建Batch任务
        batch_resp = requests.post(
            f"{base_url}/paas/v4/batches",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "input_file_id": input_file_id,
                "endpoint": "/v4/chat/completions",
                "auto_delete_input_file": True,
                "metadata": {
                    "description": "评论情感分析任务",
                    "total_requests": len(comments),
                    "model": "glm-4-plus"
                }
            }
        )
        batch_resp.raise_for_status()

        batch_data = batch_resp.json()
        batch_id = batch_data["id"]

        print(f"Batch任务创建成功！")
        print(f"任务ID: {batch_id}")
        print(f"任务状态: {batch_data['status']}")
        print(f"请稍后在控制台查看结果，或使用API轮询任务状态")

    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应内容: {e.response.text}")

    finally:
        # 清理临时文件
        if os.path.exists(jsonl_file):
            os.remove(jsonl_file)
            print(f"已清理临时文件: {jsonl_file}")

if __name__ == "__main__":
    main()