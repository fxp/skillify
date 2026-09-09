#!/usr/bin/env python3
"""
情感分类脚本
使用智谱 GLM 对文本进行情感分类
输出格式：{"sentiment": "正面"/"负面"/"中性", "score": 0到1之间的数字}
"""

import os
import requests
import json
import sys
import re


def classify_sentiment(text, model="glm-5.3"):
    """
    对单个文本进行情感分类

    Args:
        text (str): 要分类的文本
        model (str): 使用的模型，默认为 glm-5.3

    Returns:
        dict: {"sentiment": "正面"/"负面"/"中性", "score": 0到1之间的数字}
    """
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("未设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 构建提示词，明确要求输出 JSON 格式
    system_prompt = """你是一个专业的情感分类助手。请对用户的文本进行情感分析，并严格按照 JSON 格式返回结果。

返回格式必须完全符合：
{
    "sentiment": "正面" | "负面" | "中性",
    "score": 0到1之间的数字
}

其中：
- sentiment 只能是三个值之一："正面"、"负面"、"中性"
- score 是置信度分数，范围 0-1，1 表示完全确定，0 表示完全不确定

请确保输出是有效的 JSON，不要包含任何其他文字。"""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请对以下文本进行情感分类：\n\n{text}"}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,  # 较低的温度，使输出更稳定
        "max_tokens": 200
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()

        # 提取模型的回复内容
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        # 解析 JSON 响应
        try:
            # 尝试直接解析
            sentiment_data = json.loads(content)
        except json.JSONDecodeError:
            # 如果直接解析失败，尝试提取 JSON 部分
            json_match = re.search(r'\{[^}]+\}', content)
            if json_match:
                sentiment_data = json.loads(json_match.group())
            else:
                # 如果找不到 JSON，返回默认值
                sentiment_data = {
                    "sentiment": "中性",
                    "score": 0.5
                }

        # 验证并标准化输出格式
        sentiment = sentiment_data.get("sentiment", "中性")
        score = sentiment_data.get("score", 0.5)

        # 确保 sentiment 是有效值
        if sentiment not in ["正面", "负面", "中性"]:
            sentiment = "中性"

        # 确保 score 是 0-1 之间的数字
        try:
            score = float(score)
            score = max(0.0, min(1.0, score))  # 限制在 0-1 范围内
        except (ValueError, TypeError):
            score = 0.5

        return {
            "sentiment": sentiment,
            "score": score
        }

    except requests.exceptions.RequestException as e:
        raise Exception(f"API 调用失败: {e}")


def main():
    """主函数：对三条文本进行情感分类"""

    # 待分类的文本
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    print("开始情感分类...")
    print("=" * 50)

    results = []

    for i, text in enumerate(texts, 1):
        print(f"\n文本 {i}: {text}")
        print("-" * 30)

        try:
            result = classify_sentiment(text)
            results.append(result)
            print(f"情感: {result['sentiment']}")
            print(f"置信度: {result['score']:.3f}")

        except Exception as e:
            print(f"分类失败: {e}")
            # 添加默认结果以保持格式一致
            results.append({
                "sentiment": "中性",
                "score": 0.5
            })

    # 输出最终结果
    print("\n" + "=" * 50)
    print("分类结果汇总:")
    print("=" * 50)

    # 输出 JSON 格式的结果
    output_json = json.dumps(results, ensure_ascii=False, indent=2)
    print(output_json)

    # 验证结果格式
    print("\n" + "=" * 50)
    print("格式验证:")
    all_valid = True

    for i, result in enumerate(results, 1):
        is_valid = (
            isinstance(result, dict) and
            "sentiment" in result and
            "score" in result and
            result["sentiment"] in ["正面", "负面", "中性"] and
            isinstance(result["score"], (int, float)) and
            0 <= result["score"] <= 1
        )

        if not is_valid:
            print(f"❌ 结果 {i} 格式错误: {result}")
            all_valid = False
        else:
            print(f"✅ 结果 {i} 格式正确: {result}")

    if all_valid:
        print("\n🎉 所有结果格式正确，可以直接入库！")
    else:
        print("\n⚠️ 部分结果格式错误，请检查后重试。")
        sys.exit(1)


if __name__ == "__main__":
    main()