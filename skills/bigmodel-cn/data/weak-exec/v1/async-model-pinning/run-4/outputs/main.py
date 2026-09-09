#!/usr/bin/env python3
"""
异步情感分类脚本
使用智谱AI异步接口对三句话做情感分类
锁定模型版本为 glm-4.6，审计要求打印模型版本进行核对
"""

import os
import json
import time
import requests
from typing import List, Dict, Any

# API 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

# 要进行情感分类的三句话
SENTENCES = [
    "今天天气真好，心情很愉快！",
    "这个产品太差了，我非常失望。",
    "这是一个普通的产品，没什么特别之处。"
]

# 锁定的模型版本
REQUESTED_MODEL = "glm-4.6"


def submit_async_chat(messages: List[Dict[str, Any]], model: str) -> Dict[str, Any]:
    """提交异步聊天任务"""
    url = f"{BASE_URL}/paas/v4/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 1000,
        "temperature": 0.1,  # 降低随机性，保持结果一致
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


def poll_async_result(task_id: str, timeout: int = 120, interval: int = 2) -> Dict[str, Any]:
    """轮询异步任务结果"""
    url = f"{BASE_URL}/paas/v4/async-result/{task_id}"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    waited = 0
    while waited < timeout:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        result = response.json()

        if result.get("task_status") == "SUCCESS":
            return result
        elif result.get("task_status") == "FAIL":
            raise RuntimeError(f"异步任务失败: {result}")

        time.sleep(interval)
        waited += interval

    raise TimeoutError(f"轮询超时，已等待 {timeout} 秒")


def perform_sentiment_analysis(sentence: str, index: int) -> Dict[str, Any]:
    """对单句话进行情感分析"""
    # 构建系统消息，要求进行情感分类
    system_message = """你是一个情感分析专家。请对输入的文本进行情感分类，返回 JSON 格式结果：
{
    "sentiment": "positive/negative/neutral",
    "confidence": 0.0-1.0的数值,
    "analysis": "简要分析理由"
}

请严格按照上述 JSON 格式返回，不要输出其他内容。"""

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": f"请分析以下文本的情感：{sentence}"}
    ]

    print(f"\n正在处理第 {index + 1} 句话: {sentence}")

    # 提交异步任务
    task_response = submit_async_chat(messages, REQUESTED_MODEL)
    actual_model_in_task = task_response.get("model")
    task_id = task_response.get("id")

    # 审计要求：打印请求的模型和接口实际使用的模型
    print(f"请求的模型: {REQUESTED_MODEL}")
    print(f"提交任务时接口返回的模型: {actual_model_in_task}")

    # 检查模型版本是否一致（异步接口可能会静默替换模型）
    if actual_model_in_task != REQUESTED_MODEL:
        print(f"⚠️  警告：提交任务时接口实际使用的模型 ({actual_model_in_task}) 与请求的模型 ({REQUESTED_MODEL}) 不一致！")

    # 轮询获取结果
    result = poll_async_result(task_id)
    actual_model_in_result = result.get("model")

    print(f"最终结果回显的模型: {actual_model_in_result}")

    # 再次检查最终结果中的模型版本
    if actual_model_in_result != REQUESTED_MODEL:
        print(f"⚠️  警告：最终结果中使用的模型 ({actual_model_in_result}) 与请求的模型 ({REQUESTED_MODEL}) 不一致！")
        print("⚠️  警告：模型版本不一致可能影响分析结果的准确性和可复现性！")

    # 提取响应内容
    choices = result.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        # 尝试解析 JSON
        try:
            analysis_result = json.loads(content)
        except json.JSONDecodeError:
            # 如果解析失败，返回原始内容
            analysis_result = {"raw_response": content, "error": "JSON解析失败"}

        # 添加额外信息
        analysis_result["sentence"] = sentence
        analysis_result["task_id"] = task_id
        analysis_result["actual_models"] = {
            "submitted_model": actual_model_in_task,
            "result_model": actual_model_in_result,
            "requested_model": REQUESTED_MODEL
        }

        return analysis_result
    else:
        return {
            "error": "没有返回有效结果",
            "sentence": sentence,
            "task_id": task_id,
            "actual_models": {
                "submitted_model": actual_model_in_task,
                "result_model": actual_model_in_result,
                "requested_model": REQUESTED_MODEL
            }
        }


def main():
    """主函数：批量处理三句话的情感分类"""
    print("=" * 60)
    print("开始批量情感分析任务")
    print("=" * 60)
    print(f"请求的模型版本: {REQUESTED_MODEL}")
    print(f"要分析的句子数量: {len(SENTENCES)}")
    print("-" * 60)

    results = []

    # 处理每一句话
    for i, sentence in enumerate(SENTENCES):
        try:
            result = perform_sentiment_analysis(sentence, i)
            results.append(result)

            # 打印单句话的处理结果
            if "error" not in result:
                print(f"\n第 {i + 1} 句话分析结果:")
                print(f"情感: {result['sentiment']}")
                print(f"置信度: {result['confidence']}")
                print(f"分析: {result['analysis']}")
            else:
                print(f"\n第 {i + 1} 句话分析失败: {result['error']}")

        except Exception as e:
            error_result = {
                "sentence": sentence,
                "error": str(e),
                "index": i
            }
            results.append(error_result)
            print(f"\n第 {i + 1} 句话处理失败: {e}")

        print("-" * 60)

    # 汇总报告
    print("\n" + "=" * 60)
    print("批量情感分析汇总报告")
    print("=" * 60)

    # 检查模型一致性
    model_consistency_issues = []
    for i, result in enumerate(results):
        if "actual_models" in result:
            models = result["actual_models"]
            if models["submitted_model"] != models["requested_model"]:
                model_consistency_issues.append((i + 1, "submitted"))
            if models["result_model"] != models["requested_model"]:
                model_consistency_issues.append((i + 1, "result"))

    if model_consistency_issues:
        print("⚠️  模型版本一致性警告：")
        for issue in model_consistency_issues:
            print(f"  第 {issue[0]} 句话: {issue[1]} 阶段模型不一致")
        print()
    else:
        print("✓ 所有句子都通过了模型一致性检查")
        print()

    # 统计各情感类型
    sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
    valid_results = 0

    for result in results:
        if "sentiment" in result:
            sentiment = result["sentiment"].lower()
            if sentiment in sentiment_counts:
                sentiment_counts[sentiment] += 1
            valid_results += 1

    print(f"有效分析结果: {valid_results}/{len(SENTENCES)}")
    print("情感分布:")
    for sentiment, count in sentiment_counts.items():
        if count > 0:
            print(f"  {sentiment}: {count} 句")

    # 保存完整结果到文件
    with open("/tmp/batch_sentiment_analysis_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "requested_model": REQUESTED_MODEL,
            "total_sentences": len(SENTENCES),
            "valid_results": valid_results,
            "results": results,
            "model_consistency_issues": model_consistency_issues,
            "sentiment_counts": sentiment_counts
        }, f, ensure_ascii=False, indent=2)

    print(f"\n完整结果已保存到: /tmp/batch_sentiment_analysis_results.json")


if __name__ == "__main__":
    # 检查 API Key
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        print("例如: export ZHIPUAI_API_KEY='your_api_key_here'")
        exit(1)

    main()