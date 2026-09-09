#!/usr/bin/env python3
"""
使用智谱AI异步对话接口进行批量情感分类
锁定模型版本：glm-4.6
包含审计要求：核对请求模型和实际使用的模型
"""

import os
import requests
import time
import json
from typing import List, Dict, Any, Optional

# 配置
API_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
API_KEY = os.getenv("ZHIPUAI_API_KEY")
REQUESTED_MODEL = "glm-4.6"

# 三句话情感分类任务
SENTENCES = [
    "今天天气真好，心情非常愉快！",
    "这个产品完全不符合我的期望，太失望了。",
    "虽然结果不如预期，但还是学到了很多。"
]

def submit_async_chat_completion(sentence: str, model: str) -> Dict[str, Any]:
    """提交异步对话任务"""
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
                "content": "你是一个情感分类助手。请对用户输入的文本进行情感分类，只返回一个词：'积极'、'消极'或'中性'。"
            },
            {
                "role": "user",
                "content": f"请分类这句话的情感：{sentence}"
            }
        ],
        "max_tokens": 10,
        "temperature": 0.1
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"提交异步任务失败: {e}")

def poll_async_result(task_id: str, timeout: int = 300, interval: int = 2) -> Dict[str, Any]:
    """轮询异步任务结果"""
    url = f"{API_BASE_URL}/async-result/{task_id}"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    waited = 0
    while waited < timeout:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()

            if result.get("task_status") == "SUCCESS":
                return result
            elif result.get("task_status") == "FAIL":
                raise RuntimeError(f"任务失败: {result}")

            time.sleep(interval)
            waited += interval
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"轮询结果失败: {e}")

    raise TimeoutError(f"轮询超时，已等待 {timeout} 秒")

def perform_sentiment_analysis() -> None:
    """执行批量情感分类"""
    if not API_KEY:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY")
        return

    print("=" * 60)
    print("智谱AI异步接口情感分类任务")
    print("=" * 60)
    print(f"请求的模型: {REQUESTED_MODEL}")
    print(f"API Key: {API_KEY[:10]}...")
    print("-" * 60)

    results = []

    for i, sentence in enumerate(SENTENCES, 1):
        print(f"\n处理第 {i} 句话...")
        print(f"文本: {sentence}")

        # 提交异步任务
        print("\n1. 提交异步任务...")
        try:
            task_response = submit_async_chat_completion(sentence, REQUESTED_MODEL)
            task_id = task_response.get("id")
            task_status = task_response.get("task_status")
            actual_model = task_response.get("model")

            print(f"任务ID: {task_id}")
            print(f"任务状态: {task_status}")
            print(f"接口实际使用的模型: {actual_model}")

            # 审计检查：模型版本是否一致
            if actual_model != REQUESTED_MODEL:
                print(f"\n⚠️  警告: 模型版本不一致!")
                print(f"   请求的模型: {REQUESTED_MODEL}")
                print(f"   实际使用的模型: {actual_model}")
                print(f"   这可能影响结果的一致性和可复现性!")
            else:
                print(f"\n✓ 模型版本一致: {REQUESTED_MODEL}")

            # 轮询结果
            print("\n2. 轮询任务结果...")
            result = poll_async_result(task_id)

            # 最终审计检查
            final_model = result.get("model")
            if final_model != REQUESTED_MODEL:
                print(f"\n⚠️  警告: 最终结果模型版本不一致!")
                print(f"   请求的模型: {REQUESTED_MODEL}")
                print(f"   最终结果使用的模型: {final_model}")
            else:
                print(f"\n✓ 最终结果模型版本一致: {final_model}")

            # 提取情感分类结果
            if result.get("choices"):
                content = result["choices"][0]["message"]["content"].strip()
                sentiment = content
            else:
                sentiment = "分类失败"

            print(f"\n3. 分类结果: {sentiment}")

            # 记录结果
            results.append({
                "sentence": sentence,
                "sentiment": sentiment,
                "task_id": task_id,
                "requested_model": REQUESTED_MODEL,
                "actual_model_at_submission": actual_model,
                "actual_model_at_completion": final_model,
                "consistent": actual_model == REQUESTED_MODEL and final_model == REQUESTED_MODEL
            })

            print("\n" + "-" * 40)

        except Exception as e:
            print(f"错误: {e}")
            results.append({
                "sentence": sentence,
                "sentiment": f"处理失败: {str(e)}",
                "task_id": None,
                "requested_model": REQUESTED_MODEL,
                "actual_model_at_submission": None,
                "actual_model_at_completion": None,
                "consistent": False
            })

    # 输出最终报告
    print("\n" + "=" * 60)
    print("批量情感分类完成 - 审计报告")
    print("=" * 60)

    print("\n详细结果:")
    for i, result in enumerate(results, 1):
        print(f"\n{i}. 文本: {result['sentence']}")
        print(f"   情感: {result['sentiment']}")
        print(f"   请求的模型: {result['requested_model']}")
        print(f"   提交时实际模型: {result['actual_model_at_submission']}")
        print(f"   完成时实际模型: {result['actual_model_at_completion']}")
        print(f"   模型一致性: {'✓ 一致' if result['consistent'] else '⚠️ 不一致'}")

    # 审计总结
    all_consistent = all(r['consistent'] for r in results)
    print("\n" + "=" * 60)
    print("审计总结")
    print("=" * 60)
    print(f"请求的模型: {REQUESTED_MODEL}")
    print(f"所有任务模型一致性: {'✓ 全部一致' if all_consistent else '⚠️ 存在不一致'}")

    if not all_consistent:
        print("\n⚠️  重要提醒: 模型版本不一致可能影响:")
        print("- 结果的可复现性")
        print("- 审计追踪的准确性")
        print("- 业务的稳定性")
        print("\n建议检查是否需要调整模型参数或联系平台支持。")

if __name__ == "__main__":
    perform_sentiment_analysis()