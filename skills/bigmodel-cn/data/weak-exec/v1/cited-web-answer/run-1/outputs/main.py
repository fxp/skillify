#!/usr/bin/env python3
import os
import json
import requests

def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置 ZHIPUAI_API_KEY 环境变量")
        exit(1)

    # API 端点
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 问题
    question = "2026年智谱BigModel发布了哪些新模型"

    # 构建请求体
    payload = {
        "model": "glm-5.3",
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
                    "search_engine": "search_pro_bing",
                    "search_query": question,
                    "search_intent": False,
                    "count": 10,
                    "search_result": True  # 必须设置为 true 才能获取来源信息
                }
            }
        ],
        "tool_choice": "auto",
        "stream": False
    }

    try:
        # 发送请求
        print(f"正在查询：{question}")
        print("-" * 50)

        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 打印答案
        assistant_message = result["choices"][0]["message"]["content"]
        print("回答：")
        print(assistant_message)
        print("-" * 50)

        # 打印信息来源
        print("信息来源：")
        if "web_search" in result and result["web_search"]:
            sources = result["web_search"]
            for i, source in enumerate(sources, 1):
                title = source.get("title", "无标题")
                link = source.get("link", "")
                media = source.get("media", "")
                publish_date = source.get("publish_date", "")

                print(f"{i}. {title}")
                if link:
                    print(f"   链接：{link}")
                if media:
                    print(f"   来源：{media}")
                if publish_date:
                    print(f"   发布时间：{publish_date}")
                print()
        else:
            print("未获取到具体的来源信息")

    except requests.exceptions.RequestException as e:
        print(f"请求失败：{e}")
    except json.JSONDecodeError as e:
        print(f"解析响应失败：{e}")
    except KeyError as e:
        print(f"响应格式错误，缺少字段：{e}")
        print("完整响应：")
        print(json.dumps(result, indent=2, ensure_ascii=False) if 'result' in locals() else "无响应数据")

if __name__ == "__main__":
    main()