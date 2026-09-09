#!/usr/bin/env python3
import os
import json
import requests
import sys

def analyze_sentiment(text):
    """
    使用智谱GLM模型对文本进行情感分析
    返回: {"sentiment": "正面"/"负面"/"中性", "score": 0-1之间的数字}
    """
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    # API端点
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建请求数据
    payload = {
        "model": "glm-5.3",  # 使用通用旗舰模型
        "messages": [
            {
                "role": "system",
                "content": """你是专业的情感分析专家。请对用户提供的文本进行情感分析，并严格按照JSON格式返回结果。
返回格式要求：
- sentiment: 只能是"正面"、"负面"或"中性"中的一个
- score: 0到1之间的数字，表示情感强度（负面情感越负面分数越高，正面情感越正面分数越高，中性情感分数接近0.5）

请直接返回JSON，不要包含任何其他文字。示例：
{"sentiment": "正面", "score": 0.85}"""
            },
            {
                "role": "user",
                "content": f"请分析以下文本的情感：{text}"
            }
        ],
        "response_format": {"type": "json_object"},  # 要求返回JSON格式
        "temperature": 0.1,  # 降低随机性，确保输出稳定
        "max_tokens": 100   # 限制输出长度
    }

    try:
        # 发送请求
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        # 解析响应
        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # 解析JSON返回结果
        sentiment_data = json.loads(content)

        # 验证返回格式
        if "sentiment" not in sentiment_data or "score" not in sentiment_data:
            raise ValueError("返回的JSON格式不正确，缺少必要字段")

        # 验证sentiment取值
        valid_sentiments = ["正面", "负面", "中性"]
        if sentiment_data["sentiment"] not in valid_sentiments:
            raise ValueError(f"sentiment必须是{valid_sentiments}中的一个")

        # 验证score取值
        score = sentiment_data["score"]
        if not (0 <= score <= 1):
            raise ValueError("score必须是0到1之间的数字")

        return {
            "sentiment": sentiment_data["sentiment"],
            "score": float(score)
        }

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API请求失败: {e}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"解析JSON响应失败: {e}")
    except KeyError as e:
        raise RuntimeError(f"响应格式错误，缺少字段: {e}")

def main():
    """主函数：对3条文本进行情感分析"""
    # 待分析的文本列表
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    # 存储所有结果
    results = []

    print("开始情感分析...")
    print("-" * 50)

    # 对每条文本进行分析
    for i, text in enumerate(texts, 1):
        print(f"分析文本 {i}/{len(texts)}: {text}")
        try:
            result = analyze_sentiment(text)
            results.append({
                "text": text,
                "result": result
            })
            print(f"结果: 情感={result['sentiment']}, 置信度={result['score']:.2f}")
            print("-" * 30)
        except Exception as e:
            print(f"分析失败: {e}")
            results.append({
                "text": text,
                "error": str(e)
            })
            print("-" * 30)

    # 输出最终结果（严格符合要求的格式）
    print("\n最终分析结果:")
    final_results = []
    for item in results:
        if "error" in item:
            print(f"文本: {item['text']}")
            print(f"错误: {item['error']}")
        else:
            result = item['result']
            # 严格按照要求的格式输出
            output = {
                "sentiment": result["sentiment"],
                "score": result["score"]
            }
            final_results.append(output)
            print(json.dumps(output, ensure_ascii=False))

    # 将结果写入文件（可选）
    with open('sentiment_results.json', 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)

    print(f"\n共处理 {len(texts)} 条文本，成功分析 {len(final_results)} 条")

if __name__ == "__main__":
    main()