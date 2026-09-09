# -*- coding: utf-8 -*-
"""用智谱 rerank 接口对候选文档按与问题的相关性排序，并打印原文与分数。

运行：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import os
import sys

import requests

RERANK_URL = "https://open.bigmodel.cn/api/paas/v4/rerank"

QUERY = "增值税专用发票要多久内申请"

DOCUMENTS = [
    "签收后 15 日内可无理由退货，商品需保持完好",
    "增值税专用发票需在订单完成后 7 个工作日内申请，逾期需联系客服",
    "公司地址位于北京市海淀区，工作日 9:00-18:00 办公",
    "普通发票支持随时申请，无时间限制",
    "满 199 元包邮，偏远地区除外",
]


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：未设置环境变量 ZHIPUAI_API_KEY，请先 export ZHIPUAI_API_KEY=<你的 Key>")

    resp = requests.post(
        RERANK_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "rerank",
            "query": QUERY,
            "documents": DOCUMENTS,
            "top_n": 0,  # 0 = 返回全部候选
            "return_documents": True,
        },
        timeout=30,
    )
    if not resp.ok:
        sys.exit(f"错误：rerank 接口返回 {resp.status_code}：{resp.text}")
    results = resp.json().get("results") or []
    if not results:
        sys.exit("错误：rerank 接口未返回任何结果")

    # 官方文档不保证 results 已按分数降序，这里显式排序；
    # index 对应输入 DOCUMENTS 的下标，用它回查本地列表，确保打印的一定是逐字原文。
    ranked = sorted(results, key=lambda r: r["relevance_score"], reverse=True)

    print(f"问题：{QUERY}")
    print("按相关性从高到低：")
    for item in ranked:
        text = DOCUMENTS[item["index"]]
        print(f"{text} （相关性：{item['relevance_score']:.4f}）")


if __name__ == "__main__":
    main()
