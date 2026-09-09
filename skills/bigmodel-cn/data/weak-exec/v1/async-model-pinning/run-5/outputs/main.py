#!/usr/bin/env python3
import os
import json
import time
import requests
from typing import Dict, Any, List


def submit_async_task(api_key: str, model: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    提交异步对话任务
    """
    url = "https://open.bigmodel.cn/api/paas/v4/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
    }

    print(f"提交异步任务，请求模型: {model}")
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()

    result = resp.json()
    print(f"任务提交成功，task_id: {result['id']}, 任务状态: {result['task_status']}")
    print(f"接口实际返回的模型: {result['model']}")

    # 记录提交时接口返回的模型（审计要求）
    result['submitted_model'] = result['model']

    return result


def poll_async_result(task_id: str, api_key: str, interval: int = 2, timeout: int = 120) -> Dict[str, Any]:
    """
    轮询异步任务结果
    """
    url = f"https://open.bigmodel.cn/api/paas/v4/async-result/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    waited = 0
    while waited < timeout:
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            result = r.json()

            status = result.get("task_status")
            if status == "SUCCESS":
                print(f"任务执行成功！接口最终使用的模型: {result['model']}")
                # 记录最终模型（审计要求）
                result['final_model'] = result['model']
                return result
            elif status == "FAIL":
                raise RuntimeError(f"异步任务失败: {result}")

            print(f"任务状态: {status}，等待 {interval} 秒后重试...")
            time.sleep(interval)
            waited += interval

        except Exception as e:
            print(f"轮询时出错: {str(e)}")
            time.sleep(interval)
            waited += interval

    raise TimeoutError(f"轮询超时，等待了 {timeout} 秒")


def analyze_sentiment(text: str, task_id: int) -> Dict[str, Any]:
    """
    分析单句话的情感
    """
    system_prompt = """你是一个情感分析专家。请对用户输入的文本进行情感分析，并以JSON格式返回分析结果。
返回格式必须是严格的JSON，包含以下字段：
- sentiment: 情感分类 ("positive", "negative", "neutral")
- confidence: 置信度 (0.0-1.0)
- emotions: 情感关键词列表
- analysis: 详细分析说明
- text: 原始文本

请确保返回的是有效的JSON格式，不要包含任何其他文字。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text}
    ]

    return {
        "role": "user",
        "content": text,
        "task_id": task_id,
        "messages": messages
    }


def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 配置参数
    requested_model = "glm-4.6"  # 我请求的模型
    texts = [
        "今天天气真好，心情很愉快！",
        "这个产品太差了，完全不值这个价钱。",
        "我觉得这件事还可以，没有特别的感觉。"
    ]

    print("=" * 50)
    print("开始异步情感分析任务")
    print("=" * 50)

    # 对每句话提交异步任务
    results = []
    for i, text in enumerate(texts):
        print(f"\n处理第 {i+1} 句话: {text}")

        try:
            # 提交异步任务
            task_info = submit_async_task(
                api_key=api_key,
                model=requested_model,
                messages=[analyze_sentiment(text, i+1)["messages"]]
            )

            # 轮询结果
            result = poll_async_result(task_info["id"], api_key)

            # 提取情感分析结果
            content = result["choices"][0]["message"]["content"]
            try:
                sentiment_data = json.loads(content)
                sentiment_data["original_text"] = text

                # 添加审计信息到每个结果中
                sentiment_data["submitted_model"] = result.get("submitted_model", "unknown")
                sentiment_data["final_model"] = result.get("final_model", "unknown")
                sentiment_data["task_id"] = task_info["id"]

                results.append(sentiment_data)
            except json.JSONDecodeError:
                print(f"警告：返回的不是有效JSON，原始内容: {content}")
                results.append({
                    "sentiment": "unknown",
                    "confidence": 0.0,
                    "emotions": [],
                    "analysis": "JSON解析失败",
                    "text": text,
                    "raw_response": content,
                    "submitted_model": result.get("submitted_model", "unknown"),
                    "final_model": result.get("final_model", "unknown"),
                    "task_id": task_info["id"]
                })

        except Exception as e:
            print(f"处理第 {i+1} 句话时出错: {str(e)}")
            results.append({
                "sentiment": "error",
                "confidence": 0.0,
                "emotions": [],
                "analysis": f"任务失败: {str(e)}",
                "text": text
            })

    # 打印最终结果
    print("\n" + "=" * 50)
    print("情感分析结果汇总")
    print("=" * 50)

    for i, result in enumerate(results):
        print(f"\n第 {i+1} 句话: {result['original_text']}")
        print(f"情感: {result['sentiment']}")
        print(f"置信度: {result['confidence']}")
        print(f"情感关键词: {', '.join(result['emotions'])}")
        print(f"分析: {result['analysis']}")

    # 审计信息
    print("\n" + "=" * 50)
    print("审计信息")
    print("=" * 50)
    print(f"我请求的模型: {requested_model}")

    # 显示第一个任务的模型信息（所有任务应该使用相同的模型）
    if results:
        first_result = results[0]
        submitted_model = first_result.get('submitted_model', 'unknown')
        final_model = first_result.get('final_model', 'unknown')

        print(f"接口提交时返回的模型: {submitted_model}")
        print(f"接口最终使用的模型: {final_model}")

        # 模型版本一致性检查
        print("\n模型版本一致性检查:")
        models_match = True

        # 检查提交时的模型
        if submitted_model.lower() != requested_model.lower():
            print("⚠️  提交时的模型与请求的模型不一致！")
            print(f"   请求的模型: {requested_model}")
            print(f"   实际提交模型: {submitted_model}")
            models_match = False
        else:
            print("✓ 提交时的模型与请求的模型一致")

        # 检查最终使用的模型
        if final_model.lower() != requested_model.lower():
            print("⚠️  最终使用的模型与请求的模型不一致！")
            print(f"   请求的模型: {requested_model}")
            print(f"   最终使用模型: {final_model}")
            models_match = False
        else:
            print("✓ 最终使用的模型与请求的模型一致")

        if models_match:
            print("\n✓ 所有模型版本一致，符合审计要求。")
        else:
            print("\n⚠️  警告：模型版本不一致！这可能影响审计追踪，请检查模型版本锁定要求。")

        # 显示所有任务的task_id和模型信息
        print("\n各任务详情:")
        for i, result in enumerate(results):
            print(f"  任务 {i+1}: task_id={result.get('task_id', 'unknown')}, "
                  f"提交模型={result.get('submitted_model', 'unknown')}, "
                  f"最终模型={result.get('final_model', 'unknown')}")
    else:
        print("⚠️  警告：没有任务结果，无法进行模型版本验证。")


if __name__ == "__main__":
    main()