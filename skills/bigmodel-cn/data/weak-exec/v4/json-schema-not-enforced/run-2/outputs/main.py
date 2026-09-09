#!/usr/bin/env python3
"""
情感分析脚本
使用智谱GLM模型对文本进行情感分类
"""

import os
import json
import requests

def analyze_sentiment(text: str) -> dict:
    """
    对单条文本进行情感分析

    Args:
        text: 要分析的文本

    Returns:
        dict: {"sentiment": "正面"/"负面"/"中性", "score": 0到1之间的数字}
    """
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 构建请求payload
    payload = {
        "model": "glm-5.3",  # 使用旗舰模型，情感分析准确率更高
        "messages": [
            {
                "role": "system",
                "content": """你是一个专业的情感分析专家。请严格按照以下JSON格式返回情感分析结果：
{
    "sentiment": "正面/负面/中性",
    "score": 0.0到1.0之间的数字
}

sentiment说明：
- "正面": 表示积极、正面、赞美的情感
- "负面": 表示消极、负面、批评的情感
- "中性": 表示中立、客观、没有明显倾向的情感

score说明：
- 正面情感：score应该在0.6到1.0之间，越接近1.0表示越正面
- 负面情感：score应该在0.0到0.4之间，越接近0.0表示越负面
- 中性情感：score应该在0.4到0.6之间，越接近0.5表示越中性

请只返回JSON，不要包含其他任何文字。"""
            },
            {
                "role": "user",
                "content": text
            }
        ],
        "response_format": {"type": "json_object"},  # 强制返回JSON格式
        "temperature": 0.1,  # 降低随机性，提高一致性
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

        # 解析JSON响应
        sentiment_data = json.loads(content)

        # 验证返回的格式是否正确
        if "sentiment" not in sentiment_data or "score" not in sentiment_data:
            raise ValueError("返回的JSON格式不正确")

        # 验证sentiment的取值
        valid_sentiments = ["正面", "负面", "中性"]
        if sentiment_data["sentiment"] not in valid_sentiments:
            raise ValueError(f"sentiment必须是{valid_sentiments}之一")

        # 验证score的范围
        score = sentiment_data["score"]
        if not (0.0 <= score <= 1.0):
            raise ValueError("score必须在0.0到1.0之间")

        return {
            "sentiment": sentiment_data["sentiment"],
            "score": round(score, 3)  # 保留3位小数
        }

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API请求失败: {e}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON解析失败: {e}")
    except KeyError as e:
        raise RuntimeError(f"响应格式错误，缺少字段: {e}")


def main():
    """主函数：对3条文本进行情感分析"""

    # 要分析的文本列表
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    print("开始情感分析...")
    print("=" * 50)

    results = []

    for i, text in enumerate(texts, 1):
        print(f"\n分析文本 {i}: {text}")
        try:
            result = analyze_sentiment(text)
            results.append(result)
            print(f"结果: {result}")
        except Exception as e:
            print(f"分析失败: {e}")
            # 使用默认值填充
            results.append({
                "sentiment": "中性",
                "score": 0.5
            })

    # 输出最终结果
    print("\n" + "=" * 50)
    print("最终分析结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    return results


if __name__ == "__main__":
    main()