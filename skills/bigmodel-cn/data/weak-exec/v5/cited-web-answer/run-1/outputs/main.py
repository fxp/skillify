#!/usr/bin/env python3
"""
智谱AI联网问答小工具
使用智谱GLM模型进行联网搜索，回答问题并显示信息来源
"""

import os
import requests

def main():
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # API端点
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 请求体
    payload = {
        "model": "glm-5.3",  # 使用GLM-5.3模型
        "messages": [
            {
                "role": "user",
                "content": "2026 年智谱 BigModel 发布了哪些新模型"
            }
        ],
        # 配置联网搜索工具
        "tools": [{
            "type": "web_search",
            "web_search": {
                "enable": True,
                "search_engine": "search_pro_bing",  # 使用bing搜索引擎以获取真实链接
                "search_query": "2026年智谱BigModel新模型",  # 搜索查询
                "search_result": True,  # 必须设置为True才能获取来源信息
                "count": 10  # 返回结果数量
            }
        }],
        "max_tokens": 3000  # 足够的输出长度
    }

    try:
        # 发送请求
        print("正在搜索相关信息...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()

        # 提取模型回答
        answer = data["choices"][0]["message"]["content"]
        print("\n=== 回答 ===")
        print(answer)

        # 提取并显示信息来源
        web_search_results = data.get("web_search", [])
        if web_search_results:
            print("\n=== 信息来源 ===")
            for i, source in enumerate(web_search_results, 1):
                title = source.get("title", "无标题")
                link = source.get("link", "")
                media = source.get("media", "")
                publish_date = source.get("publish_date", "")

                # 构建来源信息
                source_info = f"{i}. [{title}]"
                if media:
                    source_info += f" - {media}"
                if publish_date:
                    source_info += f" ({publish_date})"
                if link:
                    source_info += f"\n   链接：{link}"
                else:
                    source_info += "\n   链接：暂无链接"

                print(source_info)
                print()
        else:
            print("\n=== 信息来源 ===")
            print("未找到具体信息来源")

    except requests.exceptions.RequestException as e:
        print(f"请求失败：{e}")
    except KeyError as e:
        print(f"解析响应失败，缺少字段：{e}")
        print("完整响应：")
        print(response.text if 'response' in locals() else "无响应数据")

if __name__ == "__main__":
    main()