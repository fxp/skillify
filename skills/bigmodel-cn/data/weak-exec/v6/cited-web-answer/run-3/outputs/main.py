#!/usr/bin/env python3
"""
联网问答小工具
使用智谱 AI 的联网搜索能力回答问题，并显示信息来源
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

    # API 配置
    base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 问题
    question = "2026 年智谱 BigModel 发布了哪些新模型"

    # 构建请求
    payload = {
        "model": "glm-4.6",
        "max_tokens": 3000,  # 长回答给够，否则截断
        "messages": [
            {"role": "user", "content": question}
        ],
        "tools": [{
            "type": "web_search",
            "web_search": {
                "enable": True,
                "search_engine": "search_pro_bing",  # 使用 bing 搜索引擎以确保返回可点击链接
                "search_result": True  # 必须设为 True 才会返回来源数组
            }
        }]
    }

    try:
        # 发送请求
        response = requests.post(base_url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()

        # 打印答案
        answer = result["choices"][0]["message"]["content"]
        print(answer)
        print("\n" + "="*50)

        # 打印信息来源
        web_search_results = result.get("web_search", [])
        if web_search_results:
            print("信息来源：")
            for source in web_search_results:
                title = source.get("title", "无标题")
                link = source.get("link", "")
                if link:  # 只显示有链接的来源
                    print(f"- {title}: {link}")
                else:
                    print(f"- {title}: [链接不可用]")
        else:
            print("未获取到信息来源")

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
    except json.JSONDecodeError as e:
        print(f"解析响应失败: {e}")
    except KeyError as e:
        print(f"响应格式错误，缺少字段: {e}")
        print("完整响应:", json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()