#!/usr/bin/env python3
import os
import requests

def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # API 基础 URL
    base_url = "https://open.bigmodel.cn/api/paas/v4"

    # 请求参数
    payload = {
        "model": "glm-5.3",
        "max_tokens": 3000,
        "messages": [
            {
                "role": "user",
                "content": "2026 年智谱 BigModel 发布了哪些新模型"
            }
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro_bing",
                    "search_result": True
                }
            }
        ]
    }

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        # 发送请求
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()

        # 打印模型回答
        if result.get("choices") and len(result["choices"]) > 0:
            answer = result["choices"][0]["message"]["content"]
            print("回答：")
            print(answer)
            print("\n" + "="*50 + "\n")

            # 打印信息来源
            web_search_results = result.get("web_search", [])
            if web_search_results:
                print("信息来源：")
                for i, source in enumerate(web_search_results, 1):
                    title = source.get("title", "无标题")
                    link = source.get("link", "")
                    if link:
                        print(f"{i}. {title}")
                        print(f"   URL: {link}")
                        print()
                    else:
                        print(f"{i}. {title} (链接不可用)")
                        print()
            else:
                print("未获取到具体信息来源")
        else:
            print("未能获取到回答")

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()