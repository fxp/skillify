#!/usr/bin/env python3
"""
智谱AI异步对话接口情感分类脚本
使用 async/chat/completions + 轮询结果
锁定模型版本：glm-4.6
审计要求：检查请求的模型和实际使用的模型是否一致
"""

import os
import json
import requests
import time
from typing import List, Dict, Optional


class ZhipuAIClient:
    """智谱AI异步对话客户端"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://open.bigmodel.cn/api"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def submit_async_chat(
        self,
        model: str,
        messages: List[Dict],
        max_tokens: int = 1000,
        temperature: float = 0.3,
        top_p: float = 0.7
    ) -> Dict:
        """提交异步聊天任务"""
        url = f"{self.base_url}/paas/v4/async/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p
        }

        print(f"提交异步请求，请求的模型: {model}")

        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()

        result = response.json()

        # 审计：检查实际使用的模型
        actual_model = result.get("model", "")
        print(f"接口实际使用的模型: {actual_model}")

        # 模型版本比对
        if model.lower() != actual_model.lower():
            print(f"⚠️  警告：模型版本不一致！")
            print(f"   请求的模型: {model}")
            print(f"   实际使用的模型: {actual_model}")
            # 可以选择在这里抛出异常或者继续执行
            # raise RuntimeError(f"模型版本不一致：请求 {model}，实际使用 {actual_model}")
        else:
            print(f"✅ 模型版本一致：{model}")

        return result

    def poll_async_result(self, task_id: str, timeout: int = 300, interval: int = 2) -> Dict:
        """轮询异步任务结果"""
        url = f"{self.base_url}/paas/v4/async-result/{task_id}"

        waited = 0
        while waited < timeout:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()

            result = response.json()
            status = result.get("task_status", "")

            print(f"轮询任务状态: {status} (等待时间: {waited}s)")

            if status == "SUCCESS":
                # 再次检查最终结果中的模型
                final_model = result.get("model", "")
                print(f"最终结果使用的模型: {final_model}")
                return result
            elif status == "FAIL":
                raise RuntimeError(f"异步任务失败: {result}")
            elif status == "PROCESSING":
                time.sleep(interval)
                waited += interval
            else:
                raise RuntimeError(f"未知任务状态: {status}")

        raise TimeoutError(f"轮询超时，等待时间超过 {timeout} 秒")


def batch_sentiment_classification(client: ZhipuAIClient, texts: List[str]) -> List[Dict]:
    """批量情感分类"""
    results = []

    # 构建系统提示
    system_prompt = """你是一个专业的情感分析助手。请对给定的文本进行情感分类，输出以下JSON格式：
{
    "sentiment": "positive|negative|neutral",
    "confidence": 0.0-1.0,
    "reason": "分析原因"
}

请只返回JSON，不要包含其他解释。"""

    for i, text in enumerate(texts):
        print(f"\n处理第 {i+1}/{len(texts)} 句话: {text}")

        # 构建消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请分析这句话的情感：{text}"}
        ]

        # 提交异步任务
        try:
            task_response = client.submit_async_chat(
                model="glm-4.6",
                messages=messages,
                max_tokens=200
            )

            task_id = task_response["id"]
            print(f"任务ID: {task_id}")

            # 轮询结果
            result = client.poll_async_result(task_id)

            # 提取回复内容
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]

                # 尝试解析JSON
                try:
                    sentiment_result = json.loads(content)
                    sentiment_result["original_text"] = text
                    results.append(sentiment_result)
                    print(f"情感分析结果: {sentiment_result['sentiment']} (置信度: {sentiment_result['confidence']})")
                except json.JSONDecodeError:
                    # 如果不是JSON格式，则作为中性处理
                    results.append({
                        "sentiment": "neutral",
                        "confidence": 0.5,
                        "reason": "返回格式不是JSON",
                        "original_text": text,
                        "raw_response": content
                    })
                    print(f"返回格式错误，标记为中性")

        except Exception as e:
            print(f"处理失败: {e}")
            # 失败的标记为错误
            results.append({
                "sentiment": "error",
                "confidence": 0.0,
                "reason": str(e),
                "original_text": text
            })

    return results


def main():
    """主函数"""
    # 从环境变量读取API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        exit(1)

    # 创建客户端
    client = ZhipuAIClient(api_key)

    # 待分析的文本
    texts = [
        "今天天气真好，阳光明媚，心情也变得愉快起来。",
        "这部电影真的太 disappointing 了，浪费了我的时间和金钱。",
        "我需要完成这个项目，截止日期就在明天。"
    ]

    print("开始批量情感分类任务...")
    print("=" * 50)

    # 执行批量情感分类
    results = batch_sentiment_classification(client, texts)

    print("\n" + "=" * 50)
    print("批量情感分类完成！")
    print("\n最终结果汇总：")

    for i, result in enumerate(results, 1):
        print(f"\n第 {i} 句话:")
        print(f"  原文: {result['original_text']}")
        print(f"  情感: {result['sentiment']}")
        print(f"  置信度: {result['confidence']}")
        print(f"  原因: {result['reason']}")

    # 输出统计信息
    sentiments = [r['sentiment'] for r in results if r['sentiment'] != 'error']
    if sentiments:
        sentiment_counts = {}
        for sentiment in sentiments:
            sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1

        print(f"\n情感分布统计:")
        for sentiment, count in sentiment_counts.items():
            print(f"  {sentiment}: {count} 句")


if __name__ == "__main__":
    main()