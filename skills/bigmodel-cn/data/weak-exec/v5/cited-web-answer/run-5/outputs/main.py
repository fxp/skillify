#!/usr/bin/env python3
"""
联网问答小工具
使用智谱AI GLM模型进行联网搜索，回答"2026年智谱BigModel发布了哪些新模型"问题
"""

import os
import json
import requests
from typing import Dict, List, Optional

def get_api_key() -> str:
    """从环境变量获取API Key"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")
    return api_key

def create_chat_request(question: str) -> Dict:
    """创建聊天请求，启用web_search工具"""
    return {
        "model": "glm-5.3",
        "messages": [
            {"role": "user", "content": question}
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro_bing",
                    "search_result": True,
                    "count": 10,
                    "search_recency_filter": "noLimit"
                }
            }
        ],
        "max_tokens": 3000,
        "stream": False
    }

def make_api_call(api_key: str, request_data: Dict) -> Dict:
    """调用智谱AI API"""
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, json=request_data, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API调用失败: {e}")
        raise

def extract_sources(response_data: Dict) -> List[Dict]:
    """从响应中提取信息来源"""
    sources = []

    # 从web_search字段获取来源信息
    web_search_results = response_data.get("web_search", [])
    for result in web_search_results:
        if result.get("link"):  # 只保留有有效链接的结果
            sources.append({
                "title": result.get("title", ""),
                "link": result.get("link", ""),
                "content": result.get("content", "")[:200] + "..." if len(result.get("content", "")) > 200 else result.get("content", "")
            })

    # 如果没有从web_search获取到来源，尝试从choices中获取（虽然这种情况很少发生）
    if not sources:
        # 某些情况下，搜索结果可能包含在message.content中
        message = response_data.get("choices", [{}])[0].get("message", {})
        content = message.get("content", "")

        # 这里可以尝试从content中提取链接（虽然这不是最佳实践）
        # 但根据要求，我们应该使用API返回的真实来源
        pass

    return sources

def main():
    """主函数"""
    try:
        # 获取API Key
        api_key = get_api_key()

        # 设置问题
        question = "2026年智谱BigModel发布了哪些新模型"
        print(f"正在查询：{question}\n")

        # 创建请求
        request_data = create_chat_request(question)

        # 调用API
        print("正在联网搜索...")
        response_data = make_api_call(api_key, request_data)

        # 提取回答
        message = response_data.get("choices", [{}])[0].get("message", {})
        answer = message.get("content", "")

        # 提取信息来源
        sources = extract_sources(response_data)

        # 打印答案
        print("\n=== 回答 ===")
        print(answer)

        # 打印信息来源
        print("\n=== 信息来源 ===")
        if sources:
            print("本次回答参考的信息来源：")
            for i, source in enumerate(sources, 1):
                print(f"{i}. {source['title']}")
                print(f"   URL: {source['link']}")
                print(f"   内容摘要: {source['content']}")
                print()
        else:
            print("未找到可用的信息来源")

        # 打印使用统计
        usage = response_data.get("usage", {})
        if usage:
            print("\n=== 使用统计 ===")
            print(f"Prompt tokens: {usage.get('prompt_tokens', 0)}")
            print(f"Completion tokens: {usage.get('completion_tokens', 0)}")
            print(f"Total tokens: {usage.get('total_tokens', 0)}")

    except Exception as e:
        print(f"错误: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())