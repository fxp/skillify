#!/usr/bin/env python3
"""
智谱AI联网问答小工具
使用联网搜索功能回答"2026年智谱BigModel发布了哪些新模型"
"""

import os
import requests
import json

def ask_zhipu_with_web_search():
    """调用智谱AI联网搜索功能回答问题"""

    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # API endpoint
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 请求数据
    payload = {
        "model": "glm-5.3",
        "messages": [
            {
                "role": "user",
                "content": "2026年智谱BigModel发布了哪些新模型？"
            }
        ],
        # 联网搜索工具配置
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_query": "2026年智谱BigModel新模型发布",
                    "search_engine": "search_pro_bing",  # 使用Bing搜索引擎以获取可点击链接
                    "count": 10,
                    "search_recency_filter": "oneYear",
                    "content_size": "high",
                    "search_result": True  # 必须设置为True才能获取来源信息
                }
            }
        ]
    }

    try:
        # 发送请求
        print("正在调用智谱AI联网搜索...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        data = response.json()

        # 提取回答内容
        answer = data["choices"][0]["message"]["content"]

        # 打印回答
        print("\n" + "="*50)
        print("回答：")
        print("="*50)
        print(answer)

        # 提取并打印信息来源
        if "web_search" in data and data["web_search"]:
            print("\n" + "="*50)
            print("信息来源：")
            print("="*50)

            sources = data["web_search"]
            for i, source in enumerate(sources, 1):
                title = source.get("title", "无标题")
                link = source.get("link", "")
                media = source.get("media", "")
                publish_date = source.get("publish_date", "")

                print(f"\n{i}. {title}")
                if media:
                    print(f"   来源：{media}")
                if publish_date:
                    print(f"   发布时间：{publish_date}")
                if link:
                    print(f"   链接：{link}")
                else:
                    print("   链接：暂无可点击链接")
        else:
            print("\n" + "="*50)
            print("信息来源：")
            print("="*50)
            print("未获取到来源信息，可能需要调整搜索参数")

        # 打印token使用情况
        if "usage" in data:
            usage = data["usage"]
            print(f"\nToken使用情况：")
            print(f"  输入Token：{usage.get('prompt_tokens', 0)}")
            print(f"  输出Token：{usage.get('completion_tokens', 0)}")
            print(f"  总Token：{usage.get('total_tokens', 0)}")

    except requests.exceptions.RequestException as e:
        print(f"请求错误：{e}")
    except json.JSONDecodeError as e:
        print(f"JSON解析错误：{e}")
    except KeyError as e:
        print(f"响应格式错误：缺少必要字段 {e}")

if __name__ == "__main__":
    ask_zhipu_with_web_search()