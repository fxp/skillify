#!/usr/bin/env python3
"""
联网问答小工具
使用智谱AI的联网搜索功能回答"2026年智谱BigModel发布了哪些新模型"
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

    # API endpoint
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 定义工具 - 联网搜索
    tools = [{
        "type": "web_search",
        "web_search": {
            "enable": True,
            "search_engine": "search_pro_bing",  # 使用Bing搜索引擎获取可点击链接
            "search_query": "2026年智谱BigModel发布新模型",  # 搜索查询
            "search_intent": False,  # 直接搜索，不做意图识别
            "count": 10,  # 返回10条结果
            "search_result": True  # 必须设置此参数才能获取web_search字段
        }
    }]

    # 请求体
    payload = {
        "model": "glm-5.3",  # 使用支持联网搜索的模型
        "messages": [
            {
                "role": "user",
                "content": "2026年智谱BigModel发布了哪些新模型？请给出详细回答。"
            }
        ],
        "tools": tools,
        "tool_choice": "auto",  # 让模型决定是否使用工具
        "max_tokens": 2000  # 设置足够的输出长度
    }

    try:
        # 发送请求
        print("正在查询智谱AI官方信息...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        data = response.json()

        # 提取回答内容
        if data.get("choices") and len(data["choices"]) > 0:
            message = data["choices"][0]["message"]
            content = message.get("content", "")

            # 打印回答
            print("\n" + "="*50)
            print("回答：")
            print("="*50)
            print(content)

            # 提取并打印信息来源
            if data.get("web_search") and data["web_search"].get("search_result"):
                print("\n" + "="*50)
                print("信息来源：")
                print("="*50)

                search_results = data["web_search"]["search_result"]
                if search_results:
                    for i, result in enumerate(search_results, 1):
                        title = result.get("title", "无标题")
                        link = result.get("link", "")
                        media = result.get("media", "未知来源")
                        publish_date = result.get("publish_date", "")

                        print(f"\n{i}. {title}")
                        print(f"   来源：{media}")
                        if publish_date:
                            print(f"   发布时间：{publish_date}")
                        if link:
                            print(f"   链接：{link}")
                        else:
                            print(f"   链接：暂无可用链接")
                else:
                    print("未获取到搜索结果")
            else:
                print("\n" + "="*50)
                print("提示：")
                print("="*50)
                print("本次回答未获取到具体的来源链接。如需查看信息来源，")
                print("请确保使用支持返回链接的搜索引擎（如 search_pro_bing）。")
        else:
            print("错误：无法获取回答内容")

    except requests.exceptions.RequestException as e:
        print(f"请求错误：{e}")
    except json.JSONDecodeError as e:
        print(f"JSON解析错误：{e}")
    except Exception as e:
        print(f"发生错误：{e}")

if __name__ == "__main__":
    main()