#!/usr/bin/env python3
"""
使用智谱AI异步对话接口进行情感分类
锁定模型版本：glm-4.6
审计要求：核对请求的模型和实际使用的模型
"""

import os
import json
import time
import requests

# API 配置
API_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

# 请求的模型版本（审计要求锁定）
REQUESTED_MODEL = "glm-4.6"

# 三句话情感分类任务
sentences = [
    "今天天气真好，心情很愉快！",
    "这部电影真的太无聊了，浪费时间和金钱。",
    "明天要考试了，有点紧张但又充满期待。"
]

# 请求头
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def submit_async_task(sentence: str, model: str) -> dict:
    """提交异步任务"""
    url = f"{API_BASE_URL}/async/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是情感分析专家。请严格按照以下JSON结构返回分析结果，不要输出多余文字：\n"
                         '{"sentiment": "positive/negative/neutral", "confidence": 0.0-1.0, '
                         '"emotions": ["joy", "sadness", "fear", "anger", "surprise", "neutral"], '
                         '"keywords": ["关键词1", "关键词2"]}'
            },
            {
                "role": "user",
                "content": f"请对以下文本进行情感分析：{sentence}"
            }
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 200
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        task_info = response.json()

        print(f"提交任务成功 - 句子: {sentence}")
        print(f"请求的模型: {model}")
        print(f"任务ID: {task_info.get('id')}")
        print(f"任务状态: {task_info.get('task_status')}")

        # 审计要求：记录响应中的模型版本
        response_model = task_info.get('model')
        print(f"响应中的模型: {response_model}")

        # 检查模型版本是否一致
        if model.lower() != response_model.lower():
            print(f"⚠️ 警告：请求的模型({model})与响应中的模型({response_model})不一致！")

        print("-" * 50)

        return task_info

    except requests.exceptions.RequestException as e:
        print(f"提交任务失败: {e}")
        raise

def poll_async_result(task_id: str) -> dict:
    """轮询异步任务结果"""
    url = f"{API_BASE_URL}/async-result/{task_id}"

    max_attempts = 60  # 最多轮询60次（约2分钟）
    interval = 2  # 每2秒轮询一次

    for attempt in range(max_attempts):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()

            status = result.get("task_status")
            print(f"轮询结果 - 尝试 {attempt + 1}/{max_attempts}: {status}")

            if status == "SUCCESS":
                # 审计要求：检查最终结果中的模型版本
                final_model = result.get('model')
                print(f"最终结果中的模型: {final_model}")

                if REQUESTED_MODEL.lower() != final_model.lower():
                    print(f"⚠️ 警告：请求的模型({REQUESTED_MODEL})与最终结果中的模型({final_model})不一致！")

                return result

            elif status == "FAIL":
                error_msg = result.get("error", {}).get("message", "未知错误")
                raise RuntimeError(f"异步任务失败: {error_msg}")

            # 继续轮询
            time.sleep(interval)

        except requests.exceptions.RequestException as e:
            print(f"轮询请求失败: {e}")
            time.sleep(interval)

    raise TimeoutError(f"轮询超时，任务ID: {task_id}")

def parse_sentiment_result(result: dict, sentence: str) -> dict:
    """解析情感分析结果"""
    try:
        choices = result.get("choices", [])
        if not choices:
            raise ValueError("响应中没有choices")

        message = choices[0].get("message", {})
        content = message.get("content", "")

        # 尝试解析JSON
        if content.startswith("{") and content.endswith("}"):
            result_data = json.loads(content)
        else:
            # 如果不是纯JSON，尝试提取JSON部分
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result_data = json.loads(json_match.group())
            else:
                raise ValueError("响应内容不是有效的JSON格式")

        # 标准化结果
        standardized = {
            "sentence": sentence,
            "sentiment": result_data.get("sentiment", "neutral").lower(),
            "confidence": float(result_data.get("confidence", 0.0)),
            "emotions": result_data.get("emotions", []),
            "keywords": result_data.get("keywords", []),
            "raw_response": content
        }

        return standardized

    except Exception as e:
        print(f"解析结果失败: {e}")
        print(f"原始内容: {content}")
        # 返回错误信息但不中断程序
        return {
            "sentence": sentence,
            "error": str(e),
            "raw_response": content
        }

def main():
    """主函数"""
    print("=" * 60)
    print("智谱AI异步情感分类任务")
    print("=" * 60)

    # 检查API Key
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        print("export ZHIPUAI_API_KEY='your_api_key_here'")
        return 1

    print(f"请求的模型版本: {REQUESTED_MODEL}")
    print(f"API Key: {API_KEY[:10]}...{API_KEY[-10:]}" if len(API_KEY) > 20 else API_KEY)
    print("-" * 60)

    all_results = []

    # 处理每个句子
    for i, sentence in enumerate(sentences, 1):
        print(f"\n处理第 {i} 句话:")
        print(f"句子: {sentence}")

        try:
            # 1. 提交异步任务
            task_info = submit_async_task(sentence, REQUESTED_MODEL)
            task_id = task_info["id"]

            # 2. 轮询结果
            print("开始轮询结果...")
            result = poll_async_result(task_id)

            # 3. 解析结果
            parsed = parse_sentiment_result(result, sentence)
            all_results.append(parsed)

            print(f"情感分类完成: {parsed.get('sentiment', 'unknown')}")

        except Exception as e:
            print(f"处理句子失败: {e}")
            all_results.append({
                "sentence": sentence,
                "error": str(e)
            })

        print("-" * 50)

    # 打印最终汇总
    print("\n" + "=" * 60)
    print("任务完成 - 汇总结果")
    print("=" * 60)

    for i, result in enumerate(all_results, 1):
        print(f"\n第 {i} 句话: {result['sentence']}")
        if 'error' in result:
            print(f"  错误: {result['error']}")
        else:
            print(f"  情感: {result['sentiment']}")
            print(f"  置信度: {result['confidence']}")
            print(f"  情绪: {', '.join(result['emotions'])}")
            print(f"  关键词: {', '.join(result['keywords'])}")

    # 检查是否有模型版本不一致的情况
    print("\n审计核对:")
    print(f"请求的模型: {REQUESTED_MODEL}")

    model_mismatch_count = 0
    for i, result in enumerate(all_results, 1):
        if 'model' in result:
            if REQUESTED_MODEL.lower() != result['model'].lower():
                print(f"⚠️ 第 {i} 句话的模型不一致: 请求 {REQUESTED_MODEL} vs 实际 {result['model']}")
                model_mismatch_count += 1

    if model_mismatch_count > 0:
        print(f"\n⚠️ 警告：发现 {model_mismatch_count} 个模型版本不一致！")
        print("根据审计要求，这可能是严重问题。")
        return 1
    else:
        print("\n✅ 所有任务的模型版本一致，审计通过。")
        return 0

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)