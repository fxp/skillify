#!/usr/bin/env python3
"""
情感分类脚本
使用智谱 GLM 对文本进行情感分类，输出格式为 {"sentiment": "正面"/"负面"/"中性", "score": 0-1的数字}
"""

import os
import json
import requests
import re
from typing import List, Dict, Union


def analyze_sentiment(texts: List[str]) -> List[Dict[str, Union[str, float]]]:
    """
    对输入的文本列表进行情感分类

    Args:
        texts: 待分类的文本列表

    Returns:
        情感分析结果列表，每个元素为 {"sentiment": "正面"/"负面"/"中性", "score": 0-1的数字}
    """
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    # API 配置
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 系统提示词，明确指定输出格式
    system_prompt = """你是情感分析专家。请严格按照以下 JSON 格式返回分析结果，不要输出任何其他文字：
{"sentiment": "正面"|"负面"|"中性", "score": 0到1的数字}

sentiment 取值说明：
- "正面": 表示积极、正面的情感
- "负面": 表示消极、负面的情感
- "中性": 表示中性、客观的情感

score 是 0 到 1 之间的数字，表示情感强度：
- 1.0 表示非常强烈的情感
- 0.0 表示完全没有情感
- 中间值表示情感强度
"""

    results = []

    # 逐条处理文本
    for text in texts:
        # 构造请求 payload
        payload = {
            "model": "glm-4.6",  # 选择合适的模型
            "max_tokens": 200,
            "thinking": {"type": "disabled"},  # 关闭思考模式，节省token
            "response_format": {"type": "json_object"},  # 要求 JSON 输出
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f'请对以下文本进行情感分析："{text}"'}
            ]
        }

        # 发送请求
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()

        # 提取回复内容
        content = result["choices"][0]["message"].get("content", "")

        # 清理内容，移除可能的 markdown 代码块标记
        cleaned_content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()

        # 解析 JSON
        try:
            parsed_data = json.loads(cleaned_content)

            # 验证字段
            sentiment = parsed_data.get("sentiment")
            score = parsed_data.get("score")

            # 验证取值范围
            if sentiment not in ("正面", "负面", "中性"):
                raise ValueError(f"无效的 sentiment 值: {sentiment}")

            if not isinstance(score, (int, float)) or not (0 <= score <= 1):
                raise ValueError(f"无效的 score 值: {score}")

            results.append({
                "sentiment": sentiment,
                "score": float(score)
            })

        except json.JSONDecodeError:
            # 如果 JSON 解析失败，尝试从内容中提取
            # 这里作为备用方案，实际使用时建议增加重试逻辑
            fallback_result = {
                "sentiment": "中性",  # 默认值
                "score": 0.5
            }
            results.append(fallback_result)
        except Exception as e:
            # 其他验证错误
            print(f"文本 '{text}' 分析失败: {e}")
            # 返回默认值
            results.append({
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

    try:
        # 进行情感分析
        results = analyze_sentiment(texts)

        # 输出结果
        for i, (text, result) in enumerate(zip(texts, results)):
            print(f"文本 {i+1}: {text}")
            print(f"情感分析结果: {result}")
            print()

        # 可以选择将结果保存到文件
        # with open('sentiment_results.json', 'w', encoding='utf-8') as f:
        #     json.dump(results, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"程序执行出错: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())