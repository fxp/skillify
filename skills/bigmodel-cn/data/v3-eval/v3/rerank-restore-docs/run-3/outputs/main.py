"""用智谱重排序接口对候选文档按与问题的相关性排序。

运行：ZHIPUAI_API_KEY=你的key python3 main.py
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
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，请先 export 再运行。", file=sys.stderr)
        sys.exit(1)

    resp = requests.post(
        RERANK_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "rerank",
            "query": QUERY,
            "documents": DOCUMENTS,
            "top_n": 0,  # 0 = 返回全部候选的得分
            "return_documents": True,
        },
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json()["results"]

    # 官方文档未保证 results 已按分数降序，这里显式排一次；
    # 原文以本地 DOCUMENTS 为准（index 回溯），避免依赖响应回显。
    ranked = sorted(
        ({"text": DOCUMENTS[r["index"]], "score": r["relevance_score"]} for r in results),
        key=lambda x: x["score"],
        reverse=True,
    )

    print(f"问题：{QUERY}")
    print("按相关性从高到低：")
    for item in ranked:
        print(f"{item['text']}    相关性分数：{item['score']:.4f}")


if __name__ == "__main__":
    main()
