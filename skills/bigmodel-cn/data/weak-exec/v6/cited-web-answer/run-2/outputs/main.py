#!/usr/bin/env python3
"""
联网问答小工具
使用智谱AI GLM模型进行联网搜索，回答关于2026年智谱BigModel发布新模型的问题
"""

import os
import json
import requests
from typing import Dict, List, Optional

def get_zhipuai_response(question: str) -> Dict:
    """
    调用智谱AI API获取联网搜索回答

    Args:
        question: 用户问题

    Returns:
        API响应的JSON数据
    """
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    # API端点
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 请求体
    payload = {
        "model": "glm-4.6",  # 使用支持工具调用的模型
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ],
        # 启用联网搜索工具
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro_bing",  # 使用Bing搜索引擎以获取可点击链接
                    "search_query": question,  # 搜索查询
                    "search_intent": False,  # 直接搜索，不做意图识别
                    "count": 10,  # 返回10条结果
                    "search_result": True  # 必须设置此参数才能获取来源信息
                }
            }
        ],
        "max_tokens": 3000,  # 设置足够的token长度以获取完整回答
        "temperature": 0.3,  # 较低的temperature以获得更准确的事实性回答
        "do_sample": True
    }

    # 发送请求
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    return response.json()

def extract_sources(response_data: Dict) -> List[Dict]:
    """
    从API响应中提取信息来源

    Args:
        response_data: API响应的JSON数据

    Returns:
        来源信息列表，每个来源包含title和link
    """
    sources = []

    # 从web_search字段中提取来源
    web_search_results = response_data.get("web_search", [])
    for source in web_search_results:
        title = source.get("title", "")
        link = source.get("link", "")

        # 只包含有有效链接的来源
        if title and link:
            sources.append({
                "title": title,
                "link": link
            })

    return sources

def print_answer_with_sources(question: str, response_data: Dict):
    """
    打印回答和来源信息

    Args:
        question: 用户问题
        response_data: API响应数据
    """
    # 提取回答内容
    answer = ""
    if "choices" in response_data and len(response_data["choices"]) > 0:
        message = response_data["choices"][0]["message"]
        answer = message.get("content", "")

    # 打印回答
    print("=" * 60)
    print(f"问题：{question}")
    print("=" * 60)
    print("\n回答：")
    print(answer)

    # 提取并打印来源
    sources = extract_sources(response_data)

    if sources:
        print("\n" + "=" * 60)
        print("信息来源：")
        print("=" * 60)

        for i, source in enumerate(sources, 1):
            print(f"{i}. {source['title']}")
            print(f"   链接：{source['link']}")
            print()
    else:
        print("\n" + "=" * 60)
        print("信息来源：")
        print("=" * 60)
        print("未获取到具体的来源信息")

def main():
    """主函数"""
    # 写死的问题
    question = "2026 年智谱 BigModel 发布了哪些新模型"

    try:
        print("正在调用智谱AI API进行联网搜索...")

        # 获取回答
        response_data = get_zhipuai_response(question)

        # 打印回答和来源
        print_answer_with_sources(question, response_data)

    except requests.exceptions.RequestException as e:
        print(f"API请求失败：{e}")
    except ValueError as e:
        print(f"错误：{e}")
    except Exception as e:
        print(f"发生未知错误：{e}")

if __name__ == "__main__":
    main()