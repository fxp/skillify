#!/usr/bin/env python3
"""
Batch API 情感分类脚本
使用智谱 BigModel 的 Batch 推理接口对用户评论进行情感分类（正面/负面/中性）
"""

import os
import json
import requests
import time
from pathlib import Path

# 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# Batch API 支持的最佳模型（根据白名单）
# 从 references/files-batch.md 中可知，glm-5.3 不在 Batch 白名单中
# 白名单中最强的模型是 glm-5.1
BATCH_MODEL = "glm-5.1"

# 系统提示 - 情感分类任务
SYSTEM_PROMPT = """你是一个情感分类专家。请对用户评论进行情感分类，只返回以下三种标签之一：
- 正面：表达满意、赞扬、推荐等积极情感的评论
- 负面：表达不满、批评、抱怨等消极情感的评论
- 中性：客观陈述、事实描述，无明显情感倾向的评论

请严格按照上述三个分类标准进行判断，不要添加任何解释文字。"""

def read_comments():
    """读取 comments.txt 文件中的评论"""
    comments_file = Path(__file__).parent.parent / "comments.txt"
    if not comments_file.exists():
        # 如果 comments.txt 不存在，创建一些示例评论用于测试
        sample_comments = [
            "商品质量很好，物流速度也快，非常满意！",
            "客服态度很差，解决问题很慢，体验感不好。",
            "订单已经收到了，包装完好。",
            "这个产品性价比很高，推荐给大家购买。",
            "发货速度太慢了，等了好几天才到。",
            "商品描述和实物基本一致，没有太多差别。",
            "售后服务很到位，问题解决得很及时。",
            "产品质量一般，价格也不便宜。"
        ]
        return sample_comments

    with open(comments_file, 'r', encoding='utf-8') as f:
        comments = [line.strip() for line in f if line.strip()]

    if not comments:
        raise ValueError("comments.txt 文件为空")

    return comments

def create_jsonl_request_file(comments):
    """创建 JSONL 请求文件"""
    request_lines = []

    for i, comment in enumerate(comments, 1):
        custom_id = f"request-{i:03d}"  # 确保 custom_id 至少6个字符

        request = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": BATCH_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"请对以下评论进行情感分类：{comment}"}
                ],
                "temperature": 0.1,  # 降低温度以获得更确定的结果
                "max_tokens": 50  # 限制输出长度，只需要返回分类标签
            }
        }
        request_lines.append(request)

    # 保存为临时 JSONL 文件
    jsonl_file = Path(__file__).parent / "batch_requests.jsonl"
    with open(jsonl_file, 'w', encoding='utf-8') as f:
        for request in request_lines:
            f.write(json.dumps(request, ensure_ascii=False) + '\n')

    return jsonl_file

def upload_batch_file(jsonl_file):
    """上传 JSONL 文件到 Batch API"""
    print(f"正在上传文件: {jsonl_file}")

    with open(jsonl_file, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers={"Authorization": f"Bearer {API_KEY}"},
            files={"file": f},
            data={"purpose": "batch"}
        )

    response.raise_for_status()
    file_info = response.json()
    print(f"文件上传成功，文件ID: {file_info['id']}")

    return file_info['id']

def create_batch_task(input_file_id):
    """创建 Batch 任务"""
    print("正在创建 Batch 任务...")

    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分析任务",
            "model": BATCH_MODEL,
            "total_requests": len(open(Path(__file__).parent / "batch_requests.jsonl").readlines())
        }
    }

    response = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json=payload
    )

    response.raise_for_status()
    batch_info = response.json()

    print(f"Batch 任务创建成功！")
    print(f"任务ID: {batch_info['id']}")
    print(f"任务状态: {batch_info['status']}")
    print(f"请求总数: {batch_info['request_counts']['total']}")

    return batch_info['id']

def main():
    """主函数"""
    print("开始 Batch API 情感分类任务...")

    try:
        # 1. 读取评论
        comments = read_comments()
        print(f"读取到 {len(comments)} 条评论")

        # 2. 创建 JSONL 请求文件
        jsonl_file = create_jsonl_request_file(comments)
        print(f"已创建请求文件: {jsonl_file}")

        # 3. 上传文件
        input_file_id = upload_batch_file(jsonl_file)

        # 4. 创建 Batch 任务
        batch_id = create_batch_task(input_file_id)

        # 5. 输出结果
        print("\n" + "="*50)
        print("任务创建完成！")
        print(f"Batch 任务ID: {batch_id}")
        print("请使用此 ID 查询任务状态和获取结果")
        print("="*50)

        return batch_id

    except Exception as e:
        print(f"错误: {str(e)}")
        raise

if __name__ == "__main__":
    batch_id = main()
    # 将 batch_id 打印到 stdout，符合要求
    print(batch_id)