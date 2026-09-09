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

    # API 配置
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 定义问题
    question = "2026 年智谱 BigModel 发布了哪些新模型"

    # 构建请求载荷
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
                    "search_result": True  # 必须设置为 True 才能获取来源信息
                }
            }
        ],
        "tool_choice": "auto"
    }

    try:
        # 发送请求
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        # 提取回答内容
        answer = data["choices"][0]["message"]["content"]
        print("回答：")
        print(answer)
        print("\n" + "="*50)

        # 提取并显示信息来源
        web_search_results = data.get("web_search", [])
        if web_search_results:
            print("信息来源：")
            for i, source in enumerate(web_search_results, 1):
                title = source.get("title", "无标题")
                link = source.get("link", "")
                media = source.get("media", "")
                publish_date = source.get("publish_date", "")

                print(f"\n{i}. {title}")
                if link:
                    print(f"   链接：{link}")
                if media:
                    print(f"   来源：{media}")
                if publish_date:
                    print(f"   发布时间：{publish_date}")
        else:
            print("未找到信息来源")

    except requests.exceptions.RequestException as e:
        print(f"请求失败：{e}")
    except KeyError as e:
        print(f"响应解析失败，缺少字段：{e}")
        print(f"完整响应：{json.dumps(data, indent=2, ensure_ascii=False)}")

if __name__ == "__main__":
    main()