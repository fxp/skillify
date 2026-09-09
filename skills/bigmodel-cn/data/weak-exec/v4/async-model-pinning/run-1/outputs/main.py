#!/usr/bin/env python3
"""
情感分类脚本 - 使用智谱AI异步接口
对三句话进行情感分类，并核对模型版本
"""

import os
import requests
import time
import json

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
REQUESTED_MODEL = "glm-4.6"  # 审计要求锁定的模型版本

# 要进行情感分类的三句话
TEXTS_TO_CLASSIFY = [
    "今天天气真好，心情很愉快！",
    "这个产品太差了，完全不推荐购买。",
    "我觉得这部电影还行，没有特别出彩的地方。"
]

def submit_async_task(text: str, model: str) -> dict:
    """提交异步任务"""
    url = f"{BASE_URL}/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是情感分析专家。请分析以下文本的情感，并以JSON格式返回结果：{\n  \"sentiment\": \"positive/negative/neutral\",\n  \"confidence\": 0.0-1.0,\n  \"analysis\": \"详细分析\"\n}"
            },
            {
                "role": "user",
                "content": text
            }
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 200
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()

def poll_async_result(task_id: str, timeout: int = 60) -> dict:
    """轮询异步任务结果"""
    url = f"{BASE_URL}/async-result/{task_id}"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    waited = 0
    while waited < timeout:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()

        status = result.get("task_status")
        if status == "SUCCESS":
            return result
        elif status == "FAIL":
            raise RuntimeError(f"异步任务失败: {result}")

        time.sleep(2)
        waited += 2

    raise TimeoutError(f"轮询超时，已等待 {timeout} 秒")

def analyze_sentiment(text: str) -> dict:
    """分析文本情感"""
    print(f"\n正在分析文本: \"{text}\"")

    # 提交异步任务
    task_info = submit_async_task(text, REQUESTED_MODEL)
    task_id = task_info["id"]
    actual_model = task_info.get("model", "unknown")

    # 打印模型信息进行审计核对
    print(f"\n【审计信息】")
    print(f"我请求的模型: {REQUESTED_MODEL}")
    print(f"接口实际使用的模型: {actual_model}")

    # 模型版本核对
    if actual_model != REQUESTED_MODEL:
        print(f"\n⚠️  警告: 模型版本不一致！")
        print(f"   请求: {REQUESTED_MODEL}")
        print(f"   实际: {actual_model}")
        print(f"   这可能影响审计结果的准确性！")
        return {"sentiment": "warning", "confidence": 0.0, "analysis": "模型版本不匹配"}

    # 轮询结果
    print(f"\n任务ID: {task_id}")
    print("正在等待分析结果...")

    result = poll_async_result(task_id)

    # 解析结果
    if "choices" in result and len(result["choices"]) > 0:
        content = result["choices"][0]["message"]["content"]
        try:
            # 尝试解析JSON响应
            sentiment_data = json.loads(content)
            return sentiment_data
        except json.JSONDecodeError:
            # 如果不是JSON格式，直接返回
            return {
                "sentiment": "unknown",
                "confidence": 0.0,
                "analysis": f"原始响应: {content}"
            }
    else:
        return {
            "sentiment": "error",
            "confidence": 0.0,
            "analysis": "无法获取分析结果"
        }

def main():
    """主函数"""
    print("=" * 50)
    print("情感分类分析 - 使用智谱AI异步接口")
    print("=" * 50)

    # 检查API Key
    if not API_KEY:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY")
        print("例如: export ZHIPUAI_API_KEY='your_api_key_here'")
        return 1

    print(f"请求模型: {REQUESTED_MODEL}")
    print(f"待分析文本数量: {len(TEXTS_TO_CLASSIFY)}")

    # 分析每句话的情感
    results = []
    for i, text in enumerate(TEXTS_TO_CLASSIFY, 1):
        print(f"\n{'-' * 30}")
        print(f"分析第 {i}/{len(TEXTS_TO_CLASSIFY)} 条")
        print(f"文本: \"{text}\"")

        result = analyze_sentiment(text)
        results.append(result)

        # 显示结果
        print(f"\n分析结果:")
        print(f"情感倾向: {result['sentiment']}")
        print(f"置信度: {result['confidence']}")
        print(f"详细分析: {result['analysis']}")
        print(f"{'-' * 30}")

    # 总结报告
    print("\n" + "=" * 50)
    print("分析总结")
    print("=" * 50)

    sentiments = [r['sentiment'] for r in results]
    sentiment_counts = {}
    for s in sentiments:
        sentiment_counts[s] = sentiment_counts.get(s, 0) + 1

    print("各情感统计:")
    for sentiment, count in sentiment_counts.items():
        print(f"  {sentiment}: {count} 条")

    # 使用统计
    if "usage" in locals():
        print(f"\nToken使用情况:")
        print(f"  输入: {usage.get('prompt_tokens', 0)} tokens")
        print(f"  输出: {usage.get('completion_tokens', 0)} tokens")
        print(f"  总计: {usage.get('total_tokens', 0)} tokens")

    print("\n分析完成！")
    return 0

if __name__ == "__main__":
    exit(main())