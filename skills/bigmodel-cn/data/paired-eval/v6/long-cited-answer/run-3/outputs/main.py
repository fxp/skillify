#!/usr/bin/env python3
"""
智谱AI联网搜索示例
查询2026年中国新能源汽车出口的主要目的地国家
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

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Base URL
    base_url = "https://open.bigmodel.cn/api/paas/v4"

    print("正在搜索2026年中国新能源汽车出口的主要目的地国家...")

    # 使用联网搜索工具
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={
                "model": "glm-4.6",  # 使用支持联网搜索的模型
                "max_tokens": 4000,   # 设置足够的长度以避免截断
                "messages": [
                    {
                        "role": "user",
                        "content": "2026年中国新能源汽车出口的主要目的地国家有哪些？请提供详细且完整的信息，包括具体的出口数据或市场份额。"
                    }
                ],
                "tools": [
                    {
                        "type": "web_search",
                        "web_search": {
                            "enable": True,
                            "search_engine": "search_pro_bing",  # 使用能返回真实链接的搜索引擎
                            "search_result": True,
                            "count": 10,  # 获取足够的结果
                            "search_recency_filter": "oneYear"  # 过去一年内的信息
                        }
                    }
                ]
            }
        )

        response.raise_for_status()
        result = response.json()

        # 提取回答内容
        answer = result["choices"][0]["message"]["content"]

        # 检查是否有联网搜索结果
        web_search_results = result.get("web_search", [])

        # 提取可用的链接
        source_links = []
        for search_result in web_search_results:
            link = search_result.get("link")
            title = search_result.get("title", "")
            if link and link.strip():
                source_links.append((title, link))

        # 验证结果
        if not answer or len(answer.strip()) < 100:
            print("错误：获取的答案不完整或过短")
            return

        if len(source_links) < 2:
            print("错误：未能获取到至少2条可点击的来源链接")
            print(f"实际获取到的链接数量: {len(source_links)}")
            if source_links:
                print("已获取的链接:")
                for title, link in source_links:
                    print(f"- {title}: {link}")
            return

        # 输出结果
        print("\n" + "="*60)
        print("2026年中国新能源汽车出口的主要目的地国家")
        print("="*60)
        print(f"\n{answer}\n")

        print("信息来源：")
        for i, (title, link) in enumerate(source_links[:5], 1):  # 显示前5个来源
            print(f"{i}. [{title}]({link})")

        print(f"\n共找到 {len(source_links)} 个信息来源，以上显示了前5个。")

    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {e}")
    except KeyError as e:
        print(f"响应格式错误: {e}")
        print(f"完整响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()