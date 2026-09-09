#!/usr/bin/env python3
"""
异步批量情感分类脚本
使用智谱GLM-4.6异步接口对三句话做情感分类
审计要求：检查并打印请求的模型和实际使用的模型
"""

import os
import json
import time
import requests
from typing import List, Dict, Any

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

# 要做情感分类的三句话
TEXTS = [
    "今天天气真好，心情非常愉快！",
    "这个产品太差了，完全不值这个价钱。",
    "明天可能会下雨，记得带伞。"
]

# 请求的模型
REQUESTED_MODEL = "glm-4.6"

def submit_async_chat(text: str, model: str) -> Dict[str, Any]:
    """提交异步聊天任务"""
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
                "content": "你是情感分析专家。请分析以下文本的情感，并按照JSON格式返回：{\"sentiment\": \"positive\"|\"negative\"|\"neutral\", \"confidence\": 0.0-1.0, \"analysis\": \"详细分析\"}"
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

def poll_async_result(task_id: str, timeout: int = 120, interval: int = 2) -> Dict[str, Any]:
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

        task_status = result.get("task_status")
        if task_status == "SUCCESS":
            return result
        elif task_status == "FAIL":
            raise RuntimeError(f"异步任务失败: {result}")

        time.sleep(interval)
        waited += interval

    raise TimeoutError(f"轮询超时，等待时间: {timeout}秒")

def analyze_sentiment_batch(texts: List[str]) -> List[Dict[str, Any]]:
    """批量情感分析"""
    results = []

    print(f"开始批量情感分析，共{len(texts)}条文本")
    print(f"请求的模型版本: {REQUESTED_MODEL}")
    print("-" * 50)

    for i, text in enumerate(texts, 1):
        print(f"处理第{i}条: {text}")

        try:
            # 1. 提交异步任务
            print("  提交异步任务...")
            task_response = submit_async_chat(text, REQUESTED_MODEL)
            task_id = task_response["id"]
            actual_model = task_response.get("model", "unknown")

            # 2. 打印模型信息（审计要求）
            print(f"  任务ID: {task_id}")
            print(f"  提交后回显模型: {actual_model}")

            # 3. 轮询结果
            print("  轮询结果...")
            final_result = poll_async_result(task_id)
            response_model = final_result.get("model", "unknown")

            # 4. 打印最终模型信息（审计要求）
            print(f"  最终响应模型: {response_model}")

            # 5. 模型一致性检查（审计要求）
            model_mismatch = False
            if REQUESTED_MODEL != actual_model:
                print(f"  ⚠️  警告：提交阶段模型不一致！请求了{REQUESTED_MODEL}，实际使用了{actual_model}")
                model_mismatch = True

            if REQUESTED_MODEL != response_model:
                print(f"  ⚠️  警告：响应阶段模型不一致！请求了{REQUESTED_MODEL}，实际使用了{response_model}")
                model_mismatch = True

            if model_mismatch:
                print("  🔴 严重警告：模型版本不匹配！审计要求必须一致！")
            else:
                print(f"  ✅ 模型版本一致：{REQUESTED_MODEL}")

            print("  分析结果:")

            # 6. 解析结果
            choice = final_result.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")

            # 尝试解析JSON
            try:
                sentiment_data = json.loads(content)
                print(f"    情感: {sentiment_data.get('sentiment', 'unknown')}")
                print(f"    置信度: {sentiment_data.get('confidence', 'unknown')}")
                print(f"    分析: {sentiment_data.get('analysis', 'unknown')}")
            except json.JSONDecodeError:
                print(f"    原始回复: {content}")

            # 7. 记录使用情况
            usage = final_result.get("usage", {})
            results.append({
                "text": text,
                "sentiment_raw": content,
                "requested_model": REQUESTED_MODEL,
                "submitted_model": actual_model,
                "response_model": response_model,
                "model_mismatch": model_mismatch,
                "usage": usage,
                "task_id": task_id
            })

            print("-" * 50)

        except Exception as e:
            print(f"  ❌ 处理失败: {str(e)}")
            results.append({
                "text": text,
                "error": str(e),
                "requested_model": REQUESTED_MODEL
            })
            print("-" * 50)

    return results

def main():
    """主函数"""
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        print("export ZHIPUAI_API_KEY='your_api_key_here'")
        return

    print("智谱AI异步情感分析脚本")
    print("=" * 50)

    # 执行批量分析
    try:
        analysis_results = analyze_sentiment_batch(TEXTS)

        # 汇总报告
        print("\n" + "=" * 50)
        print("审计汇总报告")
        print("=" * 50)
        print(f"总文本数: {len(TEXTS)}")
        print(f"成功处理: {len([r for r in analysis_results if 'error' not in r])}")
        print(f"失败处理: {len([r for r in analysis_results if 'error' in r])}")

        # 模型使用情况
        model_submissions = {}
        model_responses = {}
        mismatches = 0

        for result in analysis_results:
            if 'error' not in result:
                submitted = result.get('submitted_model', 'unknown')
                response = result.get('response_model', 'unknown')

                model_submissions[submitted] = model_submissions.get(submitted, 0) + 1
                model_responses[response] = model_responses.get(response, 0) + 1

                if result.get('model_mismatch', False):
                    mismatches += 1

        print(f"\n模型使用统计:")
        print(f"提交阶段: {dict(model_submissions)}")
        print(f"响应阶段: {dict(model_responses)}")

        if mismatches > 0:
            print(f"\n🔴 警告：发现 {mismatches} 次模型版本不匹配！")
            print("这违反了审计要求，必须确保请求的模型和实际使用的模型一致！")
        else:
            print(f"\n✅ 所有请求的模型版本均为: {REQUESTED_MODEL}")
            print("审计要求满足：请求的模型和实际使用的模型一致")

    except Exception as e:
        print(f"脚本执行失败: {str(e)}")

if __name__ == "__main__":
    main()