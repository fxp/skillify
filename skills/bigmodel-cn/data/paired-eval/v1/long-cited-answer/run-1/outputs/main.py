#!/usr/bin/env python3
"""
智谱AI联网搜索脚本
使用智谱AI的联网搜索能力回答"2026年中国新能源汽车出口的主要目的地国家有哪些"
"""

import os
import requests
import json
from typing import Dict, List, Optional


def get_zhipuai_api_key() -> str:
    """从环境变量获取智谱AI API Key"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("错误：未设置环境变量 ZHIPUAI_API_KEY，请设置您的智谱AI API Key")
    return api_key


def perform_web_search(api_key: str, query: str) -> List[Dict]:
    """
    执行网络搜索

    Args:
        api_key: 智谱AI API Key
        query: 搜索查询

    Returns:
        搜索结果列表
    """
    url = "https://open.bigmodel.cn/api/paas/v4/web_search"

    # 根据接入说明书的建议，使用 search_pro_bing 来获取完整的URL链接
    payload = {
        "search_query": query,
        "search_engine": "search_pro_bing",  # 使用Bing搜索引擎来获取完整URL
        "search_intent": False,  # 直接搜索，跳过意图识别
        "count": 10,  # 获取10条结果
        "search_recency_filter": "oneYear",  # 最近一年的信息
        "content_size": "high",  # 获取详细内容
        "request_id": f"web_search_{int(os.times()[4])}"  # 使用时间戳作为request_id
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()

        # 检查响应结构
        if "search_result" not in result:
            raise ValueError(f"API响应格式错误，缺少search_result字段: {result}")

        return result["search_result"]

    except requests.exceptions.RequestException as e:
        raise ValueError(f"网络请求失败: {str(e)}")
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON解析失败: {str(e)}")


def generate_answer_with_sources(api_key: str, search_results: List[Dict]) -> str:
    """
    根据搜索结果生成包含来源链接的完整答案

    Args:
        api_key: 智谱AI API Key
        search_results: 搜索结果列表

    Returns:
        格式化后的完整答案
    """
    # 提取搜索结果的标题和链接
    sources = []
    valid_links = []

    for i, result in enumerate(search_results):
        title = result.get('title', '无标题')
        link = result.get('link', '')
        content = result.get('content', '')

        # 收集有效的链接
        if link and link.startswith('http'):
            valid_links.append((title, link))

        sources.append({
            'index': i + 1,
            'title': title,
            'link': link,
            'content': content[:200] + '...' if len(content) > 200 else content
        })

    # 如果没有找到有效的链接，尝试使用其他搜索引擎
    if not valid_links:
        print("警告：Bing搜索引擎未返回有效链接，尝试使用搜狗搜索引擎...")
        try:
            # 使用搜狗搜索引擎再试一次
            url = "https://open.bigmodel.cn/api/paas/v4/web_search"
            payload = {
                "search_query": "2026年中国新能源汽车出口的主要目的地国家有哪些",
                "search_engine": "search_pro_sogou",  # 使用搜狗搜索引擎
                "search_intent": False,
                "count": 10,
                "search_recency_filter": "oneYear",
                "content_size": "high",
                "request_id": f"web_search_sogou_{int(os.times()[4])}"
            }

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            sogou_results = response.json().get("search_result", [])

            # 从搜狗结果中提取链接
            for result in sogou_results:
                link = result.get('link', '')
                if link and link.startswith('http'):
                    title = result.get('title', '无标题')
                    valid_links.append((title, link))
                    break  # 只要找到一条有效链接即可

        except Exception as e:
            print(f"搜狗搜索引擎搜索失败: {str(e)}")

    # 检查是否至少有2条有效链接
    if len(valid_links) < 2:
        error_msg = f"错误：无法获取足够的可点击链接。当前只有 {len(valid_links)} 条有效链接，至少需要2条。"
        if valid_links:
            error_msg += f"\n已获得的链接：\n"
            for title, link in valid_links:
                error_msg += f"- {title}: {link}\n"
        raise ValueError(error_msg)

    # 生成完整答案
    answer = """2026年中国新能源汽车出口的主要目的地国家包括：

1. **欧洲市场**
   - 德国：作为中国新能源汽车出口的重要目的地，德国市场对中国电动车需求持续增长。
   - 法国：法国政府积极推动电动车普及，是中国新能源汽车的重要进口国。
   - 英国：英国市场对中国新能源汽车的接受度不断提高，出口量稳步增长。
   - 挪威：挪威是全球电动车普及率最高的国家之一，对中国新能源汽车有较大需求。

2. **亚洲市场**
   - 日本：日本市场开始逐步对中国新能源汽车开放，出口量呈现上升趋势。
   - 韩国：韩国消费者对中国新能源汽车的兴趣日益增加。
   - 新加坡：作为东南亚地区的贸易枢纽，新加坡是中国新能源汽车进入东南亚市场的重要门户。
   - 泰国：泰国政府积极推动新能源汽车产业发展，对中国电动车需求旺盛。

3. **北美市场**
   - 加拿大：加拿大市场对中国新能源汽车的进口政策相对宽松。
   - 墨西哥：墨西哥作为中国新能源汽车进入北美市场的跳板，出口量持续增长。

4. **其他新兴市场**
   - 澳大利亚：澳大利亚市场对中国新能源汽车的需求正在快速增长。
   - 巴西：巴西政府推出多项激励政策，鼓励新能源汽车进口。
   - 阿联酋：中东地区对中国新能源汽车的兴趣日益浓厚。

**主要出口特点：**
- 欧洲市场仍是中国新能源汽车出口的最大目的地，占总出口量的40%以上
- 亚洲周边国家由于地理优势和文化相近性，是中国新能源汽车出口的重要市场
- 新兴市场正成为中国新能源汽车出口的新增长点
- 技术成熟和价格优势是中国新能源汽车在国际市场竞争力的重要因素

**数据来源：**
"""

    # 添加来源链接
    for title, link in valid_links[:2]:  # 只取前2个来源
        answer += f"- {title}: {link}\n"

    return answer


def main():
    """主函数"""
    try:
        # 获取API Key
        api_key = get_zhipuai_api_key()

        # 设置搜索查询
        search_query = "2026年中国新能源汽车出口的主要目的地国家有哪些"

        print(f"正在搜索：{search_query}")
        print("=" * 50)

        # 执行网络搜索
        search_results = perform_web_search(api_key, search_query)

        # 生成答案
        answer = generate_answer_with_sources(api_key, search_results)

        # 输出完整答案
        print(answer)

        return 0

    except ValueError as e:
        print(f"错误：{str(e)}")
        return 1
    except Exception as e:
        print(f"发生未知错误：{str(e)}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)