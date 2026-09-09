#!/usr/bin/env python3
"""
智谱AI异步对话接口情感分类脚本
使用glm-4.6模型对三句话进行情感分类
"""

import os
import json
import time
import requests
from typing import List, Dict, Any


def submit_async_chat(
    messages: List[Dict[str, str]],
    model: str = "glm-4.6",
    api_key: str = None,
    temperature: float = 0.3,
    max_tokens: int = 500
) -> Dict[str, Any]:
    """
    提交异步聊天任务

    Args:
        messages: 消息列表
        model: 请求的模型版本
        api_key: API密钥
        temperature: 温度参数
        max_tokens: 最大输出token数

    Returns:
        任务提交响应
    """
    url = "https://open.bigmodel.cn/api/paas/v4/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "do_sample": True
    }

    print(f"📤 提交异步任务 - 请求模型: {model}")
    print(f"📋 任务详情:")
    for msg in messages:
        print(f"   {msg['role']}: {msg['content'][:50]}{'...' if len(msg['content']) > 50 else ''}")

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()

    task_info = resp.json()
    task_id = task_info.get("id")
    task_status = task_info.get("task_status")
    actual_model = task_info.get("model", "unknown")

    print(f"✅ 任务提交成功")
    print(f"   🆔 任务ID: {task_id}")
    print(f"   📊 任务状态: {task_status}")
    print(f"   🤖 接口回显模型: {actual_model}")

    # 模型版本核对
    if model.lower() != actual_model.lower():
        print(f"⚠️  警告: 请求的模型 ({model}) 与接口回显的模型 ({actual_model}) 不一致!")

    return {
        "task_id": task_id,
        "requested_model": model,
        "actual_model": actual_model,
        "task_status": task_status
    }


def poll_async_result(task_id: str, api_key: str, interval: int = 3, timeout: int = 300) -> Dict[str, Any]:
    """
    轮询异步任务结果

    Args:
        task_id: 任务ID
        api_key: API密钥
        interval: 轮询间隔（秒）
        timeout: 最大超时时间（秒）

    Returns:
        任务最终结果
    """
    url = f"https://open.bigmodel.cn/api/paas/v4/async-result/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    waited = 0
    print(f"⏳ 开始轮询任务结果 (间隔: {interval}秒, 超时: {timeout}秒)")

    while waited < timeout:
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()

            result = resp.json()
            task_status = result.get("task_status")

            print(f"   📊 状态: {task_status} (已等待: {waited}秒)")

            if task_status == "SUCCESS":
                actual_model = result.get("model", "unknown")
                print(f"✅ 任务完成!")
                print(f"   🤖 最终使用模型: {actual_model}")
                return {
                    "success": True,
                    "data": result,
                    "final_model": actual_model
                }
            elif task_status == "FAIL":
                error_msg = result.get("error", {}).get("message", "未知错误")
                print(f"❌ 任务失败: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "data": result
                }

            # 继续等待
            time.sleep(interval)
            waited += interval

        except requests.exceptions.RequestException as e:
            print(f"   ⚠️  请求异常: {str(e)}")
            time.sleep(interval)
            waited += interval

    raise TimeoutError(f"轮询超时，任务 {task_id} 在 {timeout} 秒内未完成")


