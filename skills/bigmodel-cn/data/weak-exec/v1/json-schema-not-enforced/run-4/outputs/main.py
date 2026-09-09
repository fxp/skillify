#!/usr/bin/env python3
import os
import requests
import json
import sys


def analyze_sentiment(text: str, api_key: str) -> dict:
    """
    使用智谱GLM模型进行情感分析

    Args:
        text: 要分析的文本
        api_key: 智谱AI API Key

    Returns:
        dict: {"sentiment": "正面"/"负面"/"中性", "score": 0-1之间的数字}
    """
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 构建提示词，要求模型严格按照指定JSON格式返回
    system_prompt = """你是专业的情感分析专家。请对用户输入的文本进行情感分析，并严格按照以下JSON格式返回结果，不要输出任何多余文字：

{"sentiment": "正面"/"负面"/"中性", "score": 0.0到1.0之间的数字}

说明：
- sentiment: 必须是"正面"、"负面"或"中性"之一
- score: 表示情感强度的置信度，0.0表示完全没有该情感，1.0表示情感强度极高
请直接返回JSON，不要有任何解释文字。"""

    payload = {
        "model": "glm-5.3",  # 使用GLM-5.3模型
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        "response_format": {"type": "json_object"},  # 强制返回JSON格式
        "temperature": 0.1,  # 降低随机性，确保输出稳定
        "max_tokens": 100
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # 解析JSON返回
        sentiment_data = json.loads(content)

        # 验证返回格式
        sentiment = sentiment_data.get("sentiment", "中性")
        score = sentiment_data.get("score", 0.5)

        # 确保sentiment是有效值
        if sentiment not in ["正面", "负面", "中性"]:
            sentiment = "中性"

        # 确保score是数字且在0-1之间
        try:
            score = float(score)
            score = max(0.0, min(1.0, score))  # 限制在0-1范围内
        except (ValueError, TypeError):
            score = 0.5

        return {
            "sentiment": sentiment,
            "score": score
        }

    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}", file=sys.stderr)
        # 返回默认值而不是抛出异常，保证程序继续运行
        return {"sentiment": "中性", "score": 0.5}
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}", file=sys.stderr)
        return {"sentiment": "中性", "score": 0.5}
    except Exception as e:
        print(f"未知错误: {e}", file=sys.stderr)
        return {"sentiment": "中性", "score": 0.5}


def main():
    # 从环境变量读取API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")

    if not api_key:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        sys.exit(1)

    # 待分析的文本列表
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    # 分析每条文本的情感
    results = []
    for text in texts:
        result = analyze_sentiment(text, api_key)
        results.append(result)

    # 输出结果
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()