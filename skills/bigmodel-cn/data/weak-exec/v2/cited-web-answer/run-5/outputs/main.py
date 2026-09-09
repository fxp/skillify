#!/usr/bin/env python3
"""
联网问答小工具
调用智谱AI的联网搜索功能回答问题，并打印答案和实际参考的信息来源
"""

import os
import requests

def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # API 配置
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 定义问题
    question = "2026 年智谱 BigModel 发布了哪些新模型"

    # 构建请求 payload
    payload = {
        "model": "glm-5.3",
        "messages": [
            {"role": "user", "content": question}
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_query": question,
                    "search_engine": "search_pro_bing",  # 使用必应搜索引擎以获得可点击的链接
                    "search_result": True,  # 必须设置为 True 才会返回来源信息
                    "count": 10  # 获取 10 条搜索结果
                }
            }
        ],
        "tool_choice": "auto"
    }

    try:
        # 发送请求
        print("正在搜索并生成答案...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        data = response.json()

        # 获取回答内容
        if data.get("choices"):
            answer = data["choices"][0]["message"]["content"]
            print("\n=== 回答 ===")
            print(answer)
        else:
            print("错误：未获得回答")
            return

        # 获取并打印信息来源
        if data.get("web_search") and data["web_search"]:
            print("\n=== 信息来源 ===")
            for i, source in enumerate(data["web_search"], 1):
                title = source.get("title", "无标题")
                link = source.get("link", "")
                if link:  # 只打印有有效链接的来源
                    print(f"{i}. [{title}]({link})")
        else:
            print("\n=== 信息来源 ===")
            print("本次回答未引用具体的网络来源")

    except requests.exceptions.RequestException as e:
        print(f"请求错误：{e}")
    except Exception as e:
        print(f"发生错误：{e}")

if __name__ == "__main__":
    main()