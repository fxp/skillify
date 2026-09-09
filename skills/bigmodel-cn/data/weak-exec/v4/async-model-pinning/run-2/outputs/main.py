#!/usr/bin/env python3
"""
使用智谱AI异步对话接口（async/chat/completions）进行情感分类
对三句话做情感分类，并检查模型版本锁定情况
"""

import os
import json
import time
import requests
from typing import List, Dict, Any

# API配置
API_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

# 请求的模型（审计要求）
REQUESTED_MODEL = "glm-4.6"

# 三句话情感分类任务
SENTENCES = [
    "今天天气真好，心情很愉快！",
    "这个产品质量太差了，完全不值这个价钱。",
    "我不知道该说什么，就这样吧。"
]

def submit_async_task(sentence: str, model: str) -> Dict[str, Any]:
    """提交异步任务"""
    url = f"{API_BASE_URL}/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是情感分析专家。请对用户的文本进行情感分类，返回JSON格式：{\"sentiment\": \"positive/negative/neutral\", \"confidence\": 0.0-1.0, \"keywords\": [], \"analysis\": \"...\"}"
            },
            {
                "role": "user",
                "content": f"请分析以下文本的情感：{sentence}"
            }
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 500
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()

def poll_async_result(task_id: str, api_key: str, interval: int = 2, timeout: int = 120) -> Dict[str, Any]:
    """轮询异步结果"""
    url = f"{API_BASE_URL}/async-result/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

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

        time.sleep(interval)
        waited += interval

    raise TimeoutError(f"轮询超时，已等待 {timeout} 秒")

def analyze_sentences_batch(sentences: List[str], requested_model: str) -> List[Dict[str, Any]]:
    """批量分析句子情感"""
    if not API_KEY:
        raise ValueError("未设置 ZHIPUAI_API_KEY 环境变量")

    results = []
    task_ids = []

    print("=" * 60)
    print("开始批量情感分析任务")
    print(f"请求的模型版本: {requested_model}")
    print("=" * 60)

    # 提交所有异步任务
    for i, sentence in enumerate(sentences):
        print(f"\n提交任务 {i+1}/{len(sentences)}: {sentence[:30]}...")
        task = submit_async_task(sentence, requested_model)
        task_id = task["id"]
        task_ids.append(task_id)
        print(f"任务ID: {task_id}")

        # 保存请求的模型信息（审计用）
        task["requested_model"] = requested_model
        task["sentence"] = sentence

    print("\n" + "=" * 60)
    print("所有任务已提交，开始轮询结果...")
    print("=" * 60)

    # 轮询所有任务结果
    for i, (task_id, task_info) in enumerate(zip(task_ids, task_ids)):
        print(f"\n轮询任务 {i+1}/{len(task_ids)}: {task_id}")

        result = poll_async_result(task_id, API_KEY)

        # 获取实际使用的模型
        actual_model = result.get("model", "unknown")

        # 审计检查：模型版本是否一致
        requested_model = result.get("requested_model", requested_model)
        model_match = actual_model == requested_model

        print(f"请求的模型: {requested_model}")
        print(f"实际使用的模型: {actual_model}")

        # 审计警告
        if not model_match:
            print("⚠️  审计警告：模型版本不匹配！")
            print("   这可能影响分析结果的准确性！")

        # 提取情感分析结果
        if "choices" in result and result["choices"]:
            message = result["choices"][0]["message"]["content"]
            try:
                sentiment_data = json.loads(message)
            except json.JSONDecodeError:
                sentiment_data = {"sentiment": "error", "confidence": 0.0, "analysis": "JSON解析失败"}

            result_data = {
                "sentence": task_info,
                "requested_model": requested_model,
                "actual_model": actual_model,
                "model_match": model_match,
                "sentiment": sentiment_data,
                "usage": result.get("usage", {})
            }
            results.append(result_data)

        print(f"分析完成: {sentiment_data.get('sentiment', 'unknown')}")

    return results

def main():
    """主函数"""
    try:
        # 执行批量分析
        results = analyze_sentences_batch(SENTENCES, REQUESTED_MODEL)

        # 输出最终结果
        print("\n" + "=" * 60)
        print("情感分析结果汇总")
        print("=" * 60)

        for i, result in enumerate(results, 1):
            print(f"\n句子 {i}: {result['sentence']}")
            print(f"模型版本检查: {'✓' if result['model_match'] else '❌'}")
            print(f"请求模型: {result['requested_model']}")
            print(f"实际模型: {result['actual_model']}")
            print(f"情感: {result['sentiment'].get('sentiment', 'unknown')}")
            print(f"置信度: {result['sentiment'].get('confidence', 0.0):.2f}")
            print(f"关键词: {result['sentiment'].get('keywords', [])}")
            print(f"分析: {result['sentiment'].get('analysis', '')}")
            print(f"Token使用: 输入{result['usage'].get('prompt_tokens', 0)}, "
                  f"输出{result['usage'].get('completion_tokens', 0)}, "
                  f"总计{result['usage'].get('total_tokens', 0)}")

        # 审计汇总
        print("\n" + "=" * 60)
        print("审计报告")
        print("=" * 60)

        model_mismatches = [r for r in results if not r['model_match']]
        if model_mismatches:
            print(f"⚠️  发现 {len(model_mismatches)} 个模型版本不匹配:")
            for result in model_mismatches:
                print(f"  - 句子: {result['sentence'][:30]}...")
                print(f"    请求: {result['requested_model']}, 实际: {result['actual_model']}")
        else:
            print("✓ 所有任务使用模型版本一致")

        print(f"\n共处理 {len(results)} 个句子")
        print(f"请求模型: {REQUESTED_MODEL}")

    except Exception as e:
        print(f"错误: {str(e)}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())