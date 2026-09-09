#!/usr/bin/env python3
"""
使用智谱 GLM 对文本进行情感分类
输出格式：{"sentiment": "正面"/"负面"/"中性", "score": 0-1之间的数字}
"""

import os
import requests
import json
import sys

def classify_sentiment(texts):
    """
    对输入的文本列表进行情感分类

    Args:
        texts: 文本列表，例如 ["这家店服务太差了，再也不来了", "东西还行吧，没什么特别的", "太惊喜了，比我预期好太多，强烈推荐"]

    Returns:
        list: 情感分类结果列表，每个元素为 {"sentiment": "正面"/"负面"/"中性", "score": 0-1之间的数字}
    """
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        sys.exit(1)

    # API 端点
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    results = []

    # 对每个文本进行情感分类
    for text in texts:
        # 构建请求数据
        payload = {
            "model": "glm-5.3",
            "messages": [
                {
                    "role": "system",
                    "content": """你是一个专业的情感分类助手。请对用户的文本进行情感分类，只返回JSON格式的结果，不要包含任何其他解释。

分类规则：
- 正面：表达满意、赞扬、开心、惊喜等积极情感
- 负面：表达不满、抱怨、愤怒、失望等消极情感
- 中性：客观陈述、无明显情感倾向或情感中性

对于每个文本，请分析其情感倾向，并给出0-1之间的置信度分数。"""
                },
                {
                    "role": "user",
                    "content": f"请对以下文本进行情感分类：\n\"{text}\"\n\n请严格按照以下JSON格式返回结果：\n{{\"sentiment\": \"正面\"/\"负面\"/\"中性\", \"score\": 0.0-1.0之间的数字}}"
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,  # 降低随机性，确保输出稳定
            "max_tokens": 100
        }

        try:
            # 发送请求
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            # 解析响应
            response_data = response.json()
            content = response_data["choices"][0]["message"]["content"]

            # 解析JSON结果
            result = json.loads(content)

            # 验证结果格式
            if "sentiment" not in result or "score" not in result:
                print(f"警告：模型返回格式不正确，内容：{content}", file=sys.stderr)
                # 使用默认值
                result = {"sentiment": "中性", "score": 0.5}

            # 验证sentiment值
            if result["sentiment"] not in ["正面", "负面", "中性"]:
                print(f"警告：无效的sentiment值：{result['sentiment']}，将改为'中性'", file=sys.stderr)
                result["sentiment"] = "中性"

            # 验证score值
            score = result["score"]
            if not isinstance(score, (int, float)) or score < 0 or score > 1:
                print(f"警告：无效的score值：{score}，将改为0.5", file=sys.stderr)
                result["score"] = 0.5

            results.append(result)

        except requests.exceptions.RequestException as e:
            print(f"请求错误：{e}", file=sys.stderr)
            # 使用默认值
            results.append({"sentiment": "中性", "score": 0.5})
        except json.JSONDecodeError as e:
            print(f"JSON解析错误：{e}", file=sys.stderr)
            # 使用默认值
            results.append({"sentiment": "中性", "score": 0.5})
        except KeyError as e:
            print(f"响应格式错误，缺少字段：{e}", file=sys.stderr)
            # 使用默认值
            results.append({"sentiment": "中性", "score": 0.5})

    return results

def main():
    """主函数"""
    # 待分类的文本
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    # 进行情感分类
    results = classify_sentiment(texts)

    # 输出结果
    for i, (text, result) in enumerate(zip(texts, results)):
        print(f"文本 {i+1}: \"{text}\"")
        print(f"情感分类: {result['sentiment']}")
        print(f"置信度: {result['score']}")
        print("-" * 50)

    # 可选：将结果保存到JSON文件
    # with open('sentiment_results.json', 'w', encoding='utf-8') as f:
    #     json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()