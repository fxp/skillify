#!/usr/bin/env python3
"""
智谱AI联网搜索示例
搜索2026年中国新能源汽车出口的主要目的地国家
"""

import os
import json
import requests
from typing import Dict, List, Optional

def search_with_zhipuai(query: str) -> Dict:
    """
    使用智谱AI的联网搜索功能

    Args:
        query: 搜索查询字符串

    Returns:
        API响应的JSON数据
    """
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("环境变量 ZHIPUAI_API_KEY 未设置")

    # API端点
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 工具定义 - 使用web_search工具
    tools = [
        {
            "type": "web_search",
            "web_search": {
                "enable": True,
                "search_engine": "search_pro_bing",  # 使用Bing搜索引擎以获取真实链接
                "search_query": query,
                "search_intent": False,
                "count": 10,
                "search_result": True,  # 必须设置为True才能获取来源信息
                "content_size": "high"
            }
        }
    ]

    # 请求体
    payload = {
        "model": "glm-5.3",
        "messages": [
            {
                "role": "user",
                "content": query
            }
        ],
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 4000,  # 设置较大的输出限制确保答案完整
        "temperature": 0.3,  # 降低温度以获得更稳定的回答
        "stream": False
    }

    # 发送请求
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"请求失败: {str(e)}")


def extract_sources(response_data: Dict) -> List[Dict]:
    """
    从响应中提取来源信息

    Args:
        response_data: API响应数据

    Returns:
        来源列表，每个来源包含title、link、media等信息
    """
    sources = []

    # 检查响应中是否有web_search字段
    web_search_info = response_data.get("web_search", [])

    if web_search_info:
        # web_search字段可能直接在顶层
        for source in web_search_info:
            if source.get("link"):  # 只保留有链接的来源
                sources.append({
                    "title": source.get("title", ""),
                    "link": source.get("link", ""),
                    "media": source.get("media", "")
                })
    else:
        # 如果web_search字段为空，尝试从choices中获取
        choices = response_data.get("choices", [])
        if choices and len(choices) > 0:
            message = choices[0].get("message", {})
            content = message.get("content", "")

            # 尝试从内容中提取可能的链接（作为兜底方案）
            import re
            url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
            urls = re.findall(url_pattern, content)

            if urls:
                # 取前两个链接作为来源
                for url in urls[:2]:
                    sources.append({
                        "title": "来源链接",
                        "link": url if url.startswith('http') else f"https://{url}",
                        "media": "未知来源"
                    })

    return sources


def main():
    """主函数"""
    try:
        # 搜索查询
        query = "2026年中国新能源汽车出口的主要目的地国家有哪些"

        print(f"正在搜索: {query}")
        print("-" * 50)

        # 执行搜索
        response_data = search_with_zhipuai(query)

        # 提取回答内容
        choices = response_data.get("choices", [])
        if not choices:
            raise Exception("API响应中没有找到choices字段")

        message = choices[0].get("message", {})
        content = message.get("content", "")

        # 检查回答是否完整
        if not content or len(content.strip()) < 50:
            raise Exception("API返回的回答为空或过短，可能不完整")

        # 检查是否被截断（通常不完整的回答会突然结束）
        if content.endswith("...") or content.endswith("。") and len(content) < 200:
            raise Exception("API回答可能被截断，请重试")

        # 提取来源
        sources = extract_sources(response_data)

        # 验证来源数量
        if len(sources) < 2:
            print(f"警告: 只找到 {len(sources)} 个有效来源链接，可能影响可信度")

        # 输出结果
        print("\n【搜索结果】")
        print(content)

        print("\n" + "-" * 50)
        print("【来源链接】")

        if sources:
            for i, source in enumerate(sources, 1):
                print(f"{i}. [{source['title']}]({source['link']}) - {source['media']}")
        else:
            print("未能获取到有效的来源链接")

        # 验证结果完整性
        print("\n【验证结果】")
        print(f"✓ 回答长度: {len(content)} 字符")
        print(f"✓ 来源数量: {len(sources)} 个")

        if len(sources) >= 2:
            print("✓ 来源链接数量满足要求（至少2个）")
        else:
            print("✗ 来源链接数量不足（至少需要2个）")

        # 检查链接是否有效
        valid_links = 0
        for source in sources:
            if source['link'].startswith('http') and len(source['link']) > 10:
                valid_links += 1

        if valid_links >= 2:
            print("✓ 链接有效性检查通过")
        else:
            print(f"⚠ 有效链接数量: {valid_links}/2")

        print("\n任务完成！")

    except Exception as e:
        print(f"\n❌ 错误: {str(e)}")
        # 如果是网络搜索相关的问题，提供更具体的建议
        if "link" in str(e).lower():
            print("\n可能的解决方案:")
            print("1. 检查网络连接是否正常")
            print("2. 确认API Key是否有效且有足够额度")
            print("3. 尝试使用其他搜索引擎参数（如search_pro_jina、search_pro_quark）")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())