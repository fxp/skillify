#!/usr/bin/env python3
"""
异步情感分类脚本
使用智谱AI异步接口对三句话进行情感分类
必须锁定模型版本 glm-4.6，并审计实际使用的模型
"""

import os
import json
import time
import requests
from typing import List, Dict, Any

# 配置
API_KEY = os.getenv("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

# 要进行情感分类的三句话
SENTENCES = [
    "今天天气真好，心情很愉快！",
    "这个产品质量太差了，完全不值这个价格。",
    "我收到了快递，包装完好。"
]

# 请求的模型
REQUESTED_MODEL = "glm-4.6"

def submit_async_chat_task(text: str, model: str) -> Dict[str, Any]:
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
                "content": "你是情感分析专家。请对输入的文本进行情感分类，返回JSON格式：{\"sentiment\": \"positive/negative/neutral\", \"confidence\": 0.0, \"keywords\": [], \"analysis\": \"\"}"
            },
            {
                "role": "user",
                "content": f"请对以下文本进行情感分类：{text}"
            }
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 300
    }

    response = requests.post(url, headers=headers, json=payload)
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
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        result = response.json()

        status = result.get("task_status")
        if status == "SUCCESS":
            return result
        elif status == "FAIL":
            raise RuntimeError(f"异步任务失败: {result}")

        time.sleep(interval)
        waited += interval

    raise TimeoutError(f"轮询超时，等待时间超过 {timeout} 秒")

def analyze_sentiment(text: str) -> Dict[str, Any]:
    """分析情感分类"""
    print(f"\n分析文本: {text}")

    # 提交异步任务
    print(f"提交任务，请求模型: {REQUESTED_MODEL}")
    task_response = submit_async_chat_task(text, REQUESTED_MODEL)
    task_id = task_response["id"]
    print(f"任务ID: {task_id}, 任务状态: {task_response['task_status']}")

    # 轮询结果
    print("开始轮询结果...")
    result = poll_async_result(task_id)

    # 审计信息
    requested_model = REQUESTED_MODEL
    actual_model = result.get("model", "未知")

    print("\n=== 审计信息 ===")
    print(f"我请求的模型: {requested_model}")
    print(f"接口实际使用的模型: {actual_model}")

    # 模型版本检查
    if requested_model != actual_model:
        print("\n⚠️  警告：模型版本不一致！")
        print("审计要求：必须锁定模型版本使用 glm-4.6")
        print("实际使用的模型与请求的模型不同，这可能影响结果的一致性和可复现性")
    else:
        print("\n✅ 模型版本一致")

    print("================\n")

    # 解析结果
    if "choices" in result and len(result["choices"]) > 0:
        content = result["choices"][0]["message"]["content"]
        try:
            # 清理可能的代码块标记
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            sentiment_data = json.loads(content)
            return {
                "text": text,
                "requested_model": requested_model,
                "actual_model": actual_model,
                "sentiment": sentiment_data.get("sentiment", "unknown"),
                "confidence": sentiment_data.get("confidence", 0.0),
                "keywords": sentiment_data.get("keywords", []),
                "analysis": sentiment_data.get("analysis", ""),
                "task_id": task_id
            }
        except json.JSONDecodeError:
            print(f"解析JSON失败，原始内容: {content}")
            return {
                "text": text,
                "requested_model": requested_model,
                "actual_model": actual_model,
                "sentiment": "error",
                "confidence": 0.0,
                "keywords": [],
                "analysis": f"JSON解析失败: {content}",
                "task_id": task_id
            }
    else:
        print(f"未获取到有效结果: {result}")
        return {
            "text": text,
            "requested_model": requested_model,
            "actual_model": actual_model,
            "sentiment": "error",
            "confidence": 0.0,
            "keywords": [],
            "analysis": "未获取到有效结果",
            "task_id": task_id
        }

def main():
    """主函数"""
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        exit(1)

    print("开始批量情感分类任务")
    print("=" * 50)

    results = []
    for i, sentence in enumerate(SENTENCES, 1):
        print(f"\n第 {i} 个任务:")
        result = analyze_sentiment(sentence)
        results.append(result)

    # 打印汇总结果
    print("\n" + "=" * 50)
    print("批量情感分类结果汇总")
    print("=" * 50)

    for i, result in enumerate(results, 1):
        print(f"\n{i}. 文本: {result['text']}")
        print(f"   情感: {result['sentiment']}")
        print(f"   置信度: {result['confidence']}")
        print(f"   关键词: {', '.join(result['keywords'])}")
        print(f"   分析: {result['analysis']}")
        print(f"   任务ID: {result['task_id']}")
        print(f"   请求模型: {result['requested_model']}")
        print(f"   实际模型: {result['actual_model']}")

        if result['requested_model'] != result['actual_model']:
            print(f"   状态: ⚠️ 模型版本不一致")
        else:
            print(f"   状态: ✅ 模型版本一致")

    # 统计模型版本情况
    all_consistent = all(r['requested_model'] == r['actual_model'] for r in results)
    if all_consistent:
        print("\n🎉 所有任务模型版本一致，审计通过")
    else:
        print("\n❌ 部分任务模型版本不一致，审计失败")

    # 保存结果到文件
    output_file = "sentiment_analysis_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: {output_file}")

if __name__ == "__main__":
    main()