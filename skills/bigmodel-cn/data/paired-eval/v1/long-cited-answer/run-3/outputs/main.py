#!/usr/bin/env python3
"""
智谱AI联网搜索脚本
查询2026年中国新能源汽车出口的主要目的地国家
"""

import os
import requests
import json
import sys
from typing import List, Dict, Optional

def zhipu_web_search(query: str, search_engine: str = "search_pro_bing", count: int = 10) -> Dict:
    """
    调用智谱AI联网搜索API

    Args:
        query: 搜索查询
        search_engine: 搜索引擎，可选：search_pro_bing, search_pro_jina, search_pro_quark, search_pro_sogou
        count: 返回结果数量

    Returns:
        搜索结果字典
    """
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/web_search"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "search_query": query,
        "search_engine": search_engine,
        "search_intent": False,
        "count": count,
        "content_size": "high"
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"API请求失败: {e}")

def extract_links(search_results: List[Dict]) -> List[str]:
    """
    从搜索结果中提取有效的链接

    Args:
        search_results: 搜索结果列表

    Returns:
        有效链接列表
    """
    links = []
    for result in search_results:
        if result.get("link") and result["link"].startswith("http"):
            links.append(result["link"])
    return links

def format_answer(query: str, search_results: List[Dict], links: List[str]) -> str:
    """
    格式化答案，确保完整并包含链接

    Args:
        query: 搜索查询
        search_results: 搜索结果列表
        links: 来源链接列表

    Returns:
        格式化后的答案
    """
    answer = f"## {query}\n\n"

    if not search_results:
        answer += "未找到相关信息。\n"
    else:
        answer += "### 搜索结果：\n\n"
        for i, result in enumerate(search_results, 1):
            title = result.get("title", "无标题")
            content = result.get("content", "无内容")
            publish_date = result.get("publish_date", "无日期")

            answer += f"#### {i}. {title}\n"
            answer += f"**发布时间:** {publish_date}\n"
            answer += f"**摘要:** {content}\n"

            if result.get("link"):
                answer += f"**来源链接:** {result['link']}\n"

            answer += "\n"

    # 确保至少有2个有效链接
    if len(links) < 2:
        answer += "\n### ⚠️ 警告\n"
        answer += f"只找到 {len(links)} 个有效链接，不足2个。无法完成人工复核要求。\n"
    else:
        answer += "\n### 参考资料（至少2个可点击链接）：\n"
        for i, link in enumerate(links[:5], 1):  # 最多显示5个链接
            answer += f"{i}. {link}\n"

    return answer

def main():
    """主函数"""
    # 查询2026年中国新能源汽车出口的主要目的地国家
    query = "2026年中国新能源汽车出口的主要目的地国家有哪些"

    print(f"正在搜索: {query}")
    print("=" * 60)

    try:
        # 使用search_pro_bing搜索引擎，因为它能返回有效的链接
        result = zhipu_web_search(query, search_engine="search_pro_bing", count=10)

        # 提取搜索结果
        search_results = result.get("search_result", [])

        # 提取有效链接
        links = extract_links(search_results)

        # 格式化答案
        answer = format_answer(query, search_results, links)

        # 打印答案
        print(answer)

        # 验证答案完整性
        if not search_results:
            print("\n❌ 错误: 搜索结果为空", file=sys.stderr)
            sys.exit(1)

        if len(links) < 2:
            print("\n❌ 错误: 有效链接不足2个，无法满足人工复核要求", file=sys.stderr)
            sys.exit(1)

        print(f"\n✅ 成功获取 {len(search_results)} 条搜索结果和 {len(links)} 个有效链接")
        print("脚本执行完成！")

    except Exception as e:
        print(f"\n❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()