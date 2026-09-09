"""用智谱 rerank 接口对候选文档按与问题的相关性排序，并打印原文与分数。

运行：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import os
import sys

import requests

QUERY = "增值税专用发票要多久内申请"

DOCUMENTS = [
    "签收后 15 日内可无理由退货，商品需保持完好",
    "增值税专用发票需在订单完成后 7 个工作日内申请，逾期需联系客服",
    "公司地址位于北京市海淀区，工作日 9:00-18:00 办公",
    "普通发票支持随时申请，无时间限制",
    "满 199 元包邮，偏远地区除外",
]

RERANK_URL = "https://open.bigmodel.cn/api/paas/v4/rerank"


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：未设置环境变量 ZHIPUAI_API_KEY")

    resp = requests.post(
        RERANK_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "rerank",
            "query": QUERY,
            "documents": DOCUMENTS,
            "top_n": 0,  # 0 = 返回全部
            "return_documents": True,
        },
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()

    results = body.get("results")
    if not results:
        sys.exit(f"错误：接口未返回结果，响应为：{body}")

    # 按相关性从高到低排序（稳定排序：分数并列时保持接口返回顺序）
    results.sort(key=lambda r: r["relevance_score"], reverse=True)

    # 接口返回的 index 对应输入 documents 的下标，用它回查本地列表，
    # 保证打印的是逐字一致的原文，而不是依赖响应里的 document 字段。
    for item in results:
        idx = item["index"]
        text = DOCUMENTS[idx] if 0 <= idx < len(DOCUMENTS) else item.get("document", "")
        print(f"{text} （相关性：{item['relevance_score']:.4f}）")


if __name__ == "__main__":
    main()
