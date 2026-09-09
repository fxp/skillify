#!/usr/bin/env python3
"""
智谱异步情感分类脚本
使用 async/chat/completions 接口对三句话做情感分类
锁定模型版本为 glm-4.6，并验证模型一致性
"""

import os
import json
import requests
import time
from typing import List, Dict, Any


# API 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

# 请求的模型
REQUESTED_MODEL = "glm-4.6"

# 三句话情感分类任务
TEXTS = [
    "今天天气真好，心情很愉快！",
    "这部电影太无聊了，浪费了两小时。",
    "今天的饭菜还行，就是有点咸。"
]

def submit_async_chat(text: str, model: str) -> Dict[str, Any]:
    """提交异步聊天请求"""
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
                "content": "你是一个情感分析专家。请对以下文本进行情感分类，只输出 JSON 格式，包含 sentiment（positive/negative/neutral）和 confidence（0-1的数字）两个字段。"
            },
            {
                "role": "user",
                "content": f"请分析这句话的情感：{text}"
            }
        ],
        "response_format": {"type": "json_object"}
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()

def poll_async_result(task_id: str, api_key: str, interval: int = 2, timeout: int = 120) -> Dict[str, Any]:
    """轮询异步任务结果"""
    url = f"{BASE_URL}/async-result/{task_id}"
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

def main():
    """主函数"""
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    print(f"我请求的模型: {REQUESTED_MODEL}")
    print("=" * 50)

    results = []

    for i, text in enumerate(TEXTS, 1):
        print(f"\n[{i}/{len(TEXTS)}] 处理文本: {text}")

        try:
            # 提交异步任务
            print("正在提交异步任务...")
            task_response = submit_async_chat(text, REQUESTED_MODEL)
            task_id = task_response["id"]
            actual_model = task_response.get("model", "未知")

            print(f"任务ID: {task_id}")
            print(f"返回模型: {actual_model}")

            # 轮询结果
            print("正在等待任务完成...")
            result = poll_async_result(task_id, API_KEY)

            # 检查模型一致性
            final_model = result.get("model", "未知")
            print(f"最终模型: {final_model}")

            # 审计检查
            if final_model != REQUESTED_MODEL:
                print("\n🚨 审计警告：模型版本不一致！")
                print(f"  请求的模型: {REQUESTED_MODEL}")
                print(f"  实际使用的模型: {final_model}")
                print("  这可能影响结果的可靠性和一致性！")
            else:
                print("\n✅ 模型版本一致")

            # 提取情感分析结果
            if result.get("choices"):
                content = result["choices"][0]["message"]["content"]
                try:
                    sentiment_data = json.loads(content)
                    sentiment = sentiment_data.get("sentiment", "未知")
                    confidence = sentiment_data.get("confidence", 0)
                    print(f"情感分类: {sentiment} (置信度: {confidence})")
                    results.append({
                        "text": text,
                        "sentiment": sentiment,
                        "confidence": confidence,
                        "requested_model": REQUESTED_MODEL,
                        "actual_model": final_model
                    })
                except json.JSONDecodeError:
                    print(f"解析 JSON 失败: {content}")
                    results.append({
                        "text": text,
                        "error": "JSON解析失败",
                        "requested_model": REQUESTED_MODEL,
                        "actual_model": final_model
                    })
            else:
                print("未获取到结果")
                results.append({
                    "text": text,
                    "error": "未获取到结果",
                    "requested_model": REQUESTED_MODEL,
                    "actual_model": final_model
                })

        except Exception as e:
            print(f"处理失败: {str(e)}")
            results.append({
                "text": text,
                "error": str(e),
                "requested_model": REQUESTED_MODEL,
                "actual_model": "未知"
            })

    # 打印汇总结果
    print("\n" + "=" * 50)
    print("汇总结果:")
    print("=" * 50)

    model_mismatch = False
    for result in results:
        print(f"\n文本: {result['text']}")
        if 'error' in result:
            print(f"状态: ❌ {result['error']}")
        else:
            print(f"情感: {result['sentiment']}")
            print(f"置信度: {result['confidence']}")

        # 检查模型是否一致
        if result.get('requested_model') != result.get('actual_model'):
            model_mismatch = True
            print(f"模型: 🚨 {result['actual_model']} (请求的是 {result['requested_model']})")
        else:
            print(f"模型: ✅ {result['actual_model']}")

    # 最终审计报告
    print("\n" + "=" * 50)
    print("最终审计报告:")
    print("=" * 50)

    if model_mismatch:
        print("🚨 审计警告：检测到模型版本不一致！")
        print("  部分任务实际使用的模型与请求的模型不符")
        print("  这可能影响审计追踪和结果的可重复性")
        return 1
    else:
        print("✅ 审计通过：所有任务都使用了请求的模型版本")
        return 0

if __name__ == "__main__":
    exit_code = main()
    print(f"\n脚本执行完成，退出码: {exit_code}")