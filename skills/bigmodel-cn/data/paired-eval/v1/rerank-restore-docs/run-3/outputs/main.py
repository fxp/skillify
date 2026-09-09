#!/usr/bin/env python3
"""
智谱重排序接口使用示例
对候选文档按与查询的相关性进行排序
"""

import os
import requests

def rerank_documents(query, documents):
    """
    使用智谱重排序 API 对文档进行相关性排序

    Args:
        query (str): 查询文本
        documents (list): 候选文档列表

    Returns:
        list: 按相关性排序后的结果，包含文档原文和得分
    """
    # API 配置
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/rerank"

    # 请求参数
    payload = {
        "model": "rerank",
        "query": query,
        "documents": documents,
        "return_documents": True,
        "return_raw_scores": True
    }

    # 请求头
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
    sorted_results = []
    for item in result["results"]:
        # 根据 index 获取原始文档
        original_doc = documents[item["index"]]
        sorted_results.append({
            "document": original_doc,
            "score": item["relevance_score"]
        })

    return sorted_results

def main():
    """主函数"""
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

    print(f"查询问题：{query}")
    print("=" * 50)
    print("按相关性排序结果：")
    print("=" * 50)

    try:
        # 调用重排序 API
        results = rerank_documents(query, documents)

        # 按分数从高到低排序并输出
        for i, (doc_info) in enumerate(results, 1):
            print(f"{doc_info['document']}")
            print(f"相关性分数: {doc_info['score']:.4f}")
            print("-" * 30)

    except requests.exceptions.RequestException as e:
        print(f"API 请求失败: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()