#!/usr/bin/env python3
"""
情感分类脚本
使用智谱 GLM 对文本进行情感分类，输出格式为 {"sentiment": "正面"/"负面"/"中性", "score": 0-1之间的数字}
"""

import os
import requests
import json

# API 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 待分析的文本
texts_to_analyze = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐"
]

def analyze_sentiment(text: str) -> dict:
    """
    分析单条文本的情感

    Args:
        text: 待分析的文本

    Returns:
        dict: {"sentiment": "正面"/"负面"/"中性", "score": 0-1之间的数字}
    """
    prompt = f"""
    你是一个专业的情感分析专家。请分析以下文本的情感倾向，并按照要求的JSON格式返回结果。

    文本："{text}"

    请严格按照以下JSON格式返回，不要输出任何多余文字：
    {{"sentiment": "正面/负面/中性", "score": 0.95}}

    说明：
    - sentiment 只能是 "正面"、"负面" 或 "中性" 三者之一
    - score 是0到1之间的数字，表示情感倾向的置信度（越接近1越确定）
    - 请根据文本的情感强烈程度给出合适的score值
    """

    payload = {
        "model": "glm-5.3",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 100,
        "temperature": 0.1  # 降低随机性，提高输出一致性
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # 解析JSON响应
        sentiment_data = json.loads(content)

        # 验证字段
        if "sentiment" not in sentiment_data or "score" not in sentiment_data:
            raise ValueError("API返回的JSON格式不正确")

        # 标准化sentiment字段
        sentiment = sentiment_data["sentiment"].strip()
        if sentiment not in ["正面", "负面", "中性"]:
            # 如果返回的不是标准值，进行映射
            if sentiment in ["positive", "Positive", "好评", "积极"]:
                sentiment = "正面"
            elif sentiment in ["negative", "Negative", "差评", "消极"]:
                sentiment = "负面"
            elif sentiment in ["neutral", "Neutral", "一般", "中性"]:
                sentiment = "中性"
            else:
                # 如果无法识别，默认为中性
                sentiment = "中性"

        # 验证score字段
        score = float(sentiment_data["score"])
        if not 0 <= score <= 1:
            # 如果score不在0-1范围内，进行调整
            if score < 0:
                score = 0
            elif score > 1:
                score = 1

        return {
            "sentiment": sentiment,
            "score": round(score, 2)
        }

    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}")
        # 返回默认值
        return {
            "sentiment": "中性",
            "score": 0.0
        }
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        # 返回默认值
        return {
            "sentiment": "中性",
            "score": 0.0
        }
    except Exception as e:
        print(f"处理过程中发生错误: {e}")
        # 返回默认值
        return {
            "sentiment": "中性",
            "score": 0.0
        }

def main():
    """主函数：对所有文本进行情感分类"""
    print("开始情感分类...")
    print("=" * 50)

    results = []

    for i, text in enumerate(texts_to_analyze, 1):
        print(f"\n[{i}] 分析文本: {text}")

        result = analyze_sentiment(text)
        results.append({
            "text": text,
            "sentiment": result["sentiment"],
            "score": result["score"]
        })

        print(f"情感: {result['sentiment']}, 置信度: {result['score']}")

    # 输出最终结果
    print("\n" + "=" * 50)
    print("情感分析结果汇总:")
    print("=" * 50)

    for result in results:
        print(f"文本: {result['text']}")
        print(f"情感: {result['sentiment']}")
        print(f"置信度: {result['score']}")
        print("-" * 30)

    # 返回所有结果，方便其他脚本调用
    return results

if __name__ == "__main__":
    main()