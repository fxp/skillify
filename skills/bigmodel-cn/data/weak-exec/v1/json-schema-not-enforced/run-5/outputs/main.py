#!/usr/bin/env python3
import os
import json
import requests

def analyze_sentiment(text):
    """使用智谱 GLM API 分析文本情感"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "glm-5.3",
        "messages": [
            {
                "role": "system",
                "content": """你是一个专业的情感分析专家。请严格按照指定的 JSON 格式分析文本情感，只返回 JSON，不要输出其他任何文字。
JSON 格式要求：
{
    "sentiment": "正面"/"负面"/"中性",
    "score": 0 到 1 之间的数字
}

说明：
- "sentiment" 只能是三个值之一："正面"、"负面"、"中性"
- "score" 是置信度分数，0 表示完全不相关，1 表示完全确定
- 对于正面文本，score 应该 > 0.6
- 对于负面文本，score 应该 > 0.6
- 对于中性文本，score 应该 > 0.5
"""
            },
            {
                "role": "user",
                "content": f"请分析以下文本的情感：{text}"
            }
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,  # 降低随机性，确保输出稳定
        "max_tokens": 100
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()

        # 提取返回的 JSON 内容
        content = result["choices"][0]["message"]["content"]
        # 解析 JSON
        sentiment_data = json.loads(content)

        # 验证输出格式
        if "sentiment" not in sentiment_data or "score" not in sentiment_data:
            raise ValueError("返回的 JSON 格式不正确")

        sentiment = sentiment_data["sentiment"]
        score = float(sentiment_data["score"])

        # 验证 sentiment 值
        if sentiment not in ["正面", "负面", "中性"]:
            raise ValueError(f"sentiment 值必须是'正面'/'负面'/'中性'之一，实际得到：{sentiment}")

        # 验证 score 值
        if not (0 <= score <= 1):
            raise ValueError(f"score 必须是 0 到 1 之间的数字，实际得到：{score}")

        return {
            "sentiment": sentiment,
            "score": score
        }

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API 请求失败：{e}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON 解析失败：{e}")
    except KeyError as e:
        raise RuntimeError(f"响应格式错误：缺少字段 {e}")

def main():
    """主函数：分析 3 条文本的情感"""
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    results = []
    for i, text in enumerate(texts, 1):
        print(f"正在分析第 {i} 条文本...")
        try:
            result = analyze_sentiment(text)
            results.append(result)
            print(f"分析结果：{result}")
        except Exception as e:
            print(f"分析失败：{e}")
            # 提供一个默认值作为降级
            results.append({
                "sentiment": "中性",  # 默认值
                "score": 0.5
            })

    # 输出最终结果
    print("\n=== 最终分析结果 ===")
    for i, (text, result) in enumerate(zip(texts, results), 1):
        print(f"文本 {i}: {text}")
        print(f"情感: {result['sentiment']}, 置信度: {result['score']:.2f}")
        print("-" * 50)

    # 保存结果到 JSON 文件（可选）
    with open('sentiment_results.json', 'w', encoding='utf-8') as f:
        json.dump({
            "texts": texts,
            "results": results
        }, f, ensure_ascii=False, indent=2)

    print("\n结果已保存到 sentiment_results.json")

if __name__ == "__main__":
    main()