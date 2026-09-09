import os
import requests
import time
import json


def analyze_sentiment(text):
    """对文本进行情感分析"""
    return f"分析文本: {text}"


def submit_async_task(api_key, text, index):
    """提交异步情感分析任务"""
    url = "https://open.bigmodel.cn/api/paas/v4/async/chat/completions"

    payload = {
        "model": "glm-4.6",  # 我请求的模型
        "messages": [
            {
                "role": "system",
                "content": "你是一个专业的情感分析专家。请对用户输入的文本进行情感分类，只返回 JSON 格式结果：{\"sentiment\": \"positive|negative|neutral\", \"confidence\": 0.0-1.0, \"keywords\": [], \"analysis\": \"简要分析\"}"
            },
            {
                "role": "user",
                "content": f"请分析以下文本的情感：{text}"
            }
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 500
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    print(f"提交任务 {index+1}: 文本='{text}'")
    print(f"我请求的模型: {payload['model']}")

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()

    task = resp.json()

    # 检查异步任务提交时返回的模型
    actual_model = task.get("model")
    print(f"任务提交时接口使用的模型: {actual_model}")

    # 模型版本一致性检查
    if actual_model != payload["model"]:
        print(f"⚠️  警告: 请求的模型 ({payload['model']}) 与实际使用的模型 ({actual_model}) 不一致!")
        print("    这可能影响结果的稳定性和可复现性!")
    else:
        print("✓ 模型版本一致")

    print(f"任务ID: {task['id']}")
    print(f"任务状态: {task['task_status']}")
    print("-" * 50)

    return task["id"], actual_model


def poll_async_result(task_id, api_key, timeout=60, interval=2):
    """轮询异步任务结果"""
    url = f"https://open.bigmodel.cn/api/paas/v4/async-result/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    waited = 0
    while waited < timeout:
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            result = resp.json()

            status = result.get("task_status")
            if status == "SUCCESS":
                print(f"任务完成! 最终模型: {result.get('model')}")
                return result
            elif status == "FAIL":
                raise RuntimeError(f"任务失败: {result}")
            else:
                print(f"任务处理中... 状态: {status}, 已等待 {waited} 秒")
                time.sleep(interval)
                waited += interval

        except requests.exceptions.RequestException as e:
            print(f"请求失败: {e}, 重试中...")
            time.sleep(interval)
            waited += interval

    raise TimeoutError(f"轮询超时，等待 {timeout} 秒后仍未完成")


def main():
    """主函数：批量情感分析"""
    # 从环境变量读取 API Key
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY")
        print("例如: export ZHIPUAI_API_KEY='your_api_key_here'")
        return

    # 待分析的文本列表
    texts = [
        "今天天气真好，心情非常愉快！",
        "这个产品太差了，完全不值这个价钱。",
        "我今天去了超市，买了些日常用品。"
    ]

    print("开始批量情感分析任务...")
    print("=" * 60)

    task_results = []

    # 提交所有异步任务
    for i, text in enumerate(texts):
        try:
            task_id, submitted_model = submit_async_task(api_key, text, i)
            task_results.append({
                "task_id": task_id,
                "text": text,
                "submitted_model": submitted_model
            })
        except Exception as e:
            print(f"提交任务 {i+1} 失败: {e}")
            continue

    print("\n开始轮询任务结果...")
    print("=" * 60)

    # 轮询获取所有任务结果
    for i, task in enumerate(task_results):
        try:
            print(f"\n处理任务 {i+1}/{len(task_results)}")
            result = poll_async_result(task["task_id"], api_key)

            # 解析情感分析结果
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                try:
                    sentiment_data = json.loads(content)
                    print(f"文本: {task['text']}")
                    print(f"情感: {sentiment_data.get('sentiment', 'unknown')}")
                    print(f"置信度: {sentiment_data.get('confidence', 0.0)}")
                    print(f"关键词: {sentiment_data.get('keywords', [])}")
                    print(f"分析: {sentiment_data.get('analysis', '')}")
                except json.JSONDecodeError:
                    print(f"原始响应: {content}")
            else:
                print("无法解析响应结果")

            print(f"最终使用模型: {result.get('model')}")
            print("-" * 30)

        except Exception as e:
            print(f"任务 {i+1} 处理失败: {e}")
            continue

    print("\n批量情感分析完成!")


if __name__ == "__main__":
    main()