#!/usr/bin/env python3
"""
智谱AI异步对话接口情感分类任务
使用 async/chat/completions 接口进行批量处理，并严格审计模型版本
"""

import os
import requests
import json
import time
from typing import List, Dict, Any

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"
REQUESTED_MODEL = "glm-4.6"  # 用户请求的模型版本

# 三句话情感分类任务
TEXTS_TO_CLASSIFY = [
    "今天天气真好，心情非常愉快！",
    "这个产品太差了，完全不值这个价钱。",
    "昨晚的电影还不错，但情节有些拖沓。"
]

# 情感分析系统提示
SYSTEM_PROMPT = """你是一个情感分析专家。请对输入的文本进行情感分类，返回JSON格式结果，包含以下字段：
- sentiment: "positive" | "negative" | "neutral"
- confidence: 0.0-1.0 的浮点数
- keywords: 相关关键词列表
- analysis: 简要分析说明

请严格按照JSON格式返回，不要输出其他内容。"""

def submit_async_task(text: str, api_key: str) -> Dict[str, Any]:
    """提交异步任务"""
    url = f"{BASE_URL}/paas/v4/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请对以下文本进行情感分类：{text}"}
        ],
        "response_format": {"type": "json_object"}
    }

    print(f"提交任务，请求模型：{REQUESTED_MODEL}")
    print(f"文本：{text}")

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()

def poll_async_result(task_id: str, api_key: str, max_retries=30, interval=2) -> Dict[str, Any]:
    """轮询异步任务结果"""
    url = f"{BASE_URL}/paas/v4/async-result/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    print(f"开始轮询任务 {task_id}，最多等待 {max_retries * interval} 秒...")

    for i in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            result = resp.json()

            status = result.get("task_status")
            print(f"轮询第 {i+1} 次，状态：{status}")

            if status == "SUCCESS":
                return result
            elif status == "FAIL":
                raise RuntimeError(f"任务失败：{result}")
            else:
                time.sleep(interval)

        except requests.exceptions.RequestException as e:
            print(f"轮询请求异常：{e}")
            if i == max_retries - 1:
                raise
            time.sleep(interval)

    raise TimeoutError(f"轮询超时，任务 {task_id} 在 {max_retries * interval} 秒内未完成")

def analyze_sentiment(text: str, api_key: str) -> Dict[str, Any]:
    """执行情感分析任务"""
    # 1. 提交异步任务
    task_response = submit_async_task(text, api_key)
    task_id = task_response["id"]
    requested_model = task_response["model"]

    print(f"✅ 任务提交成功")
    print(f"   - 任务ID：{task_id}")
    print(f"   - 请求模型：{requested_model}")
    print(f"   - 任务状态：{task_response.get('task_status')}")

    # 2. 审计模型版本
    if requested_model != REQUESTED_MODEL:
        print(f"⚠️  警告：请求的模型版本不一致！")
        print(f"   - 请求的模型：{REQUESTED_MODEL}")
        print(f"   - 实际使用的模型：{requested_model}")
        print(f"   - 这不符合审计要求，需要立即上报！")
    else:
        print(f"✅ 模型版本一致：{REQUESTED_MODEL}")

    # 3. 轮询结果
    result = poll_async_result(task_id, api_key)

    # 4. 检查最终响应中的模型版本
    actual_model = result.get("model", "未知")
    if actual_model != REQUESTED_MODEL:
        print(f"⚠️  警告：接口实际使用的模型版本不一致！")
        print(f"   - 请求的模型：{REQUESTED_MODEL}")
        print(f"   - 接口实际使用的模型：{actual_model}")
        print(f"   - 这不符合审计要求，需要立即上报！")
    else:
        print(f"✅ 接口实际使用的模型版本一致：{actual_model}")

    # 5. 提取结果
    if "choices" in result and result["choices"]:
        message = result["choices"][0]["message"]["content"]
        try:
            # 解析JSON响应
            sentiment_data = json.loads(message)

            # 确保是有效的情感分析结果
            if "sentiment" in sentiment_data:
                return {
                    "text": text,
                    "requested_model": requested_model,
                    "actual_model": actual_model,
                    "sentiment": sentiment_data,
                    "usage": result.get("usage", {}),
                    "model_consistent": requested_model == REQUESTED_MODEL and actual_model == REQUESTED_MODEL
                }
            else:
                print(f"⚠️  返回的JSON格式不正确：{message}")
                return {
                    "text": text,
                    "requested_model": requested_model,
                    "actual_model": actual_model,
                    "error": "返回的JSON格式不正确",
                    "raw_response": message,
                    "model_consistent": requested_model == REQUESTED_MODEL and actual_model == REQUESTED_MODEL
                }
        except json.JSONDecodeError as e:
            print(f"⚠️  JSON解析失败：{e}")
            print(f"   原始响应：{message}")
            return {
                "text": text,
                "requested_model": requested_model,
                "actual_model": actual_model,
                "error": "JSON解析失败",
                "raw_response": message,
                "model_consistent": requested_model == REQUESTED_MODEL and actual_model == REQUESTED_MODEL
            }
    else:
        print(f"⚠️  响应中没有choices字段：{result}")
        return {
            "text": text,
            "requested_model": requested_model,
            "actual_model": actual_model,
            "error": "响应中没有choices字段",
            "full_response": result,
            "model_consistent": requested_model == REQUESTED_MODEL and actual_model == REQUESTED_MODEL
        }

