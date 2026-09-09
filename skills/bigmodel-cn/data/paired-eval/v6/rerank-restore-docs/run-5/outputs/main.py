#!/usr/bin/env python3
import os
import requests

def rerank_documents(query, documents):
    """
    使用智谱重排序接口对文档进行相关性排序

    Args:
        query: 查询文本
        documents: 候选文档列表

    Returns:
        list: 按相关性从高到低排序的结果，每个元素包含文档内容和分数
    """
    # 检查 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    # API 端点
    url = "https://open.bigmodel.cn/api/paas/v4/rerank"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 请求体
    payload = {
        "model": "rerank",
        "query": query,
        "documents": documents,
        "return_documents": True,  # 返回原始文档内容
        "return_raw_scores": True  # 返回原始分数
    }

    # 发送请求
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    # 解析响应
    result = response.json()

    # 将结果转换为 (文档内容, 分数) 的格式
    sorted_results = []
    for item in result['results']:
        document = item['document']
        score = item['relevance_score']
        sorted_results.append((document, score))

    # 按分数从高到低排序
    sorted_results.sort(key=lambda x: x[1], reverse=True)

    return sorted_results

def main():
    # 定义查询问题和候选文档
    query = "增值税专用发票要多久内申请"

    documents = [
        "签收后 15 日内可无理由退货，商品需保持完好",
        "增值税专用发票需在订单完成后 7 个工作日内申请，逾期需联系客服",
        "公司地址位于北京市海淀区，工作日 9:00-18:00 办公",
        "普通发票支持随时申请，无时间限制",
        "满 199 元包邮，偏远地区除外"
    ]

    try:
        # 调用重排序接口
        results = rerank_documents(query, documents)

        # 打印结果（按相关性从高到低，只输出原文和分数）
        print("按相关性从高到低排序结果：")
        for i, (document, score) in enumerate(results, 1):
            print(f"{document}")
            print(f"相关性分数: {score:.4f}")
            print("-" * 50)

    except requests.exceptions.RequestException as e:
        print(f"API 请求错误: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()