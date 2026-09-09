#!/usr/bin/env python3
import os
import requests

def rerank_documents(query, documents):
    """
    使用智谱重排序接口对文档进行相关性排序

    Args:
        query (str): 查询文本
        documents (list): 候选文档列表

    Returns:
        list: 按相关性从高到低排序的结果，每个元素包含文档内容和分数
    """
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请在环境变量中设置 ZHIPUAI_API_KEY")

    # API 配置
    url = "https://open.bigmodel.cn/api/paas/v4/rerank"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 请求参数
    payload = {
        "model": "rerank",
        "query": query,
        "documents": documents,
        "return_documents": True,  # 返回原始文档内容
        "return_raw_scores": True   # 返回原始分数
    }

    # 发送请求
    response = requests.post(url, headers=headers, json=payload)

    # 检查响应
    if response.status_code != 200:
        raise Exception(f"API 请求失败: {response.status_code} - {response.text}")

    # 解析响应
    result = response.json()

    # 提取排序结果
    sorted_results = []
    for item in result.get('results', []):
        # 根据分数从高到低排序
        score = item.get('relevance_score', 0)
        document = item.get('document', '')
        sorted_results.append({
            'document': document,
            'score': score
        })

    # 按分数降序排序
    sorted_results.sort(key=lambda x: x['score'], reverse=True)

    return sorted_results

def main():
    # 查询问题
    query = "增值税专用发票要多久内申请"

    # 候选文档列表
    documents = [
        "签收后 15 日内可无理由退货，商品需保持完好",
        "增值税专用发票需在订单完成后 7 个工作日内申请，逾期需联系客服",
        "公司地址位于北京市海淀区，工作日 9:00-18:00 办公",
        "普通发票支持随时申请，无时间限制",
        "满 199 元包邮，偏远地区除外"
    ]

    print(f"查询问题: {query}")
    print("=" * 50)

    try:
        # 调用重排序接口
        results = rerank_documents(query, documents)

        # 打印结果（按相关性从高到低，只输出原文内容和分数）
        print("按相关性从高到低排序结果：")
        print("-" * 50)
        for i, result in enumerate(results, 1):
            print(f"原文内容: {result['document']}")
            print(f"相关度分数: {result['score']:.4f}")
            print()

    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    main()