import os
import json
import requests

def analyze_sentiment(text):
    """
    使用智谱 GLM 对文本进行情感分析

    Args:
        text (str): 要分析的文本

    Returns:
        dict: 包含 sentiment 和 score 的字典
              sentiment: "正面"/"负面"/"中性"
              score: 0 到 1 之间的数字
    """
    # 从环境变量获取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    # API 端点
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建请求数据
    payload = {
        "model": "glm-5.3",  # 使用 GLM-5.3 模型
        "messages": [
            {
                "role": "system",
                "content": """你是一个专业的情感分析专家。请严格按照 JSON 格式返回分析结果，不要输出任何其他文字。
返回格式必须是：
{"sentiment": "正面"/"负面"/"中性", "score": 0-1之间的数字}

sentiment 说明：
- "正面": 表示积极的、赞赏的、满意的情绪
- "负面": 表示消极的、不满的、批评的情绪
- "中性": 表示客观的、中性的、无强烈情绪的表达

score 说明：
- 0 到 1 之间的数字，表示情感的强烈程度
- 正面和负面情感的 score 是情感的强度（越接近 1 越强烈）
- 中性情感的 score 是中性的程度（越接近 1 越确定是中性，越接近 0 越模糊）"""
            },
            {
                "role": "user",
                "content": f"请分析以下文本的情感：{text}"
            }
        ],
        "response_format": {"type": "json_object"},  # 确保返回 JSON
        "temperature": 0.1,  # 降低随机性，确保输出稳定
        "max_tokens": 100
    }

    # 发送请求
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    # 解析响应
    result = response.json()
    content = result["choices"][0]["message"]["content"]

    # 解析返回的 JSON
    try:
        sentiment_data = json.loads(content)

        # 验证字段
        if "sentiment" not in sentiment_data or "score" not in sentiment_data:
            raise ValueError("返回的 JSON 缺少必要字段")

        sentiment = sentiment_data["sentiment"]
        score = sentiment_data["score"]

        # 验证取值
        if sentiment not in ["正面", "负面", "中性"]:
            raise ValueError(f"sentiment 必须是'正面'/'负面'/'中性'，当前值：{sentiment}")

        if not isinstance(score, (int, float)) or score < 0 or score > 1:
            raise ValueError(f"score 必须是 0 到 1 之间的数字，当前值：{score}")

        return {
            "sentiment": sentiment,
            "score": score
        }

    except json.JSONDecodeError:
        raise ValueError("返回的内容不是有效的 JSON 格式")

def main():
    # 要分析的文本列表
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    # 存储所有结果
    results = []

    # 分析每个文本的情感
    for text in texts:
        print(f"分析文本: {text}")
        try:
            result = analyze_sentiment(text)
            results.append({
                "text": text,
                "sentiment": result["sentiment"],
                "score": result["score"]
            })
            print(f"结果: {result}\n")
        except Exception as e:
            print(f"分析失败: {str(e)}")
            results.append({
                "text": text,
                "sentiment": "分析失败",
                "score": 0.0
            })

    # 输出最终结果（严格按照要求的格式）
    final_results = []
    for result in results:
        if result["sentiment"] != "分析失败":
            final_results.append({
                "sentiment": result["sentiment"],
                "score": result["score"]
            })
        else:
            # 如果分析失败，给一个默认值
            final_results.append({
                "sentiment": "中性",
                "score": 0.5
            })

    # 输出最终结果
    print("=" * 50)
    print("最终结果:")
    print("=" * 50)
    for result in final_results:
        print(result)

if __name__ == "__main__":
    main()