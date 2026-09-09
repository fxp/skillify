#!/usr/bin/env python3
"""
文本情感分析脚本
使用智谱 GLM 对文本进行情感分类，输出严格的JSON格式
"""

import os
import requests
import json

def analyze_sentiment(texts):
    """
    对文本列表进行情感分析

    Args:
        texts: 待分析的文本列表

    Returns:
        list: 情感分析结果列表，每个元素格式为 {"sentiment": "正面"/"负面"/"中性", "score": 0-1之间的数字}
    """
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    # API配置
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建系统提示词
    system_prompt = """你是一个专业的文本情感分析助手。请对每条文本进行情感分类，只输出JSON格式的结果，不要包含任何其他文字。

分类标准：
- 正面：文本表达积极、满意、推荐等正面情感
- 负面：文本表达不满、抱怨、批评等负面情感
- 中性：文本客观描述、无明显情感倾向

对于每条文本，你需要输出：
1. sentiment: 必须是"正面"、"负面"、"中性"中的一个
2. score: 0到1之间的数字，表示情感的强烈程度（正面或负面）或中性程度（中性）

JSON格式示例：
{"sentiment": "正面", "score": 0.9}
{"sentiment": "负面", "score": 0.8}
{"sentiment": "中性", "score": 0.1}"""

    results = []

    for text in texts:
        # 构建用户消息
        user_prompt = f"""请分析以下文本的情感：
文本："{text}"

请严格按照以下JSON格式输出结果（不要包含任何其他文字）：
{{"sentiment": "正面"/"负面"/"中性", "score": 0到1之间的数字}}"""

        # 构造请求体
        payload = {
            "model": "glm-5.3",  # 使用旗舰模型进行文本分析
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,  # 降低随机性，确保输出稳定
            "max_tokens": 100,
            "response_format": {"type": "json_object"}  # 确保返回JSON格式
        }

        try:
            # 发送请求
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            # 解析响应
            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # 解析JSON结果
            result = json.loads(content)

            # 验证结果格式
            if "sentiment" not in result or "score" not in result:
                raise ValueError("API返回格式错误")

            # 标准化sentiment字段
            sentiment = result["sentiment"]
            if sentiment not in ["正面", "负面", "中性"]:
                raise ValueError(f"无效的sentiment值: {sentiment}")

            # 验证score范围
            score = float(result["score"])
            if score < 0 or score > 1:
                raise ValueError(f"score必须在0-1之间，实际值: {score}")

            results.append({
                "sentiment": sentiment,
                "score": score
            })

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"API请求失败: {e}")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise RuntimeError(f"解析响应失败: {e}")

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
        print(json.dumps(results, ensure_ascii=False, indent=2))

    except Exception as e:
        error_msg = f"错误: {e}"
        print(json.dumps({"error": error_msg}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    import sys
    main()