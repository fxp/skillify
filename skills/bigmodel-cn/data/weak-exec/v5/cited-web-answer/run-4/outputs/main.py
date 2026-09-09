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
        "Content-Type": "application/json",
    }

    # 问题
    question = "2026 年智谱 BigModel 发布了哪些新模型"

    # 请求体
    payload = {
        "model": "glm-5.3",  # 使用支持联网搜索的模型
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
                    "search_engine": "search_pro_bing",  # 使用 bing 搜索引擎以获取真实链接
                    "search_query": question,
                    "search_result": True,  # 必须设为 True 才会返回来源信息
                    "count": 10  # 获取 10 条搜索结果
                }
            }
        ],
        "max_tokens": 3000,  # 给足够的 token 用于生成完整回答
        "stream": False
    }

    try:
        # 发送请求
        print(f"正在提问: {question}")
        print("-" * 50)

        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        data = response.json()

        # 提取模型回答
        answer = data["choices"][0]["message"]["content"]
        print("回答:")
        print(answer)
        print("-" * 50)

        # 提取来源信息
        web_search_results = data.get("web_search", [])
        if web_search_results:
            print("信息来源:")
            for i, source in enumerate(web_search_results, 1):
                title = source.get("title", "无标题")
                link = source.get("link", "")
                media = source.get("media", "")
                publish_date = source.get("publish_date", "")

                print(f"{i}. [{title}]({link})")
                if media:
                    print(f"   媒体: {media}")
                if publish_date:
                    print(f"   发布时间: {publish_date}")
                print()
        else:
            print("未获取到来源信息")

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
    except KeyError as e:
        print(f"响应格式错误，缺少字段: {e}")
        print(f"完整响应: {json.dumps(data, indent=2, ensure_ascii=False)}")

if __name__ == "__main__":
    main()