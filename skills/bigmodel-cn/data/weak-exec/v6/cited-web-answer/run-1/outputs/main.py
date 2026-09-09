#!/usr/bin/env python3
"""
联网问答小工具
调用智谱AI模型进行联网搜索回答，并显示信息来源
"""

import os
import requests

def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        exit(1)

    # API 配置
    base_url = "https://open.bigmodel.cn/api/paas/v4"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 提问
    question = "2026 年智谱 BigModel 发布了哪些新模型"

    # 构建请求
    payload = {
        "model": "glm-4.6",
        "max_tokens": 3000,
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
                    "search_result": True,
                    "count": 10
                }
            }
        ]
    }

    try:
        # 发送请求
        print(f"正在提问：{question}")
        print("-" * 50)

        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )

        # 检查响应状态
        response.raise_for_status()
        result = response.json()

        # 打印回答内容
        if 'choices' in result and len(result['choices']) > 0:
            message = result['choices'][0]['message']
            content = message.get('content', '没有获取到回答内容')
            print(content)
        else:
            print("没有获取到回答内容")

        # 打印信息来源
        print("\n" + "=" * 50)
        print("信息来源：")
        print("=" * 50)

        # 从响应中获取 web_search 结果
        web_search_results = result.get('web_search', [])
        if web_search_results:
            for i, source in enumerate(web_search_results, 1):
                title = source.get('title', f'来源 {i}')
                link = source.get('link', '')
                media = source.get('media', '')
                publish_date = source.get('publish_date', '')

                # 构建来源信息
                source_info = f"{i}. [{title}]"
                if media:
                    source_info += f" - {media}"
                if publish_date:
                    source_info += f" ({publish_date})"

                # 添加链接（如果存在）
                if link:
                    source_info += f"\n   链接：{link}"
                else:
                    source_info += "\n   链接：未提供"

                print(source_info)
                print()
        else:
            print("未获取到信息来源")

    except requests.exceptions.RequestException as e:
        print(f"请求失败：{e}")
    except Exception as e:
        print(f"发生错误：{e}")

if __name__ == "__main__":
    main()