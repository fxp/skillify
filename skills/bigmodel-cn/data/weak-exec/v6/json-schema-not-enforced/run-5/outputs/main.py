import os
import json
import re
import requests

# 从环境变量读取 API Key
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# API 配置
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": application/json}

# 提示词模板：要求 JSON 格式输出
HINT = '只输出 JSON：{"sentiment": "正面"/"负面"/"中性", "score": 0到1的数字}'

def classify_sentiment(text, max_retries=3):
    """
    对文本进行情感分类

    Args:
        text: 要分类的文本
        max_retries: 最大重试次数

    Returns:
        dict: {"sentiment": "正面"/"负面"/"中性", "score": 0到1的数字}
    """
    for attempt in range(max_retries):
        try:
            # 发送请求
            response = requests.post(
                f"{BASE_URL}/chat/completions",
                headers=HEADERS,
                json={
                    "model": "glm-4.6",
                    "max_tokens": 400,
                    "thinking": {"type": "disabled"},  # 关闭思考模式，避免消耗 token
                    "response_format": {"type": "json_object"},  # 要求 JSON 输出
                    "messages": [
                        {"role": "system", "content": HINT},
                        {"role": "user", "content": text}
                    ]
                },
                timeout=30
            )
            response.raise_for_status()

            # 提取回复内容
            content = response.json()["choices"][0]["message"].get("content", "").strip()

            # 清理可能的代码块标记
            cleaned_content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.M).strip()

            # 解析 JSON
            result = json.loads(cleaned_content)

            # 验证结果格式
            if result.get("sentiment") in ("正面", "负面", "中性") and isinstance(result.get("score"), (int, float)):
                # 确保 score 在 0-1 范围内
                score = max(0.0, min(1.0, float(result["score"])))
                return {
                    "sentiment": result["sentiment"],
                    "score": score
                }
            else:
                if attempt == max_retries - 1:
                    raise ValueError(f"返回格式不正确: {result}")
                continue

        except json.JSONDecodeError as e:
            if attempt == max_retries - 1:
                raise ValueError(f"JSON 解析失败: {cleaned_content}")
            continue
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            continue

    raise RuntimeError(f"尝试 {max_retries} 次后仍未获得有效结果")

def main():
    """主函数：对 3 条文本进行情感分类"""
    # 测试文本
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    # 存储结果
    results = []

    print("开始情感分类...")
    for i, text in enumerate(texts, 1):
        print(f"\n处理第 {i} 条文本: {text}")
        try:
            result = classify_sentiment(text)
            results.append(result)
            print(f"分类结果: {result}")
        except Exception as e:
            print(f"分类失败: {e}")
            # 添加默认值
            results.append({"sentiment": "中性", "score": 0.5})

    # 输出最终结果
    print("\n=== 最终结果 ===")
    for i, (text, result) in enumerate(zip(texts, results), 1):
        print(f"文本 {i}: {text}")
        print(f"  情感: {result['sentiment']}")
        print(f"  置信度: {result['score']:.2f}")

    # 按 JSON 格式输出结果（符合数据库入库要求）
    output_data = {
        "results": results,
        "summary": {
            "total_texts": len(texts),
            "positive_count": sum(1 for r in results if r["sentiment"] == "正面"),
            "negative_count": sum(1 for r in results if r["sentiment"] == "负面"),
            "neutral_count": sum(1 for r in results if r["sentiment"] == "中性")
        }
    }

    print("\n=== JSON 输出（可直接入库） ===")
    print(json.dumps(output_data, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()