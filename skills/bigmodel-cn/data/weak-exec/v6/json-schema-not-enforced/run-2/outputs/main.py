#!/usr/bin/env python3
"""
情感分类脚本：使用智谱 GLM 对文本进行情感分析
输出格式：{"sentiment": "正面"/"负面"/"中性", "score": 0到1的数字}
"""

import os
import requests
import json
import re

def analyze_sentiment(text):
    """
    分析文本情感，返回符合要求的JSON结构
    """
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("环境变量 ZHIPUAI_API_KEY 未设置")

    # 构建请求数据
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 系统提示：明确指定JSON输出格式
    system_prompt = """你是情感分析专家。请严格按照以下JSON格式返回分析结果，不要输出任何其他文字：
{"sentiment": "正面"/"负面"/"中性", "score": 0到1之间的数字}

sentiment必须是以下三个值之一："正面"、"负面"、"中性"
score必须是0到1之间的数字，表示情感倾向的强度（0表示完全负面，1表示完全正面，0.5表示中性）
"""

    payload = {
        "model": "glm-4.6",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请分析以下文本的情感：{text}"}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 100
    }

    # 发送请求
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    # 解析响应
    result = response.json()
    content = result["choices"][0]["message"]["content"]

    # 清理可能的markdown代码块标记
    content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()

    # 解析JSON
    try:
        sentiment_data = json.loads(content)

        # 验证字段格式
        if sentiment_data.get("sentiment") not in ["正面", "负面", "中性"]:
            raise ValueError("sentiment必须是'正面'、'负面'或'中性'")

        score = sentiment_data.get("score")
        if not isinstance(score, (int, float)) or score < 0 or score > 1:
            raise ValueError("score必须是0到1之间的数字")

        return sentiment_data

    except json.JSONDecodeError as e:
        raise ValueError(f"返回的JSON格式错误: {e}")
    except Exception as e:
        raise ValueError(f"返回数据格式错误: {e}")

def main():
    """
    主函数：对3条文本进行情感分类并输出结果
    """
    test_texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    results = []

    for text in test_texts:
        try:
            result = analyze_sentiment(text)
            results.append({
                "text": text,
                "result": result
            })
            print(f"文本: {text}")
            print(f"结果: {result}")
            print("-" * 50)
        except Exception as e:
            print(f"分析文本时出错: {text}")
            print(f"错误: {e}")
            print("-" * 50)
            # 出错时返回中性评价，分数为0.5
            results.append({
                "text": text,
                "result": {"sentiment": "中性", "score": 0.5}
            })

    # 输出所有结果的JSON格式
    output = {item["text"]: item["result"] for item in results}
    print("\n最终结果:")
    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()