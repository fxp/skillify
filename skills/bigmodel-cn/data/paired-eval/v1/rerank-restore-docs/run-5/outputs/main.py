#!/usr/bin/env python3
import os
import requests

def rerank_documents(query, documents):
    """
    使用智谱AI rerank接口对文档进行相关性排序

    Args:
        query (str): 查询文本
        documents (list): 候选文档列表

    Returns:
        list: 按相关性排序后的文档列表，每个元素包含原文和分数
    """
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    # 构建请求URL
    url = "https://open.bigmodel.cn/api/paas/v4/rerank"

    # 构建请求体
    payload = {
        "model": "rerank",
        "query": query,
        "documents": documents,
        "return_documents": True,  # 返回原始文档
        "return_raw_scores": True   # 返回原始分数
    }

    # 设置请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 发送请求
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    # 解析响应
    result = response.json()

    # 提取排序结果
    ranked_results = []
    for item in result['results']:
        ranked_results.append({
            'document': item['document'],
            'score': item['relevance_score']
        })

    # 按分数从高到低排序
    ranked_results.sort(key=lambda x: x['score'], reverse=True)

    return ranked_results

def main():
    # 查询问题
    query = "增值税专用发票要多久内申请"

    # 候选文档
    documents = [
        "签收后 15 日内可无理由退货，商品需保持完好",
        "增值税专用发票需在订单完成后 7 个工作日内申请，逾期需联系客服",
        "公司地址位于北京市海淀区，工作日 9:00-18:00 办公",
        "普通发票支持随时申请，无时间限制",
        "满 199 元包邮，偏远地区除外"
    ]

    try:
        # 调用rerank接口
        ranked_results = rerank_documents(query, documents)

        # 输出结果
        print("按相关性从高到低排序：")
        print("=" * 50)

        for result in ranked_results:
            print(f"{result['document']}")
            print(f"相关性分数: {result['score']:.4f}")
            print("-" * 50)

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()