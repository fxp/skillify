#!/usr/bin/env python3
"""
情感分类脚本 - 使用智谱异步API
对三句话做情感分类，审计要求锁定模型版本 glm-4.6
"""

import os
import json
import time
import requests
from typing import List, Dict, Any

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
REQUESTED_MODEL = "glm-4.6"

# 待分类的三句话
SENTENCES = [
    "今天天气真好，心情很愉快！",
    "这个产品太差了，完全不值这个价钱。",
    "我觉得这部电影还可以，没有特别惊艳。"
]

def submit_async_task(sentence: str, api_key: str) -> Dict[str, Any]:
    """提交异步任务"""
    url = f"{BASE_URL}/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是情感分析专家。请对用户输入的文本进行情感分类，返回JSON格式：{\"sentiment\": \"positive|negative|neutral\", \"confidence\": 0.0-1.0的数字, \"analysis\": \"简要分析\"}"
            },
            {
                "role": "user",
                "content": f"请分析以下文本的情感：{sentence}"
            }
        ],
        "max_tokens": 500,
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"提交异步任务失败: {e}")

def poll_async_result(task_id: str, api_key: str, interval: int = 2, timeout: int = 120) -> Dict[str, Any]:
    """轮询异步任务结果"""
    url = f"{BASE_URL}/async-result/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    waited = 0
    while waited < timeout:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()

            task_status = result.get("task_status")
            if task_status == "SUCCESS":
                return result
            elif task_status == "FAIL":
                raise RuntimeError(f"异步任务失败: {result}")

            # 还在处理中，继续等待
            time.sleep(interval)
            waited += interval
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"轮询结果失败: {e}")

    raise TimeoutError(f"轮询超时，等待时间超过 {timeout} 秒")

def analyze_model_pinning(requested_model: str, actual_model: str) -> str:
    """分析模型版本锁定情况"""
    if requested_model == actual_model:
        return f"✓ 模型版本锁定成功: 请求 {requested_model}, 实际 {actual_model}"
    else:
        return f"⚠️ 模型版本不匹配! 请求 {requested_model}, 实际 {actual_model} - 审计警告!"

def main():
    print("=== 情感分析任务开始 ===")
    print(f"请求的模型版本: {REQUESTED_MODEL}")
    print("=" * 50)

    results = []

    # 对每个句子进行情感分析
    for i, sentence in enumerate(SENTENCES, 1):
        print(f"\n📝 处理句子 {i}/{len(SENTENCES)}: {sentence}")
        print("-" * 50)

        try:
            # 提交异步任务
            print("🚀 提交异步任务...")
            task_response = submit_async_task(sentence, API_KEY)

            # 获取任务信息
            task_id = task_response.get("id")
            task_model = task_response.get("model", "unknown")

            print(f"📋 任务ID: {task_id}")
            print(f"📋 任务回显模型: {task_model}")

            # 轮询结果
            print("⏳ 等待处理完成...")
            result = poll_async_result(task_id, API_KEY)

            # 获取实际使用的模型
            actual_model = result.get("model", "unknown")

            # 分析模型锁定情况
            model_check = analyze_model_pinning(REQUESTED_MODEL, actual_model)
            print(f"\n🔍 {model_check}")

            # 提取分析结果
            if "choices" in result and result["choices"]:
                content = result["choices"][0]["message"]["content"]
                try:
                    # 解析JSON响应
                    analysis = json.loads(content)
                    results.append({
                        "sentence": sentence,
                        "sentiment": analysis.get("sentiment", "unknown"),
                        "confidence": analysis.get("confidence", 0.0),
                        "analysis": analysis.get("analysis", ""),
                        "requested_model": REQUESTED_MODEL,
                        "actual_model": actual_model
                    })
                    print(f"✅ 分析完成:")
                    print(f"   情感: {analysis.get('sentiment')}")
                    print(f"   置信度: {analysis.get('confidence')}")
                    print(f"   分析: {analysis.get('analysis')}")
                except json.JSONDecodeError:
                    print(f"❌ JSON解析失败，原始响应: {content}")
            else:
                print("❌ 无返回结果")

        except Exception as e:
            print(f"❌ 处理失败: {e}")
            results.append({
                "sentence": sentence,
                "error": str(e),
                "requested_model": REQUESTED_MODEL,
                "actual_model": "unknown"
            })

    # 输出汇总报告
    print("\n" + "=" * 60)
    print("📊 汇总报告")
    print("=" * 60)

    for i, result in enumerate(results, 1):
        print(f"\n句子 {i}: {result['sentence']}")
        if "error" in result:
            print(f"   错误: {result['error']}")
        else:
            print(f"   情感: {result['sentiment']}")
            print(f"   置信度: {result['confidence']}")
            print(f"   分析: {result['analysis']}")
        print(f"   请求模型: {result['requested_model']}")
        print(f"   实际模型: {result['actual_model']}")

    # 检查所有模型的锁定情况
    print("\n" + "=" * 60)
    print("🔍 模型锁定审计报告")
    print("=" * 60)

    all_models_match = True
    for result in results:
        if "error" not in result:
            if result['requested_model'] != result['actual_model']:
                all_models_match = False
                print(f"❌ 不匹配: 请求 {result['requested_model']}, 实际 {result['actual_model']}")
            else:
                print(f"✅ 匹配: {result['actual_model']}")

    if all_models_match and not any("error" in r for r in results):
        print("\n🎉 所有任务模型版本锁定成功，审计通过!")
    else:
        print("\n⚠️ 模型锁定审计发现问题，请检查!")

if __name__ == "__main__":
    main()