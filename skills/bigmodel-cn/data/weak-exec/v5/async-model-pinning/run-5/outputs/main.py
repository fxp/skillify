#!/usr/bin/env python3
"""
异步情感分类脚本
使用智谱AI异步对话接口对三句话进行情感分类
审计要求：锁定模型版本为 glm-4.6，核对接口实际使用的模型
"""

import os
import requests
import time
import json
from typing import List, Dict, Any

# API 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

# 模型配置
REQUESTED_MODEL = "glm-4.6"  # 用户请求的模型

# 情感分类任务的三句话
SENTENCES = [
    "今天天气真好，心情很愉快！",
    "这部电影太无聊了，浪费时间和金钱。",
    "我对这个结果感到有些平静。"
]

# 情感分类系统提示
SYSTEM_PROMPT = """
你是情感分析专家。请对给定的文本进行情感分类。
返回JSON格式，包含以下字段：
- sentiment: "positive" | "negative" | "neutral"
- confidence: 0.0到1.0之间的数字，表示分类的置信度
- emotion: 情绪关键词（如"高兴"、"愤怒"、"平静"等）
- keywords: 关键词列表，长度不超过5个
- analysis: 简短分析，说明分类理由

请严格按照JSON格式返回，不要输出多余文字。
"""


def get_headers() -> Dict[str, str]:
    """获取请求头"""
    if not API_KEY:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }


def submit_async_task(sentence: str) -> Dict[str, Any]:
    """提交异步任务"""
    url = f"{BASE_URL}/paas/v4/async/chat/completions"

    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": sentence}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 500
    }

    print(f"提交任务，请求模型: {REQUESTED_MODEL}")
    print(f"句子: {sentence}")

    response = requests.post(url, headers=get_headers(), json=payload, timeout=60)
    response.raise_for_status()

    result = response.json()
    print(f"任务ID: {result.get('id')}")
    print(f"初始状态: {result.get('task_status')}")
    print(f"响应中的模型: {result.get('model')}")

    # 审计核对：检查响应中的模型
    actual_model = result.get('model')
    if actual_model != REQUESTED_MODEL:
        print(f"⚠️ 审计警告：请求模型为 {REQUESTED_MODEL}，但接口实际使用模型为 {actual_model}")

    return result


def poll_async_result(task_id: str) -> Dict[str, Any]:
    """轮询异步任务结果"""
    url = f"{BASE_URL}/paas/v4/async-result/{task_id}"

    waited = 0
    max_wait = 120  # 最大等待时间120秒
    interval = 2    # 轮询间隔2秒

    while waited < max_wait:
        response = requests.get(url, headers=get_headers(), timeout=30)
        response.raise_for_status()

        result = response.json()
        status = result.get("task_status")

        if status == "SUCCESS":
            print(f"任务完成！最终模型: {result.get('model')}")

            # 审计核对：检查最终结果中的模型
            final_model = result.get('model')
            if final_model != REQUESTED_MODEL:
                print(f"⚠️ 审计警告：请求模型为 {REQUESTED_MODEL}，但最终结果使用的模型为 {final_model}")
            else:
                print(f"✅ 审计通过：请求模型与实际使用模型一致 ({REQUESTED_MODEL})")

            return result

        elif status == "FAIL":
            print(f"任务失败: {result}")
            raise RuntimeError(f"异步任务失败: {result}")

        print(f"等待中... 已等待 {waited} 秒，状态: {status}")
        time.sleep(interval)
        waited += interval

    raise TimeoutError(f"轮询超时，已等待 {max_wait} 秒")


def classify_sentiment(sentence: str) -> Dict[str, Any]:
    """对单个句子进行情感分类"""
    # 提交异步任务
    task_result = submit_async_task(sentence)
    task_id = task_result["id"]

    # 轮询结果
    result = poll_async_result(task_id)

    # 解析结果
    choice = result["choices"][0]
    message_content = choice["message"]["content"]

    # 解析JSON
    try:
        sentiment_result = json.loads(message_content)
        return {
            "sentence": sentence,
            "result": sentiment_result,
            "usage": result.get("usage", {})
        }
    except json.JSONDecodeError:
        print(f"⚠️ JSON解析失败: {message_content}")
        return {
            "sentence": sentence,
            "result": {"error": "JSON解析失败"},
            "content": message_content,
            "usage": result.get("usage", {})
        }


def main():
    """主函数"""
    print("开始异步情感分类任务")
    print("=" * 50)

    # 打印审计信息
    print(f"请求的模型: {REQUESTED_MODEL}")
    print(f"API Key: {API_KEY[:10]}...{API_KEY[-10:] if API_KEY else '未设置'}")
    print("-" * 50)

    results = []

    for i, sentence in enumerate(SENTENCES, 1):
        print(f"\n处理第 {i} 句:")
        print("=" * 30)

        try:
            result = classify_sentiment(sentence)
            results.append(result)

            # 打印分类结果
            if "error" in result["result"]:
                print(f"分类失败: {result['result']['error']}")
            else:
                sentiment = result["result"].get("sentiment", "unknown")
                confidence = result["result"].get("confidence", 0.0)
                emotion = result["result"].get("emotion", "unknown")
                keywords = result["result"].get("keywords", [])
                analysis = result["result"].get("analysis", "")

                print(f"情感: {sentiment}")
                print(f"置信度: {confidence}")
                print(f"情绪: {emotion}")
                print(f"关键词: {', '.join(keywords)}")
                print(f"分析: {analysis}")

            # 打印使用情况
            if result.get("usage"):
                usage = result["usage"]
                print(f"Token使用情况:")
                print(f"  输入: {usage.get('prompt_tokens', 0)}")
                print(f"  输出: {usage.get('completion_tokens', 0)}")
                print(f"  总计: {usage.get('total_tokens', 0)}")

        except Exception as e:
            print(f"处理失败: {e}")
            results.append({
                "sentence": sentence,
                "error": str(e)
            })

    # 最终审计报告
    print("\n" + "=" * 50)
    print("最终审计报告")
    print("=" * 50)

    # 检查所有结果
    model_issues = []
    for i, result in enumerate(results, 1):
        if isinstance(result.get("result"), dict) and "model" in result.get("result", {}):
            actual_model = result["result"].get("model")
            if actual_model != REQUESTED_MODEL:
                model_issues.append(f"第{i}句: 请求 {REQUESTED_MODEL}, 实际 {actual_model}")

    if model_issues:
        print("⚠️ 审计警告：模型版本不一致！")
        for issue in model_issues:
            print(f"  - {issue}")
    else:
        print("✅ 所有任务的模型版本一致，审计通过")

    print(f"\n请求的模型: {REQUESTED_MODEL}")
    print(f"API Key: {API_KEY[:10]}...{API_KEY[-10:] if API_KEY else '未设置'}")
    print("脚本执行完成")


if __name__ == "__main__":
    main()