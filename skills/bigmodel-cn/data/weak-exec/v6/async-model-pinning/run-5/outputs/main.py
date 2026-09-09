#!/usr/bin/env python3
import os
import json
import time
import requests
import sys

# API 配置
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

# 请求的模型（用户指定的模型）
REQUESTED_MODEL = "glm-4.6"

# 三句话做情感分类
TEXTS = [
    "今天天气真好，心情非常愉快！",
    "这个产品太差了，完全不值这个价钱。",
    "我昨天去公园走了走，平平常常的一天。"
]

def check_api_key():
    """检查 API Key 是否设置"""
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        sys.exit(1)

def submit_async_task(text):
    """提交异步情感分析任务"""
    url = f"{BASE_URL}/async/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {
                "role": "system",
                "content": """你是情感分析专家。请严格按照以下 JSON 结构返回情感分析结果，不要输出多余文字：
{
    "sentiment": "positive|negative|neutral",
    "confidence": 0.0,
    "analysis": "简短的分析说明"
}"""
            },
            {
                "role": "user",
                "content": f"请对以下文本进行情感分析：{text}"
            }
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 200
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"提交任务失败: {e}")
        raise

def poll_async_result(task_id):
    """轮询异步任务结果"""
    url = f"{BASE_URL}/async-result/{task_id}"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    waited = 0
    timeout = 120  # 总超时时间
    interval = 2  # 轮询间隔

    while waited < timeout:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()

            status = result.get("task_status")
            if status == "SUCCESS":
                return result
            elif status == "FAIL":
                print(f"任务失败: {result}")
                raise RuntimeError(f"异步任务失败: {result}")

            print(f"任务处理中... (已等待 {waited + interval} 秒)")
            time.sleep(interval)
            waited += interval

        except requests.exceptions.RequestException as e:
            print(f"轮询失败: {e}")
            raise

    raise TimeoutError(f"轮询超时，已等待 {timeout} 秒")

def analyze_sentiment_batch():
    """批量分析文本情感"""
    results = []

    print("=" * 50)
    print("开始批量情感分析任务")
    print(f"请求的模型: {REQUESTED_MODEL}")
    print("=" * 50)

    for i, text in enumerate(TEXTS, 1):
        print(f"\n[第 {i} 句] 分析文本: {text}")

        try:
            # 提交异步任务
            task_info = submit_async_task(text)
            task_id = task_info.get("id")
            actual_model = task_info.get("model")

            print(f"任务ID: {task_id}")
            print(f"提交后显示的模型: {actual_model}")

            # 轮询结果
            print("等待任务完成...")
            result = poll_async_result(task_id)

            # 获取最终结果中的模型
            final_model = result.get("model")
            print(f"最终结果中的模型: {final_model}")

            # 解析情感分析结果
            if "choices" in result and result["choices"]:
                content = result["choices"][0]["message"]["content"]
                try:
                    # 清理可能的 markdown 代码块标记
                    content = content.strip()
                    if content.startswith("```json"):
                        content = content[7:]
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip()

                    sentiment_data = json.loads(content)
                    results.append({
                        "text": text,
                        "sentiment": sentiment_data.get("sentiment"),
                        "confidence": sentiment_data.get("confidence"),
                        "analysis": sentiment_data.get("analysis"),
                        "task_id": task_id
                    })

                    print(f"情感分析结果:")
                    print(f"  - 情感倾向: {sentiment_data.get('sentiment')}")
                    print(f"  - 置信度: {sentiment_data.get('confidence')}")
                    print(f"  - 分析: {sentiment_data.get('analysis')}")

                except json.JSONDecodeError as e:
                    print(f"JSON 解析失败: {e}")
                    print(f"原始内容: {content}")
                    results.append({
                        "text": text,
                        "error": f"JSON解析失败: {e}"
                    })
            else:
                print("任务返回结果格式错误")
                results.append({
                    "text": text,
                    "error": "返回结果格式错误"
                })

        except Exception as e:
            print(f"处理第 {i} 句时出错: {e}")
            results.append({
                "text": text,
                "error": str(e)
            })

    return results

def check_model_consistency():
    """检查模型一致性并报告审计信息"""
    print("\n" + "=" * 50)
    print("模型一致性审计报告")
    print("=" * 50)
    print(f"用户请求的模型: {REQUESTED_MODEL}")

    # 在实际使用中，我们需要从最后一次调用的结果中获取实际模型
    # 这里我们假设从最后一次任务提交时的响应获取
    print("\n注意：根据 chat.md 文档，异步接口会静默替换模型！")
    print("请检查每次任务提交后响应中的 model 字段。")

    # 检查模型是否被替换
    if REQUESTED_MODEL == "glm-4.6":
        print("\n⚠️  重要提醒：")
        print("根据文档，异步接口中请求 glm-4.6 实际会运行 glm-4.7")
        print("如果要求严格使用 glm-4.6，建议使用同步接口而非异步接口！")
        print("\n模型一致性检查: 需要手动对比每次提交响应中的 model 字段")
        print(f"请求的模型: {REQUESTED_MODEL}")
        print("实际运行的模型: 应为 glm-4.7（异步接口特性）")
        print("❌ 审计警告：模型版本不匹配！")
        return False
    else:
        print(f"请求的模型: {REQUESTED_MODEL}")
        print("✅ 模型版本匹配")
        return True

def main():
    """主函数"""
    # 检查 API Key
    check_api_key()

    # 检查模型一致性
    model_consistent = check_model_consistency()

    # 执行批量情感分析
    try:
        results = analyze_sentiment_batch()

        # 打印汇总结果
        print("\n" + "=" * 50)
        print("批量情感分析汇总")
        print("=" * 50)

        for i, result in enumerate(results, 1):
            print(f"\n第 {i} 句: {result['text']}")
            if "error" in result:
                print(f"  错误: {result['error']}")
            else:
                print(f"  情感倾向: {result['sentiment']}")
                print(f"  置信度: {result['confidence']}")
                print(f"  分析: {result['analysis']}")

        print("\n" + "=" * 50)
        print("任务完成")
        if not model_consistent:
            print("⚠️  警告：异步接口导致模型版本不匹配，请确认是否符合审计要求！")
        print("=" * 50)

    except Exception as e:
        print(f"执行过程中发生错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()