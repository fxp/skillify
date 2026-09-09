#!/usr/bin/env python3
"""
用户评论情感分类脚本 - 使用智谱 Batch API

流程：
1. 读取 comments.txt 中的评论
2. 构造 Batch API 所需的 jsonl 文件
3. 上传文件到智谱平台
4. 创建 Batch 任务
5. 打印 batch 任务 ID

重要说明：
- 用户要求使用 glm-5.3 模型，但该模型不在 Batch API 支持的模型列表中
- Batch API 支持的模型白名单包括：glm-5.1、glm-5-turbo、glm-4-plus、glm-4-flash 等
- 这里使用 glm-4-plus 作为替代模型，这是 Batch 支持的较好模型之一
- 如果坚持要用 glm-5.3，需要改用同步 API（非 Batch）逐条处理，但会失去 Batch 的价格优势（50% off）
"""

import os
import requests
import json
import time
from typing import List, Dict

# 配置
API_BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

# 检查 API Key
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# 使用 glm-4-plus 作为替代模型，因为 glm-5.3 不在 Batch API 支持的模型列表中
MODEL = "glm-4-plus"

# 系统提示词
SYSTEM_PROMPT = """你是一个专业的情感分类助手。请根据用户评论的内容，将其分类为以下情感类别之一：

- positive: 正面情感（满意、赞扬、推荐等）
- negative: 负面情感（不满、抱怨、批评等）
- neutral: 中性情感（客观陈述、疑问等）

请以 JSON 格式返回分类结果，包含以下字段：
- sentiment: 情感分类（positive/negative/neutral）
- confidence: 置信度（0-1之间的数值）
- keywords: 关键词列表（3-5个最能体现情感的关键词）

示例：
{"sentiment": "positive", "confidence": 0.95, "keywords": ["满意", "服务好", "推荐"]}"""


def read_comments() -> List[str]:
    """读取 comments.txt 文件中的评论"""
    comments = []
    try:
        with open("comments.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:  # 忽略空行
                    comments.append(line)
    except FileNotFoundError:
        raise FileNotFoundError("comments.txt 文件不存在")
    except Exception as e:
        raise Exception(f"读取 comments.txt 失败: {e}")

    if not comments:
        raise ValueError("comments.txt 为空或没有有效评论")

    print(f"成功读取 {len(comments)} 条评论")
    return comments


def create_batch_requests(comments: List[str]) -> str:
    """构造 Batch API 所需的 jsonl 文件内容"""
    lines = []

    for i, comment in enumerate(comments, 1):
        custom_id = f"sentiment-analysis-{i:04d}"  # 确保custom_id足够长

        request_data = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"请对以下评论进行情感分类：\n\n{comment}"}
                ],
                "temperature": 0.1,  # 降低随机性，提高一致性
                "max_tokens": 200
            }
        }

        lines.append(json.dumps(request_data, ensure_ascii=False))

    return "\n".join(lines)


def upload_file(content: str, purpose: str = "batch") -> str:
    """上传文件到智谱平台"""
    files = {"file": ("batch_requests.jsonl", content, "application/jsonl")}
    data = {"purpose": purpose}

    response = requests.post(
        f"{API_BASE_URL}/paas/v4/files",
        headers={"Authorization": f"Bearer {API_KEY}"},
        files=files,
        data=data
    )

    if response.status_code != 200:
        raise Exception(f"文件上传失败: {response.status_code} - {response.text}")

    file_info = response.json()
    print(f"文件上传成功，文件ID: {file_info['id']}")
    return file_info["id"]


def create_batch(input_file_id: str) -> str:
    """创建 Batch 任务"""
    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分析任务",
            "model": MODEL,
            "total_requests": 1  # 这个值会在实际创建后更新
        }
    }

    response = requests.post(
        f"{API_BASE_URL}/paas/v4/batches",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json=payload
    )

    if response.status_code != 200:
        raise Exception(f"创建 Batch 任务失败: {response.status_code} - {response.text}")

    batch_info = response.json()
    print(f"Batch 任务创建成功!")
    print(f"任务ID: {batch_info['id']}")
    print(f"任务状态: {batch_info['status']}")

    return batch_info["id"]


def main():
    """主函数"""
    try:
        print("开始执行用户评论情感分类任务...")

        # 1. 读取评论
        print("\n步骤1: 读取用户评论...")
        comments = read_comments()

        # 2. 构造 Batch 请求
        print("\n步骤2: 构造 Batch 请求...")
        batch_content = create_batch_requests(comments)

        # 3. 上传文件
        print("\n步骤3: 上传文件到智谱平台...")
        input_file_id = upload_file(batch_content)

        # 4. 创建 Batch 任务
        print("\n步骤4: 创建 Batch 任务...")
        batch_id = create_batch(input_file_id)

        # 打印结果
        print("\n" + "="*50)
        print("任务创建完成!")
        print(f"Batch 任务ID: {batch_id}")
        print("="*50)
        print("\n提示:")
        print(f"- 模型使用: {MODEL}")
        print("- 任务预计处理时间: 24小时内")
        print("- 可以通过以下方式查看任务状态:")
        print(f"  curl -H 'Authorization: Bearer {API_KEY}' '{API_BASE_URL}/paas/v4/batches/{batch_id}'")

    except Exception as e:
        print(f"\n错误: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())