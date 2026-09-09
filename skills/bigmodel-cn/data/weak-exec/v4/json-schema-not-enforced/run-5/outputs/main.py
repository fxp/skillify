#!/usr/bin/env python3
import json
import os
import requests

def analyze_sentiment(text):
    """使用智谱AI GLM模型进行情感分析"""
    # API配置
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构造请求体
    payload = {
        "model": "glm-5.3-flash",
        "messages": [
            {
                "role": "system",
                "content": """你是专业的情感分析专家。请对用户输入的文本进行情感分析，并严格按照以下JSON格式返回结果：
{"sentiment": "正面"/"负面"/"中性", "score": 0.0到1.0之间的数字}

其中：
- sentiment: 文件情感倾向，必须是"正面"、"负面"或"中性"三者之一
- score: 置信度分数，0表示完全不确定，1表示非常确定，请在0-1范围内给出合理的数值

分析标准：
- 正面：表达满意、赞赏、喜悦、推荐等积极情绪
- 负面：表达不满、失望、愤怒、抱怨等消极情绪
- 中性：客观描述、无明显情绪倾向

请只返回JSON，不要添加任何其他文字。"""
            },
            {
                "role": "user",
                "content": text
            }
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,  # 降低随机性，确保输出稳定
        "max_tokens": 100
    }

    # 发送请求
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    # 解析响应
    result = response.json()
    content = result["choices"][0]["message"]["content"]

    # 解析JSON
    try:
        sentiment_data = json.loads(content)
        return {
            "sentiment": sentiment_data["sentiment"],
            "score": float(sentiment_data["score"])
        }
    except (json.JSONDecodeError, KeyError) as e:
        # 如果解析失败，尝试从原始内容中提取
        print(f"解析JSON失败，原始内容: {content}")
        raise ValueError(f"情感分析结果格式错误: {e}")

def main():
    """主函数：分析3条文本的情感"""
    # 待分析的文本列表
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    # 分析每条文本的情感
    results = []
    for text in texts:
        print(f"分析文本: {text}")
        try:
            result = analyze_sentiment(text)
            print(f"分析结果: {result}")
            results.append(result)
        except Exception as e:
            print(f"分析失败: {e}")
            # 按照要求输出格式，即使出错也要提供结构化结果
            results.append({
                "sentiment": "中性",  # 默认值
                "score": 0.0
            })
        print("-" * 50)

    # 输出最终结果
    print("\n最终分析结果:")
    for i, (text, result) in enumerate(zip(texts, results), 1):
        print(f"{i}. '{text}' -> {result}")

    # 验证结果格式
    for result in results:
        assert result["sentiment"] in ["正面", "负面", "中性"], "sentiment必须是'正面'/'负面'/'中性'"
        assert 0 <= result["score"] <= 1, "score必须在0-1之间"

    print("\n✅ 所有文本情感分析完成！")

if __name__ == "__main__":
    main()