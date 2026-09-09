#!/usr/bin/env python3
import os
import json
import requests
import time
from typing import List, Dict, Optional

# 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# 模型配置
PREFERRED_MODEL = "glm-5.3"  # 用户指定的最佳模型
BATCH_SUPPORTED_MODELS = [
    "glm-5.1", "glm-5-turbo", "glm-4", "glm-4-0520", "glm-4-plus",
    "glm-4-long", "glm-4-plus-0111", "glm-4-air", "glm-4-air-0111",
    "glm-4-air-250414", "glm-4-flash", "glm-4-flashx-250414",
    "glm-3-turbo", "glm-4v", "glm-4v-plus", "glm-5v-turbo",
    "glm-4v-plus-0111", "cogview-3", "cogview-3-plus",
    "cogview-4-250304", "embedding-2", "embedding-3",
    "cogvideox", "cogvideox-2"
]

def read_comments(file_path: str) -> List[str]:
    """读取评论文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        comments = [line.strip() for line in f if line.strip()]
    return comments

def create_batch_jsonl(comments: List[str]) -> str:
    """创建 Batch API 所需的 JSONL 格式数据"""
    jsonl_lines = []
    for i, comment in enumerate(comments, 1):
        # 检查 Batch 是否支持 glm-5.3
        if PREFERRED_MODEL in BATCH_SUPPORTED_MODELS:
            model = PREFERRED_MODEL
        else:
            # 如果不支持，使用 glm-4-plus 作为替代（在 Batch 支持列表中）
            model = "glm-4-plus"
            print(f"警告: {PREFERRED_MODEL} 不在 Batch API 支持列表中，降级使用 {model}")

        jsonl_line = {
            "custom_id": f"request-{i:04d}",  # custom_id 最少需要 6 个字符
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """你是一个专业的情感分类助手。请对用户评论进行情感分类，返回 JSON 格式结果。
分类标准：
- positive: 正面评价（满意、推荐、超出预期等）
- negative: 负面评价（抱怨、失望、质量问题等）
- neutral: 中性评价（一般、客观描述等）

返回格式：
{"sentiment": "positive/negative/neutral", "reason": "简要分类原因"}"""
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,  # 降低随机性，提高一致性
                "max_tokens": 200
            }
        }
        jsonl_lines.append(json.dumps(jsonl_line, ensure_ascii=False))

    return '\n'.join(jsonl_lines)

def upload_batch_file(jsonl_content: str) -> Optional[str]:
    """上传 JSONL 文件到智谱平台"""
    try:
        files = {"file": ("batch_requests.jsonl", jsonl_content.encode('utf-8'), "application/jsonl")}
        data = {"purpose": "batch"}

        response = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=HEADERS,
            files=files,
            data=data
        )
        response.raise_for_status()
        file_info = response.json()
        print(f"文件上传成功: {file_info['id']}")
        return file_info["id"]
    except requests.exceptions.RequestException as e:
        print(f"文件上传失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"错误详情: {e.response.text}")
        return None

def create_batch_task(input_file_id: str) -> Optional[str]:
    """创建 Batch 任务"""
    try:
        payload = {
            "input_file_id": input_file_id,
            "endpoint": "/v4/chat/completions",
            "auto_delete_input_file": True,
            "metadata": {
                "description": "用户评论情感分析任务",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        }

        response = requests.post(
            f"{BASE_URL}/paas/v4/batches",
            headers={**HEADERS, "Content-Type": "application/json"},
            json=payload
        )
        response.raise_for_status()
        batch_info = response.json()

        print(f"Batch 任务创建成功!")
        print(f"任务 ID: {batch_info['id']}")
        print(f"任务状态: {batch_info['status']}")
        print(f"请求数量: {batch_info['request_counts']['total']}")

        return batch_info["id"]
    except requests.exceptions.RequestException as e:
        print(f"创建 Batch 任务失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"错误详情: {e.response.text}")
        return None

def check_model_availability() -> str:
    """检查模型是否可用，返回实际使用的模型"""
    if PREFERRED_MODEL in BATCH_SUPPORTED_MODELS:
        return PREFERRED_MODEL
    else:
        print(f"警告: {PREFERRED_MODEL} 不在 Batch API 支持列表中")
        # 返回 Batch 支持的最佳替代模型
        alternative_models = ["glm-4-plus", "glm-4-flash", "glm-4-air"]
        for model in alternative_models:
            if model in BATCH_SUPPORTED_MODELS:
                print(f"使用替代模型: {model}")
                return model
        return "glm-4-plus"  # 默认值

def main():
    print("开始情感分类任务...")

    # 检查 API Key
    if not API_KEY:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 检查模型可用性
    actual_model = check_model_availability()
    print(f"将使用模型: {actual_model}")

    # 读取评论
    comments_file = "../fixtures/comments.txt"
    try:
        comments = read_comments(comments_file)
        print(f"读取到 {len(comments)} 条评论")
        for i, comment in enumerate(comments[:3], 1):  # 显示前3条评论
            print(f"  {i}. {comment}")
        if len(comments) > 3:
            print(f"  ... 还有 {len(comments) - 3} 条评论")
    except FileNotFoundError:
        print(f"错误: 找不到评论文件 {comments_file}")
        return

    # 创建 JSONL 内容
    print("\n创建 Batch 请求文件...")
    jsonl_content = create_batch_jsonl(comments)
    print(f"JSONL 内容已生成，包含 {len(comments)} 个请求")

    # 上传文件
    print("\n上传文件到智谱平台...")
    input_file_id = upload_batch_file(jsonl_content)
    if not input_file_id:
        print("文件上传失败，退出程序")
        return

    # 创建 Batch 任务
    print("\n创建 Batch 任务...")
    batch_id = create_batch_task(input_file_id)
    if not batch_id:
        print("创建任务失败，退出程序")
        return

    print(f"\n✅ 任务创建完成！")
    print(f"📋 Batch ID: {batch_id}")
    print(f"🔍 你可以通过以下命令查询任务状态:")
    print(f"   curl -H 'Authorization: Bearer {API_KEY}' '{BASE_URL}/paas/v4/batches/{batch_id}'")
    print("\n💡 提示: Batch 任务预计在 24 小时内完成，请稍后查询结果")

if __name__ == "__main__":
    main()