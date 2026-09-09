#!/usr/bin/env python3
import os
import json
import requests

def create_jsonl_file(comments):
    """创建批处理请求的.jsonl文件"""
    jsonl_lines = []
    for i, comment in enumerate(comments, 1):
        # 每个请求必须包含唯一的custom_id（至少6个字符）
        custom_id = f"sentiment-{i:04d}"

        # 构造请求内容
        request = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-5.1",  # 使用Batch API支持的最佳模型
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个专业的情感分类器。请根据用户评论的内容，将其分类为以下三种情感之一：正面、负面、中性。请严格按照以下格式返回：{\"分类标签\": \"正面/负面/中性\"}。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低随机性，提高一致性
                "max_tokens": 50
            }
        }
        jsonl_lines.append(json.dumps(request, ensure_ascii=False))

    # 写入.jsonl文件
    jsonl_path = "batch_requests.jsonl"
    with open(jsonl_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(jsonl_lines))

    return jsonl_path

def upload_file(file_path):
    """上传文件到智谱平台"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/files"
    headers = {"Authorization": f"Bearer {api_key}"}

    with open(file_path, 'rb') as f:
        files = {"file": f}
        data = {"purpose": "batch"}

        response = requests.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()

    return response.json()

def create_batch_task(file_id):
    """创建批处理任务"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/batches"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "input_file_id": file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分析任务",
            "type": "sentiment_classification"
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    return response.json()

def main():
    # 读取comments.txt文件
    comments = [
        "这家店的服务态度很好，产品质量也不错，下次还会再来。",
        "物流太慢了，等了一个星期才收到货，产品质量也不怎么样。",
        "客服回复很及时，帮我解决了问题，很满意。",
        "价格有点贵，但是质量确实不错。",
        "包装很仔细，商品完好无损，配送速度也很快。",
        "退换货很麻烦，客服态度也不好，不会再来第二次了。",
        "产品质量很好，使用体验也很棒，值得推荐。",
        "总体来说还行，但是还有改进空间。",
        "非常失望，完全不值这个价格。",
        "超预期的服务，从购买到售后都很完美。"
    ]

    try:
        print("开始创建批处理任务...")

        # 1. 创建JSONL请求文件
        jsonl_path = create_jsonl_file(comments)
        print(f"✓ 已创建JSONL文件: {jsonl_path}")

        # 2. 上传文件
        file_info = upload_file(jsonl_path)
        file_id = file_info["id"]
        print(f"✓ 文件上传成功，文件ID: {file_id}")

        # 3. 创建批处理任务
        batch_info = create_batch_task(file_id)
        batch_id = batch_info["id"]
        print(f"✓ 批处理任务创建成功")
        print(f"✓ 任务ID: {batch_id}")
        print(f"✓ 任务状态: {batch_info['status']}")

        # 打印任务ID到stdout（符合要求）
        print(batch_id)

    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())