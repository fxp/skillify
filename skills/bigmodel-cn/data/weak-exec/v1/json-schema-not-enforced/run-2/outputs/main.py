import os
import json
import requests

# API配置
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

def analyze_sentiment(text):
    """
    使用智谱GLM模型对文本进行情感分析

    Args:
        text (str): 要分析的文本

    Returns:
        dict: {"sentiment": "正面"/"负面"/"中性", "score": 0到1之间的数字}
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # 构建prompt，要求模型严格按照指定格式返回
    prompt = f"""请对以下文本进行情感分析，严格按照JSON格式返回：
{{
    "sentiment": "正面"/"负面"/"中性",
    "score": 0到1之间的数字（表示情感强度，1表示最强）
}}

文本内容：{text}

请只返回JSON格式的结果，不要包含其他任何文字或解释。"""

    payload = {
        "model": "glm-5.3",  # 使用通用对话模型
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "response_format": {"type": "json_object"},  # 确保返回JSON
        "max_tokens": 100,  # 足够返回结果即可
        "temperature": 0.1  # 降低随机性，确保格式一致
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        # 解析响应
        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # 尝试解析JSON
        sentiment_data = json.loads(content)

        # 验证返回的格式是否正确
        if "sentiment" not in sentiment_data or "score" not in sentiment_data:
            raise ValueError("返回的JSON格式不正确")

        sentiment = sentiment_data["sentiment"]
        score = sentiment_data["score"]

        # 验证sentiment的值
        if sentiment not in ["正面", "负面", "中性"]:
            raise ValueError(f"无效的情感类型: {sentiment}")

        # 验证score的值
        score = float(score)
        if not (0 <= score <= 1):
            raise ValueError(f"无效的score值: {score}，应该在0到1之间")

        return {
            "sentiment": sentiment,
            "score": score
        }

    except requests.exceptions.RequestException as e:
        raise Exception(f"API请求失败: {str(e)}")
    except json.JSONDecodeError as e:
        raise Exception(f"JSON解析失败: {str(e)}")
    except Exception as e:
        raise Exception(f"情感分析失败: {str(e)}")

def main():
    """主函数：对3条文本进行情感分类"""

    # 待分析的文本列表
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    # 存储结果
    results = []

    print("开始情感分析...")
    print("-" * 50)

    for i, text in enumerate(texts, 1):
        print(f"分析第{i}条文本: {text}")
        try:
            result = analyze_sentiment(text)
            results.append({
                "text": text,
                "sentiment": result["sentiment"],
                "score": result["score"]
            })
            print(f"结果: 情感={result['sentiment']}, 强度={result['score']:.2f}")
            print("-" * 50)
        except Exception as e:
            print(f"分析失败: {str(e)}")
            results.append({
                "text": text,
                "sentiment": "分析失败",
                "score": 0.0
            })
            print("-" * 50)

    # 输出最终结果
    print("\n最终结果:")
    print("=" * 50)
    for i, result in enumerate(results, 1):
        print(f"{i}. 文本: {result['text']}")
        print(f"   情感: {result['sentiment']}")
        print(f"   强度: {result['score']}")
        print()

    # 严格按照要求的格式输出
    final_output = []
    for result in results:
        if result['sentiment'] != "分析失败":
            final_output.append({
                "sentiment": result['sentiment'],
                "score": result['score']
            })

    # 保存到文件（如果需要）
    output_file = "sentiment_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)

    print(f"结果已保存到 {output_file}")

if __name__ == "__main__":
    main()