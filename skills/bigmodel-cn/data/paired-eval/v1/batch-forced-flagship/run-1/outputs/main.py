#!/usr/bin/env python3
"""
情感分析批处理脚本
使用智谱AI Batch API对用户评论进行情感分类
"""

import os
import json
import requests
import time
from typing import List, Dict, Any

# 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# 模型选择：由于glm-5.3不支持Batch API，使用glm-4-plus作为替代
# Batch API支持的模型白名单：glm-5.1、glm-5-turbo、glm-4、glm-4-plus等
BATCH_MODEL = "glm-4-plus"
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30

def read_comments(file_path: str) -> List[str]:
    """读取评论文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            comments = [line.strip() for line in f.readlines() if line.strip()]
        print(f"成功读取 {len(comments)} 条评论")
        return comments
    except FileNotFoundError:
        print(f"错误：文件 {file_path} 不存在")
        return []
    except Exception as e:
        print(f"读取文件失败：{e}")
        return []

def create_jsonl_requests(comments: List[str]) -> str:
    """创建JSONL格式的请求内容"""
    json_lines = []
    for i, comment in enumerate(comments, 1):
        custom_id = f"sentiment-{i:06d}"  # 确保custom_id长度至少6个字符

        request_data = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": BATCH_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个情感分析专家。请对用户评论进行情感分类，返回JSON格式，包含：sentiment（情感标签：positive/negative/neutral）、confidence（置信度0-1）、keywords（关键词列表）。只返回JSON，不要其他文字。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分析：{comment}"
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 200
            }
        }
        json_lines.append(json.dumps(request_data, ensure_ascii=False))

    return '\n'.join(json_lines)

def upload_file(jsonl_content: str) -> str:
    """上传JSONL文件"""
    for attempt in range(MAX_RETRIES):
        try:
            files = {"file": ("batch_requests.jsonl", jsonl_content.encode('utf-8'), "application/json")}
            data = {"purpose": "batch"}

            response = requests.post(
                f"{BASE_URL}/paas/v4/files",
                headers=HEADERS,
                files=files,
                data=data,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 200:
                file_info = response.json()
                print(f"文件上传成功，文件ID: {file_info['id']}")
                return file_info["id"]
            else:
                print(f"文件上传失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {response.status_code} - {response.text}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)

        except requests.exceptions.RequestException as e:
            print(f"文件上传异常 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)

    raise Exception(f"文件上传失败，已尝试 {MAX_RETRIES} 次")

def create_batch(input_file_id: str) -> str:
    """创建批处理任务"""
    batch_data = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分析",
            "model": BATCH_MODEL,
            "total_requests": len(json.loads(request_data)['comments']) if 'request_data' in locals() else 0
        }
    }

    try:
        response = requests.post(
            f"{BASE_URL}/paas/v4/batches",
            headers={**HEADERS, "Content-Type": "application/json"},
            json=batch_data,
            timeout=REQUEST_TIMEOUT
        )

        if response.status_code == 200:
            batch_info = response.json()
            print(f"Batch任务创建成功！")
            print(f"任务ID: {batch_info['id']}")
            print(f"初始状态: {batch_info['status']}")
            print(f"请使用以下ID查询任务进度: {batch_info['id']}")
            return batch_info["id"]
        else:
            print(f"创建Batch任务失败: {response.status_code} - {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"创建Batch任务异常: {e}")
        return None

def check_batch_status(batch_id: str) -> Dict[str, Any]:
    """检查Batch任务状态"""
    try:
        response = requests.get(
            f"{BASE_URL}/paas/v4/batches/{batch_id}",
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT
        )

        if response.status_code == 200:
            return response.json()
        else:
            print(f"查询任务状态失败: {response.status_code} - {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"查询任务状态异常: {e}")
        return None

def main():
    """主函数"""
    print("=== 智谱AI Batch API 情感分析 ===")

    # 检查API Key
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 读取评论
    comments_file = "comments.txt"
    comments = read_comments(comments_file)

    if not comments:
        print("没有找到需要分析的评论")
        return

    # 说明模型调整
    print(f"\n注意：由于glm-5.3不支持Batch API，使用{BATCH_MODEL}作为替代模型")
    print("Batch API支持的模型有限，{BATCH_MODEL}是当前最佳的替代选择")
    print()

    try:
        # 创建JSONL请求内容
        print("正在创建JSONL请求文件...")
        jsonl_content = create_jsonl_requests(comments)

        # 上传文件
        print("正在上传文件...")
        input_file_id = upload_file(jsonl_content)

        # 创建Batch任务
        print("正在创建Batch任务...")
        batch_id = create_batch(input_file_id)

        if batch_id:
            print(f"\n✅ 任务创建成功！")
            print(f"📋 Batch任务ID: {batch_id}")
            print(f"💡 提示：您可以使用此ID查询任务进度或下载结果")
            print("\n任务预计需要一些时间处理，请定期检查任务状态")
        else:
            print("\n❌ 任务创建失败，请检查错误信息")

    except Exception as e:
        print(f"\n❌ 执行过程中出现错误: {e}")
        print("\n可能的解决方案：")
        print("1. 检查网络连接是否正常")
        print("2. 确认API Key是否有效且有足够额度")
        print("3. 确认已完成实名认证（Batch API要求）")
        print("4. 检查文件大小是否超过100MB限制")

if __name__ == "__main__":
    main()