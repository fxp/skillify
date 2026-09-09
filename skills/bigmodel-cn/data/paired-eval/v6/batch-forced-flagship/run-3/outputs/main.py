#!/usr/bin/env python3
import os
import json
import requests
import io

def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 读取 comments.txt 文件
    try:
        with open('comments.txt', 'r', encoding='utf-8') as f:
            comments = [line.strip() for line in f if line.strip()]
        print(f"读取到 {len(comments)} 条评论")
    except FileNotFoundError:
        print("错误：找不到 comments.txt 文件")
        return

    # 构造 Batch 请求的 JSONL 内容
    batch_requests = []
    for i, comment in enumerate(comments):
        # custom_id 至少需要 6 个字符
        custom_id = f"req-{i+1:05d}"

        # 构造请求体 - 使用 glm-5.1（Batch API 白名单中最强的模型）
        request_data = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-5.1",  # Batch API 白名单中最强的模型
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个情感分析专家。请对用户评论进行情感分类，只返回 JSON 格式：{\"sentiment\": \"正面|负面|中性\", \"confidence\": 0-1的数字, \"keywords\": [关键词数组]}"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "max_tokens": 200,
                "temperature": 0.1
            }
        }
        batch_requests.append(request_data)

    # 创建 JSONL 内容
    jsonl_content = '\n'.join(json.dumps(req, ensure_ascii=False) for req in batch_requests)
    print(f"构造了 {len(batch_requests)} 个 Batch 请求")

    # 上传文件
    try:
        response = requests.post(
            "https://open.bigmodel.cn/api/paas/v4/files",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("batch_requests.jsonl", io.BytesIO(jsonl_content.encode('utf-8')), "application/json")},
            data={"purpose": "batch"}
        )

        if response.status_code != 200:
            print(f"上传文件失败: {response.status_code}")
            print(response.text)
            return

        upload_result = response.json()
        input_file_id = upload_result.get("id")
        print(f"文件上传成功，文件ID: {input_file_id}")

        if not input_file_id:
            print("上传响应中没有包含文件ID")
            return

    except Exception as e:
        print(f"上传文件时出错: {str(e)}")
        return

    # 创建 Batch 任务
    try:
        response = requests.post(
            "https://open.bigmodel.cn/api/paas/v4/batches",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "input_file_id": input_file_id,
                "endpoint": "/v4/chat/completions",
                "auto_delete_input_file": True,
                "metadata": {
                    "description": "评论情感分析任务",
                    "total_requests": len(comments),
                    "model": "glm-5.1"
                }
            }
        )

        if response.status_code != 200:
            print(f"创建 Batch 任务失败: {response.status_code}")
            print(response.text)
            return

        batch_result = response.json()
        batch_id = batch_result.get("id")

        if not batch_id:
            print("创建 Batch 响应中没有包含任务ID")
            return

        print(f"Batch 任务创建成功！")
        print(f"任务ID: {batch_id}")
        print(f"任务状态: {batch_result.get('status')}")
        print(f"请使用此任务ID查询任务状态和结果")

        # 输出任务的详细信息
        print("\n任务详细信息:")
        print(f"- 输入文件ID: {input_file_id}")
        print(f"- 请求总数: {batch_result.get('request_counts', {}).get('total', 'unknown')}")
        print(f"- 端点: /v4/chat/completions")
        print(f"- 完成窗口: 24小时内（预计）")

    except Exception as e:
        print(f"创建 Batch 任务时出错: {str(e)}")
        return

if __name__ == "__main__":
    main()