#!/usr/bin/env python3
import os
import json
import requests
import sys

def main():
    """使用智谱AI的联网搜索能力回答中国新能源汽车出口目的地国家的问题"""

    # 检查API Key是否存在
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        sys.exit(1)

    # 构建请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # API基础URL
    base_url = "https://open.bigmodel.cn/api/paas/v4"

    # 构建请求数据
    request_data = {
        "model": "glm-4.6",
        "max_tokens": 4000,  # 设置足够的token以确保答案完整
        "messages": [
            {
                "role": "user",
                "content": "2026年中国新能源汽车出口的主要目的地国家有哪些？请提供详细的信息，包括出口量、市场份额等内容。"
            }
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro_bing",  # 使用Bing搜索引擎以获得有效链接
                    "search_query": "2026年中国新能源汽车出口主要目的地国家",
                    "search_intent": False,
                    "count": 10,
                    "search_result": True  # 必须设置为True才能在响应中获得来源信息
                }
            }
        ],
        "stream": False
    }

    try:
        # 发送请求
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=request_data
        )
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 检查是否有响应内容
        if "choices" not in result or len(result["choices"]) == 0:
            print("错误：API返回的响应格式不正确", file=sys.stderr)
            sys.exit(1)

        # 提取回答内容
        answer = result["choices"][0]["message"]["content"]

        # 检查是否有web_search结果（来源链接）
        web_search_results = result.get("web_search", [])
        valid_links = []

        # 收集有效的链接（非空字符串）
        for search_result in web_search_results:
            link = search_result.get("link", "")
            if link and link.startswith("http"):
                valid_links.append(link)

        # 验证答案是否完整
        if not answer or len(answer.strip()) < 50:
            print("错误：返回的答案不完整或过短", file=sys.stderr)
            sys.exit(1)

        # 验证是否有足够的来源链接
        if len(valid_links) < 2:
            print("错误：未能获取到足够的可点击来源链接（需要至少2条）", file=sys.stderr)
            print(f"实际获取到的有效链接数量：{len(valid_links)}", file=sys.stderr)
            if valid_links:
                print("已获取的链接：", ", ".join(valid_links), file=sys.stderr)
            sys.exit(1)

        # 打印完整答案
        print("=== 2026年中国新能源汽车出口的主要目的地国家 ===")
        print("\n" + answer)
        print("\n=== 来源链接 ===")
        for i, link in enumerate(valid_links, 1):
            print(f"{i}. {link}")

        # 打印成功信息
        print(f"\n✅ 答案完整，共 {len(valid_links)} 个有效来源链接")

    except requests.exceptions.RequestException as e:
        print(f"错误：API请求失败 - {str(e)}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"错误：解析API响应失败 - {str(e)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误：程序执行失败 - {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()