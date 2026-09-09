#!/usr/bin/env python3
"""
批量情感分析脚本
使用智谱AI异步对话接口对三句话进行情感分类
审计要求：检查模型版本一致性
"""

import os
import requests
import json
import time
from typing import List, Dict, Any

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"
REQUESTED_MODEL = "glm-4.6"

# 要进行情感分析的三句话
sentences = [
    "今天天气真好，心情很愉快！",
    "这个产品太差了，完全不值这个价钱。",
    "我觉得这部电影还不错，但情节有些拖沓。"
]

def submit_async_task(sentence: str, model: str) -> Dict[str, Any]:
    """提交异步任务"""
    url = f"{BASE_URL}/paas/v4/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是情感分析专家。请对以下文本进行情感分析，以JSON格式返回结果，包含sentiment（positive/negative/neutral）和confidence（0-1之间的数值）。"
            },
            {
                "role": "user",
                "content": f"请分析这句话的情感：{sentence}"
            }
        ],
        "response_format": {"type": "json_object"}
    }

    print(f"提交任务，请求模型: {model}")
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()

def poll_async_result(task_id: str, timeout: int = 120) -> Dict[str, Any]:
    """轮询异步任务结果"""
    url = f"{BASE_URL}/paas/v4/async-result/{task_id}"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    waited = 0
    poll_interval = 2

    while waited < timeout:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()

        status = result.get("task_status")
        print(f"任务状态: {status}")

        if status == "SUCCESS":
            return result
        elif status == "FAIL":
            raise RuntimeError(f"任务失败: {result}")

        time.sleep(poll_interval)
        waited += poll_interval

    raise TimeoutError(f"轮询超时，等待时间: {timeout}秒")

def analyze_sentences(sentences: List[str], model: str) -> List[Dict[str, Any]]:
    """批量分析句子的情感"""
    results = []

    for i, sentence in enumerate(sentences):
        print(f"\n=== 处理第 {i+1} 句话 ===")
        print(f"句子: {sentence}")

        # 提交异步任务
        task_response = submit_async_task(sentence, model)
        task_id = task_response["id"]
        print(f"任务ID: {task_id}")

        # 检查响应中的模型版本
        actual_model = task_response.get("model")
        print(f"提交接口回显模型: {actual_model}")

        # 轮询结果
        result = poll_async_result(task_id)
        actual_model_final = result.get("model")
        print(f"最终结果模型: {actual_model_final}")

        # 审计检查：模型版本一致性
        if actual_model != REQUESTED_MODEL or actual_model_final != REQUESTED_MODEL:
            print(f"🚨 审计警告：模型版本不一致！")
            print(f"   请求的模型: {REQUESTED_MODEL}")
            print(f"   提交接口回显: {actual_model}")
            print(f"   最终结果使用: {actual_model_final}")
        else:
            print(f"✅ 审计通过：模型版本一致 ({REQUESTED_MODEL})")

        # 提取分析结果
        if result.get("choices"):
            content = result["choices"][0]["message"]["content"]
            try:
                analysis = json.loads(content)
                analysis["original_sentence"] = sentence
                results.append(analysis)
                print(f"情感: {analysis.get('sentiment', 'unknown')}, 置信度: {analysis.get('confidence', 'unknown')}")
            except json.JSONDecodeError:
                print(f"⚠️ 解析JSON失败，原始响应: {content}")
                results.append({
                    "original_sentence": sentence,
                    "error": "Failed to parse JSON response",
                    "raw_response": content
                })
        else:
            print("⚠️ 未得到有效结果")
            results.append({
                "original_sentence": sentence,
                "error": "No valid choices in response"
            })

    return results

def main():
    """主函数"""
    print("开始批量情感分析任务")
    print(f"请求的模型版本: {REQUESTED_MODEL}")
    print(f"API Key: {'已设置' if API_KEY else '未设置'}")

    if not API_KEY:
        print("❌ 错误：未设置 ZHIPUAI_API_KEY 环境变量")
        return

    try:
        # 批量分析
        results = analyze_sentences(sentences, REQUESTED_MODEL)

        # 输出最终结果
        print("\n" + "="*50)
        print("批量情感分析结果汇总")
        print("="*50)

        for i, result in enumerate(results, 1):
            print(f"\n句子 {i}: {result['original_sentence']}")
            if 'error' in result:
                print(f"  错误: {result['error']}")
            else:
                print(f"  情感: {result.get('sentiment', 'unknown')}")
                print(f"  置信度: {result.get('confidence', 'unknown')}")

        print("\n任务完成！")

    except Exception as e:
        print(f"❌ 执行过程中发生错误: {str(e)}")

if __name__ == "__main__":
    main()