#!/usr/bin/env python3
"""
使用智谱Batch API对评论进行情感分类
Batch API价格为标准API的50%，适合大批量处理
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

    # API基础配置
    base_url = "https://open.bigmodel.cn/api"
    headers = {"Authorization": f"Bearer {api_key}"}

    # 读取评论文件
    comments_file = Path(__file__).parent.parent / "comments.txt"
    if not comments_file.exists():
        print(f"错误：找不到评论文件 {comments_file}")
        return

    # 读取所有评论
    with open(comments_file, 'r', encoding='utf-8') as f:
        comments = [line.strip() for line in f if line.strip()]

    print(f"读取到 {len(comments)} 条评论")

    # 构造JSONL请求文件内容
    # 使用Batch支持的最佳模型：glm-5.1（Batch白名单中最强）
    requests_data = []
    for i, comment in enumerate(comments):
        custom_id = f"req-{i:05d}"  # 6位数字，满足custom_id至少6字符的要求

        request_entry = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-5.1",  # Batch白名单中最强的模型
                "messages": [
                    {
                        "role": "system",
                        "content": """你是一个专业的情感分析专家。请对用户的评论进行情感分类，只返回以下三种结果之一：
- "正面"：评论表达满意、推荐、赞扬等积极情感
- "负面"：评论表达不满、批评、抱怨等消极情感
- "中性"：评论客观描述、中立或无明显情感倾向

请只返回情感分类结果，不要添加任何解释。"""
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低随机性，提高分类一致性
                "max_tokens": 50  # 只要分类结果，不需要长输出
            }
        }
        requests_data.append(request_entry)

    # 创建JSONL文件内容
    jsonl_content = "\n".join([json.dumps(req, ensure_ascii=False) for req in requests_data])
    print(f"构造了 {len(requests_data)} 个请求")

    # 上传JSONL文件
    print("上传请求文件...")
    try:
        files = {
            "file": ("batch_requests.jsonl", jsonl_content.encode('utf-8'), "application/json")
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
        if hasattr(e, 'response') and e.response is not None:
            print(f"错误详情: {e.response.text}")
        return

    # 创建Batch任务
    print("创建Batch任务...")
    try:
        batch_request = {
            "input_file_id": input_file_id,
            "endpoint": "/v4/chat/completions",
            "auto_delete_input_file": True,  # 任务完成后自动删除输入文件
            "metadata": {
                "description": "用户评论情感分析",
                "total_requests": len(requests_data),
                "model": "glm-5.1"
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

        print(f"Batch任务创建成功！")
        print(f"任务ID: {batch_id}")
        print(f"任务状态: {batch_info['status']}")
        print(f"请前往控制台或使用API查看任务进度: https://open.bigmodel.cn/batches/{batch_id}")

        # 输出任务ID到stdout，方便脚本调用者获取
        print(f"\nbatch_id={batch_id}")

    except requests.exceptions.RequestException as e:
        print(f"创建Batch任务失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"错误详情: {e.response.text}")
        return

if __name__ == "__main__":
    main()