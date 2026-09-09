#!/usr/bin/env python3
import os
import requests

def main():
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 查询问题和候选文档
    query = "增值税专用发票要多久内申请"
    documents = [
        "签收后 15 日内可无理由退货，商品需保持完好",
        "增值税专用发票需在订单完成后 7 个工作日内申请，逾期需联系客服",
        "公司地址位于北京市海淀区，工作日 9:00-18:00 办公",
        "普通发票支持随时申请，无时间限制",
        "满 199 元包邮，偏远地区除外"
    ]

    # 构建请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建请求数据
    request_data = {
        "model": "rerank",
        "query": query,
        "documents": documents,
        "return_documents": True,
        "return_raw_scores": True
    }

    try:
        # 调用 rerank 接口
        response = requests.post(
            "https://open.bigmodel.cn/api/paas/v4/rerank",
            headers=headers,
            json=request_data
        )

        # 检查响应状态
        if response.status_code != 200:
            print(f"API 请求失败，状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            return

        # 解析响应
        result = response.json()

        # 按分数从高到低排序
        sorted_results = sorted(result.get('results', []), key=lambda x: x['relevance_score'], reverse=True)

        # 打印排序结果
        print("--- 文档相关性排序（按相关性从高到低） ---")
        for i, item in enumerate(sorted_results, 1):
            document = item['document']
            score = item['relevance_score']
            print(f"相关度 {score:.4f}: {document}")

    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()