def main():
    """主函数"""
    print("=" * 60)
    print("智谱AI异步接口情感分类任务")
    print("=" * 60)

    # 检查API Key
    if not API_KEY:
        print("❌ 错误：未设置环境变量 ZHIPUAI_API_KEY")
        return

    print(f"📋 任务配置：")
    print(f"   - 请求模型：{REQUESTED_MODEL}")
    print(f"   - 处理文本数量：{len(TEXTS_TO_CLASSIFY)}")
    print(f"   - API Key：{API_KEY[:8]}...{API_KEY[-4:]}")
    print()

    # 执行批量任务
    results = []
    for i, text in enumerate(TEXTS_TO_CLASSIFY, 1):
        print(f"🔄 处理第 {i}/{len(TEXTS_TO_CLASSIFY)} 条文本")
        print("-" * 50)

        try:
            result = analyze_sentiment(text, API_KEY)
            results.append(result)

            # 打印简要结果
            if "sentiment" in result:
                print(f"✅ 情感分类成功：{result['sentiment']['sentiment']}")
                print(f"   置信度：{result['sentiment']['confidence']}")
                print(f"   关键词：{', '.join(result['sentiment']['keywords'])}")
            else:
                print(f"❌ 处理失败：{result.get('error', '未知错误')}")

            print(f"   模型一致性：{'✅ 一致' if result.get('model_consistent', False) else '❌ 不一致'}")
            print()

        except Exception as e:
            print(f"❌ 处理失败：{e}")
            results.append({
                "text": text,
                "error": str(e),
                "model_consistent": False
            })
            print()

    # 汇总报告
    print("=" * 60)
    print("📊 任务汇总报告")
    print("=" * 60)

    # 统计模型一致性
    consistent_count = sum(1 for r in results if r.get("model_consistent", False))
    print(f"模型一致性检查：{consistent_count}/{len(results)} 条任务一致")

    if consistent_count != len(results):
        print("⚠️  发现模型版本不一致的任务，请立即审计！")
        for result in results:
            if not result.get("model_consistent", False):
                print(f"   - 文本：{result['text'][:50]}...")
                print(f"     请求模型：{result.get('requested_model', '未知')}")
                print(f"     实际模型：{result.get('actual_model', '未知')}")
                print()
    else:
        print("✅ 所有任务模型版本一致，符合审计要求")

    # 打印所有详细结果
    print("\n📝 详细结果：")
    for i, result in enumerate(results, 1):
        print(f"\n{i}. 文本：{result['text']}")
        if "sentiment" in result:
            sentiment = result["sentiment"]
            print(f"   情感：{sentiment['sentiment']}")
            print(f"   置信度：{sentiment['confidence']}")
            print(f"   关键词：{', '.join(sentiment['keywords'])}")
            print(f"   分析：{sentiment['analysis']}")
        else:
            print(f"   状态：{result.get('error', '未知错误')}")

        print(f"   请求模型：{result.get('requested_model', '未知')}")
        print(f"   实际模型：{result.get('actual_model', '未知')}")
        print(f"   一致性：{'✅' if result.get('model_consistent', False) else '❌'}")

if __name__ == "__main__":
    main()