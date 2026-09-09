#!/usr/bin/env python3
"""
联网问答小工具
使用智谱AI GLM模型进行联网搜索并回答问题
"""

import os
import requests
import json

def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 问答接口配置
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 写死的问题
    question = "2026 年智谱 BigModel 发布了哪些新模型"

    # 构建请求数据，启用联网搜索
    payload = {
        "model": "glm-5.3",  # 使用 GLM-5.3 模型
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
                    "search_query": question,
                    "search_engine": "search_pro_bing",  # 使用 bing 引擎以获取真实链接
                    "count": 10,
                    "search_result": True  # 必须设置为 True 才会返回来源信息
                }
            }
        ],
        "stream": False
    }

    try:
        # 发送请求
        print(f"正在提问: {question}")
        print("-" * 50)

        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 获取回答内容
        answer = result["choices"][0]["message"]["content"]
        print("回答:")
        print(answer)

        # 打印信息来源
        print("\n" + "-" * 50)
        print("信息来源:")

        # 检查是否有 web_search 结果
        if "web_search" in result and result["web_search"]:
            sources = result["web_search"]
            for i, source in enumerate(sources, 1):
                title = source.get("title", "无标题")
                link = source.get("link", "")
                media = source.get("media", "")
                publish_date = source.get("publish_date", "")

                print(f"\n[{i}] {title}")
                if link:
                    print(f"   链接: {link}")
                if media:
                    print(f"   来源: {media}")
                if publish_date:
                    print(f"   发布时间: {publish_date}")
        else:
            print("未获取到具体的来源信息")

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
    except json.JSONDecodeError as e:
        print(f"解析响应失败: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()