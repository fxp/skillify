#!/usr/bin/env python3
"""
异步情感分类脚本
使用智谱AI异步接口对三句话进行情感分类
"""

import os
import json
import time
import requests
from typing import List, Dict, Any

# API 配置
API_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

# 请求的模型版本
REQUESTED_MODEL = "glm-4.6"

# 要分析的三句话
SENTENCES = [
    "今天天气真好，心情很愉快！",
    "这份报告的数据完全不对，让我很失望。",
    "不知道该说什么，就这样吧。"
]

# 情感分析提示词
PROMPT = """你是一个情感分析专家。请对以下文本进行情感分析，并严格按照以下JSON格式返回：
{
    "sentiment": "positive/negative/neutral",
    "confidence": 0.0,
    "analysis": "简要分析"
}

请只输出JSON，不要添加任何其他文字。"""

def submit_async_task(sentence: str, api_key: str) -> Dict[str, Any]:
    """提交异步任务"""
    url = f"{API_BASE_URL}/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": sentence}
        ],
        "max_tokens": 200,
        "response_format": {"type": "json_object"}
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()

def poll_async_result(task_id: str, api_key: str, interval: int = 2, timeout: int = 60) -> Dict[str, Any]:
    """轮询异步任务结果"""
    url = f"{API_BASE_URL}/async-result/{task_id}"
    headers = {
        "Authorization": f"Bearer {api_key}"
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

        time.sleep(interval)
        waited += interval

    raise TimeoutError(f"轮询超时，等待时间: {timeout}秒")

def analyze_sentiment(sentence: str, api_key: str) -> Dict[str, Any]:
    """对单个句子进行情感分析"""
    # 提交异步任务
    print(f"提交任务: {sentence}")
    task_response = submit_async_task(sentence, api_key)
    task_id = task_response["id"]

    # 打印任务信息
    print(f"任务ID: {task_id}")
    print(f"任务状态: {task_response['task_status']}")
    print(f"请求的模型: {REQUESTED_MODEL}")
    print(f"接口实际使用的模型: {task_response['model']}")

    # 轮询结果
    print("开始轮询结果...")
    result = poll_async_result(task_id, api_key)

    # 最终结果中的模型
    actual_model = result.get("model", "未知")
    print(f"最终结果模型: {actual_model}")

    # 检查模型版本是否一致
    if REQUESTED_MODEL != actual_model:
        print("⚠️  警告: 请求的模型与实际使用的模型不一致！")
        print(f"  请求的模型: {REQUESTED_MODEL}")
        print(f"  实际模型: {actual_model}")

    # 解析响应
    try:
        content = result["choices"][0]["message"]["content"]
        sentiment_data = json.loads(content)
        sentiment_data["requested_model"] = REQUESTED_MODEL
        sentiment_data["actual_model"] = actual_model
        sentiment_data["task_id"] = task_id
        return sentiment_data
    except (KeyError, json.JSONDecodeError) as e:
        print(f"解析响应失败: {e}")
        return {
            "error": str(e),
            "requested_model": REQUESTED_MODEL,
            "actual_model": actual_model,
            "task_id": task_id
        }

def main():
    """主函数"""
    if not API_KEY:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY")
        return

    print("开始异步情感分析任务...")
    print("=" * 50)

    results = []
    for i, sentence in enumerate(SENTENCES, 1):
        print(f"\n处理第 {i} 句话:")
        print(f"文本: {sentence}")
        print("-" * 30)

        try:
            result = analyze_sentiment(sentence, API_KEY)
            results.append({
                "sentence": sentence,
                "result": result
            })

            # 打印分析结果
            if "error" in result:
                print(f"分析失败: {result['error']}")
            else:
                print(f"情感: {result.get('sentiment')}")
                print(f"置信度: {result.get('confidence')}")
                print(f"分析: {result.get('analysis')}")
                print(f"模型一致性: {'✓' if result.get('requested_model') == result.get('actual_model') else '✗'}")

        except Exception as e:
            print(f"处理出错: {e}")
            results.append({
                "sentence": sentence,
                "error": str(e)
            })

        print("=" * 50)

    # 汇总结果
    print("\n任务完成！汇总结果:")
    print("=" * 50)
    for item in results:
        if "error" in item:
            print(f"文本: {item['sentence']}")
            print(f"状态: 失败 - {item['error']}")
        else:
            result = item["result"]
            print(f"文本: {item['sentence']}")
            print(f"情感: {result.get('sentiment')}")
            print(f"置信度: {result.get('confidence')}")
            print(f"分析: {result.get('analysis')}")
            print(f"请求模型: {result.get('requested_model')}")
            print(f"实际模型: {result.get('actual_model')}")
            print(f"一致性: {'✓' if result.get('requested_model') == result.get('actual_model') else '✗'}")

        print("-" * 30)

    # 模型一致性检查
    print("\n模型版本审计:")
    print("=" * 30)
    all_consistent = True
    for item in results:
        if "error" not in item["result"]:
            requested = item["result"].get("requested_model")
            actual = item["result"].get("actual_model")
            if requested != actual:
                all_consistent = False
                print(f"⚠️  文本 '{item['sentence']}' 模型不一致: 请求 {requested}, 实际 {actual}")

    if all_consistent:
        print("✓ 所有请求的模型与实际使用的模型一致")

    print(f"\我请求的模型: {REQUESTED_MODEL}")

if __name__ == "__main__":
    main()