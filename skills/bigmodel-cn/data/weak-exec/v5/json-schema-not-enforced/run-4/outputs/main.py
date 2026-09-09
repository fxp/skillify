#!/usr/bin/env python3
"""
使用智谱 GLM 进行情感分析的主程序
对给定的 3 条文本进行情感分类，输出格式严格符合数据库要求
"""

import os
import json
import re
import requests
from typing import List, Dict, Any


def analyze_sentiment(text: str, api_key: str) -> Dict[str, Any]:
    """
    使用智谱 GLM 对单条文本进行情感分析

    Args:
        text: 要分析的文本
        api_key: 智谱 API Key

    Returns:
        符合要求的情感分析结果: {"sentiment": "正面"/"负面"/"中性", "score": 0-1之间的数字}
    """
    # API 基础配置
    base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建系统提示词，要求输出特定格式的 JSON
    system_prompt = """你是一个专业的情感分析专家。
请分析以下文本的情感倾向，并严格按照以下 JSON 格式返回：
{"sentiment": "正面"/"负面"/"中性", "score": 0到1之间的数字}

sentiment 取值说明：
- "正面": 表示积极的情感（满意、推荐、高兴等）
- "负面": 表示消极的情感（抱怨、不满、失望等）
- "中性": 表示中立或无明显情感倾向

score 说明：
- 正面情感的分数范围：0.6-1.0
- 中性情感的分数范围：0.4-0.6
- 负面情感的分数范围：0.0-0.4

请只返回 JSON，不要添加任何解释文字。"""

    # 构建请求数据
    payload = {
        "model": "glm-4.7",  # 选择合适模型
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": text
            }
        ],
        "response_format": {"type": "json_object"},  # 使用 JSON 格式输出
        "temperature": 0.1,  # 降低随机性，提高输出一致性
        "max_tokens": 100
    }

    # 发送请求
    try:
        response = requests.post(
            base_url,
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        # 解析响应
        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # 清理响应内容（移除可能的 markdown 代码块标记）
        content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()

        # 解析 JSON
        sentiment_data = json.loads(content)

        # 验证输出格式
        if "sentiment" not in sentiment_data or "score" not in sentiment_data:
            raise ValueError(f"返回数据格式错误: {sentiment_data}")

        sentiment = sentiment_data["sentiment"]
        score = sentiment_data["score"]

        # 验证取值范围
        if sentiment not in ["正面", "负面", "中性"]:
            raise ValueError(f"sentiment 值错误: {sentiment}")

        if not isinstance(score, (int, float)) or score < 0 or score > 1:
            raise ValueError(f"score 值错误: {score}")

        return {
            "sentiment": sentiment,
            "score": float(score)
        }

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API 请求失败: {e}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON 解析失败: {e}")
    except Exception as e:
        raise RuntimeError(f"情感分析失败: {e}")


def main():
    """主函数"""
    # 测试文本
    test_texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    # 从环境变量读取 API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        print("例如: export ZHIPUAI_API_KEY='your_api_key_here'")
        exit(1)

    # 对每个文本进行情感分析
    results = []
    for text in test_texts:
        try:
            result = analyze_sentiment(text, api_key)
            results.append({
                "text": text,
                "sentiment": result["sentiment"],
                "score": result["score"]
            })
            print(f"文本: {text}")
            print(f"情感分析结果: {result}")
            print("-" * 50)
        except Exception as e:
            print(f"分析文本 '{text}' 时出错: {e}")
            continue

    # 输出最终结果（严格按照要求的格式）
    print("\n=== 最终分析结果 ===")
    for i, result in enumerate(results, 1):
        print(f"文本{i}: {result['text']}")
        print(f"结果: {json.dumps({'sentiment': result['sentiment'], 'score': result['score']}, ensure_ascii=False)}")

    # 将结果保存到文件
    output_file = "sentiment_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: {output_file}")


if __name__ == "__main__":
    main()