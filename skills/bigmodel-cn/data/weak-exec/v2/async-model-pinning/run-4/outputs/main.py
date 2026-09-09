#!/usr/bin/env python3
"""
异步情感分析脚本
使用智谱GLM-4.6异步接口对三句话进行情感分类
"""

import os
import requests
import time
import json
from typing import List, Dict, Any


def submit_async_task(api_key: str, model: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """提交异步任务"""
    url = "https://open.bigmodel.cn/api/paas/v4/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 1000
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"提交异步任务失败: {e}")


def poll_async_result(task_id: str, api_key: str, interval: int = 2, timeout: int = 120) -> Dict[str, Any]:
    """轮询异步任务结果"""
    url = f"https://open.bigmodel.cn/api/paas/v4/async-result/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    waited = 0
    while waited < timeout:
        try:
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
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"轮询结果失败: {e}")

    raise TimeoutError(f"轮询超时，已等待 {timeout} 秒")


def analyze_sentiment(text: str) -> Dict[str, Any]:
    """情感分析提示词构建"""
    return {
        "role": "user",
        "content": f"""
请对以下文本进行情感分类，只返回JSON格式，不要输出任何其他文字：
{text}

JSON格式要求：
{
    "sentiment": "positive/negative/neutral",
    "confidence": 0.0-1.0,
    "reasoning": "简短分析理由"
}
"""
    }


def main():
    # 从环境变量读取API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 需要分析的三句话
    texts = [
        "今天天气真好，心情很愉快！",
        "这个产品太糟糕了，完全不推荐购买。",
        "我明天需要去医院检查身体。"
    ]

    # 请求的模型
    requested_model = "glm-4.6"
    print(f"我请求的模型: {requested_model}")

    # 构建消息列表
    messages = []
    for text in texts:
        messages.append(analyze_sentiment(text))

    # 提交异步任务
    print("\n提交异步任务...")
    try:
        task_response = submit_async_task(api_key, requested_model, messages)
        actual_model = task_response.get("model")
        task_id = task_response.get("id")

        print(f"接口实际使用的模型: {actual_model}")
        print(f"任务ID: {task_id}")

        # 模型版本核对
        if actual_model != requested_model:
            print("\n⚠️  警告：模型版本不一致！")
            print(f"请求的模型: {requested_model}")
            print(f"实际使用的模型: {actual_model}")
            print("根据审计要求，这可能导致结果不可复现！")
        else:
            print("\n✅ 模型版本一致")

        # 轮询结果
        print("\n等待处理完成...")
        result = poll_async_result(task_id, api_key)

        # 解析并显示结果
        print("\n=== 情感分析结果 ===")
        for i, choice in enumerate(result.get("choices", [])):
            message = choice.get("message", {})
            content = message.get("content", "")

            try:
                # 尝试解析JSON响应
                sentiment_data = json.loads(content)
                print(f"\n句子 {i+1}: '{texts[i]}'")
                print(f"情感: {sentiment_data.get('sentiment')}")
                print(f"置信度: {sentiment_data.get('confidence')}")
                print(f"分析: {sentiment_data.get('reasoning')}")
            except json.JSONDecodeError:
                print(f"\n句子 {i+1}: '{texts[i]}'")
                print(f"原始响应: {content}")

        # 显示使用统计
        usage = result.get("usage", {})
        print("\n=== 使用统计 ===")
        print(f"输入Token数: {usage.get('prompt_tokens', 0)}")
        print(f"输出Token数: {usage.get('completion_tokens', 0)}")
        print(f"总Token数: {usage.get('total_tokens', 0)}")

    except Exception as e:
        print(f"\n错误: {e}")


if __name__ == "__main__":
    main()