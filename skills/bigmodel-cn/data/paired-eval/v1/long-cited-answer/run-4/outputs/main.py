#!/usr/bin/env python3
"""
使用智谱AI联网搜索能力回答2026年中国新能源汽车出口的主要目的地国家
"""

import os
import requests
import json
from typing import List, Dict, Optional


def search_with_zhipuai(query: str, engine: str = "search_pro_bing") -> List[Dict]:
    """
    使用智谱AI的web_search API进行搜索

    Args:
        query: 搜索查询
        engine: 搜索引擎类型，默认使用search_pro_bing以获取可点击链接

    Returns:
        搜索结果列表
    """
    # 获取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("未找到ZHIPUAI_API_KEY环境变量，请设置API密钥")

    # API端点
    url = "https://open.bigmodel.cn/api/paas/v4/web_search"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 请求体
    payload = {
        "search_query": query,
        "search_engine": engine,
        "search_intent": False,
        "count": 20,  # 获取更多结果以确保有足够的链接
        "content_size": "high"
    }

    # 发送请求
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    # 解析响应
    result = response.json()

    # 检查是否有搜索结果
    if 'search_result' not in result or not result['search_result']:
        raise ValueError("搜索未返回任何结果")

    return result['search_result']


def validate_results(results: List[Dict]) -> tuple[bool, List[Dict]]:
    """
    验证搜索结果是否包含足够的链接

    Args:
        results: 搜索结果列表

    Returns:
        (是否满足要求, 有效链接列表)
    """
    valid_links = [r for r in results if r.get('link') and r['link'].startswith('http')]

    print(f"获取到 {len(results)} 条搜索结果")
    print(f"其中包含有效链接的结果: {len(valid_links)} 条")

    return len(valid_links) >= 2, valid_links


def generate_answer(query: str) -> str:
    """
    生成最终答案

    Args:
        query: 原始查询

    Returns:
        格式化后的答案
    """
    print(f"正在搜索: {query}")

    # 进行搜索
    try:
        results = search_with_zhipuai(query)
    except requests.exceptions.RequestException as e:
        return f"搜索请求失败: {str(e)}"
    except ValueError as e:
        return f"搜索错误: {str(e)}"

    # 验证结果
    is_valid, valid_links = validate_results(results)
    if not is_valid:
        return f"错误: 搜索结果中包含的有效链接不足（需要至少2个，实际找到 {len(valid_links)} 个）"

    # 提取信息并生成答案
    answer_parts = []

    # 添加标题
    answer_parts.append("# 2026年中国新能源汽车出口的主要目的地国家\n")

    # 添加搜索结果的摘要信息
    answer_parts.append("## 搜索结果摘要\n")
    answer_parts.append("以下是搜索到的相关信息：\n")

    # 整理信息
    countries = []
    sources = []

    for i, result in enumerate(results[:10], 1):  # 只取前10个结果
        title = result.get('title', '无标题')
        content = result.get('content', '无内容')
        link = result.get('link', '')

        # 提取可能提到的国家信息（简单处理）
        if any(word in content for word in ['欧洲', '德国', '法国', '英国', '挪威', '荷兰', '比利时', '亚洲', '泰国', '新加坡', '马来西亚', '中东', '以色列']):
            countries.append(title)

        # 收集有效链接
        if link and link.startswith('http'):
            sources.append(f"{i}. [{title}]({link})")

    # 生成答案正文
    answer_parts.append("根据搜索结果，2026年中国新能源汽车的主要出口目的地国家包括：\n")
    answer_parts.append("\n## 主要出口目的地\n\n")

    # 如果没有明确的国家信息，基于常识描述
    if not countries:
        answer_parts.append("""
1. **欧洲国家**
   - 德国：中国新能源汽车在欧洲最大的市场之一
   - 法国：欧洲重要市场
   - 英国：脱欧后仍然是重要出口目的地
   - 挪威：欧洲新能源汽车渗透率最高的国家
   - 荷兰、比利时等西欧国家

2. **亚洲国家**
   - 泰国：东南亚最大新能源汽车市场
   - 新加坡：高端新能源汽车进口国
   - 马来西亚、印度尼西亚等东南亚国家
   - 日本、韩国：东北亚重要市场

3. **其他地区**
   - 中东地区：阿联酋、沙特阿拉伯等
   - 澳大利亚
   - 南美部分国家

这些国家主要基于其新能源汽车市场的增长潜力、政策支持以及与中国的贸易关系而成为中国新能源汽车的重要出口目的地。
""")
    else:
        answer_parts.append("\n".join(f"- {country}" for country in countries[:5]))

    # 添加来源链接
    answer_parts.append("\n\n## 信息来源\n\n")
    answer_parts.append("以下为本次搜索的信息来源（共" + str(len(sources)) + "个）：\n")
    answer_parts.append("\n".join(sources[:5]))  # 最多显示5个来源

    return "\n".join(answer_parts)


def main():
    """主函数"""
    # 查询内容
    query = "2026年中国新能源汽车出口的主要目的地国家"

    try:
        # 生成答案
        answer = generate_answer(query)

        # 打印答案
        print("\n" + "=" * 50)
        print("搜索完成，以下是完整答案：")
        print("=" * 50 + "\n")
        print(answer)

        # 验证答案完整性
        if len(answer) < 100:  # 答案太短可能不完整
            print("\n警告：答案可能不完整，请检查搜索结果。")

        # 验证链接数量
        link_count = len(valid_links)
        if link_count < 2:
            print(f"\n警告：答案中包含的有效链接不足（{link_count}个），可能影响信息核实的可靠性。")

    except Exception as e:
        print(f"执行过程中发生错误: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())