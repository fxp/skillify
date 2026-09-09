"""用智谱开放平台的 rerank 接口，对候选文档按与问题的相关性从高到低排序。

用法：
    export ZHIPUAI_API_KEY=你的APIKey
    python3 main.py
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
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY")

    resp = requests.post(
        RERANK_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "rerank",
            "query": QUERY,
            "documents": DOCUMENTS,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        sys.exit(f"rerank 接口调用失败：HTTP {resp.status_code} {resp.text}")

    try:
        results = resp.json()["results"]
    except (ValueError, KeyError):
        sys.exit(f"rerank 接口返回异常：{resp.text}")
    if not results:
        sys.exit(f"rerank 接口未返回任何结果：{resp.text}")

    # results 里的 index 对应输入 documents 的下标，据此回溯原文；
    # 官方未承诺返回顺序，这里按相关性分数从高到低自行排序。
    ranked = sorted(results, key=lambda r: r["relevance_score"], reverse=True)
    for item in ranked:
        idx = item["index"]
        if not 0 <= idx < len(DOCUMENTS):
            sys.exit(f"rerank 接口返回的 index 越界：{idx}")
        print(f"{DOCUMENTS[idx]}（相关性：{item['relevance_score']:.4f}）")


if __name__ == "__main__":
    main()
