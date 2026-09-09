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
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 问题
    question = "2026 年智谱 BigModel 发布了哪些新模型"

    # 构建请求数据
    payload = {
        "model": "glm-5.3",  # 使用支持联网搜索的模型
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ],
        # 配置联网搜索工具
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro_bing",  # 使用 bing 搜索引擎以获取可点击的链接
                    "search_query": question,
                    "count": 10,
                    "search_result": True  # 必须设置为 true 才会返回来源信息
                }
            }
        ],
        "tool_choice": "auto",
        "stream": False
    }

    try:
        # 发送请求
        print("正在搜索并生成答案...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        data = response.json()

        # 获取答案
        answer = data["choices"][0]["message"]["content"]
        print("\n=== 答案 ===")
        print(answer)

        # 获取并显示信息来源
        if "web_search" in data and data["web_search"]:
            print("\n=== 信息来源 ===")
            sources = data["web_search"]
            for i, source in enumerate(sources, 1):
                # 确保链接不为空
                link = source.get("link", "")
                if link:
                    print(f"{i}. [{source.get('title', '无标题')}]({link})")
                else:
                    print(f"{i}. {source.get('title', '无标题')} - (链接不可用)")
        else:
            print("\n=== 信息来源 ===")
            print("本次回答未包含可用的信息来源链接")

    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {e}")
    except json.JSONDecodeError as e:
        print(f"JSON 解析错误: {e}")
    except KeyError as e:
        print(f"响应数据格式错误: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()