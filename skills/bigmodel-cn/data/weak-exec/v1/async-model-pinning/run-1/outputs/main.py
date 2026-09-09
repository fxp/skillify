#!/usr/bin/env python3
"""
批量情感分析脚本
使用智谱AI异步接口对三句话进行情感分类
锁定模型版本为 glm-4.6，审计要求核对请求与响应的模型一致性
"""

import os
import json
import time
import requests
from typing import List, Dict, Any


# 配置
API_BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
TARGET_MODEL = "glm-4.6"  # 请求时指定的模型
PROMPT = """
你是一个情感分析专家。请对以下文本进行情感分析，只返回JSON格式的结果，不要包含其他文字。
JSON格式要求：
{
  "sentiment": "positive|negative|neutral",
  "confidence": 0.0-1.0,
  "analysis": "简要分析"
}

文本：
"""

# 要分析的句子
SENTENCES = [
    "今天天气真好，心情很愉快！",
    "工作压力很大，感觉快要坚持不下去了。",
    "这部电影还不错，但情节有些老套。"
]


def submit_async_task(sentence: str, api_key: str) -> Dict[str, Any]:
    """提交异步任务"""
    url = f"{API_BASE_URL}/paas/v4/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": TARGET_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是情感分析专家，严格按照指定JSON格式返回结果。"
            },
            {
                "role": "user",
                "content": f"{PROMPT}\n{sentence}"
            }
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 500
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()

    # 打印审计信息：请求的模型和接口实际使用的模型
    print(f"\n=== 审计信息 ===")
    print(f"请求的模型: {TARGET_MODEL}")
    print(f"接口响应的模型: {result.get('model', 'N/A')}")

    # 检查模型一致性
    requested_model = TARGET_MODEL
    actual_model = result.get('model', '')

    if requested_model.lower() != actual_model.lower():
        print(f"⚠️  警告：模型版本不一致！")
        print(f"   请求的模型: {requested_model}")
        print(f"   实际使用的模型: {actual_model}")
        print(f"   这可能影响结果的一致性和可复现性！")
    else:
        print(f"✅ 模型版本一致: {requested_model}")

    return result


def poll_async_result(task_id: str, api_key: str, interval: int = 3, timeout: int = 120) -> Dict[str, Any]:
    """轮询异步任务结果"""
    url = f"{API_BASE_URL}/paas/v4/async-result/{task_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    waited = 0
    while waited < timeout:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()

        task_status = result.get("task_status")

        if task_status == "SUCCESS":
            # 打印最终结果的模型信息
            print(f"\n=== 最终结果模型信息 ===")
            print(f"响应模型: {result.get('model', 'N/A')}")
            return result

        elif task_status == "FAIL":
            raise RuntimeError(f"异步任务失败: {result}")

        else:  # PROCESSING
            print(f"任务处理中... 状态: {task_status}, 已等待: {waited}/{timeout}秒")
            time.sleep(interval)
            waited += interval

    raise TimeoutError(f"轮询超时，总等待时间: {timeout}秒")


def analyze_sentiment(sentence: str, api_key: str) -> Dict[str, Any]:
    """分析单个句子的情感"""
    print(f"\n正在分析: {sentence}")

    # 1. 提交异步任务
    task_response = submit_async_task(sentence, api_key)
    task_id = task_response["id"]
    print(f"任务ID: {task_id}")

    # 2. 轮询结果
    result = poll_async_result(task_id, api_key)

    # 3. 提取情感分析结果
    if result.get("choices") and len(result["choices"]) > 0:
        content = result["choices"][0]["message"]["content"]
        try:
            # 解析JSON结果
            sentiment_result = json.loads(content)
            return {
                "sentence": sentence,
                "sentiment": sentiment_result.get("sentiment"),
                "confidence": sentiment_result.get("confidence"),
                "analysis": sentiment_result.get("analysis"),
                "usage": result.get("usage", {}),
                "model_used": result.get("model", "N/A")
            }
        except json.JSONDecodeError as e:
            return {
                "sentence": sentence,
                "error": f"JSON解析失败: {e}",
                "raw_content": content,
                "model_used": result.get("model", "N/A")
            }
    else:
        return {
            "sentence": sentence,
            "error": "未获取到有效结果",
            "model_used": result.get("model", "N/A")
        }


def main():
    """主函数：批量情感分析"""
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    print("开始批量情感分析...")
    print(f"目标模型: {TARGET_MODEL}")
    print(f"分析句子数量: {len(SENTENCES)}")

    results = []

    for i, sentence in enumerate(SENTENCES, 1):
        print(f"\n{'='*50}")
        print(f"处理第 {i}/{len(SENTENCES)} 个句子")
        print(f"{'='*50}")

        try:
            result = analyze_sentiment(sentence, API_KEY)
            results.append(result)

            # 打印当前结果摘要
            if "error" in result:
                print(f"❌ 处理失败: {result['error']}")
            else:
                print(f"✅ 处理成功:")
                print(f"   情感: {result['sentiment']}")
                print(f"   置信度: {result['confidence']}")
                print(f"   分析: {result['analysis']}")
                print(f"   使用的模型: {result['model_used']}")

        except Exception as e:
            print(f"❌ 处理异常: {e}")
            results.append({
                "sentence": sentence,
                "error": str(e),
                "model_used": "ERROR"
            })

    # 打印汇总报告
    print(f"\n{'='*60}")
    print("批量情感分析汇总报告")
    print(f"{'='*60}")
    print(f"目标模型: {TARGET_MODEL}")
    print(f"处理完成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    successful = len([r for r in results if "error" not in r])
    print(f"成功处理: {successful}/{len(SENTENCES)}")

    # 详细结果
    print(f"\n详细结果:")
    for i, result in enumerate(results, 1):
        print(f"\n{i}. 句子: {result['sentence']}")
        if "error" in result:
            print(f"   状态: 失败 - {result['error']}")
        else:
            print(f"   情感: {result['sentiment']}")
            print(f"   置信度: {result['confidence']}")
            print(f"   分析: {result['analysis']}")
            print(f"   使用的模型: {result['model_used']}")
            print(f"   Token使用: {result['usage']}")

    # 最终审计检查
    print(f"\n{'='*60}")
    print("最终审计检查")
    print(f"{'='*60}")

    all_models_used = set()
    for result in results:
        if "model_used" in result:
            all_models_used.add(result["model_used"])

    print(f"所有任务使用的模型: {all_models_used}")

    if TARGET_MODEL in all_models_used:
        print(f"✅ 至少有一个任务使用了目标模型 {TARGET_MODEL}")
    else:
        print(f"❌ 没有任务使用目标模型 {TARGET_MODEL}")

    if len(all_models_used) > 1:
        print(f"⚠️  警告：检测到使用了多个不同的模型！")
    else:
        print(f"✅ 所有任务使用了相同的模型")


if __name__ == "__main__":
    main()