#!/usr/bin/env python3
"""
联网问答小工具
调用智谱AI GLM模型进行联网搜索，回答"2026年智谱BigModel发布了哪些新模型"问题
并在答案下方列出实际参考的信息来源
"""

import os
import requests
import json

def main():
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # API端点
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 定义工具 - 联网搜索
    tools = [{
        "type": "web_search",
        "web_search": {
            "enable": True,
            "search_engine": "search_pro_bing",  # 使用Bing搜索引擎以获取真实链接
            "search_query": "2026年智谱AI BigModel新模型发布",  # 搜索查询
            "search_intent": False,  # 直接搜索，不做意图识别
            "count": 10,  # 返回10条结果
            "search_recency_filter": "oneMonth",  # 最近一个月的内容
            "content_size": "high",  # 详细内容
            "search_result": True  # 必须设置为True才能获取web_search字段
        }
    }]

    # 构建请求体
    payload = {
        "model": "glm-5.3",  # 使用支持工具调用的模型
        "messages": [
            {
                "role": "user",
                "content": "2026年智谱BigModel发布了哪些新模型？请使用联网搜索获取最新信息，并在回答时标注信息来源。"
            }
        ],
        "tools": tools,
        "tool_choice": "auto",  # 让模型决定是否使用工具
        "max_tokens": 2000,  # 足够的输出长度
        "temperature": 0.3,  # 较低的temperature以保证准确性
    }

    try:
        # 发送请求
        print("正在调用智谱AI API进行联网搜索...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 获取回答内容
        answer = result["choices"][0]["message"]["content"]
        print("\n=== 回答 ===")
        print(answer)

        # 检查是否有联网搜索的来源信息
        if "web_search" in result:
            sources = result["web_search"]
            if sources and isinstance(sources, list):
                print("\n=== 信息来源 ===")
                for i, source in enumerate(sources, 1):
                    # 确保source是字典类型
                    if isinstance(source, dict):
                        title = source.get("title", f"来源 {i}")
                        link = source.get("link", "")
                        media = source.get("media", "")
                        publish_date = source.get("publish_date", "")

                        # 构建来源信息字符串
                        source_info = f"{i}. [{title}]"
                        if media:
                            source_info += f" ({media})"
                        if publish_date:
                            source_info += f" - {publish_date}"
                        if link:
                            source_info += f"\n   链接：{link}"
                        else:
                            source_info += "\n   链接：链接不可用"

                        print(source_info)
                        print()
            else:
                print("\n=== 信息来源 ===")
                print("未找到具体的来源信息")
        else:
            print("\n=== 信息来源 ===")
            print("回答中未包含来源信息（可能需要调整工具参数）")

    except requests.exceptions.RequestException as e:
        print(f"请求错误：{e}")
    except json.JSONDecodeError as e:
        print(f"JSON解析错误：{e}")
    except KeyError as e:
        print(f"响应格式错误：缺少字段 {e}")
        print(f"完整响应：{json.dumps(result, ensure_ascii=False, indent=2)}")
    except Exception as e:
        print(f"发生错误：{e}")

if __name__ == "__main__":
    main()