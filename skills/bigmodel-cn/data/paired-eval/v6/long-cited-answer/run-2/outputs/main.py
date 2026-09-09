#!/usr/bin/env python3
import os
import json
import requests

def main():
    """
    使用智谱AI的联网搜索能力回答"2026年中国新能源汽车出口的主要目的地国家有哪些"
    要求：
    1. 答案要完整，不能被截断
    2. 必须附上至少2条可点击的来源链接
    3. 如果拿不到链接或答案不完整要明确报错
    """

    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：环境变量 ZHIPUAI_API_KEY 未设置")
        exit(1)

    # 设置请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # API基础URL
    base_url = "https://open.bigmodel.cn/api/paas/v4"

    # 构造请求
    request_data = {
        "model": "glm-4.6",
        "max_tokens": 4000,  # 设置较大的token数，确保答案不被截断
        "messages": [
            {
                "role": "user",
                "content": "2026年中国新能源汽车出口的主要目的地国家有哪些？请提供完整的答案，包括具体的国家名称、出口量或市场份额信息，并说明出口趋势。"
            }
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro_bing",  # 使用Bing搜索引擎来获取可点击的链接
                    "search_result": True  # 确保返回搜索结果
                }
            }
        ]
    }

    try:
        # 发送请求
        print("正在搜索相关信息...")
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=request_data
        )
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 提取回答内容
        answer = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not answer:
            print("错误：未能获取到回答内容")
            exit(1)

        # 提取搜索结果中的来源链接
        search_results = result.get("web_search", [])
        valid_links = []

        if not search_results:
            print("错误：未能获取到搜索结果，可能是搜索引擎配置问题")
            exit(1)

        # 收集有效的链接（link不为空）
        for search_result in search_results:
            link = search_result.get("link", "")
            if link and link.startswith("http"):
                valid_links.append({
                    "title": search_result.get("title", ""),
                    "link": link
                })

        # 检查是否有足够的有效链接
        if len(valid_links) < 2:
            print(f"错误：只找到 {len(valid_links)} 条有效链接，至少需要2条")
            print("找到的链接：")
            for link in valid_links:
                print(f"- {link['title']}: {link['link']}")
            exit(1)

        # 输出完整答案
        print("\n" + "="*80)
        print("2026年中国新能源汽车出口的主要目的地国家有哪些？")
        print("="*80)
        print("\n" + answer)
        print("\n" + "-"*80)
        print("参考来源：")
        print("-"*80)

        # 输出来源链接
        for i, link_info in enumerate(valid_links[:5], 1):  # 最多显示5条来源
            print(f"{i}. [{link_info['title']}]({link_info['link']})")

        print(f"\n共找到 {len(valid_links)} 条来源链接，已显示前5条。")

    except requests.exceptions.RequestException as e:
        print(f"请求错误：{e}")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"JSON解析错误：{e}")
        exit(1)
    except Exception as e:
        print(f"未知错误：{e}")
        exit(1)

if __name__ == "__main__":
    main()