#!/usr/bin/env python3
"""
使用智谱AI联网搜索功能查询2026年中国新能源汽车出口的主要目的地国家
"""

import os
import requests
import json

def search_with_zhipuai(query):
    """
    使用智谱AI的联网搜索功能进行搜索
    """
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("未找到环境变量 ZHIPUAI_API_KEY，请确保已设置 API Key")

    url = "https://open.bigmodel.cn/api/paas/v4/web_search"

    # 使用 search_pro_bing 以确保获取到可点击的来源链接
    payload = {
        "search_query": query,
        "search_engine": "search_pro_bing",  # 使用Bing搜索引擎以获取有效链接
        "search_intent": False,
        "count": 10,  # 获取更多结果确保答案完整
        "search_recency_filter": "noLimit",
        "content_size": "high"
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    print("正在搜索...")
    response = requests.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        error_msg = response.json().get('error', {}).get('message', '未知错误')
        raise Exception(f"API 调用失败: {response.status_code} - {error_msg}")

    return response.json()

def extract_search_results(search_result):
    """
    从搜索结果中提取关键信息
    """
    if not search_result.get('search_result'):
        raise ValueError("搜索结果为空或格式不正确")

    results = search_result['search_result']
    sources = []

    # 收集所有来源链接
    for item in results:
        if item.get('link'):
            sources.append({
                'title': item.get('title', ''),
                'link': item.get('link', ''),
                'content': item.get('content', '')[:200] + '...' if len(item.get('content', '')) > 200 else item.get('content', '')
            })

    # 如果没有获取到有效链接，尝试使用其他搜索引擎
    if not sources:
        print("警告: Bing搜索引擎未找到有效链接，尝试使用搜狗引擎...")
        return search_with_alternative_engine()

    return results, sources

def search_with_alternative_engine():
    """
    使用备用搜索引擎（搜狗）进行搜索
    """
    api_key = os.environ.get('ZHIPUAI_API_KEY')

    url = "https://open.bigmodel.cn/api/paas/v4/web_search"

    # 使用 search_pro_sogou 作为备选
    payload = {
        "search_query": "2026年中国新能源汽车出口的主要目的地国家",
        "search_engine": "search_pro_sogou",  # 使用搜狗搜索引擎
        "search_intent": False,
        "count": 10,
        "search_recency_filter": "noLimit",
        "content_size": "high"
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        raise Exception(f"备用搜索引擎调用失败: {response.status_code}")

    search_result = response.json()
    results = search_result.get('search_result', [])

    # 收集来源链接
    sources = []
    for item in results:
        if item.get('link'):
            sources.append({
                'title': item.get('title', ''),
                'link': item.get('link', ''),
                'content': item.get('content', '')[:200] + '...' if len(item.get('content', '')) > 200 else item.get('content', '')
            })

    if not sources:
        raise ValueError("所有搜索引擎都未找到有效链接，无法提供可核实的来源")

    return results, sources

def generate_answer(results, sources):
    """
    根据搜索结果生成完整答案
    """
    if not results:
        return "未能获取到相关信息。"

    # 整合搜索结果内容
    combined_content = "\n\n".join([f"{item.get('title', '')}\n{item.get('content', '')}" for item in results])

    # 构建提示词要求模型整理答案
    prompt = f"""
    请根据以下搜索结果，整理出2026年中国新能源汽车出口的主要目的地国家的完整信息。
    要求：
    1. 答案要完整，不能截断
    2. 列出所有主要目的地国家
    3. 如果包含数据，请保留关键数据
    4. 语言要正式，适合用于周报

    搜索结果：
    {combined_content}
    """

    # 调用对话接口生成答案
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    chat_payload = {
        "model": "glm-5.3",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": False
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    print("正在生成答案...")
    response = requests.post(url, headers=headers, json=chat_payload)

    if response.status_code != 200:
        error_msg = response.json().get('error', {}).get('message', '未知错误')
        raise Exception(f"生成答案失败: {response.status_code} - {error_msg}")

    chat_result = response.json()
    answer = chat_result['choices'][0]['message']['content']

    return answer, sources

def main():
    """
    主函数
    """
    try:
        # 设置查询
        query = "2026年中国新能源汽车出口的主要目的地国家"

        print(f"开始查询: {query}")
        print("=" * 50)

        # 执行搜索
        search_result = search_with_zhipuai(query)

        # 提取结果和来源
        results, sources = extract_search_results(search_result)

        # 生成答案
        answer, sources = generate_answer(results, sources)

        # 输出结果
        print("\n" + "=" * 50)
        print("2026年中国新能源汽车出口的主要目的地国家")
        print("=" * 50)
        print(answer)

        # 输出来源链接
        print("\n" + "=" * 50)
        print("来源链接（供人工复核）:")
        print("=" * 50)

        if sources:
            for i, source in enumerate(sources[:2], 1):  # 只显示前2个主要来源
                print(f"\n{i}. {source['title']}")
                print(f"   链接: {source['link']}")
                print(f"   摘要: {source['content']}")
        else:
            print("警告: 未能获取到可用的来源链接")

        # 验证完整性
        if len(answer.strip()) < 50:
            print("\n错误: 答案可能不完整，请检查API返回结果")
            return False

        if not sources:
            print("\n错误: 未能获取到可核实的来源链接，无法满足周报要求")
            return False

        print("\n✓ 查询完成，答案完整且包含可核实的来源链接")
        return True

    except Exception as e:
        print(f"\n错误: {str(e)}")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1)