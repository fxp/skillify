import os
import requests

def rerank_documents(query, documents):
    """
    使用智谱 rerank 接口对文档进行相关性排序
    """
    # 获取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请在环境变量中设置 ZHIPUAI_API_KEY")

    # 构建请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建请求数据
    data = {
        "model": "rerank",
        "query": query,
        "documents": documents,
        "return_documents": True,  # 返回原始文本
        "return_raw_scores": True  # 返回原始分数
    }

    # 发送请求
    response = requests.post(
        "https://open.bigmodel.cn/api/paas/v4/rerank",
        headers=headers,
        json=data
    )

    # 检查响应状态
    response.raise_for_status()

    # 解析响应
    result = response.json()

    # 提取排序后的结果，按相关性分数从高到低排序
    sorted_results = sorted(result.get('results', []),
                           key=lambda x: x.get('relevance_score', 0),
                           reverse=True)

    return sorted_results

def main():
    # 定义问题
    query = "增值税专用发票要多久内申请"

    # 定义候选文档
    documents = [
        "签收后 15 日内可无理由退货，商品需保持完好",
        "增值税专用发票需在订单完成后 7 个工作日内申请，逾期需联系客服",
        "公司地址位于北京市海淀区，工作日 9:00-18:00 办公",
        "普通发票支持随时申请，无时间限制",
        "满 199 元包邮，偏远地区除外"
    ]

    try:
        # 调用 rerank 接口
        sorted_results = rerank_documents(query, documents)

        # 按相关性从高到低打印原文内容和分数
        print("按相关性排序结果：")
        for result in sorted_results:
            document = result.get('document', '')
            score = result.get('relevance_score', 0)
            print(f"{document}\n分数: {score:.4f}\n")

    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()