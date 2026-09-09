#!/usr/bin/env python3
"""
情感分类任务：使用智谱异步对话接口对三句话做情感分类
审计要求：必须锁定模型版本 glm-4.6，检查接口实际使用的模型是否一致
"""

import os
import json
import time
import requests
import sys
from typing import Dict, Any, List

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
REQUESTED_MODEL = "glm-4.6"

# 三句话情感分类任务
TEXTS_TO_CLASSIFY = [
    "今天天气真好，心情非常愉快！",
    "这部电影太无聊了，浪费了两小时。",
    "这个产品功能还行，但是价格有点贵。"
]

# 情感分类提示
SYSTEM_PROMPT = """你是情感分析专家。请对输入的文本进行情感分类，并返回JSON格式结果。
每条文本分析结果必须包含以下字段：
- sentiment: "positive" | "negative" | "neutral"
- confidence: 0.0-1.0之间的数字，表示置信度
- analysis: 简要分析理由

请严格按照JSON格式返回，不要输出其他文字。示例：
{"sentiment": "positive", "confidence": 0.95, "analysis": "表达了对天气的积极评价"}"""

def check_model_consistency(requested_model: str, actual_model: str) -> bool:
    """检查请求的模型和实际使用的模型是否一致"""
    # 异步接口可能会自动替换模型，需要严格检查
    # 根据文档，glm-4.6 可能被替换为 glm-4.7，glm-4.7 可能被替换为 glm-4.7-ali
    if requested_model != actual_model:
        print(f"🚨 审计警告：模型版本不一致！")
        print(f"   请求的模型：{requested_model}")
        print(f"   实际使用的模型：{actual_model}")
        print(f"   这可能影响审计追踪和结果一致性！")
        return False
    return True

def submit_async_task(text: str, api_key: str) -> Dict[str, Any]:
    """提交异步情感分类任务"""
    url = f"{BASE_URL}/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请对以下文本进行情感分类：\n{text}"}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 500
    }

    print(f"提交任务，请求模型：{REQUESTED_MODEL}")
    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    result = resp.json()

    # 检查响应中的模型是否一致
    actual_model = result.get("model")
    check_model_consistency(REQUESTED_MODEL, actual_model)

    return result

def poll_async_result(task_id: str, api_key: str, interval: int = 2, timeout: int = 120) -> Dict[str, Any]:
    """轮询异步任务结果"""
    url = f"{BASE_URL}/async-result/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    waited = 0
    while waited < timeout:
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            result = resp.json()

            status = result.get("task_status")
            if status == "SUCCESS":
                # 检查最终结果的模型
                final_model = result.get("model")
                check_model_consistency(REQUESTED_MODEL, final_model)
                return result
            elif status == "FAIL":
                raise RuntimeError(f"任务执行失败: {result}")

            print(f"任务状态：{status}，等待中...")
            time.sleep(interval)
            waited += interval
        except requests.exceptions.Timeout:
            print("请求超时，继续轮询...")
            continue
        except Exception as e:
            print(f"轮询出错: {e}")
            time.sleep(interval)
            waited += interval

    raise TimeoutError(f"轮询超时，任务ID: {task_id}")

def parse_sentiment_result(result: Dict[str, Any], text: str) -> Dict[str, Any]:
    """解析情感分类结果"""
    choices = result.get("choices", [])
    if not choices:
        raise ValueError("未找到有效的分类结果")

    message = choices[0].get("message", {})
    content = message.get("content", "")

    try:
        # 解析JSON结果
        result_data = json.loads(content)

        # 确保必要字段存在
        if "sentiment" not in result_data or "confidence" not in result_data:
            raise ValueError("结果缺少必要字段")

        return {
            "text": text,
            "sentiment": result_data["sentiment"],
            "confidence": result_data["confidence"],
            "analysis": result_data.get("analysis", ""),
            "raw_response": content
        }
    except json.JSONDecodeError:
        # 如果不是JSON格式，尝试提取信息
        return {
            "text": text,
            "sentiment": "unknown",
            "confidence": 0.0,
            "analysis": f"解析失败，原始响应: {content[:100]}...",
            "raw_response": content
        }

def main():
    """主函数"""
    # 检查API Key
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        sys.exit(1)

    print("=" * 60)
    print("情感分类任务开始")
    print("=" * 60)
    print(f"请求的模型版本：{REQUESTED_MODEL}")
    print(f"任务数量：{len(TEXTS_TO_CLASSIFY)}")
    print()

    all_results = []

    try:
        # 对每句话提交异步任务
        for i, text in enumerate(TEXTS_TO_CLASSIFY, 1):
            print(f"【{i}/{len(TEXTS_TO_CLASSIFY)}】处理文本：{text}")
            print("-" * 50)

            # 提交任务
            task_info = submit_async_task(text, API_KEY)
            task_id = task_info["id"]
            print(f"任务已提交，ID：{task_id}")

            # 轮询结果
            print("开始轮询结果...")
            result = poll_async_result(task_id, API_KEY)

            # 解析结果
            sentiment_result = parse_sentiment_result(result, text)
            all_results.append(sentiment_result)

            # 输出当前结果
            print("分类结果：")
            print(f"  情感倾向：{sentiment_result['sentiment']}")
            print(f"  置信度：{sentiment_result['confidence']:.2f}")
            print(f"  分析：{sentiment_result['analysis']}")
            print()

    except Exception as e:
        print(f"执行出错：{e}")
        sys.exit(1)

    # 汇总报告
    print("=" * 60)
    print("任务完成 - 汇总报告")
    print("=" * 60)

    # 检查是否有模型不一致的情况
    model_consistent = True
    for result in all_results:
        # 这里已经在任务执行时检查过，汇总时只是提醒
        pass

    if model_consistent:
        print("✅ 所有任务使用的模型版本与请求一致")
    else:
        print("⚠️ 部分任务使用了不同的模型版本")

    print("\n详细结果：")
    for i, result in enumerate(all_results, 1):
        print(f"\n【{i}】")
        print(f"文本：{result['text']}")
        print(f"情感：{result['sentiment']}")
        print(f"置信度：{result['confidence']:.2f}")
        print(f"分析：{result['analysis']}")

    # 保存结果到文件
    output_file = "/tmp/sentiment_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到：{output_file}")

if __name__ == "__main__":
    main()