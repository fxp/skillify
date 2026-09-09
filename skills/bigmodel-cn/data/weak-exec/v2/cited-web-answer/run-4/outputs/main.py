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
                    "search_engine": "search_pro_bing",  # 使用 bing 搜索引擎以确保返回可点击链接
                    "search_query": question,
                    "search_intent": False,
                    "count": 10,
                    "search_result": True  # 必须设置为 True 才会返回来源信息
                }
            }
        ],
        "tool_choice": "auto"
    }

    try:
        # 发送请求
        print(f"正在查询：{question}")
        print("-" * 50)

        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        data = response.json()

        # 获取回答内容
        answer = data["choices"][0]["message"]["content"]
        print("回答：")
        print(answer)
        print("\n" + "-" * 50)

        # 获取并显示信息来源
        if "web_search" in data:
            web_results = data["web_search"]
            if web_results and len(web_results) > 0:
                print("信息来源：")
                for i, result in enumerate(web_results, 1):
                    title = result.get("title", "无标题")
                    link = result.get("link", "")
                    if link:  # 只显示有链接的来源
                        print(f"{i}. {title}")
                        print(f"   链接：{link}")
                        print()
            else:
                print("未获取到信息来源")
        else:
            print("本次回答未使用联网搜索功能")

    except requests.exceptions.RequestException as e:
        print(f"请求失败：{e}")
    except json.JSONDecodeError as e:
        print(f"响应解析失败：{e}")
    except KeyError as e:
        print(f"响应格式错误：缺少字段 {e}")
    except Exception as e:
        print(f"发生未知错误：{e}")

if __name__ == "__main__":
    main()