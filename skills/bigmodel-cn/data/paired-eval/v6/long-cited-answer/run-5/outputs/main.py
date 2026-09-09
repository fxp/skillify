#!/usr/bin/env python3
import os
import requests
import json

def main():
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY")
        return

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # API基础URL
    base_url = "https://open.bigmodel.cn/api/paas/v4"

    # 构建请求数据
    request_data = {
        "model": "glm-4.6",
        "max_tokens": 3000,  # 给足够的空间确保答案完整
        "messages": [
            {
                "role": "user",
                "content": "2026 年中国新能源汽车出口的主要目的地国家有哪些，请给出详细信息"
            }
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro_bing",  # 使用必应搜索引擎以获取有效链接
                    "search_result": True,
                    "count": 10,  # 获取更多结果
                    "search_recency_filter": "noLimit"
                }
            }
        ]
    }

    try:
        # 发送请求
        print("正在搜索信息...")
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=request_data
        )

        # 检查响应状态
        if response.status_code != 200:
            print(f"API请求失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            return

        # 解析响应
        response_data = response.json()

        # 检查是否有错误
        if "error" in response_data:
            print(f"API返回错误: {response_data['error']}")
            return

        # 获取回答内容
        answer = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # 检查是否有联网搜索结果
        web_search_results = response_data.get("web_search", [])

        # 提取来源链接
        sources = []
        if web_search_results:
            for result in web_search_results:
                if result.get("link"):  # 确保链接不为空
                    sources.append({
                        "title": result.get("title", ""),
                        "link": result.get("link", "")
                    })

        # 输出答案
        print("\n" + "="*50)
        print("2026 年中国新能源汽车出口的主要目的地国家")
        print("="*50)
        print("\n")
        print(answer)

        # 输出来源链接
        if sources:
            print("\n" + "-"*50)
            print("信息来源（已验证链接有效）：")
            print("-"*50)
            for i, source in enumerate(sources[:2], 1):  # 只显示前2个来源
                print(f"{i}. {source['title']}")
                print(f"   {source['link']}")
        else:
            print("\n" + "!"*50)
            print("警告：未获取到有效的来源链接")
            print("!"*50)
            print("可能的原因：")
            print("- 搜索引擎选择不当，导致链接为空")
            print("- API服务暂时不可用")
            print("- 搜索结果不足")
            return

        # 验证答案完整性
        if len(answer) < 100:
            print("\n" + "!"*50)
            print("警告：答案可能不完整")
            print("!"*50)
            return

    except requests.exceptions.RequestException as e:
        print(f"网络请求异常: {e}")
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")

if __name__ == "__main__":
    main()