"""用智谱 rerank 接口对候选文档按与问题的相关性从高到低排序并打印。

运行方式：python3 main.py（需先设置环境变量 ZHIPUAI_API_KEY）
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
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY")

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
            "top_n": len(DOCUMENTS),  # 返回全部候选
        },
        timeout=30,
    )
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        sys.exit(f"错误：接口返回 HTTP {resp.status_code}，详情：{resp.text}\n{exc}")

    results = resp.json().get("results")
    if not results:
        sys.exit(f"错误：接口未返回任何结果，响应内容：{resp.text}")

    # 官方文档未承诺 results 已按分数降序排列，这里自行排序确保从高到低；
    # index 对应输入 DOCUMENTS 的下标，用它回溯本地列表，保证打印的是逐字原文。
    ranked = sorted(results, key=lambda r: r["relevance_score"], reverse=True)
    for item in ranked:
        text = DOCUMENTS[item["index"]]
        print(f"{text} （相关性分数：{item['relevance_score']:.4f}）")


if __name__ == "__main__":
    main()
