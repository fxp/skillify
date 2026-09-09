#!/usr/bin/env python3
"""
智谱AI联网问答工具
问题：2026年智谱BigModel发布了哪些新模型
"""

import os
import requests
import json

def get_zhipuai_answer():
    """调用智谱AI API获取带联网搜索的答案"""

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

    # 工具定义 - 联网搜索
    tools = [{
        "type": "web_search",
        "web_search": {
            "enable": True,
            "search_engine": "search_pro_bing",  # 使用Bing搜索引擎，确保返回可点击链接
            "search_query": "2026年智谱BigModel发布的新模型",
            "search_intent": False,
            "count": 10,
            "search_recency_filter": "oneYear",  # 搜索最近一年的信息
            "content_size": "high",
            "search_result": True  # 必须设置为True才能获取来源信息
        }
    }]

    # 请求体
    payload = {
        "model": "glm-5.3",  # 使用支持工具调用的模型
        "messages": [
            {
                "role": "user",
                "content": "2026年智谱BigModel发布了哪些新模型？请使用联网搜索工具查找最新信息，并在回答时列出信息来源。"
            }
        ],
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 2000,
        "temperature": 0.3
    }

    try:
        # 发送请求
        print("正在调用智谱AI API...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        data = response.json()

        # 获取回答内容
        answer = data["choices"][0]["message"]["content"]

        # 获取来源信息
        sources = []
        if "web_search" in data and data["web_search"]:
            for search_result in data["web_search"]:
                source = {
                    "title": search_result.get("title", ""),
                    "url": search_result.get("link", ""),
                    "media": search_result.get("media", "")
                }
                sources.append(source)

        # 打印答案
        print("\n" + "="*50)
        print("回答：")
        print("="*50)
        print(answer)

        # 打印来源信息
        if sources:
            print("\n" + "="*50)
            print("信息来源：")
            print("="*50)
            for i, source in enumerate(sources, 1):
                print(f"{i}. [{source['title']}]({source['url']})")
                if source['media']:
                    print(f"   来源网站：{source['media']}")
                print()
        else:
            print("\n" + "="*50)
            print("信息来源：")
            print("="*50)
            print("未获取到具体的来源信息")

    except requests.exceptions.RequestException as e:
        print(f"请求错误：{e}")
    except json.JSONDecodeError as e:
        print(f"JSON解析错误：{e}")
    except KeyError as e:
        print(f"响应数据格式错误，缺少字段：{e}")
        print(f"完整响应：{json.dumps(data, indent=2, ensure_ascii=False)}")

if __name__ == "__main__":
    get_zhipuai_answer()