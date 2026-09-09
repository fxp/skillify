#!/usr/bin/env python3
"""
使用智谱AI联网搜索能力回答"2026年中国新能源汽车出口的主要目的地国家有哪些"
"""

import os
import json
import requests

def search_new_energy_vehicle_exports():
    """使用智谱AI联网搜索新能源汽车出口信息"""

    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("错误：环境变量 ZHIPUAI_API_KEY 未设置")

    # API配置
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建请求数据
    request_data = {
        "model": "glm-4.6",  # 使用支持联网搜索的模型
        "messages": [
            {
                "role": "user",
                "content": "2026年中国新能源汽车出口的主要目的地国家有哪些？请提供详细、完整的信息。"
            }
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro_bing",  # 使用能返回真实链接的搜索引擎
                    "search_query": "2026年中国新能源汽车出口主要目的地国家",
                    "search_intent": False,
                    "count": 10,  # 获取足够多的结果
                    "search_result": True  # 必须设置为True才能获取来源信息
                }
            }
        ],
        "max_tokens": 4000,  # 设置较大的输出长度确保答案完整
        "stream": False
    }

    print("正在搜索2026年中国新能源汽车出口信息...")

    try:
        # 发送请求
        response = requests.post(url, headers=headers, json=request_data, timeout=60)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 检查是否有错误
        if 'error' in result:
            raise Exception(f"API请求错误: {result['error']}")

        # 获取回答内容
        if 'choices' not in result or len(result['choices']) == 0:
            raise Exception("API返回格式异常，未找到回答")

        answer = result['choices'][0]['message']['content']

        # 获取来源链接
        sources = result.get('web_search', [])

        # 验证答案完整性
        if len(answer.strip()) < 100:
            raise Exception("回答内容过短，可能被截断或不完整")

        # 验证来源链接数量
        valid_sources = [source for source in sources if source.get('link')]
        if len(valid_sources) < 2:
            raise Exception(f"来源链接不足：只找到 {len(valid_sources)} 条有效链接，需要至少2条")

        # 格式化输出
        print("\n" + "="*60)
        print("2026年中国新能源汽车出口的主要目的地国家")
        print("="*60)
        print("\n" + answer)
        print("\n" + "-"*60)
        print("信息来源：")
        print("-"*60)

        for i, source in enumerate(valid_sources, 1):
            title = source.get('title', '无标题')
            link = source.get('link', '')
            media = source.get('media', '')
            publish_date = source.get('publish_date', '')

            print(f"{i}. {title}")
            if media:
                print(f"   媒体：{media}")
            if publish_date:
                print(f"   发布时间：{publish_date}")
            print(f"   链接：{link}")
            print()

        print("="*60)
        print(f"信息来源总数：{len(valid_sources)} 条")
        print("="*60)

        return True

    except requests.exceptions.RequestException as e:
        raise Exception(f"网络请求失败: {str(e)}")
    except json.JSONDecodeError as e:
        raise Exception(f"JSON解析失败: {str(e)}")
    except Exception as e:
        raise Exception(f"执行失败: {str(e)}")

def verify_sources(sources):
    """验证来源链接的有效性"""
    print("\n正在验证来源链接...")

    for i, source in enumerate(sources[:3], 1):  # 只验证前3个链接
        link = source.get('link')
        if link:
            try:
                response = requests.head(link, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    print(f"✓ 来源{i}链接有效: {link}")
                else:
                    print(f"⚠ 来源{i}链接状态码异常: {response.status_code} - {link}")
            except Exception as e:
                print(f"✗ 来源{i}链接验证失败: {str(e)} - {link}")

if __name__ == "__main__":
    try:
        # 执行搜索
        success = search_new_energy_vehicle_exports()

        if success:
            print("\n✓ 搜索完成！答案已生成，包含完整的来源链接。")
        else:
            print("\n✗ 搜索失败，请检查错误信息。")

    except Exception as e:
        print(f"\n错误：{str(e)}")
        print("\n请确保：")
        print("1. 已设置环境变量 ZHIPUAI_API_KEY")
        print("2. 网络连接正常")
        print("3. API Key 有效且有足够额度")
        exit(1)