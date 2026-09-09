#!/usr/bin/env python3
"""
批量情感分类任务 - 使用智谱AI异步接口
锁定模型版本为 glm-4.6，审计要求对比请求模型和实际使用模型
"""

import os
import json
import time
import requests
from typing import List, Dict, Optional


class ZhipuAIClient:
    """智谱AI异步对话客户端"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://open.bigmodel.cn/api/paas/v4"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def submit_async_task(self, model: str, messages: List[Dict], max_tokens: int = 1000) -> Dict:
        """提交异步对话任务"""
        url = f"{self.base_url}/async/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "do_sample": False,  # 确定输出
            "temperature": 0.0
        }

        resp = requests.post(url, headers=self.headers, json=payload)
        resp.raise_for_status()
        result = resp.json()

        # 打印审计信息：请求的模型和接口实际使用的模型
        print("=" * 60)
        print("🔍 审计信息：")
        print(f"   请求的模型: {model}")
        print(f"   接口实际返回模型: {result.get('model', 'N/A')}")

        # 检查模型版本是否一致
        requested_model = model
        actual_model = result.get('model', '')

        if requested_model != actual_model:
            print("⚠️  警告：模型版本不一致！")
            print(f"   请求的是 {requested_model}，实际使用的是 {actual_model}")
            print("   这可能导致结果不可预测，请检查是否符合审计要求！")
        else:
            print("✅ 模型版本一致")
        print("=" * 60)

        return result

    def poll_async_result(self, task_id: str, interval: int = 3, timeout: int = 300) -> Dict:
        """轮询异步任务结果"""
        url = f"{self.base_url}/async-result/{task_id}"
        waited = 0

        while waited < timeout:
            try:
                resp = requests.get(url, headers=self.headers, timeout=30)
                resp.raise_for_status()
                result = resp.json()

                status = result.get("task_status")
                print(f"轮询中... 状态: {status}, 已等待: {waited}s")

                if status == "SUCCESS":
                    # 打印审计信息：最终响应中的模型
                    final_model = result.get("model", "N/A")
                    print(f"✅ 任务完成，最终使用模型: {final_model}")

                    # 再次验证模型版本
                    requested_model = "glm-4.6"
                    if requested_model != final_model:
                        print("⚠️  最终审计：模型版本不一致！")
                        print(f"   请求的是 {requested_model}，最终使用的是 {final_model}")
                    else:
                        print("✅ 最终审计：模型版本一致")

                    return result
                elif status == "FAIL":
                    raise RuntimeError(f"任务失败: {result}")

                time.sleep(interval)
                waited += interval

            except requests.exceptions.Timeout:
                print(f"⏰ 轮询超时（{waited}s），继续等待...")
                continue
            except Exception as e:
                print(f"⚠️  轮询时发生错误: {e}")
                if waited >= timeout:
                    raise
                time.sleep(interval)
                waited += interval

        raise TimeoutError(f"轮询超时，等待超过 {timeout} 秒")


def sentiment_analysis(text: str) -> Dict:
    """情感分析提示词"""
    return {
        "role": "user",
        "content": f"请对以下文本进行情感分类，只返回一个词：正面、负面或中性。\n文本：{text}"
    }


def main():
    """主函数"""
    # 从环境变量读取API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("❌ 错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 要分析的三个句子
    texts = [
        "今天天气真好，心情很愉快！",
        "这个产品太糟糕了，完全不值这个价钱。",
        "我昨天去看了电影，剧情一般但演技还不错。"
    ]

    # 打印任务信息
    print("🚀 开始批量情感分析任务")
    print(f"📝 分析文本数量: {len(texts)}")
    print(f"🎯 目标模型: glm-4.6")
    print()

    client = ZhipuAIClient(api_key)
    results = []

    for i, text in enumerate(texts, 1):
        print(f"\n📊 处理第 {i}/{len(texts)} 个文本:")
        print(f"   文本: {text}")

        # 构建消息
        messages = [
            {
                "role": "system",
                "content": "你是一个情感分析专家，请准确判断文本的情感倾向。"
            },
            sentiment_analysis(text)
        ]

        try:
            # 提交异步任务
            print("   🔄 提交异步任务...")
            task_response = client.submit_async_task(
                model="glm-4.6",
                messages=messages,
                max_tokens=50
            )

            task_id = task_response["id"]
            print(f"   📋 任务ID: {task_id}")

            # 轮询结果
            print("   ⏳ 开始轮询结果...")
            result = client.poll_async_result(task_id)

            # 提取情感分析结果
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                content = content.strip().strip('"').strip("'")
                # 确保是有效的情感分类
                if content in ["正面", "负面", "中性"]:
                    sentiment = content
                else:
                    # 如果不是标准答案，尝试判断
                    if "正面" in content or "积极" in content or "好" in content:
                        sentiment = "正面"
                    elif "负面" in content or "消极" in content or "坏" in content:
                        sentiment = "负面"
                    else:
                        sentiment = "中性"

                results.append({
                    "text": text,
                    "sentiment": sentiment,
                    "task_id": task_id,
                    "usage": result.get("usage", {})
                })

                print(f"   ✅ 分析结果: {sentiment}")
            else:
                print(f"   ❌ 无法获取结果: {result}")
                results.append({
                    "text": text,
                    "sentiment": "分析失败",
                    "task_id": task_id,
                    "error": result
                })

        except Exception as e:
            print(f"   ❌ 处理失败: {e}")
            results.append({
                "text": text,
                "sentiment": "错误",
                "task_id": task_id if 'task_id' in locals() else "unknown",
                "error": str(e)
            })

    # 输出汇总结果
    print("\n" + "=" * 60)
    print("📋 批量情感分析结果汇总:")
    print("=" * 60)

    for i, result in enumerate(results, 1):
        print(f"{i}. 文本: {result['text']}")
        print(f"   情感: {result['sentiment']}")
        if result.get('usage'):
            print(f"   Token使用: {result['usage']}")
        if result.get('task_id'):
            print(f"   任务ID: {result['task_id']}")
        print()

    # 统计
    successful_results = [r for r in results if r['sentiment'] not in ['分析失败', '错误']]
    if successful_results:
        positive = sum(1 for r in successful_results if r['sentiment'] == '正面')
        negative = sum(1 for r in successful_results if r['sentiment'] == '负面')
        neutral = sum(1 for r in successful_results if r['sentiment'] == '中性')

        print("📊 统计:")
        print(f"   总数: {len(successful_results)}")
        print(f"   正面: {positive}")
        print(f"   负面: {negative}")
        print(f"   中性: {neutral}")

    print("\n✅ 任务完成")


if __name__ == "__main__":
    main()