"""用智谱 AI 开放平台的 rerank（重排序）接口，
对候选文档按与问题的相关性从高到低排序，并打印每段文档原文及其分数。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

仅依赖 requests。
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


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：未设置环境变量 ZHIPUAI_API_KEY，请先执行 export ZHIPUAI_API_KEY=<你的Key>")

    resp = requests.post(
        RERANK_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "rerank",
            "query": QUERY,
            "documents": DOCUMENTS,
            # 不传时接口默认不返回原文，这里显式要求带回 document 字段
            "return_documents": True,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        sys.exit(f"调用 rerank 接口失败：HTTP {resp.status_code}，{resp.text}")

    body = resp.json()
    results = body.get("results") or []
    if not results:
        sys.exit(f"错误：rerank 接口未返回结果，响应为：{body}")

    # 官方文档未承诺 results 已按分数排序，这里显式按 relevance_score 降序；
    # 原文一律用 index 回映射到本地 DOCUMENTS，确保打印内容与输入逐字一致
    # （rerank 默认不返回原文，不能依赖响应里的文本字段）。
    ranked = sorted(results, key=lambda r: r["relevance_score"], reverse=True)
    for item in ranked:
        text = DOCUMENTS[item["index"]]
        print(f"{text}（相关度：{item['relevance_score']}）")


if __name__ == "__main__":
    main()
