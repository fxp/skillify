#!/usr/bin/env python3
"""
情感分类脚本
使用智谱 GLM 模型对文本进行情感分析，输出格式：{"sentiment": "正面"/"负面"/"中性", "score": 0-1之间的数字}
"""

import os
import json
import requests

# API 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 如果没有 API Key，使用模拟数据
if not API_KEY:
    print("警告：未设置 ZHIPUAI_API_KEY 环境变量，使用模拟数据")
    SAMPLE_TEXTS = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    # 模拟情感分析结果
    mock_results = [
        {"sentiment": "负面", "score": 0.1},
        {"sentiment": "中性", "score": 0.5},
        {"sentiment": "正面", "score": 0.9}
    ]

    # 输出结果
    for i, (text, result) in enumerate(zip(SAMPLE_TEXTS, mock_results)):
        print(f"文本 {i+1}: {text}")
        print(f"情感分析结果: {json.dumps(result, ensure_ascii=False)}")
        print()

    print("注意：这是模拟数据。请设置 ZHIPUAI_API_KEY 环境变量以使用真实 API。")
    exit(0)

def analyze_sentiment(text):
    """
    分析单条文本的情感

    Args:
        text (str): 要分析的文本

    Returns:
        dict: 情感分析结果，格式为 {"sentiment": "正面"/"负面"/"中性", "score": 0-1之间的数字}
    """
    # 构建请求 payload
    payload = {
        "model": "glm-5.3",  # 使用最新的旗舰模型
        "messages": [
            {
                "role": "system",
                "content": """你是一个专业的情感分析专家。请对用户输入的文本进行情感分析，严格按照以下格式返回JSON：
{
    "sentiment": "正面" | "负面" | "中性",
    "score": 0.0-1.0之间的数字（表示情感强度，1.0为最强）
}
判断标准：
- 正面：表达满意、推荐、赞扬等积极情感
- 负面：表达不满、批评、抱怨等消极情感
- 中性：客观描述，无明显情感倾向
score值表示情感的强烈程度，例如：
- 强烈负面（如愤怒、极度不满）：0.1-0.3
- 轻微负面（如轻微不满）：0.3-0.5
- 中性：0.5
- 轻微正面（如还行、可以）：0.5-0.7
- 强烈正面（如非常满意、强烈推荐）：0.7-0.9
请只返回JSON，不要包含其他文字。"""
            },
            {
                "role": "user",
                "content": text
            }
        ],
        "response_format": {"type": "json_object"},  # 要求返回JSON格式
        "temperature": 0.1,  # 降低随机性，确保结果稳定
        "max_tokens": 100  # 限制输出长度
    }

    try:
        # 发送请求
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        # 解析响应
        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # 解析JSON
        sentiment_data = json.loads(content)

        # 验证结果格式
        if "sentiment" not in sentiment_data or "score" not in sentiment_data:
            raise ValueError("API返回的格式不正确")

        # 确保sentiment是有效值
        valid_sentiments = ["正面", "负面", "中性"]
        if sentiment_data["sentiment"] not in valid_sentiments:
            raise ValueError(f"无效的情感值: {sentiment_data['sentiment']}")

        # 确保score在0-1之间
        score = float(sentiment_data["score"])
        if not (0.0 <= score <= 1.0):
            raise ValueError(f"无效的score值: {score}")

        return {
            "sentiment": sentiment_data["sentiment"],
            "score": score
        }

    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        return None
    except Exception as e:
        print(f"情感分析失败: {e}")
        return None

def main():
    """主函数"""
    # 要分析的文本列表
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    # 分析结果列表
    results = []

    print("开始情感分析...")

    # 逐条分析文本
    for i, text in enumerate(texts):
        print(f"\n分析文本 {i+1}: {text}")

        result = analyze_sentiment(text)

        if result:
            results.append(result)
            print(f"结果: {json.dumps(result, ensure_ascii=False)}")
        else:
            # 如果分析失败，使用默认值
            default_result = {"sentiment": "中性", "score": 0.5}
            results.append(default_result)
            print(f"使用默认结果: {json.dumps(default_result, ensure_ascii=False)}")

    # 输出最终结果（保持原有的输出格式，以便直接入库）
    print("\n=== 最终结果 ===")
    for i, (text, result) in enumerate(zip(texts, results)):
        print(f"文本 {i+1}: {text}")
        print(f"情感分析结果: {json.dumps(result, ensure_ascii=False)}")

    # 可以选择将结果写入文件（如果需要）
    # with open("sentiment_results.json", "w", encoding="utf-8") as f:
    #     json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()