#!/usr/bin/env python3
import os
import requests
import json
import re
from typing import List, Dict, Any

def analyze_sentiment(text: str) -> Dict[str, Any]:
    """
    使用智谱GLM模型对文本进行情感分析

    Args:
        text: 待分析的文本

    Returns:
        包含情感和置信度的字典，格式为：
        {"sentiment": "正面"/"负面"/"中性", "score": 0到1之间的数字}
    """
    # API配置
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建请求 payload
    payload = {
        "model": "glm-5.3",  # 使用通用旗舰对话模型
        "messages": [
            {
                "role": "system",
                "content": """你是专业的情感分析专家。请对用户输入的文本进行情感分类，并严格按照以下JSON格式返回结果，不要包含任何其他文字：

{"sentiment": "正面"/"负面"/"中性", "score": 0到1之间的数字}

其中：
- sentiment: 必须是"正面"、"负面"或"中性"之一
- score: 置信度分数，范围0-1，表示模型对判断结果的信心程度

请准确理解文本的情感倾向，给出合理的置信度分数。"""
            },
            {
                "role": "user",
                "content": text
            }
        ],
        "response_format": {"type": "json_object"},  # 启用JSON格式输出
        "max_tokens": 200,  # 足够输出JSON即可
        "temperature": 0.1,  # 降低随机性，提高一致性
        "do_sample": True  # 保持采样以获得更自然的结果
    }

    # 发送请求
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()

    # 解析响应
    result = response.json()
    content = result["choices"][0]["message"]["content"]

    # 清理响应内容（去除可能的markdown代码块标记）
    content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()

    # 解析JSON
    try:
        sentiment_data = json.loads(content)

        # 验证输出格式
        if "sentiment" not in sentiment_data or "score" not in sentiment_data:
            raise ValueError("返回的JSON缺少必要字段")

        sentiment = sentiment_data["sentiment"]
        score = sentiment_data["score"]

        # 验证sentiment的值
        if sentiment not in ["正面", "负面", "中性"]:
            raise ValueError(f"无效的sentiment值: {sentiment}")

        # 验证score的范围
        if not isinstance(score, (int, float)) or not (0 <= score <= 1):
            raise ValueError(f"无效的score值: {score}")

        return {
            "sentiment": sentiment,
            "score": float(score)
        }

    except json.JSONDecodeError as e:
        raise ValueError(f"返回的JSON格式错误: {content}")
    except Exception as e:
        raise ValueError(f"解析响应时出错: {str(e)}")

def main():
    """主函数：对指定的3条文本进行情感分类"""
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

    # 逐条分析文本
    for i, text in enumerate(texts, 1):
        print(f"\n分析第 {i} 条文本:")
        print(f"文本: {text}")

        try:
            result = analyze_sentiment(text)
            results.append(result)

            print(f"情感: {result['sentiment']}")
            print(f"置信度: {result['score']:.2f}")

        except Exception as e:
            print(f"分析出错: {str(e)}")
            # 出错时返回默认值
            results.append({"sentiment": "中性", "score": 0.0})

        print("-" * 30)

    # 输出最终结果
    print("\n" + "=" * 50)
    print("情感分析结果汇总:")
    print("=" * 50)

    for i, (text, result) in enumerate(zip(texts, results), 1):
        print(f"\n文本 {i}: {text}")
        print(f"情感: {result['sentiment']}")
        print(f"置信度: {result['score']:.2f}")

    # 将结果写入JSON文件（可选）
    output_file = "sentiment_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "texts": texts,
            "results": results
        }, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_file}")

if __name__ == "__main__":
    main()