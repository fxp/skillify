#!/usr/bin/env python3
import os
import json
import requests
from typing import List, Dict, Any

def analyze_sentiment(text: str) -> Dict[str, Any]:
    """
    使用智谱 GLM 对单条文本进行情感分析

    Args:
        text: 要分析的文本

    Returns:
        {"sentiment": "正面"/"负面"/"中性", "score": 0到1之间的数字}
    """
    # 从环境变量读取 API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise ValueError("请在环境变量中设置 ZHIPUAI_API_KEY")

    # API 端点
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建提示词，要求模型返回 JSON 格式的情感分析结果
    prompt = f"""请对以下文本进行情感分析，严格按 JSON 格式返回结果：
{{
    "sentiment": "正面"/"负面"/"中性",
    "score": 0到1之间的数字（表示情感强度，1表示最强）
}}

文本："{text}"

请确保返回的是有效的 JSON，且字段名完全正确。"""

    # 请求参数
    payload = {
        "model": "glm-5.3",  # 使用 GLM-5.3 模型
        "messages": [
            {"role": "system", "content": "你是一个专业的情感分析助手，请准确判断文本的情感倾向并给出强度分数。"},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},  # 要求返回 JSON 格式
        "temperature": 0.1,  # 降低随机性，确保一致性
        "max_tokens": 100
    }

    # 发送请求
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()

    # 解析响应
    result = response.json()

    # 提取模型返回的内容
    content = result["choices"][0]["message"]["content"]

    # 尝试解析 JSON
    try:
        sentiment_data = json.loads(content)
    except json.JSONDecodeError:
        # 如果直接解析失败，尝试从响应中提取 JSON
        import re
        json_match = re.search(r'\{[^}]+\}', content)
        if json_match:
            sentiment_data = json.loads(json_match.group())
        else:
            raise ValueError(f"无法解析模型返回的 JSON: {content}")

    # 确保返回格式正确
    if "sentiment" not in sentiment_data or "score" not in sentiment_data:
        raise ValueError(f"返回的 JSON 缺少必要字段: {sentiment_data}")

    # 验证 sentiment 取值
    sentiment = sentiment_data["sentiment"]
    if sentiment not in ["正面", "负面", "中性"]:
        raise ValueError(f"sentiment 必须是'正面'/'负面'/'中性'之一，实际得到: {sentiment}")

    # 验证 score 范围
    score = float(sentiment_data["score"])
    if not (0 <= score <= 1):
        raise ValueError(f"score 必须是 0 到 1 之间的数字，实际得到: {score}")

    return {
        "sentiment": sentiment,
        "score": score
    }

def batch_analyze_sentiments(texts: List[str]) -> List[Dict[str, Any]]:
    """
    批量分析多条文本的情感

    Args:
        texts: 文本列表

    Returns:
        每个文本的情感分析结果列表
    """
    results = []
    for i, text in enumerate(texts):
        print(f"正在分析第 {i+1}/{len(texts)} 条文本...")
        try:
            result = analyze_sentiment(text)
            results.append({
                "text": text,
                "sentiment": result["sentiment"],
                "score": result["score"]
            })
            print(f"分析完成: {result}")
        except Exception as e:
            print(f"分析文本时出错: {e}")
            # 出错时使用默认值
            results.append({
                "text": text,
                "sentiment": "中性",
                "score": 0.5
            })

    return results

def main():
    """主函数"""
    # 待分析的文本
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    print("开始情感分析...")
    print(f"共 {len(texts)} 条文本")

    # 批量分析
    results = batch_analyze_sentiments(texts)

    # 输出结果
    print("\n=== 情感分析结果 ===")
    for result in results:
        print(json.dumps({
            "sentiment": result["sentiment"],
            "score": result["score"]
        }, ensure_ascii=False))

    # 返回格式确保与数据库要求一致
    return results

if __name__ == "__main__":
    main()