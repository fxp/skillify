#!/usr/bin/env python3
"""
联网问答小工具
使用智谱 GLM 模型的联网搜索功能回答问题，并显示信息来源
"""

import os
import requests
import json
from typing import List, Dict, Any

def search_with_web_search(question: str) -> tuple[str, List[Dict[str, Any]]]:
    """
    使用智谱 AI 的联网搜索功能回答问题

    Args:
        question: 用户问题

    Returns:
        tuple: (回答内容, 来源信息列表)
    """
    # API 配置
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    # API 端点
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 请求数据
    payload = {
        "model": "glm-5.3",  # 使用支持工具调用的旗舰模型
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "search_engine": "search_pro_bing",  # 使用必应搜索引擎以获取真实链接
                    "search_result": True,  # 必须显式设置才能获取来源列表
                    "count": 10  # 返回结果数量
                }
            }
        ],
        "search_result": True,  # 在响应中包含搜索结果
        "stream": False
    }

    # 发送请求
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()

        # 提取回答内容
        answer = result["choices"][0]["message"]["content"]

        # 提取来源信息
        sources = []
        if "web_search" in result and result["web_search"]:
            for search_result in result["web_search"]:
                source = {
                    "title": search_result.get("title", ""),
                    "url": search_result.get("link", "")
                }
                sources.append(source)

        return answer, sources

    except requests.exceptions.RequestException as e:
        raise Exception(f"API 请求失败: {e}")
    except KeyError as e:
        raise Exception(f"API 响应格式错误: {e}")


def format_sources(sources: List[Dict[str, Any]]) -> str:
    """
    格式化来源信息

    Args:
        sources: 来源信息列表

    Returns:
        str: 格式化后的来源文本
    """
    if not sources:
        return "未找到具体来源信息"

    formatted_lines = ["\n\n信息来源:"]
    for i, source in enumerate(sources, 1):
        title = source.get("title", "无标题")
        url = source.get("url", "")

        if url:
            formatted_lines.append(f"{i}. [{title}]({url})")
        else:
            formatted_lines.append(f"{i}. {title}（链接不可用）")

    return "\n".join(formatted_lines)


def main():
    """主函数"""
    # 写死的问题
    question = "2026 年智谱 BigModel 发布了哪些新模型"

    print(f"正在提问: {question}")
    print("=" * 50)

    try:
        # 调用联网搜索
        answer, sources = search_with_web_search(question)

        # 打印回答
        print(answer)

        # 打印来源
        print(format_sources(sources))

    except Exception as e:
        print(f"错误: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())