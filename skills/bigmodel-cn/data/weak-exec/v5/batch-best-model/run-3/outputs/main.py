#!/usr/bin/env python3
"""
情感分类 Batch 任务提交脚本
使用智谱 BigModel 的 Batch 批量推理接口对用户评论进行情感分类
"""

import os
import json
import requests
import io

# 从环境变量读取 API Key
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# API 配置
BASE_URL = "https://open.bigmodel.cn/api"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# 评论数据（从 comments.txt 读取）
COMMENTS = [
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

# 系统提示词
SYSTEM_PROMPT = """你是一个专业的情感分类器。请对用户评论进行情感分类，只输出一个分类结果：
- 正面：评论表达满意、赞扬、推荐等积极情感
- 负面：评论表达不满、抱怨、批评等消极情感
- 中性：评论客观陈述，没有明显情感倾向

请只回复"正面"、"负面"或"中性"，不要添加任何其他解释。"""

def create_jsonl_request(comments):
    """创建 Batch API 的 .jsonl 请求文件"""
    lines = []
    for i, comment in enumerate(comments):
        # custom_id 最少需要 6 个字符
        custom_id = f"req-{i+1:05d}"

        request_data = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-5.1",  # Batch API 支持的最好模型
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"请对以下评论进行情感分类：{comment}"}
                ],
                "temperature": 0.1,  # 降低随机性，提高分类一致性
                "max_tokens": 10  # 只需要输出分类结果
            }
        }
        lines.append(json.dumps(request_data, ensure_ascii=False))

    return "\n".join(lines)

def upload_batch_file(jsonl_content):
    """上传 Batch 请求文件"""
    buffer = io.BytesIO(jsonl_content.encode())

    files = {
        "file": ("batch_requests.jsonl", buffer, "application/json")
    }
    data = {
        "purpose": "batch"
    }

    response = requests.post(
        f"{BASE_URL}/paas/v4/files",
        headers=HEADERS,
        files=files,
        data=data
    )

    response.raise_for_status()
    return response.json()

def create_batch_task(input_file_id):
    """创建 Batch 任务"""
    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分类任务",
            "total_requests": len(COMMENTS)
        }
    }

    response = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=payload
    )

    response.raise_for_status()
    return response.json()

def main():
    """主函数"""
    print("开始创建 Batch 情感分类任务...")

    # 1. 创建 JSONL 请求文件
    print(f"正在处理 {len(COMMENTS)} 条评论...")
    jsonl_content = create_jsonl_request(COMMENTS)

    # 2. 上传文件
    print("上传请求文件...")
    file_info = upload_batch_file(jsonl_content)
    input_file_id = file_info["id"]
    print(f"文件上传成功，文件ID: {input_file_id}")

    # 3. 创建 Batch 任务
    print("创建 Batch 任务...")
    batch_info = create_batch_task(input_file_id)
    batch_id = batch_info["id"]

    print(f"\nBatch 任务创建成功！")
    print(f"任务ID: {batch_id}")
    print(f"任务状态: {batch_info['status']}")
    print(f"请记录此任务ID，稍后可用于查询任务状态和获取结果")

if __name__ == "__main__":
    main()