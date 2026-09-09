#!/usr/bin/env python3
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

    # 写死的问题
    question = "2026 年智谱 BigModel 发布了哪些新模型"

    print(f"正在提问：{question}")
    print("-" * 50)

    try:
        # 调用智谱 API 进行联网搜索问答
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={
                "model": "glm-4.6",  # 使用支持工具调用的模型
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
                            "search_engine": "search_pro_bing",  # 使用必应搜索引擎以获取可点击链接
                            "search_result": True
                        }
                    }
                ]
            },
            timeout=30
        )

        # 检查响应状态
        if response.status_code != 200:
            print(f"API 调用失败，状态码：{response.status_code}")
            print(f"响应内容：{response.text}")
            return

        # 解析响应
        result = response.json()

        # 打印模型回答
        if 'choices' in result and len(result['choices']) > 0:
            answer = result['choices'][0]['message']['content']
            print("回答：")
            print(answer)

        # 打印信息来源
        if 'web_search' in result and result['web_search']:
            print("\n信息来源：")
            for source in result['web_search']:
                title = source.get('title', '未知标题')
                link = source.get('link', '')
                if link:  # 只显示有有效链接的来源
                    print(f"- {title}")
                    print(f"  {link}")
                else:
                    print(f"- {title} (链接不可用)")
        else:
            print("\n未获取到搜索来源信息")

    except requests.exceptions.RequestException as e:
        print(f"请求异常：{e}")
    except Exception as e:
        print(f"发生错误：{e}")

if __name__ == "__main__":
    main()