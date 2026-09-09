#!/usr/bin/env python3
"""
联网问答小工具
使用智谱 GLM 模型进行联网搜索，回答关于 2026 年智谱 BigModel 发布的新模型的问题
"""

import os
import requests

def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # API 配置
    base_url = "https://open.bigmodel.cn/api/paas/v4"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 问题
    question = "2026 年智谱 BigModel 发布了哪些新模型"

    print(f"正在问：{question}")
    print("-" * 50)

    try:
        # 调用智谱 GLM 模型进行联网搜索问答
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={
                "model": "glm-4.6",  # 使用支持联网搜索的模型
                "max_tokens": 3000,  # 给足够长度以获取完整回答
                "messages": [
                    {
                        "role": "user",
                        "content": question
                    }
                ],
                # 启用联网搜索工具
                "tools": [
                    {
                        "type": "web_search",
                        "web_search": {
                            "enable": True,
                            "search_engine": "search_pro_bing",  # 使用 bing 搜索引擎以获取可点击的链接
                            "search_result": True  # 返回搜索结果
                        }
                    }
                ]
            },
            timeout=30
        )

        response.raise_for_status()
        result = response.json()

        # 提取回答内容
        answer = result["choices"][0]["message"]["content"]
        print("回答：")
        print(answer)

        # 打印信息来源
        print("\n" + "-" * 50)
        print("信息来源：")

        # 从响应中提取搜索结果
        web_search_results = result.get("web_search", [])
        if web_search_results:
            for i, source in enumerate(web_search_results, 1):
                title = source.get("title", f"来源 {i}")
                link = source.get("link", "")

                # 确保有链接才显示
                if link:
                    print(f"{i}. [{title}]({link})")
                else:
                    print(f"{i}. {title} (链接不可用)")
        else:
            print("未获取到具体的来源信息")

    except requests.exceptions.RequestException as e:
        print(f"请求失败：{e}")
    except KeyError as e:
        print(f"响应格式错误：缺少 {e}")
    except Exception as e:
        print(f"发生错误：{e}")

if __name__ == "__main__":
    main()