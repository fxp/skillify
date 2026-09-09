#!/usr/bin/env python3
import os
import requests
import json

def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # API 端点
    url = "https://open.bigmodel.cn/api/pas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 问题
    question = "2026 年智谱 BigModel 发布了哪些新模型"

    # 工具定义 - 使用联网搜索工具
    tools = [{
        "type": "web_search",
        "web_search": {
            "enable": True,
            "search_engine": "search_pro_bing",  # 使用必应搜索引擎以获取真实链接
            "search_query": question,
            "search_intent": False,
            "count": 10,
            "search_result": True,  # 必须设置这个才能获取来源信息
            "content_size": "high"
        }
    }]

    # 请求数据
    payload = {
        "model": "glm-5.3",
        "messages": [
            {
                "role": "user",
                "content": f"请回答以下问题：{question}\n\n请基于搜索结果给出详细回答，并在答案下方列出所有参考的信息来源，包含来源标题和可点击的URL。"
            }
        ],
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 2000
    }

    try:
        # 发送请求
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        data = response.json()

        # 获取模型回答
        answer = data["choices"][0]["message"]["content"]

        # 打印答案
        print("=== 回答 ===")
        print(answer)
        print()

        # 提取并打印来源信息
        if "web_search" in data and data["web_search"]:
            print("=== 参考信息来源 ===")
            sources = data["web_search"]
            if sources:
                for i, source in enumerate(sources, 1):
                    title = source.get("title", "无标题")
                    link = source.get("link", "")
                    media = source.get("media", "")
                    publish_date = source.get("publish_date", "")

                    print(f"{i}. [{title}]({link})")
                    if media:
                        print(f"   来源：{media}")
                    if publish_date:
                        print(f"   发布时间：{publish_date}")
                    print()
            else:
                print("未找到来源信息")
        else:
            print("=== 参考信息来源 ===")
            print("本次回答未使用联网搜索功能，因此没有具体的参考来源。")

    except requests.exceptions.RequestException as e:
        print(f"请求错误：{e}")
    except json.JSONDecodeError as e:
        print(f"JSON 解析错误：{e}")
    except KeyError as e:
        print(f"响应格式错误：缺少字段 {e}")
        print(f"完整响应：{json.dumps(data, ensure_ascii=False, indent=2)}")

if __name__ == "__main__":
    main()