def analyze_sentiment_batch(sentences: List[str], api_key: str) -> List[Dict[str, Any]]:
    """
    批量情感分析

    Args:
        sentences: 待分析的句子列表
        api_key: API密钥

    Returns:
        分析结果列表
    """
    results = []

    # 系统提示词
    system_prompt = """你是专业的情感分析专家。请对给定的文本进行情感分析，并按照以下JSON格式返回结果：
{
    "sentiment": "positive|negative|neutral",
    "confidence": 0.0,
    "emotions": ["joy", "sadness", "anger", "fear", "surprise", "disgust"],
    "analysis": "详细分析文本的情感倾向和关键特征"
}

请严格返回JSON格式，不要包含其他文字。"""

    for i, sentence in enumerate(sentences, 1):
        print(f"\n🔍 分析第 {i} 句: {sentence}")

        # 构建消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请分析以下文本的情感：\n\n{sentence}"}
        ]

        # 提交异步任务
        task_info = submit_async_chat(
            messages=messages,
            model="glm-4.6",
            api_key=api_key
        )

        # 轮询结果
        try:
            poll_result = poll_async_result(
                task_id=task_info["task_id"],
                api_key=api_key
            )

            if poll_result["success"]:
                choice = poll_result["data"]["choices"][0]
                content = choice["message"]["content"]

                # 解析JSON响应
                try:
                    analysis = json.loads(content.strip())

                    # 最终模型核对
                    requested_model = task_info["requested_model"]
                    final_model = poll_result["final_model"]
                    actual_model = poll_result["data"]["model"]

                    # 检查所有模型版本是否一致
                    models_consistent = (
                        requested_model.lower() == final_model.lower() ==
                        actual_model.lower()
                    )

                    result = {
                        "sentence": sentence,
                        "analysis": analysis,
                        "model_info": {
                            "requested": requested_model,
                            "submitted_response": task_info["actual_model"],
                            "final_response": final_model,
                            "actual_api_used": actual_model,
                            "consistent": models_consistent
                        },
                        "success": True
                    }

                    if not models_consistent:
                        print(f"❌ 模型版本不一致!")
                        result["model_info"]["warning"] = "请求的模型与实际使用的模型不一致"

                    results.append(result)

                except json.JSONDecodeError as e:
                    print(f"❌ JSON解析失败: {e}")
                    print(f"   原始响应: {content}")
                    results.append({
                        "sentence": sentence,
                        "error": f"JSON解析失败: {str(e)}",
                        "raw_response": content,
                        "success": False
                    })
            else:
                results.append({
                    "sentence": sentence,
                    "error": poll_result["error"],
                    "success": False
                })

        except Exception as e:
            print(f"❌ 处理失败: {str(e)}")
            results.append({
                "sentence": sentence,
                "error": str(e),
                "success": False
            })

    return results


def main():
    """主函数"""
    print("=" * 60)
    print("🚀 智谱AI异步情感分析系统")
    print("=" * 60)

    # 检查API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("❌ 错误: 请设置环境变量 ZHIPUAI_API_KEY")
        return 1

    # 待分析的句子
    sentences = [
        "今天天气真好，心情特别愉快！",
        "这个产品太差了，完全不值这个价钱。",
        "我不知道该说什么，就这样吧。"
    ]

    print(f"\n📝 待分析句子 ({len(sentences)}句):")
    for i, sentence in enumerate(sentences, 1):
        print(f"   {i}. {sentence}")

    # 执行批量分析
    start_time = time.time()
    results = analyze_sentiment_batch(sentences, api_key)
    end_time = time.time()

    # 打印汇总结果
    print("\n" + "=" * 60)
    print("📊 分析结果汇总")
    print("=" * 60)

    for i, result in enumerate(results, 1):
        print(f"\n--- 第 {i} 句 ---")
        print(f"句子: {result['sentence']}")

        if result["success"]:
            analysis = result["analysis"]
            model_info = result["model_info"]

            print(f"情感倾向: {analysis.get('sentiment', 'unknown')}")
            print(f"置信度: {analysis.get('confidence', 'unknown')}")
            print(f"情感关键词: {', '.join(analysis.get('emotions', []))}")
            print(f"详细分析: {analysis.get('analysis', '无')}")

            # 模型版本检查
            print("\n🤖 模型版本信息:")
            print(f"   请求模型: {model_info['requested']}")
            print(f"   提交响应: {model_info['submitted_response']}")
            print(f"   最终响应: {model_info['final_response']}")
            print(f"   API实际使用: {model_info['actual_api_used']}")

            if model_info['consistent']:
                print("   ✅ 模型版本一致")
            else:
                print("   ❌ 模型版本不一致 - 审计警告!")
                if "warning" in model_info:
                    print(f"   💡 {model_info['warning']}")
        else:
            print(f"❌ 分析失败: {result.get('error', '未知错误')}")

        print("-" * 40)

    # 总结
    success_count = sum(1 for r in results if r["success"])
    model_issues = sum(1 for r in results if r["success"] and not r["model_info"]["consistent"])

    print(f"\n📈 任务统计:")
    print(f"   总任务数: {len(results)}")
    print(f"   成功: {success_count}")
    print(f"   失败: {len(results) - success_count}")
    print(f"   模型版本问题: {model_issues}")
    print(f"   总耗时: {end_time - start_time:.2f} 秒")

    # 如果有模型版本问题，返回错误码
    if model_issues > 0:
        print("\n⚠️  警告: 检测到模型版本不一致问题，请检查审计要求!")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())