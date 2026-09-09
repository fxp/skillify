#!/usr/bin/env python3
"""
情感分类脚本
使用智谱 GLM API 对文本进行情感分类
输出格式：{"sentiment": "正面"/"负面"/"中性", "score": 0到1的数字}
"""

import json
import re
import os
import requests
from typing import List, Dict, Any

def classify_sentiment(text: str, max_retries: int = 3) -> Dict[str, Any]:
    """
    对单条文本进行情感分类

    Args:
        text: 要分类的文本
        max_retries: 最大重试次数

    Returns:
        包含 sentiment 和 score 的字典
    """
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    # 构建提示词，明确要求输出指定格式的 JSON
    system_prompt = """你是一个专业的情感分析专家。请严格按照以下 JSON 格式返回分析结果，不要输出任何其他文字：

{
    "sentiment": "正面"|"负面"|"中性",
    "score": 0到1之间的数字（表示置信度，越接近1表示越确定）
}

分类标准：
- "正面": 表达积极、满意、推荐等情绪
- "负面": 表达消极、不满、批评等情绪
- "中性": 客观描述，无明显情感倾向

score 应该根据文本情感的强烈程度来确定，例如：
- 明确的正面情感：0.8-1.0
- 明确的负面情感：0.8-1.0
- 轻微的正面/负面情感：0.6-0.8
- 中性情感：0.0-0.4
"""

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "glm-4.6",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 200,
        "temperature": 0.1  # 降低温度，提高输出的确定性
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()
            content = result["choices"][0]["message"]["content"]

            # 清理可能的 markdown 代码块标记
            content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()

            # 解析 JSON
            try:
                data = json.loads(content)

                # 验证字段
                if "sentiment" not in data or "score" not in data:
                    raise ValueError("缺少必要字段")

                sentiment = data["sentiment"]
                score = data["score"]

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
                    raise ValueError(f"JSON 解析失败: {content}") from e
                continue

        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise RuntimeError(f"API 请求失败: {str(e)}") from e
            continue

    raise RuntimeError(f"经过 {max_retries} 次尝试后仍未获得有效结果")

def main():
    """主函数：对指定的3条文本进行情感分类"""

    # 待分类的文本列表
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    results = []

    print("开始情感分类...")
    print("-" * 50)

    for i, text in enumerate(texts, 1):
        print(f"\n文本 {i}: {text}")
        try:
            result = classify_sentiment(text)
            results.append(result)
            print(f"分类结果: {result['sentiment']}, 置信度: {result['score']:.2f}")
        except Exception as e:
            print(f"分类失败: {str(e)}")
            # 添加一个默认结果，避免程序中断
            results.append({
                "sentiment": "中性",
                "score": 0.0
            })

    # 输出最终结果
    print("\n" + "=" * 50)
    print("最终分类结果:")
    print("=" * 50)

    for i, (text, result) in enumerate(zip(texts, results), 1):
        print(f"{i}. {text}")
        print(f"   情感: {result['sentiment']}")
        print(f"   置信度: {result['score']:.2f}")
        print()

    # 输出 JSON 格式结果（可用于入库）
    json_result = []
    for text, result in zip(texts, results):
        json_result.append({
            "text": text,
            "sentiment": result["sentiment"],
            "score": result["score"]
        })

    print("JSON 格式结果（可直接入库）:")
    print(json.dumps(json_result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()