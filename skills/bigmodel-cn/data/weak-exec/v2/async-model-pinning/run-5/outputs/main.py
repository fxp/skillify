#!/usr/bin/env python3
"""
使用智谱异步对话接口进行情感分类任务
"""

import os
import requests
import time
import json


def submit_async_chat_task(api_key, model, messages):
    """
    提交异步聊天任务

    Args:
        api_key: API密钥
        model: 请求的模型版本
        messages: 消息列表

    Returns:
        dict: 包含 task_id 和 task_status 的响应
    """
    url = "https://open.bigmodel.cn/api/paas/v4/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 100,  # 情感分类不需要太长输出
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()

        # 审计：打印请求的模型和实际使用的模型
        actual_model = result.get("model")
        print(f"我请求的模型: {model}")
        print(f"接口实际使用的模型: {actual_model}")

        # 审计检查：模型版本是否一致
        if model.lower() != actual_model.lower():
            print("⚠️ 警告：请求的模型与实际使用的模型不一致！这会影响审计对账！")
            print(f"差异：请求了 '{model}'，但实际使用了 '{actual_model}'")

        return result

    except requests.exceptions.RequestException as e:
        print(f"提交任务失败: {e}")
        raise


def poll_async_result(task_id, api_key, interval=2, timeout=120):
    """
    轮询异步任务结果

    Args:
        task_id: 任务ID
        api_key: API密钥
        interval: 轮询间隔（秒）
        timeout: 超时时间（秒）

    Returns:
        dict: 最终结果
    """
    url = f"https://open.bigmodel.cn/api/paas/v4/async-result/{task_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    waited = 0
    while waited < timeout:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()

            task_status = result.get("task_status")
            print(f"任务状态: {task_status}")

            if task_status == "SUCCESS":
                # 审计：再次检查最终结果中的模型
                final_model = result.get("model")
                print(f"最终结果中的模型: {final_model}")

                # 检查最终结果的模型是否与初始请求一致
                if "model" in locals():
                    if model.lower() != final_model.lower():
                        print("⚠️ 警告：最终结果中的模型与初始请求不一致！")

                return result
            elif task_status == "FAIL":
                raise RuntimeError(f"任务失败: {result}")
            else:
                print(f"等待 {interval} 秒后再次尝试...")
                time.sleep(interval)
                waited += interval

        except requests.exceptions.RequestException as e:
            print(f"轮询请求失败: {e}")
            time.sleep(interval)
            waited += interval

    raise TimeoutError(f"轮询超时，等待了 {timeout} 秒")


def analyze_sentiment(text):
    """
    生成情感分类的提示

    Args:
        text: 要分析的文本

    Returns:
        dict: 包含系统提示和用户消息的消息字典
    """
    return {
        "role": "user",
        "content": f"请对以下文本进行情感分类，只回答'积极'、'消极'或'中性'，不要有其他解释：\n\n{text}"
    }


def main():
    """主函数"""
    # 从环境变量读取 API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 审计：锁定的模型版本
    requested_model = "glm-4.6"
    print(f"=== 审计信息 ===")
    print(f"锁定的模型版本: {requested_model}")
    print("=" * 20)

    # 三句话情感分类任务
    sentences = [
        "今天天气真好，心情特别愉快！",
        "工作压力太大，感觉快要崩溃了。",
        "这部电影还行，一般般吧。"
    ]

    print("\n=== 开始处理三句话情感分类 ===")
    results = []

    for i, sentence in enumerate(sentences, 1):
        print(f"\n--- 处理第 {i} 句 ---")
        print(f"句子: {sentence}")

        # 准备消息
        messages = [analyze_sentiment(sentence)]

        try:
            # 提交异步任务
            task_response = submit_async_chat_task(api_key, requested_model, messages)
            task_id = task_response["id"]
            print(f"任务ID: {task_id}")

            # 轮询结果
            result = poll_async_result(task_id, api_key)

            # 提取情感分类结果
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"].strip()
                print(f"情感分类结果: {content}")
                results.append({
                    "sentence": sentence,
                    "sentiment": content,
                    "model_used": result.get("model"),
                    "usage": result.get("usage", {})
                })
            else:
                print("未获取到有效的分类结果")
                results.append({
                    "sentence": sentence,
                    "sentiment": "分类失败",
                    "model_used": result.get("model"),
                    "usage": {}
                })

        except Exception as e:
            print(f"处理句子时出错: {e}")
            results.append({
                "sentence": sentence,
                "sentiment": f"错误: {str(e)}",
                "model_used": None,
                "usage": {}
            })

    # 打印汇总结果
    print("\n=== 汇总结果 ===")
    for result in results:
        print(f"句子: {result['sentence']}")
        print(f"情感: {result['sentiment']}")
        print(f"使用的模型: {result['model_used']}")
        if result['usage']:
            print(f"Token使用: 输入={result['usage'].get('prompt_tokens', 0)}, "
                  f"输出={result['usage'].get('completion_tokens', 0)}, "
                  f"总计={result['usage'].get('total_tokens', 0)}")
        print("-" * 50)

    # 最终审计信息
    print("\n=== 最终审计核对 ===")
    requested_model = "glm-4.6"
    models_used = [r['model_used'] for r in results if r['model_used']]

    if all(model.lower() == requested_model.lower() for model in models_used):
        print("✅ 审计通过：所有任务都使用了请求的模型版本")
    else:
        print("❌ 审计失败：部分任务未使用请求的模型版本")
        print(f"请求的模型: {requested_model}")
        print(f"实际使用的模型: {models_used}")


if __name__ == "__main__":
    main()