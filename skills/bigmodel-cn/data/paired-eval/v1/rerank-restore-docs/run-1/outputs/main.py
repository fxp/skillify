import os
import requests

def main():
    # 问题
    query = "增值税专用发票要多久内申请"

    # 候选文档
    documents = [
        "签收后 15 日内可无理由退货，商品需保持完好",
        "增值税专用发票需在订单完成后 7 个工作日内申请，逾期需联系客服",
        "公司地址位于北京市海淀区，工作日 9:00-18:00 办公",
        "普通发票支持随时申请，无时间限制",
        "满 199 元包邮，偏远地区除外"
    ]

    # 获取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 构建请求
    url = "https://open.bigmodel.cn/api/paas/v4/rerank"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "rerank",
        "query": query,
        "documents": documents,
        "return_documents": True,
        "return_raw_scores": True
    }

    try:
        # 发送请求
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 按 relevance_score 降序排序
        sorted_results = sorted(
            result['results'],
            key=lambda x: x['relevance_score'],
            reverse=True
        )

        # 输出结果（按相关性从高到低打印原文内容和分数）
        print("按相关性排序结果：")
        print()

        for item in sorted_results:
            print(f"{item['document']}")
            print(f"相关度分数: {item['relevance_score']}")
            print()

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应内容: {e.response.text}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()