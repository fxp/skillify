#!/usr/bin/env python3
import json
import os
import requests

def analyze_sentiment(texts):
    """
    使用智谱 GLM 对文本列表进行情感分类

    Args:
        texts: 文本列表，如 ["这家店服务太差了，再也不来了", "东西还行吧，没什么特别的", "太惊喜了，比我预期好太多，强烈推荐"]

    Returns:
        list: 情感分析结果列表，每个元素为 {"sentiment": "正面"/"负面"/"中性", "score": 0到1之间的数字}
    """
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建系统提示词，要求模型严格按照指定格式返回
    system_prompt = """你是一个专业的情感分析专家。请对用户提供的每条文本进行情感分类，并严格按照以下 JSON 格式返回：

[
    {"sentiment": "正面"/"负面"/"中性", "score": 0.8},
    {"sentiment": "正面"/"负面"/"中性", "score": 0.6},
    ...
]

要求：
1. sentiment 只能是 "正面"、"负面" 或 "中性" 三种之一
2. score 是 0 到 1 之间的数字，表示情感强度（负面情感分数接近0，正面情感分数接近1）
3. 必须返回有效的 JSON 数组，不要包含任何其他文字
4. 数组顺序必须与输入文本顺序一致"""

    # 构建消息
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请分析以下文本的情感：\n" + "\n".join(f"{i+1}. {text}" for i, text in enumerate(texts))}
    ]

    # 构建请求 payload
    payload = {
        "model": "glm-5.3",
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.1,  # 降低温度以获得更稳定的结果
        "max_tokens": 1000
    }

    # 发送请求
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()

    # 解析响应
    result = response.json()
    content = result["choices"][0]["message"]["content"]

    # 解析 JSON
    try:
        # 提取 JSON 部分（可能包含在 markdown 代码块中）
        if "```json" in content:
            json_part = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_part = content.split("```")[1].split("```")[0]
        else:
            json_part = content

        # 清理并解析 JSON
        json_part = json_part.strip()
        # 移除可能的 BOM
        if json_part.startswith('﻿'):
            json_part = json_part[1:]

        sentiment_results = json.loads(json_part)

        # 验证结果格式
        for result in sentiment_results:
            if "sentiment" not in result or "score" not in result:
                raise ValueError("返回结果格式不正确")
            if result["sentiment"] not in ["正面", "负面", "中性"]:
                raise ValueError("sentiment 必须是'正面'、'负面'或'中性'")
            if not (0 <= result["score"] <= 1):
                raise ValueError("score 必须是0到1之间的数字")

        return sentiment_results

    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 解析失败: {e}\n原始内容: {content}")


def main():
    """主函数"""
    # 待分析的文本
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    try:
        # 进行情感分析
        results = analyze_sentiment(texts)

        # 输出结果
        print("情感分析结果：")
        for i, (text, result) in enumerate(zip(texts, results)):
            print(f"\n文本 {i+1}: {text}")
            print(f"情感: {result['sentiment']}")
            print(f"分数: {result['score']}")

        # 严格符合要求的输出格式（可以直接入库）
        output = {
            "sentiment": results[0]["sentiment"],  # 取第一个文本的情感
            "score": results[0]["score"]           # 取第一个文本的分数
        }

        print(f"\n严格输出格式（入库用）: {json.dumps(output, ensure_ascii=False)}")

        return output

    except Exception as e:
        print(f"错误: {e}")
        raise


if __name__ == "__main__":
    main()