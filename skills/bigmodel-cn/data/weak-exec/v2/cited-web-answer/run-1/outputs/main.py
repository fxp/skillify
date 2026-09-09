#!/usr/bin/env python3
"""
联网问答小工具
使用智谱AI的联网搜索功能回答"2026年智谱BigModel发布了哪些新模型"的问题
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

    # 构建请求
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 指定问题
    question = "2026年智谱BigModel发布了哪些新模型"

    # 构建请求体
    payload = {
        "model": "glm-5.3",  # 使用支持工具调用的模型
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "search_query": question,
                    "search_engine": "search_pro_bing",  # 使用Bing搜索引擎以获得可点击链接
                    "search_intent": False,
                    "count": 10,
                    "search_result": True  # 确保返回搜索结果列表
                }
            }
        ],
        "stream": False,
        "temperature": 0.3,
        "max_tokens": 2000
    }

    try:
        # 发送请求
        print("正在搜索相关信息...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        data = response.json()

        # 提取回答内容
        if 'choices' in data and len(data['choices']) > 0:
            message = data['choices'][0]['message']
            content = message.get('content', '没有获取到回答内容')

            # 打印回答
            print("\n" + "="*50)
            print("回答：")
            print("="*50)
            print(content)

            # 提取并打印信息来源
            print("\n" + "="*50)
            print("信息来源：")
            print("="*50)

            # 检查是否有搜索结果
            if 'web_search' in data and len(data['web_search']) > 0:
                sources = data['web_search']
                print(f"共找到 {len(sources)} 个信息来源：\n")

                for i, source in enumerate(sources, 1):
                    title = source.get('title', '无标题')
                    link = source.get('link', '')
                    snippet = source.get('snippet', '无摘要')

                    print(f"{i}. {title}")
                    if link:
                        print(f"   链接：{link}")
                    else:
                        print("   链接：暂无链接")
                    print(f"   摘要：{snippet}\n")
            else:
                print("未获取到具体的来源信息")

            # 打印token使用情况
            if 'usage' in data:
                usage = data['usage']
                print(f"\nToken使用情况：")
                print(f"输入 tokens: {usage.get('prompt_tokens', 0)}")
                print(f"输出 tokens: {usage.get('completion_tokens', 0)}")
                print(f"总计 tokens: {usage.get('total_tokens', 0)}")

        else:
            print("未获取到有效回答")

    except requests.exceptions.RequestException as e:
        print(f"请求失败：{e}")
    except json.JSONDecodeError as e:
        print(f"解析响应失败：{e}")
    except Exception as e:
        print(f"发生错误：{e}")

if __name__ == "__main__":
    main()