#!/usr/bin/env python3
import os
import json
import time
import requests
import sys

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"

# 请求的模型
REQUESTED_MODEL = "glm-4.6"

# 三句话进行情感分类
sentences = [
    "今天天气真好，心情很愉快！",
    "考试没通过，感觉很难过。",
    "不知道该说什么，就这样吧。"
]

def submit_async_task(sentence: str, api_key: str):
    """提交异步任务"""
    url = f"{BASE_URL}/paas/v4/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {
                "role": "system",
                "content": """你是情感分析专家。请严格按照以下 JSON 格式返回分析结果，不要输出多余文字：
{"sentiment": "positive/negative/neutral", "confidence": 0.0-1.0, "emotions": ["emotion1", "emotion2"], "keywords": ["keyword1", "keyword2"], "analysis": "简要分析"}"""
            },
            {
                "role": "user",
                "content": f"请对以下句子进行情感分类：{sentence}"
            }
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
        "max_tokens": 200
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"提交任务失败: {e}")
        return None

def poll_async_result(task_id: str, api_key: str, timeout=300, interval=2):
    """轮询异步结果"""
    url = f"{BASE_URL}/paas/v4/async-result/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    waited = 0
    while waited < timeout:
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            result = resp.json()

            status = result.get("task_status")
            if status == "SUCCESS":
                return result
            elif status == "FAIL":
                raise RuntimeError(f"异步任务失败: {result}")
            else:
                # 等待一段时间再轮询
                time.sleep(interval)
                waited += interval
                print(f"任务处理中，已等待 {waited} 秒...")

        except requests.exceptions.RequestException as e:
            print(f"轮询失败: {e}")
            time.sleep(interval)
            waited += interval

    raise TimeoutError(f"轮询超时，总等待时间 {timeout} 秒")

def analyze_sentences():
    """分析所有句子的情感"""
    if not API_KEY:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY")
        sys.exit(1)

    print(f"请求的模型: {REQUESTED_MODEL}")
    print("=" * 50)

    results = []

    for i, sentence in enumerate(sentences, 1):
        print(f"\n处理句子 {i}/{len(sentences)}: {sentence}")
        print("-" * 50)

        # 提交异步任务
        print("提交异步任务...")
        task_response = submit_async_task(sentence, API_KEY)

        if not task_response:
            print(f"句子 {i} 提交失败")
            results.append({
                "sentence": sentence,
                "error": "提交任务失败"
            })
            continue

        task_id = task_response.get("id")
        actual_model = task_response.get("model")

        # 打印任务信息
        print(f"任务ID: {task_id}")
        print(f"接口返回的模型: {actual_model}")

        # 检查模型一致性
        if actual_model != REQUESTED_MODEL:
            print("⚠️  警告: 接口返回的模型与请求的模型不一致!")
            print(f"   请求的模型: {REQUESTED_MODEL}")
            print(f"   实际使用的模型: {actual_model}")
            print("   ⚠️  审计警告: 模型版本被修改!")
        else:
            print("✓ 模型版本一致")

        print("\n开始轮询结果...")

        try:
            # 轮询结果
            result = poll_async_result(task_id, API_KEY)

            # 获取最终响应的模型
            final_model = result.get("model")
            if final_model != REQUESTED_MODEL:
                print("⚠️  警告: 最终响应的模型与请求的模型不一致!")
                print(f"   请求的模型: {REQUESTED_MODEL}")
                print(f"   最终使用的模型: {final_model}")
                print("   ⚠️  审计警告: 模型版本被修改!")
            else:
                print("✓ 最终响应模型版本一致")

            # 解析结果
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                try:
                    sentiment_data = json.loads(content)
                    results.append({
                        "sentence": sentence,
                        "analysis": sentiment_data
                    })
                    print(f"情感分析结果: {sentiment_data}")
                except json.JSONDecodeError:
                    results.append({
                        "sentence": sentence,
                        "analysis": {"error": "JSON解析失败", "raw_content": content}
                    })
                    print(f"分析结果 (原始): {content}")
            else:
                results.append({
                    "sentence": sentence,
                    "error": "没有返回结果"
                })
                print("错误: 没有返回分析结果")

            # 打印token使用情况
            if "usage" in result:
                usage = result["usage"]
                print(f"Token使用: 输入{usage.get('prompt_tokens', 0)}, 输出{usage.get('completion_tokens', 0)}, 总计{usage.get('total_tokens', 0)}")

        except Exception as e:
            print(f"获取结果失败: {e}")
            results.append({
                "sentence": sentence,
                "error": str(e)
            })

    # 打印汇总结果
    print("\n" + "=" * 50)
    print("情感分析汇总结果")
    print("=" * 50)

    for result in results:
        if "error" in result:
            print(f"句子: {result['sentence']}")
            print(f"错误: {result['error']}")
        else:
            analysis = result['analysis']
            print(f"句子: {result['sentence']}")
            print(f"情感: {analysis.get('sentiment', 'unknown')}")
            print(f"置信度: {analysis.get('confidence', 0)}")
            print(f"情绪: {', '.join(analysis.get('emotions', []))}")
            print(f"关键词: {', '.join(analysis.get('keywords', []))}")
            print(f"分析: {analysis.get('analysis', '')}")
        print("-" * 30)

if __name__ == "__main__":
    analyze_sentences()