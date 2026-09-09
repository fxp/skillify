#!/usr/bin/env python3
"""
情感分类脚本 - 使用智谱 GLM API 对文本进行情感分类
"""

import os
import json
import requests
import re
from typing import List, Dict, Union

# API 配置
BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

# 模型选择
MODEL = "glm-4.6"  # 使用 glm-4.6 进行情感分类

# 情感分类提示词
SCHEMA_HINT = """
你是一个专业的情感分类助手。请对给定的文本进行情感分析，并严格按照 JSON 格式输出结果。

输出格式要求：
{
    "sentiment": "正面"|"负面"|"中性",
    "score": 0到1之间的数字
}

其中：
- sentiment: 只能是"正面"、"负面"或"中性"中的一个
- score: 表示情感强度的分数，范围在0到1之间
  - 正面文本的分数应该在 0.5 到 1 之间，越正面分数越高
  - 负面文本的分数应该在 0 到 0.5 之间，越负面分数越低
  - 中性文本的分数应该在 0.4 到 0.6 之间

请直接输出 JSON，不要包含任何其他解释文字。
"""

def classify_sentiment(text: str, max_retries: int = 3) -> Dict[str, Union[str, float]]:
    """
    对单条文本进行情感分类

    Args:
        text: 要分类的文本
        max_retries: 最大重试次数

    Returns:
        包含 sentiment 和 score 的字典

    Raises:
        RuntimeError: 如果多次尝试后仍未获得有效结果
        requests.exceptions.RequestException: API 调用失败
    """
    if not API_KEY:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    # 构建请求数据
    payload = {
        "model": MODEL,
        "max_tokens": 200,
        "thinking": {"type": "disabled"},  # 禁用思考模式，避免消耗 token
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SCHEMA_HINT},
            {"role": "user", "content": f"请对以下文本进行情感分类：\n\n{text}"}
        ]
    }

    # 重试机制
    for attempt in range(max_retries):
        try:
            response = requests.post(
                BASE_URL,
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()

            # 提取回复内容
            content = result["choices"][0]["message"].get("content", "")

            # 清理代码块标记
            content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()

            # 解析 JSON
            try:
                parsed_data = json.loads(content)

                # 验证结果格式
                if "sentiment" not in parsed_data or "score" not in parsed_data:
                    raise ValueError("缺少必要字段")

                sentiment = parsed_data["sentiment"]
                score = parsed_data["score"]

                # 验证 sentiment 值
                if sentiment not in ["正面", "负面", "中性"]:
                    raise ValueError(f"无效的 sentiment 值: {sentiment}")

                # 验证 score 值
                if not isinstance(score, (int, float)) or score < 0 or score > 1:
                    raise ValueError(f"无效的 score 值: {score}")

                return {
                    "sentiment": sentiment,
                    "score": float(score)
                }

            except json.JSONDecodeError as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"JSON 解析失败: {e}")
                continue

        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            print(f"API 调用失败，重试 {attempt + 1}/{max_retries}: {e}")
            continue

    raise RuntimeError(f"多次尝试后仍未获得有效结果")

def batch_classify(texts: List[str]) -> List[Dict[str, Union[str, float]]]:
    """
    批量对文本进行情感分类

    Args:
        texts: 要分类的文本列表

    Returns:
        分类结果列表，每个元素是一个包含 sentiment 和 score 的字典
    """
    results = []

    for i, text in enumerate(texts):
        print(f"正在处理文本 {i+1}/{len(texts)}: {text[:50]}...")
        try:
            result = classify_sentiment(text)
            results.append(result)
            print(f"分类结果: {result}")
        except Exception as e:
            print(f"处理文本失败: {e}")
            # 使用默认值作为兜底
            results.append({
                "sentiment": "中性",
                "score": 0.5
            })

    return results

def main():
    """主函数"""
    # 测试文本
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    print("开始情感分类...")
    print("=" * 50)

    # 执行批量分类
    results = batch_classify(texts)

    # 输出最终结果
    print("\n最终结果:")
    print("=" * 50)

    for i, (text, result) in enumerate(zip(texts, results)):
        print(f"\n文本 {i+1}: {text}")
        print(f"情感: {result['sentiment']}")
        print(f"分数: {result['score']}")

    # 输出 JSON 格式结果
    output_file = "/tmp/sentiment_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_file}")

if __name__ == "__main__":
    main()