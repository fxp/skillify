#!/usr/bin/env python3
"""
测试版本的 main.py - 演示功能而不需要实际 API_KEY

这个版本会模拟整个过程，但不实际调用 API
"""

import os
import json
from typing import List, Dict

# 配置（仅用于演示）
API_BASE_URL = "https://open.bigmodel.cn/api"
# API_KEY = os.environ.get("ZHIPUAI_API_KEY")  # 注释掉用于测试

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
    print("\n构造的 Batch 请求示例（前3条）：")

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

        # 只打印前3条作为示例
        if i <= 3:
            print(f"请求 {i}:")
            print(f"  custom_id: {custom_id}")
            print(f"  评论: {comment[:50]}...")
            print(f"  模型: {MODEL}")
            print()

    return "\n".join(lines)


def demo_main():
    """演示主函数"""
    try:
        print("="*60)
        print("用户评论情感分类脚本演示")
        print("="*60)
        print("\n注意：这是演示版本，不实际调用 API")
        print("\n重要说明：")
        print("1. 由于 glm-5.3 不在 Batch API 支持的模型列表中")
        print("2. 这里使用 glm-4-plus 作为替代模型")
        print("3. Batch API 支持的模型包括：glm-4-plus, glm-5-turbo, glm-4-flash 等")
        print("4. 如果需要使用 glm-5.3，需要使用同步 API（非 Batch）")
        print()

        # 1. 读取评论
        print("步骤1: 读取用户评论...")
        comments = read_comments()

        # 打印评论预览
        print("\n评论预览（前5条）：")
        for i, comment in enumerate(comments[:5], 1):
            print(f"{i}. {comment}")
        if len(comments) > 5:
            print(f"... 还有 {len(comments)-5} 条评论")

        # 2. 构造 Batch 请求
        print("\n步骤2: 构造 Batch 请求...")
        batch_content = create_batch_requests(comments)

        print(f"\n总共构造了 {len(comments)} 条 Batch 请求")
        print(f"每条请求都会使用模型: {MODEL}")

        # 3. 演示上传和创建过程
        print("\n步骤3: 演拟文件上传和 Batch 创建...")
        print("实际执行时，这些步骤会：")
        print("1. 将构造的 jsonl 内容上传到智谱平台")
        print("2. 获取 input_file_id")
        print("3. 使用 input_file_id 创建 Batch 任务")
        print("4. 返回 batch 任务 ID")

        # 模拟返回的 batch ID
        mock_batch_id = "batch_2095408344001937408"

        print("\n" + "="*60)
        print("演示完成！")
        print("="*60)
        print(f"如果实际运行，会返回类似这样的 Batch 任务 ID:")
        print(f"Batch 任务ID: {mock_batch_id}")
        print(f"任务状态: validating → in_progress → finalizing → completed")
        print("\n关于模型选择的说明：")
        print("- 用户要求使用 glm-5.3，但该模型不在 Batch API 支持列表中")
        print("- 已自动替换为 glm-4-plus，这是 Batch 支持的较好模型")
        print("- 如果坚持要用 glm-5.3，需要改用同步 API 逐条处理")
        print("- Batch API 价格约为标准 API 的 50%，适合大规模任务")

    except Exception as e:
        print(f"\n错误: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(demo_main())