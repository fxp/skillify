#!/usr/bin/env python3
"""
联网问答小工具
使用智谱AI的联网搜索功能回答问题，并在答案下方列出实际参考的信息来源
"""

import os
import requests
import json

def main():
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        exit(1)

    # API配置
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 问题
    question = "2026 年智谱 BigModel 发布了哪些新模型"

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
                    "enable": True,
                    "search_engine": "search_pro_bing",  # 使用带真实链接的搜索引擎
                    "search_query": question,
                    "search_intent": False,  # 跳过意图识别，直接搜索
                    "count": 10,  # 获取10条结果
                    "search_result": True  # 关键：必须设置为True才能获得web_search字段
                }
            }
        ],
        "tool_choice": "auto",  # 让模型自动决定是否使用工具
        "stream": False,
        "max_tokens": 2048
    }

    try:
        # 发送请求
        print(f"正在提问：{question}")
        print("-" * 50)

        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 获取回答内容
        answer = result["choices"][0]["message"]["content"]
        print("回答：")
        print(answer)
        print("\n" + "=" * 50)

        # 提取参考来源
        web_search_results = result.get("web_search", [])
        if web_search_results:
            print("参考信息来源：")
            for i, source in enumerate(web_search_results, 1):
                title = source.get("title", "无标题")
                link = source.get("link", "")
                media = source.get("media", "")
                publish_date = source.get("publish_date", "")

                print(f"\n[{i}] {title}")
                if link:
                    print(f"   链接：{link}")
                if media:
                    print(f"   来源：{media}")
                if publish_date:
                    print(f"   发布时间：{publish_date}")
                print("-" * 30)
        else:
            print("未找到具体的参考信息来源")

        # 打印token使用情况（可选）
        usage = result.get("usage", {})
        if usage:
            print(f"\nToken使用情况：")
            print(f"  提示Token：{usage.get('prompt_tokens', 0)}")
            print(f"  回复Token：{usage.get('completion_tokens', 0)}")
            print(f"  总Token：{usage.get('total_tokens', 0)}")

    except requests.exceptions.RequestException as e:
        print(f"请求错误：{e}")
    except json.JSONDecodeError as e:
        print(f"JSON解析错误：{e}")
    except KeyError as e:
        print(f"响应格式错误，缺少字段：{e}")
        print("完整响应：")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False) if 'response' in locals() else "无响应数据")

if __name__ == "__main__":
    main()