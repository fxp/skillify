import os
import requests
import json

def analyze_sentiment(text):
    """对单条文本进行情感分析"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置 ZHIPUAI_API_KEY 环境变量")

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    payload = {
        "model": "glm-5.3",
        "messages": [
            {
                "role": "system",
                "content": """你是一个专业的情感分析助手。请对用户输入的文本进行情感分析，并严格按照指定的JSON格式返回结果。

返回格式要求：
{
    "sentiment": "正面"|"负面"|"中性",
    "score": 0到1之间的数字
}

情感分类标准：
- "正面": 文本表达积极、满意、赞扬等正面情感，score应该较高（>0.6）
- "负面": 文本表达消极、不满、批评等负面情感，score应该较低（<0.4）
- "中性": 文本表达中性、客观或情感不明确，score应该在中间值（0.4-0.6之间）

score是情感强度的置信度，越接近1表示情感越强烈，越接近0表示情感越微弱。请确保输出的JSON格式正确，不要包含任何其他文本。"""
            },
            {
                "role": "user",
                "content": text
            }
        ],
        "temperature": 0.1,
        "max_tokens": 100,
        "response_format": {
            "type": "json_object"
        }
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    result = response.json()
    content = result["choices"][0]["message"]["content"]

    # 解析JSON响应
    try:
        sentiment_data = json.loads(content)
        return {
            "sentiment": sentiment_data.get("sentiment"),
            "score": sentiment_data.get("score")
        }
    except json.JSONDecodeError:
        # 如果解析失败，尝试从响应中提取JSON
        import re
        json_match = re.search(r'\{[^}]+\}', content)
        if json_match:
            sentiment_data = json.loads(json_match.group())
            return {
                "sentiment": sentiment_data.get("sentiment"),
                "score": sentiment_data.get("score")
            }
        else:
            raise ValueError("无法解析模型返回的情感分析结果")

def main():
    # 待分析的文本列表
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    # 分析每条文本的情感
    results = []
    for text in texts:
        print(f"正在分析文本: {text}")
        result = analyze_sentiment(text)
        results.append({
            "text": text,
            "sentiment": result["sentiment"],
            "score": result["score"]
        })
        print(f"分析结果: {result}")

    # 输出最终结果
    print("\n=== 情感分析结果 ===")
    for i, result in enumerate(results, 1):
        print(f"{i}. 文本: {result['text']}")
        print(f"   情感: {result['sentiment']}")
        print(f"   置信度: {result['score']}")
        print()

if __name__ == "__main__":
    main()