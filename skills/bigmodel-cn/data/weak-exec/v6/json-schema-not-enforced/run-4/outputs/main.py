import os
import re
import json
import requests

def classify_sentiment(text, model="glm-4.6", max_retries=3):
    """
    使用智谱AI GLM模型对文本进行情感分类

    Args:
        text (str): 需要分类的文本
        model (str): 使用的模型，默认为glm-4.6
        max_retries (int): 最大重试次数

    Returns:
        dict: 符合格式的情感分类结果 {"sentiment": "正面"/"负面"/"中性", "score": 0-1之间的数字}
    """
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    base_url = "https://open.bigmodel.cn/api/paas/v4"
    headers = {"Authorization": f"Bearer {api_key}"}

    # 系统提示词，要求模型严格按JSON格式输出
    system_prompt = """你是一个专业的情感分析专家。请对用户的文本进行情感分析，并严格按照以下JSON格式返回，不要输出任何其他文字：
{"sentiment": "正面"|"负面"|"中性", "score": 0到1之间的数字}

说明：
- sentiment: 取值只能是"正面"、"负面"或"中性"之一
- score: 0到1之间的数字，表示情感强度或置信度，0表示完全否定，1表示完全肯定
- 只输出JSON，不要包含任何解释性文字
"""

    # 构建请求 payload
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 200,
        "temperature": 0.1,  # 较低的温度确保输出稳定
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            # 提取响应内容
            content = response.json()["choices"][0]["message"]["content"]

            # 清理可能的代码块标记
            cleaned_content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()

            # 解析JSON
            result = json.loads(cleaned_content)

            # 验证输出格式
            if "sentiment" in result and "score" in result:
                sentiment = result["sentiment"]
                score = result["score"]

                # 验证sentiment取值
                if sentiment not in ["正面", "负面", "中性"]:
                    raise ValueError(f"无效的sentiment值: {sentiment}")

                # 验证score范围
                if not isinstance(score, (int, float)) or not (0 <= score <= 1):
                    raise ValueError(f"无效的score值: {score}")

                return {
                    "sentiment": sentiment,
                    "score": float(score)
                }
            else:
                raise ValueError("返回的JSON缺少必要字段")

        except json.JSONDecodeError as e:
            if attempt == max_retries - 1:
                raise ValueError(f"JSON解析失败: {e}")
            continue
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise RuntimeError(f"API请求失败: {e}")
            continue

    raise RuntimeError(f"尝试{max_retries}次后仍未能获得有效结果")

def main():
    """主函数：对3条文本进行情感分类"""
    # 待分类的文本列表
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    print("开始情感分类...")
    print("=" * 50)

    # 对每条文本进行分类
    results = []
    for i, text in enumerate(texts, 1):
        print(f"\n文本 {i}: {text}")
        try:
            result = classify_sentiment(text)
            results.append(result)
            print(f"分类结果: {result}")
        except Exception as e:
            print(f"分类失败: {e}")
            # 提供一个默认结果
            results.append({
                "sentiment": "中性",
                "score": 0.5
            })

    # 输出最终汇总结果
    print("\n" + "=" * 50)
    print("分类结果汇总:")
    print("=" * 50)

    for i, (text, result) in enumerate(zip(texts, results), 1):
        print(f"\n文本 {i}: {text}")
        print(f"情感: {result['sentiment']}")
        print(f"置信度: {result['score']:.2f}")

    # 将结果保存为JSON文件
    output_data = {
        "texts": texts,
        "results": results,
        "summary": {
            "正面": sum(1 for r in results if r["sentiment"] == "正面"),
            "负面": sum(1 for r in results if r["sentiment"] == "负面"),
            "中性": sum(1 for r in results if r["sentiment"] == "中性")
        }
    }

    with open("sentiment_results.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print("\n结果已保存到 sentiment_results.json")

if __name__ == "__main__":
    main()