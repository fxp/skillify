import os
import requests

def rerank_documents():
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 查询文本
    query = "增值税专用发票要多久内申请"

    # 候选文档列表
    documents = [
        "签收后 15 日内可无理由退货，商品需保持完好",
        "增值税专用发票需在订单完成后 7 个工作日内申请，逾期需联系客服",
        "公司地址位于北京市海淀区，工作日 9:00-18:00 办公",
        "普通发票支持随时申请，无时间限制",
        "满 199 元包邮，偏远地区除外"
    ]

    # API端点
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
        "return_documents": True
    }

    try:
        # 发送请求
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 按分数从高到低排序
        sorted_results = sorted(result.get('results', []),
                              key=lambda x: x.get('relevance_score', 0),
                              reverse=True)

        # 输出结果
        print("按相关性从高到低排序结果：")
        print("=" * 50)

        for item in sorted_results:
            print(f"原文内容：{item['document']}")
            print(f"相关性分数：{item['relevance_score']}")
            print("-" * 50)

    except requests.exceptions.RequestException as e:
        print(f"请求失败：{e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_info = e.response.json()
                print(f"错误详情：{error_info}")
            except:
                print(f"响应内容：{e.response.text}")
    except Exception as e:
        print(f"发生错误：{e}")

if __name__ == "__main__":
    rerank_documents()