#!/usr/bin/env python3
import os
import requests
import json

def get_web_answer(question):
    """
    使用智谱AI的联网搜索功能回答问题
    """
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

    # 构建请求体
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
                    "search_engine": "search_pro_bing",  # 使用Bing搜索引擎以获得可点击链接
                    "search_query": question,
                    "search_intent": False,  # 直接搜索，不做意图识别
                    "count": 10,  # 返回10条结果
                    "search_result": True  # 必须设置为True才会返回来源信息
                }
            }
        ],
        "tool_choice": "auto",  # 自动决定是否使用工具
        "max_tokens": 2000,
        "temperature": 0.3
    }

    try:
        # 发送请求
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 提取回答内容
        answer = result["choices"][0]["message"]["content"]

        # 提取来源信息
        sources = []
        if "web_search" in result and result["web_search"]:
            for search_result in result["web_search"]:
                # 检查link字段是否为空（根据文档，某些搜索引擎返回空链接）
                link = search_result.get("link", "")
                if link:
                    sources.append({
                        "title": search_result.get("title", "未知标题"),
                        "url": link
                    })

        # 打印答案
        print("回答：")
        print(answer)
        print("\n" + "="*50)

        # 打印来源信息
        if sources:
            print("信息来源：")
            for i, source in enumerate(sources, 1):
                print(f"{i}. {source['title']}")
                print(f"   URL: {source['url']}")
                print()
        else:
            print("警告：未能获取到可点击的信息来源")

    except requests.exceptions.RequestException as e:
        print(f"请求错误: {e}")
    except KeyError as e:
        print(f"响应格式错误，缺少字段: {e}")
        print(f"完整响应: {json.dumps(result, ensure_ascii=False, indent=2)}")

def main():
    """
    主函数
    """
    # 写死的问题
    question = "2026年智谱BigModel发布了哪些新模型"

    print("正在查询问题：", question)
    print("-" * 50)

    # 获取并打印答案
    get_web_answer(question)

if __name__ == "__main__":
    main()