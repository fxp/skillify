#!/usr/bin/env python3
"""
异步批量情感分类脚本
使用智谱AI异步接口对三句话进行情感分类，锁定模型版本为glm-4.6
"""

import os
import json
import requests
import time
from typing import List, Dict, Any

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api/"
REQUESTED_MODEL = "glm-4.6"

# 检查API Key
if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

# 待分类的三句话
SENTENCES = [
    "今天天气真好，心情很愉快！",
    "这个产品太差了，完全不值这个价钱。",
    "我不知道该说什么，就这样吧。"
]

# 请求头
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

def submit_async_task(sentence: str, model: str) -> Dict[str, Any]:
    """提交异步任务"""
    url = f"{BASE_URL}paas/v4/async/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是一个情感分析专家。请分析以下句子的情感，并以JSON格式返回：{\"sentiment\": \"positive/negative/neutral\", \"confidence\": 0.0-1.0, \"analysis\": \"...\"}"
            },
            {
                "role": "user",
                "content": f"请分析这句话的情感：{sentence}"
            }
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 500
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        print(f"提交任务成功 - 句子: {sentence[:20]}...")
        print(f"  任务ID: {result.get('id')}")
        print(f"  请求模型: {result.get('model')}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"提交任务失败 - 句子: {sentence[:20]}...")
        print(f"  错误: {e}")
        raise

def poll_async_result(task_id: str, timeout: int = 120, interval: int = 2) -> Dict[str, Any]:
    """轮询异步任务结果"""
    url = f"{BASE_URL}paas/v4/async-result/{task_id}"

    waited = 0
    while waited < timeout:
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            result = resp.json()

            status = result.get("task_status")
            if status == "SUCCESS":
                print(f"任务完成 - 任务ID: {task_id}")
                return result
            elif status == "FAIL":
                error_msg = result.get("error", "未知错误")
                raise RuntimeError(f"任务失败 - 任务ID: {task_id}, 错误: {error_msg}")
            else:
                print(f"任务处理中 - 任务ID: {task_id}, 状态: {status}")
                time.sleep(interval)
                waited += interval

        except requests.exceptions.RequestException as e:
            print(f"查询任务结果时出错 - 任务ID: {task_id}, 错误: {e}")
            raise

    raise TimeoutError(f"轮询超时 - 任务ID: {task_id}")

def analyze_sentiment_batch(sentences: List[str], model: str) -> List[Dict[str, Any]]:
    """批量进行情感分析"""
    results = []
    tasks = []

    print("=" * 60)
    print("开始批量情感分析任务")
    print(f"请求的模型: {model}")
    print("=" * 60)

    # 第一步：提交所有异步任务
    print("\n[第一步] 提交异步任务...")
    for i, sentence in enumerate(sentences):
        try:
            task = submit_async_task(sentence, model)
            tasks.append({
                "task_id": task["id"],
                "sentence": sentence,
                "index": i
            })
        except Exception as e:
            print(f"第 {i+1} 个句子提交失败: {e}")
            continue

    if not tasks:
        raise RuntimeError("所有任务提交都失败了")

    print(f"\n成功提交 {len(tasks)} 个任务")

    # 第二步：轮询所有任务结果
    print("\n[第二步] 轮询任务结果...")
    for task_info in tasks:
        task_id = task_info["task_id"]
        sentence = task_info["sentence"]
        index = task_info["index"]

        try:
            result = poll_async_result(task_id)

            # 检查实际使用的模型
            actual_model = result.get("model")
            print(f"\n任务 {index+1} 结果:")
            print(f"  原句: {sentence}")
            print(f"  请求模型: {model}")
            print(f"  实际模型: {actual_model}")

            # 模型版本核对
            if actual_model != model:
                print(f"  ⚠️  警告：模型版本不一致！请求的是 {model}，实际使用的是 {actual_model}")
            else:
                print(f"  ✅ 模型版本一致")

            # 解析情感分析结果
            if "choices" in result and result["choices"]:
                choice = result["choices"][0]
                content = choice.get("message", {}).get("content", "")

                try:
                    # 尝试解析JSON结果
                    sentiment_data = json.loads(content)
                    results.append({
                        "index": index,
                        "sentence": sentence,
                        "sentiment": sentiment_data.get("sentiment", "unknown"),
                        "confidence": sentiment_data.get("confidence", 0.0),
                        "analysis": sentiment_data.get("analysis", ""),
                        "requested_model": model,
                        "actual_model": actual_model,
                        "model_match": model == actual_model
                    })
                except json.JSONDecodeError:
                    # 如果不是JSON格式，直接使用原始内容
                    results.append({
                        "index": index,
                        "sentence": sentence,
                        "sentiment": "unknown",
                        "confidence": 0.0,
                        "analysis": content,
                        "requested_model": model,
                        "actual_model": actual_model,
                        "model_match": model == actual_model
                    })
            else:
                print(f"  ⚠️  警告：响应中没有choices字段")
                results.append({
                    "index": index,
                    "sentence": sentence,
                    "sentiment": "error",
                    "confidence": 0.0,
                    "analysis": "响应格式错误",
                    "requested_model": model,
                    "actual_model": actual_model,
                    "model_match": model == actual_model
                })

        except Exception as e:
            print(f"\n任务 {index+1} 失败:")
            print(f"  原句: {sentence}")
            print(f"  错误: {e}")
            results.append({
                "index": index,
                "sentence": sentence,
                "sentiment": "error",
                "confidence": 0.0,
                "analysis": str(e),
                "requested_model": model,
                "actual_model": "unknown",
                "model_match": False
            })

    return results

def main():
    """主函数"""
    try:
        print("智谱AI异步情感分析脚本")
        print(f"请求的模型版本: {REQUESTED_MODEL}")
        print("=" * 50)

        # 执行批量情感分析
        results = analyze_sentiment_batch(SENTENCES, REQUESTED_MODEL)

        # 打印汇总结果
        print("\n" + "=" * 60)
        print("情感分析结果汇总")
        print("=" * 60)

        for result in results:
            print(f"\n句子 {result['index'] + 1}: {result['sentence']}")
            print(f"情感倾向: {result['sentiment']}")
            print(f"置信度: {result['confidence']:.2f}")
            print(f"分析结果: {result['analysis']}")
            print(f"模型版本: {'✅ 一致' if result['model_match'] else '❌ 不一致'}")
            if not result['model_match']:
                print(f"  请求: {result['requested_model']} vs 实际: {result['actual_model']}")

        # 统计信息
        total = len(results)
        matched = sum(1 for r in results if r['model_match'])
        print(f"\n模型版本核对结果: {matched}/{total} 个任务模型版本一致")

        if matched != total:
            print("⚠️  警告：存在模型版本不一致的情况，请检查审计要求！")
            return 1
        else:
            print("✅ 所有任务模型版本一致，符合审计要求")
            return 0

    except Exception as e:
        print(f"脚本执行出错: {e}")
        return 1

if __name__ == "__main__":
    exit(main())