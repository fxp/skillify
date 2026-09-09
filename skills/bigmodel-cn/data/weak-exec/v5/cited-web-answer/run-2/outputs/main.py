#!/usr/bin/env python3
"""
联网问答小工具
使用智谱AI的联网搜索功能回答"2026 年智谱 BigModel 发布了哪些新模型"
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
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 请求数据
    payload = {
        "model": "glm-5.3",  # 使用旗舰模型，支持联网搜索
        "max_tokens": 3000,  # 长回答要给够，否则被截断
        "messages": [
            {
                "role": "user",
                "content": "2026 年智谱 BigModel 发布了哪些新模型"
            }
        ],
        "tools": [{
            "type": "web_search",
            "web_search": {
                "enable": True,
                "search_engine": "search_pro_bing",  # 使用 bing 以确保能拿到可点击的链接
                "search_result": True  # 必须设置，否则来源数组不出现
            }
        }]
    }

    try:
        # 发送请求
        print("正在搜索智谱 BigModel 2026 年发布的新模型...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()

        # 打印回答
        answer = data["choices"][0]["message"]["content"]
        print("\n回答：")
        print(answer)

        # 打印信息来源
        print("\n信息来源：")
        web_search_results = data.get("web_search", [])
        if web_search_results:
            for source in web_search_results:
                title = source.get("title", "未知标题")
                link = source.get("link", "")
                if link:  # 只显示有有效链接的来源
                    print(f"- {title}")
                    print(f"  {link}")
                else:
                    print(f"- {title} (链接不可用)")
        else:
            print("未获取到来源信息")

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
    except KeyError as e:
        print(f"响应格式错误: {e}")
        print(f"完整响应: {json.dumps(data, indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()