import os
import json
import re
import requests
from typing import List, Dict, Any

# API配置
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# 请求头
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 要分析的文本列表
texts_to_analyze = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐"
]

def analyze_sentiment(text: str) -> Dict[str, Any]:
    """
    使用智谱GLM模型分析单条文本的情感

    Args:
        text: 要分析的文本

    Returns:
        包含情感分类和置信度的字典，格式为：
        {"sentiment": "正面"/"负面"/"中性", "score": 0到1之间的数字}
    """
    # 提示词，明确要求返回指定格式的JSON
    system_prompt = """你是专业的情感分析专家。请严格按照JSON格式返回分析结果，不要输出任何其他文字。
返回格式必须为：
{"sentiment": "正面"|"负面"|"中性", "score": 0到1之间的数字}

其中：
- sentiment: 只能是"正面"、"负面"或"中性"中的一个
- score: 置信度分数，0到1之间的数字，1表示非常确定，0表示完全不确定

请根据文本的情感倾向进行分析。"""

    payload = {
        "model": "glm-4.7",  # 使用支持结构化输出的模型
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        "response_format": {"type": "json_object"},  # 启用JSON格式输出
        "max_tokens": 100,  # 足够输出JSON即可
        "temperature": 0.1,  # 降低随机性，提高一致性
        "do_sample": True  # 保持采样，使输出更自然
    }

    # 发送请求
    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        # 解析响应
        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # 清理可能的markdown代码块标记
        cleaned_content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()

        # 解析JSON
        try:
            sentiment_data = json.loads(cleaned_content)

            # 验证返回的数据格式
            if "sentiment" not in sentiment_data or "score" not in sentiment_data:
                raise ValueError("返回的JSON缺少必要字段")

            sentiment = sentiment_data["sentiment"]
            score = sentiment_data["score"]

            # 验证sentiment的取值
            if sentiment not in ["正面", "负面", "中性"]:
                raise ValueError(f"sentiment必须是'正面'、'负面'或'中性'，实际得到：{sentiment}")

            # 验证score的范围
            if not isinstance(score, (int, float)) or score < 0 or score > 1:
                raise ValueError(f"score必须是0到1之间的数字，实际得到：{score}")

            return {
                "sentiment": sentiment,
                "score": float(score)
            }

        except json.JSONDecodeError as e:
            raise ValueError(f"JSON解析失败：{e}\n原始内容：{cleaned_content}")

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API请求失败：{e}")
    except KeyError as e:
        raise RuntimeError(f"响应格式错误，缺少字段：{e}")


def batch_analyze_sentiment(texts: List[str]) -> List[Dict[str, Any]]:
    """
    批量分析文本情感

    Args:
        texts: 文本列表

    Returns:
        分析结果列表，每个元素是对应文本的情感分析结果
    """
    results = []

    for i, text in enumerate(texts):
        print(f"正在分析第 {i+1}/{len(texts)} 条文本: {text[:50]}...")
        try:
            result = analyze_sentiment(text)
            results.append(result)
            print(f"完成 - 情感: {result['sentiment']}, 置信度: {result['score']:.2f}")
        except Exception as e:
            print(f"分析失败: {e}")
            # 返回默认值，避免程序中断
            results.append({
                "sentiment": "中性",  # 默认值
                "score": 0.0
            })

    return results


def main():
    """主函数"""
    print("开始情感分析...")
    print("=" * 50)

    # 执行批量分析
    results = batch_analyze_sentiment(texts_to_analyze)

    # 输出结果
    print("\n" + "=" * 50)
    print("分析结果：")
    print("=" * 50)

    for i, (text, result) in enumerate(zip(texts_to_analyze, results)):
        print(f"\n文本 {i+1}: {text}")
        print(f"情感: {result['sentiment']}")
        print(f"置信度: {result['score']:.2f}")

    # 输出JSON格式的结果
    print("\n" + "=" * 50)
    print("JSON格式结果（可直接入库）：")
    print("=" * 50)
    json_output = json.dumps(results, ensure_ascii=False, indent=2)
    print(json_output)

    # 保存结果到文件（可选）
    with open("sentiment_results.json", "w", encoding="utf-8") as f:
        f.write(json_output)

    print("\n结果已保存到 sentiment_results.json")


if __name__ == "__main__":
    main()